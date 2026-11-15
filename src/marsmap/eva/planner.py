"""Adaptador del planificador de Josué (planificador/, Marswalk v4) para la API web.

Frontera de coordenadas (contrato 02b): TODO lo que entra y sale de aquí va en lon/lat planetocéntricas
(esfera de Marte, R = 3 396 190 m). El planificador trabaja por dentro en su malla local de 20 m
(eqc lat_ts = lat_0 = 18.43, lon_0 = 77.43, fila 0 = norte). La proyección es equirectangular, así que la
conversión es exacta y sin dependencias (ver lonlat_to_xy / xy_to_lonlat y su prueba).

Qué expone:
  - replan_leg(): una ruta A -> B (~0.1 s) con los costos v4 (arena por textura HiRISE, pendiente fina) y los
    peligros del robot como celdas verificadas. Responde con el formato RouteOut que ya consume el frontend,
    más campos nuevos: procedencia por tramo, metros sobre arena, energía y O2 del astronauta.
  - return_profile(): energía gastada, energía para volver y punto de no retorno a lo largo de la EVA.
  - sand_layer(): la capa de arena (y su cobertura) como imagen sobre un bbox lon/lat.
"""

from __future__ import annotations

import io
import math
import sys
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[3]
PLANIFICADOR = RAIZ / "planificador"

R_MARS = 3_396_190.0
LAT0, LON0 = 18.43, 77.43
_K = math.cos(math.radians(LAT0))
RES = 20.0
HALF = 10_000.0  # la malla del planificador va de -10 km a +10 km en x e y (1000 x 1000 celdas)

AGENTS = ("astronaut", "rover")
MAX_LEG_M = 15_000.0  # tope por tramo: acota memoria y tiempo por petición en serverless
SOURCE_NAMES = {0: "ORBIT", 1: "HIRISE_TEXTURE", 2: "AI", 3: "SCOUT_VERIFIED"}


class PlannerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ------------------------------------------------------------------ coordenadas (exactas)
def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    return R_MARS * _K * math.radians(lon - LON0), R_MARS * math.radians(lat - LAT0)


def xy_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return LON0 + math.degrees(x / (R_MARS * _K)), LAT0 + math.degrees(y / R_MARS)


def lonlat_to_cell(lon: float, lat: float) -> tuple[int, int]:
    x, y = lonlat_to_xy(lon, lat)
    return int(math.floor((HALF - y) / RES)), int(math.floor((x + HALF) / RES))


def cell_to_lonlat(row: int, col: int) -> tuple[float, float]:
    return xy_to_lonlat(-HALF + RES * (col + 0.5), HALF - RES * (row + 0.5))


def grid_bbox() -> list[float]:
    """[lon_min, lat_min, lon_max, lat_max] de la malla del planificador (rectángulo exacto en lon/lat)."""
    lon0, lat0 = xy_to_lonlat(-HALF, -HALF)
    lon1, lat1 = xy_to_lonlat(HALF, HALF)
    return [lon0, lat0, lon1, lat1]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * R_MARS * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ estado (se carga una vez por instancia)
class _State:
    def __init__(self):
        if str(PLANIFICADOR) not in sys.path:
            sys.path.insert(0, str(PLANIFICADOR))
        import mision_v3 as v3  # noqa: PLC0415  (código del planificador, vendorizado con git subtree)
        from proto1_capas import cargar  # noqa: PLC0415

        t0 = time.perf_counter()
        self.v3 = v3
        self.layers = cargar()
        self.agents = {"astronaut": v3.ASTRONAUTA, "rover": v3.ROVER}
        self.maps = {
            name: v3.Mapa.desde_capas(self.layers, p=v3.parametros(ag))
            for name, ag in self.agents.items()
        }
        self.load_s = round(time.perf_counter() - t0, 2)


_state: _State | None = None
_state_lock = threading.Lock()


def state() -> _State:
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = _State()
    return _state


