"""Model-level checks: is this blueprint a map the game can load?

These run before anything is written, so a mistake costs a message rather than
a build.  They are the agreements of spec 4.14 plus the structural
requirements scattered through sections 4 and 5: one starting zone, a light in
every room, an enclosure, a module for every machine, and the dog flag
consistent with what is actually placed.
"""

from __future__ import annotations

import math

from ..blueprint.elements import (
    SEALED_OPENING,
    Door,
    Enclosure,
    Lamp,
    Machine,
    Massing,
    MysteryBox,
    PlayerStart,
    PowerSwitch,
    Room,
    Spawn,
    ImportedMap,
    Window,
    Yard,
    Zone,
    STOCK_PLAYER_SLOTS,
)
from ..materials import BENIGN_MISSING, TOOL_MATERIALS, is_catalogued, is_pipeline_material
from ..blueprint.model import STEP_TOLERANCE, WALL_WEAPON_DROP
from ..blueprint.elements import WallWeapon
from ..blueprint.catalogue import BARRICADE_PREFAB_HIDE_DEBRIS, LEVEL_WEAPONS
from .. import lighting
from ..spatial import Axis, Point, Span
from .. import progress
from .report import Report, error, note, warning

__all__ = ["check_blueprint", "check_prop_layout", "LAYOUT_SEVERITY"]


def check_blueprint(blueprint, *, strict_materials: bool = False) -> Report:
    """Every model-level check, gathered into one report.

    The last three lines are the model side of :mod:`~zmforge.verify.playtest`,
    whose checks cover defects only play shows rather than a
    build; :mod:`~zmforge.verify.reachability`, which floods the map from the
    spawn; and :mod:`~zmforge.verify.documented`, whose thresholds come out of
    the settings file the mod tools ship.  All three import from this module --
    hence the imports inside the function.
    """
    from .approach import check_interactive_approach
    from .climb import check_zombie_climb
    from .documented import check_navmesh_geometry
    from .hanging import check_nothing_hangs
    from .playtest import check_blueprint_playtest
    from .reachability import check_reachability

    # Z46's fix passes are part of finishing a model, not of any one caller:
    # every top a player jumps onto and no walker reaches gets a stock zombie
    # traversal, or an invisible clip cap where none fits (Z46).  Run here so a test or script that checks a recipe's
    # blueprint directly sees the same map the build writes; idempotent, and
    # Project.commit has usually run them already (it reports the counts).
    from .camping import clip_camping_tops, reach_camping_tops

    reach_camping_tops(blueprint)
    clip_camping_tops(blueprint)

    report = Report()
    _check_zones(blueprint, report)
    _check_rooms_in_zones(blueprint, report)
    _check_playable_area_coverage(blueprint, report)
    _check_spawns(blueprint, report)
    _check_player_start(blueprint, report)
    _check_doors(blueprint, report)
    _check_clearance(blueprint, report)
    _check_sealed_openings(blueprint, report)
    _check_windows(blueprint, report)
    _check_machines(blueprint, report)
    _check_machine_clearance(blueprint, report)
    _check_interactives_have_their_backs_to_the_wall(blueprint, report)
    _check_interactives_keep_clear(blueprint, report)
    _check_lighting(blueprint, report)
    _check_reflection_probes(blueprint, report)
    _check_clear_of_solids(blueprint, report)
    _check_enclosure(blueprint, report)
    _check_nothing_to_fall_through(blueprint, report)
    _check_dogs(blueprint, report)
    _check_materials(blueprint, report, strict_materials)
    _check_models(blueprint, report)
    _check_wall_weapons(blueprint, report)
    _check_own_weapons(blueprint, report)
    _check_wall_buys_can_be_seen(blueprint, report)
    progress.stage("model checks 2/4: play checks, reachability, navmesh")
    report.extend(check_blueprint_playtest(blueprint))
    report.extend(check_reachability(blueprint))
    report.extend(check_nothing_hangs(blueprint))
    report.extend(check_navmesh_geometry(blueprint))
    report.extend(check_zombie_climb(blueprint))
    report.extend(check_interactive_approach(blueprint))
    progress.stage("model checks 3/4: props and doorways")
    report.extend(check_prop_layout(blueprint))
    from .doorways import check_doorways

    report.extend(check_doorways(blueprint))
    from .walls import check_props_inside_walls

    report.extend(check_props_inside_walls(blueprint))
    from .routes import check_room_routes

    report.extend(check_room_routes(blueprint))
    from .looks import check_looks

    report.extend(check_looks(blueprint))
    from .prop_rules import check_prop_rules

    report.extend(check_prop_rules(blueprint))
    from .glows import check_glows_blueprint

    report.extend(check_glows_blueprint(blueprint))
    from .quest_gates import check_quest_gates_blueprint

    report.extend(check_quest_gates_blueprint(blueprint))
    from .design import check_design

    progress.stage("model checks 4/4: design rules")
    report.extend(check_design(blueprint))
    from .gamble import check_gamble_blueprint

    report.extend(check_gamble_blueprint(blueprint))  # Z87
    from .layout_rules import check_layout_rules

    report.extend(check_layout_rules(blueprint))
    from .power_reach import check_power_reach

    report.extend(check_power_reach(blueprint))
    from .door_cover import check_door_cover

    report.extend(check_door_cover(blueprint))
    from .windows import check_windows

    report.extend(check_windows(blueprint))
    from .indoor_light import check_indoor_light

    report.extend(check_indoor_light(blueprint))  # Z88
    from .lining import check_lining

    report.extend(check_lining(blueprint))  # Z89
    from .exposed_faces import check_exposed_faces

    report.extend(check_exposed_faces(blueprint))
    return report


#: How loudly ``Z44`` speaks.  A warning, because the placer still deals
#: models by list position and a real map has hundreds of these: a test
#: map produced 329 over 2,199 props, none of them introduced by the caller
#: running the check.  It becomes an error the day the placer states its
#: placements as relations, and that is this one word.
LAYOUT_SEVERITY = "warning"


def check_prop_layout(blueprint, *, severity: str = LAYOUT_SEVERITY) -> Report:
    """Z44: is every prop somewhere a prop can be?

    The rules are :mod:`zmforge.placement.audit` and they are the placer's own
    relations asked of a finished layout, so the rule that will choose a
    position and the rule that judges one are one object.  Imported inside the
    function because that package reads the model palette
    (:mod:`zmforge.recipes.props`), which imports the blueprint, which imports
    this.
    """
    from ..placement.audit import check_layout, layout_from_blueprint

    report = Report()
    report.extend(
        check_layout(layout_from_blueprint(blueprint), severity=severity, code="Z44")
    )
    return report


def _check_zones(blueprint, report: Report) -> None:
    zones = blueprint.elements(Zone)
    if not zones:
        report.add(error("Z3", "the map has no zones, so the zone manager has nothing to enable"))
        return
    # Counted by zone *name*, not by volume: a starting zone owning two
    # volumes is one starting zone.  See the multi-volume note below.
    starting = [z for z in zones if z.starting]
    starting_names = sorted({z.name for z in starting})
    if len(starting_names) != 1:
        report.add(
            error(
                "Z3",
                "exactly one zone must be the starting zone, found "
                f"{len(starting_names)}"
                + (f" ({', '.join(starting_names)})" if starting_names else ""),
            )
        )
    # One zone may own several volumes, and Treyarch's own maps do it: stock
    # ``zone_init`` builds ``zone.volumes`` from ``GetEntArray( zone_name,
    # "targetname" )`` filtered to ``info_volume``
    # (``_zm_zonemgr.gsc:318-330``), so every volume carrying the name joins
    # the zone.  Measured on ``map_source/zm/zm_giant.map``: 32 player volumes
    # over 12 zone names, 9 of the 12 owning two or more -- ``outside_south_zone``
    # owns six.  So two Zone elements sharing a name is the shape of a
    # multi-volume zone, not a mistake.
    #
    # What *is* a mistake is the pair disagreeing about the zone.  ``zone_init``
    # reads the spawner set from ``zone.volumes[ 0 ].target`` alone
    # (``:345`` and again at ``:442``), and nothing fixes which volume the
    # engine hands back first, so two volumes of one name naming two spawn
    # sets means one of them is silently thrown away and which one is a
    # coin toss.  Every one of zm_giant's 32 volumes names the same target as
    # its siblings.
    by_name: dict[str, list] = {}
    for zone in zones:
        by_name.setdefault(zone.name, []).append(zone)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        sets = sorted({z.spawn_set for z in group})
        if len(sets) > 1:
            report.add(
                error(
                    "Z3",
                    f"the {len(group)} volumes named {name!r} collect "
                    f"{len(sets)} different spawn sets ({', '.join(sets)}); "
                    "zone_init reads only zone.volumes[0].target, and which "
                    "volume comes back first is not fixed, so all but one of "
                    "these is silently ignored",
                    group[0].id,
                )
            )
        # ``starting`` is deliberately *not* required to agree across a zone's
        # volumes.  It is a property of the zone, not of a box: what it
        # decides is whether the name goes in ``init_zones``, and one entry
        # registers the zone however many volumes carry the name.  So a zone
        # is the starting zone if any of its volumes says so, which is what
        # ``_resync_zone_list`` and the starting-zone count above both read.
    if blueprint.script.zones and blueprint.script.zones[0] != (
        starting[0].name if starting else None
    ):
        report.add(
            error(
                "Z3",
                f"init_zones[0] is {blueprint.script.zones[0]!r} but the starting "
                f"zone is {starting[0].name if starting else 'undefined'!r}",
            )
        )

    reachable = {z.name for z in zones if z.starting}
    # A zone the map's own script puts players into (a sealed start hallway,
    # a teleport's destination) is entered without a door edge.
    reachable |= {entry.zone for entry in blueprint.script.entries}
    edges = list(blueprint.script.edges)
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge.zone_a in reachable and edge.zone_b not in reachable:
                reachable.add(edge.zone_b)
                changed = True
            elif edge.zone_b in reachable and edge.zone_a not in reachable:
                reachable.add(edge.zone_a)
                changed = True
    said: set[str] = set()
    for zone in zones:
        if zone.name in reachable or zone.name in said:
            continue
        said.add(zone.name)  # one finding per zone, not one per volume
        report.add(
            warning(
                "Z3",
                f"zone {zone.name!r} is not reachable through any door flag, so "
                "it never activates",
                zone.id,
            )
        )


