"""The blueprint's element types.

An element is one thing a mapper added: a room, a zone, a door, a light.  It
holds the *decision* (bounds, price, facing), never the text that will be
written for it — ``emit`` derives that.  Handles returned by the blueprint's
operations are the element objects themselves, so ``room.interior`` and
``door.flag`` are reachable without a lookup, and the spec's ``RoomRef`` /
``ZoneRef`` / ``DoorRef`` names are aliases at the bottom of this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Mapping, Sequence

from ..materials import CAULK, FaceMaterials, Material
from ..solids.forms import Solid
from ..solids.layout import Aperture, RoomShell, SkyCage
from ..spatial import Angles, Axis, Facing, Point, Side, Span

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..mapsource.document import Document
    from ..surfaces.ground import TerrainRecord
    from ..surfaces.patches import ColumnRun, PatchGrid
    from .catalogue import PerkKind

__all__ = [
    "Element",
    "AmbientFx",
    "Traversal",
    "AuthoredForm",
    "Massing",
    "SEALED_OPENING",
    "STAIR_CLIP",
    "FLOATS_ON_PURPOSE",
    "RoomMaterials",
    "Room",
    "Yard",
    "Enclosure",
    "Terrain",
    "PlayerStart",
    "Zone",
    "Spawn",
    "Door",
    "Machine",
    "WallWeapon",
    "MysteryBox",
    "Wunderfizz",
    "PowerSwitch",
    "Lamp",
    "Window",
    "Prefab",
    "PropScatter",
    "ImportedMap",
    "RoomRef",
    "ZoneRef",
    "DoorRef",
    "YardRef",
    "SolidRef",
    "TerrainRef",
    "WindowRef",
    "MachineRef",
    "SpawnRef",
    "EnclosureRef",
]

#: The layer real files use for map geometry.  Layers are cosmetic; the
#: compiler ignores them.
DEFAULT_LAYER = "The Map"

#: :attr:`Massing.note` of a pane filling an opening, written by
#: :meth:`~zmforge.blueprint.model.Blueprint.seal_opening`.  It is a note and
#: not a subclass because the geometry is an ordinary world brush; the note is
#: what lets ``verify`` tell a sealed hole apart from decorative massing and
#: object to a door hung in one.
SEALED_OPENING = "sealed opening"

#: :attr:`Massing.note` of the smooth clip ramp laid over a flight of steps by
#: :meth:`~zmforge.blueprint.model.Blueprint.add_steps`.  It is the surface a
#: zombie's capsule actually slides up -- bare treads present a vertical riser
#: per step and the walkers stall on them, which is why every staircase in
#: Treyarch's own source is tread models under one sloped clip brush.  The
#: note exists so the checkers can tell this brush from ordinary massing: it
#: overlaps the treads on purpose, and a clip ramp is not an obstacle to the
#: standing-room flood the way a wall is.
STAIR_CLIP = "stair clip"

#: :attr:`Massing.note` of a solid that stands on nothing and is meant to.
#: ``Z43`` reports world brushwork with no floor under it, nothing over it and
#: nothing beside it, because that is what a slab the arithmetic put in the
#: wrong place looks like; a map that wants an object hanging in mid-air --
#: a lamp's chain and hook plate, say -- says so here, once, on the geometry, the same way ``reachable`` is
#: how it says nobody can get onto something.
FLOATS_ON_PURPOSE = "floats on purpose"


@dataclass
class Element:
    """Base class: a stable id and the Radiant layer it is filed under."""

    id: str
    layer: str = DEFAULT_LAYER

    @property
    def kind(self) -> str:
        return type(self).__name__


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AuthoredForm:
    """What a massing was *asked* for, kept beside the solids it became.

    :meth:`~zmforge.blueprint.model.Blueprint.add_block` and its neighbours
    lower their arguments to explicit :class:`~zmforge.solids.forms.Solid`
    faces the moment they are called, so a committed model holds six planes
    per box and nothing else: the authored box, the material it was given,
    the heading a ramp rises toward and the step count of a flight are all
    gone.  A box can be read back out of six axis-aligned planes; a flight of
    stairs cannot -- it is *n* loose boxes that may or may not be one flight
    -- and a ramp's five faces do not say which way it was drawn.

    The shared map document (:mod:`zmforge.mapdoc`) needs exactly the
    authored form: the editor draws one `blocks` entry, one `ramps` entry with
    a direction, one `stairs` entry with a step count, and would otherwise
    have to receive 140 massings as some three thousand face triples.  So the
    form is *kept* rather than recovered.  It is a record of the call, not a
    second copy of the geometry: nothing downstream of the call reads it, and
    the solids remain the only thing that is written to the ``.map``.

    ``form`` is ``block`` (a box, from ``add_block`` or ``add_slab``),
    ``steps`` (a flight), ``ramp`` (a wedge) or ``pane`` (an opening filled by
    :meth:`~zmforge.blueprint.model.Blueprint.seal_opening`).
    """

    form: str
    box: Span | None = None
    materials: FaceMaterials | None = None
    contents: tuple[str, ...] = ()
    #: A ramp rises toward this heading; a flight of stairs climbs toward it.
    toward: Facing | None = None
    #: A flight only: the foot of the first step, and the flight's shape.
    base: Point | None = None
    steps: int = 0
    step_depth: float = 0.0
    step_rise: float = 0.0
    width: float = 0.0


@dataclass
class Massing(Element):
    """A group of world solids with no gameplay meaning of its own.

    Two flags say what a *player* can do with the group, because nothing else
    in the model can work it out.  ``walkable`` means each solid's top face is
    a surface a player stands on, so a floor slab, a step or a bridge deck
    counts and a wall, a pillar or a ramp does not -- a ramp's top is sloped
    and a box top is the only shape :meth:`Blueprint.ground_under` can answer
    for.  ``reachable`` says whether any route leads onto it; ``False`` is how
    a map declares a ledge or a balcony deliberately left with no way up, and
    ``verify`` reports the machines standing on one instead of guessing.
    """

    solids: list[Solid] = field(default_factory=list)
    note: str = ""
    walkable: bool = False
    reachable: bool = True
    #: The call this group came from, before it was lowered to ``solids``.
    #: ``None`` for a group nothing authored -- an adopted foreign map, or a
    #: caller that built :class:`Massing` itself.
    authored: AuthoredForm | None = None
    #: Non-blank writes the group as a ``script_brushmodel`` entity with this
    #: ``targetname`` instead of world brushes, so a script can find it
    #: (``GetEnt( name, "targetname" )``) and hide or delete it.  Several
    #: groups with one name become one entity.  A brush entity does not seal
    #: or split the world, so these solids stay out of the structural list.
    targetname: str = ""

    @property
    def bounds(self) -> Span:
        """The box hull of every face point in the group."""
        points = [
            point
            for solid in self.solids
            for face in solid.faces
            for point in face.points
        ]
        if not points:
            raise ValueError(f"massing {self.id!r} has no solids, so it has no bounds")
        return Span.flat_ok(
            Point(
                min(p.x for p in points),
                min(p.y for p in points),
                min(p.z for p in points),
            ),
            Point(
                max(p.x for p in points),
                max(p.y for p in points),
                max(p.z for p in points),
            ),
        )


@dataclass(frozen=True, slots=True)
class RoomMaterials:
    """What a room's three surface families are made of.

    ``sides`` overrides one wall, and only a wall: a room whose four walls are
    all the same material is the common case and the default, but the north
    wall of a bar is tiled and the other three are not, and without this the
    only way to say so is to stop using ``add_room`` and lay the shell out by
    hand.  A floor or ceiling override is refused rather than ignored, because
    ``floor`` and ``ceiling`` already say that and two ways to say one thing
    disagree eventually.
    """

    wall: Material
    floor: Material
    ceiling: Material
    hidden: Material = CAULK
    sides: Mapping[Side, Material] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for side in self.sides:
            if not side.is_horizontal:
                raise ValueError(
                    f"{side.name.lower()} is the floor or the ceiling, which has its own "
                    "material; sides overrides a wall"
                )

    def for_side(self, side: Side) -> Material:
        if side is Side.BOTTOM:
            return self.floor
        if side is Side.TOP:
            return self.ceiling
        return self.sides.get(side, self.wall)

    def hull_faces(self, piece_side: Side) -> FaceMaterials:
        """Hull rule of spec 2.2: art on the face looking in, caulk elsewhere."""
        return FaceMaterials.only_visible_on(
            piece_side.opposite, self.for_side(piece_side), self.hidden
        )

    def aperture_faces(self, side: Side) -> FaceMaterials:
        """Jambs, sill and lintel are visible on all six faces (spec 2.3)."""
        return FaceMaterials.uniform(self.for_side(side))

    def names(self) -> set[str]:
        return ({self.wall.name, self.floor.name, self.ceiling.name, self.hidden.name}
                | {material.name for material in self.sides.values()})


@dataclass
class Room(Element):
    """A sealed (or open-air) box with wall thickness and optional openings.

    ``reachable`` is the same declaration :class:`Massing` makes: ``False``
    says no route leads into this room, so it is a room to be seen into
    through a sealed opening and never stood in.  Nothing in the model can
    work that out -- a room with no door yet may be the room the next door
    opens onto -- and the checks that ask "can a player be here?" (a zone
    volume over it, playable-area coverage) need the answer, so the map says
    it.
    """

    outer: Span = None  # type: ignore[assignment]
    thickness: float = 16.0
    roofed: bool = True
    materials: RoomMaterials = None  # type: ignore[assignment]
    shell: RoomShell = None  # type: ignore[assignment]
    apertures: list[Aperture] = field(default_factory=list)
    aperture_boxes: list[Span] = field(default_factory=list)
    reachable: bool = True
    #: Open to the sky and lit by the map's sun, so it gets no fill lamps
    #: (:meth:`zmforge.blueprint.model.Blueprint.light_rooms`) and Z11 does not
    #: ask it for any.  Only a room with ``roofed=False`` may say so.  Why:
    #: ``zm_dmv``'s car park, a 1200 x 1400 lot under ``default_day``, was
    #: filled with 60 omni lamps of radius 512 at the map's full exposure on top
    #: of the sun, and played far too bright outside while every roofed room
    #: looked right.  ``mp_sector``, Treyarch's daylight map, has
    #: 24 omni lights in all, median radius 5 and none over 400.
    sunlit: bool = False

    @property
    def interior(self) -> Span:
        return self.shell.interior

    @property
    def floor_z(self) -> float:
        """World Z of the walkable floor surface."""
        return self.shell.floor_surface_z

    def opening(self, index: int) -> "Opening":
        return Opening(self, index, self.apertures[index], self.aperture_boxes[index])


@dataclass(frozen=True, slots=True)
class Opening:
    """A hole already cut in a room wall, ready for a door to fill it."""

    room: "Room"
    index: int
    aperture: Aperture
    box: Span

    @property
    def side(self) -> Side:
        return self.aperture.side

    @property
    def wall_axis(self):
        return self.side.axis


@dataclass
class Yard(Element):
    """A five-sided pocket outside a room wall, where barricade risers stand."""

    outer: Span = None  # type: ignore[assignment]
    attached: Side = Side.NORTH
    thickness: float = 16.0
    materials: RoomMaterials = None  # type: ignore[assignment]
    shell: RoomShell = None  # type: ignore[assignment]
    #: Holes through the far wall to the open air (``Blueprint.add_yard_vent``),
    #: subtracted from the shell when it is written.
    vents: list[Span] = field(default_factory=list)

    @property
    def interior(self) -> Span:
        return self.shell.interior

    @property
    def floor_z(self) -> float:
        return self.shell.floor_surface_z


@dataclass
class Enclosure(Element):
    """Sky shell plus the sun, umbra and fps-tool volumes.  One per map."""

    playable: Span | None = None
    gap: float = 128.0
    thickness: float = 32.0
    sun_preset: str = "default_day"
    #: Emit reflection probes.  On, because the mod tools' own new-map
    #: template ships one and a map with none has no indirect-lighting solve
    #: at all (see :mod:`zmforge.lighting`).  One box per room, sized to that
    #: room; :meth:`Blueprint.probe_boxes` is where the boxes come from.
    probe: bool = True
    grid_density: int = 32
    margin: float = 8.0
    cage: SkyCage | None = None  # resolved at commit time
    #: The map's air (:mod:`zmforge.atmosphere`): ``fog`` names a shipped fog
    #: asset and adds one ``volume_worldfog`` over the playable space;
    #: ``skybox`` overrides the worldspawn's ``skyboxmodel``.  ``None`` for
    #: both is the template's clear day, which is what every map had before.
    fog: str | None = None
    fog_time: float = 1.0
    skybox: str | None = None
    #: The fog you can see (:mod:`zmforge.atmosphere`, "lit fog"): a shipped
    #: ``litfog`` asset for one ``volume_litfog`` over the playable space, or
    #: ``None`` for none.
    lit_fog: str | None = None
    #: Denser pockets inside it: ``(box, lit fog asset)`` pairs, each its own
    #: nested ``volume_litfog`` (e.g. a crypt).
    lit_fog_pockets: tuple = ()
    #: Gloom (:mod:`zmforge.atmosphere`): a shipped grade for the worldspawn
    #: ``vcolor``/``bloom``, and an exposure pin in stops over the sun
    #: preset's ev.  ``None`` for both writes no key.
    grade: str | None = None
    exposure_stops: float | None = None


@dataclass
class Terrain(Element):
    """A heightfield realised either as patches or as column brushes."""

    record: "TerrainRecord" = None  # type: ignore[assignment]
    style: str = "mesh"
    material: Material = None  # type: ignore[assignment]
    chunk: int = 8
    lift: float = 2.0
    grids: list["PatchGrid"] = field(default_factory=list)
    runs: list["ColumnRun"] = field(default_factory=list)
    bands: list[tuple[float, Material]] = field(default_factory=list)
    texture_scale: float = 128.0


# --------------------------------------------------------------------------
# Gameplay
# --------------------------------------------------------------------------
#: Players the stock zombies framework places distinctly, and the count it
#: enforces.  ``zm::getfreespawnpoint`` hands player *n* the *n*-th
#: initial-spawn struct and everyone past the end of that array the first
#: one, so the spawn code itself caps nothing; the cap is
#: ``_zm.gsc:7067 player_too_many_players_check``, which freezes the players
#: and notifies ``end_game`` above four outside ``zgrief``/``zmeat``, and is
#: threaded on every spawn at ``_zm.gsc:1865``.  Four is what a stock game
#: seats, so it is the default.
STOCK_PLAYER_SLOTS = 4

#: Slots per row before the set starts a second row behind the first.  Four
#: keeps the stock set a single line, exactly as it was emitted before the
#: count became a parameter.
SLOTS_PER_ROW = 4


@dataclass
class PlayerStart(Element):
    """The respawn set and the per-slot initial spawns (spec 4.1).

    ``slots`` is how many players get a spawn point of their own.  A
    higher-player mod places player *n* on struct *n*, and on
    ``spawnpoints[ 0 ]`` once it runs out, so an eight-player game on a
    four-slot map stacks players five to eight on one point.  Extra slots
    cost a four-player game nothing -- the framework indexes into the array
    and never counts it.

    The structs are not the whole of the map side.  Above four they are useless on their own:
    ``_zm.gsc:7067 player_too_many_players_check`` freezes the players and
    ends the game on the fifth spawn.  Setting ``slots`` above
    :data:`STOCK_PLAYER_SLOTS` therefore also sets
    :attr:`ScriptPlan.lift_player_cap`, which emits the statement that turns
    that check off.
    """

    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.EAST
    spread: float = 32.0
    respawn_radius: float = 2000.0
    slots: int = STOCK_PLAYER_SLOTS
    #: Explicit per-slot points, one per slot, in slot order.  Empty (the
    #: default) lays the slots out round ``position`` as below.  Set, the
    #: slots may be anywhere -- one per sealed start hallway, say
    #: (:mod:`zmforge.script.splitstart`) -- and ``position`` is only where
    #: the respawn struct goes.
    points: tuple[Point, ...] = ()
    #: Zones no respawn group is laid in (:mod:`zmforge.blueprint.respawn`):
    #: a sealed start's hallways, where a respawn is what Z78 forbids.
    sealed_zones: tuple[str, ...] = ()

    def slot_positions(self) -> list[Point]:
        """One point per slot, in rows of :data:`SLOTS_PER_ROW`.

        Four slots are a single line across the heading, spaced ``spread``
        apart and centred on ``position`` -- the arrangement that shipped
        before the count was a parameter, reproduced exactly.  More than four
        start a second row ``spread * 1.5`` behind the first, so the set grows
        backwards rather than sideways and a wide start room is not a
        requirement for supporting eight.
        """
        if self.slots < 1:
            raise ValueError(f"a player start needs at least one slot, got {self.slots}")
        if self.points:
            if len(self.points) != self.slots:
                raise ValueError(
                    f"{len(self.points)} explicit slot points for {self.slots} slots"
                )
            return list(self.points)
        across = self.facing.cross_axis
        along = self.facing.axis
        rows = -(-self.slots // SLOTS_PER_ROW)
        depth = self.spread * 1.5
        points: list[Point] = []
        for index in range(self.slots):
            row, column = divmod(index, SLOTS_PER_ROW)
            wide = min(SLOTS_PER_ROW, self.slots - row * SLOTS_PER_ROW)
            sideways = (column - (wide - 1) / 2.0) * self.spread
            backwards = ((rows - 1) / 2.0 - row) * depth * self.facing.sign
            point = self.position.with_axis(
                across, self.position[across.index] + sideways
            )
            if rows > 1:
                point = point.with_axis(along, point[along.index] + backwards)
            points.append(point)
        return points


@dataclass
class Zone(Element):
    """A named playable volume the zone manager registers."""

    name: str = ""
    bounds: Span = None  # type: ignore[assignment]
    starting: bool = False
    spawn_set: str = ""

    def __post_init__(self) -> None:
        if not self.spawn_set:
            self.spawn_set = f"{self.name}_spawners"


#: Spawn struct flavours, keyed by the ``script_noteworthy`` value each needs.
SPAWN_MARKERS = {
    "rise": "riser_location",
    "walk": "spawn_location",
    "drop": "faller_location",
    "dog": "dog_location",
}


@dataclass
class Spawn(Element):
    """Where a zombie enters the world, plus (usually) a factory beside it."""

    zone_name: str = ""
    spawn_set: str = ""
    position: Point = None  # type: ignore[assignment]
    facing: Angles = field(default_factory=Angles)
    kind: str = "rise"
    link_tag: str = "find_flesh"
    with_factory: bool = True

    @property
    def marker(self) -> str:
        return SPAWN_MARKERS[self.kind]

    @property
    def is_dog(self) -> bool:
        return self.kind == "dog"


#: How far a door-buy trigger reaches in front of and behind the doorway.
#: The volume is what decides where the buy prompt appears, so it is a slab
#: across the opening: deep enough that a player standing at the threshold is
#: inside it, and no deeper.  Inflating the leaf by 128 units on every axis
#: instead makes each trigger 272 to 384 units on a side, can swallow hundreds
#: of props, and sells a door from about 150 units away.
#:
#: Nothing shipped is copied here: Treyarch's own perk, Pack-a-Punch, wall-buy
#: and mystery-box prompts are script-spawned volumes about a step across (our
#: reading of the decompiled scripts is written up in
#: ``docs/how-zombies-maps-work.md``), and a door buy is the one prompt whose
#: volume the map itself draws, with no recorded size to follow.  A step on
#: each side of the doorway is the same order as those, and is the distance a
#: player covers standing up to a door.
DOOR_TRIGGER_DEPTH = 64.0

#: How far the slab reaches past each jamb, so a player hugging the frame is
#: still inside it without the prompt spilling along the wall.
DOOR_TRIGGER_MARGIN = 16.0


@dataclass
class Door(Element):
    """A buyable door: trigger, moving collision, optional visible model."""

    zone_a: str = ""
    zone_b: str = ""
    box: Span = None  # type: ignore[assignment]
    price: int = 1000
    flag: str = ""
    model: str | None = None
    slide: Point | None = None
    trigger_depth: float = DOOR_TRIGGER_DEPTH
    trigger_margin: float = DOOR_TRIGGER_MARGIN
    model_yaw: float = 0.0
    #: Opens by itself, free, when the power comes on (stock ``electric_door``).
    electric: bool = False
    #: Bought as usual, but only once the power is on; until then the prompt
    #: is the stock "power required" hint (stock ``electric_buyable_door``,
    #: ``_zm_blockers.gsc:163-171`` and ``:834``; ``_zm_power.gsc:196``, ``:745``).
    requires_power: bool = False
    #: Hung in a hole in a wall (True), or free-standing across the head of a
    #: flight (a stair gate, False).  A framed leaf may run past the jambs,
    #: where the wall hides it; a free-standing one may not, so it grows
    #: upwards instead (:attr:`leaves`).
    framed: bool = True

    @property
    def power_gated(self) -> bool:
        """Shut until the power is on, however it opens after that."""
        return self.electric or self.requires_power

    @property
    def door_name(self) -> str:
        return f"{self.id}_leaf"

    @property
    def through_axis(self) -> Axis:
        """The axis you walk along to go through: the doorway's thin one.

        Horizontal only.  A doorway is a hole in an upright wall and a stair
        gate is a pane across the head of a flight; both are thin along the
        way through and tall enough to walk under, so a box that happens to be
        shallower than it is tall is still entered along X or Y.
        """
        return min((Axis.X, Axis.Y), key=lambda axis: self.box.extent(axis))

    @property
    def trigger_box(self) -> Span:
        """The volume the buy prompt lives in: a slab across the doorway.

        The opening's own width plus :data:`DOOR_TRIGGER_MARGIN` at each jamb,
        :data:`DOOR_TRIGGER_DEPTH` in front and behind, and exactly as tall as
        the opening -- never taller, so standing on a floor above or below the
        doorway does not offer the door.
        """
        across = Axis.Y if self.through_axis is Axis.X else Axis.X
        return self.box.grown_on(self.through_axis, self.trigger_depth).grown_on(
            across, self.trigger_margin
        )

    @property
    def travel(self) -> Point:
        """How far the door moves when bought.  Default: down by its height."""
        if self.slide is not None:
            return self.slide
        cover = self.leaf_cover()
        drop = self.box.extent(Axis.Z)
        if cover is not None and cover[3] - self.box.mins.z > drop + 0.5:
            # A stair gate's leaf can stand taller than its box: drop it all.
            # (The half unit ignores the 4-place modelscale's rounding.)
            drop = cover[3] - self.box.mins.z
        return Point(0.0, 0.0, -drop)

    @property
    def across_axis(self) -> Axis:
        """The horizontal axis the doorway is wide along."""
        return Axis.Y if self.through_axis is Axis.X else Axis.X

    @property
    def leaves(self) -> tuple[tuple[Point, float], ...]:
        """Where the visible leaf model goes: ``(base centre, modelscale)`` each.

        The leaf is sized to the opening, not the other way round.  Its scale
        makes it exactly as tall as the opening (the door slides down by that
        height, so it vanishes under the floor when bought), and as many leaves
        stand side by side as it takes to reach both jambs; the spare width
        runs into the wall either side, where the wall hides it.  Growing
        sideways rather than upwards is the point: a wall always continues past
        a jamb, while the top of an unroofed corn or fence wall does not.

        A free-standing stair gate (``framed`` False) has no wall at its
        sides, so there the leaves span the width exactly and any spare goes
        on top instead, and :attr:`travel` drops the taller leaf all the way.

        Empty for a door with no model, or a model whose face is not in
        :data:`~zmforge.blueprint.catalogue.DOOR_LEAF_SIZE` (check ``Z81``
        fails that door rather than guessing).
        """
        from math import ceil, floor

        from .catalogue import DOOR_LEAF_SIZE

        size = DOOR_LEAF_SIZE.get(self.model or "")
        if size is None:
            return ()
        leaf_w, leaf_h = size
        width = self.box.extent(self.across_axis)
        height = self.box.extent(Axis.Z)
        scale = height / leaf_h
        across = width / (leaf_w * scale)
        count = max(1, ceil(across - 1e-6) if self.framed else floor(across + 1e-6))
        scale = max(scale, width / (count * leaf_w))
        step = leaf_w * scale
        base = self.box.centre.with_axis(Axis.Z, self.box.mins.z)
        middle = base[self.across_axis.index]
        return tuple(
            (base.with_axis(self.across_axis, middle + (i - (count - 1) / 2.0) * step),
             round(scale, 4))
            for i in range(count)
        )

    def leaf_cover(self) -> tuple[float, float, float, float] | None:
        """``(across lo, across hi, z lo, z hi)`` the closed leaves cover, or
        ``None`` when the leaf's face is unknown."""
        from .catalogue import DOOR_LEAF_SIZE

        size = DOOR_LEAF_SIZE.get(self.model or "")
        leaves = self.leaves
        if size is None or not leaves:
            return None
        axis = self.across_axis.index
        half = [size[0] * scale / 2.0 for _, scale in leaves]
        return (
            min(p[axis] - h for (p, _), h in zip(leaves, half)),
            max(p[axis] + h for (p, _), h in zip(leaves, half)),
            min(p.z for p, _ in leaves),
            max(p.z + size[1] * scale for p, scale in leaves),
        )


