"""Regiones, capas, imágenes y consulta de celda (feature 002)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Path, Query, Request, Response
from fastapi.responses import FileResponse

from marsmap.api import render
from marsmap.api.deps import ApiError, RegionDep
from marsmap.api.schemas import CellOut, LayerOut, RegionOut
from marsmap.geo.coords import lonlat_to_rowcol, normalize_lon

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/regions", response_model=list[RegionOut])
def list_regions(request: Request) -> list[RegionOut]:
    return [
        RegionOut(
            region_id=d.region.region_id,
            name=d.region.name,
            bbox=list(d.region.bbox),
            description=d.region.description,
        )
        for d in request.app.state.registry.regions.values()
    ]


@lru_cache(maxsize=64)
def _legend(layer_id: str, path: str) -> tuple:
    return tuple(render.legend(layer_id, path))


@router.get("/regions/{region_id}/layers", response_model=list[LayerOut])
def list_layers(region: RegionDep) -> list[LayerOut]:
    out = []
    for lid, meta in region.layers.items():
        out.append(
            LayerOut(
                **meta.model_dump(exclude={"file", "bbox"}),
                bbox=list(meta.bbox),
                legend=list(_legend(lid, str(region.layer_files[lid]))),
                image_url=f"/api/regions/{region.region.region_id}/layers/{lid}/image",
            )
        )
    return out


@lru_cache(maxsize=32)
def _png(layer_id: str, path: str, mtime: float) -> bytes:  # mtime invalida la caché al regenerar
    return render.render_png(layer_id, path)


@router.get("/regions/{region_id}/layers/{layer_id}/image")
def layer_image(
    region: RegionDep, layer_id: Annotated[str, Path(pattern=r"^[a-z_]+$", max_length=64)]
):
    f = region.layer_files.get(
        layer_id
    )  # solo la lista blanca: nunca se concatena layer_id a una ruta
    if f is None:
        raise ApiError(404, "layer_not_found", "Capa no encontrada.")
    return Response(
        _png(layer_id, str(f), f.stat().st_mtime),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/regions/{region_id}/cell", response_model=CellOut)
def cell(
    region: RegionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=360)],
) -> CellOut:
    grid = region.grid
    lon = normalize_lon(lon)
    row, col = lonlat_to_rowcol(grid.transform, lon, lat)
    h, w = grid.shape
    if not (0 <= row < h and 0 <= col < w):
        raise ApiError(422, "out_of_region", "La coordenada está fuera de la región.")

    def val(layer_id: str):
        f = region.layer_files.get(layer_id)
        if f is None:
            return None
        v, _ = render.sample(f, row, col)
        return None if render.is_nodata(layer_id, v) else float(v)

    trav = val("traversability")
    return CellOut(
        lat=lat,
        lon=lon,
        elevation_m=val("elevation"),
        slope_deg=val("slope"),
        roughness_m=val("roughness"),
        traversability=None if trav is None else int(trav),
    )


@router.get("/regions/{region_id}/terrain-grid")
def terrain_grid_meta(region: RegionDep) -> dict:
    """Metadatos de la malla de elevación (para la vista 3D a ras de suelo)."""
    grid = region.grid
    h, w = grid.shape
    t = grid.transform
    meta = region.layers.get("elevation")
    return {
        "width": w,
        "height": h,
        "transform": [
            t.a,
            t.c,
            t.e,
            t.f,
        ],  # lon = c + col·a ; lat = f + row·e (grados, −180..180 E)
        "units": "m (datum Mars 2000)",
        "dtype": "float32-le",
        "nodata": "NaN",
        "resolution_m": meta.resolution_m if meta else None,
        "source_dataset": meta.source_dataset if meta else None,
        "data_url": f"/api/regions/{region.region.region_id}/terrain-grid.f32",
    }


@router.get("/regions/{region_id}/terrain-grid.f32")
def terrain_grid_data(region: RegionDep) -> Response:
    """Elevación en metros, float32 little-endian, fila mayor (NaN = sin dato)."""
    z = np.asarray(region.grid.elevation, dtype="<f4")
    return Response(
        z.tobytes(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/regions/{region_id}/traverse")
def traverse(region: RegionDep) -> dict:
    """Recorrido real de Perseverance (NASA/JPL) si está procesado para la región."""
    if region.traverse is None:
        raise ApiError(404, "traverse_not_found", "Esta región no tiene recorrido procesado.")
    return region.traverse


@router.get("/regions/{region_id}/ortho")
def ortho(region: RegionDep) -> dict:
    """Manifiesto del ortomosaico real (NASA Mars Trek): capas, trozos con bbox y metadatos."""
    m = region.ortho
    if m is None:
        raise ApiError(404, "ortho_not_found", "Esta región no tiene ortomosaico procesado.")
    rid = region.region.region_id
    base = f"/api/regions/{rid}/ortho"
    layers = [
        {**{k: v for k, v in layer.items() if k != "chunks"},
         "chunks": [{"id": c["id"], "bbox": c["bbox"], "url": f"{base}/{c['id']}"} for c in layer["chunks"]]}
        for layer in m["layers"]
    ]  # fmt: skip
    ov = m.get("overview")
    return {
        "region_id": rid,
        "crs": m.get("crs"),
        "source": m.get("source"),
        "overview": {"bbox": ov["bbox"], "url": f"{base}/overview"} if ov else None,
        "layers": layers,
    }


@router.get("/regions/{region_id}/ortho/{chunk_id}")
def ortho_chunk(
    region: RegionDep, chunk_id: Annotated[str, Path(pattern=r"^[a-z0-9_]+$", max_length=64)]
) -> FileResponse:
    """Un trozo del ortomosaico (WebP). Solo ids del manifiesto: nunca se arma una ruta con texto del cliente."""
    files = (region.ortho or {}).get("_files", {})
    if chunk_id not in files:
        raise ApiError(404, "chunk_not_found", "Trozo de ortomosaico inexistente.")
    return FileResponse(
        files[chunk_id], media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"}
    )
