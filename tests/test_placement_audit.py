"""Z44: the layout relations asked of a finished map.

Every case here is a fault a prop audit can find on a generated map, shrunk
to the smallest room that shows it: a
clock lying in the floor tile, two desks drawn through each other, a bunk bed
with no corner on its plinth, a bench through a perk machine.  The fixtures
are built by hand rather than taken from a recipe so that each one fails for
exactly one reason and passes when that reason is removed -- a check that has
only ever been run on a map with hundreds of faults has not been shown to be
quiet about anything.

The two adapters are checked against a real recipe at the end, because the
rules are only worth their thresholds if a blueprint and the text written from
it are judged the same way.
"""

from __future__ import annotations

import pytest

from zmforge.emit.mapfile import build_document
from zmforge.mapsource.writer import render_map_text
from zmforge.placement.audit import (
    ITEM_MIN_HEIGHT,
    TERRAIN_SAMPLE,
    ItemFootprint,
    Layout,
    LayoutRoom,
    check_layout,
    layout_from_blueprint,
    layout_from_map_text,
)
from zmforge.placement.geometry import Poly2
from zmforge.placement.relations import MountKind, Placed, Surface, mount_kind_of_box
from zmforge.blueprint.model import Blueprint
from zmforge.spatial import Point, Span

#: The room every fixture below is furnished: 512 units square, floor at 16,
#: ceiling at 272, which is this generator's own storey height.
LOBBY = LayoutRoom("lobby", 0.0, 0.0, 512.0, 512.0, 16.0, 272.0)

#: A wall clock's box, the shape :func:`mount_kind_of_box` reads as a fixture:
#: centred on its origin in Z, 5 units through a 32-unit face.  The measured
#: ``p7_clock_metal_wall_01_base`` is this to within a unit.
CLOCK = ((-16.0, -2.5, -16.0), (16.0, 2.5, 16.0))

#: A hanging light's box: wholly below its own origin, because it is hung by
#: the point the box starts at.
CHANDELIER = ((-20.0, -20.0, -48.0), (20.0, 20.0, 0.0))

#: A desk: on its own base, 60 by 40 in plan and 30 tall.
DESK = ((-30.0, -20.0, 0.0), (30.0, 20.0, 30.0))

#: A bench, narrower than the desk and the same height, so a pair of them
#: shares height as well as floor.
BENCH = ((-36.0, -12.0, 0.0), (36.0, 12.0, 24.0))

#: A bunk bed: 90 by 60 and 60 tall, a piece meant to stand on a raised base.
BUNK = ((-45.0, -30.0, 0.0), (45.0, 30.0, 60.0))

#: A coffee cup: both plan sides under the 40-unit side the overlap rule
#: leaves alone.
CUP = ((-4.0, -4.0, 0.0), (4.0, 4.0, 7.0))


def placed(name, box, x, y, z, *, solid=True, room="lobby", ident="", yaw=0.0):
    """One prop, placed by the origin a ``.map`` would carry."""
    return Placed.from_model(name, box, (x, y, z), yaw, 1.0,
                             solid=solid, room=room, ident=ident)


def layout(props, *, surfaces=(), items=(), rooms=(LOBBY,), mounts=None):
    """A room with things in it, and the ground under them."""
    if mounts is None:
        mounts = {}
    return Layout(
        props=tuple(props),
        rooms=tuple(rooms),
        surfaces=tuple(surfaces),
        ground=tuple(room.floor for room in rooms),
        items=tuple(items),
        mounts=dict(mounts),
    )


def machine(x, y, z=16.0, *, half_width=32.0, depth=24.0):
    """A perk machine's own body, as ``blueprint.reach`` measures one."""
    return ItemFootprint(
        "perk_quick_revive", "the quick_revive machine",
        Poly2.rect(x - half_width, y - depth, x + half_width, y + depth),
        z - 8.0, z + 72.0,
    )


# --------------------------------------------------------------------------
# Rule 1: a fixture standing at floor level
# --------------------------------------------------------------------------
def test_a_clock_on_the_floor_is_reported() -> None:
    """A wall fixture at floor level, the most visible of these faults."""
    clock = placed("clock", CLOCK, 256.0, 256.0, 16.0)
    found = check_layout(layout([clock], mounts={"clock": mount_kind_of_box(CLOCK)}))
    assert len(found) == 1
    assert "wall fixture standing at floor level" in found[0].message


