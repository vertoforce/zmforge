"""Z44: the placement relations, asked of a map that is already built.

Nothing has ever asked a finished layout whether it makes sense.  A test map
measured prop by prop (2,200 ``misc_model`` entities) shows that the count of
things a player sees immediately is not small: **135** wall and
ceiling fixtures -- clocks, signs, notice boards, chandeliers -- lying in or
under the floor tile, **89** solid props drawn through each other over 133
pairs, **31** props hanging in the air above a slab 55 to 70 units below,
**77** hanging off the edge of the plinth or counter they stand on, and **34**
standing inside an interactive item's own body, one of them straight through
Quick Revive.  Every check in :mod:`zmforge.verify` passed that map.  They
had to: they ask about brushwork, scripts, zones and reachability, and a prop
is none of those.

This module is the check-time half of :mod:`zmforge.placement`.  The placer
that will not make these mistakes is the other half, and both halves say the
rule with the same objects -- :class:`~zmforge.placement.relations.NoOverlap`,
:class:`~zmforge.placement.relations.SupportedBy`,
:func:`~zmforge.placement.relations.mount_kind_of_box` -- because a rule that
chooses a position and a rule that judges one disagree the moment they are
written twice.

What it asks
------------
Four questions, each one a fault that can be counted from boxes alone:

``mount``
    a model whose own measured box says it hangs on a wall or from a ceiling,
    standing at floor level.  135 of them, and the most visible fault in the
    map: a clock authored with its origin in the middle of its back plate is
    half in the tile when it is dealt into a floor row, and a chandelier is
    wholly under it;
``overlap``
    two solid props sharing more than a quarter of the smaller one's footprint
    at the same height.  A desk 72% inside a bench, a chair 98% inside a
    plant;
``support``
    a prop floating over the thing it stands on, or hanging off the edge of
    it.  A crate with none of its four corners on the plinth it is on;
``item``
    a prop standing inside an interactive item's own body, which is how a
    bench ends up through a perk machine's use prompt.

What it does not ask, on purpose
--------------------------------
Each of these is a real fault, and each needs evidence this module is not
given, so it says nothing rather than guessing:

* **props inside world brushwork** (desks in plinths, newspapers in
  columns, rocks in walls).  That is a question about brush solids, and
  the answer belongs with the placer's own inset pass;
* **stairs and landings**.  Which solids are a route is a blueprint
  question, not a geometry one;
* **sight lines** -- a prop on the line from a spawn to a door, or hiding a
  door leaf.  It needs the doors, the spawns and an occlusion test;
* **theme** -- rubble in a finished office, pallets in a hall.
  A room's theme is authored, and nothing in a box says a model is wrong for
  a room.

Warning, and not yet an error
-----------------------------
Every finding is a **warning** by default, because the placer has not been
switched over: a real map has hundreds of these and an error would fail
every build for a fault nobody introduced in it.  ``severity="error"``
flips all four rules at once, and that is the argument to change on the day
the placer lands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from ..verify.report import Finding, error, warning
from .geometry import EPSILON, Poly2, rotate
from .relations import (
    MountKind,
    NoOverlap,
    Placed,
    Surface,
    SupportedBy,
    mount_kind_of_box,
)

__all__ = [
    "LAYOUT_CODE",
    "LayoutRoom",
    "ItemFootprint",
    "Layout",
    "layout_from_blueprint",
    "layout_from_map_text",
    "check_layout",
    "MOUNT_SLACK",
    "OVERLAP_SHARE",
    "OVERLAP_MIN_SIDE",
    "SUPPORT_REACH",
    "FLOAT_SLACK",
    "SUPPORT_SHARE",
    "BURIED_SHARE",
    "FLOOR_EXCEPTIONS",
    "ITEM_MIN_HEIGHT",
    "ITEM_MIN_AREA",
    "OVERLAP_RULE",
    "FLOATS_RULE",
    "OVERHANG_RULE",
]

#: The registry row every finding here carries.  One code for all four rules:
#: they are one requirement -- "a prop is placed where a prop can be" -- and
#: a reader chasing a warning wants the rule in the message, not four rows in
#: the table saying the same thing four ways.
LAYOUT_CODE = "Z44"

#: How far above the thing under it a wall or ceiling fixture has to be
#: before it is no longer "at floor level".  One unit, a tenth of the ``.map``
#: writer's 8-unit grid, same as ``relations.NEAR``: a mount fault is a prop
#: at or below the floor, not a unit over it.
MOUNT_SLACK = 1.0

#: How much of the smaller footprint two solid props may share before this is
#: interpenetration.  A quarter, because that is past anything a dresser can
#: explain: real cases run 72% (a desk in a bench) and 98% (a chair in a
#: plant).
OVERLAP_SHARE = 0.25

#: Both plan sides under this and the overlap rule lets a prop alone.  40
#: units is the smallest thing in this palette a player reads as furniture;
#: below it are cups, bottles, papers and cutlery, and a cup half inside a
#: bowl is a still life rather than a fault.
OVERLAP_MIN_SIDE = 40.0

#: How far above a prop's own base a surface may be and still be the thing it
#: stands on.  8 units is the engine's step height (``props.SOLID_STAND_ON``
#: uses the same number for the same reason): anything this close is under
#: the prop's feet rather than something it has walked into.
SUPPORT_REACH = 8.0

#: How far a prop may sit above what it stands on before it is floating.  Two
#: units, a quarter of the map grid; a floating prop is typically tens of
#: units up, so nothing here turns on the exact number.
FLOAT_SLACK = 2.0

#: How much of its footprint a prop has to have on the raised surface it
#: stands on.  A prop with two corners or fewer of four on what it stands on
#: is not standing on it; half the footprint is that rule written as a share,
#: and it is the number a rectangle with two corners off has.
SUPPORT_SHARE = 0.5

#: How much of a prop's footprint something rising past its base has to cover
#: before the prop is read as buried in that thing rather than standing beside
#: it.  Half, the same share the overhang rule uses and for the same reason:
#: a corner of contact is a graze, and the fault this guard is here for -- a
#: rebar column 65 units into the tile -- has the floor over all of its
#: footprint, not a corner of it.
BURIED_SHARE = 0.5

#: A prop shorter than this standing in an interactive item's body is not
#: reported.  Flat litter -- a newspaper, a cigarette
#: packet -- lies under the body of a machine without covering the prompt or
#: the drawing, and 8 units is the height below which a model is litter.
ITEM_MIN_HEIGHT = 8.0

#: How much plan area a prop and an item's body have to share before it
#: counts.  One square unit, which is a rounding error on a 40-by-36 machine:
#: this rejects footprints that only touch along an edge.
ITEM_MIN_AREA = 1.0

#: How finely a heightfield is cut into flat surfaces, in units.  Coarser and
#: a prop on a slope is judged against a surface it is nowhere near: at the
#: mesh's own 99-unit cell size, measured, 177 props standing exactly on
#: sloped ground read as floating.
#:
#: The number that decides this is **the relief inside one square**, against
#: :data:`SUPPORT_REACH`, and not the player's width.  A square carries its
#: *highest* corner (:func:`_height_cells`) and :meth:`_SurfaceIndex.under`
#: drops any surface whose top is over ``prop.z_low + SUPPORT_REACH``, so a
#: square that climbs more than that across itself **excludes itself** from
#: the search under a prop standing on its low side, and the prop is judged
#: against a lower neighbouring square or against the room floor.  The
#: highest corner was chosen to be the conservative direction and on a steep
#: square it is the opposite one.
#:
#: 32 was the player's width and was too coarse here, measured:
#: on a terrain slope that climbs 0.7 per unit (21.6 to 63.9 over 60
#: units), a 32-unit square carries 20 to 30 units of relief
#: and five props whose ``Blueprint.ground_under`` height equals their
#: own z to the unit -- a shovel, a weed cluster, a pallet, a sandbag and a
#: wheelbarrow -- were reported floating 3 to 30 units over ground they were
#: standing on.  Halving it clears all five and adds no finding of any code;
#: 8 gives the same answer as 16, and the whole layout check costs 1.5 s
#: instead of 0.7 s on a map of 1,904 props.
TERRAIN_SAMPLE = 16.0

#: The side of the plan buckets the pair scans use, in units.  256 is a
#: little over the longest prop in the palette (a 208-unit staircase frame),
#: so a prop reaches at most one bucket in each direction, and it puts the
#: test map's 2,200 props in about 400 buckets rather than in one list of
#: 2.4 million pairs.
BUCKET = 256.0

#: Two solid props at the same height, sharing too much floor.
OVERLAP_RULE = NoOverlap(tolerance=OVERLAP_SHARE, min_side=OVERLAP_MIN_SIDE)

#: Is the prop resting on the thing under it?  ``share=0`` because this asks
#: about height only; the footprint is the next rule's question.
FLOATS_RULE = SupportedBy(tolerance=FLOAT_SLACK, share=0.0)

#: Is enough of the prop on the raised surface it stands on?  The tolerance is
#: :data:`SUPPORT_REACH` so that the height test inside the relation cannot
#: fire here: this rule is only ever asked of a prop already known to be
#: standing on the surface.
OVERHANG_RULE = SupportedBy(tolerance=SUPPORT_REACH, share=SUPPORT_SHARE)


# --------------------------------------------------------------------------
# The record a check reads
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LayoutRoom:
    """One room, as a footprint, a floor and a ceiling.

    This is deliberately less than a :class:`~zmforge.blueprint.elements.Room`
    -- a rectangle and two heights -- because it is all four rules need and
    because it is the most a ``.map`` file can be read back to.  A map edited
    in an editor and re-parsed has to be judged by the same rules as the
    blueprint it came from, and it can only be if the rules are written
    against what both sides can produce.
    """

    id: str
    x0: float
    y0: float
    x1: float
    y1: float
    floor_z: float
    ceiling_z: float

    @property
    def rect(self) -> Poly2:
        return Poly2.rect(self.x0, self.y0, self.x1, self.y1)

    @property
    def floor(self) -> Surface:
        """The room's own floor, as a surface a prop can stand on.

        Named the way a finding wants to read it, and the same way the map
        text adapter names the slab it reads back, so the two sides of the
        check produce the same sentence about the same fault.
        """
        return Surface(f"the floor of {self.id}", self.rect, self.floor_z)

    def holds(self, x: float, y: float) -> bool:
        """Is this plan point inside the room's footprint?"""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def height_overlap(self, z_low: float, z_high: float) -> float:
        """How much of a height range is inside this room's storey."""
        return min(self.ceiling_z, z_high) - max(self.floor_z, z_low)


