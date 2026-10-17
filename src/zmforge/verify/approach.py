"""Z48: can a player actually walk up to the thing and buy it?

THE HOLE THIS CLOSES
--------------------
Two checks already stand between a player and a machine they cannot use, and
between them they leave the obvious gap:

``Z42`` / :mod:`zmforge.blueprint.reach`
    the space immediately in front of an interactive is clear -- no other
    item's body in its stand box, no prop dropped in its apron.  A *local*
    question about one rectangle of floor.
``Z25`` :mod:`~zmforge.verify.reachability`
    the floor an interactive is used from is joined to the spawn, flooding
    **the building**: rooms, thresholds, steps, massing.  Furniture is not in
    that flood at all.

So the map can prove the square in front of the machine is empty, prove the
room it is in is connected, and still hand the player a machine with a wall of
scenery around the empty square.  Scenery standing round a machine does
exactly that: the keep-clear rules do
their job -- the working one's own apron is empty, every doorway lane is
open -- and nothing asks the only question that mattered, which is
whether a player can *get* to the empty square.

This check asks it: for every interactive on the map, is the stand box in
front of it reachable on foot from an initial-spawn slot, **with the dressing
standing in the way**.

Nothing here is a new movement rule.  The flood is
:func:`~zmforge.verify.reachability.flood_from_spawn` with a longer obstacle
list: the same walk, the same 16-unit step, the same 39-unit jump, the same
80-unit leap and the same survivable drop that ``Z25`` uses and that ``Z46``
takes away again for the walkers.  The difference between the ``Z25`` flood
and this one is, exactly, what the furniture did.

WHAT COUNTS AS AN OBSTACLE, AND THE ONE UNCOMFORTABLE PART
----------------------------------------------------------
Every prop, whatever its collision flag says.

That is deliberately stricter than the compiler's own answer and it is worth
being honest about why.  A prop with :attr:`~zmforge.blueprint.elements.Prop.solid`
set bakes a collmap and stops the player; a walk-through prop does not, and a
``script_model`` (:attr:`~zmforge.blueprint.elements.Prop.dynamic`) is not even
looked at by ``cod2map64``.  By that argument a room packed with walk-through
props cannot block anything, and yet it reads as a wall.

**[not separable here]** -- props packed like that wall a machine in for a
player.  Whether they
stop the player's body or only stop them finding the one machine among the
clutter is not something this repo can tell apart without a
build, and it does not change what the map should do: a player is not going to
walk into a solid-looking block of machines to find out whether it is solid.
So a prop is an obstacle here whether or not its collision is baked, and a
room that wants to be full keeps an aisle.

Two things narrow that, and both are rules this package already has.

A prop is only in the way if it **stands on the floor**:
:func:`zmforge.recipes.props.mount_kind`'s own sorting, which is what
``is_solid`` already uses to refuse collision to anything mounted off the
floor.  A duct along a soffit and a light bolted to a wall are walked under.

And it is only in the way if it stands in the player's *body*: the band from
one :data:`~zmforge.verify.reachability.STEP_UP` above the floor to the top of
his hull, which is the same test the world solids get
(:func:`~zmforge.verify.reachability._free_rects`).  A coffee cup, a newspaper
and a floor plate are stepped over and are not obstacles; a chair, a shelf and
a vending machine are.

A BOX FOR EVERY PROP, OR A LINE SAYING THERE IS NOT
----------------------------------------------------
A prop this check cannot measure is a prop it cannot count, and a prop it
cannot count is a hole of exactly the shape that produces the defect.
A perk machine placed as a prop is invisible to every prop-aware rule in the
package for this reason: ``p7_zm_vending_jugg`` and ``p7_zm_vending_ads`` are
in no ``MODEL_BOX`` entry, because that table is measured from the models'
own ``model_export`` sources and the perk machine models have none (they exist
only as built assets inside ``zm_levelcommon``).
:func:`~zmforge.placement.audit.layout_from_blueprint` drops a prop with no
box, on the good argument that an invented footprint is an invented finding,
so a perk machine standing as scenery would be in no audited layout at all.

Three sources of a box, in order: the prop's own
:attr:`~zmforge.blueprint.elements.Prop.collision_box`, which a solid prop
carries because the project writes its collmap from it; the measured table;
and :data:`UNMEASURED_BOX`, which is this module's own short list of models
whose size this repo knows from somewhere other than a model export.  A model
in none of the three is **reported as a warning naming the model and how many
of it there are**, so the blind spot is a line in the report rather than a
silence.

DELIBERATE EXCEPTIONS ARE PRINTED, NOT SKIPPED
-----------------------------------------------
Same rule as ``Z46``, and the same flag: a map is allowed interactives nobody
can reach -- a wall buy behind sealed glass, say.  It is declared by ``reachable=False`` on the room or the massing
it stands on (:func:`~zmforge.verify.reachability._declared_unreachable`), the
declaration is read here rather than re-invented, and every item it covers is
printed as a ``Z48`` warning saying which item and which declaration.  A reader
sees the list of things this map has decided nobody buys, and can disagree.
"""