def test_the_same_clock_on_the_wall_is_not() -> None:
    """Same model, same room, mounted at reading height: nothing to say."""
    clock = placed("clock", CLOCK, 256.0, 8.0, 92.0)
    assert check_layout(layout([clock], mounts={"clock": mount_kind_of_box(CLOCK)})) == []


def test_a_chandelier_dealt_onto_the_floor_is_reported() -> None:
    """A box wholly below its origin is hung, and on a floor it is buried."""
    light = placed("chandelier", CHANDELIER, 256.0, 256.0, 16.0)
    found = check_layout(
        layout([light], mounts={"chandelier": mount_kind_of_box(CHANDELIER)})
    )
    assert len(found) == 1
    assert "ceiling fixture" in found[0].message
    assert "wholly under it" in found[0].message


def test_a_chandelier_under_the_ceiling_is_not() -> None:
    light = placed("chandelier", CHANDELIER, 256.0, 256.0, 268.0)
    assert check_layout(
        layout([light], mounts={"chandelier": mount_kind_of_box(CHANDELIER)})
    ) == []


def test_a_floor_standing_model_at_floor_level_is_not_a_mount_fault() -> None:
    """The rule is about the box, not about the height: a desk belongs here."""
    desk = placed("desk", DESK, 256.0, 256.0, 16.0)
    assert check_layout(layout([desk], mounts={"desk": MountKind.FLOOR})) == []


# --------------------------------------------------------------------------
# Rule 2: two solid props in the same place
# --------------------------------------------------------------------------
def test_two_desks_eighty_percent_inside_each_other_are_one_finding_naming_both() -> None:
    first = placed("desk", DESK, 200.0, 200.0, 16.0, ident="row_0")
    second = placed("bench", BENCH, 212.0, 200.0, 16.0, ident="row_1")
    found = check_layout(layout([first, second]))
    assert len(found) == 1
    assert "desk" in found[0].message and "bench" in found[0].message
    assert "at the same height" in found[0].message


def test_two_desks_side_by_side_are_not_reported() -> None:
    """Touching is what a furnished room looks like; overlapping is not."""
    first = placed("desk", DESK, 200.0, 200.0, 16.0)
    second = placed("desk", DESK, 264.0, 200.0, 16.0)
    assert check_layout(layout([first, second])) == []


def test_a_prop_on_top_of_another_is_a_shelf_and_not_an_overlap() -> None:
    """Two boxes at different heights sharing floor is how a table is laid."""
    table = placed("desk", DESK, 200.0, 200.0, 16.0)
    cup = placed("desk", DESK, 200.0, 200.0, 46.0)
    assert [f for f in check_layout(layout([table, cup])) if "inside" in f.message] == []


def test_a_walk_through_prop_inside_a_solid_one_is_not_reported() -> None:
    """The rule is about *solid* props: a hedge is meant to be walked into."""
    desk = placed("desk", DESK, 200.0, 200.0, 16.0)
    hedge = placed("hedge", DESK, 206.0, 200.0, 16.0, solid=False)
    assert check_layout(layout([desk, hedge])) == []


def test_two_cups_in_the_same_place_are_left_alone() -> None:
    """Both plan sides under 40 units: a cup half inside a bowl is a still life."""
    first = placed("cup", CUP, 200.0, 200.0, 16.0)
    second = placed("cup", CUP, 202.0, 200.0, 16.0)
    assert check_layout(layout([first, second])) == []


# --------------------------------------------------------------------------
# Rule 3: floating, and hanging off the edge
# --------------------------------------------------------------------------
def test_a_desk_floating_forty_units_above_its_floor_is_reported() -> None:
    desk = placed("desk", DESK, 200.0, 200.0, 56.0)
    found = check_layout(layout([desk]))
    assert len(found) == 1
    assert "floats 40 units" in found[0].message


def test_a_desk_on_its_floor_is_not() -> None:
    assert check_layout(layout([placed("desk", DESK, 200.0, 200.0, 16.0)])) == []


def test_a_prop_set_down_on_another_prop_is_held_up_by_it() -> None:
    """A cake on a table is 32 units over the floor on purpose."""
    table = placed("desk", DESK, 200.0, 200.0, 16.0)
    cake = placed("cup", CUP, 200.0, 200.0, 46.0)
    assert check_layout(layout([table, cake])) == []


