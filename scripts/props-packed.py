#!/usr/bin/env python
"""Prove that the props a map places are actually in the built map.

WHY THIS EXISTS.  A clean link is not evidence that a model is in the map.
Measured: a map source placing 2,171 ``misc_model`` entities drawn from 129
distinct stock models compiled with exit 0 and no ``ERROR:`` line, the linker
printed **no ``ERROR:`` line at all** and wrote both fastfiles -- and the
linker's own ``<map>_xmodel.csv`` report listed **68** models, none of them
among the 124 whose ``.xmodel_bin`` is absent from that tools install.  The
link dropped them in silence.  Every verdict rule in
``zmforge.toolchain.evidence`` passed.

So the only honest test is the one this script runs: read the model names out
of the ``.map`` the compiler was given, read the model names out of the
linker's ``assetinfo/<map>_xmodel.csv``, and name the difference.

``<map>_xmodel.csv`` is the linker's own per-model report -- name, reference
count, radius and the vertex and triangle counts of every LOD -- so it is
both the membership list and, for free, the triangle bill.

    scripts/props-packed.py <map> --tools-dir <mod tools root>

Exit 0 when every placed model is packed, 1 when any is missing.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

MODEL_LINE = re.compile(r'"model"\s+"([^"\\]+)"')


def placed_models(map_file: Path) -> Counter:
    """Every ``misc_model`` model name in a ``.map``, with how many of each.

    Prefab references are skipped: a ``misc_prefab`` names a ``.map`` under
    ``_prefabs`` and the models are inside it, so the entity's own ``model``
    key is a path and not an asset name.
    """
    text = map_file.read_text(encoding="utf-8", errors="replace")
    counts: Counter = Counter()
    for block in text.split("// entity ")[1:]:
        if '"classname" "misc_model"' not in block:
            continue
        found = MODEL_LINE.search(block)
        if found:
            counts[found.group(1)] += 1
    return counts


def packed_models(report: Path) -> dict[str, int]:
    """Model name -> LOD-0 triangles, from the linker's own xmodel report."""
    out: dict[str, int] = {}
    with report.open(encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not name or name == "name":
                continue
            try:
                out[name] = int(row.get("tris0") or 0)
            except ValueError:
                out[name] = 0
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_name")
    parser.add_argument("--tools-dir", required=True)
    parser.add_argument(
        "--quiet", action="store_true", help="only print the verdict and what is missing"
    )
    args = parser.parse_args(argv)

    tools = Path(args.tools_dir)
    map_file = tools / "map_source" / "zm" / f"{args.map_name}.map"
    report = (
        tools / "usermaps" / args.map_name / "zone_source" / "all" / "assetinfo"
        / f"{args.map_name}_xmodel.csv"
    )
    for path, what in ((map_file, "map source"), (report, "linker xmodel report")):
        if not path.exists():
            print(f"!! no {what} at {path}")
            return 2

    placed = placed_models(map_file)
    packed = packed_models(report)
    missing = sorted(name for name in placed if name not in packed)
    present = sorted(name for name in placed if name in packed)

    instances = sum(placed.values())
    lost = sum(placed[name] for name in missing)
    triangles = sum(placed[name] * packed[name] for name in present)

    if not args.quiet:
        print(f"map source   {map_file}")
        print(f"link report  {report}")
        print(
            f"placed       {instances} misc_model entities, "
            f"{len(placed)} distinct models"
        )
        print(f"packed       {len(present)} of {len(placed)} distinct models")
        print(f"triangles    {triangles} over the placed instances (LOD 0)")
    if missing:
        print(
            f"!! {len(missing)} models are placed and NOT packed, "
            f"covering {lost} of {instances} entities:"
        )
        for name in missing:
            print(f"   {name}  x{placed[name]}")
        print(
            "   the link printed no error for any of these. On this tools copy "
            "the usual cause is a missing model_export/<folder>/<name>_lod0.xmodel_bin."
        )
        return 1
    print(f"ok: every one of the {len(placed)} placed models is in the built map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