from __future__ import annotations

import math
from collections import Counter

from ..blueprint.reach import BODIES, keep_of
from ..spatial import Axis, Point, Span
from .model import PLAYER_HULL_WIDTH
from .reachability import (
    JUMP_UP,
    PLAYER_REACH_DOWN,
    STEP_UP,
    TOUCH,
    Flood,
    _declared_unreachable,
    _obstacles,
    _placements,
    _stands_somewhere_declared,
    flood_from_spawn,
)
from ..props.origins import drawn_box
from .report import Report, error, warning
from ..blueprint.elements import PlayerStart, PropScatter

__all__ = [
    "check_interactive_approach",
    "dressed_flood",
    "prop_obstacles",
    "UNMEASURED_BOX",
    "WALK_MARGIN",
]


def _machine_box() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """A perk machine's own box, read off :data:`~zmforge.blueprint.reach.BODIES`.

    The one place in this package that states how big a perk machine is, and
    it states it from the three ``attack_spot`` structs in the stock prefab
    rather than from a model export, which is why it is available for a model
    that has no export.  Local frame, front at -Y, which is the heading every
    perk prefab is measured at (``catalogue.PERK_FRONT_ZERO``).
    """
    body = BODIES["machine"]
    return (
        (-body.half_width, -body.front, 0.0),
        (body.half_width, body.back, body.height),
    )


#: Models this check knows the size of from something other than a measured
#: model export.  Each entry needs a reason, because an invented box is an
#: invented finding: these two are the perk machine models, whose size is
#: :data:`~zmforge.blueprint.reach.BODIES`' own measurement of a perk machine,
#: and they are here because a recipe may place them as *scenery* -- a
#: machine model with no use prompt -- so something has to know how much
#: floor one takes up.
UNMEASURED_BOX: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "p7_zm_vending_jugg": _machine_box(),
    "p7_zm_vending_ads": _machine_box(),
}


#: How far every prop box is grown before the flood sees it: half a player's
#: hull, so that a gap has to be a whole hull wide before the flood squeezes
#: through it.  A player is 30 units across
#: (:data:`~zmforge.verify.model.PLAYER_HULL_WIDTH`) and a 20-unit slot
#: between two crates is not a route, however exactly the geometry says the
#: two boxes do not touch.
WALK_MARGIN = PLAYER_HULL_WIDTH / 2.0