def test_a_prop_resting_on_a_floating_prop_is_reported_too() -> None:
    """Nothing holds a thing up unless it is held up itself."""
    table = placed("desk", DESK, 200.0, 200.0, 56.0)
    cake = placed("cup", CUP, 200.0, 200.0, 86.0)
    found = check_layout(layout([table, cake]))
    assert len(found) == 2
    assert all("floats" in finding.message for finding in found)


def test_two_props_holding_each_other_up_are_both_reported() -> None:
    """Two props resting only on each other in mid air, neither on a floor."""
    first = placed("cup", CUP, 200.0, 200.0, 80.0)
    second = placed("cup", CUP, 204.0, 200.0, 80.0)
    found = check_layout(layout([first, second]))
    assert len(found) == 2
    assert all("floats 64 units" in finding.message for finding in found)


#: A shelving unit: 90 tall, boards at a quarter, half and three quarters of
#: that (22.5, 45, 67.5 over its base), the shape ``SHELF_BOARDS`` describes.
SHELF = ((-50.0, -15.0, 0.0), (50.0, 15.0, 90.0))
SHELF_SHARES = {"shelf": (0.25, 0.5, 0.75)}


def _shelved(z: float, *, shelves=SHELF_SHARES):
    unit = placed("shelf", SHELF, 200.0, 200.0, 16.0)
    box = placed("cup", CUP, 200.0, 200.0, z)
    return check_layout(Layout(
        props=(unit, box), rooms=(LOBBY,), surfaces=(), ground=(LOBBY.floor,),
        items=(), mounts={}, shelves=shelves,
    ))


def test_a_box_on_an_inner_shelf_board_is_held_up_by_it() -> None:
    """The board at half height holds it: 16 + 45."""
    assert _shelved(61.0) == []


def test_without_the_board_table_the_same_box_floats() -> None:
    """What the check said before the table: only a unit's top holds."""
    found = _shelved(61.0, shelves={})
    assert len(found) == 1 and "floats 45 units" in found[0].message


def test_a_box_hanging_between_two_boards_still_floats() -> None:
    """Six over the half-height board is six over the highest thing under it."""
    found = _shelved(67.0)
    assert len(found) == 1 and "floats" in found[0].message


def test_the_blueprint_adapter_reads_the_measured_board_table() -> None:
    """``SHELF_BOARDS`` reaches the layout as shares of the measured box."""
    from zmforge.placement.audit import _shelf_shares
    from zmforge.recipes import props

    name = "p7_shelf_metal_lab_01"
    shares = _shelf_shares({name, "p7_sandbag_02"}, props.MODEL_BOX)
    assert set(shares) == {name}
    (_x0, _y0, z0), (_x1, _y1, z1) = props.MODEL_BOX[name]
    assert shares[name][1] == pytest.approx((23.35 - z0) / (z1 - z0))


def _ramp_ground(sample: float, slope: float = 0.7):
    """A room floor with a hillside laid over it, cut at ``sample`` units.

    The slope defaults to 0.7 up for every unit north, a steep generated bank.
    """
    from zmforge.placement import audit

    was = audit.TERRAIN_SAMPLE
    audit.TERRAIN_SAMPLE = sample
    try:
        cells = audit._height_cells(
            "the hillside", 0.0, 0.0, 512.0, 512.0,
            lambda x, y: LOBBY.floor_z + slope * y,
        )
    finally:
        audit.TERRAIN_SAMPLE = was
    return (LOBBY.floor,) + tuple(cells)


def _on_the_hillside(sample: float):
    """A desk standing on that hillside, judged against it."""
    height = LOBBY.floor_z + 0.7 * 200.0
    desk = placed("desk", DESK, 200.0, 200.0, height)
    return check_layout(Layout(
        props=(desk,), rooms=(LOBBY,), surfaces=(),
        ground=_ramp_ground(sample), items=(), mounts={},
    ))


def test_a_prop_standing_on_a_steep_slope_is_not_called_floating() -> None:
    """It is on the ground; how finely the ground is sampled is our business.

    On sloped ground, props can be reported floating 3 to 30 units over
    ground their own ``Blueprint.ground_under`` height matches to the unit.  A square carries its *highest* corner, and a
    square steeper than :data:`~zmforge.placement.audit.SUPPORT_REACH` across
    itself therefore sits above the ceiling the search below a prop uses and
    drops out of its own answer, leaving a lower neighbour to be reported
    against.
    """
    assert _on_the_hillside(TERRAIN_SAMPLE) == []