# ------------------------------------------------------------------ peligros del robot -> celdas verificadas
def _with_hazards(mapa, hazards):
    """Copia del mapa con los peligros (círculos lon/lat) como arena VERIFICADA por el robot (origen 3)."""
    if not hazards:
        return mapa
    v3 = state().v3
    n_rows, n_cols = mapa.forma
    costo, arena, origen, duna = (
        mapa.costo.copy(),
        mapa.arena.copy(),
        mapa.origen.copy(),
        mapa.duna.copy(),
    )
    w = (mapa.params or v3.P)["w_arena"]
    for h in hazards:
        r0, c0 = lonlat_to_cell(h["lon"], h["lat"])
        k = int(math.ceil(h["radius_m"] / RES))
        r_lo, r_hi = max(r0 - k, 0), min(max(r0 + k + 1, 0), n_rows)
        c_lo, c_hi = max(c0 - k, 0), min(max(c0 + k + 1, 0), n_cols)
        if r_hi <= r_lo or c_hi <= c_lo:  # el peligro no toca la malla del planificador
            continue
        rr, cc = np.ogrid[r_lo:r_hi, c_lo:c_hi]
        inside = RES * np.hypot(rr - r0, cc - c0) <= h["radius_m"]
        sl = (slice(r_lo, r_hi), slice(c_lo, c_hi))
        nueva = inside & ~arena[sl]
        costo[sl] = np.where(nueva & np.isfinite(costo[sl]), costo[sl] + w, costo[sl])
        arena[sl] |= inside
        duna[sl] |= inside
        origen[sl] = np.where(inside, 3, origen[sl])
    return v3.Mapa(
        costo,
        mapa.dem,
        mapa.pend,
        mapa.riesgo,
        duna,
        mapa.bloqueado,
        arena,
        mapa.incierto,
        origen,
        mapa.params,
    )


def _check_inside(name: str, lon: float, lat: float) -> tuple[int, int]:
    r, c = lonlat_to_cell(lon, lat)
    n_rows, n_cols = state().maps["astronaut"].forma
    if not (0 <= r < n_rows and 0 <= c < n_cols):
        raise PlannerError(
            "out_of_planner_grid", f"{name} ({lon:.4f}, {lat:.4f}) is outside the planner grid"
        )
    return r, c


def _segments(path, origen, arena):
    """Tramos consecutivos de la ruta con la misma procedencia (para colorear ORBIT / HIRISE / AI / SCOUT ✓)."""
    src = [int(origen[r, c]) if arena[r, c] else 0 for r, c in path]
    segs, start = [], 0
    for i in range(1, len(src) + 1):
        if i == len(src) or src[i] != src[start]:
            segs.append(
                {"from": start, "to": max(i - 1, start), "source": SOURCE_NAMES[src[start]]}
            )
            start = i
    return segs


