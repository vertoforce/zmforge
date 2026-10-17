"""Drawing primitives for wall art that is authored rather than photographed.

WHY these and not a photograph.  ``materialType`` is ``lit_detail``: the
colour map supplies tint and large shapes, and everything finer than a texel
comes from the detail normal.  Measured on a photographed wall, a smooth painted
wall carries **0.21 / 255** of luminance at the 1-pixel octave, so its colour
map contributes a tint and little else and the surface reads as whatever the
detail map is.  A sign, a poster or a framed picture is the opposite case by
construction -- black ink on pale paper is the highest-contrast thing a wall
can carry -- which is why the art here is linework and type, not soft
gradients, and why every surface below is given visible grain rather than a
flat fill.

:func:`rms_contrast` and :func:`octave_energy` are the same measurements the
tile chain reports, so a piece can be checked against the same numbers rather
than judged by eye.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

__all__ = [
    "FONTS",
    "Ink",
    "board",
    "brass_plaque",
    "canvas_weave",
    "coffee_ring",
    "contain",
    "cover",
    "drip",
    "fit_font",
    "font",
    "font_path",
    "gilt_frame",
    "grain",
    "load_source",
    "normal_map",
    "octave_energy",
    "paper",
    "plaster",
    "punch",
    "rms_contrast",
    "rule",
    "spray_text",
    "stamp",
    "tape_corner",
    "text_block",
    "torn_edge",
    "vignette",
]

#: Extra faces registered by file path (a painter can add its own OFL faces
#: here).  The built-in jobs ("sign", "serif", "typewriter", ...) are not in
#: this dict: :func:`zmforge.fonts.resolve` finds them on any OS (the fonts
#: named in :data:`zmforge.fonts.FACES` first, then macOS/Windows equivalents, then an
#: OFL face fetched once into the font cache).  Nothing here falls back to
#: Pillow's 11-pixel bitmap, which would silently leave a poster blank.
#: Licences are recorded in assets-cache/fonts/FONTS.json.
FONTS: dict[str, Path] = {}


@dataclass(frozen=True)
class Ink:
    """Colours that behave like real marks, not like pure primaries.

    Pure black on pure white is the one combination that reads as a computer
    drew it, so the defaults are a warm near-black and a paper white with a
    cast.
    """

    black: tuple[int, int, int] = (26, 24, 22)
    soft_black: tuple[int, int, int] = (58, 54, 50)
    red: tuple[int, int, int] = (164, 32, 28)
    official_red: tuple[int, int, int] = (186, 42, 34)
    blue: tuple[int, int, int] = (36, 54, 118)
    green: tuple[int, int, int] = (28, 96, 62)
    gold: tuple[int, int, int] = (176, 138, 58)
    brass: tuple[int, int, int] = (158, 126, 54)
    paper: tuple[int, int, int] = (226, 217, 194)
    paper_white: tuple[int, int, int] = (238, 233, 220)
    card: tuple[int, int, int] = (206, 192, 162)


INK = Ink()


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """A face by job name at *size* pixels, or a clear failure."""
    return ImageFont.truetype(str(font_path(kind)), size)


def font_path(kind: str) -> Path:
    """The file behind job *kind*: a registered path, else :func:`zmforge.fonts.resolve`."""
    from ..fonts import FACES, resolve

    path = FONTS.get(kind)
    if path is None:
        if kind not in FACES:
            known = sorted({*FONTS, *FACES})
            raise KeyError(f"no face called {kind!r}; known: {', '.join(known)}")
        return resolve(kind)
    if not path.exists():
        raise FileNotFoundError(f"{kind}: {path} is not installed")
    return path


def fit_font(kind: str, text: str, width: int, *, ceiling: int = 400, floor: int = 6):
    """The largest size of *kind* at which *text* still fits *width* pixels."""
    size = ceiling
    while size > floor:
        face = font(kind, size)
        if face.getbbox(text) is None:
            return face
        left, _, right, _ = face.getbbox(text)
        if right - left <= width:
            return face
        size = max(floor, int(size * min(0.92, width / max(right - left, 1))))
    return font(kind, floor)


# -- surfaces ----------------------------------------------------------------


def _noise(shape: tuple[int, int], scale: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth value noise in [-1, 1] at roughly *scale* pixels per feature."""
    small = max(2, int(shape[0] / max(scale, 1))), max(2, int(shape[1] / max(scale, 1)))
    seed = rng.random(small).astype(np.float32)
    grown = np.asarray(
        Image.fromarray((seed * 255).astype(np.uint8)).resize(
            (shape[1], shape[0]), Image.BICUBIC
        ),
        dtype=np.float32,
    )
    grown = (grown - grown.mean()) / max(grown.std(), 1e-6)
    return np.clip(grown / 3.0, -1.0, 1.0)