@dataclass(frozen=True, slots=True)
class ItemFootprint:
    """One interactive item's own body: the space the item itself fills.

    The **body** and not the apron.  An apron is standing room and a prop in
    one is a crowding question ``Z42`` already asks of the items; a prop in
    the body is drawn through the machine, as a bench set into a perk
    machine is.
    """

    id: str
    what: str
    poly: Poly2
    z_low: float
    z_high: float


@dataclass(frozen=True, slots=True)
class Layout:
    """A finished map's props and the things they are judged against.

    Plain data, and both adapters fill in the same fields, so a check cannot
    tell whether it was handed a blueprint or a re-parsed ``.map``.

    ``surfaces`` and ``ground`` are split because a prop is judged differently
    against each.  ``surfaces`` are *raised* tops -- a plinth, a counter, a
    desk, a block -- and a prop on one has to have most of its footprint on it
    (:data:`SUPPORT_SHARE`); a prop with none of its four corners on a
    narrow plinth is the fault.  ``ground`` is floors and terrain, where only
    the height is asked: a prop whose footprint crosses a floor's edge is
    inside a wall, which is brushwork and out of scope here.

    ``spawns`` is carried and not yet read.  Spawn-cluster rules (a row of
    props through the spawn points, chairs on the line to the first door)
    need lanes and an occlusion test, and both belong with the
    placer; the field is here so the adapters do not have to change when they
    land.
    """

    props: tuple[Placed, ...] = ()
    rooms: tuple[LayoutRoom, ...] = ()
    surfaces: tuple[Surface, ...] = ()
    ground: tuple[Surface, ...] = ()
    items: tuple[ItemFootprint, ...] = ()
    spawns: tuple[tuple[float, float, float], ...] = ()
    #: Model name to mount kind, worked out once by the adapter from the
    #: model's own box and the name families :mod:`zmforge.recipes.props`
    #: lists.  Here rather than in the rule so that the check never imports
    #: the palette, and so a caller can judge a map whose models the mod tools install
    #: has never measured.
    mounts: Mapping[str, MountKind] = field(default_factory=dict)
    #: Model name to where its seat is, as a share of its own height from
    #: the base: a chair holds up what is left on it at the seat, not at the
    #: top of its backrest.  Filled by the adapter from
    #: :data:`zmforge.recipes.props.SEAT_TOP`, for the same reason as
    #: :attr:`mounts`.
    seats: Mapping[str, float] = field(default_factory=dict)
    #: Model name to where its inner boards are, each as a share of its own
    #: height from the base, lowest first: a shelving unit holds things up
    #: on every board, not only on its top.  Filled by the adapter from
    #: :data:`zmforge.recipes.props.SHELF_BOARDS`, like :attr:`seats`.
    shelves: Mapping[str, tuple[float, ...]] = field(default_factory=dict)

    def room(self, name: str) -> LayoutRoom | None:
        for room in self.rooms:
            if room.id == name:
                return room
        return None


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------

#: Walk-through plants judged by their stem, not their leaf box, wherever a
#: layout is read off a blueprint (support, overlap): a model name holding
#: one of these.
STEM_JUDGED = ("corn_stalk",)
#: Half the stem those plants stand on, world units.
STEM_HALF = 6.0


