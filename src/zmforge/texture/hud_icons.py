"""HUD images a map ships itself: perk icons drawn here, packed as ``image`` assets.

WHY.  The shipped perk widget draws whatever image asset is called the slot's
name (``PerkImage:setImage( RegisterImage( image ) )``, see
:class:`zmforge.script.perks.IconSlot`).  The two slots a custom perk may take,
``specialty_tombstone_zombies`` and ``specialty_divetonuke_zombies``, have no
image of that name in any stock assetlist on the mod tools install, so a perk that
lights one shows a blank square.  A map that packs its own image under the
name fills it.

HOW IT GETS INTO THE FASTFILE.  Three parts, the same three the wall art and
the loading screen use:

1. the PNG, written by ``Project.commit`` to
   ``texture_assets/zmforge_hud/<map>/<image>.png``;
2. a ``.gdt`` beside it (``<map>_hud.gdt``) with one ``image.gdf`` entry per
   PNG, and that ``.gdt`` registered into ``gdtdb/gdt.db`` -- by
   :func:`register` here in SQL (``gdtdb.exe`` does not run under Wine), which
   a build under Wine calls;
3. ``image,<name>`` in the map's ``.zone``, which
   :meth:`zmforge.blueprint.model.Blueprint.ship_hud_image` declares.

The entry is the stock ``t7_hud_zm_powerup_deathmachine`` image
(``texture_assets/images_ui_tu.gdt``, a zombies HUD power-up icon: semantic
``2d``, ``Linear4ch``, ``compressed``, no mips) verbatim, with the name and
``baseImage`` replaced.  Unlike ``black`` these names are on no stock
assetlist, so nothing on the install is overridden and nothing needs putting
back: the rows are new ``_entity`` rows keyed on this map's own ``.gdt`` path,
and a second registration replaces the first.

**Unverified in a link and in game**: that the linker converts these entries
and that the widget then draws them.  The route is the measured one for wall
art (``gdt.db`` row + zone line), but no link has confirmed it for HUD images.

    python -m zmforge.texture.hud_icons register <tools> <map>
    python -m zmforge.texture.hud_icons check <tools> <map> --since-file F
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from . import paint
from .gdt import _render

__all__ = [
    "ART",
    "ICON_SIZE",
    "HUD_DIR",
    "art_png",
    "base_image",
    "gdt_relative",
    "hud_gdt_document",
    "image_relative",
    "licence_plate_icon",
    "packed",
    "register",
    "ticket_icon",
]

_TEMPLATE = Path(__file__).parent / "templates" / "hud_image_entry.gdt.tmpl"

#: Square, power of two, transparent background, like a stock perk shader.
#: The stock source PNGs were not on hand to measure, so 128 is a choice,
#: and the widget scales to its own box.
ICON_SIZE = 128

#: Folder under ``texture_assets`` every map's HUD images live in, one
#: sub-folder per map so two maps on one install cannot overwrite each other.
HUD_DIR = "zmforge_hud"


def image_relative(map_name: str, image: str) -> str:
    """``texture_assets/zmforge_hud/<map>/<image>.png``, POSIX spelling."""
    return f"texture_assets/{HUD_DIR}/{map_name}/{image}.png"


def gdt_relative(map_name: str) -> str:
    """``texture_assets/zmforge_hud/<map>/<map>_hud.gdt``, POSIX spelling."""
    return f"texture_assets/{HUD_DIR}/{map_name}/{map_name}_hud.gdt"


def base_image(map_name: str, image: str) -> str:
    """``baseImage`` as the ``.gdt`` text spells it (doubled backslashes)."""
    return f"texture_assets\\\\{HUD_DIR}\\\\{map_name}\\\\{image}.png"


def hud_gdt_document(map_name: str, images: list[str] | tuple[str, ...]) -> str:
    """The map's HUD ``.gdt``: one stock-shaped ``image.gdf`` entry per name."""
    if not images:
        raise ValueError("no HUD images")
    if len(set(images)) != len(images):
        raise ValueError(f"duplicate HUD image names in {list(images)}")
    template = _TEMPLATE.read_text(encoding="utf-8")
    body = "".join(
        _render(template, {"image_name": name, "base_image": base_image(map_name, name)})
        for name in images
    )
    return "{\n" + body + "}\n"


