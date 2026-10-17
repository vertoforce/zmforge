"""The full-screen loading image for ``zm_corn_maze``, "Harvest Moon", drawn here.

A corn field at night under a huge orange harvest moon: a night-blue sky
fading to the horizon, the moon with a scarecrow standing against it, rows of
corn in silhouette, a pumpkin patch of glowing jack-o'-lanterns in front, and
the hayride trailer crossing the field.  Everything is drawn from code with
the fonts :mod:`zmforge.texture.paint` names; nothing is sourced, so there is
no licence question.

The layout rules every loading screen here keeps: 1920 x 1080 only,
the outer 30 px carry no ink, and the bottom band is kept quiet because the
game draws its own progress furniture there.  Every random draw is seeded, so
the same code gives the same bytes.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..images import encode_png
from . import paint

__all__ = ["SIZE", "TITLE", "GAG", "render_loadscreen", "loadscreen_png"]

SIZE: tuple[int, int] = (1920, 1080)
TITLE = "HARVEST MOON"
GAG = "The hayride leaves every few minutes. The driver never sleeps. There is no driver."

_SKY_TOP = np.array((8, 10, 30), dtype=np.float32)
_SKY_LOW = np.array((52, 30, 60), dtype=np.float32)
_MOON = (246, 170, 70)
_CORN = (18, 20, 14)
_CORN_LIT = (60, 48, 22)
_PUMPKIN = (230, 110, 20)
_GLOW = (255, 200, 90)
_CREAM = (246, 226, 190)
_HORIZON = 700


def _sky(seed: int) -> Image.Image:
    w, h = SIZE
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None] ** 1.4
    pixels = _SKY_TOP * (1 - t) + _SKY_LOW * t
    pixels = np.repeat(pixels, w, axis=1)
    rng = np.random.default_rng(seed)
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    for _ in range(260):  # stars, above the moon's glow
        x, y = int(rng.integers(40, w - 40)), int(rng.integers(40, _HORIZON - 200))
        v = int(rng.integers(120, 255))
        draw.point((x, y), fill=(v, v, min(255, v + 20)))
    return image


def _moon(image: Image.Image) -> None:
    cx, cy, r = 1380, 400, 250
    glow = Image.new("RGB", SIZE, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((cx - r - 120, cy - r - 120, cx + r + 120, cy + r + 120), fill=(120, 60, 20))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    image.paste(Image.blend(image, Image.fromarray(np.clip(
        np.asarray(image, dtype=np.int16) + np.asarray(glow, dtype=np.int16), 0, 255).astype(np.uint8)),
        1.0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_MOON)
    for dx, dy, rr in ((-80, -60, 40), (60, 40, 55), (-20, 110, 30), (110, -90, 25)):
        draw.ellipse((cx + dx - rr, cy + dy - rr, cx + dx + rr, cy + dy + rr), fill=(226, 148, 58))
    # The scarecrow against the moon: post, arms, a pumpkin head, a hat.
    sx, base = cx - 60, _HORIZON - 40
    draw.rectangle((sx - 7, cy - 60, sx + 7, base), fill=_CORN)
    draw.rectangle((sx - 130, cy - 10, sx + 130, cy + 6), fill=_CORN)
    draw.polygon([(sx - 60, cy - 20), (sx + 60, cy - 20), (sx + 40, cy + 110), (sx - 40, cy + 110)], fill=_CORN)
    draw.ellipse((sx - 38, cy - 120, sx + 38, cy - 50), fill=_CORN)
    draw.polygon([(sx - 70, cy - 105), (sx + 70, cy - 105), (sx + 20, cy - 190), (sx - 25, cy - 185)], fill=_CORN)
    for hx in (-14, 14):  # the eyes, lit from inside
        draw.polygon([(sx + hx - 8, cy - 80), (sx + hx + 8, cy - 80), (sx + hx, cy - 94)], fill=_GLOW)


def _corn(image: Image.Image, seed: int) -> None:
    """Rows of corn stalks in silhouette, the far rows lighter."""
    rng = np.random.default_rng(seed + 1)
    draw = ImageDraw.Draw(image)
    w = SIZE[0]
    for row, (y0, height, colour) in enumerate(((_HORIZON, 90, (30, 26, 30)),
                                               (_HORIZON + 40, 150, (22, 22, 18)),
                                               (_HORIZON + 90, 220, _CORN))):
        x = 34
        while x < w - 34:
            h = height * float(rng.uniform(0.7, 1.1))
            lean = float(rng.uniform(-14, 14))
            draw.line((x, y0 + 120, x + lean, y0 - h), fill=colour, width=5)
            for k in range(3):  # leaves
                ly = y0 - h * (0.3 + 0.2 * k)
                side = 1 if (k + row) % 2 else -1
                draw.line((x + lean * 0.5, ly, x + lean * 0.5 + side * 34, ly - 22), fill=colour, width=4)
            x += int(rng.integers(14, 26))
    draw.rectangle((0, _HORIZON + 120, w, SIZE[1]), fill=(12, 10, 8))


def _pumpkins(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    for i, (x, y, r) in enumerate(((260, 900, 62), (430, 950, 44), (1560, 930, 70), (1730, 890, 40),
                                   (1130, 960, 36))):
        draw.ellipse((x - r * 1.25, y - r, x + r * 1.25, y + r), fill=_PUMPKIN)
        draw.rectangle((x - 5, y - r - 16, x + 5, y - r + 4), fill=(40, 60, 20))
        e = r * 0.3
        for side in (-1, 1):
            draw.polygon([(x + side * r * 0.45 - e, y - e * 0.3), (x + side * r * 0.45 + e, y - e * 0.3),
                          (x + side * r * 0.45, y - e * 1.5)], fill=_GLOW)
        draw.chord((x - r * 0.7, y - r * 0.2, x + r * 0.7, y + r * 0.7), 10, 170, fill=_GLOW)


def _hayride(image: Image.Image) -> None:
    """The trailer and its tractor crossing the field, in silhouette."""
    draw = ImageDraw.Draw(image)
    y = 800
    draw.rectangle((620, y - 50, 980, y), fill=(28, 20, 12))            # the bed
    for x in (660, 700, 900, 940):
        draw.ellipse((x - 26, y - 20, x + 26, y + 32), fill=(10, 8, 6))
    for x in (650, 720, 790, 860):                                     # hay and riders
        draw.rounded_rectangle((x, y - 90, x + 60, y - 50), 8, fill=(92, 72, 30))
    draw.line((980, y - 25, 1030, y - 25), fill=(10, 8, 6), width=6)    # the tow bar
    draw.rectangle((1030, y - 90, 1140, y), fill=(20, 16, 10))          # the "tractor"
    draw.ellipse((1100, y - 20, 1150, y + 30), fill=(10, 8, 6))
    draw.ellipse((1040, y - 10, 1080, y + 30), fill=(10, 8, 6))
    draw.ellipse((600, y - 110, 630, y - 80), fill=_GLOW)               # the lantern


def _centred(draw: ImageDraw.ImageDraw, text: str, y: int, face, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    draw.text(((SIZE[0] - (right - left)) // 2 - left, y - top), text, font=face, fill=fill)


def render_loadscreen(seed: int = 31) -> Image.Image:
    """The loading screen as an RGB image of :data:`SIZE`."""
    image = _sky(seed)
    _moon(image)
    _corn(image, seed)
    _hayride(image)
    _pumpkins(image)
    draw = ImageDraw.Draw(image)
    title = paint.fit_font("sign", TITLE, 1300, ceiling=170)
    left, top, right, bottom = draw.textbbox((0, 0), TITLE, font=title)
    y = 90
    for dx, dy, fill in ((6, 7, (10, 6, 4)), (0, 0, _PUMPKIN)):
        draw.text(((SIZE[0] - (right - left)) // 2 - left + dx, y - top + dy), TITLE, font=title, fill=fill)
    _centred(draw, "A CORN MAZE ON HALLOWEEN NIGHT", 290, paint.font("serif_italic", 44), _CREAM)
    _centred(draw, GAG, 1000 - 60, paint.font("typewriter_light", 26), (200, 180, 150))
    return paint.vignette(image, 0.30)


def loadscreen_png() -> bytes:
    """The loading screen as PNG bytes, for ``commit(loading_image=...)``."""
    image = render_loadscreen()
    if image.size != SIZE:
        raise ValueError(f"the loading screen must be {SIZE}, drew {image.size}")
    return encode_png(SIZE[0], SIZE[1], image.convert("RGB").tobytes())
