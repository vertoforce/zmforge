"""The map model: one in-memory blueprint that every output file derives from.

Nothing here touches disk and nothing here knows about the ``.map`` text
format.  Callers add elements through the operations below, get a handle
back, and the whole model is validated as a unit before ``Project.commit``
writes anything (spec section 8.1).

Placement rules that were repeatedly got wrong by hand are enforced at add
time rather than left to the caller: a riser's Z is checked against the floor
underneath it, the enclosure computes its own bounds, a window cuts its hole
and digs its yard and links its riser in one call.
"""

from __future__ import annotations

import math
import re
import random
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

from ..errors import (
    BlueprintError,
    InteractiveBlocked,
    NotOnFloor,
    OpeningDoesNotFit,
    UnknownZone,
)
from ..materials import CAULK, CLIP, FaceMaterials, Material
from ..solids.forms import (
    STAIR_GATE_HEIGHT,
    Solid,
    block,
    flight,
    stair_clip,
    stair_gate,
    wedge,
)
from ..solids.layout import (
    Aperture,
    aperture_box,
    room_shell,
    sky_cage,
    yard_shell,
)
from ..spatial import Angles, Axis, Facing, Point, Side, Span
from .. import lighting
from ..surfaces.ground import TerrainRecord, spawner_height
from ..surfaces.patches import column_runs, mesh_chunks
from . import catalogue as fixed
from .catalogue import (
    BARRICADE_EXTERIOR_ZERO,
    BARRICADE_PREFAB,
    BARRICADE_PREFAB_HIDE_DEBRIS,
    LEVEL_WEAPONS,
    PerkKind,
    perk_named,
    prefab_yaw,
    wall_weapon_prefab,
    wall_weapon_weapon,
)
from .elements import (
    DEFAULT_LAYER,
    SEALED_OPENING,
    STAIR_CLIP,
    SPAWN_MARKERS,
    AuthoredForm,
    DOOR_TRIGGER_DEPTH,
    DOOR_TRIGGER_MARGIN,
    Door,
    Element,
    Enclosure,
    ImportedMap,
    Lamp,
    Machine,
    Massing,
    MysteryBox,
    Opening,
    PlayerStart,
    PowerSwitch,
    Prefab,
    Prop,
    PropScatter,
    Room,
    RoomMaterials,
    Spawn,
    Terrain,
    WallWeapon,
    Window,
    Wunderfizz,
    Yard,
    Zone,
    STOCK_PLAYER_SLOTS,
)
from . import lanes, reach
from .identity import Identity, IdAllocator
from .windows import (
    CLOSET_LAMP_COLOUR,
    CLOSET_LAMP_RADIUS,
    CLOSET_MATERIALS,
    CLOSET_PROPS,
    closet_prop_spots,
)
from ..emit.manifest import AssetRef
from ..emit.sound import ALIAS_ROW_CEILING, CustomSound
from ..script.custom import CustomScript, merge
from ..script.perks import CustomPerk, perk_script
from .script_plan import ScriptPlan, ZoneEdge
from .weapons import CustomWeapon
from ..emit.weapons import TABLE_LOADER, table_asset as weapon_table_asset
from ..emit.strings import (
    LocalizedString,
    asset_name as string_asset,
    perk_prompt,
    weapon_prompt,
    weapon_reference,
)

__all__ = [
    "Blueprint",
    "GroundHit",
    "WINDOW_SILL",
    "WINDOW_WIDTH",
    "WINDOW_HEIGHT",
    "TRAVERSE_WIDTH",
    "TRAVERSE_TOP",
    "MIN_YARD_DEPTH",
]

# The barricade window's hole, measured off the prefab's own brushes rather
# than taken from the spec, because the spec was wrong and the map was
# unplayable for it.
#
# `_prefabs/zm/zm_core/barricade_reciever_wood.map` carries three brushes, in
# prefab-local units with the placement origin at (0, 0, 0) and local z = 0 at
# the floor surface:
#
#   clip / clip_player      X -48..50  (98 wide)  Z   0..113  blocks the player
#   traverse, nonColliding  X -25..25  (50 wide)  Z   0.. 40  the AI channel
#   clip_missile / clip_ai  X -32..32  (64 wide)  Z   0.. 35  the sill band
#
# **The channel zombies climb through starts at the floor.**  Spec 4.6 said
# the opening wants "its sill 48 units above the floor surface (waist
# height)", citing an inherited claim that a floor-level sill "makes zombies
# vault onto nothing and fall through the world".  The prefab says otherwise,
# and a 48-unit sill puts the whole 0..40 traverse brush inside solid wall:
# the barricade boards up a hole the zombies have no way to reach.  That is
# why nothing comes through such a window.
#
# The vault-onto-nothing claim is separately handled and always was: add_window
# digs a yard with a floor at the same z as the room's, and Z8 refuses a riser
# that is not standing in one.
#
#: The bottom of a barricade window: the floor surface, because the prefab's
#: traversal channel starts there.  What the player *sees* is a window all the
#: same: the emitter draws a non-colliding sill wall to 32 in the hole
#: (``blueprint/windows.py``, check ``Z85``).
WINDOW_SILL = 0.0

#: Rounded in from the prefab's 98-unit player clip onto the 16-unit grid, so
#: the clip overlaps the wall by a unit either side rather than leaving a gap
#: the player can see through.
WINDOW_WIDTH = 96.0

#: Rounded in from the prefab's 113-unit player clip, for the same reason.
WINDOW_HEIGHT = 112.0

#: The AI traversal brush inside the prefab: an opening that does not contain
#: it is a boarded hole zombies cannot use.  Width along the wall, and the
#: band above the floor surface.
TRAVERSE_WIDTH = 50.0
TRAVERSE_TOP = 40.0

# Why there is one barricade rule here and not two.
#
# One tutorial says "a zombie window sill must be 40 units, and it cannot be
# higher or lower, because the hand-plant animation is authored to that
# height", sets that against "a player mantle is 32", and concludes that the
# barricade is two clearance problems, not one.  Checked, and
# it does not survive contact with either primary source:
#
#   - The 40 is not a sill.  It is the TOP of the prefab's own `traverse`
#     brush, which runs from the floor surface to 40 -- measured off
#     `barricade_reciever_wood.map` above, which is a stronger source than a
#     caption, and already enforced by `traverse_is_blocked`.  A barricade
#     opening whose sill is anything but 0 is refused outright.
#   - The 32 is real but is a different rule about a different opening.  The
#     mod tools' own `Scale_Standards.pdf` gives a
#     *player*-traversable window as width 40, height 60, sill height 32, and
#     a maximum non-traversable window as 32 x 32.  Those are blockout numbers
#     for a hole a player mantles through.
#
# So they are two rules for two things, and this package only builds one of
# them: every raised-sill opening a recipe cuts here is a view, sealed by
# `seal_opening`, never a route -- which is why `_check_clearance` skips an
# aperture with a sill.  A second rule would guard a feature that does not
# exist.  If `cut_opening` ever gets used as a way through with a sill, the
# numbers to check against are the Scale_Standards ones above, as an `N` row.


def traverse_is_blocked(width: float, height: float, sill: float) -> str | None:
    """Why a barricade opening cannot be climbed through, or ``None``.

    One function so that :meth:`Blueprint.add_window` and the Z8 check agree
    by construction, and so the reason is phrased once.
    """
    if sill > 0.0:
        return (
            f"its sill is {sill:g} above the floor, and the prefab's traversal "
            f"brush runs from the floor to {TRAVERSE_TOP:g}; a sill of any "
            "height puts that channel inside solid wall and no zombie can use "
            "the window"
        )
    if sill + height < TRAVERSE_TOP:
        return (
            f"it is {height:g} tall and reaches {sill + height:g} above the "
            f"floor, under the {TRAVERSE_TOP:g} the prefab's traversal brush "
            "needs"
        )
    if width < TRAVERSE_WIDTH:
        return (
            f"it is {width:g} wide, under the {TRAVERSE_WIDTH:g} of the "
            "prefab's traversal brush"
        )
    return None


def _refuse_a_blocked_traverse(width: float, height: float, sill: float) -> None:
    blocked = traverse_is_blocked(width, height, sill)
    if blocked is None:
        return
    raise BlueprintError(
        f"this window's opening is {width:g} x {height:g} at sill {sill:g} and "
        f"{blocked}.  A hole that is only meant to be a hole is cut_opening(), "
        "not add_window()"
    )

#: Spec 2.7: with the riser 96 units out and a 16-unit far wall, 144 is the
#: shallowest yard that leaves floor beyond the riser.  176 is what played.
MIN_YARD_DEPTH = 144.0
DEFAULT_YARD_DEPTH = 176.0

#: Spec 4.6: how far outside the barricade its riser stands.
BARRICADE_RISER_REACH = 96.0

#: Spec 4.1: players spawn a little above the slab.
PLAYER_START_CLEARANCE = 16.0

#: Spec 4.10, flagged as [played, not derived]: the wall-weapon prefab origin
#: that played sat 8 units BELOW the floor surface, i.e. inside the floor
#: slab.  The prefab's own geometry is said to account for it.  Exposed as a
#: knob rather than hard-coded, and reported by ``verify`` as suspicious.
WALL_WEAPON_DROP = 8.0


#: How far above a placement a surface may sit and still be what the thing
#: is standing on: one step.  Without it, a mezzanine would answer for a
#: spawn on the ground floor underneath it.
STEP_TOLERANCE = 8.0


@dataclass(frozen=True, slots=True)
class GroundHit:
    """What is under a point, where it came from, and whether it can be got to."""

    found: bool
    z: float
    source: str = ""
    spread: float = 0.0
    element_id: str | None = None
    reachable: bool = True


