"""The Workshop publish settings and thumbnail (``zmforge.workshop``)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from zmforge import Project, workshop
from zmforge.recipes import three_room_map
from zmforge.toolchain.layout import PREVIEW_IMAGE_SIZE

MAP_NAME = "zm_workshop_test"


# -- workshop.json ------------------------------------------------------------


def test_generated_fields_never_carry_a_publisher_id() -> None:
    fields = workshop.workshop_fields("zm_dmv", "DMV")
    assert "PublisherID" not in fields
    assert fields == {
        "Title": "DMV",
        "Description": "",
        "FolderName": "zm_dmv",
        "Thumbnail": workshop.THUMBNAIL_NAME,
    }


def test_the_file_is_plain_utf8_json_without_a_bom() -> None:
    blob = workshop.workshop_json(workshop.workshop_fields("zm_x", "Café"))
    assert not blob.startswith(b"\xef\xbb\xbf")
    assert json.loads(blob.decode("utf-8"))["Title"] == "Café"


def test_merge_keeps_what_the_user_set_on_the_host() -> None:
    existing = {
        "PublisherID": "3312345678",
        "Title": "MY DMV",
        "Description": "typed in the launcher",
        "Tags": "Zombies",
        "Type": "map",
        "Thumbnail": "",
    }
    generated = workshop.workshop_fields("zm_dmv", "DMV")
    merged = workshop.merge_workshop(existing, generated, thumbnail=r"C:\t\zone\thumb.jpg")
    assert merged["PublisherID"] == "3312345678"
    assert merged["Title"] == "MY DMV"
    assert merged["Description"] == "typed in the launcher"
    assert merged["Tags"] == "Zombies" and merged["Type"] == "map"
    assert merged["FolderName"] == "zm_dmv"
    assert merged["Thumbnail"] == r"C:\t\zone\thumb.jpg"


def test_merge_fills_empty_host_values_and_ignores_a_generated_publisher_id() -> None:
    existing = {"PublisherID": "", "Title": "", "Description": ""}
    generated = dict(workshop.workshop_fields("zm_dmv", "DMV"), PublisherID="999")
    merged = workshop.merge_workshop(existing, generated)
    assert merged["PublisherID"] == ""
    assert merged["Title"] == "DMV"
    assert merged["Thumbnail"] == workshop.THUMBNAIL_NAME


def test_merge_with_no_host_file_is_the_generated_file_plus_an_empty_id() -> None:
    generated = workshop.workshop_fields("zm_dmv", "DMV")
    assert workshop.merge_workshop(None, generated) == dict(generated, PublisherID="")


# -- picking the picture --------------------------------------------------------


def _png(path: Path, pixels: np.ndarray) -> Path:
    Image.fromarray(pixels.astype(np.uint8)).save(path)
    return path


def _busy(seed: int, level: int = 128) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(level, 60, (180, 320, 3)), 0, 255)


def _run(root: Path, name: str, shots: dict[str, list[Path]], *, hero: bool = False) -> Path:
    run = root / name / "20260924-000000"
    run.mkdir(parents=True)
    moved = {}
    for room, paths in shots.items():
        moved[room] = []
        for p in paths:
            target = run / p.name
            p.rename(target)
            moved[room].append(str(target))
    (run / "views.json").write_text(json.dumps({"map": name, "shots": moved}))
    if hero:
        _png(run / "hero.png", _busy(9))
    os.symlink(run.name, root / name / "latest")
    return run


def test_no_render_run_means_no_hero(tmp_path) -> None:
    assert workshop.hero_shot("zm_none", tmp_path) is None


def test_a_hero_render_wins(tmp_path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    door = _png(scratch / "hall--door0-n.png", _busy(1))
    run = _run(tmp_path / "render", "zm_h", {"hall": [door]}, hero=True)
    assert workshop.hero_shot("zm_h", tmp_path / "render") == run / "hero.png"


def test_the_busiest_lit_eye_level_shot_is_picked(tmp_path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    flat = _png(scratch / "hall--door0-n.png", np.full((180, 320, 3), 120))
    busy = _png(scratch / "hall--door1-s.png", _busy(2))
    dark = _png(scratch / "vault--door0-e.png", _busy(3, level=5) * 0.1)
    corner = _png(scratch / "vault--high-ne.png", _busy(4) * 1.2)
    run = _run(tmp_path / "render", "zm_s", {"hall": [flat, busy], "vault": [dark, corner]})
    assert workshop.hero_shot("zm_s", tmp_path / "render") == run / "hall--door1-s.png"


def test_only_dark_shots_fall_back_to_the_plan(tmp_path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    dark = _png(scratch / "hall--door0-n.png", np.zeros((180, 320, 3)))
    _run(tmp_path / "render", "zm_d", {"hall": [dark]})
    assert workshop.hero_shot("zm_d", tmp_path / "render") is None


# -- composing ----------------------------------------------------------------


def test_thumbnail_is_the_workshop_square_and_under_a_megabyte() -> None:
    source = Image.fromarray(_busy(5, 140).astype(np.uint8)).resize((1920, 1080))
    image = workshop.compose(source, "The DMV", workshop.THUMBNAIL_SIZE)
    blob = workshop.thumbnail_jpeg(image)
    with Image.open(io.BytesIO(blob)) as image:
        assert image.size == workshop.THUMBNAIL_SIZE
    assert len(blob) < workshop.THUMBNAIL_MAX_BYTES


def test_the_title_is_printed_on_the_foot_of_the_picture() -> None:
    grey = Image.new("RGB", (1024, 576), (128, 128, 128))
    plain = np.asarray(workshop.compose(grey, " ", PREVIEW_IMAGE_SIZE), dtype=np.int16)
    titled = np.asarray(workshop.compose(grey, "Cemetery", PREVIEW_IMAGE_SIZE), dtype=np.int16)
    diff = np.abs(titled - plain).sum(axis=2)
    rows = np.nonzero(diff.max(axis=1) > 60)[0]
    assert rows.size and rows.min() > PREVIEW_IMAGE_SIZE[1] // 2


# -- the generator writes them ------------------------------------------------


def test_commit_writes_workshop_json_and_a_plan_thumbnail(tmp_path) -> None:
    project = Project.create(MAP_NAME, tmp_path / "tools", blueprint=three_room_map(MAP_NAME))
    result = project.commit()
    assert result.ok
    paths = project.paths()
    data = json.loads(paths["workshop_json"].read_text(encoding="utf-8"))
    assert data["FolderName"] == MAP_NAME
    assert data["Thumbnail"] == workshop.THUMBNAIL_NAME
    assert "PublisherID" not in data
    with Image.open(paths["workshop_thumbnail"]) as thumb:
        assert thumb.size == workshop.THUMBNAIL_SIZE and thumb.format == "JPEG"
    assert paths["workshop_thumbnail"].parent == paths["preview_image"].parent


def test_commit_cuts_the_preview_from_a_render_when_there_is_one(tmp_path) -> None:
    plain = Project.create(MAP_NAME, tmp_path / "a", blueprint=three_room_map(MAP_NAME))
    plain.commit()
    plan_preview = plain.paths()["preview_image"].read_bytes()

    render = tmp_path / "render"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _run(render, MAP_NAME, {"hall": [_png(scratch / "hall--door0-n.png", _busy(6))]}, hero=True)
    project = Project.create(MAP_NAME, tmp_path / "b", blueprint=three_room_map(MAP_NAME))
    assert project.commit(render_root=render).ok
    preview = project.paths()["preview_image"]
    assert preview.read_bytes() != plan_preview
    with Image.open(preview) as image:
        assert image.size == PREVIEW_IMAGE_SIZE


def test_a_supplied_preview_still_wins_over_a_render(tmp_path) -> None:
    render = tmp_path / "render"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _run(render, MAP_NAME, {"hall": [_png(scratch / "hall--door0-n.png", _busy(7))]}, hero=True)
    supplied = io.BytesIO()
    Image.new("RGB", PREVIEW_IMAGE_SIZE, (10, 200, 10)).save(supplied, "PNG")
    project = Project.create(MAP_NAME, tmp_path / "c", blueprint=three_room_map(MAP_NAME))
    assert project.commit(render_root=render, preview_image=supplied.getvalue()).ok
    assert project.paths()["preview_image"].read_bytes() == supplied.getvalue()
