"""The generated late-season corn stalks (props/corn.py) that replaced Kenney's."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from zmforge.props.build import game_mesh
from zmforge.props.library import CORN_LEAF, prop
from zmforge.recipes.props import MODEL_BOX

STALKS = ("zmf_prop_corn_stalk", "zmf_prop_corn_stalk_thin")


@pytest.mark.parametrize("name", STALKS)
def test_the_generated_stalk_fills_the_kit_stalks_box_exactly(name: str, tmp_path: Path) -> None:
    """The maze is laid out by MODEL_BOX; a new mesh under the old name must hit it."""
    game, scale, _note = game_mesh(prop(name), tmp_path)
    lo, hi = game.bounds()
    want_lo, want_hi = MODEL_BOX[name]
    assert scale == pytest.approx(1.0)
    for got, want in zip(lo + hi, want_lo + want_hi):
        assert got == pytest.approx(want, abs=0.002)


#: 492 and 452 since the stalks went to 18 leaves (props/corn.py, VARIANTS),
#: with a little room; the hard ceiling is the library entry's max_triangles.
@pytest.mark.parametrize("name, most", [("zmf_prop_corn_stalk", 500),
                                        ("zmf_prop_corn_stalk_thin", 460)])
def test_the_stalk_stays_a_few_hundred_triangles(name: str, most: int, tmp_path: Path) -> None:
    game, _scale, note = game_mesh(prop(name), tmp_path)
    assert len(game.triangles) <= most <= prop(name).max_triangles
    assert "left alone" in note  # never decimated: the budget is the design
    parts = Counter(t.material for t in game.triangles)
    assert set(parts) == {"stem", "leaf", "ear", "tassel"}


def test_leaves_are_double_sided(tmp_path: Path) -> None:
    """Prop materials cull back faces; the player looks up at leaf undersides."""
    game, _s, _n = game_mesh(prop("zmf_prop_corn_stalk"), tmp_path)
    leaf = [t for t in game.triangles if t.material == "leaf"]
    corners = Counter(frozenset(tuple(round(c, 4) for c in game.positions[i]) for i in t.position)
                      for t in leaf)
    assert corners and all(n == 2 for n in corners.values())


def test_the_stalks_use_the_graded_leaf_photo_and_stay_walk_through() -> None:
    for name in STALKS:
        entry = prop(name)
        assert entry.material == CORN_LEAF and entry.solid is False
    assert CORN_LEAF.source == "ambientcg_leaf_001"
    assert CORN_LEAF.grade is not None and CORN_LEAF.grade_end is not None
    # Olive at the leaf base, straw at the tip: the end is lighter and warmer.
    assert sum(CORN_LEAF.grade_end) > sum(CORN_LEAF.grade)
