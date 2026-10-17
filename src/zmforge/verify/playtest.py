"""Five checks whose requirement was found by playing a map, not by building it.

Each one guards a defect that compiled, linked and loaded, and only showed up
in play.  They live here rather than in :mod:`~zmforge.verify.model` and
:mod:`~zmforge.verify.files` because they cut across both -- one reads the
blueprint, three read the written text -- and because grouping them keeps the
requirements document and the code in one-to-one correspondence.

``Z19``
    a flight of steps that connects to nothing at one end;
``Z20``
    the ``trigger_hurt`` under the map, which no stage can miss and no stage
    reports;
``Z21``
    a prop the compiler was told not to bake collision for;
``Z22``
    a weapon name this level's weapon set does not hold;
``Z23``
    a wall-mounted prefab turned the way ``cod2map64`` does not turn it;
``Z29``
    half of a stock assembly placed as though it were the whole model;
``Z41``
    a model that depicts a way up, which no model in a generated map can be.
"""

from __future__ import annotations

from pathlib import Path

import re
from typing import Iterable

from ..blueprint.catalogue import (
    BARRICADE_EXTERIOR_ZERO,
    ROUTE_WORDS,
    is_route_model,
    route_top,
    LEVEL_WEAPONS,
    MYSTERY_BOX_FRONT_ZERO,
    POWER_SWITCH_FRONT_ZERO,
    POWER_SWITCH_PREFAB,
    UNMEASURED_PREFAB_FRONT_ZERO,
    WALL_WEAPON_WEAPONS,
    prefab_front_zero,
    prefab_yaw,
    wall_weapon_weapon,
)
from ..blueprint.elements import (
    Machine,
    Massing,
    MysteryBox,
    PowerSwitch,
    Prefab,
    PropScatter,
    WallWeapon,
    Window,
)
from ..blueprint.model import STEP_TOLERANCE, _solid_bounds
from ..script.perks import STOCK_BOTTLES
from ..mapsource.document import Document
from ..spatial import Facing
from .report import Report, error, warning

__all__ = [
    "check_blueprint_playtest",
    "check_files_playtest",
    "check_step_flights",
    "check_kill_volume",
    "check_prop_collision",
    "check_weapon_names",
    "check_script_weapon_names",
    "check_prefab_rotation_sense",
    "check_model_assemblies",
    "check_route_props",
]


# --------------------------------------------------------------------------
# Z19: a flight of steps that leads nowhere
# --------------------------------------------------------------------------
def check_step_flights(blueprint) -> Report:
    """Z19: both ends of a flight of steps land next to something walkable.

    A flight is emitted as one solid per step, and nothing in the model ties
    it to the floor below or the deck above.  Get the base height wrong and
    the bottom step is a 200-unit wall; get the count wrong and the top step
    stops under the balcony it was meant to reach.  Both compile, both link,
    and in play the stairs simply do not work.

    The tolerance is the flight's **own** step rise, not a constant.  Spec 2.5
    records 8 as the rise the reference authors used and report as climbable
    and says the engine's real limit is not known; every shipped recipe here
    climbs in 16s.  So this check takes no position on how high a step may
    be -- it asks whether the map is consistent with itself: a flight that
    climbs in 16s and lands 200 units under its target is broken whatever the
    engine's limit turns out to be.

    Adjacency rather than a probe straight ahead.  A probe one step depth past
    the top of the flight reported three of the five flights in
    a test map as disconnected, all three wrongly: stairs turn,
    land sideways, and end on a threshold rather than a floor.  What holds for
    all five is that some other walkable surface is within one step rise
    vertically and within a hull width in plan.
    """
    from .model import PLAYER_HULL_WIDTH, _standing_patches

    report = Report()
    patches = _standing_patches(blueprint)
    for flight in blueprint.elements(Massing):
        if flight.note != "steps" or not flight.walkable or not flight.reachable:
            continue
        boxes = sorted(
            (_solid_bounds(solid) for solid in flight.solids),
            key=lambda box: box.maxs.z,
        )
        if len(boxes) < 2:
            continue  # a single step is a kerb; Z18 and the eye cover it
        tops = [box.maxs.z for box in boxes]
        rise = max(b - a for a, b in zip(tops, tops[1:]))
        reach = max(rise, STEP_TOLERANCE)
        for what, box, where in (
            ("foot", boxes[0], "nothing a player can step onto it from"),
            ("head", boxes[-1], "nothing it leads onto"),
        ):
            if _walkable_beside(box, patches, flight.id, reach, PLAYER_HULL_WIDTH):
                continue
            report.add(
                error(
                    "Z19",
                    f"the {what} of this flight of steps is at z={box.maxs.z:g} "
                    f"and has {where}: no other walkable surface is within "
                    f"{reach:g} units of that height and a hull's width in plan, "
                    "so the flight does not connect",
                    flight.id,
                )
            )
    return report


