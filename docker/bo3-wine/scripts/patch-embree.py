#!/usr/bin/env python3
"""Make embree 2.3.3 survive Wine's SetThreadIdealProcessorEx stub.

WHY [measured]: radiant_modtools.exe bakes lighting through
bin\avx\embree64r.dll (embree 2.3.3). embree sizes its task scheduler from
GetActiveProcessorCount (one per logical CPU) and, after creating each worker thread,
pins it with SetThreadGroupAffinity and SetThreadIdealProcessorEx, throwing
"cannot set thread ideal processor" if either fails (embree
common/sys/thread.cpp). Wine's SetThreadIdealProcessorEx is a stub that
returns FALSE with ERROR_CALL_NOT_IMPLEMENTED (kernelbase/thread.c, still so
in Wine 11.17), so embree's createThreads loop dies after its first thread.
The winedbg dump of a spinning bake showed exactly one embree worker and one
idle Radiant job thread per logical CPU; the sun pass took 1.7-2.9 s against 0.06 s on
Windows and the probe pass never finished.

The patch renames the import in the DLL's import name table so the call
resolves to GetCurrentProcessId, which ignores its arguments and never
returns zero. Nothing else in the file changes; the output has the same size.

The patched file is written under the Wine prefix (gitignored, never
committed - it is your own Activision binary) and bind-mounted over the
original at run time, so the tools copy itself is untouched. A DLL that does
not contain the import exactly once is left alone.

zmforge.toolchain.wine.WineRunner.ensure_shims does the same thing for the
build chain; this script is for hands-on runs (scripts/wine-bake.sh calls it).
"""
from __future__ import annotations

import sys
from pathlib import Path

OLD = b"SetThreadIdealProcessorEx\0"
NEW = b"GetCurrentProcessId\0".ljust(len(OLD), b"\0")


def patch(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    count = data.count(OLD)
    if count != 1:
        print(f"{src}: {count} occurrences of the import, not patched")
        return
    if dst.is_file() and dst.stat().st_size == len(data):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data.replace(OLD, NEW))
    assert dst.stat().st_size == src.stat().st_size
    print(f"{dst}: patched ({len(data)} bytes)")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <tools-dir> <shim-dir>", file=sys.stderr)
        return 2
    tools, shims = Path(argv[1]), Path(argv[2])
    for rel in ("bin/avx/embree64r.dll", "bin/embree64r.dll"):
        src = tools / rel
        if src.is_file():
            patch(src, shims / rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