# ------------------------------------------------------------------ API pública
def replan_leg(
    start: tuple[float, float],
    goal: tuple[float, float],
    agent: str = "astronaut",
    preset: str = "safe",
    hazards: list[dict] | None = None,
) -> dict:
    """Ruta A -> B con el planificador v4. start/goal = (lon, lat). Devuelve un dict compatible con RouteOut."""
    if agent not in AGENTS:
        raise PlannerError("invalid_agent", f"agent must be one of {AGENTS}")
    t0 = time.perf_counter()
    st = state()
    v3 = st.v3
    a = _check_inside("start", *start)
    b = _check_inside("goal", *goal)
    if haversine_m(start, goal) > MAX_LEG_M:
        raise PlannerError(
            "leg_too_long", f"Legs are limited to {MAX_LEG_M / 1000:g} km straight-line."
        )
    mapa = _with_hazards(st.maps[agent], hazards or [])
    perfil = "seguro" if preset == "safe" else "normal"
    r = v3.replanear_tramo(mapa, a, b, st.agents[agent], perfil)
    if r is None:
        pmax = (mapa.params or v3.P)["pend_max"]
        return {
            "status": "no_route",
            "reason": f"No safe path: blocked by slopes of {pmax:g}° or more.",
            "compute_ms": int((time.perf_counter() - t0) * 1000),
            "planner": "v4",
        }
    path = r["camino"]
    rows, cols = np.array([p[0] for p in path]), np.array([p[1] for p in path])
    coords = [list(cell_to_lonlat(int(rw), int(cl))) for rw, cl in path]
    coords[0], coords[-1] = [start[0], start[1]], [goal[0], goal[1]]
    z = mapa.dem[rows, cols]
    dz = np.diff(z)
    step = RES * np.hypot(np.diff(rows), np.diff(cols))
    d = np.r_[0.0, np.cumsum(np.hypot(step, dz))]
    risk = mapa.riesgo[rows, cols]
    sand = mapa.arena[rows, cols] if mapa.arena is not None else np.zeros(len(path), bool)
    sand_m = float(np.hypot(step, dz)[sand[1:]].sum())
    straight = haversine_m(start, goal)
    agent_obj = st.agents[agent]
    out = {
        "status": "ok",
        "reason": None,
        "geometry": {"type": "LineString", "coordinates": coords},
        "distance_m": float(r["km"] * 1000),
        "straight_line_m": straight,
        "tortuosity": float(r["km"] * 1000 / straight) if straight > 0 else 1.0,
        "max_slope_deg": float(r["pend_max"]),
        "mean_slope_deg": float(np.mean(mapa.pend[rows, cols])),
        "elevation_gain_m": float(dz[dz > 0].sum()),
        "elevation_loss_m": float(-dz[dz < 0].sum()),
        "pct_risk_cells": float(100 * risk.mean()),
        "est_time_h": float(r["h"]),
        "profile": [
            {"d_m": float(di), "elev_m": float(zi), "risk": bool(ri)}
            for di, zi, ri in zip(d[::2], z[::2], risk[::2], strict=False)
        ],
        "explanations": _explain(r, sand_m, mapa, agent),
        "compute_ms": int((time.perf_counter() - t0) * 1000),
        # --- nuevo en v4
        "planner": "v4",
        "agent": agent,
        "sand_m": sand_m,
        "segments": _segments(path, mapa.origen, mapa.arena),
        "energy_wh": float(r["wh"]),
        "thresholds_deg": {
            "risk": (mapa.params or v3.P)["pend_riesgo"],
            "blocked": (mapa.params or v3.P)["pend_max"],
        },
    }
    if getattr(agent_obj, "metabolico", False):
        out["o2_l"] = float(r["wh"] * v3.O2_L_POR_WH)
    return out


def _explain(r: dict, sand_m: float, mapa, agent: str) -> list[str]:
    th = mapa.params or state().v3.P
    msgs = [
        f"{agent.capitalize()} thresholds: risk from {th['pend_riesgo']:g}°, blocked from {th['pend_max']:g}° "
        "(fine slope = max of CTX 20 m and HiRISE 5 m p95)."
    ]
    if sand_m > 0:
        msgs.append(f"{sand_m:.0f} m over sand (penalized): no sand-free alternative was cheaper.")
    else:
        msgs.append("Avoids all mapped sand (HiRISE texture layer and scout-verified hazards).")
    if r["pend_max"] >= th["pend_riesgo"]:
        msgs.append(f"Steepest cell {r['pend_max']:.1f}° (risk zone): walk slowly.")
    return msgs


def _finite(xs: list[float]) -> list[float | None]:
    """NaN/inf -> None: celdas sin regreso posible (bloqueadas o fuera del radio). JSON no admite NaN (daba 500)."""
    return [x if math.isfinite(x) else None for x in xs]


