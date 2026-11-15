"""Endpoints del ortomosaico (014): manifiesto, trozos y validación de ids."""

import shutil

import pytest

from marsmap.terrain import ortho
from tests.api.conftest import make_client
from tests.terrain.test_ortho import fake_fetch


@pytest.fixture(scope="module")
def ortho_client(data_dir, tmp_path_factory):
    d = tmp_path_factory.mktemp("with_ortho")
    shutil.copytree(data_dir / "jezero", d / "jezero")
    ortho.build_ortho(
        "jezero", d, tmp_path_factory.mktemp("raw"), center=(77.4509, 18.4446), hirise_km=2,
        ctx_zoom=8, hirise_zoom=11, viking_zoom=6, overview_px=128, fetch=fake_fetch(),
    )  # fmt: skip
    return make_client(d)


def test_manifest_lists_layers_chunks_and_urls(ortho_client):
    r = ortho_client.get("/api/regions/jezero/ortho")
    assert r.status_code == 200
    body = r.json()
    assert "_files" not in body
    assert body["overview"]["url"] == "/api/regions/jezero/ortho/overview"
    layer = body["layers"][0]
    assert layer["instrument"] == "CTX" and layer["chunks"]
    c = layer["chunks"][0]
    img = ortho_client.get(c["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"


def test_chunk_ids_are_whitelisted(ortho_client):
    assert ortho_client.get("/api/regions/jezero/ortho/ctx_99_99").status_code == 404
    bad = ortho_client.get("/api/regions/jezero/ortho/..%2F..%2Fmetadata")
    assert bad.status_code in (404, 422)
    assert set(ortho_client.get("/api/regions/jezero/ortho/ctx_99_99").json()) == {"error", "code"}


def test_region_without_ortho_returns_clean_404(client):
    r = client.get("/api/regions/jezero/ortho")
    assert r.status_code == 404 and set(r.json()) == {"error", "code"}
