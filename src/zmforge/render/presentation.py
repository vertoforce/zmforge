"""A map's three presentation images: loading screen, preview card, Workshop thumbnail.

The rule (``docs/map-principles.md``, "Presentation images"): the loading
screen is the map's own top-down plan (:func:`zmforge.emit.planview.render_plan`)
framed to fill the screen, plus the title; the preview card and the Workshop
thumbnail are an in-map photograph (a ``zmforge render --baked`` shot, so the
map's baked lighting is in it) plus the title.  Never a generated
illustration, figure or clip-art.

``zmforge loadscreen <recipe>`` makes all three:

1. picks a few candidate cameras (:func:`candidate_views`): a per-recipe
   override from :data:`CAMERAS` or ``--camera``, the recipe's curated hero
   (:mod:`.hero`), then the most prop-dense, best-lit rooms, each looked at
   down its long axis toward its crowded half and toward its prop cluster,
   from eye height, tipped slightly down;
2. photographs them in one Radiant session with the last local bake
   (``render_recipe(..., baked=True, views_for=...)``; the render waits for
   free VRAM and holds the machine-wide Radiant lock);
3. scores them (:func:`zmforge.workshop._score`: luminance spread plus
   edges, zero for a dark frame) and keeps the best, or ``--pick``;
4. post-processes in Pillow (:func:`finish_photo`): exposure stretch, a gentle
   grade, a depth-free haze when the recipe has fog (Radiant cannot draw fog), a vignette, the title;
5. writes ``loadingimage.png`` (1920 x 1080), ``previewimage.png``
   (600 x 340) and ``workshop_thumbnail.jpg`` (512 x 512) into
   ``build-out/presentation/<map>/``, where ``zmforge generate`` picks them up
   (:func:`presentation_file`).

The post-processing is pure (image in, image out) and tested in
``tests/test_presentation_photos.py``.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .cameras import EYE_PITCH, View, _yaw

REPO = Path(__file__).resolve().parents[3]
#: Where finished images wait for ``zmforge generate``; one folder per map.
PRESENTATION_ROOT = REPO / "build-out" / "presentation"
LOADING_NAME = "loadingimage.png"
PREVIEW_NAME = "previewimage.png"
THUMBNAIL_NAME = "workshop_thumbnail.jpg"
LOADING_SIZE = (1920, 1080)
PREVIEW_SIZE = (600, 340)
THUMBNAIL_SIZE = (512, 512)

#: Per-recipe camera overrides, best first, for when the automatic pick is
#: poor.  ``View(room, name, x, y, z, pitch, yaw)`` in Radiant's terms
#: (pitch positive looks down, yaw ccw from +x).  Empty: every map's
#: automatic pick was fine when this was written.
CAMERAS: dict[str, tuple[View, ...]] = {}

#: Per-recipe candidate to ship when ``--pick auto``, by view name.  Without
#: an entry, auto ships the recipe's curated ``hero`` camera (a
#: :data:`zmforge.render.hero.HEROES` entry) when it has one and it is not dark, else the best-scoring candidate: the score measures
#: contrast, not theme, and on the first maps it preferred a bare side room
#: over the curated set piece every time.
PICKS: dict[str, str] = {
}

_LIGHT_WORDS = ("light", "lamp", "lantern", "candle", "bulb", "torch", "fire", "neon", "sign")


def presentation_root() -> Path:
    """:data:`PRESENTATION_ROOT`, or ``$ZMFORGE_PRESENTATION_ROOT`` (tests)."""
    return Path(os.environ.get("ZMFORGE_PRESENTATION_ROOT") or PRESENTATION_ROOT)


def presentation_file(name: str, filename: str) -> Path | None:
    """The finished *filename* of map *name*, or None when there is none yet."""
    path = presentation_root() / name / filename
    return path if path.is_file() and path.stat().st_size > 0 else None


# ----------------------------------------------------------------------
# Cameras
# ----------------------------------------------------------------------
def _room_lights_and_props(bp, area) -> tuple[list[tuple[float, float]], int]:
    """Prop positions inside *area* and how many of them (or elements) are lights."""
    props: list[tuple[float, float]] = []
    lights = 0
    for element in bp.elements():
        eid = str(getattr(element, "id", "") or "").lower()
        origin = getattr(element, "origin", None)
        if origin is not None and any(w in eid for w in _LIGHT_WORDS):
            try:
                if area.holds(origin.x, origin.y):
                    lights += 1
            except AttributeError:
                pass
        for prop in getattr(element, "props", None) or []:
            if not area.holds(prop.origin.x, prop.origin.y):
                continue
            props.append((prop.origin.x, prop.origin.y))
            model = str(getattr(prop, "model", "") or "").lower()
            if any(w in model for w in _LIGHT_WORDS):
                lights += 1
    return props, lights


def room_scores(bp) -> list[tuple[float, object, list[tuple[float, float]]]]:
    """``(score, area, prop positions)`` per room, best set piece first.

    Prop density (props per 100 x 100 units) weighted by the log of the
    floor area, so a crowded cupboard does not beat a crowded hall, plus
    the lights in it (a dark room makes a dark picture).
    """
    from ..review.facts import _areas

    out = []
    for area in _areas(bp):
        floor = max((area.x1 - area.x0) * (area.y1 - area.y0), 1.0)
        props, lights = _room_lights_and_props(bp, area)
        density = len(props) / (floor / 10_000.0)
        score = density * math.log1p(floor / 10_000.0) + 1.5 * min(lights, 12)
        out.append((score, area, props))
    out.sort(key=lambda t: (-t[0], t[1].key))
    return out


def _long_axis_target(area, props) -> tuple[tuple[float, float], float]:
    """The far end of *area*'s long axis on its crowded side, and the bearing back."""
    cx, cy = (area.x0 + area.x1) / 2, (area.y0 + area.y1) / 2
    if (area.x1 - area.x0) >= (area.y1 - area.y0):
        high = sum(1 for px, _ in props if px > cx) >= sum(1 for px, _ in props if px < cx)
        tx = area.x1 - 48 if high else area.x0 + 48
        return (tx, cy), (180.0 if high else 0.0)
    high = sum(1 for _, py in props if py > cy) >= sum(1 for _, py in props if py < cy)
    ty = area.y1 - 48 if high else area.y0 + 48
    return (cx, ty), (270.0 if high else 90.0)


