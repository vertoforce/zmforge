"""Static checks over the files a commit wrote.

Spec section 9 is explicit that these run on the **text that was written**,
parsed back with the reader, not on the in-memory objects that produced it.
That is the whole point: the compiler reads the text, so a check that trusts
the model would pass while the file was wrong.
"""

from __future__ import annotations

import csv
import io
import re
from itertools import zip_longest
from pathlib import Path

from ..blueprint.elements import STOCK_PLAYER_SLOTS
from ..mapsource import parse_map_text
from ..mapsource.document import GUID_RE, Document, OpaqueSolid, PatchSolid, BrushSolid
from ..mapsource.scalars import NUMBER_RE
from ..images.png import ImageError, read_png_header
from ..materials import BENIGN_MISSING, is_catalogued, is_pipeline_material
from ..spatial import Axis, Point, Span
from ..blueprint.catalogue import (
    LEGACY_ZOMBIE_SPAWNER_CLASS,
    LEVEL_WEAPONS,
    ZOMBIE_SPAWNER_CLASS,
)
from ..emit.manifest import ASSET_PREFIXES
from ..emit.sound import (
    ALIAS_ROW_CEILING,
    BANK_SUFFIX,
    LOCALISED_BANK_SUFFIX,
    count_alias_rows,
)
from ..emit.weapons import (
    COST_COLUMN,
    NAME_COLUMN,
    STOCK_TABLE,
    TABLE_LOADER,
    WEAPON_TABLE_COLUMNS,
    parse_table,
)
from ..toolchain.layout import LOADING_IMAGE_SIZE
from ..script.gsc import dev_only_calls, scan as gsc_scan, strip_noise as gsc_strip_noise
from ..script.symbols import unresolved as stock_unresolved
from .documented import check_light_lod
from .model import RISER_REACH_FLOOR, RISER_REACH_WARN
from .playtest import check_files_playtest
from .report import Report, error, warning

__all__ = [
    "check_map_text",
    "check_gameplay",
    "check_server_script",
    "check_client_script",
    "check_manifest",
    "check_declarations",
    "check_presentation",
    "check_script_soundness",
    "check_purchase_text",
    "check_sound_bank",
    "check_packed_sound",
    "check_linked_sound_audio",
    "deps_audio_files",
    "packed_bank_evidence",
    "check_prop_collision_files",
    "check_collmap_primitives",
    "collmap_primitives",
    "check_weapon_table",
    "check_weapon_table_wiring",
    "check_written_files",
    "check_prop_layout_text",
]

_HEADER = "iwmap 4"
_STARTING = '"script_startingnumber" 0'
_LAYER_LINE = re.compile(r'^"[^"]*"\s+flags\b')
_PAIR_LINE = re.compile(r'^"[^"]+" ".*"$')
_TAGGED_LINE = re.compile(r'^(guid|layer) ".*"$')
_ENTITY_COMMENT = re.compile(r"^// entity (\d+)$")
_BRUSH_COMMENT = re.compile(r"^// brush (\d+)$")
_NUMERIC_TOKEN = re.compile(r"^[-+]?[0-9.][0-9.eE+-]*$")
_FACE_LINE = re.compile(
    r"^\s*"
    r"(?:\(\s*\S+\s+\S+\s+\S+\s*\)\s*){3}"
    r"(\S+)\s+"
    r"(?:\S+\s+){6}"
    r"(\S+)\s+"
    r"((?:\S+\s*){6})"
    r"(.*)$"
)

_KNOWN_TRAILING = re.compile(
    r"^(?:smoothing\s+\S+|decalLayerSort\s+\"[^\"]*\"\s+decalEditorSort\s+-?\d+)?$"
)


# --------------------------------------------------------------------------
# Text format (spec 9.1)
# --------------------------------------------------------------------------
def check_map_text(text: str, *, label: str = "map") -> Report:
    """F1-F9 over one emitted ``.map``."""
    report = Report()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]

    if not lines or lines[0] != _HEADER:
        found = repr(lines[0]) if lines else "nothing"
        report.add(error("F1", f"line 1 must be {_HEADER!r}, found {found}", label))
    if len(lines) < 2 or lines[1] != _STARTING:
        found = repr(lines[1]) if len(lines) > 1 else "nothing"
        report.add(error("F1", f"line 2 must be {_STARTING!r}, found {found}", label))

    first_entity = next(
        (index for index, line in enumerate(lines) if _ENTITY_COMMENT.match(line)), None
    )
    if first_entity is None:
        report.add(error("F3", "the file contains no entity", label))
        return report
    for index in range(2, first_entity):
        if lines[index] and not _LAYER_LINE.match(lines[index]):
            report.add(
                error(
                    "F2",
                    f"expected a layer declaration before the first entity, found "
                    f"{lines[index]!r}",
                    label,
                    f"line {index + 1}",
                )
            )

    _check_numbering(lines, report, label)
    _check_pairs(lines, report, label)
    _check_numbers(lines, report, label)
    _check_faces(lines, report, label)

    document = parse_map_text(text)
    _check_guids(document, report, label)
    _check_patches(document, report, label)
    if not document.entities or document.entities[0].classname != "worldspawn":
        report.add(error("F4", "entity 0 must be the worldspawn", label))
    return report


def _check_numbering(lines: list[str], report: Report, label: str) -> None:
    expected_entity = 0
    expected_brush = 0
    for index, line in enumerate(lines):
        match = _ENTITY_COMMENT.match(line)
        if match:
            if int(match.group(1)) != expected_entity:
                report.add(
                    error(
                        "F3",
                        f"entities must be numbered consecutively; expected "
                        f"{expected_entity}, found {match.group(1)}",
                        label,
                        f"line {index + 1}",
                    )
                )
            expected_entity = int(match.group(1)) + 1
            expected_brush = 0
            continue
        match = _BRUSH_COMMENT.match(line)
        if match:
            if int(match.group(1)) != expected_brush:
                report.add(
                    error(
                        "F3",
                        f"brushes must be numbered consecutively within their "
                        f"entity; expected {expected_brush}, found {match.group(1)}",
                        label,
                        f"line {index + 1}",
                    )
                )
            expected_brush = int(match.group(1)) + 1


def _check_pairs(lines: list[str], report: Report, label: str) -> None:
    for index, line in enumerate(lines):
        if not line.startswith('"'):
            continue
        if index == 1 or _LAYER_LINE.match(line):
            continue
        if not _PAIR_LINE.match(line):
            report.add(
                error(
                    "F6",
                    f"key/value lines must be two quoted strings, found {line!r}",
                    label,
                    f"line {index + 1}",
                )
            )


def _check_numbers(lines: list[str], report: Report, label: str) -> None:
    for index, line in enumerate(lines):
        if line.startswith("//"):
            continue
        for raw in line.replace("(", " ").replace(")", " ").split():
            token = raw.strip('"')
            if not token or not _NUMERIC_TOKEN.match(token):
                continue
            if "e" in token or "E" in token:
                report.add(
                    error(
                        "F7",
                        f"exponent notation is never written into a .map: {token!r}",
                        label,
                        f"line {index + 1}",
                    )
                )
            elif token == "-0" or not NUMBER_RE.match(token):
                report.add(
                    error(
                        "F7",
                        f"{token!r} is not a plain decimal with no negative zero",
                        label,
                        f"line {index + 1}",
                    )
                )


def _check_faces(lines: list[str], report: Report, label: str) -> None:
    for index, line in enumerate(lines):
        stripped = line.strip()
        # A patch control group opens with a bare "(" on its own line; a face
        # line always carries three point triples, so require them.
        if not stripped.startswith("(") or stripped.count("(") < 3:
            continue
        match = _FACE_LINE.match(line)
        if not match:
            report.add(
                error(
                    "F8",
                    f"face line is not three points, a material, six numbers, a "
                    f"lightmap material and six numbers: {stripped!r}",
                    label,
                    f"line {index + 1}",
                )
            )
            continue
        trailing = match.group(4).strip()
        if trailing and not _KNOWN_TRAILING.match(trailing):
            report.add(
                warning(
                    "F8",
                    f"unrecognised trailing tokens on a face line: {trailing!r}",
                    label,
                    f"line {index + 1}",
                )
            )


def _check_guids(document: Document, report: Report, label: str) -> None:
    seen: set[str] = set()

    def note(guid: str | None, what: str) -> None:
        if guid is None:
            report.add(error("F5", f"{what} has no guid line", label))
            return
        if not GUID_RE.match(guid):
            report.add(
                error("F5", f"{what} has a malformed guid {guid!r}", label)
            )
        if guid in seen:
            report.add(error("F5", f"guid {guid} is used more than once", label))
        seen.add(guid)

    for number, entity in enumerate(document.entities):
        note(entity.guid, f"entity {number}")
        for brush_number, solid in enumerate(entity.solids):
            note(solid.guid, f"entity {number} brush {brush_number}")


def _check_patches(document: Document, report: Report, label: str) -> None:
    # A solid the reader had to keep as verbatim text is one whose shape is not
    # the format's.  The compiler is stricter still: a ``layer`` line between a
    # patch container's guid and its keyword made cod2map64 stop with
    # "MatchToken: got 'mesh', expected '('" (a test map),
    # while this check let it through because the reader tolerated it.
    for number, entity in enumerate(document.entities):
        for brush_number, solid in enumerate(entity.solids):
            if isinstance(solid, OpaqueSolid):
                why = next(
                    (n for n in document.notes if "kept verbatim" in n), "no note"
                )
                report.add(
                    error(
                        "F9",
                        f"entity {number} brush {brush_number} is not in a shape "
                        f"the reader knows ({why})",
                        label,
                    )
                )
    for entity in document.entities:
        for solid in entity.solids:
            if not isinstance(solid, PatchSolid):
                continue
            if solid.width < 1 or solid.height < 1:
                report.add(
                    error("F9", f"patch {solid.guid} has no control points", label)
                )
                continue
            for group in solid.grid:
                if len(group) != solid.height:
                    report.add(
                        error(
                            "F9",
                            f"patch {solid.guid} declares {solid.height} vertices "
                            f"per group but a group holds {len(group)}",
                            label,
                        )
                    )
            if solid.kind == "mesh" and solid.subdivision != 0:
                report.add(
                    warning(
                        "F9",
                        f"every real mesh carries 0 in the third dimension field, "
                        f"this one carries {solid.subdivision}",
                        label,
                    )
                )


# --------------------------------------------------------------------------
# Gameplay (spec 9.4)
# --------------------------------------------------------------------------
def _origin_of(entity) -> Point | None:
    raw = entity.value("origin")
    if raw is None:
        return None
    parts = raw.split()
    if len(parts) != 3:
        return None
    try:
        return Point(*(float(p) for p in parts))
    except ValueError:
        return None


def _brush_bounds(entity) -> Span | None:
    points: list[Point] = []
    for solid in entity.solids:
        if isinstance(solid, BrushSolid):
            for facet in solid.facets:
                points.extend(facet.points)
        elif isinstance(solid, PatchSolid):
            for group in solid.grid:
                points.extend(vertex.position for vertex in group)
    if not points:
        return None
    return Span.flat_ok(
        Point(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)),
        Point(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)),
    )


def check_gameplay(
    document: Document,
    script: str,
    *,
    client_script: str | None = None,
    strict_materials: bool = False,
    player_slots: int | None = None,
) -> Report:
    """Z1, Z3-Z9, Z11, Z12, Z26, Z28 over a parsed map and the script beside it.

    ``player_slots`` pins the initial-spawn struct count exactly.  Left out,
    the count only has to reach :data:`STOCK_PLAYER_SLOTS`, because a map
    built for eight is a valid four-player map and the checker reads the
    written file rather than the model that chose the number.

    ``client_script`` is the ``.csc`` text beside the ``.gsc``.  Given, Z9
    asks its perk question of both scripts and of the agreement between
    them; left out, only the server script is read, which is what a caller
    holding one file can answer.
    """
    report = Report()
    _check_spawn_set(document, report, player_slots)
    _check_player_cap(document, script, report)
    volumes = _check_zone_volumes(document, script, report)
    _check_spawn_structs(document, volumes, report)
    _check_zone_spawn_coverage(document, report)
    _check_factories(document, report)
    _check_door_entities(document, script, report)
    _check_barricades(document, report)
    _check_perk_modules(document, script, client_script, report)
    _check_wunderfizz(document, script, client_script, report)
    _check_custom_perks(document, script, client_script, report)
    _check_clientfield_window(script, client_script, report)
    _check_clientfield_pairs(script, client_script, report)
    _check_lighting_entities(document, report)
    _check_reflection_probes(document, report)
    _check_face_materials(document, report, strict_materials)
    # Z78: a sealed start (script.splitstart) respawns nobody in a sealed zone.
    from .sealed_start import check_sealed_start

    check_sealed_start(document, script, report)
    # Z86: every respawn struct has a target group a player can stand on.
    from .respawn_points import check_respawn_points

    check_respawn_points(document, report)
    # Z83: at most one sealed pocket of air holds player spawns (Umbra).
    from .umbra_air import check_umbra_air

    check_umbra_air(document, report)
    # Z87: one gamble machine, paid for only when affordable.
    from .gamble import check_gamble_script

    check_gamble_script(script, report)
    return report


def _check_spawn_set(
    document: Document, report: Report, expect_slots: int | None = None
) -> None:
    structs = document.entities_of("script_struct")
    respawn = [e for e in structs if e.value("targetname") == "player_respawn_point"]
    if not respawn:
        report.add(error("Z1", "expected a player_respawn_point per zone, found none"))
    initial = [
        e
        for e in structs
        if e.value("targetname") == "initial_spawn_points"
        and e.value("script_noteworthy") == "initial_spawn"
    ]
    if len(initial) < STOCK_PLAYER_SLOTS:
        report.add(
            error(
                "Z1",
                f"expected at least {STOCK_PLAYER_SLOTS} initial spawn structs, "
                f"found {len(initial)}",
            )
        )
    if expect_slots is not None and len(initial) != expect_slots:
        report.add(
            error(
                "Z1",
                f"expected {expect_slots} initial spawn structs, found {len(initial)}",
            )
        )
    for entity in initial:
        if entity.value("script_int") is not None:
            report.add(
                error(
                    "Z1",
                    "an initial-spawn struct must not carry script_int: on this "
                    "struct that key is the team side, and getfreespawnpoint "
                    f"deletes every struct whose script_int is 1 or 2 (found "
                    f"{entity.value('script_int')!r})",
                )
            )
    for entity in initial + respawn:
        tokens = (entity.value("script_string") or "").split()
        if "zclassic_start_room" not in tokens:
            report.add(
                error(
                    "Z1",
                    "a spawn struct's script_string must contain "
                    f"'zclassic_start_room', found {entity.value('script_string')!r}",
                )
            )
    origins = [o for o in (_origin_of(e) for e in initial) if o is not None]
    for index, left in enumerate(origins):
        for right in origins[index + 1 :]:
            if left.distance_to(right) < 32.0:
                report.add(
                    error(
                        "Z1",
                        f"two initial spawn points are {left.distance_to(right):.1f} "
                        "units apart; they must be at least 32",
                    )
                )


#: ``level.player_too_many_players_check = <value>;`` as the emitter writes
#: it, and as a caller could reasonably write it by hand.
_PLAYER_CAP_RE = re.compile(
    r"level\.player_too_many_players_check\s*=\s*([^;]*);"
)


