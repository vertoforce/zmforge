"""H1: the navmesh the compiler wrote, read back and asked the play questions.

Two halves, and they are tested differently on purpose.

The **reader** (:mod:`zmforge.verify.hkt`) is tested against a real file: a
Havok tagfile grammar worked out by inspection is only as good as the bytes it
has read, so the tests read ``tests/corpus/zm_one_room_navmesh.hkt`` -- the
mesh ``cod2map64 -navmesh`` builds from the ``one-room`` recipe, which is mod
tools output and has to be built with your own mod tools -- and assert the shape of the map it
came from: two
faces, one for the room and one for the yard behind the barricade, with the
room's corners on the room's own walls.

The **check** (:mod:`zmforge.verify.navmesh`) is tested against meshes built in
the test, because every interesting case is a mesh that is *wrong* and no
compiler will produce one to order.  :func:`_mesh` builds one quad per
rectangle, which is what the compiler produces for a flat room anyway.

The negative case that matters is
``test_a_room_the_player_jumps_into_and_the_mesh_cannot_climb_is_an_error``.
It is not hypothetical: the same map, built and compiled as
``zm_h1probe2``, passes every model-level check in the package -- the floor is
reachable on foot because a player jumps 64 (``Z25``), the zone has a spawn
struct (``Z4``), the doorway is wide and tall enough (``W2``, ``N2``, ``N3``)
-- and the navmesh the compiler actually wrote is four faces in three islands,
with 730,112 square units of upper floor on islands no spawn struct stands on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zmforge.blueprint.elements import Aperture, Zone
from zmforge.blueprint.model import Blueprint
from zmforge.recipes.layouts import one_room_map
from zmforge.spatial import Facing, Point, Side, Span
from zmforge.verify.hkt import (
    METRES_PER_UNIT,
    NavmeshUnreadable,
    RawNavMesh,
    read_navmesh,
    read_navmesh_bytes,
)
from zmforge.verify.navmesh import NavMesh, check_navmesh, check_navmesh_file

CORPUS = Path(__file__).parent / "corpus" / "zm_one_room_navmesh.hkt"
if not CORPUS.is_file():
    pytest.skip("tests/corpus/zm_one_room_navmesh.hkt is mod tools output and is not distributed; "
                "build zm_one_room and copy its navmesh there to run these", allow_module_level=True)

#: Where a build under Wine leaves its meshes, when there is one.
BUILT = Path("<bo3-wine>/tools/share/raw/maps/zm")


# --------------------------------------------------------------------------
# Building a mesh to order
# --------------------------------------------------------------------------
def _mesh(*quads) -> NavMesh:
    """One flat quad per ``(x0, y0, x1, y1, z)``, none of them joined.

    Unjoined is the honest default: the compiler leaves a border edge wherever
    a face has no neighbour, and the two faces of a real one-room map -- room
    and yard -- are exactly that.  :func:`_joined` makes a pair share an edge.
    """
    vertices: list[tuple[float, float, float]] = []
    start_edge: list[int] = []
    num_edges: list[int] = []
    edge_a: list[int] = []
    edge_b: list[int] = []
    for x0, y0, x1, y1, z in quads:
        base = len(vertices)
        vertices += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        start_edge.append(len(edge_a))
        num_edges.append(4)
        for corner in range(4):
            edge_a.append(base + corner)
            edge_b.append(base + (corner + 1) % 4)
    return NavMesh.of(
        RawNavMesh(
            vertices=tuple(vertices),
            start_edge=tuple(start_edge),
            num_edges=tuple(num_edges),
            edge_a=tuple(edge_a),
            edge_b=tuple(edge_b),
            opposite_edge=tuple([-1] * len(edge_a)),
            opposite_face=tuple([-1] * len(edge_a)),
        )
    )


def _joined(mesh: NavMesh, one: int, other: int) -> NavMesh:
    """The same mesh with two faces sharing an edge, as a doorway does."""
    links = list(mesh.links)
    links[one] = links[one] | {other}
    links[other] = links[other] | {one}
    return NavMesh(mesh.faces, tuple(links))


#: The mesh the compiler really does write for ``one_room_map``: the room, and
#: the yard behind the barricade, with the wall's 16 units between them.
ROOM = (-240.0, -240.0, 240.0, 240.0, 16.0)
YARD = (-240.0, -416.0, 240.0, -256.0, 16.0)


def _codes(report) -> list[str]:
    return [finding.code for finding in report.findings]


# --------------------------------------------------------------------------
# The reader, against a file the compiler wrote
# --------------------------------------------------------------------------
def test_the_corpus_navmesh_is_present() -> None:
    assert CORPUS.exists(), CORPUS


def test_the_reader_reads_the_mesh_of_the_one_room_recipe() -> None:
    raw = read_navmesh(CORPUS)
    assert (raw.face_count, raw.edge_count, len(raw.vertices)) == (2, 8, 8)


def test_every_face_is_a_closed_ring_of_edges() -> None:
    """The file's own arithmetic, which a misread stream cannot satisfy."""
    raw = read_navmesh(CORPUS)
    for face in range(raw.face_count):
        start, count = raw.start_edge[face], raw.num_edges[face]
        ring = range(start, start + count)
        assert [raw.edge_b[edge] for edge in ring] == [
            raw.edge_a[start + (step + 1) % count] for step in range(count)
        ]