@dataclass
class Machine(Element):
    """A perk vending machine or the pack-a-punch."""

    perk: "PerkKind" = None  # type: ignore[assignment]
    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH


@dataclass
class WallWeapon(Element):
    """A spawnable wall buy, with an optional chalk outline decal.

    ``chalk_material`` is off by default and has to be named explicitly: the
    decal material is keyed by the game's weapon name, not by the prefab slug,
    and building it from the slug produced three missing-material warnings in
    a measured compile (see :func:`~zmforge.materials.chalk_material_for`).
    """

    slug: str = ""
    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH
    chalk_material: Material | None = None
    decal_size: str = "4 64 32"
    #: What this buy charges, or ``None`` for whatever the level's weapon
    #: table says -- which for a map that ships no table of its own is
    #: Treyarch's price.  A price is not a key on the buy: it is a row of the
    #: map's own weapon table, so setting one here makes the map ship a table
    #: (:mod:`zmforge.emit.weapons`).  ``None`` is the safe default and emits
    #: exactly the map that was emitted before this field existed.
    price: int | None = None

    @property
    def chalk(self) -> bool:
        return self.chalk_material is not None


@dataclass
class MysteryBox(Element):
    """Prefab base, animated chest barrier and the use struct (spec 4.8)."""

    chest_name: str = "start_chest"
    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH
    price: int = 950
    starting: bool = True