def _check_rooms_in_zones(blueprint, report: Report) -> None:
    """A room no zone volume covers is a room the zone manager cannot see.

    The player standing in it is in no zone, so nothing there spawns and
    nothing there counts as occupied.  That is a mistake when the room is
    meant to be played in and deliberate when it is only meant to be looked
    into through a sealed opening, so it is a warning and it names the room.
    """
    zones = blueprint.elements(Zone)
    for room in blueprint.elements(Room):
        if not room.reachable:
            continue  # the map has declared it a room nobody stands in
        centre = room.interior.centre
        if not any(zone.bounds.holds_flat(centre.x, centre.y) for zone in zones):
            report.add(
                warning(
                    "Z3",
                    f"room {room.id} lies in no zone volume, so the zone manager "
                    "never activates it; deliberate for a room only meant to be "
                    "seen into, a mistake for one meant to be played in",
                    room.id,
                )
            )


def _standing_patches(blueprint) -> list[tuple[str, str, Span, float]]:
    """Every rectangle of surface a player can stand on, with its height.

    ``(label, element id, footprint, z)``, where ``z`` is the walkable
    surface under the player's feet.  Four kinds answer, which is the same
    set :meth:`Blueprint.ground_under` reads: a room's floor, the top of a
    walkable massing solid (a step, a slab, a deck), the threshold of an
    opening low enough to walk through, and a terrain cell.

    Left out on purpose: a yard (the barricade prefab stops the player at the
    wall line, so the pocket outside it is the zombies' side), a room or a
    massing the map has declared unreachable, and an opening whose sill is
    more than a step up, which is a window or a viewing slot rather than a
    threshold.
    """
    from ..blueprint.elements import Terrain
    from ..blueprint.model import _solid_bounds

    patches: list[tuple[str, str, Span, float]] = []
    for room in blueprint.elements(Room):
        if not room.reachable:
            continue
        patches.append((f"the floor of {room.id}", room.id, room.interior, room.floor_z))
        for index, box in enumerate(room.aperture_boxes):
            if box.mins.z > room.floor_z + STEP_TOLERANCE:
                continue
            patches.append(
                (f"the threshold of {room.id} opening {index}", room.id, box, box.mins.z)
            )
    for massing in blueprint.elements(Massing):
        if not massing.walkable or not massing.reachable:
            continue
        for order, solid in enumerate(massing.solids):
            box = _solid_bounds(solid)
            patches.append((f"the top of {massing.id}", massing.id, box, box.maxs.z))
    for terrain in blueprint.elements(Terrain):
        record = terrain.record
        edge = record.footprint
        for row in range(record.rows):
            for col in range(record.cols):
                x0 = record.anchor.x + col * record.x_cell
                y0 = record.anchor.y + row * record.y_cell
                x1, y1 = x0 + record.x_cell, y0 + record.y_cell
                cell = Span.flat_ok(Point(x0, y0, 0.0), Point(x1, y1, 0.0))
                corners = [
                    record.sample(min(x, edge.maxs.x - 1e-6), min(y, edge.maxs.y - 1e-6)).z
                    for x in (x0, x1)
                    for y in (y0, y1)
                ]
                # Both ends of the cell's height: the low corner is the one
                # that can fall out of the bottom of a zone box and the high
                # corner the one that can rise out of its top.
                for height in {min(corners), max(corners)}:
                    patches.append(
                        (f"terrain {terrain.id} at row {row} column {col}",
                         terrain.id, cell, height)
                    )
    return patches


def _uncovered_cells(patch: Span, z: float, zones) -> list[tuple[Span, float]]:
    """Where in ``patch`` a player standing at ``z`` touches no zone volume.

    Exhaustive rather than sampled.  Every box in the model is axis aligned,
    so over one rectangle of surface the answer changes only where a zone
    volume's edge crosses it: cutting the rectangle on those edges and
    testing one point inside each cell decides the whole rectangle.  A player
    at ``(x, y)`` touches a volume when the hull ``x +/- 15``, ``y +/- 15``,
    ``z`` to ``z + 72`` overlaps it, so the covered set is the union of the
    volumes grown by half a hull, and only a **positive** overlap counts:
    whether ``IsTouching`` accepts hull and volume meeting exactly on a plane
    is unmeasured, and a map that depends on that answer is a map that is one
    unit from killing the player.
    """
    half = PLAYER_HULL_WIDTH / 2.0
    top = z + PLAYER_HULL_HEIGHT
    reach = [
        (zone.bounds.mins.x - half, zone.bounds.maxs.x + half,
         zone.bounds.mins.y - half, zone.bounds.maxs.y + half)
        for zone in zones
        if min(zone.bounds.maxs.z, top) - max(zone.bounds.mins.z, z) > 0.0
    ]
    cuts_x = sorted(
        {patch.mins.x, patch.maxs.x}
        | {v for r in reach for v in r[:2] if patch.mins.x < v < patch.maxs.x}
    )
    cuts_y = sorted(
        {patch.mins.y, patch.maxs.y}
        | {v for r in reach for v in r[2:] if patch.mins.y < v < patch.maxs.y}
    )
    out: list[tuple[Span, float]] = []
    for x0, x1 in zip(cuts_x, cuts_x[1:]):
        for y0, y1 in zip(cuts_y, cuts_y[1:]):
            mid_x, mid_y = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            if any(
                rx0 < mid_x < rx1 and ry0 < mid_y < ry1 for rx0, rx1, ry0, ry1 in reach
            ):
                continue
            out.append(
                (
                    Span.flat_ok(Point(x0, y0, z), Point(x1, y1, z)),
                    (x1 - x0) * (y1 - y0),
                )
            )
    return out


def _check_playable_area_coverage(blueprint, report: Report) -> None:
    """Z18: nowhere a player can stand is outside every player volume.

    This is the one per-position path in stock zombies that turns a down into
    an outright kill, and it is silent until somebody plays the map.
    ``_zm.gsc`` threads ``player_out_of_playable_area_monitor`` on every
    player (:2035); every 3 seconds, if the player is in no life brush and
    either in a kill brush or not ``in_enabled_playable_area``, it plays
    Sam's laugh, waits half a second and does ``self.health + 1000`` damage
    with ``bleedout time`` set to zero.  On screen that is an instant death,
    not a down, and because the poll is every 3 seconds it happens *some* of
    the times the player stands in the same place.

    ``in_enabled_playable_area`` (:1999) walks every entity with
    ``script_noteworthy player_volume`` and returns true only where
    ``zm_zonemgr::zone_is_enabled( volume.targetname )`` and the player
    ``IsTouching`` that volume, so a place the volumes do not reach is out of
    bounds even with solid floor under it and walls around it.

    Zone volumes sized to the room interior fail this at every doorway: the
    interior stops at the inside face of the wall, so the band of two 16-unit
    wall thicknesses between two rooms is in no volume, and a 30-unit player
    standing in the middle of a 32-unit band touches neither side.  Worst of
    all is a deck laid *in* that band between two rooms, say 128 x 32: a
    surface the map asks the player to walk over, entirely out of bounds.
    """
    zones = [z for z in blueprint.elements(Zone) if z.bounds is not None]
    if not zones:
        return  # _check_zones already reports a map with no volumes at all
    worst: dict[tuple[str, str], tuple[float, Span]] = {}
    for label, element_id, patch, z in _standing_patches(blueprint):
        for cell, area in _uncovered_cells(patch, z, zones):
            total, biggest = worst.get((label, element_id), (0.0, cell))
            if area > (biggest.extent(Axis.X) * biggest.extent(Axis.Y)):
                biggest = cell
            worst[(label, element_id)] = (total + area, biggest)
    for (label, element_id), (area, cell) in sorted(
        worst.items(), key=lambda item: -item[1][0]
    ):
        spot = cell.centre
        report.add(
            error(
                "Z18",
                f"{label} has {area:.0f} square units where a standing player "
                f"touches no player_volume, around "
                f"({spot.x:g}, {spot.y:g}, {cell.mins.z:g}): the "
                "out-of-playable-area monitor kills a player there outright "
                "(health + 1000 damage, bleedout zero) rather than downing them",
                element_id,
            )
        )


def _check_spawns(blueprint, report: Report) -> None:
    zones = blueprint.elements(Zone)
    spawns = blueprint.elements(Spawn)
    if not spawns:
        report.add(error("Z4", "the map has no zombie spawn structs"))
    # By zone name: a zone owning several volumes is still one zone with one
    # spawn set (``_zm_zonemgr.gsc:318`` gathers the volumes by targetname,
    # ``:345`` reads the set off the first of them), so it wants one finding.
    first_of: dict[str, Zone] = {}
    for zone in zones:
        first_of.setdefault(zone.name, zone)
    for zone in first_of.values():
        mine = [s for s in spawns if s.zone_name == zone.name]
        if not mine:
            report.add(
                error(
                    "Z4",
                    f"zone {zone.name!r} has no spawn struct, so no zombie ever "
                    "appears in it; a zone collects its spawn locations from "
                    "the structs named by its volume's target "
                    "(_zm_zonemgr.gsc zone_init), create_spawner_list only "
                    "gathers locations from zones that are active -- the "
                    "occupied one and the zones a set flag connects to it -- "
                    "and both round loops in _zm.gsc spin on "
                    "'while ( level.zm_loc_types[\"zombie_location\"].size "
                    "<= 0 ) wait 0.1;', so a player alone in this zone gets "
                    "a round that never starts",
                    zone.id,
                )
            )
        for spawn in mine:
            if spawn.spawn_set != zone.spawn_set:
                report.add(
                    error(
                        "Z4",
                        f"spawn {spawn.id} is tagged {spawn.spawn_set!r} but zone "
                        f"{zone.name!r} collects {zone.spawn_set!r}",
                        spawn.id,
                    )
                )
    for spawn in spawns:
        if not spawn.link_tag:
            report.add(
                error(
                    "Z4",
                    "a spawn struct with no script_string produces zombies that "
                    "stand still",
                    spawn.id,
                )
            )
        ground = blueprint.ground_under(
            spawn.position.x, spawn.position.y, below=spawn.position.z
        )
        if not ground.found:
            report.add(
                error("Z6", "there is no floor under this spawn struct", spawn.id)
            )
            continue
        delta = spawn.position.z - ground.z
        if delta > 8.0 or delta < -0.5:
            report.add(
                error(
                    "Z6",
                    f"spawn sits {delta:+.1f} units from the surface at "
                    f"z={ground.z:g} ({ground.source}); spawns sit on the floor",
                    spawn.id,
                )
            )
    if not any(s.with_factory for s in spawns):
        report.add(
            error(
                "Z5",
                "no spawn carries a zombie factory; with no entity tagged "
                "zombie_spawner the round starts and no zombie is ever made",
            )
        )


