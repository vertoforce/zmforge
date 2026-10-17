"""Conformance checks G1-G10: is the geometry a compiler would accept?

Every property here is a property of half-spaces, not of the code that built
them, so each test recomputes the solid from the face points that would be
written into the file.  That is deliberate: a check that trusts the builder
would pass while the text was wrong, and the text is what the compiler reads.

The winding convention under test is the engine's, not Quake's (spec 1.4):
``(B - A) x (C - A)`` points *into* the solid.  Under the outward reading, 0
of 25 measured real brushes enclose any volume, so getting this backwards
produces geometry that closes under no interpretation at all.
"""

from __future__ import annotations

import random
from itertools import combinations

import pytest

from zmforge.materials import CAULK, FaceMaterials, Material
from zmforge.recipes import three_room_map
from zmforge.solids.forms import block, flight, wedge
from zmforge.solids.halfspace import plane_through
from zmforge.solids.inspect import (
    VOLUME_FLOOR,
    inspect_planes,
    inspect_solid,
    overlap_scan,
)
from zmforge.solids.layout import (
    Aperture,
    aperture_box,
    room_shell,
    sky_cage,
    wall_remainder,
    yard_shell,
)
from zmforge.spatial import Axis, Facing, Point, Side, Span

ART = Material("t7_concrete_trowelled")


def _planes_from_text(solid):
    """Rebuild the half-spaces from the face triples, the way a reader would."""
    return [plane_through(*face.points) for face in solid.faces]


def _random_box(rng: random.Random, *, fractional: bool = False) -> Span:
    def pair() -> tuple[float, float]:
        low = rng.uniform(-2048, 2048)
        size = rng.uniform(8, 512)
        if not fractional:
            low, size = float(round(low)), float(round(size))
        return low, low + size

    (x0, x1), (y0, y1), (z0, z1) = pair(), pair(), pair()
    return Span.between((x0, y0, z0), (x1, y1, z1))


def _voxel_set(boxes, step: float) -> set[tuple[int, int, int]]:
    """Cell centres covered by a set of boxes, on a fixed lattice."""
    covered: set[tuple[int, int, int]] = set()
    for box in boxes:
        i0 = int(round(box.mins.x / step))
        i1 = int(round(box.maxs.x / step))
        j0 = int(round(box.mins.y / step))
        j1 = int(round(box.maxs.y / step))
        k0 = int(round(box.mins.z / step))
        k1 = int(round(box.maxs.z / step))
        for i in range(i0, i1):
            for j in range(j0, j1):
                for k in range(k0, k1):
                    covered.add((i, j, k))
    return covered


# --------------------------------------------------------------------------
# G1: every primitive is a real solid
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fractional", [False, True])
def test_g1_every_primitive_encloses_a_solid(fractional: bool) -> None:
    """Brushes that are degenerate, inverted or over-planed never ship.

    The inversion case is the one that matters: it is the defect the reversed
    winding convention invites, and the compiler gives no useful diagnostic
    for it.
    """
    rng = random.Random(20260917)
    for _ in range(40):
        box = _random_box(rng, fractional=fractional)
        for solid in (
            block(box, ART),
            wedge(box, Facing.EAST, ART),
            wedge(box, Facing.SOUTH, ART),
        ):
            inspection = inspect_planes(_planes_from_text(solid))
            assert inspection.ok, inspection.findings
            assert inspection.volume >= VOLUME_FLOOR


def test_g1_bounds_crossing_zero_are_solid() -> None:
    """Walls generated on a zero coordinate are where the noise turns up."""
    box = Span.between((-64, -64, -64), (64, 64, 64))
    inspection = inspect_planes(_planes_from_text(block(box, ART)))
    assert inspection.ok
    assert inspection.volume == pytest.approx(128**3)


def test_g1_flipped_winding_is_reported_as_inverted() -> None:
    """A brush wound the Quake way must be named, not just called empty."""
    solid = block(Span.between((0, 0, 0), (32, 32, 32)), ART)
    flipped = [plane_through(*face.points).flipped() for face in solid.faces]
    inspection = inspect_planes(flipped)
    assert not inspection.ok
    assert [f.code for f in inspection.errors] == ["inverted"]


def test_g1_zero_thickness_box_is_refused_at_construction() -> None:
    """Item K7: a zero-height run once aborted a whole terrain."""
    from zmforge.errors import InvalidBounds

    with pytest.raises(InvalidBounds, match="Z"):
        Span.between((0, 0, 16), (32, 32, 16))


