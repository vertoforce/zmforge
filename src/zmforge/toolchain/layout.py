"""Every path and environment variable the mod tools are addressed by.

The mod tools are Windows programs, but this package also runs on Linux,
so nothing here touches the filesystem: paths are built
from :class:`pathlib.PurePath` with the flavour chosen from the shape of
the root (Section 7.1 of the specification). A Windows root string yields
Windows separators even while running on Linux, which is what the Windows
programs expect to be given.

Fixed names (Section 0.2) appear here as string literals only: executable
file names, the ``TA_*`` variable names, directory names under the root
and the fastfile language prefixes. Everything else is named for its role
in this design.
"""

from __future__ import annotations

import re
from pathlib import PurePath, PurePosixPath, PureWindowsPath

# The two bank extensions are the sound format's own, so they are spelled
# once, in the module that knows what a bank is.
from ..emit.sound import BANK_SUFFIX, LOCALISED_BANK_SUFFIX

# Same rule for the localized-string extension: the module that knows what a
# ``.str`` is spells it, and this one only joins paths.
from ..emit.strings import STR_SUFFIX

__all__ = [
    "LANGUAGE_PREFIXES",
    "MAP_NAME_RE",
    "validate_map_name",
    "LOADING_IMAGE_NAME",
    "LOADING_IMAGE_SIZE",
    "PREVIEW_IMAGE_NAME",
    "PREVIEW_IMAGE_SIZE",
    "ToolsLayout",
    "stage_environment",
]


# Fastfile prefix per link language (Section 7.3). Only ``english``/``en``
# has been exercised [measured]; the rest are [inherited, unverified] and
# are kept here so a caller can try one without editing code.
LANGUAGE_PREFIXES: dict[str, str] = {
    "english": "en",  # [measured]
    "french": "fr",  # [inherited, unverified]
    "german": "ge",  # [inherited, unverified]
    "italian": "it",  # [inherited, unverified]
    "spanish": "sp",  # [inherited, unverified]
    "russian": "ru",  # [inherited, unverified]
    "polish": "po",  # [inherited, unverified]
    "portuguese": "br",  # [inherited, unverified]
    "japanese": "ja",  # [inherited, unverified]
    "korean": "ko",  # [inherited, unverified]
}

# Section 6.1: the two presentation images, by the fixed file names the mod
# tools' own map template uses, at the sizes this package draws them.
# ``rex\templates\ZM Mod Level\usermaps\template\zone\`` ships
# ``loadingimage.png`` (IHDR 1920x1080, 8-bit truecolour) and
# ``previewimage.png`` (600x340) [measured on Windows].
#
# Only one of the two sizes is also a rule.  Of the 46 published Workshop
# items read, all 38 loading
# screens are 1920x1080, and the 39 previews use nine different sizes of which
# 600x340 is merely the commonest (23).  So ``LOADING_IMAGE_SIZE`` is checked
# against a supplied file and ``PREVIEW_IMAGE_SIZE`` is not: it is the size a
# generated card is drawn at, and a house style, nothing more.
LOADING_IMAGE_NAME = "loadingimage.png"
LOADING_IMAGE_SIZE = (1920, 1080)
PREVIEW_IMAGE_NAME = "previewimage.png"
PREVIEW_IMAGE_SIZE = (600, 340)

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PREFIX = re.compile(r"^\\\\")


def _looks_like_windows(root: str) -> bool:
    """True when the root string is a Windows path (drive letter or UNC)."""
    return bool(_DRIVE_LETTER.match(root) or _UNC_PREFIX.match(root) or "\\" in root)