def _check_player_start(blueprint, report: Report) -> None:
    starts = blueprint.elements(PlayerStart)
    if len(starts) != 1:
        report.add(
            error("Z1", f"a map needs exactly one player start set, found {len(starts)}")
        )
        return
    start = starts[0]
    if start.slots < STOCK_PLAYER_SLOTS:
        report.add(
            error(
                "Z1",
                f"a player start needs at least {STOCK_PLAYER_SLOTS} slots, "
                f"got {start.slots}; a stock game seats four and the fifth "
                "player onwards lands on the first struct",
                start.id,
            )
        )
    positions = start.slot_positions()
    for index, left in enumerate(positions):
        for right in positions[index + 1 :]:
            if left.distance_to(right) < 32.0:
                report.add(
                    error(
                        "Z1",
                        f"two initial spawn slots are {left.distance_to(right):.1f} "
                        "units apart; two players would spawn on one point",
                        start.id,
                    )
                )
    # Every slot, not just the centre: a set sized for eight covers more
    # floor than one sized for four, and a slot off the edge of it drops that
    # player through the world.
    for index, point in enumerate(positions, start=1):
        ground = blueprint.ground_under(point.x, point.y, below=point.z)
        if not ground.found:
            report.add(
                error(
                    "Z1",
                    f"initial spawn slot {index} of {start.slots} at "
                    f"({point.x:.0f}, {point.y:.0f}) is not over any floor",
                    start.id,
                )
            )


def _check_doors(blueprint, report: Report) -> None:
    flags = [edge.flag for edge in blueprint.script.edges]
    for door in blueprint.elements(Door):
        if door.price <= 0:
            report.add(
                error("Z7", f"door price must be positive, got {door.price}", door.id)
            )
        if flags.count(door.flag) != 1:
            report.add(
                error(
                    "Z7",
                    f"flag {door.flag!r} appears in {flags.count(door.flag)} zone "
                    "edges; it must appear in exactly one",
                    door.id,
                )
            )
        if door.zone_a == door.zone_b:
            report.add(
                error("Z7", f"door joins zone {door.zone_a!r} to itself", door.id)
            )


#: The player's collision width in world units.  **[stock-source]**, read out
#: of the shipped scripts on the mod tools install: ``#define PLAYER_RADIUS 15`` in
#: ``scripts/shared/player_shared.gsc:15`` and ``15.0`` in
#: ``scripts/zm/_zm_unitrigger.gsc:20``, and the bot debug box is drawn
#: ``Box( self.origin, ( -15, -15, 0 ), ( 15, 15, 72 ) )``
#: (``scripts/shared/bots/_bot.gsc:741``).  So 30 across, not the 32 this
#: constant carried as an inherited guess: those two units are the whole
#: margin a 32-unit wall band leaves, which is why the playable-area gap at
#: every doorway of a generated map measured as covered and played as a
#: random instant death (see :func:`_check_playable_area_coverage`).
PLAYER_HULL_WIDTH = 30.0

#: The standing player's height, from the same debug box.  **[stock-source]**
PLAYER_HULL_HEIGHT = 72.0

#: The narrowest walkable width this package passes without comment: the hull
#: plus 8 units of clearance on each side.  Two players abreast need twice the
#: hull, so anything under 64 is single-file by construction, and 48 is the
#: narrowest single-file passage we will write.
SINGLE_FILE_WIDTH = 48.0


def _check_clearance(blueprint, report: Report) -> None:
    """Can a body fit through the holes, and along the rooms, this map has?

    Two separate questions with two different verdicts.  A **doorway** (an
    opening whose sill is on the floor) narrower than the player's own hull is
    an error: it is drawn as a way through and is not one, and no gag needs
    it.  A **room** whose interior is narrower than the hull on a horizontal
    axis is a warning: a niche the player can look into but not stand in is a
    legitimate thing to build -- a cupboard the depth of the wall it is cut
    into, for instance -- and only the mapper knows which it is.

    Between the hull and :data:`SINGLE_FILE_WIDTH` both are warnings that say
    how much room is left, because that is the band where one player fits and
    a second cannot pass.
    """
    from ..spatial import Axis

    for room in blueprint.elements(Room):
        for aperture, box in zip(room.apertures, room.aperture_boxes):
            if aperture.sill > 0.0:
                continue  # a window is not a way through
            if aperture.width < PLAYER_HULL_WIDTH:
                report.add(
                    error(
                        "W2",
                        f"a doorway {aperture.width:g} units wide is narrower than "
                        f"the player's {PLAYER_HULL_WIDTH:g}-unit hull, so nobody "
                        "passes through it",
                        room.id,
                    )
                )
            elif aperture.width < SINGLE_FILE_WIDTH:
                report.add(
                    warning(
                        "W2",
                        f"a doorway {aperture.width:g} units wide leaves "
                        f"{aperture.width - PLAYER_HULL_WIDTH:g} units of clearance "
                        f"around a {PLAYER_HULL_WIDTH:g}-unit hull; it is single "
                        "file at best",
                        room.id,
                    )
                )
        interior = room.interior
        for axis in (Axis.X, Axis.Y):
            extent = interior.extent(axis)
            if extent < PLAYER_HULL_WIDTH:
                report.add(
                    warning(
                        "W2",
                        f"room {room.id} is {extent:g} units across on {axis.name}, "
                        f"narrower than the player's {PLAYER_HULL_WIDTH:g}-unit "
                        "hull: it can be looked into but not stood in",
                        room.id,
                    )
                )
            elif extent < SINGLE_FILE_WIDTH:
                report.add(
                    warning(
                        "W2",
                        f"room {room.id} is {extent:g} units across on {axis.name}; "
                        "one player fits and a second cannot pass",
                        room.id,
                    )
                )


def _check_sealed_openings(blueprint, report: Report) -> None:
    """A door leaf and a static pane cannot share a hole.

    ``seal_opening`` puts an immovable brush where a door leaf would sit.  A
    door hung in the same hole takes the money, plays its move and leaves the
    pane standing, which is the one failure mode of the operation that costs a
    playtest rather than a compile.
    """
    panes = [
        element
        for element in blueprint.elements(Massing)
        if element.note == SEALED_OPENING
    ]
    for pane in panes:
        materials = set()
        for solid in pane.solids:
            materials |= set(solid.material_names)
        if materials and materials <= TOOL_MATERIALS:
            report.add(
                warning(
                    "Z31",
                    f"{pane.id} fills its opening with {sorted(materials)}, which "
                    "the compiler turns into collision with nothing drawn on it: "
                    "in play the hole is solid and empty, which is what a missing "
                    "barricade, a missing pane and a dropped model all look like. "
                    "Name an art material if the fill is meant to be seen",
                    pane.id,
                )
            )

    for door in blueprint.elements(Door):
        for pane in panes:
            if pane.bounds.overlaps(door.box, slack=1e-9):
                report.add(
                    error(
                        "Z7",
                        f"door {door.id} is hung in the opening sealed by "
                        f"{pane.id}; the pane does not move, so the door can "
                        "never open",
                        door.id,
                    )
                )


def _check_windows(blueprint, report: Report) -> None:
    yards = blueprint.elements(Yard)
    for window in blueprint.elements(Window):
        riser = blueprint.find(window.riser_id)
        if riser.link_tag != window.link_tag:
            report.add(
                error(
                    "Z8",
                    f"barricade link tag {window.link_tag!r} does not match its "
                    f"riser's {riser.link_tag!r}",
                    window.id,
                )
            )
        reach = riser.position.distance_to(window.barricade_origin)
        if reach < RISER_REACH_FLOOR:
            report.add(
                error(
                    "Z8",
                    f"the riser stands {reach:.1f} units from its barricade, "
                    f"nearer than {RISER_REACH_FLOOR:g}; the prefab's own "
                    "exterior goal struct is 50 out, so a riser this close is "
                    "standing on top of the thing it walks to",
                    window.id,
                )
            )
        elif reach > RISER_REACH_WARN:
            report.add(
                warning(
                    "Z8",
                    f"the riser stands {reach:.1f} units from its barricade; the "
                    f"farthest shipped pair measured is 487.5, so this is "
                    "unusual rather than wrong -- what matters is that it is in "
                    "the yard, which is checked separately",
                    window.id,
                )
            )
        if window.prefab == BARRICADE_PREFAB_HIDE_DEBRIS:
            report.add(
                error(
                    "Z32",
                    "this window uses the hide-pieces barricade prefab, whose "
                    "only collision is the sill band (x -39..35, z 0..35); the "
                    "plain prefab's full player clip (x -48..50, z 0..113) is "
                    "simply not in that file, and nothing here plugs the hole "
                    "instead, so the opening is one a player walks through "
                    "into the yard",
                    window.id,
                )
            )
        _check_the_barricade_can_be_climbed(blueprint, window, report)
        if not any(
            yard.interior.holds_flat(riser.position.x, riser.position.y)
            for yard in yards
        ):
            report.add(
                error(
                    "Z8",
                    "the barricade's riser is not inside any yard, so it falls into "
                    "the void",
                    window.id,
                )
            )