def _walkable_beside(box, patches, own_id: str, reach: float, slack: float) -> bool:
    """Is some other walkable surface level with ``box`` and next to it?"""
    height = box.maxs.z
    for _label, element_id, patch, patch_z in patches:
        if element_id == own_id:
            continue
        if abs(patch_z - height) > reach:
            continue
        if (
            box.mins.x - slack < patch.maxs.x
            and patch.mins.x - slack < box.maxs.x
            and box.mins.y - slack < patch.maxs.y
            and patch.mins.y - slack < box.maxs.y
        ):
            return True
    return False


# --------------------------------------------------------------------------
# Z20: the floor of last resort
# --------------------------------------------------------------------------
def check_kill_volume(document: Document) -> Report:
    """Z20: a ``trigger_hurt`` under the whole map, with damage in it.

    A player who gets through the world -- a terrain seam, a gap at a wall
    foot, a hole in a floor -- lands inside the sky shell and stays
    there, alive, with nothing to kill or reset them, and the only way out
    is to quit.  The shipped
    answer is engine-side and is a brush: ``trigger_hurt`` appears six times
    across the shipped ``.map`` files, always as a slab with faces of
    material ``trigger`` (spec 3.2).  Nothing in the tool chain mentions it:
    the compile and the link are clean either way.

    Model-level ``Z15`` checks that the *inputs* the emitter needs are there.
    This reads the written map, which is the only place the slab exists, and
    asks three things of it: that it is there, that its damage is a number
    big enough to matter, and that it lies under and around every
    ``player_volume`` -- because a slab that stops short of a zone is a hole
    in the floor of last resort, and one whose top rises into a zone kills
    players who are standing in bounds.
    """
    from .files import _brush_bounds

    report = Report()
    volumes = [
        entity
        for entity in document.entities_of("info_volume")
        if entity.value("script_noteworthy") == "player_volume"
    ]
    catchers = document.entities_of("trigger_hurt")
    if not catchers:
        report.add(
            error(
                "Z20",
                "the map has no trigger_hurt, so a player who gets through the "
                "world is stuck in the void, alive, with nothing to kill or "
                "reset them",
            )
        )
        return report
    for entity in catchers:
        damage = entity.value("dmg")
        if damage is None or not damage.lstrip("-").isdigit() or int(damage) <= 0:
            report.add(
                error(
                    "Z20",
                    f"a trigger_hurt carries dmg {damage!r}; the shipped slabs "
                    "carry 1000 or 10000, and a volume that does no damage "
                    "catches the player and holds them there",
                )
            )
    boxes = [box for box in (_brush_bounds(e) for e in catchers) if box is not None]
    if not boxes:
        report.add(error("Z20", "the trigger_hurt has no brush, so it occupies nothing"))
        return report
    for volume in volumes:
        zone = _brush_bounds(volume)
        if zone is None:
            continue
        name = volume.value("targetname") or "an unnamed zone"
        covering = [
            box
            for box in boxes
            if box.mins.x <= zone.mins.x
            and box.mins.y <= zone.mins.y
            and box.maxs.x >= zone.maxs.x
            and box.maxs.y >= zone.maxs.y
        ]
        if not covering:
            report.add(
                error(
                    "Z20",
                    f"no trigger_hurt covers the footprint of zone {name!r}, so a "
                    "player who falls out of it lands in the void and stays there",
                )
            )
            continue
        above = [box for box in covering if box.maxs.z > zone.mins.z]
        if above:
            report.add(
                error(
                    "Z20",
                    f"a trigger_hurt reaches up to z={max(b.maxs.z for b in above):g} "
                    f"inside zone {name!r}, whose floor is at z={zone.mins.z:g}; it "
                    "would kill a player standing in bounds",
                )
            )
    return report