class ToolsLayout:
    """Addresses of everything under the mod-tools root.

    ``ToolsLayout("C:\\\\...\\\\Call of Duty Black Ops III 455130")`` gives
    Windows paths; ``ToolsLayout("/tmp/fake-root")`` gives POSIX paths, which
    is what the tests and any Linux-side dry run want. Use
    :meth:`windows` or :meth:`posix` when the flavour must not be guessed.
    """

    __slots__ = ("root",)

    def __init__(self, root: str | PurePath) -> None:
        if isinstance(root, PurePath):
            self.root: PurePath = root
        else:
            text = str(root)
            flavour = PureWindowsPath if _looks_like_windows(text) else PurePosixPath
            self.root = flavour(text)

    # -- explicit constructors -------------------------------------------

    @classmethod
    def windows(cls, root: str | PurePath) -> "ToolsLayout":
        """Force Windows path semantics regardless of the host."""
        return cls(PureWindowsPath(str(root)))

    @classmethod
    def posix(cls, root: str | PurePath) -> "ToolsLayout":
        """Force POSIX path semantics (tests, Linux-side dry runs)."""
        return cls(PurePosixPath(str(root)))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ToolsLayout({str(self.root)!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ToolsLayout) and other.root == self.root

    def __hash__(self) -> int:
        return hash(self.root)

    @property
    def separator(self) -> str:
        """``\\`` for a Windows root, ``/`` for a POSIX one."""
        return "\\" if isinstance(self.root, PureWindowsPath) else "/"

    def as_directory(self, path: PurePath) -> str:
        """Render *path* as a string with the trailing separator the tools want."""
        return str(path) + self.separator

    # -- tool executables and shared directories --------------------------

    @property
    def bin_dir(self) -> PurePath:
        """``<root>\\bin`` - the working directory every stage runs in."""
        return self.root / "bin"

    @property
    def gdt_database(self) -> PurePath:
        return self.root / "gdtdb" / "gdtdb.exe"

    @property
    def compiler(self) -> PurePath:
        return self.bin_dir / "cod2map64.exe"

    @property
    def light_baker(self) -> PurePath:
        """The GUI lighting tool; needs an interactive desktop (Section 7.3)."""
        return self.bin_dir / "radiant_modtools.exe"

    @property
    def linker(self) -> PurePath:
        return self.bin_dir / "linker_modtools.exe"

    @property
    def asset_cache(self) -> PurePath:
        """``<root>\\share\\assetconvert`` - converted-asset cache."""
        return self.root / "share" / "assetconvert"

    @property
    def map_source_dir(self) -> PurePath:
        return self.root / "map_source" / "zm"

    @property
    def stock_prefab_dir(self) -> PurePath:
        return self.root / "map_source" / "_prefabs" / "zm" / "zm_core"

    @property
    def script_dir(self) -> PurePath:
        return self.root / "share" / "raw" / "scripts" / "zm"

    @property
    def compiler_output_dir(self) -> PurePath:
        return self.root / "share" / "raw" / "maps" / "zm"

    @property
    def model_export_dir(self) -> PurePath:
        r"""``<root>\model_export`` - where converted models and their GDTs sit."""
        return self.root / "model_export"

    @property
    def collmap_dir(self) -> PurePath:
        r"""``<root>\share\raw\collmaps`` - the brush collmaps cod2map bakes."""
        return self.root / "share" / "raw" / "collmaps"

    @property
    def weapon_table_dir(self) -> PurePath:
        r"""``<root>\share\raw\gamedata\weapons\zm`` - the weapon tables.

        The shared ``gamedata`` tree, not the map's own folder: a
        ``stringtable`` asset is resolved by the path the zone line spells,
        and the stock table this one overlays lives here.
        """
        return self.root / "share" / "raw" / "gamedata" / "weapons" / "zm"

    @property
    def stock_weapon_table(self) -> PurePath:
        """Treyarch's own level table, the one a generated table overlays."""
        return self.weapon_table_dir / "zm_levelcommon_weapons.csv"

    @property
    def localized_strings_dir(self) -> PurePath:
        r"""``<root>\share\raw\english\localizedstrings`` - the ``.str`` files.

        The shared ``raw`` tree under the language the strings are written
        in, which is where the linker looks: a probe usermap declaring
        ``localize,zmf_locprobe`` linked clean and its own ``.deps`` named
        ``share\raw\english\localizedstrings\zmf_locprobe.str`` as the file
        it had read [measured, under Wine].  The install ships no
        ``.str`` of its own here, so the directory is usually ours to make.
        """
        return self.root / "share" / "raw" / "english" / "localizedstrings"

    @property
    def sound_bank_dir(self) -> PurePath:
        r"""``<root>\share\raw\sound\zone`` - where the linker reads banks.

        The **shared** raw tree, not the per-platform ``pc\raw\sound\zone``
        where Treyarch's own shipped ``mp_sector`` bank sits. Measured:
        a bank in ``pc\raw`` links as though it were absent, and
        the same file under ``share\raw`` links. The linker's own error
        spells the tail of the path it wants, ``sound/zone//<bank>.all.alias.sz``.
        """
        return self.root / "share" / "raw" / "sound" / "zone"

    @property
    def alias_template(self) -> PurePath:
        r"""``share\raw\sound\aliases\user_aliases.csv``, the column names.

        Treyarch's own template, read for its 102-column header rather than
        copied into this repository, and carrying one example row that shows
        the minimal shape of an alias.
        """
        return self.root / "share" / "raw" / "sound" / "aliases" / "user_aliases.csv"

    @property
    def sound_source_dir(self) -> PurePath:
        r"""``<root>\sound_assets`` - the root every ``FileSpec`` is relative to.

        Read off Treyarch's own rows, which carry both spellings side by
        side: ``FileSpec amb\electronics\...\wall_servo_a_00_01.wav`` and
        ``FileSource Q:\t7\pc\game\sound_assets\amb\electronics\...``.
        """
        return self.root / "sound_assets"

    # -- per-map inputs ----------------------------------------------------

    def map_source(self, name: str) -> PurePath:
        return self.map_source_dir / f"{name}.map"

    def prefab_dir(self, name: str) -> PurePath:
        return self.root / "map_source" / "_prefabs" / "zm" / name

    def server_script(self, name: str) -> PurePath:
        return self.script_dir / f"{name}.gsc"

    def client_script(self, name: str) -> PurePath:
        return self.script_dir / f"{name}.csc"

    def props_gdt(self, name: str) -> PurePath:
        """``model_export\\<map>_props.gdt`` - the map's own prop entries."""
        return self.model_export_dir / f"{name}_props.gdt"

    def weapon_table(self, name: str) -> PurePath:
        """``<map>_weapons.csv``, the map's own weapon table."""
        return self.weapon_table_dir / f"{name}_weapons.csv"

    def localized_strings(self, name: str) -> PurePath:
        r"""``<map>.str``, the map's own strings.

        Named after the map because the linker builds the asset name out of
        the file's basename (:func:`zmforge.emit.strings.asset_name`), so the
        file name is half of every reference the generated script spells.
        """
        return self.localized_strings_dir / f"{name}{STR_SUFFIX}"

    def sound_bank(self, name: str) -> PurePath:
        r"""``share\raw\sound\zone\<map>.all.alias.sz``, the map's own bank.

        Named after the map because ``sound,<bank>`` is what the linker
        opens, and a generated map declares its own name.
        """
        return self.sound_bank_dir / f"{name}{BANK_SUFFIX}"

    def localised_sound_bank(self, name: str) -> PurePath:
        r"""``share\raw\sound\zone\<map>.english.alias.sz``, the companion."""
        return self.sound_bank_dir / f"{name}{LOCALISED_BANK_SUFFIX}"

    def sound_companion(self, name: str, suffix: str) -> PurePath:
        r"""``share\raw\sound\zone\<map><suffix>``, one companion table.

        *suffix* comes from :data:`zmforge.emit.sound.COMPANION_SUFFIXES`.
        """
        return self.sound_bank_dir / f"{name}{suffix}"

    @property
    def sound_raw_dir(self) -> PurePath:
        r"""``<root>\share\raw\sound`` - the source tables under it.

        The reverb and ambient companions are built from the install's own
        ``reverb\common_reverb.csv`` and ``ambients\ambient_mod.csv``.
        """
        return self.root / "share" / "raw" / "sound"

    def sound_wav(self, name: str, spec: str) -> PurePath:
        r"""The wave file an alias's ``FileSpec`` names, under ``sound_assets``.

        *spec* is the FileSpec as the bank spells it; the map's own sounds
        live under a folder of the map's name so two maps on one install
        cannot overwrite each other's audio.
        """
        relative = spec.replace("\\", "/").strip("/")
        path = self.sound_source_dir
        for part in relative.split("/"):
            path = path / part
        return path

    def zone_source_dir(self, name: str) -> PurePath:
        return self.root / "usermaps" / name / "zone_source"

    # -- what the link itself wrote about the link -------------------------
    #
    # Three small reports land beside each fastfile, one set per zone
    # (``all`` and the language), and they are the only honest account of
    # what went into it: the linker's log says nothing about an asset it
    # silently left out.  *zone* is ``"all"`` or a language name.

    def link_report_dir(self, name: str, zone: str = "all") -> PurePath:
        r"""``usermaps\<map>\zone_source\<zone>\assetinfo``."""
        return self.zone_source_dir(name) / zone / "assetinfo"

    def link_pool_report(self, name: str, zone: str = "all") -> PurePath:
        r"""``<zone>\assetinfo\<map>_poolinfo.csv`` - ``type,limit,total``."""
        return self.link_report_dir(name, zone) / f"{name}_poolinfo.csv"

    def link_asset_info(self, name: str, zone: str = "all") -> PurePath:
        r"""``<zone>\assetinfo\<map>.csv`` - every asset written, with sizes."""
        return self.link_report_dir(name, zone) / f"{name}.csv"

    def link_deps(self, name: str, zone: str = "all") -> PurePath:
        r"""``<zone>\assetinfo\<map>.deps`` - every file the linker opened."""
        return self.link_report_dir(name, zone) / f"{name}.deps"

    def link_asset_list(self, name: str, zone: str = "all") -> PurePath:
        r"""``<zone>\assetlist\<map>.csv`` - ``<type>,<name>`` per asset."""
        return self.zone_source_dir(name) / zone / "assetlist" / f"{name}.csv"

    def manifest(self, name: str) -> PurePath:
        return self.zone_source_dir(name) / f"{name}.zone"

    def localisation_manifest(self, name: str) -> PurePath:
        """``usermaps\\<map>\\zone_source\\loc\\<map>.zone``."""
        return self.zone_source_dir(name) / "loc" / f"{name}.zone"

    # -- per-map outputs ---------------------------------------------------

    def compiled_bsp(self, name: str) -> PurePath:
        return self.compiler_output_dir / f"{name}.d3dbsp"

    def navmesh(self, name: str) -> PurePath:
        return self.compiler_output_dir / f"{name}_navmesh.hkt"

    def navvolume(self, name: str) -> PurePath:
        return self.compiler_output_dir / f"{name}_navvolume.hkt"

    def led(self, name: str) -> PurePath:
        return self.compiler_output_dir / f"{name}.led"

    def fastfile_dir(self, name: str) -> PurePath:
        return self.root / "usermaps" / name / "zone"

    def fastfile(self, name: str) -> PurePath:
        return self.fastfile_dir(name) / f"{name}.ff"

    def localised_fastfile(self, name: str, prefix: str = "en") -> PurePath:
        """``<prefix>_<map>.ff``; *prefix* comes from :data:`LANGUAGE_PREFIXES`."""
        return self.fastfile_dir(name) / f"{prefix}_{name}.ff"

    # -- presentation images (Section 6.1) ---------------------------------

    def loading_image(self, name: str) -> PurePath:
        r"""``usermaps\<map>\zone\loadingimage.png`` - the loading screen.

        A loose file beside the fastfiles, not an asset in one: the linker
        never sees it and the game reads it from disk.
        """
        return self.fastfile_dir(name) / LOADING_IMAGE_NAME

    def preview_image(self, name: str) -> PurePath:
        r"""``usermaps\<map>\zone\previewimage.png`` - the menu thumbnail."""
        return self.fastfile_dir(name) / PREVIEW_IMAGE_NAME

    def workshop_json(self, name: str) -> PurePath:
        r"""``usermaps\<map>\zone\workshop.json`` - the launcher's publish settings.

        See :mod:`zmforge.workshop` for what the launcher reads from it.
        """
        from ..workshop import WORKSHOP_JSON_NAME

        return self.fastfile_dir(name) / WORKSHOP_JSON_NAME

    def workshop_thumbnail(self, name: str) -> PurePath:
        r"""``usermaps\<map>\zone\workshop_thumbnail.jpg`` - the Workshop preview."""
        from ..workshop import THUMBNAIL_NAME

        return self.fastfile_dir(name) / THUMBNAIL_NAME

    # -- directory obligations (Section 7.1) --------------------------------

    def directories_to_create(self, name: str) -> list[PurePath]:
        """Directories the generator creates itself before writing.

        They may not exist for a brand new map, so writing has to make them.
        """
        return [
            self.map_source_dir,
            self.script_dir,
            self.zone_source_dir(name),
            self.fastfile_dir(name),
        ]

    def directories_required(self, name: str) -> list[PurePath]:
        """Directories a stage needs to already exist.

        These were present on the measured install; whether the tools create
        them is **[unverified]**, so a missing one is a configuration error
        rather than something to silently mkdir.
        """
        return [
            self.bin_dir,
            self.compiler_output_dir,
            self.fastfile_dir(name),
        ]


def stage_environment(layout: ToolsLayout) -> dict[str, str]:
    """The three ``TA_*`` variables of Section 7.2, each trailing-separated.

    Returned as an overlay: merge it onto the inherited environment, never
    pass it as the whole environment. The trailing separator is load-bearing
    (a backslash for a Windows root).
    """
    root_dir = layout.as_directory(layout.root)
    return {
        "TA_GAME_PATH": root_dir,
        "TA_TOOLS_PATH": root_dir,
        "TA_LOCAL_ASSET_CACHE": layout.as_directory(layout.asset_cache),
    }


def resolve_layout(layout: ToolsLayout | str | PurePath) -> ToolsLayout:
    """Accept a layout, a root string or a pure path and return a layout."""
    if isinstance(layout, ToolsLayout):
        return layout
    return ToolsLayout(layout)


# -- map names --------------------------------------------------------------

#: A usermap's name must be a legal asset name; the tools and the manifest
#: both spell it into paths, and the zombies loader expects the ``zm_`` prefix.
#: ``\Z``, not ``$``: ``$`` also matched before a trailing newline.
MAP_NAME_RE = re.compile(r"^zm_[a-z0-9_]+\Z")

#: Where Steam installs the mod tools, which is also the path Wine shows them
#: at; a POSIX tools copy is measured against this, since that is the path the
#: Windows tools themselves open.
DEFAULT_WINDOWS_ROOT = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"
)
#: ``MAX_PATH`` is 260 including the terminating NUL; the mod tools are not
#: long-path aware, so a longer path fails inside them, mid-build.
WINDOWS_MAX_PATH_CHARS = 259