def return_profile(
    habitat: tuple[float, float],
    waypoints: list[tuple[float, float]],
    budget_wh: float,
    kit_kg: float | None = None,
    reserve: float = 0.10,
) -> dict:
    """EVA hábitat -> waypoints -> hábitat para el astronauta: energía gastada, energía para volver desde cada
    punto, margen y punto de no retorno (índice en la geometría). Paradas: estudio de horas_por_objetivo."""
    st = state()
    v3 = st.v3
    agent = st.agents["astronaut"]
    if kit_kg is not None:
        from dataclasses import replace  # noqa: PLC0415

        agent = replace(agent, kit_kg=float(kit_kg))
    mapa = st.maps["astronaut"]
    base = _check_inside("habitat", *habitat)
    pts = (
        [base] + [_check_inside(f"waypoint {i + 1}", *w) for i, w in enumerate(waypoints)] + [base]
    )
    # Antes de los Dijkstra: rechazar barato una EVA demasiado lejana (antes se calculaban todos los tramos).
    radio = max(haversine_m(habitat, w) for w in waypoints) + 1500.0
    if radio > MAX_LEG_M:
        raise PlannerError(
            "eva_too_far", f"Waypoints must be within {MAX_LEG_M / 1000 - 1.5:g} km of the habitat."
        )
    path, stops = [], []
    for k, (a, b) in enumerate(zip(pts[:-1], pts[1:], strict=False)):
        r = v3.replanear_tramo(mapa, a, b, agent, "normal")
        if r is None:
            raise PlannerError("no_route", f"No safe path for leg {k + 1}.")
        path += r["camino"] if not path else r["camino"][1:]
        if k < len(waypoints):
            stops.append(len(path) - 1)
    reg = _return_cost(base, agent, radio)
    prof = v3.perfil_regreso(mapa, path, reg, agent, budget_wh, reserve, stops)
    coords = [list(cell_to_lonlat(r, c)) for r, c in path]
    return {
        "geometry": {"type": "LineString", "coordinates": coords},
        "stops_idx": stops,
        "spent_wh": _finite(prof["gastado_wh"]),
        "return_wh": _finite(prof["regreso_wh"]),
        "margin_wh": _finite(prof["margen_wh"]),
        "o2_spent_l": _finite(prof["o2_gastado_L"]),
        "point_of_no_return_idx": prof["punto_no_retorno"],
        "budget_wh": budget_wh,
        "reserve": reserve,
        "kit_kg": agent.kit_kg,
        "model": "Pandolf + Santee (Kim et al. 2024, NASA JSC) scaled to 0.38 g; suit 104 kg",
    }


_return_cache: OrderedDict = OrderedDict()
_return_lock = threading.Lock()


def _return_cost(base: tuple[int, int], agent, radio_m: float) -> dict:
    """costo_regreso cacheado por (celda base, kit) con un radio redondeado a 1 km (lo más caro de return_profile)."""
    radio = 1000.0 * math.ceil(radio_m / 1000.0)
    key = (base, round(agent.kit_kg, 1), radio)
    with _return_lock:
        if key in _return_cache:
            _return_cache.move_to_end(key)
            return _return_cache[key]
    reg = state().v3.costo_regreso(state().maps["astronaut"], base, agent, radio_m=radio)
    with _return_lock:
        _return_cache[key] = reg
        while len(_return_cache) > 4:
            _return_cache.popitem(last=False)
    return reg


@lru_cache(maxsize=1)
def sand_layer_png() -> tuple[bytes, float]:
    """PNG RGBA de la capa de arena (naranja) y de la zona sin evaluar (gris tenue) en la malla del planificador."""
    from PIL import Image  # noqa: PLC0415

    L = state().layers
    arena = L.get("arena_textura")
    cov = L.get("arena_cobertura")
    img = np.zeros((1000, 1000, 4), np.uint8)
    if arena is not None:
        img[arena > 0] = (255, 153, 0, 150)
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue(), (float(cov.mean()) if cov is not None else 0.0)


def sand_layer_meta() -> dict:
    _, coverage = sand_layer_png()
    return {
        "layer_id": "sand",
        "name": "Sand (HiRISE texture)",
        "bbox": grid_bbox(),
        "image_url": "/api/regions/jezero/eva/sand-layer.png",
        "source": "HIRISE_TEXTURE",
        "source_dataset": "HiRISE ESP_045994 orthoimage texture (band-pass 4–12 m + ridge anisotropy)",
        "coverage_fraction": coverage,
        "limitations": "Texture flags ripple fields but also some rough bedrock; outside the HiRISE frame "
        "sand is not evaluated. Replaced by the AI segmentation layer when available.",
    }