@dataclass
class Wunderfizz(Element):
    """Der Wunderfizz: one zbarrier entity that sells a random perk.

    Not a :class:`Machine`.  The perk machines are structs the framework
    reads and dresses; this is a real entity the stock script drives as a
    barrier, and the two mechanisms share nothing -- see
    :data:`~zmforge.blueprint.catalogue.WUNDERFIZZ_TARGETNAME` for the lines
    that say so.

    :attr:`starting` marks this machine the one the stock script starts on.
    Exactly one placed Wunderfizz has to carry it; with none, every machine
    goes to ``wait_for_power()`` and none of them ever thinks.  The blueprint
    sets it on the first one placed, and check Z49 holds the count.
    """

    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH
    starting: bool = True


@dataclass
class PowerSwitch(Element):
    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH


@dataclass
class Lamp(Element):
    """An omni light.  Every sealed room needs at least one (spec 4.11).

    :attr:`stops` is log2 of the emitter's intensity and only means anything
    against the map's exposure, so ``None`` -- the default -- means "whatever
    this map's sun/sky preset calls for", resolved by
    :meth:`zmforge.blueprint.model.Blueprint.stops_of`.  See
    :mod:`zmforge.lighting` for the measurements.  A float here is an
    absolute override and is not adjusted for the map's exposure, though the
    blueprint's brightness offset still applies to it.

    :attr:`shadows` is whether this lamp gets a run-time shadow map, emitted as
    ``PRIMARY_NOSHADOWMAP``.  It is not free: the map has a fixed number of omni
    shadow slices (``worldspawn``'s ``numOmniShadowSlices``) and lights past
    that number compete for one, so their shadows change as the camera moves.
    The Giant casts from 42 of its 280 omni lights; fill lamps placed only to
    raise the light level do not need to cast, and
    :meth:`zmforge.blueprint.model.Blueprint.light_rooms` turns theirs off.
    """

    position: Point = None  # type: ignore[assignment]
    colour: tuple[float, float, float] = (1.0, 1.0, 1.0)
    radius: float = 512.0
    stops: float | None = None
    zone_name: str | None = None
    shadows: bool = True
    #: Scatters its light in lit fog (``"volumetric" "1"``, as 177 lights of
    #: ``zm_giant_light.map`` do, e.g. line 920).  Off by default.
    volumetric: bool = False
    #: The radiant exploder this lamp belongs to, which makes it a light
    #: script can switch (``exploder::exploder`` / ``stop_exploder``, the
    #: stock perk-light pattern of ``_zm_perk_quick_revive.gsc:185,791``).
    #: ``None`` is an ordinary static lamp.  Set by
    #: :func:`zmforge.script.glow.place_owned_glow`, never by hand.
    exploder: str | None = None


