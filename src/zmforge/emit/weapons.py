r"""The map's own weapon table, and the two script calls that load it.

WHAT THIS BUYS.  A wall buy's price is not a key on the buy.  ``_zm_weapons.
gsc:3362 load_weapon_spec_from_table`` reads a string table row by row and
``add_zombie_weapon`` (``:529``) stores each row's ``cost`` on a struct in
``level.zombie_weapons[ weapon ]``; the purchase reads that struct live.  So
the only way a map charges its own price is to ship its own table.  Treyarch's
own levels do exactly this -- ``zm_usermap.gsc:433 custom_add_weapons`` names
``gamedata/weapons/zm/zm_levelcommon_weapons.csv`` and every shipped level
names one of its own.

HOW A USERMAP GETS ITS TABLE LOADED FIRST.  ``zm_usermap.gsc:135`` installs
the stock loader with ``DEFAULT( level._zombie_custom_add_weapons,
&custom_add_weapons )``, and ``DEFAULT`` only assigns when the variable is
undefined.  The map's own ``main()`` runs before the framework entry, so a
map that assigns that variable itself wins and the stock assignment is a
no-op.  ``_zm_weapons.gsc:676`` then calls whatever is there.

WHY THE GENERATED TABLE IS AN OVERLAY AND NOT A COPY.  Winning the hook means
the stock table is not loaded at all unless the map loads it, so the generated
loader loads the stock table first and the map's own second.
``add_zombie_weapon`` ends with ``level.zombie_weapons[ weapon ] = struct``,
keyed by the weapon, so the second load **replaces** the row rather than
adding a duplicate.  That is what lets this module write two lines for a map
that re-prices one gun instead of restating Treyarch's fifty rows -- which
also keeps their table out of this repository.

A re-priced row is the stock row with one column changed, never a row built
from scratch: the struct is rebuilt from every column, so a row that states
only a name and a cost would quietly drop that weapon's upgrade name, its
voice-over, its box eligibility and its limits.

THE CLIENT HALF, WHICH IS EASY TO MISS.  The number on the purchase prompt is
filled in by the client, and the client has no hook: ``zm_usermap.csc:83``
calls ``include_weapons()`` directly, which loads the stock table at
``:95``.  So the map's ``.csc`` has to load the same overlay itself, after
the framework entry.  Without it the player is charged the map's price and
shown Treyarch's -- the worst of both.  Check ``W4`` holds the pair together.

WHAT CANNOT BE DONE HERE.  Not the name, and the table is the reason people
keep thinking it can be.  ``WEAPON_TABLE_COLUMNS`` has a ``hint`` column and
``load_weapon_spec_from_table`` reads it (``:3368``), so a row that sets it
looks like it should work.  It is then thrown away: ``add_zombie_weapon``
(``:560-567``) assigns ``struct.hint = &"ZOMBIE_WEAPONCOSTONLY_CFILL"`` --
or the non-client-filled spelling -- and never looks at the parameter again.
The weapon's *name* does not pass through script at all; it reaches the
prompt through the engine's cursor hint, and the name that hint prints is the
weapon asset's ``displayName``, which ``deffiles/bulletweapon.awi:15`` calls a
"Localization alias".  Price yes, name no.  [Re-tested; the whole
re-test, including the one path that is still open -- a custom weapon of the
map's own with its own ``displayName`` -- is spec 5.7.1.]

A map that wants the player to know what its gun is called says so on the wall
beside it, or in the buy prompt (:mod:`zmforge.emit.strings`).

[Measured: a probe usermap whose zone declared its own table
linked clean and the linker's own assetlist for it carries the line
``stringtable,gamedata/weapons/zm/zm_wpnprobe_weapons.csv``.]
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from ..errors import ForgeError

__all__ = [
    "COST_COLUMN",
    "IN_BOX_COLUMN",
    "NAME_COLUMN",
    "STOCK_TABLE",
    "TABLE_LOADER",
    "WEAPONS_MODULE",
    "WEAPON_TABLE_COLUMNS",
    "load_call",
    "parse_table",
    "render_weapon_table",
    "table_asset",
    "table_rows",
]

#: The stock level table every zm level loads, by the name the stock script
#: spells (``zm_usermap.gsc:433``).  The generated loader loads this first.
STOCK_TABLE = "gamedata/weapons/zm/zm_levelcommon_weapons.csv"

#: The module both generated scripts need for the loader call.
WEAPONS_MODULE = "scripts\\zm\\_zm_weapons"

#: The generated server function that owns the hook.  Reserved against custom
#: logic in :meth:`~zmforge.blueprint.model.Blueprint.add_custom_logic`,
#: because GSC resolves a duplicate definition by silently taking the second.
TABLE_LOADER = "load_weapon_table"

#: The header of ``zm_levelcommon_weapons.csv``, read off the install.
#: The loader addresses columns by index, not by name, so the
#: order is the contract and the header itself is only read by people.
WEAPON_TABLE_COLUMNS: tuple[str, ...] = (
    "weapon_name",
    "upgrade_name",
    "hint",
    "cost",
    "weaponVO",
    "weaponVOresp",
    "ammo_cost",
    "create_vox",
    "obsolete_false",
    "in_box",
    "upgrade_in_box",
    "is_limited",
    "limit",
    "upgrade_limit",
    "obsolete2_false",
    "wallbuy_autospawn",
    "class",
    "is_aat_exempt",
    "is_wonder_weapon",
    "force_attachments",
)

NAME_COLUMN = WEAPON_TABLE_COLUMNS.index("weapon_name")
COST_COLUMN = WEAPON_TABLE_COLUMNS.index("cost")
IN_BOX_COLUMN = WEAPON_TABLE_COLUMNS.index("in_box")


def table_asset(map_name: str) -> str:
    """The asset name of *map_name*'s own weapon table.

    Spelled the way the zone line and both ``load_weapon_spec_from_table``
    calls must spell it: forward slashes, under the shared ``gamedata`` tree,
    because that is where the stock table lives and the linker resolves a
    ``stringtable`` by this path.
    """
    return f"gamedata/weapons/zm/{map_name}_weapons.csv"


def load_call(table: str) -> str:
    """One ``load_weapon_spec_from_table`` statement.

    The second argument is the first data row.  It is ``1`` in every stock
    call site: row 0 is the header.
    """
    return f'zm_weapons::load_weapon_spec_from_table( "{table}", 1 );'


def parse_table(text: str) -> list[list[str]]:
    """A weapon table's rows, header included, as plain split fields.

    Deliberately not :mod:`csv`: the stock table quotes nothing, the loader
    does not either (``TableLookupRow`` hands back raw fields), and a quoting
    dialect invented here would be a difference between what this reads and
    what the game reads.
    """
    rows: list[list[str]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        rows.append(line.split(","))
    return rows


def table_rows(text: str) -> dict[str, list[str]]:
    """The data rows of a weapon table, keyed by weapon name."""
    rows = parse_table(text)
    return {row[NAME_COLUMN]: row for row in rows[1:] if row and row[NAME_COLUMN]}


def render_weapon_table(
    rows: Sequence[Sequence[str]], *, newline: str = "\n"
) -> str:
    """The map's ``<map>_weapons.csv``: the header, then one row per change.

    Every row is padded to the full column count.  A short row is not a
    smaller row to the loader -- it reads a fixed set of indices, and a
    missing one is an undefined field in a live game.
    """
    width = len(WEAPON_TABLE_COLUMNS)
    lines = [",".join(WEAPON_TABLE_COLUMNS)]
    for row in rows:
        fields = list(row)
        if len(fields) > width:
            raise ForgeError(
                f"weapon table row {fields[NAME_COLUMN]!r} has {len(fields)} "
                f"fields; the table has {width} columns"
            )
        fields += [""] * (width - len(fields))
        lines.append(",".join(fields))
    return newline.join(lines) + newline


def repriced_row(stock: Sequence[str], cost: int) -> list[str]:
    """A stock row with its cost replaced and nothing else touched."""
    row = list(stock)
    row[COST_COLUMN] = str(int(cost))
    return row


def weapon_table_text(
    prices: Mapping[str, int],
    custom_rows: Iterable[Sequence[str]],
    stock_text: str,
    *,
    newline: str = "\n",
) -> str:
    """The whole table for a map: re-priced stock rows, then custom weapons.

    *stock_text* is the install's own ``zm_levelcommon_weapons.csv``, read at
    commit time rather than copied into this repository.  A price for a
    weapon that table does not have is an error and not a row built from
    defaults: a fabricated row would link, load and then hand the player a
    gun with no upgrade, no voice-over and no box eligibility, and nothing
    downstream would say so.
    """
    stock = table_rows(stock_text)
    rows: list[Sequence[str]] = []
    for weapon in sorted(prices):
        row = stock.get(weapon)
        if row is None:
            raise ForgeError(
                f"{weapon!r} is not a row of the install's own weapon table, so "
                "there is no row to re-price; a row invented here would lose "
                "the weapon's upgrade name, voice-over, box flag and limits. "
                "Declare it as a custom weapon instead, which states every "
                "column deliberately"
            )
        rows.append(repriced_row(row, prices[weapon]))
    rows.extend(custom_rows)
    return render_weapon_table(rows, newline=newline)