# --------------------------------------------------------------------------
# Z21: a prop with its collision switched off
# --------------------------------------------------------------------------
#: The two keys ``cod2map64`` reads, from the mod tools' own entity definition
#: (``bin\t7.def.json``): ``use_collmap`` bakes this model's collmap into the
#: static bsp and ``no_collmap`` keeps it out.
_BAKE = "use_collmap"
_SKIP = "no_collmap"


def _scaled_height(entity, box) -> float:
    """How tall a model with bounding *box* stands at the entity's
    ``modelscale``; 0 when the box is unknown."""
    if box is None:
        return 0.0
    height = box[1][2] - box[0][2]
    try:
        return height * float(entity.value("modelscale") or 1.0)
    except ValueError:
        return height


def check_prop_collision(document: Document, *, collmaps: "Path | None" = None) -> Report:
    """Z21: a prop meant to be solid was not baked into the collision.

    Measured on Windows: six props in ``zm_forge_gate``
    linked with ``Collision: false`` and the player walked straight through
    all six.  The same map with ``use_collmap "1"`` on those six keys compiled
    to 97,556 bytes against 95,708 -- 1,848 bytes of static collision -- and
    ``cod2map`` prints the word ``collmap`` zero times in either log, so the
    size delta was the only evidence there was.

    Both directions are worth reporting and they are not the same severity.
    A solid prop with collision skipped is an error: players and bullets pass
    through furniture.  A prop the library declares walk-through that carries
    ``use_collmap`` is a warning, because baked collision on scatter is what
    breaks the navmesh and makes zombies stop at a plant pot, and only the
    library knows which a given prop is meant to be.
    """
    report = Report()
    try:
        from ..props.library import PROPS
    except Exception as exc:  # pragma: no cover - the library has no deps
        report.add(warning("Z21", f"could not read the prop library: {exc}"))
        return report
    from ..props.collision import STOCK_COLLMAPS

    solid_by_name = {prop.name: prop.solid for prop in PROPS}
    from ..recipes.props import MODEL_BOX
    from .reachability import JUMP_UP
    # A prop that asks to be baked and has no collmap to bake is the silent
    # failure this check exists to stop: measured, use_collmap on a
    # model with no share\raw\collmaps entry grew the BSP by 28 bytes, left
    # the navmesh untouched and the player walked straight through it, with
    # nothing in any log to say so.
    unbakeable: dict[str, int] = {}
    for entity in document.entities_of("misc_model"):
        model = entity.value("model")
        if entity.value(_BAKE) == "1" and model:
            known = model in STOCK_COLLMAPS or (
                collmaps is not None and (Path(collmaps) / f"{model}.map").exists()
            )
            if not known:
                unbakeable[model] = unbakeable.get(model, 0) + 1
        if model not in solid_by_name:
            continue  # not one of ours; the map may place any stock model
        bake = entity.value(_BAKE) == "1"
        skip = entity.value(_SKIP) == "1"
        if solid_by_name[model]:
            if skip or not bake:
                report.add(
                    error(
                        "Z21",
                        f"prop {model!r} is meant to be solid but the map "
                        + (
                            f"sets {_SKIP} 1"
                            if skip
                            else f"never sets {_BAKE} 1"
                        )
                        + ", so cod2map bakes no collision for it and players "
                        "and bullets pass through it",
                    )
                )
        elif bake and _scaled_height(entity, MODEL_BOX.get(model)) > JUMP_UP:
            # Walk-through at its own size, which is what the library judges
            # (a 20-unit bear a player hops over), but scaled past a jump it
            # is an obstacle and its collision is the point: a model scaled
            # up that far is placed solid on purpose, as something to climb
            # or to stop at.
            continue
        elif bake:
            report.add(
                warning(
                    "Z21",
                    f"prop {model!r} is meant to be walked through but the map "
                    f"sets {_BAKE} 1; baked collision on scatter is what takes "
                    "the navmesh out and stops zombies at the furniture",
                )
            )
    for model, count in sorted(unbakeable.items()):
        report.add(
            error(
                "Z21",
                f"{count} placement(s) of {model!r} ask for {_BAKE} and no "
                f"collmap named after that model exists, so cod2map64 bakes "
                "nothing, says nothing, and the prop is walk-through",
            )
        )
    return report


