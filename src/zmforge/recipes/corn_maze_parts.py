"""Harvest Moon's furniture and dressing: what is in each area of :mod:`.corn_maze`.

Split from the recipe so the layout (rooms, corn, doors, maze) reads on its
own.  Everything here is a caller of the blueprint and nothing else.

**The props are the measured ones.**  Every model is a key of
:data:`zmforge.recipes.props.MODEL_BOX` (plus the few this module measures
itself, :data:`EXTRA_BOX`).  The install has no pumpkin, corn, hay bale,
scarecrow or tractor, so the farm's own things are the project's CC0 kit
props (``zmf_prop_*``, Kenney's Graveyard, Nature and Car kits, built by
the prop install step; :mod:`zmforge.props.library` names each file):

* **pumpkins** are ``zmf_prop_pumpkin``; the lit ones are
  ``zmf_prop_jack_o_lantern``.  The quest's three burning jack-o'-lanterns
  are the *tall* carved one, each up on a hay bale with its own light, so
  they stand out of every row of ordinary ones.
* **the exploding pumpkins** are prize pumpkins: the plain pumpkin at 2.5x
  (40 units across, more than twice any other) on a green glow, spawned by
  script.  The signs and the hayride say the giant glowing ones explode.
* **corn stalks** (``zmf_prop_corn_stalk`` and ``_thin``, walk-through, scaled
  to the corn's height) line every corn wall; the brush walls behind them
  still do the blocking and the hiding.
* **hay bales** are ``zmf_prop_hay_bale_stack`` with a ``zmf_prop_hay_bale``
  on top: one "bale" of the layout is the pair, 48 units tall.
* **the tractor** (``zmf_prop_tractor``) tows the hayride and is the way out.
* **fences** are ``zmf_prop_fence_wood`` sections; **scarecrows** are a
  ``zmf_prop_wooden_cross`` with a scripted jack-o'-lantern head.
* **feed sacks** are burlap sacks; **apples** at the cider stand are oranges.

**Kit props keep their library solidity** (``Z21`` is an error on a kit prop
placed otherwise): the corn is walk-through, everything else is solid.  A
stock prop that is scaled is always walk-through, because a collmap is cut
from the model's unscaled box.  A solid kit prop is scaled only a little
(:data:`KIT_SCALE`): whether ``cod2map64`` scales a ``modelscale`` prop's
collmap has not been measured, and within that range the collision is off by
at most a couple of units either way.

Every dressing prop goes through :class:`Dresser`, which refuses a spot in
an interactive item's keep-clear, on the hayride's lane, in a doorway's
approach or on a spawn, and counts what each zone got so the tests can pin
the density.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Mapping, Sequence

from .. import lighting
from ..blueprint.elements import FLOATS_ON_PURPOSE, Spawn
from ..blueprint.model import Blueprint
from ..spatial import Axis, Bounds, Facing, Point, Side
from . import corn_maze as cm
from ..placement.geometry import rotate
from . import corn_maze_assets as assets
from .props import KIT_SOLID, MODEL_BOX, is_solid, shelf_boards
from ..lettering import brush_text
from ..dressing import fit_within, window_keepouts
from ..dressing.lining import Lining, band_spans, bare_runs, line_face, plant_spot, record_opening, yaw_for
from ..placement.wallbuy import buy_shed, place_wall_buy
from ..blueprint.autolamp import light_paths
from ..materials import CLIP, FaceMaterials, Material

__all__ = ["build_all", "Dresser", "SCARECROWS", "static_head_name", "JACKS", "PUMPKIN", "PUMPKIN_SCALE", "JACK", "JACK_TALL",
           "JACK_SCALE", "PRIZE", "PRIZE_SCALE", "PRIZE_GLOW", "ORANGE", "STALK", "STALK_THIN", "STALK_SCALE",
           "TRACTOR", "FLATBED", "HAY_BALE", "HAY_STACK", "FENCE", "CROSS", "POLE_TOP", "LAMP", "CRATE", "KIT_SCALE",
           "EXTRA_BOX", "BOSS_SPAWN", "POWER"]

#: Models this map uses that :data:`~zmforge.recipes.props.MODEL_BOX` does not
#: carry yet.  Each is in the install ledger (``blueprint/installed_assets.json``
#: ``xmodels_declared``) and its box is the converted-asset catalogue's
#: measurement of the converted model (its ``bbox``), and its binary and colour image are in the tools tree's
#: ``model_export/t7_props/p7_food_fruit_set/`` -- the three checks props.py's
#: own blocks pass.  Registered into ``MODEL_BOX`` at import (``setdefault``: a
#: measurement props.py adds later wins); no other map places it.  Placed
#: walk-through.  (Reed baskets, glass jars, an old sink and a rag rug would
#: suit too, but their folders were missing from the tools tree this map was
#: checked against, so the crates and bottles below stand in.)
EXTRA_BOX = {
    "p7_food_fruit_orange": ((-1.895, -1.885, -0.003), (1.895, 1.885, 3.503)),
    # A claw hammer for the barn's benches and shelves: declared,
    # linkable (not in ``xmodels_unlinkable``), binary and images in the tools tree's
    # ``model_export/t7_props/p7_farm_tools/``; box from the same catalogue.
    "p7_farm_tools_hammer": ((-3.96, -11.24, 0.06), (4.43, 11.16, 2.2)),
}
for _name, _box in EXTRA_BOX.items():
    MODEL_BOX.setdefault(_name, _box)  # type: ignore[attr-defined]
_WALK_THROUGH = frozenset(EXTRA_BOX) | assets.WALK_THROUGH

#: The oranges: real-size ones, heaped in the harvest boxes and sold at the
#: cider stand as apples.
ORANGE = "p7_food_fruit_orange"
#: The farm's pumpkins (16 across, 13.6 tall at 1.0), and the two carved ones.
#: A kit model faces -y at yaw 0 (the kits' +z front, ``props.xmodel``).
PUMPKIN = "zmf_prop_pumpkin"
JACK = "zmf_prop_jack_o_lantern"
JACK_TALL = "zmf_prop_jack_o_lantern_tall"
#: How far a solid kit prop is scaled, at most, either way (see the module
#: docstring): 16-unit pumpkins from 14 to 20 across.
KIT_SCALE = (0.85, 1.25)
PUMPKIN_SCALE = 1.0
#: The decorative lit jack-o'-lanterns, a little bigger than a field pumpkin.
JACK_SCALE = 1.2
#: The exploding prize pumpkins (script models, so any scale): 40 across.
PRIZE = PUMPKIN
PRIZE_SCALE = 2.5
#: The prize pumpkins' tell: a sickly green glow on each (now the script's
#: ``powerup_on`` effect, :data:`.corn_maze_script.PUMPKIN_GLOW_FX`).
PRIZE_GLOW = (0.45, 1.0, 0.3)
#: Corn: walk-through (the library says so), so scaled to the corn's height:
#: 96 units at 1.0, 190-215 here against a 200-unit wall, so the tops break
#: the wall's straight edge.
STALK = "zmf_prop_corn_stalk"
STALK_THIN = "zmf_prop_corn_stalk_thin"
STALK_SCALE = 2.0
#: Harvest boxes: shallow wooden trays and boxes, each with oranges on top.
BASKETS = ("p7_box_wood_wine_storage_tan", "p7_box_wood_01_sm", "p7_box_wood_wine_storage")
#: Cider: bottles on the stand and the shelves, a big glass jug.
JAR = "p7_bottle_glass_liquor_03"
JUG = "p7_chemistry_kit_large_bottle"
LAMP = "p7_zm_der2_light_hurricane_lamp"
#: The farmhouse pictures.  Measured on two renders:
#: ``p7_3arc_lobby_picture_41x29`` draws as a flat dark grey-teal panel on
#: every wall and at every yaw (it, not the modern frames, made the blank
#: screens), while ``p7_picture_frame_modern_01`` draws its painting.
PICTURE = "p7_picture_frame_modern_01"
#: A burlap feed sack (walk-through, corn_maze_assets).
SACK = "p7_sandbag_01"
CRATE = "p7_crate_wood_01_short_open"
CRATE_LONG = "p7_crate_wood_01"
#: The tractor: 150 long on y at yaw 0, its front (the small wheels) at -y,
#: so yaw 90 points it along +x.
TRACTOR = "zmf_prop_tractor"
TRACTOR_YAW = 90.0
FLATBED = "p7_pallet_metal_military_01"
HAY_BALE = "zmf_prop_hay_bale"
HAY_STACK = "zmf_prop_hay_bale_stack"
#: Degrees either way :meth:`Dresser.put` turns each of these off the yaw it
#: was given, a different amount at every spot (:func:`_varied_yaw`): a
#: pumpkin is round, so anywhere; a bale, crate or sack a little, so a row of
#: them is not ruled.
VARY_YAW = {PUMPKIN: 180.0, HAY_BALE: 7.0, HAY_STACK: 5.0, CRATE: 9.0, CRATE_LONG: 6.0, SACK: 25.0}
FENCE = "zmf_prop_fence_wood"
#: The kit's wooden cross on a stone plinth (plinth 0-31, crossbar 64-70,
#: post top 78 units, measured off the kit's cross-wood.obj).  No longer
#: placed: the scarecrows stand on a brush pole (:func:`_scarecrow_body`).
CROSS = "zmf_prop_wooden_cross"
CROSS_TOP = 78.0

#: A lone hay bale's footprint (x along, y across) and height: the bundled
#: stack under a single bale, 25 + 23.4.  Taller than the jump (39,
#: verify.reachability.JUMP_UP) on purpose: a bale a player can hop onto and a
#: zombie cannot follow them up is a camping spot (Z46).
BALE = (40.0, 28.4, MODEL_BOX[HAY_STACK][1][2] + MODEL_BOX[HAY_BALE][1][2])

#: Where each scarecrow's turning figure sits, filled by :func:`build_all`
#: for the script module: name -> (x, y, z of the top of its post).  The
#: ``tractor`` entry is where the defend step stands, beside the rig.
SCARECROWS: dict[str, tuple[float, float, float]] = {}
#: How many back-row stalks the last build placed (:func:`_back_row`).
BACK_ROW = [0]

#: Every lit jack-o'-lantern :func:`build_all` placed, by zone: ``(x, y, z of
#: its middle)``.  The quest's first step aims at these.
JACKS: dict[str, list[tuple[float, float, float]]] = {}

#: Where the Scarecrow boss climbs out, kept clear of every prop (the old
#: spot was inside a teddy bear): ``(x, y, z)``, filled by :func:`build_all`.
BOSS_SPAWN: list[tuple[float, float, float]] = []

#: The power switch: deep in the corn, so the barn (and Pack-a-Punch up in
#: its hayloft) opens only once a player has walked the maze to it.  Its
#: cell is filled by :func:`build_all` (:func:`maze_spots`).
POWER: dict[str, object] = {"zone": "mazedeep", "cell": None}

#: What :func:`_grass` placed: ``clumps`` and their ``tris``.
GRASS: dict[str, int] = {}

#: What :func:`_outskirts` placed: ``corn``, ``trees``, ``ground`` slabs.
OUTSKIRTS: dict[str, int] = {}

#: What :func:`maze_spots` chose for the built map, for the script module.
MAZE_SPOTS: dict[str, object] = {}

_DIRS = {(1, 0): Facing.EAST, (-1, 0): Facing.WEST, (0, 1): Facing.NORTH, (0, -1): Facing.SOUTH}


def maze_spots(plan: "cm.CornMazePlan", passages) -> dict[str, object]:
    """Where things go in the maze, all chosen from its shape, so a new seed
    moves them with the corn: the path from the gate to the heart, the power
    (the dead end of the deep zone furthest from its door), the golden ears
    (the furthest dead end of the entry zone, the next furthest of the deep
    zone), the shotgun (the entry zone's nearest dead end), the risers
    (three spread-out cells a room, none a dead end or a gate cell), and the
    dead ends left over for the scenes."""
    graph = cm.maze_graph(passages)
    from_gate = cm.maze_distances(cm.MAZE_ENTRANCE, passages)
    from_door = cm.maze_distances(cm.DOOR_DEEP[0], passages)
    ends = cm.dead_ends(passages)
    zone_of = {c: cm.MAZE_ROOMS[cm.room_of(c)][0] for c in graph}
    entry_ends = sorted((c for c in ends if zone_of[c] == "mazeentry"), key=lambda c: (from_gate[c], c))
    deep_ends = sorted((c for c in ends if zone_of[c] == "mazedeep"), key=lambda c: (from_door[c], c))
    power, deep_ear = deep_ends[-1], deep_ends[-2]
    entry_ear, wallbuy = entry_ends[-1], entry_ends[0]
    # The path: walk back from the heart's gate cell along falling distance.
    path = [cm.DOOR_HEART[0]]
    while path[-1] != cm.MAZE_ENTRANCE:
        path.append(min(graph[path[-1]], key=lambda c: (from_gate[c], c)))
    path.reverse()
    clearing = {(ci + dx, cj + dy) for ci, cj in cm.CLEARINGS.values() for dx in (0, 1) for dy in (0, 1)}
    windows = {cell for _, _, cell, _ in cm.MAZE_WINDOWS}
    busy = set(ends) | clearing | windows | {cm.MAZE_ENTRANCE, *cm.DOOR_DEEP, cm.DOOR_HEART[0]}
    risers: dict[str, list] = {}
    for key, (_, (i0, j0, i1, j1)) in cm.MAZE_ROOMS.items():
        cells = sorted(((i, j) for i in range(i0, i1) for j in range(j0, j1) if (i, j) not in busy),
                       key=lambda c: ((c[0] * 7 + c[1] * 13) % 17, c))
        chosen: list = []
        for c in cells:
            if all(abs(c[0] - o[0]) + abs(c[1] - o[1]) >= 4 for o in chosen):
                chosen.append(c)
            if len(chosen) == 3:
                break
        risers[key] = chosen
    special = {power, deep_ear, entry_ear, wallbuy}
    return {"path": path, "power": power, "ears": (entry_ear, deep_ear), "wallbuy": wallbuy,
            "risers": risers, "dead_ends": ends, "scenes": [c for c in ends if c not in special],
            "clearing": sorted(clearing)}


def _back_wall(plan: "cm.CornMazePlan", cell, passages, inset: float) -> tuple[tuple[float, float], Facing]:
    """A spot *inset* off the corn at the closed end of dead end *cell*, and
    the way something mounted there faces (back up the cell)."""
    graph = cm.maze_graph(passages)
    (nb,) = graph[cell]
    out = (nb[0] - cell[0], nb[1] - cell[1])
    back = (-out[0], -out[1])
    cx, cy = plan.cell_centre(cell)
    behind = (cell[0] + back[0], cell[1] + back[1])
    same_room = cm.room_of(behind) == cm.room_of(cell)
    reach = plan.maze_pitch / 2.0 - (plan.wall / 2.0 if same_room else plan.wall) - inset
    return (cx + back[0] * reach, cy + back[1] * reach), _DIRS[out]


def _extent(model: str, scale: float, yaw: float) -> tuple[float, float, float, float]:
    """The plan footprint of *model* at *scale* and *yaw*, as offsets from its
    origin: ``(min x, max x, min y, max y)``.  The same turned box the layout
    checks and the placement audit measure (``placement.relations.Placed``)."""
    (x0, y0, _), (x1, y1, _) = MODEL_BOX[model]
    pts = [rotate(x * scale, y * scale, yaw) for x in (x0, x1) for y in (y0, y1)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


#: The corn's window keep-out (dressing.window_keepouts): how far either
#: side of the wall and past each end of the opening nothing solid goes.
#: Wider than Z57's own zone (64 and 16), which let a heap stand 45 off a
#: farmhouse window and the hayloft bales stand over the barn's east one.
WINDOW_APPROACH = 90.0
WINDOW_SIDE = 42.0


#: A back-row stalk's stem: how near a prop's keep-out it may stand
#: (:meth:`Dresser.free`, ``back=True``).
STEM_HALF = 6.0


def _varied_yaw(model: str, x: float, y: float, yaw: float) -> float:
    """*yaw* turned a little, differently for every spot, for the repeated
    farm props (:data:`VARY_YAW`): identical yaws read as one prop
    repeated."""
    spread = VARY_YAW.get(model, 0.0)
    if not spread:
        return yaw
    f = (x * 0.01373 + y * 0.02917) % 1.0
    return yaw + spread * (2.0 * f - 1.0)


class Dresser:
    """Places props for one map, refusing spots that would break a rule and
    counting what each zone got."""

    def __init__(self, bp: Blueprint, route, keepouts: list[Bounds]):
        self.bp = bp
        self.route = route
        self.keepouts = keepouts
        self.pending: dict[str, list[tuple]] = {}
        self.counts: dict[str, int] = {}
        self.refused = 0
        #: Every refused spot, ``(zone, model, x, y)``, so a dropped set piece
        #: can be found instead of silently missing.
        self.refused_at: list[tuple[str, str, float, float]] = []
        #: Keep-outs the corn bands ignore (by ``id``): a machine's wide
        #: dressing keep-out, which the bands swap for the narrower box it
        #: holds in :attr:`band_keepouts`, so the corn grows up to the stall.
        self.band_exempt: set[int] = set()
        self.band_keepouts: list[Bounds] = []
        #: Keep-outs (by ``id``) a back-row stalk ignores: an area reserved
        #: for a vignette, whose parts are in :attr:`stem_boxes`.
        self.back_exempt: set[int] = set()
        #: ``(x0, y0, x1, y1)`` plan boxes of parts set against the walls
        #: (the vignettes'): no back-row stalk's stem goes inside one.
        self.stem_boxes: list[tuple[float, float, float, float]] = []
        #: Why the last :meth:`free` said no: ``"lane"``, ``"patch"``,
        #: ``"keepout"`` or ``"interactive"`` (the blueprint's own keep-clear).
        self.last_refusal = ""
        #: Keep-outs round the barricade windows.  Unlike the others these
        #: hold even for ``check=False`` placements: a solid prop in front of
        #: a window blocks the rebuild and the zombies' way in (unchecked, the
        #: hayloft bales stand over the barn's east one).
        self.window_boxes: list[Bounds] = []
        #: The raised ground patches (:func:`_ground`), grown by
        #: :data:`GROUND_CLEAR`.  A prop keeps off them by its *turned*
        #: footprint, not its unturned half-width: a turned tuft's corner over
        #: a tilled row makes the row the surface it stands on (Z44, the v2
        #: heart).
        self.patches: list[Bounds] = []

    def by_window(self, x: float, y: float, z: float, half: float) -> bool:
        """Whether a footprint *half* either way of ``(x, y)`` at height *z*
        reaches into a window keep-out."""
        return any(box.mins.x - half <= x <= box.maxs.x + half
                   and box.mins.y - half <= y <= box.maxs.y + half
                   and box.mins.z - 8 <= z <= box.maxs.z for box in self.window_boxes)

    def free(self, x: float, y: float, z: float, half: float = 20.0, *, lane: bool = True,
             band: bool = False, reach: tuple[float, float] | None = None, back: bool = False) -> bool:
        """Whether a prop *half* either way of ``(x, y)`` may stand on *z*.

        A back-row lining stalk (``band=True, back=True``) is judged by its
        stem (:data:`STEM_HALF`) against the lane and every keep-out: its
        leaves are walk-through blades that may hang over a crate or a
        doorway's edge, so the wall behind stays corn (no stalks may
        go missing at a door).  Raised patches still take its whole turned footprint (it
        may not stand half on one, Z44), and so does a buy's keep-clear: the
        blueprint drops any prop whose box reaches into a buy's walk-up lane
        (blueprint.lanes, Z48), so the lining tapers to fit beside it instead."""
        full = half
        if band and back:
            half = STEM_HALF
        if lane and cm.distance_to_route(x, y, self.route) < cm.HAYRIDE_LANE_HALF + half:
            self.last_refusal = "lane"
            return False
        rx, ry = reach if reach is not None else (half, half)
        for box in self.patches:
            if (box.mins.x - rx < x < box.maxs.x + rx and box.mins.y - ry < y < box.maxs.y + ry
                    and box.mins.z - 8 <= z <= box.maxs.z):
                self.last_refusal = "patch"
                return False
        boxes = ([b for b in self.keepouts if id(b) not in self.band_exempt] + self.band_keepouts
                 if band else self.keepouts)
        if band and back:
            # A door's or a machine's own band box still takes the whole
            # footprint: stalks crowding a machine's sides close its walk-up
            # (Z48), and the lining tapers to fit beside a door instead.
            near = {id(b) for b in self.band_keepouts}
            for box in self.band_keepouts:
                if (box.mins.x - full <= x <= box.maxs.x + full and box.mins.y - full <= y <= box.maxs.y + full
                        and box.mins.z - 8 <= z <= box.maxs.z):
                    self.last_refusal = "keepout"
                    return False
            boxes = [b for b in boxes if id(b) not in self.back_exempt and id(b) not in near]
            if any(x0 - half <= x <= x1 + half and y0 - half <= y <= y1 + half
                   for x0, y0, x1, y1 in self.stem_boxes):
                self.last_refusal = "keepout"
                return False
        for box in boxes:
            if (box.mins.x - half <= x <= box.maxs.x + half
                    and box.mins.y - half <= y <= box.maxs.y + half
                    and box.mins.z - 8 <= z <= box.maxs.z):
                self.last_refusal = "keepout"
                return False
        # A back-row stalk is held to the blueprint's own lane rule instead
        # (put -> _in_a_lane): it may stand against the wall beside a wall
        # buy's chalk (blueprint.lanes.beside_the_chalk), not in the apron.
        if not (band and back) and self.bp.interactive_blocks(Point(x, y, z + 8.0), full, full):
            self.last_refusal = "interactive"
            return False
        return True

    def put(self, zone: str, model: str, x: float, y: float, surface: float, yaw: float = 0.0,
            scale: float = 1.0, *, solid: bool | None = None, lane: bool = True,
            check: bool = True, band: bool = False, tilt: tuple[float, float] = (0.0, 0.0),
            back: bool = False) -> bool:
        """One prop resting on *surface* at plan ``(x, y)``, leaning *tilt*
        ``(pitch, roll)`` degrees (walk-through props only).  Returns whether
        it was placed."""
        if model not in MODEL_BOX:
            raise KeyError(f"{model}: not a measured model (props.MODEL_BOX)")
        yaw = _varied_yaw(model, x, y, yaw)
        lo, hi = MODEL_BOX[model]
        half = max(hi[0] - lo[0], hi[1] - lo[1]) * scale / 2.0
        c, s_ = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
        corners_x = max(abs(lo[0]), abs(hi[0])) * scale
        corners_y = max(abs(lo[1]), abs(hi[1])) * scale
        reach = (corners_x * c + corners_y * s_, corners_x * s_ + corners_y * c)
        if check and not self.free(x, y, surface, half, lane=lane, band=band, reach=reach, back=back):
            self.refused += 1
            self.refused_at.append((zone, model, round(x), round(y)))
            return False
        if solid is None:
            if model in KIT_SOLID:
                # A kit prop keeps the library's word (Z21), and a solid one
                # is only ever scaled a little (KIT_SCALE).
                solid = KIT_SOLID[model]
                if solid and not KIT_SCALE[0] <= scale <= KIT_SCALE[1]:
                    raise ValueError(f"{model} at {scale}: a solid kit prop stays within {KIT_SCALE}")
            else:
                solid = scale == 1.0 and model not in _WALK_THROUGH and is_solid(model)
        if solid and not check and self.by_window(x, y, surface, half):
            self.refused += 1
            self.refused_at.append((zone, model, round(x), round(y)))
            return False
        z = surface - lo[2] * scale
        if check and band and self._in_a_lane(model, Point(x, y, z), yaw % 360.0, scale):
            # The blueprint would drop it on install (blueprint.lanes, Z48):
            # refuse it here, so the lining tries it smaller instead.
            self.refused += 1
            self.last_refusal = "interactive"
            return False
        item = (model, Point(x, y, z), yaw % 360.0, scale, solid)
        if tilt[0] or tilt[1]:
            if solid:
                raise ValueError(f"{model}: a solid prop does not lean (its collision box is upright)")
            item += (tilt,)
        self.pending.setdefault(zone, []).append(item)
        self.counts[zone] = self.counts.get(zone, 0) + 1
        return True

    def _in_a_lane(self, model: str, at: Point, yaw: float, scale: float) -> bool:
        """Whether a prop here would stand in a buy's walk-up lane
        (:func:`zmforge.blueprint.lanes.blocks_lane`)."""
        from ..blueprint import lanes
        from ..blueprint.elements import Prop

        n = len(self.bp.elements())
        if getattr(self, "_lanes_at", None) != n:
            self._lanes = lanes.lane_keeps(self.bp.elements())
            self._lanes_at = n
        if not self._lanes:
            return False
        prop = Prop(model=model, origin=at, yaw=yaw, scale=scale)
        return any(lanes.blocks_lane(prop, k) for k in self._lanes)

    def drop_over(self, box: Bounds) -> int:
        """Take back every pending prop on the floor whose turned footprint
        reaches over *box*, a patch laid after it: it would stand half on
        the raised patch, half off (Z44).  WHY: a path's edge tufts can be
        placed before a path or tilled rows laid across them later.  Returns how
        many were dropped."""
        dropped = 0
        for zone, items in self.pending.items():
            keep = []
            for item in items:
                model, at, _yaw, scale = item[:4]
                lo, hi = MODEL_BOX[model]
                reach = math.hypot(max(-lo[0], hi[0]), max(-lo[1], hi[1])) * scale
                on_floor = at.z + lo[2] * scale <= box.mins.z + 0.5
                if (on_floor and box.mins.x - reach < at.x < box.maxs.x + reach
                        and box.mins.y - reach < at.y < box.maxs.y + reach
                        and at.z + hi[2] * scale > box.mins.z):
                    dropped += 1
                    self.counts[zone] -= 1
                    continue
                keep.append(item)
            items[:] = keep
        return dropped

    def flush(self) -> None:
        """Place what is pending, 40 to a scatter; a later flush (the path
        lanterns go in after the lamps) numbers on from the last one."""
        batches = self.__dict__.setdefault("batches", {})
        for zone, items in self.pending.items():
            base = batches.get(zone, 0)
            for n in range(0, len(items), 40):
                self.bp.place_props(items[n:n + 40], id=f"dress_{zone}_{base + n // 40}")
            batches[zone] = base + (len(items) + 39) // 40
        self.pending.clear()


def _lamp(bp: Blueprint, x: float, y: float, z: float, zone: str, ident: str,
          colour=cm.LANTERN, radius: float = 420.0) -> None:
    bp.place_light(Point(x, y, z), colour=colour, radius=radius, zone_name=zone, id=ident)


def _tops(boxes: list[Bounds]) -> list[Bounds]:
    """The top bale of each stack: a box nothing else sits on."""
    return [b for b in boxes if not any(o is not b and abs(o.mins.z - b.maxs.z) < 1.0
                                        and o.holds_flat(b.centre.x, b.centre.y) for o in boxes)]


def _bale(d: "Dresser", zone: str, x: float, y: float, z: float, *, across: bool = False,
          stack: int = 1, yaw: float = 0.0) -> list[Bounds]:
    """A hay bale (or a stack of them) centred at plan ``(x, y)`` on *z*, all
    solid kit props at full size.  A lone bale is the bundled stack with a
    single bale on top (:data:`BALE`, 48 tall); a stack of *stack* is that
    many bundled stacks, 25 each, so two already clear the jump.  Returns each
    level's box, for what sits on it and what keeps clear of it."""
    lx, ly, _ = BALE
    turn = 90.0 if across else 0.0
    if across:
        lx, ly = ly, lx
    stack_h = MODEL_BOX[HAY_STACK][1][2]
    boxes = []
    z0 = z
    for level in range(stack):
        # A few degrees of twist so a stack is not a stamped column.
        twist = turn + yaw + (7.0 if level % 2 else -4.0)
        d.put(zone, HAY_STACK, x, y, z0, twist, check=False, lane=False)
        top = z0 + stack_h
        if stack == 1:
            d.put(zone, HAY_BALE, x, y, top, twist + 11.0, check=False, lane=False)
            top += MODEL_BOX[HAY_BALE][1][2]
        boxes.append(Bounds.between((x - lx / 2, y - ly / 2, z0), (x + lx / 2, y + ly / 2, top)))
        z0 = top
    return boxes


