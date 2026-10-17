"""Conformance checks P1-P3: does the committed map look finished?

Section 6.1: a usermap's loading screen and menu thumbnail are two loose
PNGs in the map's zone folder, and its display name is the manifest's
``>title`` line.  None of the three is an asset the linker sees, so no build
stage can ever complain about them -- which is exactly why they are checked
here, over the bytes a commit wrote.

Nothing here claims anything about what the game draws.  These are
properties of files: the right names, in the right place, carrying the map's
own layout.

Only the loading screen's dimensions are among those properties.  Published
maps' ``loadingimage.png`` files are 1920x1080, while their
``previewimage.png`` files come in nine different sizes, so the preview's
size is asserted nowhere below
except as the size a *generated* card is drawn at.
"""

from __future__ import annotations

import pytest

from zmforge import ForgeError, Project
from zmforge.emit.manifest import display_title, render_manifest
from zmforge.emit.planview import render_plan
from zmforge.images import ImageError, Raster, decode_png, encode_png, read_png_header
from zmforge.recipes import one_room_map, three_room_map
from zmforge.toolchain.layout import (
    LOADING_IMAGE_NAME,
    LOADING_IMAGE_SIZE,
    PREVIEW_IMAGE_NAME,
    PREVIEW_IMAGE_SIZE,
    ToolsLayout,
)
from zmforge.verify import check_manifest, check_presentation
from zmforge.verify import files as verify_files

MAP_NAME = "zm_forge_gate"


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    """The three-room fixture, committed with its loading screen."""
    root = tmp_path_factory.mktemp("presentation_root")
    project = Project.create(MAP_NAME, root, blueprint=three_room_map(MAP_NAME))
    result = project.commit()
    return project, result


# ---------------------------------------------------------------------------
# The PNG encoder
# ---------------------------------------------------------------------------
def test_encoded_png_has_the_shape_the_template_images_have() -> None:
    """Depth 8, colour type 2, no interlace: the tools' template IHDR."""
    blob = encode_png(4, 3, bytes([7, 8, 9]) * 12)
    header = read_png_header(blob)
    assert (header.width, header.height) == (4, 3)
    assert (header.bit_depth, header.colour_type, header.interlace) == (8, 2, 0)


def test_encoded_png_round_trips_pixel_for_pixel() -> None:
    pixels = bytes(range(0, 60)) * 3
    width, height, back = decode_png(encode_png(6, 10, pixels))
    assert (width, height) == (6, 10)
    assert back == pixels


def test_encoder_rejects_a_buffer_that_is_not_the_stated_size() -> None:
    with pytest.raises(ImageError):
        encode_png(4, 4, b"\x00" * 10)


def test_header_reader_rejects_a_file_that_is_not_a_png() -> None:
    with pytest.raises(ImageError):
        read_png_header(b"GIF89a" + b"\x00" * 40)


def test_decoder_refuses_a_depth_it_does_not_read() -> None:
    blob = bytearray(encode_png(2, 2, b"\x00" * 12))
    blob[24] = 16  # bit depth field of the IHDR
    with pytest.raises(ImageError):
        decode_png(bytes(blob))


# ---------------------------------------------------------------------------
# The raster
# ---------------------------------------------------------------------------
def test_drawing_off_the_edge_clips_instead_of_wrapping() -> None:
    raster = Raster(8, 8, (0, 0, 0))
    raster.fill_rect(-20, -20, 2, 2, (255, 0, 0))
    raster.fill_rect(6, 6, 40, 40, (0, 255, 0))
    assert raster.pixel(0, 0) == (255, 0, 0)
    assert raster.pixel(7, 7) == (0, 255, 0)
    assert raster.pixel(7, 0) == (0, 0, 0)  # no wrap from the first rectangle


def test_outline_is_drawn_inside_the_rectangle_it_is_given() -> None:
    raster = Raster(10, 10, (0, 0, 0))
    raster.outline_rect(2, 2, 8, 8, (1, 2, 3))
    assert raster.pixel(2, 2) == (1, 2, 3)
    assert raster.pixel(7, 7) == (1, 2, 3)
    assert raster.pixel(4, 4) == (0, 0, 0)
    assert raster.pixel(8, 8) == (0, 0, 0)


