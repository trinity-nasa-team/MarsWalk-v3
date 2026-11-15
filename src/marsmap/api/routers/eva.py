"""EVA con el planificador v4 de Josué (planificador/): rutas, perfil de regreso y capa de arena.

Contrato 02b: todo en lon/lat. Es la fuente de rutas en Jezero; /route (A* legado) queda para los sitios
creados al vuelo fuera de la malla del planificador.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from marsmap.api.deps import ApiError, RegionDep, limit_compute
from marsmap.api.schemas import LatLon, Obstacle
from marsmap.eva import planner

router = APIRouter()


class LegRequest(BaseModel):
    start: LatLon
    goal: LatLon
    preset: Literal["safe", "fast", "science", "balanced"] = "safe"
    agent: Literal["astronaut", "rover"] = "astronaut"
    obstacles: list[Obstacle] = Field(default_factory=list, max_length=20)


class ReturnRequest(BaseModel):
    habitat: LatLon
    waypoints: list[LatLon] = Field(min_length=1, max_length=8)
    budget_wh: float = Field(
        gt=0, le=20_000, description="metabolic energy budget of the suit (Wh)"
    )
    kit_kg: float | None = Field(default=None, ge=0, le=60)


def _only_jezero(region) -> None:
    if region.region.region_id != "jezero":
        raise ApiError(422, "planner_unavailable", "The v4 planner only covers Jezero.")


def _run(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except planner.PlannerError as exc:
        raise ApiError(422, exc.code, exc.message) from exc


@router.post("/regions/{region_id}/eva/replan-leg", dependencies=[Depends(limit_compute)])
def replan_leg(region: RegionDep, body: LegRequest) -> dict:
    """Una ruta A -> B (~0.1 s) compatible con RouteOut, más procedencia, arena y O2 (planificador v4)."""
    _only_jezero(region)
    hazards = [{"lon": o.lon, "lat": o.lat, "radius_m": o.radius_m} for o in body.obstacles]
    return _run(
        planner.replan_leg,
        (body.start.lon, body.start.lat),
        (body.goal.lon, body.goal.lat),
        body.agent,
        body.preset,
        hazards,
    )


@router.post("/regions/{region_id}/eva/return-profile", dependencies=[Depends(limit_compute)])
def return_profile(region: RegionDep, body: ReturnRequest) -> dict:
    """Energía gastada, energía para volver y punto de no retorno a lo largo de la EVA del astronauta."""
    _only_jezero(region)
    return _run(
        planner.return_profile,
        (body.habitat.lon, body.habitat.lat),
        [(w.lon, w.lat) for w in body.waypoints],
        body.budget_wh,
        body.kit_kg,
    )


@router.get("/regions/{region_id}/eva/sand-layer")
def sand_layer(region: RegionDep) -> dict:
    _only_jezero(region)
    return _run(planner.sand_layer_meta)


@router.get("/regions/{region_id}/eva/sand-layer.png")
def sand_layer_png(region: RegionDep) -> Response:
    _only_jezero(region)
    png, _ = planner.sand_layer_png()
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
