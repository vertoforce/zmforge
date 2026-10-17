"""Z25: flood the map from the spawn and see what nobody can get to.

Every other check in this package asks a local question -- is this doorway
wide enough, is this flight connected at both ends, is this floor inside a
zone volume.  A map can answer all of them and still put a perk machine on a
shelf, a room behind a wall with no hole in it, or a staircase that stops one
storey short.  That was ``M4``, the row the requirements document called the
largest hole in the table, and this module is what closed it.

What it does
------------
It takes the same standing surfaces :mod:`~zmforge.verify.model` already
derives for the playable-area sweep (:func:`~zmforge.verify.model._standing_patches`
-- a room floor, a doorway threshold, the top of a walkable massing solid, a
terrain cell), cuts each of them into the rectangles a standing player's body
actually fits in, links the rectangles a player can get between, and floods
from the initial-spawn slots.  Anything the map places that the flood never
reaches, and any room or zone the flood never enters, is an error; a patch of
floor inside a reached room that the flood never reaches is a warning, because
dead floor costs only the lighting.

The rectangle arithmetic is exact rather than sampled, for the same reason the
Z18 sweep is: every box in the model is axis aligned, so over one rectangle of
surface the answer only changes where another box's edge crosses it.  Cutting
on those edges and testing one point inside each cell decides the whole
rectangle, and no grid resolution has to be chosen or defended.

What stops a player, and what does not
--------------------------------------
* **Solid geometry.**  A cell is thrown away when a structural world solid
  stands in the player's own body there -- the same set of solids the
  overlap scan of spec 2.8 step 7 uses, so ``detail`` brushes and caulk-only
  brushes are not obstacles.  A brush whose top is no more than
  :data:`STEP_UP` above the surface is not an obstacle either: a player walks
  up onto a kerb rather than being stopped by it.
* **Height.**  Up to :data:`STEP_UP` is walked, up to :data:`JUMP_UP` is
  jumped, and a drop is taken when it is under :data:`FATAL_DROP`.  A drop is
  a **one-way** link, which is the whole point of a balcony: the flood is
  directed and a place you can fall into but not climb out of is reached, not
  unreachable.
* **Doors.**  A door is an entity, not a world solid, so the hole it hangs in
  is walked through here.  That is deliberate and matches play: a door is
  bought, and a map whose far side is only behind a price is not unreachable.
  A **sealed** opening is the opposite -- ``seal_opening`` writes a real world
  brush (``note`` :data:`~zmforge.blueprint.elements.SEALED_OPENING`) and it
  blocks the threshold here exactly as it blocks the player.
* **A ramp is not a route.**  ``add_wedge`` massing is not walkable -- the
  model cannot answer what is under a point on a sloped top, which is why
  ``ground_under`` refuses to -- so a wedge is an obstacle here and never a
  surface, and it is an obstacle as its own bounding box.  No shipped recipe
  joins two levels with one; a map that did would be reported unreachable and
  the honest fix is to teach the model about slopes, not to soften this.
* **Width is not judged here.**  ``W2`` already errors on a doorway narrower
  than the player's hull and warns on a single-file one, and duplicating that
  test per cell pair would let one obstacle edge landing inside a doorway
  split its contact in two and report a perfectly good map as broken.  So a
  contact of any length links two cells, and how wide a passage is stays
  ``W2``'s question.

Deliberately unreachable
------------------------
Some placements are meant to be out of reach, such as a wall buy behind
sealed glass or a prop on a ledge nobody can climb to.  The model
already carries that declaration -- ``reachable=False`` on a
:class:`~zmforge.blueprint.elements.Room` or a
:class:`~zmforge.blueprint.elements.Massing` -- and this check reads that same
flag rather than adding one of its own.  A surface declared unreachable is not
flooded (``_standing_patches`` already drops it), the room is not reported, and
anything standing on it is passed over in silence.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Iterable, Sequence

from .. import progress
from ..blueprint.elements import (
    Machine,
    Massing,
    MysteryBox,
    PlayerStart,
    PowerSwitch,
    Room,
    WallWeapon,
    Yard,
    Zone,
)
from ..blueprint.model import STEP_TOLERANCE, _solid_bounds
from ..spatial import Axis, Point, Span
from .model import PLAYER_HULL_HEIGHT, PLAYER_HULL_WIDTH
from .report import Report, error, warning

__all__ = [
    "check_reachability",
    "Standing",
    "Flood",
    "flood_from_spawn",
    "STEP_UP",
    "JUMP_UP",
    "GAP_JUMP",
    "FATAL_DROP",
    "HURT_DROP",
]


# --------------------------------------------------------------------------
# How far a player can move vertically
# --------------------------------------------------------------------------
#: How high a ledge a player walks up without jumping.  **[assumption]** --
#: and it is labelled one because nothing on the mod tools install states it.  There is no
#: ``stepSize``-style dvar in the shipped scripts, spec 2.5 records 8 as "the
#: rise the reference authors used and report as climbable [inherited,
#: preference]" while saying the engine's real limit is not documented, and
#: every recipe in this package climbs in 16s.  16 is therefore the largest
#: rise this repo has evidence a player walks up, and it is used as the
#: walk/jump boundary only: because :data:`JUMP_UP` is four times larger and
#: also counts as reachable, this number changes how a link is *described*,
#: not whether the flood crosses it.  Its one substantive use is deciding
#: what counts as an obstacle rather than a kerb.
STEP_UP = 16.0

#: How high a player gets onto by jumping.  **[second-hand, and the best
#: number there is]** -- 39 units, from Treyarch's own ``Scale_Standards.pdf``
#: ("Standing Jump: ~100 units distance, 39 units height") as transcribed by
#: the community, corroborated by ``jump_height "39"`` in the Black Ops I and
#: World at War dvar dumps.  The write-up, every source and how far each one
#: is to be trusted is ``docs/playable-map-requirements.md``, "How high a
#: player can actually get, and why 48 was too high".
#:
#: It is not 64.  That number comes from
#: ``setdvar( "jump_height", 64 );`` at
#: ``scripts/zm/gametypes/_globallogic.gsc:185``, which is **inside an
#: ``if ( level.oldschool )`` block** beside ``player_clipSizeMultiplier 2``:
#: a mode override, not a default, and a grep of all 17 GB of the tools finds
#: that one assignment and nothing else.  Being permissive is not the safe
#: way to be wrong: a 48-unit climb this check passes is not makeable in
#: play.
#:
#: There is no mantle to add to it either.  Mantling in this engine is a
#: property of a **material** -- ``surfaceClimbType`` on ``mantle_on`` and
#: friends -- and there are zero mantle faces in all 22 of Treyarch's own
#: ``map_source/zm/*.map``, so no zombies map has ever shipped one and this
#: generator cannot write one.  The only thing lifting a player here is the
#: raw jump.
JUMP_UP = 39.0

#: How far across a player clears in one jump, take-off and landing level.
#: **[second-hand, deliberately short]** -- the same ``Scale_Standards.pdf``
#: line gives the standing jump ~100 units of distance, and 80 is a fifth
#: under it, which is the same margin the recipes' climbs take against
#: :data:`JUMP_UP`.  The sprint leap, which would give ~220, is **off in
#: zombies**: ``_zm.gsc:216`` is ``SetDvar( "sprintLeap_enabled", 0 )``,
#: beside ``doublejump_enabled 0`` and ``wallrun_enabled 0``, in the
#: ``zm::init()`` every zombies map runs (measured on the mod tools install).
#:
#: Unlike every other number here this one is **not** permissive: a route the
#: flood crosses on it is a route the map asserts a player can leap, so being
#: short makes the check refuse a marginal gap rather than sign one off.
#: :func:`_gap_jump` says what else a gap has to be before it counts.
GAP_JUMP = 80.0

#: The drop the game treats as lethal.  **[stock-source, conditional]** --
#: ``setdvar( "bg_fallDamageMaxHeight", 512 );``,
#: ``scripts/zm/gametypes/_globallogic.gsc:145``, same ``level.oldschool``
#: block and same caveat.  A drop of this or more is not a route.
FATAL_DROP = 512.0

#: Where fall damage starts.  **[stock-source, conditional]** --
#: ``setdvar( "bg_fallDamageMinHeight", 256 );``, line 144 of the same file.
#: Not a gate: a route that costs health is still a route, and a finding says
#: so when a place can only be got to by taking one.
HURT_DROP = 256.0

#: Slack on a shared edge, in units.  Two boxes that abut exactly -- a room
#: interior and the threshold cut in its wall, two rooms' thresholds meeting
#: on the plane their outer boxes share -- overlap by exactly zero, and every
#: coordinate in this package is laid out on a grid, so this only has to
#: absorb floating-point noise.
TOUCH = 1e-6

#: Plan bucket used to avoid comparing every cell with every other one.
_BUCKET = 64.0


# --------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Standing:
    """One rectangle of floor a player's body fits on, and its height."""

    label: str
    element_id: str
    floor: Span
    z: float
    #: A sill is the floor of an opening cut above its room's floor: solid
    #: wall under it, so a player standing on a stair landing walks through
    #: it, but not part of the room below.  See :func:`_raised_sills`.
    sill: bool = False
    #: :attr:`floor`'s plan box as four plain floats, ``(x0, y0, x1, y1)``.
    #: **Derived, never passed** -- it is the same four numbers, kept where
    #: they cost one attribute lookup instead of three.  WHY a cache of
    #: something already here: :func:`_how` and :func:`_gap_jump` are asked of
    #: a million cell pairs on a map with its dressing counted, and reading
    #: ``cell.floor.maxs.x`` eight times a pair was most of the run.
    #: Measured on a test map with its dressing counted:
    #: 8,723 cells and 1.03 million pairs put through those two
    #: functions.
    plan: tuple[float, float, float, float] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan",
            (
                self.floor.mins.x,
                self.floor.mins.y,
                self.floor.maxs.x,
                self.floor.maxs.y,
            ),
        )

    @property
    def centre(self) -> Point:
        spot = self.floor.centre
        return Point(spot.x, spot.y, self.z)


