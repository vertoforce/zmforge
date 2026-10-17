"""DMV of the Damned: the car park, the counter, the queue, and the arena.

These are properties of the model and of the text a commit writes.  Nothing
here says anything about how the map plays.

Two of them are the map's reason to exist and are written as measurements
rather than as claims.  ``test_the_whole_queue_is_walked_corner_by_corner``
hands :func:`zmforge.recipes.dmv.queue_route` to the player flood ``Z25``
runs and asks whether every corner of the switchback is standing room a
player reaches, which is the only way the "the pack-a-punch is at the end of
the line" gag is real rather than asserted.
``test_the_wrong_branch_is_a_dead_end_beside_the_door`` does the same for the
branch that wastes your time.

The boss is THE EXAMINER (:mod:`zmforge.recipes.dmv_quest`):
``test_the_arena_holds_the_examiner`` pins that it is an ordinary zombie
through the framework's own spawner, made tougher, and nothing more exotic.
"""

from __future__ import annotations

import math
import re

import pytest

from zmforge.blueprint.catalogue import WALL_WEAPON_WEAPONS
from zmforge.blueprint.elements import (
    Door,
    Machine,
    Massing,
    MysteryBox,
    PowerSwitch,
    PropScatter,
    Room,
    Spawn,
    WallWeapon,
    Window,
    Zone,
)
from zmforge.blueprint.installed import judge_misc_model, load_ledger
from zmforge.recipes import dmv_of_the_damned
from zmforge.materials import TOOL_MATERIALS, is_catalogued
from zmforge.spatial import Point, Side
from zmforge.recipes.dmv import (
    FIXTURE,
    FRONTAGE_WINDOWS,
    NOTICE_LINES,
    WAITING_SEAT_FORWARD,
    WAITING_SEAT_TOP,
    counter_run,
    parking_bays,
    bay_centres,
    bay_pitch,
    window_opening,
    window_y,
    PRICES,
    PROMPTS,
    TICKET_LINES,
    ticket_trigger_point,
    SKINS,
    _lanes,
    _rails,
    queue_dead_end,
    queue_route,
    take_a_number_perk,
    vehicle_registration_perk,
)
from zmforge.verify import check_blueprint
from zmforge.verify.documented import MIN_HALLWAY_CLEARANCE
from zmforge.verify.reachability import JUMP_UP, flood_from_spawn


MAP_NAME = "zm_dmv"

#: The ten rooms, and the zone each one is.  Spelled out here so a room
#: quietly disappearing from the recipe is a failure rather than a smaller
#: number.
ZONES = (
    "lot",
    "entry",
    "waiting",
    "windows",
    "eyeexam",
    "photo",
    "breakroom",
    "records",
    "queue",
    "office",
)


@pytest.fixture(scope="module")
def built():
    return dmv_of_the_damned(MAP_NAME)


@pytest.fixture(scope="module")
def report(built):
    """One pass of the checks for the whole module; it is not a cheap call."""
    return check_blueprint(built)


@pytest.fixture(scope="module")
def flood(built):
    """Where a player can walk from the spawn, flooded once and shared."""
    return flood_from_spawn(built)


@pytest.fixture(scope="module")
def committed(dmv_committed):
    return dmv_committed


# --------------------------------------------------------------------------
# The map as a whole
# --------------------------------------------------------------------------
def test_it_commits_with_no_errors(committed) -> None:
    assert committed["result"].report.errors == [], [
        str(f) for f in committed["result"].report.errors
    ]


def test_the_model_checks_pass_with_nothing_but_the_deliberate_warnings(report) -> None:
    """Four warnings, all of them the same decision.

    ``W1`` is on all four wall buys: the spec fixes the buy origin eight
    units inside the floor because that is where stock maps put it, and the
    check says so every time.  Nothing else is left: the queue's rails and
    the two counters are ``reachable=False``, which is the declaration ``Z46``
    and ``Z48`` read, and the props that stand on a counter stand inside its
    footprint, which is what ``Z44`` measures.  One ``Z58``: the counter
    monitors are measured to draw black in the editor render
    (props/notes.json), a renderer limit, not a map defect.  One ``Z60``
    (props/notes.json rules): the same two counter monitors have no seat
    within 72 units, because the staff side of the counter has no clerk
    chairs; it is a design choice left as a warning, and the window signs
    sit on the screen rather than floating off it.  One ``Z66``: the lot's
    63 plants are spread evenly (Clark-Evans R 1.0), also left as a warning
    (zmforge.dressing.cluster.mixed_clumps).
    One ``N5`` on the lot: the parked cars stand close to the lot's walls, so
    the strips behind them (55 units behind the slewed compact at the south
    end of the near row) are narrower than the 96-unit clearance for longer
    than 64 units.  It is how a full car park looks; the aisles are the route,
    the walkers still path through (N2), and moving the cars into the aisle to
    clear it would cost the bay lines (Z44).
    """
    from conftest import DESIGN_ADVISORIES

    assert report.errors == [], [str(f) for f in report.errors]
    codes = sorted(finding.code for finding in report.warnings
                   if finding.code not in DESIGN_ADVISORIES)
    assert codes == ["N5", "W1", "W1", "W1", "W1", "Z58", "Z60", "Z66"], [str(f) for f in report.warnings]
    z60 = next(str(f) for f in report.warnings if f.code == "Z60")
    assert "faced_by: p7_consumer_grade_monitor_medium" in z60
    z58 = next(str(f) for f in report.warnings if f.code == "Z58")
    assert "p7_consumer_grade_monitor_medium" in z58


def test_the_ten_rooms_and_ten_zones_are_the_ones_the_docstring_lists(built) -> None:
    rooms = built.elements(Room)
    assert len(rooms) == 10, [room.id for room in rooms]
    # One of them has no roof, and it is the one you start in.
    assert [room.id for room in rooms if not room.roofed] == ["lot_room"]
    assert tuple(zone.name for zone in built.elements(Zone)) == ZONES


def test_every_zone_has_a_door_into_it_and_somewhere_to_spawn(built) -> None:
    """A zone with no spawner is a room the round never arrives in."""
    risers = {spawn.zone_name for spawn in built.elements(Spawn)}
    windows = {window.zone_name for window in built.elements(Window)}
    for name in ZONES:
        assert name in risers or name in windows, name
    into = set()
    for door in built.elements(Door):
        into.update((door.zone_a, door.zone_b))
    assert into == set(ZONES)


def test_door_prices_rise_with_depth(built) -> None:
    prices = {door.id: door.price for door in built.elements(Door)}
    assert len(prices) == len(PRICES)
    route = ("lot_entry", "entry_waiting", "waiting_windows", "windows_records",
             "records_queue", "queue_office")
    along = [PRICES[key] for key in route]
    assert along == sorted(along) and len(set(along)) == len(along)


# --------------------------------------------------------------------------
# The queue, which is the map
# --------------------------------------------------------------------------
def test_the_queue_is_five_lanes_wide_enough_to_fight_in(built) -> None:
    lanes = _lanes(FIXTURE)
    assert len(lanes) == 5
    widths = [round(high - low, 3) for low, high in lanes]
    assert widths == [120.0, 120.0, 120.0, 120.0, 240.0]
    # Treyarch's own hallway minimum, the number N5 warns under.  The last
    # lane is wider because the pack-a-punch needs room either side of it.
    assert min(widths) >= MIN_HALLWAY_CLEARANCE
    queue = built.find("queue_room").interior
    assert lanes[0][0] == pytest.approx(queue.mins.y)
    assert lanes[-1][1] == pytest.approx(queue.maxs.y)


def test_the_rails_are_too_tall_to_hop_and_say_they_are_not_floor(built) -> None:
    """The gag is that you cannot skip the line, and 48 > 39 is why."""
    assert FIXTURE.rail_height > JUMP_UP
    rails = [built.find(rail_id) for rail_id, *_ in _rails(FIXTURE)]
    assert len(rails) == 4
    for rail in rails:
        assert isinstance(rail, Massing)
        assert rail.reachable is False, rail.id
        box = rail.bounds
        assert box.maxs.z - box.mins.z == pytest.approx(FIXTURE.rail_height)


def test_the_switchback_alternates_which_wall_its_rails_are_fixed_to(built) -> None:
    """The turns are what make the line a line rather than a room.

    A rail fixed to the west wall leaves its gap at the east end and the next
    one up leaves it at the west, so the walk has to double back; and every
    one of those gaps is wider than the lanes it joins.
    """
    queue = built.find("queue_room").interior
    for index, (_id, x0, x1, _y0, _y1) in enumerate(_rails(FIXTURE)):
        if index % 2 == 0:
            assert x0 == pytest.approx(queue.mins.x)
            assert queue.maxs.x - x1 == pytest.approx(FIXTURE.turn_width)
        else:
            assert x1 == pytest.approx(queue.maxs.x)
            assert x0 - queue.mins.x == pytest.approx(FIXTURE.turn_width)
    assert FIXTURE.turn_width >= MIN_HALLWAY_CLEARANCE


def test_the_whole_queue_is_walked_corner_by_corner(built, flood) -> None:
    """Every corner of the route is standing room the spawn reaches.

    This is the map's one gag and the only honest way to state it: the flood
    is the graph ``Z25`` uses, so a corner it does not reach is a corner no
    player gets to.
    """
    for point in queue_route():
        assert flood.under(point.x, point.y, point.z + 4.0, only_reached=True) is not None, (
            f"({point.x:g}, {point.y:g}) is not standing room a player reaches"
        )


def test_the_walk_to_pack_a_punch_is_longer_than_the_hall_it_is_in(built) -> None:
    """2,456 units of walking in an 868-unit room, measured off the route."""
    route = queue_route()
    length = sum(
        math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(route, route[1:])
    )
    queue = built.find("queue_room").interior
    assert length == pytest.approx(2456.0, abs=1.0)
    assert length > 2.5 * (queue.maxs.x - queue.mins.x)


