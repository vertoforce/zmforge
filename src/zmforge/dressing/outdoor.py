"""Outdoor set dressing: set pieces, pinch points, three-height layering, light pools.

The art direction behind these (``docs/map-principles.md`` P18, from a
Nuketown-style stock map as the reference): big set pieces that are both
landmark and cover, paths squeezed by them rather than clean wide lanes,
detail at three heights (ground, waist, overhead), and light in pools with
dark between.  Everything here uses **stock** models that link locally
(``blueprint/installed_assets.json``, judged ``ok``) and measured boxes
read from the stock models (:data:`STOCK_BOXES`, registered into
``MODEL_BOX`` by :func:`register_boxes`, a measurement props.py adds later
wins).  Recipes pick from the palettes; nothing here knows about any map.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Sequence

from .place import PropSpec, on_floor

__all__ = [
    "STOCK_BOXES", "GROUND", "WAIST", "OVERHEAD", "WRECKS", "register_boxes",
    "layered", "pinch_point", "light_pool_points", "light_pools",
]

#: Stock models the palettes use that ``MODEL_BOX`` may not carry: each
#: box read from the model's own vertex positions, and each judged ``ok``
#: (links locally) by :func:`zmforge.blueprint.installed.judge_misc_model`.
STOCK_BOXES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "p7_foliage_hedge_box_128_48_60": ((-74.7, -35.2, -6.3), (76.5, 35.6, 66.7)),
    "p7_foliage_hedge_box_128_48_36": ((-70.4, -30.6, -3.5), (70.0, 30.9, 39.8)),
    "p7_foliage_hedge_round_48_48_36": ((-32.9, -27.2, -0.5), (25.7, 28.6, 40.9)),
    "p7_foliage_leaves_ivy_dead_128x64": ((-62.5, -31.5, -0.1), (57.5, 31.9, 1.2)),
    "p7_foliage_grass_dry_01": ((-20.2, -23.7, -0.3), (19.6, 25.6, 44.2)),
    "p7_foliage_grass_dry_03": ((-13.5, -12.2, 0.0), (13.5, 12.2, 14.5)),
    "p7_foliage_tree_olive_small": ((-45.5, -31.6, 0.0), (29.9, 56.5, 96.1)),
    "p7_foliage_tree_albizia_tall_full": ((-282.8, -269.6, 0.0), (288.1, 278.1, 763.6)),
    "p7_boulder_rock_05": ((-9.9, -5.8, -3.3), (9.6, 5.9, 3.3)),
    "veh_t7_civ_truck_semi_flatbed": ((-520.0, -68.7, -1.0), (54.2, 68.7, 79.5)),
    "p7_farm_tools_hammer": ((-4.0, -11.2, 0.1), (4.4, 11.2, 2.2)),
}

#: Ground layer (ankle height, walk-through): dry grass, stones, bones,
#: splinters and burnt boards.  ``(model, scale range, weight)``.
GROUND: tuple[tuple[str, tuple[float, float], int], ...] = (
    # The dry grass set judges "ok" but its material wants the tussock set's
    # images, which the mod tools do not ship: a zm_corn_maze link failed on
    # them.  The tall cluster and weeds link.
    ("p7_foliage_grass_tall_cluster_sml", (0.5, 0.9), 6),
    ("p7_foliage_weed_cluster_lrg", (1.5, 2.2), 3),
    ("p7_foliage_weed_cluster_med", (1.5, 2.2), 2),
    ("p7_debris_rockychunks_small_01", (0.8, 1.2), 2),
    ("p7_debris_rockychunks_small_12", (0.8, 1.2), 2),
    ("p7_boulder_rock_05", (1.5, 3.0), 2),
    ("p7_gib_chunk_bone_01", (1.0, 1.5), 1),
    ("p7_gib_chunk_bone_03", (1.0, 1.5), 1),
    ("p7_debris_wood_board_cluster_burn_01", (1.0, 1.0), 1),
    ("p7_debris_wood_board_splinter_01", (1.0, 1.0), 1),
)
#: Waist layer (solid cover and clutter): barrels, crates, a hedge clump, a
#: sheet of rusted tin, a wheelbarrow.
WAIST: tuple[tuple[str, tuple[float, float], int], ...] = (
    ("p7_barrel_metal_55gal_blue", (1.0, 1.0), 2),
    ("p7_crate_wood_01", (1.0, 1.0), 2),
    ("p7_crate_wood_01_short", (1.0, 1.0), 2),
    ("p7_foliage_hedge_round_48_48_36", (0.9, 1.3), 3),
    ("p7_foliage_tree_acacia_bush", (0.8, 1.2), 2),
    ("p7_wheel_barrow_street_vendor", (1.0, 1.0), 1),
)
#: Overhead layer (over head height, seen over walls): trees.
OVERHEAD: tuple[tuple[str, tuple[float, float], int], ...] = (
    ("p7_foliage_tree_olive_small", (1.8, 2.6), 3),
    ("p7_foliage_tree_albizia_tall_full", (0.7, 1.0), 1),
)
#: Wrecks big enough to be a landmark and a pinch point.
WRECKS: tuple[str, ...] = ("veh_t7_city_car_static_dead", "veh_t7_civ_truck_semi_flatbed")


def register_boxes() -> None:
    """Put :data:`STOCK_BOXES` into ``MODEL_BOX`` (``setdefault``)."""
    from ..recipes.props import MODEL_BOX

    for name, box in STOCK_BOXES.items():
        MODEL_BOX.setdefault(name, box)  # type: ignore[attr-defined]


def _pick(rng: random.Random, palette) -> tuple[str, float]:
    total = sum(w for _, _, w in palette)
    r = rng.uniform(0, total)
    for model, (s0, s1), w in palette:
        r -= w
        if r <= 0:
            return model, rng.uniform(s0, s1)
    model, (s0, s1), _ = palette[-1]
    return model, rng.uniform(s0, s1)


def layered(
    rng: random.Random,
    rect: tuple[float, float, float, float],
    floor_z: float,
    *,
    ground: int,
    waist: int = 0,
    overhead: int = 0,
    accept: Callable[[float, float, float], bool] | None = None,
    palettes: tuple = (GROUND, WAIST, OVERHEAD),
    spacing: float = 18.0,
    tries: int = 12,
) -> list[PropSpec]:
    """Dress the floor rectangle ``(x0, y0, x1, y1)`` at three heights:
    *ground* walk-through pieces, *waist* solid pieces, *overhead* trees.

    ``accept(x, y, radius)`` may refuse a spot (a path, a doorway, a buy);
    each piece tries *tries* spots and is dropped if none is accepted.
    Pieces keep *spacing* (ground) or their own footprint radius (the rest)
    apart.
    """
    register_boxes()
    from ..recipes.props import MODEL_BOX

    x0, y0, x1, y1 = rect
    taken: list[tuple[float, float, float]] = []
    out: list[PropSpec] = []
    for layer, count, palette in (("ground", ground, palettes[0]), ("waist", waist, palettes[1]),
                                  ("overhead", overhead, palettes[2])):
        for _ in range(count):
            model, scale = _pick(rng, palette)
            if layer == "waist":
                scale = 1.0          # a solid prop's collmap is its unscaled box (Z21)
            (a, b, _), (c, d, _) = MODEL_BOX[model]
            radius = spacing if layer == "ground" else 0.5 * math.hypot(c - a, d - b) * scale
            if layer == "overhead":
                radius = min(radius, 48.0)   # the trunk stands on the floor; the canopy is overhead
            for _ in range(tries):
                x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
                if accept is not None and not accept(x, y, radius if layer != "ground" else 8.0):
                    continue
                if any((x - tx) ** 2 + (y - ty) ** 2 < (max(radius, tr) if layer != "ground" else spacing) ** 2
                       for tx, ty, tr in taken):
                    continue
                taken.append((x, y, radius))
                spec = on_floor(model, x, y, floor_z, rng.uniform(0, 360), solid=layer == "waist",
                                scale=scale)
                # on_floor rests the unscaled box; a scaled one's underside moves
                # with the scale (Z44 found rocks floating 2 units).
                z0 = MODEL_BOX[model][0][2]
                at = spec[1]
                out.append((spec[0], type(at)(at.x, at.y, floor_z - z0 * scale), *spec[2:]))
                break
    return out


def pinch_point(
    model: str,
    centre: tuple[float, float],
    along_x: bool,
    corridor: float,
    clear: float,
    floor_z: float,
    *,
    side: int = 1,
    yaw_jitter: float = 0.0,
) -> PropSpec:
    """A solid set piece lying along a corridor so that *clear* units of the
    corridor's *corridor* width stay open, on the side opposite *side*
    (+1 or -1).  The corridor runs along x when *along_x*, centred on
    *centre*.  The piece's long axis is laid along the corridor."""
    register_boxes()
    from ..recipes.props import MODEL_BOX

    (a, b, _), (c, d, _) = MODEL_BOX[model]
    long_x = (c - a) >= (d - b)
    yaw = (0.0 if long_x == along_x else 90.0) + yaw_jitter
    depth = min(c - a, d - b)
    # The piece's near face sits `clear` in from the open side of the corridor.
    offset = side * (clear + depth / 2.0 - corridor / 2.0)
    cx, cy = centre
    x, y = (cx, cy + offset) if along_x else (cx + offset, cy)
    return on_floor(model, x, y, floor_z, yaw, solid=True)


