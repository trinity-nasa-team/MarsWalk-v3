"""Suelo fino por THEMIS nocturno (015): máscara alineada a la malla, sin red."""

import numpy as np
from affine import Affine

from marsmap.terrain import build, ortho


def test_fines_mask_marks_cold_night_pixels(monkeypatch, tmp_path):
    def fake_mosaic(layer, bbox, z, cache, fetch=None):
        d = ortho.deg_per_px(z)
        h, w = 64, 64
        arr = np.zeros((h, w, 4), np.uint8)
        arr[..., 3] = 255
        arr[:, : w // 2, :3] = 40  # mitad oeste fría (material fino)
        arr[:, w // 2 :, :3] = 150  # mitad este cálida (roca)
        return arr, (bbox[0], bbox[3] - h * d, bbox[0] + w * d, bbox[3])

    monkeypatch.setattr(ortho, "mosaic", fake_mosaic)
    d = ortho.deg_per_px(9)
    t = Affine(d / 2, 0, 77.0, 0, -d / 2, 18.5)  # malla al doble de resolución que THEMIS
    mask = build.fines_mask(t, (40, 128), tmp_path)  # 128 celdas = 64 px de THEMIS
    assert mask.shape == (40, 128)
    assert mask[:, :60].all()  # oeste: fino
    assert not mask[:, 68:].any()  # este: roca