def _eye_view(bp, area, stand: tuple[float, float], target: tuple[float, float],
              name: str, pitch: float = EYE_PITCH) -> View:
    from .hero import _eye, _terrains

    x, y = stand
    z = _eye(_terrains(bp), area, x, y)
    return View(area.key, name, round(x), round(y), round(z), pitch, _yaw(x, y, *target))


def auto_views(bp, rooms: int = 3) -> list[View]:
    """Up to two eye-height views in each of the *rooms* best set-piece rooms."""
    from .hero import HeroSpec, _search

    views: list[View] = []
    for score, area, props in room_scores(bp)[:rooms]:
        diag = math.hypot(area.x1 - area.x0, area.y1 - area.y0)
        floor_eye = area.floor_z + 40.0
        # Down the long axis toward the crowded half.
        (tx, ty), bearing = _long_axis_target(area, props)
        spec = HeroSpec(room=area.key, distance=(0.45 * diag, 1.0 * diag),
                        bearing=bearing, spread=35.0, target_clear=64.0)
        try:
            stand = _search(bp, area, spec, (tx, ty, floor_eye))
            views.append(_eye_view(bp, area, stand, (tx, ty), f"ls{len(views)}"))
        except LookupError:
            pass
        # At the prop cluster, from wherever gives the longest clear view.
        if props:
            px = sum(p[0] for p in props) / len(props)
            py = sum(p[1] for p in props) / len(props)
            spec = HeroSpec(room=area.key, distance=(0.3 * diag, 0.8 * diag),
                            target_clear=96.0)
            try:
                stand = _search(bp, area, spec, (px, py, floor_eye))
                views.append(_eye_view(bp, area, stand, (px, py), f"ls{len(views)}"))
            except LookupError:
                pass
    return views