# --------------------------------------------------------------------------
# Z22: a weapon this level does not have
# --------------------------------------------------------------------------
_GETWEAPON = re.compile(r'getweapon\(\s*"([^"]*)"\s*\)', re.IGNORECASE)


def check_weapon_names(blueprint) -> Report:
    """Z22, model side: a wall buy whose slug is not a weapon this level has.

    ``getweapon`` answers for a name that does not exist, nothing raises, and
    the feature that asked for it does nothing -- measured on the rigged
    mystery box, which asked for ``shotgun_olympia`` (a Black Ops I/II name,
    in neither ``zm_levelcommon_weapons.csv`` nor any assetlist on the
    install) and behaved like an ordinary box.

    A wall buy is checked through its prefab, not on its slug.  The slug names
    the ``spawnable_weapon_<slug>.map`` file; the weapon is named *inside* it,
    on the buy struct's ``zombie_weapon_upgrade`` key.  All thirteen were read
    off the install and are :data:`WALL_WEAPON_WEAPONS`.  Twelve
    are identical to their slug, which is why looking the slug up directly
    worked for so long; ``bowie`` is not, and warning on it was this check
    calling a working buy broken.

    A slug with no prefab at all is an **error**: the emitter cannot write the
    buy, so nothing downstream can rescue it.
    """
    report = Report()
    for weapon in blueprint.elements(WallWeapon):
        name = wall_weapon_weapon(weapon.slug)
        if name is None:
            report.add(
                error(
                    "Z22",
                    f"the wall buy slug {weapon.slug!r} has no stock "
                    "spawnable_weapon prefab, so there is no buy to place; the "
                    "thirteen that do are "
                    + ", ".join(sorted(WALL_WEAPON_WEAPONS)),
                    weapon.id,
                )
            )
            continue
        if name in LEVEL_WEAPONS:
            continue
        report.add(
            warning(
                "Z22",
                f"the wall buy slug {weapon.slug!r} names the weapon {name!r} "
                "through its prefab, and that is not a row of this level's "
                "weapon table, so the buy hands out nothing and says nothing",
                weapon.id,
            )
        )
    return report


def check_script_weapon_names(
    script: str, *, label: str, also: Iterable[str] = ()
) -> Report:
    """Z22, script side: every ``getweapon`` literal is a weapon this level has.

    The same silent failure as above, one layer down, and here it is an error
    because the script named the weapon itself: nothing else chose it and
    nothing downstream will object.  An empty literal is reported too -- it is
    what a template with an unfilled slot leaves behind.

    ``also`` is the weapons this map adds for itself -- rows of its own weapon
    table, backed by ``weapon`` lines in its zone.  A map that ships a gun may
    name it; a map that does not may not.

    The nine perk bottles are accepted alongside them, and they are not guns:
    they are ``grenadeweapon`` assets on the level-common list
    (``zone_source/all/assetlist/zm_levelcommon.csv:6283-6291``, measured),
    packed into every zombies level whether or not anything
    drinks them.  A perk of the map's own has to name one --
    ``register_perk_basic_info`` asserts the argument and the framework hands
    the weapon over before it grants the perk -- so naming one is correct and
    costs the map nothing.  Without this, every custom perk reported a Z22 for
    doing the one thing it must do.
    """
    report = Report()
    extra = set(also) | set(STOCK_BOTTLES)
    for match in _GETWEAPON.finditer(script):
        name = match.group(1)
        if name in LEVEL_WEAPONS or name in extra:
            continue
        line = script.count("\n", 0, match.start()) + 1
        report.add(
            error(
                "Z22",
                f"{label} line {line}: getweapon(\"{name}\") names a weapon "
                "outside this level's weapon set, so it returns nothing usable "
                "and whatever asked for it silently does nothing",
            )
        )
    return report


