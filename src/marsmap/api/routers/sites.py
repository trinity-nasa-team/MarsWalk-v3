"""Hábitat en cualquier lugar de Marte (016): crea una región de sitio desde el DEM global."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from rasterio.errors import RasterioIOError

from marsmap.api.deps import ApiError, limit_mission
from marsmap.geo.coords import normalize_lon
from marsmap.terrain.build import BuildError
from marsmap.terrain.site import build_site

router = APIRouter()
log = logging.getLogger("marsmap.api.sites")


class SiteRequest(BaseModel):
    lat: float = Field(
        ge=-85, le=85
    )  # el DEM y la proyección del mapa se degradan cerca de los polos
    lon: float = Field(ge=-180, le=360)

    @field_validator("lon")
    @classmethod
    def _norm(cls, v: float) -> float:
        return normalize_lon(v)


@router.post("/sites", dependencies=[Depends(limit_mission)])
def create_site(body: SiteRequest, request: Request) -> dict:
    """Devuelve la región que contiene el punto: Jezero si cae dentro; si no, un sitio nuevo (≈ 44 × 44 km)."""
    registry = request.app.state.registry
    for rid, data in registry.regions.items():
        if rid.startswith("site_"):
            continue
        w, s, e, n = data.region.bbox
        if w <= body.lon <= e and s <= body.lat <= n:
            return _out(data)
    try:
        region = build_site(
            body.lat, body.lon, request.app.state.settings.data_dir, request.app.state.site_dem
        )
    except (BuildError, RasterioIOError, ValueError, OSError) as exc:
        log.warning("no se pudo crear el sitio %.3f, %.3f: %s", body.lat, body.lon, exc)
        raise ApiError(
            422, "site_unavailable", "No hay relieve disponible para ese punto."
        ) from exc
    data = registry.get(region.region_id) or registry.load(region)
    if data is None:
        raise ApiError(500, "site_failed", "No se pudo cargar el sitio.")
    return _out(data)


def _out(data) -> dict:
    meta = data.layers.get("elevation")
    return {
        "region_id": data.region.region_id,
        "name": data.region.name,
        "bbox": list(data.region.bbox),
        "resolution_m": meta.resolution_m if meta else None,
        "source_dataset": meta.source_dataset if meta else None,
    }
