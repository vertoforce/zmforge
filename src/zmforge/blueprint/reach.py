"""Standing room: what an interactive item occupies, and what has to be empty.

An item you cannot reach is an item that does not exist.  Put a wall buy at
``(200, -560)`` and a perk machine at ``(200, -536)`` on the same wall, facing
the same way, and the machine stands in front of the buy and the buy cannot
be bought.  Nothing says so if every check asks only whether
the buy faced a wall, whether it had a floor, whether its module was loaded,
and all of them pass, because none of them asks about the *other*
interactive item.

This module answers that question, and it answers it in one place so that
:mod:`zmforge.blueprint.model` can refuse the placement, the prop placer can
treat the same volumes as no-placement zones, and
:func:`zmforge.verify.model.check_blueprint` can re-derive them from a
finished map (``Z42``) for maps this package did not generate.

Three volumes per item
----------------------

**Body** -- the item itself, the space its own model and clip fill.

**Apron** -- the space a player stands in to use it.  A body with no apron is
half a rule: two machines 8 units apart do not interpenetrate and still
cannot both be bought.  The apron is the item's own width plus
:data:`APRON_SIDE` on each side, extended :data:`APRON_DEPTH` in front of the
body -- :data:`APRON_DEPTH_STAND_BACK` for the mystery box and the
pack-a-punch, which are used from further away because they hand something
over rather than plugging it straight into you.  This is the volume a prop
placer is handed, because a prop anywhere in it crowds the buy.

**Stand** -- the strict core of the apron: the item's own width by
:data:`STAND_DEPTH` in front of its face.  This is the volume a *placement*
is refused for, because an item with nothing standing here can still be
bought and an item with something standing here cannot.

What counts as a clash
----------------------

Refused (``BLOCKING``):

* body against body -- the two items are drawn through each other;
* a standing body in front of a wall buy's chalk -- the drawing and the use
  prompt are both behind something;
* a standing body in another item's stand box -- there is nowhere to stand.

Reported and not refused (``"crowded"``):

* a standing body inside another item's apron but outside its stand box --
  the item is tight to get at and can still be bought.

**Apron against apron is not a clash** and is deliberately allowed.  Shared
standing room is what a well-laid corner looks like: a player stands in one
spot and buys the machine and the wall buy beside it without moving.  What
breaks a buy is a *body* in the way, not another person's elbow room.

Where the numbers come from
---------------------------

Measured off the stock prefabs themselves, in
``_prefabs/zm/zm_core/`` in the mod tools install, by reading each prefab's
own brushes with :func:`zmforge.mapsource.reader.parse_map_text`.  The ones
that could not be measured that way say so on their own row: a perk machine's
prefab is four ``script_struct`` entities and some lights, with no brush in
it at all, so its body is read off the three ``attack_spot`` structs the
zombies use instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..spatial import Axis, Facing, Point, Span

__all__ = [
    "APRON_SIDE",
    "APRON_DEPTH",
    "APRON_DEPTH_STAND_BACK",
    "APRON_HEIGHT",
    "Body",
    "BODIES",
    "Keep",
    "Clash",
    "keep_of",
    "keeps_of",
    "clashes",
    "BLOCKING",
    "STAND_DEPTH",
    "first_clash",
    "zone_rectangles",
    "zone_hit",
]

#: How far to each side of an item the standing room reaches, beyond the
#: item's own width.  A player hull is 30 units across
#: (``verify.model.PLAYER_HULL_WIDTH``), so 32 a side is one body plus a
#: little: enough to stand square in front of the item's edge rather than
#: having to line up on its centre.
APRON_SIDE = 32.0

#: How deep the standing room in front of a wall buy, a perk machine or the
#: power switch is.  96 is a player hull's width three times over, and it is
#: the distance that perk machine would have to move to stop covering the
#: wall buy.
APRON_DEPTH = 96.0

#: The mystery box and the pack-a-punch are used from further back: both
#: play an animation that hands a weapon out over their front face, and both
#: are approached rather than leaned on.
APRON_DEPTH_STAND_BACK = 128.0

#: The apron is a standing player, so it is a player tall.  Matching
#: ``verify.model.PLAYER_HULL_HEIGHT``; repeated rather than imported because
#: the blueprint may not import the checker.
APRON_HEIGHT = 72.0

#: How far below an item's own origin its volumes start.  A machine's origin
#: sits on the floor and a wall buy's a few units under the chalk, and a
#: little slack below both keeps a storey's items in one vertical band
#: without ever reaching the storey under it -- the floors of this
#: generator's maps are 272 units apart at the closest.
BASE_SLACK = 8.0


@dataclass(frozen=True, slots=True)
class Body:
    """One kind of interactive item's own box, in its own local frame.

    ``half_width`` is across its face, ``front`` and ``back`` are how far it
    reaches the way it faces and the way it does not, and ``height`` is up
    from its origin.  ``apron`` is how deep the standing room in front of it
    has to be.
    """

    half_width: float
    front: float
    back: float
    height: float
    apron: float
    source: str
    #: Does this body stand **in the room**?  A perk machine, the box, the
    #: pack-a-punch and the power switch do: they are objects on a floor and
    #: something in front of them is something in the way.  A wall buy does
    #: not -- its mount brush is 8 units *into* the wall behind the chalk
    #: plane, so a buy beside a doorway obstructs nothing, and a
    #: finished map has many buys mounted exactly there on purpose.  Only a standing
    #: body can block another item; a wall-mounted one can only be blocked.
    standing: bool = True


#: One row per interactive family.  ``source`` is the evidence, because a
#: threshold with no source behind it is the thing that gets quietly widened
#: the first time it is inconvenient.
BODIES: dict[str, Body] = {
    # vending_juggernaut_struct.map and its six siblings carry no brush at
    # all.  What they do carry is three `attack_spot` structs -- where a
    # zombie stands to hit a player at the machine -- at x = -30, 0 and +30,
    # all on the machine's front (-Y at yaw 0), between 19 and 38 units out.
    # So the machine is about 60 across, and the nearest spot a body fits is
    # about 27 in front of the origin.  vending_revive_struct.map is the one
    # with a brush, a `shadowcaster` proxy at x in [-19.25, 18.75] and
    # y in [12, 17]: 38 across and 17 behind the origin.  64 by 24-in-front,
    # 24-behind is those two rounded out, and the 24 agrees with the
    # MACHINE_BODY_DEPTH the clearance check has used since it was written.
    "machine": Body(32.0, 24.0, 24.0, 72.0, APRON_DEPTH,
                    "attack_spot structs + the revive shadowcaster, measured"),
    # vending_weapon_upgrade_spawnable.map carries no brush either, and no
    # attack spots: it is one `zbarrier_zmcore_packapunch` at (2.5, 5, -7.5),
    # five lights and two `info_null`s at x = -63 and -59, which is what
    # PACK_A_PUNCH_FRONT_ZERO is read from.  The entities inside it span
    # x -66.6 to 14.7, so the machine is about 80 deep along the axis it
    # faces; nothing in the file gives its width, and a perk machine's 64 is
    # the closest thing to a measurement there is.  **[width inherited,
    # unverified]**
    "pack_a_punch": Body(32.0, 68.0, 16.0, 96.0, APRON_DEPTH_STAND_BACK,
                         "prefab entity spread along its facing axis, "
                         "measured; width from the perk machines"),
    # buyable_magic_box_start.map's own clip brush: x in [-52, 49],
    # y in [-16, 18], z in [-10, 145], with the front at +Y
    # (MYSTERY_BOX_FRONT_ZERO).  The plank on top runs x in [-46, 48].
    "mystery_box": Body(52.0, 18.0, 16.0, 145.0, APRON_DEPTH_STAND_BACK,
                        "buyable_magic_box_start.map clip brush, measured"),
    # power_switch.map's clip brush: x in [-20, 20], y in [-8, 7],
    # z in [-1, 94], front at -Y (POWER_SWITCH_FRONT_ZERO).  Its own
    # trigger_use stands off that face at y in [-24, -5], which is the
    # measurement that says which way it is used from.
    "power_switch": Body(20.0, 8.0, 7.0, 94.0, APRON_DEPTH,
                         "power_switch.map clip and trigger brushes, measured"),
    # The thirteen spawnable_weapon_*.map prefabs.  Each is a `traverse`
    # mount brush behind the origin plane -- the widest is shotgun_pump's
    # x in [-19, 20] by y in [-8, -1] by z in [0, 56] -- and a chalk patch on
    # the plane itself, the widest of those being ar_standard's and
    # smg_versatile's x in [-22, 24] by z in [40, 64].  So: 48 across, 8 deep
    # into the wall, nothing in front of the plane, and 66 up from the origin
    # to clear the tallest chalk.
    # Der Wunderfizz has no measured box.  Its only model,
    # p7_zm_vending_wonder (catalogue.WUNDERFIZZ_MODEL), is not among the
    # stock models MODEL_BOX was read from (none of them is a "wonder"
    # model), the install ships no Wunderfizz prefab,
    # and the zbarrier it is spelled as (zmcore_packapunch, zbarriers.gdt)
    # has `"collisionModel" ""`.  The one size the stock script records is
    # its use trigger -- 70 wide, 30 high, 40 long, stood 40 units off the
    # machine's *right* (_zm_perk_random.gsc:154-157) -- and that is where a
    # player stands, not the machine.  So the body is the perk machine's,
    # the same borrowing verify.approach.UNMEASURED_BOX makes for the perk
    # models placed as scenery.  **[inherited from "machine", unverified]**
    "wunderfizz": Body(32.0, 24.0, 24.0, 72.0, APRON_DEPTH,
                       "no measured box; the perk machine's body, inherited"),
    "wall_weapon": Body(24.0, 0.0, 8.0, 66.0, APRON_DEPTH,
                        "the 13 spawnable_weapon prefabs' mount brushes and "
                        "chalk patches, measured",
                        standing=False),
}


#: The depth of floor directly in front of an item that has to be empty --
#: the place the player's own body goes while the prompt is up.  A player
#: hull is 30 units across (``verify.model.PLAYER_HULL_WIDTH``) and the
#: navmesh generator's own corridor width is 31 (``N2``), so 32 is one body
#: and nothing spare.
#:
#: WHY THIS AND NOT THE WHOLE APRON.  The apron is 96 or 128 deep because
#: that is how far back a player may stand; what a *blocked* item means is
#: that there is nowhere to stand at all.  Refusing anything that reaches
#: into the full apron refuses placements that are usable: a perk machine
#: in a small room can start 94 units in front of a wall buy on the
#: opposite wall, two units inside that buy's 96, and the buy still has
#: room to stand at.  Such placements are reported as crowding (a ``Z42``
#: warning) rather than refused.
STAND_DEPTH = 32.0


@dataclass(frozen=True, slots=True)
class Keep:
    """One interactive item's volumes, in world space."""

    element_id: str
    what: str
    #: The item itself: what its model and clip fill.
    body: Span
    #: The generous version of the standing room -- the item's width plus
    #: :data:`APRON_SIDE` a side, :data:`APRON_DEPTH` (or
    #: :data:`APRON_DEPTH_STAND_BACK`) in front.  This is the no-placement
    #: zone the prop placer is given: a prop anywhere in here crowds the buy.
    #: One apron for a machine, a buy or a box; two for a door, which is
    #: walked through from both sides.
    aprons: tuple[Span, ...]
    #: The strict version, and the one a placement is refused for: the item's
    #: own width by :data:`STAND_DEPTH` in front of its face.  Another
    #: interactive's body in here means there is nowhere to stand to use this
    #: one.
    stands: tuple[Span, ...] = ()
    #: For a wall buy, the thin slab in front of its chalk drawing; ``None``
    #: for everything else.  Anything whose *body* lands in here has put
    #: itself between the player and the drawing, as a perk machine
    #: standing in front of a wall buy does.
    face: Span | None = None
    #: Does this item's body stand in the room and so get in other items'
    #: way?  See :attr:`Body.standing`; a door's leaf is ``False`` for the
    #: same reason a wall buy's mount is -- it is part of the wall, and once
    #: bought it is not there at all.
    standing: bool = True

    @property
    def zones(self) -> tuple[Span, ...]:
        """Body and aprons together: the whole volume to keep clear."""
        return (self.body,) + self.aprons