@dataclass(frozen=True, slots=True)
class Flood:
    """Every standing rectangle, and which of them the spawn reaches."""

    cells: tuple[Standing, ...]
    reached: frozenset[int]
    seeds: tuple[int, ...]

    def under(self, x: float, y: float, z: float, *, only_reached: bool):
        """The highest cell a thing at ``(x, y, z)`` could be stood at, if any.

        A thing is used from the floor it is on, so the cell has to be at its
        height: no further than one step above it (a wall buy's origin sits 8
        units *inside* the floor slab, spec 4.10) and no further below it than
        a player is tall.
        """
        best = None
        for index, cell in enumerate(self.cells):
            if only_reached and index not in self.reached:
                continue
            if not cell.floor.holds_flat(x, y, tolerance=TOUCH):
                continue
            if not (-STEP_TOLERANCE <= z - cell.z <= PLAYER_REACH_DOWN):
                continue
            if best is None or cell.z > self.cells[best].z:
                best = index
        return best


#: How far below a placement the floor it is used from may be: a player's own
#: height, so a machine on a balcony is not answered for by the floor beneath.
PLAYER_REACH_DOWN = 72.0


def _obstacles(blueprint) -> list[Span]:
    """Every structural world solid, as a box.

    A ramp is its own bounding box here, which overstates it; the model has no
    free-standing ramp in any shipped recipe and ``ground_under`` cannot answer
    for a sloped top either, so the two limitations are the same one.

    The clip ramp over a flight of steps
    (:data:`~zmforge.blueprint.elements.STAIR_CLIP`) is the one exception.  It
    is not an obstacle: it *is* the stairs, laid over its own treads on
    purpose so the walkers have a plane to climb, and its bounding box is the
    whole flight from the first tread's top to the last tread's.  Counting it
    would carve every tread out of the standing room above it and leave this
    flood calling a working staircase impassable.
    """
    from ..blueprint.elements import STAIR_CLIP

    clips = {
        id(solid)
        for element in blueprint.elements(Massing)
        if element.note == STAIR_CLIP
        for solid in element.solids
    }
    return [
        _solid_bounds(solid)
        for solid in blueprint.world_solids()
        if id(solid) not in clips
    ]