def test_the_wrong_branch_is_a_dead_end_beside_the_door(built, flood) -> None:
    """Turn the wrong way and you walk 1,760 units back to where you started.

    Both halves are measured: every corner of the branch is walkable, so it
    is a real invitation rather than a wall, and its last corner is within a
    lane's width of the doorway you came in through.
    """
    branch = queue_dead_end()
    for point in branch:
        assert flood.under(point.x, point.y, point.z + 4.0, only_reached=True) is not None, (
            f"({point.x:g}, {point.y:g}) is not standing room a player reaches"
        )
    length = sum(
        math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(branch, branch[1:])
    )
    assert length == pytest.approx(1760.0, abs=1.0)
    door = built.find("queue_room").opening(0).box.centre
    end = branch[-1]
    # 275 units from the doorway it started at, which is the two lanes the
    # branch crossed on the way down: the wall it stops at is the one the
    # player walked past on the way in.
    back_at_the_start = math.dist((end.x, end.y), (door.x, door.y))
    assert back_at_the_start == pytest.approx(275.0, abs=2.0)
    assert back_at_the_start < length / 5.0
    # And it really is closed at that end: the rail between the branch's last
    # lane and the one above it runs to the west wall.
    first_rail = _rails(FIXTURE)[0]
    assert first_rail[1] == pytest.approx(built.find("queue_room").interior.mins.x)


def test_pack_a_punch_is_at_the_end_of_the_last_lane_with_its_back_to_a_wall(built) -> None:
    """A pack-a-punch authored perpendicular to the wall it stands against
    puts 24 units of it inside the brushwork (``Z9``, an error).  This one faces west out of the east wall: the facing is the
    heading the front points at, and the machine's own back is 16 units deep.
    """
    machine = built.find("queue_pap")
    assert isinstance(machine, Machine)
    assert machine.perk.slug == "pack_a_punch"
    queue = built.find("queue_room").interior
    lanes = _lanes(FIXTURE)
    assert machine.facing.name == "WEST"
    assert queue.maxs.x - machine.position.x == pytest.approx(24.0)
    assert lanes[-1][0] < machine.position.y < lanes[-1][1]
    # Nowhere else: one machine, at the end of the walk.
    assert [
        element.id
        for element in built.elements(Machine)
        if element.perk.slug == "pack_a_punch"
    ] == ["queue_pap"]


# --------------------------------------------------------------------------
# Every room sells something or does something
# --------------------------------------------------------------------------
def test_every_room_has_something_to_buy_or_something_to_do(built) -> None:
    """A room that sells nothing and does nothing is a defect, checked room by room.

    A perk, a wall buy, a box, the switch, the pack-a-punch or one of the two
    scripted gags.  A room with none of those is a corridor with a price on
    it.
    """
    doing: dict[str, list[str]] = {name: [] for name in ZONES}
    for element in built.elements():
        if not isinstance(element, (Machine, WallWeapon, MysteryBox, PowerSwitch)):
            continue
        zone = built.zone_of_point(element.position)
        assert zone is not None, element.id
        doing[zone.name].append(element.id)
    # The two rooms whose interesting thing is a script, not a purchase.
    doing["photo"].append("photo_booth_flash")
    for name in ZONES:
        assert doing[name], f"{name} has nothing to buy and nothing to do"


def test_the_seven_machines_are_one_per_room_and_the_limit_is_lifted(
    built, committed
) -> None:
    """Seven machines against a stock ceiling of four, so the ceiling goes."""
    # The two GobbleGum machines (script.gobblegum) sell no perk.
    perks = sorted(
        m.perk.slug for m in built.elements(Machine)
        if m.perk.slug not in ("pack_a_punch", "gobblegum")
    )
    assert perks == [
        "deadshot",
        "juggernog",
        "quick_revive",
        "speed_cola",
        "stamin_up",
        "take_a_number",
        "vehicle_registration",
    ]
    server = committed["server"]
    assert "level.get_player_perk_purchase_limit = &zmf_perk_purchase_limit;" in server
    limit = server[server.index("function zmf_perk_purchase_limit()") :]
    assert "return 99;" in limit[: limit.index("\n}\n")]


def test_the_ticket_machine_is_a_perk_this_repository_wrote(built) -> None:
    perk = take_a_number_perk()
    assert perk.slug == "take_a_number"
    assert perk.name == "TAKE A NUMBER"
    assert perk.cost == FIXTURE.ticket_cost
    assert [p.slug for p in built.custom_perks] == [
        "take_a_number",
        "vehicle_registration",
    ]
    # It is the cheapest machine in the map, because a number is not a
    # service; the stock machines all cost more.
    assert perk.cost < 2000


def test_the_registration_desk_sells_speed_and_sells_it_honestly(
    built, committed
) -> None:
    """VEHICLE REGISTRATION FEE: 20% faster, by the one call that moves a player.

    ``SetMoveSpeedScale`` is a scale on base movement -- ``zm_usermap.gsc:336``
    sets 1 on every player the usermap spawns -- so 1.2 is the design's 20%.
    Stamin-Up is not borrowed and could not be: ``_zm_perk_staminup.gsc`` makes
    no movement call at all, its boost is engine-side off
    ``specialty_staminup``, and this map places both machines.  **What a player
    holding both moves like is not measured.**
    """
    perk = vehicle_registration_perk()
    assert perk.slug == "vehicle_registration"
    assert perk.name == "VEHICLE REGISTRATION FEE"
    assert perk.cost == FIXTURE.registration_cost
    # 1.2x: 20% faster.
    assert "20% faster" in perk.effect.summary
    server = committed["server"]
    assert "self SetMoveSpeedScale( 1.2 );" in server
    assert "self SetMoveSpeedScale( 1 );" in server
    assert 'self waittill( "spawned_player" );' in server
    # placed in the window row, which is where a fee is paid
    machine = built.find("perk_vehicle_registration")
    assert machine.perk.slug == "vehicle_registration"


def test_the_two_perks_of_our_own_share_nothing_they_cannot_share() -> None:
    """Two perks on one map: two HUD slots, two bottles, two machines.

    Z50 refuses two perks writing one ``hudItems.perks.<key>`` path, because
    the shipped widget draws one image per key and nothing in the map decides
    which write lands last.  The bottles are separate for a duller reason:
    they are what the framework hands the player, and one drink cannot be two
    perks.
    """
    ticket = take_a_number_perk()
    registration = vehicle_registration_perk()
    assert ticket.icon.key != registration.icon.key
    assert ticket.bottle != registration.bottle
    assert ticket.machine_model != registration.machine_model
    assert ticket.specialty != registration.specialty


def test_the_registration_machine_is_the_lot_car_and_not_a_vending_model() -> None:
    """The registration machine is a car, not a vending model.

    The level-common zone carries no vehicle, so a machine left on the
    framework's model draws as ``p7_zm_vending_doubletap2`` and looks like
    Double Tap.  The lot's compact has a measured box and is declared in the
    map's zone for the framework's run-time ``SetModel``, so the machine is
    that car.  The framework's ``zm_collision_perks1`` clip is vending
    sized, so the recipe clips the rest of the car itself
    (``perk_registration_car_clip_*``).
    """
    from zmforge.recipes.dmv import REGISTRATION_CAR
    from zmforge.recipes.props import MODEL_BOX
    from zmforge.script.perks import STOCK_MACHINE_MODELS

    perk = vehicle_registration_perk()
    assert perk.machine_model == REGISTRATION_CAR
    words = {"car", "cars", "veh", "vehicle", "truck", "taxi", "sedan", "van", "bus"}
    assert words & set(perk.machine_model.split("_")), perk.machine_model
    assert perk.machine_model in MODEL_BOX
    # Not Double Tap's machine, and not any other stock vending machine.
    assert "doubletap" not in perk.machine_model
    assert perk.machine_model not in STOCK_MACHINE_MODELS


def test_the_stapler_is_the_most_expensive_thing_on_a_wall(built) -> None:
    buys = {element.id: element.price for element in built.elements(WallWeapon)}
    assert buys["office_wallbuy"] == FIXTURE.stapler_price
    assert buys["office_wallbuy"] == max(price for price in buys.values() if price)


def test_every_renamed_prompt_names_a_weapon_this_level_has(built, committed) -> None:
    """A prompt keyed on the buy's name instead of the gun's says nothing.

    ``Z22`` caught it: the bowie *buy* is ``bowie`` and the weapon it sells is
    ``bowie_knife`` (:data:`zmforge.blueprint.catalogue.WALL_WEAPON_WEAPONS`),
    and ``getweapon("bowie")`` returns nothing usable, so the line never
    reached a player.
    """
    expected = {WALL_WEAPON_WEAPONS.get(kind, kind): line for kind, line in PROMPTS.items()}
    assert built.weapon_prompts == expected
    assert "bowie_knife" in built.weapon_prompts
    for line in PROMPTS.values():
        assert line in committed["strings"], line


# --------------------------------------------------------------------------
# The back office: an arena, and not a boss
# --------------------------------------------------------------------------
def test_the_arena_encounter_is_wired_to_the_office_door(built, committed) -> None:
    """Buying the door is the whole encounter: sprinters, then hot spawns."""
    door = built.find("door_queue_office")
    server = committed["server"]
    assert f'level flag::wait_till( "{door.flag}" );' in server
    assert server.count(f'level flag::wait_till( "{door.flag}" );') == 2
    assert "zmf_closet_ambush" in server and "zmf_spawn_spike" in server
    assert f"a_spots[ {FIXTURE.ambush_count - 1} ]" in server


def test_the_sprinters_have_somewhere_to_stand(built, flood) -> None:
    """They are spawned behind the operator's counter, which is real floor."""
    office = built.find("office_room")
    counter = built.find("office_counter").bounds
    booth_y = counter.maxs.y + 40.0
    point = flood.under(office.interior.centre.x + 60.0, booth_y,
                        office.floor_z + 4.0, only_reached=True)
    assert point is not None, "the ambush spawns in the booth and the booth is not floor"