def _stem_box(model: str, box, scale: float):
    """*box*, or for a walk-through plant on one stem (:data:`STEM_JUDGED`)
    the stem it stands on.  WHY: a lining corn
    stalk stands where its stem does; its leaves over a picnic blanket 24
    off the wall are not standing on the blanket.  Judged by its leaves,
    every refill stalk behind it is dropped as "15% on the blanket" (Z44),
    which leaves bare wall (Z89).  The same reading as a tree by its trunk."""
    if not any(part in model for part in STEM_JUDGED):
        return box
    (_x0, _y0, z0), (_x1, _y1, z1) = box
    r = STEM_HALF / max(scale, 1e-6)
    return ((-r, -r, z0), (r, r, z1))  # the stem is the model's origin


def check_layout(
    layout: Layout, *, severity: str = "warning", code: str = LAYOUT_CODE
) -> list[Finding]:
    """Every layout rule, over one map, as ``Z44`` findings.

    ``severity`` is ``"warning"`` or ``"error"`` and applies to all four
    rules.  Warning is the default and the honest setting while the placer
    still deals models by list position: a full map produces hundreds of
    these, and an error would fail a build over a layout nobody touched.

    ``code`` is the registry row the findings carry.  It is a parameter, and
    the callers in :mod:`zmforge.verify` pass it, because the table of rows is
    that package's and a check that hard-coded another package's row would be
    two places to change it.
    """
    if severity not in ("warning", "error"):
        raise ValueError(f"severity must be 'warning' or 'error', got {severity!r}")
    faults: list[tuple[Placed, str]] = []
    faults += _mount_faults(layout)
    faults += _overlap_faults(layout)
    faults += _support_faults(layout)
    faults += _item_faults(layout)
    return [_say(severity, code, prop, detail) for prop, detail in faults]


def _say(severity: str, code: str, prop: Placed, detail: str) -> Finding:
    """One finding, as the layout check prints it: model, position, room, fault."""
    where = f" in {prop.room}" if prop.room else ""
    message = f"{prop.name} at {prop.position}{where} {detail}"
    element = prop.ident or prop.name
    if severity == "error":
        return error(code, message, element, prop.position)
    return warning(code, message, element, prop.position)


def _names(prop: Placed) -> str:
    """What a prop is called when it is the thing another prop stands on."""
    return f"{prop.name} at {prop.position}"


def _mount_faults(layout: Layout) -> list[tuple[Placed, str]]:
    """Rule 1: a wall or ceiling fixture standing at floor level.

    "At floor level" is measured against whatever is under the fixture rather
    than against the room's floor number, so a fixture dealt onto a plinth is
    caught by the same test as one dealt onto the tile.  A fixture is never
    standing on anything: it is screwed to a plane.
    """
    found: list[tuple[Placed, str]] = []
    under = _SurfaceIndex(tuple(layout.ground) + tuple(layout.surfaces))
    for prop in layout.props:
        kind = layout.mounts.get(prop.name, MountKind.FLOOR)
        if kind not in (MountKind.WALL, MountKind.CEILING):
            continue
        support = under.highest_below(prop, ceiling=prop.z_high + MOUNT_SLACK)
        if support is None:
            continue
        if prop.z_low > support.top_z + MOUNT_SLACK:
            continue
        sunk = support.top_z - prop.z_low
        buried = " and is wholly under it" if prop.z_high <= support.top_z else ""
        found.append((
            prop,
            f"is a {kind.value} fixture standing at floor level: its box "
            f"reaches {sunk:.0f} units into the top of {support.name}{buried}. "
            "A model whose box straddles its own origin in Z is mounted on a "
            "plane, not dealt into a floor row",
        ))
    return found


def _is_crown(model_box, body_box) -> bool:
    """True when *body_box* is under a tenth of *model_box*'s footprint: a
    model that is mostly air round a small solid body (a tree)."""
    (mx0, my0, _), (mx1, my1, _) = model_box
    (bx0, by0, _), (bx1, by1, _) = body_box
    model_area = max(mx1 - mx0, 0.0) * max(my1 - my0, 0.0)
    return model_area > 0.0 and (bx1 - bx0) * (by1 - by0) < 0.1 * model_area


def _overlap_faults(layout: Layout) -> list[tuple[Placed, str]]:
    """Rule 2: two solid props in the same place at the same height."""
    solids = [prop for prop in layout.props if prop.solid]
    index = _PlanIndex(solids)
    found: list[tuple[Placed, str]] = []
    for first, second in index.pairs():
        violation = OVERLAP_RULE.check(solids[first], solids[second])
        if violation is None:
            continue
        subject = solids[first]
        other = solids[second]
        found.append((
            subject,
            f"is {violation.amount * 100:.0f}% inside {other.name} at "
            f"{other.position}, at the same height. Two solid props sharing "
            "floor are drawn through each other",
        ))
    return found


def _support_faults(layout: Layout) -> list[tuple[Placed, str]]:
    """Rule 3: floating over what it stands on, or hanging off the edge of it.

    Three things can hold a prop up and all three are looked at: the ground (a
    room's floor, the terrain), a raised surface (a plinth, a counter, a
    block) and **another prop**, because a map that sets a cake on a table has
    put the cake 32 units over the floor on purpose.

    A prop only holds another prop up if it is itself held up.  Without that
    a row of props over a gap in the ground holds *itself* up: it hangs 55 to 70 units over the
    slab and every prop in it has the prop beside it under its feet.  So the
    grounded set is grown from the world outwards -- props resting on the
    ground or on a raised surface first, then whatever rests on those -- which
    also settles the cycles that row is full of.  Measured on a test map:
    38 floating props if any prop counts as support, 47 with the
    grounding pass.

    Two props are never reported.  One with nothing at all under it means the
    map has no surface here -- an imported ``.map``, a room this adapter could
    not read -- and a check that reported it would be reporting its own
    blindness.  One that is *not floor-standing* is not standing: a wall
    fixture is screwed to a plane, and rule 1 has the ones in the wrong place.
    """
    raised = {id(surface) for surface in layout.surfaces}
    world = _SurfaceIndex(tuple(layout.ground) + tuple(layout.surfaces))
    # Every prop holds things up on its top, a seat also at the seat and a
    # shelving unit also on each board.  The box top stays a surface for a
    # shelving unit too, though it is the tops of its posts or frame (5.8
    # over the vintage unit's top board): the cemetery and the corn maze set
    # things at that height, and calling them floaters is a change for those
    # maps to make, not this table.
    levels = []
    for index, prop in enumerate(layout.props):
        levels.append((index, prop, 1.0))
        if prop.name in layout.seats:
            levels.append((index, prop, layout.seats[prop.name]))
        levels += [(index, prop, share) for share in layout.shelves.get(prop.name, ())]
    tops = _SurfaceIndex(
        [
            Surface(_names(prop), prop.footprint,
                    prop.z_low + (prop.z_high - prop.z_low) * share)
            for _index, prop, share in levels
        ],
        [index for index, _prop, _share in levels],
    )

    standing = [
        index
        for index, prop in enumerate(layout.props)
        if layout.mounts.get(prop.name, MountKind.FLOOR) is MountKind.FLOOR
    ]
    on_world: dict[int, Surface] = {}
    holders: dict[int, list[int]] = {}
    grounded: set[int] = set()
    for index in standing:
        prop = layout.props[index]
        if _is_buried(prop, world):
            grounded.add(index)  # inside the geometry, not over it: not this rule
            continue
        surface = world.highest_below(prop, ceiling=prop.z_low + SUPPORT_REACH)
        if surface is not None:
            on_world[index] = surface
            if prop.z_low - surface.top_z <= FLOAT_SLACK:
                grounded.add(index)
                continue
        holders[index] = [
            owner
            for support, owner in tops.under(prop, ceiling=prop.z_low + SUPPORT_REACH)
            if owner != index and prop.z_low - support.top_z <= FLOAT_SLACK
        ]

    _spread_grounding(grounded, holders)

    found: list[tuple[Placed, str]] = []
    for index in standing:
        prop = layout.props[index]
        support = on_world.get(index)
        if index not in grounded:
            if support is None:
                continue  # nothing of the world under it at all: cannot judge
            propped = " on props that are not resting on anything either" if (
                holders.get(index)
            ) else ""
            found.append((
                prop,
                f"floats {prop.z_low - support.top_z:.0f} units over "
                f"{support.name}, the highest thing under it{propped}",
            ))
            continue
        if support is None or id(support) not in raised:
            continue  # a floor's own edge is a wall question, not this one
        if prop.z_low - support.top_z > FLOAT_SLACK:
            continue  # standing on another prop over this surface, not on it
        overhang = OVERHANG_RULE.check(prop, support)
        if overhang is not None:
            on = max(0.0, SUPPORT_SHARE - overhang.amount)
            found.append((
                prop,
                f"has {on * 100:.0f}% of its footprint on {support.name}, the "
                f"raised surface it stands on, under the {SUPPORT_SHARE * 100:.0f}% "
                "two of its four corners would give it",
            ))
    return found


