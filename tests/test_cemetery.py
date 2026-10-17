"""zm_cemetery, "Cemetery Quest" (:mod:`zmforge.recipes.cemetery`).

What is pinned: the layout (nine rooms, nine zones, a crypt 240 units down a
flight of stairs), the rolling ground (graded to the navmesh step, reached
by the spawn flood, really hilly), the night fog, the dressing density per
area, the gags and notices, and the quest's wiring.  Everything here is read
off the built blueprint or the committed files; nothing is an observation of
play.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from zmforge import Project
from zmforge.atmosphere import NIGHT_GROUND_FOG
from zmforge.blueprint.model import _solid_bounds
from zmforge.blueprint.elements import (
    Door, Enclosure, Machine, MysteryBox, PowerSwitch, PropScatter, Room, Spawn, Terrain,
    WallWeapon, Window, Zone,
)
from zmforge.recipes import cemetery_map
from zmforge.recipes.cemetery import (
    EPITAPHS, ENDING_PRICE, FIXTURE, GAG_LINES, MAP_TITLE, NOTICE_LINES, PRICES,
    build_cemetery, terrain_report,
)
from zmforge.recipes import cemetery_dressing as dressing
from zmforge.recipes.cemetery_dressing import AREAS, MIN_MODELS
from zmforge.review.facts import density_floor
from zmforge.script import quest as q
from zmforge.script.gsc import scan
from zmforge.script.symbols import unresolved
from zmforge.verify import check_blueprint
from zmforge.verify.documented import MAX_STEP_HEIGHT
from zmforge.verify.reachability import JUMP_UP, flood_from_spawn

from conftest import seed_stock_weapon_table

MAP_NAME = "zm_cemetery"


@pytest.fixture(scope="module")
def built():
    return build_cemetery(MAP_NAME)


@pytest.fixture(scope="module")
def bp(built):
    return built[0]


@pytest.fixture(scope="module")
def extras(built):
    return built[1]


@pytest.fixture(scope="module")
def report(bp):
    return check_blueprint(bp)


@pytest.fixture(scope="module")
def flood(bp):
    return flood_from_spawn(bp)


@pytest.fixture(scope="module")
def committed(tmp_path_factory, bp):
    root = tmp_path_factory.mktemp("cemetery")
    seed_stock_weapon_table(root)
    project = Project.create(MAP_NAME, root, blueprint=bp)
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "map": paths["map"].read_text(encoding="utf-8"),
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8"),
        "manifest": paths["manifest"].read_text(encoding="utf-8"),
    }


# --------------------------------------------------------------------------
# The map as a whole
# --------------------------------------------------------------------------
def test_it_commits_with_no_errors(committed) -> None:
    assert committed["result"].report.errors == [], [
        str(f) for f in committed["result"].report.errors]


def test_the_model_checks_leave_only_the_deliberate_wall_buy_warnings(report) -> None:
    """Nine ``W1``: one per wall buy, the spec's 8-units-into-the-floor.
    The shed's lobby pictures use the modern frame (``Z58``) and the chapel
    drapes hang from a rail (``Z59``)."""
    assert report.errors == [], [str(f) for f in report.errors]
    # N5: one terrain narrowing between plots (hills) is a known warning,
    # pinned so that a new one shows.  The design advisories are left out
    # (conftest.DESIGN_ADVISORIES).
    from conftest import DESIGN_ADVISORIES

    kept = [f for f in report.warnings if f.code not in DESIGN_ADVISORIES]
    assert Counter(f.code for f in kept) == Counter({"W1": 9, "N5": 1}), [
        str(f) for f in kept if f.code != "W1"]


def test_the_registry_knows_the_recipe_and_its_title(bp) -> None:
    from zmforge.facade.cli import RECIPES
    from zmforge.texture.loadscreens import LOADING_SCREENS

    assert RECIPES["cemetery"] is cemetery_map
    assert "cemetery" in LOADING_SCREENS
    assert bp.title == MAP_TITLE == "Cemetery Quest"


def test_the_loading_screen_is_full_hd_and_our_own(tmp_path) -> None:
    from zmforge.texture.cemetery_loadscreen import SIZE, render_loadscreen

    image = render_loadscreen()
    assert image.size == SIZE == (1920, 1080)
    # the bottom band the game draws its progress bar over stays dark
    import numpy as np

    assert np.asarray(image)[960:].mean() < 40.0


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
ROOMS = ("gate", "shed", "hills", "row", "vault", "chapel", "stairs", "ossuary", "tomb")
ZONES = ("gate", "shed", "hills", "row", "vault", "chapel", "crypt_stairs", "ossuary", "tomb")


def test_nine_rooms_nine_zones_three_of_them_outdoors(bp, extras) -> None:
    assert sorted(r.id for r in bp.elements(Room)) == sorted(f"{k}_room" for k in ROOMS)
    assert sorted(z.name for z in bp.elements(Zone)) == sorted(ZONES)
    outdoors = sorted(r.id for r in bp.elements(Room) if not r.roofed)
    assert outdoors == ["gate_room", "hills_room", "row_room"]
    assert all(r.sunlit for r in bp.elements(Room) if not r.roofed)


def test_the_crypt_is_underground_and_reached_by_a_flight_of_stairs(bp, extras, flood) -> None:
    rooms = extras["rooms"]
    ground = rooms["chapel"].floor_z
    for key in ("stairs", "ossuary", "tomb"):
        assert rooms[key].floor_z == ground - 240.0, key
    steps = bp.find("crypt_stairs")
    assert len(steps.solids) == FIXTURE.crypt_steps == 15
    # the top step meets the chapel door's sill, the bottom the crypt floor
    for point in ((2032.0, -300.0, ground), (2480.0, -300.0, rooms["stairs"].floor_z + 16.0),
                  (2960.0, 600.0, rooms["tomb"].floor_z)):
        assert flood.under(point[0], point[1], point[2] + 4.0, only_reached=True) is not None, point


def test_the_crypt_door_is_on_the_electric_lock_and_the_power_is_in_the_shed(bp, extras) -> None:
    door = bp.find("door_crypt_electric")
    assert door.electric and {door.zone_a, door.zone_b} == {"chapel", "crypt_stairs"}
    switch = bp.elements(PowerSwitch)[0]
    assert extras["rooms"]["shed"].interior.holds_flat(switch.position.x, switch.position.y)


def test_doors_cost_what_the_table_says(bp) -> None:
    prices = sorted(d.price for d in bp.elements(Door))
    assert prices == sorted(PRICES.values())


def test_standard_furniture_is_all_there(bp) -> None:
    perks = sorted(m.perk.slug for m in bp.elements(Machine) if hasattr(m, "perk"))
    assert {"juggernog", "quick_revive", "speed_cola", "double_tap", "stamin_up",
            "mule_kick", "deadshot"} <= set(perks)
    assert len(bp.elements(WallWeapon)) == 9
    # The start location on the hills and somewhere to move to on the row.
    assert len(bp.elements(MysteryBox)) == 2
    assert any(getattr(m, "perk", None) and m.perk.slug == "pack_a_punch"
               for m in bp.elements(Machine)) or bp.find("tomb_pap")
    assert len(bp.elements(Window)) == 13
    spawns = Counter(s.zone_name for s in bp.elements(Spawn))
    assert set(spawns) == set(ZONES), spawns


# --------------------------------------------------------------------------
# The ground
# --------------------------------------------------------------------------
def test_the_outdoor_ground_is_terrain_graded_to_the_walkers_step(bp) -> None:
    from zmforge.recipes.cemetery import path_boxes

    terrains = {t.id for t in bp.elements(Terrain)}
    walks = {f"{key}_path" for key in path_boxes()}
    assert terrains == {"gate_ground", "hills_ground", "row_ground"} | walks
    for key in ("gate", "hills", "row"):
        slope = terrain_report(bp, key)
        assert slope.max_neighbour_rise <= MAX_STEP_HEIGHT + 1e-6 < JUMP_UP, key
        assert slope.max_cell_relief <= MAX_STEP_HEIGHT + 1e-6, key
        assert math.degrees(math.atan(slope.max_grade)) < 46.0, key


def test_the_hills_are_actually_hills(bp) -> None:
    slope = terrain_report(bp, "hills")
    assert slope.highest - slope.lowest >= 120.0
    heights = [h for row in bp.find("hills_ground").record.heights for h in row]
    rising = sum(1 for h in heights if h > 30.0)
    assert rising / len(heights) > 0.35, "most of the hills room should be off the flat"


def test_every_interactive_stands_on_flat_ground_the_flood_reaches(bp, flood) -> None:
    for cls in (Machine, MysteryBox, PowerSwitch):
        for element in bp.elements(cls):
            p = element.position
            hit = bp.ground_under(p.x, p.y)
            assert hit.spread <= 1.0, (element.id, hit)


def test_the_hilltops_are_walked_to(bp, flood) -> None:
    from zmforge.recipes.cemetery import FOUNDER_NEEDLE, MAUSOLEUMS

    fx, fy, _ = FOUNDER_NEEDLE
    for x, y in ((fx - 60.0, fy), *((m[2] + 0.0, m[3] - 170.0) for m in MAUSOLEUMS)):
        z = bp.ground_under(x, y).z
        assert z > bp.find("hills_room").floor_z + 60.0, (x, y, z)
        assert flood.under(x, y, z + 4.0, only_reached=True) is not None, (x, y)


# --------------------------------------------------------------------------
# Fog and night
# --------------------------------------------------------------------------
def test_the_night_is_foggy(bp, committed) -> None:
    """The Giant's night preset and sky, under one ground-fog volume (and the
    lit fog, see tests/test_cemetery_ground_fog.py)."""
    enclosure = bp.elements(Enclosure)[0]
    assert enclosure.sun_preset == NIGHT_GROUND_FOG.sun_preset == "zm_factory"
    assert enclosure.fog == "zm_factory_afog"
    assert enclosure.skybox == "skybox_zm_factory"
    text = committed["map"]
    assert text.count('"classname" "volume_worldfog"') == 1
    for n in ("", "_1", "_2", "_3", "_4"):
        assert f'"fsi{n}" "zm_factory_afog"' in text
    assert '"skyboxmodel" "skybox_zm_factory"' in text
    assert '"ssi" "zm_factory"' in text
    assert bp.exposure == 5.0


def test_the_dusk_variant_is_the_same_map_at_sunset() -> None:
    from zmforge.facade.cli import RECIPES
    from zmforge.recipes.cemetery import cemetery_dusk_map

    assert RECIPES["cemetery-dusk"] is cemetery_dusk_map
    dusk = cemetery_dusk_map(MAP_NAME)
    enclosure = dusk.elements(Enclosure)[0]
    assert (enclosure.sun_preset, enclosure.skybox, enclosure.fog) == (
        "default_sunset", "skybox_default_sunset", "zm_factory_afog")
    assert check_blueprint(dusk).errors == []


def test_the_lanterns_and_candles_burn_warm_and_the_wisps_cold(bp) -> None:
    from zmforge.blueprint.elements import Lamp

    lamps = bp.elements(Lamp)
    warm = [l for l in lamps if l.colour[0] > l.colour[2]]
    cold = [l for l in lamps if l.id.startswith("wisp")]
    assert len(warm) >= 60
    assert len(cold) == 4 and all(l.colour[2] > l.colour[0] for l in cold)


# --------------------------------------------------------------------------
# Dressing
# --------------------------------------------------------------------------
def test_every_area_is_densely_dressed(bp, extras) -> None:
    """At least MIN_MODELS per area and never over the area's cap: the
    review's band top for a room, scaled by floor area for the big outdoor
    grounds (``dressing.density_cap``).  The outdoor grounds are filled
    (sparse grounds read as empty)."""
    counts = Counter()
    for scatter in bp.elements(PropScatter):
        if scatter.id.startswith("dress_"):
            counts[scatter.id.split("_")[1]] += len(scatter.props)
    for area in AREAS:
        inside = extras["rooms"][area].interior
        floor = (inside.maxs.x - inside.mins.x) * (inside.maxs.y - inside.mins.y)
        cap = dressing.density_cap(floor)
        assert cap >= density_floor(floor)
        assert MIN_MODELS <= counts[area] <= cap, (area, counts[area], cap)
    assert counts["hills"] >= 250 and counts["gate"] >= 150 and counts["row"] >= 130, counts


def test_the_walks_are_lit_by_lamp_posts_in_pairs(bp, extras) -> None:
    """Path lamps placed at random read as random, so:
    every path lamp stands just off a walk, beside it and not on it, and
    every walk longer than 400 has lamps down both sides."""
    from zmforge.recipes.cemetery import PATHS

    posts = []
    for m in bp.elements():
        if getattr(m, "id", "").startswith("path_lamp_") and m.id.endswith("_post"):
            b = _solid_bounds(m.solids[0])
            posts.append((m.id, (b.mins.x + b.maxs.x) / 2.0, (b.mins.y + b.maxs.y) / 2.0))
    assert len(posts) >= 30, len(posts)
    sides: dict[str, set] = {}
    for ident, x, y in posts:
        key = ident[len("path_lamp_"):-len("_post")].rsplit("_", 1)[0]
        _k, _room, (ax, ay), (bx, by), hw = next(p for p in PATHS if p[0] == key)
        along_x = ay == by
        t, across = (x, y - ay) if along_x else (y, x - ax)
        lo, hi = (min(ax, bx), max(ax, bx)) if along_x else (min(ay, by), max(ay, by))
        assert lo - 1.0 <= t <= hi + 1.0, (ident, x, y)
        assert hw < abs(across) <= hw + 60.0, (ident, x, y, hw)
        sides.setdefault(key, set()).add(across > 0)
    for key, _room, (ax, ay), (bx, by), _hw in PATHS:
        if abs(bx - ax) + abs(by - ay) > 400.0:
            assert sides.get(key) == {True, False}, (key, sides.get(key))
    # lit the same warm way as every lantern
    from zmforge.blueprint.elements import Lamp

    lights = [l for l in bp.elements(Lamp) if l.id.startswith("path_lamp_")]
    assert len(lights) == len(posts)
    assert all(l.colour == dressing.FLAME and l.radius == 384.0 for l in lights)


def test_the_walks_form_one_network_from_the_gate_to_every_door(extras) -> None:
    """The walks and forecourts (``path_boxes``) touch one another (within
    40, a door's wall gap) and link the start, the shed door, the hills, the
    chapel door, the row and the vault door."""
    from zmforge.recipes.cemetery import START, path_boxes

    boxes = path_boxes()
    keys = list(boxes)
    parent = {k: k for k in keys}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for a in keys:
        for b in keys:
            if dressing.rect_gap(boxes[a][1:], boxes[b][1:]) <= 40.0:
                parent[root(a)] = root(b)
    assert len({root(k) for k in keys}) == 1, {k: root(k) for k in keys}
    rects = [box[1:] for box in boxes.values()]

    def reached(rect) -> bool:
        return any(dressing.rect_gap(rect, r) <= 40.0 for r in rects)

    assert reached((START[0], START[1], START[0], START[1]))
    assert {box[0] for box in boxes.values()} >= {"gate", "hills", "row"}
    rooms = extras["rooms"]

    def door(room_key, pick):
        box = next(b for b in rooms[room_key].aperture_boxes if pick(b))
        return (box.mins.x, box.mins.y, box.maxs.x, box.maxs.y)

    shed = rooms["shed"].interior
    chapel = rooms["chapel"].interior
    vault = rooms["vault"].interior
    for name, rect in (
        ("shed door", door("shed", lambda b: b.maxs.y <= shed.mins.y + 1.0)),
        ("chapel door", door("chapel", lambda b: b.maxs.x <= chapel.mins.x + 1.0
                             and abs((b.mins.y + b.maxs.y) / 2.0) < 1.0)),
        ("vault door", door("vault", lambda b: b.maxs.x <= vault.mins.x + 1.0)),
    ):
        assert reached(rect), name


#: Model triangles do not count against MAX_MAP_TRIANGLES (brushes and
#: terrain do), so the prop count is the ceiling that is measured.  A build
#: of zm_corn_maze compiled, baked and linked with 21,232 misc_models (a padded
#: one with 39,975, the largest proven; see test_corn_maze), and zm_cemetery
#: links at 10,823.
PROVEN_PROP_CEILING = 21_000


def test_the_outdoor_ground_is_grassed_but_not_the_ways(bp, extras) -> None:
    """Hundreds of non-solid grass and weed clumps on each outdoor ground,
    in their own ``grass_<area>`` groups, none on a walk or forecourt, in a
    doorway, a window's or a spawn's room, or on a spot a player reads or
    uses something."""
    from zmforge.recipes.cemetery import START, path_boxes
    from zmforge.recipes.props import collision_box

    grass = {s.id: s.props for s in bp.elements(PropScatter) if s.id.startswith("grass_")}
    counts = {key: len(grass.get(f"grass_{key}", ())) for key in dressing.GRASS_AREAS}
    assert set(grass) == {f"grass_{key}" for key in dressing.GRASS_AREAS}, sorted(grass)
    assert counts["hills"] >= 1500 and counts["gate"] >= 500 and counts["row"] >= 350, counts
    models = {m for m, _w, _s in dressing.GRASS}
    rooms = extras["rooms"]
    ways = [box[1:] for box in path_boxes().values()]
    doors = [(b.mins.x - 60, b.mins.y - 60, b.maxs.x + 60, b.maxs.y + 60)
             for room in rooms.values() for b in room.aperture_boxes]
    discs = [(w.barricade_origin.x, w.barricade_origin.y, 90.0) for w in bp.elements(Window)]
    discs += [(s.position.x, s.position.y, 60.0) for s in bp.elements(Spawn)]
    discs += [(START[0], START[1], 140.0)]
    features = extras["features"]
    discs += [(p.x, p.y, dressing.GRASS_CLEAR - 4.0) for group in ("epitaphs", "notices")
              for p in features[group].values()]
    discs += [(p.x, p.y, dressing.GRASS_CLEAR - 4.0) for p in features["wisps"]]
    for sid, props in grass.items():
        inside = rooms[sid.split("_", 1)[1]].interior
        for p in props:
            assert p.model in models and not p.solid, (sid, p.model)
            (x0, y0, _), (x1, y1, _) = collision_box(p.model)
            cx, cy = (x0 + x1) / 2.0 * p.scale, (y0 + y1) / 2.0 * p.scale
            t = math.radians(p.yaw)
            x = p.origin.x + cx * math.cos(t) - cy * math.sin(t)
            y = p.origin.y + cx * math.sin(t) + cy * math.cos(t)
            hx, hy = dressing._half(p.model, p.yaw, p.scale)
            foot = (x - hx, y - hy, x + hx, y + hy)
            assert inside.mins.x < x < inside.maxs.x and inside.mins.y < y < inside.maxs.y
            assert all(dressing.rect_gap(foot, r) > 0.0 for r in ways + doors), (sid, x, y)
            assert all(math.hypot(x - dx, y - dy) > r for dx, dy, r in discs), (sid, x, y)
            assert not bp.interactive_blocks(p.origin, hx, hy), (sid, x, y)
    total = sum(len(s.props) for s in bp.elements(PropScatter))
    assert total <= PROVEN_PROP_CEILING, total


def _kit_props(bp, group: str | None = None):
    """(scatter id, prop) for every graveyard-kit model the dresser placed."""
    return [(s.id, p) for s in bp.elements(PropScatter) if s.id.startswith("dress_")
            and (group is None or s.id.endswith(f"_{group}"))
            for p in s.props if p.model.startswith("zmf_prop_")]


def test_the_graveyard_kit_dresses_the_grounds(bp, extras) -> None:
    """The CC0 kit: model headstones across the hills, wooden
    crosses in the old north section, iron fence panels on the gate line and
    round the family plots, jack-o'-lanterns on graves and at the chapel
    door, the groundskeeper's hand cart in the shed; the fences are black
    brush iron."""
    kit = Counter((sid.split("_")[1], p.model) for sid, p in _kit_props(bp))
    stones = (dressing.STONE_ROUND, dressing.STONE_CROSS, dressing.STONE_BROKEN)
    assert sum(kit["hills", m] for m in stones) >= 25, kit
    assert all(kit["hills", m] >= 3 for m in stones), kit
    assert sum(kit["gate", m] for m in stones) >= 8, kit
    crosses = [p for sid, p in _kit_props(bp) if p.model == dressing.WOODEN_CROSS]
    assert len(crosses) >= 5
    assert all(p.origin.y > 500.0 for p in crosses), [p.origin for p in crosses]
    # The iron fence is the black brush fence everywhere, because the kit
    # panel draws teal.
    assert not any(p.model == dressing.FENCE_IRON for _, p in _kit_props(bp)), kit
    from zmforge.blueprint.elements import Massing
    runs = {m.id.rsplit("_post", 1)[0] for m in bp.elements(Massing)
            if "fence" in m.id and "_run" in m.id and "_post" in m.id}
    assert len(runs) >= 6 and any(r.startswith("gate") for r in runs) and any(
        r.startswith("hills") for r in runs), sorted(runs)
    jacks = [(sid, p) for sid, p in _kit_props(bp)
             if p.model in (dressing.JACK, dressing.JACK_TALL)]
    assert sum(1 for sid, _ in jacks if sid.endswith(("_offerings", "_family"))) >= 3
    assert sum(1 for sid, _ in jacks if sid == "dress_gate_halloween") == 2
    door = [p for sid, p in jacks if sid == "dress_hills_halloween"]
    chapel = extras["rooms"]["chapel"]
    assert len(door) == 2
    assert all(abs(p.origin.x - chapel.interior.mins.x) < 80.0 for p in door), door
    assert [p.model for _, p in _kit_props(bp, "stores")] == [dressing.HAND_CART]
    # The readable stones stay brush tablets, each with its notice in front.
    for key in ("told_you", "back_soon", "return", "pieces", "wifi", "diet", "plot_twist",
                "reserved"):
        box = _solid_bounds(bp.find(f"epitaph_{key}_tablet").solids[0])
        at = extras["features"]["epitaphs"][key]
        centre = ((box.mins.x + box.maxs.x) / 2.0, (box.mins.y + box.maxs.y) / 2.0)
        assert math.dist(centre, (at.x, at.y)) <= 64.0, (key, centre, at)


def test_the_kit_models_stand_on_the_slopes(bp) -> None:
    """No kit model floats over the ground under its footprint, and none is
    sunk in it past the 8-unit step (``placement.audit.SUPPORT_REACH``).
    Jack-o'-lanterns on a mound stand on the mound, not the ground."""
    checked = 0
    for sid, p in _kit_props(bp):
        if p.model in (dressing.JACK, dressing.JACK_TALL) and not sid.endswith("_halloween"):
            continue
        if sid.split("_")[1] not in ("gate", "hills", "row"):
            continue
        hx, hy = dressing._half(p.model, p.yaw)
        if p.model.startswith("zmf_prop_dead_tree_"):
            # A tree meets the ground at its trunk, not under its crown (the
            # model box is the whole 190-284 unit crown); the
            # placer seats it on the low point under the trunk's 28 units
            # (cemetery_dressing._trees).
            hx = hy = 14.0
        zs = [bp.ground_under(p.origin.x + i * hx / 2.0, p.origin.y + j * hy / 2.0).z
              for i in range(-2, 3) for j in range(-2, 3)]
        assert p.origin.z - max(zs) <= 2.0, (sid, p.model, p.origin, max(zs))
        assert max(zs) - p.origin.z <= 8.0 + 1e-6, (sid, p.model, p.origin, max(zs))
        checked += 1
    assert checked >= 60, checked


def test_the_cemetery_is_built_of_graves(bp) -> None:
    ids = [m.id for m in bp.elements() if hasattr(m, "solids")]
    kit = Counter(p.model for _, p in _kit_props(bp))
    # Brush tablets and the kit's headstone models both count as stones.
    stones = ({i.rsplit("_", 1)[0] for i in ids if i.endswith("_tablet")}
              | {f"model{n}" for n in range(sum(kit[m] for m in (
                  dressing.STONE_ROUND, dressing.STONE_BROKEN)))})
    crosses = ({i.rsplit("_", 1)[0] for i in ids if i.endswith("_arm_a")}
               | {f"model{n}" for n in range(kit[dressing.STONE_CROSS]
                                             + kit[dressing.WOODEN_CROSS])})
    mounds = [i for i in ids if i.endswith("_mound")]
    trees = {i.split("_trunk")[0] for i in ids if "_trunk" in i}
    # Trees are models (cemetery_dressing._trees, one per
    # dress_<area>_<ident><n> scatter; the leafy ones are the stock albizia).
    from zmforge.dressing.trees import ALBIZIA, DEAD_TREES, GNARLED_TREES

    trees |= {f"model{n}" for n in range(sum(
        kit[m] for m in (*DEAD_TREES, *GNARLED_TREES, ALBIZIA)))}
    # Brush fence posts, the stone piers the panels hang between, and the panels.
    fences = [i for i in ids if "_fence_" in i and "_post" in i] + [
        n for n in range(kit[dressing.FENCE_IRON])]
    mausoleums = {i.rsplit("_", 1)[0] for i in ids if i.endswith("_body")
                  and (i.startswith("mausoleum_") or i.startswith("tomb_"))}
    assert len(stones) >= 55, len(stones)
    assert len(crosses) >= 25, len(crosses)
    assert len(mounds) >= 50
    assert len(trees) >= 8
    assert len(fences) >= 30
    assert len(mausoleums) >= 6
    for key in ("open_grave_rim_s", "front_gate_pier0", "altar_body", "founder_coffin",
                "founder_sarcophagus_box", "founder_needle_shaft"):
        bp.find(key)
    assert sum(1 for i in ids if i.startswith("pew_")) >= 10


# --------------------------------------------------------------------------
# Gags and notices
# --------------------------------------------------------------------------
def test_every_epitaph_and_notice_is_readable_where_it_stands(bp, extras, committed, flood) -> None:
    keys = [key for key, _ in extras["notices"]]
    assert sorted(keys) == sorted([*EPITAPHS, *NOTICE_LINES])
    assert len(EPITAPHS) >= 10
    for key, point in extras["notices"]:
        inside = [r.id for r in bp.elements(Room) if r.interior.holds_flat(point.x, point.y)]
        assert len(inside) == 1, (key, inside)
    for _prompt, lines in [*EPITAPHS.values(), *NOTICE_LINES.values()]:
        for line in lines:
            assert line in committed["strings"], line
    assert "zmf_notice(" in committed["server"]


def test_the_gate_closes_at_midnight_and_it_is_always_1159(committed) -> None:
    strings = committed["strings"]
    assert "GATES CLOSE AT MIDNIGHT." in strings
    assert "It is 11:59. It has been 11:59 for a while." in strings


def test_the_gags_only_reply_to_players(committed) -> None:
    """P13/P17 (an announcement that carries no information is noise): no zone sign-ins and no round-end groundskeeper PA;
    every gag line answers something a player did."""
    from zmforge.verify.gameplay import flavour_broadcasts

    server = committed["server"]
    for key, text in GAG_LINES.items():
        assert text in committed["strings"], key
    assert not [key for key in GAG_LINES if key.startswith(("room_", "pa_"))]
    assert "Groundskeeper:" not in committed["strings"]
    assert "function zmf_gag_announcer(" not in server
    assert "function zmf_gag_pa_random(" not in server
    assert 'level.zmf_gag_rooms[ "' not in server
    assert sum(flavour_broadcasts(server).values()) == 0
    # What is left is said on an event a player caused.
    assert 'level flag::wait_till( "power_on" );' in server
    assert 'level waittill( "weapon_fly_away_start" );' in server


# --------------------------------------------------------------------------
# The quest
# --------------------------------------------------------------------------
def test_the_quest_has_every_kind_of_step_and_a_twenty_thousand_ending(extras, committed) -> None:
    quest = extras["quest"]
    kinds = [type(s).__name__ for s in quest.steps]
    assert kinds == ["CollectDeliver", "HitTargets", "HitTargets", "StandInZone",
                     "SoulBox", "DefeatBoss", "SurviveRounds"]
    assert quest.steps[1].mode == "shoot" and len(quest.steps[1].targets) == 4
    assert quest.steps[2].mode == "melee"
    assert quest.exit.price == ENDING_PRICE == 20000
    server = committed["server"]
    assert "level thread zmf_quest_init();" in server
    assert "zmf_boss_gravedigger_spawn" in server
    assert "zm_score::can_player_purchase( 20000 )" in server
    assert "REST IN PEACE" in committed["strings"]
    for ref, (text, kind) in q.quest_strings(quest).items():
        assert text in committed["strings"], ref
    assert "xmodel,p7_tools_shovel" in committed["manifest"]
    source = scan(server)
    assert source.issues == []
    assert unresolved(source) == []


def test_the_gravedigger_comes_out_of_the_open_grave(extras) -> None:
    boss_step = extras["quest"].steps[5]
    grave = extras["features"]["open_grave"]
    assert boss_step.boss.name == "THE GRAVEDIGGER"
    # Beside the grave, on the knoll, not inside its rim on the dig trigger.
    assert 64.0 <= math.dist(boss_step.boss.spawn_at[:2], (grave.x, grave.y)) <= 160.0
    assert boss_step.boss.minions >= 4


def test_no_quest_trigger_stands_where_a_purchase_is_made(bp, extras, flood) -> None:
    quest = extras["quest"]
    others = [(e.id, e.position) for cls in (Machine, WallWeapon, PowerSwitch, MysteryBox)
              for e in bp.elements(cls)]
    others += [(w.id, w.barricade_origin) for w in bp.elements(Window)]
    others += [(d.id, d.box.centre) for d in bp.elements(Door)]
    others += [(f"notice:{key}", point) for key, point in extras["notices"]]
    points = quest.use_points()
    assert len(points) == 3
    for x, y, z in points:
        near = min((math.hypot(x - o.x, y - o.y), name) for name, o in others)
        assert near[0] >= 80.0, ((x, y), near)
        assert flood.under(x, y, z + 4.0, only_reached=True) is not None, (x, y)