#: How far the top of every prop box is dropped before the flood sees it, so
#: that a prop a player can get **on top of** is not a wall between him and
#: the far side of it.
#:
#: The flood's own obstacle rule is ``_free_rects``': a box blocks if it
#: reaches above :data:`~zmforge.verify.reachability.STEP_UP` over the surface,
#: because a kerb is walked up and a wall is not.  For a *building* that is
#: right -- nothing climbs a world brush.  For furniture it is wrong in the
#: expensive direction: a route built of platforms with props bolted to them
#: is climbed on those props, and counting each piece as a wall reports an
#: item at the top of such a route as unreachable.
#:
#: Dropping every prop's top by the difference between the two heights makes
#: the test read "blocks if it reaches more than
#: :data:`~zmforge.verify.reachability.JUMP_UP` over the surface" without
#: giving ``_free_rects`` a second obstacle list: it is exact, because the only
#: thing either function does with a box's top is compare it with that one
#: number.  What it does **not** do is put the prop's top into the flood as
#: somewhere to stand -- this package has never modelled standing on a prop --
#: so the answer here is permissive about a crate and says so.
CLIMBED = JUMP_UP - STEP_UP


def _model_boxes() -> dict:
    """The measured table, plus this module's own additions.

    Imported inside the function for the reason
    :func:`zmforge.verify.model.check_prop_layout` gives for the same import:
    the palette lives in :mod:`zmforge.recipes.props`, which imports the
    blueprint, which imports this package.
    """
    from ..props.origins import drawn_boxes
    from ..recipes.props import MODEL_BOX

    table = drawn_boxes(MODEL_BOX)
    table.update(UNMEASURED_BOX)
    return table


def _stands_on_the_floor(model: str) -> bool:
    """Is this model something a player walks into, or something he walks past?

    :func:`zmforge.recipes.props.mount_kind` already sorts the palette into
    floor, wall and ceiling, by name family and by the shape of each family's
    own box, and :func:`~zmforge.recipes.props.is_solid` already refuses to
    give collision to anything that is not on the floor -- "a collision box
    hanging in the air at head height is the shape that cuts a navmesh in
    half".  The same rule decides it here, rather than a second opinion that
    could disagree with the placer.

    It matters, and it is measured: without it this check reports a
    pack-a-punch at the end of a tunnel as walled in, by ducts and wall lights
    bolted along the tunnel at z 64 to 97 over a floor at z 16.  They are a
    soffit.  A player walks under
    them, and a check that calls a lit corridor sealed is a check nobody will
    leave switched on.
    """
    from ..recipes.props import MOUNT_FLOOR, mount_kind

    return mount_kind(model) == MOUNT_FLOOR


def prop_obstacles(blueprint, *, solid_only: bool = False) -> tuple[list[Span], Counter]:
    """Every prop in the map as a world-space box, and what could not be boxed.

    The box is the model's own, turned by the prop's yaw and scaled, and then
    the axis-aligned box around *that* -- the same
    ``(dx|cos| + dy|sin|)`` arithmetic the placer uses for a prop's footprint
    at a yaw, and exact for the quarter turns, generous for the rest.  The
    flood is axis aligned and so this has to be; being generous is the safe
    direction for a check that reports a route as shut.

    Every box is then grown by :data:`WALK_MARGIN` on each plan side, which
    is what makes this a question about a *player* rather than about a point.
    The flood links any two rectangles that touch, however narrow the contact
    -- that is deliberate there, because doorway width is ``W2``'s question
    and re-asking it per cell would split a good doorway in two -- but there
    is no ``W2`` for furniture, and without a margin the flood walks a
    16-unit slot between two crates that a 30-unit player cannot enter.  Half
    a hull on each blocker means a gap has to measure a whole hull before the
    flood uses it.  It is the same correction, for the same reason, that
    :data:`zmforge.placement.reachability.WALK_MARGIN` already makes in the
    placer's own flood.

    The second half of the pair is a count per model name of the props no box
    was found for, which the caller turns into warnings.
    """
    table = _model_boxes()
    boxes: list[Span] = []
    missing: Counter = Counter()
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if solid_only and not prop.solid:
                continue
            if not _stands_on_the_floor(prop.model):
                continue
            local = drawn_box(prop.model, prop.collision_box) or table.get(prop.model)
            if local is None:
                missing[prop.model] += 1
                continue
            (x0, y0, z0), (x1, y1, z1) = local
            scale = prop.scale
            angle = math.radians(prop.yaw)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            centre_x = (x0 + x1) / 2.0 * scale
            centre_y = (y0 + y1) / 2.0 * scale
            world_x = prop.origin.x + centre_x * cos_a - centre_y * sin_a
            world_y = prop.origin.y + centre_x * sin_a + centre_y * cos_a
            half_x = ((x1 - x0) * abs(cos_a) + (y1 - y0) * abs(sin_a)) * scale / 2.0
            half_y = ((x1 - x0) * abs(sin_a) + (y1 - y0) * abs(cos_a)) * scale / 2.0
            half_x += WALK_MARGIN
            half_y += WALK_MARGIN
            low = prop.origin.z + z0 * scale
            high = prop.origin.z + z1 * scale - CLIMBED
            if high <= low:
                continue  # nothing of it is above the height a player climbs
            boxes.append(
                Span.between(
                    Point(world_x - half_x, world_y - half_y, low),
                    Point(world_x + half_x, world_y + half_y, high),
                )
            )
    return boxes, missing