def test_text_draws_ink_and_reports_the_width_it_used() -> None:
    raster = Raster(60, 12, (0, 0, 0))
    used = raster.text(1, 1, "AB", (255, 255, 255))
    assert used == Raster.text_width("AB")
    inked = sum(
        1
        for y in range(12)
        for x in range(60)
        if raster.pixel(x, y) != (0, 0, 0)
    )
    assert inked > 0
    assert all(raster.pixel(x, 0) == (0, 0, 0) for x in range(60))


def test_unknown_characters_fall_back_rather_than_raising() -> None:
    raster = Raster(20, 12, (0, 0, 0))
    raster.text(0, 0, "\u00e9", (255, 255, 255))  # not in the font
    assert any(raster.pixel(x, y) != (0, 0, 0) for y in range(12) for x in range(20))


# ---------------------------------------------------------------------------
# The plan view
# ---------------------------------------------------------------------------
def test_the_plan_is_a_pure_function_of_the_blueprint() -> None:
    first = render_plan(three_room_map(MAP_NAME), width=320, height=180).png()
    second = render_plan(three_room_map(MAP_NAME), width=320, height=180).png()
    assert first == second


def test_different_layouts_draw_differently() -> None:
    three = render_plan(three_room_map(MAP_NAME), width=320, height=180).png()
    one = render_plan(one_room_map("zm_forge_cell"), width=320, height=180).png()
    assert three != one


def test_the_plan_is_rendered_at_the_size_it_was_asked_for() -> None:
    view = render_plan(three_room_map(MAP_NAME), width=LOADING_IMAGE_SIZE[0], height=LOADING_IMAGE_SIZE[1])
    assert read_png_header(view.png()).size == LOADING_IMAGE_SIZE


def test_every_room_interior_is_drawn_on_the_plan() -> None:
    """P1's point: the image is the map, not a coloured rectangle."""
    from zmforge.blueprint.elements import Room

    blueprint = three_room_map(MAP_NAME)
    view = render_plan(blueprint, width=960, height=540, caption=False)
    raster = view.raster
    for room in blueprint.elements(Room):
        centre = room.interior.centre
        x = round(raster.width / 2 + (centre.x - view.world.centre.x) * view.pixels_per_unit)
        y = round(raster.height / 2 - (centre.y - view.world.centre.y) * view.pixels_per_unit)
        assert raster.pixel(x, y) != (11, 12, 16), f"{room.id} is not on the plan"


def test_the_sky_cage_is_not_what_the_plan_is_framed_on() -> None:
    """Framing on the enclosure would zoom the whole map out by its gap."""
    from zmforge.blueprint.elements import Enclosure, Room, Yard
    from zmforge.spatial import Axis, Span

    blueprint = three_room_map(MAP_NAME)
    view = render_plan(blueprint, width=960, height=540)
    rooms = [room.outer for room in blueprint.elements(Room)]
    yards = [yard.outer for yard in blueprint.elements(Yard)]
    hull = Span.hull_of(rooms + yards)
    assert blueprint.elements(Enclosure), "the fixture is expected to have a shell"
    assert view.world.extent(Axis.X) == pytest.approx(hull.extent(Axis.X) + 128.0)
    assert view.world.extent(Axis.Y) == pytest.approx(hull.extent(Axis.Y) + 128.0)


def test_the_caption_says_the_map_title() -> None:
    view = render_plan(three_room_map(MAP_NAME), width=960, height=540, title="Forge Gate")
    plain = render_plan(three_room_map(MAP_NAME), width=960, height=540, caption=False)
    assert view.raster.pixels != plain.raster.pixels


# ---------------------------------------------------------------------------
# What a commit writes
# ---------------------------------------------------------------------------
def test_p1_commit_writes_both_images_under_the_names_the_tools_use(committed) -> None:
    project, result = committed
    paths = project.paths()
    assert paths["loading_image"].name == LOADING_IMAGE_NAME
    assert paths["preview_image"].name == PREVIEW_IMAGE_NAME
    assert paths["loading_image"].parent == paths["preview_image"].parent
    assert paths["loading_image"].parent.name == "zone"
    assert paths["loading_image"] in result.written
    assert read_png_header(paths["loading_image"].read_bytes()).size == LOADING_IMAGE_SIZE
    assert read_png_header(paths["preview_image"].read_bytes()).size == PREVIEW_IMAGE_SIZE


