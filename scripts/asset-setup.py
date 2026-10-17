#!/usr/bin/env python
"""Fetch or build the local helpers the texture and loading-screen steps need.

    scripts/asset-setup.py --build-sqlite   # a libsqlite3 that can open the tools' gdt.db
    scripts/asset-setup.py --fetch-fonts    # the open-licence fonts the painters read

Both write into the gitignored ``assets-cache/`` and do nothing when the file
is already there.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "assets-cache"
FONT_DIR = CACHE / "fonts"
SQLITE_URL = "https://sqlite.org/2024/sqlite-amalgamation-3450000.zip"
UA = {"User-Agent": "zmforge/1.0 (map generator)"}


def wide_sqlite() -> Path:
    """Build (once) and return a libsqlite3 that can open ``gdt.db``."""
    library = CACHE / "sqlite-wide" / "libsqlite3.so.0"
    if library.exists():
        return library
    library.parent.mkdir(parents=True, exist_ok=True)
    archive = library.parent / "amalgamation.zip"
    if not archive.exists():
        print(f"== fetching the SQLite amalgamation from {SQLITE_URL}")
        urllib.request.urlretrieve(SQLITE_URL, archive)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(library.parent)
    source = next(library.parent.glob("sqlite-amalgamation-*/sqlite3.c"))
    print("== compiling libsqlite3 with a 32767-column ceiling (once)")
    subprocess.run(
        [
            "gcc", "-O1", "-fPIC", "-shared",
            "-DSQLITE_MAX_COLUMN=32767",
            "-DSQLITE_MAX_LENGTH=2000000000",
            "-DSQLITE_MAX_SQL_LENGTH=1000000000",
            "-DSQLITE_ENABLE_COLUMN_METADATA",
            "-Wl,-soname,libsqlite3.so.0",
            "-o", str(library), str(source), "-lm", "-lpthread", "-ldl",
        ],
        check=True,
    )
    return library


def fetch_fonts() -> int:
    """Put the two open-licence faces back, each with its licence file beside it.

    The bytes are gitignored like the photographs; ``assets-cache/fonts/FONTS.json``
    is the part that is kept, and it carries the URL, the licence and a quote
    of it.  A font is redistributed inside every ``.iwi`` this set produces,
    so "which licence, and does it allow that" has to be answerable from the
    repository without going back to a font site.  The SIL Open Font License
    allows it; Impact does not, which is why Impact is not here.
    """
    record = FONT_DIR / "FONTS.json"
    if not record.exists():
        print(f"no font record at {record}")
        return 1
    # Entries marked "system" are OS font packages texture/paint.py reads in
    # place; they are recorded for their licence and never downloaded.
    fetched = [e for e in json.loads(record.read_text()) if not e.get("system")]
    for entry in fetched:
        for key, url in (("file", entry["url"]), ("licence_file", entry["licence_url"])):
            target = FONT_DIR / entry[key]
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=90) as response:
                target.write_bytes(response.read())
            print(f"== {entry[key]}  {target.stat().st_size:,} bytes  {entry['licence']}")
    ok = all((FONT_DIR / entry[key]).exists()
             for entry in fetched
             for key in ("file", "licence_file"))
    print("== fonts present" if ok else "== something is still missing")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build-sqlite", action="store_true",
                        help="build the wide-column SQLite into assets-cache/sqlite-wide/")
    parser.add_argument("--fetch-fonts", action="store_true",
                        help="download Anton and Oswald and their OFL files")
    args = parser.parse_args()
    if not (args.build_sqlite or args.fetch_fonts):
        parser.print_help()
        return 1
    status = 0
    if args.build_sqlite:
        print(f"== {wide_sqlite()}")
    if args.fetch_fonts:
        status = fetch_fonts()
    return status


if __name__ == "__main__":
    sys.exit(main())