#: How far out of the wall a barricade's riser may stand.  ``add_window`` puts
#: it at 96, which is this package's default and not a number the game has an
#: opinion about -- spec 4.6 is the single statement of the rule and this pair
#: of constants is the code's copy of it.
#:
#: Pairing every ``riser_location`` struct in
#: ``_prefabs/zm/zm_giant/script/zm_giant_nodes.map`` with the barricade
#: carrying the same ``script_string``, the eight shipped pairs stand 94.7,
#: 104.8, 198.1, 205.1, 257.6, 258.0, 343.9 and 487.5 units out (measured).
#: So there is a floor and no useful ceiling: below the prefab's
#: own ``exterior_goal`` struct at 50 the riser stands on top of the goal it
#: walks to, and that is an error; far out is merely unusual, and is a warning.
#: An earlier reading of the same file gave "93 and 252" and drew a
#: ``(64, 288)`` error band around them, which would have failed five of
#: Treyarch's own eight pairs.
RISER_REACH_FLOOR = 64.0
RISER_REACH_WARN = 512.0


def _check_the_barricade_can_be_climbed(blueprint, window, report: Report) -> None:
    """The opening has to contain the prefab's traversal channel.

    This is a bug no other check can catch: a window can be wired perfectly --
    matching link tags, riser in the yard, barricade at the interior face --
    and no zombie ever comes through, because the hole starts 48 units above
    the floor and the channel they climb through runs from the floor to 40.
    Everything about it compiles and links.  Only play says so, which is
    exactly the kind of thing a check is for.
    """
    from ..blueprint.model import traverse_is_blocked

    room = blueprint.find(window.room_id)
    aperture = room.apertures[window.aperture_index]
    blocked = traverse_is_blocked(aperture.width, aperture.height, aperture.sill)
    if blocked is None:
        return
    report.add(
        error(
            "Z8",
            f"the barricade's opening is {aperture.width:g} x "
            f"{aperture.height:g} at sill {aperture.sill:g} and {blocked}",
            window.id,
        )
    )


def _check_electric_cherry_does_not_shadow_stamin_up(blueprint, report: Report) -> None:
    """Z9: the two cannot share a map, because the stock script collides.

    ``_zm_perk_electric_cherry.gsc`` on the install is the dev stub Treyarch
    left behind, and its ``electric_cherry_perk_machine_setup`` at lines 118
    and 121 sets the spawned machine's ``script_string`` to ``marathon_perk``
    and its ``targetname`` to ``vending_marathon`` -- Stamin-Up's, not its
    own, even though the file defines ``ELECTRIC_CHERRY_RADIANT_MACHINE_NAME``
    as ``vending_electriccherry`` three lines above.  Place both and two
    machines answer to one name; which one any ``GetEnt("vending_marathon")``
    finds is not something the map decides.  Measured.

    The community fix is to edit that shipped script in place (the Modme
    "Setting up perk machines" page has the find-and-replace), which is a
    change to the install and not something a map can carry, so the model
    refuses the pair instead of pretending it works.  What the *in-game*
    symptom is has not been measured.

    This is a guard, not a fix, and it is knowingly one.  The fix a map can
    carry is a perk of our own -- the same ``zm_perks::register_*`` calls from
    the map's own script, with its own price, its own prompt out of the map's
    ``.str`` and its own machine name -- and it is built:
    :mod:`zmforge.script.perks`, checked by ``Z50``.  A map that wants what
    Electric Cherry was going to be writes one instead of placing the stub.
    """
    slugs = {m.perk.slug for m in blueprint.elements(Machine)}
    if {"electric_cherry", "stamin_up"} <= slugs:
        report.add(
            error(
                "Z9",
                "electric_cherry and stamin_up are both placed, and the "
                "install's _zm_perk_electric_cherry.gsc names its machine "
                "'vending_marathon' -- Stamin-Up's name -- so the two "
                "machines collide; place one or the other",
            )
        )


def _check_machines(blueprint, report: Report) -> None:
    modules = set(blueprint.script.module_set())
    _check_machines_stand_on_a_floor(blueprint, report)
    for machine in blueprint.elements(Machine):
        if machine.perk.module and machine.perk.module not in modules:
            report.add(
                error(
                    "Z9",
                    f"{machine.perk.slug} is placed but its module "
                    f"{machine.perk.module} is not in the server script, so the "
                    "machine has no logic",
                    machine.id,
                )
            )
    _check_electric_cherry_does_not_shadow_stamin_up(blueprint, report)
    _check_custom_perks(blueprint, report)
    boxes = blueprint.elements(MysteryBox)
    starting = [b for b in boxes if b.starting]
    if len(starting) > 1:
        report.add(
            error("Z9", f"only one mystery box can be the starting box, found {len(starting)}")
        )
    if starting and blueprint.script.chest_name != starting[0].chest_name:
        report.add(
            error(
                "Z9",
                "the starting box's chest name is not the one the script sets in "
                "level.start_chest_name",
                starting[0].id,
            )
        )


def _check_custom_perks(blueprint, report: Report) -> None:
    """Z50's model half: a perk of the map's own that nothing can buy.

    Two questions the written files answer late and the model answers now.

    *A perk with no machine.*  :meth:`~zmforge.blueprint.model.Blueprint.
    declare_perk` ships the script, the prompt and the precache; only
    :meth:`place_custom_perk` puts a machine in the map.  Declaring without
    placing is a registration the player can never reach -- and it is a real
    thing to want halfway through writing a recipe, which is why it is a
    finding rather than a refusal.

    *A HUD slot a stock perk on this map already owns.*  The two slots the
    shipped widget binds to art the game does not ship are free.  The other
    nine belong to perks with a module, and if the map places that perk, the
    two write the same UI-model path and nothing here decides which lands
    last.  Two perks *of ours* claiming one slot is refused outright at
    declaration; this is the case with a shipped perk on the other side.

    Neither has been seen in game.  See :mod:`zmforge.script.perks`.
    """
    from ..script.perks import BOUND_ICON_SLOTS

    perks = list(getattr(blueprint, "custom_perks", ()))
    if not perks:
        return
    placed = {m.perk.specialty for m in blueprint.elements(Machine)}
    for perk in perks:
        if perk.specialty not in placed:
            report.add(
                error(
                    "Z50",
                    f"this map ships the perk {perk.name} ({perk.specialty}) "
                    "and places no machine for it, so the script registers a "
                    "perk nothing sells: use place_custom_perk, or drop the "
                    "declaration",
                )
            )
        if perk.icon is None:
            continue
        owner = BOUND_ICON_SLOTS.get(perk.icon.key)
        if owner is not None and owner in placed:
            report.add(
                error(
                    "Z50",
                    f"{perk.name} claims the {perk.icon.key} HUD slot and this "
                    f"map also places {owner}, whose own module writes the "
                    "same path; one widget cannot show two perks",
                )
            )


#: How far a machine's origin may sit above the floor under it before the
#: check speaks up.  The pack-a-punch of a test fixture sits 4 units up,
#: so the tolerance has to clear that; a balcony or a rooftop clears it by
#: hundreds.
MACHINE_FLOAT_TOLERANCE = 8.0


def _check_machines_stand_on_a_floor(blueprint, report: Report) -> None:
    """Is each machine on a floor, and can anybody get to it?

    Three answers are worth telling apart, and none of them is an error,
    because all three have been asked for deliberately at least once:

    * no floor under it at all -- almost always a typo, and it costs a build;
    * standing on a surface the map declares unreachable (``reachable=False``
      on the platform) -- a machine visible from the room below with no route
      up, which is a joke or a tease and which the mapper has said out loud;
    * floating above whatever is under it -- a coordinate that has drifted.
    """
    for machine in blueprint.elements(Machine):
        ground = blueprint.ground_under(
            machine.position.x, machine.position.y, below=machine.position.z
        )
        if not ground.found:
            report.add(
                warning(
                    "Z9",
                    f"{machine.perk.slug} stands over no room, yard, terrain or "
                    "platform, so nothing a player can walk on is under it",
                    machine.id,
                )
            )
            continue
        lift = machine.position.z - ground.z
        if not ground.reachable and abs(lift) <= MACHINE_FLOAT_TOLERANCE:
            report.add(
                warning(
                    "Z9",
                    f"{machine.perk.slug} stands on {ground.source}, which this "
                    "map declares has no route onto it; the machine is visible "
                    "and cannot be used",
                    machine.id,
                )
            )
        elif lift > MACHINE_FLOAT_TOLERANCE:
            report.add(
                warning(
                    "Z9",
                    f"{machine.perk.slug} sits {lift:g} units above the walkable "
                    f"surface at z={ground.z:g} ({ground.source}); it is reachable "
                    "only if something not counted as floor carries the player up",
                    machine.id,
                )
            )
        elif lift < -MACHINE_FLOAT_TOLERANCE:
            report.add(
                warning(
                    "Z9",
                    f"{machine.perk.slug} sits {-lift:g} units below the walkable "
                    f"surface at z={ground.z:g} ({ground.source}), so it is buried",
                    machine.id,
                )
            )


#: The box a vending machine needs in front of it: clear of the prefab's own
#: body, one hull wide plus a little, and head high.  **[inherited,
#: unverified]** -- the stock machines carry their own ``zm_collision_perks1``
#: clip (spec 4.7) and nothing here has measured it.  The width is the
#: player's hull plus 4 units a side rather than a generous corridor, because
#: the configuration that played put a machine 24 units off a wall and a
#: wider test would call that broken.
MACHINE_BODY_DEPTH = 24.0
MACHINE_APPROACH_DEPTH = 64.0
MACHINE_APPROACH_WIDTH = 40.0
MACHINE_APPROACH_HEIGHT = 64.0


