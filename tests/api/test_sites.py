"""Hábitat en cualquier lugar (016): sitio construido desde un DEM global SINTÉTICO local (sin red)."""

import numpy as np
import pytest
import rasterio
from affine import Affine

from marsmap.terrain.site import site_bbox, site_id
from tests.api.conftest import make_client


@pytest.fixture(scope="module")
def global_dem(tmp_path_factory):
    """Rampa suave alrededor de Gusev (−14.57°, 175.46° E) a ~200 m."""
    path = tmp_path_factory.mktemp("dem") / "global.tif"
    d = 0.003374
    w = h = 600
    t = Affine(d, 0, 174.4, 0, -d, -13.6)
    yy, xx = np.mgrid[0:h, 0:w]
    z = (-1500 + 0.5 * xx + 0.3 * yy).astype("int16")
    with rasterio.open(
        path, "w", driver="GTiff", width=w, height=h, count=1, dtype="int16",
        crs="+proj=longlat +R=3396190 +no_defs", transform=t, nodata=-32768,
    ) as ds:  # fmt: skip
        ds.write(z, 1)
    return str(path)


def test_site_id_is_safe_and_deterministic():
    assert site_id(-14.574, 175.462) == "site_m14d57_p175d46"
    w, s, e, n = site_bbox(-14.57, 175.46)
    assert w < 175.46 < e and s < -14.57 < n


def test_create_site_builds_region_and_routes(data_dir, tmp_path, global_dem):
    import shutil

    shutil.copytree(data_dir / "jezero", tmp_path / "jezero")
    c = make_client(tmp_path)
    c.app.state.site_dem = global_dem
    r = c.post("/api/sites", json={"lat": -14.57, "lon": 175.46})
    assert r.status_code == 200, r.text
    site = r.json()
    assert site["region_id"] == "site_m14d57_p175d46"
    assert site["resolution_m"] > 100
    rid = site["region_id"]
    assert c.get(f"/api/regions/{rid}/layers").status_code == 200
    route = c.post(
        f"/api/regions/{rid}/route",
        json={
            "start": {"lat": -14.57, "lon": 175.46},
            "goal": {"lat": -14.60, "lon": 175.50},
            "preset": "safe",
        },
    )
    assert route.status_code == 200 and route.json()["status"] == "ok"
    # segunda vez: reutiliza sin reconstruir
    assert c.post("/api/sites", json={"lat": -14.57, "lon": 175.46}).json()["region_id"] == rid


def test_point_inside_jezero_returns_jezero(client):
    r = client.post("/api/sites", json={"lat": 18.44, "lon": 77.45})
    assert r.status_code == 200 and r.json()["region_id"] == "jezero"


def test_site_validation_and_missing_dem(tmp_path):
    c = make_client(tmp_path)
    c.app.state.site_dem = str(tmp_path / "no-existe.tif")
    assert c.post("/api/sites", json={"lat": 89, "lon": 0}).status_code == 422
    r = c.post("/api/sites", json={"lat": 0, "lon": 0})
    assert r.status_code == 422 and set(r.json()) == {"error", "code"}


def test_parse_site_id_es_inverso_de_site_id():
    from marsmap.terrain.site import parse_site_id

    for lat, lon in [(-14.57, 175.46), (18.44, 77.45), (0.0, -0.01), (-84.99, -179.99)]:
        assert parse_site_id(site_id(lat, lon)) == (lat, lon)
    for bad in [
        "jezero",
        "site_p91d00_p10d00",
        "site_p10d00_p181d00",
        "site_p1d0_p2d00",
        "../site_p1d00_p2d00",
    ]:
        assert parse_site_id(bad) is None


def test_sitio_se_reconstruye_en_otra_instancia(data_dir, tmp_path, global_dem):
    # Regresión (Vercel): el sitio vive en la memoria y el /tmp de la instancia que lo creó; otra instancia
    # que recibe /regions/<site_id>/... debe reconstruirlo desde el id en vez de responder 404.
    import shutil

    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        shutil.copytree(data_dir / "jezero", d / "jezero")
    ca = make_client(a)
    ca.app.state.site_dem = global_dem
    rid = ca.post("/api/sites", json={"lat": -14.57, "lon": 175.46}).json()["region_id"]

    cb = make_client(b)  # instancia "fría": no conoce el sitio
    cb.app.state.site_dem = global_dem
    r = cb.get(f"/api/regions/{rid}/layers")
    assert r.status_code == 200, r.text
    assert cb.get("/api/regions/site_p10d00_p10d00x/layers").status_code in (404, 422)
