"""Install a staging tree's custom wall art into a local copy of the mod tools.

So a map carrying wall art builds under Wine.  Staging a map's wall art
writes two files beside the map:

* ``wall-art-textures.zip``: every texture set's ``.tif`` tiles under
  ``<set>/`` and each set's ``<set>_tex.gdt`` at the top level, laid out
  relative to ``texture_assets``;
* ``wall-art-vars.json``: what the archive carries (``texture_sets``, and
  ``sets[].gdt_file``).

On Windows the archive is unpacked into ``texture_assets``, the ``i_zmf_*``
converted-image cache dropped and ``gdtdb.exe /update`` run.  Here the archive is
unpacked the same way and each set's ``.gdt`` is put into ``gdt.db`` in SQL
(:func:`zmforge.texture.gdtdb.register_gdt`), because ``gdtdb.exe`` is a .NET
program and does not run under Wine (the SQL insert was
measured as equivalent).  The cache is not dropped: in the local
copy its entries are keyed by content, so a changed tile gets a new entry
(:mod:`zmforge.props.install` says the same of the model caches).

    python -m zmforge.texture.staged_art register TOOLS STAGING

A staging tree with no archive prints "none" and changes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

ARCHIVE = "wall-art-textures.zip"
VARS = "wall-art-vars.json"
WINDOWS_ROOT = r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"


def register(tools: Path | str, staging: Path | str) -> list[str] | None:
    """Unpack and register *staging*'s wall art into *tools*; ``None`` if it has none."""
    from .gdtdb import register_gdt

    tools, staging = Path(tools), Path(staging)
    archive = staging / ARCHIVE
    if not archive.is_file():
        return None
    described = json.loads((staging / VARS).read_text(encoding="utf-8"))
    target = tools / "texture_assets"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            # The archive is unpacked under texture_assets only, and a
            # member naming a path outside it is refused.
            if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                raise SystemExit(f"!! {archive} member {member!r} leaves texture_assets")
        bundle.extractall(target)
    out: list[str] = []
    gdts = [s["gdt_file"] for s in described.get("sets", ())] or [
        f"{name}_tex.gdt" for name in described.get("texture_sets", ())]
    for set_name in described.get("texture_sets", ()):
        tiles = len(list((target / set_name).glob("*.tif")))
        out.append(f"set={set_name} tiles={tiles}")
    for gdt in gdts:
        result = register_gdt(
            target / gdt,
            tools / "gdtdb" / "gdt.db",
            tools_root=WINDOWS_ROOT,
            relative=f"texture_assets\\{gdt}",
        )
        out.append(result.describe())
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="staged_art", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="unpack and register the staged wall art (no-op if none)")
    reg.add_argument("tools", type=Path)
    reg.add_argument("staging", type=Path)
    args = parser.parse_args(argv)
    done = register(args.tools, args.staging)
    if done is None:
        print(f"== wall art: none in {args.staging}")
        return 0
    for line in done:
        print(f"== wall art: {line}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["register"] and not os.environ.get("ZMFORGE_WIDE_SQLITE"):
        # gdt.db has a table wider than a stock SQLite reads; the same wide
        # library and flag as zmforge.texture.hud_icons._reexec_wide.
        _wide = Path(__file__).resolve().parents[3] / "assets-cache" / "sqlite-wide" / "libsqlite3.so.0"
        if not _wide.exists():
            raise SystemExit(f"!! {_wide} is missing; build it once with scripts/asset-setup.py --build-sqlite")
        env = dict(os.environ)
        env["LD_PRELOAD"] = f"{_wide}:{env['LD_PRELOAD']}" if env.get("LD_PRELOAD") else str(_wide)
        env["ZMFORGE_WIDE_SQLITE"] = "1"
        os.execve(sys.executable, [sys.executable, "-m", "zmforge.texture.staged_art", *sys.argv[1:]], env)
    sys.exit(main())