def _check_player_cap(document: Document, script: str, report: Report) -> None:
    """Z26: a map with more than four spawn slots must lift the cap itself.

    A map that carries more than :data:`STOCK_PLAYER_SLOTS` initial-spawn
    structs is claiming to seat more than four players.  On stock scripts
    the structs alone do not: ``_zm.gsc:7067 player_too_many_players_check``
    takes ``max_players = 4`` outside ``zgrief``/``zmeat``, and above that
    freezes the players and notifies ``end_game``.  ``_zm.gsc:1865`` threads
    it out of ``onPlayerSpawned``, so the fifth player to spawn ends the
    match rather than merely sharing a spawn point.

    The one lever a map has is ``level.player_too_many_players_check``,
    written ``true`` at ``_zm.gsc:252`` in ``zm::init()`` -- which the
    framework entry reaches synchronously through ``load::main()``
    (``_load.gsc:79``) -- and read on spawn.  So the assignment counts only
    *after* ``zm_usermap::main()``; before it, the framework overwrites it
    and the map is back to four.  That is the same shape as Z10's rule for
    ``level.dog_rounds_allowed``, with the sides swapped.

    This is read out of the stock scripts on the mod tools install, not played.
    """
    initial = [
        entity
        for entity in document.entities_of("script_struct")
        if entity.value("targetname") == "initial_spawn_points"
        and entity.value("script_noteworthy") == "initial_spawn"
    ]
    # Comments blanked, so a commented-out assignment is not mistaken for one.
    text = "\n".join(gsc_strip_noise(script))
    entry = text.find("zm_usermap::main()")
    assignments = list(_PLAYER_CAP_RE.finditer(text))
    lifted = [
        match
        for match in assignments
        if match.group(1).strip() in ("false", "0")
        and entry >= 0
        and match.start() > entry
    ]
    if len(initial) > STOCK_PLAYER_SLOTS and not lifted:
        early = [m for m in assignments if entry >= 0 and m.start() < entry]
        detail = (
            f"the map carries {len(initial)} initial spawn structs, which "
            f"claims more than {STOCK_PLAYER_SLOTS} players, but the script "
            "never sets level.player_too_many_players_check = false after "
            "zm_usermap::main(); on stock scripts the fifth player to spawn "
            "is frozen and the game ends (_zm.gsc:7067, threaded at :1865)"
        )
        if early:
            detail += (
                "; the assignment it does carry is before the framework "
                "entry, where zm::init() overwrites it (_zm.gsc:252)"
            )
        report.add(error("Z26", detail))
    if len(initial) <= STOCK_PLAYER_SLOTS and lifted:
        report.add(
            warning(
                "Z26",
                "the script turns the framework's player-count check off but "
                f"the map has only {len(initial)} initial spawn structs, so "
                "players past the fourth all spawn on the first struct",
            )
        )


def _init_zones(script: str) -> list[str]:
    found = re.findall(r"init_zones\[(\d+)\]\s*=\s*\"([^\"]+)\"\s*;", script)
    return [name for _, name in sorted(found, key=lambda item: int(item[0]))]


def _zone_edges(script: str) -> list[tuple[str, str]]:
    """The zone pairs the script joins, by whichever call it used.

    Three forms reach the same place, and only the first is what this package
    emits:

    * ``add_adjacent_zone( a, b, flag )`` -- the door form,
      ``_zm_zonemgr.gsc:595``;
    * ``add_adjacent_zone( a, b )`` -- the same function with ``flag_name``
      left undefined.  What the engine does with an undefined array key is not
      something this repo can measure, but the pair is plainly *meant* to be
      joined, so it is read as an edge rather than reported as a zone nothing
      enables;
    * ``connect_zones( a, b )`` -- ``_zm_zonemgr.gsc:772``, which is the
      two-argument join the stock scripts actually provide: it ``zone_init``s
      both, ``enable_zone``s both and sets ``is_connected = true`` with no
      flag anywhere.

    Missing either of the last two reports the far zone as "registered but
    never enabled", which is an error, on a map that is fine.
    """
    return [
        (a, b)
        for a, b in re.findall(
            r"(?:add_adjacent_zone|connect_zones)\(\s*\"([^\"]+)\"\s*,"
            r"\s*\"([^\"]+)\"\s*(?:,[^)]*)?\)",
            script,
        )
    ]


def _enabled_zones(script: str) -> tuple[set[str], set[str]]:
    """``(registered, ever enabled)`` zone names, as the zone manager sees them.

    ``zm_zonemgr::manage_zones`` runs the map's zone hook, then calls
    ``zone_init`` and ``enable_zone`` on every entry of the array it was
    passed (``_zm_zonemgr.gsc:810``), so an ``init_zones`` name is registered
    and enabled from the start.  ``add_adjacent_zone`` (:595) calls
    ``zone_init`` on both of its zones but enables neither: an adjacent zone
    is enabled later, when its flag connects it to a zone that is already
    enabled.  A name in neither place is in no ``level.zones`` entry at all,
    and ``zone_is_enabled`` returns false for it forever (:65).

    That distinction is the whole point of the check that uses this.  A
    volume naming an unregistered or never-enabled zone is not inert: the
    playable-area monitor counts a player standing inside it as out of
    bounds and kills them outright (``_zm.gsc:1999`` and :2035).
    """
    listed = _init_zones(script)
    edges = _zone_edges(script)
    registered = set(listed) | {name for pair in edges for name in pair}
    enabled = set(listed)
    changed = True
    while changed:
        changed = False
        for left, right in edges:
            for near, far in ((left, right), (right, left)):
                if near in enabled and far not in enabled:
                    enabled.add(far)
                    changed = True
    return registered, enabled


def _check_zone_volumes(
    document: Document, script: str, report: Report
) -> dict[str, list[Span]]:
    volumes = [
        e
        for e in document.entities_of("info_volume")
        if e.value("script_noteworthy") == "player_volume"
    ]
    listed = _init_zones(script)
    registered, enabled = _enabled_zones(script)
    # One spawn set, several volumes.  Stock ``zone_init`` gathers every
    # ``info_volume`` carrying the zone's targetname (``_zm_zonemgr.gsc:318``),
    # and in ``map_source/zm/zm_giant.map`` each of the 12 zone names carries
    # its own ``target`` on every one of its volumes -- ``outside_south_zone``
    # on six of them, all naming ``outside_south_spawners``.  So this is a
    # target to *all* its boxes, and a struct is inside its zone if it is
    # inside any of them.
    bounds: dict[str, list[Span]] = {}
    named: set[str] = set()
    for entity in volumes:
        name = entity.value("targetname")
        if not name:
            report.add(error("Z3", "a player_volume has no targetname, so it names no zone"))
            continue
        named.add(name)
        if name not in registered:
            report.add(
                error(
                    "Z3",
                    f"player_volume {name!r} names a zone the script never registers: "
                    "it is in no init_zones entry and no add_adjacent_zone call, so "
                    "zone_is_enabled is false for it and a player standing inside "
                    "this volume is out of the playable area and is killed outright",
                )
            )
        elif name not in enabled:
            report.add(
                error(
                    "Z3",
                    f"player_volume {name!r} names a zone that is registered but "
                    "never enabled: no init_zones entry and no chain of "
                    "add_adjacent_zone flags reaches it from one, so it is never "
                    "playable area and a player inside it is killed outright",
                )
            )
        # A registered zone that is not in init_zones is the normal case since
        # G1: it is playable once its door flag connects it, which
        # is what a door is for.  Z67 checks the other direction (a door-gated
        # zone that *is* listed).
        box = _brush_bounds(entity)
        if box is not None:
            bounds.setdefault(entity.value("target") or name, []).append(box)
    for name in sorted(registered - named):
        report.add(
            error(
                "Z3",
                f"the script registers zone {name!r} and no player_volume carries "
                "that targetname, so zone_init finds no volume for it (its asserts "
                "fire in a dev build and it collects no spawn locations)",
            )
        )
    # Counted by zone *name*, never by volume.  One zone owns as many
    # ``info_volume``s as it likes: ``zone_init`` builds ``zone.volumes`` from
    # ``GetEntArray( zone_name, "targetname" )`` (``_zm_zonemgr.gsc:318``), so
    # every volume carrying the name joins the zone.  Treyarch's own
    # ``map_source/zm/zm_giant.map`` carries **32** player volumes over 12 zone
    # names and ``zm_giant.gsc:183`` lists exactly **one** init_zones entry, so
    # a count comparison would report the shipped map as broken by 31.  What
    # is left is the name comparison, and both directions of it are reported
    # above: a volume naming a zone no script registers, and a registered zone
    # with no volume.
    duplicated = sorted({name for name in listed if listed.count(name) > 1})
    for name in duplicated:
        report.add(
            warning(
                "Z3",
                f"init_zones lists {name!r} {listed.count(name)} times; "
                "zone_init returns early on a zone it has already made, so "
                "the repeats do nothing",
            )
        )
    return bounds


#: The ``script_noteworthy`` tokens ``_zm_zonemgr.gsc`` files into a zone's
#: ``a_loc_types[ "zombie_location" ]`` bucket, which is the list both round
#: loops draw a spawn point from.  Read from the switch at
#: ``_zm_zonemgr.gsc:371-374`` (``zone_init``); the same switch is repeated at
#: ``:464-469`` in ``reinit_zone_spawners``, where it also accepts
#: ``spawner_location``.  ``custom_spawner_entry`` is in the engine's set and
#: not in ours, because it needs a second token naming a handler this package
#: does not emit.
#:
#: Which one a struct carries decides only *how the zombie arrives*, measured
#: in ``_zm_utility.gsc:220-290`` (``move_zombie_spawn_location``):
#: ``riser_location`` threads ``zm_spawner::do_zombie_rise``, which ghosts the
#: body, plays the dirt burst and dust (``zombie_rise_fx``) and animates
#: ``ai_zombie_traverse_ground_climbout_fast``; ``spawn_location`` moves an
#: anchor to the struct, turns it at the goal, plays ``level.zombie_spawn_fx``
#: if the level defined one, and shows the zombie standing with no animation;
#: ``faller_location`` threads ``zm_ai_faller::do_zombie_fall``.  Nothing else
#: about the struct changes, which is why every check that reasons about spawn
#: structs has to take the whole set rather than the riser alone.
ZOMBIE_LOCATION_MARKERS = frozenset(
    {"riser_location", "spawn_location", "faller_location"}
)


def _check_spawn_structs(
    document: Document, volumes: dict[str, list[Span]], report: Report
) -> None:
    markers = ZOMBIE_LOCATION_MARKERS
    for entity in document.entities_of("script_struct"):
        marker = entity.value("script_noteworthy")
        if marker not in markers:
            continue
        target = entity.value("targetname")
        if target not in volumes:
            report.add(
                error(
                    "Z4",
                    f"spawn struct tagged {target!r} matches no zone volume's target",
                )
            )
            continue
        if not entity.value("script_string"):
            report.add(error("Z4", f"spawn struct tagged {target!r} has no script_string"))
        origin = _origin_of(entity)
        if origin is None:
            report.add(error("Z4", f"spawn struct tagged {target!r} has no origin"))
            continue
        if entity.value("script_string") == "find_flesh" and not any(
            box.holds_flat(origin.x, origin.y, tolerance=1e-6)
            for box in volumes[target]
        ):
            boxes = len(volumes[target])
            report.add(
                error(
                    "Z4",
                    f"an interior spawn for {target!r} sits outside "
                    + (
                        "its zone volume"
                        if boxes == 1
                        else f"all {boxes} of its zone's volumes"
                    )
                    + f" at ({origin.x:g}, {origin.y:g})",
                )
            )


def _check_zone_spawn_coverage(document: Document, report: Report) -> None:
    """Z4 per zone, not per map: a zone whose spawn set is empty.

    ``_check_factories`` holds the map-wide half, and map-wide is the right
    scope for *it*: the framework picks the spawner entity at random from
    every ``zombie_spawner`` in the level and the location separately from
    the active zones' structs (``_zm.gsc``: ``spawn_point =
    array::random( level.zm_loc_types[ "zombie_location" ] ); spawner =
    array::random( level.zombie_spawners );``), so one factory serves the
    whole map.  The *locations* are per zone and nothing shares them:
    ``zone_init`` reads ``struct::get_array( zone.volumes[ 0 ].target,
    "targetname" )``, ``create_spawner_list`` gathers only from zones that
    are enabled, active and spawning, and ``manage_zones`` makes a zone
    active only while a player is inside it or a set flag connects it to one
    that is.  A player standing alone in a zone with no structs therefore
    leaves the global location list empty, and both round loops in
    ``_zm.gsc`` wait on that list rather than time out.
    """
    markers = ZOMBIE_LOCATION_MARKERS
    spawn_sets = {
        entity.value("targetname")
        for entity in document.entities_of("script_struct")
        if markers & set((entity.value("script_noteworthy") or "").split())
    }
    for entity in document.entities_of("info_volume"):
        if entity.value("script_noteworthy") != "player_volume":
            continue
        name = entity.value("targetname") or "<no targetname>"
        target = entity.value("target")
        if not target:
            report.add(
                error(
                    "Z4",
                    f"zone volume {name!r} has no target, so zone_init takes the "
                    "branch that collects no spawn locations at all and the zone "
                    "can never spawn a zombie",
                )
            )
        elif target not in spawn_sets:
            report.add(
                error(
                    "Z4",
                    f"zone {name!r} collects spawn set {target!r} and no spawn "
                    "struct carries that targetname, so the zone has no spawn "
                    "location: a player alone in it leaves the game's location "
                    "list empty and the round never starts",
                )
            )


def _check_factories(document: Document, report: Report) -> None:
    factories = [
        e
        for e in document.entities
        if e.value("script_noteworthy") == "zombie_spawner"
    ]
    if not factories:
        report.add(
            error("Z5", "no entity is tagged zombie_spawner, so no zombie is ever made")
        )
    for entity in factories:
        if entity.classname == LEGACY_ZOMBIE_SPAWNER_CLASS:
            report.add(
                warning(
                    "Z5",
                    f"this zombie_spawner is a {LEGACY_ZOMBIE_SPAWNER_CLASS}, the "
                    "older of the two zombie aitypes the install ships. It works "
                    "-- the linker resolves it and packs it -- but its animation "
                    "mapping table names 527 animations against the 635 in "
                    f"zm_levelcommon, and 78 of the 140 it omits are traversal "
                    "moves (every jump, mantle and climb, and all nine "
                    "traverse_procedural). Window traversals are in both, so "
                    "barricades are unaffected. "
                    f"{ZOMBIE_SPAWNER_CLASS} is what "
                    "share/zone_source/zm_levelcommon.zone:51 declares for a "
                    "usermap. It is not free: measured A/B on one map with only "
                    "this classname changed, it packs 112 more animations and "
                    "3,986,944 more bytes of fastfile",
                )
            )
        elif entity.classname != ZOMBIE_SPAWNER_CLASS:
            report.add(
                error(
                    "Z5",
                    f"a zombie_spawner must be a {ZOMBIE_SPAWNER_CLASS} or a "
                    f"{LEGACY_ZOMBIE_SPAWNER_CLASS} -- those are the only two "
                    "zombie aitypes in archetypes/archetypes.gdt, and an entity "
                    "whose classname names no aitype spawns nothing -- found "
                    f"{entity.classname!r}",
                )
            )


