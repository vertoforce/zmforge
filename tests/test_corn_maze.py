"""zm_corn_maze, "Harvest Moon": the layout, the maze, the hayride, the dressing,
the gags and the quest, pinned.

Every fixture is module-scoped: the blueprint, its check report, the flood
from the spawn and one commit are each built once.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import deque
from pathlib import Path

import pytest

from zmforge import Project
from zmforge.blueprint.elements import Door, Machine, Massing, PropScatter, Room, Spawn, WallWeapon, Window
from zmforge.recipes import corn_maze as cm
from zmforge.recipes import corn_maze_parts as parts
from zmforge.recipes import corn_maze_script as cs
from zmforge.recipes.corn_maze import FIXTURE, MAZE_ROOMS, ZONES, corn_maze_map, hayride_route
from zmforge.recipes.props import MODEL_BOX
from zmforge.script import quest as q
from zmforge.script.hayride import route_length
from zmforge.texture.corn_maze_loadscreen import SIZE, loadscreen_png, render_loadscreen
from zmforge.texture.loadscreens import loading_screen_for
from zmforge.verify import check_blueprint
from zmforge.verify.reachability import JUMP_UP, flood_from_spawn

from conftest import seed_stock_weapon_table

MAP_NAME = "zm_corn_maze"


@pytest.fixture(scope="module")
def built():
    return corn_maze_map(MAP_NAME)


@pytest.fixture(scope="module")
def report(built):
    return check_blueprint(built)


@pytest.fixture(scope="module")
def flood(built):
    return flood_from_spawn(built)


@pytest.fixture(scope="module")
def rooms(built):
    return {room.id: room for room in built.elements(Room)}


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("tools_root")
    seed_stock_weapon_table(root)
    project = Project.create(MAP_NAME, root, blueprint=corn_maze_map(MAP_NAME))
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "map": paths["map"].read_text(encoding="utf-8"),
        "manifest": paths["manifest"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8")
        if "localized_strings" in paths else "",
    }


# --------------------------------------------------------------------------
# The map as a whole
# --------------------------------------------------------------------------
def test_it_commits_with_no_errors(committed) -> None:
    assert committed["result"].report.errors == [], [str(f) for f in committed["result"].report.errors]


def test_the_model_checks_pass_with_only_the_deliberate_wall_buy_warnings(report) -> None:
    """Six W1s, one per wall buy: the spec's 8-units-below-the-floor origin.
    And two Z58s from props/notes.json: the barn's hanging shirt and trousers
    are measured not to draw in the editor render (whether they draw in game
    is not measured), so a render review of the barn will not show them."""
    assert report.errors == [], [str(f) for f in report.errors]
    # The design advisories (S1-S6, D*, Z74-Z77: conftest.DESIGN_ADVISORIES)
    # are left out.  N5 x2: two maze passages narrowed to 84 by the corn
    # lining over 192 units, under Treyarch's 96 hallway standard; these are
    # known warnings, pinned so that a new one shows.
    from conftest import DESIGN_ADVISORIES

    # Z44 findings are layout warnings here as on any map (stalks half on
    # the maze vignettes' picnic blankets, bottles off their crate); they
    # are pinned only to stay warnings.
    assert all(not f.is_error for f in report.findings if f.code == "Z44")
    codes = sorted(f.code for f in report.warnings
                   if f.code not in DESIGN_ADVISORIES and f.code != "Z44")
    # N5 x3: the third is the farmyard corner by the barn, where a lamp
    # barrel and the density pass's pumpkins leave a 62-unit gap for 92 units.
    # The farmyard is open on every other side, so walkers go round (N2).
    assert codes == ["N5"] * 3 + ["W1"] * 6 + ["Z58"] * 2, [str(f) for f in report.warnings]
    z58 = " ".join(str(f) for f in report.warnings if f.code == "Z58")
    assert "p7_clothes_hanging_01_tshirt" in z58 and "p7_clothes_hanging_01_pants" in z58


def test_it_is_registered_under_the_name_the_build_uses() -> None:
    from zmforge.facade.cli import RECIPES

    assert RECIPES["corn_maze"] is corn_maze_map


def test_the_seven_zones_are_the_ones_the_docstring_draws(built) -> None:
    zones = sorted({z.name for z in built.elements() if type(z).__name__ == "Zone"})
    assert zones == sorted(ZONES)


def test_every_zone_but_the_start_has_a_door_and_every_zone_has_risers(built) -> None:
    doors = built.elements(Door)
    spawns = built.elements(Spawn)
    for zone in ZONES:
        assert sum(1 for s in spawns if s.zone_name == zone) >= 2, zone
        if zone != "farmyard":
            assert any(d.zone_b == zone for d in doors), zone
    assert {d.price for d in doors} <= {750, 1000, 1250, 1500, 1750}
    assert [d.id for d in doors if d.electric] == ["door_barn"]


def test_the_furniture_a_zombies_map_needs_is_all_here(built) -> None:
    perks = sorted(m.perk.slug for m in built.elements(Machine))
    assert perks == sorted(["quick_revive", "speed_cola", "juggernog", "stamin_up", "double_tap",
                            "mule_kick", "pack_a_punch", "gobblegum", "gobblegum"])
    assert len(built.elements(WallWeapon)) == 6
    kinds = {type(e).__name__ for e in built.elements()}
    assert {"MysteryBox", "PowerSwitch", "PlayerStart", "Window", "Enclosure"} <= kinds


def test_every_zone_with_a_free_outside_wall_has_a_barrier(built) -> None:
    """Six zones have a wall with only the dark behind it and no door in it;
    each has a window.  The farmyard's four walls all carry a door or a
    gate (see corn_maze_parts)."""
    windows = {w.zone_name for w in built.elements() if type(w).__name__ == "Window"}
    # The heart is the middle of the maze: all four of its walls are
    # maze corn, so its zombies climb out of its risers.
    assert windows == set(ZONES) - {"farmyard", "heart"}, windows


def test_no_hay_stands_where_a_zombie_climbs_out(built) -> None:
    bales = [p for s in built.elements(PropScatter) for p in s.props
             if p.model in (parts.HAY_BALE, parts.HAY_STACK)]
    for spawn in built.elements(Spawn):
        for bale in bales:
            gap = math.dist((bale.origin.x, bale.origin.y), (spawn.position.x, spawn.position.y))
            assert gap > 100.0, (spawn.id, bale.id, gap)


def test_the_power_line_says_what_the_power_does(committed) -> None:
    """The barn door is electric: the stock door opens itself, free, when the
    power comes on, and the line says exactly that."""
    assert "The barn's electric doors swung open by themselves. No charge." in committed["strings"]
    assert "generator" not in committed["strings"].lower()


def test_it_is_a_night_map(built) -> None:
    enclosure = next(e for e in built.elements() if type(e).__name__ == "Enclosure")
    # The Giant's night preset and its real night sky, not the plain black one.
    assert enclosure.sun_preset == "zm_factory"
    assert enclosure.skybox == "skybox_zm_factory"


def test_pack_a_punch_is_up_in_the_hayloft(built, rooms, flood) -> None:
    pap = next(m for m in built.elements(Machine) if m.perk.slug == "pack_a_punch")
    barn = rooms["barn_room"]
    assert pap.position.z == pytest.approx(barn.floor_z + FIXTURE.loft_height)
    assert flood.under(pap.position.x, pap.position.y + 60.0, pap.position.z + 4.0,
                       only_reached=True) is not None


# --------------------------------------------------------------------------
# The corn and the maze
# --------------------------------------------------------------------------
#: v2 is about 30,800 props; a 39,975-prop build compiled, baked and linked
#: (the prop-ceiling probe), but frame rate is unmeasured, so the cap is
#: 32,000.
PROP_CEILING_V2 = 32000
MAZE_ROOM_IDS = tuple(f"maze_{key[4:]}_room" for key in MAZE_ROOMS)


def test_the_corn_is_taller_than_anybody_can_jump(rooms) -> None:
    for key in ("farmyard_room", "patch_room", "heart_room", *MAZE_ROOM_IDS):
        room = rooms[key]
        assert not room.roofed
        assert room.outer.maxs.z - room.floor_z > 3 * JUMP_UP, key


def test_every_maze_corn_wall_is_full_height_and_declared_unclimbable(built, rooms) -> None:
    corn = [e for e in built.elements(Massing) if "_corn_" in e.id and e.id.startswith("maze")]
    assert len(corn) > 80
    assert all(not element.reachable for element in corn)
    for key in MAZE_ROOMS:
        room = rooms[f"maze_{key[4:]}_room"]
        boxes = cm.maze_boxes(FIXTURE, key, room.interior, room.floor_z)
        assert len(boxes) == sum(1 for e in corn if e.id.startswith(f"{key}_corn_"))
        for box in boxes:
            assert box.maxs.z - room.floor_z == FIXTURE.corn_height
            # Every box stays inside its room and overlaps no other.
            assert room.interior.mins.x <= box.mins.x and box.maxs.x <= room.interior.maxs.x
            assert room.interior.mins.y <= box.mins.y and box.maxs.y <= room.interior.maxs.y
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not (a.mins.x < b.maxs.x - 0.01 and b.mins.x < a.maxs.x - 0.01
                            and a.mins.y < b.maxs.y - 0.01 and b.mins.y < a.maxs.y - 0.01), (key, a, b)


def test_it_is_a_big_real_maze_with_the_heart_in_the_middle() -> None:
    """v2: 17 x 17 cells round a 5 x 5
    heart, 264 maze cells, every one reachable from the gate, the heart's
    gate a long walk in, dead ends and loops, and the zones meeting only at
    their bought gates."""
    cells = cm.maze_cells_all()
    assert FIXTURE.maze_size == 17 and len(cells) == 264
    i0, j0, i1, j1 = cm.HEART_CELLS
    assert (i0 + i1) / 2 == FIXTURE.maze_size / 2 and (j0 + j1) / 2 == FIXTURE.maze_size / 2
    passages = cm.maze_passages()
    dist = cm.maze_distances(cm.MAZE_ENTRANCE)
    assert set(dist) == set(cells)
    assert dist[cm.DOOR_HEART[0]] >= 60
    assert len(cm.dead_ends()) >= 20
    assert len(passages) - (len(cells) - 1) >= 30
    gates = {tuple(sorted(g.cells)) for g in cm.MAZE_GATES}
    for a, b in passages:
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
        za, zb = MAZE_ROOMS[cm.room_of(a)][0], MAZE_ROOMS[cm.room_of(b)][0]
        assert za == zb or tuple(sorted((a, b))) in gates


def test_the_maze_gates_rise_in_price_along_the_spiral(built) -> None:
    """Four bought gates in the maze (plus the farmyard's), dearer as you go in."""
    doors = {d.id: d for d in built.elements(Door)}
    prices = [doors[f"door_{g.key}"].price for g in cm.MAZE_GATES]
    assert prices == sorted(prices) and len(prices) == 4
    assert doors["door_mazeentry"].price <= prices[0]


def test_the_maze_is_the_same_every_build() -> None:
    from zmforge.recipes import corn_maze_layout as lay

    lay.carve.cache_clear()
    first = cm.maze_passages()
    lay.carve.cache_clear()
    assert cm.maze_passages() == first


def test_you_can_walk_the_maze_from_the_farmyard_to_the_heart(built, rooms, flood) -> None:
    """The flood from the spawn (doors open) reaches every maze cell and the
    heart, with the props standing in the way."""
    for cell in cm.maze_cells_all():
        key = cm.room_of(cell)
        room = rooms[f"maze_{key[4:]}_room"]
        x, y = FIXTURE.cell_centre(cell)
        hits = [flood.under(x + dx, y + dy, room.floor_z + 4.0, only_reached=True)
                for dx, dy in ((0, 0), (40, 0), (-40, 0), (0, 40), (0, -40))]
        assert any(h is not None for h in hits), cell
    heart = rooms["heart_room"]
    assert flood.under(heart.interior.centre.x + 200, heart.interior.centre.y + 200, heart.floor_z + 4.0,
                       only_reached=True) is not None


def test_the_quest_and_the_power_are_in_dead_ends(built) -> None:
    spots = parts.MAZE_SPOTS
    ends = set(cm.dead_ends())
    assert spots["power"] in ends and set(spots["ears"]) <= ends
    assert MAZE_ROOMS[cm.room_of(spots["power"])][0] == "mazedeep"
    assert [MAZE_ROOMS[cm.room_of(c)][0] for c in spots["ears"]] == ["mazeentry", "mazedeep"]
    assert spots["path"][0] == cm.MAZE_ENTRANCE and spots["path"][-1] == cm.DOOR_HEART[0]


def test_every_zone_is_reached_from_the_spawn(built, rooms, flood) -> None:
    for room in rooms.values():
        c = room.interior.centre
        hits = [flood.under(c.x + dx, c.y + dy, room.floor_z + 4.0, only_reached=True)
                for dx in (-150, 0, 150) for dy in (-150, 0, 150)]
        assert any(h is not None for h in hits), room.id


# --------------------------------------------------------------------------
# The hayride
# --------------------------------------------------------------------------
def test_the_route_is_a_loop_from_the_stop_through_the_gate(rooms) -> None:
    route = hayride_route(FIXTURE)
    assert route[0] == route[-1]
    assert route_length(route) > 4000.0
    # It crosses the farmyard/patch wall inside the gate opening.
    gate = rooms["patch_room"].aperture_boxes[0]
    crossings = [(a, b) for a, b in zip(route, route[1:])
                 if (a[0] - FIXTURE.patch.mins.x) * (b[0] - FIXTURE.patch.mins.x) < 0]
    assert len(crossings) == 2
    for a, b in crossings:
        t = (FIXTURE.patch.mins.x - a[0]) / (b[0] - a[0])
        y = a[1] + t * (b[1] - a[1])
        assert gate.mins.y + 60 <= y <= gate.maxs.y - 60


def test_every_waypoint_keeps_well_inside_the_corn(rooms) -> None:
    yard, patch = rooms["farmyard_room"].interior, rooms["patch_room"].interior
    for x, y in hayride_route(FIXTURE):
        box = yard if x < FIXTURE.patch.mins.x else patch
        clearance = min(x - box.mins.x, box.maxs.x - x, y - box.mins.y, box.maxs.y - y)
        assert clearance >= cm.HAYRIDE_WALL_CLEARANCE - 1e-6, (x, y, clearance)


def test_nothing_solid_stands_in_the_hayride_lane(built) -> None:
    route = hayride_route(FIXTURE)
    for element in built.elements(Massing):
        for solid in element.solids:
            box = getattr(solid, "bounds", None)
            if box is None or box.mins.z > 200 or element.id.startswith(("mazeentry", "mazedeep")):
                continue
            if box.maxs.x < FIXTURE.farmyard.mins.x or box.mins.y < FIXTURE.farmyard.mins.y:
                continue
            assert cm._box_clear_of_route(box, route, 100.0), element.id
    for scatter in built.elements(PropScatter):
        for prop in scatter.props:
            if prop.solid:
                assert cm.distance_to_route(prop.origin.x, prop.origin.y, route) > 100.0, prop.id


def test_the_hayride_is_wired_in_the_server_script(committed) -> None:
    server = committed["server"]
    for needle in ("function zmf_hayride_init()", "PlayerLinkToDelta( e_seat, \"tag_origin\"",
                   "e_base MoveTo(", "e_base RotateTo(", "zm_score::minus_to_player_score( 500 )",
                   "level.player_out_of_playable_area_monitor_callback = &zmf_hayride_zone_ok;",
                   'level notify( "zmf_hayride_lap", a_riders );', "self SetOrigin( e_seat.origin );",
                   "level thread zmf_hayride_init();", 'level flag::get( "enter_patch" )'):
        assert needle in server, needle
    for x, y in hayride_route(FIXTURE):
        assert f"( {x:g}, {y:g}, " in server


def test_the_stop_says_what_it_costs(committed) -> None:
    assert "Hold ^3[{+activate}]^7 to board the hayride [Cost: 500]" in committed["strings"]


def test_the_hayride_models_are_measured_and_declared(committed) -> None:
    for part in cs.hayride_parts():
        assert part.model in MODEL_BOX
        assert f"xmodel,{part.model}" in committed["manifest"]
    assert len(cs.hayride_seats()) == 4


def test_the_stop_is_off_the_lane_and_the_riders_are_set_down_off_it() -> None:
    route = hayride_route(FIXTURE)
    tx, ty, _ = cs.hayride_trigger(FIXTURE, 0.0)
    assert cm.distance_to_route(tx, ty, route) > 150.0
    for x, y, _ in cs.hayride_unload(FIXTURE, 0.0):
        assert cm.distance_to_route(x, y, route) > 150.0


# --------------------------------------------------------------------------
# Dressing
# --------------------------------------------------------------------------
def test_every_area_is_densely_dressed(built) -> None:
    """The review's props-per-room floor (review.facts.DENSITY_FLOOR)."""
    from zmforge.review.facts import DENSITY_FLOOR

    counts = built.dressing_counts
    assert set(counts) == set(ZONES) | set(MAZE_ROOMS)
    for zone, n in counts.items():
        # A floor, not a band (map-principles P2): more is fine; the whole
        # map carries thousands of props, the corn most of them.
        assert n >= DENSITY_FLOOR, (zone, n)
    assert sum(counts.values()) >= 3000
    for key in MAZE_ROOMS:
        assert counts[key] >= 500, key


def test_every_prop_is_a_measured_model(built) -> None:
    """A scaled stock prop is walk-through; a kit prop keeps the library's
    solidity (Z21), and a solid one is only scaled within KIT_SCALE."""
    from zmforge.recipes.props import KIT_SOLID

    lo, hi = parts.KIT_SCALE
    for scatter in built.elements(PropScatter):
        for prop in scatter.props:
            assert prop.model in MODEL_BOX, prop.model
            if prop.model in KIT_SOLID:
                assert prop.solid == KIT_SOLID[prop.model], prop.id
                if prop.solid:
                    assert lo <= prop.scale <= hi, (prop.id, prop.scale)
            elif prop.scale != 1.0:
                assert not prop.solid, prop.id


def test_the_stand_ins_are_gone(built) -> None:
    """No scaled orange for a pumpkin, no grass for corn, no forklift or
    semi for the tractor, no brush for a bale or a fence."""
    models = {p.model for s in built.elements(PropScatter) for p in s.props}
    assert not models & {"p7_food_fruit_watermelon", "p7_foliage_grass_tall_single_lrg",
                         "veh_t7_civ_forklift_modular_manned_forklift",
                         "veh_t7_civ_truck_semi_cab_trailer"}
    # The tall grass cluster is grass now (parts.GRASS_TALL), not corn.
    assert "p7_foliage_grass_tall_cluster_med" not in {parts.STALK, parts.STALK_THIN}
    oranges = [p for s in built.elements(PropScatter) for p in s.props if p.model == parts.ORANGE]
    assert oranges and all(p.scale == 1.0 for p in oranges)
    # (The scarecrows are a brush pole: the kit cross reads as a small
    # figure on a stone plinth.)
    assert not [e.id for e in built.elements(Massing) if "bale" in e.id or "fence" in e.id]
    assert {parts.PUMPKIN, parts.JACK, parts.STALK, parts.STALK_THIN, parts.HAY_BALE,
            parts.HAY_STACK, parts.FENCE, parts.TRACTOR} <= models


def test_the_patch_is_full_of_pumpkins_and_the_corn_has_stalks(built) -> None:
    by_zone: dict[str, dict[str, int]] = {}
    for scatter in built.elements(PropScatter):
        zone = scatter.id.split("_")[1]
        for prop in scatter.props:
            by_zone.setdefault(zone, {}).setdefault(prop.model, 0)
            by_zone[zone][prop.model] += 1
    assert by_zone["patch"][parts.PUMPKIN] >= 25
    # The farmyard's corn edge is mostly taken by the stand, the tractor, the
    # stop and four gates, so it carries fewer.
    for zone, least in (("farmyard", 15), ("patch", 30), ("heart", 30),
                        *((zone, 400) for zone in {z for z, _ in MAZE_ROOMS.values()})):
        stalks = by_zone[zone].get(parts.STALK, 0) + by_zone[zone].get(parts.STALK_THIN, 0)
        assert stalks >= least, (zone, stalks)
    assert by_zone["farmyard"][parts.TRACTOR] == 1


def test_it_is_lit_by_lanterns_and_the_moon(built) -> None:
    lamps = [e for e in built.elements() if type(e).__name__ == "Lamp"]
    warm = [l for l in lamps if l.colour == cm.LANTERN]
    assert len(warm) >= 40
    assert any(l.id.startswith("patch_jack") for l in lamps)


# --------------------------------------------------------------------------
# Gags
# --------------------------------------------------------------------------
def test_the_gags_ship_their_words(committed) -> None:
    strings = committed["strings"]
    for text in ("That was not apple cider.", "The scarecrow turned its head to look at you.",
                 "That was a prize pumpkin. The prize pumpkins here do that.",
                 "Prize pumpkins explode when shot. Stand well back, then shoot one."):
        assert text in strings, text


def test_the_scarecrows_turn_and_the_pumpkins_explode(committed) -> None:
    server = committed["server"]
    for needle in ("function zmf_scarecrow_watch()", "self RotateTo( ( 0, v_face[ 1 ], 0 ), 0.25 );",
                   "function zmf_pumpkin_wait()", "e_pumpkin SetCanDamage( true );",
                   'PlayFX( level._effect[ "def_explosion" ], v_at );', "RadiusDamage(",
                   "level thread zmf_scarecrows_init();", "level thread zmf_pumpkins();",
                   "level thread zmf_notices();"):
        assert needle in server, needle


def test_the_exploding_pumpkins_are_in_the_patch_off_the_lane() -> None:
    route = hayride_route(FIXTURE)
    for x, y in cs.EXPLODING_PUMPKINS:
        assert FIXTURE.patch.mins.x < x < FIXTURE.patch.maxs.x
        assert cm.distance_to_route(x, y, route) > 150.0


def test_the_prize_pumpkins_are_the_giant_glowing_ones(built, committed) -> None:
    """The tell: a size no placed pumpkin comes near, and a green glow on
    each that goes with it; and nobody is still told to shoot the green melons."""
    biggest = max(p.scale for s in built.elements(PropScatter) for p in s.props
                  if p.model in (parts.PUMPKIN, parts.JACK, parts.JACK_TALL))
    assert parts.PRIZE_SCALE >= 1.8 * biggest
    assert f'SetModel( "{parts.PRIZE}" );' in committed["server"]
    assert f"SetScale( {parts.PRIZE_SCALE:g} );" in committed["server"]
    # The glow is an effect on a script entity, deleted when the pumpkin is
    # shot; no baked light, which would stay on (as a lantern's would).
    assert not [l for l in built.elements() if type(l).__name__ == "Lamp" and l.id.startswith("patch_prize_")]
    server = committed["server"]
    for needle in (f'PlayFXOnTag( level._effect[ "{cs.PUMPKIN_GLOW_FX}" ], e_glow, "tag_origin" );',
                   "e_pumpkin.e_glow = e_glow;", "self.e_glow Delete();"):
        assert needle in server, needle
    assert server.index("self.e_glow Delete();") < server.index("self Delete();", server.index("zmf_pumpkin_wait"))
    lowered = committed["strings"].lower()
    for stale in ("melon", "watermelon", "the green ones", "forklift", "tractor-trailer", "very large oranges"):
        assert stale not in lowered, stale


def test_the_hayride_is_towed_by_the_tractor_and_it_moves(committed) -> None:
    models = [p.model for p in cs.hayride_parts()]
    assert parts.TRACTOR in models and "veh_t7_civ_forklift_modular_manned_forklift" not in models
    tractor = next(p for p in cs.hayride_parts() if p.model == parts.TRACTOR)
    # Nose along +x, the way the rig drives, and clear of the trailer bed.
    assert tractor.yaw == parts.TRACTOR_YAW
    assert cs.TRACTOR_X - 75.0 > MODEL_BOX[parts.FLATBED][1][0]
    server = committed["server"]
    assert f'e_part SetModel( "{parts.TRACTOR}" );' in server
    assert "e_part LinkTo( e_base );" in server and "e_base MoveTo(" in server


def test_the_leaving_line_goes_only_to_players_near_the_stop_not_on_board() -> None:
    """P13: the five-second call is for players who can still hop on, not
    the rest of the map (and not the rider who just read the boarded line)."""
    from zmforge.script.hayride import Seat, hayride
    lines = {k: f"R_{k.upper()}" for k in ("prompt", "away", "boarded", "leaving", "broke",
                                           "full")}
    script = hayride(route=[(0, 0), (500, 0), (500, 500), (0, 0)], z=0.0, parts=(),
                     seats=(Seat(offset=(0, 0, 0), yaw=0.0),), unload=((50, 0, 0),),
                     trigger=(10.0, 20.0, 0.0), price=500, prompt=lines["prompt"],
                     prompt_away=lines["away"], prompt_closed=None, said_boarded=lines["boarded"],
                     said_leaving=lines["leaving"], said_broke=lines["broke"], said_full=lines["full"],
                     said_closed=None, leaving_heard=600.0)
    depart = next(f for f in script.functions if f.name == "zmf_hayride_depart").body
    say = next(i for i, line in enumerate(depart) if "R_LEAVING" in line)
    assert depart[say].strip() == 'e_p IPrintLnBold( &"R_LEAVING" );'
    guard = "\n".join(depart[:say])
    assert "DistanceSquared( e_p.origin, ( 10, 20, 0 ) ) < 360000" in guard
    assert "e_p.zmf_hayride_riding" in guard
    assert not any("a_players[ i ] IPrintLnBold" in line for line in depart)


def test_a_rider_reads_one_line_a_ride_and_no_prompt_while_seated(committed) -> None:
    """Too many prompts during the ride read as noise (P17, few
    broadcasts).  The boarded line is the only line a
    rider reads: none at the waypoints, none on the way home, and neither
    use trigger's prompt shows to a seated rider."""
    server = committed["server"]

    def body(name: str) -> str:
        part = server[server.index(f"function {name}("):]
        return part[: part.index("\n}\n")]

    board, depart = body("zmf_hayride_board"), body("zmf_hayride_depart")
    assert board.count("IPrintLnBold") == 1
    assert "zmf_hayride_trigger SetInvisibleToPlayer( e_player, true );" in board
    assert "zmf_hayride_ride_trigger SetInvisibleToPlayer( e_player, true );" in board
    # The only bold line in the call is the leaving call, to players not aboard.
    assert depart.count("IPrintLnBold") == 1 and "e_p IPrintLnBold" in depart
    assert "zmf_hayride_say_riders" not in server and "HAYRIDE_STOP_" not in committed["strings"]
    assert "zmf_hayride_trigger SetInvisibleToPlayer( e_rider, false );" in depart


def test_the_golden_corn_counts_the_moment_it_is_picked_up(committed) -> None:
    """Each pickup counts (x/3) at once; no cider-stand
    hand-in, no carry timer."""
    server, strings = committed["server"], committed["strings"]
    item = server[server.index("function zmf_quest_item_ears("):]
    item = item[: item.index("\n}\n")]
    assert "zmf_quest_progress(" in item and 'level notify( "zmf_q_filed_ears" );' in item
    assert "zmf_q_bag" not in item
    assert "function zmf_quest_desk_ears(" not in server
    assert "p7_food_fruit_banana_bunch" in server
    for gone in ("hand the golden corn", "GOLDEN CORN:", "The cider stand wants golden corn"):
        assert gone not in strings, gone


def test_the_hayride_boards_on_the_move_and_does_not_shove(committed) -> None:
    """In play the wagon pushed players off and could only be boarded
    at the stop.  A use trigger rides linked to the base, the parts are not
    solid while it drives, and a mid-lap rider is set down at the stop but
    earns no full lap (quest credit)."""
    server = committed["server"]
    init = server[server.index("function zmf_hayride_init("):]
    init = init[: init.index("\n}\n")]
    for needle in ('t_ride = spawn( "trigger_radius_use", v_stop', "t_ride EnableLinkTo();",
                   "t_ride LinkTo( e_base );", "level.zmf_hayride_ride_trigger = t_ride;"):
        assert needle in init, needle
    assert "level thread zmf_hayride_listen( level.zmf_hayride_ride_trigger, true );" in server
    assert "zmf_hayride_listen( t_stop, false );" in server
    listen = server[server.index("function zmf_hayride_listen( t_use, b_moving )"):]
    listen = listen[: listen.index("\n}\n")]
    assert '( level.zmf_hayride_state == "away" && !b_moving )' in listen
    assert "zm_score::minus_to_player_score( 500 )" in listen
    # A downed or spectating player cannot board: the same
    # guard the gamble machine and the quest items use, before any charge.
    guard = listen.index("e_who laststand::player_is_in_laststand()")
    assert guard < listen.index("zm_score::minus_to_player_score")
    assert '"spectator"' in listen[max(0, guard - 200): guard + 200]
    assert "#using scripts\\shared\\laststand_shared;" in server

    depart = server[server.index("function zmf_hayride_depart("):]
    depart = depart[: depart.index("\n}\n")]
    assert depart.index("zmf_hayride_solid( false );") < depart.index("MoveTo( a_route[ i ]")
    late, append = depart.index("if ( b_late )"), depart.index("a_riders[ a_riders.size ] = e_rider;")
    assert late < append < depart.index('e_rider notify( "zmf_hayride_rode" );')
    assert depart.index("e_rider Unlink();") < late  # a late rider still gets off
    assert "level thread zmf_hayride_resolid();" in depart
    assert 'e_seat.zmf_late = ( level.zmf_hayride_state == "away" );' in server
    assert "NotSolid();" in server and "Solid();" in server


def test_the_hayride_step_ends_on_its_own_notify(committed) -> None:
    server = committed["server"]
    start = server.index("function zmf_quest_step_hayride(")
    step = server[start: server.index("\n}\n", start)]
    assert 'level notify( "zmf_q_end_hayride" );' in step
    assert step.index('level notify( "zmf_q_end_hayride" );') < step.index("zmf_quest_finish(")


def test_the_scarecrows_are_a_pole_with_a_carved_head(built, committed) -> None:
    """A scarecrow on a block reads as a statue on a plinth, so each
    scarecrow is a wooden pole standing in the ground, with no kit cross, no
    plinth and no mound, and the scripted head sits on the pole's top."""
    blocks = {e.id: e for e in built.elements(Massing)}
    poles = [e for i, e in blocks.items() if i.endswith("_scarecrow_pole")]
    assert len(poles) >= 1
    # The patch's decorative scarecrow is gone: no pole, no
    # head, no turning figure; the heart's (the quest's) is the only one.
    assert "patch" not in parts.SCARECROWS and "patch_scarecrow_pole" not in blocks
    assert not [e for e in built.elements(Massing) if e.targetname == parts.static_head_name("patch")]
    assert parts.static_head_name("patch") not in committed["server"]
    assert parts.CROSS not in {p.model for s in built.elements(PropScatter) for p in s.props}
    assert not [i for i in blocks if "scarecrow_mound" in i]
    for name in ("heart",):
        x, y, top = parts.SCARECROWS[name]
        pole = blocks[f"{name}_scarecrow_pole"]
        (x0, y0, z0), (x1, y1, z1) = pole.bounds.mins, pole.bounds.maxs
        assert x0 < x < x1 and y0 < y < y1 and z1 == pytest.approx(top)
        assert z1 - z0 == pytest.approx(parts.POLE_TOP) and parts.POLE_TOP >= 140.0
    assert parts.JACK in {p.model for p in cs.scarecrow_parts()}
    assert f'e_part SetModel( "{parts.JACK}" );' in committed["server"]


def test_the_scripted_scarecrows_carry_a_static_head_the_script_removes(built, committed) -> None:
    """The scripted jack never draws in the editor, so without a static head
    a scripted scarecrow reads as a headless shirt on a T-post.  The heart's
    scarecrow carries a sack head and straw hat on the pole top as one
    ``script_brushmodel``, and the script deletes it when it spawns the
    turning head, so the two never stand in the same spot."""
    for name in ("heart",):
        tname = parts.static_head_name(name)
        head = [e for e in built.elements(Massing) if e.targetname == tname]
        ids = {e.id for e in head}
        assert {f"{name}_scarecrow_head_sack", f"{name}_scarecrow_head_brim",
                f"{name}_scarecrow_head_crown"} <= ids
        x, y, top = parts.SCARECROWS[name]
        sack = next(e for e in head if e.id.endswith("_head_sack")).bounds
        assert sack.mins.z == pytest.approx(top) and sack.mins.x < x < sack.maxs.x and sack.mins.y < y < sack.maxs.y
        # One brush entity of that name in the map, not world brushes.
        assert committed["map"].count(f'"targetname" "{tname}"') == 1
        block = committed["map"].split(f'"targetname" "{tname}"')[0].rsplit('"classname"', 1)[1]
        assert block.startswith(' "script_brushmodel"')
        # The script removes it as it puts the turning head up.
        server = committed["server"]
        assert f'e_static = GetEnt( "{tname}", "targetname" );' in server
        assert server.index(f'GetEnt( "{tname}"') > server.index(f'e_part SetModel( "{parts.JACK}" );')
    # The dead ends' scarecrows keep their pumpkin heads and get no scripted one.
    assert not [e for e in built.elements(Massing) if e.targetname and "_scene_" in e.id]


def test_no_loft_bale_stands_over_a_barricade_window(built) -> None:
    """Bales placed with ``check=False`` would ignore the windows' keep-out
    (dress_barn_1_17..1_20); a solid prop placed unchecked is still kept 90
    off a window, so the east-end hayloft bales stand at the back wall."""
    wins = [w.barricade_origin for w in built.elements(Window)]
    for s in built.elements(PropScatter):
        for p in s.props:
            if not p.solid:
                continue
            for o in wins:
                near = abs(p.origin.x - o.x) < 90 and abs(p.origin.y - o.y) < 90
                assert not (near and o.z - 10 <= p.origin.z <= o.z + 260), (s.id, p.model, p.origin)


def test_the_farmyard_boards_and_the_back_row(built) -> None:
    """The farmyard's north and south walls carry posts and rails (the plank
    face alone reads as earth), and the back row puts stalks into
    the band's widest gaps, including over the wall-side zombie spawns."""
    ids = [e.id for e in built.elements(Massing) if e.id.startswith("farmyard_boards_")]
    for side in ("n", "s"):
        assert sum(f"_{side}_post_" in i for i in ids) >= 12
        assert sum(f"_{side}_rail_" in i for i in ids) == 2 * len(parts.YARD_RAILS)
    # The bands' own back rows and the refill (parts.refill_bare) close
    # most gaps before the back row looks.
    assert parts.BACK_ROW[0] + built.corn_refilled > 0


def test_the_scarecrows_have_arms_and_clothes_on_them(built) -> None:
    """A bare pole reads as a cross on a plinth, so every scarecrow has
    static plank arms in flannel sleeves, a flannel body and denim legs on
    every scarecrow, not only the scripted head; the script carries no arms
    of its own.  Each is man-sized, the legs hanging clear of the ground."""
    ids = [e.id for e in built.elements(Massing)]
    poles = sum(i.endswith("_scarecrow_pole") for i in ids)
    for piece in ("_scarecrow_arms", "_scarecrow_body", "_scarecrow_leg_l", "_scarecrow_sleeve_r"):
        assert sum(i.endswith(piece) for i in ids) == poles >= 2, piece
    body = next(e for e in built.elements(Massing) if e.id == "heart_scarecrow_body")
    assert body.bounds.maxs.z - body.bounds.mins.z >= 40.0
    assert "p7_debris_wood_board_2x4x128" not in {p.model for p in cs.scarecrow_parts()}


def test_the_walls_and_floors_read_as_a_farm(built) -> None:
    """The corn walls are dark earth, not the lawn that draws as
    blue-grey slabs; the farmhouse is one plank finish with no brick wall;
    no harvest heap or sandbag indoors; the outdoor floors carry tracks and
    tilled rows."""
    assert cm._CORN.name != "t7_grass_lawn_medium_small_green"
    assert cm._HOUSE.wall == cm._PLANKS and not cm._HOUSE.sides
    house = [p.model for s in built.elements(PropScatter) if s.id.startswith("dress_farmhouse_") for p in s.props]
    assert parts.SACK not in house and house.count(parts.PUMPKIN) <= 2
    ids = [e.id for e in built.elements(Massing)]
    for prefix in ("patch_row_", "heart_row_", "patch_hayride_track_", "heart_path_gate_", "farmyard_path_ns_"):
        assert any(i.startswith(prefix) for i in ids), prefix
    assert sum(len(s.props) for s in built.elements(PropScatter)) < PROP_CEILING_V2


# --------------------------------------------------------------------------
# The quest
# --------------------------------------------------------------------------
def test_the_quest_has_every_kind_of_step_and_a_20000_point_win(built) -> None:
    quest = built.quest
    kinds = [type(s).__name__ for s in quest.steps]
    assert kinds == ["HitTargets", "RideHayride", "SoulBox", "CollectDeliver", "HitTargets",
                     "DefeatBoss", "StandInZone"]
    assert quest.steps[0].mode == "shoot" and quest.steps[4].mode == "melee"
    assert quest.steps[5].boss.name == "The Scarecrow"
    assert quest.exit.price == 20000
    assert len(cm.QUEST_STEPS) == len(quest.steps) + 1


def test_the_quest_is_woven_into_the_script(committed) -> None:
    server = committed["server"]
    assert "zmf_boss_scarecrow_spawn" in server
    assert 'level waittill( "zmf_hayride_lap", a_riders );' in server
    assert "YOU SURVIVED THE HARVEST" in committed["strings"]


def test_the_boss_is_the_heart_scarecrow_climbing_down(built, committed) -> None:
    """The boss spawns from the scarecrow, not somewhere new.  The
    figure stays on its post after the wake step, and leaves it the moment
    the boss appears at the post's foot (snapped to the navmesh), where the
    arrival quake and effect play."""
    boss = built.quest.steps[5].boss
    x, y, top = parts.SCARECROWS["heart"]
    assert math.dist(boss.spawn_at[:2], (x, y)) == pytest.approx(parts.SCARECROW_FOOT)
    assert parts.SCARECROW_ARM < parts.SCARECROW_FOOT <= 96.0 and boss.spawn_snap
    server = committed["server"]
    spawn = server[server.index("function zmf_boss_scarecrow_spawn("):]
    spawn = spawn[: spawn.index("\n}\n")]
    # the snapped point is the spawn point itself (bosses._arrival_lines)
    snap, tp = spawn.index("GetClosestPointOnNavMesh( v_at,"), spawn.index("s_at.origin = v_at;")
    assert snap < tp < spawn.index('level notify( "zmf_boss_scarecrow_spawned" );')
    assert "Earthquake( 0.35, 2, v_at, 1500 );" in spawn
    down = server[server.index("function zmf_scarecrow_climbs_down("):]
    down = down[: down.index("\n}\n")]
    assert 'level waittill( "zmf_boss_scarecrow_spawned" );' in down
    assert "zmf_quest_step_done" not in down and "zmf_q_state" not in down


def test_the_quest_use_triggers_stand_clear_of_every_other_use_trigger(built) -> None:
    rooms_ = {r.id: r for r in built.elements(Room)}
    keyed = {"farmyard": rooms_["farmyard_room"], "patch": rooms_["patch_room"]}
    others = [cs.hayride_trigger(FIXTURE, keyed["farmyard"].floor_z)]
    others += list(cs.notice_spots(FIXTURE, keyed).values())
    for point in built.quest.use_points():
        for other in others:
            assert math.dist(point[:2], other[:2]) > 110.0, (point, other)


def test_all_three_lanterns_are_script_lanterns_on_bales(built) -> None:
    """Each quest lantern is the tall carved one, spawned by script on top of
    a hay bale, and no tall one is placed as a static model."""
    props = [p for s in built.elements(PropScatter) for p in s.props]
    assert not [p for p in props if p.model == parts.JACK_TALL]
    targets = built.quest.steps[0].targets
    assert len(parts.QUEST_JACKS) == len(targets) == 3
    bales = [p for p in props if p.model in (parts.HAY_BALE, parts.HAY_STACK)]
    for target, (x, y, top, _) in zip(targets, parts.QUEST_JACKS):
        assert math.dist(target.point[:2], (x, y)) < 1.0
        assert top < target.point[2] < top + MODEL_BOX[parts.JACK_TALL][1][2] * parts.QUEST_JACK_SCALE
        assert any(math.dist((b.origin.x, b.origin.y), (x, y)) < 1.0 and b.origin.z < top for b in bales)


def test_a_shot_lantern_goes_dark(built, committed) -> None:
    """A baked light cannot be switched off, so the
    quest lanterns have no map light; their glow is an effect on a script
    entity, deleted on the hit, and the lantern becomes a plain pumpkin."""
    lamps = [l.id for l in built.elements() if type(l).__name__ == "Lamp"]
    assert not [l for l in lamps if "quest_jack" in l]
    server = committed["server"]
    for needle in ("level thread zmf_lanterns();", 'level waittill( "zmf_q_hit_lanterns", j, e_who );',
                   f'PlayFXOnTag( level._effect[ "{cs.LANTERN_GLOW_FX}" ], e_fx, "tag_origin" );',
                   "e_fx Delete();", f'e_jack SetModel( "{parts.PUMPKIN}" );',
                   f'PlayFX( level._effect[ "{cs.LANTERN_OUT_FX}" ]'):
        assert needle in server, needle
    assert server.count(f'e_jack SetModel( "{parts.JACK_TALL}" );') == 3
    assert f"xmodel,{parts.JACK_TALL}" in committed["manifest"]


# --------------------------------------------------------------------------
# The loading screen
# --------------------------------------------------------------------------
def test_the_loading_screen_is_drawn_here_and_is_stable() -> None:
    blob = loadscreen_png()
    assert render_loadscreen().size == SIZE
    assert hashlib.sha256(blob).hexdigest() == hashlib.sha256(loadscreen_png()).hexdigest()
    assert loading_screen_for("corn_maze") == blob


def test_the_ground_is_grassed_but_not_the_walkways(built) -> None:
    """Hundreds of grass clumps (a few tufts each), none solid, none on the
    hayride lane, and the whole map's props stay well inside the compiler's
    triangle ceiling."""
    from zmforge.recipes.props import MAX_MAP_TRIANGLES

    grass_models = {m for m, _, _ in parts.GRASS_TALL + parts.GRASS_LOW + parts.GRASS_LITTER}
    assert 1200 <= parts.GRASS["clumps"] <= 5200   # v2: the maze doubled
    assert parts.GRASS["patches"] >= 300
    # Clumps, not a lawn: a tuft has on average two or more others within reach.
    assert parts.GRASS["clumps"] >= 2.5 * parts.GRASS["patches"]
    assert parts.GRASS["tris"] < MAX_MAP_TRIANGLES // 4
    route = hayride_route(FIXTURE)
    for scatter in built.elements(PropScatter):
        for p in scatter.props:
            if p.model in grass_models and scatter.id.startswith(("dress_farmyard", "dress_patch")):
                assert not p.solid
                assert cm.distance_to_route(p.origin.x, p.origin.y, route) > cm.HAYRIDE_LANE_HALF, p


def _outdoor_rooms(rooms) -> dict:
    """The recipe's outdoor room keys -> their Room elements."""
    ids = {"farmyard": "farmyard_room", "patch": "patch_room", "heart": "heart_room",
           "mazeentry": "maze_entry_room", "mazenorth": "maze_north_room",
           "mazewest": "maze_west_room", "mazedeep": "maze_deep_room"}
    return {key: rooms[rid] for key, rid in ids.items()}


def test_no_grass_grows_through_a_wall_or_over_a_quest_spot(built, rooms) -> None:
    """Unchecked, about 120 clumps drew through the walls and a clump hid
    the heart's golden ear.  Every clump's turned
    footprint stays inside its room and off the maze's corn walls, and
    clear of every quest spot."""
    outdoor = _outdoor_rooms(rooms)
    grass = {m for m, _, _ in parts.GRASS_TALL + parts.GRASS_LOW + parts.GRASS_LITTER}
    corn = [m.bounds for m in built.elements(Massing) if "_corn_" in m.id]
    quest = cs.quest_points(FIXTURE, outdoor)
    heart_ear = cs.golden_ears(FIXTURE, outdoor)[2]
    assert heart_ear[:2] in quest
    checked = 0
    for scatter in built.elements(PropScatter):
        key = re.sub(r"_\d+$", "", scatter.id[len("dress_"):]) if scatter.id.startswith("dress_") else ""
        if key not in outdoor:
            continue
        inner = outdoor[key].interior
        for p in scatter.props:
            if p.model not in grass:
                continue
            checked += 1
            x0, x1, y0, y1 = parts._extent(p.model, p.scale, p.yaw)
            x0, x1, y0, y1 = p.origin.x + x0, p.origin.x + x1, p.origin.y + y0, p.origin.y + y1
            assert (x0 >= inner.mins.x and x1 <= inner.maxs.x
                    and y0 >= inner.mins.y and y1 <= inner.maxs.y), (scatter.id, p)
            # Against a corn wall: the circle the footprint turns in (it holds
            # every corner at any yaw) stays off the wall's box.
            reach = parts._grass_reach(p.model, p.scale)
            for w in corn:
                assert parts._box_dist(p.origin.x, p.origin.y, w) >= reach, (scatter.id, p)
            for qx, qy in quest:
                assert math.hypot(p.origin.x - qx, p.origin.y - qy) >= parts.QUEST_CLEAR + reach - 0.01, (p, qx, qy)
    assert checked >= 600  # enough clumps to cover the maze, short of a lawn


def test_the_pantry_hutch_things_stand_on_its_boards(built) -> None:
    """The farmhouse hutch is brushwork: what is set on it rests on a
    board's top, not in the air or inside it."""
    blocks = {e.id: e.authored.box for e in built.elements(Massing) if e.id.startswith("farmhouse_hutch_board_")}
    assert len(blocks) == 4
    tops = sorted(b.maxs.z for b in blocks.values())
    x0 = min(b.mins.x for b in blocks.values())
    x1 = max(b.maxs.x for b in blocks.values())
    on = [p for s in built.elements(PropScatter) for p in s.props
          if x0 <= p.origin.x <= x1 and any(b.mins.y <= p.origin.y <= b.maxs.y for b in blocks.values())
          and p.origin.z > tops[0]]
    assert len(on) >= 12
    for p in on:
        base = p.origin.z + MODEL_BOX[p.model][0][2] * p.scale
        assert min(abs(base - t) for t in tops[1:]) < 0.01, p


def test_the_farmhouse_has_its_furniture_groups(built) -> None:
    """No bare room: it has two
    rugs, a stove with the couch facing it, a bed on a frame, a dresser
    and a counter (all brushwork), with things standing on the dresser."""
    ids = {e.id: e for e in built.elements(Massing)}
    for part in ("farmhouse_rug_parlour_field", "farmhouse_rug_table_field", "farmhouse_stove_body",
                 "farmhouse_stove_pipe", "farmhouse_stove_clip", "farmhouse_bed_deck", "farmhouse_bed_head",
                 "farmhouse_dresser_body", "farmhouse_counter_body", "farmhouse_nightstand_body"):
        assert part in ids, part
    stove = ids["farmhouse_stove_body"].authored.box
    # A wooden settle, not the stock modern couch, facing the stove
    # (its high back on the north side, away from the stove).
    seat, back = ids["farmhouse_settle_2"].authored.box, ids["farmhouse_settle_3"].authored.box
    assert abs(seat.centre.x - stove.centre.x) < 20.0 and seat.mins.y > stove.maxs.y
    assert back.mins.y >= seat.maxs.y and back.maxs.z > seat.maxs.z + 20.0
    assert "p7_couch_cloth_modern_01" not in {p.model for s in built.elements(PropScatter) for p in s.props}
    dresser = ids["farmhouse_dresser_body"].authored.box
    top = ids["farmhouse_dresser_top"].authored.box.maxs.z
    on = [p for s in built.elements(PropScatter) for p in s.props
          if dresser.mins.x <= p.origin.x <= dresser.maxs.x and dresser.mins.y - 2 <= p.origin.y <= dresser.maxs.y
          and abs(p.origin.z + MODEL_BOX[p.model][0][2] * p.scale - top) < 0.01]
    assert len(on) >= 4
    assert not any(p.model == "p7_3arc_lobby_picture_41x29" for s in built.elements(PropScatter)
                   for p in s.props if s.id.startswith("dress_farmhouse"))


def test_no_wall_buy_hangs_on_the_corn(built, rooms) -> None:
    """A buy chalked on a corn wall cleared the corn in front
    of it and showed the painted wall.  Buys go on real walls in their own
    zone instead (placement.wallbuy): the farmyard's pistol on the board
    fence of the farmhouse's south wall, the patch's, the heart's and the
    maze's guns inside plank sheds (the corn behind the field sheds is
    whole); Z91 finds none on a lined face.  Only the lettered POWER board
    is a backboard."""
    from zmforge.blueprint.elements import WallWeapon
    from zmforge.verify.lining import buys_on_lined_faces

    boards = {e.id for e in built.elements(Massing) if e.id.endswith("_board_board")}
    assert boards == {"mazedeep_power_board_board"}
    assert buys_on_lined_faces(built) == []
    moved = {m[0]: m for m in built.moved_wall_buys}
    assert set(moved) == {"farmyard_wallbuy", "patch_wallbuy", "mazeentry_wallbuy", "heart_wallbuy"}
    assert moved["farmyard_wallbuy"][3] == "farmyard_room wall"
    for ident in ("patch_wallbuy", "mazeentry_wallbuy", "heart_wallbuy"):
        assert moved[ident][3].endswith("_buy_shed_back"), moved[ident]
    zones = {"farmyard_wallbuy": "farmyard_room", "patch_wallbuy": "patch_room",
             "mazeentry_wallbuy": "maze_entry_room", "heart_wallbuy": "heart_room"}
    for ident, key in zones.items():
        buy = next(w for w in built.elements(WallWeapon) if w.id == ident)
        assert rooms[key].interior.holds_flat(buy.position.x, buy.position.y), ident
    # The field sheds stand clear of the corn bands, so the corn behind is whole.
    for ident in ("patch_buy_shed_back", "heart_buy_shed_back"):
        b = next(e for e in built.elements(Massing) if e.id == ident).bounds
        for f in built.lined_faces:
            horizontal, face, (s0, s1), sign, *_ , depth = f
            near, along = ((b.mins.y, b.maxs.y), (b.mins.x, b.maxs.x)) if horizontal else \
                ((b.mins.x, b.maxs.x), (b.mins.y, b.maxs.y))
            if along[1] < s0 or along[0] > s1:
                continue
            assert min(abs(near[0] - face), abs(near[1] - face)) > depth, (ident, f)


def test_no_prop_pokes_through_a_room_wall(report) -> None:
    """Shelf items put at the shelf's middle stand 5-11 units into the barn
    walls, and a box on the farmhouse dresser 3 units into the north wall.
    The shared check every map gets (Z54: a solid floor
    prop is an error, a hollow item on a surface a warning); the corn's items
    go through dressing.fit_within."""
    assert not [str(f) for f in report if f.code == "Z54"]


def test_nothing_solid_stands_in_a_window_way_in(built, report) -> None:
    """The corn's window keep-outs are the shared zone
    (dressing.window_keepouts) made wider, so the shared check (Z57) finds
    nothing."""
    from zmforge.dressing import window_keepouts

    assert not [str(f) for f in report if f.code == "Z57"]
    assert len(window_keepouts(built)) == len(list(built.elements(Window)))


# --------------------------------------------------------------------------
# Time limits, finished steps, a calm screen (map-principles P6, P12, P13)
# --------------------------------------------------------------------------
def test_every_skill_step_runs_against_a_visible_clock(built) -> None:
    """P6: the shoot and knife steps are timed from their first progress,
    with a HUD countdown, a timeout line, and a start line that tells the
    player the limit.  The golden corn is a plain collect:
    no clock, no hand-in."""
    steps = {s.key: s for s in built.quest.steps}
    for key, limit in (("lanterns", cs.LANTERNS_TIME_LIMIT), ("wake", cs.WAKE_TIME_LIMIT)):
        step = steps[key]
        assert step.time_limit == limit, key
        assert step.timeout and "TIME'S UP" in step.timeout, key
        assert step.timer_line and "&&1" in step.timer_line, key
    assert f"{cs.LANTERNS_TIME_LIMIT:.0f} seconds" in steps["lanterns"].start
    ears = steps["ears"]
    assert not ears.deliver and ears.time_limit is None and ears.timer_line is None
    assert f"{cs.WAKE_TIME_LIMIT:.0f} seconds" in steps["wake"].start


def test_the_lanterns_light_again_when_their_clock_runs_out(committed) -> None:
    """The countdown wakes the hit notify with no target; the lanterns'
    thread relights every dark one, and ends with the step."""
    server = committed["server"]
    assert "function zmf_lanterns_relight()" in server
    assert "if ( !isdefined( j ) && !isdefined( e_who ) )" in server
    assert 'level endon( "zmf_q_end_lanterns" );' in server
    assert "function zmf_quest_timer_lanterns()" in server
    assert "function zmf_quest_timer_ears()" not in server
    assert "function zmf_quest_timer_wake()" in server


def test_no_chatter_on_a_timer(committed) -> None:
    """P13: the random PA jokes are gone; the round-end radio says things
    that are true for the whole game."""
    assert not [k for k in cs.GAG_LINES if k.startswith("pa_random")]
    assert "zmf_gag_pa_random" not in committed["server"]
    # P17: the round-end radio told players where the
    # power and Pack-a-Punch were, so it is gone, and so are the zone lines.
    assert not [k for k in cs.GAG_LINES if k.startswith(("pa_", "room_"))]
    assert "function zmf_gag_announcer(" not in committed["server"]
    assert "maze_map" not in cs.NOTICES


def test_a_prize_pumpkin_cannot_reach_the_hayride() -> None:
    route = hayride_route(cm.CornMazePlan())

    def gap(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / span)) if span else 0.0
        return math.dist(p, (a[0] + t * dx, a[1] + t * dy))

    seat_reach = max(abs(s.offset[1]) for s in cs.hayride_seats()) + 16.0
    for p in cs.EXPLODING_PUMPKINS:
        nearest = min(gap(p, route[i], route[(i + 1) % len(route)]) for i in range(len(route)))
        assert nearest - seat_reach > cs.PUMPKIN_BLAST_RADIUS, (p, nearest)


