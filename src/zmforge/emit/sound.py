r"""The sound alias bank a map ships, and the rules that bank has to obey.

This module exists because the belief it replaces was wrong. This
project once recorded custom sound as "settled no": the linker
loads ``<bank>.all.alias.sz``, nothing in ``bin`` writes a ``.sz``, so a
bank needed the GUI asset editor. The extension is the whole reason anyone
believed it. Measured on the mod tools install, on Treyarch's own shipped bank
``pc\raw\sound\zone\mp_sector.all.alias.sz``:

* ``file`` reports **CSV text**;
* the first line is a 102-column header starting ``Name,Behavior,Storage,
  FileSpec,...``;
* there are 646 data rows under it, each one a plain comma-separated line;
* the line endings are CRLF.

So a ``.sz`` is a spreadsheet saved under a misleading extension. Nothing
compiles it and nothing needs to: writing the file *is* building the bank.

Three rules were measured the same day, and each one only announces itself
when it is broken, which is why they are checks rather than comments:

1. **The bank is named after the map.** ``sound,<bank>`` in the manifest
   makes the linker open ``<bank>.all.alias.sz``; a bank under any other
   name is simply not found.
2. **The bank is read from the shared raw tree**,
   ``share\raw\sound\zone\``, not from the per-platform ``pc\raw\sound\
   zone\`` where Treyarch's own ``mp_sector`` bank sits. A bank in
   ``pc\raw`` links as though it were not there.
3. **A bank holds at most 104,729 rows.** That is roughly 160 times what a
   real map uses, so it is a ceiling nobody trips over by accident, but a
   generator that writes a row per something is capable of it.

A fourth rule was found by building rather than by reading, and it is the
one that cost a link. Treyarch's own example row in ``share\raw\sound\
aliases\user_aliases.csv`` is nearly all empty cells:

    test_sound,,,tst\test_sound.wav,,,UIN_MOD,,,,,,,,,,,80,80,...

That reads like "the template named in ``Template`` fills the rest in", and
the **linker does not do that**. A bank of rows shaped like the example got
108 ``ERROR:`` lines, two per column, ``row 1 had empty required column
Storage`` and ``Unknown Storage ''``. Template inheritance belongs to the
asset editor. So :data:`_REQUIRED_DEFAULTS` spells a value for all 50
columns the linker demands, and a row overrides the handful it cares about.

The header itself is read from that same ``user_aliases.csv`` rather than
carried in this repository: the same policy the weapon table follows, for
the same reason.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Iterable, Sequence

__all__ = [
    "ALIAS_ROW_CEILING",
    "BANK_SUFFIX",
    "LOCALISED_BANK_SUFFIX",
    "CustomSound",
    "SoundAlias",
    "read_alias_header",
    "render_alias_bank",
    "render_companions",
    "render_localised_bank",
    "count_alias_rows",
    "COMPANION_SUFFIXES",
    "FALLBACK_ALIAS_HEADER",
    "FALLBACK_REVERB_HEADER",
]

#: The most rows one bank may carry. Measured by growing a bank
#: until the link stopped accepting it. A real map uses a few hundred.
ALIAS_ROW_CEILING = 104_729

#: What the linker opens for ``sound,<bank>``, and its language companion.
#: Both are CSV; the localised one is a header and no rows on a map whose
#: sound is not voice-over.
BANK_SUFFIX = ".all.alias.sz"
LOCALISED_BANK_SUFFIX = ".english.alias.sz"

#: CRLF, because every shipped bank on the mod tools install uses it (measured: 647
#: CR to 647 LF in ``mp_sector.all.alias.sz``). Whether the loader minds is
#: untested, and matching what ships costs nothing.
BANK_NEWLINE = "\r\n"

#: Templates a **mod** may name, from ``share\raw\sound\templates\
#: template_mod.csv``. A row naming a template outside this file is naming
#: one a usermap's sound build does not load. The list is deliberately the
#: 2D/3D event and UI families a generated map has a use for, not the whole
#: file: cinematics and voice-over need assets a generator does not make.
MOD_TEMPLATES: frozenset[str] = frozenset(
    {
        "UIN_MOD",
        "UIN_BUTTON_2D_MOD",
        "UIN_ALERT_2D_MOD",
        "UIN_IN_GAME_2D_MOD",
        "AMB_AMBIENCE_3D_MOD",
        "AMB_AMBIENCE_AIR_2D_MOD",
        "EXP_EXPLOSION_3D_MOD",
        "EXP_EXPLOSION_LFE_3D_MOD",
        "EXP_EXPLOSION_DEBRIS_3D_MOD",
        "DST_DESTRUCTIBLE_MOD",
        "DST_DESTRUCTIBLE_LFE_MOD",
        "PHY_IMP_LOUD_MOD",
        "PHY_IMP_SOFT_MOD",
        "EVT_EVENT_3D_MOD",
        "EVT_EVENT_LFE_3D_MOD",
        "EVT_EVENT_2D_MOD",
        "EVT_EVENT_LFE_2D_MOD",
        "EVT_EVENT_QUAD_MOD",
        "EVT_2HALF_D_MOD",
        "tst_calibration_loop_MOD",
        "tst_calibration_MOD",
    }
)


#: The alias header as the mod tools install spells it, carried so that a map can be
#: generated into a **staging tree** rather than into the tools themselves.
#: That is one shipping path for a map: the generator writes into a staging
#: folder, which mirrors a few directories of a tools root and none of
#: Treyarch's files, and a copy step puts the result onto the mod tools.
#:
#: A real install always wins: :func:`read_alias_header` reads the install's
#: own ``user_aliases.csv`` when it is there and only falls back to this when
#: it is not.  ``tests/test_sound.py`` pins the two against each other on any
#: machine that has the tools, so a game update that changes the columns is a
#: failing test rather than a bank with every value in the wrong field.
#:
#: Column *names* are carried here; no row of Treyarch's data is.
FALLBACK_ALIAS_HEADER: tuple[str, ...] = (
    "Name",
    "Behavior",
    "Storage",
    "FileSpec",
    "FileSpecSustain",
    "FileSpecRelease",
    "Template",
    "Loadspec",
    "Secondary",
    "SustainAlias",
    "ReleaseAlias",
    "Bus",
    "VolumeGroup",
    "DuckGroup",
    "Duck",
    "ReverbSend",
    "CenterSend",
    "VolMin",
    "VolMax",
    "DistMin",
    "DistMaxDry",
    "DistMaxWet",
    "DryMinCurve",
    "DryMaxCurve",
    "WetMinCurve",
    "WetMaxCurve",
    "LimitCount",
    "LimitType",
    "EntityLimitCount",
    "EntityLimitType",
    "PitchMin",
    "PitchMax",
    "PriorityMin",
    "PriorityMax",
    "PriorityThresholdMin",
    "PriorityThresholdMax",
    "AmplitudePriority",
    "PanType",
    "Pan",
    "Futz",
    "Looping",
    "RandomizeType",
    "Probability",
    "StartDelay",
    "EnvelopMin",
    "EnvelopMax",
    "EnvelopPercent",
    "OcclusionLevel",
    "IsBig",
    "DistanceLpf",
    "FluxType",
    "FluxTime",
    "Subtitle",
    "Doppler",
    "ContextType",
    "ContextValue",
    "ContextType1",
    "ContextValue1",
    "ContextType2",
    "ContextValue2",
    "ContextType3",
    "ContextValue3",
    "Timescale",
    "IsMusic",
    "IsCinematic",
    "FadeIn",
    "FadeOut",
    "Pauseable",
    "StopOnEntDeath",
    "Compression",
    "StopOnPlay",
    "DopplerScale",
    "FutzPatch",
    "VoiceLimit",
    "IgnoreMaxDist",
    "NeverPlayTwice",
    "ContinuousPan",
    "FileSource",
    "FileSourceSustain",
    "FileSourceRelease",
    "FileTarget",
    "FileTargetSustain",
    "FileTargetRelease",
    "Platform",
    "Language",
    "OutputDevices",
    "PlatformMask",
    "WiiUMono",
    "StopAlias",
    "DistanceLpfMin",
    "DistanceLpfMax",
    "FacialAnimationName",
    "RestartContextLoops",
    "SilentInCPZ",
    "ContextFailsafe",
    "GPAD",
    "GPADOnly",
    "MuteVoice",
    "MuteMusic",
    "RowSourceFileName",
    "RowSourceShortName",
    "RowSourceLineNumber",
)

#: The reverb table's column names, carried for the same reason.  A generated
#: map declares no reverb presets, so its reverb companion is this header and
#: no rows.
FALLBACK_REVERB_HEADER: tuple[str, ...] = (
    "Name",
    "MasterReturn",
    "EarlyInputLpf",
    "EarlyFeedback",
    "EarlySmear",
    "EarlyBaseDelayMs",
    "EarlyPreDelayMs",
    "EarlyReturn",
    "NearInputLpf",
    "NearFeedback",
    "NearReturn",
    "NearLowDamp",
    "NearHighDamp",
    "NearDecayTime",
    "NearSmear",
    "NearPreDelayMs",
    "FarInputLpf",
    "FarFeedback",
    "FarReturn",
    "FarLowDamp",
    "FarHighDamp",
    "FarDecayTime",
    "FarSmear",
    "FarPreDelayMs",
)

#: Where a bank's header comes from when nobody passes one in.
_HEADER_NAMES = ("Name", "Behavior", "Storage", "FileSpec")

#: Columns the **linker** requires a value in, whatever the row's template
#: says.  This is the second thing the build corrected: the one
#: example row Treyarch ships in ``user_aliases.csv`` leaves almost every
#: cell blank, which reads like "the template fills these in", and the
#: linker does not do that.  A bank of rows shaped like the example produced
#: 108 ``ERROR:`` lines, two per column, of the form
#: ``row 1 had empty required column Storage`` and ``Unknown Storage ''``.
#: Template inheritance is the asset editor's behaviour, not the linker's.
#:
#: Every value below is one the mod tools' own tables accept, checked
#: against ``share\raw\sound\globals\`` (``volume_group.csv``,
#: ``duck_group.csv``, ``curve.csv``, ``pan.csv``) and against the shape of
#: Treyarch's shipped looping rows in ``mp_sector.all.alias.sz``.
_REQUIRED_DEFAULTS: dict[str, str] = {
    "Storage": "LOADED",
    "Bus": "BUS_FX",
    "VolumeGroup": "grp_set_piece",
    "DuckGroup": "snp_scripted_moment",
    "ReverbSend": "0",
    "CenterSend": "0",
    "DryMinCurve": "allon",
    "DryMaxCurve": "default",
    "WetMinCurve": "allon",
    "WetMaxCurve": "default",
    "LimitCount": "4",
    "LimitType": "PRIORITY",
    "EntityLimitCount": "4",
    "EntityLimitType": "OLDEST",
    "PitchMin": "0",
    "PitchMax": "0",
    "PriorityMin": "10",
    "PriorityMax": "50",
    "PriorityThresholdMin": "0",
    "PriorityThresholdMax": "1",
    "AmplitudePriority": "False",
    "PanType": "3d",
    "Pan": "default",
    "Probability": "1",
    "StartDelay": "0",
    "EnvelopMin": "0",
    "EnvelopMax": "0",
    "EnvelopPercent": "0",
    "OcclusionLevel": "0",
    "IsBig": "False",
    "DistanceLpf": "True",
    "DistanceLpfMin": "800",
    "DistanceLpfMax": "3000",
    "FluxType": "NONE",
    "FluxTime": "0",
    "Doppler": "False",
    "DopplerScale": "1",
    "Timescale": "False",
    "IsMusic": "False",
    "IsCinematic": "False",
    "Pauseable": "True",
    "StopOnEntDeath": "False",
    "VoiceLimit": "False",
    "IgnoreMaxDist": "False",
    "NeverPlayTwice": "False",
    "ContinuousPan": "True",
    "RestartContextLoops": "False",
    "SilentInCPZ": "False",
    "ContextFailsafe": "False",
    "GPAD": "False",
    # The linker reports its required columns in waves: these three only
    # appeared once the fifty above were filled, on the second build.
    "GPADOnly": "False",
    "MuteVoice": "False",
    "MuteMusic": "False",
}

#: The columns an alias names for itself rather than inheriting a default.
#: A header without one of these is not an alias header this package can
#: write into.
_CHOSEN_COLUMNS = ("Name", "FileSpec", "Template", "Looping")

#: The companion tables the linker opens beside the alias bank, and what it
#: says when one is missing (measured on ``zm_ringprobe``):
#: ``ERROR: unable to load file 'sound/zone//<map>.all.ducklist.sz'`` then
#: ``ERROR: ducklist failed to load``, and the same pair for ``reverb``.
#: ``ambient``, ``musiclist`` and ``scriptid`` were not named by that link
#: and are written anyway, because every shipped bank on the mod tools install has
#: all five and a table nobody reads costs a few bytes.
COMPANION_SUFFIXES = (
    ".all.reverb.sz",
    ".all.ducklist.sz",
    ".all.ambient.sz",
    ".all.musiclist.sz",
    ".all.scriptid.sz",
)

#: ``<map>.all.scriptid.sz``: a header and no rows.  Read off the shipped
#: ``mp_sector.all.scriptid.sz``, which is that header and nothing else.
_SCRIPTID_HEADER = (
    "ScriptId",
    "AliasName",
    "RowSourceFileName",
    "RowSourceShortName",
    "RowSourceLineNumber",
)


def _sanitise(value: object) -> str:
    """One cell, with the two characters a CSV cell may not hold removed.

    A comma or a newline in a cell silently shifts every column after it,
    which is the class of failure this whole file exists to avoid, so it is
    a hard error rather than a quiet strip.
    """
    text = "" if value is None else str(value)
    if "," in text or "\n" in text or "\r" in text:
        raise ValueError(
            f"{text!r} cannot go in an alias bank cell: the bank is comma "
            "separated, so a comma or a newline moves every later column"
        )
    return text


@dataclass(frozen=True, slots=True)
class SoundAlias:
    """One row of the bank: a name a script may play, and the file behind it.

    ``name`` is what ``playsound`` / ``playloopsound`` is given. ``wav`` is
    the ``FileSpec``, a path **relative to the tools' ``sound_assets``
    folder**: Treyarch's own rows spell it that way (``FileSpec
    amb\\electronics\\...\\wall_servo_a_00_01.wav`` beside ``FileSource
    Q:\\t7\\pc\\game\\sound_assets\\amb\\electronics\\...``), and the one
    ``.wav`` the mod tools install ships, ``sound_assets\\tst\\test_sound.wav``, is
    referenced as ``tst\\test_sound.wav``.

    Every other field is optional and empty cells inherit the template, so
    a row says only what it means to change. ``looping`` is spelled out
    because only one mod template loops.
    """

    name: str
    wav: str
    template: str = "EVT_EVENT_3D_MOD"
    looping: bool = False
    volume: int | None = 90
    dist_min: float | None = None
    dist_max_dry: float | None = None
    dist_max_wet: float | None = None
    storage: str = ""
    behavior: str = ""
    fade_in_ms: int | None = None
    fade_out_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.name or any(ch in self.name for ch in ", \t\r\n"):
            raise ValueError(
                f"{self.name!r} is not a usable alias name: it is spelled into "
                "a comma-separated cell and into a script literal"
            )
        if not self.wav.lower().endswith(".wav"):
            raise ValueError(
                f"{self.wav!r} is not a .wav; the FileSpec column names the "
                "source wave file, relative to the tools' sound_assets folder"
            )
        if self.template not in MOD_TEMPLATES:
            raise ValueError(
                f"{self.template!r} is not a template template_mod.csv defines, "
                "so a usermap's sound build does not carry it; known: "
                + ", ".join(sorted(MOD_TEMPLATES))
            )

    @property
    def wav_windows(self) -> str:
        """The FileSpec as the bank spells it: backslashes."""
        return self.wav.replace("/", "\\")

    @property
    def wav_posix(self) -> str:
        """The FileSpec as a path under ``sound_assets`` on this machine."""
        return self.wav.replace("\\", "/")

    def cells(self) -> dict[str, str]:
        """Every column this row fills.

        Starts from :data:`_REQUIRED_DEFAULTS`, because the linker demands a
        value in each of those and does not fall back to the template, and
        then lays this alias's own choices over the top.
        """
        cells: dict[str, str] = dict(_REQUIRED_DEFAULTS)
        cells.update(
            {
                "Name": _sanitise(self.name),
                "Behavior": _sanitise(self.behavior) or "DEFAULT",
                "FileSpec": _sanitise(self.wav_windows),
                "Template": _sanitise(self.template),
                "Looping": "LOOPING" if self.looping else "NONLOOPING",
                "DistMin": _number(self.dist_min if self.dist_min is not None else 150),
                "DistMaxDry": _number(
                    self.dist_max_dry if self.dist_max_dry is not None else 1200
                ),
                "DistMaxWet": _number(
                    self.dist_max_wet if self.dist_max_wet is not None else 1300
                ),
                "FadeIn": _sanitise(self.fade_in_ms if self.fade_in_ms is not None else 0),
                "FadeOut": _sanitise(
                    self.fade_out_ms if self.fade_out_ms is not None else 0
                ),
            }
        )
        if self.storage:
            cells["Storage"] = _sanitise(self.storage)
        if self.volume is not None:
            cells["VolMin"] = _sanitise(self.volume)
            cells["VolMax"] = _sanitise(self.volume)
        return cells


def _number(value: float) -> str:
    return f"{value:g}"


@dataclass(frozen=True, slots=True)
class CustomSound:
    """An alias plus the bytes of the wave file it names.

    The two travel together because they fail together: a row whose file is
    not on disk is an alias the game has nothing to play, and a wave file no
    row names is bytes nothing reaches.
    """

    alias: SoundAlias
    wav_bytes: bytes
    #: Where the audio came from and under what licence. Synthesised audio
    #: says so; anything sourced names the source, which is the standard the
    #: rest of this repository holds for found assets.
    credit: str = ""

    def __post_init__(self) -> None:
        if not self.wav_bytes:
            raise ValueError(
                f"the alias {self.alias.name!r} carries no audio; an empty wave "
                "file links and plays silence, which is the failure this map "
                "would have shipped anyway"
            )
        if not self.credit.strip():
            raise ValueError(
                f"the alias {self.alias.name!r} has no credit line; say where "
                "the audio came from and under what licence, or that it was "
                "synthesised"
            )


def read_alias_header(path: str | PurePath) -> tuple[str, ...]:
    r"""The 102 column names, read from the install rather than carried here.

    ``path`` is normally ``share\raw\sound\aliases\user_aliases.csv``, the
    template Treyarch ships for exactly this purpose. Reading it keeps this
    repository free of Treyarch's data and keeps a generated bank in step
    with whatever install it is being written into: if a game update adds a
    column, a bank built from the install's own header still lines up.
    """
    source = Path(str(path))
    if not source.exists():
        return FALLBACK_ALIAS_HEADER
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if [name for name in _HEADER_NAMES if name not in header]:
        raise ValueError(
            f"{source} does not look like an alias table: its first line is "
            f"missing one of {', '.join(_HEADER_NAMES)}"
        )
    return tuple(header)


def count_alias_rows(text: str) -> int:
    """Data rows in a rendered bank, header and trailing blank excluded."""
    lines = [line for line in text.splitlines() if line.strip()]
    return max(len(lines) - 1, 0)


def render_alias_bank(
    aliases: Iterable[SoundAlias],
    header: Sequence[str],
    *,
    newline: str = BANK_NEWLINE,
) -> str:
    """The bank file: the install's header, then one line per alias.

    Refuses duplicate names (two rows, one alias, and which one wins is not
    written down anywhere) and refuses to exceed :data:`ALIAS_ROW_CEILING`.
    """
    rows = list(aliases)
    seen: set[str] = set()
    for alias in rows:
        if alias.name in seen:
            raise ValueError(
                f"two rows are both called {alias.name!r}; which one the loader "
                "keeps is not written down anywhere, so this is a mistake"
            )
        seen.add(alias.name)
    if len(rows) > ALIAS_ROW_CEILING:
        raise ValueError(
            f"{len(rows)} rows is over the measured ceiling of "
            f"{ALIAS_ROW_CEILING}; a bank that large does not load"
        )
    columns = list(header)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerow(columns)
    for alias in rows:
        cells = alias.cells()
        # A column this alias *chose* and the header does not have is a
        # mistake worth stopping for.  A default for a column the header
        # does not have is not: the header is whatever the install has, and
        # the defaults exist to satisfy the linker's required list, which is
        # a subset of it.
        unknown = [name for name in _CHOSEN_COLUMNS if name not in columns]
        if unknown:
            raise ValueError(
                f"the alias {alias.name!r} sets {', '.join(unknown)}, which this "
                "install's alias header does not have a column for"
            )
        writer.writerow([cells.get(name, "") for name in columns])
    return buffer.getvalue()


def render_companions(
    sound_raw_dir: str | PurePath, *, newline: str = BANK_NEWLINE
) -> dict[str, str]:
    r"""The five tables the linker opens beside the alias bank, keyed by suffix.

    Two of them are load-bearing, measured on a link that had the
    alias bank and nothing else::

        ERROR: unable to load file 'sound/zone//zm_ringprobe.all.ducklist.sz'
        ERROR: ducklist failed to load - sound/zone//zm_ringprobe.all.ducklist.sz
        ERROR: unable to load file 'sound/zone//zm_ringprobe.all.reverb.sz'
        ERROR: reverb failed to load for zone zm_ringprobe

    ``reverb`` and ``ambient`` are the install's own source tables,
    ``share\raw\sound\reverb\common_reverb.csv`` and
    ``share\raw\sound\ambients\ambient_mod.csv``, read at write time rather
    than carried here.  The other three are header-only: a map that adds no
    ducking, no music list and no script ids has nothing to put in them, and
    the shipped ``mp_sector.all.musiclist.sz`` is itself a bare ``Name``
    header.

    *sound_raw_dir* is ``<root>\share\raw\sound``.
    """
    root = Path(str(sound_raw_dir))
    tables: dict[str, str] = {
        # The install's own preset list when there is one, which is what a
        # shipped map's bank carries, and the bare header when there is not.
        # Both link clean [measured]: 43 presets gave a packed
        # sound asset of 7,179 bytes and none gave 299.  Reading the install
        # rather than carrying its table is the weapon table's policy, and a
        # staging tree that has no install to read still links.
        ".all.reverb.sz": _passthrough(
            root / "reverb" / "common_reverb.csv", newline, FALLBACK_REVERB_HEADER
        ),
        # Header only.  Passing ambient_mod.csv's own row through failed the
        # link with ``Unknown defaultRoom 'yes'`` and ``row 1 had empty
        # required column duck``: that file is the asset editor's input, not
        # a zone table, and a generated map declares no ambient rooms anyway.
        ".all.ambient.sz": _header_only(
            root / "ambients" / "ambient_mod.csv", newline
        ),
        ".all.ducklist.sz": "Name" + newline,
        ".all.musiclist.sz": "Name" + newline,
        ".all.scriptid.sz": ",".join(_SCRIPTID_HEADER) + newline,
    }
    return tables


def _header_only(source: Path, newline: str, fallback: Sequence[str] = ()) -> str:
    """The column names of one of the install's tables, and no rows."""
    if not source.exists():
        return (",".join(fallback) if fallback else "Name") + newline
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        first = handle.readline().rstrip("\r\n")
    return first + newline


def _passthrough(source: Path, newline: str, fallback: Sequence[str] = ()) -> str:
    """One of the install's own tables, line endings normalised.

    Copied through rather than rebuilt: a list of reverb presets is something
    a generated map neither invents nor edits, and the install is the only
    place it is correct for.  A root that is not an install -- a staging tree
    on the way to one -- gets the carried column names and no rows, which
    links.
    """
    if not source.exists():
        return (",".join(fallback) if fallback else "Name") + newline
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    return newline.join(lines) + newline


def render_localised_bank(header: Sequence[str], *, newline: str = BANK_NEWLINE) -> str:
    """The ``<map>.english.alias.sz`` companion: the header and no rows.

    The linker opens it alongside the ``all`` bank. A map whose custom sound
    is not voice-over has nothing language-specific to put in it, and an
    empty table with the right columns is what a link accepts (measured:
    a header-only English bank linked clean).
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerow(list(header))
    return buffer.getvalue()