def test_the_booth_is_reachable_round_the_end_of_the_counter(built, flood) -> None:
    """The operator's window is a window, so the way in is the gap beside it.

    A counter run wall to wall would seal the strip behind it off, and a
    strip of floor no player and no walker can get to is exactly what ``Z25``
    and ``Z46`` exist to report.  164 units of gap at the east end is the
    answer, and this is the measurement of it.
    """
    office = built.find("office_room")
    counter = built.find("office_counter").bounds
    gap = office.interior.maxs.x - counter.maxs.x
    assert gap == pytest.approx(FIXTURE.booth_way_in)
    assert gap > 96.0  # Treyarch's hallway minimum; a walker fits too
    behind = flood.under(
        counter.maxs.x + gap / 2.0,
        (counter.maxs.y + office.interior.maxs.y) / 2.0,
        office.floor_z + 4.0,
        only_reached=True,
    )
    assert behind is not None


def test_the_arena_holds_the_examiner(built, committed) -> None:
    """The back office is the arena and THE EXAMINER is its boss.

    The boss is an ordinary zombie through the framework's own spawner with
    more health, a glow and a name (:mod:`zmforge.script.bosses`), spawned
    when a player walks into the office once the road test is open.  Nothing
    in the script claims a custom AI: no shield, no scripted animation, no
    AI class of its own.
    """
    server = committed["server"]
    spawn = server[server.index("function zmf_boss_examiner_spawn("):]
    spawn = spawn[: spawn.index("\n}\n")]
    assert 'zombie_utility::spawn_zombie( e_spawner, "zmf_boss_examiner", s_at );' in spawn
    assert "self.health = n_health;" in server
    assert "level thread zmf_boss_examiner_minions();" in spawn
    road = server[server.index("function zmf_quest_step_road("):]
    assert 't_arena = spawn( "trigger_radius"' in road[: road.index("\n}\n")]
    office = built.find("office_room").interior
    assert office.holds_flat(*[float(v) for v in
                               spawn.split("v_at = ( ")[1].split(" )")[0].split(",")[:2]])
    for claim in ("magic_bullet_shield", "spawn_ai(", "animscripted", "playanim", "dodamage"):
        assert claim not in server, f"the map's script mentions {claim}"
    assert {element.id for element in built.elements(Massing)} >= {
        "office_counter",
        "office_transom",
    }


# --------------------------------------------------------------------------
# The gags that are props, and the props that are gags
# --------------------------------------------------------------------------
def test_the_counter_run_is_the_only_thing_between_the_public_and_the_staff(
    built, flood
) -> None:
    """The one architectural fact this building is built on.

    PennDOT's photo licence centre co-location requirements, 4.1.3:
    "Employee workstations must be behind the PLC customer service counter
    area and accessible from the public service area only through a gate or
    a door".  So this measures three things rather than asserting them: the
    counter divides the hall, the public floor cannot climb it, and the gate
    at its north end is floor a player actually reaches.
    """
    face_x, back_x, run_y0, run_y1 = counter_run(FIXTURE)
    hall = built.find("windows_room").interior
    counter = built.find("windows_counter")
    # It crosses the hall: it starts on the south wall and it is a counter,
    # not a partition -- the staff side behind it is real floor.
    assert run_y0 == pytest.approx(hall.mins.y)
    assert back_x - face_x == pytest.approx(FIXTURE.counter_depth)
    assert hall.maxs.x - back_x > MIN_HALLWAY_CLEARANCE, back_x
    assert face_x - hall.mins.x == pytest.approx(FIXTURE.public_depth)
    # Too tall to climb from the public side, and it says so.
    assert counter.reachable is False
    assert FIXTURE.counter_height > JUMP_UP
    assert FIXTURE.ada_section_height > JUMP_UP
    # The gate is the gap it stops short of the north wall by, and both
    # sides of it are standing room.
    assert hall.maxs.y - run_y1 == pytest.approx(FIXTURE.staff_gate)
    assert FIXTURE.staff_gate >= MIN_HALLWAY_CLEARANCE
    gate = Point((face_x + back_x) / 2.0, (run_y1 + hall.maxs.y) / 2.0,
                 built.find("windows_room").floor_z)
    staff = Point(back_x + 120.0, 0.0, built.find("windows_room").floor_z)
    for name, where in (("gate", gate), ("staff floor", staff)):
        assert flood.under(where.x, where.y, where.z + 4.0,
                           only_reached=True) is not None, (name, where)


def test_the_counter_hall_has_one_service_window_in_a_plain_partition(built) -> None:
    """One service window, no numbers.

    A run of eight numbered bays with one open reads as one long black
    window, and the numbers as noise.  So the run is a
    partition wall with exactly one opening in it, framed at each side, and
    no sign brush on it carries a window number or a CLOSED plate.

    The bay grid that still places the desks and dressing is derived, not
    quoted: no published figure was found for the spacing of service
    positions, so the run is divided evenly and checked against ADA's 48 in
    of clear floor space at a service counter position.
    """
    centres = bay_centres(FIXTURE)
    pitch = bay_pitch(FIXTURE)
    steps = {round(b - a, 3) for a, b in zip(centres, centres[1:])}
    assert steps == {round(pitch, 3)}
    assert pitch >= 48.0, pitch
    blocks = {block.id: block for block in built.elements(Massing) if block.id}
    assert not [i for i in blocks if i.startswith(("windows_shutter", "windows_sign"))]
    # Exactly one framed opening: one glass screen, two mullions at its sides.
    assert [i for i in blocks if i.startswith("windows_screen")] == ["windows_screen"]
    mullions = sorted(i for i in blocks if i.startswith("windows_mullion"))
    assert mullions == ["windows_mullion_0", "windows_mullion_1"]
    y0, y1 = window_opening(FIXTURE)
    assert y0 < window_y(FIXTURE) < y1 and y1 - y0 >= 48.0
    screen = blocks["windows_screen"].bounds
    assert (screen.mins.y, screen.maxs.y) == pytest.approx((y0, y1))
    # The partition covers the rest of the run and never the opening.
    face_x, _back_x, run_y0, run_y1 = counter_run(FIXTURE)
    parts = [b.bounds for i, b in blocks.items() if i.startswith("windows_partition_")]
    assert parts
    for box in parts:
        assert box.maxs.y <= y0 or box.mins.y >= y1, box
    covered = sum(box.maxs.y - box.mins.y for box in parts)
    assert covered == pytest.approx((run_y1 - run_y0) - (y1 - y0) - 2 * FIXTURE.mullion_width)
    # The clerk's side of the one window is lit.
    assert built.find("windows_clerk_light") is not None
    # The wall buy is on solid partition, one bay short of the window, and
    # its prompt names no window.
    assert "WINDOW" not in PROMPTS["smg_standard"]
    assert FIXTURE.wallbuy_bay != FIXTURE.window_bay
    buy = built.find("windows_wallbuy")
    assert buy.position.y == pytest.approx(centres[FIXTURE.wallbuy_bay - 1])
    assert not y0 <= buy.position.y <= y1


def test_the_counter_has_a_public_side_and_a_staff_side_and_a_lowered_section(
    built,
) -> None:
    """Two tiers and a dip, and where each number came from.

    The staff work surface is 28.5, which is measured: UC Berkeley's customer
    service counter design guidelines, "Fixed work surface height at 28.5"
    with an unobstructed 27.5" floor to under counter height".  The lowered
    patron section is ``ada_section_length`` long, which is ADA 904.4.1's "a
    portion of the counter surface that is 36 inches (915 mm) long minimum".
    Its *height* is not the code's 36: 36 is under the engine's 39-unit jump,
    so the map is one unit over and the compromise is pinned here so nobody
    reads 40 as a sourced number.
    """
    face_x, back_x, _y0, _y1 = counter_run(FIXTURE)
    ledge = built.find("windows_counter").bounds
    worktop = built.find("windows_worktop").bounds
    floor = built.find("windows_room").floor_z
    assert ledge.mins.x == pytest.approx(face_x)
    assert ledge.maxs.x - ledge.mins.x == pytest.approx(FIXTURE.patron_ledge_depth)
    assert ledge.maxs.z - floor == pytest.approx(FIXTURE.counter_height)
    assert worktop.mins.x == pytest.approx(ledge.maxs.x)
    assert worktop.maxs.x == pytest.approx(back_x)
    assert worktop.maxs.z - floor == pytest.approx(28.5)
    dip = built.find("windows_counter_1").bounds
    assert dip.maxs.z - floor == pytest.approx(FIXTURE.ada_section_height)
    assert dip.maxs.y - dip.mins.y == pytest.approx(FIXTURE.ada_section_length)
    assert FIXTURE.ada_section_length == 36.0
    assert FIXTURE.ada_section_height == 40.0 > JUMP_UP


def test_the_waiting_room_seats_ten_in_rows_facing_the_counter(built) -> None:
    """Ten is PennDOT's number for a photo licence centre waiting area --
    "ten waiting chairs per camera system", co-location requirements 4.1.5 --
    and this branch has one camera.  Two rows of five, and every seat looks
    east at the counter run.
    """
    chairs = built.find("waiting_chairs")
    assert isinstance(chairs, PropScatter)
    assert len(chairs.props) == 10
    assert FIXTURE.chair_rows * FIXTURE.chair_cols == 10
    # Five abreast in each row, two rows deep: measured off the placements
    # rather than read off the loop that made them.
    rows = sorted({round(prop.origin.x, 3) for prop in chairs.props})
    assert len(rows) == FIXTURE.chair_rows, rows
    assert rows[1] - rows[0] == pytest.approx(FIXTURE.row_pitch)
    for row in rows:
        seats = sorted(
            prop.origin.y for prop in chairs.props
            if round(prop.origin.x, 3) == row
        )
        assert len(seats) == FIXTURE.chair_cols
        assert seats[1] - seats[0] == pytest.approx(FIXTURE.seat_pitch)
    assert all(prop.solid for prop in chairs.props)
    assert {prop.model for prop in chairs.props} == {"p7_chair_waiting_room_01_blue"}
    # And every one of them faces east, at the door to the service windows.
    # A chair's own front is -90 off its yaw, which is why this is measured
    # rather than read off the number in the file.
    from zmforge.recipes.props import MODEL_FRONT

    looks = {
        (prop.yaw + MODEL_FRONT[prop.model]) % 360.0 for prop in chairs.props
    }
    assert looks == {0.0}