def _free_rects(patch: Span, z: float, obstacles: Sequence[Span]) -> list[Span]:
    """``patch`` cut into the rectangles a player standing at ``z`` fits in.

    Exhaustive, not sampled, by the argument in this module's docstring.  The
    body is the band from one step above the surface -- anything lower is
    walked over -- to the top of the player's hull.
    """
    low = z + STEP_UP
    high = z + PLAYER_HULL_HEIGHT
    blocking = [
        box
        for box in obstacles
        if min(box.maxs.z, high) - max(box.mins.z, low) > 0.0
        and min(box.maxs.x, patch.maxs.x) - max(box.mins.x, patch.mins.x) > 0.0
        and min(box.maxs.y, patch.maxs.y) - max(box.mins.y, patch.mins.y) > 0.0
    ]
    if not blocking:
        return [Span.flat_ok(Point(patch.mins.x, patch.mins.y, z),
                             Point(patch.maxs.x, patch.maxs.y, z))]
    cuts_x = sorted(
        {patch.mins.x, patch.maxs.x}
        | {
            value
            for box in blocking
            for value in (box.mins.x, box.maxs.x)
            if patch.mins.x < value < patch.maxs.x
        }
    )
    cuts_y = sorted(
        {patch.mins.y, patch.maxs.y}
        | {
            value
            for box in blocking
            for value in (box.mins.y, box.maxs.y)
            if patch.mins.y < value < patch.maxs.y
        }
    )
    free: list[Span] = []
    # One band of y at a time, and the free cells **merged along x** as they
    # are walked.  The union is the same either way; what merging saves is the
    # count, and the count is what makes this affordable on a dressed map.  A
    # room with 163 pieces of furniture in it cuts into 326 by 326 cells, and
    # the ones the furniture does not stand on are a handful of runs per band
    # rather than three hundred separate rectangles.  Measured on
    # a test map, with every piece of dressing that
    # had a measured box counted as an obstacle: 378,722 cells unmerged
    # against 8,647 merged, a factor of 44, and the flood over them is
    # quadratic in the cells of one room.
    for y0, y1 in zip(cuts_y, cuts_y[1:]):
        mid_y = (y0 + y1) / 2.0
        band = [
            box
            for box in blocking
            if box.mins.y < mid_y < box.maxs.y
        ]
        run_start: float | None = None
        for x0, x1 in zip(cuts_x, cuts_x[1:]):
            mid_x = (x0 + x1) / 2.0
            shut = any(box.mins.x < mid_x < box.maxs.x for box in band)
            if shut:
                if run_start is not None:
                    free.append(Span.flat_ok(Point(run_start, y0, z), Point(x0, y1, z)))
                    run_start = None
            elif run_start is None:
                run_start = x0
        if run_start is not None:
            free.append(
                Span.flat_ok(Point(run_start, y0, z), Point(cuts_x[-1], y1, z))
            )
    return free


def _raised_sills(blueprint) -> list[tuple[str, str, Span, float]]:
    """The openings ``_standing_patches`` leaves out, which a player still uses.

    That function takes an opening cut more than a step above its room's floor
    to be a window rather than a threshold, which is right for Z18: a player
    is not standing in a window, and counting one as standing room would ask
    the zone volumes to cover it.

    It is wrong for a flood, and it was wrong in the only way that matters.
    Six of the rooms in a test map are reached through a door cut
    at an *upper* floor's height in the wall of a room whose own floor is
    hundreds of units lower, such as a gallery opening down into an
    undercroft.  On the low
    room's side that hole is 'a window' by the rule above, so the map read as
    six unreachable rooms.  The hole is not a window: the wall below the sill
    is solid brush by construction (``room_shell`` cuts the aperture out of
    the wall and leaves the piece underneath), so its floor is a surface, and
    it is the surface a stair landing or a graded slope meets.

    Marked ``sill=True`` so that reaching one is not mistaken for entering the
    room it is cut into.
    """
    out: list[tuple[str, str, Span, float]] = []
    for room in blueprint.elements(Room):
        if not room.reachable:
            continue
        for index, box in enumerate(room.aperture_boxes):
            if box.mins.z <= room.floor_z + STEP_TOLERANCE:
                continue  # _standing_patches already has it
            out.append(
                (f"the sill of {room.id} opening {index}", room.id, box, box.mins.z)
            )
    return out