# --------------------------------------------------------------------------
# Z23: a prefab turned to face somewhere other than where it was asked to
# --------------------------------------------------------------------------
def check_prefab_rotation_sense(blueprint) -> Report:
    """Z23: a prefab emitted at a yaw that does not put its front on its heading.

    This is the wall-buy defect, generalised, and both halves of it are now
    measured.  ``cod2map64`` turns a prefab **counter-clockwise** by its yaw --
    measured off the compiled ``zm_mymap.d3dbsp`` and recorded on
    :func:`~zmforge.blueprint.catalogue.wall_weapon_yaw` -- and the engine
    turns the entities a map emits directly the same way.  The other half, the
    heading each family's front points at yaw 0, was read off the stock
    prefabs on the install for every family and is recorded
    beside each constant in :mod:`~zmforge.blueprint.catalogue`.  So the yaw a
    prefab should carry is ``(heading - front_at_yaw_zero) mod 360``, and
    anything else is an **error**: the clockwise turn that shipped ten of
    a test map's eleven wall buys aimed into their own walls is one
    way to get it wrong, and reading a perk's front off the pack-a-punch's is
    another.

    Nothing in the chain objects on its own: the prefab expands, the structs
    land in the BSP, the weapon exists.  What the player gets is a machine
    facing a wall, and for the perk family the ``zm_collision_perks1`` clip
    goes with it, so the machine's body blocks the wrong side as well.  The
    use prompts survive it -- ``_zm_perks.gsc:1508`` and
    ``_zm_pack_a_punch.gsc:106`` both spawn a ``trigger_radius_use`` -- which
    is exactly why this went unseen; the mystery box's is a unitrigger offset
    off the box's own front and does not.

    Two things are **not** errors:

    * A :class:`~zmforge.blueprint.elements.Prefab` carrying a raw ``yaw``.
      The caller established that prefab's own zero heading and this
      convention was not consulted.
    * A :class:`~zmforge.blueprint.elements.Prefab` whose model is not in
      :data:`~zmforge.blueprint.catalogue.PREFAB_FRONT_ZERO_BY_MODEL`.  Nobody
      has opened that prefab, the emitter fell back to a guess, and a warning
      says so rather than claiming a defect it cannot prove.

    A wall buy is not reported either: it goes through
    :func:`~zmforge.blueprint.catalogue.wall_weapon_yaw`, and ``W3`` probes
    the geometry in front of it.
    """
    from ..emit.mapfile import build_document  # local import: emit sits above

    report = Report()
    try:
        document = build_document(blueprint)
    except Exception as exc:  # the other checks report the underlying defect
        report.add(
            warning("Z23", f"could not build the document to check prefab facing: {exc}")
        )
        return report

    emitted: dict[tuple[float, float, float], list] = {}
    for entity in document.entities:
        origin = _read_point(entity.value("origin"))
        angles = _read_point(entity.value("angles"))
        if origin is None or angles is None:
            continue
        emitted.setdefault(origin, []).append((entity, angles[1] % 360.0))

    def _at(position, model: str | None, classname: str | None = None):
        """Every emitted entity at ``position`` that this element owns."""
        key = (round(position.x, 3), round(position.y, 3), round(position.z, 3))
        found = []
        for entity, yaw in emitted.get(key, ()):
            if model is not None and (entity.value("model") or "") != model:
                continue
            if classname is not None and entity.classname != classname:
                continue
            found.append((entity, yaw))
        return found

    def _check(element, zero, heading, label, position, model=None, classname=None) -> None:
        wanted = prefab_yaw(heading, zero)
        for entity, yaw in _at(position, model, classname):
            if yaw == wanted % 360.0:
                continue
            report.add(
                error(
                    "Z23",
                    f"this {label} is asked to face {heading.value} and its "
                    f"{entity.classname} is emitted at yaw {yaw:g}; the prefab's "
                    f"front points {zero.value} at yaw 0 and cod2map64 turns a "
                    f"prefab counter-clockwise, so {heading.value} needs yaw "
                    f"{wanted:g}. As emitted it points somewhere else, and "
                    "against a wall that means into the wall: nothing visible "
                    "to walk up to, and its collision on the wrong side",
                    element.id,
                )
            )

    for machine in blueprint.elements(Machine):
        _check(
            machine,
            machine.perk.front_zero,
            machine.facing,
            f"{machine.perk.slug} machine",
            machine.position,
            model=machine.perk.placed_model,
        )
    for box in blueprint.elements(MysteryBox):
        # All three of the box's entities: the stand prefab, the zbarrier that
        # is the box itself, and the chest struct the framework reads.
        _check(box, MYSTERY_BOX_FRONT_ZERO, box.facing, "mystery box", box.position)
    for switch in blueprint.elements(PowerSwitch):
        _check(
            switch,
            POWER_SWITCH_FRONT_ZERO,
            switch.facing,
            "power switch",
            switch.position,
            model=POWER_SWITCH_PREFAB,
        )

    for prefab in blueprint.elements(Prefab):
        if prefab.yaw is not None:
            continue
        zero = prefab_front_zero(prefab.model)
        if zero is None:
            report.add(
                warning(
                    "Z23",
                    f"this prefab is {prefab.model}, which nobody has opened on "
                    "the install, so the heading its front points at yaw 0 is "
                    "unknown; it was emitted for a front of "
                    f"{UNMEASURED_PREFAB_FRONT_ZERO.value} at yaw 0, which is a "
                    "guess, and if that guess is wrong the prefab faces "
                    f"somewhere other than the requested {prefab.facing.value}. "
                    "Read the prefab's own geometry on the install and add it to "
                    "catalogue.PREFAB_FRONT_ZERO_BY_MODEL to settle it",
                    prefab.id,
                )
            )
            continue
        _check(
            prefab,
            zero,
            prefab.facing,
            "scenery prefab",
            prefab.position,
            model=prefab.model,
        )

    for window in blueprint.elements(Window):
        outward = Facing.of(window.side)
        wanted = prefab_yaw(outward, BARRICADE_EXTERIOR_ZERO)
        if window.barricade_yaw % 360.0 != wanted:
            report.add(
                error(
                    "Z23",
                    f"this barricade's exterior should point {outward.value} and "
                    f"it is emitted at yaw {window.barricade_yaw:g}; the prefab's "
                    "exterior points north at yaw 0 and cod2map64 turns it "
                    f"counter-clockwise, so {outward.value} needs yaw {wanted:g}. "
                    "Turned any other way the boards face into the room and the "
                    "riser's goal sits on the wrong side of the wall",
                    window.id,
                )
            )
    return report


