"""The asset manifest the linker reads (spec section 6).

A comma-separated file where ``>`` marks a directive and ``//`` a comment.
Only six lines are needed for a map that uses stock assets; the rest of what
a test map's manifest carried is emitted because it is free, and the entries a
shipped map has that this one does not (``sound``, the localisation
companion) are **off by default** because a build has shown they are not
needed and adding an asset that does not exist makes the linker complain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "AssetRef",
    "ASSET_PREFIXES",
    "dedupe",
    "render_manifest",
    "render_localisation_manifest",
    "display_title",
    "REQUIRED_LINES",
]


#: Asset prefixes seen in real BO3 zone files.  Every one of these was read
#: out of a shipped or community ``.zone`` / ``.zpkg`` and is listed in the
#: format reference's table: inventing a prefix here would produce a manifest
#: line the linker cannot act on.
ASSET_PREFIXES: frozenset[str] = frozenset(
    {
        "xmodel",
        "material",
        "image",
        "sound",
        "col_map",
        "gfx_map",
        "fx",
        "xanim",
        "weapon",
        "stringtable",
        "localize",
        "rawfile",
        "scriptparsetree",
        "aitype",
        "scriptbundle",
        "zbarrier",
        "weaponcamo",
        "postfxbundle",
        "ttf",
        "include",
        "ignore",
        "ignore_missing_shipped",
    }
)

_ASSET_NAME = re.compile(r"^[A-Za-z0-9_./\\-]+$")


@dataclass(frozen=True, slots=True)
class AssetRef:
    """One asset a map declares so the linker packs it.

    ``prefix`` is the zone file's asset type and must be one the format
    reference has actually seen; ``name`` is the asset, which for some types
    is a path (``stringtable,gamedata/weapons/zm/....csv``).

    Declaring an asset that does not exist makes the **linker** complain,
    which is a visible failure in a log.  Calling for an asset that was never
    declared is a **runtime** failure, which is a dead map in a play session.
    That asymmetry is why mechanics declare what they use.
    """

    prefix: str
    name: str

    def __post_init__(self) -> None:
        if self.prefix not in ASSET_PREFIXES:
            raise ValueError(
                f"{self.prefix!r} is not an asset prefix any real zone file "
                "has been seen to use; known: " + ", ".join(sorted(ASSET_PREFIXES))
            )
        if not _ASSET_NAME.match(self.name or ""):
            raise ValueError(
                f"{self.name!r} is not a usable asset name: a manifest line is "
                "comma separated, so the name may not hold a comma or a space"
            )

    @property
    def line(self) -> str:
        return f"{self.prefix},{self.name}"


def dedupe(refs: Iterable[AssetRef]) -> list[AssetRef]:
    """Declarations in first-declared order, one line each."""
    seen: set[str] = set()
    out: list[AssetRef] = []
    for ref in refs:
        if ref.line not in seen:
            seen.add(ref.line)
            out.append(ref)
    return out


def display_title(map_name: str, title: str | None = None) -> str:
    r"""The name menus should show for *map_name*.

    ``>title`` is free text: Treyarch's own shipped example usermap carries
    ``>title,Mod Combine`` in ``usermaps\mp_combine\zone_source\
    mp_combine.zone`` while its folder is ``mp_combine`` [measured on
    Windows]. The mod tools' ZM template has no ``>title`` line
    at all, so a map made from it shows up under its asset name; this
    function is why a generated map does not.
    """
    if title:
        return title
    stem = map_name[3:] if map_name.startswith("zm_") else map_name
    words = [word for word in stem.replace("-", "_").split("_") if word]
    return " ".join(word.capitalize() for word in words) or map_name


def _required(map_name: str) -> list[str]:
    return [
        ">class,zm_mod_level",
        ">group,modtools",
        f"col_map,maps/zm/{map_name}.d3dbsp",
        f"gfx_map,maps/zm/{map_name}.d3dbsp",
        f"scriptparsetree,scripts/zm/{map_name}.gsc",
        f"scriptparsetree,scripts/zm/{map_name}.csc",
    ]


#: The six lines conformance check Z14 requires, as a template.
REQUIRED_LINES = _required("<map>")


def render_manifest(
    map_name: str,
    *,
    title: str | None = None,
    sound_bank: bool = False,
    assets: Sequence[AssetRef] = (),
    extra: Sequence[str] = (),
    newline: str = "\n",
) -> str:
    """The map's ``<map>.zone``.

    ``assets`` are declarations a mechanic asked for -- a sound bank, a
    localized string, an fx -- each already validated as a real prefix.

    ``sound_bank`` adds the ``sound,<map>`` line every released map carries,
    unless ``assets`` already declares it.  It is off by default because a
    map with no bank on disk would be asking the linker for an asset that
    does not exist; a map that carries sounds turns it on by declaring them
    (:meth:`zmforge.blueprint.model.Blueprint.add_custom_sound`).
    """
    lines = [
        ">class,zm_mod_level",
        ">group,modtools",
        f">title,{title or map_name}",
        ">level.forced_model_lods,-4",
        ">level.force_static_models,1",
        ">level.force_view_models,1",
        ">level.force_world_materials,1",
        "",
        f"col_map,maps/zm/{map_name}.d3dbsp",
        f"gfx_map,maps/zm/{map_name}.d3dbsp",
        "",
        f"scriptparsetree,scripts/zm/{map_name}.gsc",
        f"scriptparsetree,scripts/zm/{map_name}.csc",
    ]
    declared = dedupe(assets)
    if sound_bank and not any(ref.line == f"sound,{map_name}" for ref in declared):
        lines.append(f"sound,{map_name}")
    if declared:
        lines.append("")
        lines.extend(ref.line for ref in declared)
    lines.extend(extra)
    return newline.join(lines) + newline


def render_localisation_manifest(map_name: str, *, newline: str = "\n") -> str:
    """The optional ``loc/<map>.zone`` companion.

    Off by default at the project level: the English fastfile was written
    without it, so until a build shows it matters it is an opt-in.
    """
    lines = [
        ">mode,zm",
        ">type,level",
        ">expect,core_all",
        ">expect,zm_common_all",
        f">level.xpak_write,{map_name}",
        ">linker.animation_mode,ZM",
        "ignore,core_common",
        "ignore_missing_shipped,core_pre_gfx",
    ]
    return newline.join(lines) + newline