def test_no_zombie_climbs_out_where_a_notice_is_read(built, rooms) -> None:
    zones = {z: rooms[f"{z}_room"] for z in ("farmyard", "patch")}
    spots = cs.notice_spots(cm.CornMazePlan(), zones)
    for spawn in built.elements(Spawn):
        for key, (x, y, _) in spots.items():
            assert math.dist((x, y), (spawn.position.x, spawn.position.y)) > 150.0, (spawn.id, key)


def test_the_farm_is_signed_with_its_own_name(built, committed) -> None:
    """P14: the farm the text names has a sign saying so, not the kit's
    AeroFarm board."""
    models = {p.model for s in built.elements(PropScatter) for p in s.props}
    assert "p7_sign_aerofarm_01" not in models
    assert "HARVEST MOON FARM -- hold ^3[{+activate}]^7 to read" in committed["strings"]


def test_nothing_stands_inside_the_farmhouse_bed(built) -> None:
    props = [p for s in built.elements(PropScatter) for p in s.props if p.id.startswith("dress_farmhouse")]
    bed = next(p for p in props if "mattress" in p.model)
    (x0, y0, _), (x1, y1, _) = MODEL_BOX[bed.model]
    inside = [p.id for p in props if p is not bed and p.origin.z < bed.origin.z + 5.0
              and bed.origin.x + x0 < p.origin.x < bed.origin.x + x1
              and bed.origin.y + y0 < p.origin.y < bed.origin.y + y1]
    assert inside == []