#: The clash kinds that refuse a placement, worst first.  ``"crowded"`` is
#: the fourth kind and is not in here: it is reported and not refused.
BLOCKING = ("body", "face", "stand")


@dataclass(frozen=True, slots=True)
class Clash:
    """Two interactives that do not leave each other enough room."""

    first: Keep
    second: Keep
    #: ``"body"``, ``"face"``, ``"stand"`` or ``"crowded"`` -- which question
    #: this pair failed.  The first three are blocking; see :data:`BLOCKING`.
    kind: str
    overlap: Span

    @property
    def blocks(self) -> bool:
        """Is this the kind that makes an item unusable?"""
        return self.kind in BLOCKING

    def message(self) -> str:
        size = self.overlap.size
        where = (
            f"{size.x:g} x {size.y:g} x {size.z:g} units about "
            f"({self.overlap.centre.x:g}, {self.overlap.centre.y:g}, "
            f"{self.overlap.centre.z:g})"
        )
        if self.kind == "face":
            return (
                f"{self.second.what} ({self.second.element_id}) stands in front of "
                f"the chalk drawing on {self.first.what} "
                f"({self.first.element_id}), covering {where} of it; the buy "
                "cannot be seen or bought"
            )
        if self.kind == "body":
            return (
                f"{self.first.what} ({self.first.element_id}) and "
                f"{self.second.what} ({self.second.element_id}) are drawn through "
                f"each other: their own boxes share {where}"
            )
        if self.kind == "stand":
            return (
                f"{self.second.what} ({self.second.element_id}) fills the "
                f"{STAND_DEPTH:g} units of floor in front of {self.first.what} "
                f"({self.first.element_id}) -- {where} of it -- so there is "
                "nowhere to stand to use it"
            )
        return (
            f"{self.second.what} ({self.second.element_id}) reaches {where} into "
            f"the standing room of {self.first.what} ({self.first.element_id}); "
            "the item can still be used, from further to one side"
        )