def light_pool_points(
    candidates: Sequence[tuple[float, float]],
    radius: float,
    *,
    dark_gap: float = 0.6,
) -> list[tuple[float, float]]:
    """Choose lamp spots from *candidates* (in the given order of priority)
    so no two pools of *radius* overlap and a gap of ``dark_gap x radius``
    of darkness lies between them: pooled light, not a flood."""
    min_d = radius * (2.0 + dark_gap)
    chosen: list[tuple[float, float]] = []
    for x, y in candidates:
        if all((x - a) ** 2 + (y - b) ** 2 >= min_d ** 2 for a, b in chosen):
            chosen.append((x, y))
    return chosen


def light_pools(
    bp,
    spots: Sequence[tuple[float, float]],
    floor_z: float,
    *,
    colour: tuple[float, float, float],
    radius: float,
    zone: str | None = None,
    height: float = 64.0,
    fixture: str | None = "p7_zm_der2_light_hurricane_lamp",
    ident: str = "pool",
) -> list[PropSpec]:
    """A light of *radius* at *height* over each spot, with its *fixture*
    (a lantern on the ground by default) under it; returns the fixture props
    for the caller to place."""
    items: list[PropSpec] = []
    from ..spatial import Point

    for n, (x, y) in enumerate(spots):
        bp.place_light(Point(x, y, floor_z + height), colour=colour, radius=radius,
                       zone_name=zone, id=f"{ident}_{n}")
        if fixture:
            items.append(on_floor(fixture, x, y, floor_z, (n * 47) % 360, solid=False))
    return items