def test_the_eye_chart_reads_downwards_in_five_sizes(built) -> None:
    """A white board on the eye room's north wall, and on it five rows of
    letters built from dark brushes, each row smaller and lower than the
    last, every brush on the board's face (a player could not find the
    Vision Test on the old chart of blank picture frames)."""
    from zmforge.recipes.dmv_rooms.eye import CHART_ROWS, chart_letters

    room = built.find("eye_exam_room")
    board = built.find("eye_chart").authored.box
    assert board.maxs.y == room.interior.maxs.y           # on the north wall
    assert board.mins.x > room.interior.mins.x and board.maxs.x < room.interior.maxs.x
    letters = chart_letters(room.interior, room.floor_z)
    assert "".join(l.char for l in letters) == "".join(t for t, _h in CHART_ROWS)
    rows = [[l for l in letters if l.row == r] for r in range(len(CHART_ROWS))]
    assert len(rows) == 5
    sizes = [row[0].height for row in rows]
    assert sizes == sorted(sizes, reverse=True) and len(set(sizes)) == 5
    tops = [row[0].z1 for row in rows]
    assert tops == sorted(tops, reverse=True)
    ink = [m for m in built.elements(Massing) if m.id.startswith("eye_chart_")]
    assert len(ink) == sum(len(l.boxes) for l in letters) >= 3 * len(letters)
    for m in ink:
        box = m.authored.box
        assert board.mins.x <= box.mins.x and box.maxs.x <= board.maxs.x
        assert board.mins.z <= box.mins.z and box.maxs.z <= board.maxs.z
        assert box.maxs.y == board.mins.y                 # on the board's face
        assert m.authored.materials.per_side[Side.SOUTH].name == "t7_plastic_rubber_trim"
    assert (built.find("eye_chart").authored.materials.per_side[Side.SOUTH].name
            == "t7_plastic_molding_trim_white")


def test_every_kit_prop_is_solid_and_carries_a_box_to_cut_a_collmap_from(built) -> None:
    """The donuts.  A kit prop placed hollow writes ``no_collmap 1`` over a
    model this project builds a collmap for, which ``Z21`` reports."""
    kit = [
        prop
        for scatter in built.elements(PropScatter)
        for prop in scatter.props
        if prop.model.startswith("zmf_prop_")
    ]
    assert kit, "the break room's donuts are gone"
    for prop in kit:
        assert prop.solid, prop.model
        assert prop.collision_box is not None, prop.model


def test_every_model_the_map_places_is_one_the_install_can_resolve(built) -> None:
    """An unverified model name costs a build to find out about."""
    ledger = load_ledger()
    if ledger is None:
        pytest.skip("no installed-assets ledger (src/zmforge/blueprint/installed_assets.json)")
    verdicts = {
        prop.model: judge_misc_model(prop.model, ledger)
        for scatter in built.elements(PropScatter)
        for prop in scatter.props
        if not prop.dynamic
    }
    assert verdicts, "no props were placed"
    assert {name: verdict for name, verdict in verdicts.items() if verdict != "ok"} == {}


def test_the_photo_booth_flashes_only_the_player_who_stepped_in(committed) -> None:
    """The flash is the gag and a broadcast flash would be the bug.

    A white flash threaded on ``level`` re-threads itself onto every
    player, which is that bug.  This one is the
    teleporter's own ceremony, which is called on the player the pad caught.
    """
    server = committed["server"]
    body = server[server.index("function zmf_teleport_player_booth()") :]
    body = body[: body.index("\n}\n") + 2]
    assert 'self thread hud::fade_to_black_for_x_sec( 0, 0.3, 0, 0.5, "white" );' in body
    assert "self playsoundtoplayer(" in body
    for broadcast in ("getplayers(", "level.players", "level thread lui", "level notify"):
        assert broadcast not in body, broadcast


def test_the_map_carries_its_own_words_and_nobody_else_s(built, committed) -> None:
    strings = committed["strings"]
    assert "TAKE A NUMBER" in strings
    # four buys, two perks of our own, the ticket dispenser's three lines,
    # each notice's prompt and replies, and the on-screen gags
    from zmforge.recipes.dmv import GAG_LINES

    notices = sum(1 + len(replies) for _prompt, replies in _all_notice_lines().values())
    # and the ending's lines (zmforge.recipes.dmv_quest)
    from zmforge.recipes.dmv import lot_walk
    from zmforge.recipes.dmv_quest import register_quest
    from zmforge.script.quest import gate_quest, quest_strings

    keys = {"lot": "lot_room", "entry": "entry_room", "waiting": "waiting_room",
            "windows": "windows_room", "eye": "eye_exam_room", "photo": "photo_room",
            "break": "break_room", "records": "records_room", "queue": "queue_room",
            "office": "office_room"}
    rooms = {key: built.find(rid) for key, rid in keys.items()}
    quest = register_quest(FIXTURE, rooms, walk_top=lot_walk(FIXTURE, rooms["lot"])[0])
    # as installed: each step behind a door carries its find line (P8)
    quest = gate_quest(built, quest)
    # plus the six gamble machine lines (Z87) and the GobbleGum
    # gate's one (script.gobblegum), which every map carries
    machines = sum(1 for line in strings.splitlines()
                   if line.startswith("REFERENCE")
                   and line.split()[-1].startswith(("ZMF_GAMBLE_", "ZMF_BGB_")))
    assert machines == 7
    assert strings.count("REFERENCE") == (len(PROMPTS) + 2 + len(TICKET_LINES) + notices
                                          + len(GAG_LINES) + len(quest_strings(quest))
                                          + machines)


def test_the_kiosk_hands_out_tickets_and_the_window_calls_them(committed) -> None:
    """Take a number: the kiosk by the front door hands
    out tickets 1-10; from round 5 the PA calls one a minute and the holder
    has TICKET_GRACE_SECONDS to reach the service window.  Every line is the map's own,
    precached, on a trigger the script spawns -- no Lua, no literal prompt."""
    from zmforge.recipes.dmv import (
        TICKET_CALL_SECONDS, TICKET_GRACE_SECONDS, TICKET_NUMBERS, TICKET_OPEN_ROUND,
        ticket_lines,
    )

    strings, server = committed["strings"], committed["server"]
    assert (TICKET_NUMBERS, TICKET_CALL_SECONDS, TICKET_GRACE_SECONDS, TICKET_OPEN_ROUND) == (
        10, 60.0, 3.0, 5)
    lines = ticket_lines(FIXTURE)
    for key, text in lines.items():
        kind = "triggerstring" if key in ("prompt", "number") else "string"
        assert f'#precache( "{kind}", "ZM_DMV_TICKET_{key.upper()}" );' in server, key
        assert text in strings, key
        assert "{" not in text.replace("{+activate}", ""), key   # every hole filled
    assert "NOW SERVING NUMBER ^3&&1^7" in lines["call"]
    assert "THAT'S YOU" in lines["you"] and "WINDOW" in lines["you"]
    # One window, so no line names a window number.
    for key, text in lines.items():
        assert not re.search(r"\bWINDOW\s+\d", text, re.I), (key, text)
    assert "given to the next person" in lines["missed"]
    assert "No one? Next!" in lines["no_one"]
    assert "Your paperwork has been processed." in lines["served"]
    assert "round 5" in lines["yours_early"]
    assert 'spawn( "trigger_radius_use"' in server
    assert 'SetHintString( &"ZM_DMV_TICKET_NUMBER", e_who.zmf_my_ticket );' in server
    assert "for ( n = 1; n <= 10; n++ )" in server
    caller = server[server.index("function zmf_ticket_caller("):]
    assert "while ( level.round_number < 5 )" in caller
    assert "\tn_wait = 60;" in caller and "\twait n_wait;" in caller
    assert "n_end = gettime() + 3000;" in caller
    # No call before the window's room is open.
    assert 'while ( !zm_zonemgr::zone_is_enabled( "windows" ) )' in caller


def test_every_wall_fixture_looks_out_of_the_wall_it_is_fixed_to(built) -> None:
    """A sign facing along its own wall is a sign nobody reads.

    Ten of eleven wall buys once shipped facing their own walls (``Z23``), and
    a fixture is the same mistake with nothing to catch it: no check asks
    which way a clock looks.  So the recipe subtracts the model's own front
    (:func:`zmforge.recipes.props._mount_face`) and this measures the result:
    for every wall-mounted prop in the map, the direction it actually looks is
    the direction away from the nearest wall face.
    """
    from zmforge.recipes.props import MOUNT_WALL, _mount_face, mount_kind

    fixtures = [
        prop
        for scatter in built.elements(PropScatter)
        for prop in scatter.props
        if mount_kind(prop.model) == MOUNT_WALL
    ]
    assert len(fixtures) >= 12, len(fixtures)
    # Three of them are not on a wall of a room at all: the NOW SERVING board
    # and the two closed-window plates hang on the counter run, which stands
    # across the middle of the counter hall.  Their wall is the counter's own
    # public face, so they are measured against that instead -- they all have
    # to look west, out of it, at the chairs.
    face_x, _back_x, run_y0, run_y1 = counter_run(FIXTURE)
    on_the_counter = [
        prop for prop in fixtures
        if face_x - 16.0 <= prop.origin.x <= face_x + FIXTURE.patron_ledge_depth
        and run_y0 <= prop.origin.y <= run_y1
    ]
    assert len(on_the_counter) == 3, [prop.model for prop in on_the_counter]
    for prop in on_the_counter:
        assert (prop.yaw + _mount_face(prop.model)) % 360.0 == pytest.approx(180.0), (
            prop.model, prop.origin
        )
    fixtures = [prop for prop in fixtures if prop not in on_the_counter]
    rooms = built.elements(Room)
    for prop in fixtures:
        room = min(
            rooms,
            key=lambda r: max(
                r.interior.mins.x - prop.origin.x,
                prop.origin.x - r.interior.maxs.x,
                r.interior.mins.y - prop.origin.y,
                prop.origin.y - r.interior.maxs.y,
            ),
        )
        inside = room.interior
        gaps = {
            0.0: prop.origin.x - inside.mins.x,     # west wall: look east
            180.0: inside.maxs.x - prop.origin.x,   # east wall: look west
            90.0: prop.origin.y - inside.mins.y,    # south wall: look north
            270.0: inside.maxs.y - prop.origin.y,   # north wall: look south
        }
        away = min(gaps, key=lambda heading: gaps[heading])
        looks = (prop.yaw + _mount_face(prop.model)) % 360.0
        assert looks == pytest.approx(away), (
            f"{prop.model} at {prop.origin} looks {looks:g}, not {away:g} "
            f"(out of {room.id}'s nearest wall)"
        )