# --------------------------------------------------------------------------
# Z29: half of an assembly, placed as if it were the whole thing
# --------------------------------------------------------------------------
def check_model_assemblies(document: Document) -> Report:
    """Z29: a stock model that is one part of an assembly has its other parts.

    ``p7_cai_staircase_01`` is not a staircase.  It is the **frame** of one --
    two stringers, a handrail each side and a glass balustrade -- and the
    treads are eleven separate ``p7_cai_staircase_step_01`` models Treyarch
    places with it (``_prefabs/mp/mp_combine/geo/
    mp_combine_aquaculture_bdg_south/mp_combine_lab_staircase.map``: one frame
    at ``-58 6 40``, eleven treads at ``-58 13 46`` .. ``-58 133 126``).
    A frame placed on its own draws in game as handrails standing in mid air
    with nothing between them.

    Nothing else in the chain can see this, which is why it is a check and not
    a log line.  The model exists and is spelled correctly, ``cod2map64``
    prints no warning for it, the linker packs it -- the map's own
    ``zone_source/all/assetlist/<map>.csv`` carries
    ``xmodel,p7_cai_staircase_01`` with all six of its meshes and both its
    materials -- and every existing check passes, because a decorative prop is
    not a route and no stage compares a model against the company it is
    normally kept in.  The only evidence is Treyarch's own use of the pair,
    which is what :data:`~zmforge.blueprint.catalogue.MODEL_COMPANIONS` holds.

    This reads the written map rather than the blueprint, so it also covers
    props added afterwards by :mod:`zmforge.props.place`.
    """
    from ..blueprint.catalogue import MODEL_COMPANIONS, companion_origins

    report = Report()
    models = document.entities_of("misc_model")
    sited: dict[str, list[tuple[float, float, float]]] = {}
    for entity in models:
        origin = _read_point(entity.value("origin"))
        if origin is not None:
            sited.setdefault(entity.value("model") or "", []).append(origin)

    for entity in models:
        model = entity.value("model") or ""
        if model not in MODEL_COMPANIONS:
            continue
        origin = _read_point(entity.value("origin"))
        if origin is None:
            continue
        angles = _read_point(entity.value("angles")) or (0.0, 0.0, 0.0)
        try:
            scale = float(entity.value("modelscale") or 1.0)
        except ValueError:
            scale = 1.0
        wanted = companion_origins(model, origin, angles[1], scale)
        missing = [
            part
            for part, position in wanted
            if not _model_near(sited.get(part, ()), position)
        ]
        if not missing:
            continue
        report.add(
            error(
                "Z29",
                f"{model} at {entity.value('origin')} is one part of an "
                f"assembly and {len(missing)} of its {len(wanted)} "
                f"{missing[0]} parts are not in the map; the game draws what "
                "is there, so this reads as handrails standing in mid air "
                "with nothing between them, and no stage of the build says a "
                "word about it",
                entity.value(_ASSEMBLY_MARKER) or model,
            )
        )
    return report