def test_the_images_land_where_the_layout_says_the_fastfiles_go() -> None:
    layout = ToolsLayout.windows(r"C:\tools")
    assert str(layout.loading_image("zm_x")) == r"C:\tools\usermaps\zm_x\zone\loadingimage.png"
    assert str(layout.preview_image("zm_x")) == r"C:\tools\usermaps\zm_x\zone\previewimage.png"
    assert layout.fastfile_dir("zm_x") in layout.directories_to_create("zm_x")


def test_p1_fires_when_the_loading_screen_is_absent() -> None:
    report = check_presentation(None, None)
    assert {finding.code for finding in report.errors} == {"P1", "P2"}


def test_p1_fires_on_a_file_that_is_not_a_png() -> None:
    report = check_presentation(b"not a png at all", encode_png(*PREVIEW_IMAGE_SIZE, b"\x00" * (600 * 340 * 3)))
    assert [finding.code for finding in report.errors] == ["P1"]


def test_p1_warns_when_the_size_is_not_the_one_every_published_map_uses() -> None:
    report = check_presentation(
        encode_png(64, 64, b"\x00" * (64 * 64 * 3)),
        encode_png(*PREVIEW_IMAGE_SIZE, b"\x00" * (600 * 340 * 3)),
    )
    assert report.errors == []
    assert [finding.code for finding in report] == ["P1"]


#: The ``previewimage.png`` sizes found across a sample of published Workshop
#: maps.  The first is the most common and the rest are spread over the other
#: nine.  Every one of those maps is published and playable, which is the
#: whole argument for P2 not looking at the size.
PUBLISHED_PREVIEW_SIZES = (
    (600, 340),
    (600, 338),
    (600, 360),
    (600, 460),
    (1200, 680),
    (1920, 1080),
    (1992, 1306),
    (2218, 1214),
    (3126, 2027),
)


@pytest.mark.parametrize("size", PUBLISHED_PREVIEW_SIZES)
def test_p2_accepts_every_preview_size_a_published_map_actually_ships(size) -> None:
    """A preview's size is never a finding.

    The mod tools' template has one size, but of the 39 published
    ``previewimage.png`` files, 23 have it and 16 do not, so requiring it
    would fail 41% of a corpus in which every member ships, loads and shows
    its card.
    """
    width, height = size
    report = check_presentation(
        encode_png(*LOADING_IMAGE_SIZE, b"\x00" * (1920 * 1080 * 3)),
        encode_png(width, height, b"\x00" * (width * height * 3)),
    )
    assert list(report) == []


def test_p2_still_catches_the_two_things_the_corpus_does_support() -> None:
    """Absent, and not a PNG.  Those are defects; an unusual size is not."""
    good = encode_png(*LOADING_IMAGE_SIZE, b"\x00" * (1920 * 1080 * 3))
    assert [f.code for f in check_presentation(good, None).errors] == ["P2"]
    assert [f.code for f in check_presentation(good, b"GIF89a nope").errors] == ["P2"]


def test_the_committed_map_passes_every_file_check(committed) -> None:
    project, _ = committed
    report = verify_files(project)
    assert report.errors == []


def test_deleting_the_loading_screen_is_caught_by_the_file_checks(tmp_path) -> None:
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    project.commit()
    project.paths()["loading_image"].unlink()
    report = verify_files(project)
    assert [finding.code for finding in report.errors] == ["P1"]


def test_a_supplied_image_is_written_verbatim(tmp_path) -> None:
    supplied = encode_png(*LOADING_IMAGE_SIZE, bytes([3, 4, 5]) * (1920 * 1080))
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    result = project.commit(loading_image=supplied)
    assert project.paths()["loading_image"].read_bytes() == supplied
    assert result.report.errors == []


def test_a_supplied_image_may_be_a_path(tmp_path) -> None:
    source = tmp_path / "mine.png"
    source.write_bytes(encode_png(*PREVIEW_IMAGE_SIZE, bytes([9]) * (600 * 340 * 3)))
    project = Project.create("zm_forge_cell", tmp_path / "root", blueprint=one_room_map("zm_forge_cell"))
    project.commit(preview_image=source)
    assert project.paths()["preview_image"].read_bytes() == source.read_bytes()


