r"""The map's own localized strings, and the wall-buy prompts they rename.

WHY THIS MODULE EXISTS.  Spec 5.7 says a wall buy's prompt is not the map's
to write, and for the weapon *name* that stays true: the name reaches the
prompt through the engine's cursor hint.  The rest of the line does not.
``_zm_weapons.gsc:559-566`` force-assigns ``struct.hint =
&"ZOMBIE_WEAPONCOSTONLYFILL"`` over whatever the map's weapon table put in
the ``hint`` column, and ``get_weapon_hint()`` (``_zm_weapons.gsc:1417-1422``)
hands ``level.zombie_weapons[weapon].hint`` straight to the unitrigger stub
(``_zm_weapons.gsc:969``, re-read at ``:1305``).  So the reference is a
variable a script may overwrite after the tables load, and what it points at
is an asset this map can ship.

WHAT WAS MEASURED (under Wine, probe usermap ``zm_locprobe``).
The linker supports ``localize``.  A line ``localize,zmf_locprobe`` in the
map's **main** zone linked with no ``ERROR:`` line, and the linker's own
``zone_source/english/assetinfo/zm_locprobe.deps`` recorded the file it read:
``share\raw\english\localizedstrings\zmf_locprobe.str``.  The asset is routed
into the ENGLISH fastfile by the linker itself -- it turns up in
``zone_source/english/assetlist/<map>.csv`` -- so there is no second zone
entry to write.

THE NAMING RULE IS MEASURED, NOT GUESSED.  From that same ``assetinfo`` CSV,
the linked asset name is ``<STR FILE BASENAME>_<REFERENCE>``, uppercased, and
the prefix is **always** added, even when the reference already begins with
it: ``zmforge.str`` + ``ZMFORGE_BIG_GUN`` linked as
``ZMFORGE_ZMFORGE_BIG_GUN``.  :func:`asset_name` is that rule and
:func:`test_the_measured_asset_naming_rule` in ``tests/test_wall_prompts.py``
pins it against all four measured pairs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence


__all__ = [
    "LocalizedString",
    "NAME_TOKEN",
    "PROMPT_SHAPE",
    "STR_SUFFIX",
    "asset_name",
    "perk_prompt",
    "render_str_file",
    "weapon_prompt",
    "weapon_reference",
]

#: ``StringEd`` writes these, and a shipped map's file is the format this one
#: copies: ``ohm-nabar/zm_building``'s
#: ``english/localizedstrings/zm_abbey.str``.  Nothing but the extension is
#: checked by the linker, which resolves the asset by the file's basename.
STR_SUFFIX = ".str"

#: A reference is the key inside the ``.str`` and half of the asset name, so
#: it lives under the same alphabet an asset name does.
_REFERENCE = re.compile(r"^[A-Z0-9_]+$")

#: The prompt a wall buy shows, in the shape Treyarch's own prompts use.
#: ``^3`` and ``^7`` are colour codes, ``[{+activate}]`` is resolved to the
#: player's own use key, and ``&&1`` is the first ``SetHintString`` parameter
#: -- which is the cost, because the stub passes it:
#: ``SetHintString( stub.hint_string, stub.cost )``
#: (``_zm_unitrigger.gsc:749-765``).  Read off
#: ``PERK_DOUBLETAP_ORIGINAL`` in the shipped ``zm_abbey.str``.  The gun's
#: name goes where :data:`NAME_TOKEN` is; the braces are the engine's own
#: syntax, so this is substituted by hand rather than with ``str.format``.
PROMPT_SHAPE = "Hold ^3[{+activate}]^7 to buy $NAME [Cost: &&1]"

#: What :func:`weapon_prompt` replaces in :data:`PROMPT_SHAPE`.
NAME_TOKEN = "$NAME"


@dataclass(frozen=True, slots=True)
class LocalizedString:
    """One entry of a ``.str`` file: the key, and the English text.

    ``reference`` is what the file calls the string and what the asset name
    is built from; ``english`` is the ``LANG_ENGLISH`` line.  A map that only
    ever ships English still writes the language tag, because that is the
    line the format has.
    """

    reference: str
    english: str

    def __post_init__(self) -> None:
        if not _REFERENCE.match(self.reference or ""):
            raise ValueError(
                f"{self.reference!r} is not a usable localized-string "
                "reference: the linker uppercases the reference into the "
                "asset name, so only A-Z, 0-9 and _ survive a round trip"
            )
        if '"' in self.english:
            raise ValueError(
                f"{self.reference}: the text is written between double quotes "
                "in the .str, so a double quote inside it ends the string "
                "early and the rest of the line is read as something else"
            )
        if "\r" in self.english or "\n" in self.english:
            raise ValueError(
                f"{self.reference}: a localized string is one line. The "
                "reader takes the rest of the LANG_ENGLISH line and a second "
                "line would be read as the next directive"
            )


def asset_name(str_file: str, reference: str) -> str:
    """The name the linker gives ``reference`` inside ``<str_file>.str``.

    ``<FILE>_<REFERENCE>``, uppercased, with the prefix always added.
    Measured off the linker's own
    ``zone_source/english/assetinfo/zm_locprobe.csv``: ``zmforge.str`` +
    ``ZMFORGE_BIG_GUN`` came out as ``ZMFORGE_ZMFORGE_BIG_GUN``, so there
    is no de-duplication to imitate here, and a script that guesses the
    shorter spelling asks for an asset that is not in the fastfile.
    """
    stem = str_file[: -len(STR_SUFFIX)] if str_file.endswith(STR_SUFFIX) else str_file
    return f"{stem}_{reference}".upper()


def weapon_reference(weapon: str) -> str:
    """The reference a wall buy's renamed prompt is filed under.

    Keyed by the **weapon**, not by the gun's id: the hint lives on
    ``level.zombie_weapons[ GetWeapon( <weapon> ) ]``, which is one entry per
    weapon, so two names for one weapon would be a silent overwrite in the
    game and are a collision in a dict here instead.
    """
    return f"BUY_{weapon.upper()}"


def weapon_prompt(name: str) -> str:
    """The English line for a wall buy this map renamed.

    The cost is left as ``&&1`` rather than written in: the number is the
    stub's, filled in at use time from the weapon table, so a prompt that
    spelled a price would go stale the moment a caller changed a plan field.
    """
    return PROMPT_SHAPE.replace(NAME_TOKEN, name)


def perk_prompt(name: str) -> str:
    """The English line a custom perk's machine shows.

    The same shape a wall buy uses, and for a measured reason: the framework
    hands the perk's hint to ``SetHintString( hint, cost )``
    (``_zm_perks.gsc:395`` and ``:530``), so the cost arrives as ``&&1``
    exactly as it does for a wall buy's stub.  One shape, one place to change
    it, and a perk prompt that reads like every other prompt in the map.
    """
    return weapon_prompt(name)


def render_str_file(
    entries: Sequence[LocalizedString] | Iterable[LocalizedString],
    *,
    newline: str = "\r\n",
) -> str:
    """A ``.str`` file the linker reads, in the shipped format.

    Copied from ``ohm-nabar/zm_building``'s ``zm_abbey.str``: a three-line
    header, a blank line, then ``REFERENCE``/``LANG_ENGLISH`` pairs, then
    ``ENDMARKER``.  CRLF by default because that is what the shipped file
    has.  The alignment in Treyarch's file is tabs and is decoration -- the
    probe that linked was aligned differently and linked just
    the same -- so the columns here are tabs and nothing reads them.

    A duplicate reference is refused rather than written: the file would
    link, the second entry would win, and nothing downstream would say which
    prompt the player is reading.
    """
    rows = list(entries)
    seen: set[str] = set()
    for entry in rows:
        if entry.reference in seen:
            raise ValueError(
                f"{entry.reference}: the same reference twice in one .str "
                "file. The linker keeps one of them and says nothing"
            )
        seen.add(entry.reference)

    lines = [
        'VERSION\t\t\t"1"',
        'CONFIG\t\t\t\t"C:\\projects\\cod\\t7\\bin\\StringEd.cfg"',
        'FILENOTES\t\t\t""',
        "",
    ]
    for entry in rows:
        lines.append(f"REFERENCE\t\t\t{entry.reference}")
        lines.append(f'LANG_ENGLISH\t\t"{entry.english}"')
        lines.append("")
    lines.append("ENDMARKER")
    return newline.join(lines) + newline