# --------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------
#: Floor, wall and ceiling per room, as the recipe means them.  Spelled out
#: here rather than read back off :data:`~zmforge.recipes.dmv.SKINS`, which
#: would only prove the recipe equals itself: this is the table in the
#: module docstring's sense, and changing what a room is made of is a
#: decision somebody takes in two places.
#:
#: **Nobody has seen any of this in game.**  These are the names the ``.map``
#: carries, not a judgement about how the building looks.
EXPECTED_SKINS = {
    #                   floor                               wall                              ceiling
    # Outside.  The ceiling name is carried but never laid: the car park has
    # no roof, and what is over it is the enclosure's sky.
    "lot_room": ("t7_asphalt_advanced_strips", "t7_concrete_slabs_interlocked", "t7_asphalt_advanced_strips"),
    "entry_room": ("t7_stone_travertine_tiles", "t7_plaster_smooth_light_01", "t7_plastic_panels_white"),
    "waiting_room": ("t7_linoleum_floor_tile_square", "t7_concrete_worn_painted_white", "t7_plastic_panels_white"),
    "windows_room": ("t7_ceramic_tiles_16x16", "t7_plaster_smooth_light_01", "t7_plastic_panels_white"),
    "eye_exam_room": ("t7_ceramic_tile_large_white", "t7_plaster_smooth_light_01", "t7_metal_panel_white_perforated"),
    "photo_room": ("t7_linoleum_floor_tile_square", "t7_metal_panel_horizontal_painted", "t7_metal_panel_white_perforated"),
    "break_room": ("t7_ceramic_tiles_6x6_dirty_01", "t7_ceramic_tile_shower_white", "t7_plastic_ceiling_corrugated_panel"),
    "records_room": ("t7_concrete_tiles_2x2_dirty_01", "t7_brick_worn_heavy_grout_red", "t7_metal_rust_ceiling_01"),
    "queue_room": ("t7_linoleum_floor_tile_square", "t7_plaster_smooth_dirty_01", "t7_plastic_panels_white"),
    "office_room": ("t7_concrete_pebbles_cracked", "t7_concrete_worn_painted_white", "t7_metal_panel_white_perforated"),
}


def test_each_room_is_laid_in_the_surfaces_the_recipe_chose(built) -> None:
    """Every room carries its own skin, and the table above is that skin."""
    rooms = {room.id: room for room in built.elements(Room)}
    assert set(rooms) == set(EXPECTED_SKINS), sorted(rooms)
    for room_id, (floor, wall, ceiling) in EXPECTED_SKINS.items():
        skin = rooms[room_id].materials
        assert skin.floor.name == floor, room_id
        assert skin.wall.name == wall, room_id
        assert skin.ceiling.name == ceiling, room_id


def test_no_two_rooms_are_the_same_three_surfaces(built) -> None:
    """The reason the skins exist.

    The default shell is one wall, one floor and one ceiling for the whole
    map, and ten rooms built out of it are ten photographs of the same
    room.  A surface is the cheapest thing that tells a player where they
    are, so no two rooms may share all three -- and because the catalogue is
    twelve materials wide, several rooms share two of them and are told
    apart by the third.
    """
    seen: dict[tuple[str, str, str], str] = {}
    for room in built.elements(Room):
        skin = room.materials
        key = (skin.floor.name, skin.wall.name, skin.ceiling.name)
        assert key not in seen, f"{room.id} is {seen[key]} again: {key}"
        seen[key] = room.id


def test_the_counters_are_laminate_on_panelling_behind_glass(built) -> None:
    """What a government office is made of at the places you touch it.

    Both counters carry a laminate top on a panelled public face, the staff
    work surface the same laminate on a steel carcass, the screen over the
    service window and the operator's transom are glass, the counter wall
    either side of the window is plaster and the rope line is black belts on clip.  These are the surfaces a player
    stands a foot from, so they are pinned by name.
    """
    blocks = {block.id: block for block in built.elements(Massing)}
    laminate = "t7_wood_veneer_sugarpine_matte"
    panelling = "t7_wood_panel_01"
    glass = "t7_glass_plain_opaque"

    def faces(block_id):
        laid = blocks[block_id].authored.materials
        return {side: laid.on(side).name for side in Side}

    for block_id in ("windows_counter", "office_counter"):
        sides = faces(block_id)
        assert sides[Side.TOP] == laminate, (block_id, sides)
        assert panelling in sides.values(), (block_id, sides)
    assert faces("windows_worktop")[Side.TOP] == laminate
    for block_id in ("windows_screen", "office_transom"):
        assert set(faces(block_id).values()) == {glass, "caulk"}, block_id
    # The partition either side of the one window: plaster to the hall.
    partitions = [i for i in blocks if i.startswith("windows_partition_")]
    assert partitions
    for block_id in partitions:
        assert faces(block_id)[Side.WEST] == "t7_plaster_smooth_light_01", block_id
    assert not [i for i in blocks if i.startswith("windows_shutter")]
    rails = [
        block for block_id, block in blocks.items() if block_id.startswith("queue_rail")
    ]
    assert rails, sorted(blocks)
    # The rope line (bare poles do not read as a waiting line): each
    # rail is an invisible clip, and what a player sees is black belts
    # strung post to post along its middle, every one inside the rail.
    for index, rail in enumerate(rails):
        assert {face.material.name for face in rail.solids[0].faces} == {"clip"}, rail.id
        belts = [b for block_id, b in blocks.items()
                 if block_id.startswith(f"queue_belt_{index}_")]
        assert len(belts) >= 5, rail.id
        box = rail.authored.box
        for belt in belts:
            names = {face.material.name for face in belt.solids[0].faces}
            assert "t7_plastic_rubber_trim" in names, belt.id
            b = belt.authored.box
            assert box.mins.y <= b.mins.y and b.maxs.y <= box.maxs.y, belt.id
            assert box.mins.x <= b.mins.x and b.maxs.x <= box.maxs.x, belt.id


def test_every_surface_this_map_lays_is_one_the_install_can_compile(built) -> None:
    """A material outside the known-clean catalogue is a build spent to find
    out: the compiler prints ``WARNING: Material '<name>' is missing``, exits
    0, and the surface renders as the error texture (spec 2.9).  Checking it
    here is the cheap half of the same measurement ``Z12`` makes.
    """
    names = set()
    for room in built.elements(Room):
        names |= room.materials.names()
    for block in built.elements(Massing):
        for solid in block.solids:
            names |= {face.material.name for face in solid.faces}
    assert names, "the map lays no surfaces at all"
    uncatalogued = sorted(name for name in names if not is_catalogued(name))
    assert uncatalogued == [], uncatalogued
    assert names - TOOL_MATERIALS, "every surface is a tool material"


def test_the_back_office_is_the_only_carpeted_floor(built) -> None:
    """Carpet is behind the counter, where a real branch puts it, and the
    public floors are hard: linoleum, ceramic and stone tile.  The carpet is
    the speckled concrete laid at 32 units so the grain reads as fleck --
    the size is as much of the choice as the name, so it is pinned with it.
    """
    carpet = "t7_concrete_pebbles_cracked"
    carpeted = [
        room.id for room in built.elements(Room) if room.materials.floor.name == carpet
    ]
    assert carpeted == ["office_room"], carpeted
    assert SKINS["office_room"].floor.scale == 32.0


#: Tool surfaces are not art: they are what the compiler draws nothing on.
_ART_EXCLUDED = TOOL_MATERIALS


def _art_faces(document) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity in document.entities:
        for solid in entity.solids:
            for facet in getattr(solid, "facets", ()):
                if facet.material in _ART_EXCLUDED:
                    continue
                counts[facet.material] = counts.get(facet.material, 0) + 1
    return counts


def test_the_building_is_dressed_in_many_surfaces_and_none_dominates(committed) -> None:
    """No single surface dominates the building, so it does not read as plain.

    Measured on an earlier build of this map: nine art materials, and trowelled
    concrete, dark concrete and iron were 666 of 787 art faces.  Counted
    here the same way -- brush faces in the written ``.map`` by material,
    tool surfaces left out -- the building now lays at least fifteen
    distinct surfaces and none of them is more than a quarter of the faces.
    """
    counts = _art_faces(committed["document"])
    total = sum(counts.values())
    assert len(counts) >= 15, sorted(counts)
    worst = max(counts, key=counts.get)
    assert counts[worst] / total <= 0.25, (worst, counts[worst], total)
    # The three that made the earlier build grey are minor.
    grey = sum(counts.get(name, 0) for name in (
        "t7_concrete_trowelled", "t7_concrete_wall_dark_01", "t7_metal_worn_iron_dark"))
    assert grey / total < 0.1, (grey, total)


def test_every_roofed_room_has_trim_and_light_fittings(built) -> None:
    """No plain boxes: a rubber base along the walls, a moulding at the
    ceiling, a frame round every doorway and a grid of 2x4 fittings."""
    blocks = {block.id for block in built.elements(Massing)}
    for key in ("entry", "waiting", "windows", "eye", "photo", "break",
                "records", "queue", "office"):
        assert any(b.startswith(f"{key}_skirting_") for b in blocks), key
        assert sum(b.startswith(f"{key}_cornice_") for b in blocks) == 4, key
        assert any(b.startswith(f"{key}_door_head_") for b in blocks), key
        assert any(b.startswith(f"{key}_light_") for b in blocks), key