def _fence(x0: float, x1: float, y: float, z: float) -> list[tuple[float, Bounds]]:
    """A wooden fence running east-west: :data:`FENCE` sections end to end
    (64 long, solid), as ``(x of each section's middle, its box)``.  Placed
    by :func:`_put_fence` once the dresser exists; the boxes are keep-outs
    before that."""
    (fx0, fy0, _), (fx1, fy1, fz1) = MODEL_BOX[FENCE]
    length = fx1 - fx0
    count = max(1, round(abs(x1 - x0) / length))
    start = (x0 + x1) / 2 - count * length / 2
    out = []
    for i in range(count):
        mx = start + (i + 0.5) * length
        out.append((mx, Bounds.between((mx - length / 2, y + fy0, z), (mx + length / 2, y + fy1, z + fz1))))
    return out


#: How far a perimeter stalk's footprint keeps off the corn wall's face.
_STALK_GAP = 2.0

#: The corn along a wall: :func:`zmforge.dressing.lining.line_face`'s
#: staggered rows (:data:`BAND_LINING`), both faces of every corn wall.  Each
#: stalk's whole footprint stays within :data:`BAND_DEPTH` of the face (a
#: stalk too wide for its set-back is scaled down to fit): a 264-unit maze
#: corridor keeps 112 units of clear path down its middle, 88 beside a room's
#: outer corn (the every-prop flood, Z48, walks it).
#:
#: One row, a stalk every 20, shows grey wall between stalks; three
#: staggered rows, a stalk every 12 along the face, the back row tucked 16
#: into the wall so its leaves hang over the wall top, still read as thin.
#: Measured
#: head-on off the real meshes (``lining.hidden_fraction``): the
#: rows hid 62% of the wall face (p10 45%) and 21% of the 60 units over its
#: top.  Now four rows, a stalk every 8, each leaning up to 5 degrees, the
#: back row 280-320 tall and the stepped-out rows 215-270, with 18 leaves a
#: stalk (``props.corn.VARIANTS``), on a painted corn surface
#: (``corn_maze._CORN``): 74% (p10 53%) and 38%, for 12,540 stalks against
#: 9,167 (the map 24,598 props against 21,228).  That build still had 78
#: stalk-free runs of 80 and more, so the back two rows now carry on behind props (Dresser.free, back=True),
#: refused stalks taper, and :func:`refill_bare` puts back what the
#: vignettes and the support pass took (Z89 bounds the worst run).
BAND_DEPTH = 76.0
BAND_LINING = Lining(step=8.0, rows=4, depth=BAND_DEPTH, tuck=16.0, gap=_STALK_GAP, lean=5.0)
BAND_STEP = BAND_LINING.step
#: The open rooms' own corn (farmyard, pumpkin patch, heart): a plant every
#: 5, not 8.  The maze faces get the density pass's under- and front-corn on
#: top of the band (corn_maze_setpieces); these walls have only the band, and
#: measured head-on hid 45-48% of the farmyard's east wall against 77-88% on
#: the maze faces (the farmyard wall read as bare wall texture).
OPEN_LINING = replace(BAND_LINING, step=5.0)