def standing_cells(
    blueprint, obstacles: Sequence[Span] | None = None
) -> list[Standing]:
    """Every rectangle of floor a player's body fits on, over the whole map.

    ``obstacles`` defaults to :func:`_obstacles`, the structural world solids,
    which is what ``Z25`` and ``Z46`` ask about: whether the *building* lets a
    player through.  ``Z47`` passes a longer list -- the same solids plus
    everything the dressing stood on the floor -- so that one flood can be run
    twice over the same map and the difference between the two answers is,
    exactly, what the furniture did.
    """
    from .model import _standing_patches

    if obstacles is None:
        obstacles = _obstacles(blueprint)
    cells: list[Standing] = []
    sources = [(patch, False) for patch in _standing_patches(blueprint)]
    sources += [(patch, True) for patch in _raised_sills(blueprint)]
    for done, ((label, element_id, patch, z), sill) in enumerate(sources, 1):
        progress.count("measuring floor space", done, len(sources))
        for rect in _free_rects(patch, z, obstacles):
            cells.append(Standing(label, element_id, rect, z, sill))
    return cells


def _how(here: Standing, there: Standing) -> str | None:
    """How a player gets from ``here`` to ``there``, or ``None`` if they cannot.

    Directed: the drop back the other way is a separate question and is asked
    separately.
    """
    hx0, hy0, hx1, hy1 = here.plan
    tx0, ty0, tx1, ty1 = there.plan
    over_x = (hx1 if hx1 < tx1 else tx1) - (hx0 if hx0 > tx0 else tx0)
    over_y = (hy1 if hy1 < ty1 else ty1) - (hy0 if hy0 > ty0 else ty0)
    if over_x < -TOUCH or over_y < -TOUCH:
        return None
    if over_x <= TOUCH and over_y <= TOUCH:
        return None  # a corner is not a way through
    rise = there.z - here.z
    if rise > JUMP_UP:
        return None
    if rise > STEP_UP:
        return "jumped up"
    if rise >= 0.0:
        return "walked"
    drop = -rise
    if drop >= FATAL_DROP:
        return None
    if drop >= HURT_DROP:
        return "dropped, taking fall damage"
    if drop > STEP_UP:
        return "dropped"
    return "walked"


def _gap_jump(
    here: Standing, there: Standing, obstacles: Sequence[Span]
) -> str | None:
    """How a player leaps from ``here`` to ``there`` over a gap, or ``None``.

    :func:`_how` answers for two surfaces that **touch in plan**, which is
    every route a map can build out of steps, slabs and thresholds.  It is not
    every route a map can build: a course of platforms with air between them
    is the ordinary zombies climbing shape, and until this function existed the
    flood called every one of them unreachable content, so a recipe could
    either not build one or assert it in a comment.

    Four things have to be true, and each one is what stops this from being a
    licence to fly:

    * **Level take-off and landing.**  The same height, to within
      :data:`TOUCH`, which is floating-point noise and nothing else -- every
      coordinate in this package is laid out on a grid, so a course that means
      to be level is level.  A jump that also climbs is a different
      measurement and this repo has not got it; a jump that also drops would
      let the flood leave any ledge in any direction, which is exactly the
      freedom that would stop a real defect being reported.
    * **Square on, and only one way.**  The two rectangles are separated on
      one plan axis and overlap on the other.  Diagonal corner-to-corner leaps
      are refused for the same reason :func:`_how` refuses a corner: nobody
      can say what they are worth.
    * **Somewhere to land.**  The overlap across the gap is at least a
      player's own width (:data:`~zmforge.verify.model.PLAYER_HULL_WIDTH`), so
      the landing is a surface rather than an edge to clip.
    * **Nothing in the way.**  A solid standing in the gap, or on either lip,
      whose top is more than a step above the two surfaces is a wall between
      them: the player hits it rather than clearing it.  Anything lower is
      jumped over.

    And the gap itself is at most :data:`GAP_JUMP`, which is short on purpose.
    """
    if abs(there.z - here.z) > TOUCH:
        return None  # level means level: see the docstring
    hx0, hy0, hx1, hy1 = here.plan
    tx0, ty0, tx1, ty1 = there.plan
    over_x = (hx1 if hx1 < tx1 else tx1) - (hx0 if hx0 > tx0 else tx0)
    over_y = (hy1 if hy1 < ty1 else ty1) - (hy0 if hy0 > ty0 else ty0)
    if over_x < -GAP_JUMP or over_y < -GAP_JUMP:
        return None  # too far apart on an axis for any leap this short
    if over_x > TOUCH and over_y > TOUCH:
        return None  # they overlap: _how owns this pair
    if over_x <= TOUCH and over_y <= TOUCH:
        return None  # apart on both axes, which is a diagonal leap
    if over_x > TOUCH:
        gap, span = -over_y, Axis.X
    else:
        gap, span = -over_x, Axis.Y
    if not 0.0 < gap <= GAP_JUMP:
        return None
    if (over_x if span is Axis.X else over_y) < PLAYER_HULL_WIDTH:
        return None
    lane = _lane_between(here, there)
    low = max(here.z, there.z) + STEP_UP
    high = max(here.z, there.z) + PLAYER_HULL_HEIGHT
    for box in obstacles:
        if box.maxs.z <= low or box.mins.z >= high:
            continue
        if min(box.maxs.x, lane.maxs.x) - max(box.mins.x, lane.mins.x) <= TOUCH:
            continue
        if min(box.maxs.y, lane.maxs.y) - max(box.mins.y, lane.mins.y) <= TOUCH:
            continue
        return None
    return f"jumped {gap:g} units across"


