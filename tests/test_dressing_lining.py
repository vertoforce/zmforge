"""The wall-lining helper (zmforge.dressing.lining) and the Z89 measure.

WHY: lined corn walls need more corn than the length lined suggests.
The rows were measured by length
lined (94.6%), which said nothing about how much wall showed between leaves.
"""

from __future__ import annotations

from zmforge.blueprint.elements import Prop
from zmforge.dressing.lining import DEFAULT_LINING, Lining, hidden_fraction, line_face, tilt_for
from zmforge.spatial import Angles, Point

SQUARE = ([(-50.0, 0.0, 0.0), (50.0, 0.0, 0.0), (50.0, 0.0, 300.0), (-50.0, 0.0, 300.0)],
          [(0, 1, 2), (0, 2, 3)])


def _line(lining: Lining) -> list[tuple]:
    placed = []

    def place(model, x, y, yaw, scale, tilt=(0.0, 0.0), back=False):
        placed.append((model, x, y, yaw, scale, tilt))
        return True

    line_face(True, 0.0, [(0.0, 400.0)], 1, lambda k, row: ("plant", 1.0),
              lambda m, s, yaw: (-10.0, 10.0, -10.0, 10.0), place, lining=lining)
    return placed


def test_the_default_lining_is_four_rows_a_plant_every_ten() -> None:
    assert DEFAULT_LINING.rows >= 4 and DEFAULT_LINING.step <= 10.0
    assert len(_line(DEFAULT_LINING)) >= 40


def test_plants_lean_a_little_each_their_own_way() -> None:
    placed = _line(DEFAULT_LINING)
    tilts = [t for *_, t in placed]
    assert all(abs(p) <= DEFAULT_LINING.lean and abs(r) <= DEFAULT_LINING.lean for p, r in tilts)
    assert all(a != b for a, b in zip(tilts, tilts[1:]))
    assert len(set(tilts)) >= 8
    upright = _line(Lining(lean=0.0))
    assert {t for *_, t in upright} == {(0.0, 0.0)}
    assert tilt_for(3, 0.0) == (0.0, 0.0)


