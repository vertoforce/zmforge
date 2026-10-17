"""Register a ``.gdt``'s entries into ``gdtdb/gdt.db`` without ``gdtdb.exe``.

WHY THIS EXISTS.  Writing the ``.gdt`` text is not enough.  Measured:
a map whose face lines spelled a material declared only in a
``.gdt`` file compiled with ``WARNING: Material 'rs_probe_sign' is missing``
and linked to a fastfile that carries the error texture -- the silent
fallback.  The same map, after its two entries were inserted into
``gdt.db``, compiled with no missing-material line.  So the asset database is
what the compiler reads, and the ``.gdt`` text is only its input format.

The tool that does that conversion is ``gdtdb.exe /update``, and it is the one
tool of the four that does **not** run under Wine: it is a .NET program
and the Wine image has no runtime for it (``zmforge.toolchain.wine``).  It runs
on Windows, but a build under Wine has no Windows to hand it to, and every
texture change needs it.

So this module does what ``/update`` does, in SQL.  It is not a guess at the
schema: every table, column and id below was read out of the install's own
``gdt.db``.

  ``_gdt``      one row per ``.gdt`` file, keyed by its **lower-cased** full
                Windows path.
  ``_entity``   one row per asset: its name, the ``.gdf`` it follows
                (``image`` is ``PK_id`` 49, ``material`` is 61 on the mod tools
                install), the ``_gdt`` it came from, and its order and line
                number in that file.
  ``image`` /   one row per asset, sharing ``_entity``'s ``PK_id``, with one
  ``material``  column per field the ``.gdf`` defines -- 42 for an image, 909
                for a material.
  ``_meta``     the field list for each type, in ``_index`` order, with each
                field's default.  This is where a field absent from the
                ``.gdt`` text gets its value, so nothing is invented here.

``_derived_bits`` is a bitmap over those fields, one bit per ``_meta._index``,
set when the ``.gdt`` states the field rather than inheriting it.  Read off
the install: an image row is 6 bytes ending ``03`` (42 bits) and a material
row 114 bytes ending ``1f`` (909 bits), both all-ones below that, which is
exactly "every field stated".

``_precalc_md5`` is stored the way .NET's ``BitConverter.ToString`` prints a
digest (upper case, hyphen separated).  It is the MD5 of the entry's stated
field *values*, concatenated in file order, as UTF-8; ``_entity._gdt_linenum``
is the line of the entry's closing brace.  Measured on a scratch
copy of the install's ``gdt.db``: re-registering two stock ``.gdt`` files
(an xmodel, a material and two images each) gave every column of every row
exactly as ``gdtdb.exe`` had written it (earlier versions of this module
differed in only these two).  The stock entries state every field, so an
entry that states only some is hashed the same way by assumption.

SQLITE, AND THE ONE OBSTACLE.  ``gdt.db`` has a ``scriptbundle`` table with
more than 2000 columns, which is the *default compile-time* column ceiling in
SQLite, so Debian's ``sqlite3`` and Python's ``sqlite3`` both refuse the file
with ``malformed database schema (scriptbundle) - too many columns``.  The
database is not malformed; the library is built too small for it.  A SQLite
built with ``-DSQLITE_MAX_COLUMN=32767`` reads and writes it normally.
:func:`connect` states that plainly rather than letting the caller read
"malformed" and conclude the install is damaged.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

__all__ = [
    "GDF_IDS",
    "Entry",
    "RegisterResult",
    "connect",
    "parse_gdt",
    "register_gdt",
    "windows_gdt_path",
]

#: ``_gdf.PK_id`` for the two definitions a texture uses, read off this
#: install's ``gdt.db``.  They are database ids, not names, so they are looked
#: up by name at registration time and these are the observed values only.
GDF_IDS: dict[str, str] = {
    "image.gdf": "image",
    "material.gdf": "material",
    # A weapon is an asset like any other, and registering one is the same
    # two rows: "bulletweapon" is _gdf.PK_id 16 on the mod tools install, and its own
    # table is as wide as material's.  [Measured: the probe map's
    # gun is _entity 16559 with FK_gdf 16, and the linker packed
    # weapon,zmf_probe_gun_zm from it.]  A weapon definition is the caller's
    # file -- around a thousand fields, and the install ships no stock weapon
    # source to derive them from -- so this module registers it, it does not
    # write it.
    "bulletweapon.gdf": "bulletweapon",
    # The kit props' own models (zmforge.props), so a link under Wine can
    # carry a newly converted prop without a gdtdb.exe run first.
    # "xmodel" is _gdf.PK_id 113 on the mod tools install; its table has 217 columns.
    "xmodel.gdf": "xmodel",
}

_HEAD = re.compile(r'^\s*"([^"]+)"\s*\(\s*"([^"]+)"\s*\)\s*$')
_DERIVED = re.compile(r'^\s*"[^"]+"\s*\[\s*"[^"]+"\s*\]\s*$', re.M)
_KEY_VALUE = re.compile(r'^\s*"([^"]*)"\s*"(.*)"\s*$')

_COLUMN_LIMIT_HINT = (
    "this SQLite is built with the default 2000-column ceiling and gdt.db's "
    "scriptbundle table is wider than that; the file is fine, the library is "
    "too small for it.  scripts/asset-setup.py --build-sqlite builds a wide "
    "one once into assets-cache/sqlite-wide/; run this with that library in "
    "LD_PRELOAD"
)


@dataclass(frozen=True)
class Entry:
    """One asset as the ``.gdt`` text states it."""

    name: str
    gdf: str
    fields: dict[str, str]
    line: int  # the closing brace's line, as gdtdb.exe stores it

    @property
    def table(self) -> str:
        if self.gdf not in GDF_IDS:
            raise ValueError(
                f"{self.name}: {self.gdf!r} is not a definition this registrar "
                f"handles; known: {', '.join(sorted(GDF_IDS))}"
            )
        return GDF_IDS[self.gdf]


@dataclass(frozen=True)
class RegisterResult:
    """What :func:`register_gdt` did, so a caller can print evidence."""

    gdt_path: str
    gdt_id: int
    replaced: int
    entries: tuple[tuple[str, str, int], ...]  # (name, table, PK_id)

    def describe(self) -> str:
        made = ", ".join(f"{name} [{table} {pk}]" for name, table, pk in self.entries)
        verb = f"replaced {self.replaced} row(s), " if self.replaced else ""
        return f"{self.gdt_path}: {verb}registered {len(self.entries)}: {made}"


def connect(db: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open ``gdt.db``, or explain the column-limit refusal.

    Opening is lazy in SQLite, so the schema error surfaces on first query,
    not on connect: a trivial query is run here to move the failure to the
    call that can explain it.
    """
    path = Path(db)
    if not path.exists():
        raise FileNotFoundError(f"no asset database at {path}")
    uri = f"file:{path}?mode=ro" if read_only else f"file:{path}"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("select count(*) from _gdt").fetchone()
    except sqlite3.DatabaseError as exc:
        connection.close()
        if "too many columns" in str(exc):
            raise sqlite3.DatabaseError(f"{path}: {_COLUMN_LIMIT_HINT}") from exc
        raise
    return connection


