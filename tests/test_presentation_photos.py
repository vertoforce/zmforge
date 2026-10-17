"""Post-processing of ``zmforge loadscreen`` (zmforge.render.presentation).

Pure image-in, image-out steps: no Radiant, no blueprint.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from zmforge.render import presentation as ps

BG = (11, 12, 16)


def _render(w=1468, h=790, level=60):
    """A dim, flat, render-like frame with some structure."""
    rng = np.random.default_rng(1)
    a = np.full((h, w, 3), level, dtype=np.float32)
    a[h // 3:, :, :] += 25
    a += rng.normal(0, 6, a.shape)
    a[h // 2 - 40:h // 2 + 40, w // 2 - 40:w // 2 + 40] = 200   # a lamp
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _mean(image, box=None):
    a = np.asarray(image.convert("L"), dtype=np.float32)
    if box:
        x0, y0, x1, y1 = box
        a = a[y0:y1, x0:x1]
    return float(a.mean())


def test_expose_stretches_a_dim_frame_but_caps_the_gain():
    dim = _render(level=30)
    out = ps.expose(dim)
    assert out.size == dim.size
    assert _mean(out) > _mean(dim) * 1.3
    black = Image.new("RGB", (64, 36), (3, 3, 3))
    assert _mean(ps.expose(black)) < 40            # a dark frame stays dark


def test_grade_is_gentle():
    src = _render()
    diff = np.abs(np.asarray(ps.grade(src), np.float32) - np.asarray(src, np.float32))
    assert diff.mean() < 12


def test_haze_veils_the_horizon_not_the_foot():
    src = Image.new("RGB", (200, 200), (20, 20, 20))
    out = ps.haze(src, strength=0.4, horizon=0.45, colour=(180, 180, 180))
    assert _mean(out, (0, 85, 200, 95)) > _mean(out, (0, 190, 200, 200)) + 20
    assert _mean(out, (0, 190, 200, 200)) < 30                     # foot barely touched
    assert _mean(out, (0, 0, 200, 5)) > 40                         # top veiled too


def test_vignette_darkens_corners_only():
    flat = Image.new("RGB", (400, 300), (160, 160, 160))
    out = ps.vignette(flat, strength=0.4)
    assert _mean(out, (190, 140, 210, 160)) > 155
    assert _mean(out, (0, 0, 10, 10)) < 110


@pytest.mark.parametrize("size", [ps.LOADING_SIZE, ps.PREVIEW_SIZE, ps.THUMBNAIL_SIZE])
def test_crop_to_hits_every_target_size(size):
    assert ps.crop_to(_render(), size).size == size


def test_finish_photo_sizes_and_title_band():
    for size in (ps.PREVIEW_SIZE, ps.THUMBNAIL_SIZE):
        out = ps.finish_photo(_render(), size, "My Map at Night", fog=True)
        assert out.size == size and out.mode == "RGB"
    # The title is bright text on a darkened foot.
    card = ps.finish_photo(_render(level=120), ps.PREVIEW_SIZE, "Test Map")
    foot = np.asarray(card.convert("L"))[-60:]
    assert foot.max() > 220


def test_thumbnail_is_a_small_jpeg():
    blob = ps.thumbnail_jpeg(ps.finish_photo(_render(), ps.THUMBNAIL_SIZE, "X"))
    assert blob[:2] == b"\xff\xd8" and len(blob) < 1_000_000


def _blocks(width, height, rects):
    img = Image.new("RGB", (width, height), BG)
    a = np.asarray(img).copy()
    for x0, y0, x1, y1 in rects:
        a[y0:y1, x0:x1] = (120, 120, 120)
    return Image.fromarray(a)


def test_trim_and_collapse_close_up_a_wide_gulf():
    img = _blocks(1000, 200, [(50, 50, 100, 150), (900, 60, 950, 140)])
    trimmed = ps.trim(img, BG)
    assert trimmed.size == (900, 100)
    closed = ps.collapse_gaps(trimmed, BG, max_gap=0.05)
    # Both blocks survive at full size; the 800 px gulf shrinks to the limit.
    assert closed.width == 50 + 50 + int(0.05 * 900)
    assert closed.height == 100
    drawn = ps._drawn(closed, BG)
    assert drawn[:, :50].all(axis=0).any() and drawn[:, -50:].any()


def test_collapse_keeps_small_gaps():
    img = ps.trim(_blocks(300, 100, [(0, 0, 100, 100), (110, 0, 300, 100)]), BG)
    assert ps.collapse_gaps(img, BG, max_gap=0.05).size == img.size


def test_parse_camera_and_presentation_file(tmp_path, monkeypatch):
    view = ps.parse_camera("100 -20 76 8 90.5")
    assert (view.x, view.y, view.z, view.pitch, view.yaw) == (100, -20, 76, 8, 90.5)
    with pytest.raises(ValueError):
        ps.parse_camera("1 2 3")
    monkeypatch.setenv("ZMFORGE_PRESENTATION_ROOT", str(tmp_path))
    assert ps.presentation_file("zm_x", ps.PREVIEW_NAME) is None
    (tmp_path / "zm_x").mkdir()
    (tmp_path / "zm_x" / ps.PREVIEW_NAME).write_bytes(b"x")
    assert ps.presentation_file("zm_x", ps.PREVIEW_NAME) == tmp_path / "zm_x" / ps.PREVIEW_NAME
