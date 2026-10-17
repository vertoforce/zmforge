r"""A weapon the map ships itself, as a model rather than as a .gdt.

A weapon is a first-class asset type: ``weapon`` is one of the prefixes a
zone file may declare, and the linker fails loudly on a ``weapon`` line naming
something the asset database does not have -- which is the good half.  The bad
half is that a *table row* naming a weapon that does not exist is not checked
by anything: the table is a string table, opaque to the linker, and the game
finds out at the moment a player walks up to the buy.  ``W5`` is this
package's answer to that.

WHAT A CUSTOM GUN NEEDS, in the four places it needs it:

``definition``
    the asset-database entry -- a ``bulletweapon.gdf`` entity in a ``.gdt``.
    It is the caller's file, not something generated here: a bullet weapon
    states around a thousand fields and the install ships no stock weapon
    source to derive them from (``share/raw`` has no
    weapons directory, and a stock ``gdt.db`` holds no Treyarch
    ``bulletweapon`` entity).  Registering it into ``gdt.db`` is
    :mod:`zmforge.texture.gdtdb`, which handles ``bulletweapon.gdf``.
``asset``
    the ``weapon,<asset>`` line in the zone, so the linker packs it.  The
    asset name is the table name with the mode suffix -- the probe's table
    row said ``zmf_probe_gun`` and its zone line said ``zmf_probe_gun_zm``.
a table row
    what this class renders.  Without it the weapon exists and the level does
    not know it: it is not in ``level.zombie_weapons``, so no buy hands it
    out and the box never offers it.
its models
    three separate things by three separate mechanisms, and only two of them
    are weapon fields.  The model in the player's hands and the model on the
    ground are ``viewModel`` / ``worldModel`` on the weapon definition.  The
    model on the *wall* is neither: it is a key on the entity the wall buy
    points at, plus an ``xmodel`` line in the zone, and needs no weapon work
    at all.  :meth:`~zmforge.blueprint.model.Blueprint.place_wall_weapon`
    takes it as ``wall_model``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..emit.weapons import WEAPON_TABLE_COLUMNS
from ..errors import ForgeError

__all__ = ["CustomWeapon", "WEAPON_NAME_RE"]

#: A weapon name has to survive a comma-separated table, a zone line and a
#: GSC string literal, so it is the intersection of all three.
WEAPON_NAME_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class CustomWeapon:
    """One gun this map adds to the level's weapon set.

    ``asset`` defaults to ``<name>_zm``, which is the pairing the probe map
    linked with [measured]; state it explicitly when the asset in
    the database is spelled some other way, because a mismatch here is a
    linker error on one side or a silent no-op on the other.

    ``in_box`` is the mystery box's eligibility and defaults to ``False``:
    a new gun should appear where the map put it, not in a chest nobody
    asked to change.
    """

    name: str
    cost: int
    #: The ``.gdt`` that declares the asset, as the mod tools spell it.
    #: Empty means the caller has already registered the asset by hand --
    #: allowed, and reported by ``W6`` so it is a decision rather than an
    #: omission.
    definition: str = ""
    asset: str = ""
    upgrade_name: str = ""
    weapon_class: str = ""
    vo: str = ""
    ammo_cost: int | None = None
    in_box: bool = False
    is_wonder_weapon: bool = False
    wallbuy_autospawn: bool = False

    def __post_init__(self) -> None:
        if not WEAPON_NAME_RE.match(self.name or ""):
            raise ForgeError(
                f"{self.name!r} is not a usable weapon name: it is written into a "
                "comma-separated table, a zone line and a GSC string, so it must "
                f"match {WEAPON_NAME_RE.pattern}"
            )
        if self.upgrade_name and not WEAPON_NAME_RE.match(self.upgrade_name):
            raise ForgeError(
                f"{self.upgrade_name!r} is not a usable weapon name for the "
                f"upgrade of {self.name!r}"
            )
        if self.cost < 0:
            raise ForgeError(f"{self.name}: a weapon cost may not be negative")

    @property
    def asset_name(self) -> str:
        """The name the zone's ``weapon`` line carries."""
        return self.asset or f"{self.name}_zm"

    def table_row(self) -> list[str]:
        """This weapon's row, in the install's own column order.

        Every column is stated, including the empty ones: the loader reads a
        fixed set of indices and a row that stops early leaves them
        undefined in a live game.
        """
        row = [""] * len(WEAPON_TABLE_COLUMNS)
        row[WEAPON_TABLE_COLUMNS.index("weapon_name")] = self.name
        row[WEAPON_TABLE_COLUMNS.index("upgrade_name")] = self.upgrade_name
        row[WEAPON_TABLE_COLUMNS.index("cost")] = str(int(self.cost))
        row[WEAPON_TABLE_COLUMNS.index("weaponVO")] = self.vo
        if self.ammo_cost is not None:
            row[WEAPON_TABLE_COLUMNS.index("ammo_cost")] = str(int(self.ammo_cost))
        row[WEAPON_TABLE_COLUMNS.index("in_box")] = _flag(self.in_box)
        row[WEAPON_TABLE_COLUMNS.index("upgrade_in_box")] = _flag(False)
        row[WEAPON_TABLE_COLUMNS.index("is_limited")] = _flag(False)
        row[WEAPON_TABLE_COLUMNS.index("obsolete2_false")] = _flag(False)
        row[WEAPON_TABLE_COLUMNS.index("wallbuy_autospawn")] = _flag(
            self.wallbuy_autospawn
        )
        row[WEAPON_TABLE_COLUMNS.index("class")] = self.weapon_class
        if self.is_wonder_weapon:
            row[WEAPON_TABLE_COLUMNS.index("is_wonder_weapon")] = _flag(True)
        return row


def _flag(value: bool) -> str:
    """The table's own spelling of a boolean.

    ``load_weapon_spec_from_table`` compares ``ToLower( field ) == "true"``,
    so anything but ``TRUE`` reads as false; the stock table writes ``TRUE``
    and ``FALSE`` and so does this.
    """
    return "TRUE" if value else "FALSE"
