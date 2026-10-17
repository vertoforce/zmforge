"""zmforge render --hero: the hero camera registry, the dry path and hero.png carry-forward.

No Radiant: every camera here is resolved from a built blueprint only.
"""

from __future__ import annotations

import json
from functools import lru_cache

import pytest

from zmforge.render import cameras, hero
from zmforge.render.cameras import View


@lru_cache(maxsize=None)
def _bp(recipe: str):
    from zmforge.review.facts import build_blueprint

    return build_blueprint(recipe)[0]


def _area(bp, key):
    from zmforge.review.facts import _areas

    return next(a for a in _areas(bp) if a.key == key)


@pytest.mark.parametrize("recipe", ["dmv", "cemetery", "corn_maze", "one-room"])
def test_hero_view_is_at_eye_level_inside_its_room(recipe):
    bp = _bp(recipe)
    view = hero.hero_view(recipe, bp)
    assert isinstance(view, View) and view.name == "hero"
    spec = hero.spec_for(recipe)
    if spec is not None:
        assert view.room == _area(bp, spec.room).key
    area = _area(bp, view.room)
    assert area.x0 < view.x < area.x1 and area.y0 < view.y < area.y1
    ground = bp.ground_under(view.x, view.y, below=view.z).z
    assert view.z - ground == pytest.approx(cameras.EYE, abs=1.0)
    assert -35.0 <= view.pitch <= 35.0 and 0.0 <= view.yaw < 360.0


def test_hero_camera_faces_its_target():
    bp = _bp("corn_maze")
    view = hero.hero_view("corn_maze", bp)
    tx, ty, tz = hero.feature_point(bp, hero.HEROES["corn_maze"].target)
    assert view.yaw == pytest.approx(cameras._yaw(view.x, view.y, tx, ty), abs=0.2)
    assert view.pitch < 0        # the water tower stands over the corn: look up at it


def test_dry_run_lists_the_hero_camera(tmp_path):
    from zmforge.render.run import render_recipe

    manifest = render_recipe("one-room", out=tmp_path / "run", dry=True, hero=True)
    assert manifest["views"] == []                   # --hero shoots nothing else
    assert manifest["settings"]["width"] == hero.HERO_WIDTH
    assert View(**manifest["hero"]["view"]).name == "hero"
    assert manifest["hero"]["hash"]


def test_hero_png_carries_forward_only_while_its_room_is_unchanged(tmp_path):
    from zmforge.render.run import _carry_hero, _hero_entry

    bp = _bp("one-room")
    map_text = '{\n"classname" "worldspawn"\n}\n'
    settings = {"width": hero.HERO_WIDTH, "lighting": "fake", "version": 2}
    entry = _hero_entry("one-room", bp, map_text, settings)
    before = tmp_path / "before"
    before.mkdir()
    (before / hero.HERO_FILE).write_bytes(b"png")
    entry["path"] = str(before / hero.HERO_FILE)
    (before / "views.json").write_text(json.dumps({"hero": entry}))

    same = tmp_path / "same"
    same.mkdir()
    kept = _carry_hero(before, same, "one-room", bp, map_text, lambda s: None)
    assert kept and kept["path"] == str(same / hero.HERO_FILE)
    assert (same / hero.HERO_FILE).read_bytes() == b"png"

    # A brush inside the hero room changes its hash: the old picture is stale.
    view = View(**entry["view"])
    moved = map_text + (
        "{\n( %d %d 0 ) ( %d %d 0 ) ( %d %d 0 ) caulk 0 0 0 1 1 0 0 0\n}\n"
        % (view.x, view.y, view.x + 8, view.y, view.x, view.y + 8))
    stale = tmp_path / "stale"
    stale.mkdir()
    assert _carry_hero(before, stale, "one-room", bp, moved, lambda s: None) is None
    assert not (stale / hero.HERO_FILE).exists()
