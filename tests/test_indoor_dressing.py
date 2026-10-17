"""The indoor dressing library: dressing.indoor (heaps), dressing.walldetail
(wall and ceiling detail), dressing.setpiece (open-floor splitter) and the
checks that hold big rooms to them (S2 at 40%, S5 overhead, S6 flat walls)."""

from __future__ import annotations

import random

import pytest

from zmforge.blueprint.elements import Room
from zmforge.dressing import indoor as ind
from zmforge.dressing import setpiece as sp
from zmforge.dressing import vignette as vg
from zmforge.dressing import walldetail as wd
from zmforge.recipes.layouts import one_room_map
from zmforge.recipes.props import MODEL_BOX
from zmforge.spatial import Bounds

BIG = Bounds.between((-700, -600, 0), (700, 600, 336))


def _room(bp):
    return [r for r in bp.elements(Room)][0]


def _fresh():
    bp = one_room_map("zm_indoor_test", bounds=BIG)
    return bp, _room(bp)


def _codes(report, code):
    return [f for f in report.findings if f.code == code]


def test_every_indoor_kind_is_a_one_line_story_from_measured_stock_models() -> None:
    assert len(ind.INDOOR_KINDS) >= 7
    spot = ind.IndoorSpot(0.0, 0.0, 0.0, 90.0, "wall_face", "r", width=240.0, back=0.0, reach=160.0)
    for kind in ind.INDOOR_KINDS.values():
        assert kind.story and "\n" not in kind.story and kind.story.endswith(".")
        parts = kind.build(random.Random(1), spot)
        items = [p for p in parts if isinstance(p, vg.Item)]
        assert 5 <= len(items) <= 40, (kind.name, len(items))
        assert [p for p in parts if getattr(p, "core", False)], kind.name
        for item in items:
            assert item.model in MODEL_BOX, (kind.name, item.model)
            # known bad models stay out (placeholder material, bad foliage)
            assert item.model not in ("p7_desk_metal_old_01", "p7_foliage_grass_dry_03"), kind.name
            assert "ar_cqb" not in item.model
    for theme, names in ind.THEMES.items():
        assert set(names) <= set(ind.INDOOR_KINDS), theme


@pytest.mark.parametrize("kind", sorted(ind.INDOOR_KINDS))
def test_each_indoor_kind_places_whole_in_a_plain_room(kind) -> None:
    bp, room = _fresh()
    placer = ind.RoomPlacer(bp, room)
    k = ind.INDOOR_KINDS[kind]
    made = None
    for spot in ind.wall_spots(room, placer, width=k.needs[0], depth=k.needs[1]):
        made = ind.place_vignette(bp, kind, spot, random.Random(3), placer, ident="t",
                                  library=ind.INDOOR_KINDS, settle_models=ind.INDOOR_SETTLE)
        if made:
            break
    placer.flush()
    assert made is not None and made.props >= 5, kind


def test_the_placer_keeps_door_lanes_windows_and_keepouts_clear() -> None:
    bp, room = _fresh()
    lanes = ind.door_lanes(room)
    assert len(lanes) == len(room.apertures)
    keep = Bounds.between((-100, -100, 0), (100, 100, 336))
    placer = ind.RoomPlacer(bp, room, [keep])
    for lane in lanes + [keep]:
        probe = Bounds.between((lane.mins.x + 1, lane.mins.y + 1, room.floor_z),
                               (lane.mins.x + 20, lane.mins.y + 20, room.floor_z + 8))
        assert not placer.fits_box("r", probe)
    assert not placer.fits("r", "p7_crate_wood_01", 0.0, 0.0, room.floor_z, 0.0, 1.0, True)


def test_dress_indoor_lays_distinct_stories_apart() -> None:
    bp, room = _fresh()
    placer = ind.RoomPlacer(bp, room)
    got = ind.dress_indoor(bp, room, placer, random.Random(5), count=4, ident="h", theme="institution")
    placer.flush()
    assert len(got) >= 3
    assert len({v.kind for v in got}) == len(got)


def test_wall_detail_reaches_the_overhead_and_wall_targets() -> None:
    from zmforge.verify.scenes import check_scenes

    bp, room = _fresh()
    before = check_scenes(bp)
    assert _codes(before, "S5") and _codes(before, "S6")
    rep = wd.dress_walls(bp, room, "institution", ident="wd")
    assert rep.per_k2() >= 60.0, rep.parts
    assert rep.per_100() >= 1.5, rep.parts
    for part in ("skirting", "wainscot", "rail", "pilaster", "beam", "duct", "riser", "hanging"):
        assert rep.parts.get(part), part
    after = check_scenes(bp)
    assert not _codes(after, "S5") and not _codes(after, "S6")