def test_the_frontage_is_a_facade_and_not_a_wall(built) -> None:
    """The car park's east wall is the branch's street face: red brick over
    a concrete base band, pilasters, four framed windows, a sign band over
    the canopy, a cornice and a coping on every wall of the site."""
    blocks = {block.id: block for block in built.elements(Massing)}
    lot = next(room for room in built.elements(Room) if room.id == "lot_room")
    assert lot.materials.for_side(Side.EAST).name == "t7_brick_worn_red"
    assert sum(b.startswith("lot_pilaster_") for b in blocks) == 4
    assert sum(b.endswith("_glass") and b.startswith("lot_window_") for b in blocks) == 4
    assert any(b.startswith("lot_base_band_") for b in blocks)
    assert {"lot_sign_band", "lot_cornice"} <= set(blocks)
    assert sum(b.startswith("lot_coping_") for b in blocks) == 4
    footway = blocks["lot_footway"].authored.materials
    assert footway.on(Side.TOP).name == "t7_concrete_sidewalk_2x2_01"
    assert footway.on(Side.WEST).name == "t7_street_concrete_curb_01a"

# --------------------------------------------------------------------------
# Outside: the car park, and the walk in
# --------------------------------------------------------------------------
def test_the_map_starts_outside_and_the_front_door_is_the_first_one(
    built, flood
) -> None:
    """You spawn on the asphalt, not in the lobby.

    Three measurements: the player start is in the car park and not in any
    roofed room, the only door out of the car park is the one into the entry
    lobby, and there is something to buy out there -- a spawn with nothing on
    its walls is a round spent running.
    """
    lot = built.find("lot_room")
    start = built.find("player_start").position
    inside_lot = lot.interior
    assert inside_lot.mins.x <= start.x <= inside_lot.maxs.x, start
    assert inside_lot.mins.y <= start.y <= inside_lot.maxs.y, start
    assert built.zone_of_point(start).name == "lot"
    assert lot.roofed is False
    # It is a car park and not a yard: the start stands in the drive aisle,
    # a full stall's depth back from the footway.
    assert lot.interior.maxs.x - start.x > FIXTURE.walk_depth + FIXTURE.stall_depth
    out = [
        door for door in built.elements(Door)
        if "lot" in (door.zone_a, door.zone_b)
    ]
    assert [door.id for door in out] == ["door_lot_entry"]
    assert {door.zone_a for door in out} | {door.zone_b for door in out} == {
        "lot", "entry"
    }
    buys = [
        element.id for element in built.elements(WallWeapon)
        if built.zone_of_point(element.position).name == "lot"
    ]
    assert buys == ["lot_wallbuy"]


def test_the_car_park_is_striped_into_bays_with_the_accessible_pair_by_the_walk(
    built,
) -> None:
    """The bays, and which numbers in them are sourced.

    **They are not.**  A 9 x 18 ft bay, a 24 ft aisle and an 8 ft accessible
    bay with an 8 ft access aisle are the assumed figures -- no published
    source was found that fixes bay sizes for a motor vehicle branch -- so
    what this pins is that the map is consistent with what it says it
    assumed, and that the two accessible bays are the two nearest the door.
    """
    bays = parking_bays(FIXTURE)
    kinds = {kind for kind, *_ in bays}
    assert kinds == {"standard", "accessible", "aisle"}
    accessible = [bay for bay in bays if bay[0] == "accessible"]
    aisles = [bay for bay in bays if bay[0] == "aisle"]
    assert len(accessible) == len(aisles) == 2
    for _kind, _x0, _x1, y0, y1 in accessible:
        assert y1 - y0 == pytest.approx(FIXTURE.accessible_stall_width)
    for _kind, _x0, _x1, y0, y1 in aisles:
        assert y1 - y0 == pytest.approx(FIXTURE.access_aisle_width)
    for _kind, x0, x1, y0, y1 in bays:
        assert x1 - x0 == pytest.approx(FIXTURE.stall_depth)
        if _kind == "standard":
            assert y1 - y0 == pytest.approx(FIXTURE.stall_width)
    # The accessible pair is nearest the covered walk: nothing else in the
    # near row is closer to the centre line than they are.
    walk = FIXTURE.canopy_width / 2.0
    near_row = max(x0 for _k, x0, _x1, _y0, _y1 in bays)
    near = [bay for bay in bays if bay[1] == near_row and bay[0] != "aisle"]
    closest = min(abs((y0 + y1) / 2.0) for _k, _x0, _x1, y0, y1 in near)
    for kind, _x0, _x1, y0, y1 in near:
        if abs((y0 + y1) / 2.0) == closest:
            assert kind == "accessible", (kind, y0, y1)
    assert closest > walk
    # And every bay edge is actually painted on the ground.
    lines = [
        block for block in built.elements(Massing)
        if block.id.startswith("lot_bay_line_")
    ]
    assert len(lines) >= len(bays)
    for line in lines:
        box = line.bounds
        assert box.maxs.y - box.mins.y == pytest.approx(FIXTURE.stripe_width)
        assert box.maxs.z - box.mins.z == pytest.approx(FIXTURE.stripe_height)


def test_the_outside_is_sealed_and_the_round_arrives_in_it(built, flood) -> None:
    """A car park is a room like any other: one hole in it, spawners in it,
    and every corner of it standing room the player reaches.
    """
    lot = built.find("lot_room")
    # One hole in the shell, and it is the front door.
    assert len(lot.apertures) == 1
    assert lot.apertures[0].side is Side.EAST
    risers = [
        spawn for spawn in built.elements(Spawn) if spawn.zone_name == "lot"
    ]
    assert len(risers) == 3, [spawn.id for spawn in risers]
    inside = lot.interior
    walk_top = lot.floor_z + FIXTURE.kerb_height
    corners = [
        Point(inside.mins.x + 96.0, inside.mins.y + 96.0, walk_top),
        Point(inside.mins.x + 96.0, inside.maxs.y - 96.0, walk_top),
        Point(inside.maxs.x - 96.0, 0.0, walk_top),
        Point(inside.centre.x, inside.maxs.y - 96.0, lot.floor_z),
    ]
    for point in corners:
        assert flood.under(point.x, point.y, point.z + 4.0,
                           only_reached=True) is not None, point


def test_the_back_of_house_is_all_on_the_staff_side_of_the_counter(built) -> None:
    """Which doors are behind the counter and which are in front of it.

    This is the whole architectural claim, measured: the two rooms a customer
    is sent to open off the public floor, and the secure store and the staff
    break room open off the staff floor -- so the only way to any of the back
    of house is round the end of the counter run, past the sign.  The break
    room used to hang off the waiting room, which put the building's power
    switch in the public half.
    """
    face_x, back_x, _y0, _y1 = counter_run(FIXTURE)
    windows = built.find("windows_room")
    sides = {}
    for index in range(len(windows.apertures)):
        box = windows.opening(index).box
        sides[round(box.centre.x, 1), round(box.centre.y, 1)] = box
    doors = {door.id: door for door in built.elements(Door)}
    public, staff = [], []
    for door_id, room, opening in (
        ("door_waiting_windows", "windows_room", 0),
        ("door_windows_eye_exam", "eye_exam_room", 0),
        ("door_windows_records", "records_room", 0),
        ("door_windows_break", "break_room", 0),
    ):
        assert door_id in doors, sorted(doors)
        centre = built.find(room).opening(opening).box.centre
        (public if centre.x < face_x else staff).append(door_id)
    assert sorted(public) == ["door_waiting_windows", "door_windows_eye_exam"]
    assert sorted(staff) == ["door_windows_break", "door_windows_records"]
    # And the power switch is in the break room: behind the counter, not in
    # the public half.
    switch = built.elements(PowerSwitch)[0]
    assert built.zone_of_point(switch.position).name == "breakroom"
    assert switch.position.x > back_x


# --------------------------------------------------------------------------
# Lighting: the car park is lit by the sun, the building by its lamps
# --------------------------------------------------------------------------
def test_the_car_park_is_sunlit_and_carries_no_fill_lamps(built) -> None:
    # Sixty radius-512 fill lamps at full exposure on top of default_day's
    # sun make the lot far too bright, and only outside.
    from zmforge.blueprint.elements import Lamp, Room

    rooms = {room.id: room for room in built.elements(Room)}
    lot = rooms["lot_room"]
    assert lot.sunlit and not lot.roofed
    in_lot = [
        lamp for lamp in built.elements(Lamp)
        if lot.interior.holds(lamp.position, tolerance=-1e-9)
    ]
    assert in_lot == []
    # Every roofed room still gets its lamps.
    for room in rooms.values():
        if room.roofed:
            assert any(
                room.interior.holds(lamp.position, tolerance=-1e-9)
                for lamp in built.elements(Lamp)
            ), room.id


def test_only_an_unroofed_room_may_be_sunlit() -> None:
    from zmforge.blueprint.model import Blueprint
    from zmforge.errors import BlueprintError
    from zmforge.spatial import Span

    bp = Blueprint("zm_sunlit_probe")
    with pytest.raises(BlueprintError):
        bp.add_room(Span.between((0, 0, 0), (256, 256, 128)), sunlit=True)


# ---------------------------------------------------------------------------
# Lived in: the second furnishing pass
# ---------------------------------------------------------------------------

#: The floor under which a room reads as a set rather than a workplace, against
#: a target of 50-100 props a room (``recipes/dmv_rooms``).  139 props across
#: the map reads too sparse for an office, so every room is pinned a little
#: under what it carries, and taking a room's dressing out is a decision this
#: test makes somebody write down.
MIN_PROPS_PER_ROOM = {
    "lot_room": 95,
    "entry_room": 90,
    "waiting_room": 95,
    "windows_room": 100,
    "eye_exam_room": 55,
    "photo_room": 50,
    "break_room": 60,
    "records_room": 95,
    "queue_room": 75,
    "office_room": 95,
}


def _props_by_room(built) -> dict[str, list]:
    """Every placed prop, filed under the room its *footprint* centre is in
    (not its origin: half the palette draws off to one side of it)."""
    from zmforge.placement.relations import Placed
    from zmforge.recipes.props import collision_box

    rooms = list(built.elements(Room))
    out: dict[str, list] = {room.id: [] for room in rooms}
    for scatter in built.elements(PropScatter):
        if scatter.id.endswith("_closet"):
            continue  # a barricade window's closet, outside every room (Z85)
        for prop in scatter.props:
            box = collision_box(prop.model)
            assert box is not None, prop.model
            placed = Placed.from_model(
                prop.model, box, (prop.origin.x, prop.origin.y, prop.origin.z),
                prop.yaw, prop.scale, solid=prop.solid, ident=prop.id,
            )
            home = [
                room.id for room in rooms
                if room.interior.mins.x - 4.0 <= placed.x <= room.interior.maxs.x + 4.0
                and room.interior.mins.y - 4.0 <= placed.y <= room.interior.maxs.y + 4.0
            ]
            assert len(home) == 1, (prop.model, placed.x, placed.y, home)
            out[home[0]].append(prop)
    return out