def _lane_between(here: Standing, there: Standing) -> Span:
    """The strip of air a leap from ``here`` to ``there`` passes through.

    The two surfaces' shared width on the axis they overlap on, and lip to lip
    on the axis they are apart on, so that a solid standing on either edge
    counts as being in the way and not only one standing in the void.

    One expression does both: on an axis the rectangles overlap on, the larger
    of the two minima is below the smaller of the two maxima and the pair is
    the overlap; on an axis they are apart on, the order flips and the pair is
    the gap.
    """
    corners = []
    for near, far in (
        ((here.floor.mins.x, here.floor.maxs.x), (there.floor.mins.x, there.floor.maxs.x)),
        ((here.floor.mins.y, here.floor.maxs.y), (there.floor.mins.y, there.floor.maxs.y)),
    ):
        inner = max(near[0], far[0])
        outer = min(near[1], far[1])
        corners.append((min(inner, outer), max(inner, outer)))
    (x0, x1), (y0, y1) = corners
    return Span.flat_ok(Point(x0, y0, 0.0), Point(x1, y1, 0.0))


def _buckets(cell: Standing, *, reach: float = 0.0) -> Iterable[tuple[int, int]]:
    """Which plan buckets a cell sits in, optionally grown by ``reach``.

    Indexing is done with ``reach`` of zero, so every cell lands in the
    buckets it actually covers; looking up is done with :data:`GAP_JUMP`, so a
    platform whose neighbour across the gap falls in the next bucket along is
    still compared with it.  Without that the gap link would work or not work
    depending on where a course happened to sit relative to a 512-unit grid.
    """
    box = cell.floor
    for gx in range(
        math.floor((box.mins.x - TOUCH - reach) / _BUCKET),
        math.floor((box.maxs.x + TOUCH + reach) / _BUCKET) + 1,
    ):
        for gy in range(
            math.floor((box.mins.y - TOUCH - reach) / _BUCKET),
            math.floor((box.maxs.y + TOUCH + reach) / _BUCKET) + 1,
        ):
            yield gx, gy


def _seed_cells(
    blueprint, cells: Sequence[Standing], points: Sequence[Point] | None = None
) -> list[int]:
    """The cells the initial-spawn slots stand on, and the points a script
    puts players at (:class:`~zmforge.blueprint.script_plan.ScriptEntry`).

    ``points`` replaces both with exactly those points, for a caller asking
    what one place alone leads to."""
    if points is None:
        points = [p for start in blueprint.elements(PlayerStart) for p in start.slot_positions()]
        points += [Point(*p) for entry in blueprint.script.entries for p in entry.points]
    seeds: list[int] = []
    for point in points:
        best = None
        for index, cell in enumerate(cells):
            if not cell.floor.holds_flat(point.x, point.y, tolerance=TOUCH):
                continue
            if cell.z > point.z + STEP_TOLERANCE:
                continue
            if best is None or cell.z > cells[best].z:
                best = index
        if best is not None and best not in seeds:
            seeds.append(best)
    return seeds


def flood_from_spawn(
    blueprint, obstacles: Sequence[Span] | None = None,
    *, points: Sequence[Point] | None = None,
) -> Flood:
    """Which standing rectangles a player can get to on foot from the spawn.

    Two kinds of link: :func:`_how` for two surfaces that touch, and
    :func:`_gap_jump` for two level surfaces with at most :data:`GAP_JUMP` of
    air between them.  The gap link is asked second and only when the first
    said no, so nothing a map builds out of steps and slabs changes meaning.

    ``obstacles`` is what stands in the player's body; see
    :func:`standing_cells`.  It is used twice here -- to cut the standing
    room, and as the thing a gap jump may not pass through -- so a caller that
    adds the furniture to it gets both.

    ``points`` floods from those points alone instead of from the spawn
    slots and the script entries: what can a player standing there walk to.
    """
    if obstacles is None:
        obstacles = _obstacles(blueprint)
    cells = standing_cells(blueprint, obstacles)
    grid: dict[tuple[int, int], set[int]] = {}
    for index, cell in enumerate(cells):
        for key in _buckets(cell):
            grid.setdefault(key, set()).add(index)

    seeds = _seed_cells(blueprint, cells, points)
    reached = set(seeds)

    def take(index: int) -> None:
        """Reach a cell, and take it out of the buckets it sits in.

        A cell already reached is never a target again -- the link test is
        directed and every caller of it skips a reached cell -- so dropping it
        from the index costs nothing and stops every later cell in a crowded
        room scanning past it.  It matters because one dressed room's bucket
        holds thousands of cells, and without this every one of them is
        compared with every other one for as long as the flood runs.
        """
        reached.add(index)
        for key in _buckets(cells[index]):
            bucket = grid.get(key)
            if bucket is not None:
                bucket.discard(index)

    for index in seeds:
        take(index)
    queue = deque(seeds)
    while queue:
        index = queue.popleft()
        here = cells[index]
        nearby: set[int] = set()
        for key in _buckets(here, reach=GAP_JUMP):
            nearby.update(grid.get(key, ()))
        for other in nearby:
            if other in reached:
                continue
            if (
                _how(here, cells[other]) is None
                and _gap_jump(here, cells[other], obstacles) is None
            ):
                continue
            take(other)
            queue.append(other)
    return Flood(tuple(cells), frozenset(reached), tuple(seeds))


