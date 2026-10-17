"""The full-screen loading image for ``zm_dmv``, "DMV of the Damned", drawn here.

A waiting room the player is stuck in while the fastfile loads, which is the
joke: the wall board says NOW SERVING, the ticket in hand is hopelessly far
behind it, and the small print is the Department's own. Everything is drawn
from code with the fonts :mod:`zmforge.texture.paint` names; nothing is
sourced, so there is no licence question.

The layout rules every loading screen here keeps: 1920 x 1080 only,
the outer 30 px carry no ink, and the bottom band is kept quiet because the
game draws its own progress furniture there. Every random draw is seeded, so
the same code gives the same bytes.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..images import encode_png
from . import paint

__all__ = ["SIZE", "TITLE", "GAG", "render_loadscreen", "loadscreen_png"]

SIZE: tuple[int, int] = (1920, 1080)
TITLE = "DMV OF THE DAMNED"
GAG = "Please take a number. Current wait time: eternal."

_WALL = (38, 52, 50)        # institutional teal, lit badly
_FLOOR = (58, 54, 46)
_LED = (255, 64, 40)
_LED_DIM = (70, 18, 14)
_CREAM = (232, 224, 200)
_TICKET = (236, 228, 196)
_INK = paint.INK.black
_RED = paint.INK.official_red


def _wall(seed: int) -> Image.Image:
    """Painted block wall above a scuffed floor, with a ceiling-light falloff."""
    width, height = SIZE
    rng = np.random.default_rng(seed)
    pixels = np.zeros((height, width, 3), dtype=np.float32)
    pixels[:, :] = _WALL
    floor_top = int(height * 0.80)
    pixels[floor_top:, :] = _FLOOR
    # Block courses: a darker mortar line every 72 px, staggered joints.
    for row, y in enumerate(range(0, floor_top, 72)):
        pixels[y:y + 3, :] -= 14
        offset = 0 if row % 2 else 72
        for x in range(offset, width, 144):
            pixels[y:min(y + 72, floor_top), x:x + 3] -= 12
    # A faint low-frequency mottle, not per-pixel grain: the linker packs this
    # image uncompressed, and grain costs megabytes in the fastfile.
    pixels += np.repeat(np.repeat(rng.normal(0.0, 2.5, (height // 24 + 1, width // 24 + 1, 1)), 24, 0), 24, 1)[:height, :width].astype(np.float32)
    # One fluorescent tube's worth of light, centred high.
    yy, xx = np.mgrid[0:height, 0:width]
    light = np.clip(1.0 - np.hypot((xx - width / 2) / 1.3, yy + 200) / 1500.0, 0, 1)
    pixels *= (0.55 + 0.6 * light)[:, :, None]
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def _centred(draw: ImageDraw.ImageDraw, text: str, y: int, face, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    draw.text(((SIZE[0] - (right - left)) // 2 - left, y - top), text, font=face, fill=fill)


def _board(image: Image.Image) -> None:
    """The NOW SERVING board: black panel, glowing LED number, a dead digit."""
    draw = ImageDraw.Draw(image)
    box = (560, 70, 1360, 370)
    draw.rounded_rectangle((box[0] - 14, box[1] - 14, box[2] + 14, box[3] + 14),
                           radius=18, fill=(92, 92, 88))
    draw.rounded_rectangle(box, radius=10, fill=(12, 12, 12))
    label = paint.font("sign", 54)
    draw.text((box[0] + 40, box[1] + 26), "NOW SERVING", font=label, fill=_CREAM)
    draw.text((box[0] + 40, box[1] + 90), "PLEASE WAIT", font=paint.font("sign_light", 34),
              fill=(160, 150, 130))
    # The number, with a dim "8" ghost under every digit like a real segment
    # display, and a glow pass underneath.
    digits = paint.font("typewriter", 170)
    x, y = box[0] + 300, box[1] + 80
    ghost = ImageDraw.Draw(image)
    ghost.text((x, y), "8888", font=digits, fill=_LED_DIM)
    glow = Image.new("RGB", SIZE, (0, 0, 0))
    ImageDraw.Draw(glow).text((x, y), "A001", font=digits, fill=_LED)
    glow = glow.filter(ImageFilter.GaussianBlur(14))
    base = np.asarray(image, dtype=np.int16)
    base = np.clip(base + (np.asarray(glow, dtype=np.int16) * 0.9).astype(np.int16), 0, 255)
    image.paste(Image.fromarray(base.astype(np.uint8)))
    ImageDraw.Draw(image).text((x, y), "A001", font=digits, fill=_LED)


def _ticket(image: Image.Image) -> None:
    """The player's ticket, tilted, with its hopeless number."""
    width, height = 400, 250
    card = Image.new("RGBA", (width, height), _TICKET + (255,))
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(150, 140, 110), width=3)
    for x in range(12, width, 24):  # perforation along the top
        draw.ellipse((x - 4, -4, x + 4, 4), fill=(0, 0, 0, 0))
    draw.text((28, 26), "YOUR NUMBER", font=paint.font("sign", 30), fill=_INK)
    number = paint.fit_font("typewriter", "Z-9,999,999", width - 56, ceiling=90)
    draw.text((28, 72), "Z-9,999,999", font=number, fill=_RED)
    small = paint.font("typewriter_light", 22)
    draw.text((28, 162), "Est. wait: 115 rounds", font=small, fill=_INK)
    draw.text((28, 196), "Do not lose this ticket.", font=small, fill=_INK)
    tilted = card.rotate(-7, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", tilted.size, (0, 0, 0, 0))
    shadow.putalpha(tilted.getchannel("A").point(lambda a: a // 3))
    image.paste((0, 0, 0), (1400 + 14, 690 + 14), shadow.filter(ImageFilter.GaussianBlur(8)))
    image.paste(tilted, (1400, 690), tilted)


def _chairs(image: Image.Image) -> None:
    """A row of bolted-together waiting-room chairs, in silhouette."""
    draw = ImageDraw.Draw(image)
    y = int(SIZE[1] * 0.80)
    for i in range(5):
        x = 120 + i * 190
        draw.rectangle((x, y - 150, x + 150, y - 60), fill=(30, 58, 92))   # back
        draw.rectangle((x - 6, y - 64, x + 156, y - 40), fill=(26, 50, 80))  # seat
        draw.rectangle((x + 10, y - 40, x + 20, y + 10), fill=(20, 20, 20))
        draw.rectangle((x + 130, y - 40, x + 140, y + 10), fill=(20, 20, 20))
    draw.rectangle((110, y - 50, 120 + 4 * 190 + 160, y - 44), fill=(20, 20, 20))


def render_loadscreen(seed: int = 7) -> Image.Image:
    """The loading screen as an RGB image of :data:`SIZE`."""
    image = _wall(seed)
    _board(image)
    _chairs(image)
    _ticket(image)
    draw = ImageDraw.Draw(image)
    title = paint.fit_font("sign", TITLE, 1500, ceiling=150)
    left, top, right, bottom = draw.textbbox((0, 0), TITLE, font=title)
    y = 410
    for dx, dy in ((5, 6), (0, 0)):  # drop shadow, then the words
        fill = (8, 8, 8) if dx else _CREAM
        draw.text(((SIZE[0] - (right - left)) // 2 - left + dx, y - top + dy), TITLE,
                  font=title, fill=fill)
    _centred(draw, GAG, 580, paint.font("serif_italic", 46), (220, 200, 160))
    _centred(draw, "Form ZM-115: Application to Remain Alive (in triplicate)", 648,
             paint.font("typewriter_light", 28), (170, 165, 150))
    return paint.vignette(image, 0.30)


def loadscreen_png() -> bytes:
    """The loading screen as PNG bytes, for ``commit(loading_image=...)``."""
    image = render_loadscreen()
    if image.size != SIZE:
        raise ValueError(f"the loading screen must be {SIZE}, drew {image.size}")
    return encode_png(SIZE[0], SIZE[1], image.convert("RGB").tobytes())
