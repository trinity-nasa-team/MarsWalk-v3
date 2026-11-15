"""Servicio de rutas: valida puntos, arma el mapa de costos con restricciones y corre A*."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from marsmap.planning.astar import astar
from marsmap.planning.constraints import forbidden_mask, radius_mask, zone_at
from marsmap.planning.costmap import CostMap, build_costmap, poi_interest
from marsmap.planning.explain import explain_route
from marsmap.planning.metrics import RouteMetrics, compute_metrics
from marsmap.planning.presets import PRESETS, Weights
from marsmap.planning.terrain_grid import TerrainGrid


class RouteError(Exception):
    """Error de entrada con código estable (la API lo traduce a 422)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RouteResult:
    status: str  # "ok" | "no_route"
    reason: str | None
    weights: Weights
    cells: list[tuple[int, int]] = field(default_factory=list)
    metrics: RouteMetrics | None = None
    explanations: list[str] = field(default_factory=list)
    costmap: CostMap | None = None


def resolve_weights(preset: str | None, weights: Weights | None) -> Weights:
    if preset is not None:
        if preset not in PRESETS:
            raise RouteError("invalid_preset", f"preset desconocido: {preset!r}")
        return PRESETS[preset]
    if weights is None:
        return PRESETS["balanced"]
    return weights


def build_constrained_costmap(
    grid: TerrainGrid,
    weights: Weights,
    zones: list[dict] | None = None,
    habitat: tuple[float, float] | None = None,
    max_radius_m: float | None = None,
    pois: list[dict] | None = None,
) -> CostMap:
    forb = forbidden_mask(grid, zones) if zones else None
    outside = None
    if habitat is not None and max_radius_m is not None:
        outside = radius_mask(grid, habitat[0], habitat[1], max_radius_m)
    interest = poi_interest(grid, pois) if pois and weights.science > 0 else None
    return build_costmap(grid, weights, forb, outside, interest)


# Un sitio en pendiente (p. ej. en el borde del cráter) se alcanza desde el terreno transitable más
# cercano, como al acercarse a pie a un afloramiento. Nunca se ajusta fuera de una zona prohibida.
SNAP_MAX_M = 300.0


def nearest_open(cm: CostMap, rc: tuple[int, int], max_m: float = SNAP_MAX_M):
    """Celda no bloqueada más cercana a `rc` dentro de `max_m`; (celda, distancia_m) o None."""
    r0, c0 = rc
    dx = float(cm.dx_m[r0])
    dy = float(cm.dy_m)
    kr, kc = int(max_m // dy) + 1, int(max_m // dx) + 1
    h, w = cm.shape
    r1, r2, c1, c2 = max(0, r0 - kr), min(h, r0 + kr + 1), max(0, c0 - kc), min(w, c0 + kc + 1)
    rr, cc = np.mgrid[r1:r2, c1:c2]
    d = np.hypot((rr - r0) * dy, (cc - c0) * dx)
    d[cm.blocked[r1:r2, c1:c2] | (d > max_m)] = np.inf
    i = np.unravel_index(int(np.argmin(d)), d.shape)
    if not np.isfinite(d[i]):
        return None
    return (int(rr[i]), int(cc[i])), float(d[i])


def locate(
    grid: TerrainGrid, cm: CostMap, lat: float, lon: float, role: str, zones=None, notes=None
):
    rc = grid.to_rowcol(lat, lon)
    if rc is None:
        raise RouteError("out_of_region", f"el punto de {role} está fuera de la región")
    if cm.blocked[rc]:
        zone = zone_at(grid, zones or [], lat, lon)
        if not zone:
            snap = nearest_open(cm, rc)
            if snap is not None:
                cell, d = snap
                if notes is not None:
                    notes.append(
                        f"El punto de {role} está en pendiente mayor de 15° (o sin dato); la ruta "
                        f"{'sale' if role == 'inicio' else 'llega'} al terreno transitable más cercano, "
                        f"a {d:.0f} m."
                    )
                return cell
        why = (
            f"zona prohibida «{zone}»"
            if zone
            else f"terreno bloqueado (pendiente > 15° o sin dato) sin terreno transitable a menos de {SNAP_MAX_M:.0f} m"
        )
        code = "start_blocked" if role == "inicio" else "goal_blocked"
        raise RouteError(code, f"el punto de {role} cae en {why}")
    return rc


def plan_route(
    grid: TerrainGrid,
    start: tuple[float, float],
    goal: tuple[float, float],
    weights: Weights,
    zones: list[dict] | None = None,
    habitat: tuple[float, float] | None = None,
    max_radius_m: float | None = None,
    pois: list[dict] | None = None,
    costmap: CostMap | None = None,
    timeout_s: float = 5.0,
) -> RouteResult:
    """`start` y `goal` son (lat, lon). Lanza RouteError o SearchTimeout."""
    cm = costmap or build_constrained_costmap(grid, weights, zones, habitat, max_radius_m, pois)
    notes: list[str] = []
    s = locate(grid, cm, start[0], start[1], "inicio", zones, notes)
    g = locate(grid, cm, goal[0], goal[1], "destino", zones, notes)
    res = astar(cm, s, g, timeout_s=timeout_s)
    if res is None:
        return RouteResult(
            "no_route",
            "No existe un camino que cumpla las restricciones: el destino queda aislado "
            "por terreno bloqueado, zonas prohibidas o el radio máximo.",
            weights,
            costmap=cm,
        )
    m = compute_metrics(cm, res.cells)
    return RouteResult(
        "ok", None, weights, res.cells, m, notes + explain_route(cm, res.cells, m), cm
    )
