"""A solid prop placed by the tuple form gets its collision box for free.

``use_collmap "1"`` on a model with no collmap file is the silent failure
``Z21`` exists to catch: ``cod2map64`` bakes nothing, prints nothing, and the
player walks through the furniture.  The recipes that build a
:class:`~zmforge.blueprint.elements.Prop` by hand pass ``collision_box`` with
the flag, but the short ``(model, point, yaw, scale, solid)`` tuple has no
room for one, so a kit prop declared solid in ``props.library`` (a lollipop,
for one) reached the map with the flag and no box.
:meth:`~zmforge.blueprint.model.Blueprint.place_props` now fills it from the
same measured table the recipes read.

These tests live apart from ``test_props.py`` because what they hold is the
blueprint call's contract, not a prop-layout rule.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint.elements import Prop
from zmforge.blueprint.model import Blueprint
from zmforge.errors import BlueprintError
from zmforge.recipes.props import MODEL_BOX
from zmforge.spatial import Point

#: The prop this bug was found on, and its measured box.
LOLLIPOP = "zmf_prop_lollipop"


def test_a_tuple_form_solid_prop_takes_the_models_measured_box():
    """No box in the tuple, so the table's box, not ``None``."""
    blueprint = Blueprint(name="zm_collision_default")
    scatter = blueprint.place_props(
        [(LOLLIPOP, Point(0.0, 0.0, 0.0), 90.0, 8.0, True)], id="kit_solid"
    )
    (prop,) = scatter.props
    assert prop.solid is True
    assert prop.collision_box == MODEL_BOX[LOLLIPOP]


def test_a_walk_through_prop_still_carries_no_box():
    """The default is only for the props that ask to be baked.

    A box on a walk-through prop would be written into
    ``share/raw/collmaps`` by the project and is exactly what stops zombies
    at a plant pot.
    """
    blueprint = Blueprint(name="zm_collision_default")
    scatter = blueprint.place_props(
        [(LOLLIPOP, Point(0.0, 0.0, 0.0), 90.0)], id="kit_loose"
    )
    (prop,) = scatter.props
    assert prop.solid is False
    assert prop.collision_box is None


def test_a_box_the_caller_spelled_out_wins():
    """A whole ``Prop`` is taken as written; this method does not second-guess it."""
    mine = ((-1.0, -2.0, 0.0), (1.0, 2.0, 3.0))
    assert mine != MODEL_BOX[LOLLIPOP]
    blueprint = Blueprint(name="zm_collision_default")
    scatter = blueprint.place_props(
        [
            Prop(
                model=LOLLIPOP,
                origin=Point(0.0, 0.0, 0.0),
                yaw=90.0,
                solid=True,
                collision_box=mine,
            )
        ],
        id="kit_hand_cut",
    )
    (prop,) = scatter.props
    assert prop.collision_box == mine


def test_a_model_with_no_measured_box_is_refused_by_name():
    """The error names the model, because that is what the fix needs.

    Guessing a box here would put collision somewhere the art is not.
    """
    unknown = "p7_a_model_nobody_measured"
    assert unknown not in MODEL_BOX
    blueprint = Blueprint(name="zm_collision_default")
    with pytest.raises(BlueprintError) as raised:
        blueprint.place_props(
            [(unknown, Point(0.0, 0.0, 0.0), 0.0, 1.0, True)], id="kit_unknown"
        )
    assert unknown in str(raised.value)


def test_a_stock_model_that_ships_its_own_collmap_keeps_none():
    """Treyarch authored a shape for these; a box of ours would replace it.

    The project only writes a collmap for a model outside
    :data:`~zmforge.props.collision.STOCK_COLLMAPS`, so ``None`` here is the
    instruction "use the install's", not a missing value.
    """
    from zmforge.props.collision import STOCK_COLLMAPS

    theirs = sorted(set(STOCK_COLLMAPS) - set(MODEL_BOX))
    assert theirs, "the install ships collmaps for models outside the box table"
    blueprint = Blueprint(name="zm_collision_default")
    scatter = blueprint.place_props(
        [(theirs[0], Point(0.0, 0.0, 0.0), 0.0, 1.0, True)], id="kit_stock"
    )
    (prop,) = scatter.props
    assert prop.solid is True
    assert prop.collision_box is None