def _far_apart(view: View, taken: Sequence[View]) -> bool:
    return all(math.hypot(view.x - t.x, view.y - t.y) > 96 or abs(view.yaw - t.yaw) > 25
               for t in taken)


def candidate_views(recipe: str, bp, *, count: int = 5,
                    extra: Sequence[View] = ()) -> list[View]:
    """Override cameras, then the curated hero, then :func:`auto_views`; at most *count*."""
    from .hero import hero_view

    out: list[View] = []
    for i, view in enumerate(list(extra) + list(CAMERAS.get(recipe, ()))):
        out.append(View(view.room, f"ov{i}", view.x, view.y, view.z, view.pitch, view.yaw))
    try:
        hero = hero_view(recipe, bp)
        out.append(View(hero.room, "hero", hero.x, hero.y, hero.z, hero.pitch, hero.yaw))
    except (KeyError, LookupError) as exc:
        print(f"!! hero camera: {exc}", file=sys.stderr)
    for view in auto_views(bp):
        if len(out) >= count:
            break
        if _far_apart(view, out):
            out.append(view)
    return out[:count]


def parse_camera(text: str, room: str = "override") -> View:
    """``"X Y Z PITCH YAW"`` (Radiant's Jump Camera To order) as a View."""
    parts = [float(p) for p in text.replace(",", " ").split()]
    if len(parts) != 5:
        raise ValueError(f"--camera wants 'X Y Z PITCH YAW', got {text!r}")
    x, y, z, pitch, yaw = parts
    return View(room, "cli", x, y, z, pitch, yaw)


def has_fog(bp) -> bool:
    """True when the recipe asks for fog of either kind (world or lit)."""
    from ..blueprint.elements import Enclosure

    return any(getattr(e, "fog", None) or getattr(e, "lit_fog", None)
               for e in bp.elements(Enclosure))


