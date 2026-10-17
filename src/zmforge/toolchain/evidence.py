"""Reading verdicts out of tool logs.

The exit code is not the verdict (Section 10, item K3): the linker returns
154000 or 2000 on success, and the compiler returns 0 with a leak. What a
stage did is decided by what it printed, so every stage log is parsed into
a :class:`StageEvidence` record and the stage verdict is derived from that.

Two rules from the known-bad list are implemented here:

* K12 - output is decoded with replacement, never strictly. One undecodable
  byte must not discard a whole build's worth of log.
* K13 - ``jun_art_wood_plywood_dark03`` (from the mystery box prefab) is a
  known-benign missing material and is not a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "BENIGN_MISSING_MATERIALS",
    "RADIANT_LOG_MARKER",
    "StageEvidence",
    "decode_tool_output",
    "read_bake_log",
    "read_compile_log",
    "read_link_log",
    "read_refresh_log",
    "strip_colour",
]


# Missing-material warnings that a clean build still prints. K13: the
# material is not offered by the catalogue, and its warning is benign.
BENIGN_MISSING_MATERIALS: frozenset[str] = frozenset({"jun_art_wood_plywood_dark03"})

# Radiant names the image a material could not load.  Most such lines are the
# compiled stock ``i_mtl_*`` images the tools ship without a .tif and are
# harmless; a *placeholder* image is not: the material links and the game
# draws it magenta with black DELETE lettering (``mtl_p_ger_metal_desk`` on
# ``p7_desk_metal_old_01``, zm_cemetery shed desk).
_FAILED_IMAGE = re.compile(
    r"Failed to load image\s+'([^']+)'\s+for material\s+'([^']+)'", re.IGNORECASE
)

# ``^1``-style console colour codes.
_COLOUR = re.compile(r"\^\d")

_ERROR_LINE = re.compile(r"(?:^|\s)(?:UNRECOVERABLE\s+)?ERROR:", re.IGNORECASE)
# Wine's own loader failures, which are not ``ERROR:`` lines. WHY they belong
# in the shared error scan: a tool that Wine killed before it printed anything
# leaves a log that looks clean, and the link verdict then passes on the
# *previous* build's fastfiles, which are still on disk [measured:
# linker_modtools.exe aborted on an unimplemented msvcr110 Concurrency Runtime
# entry point and the chain reported "link: ok" with two stale fastfiles].
# Benign ``wine:`` notices ("created the configuration directory", "using
# kernel write watches") are not matched, which is why this is keyed on the
# failure words rather than on the prefix alone.
_WINE_FATAL = re.compile(
    r"^wine:.*(?:unimplemented function|Unhandled [a-z ]*(?:exception|page fault)"
    r"|aborting|could not load|failed to load|cannot find).*$",
    re.IGNORECASE | re.MULTILINE,
)
_LEAK_BANNER = re.compile(r"^[*\s]*\bleaked\b[*\s]*$", re.IGNORECASE | re.MULTILINE)
_LEAKFILE = re.compile(r"WROTE BSP LEAKFILE:\s*(\S.*?\.lin)\s*$", re.IGNORECASE | re.MULTILINE)
_MISSING_MATERIAL = re.compile(r"Material\s+'([^']+)'\s+is missing", re.IGNORECASE)
# A string table the zone declares and the linker could not find.  It is a
# WARNING, the link finishes, both fastfiles are written and the verdict used
# to pass -- which is the worst shape a failure can have here, because the
# asset a usermap declares a string table for is its **weapon table**: the map
# then ships with Treyarch's prices and nothing says so until somebody walks
# up to a wall buy.  Measured by linking zm_price_probe with its
# table moved aside:
#   ^3WARNING: missing stringTable gamedata/weapons/zm/zm_price_probe_weapons.csv
#     stringtable:gamedata/weapons/zm/zm_price_probe_weapons.csv
#       csv:zone_source/zm_price_probe.zone
# and "done: 0m24.09s" after it, exit like any other link.  Other asset types
# presumably print the same shape; only this one has been measured, so only
# this one is matched.
_MISSING_STRINGTABLE = re.compile(
    r"^.*\bmissing\s+stringTable\b.*$", re.IGNORECASE | re.MULTILINE
)
_UMBRA_UNSET = re.compile(r"^.*umbra.*not\s+set.*$", re.IGNORECASE | re.MULTILINE)
_SKY_RESTRICTED = re.compile(r"restricting BSP to sky brushes", re.IGNORECASE)
_CURVE_COLLISION = re.compile(r"building curve/terrain collision", re.IGNORECASE)
_CAULK_TERRAIN = re.compile(r"terrain patches with caulk were discovered", re.IGNORECASE)
_NAVVOLUME_SKIPPED = re.compile(r"NavVolume generation is skipped", re.IGNORECASE)
_DONE_TAIL = re.compile(r"^.*\bdone:\s*\S+.*$", re.IGNORECASE | re.MULTILINE)
_DROPPED_VERTS = re.compile(
    r"DROPPED VERTS\.\s*\d+\s*warnings encountered while processing xmodel\s*'([^']*)'",
    re.IGNORECASE,
)
_GDT_PROCESSED = re.compile(r"gdtDB:\s*processed.*$", re.IGNORECASE | re.MULTILINE)
# The bake. Radiant prints one line to the console on success and keeps the
# rest in its own log, which the Wine runner appends after this marker
# [measured].
RADIANT_LOG_MARKER = "== Radiant.log"
_BAKE_EXPORTED = re.compile(r"^LED Exported for .*$", re.MULTILINE)
_BAKE_EXPORT_DONE = re.compile(r"Export Done \([^)]*\)")
_BAKE_PHASE = re.compile(
    r"Sun bake Done \([^)]*\)|Ray tracing scene build \([^)]*\)"
    r"|Bounce \d+ Complete \([^)]*\)|Export Done \([^)]*\)|Exported \S[^\r\n]*?\.led"
)
_BAKE_FAILED = re.compile(r"^.*Failed to export.*$", re.IGNORECASE | re.MULTILINE)
_RADIANT_ERROR = re.compile(r"^\d\d:\d\d:\d\d: ERROR:\s*(.*?)\s*$", re.MULTILINE)
_DUPLICATE_ASSET = re.compile(r"Duplicate\s+'([^']+)'\s+asset\s+'([^']+)'", re.IGNORECASE)


def decode_tool_output(raw: bytes, encodings: tuple[str, ...] = ("utf-8",)) -> str:
    """Decode tool bytes without ever throwing the result away (K12).

    Each encoding in *encodings* is tried strictly, in order. If they all
    fail, the first one is applied again with ``errors="replace"``, so an
    undecodable byte costs one character and nothing else.

    The default single-encoding chain is deliberate. ``cp1252`` cannot be a
    strict fallback because it maps 0xFF to a valid character, which would
    silently invent text where the console emitted garbage; a caller that
    knows a log came from a legacy code page can ask for
    ``encodings=("utf-8", "cp1252")``.
    """
    if not encodings:
        encodings = ("utf-8",)
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode(encodings[0], errors="replace")


def strip_colour(text: str) -> str:
    """Remove ``^N`` console colour codes so patterns match plain text."""
    return _COLOUR.sub("", text)


@dataclass
class StageEvidence:
    """What a stage's log says, independent of the exit code.

    One record covers every stage; the fields a stage cannot produce simply
    stay empty. Verdicts live in :mod:`zmforge.toolchain.stages`, which reads
    this record - nothing here decides pass or fail.
    """

    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    leaked: bool = False
    leakfile: str | None = None
    missing_materials: list[str] = field(default_factory=list)
    benign_missing_materials: list[str] = field(default_factory=list)
    umbra_volume_unset: bool = False
    sky_restricted: bool = False
    curve_collision: bool = False
    caulk_terrain_patches: bool = False
    navvolume_skipped: bool = False
    completion_lines: list[str] = field(default_factory=list)
    ignored_asset_warnings: list[str] = field(default_factory=list)
    duplicate_assets: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """No ``ERROR:`` line was printed."""
        return not self.errors

    @property
    def unexpected_missing_materials(self) -> list[str]:
        """Missing materials that are not on the benign list (K13)."""
        return [m for m in self.missing_materials if m not in BENIGN_MISSING_MATERIALS]


def _unique(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def _error_lines(text: str) -> list[str]:
    """Every line that means the stage failed, whoever printed it.

    Both the tools' own ``ERROR:`` lines and Wine's loader failures, because
    a stage killed by the loader failed just as completely as one that
    printed an error.
    """
    lines = [line.strip() for line in text.splitlines() if _ERROR_LINE.search(line)]
    lines += [match.group(0).strip() for match in _WINE_FATAL.finditer(text)]
    return _unique(lines)


def read_compile_log(text: str) -> StageEvidence:
    """Parse ``cod2map64.exe`` output (Section 7.3, Compile)."""
    plain = strip_colour(text)
    evidence = StageEvidence(errors=_error_lines(plain))

    leakfile = _LEAKFILE.search(plain)
    if leakfile:
        evidence.leakfile = leakfile.group(1).strip().strip('"')
    evidence.leaked = bool(leakfile) or bool(_LEAK_BANNER.search(plain))
    if evidence.leaked:
        evidence.notes.append("leak banner found")

    materials = _unique(_MISSING_MATERIAL.findall(plain))
    evidence.missing_materials = materials
    evidence.benign_missing_materials = [m for m in materials if m in BENIGN_MISSING_MATERIALS]
    # A missing material compiles and links (exit 0, a WARNING line) and is
    # the magenta error texture in game, so an unexpected one fails the stage.
    evidence.errors = _unique(
        evidence.errors
        + [f"material '{m}' is missing: it renders as the error texture"
           for m in evidence.unexpected_missing_materials]
    )

    evidence.umbra_volume_unset = bool(_UMBRA_UNSET.search(plain))
    if evidence.umbra_volume_unset:
        evidence.notes.append("umbra volume not set")
    evidence.sky_restricted = bool(_SKY_RESTRICTED.search(plain))
    if evidence.sky_restricted:
        evidence.notes.append("restricting BSP to sky brushes")
    evidence.curve_collision = bool(_CURVE_COLLISION.search(plain))
    if evidence.curve_collision:
        evidence.notes.append("building curve/terrain collision")
    evidence.caulk_terrain_patches = bool(_CAULK_TERRAIN.search(plain))
    if evidence.caulk_terrain_patches:
        evidence.notes.append("terrain patches with caulk were discovered")
    # The compiler prints "Writing <map>_navvolume.hkt" whether or not it
    # wrote one, so this warning is the only thing that says the file is
    # absent on purpose: the map has no nav_volume brush, and by the tool's
    # own wording that costs flying units their pathing, not the walkers.
    evidence.navvolume_skipped = bool(_NAVVOLUME_SKIPPED.search(plain))
    if evidence.navvolume_skipped:
        evidence.notes.append(
            "navvolume generation skipped (no nav_volume brush): flying units have no pathing"
        )
    return evidence


def read_link_log(text: str) -> StageEvidence:
    """Parse ``linker_modtools.exe`` output (Section 7.3, Link).

    Per-asset ``DROPPED VERTS`` warnings are noise and are collected apart
    from the errors; the ``done: <m>m<s>s`` tails are kept as completion
    lines, one per fastfile.
    """
    plain = strip_colour(text)
    evidence = StageEvidence(errors=_error_lines(plain))
    # A declared asset the linker could not find is a failure whatever word
    # it prints, and this one prints "WARNING" and finishes.  Merged into the
    # errors the same way read_bake_log merges its own second pattern.
    evidence.errors = _unique(
        evidence.errors
        + [match.group(0).strip() for match in _MISSING_STRINGTABLE.finditer(plain)]
    )
    evidence.ignored_asset_warnings = _unique(_DROPPED_VERTS.findall(plain))
    evidence.completion_lines = [line.strip() for line in _DONE_TAIL.findall(plain)]
    materials = _unique(_MISSING_MATERIAL.findall(plain))
    evidence.missing_materials = materials
    evidence.benign_missing_materials = [m for m in materials if m in BENIGN_MISSING_MATERIALS]
    # A missing material compiles and links (exit 0, a WARNING line) and is
    # the magenta error texture in game, so an unexpected one fails the stage.
    evidence.errors = _unique(
        evidence.errors
        + [f"material '{m}' is missing: it renders as the error texture"
           for m in evidence.unexpected_missing_materials]
    )
    if evidence.ignored_asset_warnings:
        evidence.notes.append(
            f"{len(evidence.ignored_asset_warnings)} per-asset conversion warnings ignored"
        )
    return evidence


def read_refresh_log(text: str) -> StageEvidence:
    """Parse ``gdtdb.exe /update`` output (Section 7.3, Asset database refresh)."""
    plain = strip_colour(text)
    evidence = StageEvidence(errors=_error_lines(plain))
    evidence.completion_lines = [line.strip() for line in _GDT_PROCESSED.findall(plain)]
    evidence.duplicate_assets = _unique(
        [f"{kind} '{name}'" for kind, name in _DUPLICATE_ASSET.findall(plain)]
    )
    if evidence.duplicate_assets:
        evidence.notes.append(f"{len(evidence.duplicate_assets)} duplicate assets")
    return evidence


def read_bake_log(text: str) -> StageEvidence:
    """Parse ``radiant_modtools.exe`` bake output.

    Two parts. The console: Radiant prints ``LED Exported for <map>`` on
    success and ``Error: Failed to export ...`` on failure, and Wine's own
    loader failures land here too; it is scanned like every other stage.
    Then, after :data:`RADIANT_LOG_MARKER`, Radiant's own log when the runner
    could attach it. Its ``ERROR:`` lines are **not** failures: a successful
    bake of a test map on Windows printed the same
    ``Can't find xmodel ... in gdtDB`` lines and exported anyway [measured].
    What that log must contain is ``Export Done``; a log without
    it belongs to a bake that did not finish, whatever is on disk.
    """
    plain = strip_colour(text)
    console, _, radiant = plain.partition(RADIANT_LOG_MARKER)
    evidence = StageEvidence(errors=_error_lines(console))
    evidence.errors += [match.group(0).strip() for match in _BAKE_FAILED.finditer(plain)]
    evidence.completion_lines = [m.group(0).strip() for m in _BAKE_EXPORTED.finditer(console)]
    if radiant.strip():
        evidence.completion_lines += [m.group(0).strip() for m in _BAKE_PHASE.finditer(radiant)]
        evidence.ignored_asset_warnings = _unique(_RADIANT_ERROR.findall(radiant))
        from ..materials import PLACEHOLDER_IMAGES  # local: materials sits above

        evidence.errors += [
            f"material '{material}' uses the placeholder image '{image}': it "
            "renders magenta with DELETE lettering"
            for image, material in _unique(_FAILED_IMAGE.findall(radiant))
            if image.lower() in PLACEHOLDER_IMAGES
        ]
        if evidence.ignored_asset_warnings:
            evidence.notes.append(
                f"{len(evidence.ignored_asset_warnings)} asset ERROR lines in Radiant.log "
                "ignored (Windows's successful bake prints the same kind)"
            )
        if not _BAKE_EXPORT_DONE.search(radiant):
            evidence.errors.append(
                "Radiant.log has no 'Export Done' line: the bake did not finish"
            )
    evidence.errors = _unique(evidence.errors)
    return evidence
