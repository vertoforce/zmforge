"""A ride players pay for, sit on, and are carried round a route by.

What it is: an invisible ``tag_origin`` base that the script moves waypoint to
waypoint, a set of visible models linked to it (the vehicle), and a set of
seats -- more ``tag_origin`` entities linked to it -- that a player is linked
onto when they pay at the stop.  Nothing here is an element: no brush, no
map entity, no model check sees it.  The caller keeps the route clear of
solids and keeps every waypoint inside a zone volume.

**The stock calls it is built from**, read in the mod tools'
``share/raw/scripts``:

====================================  =======================================================
what                                  evidence
====================================  =======================================================
spawn a model the script owns         ``shared/floor_collapse_shared.gsc:90 flr_model[i] =
                                      spawn( "script_model", positions[i].origin, 1 );``
an invisible attachment point         ``shared/vehicles/_croc.gsc:813 self.damage_fx_ent
                                      SetModel( "tag_origin" );``
carry one entity on another           ``shared/load_shared.gsc:997 ent LinkTo( e_link );``
move it, wait for it                  ``zm/_zm_blockers.gsc:579 self MoveTo( self.origin +
                                      vector, time, time * 0.25, time * 0.25 );``;
                                      ``shared/vehicleriders_shared.gsc:764 e_move waittill(
                                      "movedone" );``
turn it, wait for it                  ``shared/doors_shared.gsc:208 m_e_door RotateTo( v_angle,
                                      ... );``; ``zm/_zm_traps.gsc:526 ... waittill(
                                      "rotatedone" );``
**put a player on it**                ``shared/scene_shared.gsc:1656 player PlayerLinkToDelta(
                                      _e, "tag_player", 1, ...viewclamps... , 1, 1 );`` and
                                      ``shared/doors_shared.gsc:896 self PlayerLinkToDelta(
                                      self.freeze_origin, "tag_origin", 1.0, 45.0, 45.0, 45.0,
                                      45.0 );`` -- the second links to a ``tag_origin``
                                      entity's own tag, which is what a seat here is
take them off                         ``shared/vehicleriders_shared.gsc:632 self Unlink();``
grow a model                          ``shared/ai/archetype_robot.gsc:3520 wasp SetScale(
                                      0.75 );``
no damage while seated                ``shared/vehicle_ai_shared.gsc:1749 params.driver
                                      EnableInvulnerability();`` / ``_quadrotor.gsc:502
                                      player DisableInvulnerability();``
pay for it                            ``zm/_zm_score.gsc:655 function can_player_purchase(
                                      n_cost )``, ``:551 function minus_to_player_score(
                                      points )``
the heading to the next waypoint      ``shared/util_shared.gsc:1154 plant_angle =
                                      VectorToAngles( tangent );``
====================================  =======================================================

**The out-of-playable-area monitor.**  ``zm/_zm.gsc:2064`` kills a player who
is touching no enabled ``player_volume``, *unless*
``level.player_out_of_playable_area_monitor_callback`` is set and returns
false for them (``:2066``).  Nothing in the stock tree assigns that callback,
so this module sets it to one that exempts a seated rider.
The route is still meant to stay inside zones the ride requires open; the
callback is the belt to those braces, for a rider whose seat swings over a
corn wall on a corner.

**The fallback.**  If ``PlayerLinkToDelta`` does not hold a player to a seat
that is moving under ``MoveTo`` -- which has not been watched happen --
every rider also runs a follower that puts them back on their seat whenever
they are more than ``drift`` units off it, every server frame.  With a
working link it never fires; without one it is the scripted ride the map
still owes the player: carried round the route, looking where they like.

**Boarding on the move.**  Besides the stop's trigger there is a second use
trigger, linked to the base the way ``zm/_zm_laststand.gsc:849-852`` links a
revive trigger to a player (``SetMovingPlatformEnabled``, ``EnableLinkTo``,
``LinkTo``), so the prompt travels with the vehicle: walk up to it anywhere
on the route, pay the same price, take the same first free seat.  A rider
who boards mid-lap is set down at the stop with everyone else, but only the
riders aboard since the stop count as having gone all the way round
(``zmf_hayride_rode`` and the riders in ``zmf_hayride_lap``).  It is hidden
from riders (``SetInvisibleToPlayer``).  No boarding while it sits at the
stop cooling off: nothing would drive it.

**Not solid while it drives.**  The parts are ``script_model`` s, which shove
a player they move into, and a player standing on one under ``MoveTo`` is
not carried.  So the parts go ``NotSolid`` when it leaves the stop and
``Solid`` again once it is home and no player is within *clear_radius* of
the base (a player inside a part when it turned solid would be stuck).
Riders never depended on solidity: they are linked to their seats.

**Unverified in play**, all of it: that a linked use trigger follows a base
under ``MoveTo`` and can be used on the way; that a player linked with
``PlayerLinkToDelta`` to a ``tag_origin`` whose parent is moving is carried
smoothly, can look round within the clamps and can fire; that linked
``script_model`` parts follow a ``RotateTo`` of their parent; and how the
zombies behave round a moving rider.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .custom import CustomFunction, CustomScript, Slot

__all__ = ["RidePart", "Seat", "hayride", "route_length"]

_LASTSTAND = r"scripts\shared\laststand_shared"
_SCORE = r"scripts\zm\_zm_score"
_FLAG = r"scripts\shared\flag_shared"


@dataclass(frozen=True)
class RidePart:
    """One visible model of the vehicle, placed relative to the base at yaw 0
    (``+x`` is the direction of travel)."""

    model: str
    offset: tuple[float, float, float]
    yaw: float = 0.0
    scale: float = 1.0


@dataclass(frozen=True)
class Seat:
    """Where a rider sits, relative to the base at yaw 0, and which way the
    rider faces (degrees off the direction of travel)."""

    offset: tuple[float, float, float]
    yaw: float = 0.0


def _v(p: Sequence[float]) -> str:
    return "( " + ", ".join(f"{float(c):g}" for c in p) + " )"


def route_length(route: Sequence[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(route, route[1:]))


def hayride(
    *,
    route: Sequence[tuple[float, float]],
    z: float,
    parts: Sequence[RidePart],
    seats: Sequence[Seat],
    unload: Sequence[tuple[float, float, float]],
    trigger: tuple[float, float, float],
    price: int,
    prompt: str,
    prompt_away: str,
    prompt_closed: str | None,
    said_boarded: str,
    said_leaving: str,
    said_broke: str,
    said_full: str,
    said_closed: str | None,
    requires_flag: str | None = None,
    speed: float = 170.0,
    turn_time: float = 0.8,
    board_wait: float = 5.0,
    cooldown: float = 15.0,
    drift: float = 48.0,
    radius: float = 96.0,
    leaving_heard: float = 768.0,
    board_radius: float = 128.0,
    clear_radius: float | None = None,
) -> CustomScript:
    """The whole ride as one :class:`CustomScript`.

    *route* is the waypoints in plan, first and last the stop, driven at
    height *z*.  *prompt*, *prompt_away* and *prompt_closed* are
    ``triggerstring`` assets (the stop's hint while it can be boarded, while
    the ride is out, and before *requires_flag* is set); every ``said_*`` and
    every ``said_*`` is a ``string`` asset, printed bold to the player(s)
    concerned.  *said_leaving* goes only to players within *leaving_heard*
    of the stop who are not on board (they can still hop on); the rider who
    started the call has just read *said_boarded*, and the rest of the map
    has no use for it (map-principles P13).

    A rider reads one line a ride, *said_boarded*, and no prompt while
    seated: both use triggers turn invisible to them until they are set down
    (too many prompts during the ride read as noise; it used to print a line at four waypoints and another on the way
    home, P17 few broadcasts).

    *board_radius* is the reach of the use trigger that rides with the
    base (board anywhere on the route); *clear_radius* is how far round the
    base no player may stand before the parked vehicle turns solid again
    (default: the farthest part's offset plus 96).

    Notifies ``zmf_hayride_departed`` on level when it leaves and, at the end
    of every lap, ``zmf_hayride_lap`` on level and ``zmf_hayride_rode`` on each
    rider who was aboard for the whole lap (not one who got on mid-lap),
    which is what a quest step listens for.
    """
    route = [tuple(map(float, p)) for p in route]
    if len(route) < 3:
        raise ValueError("a ride needs at least three waypoints")
    if route[0] != route[-1]:
        raise ValueError("a ride ends where it starts, at the stop")
    if not seats:
        raise ValueError("a ride needs at least one seat")
    if len(unload) < len(seats):
        raise ValueError("every seat needs somewhere to set its rider down")

    if clear_radius is None:
        clear_radius = max((math.hypot(p.offset[0], p.offset[1]) for p in parts), default=0.0) + 96.0
    first_yaw = math.degrees(math.atan2(route[1][1] - route[0][1], route[1][0] - route[0][0]))
    ms = lambda s: int(round(float(s) * 1000))  # noqa: E731

    init = [
        'level endon( "end_game" );',
        f"v_stop = {_v((route[0][0], route[0][1], z))};",
        'e_base = spawn( "script_model", v_stop );',
        'e_base SetModel( "tag_origin" );',
        "e_base.angles = ( 0, 0, 0 );",
        "level.zmf_hayride = e_base;",
        "level.zmf_hayride_parts = [];",
    ]
    for part in parts:
        init += [
            f'e_part = spawn( "script_model", v_stop + {_v(part.offset)} );',
            f'e_part SetModel( "{part.model}" );',
            f"e_part.angles = ( 0, {part.yaw:g}, 0 );",
            *([f"e_part SetScale( {part.scale:g} );"] if part.scale != 1.0 else []),
            "e_part LinkTo( e_base );",
            "level.zmf_hayride_parts[ level.zmf_hayride_parts.size ] = e_part;",
        ]
    init.append("level.zmf_hayride_seats = [];")
    for seat in seats:
        init += [
            f'e_seat = spawn( "script_model", v_stop + {_v(seat.offset)} );',
            'e_seat SetModel( "tag_origin" );',
            f"e_seat.angles = ( 0, {seat.yaw:g}, 0 );",
            "e_seat LinkTo( e_base );",
            "level.zmf_hayride_seats[ level.zmf_hayride_seats.size ] = e_seat;",
        ]
    init += [
        "level.zmf_hayride_unload = [];",
        *(f"level.zmf_hayride_unload[ {n} ] = {_v(p)};" for n, p in enumerate(unload)),
        # Turn the whole assembly to face down the first leg.  Every part is
        # linked by now, so it turns with the base.
        f"e_base RotateTo( ( 0, {first_yaw:g}, 0 ), 0.05 );",
        'e_base waittill( "rotatedone" );',
        # The use trigger that rides along (zm/_zm_laststand.gsc:846-853).
        f't_ride = spawn( "trigger_radius_use", v_stop, 0, {board_radius:g}, 96 );',
        "t_ride TriggerIgnoreTeam();",
        "t_ride SetVisibleToAll();",
        't_ride SetTeamForTrigger( "none" );',
        't_ride SetCursorHint( "HINT_NOICON" );',
        "t_ride SetMovingPlatformEnabled( true );",
        "t_ride EnableLinkTo();",
        "t_ride LinkTo( e_base );",
        "level.zmf_hayride_ride_trigger = t_ride;",
        "level.player_out_of_playable_area_monitor_callback = &zmf_hayride_zone_ok;",
        "level.zmf_hayride_state = \"idle\";",
        "level thread zmf_hayride_stop();",
    ]

    stop = [
        'level endon( "end_game" );',
        f't_stop = spawn( "trigger_radius_use", {_v(trigger)}, 0, {radius:g}, 96 );',
        "t_stop TriggerIgnoreTeam();",
        "t_stop SetVisibleToAll();",
        't_stop SetTeamForTrigger( "none" );',
        't_stop SetCursorHint( "HINT_NOICON" );',
        "level.zmf_hayride_trigger = t_stop;",
        "zmf_hayride_hint();",
        "level thread zmf_hayride_listen( level.zmf_hayride_ride_trigger, true );",
        "zmf_hayride_listen( t_stop, false );",
    ]

    listen = [
        'level endon( "end_game" );',
        "while ( true )",
        "{",
        '\tt_use waittill( "trigger", e_who );',
        # A downed (last stand) or spectating player cannot board: the same
        # guard the gamble machine and the quest items use.
        "\tif ( !isplayer( e_who ) || e_who laststand::player_is_in_laststand() "
        '|| e_who.sessionstate == "spectator" '
        "|| ( isdefined( e_who.zmf_hayride_riding ) && e_who.zmf_hayride_riding ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tn_now = gettime();",
        "\tif ( isdefined( e_who.zmf_hayride_next ) && n_now < e_who.zmf_hayride_next )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\te_who.zmf_hayride_next = n_now + 1500;",
    ]
    if requires_flag:
        listen += [
            f'\tif ( !level flag::get( "{requires_flag}" ) )',
            "\t{",
            *([f'\t\te_who IPrintLnBold( &"{said_closed}" );'] if said_closed else []),
            "\t\tcontinue;",
            "\t}",
        ]
    listen += [
        # Cooling off at the stop: nothing would drive it.  Out on the route:
        # only the trigger riding with it boards.
        '\tif ( level.zmf_hayride_state == "home" || ( level.zmf_hayride_state == "away" && !b_moving ) )',
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tn_seat = zmf_hayride_free_seat();",
        "\tif ( n_seat < 0 )",
        "\t{",
        f'\t\te_who IPrintLnBold( &"{said_full}" );',
        "\t\tcontinue;",
        "\t}",
        f"\tif ( !e_who zm_score::can_player_purchase( {int(price)} ) )",
        "\t{",
        f'\t\te_who IPrintLnBold( &"{said_broke}" );',
        "\t\tcontinue;",
        "\t}",
        f"\te_who zm_score::minus_to_player_score( {int(price)} );",
        "\tzmf_hayride_board( e_who, n_seat );",
        '\tif ( level.zmf_hayride_state == "idle" )',
        "\t{",
        '\t\tlevel.zmf_hayride_state = "boarding";',
        "\t\tlevel thread zmf_hayride_depart();",
        "\t}",
        "}",
    ]

    hint = [
        'if ( level.zmf_hayride_state == "home" )',
        "{",
        f'\tlevel.zmf_hayride_trigger SetHintString( &"{prompt_away}" );',
        f'\tlevel.zmf_hayride_ride_trigger SetHintString( &"{prompt_away}" );',
        "\treturn;",
        "}",
        'if ( level.zmf_hayride_state == "away" )',
        "{",
        f'\tlevel.zmf_hayride_trigger SetHintString( &"{prompt_away}" );',
        f'\tlevel.zmf_hayride_ride_trigger SetHintString( &"{prompt}" );',
        "\treturn;",
        "}",
    ]
    if requires_flag and prompt_closed:
        hint += [
            f'if ( !level flag::get( "{requires_flag}" ) )',
            "{",
            f'\tlevel.zmf_hayride_trigger SetHintString( &"{prompt_closed}" );',
            f'\tlevel.zmf_hayride_ride_trigger SetHintString( &"{prompt_closed}" );',
            "\treturn;",
            "}",
        ]
    hint += [f'level.zmf_hayride_trigger SetHintString( &"{prompt}" );',
             f'level.zmf_hayride_ride_trigger SetHintString( &"{prompt}" );']

    free_seat = [
        "for ( i = 0; i < level.zmf_hayride_seats.size; i++ )",
        "{",
        "\tif ( !isdefined( level.zmf_hayride_seats[ i ].zmf_rider ) )",
        "\t{",
        "\t\treturn i;",
        "\t}",
        "}",
        "return -1;",
    ]

    board = [
        "e_seat = level.zmf_hayride_seats[ n_seat ];",
        "e_seat.zmf_rider = e_player;",
        # Got on out on the route: set down at the stop, but no full lap.
        'e_seat.zmf_late = ( level.zmf_hayride_state == "away" );',
        "level.zmf_hayride_ride_trigger SetInvisibleToPlayer( e_player, true );",
        "level.zmf_hayride_trigger SetInvisibleToPlayer( e_player, true );",
        "e_player.zmf_hayride_riding = true;",
        "e_player EnableInvulnerability();",
        "e_player SetOrigin( e_seat.origin );",
        "e_player SetPlayerAngles( e_seat.angles );",
        'e_player PlayerLinkToDelta( e_seat, "tag_origin", 1, 180, 180, 60, 45 );',
        "e_player thread zmf_hayride_follow( e_seat );",
        f'e_player IPrintLnBold( &"{said_boarded}" );',
    ]

    follow = [
        'self endon( "disconnect" );',
        'self endon( "zmf_hayride_off" );',
        'level endon( "end_game" );',
        "while ( isdefined( self.zmf_hayride_riding ) && self.zmf_hayride_riding )",
        "{",
        f"\tif ( Distance( self.origin, e_seat.origin ) > {drift:g} )",
        "\t{",
        "\t\tself SetOrigin( e_seat.origin );",
        "\t}",
        "\twait 0.05;",
        "}",
    ]

    depart = [
        'level endon( "end_game" );',
        "a_players = getplayers();",
        "for ( i = 0; i < a_players.size; i++ )",
        "{",
        "\te_p = a_players[ i ];",
        "\tif ( isdefined( e_p.zmf_hayride_riding ) && e_p.zmf_hayride_riding )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        f"\tif ( DistanceSquared( e_p.origin, {_v(trigger)} ) < {float(leaving_heard) ** 2:g} )",
        "\t{",
        f'\t\te_p IPrintLnBold( &"{said_leaving}" );',
        "\t}",
        "}",
        f"wait {board_wait:g};",
        'level.zmf_hayride_state = "away";',
        "zmf_hayride_hint();",
        "zmf_hayride_solid( false );",
        'level notify( "zmf_hayride_departed" );',
        "e_base = level.zmf_hayride;",
        "a_route = [];",
        *(f"a_route[ {n} ] = {_v((x, y, z))};" for n, (x, y) in enumerate(route)),
        "for ( i = 1; i < a_route.size; i++ )",
        "{",
        "\tv_leg = a_route[ i ] - e_base.origin;",
        "\tif ( Length( v_leg ) < 1 )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tv_face = VectorToAngles( v_leg );",
        f"\te_base RotateTo( ( 0, v_face[ 1 ], 0 ), {turn_time:g} );",
        '\te_base waittill( "rotatedone" );',
        f"\tn_time = Length( v_leg ) / {speed:g};",
        "\te_base MoveTo( a_route[ i ], n_time, n_time * 0.1, n_time * 0.1 );",
        '\te_base waittill( "movedone" );',
        "}",
        "a_riders = [];",
        "for ( i = 0; i < level.zmf_hayride_seats.size; i++ )",
        "{",
        "\te_rider = level.zmf_hayride_seats[ i ].zmf_rider;",
        "\tb_late = isdefined( level.zmf_hayride_seats[ i ].zmf_late ) && level.zmf_hayride_seats[ i ].zmf_late;",
        "\tlevel.zmf_hayride_seats[ i ].zmf_rider = undefined;",
        "\tlevel.zmf_hayride_seats[ i ].zmf_late = undefined;",
        "\tif ( !isdefined( e_rider ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\te_rider.zmf_hayride_riding = false;",
        '\te_rider notify( "zmf_hayride_off" );',
        "\te_rider Unlink();",
        "\te_rider SetOrigin( level.zmf_hayride_unload[ i ] );",
        "\te_rider DisableInvulnerability();",
        "\tlevel.zmf_hayride_ride_trigger SetInvisibleToPlayer( e_rider, false );",
        "\tlevel.zmf_hayride_trigger SetInvisibleToPlayer( e_rider, false );",
        "\tif ( b_late )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\ta_riders[ a_riders.size ] = e_rider;",
        '\te_rider notify( "zmf_hayride_rode" );',
        "}",
        'level.zmf_hayride_state = "home";',
        "zmf_hayride_hint();",
        "level thread zmf_hayride_resolid();",
        'level notify( "zmf_hayride_lap", a_riders );',
        f"wait {cooldown:g};",
        'level.zmf_hayride_state = "idle";',
        "zmf_hayride_hint();",
    ]

    solid = [
        "for ( i = 0; i < level.zmf_hayride_parts.size; i++ )",
        "{",
        "\tif ( b_solid )",
        "\t{",
        "\t\tlevel.zmf_hayride_parts[ i ] Solid();",
        "\t}",
        "\telse",
        "\t{",
        "\t\tlevel.zmf_hayride_parts[ i ] NotSolid();",
        "\t}",
        "}",
    ]

    resolid = [
        'level endon( "end_game" );',
        'level endon( "zmf_hayride_departed" );',
        "while ( true )",
        "{",
        "\tb_clear = true;",
        "\ta_players = getplayers();",
        "\tfor ( i = 0; i < a_players.size; i++ )",
        "\t{",
        f"\t\tif ( Distance2DSquared( a_players[ i ].origin, level.zmf_hayride.origin ) < {float(clear_radius) ** 2:g} )",
        "\t\t{",
        "\t\t\tb_clear = false;",
        "\t\t}",
        "\t}",
        "\tif ( b_clear )",
        "\t{",
        "\t\tzmf_hayride_solid( true );",
        "\t\treturn;",
        "\t}",
        "\twait 0.25;",
        "}",
    ]

    hint_on_flag = []
    if requires_flag and prompt_closed:
        hint_on_flag = [CustomFunction(
            "zmf_hayride_hint_on_open",
            ('level endon( "end_game" );',
             f'level flag::wait_till( "{requires_flag}" );',
             "zmf_hayride_hint();"),
            purpose="Swap the stop's prompt from closed to open when the route opens.",
        )]

    functions = [
        CustomFunction("zmf_hayride_init", tuple(init),
                       purpose="Spawn the hayride at its stop: base, parts, seats; start the stop."),
        CustomFunction("zmf_hayride_stop", tuple(stop),
                       purpose="Spawn the stop's use trigger; listen on it and on the one riding along."),
        CustomFunction("zmf_hayride_listen", tuple(listen), params=("t_use", "b_moving"),
                       purpose="One use trigger: pay, get a seat, start the call (b_moving: boards out on the route)."),
        CustomFunction("zmf_hayride_hint", tuple(hint),
                       purpose="The stop's prompt for the ride's current state."),
        CustomFunction("zmf_hayride_free_seat", tuple(free_seat),
                       purpose="Index of the first empty seat, or -1."),
        CustomFunction("zmf_hayride_board", tuple(board), params=("e_player", "n_seat"),
                       purpose="Link a paying player onto a seat (PlayerLinkToDelta, doors_shared.gsc:896)."),
        CustomFunction("zmf_hayride_follow", tuple(follow), params=("e_seat",),
                       purpose="Fallback: keep a rider on their seat if the link does not."),
        CustomFunction("zmf_hayride_depart", tuple(depart),
                       purpose="Call the ride, drive the route, set the riders down, cool off."),
        CustomFunction("zmf_hayride_solid", tuple(solid), params=("b_solid",),
                       purpose="Parts Solid / NotSolid (a moving script_model shoves players)."),
        CustomFunction("zmf_hayride_resolid", tuple(resolid),
                       purpose="Home: turn the parts solid once no player stands inside them."),
        CustomFunction("zmf_hayride_zone_ok", (
            "return !( isdefined( self.zmf_hayride_riding ) && self.zmf_hayride_riding );",),
            purpose="Out-of-playable-area callback (_zm.gsc:2066): never kill a seated rider."),
        *hint_on_flag,
    ]
    statements = [(Slot.AFTER_ENTRY, "level thread zmf_hayride_init();")]
    if hint_on_flag:
        statements.append((Slot.AFTER_ENTRY, "level thread zmf_hayride_hint_on_open();"))
    models = sorted({part.model for part in parts} | {"tag_origin"})
    return CustomScript(
        using=(_SCORE, _LASTSTAND) + ((_FLAG,) if requires_flag else ()),
        functions=tuple(functions),
        statements=tuple(statements),
        assets=tuple(("xmodel", m) for m in models if m != "tag_origin"),
        notes=(f"hayride: {len(route) - 1} legs, {route_length(route):.0f} units, "
               f"{len(seats)} seats, {price} points",),
    )