def _spread_grounding(grounded: set[int], holders: Mapping[int, Sequence[int]]) -> None:
    """Ground everything resting on something already grounded, and repeat.

    A fixed point rather than a walk, because the holds-up graph has cycles in
    it -- three props in a hovering row each resting on the next -- and a walk
    would either loop or call the cycle grounded.
    """
    held_by: dict[int, list[int]] = {}
    for index, supports in holders.items():
        for other in supports:
            held_by.setdefault(other, []).append(index)
    queue = list(grounded)
    while queue:
        settled = queue.pop()
        for index in held_by.get(settled, ()):
            if index not in grounded:
                grounded.add(index)
                queue.append(index)


def _is_buried(prop: Placed, index: "_SurfaceIndex") -> bool:
    """Is this prop *inside* something rather than on top of something?

    A rebar column whose z-centred box puts 65 units of itself into the floor
    tile has the floor covering its whole footprint at a height well above its
    own base.  That is the placer's z arithmetic and it is out of scope here; what this guard buys is that the rule
    does not then go looking further down, find the storey below and call the
    column a floating prop.

    The share matters.  A desk standing on the floor beside a plinth grazes
    that plinth by a corner, and a corner is not being inside it.
    """
    above = index.highest_below(prop, ceiling=prop.z_high, skip=id(prop))
    if above is None or above.top_z <= prop.z_low + SUPPORT_REACH:
        return False
    area = prop.footprint.area
    if area <= EPSILON:
        return False
    return prop.footprint.overlap_area(above.poly) / area >= BURIED_SHARE


def _item_faults(layout: Layout) -> list[tuple[Placed, str]]:
    """Rule 4: a prop standing inside an interactive item's own body."""
    found: list[tuple[Placed, str]] = []
    if not layout.items:
        return found
    for prop in layout.props:
        if prop.height < ITEM_MIN_HEIGHT:
            continue  # litter under a machine covers nothing
        for item in layout.items:
            if min(prop.z_high, item.z_high) - max(prop.z_low, item.z_low) <= 0.0:
                continue
            shared = prop.footprint.overlap_area(item.poly)
            if shared < ITEM_MIN_AREA:
                continue
            found.append((
                prop,
                f"stands inside the body of {item.what} ({item.id}), sharing "
                f"{shared:.0f} square units of floor with it. The item is "
                "drawn through the prop and its use prompt is behind it",
            ))
    return found


# --------------------------------------------------------------------------
# Finding things near things
# --------------------------------------------------------------------------
def _bucket_cells(x0: float, y0: float, x1: float, y1: float) -> Iterable[tuple[int, int]]:
    for cx in range(int(math.floor(x0 / BUCKET)), int(math.floor(x1 / BUCKET)) + 1):
        for cy in range(int(math.floor(y0 / BUCKET)), int(math.floor(y1 / BUCKET)) + 1):
            yield (cx, cy)


class _PlanIndex:
    """Props bucketed by plan position, so the pair scan is not quadratic.

    2,200 props is 2.4 million pairs, and a test map's props sit in about
    400 buckets of :data:`BUCKET` units; every pair this yields shares a
    bucket, which is a superset of every pair that can overlap.
    """

    def __init__(self, props: Sequence[Placed]) -> None:
        self._props = props
        self._cells: dict[tuple[int, int], list[int]] = {}
        for index, prop in enumerate(props):
            for cell in _bucket_cells(*prop.footprint.bounds):
                self._cells.setdefault(cell, []).append(index)

    def pairs(self) -> Iterable[tuple[int, int]]:
        """Every pair whose boxes overlap in plan, each pair once."""
        seen: set[tuple[int, int]] = set()
        for members in self._cells.values():
            for position, first in enumerate(members):
                a0, b0, a1, b1 = self._props[first].footprint.bounds
                for second in members[position + 1:]:
                    key = (first, second) if first < second else (second, first)
                    if key in seen:
                        continue
                    c0, d0, c1, d1 = self._props[second].footprint.bounds
                    if a1 <= c0 or c1 <= a0 or b1 <= d0 or d1 <= b0:
                        continue
                    seen.add(key)
                    yield key