#: How far a companion part may sit from where the assembly puts it.  The
#: stock prefabs author these on whole units, and the emitter computes them, so
#: this is rounding slack and not a tolerance anyone should need.
ASSEMBLY_SLACK = 1.0

_ASSEMBLY_MARKER = "zmf_prop"


def _model_near(
    origins: Iterable[tuple[float, float, float]],
    position: tuple[float, float, float],
) -> bool:
    return any(
        all(abs(a - b) <= ASSEMBLY_SLACK for a, b in zip(origin, position))
        for origin in origins
    )


def _read_point(text: str | None) -> tuple[float, float, float] | None:
    """A ``"x y z"`` entity value as three rounded floats."""
    if not text:
        return None
    parts = text.split()
    if len(parts) != 3:
        return None
    try:
        return tuple(round(float(part), 3) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------
def check_blueprint_playtest(blueprint) -> Report:
    """Z19, Z23, Z41 and the model side of Z22."""
    report = Report()
    report.extend(check_step_flights(blueprint))
    report.extend(check_route_props(blueprint))
    report.extend(check_weapon_names(blueprint))
    report.extend(check_prefab_rotation_sense(blueprint))
    return report


def check_files_playtest(
    document: Document,
    script: str,
    *,
    label: str,
    weapons: Iterable[str] = (),
    collmaps: "Path | None" = None,
) -> Report:
    """Z20, Z21, Z29 and the script side of Z22, over the written map and script."""
    report = Report()
    report.extend(check_kill_volume(document))
    report.extend(check_prop_collision(document, collmaps=collmaps))
    report.extend(check_model_assemblies(document))
    report.extend(check_script_weapon_names(script, label=label, also=weapons))
    return report

# --------------------------------------------------------------------------
# Z41: a model that promises a way up, and does not deliver one
# --------------------------------------------------------------------------
def check_route_props(blueprint) -> Report:
    """Z41: a prop that depicts a route leads onto a walkable surface.

    A staircase is not an object.  Every other model a map places is one --
    the player looks at it, walks round it and is done -- but a staircase is
    an **instruction**: whoever sees it reads "that is the way up", walks to
    it, and is owed a floor at the top.  ``Z19`` holds a flight of steps to
    exactly that, and holds it of ``add_steps`` brushwork.  This asks the
    same question of the models, which ``Z19`` cannot see.

    HOW THIS DEFECT ESCAPES EVERY OTHER CHECK.  A themed palette dealt out by
    :class:`~zmforge.recipes.props.Row` places whatever model an index lands
    on at a computed point, so a ``p7_cai_staircase_01`` (109 x 191.5 x 131.5)
    can land anywhere in a room.  In a three-storey hall whose floors are 272
    and 320 units apart, every such staircase delivers a player 86 units up,
    into open air, and no position in that room can bridge either gap.
    ``Z19`` does not see them because they are not massing.  ``Z25`` does not
    see them because a flood reports what
    is **stranded**, and a staircase that goes nowhere strands nobody -- a
    useless piece of map is invisible to a reachability argument by
    construction.  Between them those two rows ask whether the map as a whole
    is traversable; neither asks whether a piece of it does the job it was put
    there to do.

    WHAT IT MEASURES.  The top of the **climb**, not the top of the model: a
    staircase's box includes its handrail and a ladder's includes its stiles,
    so a check that used the box would demand a floor above the handrail.
    :func:`~zmforge.blueprint.catalogue.route_top` reads the highest of the
    model's own part offsets where it has them
    (:data:`~zmforge.blueprint.catalogue.MODEL_COMPANIONS`, which is the
    measured number rather than a typed one) and
    :data:`~zmforge.blueprint.catalogue.ROUTE_TOP` where it does not.  A route
    model with neither is reported too: a climb whose height nobody has
    measured cannot be shown to lead anywhere, and guessing it is the failure
    this check exists to stop.

    The reach and the plan test are ``Z19``'s, deliberately -- a route is a
    route however it is built, and a second standard for models would be a
    second thing to keep true.

    The recipe side is the real fix and this is the backstop.
    :func:`zmforge.recipes.props._model` takes a ``strewn`` flag that
    :class:`~zmforge.recipes.props.Row` and :class:`~zmforge.recipes.props.Fill`
    pass and :class:`~zmforge.recipes.props.One` does not, so a scatter rule
    that lands on a route model steps past it: a map cannot deal a staircase
    out as litter again.  This covers what that cannot -- a hand-written
    :meth:`~zmforge.blueprint.model.Blueprint.place_props` call, a deliberate
    ``One`` placed badly, or another recipe entirely -- and it leaves a
    correctly sited prop staircase alone, which a flat ban would not.

    A name that trips :data:`~zmforge.blueprint.catalogue.ROUTE_WORDS` and is
    genuinely not a route goes in
    :data:`~zmforge.blueprint.catalogue.ROUTE_MODELS` as ``False``, so an
    exception is a judgement written down beside its reason rather than a
    check turned off.
    """
    from .model import PLAYER_HULL_WIDTH, _standing_patches

    report = Report()
    patches = _standing_patches(blueprint)
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if not is_route_model(prop.model):
                continue
            where = (
                f"{prop.model!r} at ({prop.origin.x:g}, {prop.origin.y:g}, "
                f"{prop.origin.z:g})"
            )
            climb = route_top(prop.model, prop.scale)
            if climb is None:
                report.add(
                    error(
                        "Z41",
                        f"{where} depicts a way up and nothing has measured "
                        "how far up it goes, so it cannot be shown to lead "
                        "anywhere.  Put the top of its climb -- the last "
                        "tread or rung, not the top of the model -- in "
                        "catalogue.ROUTE_TOP, or give it its parts in "
                        "MODEL_COMPANIONS.  It is screened as a route on its "
                        f"name ({', '.join(ROUTE_WORDS)}); if it is not one, "
                        "say so in catalogue.ROUTE_MODELS",
                        scatter.id,
                    )
                )
                continue
            head = prop.origin.z + climb
            if _walkable_at(head, prop, patches, PLAYER_HULL_WIDTH):
                continue
            report.add(
                error(
                    "Z41",
                    f"{where} depicts a way up that arrives at z={head:g} "
                    "with nothing to arrive on: no walkable surface is within "
                    f"{STEP_TOLERANCE:g} units of that height and a hull's "
                    "width of it in plan.  A player reads a staircase as an "
                    "instruction and walks to it, so a flight that lands in "
                    "the air is a defect however good it looks.  Build the "
                    "route with add_steps, which Z19 guards, or place a model "
                    "that is an object",
                    scatter.id,
                )
            )
    return report


def _walkable_at(height: float, prop, patches, slack: float) -> bool:
    """Is some walkable surface level with ``height`` and beside ``prop``?

    The prop's footprint is not in the model, so the plan test is the hull
    slack about its origin.  That is generous, and generous is right here:
    this reports a route that lands in *open air*, and a false negative costs
    nothing that ``Z19`` does not already cover for the brushwork beside it.
    """
    for _label, _element_id, patch, patch_z in patches:
        if abs(patch_z - height) > STEP_TOLERANCE:
            continue
        if (
            prop.origin.x - slack < patch.maxs.x
            and patch.mins.x - slack < prop.origin.x + slack
            and prop.origin.y - slack < patch.maxs.y
            and patch.mins.y - slack < prop.origin.y + slack
        ):
            return True
    return False