# --------------------------------------------------------------------------
# G2: the box
# --------------------------------------------------------------------------
def test_g2_box_has_eight_corner_vertices_and_the_right_volume() -> None:
    box = Span.between((-100, 20, 3.5), (40, 260, 99))
    inspection = inspect_solid(block(box, ART))
    assert len(inspection.vertices) == 8
    corners = {tuple(round(c, 6) for c in p) for p in box.corners()}
    found = {tuple(round(c, 6) for c in p) for p in inspection.vertices}
    assert found == corners
    assert inspection.volume == pytest.approx(box.volume, rel=1e-9)


def test_g2_spec_worked_example_point_order() -> None:
    """The unit-box test vectors of spec 2.1, on the orientation check itself.

    Both are cases where the natural corner order comes out outward and the
    check has to swap the last two points.  The check is asserted directly
    because which three corners a builder picks is its own business (the spec
    says "any three distinct corners"); what is fixed is the order they end up
    in once a normal is requested.
    """
    from zmforge.solids.halfspace import orient_inward

    bottom = orient_inward(
        Point(0, 0, 0), Point(0, 1, 0), Point(1, 1, 0), Side.BOTTOM.inward
    )
    assert [tuple(p) for p in bottom] == [(0, 0, 0), (1, 1, 0), (0, 1, 0)]
    east = orient_inward(
        Point(1, 0, 0), Point(1, 1, 0), Point(1, 1, 1), Side.EAST.inward
    )
    assert [tuple(p) for p in east] == [(1, 0, 0), (1, 1, 1), (1, 1, 0)]

    # A triple that is already inward is emitted unchanged.
    unchanged = orient_inward(
        Point(0, 0, 0), Point(1, 1, 0), Point(0, 1, 0), Side.BOTTOM.inward
    )
    assert [tuple(p) for p in unchanged] == [(0, 0, 0), (1, 1, 0), (0, 1, 0)]


def test_g2_every_emitted_box_face_is_wound_inward() -> None:
    """The property the spec's example illustrates, over all six faces."""
    unit = block(Span.between((0, 0, 0), (1, 1, 1)), ART)
    for face in unit.faces:
        plane = plane_through(*face.points)
        assert plane.normal.dot(face.inward) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# G3: the wedge
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rise", [Facing.EAST, Facing.WEST, Facing.NORTH, Facing.SOUTH]
)
def test_g3_wedge_is_five_planes_of_half_the_box(rise: Facing) -> None:
    """Item K16: the slope is wound by the numeric check, in every direction."""
    box = Span.between((-256, -128, 0), (256, 128, 96))
    solid = wedge(box, rise, ART)
    assert len(solid.faces) == 5
    inspection = inspect_planes(_planes_from_text(solid))
    assert inspection.ok, inspection.findings
    assert inspection.volume == pytest.approx(box.volume / 2.0, rel=1e-9)

    highest = max(inspection.vertices, key=lambda p: p.z)
    assert highest.z == pytest.approx(box.maxs.z)
    assert highest[rise.axis.index] == pytest.approx(box.face_plane(rise.side))


# --------------------------------------------------------------------------
# G4: the room shell
# --------------------------------------------------------------------------
@pytest.mark.parametrize("roofed", [True, False])
def test_g4_room_shell_is_the_outer_box_minus_the_interior(roofed: bool) -> None:
    """Item K17 keeps the open-air variant honest: its walls run to the top."""
    outer = Span.between((-256, -128, 0), (256, 384, 256))
    shell = room_shell(outer, 16.0, roofed=roofed)
    step = 8.0
    union = _voxel_set(shell.boxes(), step)
    expected = _voxel_set([outer], step) - _voxel_set([shell.interior], step)
    assert union == expected

    for left, right in combinations(shell.boxes(), 2):
        assert not left.overlaps(right, slack=0.0)

    if not roofed:
        for piece in shell.pieces:
            if piece.side.is_horizontal:
                assert piece.box.maxs.z == pytest.approx(outer.maxs.z)


def test_g4_room_too_thin_for_its_walls_is_refused() -> None:
    from zmforge.errors import InvalidBounds

    with pytest.raises(InvalidBounds, match="interior"):
        room_shell(Span.between((0, 0, 0), (32, 512, 512)), 16.0)


# --------------------------------------------------------------------------
# G5: openings
# --------------------------------------------------------------------------
def test_g5_wall_with_openings_equals_the_wall_minus_the_holes() -> None:
    """The sweep of spec 2.3, checked by voxel sampling rather than by shape."""
    outer = Span.between((-512, -256, 0), (-128, 256, 256))
    shell = room_shell(outer, 16.0)
    holes = [
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=-96), 16.0),
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=96), 16.0),
    ]
    wall = shell.of_side(Side.SOUTH)[0].box
    pieces = wall_remainder(wall, holes, Axis.X)

    step = 8.0
    assert _voxel_set(pieces, step) == _voxel_set([wall], step) - _voxel_set(holes, step)
    for left, right in combinations(pieces, 2):
        assert not left.overlaps(right, slack=0.0)
    for hole in holes:
        assert not any(piece.overlaps(hole, slack=0.0) for piece in pieces)