class _SurfaceIndex:
    """Surfaces bucketed by plan position, for "what is under this prop?".

    ``owners`` names what each surface belongs to, or ``None`` for the ground
    and the world's own solids.  It is how a prop is kept from being told it
    is standing on itself once every prop's top is a surface too.
    """

    def __init__(
        self, surfaces: Sequence[Surface], owners: Sequence[int | None] | None = None
    ) -> None:
        self._surfaces = surfaces
        self._owners = owners if owners is not None else [None] * len(surfaces)
        self._cells: dict[tuple[int, int], list[int]] = {}
        for index, surface in enumerate(surfaces):
            for cell in _bucket_cells(*surface.poly.bounds):
                self._cells.setdefault(cell, []).append(index)

    def under(
        self, prop: Placed, *, ceiling: float, skip: int | None = None
    ) -> list[tuple[Surface, int | None]]:
        """Every surface under ``prop`` whose top is at or under ``ceiling``.

        Under means *under the footprint*: a surface the prop only stands
        beside is not one it could be standing on, however close its top is.
        """
        footprint = prop.footprint
        found: list[tuple[Surface, int | None]] = []
        for index in self._near(footprint.bounds):
            surface = self._surfaces[index]
            owner = self._owners[index]
            if surface.top_z > ceiling or (skip is not None and owner == skip):
                continue
            if footprint.overlap_area(surface.poly) <= EPSILON:
                continue
            found.append((surface, owner))
        return found

    def highest_below(
        self, prop: Placed, *, ceiling: float, skip: int | None = None
    ) -> Surface | None:
        """The highest surface under ``prop``, ties broken by overlap.

        Ties are the common case rather than the odd one: a room's floor slab
        and the plinth beside it are written as separate brushes with their
        tops on the same plane, and a prop on the floor grazing the plinth by
        a corner is standing on the floor.
        """
        best: Surface | None = None
        best_rank = (-math.inf, 0.0)
        for surface, _owner in self.under(prop, ceiling=ceiling, skip=skip):
            rank = (surface.top_z, prop.footprint.overlap_area(surface.poly))
            if rank > best_rank:
                best, best_rank = surface, rank
        return best

    def _near(self, bounds: tuple[float, float, float, float]) -> set[int]:
        found: set[int] = set()
        for cell in _bucket_cells(*bounds):
            found.update(self._cells.get(cell, ()))
        return found


# --------------------------------------------------------------------------
# The two adapters
# --------------------------------------------------------------------------
def _model_boxes(boxes: Mapping[str, tuple] | None) -> Mapping[str, tuple]:
    """The measured-box table, defaulting to the palette's own.

    Imported inside the function on purpose.  :mod:`zmforge.recipes.props`
    imports half the blueprint to place a prop, and a check that pulled it in
    at import time would make ``zmforge.placement`` depend on the placer it
    exists to replace.
    """
    if boxes is not None:
        return boxes
    from ..props.origins import drawn_boxes
    from ..recipes import props

    # The catalogue boxes are in the artist's scene frame; a model draws in
    # its root bone's (zmforge.props.origins: 44 of these moved, one duct by
    # 150 units), and a check has to judge the box the player sees.
    return drawn_boxes(props.MODEL_BOX)


#: The models whose measured box says "wall fixture" and which are not one.
#: Measured over the 125 models of ``props.MODEL_BOX``: the box
#: rule (:func:`~zmforge.placement.relations.mount_kind_of_box`) calls fifteen
#: of them ``WALL``.  Ten are wall fixtures and it found them without being
#: told -- the clock, the LED fixture, the picture frame, three pieces of
#: signage, the bulletin board, two Der Riese signs, the duct vent.  These five
#: are the others, and each is a thing that lies or stands on a floor and
#: happens to be authored about its own middle:
#:
#:   ``rebar_column``       a column, authored about its centre, 130 tall
#:   ``tools_shovel``       a shovel
#:   ``wires_electrical``   a coil of cable
#:   ``debris_plaster``     two pieces of broken plaster
#:
#: Without this list the check reports props like these as mount faults
#: (shovels, rebar columns, pieces of plaster), and none of them is a fault.
FLOOR_EXCEPTIONS: tuple[str, ...] = (
    "rebar_column",
    "tools_shovel",
    "wires_electrical",
    "debris_plaster",
)


def _seat_shares(models: Iterable[str], boxes: Mapping[str, tuple]) -> dict[str, float]:
    """Each seat model's seat height as a share of its measured box height."""
    from ..recipes import props

    shares: dict[str, float] = {}
    for name in models:
        seat, box = props.SEAT_TOP.get(name), boxes.get(name)
        if seat is None or box is None:
            continue
        height = box[1][2] - box[0][2]
        if height > 0.0:
            shares[name] = (seat - box[0][2]) / height
    return shares


def _shelf_shares(
    models: Iterable[str], boxes: Mapping[str, tuple]
) -> dict[str, tuple[float, ...]]:
    """Each shelving model's board tops as shares of its measured box height."""
    from ..recipes import props

    shares: dict[str, tuple[float, ...]] = {}
    for name in models:
        boards, box = props.SHELF_BOARDS.get(name), boxes.get(name)
        if not boards or box is None:
            continue
        height = box[1][2] - box[0][2]
        if height > 0.0:
            shares[name] = tuple((board - box[0][2]) / height for board in boards)
    return shares


def _mount_kinds(models: Iterable[str], boxes: Mapping[str, tuple]) -> dict[str, MountKind]:
    """Each model's mount kind: its family if it has one, else its own box.

    The order is :func:`zmforge.recipes.props.mount_kind`'s, so the check and
    the placer answer the same question the same way.  The families come
    first because they are the measurements somebody has already made of this
    palette -- what ``signage`` and ``light_chandelier`` are shaped like --
    and the box answers for everything else.

    ``EITHER`` -- z-centred and not thin in plan -- is read as floor-standing.
    That shape is a rock or a lump of masonry as often as it is a fixture, and
    floor-standing is the answer every model got before mount kinds existed,
    so it is the reading that reports nothing new.
    """
    from ..recipes import props

    kinds: dict[str, MountKind] = {}
    for name in models:
        if any(word in name for word in props.CEILING_FAMILIES):
            kinds[name] = MountKind.CEILING
            continue
        if any(word in name for word in props.WALL_FAMILIES):
            kinds[name] = MountKind.WALL
            continue
        if any(word in name for word in FLOOR_EXCEPTIONS):
            kinds[name] = MountKind.FLOOR
            continue
        measured = mount_kind_of_box(boxes.get(name))
        kinds[name] = measured if measured is not MountKind.EITHER else MountKind.FLOOR
    return kinds


def _in_rooms(props: Sequence[Placed], rooms: Sequence[LayoutRoom]) -> tuple[Placed, ...]:
    """Every prop with its room filled in, so every finding can name one.

    A prop belongs to the room whose footprint holds its own footprint centre
    and whose storey its height range shares most of.  The second half is what
    a tall stacked room needs: a hall, the balcony over it and the gallery over
    that have the same plan and three floors, and a prop is in exactly one of them.
    """
    placed: list[Placed] = []
    for prop in props:
        best: LayoutRoom | None = None
        best_overlap = 0.0
        for room in rooms:
            if not room.holds(prop.x, prop.y):
                continue
            overlap = room.height_overlap(prop.z_low, prop.z_high)
            if best is None or overlap > best_overlap:
                best, best_overlap = room, overlap
        placed.append(
            Placed(
                prop.name, prop.x, prop.y, prop.hx, prop.hy, prop.yaw,
                prop.z_low, prop.z_high, prop.solid,
                best.id if best is not None else "", prop.ident,
            )
        )
    return tuple(placed)