def test_the_corn_stands_over_its_walls_and_the_props_fit_the_ceiling(built) -> None:
    """Grey wall shows between band stalks 30 apart and over full ones
    188-196 tall on a 200 wall, so the corn must stand over its walls; and
    the props, grass tufts included, must fit the prop ceiling."""
    from zmforge.review.facts import PROP_CEILING

    props = [p for s in built.elements(PropScatter) for p in s.props]
    assert len(props) <= PROP_CEILING - 300, len(props)
    band = [p for s in built.elements(PropScatter) if s.id.startswith("dress_maze")
            for p in s.props if p.model in (parts.STALK, parts.STALK_THIN)]
    tall = [p for p in band if MODEL_BOX[p.model][1][2] * p.scale > FIXTURE.corn_height]
    assert len(tall) >= 0.6 * len(band), (len(tall), len(band))
    assert parts.BAND_STEP <= 20.0


def test_the_farmhouse_table_stands_on_legs(built) -> None:
    """The table is a top, four legs, rails and a clip over it all, not one
    solid brush block, which reads as a legless block."""
    ids = {m.id for m in built.elements(Massing)}
    assert "farmhouse_table" not in ids
    assert {f"farmhouse_table_leg_{n}" for n in range(4)} <= ids
    assert {"farmhouse_table_top", "farmhouse_table_clip"} <= ids