# ----------------------------------------------------------------------
# Post-processing (pure: image in, image out)
# ----------------------------------------------------------------------
def _arr(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _img(a: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGB")


def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def expose(image: Image.Image, *, target: float = 0.36, max_gain: float = 2.4,
           knee: float = 0.8) -> Image.Image:
    """Lift a dim render toward mean luminance *target*, highlights rolled off.

    Radiant's baked view is dim and flat next to the game (no exposure, no
    bloom).  The black point drops by at most 0.04, the gain is capped at
    *max_gain* (so a truly dark room stays dark) and never darkens, and
    values above *knee* roll off smoothly instead of clipping, so lamps
    keep their shape.
    """
    a = _arr(image)
    lo = min(float(np.percentile(_luma(a), 0.5)), 0.04)
    a = np.clip(a - lo, 0.0, None) / (1.0 - lo)
    mean = float(_luma(a).mean())
    gain = min(max_gain, max(1.0, target / max(mean, 1e-3)))
    a = a * gain
    room = 1.0 - knee
    a = np.where(a < knee, a, knee + room * np.tanh((a - knee) / room))
    return _img(a)


def grade(image: Image.Image, *, contrast: float = 0.18, saturation: float = 1.08,
          warm: float = 0.035) -> Image.Image:
    """A gentle S-curve, a little saturation, warm highlights and cool shadows."""
    a = _arr(image)
    s = a * a * (3.0 - 2.0 * a)                     # smoothstep S-curve
    a = a + contrast * (s - a)
    y = _luma(a)[..., None]
    a = y + (a - y) * saturation
    tint = (y - 0.5) * 2.0                          # -1 shadows .. +1 highlights
    a = a + warm * tint * np.array([1.0, 0.35, -0.8], dtype=np.float32)
    return _img(a)


def haze(image: Image.Image, *, strength: float = 0.28, horizon: float = 0.45,
         colour: tuple[int, int, int] | None = None) -> Image.Image:
    """A depth-free fake fog: a veil strongest at the horizon, gone at the foot.

    Radiant draws no fog, so a foggy map's photograph would otherwise look
    clearer than the game.  With no depth buffer the veil follows height in
    the frame: full *strength* at *horizon* (fraction of the height), easing
    to 60% at the top edge and to nothing at the bottom.  The colour
    defaults to the picture's own mid-tones, desaturated, so it never
    tints a night scene blue by itself.  Bright pixels are veiled less, so
    lamps still glow through.
    """
    a = _arr(image)
    h = a.shape[0]
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)
    above = 0.6 + 0.4 * np.clip(t / max(horizon, 1e-3), 0, 1)
    below = np.clip(1.0 - (t - horizon) / max(1.0 - horizon, 1e-3), 0, 1) ** 1.6
    veil = np.where(t <= horizon, above, below) * strength
    if colour is None:
        y = _luma(a)
        mid = a[(y > np.percentile(y, 30)) & (y < np.percentile(y, 80))]
        base = mid.mean(axis=0) if mid.size else np.array([0.4, 0.4, 0.4], np.float32)
        grey = float(base.mean())
        fog = (0.6 * grey + 0.4 * base) * 1.15 + 0.04
    else:
        fog = np.array(colour, dtype=np.float32) / 255.0
    alpha = veil[:, None, None] * (1.0 - 0.6 * _luma(a)[..., None])
    return _img(a * (1.0 - alpha) + fog[None, None, :] * alpha)


def vignette(image: Image.Image, *, strength: float = 0.35, softness: float = 1.8) -> Image.Image:
    """Darken toward the corners: 1 - strength * r^softness (r = 1 at a corner)."""
    a = _arr(image)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - (w - 1) / 2) / (w / 2), (yy - (h - 1) / 2) / (h / 2)) / math.sqrt(2)
    return _img(a * (1.0 - strength * r ** softness)[..., None])


def crop_to(image: Image.Image, size: tuple[int, int], *, focus: float = 0.5,
            vfocus: float = 0.5) -> Image.Image:
    """Cover-crop *image* to *size*'s aspect (focus/vfocus place the window), then resize."""
    width, height = image.size
    want = size[0] / size[1]
    if width / height > want:
        new_w = round(height * want)
        left = round((width - new_w) * min(max(focus, 0.0), 1.0))
        box = (left, 0, left + new_w, height)
    else:
        new_h = round(width / want)
        top = round((height - new_h) * min(max(vfocus, 0.0), 1.0))
        box = (0, top, width, top + new_h)
    out = image.crop(box)
    if out.size != size:
        out = out.resize(size, Image.LANCZOS)
        if size[0] > box[2] - box[0]:               # upscaled: sharpen a little back
            out = out.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=2))
    return out


