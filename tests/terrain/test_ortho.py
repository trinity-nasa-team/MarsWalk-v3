"""Ortomosaico (014) con tiles sintéticos deterministas: sin red."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from marsmap.terrain import ortho
from marsmap.terrain.ortho import (
    CTX,
    TILE_PX,
    colorize,
    crop,
    deg_per_px,
    mosaic,
    tile_range,
    tiles_bbox,
    write_chunks,
)


def _png(rgba) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (TILE_PX, TILE_PX), rgba).save(buf, "PNG")
    return buf.getvalue()


def fake_fetch(missing=frozenset()):
    calls = []

    def fetch(url: str):
        calls.append(url)
        z, row, col = (int(p) for p in url.rsplit(".", 1)[0].split("/")[-3:])
        if (row, col) in missing:
            return None
        return _png((row % 256, col % 256, z * 10, 255))

    fetch.calls = calls
    return fetch


def test_tile_range_covers_bbox_in_trek_geographic_matrix():
    cols, rows = tile_range((77.0, 18.0, 78.0, 18.9), 12)
    size = 180 / 2**12
    assert cols.start == int((77 + 180) // size) and rows.start == int((90 - 18.9) // size)
    w, s, e, n = tiles_bbox(cols, rows, 12)
    assert w <= 77 and s <= 18 and e >= 78 and n >= 18.9
    assert e - w < 1 + 2 * size and n - s < 0.9 + 2 * size


def test_mosaic_places_each_tile_in_its_row_col_and_caches(tmp_path):
    fetch = fake_fetch(missing={(1628, 5859)})
    arr, tb = mosaic(CTX, (77.40, 18.42, 77.50, 18.47), 12, tmp_path, fetch)
    cols, rows = tile_range((77.40, 18.42, 77.50, 18.47), 12)
    assert arr.shape == (len(rows) * TILE_PX, len(cols) * TILE_PX, 4)
    for i, row in enumerate(rows):
        for j, col in enumerate(cols):
            px = arr[i * TILE_PX + 5, j * TILE_PX + 5]
            if (row, col) == (1628, 5859):
                assert px[3] == 0  # 404 → transparente
            else:
                assert tuple(px) == (row % 256, col % 256, 120, 255)
    n = len(fetch.calls)
    mosaic(CTX, (77.40, 18.42, 77.50, 18.47), 12, tmp_path, fetch)
    assert len(fetch.calls) == n + 1  # solo reintenta el que faltaba; el resto sale de caché


def test_crop_is_pixel_aligned_and_reports_exact_bbox():
    z = 12
    d = deg_per_px(z)
    arr = np.zeros((512, 512, 4), np.uint8)
    tb = (77.0, 18.0, 77.0 + 512 * d, 18.0 + 512 * d)
    out, b = crop(arr, tb, (77.0 + 10.4 * d, 18.0 + 20 * d, 77.0 + 100 * d, 18.0 + 300 * d), z)
    assert out.shape[1] == round((b[2] - b[0]) / d) and out.shape[0] == round((b[3] - b[1]) / d)
    assert b[0] <= 77.0 + 10.4 * d and b[2] >= 77.0 + 100 * d


def test_colorize_keeps_detail_luminance_and_takes_color():
    gray = np.zeros((64, 64, 4), np.uint8)
    gray[..., :3] = np.linspace(40, 220, 64, dtype=np.uint8)[None, :, None]
    gray[..., 3] = 255
    color = np.zeros((4, 4, 4), np.uint8)
    color[...] = (190, 110, 70, 255)  # óxido
    out = colorize(gray, (0, 0, 1, 1), color, (-1, -1, 2, 2))
    assert out[..., 0].mean() > out[..., 2].mean() + 20  # rojizo
    lum = out[..., :3].astype(float) @ [0.299, 0.587, 0.114]
    assert np.corrcoef(lum[0], gray[0, :, 0])[0, 1] > 0.99  # el detalle sigue siendo el de CTX


def test_write_chunks_limits_size_skips_empty_and_tiles_bbox(tmp_path, monkeypatch):
    monkeypatch.setattr(ortho, "CHUNK_PX", 100)
    z = 12
    d = deg_per_px(z)
    arr = np.full((250, 180, 4), 255, np.uint8)
    arr[200:, :, 3] = 0  # última fila de trozos sin datos
    chunks = write_chunks(arr, (77.0, 18.0, 77.0 + 180 * d, 18.0 + 250 * d), tmp_path, "ctx", z)
    assert [c["id"] for c in chunks] == ["ctx_0_0", "ctx_0_1", "ctx_1_0", "ctx_1_1"]
    for c in chunks:
        im = Image.open(tmp_path / c["file"])
        assert im.size[0] <= 100 and im.size[1] <= 100 and im.format == "WEBP"
    assert chunks[1]["bbox"][0] == pytest.approx(chunks[0]["bbox"][2])


def test_build_ortho_writes_manifest_with_metadata(tmp_path):
    m = ortho.build_ortho(
        "jezero", tmp_path / "processed", tmp_path / "raw", center=(77.4509, 18.4446),
        hirise_km=2, ctx_zoom=8, hirise_zoom=11, viking_zoom=6, overview_px=256, fetch=fake_fetch(),
    )  # fmt: skip
    ids = [layer["layer_id"] for layer in m["layers"]]
    assert ids == ["ortho_ctx", "ortho_hirise"]
    ctx = m["layers"][0]
    w, s, e, n = ctx["bbox"]
    assert w <= 77.0 and s <= 18.0 and e >= 78.0 and n >= 18.9 and w > 76.9
    for key in (
        "source_dataset",
        "instrument",
        "resolution_m",
        "product_date",
        "limitations",
        "color",
    ):
        assert ctx[key]
    assert "aproximado" in ctx["color"].lower()
    out = tmp_path / "processed" / "jezero" / "ortho"
    assert (out / "ortho.json").is_file() and (out / "overview.webp").is_file()
    assert (tmp_path / "raw" / "jezero" / "ortho_ctx_z8.tif").is_file()


def test_http_fetch_rejects_hosts_outside_whitelist():
    with pytest.raises(ValueError):
        ortho.http_fetch("https://example.com/tile.png")
