"""Adaptador del planificador v4 (src/marsmap/eva/planner.py) y endpoints /eva/*."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marsmap.api.main import create_app
from marsmap.api.settings import Settings
from marsmap.eva import planner as P

RAIZ = Path(__file__).resolve().parents[2]
TRAMOS = RAIZ / "planificador" / "data" / "processed" / "m20_tramos_ABC.geojson"


def test_conversion_lonlat_xy_es_exacta_y_reversible():
    for lon, lat in [(77.4508, 18.4447), (77.40, 18.47), (77.36, 18.38)]:
        x, y = P.lonlat_to_xy(lon, lat)
        lon2, lat2 = P.xy_to_lonlat(x, y)
        assert abs(lon2 - lon) < 1e-12 and abs(lat2 - lat) < 1e-12
    # el centro de la malla (18.43 N, 77.43 E) es el origen local y cae en la celda (500, 500)
    assert P.lonlat_to_xy(77.43, 18.43) == (0.0, 0.0)
    assert P.lonlat_to_cell(77.43, 18.43) == (500, 500)
    # 1° de latitud = R * pi / 180 m en la esfera de Marte
    assert abs(P.lonlat_to_xy(77.43, 19.43)[1] - 3_396_190 * math.pi / 180) < 1e-6
    lon0, lat0, lon1, lat1 = P.grid_bbox()
    assert lon0 < 77.43 < lon1 and lat0 < 18.43 < lat1


@pytest.fixture(scope="module")
def client():
    data = RAIZ / "data" / "processed"
    return TestClient(create_app(Settings(data_dir=data)), raise_server_exceptions=False)


def _tramo_b():
    f = next(
        x for x in json.loads(TRAMOS.read_text())["features"] if x["properties"]["tramo"] == "B"
    )
    c = f["geometry"]["coordinates"]
    return P.xy_to_lonlat(*c[0]), P.xy_to_lonlat(*c[-1])


def _leg(client, s, g, **kw):
    body = {"start": {"lon": s[0], "lat": s[1]}, "goal": {"lon": g[0], "lat": g[1]}, **kw}
    return client.post("/api/regions/jezero/eva/replan-leg", json=body)


def test_tramo_b_de_seitah_rodea_la_arena(client):
    s, g = _tramo_b()
    r = _leg(client, s, g, agent="rover", preset="fast")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok" and d["planner"] == "v4"
    # la línea recta mide ~2.75 km; con la arena, la ruta rodea Séítah por el norte (> 4 km)
    assert d["distance_m"] > 4000 and d["tortuosity"] > 1.4
    coords = d["geometry"]["coordinates"]
    assert coords[0] == [s[0], s[1]] and coords[-1] == [g[0], g[1]]
    for key in ("profile", "explanations", "segments", "energy_wh", "pct_risk_cells", "est_time_h"):
        assert key in d


def test_astronauta_trae_oxigeno(client):
    s, g = _tramo_b()
    d = _leg(client, s, g, agent="astronaut", preset="fast").json()
    assert d["o2_l"] > 0 and d["energy_wh"] > 0
    assert d["thresholds_deg"] == {"risk": 10.0, "blocked": 20.0}


def test_peligro_del_robot_cambia_la_ruta(client):
    s, g = _tramo_b()
    d0 = _leg(client, s, g, agent="astronaut", preset="fast").json()
    mid = d0["geometry"]["coordinates"][len(d0["geometry"]["coordinates"]) // 2]
    d1 = _leg(
        client,
        s,
        g,
        agent="astronaut",
        preset="fast",
        obstacles=[{"lon": mid[0], "lat": mid[1], "radius_m": 300}],
    ).json()
    assert d1["status"] == "ok" and d1["distance_m"] > d0["distance_m"]


def test_fuera_de_la_malla_es_422(client):
    r = _leg(client, (77.0, 18.0), (77.45, 18.44))
    assert r.status_code == 422 and r.json()["code"] == "out_of_planner_grid"


def test_perfil_de_regreso_y_punto_de_no_retorno(client):
    body = {
        "habitat": {"lon": 77.4508, "lat": 18.4447},
        "waypoints": [{"lon": 77.4420, "lat": 18.4400}],
    }
    holgado = client.post(
        "/api/regions/jezero/eva/return-profile", json={**body, "budget_wh": 1408}
    ).json()
    assert holgado["point_of_no_return_idx"] is None and min(holgado["margin_wh"]) > 0
    justo = client.post(
        "/api/regions/jezero/eva/return-profile", json={**body, "budget_wh": 250}
    ).json()
    assert justo["point_of_no_return_idx"] is not None
    con_kit = client.post(
        "/api/regions/jezero/eva/return-profile", json={**body, "budget_wh": 1408, "kit_kg": 30}
    ).json()
    assert con_kit["spent_wh"][-1] > holgado["spent_wh"][-1]  # más carga, más energía


def test_capa_de_arena(client):
    meta = client.get("/api/regions/jezero/eva/sand-layer").json()
    assert (
        meta["layer_id"] == "sand" and len(meta["bbox"]) == 4 and meta["source"] == "HIRISE_TEXTURE"
    )
    png = client.get(meta["image_url"])
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_peligro_fuera_de_la_malla_no_rompe(client):
    """Revisión de código: un peligro al oeste/norte de la malla (más lejos que su radio) daba 500."""
    s, g = _tramo_b()
    for lon, lat in [(77.20, 18.43), (77.43, 18.70), (77.65, 18.20)]:
        r = _leg(
            client, s, g, agent="astronaut", obstacles=[{"lon": lon, "lat": lat, "radius_m": 100}]
        )
        assert r.status_code == 200 and r.json()["status"] == "ok"


def test_tramo_demasiado_largo_es_422(client):
    r = _leg(client, (77.26, 18.27), (77.60, 18.59))
    assert r.status_code == 422 and r.json()["code"] == "leg_too_long"


def test_regreso_sin_pnr_falso_y_con_cache(client):
    body = {
        "habitat": {"lon": 77.4508, "lat": 18.4447},
        "waypoints": [{"lon": 77.4024, "lat": 18.4486}],
        "budget_wh": 3000,
    }
    r1 = client.post("/api/regions/jezero/eva/return-profile", json=body).json()
    assert all(v is not None for v in r1["return_wh"])  # el radio cubre toda la EVA: sin NaN
    assert r1["point_of_no_return_idx"] is None
    r2 = client.post("/api/regions/jezero/eva/return-profile", json=body).json()
    assert r2["spent_wh"] == r1["spent_wh"]


def test_finite_convierte_nan_en_none_para_json():
    # Regresión: NaN (celda sin regreso posible) llegaba a la respuesta y Starlette respondía 500.
    out = P._finite([1.5, float("nan"), float("inf"), -2.0])
    assert out == [1.5, None, None, -2.0]
    json.dumps(out, allow_nan=False)