def _check_door_entities(document: Document, script: str, report: Report) -> None:
    edges = re.findall(
        r"add_adjacent_zone\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*\)",
        script,
    )
    # A zone is known if the script lists it or a player_volume carries it:
    # since G1 init_zones holds only the zones open at load, and
    # a door-gated zone is registered by its add_adjacent_zone call alone.
    zone_names = set(_init_zones(script)) | {
        e.value("targetname")
        for e in document.entities_of("info_volume")
        if e.value("script_noteworthy") == "player_volume" and e.value("targetname")
    }
    for trigger in document.entities_of("trigger_use"):
        if trigger.value("targetname") != "zombie_door":
            continue
        name = trigger.value("target")
        leaves = [
            e
            for e in document.entities_of("script_brushmodel")
            if e.value("targetname") == name
        ]
        if not leaves:
            report.add(error("Z7", f"door {name!r} has no script_brushmodel collision"))
        models = [
            e for e in document.entities_of("script_model") if e.value("targetname") == name
        ]
        for part in leaves + models:
            if part.value("DYNAMICPATH") != "1":
                report.add(
                    error(
                        "Z30",
                        f"door {name!r} has a {part.value('classname')} part without "
                        "DYNAMICPATH set to 1; the door still opens and the AI paths "
                        "through the opening are never rejoined",
                    )
                )
        vectors = {e.value("script_vector") for e in leaves + models}
        if len(vectors) > 1:
            report.add(
                error("Z7", f"door {name!r} parts disagree about script_vector: {vectors}")
            )
        origin = _origin_of(trigger)
        box = _brush_bounds(trigger)
        if origin is None:
            report.add(error("Z7", f"door trigger {name!r} has no explicit origin"))
        elif box is not None and not box.holds(origin, tolerance=1e-6):
            report.add(error("Z7", f"door trigger {name!r} has its origin outside its brush"))
        _check_door_trigger_size(name, box, leaves, report)
        cost = trigger.value("zombie_cost")
        if cost is None or not cost.isdigit() or int(cost) <= 0:
            report.add(error("Z7", f"door {name!r} has a non-positive zombie_cost {cost!r}"))
        flag = trigger.value("script_flag")
        matching = [e for e in edges if e[2] == flag]
        if len(matching) != 1:
            report.add(
                error(
                    "Z7",
                    f"door flag {flag!r} appears in {len(matching)} add_adjacent_zone "
                    "calls; it must appear in exactly one",
                )
            )
        for edge in matching:
            for zone in edge[:2]:
                if zone not in zone_names:
                    report.add(
                        error("Z7", f"add_adjacent_zone names unknown zone {zone!r}")
                    )


def _check_door_trigger_size(
    name: str, box, leaves: list, report: Report
) -> None:
    """Z7: a door buy prompt appears at the door and nowhere else.

    The trigger is the volume the prompt lives in, so its size *is* the
    range at which the door can be bought.  Measured against the leaf that
    fills the opening, which is in the same file: a slab a margin wider than
    the opening, a step deep on each side of it, and never taller than the
    opening, so a player on the floor above is not offered the door.  Growing
    the leaf by 128 units on every axis instead makes each trigger 272 to 384
    units on a side and sells a door from about 150 units away.
    """
    from ..blueprint.elements import DOOR_TRIGGER_DEPTH, DOOR_TRIGGER_MARGIN

    if box is None or not leaves:
        return
    leaf = _brush_bounds(leaves[0])
    if leaf is None:
        return
    through = min((Axis.X, Axis.Y), key=lambda axis: leaf.extent(axis))
    across = Axis.Y if through is Axis.X else Axis.X
    allowed = {
        through: leaf.extent(through) + 2.0 * DOOR_TRIGGER_DEPTH,
        across: leaf.extent(across) + 2.0 * DOOR_TRIGGER_MARGIN,
        Axis.Z: leaf.extent(Axis.Z),
    }
    for axis, limit in allowed.items():
        if box.extent(axis) > limit + 1e-6:
            report.add(
                error(
                    "Z7",
                    f"door trigger {name!r} is {box.extent(axis):g} units on "
                    f"{axis.name}, past the {limit:g} its own leaf allows; the "
                    "buy prompt appears that far from the door",
                )
            )


def _check_barricades(document: Document, report: Report) -> None:
    barricades = [
        e
        for e in document.entities_of("misc_prefab")
        if "barricade" in (e.value("model") or "") and e.value("script_string")
    ]
    # Any zombie-location mode, not the riser alone.  A barricade's spawn is a
    # plain spawn struct and the mode is free: Treyarch's own zm_giant pairs 44
    # of its 50 ``spawn_location`` structs with a ``receiver_set_*`` barricade
    # tag and only 8 ``riser_location`` structs (measured over
    # map_source/_prefabs/zm/zm_giant/script/zm_giant_nodes.map).  Matching on
    # ``riser_location`` alone made Z8 report "matches 0 riser structs" on the
    # shipped majority pattern.
    risers = [
        e
        for e in document.entities_of("script_struct")
        if ZOMBIE_LOCATION_MARKERS & set((e.value("script_noteworthy") or "").split())
    ]
    for barricade in barricades:
        tag = barricade.value("script_string")
        linked = [r for r in risers if r.value("script_string") == tag]
        if len(linked) != 1:
            report.add(
                error(
                    "Z8",
                    f"barricade link tag {tag!r} matches {len(linked)} riser structs; "
                    "it must match exactly one",
                )
            )
            continue
        here = _origin_of(barricade)
        there = _origin_of(linked[0])
        if here is None or there is None:
            report.add(error("Z8", f"barricade {tag!r} or its riser has no origin"))
            continue
        reach = here.distance_to(there)
        # 96 is this package's default, not a rule: Treyarch's own eight
        # barricade/riser pairs in zm_giant stand 94.7 to 487.5 apart
        # (spec 4.6).  This check used to demand 96 give
        # or take 1, which would have failed seven of those eight.  The same
        # floor and warning bound as the model-level half, so the two halves
        # of Z8 cannot disagree.
        if reach < RISER_REACH_FLOOR:
            report.add(
                error(
                    "Z8",
                    f"the riser for {tag!r} stands {reach:.2f} units out, nearer "
                    f"than {RISER_REACH_FLOOR:g}; the prefab's own exterior goal "
                    "struct is 50 out, so the riser is on top of it",
                )
            )
        elif reach > RISER_REACH_WARN:
            report.add(
                warning(
                    "Z8",
                    f"the riser for {tag!r} stands {reach:.2f} units out; the "
                    "farthest shipped pair measured is 487.5, so this is unusual "
                    "rather than wrong",
                )
            )


#: ``zm_perk_random::include_perk_in_random_rotation( "<specialty>" );`` as
#: the emitter writes it, and as a caller could reasonably write it by hand.
_ROTATION_RE = re.compile(
    r'include_perk_in_random_rotation\s*\(\s*"([^"]+)"\s*\)'
)


def _check_wunderfizz(
    document: Document, script: str, client_script: str | None, report: Report
) -> None:
    """Z49: a placed Der Wunderfizz, and something for it to give.

    The machine is stock and so is everything it needs, which is what makes
    the failures quiet.  Four of them are worth naming, all read off
    ``share/raw/scripts/zm/_zm_perk_random.{gsc,csc,gsh}`` on the install,
    and **none of them observed in game**:

    *Nothing to give.*  The rotation is a separate list from the perks:
    ``include_perk_in_random_rotation`` (``:617-624``) is the only thing
    that writes ``level._random_perk_machine_perk_list``, and
    ``get_weighted_random_perk`` (``:627-658``) reads it with
    ``GetArrayKeys`` and then indexes ``keys[ 0 ]`` on the way out.  A map
    that places the machine and registers nothing has an undefined array
    under both.  A player pays 1500 and the script faults.

    *Nothing to start.*  ``init_starting_perk_random_machine_location``
    (``:123-150``) threads ``machine_think()`` on the first machine whose
    ``script_noteworthy`` contains ``start_perk_random_machine`` and sends
    every other machine to ``wait_for_power()``.  With none marked, no
    machine ever thinks and the map has furniture.

    *A perk the map cannot render.*  ``get_perk_weapon_model`` (``:725``)
    reads ``level.machine_assets[ perk ].weapon`` for whatever it is about
    to hand over, and that array is written only by a perk module
    (``_zm_perk_juggernaut.gsc:72``).  A rotation entry whose module the
    script does not carry is a bottle with no model.

    *Half a machine.*  The client half registers every clientfield the
    server half sets and precaches the four effects
    (``_zm_perk_random.csc:19-22``, ``:33-41``), so the module belongs in
    both scripts -- the same rule Z9 applies to a perk.
    """
    from ..blueprint import catalogue as fixed
    from ..blueprint.catalogue import PERKS

    machines = [
        entity
        for entity in document.entities
        if entity.value("targetname") == fixed.WUNDERFIZZ_TARGETNAME
    ]
    # ``strip_noise`` blanks string *bodies* as well as comments and is
    # length-preserving, so the stripped text says where a live call is and
    # the original says what it names.  Reading the name off the stripped
    # text would give a run of spaces.
    stripped = "\n".join(gsc_strip_noise(script))
    rotation = [
        script[match.start(1) : match.end(1)]
        for match in _ROTATION_RE.finditer(stripped)
    ]
    if not machines:
        if rotation:
            report.add(
                warning(
                    "Z49",
                    f"the script registers {len(rotation)} perks with Der "
                    "Wunderfizz but the map has no perk_random_machine "
                    "entity, so the calls do nothing",
                )
            )
        return

    using = f"#using {fixed.WUNDERFIZZ_MODULE};"
    if using not in script:
        report.add(
            error(
                "Z49",
                f"the map has {len(machines)} Der Wunderfizz but the script "
                f"is missing '{using}', so the machine has no logic",
            )
        )
    if client_script is not None and using not in client_script:
        report.add(
            error(
                "Z49",
                "the map has a Der Wunderfizz but the client script is "
                f"missing '{using}', so the machine's clientfields and its "
                "four effects are never registered",
            )
        )

    starting = [
        entity
        for entity in machines
        if fixed.WUNDERFIZZ_START_NOTEWORTHY in (entity.value("script_noteworthy") or "")
    ]
    if not starting:
        report.add(
            error(
                "Z49",
                f"none of the {len(machines)} perk_random_machine entities "
                f"carries script_noteworthy '{fixed.WUNDERFIZZ_START_NOTEWORTHY}', "
                "so no machine is ever threaded and the Wunderfizz never "
                "works (_zm_perk_random.gsc:123-150)",
            )
        )
    elif len(starting) > 1:
        report.add(
            warning(
                "Z49",
                f"{len(starting)} perk_random_machine entities are marked "
                "the starting one; the stock script takes the first and "
                "leaves the rest waiting for power",
            )
        )

    pieces = len(fixed.WUNDERFIZZ_PIECES)
    for entity in machines:
        boards = entity.value("zbarriernumboards")
        if boards is None or not boards.isdigit() or int(boards) < pieces:
            report.add(
                error(
                    "Z49",
                    "a perk_random_machine carries zbarriernumboards "
                    f"{boards!r}; the stock script drives {pieces} piece "
                    f"indices (_zm_perk_random.gsh:26-31), so fewer than "
                    f"{pieces} boards is a machine with states it cannot show",
                )
            )

    if not rotation:
        report.add(
            error(
                "Z49",
                "the map places a Der Wunderfizz and the script never calls "
                "zm_perk_random::include_perk_in_random_rotation, so the "
                "machine has no perk to give: level._random_perk_machine_"
                "perk_list is undefined and get_weighted_random_perk reads "
                "it on every use (_zm_perk_random.gsc:617-658)",
            )
        )
    modules = {perk.specialty: perk.module for perk in PERKS if perk.specialty}
    for specialty in rotation:
        module = modules.get(specialty)
        if module is None:
            report.add(
                warning(
                    "Z49",
                    f"Der Wunderfizz's rotation names '{specialty}', which "
                    "is not a perk the mod tools install ships a module for; nothing "
                    "writes level.machine_assets for it unless the map does",
                )
            )
        elif f"#using {module};" not in script:
            report.add(
                error(
                    "Z49",
                    f"Der Wunderfizz's rotation names '{specialty}' but the "
                    f"script is missing '#using {module};', so nothing "
                    "writes level.machine_assets for it and the machine "
                    "cannot render the bottle it offers "
                    "(_zm_perk_random.gsc:725)",
                )
            )


#: The framework entry both scripts call, spelled here rather than imported
#: so this module keeps reading text and not the emitter.
_ENTRY_CALL = "zm_usermap::main"

#: ``zm_perks::register_perk_basic_info( ... );`` as the emitter writes it and
#: as a hand-written script could reasonably write it: everything up to the
#: statement's semicolon, which is enough because the call is one statement.
_PERK_BASIC_RE = re.compile(r"register_perk_basic_info\s*\(([^;]*)\)\s*;")

#: The other four registrations, which all take the specialty first, and
#: whose function references say which functions belong to which perk.
_PERK_REGISTER_RE = re.compile(r"register_perk_(\w+)\s*\(([^;]*)\)\s*;")

_QUOTED_RE = re.compile(r"\"([^\"]*)\"")
_FUNC_REF_RE = re.compile(r"&(\w+)")
_BOTTLE_RE = re.compile(r"GetWeapon\s*\(\s*\"([^\"]*)\"\s*\)", re.IGNORECASE)
_HINT_RE = re.compile(r"&\"([^\"]*)\"")
_FUNCTION_RE = re.compile(r"^function\s+(\w+)\s*\(")
_UIMODEL_RE = re.compile(r"set_player_uimodel\s*\(\s*\"([^\"]*)\"")
_PRECACHE_STRING_RE = re.compile(
    r"#\s*precache\(\s*\"string\"\s*,\s*\"([^\"]+)\"\s*\)"
)

#: ``level._effect[ "<handle>" ] = "<path>";`` as a perk's precache function
#: writes it.  The path is the thing that needs a ``#precache`` on both sides.
_EFFECT_HANDLE_RE = re.compile(
    r"level\._effect\[\s*\"[^\"]*\"\s*\]\s*=\s*\"([^\"]+)\"\s*;"
)


def _function_spans(stripped: str) -> list[tuple[str, int, int]]:
    """``(name, start, end)`` for every top-level function in the text.

    The generated file puts every ``function`` at column zero and closes it
    with a ``}`` at column zero, which is what the mod tools' own raw scripts
    do as well, so this needs no parser: it needs the two column-zero
    landmarks.  A caller's own function body is indented by the emitter, so
    nothing inside one can be mistaken for the next.
    """
    spans: list[tuple[str, int, int]] = []
    name = ""
    start = 0
    position = 0
    for line in stripped.splitlines(keepends=True):
        found = _FUNCTION_RE.match(line)
        if found:
            name, start = found.group(1), position
        elif name and line.startswith("}"):
            spans.append((name, start, position + len(line)))
            name = ""
        position += len(line)
    if name:
        spans.append((name, start, position))
    return spans


def _enclosing(spans, position: int) -> str | None:
    for name, start, end in spans:
        if start <= position < end:
            return name
    return None


_REGISTER_CALL = re.compile(r"clientfield::register\s*\(")


def _check_clientfield_window(
    script: str, client_script: str | None, report: Report
) -> None:
    """Z51: every clientfield a map registers is registered before the entry.

    The engine closes clientfield registration in
    ``CodeCallback_FinalizeInitialization``, which ``callbacks_shared.gsc:
    539-546`` calls "the final step of initialization" -- and the framework
    entry **yields** before it returns: ``zm_usermap::main()`` calls
    ``load::main()`` (``zm/_load.gsc:77``), which waits at ``system::wait_till
    ( "all" )`` (``:105``).  So a ``clientfield::register`` written after
    ``zm_usermap::main();`` runs with the period already shut, and the engine
    does not warn: it refuses the map at load.

    Measured, which is why this check exists: ``zm_dmv`` built for eight seats
    linked clean and the game would not load it --

        Attempt to register ClientField laststand_update4 post finalization
        of ClientField registration period failed

    (measured on Windows).  The registration was three lines below the entry
    call.  Both scripts are read, because both halves register.
    """
    for text, side in ((script, "server"), (client_script, "client")):
        if not text:
            continue
        stripped = "\n".join(gsc_strip_noise(text))
        entry = stripped.find(f"{_ENTRY_CALL}(")
        if entry < 0:
            continue
        for match in _REGISTER_CALL.finditer(stripped):
            if match.start() <= entry:
                continue
            line = stripped[match.start() : stripped.find("\n", match.start())]
            report.add(
                error(
                    "Z51",
                    f"the {side} script calls clientfield::register after "
                    f"{_ENTRY_CALL}(), which is after the engine has closed "
                    "the registration period: the entry waits at "
                    'system::wait_till( "all" ) (zm/_load.gsc:105) and '
                    "CodeCallback_FinalizeInitialization runs while it waits "
                    "(callbacks_shared.gsc:539-546).  The map links clean and "
                    "the game refuses it at load.  Register before the entry "
                    "and leave only the level-array bookkeeping after it -- "
                    f"the call is: {line.strip()[:120]}",
                )
            )


