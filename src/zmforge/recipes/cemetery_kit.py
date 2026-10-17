"""Brushwork for a graveyard: headstones, crosses, mausoleums, iron fences.

The install carries no headstone, cross, tomb, dead tree or iron-fence model
among the ones this package has measured (``recipes.props.MODEL_BOX``, 511
entries, grepped for grave/tomb/cross/fence/tree/candle), so the
things that make a cemetery a cemetery are built in this module out of world brushes in
the stock surfaces :mod:`zmforge.materials` has seen compile.  Every builder
is one function, takes the ground height it stands on, and adds its blocks
under one id prefix, so a test can count them and a caller can find them.

This package converts its own CC0 headstone, cross, iron
fence and pumpkin models (``zmf_prop_*``, :mod:`zmforge.props.library`), and
:mod:`zmforge.recipes.cemetery_dressing` places those first.  The builders
here stay for what the models cannot do: the readable epitaph stones, graves
whose model would straddle two terrain cells, fence cells too steep for a
64-unit panel, and the piers the panels hang between.

Each builder buries its base ``BURY`` units below the ground it is given, so
a headstone on a slope has no daylight under its downhill edge.  Callers pass
the *lowest* ground under the footprint
(:func:`zmforge.surfaces.hills.lowest_under`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..blueprint.model import Blueprint
from ..materials import Material
from ..spatial import Bounds, Facing

__all__ = [
    "BURY",
    "STONE",
    "MOSS_BRICK",
    "WET_BRICK",
    "WET_STONE",
    "DARK_WET",
    "weathered",
    "DARK_STONE",
    "TRIM",
    "SLAB",
    "IRON",
    "BLACK",
    "WOOD",
    "DIRT",
    "GROUND",
    "GRASS",
    "PATH",
    "COBBLE",
    "MUD",
    "FLAGSTONE",
    "TEXTURE_PIXELS",
    "terrain_texture_scale",
    "BRICK",
    "PANEL",
    "PEW_WOOD",
    "Epitaph",
    "headstone",
    "cross",
    "obelisk",
    "grave_mound",
    "open_grave",
    "mausoleum",
    "fence_run",
    "fence_gate",
    "fence_pier",
    "dead_tree",
    "lantern_post",
    "candle",
    "pew",
    "altar",
    "sarcophagus",
    "niche_wall",
    "sconce",
    "gate_piers",
]

#: How far every base goes into the ground it stands on.
BURY = 6.0

#: Headstones, benches, urns, angels and tomb fronts: speckled grey granite
#: (tan travertine reads as cardboard).
STONE = Material("t7_stone_marble_tile_4x4", 48.0)
#: The perimeter walls: layered, streaked old masonry, and the dark coursed
#: blocks of their piers and copings (dressing.boundary_wall).
WALL_STONE = Material("t7_concrete_bunker_layered_02", 128.0)
PIER_STONE = Material("t7_stone_slate_tile_grey", 64.0)
#: Weathered mixes (flat teal-grey everywhere reads as
#: unweathered): old brown brick streaked wet and
#: green, worn red brick, stained wet stone and dark wet stone.
MOSS_BRICK = Material("t7_brick_worn_heavy_grout_brown_wet", 96.0)
WET_BRICK = Material("t7_brick_worn_dirty_red_wet", 96.0)
WET_STONE = Material("t7_concrete_wall_weathered_01_wet", 128.0)
DARK_WET = Material("t7_concrete_bare_dark_01_wet", 96.0)
#: What a stone set piece may weather to, picked per object (``weathered``).
STONE_WEATHER = (STONE, STONE, WET_STONE, DARK_WET)
DARK_STONE = Material("t7_concrete_wall_dark_01", 64.0)
TRIM = Material("t7_concrete_trim_beveled_03", 32.0)
SLAB = Material("t7_concrete_slabs_interlocked", 128.0)
IRON = Material("t7_metal_worn_iron_dark", 32.0)
BLACK = Material("t7_metal_black_trim_01", 16.0)
WOOD = Material("t7_wood_planks_worn", 64.0)
DIRT = Material("t7_rock_sand_crumbled_medium_golden", 64.0)
GROUND = Material("t7_dirt_grassy_forest_ground", 128.0)
#: The outdoor ground and crypt floors (a flat grey floor read as
#: unfinished in game).  Scales: the lawn at 96, the size the 924 stock
#: brush faces that carry it use (grepped over ``map_source``); the rest have
#: no stock brush to copy and are set so one repeat is 8-11 texels a unit,
#: the density the lawn and the stock terrain meshes run at.
GRASS = Material("t7_grass_lawn_medium_small_green", 96.0)
#: The walks: rocky dirt (2048 px colour map).
PATH = Material("t7_dirt_rocky_01", 256.0)
#: The forecourt inside the front gate and before the shed door.
COBBLE = Material("t7_rock_cobblestone_round", 96.0)
#: The spoil round the open grave.
MUD = Material("t7_mud_ground_dirt_wet_01", 128.0)
#: The crypt's floors (2048 px colour map).
FLAGSTONE = Material("t7_stone_flagstone_floor", 192.0)

#: Width in pixels of each terrain material's colour map, read off the
#: ``_c.tif`` headers under ``texture_assets/t7_materials``.
TEXTURE_PIXELS: Mapping[str, int] = {
    GROUND.name: 1024,
    GRASS.name: 1024,
    PATH.name: 2048,
    MUD.name: 1024,
    COBBLE.name: 1024,
}


def terrain_texture_scale(material: Material) -> float:
    """The ``texture_scale`` a mesh terrain in *material* needs.

    A mesh patch's ``t`` coordinates are texels, not repeats: the stock
    terrain meshes carry ``t`` = 8 or 16 x world X
    (``_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map:41``,
    ``_prefabs/zm/zm_giant/zm_giant_geo.map``), where the emitter's default
    128 wrote X / 128 -- a thousand times too small, so the whole of a
    hillside showed one smeared texel: flat grey ground.  ``planar_uv`` divides by the scale, so the scale
    is world units per texel: one repeat (``material.scale``) over the
    image's width.
    """
    return float(material.scale) / float(TEXTURE_PIXELS[material.name])
BRICK = Material("t7_brick_worn_heavy_grout_red", 96.0)
#: Older, finer brick for the crypt's walls.
OLD_BRICK = Material("t7_brick_worn_red", 96.0)
PANEL = Material("t7_wood_panel_01", 64.0)
PEW_WOOD = Material("t7_wood_veneer_sugarpine_matte", 64.0)


@dataclass(frozen=True)
class Epitaph:
    """A headstone a player can read: its name line and what it says."""

    key: str
    name: str
    lines: tuple[str, ...]


def weathered(material, ident: str):
    """Grey granite weathers per object: the same stone for every piece of
    one headstone, bench or tomb (keyed by its ident's stem), a mix across
    the ground (``STONE_WEATHER``)."""
    if material is not STONE:
        return material
    import zlib

    stem = ident.rsplit("_", 1)[0]
    return STONE_WEATHER[zlib.crc32(stem.encode()) % len(STONE_WEATHER)]


def _box(bp: Blueprint, x0, y0, z0, x1, y1, z1, material, ident: str, **kw):
    return bp.add_block(
        Bounds.between((min(x0, x1), min(y0, y1), z0), (max(x0, x1), max(y0, y1), z1)),
        weathered(material, ident), id=ident, **kw,
    )


def _along(facing: Facing, half_w: float, half_d: float) -> tuple[float, float]:
    """Half extents (x, y) of a slab ``2*half_w`` wide facing ``facing``."""
    if facing in (Facing.NORTH, Facing.SOUTH):
        return half_w, half_d
    return half_d, half_w


def headstone(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
              ident: str, width: float = 28.0, height: float = 40.0,
              material: Material = STONE) -> None:
    """A tablet on a plinth: 2 blocks."""
    base = ground - BURY
    px, py = _along(facing, width / 2.0 + 4.0, 8.0)
    _box(bp, x - px, y - py, base, x + px, y + py, ground + 6.0, TRIM, f"{ident}_plinth")
    tx, ty = _along(facing, width / 2.0, 4.0)
    _box(bp, x - tx, y - ty, ground + 6.0, x + tx, y + ty, ground + 6.0 + height,
         material, f"{ident}_tablet")


def cross(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
          ident: str, height: float = 64.0, material: Material = DARK_STONE) -> None:
    """A stone cross on a stepped base: 4 blocks."""
    base = ground - BURY
    _box(bp, x - 14, y - 14, base, x + 14, y + 14, ground + 8.0, TRIM, f"{ident}_base")
    _box(bp, x - 4, y - 4, ground + 8.0, x + 4, y + 4, ground + height, material,
         f"{ident}_post")
    arm_z = ground + height * 0.62
    ax, ay = _along(facing, 18.0, 4.0)
    if facing in (Facing.NORTH, Facing.SOUTH):
        _box(bp, x - ax, y - ay, arm_z, x - 4, y + ay, arm_z + 8, material, f"{ident}_arm_a")
        _box(bp, x + 4, y - ay, arm_z, x + ax, y + ay, arm_z + 8, material, f"{ident}_arm_b")
    else:
        _box(bp, x - ax, y - ay, arm_z, x + ax, y - 4, arm_z + 8, material, f"{ident}_arm_a")
        _box(bp, x - ax, y + 4, arm_z, x + ax, y + ay, arm_z + 8, material, f"{ident}_arm_b")


def obelisk(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
            height: float = 128.0) -> None:
    """A tall needle on a three-step base: 5 blocks."""
    base = ground - BURY
    _box(bp, x - 24, y - 24, base, x + 24, y + 24, ground + 8, TRIM, f"{ident}_step0")
    _box(bp, x - 18, y - 18, ground + 8, x + 18, y + 18, ground + 16, STONE, f"{ident}_step1")
    _box(bp, x - 11, y - 11, ground + 16, x + 11, y + 11, ground + 16 + height * 0.8,
         DARK_STONE, f"{ident}_shaft")
    _box(bp, x - 7, y - 7, ground + 16 + height * 0.8, x + 7, y + 7, ground + 16 + height * 0.95,
         DARK_STONE, f"{ident}_neck")
    _box(bp, x - 3, y - 3, ground + 16 + height * 0.95, x + 3, y + 3, ground + 16 + height,
         DARK_STONE, f"{ident}_tip")


def grave_mound(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
                ident: str) -> None:
    """The long low heap in front of a headstone: 1 block, 6 units proud, so it
    is walked over as a kerb."""
    hx, hy = _along(facing, 14.0, 36.0)
    _box(bp, x - hx, y - hy, ground - BURY, x + hx, y + hy, ground + 6.0, DIRT, ident)


def open_grave(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
               length: float = 96.0, width: float = 48.0, rim: float = 16.0) -> tuple[float, float, float, float]:
    """A dug grave: a rim of spoil round a bare pit, the long axis north-south.

    The pit floor is the ground itself (the caller flattens it); the rim is
    ``rim`` high, a step, so anyone can climb in and back out.
    Returns the pit's inner rectangle ``(x0, y0, x1, y1)``.
    """
    x0, x1 = x - width / 2.0, x + width / 2.0
    y0, y1 = y - length / 2.0, y + length / 2.0
    t = 16.0
    base = ground - BURY
    # The rim is walkable and no higher than a step, so a player -- and a
    # zombie -- steps over it into the pit and back out (Z25, Z46).
    _box(bp, x0 - t, y0 - t, base, x1 + t, y0, ground + rim, MUD, f"{ident}_rim_s",
         walkable=True)
    _box(bp, x0 - t, y1, base, x1 + t, y1 + t, ground + rim, MUD, f"{ident}_rim_n",
         walkable=True)
    _box(bp, x0 - t, y0, base, x0, y1, ground + rim, MUD, f"{ident}_rim_w", walkable=True)
    # The spoil heap: everything dug out, piled on the east side.
    _box(bp, x1, y0, base, x1 + t, y1, ground + rim, MUD, f"{ident}_rim_e", walkable=True)
    _box(bp, x1 + t, y0 + 12, base, x1 + t + 28, y1 - 12, ground + rim + 10, MUD,
         f"{ident}_spoil")
    return x0, y0, x1, y1


def mausoleum(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
              ident: str, width: float = 176.0, depth: float = 224.0,
              height: float = 168.0) -> dict[str, float]:
    """A family tomb: plinth, body, four columns, a stepped roof and an iron
    door on the front, all solid.  ``(x, y)`` is the centre of the plinth;
    the door is on the ``facing`` side.  Returns where the door plate is.
    """
    hx, hy = _along(facing, width / 2.0, depth / 2.0)
    base = ground - BURY
    top_plinth = ground + 16.0
    _box(bp, x - hx - 16, y - hy - 16, base, x + hx + 16, y + hy + 16, top_plinth,
         TRIM, f"{ident}_plinth")
    body_top = top_plinth + height
    _box(bp, x - hx + 16, y - hy + 16, top_plinth, x + hx - 16, y + hy - 16, body_top,
         SLAB, f"{ident}_body")
    # Columns at the four corners, proud of the body.
    for n, (cx, cy) in enumerate(((x - hx, y - hy), (x + hx - 16, y - hy),
                                  (x - hx, y + hy - 16), (x + hx - 16, y + hy - 16))):
        _box(bp, cx, cy, top_plinth, cx + 16, cy + 16, body_top, STONE, f"{ident}_col{n}")
    # Roof: an entablature and two setbacks.
    _box(bp, x - hx - 8, y - hy - 8, body_top, x + hx + 8, y + hy + 8, body_top + 16,
         TRIM, f"{ident}_roof0")
    _box(bp, x - hx + 8, y - hy + 8, body_top + 16, x + hx - 8, y + hy - 8, body_top + 32,
         DARK_STONE, f"{ident}_roof1")
    _box(bp, x - hx + 32, y - hy + 32, body_top + 32, x + hx - 32, y + hy - 32, body_top + 44,
         DARK_STONE, f"{ident}_roof2")
    # The iron door, on the front face, and the name plate over it.
    fx = {Facing.NORTH: 0.0, Facing.SOUTH: 0.0, Facing.EAST: 1.0, Facing.WEST: -1.0}[facing]
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0, Facing.EAST: 0.0, Facing.WEST: 0.0}[facing]
    front = (x + fx * (hx - 16), y + fy * (hy - 16))
    if fy:
        _box(bp, front[0] - 32, front[1], top_plinth, front[0] + 32, front[1] + fy * 4,
             top_plinth + 104, IRON, f"{ident}_door")
        _box(bp, front[0] - 44, front[1], top_plinth + 116, front[0] + 44, front[1] + fy * 4,
             top_plinth + 136, STONE, f"{ident}_plate")
    else:
        _box(bp, front[0], front[1] - 32, top_plinth, front[0] + fx * 4, front[1] + 32,
             top_plinth + 104, IRON, f"{ident}_door")
        _box(bp, front[0], front[1] - 44, top_plinth + 116, front[0] + fx * 4, front[1] + 44,
             top_plinth + 136, STONE, f"{ident}_plate")
    return {
        "door_x": front[0] + fx * 24.0,
        "door_y": front[1] + fy * 24.0,
        "ground": ground,
        "top": body_top + 44,
    }


def fence_run(bp: Blueprint, x0: float, y0: float, x1: float, y1: float, ground_at, *,
              ident: str, height: float = 52.0, pitch: float = 20.0) -> int:
    """A wrought-iron fence along an axis-aligned line: a post every
    ``pitch`` with a spear tip, and top and bottom rails per span, each span
    seated on the ground under it (``ground_at(x, y)`` -> world Z).

    52 units: taller than the 39-unit jump, so a fence is a wall to a player.
    Returns the number of blocks laid.
    """
    horizontal = abs(y1 - y0) < 1e-6
    length = abs(x1 - x0) if horizontal else abs(y1 - y0)
    count = max(1, int(length // pitch))
    step = length / count
    laid = 0
    for n in range(count + 1):
        t = n * step
        px = min(x0, x1) + t if horizontal else x0
        py = y0 if horizontal else min(y0, y1) + t
        g = ground_at(px, py)
        _box(bp, px - 2, py - 2, g - BURY, px + 2, py + 2, g + height, BLACK,
             f"{ident}_post{n}")
        _box(bp, px - 1, py - 1, g + height, px + 1, py + 1, g + height + 6, IRON,
             f"{ident}_tip{n}")
        laid += 2
        if n < count:
            nx = px + step if horizontal else px
            ny = py if horizontal else py + step
            g2 = min(g, ground_at(nx, ny))
            for k, z in enumerate((g2 + 8.0, g + height - 8.0)):
                if horizontal:
                    _box(bp, px + 2, py - 1, z, nx - 2, py + 1, z + 2, IRON,
                         f"{ident}_rail{n}_{k}")
                else:
                    _box(bp, px - 1, py + 2, z, px + 1, ny - 2, z + 2, IRON,
                         f"{ident}_rail{n}_{k}")
                laid += 1
    return laid


def fence_pier(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
               height: float = 64.0) -> None:
    """A square stone pier with a cap: what the iron fence panels (the
    ``zmf_prop_fence_iron`` model) stand between.  2 blocks."""
    _box(bp, x - 6, y - 6, ground - BURY, x + 6, y + 6, ground + height, STONE, f"{ident}_post")
    _box(bp, x - 8, y - 8, ground + height, x + 8, y + 8, ground + height + 4, TRIM,
         f"{ident}_cap")


def fence_gate(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
               ident: str, width: float = 192.0, height: float = 176.0,
               against_wall: bool = True) -> None:
    """The big decorative iron gate: two stone piers, bars, a top rail and an
    arch bar.  With ``against_wall`` the bars stand flat against a wall
    behind them (the gate is shut, and says so)."""
    hx, hy = _along(facing, width / 2.0, 4.0)
    base = ground - BURY
    if facing in (Facing.EAST, Facing.WEST):
        for n, py in enumerate((y - width / 2.0 - 32, y + width / 2.0)):
            _box(bp, x - 16, py, base, x + 16, py + 32, ground + height + 32, STONE,
                 f"{ident}_pier{n}")
            _box(bp, x - 20, py - 4, ground + height + 32, x + 20, py + 36,
                 ground + height + 40, TRIM, f"{ident}_cap{n}")
        bars = int(width // 16)
        for n in range(bars):
            by = y - width / 2.0 + 8 + n * 16
            _box(bp, x - 2, by - 2, base, x + 2, by + 2, ground + height, BLACK,
                 f"{ident}_bar{n}")
        _box(bp, x - 3, y - width / 2.0, ground + height - 12, x + 3, y + width / 2.0,
             ground + height - 6, IRON, f"{ident}_rail_top")
        _box(bp, x - 3, y - width / 2.0, ground + 20, x + 3, y + width / 2.0,
             ground + 26, IRON, f"{ident}_rail_low")
        _box(bp, x - 3, y - width / 4.0, ground + height, x + 3, y + width / 4.0,
             ground + height + 20, IRON, f"{ident}_arch")
    else:
        for n, px in enumerate((x - width / 2.0 - 32, x + width / 2.0)):
            _box(bp, px, y - 16, base, px + 32, y + 16, ground + height + 32, STONE,
                 f"{ident}_pier{n}")
            _box(bp, px - 4, y - 20, ground + height + 32, px + 36, y + 20,
                 ground + height + 40, TRIM, f"{ident}_cap{n}")
        bars = int(width // 16)
        for n in range(bars):
            bx = x - width / 2.0 + 8 + n * 16
            _box(bp, bx - 2, y - 2, base, bx + 2, y + 2, ground + height, BLACK,
                 f"{ident}_bar{n}")
        _box(bp, x - width / 2.0, y - 3, ground + height - 12, x + width / 2.0, y + 3,
             ground + height - 6, IRON, f"{ident}_rail_top")
        _box(bp, x - width / 2.0, y - 3, ground + 20, x + width / 2.0, y + 3,
             ground + 26, IRON, f"{ident}_rail_low")
        _box(bp, x - width / 4.0, y - 3, ground + height, x + width / 4.0, y + 3,
             ground + height + 20, IRON, f"{ident}_arch")
    del hx, hy


#: Branch pattern of a dead tree: (height fraction, direction, length, rise).
_BRANCHES = (
    (0.45, (1, 0), 64.0, 24.0),
    (0.55, (0, 1), 52.0, 32.0),
    (0.66, (-1, 0), 72.0, 20.0),
    (0.74, (0, -1), 48.0, 40.0),
    (0.84, (1, 0), 40.0, 28.0),
    (0.9, (-1, 0), 36.0, 32.0),
)


def dead_tree(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
              height: float = 256.0, turn: int = 0) -> int:
    """A bare, crooked tree: a trunk that narrows twice and six branches, each
    one limb out and a twig up at its end.  ``turn`` rotates the branch
    pattern by quarter turns so no two trees in a row match.  Returns the
    number of blocks."""
    laid = 0
    base = ground - BURY
    sections = ((14.0, 0.0, 0.4), (10.0, 0.4, 0.75), (6.0, 0.75, 1.0))
    for n, (half, lo, hi) in enumerate(sections):
        _box(bp, x - half, y - half, base if n == 0 else ground + height * lo,
             x + half, y + half, ground + height * hi, WOOD, f"{ident}_trunk{n}")
        laid += 1
    # Roots: two low flares.
    _box(bp, x - 26, y - 6, base, x + 26, y + 6, ground + 10, WOOD, f"{ident}_root0")
    _box(bp, x - 6, y - 26, base, x + 6, y - 10, ground + 8, WOOD, f"{ident}_root1")
    laid += 2
    for n, (frac, (dx, dy), length, rise) in enumerate(_BRANCHES):
        for _ in range(turn % 4):
            dx, dy = -dy, dx
        z = ground + height * frac
        trunk_half = 10.0 if frac < 0.75 else 6.0
        sx, sy = x + dx * trunk_half, y + dy * trunk_half
        ex, ey = sx + dx * length, sy + dy * length
        if dx:
            _box(bp, sx, y - 3, z, ex, y + 3, z + 6, WOOD, f"{ident}_limb{n}")
            _box(bp, ex - 3 * dx if dx > 0 else ex, y - 2, z + 6,
                 ex if dx > 0 else ex + 3, y + 2, z + 6 + rise, WOOD, f"{ident}_twig{n}")
        else:
            _box(bp, x - 3, sy, z, x + 3, ey, z + 6, WOOD, f"{ident}_limb{n}")
            _box(bp, x - 2, ey - 3 * dy if dy > 0 else ey, z + 6,
                 x + 2, ey if dy > 0 else ey + 3, z + 6 + rise, WOOD, f"{ident}_twig{n}")
        laid += 2
    return laid


def lantern_post(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
                 height: float = 80.0) -> float:
    """An iron post with a cross-arm for a lantern.  Returns the Z the lantern
    model's underside rests on (the top of the post's cap)."""
    _box(bp, x - 3, y - 3, ground - BURY, x + 3, y + 3, ground + height, BLACK,
         f"{ident}_post")
    _box(bp, x - 8, y - 8, ground + height, x + 8, y + 8, ground + height + 2, IRON,
         f"{ident}_cap")
    return ground + height + 2


def candle(bp: Blueprint, x: float, y: float, surface: float, *, ident: str,
           height: float = 8.0) -> float:
    """A church candle: a 2-unit stick of wax.  Returns the wick's Z."""
    _box(bp, x - 1, y - 1, surface, x + 1, y + 1, surface + height, STONE, ident)
    return surface + height