@pytest.mark.parametrize("theme", sorted(wd.THEMES))
def test_every_wall_theme_clears_the_bars(theme) -> None:
    bp, room = _fresh()
    rep = wd.dress_walls(bp, room, theme, ident="wd")
    assert rep.per_k2() >= 60.0 and rep.per_100() >= 1.5, (theme, rep.per_k2(), rep.per_100())


def test_wall_detail_leaves_openings_and_keepouts_bare() -> None:
    from zmforge.blueprint.elements import Massing
    from zmforge.dressing.walldetail import _solid_box

    bp, room = _fresh()
    keep = Bounds.between((-200, room.interior.mins.y - 1, 0), (200, room.interior.mins.y + 60, 336))
    wd.dress_walls(bp, room, "institution", ident="wd", keepouts=[keep])
    holes = [(b.mins.x - 8, b.mins.y - 8, b.mins.z, b.maxs.x + 8, b.maxs.y + 8, b.maxs.z)
             for b in room.aperture_boxes]
    holes.append((keep.mins.x, keep.mins.y, keep.mins.z, keep.maxs.x, keep.maxs.y, keep.maxs.z))
    for m in bp.elements(Massing):
        if not m.id.startswith("wd_") or "beam" in m.id:
            continue
        for s in m.solids:
            x0, y0, z0, x1, y1, z1 = _solid_box(s)
            for h in holes:
                inside = x0 < h[3] - 0.5 and x1 > h[0] + 0.5 and y0 < h[4] - 0.5 and y1 > h[1] + 0.5 \
                    and z0 < h[5] - 0.5 and z1 > h[2] + 0.5
                assert not inside, (m.id, h)


def test_the_splitter_breaks_up_open_floor_and_keeps_lanes() -> None:
    from zmforge.verify.scenes import check_scenes

    bp, room = _fresh()
    wide = sp.open_stretches(bp, room)
    assert 2 * wide[0][2] >= 512
    assert _codes(check_scenes(bp), "S3")
    placer = ind.RoomPlacer(bp, room)
    got = sp.split_open_floor(bp, room, placer, random.Random(1), ident="sp", lane=128.0)
    placer.flush()
    assert got
    after = sp.open_stretches(bp, room)
    assert after[0][2] < wide[0][2]
    assert not _codes(check_scenes(bp), "S3")
    # every piece keeps a lane: nothing of it is within 96 of a wall
    b = room.interior
    for v in got:
        for x0, y0, x1, y1 in v.boxes:
            assert x0 - b.mins.x >= 96 and b.maxs.x - x1 >= 96, v.kind
            assert y0 - b.mins.y >= 96 and b.maxs.y - y1 >= 96, v.kind


def test_the_splitter_does_nothing_in_a_small_room() -> None:
    bp = one_room_map("zm_small", bounds=Bounds.between((-200, -200, 0), (200, 200, 256)))
    room = _room(bp)
    placer = ind.RoomPlacer(bp, room)
    assert sp.split_open_floor(bp, room, placer, random.Random(1), ident="sp") == []


def test_a_dressed_room_passes_the_model_checks() -> None:
    from zmforge.verify.model import check_blueprint

    bp, room = _fresh()
    placer = ind.RoomPlacer(bp, room)
    sp.split_open_floor(bp, room, placer, random.Random(1), ident="sp")
    ind.dress_indoor(bp, room, placer, random.Random(2), count=7, ident="hp", gap=200.0)
    placer.flush()
    wd.dress_walls(bp, room, "institution", ident="wd")
    report = check_blueprint(bp)
    assert not report.errors, [(f.code, str(f.message)[:120]) for f in report.errors]


def test_s2_holds_big_rooms_to_forty_percent_of_stock() -> None:
    from zmforge.dressing.scene import BIG_ROOM_SHARE, STOCK
    from zmforge.review.facts import density_floor
    from zmforge.verify.scenes import check_scenes

    bp, _ = _fresh()
    msgs = [str(f.message) for f in _codes(check_scenes(bp), "S2")]
    assert any(f"warn under {STOCK['props_non_trim'] * BIG_ROOM_SHARE:.0f}" in m for m in msgs), msgs
    assert density_floor(1000 * 1000) == 459


