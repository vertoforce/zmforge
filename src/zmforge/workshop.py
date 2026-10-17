"""Steam Workshop publish settings: ``zone/workshop.json`` and its thumbnail.

WHAT THE LAUNCHER READS.  ``bin/modlauncher.exe`` (the mod tools' launcher)
carries these strings next to each other, in this order [measured
with ``strings`` on the launcher binary]::

    %1/%2/zone
    /workshop.json
    PublisherID / Title / Description / Thumbnail
    Publish Mod / Title: / Description: / Thumbnail: / Tags:
    All Files (*.*) / Open Thumbnail
    FolderName

So the publish dialog is filled from ``usermaps/<map>/zone/workshop.json``,
its "Thumbnail:" field is one of the four keys read back, and the "Open
Thumbnail" button is a file picker, whose answer is an absolute path.  That the
launcher hands this path to Steam as the item's preview image is the natural
reading and is **not verified** here: nothing in this project has published an
item with it set.  The install step writes the absolute Windows path because a
relative one would resolve against whatever folder the launcher runs from.

SIZE.  Logical Edits ("Preview Image, Loading Screens & Steam Workshop Page") gives the Workshop thumbnail as 512 x 512 and
under 2 MB, or the publish errors.  :data:`THUMBNAIL_SIZE` is that square and
:data:`THUMBNAIL_MAX_BYTES` holds it to 1 MB, Steam's own recommendation, which
a 512 x 512 JPEG never approaches.

MERGE, NOT CLOBBER.  The file in the mod tools install is also where the launcher
stores the Workshop item id after the first publish (``PublisherID``) and what
the user typed.  :func:`merge_workshop` is the rule the install step applies:
the user's non-empty ``PublisherID``, ``Title`` and ``Description`` win, and
every key the generator does not write (``Tags``, ``Type``) is kept.  An
install step that copies the generated file over an existing one must apply
it, or the next publish makes a second Workshop item.

THE PICTURE.  :func:`hero_shot` looks for a ``zmforge render`` run of the map
and picks its hero render (``hero.png``, see :mod:`zmforge.render.hero`) or
failing that its strongest eye-level shot; :func:`compose` crops it to a size,
resizes it and prints the map's title across the foot.  With no render run the
caller keeps the plan view.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Mapping

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

__all__ = [
    "WORKSHOP_JSON_NAME",
    "THUMBNAIL_NAME",
    "THUMBNAIL_SIZE",
    "THUMBNAIL_MAX_BYTES",
    "USER_KEYS",
    "workshop_fields",
    "workshop_json",
    "merge_workshop",
    "hero_shot",
    "compose",
    "thumbnail_jpeg",
    "preview_png",
]

WORKSHOP_JSON_NAME = "workshop.json"
#: Beside workshop.json in the zone folder; the install step copies it there and
#: points ``Thumbnail`` at it.
THUMBNAIL_NAME = "workshop_thumbnail.jpg"
THUMBNAIL_SIZE = (512, 512)
THUMBNAIL_MAX_BYTES = 1_000_000

#: Keys whose non-empty value in the installed file outlives a reinstall.
USER_KEYS = ("PublisherID", "Title", "Description")

#: A shot darker than this on average is a black or unlit render.
_MIN_MEAN = 28.0


# ---------------------------------------------------------------------------
# workshop.json
# ---------------------------------------------------------------------------


def workshop_fields(name: str, title: str, *, description: str = "",
                    thumbnail: str = THUMBNAIL_NAME) -> dict[str, str]:
    """What the generator knows about the publish: never a ``PublisherID``.

    ``Thumbnail`` is the bare file name; the install step replaces it with the
    absolute path in the mod tools install (see the module docstring).
    """
    return {
        "Title": title,
        "Description": description,
        "FolderName": name,
        "Thumbnail": thumbnail,
    }


def workshop_json(fields: Mapping[str, object]) -> bytes:
    """``fields`` as the launcher's file: UTF-8, no BOM, tab-free indent."""
    return (json.dumps(dict(fields), indent=4, ensure_ascii=False) + "\n").encode("utf-8")


def merge_workshop(existing: Mapping[str, object] | None,
                   generated: Mapping[str, object],
                   *, thumbnail: str | None = None) -> dict[str, object]:
    """The file to leave in the mod tools install.

    Start from *existing* (kept whole, so ``Tags``/``Type`` survive), lay the
    generated values over it, then put back any non-empty :data:`USER_KEYS`
    the installed file already had.  A generated ``PublisherID`` is ignored outright: a
    wrong id would publish over someone else's item.  *thumbnail*, when given,
    is the absolute path ``Thumbnail`` should hold.
    """
    merged: dict[str, object] = dict(existing or {})
    for key, value in generated.items():
        if key == "PublisherID":
            continue
        merged[key] = value
    for key in USER_KEYS:
        value = (existing or {}).get(key)
        if value not in (None, ""):
            merged[key] = value
    merged.setdefault("PublisherID", "")
    if thumbnail is not None:
        merged["Thumbnail"] = thumbnail
    return merged