def _intersection(a: Span, b: Span) -> Span | None:
    """The box two boxes share, or ``None`` when they only touch."""
    lows = [max(a.mins[i], b.mins[i]) for i in range(3)]
    highs = [min(a.maxs[i], b.maxs[i]) for i in range(3)]
    if any(highs[i] - lows[i] <= 0.0 for i in range(3)):
        return None
    return Span.flat_ok(Point(*lows), Point(*highs))


def _oriented(
    origin: Point, facing: Facing, body: Body, *, height: float | None = None,
    front: float | None = None, back: float | None = None,
    half_width: float | None = None,
) -> Span:
    """A local box turned onto a compass heading and put at ``origin``.

    ``front`` and ``back`` are along the heading, ``half_width`` across it,
    and the box runs from :data:`BASE_SLACK` under the origin to ``height``
    above it.  Left ``None``, each takes the item family's own measurement.
    """
    half = body.half_width if half_width is None else half_width
    ahead = body.front if front is None else front
    behind = body.back if back is None else back
    tall = body.height if height is None else height
    step = facing.step
    across = facing.cross_axis
    near = origin + step.scaled(-behind)
    far = origin + step.scaled(ahead)
    low = Point(min(near.x, far.x), min(near.y, far.y), origin.z - BASE_SLACK)
    high = Point(max(near.x, far.x), max(near.y, far.y), origin.z + tall)
    low = low.with_axis(across, low[across.index] - half)
    high = high.with_axis(across, high[across.index] + half)
    return Span.flat_ok(low, high)