def title_text(image: Image.Image, title: str, *, tagline: str | None = None,
               align: str = "center", scale: float = 1.0) -> Image.Image:
    """*title* (upper case, the ``sign`` face) over a dark band fading up from the foot."""
    from ..texture import paint

    image = image.convert("RGB").copy()
    width, height = image.size
    margin = max(8, width // 24)
    text = title.upper()
    face = paint.fit_font("sign", text, int((width - 2 * margin) * (0.9 if align == "center" else 0.7)),
                          ceiling=max(24, int(height / 7 * scale)))
    left, top, right, bottom = face.getbbox(text)
    text_h = bottom - top
    sub = None
    sub_h = 0
    if tagline:
        sub = paint.fit_font("sign", tagline, width - 2 * margin, ceiling=max(12, text_h // 3))
        sl, st, sr, sb = sub.getbbox(tagline)
        sub_h = (sb - st) + text_h // 3
    band = int((text_h + sub_h) * 2.4) + margin
    shade = np.zeros((height,), dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, min(band, height), dtype=np.float32) ** 1.5
    shade[height - len(ramp):] = ramp * 0.78
    a = _arr(image) * (1.0 - shade[:, None, None])
    image = _img(a)
    x = (width - (right - left)) // 2 - left if align == "center" else margin - left
    y = height - margin - sub_h - bottom
    glow = Image.new("L", image.size, 0)
    ImageDraw.Draw(glow).text((x, y), text, font=face, fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(max(2, text_h // 8)))
    image = Image.composite(Image.new("RGB", image.size, (0, 0, 0)), image,
                            glow.point(lambda v: int(v * 0.8)))
    draw = ImageDraw.Draw(image)
    draw.text((x, y), text, font=face, fill=(240, 236, 226))
    if sub is not None:
        sl, st, sr, sb = sub.getbbox(tagline)
        sx = (width - (sr - sl)) // 2 - sl if align == "center" else margin - sl
        draw.text((sx, height - margin - sb), tagline, font=sub, fill=(196, 190, 178))
    return image


def finish_photo(source: Image.Image, size: tuple[int, int], title: str, *,
                 fog: bool = False, focus: float = 0.5, tagline: str | None = None) -> Image.Image:
    """A render as a titled card: expose, grade, (haze), crop, vignette, title."""
    image = grade(expose(source.convert("RGB")))
    if fog:
        image = haze(image)
    image = crop_to(image, size, focus=focus, vfocus=0.45)
    image = vignette(image, strength=0.32)
    return title_text(image, title, tagline=tagline)


def _drawn(image: Image.Image, bg: tuple[int, int, int]) -> np.ndarray:
    """Pixels that differ from the background colour *bg*."""
    a = np.asarray(image.convert("RGB"), dtype=np.int16)
    return np.abs(a - np.array(bg, dtype=np.int16)).sum(axis=2) > 6


def trim(image: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    """*image* cropped to the box of everything not *bg*."""
    drawn = _drawn(image, bg)
    rows, cols = np.where(drawn.any(axis=1))[0], np.where(drawn.any(axis=0))[0]
    if not rows.size:
        return image
    return image.crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))


def collapse_gaps(image: Image.Image, bg: tuple[int, int, int], *,
                  max_gap: float = 0.05) -> Image.Image:
    """Close up empty bands wider than *max_gap* of the image, in both axes.

    A map whose parts sit far apart (a corridor block thousands of units
    from the main building) would otherwise be drawn tiny across a wide
    black gulf.  Only fully empty columns/rows are removed, so every shape
    keeps its own size and nothing overlaps; only the spacing between
    disconnected parts is shortened.
    """
    a = np.asarray(image.convert("RGB"))
    for axis in (0, 1):                          # 0: columns (x), 1: rows (y)
        drawn = _drawn(Image.fromarray(a), bg)
        used = drawn.any(axis=0) if axis == 0 else drawn.any(axis=1)
        length = used.size
        limit = max(4, int(max_gap * length))
        keep = np.ones(length, dtype=bool)
        i = 0
        while i < length:
            if used[i]:
                i += 1
                continue
            j = i
            while j < length and not used[j]:
                j += 1
            if j - i > limit:
                start = i + limit // 2
                keep[start:start + (j - i - limit)] = False
            i = j
        a = a[:, keep] if axis == 0 else a[keep, :]
    return Image.fromarray(a)


def light_plan(plan: Image.Image, bp, bg: tuple[int, int, int], *, ambient: float = 0.3,
               peak: float = 1.7, glow: float = 16.0) -> Image.Image:
    """*plan* (a caption-free :func:`render_plan` drawing) shaded by the map's
    own lamps: each always-on lamp lights a pool of its colour and radius,
    everything else sits at *ambient*.  Exploder lamps (switched by script
    for an event, e.g. the cemetery wisps) are left out, as in the photos
    (:func:`zmforge.render.radiant.without_script_lights`).  Only drawn
    pixels change; the background stays the background.

    WHY: the plan loading screens read well but looked
    flat and unlit; this keeps the plan and gives it the map's lighting.
    """
    from ..blueprint.elements import Lamp
    from ..emit.planview import _footprints, _Frame
    from ..spatial import Span

    w, h = plan.size
    unit = max(1, round(min(w, h) / 180.0))
    pad = unit * 6
    boxes = _footprints(bp)
    if not boxes:
        return plan
    frame = _Frame(Span.hull_of(boxes).grown(64.0), (pad, pad, w - pad, h - pad))
    step = 6
    gw, gh = (w + step - 1) // step, (h + step - 1) // step
    gx = (np.arange(gw) * step + step / 2)[None, :]
    gy = (np.arange(gh) * step + step / 2)[:, None]
    light = np.zeros((gh, gw, 3), dtype=np.float32)
    for lamp in bp.elements(Lamp):
        if getattr(lamp, "exploder", None) or lamp.position is None:
            continue
        r = max(1.0, lamp.radius * frame.scale)
        px, py = frame.x(lamp.position.x), frame.y(lamp.position.y)
        x0, x1 = max(0, int((px - r) // step)), min(gw, int((px + r) // step) + 1)
        y0, y1 = max(0, int((py - r) // step)), min(gh, int((py + r) // step) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        d = np.hypot(gx[:, x0:x1] - px, gy[y0:y1, :] - py) / r
        fall = np.clip(1.0 - d, 0.0, 1.0) ** 2.5
        light[y0:y1, x0:x1] += fall[..., None] * np.array(lamp.colour, dtype=np.float32) * 0.45
    tone = 1.0 - np.exp(-light)                  # many overlapping lamps saturate gently
    tone = np.asarray(Image.fromarray((tone * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR),
                      dtype=np.float32) / 255
    a = np.asarray(plan, dtype=np.float32)
    drawn = _drawn(plan, bg)[..., None]
    lit_px = a * (ambient + (peak - ambient) * tone) + tone * glow
    out = np.where(drawn, np.clip(lit_px, 0, 255), a)
    # keep every drawn pixel distinguishable from the background (trim, gaps)
    keep = np.abs(out - np.array(bg, dtype=np.float32)).sum(axis=2, keepdims=True) > 9
    out = np.where(drawn & ~keep, np.array(bg, dtype=np.float32) + 4, out)
    return Image.fromarray(out.astype(np.uint8))


def plan_loading_screen(bp, title: str, *, size: tuple[int, int] = LOADING_SIZE,
                        tagline: str | None = None, lit: bool = True) -> Image.Image:
    """The map's plan (:func:`render_plan`), trimmed, fitted to fill *size*, titled.

    The plan is drawn caption-free at the aspect of the map's own footprint,
    trimmed to what was drawn, wide empty gaps between disconnected parts
    closed up (:func:`collapse_gaps`), turned a quarter when the map is
    taller than wide (the north arrow turns with it), and scaled to
    the largest size that fits above the title, over a faint grid and a
    vignette.
    """
    from ..emit.planview import PLAN_PALETTE, render_plan

    width, height = size
    title_room = int(height * 0.17)
    area_w, area_h = width - 2 * int(width * 0.03), height - title_room - int(height * 0.04)
    plan = Image.open(io.BytesIO(render_plan(bp, width=area_w * 3, height=area_h * 3,
                                             caption=False).png())).convert("RGB")
    bg = PLAN_PALETTE.background
    if lit:
        plan = light_plan(plan, bp, bg)
    plan = collapse_gaps(trim(plan, bg), bg, max_gap=0.05)
    if plan.height > plan.width * 1.15:
        plan = plan.rotate(90, expand=True, fillcolor=bg)
    k = min(area_w / plan.width, area_h / plan.height)
    plan = plan.resize((max(1, round(plan.width * k)), max(1, round(plan.height * k))),
                       Image.LANCZOS)
    canvas = Image.new("RGB", size, PLAN_PALETTE.background)
    grid = ImageDraw.Draw(canvas)
    line = tuple(min(255, c + 7) for c in PLAN_PALETTE.background)
    step = max(24, width // 40)
    for gx in range(0, width, step):
        grid.line([(gx, 0), (gx, height)], fill=line)
    for gy in range(0, height, step):
        grid.line([(0, gy), (width, gy)], fill=line)
    # Paste only what the plan drew, so the grid shows through its background.
    mask = Image.fromarray((_drawn(plan, bg) * 255).astype(np.uint8), "L")
    mask = mask.filter(ImageFilter.MaxFilter(3))
    ox = (width - plan.width) // 2
    oy = int(height * 0.04) + (area_h - plan.height) // 2
    canvas.paste(plan, (ox, oy), mask)
    canvas = vignette(canvas, strength=0.45)
    return title_text(canvas, title, tagline=tagline, scale=0.85)


def thumbnail_jpeg(image: Image.Image) -> bytes:
    from ..workshop import thumbnail_jpeg as encode

    return encode(image)


def png_bytes(image: Image.Image) -> bytes:
    from ..images import encode_png

    rgb = image.convert("RGB")
    return encode_png(rgb.size[0], rgb.size[1], rgb.tobytes())


# ----------------------------------------------------------------------
# The command
# ----------------------------------------------------------------------
def add_arguments(parser: argparse.ArgumentParser, recipes) -> None:
    parser.add_argument("recipe", choices=sorted(recipes))
    parser.add_argument("--name", default=None, help="map name (default zm_<recipe>)")
    parser.add_argument("--candidates", type=int, default=5,
                        help="how many cameras to photograph (default 5)")
    parser.add_argument("--camera", action="append", default=[], metavar="'X Y Z PITCH YAW'",
                        help="an extra camera, tried first (repeatable)")
    parser.add_argument("--pick", default="auto",
                        help="which candidate to ship: 'auto' (best score) or its view "
                             "name (hero, ls0, ov0, cli...)")
    parser.add_argument("--from-run", default=None, metavar="DIR",
                        help="skip Radiant: post-process the candidates of an earlier run")
    parser.add_argument("--work", default=None,
                        help="candidate renders go here (default: the per-user cache, "
                             "e.g. ~/.cache/zmforge/loadscreens/<map>/<time>; "
                             "$ZMFORGE_CACHE_DIR moves it)")
    parser.add_argument("--out", default=None,
                        help="finished images go here (default build-out/presentation/<map>)")
    parser.add_argument("--tagline", default=None, help="a short line under the title")
    parser.add_argument("--fog", choices=("auto", "on", "off"), default="auto",
                        help="fake haze on the photos (auto: when the recipe has fog)")
    parser.add_argument("--list", action="store_true",
                        help="print the candidate cameras and stop (no Radiant)")


def _candidates_from(run: Path) -> list[tuple[View, Path]]:
    manifest = json.loads((run / "views.json").read_text(encoding="utf-8"))
    views = {View(**v).slug: View(**v) for v in manifest.get("views", [])}
    out = []
    for paths in manifest.get("shots", {}).values():
        for raw in paths:
            path = Path(raw)
            if path.is_file() and path.stem in views:
                out.append((views[path.stem], path))
    return out


def make(recipe: str, *, name: str | None = None, candidates: int = 5,
         cameras: Sequence[str] = (), pick: str = "auto", from_run: str | None = None,
         work: str | None = None, out: str | None = None, tagline: str | None = None,
         fog: str = "auto", list_only: bool = False, log=lambda s: None) -> dict:
    from ..review import facts as measure
    from ..workshop import _score
    from .run import render_recipe

    name = name or measure.default_map_name(recipe)
    extra = [parse_camera(c) for c in cameras]
    if work:
        work_dir = Path(work)
    else:
        from ..fonts import user_cache_dir

        work_dir = user_cache_dir("loadscreens") / name / time.strftime("%Y%m%d-%H%M%S")
    chosen_views: list[View] = []
    held: dict = {}

    def views_for(bp):
        held["bp"] = bp
        chosen_views[:] = candidate_views(recipe, bp, count=candidates, extra=extra)
        return chosen_views

    if from_run:
        run = Path(from_run)
        held["bp"] = measure.generate(recipe, name, scratch=work_dir / "gen", keep=False).blueprint
    else:
        manifest = render_recipe(recipe, name=name, out=work_dir, baked=True, dry=list_only,
                                 views_for=views_for, log=log)
        run = Path(manifest["out"])
        if list_only:
            return {"views": [v.as_dict() for v in chosen_views], "out": str(run)}
    shots = _candidates_from(run)
    if not shots:
        raise SystemExit(f"no candidate pictures in {run}")
    scored = sorted(((_score(p), v, p) for v, p in shots), key=lambda t: -t[0])
    if pick == "auto":
        from .hero import spec_for

        curated = spec_for(recipe) is not None
        pick = PICKS.get(recipe) or next(
            (v.name for sc, v, _ in scored if curated and v.name == "hero" and sc > 0),
            "auto")
    if pick == "auto":
        best = scored[0]
    else:
        match = [s for s in scored if s[1].name == pick or s[2].stem == pick]
        if not match:
            raise SystemExit(f"--pick {pick}: no such candidate "
                             f"({', '.join(s[1].name for s in scored)})")
        best = match[0]

    from ..emit.manifest import display_title

    bp = held["bp"]
    title = display_title(name, getattr(bp, "title", None))
    foggy = has_fog(bp) if fog == "auto" else fog == "on"
    dest = Path(out) if out else presentation_root() / name
    dest.mkdir(parents=True, exist_ok=True)
    with Image.open(best[2]) as opened:
        photo = opened.convert("RGB")
    loading = plan_loading_screen(bp, title, tagline=tagline)
    preview = finish_photo(photo, PREVIEW_SIZE, title, fog=foggy, tagline=None)
    thumb = finish_photo(photo, THUMBNAIL_SIZE, title, fog=foggy)
    (dest / LOADING_NAME).write_bytes(png_bytes(loading))
    (dest / PREVIEW_NAME).write_bytes(png_bytes(preview))
    (dest / THUMBNAIL_NAME).write_bytes(thumbnail_jpeg(thumb))
    # Every candidate finished the same way, for picking by eye.
    looks = work_dir / "cards"
    looks.mkdir(parents=True, exist_ok=True)
    for score, view, path in scored:
        with Image.open(path) as opened:
            card = finish_photo(opened.convert("RGB"), (1024, 576), title, fog=foggy)
        card.save(looks / f"{view.name}.jpg", quality=88)
    loading.resize((1024, 576), Image.LANCZOS).save(looks / "loadingimage.jpg", quality=88)
    report = {
        "map": name, "recipe": recipe, "title": title, "fog": foggy, "run": str(run),
        "picked": best[1].name, "picked_path": str(best[2]),
        "candidates": [{"view": v.as_dict(), "score": round(s, 1), "path": str(p)}
                       for s, v, p in scored],
        "written": [str(dest / n) for n in (LOADING_NAME, PREVIEW_NAME, THUMBNAIL_NAME)],
        "cards": str(looks),
    }
    (dest / "presentation.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(args: argparse.Namespace) -> int:
    log = lambda s: print(s, file=sys.stderr, flush=True)  # noqa: E731
    report = make(args.recipe, name=args.name, candidates=args.candidates, cameras=args.camera,
                  pick=args.pick, from_run=args.from_run, work=args.work, out=args.out,
                  tagline=args.tagline, fog=args.fog, list_only=args.list, log=log)
    if args.list:
        for v in report["views"]:
            print(f"{v['room']:<16} {v['name']:<6} {View(**v).radiant_text()}")
        return 0
    for c in report["candidates"]:
        mark = "*" if c["view"]["name"] == report["picked"] else " "
        print(f"{mark} {c['view']['name']:<6} {c['score']:>6}  {c['view']['room']}")
    for path in report["written"]:
        print(f"wrote {path}")
    print(f"cards: {report['cards']}")
    return 0