def _split_top_level(args: str) -> list[str]:
    """Split a call's argument text on the commas at bracket depth zero."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    for char in args:
        if char == '"':
            in_string = not in_string
        elif not in_string and char in "([":
            depth += 1
        elif not in_string and char in ")]":
            depth -= 1
        elif not in_string and char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [" ".join(part.split()) for part in parts]


def clientfield_registrations(text: str) -> list[tuple[str, ...]]:
    """Every ``clientfield::register`` in a script, as the engine compares it.

    Each entry is ``(loops, pool, name, version, bits, type)``: the first five
    arguments, which both halves pass (the client's extra three -- callback,
    host-only, zero-on-new-entity -- are the client's business), with
    whitespace collapsed, and ``loops`` the headers of the ``for`` loops the
    call sits in.  The loop is part of the identity because the name is an
    expression: ``"laststand_update" + i`` is four fields or six depending on
    the bound.  Comments and developer blocks are ignored; string bodies are
    read from the original text, which :func:`gsc_strip_noise` keeps at the
    same offsets.
    """
    stripped = "\n".join(gsc_strip_noise(text))
    original = "\n".join(text.split("\n"))
    found: list[tuple[str, ...]] = []
    stack: list[str] = []
    statement_start = 0
    parens = 0
    index = 0
    length = len(stripped)
    while index < length:
        char = stripped[index]
        if char == "{":
            stack.append(" ".join(original[statement_start:index].split()))
            statement_start = index + 1
        elif char == "}":
            if stack:
                stack.pop()
            statement_start = index + 1
        elif char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif char == ";" and parens <= 0:
            statement_start = index + 1
        elif stripped.startswith("clientfield::register", index):
            match = _REGISTER_CALL.match(stripped, index)
            if match:
                depth = 1
                cursor = match.end()
                while cursor < length and depth:
                    if stripped[cursor] == "(":
                        depth += 1
                    elif stripped[cursor] == ")":
                        depth -= 1
                    cursor += 1
                args = _split_top_level(original[match.end() : cursor - 1])
                loops = " | ".join(
                    header for header in stack if header.startswith("for")
                )
                found.append((loops, *(args + [""] * 5)[:5]))
                index = cursor
                continue
        index += 1
    return found


def _check_clientfield_pairs(
    script: str, client_script: str | None, report: Report
) -> None:
    """Z52: the two scripts register the same clientfields.

    The engine compares the server's clientfield list with the client's and
    drops the connection when they differ -- measured, which is why this
    check exists: ``zm_dmv`` built for eight seats registered six
    ``clientuimodel`` score fields per extra seat on the server and none on
    the client, and a solo game ended "Server Disconnected -
    Clientfield Mismatch".  A stock server-only registration is
    safe only because the game's own LUI file supplies the client half, and a
    usermap cannot ship LUI (Z27), so whatever the map's own scripts register
    has to appear in both, in the same order, with the same pool, version,
    bit count and type.
    """
    if not script or not client_script:
        return
    server = clientfield_registrations(script)
    client = clientfield_registrations(client_script)
    if server == client:
        return
    for position, (ours, theirs) in enumerate(
        zip_longest(server, client), start=1
    ):
        if ours == theirs:
            continue

        def show(entry):
            if entry is None:
                return "nothing"
            loops, *args = entry
            where = f" inside {loops}" if loops else ""
            return f"({', '.join(args)}){where}"

        report.add(
            error(
                "Z52",
                f"clientfield registration {position} differs between the "
                f"scripts: the server registers {show(ours)[:200]} and the "
                f"client registers {show(theirs)[:200]}.  The engine compares "
                "the two lists and disconnects on a difference (\"Clientfield "
                "Mismatch\", measured on zm_dmv); register every "
                "field the map adds in both scripts, in the same order, with "
                "the same pool, version, bits and type",
            )
        )
        return


def _check_custom_perks(
    document: Document, script: str, client_script: str | None, report: Report
) -> None:
    """Z50: a perk the map wrote itself, and the ways it is furniture.

    A perk of our own is five registration calls, one ``script_struct`` and
    one string (:mod:`zmforge.script.perks`).  Nothing in the game validates
    any of it: an unknown specialty registers without complaint, a machine
    nobody registered is skipped in silence, and a perk nothing calls is a
    perk that does not exist.  Every finding below links clean, and each is
    read off the install's own ``share/raw/scripts/zm/_zm_perks.gsc``.

    *No bottle.*  ``:1825`` asserts the argument, ``:612`` takes the points
    **before** the drink and ``:617`` grants the perk only when the weapon
    change completes.  A machine whose bottle does not resolve charges the
    player and hands back nothing -- which is the community's own report of
    the same defect: no drink animation, no icon, no effect, no sprint
    (UGX-Mods 14197).

    *A script the map never carries.*  The registration lives in a function,
    and a function nothing calls is not run.  ``main`` has to call it, and
    before ``zm_usermap::main()``: the entry reaches ``zm_perks::init``, which
    runs every perk's precache function (``:40``, ``:172-184``), so a
    registration after it is a registration nothing reads.

    *A perk with no machine.*  The registration runs, the perk exists, and no
    ``zm_perk_machine`` struct carries its specialty, so there is nowhere to
    buy it.  And the other way round -- a struct whose ``script_noteworthy``
    names a perk neither the mod tools install nor this script registers -- is quieter
    still: ``:1437`` collects the struct, finds nothing behind it, and the
    machine never turns on.

    *Two perks, one HUD slot.*  The icon is a hard-coded key inside the
    shipped interface widget.  Two perks writing one path is one widget being
    told two things, and nothing in the map decides which write lands last.
    Claiming a key a **stock** perk on this map owns is the same defect with a
    shipped perk on the other side of it.

    And one that is cheaper to catch here than in a play session: a prompt the
    script names and never precaches, which is a blank line on the machine.

    **Nothing here is verified in game.**
    """
    from ..blueprint.catalogue import PERKS
    from ..script.perks import (
        BOUND_ICON_SLOTS,
        SPECIALTY_PREFIX,
        STOCK_BOTTLES,
        icon_key_of,
    )

    stripped = "\n".join(gsc_strip_noise(script))
    spans = _function_spans(stripped)
    main = next(((s, e) for name, s, e in spans if name == "main"), None)
    entry = stripped.find(f"{_ENTRY_CALL}(")

    stock = {perk.specialty for perk in PERKS if perk.specialty}
    machines: dict[str, list] = {}
    for entity in document.entities_of("script_struct"):
        if entity.value("targetname") != "zm_perk_machine":
            continue
        machines.setdefault(entity.value("script_noteworthy") or "", []).append(entity)

    # -- what the script registers, and which functions belong to it ----
    registered: dict[str, dict] = {}
    owner_of: dict[str, str] = {}
    for match in _PERK_BASIC_RE.finditer(stripped):
        # The stripped text says where a live call is; the original says what
        # it names, because stripping blanks string bodies.
        text = script[match.start(1) : match.end(1)]
        names = _QUOTED_RE.findall(text)
        specialty = names[0] if names else ""
        if not specialty:
            report.add(
                error(
                    "Z50",
                    "a register_perk_basic_info call names no specialty "
                    "string; that string is the perk, the machine's "
                    "script_noteworthy and the key the framework files it "
                    "under (_zm_perks.gsc:1808-1818)",
                )
            )
            continue
        bottle = _BOTTLE_RE.search(text)
        hint = _HINT_RE.search(text)
        registered[specialty] = {
            "bottle": bottle.group(1) if bottle else None,
            "hint": hint.group(1) if hint else None,
            "in": _enclosing(spans, match.start()),
            "at": match.start(),
        }
    for match in _PERK_REGISTER_RE.finditer(stripped):
        text = script[match.start(2) : match.end(2)]
        names = _QUOTED_RE.findall(text)
        specialty = names[0] if names else ""
        if not specialty:
            continue
        registered.setdefault(
            specialty,
            {
                "bottle": None,
                "hint": None,
                "in": _enclosing(spans, match.start()),
                "at": match.start(),
                "partial": True,
            },
        )
        for function in _FUNC_REF_RE.findall(text):
            owner_of[function] = specialty

    if not registered:
        for specialty, entities in machines.items():
            if specialty.startswith(SPECIALTY_PREFIX):
                report.add(
                    error(
                        "Z50",
                        f"the map has {len(entities)} perk machine(s) for "
                        f"{specialty!r} and the script never registers it, so "
                        "the map carries the machine and not the perk: "
                        "nothing writes level._custom_perks and the machine "
                        "never turns on (_zm_perks.gsc:1437)",
                    )
                )
        return

    for specialty, facts in registered.items():
        if facts.get("partial"):
            report.add(
                error(
                    "Z50",
                    f"{specialty!r} is registered with the framework but never "
                    "through register_perk_basic_info, so it has no price, no "
                    "prompt and no bottle; _zm_perks.gsc:1821-1825 asserts all "
                    "five arguments",
                )
            )
        if specialty in stock:
            report.add(
                warning(
                    "Z50",
                    f"the script registers {specialty!r}, which is a perk this "
                    "install ships a module for.  Every zm_perks::register_* "
                    "call keeps the first registration and the stock modules "
                    "register from a preload, before this script's main() runs, "
                    "so these calls change nothing (_zm_perks.gsc:1903, "
                    "callbacks_shared.gsc:531)",
                )
            )
        bottle = facts["bottle"]
        if not facts.get("partial") and not bottle:
            report.add(
                error(
                    "Z50",
                    f"{specialty!r} is registered with no bottle weapon.  The "
                    "framework takes the points first (_zm_perks.gsc:612) and "
                    "grants the perk only when the weapon change completes "
                    "(:617), so the machine charges the player and gives "
                    "nothing.  Name a stock bottle: " + ", ".join(STOCK_BOTTLES),
                )
            )
        elif bottle and bottle not in STOCK_BOTTLES:
            report.add(
                warning(
                    "Z50",
                    f"{specialty!r} drinks {bottle!r}, which is not one of the "
                    "nine bottles on the stock asset list, so the map has to "
                    "ship a weapon asset of that name or the perk is never "
                    "granted (zm_levelcommon.csv:6283-6291)",
                )
            )
        hint = facts["hint"]
        if hint and hint not in _PRECACHE_STRING_RE.findall(script):
            report.add(
                error(
                    "Z50",
                    f"{specialty!r} shows the prompt &\"{hint}\" and the script "
                    f'never precaches it (#precache( "string", "{hint}" );), so '
                    "the machine's prompt is blank: the localize line packs the "
                    "string and the directive is what gives the script a handle "
                    "for it",
                )
            )
        _check_registration_runs(specialty, facts, stripped, main, entry, report)
        if not machines.get(specialty):
            report.add(
                error(
                    "Z50",
                    f"the script registers the perk {specialty!r} and the map "
                    "has no machine carrying that script_noteworthy, so there "
                    "is nowhere a player can buy it: the framework builds the "
                    "use trigger from the struct and from nothing else "
                    "(_zm_perks.gsc:1419, :1437)",
                )
            )

    for specialty, entities in machines.items():
        if specialty in stock or specialty in registered:
            continue
        report.add(
            error(
                "Z50",
                f"the map has {len(entities)} perk machine(s) for {specialty!r} "
                "and neither the mod tools install nor this script registers it, so the "
                "machine has no perk behind it and never turns on "
                "(_zm_perks.gsc:1437)",
            )
        )

    _check_icon_claims(document, script, stripped, spans, owner_of, machines, report)
    _check_machine_light(script, stripped, client_script, report)


def _check_registration_runs(
    specialty: str, facts: dict, stripped: str, main, entry: int, report: Report
) -> None:
    """The registration has to be reached, and reached before the entry."""
    where = facts["in"]
    if where is None or main is None:
        return
    if where == "main":
        position = facts["at"]
    else:
        call = re.search(rf"\b{re.escape(where)}\s*\(\s*\)\s*;", stripped[main[0] : main[1]])
        if call is None:
            report.add(
                error(
                    "Z50",
                    f"{specialty!r} is registered inside {where}() and main "
                    "never calls it, so the map carries the perk's script and "
                    "never runs it: level._custom_perks has no entry, the "
                    "machine never turns on and nothing says why",
                )
            )
            return
        position = main[0] + call.start()
    if entry >= 0 and position > entry:
        report.add(
            error(
                "Z50",
                f"{specialty!r} is registered after {_ENTRY_CALL}(), which "
                "is too late: the entry reaches zm_perks::init, which runs "
                "every perk's precache function and starts every machine loop "
                "(_zm_perks.gsc:40, :172-184)",
            )
        )


def _check_machine_light(
    script: str, stripped: str, client_script: str | None, report: Report
) -> None:
    """The effect a perk hands the framework needs a handle on both sides.

    ``level._effect[ x ] = "<path>"`` is a name and not a registration: the
    handle comes from the ``#precache`` directive, spelled ``fx`` on the
    server and ``client_fx`` on the client, and the stock perk modules
    precache theirs in both halves (``_zm_perk_juggernaut.gsc:29`` against
    ``.csc:16``).  A machine light with no handle plays nothing and says
    nothing -- and this is the one asset a custom perk names that Z17 cannot
    see, because a stock effect needs no manifest line to be packed.
    """
    for match in _EFFECT_HANDLE_RE.finditer(stripped):
        path = script[match.start(1) : match.end(1)]
        for text, kind, side in (
            (script, "fx", "server"),
            (client_script, "client_fx", "client"),
        ):
            if text is None:
                continue
            if f'#precache( "{kind}", "{path}" );' in text:
                continue
            report.add(
                error(
                    "Z50",
                    f"a perk hands the framework the effect {path!r} and the "
                    f"{side} script never precaches it "
                    f'(#precache( "{kind}", "{path}" );), so the machine light '
                    "has no handle: it plays nothing and reports nothing",
                )
            )


def _check_icon_claims(
    document: Document,
    script: str,
    stripped: str,
    spans,
    owner_of: dict[str, str],
    machines: dict,
    report: Report,
) -> None:
    """One widget key, one perk -- and not a key a stock perk on this map owns."""
    from ..blueprint.catalogue import PERKS
    from ..script.perks import BOUND_ICON_SLOTS, icon_key_of

    claims: dict[str, set[str]] = {}
    for match in _UIMODEL_RE.finditer(stripped):
        path = script[match.start(1) : match.end(1)]
        function = _enclosing(spans, match.start()) or ""
        claims.setdefault(path, set()).add(owner_of.get(function, function))
    for path, owners in sorted(claims.items()):
        key = icon_key_of(path)
        if len(owners) > 1:
            report.add(
                error(
                    "Z50",
                    f"{len(owners)} perks write the HUD path {path!r} "
                    f"({', '.join(sorted(owners))}); the shipped widget draws "
                    "one image per key, so two perks claiming one slot means "
                    "whichever wrote last decides and the other perk has no icon",
                )
            )
        if key is None:
            continue
        if key not in BOUND_ICON_SLOTS:
            report.add(
                warning(
                    "Z50",
                    f"the script writes the HUD path {path!r}, which the shipped "
                    "interface widget does not bind, so nothing draws whatever "
                    "art the map ships.  That table is Lua and the mod tools' "
                    "linker refuses a Lua rawfile ('ERROR: Lua not supported', "
                    "measured)",
                )
            )
            continue
        held_by = BOUND_ICON_SLOTS[key]
        if held_by is None:
            continue
        perk = next((p for p in PERKS if p.specialty == held_by), None)
        placed = bool(machines.get(held_by)) or (
            perk is not None
            and perk.from_prefab
            and any(
                entity.value("model") == perk.prefab
                for entity in document.entities_of("misc_prefab")
            )
        )
        if placed:
            report.add(
                error(
                    "Z50",
                    f"the script claims the {key!r} HUD slot and this map also "
                    f"places {held_by!r}, whose own module writes the same path; "
                    "the two perks fight over one widget and the map does not "
                    "decide which write lands last",
                )
            )
        else:
            report.add(
                warning(
                    "Z50",
                    f"the script claims the {key!r} HUD slot, which belongs to "
                    f"{held_by!r}.  Nothing on this map lights it, so the slot "
                    "is free in practice -- but a stock perk added later takes "
                    "it back.  The two slots nothing owns are tombstone and "
                    "dive_to_nuke",
                )
            )


def _check_perk_modules(
    document: Document, script: str, client_script: str | None, report: Report
) -> None:
    """Z9's script half: every placed perk's module, in *both* scripts.

    A perk is two halves.  The server module is the machine's logic; the
    client module is its clientfields, its HUD callbacks and its machine
    effect (``_zm_perk_juggernaut.csc:20-30`` registers all three through
    ``zm_perks::register_perk_clientfields`` and ``register_perk_effects``),
    and every perk module in the mod tools' raw scripts has a ``.csc``
    beside its ``.gsc``.  Treyarch's own map names each perk module in both
    files -- ``zm_giant.gsc:30-38`` against ``zm_giant.csc:21-28`` -- so a
    module in one script and not the other is the defect this asks about.
    The in-game symptom of the missing client half is unverified.
    """
    from ..blueprint.catalogue import PERKS

    # A machine is either a stamped prefab or -- for the two the install
    # ships a model and a script for but no prefab -- the bare
    # ``zm_perk_machine`` struct the framework reads.  Both carry the name
    # this check keys on in their ``model``.
    placed = {e.value("model") for e in document.entities_of("misc_prefab")}
    # A struct machine is identified by its **specialty**, not by its model.
    # The model is not an identity: a perk this repository wrote stands on a
    # stock machine model and is free to stand on one a stock perk also
    # names, and ``p7_zm_vending_nuke`` is exactly that case -- it is the
    # Electric Cherry stub's model, and the stub ships no machine.  Keying
    # this on the model alone reported a missing ``_zm_perk_electric_cherry``
    # ``#using`` for a map that places no Electric Cherry at all.  What the
    # framework reads off the struct is ``script_noteworthy``
    # (``_zm_perks.gsc:1419``), so that is what this reads too.
    specialties = {
        e.value("script_noteworthy")
        for e in document.entities_of("script_struct")
        if e.value("targetname") == "zm_perk_machine"
    }
    for perk in PERKS:
        here = perk.placed_model in placed if perk.from_prefab else (
            perk.specialty in specialties
        )
        if here and perk.module:
            using = f"#using {perk.module};"
            if using not in script:
                report.add(
                    error(
                        "Z9",
                        f"{perk.slug} is in the map but the script is missing "
                        f"'{using}', so the machine has no logic",
                    )
                )
            if client_script is not None and using not in client_script:
                report.add(
                    error(
                        "Z9",
                        f"{perk.slug} is in the map but the client script is "
                        f"missing '{using}', so the perk's client half -- its "
                        "clientfields, HUD and machine effect -- is never "
                        "registered",
                    )
                )
    if client_script is None:
        return
    # The two lists have to be the same list, whatever is placed: a module
    # in one script alone is the mismatch, and it is the mismatch that is
    # the bug.
    server_modules = {
        perk.module
        for perk in PERKS
        if perk.module and f"#using {perk.module};" in script
    }
    client_modules = {
        perk.module
        for perk in PERKS
        if perk.module and f"#using {perk.module};" in client_script
    }
    for module in sorted(client_modules - server_modules):
        report.add(
            error(
                "Z9",
                f"the client script carries '#using {module};' and the server "
                "script does not, so the two disagree about which perks exist",
            )
        )


def _check_lighting_entities(document: Document, report: Report) -> None:
    for classname, label in (("volume_sun", "sun volume"), ("umbra_volume", "umbra volume")):
        found = document.entities_of(classname)
        if len(found) != 1:
            report.add(
                error("Z11", f"expected exactly one {label}, found {len(found)}")
            )
    sky_brushes = 0
    world = document.worldspawn
    if world is not None:
        for solid in world.solids:
            if isinstance(solid, BrushSolid) and all(
                facet.material == "sky" for facet in solid.facets
            ):
                sky_brushes += 1
    if sky_brushes != 6:
        report.add(
            error(
                "Z11",
                f"the sky shell must be six slabs, found {sky_brushes} all-sky brushes",
            )
        )
    if not document.entities_of("light"):
        report.add(error("Z11", "the map has no light entity"))


def _check_reflection_probes(document: Document, report: Report) -> None:
    """Z28 on the written text: a probe exists, and its box is a real box.

    The model side asks whether every room is covered.  This side asks
    whether what got written is a probe the tools will accept, which is three
    things and no more: ``size_min``/``size_max`` are three numbers each, the
    box they describe has a positive extent on every axis, and
    ``in_play_space`` obeys the one rule ``t7.def.json`` states about it --
    the key is unavailable once every side is over 1000 units.

    Zero probes is a warning rather than an error: it is what a caller who
    passed ``probe=False`` asked for, and neither ``cod2map64`` nor the
    linker objects to it.
    """
    from ..lighting import PROBE_PLAY_SPACE_LIMIT, probe_in_play_space

    probes = document.entities_of("reflection_probe")
    if not probes:
        report.add(
            warning(
                "Z28",
                "the written map has no reflection_probe; the mod tools' own "
                "new-map template ships one, so nothing in this map gets "
                "bounced light",
            )
        )
        return
    for probe in probes:
        name = probe.value("name") or "probe"
        half_low = _read_triple(probe.value("size_min"))
        half_high = _read_triple(probe.value("size_max"))
        if half_low is None or half_high is None:
            report.add(
                error(
                    "Z28",
                    f"reflection probe {name!r} has no size_min/size_max pair, "
                    "so it covers nothing",
                )
            )
            continue
        extents = tuple(low + high for low, high in zip(half_low, half_high))
        if min(extents) <= 0.0:
            report.add(
                error(
                    "Z28",
                    f"reflection probe {name!r} has a box of {extents[0]:g} x "
                    f"{extents[1]:g} x {extents[2]:g}, which is flat on at "
                    "least one axis and encloses no volume",
                )
            )
            continue
        wants = "1" if probe_in_play_space(extents) else "0"
        if (probe.value("in_play_space") or "1") != wants:
            report.add(
                error(
                    "Z28",
                    f"reflection probe {name!r} sets in_play_space to "
                    f"{probe.value('in_play_space')!r}; its box is "
                    f"{extents[0]:g} x {extents[1]:g} x {extents[2]:g} and "
                    f"t7.def.json says the key is unavailable once every side "
                    f"is over {PROBE_PLAY_SPACE_LIMIT:g}",
                )
            )


def _read_triple(raw: str | None) -> tuple[float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split()
    if len(parts) != 3:
        return None
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return None


def _check_face_materials(document: Document, report: Report, strict: bool) -> None:
    names: set[str] = set()
    for entity in document.entities:
        for solid in entity.solids:
            if isinstance(solid, BrushSolid):
                names.update(facet.material for facet in solid.facets)
            elif isinstance(solid, PatchSolid):
                names.add(solid.material)
                if solid.material == "caulk":
                    report.add(
                        error(
                            "Z12",
                            "a patch carries caulk; the compiler prints its "
                            "terrain-caulk banner and the patch renders black",
                        )
                    )
    for name in sorted(names):
        if is_catalogued(name):
            continue
        note = f"material {name!r} is not in the known-clean catalogue"
        if name in BENIGN_MISSING:
            note += " (known benign: it comes from a stock prefab)"
        elif not is_pipeline_material(name):
            # Not stock-proven and not staged by our own pipeline: in game it
            # is the magenta error texture, so it never ships as a warning.
            report.add(error("Z12", note + "; it renders as the error texture"))
            continue
        report.add((error if strict else warning)("Z12", note))


# --------------------------------------------------------------------------
# Scripts and manifest (spec 9.4 Z2, Z10, Z13, Z14)
# --------------------------------------------------------------------------
def check_server_script(script: str) -> Report:
    """Z2 and Z10: the forbidden assignment, and statement order in ``main``."""
    report = Report()
    for match in re.finditer(
        r"level\.default_start_location\s*=\s*\"([^\"]*)\"", script
    ):
        if match.group(1) != "start_room":
            report.add(
                error(
                    "Z2",
                    "the map script assigned level.default_start_location to "
                    f"{match.group(1)!r}; the spawn match string becomes "
                    f"'zclassic_{match.group(1)}', which matches no struct and "
                    "empties the spawn set",
                )
            )

    assignments = list(
        re.finditer(r"level\.dog_rounds_allowed\s*=\s*([^;]*);", script)
    )
    dog = assignments[0] if assignments else None
    entry = script.find("zm_usermap::main()")
    hook = script.find("level.zone_manager_init_func")
    zones = [m.start() for m in re.finditer(r"init_zones\[\d+\]", script)]
    manage = script.find("zm_zonemgr::manage_zones")

    if dog is None:
        report.add(error("Z10", "the script never assigns level.dog_rounds_allowed"))
    if entry < 0:
        report.add(error("Z10", "the script never calls zm_usermap::main()"))
    if manage < 0:
        report.add(error("Z10", "the script never starts zm_zonemgr::manage_zones"))
    # Every assignment, not only the first: the generated one is in the right
    # place by construction, so the one that matters is any a caller added
    # after the entry, where the framework has already read the variable.
    late = [m for m in assignments if entry >= 0 and m.start() > entry]
    for match in late:
        report.add(
            error(
                "Z10",
                f"level.dog_rounds_allowed is assigned ({match.group(1).strip()}) "
                "after the framework entry; the framework's default has already "
                "applied by then",
            )
        )
    if entry >= 0 and hook >= 0 and hook < entry:
        report.add(error("Z10", "the zone hook is set before the framework entry"))
    if hook >= 0 and zones and min(zones) < hook:
        report.add(error("Z10", "init_zones entries appear before the zone hook is set"))
    if zones and manage >= 0 and manage < max(zones):
        report.add(error("Z10", "manage_zones is started before init_zones is filled"))

    if dog is not None and dog.group(1).strip() == "1":
        report.add(
            warning(
                "Z10",
                "dog rounds are on; the map must carry zombie_dog_spawner entities "
                "and dog_location structs",
            )
        )
    _check_zone_hook_order(script, report)
    return report


def _check_zone_hook_order(script: str, report: Report) -> None:
    """Z3: a zone flag is initialised before the adjacency calls, never after.

    ``add_adjacent_zone`` initialises the flag it is handed when nothing has
    defined it yet (``_zm_zonemgr.gsc``), and ``flag::init`` writes the flag
    back to 0 and, in a dev build, asserts on a flag that already exists
    (``flag_shared.gsc``).  So an ``init`` that runs *after* an adjacency
    call can only either re-zero a flag the zone manager just made or trip
    that assert.  The mod tools' ZM template and every shipped zone hook put
    the flag lines first; this keeps a generated hook on that order, which is
    the arrangement the community guide's "delete the two flag lines" advice
    is an alternative to rather than a correction of.
    """
    inits = [m.start() for m in re.finditer(r"flag::init\s*\(", script)]
    adjacents = [m.start() for m in re.finditer(r"add_adjacent_zone\s*\(", script)]
    if not inits or not adjacents:
        return
    first_adjacent = min(adjacents)
    for position in inits:
        if position > first_adjacent:
            line = script.count("\n", 0, position) + 1
            report.add(
                error(
                    "Z3",
                    f"line {line}: a flag is initialised after the first "
                    "add_adjacent_zone call; flag::init writes the flag back to "
                    "zero, and add_adjacent_zone has already created any flag it "
                    "was handed, so the zone connection this flag opens can be "
                    "left shut",
                )
            )


def check_client_script(script: str) -> Report:
    """Z13: the client entry must be called or the game disconnects on join."""
    report = Report()
    # The whole of main(), not "up to the first closing brace": a client main
    # with a block in it before the entry call -- which is what a map with
    # more than four seats writes, because its client fields have to be
    # registered before the entry (Z51) -- would otherwise read as a main()
    # that never calls the entry at all.
    stripped = "\n".join(gsc_strip_noise(script))
    spans = _function_spans(stripped)
    main = next(((start, end) for name, start, end in spans if name == "main"), None)
    body = stripped[main[0] : main[1]] if main is not None else None
    if body is None:
        report.add(error("Z13", "the client script has no main()"))
    elif "zm_usermap::main()" not in body:
        report.add(
            error(
                "Z13",
                "the client main() does not call zm_usermap::main(); the server and "
                "client disagree about client fields and the join is dropped",
            )
        )
    return report


def check_script_soundness(script: str, *, label: str) -> Report:
    """Z15 and Z16: is this text a script at all, and does it call only what exists?

    Z10 and Z13 test the framework contract -- the ordering and the client
    entry -- and both assume the file compiles.  Custom gameplay logic
    (:mod:`zmforge.script`) breaks that assumption: it is the first thing the
    engine emits that was not written by the engine.  A missing semicolon or
    a call to a function nothing defines is fatal at run time in this game,
    and the compiler lives on Windows behind a linker that never exits
    zero, so these two run in the same process that wrote the text.

    ``Z15`` is structure: brackets, string literals, statement terminators,
    statements outside a function, a name defined twice.
    ``Z16`` is references: a call or ``&pointer`` to a function the file does
    not define, a namespaced call the stock symbol table does not know, or a
    known call whose module the script never ``#using``s.
    ``Z90`` is a dev-only builtin (``PrintLn``, ``Line``, ...) called outside a
    ``/# #/`` developer block, which only the game's loader reports, at map
    load (:data:`zmforge.script.gsc.DEV_ONLY_BUILTINS`).
    """
    report = Report()
    source = gsc_scan(script)
    for issue in source.issues:
        report.add(error("Z15", f"{label} line {issue.line}: {issue.detail}"))
    for issue in stock_unresolved(source):
        report.add(error("Z16", f"{label} line {issue.line}: {issue.detail}"))
    for line, name in dev_only_calls(script):
        report.add(error(
            "Z90",
            f"{label} line {line}: {name}() is a dev-only builtin outside a "
            "/# #/ developer block; the retail loader refuses the whole script "
            "(\"Dev only calls must be wrapped in a devblock\")",
        ))
    report.extend(check_purchase_text(script, label=label))
    return report


def _using_paths(script: str) -> set[str]:
    """Every module a script ``#using``s, as ``scripts/zm/name``."""
    return {
        module.strip().replace("\\", "/").lower()
        for module in re.findall(r"#\s*using\s+([^;]+);", script)
    }


def check_declarations(
    manifest: str, server: str, client: str, map_name: str
) -> Report:
    """Z17, over the manifest and the two scripts at once.

    A manifest line is a promise that ends at the linker.  Two of the types
    need a second half in the scripts, and neither half missing says anything
    at run time:

    ``fx``
        the effect is packed and has no handle.  ``level._effect[ x ] =
        "<path>"`` is a name, not a registration: the server script registers
        it with ``#precache( "fx", ... )`` and the client script with
        ``#precache( "client_fx", ... )``, which is how the mod tools' own
        raw sources do it (``zm_giant.gsc`` against ``zm_giant_fx.csc``).  A
        prefab whose effect was never precached renders nothing and errors
        nowhere.
    ``scriptparsetree``
        the script is compiled into the fastfile and never runs.  A loose
        ``.gsc`` needs the parse-tree line *and* a ``#using`` line in the map
        script that calls into it.  It usually needs a third artefact as
        well -- the entity in the map the script looks for by ``targetname``
        -- and that one cannot be checked here, because only the script
        being installed knows the name.  It is on the manual list.
    """
    report = Report()
    lines = [line.strip() for line in manifest.splitlines()]
    precached = {
        (kind, name)
        for script, kinds in ((server, ("fx",)), (client, ("client_fx",)))
        for kind in kinds
        for name in re.findall(
            r'#\s*precache\(\s*"' + kind + r'"\s*,\s*"([^"]+)"\s*\)', script
        )
    }
    using = {"gsc": _using_paths(server), "csc": _using_paths(client)}
    own = {
        f"scripts/zm/{map_name}.gsc".lower(),
        f"scripts/zm/{map_name}.csc".lower(),
    }
    for line in lines:
        if not line or line.startswith((">", "//")):
            continue
        prefix, _, value = line.partition(",")
        value = value.strip()
        if not value:
            continue
        if prefix == "fx":
            for kind, where in (("fx", "server"), ("client_fx", "client")):
                if (kind, value) not in precached:
                    report.add(
                        error(
                            "Z17",
                            f"the manifest declares fx {value!r} and the {where} "
                            f'script never precaches it (#precache( "{kind}", '
                            f'"{value}" );): the effect is packed into the '
                            "fastfile, the game has no handle for it, and "
                            "anything that plays it renders nothing and reports "
                            "nothing",
                        )
                    )
        elif prefix == "scriptparsetree":
            path = value.replace("\\", "/").lower()
            if path in own:
                continue
            extension = path.rsplit(".", 1)[-1]
            if extension not in using:
                continue
            module = path.rsplit(".", 1)[0]
            if module not in using[extension]:
                side = "server" if extension == "gsc" else "client"
                report.add(
                    error(
                        "Z17",
                        f"the manifest declares {value!r} and the {side} script "
                        f"has no '#using {module.replace('/', chr(92))};' line, so "
                        "the script is compiled into the fastfile and nothing "
                        "calls into it",
                    )
                )
    return report


def check_manifest(text: str, map_name: str) -> Report:
    """Z14 the six lines the linker needs, Z17 every other declaration, P3 a title.

    Z17 exists because a manifest is the only place a map says what it needs
    packed, and a typo there is not caught by anything else: the linker acts
    on the lines it understands and the map dies at run time reaching for the
    asset that never arrived.
    """
    report = Report()
    lines = {line.strip() for line in text.splitlines()}
    required = [
        ">class,zm_mod_level",
        ">group,modtools",
        f"col_map,maps/zm/{map_name}.d3dbsp",
        f"gfx_map,maps/zm/{map_name}.d3dbsp",
        f"scriptparsetree,scripts/zm/{map_name}.gsc",
        f"scriptparsetree,scripts/zm/{map_name}.csc",
    ]
    for entry in required:
        if entry not in lines:
            report.add(error("Z14", f"the manifest is missing {entry!r}"))
    for line in sorted(lines):
        if not line or line.startswith((">", "//")):
            continue
        if line in required:
            continue
        prefix, _, value = line.partition(",")
        if prefix not in ASSET_PREFIXES:
            report.add(
                error(
                    "Z17",
                    f"the manifest declares {line!r}, whose type {prefix!r} is "
                    "not an asset prefix any real zone file has been seen to "
                    "use; the linker cannot act on it",
                )
            )
        elif not value.strip():
            report.add(
                error("Z17", f"the manifest line {line!r} names no asset")
            )
    report.extend(_check_unpackable_types(lines))
    report.extend(_check_unbuildable_assets(lines, map_name))
    titles = [line for line in lines if line.startswith(">title,")]
    if not titles:
        report.add(
            warning(
                "P3",
                "the manifest has no '>title,' line, so menus fall back to the "
                "asset name; the mod tools' ZM template omits it too",
            )
        )
    for line in titles:
        # What survives the toolchain, measured with the mod tools and
        # confirmed in game: the linker rewrites the title into
        # zone_source/loc/<map>.zone, and there a comma truncates and every
        # space is removed, so `>title,Corn Maze, Night` comes out as
        # `>title,CornMaze`.  Letters, digits and brackets come through:
        # `Corn Maze (Night)` comes out as `CornMaze(Night)`.
        # The space-stripping is not warned about: it happens to every
        # readable title, so it is a fact about the toolchain (spec 6.1.1)
        # rather than something wrong with this map. A comma is different:
        # it silently throws text away, and few titles have one.
        value = line[len(">title,"):]
        if "," in value:
            kept = value.split(",", 1)[0].replace(" ", "")
            report.add(
                warning(
                    "P3",
                    f"the title {value!r} has a comma in it, and the manifest is a "
                    f"comma-separated file: everything from the comma on is dropped, "
                    f"so menus get {kept!r}",
                )
            )
    return report


#: What a literal purchase or use prompt looks like in a script.  Spec 5.7:
#: of 614 stock ``sethintstring(`` call sites "every non-localized literal is
#: the empty string, which clears a prompt", and nothing here has measured
#: what a non-empty one does.  The map's own text belongs in a localized
#: string it ships (``zmforge.emit.strings``), which *is* measured.
_HINTSTRING = re.compile(r'sethintstring\(\s*"([^"]+)"', re.IGNORECASE)



#: Raw file suffixes the linker refuses outright, with the line it
#: prints.  **Measured, not reasoned about**: a usermap that
#: declared ``rawfile,ui/zmforge/zm_mymap_lobby.lua`` linked to
#: ``ERROR: Lua not supported`` on Windows and, reproduced in 46 s,
#: under Wine here.  The linker still wrote a fastfile, so nothing but the
#: ``ERROR:`` line says the map is broken -- which is exactly the failure this
#: check exists to move earlier.  Nothing on the mod tools install contradicts it:
#: there is not one ``.lua`` or ``.luac`` file anywhere under the mod tools,
#: and not one shipped ``.zone`` mentions Lua.  The community's lobby-size
#: page offers a map-side route (a ``rawfile`` plus ``LuiLoad`` from the
#: ``.csc``); on the mod tools install that route does not link, and the map has to do
#: without whatever the Lua was for.
UNPACKABLE_RAWFILE_SUFFIXES: dict[str, str] = {
    ".lua": "ERROR: Lua not supported",
    ".luac": "ERROR: Lua not supported",
}


def _check_unpackable_types(lines: set[str]) -> Report:
    """Z27: no manifest line names an asset this linker will not pack.

    An unpackable declaration is worse than a missing one.  The link prints
    its ``ERROR:`` and then writes the fastfiles anyway, so a build that does
    not read the log installs a map the linker refused -- which is how a Lua
    raw file reached a play session and blocked the build.
    """
    report = Report()
    for line in sorted(lines):
        prefix, _, value = line.partition(",")
        if prefix != "rawfile":
            continue
        name = value.strip().lower()
        for suffix, message in UNPACKABLE_RAWFILE_SUFFIXES.items():
            if name.endswith(suffix):
                report.add(
                    error(
                        "Z47",
                        f"the manifest declares {line!r}, and the mod tools' "
                        f"linker answers that with {message!r} and fails the "
                        "link while still writing a fastfile; measured "
                        "on Windows and under Wine",
                    )
                )
                break
    return report

def _check_unbuildable_assets(lines, map_name: str) -> Report:
    """Z24, manifest side: a declaration that cannot resolve to an asset.

    **The sound half used to be a flat error and was wrong.**  It
    once refused any ``sound,`` line, on the reading that a
    bank is a compiled ``.sz`` only the GUI asset editor can produce.  The
    extension was the whole basis of that: Treyarch's own shipped bank,
    ``pc\\raw\\sound\\zone\\mp_sector.all.alias.sz``, is CSV text with a
    102-column header and 646 rows, and a bank written by hand into
    ``share\\raw\\sound\\zone`` links.  So a ``sound,`` line is normal, and
    what is checked now is the three rules that do bite:

    ``sound,<bank>`` where ``<bank>`` is not the map name
        an **error**.  ``sound,<bank>`` is the name the linker opens
        ``<bank>.all.alias.sz`` under, and a generated map writes its bank
        under its own name, so any other spelling names a file that is not
        there.  The old failure, ``ERROR: unable to load file
        'sound/zone//zm_example.all.alias.sz'`` then ``ERROR: sound
        aliases failed to load``, is what that looks like in a log.

    The other two rules are about files rather than lines and live in
    :func:`check_sound_bank`: the bank is read from the shared raw tree, and
    it holds at most 104,729 rows.

    ``localize,<name>``
        **no longer flagged at all** [measured].  This used to
        warn, on the reasoning that the install ships no ``.str`` to copy the
        format from.  It ships none, and that turned out to say nothing about
        the linker: a probe usermap declaring ``localize,zmf_locprobe`` in its
        main zone, against a hand-written
        ``share\\raw\\english\\localizedstrings\\zmf_locprobe.str``, linked
        with no ``ERROR:`` line and the linker's own ``.deps`` named the file
        it had read.  The only rule left is the one the link itself enforces
        -- the ``.str`` named by the line has to be on disk -- and that is a
        file question, not a manifest-line question.
    """
    report = Report()
    for line in sorted(lines):
        prefix, _, value = line.partition(",")
        if prefix == "sound":
            bank = value.strip()
            if bank != map_name:
                report.add(
                    error(
                        "Z24",
                        f"the manifest declares {line!r}, and a map's sound bank is "
                        f"named after the map: the linker opens {bank}.all.alias.sz "
                        f"and this map writes {map_name}.all.alias.sz, so the link "
                        "reports 'sound aliases failed to load' and every custom "
                        "sound is silent",
                    )
                )
    return report


def check_sound_bank(
    manifest: str,
    *,
    map_name: str,
    bank_dir: str | Path | None,
    platform_bank_dir: str | Path | None = None,
    sound_source_dir: str | Path | None = None,
) -> Report:
    r"""Z24, file side: the three rules a sound bank only breaks silently.

    All three were measured on the mod tools install, and each one
    produces either a link that says nothing useful or a map that loads and
    plays nothing, which is why they are checks.

    **Named after the map.** Handled on the manifest line above; here it is
    the file that has to exist under that name.

    **Read from the shared raw tree.** ``share\raw\sound\zone\``, not the
    per-platform ``pc\raw\sound\zone\`` where Treyarch's own ``mp_sector``
    bank sits.  A bank in ``pc\raw`` links exactly as though it were not
    there, so this reports the near miss by name rather than saying "not
    found".

    **At most 104,729 rows.** About 160 times what a real map uses, so a map
    that trips it is a generator writing a row per something rather than a
    person typing.

    And one rule that is not about the bank but fails the same way: a row
    whose ``FileSpec`` names a wave file that is not under ``sound_assets``
    is an alias the game has nothing to play.  Checked only when the caller
    says where ``sound_assets`` is.
    """
    report = Report()
    declared = {
        line.strip().partition(",")[2].strip()
        for line in manifest.splitlines()
        if line.strip().startswith("sound,")
    }
    if not declared or bank_dir is None:
        return report

    directory = Path(str(bank_dir))
    for bank in sorted(declared):
        path = directory / f"{bank}{BANK_SUFFIX}"
        if not path.exists():
            elsewhere = (
                Path(str(platform_bank_dir)) / f"{bank}{BANK_SUFFIX}"
                if platform_bank_dir is not None
                else None
            )
            if elsewhere is not None and elsewhere.exists():
                report.add(
                    error(
                        "Z24",
                        f"the manifest declares {bank!r} and the bank is at "
                        f"{elsewhere}, the per-platform raw tree. The linker reads "
                        f"{directory}; a bank in pc\\raw links as though it were "
                        "absent [measured]",
                    )
                )
            else:
                report.add(
                    error(
                        "Z24",
                        f"the manifest declares {bank!r} and {path} does not exist, "
                        "so the link stops with 'sound aliases failed to load'",
                    )
                )
            continue

        companion = directory / f"{bank}{LOCALISED_BANK_SUFFIX}"
        if not companion.exists():
            report.add(
                error(
                    "Z24",
                    f"{path} exists and its language companion {companion.name} does "
                    "not; the linker opens both, and a header-only English bank is "
                    "what a map with no voice-over ships [measured]",
                )
            )

        text = path.read_text(encoding="utf-8", errors="replace")
        rows = count_alias_rows(text)
        if rows > ALIAS_ROW_CEILING:
            report.add(
                error(
                    "Z24",
                    f"{path.name} carries {rows} rows and a bank holds at most "
                    f"{ALIAS_ROW_CEILING} [measured]; over that the bank "
                    "does not load and every alias in it is silent",
                )
            )
        if rows == 0:
            report.add(
                warning(
                    "Z24",
                    f"{path.name} has a header and no rows, so the manifest is "
                    "asking the linker to pack a bank that names no sound",
                )
            )
        if sound_source_dir is not None:
            report.extend(
                _check_alias_sources(text, Path(str(sound_source_dir)), path.name)
            )
    return report


def check_packed_sound(assetinfo: str | Path, *, map_name: str) -> Report:
    r"""Z24, after the link: is the bank actually in the fastfile?

    The failure this exists for is the one this project keeps hitting with
    models: a clean link is not evidence that an asset is packed. The
    linker's own report is,
    ``usermaps\<map>\zone_source\all\assetinfo\<map>.csv``, which lists every
    asset it wrote with its size. A packed bank looks like::

        1149,sound,zm_ringprobe.all,7179,0,||assetlist

    A map that declared ``sound,<map>`` and has no such row linked without
    its sound and said nothing about it, which is silence in the game and
    nothing in the log.
    """
    report = Report()
    path = Path(str(assetinfo))
    if not path.exists():
        report.add(
            warning(
                "Z24",
                f"{path} does not exist, so whether the sound bank was packed is "
                "unknown; it is written by the link",
            )
        )
        return report
    wanted = f"{map_name}.all"
    for row in csv.reader(io.StringIO(path.read_text(encoding="utf-8", errors="replace"))):
        if len(row) > 3 and row[1] == "sound" and row[2] == wanted:
            if row[3].strip() in ("", "0"):
                report.add(
                    error(
                        "Z24",
                        f"the link packed {wanted} at zero bytes, so the bank is in "
                        "the fastfile and holds nothing",
                    )
                )
            return report
    report.add(
        error(
            "Z24",
            f"the link wrote no 'sound,{wanted}' row into {path.name}, so the map's "
            "sound bank is not in the fastfile. The link does not say so: an asset "
            "that is silently absent is this tool chain's usual failure",
        )
    )
    return report


def _check_alias_sources(bank_text: str, sound_assets: Path, label: str) -> Report:
    """Every row's ``FileSpec``, against the wave files on disk.

    ``FileSpec`` is relative to the tools' ``sound_assets`` folder: Treyarch's
    own rows carry both spellings, ``FileSpec amb\\...\\wall_servo_a_00_01.wav``
    beside ``FileSource Q:\\t7\\pc\\game\\sound_assets\\amb\\...``.
    """
    report = Report()
    rows = list(csv.DictReader(io.StringIO(bank_text)))
    for index, row in enumerate(rows, start=1):
        spec = (row.get("FileSpec") or "").strip()
        name = (row.get("Name") or "").strip()
        if not spec:
            report.add(
                warning(
                    "Z24",
                    f"{label} row {index} ({name or 'unnamed'}) names no FileSpec, "
                    "so the alias resolves to no audio",
                )
            )
            continue
        target = sound_assets
        for part in spec.replace("\\", "/").strip("/").split("/"):
            target = target / part
        if not target.exists():
            report.add(
                error(
                    "Z24",
                    f"{label} row {index} ({name or 'unnamed'}) names {spec!r} and "
                    f"{target} does not exist; the alias links and plays silence",
                )
            )
    return report


# ---------------------------------------------- after the link: does it play?
#: What a file has to look like in the linker's ``.deps`` for it to be audio.
#: The alias rows this project writes name ``.wav``; the rest are here because
#: the deps records whatever the tool opened and the other spellings cost
#: nothing to accept.
AUDIO_SUFFIXES: tuple[str, ...] = (
    ".wav",
    ".flac",
    ".mp3",
    ".ogg",
    ".xma",
    ".xwma",
    ".wem",
)

#: The folder under the tools root that holds the wave files themselves; every
#: alias ``FileSpec`` is relative to it (:attr:`ToolsLayout.sound_source_dir`).
#: A deps line pointing anywhere inside it is audio whatever it is called.
SOUND_SOURCE_DIR_NAME = "sound_assets"

#: ``file,<path>,<mtime>[,<hash>...]``, indented under the asset that needed
#: it.  The path is captured lazily and bounded by the numeric mtime so a
#: path containing a comma cannot split the line in the wrong place.
_DEPS_FILE_RE = re.compile(r"^[ \t]+file,(?P<path>.*?),\d+,", re.MULTILINE)


def deps_audio_files(deps: str) -> list[str]:
    """Every audio file the linker's ``.deps`` says it read.

    The ``.deps`` is the linker's own account of what it opened for a
    fastfile: one unindented line per asset, then indented ``gdt``, ``asset``
    and ``file`` lines under it.  A bank the linker filled with audio has the
    waves in here; a bank it packed from hand-written tables alone has the
    ``.sz`` tables and nothing else.
    """
    found: list[str] = []
    for match in _DEPS_FILE_RE.finditer(deps):
        path = match.group("path").strip()
        parts = path.replace("\\", "/").lower().split("/")
        if path.lower().endswith(AUDIO_SUFFIXES) or SOUND_SOURCE_DIR_NAME in parts:
            found.append(path)
    return found


def packed_bank_evidence(
    map_name: str,
    *,
    pool_report: str = "",
    asset_list: str = "",
) -> list[str]:
    """Why we believe the link packed a sound bank for *map_name*.

    Two outputs of one link state it as a result, and either one on its own
    is enough, because which of them a caller has on hand varies:

    * the pool report, ``<map>_poolinfo.csv``, counts the assets of each
      type it wrote, so ``sound`` with a total above zero is a packed bank;
    * the asset list, ``assetlist/<map>.csv``, carries ``sound,<map>``.

    The ``.deps`` also opens a section headed ``sound,<map>,<language>``, and
    that one is deliberately **not** evidence: it is the zone file's
    declaration, not the link's result.  Measured on
    ``zm_ringprobe``, whose link failed outright ("sound aliases failed to
    load"): the deps carried that section, the pool report said zero and
    neither asset list mentioned sound.

    Returns the evidence lines, empty when the map packed no bank at all.
    """
    reasons: list[str] = []
    for row in csv.reader(io.StringIO(pool_report)):
        cells = [cell.strip() for cell in row]
        if len(cells) >= 3 and cells[0] == "sound":
            try:
                total = int(cells[2])
            except ValueError:
                continue
            if total > 0:
                reasons.append(
                    f"the pool report counts {total} sound asset(s) "
                    f"({','.join(cells[:3])})"
                )
    for row in csv.reader(io.StringIO(asset_list)):
        cells = [cell.strip() for cell in row]
        if len(cells) >= 2 and cells[0] == "sound" and cells[1] == map_name:
            reasons.append(f"the asset list carries sound,{map_name}")
    return reasons


def check_linked_sound_audio(
    map_name: str,
    *,
    pool_report: str = "",
    asset_list: str = "",
    deps: str = "",
    label: str = "",
) -> Report:
    r"""Z24, after the link: a packed bank that carries no audio.

    THE CRASH THIS EXISTS FOR.  A test map linked
    with every verdict green -- no ``ERROR:`` line, both fastfiles written --
    and the game died on an access violation part way through loading the
    level.  The game's own message, recovered from the crashed process, named
    the map's sound bank and said it failed to load.  The link had reported
    the bank packed (``sound`` above zero in the pool report, ``sound,<map>``
    in both asset lists) and its ``.deps`` named the seven ``.sz`` tables and
    no wave file at all, so the bank in the fastfile held aliases and no
    audio.  A bank the game will not accept is not a warning: it is a crash
    at load, and nothing else in the build says a word about it.

    So: when the link's own outputs say a bank was packed for this map, the
    ``.deps`` has to name at least one audio file, and this is an error when
    it does not.

    *pool_report*, *asset_list* and *deps* are the **text** of those three
    outputs, because the caller may have read them from a Wine build's
    tree or from a Windows one.  Pass what is on hand;
    each one is optional and the check uses whichever arrived.
    """
    report = Report()
    where = f"{label}: " if label else ""
    reasons = packed_bank_evidence(
        map_name, pool_report=pool_report, asset_list=asset_list
    )
    if not reasons:
        return report
    if not deps.strip():
        report.add(
            warning(
                "Z24",
                f"{where}{reasons[0]}, and the link's .deps was not read, so "
                "whether that bank carries any audio is unknown",
            )
        )
        return report
    audio = deps_audio_files(deps)
    if audio:
        return report
    report.add(
        error(
            "Z24",
            f"{where}the link packed the sound bank for {map_name} ({reasons[0]}) "
            "and its .deps names no audio file, so the bank holds aliases and no "
            "sound. The game refuses a bank built this way and dies at load: "
            "measured, it named the bank, said it failed to load, and "
            "took an access violation two and a half minutes in. Build the bank "
            "with a tool that reads the waves, or ship the map without one "
            "(recipe custom_sound=False)",
        )
    )
    return report


def check_purchase_text(script: str, *, label: str) -> Report:
    """Z24, script side: a prompt this game will not show.

    A prompt this map's own text **can** reach -- spec 5.7 says
    so -- but not this way.  The measured route is a localized string
    the map ships (``localize,<map>`` plus a ``.str``, measured to link clean)
    referenced as ``&"<MAP>_<REFERENCE>"``; a bare literal is a
    different thing, and it is the thing no stock call site does.  Of 614
    stock ``sethintstring(`` calls every non-localized literal is the empty
    string, which clears a prompt, and no measurement here says what the
    engine does with a non-empty one.

    So this stays a **warning**, and the reason is narrower than it was: not
    "the install cannot build a ``.str``" (it can, and the generator now
    writes one), but "one route is measured and this is not it".  The empty
    literal is allowed: it is what the stock scripts pass.
    """
    report = Report()
    for match in _HINTSTRING.finditer(script):
        line = script.count("\n", 0, match.start()) + 1
        report.add(
            warning(
                "Z24",
                f"{label} line {line}: sethintstring(\"{match.group(1)}\") passes a "
                "literal. Every one of the 614 stock call sites passes either a "
                "localized reference or the empty string, and what the engine "
                "does with a non-empty literal is unmeasured. Ship the text as a "
                "localized string instead -- zmforge.emit.strings writes the "
                ".str, the zone declares localize,<map>, and the script refers "
                "to &\"<MAP>_<REFERENCE>\" (spec 5.7)",
            )
        )
    return report


def check_presentation(
    loading_image: bytes | None, preview_image: bytes | None
) -> Report:
    """P1, P2: the two loose PNGs a finished map ships beside its fastfiles.

    Section 6.1: neither is a fastfile asset, so no build stage will ever
    complain about one being absent or malformed.  Nothing but a check like
    this one catches it before a play session does.

    **The two are not held to the same standard, and the difference is
    measured rather than chosen.**  Across 46 published Workshop maps:

    ``P1``
        every one of the 38 published ``loadingimage.png`` files is
        1920 x 1080.  No exception in the corpus, so the size is checked and
        a difference is worth saying out loud.
    ``P2``
        of the 39 published ``previewimage.png`` files, 23 are the mod tools'
        template size of 600 x 340 and **16 are not**: six at 1920 x 1080,
        four at 600 x 338, and one each at 600 x 360, 600 x 460, 1200 x 680,
        1992 x 1306, 2218 x 1214 and 3126 x 2027, which is eight other sizes.  Every one of those maps is
        published and playable.  So 600 x 340 is the template's size and the
        commonest choice, not a constraint the game imposes, and this check
        **does not look at the preview's size at all**.  It used to, and it
        objected to 41% of the real corpus.

    What is left is what the corpus does support for both files: the file is
    there, and it is a PNG whose header this package can read.  Colour type
    is not checked either, and that is the same correction: published files
    include 32-bit ARGB for 17 of the 38 loading screens and 19 of the 39
    previews, and one 8-bit palette preview, so alpha and palette both reach a
    shipped map.  The
    template being 8-bit truecolour says what the template is.

    Presence is an error rather than a warning because it is a defect *for
    us*: this package writes both files itself, from the blueprint, so a
    missing one means the commit did not do its job.  In the wild it is
    softer -- 39 of the 40 published maps ship the preview, 38 ship both, and
    a map missing one still loads.
    """
    report = Report()
    for code, role, blob, required in (
        ("P1", "loadingimage.png", loading_image, LOADING_IMAGE_SIZE),
        ("P2", "previewimage.png", preview_image, None),
    ):
        if blob is None:
            report.add(error(code, f"{role} is missing from the map's zone folder"))
            continue
        try:
            header = read_png_header(blob)
        except ImageError as problem:
            report.add(error(code, f"{role}: {problem}"))
            continue
        if required is not None and header.size != required:
            report.add(
                warning(
                    code,
                    f"{role} is {header.width}x{header.height}. All 38 published "
                    f"Workshop maps that ship this file are "
                    f"{required[0]}x{required[1]}, as is the mod tools' own "
                    "template, with no exception measured",
                )
            )
    return report


# --------------------------------------------------------------------------
# W4, W5: the map's own weapon table
# --------------------------------------------------------------------------
_LOAD_TABLE = re.compile(
    r'load_weapon_spec_from_table\(\s*"([^"]*)"\s*,\s*(-?\d+)\s*\)'
)
_ADD_WEAPONS_HOOK = re.compile(r"level\._zombie_custom_add_weapons\s*=")
_FRAMEWORK_ENTRY = re.compile(r"zm_usermap::main\(\s*\)\s*;")


def check_weapon_table_wiring(
    manifest: str, server: str, client: str, *, map_name: str
) -> Report:
    r"""W4: a custom price reaches the charge **and** the prompt, or neither.

    Four ways a map can ship a weapon table and still be wrong, and the game
    reports none of them:

    * the hook is assigned after the framework entry, where
      ``DEFAULT( level._zombie_custom_add_weapons, &custom_add_weapons )``
      (``zm_usermap.gsc:135``) has already filled it in, so the map's loader
      is never called and every price is Treyarch's;
    * the server loads the map's table and the **client** does not.  The
      number on the prompt is filled in client side and ``zm_usermap.csc:83``
      has no hook, so the player is charged the map's price and shown the
      stock one.  This is the failure this check exists for;
    * a script loads a table the manifest never declared, so the linker never
      packed it and ``TableLookupRow`` answers nothing at run time -- the
      stock prices, silently;
    * the loader replaces the stock hook without loading the stock table
      first, which does not re-price anything, it *empties* the level's
      weapon set down to the map's own rows.

    The stock table is exempt from the manifest rule: every zm level already
    has it through ``include,zm_levelcommon_weapons``.
    """
    report = Report()
    server_loads = _table_loads(server)
    client_loads = _table_loads(client)
    declared = {
        line.split(",", 1)[1].strip()
        for line in manifest.splitlines()
        if line.strip().startswith("stringtable,")
    }
    own = f"gamedata/weapons/zm/{map_name}_weapons.csv"

    if server_loads and not _ADD_WEAPONS_HOOK.search(server):
        report.add(
            error(
                "W4",
                "the server script loads a weapon table but never assigns "
                "level._zombie_custom_add_weapons, so nothing calls the loader "
                "and every price stays Treyarch's",
            )
        )
    for match in _ADD_WEAPONS_HOOK.finditer(server):
        entry = _FRAMEWORK_ENTRY.search(server)
        if entry is not None and match.start() > entry.start():
            report.add(
                error(
                    "W4",
                    "level._zombie_custom_add_weapons is assigned after "
                    "zm_usermap::main(). The framework's DEFAULT has already "
                    "filled it in by then (zm_usermap.gsc:135), so the map's "
                    "loader is never called",
                )
            )
    if server_loads and STOCK_TABLE not in server_loads:
        report.add(
            error(
                "W4",
                f"the server's {TABLE_LOADER} replaces the stock weapon loader "
                f"but never loads {STOCK_TABLE}, so the level's weapon set is "
                "only this map's own rows: every stock weapon disappears from "
                "the box and from every buy that was not re-priced",
            )
        )
    if own in server_loads and own not in client_loads:
        report.add(
            error(
                "W4",
                f"the server loads {own} and the client script does not. The "
                "purchase prompt's number is client side and has no hook, so "
                "the player would be charged this map's price and shown the "
                "stock one",
            )
        )
    if own in client_loads and own not in server_loads:
        report.add(
            error(
                "W4",
                f"the client loads {own} and the server does not, so the prompt "
                "would show a price nothing charges",
            )
        )
    for table in sorted(set(server_loads) | set(client_loads)):
        if table == STOCK_TABLE:
            continue
        if table not in declared:
            report.add(
                error(
                    "W4",
                    f"a script loads the weapon table {table!r} and the manifest "
                    "does not declare it, so the linker never packed it and the "
                    "lookup finds nothing at run time -- stock prices, silently",
                )
            )
    for table in sorted(declared):
        if table.endswith("_weapons.csv") and table not in set(server_loads) | set(
            client_loads
        ):
            report.add(
                warning(
                    "W4",
                    f"the manifest declares the weapon table {table!r} and no "
                    "script loads it, so it is packed and never read",
                )
            )
    return report


def _table_loads(script: str) -> list[str]:
    return [match.group(1) for match in _LOAD_TABLE.finditer(script)]


def check_weapon_table(
    text: str, manifest: str, *, label: str = "weapon table"
) -> Report:
    r"""W5: a table row naming a weapon that does not exist.

    The linker cannot catch this one and that is the whole reason it is here.
    A ``weapon`` line in the zone naming an asset the database does not have
    stops the link with an error -- good.  A table **row** naming a weapon
    that does not exist is invisible to it: a string table is opaque, the
    linker packs the text.  What happens instead is ``getweapon`` answering
    for a name nothing backs, ``add_zombie_weapon`` filing a struct against
    it, and the buy handing out nothing in a play session.

    A name counts as existing when it is a row of the stock level table
    (:data:`~zmforge.blueprint.catalogue.LEVEL_WEAPONS`) or the manifest
    declares it -- ``weapon,<name>_zm``, which is the pairing the probe map
    linked with, or ``weapon,<name>`` for an asset spelled without the mode
    suffix.
    """
    report = Report()
    rows = parse_table(text)
    if not rows:
        report.add(error("W5", f"{label} is empty"))
        return report
    header = rows[0]
    if header != list(WEAPON_TABLE_COLUMNS):
        report.add(
            warning(
                "W5",
                f"{label}: the header row is not the install's own. The loader "
                "reads columns by index, so a table whose columns are in a "
                "different order loads the wrong field into every weapon",
            )
        )
    declared = {
        line.split(",", 1)[1].strip()
        for line in manifest.splitlines()
        if line.strip().startswith("weapon,")
    }
    width = len(WEAPON_TABLE_COLUMNS)
    for number, row in enumerate(rows[1:], start=2):
        name = row[NAME_COLUMN] if row else ""
        if not name:
            report.add(error("W5", f"{label} row {number} names no weapon"))
            continue
        if len(row) < width:
            report.add(
                error(
                    "W5",
                    f"{label} row {number} ({name}) has {len(row)} fields and the "
                    f"table has {width} columns; the loader reads a fixed set of "
                    "indices, so the missing ones are undefined in a live game",
                )
            )
        for column, weapon in (
            ("weapon_name", name),
            ("upgrade_name", row[1] if len(row) > 1 else ""),
        ):
            if not weapon or weapon in LEVEL_WEAPONS:
                continue
            if weapon in declared or f"{weapon}_zm" in declared:
                continue
            # The upgraded form of a stock weapon is not a row of the table
            # -- LEVEL_WEAPONS is its weapon_name column -- but it exists:
            # load_weapon_spec_from_table calls include_weapon on the upgrade
            # column too (_zm_weapons.gsc:3399), and every stock row that has
            # one spells it "<weapon>_upgraded" (read off the install's own
            # table).  Anything else in that column is a typo.
            if (
                column == "upgrade_name"
                and name in LEVEL_WEAPONS
                and weapon in (f"{name}_upgraded", name)
            ):
                continue
            report.add(
                error(
                    "W5",
                    f"{label} row {number} names {weapon!r} as its {column} and "
                    "nothing has that weapon: it is not a row of the stock level "
                    "table and the manifest declares no weapon asset for it. The "
                    "linker cannot see this -- a string table is opaque to it -- "
                    "so the failure would be a buy that hands out nothing",
                )
            )
        cost = row[COST_COLUMN] if len(row) > COST_COLUMN else ""
        if not re.fullmatch(r"-?\d+", cost or ""):
            report.add(
                error(
                    "W5",
                    f"{label} row {number} ({name}) has the cost {cost!r}, which "
                    "int() reads as 0: the buy would be free and say so",
                )
            )
        elif int(cost) < 0:
            report.add(
                error("W5", f"{label} row {number} ({name}) has a negative cost")
            )
    return report


# --------------------------------------------------------------------------
# Z27: a collision file a prop's asset-database entry names and nobody wrote
# --------------------------------------------------------------------------
_GDT_HEAD = re.compile(r'^\s*"([^"]+)"\s*\(\s*"([^"]+)"\s*\)\s*$')
_GDT_FIELD = re.compile(r'^\s*"([^"]*)"\s*"(.*)"\s*$')


def check_prop_collision_files(
    gdt_text: str, *, model_export: Path, collmaps: Path, label: str = "props gdt"
) -> Report:
    r"""Z27: every collision file a props ``.gdt`` names exists on this root.

    A prop's collision is two files, and the asset-database entry names both
    of them by string:

    ``BulletCollisionFile``
        ``<map>\<asset>_col.XMODEL_BIN``, the bullet mesh.  The prop chain
        writes the **text** export beside the model and the binary comes from
        ``export2bin`` afterwards, so the GDT names a file no step in this
        package produces.  Nothing noticed until an entry referenced one:
        the linker then reports it against the model, not against the
        collision, which is why it read as an unrelated failure.
        [Measured: ``model_export/zm_forge_gate_props.gdt`` on the
        Wine root names four ``_col.XMODEL_BIN`` files and
        ``model_export/zm_forge_gate/`` holds none of them.]
    ``CollisionMap``
        a bare filename in ``share\raw\collmaps``, which the install step copies
        there.  Same failure mode, one directory over.

    Both are errors.  An entry naming a file that is not there is the one
    kind of missing asset that costs a build to find out about, and it is
    free to find out about here.
    """
    report = Report()
    for name, gdf, fields in _gdt_entries(gdt_text):
        if gdf != "xmodel.gdf":
            continue
        bullet = fields.get("BulletCollisionFile", "").replace("\\\\", "\\")
        lod = fields.get("BulletCollisionLOD", "")
        collmap = fields.get("CollisionMap", "")
        if bullet:
            target = model_export.joinpath(*bullet.replace("\\", "/").split("/"))
            if not target.exists():
                report.add(
                    error(
                        "Z27",
                        f"{label}: {name} names the bullet collision file "
                        f"{bullet!r} and {target} does not exist. The prop chain "
                        "writes the .XMODEL_EXPORT and export2bin makes the "
                        ".XMODEL_BIN; without that step the entry points at "
                        "nothing and the linker reports it against the model",
                    )
                )
        elif lod == "Custom":
            report.add(
                error(
                    "Z27",
                    f"{label}: {name} asks for custom bullet collision and names "
                    "no file, so it converts with no collision at all",
                )
            )
        if collmap:
            target = collmaps / collmap
            if not target.exists():
                report.add(
                    error(
                        "Z27",
                        f"{label}: {name} names the collmap {collmap!r} and "
                        f"{target} does not exist, so cod2map has nothing to bake "
                        "and a solid prop is walked through",
                    )
                )
    return report


def _gdt_entries(text: str):
    """``(name, gdf, fields)`` per entity in a ``.gdt``, in file order."""
    name = gdf = None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        head = _GDT_HEAD.match(line)
        if head is not None:
            name, gdf = head.group(1), head.group(2)
            fields = {}
            continue
        if name is not None and line.strip() == "}":
            yield name, gdf or "", fields
            name = gdf = None
            continue
        pair = _GDT_FIELD.match(line)
        if pair is not None and name is not None:
            fields[pair.group(1)] = pair.group(2)


# --------------------------------------------------------------------------
# Z45: a collision file this compiler build cannot parse
# --------------------------------------------------------------------------
#: A bare keyword line inside a collmap brush.  ``cod2map64`` reads a brush
#: body as faces -- a line of three bracketed points, a material and two sets
#: of six numbers -- and the only bare words it tolerates before them are
#: ``guid``, ``contents``, ``matName`` and ``collmap_bone``.  A ``physics_*``
#: word where a face should start is a solid primitive from a newer authoring
#: tool than the compiler the mod tools ship.
# The trailing ``\r`` is load-bearing for a caller that read the file in
# binary and decoded it: every collmap on the mod tools install is CRLF.
_COLLMAP_PRIMITIVE = re.compile(r"^[ \t]*(physics_[A-Za-z0-9_]+)[ \t\r]*$", re.M)


def collmap_primitives(text: str) -> list[tuple[int, str]]:
    """``(line number, keyword)`` for every rejected primitive in a collmap.

    Read as "a word this compiler does not know", not as an allowlist of
    named offenders: only ``physics_cylinder`` has been seen in the wild
    (28 of the 258 collmaps the mod tools install ships, measured) and
    naming the others would be guessing at which spellings exist.
    """
    return [
        (text.count("\n", 0, match.start()) + 1, match.group(1))
        for match in _COLLMAP_PRIMITIVE.finditer(text)
    ]


def check_collmap_primitives(
    document: Document, *, collmaps: Path | None, label: str = "collmap"
) -> Report:
    r"""Z45: every collmap this map asks ``cod2map64`` to bake, it can parse.

    WHY THIS EXISTS, measured.  Marking the watermelon solid put
    ``use_collmap "1"`` on ``p7_food_fruit_watermelon``, so the compiler
    opened Treyarch's own collision file for it, and the build stopped at::

        ERROR: File .../share/raw/collmaps/p7_food_fruit_watermelon.map,
        line 23: MatchToken: got 'physics_cylinder', expected '('

    The same shape of failure as ``F9``, one file over: a keyword the parser
    does not know where it expects a face, reported against a file nobody in
    this repository wrote.  28 of the 258 collmaps on the mod tools install carry such
    a primitive; all 28 are out of
    :data:`zmforge.props.collision.STOCK_COLLMAPS`, so a prop that needs one
    gets a generated box instead.  This is the backstop for the ones that come
    back: the set is a recorded list, an install step can put any file at
    that filename, and finding out from ``cod2map64`` costs a whole build.

    An error, and against the *staged* file rather than the list: what the
    compiler reads is whatever sits at ``share\raw\collmaps\<model>.map`` on
    the root being built, which is the only copy that can be wrong.
    """
    report = Report()
    if collmaps is None:
        return report  # nothing staged to read; Z21 answers for a missing one
    directory = Path(collmaps)
    models = sorted(
        {
            entity.value("model")
            for entity in document.entities_of("misc_model")
            if entity.value("use_collmap") == "1" and entity.value("model")
        }
    )
    for model in models:
        target = directory / f"{model}.map"
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # absent is Z21's finding and Z27's, not this one
        for line, keyword in collmap_primitives(text):
            report.add(
                error(
                    "Z45",
                    f"{label}: {target.name} line {line} uses the {keyword!r} "
                    "primitive, which this cod2map64 build does not parse -- "
                    f"the compile stops with \"MatchToken: got '{keyword}', "
                    "expected '('\" and writes no BSP. Drop the model from "
                    "STOCK_COLLMAPS so a generated box is written instead, or "
                    "stage a collmap of plain brushes",
                )
            )
    return report


#: How loudly ``Z44`` speaks on this side.  The same word as
#: ``verify.model.LAYOUT_SEVERITY`` and for the same reason: until the placer
#: states its placements as relations, a real map has hundreds of these and an
#: error would fail every build.
LAYOUT_SEVERITY = "warning"


def check_prop_layout_text(map_text: str, *, severity: str = LAYOUT_SEVERITY) -> Report:
    """Z44 over the written text: is every prop somewhere a prop can be?

    The file side of :func:`zmforge.verify.model.check_prop_layout`, and it
    exists because a map that came back from an editor has no blueprint
    behind it: the props, the rooms (the zone manager's own player volumes),
    the floors, the ground and the interactive prefabs all come out of the
    text the compiler will read.  Same rules, same code, same thresholds.
    """
    from ..placement.audit import check_layout, layout_from_map_text

    report = Report()
    report.extend(
        check_layout(layout_from_map_text(map_text), severity=severity, code="Z44")
    )
    return report


def check_localized_strings(
    manifest: str,
    *,
    strings_dir: Path | None,
    label: str = "localizedstrings",
) -> Report:
    r"""Z24, file side: a ``localize,`` line with no ``.str`` behind it.

    **Without this check a build breaks late.**  A map that declares
    ``localize,<name>`` with no ``.str`` in place in the tools tree when the
    link runs links against a file that is not there, and stops with, twice,
    once per fastfile::

        ^1Localization ERROR: Unable to load "localizedstrings/<name>.str"!
          localize:<name>

    Moving the file aside and re-linking prints the same two lines
    [measured], so the message means exactly what it
    says and the path it prints is
    ``share\raw\english\localizedstrings\<name>.str`` under the tools root.

    Every other static check can pass such a build: the compile is clean, the
    manifest is well formed, the script references strings that really are in
    the file the generator wrote.  Nothing asked the one question that mattered -- whether
    the file would be *there* -- which is the same question ``W5`` already asks
    of a declared weapon table.  So this is an **error**, not a warning: a
    declared string with no file is a link that stops, not a prompt that reads
    oddly.

    ``strings_dir`` of ``None`` means the caller cannot say where the ``.str``
    files live, and then nothing is checked rather than everything being
    guessed at.
    """
    report = Report()
    if strings_dir is None:
        return report
    for line in manifest.splitlines():
        stripped = line.strip()
        if not stripped.startswith("localize,"):
            continue
        name = stripped.split(",", 1)[1].strip()
        if not name:
            continue
        path = Path(strings_dir) / f"{name}.str"
        if path.exists():
            continue
        report.add(
            error(
                "Z24",
                f"{label}: the manifest declares {stripped!r} and {path} does "
                "not exist. The linker stops on this, once per fastfile, with "
                f'Localization ERROR: Unable to load "localizedstrings/{name}.str"! '
                "-- so the map does not build at all. Either the generator did "
                "not write the file or the file was not in place when the link "
                "ran",
            )
        )
    return report


def check_written_files(
    map_path: str | Path,
    server_script_path: str | Path,
    client_script_path: str | Path,
    manifest_path: str | Path,
    *,
    map_name: str | None = None,
    strict_materials: bool = False,
    loading_image_path: str | Path | None = None,
    preview_image_path: str | Path | None = None,
    player_slots: int | None = None,
    weapon_table_path: str | Path | None = None,
    localized_strings_path: str | Path | None = None,
    props_gdt_path: str | Path | None = None,
    model_export_dir: str | Path | None = None,
    collmap_dir: str | Path | None = None,
    sound_bank_dir: str | Path | None = None,
    platform_sound_bank_dir: str | Path | None = None,
    sound_source_dir: str | Path | None = None,
) -> Report:
    """Every static check, over the files a commit writes.

    The two image paths are optional so a caller checking an older map, or a
    map committed with ``loading_screen=False``, is not told off for files it
    never asked for.
    """
    map_text = Path(map_path).read_text(encoding="utf-8", errors="replace")
    server = Path(server_script_path).read_text(encoding="utf-8", errors="replace")
    client = Path(client_script_path).read_text(encoding="utf-8", errors="replace")
    manifest = Path(manifest_path).read_text(encoding="utf-8", errors="replace")
    name = map_name or Path(map_path).stem

    document = parse_map_text(map_text)
    report = check_map_text(map_text, label=Path(map_path).name)
    report.extend(
        check_gameplay(
            document,
            server,
            client_script=client,
            strict_materials=strict_materials,
            player_slots=player_slots,
        )
    )
    map_weapons = {
        line.split(",", 1)[1].strip()
        for line in manifest.splitlines()
        if line.strip().startswith("weapon,")
    }
    # A weapon asset is declared as "<name>_zm" and named in script without
    # the suffix (measured on the probe map), so Z22 has to know
    # both spellings before it calls one of them unknown.
    map_weapons |= {
        name[: -len("_zm")] for name in map_weapons if name.endswith("_zm")
    }
    report.extend(
        check_files_playtest(
            document,
            server,
            label=Path(server_script_path).name,
            weapons=map_weapons,
            collmaps=Path(collmap_dir) if collmap_dir else None,
        )
    )
    report.extend(
        check_collmap_primitives(
            document,
            collmaps=Path(collmap_dir) if collmap_dir else None,
            label="collmaps",
        )
    )
    report.extend(check_light_lod(document))
    report.extend(check_prop_layout_text(map_text))
    report.extend(check_server_script(server))
    report.extend(check_client_script(client))
    report.extend(check_script_soundness(server, label=Path(server_script_path).name))
    report.extend(check_script_soundness(client, label=Path(client_script_path).name))
    report.extend(check_manifest(manifest, name))
    report.extend(check_declarations(manifest, server, client, name))
    report.extend(check_weapon_table_wiring(manifest, server, client, map_name=name))
    if weapon_table_path is not None:
        table = Path(weapon_table_path)
        if table.exists():
            report.extend(
                check_weapon_table(
                    table.read_text(encoding="utf-8", errors="replace"),
                    manifest,
                    label=table.name,
                )
            )
        elif f"{name}_weapons.csv" in manifest:
            report.add(
                error(
                    "W5",
                    f"the manifest declares this map's weapon table and {table} "
                    "does not exist, so the link packs nothing and every price "
                    "is the stock one",
                )
            )
    if localized_strings_path is not None:
        # The path handed in is the map's own .str; every localize line in the
        # manifest is read out of the same folder, so the folder is what the
        # check wants (a build failed on exactly this, see
        # check_localized_strings).
        report.extend(
            check_localized_strings(
                manifest, strings_dir=Path(localized_strings_path).parent
            )
        )
    if sound_bank_dir is not None:
        report.extend(
            check_sound_bank(
                manifest,
                map_name=name,
                bank_dir=sound_bank_dir,
                platform_bank_dir=platform_sound_bank_dir,
                sound_source_dir=sound_source_dir,
            )
        )
    if props_gdt_path is not None and model_export_dir is not None:
        gdt = Path(props_gdt_path)
        if gdt.exists():
            report.extend(
                check_prop_collision_files(
                    gdt.read_text(encoding="utf-8", errors="replace"),
                    model_export=Path(model_export_dir),
                    collmaps=Path(collmap_dir or Path(model_export_dir).parent),
                    label=gdt.name,
                )
            )
    if loading_image_path is not None or preview_image_path is not None:
        report.extend(
            check_presentation(
                _optional_bytes(loading_image_path),
                _optional_bytes(preview_image_path),
            )
        )
    return report


def _optional_bytes(path: str | Path | None) -> bytes | None:
    if path is None:
        return None
    resolved = Path(path)
    return resolved.read_bytes() if resolved.exists() else None