def parse_gdt(text: str) -> list[Entry]:
    """Every asset in a ``.gdt``, in file order, with its stated fields.

    The format is the one :mod:`zmforge.texture.gdt` writes and the install's
    own files use: a brace-wrapped list of ``"name" ( "type.gdf" )`` headers,
    each followed by a brace block of ``"key" "value"`` pairs.  Line endings
    are either kind -- the shipped files are CRLF and this generator writes
    LF.
    """
    entries: list[Entry] = []
    name = gdf = None
    fields: dict[str, str] = {}
    depth = 0
    for index, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.rstrip()
        head = _HEAD.match(line)
        if head is not None and depth <= 1:
            name, gdf = head.group(1), head.group(2)
            fields = {}
            continue
        stripped = line.strip()
        if stripped == "{":
            depth += 1
            continue
        if stripped == "}":
            depth -= 1
            if name is not None and depth <= 1:
                # gdtdb.exe records the closing brace's line, not the header's.
                entries.append(Entry(name, gdf or "", dict(fields), index))
                name = gdf = None
            continue
        pair = _KEY_VALUE.match(line)
        if pair is not None and name is not None:
            fields[pair.group(1)] = pair.group(2)
    return entries


def windows_gdt_path(tools_root: str, relative: str) -> str:
    r"""``texture_assets\zm_x_tex.gdt`` under *tools_root*, as ``_gdt.name``.

    The install stores the full Windows path lower-cased, which is what makes
    a second registration of the same file replace the first rather than
    duplicate it.
    """
    return str(PureWindowsPath(tools_root) / PureWindowsPath(relative)).lower()


def _present_tables(connection: sqlite3.Connection) -> set[str]:
    """The type tables this registrar handles that this database carries."""
    have = {
        str(name)
        for (name,) in connection.execute(
            "select name from sqlite_master where type = 'table'"
        )
    }
    return {table for table in set(GDF_IDS.values()) if table in have}


def _meta(connection: sqlite3.Connection, table: str) -> list[tuple[str, str, int]]:
    rows = connection.execute(
        "select _key, _default, _index from _meta where _name = ? order by _index",
        (table,),
    ).fetchall()
    if not rows:
        raise ValueError(f"gdt.db has no field list for {table!r}")
    return [(str(key), str(default), int(index)) for key, default, index in rows]