def test_hidden_fraction_draws_the_mesh_onto_the_face() -> None:
    pos, tris = SQUARE
    # A 100-wide, 300-tall card in front of a 200-long, 200-tall face.
    plant = (pos, tris, 100.0, 30.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert abs(hidden_fraction(True, 0.0, (0.0, 200.0), 1, 0.0, 200.0, [plant]) - 0.5) < 0.03
    assert hidden_fraction(True, 0.0, (0.0, 200.0), 1, 0.0, 200.0, []) == 0.0
    # Over the top: the card reaches 100 over a 200 wall, half the length.
    assert abs(hidden_fraction(True, 0.0, (0.0, 200.0), 1, 0.0, 200.0, [plant], above=60.0) - 0.5) < 0.03
    # Turned edge-on to the face it hides almost nothing.
    edge = (pos, tris, 100.0, 30.0, 0.0, 90.0, 1.0, 0.0, 0.0)
    assert hidden_fraction(True, 0.0, (0.0, 200.0), 1, 0.0, 200.0, [edge]) < 0.05


def test_a_prop_lean_reaches_the_map_angles() -> None:
    from zmforge.emit.mapfile import _angle_text

    prop = Prop(model="zmf_prop_corn_stalk", origin=Point(0.0, 0.0, 0.0), yaw=30.0, pitch=-3.5, roll=2.0)
    assert _angle_text(Angles(prop.pitch, prop.yaw, prop.roll)).split() == ["356.5", "30", "2"]


# --- the worst gap, not the mean -----------------------
# A mean can pass while a stretch of wall has no stalk at all: a farmyard wall
# behind a crate with pumpkins, a wheelbarrow and small crates showed only the
# painted corn texture, on a build that passed Z89 at a 79% mean.  Measured on
# that map: 78 stalk-free runs of 80 units and more (longest 421);
# every keep-out took all four rows plus a plant's leaf spread either side,
# and a vignette's trim took every row behind its crates.

CRATE_GROUP = (150.0, 260.0)     # a crate and a wheelbarrow set down in front
DOOR = (300.0, 340.0)            # a real opening in the wall


def _line_round_props(lining: Lining = DEFAULT_LINING) -> list[tuple]:
    """Line a 600-long face the way a recipe does: a back-row plant is turned
    away only if its stem is in the door; a front-row plant by its whole
    20-wide footprint touching the crate group or the door."""
    placed = []

    def place(model, x, y, yaw, scale, tilt=(0.0, 0.0), back=False):
        half = 10.0 * scale
        if back:
            if DOOR[0] <= x <= DOOR[1]:
                return False
        elif any(lo - half <= x <= hi + half for lo, hi in (CRATE_GROUP, DOOR)):
            return False
        placed.append((x, y, scale, back))
        return True

    line_face(True, 0.0, [(0.0, 600.0)], 1, lambda k, row: ("plant", 1.0),
              lambda m, s, yaw: (-10.0 * s, 10.0 * s, -10.0 * s, 10.0 * s), place, lining=lining)
    return placed


def test_back_rows_carry_on_behind_low_props_and_taper_at_an_opening() -> None:
    from zmforge.dressing.lining import longest_bare_run

    placed = _line_round_props()
    behind = [x for x, _y, _s, back in placed if CRATE_GROUP[0] <= x <= CRATE_GROUP[1]]
    assert behind and all(back for x, _y, _s, back in placed if CRATE_GROUP[0] <= x <= CRATE_GROUP[1])
    run, _r0, _r1 = longest_bare_run([x for x, *_ in placed], CRATE_GROUP)
    assert run <= 3 * DEFAULT_LINING.step * DEFAULT_LINING.rows / DEFAULT_LINING.back_rows
    # At the door the front rows step down in size instead of stopping a
    # whole plant short of it.
    near_door = [s for x, _y, s, back in placed if not back and DOOR[0] - 20 <= x <= DOOR[0]]
    assert near_door and min(near_door) < 1.0
    # The earlier rules (no back rows, no taper) bared the whole group.
    old = _line_round_props(Lining(back_rows=0, taper=()))
    assert longest_bare_run([x for x, *_ in old], (0.0, 600.0))[0] >= CRATE_GROUP[1] - CRATE_GROUP[0]


def _lined_wall(gap: tuple[float, float] | None, *, back_fill: bool = False, opening: bool = False):
    """A 200-tall wall face ``y = 0`` lined from x 0 to 800 with corn stalks,
    stalk-free over *gap* (unless *back_fill*: back-row stalks every 24 there),
    a crate group and pumpkins (short, so they hide nothing) set down in front."""
    from zmforge.blueprint.model import Blueprint

    bp = Blueprint("zm_lining_probe")
    items = []
    for i in range(80):
        x = 5.0 + i * 10.0
        if gap and gap[0] <= x <= gap[1]:
            continue
        items.append(("zmf_prop_corn_stalk", Point(x, 20.0 + 18.0 * (i % 3), 0.0), (i * 37) % 360, 2.1))
    if gap and back_fill:
        x = gap[0]
        while x <= gap[1]:
            items.append(("zmf_prop_corn_stalk_thin", Point(x, 18.0, 0.0), 0.0, 3.1))
            x += 24.0
    items += [("zmf_prop_pumpkin", Point(360.0, 60.0, 0.0), 0.0, 1.0),
              ("zmf_prop_pumpkin", Point(420.0, 50.0, 0.0), 0.0, 1.0)]
    bp.place_props(items, id="probe_corn")
    bp.lined_faces = [(True, 0.0, (0.0, 800.0), 1, 0.0, 200.0, 76.0)]
    bp.lined_openings = [(True, 0.0, 1, gap[0], gap[1], "hard")] if opening and gap else []
    return bp


def _bare_errors(bp) -> list[str]:
    from zmforge.verify.lining import check_lining

    return [str(f) for f in check_lining(bp).errors if "no plant in front" in str(f)]


def test_z89_fails_a_bare_stretch_behind_a_crate_group_whatever_the_mean() -> None:
    from zmforge.verify.lining import MAX_BARE, lined_face_bare

    bare = _lined_wall((300.0, 520.0))
    (label, run, r0, r1), = lined_face_bare(bare)
    assert run > MAX_BARE and 290 <= r0 and r1 <= 530
    assert _bare_errors(bare) and "y=0 0..800" in _bare_errors(bare)[0]
    # The pumpkins in the band are too short to count as plants.
    assert lined_face_bare(_lined_wall(None))[0][1] <= 20
    # Back rows behind the group pass; so does a gap the recipe says is a door.
    assert not _bare_errors(_lined_wall((300.0, 520.0), back_fill=True))
    assert not _bare_errors(_lined_wall((300.0, 520.0), opening=True))


def test_a_machine_placed_after_the_lining_records_its_opening() -> None:
    from zmforge.dressing.lining import record_opening
    from zmforge.spatial import Bounds

    bp = _lined_wall((300.0, 420.0))
    assert _bare_errors(bp)
    cabinet = Bounds.between((330.0, 2.0, 0.0), (390.0, 40.0, 90.0))
    assert record_opening(bp, cabinet, "gamble machine") == 1
    assert not _bare_errors(bp)
    # Something across the room from the face opens nothing.
    assert record_opening(bp, Bounds.between((330.0, 300.0, 0.0), (390.0, 340.0, 90.0)), "x") == 0


def test_plants_turn_round_the_whole_circle_and_vary_model_and_size() -> None:
    """Identical stalks read as one clump repeated: the yaws were four right angles, so every clump read alike."""
    from zmforge.dressing.lining import yaw_for
    from zmforge.recipes import corn_maze_parts as parts

    yaws = [yaw_for(k) for k in range(64)]
    assert all(0.0 <= y < 360.0 for y in yaws)
    assert all(abs(a - b) % 360.0 > 20.0 for a, b in zip(yaws, yaws[1:]))
    # Spread over the circle: every 45-degree sector is used.
    assert {int(y // 45) for y in yaws} == set(range(8))
    for row in range(4):
        picks = [parts._band_stalk(k, row) for k in range(row, 4 * 24, 4)]
        assert {m for m, _ in picks} == {parts.STALK, parts.STALK_THIN}, row
        assert all(a != b for a, b in zip(picks, picks[1:])), row
    # The farm's repeated props are turned a little, differently at every spot.
    turned = {round(parts._varied_yaw(parts.CRATE, x * 37.0, x * 11.0, 0.0), 1) for x in range(12)}
    assert len(turned) >= 10 and all(abs(t) <= parts.VARY_YAW[parts.CRATE] for t in turned)


def test_a_wall_buy_may_not_hang_on_a_lined_face() -> None:
    """A buy on the corn cleared the corn in front of it.
    The blueprint refuses one there, Z91 fails one put there anyway, and its
    body no longer excuses a bare stretch from Z89."""
    import pytest

    from zmforge.blueprint.elements import WallWeapon
    from zmforge.errors import BlueprintError
    from zmforge.spatial import Facing
    from zmforge.verify.lining import buys_on_lined_faces, check_lining

    bp = _lined_wall((300.0, 420.0))
    with pytest.raises(BlueprintError):
        bp.place_wall_weapon("pistol_burst", Point(360.0, 2.0, -8.0), Facing.NORTH, id="buy")
    # Off the face (a shed's wall in front of the band) is fine.
    bp.place_wall_weapon("pistol_burst", Point(360.0, 150.0, -8.0), Facing.NORTH, id="shed_buy")
    assert buys_on_lined_faces(bp) == []
    # One that got there anyway (placed before the faces were known).
    late = _lined_wall((300.0, 420.0))
    faces = late.lined_faces
    late.lined_faces = []
    late.place_wall_weapon("pistol_burst", Point(360.0, 2.0, -8.0), Facing.NORTH, id="buy")
    late.lined_faces = faces
    assert [b[0] for b in buys_on_lined_faces(late)] == ["buy"]
    codes = [f.code for f in check_lining(late).errors]
    assert "Z91" in codes
    # ... and the bare stretch behind it is still a Z89 finding.
    assert _bare_errors(late)
    assert isinstance(late.elements(WallWeapon)[0], WallWeapon)


def test_lined_face_at_matches_line_side_span_and_height() -> None:
    from zmforge.dressing.lining import lined_face_at
    from zmforge.spatial import Facing

    faces = [(True, 0.0, (0.0, 800.0), 1, 0.0, 200.0, 76.0)]
    assert lined_face_at(Point(100.0, 2.0, -8.0), Facing.NORTH, faces) == faces[0]
    assert lined_face_at(Point(100.0, 2.0, -8.0), Facing.SOUTH, faces) is None
    assert lined_face_at(Point(100.0, 20.0, -8.0), Facing.NORTH, faces) is None
    assert lined_face_at(Point(900.0, 2.0, -8.0), Facing.NORTH, faces) is None
    assert lined_face_at(Point(100.0, 2.0, 400.0), Facing.NORTH, faces) is None