def test_the_old_sample_size_is_what_called_it_floating() -> None:
    """The same slope at 32 units, which is the size that had to change.

    Pinned so that the constant cannot drift back without this saying what it
    costs: the finding is not a prop in the wrong place, it is the check
    measuring the ground in steps too big for the hill.
    """
    found = _on_the_hillside(32.0)
    assert len(found) == 1
    assert "floats" in found[0].message


def test_a_bunk_bed_with_no_corner_on_its_plinth_is_reported() -> None:
    plinth = Surface("the holding plinth", Poly2.rect(280.0, 280.0, 340.0, 340.0), 40.0)
    bunk = placed("bunkbed", BUNK, 300.0, 330.0, 40.0)
    found = check_layout(layout([bunk], surfaces=[plinth]))
    assert len(found) == 1
    assert "of its footprint on the holding plinth" in found[0].message


def test_a_bunk_bed_squarely_on_its_plinth_is_not() -> None:
    plinth = Surface("the holding plinth", Poly2.rect(240.0, 240.0, 380.0, 380.0), 40.0)
    bunk = placed("bunkbed", BUNK, 300.0, 300.0, 40.0)
    assert check_layout(layout([bunk], surfaces=[plinth])) == []


def test_a_prop_hanging_over_the_edge_of_the_floor_is_not_this_rules_question() -> None:
    """A footprint crossing a floor's edge is brushwork, and out of scope."""
    desk = placed("desk", DESK, 8.0, 256.0, 16.0)
    assert check_layout(layout([desk])) == []


# --------------------------------------------------------------------------
# Rule 4: standing inside an interactive item
# --------------------------------------------------------------------------
def test_a_bench_inside_a_perk_machines_footprint_is_reported() -> None:
    """Scenery placed inside a perk machine, with one bench and one machine."""
    bench = placed("bench", BENCH, 200.0, 200.0, 16.0)
    found = check_layout(layout([bench], items=[machine(200.0, 200.0)]))
    assert len(found) == 1
    assert "the quick_revive machine" in found[0].message
    assert "perk_quick_revive" in found[0].message


def test_a_bench_beside_the_machine_is_not() -> None:
    bench = placed("bench", BENCH, 320.0, 200.0, 16.0)
    assert check_layout(layout([bench], items=[machine(200.0, 200.0)])) == []


def test_litter_under_a_machine_is_left_alone() -> None:
    """A newspaper covers neither the prompt nor the drawing."""
    paper = ((-8.0, -8.0, 0.0), (8.0, 8.0, ITEM_MIN_HEIGHT - 2.0))
    litter = placed("newspaper", paper, 200.0, 200.0, 16.0, solid=False)
    assert check_layout(layout([litter], items=[machine(200.0, 200.0)])) == []


# --------------------------------------------------------------------------
# What every finding carries, and how loudly it says it
# --------------------------------------------------------------------------
def test_a_clean_room_produces_nothing() -> None:
    """A desk on the floor, a bench beside it and a clock on the wall."""
    props = [
        placed("desk", DESK, 200.0, 200.0, 16.0),
        placed("bench", BENCH, 200.0, 260.0, 16.0),
        placed("clock", CLOCK, 256.0, 8.0, 92.0),
    ]
    assert check_layout(
        layout(props, mounts={"clock": mount_kind_of_box(CLOCK)})
    ) == []


def test_every_finding_names_the_model_its_position_and_its_room() -> None:
    props = [
        placed("clock", CLOCK, 100.0, 100.0, 16.0, ident="dressing_0"),
        placed("desk", DESK, 200.0, 200.0, 56.0, ident="dressing_1"),
        placed("bench", BENCH, 300.0, 300.0, 16.0, ident="dressing_2"),
    ]
    found = check_layout(
        layout(props, items=[machine(300.0, 300.0)],
               mounts={"clock": mount_kind_of_box(CLOCK)})
    )
    assert len(found) == 3
    for finding in found:
        assert finding.code == "Z44"
        assert " in lobby " in finding.message
        assert finding.position in finding.message
        assert finding.message.split(" at ")[0] in ("clock", "desk", "bench")
        assert finding.element_id.startswith("dressing_")