def _check_machine_clearance(blueprint, report: Report) -> None:
    """Can a player walk up to this machine and use it?

    A machine is bought by standing in front of it, so the space in front of
    it has to be empty and has to have floor.  Both go wrong silently: a
    machine placed by eye against the wrong wall ends up inside the next
    room's geometry, or on the lip of a balcony with its front over the void,
    and neither shows up until somebody walks over to it in game.

    Blocked space is an error -- there is no map in which a machine you cannot
    reach the front of is wanted, except the one this map declares
    unreachable, which is checked separately and not by geometry.  Missing
    floor in front is a warning, because a machine at the edge of a drop is a
    legitimate, if cruel, thing to build.
    """
    from ..solids import inspect_solid

    machines = blueprint.elements(Machine)
    if not machines:
        return
    obstacles = [
        box
        for box in (inspect_solid(solid).bounds() for solid in blueprint.world_solids())
        if box is not None
    ]
    for machine in machines:
        ground = blueprint.ground_under(
            machine.position.x, machine.position.y, below=machine.position.z
        )
        if not ground.found:
            continue  # already reported by the placement check
        box = _approach_box(machine, ground.z)
        blocked = [bounds for bounds in obstacles if bounds.overlaps(box, slack=0.0)]
        if blocked:
            report.add(
                error(
                    "Z9",
                    f"the {MACHINE_APPROACH_DEPTH:g} units in front of "
                    f"{machine.perk.slug} are inside {len(blocked)} solid(s); "
                    "nobody can stand where the machine is used from",
                    machine.id,
                )
            )
        front = box.centre
        standing = blueprint.ground_under(front.x, front.y, below=machine.position.z)
        if not standing.found or abs(standing.z - ground.z) > STEP_TOLERANCE:
            report.add(
                warning(
                    "Z9",
                    f"there is no floor level with {machine.perk.slug} in front of "
                    "it, so it is used from the edge of a drop or not at all",
                    machine.id,
                )
            )


def _approach_box(machine, floor_z: float):
    """The space a player occupies while buying: in front, at head height."""
    facing = machine.facing
    step = facing.step
    across = facing.cross_axis
    near = machine.position + step.scaled(MACHINE_BODY_DEPTH)
    far = machine.position + step.scaled(MACHINE_BODY_DEPTH + MACHINE_APPROACH_DEPTH)
    half = MACHINE_APPROACH_WIDTH / 2.0
    low = Point(
        min(near.x, far.x), min(near.y, far.y), floor_z + 4.0
    )
    high = Point(
        max(near.x, far.x), max(near.y, far.y), floor_z + 4.0 + MACHINE_APPROACH_HEIGHT
    )
    low = low.with_axis(across, low[across.index] - half)
    high = high.with_axis(across, high[across.index] + half)
    return Span.between(low, high)


# An interactive item's origin sits on the floor it stands on, and its own
# measured body starts a little under that origin so the reach rules can put
# two storeys' items in one band (``reach.BASE_SLACK``).  Against *world*
# brushwork that would read the floor slab as a collision on every machine in
# every map, so the body used here starts above the floor instead.
INTERACTIVE_BODY_LIFT = 8.0

# How wide the probe that asks "is there a wall behind this?" is, a side.
# A player hull is 30 units across (:data:`PLAYER_HULL_WIDTH`), so 16 a side
# is one body looking straight back: it must not be as wide as the item
# itself, or the very wall that is cutting across the item's side answers the
# question and the defect exempts itself.
INTERACTIVE_BEHIND_PROBE_HALF_WIDTH = 16.0


def _interactive_body(element, body, *, front: float, back: float, half_width: float):
    """One item's measured box, turned onto its heading and lifted off the floor."""
    origin = Point.of(element.position)
    step = element.facing.step
    across = element.facing.cross_axis
    near = origin + step.scaled(-back)
    far = origin + step.scaled(front)
    low = Point(min(near.x, far.x), min(near.y, far.y), origin.z + INTERACTIVE_BODY_LIFT)
    high = Point(max(near.x, far.x), max(near.y, far.y), origin.z + body.height)
    low = low.with_axis(across, low[across.index] - half_width)
    high = high.with_axis(across, high[across.index] + half_width)
    return Span.between(low, high)


def _check_interactives_have_their_backs_to_the_wall(blueprint, report: Report) -> None:
    """Z9: a machine standing side-on to the wall it is against.

    THE DEFECT.  ``facing`` on a machine, the box and the switch is the
    heading its **front** points at, and the front is the face with the use
    prompt on it, so a machine against a wall faces *away* from that wall.
    Get the heading wrong by a quarter turn and the machine stands broadside
    to the wall with its front aimed along it: its model pokes through the
    brickwork, its prompt is read side-on, and nothing downstream objects.
    ``Z23`` cannot see it -- the yaw emitted is exactly the yaw the authored
    heading asks for, which is the point -- and the other Z9 rows cannot
    either, because the origin is in open air and the 64 units in front of it
    are clear.  For example, a pack-a-punch placed 24 units off a north wall
    facing **west** stands 8 units of its 64-wide body inside that wall.

    WHAT IT ASKS.  Two questions, and only both together are a defect:

    * does world brushwork reach into the item's own body, forward of its
      origin plane -- the half the player looks at and buys from?  The back
      is excluded on purpose: every machine in a finished map has its back
      *in* the wall by a few units, and that is what against-the-wall means.
    * and is there nothing behind it -- no brushwork within
      :data:`~zmforge.blueprint.reach.APRON_DEPTH` straight back from its
      back face?

    An item with a wall behind it is in a nook and its heading is deliberate:
    a pack-a-punch may stand in a 48-unit gap between two piers and clip
    both, its back wall 31 units behind it, and still be perfectly usable.
    An item touching brickwork with nothing
    behind it is the quarter-turn mistake and nothing else.

    The measurements are :mod:`zmforge.blueprint.reach`; the solids are read
    as bounding boxes, the way :func:`_check_machine_clearance` reads them,
    because world brushwork here is walls and piers.
    """
    from ..blueprint import reach
    from ..solids import inspect_solid

    items: list[tuple[object, object, str]] = []
    for machine in blueprint.elements(Machine):
        pap = machine.perk.slug == "pack_a_punch"
        items.append(
            (machine, reach.BODIES["pack_a_punch" if pap else "machine"],
             f"the {machine.perk.slug} machine")
        )
    for box in blueprint.elements(MysteryBox):
        items.append((box, reach.BODIES["mystery_box"], "the mystery box"))
    for switch in blueprint.elements(PowerSwitch):
        items.append((switch, reach.BODIES["power_switch"], "the power switch"))
    if not items:
        return

    obstacles = [
        (solid, bounds)
        for solid, bounds in (
            (solid, inspect_solid(solid).bounds()) for solid in blueprint.world_solids()
        )
        if bounds is not None
    ]
    if not obstacles:
        return

    for element, body, what in items:
        front = _interactive_body(
            element, body, front=body.front, back=0.0, half_width=body.half_width
        )
        intruders = [
            (solid, bounds) for solid, bounds in obstacles if bounds.overlaps(front, slack=0.0)
        ]
        if not intruders:
            continue
        behind = _interactive_body(
            element,
            body,
            front=-body.back,
            back=body.back + reach.APRON_DEPTH,
            half_width=INTERACTIVE_BEHIND_PROBE_HALF_WIDTH,
        )
        if any(bounds.overlaps(behind, slack=0.0) for _, bounds in obstacles):
            continue  # in a nook, with its back to something: deliberate
        solid, bounds = intruders[0]
        origin = Point.of(element.position)
        # Which way the wall lies is read off the *overlap*, not off the
        # solid's own centre: a room wall is one brush the length of the room,
        # and its centre can be half a map away from the machine standing
        # against it.  The overlap is a slab -- the few units of the item that
        # are inside the wall -- so the axis it is thinnest on is the one the
        # wall's face is on, and the item's own depth along its heading is not
        # allowed to outvote it.
        lows = [max(bounds.mins[i], front.mins[i]) for i in range(2)]
        highs = [min(bounds.maxs[i], front.maxs[i]) for i in range(2)]
        thickness = [highs[i] - lows[i] for i in range(2)]
        offset = [(lows[i] + highs[i]) / 2.0 - (origin.x, origin.y)[i] for i in range(2)]
        if thickness[0] != thickness[1]:
            axis = 0 if thickness[0] < thickness[1] else 1
        else:
            axis = 0 if abs(offset[0]) >= abs(offset[1]) else 1
        toward = {
            (0, True): "east", (0, False): "west",
            (1, True): "north", (1, False): "south",
        }[(axis, offset[axis] >= 0.0)]
        away = {"east": "west", "west": "east", "north": "south", "south": "north"}[toward]
        report.add(
            error(
                "Z9",
                f"{what} stands side-on to the brushwork to its {toward} "
                f"({solid.note or 'unlabelled'}): it is authored facing "
                f"{element.facing.value}, which is the heading its front points "
                f"at, so its own body reaches into that wall and its use prompt "
                f"is read along it rather than out of it. Nothing is behind it "
                f"within {reach.APRON_DEPTH:g} units, so this is a quarter turn "
                f"out: face {away} and put its back on that wall",
                element.id,
            )
        )


def _check_interactives_keep_clear(blueprint, report: Report) -> None:
    """Z42: does every interactive item leave every other one usable?

    The same question :meth:`Blueprint._refuse_a_blocked_interactive` refuses
    a placement for, asked again of a finished model.  It is asked twice on
    purpose: the model refuses what this generator's own recipes build, and
    this row covers everything that arrives by another road -- a blueprint
    read back out of the editor, a document the placement methods never saw,
    and any element whose position was moved after it was installed.

    An **error** is an item that cannot be used at all: two bodies drawn
    through each other, a body in front of a wall buy's chalk, or a body
    filling the floor the item is used from.  That is the defect this catches -- a perk machine at
    ``(200, -536)`` standing in front of a wall buy at ``(200, -560)``, both
    on one wall facing the same way, so the buy cannot be pressed.

    A **warning** is crowding: an item that reaches into another's apron and
    still leaves it somewhere to stand.  It does not stop a purchase,
    which is why the rule refuses the
    first kind and only reports the second.

    The measurements and the reasoning are in
    :mod:`zmforge.blueprint.reach`.
    """
    from ..blueprint import reach

    keeps = reach.keeps_of(blueprint.elements())
    for clash in reach.clashes(keeps):
        message = clash.message()
        element_id = clash.first.element_id
        if clash.blocks:
            report.add(error("Z42", message, element_id))
        else:
            report.add(warning("Z42", message, element_id))


