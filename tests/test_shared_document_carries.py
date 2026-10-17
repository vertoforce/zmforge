"""What the shared document carries so a map can be rebuilt as the same bytes.

The ``editor`` half of ``<name>.blueprint.json`` is a description of a map, and
the test of a description is whether the thing can be built again from it.  The
byte-for-byte proof belongs to whatever reads the document back; these are
the facts this side has to write down for that proof to be possible, and the
places where two ways of writing the same fact were being written two ways.
"""

from __future__ import annotations

import pytest


from zmforge import mapdoc
from zmforge.recipes.pranks import prank_map



# --- one way of writing one fact ---------------------------------------------------
def test_a_prop_carries_its_own_name_and_keeps_one_it_was_given() -> None:
    """The name is what the prop's GUID is derived from, so it has to be a field.

    Were it the prop's place in its scatter, a prop inserted by another writer
    would renumber every prop after it and every GUID with it - and the join between the
    document, the `.map` and a person's edits in Radiant is the GUID.
    """
    from zmforge.blueprint.elements import Prop, PropScatter
    from zmforge.spatial import Point

    scatter = PropScatter(id="dressing_hall", props=[
        Prop("p7_zm_prop_chair", Point(0, 0, 0), 0.0),
        Prop("p7_zm_prop_chair", Point(64, 0, 0), 0.0, id="chair_by_the_door"),
    ])
    assert [p.id for p in scatter.props] == ["dressing_hall_0", "chair_by_the_door"]


def test_a_full_turn_is_stored_and_written_as_no_turn() -> None:
    """A heading is a direction, not a count of turns.

    A prop turned a full circle is written `0 360 0` in the map file, and the
    same prop rebuilt through the document - which folds on the way in - comes
    out `0 0 0`: the same facing, two files.
    """
    from zmforge.blueprint.elements import Prop
    from zmforge.emit.mapfile import _angle_text
    from zmforge.spatial import Angles, Point

    assert Prop("p7_zm_prop_chair", Point(0, 0, 0), 360.0).yaw == 0.0
    assert Prop("p7_zm_prop_chair", Point(0, 0, 0), -90.0).yaw == 270.0
    assert _angle_text(Angles(0.0, 360.0, 0.0)) == "0 0 0"
    assert _angle_text(Angles(0.0, -90.0, 0.0)) == "0 270 0"


def test_the_terrain_record_writes_every_number_as_a_number() -> None:
    """`Point` does not coerce, so a recipe can anchor a patch at three ints.

    The same map rebuilt from its own document holds three floats, and
    `json.dumps` spells those `1624` and `1624.0`: the same anchor, six
    different bytes, in a file whose whole job is to be compared.
    """
    from zmforge.spatial import Point
    from zmforge.surfaces.field import HeightField
    from zmforge.surfaces.ground import TerrainRecord

    record = TerrainRecord(anchor=Point(1624, -552, 16), cell=64,
                           heights=HeightField.from_rows([[0, 1], [2, 3]]),
                           settings={"chunk": 8, "lift": 2, "material": "t7_dirt"})
    written = record.to_dict()
    assert written["anchor"] == [1624.0, -552.0, 16.0]
    assert all(isinstance(v, float) for v in written["anchor"])
    assert isinstance(written["cell"], float)
    assert all(isinstance(h, float) for row in written["heights"] for h in row)
    assert written["settings"] == {"chunk": 8.0, "lift": 2.0, "material": "t7_dirt"}


def test_the_document_writes_a_position_as_three_floats() -> None:
    from zmforge.spatial import Point

    assert mapdoc._plain(Point(1260, 700, 288.0)) == [1260.0, 700.0, 288.0]


# --- putting the order back --------------------------------------------------------
def test_reorder_puts_the_recorded_ids_first_and_leaves_the_rest_alone() -> None:
    """Stable and partial on purpose: an id the order does not name - a block
    somebody drew after the map was generated - lands after the recorded ones
    and does not move anything else."""
    bp = prank_map("zm_reorder_test")
    original = [e.id for e in bp.elements()]
    shuffled = list(reversed(original))
    bp.reorder(shuffled)
    assert [e.id for e in bp.elements()] == shuffled
    bp.reorder(original[:5])
    assert [e.id for e in bp.elements()][:5] == original[:5]
    assert [e.id for e in bp.elements()][5:] == [i for i in shuffled if i not in original[:5]]


def test_a_barricade_can_be_declared_over_a_hole_that_is_already_there() -> None:
    """`add_window` is for a caller with nothing yet; this is for one that has
    the hole, the yard and the riser already - which is what the editor's
    document is.  Without it the boards are a plain prefab, and
    `check_nav_apertures` then refuses the 96 x 48 hole the shipped recipes cut,
    because it exempts one only when a `Window` names it."""
    from zmforge import verify
    from zmforge.blueprint.elements import Window

    bp = prank_map("zm_declared_barricade")
    window = bp.elements(Window)[0]
    room, index, riser = window.room_id, window.aperture_index, window.riser_id
    bp._elements.remove(window)
    del bp._by_id[window.id]
    assert [f.code for f in verify.check_nav_apertures(bp).errors] == ["N3"]

    again = bp.declare_barricade(room, index, riser=riser, prefab=window.prefab,
                                 id=f"{window.id}_declared")
    assert (again.barricade_origin, again.barricade_yaw, again.link_tag) == (
        window.barricade_origin, window.barricade_yaw, window.link_tag)
    assert (again.yard_id, again.zone_name, again.side) == (
        window.yard_id, window.zone_name, window.side)
    assert not verify.check_nav_apertures(bp).errors


def test_a_block_painted_a_face_at_a_time_carries_every_side() -> None:
    """A crate with a metal lid and a brick end is three materials, not one.

    The document held one ``texture`` per block and the writer picked the first
    face that was not caulk, so the box came back painted all over in the lid's
    metal - no gap, no note, and the wood and the brick simply gone.  ``texture``
    is the default the unnamed faces are painted with and ``faces`` names the
    rest, spelled the editor's way (``ceiling``, not ``top``).
    """
    from zmforge import Blueprint, FaceMaterials, Material, Side
    from zmforge.spatial import Bounds

    bp = Blueprint("zm_two_tone", seed="zm_two_tone")
    bp.add_block(
        Bounds.between((256, 64, 16), (320, 128, 80)),
        FaceMaterials(default=Material("t7_wood_planks_worn"),
                      per_side={Side.TOP: Material("t7_metal_worn_iron_dark"),
                                Side.NORTH: Material("t7_brick_worn_heavy_grout_red")}),
        id="crate_two_tone",
    )
    block = mapdoc.editor_document(bp)["blocks"][0]
    assert block["texture"] == "t7_wood_planks_worn"
    assert block["faces"] == {"ceiling": "t7_metal_worn_iron_dark",
                              "north": "t7_brick_worn_heavy_grout_red"}
    # and the hull rule - caulk under one visible face - still says it in one
    # word, so a hung picture is not written twice.
    bp.add_block(Bounds.between((0, 0, 16), (64, 8, 80)),
                 FaceMaterials.only_visible_on(Side.SOUTH, Material("t7_zm_der_tile_hexagon")),
                 id="picture_panel")
    panel = mapdoc.editor_document(bp)["blocks"][1]
    assert panel["texture"] == "t7_zm_der_tile_hexagon" and panel["facing"] == "south"
    assert "faces" not in panel
