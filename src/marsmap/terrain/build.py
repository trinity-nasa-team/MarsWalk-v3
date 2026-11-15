"""CLI: DEM → capas de terreno en `data/processed/<region>/`.

Ejemplos:
    python -m marsmap.terrain.build --region jezero --synthetic --seed 42
    python -m marsmap.terrain.build --region jezero --source data/raw/jezero/dem.tif
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from marsmap.config.regions import get_region, validate_bbox
from marsmap.geo.coords import MARS_GEO_CRS, cell_size_m, row_latitudes
from marsmap.terrain import derive
from marsmap.terrain.dem import read_dem_window
from marsmap.terrain.metadata import LayerMetadata, RegionMetadata, now_iso, write_metadata
from marsmap.terrain.synthetic import generate_dem

DEFAULT_OUT = Path(os.environ.get("DATA_DIR", "data/processed"))


@dataclass(frozen=True)
class LayerSpec:
    layer_id: str
    name: str
    units: str
    dtype: str
    nodata: float
    limitation: str


LAYERS = [
    LayerSpec("elevation", "Elevación", "m (datum Mars 2000)", "float32", np.nan,
              "Elevación media de celda; no resuelve rocas ni escarpes menores que la celda."),
    LayerSpec("slope", "Pendiente", "grados", "float32", np.nan,
              "Pendiente promedio a escala de celda; subestima pendientes locales más cortas."),
    LayerSpec("roughness", "Rugosidad", "m (desv. estándar 3×3)", "float32", np.nan,
              "Rugosidad a escala de 3 celdas; no detecta rocas individuales."),
    LayerSpec("hillshade", "Sombreado del relieve", "0–255", "uint8", derive.HILLSHADE_NODATA,
              "Visualización (azimut 315°, altitud 45°); sin valor físico."),
    LayerSpec("traversability", "Transitabilidad", "0 segura, 1 riesgo, 2 bloqueada", "uint8",
              derive.TRAV_NODATA,
              "Solo por pendiente (umbrales de Perseverance 10°/15°); no ve arena blanda ni rocas."),
]  # fmt: skip

SOURCE_INFO = {
    "synthetic": ("synthetic", "Generador sintético determinista"),
    "dem": ("MOLA_HRSC_Blend_200m_v2", "MGS MOLA + MEX HRSC"),
}


class BuildError(Exception):
    """Error de entrada controlado: la CLI sale con código ≠ 0 y un mensaje claro."""


# Suelo suelto (015): THEMIS IR nocturno. De noche el polvo y la arena fina (baja inercia térmica) se enfrían
# antes que la roca. Umbral de demo: brillo ≤ 75/255 (≈ percentil 25 dentro de Jezero, medido 2026-11-14).
THEMIS_FINES_MAX = 75


def fines_mask(transform: Affine, shape: tuple[int, int], raw_dir: Path) -> np.ndarray:
    """Máscara de material fino a partir del mosaico THEMIS nocturno (Trek, z = 9, ~80 m/px)."""
    from marsmap.terrain.ortho import TrekLayer, deg_per_px, mosaic

    layer = TrekLayer(
        "THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018", "png", "THEMIS IR Night 100 m",
        "Mars Odyssey", "THEMIS", "100 m/px", (-180, -90, 180, 90), "2018-10",
    )  # fmt: skip
    h, w = shape
    lon0, lat0 = transform.c, transform.f
    bbox = (lon0, lat0 + h * transform.e, lon0 + w * transform.a, lat0)
    arr, tb = mosaic(layer, bbox, 9, raw_dir / "themis_tiles")
    g = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    d = deg_per_px(9)
    cols = ((lon0 + (np.arange(w) + 0.5) * transform.a - tb[0]) / d).astype(int)
    rows = ((tb[3] - (lat0 + (np.arange(h) + 0.5) * transform.e)) / d).astype(int)
    sub = g[np.clip(rows, 0, g.shape[0] - 1)][:, np.clip(cols, 0, g.shape[1] - 1)]
    valid = arr[..., 3][np.clip(rows, 0, g.shape[0] - 1)][:, np.clip(cols, 0, g.shape[1] - 1)] > 0
    return valid & (sub <= THEMIS_FINES_MAX)


def derive_layers(z: np.ndarray, transform: Affine) -> dict[str, np.ndarray]:
    lats = row_latitudes(transform, z.shape[0])
    dx_m, dy_m = cell_size_m(transform, lats)
    slope = derive.slope_deg(z, dx_m, dy_m)
    return {
        "elevation": z.astype(np.float32),
        "slope": slope,
        "roughness": derive.roughness(z),
        "hillshade": derive.hillshade(z, dx_m, dy_m),
        "traversability": derive.traversability(slope),
    }


def _write_tif(path: Path, array: np.ndarray, transform: Affine, spec: LayerSpec) -> None:
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": spec.dtype,
        "crs": MARS_GEO_CRS,
        "transform": transform,
        "nodata": spec.nodata,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype(spec.dtype), 1)


def _check_alignment(folder: Path) -> None:
    ref = None
    for spec in LAYERS:
        with rasterio.open(folder / f"{spec.layer_id}.tif") as ds:
            sig = (ds.width, ds.height, tuple(ds.transform), ds.crs.to_string())
        if ref is None:
            ref = sig
        elif sig != ref:
            raise BuildError(f"la capa {spec.layer_id} no está alineada con las demás")


def build(
    region_id: str,
    out_root: Path = DEFAULT_OUT,
    source: str | None = None,
    synthetic: bool = False,
    seed: int = 42,
    bbox_override=None,
    resolution_m: float = 200.0,
    dem_resolution_m: float | None = None,
    source_info: tuple[str, str] | None = None,
    themis_raw: Path | None = None,
    region_obj=None,
) -> Path:
    try:
        region = region_obj or get_region(region_id)  # region_obj: sitios dinámicos (016)
    except KeyError as exc:
        raise BuildError(str(exc)) from exc
    try:
        bbox = validate_bbox(bbox_override) if bbox_override is not None else region.bbox
    except ValueError as exc:
        raise BuildError(f"bbox inválido: {exc}") from exc

    if synthetic:
        z, transform, _, _ = generate_dem(bbox, resolution_m=resolution_m, seed=seed)
        res_m, kind = resolution_m, "synthetic"
    else:
        if not source:
            raise BuildError("indica --source <dem> o --synthetic")
        if not source.startswith("/vsicurl/https://") and not Path(source).is_file():
            raise BuildError(f"no existe el archivo DEM: {source}")
        try:
            win = read_dem_window(source, bbox, dem_resolution_m)
        except ValueError as exc:  # incluye DemCoverageError
            raise BuildError(str(exc)) from exc
        z, transform, res_m, kind = win.elevation, win.transform, win.resolution_m, "dem"

    layers = derive_layers(z, transform)
    fines_note = ""
    if themis_raw is not None:
        fines = fines_mask(transform, z.shape, themis_raw)
        trav = layers["traversability"]
        trav[(trav == derive.TRAV_SAFE) & fines] = derive.TRAV_RISK
        fines_note = (
            f" Además, riesgo en material fino según THEMIS IR nocturno (brillo ≤ {THEMIS_FINES_MAX}/255,"
            " umbral de demo): {:.0%} de las celdas.".format(float(fines.mean()))
        )
    out_root.mkdir(parents=True, exist_ok=True)
    final = out_root / region.region_id
    tmp = out_root / f".{region.region_id}.tmp-{os.getpid()}"
    old = out_root / f".{region.region_id}.old-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        dataset, instrument = source_info if (source_info and kind == "dem") else SOURCE_INFO[kind]
        generated_at = now_iso()
        metas = []
        for spec in LAYERS:
            _write_tif(tmp / f"{spec.layer_id}.tif", layers[spec.layer_id], transform, spec)
            metas.append(
                LayerMetadata(
                    layer_id=spec.layer_id,
                    name=spec.name,
                    units=spec.units,
                    file=f"{spec.layer_id}.tif",
                    source_dataset=dataset if kind == "dem" else f"synthetic(seed={seed})",
                    instrument=instrument,
                    resolution_m=round(float(res_m), 3),
                    crs=MARS_GEO_CRS,
                    bbox=tuple(round(v, 6) for v in bbox),
                    generated_at=generated_at,
                    limitations=spec.limitation
                    + (fines_note if spec.layer_id == "traversability" else "")
                    + " Proyección lon/lat: el mapa web distorsiona ~5% a 18° de latitud.",
                )
            )
        h, w = z.shape
        write_metadata(
            tmp, RegionMetadata(region_id=region.region_id, width=w, height=h, layers=metas)
        )
        _check_alignment(tmp)
        # Conserva los archivos que no son capas (POI, zonas prohibidas…).
        if final.exists():
            for extra in final.glob("*.geojson"):
                shutil.copy2(extra, tmp / extra.name)
            for sub in (d for d in final.iterdir() if d.is_dir()):  # p. ej. ortho/ (014)
                shutil.copytree(sub, tmp / sub.name)
            final.rename(old)
        tmp.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        if old.exists() and not final.exists():
            old.rename(final)
        raise
    return final


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="marsmap.terrain.build", description=__doc__)
    p.add_argument("--region", required=True, help="region_id de regions.yaml (p. ej. jezero)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--source", help="ruta al DEM (GeoTIFF/IMG) ya descargado")
    src.add_argument("--synthetic", action="store_true", help="usar terreno sintético")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--bbox", type=float, nargs=4, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX")
    )
    p.add_argument("--resolution-m", type=float, default=200.0, help="solo con --synthetic")
    p.add_argument("--dem-resolution-m", type=float, help="remuestrea el DEM real a esta celda (m)")
    p.add_argument("--dataset", help="nombre del producto DEM (metadatos)")
    p.add_argument("--instrument", help="instrumento del DEM (metadatos)")
    p.add_argument(
        "--themis", action="store_true", help="marca material fino (THEMIS IR nocturno) como riesgo"
    )
    args = p.parse_args(argv)
    try:
        out = build(
            args.region,
            args.out,
            args.source,
            args.synthetic,
            args.seed,
            args.bbox,
            args.resolution_m,
            args.dem_resolution_m,
            (args.dataset, args.instrument) if args.dataset and args.instrument else None,
            Path("data/raw") / args.region if args.themis else None,
        )
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"capas generadas en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