def _check_lighting(blueprint, report: Report) -> None:
    lamps = blueprint.elements(Lamp)
    if not lamps:
        report.add(
            error("Z11", "the map has no lights; the sun cannot reach inside a sealed box")
        )
    for room in blueprint.elements(Room):
        if room.sunlit:
            continue  # open to the sky; the sun is its light (Room.sunlit)
        inside = [
            lamp
            for lamp in lamps
            if room.interior.holds(lamp.position, tolerance=-1e-9)
        ]
        if not inside:
            report.add(
                error("Z11", f"room {room.id} has no light inside it", room.id)
            )
        for lamp in inside:
            if lamp.position.z >= room.shell.ceiling_underside_z:
                report.add(
                    error(
                        "Z11",
                        "this light sits in or above the ceiling slab, where it "
                        "illuminates nothing",
                        lamp.id,
                    )
                )
        _check_room_is_covered(blueprint, room, inside, report)
    _check_lamp_intensity(blueprint, lamps, report)


def _check_lamp_intensity(blueprint, lamps, report: Report) -> None:
    """A lamp's brightness has to be in the band the shipped maps use.

    ``stops`` is log2 of an intensity and means nothing except against the
    exposure of the map's own sun/sky preset, so the band is expressed as an
    offset from that exposure.  A map with lamps at ``stops 4`` under
    ``ssi default_day`` (ev 15) plays nearly black: 11 stops, 2048x, under
    the shipped practice.  Every number here is measured --
    see :mod:`zmforge.lighting`.

    Both ends are errors.  Too dark is the bug that prompted the check; too
    bright is the same mistake with the sign flipped and is no more likely
    to be deliberate, since a lamp only ever gets an absolute ``stops`` from
    a caller who typed one.

    The map-wide brightness offset is deliberately **not** part of that test.
    It is the knob someone turns while looking at a bake, and judging it
    against the shipped band would have made half its range unusable -- a
    two-stop trim down reported 128 errors and refused to write the map.  So
    the band judges how each lamp is authored, and the offset gets one
    warning for the whole map when it takes the result outside the band.
    """
    low, high = lighting.SHIPPED_STOPS_OVER_EXPOSURE
    exposure = blueprint.exposure
    trim = blueprint.brightness_stops
    for lamp in lamps:
        authored = blueprint.stops_of(lamp) - trim
        over = authored - exposure
        if low <= over <= high:
            continue
        ratio = 2.0 ** abs(over - (high if over > high else low))
        report.add(
            error(
                "Z11",
                f"this light is at stops {authored:g}, which is {over:+.1f} stops "
                f"against the map's exposure of ev {exposure:g}; the shipped "
                f"maps sit between {low:+g} and {high:+g}, so it is about "
                f"{ratio:.0f}x too "
                f"{'bright' if over > high else 'dark'} to read as lit",
                lamp.id,
            )
        )
    if trim and lamps:
        worst = max(
            blueprint.stops_of(lamp) - exposure for lamp in lamps
        )
        least = min(blueprint.stops_of(lamp) - exposure for lamp in lamps)
        if least < low or worst > high:
            report.add(
                warning(
                    "Z11",
                    f"the map-wide brightness offset of {trim:+g} stops puts the "
                    f"lights {least:+.1f} to {worst:+.1f} against this map's "
                    f"exposure of ev {exposure:g}, outside the {low:+g} to "
                    f"{high:+g} the shipped maps use; that is allowed because it "
                    "is the knob for judging a bake, but it is a trim, not a fix",
                )
            )


def _check_room_is_covered(blueprint, room, inside, report: Report) -> None:
    """A room bigger than one lamp's patch needs more than one lamp.

    Z11 already requires a lamp per room, and a lamp per room gives a
    640 x 768 hall and a 112 x 112 closet alike.  The Giant carries one lamp
    per 226 x 226 units of footprint; a large map lit one lamp per room
    measured one per 521 x 521.  The rule is therefore stated as a
    spacing: no part of a room's floor further than
    :data:`zmforge.lighting.MAX_LAMP_SPACING` from a lamp, in plan.
    :meth:`zmforge.blueprint.model.Blueprint.light_rooms` satisfies it.
    """
    if not inside:
        return  # the missing-lamp error above already says it
    spacing = lighting.MAX_LAMP_SPACING
    interior = room.interior
    for point, cell in blueprint._lamp_grid(interior, interior.centre.z, spacing):
        if any(cell.holds_flat(lamp.position.x, lamp.position.y) for lamp in inside):
            continue
        report.add(
            error(
                "Z11",
                f"room {room.id} is {interior.maxs.x - interior.mins.x:g} x "
                f"{interior.maxs.y - interior.mins.y:g} and has no light within "
                f"{spacing:g} units of ({point.x:g}, {point.y:g}); one lamp does "
                "not light a hall -- call light_rooms()",
                room.id,
            )
        )
        return  # one report per room is enough to act on


#: How far inside a world solid an origin may sit before it counts as buried
#: (spec 2.8 step 8: "error if any world solid contains the point by more than
#: 2 units").  A riser exactly on the floor surface is at depth 0 in the slab.
SOLID_EMBED_TOLERANCE = 2.0

def _check_reflection_probes(blueprint, report: Report) -> None:
    """Z28: every room is inside a reflection probe's box.

    A ``reflection_probe`` carries the bake's indirect solve, not a gloss
    layer: ``bin\\t7.def.json`` files most of its keys under ``2_DIFFUSE_GI``
    and describes ``brightnessAdjust`` as scaling the bounce brightness
    during the bake.  Nothing in the toolchain says so -- ``cod2map64``
    knows the classname and has no zero-probe message -- and that is exactly
    why it wants a check: the failure is a silently flatter map.

    A map that turns probe emission off is a *warning*, not an error, because
    it is a thing a caller can mean; a room that no box encloses is an error,
    because it is the tutorials' demonstrated symptom (a hard brightness step
    at the box boundary) and nothing but this says it.
    """
    enclosures = blueprint.elements(Enclosure)
    if not enclosures:
        return
    if not enclosures[0].probe:
        report.add(
            warning(
                "Z28",
                "this map emits no reflection probe; the mod tools' own new-map "
                "template ships one, so the map starts below a blank one and "
                "its geometry gets no bounced light",
                enclosures[0].id,
            )
        )
        return
    boxes = blueprint.probe_boxes()
    for room in blueprint.elements(Room):
        if not any(box.encloses(room.interior, tolerance=1e-6) for _, box in boxes):
            report.add(
                error(
                    "Z28",
                    f"no reflection probe box encloses room {room.id} on all "
                    "three axes, so its surfaces bake with a brightness step at "
                    "the edge of whatever box does reach them",
                    room.id,
                )
            )


#: How far above an origin the second probe sits: inside the body of whatever
#: stands there (a player is 72 tall, a rising zombie comes up through it) and
#: below anything a floor-standing thing could legitimately have over it.
SOLID_EMBED_PROBE = 8.0


def _check_clear_of_solids(blueprint, report: Report) -> None:
    """Spec 2.8 step 8: nothing the game places may sit inside a world brush.

    ``ground_under`` answers "is there floor below this point" and nothing
    else, so a spawn slot inside a pillar, a riser inside a counter or a lamp
    inside a pier all had floor under them and passed.  Each is silent
    until played: the player is stuck or killed, the zombie never appears,
    the room stays dark.  The test is the half-space one the compiler uses,
    so a wedge or a step reads as its real shape and not as its bounding box.

    Wall buys are left out on purpose: spec 4.10 fixes their origin 8 units
    inside the floor slab, and W1 already says so on every one of them.
    """
    from ..solids.halfspace import plane_through

    solids = [
        (solid, [plane_through(*face.points) for face in solid.faces])
        for solid in blueprint.world_solids()
    ]
    if not solids:
        return

    def buried(point: Point, *, light: bool = False):
        # The origin and a point a little way up the body that stands on it.
        # A riser's origin is *on* the floor, so a pillar standing on that
        # floor around it contains the origin only at its bottom face; the
        # probe above the origin is what sees the pillar.
        for probe in (point, point.with_axis(Axis.Z, point.z + SOLID_EMBED_PROBE)):
            for solid, planes in solids:
                if light and solid.material_names <= {"clip"}:
                    # Clip draws nothing and stops no light: a lamp inside a
                    # camping cap (verify.camping, clip to the ceiling) lights
                    # the room as it would without it (zm_corn_maze's barn).
                    continue
                depth = min(plane.depth_at(probe) for plane in planes)
                if depth > SOLID_EMBED_TOLERANCE:
                    return solid, depth
        return None

    places: list[tuple[str, str, str, Point]] = []
    for start in blueprint.elements(PlayerStart):
        for index, point in enumerate(start.slot_positions(), start=1):
            places.append(
                ("Z1", f"initial spawn slot {index} of {start.slots}", start.id, point)
            )
    for spawn in blueprint.elements(Spawn):
        places.append(("Z6", "this spawn struct", spawn.id, spawn.position))
    for machine in blueprint.elements(Machine):
        places.append(("Z9", f"the {machine.perk.slug} machine", machine.id, machine.position))
    for box in blueprint.elements(MysteryBox):
        places.append(("Z9", "the mystery box", box.id, box.position))
    for switch in blueprint.elements(PowerSwitch):
        places.append(("Z9", "the power switch", switch.id, switch.position))
    for lamp in blueprint.elements(Lamp):
        places.append(("Z11", "this light", lamp.id, lamp.position))

    for code, what, element_id, point in places:
        hit = buried(point, light=code == "Z11")
        if hit is None:
            continue
        solid, depth = hit
        report.add(
            error(
                code,
                f"{what} sits {depth:g} units inside a world solid "
                f"({solid.note or 'unlabelled'}) at ({point.x:g}, {point.y:g}, "
                f"{point.z:g}); the floor under it is not the problem, the "
                "brush around it is",
                element_id,
            )
        )


