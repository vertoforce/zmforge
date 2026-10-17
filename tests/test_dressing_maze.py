"""The shared maze generator (zmforge.dressing.maze)."""

from __future__ import annotations

from zmforge.dressing.maze import Maze, carve_maze, pair, wall_runs


def test_same_seed_same_maze_and_every_cell_reachable() -> None:
    a = carve_maze(12, 9, "seed", start=(0, 0))
    b = carve_maze(12, 9, "seed", start=(0, 0))
    assert a == b
    assert a.connected((0, 0))
    assert a.loops() == 0            # a pure carve is a spanning tree
    assert carve_maze(12, 9, "other", start=(0, 0)) != a


def test_loops_add_cycles_without_losing_dead_ends() -> None:
    tree = carve_maze(15, 15, "loops", start=(0, 0))
    looped = carve_maze(15, 15, "loops", start=(0, 0), loops=12)
    assert looped.loops() == 12
    assert set(tree.dead_ends()) == set(looped.dead_ends())
    assert carve_maze(15, 15, "loops", start=(0, 0), loop_ratio=0.1).loops() == round(0.1 * 225)


def test_dead_end_ratio_braids_down_to_the_target_and_keeps_the_kept() -> None:
    tree = carve_maze(20, 20, "braid", start=(0, 0))
    keep = tree.dead_ends()[:3]
    braided = carve_maze(20, 20, "braid", start=(0, 0), dead_end_ratio=0.05, keep_dead_ends=keep)
    assert len(tree.dead_ends()) > 0.05 * 400
    assert len(braided.dead_ends()) <= 0.05 * 400
    assert set(keep) <= set(braided.dead_ends())
    assert braided.loops() > 0


def test_allowed_and_rationed_walls() -> None:
    # Two rooms side by side (x < 5, x >= 5), joined only at one door pair.
    door = pair((4, 2), (5, 2))

    def allowed(a, b) -> bool:
        return (a[0] < 5) == (b[0] < 5) or pair(a, b) == door

    m = carve_maze(10, 5, "rooms", start=(0, 0), allowed=allowed, loops=6)
    crossings = [p for p in m.passages if (p[0][0] < 5) != (p[1][0] < 5)]
    assert crossings == [door]
    assert m.connected((0, 0))


def test_open_blocks_make_clearings_and_cells_can_have_holes() -> None:
    hole = {(i, j) for i in range(3, 6) for j in range(3, 6)}
    cells = [(i, j) for i in range(9) for j in range(9) if (i, j) not in hole]
    block = [(0, 0), (1, 0), (0, 1), (1, 1)]
    m = carve_maze(9, 9, "holes", start=(8, 8), cells=cells, open_blocks=[block])
    assert not any(a in hole or b in hole for a, b in m.passages)
    assert {pair((0, 0), (1, 0)), pair((0, 0), (0, 1)), pair((1, 0), (1, 1)), pair((0, 1), (1, 1))} <= m.passages
    assert m.connected((8, 8))


def test_wall_runs_cover_every_closed_wall_once() -> None:
    m: Maze = carve_maze(6, 6, "walls", start=(0, 0), loops=3)
    boxes = wall_runs(m.passages, (0, 0, 6, 6), (0.0, 0.0), 100.0, 10.0, 0.0, 200.0)
    # Every closed interior wall's midpoint lies inside exactly one box.
    for i in range(6):
        for j in range(6):
            for (di, dj) in ((1, 0), (0, 1)):
                a, b = (i, j), (i + di, j + dj)
                if b[0] >= 6 or b[1] >= 6:
                    continue
                mx = (i + 0.5) * 100 + di * 50
                my = (j + 0.5) * 100 + dj * 50
                hits = [bx for bx in boxes
                        if bx.mins.x <= mx <= bx.maxs.x and bx.mins.y <= my <= bx.maxs.y]
                assert len(hits) == (0 if pair(a, b) in m.passages else 1), (a, b, len(hits))


def test_the_corn_maze_carve_is_the_library_carve() -> None:
    """zm_corn_maze's passages are the shared carve's (v2 layout).  The v1
    maze came out identical from the library before the switch."""
    from zmforge.recipes import corn_maze as cm
    from zmforge.recipes import corn_maze_layout as lay

    assert cm.maze_passages() == lay.carve()[0].passages


def test_the_corn_maze_v2_layout() -> None:
    """The v2 layout, 17 x 17 cells (half the 24 x 24 field, about v1's
    area; corn_maze_layout), every cell reachable, four gates at rising
    prices, loops and dead ends."""
    from zmforge.recipes import corn_maze as cm
    from zmforge.recipes import corn_maze_layout as lay

    s = lay.stats()
    assert s["connected"]
    area = (lay.SIZE * lay.PITCH) ** 2 / (15 * 288.0) ** 2   # v1: 15 cells of 288
    assert 0.95 <= area <= 1.1, area
    assert lay.SIZE == 17
    prices = [g.price for g in lay.GATES]
    assert prices == sorted(prices) and len(prices) == 4
    assert s["loops"] >= 20 and 20 <= s["dead_ends"] <= 0.1 * s["cells"]
    assert s["secrets"] >= 2
    maze, _ = lay.carve()
    crossings = {lay.zone_of(a) + "|" + lay.zone_of(b) for a, b in maze.passages if lay.zone_of(a) != lay.zone_of(b)}
    assert len(crossings) == 3            # the three zone gates inside the ring; the heart's is a door