def _apron(origin: Point, facing: Facing, body: Body) -> Span:
    """The generous standing room in front of one item."""
    return _oriented(
        origin,
        facing,
        body,
        front=body.front + body.apron,
        back=-body.front,
        half_width=body.half_width + APRON_SIDE,
        height=APRON_HEIGHT,
    )


def _stand(origin: Point, facing: Facing, body: Body) -> Span:
    """The floor a player's own body goes on to use this item."""
    return _oriented(
        origin,
        facing,
        body,
        front=body.front + STAND_DEPTH,
        back=-body.front,
        height=APRON_HEIGHT,
    )


#: Where a wall buy's chalk drawing sits above its own origin.  Measured
#: over the thirteen ``spawnable_weapon_*.map`` patches: the
#: lowest starts at z = 40 (``ar_standard``, ``smg_versatile``) and the
#: highest ends at z = 66 (``shotgun_pump``).
CHALK_LOW = 40.0
CHALK_HIGH = 66.0

#: How far in front of the chalk has to be empty for the drawing to be seen
#: and the prompt reached.  A player hull is 30 across, so 24 is less than
#: one body: this is the "something is parked against the wall over it"
#: test, not the "somewhere to stand" test, which is the apron's job.
FACE_CLEAR = 24.0


def _chalk_face(origin: Point, facing: Facing, body: Body) -> Span:
    """The slab immediately in front of a wall buy's drawing."""
    step = facing.step
    across = facing.cross_axis
    near = origin
    far = origin + step.scaled(FACE_CLEAR)
    low = Point(min(near.x, far.x), min(near.y, far.y), origin.z + CHALK_LOW)
    high = Point(max(near.x, far.x), max(near.y, far.y), origin.z + CHALK_HIGH)
    low = low.with_axis(across, low[across.index] - body.half_width)
    high = high.with_axis(across, high[across.index] + body.half_width)
    return Span.flat_ok(low, high)