# ---------------------------------------------------------------------------
# Picking the picture
# ---------------------------------------------------------------------------


def _score(path: Path) -> float:
    """How much there is to look at: luminance spread, zero for a dark frame."""
    with Image.open(path) as image:
        grey = np.asarray(image.convert("L").resize((256, 144)), dtype=np.float32)
    if grey.mean() < _MIN_MEAN:
        return 0.0
    edges = np.abs(np.diff(grey, axis=0)).mean() + np.abs(np.diff(grey, axis=1)).mean()
    return float(grey.std() + edges)


def hero_shot(name: str, root: Path | None = None) -> Path | None:
    """The render to build *name*'s Workshop pictures from, or None.

    The latest ``zmforge render`` run's ``hero.png`` when it has one; else its
    eye-level doorway shots (``door*``, 60 units up) scored by :func:`_score`;
    else None, and the caller keeps the plan view.  High corner shots are left
    out on purpose: they look down on a room like a plan does.
    """
    from .render.run import latest_run, load_manifest

    run = latest_run(name, root)
    if run is None:
        return None
    hero = run / "hero.png"
    if hero.is_file():
        return hero
    manifest = load_manifest(run)
    best: tuple[float, Path] | None = None
    for paths in manifest.get("shots", {}).values():
        for raw in paths:
            path = Path(raw)
            if not path.is_file() or "--door" not in path.stem:
                continue
            score = _score(path)
            if score > 0 and (best is None or score > best[0]):
                best = (score, path)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Composing
# ---------------------------------------------------------------------------


def _crop_to(image: Image.Image, size: tuple[int, int], focus: float = 0.5) -> Image.Image:
    """Centre-crop *image* to *size*'s aspect (*focus* shifts it sideways)."""
    width, height = image.size
    want = size[0] / size[1]
    if width / height > want:
        new_w = round(height * want)
        left = round((width - new_w) * min(max(focus, 0.0), 1.0))
        box = (left, 0, left + new_w, height)
    else:
        new_h = round(width / want)
        top = (height - new_h) // 2
        box = (0, top, width, top + new_h)
    return image.crop(box).resize(size, Image.LANCZOS)


def compose(source: Image.Image | Path | str, title: str, size: tuple[int, int],
            *, focus: float = 0.5) -> Image.Image:
    """*source* cropped to *size*, with *title* printed across its foot.

    The title is set in the loading screen's ``sign`` face, white over a dark
    band that fades up into the picture, so it reads on any render.
    """
    from .texture import paint

    if not isinstance(source, Image.Image):
        with Image.open(source) as opened:
            source = opened.convert("RGB")
    image = _crop_to(source.convert("RGB"), size, focus)
    width, height = size
    margin = max(8, width // 24)
    text = title.upper()
    face = paint.fit_font("sign", text, width - 2 * margin, ceiling=max(24, height // 7))
    left, top, right, bottom = face.getbbox(text)
    text_h = bottom - top
    band = int(text_h * 2.6) + margin

    shade = np.zeros((height, 1), dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, band, dtype=np.float32) ** 1.4
    shade[height - band:, 0] = ramp * 0.82
    alpha = Image.fromarray((np.repeat(shade, width, axis=1) * 255).astype(np.uint8))
    image = Image.composite(Image.new("RGB", size, (0, 0, 0)), image, alpha)

    x = (width - (right - left)) // 2 - left
    y = height - margin - bottom
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).text((x, y), text, font=face, fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(max(2, text_h // 10)))
    image = Image.composite(Image.new("RGB", size, (0, 0, 0)), image, glow)
    ImageDraw.Draw(image).text((x, y), text, font=face, fill=(240, 236, 226))
    return image


def thumbnail_jpeg(image: Image.Image) -> bytes:
    """*image* as a JPEG under :data:`THUMBNAIL_MAX_BYTES`."""
    for quality in (92, 85, 75, 60):
        out = io.BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
        if out.tell() <= THUMBNAIL_MAX_BYTES:
            return out.getvalue()
    raise ValueError("workshop thumbnail does not fit in 1 MB even at quality 60")


def preview_png(image: Image.Image) -> bytes:
    """*image* as the package's PNG (the encoder every presentation image uses)."""
    from .images import encode_png

    rgb = image.convert("RGB")
    return encode_png(rgb.size[0], rgb.size[1], rgb.tobytes())