def layout_from_blueprint(blueprint, *, boxes: Mapping[str, tuple] | None = None) -> Layout:
    """The layout a blueprint describes, before anything is written.

    This is the side ``zmforge check`` and the editor's Build run, so a fault
    is reported against the model that can still be changed.  ``boxes`` is the
    measured-box table and defaults to :data:`zmforge.recipes.props.MODEL_BOX`;
    a prop whose model has no measured box is left out, because a footprint
    invented for it would be a finding invented for it.
    """
    from ..blueprint.elements import Massing, PlayerStart, PropScatter, Room, Terrain, Zone
    from ..blueprint.model import _solid_bounds
    from ..blueprint.reach import keep_of

    table = _model_boxes(boxes)

    zones = blueprint.elements(Zone)
    rooms = tuple(
        LayoutRoom(
            _zone_named(room, zones),
            room.interior.mins.x, room.interior.mins.y,
            room.interior.maxs.x, room.interior.maxs.y,
            room.floor_z,
            room.shell.ceiling_underside_z,
        )
        for room in blueprint.elements(Room)
    )

    props: list[Placed] = []
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            box = table.get(prop.model)
            if box is None:
                continue
            if prop.collision_box is not None and _is_crown(box, prop.collision_box):
                # A tree: its model box is the whole crown (190-571 units
                # across) and its body is the trunk (dressing.trees,
                # KIT_COLLISION_BOX).  Judged by the crown, every pair of
                # trees whose limbs interleave was "drawn through each other"
                # (Z44 x75 on zm_cemetery).
                box = prop.collision_box
            elif not prop.solid:
                box = _stem_box(prop.model, box, prop.scale)
            props.append(
                Placed.from_model(
                    prop.model, box,
                    (prop.origin.x, prop.origin.y, prop.origin.z),
                    prop.yaw, prop.scale,
                    solid=prop.solid, ident=prop.id,
                )
            )

    from ..verify.camping import CAMPING_CAP

    surfaces: list[Surface] = []
    for massing in blueprint.elements(Massing):
        if getattr(massing, "note", None) == CAMPING_CAP:
            # A camping cap is player clip over a prop top: nothing stands on
            # it and no fixture is screwed to it.  Counted as a surface, every
            # picture hung over a capped cabinet read as a wall fixture
            # standing at floor level (Z44, zm_dmv and a test map).
            continue
        for index, solid in enumerate(massing.solids):
            box = _solid_bounds(solid)
            surfaces.append(
                Surface(
                    f"{massing.id}" if len(massing.solids) == 1 else f"{massing.id}[{index}]",
                    Poly2.rect(box.mins.x, box.mins.y, box.maxs.x, box.maxs.y),
                    box.maxs.z,
                )
            )

    ground = [room.floor for room in rooms]
    for terrain in blueprint.elements(Terrain):
        ground.extend(_terrain_cells(terrain))

    items: list[ItemFootprint] = []
    for element in blueprint.elements():
        keep = _item_keep(element, keep_of)
        if keep is None:
            continue
        body = keep.body
        items.append(
            ItemFootprint(
                keep.element_id, keep.what,
                Poly2.rect(body.mins.x, body.mins.y, body.maxs.x, body.maxs.y),
                body.mins.z, body.maxs.z,
            )
        )

    spawns: list[tuple[float, float, float]] = []
    for start in blueprint.elements(PlayerStart):
        spawns.extend((point.x, point.y, point.z) for point in start.slot_positions())

    return Layout(
        props=_in_rooms(props, rooms),
        rooms=rooms,
        surfaces=tuple(surfaces),
        ground=tuple(ground),
        items=tuple(items),
        spawns=tuple(spawns),
        mounts=_mount_kinds({prop.name for prop in props}, table),
        seats=_seat_shares({prop.name for prop in props}, table),
        shelves=_shelf_shares({prop.name for prop in props}, table),
    )


def _zone_named(room, zones) -> str:
    """What to call a room in a finding: its zone's name, or its own id.

    The zone name is the one a person uses -- ``lobby``, ``queue``, ``crypt``
    -- and it is the only name a written ``.map`` carries for a room at all
    (the player volumes the zone manager reads).  Naming rooms the same way on
    both sides is what lets the two adapters be compared, and it is why a
    finding names "lobby" rather than "room_12".
    """
    middle = room.interior.centre
    for zone in zones:
        box = zone.bounds
        if (box.mins.x <= middle.x <= box.maxs.x
                and box.mins.y <= middle.y <= box.maxs.y
                and box.mins.z - 1.0 <= room.floor_z <= box.maxs.z + 1.0):
            return zone.name
    return room.id


def _item_keep(element, keep_of):
    """The keep-clear volumes of one element, if it is an item with a body.

    A door is skipped.  Its leaf *is* the wall until it is bought, so a prop
    against it is a door-clearance question, counted separately, rather than a prop standing inside a machine.
    """
    from ..blueprint.elements import Door

    if isinstance(element, Door):
        return None
    return keep_of(element)


def _terrain_cells(terrain) -> list[Surface]:
    """A heightfield as flat surfaces, one per :data:`TERRAIN_SAMPLE` square.

    A heightfield is not a plane and :class:`~zmforge.placement.relations.Surface`
    is, so the mesh is cut into squares small enough that the difference does
    not matter.  Each square's height is its **highest** corner, which is the
    conservative direction only while a square climbs less than
    :data:`SUPPORT_REACH` across itself; past that the highest corner puts the
    square over the ceiling :meth:`_SurfaceIndex.under` searches below and the
    square drops out of its own answer.  That is what :data:`TERRAIN_SAMPLE`
    is sized against, and it is the whole reason the number moved.

    The faults this has to see -- a row of props 55 to 70 units over a slab
    because the terrain mesh stops 24 units short of the wall -- are far past
    anything the rounding can hide either way: there is no mesh under them at
    all.
    """
    record = terrain.record
    box = record.footprint

    def height_at(x: float, y: float) -> float | None:
        sample = record.sample(
            min(max(x, box.mins.x), box.maxs.x - 1e-6),
            min(max(y, box.mins.y), box.maxs.y - 1e-6),
        )
        return sample.z if sample.found else None

    return _height_cells(f"{terrain.id} terrain", box.mins.x, box.mins.y,
                         box.maxs.x, box.maxs.y, height_at)


def _height_cells(
    name: str, x0: float, y0: float, x1: float, y1: float, height_at
) -> list[Surface]:
    """One flat surface per :data:`TERRAIN_SAMPLE` square of a heightfield."""
    across = max(1, int(math.ceil((x1 - x0) / TERRAIN_SAMPLE)))
    down = max(1, int(math.ceil((y1 - y0) / TERRAIN_SAMPLE)))
    step_x = (x1 - x0) / across
    step_y = (y1 - y0) / down
    cells: list[Surface] = []
    for column in range(across):
        for row in range(down):
            ax = x0 + column * step_x
            ay = y0 + row * step_y
            bx, by = ax + step_x, ay + step_y
            heights = [
                height for height in (
                    height_at(ax, ay), height_at(bx, ay),
                    height_at(ax, by), height_at(bx, by),
                ) if height is not None
            ]
            if heights:
                cells.append(Surface(name, Poly2.rect(ax, ay, bx, by), max(heights)))
    return cells


