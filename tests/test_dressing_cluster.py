"""Natural clustering (``zmforge.dressing.cluster``) and the evenness check
``Z66`` (``verify/evenness.py``): clumps measure clumped, an even scatter
measures even, the check fires on the one and not on the other."""

from __future__ import annotations

import math
import random

from zmforge.blueprint.elements import Room
from zmforge.dressing import on_floor
from zmforge.dressing.cluster import (
    EVEN_R,
    MIN_FOLIAGE,
    Tier,
    clark_evans,
    clustered_points,
    edge_distance,
    is_foliage,
    mixed_clumps,
    nn_distances,
    rect_edges,
)
from zmforge.recipes.layouts import three_room_map
from zmforge.verify import check_blueprint
from zmforge.verify.evenness import check_foliage_evenness, foliage_evenness

RECT = (0.0, 0.0, 2000.0, 2000.0)
AREA, PERIM = 2000.0 * 2000.0, 8000.0
GRASS = "p7_foliage_grass_tall_cluster_sml"
BUSH = "p7_foliage_tree_acacia_bush"


def _uniform(n: int, seed: str = "u"):
    rng = random.Random(seed)
    return [(rng.uniform(0, 2000), rng.uniform(0, 2000)) for _ in range(n)]


def test_clark_evans_reads_random_regular_and_clumped() -> None:
    r_random = clark_evans(_uniform(600), AREA, PERIM)
    grid = [(50.0 + 100.0 * i, 50.0 + 100.0 * j) for i in range(20) for j in range(20)]
    r_grid = clark_evans(grid, AREA, PERIM)
    clumps = clustered_points(random.Random("c"), RECT, 600, clumps=60, spread=30.0)
    r_clumps = clark_evans([(x, y) for x, y, _ in clumps], AREA, PERIM)
    assert 0.9 <= r_random <= 1.1, r_random
    assert r_grid > 1.8, r_grid
    assert r_clumps < 0.6, r_clumps
    assert clark_evans([(0.0, 0.0)], AREA) is None


def test_nearest_neighbours_match_brute_force() -> None:
    pts = _uniform(300, "nn")
    fast = nn_distances(pts)
    slow = [min(math.hypot(x - a, y - b) for j, (a, b) in enumerate(pts) if j != i)
            for i, (x, y) in enumerate(pts)]
    assert all(abs(f - s) < 1e-9 for f, s in zip(fast, slow))


def test_clustered_points_are_seeded_and_lean_on_edges_and_off_the_walk() -> None:
    wall = rect_edges(*RECT)
    walk = [(0.0, 1000.0, 2000.0, 1000.0, 80.0)]
    a = clustered_points(random.Random(7), RECT, 500, edges=wall, avoid=walk, edge_reach=150.0)
    b = clustered_points(random.Random(7), RECT, 500, edges=wall, avoid=walk, edge_reach=150.0)
    assert a == b and len(a) == 500
    assert all(abs(y - 1000.0) >= 80.0 for _x, y, _c in a)
    near = sum(min(edge_distance(x, y, e)[0] for e in wall) < 300.0 for x, y, _ in a)
    # A uniform scatter puts 51% of points within 300 of the square's edge.
    assert near / len(a) > 0.7, near / len(a)


def test_mixed_clumps_put_a_core_with_smaller_pieces_round_it() -> None:
    tiers = (Tier(((BUSH, (1.0, 1.2), 1),), (1, 1), (0.0, 10.0)),
             Tier(((BUSH, (0.5, 0.7), 1),), (1, 3), (40.0, 80.0)),
             Tier(((GRASS, (0.8, 1.2), 1),), (3, 6), (50.0, 120.0)))
    taken: list[tuple[float, float]] = []

    def place(model, x, y, yaw, scale):
        if any(math.hypot(x - a, y - b) < 12.0 for a, b in taken):
            return False
        taken.append((x, y))
        return True

    got = mixed_clumps(random.Random("m"), RECT, tiers, 300, place=place, parent_gap=150.0)
    assert len(got) == 300
    cores = {p.clump: p for p in got if p.tier == 0}
    rings = [p for p in got if p.tier == 1]
    assert rings and all(p.clump in cores for p in got)
    for p in rings:
        c = cores[p.clump]
        assert math.hypot(p.x - c.x, p.y - c.y) < 150.0
    r = clark_evans([(p.x, p.y) for p in got], AREA, PERIM)
    assert r < 0.8, r
    again = mixed_clumps(random.Random("m"), RECT, tiers, 300,
                         place=lambda *a: True, parent_gap=150.0)
    assert len(again) == 300


def test_is_foliage() -> None:
    assert is_foliage(GRASS) and is_foliage("p7_foliage_hedge_box_48_48_36")
    assert is_foliage("p7_3arc_park_leaves_grp_2") and is_foliage("p7_foliage_plant_meskel_3_noflower")
    assert not is_foliage("p7_gib_chunk_bone_01") and not is_foliage("zmf_prop_corn_stalk")


# -- Z66 -------------------------------------------------------------------
def _room_map(points):
    bp = three_room_map("zm_even_probe")
    room = next(r for r in bp.elements(Room) if r.id == "arena_room")
    i = room.interior
    w, h = i.maxs.x - i.mins.x, i.maxs.y - i.mins.y
    items = [on_floor(GRASS, i.mins.x + 20 + fx * (w - 40), i.mins.y + 20 + fy * (h - 40),
                      room.floor_z, 0.0, solid=False) for fx, fy in points]
    bp.place_props(items, id="probe_grass")
    return bp


def test_an_even_lawn_warns_z66(past_the_lane_rule) -> None:
    n = 12
    grid = [((i + 0.5) / n, (j + 0.5) / n) for i in range(n) for j in range(n)]
    bp = _room_map(grid)
    row = next(r for r in foliage_evenness(bp) if r["room"] == "arena_room")
    assert row["foliage"] == n * n and row["r"] >= EVEN_R
    found = [f for f in check_foliage_evenness(bp).warnings if f.code == "Z66"]
    assert len(found) == 1 and "arena_room" in str(found[0])
    assert any(f.code == "Z66" for f in check_blueprint(bp).warnings)


def test_clumped_planting_does_not() -> None:
    rng = random.Random("clumped")
    pts = []
    for _ in range(12):
        cx, cy = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        pts += [(min(max(cx + rng.gauss(0, 0.02), 0.0), 1.0),
                 min(max(cy + rng.gauss(0, 0.02), 0.0), 1.0)) for _ in range(12)]
    bp = _room_map(pts)
    row = next(r for r in foliage_evenness(bp) if r["room"] == "arena_room")
    assert row["foliage"] >= MIN_FOLIAGE and row["r"] < EVEN_R
    assert not check_foliage_evenness(bp).warnings


def test_a_few_plants_are_not_asked() -> None:
    bp = _room_map([((i + 0.5) / 5, 0.5) for i in range(5)])
    assert not check_foliage_evenness(bp).warnings