def _door_keeps(door) -> Keep:
    """A door's leaf, and the standing room on both of its faces.

    The leaf is the whole opening box; the apron is a player's depth off each
    of its two large faces, widened by :data:`APRON_SIDE` so that an item
    hard against the door jamb is inside it.

    The leaf itself is **not** a standing body.  It fills the hole in the
    wall while the door is shut, and a bought door drops out of the world
    entirely (:attr:`~zmforge.blueprint.elements.Door.travel`), so nothing
    the player has to reach is ever behind it.  What matters is the lane:
    both aprons have to stay clear of the things that *do* stand in a room.
    """
    box = door.box
    size = box.size
    thin = min(
        (Axis.X, Axis.Y), key=lambda axis: size[axis.index]
    )
    wide = Axis.Y if thin is Axis.X else Axis.X
    grown = box.grown_on(wide, APRON_SIDE)
    low = grown.mins[thin.index]
    high = grown.maxs[thin.index]
    aprons = (
        grown.slice_on(thin, low - APRON_DEPTH, low),
        grown.slice_on(thin, high, high + APRON_DEPTH),
    )
    # The strict lane is the doorway's own width, not the widened one: what
    # stops a door being walked through is something *in* it.
    near = box.mins[thin.index]
    far = box.maxs[thin.index]
    stands = (
        box.slice_on(thin, near - STAND_DEPTH, near),
        box.slice_on(thin, far, far + STAND_DEPTH),
    )
    return Keep(door.id, f"the {door.flag or door.id} door", box, aprons,
                stands, standing=False)


def keep_of(element) -> Keep | None:
    """The volumes one element keeps clear, or ``None`` if it keeps none.

    Everything with a use prompt is in here and nothing else is.  A prefab
    placed for scenery is not: it carries no mechanic, which is the whole
    point of :meth:`~zmforge.blueprint.model.Blueprint.place_prefab`.
    """
    from .elements import (
        Door, Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz,
    )

    if isinstance(element, Door):
        return _door_keeps(element)
    if isinstance(element, Machine):
        pap = element.perk.slug == "pack_a_punch"
        body = BODIES["pack_a_punch" if pap else "machine"]
        what = element.perk.slug
    elif isinstance(element, MysteryBox):
        body = BODIES["mystery_box"]
        what = f"the {element.chest_name} mystery box"
    elif isinstance(element, Wunderfizz):
        body = BODIES["wunderfizz"]
        what = "Der Wunderfizz"
    elif isinstance(element, PowerSwitch):
        body = BODIES["power_switch"]
        what = "the power switch"
    elif isinstance(element, WallWeapon):
        body = BODIES["wall_weapon"]
        what = f"the {element.slug} wall buy"
    else:
        return None
    origin = Point.of(element.position)
    facing = Facing.of(element.facing)
    face = None
    if isinstance(element, WallWeapon):
        face = _chalk_face(origin, facing, body)
    return Keep(element.id, what, _oriented(origin, facing, body),
                (_apron(origin, facing, body),),
                (_stand(origin, facing, body),), face, body.standing)


def keeps_of(elements) -> list[Keep]:
    """Every keep-clear volume in an iterable of elements, in order."""
    found = []
    for element in elements:
        keep = keep_of(element)
        if keep is not None:
            found.append(keep)
    return found