class Blueprint:
    """The whole map model.

    Elements are added through the operations below and referenced by the
    handles returned.  Ids are stable, so a re-run with the same inputs yields
    the same ids, the same GUIDs and the same bytes.

    ``title`` is the map's display name; it is the only field here that no
    geometry depends on, and it is here rather than on the project because
    the loading screen's caption and the manifest's ``>title`` have to agree.
    """

    def __init__(
        self,
        name: str,
        *,
        seed: str | None = None,
        title: str | None = None,
        brightness_stops: float = 0.0,
    ) -> None:
        self.name = name
        self.seed = seed if seed is not None else name
        #: One overall brightness knob for the whole map, in photographic
        #: stops, added to every lamp.  ``+1`` doubles every light, ``-1``
        #: halves it.  It exists so that judging a bake and nudging it does
        #: not mean regenerating any logic: see :mod:`zmforge.lighting`.
        self.brightness_stops = float(brightness_stops)
        #: A starter shape (one-room, three-room), not a finished map:
        #: the design advisories (dressing density, scenes, training rings,
        #: the gamble machine) describe what it deliberately leaves out, so
        #: front ends show its warnings only on request (``zmforge -v``).
        #: Errors are unaffected.
        self.starter = False
        #: What a front end built this from (recipe name, player slots,
        #: starting points), recorded under the document's ``origin`` so a
        #: later ``zmforge requirements --recipe`` can refuse a mismatch.
        self.origin_args: dict = {}
        #: What menus should call this map.  ``None`` means "derive it from
        #: the asset name" (see :func:`zmforge.emit.manifest.display_title`).
        self.title = title
        self.identity = Identity(self.seed)
        self.script = ScriptPlan(map_name=name)
        #: Assets the map declares beyond the required six manifest lines.
        self.assets: list[AssetRef] = []
        #: Stock weapons this map re-prices, by weapon name.  Empty is the
        #: default and means the map ships no weapon table at all.
        self.weapon_prices: dict[str, int] = {}
        #: Guns this map adds to the level's weapon set.
        self.custom_weapons: list[CustomWeapon] = []
        #: What this map calls a weapon on its wall-buy prompt, by weapon
        #: name.  Empty is the default and means the map ships no localized
        #: strings at all and says exactly what the framework says.
        self.weapon_prompts: dict[str, str] = {}
        #: Sounds this map carries itself, one row of its own alias bank
        #: each, with the wave file behind it.  Empty is the default and
        #: means the map ships no bank at all.
        self.custom_sounds: list[CustomSound] = []
        #: Every quest ``trigger_radius_use``, as ``(label, origin, radius)``,
        #: recorded by :func:`zmforge.script.quest.install_quest` so the
        #: static checks can ask whether a player can walk to it (Z55).
        self.quest_use_points: list[tuple[str, Point, float]] = []
        #: The map's declared walk paths, polylines of floor points ``(x, y,
        #: z)`` (a maze's cell-to-cell passages), for
        #: :func:`zmforge.blueprint.autolamp.light_paths` and D7's dark-stretch
        #: warning.  Empty: the map declares none and D7 has nothing to ask.
        self.walk_paths: list[list[tuple[float, float, float]]] = []
        #: Every quest step's points and the zones it waits for, recorded by
        #: :func:`zmforge.script.quest.install_quest` for Z61 (P8).
        self.quest_steps: list[dict] = []
        #: Use triggers wired by custom logic (split-start buttons, a ticket
        #: dispenser, a mechanic's stations), as dicts the design review lists
        #: next to the element walk's machines and doors: ``id``, ``kind``
        #: (``"use_trigger"``), ``what``, ``at``, ``prompt``/``prompts``,
        #: ``wired_by``, ``purchase``.  Advisory only; nothing is emitted.
        self.review_interactives: list[dict] = []
        #: Plain statements a recipe makes to the design review about how the
        #: map is built (a count that follows the player slots, say), so the
        #: reviewer does not have to infer them from the code.  Advisory only.
        self.review_notes: list[str] = []
        #: Perks of this map's own, in the order they were declared.  Empty
        #: is the default and emits exactly the pair of scripts that were
        #: emitted before custom perks existed.
        self.custom_perks: list[CustomPerk] = []
        #: HUD images this map packs itself, image asset name -> PNG bytes
        #: (:meth:`ship_hud_image`).  Empty is the default and writes no
        #: ``texture_assets`` folder and no ``.gdt`` at all.
        self.hud_images: dict[str, bytes] = {}
        self.map_strings: dict[str, str] = {}
        self._ids = IdAllocator()
        self._elements: list[Element] = []
        self._by_id: dict[str, Element] = {}
        #: One :class:`zmforge.blueprint.reach.Keep` per interactive item
        #: already placed, kept as they go in so that each new placement is
        #: checked against the ones before it rather than the whole model
        #: being re-derived every time.
        self._keeps: list[reach.Keep] = []
        #: :meth:`interactive_keep_clear`'s answer, held because a prop
        #: placer asks it once per candidate and this map places two
        #: thousand of them.  Dropped whenever an interactive goes in.
        self._keep_clear: tuple[tuple[float, ...], ...] | None = None

    # ------------------------------------------------------------------
    # Element bookkeeping
    # ------------------------------------------------------------------
    def _install(self, element: Element) -> Element:
        self._refuse_a_blocked_interactive(element)
        self._elements.append(element)
        self._by_id[element.id] = element
        # Every buyable keeps a clear walk-up lane, whatever placed the props
        # (zmforge.blueprint.lanes; Z48).
        lanes.enforce(self, element)
        return element

    # ------------------------------------------------------------------
    # Interactive items: standing room
    # ------------------------------------------------------------------
    def _refuse_a_blocked_interactive(self, element: Element) -> None:
        """Refuse an interactive that another one stops being used.

        Everything with a use prompt -- a perk machine, the pack-a-punch, a
        mystery box, the power switch, a wall buy, a door -- owns a body and
        an apron (:mod:`zmforge.blueprint.reach`), and the refusal happens
        here, in ``_install``, so that every way of adding one is covered by
        the one rule rather than each placement method carrying its own copy.

        **Why this is an exception and not a finding.**  A wall buy behind a
        perk machine is a defect a map can ship with: an after-the-fact
        warning is a thing a person can be looking away from, and what it
        costs is a buy nobody can press.  An item you cannot reach is an
        item that does not exist, so the model refuses to hold one.

        Crowding -- an item that reaches into another's apron but leaves it
        somewhere to stand -- is *not* refused; ``Z42`` reports it.
        """
        keep = reach.keep_of(element)
        if keep is None:
            return
        clash = reach.first_clash(keep, self._keeps)
        if clash is not None:
            raise InteractiveBlocked(f"{element.id}: {clash.message()}", clash)
        self._keeps.append(keep)
        self._keep_clear = None

    def interactive_keeps(self) -> list[reach.Keep]:
        """Every interactive item's body and apron, derived from the elements.

        Re-derived rather than read off :attr:`_keeps`, so that it answers
        for a blueprint this process did not build one placement at a time --
        one read back out of the editor, say.
        """
        return reach.keeps_of(self._elements)

    def interactive_keep_clear(
        self,
    ) -> tuple[tuple[float, float, float, float, float, float], ...]:
        """Where no prop may stand: every interactive's body and its apron.

        The union of the two volumes every item with a use prompt owns, as
        ``(x0, y0, x1, y1, z0, z1)`` boxes -- the same six numbers
        ``zmforge.recipes.props._stair_zones`` already returns, so a prop
        placer filters them the way it already filters staircases.  The
        ``z0``/``z1`` pair is what keeps a machine on the balcony from
        emptying the floor under it.

        The prop placer's one-line use is :meth:`interactive_blocks`::

            if bp.interactive_blocks(where, half[0], half[1]):
                return "interactive"

        A prop can stand inside an interactive item's own footprint or
        within 48 units in front of one; these are those volumes, and they are wider than 48 because standing
        room is what the prop is taking away.

        Held between calls and dropped when an interactive is added, because
        a placer asks it once per candidate.  An element moved *after* it was
        installed is the one case the held answer can be stale for;
        :meth:`interactive_keeps` always re-derives, and so does ``Z42``.
        """
        if self._keep_clear is None:
            self._keep_clear = reach.zone_rectangles(self.interactive_keeps())
        return self._keep_clear

    def interactive_blocks(
        self, where: Point, half_x: float = 0.0, half_y: float = 0.0
    ) -> bool:
        """Does a footprint at ``where`` stand in an interactive's keep-clear?

        ``half_x``/``half_y`` are the footprint's own half extents in plan,
        so a long prop whose centre is beside a machine but whose end is over
        its apron answers ``True``.
        """
        at = Point.of(where)
        return reach.zone_hit(
            self.interactive_keep_clear(), at.x, at.y, at.z, half_x, half_y
        )

    def _claim(self, kind: str, wanted: str | None) -> str:
        return self._ids.next_for(kind, wanted)

    def elements(self, kind: type | None = None) -> list[Element]:
        if kind is None:
            return list(self._elements)
        return [e for e in self._elements if isinstance(e, kind)]

    def reorder(self, order: Sequence[str]) -> None:
        """Put the elements back in a recorded order, ids first, rest after.

        The map file is written class by class -- every room's brushes, then
        every yard's, then every massing's -- so the *order elements were built
        in* is part of the file, and it is not recoverable from the finished
        geometry: a flight of stairs, a ramp and a block are three calls and one
        class, and a document that lists them in three lists has lost which came
        first.  ``zmforge.editordoc`` writes the order down and this puts it
        back, which is what makes an unedited round trip through the shared
        document produce the same bytes rather than the same map.

        The sort is stable and partial on purpose: an id this order does not
        name -- a block someone drew in the editor after the map was generated
        -- keeps its place relative to the other new ones and lands after the
        recorded ones, so adding one thing does not move everything else.
        """
        rank = {str(name): index for index, name in enumerate(order)}
        end = len(rank)
        self._elements.sort(key=lambda element: rank.get(element.id, end))

    def find(self, element_id: str) -> Element:
        try:
            return self._by_id[element_id]
        except KeyError:
            raise BlueprintError(f"no element with id {element_id!r}") from None

    def near(self, point: Point, radius: float) -> list[Element]:
        hits: list[Element] = []
        for element in self._elements:
            origin = getattr(element, "position", None)
            if origin is None:
                continue
            if origin.distance_to(point) <= radius:
                hits.append(element)
        return hits

    def __iter__(self) -> Iterator[Element]:
        return iter(self._elements)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def add_block(
        self,
        bounds: Span,
        materials: FaceMaterials | Material | str,
        *,
        contents: Sequence[str] = (),
        walkable: bool = False,
        reachable: bool = True,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
        note: str = "",
        targetname: str = "",
    ) -> Massing:
        """One world box.  ``walkable`` makes its top a surface placements
        resolve against; ``reachable=False`` declares that nothing leads onto
        it (see :class:`~zmforge.blueprint.elements.Massing`).  A
        ``targetname`` makes it part of a scripted brush entity of that name
        (:attr:`~zmforge.blueprint.elements.Massing.targetname`)."""
        faces = _as_face_materials(materials)
        element = Massing(
            id=self._claim("block", id),
            layer=layer,
            solids=[block(bounds, faces, tuple(contents))],
            note=note,
            walkable=walkable,
            reachable=reachable,
            targetname=targetname,
            authored=AuthoredForm(
                "block", box=bounds, materials=faces, contents=tuple(contents)
            ),
        )
        return self._install(element)  # type: ignore[return-value]

    def add_slab(
        self,
        footprint: Span,
        z: float,
        thickness: float,
        materials: FaceMaterials | Material | str,
        *,
        walkable: bool = True,
        reachable: bool = True,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Massing:
        """A horizontal slab whose top surface sits at ``z``.

        A slab is a floor unless told otherwise, so ``walkable`` defaults to
        true here and false on :meth:`add_block`.  ``reachable=False`` is the
        upper floor, ledge or balcony with no route onto it.
        """
        box = Span.between(
            Point(footprint.mins.x, footprint.mins.y, z - thickness),
            Point(footprint.maxs.x, footprint.maxs.y, z),
        )
        return self.add_block(
            box,
            materials,
            walkable=walkable,
            reachable=reachable,
            id=id,
            layer=layer,
            note="slab",
        )

    def add_wedge(
        self,
        bounds: Span,
        rise_toward: Facing | str,
        materials: FaceMaterials | Material | str,
        *,
        note: str = "ramp",
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Massing:
        faces = _as_face_materials(materials)
        element = Massing(
            id=self._claim("ramp", id),
            layer=layer,
            solids=[wedge(bounds, Facing.of(rise_toward), faces, note=note)],
            note=note,
            authored=AuthoredForm(
                "ramp", box=bounds, materials=faces, toward=Facing.of(rise_toward)
            ),
        )
        return self._install(element)  # type: ignore[return-value]

    def add_steps(
        self,
        base: Point,
        count: int,
        depth: float,
        height: float,
        width: float,
        toward: Facing | str,
        materials: FaceMaterials | Material | str,
        *,
        reachable: bool = True,
        clip_ramp: bool = True,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Massing:
        """A flight of full-depth step columns.  Every step's top is walkable,
        and each is its own solid, so a placement on the fourth step resolves
        to the fourth step.

        A flight of two steps or more also gets a smooth clip ramp over its
        treads (:func:`~zmforge.solids.forms.stair_clip`), because that plane
        and not the treads is what the walkers climb; pass ``clip_ramp=False``
        only for a flight nothing is meant to be able to climb, and say so in
        the recipe.
        """
        faces = _as_face_materials(materials)
        boxes = flight(base, count, depth, height, width, Facing.of(toward))
        element = Massing(
            id=self._claim("steps", id),
            layer=layer,
            solids=[block(box, faces) for box in boxes],
            note="steps",
            walkable=True,
            reachable=reachable,
            authored=AuthoredForm(
                "steps",
                materials=faces,
                toward=Facing.of(toward),
                base=base,
                steps=int(count),
                step_depth=float(depth),
                step_rise=float(height),
                width=float(width),
            ),
        )
        installed = self._install(element)
        ramp = stair_clip(base, count, depth, height, width, Facing.of(toward))
        if clip_ramp and ramp is not None:
            self.add_wedge(
                ramp,
                Facing.of(toward),
                CLIP,
                note=STAIR_CLIP,
                id=f"{installed.id}_clip",
                layer=layer,
            )
        return installed  # type: ignore[return-value]

    def add_room(
        self,
        bounds: Span,
        *,
        wall: float = 16.0,
        openings: Sequence[Aperture] = (),
        roofed: bool = True,
        materials: RoomMaterials | None = None,
        reachable: bool = True,
        sunlit: bool = False,
        wall_height: float | None = None,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Room:
        """``wall_height`` (open rooms only) stops the walls that far above
        the bottom of ``bounds``, so the sky and a backdrop show over them;
        a clip slab from the wall top to the
        top of ``bounds`` keeps players and zombies in."""
        if sunlit and roofed:
            raise BlueprintError(
                "a room can only be sunlit if it has no roof (roofed=False)"
            )
        shell = room_shell(bounds, wall, roofed=roofed, wall_height=wall_height)
        room = Room(
            id=self._claim("room", id),
            layer=layer,
            outer=bounds,
            thickness=wall,
            roofed=roofed,
            materials=materials or _default_room_materials(),
            shell=shell,
            reachable=reachable,
            sunlit=sunlit,
        )
        self._install(room)
        for aperture in openings:
            self.cut_opening(room, aperture)
        if wall_height is not None:
            from ..materials import CLIP

            top = bounds.maxs.z
            for piece in shell.pieces:
                if piece.side in (Side.BOTTOM, Side.TOP):
                    continue
                box = piece.box
                self.add_block(
                    Span.between(Point(box.mins.x, box.mins.y, box.maxs.z),
                                 Point(box.maxs.x, box.maxs.y, top)),
                    CLIP, reachable=False, id=f"{room.id}_clip_{piece.side.name.lower()}",
                    note="clip over a low open-air wall (add_room wall_height)")
        return room

    def cut_opening(self, room: Room, aperture: Aperture) -> Opening:
        """Add a hole to a room that already exists.

        Returns the :class:`Opening` handle a door can be hung in.
        """
        box = aperture_box(room.shell, aperture, room.thickness)
        for existing in room.aperture_boxes:
            if existing.overlaps(box, slack=0.0):
                raise OpeningDoesNotFit(
                    f"opening on the {aperture.side.name.lower()} wall of {room.id} "
                    "overlaps an opening already cut there"
                )
        room.apertures.append(aperture)
        room.aperture_boxes.append(box)
        return room.opening(len(room.apertures) - 1)

    def seal_opening(
        self,
        opening: Opening,
        *,
        material: FaceMaterials | Material | str = CLIP,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Massing:
        """Fill an opening with a solid pane, so it is seen through but not
        walked through.

        This is how a map says "look, do not enter": the hole through the wall
        is real, so the room beyond it is lit, textured and visible, while the
        pane stops the player and the zombies at the wall line.  Without it
        the only two states a wall has are open and absent -- a room nobody
        can reach has to be walled off completely, and then there is nothing
        to see.

        The default material is ``clip``, which the compiler turns into
        collision with nothing drawn on it, so the view through the hole is of
        the far room and not of a pane.  Name an art material instead for a
        doorway that has been bricked up, where the player is meant to see
        that it is filled.

        The pane spans the wall's full thickness, the same box a door leaf
        would get, and it is a static world brush: nothing moves it, and no
        price opens it.
        """
        faces = _as_face_materials(material)
        pane = Massing(
            id=self._claim("pane", id),
            layer=layer,
            solids=[block(opening.box, faces)],
            note=SEALED_OPENING,
            authored=AuthoredForm("pane", box=opening.box, materials=faces),
        )
        return self._install(pane)  # type: ignore[return-value]

    def add_yard(
        self,
        bounds: Span,
        attached_side: Side | Facing | str,
        *,
        wall: float = 16.0,
        materials: RoomMaterials | None = None,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Yard:
        side = _as_side(attached_side)
        shell = yard_shell(bounds, side, wall)
        yard = Yard(
            id=self._claim("yard", id),
            layer=layer,
            outer=bounds,
            attached=side,
            thickness=wall,
            materials=materials or _default_room_materials(),
            shell=shell,
        )
        return self._install(yard)  # type: ignore[return-value]

    def add_yard_vent(self, yard: Yard | str, *, size: float = 24.0,
                      id: str | None = None) -> Massing:
        """Open a sealed yard to the open air inside the sky shell.

        BO3's occlusion pass (Umbra, run by the linker) keeps the open air and
        one sealed pocket of air and drops every other sealed pocket as the
        inside of a solid: every link log reads ``Filtered N/N+2 inside
        clusters``.  A player standing in a dropped pocket sees floors and
        walls flicker away to the sky (a row of sealed start corridors does
        exactly this).  This cuts a ``size`` hole high in the
        yard's far wall, at its low end, and plugs it with clip: players and
        zombies are still held, nothing is drawn on the plug, and to Umbra the
        yard -- and every room whose window opens on it -- is open air.
        Check ``Z83``.
        """
        if isinstance(yard, str):
            found = self.find(yard)
            if not isinstance(found, Yard):
                raise BlueprintError(f"{yard!r} is not a yard")
            yard = found
        far = Facing.of(yard.attached).opposite.side
        pieces = yard.shell.of_side(far)
        if not pieces:
            raise BlueprintError(f"yard {yard.id} has no far wall to vent through")
        wall = pieces[0].box
        along = Axis.Y if far.axis is Axis.X else Axis.X
        inside = yard.interior
        low = inside.mins[along.index] + 8.0
        top = inside.maxs.z - 8.0
        if inside.maxs[along.index] - low < size or top - size < inside.mins.z:
            raise BlueprintError(f"yard {yard.id} is too small for a {size} vent")
        mins = wall.mins.with_axis(along, low).with_axis(Axis.Z, top - size)
        maxs = wall.maxs.with_axis(along, low + size).with_axis(Axis.Z, top)
        hole = Span.between(mins, maxs)
        yard.vents.append(hole)
        return self.add_block(hole, CLIP, reachable=False,
                              id=id or f"{yard.id}_vent",
                              note="clip plug in a yard's air vent (add_yard_vent, Z83)")

    def enclose(
        self,
        playable: Span | None = None,
        *,
        gap: float = 128.0,
        thickness: float = 32.0,
        sun_preset: str = "default_day",
        probe: bool = True,
        atmosphere=None,
        id: str | None = None,
    ) -> Enclosure:
        """The sky shell and the sun/umbra/fps volumes.  Exactly one per map.

        With ``playable=None`` the bounds are computed from every room, yard
        and terrain at commit time, so the caller cannot get them wrong.

        ``atmosphere`` (a :class:`zmforge.atmosphere.Atmosphere`) sets the sun
        preset, the sky model and the fog volume together, and overrides
        ``sun_preset`` when given.
        """
        if self.elements(Enclosure):
            raise BlueprintError("this map already has an enclosure")
        fog = skybox = lit_fog = grade = exposure_stops = None
        fog_time = 1.0
        if atmosphere is not None:
            sun_preset = atmosphere.sun_preset
            fog, skybox, fog_time = atmosphere.fog, atmosphere.skybox, atmosphere.fog_time
            lit_fog = getattr(atmosphere, "lit_fog", None)
            grade = getattr(atmosphere, "grade", None)
            exposure_stops = getattr(atmosphere, "exposure_stops", None)
        element = Enclosure(
            id=self._claim("enclosure", id),
            playable=playable,
            gap=gap,
            thickness=thickness,
            sun_preset=sun_preset,
            probe=probe,
            fog=fog,
            fog_time=fog_time,
            skybox=skybox,
            lit_fog=lit_fog,
            grade=grade,
            exposure_stops=exposure_stops,
        )
        return self._install(element)  # type: ignore[return-value]

    def playable_bounds(self) -> Span:
        """The union of everything a player can stand in."""
        boxes: list[Span] = []
        for room in self.elements(Room):
            boxes.append(room.outer)
        for yard in self.elements(Yard):
            boxes.append(yard.outer)
        for terrain in self.elements(Terrain):
            boxes.append(terrain.record.footprint)
        for massing in self.elements(Massing):
            for solid in massing.solids:
                boxes.append(_solid_bounds(solid))
        # Every model too: a misc_model outside the sky shell leaks the map
        # (zm_cemetery's backdrop trees, models since
        # then, stood past the shell the brush trees used to grow, and
        # cod2map64 wrote a leak line from one of them).  Rooms and massing
        # come first, so a map with nothing else still refuses below.
        if boxes:
            boxes.extend(_prop_bounds(self.elements(PropScatter)))
        if not boxes:
            raise BlueprintError(
                "the map has no geometry, so its playable bounds cannot be computed; "
                "pass explicit bounds to enclose()"
            )
        return Span.hull_of(boxes)

    def probe_boxes(self) -> list[tuple[str, Span]]:
        """The volume each reflection probe covers, and what it belongs to.

        One box per room, at the room's interior, because that is what the
        shipped content does: the 23 probes in ``zm_alien_isolation.map`` are
        room-sized boxes, not one box over the map and not the mod tools'
        unsized 144-unit template cube.  A map with no rooms at all -- terrain
        and massing only -- gets a single box over its playable bounds, so
        that it still ships the one probe a blank generated map ships.

        Nothing here reads :attr:`Enclosure.probe`: this says where probes go,
        the enclosure says whether any are emitted.

        **Indoor air is all inside an indoor probe (check ``Z88``).**  A
        point in no probe box is lit, and exposed, by the sun volume's global
        probe: the outdoor one (``t7.def.json``: ``volume_sun``
        ``global_fill_color`` fills "occluded parts of the global probe";
        ``reflection_probe`` ``evcomp`` is "EV compensation to final probe
        exposure", so a probe carries an exposure of its own).  Boxes at the
        bare interiors left every doorway's wall-thick threshold and every
        barricade closet (:class:`Yard`) in no box, so the rooms are indoor
        boxes joined through slices of "outdoors" and the closets are outdoors
        entirely (a bright flash walking between rooms, blown-out closets).  So a roofed room's box reaches through its
        own walls (grown by its wall thickness across the floor plan, where
        the neighbour's box meets it), and each closet gets its own box.  An
        unroofed (outdoor) room keeps its interior box: the indoor side owns
        the threshold, and the outdoor areas of the cemetery and the corn maze
        are lit as before.
        """
        rooms = self.elements(Room)
        if rooms:
            boxes = [
                (room.id, _indoor_probe_box(room) if room.roofed else room.interior)
                for room in rooms
            ]
            boxes += [(yard.id, yard.interior) for yard in self.elements(Yard)]
            return boxes
        try:
            return [("enclosure", self.playable_bounds())]
        except BlueprintError:
            return []

    def resolve_enclosure(self) -> Enclosure | None:
        """Fill in the enclosure's cage from the current geometry."""
        found = self.elements(Enclosure)
        if not found:
            return None
        enclosure = found[0]
        assert isinstance(enclosure, Enclosure)
        playable = enclosure.playable or self.playable_bounds()
        enclosure.cage = sky_cage(playable, enclosure.gap, enclosure.thickness)
        return enclosure

    def add_terrain(
        self,
        heightfield,
        anchor: Point,
        cell: float,
        *,
        style: str = "mesh",
        material: Material | str = "t7_dirt_grassy_forest_ground",
        chunk: int = 8,
        lift: float = 2.0,
        post=None,
        bands: Sequence[tuple[float, Material | str]] = (),
        texture_scale: float = 128.0,
        id: str | None = None,
        layer: str = DEFAULT_LAYER,
    ) -> Terrain:
        if style not in ("mesh", "columns"):
            raise BlueprintError(f"unknown terrain style {style!r}")
        field_ = heightfield
        anchor, cell, cell_down = self._terrain_fitted_to_its_room(
            field_, Point.of(anchor), float(cell)
        )
        if post is not None:
            field_ = post.applied_to(field_, anchor, cell, cell_down)
        if lift:
            field_ = field_.lifted(lift)
        record = TerrainRecord(
            anchor=anchor,
            cell=cell,
            cell_y=None if cell_down == cell else cell_down,
            heights=field_,
            style=style,
            settings={
                "chunk": chunk,
                "lift": lift,
                "material": str(material),
                "texture_scale": texture_scale,
            },
        )
        terrain = Terrain(
            id=self._claim("terrain", id),
            layer=layer,
            record=record,
            style=style,
            material=Material.of(material),
            chunk=chunk,
            lift=lift,
            bands=[(z, Material.of(m)) for z, m in bands],
            texture_scale=texture_scale,
        )
        if style == "mesh":
            terrain.grids = mesh_chunks(field_, anchor, cell, chunk, cell_y=cell_down)
        else:
            terrain.runs = column_runs(field_, anchor, cell, cell_y=cell_down)
        return self._install(terrain)  # type: ignore[return-value]

    def _terrain_fitted_to_its_room(
        self, field_, anchor: Point, cell: float
    ) -> tuple[Point, float, float]:
        """Stretch a heightfield meant as a room's ground onto that interior.

        A grid written as "anchor, then N cells of this size" only meets the
        walls when the interior happens to be a whole number of cells across,
        and where it falls short the leftover strip has no ground in it at
        all.  Anything standing there is placed on the terrain and stands on
        the floor slab far below: measured on a test map, a mesh that
        stopped 8 units short of one wall and 24 short of the other left a row
        of 37 props along that wall hanging 55 to 70 units in the air.

        So the extents come from the room rather than from the call.  A field
        that already reaches within one cell of every wall is taken to *be*
        that room's ground and is stretched the rest of the way, which needs
        one spacing per axis, because the row and column count is the caller's
        and the interior need not be square.  A field further off than that is
        a patch of ground inside a room -- a mound, a verge -- and is left
        exactly where it was put.
        """
        requested = Span.flat_ok(
            anchor,
            Point(
                anchor.x + field_.cols * cell,
                anchor.y + field_.rows * cell,
                anchor.z,
            ),
        )
        interior = self.ground_room_of(requested, anchor.z, cell + 1e-6)
        if interior is None:
            return anchor, cell, cell
        across = interior.extent(Axis.X) / field_.cols
        along = interior.extent(Axis.Y) / field_.rows
        fitted = Point(interior.mins.x, interior.mins.y, anchor.z)
        if across == cell and along == cell and fitted == anchor:
            return anchor, cell, cell
        return fitted, across, along

    def ground_room_of(
        self, requested: Span, floor_z: float, slack: float
    ) -> Span | None:
        """The interior the XY rectangle ``requested`` is the ground of.

        The smallest room or yard whose floor the rectangle sits on and whose
        walls it comes within ``slack`` of on all four sides.  Smallest,
        because a yard dug outside a room wall lies inside that room's own
        outer box as well, and the tighter of the two is the one whose walls
        the ground has to meet.  ``None`` says the rectangle is a patch of
        ground inside a room rather than the room's whole floor.
        """
        best: Span | None = None
        for element in (*self.elements(Room), *self.elements(Yard)):
            interior = element.interior
            if not (
                interior.mins.z - STEP_TOLERANCE
                <= floor_z
                <= interior.maxs.z + STEP_TOLERANCE
            ):
                continue
            if any(
                abs(mine - theirs) > slack
                for mine, theirs in (
                    (requested.mins.x, interior.mins.x),
                    (requested.maxs.x, interior.maxs.x),
                    (requested.mins.y, interior.mins.y),
                    (requested.maxs.y, interior.maxs.y),
                )
            ):
                continue
            if best is None or (
                interior.extent(Axis.X) * interior.extent(Axis.Y)
                < best.extent(Axis.X) * best.extent(Axis.Y)
            ):
                best = interior
        return best

    # ------------------------------------------------------------------
    # Ground queries
    # ------------------------------------------------------------------
    def ground_under(
        self, x: float, y: float, *, below: float | None = None
    ) -> GroundHit:
        """Height of the walkable surface under ``(x, y)``.

        Three kinds of surface answer: terrain, the top of a walkable massing
        solid (a floor slab, a step, a bridge deck) and a room or yard floor.
        Terrain wins over the room floor it was laid on top of, and a platform
        wins over both when it is higher, so a map with more than one storey
        can place a spawn, a machine or a wall buy upstairs.

        ``below`` is the Z of the thing being placed.  Surfaces more than
        :data:`STEP_TOLERANCE` above it are not what it stands on, which is
        what stops a mezzanine answering for the ground floor beneath it.
        With no hint the highest surface wins.  When every surface is above
        the hint the highest is still returned, so a caller asking about a
        point in mid-air gets the real geometry and the distance to it rather
        than "nothing below".
        """
        candidates: list[GroundHit] = []
        terrain_found = False
        for terrain in self.elements(Terrain):
            sample = terrain.record.sample(x, y)
            if sample.found:
                terrain_found = True
                candidates.append(
                    GroundHit(
                        True,
                        sample.z,
                        f"terrain {terrain.id}",
                        sample.spread,
                        terrain.id,
                    )
                )
        for massing in self.elements(Massing):
            if not massing.walkable:
                continue
            for solid in massing.solids:
                box = _solid_bounds(solid)
                if box.holds_flat(x, y):
                    candidates.append(
                        GroundHit(
                            True,
                            box.maxs.z,
                            f"platform {massing.id}",
                            0.0,
                            massing.id,
                            massing.reachable,
                        )
                    )
        if not terrain_found:
            for room in self.elements(Room):
                if room.interior.holds_flat(x, y):
                    candidates.append(
                        GroundHit(True, room.floor_z, f"room {room.id}", 0.0, room.id)
                    )
            for yard in self.elements(Yard):
                if yard.interior.holds_flat(x, y):
                    candidates.append(
                        GroundHit(True, yard.floor_z, f"yard {yard.id}", 0.0, yard.id)
                    )
        if not candidates:
            return GroundHit(False, 0.0, "nothing below")
        under = candidates
        if below is not None:
            allowed = [hit for hit in candidates if hit.z <= below + STEP_TOLERANCE]
            under = allowed or candidates
        return max(under, key=lambda hit: hit.z)

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------
    def set_player_start(
        self,
        position: Point,
        facing: Facing | str = Facing.EAST,
        *,
        spread: float = 32.0,
        slots: int = STOCK_PLAYER_SLOTS,
        points: Sequence[Point] = (),
        id: str | None = None,
    ) -> PlayerStart:
        """Place the whole spawn set.  Calling again replaces it (K1).

        ``slots`` is how many players get their own initial-spawn struct, and
        it is the only number in a map that follows the player count.  Four
        is a stock game.  Above four the script plan also turns the
        framework's player-count check off
        (:attr:`ScriptPlan.lift_player_cap`), because the structs on their
        own do not seat the fifth player: ``_zm.gsc:7067`` freezes everyone
        and ends the game instead.  Asking for four again turns it back off,
        so the pair never disagrees.

        ``points``, when given, is one explicit point per slot instead of
        the row laid out round ``position`` (which then only places the
        respawn struct); see :attr:`PlayerStart.points`.

        Above four the emitted scripts also re-do the per-player
        registrations the stock scripts only did four of.

        Two things this cannot reach.  Only four playable characters exist,
        so players five and up share character 0.  And the *lobby's* own
        client limit is LUI, which a usermap cannot carry at all: the linker
        on the mod tools install answers a Lua raw file with ``ERROR: Lua not
        supported`` and fails the link (both on
        Windows and under Wine).  See ``docs/developer-guide.md``, "Eight-player maps".
        """
        for existing in self.elements(PlayerStart):
            self._elements.remove(existing)
            self._by_id.pop(existing.id, None)
        element = PlayerStart(
            id=self._claim("player_start", id or "player_start"),
            position=position,
            facing=Facing.of(facing),
            spread=spread,
            slots=slots,
            points=tuple(points),
        )
        element.slot_positions()  # refuses a points list that does not match slots
        self.script.lift_player_cap = element.slots > STOCK_PLAYER_SLOTS
        self.script.player_slots = element.slots
        return self._install(element)  # type: ignore[return-value]

    def add_zone(
        self,
        name: str,
        bounds: Span | Room,
        *,
        starting: bool = False,
        spawn_set: str | None = None,
        id: str | None = None,
    ) -> Zone:
        """Register a named playable volume.

        A :class:`Room` gives its **outer** box, walls included, not its
        interior.  The interior stops at the inside face of the wall, so two
        rooms sharing a wall leave a band of their two wall thicknesses --
        32 units here -- that belongs to no zone, and the doorway through it
        is in that band.  A player is 30 units across (``PLAYER_RADIUS 15``,
        ``scripts/shared/player_shared.gsc:15`` and
        ``scripts/zm/_zm_unitrigger.gsc:20``; the bot debug box is drawn
        ``(-15,-15,0)..(15,15,72)``, ``scripts/shared/bots/_bot.gsc:741``),
        so standing in the middle of that band the player touches neither
        volume, ``zm::in_enabled_playable_area`` returns false, and the
        out-of-playable-area monitor (``_zm.gsc:2035``, every 3 seconds)
        does ``health + 1000`` damage with bleedout set to zero: an instant
        death, not a down.  Outer boxes of adjacent rooms meet on the wall's
        centre plane, so the band is covered from both sides and nothing is
        left over.
        """
        box = bounds.outer if isinstance(bounds, Room) else bounds
        if starting:
            for zone in self.elements(Zone):
                if zone.starting and zone.name != name:  # type: ignore[attr-defined]
                    raise BlueprintError(
                        f"zone {zone.name!r} is already the starting zone"  # type: ignore[attr-defined]
                    )
        zone = Zone(
            id=self._claim("zone", id or f"zone_{name}"),
            name=name,
            bounds=box,
            starting=starting,
            spawn_set=spawn_set or "",
        )
        self._install(zone)
        self._resync_zone_list()
        return zone

    def _resync_zone_list(self) -> None:
        """``init_zones`` carries zone *names*, and a zone may own several volumes.

        Stock ``zone_init`` (``_zm_zonemgr.gsc:286``) returns immediately for a
        zone it has already made, and builds ``zone.volumes`` from
        ``GetEntArray( zone_name, "targetname" )`` (``:318``), so every volume
        carrying the name joins the one zone and listing the name twice does
        nothing.  Treyarch's ``map_source/zm/zm_giant.map`` carries 32 player
        volumes over 12 zone names against the single ``init_zones[0] =
        "receiver_zone";`` of ``zm_giant.gsc:183``.
        """
        zones = [z for z in self.elements(Zone)]
        names: list[str] = []
        for zone in zones:
            if zone.starting and zone.name not in names:  # type: ignore[attr-defined]
                names.append(zone.name)  # type: ignore[attr-defined]
        for zone in zones:
            if not zone.starting and zone.name not in names:  # type: ignore[attr-defined]
                names.append(zone.name)  # type: ignore[attr-defined]
        self.script.zones = names

    def zone_named(self, name: str) -> Zone:
        for zone in self.elements(Zone):
            if zone.name == name:  # type: ignore[attr-defined]
                return zone  # type: ignore[return-value]
        raise UnknownZone(f"no zone named {name!r}")

    def _zone_of(self, zone: Zone | str) -> Zone:
        return zone if isinstance(zone, Zone) else self.zone_named(zone)

    def add_riser(
        self,
        zone: Zone | str,
        position: Point,
        facing: Facing | Angles | str = Facing.NORTH,
        *,
        kind: str = "rise",
        factory: bool = True,
        link_tag: str = "find_flesh",
        allow_float: bool = False,
        id: str | None = None,
    ) -> Spawn:
        if kind not in SPAWN_MARKERS:
            raise BlueprintError(
                f"unknown spawn kind {kind!r}; the engine dispatches on the "
                f"script_noteworthy token and knows "
                f"{', '.join(sorted(SPAWN_MARKERS))}"
            )
        target = self._zone_of(zone)
        ground = self.ground_under(position.x, position.y, below=position.z)
        if not allow_float:
            if not ground.found:
                raise NotOnFloor(
                    f"no floor under ({position.x}, {position.y}); "
                    "a spawn struct in the void drops the zombie through the world"
                )
            delta = position.z - ground.z
            if delta < -0.5 or delta > 8.0:
                raise NotOnFloor(
                    f"spawn at z={position.z} is {delta:+.1f} from the surface at "
                    f"z={ground.z} ({ground.source}); spawns sit on the floor, "
                    "never above it"
                )
        spawn = Spawn(
            id=self._claim("spawn", id),
            zone_name=target.name,
            spawn_set=target.spawn_set,
            position=position,
            facing=_as_angles(facing),
            kind=kind,
            link_tag=link_tag,
            with_factory=factory,
        )
        return self._install(spawn)  # type: ignore[return-value]

    def add_window(
        self,
        zone: Zone | str,
        room: Room,
        side: Side | Facing | str,
        offset: float = 0.0,
        *,
        yard_depth: float | None = None,
        width: float = WINDOW_WIDTH,
        height: float = WINDOW_HEIGHT,
        sill: float = WINDOW_SILL,
        hide_debris: bool = False,
        light: bool = True,
        spawn_kind: str = "rise",
        id: str | None = None,
    ) -> Window:
        """Cut a barricade window and wire up everything it needs.

        One call does the hole, the yard outside it, the prefab at the wall's
        interior face, the riser 96 units out facing back, and a light in the
        yard, because getting any one of those coordinates wrong is a
        playtest wasted (spec 8.4, E3).

        A window here means a working zombie entry point.  For a hole that is
        only a hole -- a gap to see or shoot through, with no barricade and no
        spawn behind it -- use :meth:`cut_opening` with an
        :class:`~zmforge.solids.layout.Aperture`, which is what it has always
        been for and is deliberately not changed.

        ``width``, ``height`` and ``sill`` default to the hole the prefab's
        own brushes ask for and are refused if they do not contain its
        traversal channel: a barricade over a hole the zombies cannot reach
        looks right in the editor, compiles, links, and is dead in play.

        ``spawn_kind`` is the mode of the spawn struct outside the window and
        takes any key of :data:`~zmforge.blueprint.elements.SPAWN_MARKERS`.
        ``"rise"`` (``riser_location``) is the default and is what the mod
        tools' own ZM level template ships; ``"walk"`` (``spawn_location``)
        makes the zombie appear standing and walk in with no climb-out
        animation, which is what a yard feeding a traversal or an approach
        from off the map wants.  Both are ordinary barricade spawns to the
        engine -- ``move_zombie_spawn_location`` branches on the token and
        nothing else about the struct changes -- and Treyarch's own zm_giant
        uses ``spawn_location`` for 44 of its 50 barricade-tagged spawns
        against 8 risers.
        """
        target = self._zone_of(zone)
        wall_side = _as_side(side)
        if not wall_side.is_horizontal:
            raise BlueprintError("a window goes in a wall, not in the floor or ceiling")

        _refuse_a_blocked_traverse(width, height, sill)
        opening = self.cut_opening(
            room,
            Aperture(
                side=wall_side,
                width=width,
                height=height,
                sill=sill,
                offset=offset,
            ),
        )

        outward = Facing.of(wall_side)
        depth = DEFAULT_YARD_DEPTH if yard_depth is None else float(yard_depth)
        if depth < MIN_YARD_DEPTH:
            raise BlueprintError(
                f"a yard {depth} deep leaves no floor beyond the riser; "
                f"the shallowest that works is {MIN_YARD_DEPTH}"
            )
        yard = self._yard_for(room, wall_side, depth)

        interior_face = room.outer.face_plane(wall_side) - wall_side.sign * room.thickness
        origin = opening.box.centre.with_axis(wall_side.axis, interior_face)
        origin = Point(origin.x, origin.y, room.floor_z)
        barricade_yaw = prefab_yaw(outward, BARRICADE_EXTERIOR_ZERO)

        window_id = self._claim("window", id)
        link_tag = f"{window_id}_link"

        riser_origin = origin + outward.step.scaled(BARRICADE_RISER_REACH)
        riser_ground = self.ground_under(
            riser_origin.x, riser_origin.y, below=origin.z
        )
        riser_origin = Point(
            riser_origin.x,
            riser_origin.y,
            riser_ground.z if riser_ground.found else origin.z,
        )
        riser = self.add_riser(
            target,
            riser_origin,
            # Not the barricade's yaw plus 180.  A riser is an AI spawn, its
            # angles are a plain world heading, and the stock prefab shows what
            # that heading should be: barricade_reciever_wood's own
            # ``exterior_goal`` struct stands outside the window and faces
            # straight back at the barricade.  So does this one.
            Angles.facing_yaw(outward.opposite.world_yaw),
            kind=spawn_kind,
            factory=False,
            link_tag=link_tag,
            id=f"{window_id}_riser",
        )

        if light:
            # One dim warm lamp over this window's own riser, not a
            # full-strength one at the yard's centre: three windows on one
            # wall stack three there and blow the closet out to white
            # (blueprint/windows.py, check Z85).
            self.place_light(
                Point(riser_origin.x, riser_origin.y,
                      yard.outer.maxs.z - yard.thickness - 40.0),
                colour=CLOSET_LAMP_COLOUR,
                radius=CLOSET_LAMP_RADIUS,
                zone_name=target.name,
                id=f"{window_id}_light",
            )
        # A little clutter against the closet's far wall either side of the
        # riser, walk-through, so the space behind the boards is a place.
        clutter = [
            (CLOSET_PROPS[k % len(CLOSET_PROPS)], spot, float(k * 67 % 360))
            for k, spot in enumerate(closet_prop_spots(
                yard, origin, outward.step, BARRICADE_RISER_REACH, width / 2.0 + 40.0))
        ]
        if clutter:
            self.place_props(clutter, id=f"{window_id}_closet")

        element = Window(
            id=window_id,
            zone_name=target.name,
            room_id=room.id,
            side=wall_side,
            link_tag=link_tag,
            barricade_origin=origin,
            barricade_yaw=barricade_yaw,
            prefab=BARRICADE_PREFAB_HIDE_DEBRIS if hide_debris else BARRICADE_PREFAB,
            yard_id=yard.id,
            riser_id=riser.id,
            aperture_index=opening.index,
        )
        return self._install(element)  # type: ignore[return-value]

    def declare_barricade(
        self,
        room: Room | str,
        aperture_index: int,
        *,
        riser: Spawn | str,
        prefab: str = BARRICADE_PREFAB,
        zone: Zone | str | None = None,
        yard: Yard | str | None = None,
        id: str | None = None,
    ) -> Window:
        """Say that a hole already cut is a barricade window.

        :meth:`add_window` is the call for a caller that has nothing yet: it
        cuts the hole, digs the yard, stands the riser, hangs the light and
        hangs the boards, because getting any one of those coordinates wrong is
        a playtest wasted.  A caller that already holds the first four -- which
        is what a map editor's document is, where the hole is a room opening,
        the yard is blocks, the riser is a zombie spawner and the light is a
        light -- needs the fifth and the *declaration*, and calling
        ``add_window`` would give it a second yard and a second riser beside the
        ones already drawn.

        The origin and the heading are derived here from the room and the hole
        rather than passed in, so both calls put the prefab in the same place
        for the same wall.

        Without the declaration the boards are still written -- as a plain
        :class:`~zmforge.blueprint.elements.Prefab` -- and the map is refused
        for a reason that is not true: ``verify.check_nav_apertures`` exempts a
        hole from the navmesh width and height rules only when a ``Window``
        names it, because zombies cross a barricade by playing its traversal
        animation and not by walking, so the 96 x 48 hole the shipped recipes
        cut is legal on the recipe's side and two ``N3`` errors on the way back.
        """
        room_element = room if isinstance(room, Room) else self.find(room)
        if not isinstance(room_element, Room):
            raise BlueprintError(f"{room_element.id!r} is not a room")
        if not 0 <= aperture_index < len(room_element.apertures):
            raise BlueprintError(
                f"room {room_element.id!r} has no aperture {aperture_index}"
            )
        opening = room_element.opening(aperture_index)
        wall_side = opening.aperture.side
        if not wall_side.is_horizontal:
            raise BlueprintError("a window goes in a wall, not in the floor or ceiling")

        riser_element = riser if isinstance(riser, Spawn) else self.find(riser)
        if not isinstance(riser_element, Spawn):
            raise BlueprintError(f"{riser_element.id!r} is not a spawn struct")

        if yard is None:
            found = [
                y for y in self.elements(Yard)
                if y.interior.holds_flat(  # type: ignore[attr-defined]
                    riser_element.position.x, riser_element.position.y)
            ]
            yard_id = found[0].id if found else ""
        else:
            yard_id = yard.id if isinstance(yard, Yard) else str(yard)

        zone_name = (
            self._zone_of(zone).name if zone is not None else riser_element.zone_name
        )
        outward = Facing.of(wall_side)
        interior_face = (
            room_element.outer.face_plane(wall_side)
            - wall_side.sign * room_element.thickness
        )
        origin = opening.box.centre.with_axis(wall_side.axis, interior_face)
        element = Window(
            id=self._claim("window", id),
            zone_name=zone_name,
            room_id=room_element.id,
            side=wall_side,
            link_tag=riser_element.link_tag,
            barricade_origin=Point(origin.x, origin.y, room_element.floor_z),
            barricade_yaw=prefab_yaw(outward, BARRICADE_EXTERIOR_ZERO),
            prefab=prefab,
            yard_id=yard_id,
            riser_id=riser_element.id,
            aperture_index=aperture_index,
        )
        return self._install(element)  # type: ignore[return-value]

    def _yard_for(self, room: Room, wall_side: Side, depth: float) -> Yard:
        """Reuse a yard already covering the spot, else dig one."""
        outer_face = room.outer.face_plane(wall_side)
        probe = room.outer.centre.with_axis(
            wall_side.axis, outer_face + wall_side.sign * (depth / 2.0)
        )
        for yard in self.elements(Yard):
            if yard.outer.holds_flat(probe.x, probe.y):  # type: ignore[attr-defined]
                return yard  # type: ignore[return-value]
        axis = wall_side.axis
        near = outer_face
        far = outer_face + wall_side.sign * depth
        low, high = (near, far) if far > near else (far, near)
        bounds = Span.between(
            room.outer.mins.with_axis(axis, low),
            room.outer.maxs.with_axis(axis, high),
        )
        return self.add_yard(bounds, Facing.of(wall_side).opposite.side, wall=room.thickness,
                             materials=_closet_materials())

    def stair_gate_box(self, steps: Massing | str, *,
                       gate_height: float = STAIR_GATE_HEIGHT) -> Span:
        """The free span across the head of ``steps``, for a door to fill.

        Read off the flight's :class:`~zmforge.blueprint.elements.AuthoredForm`
        -- the call that built it -- rather than off its boxes, so it is the same
        arithmetic :func:`~zmforge.solids.forms.stair_gate` does and the same one
        a map editor does from the flight in the editor's document.  That is what
        lets a gate cross between the two as the id of a flight.
        """
        element = steps if isinstance(steps, Massing) else self.find(steps)
        authored = getattr(element, "authored", None)
        if authored is None or authored.form != "steps":
            raise BlueprintError(
                f"a stair gate needs a flight of stairs, and {element.id!r} is not one"
            )
        return stair_gate(
            authored.base, authored.steps, authored.step_depth, authored.step_rise,
            authored.width, authored.toward, gate_height=gate_height,
        )

    def add_stair_gate(
        self,
        between: tuple[Zone | str, Zone | str],
        steps: Massing | str,
        *,
        gate_height: float = STAIR_GATE_HEIGHT,
        **door,
    ) -> Door:
        """A buyable door across the head of a flight of stairs.

        A zone stacked over another one -- a balcony over the hall it looks
        into -- has no wall between it and the zone below, so the door that sells
        it hangs in the air over the flight's head instead of in a doorway.  This
        is :meth:`add_door` with the box derived from the flight rather than
        written out, which is what keeps the gate recognisable afterwards: both
        this package's editor translator and a map editor that reads the
        document compute the same box from the same flight, so the document carries ``stairs: <flight id>`` and
        nothing has to be inferred from six loose numbers.
        """
        gate = self.add_door(between, self.stair_gate_box(steps, gate_height=gate_height),
                             **door)
        gate.framed = False  # no wall either side: the leaf grows up, not out (Z81)
        return gate

    def add_door(
        self,
        between: tuple[Zone | str, Zone | str],
        at: Opening | Span,
        *,
        price: int = 1000,
        flag: str | None = None,
        model: str | None = fixed.DEFAULT_DOOR_MODEL,
        slide: Point | None = None,
        trigger_depth: float = DOOR_TRIGGER_DEPTH,
        trigger_margin: float = DOOR_TRIGGER_MARGIN,
        electric: bool = False,
        requires_power: bool = False,
        id: str | None = None,
    ) -> Door:
        """A buyable door between two zones.  ``electric`` opens it free when
        the power comes on; ``requires_power`` keeps it unbuyable (the stock
        "power required" hint) until the power is on, then sells it at
        ``price``.  ``Z80`` fails a map whose power switch sits behind either."""
        if electric and requires_power:
            raise BlueprintError("a door is electric (opens with the power) or "
                                 "requires power (bought after it), not both")
        zone_a = self._zone_of(between[0])
        zone_b = self._zone_of(between[1])
        box = at.box if isinstance(at, Opening) else at
        thin_axis = _thinnest_axis(box)
        door = Door(
            id=self._claim("door", id),
            zone_a=zone_a.name,
            zone_b=zone_b.name,
            box=box,
            price=int(price),
            flag=flag or f"enter_{zone_b.name}",
            model=model,
            slide=slide,
            trigger_depth=trigger_depth,
            trigger_margin=trigger_margin,
            model_yaw=90.0 if thin_axis is Axis.X else 0.0,
            electric=electric,
            requires_power=requires_power,
        )
        self._install(door)
        self.script.edges.append(ZoneEdge(zone_a.name, zone_b.name, door.flag))
        return door

    def place_perk(
        self,
        kind: str | PerkKind,
        position: Point,
        facing: Facing | str,
        *,
        id: str | None = None,
    ) -> Machine:
        perk = kind if isinstance(kind, PerkKind) else perk_named(kind)
        machine = Machine(
            id=self._claim("machine", id),
            perk=perk,
            position=position,
            facing=Facing.of(facing),
        )
        self._install(machine)
        if perk.module:
            self.script.perk_modules.append(perk.module)
        if perk.specialty and perk.module:
            # Both halves matter.  The specialty is the name Der Wunderfizz
            # would offer; the module is what writes
            # ``level.machine_assets[<specialty>]``, without which the
            # Wunderfizz has nothing to render (_zm_perk_random.gsc:725).
            # Recorded whether or not a Wunderfizz is ever placed, so the
            # recipe may place them in either order.
            self.script.perk_rotation.append(perk.specialty)
        return machine

    def declare_perk(self, perk: CustomPerk) -> str:
        """Ship a perk of this map's own, without placing a machine for it.

        Three things go together and this is where they are kept together,
        because any one of them alone is a perk that does not work: the five
        registration calls in the map's own script
        (:func:`zmforge.script.perks.perk_script`), the prompt in the map's
        ``.str`` with the ``localize`` line in the manifest behind it, and the
        ``#precache`` of both the prompt and the machine light.  Returns the
        linker's name for the prompt asset.

        Declaring is idempotent per perk and refuses two kinds of collision
        outright, because both are silent in game:

        * **two perks under one specialty**, which the framework resolves by
          keeping whichever registered first (``_zm_perks.gsc:1903`` and its
          neighbours) and saying nothing;
        * **two perks claiming one HUD slot**, which is one widget being told
          two different things by two ``set_player_uimodel`` calls; whichever
          ran last wins, and the other perk has no icon.

        Nothing about a custom perk is verified in game.
        """
        try:
            clash = perk_named(perk.slug)
        except KeyError:
            clash = None
        if clash is not None:
            raise BlueprintError(
                f"{perk.slug!r} is already the slug of a machine the mod tools install "
                f"ships ({clash.slug}); two machines under one slug read the "
                "same in every finding this package prints, so give the perk a "
                "name of its own"
            )
        for existing in self.custom_perks:
            if existing == perk:
                return string_asset(self.name, perk.reference)
            if existing.specialty == perk.specialty:
                raise BlueprintError(
                    f"this map already ships a perk called {existing.name!r} "
                    f"under {perk.specialty!r}; the framework keeps the first "
                    "registration and ignores the second (_zm_perks.gsc:1903)"
                )
            if (
                perk.icon is not None
                and existing.icon is not None
                and existing.icon.path == perk.icon.path
            ):
                raise BlueprintError(
                    f"{perk.name} and {existing.name} both claim the "
                    f"{perk.icon.key} HUD slot ({perk.icon.path}); one widget "
                    "cannot show two perks, so give one of them the other "
                    "unclaimed slot or no icon at all"
                )
        asset = string_asset(self.name, perk.reference)
        self.custom_perks.append(perk)
        if perk.icon is not None and perk.icon_art is not None:
            from ..texture.hud_icons import art_png

            self.ship_hud_image(perk.icon.image, art_png(perk.icon_art))
        self.declare_asset("localize", self.name)
        if asset not in self.script.perk_hints:
            self.script.perk_hints.append(asset)
        # The machine light is a stock effect and is **not** declared as an
        # asset: it is already in the level-common zone, so a manifest line
        # would ask the linker to pack a second copy.  What it does need is
        # the handle, which comes from the #precache directive in both
        # scripts and nowhere else -- the same rule every stock perk module
        # follows (_zm_perk_juggernaut.gsc:29 against .csc:16).
        if perk.light_fx not in self.script.precache_fx:
            self.script.precache_fx.append(perk.light_fx)
        self.add_custom_logic(perk_script(perk, asset))
        return asset

    def place_custom_perk(
        self,
        perk: CustomPerk,
        position: Point,
        facing: Facing | str,
        *,
        id: str | None = None,
    ) -> Machine:
        """A machine selling a perk this repository wrote.

        The machine is the same one Widow's Wine gets -- one ``script_struct``
        with a model, the specialty in ``script_noteworthy`` and
        ``targetname zm_perk_machine`` -- so it is placed through the same
        call as a stock perk and answers to the same reachability, clearance
        and facing checks.  The perk itself is declared on the first
        placement; a second machine for the same perk is a second machine and
        not a second registration, which is what a map with two of them wants.

        A custom perk is **not** offered by Der Wunderfizz.  The rotation is
        built from perks whose module the script carries
        (:meth:`place_perk`), and this perk has no module: its script is the
        map's own.  Asking for it in a rotation is a question for check Z49,
        which reads the written files.
        """
        self.declare_perk(perk)
        kind = PerkKind(
            perk.slug,
            None,
            None,
            xmodel=perk.machine_model,
            specialty=perk.specialty,
            front_zero=perk.front_zero,
        )
        return self.place_perk(kind, position, facing, id=id)

    def place_pack_a_punch(
        self, position: Point, facing: Facing | str, *, id: str | None = None
    ) -> Machine:
        return self.place_perk("pack_a_punch", position, facing, id=id)

    def place_power_switch(
        self, position: Point, facing: Facing | str, *, id: str | None = None
    ) -> PowerSwitch:
        element = PowerSwitch(
            id=self._claim("power", id),
            position=position,
            facing=Facing.of(facing),
        )
        return self._install(element)  # type: ignore[return-value]

    def place_prefab(
        self,
        model: str,
        position: Point,
        facing: Facing | str = Facing.SOUTH,
        *,
        yaw: float | None = None,
        script_string: str = "",
        id: str | None = None,
    ) -> Prefab:
        """Put a stock prefab down, and nothing else.

        This is what :meth:`place_perk`, :meth:`place_mystery_box` and
        :meth:`place_power_switch` each emit *besides* their own wiring: one
        ``misc_prefab`` with a model, an origin and an angle.  Those three know
        what else their prefab needs; this one deliberately knows nothing, so
        it registers no script module, no zone and no zone edge, and a map that
        uses it plays exactly as it did without it.

        ``model`` is the prefab path relative to ``map_source/``, e.g.
        ``_prefabs/zm/zm_core/power_switch.map``.  ``yaw`` overrides the
        appendix-B prefab convention for a prefab whose zero heading the caller
        has established is not south.

        ``script_string`` is the one token some stock prefabs are wired with
        and nothing else about them says: a barricade's is the link tag its
        riser carries, and the two are joined by that string and by nothing
        else.  :meth:`add_window` writes the pair itself; this is how a caller
        that already has the hole, the yard and the riser -- which is what a
        map edited in a map editor is -- puts the barricade back.
        """
        path = str(model).strip()
        if not path or any(ch.isspace() for ch in path):
            raise BlueprintError(f"a prefab needs a path with no spaces, got {model!r}")
        if not path.endswith(".map"):
            raise BlueprintError(
                f"a prefab model is a .map path relative to map_source/, got {path!r}"
            )
        element = Prefab(
            id=self._claim("prefab", id),
            model=path,
            position=Point.of(position),
            facing=Facing.of(facing),
            yaw=None if yaw is None else float(yaw),
            script_string=str(script_string or ""),
        )
        return self._install(element)  # type: ignore[return-value]

    def place_wall_weapon(
        self,
        kind: str,
        position: Point,
        facing: Facing | str,
        *,
        chalk_material: Material | str | None = None,
        price: int | None = None,
        id: str | None = None,
    ) -> WallWeapon:
        """Place a stock spawnable-weapon prefab against a wall.

        ``chalk_material`` names the outline decal's material and is optional
        because it cannot be derived: the decal is keyed by the game's weapon
        name, the prefab by a class slug, and a name built from the slug is
        not in the asset database.

        ``price`` is what this buy charges.  Left ``None`` the buy charges
        whatever Treyarch's table says and the map ships no table of its own,
        which is exactly the map this method emitted before the option
        existed.  Given a number, the map ships its own weapon table
        (:mod:`zmforge.emit.weapons`) carrying that weapon's stock row with
        the cost replaced, and both generated scripts learn to load it.  The
        *name* on the prompt is not negotiable and never has been (spec 5.7):
        price yes, name no.
        """
        wall_weapon_prefab(kind)  # validates the slug
        from ..dressing.lining import lined_face_at

        if lined_face_at(position, Facing.of(facing), getattr(self, "lined_faces", ()) or ()) is not None:
            # A buy chalked on a wall lined with plants clears the plants in
            # front of it and shows bare wall there:
            # zmforge.placement.wallbuy.place_wall_buy finds a real wall.
            raise BlueprintError(
                f"{id or kind}: a wall buy may not hang on a lined face (bp.lined_faces); "
                "use placement.wallbuy.place_wall_buy, which picks the nearest unlined wall"
            )
        element = WallWeapon(
            id=self._claim("wallbuy", id),
            slug=kind,
            position=position,
            facing=Facing.of(facing),
            chalk_material=Material.of(chalk_material) if chalk_material else None,
            price=None if price is None else int(price),
        )
        if element.price is not None:
            if element.price < 0:
                raise BlueprintError(
                    f"{element.id}: a wall buy price may not be negative"
                )
            self._ship_weapon_table()
        return self._install(element)  # type: ignore[return-value]

    def place_mystery_box(
        self,
        position: Point,
        facing: Facing | str = Facing.SOUTH,
        *,
        price: int = fixed.DEFAULT_CHEST_COST,
        starting: bool = True,
        chest_name: str | None = None,
        id: str | None = None,
    ) -> MysteryBox:
        name = chest_name or (
            fixed.DEFAULT_CHEST_NAME if starting else f"chest_{len(self.elements(MysteryBox))}"
        )
        element = MysteryBox(
            id=self._claim("box", id),
            chest_name=name,
            position=position,
            facing=Facing.of(facing),
            price=int(price),
            starting=starting,
        )
        self._install(element)
        if starting:
            self.script.chest_name = name
        return element  # type: ignore[return-value]

    def place_wunderfizz(
        self,
        position: Point,
        facing: Facing | str = Facing.SOUTH,
        *,
        rotation: Sequence[str] | None = None,
        id: str | None = None,
    ) -> Wunderfizz:
        """Der Wunderfizz, the machine that sells a random perk.

        The first one placed is the machine the stock script starts on
        (:attr:`~zmforge.blueprint.elements.Wunderfizz.starting`); later ones
        are the places it can move to.

        ``rotation`` is what it may hand out, as ``specialty_`` strings or as
        perk slugs -- ``"juggernog"`` and ``"specialty_armorvest"`` both
        work.  Left out, it is **every perk the map places**, which is the
        behaviour a recipe wants by default and the only one that is safe by
        construction: a perk on the map is a perk module in the script, and a
        perk module is what fills in ``level.machine_assets`` for the bottle
        the machine shows (``_zm_perk_random.gsc:725-733``).  Passing a list
        turns that guarantee off, so check Z49 asks the question again of the
        written files.

        Nothing about this is verified in game.
        """
        element = Wunderfizz(
            id=self._claim("wunderfizz", id),
            position=position,
            facing=Facing.of(facing),
            starting=not self.elements(Wunderfizz),
        )
        self._install(element)
        self.script.wunderfizz = True
        if rotation is not None:
            named: list[str] = []
            for entry in rotation:
                if entry.startswith("specialty_"):
                    named.append(entry)
                    continue
                perk = fixed.perk_named(entry)
                if not perk.specialty:
                    raise ValueError(
                        f"{perk.slug} has no specialty string, so Der "
                        "Wunderfizz cannot offer it"
                    )
                named.append(perk.specialty)
            self.script.wunderfizz_rotation = named
        return element  # type: ignore[return-value]

    def place_light(
        self,
        position: Point,
        colour: tuple[float, float, float] = (1.0, 1.0, 1.0),
        radius: float = 512.0,
        stops: float | None = None,
        *,
        zone_name: str | None = None,
        shadows: bool = True,
        id: str | None = None,
    ) -> Lamp:
        """One omni light.

        ``stops`` left at ``None`` takes the brightness the map's own sun/sky
        preset calls for (:func:`zmforge.lighting.default_stops`), which is
        the only way to get it right: the key is log2 of an intensity and it
        is meaningless except against the exposure the preset sets.  Pass a
        float only to override a single lamp deliberately, and expect the
        conformance check to say so if it lands outside the band the shipped
        maps use.
        """
        element = Lamp(
            id=self._claim("light", id),
            position=position,
            colour=colour,
            radius=radius,
            stops=stops,
            zone_name=zone_name,
            shadows=shadows,
        )
        return self._install(element)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Lighting
    # ------------------------------------------------------------------
    @property
    def exposure(self) -> float:
        """The ``ev`` of the sun/sky preset this map is exposed for.

        Taken from the enclosure, because that is where the preset is named
        (:meth:`enclose`); a map with no enclosure yet is treated as the
        default preset, which is also what ``enclose`` would give it.
        """
        found = self.elements(Enclosure)
        preset = (
            found[0].sun_preset  # type: ignore[attr-defined]
            if found
            else lighting.DEFAULT_SSI
        )
        return lighting.exposure_of(preset)

    def stops_of(self, lamp: Lamp) -> float:
        """The ``stops`` value a lamp is actually emitted with.

        Its own if it names one, this map's exposure if it does not, plus the
        blueprint's overall brightness offset either way.  One function, so
        the emitter, the checker and any report agree by construction.
        """
        base = self.exposure + lighting.STOPS_OVER_EXPOSURE if lamp.stops is None else lamp.stops
        return base + self.brightness_stops

    def light_rooms(
        self,
        *,
        spacing: float = lighting.MAX_LAMP_SPACING,
        clearance: float = lighting.CEILING_CLEARANCE,
        radius: float | None = None,
        colour: tuple[float, float, float] | None = None,
    ) -> list[Lamp]:
        """Top every room up to the lamp density the shipped maps carry.

        A hand-placed lamp per room is one lamp per room however big the room
        is: a four-storey map lit that way measured one lamp per 521 x 521
        units of footprint against The Giant's 226 x 226, and it read as dark
        whatever the intensity.  This
        walks a grid no coarser than ``spacing`` over each room's interior
        and adds a lamp wherever the room has none within that distance in
        plan, so a small room keeps its single hand-placed lamp and a hall
        gets the several it needs.

        Lamps hang ``clearance`` below the ceiling's underside, never inside
        the slab (spec 4.11), and a grid point that falls inside a world
        solid -- a pier, a stair, a counter -- is skipped rather than buried.
        Colour and radius default to those of the nearest hand-placed lamp
        in the same room, so a room the recipe made cold stays cold.

        **A tall room gets more than one storey of lamps.**  A grid laid once,
        at the ceiling, is only a lighting rule in a room short enough for the
        ceiling to reach the floor.  Measured: in a room 896 units tall, with
        its lamps hung 484 to 856 above the floor, the floor comes out three
        stops under rooms of ordinary height.  So the grid is repeated down the room at the same
        ``spacing`` it already uses in plan, which makes the rule the same on
        all three axes; :meth:`_lamp_tiers` carries the measurement that says
        ``spacing`` is the right number for z as well.  A room shorter than one
        step is unchanged, which is 22 of that map's 25 rooms.

        Fill lamps are placed with ``shadows=False``.  They exist to raise the
        light level, and a map may only hold ``numOmniShadowSlices`` run-time
        omni shadows at once; letting every fill lamp ask for one is what makes
        a shadow appear and vanish as the player walks.  The Giant casts from
        42 of its 280 omni lights.

        Idempotent: running it twice adds nothing the second time.  Call it
        after the geometry and the deliberate lamps are in.
        """
        from ..solids.halfspace import plane_through

        planes = [
            (solid, [plane_through(*face.points) for face in solid.faces])
            for solid in self.world_solids()
        ]

        def buried(point: Point) -> bool:
            for probe in (point, point.with_axis(Axis.Z, point.z - clearance / 2.0)):
                for _solid, faces in planes:
                    if min(face.depth_at(probe) for face in faces) > 1e-6:
                        return True
            return False

        added: list[Lamp] = []
        for room in self.elements(Room):
            if room.sunlit:  # type: ignore[attr-defined]
                continue  # the sun lights it; see Room.sunlit
            interior = room.interior  # type: ignore[attr-defined]
            ceiling = room.shell.ceiling_underside_z  # type: ignore[attr-defined]
            z = ceiling - clearance
            if z <= room.floor_z:  # type: ignore[attr-defined]
                continue
            # A lamp counts as this room's only if it is *in* this room.  The
            # plan test alone is wrong the moment a map stacks a room on a
            # room: the lower room's lamps sit directly under the upper
            # room's, and taking the plan position alone lets each storey
            # satisfy the other's grid and leaves both dark in the middle
            # (Z11 reports the same gap point for a room and the room above it).
            here = [
                lamp
                for lamp in self.elements(Lamp)
                if interior.holds_flat(lamp.position.x, lamp.position.y)
                and room.floor_z <= lamp.position.z <= ceiling  # type: ignore[attr-defined]
            ]
            # A glow (a sensor's pip, a warning light; lighting.is_glow) is
            # neither the style the fill copies nor a lamp that lights a cell:
            # a fill that copies a radius-72 red sensor glow into every lamp
            # leaves the room baked lit by its windows alone (D8).
            # An exploder lamp (script-switched) is left out too: it may be off.
            here = [lamp for lamp in here
                    if not lighting.is_glow(lamp.radius) and lamp.exploder is None]
            hue = colour
            reach = radius
            if here:
                if hue is None:
                    hue = here[0].colour
                if reach is None:
                    reach = here[0].radius
            hue = (1.0, 1.0, 1.0) if hue is None else hue
            reach = 512.0 if reach is None else reach

            tiers = self._lamp_tiers(z, room.floor_z, spacing)  # type: ignore[attr-defined]
            band = (tiers[0] - tiers[1]) / 2.0 if len(tiers) > 1 else spacing
            spots: list[tuple[float, Point]] = []
            for tier in tiers:
                for point, cell in self._lamp_grid(interior, tier, spacing):
                    if any(
                        cell.holds_flat(lamp.position.x, lamp.position.y)
                        and abs(lamp.position.z - tier) <= band
                        for lamp in here
                    ) or any(cell.holds_flat(p.x, p.y) and abs(p.z - tier) <= band
                             for _t, p in spots):
                        continue
                    if buried(point):
                        continue
                    spots.append((tier, point))
            # Top-up (D8): when the copied style would leave the
            # floor dark by D8's own estimate -- a radius-300 stage light
            # copied 248 over a floor estimates 0.05 -- the fill gets the reach (lighting.fill_radius) and, in a
            # single-tier room, the stops (lighting.fill_boost) a storey-high
            # room's floor gets.  Only then: a room that passes keeps its
            # recipe's mood (the cemetery recipe's rooms are untouched).
            from ..verify.lightlevel import style_leaves_floor_dark

            top_up = bool(spots) and style_leaves_floor_dark(
                self, room, here, [p for _t, p in spots], hue, reach)
            for tier, point in spots:
                drop = tier - room.floor_z  # type: ignore[attr-defined]
                boost = lighting.fill_boost(drop) if top_up and len(tiers) == 1 else 0.0
                lamp = self.place_light(
                    point,
                    colour=hue,
                    radius=max(reach, lighting.fill_radius(drop, spacing)) if top_up else reach,
                    stops=(self.exposure + lighting.STOPS_OVER_EXPOSURE + boost
                           if boost > 0.0 else None),
                    zone_name=self._zone_name_over(room),
                    shadows=False,
                    id=f"{room.id}_fill_{len(added)}",
                )
                here.append(lamp)
                added.append(lamp)
        # Then every door and buyable the grid left out of reach gets a play
        # lamp of its own (zmforge.blueprint.autolamp; D5).  Not in the returned list: that is the fill grid.
        from .autolamp import light_play

        light_play(self)
        return added

    @staticmethod
    def _lamp_tiers(ceiling_z: float, floor_z: float, spacing: float) -> list[float]:
        """The heights a room's lamp grid is laid at, ceiling first.

        The plan grid puts a lamp within ``spacing`` of every patch of floor
        in x and y; this puts one within ``spacing`` in z as well, so the rule
        is the same in all three axes and a tall room stops being a special
        case.  ``spacing`` is the right number for the z axis too and not just
        by analogy -- measured over the 25 rooms of a test map,
        every room whose floor reads correctly has its ceiling
        lamps 92 to 280 units above that floor, and the three that read dark
        are the three above that band, at 384, 840 and 856.  :data:`zmforge.lighting.MAX_LAMP_SPACING` is 256 and
        sits inside the working band.

        The tiers are spread evenly rather than stacked down from the ceiling
        at a fixed step, so the gap between them and the gap from the lowest
        to the floor are the same distance and no tier lands just above
        another.  A room shorter than one step keeps its single ceiling tier,
        which is every shipped room but those three.
        """
        import math

        drop = ceiling_z - floor_z
        if spacing <= 0.0 or drop <= spacing:
            return [ceiling_z]
        tiers = math.ceil(drop / spacing)
        step = drop / tiers
        return [ceiling_z - index * step for index in range(tiers)]

    @staticmethod
    def _lamp_grid(
        interior: Span, z: float, spacing: float
    ) -> list[tuple[Point, Span]]:
        """The coarsest grid over ``interior`` with no cell wider than
        ``spacing``, as ``(centre, cell)`` pairs.

        A room 300 wide gets two columns and one 200 wide gets one, so the
        rule "a lamp in every cell" is exactly "a lamp per ``spacing`` square
        patch of floor" -- the density measured off The Giant.
        """
        import math

        cells: list[tuple[Point, Span]] = []
        width = interior.maxs.x - interior.mins.x
        depth = interior.maxs.y - interior.mins.y
        nx = max(1, math.ceil(width / spacing))
        ny = max(1, math.ceil(depth / spacing))
        for ix in range(nx):
            for iy in range(ny):
                x0 = interior.mins.x + width * ix / nx
                x1 = interior.mins.x + width * (ix + 1) / nx
                y0 = interior.mins.y + depth * iy / ny
                y1 = interior.mins.y + depth * (iy + 1) / ny
                cells.append(
                    (
                        Point((x0 + x1) / 2.0, (y0 + y1) / 2.0, z),
                        Span.between(
                            Point(x0, y0, interior.mins.z),
                            Point(x1, y1, interior.maxs.z),
                        ),
                    )
                )
        return cells

    def _zone_name_over(self, room: Room) -> str | None:
        """The zone whose volume covers this room's middle, if any."""
        centre = room.interior.centre  # type: ignore[attr-defined]
        for zone in self.elements(Zone):
            bounds = zone.bounds  # type: ignore[attr-defined]
            if bounds is not None and bounds.holds_flat(centre.x, centre.y):
                return zone.name  # type: ignore[attr-defined]
        return None

    def place_props(
        self,
        items: Sequence[
            tuple[str, Point, float]
            | tuple[str, Point, float, float]
            | tuple[str, Point, float, float, bool]
            | tuple[str, Point, float, float, bool, tuple[float, float]]
            | Prop
        ],
        *,
        id: str | None = None,
    ) -> PropScatter:
        """Put named models exactly where the caller says, at the yaw it says.

        :meth:`strew_props` scatters: it is for rubble and undergrowth, where
        the point is that nobody chose. Furnishing a room is the opposite --
        a counter runs along a wall, a stack of crates sits in a corner, a
        chair faces the desk -- and there was no way to say that, which is
        why every generated room so far has been an empty box.

        Each item is ``(model, position, yaw)`` with an optional fourth
        element for scale, an optional fifth for whether the prop is
        solid and an optional sixth ``(pitch, roll)`` lean (:attr:`Prop.pitch`).
        Nothing is snapped to the floor: the caller knows whether a thing
        stands on the ground or hangs off a wall, and :meth:`ground_under`
        is there for the ones that do.

        Solidity defaults to ``False`` because the caller that knows a shelf
        from a sheet of paper is the recipe, not this method.

        A solid prop needs a collision box as well as the flag, and the tuple
        form has no room to spell one out, so it is looked up here from the
        measured per-model table the prop recipes use
        (:func:`zmforge.recipes.props.collision_box`).  Without it the entity
        is written with ``use_collmap "1"`` and no collmap for ``cod2map64``
        to bake, which ``Z21`` reports as an error and which in play is a
        prop the player walks through.  A :class:`Prop` passed in whole is left exactly as the
        caller built it: it can say the box itself.
        """
        props: list[Prop] = []
        for item in items:
            if isinstance(item, Prop):
                props.append(item)
                continue
            model, position, yaw = item[0], Point.of(item[1]), float(item[2])
            scale = float(item[3]) if len(item) > 3 else 1.0
            solid = bool(item[4]) if len(item) > 4 else False
            pitch, roll = (float(item[5][0]), float(item[5][1])) if len(item) > 5 else (0.0, 0.0)
            props.append(
                Prop(
                    model=str(model),
                    origin=position,
                    yaw=yaw,
                    scale=scale,
                    solid=solid,
                    pitch=pitch,
                    roll=roll,
                    collision_box=_default_collision_box(str(model)) if solid else None,
                )
            )
        if not props:
            raise BlueprintError("place_props was given nothing to place")
        element = PropScatter(id=self._claim("props", id), props=props)
        return self._install(element)  # type: ignore[return-value]

    def strew_props(
        self,
        footprint: Span,
        palette: Sequence[str] = fixed.PROP_PALETTE,
        *,
        spacing: float = 128.0,
        density: float = 0.4,
        seed: int = 0,
        keep_clear: Sequence[Span] = (),
        scale: float = 1.0,
        id: str | None = None,
    ) -> PropScatter:
        """A jittered grid of decorative models, deterministic for a seed."""
        if not palette:
            raise BlueprintError("a prop scatter needs at least one model")
        rng = random.Random(f"{self.seed}:{seed}:{id or 'props'}")
        props: list[Prop] = []
        x = footprint.mins.x + spacing / 2.0
        while x < footprint.maxs.x:
            y = footprint.mins.y + spacing / 2.0
            while y < footprint.maxs.y:
                if rng.random() <= density:
                    jx = x + rng.uniform(-spacing / 3.0, spacing / 3.0)
                    jy = y + rng.uniform(-spacing / 3.0, spacing / 3.0)
                    if not any(box.holds_flat(jx, jy) for box in keep_clear):
                        ground = self.ground_under(jx, jy)
                        if ground.found:
                            props.append(
                                Prop(
                                    model=rng.choice(list(palette)),
                                    origin=Point(jx, jy, ground.z),
                                    yaw=rng.uniform(0.0, 360.0),
                                    scale=scale,
                                )
                            )
                y += spacing
            x += spacing
        element = PropScatter(id=self._claim("props", id), props=props)
        return self._install(element)  # type: ignore[return-value]

    def set_dog_rounds(self, enabled: bool) -> None:
        """Dog rounds are off by default (spec 4.12, E6)."""
        self.script.dog_rounds = bool(enabled)

    def declare_asset(self, prefix: str, name: str) -> AssetRef:
        """Declare an asset the map's manifest must list.

        The linker packs what the manifest names.  A script that calls for an
        asset nobody declared fails at run time, in a play session; a
        manifest that names an asset nobody built fails in the linker's log.
        Declaring is the cheaper failure, so anything a mechanic plays or
        shows should be declared here.

        An ``fx`` declaration does one thing more: it adds the effect to the
        script plan's precache list, so both emitted scripts register the
        handle the game plays the effect through (``#precache( "fx", ... )``
        in the ``.gsc`` and ``#precache( "client_fx", ... )`` in the
        ``.csc``).  A declared effect with no precache line is packed into
        the fastfile, plays nothing and reports nothing; check Z17 holds the
        manifest and the two scripts together.
        """
        ref = AssetRef(prefix, name)
        if ref not in self.assets:
            self.assets.append(ref)
        if ref.prefix == "fx" and ref.name not in self.script.precache_fx:
            self.script.precache_fx.append(ref.name)
        return ref

    def ship_hud_image(self, name: str, png: bytes) -> AssetRef:
        """Pack *png* into this map's fastfile as the image asset *name*.

        For a HUD widget that resolves an image by name at run time -- the
        perk widget's two unclaimed slots are the case this was written for
        (:class:`zmforge.script.perks.IconSlot`).  The commit writes the PNG
        and a stock-shaped ``.gdt`` entry for it under
        ``texture_assets/zmforge_hud/<map>/`` (:mod:`zmforge.texture.hud_icons`),
        and this declares ``image,<name>`` in the zone.  The ``.gdt`` still
        has to be registered into ``gdt.db`` before the link; your build
        script does that before it links.

        Idempotent for the same bytes; a second, different picture under one
        name is refused, since the fastfile can carry only one.
        """
        name = str(name).strip()
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise BlueprintError(
                f"{name!r} is not a usable image asset name: lower case, "
                "digits and _ only"
            )
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BlueprintError(f"{name}: a HUD image is shipped as PNG bytes")
        existing = self.hud_images.get(name)
        if existing is not None and existing != png:
            raise BlueprintError(
                f"this map already ships a different picture as {name!r}; one "
                "image asset name packs one image"
            )
        self.hud_images[name] = png
        return self.declare_asset("image", name)

    def add_custom_logic(self, custom: CustomScript) -> CustomScript:
        """Weave a caller's gameplay logic into the generated scripts.

        This is the only supported way to put logic a mapper wrote into a
        generated map: the scripts are regenerated whole every commit
        (spec 5.3), so an edit to the emitted file would not survive the
        next one.  Several calls accumulate, so mechanics can be written
        independently of each other and combined here.

        The reserved names are refused rather than emitted, because GSC
        resolves a duplicate definition silently by taking the second one:
        a custom function called ``main`` would replace the map's entry
        point and the map would load into nothing.
        """
        merged = merge(self.script.custom, custom)
        reserved = {
            "main",
            "__init__",
            "on_player_spawned",
            TABLE_LOADER,
            self.script.zone_hook,
        }
        for function in merged.functions:
            if function.name in reserved:
                raise ValueError(
                    f"custom function {function.name!r} collides with a function "
                    "the engine generates; GSC would take the custom one and the "
                    "map would lose its generated logic"
                )
        self.script.custom = merged
        for prefix, name in merged.assets:
            self.declare_asset(prefix, name)
        return merged

    def add_custom_sound(self, sound: CustomSound) -> CustomSound:
        r"""Ship a sound of the map's own, playable by name from its scripts.

        Three files follow from one call and a map that skips any of them is
        silent in a different way: the wave file lands under the tools'
        ``sound_assets`` tree where the alias's ``FileSpec`` points, the
        map's bank gets a row naming it, and the manifest gets
        ``sound,<map>`` so the linker packs the bank.

        The bank is named after the map and nothing else, which is why this
        takes no bank name: ``sound,<bank>`` is what the linker opens, and a
        bank under any other name is not found.  See
        :mod:`zmforge.emit.sound` for the three measured rules.
        """
        if any(existing.alias.name == sound.alias.name for existing in self.custom_sounds):
            raise BlueprintError(
                f"this map already carries a sound called {sound.alias.name!r}; "
                "two rows under one name is a bank whose winner is undefined"
            )
        if len(self.custom_sounds) + 1 > ALIAS_ROW_CEILING:
            raise BlueprintError(
                f"a sound bank holds at most {ALIAS_ROW_CEILING} rows [measured]; "
                "this map is asking for more"
            )
        self.custom_sounds.append(sound)
        self.declare_asset("sound", self.name)
        return sound

    def add_custom_weapon(self, weapon: CustomWeapon) -> CustomWeapon:
        """Add a gun of the map's own to this level's weapon set.

        Three things follow from one call, and a map that skips any of them
        fails in a different place: the weapon is declared in the zone so the
        linker packs it, it gets a row in the map's weapon table so the level
        knows it exists, and both generated scripts load that table.

        The linker is the guard on the first: a ``weapon`` line naming
        something the asset database does not have stops the link with an
        error.  Nothing is the guard on the second -- the table is opaque to
        the linker -- which is what check ``W5`` is for.
        """
        if any(existing.name == weapon.name for existing in self.custom_weapons):
            raise BlueprintError(
                f"custom weapon {weapon.name!r} is already declared; a second row "
                "for the same name would overwrite the first in "
                "level.zombie_weapons and only the last would ever be seen"
            )
        if weapon.name in LEVEL_WEAPONS:
            raise BlueprintError(
                f"{weapon.name!r} is already a weapon this level has; use "
                "set_weapon_price to change what it costs rather than declaring "
                "a second definition under the same name"
            )
        self.custom_weapons.append(weapon)
        self.declare_asset("weapon", weapon.asset_name)
        self._ship_weapon_table()
        return weapon

    def set_weapon_price(self, weapon: str, cost: int) -> None:
        """Charge *cost* for *weapon* everywhere this level charges for it.

        The table is the level's, not the buy's, so this is the form to use
        for a weapon nothing on a wall sells -- a box weapon's ammo price
        follows its cost, for one.  A wall buy's own ``price`` argument ends
        up here.
        """
        if cost < 0:
            raise BlueprintError(f"{weapon}: a weapon price may not be negative")
        self.weapon_prices[weapon] = int(cost)
        self._ship_weapon_table()

    def weapon_price_table(self) -> dict[str, int]:
        """Every stock weapon this map re-prices, by weapon name.

        Wall buys are resolved through their prefab, because the slug names
        the prefab file and the weapon is named inside it -- the ``bowie``
        slug sells ``bowie_knife``.  A slug with no prefab is left out; the
        model-level check ``Z22`` is what reports it.
        """
        prices = dict(self.weapon_prices)
        for buy in self.elements(WallWeapon):
            if buy.price is None:  # type: ignore[attr-defined]
                continue
            name = wall_weapon_weapon(buy.slug)  # type: ignore[attr-defined]
            if name is not None:
                prices[name] = int(buy.price)  # type: ignore[attr-defined]
        return prices

    def ships_weapon_table(self) -> bool:
        """Whether this map has anything of its own to say about weapons."""
        return bool(self.weapon_price_table() or self.custom_weapons)

    def _ship_weapon_table(self) -> None:
        """Turn the map's own weapon table on, idempotently.

        Called only from the two places that can want one, so a map that asks
        for no prices and no guns emits the manifest and the scripts it
        emitted before this existed.
        """
        table = weapon_table_asset(self.name)
        self.script.weapon_table = table
        self.declare_asset("stringtable", table)

    def rename_weapon_prompt(self, weapon: str, name: str) -> str:
        """Say *name* on every wall buy that sells *weapon*, and ship the string.

        Spec 5.7 is right about the weapon's own name, which arrives through
        the engine's cursor hint and is not ours; it is the rest of the line
        that turned out to be a variable.  The framework assigns
        ``&"ZOMBIE_WEAPONCOSTONLYFILL"`` to ``level.zombie_weapons[weapon].
        hint`` itself (``_zm_weapons.gsc:559-566``) and then reads that field
        back when it builds each wall buy's unitrigger
        (``get_weapon_hint()``, ``_zm_weapons.gsc:1417-1422``, used at
        ``:969``), so a map that overwrites it between those two moments
        chooses the text.  The emitted loader is that moment
        (:mod:`zmforge.emit.scripts`).

        Three things go together, and this method is where they are kept
        together, because any one of them alone is a blank prompt: the
        ``localize`` asset in the manifest, the ``.str`` file the project
        writes beside it (:mod:`zmforge.emit.strings`), and the assignment in
        the script.  Returns the asset name, which is the linker's, not ours
        (:func:`zmforge.emit.strings.asset_name`, measured).

        Keyed by weapon rather than by wall buy: ``level.zombie_weapons`` has
        one entry per weapon, so two buys selling the same gun cannot be
        given different names however they are placed, and asking for that is
        refused here rather than resolved silently in a live game.
        """
        text = str(name).strip()
        if not text:
            raise BlueprintError(
                f"{weapon}: a renamed prompt needs a name; an empty string "
                "clears the prompt rather than setting one"
            )
        existing = self.weapon_prompts.get(weapon)
        if existing is not None and existing != text:
            raise BlueprintError(
                f"{weapon} is already renamed to {existing!r}; level."
                f"zombie_weapons holds one hint per weapon, so a second name "
                "would silently replace the first on every buy that sells it"
            )
        self.weapon_prompts[weapon] = text
        self.declare_asset("localize", self.name)
        self.script.weapon_hints = [
            (gun, string_asset(self.name, weapon_reference(gun)))
            for gun in self.weapon_prompts
        ]
        return string_asset(self.name, weapon_reference(weapon))

    def ships_localized_strings(self) -> bool:
        """Whether this map has words of its own to put in the English zone."""
        return bool(self.weapon_prompts or self.custom_perks or self.map_strings)

    def localized_strings(self) -> tuple[LocalizedString, ...]:
        """Every entry of the map's own ``.str``, in the order asked for.

        The file is the other half of :attr:`ScriptPlan.weapon_hints`: the
        script names an asset, and the asset exists because this entry is in
        this file under the map's own name.
        """
        return tuple(
            [
                LocalizedString(weapon_reference(weapon), weapon_prompt(text))
                for weapon, text in self.weapon_prompts.items()
            ]
            + [
                LocalizedString(perk.reference, perk_prompt(perk.name))
                for perk in self.custom_perks
            ]
            + [
                LocalizedString(reference, text)
                for reference, text in self.map_strings.items()
            ]
        )

    def add_map_string(self, reference: str, text: str, *, kind: str = "string") -> str:
        """Ship one line of the map's own words and return its asset name.

        The same ``.str`` a renamed wall buy lands in (:mod:`zmforge.emit.
        strings`), precached in the server script as *kind* --
        ``triggerstring`` for a prompt on a trigger a custom script spawns,
        ``string`` for a line it prints.  A script names it as
        ``&"<asset>"``.  ``&&1`` in *text* is the first parameter the call
        passes, exactly as a wall buy's cost is.
        """
        if kind not in ("string", "triggerstring"):
            raise BlueprintError(f"{kind!r}: a map string is a string or a triggerstring")
        text = str(text).strip()
        if not text:
            raise BlueprintError(f"{reference}: an empty map string shows nothing")
        existing = self.map_strings.get(reference)
        if existing is not None and existing != text:
            raise BlueprintError(f"{reference} already says {existing!r}")
        self.map_strings[reference] = text
        self.declare_asset("localize", self.name)
        asset = string_asset(self.name, reference)
        if (kind, asset) not in self.script.map_strings:
            self.script.map_strings.append((kind, asset))
        return asset

    def adopt(self, document, *, source_path: str = "", id: str | None = None) -> ImportedMap:
        """Keep a foreign map verbatim inside this blueprint."""
        element = ImportedMap(
            id=self._claim("imported", id),
            document=document,
            source_path=source_path,
        )
        return self._install(element)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Derived views used by emit and verify
    # ------------------------------------------------------------------
    def zone_of_point(self, point: Point) -> Zone | None:
        for zone in self.elements(Zone):
            if zone.bounds.holds_flat(point.x, point.y):  # type: ignore[attr-defined]
                return zone  # type: ignore[return-value]
        return None

    def spawns_of(self, zone_name: str) -> list[Spawn]:
        return [s for s in self.elements(Spawn) if s.zone_name == zone_name]  # type: ignore[attr-defined]

    def windows_of(self, zone_name: str) -> list[Window]:
        return [w for w in self.elements(Window) if w.zone_name == zone_name]  # type: ignore[attr-defined]

    def material_names(self) -> set[str]:
        names: set[str] = set()
        for room in self.elements(Room):
            names |= room.materials.names()  # type: ignore[attr-defined]
        for yard in self.elements(Yard):
            names |= yard.materials.names()  # type: ignore[attr-defined]
        for terrain in self.elements(Terrain):
            names.add(terrain.material.name)  # type: ignore[attr-defined]
            names |= {m.name for _, m in terrain.bands}  # type: ignore[attr-defined]
        for massing in self.elements(Massing):
            for solid in massing.solids:  # type: ignore[attr-defined]
                names |= {face.material.name for face in solid.faces}
        return names

    def world_solids(self) -> list[Solid]:
        """Every structural solid, for the overlap scan of spec 2.8 step 7."""
        from ..emit.mapfile import world_solids_of  # local import: emit sits above

        return world_solids_of(self)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _indoor_probe_box(room: Room) -> Span:
    """A roofed room's probe box: its interior, reaching through its own
    walls across the floor plan (:meth:`Blueprint.probe_boxes`, ``Z88``)."""
    t = float(room.thickness)
    return room.interior.grown_on(Axis.X, t).grown_on(Axis.Y, t)


def _closet_materials() -> RoomMaterials:
    """A barricade closet's dark, weathered shell (``blueprint.windows``)."""
    return RoomMaterials(
        wall=Material(CLOSET_MATERIALS["wall"]),
        floor=Material(CLOSET_MATERIALS["floor"]),
        ceiling=Material(CLOSET_MATERIALS["ceiling"]),
    )


def _default_room_materials() -> RoomMaterials:
    return RoomMaterials(
        wall=Material("t7_concrete_wall_dark_01"),
        floor=Material("t7_concrete_trowelled"),
        ceiling=Material("t7_metal_rust_ceiling_01"),
    )


def _default_collision_box(
    model: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """The box a solid prop's collmap is cut from, for a caller that gave none.

    The table is :data:`zmforge.recipes.props.MODEL_BOX`, read through
    ``collision_box`` so this and the recipes cut the same shape; the import
    is here rather than at the top because the recipes import this module.

    A model the install already ships a collmap for keeps ``None``: theirs is
    authored to the art and :meth:`zmforge.project.Project` never overwrites
    it.  Anything else with no measured box is refused by name, because the
    alternative is a prop that is silently walked through -- ``use_collmap``
    on a model with no collmap file compiles clean and says nothing.
    """
    from ..props.collision import STOCK_COLLMAPS
    from ..recipes.props import collision_box

    box = collision_box(model)
    if box is not None:
        return box
    if model in STOCK_COLLMAPS:
        return None
    raise BlueprintError(
        f"prop {model!r} is placed solid and no collision box was given for "
        "it: the model is not in the measured box table "
        "(zmforge.recipes.props.MODEL_BOX) and the install ships no collmap "
        "of its own, so cod2map64 would bake nothing and the player would "
        "walk through it.  Measure the model into MODEL_BOX, or place it "
        "with a Prop that carries its own collision_box"
    )


def _as_face_materials(value: FaceMaterials | Material | str) -> FaceMaterials:
    if isinstance(value, FaceMaterials):
        return value
    return FaceMaterials.uniform(Material.of(value))


def _as_side(value: Side | Facing | str) -> Side:
    if isinstance(value, Side):
        return value
    return Facing.of(value).side


def _as_angles(value: Facing | Angles | str | float) -> Angles:
    from ..spatial import heading_of

    return heading_of(value)


def _thinnest_axis(box: Span) -> Axis:
    return min(Axis, key=lambda axis: box.extent(axis))


def _prop_bounds(scatters) -> list[Span]:
    """A world box round every placed model, from its measured box turned
    any way (the widest plan reach, both axes) and scaled; a model with no
    measured box counts as its origin."""
    from ..dressing.trees import EXTRA_BOX
    from ..recipes.props import MODEL_BOX

    out: list[Span] = []
    for scatter in scatters:
        for prop in scatter.props:
            o, k = prop.origin, prop.scale
            box = (MODEL_BOX.get(prop.model) or EXTRA_BOX.get(prop.model)
                   or prop.collision_box)
            if box is None:
                # Its origin, as a half-unit box: Span refuses a zero extent.
                out.append(Span.between(Point(o.x - 0.5, o.y - 0.5, o.z - 0.5),
                                        Point(o.x + 0.5, o.y + 0.5, o.z + 0.5)))
                continue
            (x0, y0, z0), (x1, y1, z1) = box
            r = max(abs(x0), abs(x1), abs(y0), abs(y1)) * k
            out.append(Span.between(Point(o.x - r, o.y - r, o.z + z0 * k),
                                    Point(o.x + r, o.y + r, o.z + z1 * k)))
    return out


def _solid_bounds(solid: Solid) -> Span:
    points = [p for face in solid.faces for p in face.points]
    return Span.flat_ok(
        Point(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)),
        Point(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)),
    )