# --------------------------------------------------------------------------
# Declared unreachable: the flag the map already carries
# --------------------------------------------------------------------------
def _declared_unreachable(blueprint) -> list[tuple[str, str, Span, float]]:
    """The surfaces this map has said out loud nobody gets onto.

    The mirror image of ``_standing_patches``'s two ``continue`` lines, read
    off the same ``reachable`` flag: a room nobody enters and a massing with
    no route onto it.  Kept here rather than as a second flag so that a recipe
    declares a deliberate tease once, on the geometry, and every check that
    asks "can a player be here?" gets the same answer.
    """
    out: list[tuple[str, str, Span, float]] = []
    for room in blueprint.elements(Room):
        if room.reachable:
            continue
        out.append((f"room {room.id}", room.id, room.interior, room.floor_z))
        for box in room.aperture_boxes:
            out.append((f"room {room.id}", room.id, box, box.mins.z))
    for massing in blueprint.elements(Massing):
        if massing.reachable:
            continue
        for solid in massing.solids:
            box = _solid_bounds(solid)
            out.append((f"{massing.id}", massing.id, box, box.maxs.z))
    return out


def _stands_somewhere_declared(
    declared: Sequence[tuple[str, str, Span, float]], x: float, y: float, z: float
) -> str | None:
    for label, _element_id, box, surface in declared:
        if not box.holds_flat(x, y, tolerance=TOUCH):
            continue
        if -STEP_TOLERANCE <= z - surface <= PLAYER_REACH_DOWN:
            return label
    return None


# --------------------------------------------------------------------------
# What the map places, and where it is used from
# --------------------------------------------------------------------------
#: How far in front of a thing a player stands to use it, in the order tried.
#: Zero first, because a machine's own origin is on the floor it is used from;
#: the offsets are for a wall buy, whose origin is inside the wall.
USE_OFFSETS = (0.0, 24.0, 48.0)


def _placements(blueprint):
    """Everything a player has to reach, with the name a finding should use."""
    for machine in blueprint.elements(Machine):
        yield machine, machine.perk.slug, machine.facing
    for box in blueprint.elements(MysteryBox):
        yield box, "the mystery box", box.facing
    for switch in blueprint.elements(PowerSwitch):
        yield switch, "the power switch", switch.facing
    for buy in blueprint.elements(WallWeapon):
        yield buy, f"the {buy.slug} wall buy", buy.facing


def _use_spots(element, facing) -> list[Point]:
    step = facing.step
    return [element.position + step.scaled(offset) for offset in USE_OFFSETS]


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------
def check_reachability(blueprint) -> Report:
    """Z25: can a player walk from the spawn to everything the map placed?

    Three findings come out of it, in the order they matter:

    * a machine, box, switch or wall buy the flood never reaches, which the
      map has not declared unreachable -- money spent on content nobody sees;
    * a room the flood never enters, which is the stairs-that-stop-short and
      the room-with-no-door, the two defects that were found by eye;
    * a zone the flood never enters, which is worse than a room: an inactive
      zone contributes no spawns, so even the zombies do not go there.

    And one warning: a patch of floor inside a room the player does get into
    that the player cannot get to, which is the same defect one wall in.  It
    is a warning rather than an error because dead floor costs nothing but the
    lighting, and it only counts a patch a player's own footprint fits in, so
    the gap between a pillar and the wall behind it is not reported as a
    place.
    """
    report = Report()
    starts = blueprint.elements(PlayerStart)
    if not starts:
        return report  # Z1 reports a map with no spawn set; there is nothing to flood from
    flood = flood_from_spawn(blueprint)
    if not flood.seeds:
        report.add(
            warning(
                "Z25",
                "no initial-spawn slot stands on a surface this check can flood "
                "from, so nothing below it could be checked for reachability; "
                "Z1 says whether the slots are over floor at all",
                starts[0].id,
            )
        )
        return report

    declared = _declared_unreachable(blueprint)
    _check_placements(blueprint, flood, declared, report)
    _check_rooms(blueprint, flood, report)
    _check_zones(blueprint, flood, report)
    from .respawn_points import check_respawn_reach

    check_respawn_reach(blueprint, flood, report)  # Z86
    from .gamble import check_gamble_reach

    check_gamble_reach(blueprint, flood, report)  # Z87
    _check_stranded_floor(flood, report)
    _check_volumes_over_unreachable_ground(blueprint, report)
    return report


def _check_placements(blueprint, flood: Flood, declared, report: Report) -> None:
    for element, name, facing in _placements(blueprint):
        spots = _use_spots(element, facing)
        if any(
            flood.under(spot.x, spot.y, element.position.z, only_reached=True)
            is not None
            for spot in spots
        ):
            continue
        told = next(
            (
                where
                for spot in spots
                if (
                    where := _stands_somewhere_declared(
                        declared, spot.x, spot.y, element.position.z
                    )
                )
                is not None
            ),
            None,
        )
        if told is not None:
            continue  # the map said so: a tease, not a defect
        standing = any(
            flood.under(spot.x, spot.y, element.position.z, only_reached=False)
            is not None
            for spot in spots
        )
        position = (
            f"({element.position.x:g}, {element.position.y:g}, "
            f"{element.position.z:g})"
        )
        report.add(
            error(
                "Z25",
                f"no player can reach {name}: "
                + (
                    "the floor it is used from is not connected to the spawn by "
                    "any walk, step, jump or survivable drop"
                    if standing
                    else "there is no standing room in front of it at all"
                )
                + ". A place nobody can get to is a mistake unless the map says "
                "otherwise, which it does with reachable=False on the room or "
                "the platform it stands on",
                element.id,
                position,
            )
        )