@dataclass
class Window(Element):
    """A barricade window: hole, yard, prefab and its linked riser."""

    zone_name: str = ""
    room_id: str = ""
    side: Side = Side.NORTH
    link_tag: str = ""
    barricade_origin: Point = None  # type: ignore[assignment]
    barricade_yaw: float = 0.0
    prefab: str = ""
    yard_id: str = ""
    riser_id: str = ""
    aperture_index: int = -1


@dataclass
class Prefab(Element):
    """A stock prefab placed for its own sake: scenery, not a mechanic.

    A perk machine, the mystery box and the power switch are each a
    ``misc_prefab`` too, but each carries something besides the entity -- a
    ``#using`` line, a chest name, a price -- which is why each has an element
    of its own.  This one carries nothing else at all: the same entity with no
    side effect, for the stock prefabs the generator has no model of.  The
    value is the prefab path relative to ``map_source/``, which is what the
    ``misc_prefab`` key's own definition says it is (format reference, the
    ``model`` key's ``.gdf`` schema: ``fileExtension`` ``map``).

    ``yaw`` is ``None`` for the usual case, where :attr:`facing` is turned
    counter-clockwise off the front-at-yaw-zero measured for this model
    (``catalogue.PREFAB_FRONT_ZERO_BY_MODEL``, spec appendix B; the stock
    library's twenty-six prefabs are all in there and they do not agree with
    each other).  For a model nobody has read the emitter has to guess and
    ``Z23`` warns, which is the case for giving the raw ``yaw`` instead: a
    caller that has established this prefab's own zero heading.  Then
    :attr:`facing` is not read at all.
    """

    model: str = ""
    position: Point = None  # type: ignore[assignment]
    facing: Facing = Facing.SOUTH
    yaw: float | None = None
    #: The ``script_string`` token on the entity, or ``""`` for none.  A
    #: barricade is a ``misc_prefab`` whose token is the link tag its riser
    #: carries, and that pairing is the whole of the wiring between them
    #: (:meth:`~zmforge.blueprint.model.Blueprint.add_window`).  Without a
    #: field for it a barricade could not be placed except through
    #: ``add_window``, which would drop it on a round trip through a map
    #: editor, where the hole, the yard and the riser are three separate
    #: things the map's author draws.
    script_string: str = ""


