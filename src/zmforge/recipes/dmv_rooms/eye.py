"""zm_dmv dense pass: the eye room (key ``eye``).  See the package docstring.

A tiny room where the test never ended.  What the dense pass adds, round the
chart, the Deadshot machine and the shotgun buy (all of which stay clear):

* **the examiner's station** -- the drops and the examiner's own bottle on
  the table, a folder on the failed-test stack;
* **the line on the floor** -- three sheets taped end to end across the room,
  the "stand here" mark, which is also the ``eye_line`` quirk;
* **the lenses box** -- a carton of trial lenses in the north-east corner with
  its paperwork, the ``eye_lenses`` quirk;
* **the chart wall** -- more anatomy posters and a caution sign, and the
  plaster people knocked off it getting too close to read line five;
* **the floor** -- failed tests, cups and balled paper that missed the bin.

Nothing solid but the lenses carton, which stands in a corner.

``refractor``  the phoropter: two lens cans on an arc lamp's arm in front of
  the exam chair, facing the chart.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...dressing import on_wall
from ._kit import Bounds, Facing, Point, RoomContext, _belt_line, _centred, _floor, _mounted, _on, _rest_on, _top_of

#: The room's quirks (see :func:`zmforge.script.tricks.use_notices`).
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "eye_drops": ("EYE DROPS: hold ^3[{+activate}]^7 to dilate", (
        "Your pupils are now dilated. Please wait 45 minutes.",
        "Please do not operate a vehicle. (You do not have a vehicle.)",
        "The drops are in a wine bottle. The examiner says this is normal.",
    )),
    "eye_line": ("STAND ON THE LINE: hold ^3[{+activate}]^7", (
        "Further back.",
        "Further back.",
        "You are now in the hallway. Read line one.",
    )),
    "eye_lenses": ("CORRECTIVE LENSES: hold ^3[{+activate}]^7 to try", (
        "Better, or worse?",
        "Better, or worse?",
        "Thank you. Your answer was wrong.",
    )),
}

#: The examiner's table, as :func:`zmforge.recipes.dmv._furnish_lived_in`
#: places it: against the east wall, 50 in off the south one.
TABLE = "p7_cai_work_table_metal_03_white"
#: The lenses carton, turned so its short side runs along the east wall.
LENSES = "p7_container_cardboard_box_01"


# --------------------------------------------------------------------------
# The eye chart: a white board on the north wall with real letters on it
# --------------------------------------------------------------------------
# Picture frames of falling size with no letters do not read as a chart, and
# a player cannot find the Vision Test in them (nothing reads as letters
# to shoot).  Wall-art textures do not link in
# a Wine build, so the letters are brushes: a 5x5 block font, each letter cut
# into as few boxes as cover it, dark rubber trim on a white moulding board.
# The quest's targets (:func:`chart_target`) are read off the same layout, so
# the spot a player must hit is always the centre of the letter drawn there.
#
# Rows shrink the way a Snellen chart does (letter heights 25, 15, 10, 7, 5):
# row 1 is the E, row 2 hides the F beside a decoy P, row 3 hides the P among
# decoys, rows 4 and 5 are decoys (row 5 is the "R U N" of the eye test
# notice's last line).  Measured texture means (colour maps on the install): the moulding reads 200 grey, the rubber trim 51.

#: The font.  ``#`` is ink; each letter is 5 cells by 5, top row first.
FONT: dict[str, tuple[str, ...]] = {
    "C": (".####", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "####.", "#....", "#####"),
    "F": ("#####", "#....", "####.", "#....", "#...."),
    "L": ("#....", "#....", "#....", "#....", "#####"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "####.", "#....", "#...."),
    "R": ("####.", "#...#", "####.", "#..#.", "#...#"),
    "T": ("#####", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", ".###."),
    "Z": ("#####", "...#.", "..#..", ".#...", "#####"),
}
#: The rows, top down: the letters and the height each is drawn at.
CHART_ROWS: tuple[tuple[str, float], ...] = (
    ("E", 25.0),
    ("FP", 15.0),
    ("TOPZ", 10.0),
    ("LEDFC", 7.0),
    ("RUN", 5.0),
)
#: The Vision Test's letters, in order, as (row, column) on :data:`CHART_ROWS`.
VISION_LETTERS: tuple[tuple[int, int], ...] = ((0, 0), (1, 0), (2, 2))
#: Blank cells between two letters of a row.
LETTER_GAP_CELLS = 2
#: Board layout: margins round the letters and the gap under each row.
CHART_MARGIN = 6.0
CHART_ROW_GAPS = (8.0, 7.0, 6.0, 5.0)
#: The board's top, above the floor; it hangs down from there.
CHART_TOP = 170.0
#: How far the board stands off the wall, and the letters off the board.
CHART_DEPTH = 1.0
LETTER_DEPTH = 0.75


@dataclass(frozen=True)
class ChartLetter:
    """One letter as drawn: which row and column, its outline on the wall
    (``x0``..``x1`` across, ``z0``..``z1`` up) and the boxes that draw it."""

    char: str
    row: int
    col: int
    x0: float
    x1: float
    z0: float
    z1: float
    face_y: float
    boxes: tuple[Bounds, ...]

    @property
    def height(self) -> float:
        return self.z1 - self.z0

    @property
    def centre(self) -> tuple[float, float, float]:
        """The middle of the letter, half a unit out in front of its face."""
        return ((self.x0 + self.x1) / 2.0, self.face_y - 0.5, (self.z0 + self.z1) / 2.0)


def _cells_to_rects(glyph: tuple[str, ...]) -> list[tuple[int, int, int, int]]:
    """Cover a glyph's ink with few rectangles ``(col, row, width, height)``:
    at each uncovered ink cell, the larger of a run across then down, or a
    run down then across."""
    ink = {(c, r) for r, line in enumerate(glyph) for c, ch in enumerate(line) if ch == "#"}
    used: set[tuple[int, int]] = set()
    rects = []
    for r in range(len(glyph)):
        for c in range(len(glyph[0])):
            if (c, r) not in ink or (c, r) in used:
                continue
            free = lambda cc, rr: (cc, rr) in ink and (cc, rr) not in used  # noqa: E731
            # across, then down
            w = 1
            while free(c + w, r):
                w += 1
            h = 1
            while all(free(c + i, r + h) for i in range(w)):
                h += 1
            wide = (c, r, w, h)
            # down, then across
            h2 = 1
            while free(c, r + h2):
                h2 += 1
            w2 = 1
            while all(free(c + w2, r + j) for j in range(h2)):
                w2 += 1
            tall = (c, r, w2, h2)
            best = wide if w * h >= w2 * h2 else tall
            bc, br, bw, bh = best
            used |= {(bc + i, br + j) for i in range(bw) for j in range(bh)}
            rects.append(best)
    return rects


def _row_width(letters: str, height: float) -> float:
    cell = height / 5.0
    return (len(letters) * 5 + (len(letters) - 1) * LETTER_GAP_CELLS) * cell


def chart_board(interior: Bounds, floor_z: float) -> Bounds:
    """The white board, centred on the north wall."""
    width = max(_row_width(t, h) for t, h in CHART_ROWS) + 2.0 * CHART_MARGIN
    height = (sum(h for _t, h in CHART_ROWS) + sum(CHART_ROW_GAPS)
              + 2.0 * CHART_MARGIN)
    cx, wall = interior.centre.x, interior.maxs.y
    top = floor_z + CHART_TOP
    return Bounds.between((cx - width / 2.0, wall - CHART_DEPTH, top - height),
                          (cx + width / 2.0, wall, top))


def chart_letters(interior: Bounds, floor_z: float) -> list[ChartLetter]:
    """Every letter on the chart, top row first, each row centred."""
    board = chart_board(interior, floor_z)
    cx = interior.centre.x
    face = board.mins.y - LETTER_DEPTH
    out: list[ChartLetter] = []
    top = board.maxs.z - CHART_MARGIN
    for row, (text, height) in enumerate(CHART_ROWS):
        cell = height / 5.0
        left = cx - _row_width(text, height) / 2.0
        for col, char in enumerate(text):
            x0 = left + col * (5 + LETTER_GAP_CELLS) * cell
            boxes = tuple(
                Bounds.between((x0 + c * cell, face, top - (r + h) * cell),
                               (x0 + (c + w) * cell, board.mins.y, top - r * cell))
                for c, r, w, h in _cells_to_rects(FONT[char])
            )
            out.append(ChartLetter(char, row, col, x0, x0 + 5 * cell,
                                   top - height, top, face, boxes))
        if row < len(CHART_ROW_GAPS):
            top -= height + CHART_ROW_GAPS[row]
    return out


def chart_target(room, row: int, col: int) -> tuple[tuple[float, float, float], float]:
    """The Vision Test's spot for the letter at ``row``, ``col`` of *room*'s
    chart, and an aim radius of half that letter's height."""
    for letter in chart_letters(room.interior, room.floor_z):
        if letter.row == row and letter.col == col:
            return letter.centre, letter.height / 2.0
    raise KeyError((row, col))