def dressed_flood(blueprint, *, solid_only: bool = False) -> tuple[Flood, Counter]:
    """``Z25``'s flood with the furniture in it.

    ``solid_only`` keeps the props that bake a collmap and drops the ones the
    player walks through, which is the *certain* half of the answer; see
    :func:`check_interactive_approach` for why both are run.
    """
    boxes, missing = prop_obstacles(blueprint, solid_only=solid_only)
    return flood_from_spawn(blueprint, _obstacles(blueprint) + boxes), missing


def _reaches(flood: Flood, stand: Span, floor_z: float) -> bool:
    """Is any rectangle the flood reached inside this stand box?

    Plan overlap and a height band, the same band
    :meth:`~zmforge.verify.reachability.Flood.under` uses: the floor a thing is
    used from is at its own height, no further than one step above it and no
    further below it than a player is tall.

    Overlap of any size counts.  **How much** standing room an item has is
    ``Z42``'s question and it is answered against the item's own apron; asking
    it again here, per cell, would report a machine as unreachable because one
    obstacle edge happened to cut its stand box in two.  This check owns one
    word, and the word is *connected*.
    """
    for index in flood.reached:
        cell = flood.cells[index]
        if min(cell.floor.maxs.x, stand.maxs.x) - max(cell.floor.mins.x, stand.mins.x) <= TOUCH:
            continue
        if min(cell.floor.maxs.y, stand.maxs.y) - max(cell.floor.mins.y, stand.mins.y) <= TOUCH:
            continue
        if -STEP_UP <= floor_z - cell.z <= PLAYER_REACH_DOWN:
            return True
    return False


def _bare_flood(blueprint, cache: list) -> Flood:
    """``Z25``'s own flood, built at most once and only if something failed.

    What it is for: a stand box the bare building cannot reach either is not
    the dressing's fault, and the finding says so instead of blaming the
    furniture for a missing staircase.  It is built lazily because on a map
    with nothing wrong it is never needed.
    """
    if not cache:
        cache.append(flood_from_spawn(blueprint))
    return cache[0]


