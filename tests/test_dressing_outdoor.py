"""Outdoor set dressing blocks (zmforge.dressing.outdoor)."""

from __future__ import annotations

import random

from zmforge.blueprint.installed import judge_misc_model, load_ledger
from zmforge.dressing import outdoor


def _model(p):
    return p[0] if isinstance(p, tuple) else p.model


def test_every_palette_model_links_locally_and_has_a_box() -> None:
    from zmforge.recipes.props import MODEL_BOX

    outdoor.register_boxes()
    ledger = load_ledger()
    names = {m for pal in (outdoor.GROUND, outdoor.WAIST, outdoor.OVERHEAD) for m, _, _ in pal}
    names |= set(outdoor.WRECKS)
    for name in sorted(names):
        assert name in MODEL_BOX, name
        if ledger is not None:
            assert judge_misc_model(name, ledger) == "ok", name


def test_layered_fills_three_heights_and_respects_accept() -> None:
    rng = random.Random("layers")
    path = (-50.0, 50.0)   # a path down the middle, x in [-50, 50]

    def accept(x, y, r):
        return not (path[0] - r < x < path[1] + r)

    items = outdoor.layered(rng, (-500, -500, 500, 500), 0.0, ground=80, waist=10, overhead=3,
                            accept=accept)
    models = [_model(p) for p in items]
    ground = {m for m, _, _ in outdoor.GROUND}
    waist = {m for m, _, _ in outdoor.WAIST}
    over = {m for m, _, _ in outdoor.OVERHEAD}
    assert sum(m in ground for m in models) >= 60
    assert sum(m in waist for m in models) >= 5
    assert sum(m in over for m in models) >= 1
    for p in items:
        x = p[1].x
        assert not (path[0] < x < path[1]), p
    assert items == outdoor.layered(random.Random("layers"), (-500, -500, 500, 500), 0.0, ground=80,
                                    waist=10, overhead=3, accept=accept)


def test_pinch_point_leaves_the_asked_clearance() -> None:
    from zmforge.recipes.props import MODEL_BOX

    outdoor.register_boxes()
    model = "veh_t7_city_car_static_dead"
    spec = outdoor.pinch_point(model, (0.0, 0.0), True, 240.0, 64.0, 0.0, side=1)
    (a, b, _), (c, d, _) = MODEL_BOX[model]
    depth = min(c - a, d - b)
    # The corridor spans y in [-120, 120]; side=+1 pushes the car to +y,
    # leaving exactly 64 open between -120 and the car's -y face.
    from zmforge.dressing import turned_box

    _, y0, _, _ = turned_box(model, spec[2])
    assert abs((spec[1].y + y0) - (-120.0) - 64.0) < 0.01, (spec[1].y + y0, depth)
    assert spec[4] is True


def test_light_pools_leave_dark_between() -> None:
    cands = [(x * 50.0, 0.0) for x in range(40)]
    pts = outdoor.light_pool_points(cands, 200.0, dark_gap=0.5)
    assert len(pts) >= 3
    for (a, _), (b, _) in zip(pts, pts[1:]):
        assert b - a >= 500.0