@dataclass(frozen=True, slots=True)
class Prop:
    model: str
    origin: Point
    yaw: float
    scale: float = 1.0
    #: Whether ``cod2map64`` bakes this model's collision into the static BSP.
    #: ``False`` writes ``no_collmap "1"`` and the player walks through it;
    #: ``True`` writes ``use_collmap "1"`` and the compiler bakes the collmap
    #: named after the model in ``share/raw/collmaps``.  Measured on the mod tools
    #: install: the key is read at *compile* time and resolved by
    #: filename, so a model with no stock collmap needs one generated for it
    #: or the flag does nothing at all (see :mod:`zmforge.props.collision`).
    solid: bool = False
    #: The model's own bounding box in its local frame, ``(mins, maxs)``, for
    #: a solid prop whose model ships no collmap: the project writes one from
    #: it at commit time.  ``None`` means "use whatever the install ships",
    #: which is right for Treyarch's own 26 and for a walk-through prop.
    collision_box: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    #: Write this one as a ``script_model`` rather than a ``misc_model``, so
    #: the **game** resolves the model when it spawns the entity instead of
    #: ``cod2map64`` resolving it when it bakes the BSP.
    #:
    #: WHY, measured on the mod tools install with ``cod2map64 -platform pc``
    #: on a probe map: ``misc_model "p7_zm_vending_ads"`` and
    #: ``misc_model "p7_zm_vending_jugg"`` both print ``ERROR: Missing xmodel``
    #: and no BSP is written, because the perk-machine models are declared by
    #: no GDT and have no ``model_export`` source -- they exist only as built
    #: assets in ``zm_levelcommon`` (``zone_source/all/assetlist/
    #: zm_levelcommon.csv:1978, 1981``).  The same two names on
    #: ``script_model`` entities compile clean, exit 0, BSP written, because
    #: the compiler never looks a script entity's model up.  At run time the
    #: game has them: this map spawns a real machine of each perk, and the
    #: stock framework sets exactly these model names on it.
    #:
    #: A ``script_model`` carries no baked collision, so a dynamic prop is
    #: always walk-through however big it is -- which is what makes a room
    #: packed to the walls with them safe.
    #:
    #: **Unverified:** that the entity renders with no ``targetname`` on it.
    #: The stock door leaf (``p7_zm_der_door_buy_std_onepiece``)
    #: is a ``script_model`` with no targetname and it is visible, which is
    #: the closest thing to evidence there is without running the game.
    dynamic: bool = False
    #: This prop's own name, and the only thing its GUID is derived from.
    #: Blank means "take the scatter's": :class:`PropScatter` fills it in with
    #: ``<scatter id>_<index>``, which is what every prop a recipe places has
    #: always been called.  It is a field on the prop rather than its place in
    #: a list because that is what holds a GUID still -- a prop inserted in the
    #: middle of a scatter would otherwise renumber every prop after it, and the
    #: join between this map, its shared document and a person's edits in
    #: Radiant is the GUID.
    id: str = ""
    #: A lean off upright, in degrees: ``pitch`` tips the model's own +x end
    #: down, ``roll`` tips it about its own x axis (the map file's ``angles``
    #: are ``pitch yaw roll``).  Zero for almost everything; a plant lining a
    #: wall leans a few degrees so a row of them is not a picket fence
    #: (:mod:`zmforge.dressing.lining`).  Footprint checks keep using the
    #: upright box, so only walk-through props should lean far.
    pitch: float = 0.0
    roll: float = 0.0

    def __post_init__(self) -> None:
        # A heading is a direction, not a count of turns, so it is stored folded
        # into [0, 360).  Two writers read this field -- the map file and the
        # shared document -- and a prop turned a full circle was written `360`
        # by one of them and `0` by the other the moment the same map came back
        # through the editor, which folds on the way in.  One place, here.
        object.__setattr__(self, "yaw", float(self.yaw) % 360.0)