def _check_enclosure(blueprint, report: Report) -> None:
    enclosures = blueprint.elements(Enclosure)
    if len(enclosures) != 1:
        report.add(
            error(
                "Z11",
                f"a map needs exactly one enclosure (sky shell, sun and umbra "
                f"volumes), found {len(enclosures)}",
            )
        )
        return
    enclosure = blueprint.resolve_enclosure()
    cage = enclosure.cage
    for room in blueprint.elements(Room):
        if not cage.inner.encloses(room.outer):
            report.add(
                error("G7", f"room {room.id} pokes out of the sky shell", room.id)
            )
    for yard in blueprint.elements(Yard):
        if not cage.inner.encloses(yard.outer):
            report.add(
                error("G7", f"yard {yard.id} pokes out of the sky shell", yard.id)
            )


def _check_nothing_to_fall_through(blueprint, report: Report) -> None:
    """Z15: no walkable surface with void under it and no way back.

    A defect no other check knows about: a player can get through the outdoor
    terrain and be stuck underneath, alive,
    with nothing to kill or reset them.  A mesh is a surface, not a volume,
    so a heightfield with nothing beneath it is exactly that void.

    Two things are required, because the shipped maps do both.  The volume
    under a mesh terrain is filled with solid brushes -- ``zm_giant_geo.map``
    line 6008 is one caulk block spanning x -7776..6680, y -10624..8880 down
    to z -288 -- and a map-wide ``trigger_hurt`` slab catches whatever gets
    through anyway.  The emitter guarantees the first per terrain
    (``_terrain_plinth``) and the second from the enclosure
    (``_catch_volume_entity``), so what is checkable on the model is that the
    inputs those need are present.
    """
    from ..blueprint.elements import Terrain

    terrains = blueprint.elements(Terrain)
    if not blueprint.elements(Enclosure):
        if terrains:
            report.add(
                error(
                    "Z15",
                    f"this map has {len(terrains)} terrain(s) and no enclosure, so "
                    "nothing generates the trigger_hurt under it; a player who "
                    "gets through the ground is stuck in the void, alive",
                )
            )
        return  # _check_enclosure already reports the missing enclosure

    enclosure = blueprint.resolve_enclosure()
    cage = enclosure.cage
    for terrain in terrains:
        plan = terrain.record.footprint
        if not cage.inner.holds_flat(plan.mins.x, plan.mins.y) or not cage.inner.holds_flat(
            plan.maxs.x, plan.maxs.y
        ):
            report.add(
                error(
                    "Z15",
                    f"terrain {terrain.id} reaches outside the sky shell, so the "
                    "trigger_hurt under the map does not cover all of it",
                    terrain.id,
                )
            )
        if terrain.style == "mesh" and not terrain.grids:
            report.add(
                error(
                    "Z15",
                    f"terrain {terrain.id} is mesh style with no grids, so it "
                    "emits no surface and no fill under one",
                    terrain.id,
                )
            )
        _check_terrain_meets_the_walls(blueprint, terrain, report)


def _check_terrain_meets_the_walls(blueprint, terrain, report: Report) -> None:
    """Z15: a room's ground reaches every wall of that room.

    A heightfield stepped out as "anchor plus N cells" stops wherever the
    arithmetic runs out, which is not where the wall is.  The strip left over
    has no ground at the terrain's height, so anything placed on the terrain
    there is left standing over the floor slab far below and a player walking
    to the wall drops the same distance.  Measured on a test map:
    a room's mesh stopped 8 units short of one wall and 24 short of the
    other, and 37 props hung 55 to 70 units up.

    Only a terrain that is a room's *ground* is asked this.  A patch laid
    inside a room -- a mound, a verge -- is not touching any wall on purpose,
    and :meth:`~zmforge.blueprint.model.Blueprint.ground_room_of` is what
    tells the two apart.
    """
    record = terrain.record
    if record is None:
        return
    plan = record.footprint
    slack = max(record.x_cell, record.y_cell) + 1e-6
    interior = blueprint.ground_room_of(plan, record.anchor.z, slack)
    if interior is None:
        return
    for name, mine, theirs in (
        ("west", plan.mins.x, interior.mins.x),
        ("east", plan.maxs.x, interior.maxs.x),
        ("south", plan.mins.y, interior.mins.y),
        ("north", plan.maxs.y, interior.maxs.y),
    ):
        if abs(mine - theirs) > 1e-6:
            report.add(
                error(
                    "Z15",
                    f"terrain {terrain.id} stops {abs(mine - theirs):g} units "
                    f"from the {name} wall of the room it is the ground of; "
                    "the strip between them has no ground in it, so anything "
                    "placed on the terrain there stands over the floor below",
                    terrain.id,
                )
            )


def _check_dogs(blueprint, report: Report) -> None:
    spawns = blueprint.elements(Spawn)
    dogs = [s for s in spawns if s.is_dog]
    if blueprint.script.dog_rounds and not dogs:
        report.add(
            error(
                "Z10",
                "dog rounds are on but the map has no dog spawner or dog_location "
                "struct; the dog round cannot complete",
            )
        )
    if dogs and not blueprint.script.dog_rounds:
        report.add(
            warning(
                "Z10",
                "dog spawn structs are placed but level.dog_rounds_allowed is 0, so "
                "they are never used",
            )
        )


def _check_materials(blueprint, report: Report, strict: bool) -> None:
    for name in sorted(blueprint.material_names()):
        if is_catalogued(name):
            continue
        note = (
            f"{name!r} is not in the known-clean catalogue; the compiler will print "
            "a missing-material warning and the surface renders as the error texture"
        )
        if name in BENIGN_MISSING:
            note += " (this one is known to come from a stock prefab and is benign)"
        elif not is_pipeline_material(name):
            # Neither stock-proven nor staged by our own pipeline (wall art,
            # generated surfaces): an error whatever the strictness.
            report.add(error("Z12", note))
            continue
        report.add((error if strict else warning)("Z12", note))


def _check_models(blueprint, report: Report) -> None:
    """Z13: every model the map places must exist on the install, and link.

    The compiler stops on the first map with a ``misc_model`` it cannot find
    (``Missing xmodel '...'`` / ``Missing 1 xmodel!``, no BSP written) and a
    shipped map source is no proof the asset exists -- see
    :mod:`zmforge.blueprint.installed`.  A model can also compile and then
    stop the linker because a LOD or collision file its GDT names is absent
    from the local tools (``xmodels_unlinkable`` in the ledger).  The judgement is made over the
    document the blueprint would emit, so it covers every element that places
    a model or a prefab rather than a list kept by hand.  With no ledger the
    check degrades to one warning; it never invents an answer.
    """
    from ..blueprint.installed import LEDGER_PATH, judge_misc_model, load_ledger
    from ..emit.mapfile import build_document  # local import: emit sits above
    from ..props.notes import model_note

    def instead(model: str, default: str) -> str:
        # The swap a past map made lives in props/notes.json; the verdict
        # itself comes only from the ledger (notes.py derives its own
        # ``local_tools`` from the same ledger, so nothing is kept twice).
        note = model_note(model)
        return f"use {note.use_instead}" if note and note.use_instead else default

    ledger = load_ledger()
    if ledger is None:
        report.add(
            warning(
                "Z13",
                f"no installed-assets ledger at {LEDGER_PATH.name}; model names "
                "were not checked against the install (the ledger ships with "
                "zmforge; scripts/scan-local-tools.py refreshes its link list)",
            )
        )
        return
    try:
        document = build_document(blueprint)
    except Exception as exc:  # the other checks report the underlying defect
        report.add(warning("Z13", f"could not build the document to check its models: {exc}"))
        return
    seen: set[tuple[str, str]] = set()
    for entity in document.entities:
        classname = entity.classname or ""
        model = entity.value("model")
        if not model or (classname, model) in seen:
            continue
        seen.add((classname, model))
        if classname == "misc_prefab" or model.endswith(".map"):
            if not ledger.has_prefab(model):
                report.add(
                    error(
                        "Z13",
                        f"prefab {model!r} is not under map_source/_prefabs on the "
                        f"install ({len(ledger.prefabs)} shipped prefabs, measured "
                        f"{ledger.measured})",
                    )
                )
            continue
        if classname != "misc_model":
            continue  # spawner and barrier models are resolved by the game, not cod2map64
        verdict = judge_misc_model(model, ledger)
        if verdict == "missing":
            report.add(
                error(
                    "Z13",
                    f"misc_model {model!r}: cod2map64 on the install reports "
                    f"\"Missing xmodel\" and writes no BSP (probed {ledger.measured})",
                )
            )
        elif verdict == "unlinkable" and "placeholder image" in ledger.xmodels_unlinkable[model]:
            report.add(
                error(
                    "Z13",
                    f"misc_model {model!r} links but its material "
                    f"{ledger.xmodels_unlinkable[model]}, so it renders magenta "
                    f"with DELETE lettering; {instead(model, 'use another model')}",
                )
            )
        elif verdict == "unlinkable" and "TIFF the linker cannot read" in ledger.xmodels_unlinkable[model]:
            report.add(
                error(
                    "Z13",
                    f"misc_model {model!r} compiles but will not link: "
                    f"{ledger.xmodels_unlinkable[model]} (linker: \"format not supported\", "
                    f"then \"image ... is missing\"; scanned "
                    f"{ledger.local_tools_measured or 'unknown date'}); "
                    f"{instead(model, 'use another model')}",
                )
            )
        elif verdict == "unlinkable":
            report.add(
                error(
                    "Z13",
                    f"misc_model {model!r} compiles but will not link: the local "
                    f"tools lack {ledger.xmodels_unlinkable[model]} under model_export "
                    f"(linker: \"Could not find xmodel file\"; scanned "
                    f"{ledger.local_tools_measured or 'unknown date'}); "
                    f"{instead(model, 'use another model')}",
                )
            )
        elif verdict == "unverified":
            report.add(
                warning(
                    "Z13",
                    f"misc_model {model!r} is declared by no GDT on the install and "
                    "has not been probed; rescan your tools with "
                    "scripts/scan-local-tools.py, or test-compile it before building",
                )
            )


