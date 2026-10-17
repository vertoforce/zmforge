"""The shared vignette library (dressing.vignette) and its corn maze use."""

from __future__ import annotations

import math
import random

import pytest

from zmforge.blueprint.elements import PropScatter
from zmforge.dressing import vignette as vg
from zmforge.recipes.corn_maze import corn_maze_map
from zmforge.recipes.props import MODEL_BOX


@pytest.fixture(scope="module")
def built():
    return corn_maze_map("zm_corn_maze")


def test_every_kind_is_a_one_line_story_built_from_measured_models() -> None:
    assert len(vg.KINDS) >= 12
    spot = vg.Spot(0.0, 0.0, 0.0, 90.0, "dead_end", "r", width=220.0, back=68.0, reach=80.0)
    for kind in vg.KINDS.values():
        assert kind.story and "\n" not in kind.story and kind.story.endswith(".")
        assert set(kind.fits) <= set(vg.SPOT_KINDS)
        parts = kind.build(random.Random(1), spot)
        items = [p for p in parts if isinstance(p, vg.Item)]
        assert 5 <= len(items) <= 30, (kind.name, len(items))
        assert [p for p in parts if getattr(p, "core", False)], kind.name
        for item in items:
            assert item.model in MODEL_BOX, (kind.name, item.model)


def test_a_vignette_is_all_or_nothing_for_its_core_parts(built) -> None:
    class No(vg.SimplePlacer):
        def fits(self, *a, **k):
            return False

    before = len(vg.vignettes_of(built))
    spot = vg.Spot(0.0, 0.0, 0.0, 0.0, "wall_face", "r", width=180.0, back=50.0, reach=14.0)
    assert vg.place_vignette(built, "lost_child", spot, random.Random(2), No(built), ident="t") is None
    assert len(vg.vignettes_of(built)) == before


def test_the_corn_maze_has_a_vignette_every_two_to_three_corridor_segments(built) -> None:
    c = built.vignette_counts
    assert c["corridor"] >= c["segments"] / 3.0, c
    # dead ends: 13 of the 17 x 17 maze's 23
    assert c["dead_end"] >= 12 and c["clearing"] + c["rim"] >= 10, c
    assert len(c["kinds"]) >= 12, c["kinds"]


def test_no_story_repeats_close_by(built) -> None:
    from zmforge.recipes.corn_maze_vignettes import SAME_KIND_GAP

    placed = [v for v in vg.vignettes_of(built) if v.room != "r"]
    for a in placed:
        for b in placed:
            if a is not b and a.kind == b.kind:
                assert math.dist(a.focus[:2], b.focus[:2]) >= SAME_KIND_GAP * 0.8, (a.kind, a.focus, b.focus)


def test_the_cameras_aim_at_vignettes(built) -> None:
    from zmforge.dressing.scene import scenes_of

    focus = {f for s in scenes_of(built) for f in s.focus}
    assert sum(1 for v in vg.vignettes_of(built) if v.focus in focus) >= 12


def test_the_map_stays_under_the_32000_prop_cap(built) -> None:
    assert sum(len(s.props) for s in built.elements(PropScatter)) <= 32000