def check_interactive_approach(blueprint) -> Report:
    """Z48 over a blueprint: every interactive, the dressing counted.

    Two floods, and the difference between them is the severity.

    * with **only the props that bake collision** -- the certain half.  A
      stand box this one cannot reach is walled in by something the compiler
      itself puts a collmap on, and that is an **error**.
    * with **every prop on the floor**, collision or not.  A stand box only
      this one cannot reach is walled in by scenery the engine may let the
      player push through, and that is a **warning**: the map reads as sealed
      whether or not it is sealed, and a player does not walk into a block of
      machines to find out.  It is the half this repo cannot settle without a
      build.
    """
    report = Report()
    if not blueprint.elements(PlayerStart):
        return report  # Z1 owns a map with no spawn set
    solid_flood, _ = dressed_flood(blueprint, solid_only=True)
    if not solid_flood.seeds:
        return report  # Z25 already says the spawn slots stand on nothing
    # The models nothing could measure are counted off the *second* flood,
    # which is the one that looks at every prop; the first has already dropped
    # the walk-through ones and would under-report the blind spot.
    every_flood, missing = dressed_flood(blueprint)

    for model, count in sorted(missing.items()):
        report.add(
            warning(
                "Z48",
                f"{count} prop(s) of {model} were not counted as obstacles: no "
                "measured box for the model, in recipes.props.MODEL_BOX or in "
                "verify.approach.UNMEASURED_BOX, and a footprint invented for "
                "it would be a finding invented for it. Anything this model "
                "walls in, this check cannot see",
            )
        )

    declared = _declared_unreachable(blueprint)
    bare: list[Flood] = []
    for element, name, _facing in _placements(blueprint):
        keep = keep_of(element)
        if keep is None or not keep.stands:
            continue
        floor_z = element.position.z
        walled = not any(
            _reaches(solid_flood, stand, floor_z) for stand in keep.stands
        )
        screened = not any(
            _reaches(every_flood, stand, floor_z) for stand in keep.stands
        )
        if not walled and not screened:
            continue
        told = next(
            (
                where
                for stand in keep.stands
                if (
                    where := _stands_somewhere_declared(
                        declared, stand.centre.x, stand.centre.y, floor_z
                    )
                )
                is not None
            ),
            None,
        )
        if told is not None:
            report.add(
                warning(
                    "Z48",
                    f"declared out of reach: nobody can stand in front of "
                    f"{name}, and {told} is declared reachable=False, so this "
                    "is the map's own decision and not a finding",
                    element.id,
                )
            )
            continue
        stand = keep.stands[0]
        spot = stand.centre
        where = f"({spot.x:g}, {spot.y:g}, {floor_z:g})"
        if walled:
            building = any(
                _reaches(_bare_flood(blueprint, bare), box, floor_z)
                for box in keep.stands
            )
            report.add(
                error(
                    "Z48",
                    f"a player cannot walk to the spot {name} is used from"
                    + (
                        ": props with baked collision seal it off. Every route "
                        f"into the {stand.extent(Axis.X):g} by "
                        f"{stand.extent(Axis.Y):g} stand box in front of it is "
                        "closed by something the compiler gives a collmap, and "
                        "the same flood with the props taken out walks straight "
                        "in, so this is furniture and not architecture. Leave "
                        "an aisle to it, or move the props"
                        if building
                        else ". The floor in front of it is not joined to the "
                        "spawn by any walk, step, jump or survivable drop even "
                        "with every prop taken out, so the building is what "
                        "closes it; Z25 owns that half and says where"
                    )
                    + ". A thing nobody can walk to is a thing that does not "
                    "exist, unless the map says otherwise with reachable=False "
                    "on the room or the platform it stands on",
                    element.id,
                    where,
                )
            )
        else:
            # This is an error for the buyables every map is built around --
            # the power switch, a perk,
            # the box and a wall buy -- because the placer now keeps a clear
            # approach lane in front of each (zmforge.blueprint.lanes), so a
            # buyable closed in by scenery is a placement that skipped it.
            speak = error if _is_buyable(element) else warning
            report.add(
                speak(
                    "Z48",
                    f"a player can only reach {name} by pushing through "
                    "scenery: every way into the stand box in front of it is "
                    "closed by props that bake no collision. The engine may "
                    "well let them through -- a walk-through model is the "
                    "whole reason a room can be packed to its walls -- but the "
                    "room reads as sealed, and a player takes a working item "
                    "behind it for unreachable. Leave a visible way in",
                    element.id,
                    where,
                )
            )
    return report


def _is_buyable(element) -> bool:
    """The power switch, a perk machine, a mystery box or a wall buy."""
    from ..blueprint.elements import Machine, MysteryBox, PowerSwitch, WallWeapon

    return isinstance(element, (Machine, MysteryBox, PowerSwitch, WallWeapon))
