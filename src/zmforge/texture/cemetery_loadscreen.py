"""The full-screen loading image for ``zm_cemetery``, "Cemetery Quest", drawn here.

Night over Hollow Rest Cemetery: a moon behind thin cloud, three bands of
rolling hills going grey with distance, fog lying in the hollows between
them, a row of headstones and crosses on the nearest rise, a dead tree, a
mausoleum on the far hill, and the iron gate -- with its sign -- in front.
Everything is drawn from code with the fonts :mod:`zmforge.texture.paint`
names; nothing is sourced, so there is no licence question.

The layout rules every loading screen here keeps: 1920 x 1080 only,
the outer 30 px carry no ink, the bottom band is kept quiet for the game's
own progress furniture, and grain is low-frequency (the linker packs this
image uncompressed).  Every random draw is seeded.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..images import encode_png
from . import paint

__all__ = ["SIZE", "TITLE", "GAG", "render_loadscreen", "loadscreen_png"]

SIZE: tuple[int, int] = (1920, 1080)
TITLE = "CEMETERY QUEST"
GAG = "Gates close at midnight. It is 11:59."

_SKY_TOP = np.array((8, 10, 22), dtype=np.float32)
_SKY_LOW = np.array((34, 40, 62), dtype=np.float32)
_MOON = (226, 230, 214)
_STONE = (58, 62, 70)
_STONE_EDGE = (98, 104, 112)
_TITLE = (214, 222, 206)
_GAG = (170, 180, 170)


def _sky(seed: int) -> Image.Image:
    width, height = SIZE
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    pixels = _SKY_TOP * (1.0 - t) + _SKY_LOW * t
    pixels = np.repeat(pixels, width, axis=1)
    # Moon glow, upper right.
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    mx, my = 1580.0, 400.0
    glow = np.clip(1.0 - np.hypot(xx - mx, yy - my) / 700.0, 0.0, 1.0) ** 2.2
    pixels += glow[:, :, None] * np.array((60, 62, 58), dtype=np.float32)
    # Stars: a few hundred, away from the moon.
    for _ in range(260):
        x, y = int(rng.uniform(40, width - 40)), int(rng.uniform(40, height * 0.45))
        if math.hypot(x - mx, y - my) < 220:
            continue
        b = rng.uniform(90, 200)
        pixels[y:y + 2, x:x + 2] = (b, b, b * 1.05)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def _moon(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    cx, cy, r = 1580, 400, 92
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_MOON)
    for dx, dy, rr in ((-30, -20, 18), (25, 30, 12), (40, -35, 9), (-10, 45, 7)):
        draw.ellipse((cx + dx - rr, cy + dy - rr, cx + dx + rr, cy + dy + rr), fill=(200, 204, 190))


def _hill_line(base: float, amp: float, waves: tuple[tuple[float, float], ...], width: int) -> np.ndarray:
    x = np.arange(width, dtype=np.float32)
    y = np.full(width, base, dtype=np.float32)
    for period, phase in waves:
        y += amp * np.sin(x / period + phase)
    return y


def _hills(image: Image.Image) -> list[np.ndarray]:
    """Three bands of rolling hills, far to near, each darker, with a fog
    band pooled in the hollow in front of it.  Returns each band's ridge."""
    width, height = SIZE
    arr = np.asarray(image).astype(np.float32)
    yy = np.arange(height, dtype=np.float32)[:, None]
    ridges = []
    bands = (
        (560.0, 30.0, ((210.0, 0.4), (95.0, 1.3)), (40, 46, 62), 0.55),
        (680.0, 42.0, ((260.0, 2.1), (120.0, 0.2)), (26, 30, 40), 0.45),
        (820.0, 50.0, ((330.0, 1.1), (140.0, 2.6)), (12, 14, 20), 0.35),
    )
    for base, amp, waves, colour, fog in bands:
        ridge = _hill_line(base, amp, waves, width)
        ridges.append(ridge)
        below = yy >= ridge[None, :]
        arr[below] = colour
        # Fog: a soft pale band just under the ridge of the band behind,
        # thickest in the hollows (where the ridge dips lowest).
        depth = (ridge - ridge.min()) / max(1.0, ridge.max() - ridge.min())
        band = np.exp(-((yy - (ridge[None, :] + 10.0)) / 34.0) ** 2) * (0.35 + 0.65 * depth)[None, :]
        arr += band[:, :, None] * fog * (np.array((150, 160, 170), dtype=np.float32) - arr)
    image.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    return ridges