def test_every_room_is_furnished_like_a_working_office(built) -> None:
    by_room = _props_by_room(built)
    counts = {room: len(props) for room, props in by_room.items()}
    assert set(counts) == set(MIN_PROPS_PER_ROOM)
    short = {room: (counts[room], floor) for room, floor in MIN_PROPS_PER_ROOM.items()
             if counts[room] < floor}
    assert short == {}, counts
    # Density (``recipes/dmv_rooms``): every room over a hundred props and
    # none past the ~300 a big room is filled to.
    # The shelf-board fill (props.SHELF_BOARDS) puts 165 files on the
    # fourteen inner boards of the records room's two shelving units, so
    # that room alone is allowed to ~450; nothing it adds is on the floor.
    assert min(counts.values()) >= 100, counts
    assert counts["records_room"] <= 450, counts
    assert max(v for room, v in counts.items() if room != "records_room") <= 310, counts
    assert sum(counts.values()) >= 2000, counts


def test_the_staff_side_and_the_break_room_have_what_people_use(built) -> None:
    """A terminal, a mug and paperwork on every workstation; a fridge, a
    coffee maker and a water cooler where the staff take their break."""
    by_room = {room: [prop.model for prop in props]
               for room, props in _props_by_room(built).items()}
    windows = by_room["windows_room"]
    assert windows.count("p7_desk_metal_old_01_body") == 4
    for model in ("p7_keyboard_metal_tech", "p7_cup_coffee_mug", "p7_office_paper_stack_sml"):
        assert windows.count(model) >= 4, model
    assert windows.count("p7_file_cab_metal_02") >= 4
    kitchen = by_room["break_room"]
    for model in ("p7_cai_fridge_metal_plant", "p7_coffee_maker_digital",
                  "p7_water_cooler_digital_body", "p7_cai_work_table_metal_03_white"):
        assert model in kitchen, model
    assert kitchen.count("p7_chair_lab_01") >= 4
    waiting = by_room["waiting_room"]
    assert waiting.count("p7_chair_waiting_room_01_blue") >= 19
    assert waiting.count("p7_handrail_post_middle") >= 8
    assert "p7_water_cooler_digital_body" in waiting
    lot = by_room["lot_room"]
    assert lot.count("p7_3arc_park_pylon") >= 8
    assert lot.count("p7_bench_modern_01") >= 2


def test_every_stanchion_line_is_belted_and_cannot_be_hopped(built) -> None:
    """Bare poles do not read as a waiting line.  Every line of stanchion posts outside the queue
    (the queue's are pinned with its rails) carries a belt between each
    pair of neighbours, just under the post tops, and a clip behind it taller
    than the jump."""
    from zmforge.recipes.dmv import BELT_BOTTOM, BELT_CLIP_HEIGHT, BELT_TOP
    from zmforge.verify.reachability import JUMP_UP

    blocks = {block.id: block for block in built.elements(Massing)}
    lines = {"waiting_belt_0": 4, "waiting_belt_1": 4, "entry_belt_0": 2,
             "entry_belt_1": 2, "eye_belt": 2}
    for ident, belts in lines.items():
        found = [b for i, b in blocks.items() if i.startswith(f"{ident}_") and i[-1].isdigit()]
        assert len(found) == belts, (ident, sorted(b.id for b in found))
        clip = blocks[f"{ident}_clip"]
        assert {f.material.name for f in clip.solids[0].faces} == {"clip"}
        floor = clip.authored.box.mins.z
        assert clip.authored.box.maxs.z - floor == BELT_CLIP_HEIGHT > JUMP_UP
        for belt in found:
            box = belt.authored.box
            assert (box.mins.z - floor, box.maxs.z - floor) == (BELT_BOTTOM, BELT_TOP)


def test_desk_clutter_stands_on_its_desk_and_is_not_an_obstacle(built) -> None:
    """Every small thing the second pass put on a surface is hollow and
    rests exactly on that surface's top, not in it and not above it."""
    from zmforge.recipes.props import collision_box

    clutter = {"p7_keyboard_metal_tech", "p7_cup_coffee_mug", "p7_office_paper_stack_sml",
               "p7_office_paper_folder_pink", "p7_coffee_maker_digital",
               "p7_water_cooler_digital_bottle"}
    floor = 16.0
    tops = {floor + FIXTURE.staff_surface_height, floor + FIXTURE.counter_height}
    for surface in ("p7_desk_metal_old_01_body", "p7_zm_der_cabinet_lab_bottom",
                    "p7_cai_work_table_metal_03_white", "p7_water_cooler_digital_body"):
        (_x0, _y0, z0), (_x1, _y1, z1) = collision_box(surface)
        tops.add(floor + z1 - z0)
    seen = 0
    for scatter in built.elements(PropScatter):
        if not scatter.id.endswith("_lived_in"):
            continue
        for prop in scatter.props:
            if prop.model not in clutter:
                continue
            seen += 1
            assert not prop.solid, prop.model
            bottom = prop.origin.z + collision_box(prop.model)[0][2] * prop.scale
            assert any(abs(bottom - top) < 0.01 for top in tops), (prop.model, bottom)
    assert seen >= 30


# --------------------------------------------------------------------------
# After the outbreak: the set pieces and the notices
# --------------------------------------------------------------------------
import re as _re

_NOTICE_CALL = _re.compile(
    r'level thread zmf_notice\( \( (-?[\d.]+), (-?[\d.]+), (-?[\d.]+) \), '
    r'&"ZM_DMV_NOTICE_([A-Z0-9_]+)", a_lines_\d+ \);'
)


def _notices(committed) -> list[tuple[str, Point]]:
    return [
        (key.lower(), Point(float(x), float(y), float(z)))
        for x, y, z, key in _NOTICE_CALL.findall(committed["server"])
    ]


def _all_notice_lines() -> dict:
    """NOTICE_LINES plus the dense pass's per-room notices (``dmv_rooms``)."""
    from zmforge.recipes.dmv_rooms import dense_notice_lines

    return {**NOTICE_LINES, **dense_notice_lines()}


def _character(built, room: str) -> list:
    return [prop for prop in built.find(f"{room}_character").props]


def test_every_notice_is_hung_and_says_its_own_words(committed) -> None:
    """Each joke in NOTICE_LINES is a use trigger the server script spawns,
    with a precached prompt and replies that are the map's own strings."""
    server, strings = committed["server"], committed["strings"]
    notices = _notices(committed)
    keys = [key for key, _point in notices]
    lines = _all_notice_lines()
    assert set(keys) == set(lines)
    # One notice per joke: there are no per-window POSITION CLOSED notices,
    # because there are no extra windows.
    assert "closed_window" not in keys
    assert len(notices) == len(lines)
    assert server.count("level thread zmf_notices();") == 1
    assert 'spawn( "trigger_radius_use", v_origin, 0, ' in server
    for key, (prompt, replies) in lines.items():
        ref = f"ZM_DMV_NOTICE_{key.upper()}"
        assert f'#precache( "triggerstring", "{ref}" );' in server, key
        assert prompt in strings, key
        for index, line in enumerate(replies):
            assert f'#precache( "string", "{ref}_{index}" );' in server, (key, index)
            assert f'&"{ref}_{index}"' in server, (key, index)
            assert line in strings, (key, line)


def test_the_jokes_are_the_ones_that_were_asked_for() -> None:
    """The map's key joke lines, pinned so a rewrite keeps them."""
    said = {key: " / ".join((prompt,) + replies)
            for key, (prompt, replies) in NOTICE_LINES.items()}
    assert "Form 27-B: to request Form 27-A." in said["forms"]
    assert "SUGGESTION BOX" in said["suggestions"]
    assert said["now_serving"].startswith("SERVICE WINDOW")
    assert "3 seconds" in said["now_serving"]
    assert "Do not smile." in said["photo"]
    assert "Read the bottom line." in said["eye_test"]      # the shotgun reads it
    assert "R U N" in PROMPTS["shotgun_pump"]
    assert "OUT OF ORDER" in said["cooler"]
    assert "CLOSED" in said["queue_closed"] and "back" in said["queue_closed"]
    assert "846" in said["customer_846"]
    assert "MANAGER" in said["manager"]


def test_no_notice_stands_where_a_purchase_is_made(built, committed, flood) -> None:
    """Two use triggers in one player's reach show one prompt, and the loser
    might be a perk.  So every notice is at least 80 units from every perk,
    wall buy, box, switch, window barrier and the ticket machine, stands in
    a room, and is on floor a player can reach."""
    others = [(e.id, e.position) for cls in (Machine, WallWeapon, PowerSwitch, MysteryBox)
              for e in built.elements(cls)]
    others += [(w.id, w.barricade_origin) for w in built.elements(Window)]
    entry = built.find("entry_room")
    others.append(("ticket", ticket_trigger_point(entry.interior, entry.floor_z)))
    notices = _notices(committed)
    for key, point in notices:
        near = min((math.hypot(point.x - o.x, point.y - o.y), name) for name, o in others)
        assert near[0] >= 80.0, (key, point, near)
        rooms = [room.id for room in built.elements(Room)
                 if room.interior.holds_flat(point.x, point.y)]
        assert len(rooms) == 1, (key, point, rooms)
        assert flood.under(point.x, point.y, point.z + 4.0, only_reached=True) is not None, key
    for index, (key, a) in enumerate(notices):
        for other, b in notices[index + 1:]:
            assert math.hypot(a.x - b.x, a.y - b.y) >= 80.0, (key, other)


