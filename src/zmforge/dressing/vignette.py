"""Vignettes: small composed groups of props that each tell one micro-story.

``docs/map-design-method.md`` makes every *room* a scene; a vignette is the
same idea at the scale of a corridor bend: 5 to 30 props and a few brushes
arranged so a player reads what happened in one glance (an abandoned picnic,
a lost child's bear and a lamp still burning, a pen where something got in).
A corn maze lined with litter alone reads as empty; it needs props with
character: stories everywhere, not more of the same litter.

A vignette is laid out in a local frame at a :class:`Spot`: ``u`` runs out
from the spot's back line (a wall face, the front of a corn band) into the
open, ``v`` along the back line to the left.  Each kind in :data:`KINDS` has
a one-line story, the spot kinds it fits, and a builder that returns its
parts.  :func:`place_vignette` turns the parts to world space, asks the
map's :class:`Placer` whether every *core* part fits (keep-outs, routes,
windows, interactives: the map's own rules), and either places the whole
vignette or nothing.  Parts that are not core are dropped one by one when
they do not fit.

* :class:`Spot` -- where a vignette may go: a ``bend``, ``dead_end``,
  ``clearing_edge`` or ``wall_face``, its back line, width and depth.
* :data:`KINDS` / :class:`Kind` -- the library (twelve farm-horror kinds).
* :func:`choose_kind` -- a kind that fits the spot and is not repeated
  within *gap* units (no two picnics in one stretch of corn).
* :func:`place_vignette` -- lay it; returns a :class:`Vignette` record
  (kind, story, focus point) or ``None``.
* :func:`add_focus` -- hand a room's best vignettes to its scene, so the
  render cameras aim at them (``render/cameras.py`` ``focus_views``).
* :class:`SimplePlacer` -- a placer for a map with no dresser of its own.

Props come from stock models that link locally first, then our realistic
generated or CC0 props (``zmf_prop_dead_log``, ``zmf_prop_hay_bale``), then
kit props (the pumpkins) only where nothing else exists.  Brushes use
worn, catalogued materials only.  No part carries text (P17).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Callable, Protocol, Sequence

from ..blueprint.elements import FLOATS_ON_PURPOSE
from ..materials import Material
from ..spatial import Bounds, Point

__all__ = [
    "Spot", "Kind", "Vignette", "Placer", "SimplePlacer", "KINDS", "SPOT_KINDS",
    "Item", "Block", "Slant", "Fx", "Glow",
    "choose_kind", "place_vignette", "vignettes_of", "add_focus", "footprint_boxes",
    "WOOD", "IRON", "RUST", "CHECK", "CANVAS", "WAX", "WARM", "DIM",
]

#: Where a vignette may stand.  A *bend* is the wall a player walks straight
#: at before a corridor turns; a *wall_face* is the side of a straight run;
#: a *dead_end* is the closed end of a dead end; a *clearing_edge* is the rim
#: of an open area, facing into it.
SPOT_KINDS = ("bend", "dead_end", "clearing_edge", "wall_face")

WOOD = Material("t7_wood_planks_worn", 64.0)
IRON = Material("t7_metal_worn_iron_dark", 64.0)
RUST = Material("t7_metal_rust_ceiling_01", 64.0)
#: A red check cloth: worn red brick at a small repeat reads as a check
#: (the corn farmhouse rug and the scarecrow's flannel, rendered).
CHECK = Material("t7_brick_worn_red", 12.0)
#: Pale dirty canvas (tent, bedroll edge) and candle wax.
CANVAS = Material("t7_plaster_smooth_dirty_01", 64.0)
WAX = Material("t7_plaster_smooth_dirty_01", 16.0)
#: Light colours: a fire or a lamp flame, and a dying flashlight glow.
WARM = (1.0, 0.5, 0.22)
DIM = (0.95, 0.72, 0.45)

LAMP = "p7_zm_der2_light_hurricane_lamp"
PUMPKIN = "zmf_prop_pumpkin"
JACK = "zmf_prop_jack_o_lantern"


# ---------------------------------------------------------------------------
# Parts, in the local frame (u out from the back line, v along it, z up from
# the ground at the spot).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Item:
    """One prop.  *yaw* is local (0 faces along ``+u`` turned by the
    model's own convention); *on* rests it on an earlier item's top (its
    index in the part list) or a :class:`Block`'s top; *dz* lifts its
    underside off the ground (a blanket).  *core* parts must all fit or the
    vignette is not placed.  *solid* ``None`` lets the map decide."""

    model: str
    u: float
    v: float
    yaw: float = 0.0
    scale: float = 1.0
    on: int | None = None
    dz: float = 0.0
    solid: bool | None = None
    core: bool = False


@dataclass(frozen=True)
class Block:
    """A brush box ``u0..u1 x v0..v1 x z0..z1``.  *top* marks one that
    things rest on (an altar plank, a lamp arm)."""

    u0: float
    v0: float
    z0: float
    u1: float
    v1: float
    z1: float
    material: Material = WOOD
    name: str = "board"
    core: bool = True
    floats: bool = False


@dataclass(frozen=True)
class Slant:
    """A leaning slab (a tent side, a fallen roof, a tipped wagon bed): one
    sheared brush from *low* ``(u, v, z)`` to *high*, *across* half-wide at
    right angles to the lean and *thick* half-thick along it."""

    low: tuple[float, float, float]
    high: tuple[float, float, float]
    across: float
    thick: float
    material: Material = WOOD
    name: str = "slab"
    core: bool = True


@dataclass(frozen=True)
class Fx:
    """A stock effect: ``smoulder`` (smoke and hot ground), ``embers`` or
    ``fire`` (flames, embers, smoke and a light pool)."""

    what: str
    u: float
    v: float
    dz: float = 4.0


@dataclass(frozen=True)
class Glow:
    """An owned light: a lamp still lit, candles, a fire's pool."""

    u: float
    v: float
    dz: float
    colour: tuple[float, float, float] = WARM
    radius: float = 220.0


Part = Item | Block | Slant | Fx | Glow


@dataclass(frozen=True)
class Spot:
    """Where a vignette may go.  ``(x, y, z)`` is the middle of its back
    line on the ground; *yaw* the way it faces (degrees, 0 = +x), from the
    back into the open; *width* the room along the back line; *back* how far
    behind the line parts may reach (into a corn band, never into the wall);
    *reach* how far out into the walk line they may come."""

    x: float
    y: float
    z: float
    yaw: float
    kind: str
    room: str
    width: float = 150.0
    back: float = 45.0
    reach: float = 14.0

    def world(self, u: float, v: float) -> tuple[float, float]:
        a = math.radians(self.yaw)
        c, s = math.cos(a), math.sin(a)
        return self.x + u * c - v * s, self.y + u * s + v * c


@dataclass(frozen=True)
class Kind:
    name: str
    story: str
    fits: tuple[str, ...]
    build: Callable[[random.Random, Spot], list]
    #: The smallest spot it needs: ``(width, back + reach)``.
    needs: tuple[float, float] = (120.0, 55.0)
    #: Where the camera should look, local ``(u, v, z)``.
    focus: tuple[float, float, float] = (-10.0, 0.0, 24.0)
    large: bool = False


@dataclass(frozen=True)
class Vignette:
    """A placed vignette, kept on ``bp.vignettes`` for scenes and review."""

    kind: str
    story: str
    room: str
    spot: str
    focus: tuple[float, float, float]
    props: int
    brushes: int
    lights: int
    fx: int
    boxes: tuple[tuple[float, float, float, float], ...] = field(default=(), repr=False)


class Placer(Protocol):
    """The map's rules, asked by :func:`place_vignette`."""

    def fits(self, room: str, model: str, x: float, y: float, surface: float, yaw: float,
             scale: float, solid: bool | None) -> bool: ...

    def fits_box(self, room: str, box: Bounds) -> bool: ...

    def put(self, room: str, model: str, x: float, y: float, surface: float, yaw: float,
            scale: float, solid: bool | None) -> None: ...

    def reserve(self, room: str, box: Bounds) -> None: ...


# ---------------------------------------------------------------------------
# Helpers the builders share
# ---------------------------------------------------------------------------
def _j(rng: random.Random, amount: float = 4.0) -> float:
    return rng.uniform(-amount, amount)


def _ring(rng, model_choices, cu, cv, r, n, start=0.0, scale=(0.9, 1.2), solid=False) -> list[Item]:
    out = []
    for k in range(n):
        a = math.radians(start + k * 360.0 / n + _j(rng, 12))
        out.append(Item(model_choices[k % len(model_choices)], cu + r * math.cos(a), cv + r * math.sin(a),
                        rng.uniform(0, 360), rng.uniform(*scale), solid=solid))
    return out


# ---------------------------------------------------------------------------
# The library: twelve farm-horror kinds.  Sizes in units; the corn maze's
# small spots give 150 x 60 (a nook 45 into a corn band), its dead ends
# and clearing edges 180 x 150.
# ---------------------------------------------------------------------------
def _picnic(rng, spot):
    parts: list = [Block(-40, -30, 0, -4, 30, 1, CHECK, "blanket", floats=False)]
    parts += [
        Item("p7_box_wood_wine_storage_tan", -30, -17, 10 + _j(rng), on=0, core=True),
        Item("p7_bottle_glass_wine_01", -20, 5, 0, on=0, solid=False),
        Item("p7_debris_trash_paper_plate_01", -13, 14, rng.uniform(0, 360), on=0, solid=False),
        Item("p7_debris_trash_paper_plate_01", -26, 18, rng.uniform(0, 360), on=0, solid=False),
        Item("p7_food_fruit_melon", -12, -4, 30, on=0, solid=False),
        Item("p7_debris_trash_cup_red_02", -9, 24, 0, on=0, solid=False),
        Item("p7_debris_trash_food_box_01", -32, 2, rng.uniform(0, 360), on=0, solid=False),
        # The cooler, knocked aside off the blanket; its melon rolled out.
        Item("p7_crate_plastic_tech_01", -22, 50, 60 + _j(rng, 10), solid=True),
        Item("p7_food_fruit_melon", 4, 40, 0, solid=False),
        Item("p7_food_fruit_banana_bunch", -24, -2, 40, on=0, solid=False),
        Item("p7_bottle_glass_liquor_01", 2, -26, 0, solid=False),
        Item("p7_debris_trash_cup_red_02", 6, 12, 0, solid=False),
    ]
    return parts


def _lost_child(rng, spot):
    return [
        Item("p7_zm_teddybear", -12, 6, 200 + _j(rng, 20), solid=False, core=True),
        Item("p7_clothes_womens_crumpled_01_shirt", -26, -16, rng.uniform(0, 360), solid=False),
        Item(LAMP, -4, -26, rng.uniform(0, 360), solid=False, core=True),
        Glow(-4, -26, 14, DIM, 150.0),
        Item("p7_debris_paper_sheet_01", -34, 24, rng.uniform(0, 360), 0.6, solid=False),
        Item(PUMPKIN, -36, -2, rng.uniform(0, 360), 0.85, solid=False),
        Item("p7_bottle_plastic_16oz_water", 4, 18, 0, solid=False),
        Item("p7_foliage_weed_cluster_med", -18, 34, rng.uniform(0, 360), 1.6, solid=False),
    ]


def _harvest_gone_wrong(rng, spot):
    return [
        Item("p7_tools_shovel", -10, -8, 70 + _j(rng, 15), solid=False, core=True),
        Item("p7_pot_metal_boiling_lg", -28, 16, rng.uniform(0, 360), solid=False, core=True),
        Item("p7_pot_metal_boiling_lg", -12, 32, rng.uniform(0, 360), solid=False),
        Item(PUMPKIN, -22, 34, rng.uniform(0, 360), 0.9, solid=False),
        Item(PUMPKIN, 0, 44, rng.uniform(0, 360), 0.9, solid=False),
        Item(PUMPKIN, -36, -30, rng.uniform(0, 360), 1.0, solid=False),
        Item("p7_gib_chunk_meat_01", -4, 6, rng.uniform(0, 360), 1.4, solid=False),
        Item("p7_gib_chunk_flesh_02", 4, -22, rng.uniform(0, 360), 1.4, solid=False),
        Item("p7_gib_chunk_bone_01", -18, -2, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_debris_wood_board_splinter_02", -30, -8, rng.uniform(0, 360), solid=False),
        Item("p7_debris_wood_board_splinter_01", -38, 22, rng.uniform(0, 360), solid=False),
        Item("p7_box_wood_01_sm", -34, 44, 20 + _j(rng), solid=False),
    ]


def _crow_roost(rng, spot):
    # No stock bird links, so
    # the roost is the posts and what the birds left under them.
    h = (84.0 + _j(rng, 6), 96.0 + _j(rng, 6), 78.0 + _j(rng, 6))
    parts: list = [
        Block(-32, -42, 0, -28, -38, h[0], WOOD, "roost_post"),
        Block(-36, -2, 0, -32, 2, h[1], WOOD, "roost_post"),
        Block(-30, 38, 0, -26, 42, h[2], WOOD, "roost_post"),
        Block(-35, -38, 58, -31, -2, 62, WOOD, "roost_rail", floats=True),
        Block(-43, -9, h[1], -25, 9, h[1] + 2, WOOD, "roost_cap", floats=True),
    ]
    parts += [
        Item(JACK, -34, 0, 180 + _j(rng, 20), 0.9, on=4, solid=False),
        Item("p7_gib_chunk_bone_03", -30, -40, rng.uniform(0, 360), 1.5, on=0, solid=False),
        Item("p7_gib_chunk_bone_01", -10, 10, rng.uniform(0, 360), 1.4, solid=False, core=True),
        Item("p7_gib_chunk_bone_01", -16, -22, rng.uniform(0, 360), 1.4, solid=False),
        Item("p7_gib_chunk_bone_03", -2, -6, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_gib_chunk_meat_02", -20, 26, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_debris_rockychunks_small_07", -4, 28, rng.uniform(0, 360), solid=False),
        Item("p7_3arc_park_leaves_grp_2", -22, -14, rng.uniform(0, 360), solid=False),
    ]
    return parts


def _campfire(rng, spot):
    fu, fv = 22.0, -6.0
    parts: list = [
        # An A-frame tent of two canvas slabs meeting at a ridge.
        Slant((-62, 0, 0), (-38, 0, 46), 34, 1.5, CANVAS, "tent_side"),
        Slant((-14, 0, 0), (-38, 0, 46), 34, 1.5, CANVAS, "tent_side"),
        Item("p7_debris_wood_board_cluster_burn_03", fu, fv, rng.uniform(0, 360), 0.7, solid=False,
             core=True),
        Fx("smoulder", fu, fv, 4.0),
        Glow(fu, fv, 26.0, WARM, 280.0),
        Item("p7_bed_sheet_barrack_03", 2, 40, 90 + _j(rng, 10), solid=False),
        Item("p7_pan_metal_sauce", fu + 26, fv - 20, rng.uniform(0, 360), solid=False),
        Item("p7_pot_metal_boiling_lg", fu - 6, fv + 30, rng.uniform(0, 360), solid=False),
        Item("p7_debris_trash_food_box_01", fu + 14, fv + 34, rng.uniform(0, 360), solid=False),
        Item("p7_bottle_glass_liquor_01", fu + 34, fv + 10, 0, solid=False),
        Item("p7_luggage_cloth_a_lg_green", -8, -40, 70 + _j(rng), solid=True),
        Item("p7_crate_wood_01_short", 40, 52, 15 + _j(rng), solid=True),
        Item(LAMP, 40, 52, rng.uniform(0, 360), on=11, solid=False),
    ]
    parts += _ring(rng, ("p7_debris_rockychunks_small_08", "p7_debris_rockychunks_small_09",
                         "p7_debris_rockychunks_small_12"), fu, fv, 24.0, 7, scale=(0.7, 0.9))
    return parts


def _hay_wagon(rng, spot):
    return [
        # The bed, tipped where its wheel came off: low end on the ground.
        Slant((-24, -60, 0), (-24, 52, 30), 30, 8, WOOD, "wagon_bed"),
        Block(-52, 40, 0, 4, 46, 24, IRON, "wagon_axle"),
        Item("p7_debris_wood_board_cluster_02", 28, -48, rng.uniform(0, 360), solid=False,
             core=True),
        Item("zmf_prop_hay_bale", 24, -10, 70 + _j(rng, 15), solid=True, core=True),
        Item("zmf_prop_hay_bale", 50, 18, 20 + _j(rng, 15), solid=True),
        Item("zmf_prop_hay_bale", -2, -76, 90 + _j(rng, 8), solid=True),
        Item(PUMPKIN, 44, -30, rng.uniform(0, 360), 1.0, solid=False),
        Item(PUMPKIN, 60, 44, rng.uniform(0, 360), 0.9, solid=False),
        Item("p7_debris_wood_board_splinter_03", 12, 30, rng.uniform(0, 360), solid=False),
        Item("p7_debris_wood_board_splinter_01", 40, -64, rng.uniform(0, 360), solid=False),
        Item("p7_foliage_grass_tall_cluster_sml", 64, -8, rng.uniform(0, 360), 0.7, solid=False),
    ]


def _tool_shed(rng, spot):
    return [
        Block(-60, -46, 0, -56, -42, 78, WOOD, "shed_post"),
        Block(-60, 42, 0, -56, 46, 78, WOOD, "shed_post"),
        # The roof came down off its posts: its low edge is in the dirt.
        Slant((-6, 0, 0), (-60, 0, 74), 48, 1.2, RUST, "shed_roof"),
        # Rusted sheet walls (brushes: the stock corrugated sheets are wall
        # fixtures and Z44 wants them on a wall).
        Block(-64, -48, 0, -62, 44, 84, RUST, "shed_wall"),
        Block(-60, 58, 0, -18, 60, 66, RUST, "shed_wall"),
        Item("p7_crate_wood_01_short", -46, -22, 10 + _j(rng), solid=True),
        Item("p7_box_wood_01_long", -46, 20, 90 + _j(rng), solid=True),
        Item("p7_wheel_barrow_street_vendor", 30, 50, 140 + _j(rng, 10), solid=True),
        Item("p7_tools_shovel", 16, -40, 20 + _j(rng, 20), solid=False),
        Item("p7_bag_plastic_soil", 34, -10, rng.uniform(0, 360), solid=False),
        Item("p7_pallet_wood_damaged", 40, -60, 30 + _j(rng), solid=False),
        Item("p7_barrel_metal_55gal_blue", -10, 76, rng.uniform(0, 360), solid=True),
        Item("p7_debris_wood_board_cluster_01", 10, 10, rng.uniform(0, 360), solid=False),
    ]


def _warning_sign(rng, spot):
    # Blank weathered boards on a post: whatever it said is scraped off (P17).
    return [
        Block(-26, -2, 0, -22, 2, 92 + _j(rng, 4), WOOD, "sign_post"),
        Block(-22, -24, 60, -20, 22, 84, WOOD, "sign_board", floats=True),
        Block(-22, -18, 40, -20, 14, 52, WOOD, "sign_board", floats=True),
        Item(JACK, -8, -20, 150 + _j(rng, 20), solid=False, core=True),
        Item("p7_gib_chunk_bone_01", -4, 12, rng.uniform(0, 360), 1.4, solid=False),
        Item("p7_debris_rockychunks_small_05", -12, 22, rng.uniform(0, 360), solid=False),
        Item("p7_debris_paper_sheet_01", 4, 4, rng.uniform(0, 360), 0.5, solid=False),
        Item("p7_foliage_weed_cluster_lrg", -30, 14, rng.uniform(0, 360), 1.6, solid=False),
    ]


def _strawman_remains(rng, spot):
    # Named "strawman", never "_scarecrow_": the Z60 scarecrow assembly rule
    # (ids with _scarecrow_) is for a standing one, and these pieces lie apart.
    return [
        Block(-32, -3, 0, -26, 3, 42 + _j(rng, 4), WOOD, "remains_pole"),
        Block(-24, -52, 0, -18, -10, 6, WOOD, "remains_pole_down"),
        Block(-38, 8, 0, -34, 52, 4, WOOD, "remains_arm"),
        Block(-26, 22, 0, -8, 40, 1, CHECK, "remains_shirt"),
        Item("p7_debris_clothing_pants_01", -2, -28, rng.uniform(0, 360), 0.7, solid=False, core=True),
        Item(PUMPKIN, 4, 8, rng.uniform(0, 360), 0.85, solid=False),
        Item("p7_gib_chunk_flesh_01", 8, 16, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_gib_chunk_flesh_03", 0, 0, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_foliage_grass_tall_cluster_sml", -40, -30, rng.uniform(0, 360), 0.6, solid=False),
        Item("p7_debris_wood_board_splinter_02", -36, -18, rng.uniform(0, 360), solid=False),
    ]


def _pumpkin_shrine(rng, spot):
    parts: list = [
        Item("p7_crate_wood_01_short", -30, -30, 0, solid=True, core=True),
        Item("p7_crate_wood_01_short", -30, 30, 0, solid=True, core=True),
        Block(-44, -46, 31.2, -16, 46, 34, WOOD, "altar_plank", floats=True),
        Item(JACK, -30, -24, 180, 1.0, on=2, solid=False),
        Item(JACK, -32, 2, 180, 1.2, on=2, solid=False),
        Item(JACK, -30, 26, 180, 1.0, on=2, solid=False),
        Item("p7_crate_wood_01_short", -60, 0, 5 + _j(rng), solid=True),
        Item("p7_crate_wood_01_short", -60, 0, _j(rng, 8), on=6, solid=True),
        Item(JACK, -60, 0, 180, 1.1, on=7, solid=False),
        Glow(-20, 0, 44, WARM, 240.0),
    ]
    for k in range(9):
        a = math.radians(-80 + k * 20 + _j(rng, 5))
        parts.append(Item(PUMPKIN, -30 + 62 * math.cos(a), 62 * math.sin(a), rng.uniform(0, 360),
                          rng.uniform(0.85, 1.15), solid=False))
    for k in range(6):
        a = math.radians(-50 + k * 20)
        cu, cv = -30 + 40 * math.cos(a), 40 * math.sin(a)
        h = rng.uniform(5, 10)
        parts.append(Block(cu - 1.2, cv - 1.2, 0, cu + 1.2, cv + 1.2, h, WAX, "candle", core=False))
    return parts


def _animal_pen(rng, spot):
    parts: list = []
    u0, u1, v0, v1 = -62.0, -4.0, -54.0, 54.0
    for u, v in ((u0, v0), (u0, 0), (u0, v1), (u1, v0), (u1, v1), ((u0 + u1) / 2, v0),
                 ((u0 + u1) / 2, v1), (u1, -16), (u1, 22)):
        parts.append(Block(u - 2, v - 2, 0, u + 2, v + 2, 44, WOOD, "pen_post"))
    for z in (16.0, 32.0):
        parts += [Block(u0 - 1, v0 + 2, z, u0 + 1, v1 - 2, z + 4, WOOD, "pen_rail", floats=True),
                  Block(u0 + 2, v0 - 1, z, u1 - 2, v0 + 1, z + 4, WOOD, "pen_rail", floats=True),
                  Block(u0 + 2, v1 - 1, z, u1 - 2, v1 + 1, z + 4, WOOD, "pen_rail", floats=True),
                  Block(u1 - 1, v0 + 2, z, u1 + 1, -18, z + 4, WOOD, "pen_rail", floats=True),
                  Block(u1 - 1, 24, z, u1 + 1, v1 - 2, z + 4, WOOD, "pen_rail", floats=True)]
    parts.append(Block(-58, -40, 0, -48, 0, 10, WOOD, "pen_trough"))
    gore = ("p7_gib_chunk_meat_01", "p7_gib_chunk_meat_03", "p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03",
            "p7_gib_chunk_flesh_02", "p7_gib_chunk_bone_01", "p7_gib_chunk_meat_02", "p7_gib_chunk_bone_03")
    for k, m in enumerate(gore):
        parts.append(Item(m, rng.uniform(-50, -20), rng.uniform(-30, 44), rng.uniform(0, 360), 1.5,
                          solid=False, core=(k == 0)))
    parts += [Item("p7_pot_metal_boiling_lg", -20, 36, rng.uniform(0, 360), solid=False),
              Item("p7_debris_wood_board_splinter_01", 8, 4, rng.uniform(0, 360), solid=False),
              Item("p7_gib_chunk_bone_01", 14, -12, rng.uniform(0, 360), 1.4, solid=False),
              Item("p7_foliage_weed_cluster_lrg", -36, 10, rng.uniform(0, 360), 1.8, solid=False)]
    return parts


def _lantern_stakes(rng, spot):
    return [
        Block(-16, -42, 0, -13, -39, 58, WOOD, "stake"),
        Block(-16, -47, 58, -1, -33, 61, WOOD, "stake_arm", floats=True),
        Item(LAMP, -8, -40.5, rng.uniform(0, 360), on=1, solid=False, core=True),
        Block(-16, 39, 0, -13, 42, 58, WOOD, "stake"),
        Block(-16, 33, 58, -1, 47, 61, WOOD, "stake_arm", floats=True),
        Item(LAMP, -8, 40.5, rng.uniform(0, 360), on=4, solid=False),
        # The middle stake snapped; its lamp lies out.
        Block(-16, -2, 0, -13, 1, 28, WOOD, "stake"),
        Item(LAMP, 2, 10, rng.uniform(0, 360), solid=False),
        Glow(-8, -40, 66, DIM, 200.0),
        Item("p7_foliage_weed_cluster_med", -20, -30, rng.uniform(0, 360), 1.8, solid=False),
        Item("p7_foliage_weed_cluster_lrg", -22, 28, rng.uniform(0, 360), 1.6, solid=False),
    ]


def _lost_luggage(rng, spot):
    return [
        Item("p7_luggage_hardshell_handle_down_white", -24, -10, 80 + _j(rng, 20), solid=True, core=True),
        Item("p7_debris_clothing_piles_01", -8, 16, rng.uniform(0, 360), solid=False),
        Item("p7_debris_clothing_tshirts_01", 2, -30, rng.uniform(0, 360), solid=False),
        Item("p7_clothes_womens_crumpled_02_skirt", -30, 30, rng.uniform(0, 360), solid=False),
        Item("p7_clothes_womens_crumpled_02_pants", 6, 40, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_open_01", -2, -4, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_03", -36, -32, rng.uniform(0, 360), solid=False),
        Item("p7_bottle_plastic_16oz_water", 4, 10, 0, solid=False),
    ]


def _burnt_papers(rng, spot):
    return [
        Item("p7_debris_wood_board_cluster_burn_01", -18, 0, rng.uniform(0, 360), 0.8, solid=False, core=True),
        Fx("embers", -18, 0, 2.0),
        Item("p7_book_vintage_open_03_burn", -2, 18, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_02_burn", -32, -20, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_05_burn", -4, -24, rng.uniform(0, 360), solid=False),
        Item("p7_debris_newspaper_02", 4, 34, rng.uniform(0, 360), 0.8, solid=False),
        Item("p7_debris_newspaper_05", -30, 28, rng.uniform(0, 360), 0.8, solid=False),
        Item("p7_debris_paper_sheet_01", 6, -2, rng.uniform(0, 360), 0.5, solid=False),
        Item(LAMP, -36, 6, rng.uniform(0, 360), solid=False),
    ]


def _spilled_feed(rng, spot):
    return [
        Item("p7_crate_wood_01_short_open", -28, -24, 12 + _j(rng), solid=True, core=True),
        Item("p7_bag_plastic_soil", -30, 8, rng.uniform(0, 360), solid=False),
        Item("p7_bag_plastic_soil", -12, 22, rng.uniform(0, 360), solid=False),
        Item("p7_bag_plastic_soil", 2, -6, rng.uniform(0, 360), solid=False),
        Item("p7_box_wood_wine_storage", -30, 34, 30 + _j(rng), solid=False),
        Item("p7_debris_wood_board_splinter_03", 6, 26, rng.uniform(0, 360), solid=False),
        Item("p7_gib_chunk_bone_01", -6, -36, rng.uniform(0, 360), 1.3, solid=False),
        Item("p7_pot_metal_boiling_lg", -26, -24, rng.uniform(0, 360), on=0, solid=False),
    ]


def _drag_marks(rng, spot):
    # A trail of what was lost, from the walk into the corn.
    trail = ("p7_debris_clothing_pants_01", "p7_gib_chunk_flesh_02", "p7_gib_chunk_meat_03",
             "p7_gib_chunk_bone_01", "p7_gib_chunk_meat_01", "p7_gib_chunk_flesh_03", "p7_gib_chunk_bone_03")
    parts = [Item(m, -2 - k * 6.5 + _j(rng, 2), (k % 2 - 0.5) * 10 + _j(rng, 3), rng.uniform(0, 360),
                  0.8 if k == 0 else 1.4, solid=False, core=(k == 0)) for k, m in enumerate(trail)]
    parts += [Item("p7_clothes_womens_crumpled_01_shirt", -40, 20, rng.uniform(0, 360), solid=False),
              Item(LAMP, 6, -30, rng.uniform(0, 360), solid=False)]
    return parts


KINDS: dict[str, Kind] = {k.name: k for k in (
    Kind("picnic", "A picnic left in a hurry: the blanket still laid, the food out, the cooler kicked over.",
         ("bend", "wall_face", "clearing_edge", "dead_end"), _picnic, (130.0, 60.0), (-20.0, 10.0, 10.0)),
    Kind("lost_child", "A child's bear and jacket in the rows, and a lamp still burning where it fell.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _lost_child, (100.0, 50.0), (-12.0, -6.0, 12.0)),
    Kind("harvest_gone_wrong", "The picking stopped mid-row: tools dropped, buckets over, blood in the stubble.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _harvest_gone_wrong, (120.0, 55.0),
         (-14.0, 8.0, 10.0)),
    Kind("crow_roost", "The crows' posts: whatever was left on them has been picked to the bone.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _crow_roost, (110.0, 50.0), (-24.0, 0.0, 50.0)),
    Kind("campfire", "Somebody camped here to wait for morning; the fire still smoulders, the bedroll is empty.",
         ("dead_end", "clearing_edge"), _campfire, (170.0, 125.0), (0.0, 0.0, 24.0), large=True),
    Kind("hay_wagon", "The hayride's spare wagon lost a wheel and tipped its load into the corn.",
         ("dead_end", "clearing_edge"), _hay_wagon, (170.0, 130.0), (10.0, -10.0, 20.0), large=True),
    Kind("tool_shed", "The farmer's tool shed fell in on itself; his tools are where he left them.",
         ("dead_end", "clearing_edge"), _tool_shed, (170.0, 130.0), (-20.0, 10.0, 36.0), large=True),
    Kind("warning_sign", "A sign stood at the turn once; whatever it warned of, the words are scraped off.",
         ("bend", "wall_face", "clearing_edge"), _warning_sign, (80.0, 45.0), (-20.0, 0.0, 60.0)),
    Kind("strawman_remains", "A scarecrow was torn down here: its clothes scattered, its head smashed.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _strawman_remains, (120.0, 50.0),
         (-14.0, 0.0, 12.0)),
    Kind("pumpkin_shrine", "Someone built a shrine of pumpkins and candles out here, and keeps it lit.",
         ("dead_end", "clearing_edge"), _pumpkin_shrine, (160.0, 110.0), (-30.0, 0.0, 34.0), large=True),
    Kind("animal_pen", "The farm's animal pen: something got in, and nothing got out.",
         ("dead_end", "clearing_edge"), _animal_pen, (130.0, 90.0), (-40.0, 0.0, 20.0), large=True),
    Kind("lost_luggage", "Someone ran with a suitcase and dropped it; the clothes spilled into the rows.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _lost_luggage, (110.0, 50.0), (-14.0, 0.0, 12.0)),
    Kind("burnt_papers", "Someone burned their books and letters here and left before it caught the corn.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _burnt_papers, (110.0, 50.0), (-16.0, 0.0, 8.0)),
    Kind("spilled_feed", "Feed sacks fell off a cart and split; something has been at them.",
         ("bend", "wall_face", "dead_end", "clearing_edge"), _spilled_feed, (110.0, 50.0), (-18.0, 0.0, 16.0)),
    Kind("drag_marks", "Something was dragged off the path into the corn here; bits of it lie along the way.",
         ("bend", "wall_face", "dead_end"), _drag_marks, (100.0, 55.0), (-16.0, 0.0, 6.0)),
    Kind("lantern_stakes", "Lanterns on stakes marked the way through; one stake is snapped, its lamp in the dirt.",
         ("bend", "wall_face", "clearing_edge"), _lantern_stakes, (100.0, 30.0), (-10.0, 0.0, 50.0)),
)}


# ---------------------------------------------------------------------------
# Choosing and placing
# ---------------------------------------------------------------------------
def vignettes_of(bp) -> list[Vignette]:
    return list(getattr(bp, "vignettes", None) or ())


def choose_kind(rng: random.Random, spot: Spot, placed: Sequence[Vignette], *, gap: float = 1000.0,
                large: bool | None = None, exclude: Sequence[str] = (),
                library: "dict[str, Kind] | None" = None) -> list[str]:
    """Kinds that fit *spot* and are not already within *gap* units, the
    least used first (ties shuffled by *rng*).  *large* ``True`` asks for the
    big kinds only (a dead end or a clearing), ``False`` for small ones.
    *library* picks from another set of kinds (the indoor ones,
    :data:`zmforge.dressing.indoor.INDOOR_KINDS`) instead of :data:`KINDS`."""
    near = {v.kind for v in placed if math.hypot(v.focus[0] - spot.x, v.focus[1] - spot.y) < gap}
    used: dict[str, int] = {}
    for v in placed:
        used[v.kind] = used.get(v.kind, 0) + 1
    names = [k.name for k in (KINDS if library is None else library).values()
             if spot.kind in k.fits and k.name not in near and k.name not in exclude
             and (large is None or k.large == large)
             and k.needs[0] <= spot.width + 1e-6 and k.needs[1] <= spot.back + spot.reach + 1e-6]
    rng.shuffle(names)
    names.sort(key=lambda n: used.get(n, 0))
    return names


def _box_of(spot: Spot, u0, v0, z0, u1, v1, z1) -> Bounds:
    pts = [spot.world(u, v) for u in (u0, u1) for v in (v0, v1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return Bounds.between((min(xs), min(ys), spot.z + z0), (max(xs), max(ys), spot.z + z1))


def _model_box(model: str):
    from ..recipes.props import MODEL_BOX

    return MODEL_BOX.get(model)


def _reach(model: str, scale: float) -> float:
    box = _model_box(model)
    if box is None:
        return 0.0
    (a, b, _), (c, d, _) = box
    return math.hypot(max(-a, c), max(-b, d)) * scale


def _extents(model: str, scale: float, yaw: float) -> tuple[float, float]:
    """Half extents along the spot's ``u`` and ``v`` of *model* turned by the
    local *yaw* (its x axis at *yaw* from ``u``)."""
    box = _model_box(model)
    cx = max(abs(box[0][0]), abs(box[1][0])) * scale
    cy = max(abs(box[0][1]), abs(box[1][1])) * scale
    c, s = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
    return cx * c + cy * s, cx * s + cy * c


#: Ground litter that settles a vignette into the ground round its edge:
#: ``(model, (scale_lo, scale_hi))``, walk-through, all stock.
SETTLE = (("p7_foliage_weed_cluster_lrg", (1.4, 2.0)), ("p7_foliage_weed_cluster_med", (1.6, 2.2)),
          ("p7_3arc_park_leaves_grp_2", (0.9, 1.3)), ("p7_debris_rockychunks_small_07", (0.8, 1.2)),
          ("p7_debris_rockychunks_small_10", (0.8, 1.2)), ("p7_debris_wood_board_splinter_01", (1.0, 1.0)),
          ("p7_foliage_grass_tall_cluster_sml", (0.5, 0.75)))


def footprint_boxes(v: Vignette) -> list[tuple[float, float, float, float]]:
    """The vignette's parts' plan boxes ``(x0, y0, x1, y1)``."""
    return list(v.boxes)


def place_vignette(bp, kind: str, spot: Spot, rng: random.Random, placer: Placer, *,
                   ident: str, settle: tuple[int, int] = (4, 8),
                   library: "dict[str, Kind] | None" = None,
                   settle_models: "Sequence[tuple[str, tuple[float, float]]] | None" = None
                   ) -> Vignette | None:
    """Lay one *kind* vignette at *spot* through *placer*; all or nothing for
    its core parts.  Returns the record (also appended to ``bp.vignettes``)
    or ``None`` when a core part does not fit.  *library* looks *kind* up in
    another set of kinds than :data:`KINDS`; *settle_models* replaces the
    outdoor :data:`SETTLE` litter (an indoor floor gets paper and plaster,
    not weeds)."""
    from .fx import burning, embers, smouldering
    from .fixtures import sheared_bar

    k = (KINDS if library is None else library)[kind]
    settle_from = SETTLE if settle_models is None else tuple(settle_models)
    parts = k.build(rng, spot)
    half_w = spot.width / 2.0
    # Resolve every part to world space and test it.
    tops: dict[int, float] = {}
    plan: list[tuple] = []
    for n, part in enumerate(parts):
        if isinstance(part, Item):
            box = _model_box(part.model)
            if box is None:
                ok = False
            else:
                r = _reach(part.model, part.scale)
                eu, ev = _extents(part.model, part.scale, part.yaw)
                surface = spot.z + part.dz if part.on is None else tops.get(part.on)
                inside = (part.u - eu >= -spot.back - 1e-6 and part.u + eu <= spot.reach + 1e-6
                          and abs(part.v) + ev <= half_w + 1e-6)
                x, y = spot.world(part.u, part.v)
                yaw = (spot.yaw + part.yaw) % 360.0
                ok = surface is not None and inside
                if ok and part.on is None:
                    ok = placer.fits(spot.room, part.model, x, y, surface, yaw, part.scale, part.solid)
                if ok:
                    tops[n] = surface + (box[1][2] - box[0][2]) * part.scale
                    plan.append(("item", part, x, y, surface, yaw, r))
            if not ok and part.core:
                return None
        elif isinstance(part, Block):
            inside = (min(part.u0, part.u1) >= -spot.back - 1e-6 and max(part.u0, part.u1) <= spot.reach + 1e-6
                      and max(abs(part.v0), abs(part.v1)) <= half_w + 1e-6)
            bx = _box_of(spot, part.u0, part.v0, part.z0, part.u1, part.v1, part.z1)
            ok = inside and placer.fits_box(spot.room, bx)
            if ok:
                tops[n] = spot.z + part.z1
                plan.append(("block", part, bx))
            elif part.core:
                return None
        elif isinstance(part, Slant):
            us = (part.low[0], part.high[0])
            vs = (part.low[1], part.high[1])
            lean_u = abs(part.high[0] - part.low[0]) >= abs(part.high[1] - part.low[1])
            du, dv = (part.thick, part.across) if lean_u else (part.across, part.thick)
            bx = _box_of(spot, min(us) - du, min(vs) - dv, min(part.low[2], part.high[2]),
                         max(us) + du, max(vs) + dv, max(part.low[2], part.high[2]))
            inside = (min(us) - du >= -spot.back - 1e-6 and max(us) + du <= spot.reach + 1e-6
                      and max(abs(v) for v in vs) + dv <= half_w + 1e-6)
            ok = inside and placer.fits_box(spot.room, bx)
            if ok:
                plan.append(("slant", part, bx, du, dv))
            elif part.core:
                return None
        else:
            plan.append(("other", part))
    # Settle it: a little ground litter round the parts, in the spot's own
    # rectangle and off every placed part.
    taken = [(e[2], e[3], e[6]) for e in plan if e[0] == "item"]
    taken += [((e[2].mins.x + e[2].maxs.x) / 2, (e[2].mins.y + e[2].maxs.y) / 2,
               max(e[2].maxs.x - e[2].mins.x, e[2].maxs.y - e[2].mins.y) / 2)
              for e in plan if e[0] in ("block", "slant")]
    for _ in range(rng.randint(*settle)):
        model, (s0, s1) = settle_from[rng.randrange(len(settle_from))]
        scale = rng.uniform(s0, s1)
        r = _reach(model, scale)
        u = rng.uniform(-spot.back + r, spot.reach - r) if spot.back + spot.reach > 2 * r else 0.0
        v = rng.uniform(-half_w + r, half_w - r)
        x, y = spot.world(u, v)
        if any(math.hypot(x - tx, y - ty) < tr + r * 0.6 for tx, ty, tr in taken):
            continue
        yaw = rng.uniform(0, 360)
        if placer.fits(spot.room, model, x, y, spot.z, yaw, scale, False):
            plan.append(("item", Item(model, u, v, 0.0, scale, solid=False), x, y, spot.z, yaw, r))
            taken.append((x, y, r))
    # Commit.
    props = brushes = lights = fx = 0
    boxes: list[tuple[float, float, float, float]] = []    # what the corn is trimmed from
    reserved: list[tuple[float, float, float, float]] = []
    top_z = spot.z
    for n, entry in enumerate(plan):
        what = entry[0]
        if what == "item":
            _, part, x, y, surface, yaw, r = entry
            placer.put(spot.room, part.model, x, y, surface, yaw, part.scale, part.solid)
            props += 1
            box = _model_box(part.model)
            tall = (box[1][2] - box[0][2]) * part.scale
            reserved.append((x - r, y - r, x + r, y + r))
            if part.solid or tall > 8.0:          # low litter can lie among the corn
                boxes.append((x - r, y - r, x + r, y + r))
            top_z = max(top_z, surface + tall)
        elif what == "block":
            _, part, bx = entry
            bp.add_block(bx, part.material, contents=("detail",), reachable=False,
                         id=f"{ident}_{part.name}_{n}",
                         note=FLOATS_ON_PURPOSE if part.floats else f"vignette {kind}")
            brushes += 1
            boxes.append((bx.mins.x, bx.mins.y, bx.maxs.x, bx.maxs.y))
            reserved.append(boxes[-1])
            top_z = max(top_z, bx.maxs.z)
        elif what == "slant":
            _, part, bx, du, dv = entry
            lo = (*spot.world(part.low[0], part.low[1]), spot.z + part.low[2])
            hi = (*spot.world(part.high[0], part.high[1]), spot.z + part.high[2])
            # sheared_bar's halves are world x and y: turn the local ones.
            turned = round(spot.yaw / 90.0) % 2 == 1
            hx, hy = (dv, du) if turned else (du, dv)
            sheared_bar(bp, f"{ident}_{part.name}_{n}", lo, hi, hx, part.material, half_y=hy,
                        note=f"vignette {kind}")
            brushes += 1
            boxes.append((bx.mins.x, bx.mins.y, bx.maxs.x, bx.maxs.y))
            reserved.append(boxes[-1])
            top_z = max(top_z, bx.maxs.z)
        else:
            part = entry[1]
            x, y = spot.world(part.u, part.v)
            at = Point(x, y, spot.z + part.dz)
            if isinstance(part, Fx):
                made = (smouldering(bp, at, note=f"{ident} {kind}") if part.what == "smoulder" else
                        [embers(bp, at, note=f"{ident} {kind}")] if part.what == "embers" else
                        burning(bp, at, note=f"{ident} {kind}"))
                fx += sum(1 for m in made if m.__class__.__name__ == "AmbientFx")
            else:
                bp.place_light(at, colour=part.colour, radius=part.radius, shadows=False,
                               zone_name=getattr(placer, "zone_of", lambda r: None)(spot.room),
                               id=f"{ident}_glow_{n}")
                lights += 1
    if reserved:
        x0 = min(b[0] for b in reserved)
        y0 = min(b[1] for b in reserved)
        x1 = max(b[2] for b in reserved)
        y1 = max(b[3] for b in reserved)
        placer.reserve(spot.room, Bounds.between((x0 - 6, y0 - 6, spot.z), (x1 + 6, y1 + 6, max(top_z, spot.z + 8))))
    fu, fv, fz = k.focus
    focus = (*spot.world(fu, fv), spot.z + fz)
    record = Vignette(kind, k.story, spot.room, spot.kind, focus, props, brushes, lights, fx, tuple(boxes))
    placed = getattr(bp, "vignettes", None)
    if placed is None:
        placed = []
        bp.vignettes = placed
    placed.append(record)
    return record


def add_focus(bp, room, points: Sequence[tuple[float, float, float]]) -> None:
    """Add *points* to *room*'s declared scene focus (the render cameras aim
    a view at each).  No scene, no change."""
    key = getattr(room, "id", room)
    scenes = getattr(bp, "scenes", None) or []
    for n, s in enumerate(scenes):
        if s.room == key:
            scenes[n] = replace(s, focus=tuple(s.focus) + tuple(tuple(map(float, p)) for p in points))
            return


class SimplePlacer:
    """A placer for a map with no dresser: refuses parts inside *keepouts*
    or over an interactive, and places props through ``bp.place_props``
    (call :meth:`flush` at the end)."""

    def __init__(self, bp, keepouts: Sequence[Bounds] = ()):
        self.bp = bp
        self.keepouts = list(keepouts)
        self.pending: dict[str, list] = {}

    def _clear(self, x0, y0, x1, y1, z) -> bool:
        for b in self.keepouts:
            if b.mins.x < x1 and b.maxs.x > x0 and b.mins.y < y1 and b.maxs.y > y0 \
                    and b.mins.z - 8 <= z <= b.maxs.z:
                return False
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return not self.bp.interactive_blocks(Point(cx, cy, z + 8.0), (x1 - x0) / 2, (y1 - y0) / 2)

    def fits(self, room, model, x, y, surface, yaw, scale, solid) -> bool:
        r = _reach(model, scale)
        return self._clear(x - r, y - r, x + r, y + r, surface)

    def fits_box(self, room, box) -> bool:
        return self._clear(box.mins.x, box.mins.y, box.maxs.x, box.maxs.y, box.mins.z)

    def put(self, room, model, x, y, surface, yaw, scale, solid) -> None:
        lo = _model_box(model)[0]
        item = (model, Point(x, y, surface - lo[2] * scale), yaw, scale)
        self.pending.setdefault(room, []).append(item if solid is None else (*item, solid))

    def reserve(self, room, box) -> None:
        self.keepouts.append(box)

    def flush(self) -> None:
        for room, items in self.pending.items():
            for n in range(0, len(items), 40):
                self.bp.place_props(items[n:n + 40], id=f"vignette_{room}_{n // 40}")
        self.pending.clear()
