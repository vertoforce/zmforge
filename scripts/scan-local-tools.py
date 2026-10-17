#!/usr/bin/env python3
"""Rescan a local mod tools folder for models that compile but will not link.

WHY: a ``.gdt`` can declare a model whose ``.xmodel_bin`` files (a LOD or its
bullet collision) are missing from the tools' ``model_export``.  cod2map64
compiles a map that places it, then the linker stops with ``Could not find
xmodel file: ...XMODEL_BIN``.  The same happens when a material the model
uses names a colour or normal image whose ``.tif`` is not in the tools
(``image 'i_mtl_p7_foliage_grass_tussock_dry_c' is missing``), so the scan
reads each model's materials from its model files and checks those too.  ``zmforge verify`` refuses such models (check
Z13) from the ``xmodels_unlinkable`` list in
``src/zmforge/blueprint/installed_assets.json``; this script refreshes that
list from your own copy of the tools, and records every model your tools'
GDTs declare (``xmodels_local``, the converted ``zmf_prop_*`` models
included) so Z13 does not call them unverified.  Every other field of the ledger is left as it
is.

    scripts/scan-local-tools.py                 # scan $ZMFORGE_WINE_TOOLS, write the ledger
    scripts/scan-local-tools.py DIR             # scan another tools folder
    scripts/scan-local-tools.py --check         # compare only; exit 1 on drift

The tools folder defaults to ``ZMFORGE_WINE_TOOLS`` (see
``docs/public/wiring-your-build.md``).  Exit 3 when it has no ``model_export``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zmforge.blueprint.installed import (  # noqa: E402
    DEFAULT_LOCAL_TOOLS,
    LEDGER_PATH,
    scan_declared_xmodels,
    scan_unlinkable,
)


def refresh_unlinkable(tools: Path, check: bool = False) -> int:
    """Rescan *tools* and write (or, with *check*, compare) the ledger's
    ``xmodels_unlinkable`` and ``xmodels_local`` (every xmodel the local
    tools' GDTs declare); every other field is left as measured."""
    if not (tools / "model_export").is_dir():
        print(f"{tools} has no model_export; nothing scanned")
        return 3
    found = scan_unlinkable(tools)
    raw = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    was = raw.get("xmodels_unlinkable", {})
    print(f"unlinkable: {len(found)} (was {len(was)})")
    # Every model the local tools' GDTs declare, the zmforge-converted
    # ``zmf_prop_*`` ones included, in a field of its own so the reference
    # measurement (``xmodels_declared``) is left untouched.
    local = sorted(scan_declared_xmodels(tools))
    was_local = raw.get("xmodels_local", [])
    print(f"declared by the local tools: {len(local)} (was {len(was_local)})")
    if check:
        drift = sorted(set(found) ^ set(was)) + sorted(set(local) ^ set(was_local))
        print(f"drift: {drift[:10]}" if drift else "ledger matches the local tools")
        return 1 if drift else 0
    raw["xmodels_unlinkable"] = found
    raw["xmodels_local"] = local
    raw["local_tools_measured"] = datetime.date.today().isoformat()
    LEDGER_PATH.write_text(json.dumps(raw, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {LEDGER_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tools", nargs="?", default=str(DEFAULT_LOCAL_TOOLS),
                        help="the mod tools folder (default: $ZMFORGE_WINE_TOOLS)")
    parser.add_argument("--check", action="store_true", help="compare with the ledger; write nothing")
    args = parser.parse_args(argv)
    return refresh_unlinkable(Path(args.tools), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
