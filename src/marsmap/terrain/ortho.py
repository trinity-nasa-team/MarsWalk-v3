"""Ortomosaico real de una región con los tiles WMTS de NASA Mars Trek (feature 014).

Matriz geográfica de Trek (`default028mm`): origen (−180°, 90°), nivel z = 2^(z+1) × 2^z tiles de 256 px,
cada tile mide 180/2^z grados. Es la misma convención que usa el proyecto (lon −180..180 E, esfera Mars 2000).

    python -m marsmap.terrain.ortho --region jezero

Base: CTX (toda la región). Detalle: ventana HiRISE alrededor del hábitat. Color: Viking MDIM 2.1
(~330 m/px) aplicado por pansharpening (luminancia de CTX/HiRISE + crominancia de Viking): es color
APROXIMADO y así se declara en los metadatos.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from marsmap.config.regions import get_region
from marsmap.geo.coords import MARS_GEO_CRS
from marsmap.terrain.fetch import check_url

log = logging.getLogger("marsmap.ortho")

TILE_PX = 256
TREK = (
    "https://trek.nasa.gov/tiles/Mars/EQ/{layer}/1.0.0/default/default028mm/{z}/{row}/{col}.{ext}"
)
MARS_RADIUS_M = 3_396_190
CHUNK_PX = 2048


@dataclass(frozen=True)
class TrekLayer:
    layer: str
    ext: str
    title: str
    mission: str
    instrument: str
    native_resolution: str
    coverage: tuple[float, float, float, float]  # bbox lon/lat del producto
    created: str


# Verificados en el catálogo de Trek (searchItems + WMTSCapabilities.xml) el 2026-11-14.
CTX = TrekLayer(
    "Jezero_CTX_BlockAdj_dd", "png", "MRO CTX, Jezero Mosaic, Preliminary",
    "Mars Reconnaissance Orbiter", "CTX", "~6 m/px",
    (75.1537692, 15.9058484, 78.8717121, 19.4453003), "2020-08-03",
)  # fmt: skip
HIRISE = TrekLayer(
    "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd", "png",
    "MRO HiRISE, Jezero Mosaic, Controlled (USGS, Mars 2020 TRN)",
    "Mars Reconnaissance Orbiter", "HiRISE", "25 cm/px",
    (77.2229331, 18.3067994, 77.583964, 18.669315), "2020-08-03",
)  # fmt: skip
VIKING = TrekLayer(
    "Mars_Viking_MDIM21_ClrMosaic_global_232m", "jpg", "Viking VIS, Global Color Mosaic (MDIM 2.1)",
    "Viking Orbiter", "VIS", "232 m/px (servido hasta z = 7, ~330 m/px)",
    (-180.0, -90.0, 180.0, 90.0), "",
)  # fmt: skip


def deg_per_px(z: int) -> float:
    return 180.0 / (2**z * TILE_PX)


def m_per_px(z: int) -> float:
    return deg_per_px(z) * math.pi / 180 * MARS_RADIUS_M


def tile_range(bbox, z: int) -> tuple[range, range]:
    """Columnas y filas de tiles que cubren el bbox (lon_min, lat_min, lon_max, lat_max)."""
    w, s, e, n = bbox
    size = 180.0 / 2**z
    c0, c1 = math.floor((w + 180) / size), math.floor((e + 180) / size - 1e-12)
    r0, r1 = math.floor((90 - n) / size), math.floor((90 - s) / size - 1e-12)
    return range(c0, c1 + 1), range(r0, r1 + 1)


def tiles_bbox(cols: range, rows: range, z: int) -> tuple[float, float, float, float]:
    size = 180.0 / 2**z
    return (
        -180 + cols.start * size,
        90 - (rows.stop) * size,
        -180 + cols.stop * size,
        90 - rows.start * size,
    )


Fetcher = Callable[[str], bytes | None]


def http_fetch(url: str, retries: int = 3) -> bytes | None:
    """Descarga un tile; None si no existe (404). Reintenta errores transitorios."""
    check_url(url)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(  # noqa: S310 (https y host en lista blanca: check_url)
                url, headers={"User-Agent": "marsmap/0.1 (NASA Space Apps)"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (URL en lista blanca)
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(1.5 * (attempt + 1))
    return None


def mosaic(
    layer: TrekLayer, bbox, z: int, cache: Path, fetch: Fetcher = http_fetch
) -> tuple[np.ndarray, tuple]:
    """Empata los tiles de `layer` que cubren `bbox` en un arreglo RGBA y devuelve (arreglo, bbox_tiles).

    Cada tile va en su fila/columna exacta; los que faltan (404) quedan transparentes. Caché en disco.
    """
    cols, rows = tile_range(bbox, z)
    out = np.zeros((len(rows) * TILE_PX, len(cols) * TILE_PX, 4), dtype=np.uint8)
    got = 0
    for i, row in enumerate(rows):
        for j, col in enumerate(cols):
            f = cache / layer.layer / str(z) / str(row) / f"{col}.{layer.ext}"
            if f.is_file():
                data = f.read_bytes()
            else:
                data = fetch(TREK.format(layer=layer.layer, z=z, row=row, col=col, ext=layer.ext))
                if data is None:
                    continue
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
            tile = Image.open(BytesIO(data)).convert("RGBA").resize((TILE_PX, TILE_PX))
            out[i * TILE_PX : (i + 1) * TILE_PX, j * TILE_PX : (j + 1) * TILE_PX] = np.asarray(tile)
            got += 1
    log.info("%s z%d: %d/%d tiles", layer.layer, z, got, len(rows) * len(cols))
    return out, tiles_bbox(cols, rows, z)


def crop(arr: np.ndarray, arr_bbox, target_bbox, z: int) -> tuple[np.ndarray, tuple]:
    """Recorta al bbox pedido, alineado a píxeles. Devuelve (arreglo, bbox_exacto_del_recorte)."""
    d = deg_per_px(z)
    w0, _, _, n0 = arr_bbox
    w, s, e, n = target_bbox
    c0 = max(0, int(math.floor((w - w0) / d)))
    c1 = min(arr.shape[1], int(math.ceil((e - w0) / d)))
    r0 = max(0, int(math.floor((n0 - n) / d)))
    r1 = min(arr.shape[0], int(math.ceil((n0 - s) / d)))
    out = arr[r0:r1, c0:c1]
    return out, (w0 + c0 * d, n0 - r1 * d, w0 + c1 * d, n0 - r0 * d)


def colorize(gray_rgba: np.ndarray, gray_bbox, color_rgba: np.ndarray, color_bbox) -> np.ndarray:
    """Pansharpening: Y (detalle) de la imagen fina + Cb/Cr (color) de la gruesa, remuestreada al mismo bbox."""
    h, w = gray_rgba.shape[:2]
    cw, cs, ce, cn = color_bbox
    gw, gs, ge, gn = gray_bbox
    ch, cwid = color_rgba.shape[:2]
    # Recorte de la imagen de color al bbox de la fina (en píxeles de la gruesa, con decimales).
    box = (
        (gw - cw) / (ce - cw) * cwid,
        (cn - gn) / (cn - cs) * ch,
        (ge - cw) / (ce - cw) * cwid,
        (cn - gs) / (cn - cs) * ch,
    )
    color = Image.fromarray(color_rgba[..., :3]).resize((w, h), Image.BICUBIC, box=box)
    _, cb, cr = color.convert("YCbCr").split()
    y = Image.fromarray(gray_rgba[..., :3]).convert("L")
    rgb = np.asarray(Image.merge("YCbCr", (y, cb, cr)).convert("RGB"))
    return np.dstack([rgb, gray_rgba[..., 3]])


def write_chunks(
    arr: np.ndarray, bbox, out_dir: Path, prefix: str, z: int, quality: int = 82
) -> list[dict]:
    """Corta en trozos ≤ CHUNK_PX y los guarda como WebP (con alfa). Devuelve [{id, file, bbox}]."""
    d = deg_per_px(z)
    w0, _, _, n0 = bbox
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for r0 in range(0, arr.shape[0], CHUNK_PX):
        for c0 in range(0, arr.shape[1], CHUNK_PX):
            part = arr[r0 : r0 + CHUNK_PX, c0 : c0 + CHUNK_PX]
            if part[..., 3].max() == 0:
                continue  # sin datos
            cid = f"{prefix}_{r0 // CHUNK_PX}_{c0 // CHUNK_PX}"
            name = f"{cid}.webp"
            Image.fromarray(part, "RGBA").save(out_dir / name, "WEBP", quality=quality, method=6)
            h, w = part.shape[:2]
            chunks.append(
                {
                    "id": cid,
                    "file": name,
                    "bbox": [w0 + c0 * d, n0 - (r0 + h) * d, w0 + (c0 + w) * d, n0 - r0 * d],
                }
            )
    return chunks


def window_bbox(center_lonlat, km: float) -> tuple[float, float, float, float]:
    lon, lat = center_lonlat
    half_lat = (km * 500) / MARS_RADIUS_M * 180 / math.pi
    half_lon = half_lat / math.cos(math.radians(lat))
    return (lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat)


def intersect(a, b):
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (w, s, e, n) if w < e and s < n else None


def _layer_meta(
    layer: TrekLayer, lid: str, name: str, z: int, bbox, chunks, retrieved: str
) -> dict:
    return {
        "layer_id": lid,
        "name": name,
        "source_dataset": layer.title,
        "trek_layer": layer.layer,
        "mission": layer.mission,
        "instrument": layer.instrument,
        "native_resolution": layer.native_resolution,
        "resolution_m": round(m_per_px(z), 2),
        "zoom": z,
        "bbox": [round(v, 7) for v in bbox],
        "product_date": layer.created,
        "retrieved_at": retrieved,
        "color": f"Aproximado: crominancia de {VIKING.title} ({VIKING.native_resolution}) por pansharpening.",
        "limitations": (
            "Imagen visible ortorrectificada; mosaico de tomas con iluminación y fechas distintas "
            "(puede haber costuras de brillo). El color NO es de este instrumento: viene de Viking a baja "
            "resolución y es aproximado."
        ),
        "chunks": chunks,
    }


def build_ortho(
    region_id: str,
    processed_dir: Path,
    raw_dir: Path,
    *,
    center=None,
    hirise_km: float = 5.0,
    ctx_zoom: int = 12,
    hirise_zoom: int = 15,
    viking_zoom: int = 7,
    overview_px: int = 4096,
    fetch: Fetcher = http_fetch,
) -> dict:
    region = get_region(region_id)
    bbox = tuple(region.bbox)
    out_dir = processed_dir / region_id / "ortho"
    cache = raw_dir / region_id / "ortho_tiles"
    retrieved = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Color (Viking): cubre todo, baja resolución.
    vik, vik_bbox = mosaic(VIKING, bbox, viking_zoom, cache, fetch)

    # Base CTX recortada a la región.
    ctx_full, ctx_tb = mosaic(CTX, bbox, ctx_zoom, cache, fetch)
    ctx, ctx_bbox = crop(ctx_full, ctx_tb, bbox, ctx_zoom)
    ctx = colorize(ctx, ctx_bbox, vik, vik_bbox)
    _write_geotiff(raw_dir / region_id / f"ortho_ctx_z{ctx_zoom}.tif", ctx, ctx_bbox)
    layers = [
        _layer_meta(
            CTX, "ortho_ctx", "Imagen real CTX", ctx_zoom, ctx_bbox,
            write_chunks(ctx, ctx_bbox, out_dir, "ctx", ctx_zoom), retrieved,
        )
    ]  # fmt: skip

    # Vista general para la textura 3D del visor.
    scale = overview_px / max(ctx.shape[:2])
    ov = Image.fromarray(ctx, "RGBA").resize(
        (round(ctx.shape[1] * scale), round(ctx.shape[0] * scale)), Image.LANCZOS
    )
    ov.convert("RGB").save(out_dir / "overview.webp", "WEBP", quality=80, method=6)

    # Ventana HiRISE alrededor del hábitat.
    if center is not None and hirise_km > 0:
        win = intersect(window_bbox(center, hirise_km), HIRISE.coverage)
        if win:
            hi_full, hi_tb = mosaic(HIRISE, win, hirise_zoom, cache, fetch)
            hi, hi_bbox = crop(hi_full, hi_tb, win, hirise_zoom)
            if hi[..., 3].any():
                hi = colorize(hi, hi_bbox, vik, vik_bbox)
                layers.append(
                    _layer_meta(
                        HIRISE, "ortho_hirise", "Imagen real HiRISE (ventana)", hirise_zoom, hi_bbox,
                        write_chunks(hi, hi_bbox, out_dir, "hirise", hirise_zoom), retrieved,
                    )
                )  # fmt: skip

    manifest = {
        "region_id": region_id,
        "crs": MARS_GEO_CRS,
        "source": "NASA Mars Trek WMTS (trek.nasa.gov) · USGS Astrogeology",
        "overview": {"file": "overview.webp", "bbox": [round(v, 7) for v in ctx_bbox]},
        "layers": layers,
    }
    (out_dir / "ortho.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return manifest


def _write_geotiff(path: Path, arr: np.ndarray, bbox) -> None:
    """GeoTIFF completo (pesado) a data/raw/, fuera de git."""
    import rasterio
    from rasterio.transform import from_bounds

    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape[:2]
    with rasterio.open(
        path, "w", driver="GTiff", width=w, height=h, count=4, dtype="uint8",
        crs=MARS_GEO_CRS, transform=from_bounds(*bbox, w, h), compress="deflate", tiled=True,
    ) as dst:  # fmt: skip
        dst.write(np.moveaxis(arr, -1, 0))


def _default_center(processed_dir: Path, region_id: str):
    """Hábitat por defecto: primer waypoint del recorrido real de Perseverance (sitio de aterrizaje)."""
    trav = processed_dir / region_id / "traverse.geojson"
    if trav.is_file():
        coords = json.loads(trav.read_text(encoding="utf-8"))["geometry"]["coordinates"]
        if coords:
            return tuple(coords[0])
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ortomosaico real (NASA Mars Trek) de una región.")
    p.add_argument("--region", default="jezero")
    p.add_argument("--processed", type=Path, default=Path("data/processed"))
    p.add_argument("--raw", type=Path, default=Path("data/raw"))
    p.add_argument(
        "--center", help="lat,lon de la ventana HiRISE (por defecto, el sitio de aterrizaje)"
    )
    p.add_argument("--hirise-km", type=float, default=5.0)
    p.add_argument("--ctx-zoom", type=int, default=12)
    p.add_argument("--hirise-zoom", type=int, default=15)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    center = None
    if a.center:
        lat, lon = (float(v) for v in a.center.split(","))
        center = (lon, lat)
    else:
        center = _default_center(a.processed, a.region)
    try:
        m = build_ortho(
            a.region, a.processed, a.raw, center=center, hirise_km=a.hirise_km,
            ctx_zoom=a.ctx_zoom, hirise_zoom=a.hirise_zoom,
        )  # fmt: skip
    except (KeyError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for layer in m["layers"]:
        print(f"{layer['layer_id']}: {len(layer['chunks'])} trozos, {layer['resolution_m']} m/px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