def test_a_supplied_file_that_is_not_a_png_is_refused(tmp_path) -> None:
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    with pytest.raises(ForgeError):
        project.commit(loading_image=b"JPEGish bytes")


def test_a_supplied_image_of_the_wrong_size_is_written_with_a_warning(tmp_path) -> None:
    odd = encode_png(800, 600, b"\x00" * (800 * 600 * 3))
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    result = project.commit(loading_image=odd)
    assert result.ok
    assert "P1" in {finding.code for finding in result.report}
    assert project.paths()["loading_image"].read_bytes() == odd


def test_a_supplied_preview_of_an_odd_size_is_written_without_a_warning(tmp_path) -> None:
    """The commit-time twin of the P2 correction.

    1200x680 is one of the nine non-template sizes measured in the published
    corpus.  A caller who hands us one has not made a mistake.
    """
    odd = encode_png(1200, 680, b"\x00" * (1200 * 680 * 3))
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    result = project.commit(preview_image=odd)
    assert result.ok
    assert "P2" not in {finding.code for finding in result.report}
    assert project.paths()["preview_image"].read_bytes() == odd
    assert verify_files(project).errors == []


def test_opting_out_writes_neither_image_and_does_not_complain(tmp_path) -> None:
    """A commit must not report the caller's own decision as an error."""
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    result = project.commit(loading_screen=False)
    assert not project.paths()["loading_image"].exists()
    assert not project.paths()["preview_image"].exists()
    assert result.ok
    assert {"P1", "P2"}.isdisjoint({finding.code for finding in result.report})
    assert verify_files(project, presentation=False).errors == []
    assert [f.code for f in verify_files(project).errors] == ["P1", "P2"]


def test_a_hand_edited_loading_screen_is_not_clobbered(tmp_path) -> None:
    project = Project.create("zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"))
    project.commit()
    target = project.paths()["loading_image"]
    hand_made = encode_png(*LOADING_IMAGE_SIZE, bytes([1, 2, 3]) * (1920 * 1080))
    target.write_bytes(hand_made)
    result = project.commit()
    assert str(target) in result.skipped
    assert target.read_bytes() == hand_made
    forced = project.commit(force=True)
    assert str(target) in [str(path) for path in forced.written]
    assert target.read_bytes() != hand_made


# ---------------------------------------------------------------------------
# The display name
# ---------------------------------------------------------------------------
def test_p3_the_manifest_carries_a_readable_display_name(committed) -> None:
    project, _ = committed
    manifest = project.paths()["manifest"].read_text(encoding="utf-8")
    assert ">title,Forge Gate" in manifest
    assert check_manifest(manifest, MAP_NAME).errors == []


def test_p3_fires_on_a_manifest_with_no_title(committed) -> None:
    project, _ = committed
    manifest = project.paths()["manifest"].read_text(encoding="utf-8")
    without = "\n".join(
        line for line in manifest.splitlines() if not line.startswith(">title,")
    )
    report = check_manifest(without, MAP_NAME)
    assert report.errors == []
    assert "P3" in {finding.code for finding in report}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("zm_forge_gate", "Forge Gate"),
        ("zm_the_giant", "The Giant"),
        ("zm_x", "X"),
        ("mp_combine", "Mp Combine"),
        ("zm_", "zm_"),
    ],
)
def test_display_titles_are_derived_from_the_asset_name(name, expected) -> None:
    assert display_title(name) == expected


def test_an_explicit_title_wins_and_survives_a_reopen(tmp_path) -> None:
    project = Project.create(
        "zm_forge_cell", tmp_path, blueprint=one_room_map("zm_forge_cell"), title="The Cell"
    )
    project.commit()
    assert ">title,The Cell" in project.paths()["manifest"].read_text(encoding="utf-8")
    reopened = Project.open("zm_forge_cell", tmp_path)
    assert reopened.blueprint.title == "The Cell"
    assert render_manifest("zm_forge_cell", title=reopened.blueprint.title).count(
        ">title,The Cell"
    ) == 1