def test_the_vertices_come_back_in_map_units() -> None:
    """The room's own walls, to within the generator's quantisation."""
    mesh = NavMesh.of(read_navmesh(CORPUS))
    room = one_room_map("zm_one_room").find("room")
    floor = max(mesh.faces, key=lambda face: face.area)
    assert floor.bounds.mins.x == pytest.approx(room.interior.mins.x, abs=1.0)
    assert floor.bounds.maxs.y == pytest.approx(room.interior.maxs.y, abs=1.0)
    assert floor.low == pytest.approx(room.floor_z, abs=1.0)


def test_the_mesh_stops_at_the_barricade_wall() -> None:
    """Two faces, not joined: the walkers cross that gap by animation."""
    mesh = NavMesh.of(read_navmesh(CORPUS))
    assert [len(island) for island in mesh.islands()] == [1, 1]


def test_one_map_unit_is_the_documented_inch() -> None:
    assert METRES_PER_UNIT == 0.0254


def test_something_that_is_not_a_tagfile_is_refused() -> None:
    with pytest.raises(NavmeshUnreadable):
        read_navmesh_bytes(b"iwmap 4\n" * 40)


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(NavmeshUnreadable):
        read_navmesh_bytes(b"")


def test_a_truncated_navmesh_is_refused_rather_than_half_read() -> None:
    """A half-understood binary is worse than no check at all."""
    whole = CORPUS.read_bytes()
    with pytest.raises(NavmeshUnreadable):
        read_navmesh_bytes(whole[: len(whole) // 2])


def test_a_missing_file_is_a_finding_and_not_an_exception() -> None:
    report = check_navmesh_file(one_room_map("zm_one_room"), CORPUS.with_name("nope.hkt"))
    assert _codes(report) == ["H1"]
    assert "could not be read" in report.findings[0].message


# --------------------------------------------------------------------------
# The check, against meshes built to order
# --------------------------------------------------------------------------
def test_the_mesh_the_compiler_wrote_for_the_one_room_recipe_passes() -> None:
    report = check_navmesh_file(one_room_map("zm_one_room"), CORPUS)
    assert report.findings == [], [str(finding) for finding in report]


def test_a_mesh_with_no_faces_at_all_is_an_error() -> None:
    report = check_navmesh(one_room_map("zm_one_room"), _mesh())
    assert _codes(report) == ["H1"]
    assert "no walkable surface" in report.findings[0].message


def test_a_room_with_no_surface_in_it_is_an_error() -> None:
    """The yard has mesh, the room has none: nothing gets in past the window."""
    report = check_navmesh(one_room_map("zm_one_room"), _mesh(YARD))
    assert set(_codes(report)) == {"H1"}
    assert any("the floor of room" in str(finding) for finding in report.errors)


def test_a_spawn_struct_with_no_surface_under_it_is_an_error() -> None:
    """The room's own riser, left standing on nothing."""
    report = check_navmesh(one_room_map("zm_one_room"), _mesh(YARD))
    assert any(
        finding.element_id == "interior_riser" and "spawn struct" in finding.message
        for finding in report.errors
    )


def test_a_barricade_with_surface_on_only_one_side_is_an_error() -> None:
    report = check_navmesh(one_room_map("zm_one_room"), _mesh(ROOM))
    assert any(
        finding.element_id == "window" and "barricade" in finding.message
        for finding in report.errors
    )


def test_a_barricade_with_surface_on_both_sides_is_not() -> None:
    report = check_navmesh(one_room_map("zm_one_room"), _mesh(ROOM, YARD))
    assert [finding for finding in report if finding.element_id == "window"] == []


# --------------------------------------------------------------------------
# The case nothing else in the package catches
# --------------------------------------------------------------------------
def _two_storeys() -> Blueprint:
    """One zone, two rooms, and the upper floor 32 units up.

    A player jumps 39 (``Z25``'s ``JUMP_UP``, the measured jump height) and
    the navmesh generator steps 18
    (``N1``'s ``maxStepHeight``), so a 32-unit rise is a place the player
    reaches and the walkers cannot -- and because both rooms are one
    zone, ``Z4``'s "every zone has a spawn struct" is satisfied by the riser
    downstairs.  Built and compiled as ``zm_h1probe2``: the mesh
    came out in three islands, exactly as this test asserts by hand.
    """
    blueprint = Blueprint("zm_two_storeys")
    low = blueprint.add_room(
        Span.between((-768, -512, 0), (0, 512, 384)),
        wall=16.0,
        openings=[Aperture(Side.EAST, 128.0, 96.0, sill=32.0)],
        id="low_room",
    )
    blueprint.add_room(
        Span.between((0, -512, 32), (768, 512, 432)),
        wall=16.0,
        openings=[Aperture(Side.WEST, 128.0, 96.0)],
        id="high_room",
    )
    zone = blueprint.add_zone(
        "start", Span.between((-784, -528, 0), (784, 528, 448)), starting=True
    )
    blueprint.add_window(zone, low, Side.SOUTH, yard_depth=176.0, height=48.0, id="window")
    blueprint.add_riser(zone, Point(-384, 400, low.floor_z), Facing.SOUTH, id="low_riser")
    blueprint.set_player_start(Point(-384, 0, low.floor_z + 16.0), Facing.EAST)
    blueprint.set_dog_rounds(False)
    blueprint.enclose(id="enclosure")
    blueprint.light_rooms()
    return blueprint


#: The mesh the compiler wrote for that map, as faces: the lower floor, the
#: yard behind its barricade, and the upper floor 32 units up with no edge
#: joining it to anything.
LOW_FLOOR = (-752.0, -496.0, -16.0, 496.0, 16.0)
LOW_YARD = (-752.0, -672.0, -16.0, -512.0, 16.0)
HIGH_FLOOR = (16.0, -496.0, 752.0, 496.0, 48.0)


def test_a_room_the_player_jumps_into_and_the_mesh_cannot_climb_is_an_error() -> None:
    report = check_navmesh(_two_storeys(), _mesh(LOW_FLOOR, LOW_YARD, HIGH_FLOOR))
    upstairs = [
        finding for finding in report.errors if finding.element_id == "high_room"
    ]
    assert [finding.code for finding in upstairs] == ["H1"], [
        str(finding) for finding in report
    ]
    assert "no zombie can path to" in upstairs[0].message


def test_the_same_map_passes_once_the_mesh_is_joined_to_the_lower_floor() -> None:
    """A staircase would do it: one shared edge and the island is one island."""
    mesh = _joined(_mesh(LOW_FLOOR, LOW_YARD, HIGH_FLOOR), 0, 2)
    report = check_navmesh(_two_storeys(), mesh)
    assert [finding for finding in report.errors if finding.element_id == "high_room"] == []


def test_the_upper_floor_passes_when_a_spawn_struct_stands_on_it() -> None:
    """An island of its own is fine if the walkers arrive on it."""
    blueprint = _two_storeys()
    start = blueprint.elements(Zone)[0]
    blueprint.add_riser(start, Point(384, 400, 48.0), Facing.SOUTH, id="high_riser")
    report = check_navmesh(blueprint, _mesh(LOW_FLOOR, LOW_YARD, HIGH_FLOOR))
    assert [finding for finding in report.errors if finding.element_id == "high_room"] == []


def test_a_table_no_zombie_can_climb_is_a_warning_and_not_an_error() -> None:
    """Measured: the generator lays no surface on a top more than 18 units up.

    That is what a table is.  Reporting one as an error would fail every map
    with furniture in it, so the top of a massing that is not a flight of steps
    is a warning that says what it is and leaves the judgement to the reader.
    """
    blueprint = one_room_map("zm_one_room")
    blueprint.add_slab(
        Span.flat_ok(Point(-200, -200, 0), Point(-60, -60, 0)),
        48.0,
        32.0,
        "t7_concrete_trowelled",
        id="table",
    )
    report = check_navmesh(blueprint, _mesh(ROOM, YARD))
    assert [finding.severity for finding in report if finding.element_id == "table"] == [
        "warning"
    ]