def _headstones(image: Image.Image, ridge: np.ndarray, seed: int) -> None:
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(seed)
    x = 90
    while x < SIZE[0] - 120:
        ground = int(ridge[min(x, SIZE[0] - 1)]) + 6
        kind = rng.integers(0, 3)
        w = int(rng.integers(34, 54))
        h = int(rng.integers(50, 90))
        if kind == 0:  # rounded tablet
            draw.rectangle((x, ground - h + w // 2, x + w, ground), fill=_STONE)
            draw.ellipse((x, ground - h, x + w, ground - h + w), fill=_STONE)
            draw.line((x + w, ground - h + w // 2, x + w, ground), fill=_STONE_EDGE, width=2)
        elif kind == 1:  # cross
            draw.rectangle((x + w // 2 - 6, ground - h - 20, x + w // 2 + 6, ground), fill=_STONE)
            draw.rectangle((x + 4, ground - h + 4, x + w - 4, ground - h + 16), fill=_STONE)
        else:  # tilted slab (old)
            lean = int(rng.integers(-10, 10))
            draw.polygon(((x, ground), (x + w, ground), (x + w + lean, ground - h),
                          (x + lean, ground - h)), fill=_STONE)
        x += int(rng.integers(90, 170))


def _dead_tree(image: Image.Image, x: int, ground: int) -> None:
    draw = ImageDraw.Draw(image)
    colour = (6, 7, 10)

    def branch(x0, y0, angle, length, width, depth):
        if depth == 0 or length < 8:
            return
        x1 = x0 + length * math.cos(angle)
        y1 = y0 - length * math.sin(angle)
        draw.line((x0, y0, x1, y1), fill=colour, width=max(1, int(width)))
        branch(x1, y1, angle + 0.45, length * 0.72, width * 0.65, depth - 1)
        branch(x1, y1, angle - 0.38, length * 0.66, width * 0.65, depth - 1)

    branch(x, ground, math.pi / 2 + 0.05, 190, 26, 7)


def _mausoleum(image: Image.Image, x: int, ground: int) -> None:
    draw = ImageDraw.Draw(image)
    c = (22, 25, 34)
    draw.rectangle((x, ground - 150, x + 170, ground), fill=c)
    draw.polygon(((x - 14, ground - 150), (x + 184, ground - 150), (x + 85, ground - 205)), fill=c)
    draw.rectangle((x + 60, ground - 100, x + 110, ground), fill=(10, 11, 16))
    for cx in (x + 12, x + 146):
        draw.rectangle((cx, ground - 150, cx + 12, ground), fill=(34, 38, 48))


def _gate(image: Image.Image) -> None:
    """The iron gate across the foreground, with its sign."""
    draw = ImageDraw.Draw(image)
    width, height = SIZE
    iron = (4, 4, 6)
    top, bottom = 690, 930
    left, right = 150, width - 150
    for x in range(left, right, 34):
        draw.rectangle((x, top, x + 6, bottom), fill=iron)
        draw.polygon(((x - 4, top), (x + 10, top), (x + 3, top - 22)), fill=iron)
    for y in (top + 26, bottom - 40):
        draw.rectangle((left, y, right, y + 8), fill=iron)
    for x in (left - 40, right - 10):
        draw.rectangle((x, top - 90, x + 50, bottom), fill=(30, 32, 38))
        draw.rectangle((x - 8, top - 104, x + 58, top - 90), fill=(44, 46, 52))
    # The sign on the gate.
    sx0, sy0, sx1, sy1 = width // 2 - 260, top + 60, width // 2 + 260, top + 150
    draw.rectangle((sx0, sy0, sx1, sy1), fill=(214, 206, 180), outline=iron, width=5)
    line = "GATES CLOSE AT MIDNIGHT"
    face = paint.fit_font("serif", line, sx1 - sx0 - 60, ceiling=40)
    l, t, r, b = draw.textbbox((0, 0), line, font=face)
    draw.text(((sx0 + sx1 - (r - l)) // 2 - l, sy0 + 22 - t), line, font=face, fill=(30, 24, 20))


def render_loadscreen(seed: int = 1897) -> Image.Image:
    image = _sky(seed)
    _moon(image)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    ridges = _hills(image)
    _mausoleum(image, 1180, int(ridges[0][1260]) + 12)
    _headstones(image, ridges[1], seed + 1)
    _dead_tree(image, 360, int(ridges[2][360]) + 20)
    _gate(image)
    draw = ImageDraw.Draw(image)
    title = paint.fit_font("chancery", TITLE, 1300, ceiling=150)
    l, t, r, b = draw.textbbox((0, 0), TITLE, font=title)
    x, y = (SIZE[0] - (r - l)) // 2 - l, 120 - t
    shadow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + 6, y + 6), TITLE, font=title, fill=(0, 0, 0, 200))
    image = Image.alpha_composite(image.convert("RGBA"),
                                  shadow.filter(ImageFilter.GaussianBlur(6))).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.text((x, y), TITLE, font=title, fill=_TITLE)
    face = paint.font("serif_italic", 44)
    l, t, r, b = draw.textbbox((0, 0), GAG, font=face)
    draw.text(((SIZE[0] - (r - l)) // 2 - l, 300 - t), GAG, font=face, fill=_GAG)
    return paint.vignette(image, 0.34)


def loadscreen_png() -> bytes:
    """The loading screen as PNG bytes, for ``commit(loading_image=...)``."""
    image = render_loadscreen()
    if image.size != SIZE:
        raise ValueError(f"the loading screen must be {SIZE}, drew {image.size}")
    return encode_png(SIZE[0], SIZE[1], image.convert("RGB").tobytes())