def _pair_clash(first: Keep, second: Keep) -> Clash | None:
    """The worst thing wrong between two items, or ``None``.

    Order of severity, and the order the messages are worth reading in: two
    bodies through each other, then a body over a wall buy's chalk, then a
    body on the floor the item is used from, then a body merely inside the
    generous apron -- the last of which is crowding and not a blockage.

    Two boxes in one place is asked of every pair.  Everything after it is
    about *standing room*, and there only a **standing** body -- a machine,
    the box, the pack-a-punch, the power switch -- can be the thing in the
    way: a wall buy's mount and a door's leaf are part of the wall they are
    cut into, so for those questions they are asked whether they are blocked
    and never whether they block.

    Apron against apron is not asked at all.  Shared standing room is what a
    well-laid corner looks like: one spot to stand in, two things to buy
    without moving.
    """
    shared = _intersection(first.body, second.body)
    if shared is not None:
        # Asked of every pair, standing or not.  Two wall buys on one patch
        # of wall draw their chalk through each other, and a buy inside a
        # door's leaf is mounted on a door: neither is a body standing in a
        # room, and both are still two things in one place.
        return Clash(first, second, "body", shared)
    for owner, other in ((first, second), (second, first)):
        if owner.face is None or not other.standing:
            continue
        covered = _intersection(owner.face, other.body)
        if covered is not None:
            return Clash(owner, other, "face", covered)
    for owner, other in ((first, second), (second, first)):
        if not other.standing:
            continue
        for stand in owner.stands:
            blocked = _intersection(stand, other.body)
            if blocked is not None:
                return Clash(owner, other, "stand", blocked)
    for owner, other in ((first, second), (second, first)):
        if not other.standing:
            continue
        for apron in owner.aprons:
            crowded = _intersection(apron, other.body)
            if crowded is not None:
                return Clash(owner, other, "crowded", crowded)
    return None


def clashes(keeps) -> list[Clash]:
    """Every pair of interactives that does not leave the other room enough.

    Blocking and crowding both, at most one per pair and the worst one; read
    :attr:`Clash.blocks` to tell them apart.
    """
    found = []
    keeps = list(keeps)
    for index, first in enumerate(keeps):
        for second in keeps[index + 1:]:
            clash = _pair_clash(first, second)
            if clash is not None:
                found.append(clash)
    return found


def first_clash(candidate: Keep, placed) -> Clash | None:
    """The first placed item ``candidate`` blocks, or is blocked by, or ``None``.

    This is the placement-time question, and it is asked with the candidate
    first so that its message reads the way the caller thinks about it: the
    thing being placed, against the thing already there.  Crowding is not
    returned: a placement is refused for a blockage and nothing else
    (:data:`BLOCKING`).
    """
    for keep in placed:
        clash = _pair_clash(candidate, keep)
        if clash is not None and clash.blocks:
            return clash
    return None


def zone_rectangles(keeps) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """The union of every body and apron, as ``x0 y0 x1 y1 z0 z1`` boxes.

    The shape a prop placer wants: plan rectangles with the storey they
    belong to attached, the same six numbers
    ``zmforge.recipes.props._stair_zones`` already returns, so that a placer
    filters them the way it already filters staircases.
    """
    boxes = []
    for keep in keeps:
        for zone in keep.zones:
            boxes.append(
                (zone.mins.x, zone.mins.y, zone.maxs.x, zone.maxs.y,
                 zone.mins.z, zone.maxs.z)
            )
    return tuple(boxes)


#: How far below a zone a prop's resting height may be and still count as
#: standing in it.  A prop's origin is its base, and a zone starts
#: :data:`BASE_SLACK` under the item's origin, so a prop on the same floor is
#: never more than a few units under the zone's bottom; 16 is the generator's
#: own floor thickness and a storey is 272.
ZONE_FLOOR_SLACK = 16.0


def zone_hit(
    zones, x: float, y: float, z: float, half_x: float = 0.0, half_y: float = 0.0
) -> bool:
    """Does a footprint at ``(x, y, z)`` stand inside one of ``zones``?

    ``half_x``/``half_y`` are the footprint's own half extents in plan, so a
    long prop whose centre is beside a machine but whose end is over its
    apron answers ``True``.
    """
    for x0, y0, x1, y1, z0, z1 in zones:
        if not (z0 - ZONE_FLOOR_SLACK <= z <= z1):
            continue
        if x + half_x > x0 and x - half_x < x1 and y + half_y > y0 and y - half_y < y1:
            return True
    return False