def test_the_barn_carries_its_stores(built) -> None:
    """The barn must carry at least 160 props, well over a floor of 150."""
    barn = [p for s in built.elements(PropScatter) if s.id.startswith("dress_barn") for p in s.props]
    assert len(barn) >= 160, len(barn)
    assert sum(p.model == parts.HAY_STACK for p in barn) >= 30


def test_the_maze_rows_are_dressed_at_three_heights_within_the_prop_ceiling(built) -> None:
    """At about 440 props per 1000 x 1000 (stock maps carry 1,148) the maze
    rooms showed bare earth between the stalks.  Ground cover
    under and along the corn, waist pieces in the rows and a pole line with
    wires overhead lift every maze room over 500, and the map stays under the
    25,000 the link probe proved."""
    from zmforge.review.facts import _areas, _props, is_floor_litter

    counts = built.density_counts
    # Sized for the 17 x 17 maze.
    assert counts["under"] > 1000 and counts["front"] > 750 and counts["waist"] > 20
    assert counts["poles"] >= 8
    wires = [e.id for e in built.elements(Massing) if "_wire_" in e.id]
    assert len(wires) >= 2 * counts["poles"] - 16
    areas = _areas(built)
    props = _props(built, areas)
    for area in areas:
        if not area.key.startswith("maze"):
            continue
        mine = [p for p in props if p.area is area]
        per_k2 = (len(mine) - sum(1 for p in mine if is_floor_litter(p, area))) / (area.area / 1e6)
        assert per_k2 > 500, (area.key, round(per_k2))
    assert sum(len(s.props) for s in built.elements(PropScatter)) < PROP_CEILING_V2


def test_a_walk_through_clump_piece_is_measured_at_its_near_edge() -> None:
    """Z48: a clump limit tested at a piece's centre lets a tall grass
    cluster centred on the band front stand ~50 units further into the walk
    and close maze rows to the every-prop flood (six buyables).  The limit is
    on the piece's near edge."""
    from zmforge.recipes import corn_maze_setpieces as sp

    out = sp.CLUMP_OUT
    assert sp.clump_fits(40.0 - out, 40.0, solid=False)          # edge exactly CLUMP_OUT out
    assert not sp.clump_fits(0.0, 40.0, solid=False)             # centred on the front: 40 out
    assert not sp.clump_fits(-out, 10.0, solid=False)            # the old centre-only pass
    assert not sp.clump_fits(10.0, 20.0, solid=True)             # solid pieces stay wholly in
    assert not sp.clump_fits(parts.BAND_DEPTH - 10.0, 20.0, solid=False)  # nor into the wall