def pew(bp: Blueprint, x0: float, x1: float, y: float, floor: float, *, ident: str,
        facing: Facing = Facing.EAST) -> None:
    """A church pew running north-south, ``facing`` east or west: seat, back
    and two ends."""
    back = -1.0 if facing is Facing.EAST else 1.0
    del x1
    sx0 = x0
    sx1 = x0 + 20.0
    # 120 long end to end: a gap between two pews no longer than the
    # 128-unit run Scale_Standards.pdf allows under full clearance (N5).
    _box(bp, sx0, y - 56, floor + 16, sx1, y + 56, floor + 20, PEW_WOOD, f"{ident}_seat")
    bx = sx0 if back < 0 else sx1 - 4
    _box(bp, bx, y - 56, floor + 20, bx + 4, y + 56, floor + 40, PEW_WOOD, f"{ident}_back")
    for n, ey in enumerate((y - 60, y + 56)):
        _box(bp, sx0, ey, floor, sx1, ey + 4, floor + 36, PANEL, f"{ident}_end{n}")


def altar(bp: Blueprint, wall_x: float, y: float, floor: float, *, ident: str,
          length: float = 128.0) -> float:
    """A stone altar against an east wall at ``wall_x``, long axis
    north-south, on a one-step dais in front of it -- flush, so there is no
    dead-end slot behind it.  Returns the table top's Z."""
    _box(bp, wall_x - 104, y - length / 2 - 32, floor, wall_x, y + length / 2 + 32, floor + 8,
         TRIM, f"{ident}_dais", walkable=True)
    _box(bp, wall_x - 44, y - length / 2, floor + 8, wall_x, y + length / 2, floor + 40,
         STONE, f"{ident}_body")
    _box(bp, wall_x - 48, y - length / 2 - 4, floor + 40, wall_x, y + length / 2 + 4, floor + 44,
         DARK_STONE, f"{ident}_top")
    return floor + 44