def _table(ctx: RoomContext) -> tuple[float, float, float]:
    inside = ctx.room.interior
    return inside.maxs.x - 12.0, inside.mins.y + 50.0, _top_of(TABLE, ctx.room.floor_z)


def _lenses(ctx: RoomContext) -> tuple[float, float]:
    inside = ctx.room.interior
    return inside.maxs.x - 15.0, inside.maxs.y - 20.0


def _line_y(ctx: RoomContext) -> float:
    return ctx.room.interior.mins.y + 124.0


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    inside = ctx.room.interior
    z = ctx.room.floor_z
    tx, ty, _top = _table(ctx)
    lx, ly = _lenses(ctx)
    return [
        # In front of the table, west of it, 80 clear of the door (at ty - 6
        # it is only 72 clear) and off the Deadshot machine.
        ("eye_drops", Point(tx - 46.0, ty + 10.0, z)),
        # On the taped line, west of centre, clear of the shotgun buy.
        ("eye_line", Point(inside.centre.x - 30.0, _line_y(ctx) - 20.0, z)),
        # Beside the carton, far enough from the chart's own notice.
        ("eye_lenses", Point(lx - 26.0, ly - 4.0, z)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the eye room."""
    inside = ctx.room.interior
    x0, x1, y0, y1 = inside.mins.x, inside.maxs.x, inside.mins.y, inside.maxs.y
    z = ctx.room.floor_z
    cx = inside.centre.x

    # ---- the examiner's station: the table's free east strip -----------
    tx, ty, top = _table(ctx)
    stack_top = _top_of("p7_office_paper_stack_sml", top)
    ctx.put([
        _on("p7_bottle_glass_wine_01", tx + 7.0, ty - 26.0, top, 0.0),       # the drops
        _on("p7_bottle_glass_liquor_01", tx + 7.0, ty - 12.0, top, 90.0),    # the examiner's
        _on("p7_cleaning_paper_folded_wrapped", tx + 7.0, ty + 2.0, top, 0.0),
        _on("p7_office_paper_folder_pink", tx, ty + 22.0, stack_top, 8.0),
    ], "dense_eye_station")

    # ---- the line on the floor: three sheets end to end ----------------
    line_y = _line_y(ctx)
    ctx.put([
        _floor("p7_office_paper_sheet_01", cx - 30.0 + dx, line_y, z, 90.0, solid=False)
        for dx in (-16.0, 0.0, 16.0)
    ], "dense_eye_line")

    # ---- the refractor: the exam chair's set piece ---------------------
    # The chair in the south-west corner faces the chart; an arc floor lamp
    # stands on its west side with the arm reaching over in front of it,
    # and on the arm's head sit two lens cans side by side -- a phoropter,
    # out of the only lens-on-a-body model the measured palette has (an
    # eye room needs a refractor facing the chart).
    # The lamp is solid, so the checks read the lens cans as standing on it;
    # its box is its arm's reach, over the corner the chair already blocks.
    arm = "p7_light_metal_modern_floor_01"
    arm_top = _top_of(arm, z)
    ax, ay = x0 + 16.0, y0 + 96.0
    head_x = ax + 44.0
    ctx.put([
        (arm, Point(ax, ay, _rest_on(arm, z)), 0.0, 1.0, True),
        # The can's box straddles its origin in Z, which the checks read as
        # a fitting on a plane: its origin sits on the arm's head.
        _centred("p7_zm_der_light_spot_housing", head_x - 7.0, ay, arm_top + 4.0, 90.0, scale=0.35),
        _centred("p7_zm_der_light_spot_housing", head_x + 7.0, ay, arm_top + 4.0, 90.0, scale=0.35),
    ], "dense_eye_refractor")

    # ---- the lenses carton and its paperwork ---------------------------
    lx, ly = _lenses(ctx)
    box_top = _top_of(LENSES, z)
    ctx.put([
        _floor(LENSES, lx, ly, z, 90.0),
        _on("p7_office_paper_sheet_02", lx, ly - 8.0, box_top, 10.0),
        _on("p7_office_paper_folder_blue", lx, ly + 10.0, box_top, 95.0),
        _floor("p7_office_paper_sheet_02", lx - 30.0, ly + 10.0, z, 40.0, solid=False),
        _floor("p7_office_paper_sheet_12", lx - 50.0, ly - 2.0, z, 75.0, solid=False),
        _floor("p7_office_paper_sheet_10", lx - 26.0, ly - 30.0, z, 150.0, solid=False),
        _floor("p7_office_paper_sheet_08", lx - 64.0, ly + 8.0, z, 205.0, solid=False),
    ], "dense_eye_lenses")

    # ---- the chart wall and the others ---------------------------------
    # The poster and the sign stand east of the letter board (which reaches
    # 32 either side of the wall's centre): the poster is 39 across, so its
    # middle at +54 leaves 3 of wall; the 28-wide sign sits 20 off the corner.
    ctx.put([
        _mounted("p7_zm_der2_poster_anatomy_03", Point(cx + 54.0, y1 - 0.5, z + 110.0),
                 Facing.SOUTH),
        _mounted("p7_signage_caution_warning_01", Point(x1 - 20.0, y1 - 0.5, z + 106.0),
                 Facing.SOUTH),
        _mounted("p7_zm_der2_poster_anatomy_02", Point(x1 - 0.5, ty + 4.0, z + 118.0),
                 Facing.WEST),
        _mounted("p7_zm_der_signage_caution", Point(x1 - 0.5, y1 - 88.0, z + 80.0),
                 Facing.WEST),
        _mounted("p7_zm_der2_poster_anatomy_07", Point(x0 + 0.5, y1 - 96.0, z + 150.0),
                 Facing.EAST),
    ], "dense_eye_walls")
    # Under the chart: what came off the wall when people leaned in.
    ctx.put([
        _floor("p7_debris_plaster_rubble_med_01", cx + 22.0, y1 - 6.0, z, 90.0, solid=False),
        _floor("p7_debris_rockychunks_small_05", cx - 6.0, y1 - 14.0, z, 20.0, solid=False),
        _floor("p7_debris_brick_chunk_01", cx + 8.0, y1 - 24.0, z, 60.0, solid=False),
        _floor("p7_debris_brick_chunk_02", cx - 22.0, y1 - 26.0, z, 130.0, solid=False),
    ], "dense_eye_chart_rubble")

    # ---- the floor: failed tests, cups, and paper that missed the bin --
    litter = [
        ("p7_office_paper_sheet_12", x0 + 48.0, y0 + 16.0, 20.0),
        ("p7_cleaning_paper_ball_brown", x0 + 44.0, y0 + 40.0, 0.0),
        ("p7_cleaning_paper_ball_brown", x0 + 12.0, y0 + 50.0, 70.0),
        ("p7_cleaning_paper_brown", x0 + 64.0, y0 + 40.0, 110.0),
        ("p7_debris_trash_cup_coffee_02", cx - 15.0, y0 + 54.0, 40.0),
        ("p7_office_paper_sheet_10", cx + 25.0, y0 + 40.0, 300.0),
        ("p7_office_paper_folder_blue", x1 - 40.0, y0 + 70.0, 25.0),
        ("p7_cleaning_paper_ball_brown", x1 - 64.0, y0 + 84.0, 0.0),
        ("p7_office_paper_sheet_08", x0 + 69.0, y0 + 89.0, 65.0),
        ("p7_office_paper_sheet_09", cx + 40.0, y1 - 74.0, 15.0),
        ("p7_debris_trash_cup_coffee_02", cx + 15.0, y1 - 84.0, 200.0),
        ("p7_cleaning_paper_ball_brown", cx - 30.0, y1 - 94.0, 0.0),
        ("p7_office_paper_sheet_03", cx - 20.0, y1 - 34.0, 45.0),
        ("p7_office_paper_sheet_01", cx - 35.0, y1 - 8.0, 100.0),
        ("p7_cleaning_paper_ball_brown", x1 - 26.0, y1 - 74.0, 0.0),
        ("p7_desk_metal_old_01_drawer_small_01", cx + 55.0, y0 + 26.0, 15.0),
    ]
    ctx.put([_floor(model, x, y, z, yaw, solid=False) for model, x, y, yaw in litter],
            "dense_eye_litter")
    _dress_exam(ctx)


# ==========================================================================
# The DMV eye-test pass (the room needed far more props to read as a
# DMV).  All of it clear of the chart, the reading line and the sight line
# between them (the middle of the room from the line north), of the strips
# in front of Deadshot and the shotgun, and of the riser.  One solid: a
# forms cabinet in the north-west corner.
#
# Vignettes (ids ``dense_eye_<name>``):
#
# ``tray``      the lens tray on a crate beside the exam chair: trial lenses,
#               tissues and a form
# ``waiting``   the examiner's own line: three posts from the door to the
#               table and the tape at its head
# ``stool``     the examiner's stool, pushed back from the table
# ``cabinet``   the forms cabinet in the north-west corner, forms on top
# ``lens_stock`` more boxes of lenses beside the carton
# ``posters``   rules, eye-test notices and frames round the upper walls
# ``floor``     failed tests, tissues and cups everywhere a player is not
#               standing to read the chart
# ``boards``    the boards somebody meant to nail over the door, dropped
# ==========================================================================
import random as _random  # noqa: E402

from ._kit import _seated  # noqa: E402


_EYE_LITTER = (
    "p7_office_paper_sheet_10", "p7_cleaning_paper_towel", "p7_office_paper_sheet_12",
    "p7_cleaning_paper_ball_brown", "p7_office_paper_sheet_02", "p7_debris_trash_cup_coffee_02",
    "p7_office_paper_sheet_09", "p7_cleaning_paper_towel", "p7_debris_trash_paper_04",
    "p7_office_paper_folder_pink", "p7_office_paper_sheet_01", "p7_debris_trash_paper_10",
    "p7_box_copy_paper_sheet", "p7_cleaning_paper_ball_brown", "p7_office_paper_sheet_03",
    "p7_debris_trash_cup_red_02", "p7_office_paper_sheet_08", "p7_debris_trash_paper_05",
)


def _dress_exam(ctx: RoomContext) -> None:
    """The DMV eye-test pass (see the block comment above)."""
    inside = ctx.room.interior
    x0, x1, y0, y1 = inside.mins.x, inside.maxs.x, inside.mins.y, inside.maxs.y
    z = ctx.room.floor_z
    cx = inside.centre.x

    # ---- the lens tray on a stand at the exam chair's elbow -----------------
    # Not in the south-west corner: the lived-in pass's bin stands there and
    # dmv._clear_door_bands drops it, with anything riding on its footprint.
    crate = "p7_crate_wood_01_short"
    kx, ky = x0 + 68.0, y0 + 56.0
    c_top = _top_of(crate, z)
    tray = "p7_box_wood_wine_storage"
    t_top = _top_of(tray, c_top)
    vial = "p7_zm_der_light_bulb_glass_cover"
    ctx.put([
        _floor(crate, kx, ky, z, 0.0, solid=False),
        _on(tray, kx + 2.0, ky - 2.0, c_top, 90.0),
        _on(vial, kx - 4.0, ky - 4.0, t_top, 0.0),
        _on(vial, kx + 3.0, ky - 4.0, t_top, 0.0),
        _on(vial, kx + 9.0, ky - 3.0, t_top, 0.0),
        _on("p7_cleaning_paper_folded_wrapped", kx - 9.0, ky + 8.0, c_top, 90.0),
        _on("p7_cleaning_paper_towel", kx + 6.0, ky + 8.0, t_top, 25.0),
        _on("p7_office_paper_sheet_10", kx + 2.0, ky + 1.0, t_top, 70.0),
    ], "dense_eye_tray")

    # ---- the examiner's own line: door to table ----------------------------
    # Belted post to post (bare poles do not read as a waiting line).
    post = "p7_handrail_post_end"
    line = [(x1 - 42.0, y0 + y) for y in (24.0, 56.0, 88.0)]
    _belt_line(ctx.bp, line, z, "eye_belt")
    ctx.put([
        _floor(post, x, y, z, 0.0, solid=False) for x, y in line
    ] + [
        _floor("p7_office_paper_sheet_01", x1 - 62.0 + dx, y0 + 94.0, z, 90.0, solid=False)
        for dx in (-16.0, 0.0)
    ], "dense_eye_waiting")

    # ---- the examiner's stool, pushed back from the table -----------------
    tx, ty, top = _table(ctx)
    ctx.put([
        _seated("p7_sgen_chair_dining_future", Point(tx - 44.0, ty + 22.0, z), Facing.EAST,
                solid=False),
    ], "dense_eye_stool")

    # ---- the forms cabinet, north-west corner ------------------------------
    cab = "p7_file_cab_metal_02"
    fx, fy = x0 + 9.5, y1 - 15.5
    f_top = _top_of(cab, z)
    ctx.put([
        _floor(cab, fx, fy, z, 0.0),
        _on("p7_office_paper_stack_sml", fx, fy - 6.0, f_top, 90.0),
        _on("p7_office_paper_folder_blue", fx + 1.0, fy - 2.0, _top_of("p7_office_paper_stack_sml", f_top), 100.0),
        # On the stack, not past the cabinet's back into the wall.
        _on("p7_book_office_binder_open", fx, fy + 1.0,
            _top_of("p7_office_paper_folder_blue", _top_of("p7_office_paper_stack_sml", f_top)), 0.0),
    ], "dense_eye_cabinet")

    # ---- more boxes of trial lenses beside the carton ----------------------
    lx, ly = _lenses(ctx)
    small = "p7_box_wood_01_sm"
    s_top = _top_of(small, z)
    ctx.put([
        _floor(small, lx - 33.0, y1 - 13.0, z, 90.0, solid=False),
        _on("p7_box_wood_wine_storage_tan", lx - 33.0, y1 - 13.0, s_top, 90.0),
        _floor("p7_crate_wood_01_short_open_lid", lx - 6.0, ly - 40.0, z, 20.0, solid=False),
    ], "dense_eye_lens_stock")

    # ---- rules, eye-test notices and frames round the upper walls ----------
    frame, anat = "p7_picture_frame_modern_01", "p7_zm_der2_poster_anatomy_"
    ctx.put([on_wall(m, f, a, w, centre_z=zc) for m, f, a, w, zc in (
        # west wall, either side of the shotgun
        (frame, Facing.EAST, y0 + 26.0, x0, z + 104.0),
        (anat + "05", Facing.EAST, y0 + 76.0, x0, z + 110.0),
        (anat + "06", Facing.EAST, y1 - 13.0, x0, z + 108.0),
        # north wall, clear of the chart
        (anat + "06", Facing.SOUTH, x0 + 14.0, y1, z + 110.0),
        (frame, Facing.SOUTH, x0 + 44.0, y1, z + 154.0),
        (frame, Facing.SOUTH, cx + 60.0, y1, z + 154.0),
        # east wall, over the table and the carton, and over Deadshot's sign
        ("p7_signage_loading_zone_02", Facing.WEST, y0 + 15.0, x1, z + 104.0),
        (anat + "06", Facing.WEST, y1 - 14.0, x1, z + 104.0),
        (frame, Facing.WEST, y1 - 84.0, x1, z + 154.0),
        # south wall: over the door, and above the board and the picture
        ("p7_zm_der_signage_office_maxis", Facing.NORTH, cx, y0, z + 132.0),
        ("p7_zm_der2_signage_hazard_01", Facing.NORTH, cx - 53.0, y0, z + 124.0),
        (frame, Facing.NORTH, x1 - 33.0, y0, z + 154.0),
        (frame, Facing.NORTH, x0 + 33.0, y0, z + 154.0),
    )], "dense_eye_posters")

    # ---- the floor: failed tests and tissues -------------------------------
    rng = _random.Random(55023)
    line_y = _line_y(ctx)
    busy = [  # (x0, y0, x1, y1): solids, the line, the strips, the sight line
        (x1 - 64.0 - 6.0, 516.0, x1, 584.0),                 # Deadshot's strip
        (x0, 516.0, x0 + 68.0, 584.0),                       # the shotgun's
        (cx - 60.0, line_y - 12.0, cx + 20.0, line_y + 12.0),  # the taped line
        (x1 - 24.0, y0, x1, y0 + 94.0),                      # the table
        (x0, y0 + 44.0, x0 + 56.0, y0 + 86.0),               # the exam chair
        (x0, y0 + 84.0, x0 + 80.0, y0 + 108.0),              # the refractor
        (x0 + 20.0, y1 - 90.0, x0 + 90.0, y1 - 20.0),        # the plant, the riser
        (x0, y1 - 34.0, x0 + 22.0, y1),                      # the cabinet
        (x1 - 32.0, y1 - 42.0, x1, y1),                      # the carton
        (x0 + 50.0, y0 + 38.0, x0 + 86.0, y0 + 74.0),        # the lens tray
    ]
    litter = []
    n = 0
    tries = 0
    while n < 26 and tries < 600:
        tries += 1
        x, y = rng.uniform(x0 + 8.0, x1 - 8.0), rng.uniform(y0 + 8.0, y1 - 8.0)
        if any(a <= x <= c and b <= y <= d for a, b, c, d in busy):
            continue
        litter.append(_floor(_EYE_LITTER[n % len(_EYE_LITTER)], x, y, z,
                             rng.uniform(0.0, 360.0), solid=False))
        n += 1
    ctx.put(litter, "dense_eye_floor")

    # ---- the boards somebody meant to nail over the door ------------------
    ctx.put([
        _floor("p7_debris_wood_board_2pc_2x4x128_lt", cx + 6.0, y0 + 14.0, z, 4.0, solid=False),
        _floor("p7_debris_wood_board_splinter_02", cx - 30.0, y0 + 24.0, z, 70.0, solid=False),
        _floor("p7_debris_wood_board_splinter_03", cx + 22.0, y0 + 30.0, z, 150.0, solid=False),
        _floor("p7_debris_wood_board_cluster_03", cx + 42.0, y1 - 46.0, z, 35.0, solid=False),
    ], "dense_eye_boards")