def _gdf_id(connection: sqlite3.Connection, gdf: str) -> int:
    name = GDF_IDS.get(gdf)
    if name is None:
        raise ValueError(
            f"{gdf!r} is not a definition this registrar handles; known: "
            + ", ".join(sorted(GDF_IDS))
        )
    row = connection.execute("select PK_id from _gdf where name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"gdt.db declares no {name!r} definition")
    return int(row[0])


def register_gdt(
    gdt_file: Path | str, db: Path | str, *, tools_root: str, relative: str
) -> RegisterResult:
    """Put every asset in *gdt_file* into *db*, replacing a previous run's.

    *relative* is where the file sits under the tools root in Windows
    spelling, e.g. ``texture_assets\\zm_wall_art_tex.gdt``; it is what the
    database keys the file on, and what makes this idempotent.

    Everything the file does not state takes the default ``_meta`` records,
    so no field value is invented here.
    """
    gdt_file = Path(gdt_file)
    text = gdt_file.read_text(encoding="utf-8")
    # A derived entry (``"name" [ "parent" ]``) is a row gdtdb.exe writes with
    # FK_parent_id set; this registrar does not handle them, and re-registering
    # a file that has some would silently drop them (measured on
    # stock wpn_t7_paint_shop.gdt: 5 rows before, 2 after).
    if _DERIVED.search(text):
        raise ValueError(f"{gdt_file} has derived entries, which this registrar does not handle")
    entries = parse_gdt(text)
    if not entries:
        raise ValueError(f"{gdt_file} declares no assets")
    key = windows_gdt_path(tools_root, relative)

    connection = connect(db)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.cursor()
        row = cursor.execute("select PK_id from _gdt where name = ?", (key,)).fetchone()
        replaced = 0
        if row is not None:
            gdt_id = int(row[0])
            stale = [
                int(pk)
                for (pk,) in cursor.execute(
                    "select PK_id from _entity where FK_gdt = ?", (gdt_id,)
                )
            ]
            # Only the type tables this database actually has.  GDF_IDS
            # names every definition the registrar can handle, and an install
            # is free not to carry one of them -- deleting from a table that
            # is not there would fail a replacement that has nothing to do
            # with weapons.
            for table in sorted(_present_tables(connection)):
                for pk in stale:
                    cursor.execute(f"delete from {table} where PK_id = ?", (pk,))
            cursor.execute("delete from _entity where FK_gdt = ?", (gdt_id,))
            replaced = len(stale)
        else:
            stamp = int.from_bytes(
                hashlib.md5(key.encode("utf-8")).digest()[:8], "big", signed=True
            )
            cursor.execute(
                "insert into _gdt (name, bOpenForEdit, timestamp) values (?, 0, ?)",
                (key, stamp),
            )
            gdt_id = int(cursor.lastrowid or 0)

        # Read the field list for the types this file uses, not for every
        # type the registrar knows: a database with no weapons in it is a
        # normal database, and a texture GDT has no business needing one.
        fields_by_table = {
            entry.table: _meta(connection, entry.table) for entry in entries
        }
        made: list[tuple[str, str, int]] = []
        for order, entry in enumerate(entries):
            table = entry.table
            cursor.execute(
                "insert into _entity (name, iGdtSeqNum, FK_parent_id, FK_gdf, FK_gdt, "
                "_gdt_linenum, bExport) values (?, ?, NULL, ?, ?, ?, 0)",
                (entry.name, order, _gdf_id(connection, entry.gdf), gdt_id, entry.line),
            )
            pk = int(cursor.lastrowid or 0)
            meta = fields_by_table[table]
            columns, values = [], []
            bits = bytearray((len(meta) + 7) // 8)
            for position, (key_name, default, index) in enumerate(meta):
                columns.append(key_name)
                values.append(entry.fields.get(key_name, default))
                # A stock gdt.db's _meta stores _index as -1 for every field
                # (measured on image, material and xmodel), and a
                # -1 set only the top bit of the last byte.  gdtdb.exe writes
                # all-ones for a fully stated row, which the field's position
                # reproduces.
                bit = index if index >= 0 else position
                if key_name in entry.fields:
                    bits[bit // 8] |= 1 << (bit % 8)
            # What gdtdb.exe hashes: the stated values, in file order.
            digest = hashlib.md5("".join(entry.fields.values()).encode("utf-8")).digest()
            quoted = ",".join(f'"{column}"' for column in columns)
            holders = ",".join("?" * (len(columns) + 4))
            cursor.execute(
                f"insert into {table} (PK_id, _precalc_md5, _name, _derived_bits, {quoted}) "
                f"values ({holders})",
                [pk, "-".join(f"{b:02X}" for b in digest), entry.name, bytes(bits), *values],
            )
            made.append((entry.name, table, pk))
        connection.commit()
    finally:
        connection.close()
    return RegisterResult(key, gdt_id, replaced, tuple(made))