#: Which interactive family each stock prefab path belongs to, for a map read
#: back from its own text.  The bodies themselves are
#: :data:`zmforge.blueprint.reach.BODIES`, measured off these same prefabs;
#: this table only says which row a path lands on.
PREFAB_FAMILIES: tuple[tuple[str, str], ...] = (
    ("vending_weapon_upgrade", "pack_a_punch"),
    ("vending_", "machine"),
    ("buyable_magic_box", "mystery_box"),
    ("power_switch", "power_switch"),
    ("spawnable_weapon_", "wall_weapon"),
)

#: What a player spawn point looks like in the text: a ``script_struct``
#: carrying this ``script_noteworthy``.  A zombie riser is the same classname
#: with ``riser_location`` on it, and the noteworthy is the only thing that
#: tells the two apart.
SPAWN_NOTEWORTHY = "initial_spawn"

#: A worldspawn brush no thicker than this, and at least
#: :data:`SLAB_MIN_SIDE` on both plan axes, is read as floor rather than as
#: something a prop stands on top of.  16 units is this generator's own wall
#: and floor thickness (``Room.thickness``), so every floor slab it writes is
#: exactly this thick and every plinth, counter and block is taller.
SLAB_MAX_THICKNESS = 16.0

#: How broad a thin brush has to be before it reads as floor.  32 units is two
#: player widths; anything narrower and this thick is a kerb, a step or a
#: shelf, which is a thing props stand on.
SLAB_MIN_SIDE = 32.0


def layout_from_map_text(text: str, *, boxes: Mapping[str, tuple] | None = None) -> Layout:
    """The layout a written ``.map`` describes, read back out of its own text.

    The compiler reads the text, so the text is what gets checked (spec
    section 9), and a map a person edited in an editor and re-wrote has no
    blueprint behind it at all.  Everything comes out of the file: props from
    the ``misc_model`` entities, rooms from the ``info_volume`` player volumes
    the zone manager uses, floors and platforms from the worldspawn brushes,
    the ground from the terrain patches, and the interactive items from the
    stock prefab paths.
    """
    from ..mapsource.reader import parse_map_text

    table = _model_boxes(boxes)
    document = parse_map_text(text)

    rooms: list[LayoutRoom] = []
    slabs: list[Surface] = []
    patches: list[Surface] = []
    platforms: list[Surface] = []
    props: list[Placed] = []
    items: list[ItemFootprint] = []
    spawns: list[tuple[float, float, float]] = []
    volumes: list[tuple[str, tuple[float, float, float, float, float, float]]] = []

    for entity in document.entities:
        classname = entity.classname
        if classname == "worldspawn":
            for solid in entity.solids:
                bounds = _solid_box(solid)
                if bounds is None:
                    continue
                if _is_patch(solid):
                    patches.extend(_patch_surfaces(solid, bounds))
                    continue
                x0, y0, z0, x1, y1, z1 = bounds
                rect = Poly2.rect(x0, y0, x1, y1)
                if z1 - z0 <= SLAB_MAX_THICKNESS and min(x1 - x0, y1 - y0) >= SLAB_MIN_SIDE:
                    slabs.append(Surface("the floor", rect, z1))
                else:
                    platforms.append(Surface(f"the block at {x0:.0f} {y0:.0f}", rect, z1))
        elif classname == "misc_model":
            placed = _placed_from_entity(entity, table)
            if placed is not None:
                props.append(placed)
        elif classname == "info_volume":
            if entity.value("script_noteworthy") != "player_volume":
                continue
            bounds = _entity_box(entity)
            if bounds is not None:
                volumes.append((entity.value("targetname") or "", bounds))
        elif classname == "misc_prefab":
            item = _item_from_prefab(entity)
            if item is not None:
                items.append(item)
        elif classname == "script_struct":
            if entity.value("script_noteworthy") == SPAWN_NOTEWORTHY:
                origin = _numbers(entity.value("origin"), 3)
                if origin is not None:
                    spawns.append((origin[0], origin[1], origin[2]))

    floor_index = _SurfaceIndex(slabs)
    for name, (x0, y0, z0, x1, y1, z1) in volumes:
        rooms.append(
            LayoutRoom(name, x0, y0, x1, y1, _floor_of(floor_index, x0, y0, x1, y1, z0, z1), z1)
        )

    ground = [
        Surface(_room_named(rooms, surface), surface.poly, surface.top_z)
        for surface in slabs
    ] + patches
    return Layout(
        props=_in_rooms(props, tuple(rooms)),
        rooms=tuple(rooms),
        surfaces=tuple(platforms),
        ground=tuple(ground),
        items=tuple(items),
        spawns=tuple(spawns),
        mounts=_mount_kinds({prop.name for prop in props}, table),
        seats=_seat_shares({prop.name for prop in props}, table),
        shelves=_shelf_shares({prop.name for prop in props}, table),
    )


def _room_named(rooms: Sequence[LayoutRoom], surface: Surface) -> str:
    """Which room's floor a slab is, for a message that can say so."""
    x0, y0, x1, y1 = surface.poly.bounds
    centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    for room in rooms:
        if room.holds(*centre) and abs(room.floor_z - surface.top_z) <= MOUNT_SLACK:
            return f"the floor of {room.id}"
    return "the floor"


def _floor_of(
    index: _SurfaceIndex,
    x0: float, y0: float, x1: float, y1: float,
    z0: float, z1: float,
) -> float:
    """A room's floor height, measured off the slab inside its own volume.

    A zone volume says where a room is and how tall it is; it does not say
    where the floor surface is, because it starts at the *bottom* of the floor
    slab.  So the floor is the top of the lowest slab inside the volume, which
    for every room this generator writes is the volume's own base plus the
    16-unit slab.
    """
    probe = Placed("floor", (x0 + x1) / 2.0, (y0 + y1) / 2.0,
                   (x1 - x0) / 2.0, (y1 - y0) / 2.0, 0.0, z0, z1)
    surface = index.highest_below(probe, ceiling=z0 + SLAB_MAX_THICKNESS * 2.0)
    return surface.top_z if surface is not None else z0


def _is_patch(solid) -> bool:
    return hasattr(solid, "grid")