def grain(image: Image.Image, amount: float = 6.0, *, seed: int = 0) -> Image.Image:
    """Per-pixel noise, so the surface is never a flat fill.

    A flat fill is the failure this guards: with no fine structure of its own
    a colour map hands the whole look to the detail normal, and the surface
    stops being a poster and becomes tinted whatever-the-detail-map-is.
    """
    rng = np.random.default_rng(seed)
    array = np.asarray(image, dtype=np.float32)
    speckle = rng.normal(0.0, amount, array.shape[:2])[:, :, None]
    return Image.fromarray(np.clip(array + speckle, 0, 255).astype(np.uint8))


def paper(
    size: tuple[int, int],
    *,
    tone: tuple[int, int, int] = INK.paper,
    seed: int = 0,
    foxing: float = 1.0,
) -> Image.Image:
    """Aged paper: a mottled tone, fibre grain and a few foxing blooms."""
    width, height = size
    rng = np.random.default_rng(seed)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[:, :] = tone
    mottle = _noise((height, width), 48.0, rng)[:, :, None]
    base += mottle * 14.0
    fibre = _noise((height, width), 3.0, rng)[:, :, None]
    base += fibre * 7.0
    for _ in range(int(3 * foxing)):
        cx, cy = rng.integers(0, width), rng.integers(0, height)
        radius = rng.integers(width // 12, width // 5)
        yy, xx = np.mgrid[0:height, 0:width]
        fall = np.clip(1.0 - np.hypot(xx - cx, yy - cy) / max(radius, 1), 0, 1) ** 2
        base -= fall[:, :, None] * np.array([6.0, 12.0, 20.0]) * rng.uniform(0.4, 1.0)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def board(
    size: tuple[int, int],
    *,
    tone: tuple[int, int, int] = (96, 74, 52),
    seed: int = 0,
    planks: int = 0,
) -> Image.Image:
    """Painted or bare wood: long grain along x, optional plank seams."""
    width, height = size
    rng = np.random.default_rng(seed)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[:, :] = tone
    long_grain = _noise((height, width // 24 or 1), 2.0, rng)
    long_grain = np.asarray(
        Image.fromarray(((long_grain + 1) * 127).astype(np.uint8)).resize(
            (width, height), Image.BICUBIC
        ),
        dtype=np.float32,
    )
    base += ((long_grain / 127.0) - 1.0)[:, :, None] * 22.0
    base += _noise((height, width), 2.0, rng)[:, :, None] * 8.0
    if planks:
        step = height / planks
        for index in range(1, planks):
            y = int(index * step)
            base[max(0, y - 2) : y + 2, :] *= 0.62
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def plaster(
    size: tuple[int, int],
    *,
    tone: tuple[int, int, int] = (150, 145, 134),
    seed: int = 0,
) -> Image.Image:
    """Painted masonry, for graffiti and stencilled notices to sit on."""
    width, height = size
    rng = np.random.default_rng(seed)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[:, :] = tone
    base += _noise((height, width), 60.0, rng)[:, :, None] * 20.0
    base += _noise((height, width), 8.0, rng)[:, :, None] * 12.0
    base += _noise((height, width), 1.6, rng)[:, :, None] * 9.0
    image = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    for _ in range(rng.integers(4, 9)):
        x, y = rng.integers(0, width), rng.integers(0, height)
        points = [(x, y)]
        for _ in range(rng.integers(3, 8)):
            x += int(rng.integers(-width // 9, width // 9))
            y += int(rng.integers(-height // 14, height // 14))
            points.append((x, y))
        draw.line(points, fill=(tone[0] - 34, tone[1] - 34, tone[2] - 32), width=2)
    return image


# -- marks -------------------------------------------------------------------


def text_block(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[tuple[str, str, int, tuple[int, int, int]]],
    *,
    left: int,
    top: int,
    width: int,
    leading: float = 1.25,
    centre: bool = False,
) -> int:
    """Lay out ``(text, face, size, colour)`` rows and return the bottom y.

    A row whose size is ``0`` is fitted to *width* instead, which is how a
    headline gets to be as large as its box allows without a magic number.
    """
    y = top
    for text, face_name, size, colour in lines:
        if not text:
            y += int(leading * (size or 16))
            continue
        face = fit_font(face_name, text, width) if size == 0 else font(face_name, size)
        box = face.getbbox(text)
        # A line that does not fit is shrunk to fit rather than clipped: a
        # notice whose punchline runs off the paper is not a joke, it is a
        # bug, and every one of these is a hand-written string.
        if box is not None and box[2] - box[0] > width:
            face = fit_font(face_name, text, width, ceiling=size or 400)
            box = face.getbbox(text)
        run = (box[2] - box[0]) if box else 0
        x = left + (width - run) // 2 if centre else left
        draw.text((x - (box[0] if box else 0), y), text, font=face, fill=colour)
        y += int(((box[3] - box[1]) if box else size) * leading)
    return y


def rule(
    draw: ImageDraw.ImageDraw,
    y: int,
    left: int,
    right: int,
    *,
    colour: tuple[int, int, int] = INK.black,
    weight: int = 3,
) -> None:
    draw.line([(left, y), (right, y)], fill=colour, width=weight)


def border(
    image: Image.Image,
    *,
    inset: int,
    colour: tuple[int, int, int] = INK.black,
    weight: int = 6,
    double: bool = True,
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    draw.rectangle(
        [inset, inset, width - inset - 1, height - inset - 1], outline=colour, width=weight
    )
    if double:
        gap = inset + weight * 3
        draw.rectangle(
            [gap, gap, width - gap - 1, height - gap - 1],
            outline=colour,
            width=max(1, weight // 3),
        )


def gilt_frame(image: Image.Image, *, depth: int = 0, seed: int = 0) -> None:
    """An ornate gold frame drawn into the outside of *image*, in place.

    Grandeur that is trying too hard is the point, so the moulding is four
    bands of different width with a bevel, not one flat gold rectangle.
    """
    width, height = image.size
    depth = depth or max(14, min(width, height) // 11)
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(seed)
    bands = [
        (0.00, 0.34, (120, 92, 34)),
        (0.34, 0.52, (206, 172, 84)),
        (0.52, 0.66, (148, 114, 44)),
        (0.66, 0.84, (228, 198, 116)),
        (0.84, 1.00, (96, 72, 28)),
    ]
    for start, end, colour in bands:
        a, b = int(depth * start), int(depth * end)
        for offset in range(a, max(a + 1, b)):
            jitter = int(rng.integers(-6, 7))
            shade = tuple(max(0, min(255, c + jitter)) for c in colour)
            draw.rectangle(
                [offset, offset, width - offset - 1, height - offset - 1], outline=shade
            )
    inner = depth
    draw.rectangle(
        [inner, inner, width - inner - 1, height - inner - 1], outline=(52, 40, 18), width=3
    )


def brass_plaque(
    image: Image.Image,
    box: tuple[int, int, int, int],
    lines: Sequence[str],
    *,
    face: str = "serif",
    seed: int = 0,
) -> None:
    """The engraved plate under a portrait: brushed metal, engraved type."""
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    rng = np.random.default_rng(seed)
    plate = np.zeros((height, width, 3), dtype=np.float32)
    plate[:, :] = (150, 122, 58)
    plate += _noise((height, width), 1.5, rng)[:, :, None] * 10.0
    plate += np.linspace(16, -16, height)[:, None, None]
    tile = Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(tile)
    draw.rectangle([0, 0, width - 1, height - 1], outline=(92, 72, 30), width=2)
    gap = height / (len(lines) + 0.6)
    for index, text in enumerate(lines):
        fitted = fit_font(face, text, int(width * 0.86), ceiling=int(gap * 0.95))
        bbox = fitted.getbbox(text)
        run = bbox[2] - bbox[0]
        x = (width - run) // 2 - bbox[0]
        y = int(gap * (index + 0.3))
        draw.text((x + 1, y + 1), text, font=fitted, fill=(206, 182, 118))
        draw.text((x, y), text, font=fitted, fill=(58, 44, 16))
    image.paste(tile, (x0, y0))


def stamp(
    image: Image.Image,
    centre: tuple[int, int],
    text: str,
    *,
    colour: tuple[int, int, int] = INK.official_red,
    angle: float = -14.0,
    width: int = 0,
    boxed: bool = True,
) -> None:
    """A rubber stamp, rotated and unevenly inked."""
    width = width or int(image.size[0] * 0.55)
    fitted = fit_font("sign", text, int(width * 0.84))
    bbox = fitted.getbbox(text)
    height = int((bbox[3] - bbox[1]) * 2.1)
    plate = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    if boxed:
        draw.rectangle([2, 2, width - 3, height - 3], outline=colour + (235,), width=6)
    draw.text(
        ((width - (bbox[2] - bbox[0])) // 2 - bbox[0], (height - (bbox[3] - bbox[1])) // 2 - bbox[1]),
        text,
        font=fitted,
        fill=colour + (235,),
    )
    rng = np.random.default_rng(abs(hash(text)) % (2**31))
    alpha = np.asarray(plate.split()[3], dtype=np.float32)
    alpha *= np.clip(0.55 + _noise(alpha.shape, 5.0, rng) * 1.1, 0.0, 1.0)
    plate.putalpha(Image.fromarray(alpha.astype(np.uint8)))
    plate = plate.rotate(angle, expand=True, resample=Image.BICUBIC)
    image.paste(plate, (centre[0] - plate.size[0] // 2, centre[1] - plate.size[1] // 2), plate)


def spray_text(
    image: Image.Image,
    position: tuple[int, int],
    text: str,
    *,
    colour: tuple[int, int, int],
    width: int,
    face: str = "sign",
    angle: float = 0.0,
    drips: int = 3,
    seed: int = 0,
) -> None:
    """Spray paint: soft edges, overspray, and paint that ran."""
    fitted = fit_font(face, text, width)
    bbox = fitted.getbbox(text)
    pad = max(18, width // 12)
    plate = Image.new(
        "RGBA", (bbox[2] - bbox[0] + pad * 2, bbox[3] - bbox[1] + pad * 4), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(plate)
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=fitted, fill=colour + (255,))
    rng = np.random.default_rng(seed)
    for _ in range(drips):
        x = int(rng.integers(pad, max(pad + 1, plate.size[0] - pad)))
        y = pad + (bbox[3] - bbox[1])
        length = int(rng.integers(pad, pad * 3))
        draw.line([(x, y - 6), (x, y + length)], fill=colour + (220,), width=int(rng.integers(3, 7)))
        draw.ellipse(
            [x - 4, y + length - 4, x + 4, y + length + 4], fill=colour + (200,)
        )
    plate = plate.filter(ImageFilter.GaussianBlur(1.6))
    alpha = np.asarray(plate.split()[3], dtype=np.float32)
    alpha *= np.clip(0.72 + _noise(alpha.shape, 4.0, rng) * 0.8, 0.0, 1.15)
    overspray = np.clip(_noise(alpha.shape, 2.0, rng), 0, 1) * (alpha > 8) * 26.0
    plate.putalpha(Image.fromarray(np.clip(alpha + overspray, 0, 255).astype(np.uint8)))
    if angle:
        plate = plate.rotate(angle, expand=True, resample=Image.BICUBIC)
    image.paste(plate, position, plate)


def drip(
    image: Image.Image, x: int, y: int, length: int, colour: tuple[int, int, int], width: int = 5
) -> None:
    draw = ImageDraw.Draw(image)
    draw.line([(x, y), (x, y + length)], fill=colour, width=width)
    draw.ellipse([x - width, y + length - width, x + width, y + length + width], fill=colour)


def tape_corner(image: Image.Image, corner: str, *, span: int = 0, seed: int = 0) -> None:
    """A strip of yellowed tape across one corner."""
    width, height = image.size
    span = span or min(width, height) // 4
    plate = Image.new("RGBA", (span, span // 3), (222, 214, 178, 128))
    draw = ImageDraw.Draw(plate)
    draw.rectangle([0, 0, span - 1, span // 3 - 1], outline=(196, 188, 150, 150))
    rng = np.random.default_rng(seed)
    angles = {"nw": -45, "ne": 45, "sw": 45, "se": -45}
    plate = plate.rotate(angles.get(corner, -45) + int(rng.integers(-6, 7)), expand=True)
    spots = {
        "nw": (-plate.size[0] // 3, -plate.size[1] // 3),
        "ne": (width - 2 * plate.size[0] // 3, -plate.size[1] // 3),
        "sw": (-plate.size[0] // 3, height - 2 * plate.size[1] // 3),
        "se": (width - 2 * plate.size[0] // 3, height - 2 * plate.size[1] // 3),
    }
    image.paste(plate, spots.get(corner, (0, 0)), plate)


def coffee_ring(image: Image.Image, centre: tuple[int, int], radius: int, *, seed: int = 0) -> None:
    plate = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    rng = np.random.default_rng(seed)
    for step in range(3):
        wobble = int(rng.integers(-4, 5))
        draw.ellipse(
            [
                centre[0] - radius - wobble,
                centre[1] - radius - wobble,
                centre[0] + radius + wobble,
                centre[1] + radius + wobble,
            ],
            outline=(120, 86, 46, 92 - step * 22),
            width=5 - step,
        )
    plate = plate.filter(ImageFilter.GaussianBlur(2.0))
    image.paste(plate, (0, 0), plate)


def torn_edge(image: Image.Image, side: str = "bottom", *, depth: int = 0, seed: int = 0) -> None:
    """Replace one edge with a ragged tear, filled with the paper's backing."""
    width, height = image.size
    depth = depth or max(8, height // 22)
    rng = np.random.default_rng(seed)
    draw = ImageDraw.Draw(image)
    if side in ("bottom", "top"):
        y = height - 1 if side == "bottom" else 0
        points = []
        x = 0
        while x < width:
            points.append((x, y + int(rng.integers(-depth, depth + 1)) * (1 if side == "top" else -1)))
            x += max(6, width // 40)
        points.append((width, y))
        polygon = points + ([(width, height), (0, height)] if side == "bottom" else [(width, 0), (0, 0)])
        draw.polygon(polygon, fill=(196, 188, 168))
        draw.line(points, fill=(150, 142, 124), width=2)


def vignette(image: Image.Image, strength: float = 0.28) -> Image.Image:
    """Darken the corners, the way anything hanging in a lit room does."""
    width, height = image.size
    yy, xx = np.mgrid[0:height, 0:width]
    radius = np.hypot(xx - width / 2, yy - height / 2) / math.hypot(width / 2, height / 2)
    fall = 1.0 - strength * np.clip(radius, 0, 1) ** 2
    array = np.asarray(image, dtype=np.float32) * fall[:, :, None]
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


# -- mounting a found picture ------------------------------------------------


def load_source(path: Path | str, *, max_side: int = 2400) -> Image.Image:
    """A found image, upright, in RGB, no bigger than it needs to be.

    ``exif_transpose`` is not optional: a camera photograph can decode
    5184x3888 landscape and carry EXIF orientation 6, so a reader that
    ignores the tag hangs it sideways.
    """
    # The file is closed before anything else happens to the pixels: Pillow
    # opens lazily, and a set this size leaks a handle per picture otherwise.
    with Image.open(str(path)) as opened:
        opened.load()
        image = ImageOps.exif_transpose(opened) or opened
        image = image.convert("RGB")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    return image


def cover(
    image: Image.Image, size: tuple[int, int], *, zoom: float = 1.0, bias: float = 1 / 3
) -> Image.Image:
    """Fill *size* with *image*, cropping the long axis rather than squashing.

    ``zoom`` crops in further, which is how a photograph *of a framed
    painting on a gallery wall* becomes the painting: such a photograph
    often carries the painting's frame, its gallery label and a strip of
    white wall, and none of that belongs inside our frame.
    """
    width, height = size
    scale = max(width / image.size[0], height / image.size[1]) * max(zoom, 1.0)
    grown = image.resize(
        (max(width, int(image.size[0] * scale)), max(height, int(image.size[1] * scale))),
        Image.LANCZOS,
    )
    left = (grown.size[0] - width) // 2
    top = int((grown.size[1] - height) * bias)  # bias up: faces sit above centre
    return grown.crop((left, top, left + width, top + height))


def contain(image: Image.Image, size: tuple[int, int], background: tuple[int, int, int]):
    """Fit *image* inside *size* whole, on *background*.  Nothing is cropped."""
    plate = Image.new("RGB", size, background)
    copy = image.copy()
    copy.thumbnail(size, Image.LANCZOS)
    plate.paste(copy, ((size[0] - copy.size[0]) // 2, (size[1] - copy.size[1]) // 2))
    return plate


def punch(image: Image.Image, amount: float = 1.22, black: float = 0.06) -> Image.Image:
    """Lift contrast and clip a little black, so the picture holds up in game.

    A scan of an old painting is mostly midtones; a wall texture that is all
    midtones is the flat case this whole module is trying to avoid.
    """
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = np.clip((array - black) / max(1.0 - black, 1e-3), 0, 1)
    array = np.clip((array - 0.5) * amount + 0.5, 0, 1)
    return Image.fromarray((array * 255).astype(np.uint8))


# -- detail normals ----------------------------------------------------------


def normal_map(height_field: np.ndarray, *, strength: float = 2.0) -> Image.Image:
    """A tangent-space normal map from a height field in [0, 1].

    The convention is the shipped detail normals': +X right, +Y up, +Z out,
    packed to 0-255.  Anything flatter than the surface it stands for is
    better than borrowing another surface's relief, which is the defect this
    whole module exists to avoid.
    """
    field = height_field.astype(np.float32)
    dx = np.gradient(field, axis=1) * strength * field.shape[1] / 64.0
    dy = np.gradient(field, axis=0) * strength * field.shape[0] / 64.0
    normals = np.dstack([-dx, dy, np.ones_like(field)])
    normals /= np.linalg.norm(normals, axis=2, keepdims=True)
    return Image.fromarray(((normals * 0.5 + 0.5) * 255).astype(np.uint8))


def canvas_weave(size: tuple[int, int], *, period: float = 5.0, seed: int = 0) -> np.ndarray:
    """A height field of woven threads, for a painting's own surface."""
    width, height = size
    yy, xx = np.mgrid[0:height, 0:width]
    weave = np.sin(xx * 2 * math.pi / period) * np.sin(yy * 2 * math.pi / period)
    rng = np.random.default_rng(seed)
    return np.clip(0.5 + 0.28 * weave + 0.12 * _noise((height, width), 2.0, rng), 0, 1)


def paper_fibre(size: tuple[int, int], *, seed: int = 0) -> np.ndarray:
    """A height field of paper: fine random fibre, almost no large relief."""
    width, height = size
    rng = np.random.default_rng(seed)
    field = 0.5 + 0.10 * _noise((height, width), 1.4, rng) + 0.04 * _noise((height, width), 6.0, rng)
    return np.clip(field, 0, 1)


def wood_grain(size: tuple[int, int], *, seed: int = 0) -> np.ndarray:
    """A height field of sawn board: long grain plus the odd raised ridge."""
    width, height = size
    rng = np.random.default_rng(seed)
    stretched = _noise((height, max(2, width // 20)), 2.0, rng)
    grown = np.asarray(
        Image.fromarray(((stretched + 1) * 127).astype(np.uint8)).resize(
            (width, height), Image.BICUBIC
        ),
        dtype=np.float32,
    ) / 127.0 - 1.0
    return np.clip(0.5 + 0.22 * grown + 0.06 * _noise((height, width), 1.5, rng), 0, 1)


# -- measurement -------------------------------------------------------------


def _luma(image: Image.Image) -> np.ndarray:
    array = np.asarray(image.convert("RGB"), dtype=np.float32)
    return array @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def rms_contrast(image: Image.Image) -> float:
    """Standard deviation of luminance, 0-255.  The tile chain's own number."""
    return float(_luma(image).std())


def octave_energy(image: Image.Image, octaves: Iterable[int] = (1, 2, 4, 8)) -> dict[str, float]:
    """Luminance RMS surviving a blur at each octave, 0-255.

    The 1-pixel figure is the one that decides whether a surface has fine
    structure of its own: a smooth painted wall measures about 0.21 there and
    renders as whatever its detail map is.
    """
    luma = _luma(image)
    out: dict[str, float] = {}
    for octave in octaves:
        blurred = np.asarray(
            Image.fromarray(luma.astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(octave / 2.0)
            ),
            dtype=np.float32,
        )
        out[f"{octave}px"] = float((luma - blurred).std())
    return out
