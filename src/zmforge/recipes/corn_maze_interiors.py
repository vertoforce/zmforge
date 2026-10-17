"""The corn maze's buildings and yard, dressed to stock density.

The corn maze's buildings need stock density to read as lived in.
Measured on the map before this module
(a one-off density count), props per 1000 x 1000
units of floor against zm_giant's ~1,150: farmhouse 242, barn floor 147,
hayloft 78, farmyard 119 (not counting its grass and corn).  Nothing was
above head height.

Each room gets what its story leaves behind, at three heights
(docs/map-design-method.md):

* **Farmhouse** -- a family that left mid-supper: the pantry and plate
  shelves packed with preserves and books, high shelves round the kitchen
  and over the bed, washing still on the line by the stove, lamps hung from the
  joists, and heaps of stores, luggage and books along the walls.
* **Barn** -- a working barn: shelves of tins, jugs and tools over the
  benches, a workbench, tie-beams with cage lamps, feed sacks, crates and
  barrels heaped along the walls, the farmer's work clothes hung under the
  hayloft.
* **Hayloft** -- stores stacked against the back wall and the west end,
  clear of Pack-a-Punch and the stair head.
* **Farmyard** -- stacks of crates and barrels along the fences, a barrel
  fire by the barn side, sacks on pallets.

The shapes come from the shared :mod:`zmforge.dressing.interior`; this
module only says where, and every piece goes through the recipe's
:class:`~zmforge.recipes.corn_maze_parts.Dresser`, so the doors, buys,
windows, spawns and the hayride lane keep their keep-outs.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from ..dressing.cluster import clustered_points, rect_edges
from ..dressing.fx import burning
from ..dressing.interior import Piece, fill_board, hang_under, stack_clump
from ..spatial import Bounds, Point

#: What a pantry shelf holds.
PANTRY = (("p7_bottle_glass_liquor_03", 3), ("p7_bottle_glass_wine_01", 1), ("p7_container_bottle_wine_01", 1),
          ("p7_chemistry_kit_large_bottle", 3), ("p7_box_wood_01_sm", 3), ("p7_box_wood_wine_storage_tan", 2),
          ("p7_pot_metal_boiling_lg", 2), ("p7_food_fruit_melon", 1), ("p7_zm_der2_light_hurricane_lamp", 1))
#: Books, in runs, and what stands between them.
BOOKS = (("p7_book_vintage_01", 2), ("p7_book_vintage_02", 2), ("p7_book_vintage_03", 2),
         ("p7_book_vintage_04", 2), ("p7_book_vintage_05", 2), ("p7_book_vintage_06", 2),
         ("p7_decanter_glass_bottle", 1), ("p7_zm_der2_light_hurricane_lamp", 1), ("p7_box_wood_01_sm", 1))
#: The kitchen counter and plate shelf.
KITCHEN = (("p7_pot_metal_boiling_lg", 3), ("p7_pan_metal_sauce", 3), ("p7_pan_metal_lid", 2),
           ("p7_cup_coffee_mug", 3), ("p7_bottle_glass_liquor_03", 3), ("p7_decanter_glass_bottle", 1),
           ("p7_chemistry_kit_large_bottle", 1), ("p7_food_fruit_melon", 1))
#: A barn shelf: oil and linseed in bottles, jugs, lamps, tins (small boxes),
#: tools.
BARN_SHELF = (("p7_bottle_glass_liquor_03", 1), ("p7_chemistry_kit_large_bottle", 3),
              ("p7_zm_der2_light_hurricane_lamp", 2), ("p7_box_wood_01_sm", 3), ("p7_box_wood_wine_storage", 2),
              ("p7_pot_metal_boiling_lg", 2), ("p7_pan_metal_sauce", 1), ("p7_farm_tools_hammer", 1),
              ("zmf_prop_pumpkin", 1))
#: House heaps: stores and luggage, with small things on top.
HOUSE_BASE = (("p7_crate_wood_01_short_open", 3), ("p7_box_wood_wine_storage", 2),
              ("p7_box_wood_wine_storage_tan", 2), ("p7_luggage_cloth_a_lg_green", 1))
HOUSE_TOP = (("p7_bottle_glass_liquor_03", 3), ("p7_book_vintage_01", 2), ("p7_book_vintage_03", 2),
             ("p7_book_vintage_05", 1), ("p7_cup_coffee_mug", 1), ("p7_box_wood_01_sm", 1),
             ("p7_decanter_glass_bottle", 1))
HOUSE_SKIRT = (("p7_book_vintage_02", 2), ("p7_book_vintage_open_04", 1), ("p7_box_wood_01_sm", 2),
               ("p7_cup_coffee_mug", 1), ("p7_debris_clothing_piles_01", 1),
               ("p7_bottle_glass_wine_01", 1))
#: Barn and yard heaps: crates, barrels, sacks.
# (Not the long ``p7_crate_wood_01``: what stood on it read as floating
# 31 over the floor, Z44 check.)
YARD_BASE = (("p7_crate_wood_01_short_open", 4), ("p7_barrel_metal_55gal_blue", 2), ("zmf_prop_wooden_crate", 2))
YARD_TOP = (("p7_sandbag_01", 3), ("p7_zm_der2_light_hurricane_lamp", 1), ("p7_chemistry_kit_large_bottle", 1),
            ("p7_box_wood_01_sm", 2), ("p7_farm_tools_hammer", 1), ("zmf_prop_pumpkin", 1),
            ("p7_bottle_glass_liquor_03", 1))
YARD_SKIRT = (("p7_sandbag_01", 4), ("zmf_prop_pumpkin", 2), ("p7_box_wood_01_sm", 1),
              ("p7_debris_wood_board_splinter_01", 1), ("p7_tools_shovel", 1),
              ("p7_box_wood_wine_storage_tan", 1))
#: Small heaps that fill the gaps the big ones leave: sacks, boxes, a
#: pumpkin, with bits on top and litter round them.
# Only flat-topped bases: a sack or a pumpkin under a bottle is not a
# surface the checks accept (Z44 floaters, check); they go in
# the litter round the heap instead.
SMALL_BASE = (("p7_box_wood_01_sm", 3), ("p7_box_wood_wine_storage", 2), ("p7_box_wood_wine_storage_tan", 2),
              ("p7_barrel_metal_55gal_blue", 1))
# liquor_01 read as floating on every crate and barrel top it stood on (Z44);
# liquor_03 stands.
SMALL_TOP = (("zmf_prop_pumpkin", 1), ("p7_bottle_glass_liquor_03", 1),
             ("p7_farm_tools_hammer", 1), ("p7_chemistry_kit_large_bottle", 1))
LITTER = (("p7_debris_wood_board_splinter_01", 2), ("p7_debris_wood_board_splinter_02", 2),
          ("p7_debris_wood_board_splinter_03", 1), ("p7_sandbag_01", 2), ("zmf_prop_pumpkin", 1),
          ("p7_tools_shovel", 1), ("p7_debris_wood_board_cluster_01", 1))
#: Hung from the joists and under the hayloft.
HOUSE_LAMPS = (("p7_zm_der_light_shade", 2), ("p7_zm_der_light_cage_01", 1))
WASHING = (("p7_clothes_hanging_01_shirt", 3), ("p7_clothes_hanging_01_tshirt", 2),
           ("p7_clothes_hanging_01_dress", 1), ("p7_clothes_hanging_01_suit", 1))
WORK_CLOTHES = (("p7_clothes_hanging_01_shirt", 2), ("p7_clothes_hanging_01_tshirt", 2),
                ("p7_clothes_hanging_01_suit", 1))
#: How deep a wall shelf is: a 24 board takes a jug, a pot, a lantern, a
#: small crate (``p7_box_wood_01_sm`` is 15 x 22).
SHELF_DEPTH = 24.0
BARN_LAMPS = (("p7_zm_der_light_cage_01", 2), ("p7_zm_der_light_shade", 1))


OPEN_CRATE = "p7_crate_wood_01_short_open"


def _reach(model: str, scale: float = 1.0) -> float:
    from .corn_maze_parts import MODEL_BOX

    (x0, y0, _), (x1, y1, _) = MODEL_BOX[model]
    return math.hypot(max(-x0, x1), max(-y0, y1)) * scale


class _Floor:
    """What stands on one floor already (the zone's pending props), so a new
    heap keeps off it: the dresser's keep-outs are for doors and machines,
    not for the crate someone put down before."""

    def __init__(self, d, zone: str, z: float):
        self.z = z
        self.taken = [(at.x, at.y, _reach(m, sc)) for m, at, _yaw, sc, *_ in d.pending.get(zone, [])
                      if abs(at.z - z) < 40.0]

    def clear(self, x: float, y: float, r: float, pad: float = 4.0) -> bool:
        return all(math.hypot(x - tx, y - ty) >= r + tr + pad for tx, ty, tr in self.taken)

    def add(self, x: float, y: float, r: float) -> None:
        self.taken.append((x, y, r))


def _frange(a: float, b: float, step: float) -> list[float]:
    out, x = [], a
    while x <= b:
        out.append(x)
        x += step
    return out


def _board(d, zone: str, pieces: Sequence[Piece]) -> int:
    """Shelf and counter items: the board is the recipe's keep-out already."""
    return sum(bool(d.put(zone, p.model, p.x, p.y, p.surface, p.yaw, p.scale, check=False, lane=False))
               for p in pieces)


def _inside(p: Piece, walls: tuple[float, float, float, float] | None) -> bool:
    """Whether *p*'s turned footprint stays inside *walls* (the room's inner
    faces, ``x0, y0, x1, y1``) by a unit: over the wall is Z54."""
    if walls is None:
        return True
    from ..dressing.interior import _turned

    fx0, fy0, fx1, fy1 = _turned(p.model, p.yaw, p.scale)
    return (p.x + fx0 >= walls[0] + 1.0 and p.y + fy0 >= walls[1] + 1.0
            and p.x + fx1 <= walls[2] - 1.0 and p.y + fy1 <= walls[3] - 1.0)


def _clump(d, zone: str, pieces: Sequence[Piece], floor: _Floor, *, lane: bool,
           walls: tuple[float, float, float, float] | None = None) -> int:
    """A heap: the base checked (refused, the heap goes), what is stacked on
    it unchecked, the skirt checked piece by piece and against the floor.
    Nothing reaches past *walls*."""
    if not pieces or not _inside(pieces[0], walls):
        return 0
    pieces = pieces[:1] + [p for p in pieces[1:] if _inside(p, walls)]
    base = pieces[0]
    r = _reach(base.model)
    if not floor.clear(base.x, base.y, r) or not d.put(zone, base.model, base.x, base.y, base.surface,
                                                       base.yaw, base.scale, lane=lane):
        return 0
    floor.add(base.x, base.y, r)
    n = 1
    # An open crate has no top to stand things on: its lid goes on first
    # (as the barn's ring does), or what is stacked on it floats (Z44).
    if base.model == OPEN_CRATE:
        from .corn_maze_parts import MODEL_BOX

        lid_z = base.surface + MODEL_BOX[OPEN_CRATE][1][2] - MODEL_BOX[OPEN_CRATE][0][2]
        n += bool(d.put(zone, OPEN_CRATE + "_lid", base.x, base.y, lid_z, base.yaw, base.scale, check=False,
                        lane=False, solid=False))
    # A stacked piece the placer turns away (a solid one by a window) takes
    # everything above it with it: nothing is left floating (Z44).
    refused_at = math.inf
    for p in pieces[1:]:
        if p.surface > floor.z + 0.5:
            if p.surface >= refused_at - 0.5:
                continue
            if d.put(zone, p.model, p.x, p.y, p.surface, p.yaw, p.scale, check=False, lane=False):
                n += 1
            else:
                refused_at = min(refused_at, p.surface + 0.5)
            continue
        pr = _reach(p.model)
        if floor.clear(p.x, p.y, pr, pad=1.0) and d.put(zone, p.model, p.x, p.y, p.surface, p.yaw, p.scale,
                                                        lane=lane):
            floor.add(p.x, p.y, pr)
            n += 1
    return n


def _heaps(d, zone: str, rng: random.Random, rect, floor: _Floor, count: int, *, band: float,
           base, tops, skirt, lane: bool = False, accept=None, second: float = 0.5,
           spread: float = 45.0, walls=None, on_top: tuple[int, int] = (1, 3),
           skirt_n: tuple[int, int] = (2, 5)) -> int:
    """*count* heaps in clumps along the walls of *rect* (within *band* of
    one), each a :func:`stack_clump`, nothing past *walls* (default
    *rect*)."""
    x0, y0, x1, y1 = rect
    walls = walls or rect

    def ok(x: float, y: float) -> bool:
        near = min(x - x0, x1 - x, y - y0, y1 - y) <= band
        return near and (accept is None or accept(x, y))

    points = clustered_points(rng, rect, count * 10, clumps=max(3, count), spread=spread,
                              edges=rect_edges(*rect), edge_reach=band, edge_bias=0.95, accept=ok)
    n = placed = 0
    for x, y, _c in points:
        if placed >= count:
            break
        got = _clump(d, zone, stack_clump(rng, x, y, floor.z, base=base, tops=tops, skirt=skirt,
                                          second=second, on_top=on_top, skirt_n=skirt_n), floor, lane=lane, walls=walls)
        if got:
            placed += 1
            n += got
    return n


def _wall_shelf(bp, d, zone: str, box: Bounds, front: tuple[int, int], ident: str, boards: Sequence[float],
                palette, rng: random.Random, *, check_z: Sequence[float] | None = None,
                depth: float | None = None, checked: bool = False) -> int:
    """A shelving unit (``_brush_shelf``) filling *box* against a wall, open
    to *front*, packed with *palette* on every board; skipped when any of
    its span is in a keep-out (a window, a buy, a machine, a door)."""
    from .corn_maze_parts import _brush_shelf

    # Deep enough for the big readable things (16-deep
    # boards held only 3-unit bottles, and from across the room the full
    # shelves read empty).  Grown out from the wall, into the room.
    depth = SHELF_DEPTH if depth is None else depth
    lo, hi = box.mins, box.maxs
    if front[0] == 0:
        box = (Bounds.between((lo.x, lo.y, lo.z), (hi.x, max(hi.y, lo.y + depth), hi.z)) if front[1] > 0
               else Bounds.between((lo.x, min(lo.y, hi.y - depth), lo.z), (hi.x, hi.y, hi.z)))
    else:
        box = (Bounds.between((lo.x, lo.y, lo.z), (max(hi.x, lo.x + depth), hi.y, hi.z)) if front[0] > 0
               else Bounds.between((min(lo.x, hi.x - depth), lo.y, lo.z), (hi.x, hi.y, hi.z)))
    along_x = front[0] == 0
    zs = check_z if check_z is not None else (box.mins.z,)
    a0, a1 = (box.mins.x, box.maxs.x) if along_x else (box.mins.y, box.maxs.y)
    cx, cy = box.centre.x, box.centre.y
    for t in (() if checked else (0.1, 0.5, 0.9)):
        a = a0 + (a1 - a0) * t
        x, y = (a, cy) if along_x else (cx, a)
        if any(not d.free(x, y, z, 10.0, lane=False) or d.by_window(x, y, z, 10.0) for z in zs):
            return 0
    # Nor over a prop already standing there (the barn's ring of stores).
    for m, at, yaw, sc, *_ in ([] if checked else d.pending.get(zone, [])):
        rr = _reach(m, sc)
        if (box.mins.x - rr < at.x < box.maxs.x + rr and box.mins.y - rr < at.y < box.maxs.y + rr
                and box.mins.z - 40.0 < at.z < box.maxs.z):
            return 0
    tops = _brush_shelf(bp, box, front, ident, boards)
    # 16, not 6: a heap's base is checked by its half-width, and at 6 a
    # turned crate still reached 2-15% onto the unit (Z44).
    d.keepouts.append(box.grown(16.0))
    # The board's clear plan: inside the side boards, in front of the back.
    back = 1.5
    if along_x:
        by0, by1 = (box.mins.y + back, box.maxs.y) if front[1] > 0 else (box.mins.y, box.maxs.y - back)
        plan = Bounds.between((box.mins.x + 2.0, by0, 0.0), (box.maxs.x - 2.0, by1, 1.0))
    else:
        bx0, bx1 = (box.mins.x + back, box.maxs.x) if front[0] > 0 else (box.mins.x, box.maxs.x - back)
        plan = Bounds.between((bx0, box.mins.y + 2.0, 0.0), (bx1, box.maxs.y - 2.0, 1.0))
    n = 0
    for i, top in enumerate(tops):
        gap = (tops[i + 1] - top - 2.0) if i + 1 < len(tops) else (box.maxs.z - top + 40.0)
        n += _board(d, zone, fill_board(rng, palette, plan, top, max_height=gap - 1.0))
    return n


def dress(bp, d, plan, *, fhi: Bounds, bi: Bounds, fi: Bounds, hz: float, bz: float, fz: float,
          loft_top: float, stair_x: float) -> dict[str, int]:
    """Dress the farmhouse, the barn (floor and hayloft) and the farmyard;
    returns the props each got."""
    from . import corn_maze as cm
    from .corn_maze_parts import _brush_table, _lamp

    rng = random.Random("corn-interiors")
    got = {"farmhouse": 0, "barn": 0, "loft": 0, "farmyard": 0}

    # ---- Farmhouse ---------------------------------------------------------
    ceiling = fhi.maxs.z
    # High shelves over head height round the walls (overhead band): over
    # the kitchen counter two boards, over the bed wall and the north-west
    # corner one each.  Each goes only where no window, machine or buy is.
    high = [
        ("farmhouse_hshelf_kitchen", Bounds.between((fhi.mins.x + 4, fhi.mins.y, hz + 150), (fhi.mins.x + 264, fhi.mins.y + 16, hz + 214)), (0, 1), (2.0, 32.0, 62.0), KITCHEN),
        ("farmhouse_hshelf_nw", Bounds.between((fhi.mins.x, fhi.maxs.y - 190, hz + 140), (fhi.mins.x + 16, fhi.maxs.y - 4, hz + 176)), (1, 0), (2.0, 34.0), PANTRY),
        # Over the dresser and the bed, not over the box: it rises when it moves.
        ("farmhouse_hshelf_north_w", Bounds.between((fhi.centre.x - 120, fhi.maxs.y - 16, hz + 150), (fhi.centre.x + 110, fhi.maxs.y, hz + 186)), (0, -1), (2.0, 34.0), BOOKS),
        ("farmhouse_hshelf_north_e", Bounds.between((fhi.centre.x + 140, fhi.maxs.y - 16, hz + 150), (fhi.centre.x + 230, fhi.maxs.y, hz + 186)), (0, -1), (2.0, 34.0), PANTRY),
        ("farmhouse_hshelf_ne", Bounds.between((fhi.maxs.x - 16, fhi.maxs.y - 200, hz + 140), (fhi.maxs.x, fhi.maxs.y - 24, hz + 176)), (-1, 0), (2.0, 34.0), BOOKS),
        ("farmhouse_hshelf_se", Bounds.between((fhi.centre.x + 70, fhi.mins.y, hz + 150), (fhi.centre.x + 180, fhi.mins.y + 16, hz + 186)), (0, 1), (2.0, 34.0), PANTRY),
    ]
    for ident, box, front, boards, pal in high:
        got["farmhouse"] += _wall_shelf(bp, d, "farmhouse", box, front, ident, boards, pal, rng,
                                        check_z=(box.mins.z, box.maxs.z - 10))
    # A bookcase and a dresser-height pantry on the floor, where the wall is free.
    for ident, box, front, boards, pal in (
            ("farmhouse_bookcase_w", Bounds.between((fhi.mins.x, fhi.centre.y + 180, hz), (fhi.mins.x + 18, fhi.centre.y + 250, hz + 112)), (1, 0), (2.0, 30.0, 58.0, 86.0, 112.0), BOOKS),
            ("farmhouse_pantry_e", Bounds.between((fhi.maxs.x - 18, fhi.maxs.y - 190, hz), (fhi.maxs.x, fhi.maxs.y - 110, hz + 86)), (-1, 0), (2.0, 30.0, 58.0, 86.0), PANTRY)):
        got["farmhouse"] += _wall_shelf(bp, d, "farmhouse", box, front, ident, boards, pal, rng,
                                        check_z=(hz, hz + 60))
    # A second bookcase: the first free stretch of wall of these (the east
    # wall by the wall buy, where it first went, is the buy's to keep).
    for ident, box, front in (
            ("farmhouse_bookcase_s", Bounds.between((fhi.centre.x + 84, fhi.mins.y, hz), (fhi.centre.x + 150, fhi.mins.y + 18, hz + 112)), (0, 1)),
            ("farmhouse_bookcase_n", Bounds.between((fhi.mins.x + 24, fhi.maxs.y - 18, hz), (fhi.mins.x + 94, fhi.maxs.y, hz + 112)), (0, -1)),
            ("farmhouse_bookcase_e", Bounds.between((fhi.maxs.x - 18, fhi.maxs.y - 290, hz), (fhi.maxs.x, fhi.maxs.y - 220, hz + 112)), (-1, 0))):
        n = _wall_shelf(bp, d, "farmhouse", box, front, ident, (2.0, 30.0, 58.0, 86.0, 112.0), BOOKS, rng,
                        check_z=(hz, hz + 60))
        got["farmhouse"] += n
        if n:
            break
    # Lamps hung from the ceiling down the room, and the washing on a line
    # by the stove (it dries by the fire).
    for n, y in enumerate((fhi.mins.y + 150.0, fhi.centre.y + 10.0, fhi.maxs.y - 150.0)):
        got["farmhouse"] += _board(d, "farmhouse", hang_under(
            bp, f"farmhouse_lamps_{n}", (fhi.mins.x + 90.0, y), (fhi.maxs.x - 90.0, y), ceiling - 34.0,
            ceiling=ceiling, models=HOUSE_LAMPS, rng=rng, step=(110.0, 150.0)))
    got["farmhouse"] += _board(d, "farmhouse", hang_under(
        bp, "farmhouse_washing", (fhi.centre.x + 110.0, fhi.mins.y + 60.0), (fhi.maxs.x - 40.0, fhi.mins.y + 60.0),
        hz + 196.0, ceiling=ceiling, models=WASHING, rng=rng, step=(14.0, 22.0)))
    got["farmhouse"] += _board(d, "farmhouse", hang_under(
        bp, "farmhouse_washing_w", (fhi.mins.x + 40.0, fhi.maxs.y - 60.0), (fhi.mins.x + 40.0, fhi.centre.y + 110.0),
        hz + 196.0, ceiling=ceiling, models=WASHING, rng=rng, step=(14.0, 22.0)))
    # Heaps of stores, luggage and books along the walls.
    house_floor = _Floor(d, "farmhouse", hz)
    got["farmhouse"] += _heaps(d, "farmhouse", rng, (fhi.mins.x + 20, fhi.mins.y + 20, fhi.maxs.x - 20, fhi.maxs.y - 20),
                               house_floor, 24, band=110.0, walls=(fhi.mins.x, fhi.mins.y, fhi.maxs.x, fhi.maxs.y), base=HOUSE_BASE, tops=HOUSE_TOP, skirt=HOUSE_SKIRT,
                               second=0.45, spread=35.0)

    # ---- Barn floor --------------------------------------------------------
    bceil = bi.maxs.z
    edge_y = bi.mins.y + plan.loft_depth
    # Shelves high on the walls north of the hayloft, over the racks and benches.
    for ident, box, front in (
            ("barn_hshelf_nw", Bounds.between((bi.mins.x + 20, bi.maxs.y - 16, bz + 150), (bi.centre.x - 90, bi.maxs.y, bz + 220)), (0, -1)),
            ("barn_hshelf_ne", Bounds.between((bi.centre.x + 90, bi.maxs.y - 16, bz + 150), (bi.maxs.x - 20, bi.maxs.y, bz + 220)), (0, -1)),
            # The west wall either side of its window (the east wall is the
            # stair's).
            ("barn_hshelf_w", Bounds.between((bi.mins.x, edge_y + 20, bz + 150), (bi.mins.x + 16, edge_y + 120, bz + 220)), (1, 0)),
            ("barn_hshelf_w2", Bounds.between((bi.mins.x, bi.maxs.y - 216, bz + 150), (bi.mins.x + 16, bi.maxs.y - 40, bz + 220)), (1, 0)),
            # The hayloft's back wall and west end, over the stores stacked there.
            ("barn_loft_shelf_s", Bounds.between((bi.mins.x + 150, bi.mins.y, loft_top + 110), (bi.centre.x - 330, bi.mins.y + 16, loft_top + 180)), (0, 1)),
            ("barn_loft_shelf_s2", Bounds.between((bi.centre.x + 80, bi.mins.y, loft_top + 110), (bi.maxs.x - 120, bi.mins.y + 16, loft_top + 180)), (0, 1)),
            ("barn_loft_shelf_w", Bounds.between((bi.mins.x, bi.mins.y + 110, loft_top + 110), (bi.mins.x + 16, edge_y - 60, loft_top + 180)), (1, 0))):
        got["barn"] += _wall_shelf(bp, d, "barn", box, front, ident, (2.0, 36.0, 70.0), BARN_SHELF, rng,
                                   check_z=(box.mins.z, box.maxs.z - 10))
    # A workbench under the hayloft on the west wall, its top packed, a
    # shelving unit beside it.
    bench = Bounds.between((bi.mins.x + 4, bi.mins.y + 170, bz), (bi.mins.x + 34, bi.mins.y + 310, bz + 38))
    standing = [(at.x, at.y, _reach(m, sc)) for m, at, _yaw, sc, *_ in d.pending.get("barn", []) if at.z < bz + 60]
    if all(d.free(bench.centre.x, y, bz, 16.0, lane=False) for y in (bench.mins.y + 10, bench.centre.y, bench.maxs.y - 10)) \
            and not any(bench.mins.x - r < x < bench.maxs.x + r and bench.mins.y - r < y < bench.maxs.y + r
                        for x, y, r in standing):
        _brush_table(bp, bench, "barn_workbench")
        d.keepouts.append(bench.grown(16.0))
        got["barn"] += _board(d, "barn", fill_board(rng, BARN_SHELF, bench, bench.maxs.z, gap=3.0))
    got["barn"] += _wall_shelf(bp, d, "barn", Bounds.between((bi.mins.x, bi.mins.y + 30, bz), (bi.mins.x + 20, bi.mins.y + 124, bz + 112)),
                               (1, 0), "barn_bench_shelf", (2.0, 30.0, 58.0, 86.0, 112.0), BARN_SHELF, rng,
                               check_z=(bz, bz + 60))
    # Shelving units down the long walls north of the hayloft, wherever the
    # wall is free (the tool rack, the wall buy, the windows and the trough
    # keep theirs): a barn's walls carry its stores.
    for side, xw, front in (("w", bi.mins.x, (1, 0)), ("e", bi.maxs.x - 18.0, (-1, 0))):
        for k, y in enumerate(range(int(edge_y + 60), int(bi.maxs.y - 120), 110)):
            box = Bounds.between((xw, y, bz), (xw + 18.0, y + 80.0, bz + 86.0))
            got["barn"] += _wall_shelf(bp, d, "barn", box, front, f"barn_unit_{side}_{k}", (2.0, 30.0, 58.0, 86.0),
                                       BARN_SHELF, rng, check_z=(bz, bz + 60))
    def barn_ok_rack(x: float, y0: float, y1: float) -> bool:
        # Off the door's run in from the north and the stair's foot.
        return not (abs(x) < 150 and y1 > bi.maxs.y - 300) and x + 24 < stair_x - 130

    # Freestanding store racks, back to back, in the west half of the floor
    # (the east half is the walk from the door to the stair): the barn's
    # stores at eye level, not only round its walls.  A pair stands only
    # whole, and only where both faces are free (_wall_shelf's checks).
    racks = 0
    for rx in _frange(bi.mins.x + 130.0, bi.centre.x + 260.0, 40.0):
        for ry0 in _frange(edge_y + 60.0, bi.maxs.y - 320.0, 40.0):
            ry1 = ry0 + 130.0
            if racks >= 4 or not barn_ok_rack(rx, ry0, ry1):
                continue
            west = Bounds.between((rx - 24.0, ry0, bz), (rx, ry1, bz + 112.0))
            east = Bounds.between((rx, ry0, bz), (rx + 24.0, ry1, bz + 112.0))
            if not all(d.free(x, y, z, 14.0, lane=False) for x in (west.mins.x, rx, east.maxs.x)
                       for y in (ry0, ry0 + 45.0, ry1 - 45.0, ry1) for z in (bz, bz + 60.0)):
                continue
            if any(west.mins.x - 24 - _reach(m, sc) < at.x < east.maxs.x + 24 + _reach(m, sc)
                   and ry0 - 24 - _reach(m, sc) < at.y < ry1 + 24 + _reach(m, sc) and at.z < bz + 120
                   for m, at, _yaw, sc, *_ in d.pending.get("barn", [])):
                continue
            for ident, box, front in ((f"barn_rack_{racks}_w", west, (-1, 0)), (f"barn_rack_{racks}_e", east, (1, 0))):
                got["barn"] += _wall_shelf(bp, d, "barn", box, front, ident, (2.0, 30.0, 58.0, 86.0, 112.0),
                                           BARN_SHELF, rng, checked=True)
            d.keepouts.append(Bounds.between((west.mins.x - 60, ry0 - 60, bz), (east.maxs.x + 60, ry1 + 60, bz + 120)))
            racks += 1
    # Tie-beams across the barn north of the hayloft, cage lamps hung under
    # them; the farmer's work clothes on a line under the hayloft's edge.
    for n, y in enumerate((edge_y + 120.0, edge_y + 300.0, edge_y + 480.0)):
        beam = Bounds.between((bi.mins.x, y - 5.0, bz + 330.0), (bi.maxs.x, y + 5.0, bz + 342.0))
        bp.add_block(beam, cm._BEAM, reachable=False, id=f"barn_tiebeam_{n}", note="tie beam")
        got["barn"] += _board(d, "barn", hang_under(bp, f"barn_tiebeam_lamps_{n}", (bi.mins.x + 80.0, y),
                                                    (bi.maxs.x - 80.0, y), bz + 330.0, ceiling=bceil,
                                                    models=BARN_LAMPS, rng=rng, step=(80.0, 120.0), bar=False))
    got["barn"] += _board(d, "barn", hang_under(bp, "barn_loft_washing", (bi.mins.x + 130.0, edge_y - 40.0),
                                                (bi.mins.x + 400.0, edge_y - 40.0), loft_top - 16.0,
                                                ceiling=loft_top - 16.0, models=WORK_CLOTHES, rng=rng,
                                                step=(16.0, 26.0), bar=False))
    got["loft"] += _board(d, "barn", hang_under(bp, "barn_loft_lamps", (bi.mins.x + 80.0, bi.mins.y + 200.0),
                                                (bi.maxs.x - 80.0, bi.mins.y + 200.0), loft_top + 170.0,
                                                ceiling=bceil, models=BARN_LAMPS, rng=rng, step=(140.0, 190.0)))
    # The rest of the work clothes, on a line under the hayloft's edge east of
    # the first, clear of the stair.
    got["barn"] += _board(d, "barn", hang_under(bp, "barn_loft_washing_e", (bi.centre.x - 60.0, edge_y - 40.0),
                                                (stair_x - 150.0, edge_y - 40.0), loft_top - 16.0,
                                                ceiling=loft_top - 16.0, models=WORK_CLOTHES, rng=rng,
                                                step=(16.0, 26.0), bar=False))
    barn_floor = _Floor(d, "barn", bz)

    def barn_ok(x: float, y: float) -> bool:
        # Clear of the stair's foot and the door's run in from the north.
        return not (stair_x - 110 < x < bi.maxs.x and edge_y - 20 < y < edge_y + 460) and not (abs(x) < 110 and y > bi.maxs.y - 260)

    got["barn"] += _heaps(d, "barn", rng, (bi.mins.x + 20, bi.mins.y + 20, bi.maxs.x - 20, bi.maxs.y - 20), barn_floor,
                          90, walls=(bi.mins.x, bi.mins.y, bi.maxs.x, bi.maxs.y), band=220.0, base=YARD_BASE, tops=YARD_TOP, skirt=YARD_SKIRT, accept=barn_ok, second=0.7,
                          on_top=(2, 5), skirt_n=(4, 9))

    # The gaps between: small heaps of sacks, boxes and pumpkins.
    got["barn"] += _heaps(d, "barn", rng, (bi.mins.x + 20, bi.mins.y + 20, bi.maxs.x - 20, bi.maxs.y - 20), barn_floor,
                          70, walls=(bi.mins.x, bi.mins.y, bi.maxs.x, bi.maxs.y), band=240.0, base=SMALL_BASE,
                          tops=SMALL_TOP, skirt=LITTER, accept=barn_ok, second=0.4, on_top=(1, 3),
                          skirt_n=(3, 7), spread=30.0)

    # ---- Hayloft -----------------------------------------------------------
    loft_floor = _Floor(d, "barn", loft_top)

    def loft_ok(x: float, y: float) -> bool:
        # The back wall and the west end only: the deck's front is the walk
        # from the stair head to Pack-a-Punch.
        # Pack-a-Punch stands at x = -120 on the back wall, the stair head at
        # the east end of the deck's front.
        back = y < bi.mins.y + 120.0 or x < bi.mins.x + 200.0 or (x > 200.0 and y < edge_y - 150.0)
        return back and y < edge_y - 70.0 and not (-300 < x < 60)

    got["loft"] += _heaps(d, "barn", rng, (bi.mins.x + 16, bi.mins.y + 16, bi.maxs.x - 16, edge_y - 60), loft_floor,
                          26, walls=(bi.mins.x, bi.mins.y, bi.maxs.x, bi.maxs.y), band=100.0, base=YARD_BASE, tops=YARD_TOP, skirt=YARD_SKIRT, accept=loft_ok,
                          second=0.6, spread=30.0, on_top=(2, 4), skirt_n=(3, 6))

    # ---- Farmyard ----------------------------------------------------------
    yard_floor = _Floor(d, "farmyard", fz)

    def yard_ok(x: float, y: float) -> bool:
        # Off the trodden paths (north-south on x = 0, west to the maze gate
        # on y = 150) and the hayride stop.
        return abs(x) > 90.0 and abs(y - 150.0) > 80.0 and not (x < fi.mins.x + 420 and y < -150)

    got["farmyard"] += _heaps(d, "farmyard", rng, (fi.mins.x + 20, fi.mins.y + 20, fi.maxs.x - 20, fi.maxs.y - 20),
                              yard_floor, 110, band=280.0, walls=(fi.mins.x, fi.mins.y, fi.maxs.x, fi.maxs.y), base=YARD_BASE, tops=YARD_TOP, skirt=YARD_SKIRT,
                              lane=True, accept=yard_ok, second=0.6, on_top=(2, 5), skirt_n=(4, 9))
    got["farmyard"] += _heaps(d, "farmyard", rng, (fi.mins.x + 20, fi.mins.y + 20, fi.maxs.x - 20, fi.maxs.y - 20),
                              yard_floor, 70, band=200.0, walls=(fi.mins.x, fi.mins.y, fi.maxs.x, fi.maxs.y),
                              base=SMALL_BASE, tops=SMALL_TOP, skirt=LITTER, lane=True, accept=yard_ok,
                              second=0.4, on_top=(1, 3), skirt_n=(3, 7), spread=30.0)
    # The burn barrel by the barn-side fence, east of the barn door.
    for bx_, by_ in ((230.0, fi.mins.y + 70.0), (330.0, fi.mins.y + 80.0), (-230.0, fi.mins.y + 70.0)):
        if yard_floor.clear(bx_, by_, 20.0) and d.put("farmyard", "p7_barrel_metal_55gal_blue", bx_, by_, fz, 20.0):
            yard_floor.add(bx_, by_, 20.0)
            burning(bp, Point(bx_, by_, fz + 36.0), size="small", light=False, note="farmyard burn barrel")
            _lamp(bp, bx_, by_, fz + 70.0, "farmyard", "farmyard_burn_barrel_glow", radius=220.0)
            got["farmyard"] += 1
            for k in range(5):
                a = k * 72.0 + 20.0
                m = ("p7_debris_wood_board_splinter_01", "p7_debris_wood_board_splinter_02", "p7_sandbag_01",
                     "p7_debris_wood_board_splinter_03", "p7_box_wood_01_sm")[k]
                x, y = bx_ + 34.0 * math.cos(math.radians(a)), by_ + 34.0 * math.sin(math.radians(a))
                if yard_floor.clear(x, y, _reach(m), pad=1.0) and d.put("farmyard", m, x, y, fz, a):
                    yard_floor.add(x, y, _reach(m))
                    got["farmyard"] += 1
            break
    return got