def test_the_street_windows_are_boarded_up(built) -> None:
    """Every framed window on the street face has at least three planks
    nailed across it, on the frame, between sill and head, looking out."""
    from zmforge.recipes.props import MOUNT_WALL, _mount_face, mount_kind

    lot = built.find("lot_room")
    fx = lot.interior.maxs.x
    boards = [prop for prop in _character(built, "lot")
              if "barricade_board" in prop.model]
    assert all(mount_kind(prop.model) == MOUNT_WALL for prop in boards)
    for centre, span, _mullion in FRONTAGE_WINDOWS:
        across = [prop for prop in boards if abs(prop.origin.y - centre) <= span / 2.0]
        assert len(across) >= 3, centre
        for prop in across:
            assert fx - 6.0 <= prop.origin.x <= fx - 3.0, prop.origin
            assert (prop.yaw + _mount_face(prop.model)) % 360.0 == pytest.approx(180.0)
    assert len(boards) == sum(3 if span <= 110.0 else 4 for _c, span, _m in FRONTAGE_WINDOWS)


def test_customer_846_is_still_in_his_seat(built) -> None:
    """What is left of him is on the seat of the front row's north chair --
    at the measured seat height, not the backrest's -- and his ticket is on
    the floor in front of it."""
    waiting = built.find("waiting_room")
    chairs = [prop for prop in built.find("waiting_chairs").props]
    his = max(chairs, key=lambda prop: (prop.origin.x, prop.origin.y))
    remains = [prop for prop in _character(built, "waiting") if "gib_chunk" in prop.model]
    on_seat = [prop for prop in remains
               if math.hypot(prop.origin.x - his.origin.x - WAITING_SEAT_FORWARD,
                             prop.origin.y - his.origin.y) <= 8.0]
    assert len(on_seat) >= 3
    from zmforge.recipes.props import collision_box
    for prop in on_seat:
        bottom = prop.origin.z + collision_box(prop.model)[0][2]
        assert bottom == pytest.approx(waiting.floor_z + WAITING_SEAT_TOP, abs=0.01)
        assert not prop.solid
    assert 18.0 < WAITING_SEAT_TOP < 20.0     # the cushion, not the 34.9 backrest
    tickets = [prop for prop in _character(built, "waiting")
               if prop.model.startswith("p7_office_paper_sheet")
               and 16.0 <= prop.origin.x - his.origin.x <= 40.0
               and abs(prop.origin.y - his.origin.y) <= 16.0]
    assert tickets, "his ticket is gone"


def test_each_room_has_its_outbreak_set_piece(built) -> None:
    """One or two things per room that somebody did here, by model."""
    wanted = {
        "lot": {"p7_wheel_barrow_street_vendor", "p7_sandbag_02",
                "p7_luggage_hardshell_handle_down_white", "p7_anim_zm_barricade_board_01"},
        "entry": {"p7_chair_waiting_room_01_blue", "p7_debris_newspaper_02"},
        "waiting": {"p7_gib_chunk_bone_01", "p7_zm_teddybear", "p7_crate_wood_01_short",
                    "p7_luggage_cloth_a_lg_green", "p7_chair_waiting_room_01_blue"},
        "windows": {"p7_file_cab_metal_02_drawer_02"},
        "eye": {"p7_zm_der2_poster_anatomy_01", "p7_zm_der2_poster_anatomy_04"},
        "photo": {"p7_cleaning_paper_ball_brown"},
        "break": {"zmf_prop_birthday_cake", "p7_debris_trash_paper_plate_01"},
        "records": {"p7_bed_mattress_barrack_made_v2", "p7_bed_pillow_barrack",
                    "p7_zm_der2_light_hurricane_lamp", "p7_crate_wood_01_short_open",
                    "p7_file_cab_metal_02_drawer_02"},
        "queue": {"p7_debris_trash_drink_carrier_01"},
        "office": {"p7_bottle_glass_liquor_01", "p7_book_office_lrg_red"},
    }
    for room, models in wanted.items():
        have = {prop.model for prop in _character(built, room)}
        assert models <= have, (room, models - have)
    total = sum(len(_character(built, room)) for room in wanted)
    assert total >= 90, total
    variety = {prop.model for room in wanted for prop in _character(built, room)}
    assert len(variety) >= 40, len(variety)


def test_one_chair_faces_the_wall_and_one_is_out_of_line(built) -> None:
    """Nothing can be knocked over (a prop has only a yaw), so the disorder
    is in the headings: one chair turned to the east wall a hand's width off
    it, one left at an angle that is no quarter turn."""
    from zmforge.recipes.props import MODEL_FRONT

    waiting = built.find("waiting_room")
    chairs = [prop for prop in _character(built, "waiting")
              if prop.model == "p7_chair_waiting_room_01_blue"]
    assert len(chairs) == 2
    looks = [(prop.yaw + MODEL_FRONT[prop.model]) % 360.0 for prop in chairs]
    to_wall = [prop for prop, look in zip(chairs, looks) if look == pytest.approx(0.0)]
    assert to_wall and waiting.interior.maxs.x - to_wall[0].origin.x <= 20.0
    assert any(look % 90.0 > 5.0 for look in looks)


def test_desk_and_seat_clutter_is_not_an_obstacle_but_the_kit_still_is(built) -> None:
    """Everything the pass strews is walked through except the teddy, which
    is a kit prop and so keeps its collmap (Z21)."""
    from zmforge.recipes.props import MODEL_BOX

    for room in ("lot", "entry", "waiting", "windows", "eye", "photo", "break",
                 "records", "queue", "office"):
        for prop in _character(built, room):
            (_x0, _y0, z0), (_x1, _y1, z1) = MODEL_BOX[prop.model]
            if prop.model.startswith("zmf_prop_"):
                assert prop.solid, prop.model
            elif z1 - z0 < 8.0:
                assert not prop.solid, (room, prop.model)



def test_the_menus_call_it_dmv_of_the_damned(built, committed) -> None:
    from zmforge.recipes.dmv import MAP_TITLE

    assert MAP_TITLE == "DMV of the Damned"
    assert built.title == MAP_TITLE
    assert "DMV of the Damned" in committed["manifest"] or any(
        "DMV of the Damned" in path.read_text(encoding="utf-8", errors="ignore")
        for path in committed["root"].rglob("*.zone")
    )



# --------------------------------------------------------------------------
# The two custom perks' HUD icons (zmforge.texture.hud_icons)
# --------------------------------------------------------------------------
def test_both_custom_perk_icons_ship_as_image_assets(committed) -> None:
    """Both perks' slot images are on no stock assetlist, so the map packs its own.

    The zone must list ``image,<name>`` for each, and the commit must have
    written each PNG and a ``.gdt`` entry naming it.  Whether the link packs
    them and the widget draws them has not been measured.
    """
    from PIL import Image

    from zmforge.script.perks import DIVE_TO_NUKE_ICON, TOMBSTONE_ICON
    from zmforge.texture import hud_icons
    from zmforge.texture.gdtdb import parse_gdt

    names = [TOMBSTONE_ICON.image, DIVE_TO_NUKE_ICON.image]
    zone = committed["manifest"].splitlines()
    root = committed["root"]
    gdt = root / hud_icons.gdt_relative(MAP_NAME)
    declared = {e.name: e.fields["baseImage"] for e in parse_gdt(gdt.read_text(encoding="utf-8"))}
    for name in names:
        assert f"image,{name}" in zone, name
        png = root / hud_icons.image_relative(MAP_NAME, name)
        with Image.open(png) as image:
            assert image.format == "PNG"
            assert image.size == (hud_icons.ICON_SIZE, hud_icons.ICON_SIZE)
            assert image.mode == "RGBA"
        assert declared[name] == hud_icons.base_image(MAP_NAME, name)


def test_no_solid_prop_within_the_review_door_band(built) -> None:
    """A door band clear of solid props, as a hard rule for this map.

    ``Z53`` keeps the path *through* a doorway clear (48 either side, 8 past
    each jamb).  This rule is stricter: by plain edge-to-edge distance no solid
    piece stands within 48 of an opening, flanking the jambs, and
    :func:`zmforge.recipes.dmv._clear_door_bands` slides or drops any that
    would.  The test measures with :mod:`zmforge.review.facts`, the code the
    review packet uses, so the two cannot drift.
    """
    from zmforge.review import facts as F

    areas = F._areas(built)
    props = F._props(built, areas)
    F._measure_props(props, F._openings(built, areas))
    near = [
        (p.id, p.door_gap, p.door) for p in props
        if p.area is not None and p.solid and p.door_gap is not None
        and p.door_gap < F.DOOR_BAND and p.z_high is not None
        and p.z_high - p.area.floor_z > F.STEP_HEIGHT and p.mount in ("floor", "either")
    ]
    assert near == []


def test_no_string_names_a_window_number(committed) -> None:
    """Signage must match what is built: the hall has one
    service window, so no string the map ships -- PA lines, HUD lines,
    prompts, notices, quest hints -- may send a player to "window 2" or
    "WINDOW 5", which do not exist."""
    strings = committed["strings"]
    assert "SERVICE WINDOW" in strings
    hits = re.findall(r"[^\n]*\bwindow\s+\d[^\n]*", strings, re.I)
    assert hits == [], hits[:5]


def test_the_registration_perk_is_a_car_not_double_tap() -> None:
    """The VEHICLE REGISTRATION FEE machine once showed Double
    Tap's vending model.  It is the lot's compact car, with a measured box,
    its trigger moved out to the car's side, and text and cost unchanged."""
    from zmforge.recipes.dmv import (REGISTRATION_CAR, REGISTRATION_TRIGGER_SHIFT,
                                     vehicle_registration_perk)
    from zmforge.recipes.props import MODEL_BOX
    from zmforge.script.perks import perk_script

    perk = vehicle_registration_perk()
    assert perk.machine_model == REGISTRATION_CAR
    assert REGISTRATION_CAR.startswith("veh_") and REGISTRATION_CAR in MODEL_BOX
    assert "doubletap" not in perk.machine_model and "vending" not in perk.machine_model
    assert perk.name == "VEHICLE REGISTRATION FEE" and perk.cost == 3000
    text = "\n".join(line for f in perk_script(perk, "HINT").functions for line in f.body)
    assert f'.off_model = "{REGISTRATION_CAR}";' in text
    assert "p7_zm_vending_doubletap" not in text
    assert f"AnglesToRight( perk_machine.angles ), {REGISTRATION_TRIGGER_SHIFT:g} )" in text