def test_g5_touching_openings_are_adjacent_not_overlapping() -> None:
    outer = Span.between((-512, -256, 0), (-128, 256, 256))
    shell = room_shell(outer, 16.0)
    wall = shell.of_side(Side.SOUTH)[0].box
    holes = [
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=-32), 16.0),
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=32), 16.0),
    ]
    pieces = wall_remainder(wall, holes, Axis.X)
    for left, right in combinations(pieces, 2):
        assert not left.overlaps(right, slack=0.0)


def test_g5_overlapping_openings_are_a_caller_error() -> None:
    from zmforge.errors import OpeningDoesNotFit

    outer = Span.between((-512, -256, 0), (-128, 256, 256))
    shell = room_shell(outer, 16.0)
    wall = shell.of_side(Side.SOUTH)[0].box
    holes = [
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=0), 16.0),
        aperture_box(shell, Aperture(Side.SOUTH, 64, 48, sill=48, offset=16), 16.0),
    ]
    with pytest.raises(OpeningDoesNotFit, match="overlap"):
        wall_remainder(wall, holes, Axis.X)


@pytest.mark.parametrize(
    "aperture, reason",
    [
        (Aperture(Side.SOUTH, 64, 512, sill=0), "tall"),
        (Aperture(Side.SOUTH, 64, 48, sill=240), "units of wall"),
        (Aperture(Side.SOUTH, 4096, 48), "does not fit"),
        (Aperture(Side.SOUTH, 64, 48, offset=4096), "outside"),
    ],
)
def test_g5_openings_that_do_not_fit_say_which_constraint_failed(aperture, reason) -> None:
    from zmforge.errors import OpeningDoesNotFit

    shell = room_shell(Span.between((-512, -256, 0), (-128, 256, 256)), 16.0)
    with pytest.raises(OpeningDoesNotFit, match=reason):
        aperture_box(shell, aperture, 16.0)