def _check_rooms(blueprint, flood: Flood, report: Report) -> None:
    entered = {
        flood.cells[index].element_id
        for index in flood.reached
        if not flood.cells[index].sill
    }
    for room in blueprint.elements(Room):
        if not room.reachable:
            continue  # declared: a room to be seen into, never stood in
        if room.id in entered:
            continue
        mine = [
            cell
            for cell in flood.cells
            if cell.element_id == room.id and not cell.sill
        ]
        if not mine:
            continue  # no standing room in it at all; W2 and Z18 own that
        spot = room.interior.centre
        report.add(
            error(
                "Z25",
                f"room {room.id} has no route into it: its floor at "
                f"z={room.floor_z:g} is not connected to the spawn by any walk, "
                f"step, jump of up to {JUMP_UP:g} units or drop of under "
                f"{FATAL_DROP:g}. Either an opening is missing, a flight of "
                "steps stops short of it, or it is meant to be looked into and "
                "wants reachable=False",
                room.id,
                f"({spot.x:g}, {spot.y:g}, {room.floor_z:g})",
            )
        )


def _check_zones(blueprint, flood: Flood, report: Report) -> None:
    for zone in blueprint.elements(Zone):
        if zone.bounds is None:
            continue
        if any(
            _inside(zone.bounds, flood.cells[index]) for index in flood.reached
        ):
            continue
        if not any(_inside(zone.bounds, cell) for cell in flood.cells):
            continue  # nothing stands in it; Z18 and Z3 own an empty volume
        report.add(
            error(
                "Z25",
                f"zone {zone.name!r} has standing room in it and no route to it "
                "from the spawn, so it never becomes the occupied zone: nothing "
                "spawns there and nothing there counts as played",
                zone.id,
            )
        )


def _check_stranded_floor(flood: Flood, report: Report) -> None:
    """Floor a player could stand on, in a room they can get into, and cannot reach.

    The maze case: a room divided by partitions can have a 224 by 272 pocket
    walled off on both open sides, lit by two lamps and enterable from
    nowhere.  The room around it is reached, so the room check is silent, and
    the pocket is inside the room's zone volume, so Z18 is silent too.

    Reported the way Z18 reports its own gaps -- total square units per
    surface, and the centre of the largest piece -- because it is the same
    question asked from the other side, and a reader who has read one line
    can read the other.

    Only a patch the player's own footprint fits in counts.  A rectangle
    narrower than the hull on either axis cannot hold a player whether a route
    leads to it or not, so the sliver behind a pillar is not a place nobody
    can get to, it is not a place.
    """
    reached_ground = {
        (
            flood.cells[index].element_id,
            flood.cells[index].floor.mins.x,
            flood.cells[index].floor.mins.y,
            flood.cells[index].floor.maxs.x,
            flood.cells[index].floor.maxs.y,
        )
        for index in flood.reached
    }
    worst: dict[tuple[str, str], tuple[float, Span]] = {}
    for index, cell in enumerate(flood.cells):
        if index in flood.reached or cell.sill:
            continue
        if (
            cell.floor.extent(Axis.X) < PLAYER_HULL_WIDTH
            or cell.floor.extent(Axis.Y) < PLAYER_HULL_WIDTH
        ):
            continue
        if (
            cell.element_id,
            cell.floor.mins.x,
            cell.floor.mins.y,
            cell.floor.maxs.x,
            cell.floor.maxs.y,
        ) in reached_ground:
            continue  # the same ground, reached at another of its sampled heights
        area = cell.floor.extent(Axis.X) * cell.floor.extent(Axis.Y)
        total, biggest = worst.get((cell.label, cell.element_id), (0.0, cell.floor))
        if area > biggest.extent(Axis.X) * biggest.extent(Axis.Y):
            biggest = cell.floor
        worst[(cell.label, cell.element_id)] = (total + area, biggest)
    for (label, element_id), (area, biggest) in sorted(
        worst.items(), key=lambda item: -item[1][0]
    ):
        spot = biggest.centre
        report.add(
            warning(
                "Z25",
                f"{label} has {area:.0f} square units of standing room with no "
                f"route to it, the largest piece around ({spot.x:g}, {spot.y:g}); "
                "the room around it is reached, so this is floor walled off "
                "one wall in: a partition that closed a pocket, or a step that "
                "was never built",
                element_id,
            )
        )


#: Ground smaller than this inside a volume is not worth a finding.  A zone
#: volume is sized to a room's *outer* box (walls included, so that the
#: doorway band between two rooms belongs to one of them), which routinely
#: puts a few hundred square units of wall footprint and threshold overhang
#: inside it.  This is the area at which a piece of unreachable ground stops
#: being that and starts being somewhere a zombie can be killed: one player
#: hull square, 900 units.
Z40_MIN_AREA = PLAYER_HULL_WIDTH * PLAYER_HULL_WIDTH


def _plan_intersection(a: Span, b: Span, z: float) -> Span | None:
    """The rectangle two boxes share in plan, or ``None`` if they share none."""
    x0, x1 = max(a.mins.x, b.mins.x), min(a.maxs.x, b.maxs.x)
    y0, y1 = max(a.mins.y, b.mins.y), min(a.maxs.y, b.maxs.y)
    if x1 - x0 <= TOUCH or y1 - y0 <= TOUCH:
        return None
    return Span.flat_ok(Point(x0, y0, z), Point(x1, y1, z))