# -- the art ----------------------------------------------------------------------

def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    scale = 4  # drawn large, downsampled once: smooth edges without a filter per shape
    size = ICON_SIZE * scale
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image), scale


def _badge(draw: ImageDraw.ImageDraw, size: int, fill, rim) -> None:
    """The round plate every stock perk icon sits on."""
    pad = size // 32
    draw.ellipse((pad, pad, size - pad, size - pad), fill=rim)
    inner = size // 14
    draw.ellipse((inner, inner, size - inner, size - inner), fill=fill)


def _centred(draw, box, text, face, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    x = (box[0] + box[2]) / 2 - (left + right) / 2
    y = (box[1] + box[3]) / 2 - (top + bottom) / 2
    draw.text((x, y), text, font=face, fill=fill)


def ticket_icon() -> Image.Image:
    """TAKE A NUMBER: a queue ticket, notched edges, a big number on it."""
    image, draw, scale = _canvas()
    size = image.width
    _badge(draw, size, fill=(38, 58, 112, 255), rim=(236, 228, 206, 255))
    # the ticket, tilted a touch by drawing it on its own layer
    ticket = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    t = ImageDraw.Draw(ticket)
    left, top, right, bottom = size * 0.20, size * 0.30, size * 0.80, size * 0.70
    t.rounded_rectangle((left, top, right, bottom), radius=size // 40, fill=(244, 236, 214, 255))
    notch = size * 0.06
    for x in (left, right):
        t.ellipse((x - notch, (top + bottom) / 2 - notch, x + notch, (top + bottom) / 2 + notch),
                  fill=(0, 0, 0, 0))
    stub = left + (right - left) * 0.26
    for y in range(int(top + size * 0.03), int(bottom - size * 0.02), size // 28):
        t.line((stub, y, stub, y + size // 60), fill=(164, 32, 28, 255), width=max(2, size // 160))
    _centred(t, (left, top, stub, bottom), "No", paint.font("sign", size // 14), (164, 32, 28, 255))
    _centred(t, (stub, top, right, bottom), "42", paint.font("sign", size // 4), (26, 24, 22, 255))
    ticket = ticket.rotate(-10, resample=Image.BICUBIC, center=(size / 2, size / 2))
    image.alpha_composite(ticket)
    return image.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def licence_plate_icon() -> Image.Image:
    """VEHICLE REGISTRATION FEE: a licence plate over a car's silhouette."""
    image, draw, scale = _canvas()
    size = image.width
    _badge(draw, size, fill=(28, 96, 62, 255), rim=(236, 228, 206, 255))
    body = (236, 228, 206, 255)
    # the car: roof, body, two wheels
    draw.rounded_rectangle((size * 0.30, size * 0.20, size * 0.70, size * 0.40), radius=size // 16, fill=body)
    draw.rounded_rectangle((size * 0.16, size * 0.34, size * 0.84, size * 0.52), radius=size // 20, fill=body)
    for cx in (0.30, 0.70):
        r = size * 0.075
        draw.ellipse((size * cx - r, size * 0.52 - r, size * cx + r, size * 0.52 + r), fill=(26, 24, 22, 255))
    # the plate, the thing the fee is for
    plate = (size * 0.18, size * 0.58, size * 0.82, size * 0.80)
    draw.rounded_rectangle(plate, radius=size // 36, fill=(246, 214, 70, 255),
                           outline=(26, 24, 22, 255), width=size // 64)
    _centred(draw, plate, "DMV 1", paint.font("sign", size // 7), (26, 24, 22, 255))
    return image.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


#: Named pieces of art a recipe may ask for by key (``CustomPerk.icon_art``).
ART: dict[str, Callable[[], Image.Image]] = {
    "ticket": ticket_icon,
    "licence_plate": licence_plate_icon,
}


def art_png(key: str) -> bytes:
    """The art called *key* as PNG bytes, or a refusal naming what there is."""
    try:
        draw = ART[key]
    except KeyError:
        raise KeyError(f"no HUD art called {key!r}; known: {', '.join(sorted(ART))}") from None
    buffer = io.BytesIO()
    draw().save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# -- registration -------------------------------------------------------------------

def register(tools: Path | str, map_name: str) -> str | None:
    """Put *map_name*'s HUD ``.gdt`` into ``gdt.db``; ``None`` if it has none."""
    from .gdtdb import register_gdt

    tools = Path(tools)
    gdt = tools / gdt_relative(map_name)
    if not gdt.is_file():
        return None
    result = register_gdt(
        gdt,
        tools / "gdtdb" / "gdt.db",
        tools_root=r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130",
        relative=gdt_relative(map_name).replace("/", "\\"),
    )
    return result.describe()


def packed(tools: Path | str, map_name: str, since: float) -> tuple[list[str], list[str]]:
    """Which of the map's HUD images this link's own assetlist lists.

    Returns ``(listed, missing)`` against the entries of the map's HUD
    ``.gdt``; both empty when the map has none.  Only an assetlist written
    after *since* counts (same rule as the loading-screen check).
    """
    from .gdtdb import parse_gdt

    tools = Path(tools)
    gdt = tools / gdt_relative(map_name)
    if not gdt.is_file():
        return [], []
    names = [e.name for e in parse_gdt(gdt.read_text(encoding="utf-8"))]
    listing = tools / "usermaps" / map_name / "zone_source" / "all" / "assetlist" / f"{map_name}.csv"
    rows: set[str] = set()
    if listing.is_file() and listing.stat().st_mtime >= since:
        rows = {line.strip() for line in listing.read_text(encoding="utf-8", errors="replace").splitlines()}
    listed = [n for n in names if f"image,{n}" in rows]
    return listed, [n for n in names if n not in listed]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hud_icons", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="register the map's HUD .gdt into gdt.db (no-op if none)")
    reg.add_argument("tools", type=Path)
    reg.add_argument("map")
    check = sub.add_parser("check", help="exit 1 unless the last link packed every HUD image")
    check.add_argument("tools", type=Path)
    check.add_argument("map")
    check.add_argument("--since-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "register":
        done = register(args.tools, args.map)
        print(f"== hud images: {done or 'none for ' + args.map}")
        return 0
    listed, missing = packed(args.tools, args.map, args.since_file.stat().st_mtime)
    if not listed and not missing:
        print(f"== hud images: none for {args.map}")
        return 0
    print(f"== hud images: packed {', '.join(listed) or 'none'}"
          + (f"; NOT packed: {', '.join(missing)}" if missing else ""))
    return 1 if missing else 0


_WIDE = Path(__file__).resolve().parents[3] / "assets-cache" / "sqlite-wide" / "libsqlite3.so.0"
_FLAG = "ZMFORGE_WIDE_SQLITE"


def _reexec_wide() -> None:
    """Re-run with the wide-column SQLite preloaded, as loadscreen_override does."""
    if os.environ.get(_FLAG):
        return
    if not _WIDE.exists():
        raise SystemExit(f"!! {_WIDE} is missing; build it once with scripts/asset-setup.py --build-sqlite")
    env = dict(os.environ)
    env["LD_PRELOAD"] = f"{_WIDE}:{env['LD_PRELOAD']}" if env.get("LD_PRELOAD") else str(_WIDE)
    env[_FLAG] = "1"
    os.execve(sys.executable, [sys.executable, "-m", __spec__.name, *sys.argv[1:]], env)  # type: ignore[union-attr]


if __name__ == "__main__":
    if sys.argv[1:2] == ["register"]:
        _reexec_wide()
    sys.exit(main())