@dataclass
class PropScatter(Element):
    """Decorative models, solid or not, one entity each (spec 4.13).

    Each :class:`Prop` carries its own :attr:`Prop.solid`; the group does not.
    A scatter used to be collision-free by definition, which is what made
    every piece of set dressing in a generated map walk-through.
    """

    props: list[Prop] = field(default_factory=list)

    def __post_init__(self) -> None:
        # A prop that was not given a name of its own is called after the
        # scatter and its place in it, which is the name every recipe-placed
        # prop has always had; a prop that was given one keeps it, which is how
        # a map rebuilt from the shared document writes the same GUIDs.
        self.props = [
            prop if prop.id else replace(prop, id=f"{self.id}_{index}")
            for index, prop in enumerate(self.props)
        ]


@dataclass
class ImportedMap(Element):
    """A foreign or older ``.map`` preserved verbatim.

    Blueprint operations cannot edit its contents; it is written back as it
    was read so nothing is silently dropped.
    """

    document: "Document" = None  # type: ignore[assignment]
    source_path: str = ""


@dataclass
class AmbientFx(Element):
    """A looping stock effect placed in the map, as Radiant places it.

    Written as a ``classname "fx"`` entity with an ``fxdef`` key, the way the
    stock maps place ambient fire, smoke and embers (``zm_giant`` carries 894
    of them in its prefabs, e.g. ``fxdef "fire/fx_fire_lamp_hurricane"``); no
    script plays it.  The effect must also be in the zone, which
    :func:`zmforge.dressing.fx.burning` and friends do through
    ``Blueprint.declare_asset``.  ``yaw``/``pitch`` aim the effect's forward
    axis; stock fire points up, which is ``pitch=-90``.
    """

    position: Point = None  # type: ignore[assignment]
    fx: str = ""
    pitch: float = -90.0
    yaw: float = 0.0
    note: str = ""


@dataclass
class Traversal(Element):
    """A zombie traversal: a ``node_negotiation_begin`` / ``_end`` pair.

    Written the way Treyarch's own
    ``map_source/_prefabs/library/traverse/t7_zm_jump_128.map`` writes one:
    the begin node on the low floor facing the ledge with ``animscript
    "jump_up_128"``, targeting the end node on the ledge top, which carries
    ``animscript "jump_down_128"`` for the way back, and the begin node
    ``movementtype_ignore "civilian,riotshield,zombie_dog"``.  Placed by
    :func:`zmforge.verify.camping.reach_camping_tops` so a walker follows a
    player onto a top he jumped onto (Z46).
    """

    begin: Point = None  # type: ignore[assignment]
    end: Point = None  # type: ignore[assignment]
    up: str = ""
    down: str = ""
    note: str = ""


# Spec section 8.3 names the handles this way; the elements *are* the handles.
SolidRef = Massing
RoomRef = Room
YardRef = Yard
ZoneRef = Zone
DoorRef = Door
TerrainRef = Terrain
WindowRef = Window
MachineRef = Machine
SpawnRef = Spawn
EnclosureRef = Enclosure
OpeningRef = Opening