def deepest_map_path(layout: "ToolsLayout", name: str) -> PurePath:
    r"""The longest path the tools write for map *name*.

    The linker's per-zone reports, ``usermaps\<map>\zone_source\<language>\
    assetinfo\<map>_poolinfo.csv``: the map's name is in it twice, and the
    longest language name is the deepest zone.
    """
    zones = ("all", *LANGUAGE_PREFIXES)
    candidates = [
        method(name, zone)
        for zone in zones
        for method in (layout.link_pool_report, layout.link_asset_info,
                       layout.link_deps, layout.link_asset_list)
    ]
    return max(candidates, key=lambda path: len(str(path)))


def validate_map_name(name: object, layout: "ToolsLayout | None" = None) -> str:
    """*name* if it is a usable map name, else a one-line :class:`ForgeError`.

    Checks the spelling (which also rules out ``..`` and path separators) and
    that the deepest file the tools write for it fits Windows' path limit under
    *layout*'s root (a POSIX root is measured as the Steam path Wine shows).
    """
    from ..errors import ForgeError

    if not isinstance(name, str) or not MAP_NAME_RE.fullmatch(name):
        raise ForgeError(
            f"map name {name!r} must match {MAP_NAME_RE.pattern}: lower case, "
            "digits and underscores, starting with 'zm_'"
        )
    if layout is None or not isinstance(layout.root, PureWindowsPath):
        layout = ToolsLayout.windows(DEFAULT_WINDOWS_ROOT)
    deepest = str(deepest_map_path(layout, name))
    if len(deepest) > WINDOWS_MAX_PATH_CHARS:
        longest = len(name)
        while longest > 4 and len(str(deepest_map_path(
                layout, "zm_" + "a" * (longest - 3)))) > WINDOWS_MAX_PATH_CHARS:
            longest -= 1
        raise ForgeError(
            f"map name {name!r} is too long: the tools would write {deepest} "
            f"({len(deepest)} characters, over Windows' {WINDOWS_MAX_PATH_CHARS}); "
            f"use at most {longest} characters"
        )
    return name