def _patch_surfaces(solid, bounds: tuple[float, float, float, float, float, float]) -> list[Surface]:
    """A terrain patch as flat surfaces, read off its own control mesh.

    The control points of a mesh patch this generator wrote are a regular
    lattice -- that is what a heightfield chunk is -- so the height between
    them is the bilinear blend of the four around the point, which is what
    :meth:`zmforge.surfaces.ground.TerrainRecord.sample` computes on the
    blueprint side and what the compiler draws.  A patch whose points are not
    a lattice (a hand-made curve, an imported map) is not a heightfield and
    becomes one flat surface at its highest point instead of a wrong guess.
    """
    x0, y0, _z0, x1, y1, z1 = bounds
    lattice: dict[tuple[float, float], float] = {}
    for row in getattr(solid, "grid", ()):
        for vertex in row:
            point = vertex.position
            lattice[(round(float(point.x), 3), round(float(point.y), 3))] = float(point.z)
    xs = sorted({key[0] for key in lattice})
    ys = sorted({key[1] for key in lattice})
    if len(xs) < 2 or len(ys) < 2 or len(xs) * len(ys) != len(lattice):
        return [Surface("the ground", Poly2.rect(x0, y0, x1, y1), z1)]

    def height_at(x: float, y: float) -> float | None:
        column = _slot(xs, x)
        row = _slot(ys, y)
        left, right = xs[column], xs[column + 1]
        near, far = ys[row], ys[row + 1]
        fx = 0.0 if right == left else (min(max(x, left), right) - left) / (right - left)
        fy = 0.0 if far == near else (min(max(y, near), far) - near) / (far - near)
        low = lattice[(left, near)] * (1 - fx) + lattice[(right, near)] * fx
        high = lattice[(left, far)] * (1 - fx) + lattice[(right, far)] * fx
        return low * (1 - fy) + high * fy

    return _height_cells("the ground", xs[0], ys[0], xs[-1], ys[-1], height_at)


def _slot(values: Sequence[float], at: float) -> int:
    """The index of the lattice line at or below ``at``, clamped to a cell."""
    import bisect

    return max(0, min(len(values) - 2, bisect.bisect_right(values, at) - 1))


def _solid_box(solid) -> tuple[float, float, float, float, float, float] | None:
    """The axis-aligned box around one brush or patch, from its own points."""
    points: list[tuple[float, float, float]] = []
    facets = getattr(solid, "facets", ())
    for facet in facets:
        points.extend((p.x, p.y, p.z) for p in facet.points)
    for row in getattr(solid, "grid", ()):
        points.extend((v.position.x, v.position.y, v.position.z) for v in row)
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _entity_box(entity) -> tuple[float, float, float, float, float, float] | None:
    """The box around every solid of one entity."""
    boxes = [box for box in (_solid_box(solid) for solid in entity.solids) if box]
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes), min(box[1] for box in boxes),
        min(box[2] for box in boxes), max(box[3] for box in boxes),
        max(box[4] for box in boxes), max(box[5] for box in boxes),
    )


def _numbers(value: str | None, count: int) -> tuple[float, ...] | None:
    if not value:
        return None
    parts = value.split()
    if len(parts) < count:
        return None
    try:
        return tuple(float(part) for part in parts[:count])
    except ValueError:
        return None


def _placed_from_entity(entity, table: Mapping[str, tuple]) -> Placed | None:
    """One ``misc_model`` entity as a placed prop.

    ``angles`` is ``pitch yaw roll`` and the middle number is the yaw, the
    same reading :meth:`Placed.from_model` wants.  ``use_collmap`` is what
    makes a prop solid: the key is read at compile time and is the whole of
    the difference between a prop the player walks into and one he walks
    through.
    """
    model = entity.value("model")
    if not model:
        return None
    box = table.get(model)
    origin = _numbers(entity.value("origin"), 3)
    if box is None or origin is None:
        return None
    angles = _numbers(entity.value("angles"), 3) or (0.0, 0.0, 0.0)
    scale = _numbers(entity.value("modelscale"), 1) or (1.0,)
    solid = entity.value("use_collmap") == "1"
    if not solid:
        box = _stem_box(model, box, scale[0])
    return Placed.from_model(
        model, box, origin, angles[1], scale[0],
        solid=solid,
        ident=entity.value("targetname") or "",
    )


def _item_from_prefab(entity) -> ItemFootprint | None:
    """One stock interactive prefab as the body it fills.

    The prefab's yaw is not its heading: every family is authored facing its
    own way at yaw 0 (``blueprint.catalogue``'s measured ``*_FRONT_ZERO``
    table), so the world heading is the entity's yaw plus its family's, and
    the body is that heading's box.
    """
    from ..blueprint.catalogue import (
        MYSTERY_BOX_FRONT_ZERO,
        PACK_A_PUNCH_FRONT_ZERO,
        PERK_FRONT_ZERO,
        POWER_SWITCH_FRONT_ZERO,
        WALL_WEAPON_FRONT_ZERO,
    )
    from ..blueprint.reach import BASE_SLACK, BODIES

    model = (entity.value("model") or "").strip()
    name = model.rsplit("/", 1)[-1]
    family = next((row for word, row in PREFAB_FAMILIES if word in name), None)
    if family is None:
        return None
    origin = _numbers(entity.value("origin"), 3)
    if origin is None:
        return None
    zero = {
        "machine": PERK_FRONT_ZERO,
        "pack_a_punch": PACK_A_PUNCH_FRONT_ZERO,
        "mystery_box": MYSTERY_BOX_FRONT_ZERO,
        "power_switch": POWER_SWITCH_FRONT_ZERO,
        "wall_weapon": WALL_WEAPON_FRONT_ZERO,
    }[family]
    angles = _numbers(entity.value("angles"), 3) or (0.0, 0.0, 0.0)
    heading = (angles[1] + zero.world_yaw) % 360.0
    body = BODIES[family]
    centre = rotate((body.front - body.back) / 2.0, 0.0, heading)
    poly = Poly2.box(
        origin[0] + centre[0], origin[1] + centre[1],
        (body.front + body.back) / 2.0, body.half_width, heading,
    )
    return ItemFootprint(
        name.removesuffix(".map"), family.replace("_", " "),
        poly, origin[2] - BASE_SLACK, origin[2] + body.height,
    )


def drop_unsupported_dressing(blueprint, *, prefixes: Sequence[str] = ("dress_", "dense_"),
                              contains: Sequence[str] = (), overlaps: bool = False) -> int:
    """Remove set dressing the support check (``Z44``) would flag, and say how many.

    Dressing is laid in passes: a later pass (a vignette's blanket, a fallen
    figure) can land over props an earlier pass stood on the ground, and a
    piece meant for a shelf can end up where the shelf is not.  Each of those
    props is a ``Z44`` finding.  For decoration in the scatters named by
    *prefixes* the fix is always the same -- the piece goes -- so it is done
    here once, after the last dressing pass, instead of in each recipe.
    Interactive and structural props are never in those scatters.  A scatter
    whose id contains one of *contains* counts as dressing too; with
    *overlaps*, a decoration piece standing mostly inside another solid one
    goes as well.
    """
    from ..blueprint.elements import PropScatter

    layout = layout_from_blueprint(blueprint)
    faults = _support_faults(layout) + (_overlap_faults(layout) if overlaps else [])
    bad = {prop.ident for prop, _detail in faults if prop.ident}
    if not bad:
        return 0
    dropped = 0
    for scatter in blueprint.elements(PropScatter):
        if not (scatter.id.startswith(tuple(prefixes))
                or any(part in scatter.id for part in contains)):
            continue
        keep = [prop for prop in scatter.props if prop.id not in bad]
        dropped += len(scatter.props) - len(keep)
        scatter.props = keep
    return dropped