# --------------------------------------------------------------------------
# G6: the yard
# --------------------------------------------------------------------------
def _flood_escapes(shell, step: float) -> bool:
    """Does a 4-unit fill from the yard interior reach outside the outer box?

    Item K11: flanking walls that stopped a thickness short of the open side
    left a ``t x t`` corner slot, and the fill escaped west of the room before
    the fix.  The open side is sealed off for the test so the only way out is
    a defect.
    """
    outer = shell.outer
    solid = _voxel_set(shell.boxes(), step)
    lo = (
        int(round(outer.mins.x / step)) - 2,
        int(round(outer.mins.y / step)) - 2,
        int(round(outer.mins.z / step)) - 2,
    )
    hi = (
        int(round(outer.maxs.x / step)) + 2,
        int(round(outer.maxs.y / step)) + 2,
        int(round(outer.maxs.z / step)) + 2,
    )
    start = shell.interior.centre
    seed = (
        int(start.x // step),
        int(start.y // step),
        int(start.z // step),
    )
    seen = {seed}
    stack = [seed]
    inside_lo = (
        int(round(outer.mins.x / step)),
        int(round(outer.mins.y / step)),
        int(round(outer.mins.z / step)),
    )
    inside_hi = (
        int(round(outer.maxs.x / step)),
        int(round(outer.maxs.y / step)),
        int(round(outer.maxs.z / step)),
    )
    while stack:
        cell = stack.pop()
        for axis in range(3):
            for delta in (-1, 1):
                nxt = list(cell)
                nxt[axis] += delta
                nxt = tuple(nxt)
                if nxt in seen or nxt in solid:
                    continue
                if any(nxt[i] < lo[i] or nxt[i] >= hi[i] for i in range(3)):
                    continue
                # The open side is where the room is; treat it as sealed.
                if _is_open_side(shell, nxt, inside_lo, inside_hi):
                    continue
                if any(
                    nxt[i] < inside_lo[i] or nxt[i] >= inside_hi[i] for i in range(3)
                ):
                    return True
                seen.add(nxt)
                stack.append(nxt)
    return False


def _is_open_side(shell, cell, inside_lo, inside_hi) -> bool:
    attached = shell_attached_side(shell)
    axis = attached.axis.index
    if attached.sign < 0:
        return cell[axis] < inside_lo[axis]
    return cell[axis] >= inside_hi[axis]


def shell_attached_side(shell):
    """Which side of this yard has no wall (inferred from the pieces present)."""
    present = {piece.side for piece in shell.pieces}
    for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST):
        if side not in present:
            return side
    raise AssertionError("this shell is closed on every side")


@pytest.mark.parametrize("attached", [Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST])
def test_g6_yard_is_open_only_on_its_attached_side(attached: Side) -> None:
    yard = yard_shell(Span.between((-512, -432, 0), (-128, -256, 256)), attached, 16.0)
    assert shell_attached_side(yard) is attached
    assert not _flood_escapes(yard, 4.0)


def test_g6_yard_flanking_walls_reach_the_open_edge() -> None:
    """The corner slot of item K11, stated as a coordinate rather than a fill."""
    outer = Span.between((-512, -432, 0), (-128, -256, 256))
    yard = yard_shell(outer, Side.NORTH, 16.0)
    for side in (Side.WEST, Side.EAST):
        piece = yard.of_side(side)[0].box
        assert piece.maxs.y == pytest.approx(outer.maxs.y)


# --------------------------------------------------------------------------
# G7: the enclosure
# --------------------------------------------------------------------------
def test_g7_sky_shell_leaves_no_gap_and_no_overlap() -> None:
    playable = Span.between((-512, -512, 0), (1280, 512, 384))
    cage = sky_cage(playable, gap=128.0, thickness=32.0)
    step = 32.0
    union = _voxel_set(cage.boxes(), step)
    expected = _voxel_set([cage.outer], step) - _voxel_set([cage.inner], step)
    assert union == expected
    for left, right in combinations(cage.boxes(), 2):
        assert not left.overlaps(right, slack=0.0)
    assert cage.inner.encloses(playable)


def test_g7_a_fill_from_the_playable_interior_never_escapes() -> None:
    playable = Span.between((-256, -256, 0), (256, 256, 256))
    cage = sky_cage(playable, gap=128.0, thickness=32.0)
    shell = type("_S", (), {})()
    shell.outer = cage.outer
    shell.interior = cage.inner
    shell.pieces = cage.slabs
    assert shell_attached_side_is_absent(cage)
    assert not _fill_escapes_cage(cage, 32.0)


def shell_attached_side_is_absent(cage) -> bool:
    return len(cage.slabs) == 6


def _fill_escapes_cage(cage, step: float) -> bool:
    solid = _voxel_set(cage.boxes(), step)
    lo = tuple(int(round(cage.outer.mins[i] / step)) - 2 for i in range(3))
    hi = tuple(int(round(cage.outer.maxs[i] / step)) + 2 for i in range(3))
    inside_lo = tuple(int(round(cage.outer.mins[i] / step)) for i in range(3))
    inside_hi = tuple(int(round(cage.outer.maxs[i] / step)) for i in range(3))
    centre = cage.playable.centre
    seed = tuple(int(centre[i] // step) for i in range(3))
    seen = {seed}
    stack = [seed]
    while stack:
        cell = stack.pop()
        for axis in range(3):
            for delta in (-1, 1):
                nxt = list(cell)
                nxt[axis] += delta
                nxt = tuple(nxt)
                if nxt in seen or nxt in solid:
                    continue
                if any(nxt[i] < lo[i] or nxt[i] >= hi[i] for i in range(3)):
                    continue
                if any(nxt[i] < inside_lo[i] or nxt[i] >= inside_hi[i] for i in range(3)):
                    return True
                seen.add(nxt)
                stack.append(nxt)
    return False


def test_g7_rooms_and_yards_lie_strictly_inside_the_inner_bounds() -> None:
    blueprint = three_room_map("zm_forge_gate")
    enclosure = blueprint.resolve_enclosure()
    from zmforge.blueprint.elements import Room, Yard

    for element in blueprint.elements(Room) + blueprint.elements(Yard):
        assert enclosure.cage.inner.encloses(element.outer)
        assert not enclosure.cage.inner.mins.distance_to(element.outer.mins) == 0


# --------------------------------------------------------------------------
# G8: stairs
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "toward", [Facing.EAST, Facing.WEST, Facing.NORTH, Facing.SOUTH]
)
def test_g8_steps_are_non_overlapping_columns(toward: Facing) -> None:
    """The reference made each step cover every previous one; that trips G10."""
    base = Point(100.0, -40.0, 16.0)
    steps = flight(base, 6, 16.0, 8.0, 64.0, toward)
    assert len(steps) == 6
    for index, box in enumerate(steps):
        assert box.maxs.z == pytest.approx(base.z + 8.0 * (index + 1))
        assert box.mins.z == pytest.approx(base.z)
    for left, right in combinations(steps, 2):
        assert not left.overlaps(right, slack=0.0)


# --------------------------------------------------------------------------
# G9: face materials
# --------------------------------------------------------------------------
def test_g9_hull_boxes_carry_art_on_exactly_one_face_looking_inward() -> None:
    """Item E8: the same art on both sides made the interior render as sky."""
    from zmforge.emit.mapfile import _room_solids

    blueprint = three_room_map("zm_forge_gate")
    from zmforge.blueprint.elements import Room

    room = blueprint.find("vault_room")
    assert isinstance(room, Room)
    hull_boxes = 0
    for solid in _room_solids(room):
        visible = [f for f in solid.faces if f.material != CAULK]
        if len(visible) == 6:
            continue  # an opening piece, checked below
        hull_boxes += 1
        assert len(visible) == 1, solid.note
        looking = visible[0].inward
        assert room.interior.holds(
            _face_centre(visible[0]) + looking.scaled(1.0), tolerance=1.0
        )
    assert hull_boxes >= 5


def _face_centre(face):
    a, b, c = face.points
    return Point((a.x + b.x + c.x) / 3, (a.y + b.y + c.y) / 3, (a.z + b.z + c.z) / 3)


def test_g9_opening_pieces_are_visible_on_all_six_faces() -> None:
    """The player sees the jambs, sill and lintel walking through (spec 2.3)."""
    from zmforge.emit.mapfile import _room_solids

    blueprint = three_room_map("zm_forge_gate")
    room = blueprint.find("start_room")
    six_sided = [
        solid
        for solid in _room_solids(room)
        if all(face.material != CAULK for face in solid.faces)
    ]
    assert six_sided, "a room with three openings must have framing pieces"


# --------------------------------------------------------------------------
# G10: the overlap scan
# --------------------------------------------------------------------------
def test_g10_committed_demo_map_has_no_structural_overlaps() -> None:
    """Radiant tolerates interpenetration; the BSP pays for it every time."""
    blueprint = three_room_map("zm_forge_gate")
    blueprint.resolve_enclosure()
    findings = overlap_scan(blueprint.world_solids())
    assert findings == [], [f.message for f in findings]


def test_g10_scan_finds_a_deliberate_overlap() -> None:
    """A scan that never fires is not evidence of anything."""
    left = block(Span.between((0, 0, 0), (64, 64, 64)), ART)
    right = block(Span.between((32, 32, 32), (96, 96, 96)), ART)
    assert len(overlap_scan([left, right])) == 1


# --------------------------------------------------------------------------
# G5 (per wall): one wall of a room made of something else
# --------------------------------------------------------------------------
def test_one_wall_can_carry_its_own_material() -> None:
    """A room whose north wall is tiled and whose other three are not.

    The override reaches the face that looks into the room on that wall and
    nothing else: the other walls keep the room's wall material, the floor and
    the ceiling keep theirs, and the hidden faces stay caulk (spec 2.2).
    """
    from zmforge.blueprint.elements import RoomMaterials
    from zmforge.blueprint.model import Blueprint
    from zmforge.emit.mapfile import _room_solids

    tiled = Material("t7_zm_der_tile_hexagon")
    blueprint = Blueprint("zm_sides", seed="zm_sides")
    room = blueprint.add_room(
        Span.between((0, 0, 0), (512, 512, 256)),
        materials=RoomMaterials(
            wall=Material("t7_concrete_wall_dark_01"),
            floor=Material("t7_concrete_trowelled"),
            ceiling=Material("t7_concrete_wall_dark_01"),
            sides={Side.NORTH: tiled},
        ),
        id="room",
    )
    faces = {
        piece.side: {face.material.name for face in solid.faces}
        for piece, solid in zip(room.shell.pieces, _room_solids(room))
    }
    assert tiled.name in faces[Side.NORTH]
    assert tiled.name not in faces[Side.SOUTH]
    assert tiled.name not in faces[Side.BOTTOM]
    assert tiled.name in blueprint.material_names()


def test_a_floor_override_on_sides_is_refused_rather_than_ignored() -> None:
    from zmforge.blueprint.elements import RoomMaterials

    with pytest.raises(ValueError, match="floor or the ceiling"):
        RoomMaterials(
            wall=Material("t7_concrete_wall_dark_01"),
            floor=Material("t7_concrete_trowelled"),
            ceiling=Material("t7_concrete_wall_dark_01"),
            sides={Side.BOTTOM: Material("t7_wood_planks_worn")},
        )
