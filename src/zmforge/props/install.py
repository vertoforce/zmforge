"""Put a converted props staging tree into a mod tools tree run under Wine.

This is the Wine form of the prop install step: it deploys the staged
files, writes the model binaries and registers the ``.gdt`` files, the same
steps a Windows install of the mod tools takes, with no Windows machine.

* ``model_export/<map>/*.XMODEL_EXPORT`` and their ``.XMODEL_BIN``: the binary
  comes from :mod:`zmforge.props.xmodel_bin`, which writes the same bytes as
  ``export2bin.exe`` (``export2bin.exe`` itself writes truncated files under
  Wine).  Measured: byte-identical to ``export2bin.exe`` output on Windows
  for every export compared.
* ``share/raw/collmaps/*.map``, ``texture_assets/<map>/*.tif``, both ``.gdt``
  files and ``usermaps/<map>/PROP-CREDITS.md``: copied as they are, the same
  files a Windows install copies.  The ``.tif`` stays 8-bit, as it ships: the linker
  converts it (the 16-bit copies in ``render/propfix.py`` are for Radiant's
  render only).
* ``gdtdb/gdt.db``: both ``.gdt`` files registered in SQL
  (:func:`zmforge.texture.gdtdb.register_gdt`, as the Wine build registers
  the HUD and wall-art images), because ``gdtdb.exe`` does not run under Wine.

A Windows install would also clear ``zmf_*`` from
``share/assetconvert/{image,xmodel}``.  Nothing here does: in a tools tree under Wine
those caches are keyed by content (every entry name ends in a hash, and
``image`` entries start ``i_zmf_``, which a ``zmf_*`` pattern does not match
anyway), so a changed model or image gets a new entry.

A file whose bytes are already in place is not rewritten, so a re-run leaves
modification times alone.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .xmodel_bin import export_to_bin

__all__ = ["InstallResult", "write_bins", "install", "main"]


@dataclass
class InstallResult:
    bins: int = 0
    copied: list[str] = field(default_factory=list)
    unchanged: int = 0
    registered: list[dict] = field(default_factory=list)

    def describe(self) -> str:
        regs = ", ".join(f"{r['gdt']}: {r.get('entries', r.get('error'))}"
                         for r in self.registered)
        return (f"{self.bins} .XMODEL_BIN written, {len(self.copied)} file(s) copied, "
                f"{self.unchanged} already in place; registered {regs or 'nothing'}")


def write_bins(staging: Path, map_name: str) -> int:
    """Write a ``.XMODEL_BIN`` beside every ``.XMODEL_EXPORT`` in the staging tree."""
    model_dir = staging / "model_export" / map_name
    n = 0
    for export in sorted(model_dir.glob("*.XMODEL_EXPORT")):
        export.with_suffix(".XMODEL_BIN").write_bytes(
            export_to_bin(export.read_text(encoding="utf-8")))
        n += 1
    return n


def _pairs(staging: Path, map_name: str) -> list[tuple[Path, str]]:
    """(staged file, path under the tools root) for everything the install copies."""
    out: list[tuple[Path, str]] = []
    for f in sorted((staging / "model_export" / map_name).glob("*")):
        if f.suffix.upper() in (".XMODEL_EXPORT", ".XMODEL_BIN"):
            out.append((f, f"model_export/{map_name}/{f.name}"))
    for f in sorted((staging / "collmaps").glob("*.map")):
        out.append((f, f"share/raw/collmaps/{f.name}"))
    for f in sorted((staging / "texture_assets" / map_name).glob("*.tif")):
        out.append((f, f"texture_assets/{map_name}/{f.name}"))
    for rel in (f"model_export/{map_name}_props.gdt", f"texture_assets/{map_name}_props_tex.gdt"):
        if (staging / rel).is_file():
            out.append((staging / rel, rel))
    if (staging / "PROP-CREDITS.md").is_file():
        out.append((staging / "PROP-CREDITS.md", f"usermaps/{map_name}/PROP-CREDITS.md"))
    return out


def check_gdt_points_at_bins(staging: Path, map_name: str) -> None:
    """The xmodel ``.gdt`` names ``.XMODEL_BIN`` files, never the text export:
    the linker cannot read those."""
    gdt = staging / "model_export" / f"{map_name}_props.gdt"
    text = gdt.read_text(encoding="utf-8")
    if ".XMODEL_EXPORT" in text.upper():
        raise ValueError(f"{gdt} names an .XMODEL_EXPORT; the linker cannot read those")
    exports = list((staging / "model_export" / map_name).glob("*.XMODEL_EXPORT"))
    bins = list((staging / "model_export" / map_name).glob("*.XMODEL_BIN"))
    if not exports or len(bins) != len(exports):
        raise ValueError(f"{len(bins)} .XMODEL_BIN for {len(exports)} exports")


def install(staging: Path, tools: Path, map_name: str, *, register: bool = True,
            log=lambda s: None) -> InstallResult:
    """Convert, copy and register one staging tree into the tools tree at *tools*."""
    result = InstallResult()
    result.bins = write_bins(staging, map_name)
    check_gdt_points_at_bins(staging, map_name)
    for src, rel in _pairs(staging, map_name):
        dest = tools / rel
        data = src.read_bytes()
        if dest.is_file() and dest.read_bytes() == data:
            result.unchanged += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".zmf-tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        result.copied.append(rel)
    if register:
        from ..render.assets import run_wide

        files = [(str(tools / rel), rel.replace("/", "\\"))
                 for rel in (f"model_export/{map_name}_props.gdt",
                             f"texture_assets/{map_name}_props_tex.gdt")
                 if (tools / rel).is_file()]
        result.registered = run_wide({"op": "register", "db": str(tools / "gdtdb" / "gdt.db"),
                                      "files": files})["registered"]
        errors = [r for r in result.registered if "error" in r]
        if errors:
            raise RuntimeError(f"gdt.db registration failed: {errors}")
    log(f"== {result.describe()}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zmforge.props.install",
                                     description=__doc__.split("\n")[0])
    parser.add_argument("staging", type=Path, help="the tree `zmforge props --out` wrote")
    parser.add_argument("--tools", type=Path, required=True, help="the local mod-tools root")
    parser.add_argument("--map", required=True, help="the map name the props were built for")
    parser.add_argument("--bins-only", action="store_true",
                        help="write the .XMODEL_BIN files into the staging tree and stop")
    args = parser.parse_args(argv)
    if args.bins_only:
        n = write_bins(args.staging, args.map)
        check_gdt_points_at_bins(args.staging, args.map)
        print(f"== {n} .XMODEL_BIN written into {args.staging}")
        return 0
    try:
        install(args.staging, args.tools, args.map, log=print)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