class _Planted:
    """Where stalks already stand, on a coarse grid, so two faces meeting
    at a corner do not plant the same spot twice.  7 apart, not 10:
    the lining's four staggered rows stand 10 along (6-14 with
    the wobble) and 0-30 across from each other."""

    def __init__(self, spacing: float = 7.0):
        self.spacing = spacing
        self.cells: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def near(self, x: float, y: float) -> bool:
        s = self.spacing
        cx, cy = int(x // s), int(y // s)
        return any(math.hypot(x - px, y - py) < s
                   for gx in (cx - 1, cx, cx + 1) for gy in (cy - 1, cy, cy + 1)
                   for px, py in self.cells.get((gx, gy), ()))

    def add(self, x: float, y: float) -> None:
        s = self.spacing
        self.cells.setdefault((int(x // s), int(y // s)), []).append((x, y))


def _band_stalk(k: int, row: int = 1) -> tuple[str, float]:
    """The *k*-th stalk of a band, in lining *row*: ``(model, scale)``.  Row 0
    (tucked into the wall) stands tallest, 240-330, its leaves well over the
    200-unit wall top; row 1 (at the face) about 200-270; rows 2 and 3
    (stepped out) 200-270 (the band's fit trims the widest), so the top edge is ragged and the corn stands over
    the wall all along it.  Both stalk models in every row, the scale drawn
    off a golden-ratio sequence (otherwise the rows read as one clump
    repeated), so no two
    neighbours along a row are alike."""
    j = k // 4
    f = (k * 0.6180339887) % 1.0
    if row == 0:
        return (STALK, 2.45 + 0.3 * f) if j % 3 == 1 else (STALK_THIN, 3.0 + 0.65 * f)
    if row == 1:
        return (STALK_THIN, 2.4 + 0.6 * f) if j % 3 == 2 else (STALK, 2.1 + 0.35 * f)
    return (STALK, 2.1 + 0.3 * f) if (j + row) % 4 == 0 else (STALK_THIN, 2.3 + 0.7 * f)


def _corn_band(d: "Dresser", zone: str, horizontal: bool, face: float, a0: float, a1: float,
               sign: int, z: float, salt: int, planted: _Planted,
               blockers: list[Bounds] = (), lining: Lining = BAND_LINING) -> int:
    """A band of corn along one wall face (:func:`zmforge.dressing.lining.line_face`).

    The face is the line ``y = face`` (``horizontal``) or ``x = face``, from
    *a0* to *a1* along it; *sign* is the side the corridor is on.  Any of
    *blockers* (the other corn walls) that stands in the band splits it, so
    no stalk is planted into a wall that meets this one.  Every stalk goes
    through the dresser's band rules (``band=True``), so no clear zone takes
    one.  Returns how many stalks it planted."""
    spans = band_spans(horizontal, face, a0, a1, sign, lining.depth, blockers)
    _BAND_FACES.append((zone, horizontal, face, sign, z, spans, planted))

    def place(model: str, x: float, y: float, yaw: float, scale: float,
              tilt: tuple[float, float] = (0.0, 0.0), back: bool = False) -> bool:
        if planted.near(x, y):
            return False
        if d.put(zone, model, x, y, z, yaw, scale, band=True, tilt=tilt, back=back):
            planted.add(x, y)
            return True
        return False

    return line_face(horizontal, face, spans, sign, _band_stalk, _extent, place, lining=lining, salt=salt)


#: Every band face laid this build, ``(zone, horizontal, face, sign, z,
#: spans, planted)``, for the back row (:func:`_back_row`).
_BAND_FACES: list[tuple] = []

#: The back row: stalks left over under the prop cap go where the
#: band left the longest bare stretch of earth wall.  Measured on a
#: built map: the bands stop about 200 units
#: at every bought gate (the blueprint's own door apron, 32 either side of
#: the hole, plus half a front stalk's 60-72 unit spread beyond it), 140-170
#: at the wall buys, the box and the perks, 130-140 at the zombie spawns and
#: the open boundaries.  A back-row stalk stands at the wall face, square to
#: it and slimmer than the front row's, so it fits the ends of those
#: stretches the front row's wider, turned stalks could not.  The same rules
#: as the bands (``band=True``): nothing goes into an apron or keep-out.
BACK_ROW_BUDGET = 140
#: Props each building got from :mod:`.corn_maze_interiors`, this build.
INTERIORS: dict[str, int] = {}
BACK_ROW_SCALES = (2.2, 1.9)
BACK_ROW_MIN_GAP = 44.0


#: The farmyard's north and south walls.  They are the planks
#: ``_YARD`` gives them (checked in the map: every farmyard N/S wall brush is
#: ``t7_wood_planks_worn``), but a flat 176-unit face of that texture draws
#: as grey-brown grain from across the yard, the same as the corn walls'
#: earth, so it reads as earth.  Posts and rails proud of the face
#: give it the lines of a board fence.
YARD_POST_STEP = 96.0
YARD_RAILS = ((100.0, 106.0), (168.0, 176.0))


def _yard_boards(bp: Blueprint, fi: Bounds, fz: float) -> int:
    """Posts every :data:`YARD_POST_STEP` and two rails along the
    farmyard's north and south wall faces, clear of the two door holes
    (house north, barn south, both on ``x = 0``).  Returns the post count."""
    posts = 0
    for side, face, sign in (("n", fi.maxs.y, -1), ("s", fi.mins.y, 1)):
        def slab(x0: float, x1: float, deep: float, z0: float, z1: float, name: str) -> None:
            y0, y1 = sorted((face, face + sign * deep))
            bp.add_block(Bounds.between((x0, y0, fz + z0), (x1, y1, fz + z1)), cm._BEAM, reachable=False,
                         id=f"farmyard_boards_{side}_{name}", note=FLOATS_ON_PURPOSE)
        for n, (x0, x1) in enumerate(((fi.mins.x, -80.0), (80.0, fi.maxs.x))):
            k = int((x1 - x0) // YARD_POST_STEP)
            for i in range(k + 1):
                x = x0 + 3.0 + i * (x1 - x0 - 6.0) / k
                slab(x - 3.0, x + 3.0, 5.0, 0.0, 180.0, f"post_{n}_{i}")
                posts += 1
            for r, (z0, z1) in enumerate(YARD_RAILS):
                slab(x0, x1, 3.0, z0, z1, f"rail_{n}_{r}")
    return posts


def _back_row(d: "Dresser", budget: int = BACK_ROW_BUDGET) -> int:
    """Fill the widest gaps along the band faces, widest first, until
    *budget* stalks are placed or no gap takes one.  Returns how many."""
    gaps = []
    for zone, horizontal, face, sign, z, spans, planted in _BAND_FACES:
        near = []
        for pts in planted.cells.values():
            for px, py in pts:
                off, along = (py, px) if horizontal else (px, py)
                if 0.0 <= (off - face) * sign <= BAND_DEPTH:
                    near.append(along)
        for s0, s1 in spans:
            if s1 - s0 < 40.0:
                continue
            marks = sorted([s0 - 20.0] + [a for a in near if s0 - 20.0 <= a <= s1 + 20.0] + [s1 + 20.0])
            for m0, m1 in zip(marks, marks[1:]):
                if m1 - m0 >= BACK_ROW_MIN_GAP * 2:
                    gaps.append((m1 - m0, zone, horizontal, face, sign, z, max(s0, m0), min(s1, m1), planted))
    gaps.sort(key=lambda g: -g[0])
    placed = 0
    for width, zone, horizontal, face, sign, z, g0, g1, planted in gaps:
        n = max(1, int((g1 - g0) // BACK_ROW_MIN_GAP) - 1)
        for i in range(1, n + 1):
            if placed >= budget:
                return placed
            a = g0 + i * (g1 - g0) / (n + 1)
            yaw = yaw_for(placed + i, 3)
            for scale in BACK_ROW_SCALES:
                ex0, ex1, ey0, ey1 = _extent(STALK_THIN, scale, yaw)
                if horizontal:
                    x, y = a, (face + _STALK_GAP - ey0 if sign > 0 else face - _STALK_GAP - ey1)
                else:
                    x, y = (face + _STALK_GAP - ex0 if sign > 0 else face - _STALK_GAP - ex1), a
                if planted.near(x, y):
                    break
                if d.put(zone, STALK_THIN, x, y, z, yaw, scale, band=True, back=True):
                    planted.add(x, y)
                    placed += 1
                    break
    return placed


#: The refill (:func:`refill_bare`): bare stretches of a lined face longer
#: than this get back-row stalks, one every :data:`REFILL_STEP` along.
REFILL_MIN = 16.0
REFILL_STEP = 12.0
#: How far a refill stalk's footprint may reach into its (24-thick) wall.
REFILL_TUCK = 22.0
#: The refill's rounds (:func:`refill_bare`), each a list of the scale shares
#: a stalk is tried at; the support pass runs after each round.  The last
#: round's 0.4 keeps a tucked stalk's leaves (half-spread 14) off a vignette
#: blanket 25 out from the face.
REFILL_SIZES = ((1.0, 0.7, 0.5), (0.55, 0.4, 0.3))


def refill_bare(bp: Blueprint, d: "Dresser", lining: Lining = BAND_LINING,
                sizes: Sequence[float] = (1.0, 0.7, 0.5)) -> int:
    """After the last dressing pass: back-row stalks (tapered down as far as
    ``lining.taper`` goes) into every stretch of a lined face still bare for
    more than :data:`REFILL_MIN`, outside the recorded openings.  WHY (no lined wall may show a
    bare stretch): the vignettes
    trim the corn from under their parts and the support pass (Z44) drops
    stalks a later blanket or rug landed under, so the back rows lost 140-180
    units at a time after the bands were laid.  Same rules as the bands
    (``band=True, back=True``), each stalk at the first of *sizes* (its
    scale's share) the dresser takes: the caller runs the support pass after
    and calls again with smaller *sizes*, so a stalk whose leaves landed on a
    blanket comes back smaller.  Returns how many went in."""
    from ..blueprint.elements import PropScatter

    stalks = [(p.origin, (MODEL_BOX[p.model][1][0] - MODEL_BOX[p.model][0][0]) * p.scale / 4.0)
              for s in bp.elements(PropScatter) for p in s.props if "corn_stalk" in p.model]
    # A refill stalk may reach further into the wall than the band's own
    # (REFILL_TUCK), so a small one's stem stands at the face, behind a part
    # set flush against it.
    tucked = replace(lining, tuck=REFILL_TUCK)
    planted = _Planted()
    for o, _r in stalks:
        planted.add(o.x, o.y)
    placed = 0
    k = 0
    for zone, horizontal, face, sign, z, spans, _ in _BAND_FACES:
        # What each stalk hides: half its leaf spread either side of its
        # stem (the Z89 measure, verify.lining.COVER).
        here = [((o.x if horizontal else o.y) - r, (o.x if horizontal else o.y) + r) for o, r in stalks
                if -20.0 <= ((o.y if horizontal else o.x) - face) * sign <= lining.depth + 4.0
                and z - 40.0 <= o.z <= z + 400.0]
        for span in spans:
            for r0, r1 in bare_runs(here, span):
                if r1 - r0 <= REFILL_MIN:
                    continue
                n = max(1, int((r1 - r0) // REFILL_STEP))
                for i in range(1, n + 1):
                    a = r0 + i * (r1 - r0) / (n + 1)
                    k += 1
                    yaw = yaw_for(k, 7)
                    done = False
                    for row in range(lining.back_rows):
                        model, scale = _band_stalk(k * lining.rows + row, row)
                        for size in sizes:
                            x, y, sc = plant_spot(horizontal, face, span[0], span[1], sign, row, a, model,
                                                  scale * size, yaw, _extent, tucked)
                            if planted.near(x, y):
                                done = True
                                break
                            if d.put(zone, model, x, y, z, yaw, sc, band=True, back=True):
                                planted.add(x, y)
                                placed += 1
                                done = True
                                break
                        if done:
                            break
    d.flush()
    return placed


def _room_bands(d: "Dresser", zone: str, room, walls: list[Bounds], salt: int, planted: _Planted,
                sides=(Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST), lining: Lining = BAND_LINING) -> int:
    """Corn bands along an outdoor room's own inside faces (*sides*) and
    along both long faces of every corn wall in *walls* inside it."""
    z = room.floor_z
    total = 0
    faces = _band_faces(room, walls, sides)
    for n, (horizontal, face, a0, a1, sign) in enumerate(faces):
        total += _corn_band(d, zone, horizontal, face, a0, a1, sign, z, salt + n * 11, planted, walls,
                            lining=lining)
    total += _wall_ends(d, zone, room, walls, planted)
    return total


def _band_faces(room, walls: Sequence[Bounds], sides) -> list[tuple[bool, float, float, float, int]]:
    """``(horizontal, face, a0, a1, sign)`` of every face :func:`_room_bands`
    lines: the room's own inside *sides* and both long faces of each corn
    wall in *walls*."""
    i = room.interior
    faces = []
    if Side.NORTH in sides:
        faces.append((True, i.maxs.y, i.mins.x, i.maxs.x, -1))
    if Side.SOUTH in sides:
        faces.append((True, i.mins.y, i.mins.x, i.maxs.x, 1))
    if Side.EAST in sides:
        faces.append((False, i.maxs.x, i.mins.y, i.maxs.y, -1))
    if Side.WEST in sides:
        faces.append((False, i.mins.x, i.mins.y, i.maxs.y, 1))
    for w in walls:
        if (w.maxs.x - w.mins.x) >= (w.maxs.y - w.mins.y):
            faces += [(True, w.maxs.y, w.mins.x, w.maxs.x, 1), (True, w.mins.y, w.mins.x, w.maxs.x, -1)]
        if (w.maxs.y - w.mins.y) >= (w.maxs.x - w.mins.x):
            faces += [(False, w.maxs.x, w.mins.y, w.maxs.y, 1), (False, w.mins.x, w.mins.y, w.maxs.y, -1)]
    return faces


def _wall_ends(d: "Dresser", zone: str, room, walls: list[Bounds], planted: _Planted) -> int:
    """Two stalks across the free end of every corn wall in *walls*."""
    i, z = room.interior, room.floor_z
    total = 0
    # The free end of every corn wall: the bands stop short of it, and the
    # render showed its 24-unit end as a bare grey post at
    # every turn of the maze.  Two stalks stand across it, a hand beyond it.
    for n, w in enumerate(walls):
        long_x = (w.maxs.x - w.mins.x) >= (w.maxs.y - w.mins.y)
        mid = (w.mins.y + w.maxs.y) / 2 if long_x else (w.mins.x + w.maxs.x) / 2
        for out, end in ((-1, w.mins.x if long_x else w.mins.y), (1, w.maxs.x if long_x else w.maxs.y)):
            px, py = (end + out * 4.0, mid) if long_x else (mid, end + out * 4.0)
            if not (i.mins.x + 2 < px < i.maxs.x - 2 and i.mins.y + 2 < py < i.maxs.y - 2):
                continue  # it meets the room's own corn
            if any(o is not w and o.mins.x - 1 <= px <= o.maxs.x + 1 and o.mins.y - 1 <= py <= o.maxs.y + 1
                   for o in walls):
                continue  # it meets another wall
            for k, lat in enumerate((-8.0, 8.0)):
                model, scale = (STALK, STALK_SCALE) if k == 0 else (STALK_THIN, STALK_SCALE + 0.4)
                along = end + out * END_STALK_OUT
                x, y = (along, mid + lat) if long_x else (mid + lat, along)
                yaw = (n * 53 + k * 140) % 360.0
                if d.put(zone, model, x, y, z, yaw, scale, band=True):
                    planted.add(x, y)
                    total += 1
    return total


#: A brush table's plank top, leg and rail sizes.
TABLE_TOP = 3.0
TABLE_LEG = 5.0
TABLE_RAIL = 5.0


def _steps(a: float, b: float, step: float) -> list[float]:
    """``a``, ``a + step``, ... up to *b*."""
    return [a + i * step for i in range(int((b - a) // step) + 1)]


def _brush_table(bp: Blueprint, box: Bounds, ident: str) -> None:
    """A wooden table filling *box*: a :data:`TABLE_TOP`-thick plank top
    overhanging four :data:`TABLE_LEG`-square legs by 4, a rail under the top
    between the legs, and a clip brush over the whole box (nothing walks
    under or climbs it)."""
    x0, y0, z0 = box.mins.x, box.mins.y, box.mins.z
    x1, y1, z1 = box.maxs.x, box.maxs.y, box.maxs.z
    zt = z1 - TABLE_TOP
    bp.add_block(Bounds.between((x0, y0, zt), (x1, y1, z1)), cm._PLANKS, reachable=False,
                 id=f"{ident}_top", note="table top")
    lx0, lx1, ly0, ly1 = x0 + 4.0, x1 - 4.0 - TABLE_LEG, y0 + 4.0, y1 - 4.0 - TABLE_LEG
    for n, (lx, ly) in enumerate(((lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1))):
        bp.add_block(Bounds.between((lx, ly, z0), (lx + TABLE_LEG, ly + TABLE_LEG, zt)), cm._PLANKS,
                     reachable=False, id=f"{ident}_leg_{n}", note="table leg")
    rz = zt - TABLE_RAIL
    for n, rail in enumerate((
            Bounds.between((lx0 + TABLE_LEG, ly0 + 1.0, rz), (lx1, ly0 + TABLE_LEG - 1.0, zt)),
            Bounds.between((lx0 + TABLE_LEG, ly1 + 1.0, rz), (lx1, ly1 + TABLE_LEG - 1.0, zt)),
            Bounds.between((lx0 + 1.0, ly0 + TABLE_LEG, rz), (lx0 + TABLE_LEG - 1.0, ly1, zt)),
            Bounds.between((lx1 + 1.0, ly0 + TABLE_LEG, rz), (lx1 + TABLE_LEG - 1.0, ly1, zt)))):
        bp.add_block(rail, cm._PLANKS, reachable=False, id=f"{ident}_rail_{n}", note="table rail")
    bp.add_block(box, CLIP, reachable=False, id=f"{ident}_clip", note="table clip")



#: Farmhouse furniture heights: the kitchen counter (over the jump, so not
#: a perch, like the table), a rug's thickness, the bed frame's deck.
COUNTER_H = 42.0
RUG_H = 1.0
BED_FRAME_H = 12.0
#: A braided rug: a red weave (the worn brick laid small reads as a tight
#: weave, not as bricks) inside a dark felt border.
RUG_FIELD = Material("t7_brick_worn_red", 12.0)
RUG_BORDER = Material("t7_rubber_roof_granular", 24.0)
RUG_BORDER_W = 8.0


def _front_face(box: Bounds, front: tuple[int, int]) -> tuple[bool, float, float, float]:
    """``(along_x, face, a0, a1)``: the plane of *box*'s front face and its
    extent along it."""
    fx, fy = front
    if fy:
        return True, (box.maxs.y if fy > 0 else box.mins.y), box.mins.x, box.maxs.x
    return False, (box.maxs.x if fx > 0 else box.mins.x), box.mins.y, box.maxs.y


def _proud(front: tuple[int, int], face: float, along_x: bool, a0: float, a1: float,
           z0: float, z1: float, depth: float) -> Bounds:
    """A slab *depth* proud of the front face, over ``a0..a1`` and ``z0..z1``."""
    sign = front[1] if along_x else front[0]
    n0, n1 = sorted((face, face + sign * depth))
    if along_x:
        return Bounds.between((a0, n0, z0), (a1, n1, z1))
    return Bounds.between((n0, a0, z0), (n1, a1, z1))


def _brush_cabinet(bp: Blueprint, box: Bounds, front: tuple[int, int], ident: str, *,
                   rows: int = 1, cols: int = 2) -> None:
    """A wooden cabinet, counter or dresser filling *box*, its front facing
    *front* (a unit step in x or y): a plank carcass on a dark plinth, a top
    board, *rows* x *cols* door or drawer fronts a unit proud with an iron
    knob each."""
    (x0, y0, z0), (x1, y1, z1) = box.mins, box.maxs
    bp.add_block(Bounds.between((x0, y0, z0 + 3.0), (x1, y1, z1 - 2.0)), cm._PLANKS, reachable=False,
                 id=f"{ident}_body", note="cabinet")
    along_x, face, a0, a1 = _front_face(box, front)
    # The plinth, set back 2 under the front.
    bp.add_block(Bounds.between((x0 + (2.0 if front[0] < 0 else 0.0), y0 + (2.0 if front[1] < 0 else 0.0), z0),
                                (x1 - (2.0 if front[0] > 0 else 0.0), y1 - (2.0 if front[1] > 0 else 0.0), z0 + 3.0)),
                 cm._IRON, reachable=False, id=f"{ident}_plinth", note="cabinet plinth")
    grow = (1.0 if (front[1] or front[0] < 0) else 0.0, 1.0 if (front[0] or front[1] < 0) else 0.0,
            1.0 if (front[1] or front[0] > 0) else 0.0, 1.0 if (front[0] or front[1] > 0) else 0.0)
    bp.add_block(Bounds.between((x0 - grow[0], y0 - grow[1], z1 - 2.0), (x1 + grow[2], y1 + grow[3], z1)),
                 cm._PLANKS, reachable=False, id=f"{ident}_top", note="cabinet top")
    fz0, fz1 = z0 + 5.0, z1 - 4.0
    cw, rh = (a1 - a0 - 6.0) / cols, (fz1 - fz0) / rows
    n = 0
    for r in range(rows):
        for c in range(cols):
            p0, p1 = a0 + 3.0 + c * cw + 1.0, a0 + 3.0 + (c + 1) * cw - 1.0
            q0, q1 = fz0 + r * rh + 1.0, fz0 + (r + 1) * rh - 1.0
            bp.add_block(_proud(front, face, along_x, p0, p1, q0, q1, 1.0), cm._PANEL, reachable=False,
                         id=f"{ident}_front_{n}", note="cabinet door")
            km, kz = (p0 + p1) / 2, (q1 - 4.0 if rows > 1 else q1 - 6.0)
            bp.add_block(_proud(front, face + (front[1] if along_x else front[0]), along_x, km - 1.5, km + 1.5,
                                kz - 1.5, kz + 1.5, 1.5), cm._IRON, reachable=False,
                         id=f"{ident}_knob_{n}", note="cabinet knob")
            n += 1


def _brush_shelf(bp: Blueprint, box: Bounds, front: tuple[int, int], ident: str,
                 boards: Sequence[float]) -> list[float]:
    """Open wooden shelves filling *box*, open to *front*: a back board, two
    side boards and a 2-unit board at each height in *boards* (over the
    box's floor).  Returns the world height of each board's top."""
    (x0, y0, z0), (x1, y1, z1) = box.mins, box.maxs
    along_x, face, a0, a1 = _front_face(box, front)
    sign = front[1] if along_x else front[0]
    back_at = (y0 if sign > 0 else y1) if along_x else (x0 if sign > 0 else x1)
    depth = (y1 - y0) if along_x else (x1 - x0)
    bp.add_block(_proud((0, sign) if along_x else (sign, 0), back_at, along_x, a0, a1, z0, z1, 1.5), cm._PLANKS,
                 reachable=False, id=f"{ident}_back", note="shelf back")
    for n, (s0, s1) in enumerate(((a0, a0 + 2.0), (a1 - 2.0, a1))):
        bp.add_block(_proud((0, sign) if along_x else (sign, 0), back_at, along_x, s0, s1, z0, z1, depth),
                     cm._PLANKS, reachable=False, id=f"{ident}_side_{n}", note="shelf side")
    tops = []
    for n, h in enumerate(boards):
        bp.add_block(_proud((0, sign) if along_x else (sign, 0), back_at, along_x, a0 + 2.0, a1 - 2.0,
                            z0 + h - 2.0, z0 + h, depth), cm._PLANKS, reachable=False,
                     id=f"{ident}_board_{n}", note="shelf board")
        tops.append(z0 + h)
    return tops


def _wood_stove(bp: Blueprint, x: float, y: float, z: float, ceiling: float, ident: str) -> None:
    """A cast-iron wood stove centred at ``(x, y)`` against a south wall
    (it looks north): a brick hearth, four short legs, the firebox, a top
    plate, a door, the stovepipe to *ceiling*, a warm glow in front, and a
    clip so it is no perch."""
    bp.add_block(Bounds.between((x - 34.0, y - 22.0, z), (x + 34.0, y + 44.0, z + 1.0)), cm._BRICK,
                 contents=("detail",), reachable=False, id=f"{ident}_hearth", note="stove hearth")
    for n, (lx, ly) in enumerate(((x - 16, y - 12), (x + 13, y - 12), (x - 16, y + 9), (x + 13, y + 9))):
        bp.add_block(Bounds.between((lx, ly, z + 1.0), (lx + 3.0, ly + 3.0, z + 9.0)), cm._IRON,
                     reachable=False, id=f"{ident}_leg_{n}", note="stove leg")
    bp.add_block(Bounds.between((x - 18.0, y - 14.0, z + 9.0), (x + 18.0, y + 14.0, z + 34.0)), cm._IRON,
                 reachable=False, id=f"{ident}_body", note="stove firebox")
    bp.add_block(Bounds.between((x - 20.0, y - 16.0, z + 34.0), (x + 20.0, y + 16.0, z + 36.0)), cm._IRON,
                 reachable=False, id=f"{ident}_top", note="stove top")
    bp.add_block(Bounds.between((x - 9.0, y + 14.0, z + 14.0), (x + 9.0, y + 15.5, z + 29.0)), cm._BRICK,
                 reachable=False, id=f"{ident}_door", note="stove door")
    bp.add_block(Bounds.between((x - 4.0, y - 10.0, z + 36.0), (x + 4.0, y - 2.0, ceiling)), cm._IRON,
                 reachable=False, id=f"{ident}_pipe", note="stovepipe")
    bp.add_block(Bounds.between((x - 20.0, y - 16.0, z), (x + 20.0, y + 16.0, z + 48.0)), CLIP,
                 reachable=False, id=f"{ident}_clip", note="stove clip")
    _lamp(bp, x, y + 34.0, z + 22.0, "farmhouse", f"{ident}_glow", radius=160.0)


def _rug(bp: Blueprint, box: Bounds, ident: str) -> None:
    """A braided rug over *box* (a unit thick, detail): the weave inside a
    felt border."""
    (x0, y0, z0), (x1, y1, z1) = box.mins, box.maxs
    w = RUG_BORDER_W
    bp.add_block(Bounds.between((x0 + w, y0 + w, z0), (x1 - w, y1 - w, z1)), RUG_FIELD, contents=("detail",),
                 reachable=False, id=f"{ident}_field", note="rug")
    for n, b in enumerate((Bounds.between((x0, y0, z0), (x1, y0 + w, z1)), Bounds.between((x0, y1 - w, z0), (x1, y1, z1)),
                           Bounds.between((x0, y0 + w, z0), (x0 + w, y1 - w, z1)),
                           Bounds.between((x1 - w, y0 + w, z0), (x1, y1 - w, z1)))):
        bp.add_block(b, RUG_BORDER, contents=("detail",), reachable=False, id=f"{ident}_border_{n}", note="rug border")


#: Ground cover on the outdoor floors (bare, the heart and the patch
#: read as a vast empty dark dirt floor).  Thin detail brushes, a
#: unit or two over the floor, each its own height so no two coincide: the
#: packed track, then the tilled rows, then scattered straw on top.
GROUND_H = {"path": 1.0, "tilled": 1.5, "straw": 2.0}
#: How far the rest of the dressing keeps off a patch: a prop's keep-out
#: test uses its unturned half-width, and a turned tuft reaches further.
GROUND_CLEAR = 10.0


def _ground(bp: Blueprint, x0: float, y0: float, x1: float, y1: float, z: float, kind: str,
            ident: str, d: "Dresser | None" = None) -> Bounds:
    """One patch.  With *d*, it becomes a keep-out for everything placed
    after it: a prop standing half on a patch and half off reads as
    overhanging a raised surface (Z44), so what stands on a patch is put
    there first, on purpose, and the rest keeps off."""
    material = {"path": cm._PATH, "tilled": cm._TILLED, "straw": cm._STRAW}[kind]
    box = Bounds.between((min(x0, x1), min(y0, y1), z), (max(x0, x1), max(y0, y1), z + GROUND_H[kind]))
    # The top carries the patch; the unit-high sides carry the floor's own
    # dirt (pale side faces draw as thin white outlines, like painted
    # parking bays).
    faces = FaceMaterials(default=cm._DIRT, per_side={Side.TOP: material})
    bp.add_block(box, faces, contents=("detail",), reachable=False, id=ident, note=f"ground {kind}")
    if d is not None:
        d.keepouts.append(box.grown(GROUND_CLEAR))
        d.patches.append(box.grown(GROUND_CLEAR))
        d.drop_over(box)
    return box


#: Grass along a track's edges, so its border is broken and blends into the
#: floor instead of ending on a ruled line: a low clump every
#: ``EDGE_TUFT_STEP`` or so, on either side, about two in three kept.
EDGE_TUFT = "p7_foliage_grass_tall_cluster_sml"
EDGE_TUFT_STEP = 64.0


def _edge_tufts(d: "Dresser", zone: str, box: Bounds, along_x: bool, rng: random.Random) -> int:
    """Low grass clumps just off both long edges of the strip *box*, clear
    of its keep-out and of the hayride lane (no grass on the lane, and its
    track, laid later, crosses the farmyard).  Returns how many were placed."""
    lo, hi = MODEL_BOX[EDGE_TUFT]
    n = 0
    a0, a1 = (box.mins.x, box.maxs.x) if along_x else (box.mins.y, box.maxs.y)
    # A strip that starts at a room's wall (the heart's gate path) keeps its
    # first tufts a wall's thickness in, or they sit in the wall (v2 heart).
    a = a0 + 24.0 + rng.uniform(10.0, EDGE_TUFT_STEP)
    while a < a1 - 34.0:
        for side in (-1, 1):
            if rng.random() > 0.65:
                continue
            scale = rng.uniform(0.45, 0.75)
            half = max(hi[0] - lo[0], hi[1] - lo[1]) * scale / 2.0
            off = GROUND_CLEAR + half + rng.uniform(1.0, 8.0)
            if along_x:
                x, y = a + rng.uniform(-12, 12), (box.maxs.y + off if side > 0 else box.mins.y - off)
            else:
                x, y = (box.maxs.x + off if side > 0 else box.mins.x - off), a + rng.uniform(-12, 12)
            if d.put(zone, EDGE_TUFT, x, y, box.mins.z, rng.uniform(0, 360), scale, solid=False):
                n += 1
        a += EDGE_TUFT_STEP * rng.uniform(0.7, 1.3)
    return n


def _track(bp: Blueprint, points: Sequence[tuple[float, float]], z: float, width: float, ident: str,
           kind: str = "path", d: "Dresser | None" = None, zone: str | None = None) -> None:
    """A trodden track *width* wide along *points*: one axis-aligned strip
    per straight run, and one worn patch over the middle of a slanted run
    (a slanted run laid as a chain of overlapping squares draws
    as a saw-tooth).  With *zone*, low grass breaks up the strips' long
    edges (:func:`_edge_tufts`)."""
    h = width / 2.0
    rng = random.Random(ident)
    for n, ((ax, ay), (bx, by)) in enumerate(zip(points, points[1:])):
        if abs(ax - bx) < 1.0 or abs(ay - by) < 1.0:
            box = _ground(bp, min(ax, bx) - h, min(ay, by) - h, max(ax, bx) + h, max(ay, by) + h, z, kind,
                          f"{ident}_{n}", d)
            if d is not None and zone is not None:
                _edge_tufts(d, zone, box, abs(ax - bx) >= 1.0, rng)
            continue
        cx, cy = (ax + bx) / 2.0, (ay + by) / 2.0
        wx, wy = abs(bx - ax) * 0.3 + h * 0.8, abs(by - ay) * 0.3 + h * 0.8
        _ground(bp, cx - wx, cy - wy, cx + wx, cy + wy, z, kind, f"{ident}_{n}", d)


def _crop_rows(bp: Blueprint, d: "Dresser", zone: str, rng: random.Random, x0: float, x1: float,
               ys: Sequence[float], z: float, ident: str, *, width: float = 34.0,
               clear=None, gap: tuple[float, float] = (110.0, 170.0),
               cluster: Sequence[int] = (2, 2, 3)) -> int:
    """Tilled rows along x from *x0* to *x1* at each of *ys*, cut into runs
    wherever ``clear(x, y)`` is false (a lane, a scarecrow); pumpkins sit on
    them in twos and threes with gaps between, and a weed here and there.
    Returns the pumpkins placed."""
    placed = 0
    half = width / 2.0
    # What already stands here: a row runs under none of it.
    standing = []
    for model, at, _yaw, scale, *_ in d.pending.get(zone, []):
        (lx, ly, _), (hx, hy, _) = MODEL_BOX[model]
        standing.append((at.x, at.y, max(hx - lx, hy - ly) * scale / 2.0 + 4.0))
    for r, y in enumerate(ys):
        near = [(px, pr) for px, py, pr in standing if abs(py - y) < half + pr]
        runs, start = [], None
        xs = [x0 + 10.0 * k for k in range(int((x1 - x0) // 10.0) + 1)]
        for x in xs:
            ok = ((clear is None or clear(x, y)) and d.free(x, y, z, half + 2.0, lane=False)
                  and not any(abs(px - x) < pr + 5.0 for px, pr in near))
            if ok and start is None:
                start = x
            if (not ok or x == xs[-1]) and start is not None:
                end = x if ok else x - 10.0
                if end - start >= 100.0:
                    runs.append((start, end))
                start = None
        for q, (a0, a1) in enumerate(runs):
            row = _ground(bp, a0, y - half, a1, y + half, z, "tilled", f"{ident}_{r}_{q}")
            x = a0 + rng.uniform(15.0, 60.0)
            while x < a1 - 20.0:
                for k in range(rng.choice(cluster)):
                    px, py = x + k * 17.0 + rng.uniform(-3, 3), y + rng.uniform(-7, 7)
                    if px < a1 - 8.0 and _pumpkin(d, zone, px, py, z + GROUND_H["tilled"], rng.uniform(0, 360),
                                                  PUMPKIN_SCALE + rng.choice((-0.1, 0.0, 0.1))):
                        placed += 1
                if rng.random() < 0.4 and x + 70.0 < a1:
                    d.put(zone, rng.choice(("p7_foliage_weed_cluster_lrg", "p7_foliage_weed_cluster_med")),
                          x + 70.0, y + rng.uniform(-8, 8), z + GROUND_H["tilled"], rng.uniform(0, 360),
                          solid=False)
                x += rng.uniform(*gap)
            d.keepouts.append(row.grown(GROUND_CLEAR))
            d.patches.append(row.grown(GROUND_CLEAR))
    return placed


def _tool_rack(bp: Blueprint, d: "Dresser", zone: str, a0: float, a1: float, face: float, z: float,
               facing: Facing, ident: str, *, tack: bool = False) -> None:
    """A plank board on the wall at *face* (y, looking *facing* north or
    south) from x *a0* to *a1*, with pegs and what hangs on them: long-handled
    tools built from brushes (fork, rake, hoe, spade), or for *tack* a horse
    collar, straps and the farmer's work clothes."""
    sy = facing.step.y
    def out(o0: float, o1: float) -> tuple[float, float]:
        return tuple(sorted((face + sy * o0, face + sy * o1)))  # type: ignore[return-value]
    y0, y1 = out(0.0, 2.0)
    bp.add_block(Bounds.between((a0, y0, z + 24.0), (a1, y1, z + 124.0)), cm._PLANKS, reachable=False,
                 id=f"{ident}_board", note="rack board")
    r0, r1 = out(2.0, 5.0)
    bp.add_block(Bounds.between((a0, r0, z + 110.0), (a1, r1, z + 114.0)), cm._PLANKS, reachable=False,
                 id=f"{ident}_rail", note="peg rail")
    slots = _steps(a0 + 22.0, a1 - 20.0, (a1 - a0 - 40.0) / 5.0)[:6]
    # Everything on the rack is flush against the board (Z43: fixed to it).
    ty0, ty1 = out(2.0, 4.0)
    n = 0

    def box(x0: float, x1: float, z0: float, z1: float, mat: Material, note: str, t0: float = ty0,
            t1: float = ty1) -> None:
        nonlocal n
        bp.add_block(Bounds.between((x0, t0, z + z0), (x1, t1, z + z1)), mat, contents=("detail",),
                     reachable=False, id=f"{ident}_{n}", note=note)
        n += 1

    for k, x in enumerate(slots):
        box(x - 1.5, x + 1.5, 104.0, 108.0, cm._IRON, "peg", *out(2.0, 6.0))
        kind = ("collar", "strap", "shirt", "pants", "strap", "collar")[k] if tack else \
            ("fork", "rake", "spade", "hoe", "fork", "rake")[k]
        if kind in ("fork", "rake", "hoe"):
            box(x - 1.0, x + 1.0, 36.0, 104.0, cm._PLANKS, "tool handle")
            if kind == "fork":
                box(x - 7.0, x + 7.0, 20.0, 22.0, cm._IRON, "fork head")
                for tx in (-6.0, -1.0, 4.0):
                    box(x + tx, x + tx + 1.5, 6.0, 20.0, cm._IRON, "fork tine")
                box(x - 1.0, x + 1.0, 22.0, 36.0, cm._PLANKS, "tool handle")
            elif kind == "rake":
                box(x - 10.0, x + 10.0, 32.0, 36.0, cm._IRON, "rake head")
                for tx in _steps(x - 9.0, x + 8.0, 4.0):
                    box(tx, tx + 1.0, 28.0, 32.0, cm._IRON, "rake tine")
            else:
                box(x - 5.0, x + 5.0, 30.0, 36.0, cm._IRON, "hoe blade")
        elif kind == "spade":
            box(x - 1.0, x + 1.0, 44.0, 100.0, cm._PLANKS, "spade handle")
            box(x - 5.0, x + 5.0, 100.0, 103.0, cm._PLANKS, "spade grip")
            box(x - 6.0, x + 6.0, 26.0, 44.0, cm._IRON, "spade blade")
        elif kind == "collar":
            box(x - 12.0, x - 7.0, 72.0, 104.0, RUG_BORDER, "collar side")
            box(x + 7.0, x + 12.0, 72.0, 104.0, RUG_BORDER, "collar side")
            box(x - 12.0, x + 12.0, 66.0, 72.0, RUG_BORDER, "collar bottom")
            box(x - 10.0, x - 8.0, 70.0, 106.0, cm._IRON, "hame", *out(4.0, 6.0))
            box(x + 8.0, x + 10.0, 70.0, 106.0, cm._IRON, "hame", *out(4.0, 6.0))
        elif kind == "strap":
            for sx in (-4.0, 2.0):
                box(x + sx, x + sx + 2.5, 40.0 + 12.0 * (sx > 0), 108.0, RUG_BORDER, "strap")
            box(x - 4.0, x + 4.5, 60.0, 64.0, cm._IRON, "buckle", *out(4.0, 5.0))
        else:
            m = "p7_clothes_hanging_01_tshirt" if kind == "shirt" else "p7_clothes_hanging_01_pants"
            lo, hi = MODEL_BOX[m]
            # Wide along their own y: a quarter turn hangs them flat to a
            # wall that runs along x.
            d.put(zone, m, x, (ty0 + ty1) / 2 + sy * 2.0, z + 102.0 - (hi[2] - lo[2]), 90.0,
                  check=False, lane=False, solid=False)
    d.keepouts.append(Bounds.between((a0, min(y0, ty1 + sy * 20), z), (a1, max(y1, ty1 + sy * 20), z + 130.0)))


def _bed_frame(bp: Blueprint, box: Bounds, ident: str) -> None:
    """A plank bed frame over *box* (head at its north end, against the
    wall): the deck, a headboard and a footboard."""
    (x0, y0, z0), (x1, y1, z1) = box.mins, box.maxs
    bp.add_block(box, cm._PLANKS, reachable=False, id=f"{ident}_deck", note="bed frame")
    bp.add_block(Bounds.between((x0, y1 - 4.0, z1), (x1, y1, z0 + 44.0)), cm._PLANKS, reachable=False,
                 id=f"{ident}_head", note="headboard")
    bp.add_block(Bounds.between((x0, y0, z1), (x1, y0 + 3.0, z0 + 22.0)), cm._PLANKS, reachable=False,
                 id=f"{ident}_foot", note="footboard")


#: A plank board behind a machine or wall buy on a corn wall: the corn
#: bands keep clear of the machine, and the corn wall's brush showed there
#: as a bare slab (the heart's north wall behind
#: the box and the wall buy, the power's dead end).  ``half`` is along the
#: wall, sized to the gap the bands leave, so the corn meets its posts.
BACKBOARD_T = 2.0
BACKBOARD_H = 184.0
BACKBOARD_HALF = {"box": 116.0, "wallbuy": 108.0, "corn_wallbuy": 96.0, "power": 94.0}


def _backboard(bp: Blueprint, x: float, y: float, z: float, facing: Facing, half: float, ident: str,
               text: str = "") -> None:
    """A board of vertical planks on the wall face through ``(x, y)`` (it
    looks *facing*), from the floor *z* up :data:`BACKBOARD_H`, a post at
    each end and a cap along the top, lettered *text* near the top."""
    step = facing.step

    def slab(a0: float, a1: float, out0: float, out1: float, z0: float, z1: float) -> Bounds:
        if step.x:
            xs = sorted((x + step.x * out0, x + step.x * out1))
            return Bounds.between((xs[0], y + a0, z0), (xs[1], y + a1, z1))
        ys = sorted((y + step.y * out0, y + step.y * out1))
        return Bounds.between((x + a0, ys[0], z0), (x + a1, ys[1], z1))

    t = BACKBOARD_T
    bp.add_block(slab(-half, half, 0.0, t, z, z + BACKBOARD_H), cm._PLANKS, reachable=False,
                 id=f"{ident}_board", note="plank board")
    for n, a in enumerate((-half, half - 6.0)):
        bp.add_block(slab(a, a + 6.0, t, t + 5.0, z, z + BACKBOARD_H + 12.0), cm._PLANKS, reachable=False,
                     id=f"{ident}_post_{n}", note="board post")
    bp.add_block(slab(-half + 6.0, half - 6.0, t, t + 5.0, z + BACKBOARD_H - 6.0, z + BACKBOARD_H), cm._PLANKS,
                 reachable=False, id=f"{ident}_cap", note="board cap")
    if text:
        brush_text(bp, text, at=Point(x + step.x * t, y + step.y * t, z + BACKBOARD_H - 26.0),
                   facing=facing, cell=2.2, plate=False, ident=f"{ident}_text")

#: How far beyond a corn wall's free end its two capping stalks stand.
END_STALK_OUT = 6.0

def _scarecrow_frame(x: float, y: float, z: float) -> Bounds:
    """The box a scarecrow takes up (:func:`_scarecrow_body`): its pole and
    the cross-arm, which the scripted head turns on top of."""
    a = SCARECROW_ARM
    return Bounds.between((x - a, y - a, z), (x + a, y + a, z + POLE_TOP))


#: The scarecrow (the kit cross reads as a small
#: statue on a grey plinth, not a scarecrow on a pole): a
#: brush-built wooden pole standing straight in the ground, no plinth and no
#: mound, with a plank cross-arm near its top and a man-sized figure hung on
#: it.  The kit cross (:data:`CROSS`, 78 tall on a 31-unit stone plinth) was
#: too short to carry a figure the size of a person.  The pole's top (the
#: scripted head's base, ``SCARECROWS``) is ``POLE_TOP`` over the ground; the
#: arms sit at shoulder height, ``ARM_Z``; the shirt runs from the belt,
#: ``BELT_Z``, to the shoulders; the legs hang from the belt to ``FEET_Z``,
#: clear of the ground as a scarecrow's do.  Static: in game only the head
#: and its chest sign turn.
POLE_TOP = 150.0
POLE_HALF = 3.0
ARM_Z = 128.0
BELT_Z = 92.0
FEET_Z = 48.0
SCARECROW_ARM = 46.0
#: How far in front of its post the heart's scarecrow lands when it climbs
#: down to be the boss: clear of the pole and cross-arm (``SCARECROW_ARM``).
SCARECROW_FOOT = 64.0


def static_head_name(name: str) -> str:
    """The ``targetname`` of a scripted scarecrow's static head:
    the brush head the map carries, which the script deletes when it spawns
    its turning one (``corn_maze_script.scarecrow_script``)."""
    return f"zmf_scarecrow_head_{name}"


#: The static head (without one the scarecrow reads as a headless shirt on
#: a T-post, since the scripted jack never draws in the editor): a burlap sack stuffed on the
#: pole top, tied at the neck, a face inked on it and a straw hat.  Heights
#: over the pole top; *b* is across the arms, the face on its -b side (the
#: side the scarecrow looks out of, see the placement in ``build_all``).
HEAD_SACK = (8.0, 7.5, 18.0)
HEAD_BRIM = (14.0, 13.0, 2.0)
HEAD_CROWN = (7.0, 6.5, 7.0)


def _scarecrow_body(bp: Blueprint, d: "Dresser", zone: str, x: float, y: float, z: float, yaw: float,
                    ident: str, arm: float = SCARECROW_ARM, head: str = "") -> Bounds:
    """A scarecrow on its pole at ``(x, y)`` standing on *z*, its arms along
    the local x of *yaw*.  The pole is a solid post into the ground; the
    arms and clothes hang on it.  A non-blank *head* gives it a static sack
    head and straw hat, a brush entity of that ``targetname`` the script can
    delete (:func:`static_head_name`).  Returns the pole's box."""
    rad = math.radians(yaw)
    along_x = abs(math.cos(rad)) >= abs(math.sin(rad))

    def piece(a0: float, a1: float, b0: float, b1: float, z0: float, z1: float, mat: Material, name: str,
              note: str = FLOATS_ON_PURPOSE, targetname: str = "") -> Bounds:
        """*a* along the arms, *b* across them, heights over the ground."""
        lo, hi = ((x + a0, y + b0), (x + a1, y + b1)) if along_x else ((x + b0, y + a0), (x + b1, y + a1))
        box = Bounds.between((lo[0], lo[1], z + z0), (hi[0], hi[1], z + z1))
        bp.add_block(box, mat, reachable=False, id=f"{ident}_{name}", note=note, targetname=targetname)
        return box

    h = POLE_HALF
    pole = piece(-h, h, -h, h, 0.0, POLE_TOP, cm._BEAM, "pole", note="scarecrow pole")
    a = arm
    piece(-a, a, -2.0, 2.0, ARM_Z, ARM_Z + 5.0, cm._PLANKS, "arms")
    # A straw collar at the pole's top, which the head (the script's jack,
    # or a pumpkin on a dead end's scarecrow) sits on: a pumpkin balanced on
    # a 6-unit pole top is a Z44 (10% of its footprint).
    piece(-8.0, 8.0, -8.0, 8.0, POLE_TOP - 4.0, POLE_TOP, cm._STRAW, "collar")
    chest = min(11.0, a - 8.0)
    for side, (s0, s1) in (("l", (-a + 5.0, -chest)), ("r", (chest, a - 5.0))):
        piece(s0, s1, -3.5, 3.5, ARM_Z - 3.0, ARM_Z + 6.0, cm._FLANNEL, f"sleeve_{side}")
    # The shirt stops short of the chest sign the script pins 5 in front of
    # the pole (corn_maze_script.scarecrow_parts).
    piece(-chest, chest, -4.5, 4.5, BELT_Z, ARM_Z + 7.0, cm._FLANNEL, "body")
    piece(-chest + 1.0, chest - 1.0, -4.75, 4.75, BELT_Z - 2.0, BELT_Z + 3.0, cm._BEAM, "belt")
    leg = min(8.0, chest - 1.0)
    for side, (s0, s1) in (("l", (-leg, -1.5)), ("r", (1.5, leg))):
        piece(s0, s1, -3.5, 3.5, FEET_Z, BELT_Z - 2.0, cm._DENIM, f"leg_{side}")
    if head:
        t = POLE_TOP
        sa, sb, sh = HEAD_SACK
        piece(-sa, sa, -sb, sb, t, t + sh, cm._WHITEWASH, "head_sack", targetname=head)
        # Tied at the neck with a cord.
        piece(-sa - 0.5, sa + 0.5, -sb - 0.5, sb + 0.5, t + 2.0, t + 4.0, cm._BEAM, "head_cord",
              targetname=head)
        # Two inked eyes and a stitched mouth on the face.
        f0, f1 = -sb - 1.0, -sb
        for side, (e0, e1) in (("l", (-5.0, -2.0)), ("r", (2.0, 5.0))):
            piece(e0, e1, f0, f1, t + 10.0, t + 13.0, cm._IRON, f"head_eye_{side}", targetname=head)
        piece(-4.0, 4.0, f0, f1, t + 6.0, t + 7.0, cm._IRON, "head_mouth", targetname=head)
        ba, bb, bh = HEAD_BRIM
        piece(-ba, ba, -bb, bb, t + sh - 1.0, t + sh - 1.0 + bh, cm._STRAW, "head_brim", targetname=head)
        ca, cb, ch = HEAD_CROWN
        piece(-ca, ca, -cb, cb, t + sh - 1.0 + bh, t + sh - 1.0 + bh + ch, cm._STRAW, "head_crown",
              targetname=head)
    return pole


def _sign_board(bp: Blueprint, x0: float, x1: float, y: float, z: float, ident: str,
                lines: Sequence[tuple[str, float, float]] = (), facing: Facing = Facing.SOUTH) -> list[Bounds]:
    """A painted board on two posts, facing north-south, for a notice to hang
    on, its *facing* face (south or north) lettered with *lines* ``(text,
    cell, height over z)`` (a blank board read as nothing at all in the
    render); the posts stand behind it."""
    back = 1.0 if facing == Facing.SOUTH else -1.0
    boxes = [Bounds.between((x0, y - 2, z + 40.0), (x1, y + 2, z + 96.0))]
    for i, px in enumerate((x0 + 6.0, x1 - 6.0)):
        boxes.append(Bounds.between((px - 3, y + 2 * back, z), (px + 3, y + 8 * back, z + 96.0)))
    for i, box in enumerate(boxes):
        bp.add_block(box, cm._PANEL if i == 0 else cm._BEAM, reachable=False, id=f"{ident}_{i}",
                     note="sign board" if i == 0 else "sign post")
    for n, (text, cell, dz) in enumerate(lines):
        brush_text(bp, text, at=Point((x0 + x1) / 2, y - 2.0 * back, z + dz), facing=facing, cell=cell,
                   plate=False, ident=f"{ident}_text_{n}")
    return boxes


def _pumpkin(d: Dresser, zone: str, x: float, y: float, z: float, yaw: float,
             scale: float = PUMPKIN_SCALE, model: str = PUMPKIN, **k) -> bool:
    return d.put(zone, model, x, y, z, yaw, scale, **k)


#: The quest's burning jack-o'-lanterns: the tall carved one, a size up, on a
#: hay bale so it stands over every ordinary pumpkin.
QUEST_JACK_SCALE = 1.25

#: Each quest lantern, for the script that owns it: ``(x, y, z of the bale
#: top, yaw)``, in the quest's target order, filled by :func:`build_all`.
#: The lantern itself is **not** placed here.  A placed model and a map
#: ``light`` are static: the light is baked into the lightmap at compile and
#: no server script can switch it off (a shot lantern's
#: glow would stay on).  So the lantern is a ``script_model`` and its
#: glow a looped effect on a ``tag_origin``, both spawned by
#: :func:`zmforge.recipes.corn_maze_script.lantern_script`, which puts it out.
QUEST_JACKS: list[tuple[float, float, float, float]] = []


def _quest_jack(bp: Blueprint, d: Dresser, zone: str, x: float, y: float, z: float,
                yaw: float) -> tuple[float, float, float]:
    """One of the quest's three lanterns: a bale for :data:`JACK_TALL` to sit
    on (the lantern and its glow are the script's, :data:`QUEST_JACKS`).
    Returns the middle of the lantern, the shot's target."""
    bale = _bale(d, zone, x, y, z, yaw=yaw)
    d.keepouts += [b.grown(10.0) for b in bale]
    top = bale[-1].maxs.z
    QUEST_JACKS.append((x, y, top, yaw))
    height = MODEL_BOX[JACK_TALL][1][2] * QUEST_JACK_SCALE
    return (x, y, top + height / 2.0)


def _basket_of_oranges(d: Dresser, zone: str, x: float, y: float, z: float, yaw: float,
                       which: int = 1, **k) -> None:
    """A harvest box with a few oranges (real-size ones) heaped on it."""
    model = BASKETS[which % len(BASKETS)]
    if d.put(zone, model, x, y, z, yaw, **k):
        top = z + MODEL_BOX[model][1][2]
        for i, (dx, dy) in enumerate(((-4, -3), (4, 2), (0, 5), (-2, 0))):
            d.put(zone, ORANGE, x + dx, y + dy, top, i * 70.0, 1.0, check=False)


#: The open crate's lid, so what stands on a crate stands on wood, not on
#: the rim of an open box.
CRATE_LID = "p7_crate_wood_01_short_open_lid"
#: How each stock perk machine is dressed as the farm drink its line names
#: (P14: stock prefabs alone do not name the farm drinks).  The machines
#: stay stock -- a stock perk's model is the prefab's and its collision the
#: framework's ``zm_collision_perks1``, so swapping the model the way the DMV
#: swaps its registration car (a custom perk's ``machine_model``) would lose
#: the stock perk -- and each is wrapped instead: things on the floor either
#: side of it, against its wall, and outdoors a plank stall roof on two posts
#: over it, like the farm stand's canopy that already covers the two ciders.
#: ``lat`` is along the wall (the sign picks the side), ``fwd`` out of the
#: wall from the machine's origin; a stack is placed bottom up, each item on
#: the one before.  Nothing stands in the Z9 approach (40 wide in front).
PERK_STALLS: dict[str, dict] = {
    # Hot cider: a boiling pot on a bale, the jug and bottles, a lamp.
    "quick_revive": {"zone": "farmyard", "stall": False, "sides": (
        (-60.0, [("bale",), ("p7_pot_metal_boiling_lg",)]),
        (-60.0, [("on_bale", JUG, 0.0, 13.0), ("on_bale", LAMP, 0.0, -14.0)]),
        (60.0, [(CRATE,), (CRATE_LID,), ("oranges",)]),
    )},
    # Cold cider: a blue drum with its lid, bottles stood on it, and a crate.
    "speed_cola": {"zone": "farmyard", "stall": False, "sides": (
        (-54.0, [("p7_barrel_metal_55gal_blue",), ("p7_zm_der2_barrel_metal_55gal_lid",),
                 (JAR,)]),
        (58.0, [(CRATE,), (CRATE_LID,), (JUG,)]),
    )},
    # Pumpkin spice: a bale with a pumpkin and the spice pot on it, and a
    # heap of pumpkins on the ground the other side (no bale there: the
    # patch riser at (2150, -480) wants hay 100 units off, test_corn_maze).
    "stamin_up": {"zone": "patch", "stall": True, "sides": (
        (62.0, [("bale",), (PUMPKIN,)]),
        (62.0, [("on_bale", "p7_pot_metal_boiling_lg", 0.0, 14.0)]),
        (96.0, [(PUMPKIN,)]),
        (-58.0, [(PUMPKIN,)]), (-60.0, [("far", PUMPKIN, 20.0)]), (-80.0, [(PUMPKIN,)]),
    )},
    # Moonshine: a still -- the drum with the boiling pot on it and the big
    # jug -- and a crate of bottles.
    "double_tap": {"zone": "heart", "stall": True, "sides": (
        (-54.0, [("p7_barrel_metal_55gal_blue",), ("p7_zm_der2_barrel_metal_55gal_lid",),
                 ("p7_pot_metal_boiling_lg",)]),
        (-84.0, [(JUG,)]),
        (60.0, [(CRATE,), (CRATE_LID,), ("p7_bottle_glass_liquor_01",)]),
        (60.0, [("on_crate", JAR, -8.0), ("on_crate", "p7_bottle_glass_wine_01", 9.0)]),
    )},
    # The mule's: its cart, its feed sacks on a bale, a lamp.
    "mule_kick": {"zone": "heart", "stall": True, "sides": (
        (-78.0, [("cart",)]),
        (62.0, [("bale",), ("on_bale", LAMP, 0.0, 10.0)]),
        (96.0, [(SACK,)]),
    )},
    # Farmhouse lemonade (indoors, no roof): the pitcher and mugs on a
    # crate, and a box of "lemons" (the oranges again).  Mugs, not
    # p6_bar_beer_glass: the link cannot find that model (see
    # props.MODEL_BOX) and the build fails on it.
    # Crates of oranges and a jug do not say lemonade, so a lettered
    # board goes over the machine.
    "juggernog": {"zone": "farmhouse", "stall": False, "sign": "LEMONADE", "sides": (
        (-58.0, [(CRATE,), (CRATE_LID,), (JUG,)]),
        (-58.0, [("on_crate", "p7_cup_coffee_mug", 9.0), ("on_crate", "p7_cup_coffee_mug", -10.0, 8.0)]),
        (58.0, [(CRATE,), (CRATE_LID,), ("oranges",)]),
    )},
}
#: The stall roof: its underside (the farm stand's canopy is at 150 over the
#: two cider machines), how far it reaches either side and out of the wall.
STALL_ROOF_Z = 150.0
#: A lidded crate's top: the crate, then the lid's own thickness (the lid's
#: box sits 29 units up its origin, in the crate's frame).
_CRATE_TOP = MODEL_BOX[CRATE][1][2] + MODEL_BOX[CRATE_LID][1][2] - MODEL_BOX[CRATE_LID][0][2]
STALL_HALF = 68.0
STALL_DEPTH = 70.0


def _dress_perk_stalls(bp: Blueprint, d: "Dresser") -> None:
    """Each stock perk machine dressed as the drink its line names
    (:data:`PERK_STALLS`).  Placed with ``check=False``: every spot is inside
    the machine's own 130-unit keep-out, which is what keeps the rest of the
    dressing off it."""
    from ..blueprint.elements import Machine

    for machine in bp.elements(Machine):
        slug = getattr(machine.perk, "slug", None)
        spec = PERK_STALLS.get(slug)
        if spec is None:
            continue
        zone = spec["zone"]
        fwd_v = machine.facing.step
        side_v = Point(-fwd_v.y, fwd_v.x, 0.0)
        o = machine.position
        floor = o.z
        along_x = abs(side_v.x) > 0.5  # the wall runs along x
        yaw0 = 0.0

        def at(lat: float, fwd: float) -> tuple[float, float]:
            return (o.x + side_v.x * lat + fwd_v.x * fwd, o.y + side_v.y * lat + fwd_v.y * fwd)

        for n, (lat, stack) in enumerate(spec["sides"]):
            x, y = at(lat, 0.0)
            z = floor
            for item in stack:
                kind = item[0]
                if kind == "bale":
                    boxes = _bale(d, zone, x, y, floor, across=along_x)
                    z = boxes[-1].maxs.z
                    continue
                if kind == "cart":
                    cx, cy = at(lat, 8.0)
                    d.put(zone, "zmf_prop_hand_cart", cx, cy, floor, 0.0 if along_x else 90.0, check=False, lane=False)
                    continue
                if kind == "oranges":
                    for i, (dx, dy) in enumerate(((-5, -4), (5, 3), (0, 6), (-3, 1), (6, -5))):
                        d.put(zone, ORANGE, x + dx, y + dy, z, i * 70.0, check=False, lane=False)
                    continue
                if kind in ("on_bale", "on_crate", "far"):
                    # On the bale or crate at this spot, *dl* along the wall
                    # and *df* out of it; "far" is on the floor *dl* out.
                    base = {"on_bale": BALE[2], "on_crate": _CRATE_TOP, "far": 0.0}[kind]
                    model, dl = item[1], item[2]
                    df = item[3] if len(item) > 3 else 0.0
                    px, py = at(lat, dl) if kind == "far" else at(lat + dl, df)
                    d.put(zone, model, px, py, floor + base, yaw0 + n * 37.0, check=False, lane=False)
                    continue
                model = kind
                d.put(zone, model, x, y, z, yaw0 + n * 23.0, check=False, lane=False)
                z += MODEL_BOX[model][1][2] - MODEL_BOX[model][0][2]
        if spec.get("sign"):
            # On the wall behind the machine (a perk stands 24 off it), over
            # the machine's top.
            (ax, ay), (bx, by) = at(-52.0, -24.0), at(52.0, -22.0)
            board = Bounds.between((min(ax, bx), min(ay, by), floor + 112.0),
                                   (max(ax, bx), max(ay, by), floor + 142.0))
            bp.add_block(board, cm._PANEL, reachable=False, id=f"{machine.id}_sign", note="sign board")
            tx, ty = at(0.0, -22.0)
            brush_text(bp, spec["sign"], at=Point(tx, ty, floor + 127.0), facing=machine.facing, cell=1.8,
                       plate=False, ident=f"{machine.id}_sign_text")
        if spec["stall"]:
            (ax, ay), (bx, by) = at(-STALL_HALF, -24.0), at(STALL_HALF, STALL_DEPTH)
            roof = Bounds.between((min(ax, bx), min(ay, by), floor + STALL_ROOF_Z),
                                  (max(ax, bx), max(ay, by), floor + STALL_ROOF_Z + 6.0))
            bp.add_block(roof, cm._PLANKS, reachable=False, id=f"{machine.id}_stall_roof",
                         note="perk stall roof")
            for i, lat in enumerate((-STALL_HALF + 5.0, STALL_HALF - 5.0)):
                px, py = at(lat, STALL_DEPTH - 5.0)
                bp.add_block(Bounds.between((px - 4, py - 4, floor), (px + 4, py + 4, floor + STALL_ROOF_Z)),
                             cm._BEAM, reachable=False, id=f"{machine.id}_stall_post_{i}",
                             note="perk stall post")


#: The x of the farm's name board on the farmyard's north boards.
FARM_SIGN_X = -380.0


def _board_wall_dressing(bp: Blueprint, d: "Dresser", fy, plan: "cm.CornMazePlan") -> None:
    """The farmyard's two board fences (north, the farmhouse side; south,
    the barn side), dressed so they read as a farm's boards: loose weathered
    planks, feed sacks, a dropped hammer and tall grass along the foot, and
    the farm's painted sign on the north one.  (Not the dry grass: its
    material's tussock images were missing from the tools tree, and a
    link stopped on them.  The dead ivy would need a
    pitch to lie on the boards, and a placed prop carries only a yaw.)"""
    fi, fz = fy.interior, fy.floor_z
    rng = random.Random("harvest-moon-boards")
    # The farm's painted sign on the north boards, west of the farmhouse
    # door: a board with the HARVEST MOON FARM notice on it
    # (corn_maze_script.NOTICES["farm_sign"]).  It was the kit's
    # p7_sign_aerofarm_01, which reads as a different farm
    # (P14: a named place is labelled as itself).
    x0, x1 = FARM_SIGN_X - 90.0, FARM_SIGN_X + 90.0
    board = Bounds.between((x0, fi.maxs.y - 4.0, fz + 40.0), (x1, fi.maxs.y, fz + 100.0))
    bp.add_block(board, cm._PANEL, reachable=False, id="farm_sign", note="sign board")
    for n, (text, dz) in enumerate((("HARVEST MOON", 44.0), ("FARM", 22.0))):
        brush_text(bp, text, at=Point(FARM_SIGN_X, board.mins.y, fz + 40.0 + dz), facing=Facing.SOUTH,
                   cell=2.2, plate=False, ident=f"farm_sign_text_{n}")
    d.keepouts.append(board.grown_on(Axis.X, 20.0).grown_on(Axis.Y, 48.0).grown_on(Axis.Z, 40.0))
    for side, y_face, sign in ((Side.NORTH, fi.maxs.y, -1), (Side.SOUTH, fi.mins.y, 1)):
        x = fi.mins.x + 60.0
        k = 0
        while x < fi.maxs.x - 60.0:
            k += 1
            m = ("p7_plank_wood_weathered_02", "p7_sandbag_01", "p7_foliage_grass_tall_cluster_sml",
                 "p7_farm_tools_hammer", "p7_foliage_grass_tall_cluster_sml")[k % 5]
            # Set off the boards by the turned footprint, so nothing is drawn
            # through them (four were, 2.4 to 7.3 units, at a flat 24).
            px, yaw = x + rng.uniform(-20, 20), rng.uniform(0, 360)
            _, _, ey0, ey1 = _extent(m, 1.0, yaw)
            off = max(24.0, GRASS_WALL_GAP + (-ey0 if sign > 0 else ey1))
            d.put("farmyard", m, px, y_face + sign * off, fz, yaw, solid=False)
            x += 110.0 + rng.uniform(-20, 20)


def _yaw_facing(ox: int, oy: int) -> float:
    """The yaw that turns a kit prop's face (-y at yaw 0) towards ``(ox, oy)``."""
    return {(0, -1): 0.0, (1, 0): 90.0, (0, 1): 180.0, (-1, 0): 270.0}[(ox, oy)]


def _landmarks(bp: Blueprint, d: "Dresser", plan: "cm.CornMazePlan", rooms) -> list[Bounds]:
    """Two things tall enough to see over the corn from anywhere in the maze,
    each in its clearing (:data:`zmforge.recipes.corn_maze.CLEARINGS`): the
    farm's water tower in the entry (tank top at 492) and an old windmill in
    the west rows (blades to 600).  Brushwork, never climbable, each lit.
    Returns their boxes (the dressing keeps clear of them)."""
    x0, y0 = plan.maze_origin
    p = plan.maze_pitch
    out: list[Bounds] = []

    def block(ident: str, box: Bounds, mat) -> None:
        bp.add_block(box, mat, reachable=False, id=ident, note="landmark")
        out.append(box)

    ci, cj = cm.CLEARINGS["water_tower"]
    cx, cy = x0 + (ci + 1) * p, y0 + (cj + 1) * p
    z = rooms[cm.room_of((ci, cj))].floor_z
    for i, (dx, dy) in enumerate(((-64, -64), (64, -64), (-64, 64), (64, 64))):
        block(f"water_tower_leg_{i}", Bounds.between((cx + dx - 6, cy + dy - 6, z), (cx + dx + 6, cy + dy + 6, z + 340)),
              cm._BEAM)
    for i, (ax, ay) in enumerate(((0, -1), (0, 1))):
        yy = cy + ay * 64
        block(f"water_tower_brace_{i}", Bounds.between((cx - 58, yy - 2, z + 170), (cx + 58, yy + 2, z + 180)), cm._BEAM)
    block("water_tower_deck", Bounds.between((cx - 84, cy - 84, z + 340), (cx + 84, cy + 84, z + 352)), cm._PLANKS)
    block("water_tower_tank", Bounds.between((cx - 72, cy - 72, z + 352), (cx + 72, cy + 72, z + 480)), cm._PLANKS)
    block("water_tower_roof", Bounds.between((cx - 80, cy - 80, z + 480), (cx + 80, cy + 80, z + 492)), cm._ROOF)
    _lamp(bp, cx, cy, z + 300.0, cm.room_of((ci, cj)), "water_tower_lantern", radius=520.0)

    ci, cj = cm.CLEARINGS["windmill"]
    cx, cy = x0 + (ci + 1) * p, y0 + (cj + 1) * p
    key = cm.room_of((ci, cj))
    z = rooms[key].floor_z
    for i, (dx, dy) in enumerate(((-40, -40), (40, -40), (-40, 40), (40, 40))):
        block(f"windmill_leg_{i}", Bounds.between((cx + dx - 5, cy + dy - 5, z), (cx + dx + 5, cy + dy + 5, z + 440)),
              cm._IRON)
    block("windmill_head", Bounds.between((cx - 48, cy - 48, z + 440), (cx + 48, cy + 48, z + 480)), cm._IRON)
    # The sails face east, over the maze to the heart: a cross of four.
    hx = cx + 52
    block("windmill_sail_0", Bounds.between((hx, cy - 12, z + 470), (hx + 6, cy + 12, z + 600)), cm._PLANKS)
    block("windmill_sail_1", Bounds.between((hx, cy - 12, z + 330), (hx + 6, cy + 12, z + 450)), cm._PLANKS)
    block("windmill_sail_2", Bounds.between((hx, cy - 140, z + 450), (hx + 6, cy - 12, z + 470)), cm._PLANKS)
    block("windmill_sail_3", Bounds.between((hx, cy + 12, z + 450), (hx + 6, cy + 140, z + 470)), cm._PLANKS)
    block("windmill_hub", Bounds.between((hx, cy - 12, z + 450), (hx + 6, cy + 12, z + 470)), cm._IRON)
    _lamp(bp, cx, cy, z + 300.0, key, "windmill_lantern", radius=520.0)
    d.keepouts += [b.grown(24.0) for b in out]
    return out


#: Dead-end scene kinds handed to the vignette library (the harvest pile,
#: picnic, gore and tipped cart): it has bigger, varied stories for them.
#: The scarecrow (1) and the lantern on a bale (2) stay here.
VIGNETTE_DEAD_END_KINDS = (0, 3, 4, 5)


def _dead_end_scene(bp: Blueprint, d: "Dresser", plan: "cm.CornMazePlan", rooms, passages, cell,
                    n: int, rng: random.Random) -> None:
    """A little scene at the closed end of dead end *cell*: what somebody
    left, or what was left of them.  Six kinds in turn; every other one has
    a lit jack-o'-lantern or a lamp, so a dead end is a pool of warm light."""
    key = cm.room_of(cell)
    z = rooms[key].floor_z
    (nb,) = cm.maze_graph(passages)[cell]
    ox, oy = nb[0] - cell[0], nb[1] - cell[1]
    px, py = -oy, ox
    cx, cy = plan.cell_centre(cell)
    face = _yaw_facing(ox, oy)

    def at(u: float, v: float) -> tuple[float, float]:
        return cx + ox * u + px * v, cy + oy * u + py * v

    kind = n % 6
    lit = None
    if kind in VIGNETTE_DEAD_END_KINDS:
        # The shared vignette library dresses this one instead, after the
        # corn bands (recipes/corn_maze_vignettes.py).
        bp.vignette_dead_ends = [*getattr(bp, "vignette_dead_ends", []), cell]  # type: ignore[attr-defined]
        return
    if kind == 0:  # a harvest pile
        for i, (u, v, sc) in enumerate(((-20, 0, 1.2), (-6, -22, 1.05), (-8, 22, 1.1), (6, 6, 0.95),
                                        (-30, -34, 1.0), (-28, 36, 1.15))):
            _pumpkin(d, key, *at(u, v), z, face + i * 40.0, sc)
        x, y = at(24, -30)
        if _pumpkin(d, key, x, y, z, face, JACK_SCALE, JACK):
            lit = (x, y)
        _basket_of_oranges(d, key, *at(18, 34), z, face + 20.0, n)
    elif kind == 1:  # a scarecrow nobody put a head on, so somebody used a pumpkin
        x, y = at(-26, 0)
        if d.free(x, y, z, 16.0):
            # Short arms: it stands across a dead end's corridor (N5: at 36
            # a side the arms pinched a corridor to 58 units).
            pole = _scarecrow_body(bp, d, key, x, y, z, face + 90.0, f"{key}_scene_{n}_scarecrow", arm=22.0)
            d.keepouts.append(pole.grown(10.0))
            d.put(key, PUMPKIN, x, y, z + POLE_TOP, face, 1.2, check=False)
        for i, v in enumerate((-40, 40)):
            _pumpkin(d, key, *at(10, v), z, face + i * 70.0, 1.0 + 0.1 * i)
        d.put(key, "p7_gib_chunk_bone_03", *at(20, 12), z, face + 30.0)
    elif kind == 2:  # a lost lantern on a bale
        x, y = at(-26, 0)
        bb = _bale(d, key, x, y, z, across=(ox != 0), yaw=face)
        d.keepouts += [b.grown(6.0) for b in bb]
        d.put(key, LAMP, x, y, bb[-1].maxs.z, face, check=False)
        # Its light hangs just off the bale on the path side, not over the
        # bale: the bale's top is a camping top, and Z46's clip cap over it
        # (verify.camping, 48 tall) buried a light hung there (Z11).
        lit = at(8, 0)
        d.put(key, "p7_gib_chunk_bone_01", *at(24, 26), z, rng.uniform(0, 360))
        d.put(key, "p7_tools_shovel", *at(20, -34), z, face + 70.0)
    elif kind == 3:  # a picnic, abandoned
        x, y = at(-24, -20)
        if d.put(key, CRATE, x, y, z, face + 10.0):
            top = z + MODEL_BOX[CRATE][1][2]
            d.put(key, JAR, x - 4, y + 2, top, 0.0, check=False)
            d.put(key, "p7_decanter_glass_bottle", x + 5, y - 3, top, 40.0, check=False)
        _basket_of_oranges(d, key, *at(-20, 28), z, face, n + 1)
        _pumpkin(d, key, *at(18, 0), z, face + 15.0, 1.1)
    elif kind == 4:  # what the corn left
        for i, (m, u, v) in enumerate((("p7_gib_chunk_bone_01", -20, -18), ("p7_gib_chunk_bone_03", -6, 20),
                                       ("p7_gib_chunk_meat_01", 14, -6), ("p7_gib_chunk_flesh_01", -30, 30))):
            d.put(key, m, *at(u, v), z, rng.uniform(0, 360))
        x, y = at(-30, -38)
        if _pumpkin(d, key, x, y, z, face, JACK_SCALE, JACK):
            lit = (x, y)
    else:  # a hand cart of pumpkins, tipped into the corn
        x, y = at(-24, 0)
        if d.put(key, "p7_wheel_barrow_street_vendor", x, y, z, face + 90.0):
            top = z + MODEL_BOX["p7_wheel_barrow_street_vendor"][1][2]
            for i, v in enumerate((-14, 4, 18)):
                xx, yy = at(-24, v)
                _pumpkin(d, key, xx, yy, top, i * 50.0, 0.9, check=False)
        _pumpkin(d, key, *at(18, 20), z, face + 60.0, 1.0)
        _pumpkin(d, key, *at(26, -12), z, face + 120.0, 0.95)
    if lit is not None:
        _lamp(bp, lit[0], lit[1], z + 48.0, key, f"{key}_deadend_{n}", radius=280.0)


#: The low weeds scattered on the maze floor, and the scales they are drawn
#: at: all under the step height (Z48 steps over them), all walk-through.
FLOOR_WEEDS = (("p7_foliage_weed_cluster_lrg", 2.0), ("p7_foliage_weed_cluster_med", 2.2),
               ("p7_foliage_weed_cluster_sml_a", 2.0), ("p7_foliage_weed_cluster_sml_b", 2.4))


#: How far a path lantern's light reaches (the trail lanterns' 300).
PATH_LANTERN_RADIUS = 300.0
#: How many path lanterns the last build placed (:func:`_path_lantern`).
PATH_LANTERNS = [0]


def _path_lantern(d: "Dresser", plan: "cm.CornMazePlan", rooms):
    """The maze's path-light fixture for :func:`zmforge.blueprint.autolamp.light_paths`:
    a hurricane lantern on the ground just in front of the corn band on one
    side of the path (the trail lanterns' spot), its light 60 over it."""
    off = plan.maze_pitch / 2.0 - plan.wall / 2.0 - BAND_DEPTH - 10.0

    def fixture(point: Point, direction: tuple[float, float]) -> Point | None:
        key = cm.room_of(plan.cell_of(point.x, point.y))
        if key is None:
            return None
        z = rooms[key].floor_z
        px, py = -direction[1], direction[0]
        # A solid lantern first; else a walk-through one (scaled, so no
        # collmap) under the corn band's rules, which let it stand where
        # a zombie rises, as the corn does.
        for scale, band in ((1.0, False), (0.98, True)):
            for side in (1, -1):
                x, y = point.x + side * px * off, point.y + side * py * off
                if d.put(key, LAMP, x, y, z, (x * 7 + y * 3) % 360.0, scale, band=band):
                    return Point(x, y, z + 60.0)
        return None

    return fixture


def _maze_floor(bp: Blueprint, d: "Dresser", plan: "cm.CornMazePlan", rooms, passages, spots,
                rng: random.Random) -> None:
    """The maze floor: weeds in every cell, a lantern every few cells along
    the way to the heart (the lanterns are the farm's trail markers, the
    notice at the gate says so), and a pumpkin against the corn now and then."""
    graph = cm.maze_graph(passages)
    path = spots["path"]
    on_path = set(path)
    special = set(spots["dead_ends"]) | set(spots["clearing"])
    half = plan.maze_pitch / 2.0
    for n, cell in enumerate(cm.maze_cells_all(plan.maze_size)):
        key = cm.room_of(cell)
        z = rooms[key].floor_z
        cx, cy = plan.cell_centre(cell)
        if cell in spots["ears"]:
            continue  # nothing to hide a golden ear in
        for k in range(3):
            m, sc = FLOOR_WEEDS[(n + k) % len(FLOOR_WEEDS)]
            d.put(key, m, cx + rng.uniform(-half + 60, half - 60), cy + rng.uniform(-half + 60, half - 60), z,
                  rng.uniform(0, 360), sc, solid=False)
        if cell in special:
            continue
        closed = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if (cell[0] + dx, cell[1] + dy) not in graph[cell]]
        if not closed:
            continue
        sx, sy = closed[n % len(closed)]
        # Just in front of the corn band on a closed side, off the path's middle.
        reach = half - plan.wall / 2.0 - BAND_DEPTH - 10.0
        along = rng.uniform(-60, 60)
        x, y = cx + sx * reach + (-sy) * along, cy + sy * reach + sx * along
        if cell in on_path and path.index(cell) % 4 == 2:
            if d.put(key, LAMP, x, y, z, rng.uniform(0, 360)):
                _lamp(bp, x, y, z + 60.0, key, f"{key}_trail_{path.index(cell)}", radius=300.0)
        elif n % 3 == 0:
            _pumpkin(d, key, x, y, z, rng.uniform(0, 360), 0.9 + 0.1 * (n % 4))


#: The field beyond the map's corn walls: tall stalks (walk-through, so any
#: scale; 3.2-3.8 is 300-365 units, over the 200-unit walls) in a band next
#: to every outdoor room, so the corn seen over any wall goes on past it,
#: and a line of trees further out on the skyline (:data:`OUTSKIRT_TREES`).
OUTSKIRT_TILE = 144.0
OUTSKIRT_CORN = 450.0
OUTSKIRT_REACH = 900.0
#: The skyline trees, if the link has proved them (``corn_maze_assets``:
#: the albizia's sway materials are declared nowhere); ``()`` for none.
OUTSKIRT_TREES: tuple[str, ...] = ("p7_foliage_tree_albizia_tall_full",)


def _outskirts(bp: Blueprint, plan: "cm.CornMazePlan", rooms) -> dict[str, int]:
    """The ground, corn and trees outside the playable rooms.

    A grid of :data:`OUTSKIRT_TILE` tiles over everything within
    :data:`OUTSKIRT_REACH` of an outdoor room; a tile touching any room or
    window yard is left alone.  Each free tile gets a dirt floor slab
    (never reachable: every room is walled in 200-unit corn), and tall corn
    if it is within :data:`OUTSKIRT_CORN` of an outdoor room, else a tree
    on every other tile.  Returns the counts placed."""
    from ..blueprint.elements import Yard

    outdoor = [r for r in rooms.values() if not r.roofed]
    taken = [r.outer.grown(8.0) for r in rooms.values()] + [y.outer.grown(8.0) for y in bp.elements(Yard)]
    xs = [b.mins.x for b in taken] + [b.maxs.x for b in taken]
    ys = [b.mins.y for b in taken] + [b.maxs.y for b in taken]
    t = OUTSKIRT_TILE
    x0, y0 = min(xs) - OUTSKIRT_REACH, min(ys) - OUTSKIRT_REACH
    nx, ny = int((max(xs) - min(xs) + 2 * OUTSKIRT_REACH) // t) + 1, int((max(ys) - min(ys) + 2 * OUTSKIRT_REACH) // t) + 1

    def gap(box: Bounds, room) -> float:
        o = room.outer
        dx = max(o.mins.x - box.maxs.x, box.mins.x - o.maxs.x, 0.0)
        dy = max(o.mins.y - box.maxs.y, box.mins.y - o.maxs.y, 0.0)
        return math.hypot(dx, dy)

    rng = random.Random("harvest-moon-outskirts")
    free: dict[tuple[int, int], float] = {}
    for j in range(ny):
        for i in range(nx):
            tile = Bounds.between((x0 + i * t, y0 + j * t, -24.0), (x0 + (i + 1) * t, y0 + (j + 1) * t, 0.0))
            if any(tile.overlaps(b) for b in taken):
                continue
            near = min(gap(tile, r) for r in outdoor)
            if near <= OUTSKIRT_REACH:
                free[(i, j)] = near
    free_rows: dict[int, list[int]] = {}
    for i, j in sorted(free, key=lambda c: (c[1], c[0])):
        free_rows.setdefault(j, []).append(i)
    items = []
    tree_tiles: list[tuple[int, int]] = []
    corn = trees = 0
    for (i, j), near in sorted(free.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        # Only where the ground runs on all round, so every footprint is on it.
        if not all((i + di, j + dj) in free for di in (-1, 0, 1) for dj in (-1, 0, 1)):
            continue
        cx, cy = x0 + (i + 0.5) * t, y0 + (j + 0.5) * t
        if near <= OUTSKIRT_CORN:
            for a in range(2):
                for b in range(2):
                    k = corn
                    corn += 1
                    model = STALK if k % 3 else STALK_THIN
                    x = cx + (a - 0.5) * t / 2 + rng.uniform(-12, 12)
                    y = cy + (b - 0.5) * t / 2 + rng.uniform(-12, 12)
                    items.append((model, Point(x, y, 0.0), rng.uniform(0, 360), rng.uniform(3.2, 3.8), False))
        elif (OUTSKIRT_TREES and i % 3 == 0 and j % 3 == 0
              # The tree's box is its canopy, 570 across: the ground runs
              # on under all of it (Z44).
              and all((i + di, j + dj) in free for di in range(-2, 3) for dj in range(-2, 3))):
            model = OUTSKIRT_TREES[(i * 7 + j) % len(OUTSKIRT_TREES)]
            items.append((model, Point(cx + rng.uniform(-8, 8), cy + rng.uniform(-8, 8), -MODEL_BOX[model][0][2]),
                          rng.uniform(0, 360), 1.0, False))
            trees += 1
            tree_tiles.append((i, j))
    # The ground: as few slabs as cover the free tiles, each the widest run
    # in a row carried down every row that has it free (a tree's canopy is
    # four rows deep, and a prop should stand mostly on one surface, Z44).
    n = 0
    used: set[tuple[int, int]] = set()
    # Each tree first gets its own slab, the 3 x 3 tiles round it, so at least
    # half its canopy box is over one surface however it turns (Z44: laid by
    # the greedy runs below, a tree's ground was split over two or three
    # slabs and none held 50%; v2).  Trees are 3 tiles apart.
    for i, j in tree_tiles:
        bp.add_block(Bounds.between((x0 + (i - 1) * t, y0 + (j - 1) * t, -24.0), (x0 + (i + 2) * t, y0 + (j + 2) * t, 0.0)),
                     cm._DIRT, reachable=False, id=f"outskirts_ground_{n}", note="the field beyond the corn")
        used.update((i + di, j + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1))
        n += 1
    for (i, j) in sorted(free, key=lambda c: (c[1], c[0])):
        if (i, j) in used:
            continue
        i1 = i
        while (i1 + 1, j) in free and (i1 + 1, j) not in used:
            i1 += 1
        j1 = j
        while all((c, j1 + 1) in free and (c, j1 + 1) not in used for c in range(i, i1 + 1)):
            j1 += 1
        used.update((c, r) for c in range(i, i1 + 1) for r in range(j, j1 + 1))
        bp.add_block(Bounds.between((x0 + i * t, y0 + j * t, -24.0), (x0 + (i1 + 1) * t, y0 + (j1 + 1) * t, 0.0)),
                     cm._DIRT, reachable=False, id=f"outskirts_ground_{n}", note="the field beyond the corn")
        n += 1
    for k in range(0, len(items), 40):
        bp.place_props(items[k:k + 40], id=f"outskirts_{k // 40}")
    return {"corn": corn, "trees": trees, "ground": n}


#: Grass over the outdoor ground (grass patches
#: everywhere but the walkways).  All walk-through and cheap: the tall ones
#: (34-61 units) only where nobody walks, against walls, fences and the
#: corn; the low ones (the small cluster at 0.42, 14 units, under the 16-unit
#: step, so Z48 steps over it) anywhere off a path; flat leaf litter down the
#: trampled middle of a maze corridor.  ``(model, scale range, tris)``.
GRASS_TALL = (("p7_foliage_grass_tall_cluster_sml", (0.9, 1.3), 71),) * 5 + (
    ("p7_foliage_grass_tall_cluster_med", (0.7, 1.0), 356),
    ("p7_foliage_grass_tall_single_sml", (0.8, 1.1), 330))
GRASS_LOW = (("p7_foliage_grass_tall_cluster_sml", (0.36, 0.42), 71),) * 5 + (
    ("p7_foliage_weed_cluster_sml_b", (2.0, 2.4), 14),)
GRASS_LITTER = (("p7_3arc_park_leaves_grp_2", (0.9, 1.3), 35),)
#: The grid the grass is thrown on, and how far a walkway is kept bare.
GRASS_STEP = 52.0
WALK_HALF = 64.0


def _seg_dist(x: float, y: float, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def _box_dist(x: float, y: float, b: Bounds) -> float:
    return math.hypot(max(b.mins.x - x, 0.0, x - b.maxs.x), max(b.mins.y - y, 0.0, y - b.maxs.y))


#: How far a grass clump's footprint keeps off a wall face, and how far off
#: a quest spot (an ear, a notice, a prize pumpkin, a trigger).
GRASS_WALL_GAP = 2.0
QUEST_CLEAR = 48.0


def _grass_reach(model: str, scale: float) -> float:
    """How far *model*'s plan footprint reaches from its origin at any yaw:
    the farthest corner of its :data:`MODEL_BOX`, scaled."""
    (x0, y0, _), (x1, y1, _) = MODEL_BOX[model]
    return scale * max(math.hypot(a, b) for a in (x0, x1) for b in (y0, y1))


def _wall_edge(x: float, y: float, inner: Bounds, walls: Sequence[Bounds]) -> tuple[float, float, float]:
    """``(distance, ux, uy)``: how far ``(x, y)`` is from the nearest wall
    face (the room's own, or any of *walls*), and the unit step away from it."""
    best = (x - inner.mins.x, 1.0, 0.0)
    for d, ux, uy in ((inner.maxs.x - x, -1.0, 0.0), (y - inner.mins.y, 0.0, 1.0),
                      (inner.maxs.y - y, 0.0, -1.0)):
        if d < best[0]:
            best = (d, ux, uy)
    for w in walls:
        dx = max(w.mins.x - x, 0.0, x - w.maxs.x)
        dy = max(w.mins.y - y, 0.0, y - w.maxs.y)
        d = math.hypot(dx, dy)
        if d >= best[0]:
            continue
        if d > 0.0:
            sx = (x - min(max(x, w.mins.x), w.maxs.x)) / d
            sy = (y - min(max(y, w.mins.y), w.maxs.y)) / d
            best = (d, sx, sy)
        else:
            # Inside the wall: out through the nearest side.
            out = min((x - w.mins.x, -1.0, 0.0), (w.maxs.x - x, 1.0, 0.0),
                      (y - w.mins.y, 0.0, -1.0), (w.maxs.y - y, 0.0, 1.0))
            best = (-out[0], out[1], out[2])
    return best


def _grass_fits(model: str, scale: float, x: float, y: float, edge: float,
                quest: Sequence[tuple[float, float]]) -> bool:
    """Whether a clump at ``(x, y)``, *edge* from the nearest wall face, stays
    off the walls and every quest spot."""
    r = _grass_reach(model, scale)
    if r + GRASS_WALL_GAP > edge:
        return False
    return all(math.hypot(x - qx, y - qy) >= QUEST_CLEAR + r for qx, qy in quest)


#: Grass grows in clumps, not as a lawn (tufts spread
#: evenly over every floor).  Clump centres are thrown on a jittered
#: :data:`CLUMP_STEP` grid and kept by where they fall: at a wall's foot
#: (the corn, the board fences), at the edge of a walkway or the hayride
#: lane, rarely out in the open, and in a maze corridor's trampled middle
#: only as a little leaf litter.  Each clump is a few tufts within
#: :data:`CLUMP_RADIUS` of its centre.
CLUMP_STEP = 80.0
CLUMP_RADIUS = 28.0
#: ``where -> (chance a centre is kept, (fewest, most) tufts)``.
CLUMP_KIND = {"foot": (0.6, (3, 7)), "edge": (0.5, (3, 5)), "open": (0.05, (1, 3)),
              "mazefoot": (0.3, (3, 6)), "middle": (0.06, (1, 2))}
#: In a maze corridor, the band of ground (distance off the corn wall's
#: face) that counts as the corn's foot: the front of the stalk band, where
#: the grass shows; under the stalks it is hidden.
MAZE_FOOT = (48.0, 100.0)
#: Grass clumps would be the patch's top model at 0.42, padding the totals
#: with grass while the patch field reads as mostly empty dark dirt, so
#: each kept-centre chance scaled down per room, the props it
#: frees spent on pumpkins along the patch's rows.
CLUMP_ROOM_SCALE = {"patch": 0.5, "farmyard": 0.8}
#: How far past a walkway's or the lane's bare half a clump still counts as
#: growing along its edge.
PATH_EDGE = 44.0


def _grass(d: "Dresser", plan: "cm.CornMazePlan", rooms, maze_walls, spots, walkways) -> dict[str, int]:
    """Grass clumps over every outdoor room's ground.

    Clump centres on a jittered :data:`CLUMP_STEP` grid, kept or dropped by
    where they fall (:data:`CLUMP_KIND`): the foot of a wall, the edge of a
    walkway or the hayride lane, the open ground, or a maze corridor's
    middle.  Each kept centre grows a few tufts around it; the distance of
    each tuft to the nearest corn picks what it is: tall grass within reach
    of the corn, low grass further out, leaf litter down the middle of a
    maze corridor.  Nothing on *walkways* (``room key -> [(a, b), ...]``
    segments kept :data:`WALK_HALF` bare), the hayride lane, a doorway's
    approach, an interactive or a spawn (the dresser's own refusals), or a
    golden ear.  Every tuft keeps its whole footprint, turned any way
    (:func:`_grass_reach`), :data:`GRASS_WALL_GAP` off the room's walls and
    the maze's corn walls (a clump otherwise draws through a wall brush), and
    :data:`QUEST_CLEAR` off every quest
    spot (:func:`.corn_maze_script.quest_points`, so no golden ear ends up
    under a clump).  Where the chosen tuft does not fit,
    the smallest tall cluster at its smallest size is tried instead.
    Returns ``{"clumps": tufts placed, "patches": clumps, "tris": t}``."""
    from .corn_maze_script import quest_points

    rng = random.Random("harvest-moon-grass")
    quest = quest_points(plan, rooms)
    route = d.route
    n = tris = patches = 0
    for key in ("farmyard", "patch", "heart", *cm.MAZE_ROOMS):
        room = rooms[key]
        inner, z = room.interior, room.floor_z
        walls = maze_walls.get(key, [])
        maze = key in cm.MAZE_ROOMS
        paths = walkways.get(key, [])
        lane = key in ("farmyard", "patch")

        def edge_at(x: float, y: float) -> float:
            return min(x - inner.mins.x, inner.maxs.x - x, y - inner.mins.y, inner.maxs.y - y,
                       *(_box_dist(x, y, w) for w in walls))

        def path_at(x: float, y: float) -> float:
            """How far past the nearest walkway's or the lane's bare edge."""
            far = [_seg_dist(x, y, a, b) - WALK_HALF for a, b in paths]
            if lane:
                far.append(cm.distance_to_route(x, y, route) - cm.HAYRIDE_LANE_HALF)
            return min(far, default=1e9)

        nx = int((inner.maxs.x - inner.mins.x) // CLUMP_STEP)
        ny = int((inner.maxs.y - inner.mins.y) // CLUMP_STEP)
        for i in range(nx):
            for j in range(ny):
                cx = inner.mins.x + (i + 0.5) * CLUMP_STEP + rng.uniform(-30, 30)
                cy = inner.mins.y + (j + 0.5) * CLUMP_STEP + rng.uniform(-30, 30)
                edge, far = edge_at(cx, cy), path_at(cx, cy)
                if far < 0.0:
                    continue
                if maze and edge < MAZE_FOOT[0]:
                    continue
                if edge < (MAZE_FOOT[1] if maze else 110.0):
                    kind = "mazefoot" if maze else "foot"
                elif maze:
                    kind = "middle"
                elif far < PATH_EDGE:
                    kind = "edge"
                else:
                    kind = "open"
                chance, (lo, hi) = CLUMP_KIND[kind]
                chance *= CLUMP_ROOM_SCALE.get(key, 1.0)
                if rng.random() > chance:
                    continue
                grew = 0
                for _ in range(rng.randint(lo, hi)):
                    r, a = CLUMP_RADIUS * math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
                    x, y = cx + r * math.cos(a), cy + r * math.sin(a)
                    edge = edge_at(x, y)
                    if path_at(x, y) < 0.0:
                        continue
                    if kind == "middle":
                        pool = GRASS_LITTER
                    elif edge < (64.0 if maze else 110.0):
                        pool = GRASS_TALL
                    else:
                        pool = GRASS_LOW
                    model, (s0, s1), t = pool[rng.randrange(len(pool))]
                    scale, yaw = rng.uniform(s0, s1), rng.uniform(0, 360)
                    if not _grass_fits(model, scale, x, y, edge, quest):
                        # Too big for the spot: the pool's first model at its
                        # smallest; else the low cluster, stepped out from the
                        # nearest wall by what it lacks (it is under the 16-unit
                        # step, so moving it into a path closes nothing, Z48).
                        model, (scale, _), t = pool[0]
                        if not _grass_fits(model, scale, x, y, edge, quest):
                            model, (scale, _), t = GRASS_LOW[0]
                            for _ in range(2):
                                near, ux, uy = _wall_edge(x, y, inner, walls)
                                lack = _grass_reach(model, scale) + GRASS_WALL_GAP - near
                                if lack <= 0.0:
                                    break
                                x, y = x + ux * (lack + 0.5), y + uy * (lack + 0.5)
                            if (path_at(x, y) < 0.0
                                    or not _grass_fits(model, scale, x, y, _wall_edge(x, y, inner, walls)[0], quest)):
                                continue
                    if d.put(key, model, x, y, z, yaw, scale, solid=False):
                        n += 1
                        grew += 1
                        tris += t
                patches += grew > 0
    return {"clumps": n, "patches": patches, "tris": tris}


#: A wall buy's keep-clear for the dressing: :data:`WALLBUY_CHALK` either
#: side of it along the wall, the whole way out to :data:`WALLBUY_APRON`
#: (the chalk and the spot a player reads it from), and the full apron width
#: only beyond the corn band.  A 260-square box round it used to leave 260
#: units of bare wall at every wall buy (the farmyard's east corn); the blueprint's own interactive keep-clear still holds.
#: 44 rather than 64 (a wider bare wall either side
#: of the heart's wall buy reads as a slab); the chalk is about 60 long.
WALLBUY_CHALK = 44.0
WALLBUY_APRON = 130.0


def _wallbuy_keepouts(p: Point, facing: Facing) -> list[Bounds]:
    step = facing.step
    z0, z1 = p.z - 16.0, p.z + 120.0

    def box(along: float, near: float, far: float) -> Bounds:
        if step.x:
            xs = sorted((p.x + step.x * near, p.x + step.x * far))
            return Bounds.between((xs[0], p.y - along, z0), (xs[1], p.y + along, z1))
        ys = sorted((p.y + step.y * near, p.y + step.y * far))
        return Bounds.between((p.x - along, ys[0], z0), (p.x + along, ys[1], z1))

    return [box(WALLBUY_CHALK, -8.0, WALLBUY_APRON),
            box(WALLBUY_APRON, BAND_DEPTH + 4.0, WALLBUY_APRON)]


#: The sheds a wall buy hangs in (placement.wallbuy.buy_shed), this build:
#: their footprints are keep-outs for the dressing, and a shed standing in a
#: lined face's band (the maze's dead-end hut) is recorded as an opening
#: there, since its walls hide the corn wall behind them.
BUY_SHEDS: list[Bounds] = []
#: A field shed stands this far off the corn wall, so the corn behind it is
#: whole (past the band's 76) and the strip behind it is a player wide (at
#: 84 the heart's was an N5 pinch, 84 wide for 176 units, measured;
#: Scale_Standards: 96).
SHED_STANDOFF = 104.0
#: How deep the dead-end hut is (a wall buy's 96-unit walk-up fits in it).
DEAD_END_SHED_DEPTH = 128.0
#: Along-wall half width and depth of a field shed.
SHED_WIDTH = 176.0
SHED_DEPTH = 120.0


#: How far in front of a buy shed's open side nothing solid stands
#: (:func:`_off_shed_fronts`): the buy's 96-unit walk-up runs out of it.
SHED_FRONT_CLEAR = 160.0


def _off_shed_fronts(x: float, y: float, r: float) -> tuple[float, float]:
    """``(x, y)``, or the nearest spot along x (steps of 40) where something
    *r* across stays out of every buy shed and the :data:`SHED_FRONT_CLEAR`
    in front of it (sheds are open on the side away from their back wall;
    a box grown that far all round is the simple, safe reading)."""
    boxes = [b.grown(SHED_FRONT_CLEAR) for b in BUY_SHEDS]
    for k in range(40):
        dx = 40.0 * ((k + 1) // 2) * (1 if k % 2 else -1)
        px = x + dx
        if not any(b.mins.x - r <= px <= b.maxs.x + r and b.mins.y - r <= y <= b.maxs.y + r for b in boxes):
            return px, y
    return x, y


def _planned_lining(plan: "cm.CornMazePlan", rooms: Mapping[str, object],
                    maze_walls: Mapping[str, list[Bounds]]) -> list[tuple]:
    """``bp.lined_faces`` as the dressing will lay them (:func:`_room_bands`'s
    faces, whole spans), known before any wall buy goes in."""
    every = (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST)
    lined = [("farmyard", (Side.EAST, Side.WEST), []), ("patch", every, []), ("heart", every, [])]
    lined += [(key, every, maze_walls[key]) for key in cm.MAZE_ROOMS]
    out = []
    for key, sides, walls in lined:
        room = rooms[key]
        z = room.floor_z
        for horizontal, face, a0, a1, sign in _band_faces(room, walls, sides):
            out.append((horizontal, face, (a0, a1), sign, z, z + plan.corn_height, BAND_DEPTH))
    return out


def _farmyard_later(plan: "cm.CornMazePlan", fi: Bounds, fz: float) -> list[Bounds]:
    """What the farmyard gets after its wall buy, which the buy keeps clear
    of: the farm sign, the tractor, the hayride stop and its lane, the
    stand."""
    stop_x, stop_y = cm.hayride_route(plan)[0]
    tx, ty = fi.mins.x + 206.0, fi.maxs.y - 150.0
    lane = cm.HAYRIDE_LANE_HALF
    return [Bounds.between((FARM_SIGN_X - 114.0, fi.maxs.y - 40.0, fz), (FARM_SIGN_X + 114.0, fi.maxs.y, fz + 120.0)),
            Bounds.between((tx - 170.0, ty - 170.0, fz), (tx + 170.0, ty + 170.0, fz + 120.0)),
            Bounds.between((stop_x - 170.0, fi.mins.y, fz), (stop_x + 110.0, stop_y - 130.0, fz + 120.0)),
            Bounds.between((fi.mins.x, stop_y - lane, fz), (fi.maxs.x, stop_y + lane, fz + 120.0)),
            Bounds.between((110.0, 420.0, fz), (650.0, fi.maxs.y, fz + 160.0))]


def _shed_for_buy(bp: Blueprint, plan: "cm.CornMazePlan", ident: str, wall: Point, room,
                  zone_box: Bounds) -> Bounds:
    """A field shed for a wall buy wanted at *wall* (a spot on *room*'s
    corn): its back at least :data:`SHED_STANDOFF` off the room's corn
    walls, so the corn behind it is whole (out in the field if it must be),
    at the place nearest *wall* that is clear of the hayride's lane, every
    interactive's keep, every doorway and window, every spawn and every
    lined face's band."""
    from ..blueprint.elements import Room
    from ..placement.wallbuy import shed_footprint

    route = cm.hayride_route(plan)
    keeps = [z for k in bp.interactive_keeps() for z in k.zones]
    holes = [Bounds.between(b.mins, b.maxs).grown(40.0)
             for r in bp.elements(Room) for b in (getattr(r, "aperture_boxes", ()) or ())]
    spawns = [sp.position for sp in bp.elements(Spawn)]
    bands = []
    for horizontal, face, (s0, s1), sign, floor, top, depth in getattr(bp, "lined_faces", ()):
        n0, n1 = sorted((face, face + sign * depth))
        lo, hi = ((s0, n0), (s1, n1)) if horizontal else ((n0, s0), (n1, s1))
        bands.append(Bounds.between((lo[0], lo[1], floor), (hi[0], hi[1], top)))
    i, z = room.interior, room.floor_z
    sides = ((Facing.SOUTH, True, i.maxs.y, i.mins.x, i.maxs.x), (Facing.NORTH, True, i.mins.y, i.mins.x, i.maxs.x),
             (Facing.WEST, False, i.maxs.x, i.mins.y, i.maxs.y), (Facing.EAST, False, i.mins.x, i.mins.y, i.maxs.y))
    why: dict[str, int] = {}
    best = None
    spots = []
    for facing, horizontal, line, a0, a1, in sides:
        step = facing.step
        reach_out = (i.maxs.y - i.mins.y) if horizontal else (i.maxs.x - i.mins.x)
        a = a0
        while a <= a1:
            x, y = (a, line) if horizontal else (line, a)
            a += 32.0
            out = SHED_STANDOFF
            while out < reach_out - SHED_DEPTH:
                spots.append((facing, Point(x + step.x * out, y + step.y * out, z)))
                out += 32.0
    for facing, back in spots:
            score = math.hypot(back.x - wall.x, back.y - wall.y)
            if best is not None and score >= best[0]:
                continue
            box = shed_footprint(back, facing, SHED_WIDTH, SHED_DEPTH)
            corners = [(cx, cy) for cx in (box.mins.x, box.maxs.x) for cy in (box.mins.y, box.maxs.y)]
            grown = box.grown(8.0)
            if not all(zone_box.holds_flat(cx, cy) for cx, cy in corners) or any(grown.overlaps(b) for b in bands):
                why["room"] = why.get("room", 0) + 1
                continue
            if any(cm.distance_to_route(cx, cy, route) < cm.HAYRIDE_LANE_HALF + 16.0
                   for cx, cy in corners + [(box.centre.x, box.centre.y)]):
                why["lane"] = why.get("lane", 0) + 1
                continue
            if any(box.grown(16.0).overlaps(k) for k in keeps) or any(box.grown(16.0).overlaps(h) for h in holes):
                why["keep/hole"] = why.get("keep/hole", 0) + 1
                continue
            if any(box.grown(64.0).holds_flat(p.x, p.y) for p in spawns):
                why["spawn"] = why.get("spawn", 0) + 1
                continue
            best = (score, back, facing)
    if best is None:
        raise ValueError(f"{ident}: no clear spot for a buy shed in the room by ({wall.x:.0f}, {wall.y:.0f}): {why}")
    _, back, facing = best
    BUY_SHEDS.append(buy_shed(bp, back, facing, width=SHED_WIDTH, depth=SHED_DEPTH, material=cm._PLANKS,
                              ident=ident))
    return BUY_SHEDS[-1]


#: How far behind a machine's origin its keep-out reaches: to the wall it
#: stands against (24 for a perk or the power, 40 for the box or Pack-a-Punch)
#: and a little into it, never through a 24-unit corn wall to the far side.
MACHINE_BACK = 44.0
#: An aperture longer than this along its wall is an open boundary between
#: two maze rooms, not a door or a window (a door is at most a corridor wide).
OPEN_BOUNDARY = 300.0
#: Half the width along the wall that the corn bands keep clear round a
#: machine (a perk under a stall keeps clear of the stall's roof instead).
BAND_CLEAR = {"Machine": 60.0, "MysteryBox": 64.0, "PowerSwitch": 50.0}


def _facing_box(p: Point, facing: Facing, half: float, back: float, front: float) -> Bounds:
    """A box round a machine at *p* facing *facing*: *half* either side along
    its wall, *back* behind it and *front* out in front, 16 under to 120 over."""
    step = facing.step
    z0, z1 = p.z - 16.0, p.z + 120.0
    if step.x:
        xs = sorted((p.x - step.x * back, p.x + step.x * front))
        return Bounds.between((xs[0], p.y - half, z0), (xs[1], p.y + half, z1))
    ys = sorted((p.y - step.y * back, p.y + step.y * front))
    return Bounds.between((p.x - half, ys[0], z0), (p.x + half, ys[1], z1))


def build_all(bp: Blueprint, plan: "cm.CornMazePlan", rooms: Mapping[str, object],
              zones: Mapping[str, object], *, player_slots: int) -> Dresser:
    route = cm.hayride_route(plan)
    fy, pa, fh, ba, he = (rooms[k] for k in ("farmyard", "patch", "farmhouse", "barn", "heart"))
    fz, fi = fy.floor_z, fy.interior
    pz, pi = pa.floor_z, pa.interior
    hz, fhi = fh.floor_z, fh.interior
    bz, bi = ba.floor_z, ba.interior
    tz, hi = he.floor_z, he.interior
    loft_top = bz + plan.loft_height

    # =====================================================================
    # Interactive items first, so the dressing can keep clear of them.
    # =====================================================================
    bp.set_player_start(Point(0.0, 150.0, fz + 16.0), Facing.SOUTH, slots=player_slots)
    # Not at the tractor: a riser at (-300, 330) was 31 units from its
    # notice, so zombies climbed out at the feet of whoever was reading it.
    for i, (x, y) in enumerate(((-450.0, -100.0), (330.0, 60.0), (420.0, -520.0))):
        bp.add_riser(zones["farmyard"], Point(x, y, fz), Facing.NORTH, id=f"farmyard_riser_{i}")
    # The farm stand, against the north corn: hot cider (Quick Revive) and
    # cold cider (Speed Cola).
    bp.place_perk("quick_revive", Point(330.0, fi.maxs.y - 24.0, fz), Facing.SOUTH,
                  id="perk_quick_revive")
    bp.place_perk("speed_cola", Point(520.0, fi.maxs.y - 24.0, fz), Facing.SOUTH,
                  id="perk_speed_cola")
    # The corn this build will line, known before any wall buy goes in: a
    # buy is never chalked on a lined face (placement.wallbuy, Z91), so each buy the layout asks for on the corn goes on the
    # nearest real wall of its zone instead, and every corn wall is filled.
    maze_keys = tuple(cm.MAZE_ROOMS)
    passages = cm.maze_passages(plan.maze_size, plan.maze_seed, plan.maze_loops)
    maze_walls: dict[str, list[Bounds]] = {
        key: cm.maze_boxes(plan, key, rooms[key].interior, rooms[key].floor_z, passages)
        for key in maze_keys}
    bp.lined_faces = _planned_lining(plan, rooms, maze_walls)  # type: ignore[attr-defined]
    bp.lined_openings = []  # type: ignore[attr-defined]
    BUY_SHEDS.clear()
    # The pistol's spot is on the east corn; it goes on the board fence
    # (the farmhouse's south wall, a building's) nearest that spot.
    place_wall_buy(bp, "pistol_burst", Point(fi.maxs.x - 2.0, 250.0, fz - 8.0), Facing.WEST,
                   zone_box=zones["farmyard"].bounds, id="farmyard_wallbuy",
                   avoid=_farmyard_later(plan, fi, fz))

    # A riser well clear of the scarecrow post (it used to stand at its foot).
    for i, (x, y) in enumerate(((1600.0, 420.0), (2150.0, -480.0), (850.0, 780.0),
                                (2180.0, 780.0))):
        bp.add_riser(zones["patch"], Point(x, y, pz), Facing.WEST, id=f"patch_riser_{i}")
    bp.place_perk("stamin_up", Point(2050.0, pi.mins.y + 24.0, pz), Facing.NORTH,
                  id="perk_stamin_up")
    # The patch is corn on all four sides: the smg hangs in a tool shed
    # standing in front of the north corn (the corn behind it is whole).
    _shed_for_buy(bp, plan, "patch_buy_shed", Point(1500.0, pi.maxs.y, pz), pa, zones["patch"].bounds)
    place_wall_buy(bp, "smg_standard", Point(1500.0, pi.maxs.y - 2.0, pz - 8.0), Facing.SOUTH,
                   zone_box=zones["patch"].bounds, id="patch_wallbuy")

    # ---- the maze: its corn, its risers, the wall buy and the power -------
    spots = maze_spots(plan, passages)
    MAZE_SPOTS.clear()
    MAZE_SPOTS.update(spots)
    for key in maze_keys:
        room = rooms[key]
        for i, cell in enumerate(spots["risers"][key]):
            x, y = plan.cell_centre(cell)
            bp.add_riser(zones[key], Point(x, y, room.floor_z), Facing.NORTH, id=f"{key}_riser_{i}")
    # The shotgun: on the back wall of the dead end nearest the entrance.
    # A hut filling the dead end, wall to wall: every face of the maze is
    # corn, so the shotgun hangs on the hut's back wall.
    (wx, wy), facing = _back_wall(plan, spots["wallbuy"], passages, 2.0)
    (hx, hy), _ = _back_wall(plan, spots["wallbuy"], passages, 0.0)
    ez = rooms["mazeentry"].floor_z
    BUY_SHEDS.append(buy_shed(bp, Point(hx, hy, ez), facing, width=plan.maze_pitch - plan.wall - 2.0,
                              depth=DEAD_END_SHED_DEPTH, material=cm._PLANKS, ident="mazeentry_buy_shed"))
    record_opening(bp, BUY_SHEDS[-1], "buy shed")
    place_wall_buy(bp, "shotgun_pump", Point(wx, wy, ez - 8.0), facing,
                   zone_box=zones["mazeentry"].bounds, id="mazeentry_wallbuy")
    # The gate into the deep rows: its door's keep-clear bares the corn
    # walls either side for about 150 units.  They are left bare: as on
    # the earth wall, the bare face reads as soil, and plank boards there
    # stand out grey.
    # The power: a generator switch on the back wall of the deepest dead end
    # of the deep rows.  It opens the barn (an electric door).
    power_room = rooms[cm.room_of(spots["power"])]
    (sx, sy), facing = _back_wall(plan, spots["power"], passages, 24.0)
    bp.place_power_switch(Point(sx, sy, power_room.floor_z + 8.0), facing, id="mazedeep_power")
    _backboard(bp, sx - facing.step.x * 24.0, sy - facing.step.y * 24.0, power_room.floor_z, facing,
               BACKBOARD_HALF["power"], "mazedeep_power_board", text="POWER")

    for i, (x, y) in enumerate(((hi.mins.x + 150, hi.mins.y + 300), (hi.maxs.x - 150, hi.maxs.y - 150),
                                (hi.mins.x + 150, hi.maxs.y - 150), (hi.maxs.x - 150, hi.mins.y + 300))):
        bp.add_riser(zones["heart"], Point(x, y, tz), Facing.EAST, id=f"heart_riser_{i}")
    bp.place_perk("double_tap", Point(hi.mins.x + 24.0, hi.centre.y + 150.0, tz), Facing.EAST,
                  id="perk_double_tap")
    bp.place_perk("mule_kick", Point(hi.maxs.x - 24.0, hi.centre.y + 150.0, tz), Facing.WEST,
                  id="perk_mule_kick")
    # The heart is corn all round: the smg hangs in a shed in front of the
    # north corn.
    _shed_for_buy(bp, plan, "heart_buy_shed", Point(hi.centre.x, hi.maxs.y, tz), he, zones["heart"].bounds)
    place_wall_buy(bp, "smg_fastfire", Point(hi.centre.x, hi.maxs.y - 2.0, tz - 8.0),
                   Facing.SOUTH, zone_box=zones["heart"].bounds, id="heart_wallbuy")
    # The box's second home, where it goes when it moves ("a nicer farm
    # upstate"): the scarecrow's clearing.
    bp.place_mystery_box(Point(hi.mins.x + 420.0, hi.maxs.y - 40.0, tz), Facing.SOUTH, starting=False,
                         id="heart_box")

    # Boarded gaps in the corn: a barrier in every outdoor zone but the
    # farmyard, each on a stretch of corn with nothing but the dark behind it,
    # and in the maze on a cell's middle, where no lattice post stands.  The
    # farmyard has a door or gate in all four of its walls, and a window cut
    # in any of them (north at -600, south at +625, measured) cost
    # the door on that wall its route: the farmhouse or the barn became
    # unreachable (Z25/Z48).  Its zombies come up out of its risers.
    for key, side_name, cell, ident in cm.MAZE_WINDOWS:
        side = {"north": Side.NORTH, "south": Side.SOUTH, "east": Side.EAST, "west": Side.WEST}[side_name]
        room = rooms[key]
        cx, cy = plan.cell_centre(cell)
        offset = (cx - room.outer.centre.x) if side in (Side.NORTH, Side.SOUTH) else (cy - room.outer.centre.y)
        bp.add_window(zones[key], room, side, offset=offset, yard_depth=176.0, id=ident)
    bp.add_window(zones["patch"], pa, Side.NORTH, offset=-400.0, yard_depth=176.0, id="patch_window")
    bp.add_window(zones["farmhouse"], fh, Side.WEST, yard_depth=176.0, id="farmhouse_window_west")
    bp.add_window(zones["farmhouse"], fh, Side.EAST, yard_depth=176.0, id="farmhouse_window_east")
    bp.add_riser(zones["farmhouse"], Point(fhi.mins.x + 80.0, fhi.maxs.y - 80.0, hz), Facing.EAST,
                 id="farmhouse_riser")
    bp.place_perk("juggernog", Point(fhi.maxs.x - 150.0, fhi.maxs.y - 24.0, hz), Facing.SOUTH,
                  id="perk_juggernog")
    bp.place_mystery_box(Point(fhi.mins.x + 230.0, fhi.maxs.y - 40.0, hz), Facing.SOUTH,
                         id="farmhouse_box")
    bp.place_wall_weapon("ar_marksman", Point(fhi.maxs.x - 2.0, fhi.mins.y + 110.0, hz - 8.0),
                         Facing.WEST, id="farmhouse_wallbuy")

    # The east window sits under the hayloft, clear of the hayloft stairs (at
    # offset +150 it opened 16 units behind them, where nobody could rebuild it).
    bp.add_window(zones["barn"], ba, Side.EAST, offset=-226.0, yard_depth=176.0,
                  id="barn_window_east")
    bp.add_window(zones["barn"], ba, Side.WEST, offset=150.0, yard_depth=176.0,
                  id="barn_window_west")
    bp.place_wall_weapon("ar_standard", Point(bi.mins.x + 2.0, bi.centre.y - 60.0, bz - 8.0),
                         Facing.EAST, id="barn_wallbuy")
    hayloft = Bounds.between((bi.mins.x, bi.mins.y, loft_top - 16.0),
                          (bi.maxs.x, bi.mins.y + plan.loft_depth, loft_top))
    bp.add_block(hayloft, cm._PLANKS, walkable=True, id="barn_hayloft")
    steps = int(plan.loft_height // 16)
    stair_x = bi.maxs.x - 128.0
    bp.add_steps(Point(stair_x, bi.mins.y + plan.loft_depth + steps * 32.0, bz), steps,
                 32.0, 16.0, 112.0, Facing.SOUTH, cm._PLANKS, id="barn_loft_steps")
    # A rail along the hayloft's open edge, all but the stair head.
    # Posts and two rails in plank, a clip over the whole of it so it still
    # stops a player like a solid rail would (a 40-tall solid slab reads
    # as a teal glass barrier).
    rail = Bounds.between((bi.mins.x, hayloft.maxs.y - 4.0, loft_top), (stair_x - 8.0, hayloft.maxs.y, loft_top + 40.0))
    bp.add_block(rail, CLIP, reachable=False, id="barn_loft_rail", note="loft rail clip")
    for n, px in enumerate(_steps(rail.mins.x, rail.maxs.x - 5.0, 48.0) + [rail.maxs.x - 5.0]):
        bp.add_block(Bounds.between((px, rail.mins.y - 1.0, loft_top), (px + 5.0, rail.maxs.y, rail.maxs.z)),
                     cm._PLANKS, reachable=False, id=f"barn_loft_rail_post_{n}", note="loft rail post")
    for n, (r0, r1) in enumerate(((rail.maxs.z - 5.0, rail.maxs.z), (loft_top + 17.0, loft_top + 21.0))):
        bp.add_block(Bounds.between((rail.mins.x, rail.mins.y, r0), (rail.maxs.x, rail.mins.y + 3.0, r1)),
                     cm._PLANKS, reachable=False, id=f"barn_loft_rail_bar_{n}", note="loft rail")
    bp.place_pack_a_punch(Point(bi.centre.x - 120.0, bi.mins.y + 40.0, loft_top), Facing.NORTH,
                          id="barn_pap")
    for i, (x, y) in enumerate(((bi.mins.x + 120, bi.maxs.y - 120), (bi.centre.x - 150, bi.centre.y + 150))):
        bp.add_riser(zones["barn"], Point(x, y, bz), Facing.SOUTH, id=f"barn_riser_{i}")

    # =====================================================================
    # Structures: the hayride stop, the farm stand, fences, scarecrow posts.
    # =====================================================================
    stop_x, stop_y = route[0]
    platform = Bounds.between((stop_x - 150, fi.mins.y, fz), (stop_x + 90, stop_y - 150, fz + 12.0))
    bp.add_block(platform, cm._PLANKS, walkable=True, id="hayride_platform", note="hayride stop")
    # A board at the back of the stop, lettered to the yard, a lantern on its
    # post (a plank deck and a use prompt alone are hard to find as the
    # place to buy the ride).
    hay_sign = _sign_board(bp, stop_x - 110.0, stop_x - 10.0, fi.mins.y + 30.0, fz + 12.0, "hayride_sign",
                           (("HAYRIDE", 1.8, 74.0), ("BOARD HERE", 1.2, 52.0)), facing=Facing.NORTH)
    # The stand's canopy runs over its counter as well as the two perks.
    canopy = Bounds.between((120.0, 430.0, fz + 150.0), (640.0, fi.maxs.y, fz + 158.0))
    # Planks, not roofing felt: the felt reads as a thick grey concrete
    # slab.
    # An open slatted roof, not a slab (a plank slab still reads as a
    # heavy block): a beam along the front on four
    # posts, a ledger along the back boards, and rafters across with gaps
    # between.  ``canopy`` stays the roof's whole box for the keep-outs.
    (c0x, c0y, c0z), (c1x, c1y, c1z) = canopy.mins, canopy.maxs
    bp.add_block(Bounds.between((c0x, c0y, c0z - 4.0), (c1x, c0y + 8.0, c0z + 4.0)), cm._BEAM,
                 reachable=False, id="farmstand_canopy_beam")
    bp.add_block(Bounds.between((c0x, c1y - 6.0, c0z - 4.0), (c1x, c1y, c0z + 4.0)), cm._BEAM,
                 reachable=False, id="farmstand_canopy_ledger")
    for n, rx in enumerate(_steps(c0x + 4.0, c1x - 10.0, 34.0)):
        bp.add_block(Bounds.between((rx, c0y - 6.0, c0z + 4.0), (rx + 5.0, c1y, c1z)), cm._PLANKS,
                     reachable=False, id=f"farmstand_canopy_rafter_{n}")
    for i, (x, y) in enumerate(((126.0, 436.0), (230.0, 436.0), (425.0, 436.0), (634.0, 436.0))):
        bp.add_block(Bounds.between((x - 4, y - 4, fz), (x + 4, y + 4, fz + 146.0)), cm._BEAM,
                     reachable=False, id=f"farmstand_post_{i}")
    counter = Bounds.between((140.0, fi.maxs.y - 60.0, fz), (250.0, fi.maxs.y, fz + 42.0))
    bp.add_block(counter, cm._PLANKS, reachable=False, id="farmstand_counter")

    # No maze map board: in-world maps give the layout away (P17).
    # The PICK YOUR OWN PUMPKIN sign by the patch gate, where its notice is.
    sign_x, sign_y = pi.mins.x + 80.0, plan.lane_y + 250.0
    sign = _sign_board(bp, sign_x - 50.0, sign_x + 50.0, sign_y + 30.0, pz, "patch_sign",
                       (("PICK YOUR OWN", 1.2, 82.0), ("PUMPKINS", 1.8, 60.0)))

    # The patch's decorative scarecrow was removed; its
    # lantern still lights the patch from where it stood.  Only the heart's
    # (the quest's) stands.
    patch_spot = (1525.0, 175.0)
    scarecrow_heart = (hi.centre.x, hi.centre.y - 120.0)
    posts = [_scarecrow_frame(*scarecrow_heart, tz)]
    SCARECROWS.clear()
    _BAND_FACES.clear()
    JACKS.clear()
    QUEST_JACKS.clear()
    BOSS_SPAWN.clear()
    SCARECROWS["heart"] = (scarecrow_heart[0], scarecrow_heart[1], tz + POLE_TOP)
    # The boss is the scarecrow climbing down (it spawns from
    # the scarecrow, not somewhere new): it appears at the foot of its post,
    # on the gate side it faces, and the script snaps it to the navmesh
    # (Boss.spawn_snap) and takes the figure off the post at that moment.
    BOSS_SPAWN.append((scarecrow_heart[0], scarecrow_heart[1] - SCARECROW_FOOT, tz))

    fence_y = stop_y + 160.0
    fence_sections = []
    for a, b in ((-150.0, 150.0), (300.0, 580.0)):
        fence_sections += _fence(a, b, fence_y, fz)
    fences = [box for _, box in fence_sections]

    keepouts: list[Bounds] = []
    machine_boxes: list[tuple[object, Bounds]] = []
    aperture_boxes: list[tuple[Bounds, Bounds]] = []
    for door_room in rooms.values():
        for box in door_room.aperture_boxes:
            # The approach, deep on both sides of the wall and only a little
            # wider than the hole along it, so the stalks still line the
            # corn right up to a gate.
            thin_x = (box.maxs.x - box.mins.x) < (box.maxs.y - box.mins.y)
            keepouts.append(box.grown_on(Axis.X, 140.0 if thin_x else 24.0)
                            .grown_on(Axis.Y, 24.0 if thin_x else 140.0).grown_on(Axis.Z, 16.0))
            # The corn bands only keep clear of the hole itself, out to the
            # approach's depth: the extra 24 either side along the wall, plus
            # each stalk's own half-width, cleared the corridor's side walls
            # for 140 units at every door and window, far wider than
            # the door (the blueprint's own interactive keep-clear
            # still holds for the stalks).
            # An open boundary between two maze rooms (wider than any door,
            # nothing to walk through) keeps only its own gap: its approach
            # bared every corridor wall that crosses it for 140 each side.
            # A door is often the corridor's full width, so its approach also
            # takes the bands along the corridor's two walls: those keep
            # their corn up to the door, and only the corridor's middle (the
            # hole less a band either side) stays clear.
            along = (box.maxs.y - box.mins.y) if thin_x else (box.maxs.x - box.mins.x)
            deep = 140.0 if along <= OPEN_BOUNDARY else 0.0
            trim = -max(0.0, min(BAND_DEPTH, (along - 64.0) / 2)) if deep else 0.0
            aperture_boxes.append((keepouts[-1], box.grown_on(Axis.X, deep if thin_x else trim)
                                   .grown_on(Axis.Y, trim if thin_x else deep).grown_on(Axis.Z, 16.0)))
    keepouts.append(Bounds.between((-150, 0, fz), (150, 300, fz + 200)))  # the spawn
    keepouts += [b.grown(4.0) for b in BUY_SHEDS]
    keepouts.append(platform.grown(16.0))
    keepouts.append(Bounds.between((canopy.mins.x - 10, canopy.mins.y - 10, fz),
                                   (canopy.maxs.x + 10, canopy.maxs.y, fz + 200)))
    keepouts.append(counter.grown(4.0))
    keepouts += [b.grown(24.0) for b in sign + hay_sign]
    keepouts += [p.grown(30.0) for p in posts]
    keepouts += [f.grown(8.0) for f in fences]
    keepouts.append(Bounds.between((stair_x - 40, bi.mins.y + plan.loft_depth - 10, bz),
                                   (bi.maxs.x, bi.mins.y + plan.loft_depth + steps * 32 + 80, bz + 300)))
    bx, by, bzz = BOSS_SPAWN[0]
    keepouts.append(Bounds.between((bx - 70, by - 70, bzz - 10), (bx + 70, by + 70, bzz + 120)))
    spawn_boxes = []
    apron_boxes: list[Bounds] = []
    for spawn in bp.elements(Spawn):
        p = spawn.position
        keepouts.append(Bounds.between((p.x - 50, p.y - 50, p.z - 10), (p.x + 50, p.y + 50, p.z + 100)))
        spawn_boxes.append(keepouts[-1])
    # Nothing solid
    # within 90 of a barricade window, up to the hayloft.  The corn bands keep
    # to their own aperture rules (band_exempt below).
    # The shared zone (dressing.window_keepouts, the one Z57 checks), made
    # wider here: 90 in from the wall, 42 past each end of the 96-wide
    # opening (90 either side of the window's middle), and up to the hayloft.
    window_boxes = window_keepouts(bp, approach=WINDOW_APPROACH, side=WINDOW_SIDE, height=260.0)
    keepouts += window_boxes
    for element in bp.elements():
        kind = type(element).__name__
        if kind == "WallWeapon":
            chalk, apron = _wallbuy_keepouts(element.position, element.facing)
            keepouts += [chalk, apron]
            apron_boxes += [chalk, apron]
        elif kind in ("Machine", "MysteryBox", "PowerSwitch"):
            # 130 either side and out in front, but only back as far as the
            # wall it stands against: the square it was cut through that
            # wall and bared the corn in the corridor behind (the maze rows behind the heart's two perks, the
            # power switch's dead end).
            keepouts.append(_facing_box(element.position, element.facing, 130.0, MACHINE_BACK, 130.0))
            machine_boxes.append((element, keepouts[-1]))
    d = Dresser(bp, route, keepouts)
    # A wall buy's chalk and reading spot: a back-row stalk is held to the
    # blueprint's lane rule there instead (blueprint.lanes.beside_the_chalk:
    # against the wall beside the chalk, never in front of it or the stand).
    d.back_exempt.update(id(b) for b in apron_boxes)
    d.band_exempt.update(id(b) for b in window_boxes)
    d.window_boxes = window_boxes
    # The corn stands over the zombie spawns by the walls.  A stalk
    # is walk-through (KIT_SOLID), so a zombie climbs out through it; the
    # spawns' 100-unit keep-outs had left 130-140 units of bare earth wall
    # at each in the patch and the maze rooms.
    d.band_exempt.update(id(b) for b in spawn_boxes)
    for wide, narrow in aperture_boxes:
        d.band_exempt.add(id(wide))
        d.band_keepouts.append(narrow)
    # The corn bands grow closer: up to the stall's posts, not 130 off.
    for element, wide in machine_boxes:
        slug = getattr(getattr(element, "perk", None), "slug", None)
        half = BAND_CLEAR.get(type(element).__name__, 60.0)
        if slug in PERK_STALLS and PERK_STALLS[slug]["stall"]:
            half = STALL_HALF + 10.0
        d.band_exempt.add(id(wide))
        d.band_keepouts.append(_facing_box(element.position, element.facing, half, MACHINE_BACK, 130.0))

    # =====================================================================
    # Farmyard
    # =====================================================================
    # Tracks trodden between the gates and the spawn, laid first so the
    # dressing keeps off them (see _ground).
    _track(bp, ((0.0, fi.mins.y), (0.0, fi.maxs.y)), fz, 56.0, "farmyard_path_ns", d=d, zone="farmyard")
    # It stops at the corn's front, not the wall: run into the wall it bared
    # 108 units of it (no stalk may stand half on a path, Z44), and the
    # maze gate is further north.
    _track(bp, ((fi.mins.x + BAND_DEPTH, 150.0), (-28.0, 150.0)), fz, 40.0, "farmyard_path_maze", d=d,
           zone="farmyard")
    _yard_boards(bp, fi, fz)
    # The tractor, the way out: parked in the north-west corner, nose east
    # to the yard.  The defend step stands south of it, the exit trigger 110
    # west of that.
    tx, ty = fi.mins.x + 206.0, fi.maxs.y - 150.0
    d.put("farmyard", TRACTOR, tx, ty, fz, TRACTOR_YAW, check=False)
    ex0, ex1, ey0, ey1 = _extent(TRACTOR, 1.0, TRACTOR_YAW)
    d.keepouts.append(Bounds.between((tx + ex0 - 10, ty + ey0 - 10, fz), (tx + ex1 + 10, ty + ey1 + 10, fz + 120)))
    SCARECROWS["tractor"] = (tx - 20.0, ty - 110.0, fz)
    # Room to aim at the way out: the exit trigger stands 110 west of here.
    # (Only 50 either way along the west corn: it is 76 behind the trigger,
    # and the stalks beyond that span do not stand between it and a player.)
    ex, ey = tx - 20.0 - 110.0, ty - 110.0
    d.keepouts.append(Bounds.between((ex - 90, ey - 50, fz), (ex + 90, ey + 50, fz + 150)))
    # The fence along the lane, and the scarecrows' frames.
    for mx, _ in fence_sections:
        d.put("farmyard", FENCE, mx, fence_y, fz, 0.0, check=False, lane=False)
    # It faces the way players come at it, arms spread across their view:
    # from its gate (south); side-on, it reads as a bare pole.
    for zone_, (sx_, sy_), z_, yaw_ in (("heart", scarecrow_heart, tz, 0.0),):
        _scarecrow_body(bp, d, zone_, sx_, sy_, z_, yaw_, f"{zone_}_scarecrow", head=static_head_name(zone_))
    bales = []
    for i, (x, y, across, stack) in enumerate((
            (-560.0, 90.0, False, 2), (-490.0, 90.0, False, 1), (560.0, -100.0, True, 1),
            (620.0, 20.0, True, 2), (-620.0, -540.0 + 16.0, False, 1))):
        bales += _bale(d, "farmyard", x, y, fz, across=across, stack=stack, yaw=i * 5.0)
    d.keepouts += [b.grown(6.0) for b in bales]
    # The cider stand: jars of cider, a basket of "apples" (oranges), a
    # decanter, a pumpkin for show.
    ctop = counter.maxs.z
    cx0 = (counter.mins.x + counter.maxs.x) / 2
    for i, (m, dx, dy) in enumerate(((JAR, -40, -10), (JAR, -32, -14), (JAR, -24, -8), (JUG, -40, -32),
                                     ("p7_decanter_glass_bottle", 36, -34),
                                     ("p7_food_fruit_melon", 42, -14))):
        d.put("farmyard", m, cx0 + dx, fi.maxs.y - 20.0 + dy, ctop, i * 40.0, check=False)
    _basket_of_oranges(d, "farmyard", cx0 + 8.0, fi.maxs.y - 26.0, ctop, 20.0, 2, check=False)
    _pumpkin(d, "farmyard", cx0 - 6.0, fi.maxs.y - 44.0, ctop, 30.0, 0.9, check=False)
    for i, (x, y) in enumerate(((100.0, 400.0), (640.0, 380.0))):
        if d.put("farmyard", CRATE, x, y, fz, i * 20.0):
            _pumpkin(d, "farmyard", x, y, fz + 30.0, i * 50.0, 1.0, check=False)
    # The quest's farmyard lantern by the fence, facing the spawn; then the
    # ordinary lit ones.
    JACKS["farmyard"] = [_quest_jack(bp, d, "farmyard", -100.0, stop_y + 195.0, fz, 180.0)]
    jacks = [(220.0, stop_y + 195.0), (620.0, stop_y + 195.0), (-640.0, 250.0), (400.0, 250.0)]
    for i, (x, y) in enumerate(jacks, start=1):
        if _pumpkin(d, "farmyard", x, y, fz, 150.0 + i * 13.0, JACK_SCALE, JACK):
            _lamp(bp, x, y, fz + 44.0, "farmyard", f"farmyard_jack_{i}", radius=220.0)
    # Grouped, not strewn: the render showed boards, a 2x4 and
    # a lone shovel scattered over the open yard like confetti.  The same
    # props now make two things a farmyard has: a woodpile against the barn
    # side boards (planks, the 2x4, a long crate of offcuts) and the feed
    # sacks on their pallet by the maze gate.  The weeds keep to the edges.
    litter = [
        # The woodpile, east of the barn door, against the barn-side boards.
        ("p7_debris_wood_board_cluster_01", 180.0, fi.mins.y + 34.0, 0.0),
        ("p7_debris_wood_board_cluster_02", 235.0, fi.mins.y + 38.0, 20.0),
        ("p7_debris_wood_board_2x4x128", 225.0, fi.mins.y + 78.0, 0.0),
        (CRATE_LONG, 305.0, fi.mins.y + 40.0, 0.0),
        # The feed: sacks on a pallet and two more set down beside it.
        ("p7_pallet_wood_damaged", -620.0, -10.0, 0.0),
        (SACK, -585.0, -45.0, 80.0), (SACK, -560.0, -20.0, 100.0),
        ("p7_foliage_weed_cluster_lrg", -655.0, -170.0, 0.0), ("p7_foliage_weed_cluster_lrg", 640.0, 380.0, 90.0),
        ("p7_foliage_weed_cluster_med", -640.0, 300.0, 40.0),
        ("p7_foliage_grass_tall_cluster_sml", -650.0, -200.0, 0.0),
        # The shovel stays with the harvest cart in the east yard.
        ("p7_tools_shovel", 430.0, 130.0, 110.0),
    ]
    for i, (m, x, y, yaw) in enumerate(litter):
        if d.put("farmyard", m, x, y, fz, yaw, solid=False if m.startswith("p7_foliage") else None):
            if m == "p7_pallet_wood_damaged":
                for j in range(3):
                    d.put("farmyard", SACK, x - 12 + j * 12, y + (j % 2) * 6, fz + 5.0, 90.0 + j * 10,
                          check=False)
    # A pumpkin pile at the stand's end and a row of them along the fence.
    for i in range(6):
        _pumpkin(d, "farmyard", 60.0 + (i % 3) * 30.0, 380.0 - (i // 3) * 30.0, fz, i * 40.0,
                 1.0 + 0.1 * (i % 3))
    for i in range(6):
        _pumpkin(d, "farmyard", -130.0 + i * 125.0, stop_y + 230.0, fz, i * 45.0, 1.0 + 0.15 * (i % 2))
    # The east yard: a harvest cart and its load, barrels, baskets.
    for i, (m, x, y, yaw) in enumerate((
            ("p7_wheel_barrow_street_vendor", 470.0, 180.0, 20.0),
            ("p7_barrel_metal_55gal_blue", 480.0, 392.0, 0.0), ("p7_barrel_metal_55gal_blue", 508.0, 370.0, 40.0),
            (BASKETS[0], 440.0, 330.0, 30.0), (CRATE_LONG, -300.0, 520.0, 0.0),
            (CRATE, -560.0, -440.0, 0.0), (CRATE, -560.0, -405.0, 15.0))):
        if d.put("farmyard", m, x, y, fz, yaw, solid=False if m.startswith("p7_foliage") else None):
            if m == "p7_wheel_barrow_street_vendor":
                for j in range(3):
                    _pumpkin(d, "farmyard", x + 34 + j * 4, y - 20 + j * 24, fz, j * 60.0, 0.95,
                             check=False)
            elif m == "p7_pallet_wood_damaged":
                for j in range(2):
                    d.put("farmyard", SACK, x - 8 + j * 16, y, fz + 5.0, 90.0 + j * 10, check=False)
            elif m == BASKETS[0]:
                for j in range(3):
                    d.put("farmyard", ORANGE, x - 4 + j * 4, y - 6 + j * 6, fz + MODEL_BOX[m][1][2], j * 50.0, 1.0,
                          check=False)
    for i, box in enumerate(_tops(bales)[:3]):
        d.put("farmyard", LAMP, box.centre.x, box.centre.y, box.maxs.z, i * 60.0, check=False)
    # The hayride stop's lantern, on its sign's west post.
    post = hay_sign[1]
    d.put("farmyard", LAMP, post.centre.x, post.centre.y, post.maxs.z, 0.0, check=False)
    # The middle of the yard (bare, it reads as dirt; the tracks are
    # laid at the top of this section): the harvest
    # brought out of the farmhouse in heaps on spilled straw, and a hand cart
    # loaded with more.
    for h, (hx, hy) in enumerate(((-230.0, 420.0), (-250.0, -95.0), (240.0, -95.0))):
        if not d.free(hx, hy, fz, 46.0):
            continue
        straw = _ground(bp, hx - 44.0, hy - 42.0, hx + 44.0, hy + 42.0, fz, "straw", f"farmyard_heap_straw_{h}")
        heap_spots = [(0.0, 0.0)] + [(r * math.cos(math.radians(a + r)), r * math.sin(math.radians(a + r)))
                                for r in (17.0, 32.0) for a in range(0, 360, 60 if r < 20 else 45)]
        for k, (dx, dy) in enumerate(heap_spots[:11]):
            _pumpkin(d, "farmyard", hx + dx, hy + dy, fz + GROUND_H["straw"], k * 53.0 + h * 20.0,
                     PUMPKIN_SCALE + (0.15 if k == 0 else 0.05 * (k % 3) - 0.05))
        d.keepouts.append(straw.grown(GROUND_CLEAR))
    if d.put("farmyard", "p7_wheel_barrow_street_vendor", -330.0, -60.0, fz, 70.0):
        ctop = fz + MODEL_BOX["p7_wheel_barrow_street_vendor"][1][2] - 4.0
        for j, (dx, dy) in enumerate(((-6.0, -14.0), (6.0, 0.0), (-4.0, 14.0), (2.0, -2.0))):
            _pumpkin(d, "farmyard", -330.0 + dx, -60.0 + dy, ctop + (8.0 if j == 3 else 0.0), j * 70.0, 0.95,
                     check=False)
    # The board fences north and south: a painted farm sign, loose planks
    # and feed sacks along the foot of them.
    _board_wall_dressing(bp, d, fy, plan)
    # Corn on the yard's east and west; its north and south are board fence.
    _room_bands(d, "farmyard", fy, [], salt=1, planted=_Planted(), sides=(Side.EAST, Side.WEST),
                lining=OPEN_LINING)

    # =====================================================================
    # Pumpkin patch
    # =====================================================================
    for i, (x, y) in enumerate(((1200.0, -500.0), (2230.0, 150.0), (780.0, 150.0))):
        bb = _bale(d, "patch", x, y, pz, across=(i != 0), yaw=i * 9.0)
        d.keepouts += [b.grown(6.0) for b in bb]
        d.put("patch", LAMP if i != 1 else CRATE, bb[-1].centre.x, bb[-1].centre.y, bb[-1].maxs.z,
              i * 50.0, check=False)
    for i, (m, x, y) in enumerate((
            ("p7_wheel_barrow_street_vendor", 1850.0, -470.0), ("p7_tools_shovel", 1790.0, -500.0),
            (CRATE, 900.0, -500.0), (SACK, 945.0, -515.0),
            ("p7_pallet_wood_damaged", 2230.0, 300.0), (LAMP, 1480.0, 120.0),
            ("p7_gib_chunk_bone_03", 1480.0, 230.0))):
        if d.put("patch", m, x, y, pz, i * 29.0):
            if m == "p7_wheel_barrow_street_vendor":
                for j in range(3):
                    _pumpkin(d, "patch", x + 34 + j * 4, y - 20 + j * 24, pz, j * 60.0, 0.95, check=False)
            elif m == CRATE:
                _pumpkin(d, "patch", x, y, pz + 30.0, i * 40.0, 1.0, check=False)
            elif m == "p7_pallet_wood_damaged":
                for j in range(3):
                    d.put("patch", SACK, x - 12 + j * 12, y + (j % 2) * 6, pz + 5.0, 90.0 + j * 10, check=False)
    _basket_of_oranges(d, "patch", 2150.0, 60.0, pz, 0.0, 0)
    # The quest's patch lantern faces the gate the players come in by.
    JACKS["patch"] = [_quest_jack(bp, d, "patch", 1330.0, -30.0, pz, 250.0)]
    # The third stands 150 units off prize pumpkin 4 (1650, -40), not 70:
    # its baked light lit the spot after the pumpkin was gone (Z64, P12).
    for i, (x, y) in enumerate(((1720.0, 380.0), (1330.0, 380.0), (1800.0, -60.0),
                                (2200.0, 0.0), (900.0, 800.0)), start=1):
        if _pumpkin(d, "patch", x, y, pz, 200.0 + i * 40.0, JACK_SCALE, JACK):
            _lamp(bp, x, y, pz + 50.0, "patch", f"patch_jack_{i}", radius=240.0)
    # The six exploding prize pumpkins (script models) get their spots to
    # themselves.  Their green glow is the script's (an effect deleted with
    # the pumpkin, corn_maze_script.PUMPKIN_GLOW_FX), not a baked light,
    # which would stay on over the crater.
    from .corn_maze_script import EXPLODING_PUMPKINS, GREAT_PUMPKIN
    for x, y in EXPLODING_PUMPKINS:
        d.keepouts.append(Bounds.between((x - 50, y - 50, pz), (x + 50, y + 50, pz + 60)))
    # The quest's Great Pumpkin (a script model, 80 across when full) gets
    # its ground to itself: the crop rows are cut round it.
    gx, gy = GREAT_PUMPKIN
    d.keepouts.append(Bounds.between((gx - 70, gy - 70, pz), (gx + 70, gy + 70, pz + 90)))
    # A split-rail fence along the south side of the hayride lane, a gap
    # every fourth section so nobody is fenced in.
    fl = MODEL_BOX[FENCE][1][0] - MODEL_BOX[FENCE][0][0]
    for n, mx in enumerate(range(int(pi.mins.x) + 100, 1680, int(fl))):
        if n % 4 != 3:
            d.put("patch", FENCE, mx + fl / 2, plan.lane_y - 180.0, pz, 0.0)
    # The field: tilled rows of dark soil across it, cut where the hayride
    # lane and the scarecrow's ground cross them, the pumpkins in twos and
    # threes along the rows (pumpkins on a grid over bare soil read as a
    # vast empty dark floor).  The hayride's own track is
    # trodden into the lane.
    ground_rng = random.Random(f"{plan.maze_seed}-patch-ground")
    _track(bp, route, pz, 90.0, "patch_hayride_track", d=d)

    def patch_clear(x: float, y: float) -> bool:
        return cm.distance_to_route(x, y, route) > cm.HAYRIDE_LANE_HALF + 10.0

    # Clear of the corn bands along the north and south corn (BAND_DEPTH).
    rows = [float(y) for y in range(int(pi.mins.y) + 140, int(pi.maxs.y) - 130, 88)]
    placed = _crop_rows(bp, d, "patch", ground_rng, pi.mins.x + 110.0, pi.maxs.x - 110.0, rows, pz,
                        "patch_row", clear=patch_clear, gap=(70.0, 115.0), cluster=(3, 3, 4, 5))
    _room_bands(d, "patch", pa, [], salt=2, planted=_Planted(), lining=OPEN_LINING)

    # =====================================================================
    # Maze: a staggered double band of corn along both faces of every corn
    # wall and the inside of every maze room, a small scene in every dead
    # end, weeds underfoot, lanterns along the way to the heart and two
    # landmarks over the corn.
    # =====================================================================
    planted = _Planted()
    # The landmarks first, so the corn keeps clear of their legs.
    landmarks = _landmarks(bp, d, plan, rooms)
    # The quest's maze lantern: in the water tower's clearing, on a bale.
    wt = cm.CLEARINGS["water_tower"]
    lx, ly = plan.cell_centre(wt)
    JACKS["mazeentry"] = [_quest_jack(bp, d, "mazeentry", lx - 30.0, ly - 30.0,
                                      rooms["mazeentry"].floor_z, 225.0)]
    scene_rng = random.Random(f"{plan.maze_seed}-scenes")
    for n, cell in enumerate(spots["scenes"]):
        _dead_end_scene(bp, d, plan, rooms, passages, cell, n, scene_rng)
    for n, key in enumerate(maze_keys):
        _room_bands(d, key, rooms[key], maze_walls[key], salt=100 * n, planted=planted)
    _maze_floor(bp, d, plan, rooms, passages, spots, scene_rng)

    # =====================================================================
    # The heart: the scarecrow's clearing
    # =====================================================================
    # Ground cover first, so the dressing keeps off it (see _ground; bare, it
    # reads as a vast empty dark dirt floor): the path
    # trodden in from the gate to the scarecrow, one across between the two
    # perk stalls, a worn ring round the pumpkins, and tilled rows in the
    # corners with pumpkins on them.
    ground_rng = random.Random(f"{plan.maze_seed}-heart-ground")
    sx_, sy_ = scarecrow_heart
    ring_r = 230.0
    cross_y = min(max(1765.0, hi.mins.y + 300.0), hi.maxs.y - 300.0)
    _track(bp, ((sx_, hi.mins.y), (sx_, sy_ - ring_r)), tz, 56.0, "heart_path_gate", d=d, zone="heart")
    _track(bp, ((sx_, sy_ + ring_r), (sx_, cross_y)), tz, 56.0, "heart_path_north", d=d, zone="heart")
    # Short of the two stalls' own dressing either end.
    _track(bp, ((hi.mins.x + 170.0, cross_y), (hi.maxs.x - 170.0, cross_y)), tz, 56.0, "heart_path_across", d=d, zone="heart")
    # No worn ring round the pumpkins: laid as squares it drew as a jagged
    # dotted outline; the gate and north paths stop at it.
    # The rows keep off where the dressing below stands (its bales, crates,
    # the barrow and the scenes in the quadrants).
    # The north bale stands off the front of the wall buy's shed, not in its
    # way in (it stood across the shed's open front).
    north_bale = _off_shed_fronts(hi.centre.x, hi.maxs.y - 250.0, 80.0)
    later = [(hi.mins.x + 200, hi.centre.y - 60), (hi.maxs.x - 200, hi.centre.y - 60), north_bale,
             (hi.mins.x + 300, hi.mins.y + 120), (hi.maxs.x - 300, hi.mins.y + 120), (hi.mins.x + 340, hi.mins.y + 160),
             (hi.centre.x + 260, hi.centre.y + 300), (hi.maxs.x - 320, hi.maxs.y - 300),
             (hi.mins.x + 320, hi.maxs.y - 330), (hi.centre.x - 280, hi.centre.y + 250),
             (hi.centre.x + 300, hi.centre.y - 300), (hi.centre.x - 40, hi.centre.y - 200),
             (hi.maxs.x - 260, hi.maxs.y - 180), (hi.mins.x + 260, hi.centre.y + 120),
             (hi.maxs.x - 280, hi.centre.y + 60), (hi.centre.x - 220, hi.mins.y + 260),
             (hi.centre.x - 200, hi.mins.y + 300), (hi.maxs.x - 330, hi.mins.y + 300),
             (hi.maxs.x - 300, hi.mins.y + 330), (hi.maxs.x - 250, hi.centre.y + 40)]

    def heart_clear(x: float, y: float) -> bool:
        return (abs(x - sx_) > 70.0 and abs(y - cross_y) > 70.0
                and math.hypot(x - sx_, y - sy_) > ring_r + 60.0
                and all(math.hypot(x - lx, y - ly) > 75.0 for lx, ly in later))

    rows = [float(y) for y in range(int(hi.mins.y) + 140, int(hi.maxs.y) - 130, 96)]
    _crop_rows(bp, d, "heart", ground_rng, hi.mins.x + 110.0, hi.maxs.x - 110.0, rows, tz, "heart_row",
               clear=heart_clear, gap=(280.0, 400.0))
    heart_bales = []
    # Well clear of the risers (at y - 250 two bales stood 56 units from
    # heart_riser_0 and _3, and zombies climbed out into them).
    for i, (x, y) in enumerate(((hi.mins.x + 200, hi.centre.y - 60), (hi.maxs.x - 200, hi.centre.y - 60),
                                north_bale)):
        heart_bales += _bale(d, "heart", x, y, tz, across=(i < 2), yaw=i * 6.0)
    d.keepouts += [b.grown(6.0) for b in heart_bales]
    for i, box in enumerate(heart_bales):
        d.put("heart", LAMP if i != 1 else PUMPKIN, box.centre.x, box.centre.y, box.maxs.z, i * 50.0,
              check=False)
    for i in range(12):
        if i in (3, 9):
            continue  # two ways in to the scarecrow (the knife step, the boss)
        a = math.radians(i * 30.0)
        x = scarecrow_heart[0] + 170.0 * math.cos(a)
        y = scarecrow_heart[1] + 170.0 * math.sin(a)
        lit = i % 3 == 0
        # Every face turned in on the scarecrow (a kit face looks -y at yaw 0).
        if _pumpkin(d, "heart", x, y, tz, i * 30.0 - 90.0, JACK_SCALE if lit else 1.1,
                    JACK if lit else PUMPKIN) and lit:
            _lamp(bp, x, y, tz + 44.0, "heart", f"heart_jack_{i}", radius=240.0)
    for i in range(6):
        a = math.radians(i * 60.0 + 30.0)
        d.put("heart", "p7_gib_chunk_bone_0" + str(1 + 2 * (i % 2)), scarecrow_heart[0] + 110 * math.cos(a),
              scarecrow_heart[1] + 110 * math.sin(a), tz, i * 50.0)
    for i, (m, x, y) in enumerate((
            (CRATE, hi.mins.x + 300, hi.mins.y + 120), (CRATE_LONG, hi.maxs.x - 300, hi.mins.y + 120),
            (SACK, hi.mins.x + 340, hi.mins.y + 160), ("p7_tools_shovel", hi.centre.x + 260, hi.centre.y + 300),
            ("p7_wheel_barrow_street_vendor", hi.maxs.x - 320, hi.maxs.y - 300),
            ("p7_pallet_wood_damaged", hi.mins.x + 320, hi.maxs.y - 330),
            ("p7_debris_wood_board_cluster_burn_01", hi.centre.x - 280, hi.centre.y + 250),
            ("p7_debris_wood_board_cluster_burn_02", hi.centre.x + 300, hi.centre.y - 300),
            ("p7_gib_chunk_meat_02", hi.centre.x - 40, hi.centre.y - 200),
            ("p7_zm_teddybear", hi.maxs.x - 260, hi.maxs.y - 180))):
        if d.put("heart", m, x, y, tz, i * 41.0) and m == "p7_wheel_barrow_street_vendor":
            for j in range(3):
                _pumpkin(d, "heart", x + 34 + j * 4, y - 20 + j * 24, tz, j * 60.0, 0.95, check=False)
    # Small scenes in the quadrants: an offering pile, a spilled harvest, a
    # dropped lantern where somebody stopped running.
    for i, (m, x, y, yaw) in enumerate((
            ("p7_foliage_weed_cluster_lrg", hi.mins.x + 260, hi.centre.y + 120, 0.0),
            ("p7_gib_chunk_bone_01", hi.mins.x + 280, hi.centre.y + 140, 40.0),
            (LAMP, hi.mins.x + 240, hi.centre.y + 100, 0.0),
            (BASKETS[1], hi.maxs.x - 280, hi.centre.y + 60, 80.0),
            (LAMP, hi.centre.x - 220, hi.mins.y + 260, 90.0),
            ("p7_gib_chunk_meat_01", hi.centre.x - 200, hi.mins.y + 300, 0.0),
            (SACK, hi.maxs.x - 330, hi.mins.y + 300, 30.0), (CRATE, hi.maxs.x - 300, hi.mins.y + 330, 10.0))):
        d.put("heart", m, x, y, tz, yaw, solid=False if "foliage" in m else None)
    for i in range(5):
        _pumpkin(d, "heart", hi.maxs.x - 250 + 30 * math.cos(i * 1.3), hi.centre.y + 40 + 30 * math.sin(i * 1.3),
                 tz, i * 60.0, 0.95)
    _room_bands(d, "heart", he, [], salt=4, planted=_Planted(), lining=OPEN_LINING)

    # =====================================================================
    # Farmhouse: the kitchen, the parlour, a bed nobody sleeps in.
    # =====================================================================
    # A harvest table, counter height: over the jump, so it is not a perch.
    # No stock wooden table links (the linkable tables are metal lab and
    # office desks), and a solid block reads as a legless teal block,
    # so it is built: a plank top, four square
    # legs, a rail under the top, and a clip over the whole volume so it
    # still stops players and zombies like the block did.
    table = Bounds.between((fhi.centre.x - 60, fhi.centre.y - 20, hz), (fhi.centre.x + 60, fhi.centre.y + 40, hz + 42))
    _brush_table(bp, table, "farmhouse_table")
    d.keepouts.append(table.grown(4.0))
    for i, (dx, dy, yaw) in enumerate(((-40, -45, 90), (40, -45, 90), (-40, 65, 270), (40, 65, 270),
                                       (-90, 10, 0), (90, 10, 200))):
        d.put("farmhouse", "p7_chair_wood_fancy_01", fhi.centre.x + dx, fhi.centre.y + dy, hz, yaw,
              lane=False)
    ttop = table.maxs.z
    for i, (m, dx, dy, sc) in enumerate(((PUMPKIN, 0, 12, 0.95), ("p7_pot_metal_boiling_lg", -34, 4, 1.0),
                                         (JAR, 30, 22, 1.0), (JAR, 36, 16, 1.0),
                                         ("p7_decanter_glass_bottle", -45, 25, 1.0), (LAMP, -10, -8, 1.0),
                                         ("p7_cup_coffee_mug", 20, -5, 1.0), ("p7_cup_coffee_mug", -24, 30, 1.0))):
        d.put("farmhouse", m, fhi.centre.x + dx, fhi.centre.y + dy, ttop, i * 30.0, sc, check=False)
    _basket_of_oranges(d, "farmhouse", fhi.centre.x + 44, fhi.centre.y - 6, ttop, 10.0, 2, check=False)
    # The kitchen, along the south wall west of the door: a wooden counter
    # (brushes: lab cabinets here read as lab furniture) with the pots,
    # the preserves and
    # the cider jug on top.
    cab_y = fhi.mins.y + 15.0
    kitchen_top = hz + COUNTER_H
    counter = Bounds.between((fhi.mins.x + 6.0, fhi.mins.y, hz), (fhi.mins.x + 268.0, fhi.mins.y + 30.0, hz + COUNTER_H))
    _brush_cabinet(bp, counter, (0, 1), "farmhouse_counter", rows=1, cols=4)
    d.keepouts.append(Bounds.between((fhi.mins.x, fhi.mins.y, hz), (fhi.mins.x + 270.0, fhi.mins.y + 40.0, hz + 60)))
    for i, (m, dx, dy) in enumerate((("p7_pot_metal_boiling_lg", 20, 0), ("p7_pan_metal_sauce", 50, 4),
                                     ("p7_pan_metal_lid", 70, -2), (JAR, 95, 2), (JAR, 102, -4),
                                     (JUG, 180, 0), ("p7_cup_coffee_mug", 200, 4),
                                     ("p7_book_vintage_01", 235, 0), (LAMP, 250, -2))):
        d.put("farmhouse", m, fhi.mins.x + dx, cab_y + dy, kitchen_top, i * 25.0, check=False)
    _basket_of_oranges(d, "farmhouse", fhi.mins.x + 150.0 + 70.0, cab_y, kitchen_top, 90.0, 0, check=False)
    # The pantry hutch on the west wall, south of the window: open wooden
    # shelves (the metal industrial shelf here read as a lab rack), the
    # preserves on the middle board, pumpkins and books on the top.
    hutch = Bounds.between((fhi.mins.x, fhi.mins.y + 80.0, hz), (fhi.mins.x + 20.0, fhi.mins.y + 180.0, hz + 86.0))
    boards = _brush_shelf(bp, hutch, (1, 0), "farmhouse_hutch", (2.0, 30.0, 58.0, 86.0))
    d.keepouts.append(hutch.grown(6.0))
    hx, hy = fhi.mins.x + 10.0, (hutch.mins.y + hutch.maxs.y) / 2
    for i, (m, dy, sc) in enumerate(((JAR, -40, 1.0), (JAR, -32, 1.0), (JAR, -24, 1.0), (PUMPKIN, 0, 0.95),
                                     ("p7_book_vintage_02", 26, 1.0), ("p7_book_vintage_03", 34, 1.0))):
        d.put("farmhouse", m, hx, hy + dy, boards[-1], i * 20.0, sc, check=False)
    for i, (m, dy) in enumerate(((JAR, -38), (JAR, -30), (JAR, -22), (JAR, -14), (JUG, 8),
                                 ("p7_bottle_glass_wine_01", 24), ("p7_bottle_glass_wine_01", 32))):
        d.put("farmhouse", m, hx, hy + dy, boards[2], i * 35.0, check=False)
    for i, (m, dy) in enumerate(((BASKETS[0], -24), ("p7_pot_metal_boiling_lg", 14), ("p7_pan_metal_sauce", 32))):
        d.put("farmhouse", m, hx, hy + dy, boards[1], 90.0 * (i % 2), check=False)
    for i, (m, x, y, yaw) in enumerate((("p7_box_wood_wine_storage", fhi.mins.x + 300, fhi.mins.y + 60, 90.0),
                                        (BASKETS[0], fhi.mins.x + 310, fhi.mins.y + 88, 80.0))):
        d.put("farmhouse", m, x, y, hz, yaw, lane=False)
    # The parlour, south-east of the door: a cast-iron wood stove on a brick
    # hearth against the south wall, a braided rug in front of it, the couch
    # facing it and a chair turned to it, a footstool with the lamp, so the
    # room has a second furniture group and the couch faces something.  Clear of the wall buy's apron on the east wall.
    stove_x = fhi.centre.x + 230.0
    _wood_stove(bp, stove_x, fhi.mins.y + 22.0, hz, fhi.maxs.z, "farmhouse_stove")
    d.keepouts.append(Bounds.between((stove_x - 36.0, fhi.mins.y, hz), (stove_x + 36.0, fhi.mins.y + 70.0, fhi.maxs.z)))
    _rug(bp, Bounds.between((stove_x - 110.0, fhi.mins.y + 76.0, hz), (stove_x + 60.0, fhi.mins.y + 160.0, hz + RUG_H)),
         "farmhouse_rug_parlour")
    # A wooden settle facing the stove, not the stock modern couch
    # (a low dark modern chaise on a
    # metal frame reads as out of place in a farmhouse): a plank seat on two end
    # boards, a high back, a cushion on it.
    sx0, sx1, sy0 = stove_x - 30.0, stove_x + 40.0, fhi.mins.y + 176.0
    for n, (s_lo, s_hi, mat) in enumerate((
            ((sx0, sy0, hz), (sx0 + 3.0, sy0 + 24.0, hz + 26.0), cm._BEAM),
            ((sx1 - 3.0, sy0, hz), (sx1, sy0 + 24.0, hz + 26.0), cm._BEAM),
            ((sx0 + 3.0, sy0, hz + 14.0), (sx1 - 3.0, sy0 + 21.0, hz + 18.0), cm._PLANKS),
            ((sx0 + 3.0, sy0 + 21.0, hz + 14.0), (sx1 - 3.0, sy0 + 24.0, hz + 46.0), cm._PLANKS))):
        bp.add_block(Bounds.between(s_lo, s_hi), mat, reachable=False, id=f"farmhouse_settle_{n}", note="settle")
    d.put("farmhouse", "p7_cai_apt_couch_cushion_sml", stove_x + 5.0, sy0 + 10.0, hz + 18.0, 30.0, check=False)
    for i, (m, x, y, yaw) in enumerate((("p7_chair_wood_fancy_01", stove_x - 80.0, fhi.mins.y + 112.0, 315.0),
                                        ("p7_cai_apt_couch_ottoman", stove_x - 95.0, fhi.mins.y + 178.0, 0.0))):
        d.put("farmhouse", m, x, y, hz + (RUG_H if m.startswith("p7_chair") else 0.0), yaw, check=False)
    d.keepouts.append(Bounds.between((stove_x - 110.0, fhi.mins.y + 70.0, hz), (stove_x + 60.0, fhi.mins.y + 215.0, hz + 60)))
    d.put("farmhouse", LAMP, stove_x - 95.0, fhi.mins.y + 178.0, hz + 19.4, 0.0, check=False)
    # The kitchen table stands on a rug too.
    _rug(bp, Bounds.between((table.mins.x - 60.0, table.mins.y - 58.0, hz), (table.maxs.x + 60.0, table.maxs.y + 58.0, hz + RUG_H)),
         "farmhouse_rug_table")
    # The bed, head to the north wall between the box and Juggernog, on a
    # plank frame with a headboard (a mattress on the floor reads as a
    # squatter's pallet), a nightstand by it.
    bed = MODEL_BOX["p7_bed_mattress_barrack_made_v2"]
    bed_x, bed_y = fhi.centre.x + 40.0, fhi.maxs.y + bed[0][1] - 2.0
    frame = Bounds.between((bed_x - 28.0, fhi.maxs.y - 98.0, hz), (bed_x + 28.0, fhi.maxs.y, hz + BED_FRAME_H))
    _bed_frame(bp, frame, "farmhouse_bed")
    lift = BED_FRAME_H - bed[0][2]
    d.put("farmhouse", "p7_bed_mattress_barrack_made_v2", bed_x, bed_y, hz + lift, 0.0, check=False, lane=False)
    d.put("farmhouse", "p7_bed_pillow_barrack", bed_x, fhi.maxs.y - 16.0, hz + lift + bed[1][2], 0.0, check=False)
    d.put("farmhouse", "p7_zm_teddybear", bed_x + 8.0, fhi.maxs.y - 40.0, hz + lift + bed[1][2], 200.0, check=False)
    stand = Bounds.between((bed_x + 34.0, fhi.maxs.y - 24.0, hz), (bed_x + 58.0, fhi.maxs.y, hz + 30.0))
    _brush_cabinet(bp, stand, (0, -1), "farmhouse_nightstand", rows=1, cols=1)
    for i, (m, dx) in enumerate(((LAMP, -4.0), ("p7_book_vintage_04_burn", 6.0))):
        d.put("farmhouse", m, (stand.mins.x + stand.maxs.x) / 2 + dx, fhi.maxs.y - 12.0, stand.maxs.z, i * 60.0, check=False)
    # The dresser west of the bed: drawers, a lamp, books, a jar, the
    # picture over it.
    dresser = Bounds.between((bed_x - 104.0, fhi.maxs.y - 26.0, hz), (bed_x - 40.0, fhi.maxs.y, hz + 46.0))
    _brush_cabinet(bp, dresser, (0, -1), "farmhouse_dresser", rows=3, cols=2)
    for i, (m, dx, dy) in enumerate(((LAMP, 10, -12), ("p7_book_vintage_02", 24, -10), ("p7_book_vintage_03", 30, -12),
                                     (JAR, 44, -14), (BASKETS[0], 54, -12))):
        fit = fit_within(m, dresser.mins.x + dx, fhi.maxs.y + dy, i * 35.0, dresser)
        if fit is not None:
            d.put("farmhouse", m, fit[0], fit[1], dresser.maxs.z, fit[2], check=False)
    (bx0, by0, _), (bx1, by1, bz1) = bed
    d.keepouts.append(Bounds.between((dresser.mins.x, frame.mins.y, hz), (stand.maxs.x, fhi.maxs.y, hz + 60.0)).grown(10.0))
    # On the walls: a picture over the dresser (the frame that draws its
    # painting, see PICTURE), a clock over the kitchen.  Only two pictures, on
    # different walls, with the notice board below: the one painting hung
    # several times reads as identical frames in a row.
    for i, (m, x, y, yaw, zz) in enumerate((
            (PICTURE, bed_x - 72.0, fhi.maxs.y, 0.0, 88.0),
            ("p7_clock_metal_wall_01_base", fhi.mins.x + 137.0, fhi.mins.y + 4.0, 180.0, 80.0))):
        lo = MODEL_BOX[m][0][2]
        d.put("farmhouse", m, x, y, hz + zz + lo, yaw, check=False, lane=False)
    # Left in a hurry: a broken board and a bone by the parlour, the harvest
    # set down by the door.
    for i, (m, x, y, yaw) in enumerate((
            ("p7_debris_wood_board_splinter_01", fhi.centre.x + 150.0, fhi.centre.y - 110.0, 40.0),
            ("p7_gib_chunk_bone_03", fhi.centre.x + 165.0, fhi.centre.y - 85.0, 0.0))):
        d.put("farmhouse", m, x, y, hz, yaw, lane=False)
    # More of the house (map-principles P2: an indoor room carries at least
    # review.facts.DENSITY_FLOOR props).  Each group is a thing a
    # farmhouse has: the harvest brought in along the east wall, the
    # parlour's reading left where it fell, the supper nobody finished, a
    # crate of preserves by the pantry, and more pictures on the walls.
    cx, cy = fhi.centre.x, fhi.centre.y
    # The harvest brought in: pumpkins, sacks and crates set down along the
    # walls wherever the floor is free (the east wall carries the wall buy
    # and the window, the north the box, the bed and Juggernog, so fixed
    # spots were mostly refused), walked round the room from the south-east
    # corner, until the room has its floor's worth.
    # The bed was placed unchecked, so it is no keep-out of its own: the
    # heap keeps out of it explicitly (otherwise a crate and pumpkins
    # can stand inside the mattress).
    (bx0, by0, _), (bx1, by1, bz1) = bed
    d.keepouts.append(Bounds.between((bed_x + bx0, bed_y + by0, hz), (bed_x + bx1, bed_y + by1, hz + bz1))
                      .grown(12.0))
    # Stores, not the harvest (pumpkins along the skirting and military
    # sandbags indoors look wrong).  The pumpkins went
    # out to the yard; the house keeps crates of preserves, wine boxes and
    # luggage, with jars on the crates.
    heap = (CRATE, "p7_box_wood_wine_storage", "p7_luggage_cloth_a_lg_green", CRATE,
            "p7_box_wood_wine_storage_tan", BASKETS[1])
    want, got, k = 22, 0, 0
    # In heaps, not a ring (a pumpkin every 34 units
    # round the walls read as confetti): the harvest is set down in piles in
    # the corners and at the middle of the south and west walls, each pile a
    # spiral out from its centre, the next pile taking over when one is full
    # or runs out of floor.
    piles = [(fhi.maxs.x - 50.0, fhi.mins.y + 50.0), (fhi.mins.x + 50.0, fhi.mins.y + 50.0),
             (fhi.mins.x + 50.0, fhi.maxs.y - 50.0), (fhi.maxs.x - 50.0, fhi.maxs.y - 50.0),
             (fhi.centre.x - 60.0, fhi.mins.y + 45.0)]
    # Each pile its own stores and size (the same crate, jugs and bottles in
    # every heap reads as a copy-paste stamp): jars
    # in crates, the luggage, the wine, the fruit baskets; the pile at the
    # west wall's middle went (it stood 45 units off the west window).
    pile_stores = ((CRATE, "p7_box_wood_wine_storage", CRATE, CRATE),
                   ("p7_luggage_cloth_a_lg_green", "p7_box_wood_01_sm", "p7_luggage_cloth_a_lg_green"),
                   ("p7_box_wood_wine_storage", "p7_box_wood_wine_storage_tan"),
                   (BASKETS[1], BASKETS[1], "p7_box_wood_wine_storage_tan"),
                   ("p7_box_wood_wine_storage_tan", CRATE, BASKETS[1]))
    pile_size = (6, 4, 5, 4, 3)
    spiral = [(0.0, 0.0)] + [(r * math.cos(math.radians(a + r)), r * math.sin(math.radians(a + r)))
                             for r in (30.0, 56.0, 82.0) for a in range(0, 360, int(3600 / r / 3.2))]
    # Whatever the piles cannot hold goes along the walls as before, so the
    # room keeps its floor's worth (P2).
    ring = []
    for inset in (30.0, 70.0):
        ring += ([(fhi.maxs.x - inset, y) for y in range(int(fhi.mins.y + inset), int(fhi.maxs.y - inset), 34)]
                 + [(x, fhi.maxs.y - inset) for x in range(int(fhi.maxs.x - inset), int(fhi.mins.x + inset), -34)]
                 + [(fhi.mins.x + inset, y) for y in range(int(fhi.maxs.y - inset), int(fhi.mins.y + inset), -34)]
                 + [(x, fhi.mins.y + inset) for x in range(int(fhi.mins.x + inset), int(fhi.maxs.x - inset), 34)])
    groups = [[(px + dx, py + dy) for dx, dy in spiral
               if fhi.mins.x + 24.0 <= px + dx <= fhi.maxs.x - 24.0
               and fhi.mins.y + 24.0 <= py + dy <= fhi.maxs.y - 24.0] for px, py in piles] + [ring]
    for gi, cands in enumerate(groups):
        in_pile = 0
        for x, y in cands:
            if got >= want or (cands is not ring and in_pile >= pile_size[gi]):
                break
            m = heap[k % len(heap)] if cands is ring else pile_stores[gi][in_pile % len(pile_stores[gi])]
            ok = d.put("farmhouse", m, x, y, hz, k * 47.0, lane=False)
            if ok and m == CRATE:
                top = hz + MODEL_BOX[CRATE][1][2]
                for j, (jm, ddx, ddy) in enumerate(((JAR, -6, -6), (JAR, 5, 4), (JUG, -2, 8))[:2 + k % 2]):
                    d.put("farmhouse", jm, x + ddx, y + ddy, top, j * 50.0, check=False)
            if ok:
                got += 1
                k += 1
                in_pile += 1
    # Supper nobody finished, in a drift by the table (loose books and plates
    # spread singly over the floor read as confetti).
    for i, (m, dx, dy, yaw) in enumerate((
            ("p7_debris_trash_paper_plate_01", -70, 58, 10.0), ("p7_debris_trash_paper_plate_01", -84, 70, 130.0),
            ("p7_debris_trash_cup_coffee_02", -96, 56, 50.0), ("p7_cup_coffee_mug", -66, 76, 250.0))):
        d.put("farmhouse", m, cx + dx, cy + dy, hz + RUG_H, yaw)
    for i, (x, y) in enumerate(((fhi.mins.x + 40.0, fhi.mins.y + 220.0),)):
        if d.put("farmhouse", CRATE, x, y, hz, 90.0, lane=False):
            top = hz + MODEL_BOX[CRATE][1][2]
            for j, (m, ddx, ddy) in enumerate(((JAR, -6, -8), (JAR, 0, 0), (JAR, 6, 8), (LAMP, -4, 10))):
                d.put("farmhouse", m, x + ddx, y + ddy, top, j * 40.0, check=False)
    for i, (m, x, y, yaw, zz) in enumerate((
            # The farm's notice board (it looks north at yaw 0, see
            # dmv._mounted), where a third copy of the painting hung.
            ("p7_zm_der2_bulletin_board", fhi.maxs.x, cy - 120.0, 90.0, 60.0),
            # Clear of the west window: at cy + 60 it hung half across the
            # window's opening, in front of the barricade.
            (PICTURE, fhi.mins.x, cy + 150.0, 90.0, 72.0))):
        d.put("farmhouse", m, x, y, hz + zz + MODEL_BOX[m][0][2], yaw, check=False, lane=False)

    # =====================================================================
    # Barn: hay everywhere, feed, tools, the hayloft.
    # =====================================================================
    # The hayloft stands on posts, with a header beam under its edge: a slab
    # with no posts under it reads as floating.
    edge_y = bi.mins.y + plan.loft_depth
    loft_under = loft_top - 16.0
    bp.add_block(Bounds.between((bi.mins.x, edge_y - 10.0, loft_under - 10.0), (bi.maxs.x, edge_y, loft_under)),
                 cm._BEAM, reachable=False, id="barn_loft_header", note="loft header beam")
    for n, px in enumerate((bi.mins.x + 90.0, bi.mins.x + 290.0, bi.centre.x - 20.0, bi.centre.x + 170.0,
                            stair_x - 90.0)):
        if not d.free(px, edge_y - 5.0, bz, 6.0, lane=False):
            continue
        post = Bounds.between((px - 4.0, edge_y - 9.0, bz), (px + 4.0, edge_y - 1.0, loft_under - 10.0))
        bp.add_block(post, cm._BEAM, reachable=False, id=f"barn_loft_post_{n}", note="loft post")
        d.keepouts.append(post.grown(10.0))
    # The walls: a tool rack by the door, a tack board under the hayloft,
    # shelves on the west wall and under the hayloft on the east (bare plank walls
    # read as empty).
    _tool_rack(bp, d, "barn", bi.centre.x + 130.0, bi.centre.x + 330.0, bi.maxs.y, bz, Facing.SOUTH, "barn_tools")
    _tool_rack(bp, d, "barn", bi.mins.x + 100.0, bi.mins.x + 300.0, bi.mins.y, bz, Facing.NORTH, "barn_tack",
               tack=True)
    for ident, box, front in (
            ("barn_shelf_west", Bounds.between((bi.mins.x, bi.maxs.y - 250.0, bz), (bi.mins.x + 24.0, bi.maxs.y - 150.0, bz + 86.0)), (1, 0)),
            ("barn_shelf_east", Bounds.between((bi.maxs.x - 24.0, bi.mins.y + 20.0, bz), (bi.maxs.x, bi.mins.y + 120.0, bz + 86.0)), (-1, 0))):
        cx_, cy_ = box.centre.x, box.centre.y
        if not d.free(cx_, cy_, bz, 30.0, lane=False):
            continue
        tops = _brush_shelf(bp, box, front, ident, (2.0, 30.0, 58.0, 86.0))
        d.keepouts.append(box.grown(6.0))
        for i, (m, dy, t) in enumerate(((JAR, -38, 1), (JAR, -30, 1), (JUG, -16, 1), (LAMP, 10, 1), (BASKETS[0], 32, 1),
                                        ("p7_pot_metal_boiling_lg", -26, 2), (BASKETS[2], 20, 2),
                                        (BASKETS[1], 0, 3), (JAR, 30, 3), (JAR, 38, 3))):
            fit = fit_within(m, cx_, cy_ + dy, i * 30.0, box) if m in MODEL_BOX else None
            if fit is not None:
                d.put("barn", m, fit[0], fit[1], tops[t], fit[2], check=False)
    barn_bales = []
    stacks = ((bi.centre.x - 300, bi.centre.y + 20, False, 3), (bi.centre.x - 300, bi.centre.y + 56, False, 2),
              (bi.centre.x - 230, bi.centre.y + 20, False, 1), (bi.maxs.x - 250, bi.maxs.y - 80, True, 2),
              (bi.maxs.x - 290, bi.maxs.y - 80, True, 1), (bi.centre.x + 60, bi.centre.y + 30, False, 1),
              (bi.centre.x - 80, bi.mins.y + plan.loft_depth + 120, True, 1))
    for i, (x, y, across, stack) in enumerate(stacks):
        barn_bales += _bale(d, "barn", x, y, bz, across=across, stack=stack, yaw=i * 4.0)
    loft_bales = []
    for i, (x, y, across, stack) in enumerate(((bi.mins.x + 60, bi.mins.y + 40, False, 2),
                                               (bi.mins.x + 130, bi.mins.y + 40, False, 1),
                                               (bi.maxs.x - 200, bi.mins.y + 40, False, 2),
                                               (bi.mins.x + 60, bi.mins.y + 200, True, 1),
                                               # The hay in the hayloft (four stacks on
                                               # the west end alone leave the rest bare
                                               # boards): a stepped wall of it along the back
                                               # east of Pack-a-Punch, more on the east end
                                               # clear of the stair head, one set down loose.
                                               (bi.centre.x + 110, bi.mins.y + 40, False, 3),
                                               (bi.centre.x + 170, bi.mins.y + 40, False, 2),
                                               (bi.centre.x + 230, bi.mins.y + 40, False, 3),
                                               (bi.centre.x + 140, bi.mins.y + 105, True, 1),
                                               (bi.centre.x + 205, bi.mins.y + 105, True, 1),
                                               # The east end: against the back wall,
                                               # clear of the east window's keep-out
                                               # (at +170 and +230 they would stand
                                               # over the window, P3).
                                               (bi.maxs.x - 60, bi.mins.y + 40, True, 2),
                                               (bi.maxs.x - 60, bi.mins.y + 100, True, 1),
                                               (bi.mins.x + 260, bi.mins.y + 260, False, 1))):
        loft_bales += _bale(d, "barn", x, y, loft_top, across=across, stack=stack, yaw=i * 4.0)
    # A feed trough by the north wall.
    trough = Bounds.between((bi.mins.x + 170, bi.maxs.y - 34, bz), (bi.mins.x + 290, bi.maxs.y - 4, bz + 26))
    bp.add_block(trough, cm._PLANKS, reachable=False, id="barn_trough", note="feed trough")
    d.keepouts += [b.grown(6.0) for b in barn_bales + loft_bales] + [trough.grown(4.0)]
    barn_items = [
        # Tack and tools in the north-east corner, by the stair foot.
        ("p7_wheel_barrow_street_vendor", bi.centre.x + 200, bi.maxs.y - 250, 30.0),
        ("p7_tools_shovel", bi.centre.x - 120, bi.maxs.y - 160, 20.0),
        ("p7_tools_shovel", bi.centre.x - 100, bi.maxs.y - 170, 50.0),
        # Feed: sacks on a pallet, baskets, barrels by the trough.
        ("p7_pallet_wood_damaged", bi.centre.x - 230, bi.maxs.y - 140, 0.0),
        ("p7_barrel_metal_55gal_blue", bi.mins.x + 330, bi.maxs.y - 30, 0.0),
        ("p7_barrel_metal_55gal_blue", bi.mins.x + 360, bi.maxs.y - 40, 40.0),
        (BASKETS[1], bi.mins.x + 50, bi.maxs.y - 30, 0.0),
        (SACK, bi.mins.x + 310, bi.maxs.y - 80, 20.0),
        # Along the east wall, under the hayloft and by the window.
        (CRATE_LONG, bi.centre.x + 300, bi.mins.y + 330, 90.0),
        ("p7_debris_wood_board_cluster_03", bi.centre.x + 50, bi.maxs.y - 300, 0.0),
        ("p7_debris_wood_board_cluster_04", bi.centre.x - 100, bi.mins.y + 280, 0.0),
        ("p7_gib_chunk_bone_01", bi.centre.x - 20, bi.centre.y + 40, 0.0),
        ("p7_gib_chunk_flesh_01", bi.centre.x + 10, bi.centre.y + 60, 0.0),
        ("p7_foliage_grass_tall_cluster_sml", bi.mins.x + 410, bi.maxs.y - 60, 0.0),
        ("p7_foliage_grass_tall_cluster_sml", bi.maxs.x - 380, bi.maxs.y - 250, 0.0),
        ("p7_foliage_weed_cluster_lrg", bi.centre.x + 120, bi.mins.y + plan.loft_depth + 60, 0.0),
        ("p7_foliage_weed_cluster_lrg", bi.centre.x - 200, bi.mins.y + 180, 0.0),
        (CRATE, bi.centre.x + 250, bi.mins.y + 250, 30.0),
        (CRATE, bi.centre.x - 60, bi.mins.y + 120, 0.0), (CRATE, bi.centre.x - 25, bi.mins.y + 120, 20.0),
        (SACK, bi.centre.x + 60, bi.mins.y + 60, 0.0), (SACK, bi.centre.x + 80, bi.mins.y + 70, 40.0),
        ("p7_pallet_wood_damaged", bi.maxs.x - 60, bi.mins.y + 90, 0.0),
        (LAMP, bi.centre.x + 150, bi.mins.y + 200, 0.0),
    ]
    for m, x, y, yaw in barn_items:
        if d.put("barn", m, x, y, bz, yaw, lane=False, solid=False if "foliage" in m else None):
            if m == "p7_pallet_wood_damaged":
                for j in range(3):
                    d.put("barn", SACK, x - 12 + j * 12, y + (j % 2) * 6, bz + 5.0, 90.0 + j * 10, check=False)
            elif m == "p7_wheel_barrow_street_vendor":
                for j in range(3):
                    _pumpkin(d, "barn", x + 34 + j * 4, y - 20 + j * 24, bz, j * 60.0, 0.95, check=False)
            elif m in BASKETS:
                for j in range(3):
                    d.put("barn", ORANGE, x - 4 + j * 4, y - 6 + j * 6, bz + MODEL_BOX[m][1][2], j * 50.0,
                          1.0, check=False)
    d.put("barn", SACK, trough.centre.x - 30, trough.centre.y, trough.maxs.z, 90.0, check=False)
    d.put("barn", LAMP, trough.centre.x + 30, trough.centre.y, trough.maxs.z, 0.0, check=False)
    for i, (m, x, y) in enumerate(((LAMP, bi.mins.x + 60, bi.mins.y + 120), (CRATE, bi.maxs.x - 60, bi.mins.y + 60),
                                   (CRATE, bi.maxs.x - 60, bi.mins.y + 95), (SACK, bi.centre.x + 150, bi.mins.y + 60),
                                   (PUMPKIN, bi.centre.x + 60, bi.mins.y + 30), (PUMPKIN, bi.centre.x - 300, bi.mins.y + 30),
                                   ("p7_gib_chunk_bone_03", bi.centre.x + 100, bi.mins.y + 250),
                                   (BASKETS[2], bi.mins.x + 200, bi.mins.y + 300),
                                   ("p7_tools_shovel", bi.centre.x + 220, bi.mins.y + 320))):
        d.put("barn", m, x, y, loft_top, i * 45.0, 1.15 if m == PUMPKIN else 1.0, lane=False)
    for box in (barn_bales[2], barn_bales[5], loft_bales[1]):
        d.put("barn", LAMP, box.centre.x, box.centre.y, box.maxs.z, 30.0, check=False)
    d.put("barn", "p7_zm_teddybear", barn_bales[7].centre.x, barn_bales[7].centre.y, barn_bales[7].maxs.z,
          200.0, check=False)
    for box in (barn_bales[4], barn_bales[9]):
        _pumpkin(d, "barn", box.centre.x, box.centre.y, box.maxs.z, 60.0, 1.05, check=False)
    # More barn (P2: it had 85 props): tools and lamps set down along the
    # west wall clear of its window (the wall buy is at centre - 60, the
    # window at centre + 150), feed sacks and crates along the south wall
    # under the hayloft, and pumpkins by the trough.  (Hung on the wall they
    # read as floating, Z44: a placed prop has no hook.)
    for i, (m, y, yaw) in enumerate((("p7_tools_shovel", bi.centre.y + 270.0, 90.0),
                                     ("p7_tools_shovel", bi.centre.y + 300.0, 90.0),
                                     (LAMP, bi.centre.y + 350.0, 0.0),
                                     (LAMP, bi.centre.y - 300.0, 0.0))):
        d.put("barn", m, bi.mins.x + 20.0, y, bz, yaw, lane=False)
    for i, (m, x, y, yaw) in enumerate(((SACK, bi.centre.x + 130, bi.mins.y + 30, 0.0),
                                        (SACK, bi.centre.x + 160, bi.mins.y + 34, 20.0),
                                        (SACK, bi.centre.x + 190, bi.mins.y + 30, 350.0),
                                        (CRATE, bi.centre.x + 240, bi.mins.y + 40, 10.0),
                                        (CRATE, bi.centre.x + 275, bi.mins.y + 40, 350.0),
                                        (PUMPKIN, trough.maxs.x + 30, trough.centre.y - 10, 0.0),
                                        (PUMPKIN, trough.maxs.x + 55, trough.centre.y - 20, 70.0),
                                        (PUMPKIN, trough.mins.x - 30, trough.centre.y - 15, 140.0),
                                        ("p7_book_vintage_open_04_burn", bi.centre.x - 150, bi.centre.y - 60, 30.0),
                                        ("p7_bottle_glass_liquor_01", bi.centre.x + 100, bi.centre.y - 90, 0.0),
                                        (SACK, bi.centre.x + 220, bi.mins.y + 70, 60.0),
                                        (PUMPKIN, bi.centre.x + 210, bi.mins.y + 110, 20.0),
                                        (PUMPKIN, bi.centre.x - 170, bi.maxs.y - 45, 200.0),
                                        (CRATE, bi.centre.x - 200, bi.maxs.y - 40, 5.0))):
        d.put("barn", m, x, y, bz, yaw, 1.05 if m == PUMPKIN else 1.0, lane=False)
    # A heap of pumpkins in from the door: a close spiral, not the 4 x 3
    # grid the render showed (a planted bed, not a pile).
    for i in range(10):
        r, a = (0.0, 0.0) if i == 0 else (20.0 if i < 5 else 38.0, i * (90.0 if i < 5 else 60.0))
        _pumpkin(d, "barn", bi.centre.x + 210 + r * math.cos(math.radians(a)),
                 bi.centre.y + 90 + r * math.sin(math.radians(a)), bz,
                 i * 60.0, 1.05 + 0.1 * (i % 3), lane=False)
    # Barn stores along its walls (120 props against a
    # floor of 150, bare walls): every free spot on a 72 step round the
    # ground floor (the south row under the hayloft) gets, in turn, a two-high hay stack, a lidded crate with a
    # sack against it, or feed sacks on a pallet.  Keep-outs (doors, the
    # wall buy, the machines, the stair) are the dresser's.
    ring = [(x, bi.maxs.y - 34.0) for x in _steps(bi.mins.x + 60.0, bi.maxs.x - 60.0, 72.0)]
    ring += [(bi.mins.x + 34.0, y) for y in _steps(bi.mins.y + 90.0, bi.maxs.y - 90.0, 72.0)]
    ring += [(bi.maxs.x - 34.0, y) for y in _steps(bi.mins.y + 90.0, bi.maxs.y - 90.0, 72.0)]
    ring += [(x, bi.mins.y + 34.0) for x in _steps(bi.mins.x + 96.0, bi.maxs.x - 96.0, 72.0)]
    for k, (x, y) in enumerate(ring):
        across = abs(x - bi.mins.x) < 40.0 or abs(x - bi.maxs.x) < 40.0
        if not d.free(x, y, bz, 34.0, lane=False) or any(
                b.mins.x - 30 <= x <= b.maxs.x + 30 and b.mins.y - 30 <= y <= b.maxs.y + 30 for b in barn_bales):
            continue
        kind = k % 3
        if kind == 0:
            barn_bales += _bale(d, "barn", x, y, bz, across=across, stack=2, yaw=k * 5.0)
        elif kind == 1:
            if d.put("barn", CRATE, x, y, bz, 90.0 if across else 0.0, lane=False):
                d.put("barn", CRATE_LID, x, y, bz + MODEL_BOX[CRATE][1][2], 90.0 if across else 0.0, check=False)
                d.put("barn", SACK, x + (0.0 if across else 30.0), y + (30.0 if across else 0.0), bz, k * 17.0,
                      lane=False)
        else:
            # The pallet is deeper than the ring's inset: 6 more off the wall (Z54).
            x += 6.0 if abs(x - bi.mins.x) < 40.0 else -6.0 if abs(x - bi.maxs.x) < 40.0 else 0.0
            y += 6.0 if abs(y - bi.mins.y) < 40.0 else -6.0 if abs(y - bi.maxs.y) < 40.0 else 0.0
            if d.put("barn", FLATBED, x, y, bz, 90.0 if across else 0.0, lane=False):
                ptop = bz + MODEL_BOX[FLATBED][1][2]
                for j in range(3):
                    dx, dy = (0.0, -14.0 + j * 14.0) if across else (-14.0 + j * 14.0, 0.0)
                    d.put("barn", SACK, x + dx, y + dy, ptop, (0.0 if across else 90.0) + j * 8.0, check=False)
    # The perks are farm drinks (P14): each stock machine gets its stall.
    _dress_perk_stalls(bp, d)
    # The buildings and the yard to stock density (sparse buildings read
    # as empty sets): packed shelves, heaps that climb,
    # things hung overhead (recipes/corn_maze_interiors.py).
    from . import corn_maze_interiors
    INTERIORS.clear()
    INTERIORS.update(corn_maze_interiors.dress(bp, d, plan, fhi=fhi, bi=bi, fi=fi, hz=hz, bz=bz, fz=fz,
                                               loft_top=loft_top, stair_x=stair_x))
    # Grass everywhere but the walkways: the farmyard's paths from the spawn
    # to every gate and door, the heart's from its gate to the scarecrow.
    spawn = (0.0, 150.0)
    fyi = fy.interior
    walkways = {
        "farmyard": [(spawn, (fyi.mins.x, plan.cell_centre(cm.MAZE_ENTRANCE)[1])), (spawn, (0.0, fyi.maxs.y)),
                     (spawn, (0.0, fyi.mins.y)), (spawn, (fyi.maxs.x, plan.lane_y)),
                     (spawn, (stop_x, stop_y))],
        "heart": [((plan.cell_centre(cm.DOOR_HEART[0])[0], hi.mins.y), scarecrow_heart)],
    }
    BACK_ROW[0] = _back_row(d)
    # Every lined face, for the Z89 check (verify.lining): the plants must
    # hide the wall, not just stand along it.
    bp.lined_faces = [(horizontal, face, span, sign, z, z + plan.corn_height, BAND_DEPTH)  # type: ignore[attr-defined]
                      for _zone, horizontal, face, sign, z, spans, _ in _BAND_FACES for span in spans]
    bp.lined_openings = []  # type: ignore[attr-defined]
    for box in BUY_SHEDS:
        record_opening(bp, box, "buy shed")
    GRASS.clear()
    GRASS.update(_grass(d, plan, rooms, maze_walls, spots, walkways))
    d.flush()

    # =====================================================================
    # Light: lanterns in every area (warm); light_rooms tops up with moonlight.
    # =====================================================================
    _lamp(bp, 0.0, 150.0, fz + 160.0, "farmyard", "farmyard_lantern")
    _lamp(bp, stop_x - 60.0, fi.mins.y + 80.0, fz + 140.0, "farmyard", "hayride_stop_lantern")
    _lamp(bp, 430.0, 500.0, fz + 130.0, "farmyard", "farmstand_lantern")
    _lamp(bp, patch_spot[0], patch_spot[1] + 60, pz + 170.0, "patch", "patch_lantern")
    _lamp(bp, hi.centre.x, hi.centre.y, tz + 170.0, "heart", "heart_lantern", colour=(1.0, 0.35, 0.1))
    _lamp(bp, fhi.centre.x, fhi.centre.y, fhi.maxs.z - 40.0, "farmhouse", "farmhouse_lamp")
    _lamp(bp, bi.centre.x, bi.maxs.y - 200.0, bz + 150.0, "barn", "barn_lantern")
    _lamp(bp, bi.centre.x, bi.mins.y + 200.0, loft_top + 150.0, "barn", "loft_lantern")
    OUTSKIRTS.clear()
    OUTSKIRTS.update(_outskirts(bp, plan, rooms))
    # The generator's work light, so the power switch can be found in the
    # corn, and the heart's glow: the harvest moon come down into the corn.
    (gx, gy), _ = _back_wall(plan, spots["power"], passages, 70.0)
    _lamp(bp, gx, gy, power_room.floor_z + 120.0, cm.room_of(spots["power"]), "mazedeep_power_lantern",
          radius=300.0)
    _lamp(bp, hi.centre.x, hi.centre.y + 200.0, tz + 260.0, "heart", "heart_moon", colour=(1.0, 0.62, 0.3),
          radius=900.0)
    # Moonlight down into the maze rows, on every other cell each way (the
    # maze rooms are sunlit, so Z11's 256-unit grid does not apply; these
    # and the lanterns are what lights them besides the sky).
    for cell in cm.maze_cells_all(plan.maze_size):
        if cell[0] % 2 == 0 and cell[1] % 2 == 0:
            key = cm.room_of(cell)
            x, y = plan.cell_centre(cell)
            # Shadowless fill: the maze is large, and only the first 340
            # shadowing lamps keep their shadow.
            bp.place_light(Point(x, y, rooms[key].floor_z + 170.0), colour=cm.MOON, radius=460.0,
                           zone_name=key, shadows=False, id=f"{key}_moon_{cell[0]}_{cell[1]}")
    # The dark between the moon lamps (no dark spots
    # in the maze): the maze's passages are its walk paths, and every dark
    # stretch of them longer than autolamp.DARK_STRETCH gets a trail lantern
    # on the ground beside the corn in its middle (blueprint.autolamp, D7).
    graph = cm.maze_graph(passages)
    bp.walk_paths = [[(*plan.cell_centre(a), rooms[cm.room_of(a)].floor_z),
                      (*plan.cell_centre(b), rooms[cm.room_of(b)].floor_z)]
                     for a in sorted(graph) for b in sorted(graph[a]) if a < b]
    PATH_LANTERNS[0] = len(light_paths(bp, _path_lantern(d, plan, rooms), colour=cm.LANTERN,
                                       radius=PATH_LANTERN_RADIUS, id_prefix="maze_path"))
    d.flush()
    return d