# The stock spawnable-weapon prefab puts its chalk drawing and its weapon
# struct on the plane through its own origin, and its mount brush in the eight
# units *behind* that plane (measured on the install, see
# catalogue.WALL_WEAPON_FRONT_ZERO).  So the wall it is mounted on has to be
# behind the origin, and the room the player buys from has to be in front.
# The back face of the mount brush: eight units behind the origin plane.
WALL_BUY_BEHIND_PROBE = 8.0
# In front of the origin plane the player has to be able to stand; probe
# just past the chalk and again at the depth the mount would have taken.
WALL_BUY_AHEAD_PROBES = (4.0, 8.0)
_WALL_WEAPON_PREFAB_MARK = "spawnable_weapon_"


def _check_wall_buys_can_be_seen(blueprint, report: Report) -> None:
    """W3: a wall buy facing the wrong way cannot show up, and says nothing.

    Read off the *emitted* entity rather than the blueprint, because the way
    this failed was an emitter bug and not a recipe one: ``prefab_yaw`` turned
    the prefab clockwise where ``cod2map64`` turns it counter-clockwise, which
    is right on east and west and 180 degrees out on north and south, so
    every north- or south-facing wall buy comes out backwards.  Nothing
    downstream complains: the prefab expands, the structs land in the BSP with
    unique names, the weapon exists, and in game the chalk drawing faces into
    the brickwork, the mount sticks out into the room and the buy's unitrigger
    origin - which ``_zm_weapons.gsc:962`` offsets sideways from the struct -
    sits inside the wall, so the prompt cannot be reached either.
    """
    from ..solids.halfspace import plane_through
    from ..emit.mapfile import build_document  # local import: emit sits above

    weapons = blueprint.elements(WallWeapon)
    if not weapons:
        return
    try:
        document = build_document(blueprint)
    except Exception as exc:  # the other checks report the underlying defect
        report.add(warning("W3", f"could not build the document to check wall buys: {exc}"))
        return

    solids = [
        (solid, [plane_through(*face.points) for face in solid.faces])
        for solid in blueprint.world_solids()
    ]
    if not solids:
        return

    def solid_at(point: Point):
        for solid, planes in solids:
            depth = min(plane.depth_at(point) for plane in planes)
            if depth > SOLID_EMBED_TOLERANCE:
                return solid
        return None

    by_position = {
        (round(w.position.x, 3), round(w.position.y, 3), round(w.position.z, 3)): w
        for w in weapons
    }
    for entity in document.entities:
        model = entity.value("model") or ""
        if _WALL_WEAPON_PREFAB_MARK not in model:
            continue
        origin = _read_vector(entity.value("origin"))
        angles = _read_vector(entity.value("angles"))
        if origin is None or angles is None:
            continue
        yaw = math.radians(angles[1])
        # The prefab's front is its local +Y, and the compiler turns the
        # prefab counter-clockwise by the yaw.
        front = (-math.sin(yaw), math.cos(yaw))
        here = by_position.get((round(origin[0], 3), round(origin[1], 3), round(origin[2], 3)))
        element_id = here.id if here is not None else None
        facing = f" placed facing {here.facing.value}" if here is not None else ""
        # The chalk sits about 56 units up the prefab from its origin.
        z = origin[2] + 56.0
        behind = Point(
            origin[0] - front[0] * WALL_BUY_BEHIND_PROBE,
            origin[1] - front[1] * WALL_BUY_BEHIND_PROBE,
            z,
        )
        blocker = None
        reach = 0.0
        for reach in WALL_BUY_AHEAD_PROBES:
            blocker = solid_at(
                Point(origin[0] + front[0] * reach, origin[1] + front[1] * reach, z)
            )
            if blocker is not None:
                break
        if blocker is not None:
            report.add(
                error(
                    "W3",
                    f"this wall buy{facing} points into a world solid "
                    f"({blocker.note or 'unlabelled'}): at yaw {angles[1]:g} its "
                    f"front faces ({front[0]:.0f}, {front[1]:.0f}), and "
                    f"{reach:g} units that way is inside brickwork, "
                    "so its chalk drawing and its use prompt are both in the wall",
                    element_id,
                )
            )
            continue
        if solid_at(behind) is None:
            if _inside_imported_geometry(blueprint, behind):
                continue  # an adopted .map's brushes are not in world_solids
            report.add(
                warning(
                    "W3",
                    f"this wall buy{facing} has no wall behind it: at yaw "
                    f"{angles[1]:g} even the back of its mount brush, "
                    f"{WALL_BUY_BEHIND_PROBE:g} units behind it, is in open space, so "
                    "the mount floats",
                    element_id,
                )
            )


def _inside_imported_geometry(blueprint, point: Point) -> bool:
    """Is ``point`` in the footprint of an adopted ``.map``?

    ``world_solids`` is built from blueprint elements and so cannot see the
    brushes inside an :class:`ImportedMap`.  A wall buy mounted on an imported
    room's wall therefore reads as having nothing behind it, which is a hole
    in the probe rather than a defect in the map.
    """
    from ..solids.halfspace import plane_through

    for imported in blueprint.elements(ImportedMap):
        document = imported.document
        if document is None:
            continue
        for entity in getattr(document, "entities", ()):
            for brush in getattr(entity, "solids", ()) or ():
                facets = getattr(brush, "facets", ()) or ()
                if not facets:
                    continue
                planes = [plane_through(*facet.points) for facet in facets]
                if min(plane.depth_at(point) for plane in planes) > -SOLID_EMBED_TOLERANCE:
                    return True
    return False


def _read_vector(text: str | None) -> tuple[float, float, float] | None:
    if not text:
        return None
    parts = text.split()
    if len(parts) != 3:
        return None
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return None


def _check_own_weapons(blueprint, report: Report) -> None:
    """W5 and W6, model side: what the map says about weapons before it writes.

    W5 here is the cheap half of the file-level check: a price for a weapon
    the stock level table does not have cannot be written at all, because a
    re-priced row is the stock row with one column changed and there is no
    stock row to change.  Catching it in the model means the caller hears
    about it before a commit reads the install.

    W6 is a decision, not a defect: a custom weapon with no ``definition``
    is one whose asset somebody registered by hand.  That works -- the probe
    map's own weapon was registered exactly once and stayed registered -- but
    it is not reproducible from the blueprint, so it is said out loud.
    """
    custom = {weapon.name: weapon for weapon in blueprint.custom_weapons}
    assets: dict[str, str] = {}
    for weapon in blueprint.custom_weapons:
        if weapon.asset_name in assets:
            report.add(
                error(
                    "W6",
                    f"{weapon.name!r} and {assets[weapon.asset_name]!r} both "
                    f"declare the weapon asset {weapon.asset_name!r}; the zone "
                    "would carry the line twice and the two rows would fight "
                    "over one asset",
                )
            )
        assets[weapon.asset_name] = weapon.name
        if not weapon.definition:
            report.add(
                warning(
                    "W6",
                    f"the custom weapon {weapon.name!r} names no definition, so "
                    "nothing in this blueprint says where the asset "
                    f"{weapon.asset_name!r} comes from. The zone will declare it "
                    "and the link will fail loudly if the asset database has "
                    "never been told about it",
                )
            )
    for name, cost in sorted(blueprint.weapon_prices.items()):
        if name in custom:
            report.add(
                error(
                    "W5",
                    f"{name!r} is this map's own weapon and its cost is already "
                    f"{custom[name].cost}; a second price of {cost} would be "
                    "written as a second row for one weapon and only the last "
                    "row would ever be read",
                )
            )
        elif name not in LEVEL_WEAPONS:
            report.add(
                error(
                    "W5",
                    f"there is a price for {name!r} and this level has no such "
                    "weapon: it is not a row of the stock table and this map "
                    "declares no custom weapon by that name, so there is no row "
                    "to re-price",
                )
            )


def _check_wall_weapons(blueprint, report: Report) -> None:
    """Flag the wall-buy Z relation the spec records but does not explain.

    Spec 4.10 records, as **[played, not derived]**, that the wall-weapon
    prefab origin sat at ``z = 8`` with the floor surface at 16 -- eight units
    *below* the floor the player walks on.  It is reproduced because that is
    what compiled and played, and reported here because nothing in the spec
    explains why a purchase point belongs inside the floor slab.
    """
    for weapon in blueprint.elements(WallWeapon):
        ground = blueprint.ground_under(
            weapon.position.x,
            weapon.position.y,
            below=weapon.position.z + WALL_WEAPON_DROP,
        )
        if not ground.found:
            report.add(
                warning(
                    "W1",
                    "this wall buy is not over any floor, so its depth below the "
                    "surface cannot be checked",
                    weapon.id,
                )
            )
            continue
        drop = ground.z - weapon.position.z
        if abs(drop - WALL_WEAPON_DROP) < 0.5:
            # The expected case on every map: a note, shown only with -v.
            report.add(
                note(
                    "W1",
                    f"this wall buy sits {drop:g} units below the floor surface at "
                    f"z={ground.z:g}, which is what a built map does and what the "
                    "spec fixes; it is reproduced deliberately and is worth "
                    "re-measuring in game",
                    weapon.id,
                )
            )
        elif drop > 0.5:
            report.add(
                warning(
                    "W1",
                    f"this wall buy sits {drop:g} units below the floor surface",
                    weapon.id,
                )
            )