def test_a_prop_in_no_room_still_reports_without_naming_one() -> None:
    clock = placed("clock", CLOCK, 900.0, 900.0, 16.0, room="")
    found = check_layout(
        layout([clock], rooms=(LOBBY, LayoutRoom("yard", 800.0, 800.0, 1000.0,
                                                 1000.0, 16.0, 272.0)),
               mounts={"clock": mount_kind_of_box(CLOCK)})
    )
    assert len(found) == 1
    assert " in " not in found[0].message.split(" is a ")[0]


def test_the_severity_switch_turns_every_warning_into_an_error() -> None:
    props = [placed("clock", CLOCK, 100.0, 100.0, 16.0),
             placed("desk", DESK, 200.0, 200.0, 56.0)]
    mounts = {"clock": mount_kind_of_box(CLOCK)}
    warned = check_layout(layout(props, mounts=mounts))
    failed = check_layout(layout(props, mounts=mounts), severity="error")
    assert [f.severity for f in warned] == ["warning", "warning"]
    assert [f.severity for f in failed] == ["error", "error"]
    assert [f.message for f in warned] == [f.message for f in failed]


def test_an_unknown_severity_is_refused() -> None:
    with pytest.raises(ValueError):
        check_layout(layout([]), severity="loud")


def test_the_code_is_the_callers_to_give() -> None:
    """The registry of codes is ``zmforge.verify``'s, not this package's."""
    clock = placed("clock", CLOCK, 100.0, 100.0, 16.0)
    found = check_layout(
        layout([clock], mounts={"clock": mount_kind_of_box(CLOCK)}), code="Z99"
    )
    assert [f.code for f in found] == ["Z99"]


# --------------------------------------------------------------------------
# The two adapters, over a blueprint and the text written from it
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def furnished():
    """One room with four props in it, two of them wrong.

    Hand-built rather than taken from a recipe because the recipes that place
    props place two thousand of them, and what these two tests are about is
    the adapters agreeing, not the size of the map they agree on.
    """
    blueprint = Blueprint("zm_layout_fixture")
    room = blueprint.add_room(
        Span.between(Point(-256.0, -256.0, 0.0), Point(256.0, 256.0, 272.0))
    )
    blueprint.add_zone("room", room, starting=True)
    blueprint.place_props([
        ("p7_desk_metal_old_01_body", Point(0.0, 0.0, 16.0), 0.0, 1.0, True),
        ("p7_desk_metal_old_01_body", Point(24.0, 0.0, 16.0), 0.0, 1.0, True),
        ("p7_clock_metal_wall_01_base", Point(-100.0, -100.0, 16.0), 0.0, 1.0, False),
        ("p7_bench_modern_01", Point(120.0, 120.0, 56.0), 0.0, 1.0, True),
    ])
    return blueprint


def test_the_blueprint_adapter_fills_in_rooms_mounts_and_ground(furnished) -> None:
    built = layout_from_blueprint(furnished)
    assert len(built.props) == 4
    assert {room.id for room in built.rooms} == {"room"}, (
        "a room is named after the zone it is in, as the map text names it"
    )
    assert all(prop.room for prop in built.props), "every prop names its room"
    assert built.mounts["p7_clock_metal_wall_01_base"] is MountKind.WALL
    assert built.ground, "the room's floor is the ground"


def test_the_map_text_adapter_reads_the_same_props_back(furnished) -> None:
    """The text is what the compiler reads, so the text is what gets checked."""
    from_text = layout_from_map_text(render_map_text(build_document(furnished)))
    from_model = layout_from_blueprint(furnished)
    assert len(from_text.props) == len(from_model.props)
    assert {prop.name for prop in from_text.props} == {
        prop.name for prop in from_model.props
    }
    assert {room.id for room in from_text.rooms} == {"room"}
    assert from_text.mounts == from_model.mounts


def test_both_adapters_find_the_same_faults(furnished) -> None:
    """A map edited by hand is judged as the blueprint would be."""
    from_text = check_layout(layout_from_map_text(render_map_text(build_document(furnished))))
    from_model = check_layout(layout_from_blueprint(furnished))
    assert {f.message for f in from_text} == {f.message for f in from_model}
    assert len(from_model) == 3  # the clock, the two desks, the floating bench
