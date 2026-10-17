"""A stock model's box is read in its root bone's frame, where the engine draws it."""

from __future__ import annotations

import pytest

from zmforge.props.origins import drawn_box, drawn_boxes, stock_origins
from zmforge.recipes.props import CATALOGUE_BOX, MODEL_BOX

DUCT = "p7_duct_metal_circular_straight_32"


def test_the_duct_draws_on_its_origin_not_150_units_off():
    raw = CATALOGUE_BOX[DUCT]
    assert raw[0][1] == pytest.approx(133.435)  # the catalogue's scene-frame box
    (x0, y0, z0), (x1, y1, z1) = drawn_box(DUCT, raw)
    assert (y0, y1) == pytest.approx((-16.565, 16.565))
    assert (x0, x1, z0, z1) == pytest.approx((raw[0][0], raw[1][0], raw[0][2], raw[1][2]))


def test_a_drawn_box_is_the_raw_box_less_the_root_bone_when_it_is_not_turned():
    for name, entry in stock_origins().items():
        if "axes" in entry:
            continue
        for i in range(2):
            for j in range(3):
                assert entry["drawn"][i][j] == pytest.approx(
                    entry["raw"][i][j] - entry["root"][j], abs=0.002), name


def test_only_the_raw_catalogue_box_is_corrected():
    drawn = drawn_box(DUCT, CATALOGUE_BOX[DUCT])
    assert drawn_box(DUCT, drawn) == drawn           # already corrected: a no-op
    hand = ((-10.0, -10.0, 0.0), (10.0, 10.0, 5.0))
    assert drawn_box(DUCT, hand) == hand             # a box cut by hand passes through
    assert drawn_box("zmf_prop_hand_cart", MODEL_BOX["zmf_prop_hand_cart"]) == MODEL_BOX["zmf_prop_hand_cart"]
    assert drawn_box(DUCT, None) is None
    # JSON-shaped (lists) boxes from a stored model document are matched too.
    as_lists = [list(CATALOGUE_BOX[DUCT][0]), list(CATALOGUE_BOX[DUCT][1])]
    assert drawn_box(DUCT, as_lists) == drawn


def test_every_moved_model_the_palette_carries_is_the_catalogue_box():
    """If CATALOGUE_BOX drifts from the catalogue the correction silently stops."""
    moved = [name for name in CATALOGUE_BOX if name in stock_origins()]
    assert len(moved) >= 40
    for name in moved:
        assert drawn_box(name, CATALOGUE_BOX[name]) != CATALOGUE_BOX[name] or (
            stock_origins()[name]["raw"] == stock_origins()[name]["drawn"]), name


def test_the_recipes_place_by_the_drawn_box():
    """MODEL_BOX, which every recipe places by, is corrected at source."""
    assert MODEL_BOX[DUCT][0][1] == pytest.approx(-16.565)
    for name in CATALOGUE_BOX:
        assert MODEL_BOX[name] == drawn_box(name, CATALOGUE_BOX[name]), name
        assert drawn_box(name, MODEL_BOX[name]) == MODEL_BOX[name], name  # no double correction


def test_the_checks_read_the_drawn_table():
    from zmforge.placement.audit import _model_boxes as audit_boxes
    from zmforge.verify.approach import _model_boxes as approach_boxes

    for table in (audit_boxes(None), approach_boxes()):
        assert table[DUCT][0][1] == pytest.approx(-16.565)
    assert len(drawn_boxes(MODEL_BOX)) == len(MODEL_BOX)
