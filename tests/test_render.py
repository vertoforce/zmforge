"""zmforge render: camera placement, Radiant filter prefs, the CLI, the visual review call."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from zmforge.render import cameras
from zmforge.render.cameras import View, corner_views, doorway_views, room_views
from zmforge.render.radiant import hide_helpers


def _area(x0=0.0, y0=0.0, x1=400.0, y1=200.0, floor=16.0, ceiling=208.0, key="queue"):
    return SimpleNamespace(key=key, room_id=f"{key}_room", x0=x0, y0=y0, x1=x1, y1=y1,
                           floor_z=floor, ceiling_z=ceiling)


def _inside(area, v: View) -> bool:
    return (area.x0 < v.x < area.x1 and area.y0 < v.y < area.y1
            and area.floor_z < v.z < area.ceiling_z)


def test_doorway_view_stands_inside_at_eye_height_facing_the_room():
    area = _area()
    # A doorway in the west wall, centred at y=100.
    (view,) = doorway_views(area, [("d1", (-8.0, 76.0, 8.0, 124.0), {})])
    assert _inside(area, view)
    assert view.z == area.floor_z + cameras.EYE
    assert view.x == cameras.DOOR_STEP          # stepped in from x=0
    assert view.name.endswith("-w")
    # Facing east, into the room (the middle is dead ahead).
    assert view.yaw == pytest.approx(0.0, abs=0.5)
    assert view.pitch > 0                        # a little down


def test_doorway_on_north_wall_faces_south():
    area = _area()
    (view,) = doorway_views(area, [("d2", (180.0, 192.0, 220.0, 208.0), {})])
    assert _inside(area, view)
    assert view.yaw == pytest.approx(270.0, abs=0.5)


def test_low_ceiling_keeps_the_eye_under_it():
    area = _area(ceiling=60.0)
    (view,) = doorway_views(area, [("d", (-8.0, 90.0, 8.0, 110.0), {})])
    assert view.z == 60.0 - cameras.CEILING_CLEAR


def test_corner_views_look_down_across_the_room():
    area = _area()
    sw, ne = corner_views(area)
    for v in (sw, ne):
        assert _inside(area, v)
        assert v.z == area.ceiling_z - cameras.CEILING_CLEAR
        assert 0 < v.pitch < 90
    assert 0 < sw.yaw < 90 and 180 < ne.yaw < 270


def test_room_views_limit_and_order():
    area = _area()
    doors = [("a", (-8.0, 90.0, 8.0, 110.0), {}), ("b", (392.0, 90.0, 408.0, 110.0), {})]
    assert [v.name for v in room_views(area, doors)] == [
        "corner-sw", "corner-ne", "door0-w", "door1-e"]
    assert len(room_views(area, doors, limit=3)) == 3


def test_radiant_text_and_slug():
    v = View("records (x)", "door0-w", 10.4, -20.0, 76.0, 8.0, 90.0)
    assert v.radiant_text() == "10 -20 76 8.0 90.0"
    assert v.slug == "records__x_--door0-w"


def test_hide_helpers_turns_off_editor_only_groups():
    reg = (
        '[Software\\\\Treyarch\\\\Radiant\\\\Filters\\\\Groups\\\\Geometry] 1\n'
        '"Caulk"="true"\n"World"="true"\n'
        '[Software\\\\Treyarch\\\\Radiant\\\\Filters\\\\Groups\\\\Triggers] 1\n'
        '"Kill"="true"\n'
        '[Software\\\\Treyarch\\\\Radiant\\\\Other] 1\n"Caulk"="true"\n'
    )
    out = hide_helpers(reg + '"Filter_ShowGameView"="false"\n')
    assert '"Filter_ShowGameView"="true"' in out          # no entity boxes, no light bulbs
    assert '"Caulk"="false"\n"World"="true"' in out     # geometry kept, caulk hidden
    assert '"Kill"="false"' in out                      # every trigger hidden
    assert '[Software\\\\Treyarch\\\\Radiant\\\\Other] 1\n"Caulk"="true"\n' in out


def test_plan_views_on_a_real_recipe():
    from zmforge.review.facts import build_blueprint

    bp, _, _ = build_blueprint("one-room")
    views = cameras.plan_views(bp, limit=3)
    assert views and all(isinstance(v, View) for v in views)
    assert len({v.slug for v in views}) == len(views)


def test_visual_review_sends_images_as_stream_json(tmp_path, review_runner):
    png = tmp_path / "queue--corner-sw.png"
    png.write_bytes(b"\x89PNG fake")
    stub = tmp_path / "claude"
    seen = tmp_path / "seen"
    result = {"type": "result", "subtype": "success", "is_error": False,
              "structured_output": {"grade": "B"}, "total_cost_usd": 0.01}
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$@" > {seen}.argv\ncat > {seen}.stdin\n'
        "echo '{\"type\":\"system\"}'\n"
        f"echo '{json.dumps(result)}'\n")
    stub.chmod(0o755)
    cli = review_runner.ClaudeCLI(binary=str(stub))
    review, meta = cli("judge this room", {"type": "object"}, images=[png])
    assert review == {"grade": "B"} and meta["total_cost_usd"] == 0.01
    argv = (tmp_path / "seen.argv").read_text()
    assert "--input-format stream-json" in argv and "--output-format stream-json" in argv
    message = json.loads((tmp_path / "seen.stdin").read_text())
    kinds = [block["type"] for block in message["message"]["content"]]
    assert kinds == ["image", "text"]


def test_room_prompt_asks_for_p15_only_with_images():
    from zmforge.review import ai

    plain = ai.room_prompt([], {"room": "queue"}, "", map_name="zm_x", thresholds={})
    visual = ai.room_prompt([], {"room": "queue"}, "", map_name="zm_x", thresholds={},
                            images=["queue--corner-sw.png"])
    assert "RENDERED VIEWS" not in plain
    assert "RENDERED VIEWS" in visual and "queue--corner-sw.png" in visual
    assert "P15" in visual and "doesnt_make_sense" in visual


def _radiant_ready() -> bool:
    if os.environ.get("ZMFORGE_RENDER_TEST") != "1" or not shutil.which("nvidia-smi"):
        return False
    return subprocess.run(["docker", "image", "inspect", "zmforge-radiant-render:local"],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _radiant_ready(),
                    reason="needs the GPU, the render image and ZMFORGE_RENDER_TEST=1 "
                           "(starts Radiant, several minutes)")
def test_render_one_room_in_radiant(tmp_path):
    from zmforge.render.run import render_recipe

    manifest = render_recipe("one-room", views=1, out=tmp_path)
    shots = [Path(p) for paths in manifest["shots"].values() for p in paths]
    assert shots and all(p.stat().st_size > 10_000 for p in shots)


def test_goto_types_negative_coordinates_safely():
    """xdotool reads a leading '-' as an option unless the text follows '--'."""
    from zmforge.render.radiant import RadiantCamera

    scripts: list[str] = []

    def fake_sh(script, timeout=120.0, check=False):
        scripts.append(script)
        return "123\n" if "search" in script else ""

    cam = RadiantCamera(Path("zm_x.map"), container="none")
    cam.sh = fake_sh  # type: ignore[method-assign]
    cam.goto(View("queue", "corner-ne", -726, 474, 260, 21.0, 244.4))
    typed = next(s for s in scripts if "xdotool type" in s)
    assert "type --delay 12 -- '-726 474 260 -21.0 244.4'" in typed   # pitch flipped: up is +


def test_camera_inside_a_prop_moves_toward_the_middle_and_keeps_its_aim():
    area = _area()
    sw, _ne = corner_views(area)
    stalk = (0.0, 0.0, 40.0, 40.0, area.floor_z, area.ceiling_z)   # corn in the corner
    moved = cameras.clear_of_props(sw, area, [stalk])
    assert (moved.x, moved.y) != (sw.x, sw.y) and moved.z == sw.z
    assert not cameras._inside(moved.x, moved.y, moved.z, stalk)
    assert abs(moved.yaw - sw.yaw) < 15                       # still looks across the room
    assert cameras.clear_of_props(sw, area, [(300, 150, 320, 170, 0, 50)]) == sw


def test_plan_views_on_the_corn_maze_stand_clear_of_the_corn():
    from zmforge.review.facts import _areas, _props, build_blueprint

    bp, _, _ = build_blueprint("corn_maze")
    areas = _areas(bp)
    boxes = [(*p.bounds, p.z_low, p.z_high) for p in _props(bp, areas)
             if p.bounds and p.z_low is not None and p.z_high is not None]
    views = [v for v in cameras.plan_views(bp, rooms=["heart", "mazeentry"], limit=3)]
    assert views
    stuck = [v.slug for v in views if any(cameras._inside(v.x, v.y, v.z, b) for b in boxes)]
    assert not stuck, stuck


def _serpentine():
    """A 768-square room of three east-west corridors about 100 wide between two
    224-thick walls (corn), each wall open at one end: a maze in miniature."""
    area = _area(0.0, 0.0, 768.0, 768.0, floor=0.0, ceiling=400.0, key="rows")
    walls = [(0.0, 112.0, 640.0, 336.0, 0.0, 200.0),      # open at the east end
             (128.0, 432.0, 768.0, 656.0, 0.0, 200.0)]    # open at the west end
    return area, walls


def test_a_maze_room_gets_path_views_standing_in_the_corridors():
    """WHY: corner views of a maze room stand in the corn
    and show no path; a maze room is seen from its
    paths, looking along them."""
    area, walls = _serpentine()
    free = cameras.FreeMap(area, 90.0, walls)
    assert free.share < cameras.MAZE_FREE_SHARE
    views = room_views(area, [], solids=walls)
    names = [v.name for v in views]
    assert names[:2] == ["path0", "path1"] and not any(n.startswith("corner") for n in names)
    for v in views[:2]:
        assert free.at(v.x, v.y), v                        # in a corridor, not in a wall
        assert v.yaw in (0.0, 90.0, 180.0, 270.0)          # looking along it
        ahead = (v.x + 300.0 * math.cos(math.radians(v.yaw)), v.y + 300.0 * math.sin(math.radians(v.yaw)))
        assert free.sees(v.x, v.y, *ahead), v              # and the corridor runs on
    assert math.hypot(views[0].x - views[1].x, views[0].y - views[1].y) >= cameras.VIEW_SPREAD


def test_a_declared_set_piece_gets_a_view_that_sees_it():
    area, walls = _serpentine()
    wreck = (600.0, 384.0, 40.0)                            # in the middle corridor
    views = room_views(area, [], solids=walls, focus=[wreck])
    assert views[0].name == "focus0"
    v = views[0]
    free = cameras.FreeMap(area, 90.0, walls)
    assert free.sees(v.x, v.y, wreck[0], wreck[1], stop_short=cameras.FOCUS_NEAR * 0.75)
    aim = math.degrees(math.atan2(wreck[1] - v.y, wreck[0] - v.x)) % 360.0
    assert abs((v.yaw - aim + 180.0) % 360.0 - 180.0) < 1.0
    # An open room keeps its corners after the set piece.
    open_views = room_views(_area(), [], focus=[(200.0, 100.0, 40.0)])
    assert [x.name for x in open_views][:3] == ["focus0", "corner-sw", "corner-ne"]


def test_the_corn_maze_rooms_are_seen_from_their_paths_and_set_pieces():
    from zmforge.dressing.scene import scenes_of
    from zmforge.review.facts import build_blueprint

    bp, _, _ = build_blueprint("corn_maze")
    assert sum(len(s.focus) for s in scenes_of(bp)) >= 8        # every set piece and clearing
    views = cameras.plan_views(bp, rooms=["maze_entry_room", "maze_north_room"], limit=3)
    for room in ("mazeentry", "mazenorth"):
        names = [v.name for v in views if v.room == room]
        assert names and names[0] == "focus0" and not any(n.startswith("corner") for n in names), names
