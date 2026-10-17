"""Put a map's loading screen into its fastfile, by overriding the ``black`` image.

WHY.  A usermap's full-screen loading screen draws the stock image asset
``black``; that is why ours were black.  The loose ``zone\\loadingimage.png``
every map ships is not read for it (measured in game: the preview card shows, the loading screen stays
black), and the mod tools' own template does nothing more.  The route the
community documents (Logical Edits, "Preview Image, Loading Screens, & Steam
Workshop Page", 2022) is to override ``black``, and it has three parts, all of
which the linker needs at once [measured, zm_blackprobe, three
runs; ``mapsource-format-reference.md`` 3.6]:

1. the ``black`` row in ``gdtdb/gdt.db`` points at the map's PNG as a 2D,
   uncompressed, streamable image;
2. ``image,black`` is commented out of the install's
   ``zone_source/all/assetlist/core_gfx.csv`` -- with the row live the map's
   own line is silently ignored;
3. ``image,black`` is a line in the map's own ``.zone``.

The linker then logs ``Converting image black`` and packs the image into the
map's ``.ff``.  Parts 1 and 2 change the *install*, and ``black`` is shared by
every map and by HUD elements, so this is SET, LINK, RESTORE: the converted
image lives on in the linked ``.ff`` after the install is put back (measured),
and the next map's link sees stock ``black`` again.

``gdtdb.exe`` does not run under Wine, so part 1 is done in SQL, the way
:mod:`zmforge.texture.gdtdb` registers wall art.  ``gdt.db`` needs a SQLite
built with a wide column limit; run as a script this module re-executes itself
with the one ``scripts/asset-setup.py --build-sqlite`` builds into
``assets-cache/sqlite-wide/``.

The row written is the stock ``img_t7_mod_loading`` definition (the tools'
own full-screen loading image: semantic ``2d``, ``Linear4ch``, no mips, clamped)
with the tutorial's two switches, ``compressionMethod uncompressed`` and
``streamable 1``, and ``baseImage`` pointing at a copy of the map's PNG.  Its
``_precalc_md5`` covers the PNG bytes, so a new picture is never mistaken for
an old conversion.

CRASH SAFETY.  Before anything is changed the originals are written to
``gdtdb/zmforge-black-override.json``.  :func:`restore` reads that file, puts
everything back and deletes it; :func:`apply` restores a leftover one first.
So a killed build leaves the install one ``restore`` away from stock, and the
next build does that restore itself.

    python -m zmforge.toolchain.loadscreen_override set <tools> <map> [--png P]
    python -m zmforge.toolchain.loadscreen_override restore <tools>
    python -m zmforge.toolchain.loadscreen_override check <tools> <map> --since-file F
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Iterator

__all__ = [
    "ASSET",
    "STATE_NAME",
    "apply",
    "restore",
    "override",
    "packed",
    "main",
]

ASSET = "black"
TEMPLATE = "img_t7_mod_loading"
STATE_NAME = "zmforge-black-override.json"
CORE_GFX = Path("zone_source/all/assetlist/core_gfx.csv")
LIVE_ROW = b"image,black"
DEAD_ROW = b"//image,black"
ZONE_LINE = "image,black"
#: Fields the tutorial sets in APE; everything else comes from TEMPLATE.
SWITCHES = {"compressionMethod": "uncompressed", "streamable": 1}
#: Columns that identify a row rather than describe the image.
_IDENTITY = ("PK_id", "_name", "_precalc_md5", "_derived_bits")

Connect = Callable[[Path], sqlite3.Connection]


def _connect(db: Path) -> sqlite3.Connection:
    from ..texture.gdtdb import connect

    return connect(db)


def _state_path(tools: Path) -> Path:
    return tools / "gdtdb" / STATE_NAME


def _image_row(connection: sqlite3.Connection, name: str) -> dict:
    """The ``image`` table row of the asset called *name*, as column -> value."""
    row = connection.execute(
        "select i.* from image i join _entity e on e.PK_id = i.PK_id where e.name = ?",
        (name,),
    )
    columns = [d[0] for d in row.description]
    values = row.fetchall()
    if len(values) != 1:
        raise RuntimeError(f"gdt.db has {len(values)} image rows named {name!r}, expected 1")
    return dict(zip(columns, values[0]))


def _encode(row: dict) -> dict:
    return {k: ({"hex": v.hex()} if isinstance(v, bytes) else v) for k, v in row.items()}


def _decode(row: dict) -> dict:
    return {k: (bytes.fromhex(v["hex"]) if isinstance(v, dict) else v) for k, v in row.items()}


def _write_row(connection: sqlite3.Connection, row: dict) -> None:
    pk = row["PK_id"]
    columns = [c for c in row if c != "PK_id"]
    assignments = ",".join(f'"{c}" = ?' for c in columns)
    connection.execute(
        f"update image set {assignments} where PK_id = ?", [row[c] for c in columns] + [pk]
    )


def base_image(map_name: str) -> str:
    r"""``baseImage`` for *map_name*'s copy, spelled as the stock rows are.

    The install stores these paths with doubled backslashes
    (``texture_assets\\t7_default\\default_black_0.tif``), so this does too.
    """
    return f"texture_assets\\\\zmforge_loadscreens\\\\{map_name}_loading.png"


def apply(tools: Path, map_name: str, png: Path | None = None, *, connect: Connect = _connect) -> list[str]:
    """Point ``black`` at *map_name*'s loading screen; returns what it did.

    *png* defaults to the loose ``usermaps/<map>/zone/loadingimage.png`` that
    ``zmforge generate`` writes.
    """
    tools = Path(tools)
    if _state_path(tools).exists():
        restore(tools, connect=connect)
    png = Path(png) if png else tools / "usermaps" / map_name / "zone" / "loadingimage.png"
    if not png.is_file():
        raise FileNotFoundError(f"no loading image at {png}")
    core_gfx = tools / CORE_GFX
    gfx = core_gfx.read_bytes()
    lines = gfx.split(b"\n")
    live = [i for i, line in enumerate(lines) if line.rstrip(b"\r") == LIVE_ROW]
    if len(live) != 1:
        raise RuntimeError(f"{core_gfx}: expected one live {LIVE_ROW.decode()} row, found {len(live)}")
    zone = tools / "usermaps" / map_name / "zone_source" / f"{map_name}.zone"
    zone_text = zone.read_text(encoding="utf-8")

    connection = connect(tools / "gdtdb" / "gdt.db")
    try:
        original = _image_row(connection, ASSET)
        template = _image_row(connection, TEMPLATE)
        # Everything is written down before anything is changed.
        _state_path(tools).write_text(json.dumps({
            "map": map_name,
            "row": _encode(original),
            "core_gfx_line": live[0],
            "zone": str(zone.relative_to(tools)),
            "zone_text": zone_text,
        }, indent=1), encoding="utf-8")

        copy = tools / "texture_assets" / "zmforge_loadscreens" / f"{map_name}_loading.png"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(png, copy)

        row = {k: v for k, v in template.items() if k not in _IDENTITY}
        row.update(SWITCHES)
        row["baseImage"] = base_image(map_name)
        digest = hashlib.md5(
            "".join(f"{k}{v}" for k, v in row.items()).encode("utf-8") + png.read_bytes()
        ).digest()
        row["PK_id"] = original["PK_id"]
        row["_precalc_md5"] = "-".join(f"{b:02X}" for b in digest)
        _write_row(connection, row)
        connection.commit()
    finally:
        connection.close()

    lines[live[0]] = lines[live[0]].replace(LIVE_ROW, DEAD_ROW, 1)
    core_gfx.write_bytes(b"\n".join(lines))
    done = [
        f"gdt.db: image '{ASSET}' -> {row['baseImage']} ({png.stat().st_size} bytes, "
        f"{', '.join(f'{k} {v}' for k, v in SWITCHES.items())})",
        f"{CORE_GFX}: line {live[0] + 1} commented out",
    ]
    if ZONE_LINE not in (line.strip() for line in zone_text.splitlines()):
        zone.write_text(zone_text.rstrip("\n") + f"\n{ZONE_LINE}\n", encoding="utf-8")
        done.append(f"{zone.name}: added {ZONE_LINE}")
    return done


def restore(tools: Path, *, connect: Connect = _connect) -> list[str]:
    """Put back what :func:`apply` changed.  A no-op when nothing is pending."""
    tools = Path(tools)
    state_file = _state_path(tools)
    if not state_file.exists():
        return []
    state = json.loads(state_file.read_text(encoding="utf-8"))
    connection = connect(tools / "gdtdb" / "gdt.db")
    try:
        _write_row(connection, _decode(state["row"]))
        connection.commit()
    finally:
        connection.close()
    core_gfx = tools / CORE_GFX
    lines = core_gfx.read_bytes().split(b"\n")
    index = state["core_gfx_line"]
    if lines[index].rstrip(b"\r") == DEAD_ROW:
        lines[index] = lines[index].replace(DEAD_ROW, LIVE_ROW, 1)
        core_gfx.write_bytes(b"\n".join(lines))
    zone = tools / state["zone"]
    if zone.exists():
        zone.write_text(state["zone_text"], encoding="utf-8")
    state_file.unlink()
    return [f"restored gdt.db '{ASSET}', {CORE_GFX} line {index + 1} and {zone.name}"]


@contextlib.contextmanager
def override(tools: Path, map_name: str, png: Path | None = None, *, connect: Connect = _connect) -> Iterator[list[str]]:
    """``apply`` for the duration of the block, ``restore`` however it ends."""
    try:
        yield apply(tools, map_name, png, connect=connect)
    finally:
        restore(tools, connect=connect)


def packed(tools: Path, map_name: str, since: float) -> str | None:
    """Evidence that the last link packed the map's ``black``, or None.

    The linker's own output assetlist, ``usermaps/<map>/zone_source/all/
    assetlist/<map>.csv``, lists ``image,black`` only when the override was in
    place: with the stock ``core_gfx.csv`` row live the map's zone line is
    silently ignored and the row is absent (control run).
    That holds whether the linker converted the image or reused a cached
    ``share/assetconvert/image/v29/black_*.iwi`` -- a cache hit prints no
    ``Converting image black`` line, so the log line alone would refuse every
    rebuild of an unchanged picture.  *since* (epoch seconds) is when this
    link started, so an assetlist left by an earlier link does not count.
    """
    listing = Path(tools) / "usermaps" / map_name / "zone_source" / "all" / "assetlist" / f"{map_name}.csv"
    if not listing.is_file() or listing.stat().st_mtime < since:
        return None
    rows = {line.strip() for line in listing.read_text(encoding="utf-8", errors="replace").splitlines()}
    if ZONE_LINE not in rows:
        return None
    return f"{listing.name} lists {ZONE_LINE} (written by this link)"


# -- command line ---------------------------------------------------------------

_WIDE = Path(__file__).resolve().parents[3] / "assets-cache" / "sqlite-wide" / "libsqlite3.so.0"
_FLAG = "ZMFORGE_WIDE_SQLITE"


def _reexec_wide() -> None:
    """Re-run this module with the wide-column SQLite preloaded, once."""
    if os.environ.get(_FLAG):
        return
    if not _WIDE.exists():
        raise SystemExit(f"!! {_WIDE} is missing; build it once with scripts/asset-setup.py --build-sqlite")
    env = dict(os.environ)
    env["LD_PRELOAD"] = f"{_WIDE}:{env['LD_PRELOAD']}" if env.get("LD_PRELOAD") else str(_WIDE)
    env[_FLAG] = "1"
    os.execve(sys.executable, [sys.executable, "-m", __spec__.name, *sys.argv[1:]], env)  # type: ignore[union-attr]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loadscreen_override", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    set_ = sub.add_parser("set")
    set_.add_argument("tools", type=Path)
    set_.add_argument("map")
    set_.add_argument("--png", type=Path, default=None)
    back = sub.add_parser("restore")
    back.add_argument("tools", type=Path)
    check = sub.add_parser("check", help="exit 1 unless the last link packed black")
    check.add_argument("tools", type=Path)
    check.add_argument("map")
    check.add_argument("--since-file", type=Path, required=True,
                       help="a file touched when the link started")
    args = parser.parse_args(argv)
    if args.command == "check":
        found = packed(args.tools, args.map, args.since_file.stat().st_mtime)
        print(f"== loading screen: {found or 'NOT packed: the assetlist has no image,black from this link'}")
        return 0 if found else 1
    if args.command == "set":
        lines = apply(args.tools, args.map, args.png)
    else:
        lines = restore(args.tools) or ["nothing to restore"]
    for line in lines:
        print(f"== loading screen: {line}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] != ["check"]:
        _reexec_wide()
    sys.exit(main())