def sarcophagus(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
                length: float = 104.0) -> float:
    """A stone coffin on a plinth, long axis east-west.  Returns its lid's Z."""
    _box(bp, x - length / 2 - 8, y - 28, floor, x + length / 2 + 8, y + 28, floor + 8,
         TRIM, f"{ident}_plinth")
    _box(bp, x - length / 2, y - 20, floor + 8, x + length / 2, y + 20, floor + 36,
         STONE, f"{ident}_box")
    _box(bp, x - length / 2 - 4, y - 24, floor + 36, x + length / 2 + 4, y + 24, floor + 42,
         DARK_STONE, f"{ident}_lid")
    return floor + 42


def niche_wall(bp: Blueprint, x0: float, x1: float, y_wall: float, floor: float, *,
               facing: Facing, ident: str, rows: int = 3, pitch: float = 64.0,
               depth: float = 20.0) -> list[tuple[float, float, float]]:
    """Burial niches (loculi) along a wall running east-west: shelves that
    stand ``depth`` out from the wall at ``y_wall``, ``rows`` high, with a
    divider every ``pitch``.  ``facing`` is NORTH or SOUTH, the way the
    shelves open.  Returns a shelf-top point per niche ``(x, y, z)`` for
    whatever is laid in it."""
    sign = 1.0 if facing is Facing.NORTH else -1.0
    y_in = y_wall + sign * depth
    ya, yb = min(y_wall, y_in), max(y_wall, y_in)
    tops = []
    count = max(1, int((x1 - x0) // pitch))
    for r in range(rows):
        z = floor + 24 + r * 36
        _box(bp, x0, ya, z, x1, yb, z + 4, DARK_STONE, f"{ident}_shelf{r}")
        for c in range(count):
            tops.append((x0 + (c + 0.5) * (x1 - x0) / count, (ya + yb) / 2.0, z + 4))
    for c in range(count + 1):
        dx = x0 + c * (x1 - x0) / count
        lo, hi = (dx, dx + 4) if c < count else (dx - 4, dx)
        _box(bp, lo, ya, floor, hi, yb, floor + 24 + rows * 36, BRICK, f"{ident}_div{c}")
    return tops


def sconce(bp: Blueprint, x: float, y: float, z: float, *, facing: Facing, ident: str) -> tuple[float, float, float]:
    """An iron torch bracket on a wall at (x, y) -- the wall face -- at height
    ``z``, sticking out ``facing``: a back plate, an arm and a cup.  Returns
    where the flame is."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    if fx:
        _box(bp, x, y - 5, z - 10, x + fx * 2, y + 5, z + 10, IRON, f"{ident}_plate")
        _box(bp, x + fx * 2, y - 1, z - 1, x + fx * 12, y + 1, z + 1, BLACK, f"{ident}_arm")
        _box(bp, x + fx * 10, y - 3, z + 1, x + fx * 16, y + 3, z + 7, IRON, f"{ident}_cup")
        return (x + fx * 13, y, z + 14)
    _box(bp, x - 5, y, z - 10, x + 5, y + fy * 2, z + 10, IRON, f"{ident}_plate")
    _box(bp, x - 1, y + fy * 2, z - 1, x + 1, y + fy * 12, z + 1, BLACK, f"{ident}_arm")
    _box(bp, x - 3, y + fy * 10, z + 1, x + 3, y + fy * 16, z + 7, IRON, f"{ident}_cup")
    return (x, y + fy * 13, z + 14)


def gate_piers(bp: Blueprint, opening, ground: float, *, into: Facing, ident: str,
               height: float = 176.0) -> None:
    """Two stone gate piers with caps, one either side of a doorway, standing
    against the wall on the ``into`` side -- what makes a bought door read as
    a cemetery gate.  ``opening`` is the doorway's box."""
    box = opening
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(into, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(into, 0.0)
    if fx:
        face = box.maxs.x if fx > 0 else box.mins.x
        for n, (y0, y1) in enumerate(((box.mins.y - 40, box.mins.y - 8),
                                      (box.maxs.y + 8, box.maxs.y + 40))):
            _box(bp, face, y0, ground - BURY, face + fx * 32, y1, ground + height, STONE,
                 f"{ident}_pier{n}")
            _box(bp, face, y0 - 4, ground + height, face + fx * 36, y1 + 4, ground + height + 10,
                 TRIM, f"{ident}_cap{n}")
    else:
        face = box.maxs.y if fy > 0 else box.mins.y
        for n, (x0, x1) in enumerate(((box.mins.x - 40, box.mins.x - 8),
                                      (box.maxs.x + 8, box.maxs.x + 40))):
            _box(bp, x0, face, ground - BURY, x1, face + fy * 32, ground + height, STONE,
                 f"{ident}_pier{n}")
            _box(bp, x0 - 4, face, ground + height, x1 + 4, face + fy * 36, ground + height + 10,
                 TRIM, f"{ident}_cap{n}")


def stone_bench(bp: Blueprint, x: float, y: float, grounds: tuple[float, float], *,
                facing: Facing, ident: str, length: float = 64.0) -> None:
    """A stone bench centred on (x, y), its seat looking ``facing``: two legs
    each seated on its own ground (``grounds``: under the left and the right
    leg, looking out from the seat), a slab seat 16 above the higher and a
    low back -- 4 blocks."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    seat = max(grounds) + 16.0
    half = length / 2.0
    # "left" and "right" along the bench: -/+ the axis it runs along
    for n, (g, s) in enumerate(zip(grounds, (-1.0, 1.0))):
        c = s * (half - 7.0)
        lx, ly = (x + c, y) if fy else (x, y + c)
        hx, hy = _along(facing, 5.0, 7.0)
        _box(bp, lx - hx, ly - hy, g - BURY, lx + hx, ly + hy, seat, TRIM, f"{ident}_leg{n}")
    sx, sy = _along(facing, half, 9.0)
    _box(bp, x - sx, y - sy, seat, x + sx, y + sy, seat + 4.0, STONE, f"{ident}_seat")
    bx, by = x - fx * 7.0, y - fy * 7.0
    kx, ky = _along(facing, half, 2.0)
    _box(bp, bx - kx, by - ky, seat + 4.0, bx + kx, by + ky, seat + 20.0, STONE, f"{ident}_back")


def urn(bp: Blueprint, x: float, y: float, ground: float, *, ident: str,
        height: float = 44.0) -> None:
    """A stone funeral urn on a square plinth, 32 across: 4 blocks."""
    h = height
    _box(bp, x - 14, y - 14, ground - BURY, x + 14, y + 14, ground + h * 0.4, TRIM,
         f"{ident}_plinth")
    _box(bp, x - 5, y - 5, ground + h * 0.4, x + 5, y + 5, ground + h * 0.52, STONE,
         f"{ident}_foot")
    _box(bp, x - 10, y - 10, ground + h * 0.52, x + 10, y + 10, ground + h * 0.9, STONE,
         f"{ident}_bowl")
    _box(bp, x - 12, y - 12, ground + h * 0.9, x + 12, y + 12, ground + h, STONE,
         f"{ident}_lip")


def angel(bp: Blueprint, x: float, y: float, ground: float, *, facing: Facing,
          ident: str) -> None:
    """A mourning angel looking ``facing`` from a plinth 44 across: a robed
    figure, its head, and two wings spread behind the shoulders -- 6 blocks,
    about 120 tall."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    _box(bp, x - 22, y - 22, ground - BURY, x + 22, y + 22, ground + 26, TRIM,
         f"{ident}_plinth")
    _box(bp, x - 18, y - 18, ground + 26, x + 18, y + 18, ground + 30, STONE, f"{ident}_step")
    rx, ry = _along(facing, 9.0, 7.0)
    _box(bp, x - rx, y - ry, ground + 30, x + rx, y + ry, ground + 96, STONE, f"{ident}_robe")
    _box(bp, x - 5, y - 5, ground + 96, x + 5, y + 5, ground + 108, STONE, f"{ident}_head")
    # the wings: thin slabs behind the shoulders, reaching out and up
    bx, by = x - fx * 8.0, y - fy * 8.0
    for n, s in enumerate((-1.0, 1.0)):
        if fx:
            y0, y1 = sorted((by + s * 6.0, by + s * 24.0))
            _box(bp, bx - 2, y0, ground + 52, bx + 2, y1, ground + 118, STONE,
                 f"{ident}_wing{n}")
        else:
            x0, x1 = sorted((bx + s * 6.0, bx + s * 24.0))
            _box(bp, x0, by - 2, ground + 52, x1, by + 2, ground + 118, STONE,
                 f"{ident}_wing{n}")


# ---------------------------------------------------------------------------
# Crypt furniture: the install has no skull, long-bone, chain,
# candelabra or wreath model, so these are small brushes.  Each takes the
# wall it hangs on as (``wall``: the face's y for a NORTH/SOUTH facing, its x
# for EAST/WEST) and a range ``a0..a1`` along it.
# ---------------------------------------------------------------------------
def _wall_box(bp: Blueprint, wall: float, a0: float, a1: float, out0: float, out1: float,
              z0: float, z1: float, facing: Facing, material, ident: str):
    """A box standing ``out0..out1`` proud of a wall face looking ``facing``."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    if fy:
        return _box(bp, a0, wall + fy * out0, z0, a1, wall + fy * out1, z1, material, ident)
    return _box(bp, wall + fx * out0, a0, z0, wall + fx * out1, a1, z1, material, ident)


def _on_wall(wall: float, along: float, out: float, facing: Facing) -> tuple[float, float]:
    """The plan point ``out`` in front of a wall face at ``along``."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    return (along, wall + fy * out) if fy else (wall + fx * out, along)


def niche_run(bp: Blueprint, a0: float, a1: float, wall: float, floor: float, *,
              facing: Facing, ident: str, rows: int = 3, pitch: float = 64.0,
              depth: float = 20.0) -> list[tuple[float, float, float]]:
    """:func:`niche_wall` for a wall of any facing (east and west walls too).
    Returns a shelf-top point per niche ``(x, y, z)``, bottom row first."""
    tops = []
    count = max(1, int((a1 - a0) // pitch))
    for r in range(rows):
        z = floor + 24 + r * 36
        _wall_box(bp, wall, a0, a1, 0.0, depth, z, z + 4, facing, DARK_STONE, f"{ident}_shelf{r}")
        for c in range(count):
            x, y = _on_wall(wall, a0 + (c + 0.5) * (a1 - a0) / count, depth / 2.0, facing)
            tops.append((x, y, z + 4))
    for c in range(count + 1):
        da = a0 + c * (a1 - a0) / count
        lo, hi = (da, da + 4) if c < count else (da - 4, da)
        _wall_box(bp, wall, lo, hi, 0.0, depth, floor, floor + 24 + rows * 36, facing, BRICK,
                  f"{ident}_div{c}")
    return tops


def loculi(bp: Blueprint, a0: float, a1: float, wall: float, z0: float, *, facing: Facing,
           ident: str, rows: int = 2, pitch: float = 56.0, height: float = 32.0,
           opened=frozenset()) -> list[tuple[float, float, float]]:
    """Burial slots high in a wall, ``rows`` deep from ``z0`` up: each sealed
    by a stone slab with an iron name plate, except the (row, column) cells
    in ``opened``, which are broken open onto a sill.  A cornice runs under
    each row.  Returns a sill-top point per opened cell ``(x, y, z)``."""
    count = max(1, int((a1 - a0) // pitch))
    step = (a1 - a0) / count
    sills = []
    for r in range(rows):
        zb = z0 + r * (height + 10.0)
        _wall_box(bp, wall, a0, a1, 0.0, 5.0, zb - 4, zb, facing, TRIM, f"{ident}_cornice{r}")
        for c in range(count):
            lo, hi = a0 + c * step + 4, a0 + (c + 1) * step - 4
            mid = (lo + hi) / 2.0
            if (r, c) in opened:
                _wall_box(bp, wall, lo, hi, 0.0, 14.0, zb, zb + 3, facing, DARK_STONE,
                          f"{ident}_sill{r}_{c}")
                _wall_box(bp, wall, lo - 3, lo, 0.0, 4.0, zb, zb + height, facing, STONE,
                          f"{ident}_jamb{r}_{c}a")
                _wall_box(bp, wall, hi, hi + 3, 0.0, 4.0, zb, zb + height, facing, STONE,
                          f"{ident}_jamb{r}_{c}b")
                x, y = _on_wall(wall, mid, 8.0, facing)
                sills.append((x, y, zb + 3))
            else:
                _wall_box(bp, wall, lo, hi, 0.0, 2.0, zb, zb + height, facing, STONE,
                          f"{ident}_slab{r}_{c}")
                _wall_box(bp, wall, mid - 9, mid + 9, 2.0, 3.0, zb + height / 2 - 3,
                          zb + height / 2 + 3, facing, IRON, f"{ident}_plate{r}_{c}")
    return sills


def skull(bp: Blueprint, x: float, y: float, z: float, *, facing: Facing, ident: str) -> None:
    """A skull resting at (x, y) on ``z``, looking ``facing``: cranium, jaw
    and two dark eye sockets -- 4 blocks, 8 tall."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    hx, hy = _along(facing, 3.0, 3.5)
    _box(bp, x - hx, y - hy, z + 2, x + hx, y + hy, z + 8, STONE, f"{ident}_cranium")
    jx, jy = _along(facing, 2.0, 1.5)
    cx, cy = x + fx * 2.0, y + fy * 2.0
    _box(bp, cx - jx, cy - jy, z, cx + jx, cy + jy, z + 2, STONE, f"{ident}_jaw")
    for n, s in enumerate((-1.5, 1.5)):
        ex, ey = (x + s, y + fy * 3.5) if fy else (x + fx * 3.5, y + s)
        ox, oy = _along(facing, 0.75, 0.5)
        _box(bp, ex - ox, ey - oy, z + 4, ex + ox, ey + oy, z + 6, BLACK, f"{ident}_eye{n}")


def long_bones(bp: Blueprint, x: float, y: float, z: float, *, facing: Facing, ident: str,
               count: int = 4, length: float = 22.0) -> float:
    """Long bones (shins) stacked like firewood at (x, y) on ``z``, lying
    along the wall a ``facing`` shelf is on: a shaft and two knuckles each,
    two to a layer.  Returns the stack's top."""
    top = z
    for k in range(count):
        layer, slot = divmod(k, 2)
        off = (slot - 0.5) * 4.0 + (layer % 2) * 1.0
        bz = z + layer * 3.0
        cx, cy = (x + (layer % 2) * 1.5, y + off) if facing in (Facing.NORTH, Facing.SOUTH) \
            else (x + off, y + (layer % 2) * 1.5)
        sx, sy = _along(facing, length / 2.0 - 3.0, 1.0)
        _box(bp, cx - sx, cy - sy, bz, cx + sx, cy + sy, bz + 2, STONE, f"{ident}_{k}_shaft")
        for e, s in enumerate((-1.0, 1.0)):
            kx, ky = (cx + s * (length / 2.0 - 1.5), cy) if facing in (Facing.NORTH, Facing.SOUTH) \
                else (cx, cy + s * (length / 2.0 - 1.5))
            _box(bp, kx - 1.5, ky - 1.5, bz, kx + 1.5, ky + 1.5, bz + 3, STONE,
                 f"{ident}_{k}_knuckle{e}")
        top = bz + 3
    return top


def chain(bp: Blueprint, x: float, y: float, z_top: float, *, length: float, ident: str) -> None:
    """An iron chain hanging from ``z_top`` at (x, y): links 5 tall, each
    turned a quarter from the last, with a hook plate at the top."""
    _box(bp, x - 2, y - 2, z_top - 2, x + 2, y + 2, z_top, IRON, f"{ident}_hook")
    for k in range(max(1, int(length // 4))):
        hx, hy = (1.5, 0.5) if k % 2 else (0.5, 1.5)
        _box(bp, x - hx, y - hy, z_top - 2 - (k + 1) * 4 - 1, x + hx, y + hy, z_top - 2 - k * 4,
             IRON, f"{ident}_link{k}")


def stair_rail(bp: Blueprint, x0: float, y: float, floor: float, *, steps: int, run: float,
               rise: float, ident: str, height: float = 34.0, first: int = 0) -> None:
    """An iron handrail stepping down a flight that rises westward from
    ``x0 + steps * run`` to ``x0`` (tread ``s`` spans ``x0 + s*run`` onward
    at ``floor + rise * (steps - s)``): a 2-wide bar ``height`` over each
    tread from ``first`` down, at ``y``."""
    for s in range(first, steps):
        tz = floor + rise * (steps - s)
        _box(bp, x0 + s * run, y - 1, tz + height, x0 + (s + 1) * run, y + 1, tz + height + 2,
             BLACK, f"{ident}_bar{s}")
        # the drop to the next tread down, so the steps of the bar join
        _box(bp, x0 + (s + 1) * run - 2, y - 1, tz + height - rise, x0 + (s + 1) * run,
             y + 1, tz + height, BLACK, f"{ident}_drop{s}")


def candelabra(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
               height: float = 52.0) -> list[tuple[float, float, float]]:
    """A standing iron candelabrum: foot, stem and a cross arm with three
    cups.  Returns the cup tops for :func:`candle`."""
    _box(bp, x - 7, y - 7, floor, x + 7, y + 7, floor + 2, IRON, f"{ident}_foot")
    _box(bp, x - 1, y - 1, floor + 2, x + 1, y + 1, floor + height, BLACK, f"{ident}_stem")
    _box(bp, x - 12, y - 1, floor + height, x + 12, y + 1, floor + height + 2, BLACK,
         f"{ident}_arm")
    cups = []
    for n, dx in enumerate((-11.0, 0.0, 11.0)):
        _box(bp, x + dx - 2, y - 2, floor + height + 2, x + dx + 2, y + 2, floor + height + 4,
             IRON, f"{ident}_cup{n}")
        cups.append((x + dx, y, floor + height + 4))
    return cups


def name_lintel(bp: Blueprint, a0: float, a1: float, wall: float, z: float, *,
                facing: Facing, ident: str) -> None:
    """A carved stone lintel over a doorway (bottom at ``z``) with an iron
    name plate on its face."""
    _wall_box(bp, wall, a0, a1, 0.0, 6.0, z, z + 14, facing, TRIM, f"{ident}_stone")
    mid = (a0 + a1) / 2.0
    _wall_box(bp, wall, mid - 28, mid + 28, 6.0, 7.0, z + 3, z + 11, facing, IRON,
              f"{ident}_plate")


def wreath(bp: Blueprint, wall: float, along: float, z: float, *, facing: Facing,
           ident: str, radius: float = 9.0) -> None:
    """A dried funeral wreath hung flat on a wall, centred at ``along``, ``z``:
    a ring of eight brown tufts and a black ribbon under it."""
    import math as _m
    for k in range(8):
        a = k * _m.pi / 4.0
        da, dz = radius * _m.cos(a), radius * _m.sin(a)
        _wall_box(bp, wall, along + da - 2.5, along + da + 2.5, 0.0, 3.0, z + dz - 2.5,
                  z + dz + 2.5, facing, DIRT, f"{ident}_tuft{k}")
    _wall_box(bp, wall, along - 1.5, along + 1.5, 0.0, 1.0, z - radius - 12, z - radius - 2.5,
              facing, BLACK, f"{ident}_ribbon")


def tunnel_mouth(bp: Blueprint, wall: float, a0: float, a1: float, floor: float, top: float, *,
                 facing: Facing, ident: str) -> None:
    """Shoring round a hole broken through a wall (``a0..a1`` along it, up to
    ``top``): a timber post each side and a beam across, standing on the
    wall's inside face ``facing`` the room, and broken courses of brick
    jutting from the wall each side."""
    for n, (lo, hi) in enumerate(((a0 - 10, a0 - 2), (a1 + 2, a1 + 10))):
        _wall_box(bp, wall, lo, hi, 0.0, 8.0, floor, top, facing, WOOD, f"{ident}_post{n}")
    _wall_box(bp, wall, a0 - 12, a1 + 12, 0.0, 9.0, top, top + 10, facing, WOOD, f"{ident}_beam")
    for n, (lo, hi, z0, z1, out) in enumerate((
            (a0 - 34, a0 - 12, floor + 40, floor + 52, 6.0),
            (a0 - 28, a0 - 12, floor + 70, floor + 80, 4.0),
            (a1 + 12, a1 + 36, floor + 30, floor + 42, 7.0),
            (a1 + 12, a1 + 26, floor + 84, floor + 94, 5.0))):
        _wall_box(bp, wall, lo, hi, 0.0, out, z0, z1, facing, OLD_BRICK, f"{ident}_course{n}")


# ---------------------------------------------------------------------------
# Interior furniture for the shed, the vault and the chapel (brush, so the
# layout check can measure every top that props are set on).
# ---------------------------------------------------------------------------
def plank_shelves(bp: Blueprint, a0: float, a1: float, wall: float, floor: float, *,
                  facing: Facing, ident: str, boards=(22.0, 46.0, 70.0, 94.0),
                  depth: float = 20.0) -> list[float]:
    """Wooden shelving on a wall, ``a0..a1`` along it: two uprights and a
    plank per board height.  Returns each plank's top Z, lowest first."""
    tops = []
    for n, h in enumerate(boards):
        _wall_box(bp, wall, a0, a1, 0.0, depth, floor + h - 3.0, floor + h, facing, WOOD,
                  f"{ident}_board{n}")
        tops.append(floor + h)
    for n, (lo, hi) in enumerate(((a0 - 4, a0), (a1, a1 + 4))):
        _wall_box(bp, wall, lo, hi, 0.0, depth, floor, floor + boards[-1] + 4.0, facing, WOOD,
                  f"{ident}_upright{n}")
    return tops


def tool_rack(bp: Blueprint, a0: float, a1: float, wall: float, floor: float, *,
              facing: Facing, ident: str) -> None:
    """A groundskeeper's tool rack: a plank rail on the wall with a rake, a
    pickaxe, a hoe and a broom stood up against it, heads up."""
    _wall_box(bp, wall, a0, a1, 0.0, 3.0, floor + 58, floor + 64, facing, WOOD, f"{ident}_rail")
    step = (a1 - a0) / 4.0
    for n, kind in enumerate(("rake", "pick", "hoe", "broom")):
        a = a0 + (n + 0.5) * step
        # the handle, leaning on the rail
        _wall_box(bp, wall, a - 1, a + 1, 4.0, 6.0, floor, floor + 70, facing, WOOD,
                  f"{ident}_{kind}_handle")
        if kind == "rake":
            _wall_box(bp, wall, a - 9, a + 9, 3.0, 7.0, floor + 70, floor + 72, facing, IRON,
                      f"{ident}_rake_head")
            for t in range(5):
                ta = a - 8 + t * 4
                _wall_box(bp, wall, ta - 0.5, ta + 0.5, 4.5, 5.5, floor + 72, floor + 76,
                          facing, IRON, f"{ident}_rake_tine{t}")
        elif kind == "pick":
            _wall_box(bp, wall, a - 12, a + 12, 4.0, 6.0, floor + 70, floor + 73, facing, IRON,
                      f"{ident}_pick_head")
        elif kind == "hoe":
            _wall_box(bp, wall, a - 1, a + 5, 3.0, 9.0, floor + 68, floor + 74, facing, IRON,
                      f"{ident}_hoe_blade")
        else:
            _wall_box(bp, wall, a - 5, a + 5, 3.0, 8.0, floor + 70, floor + 84, facing, DIRT,
                      f"{ident}_broom_head")


def stove(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
          ceiling: float) -> float:
    """A small iron pot-belly stove on four stubby legs, its flue going up
    through the roof.  Returns the hob's Z."""
    for n, (dx, dy) in enumerate(((-9, -9), (9, -9), (-9, 9), (9, 9))):
        _box(bp, x + dx - 1.5, y + dy - 1.5, floor, x + dx + 1.5, y + dy + 1.5, floor + 6, BLACK,
             f"{ident}_leg{n}")
    _box(bp, x - 11, y - 11, floor + 6, x + 11, y + 11, floor + 30, IRON, f"{ident}_body")
    _box(bp, x - 12, y - 12, floor + 30, x + 12, y + 12, floor + 32, BLACK, f"{ident}_hob")
    _box(bp, x + 4, y - 3, floor + 32, x + 10, y + 3, ceiling, BLACK, f"{ident}_flue")
    return floor + 32


def kettle(bp: Blueprint, x: float, y: float, z: float, *, ident: str) -> None:
    """A tin kettle on ``z``: body, lid knob, spout and a bail handle."""
    _box(bp, x - 4, y - 4, z, x + 4, y + 4, z + 6, IRON, f"{ident}_body")
    _box(bp, x - 1, y - 1, z + 6, x + 1, y + 1, z + 7, BLACK, f"{ident}_knob")
    _box(bp, x + 4, y - 1, z + 3, x + 8, y + 1, z + 5, IRON, f"{ident}_spout")
    _box(bp, x - 3, y - 0.5, z + 9, x + 3, y + 0.5, z + 10, BLACK, f"{ident}_handle")
    for n, dx in enumerate((-3.0, 2.0)):
        _box(bp, x + dx, y - 0.5, z + 6, x + dx + 1, y + 0.5, z + 9, BLACK, f"{ident}_bail{n}")


def stool(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
          height: float = 18.0) -> float:
    """A plain three-legged wooden stool.  Returns the seat's top."""
    for n, (dx, dy) in enumerate(((-5, -5), (5, -5), (0, 6))):
        _box(bp, x + dx - 1, y + dy - 1, floor, x + dx + 1, y + dy + 1, floor + height - 2,
             WOOD, f"{ident}_leg{n}")
    _box(bp, x - 8, y - 8, floor + height - 2, x + 8, y + 8, floor + height, WOOD,
         f"{ident}_seat")
    return floor + height


def hook_peg(bp: Blueprint, wall: float, along: float, z: float, *, facing: Facing,
             ident: str) -> float:
    """A wooden coat peg on a wall at ``along``, height ``z``.  Returns how far
    it stands out from the wall (where a hung thing's centre goes)."""
    _wall_box(bp, wall, along - 5, along + 5, 0.0, 1.0, z - 4, z + 4, facing, WOOD,
              f"{ident}_plate")
    _wall_box(bp, wall, along - 1, along + 1, 1.0, 5.0, z - 1, z + 1, facing, WOOD,
              f"{ident}_peg")
    return 4.0


def kneeler(bp: Blueprint, x: float, y: float, floor: float, *, facing: Facing,
            ident: str, length: float = 40.0) -> float:
    """A prayer kneeler: a padded step and a rest rail in front of it at
    elbow height, looking ``facing``.  Returns the rail's top."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    sx, sy = _along(facing, length / 2.0, 6.0)
    _box(bp, x - sx, y - sy, floor, x + sx, y + sy, floor + 6, PEW_WOOD, f"{ident}_step")
    rx, ry = x + fx * 12.0, y + fy * 12.0
    px, py = _along(facing, length / 2.0, 3.0)
    for n, s in enumerate((-1.0, 1.0)):
        ex, ey = (rx + s * (length / 2.0 - 2.0), ry) if fy else (rx, ry + s * (length / 2.0 - 2.0))
        _box(bp, ex - 1.5, ey - 1.5, floor, ex + 1.5, ey + 1.5, floor + 28, PANEL,
             f"{ident}_post{n}")
    _box(bp, rx - px, ry - py, floor + 28, rx + px, ry + py, floor + 31, PANEL, f"{ident}_rail")
    return floor + 31


def lectern(bp: Blueprint, x: float, y: float, floor: float, *, ident: str) -> float:
    """A wooden lectern: a foot, a post and a reading top.  Returns the
    top's Z."""
    _box(bp, x - 10, y - 10, floor, x + 10, y + 10, floor + 3, PANEL, f"{ident}_foot")
    _box(bp, x - 3, y - 3, floor + 3, x + 3, y + 3, floor + 42, PANEL, f"{ident}_post")
    _box(bp, x - 10, y - 13, floor + 42, x + 10, y + 13, floor + 45, PEW_WOOD, f"{ident}_top")
    return floor + 45


def organ(bp: Blueprint, a0: float, a1: float, wall: float, floor: float, *,
          facing: Facing, ident: str) -> tuple[float, float]:
    """A chapel harmonium against a wall, ``a0..a1`` along it: the case, a
    keyboard shelf with black and white keys, a music rest and a row of
    pipes up the wall.  Returns ``(keyboard shelf top, case top)``."""
    _wall_box(bp, wall, a0, a1, 0.0, 24.0, floor, floor + 30, facing, PANEL, f"{ident}_case")
    _wall_box(bp, wall, a0 + 2, a1 - 2, 14.0, 30.0, floor + 30, floor + 33, facing, PEW_WOOD,
              f"{ident}_keybed")
    _wall_box(bp, wall, a0 + 6, a1 - 6, 22.0, 29.0, floor + 33, floor + 34, facing, STONE,
              f"{ident}_keys")
    n = int((a1 - a0 - 12) // 4)
    for k in range(0, n, 2):
        ka = a0 + 6 + k * 4 + 1
        _wall_box(bp, wall, ka, ka + 1.5, 24.0, 28.0, floor + 34, floor + 35, facing, BLACK,
                  f"{ident}_sharp{k}")
    _wall_box(bp, wall, a0, a1, 0.0, 14.0, floor + 33, floor + 62, facing, PANEL,
              f"{ident}_upper")
    _wall_box(bp, wall, a0 + 8, a1 - 8, 14.0, 16.0, floor + 44, floor + 60, facing, PEW_WOOD,
              f"{ident}_rest")
    pipes = max(3, int((a1 - a0) // 10))
    for k in range(pipes):
        pa = a0 + 4 + k * (a1 - a0 - 8) / pipes
        h = 40.0 + 30.0 * (1.0 - abs(k - (pipes - 1) / 2.0) / max(1.0, (pipes - 1) / 2.0))
        _wall_box(bp, wall, pa, pa + 5, 1.0, 5.0, floor + 62, floor + 62 + h, facing, IRON,
                  f"{ident}_pipe{k}")
    return floor + 33, floor + 62


def font(bp: Blueprint, x: float, y: float, floor: float, *, ident: str) -> float:
    """A stone baptismal font: a stepped foot, a column and a square bowl
    with a rim.  Returns the rim's Z."""
    _box(bp, x - 14, y - 14, floor, x + 14, y + 14, floor + 4, TRIM, f"{ident}_foot")
    _box(bp, x - 6, y - 6, floor + 4, x + 6, y + 6, floor + 26, STONE, f"{ident}_column")
    _box(bp, x - 13, y - 13, floor + 26, x + 13, y + 13, floor + 34, STONE, f"{ident}_bowl")
    for n, (x0, y0, x1, y1) in enumerate(((-13, -13, 13, -11), (-13, 11, 13, 13),
                                          (-13, -11, -11, 11), (11, -11, 13, 11))):
        _box(bp, x + x0, y + y0, floor + 34, x + x1, y + y1, floor + 37, TRIM, f"{ident}_rim{n}")
    _box(bp, x - 11, y - 11, floor + 34, x + 11, y + 11, floor + 35, SLAB, f"{ident}_water")
    return floor + 37


def wall_cross(bp: Blueprint, wall: float, along: float, z: float, *, facing: Facing,
               ident: str, height: float = 72.0) -> None:
    """A plain dark wooden cross hung on a wall, its foot at ``z``."""
    _wall_box(bp, wall, along - 3, along + 3, 0.0, 3.0, z, z + height, facing, PEW_WOOD,
              f"{ident}_upright")
    arm = z + height * 0.68
    _wall_box(bp, wall, along - height * 0.28, along + height * 0.28, 0.0, 3.0, arm - 3,
              arm + 3, facing, PEW_WOOD, f"{ident}_arm")


def side_table(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
               half_x: float, half_y: float, height: float = 30.0,
               material: Material = PANEL) -> float:
    """A plain table on four legs.  Returns the top's Z."""
    for n, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        lx, ly = x + sx * (half_x - 2), y + sy * (half_y - 2)
        _box(bp, lx - 1.5, ly - 1.5, floor, lx + 1.5, ly + 1.5, floor + height - 2, material,
             f"{ident}_leg{n}")
    _box(bp, x - half_x, y - half_y, floor + height - 2, x + half_x, y + half_y, floor + height,
         material, f"{ident}_top")
    return floor + height


def flower_stand(bp: Blueprint, x: float, y: float, floor: float, *, ident: str,
                 height: float = 36.0) -> float:
    """A slim iron stand for a funeral spray.  Returns the tray's Z."""
    _box(bp, x - 8, y - 8, floor, x + 8, y + 8, floor + 2, IRON, f"{ident}_foot")
    _box(bp, x - 1, y - 1, floor + 2, x + 1, y + 1, floor + height - 2, BLACK, f"{ident}_stem")
    _box(bp, x - 15, y - 15, floor + height - 2, x + 15, y + 15, floor + height, IRON,
         f"{ident}_tray")
    return floor + height


def small_urn(bp: Blueprint, x: float, y: float, z: float, *, ident: str,
              height: float = 14.0) -> float:
    """A cinerary urn small enough for a niche: foot, body, neck and lid.
    Returns the lid's top."""
    h = height
    _box(bp, x - 3, y - 3, z, x + 3, y + 3, z + h * 0.15, TRIM, f"{ident}_foot")
    _box(bp, x - 5, y - 5, z + h * 0.15, x + 5, y + 5, z + h * 0.75, STONE, f"{ident}_body")
    _box(bp, x - 3, y - 3, z + h * 0.75, x + 3, y + 3, z + h * 0.9, STONE, f"{ident}_neck")
    _box(bp, x - 4, y - 4, z + h * 0.9, x + 4, y + 4, z + h, DARK_STONE, f"{ident}_lid")
    return z + h
