"""POIs de todo Marte (016) con respuestas falsas de Trek: sin red."""

import json

from marsmap.data.mars_pois import EZ_URL, NOMEN_URL, parse_nomenclature, parse_zones
from tests.api.conftest import make_client

EZ = {"features": [{"attributes": {"name": "Gusev Crater", "lat": -14.574, "lon": 175.462, "elev": -1.5, "abstract_l": "http://x"}},
                   {"attributes": {"name": "Chryse", "lat": 20, "lon": 320, "elev": -3.7}},
                   {"attributes": {"name": "malo", "lat": None, "lon": 1}}]}  # fmt: skip
NOMEN = {"response": {"docs": [{"title": "Jezero", "productCat2": "Crater, craters", "shape": "POINT (77.58 18.38)"},
                               {"title": "Abalos Colles", "productCat2": "Collis", "shape": "POINT (-71.65 76.83)"},
                               {"title": "sin forma", "shape": ""}]}}  # fmt: skip


def test_parsers_normalize_longitude_and_skip_bad_rows():
    z = parse_zones(EZ)
    assert [p["name"] for p in z] == ["Gusev Crater", "Chryse"]
    assert z[1]["lon"] == -40.0  # 320 E → −40
    n = parse_nomenclature(NOMEN)
    assert [p["name"] for p in n] == ["Abalos Colles", "Jezero"]
    assert n[1] == {"name": "Jezero", "type": "Crater, craters", "lat": 18.38, "lon": 77.58}


def test_endpoint_caches_and_serves(data_dir, tmp_path):
    calls = []

    def fake(url):
        calls.append(url)
        return json.dumps(EZ if url == EZ_URL else NOMEN).encode()

    c = make_client(tmp_path / "processed")
    c.app.state.mars_fetch = fake
    r = c.get("/api/mars/pois")
    assert r.status_code == 200
    body = r.json()
    assert len(body["exploration_zones"]) == 2 and len(body["nomenclature"]) == 2
    assert "EZMars" in body["sources"]["exploration_zones"]
    assert c.get("/api/mars/pois").status_code == 200
    assert sorted(calls) == sorted([EZ_URL, NOMEN_URL])  # una sola vez
    assert (tmp_path / "raw" / "mars_pois.json").is_file()


def test_upstream_failure_is_clean_502(tmp_path):
    import urllib.error

    def boom(url):
        raise urllib.error.URLError("sin red")

    c = make_client(tmp_path / "processed")
    c.app.state.mars_fetch = boom
    r = c.get("/api/mars/pois")
    assert r.status_code == 502 and set(r.json()) == {"error", "code"}