def _zombie_ground_no_player_reaches(blueprint):
    """Ground a zombie can be killed on and a player cannot walk to.

    One kind, and it is deliberately the only one: **a yard**, the pocket
    outside a barricade window where the risers stand.
    :func:`~zmforge.verify.model._standing_patches` leaves a yard out of the
    playable area on purpose -- the barricade prefab stops the *player* at
    the wall line -- and that is exactly what makes it ground a zombie stands
    on and a player cannot reach.  It is also the case the community names:
    Logical Edits, "Zombie Spawners & Zones", about 7:12, says keep zone
    volume out from behind window barricades and traversals.  This package
    models no traversal, so a yard is the whole of it.

    **Not** included, on purpose, and each for the same reason -- nothing
    here says a *zombie* can get there either, and a volume over ground no
    zombie dies on costs nothing:

    * a surface the map declares ``reachable=False``.  Every other check in
      this package passes over one in silence because the map said so, and
      this one does too;
    * floor the flood never gets to -- a pocket walled off on every side.
      ``Z25`` already warns about that as dead floor, and a partition that
      stops a player stops a zombie.

    If a map ever grows a traversal, or a ledge a zombie can be pushed onto,
    this is the function that learns about it.
    """
    return [
        (f"the yard {yard.id}, which is the zombies' side of a barricade",
         yard.interior, yard.floor_z)
        for yard in blueprint.elements(Yard)
    ]


def _check_volumes_over_unreachable_ground(blueprint, report: Report) -> None:
    """Z40: a zone volume covering ground a player cannot get to.

    The converse of ``Z18``.  ``Z18`` asks that nowhere a player stands is
    outside every volume, because the out-of-playable-area monitor kills them
    there.  This asks the other half -- that a volume does not reach over
    ground only zombies can occupy -- and the cost is not a death, it is a
    round's powerups, so it is a warning.  What counts as that ground, and
    what deliberately does not, is
    :func:`_zombie_ground_no_player_reaches`.

    Two stock mechanisms, and the volume is the switch for both.

    **A zombie is not powerup-eligible until it touches a volume.**
    ``_zm_spawner.gsc:359`` sets ``self.no_powerups = true`` on every zombie
    as it spawns.  ``zombie_entered_playable`` (``:593``) then polls once a
    second over ``GetEntArray( "player_volume", "script_noteworthy" )`` and
    the first volume the zombie touches calls
    ``zombie_complete_emerging_into_playable_area`` (``:3253``), whose second
    line is ``self.no_powerups = false``.  ``zombie_can_drop_powerups``
    (``:1545``) reads that flag.  So a volume stopping at the barricade's
    wall line means a zombie killed in the yard drops nothing at all; a
    volume reaching over the yard means it is already eligible out there.

    **The drop itself is validated against the same volumes.**
    ``zombie_death_points`` (``_zm_spawner.gsc:1584``) ground-traces the
    corpse and threads ``zm_powerups::powerup_drop( origin )``.  That
    function (``_zm_powerups.gsc:586``) increments
    ``level.powerup_drop_count``, spawns the powerup at ``origin + (0,0,40)``
    and keeps it only if it ``istouching`` one of the ``player_volume``
    entities -- *any* of them, enabled or not.  Outside every volume it is
    deleted and the count is decremented, so the map gets the drop back.
    Inside one, it stays: 15 seconds of ``powerup_timeout`` on a max of
    ``zombie_powerup_drop_max_per_round`` = 4 per round
    (``_zm_powerups.gsc:74``), spent on a spot nobody can walk to.

    Community source for the rule, from the other end: Logical Edits,
    "Zombie Spawners & Zones", about 7:12 -- keep zone volume out from
    behind window barricades and traversals.  The consequence he gives is
    the uncollectable drop; the eligibility flag is ours, read here.
    """
    ground = _zombie_ground_no_player_reaches(blueprint)
    if not ground:
        return
    for zone in blueprint.elements(Zone):
        if zone.bounds is None:
            continue
        total = 0.0
        biggest: tuple[float, str, Span] | None = None
        for label, box, surface in ground:
            if not (
                zone.bounds.mins.z - STEP_TOLERANCE
                <= surface
                <= zone.bounds.maxs.z
            ):
                continue
            shared = _plan_intersection(zone.bounds, box, surface)
            if shared is None:
                continue
            area = shared.extent(Axis.X) * shared.extent(Axis.Y)
            if area < Z40_MIN_AREA:
                continue
            total += area
            if biggest is None or area > biggest[0]:
                biggest = (area, label, shared)
        if biggest is None or total < Z40_MIN_AREA:
            continue
        spot = biggest[2].centre
        report.add(
            warning(
                "Z40",
                f"zone {zone.name!r}'s volume covers {total:.0f} square units "
                "of ground no player can walk to, the largest piece being "
                f"{biggest[1]} around ({spot.x:g}, {spot.y:g}, "
                f"{biggest[2].mins.z:g}). A zombie is only powerup-eligible "
                "once it touches a player_volume (_zm_spawner.gsc:3253 clears "
                "no_powerups), and a drop is kept wherever it touches one "
                "(_zm_powerups.gsc:630), so this turns a zombie killed out "
                "there from a no-drop into one of the round's four powerups, "
                "landing where nobody can collect it. Pull the volume back to "
                "the ground a player can stand on",
                zone.id,
            )
        )


def _inside(bounds: Span, cell: Standing) -> bool:
    return (
        min(bounds.maxs.x, cell.floor.maxs.x) - max(bounds.mins.x, cell.floor.mins.x)
        > 0.0
        and min(bounds.maxs.y, cell.floor.maxs.y)
        - max(bounds.mins.y, cell.floor.mins.y)
        > 0.0
        and bounds.mins.z - STEP_TOLERANCE <= cell.z <= bounds.maxs.z
    )
