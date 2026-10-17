"""Split start: every player starts alone in a sealed hallway with a button.

What it is, in play: *N* hallways, each its own zone with its own spawners
and barriers and no floor, door or sight line to any other.  Player *i*
starts in hallway *i* and plays the first rounds there alone.  At the end of
each hallway is a button ("everyone else dies and you get 5,000 points").
The first player to press it gets the points and is moved to the hub;
everyone else is killed and comes back, at the normal between-round respawn,
in the hub.  If nobody has pressed by the start of round *R*, everyone is
moved to the hub alive with their points set to 0.  Either way the hallways
close for good: every button is deleted, every hallway zone is disabled (no
spawns there, and standing in one is out of the playable area), and every
later respawn or late join lands in the hub.

What the recipe supplies: the hallway rooms and their zones (spawners,
barriers, no connection to anything), a spawn point, facing and button
position per hallway, the hub zone and a few points in it.
:func:`install_split_start` does the rest: the per-slot initial-spawn structs
(one per hallway, :attr:`~zmforge.blueprint.elements.PlayerStart.points`),
the declarations that tell the reachability checks these zones are entered
by script (:class:`~zmforge.blueprint.script_plan.ScriptEntry`), the strings
and the script.  :func:`hallway_links` is the check that the hallways really
are sealed from each other and from the hub.

**The stock behaviour it is built on**, read in the mod tools'
``share/raw/scripts``:

====================================  =======================================================
what                                  evidence
====================================  =======================================================
initial spawn: which struct           ``zm/gametypes/_zm_gametype.gsc:433-484``
                                      ``onFindValidSpawnPoint`` collects the
                                      ``initial_spawn`` structs and asks
                                      ``zm/_zm.gsc:690 getFreeSpawnpoint``.  That shuffles
                                      the array once per game (``:703-707``), numbers the
                                      structs in shuffled order (``en_num``, ``:776-785``)
                                      and hands player ``playernum`` the struct numbered
                                      ``playernum`` (``:789``), falling back to
                                      ``spawnpoints[0]`` (``:795``).  ``playernum`` is the
                                      team's join counter (``_zm.gsc:673-687``), so *k*
                                      players get *k* different structs while there are at
                                      least *k*; which struct is random.  ``script_int`` on
                                      a struct is a team side, not a slot (``:736-770``).
... and after ``begin_spawning``      ``_zm_gametype.gsc:438-441`` asks
                                      ``check_for_valid_spawn_near_team`` first (a late
                                      joiner)
between-round respawn                 ``_zm.gsc:4462-4472`` (``:4467``, ``:4471``) threads ``spectators_respawn``
                                      at the end of a round; ``:3231-3251`` respawns every
                                      spectator each second until ``between_round_over``
                                      (``:4555``); ``:3277-3345 spectator_respawn`` takes
                                      its point from ``check_for_valid_spawn_near_team``
                                      (``:3297``)
**forcing the respawn point**         ``_zm.gsc:3361-3367``: when
                                      ``level.check_for_valid_spawn_near_team_callback``
                                      is set it is called as ``( revivee, return_struct )``
                                      and its answer used as is -- by the spectator respawn
                                      (``:3297``, ``.origin`` / ``.angles`` read at
                                      ``:3302-3311``), the late-join spawn
                                      (``_zm_gametype.gsc:440``) and host migration
                                      (``_hostmigration.gsc:257``, ``:597``).  Nothing in
                                      the stock tree sets it.  It
                                      stays set for the whole game: see the next row.
**why the stock respawn is not used** without the callback the stock pick is
                                      ``get_valid_spawn_location`` (``_zm.gsc:3435``),
                                      which reads ``struct::get_array(
                                      spawn_points[closest_group].target, "targetname" )``
                                      (``:3453``).  zmforge's one ``player_respawn_point``
                                      has no ``target`` (stock ``zm_giant.map`` ones
                                      carry ``"target" "autoNNN"``), so no point comes
                                      back and ``spectator_respawn`` falls to ``self
                                      Spawn( origin, angles )`` (``:3315``) with
                                      ``origin = self.spectator_respawn.origin``
                                      (``:3282``): the player's *initial spawn struct*
                                      (``_zm_gametype.gsc:552``), which is in their
                                      sealed hallway, so after a press
                                      the dead would come back in their hallways.  So
                                      the callback is never cleared, and every player's
                                      ``spectator_respawn`` is re-pointed at a hub point
                                      when the opening resolves
is this player in a sealed hallway    ``_zm_zonemgr.gsc:214 entity_in_zone( zone_name,
                                      ignore_enabled_check )``, called with ``true`` as
                                      ``_zm_unitrigger.gsc:269`` does (the hallway zones
                                      are disabled by then)
every spawn, whatever the path       ``shared/callbacks_shared.gsc:183 on_spawned``; run
                                      by ``_globallogic_spawn.gsc:465`` (first spawn) and
                                      ``_zm.gsc:3338`` (spectator respawn)
move a player                         ``zm_tomb_teleporter.gsc:526-527 player setorigin(
                                      ... ); player setplayerangles( ... );``
kill a player outright (co-op)        ``_zm.gsc:2097-2100``, the out-of-playable-area
                                      kill: ``DisableInvulnerability(); .lives = 0;
                                      dodamage( health + 1000, origin ); .bleedout_time =
                                      0;``.  The damage downs them (``PlayerLastStand``
                                      threads ``laststand_bleedout``, which sets
                                      ``bleedout_time`` at ``_zm_laststand.gsc:537``); the
                                      zero written after it ends both countdown loops
                                      (``:543``, ``:564``) and they bleed out (``:580``)
                                      to spectator.  A player already down only needs
                                      the zero.
solo                                  the solo presser is the winner and is never
                                      damaged; ``_zm.gsc:4467-4471`` only respawns
                                      spectators when there is more than one player
revive a downed player                ``_zm.gsc:2797 players[i] zm_laststand::auto_revive(
                                      players[i] );`` (``_zm_laststand.gsc:1327``)
points                                ``_zm_score.gsc:521 add_to_player_score``; the
                                      balance is ``self.score`` mirrored to
                                      ``self.pers["score"]`` (``:533-534``, ``:565-566``),
                                      and ``_zm.gsc:3272`` writes ``self.score``
                                      directly.  ``minus_to_player_score`` is not used for
                                      the zeroing: it refunds under the Shopping Free gum
                                      (``:558-563``).
round start                           ``_zm.gsc:4433 level notify( "start_of_round" );``,
                                      with ``level.round_number`` already the new round
                                      (``:4551``, before the next loop)
stopping a zone for good              ``_zm_zonemgr.gsc:299, :307`` are the fields
                                      ``zone_init`` starts a zone with (``is_enabled`` /
                                      ``is_spawning_allowed`` false); ``:1166``
                                      ``create_spawner_list`` only takes spawn locations
                                      from a zone with both true, and ``manage_zones``
                                      skips a disabled zone (``:891``).  The list is
                                      rebuilt at once through
                                      ``level.create_spawner_list_func`` (set at ``:57``,
                                      called with the zone keys at ``:974``, kept
                                      as ``level.zone_keys`` at ``:857``) instead
                                      of waiting for the next second.  A disabled zone's
                                      volume is also outside the playable area
                                      (``_zm.gsc:2012``), so there is no way back.
zombies left in the hallways          ``zm_giant_cleanup_mgr.gsc:223, :237``:
                                      ``level.zombie_total++`` then ``Kill()`` -- the
                                      zombie is respawned later, where the players are
====================================  =======================================================

The first-press lock: GSC threads are cooperative and only yield at a
``wait`` or ``waittill``, so :func:`zmf_split_lock`'s test-and-set of
``level.zmf_split_phase`` runs whole before any other thread runs.  Two
presses in the same server frame are two trigger notifies handled one after
the other, and the second finds the phase already ``"hub"``.  The same lock
is what the round-*R* fallback takes, so a press and the fallback cannot
both happen.

The hallway each player gets: the stock shuffle above puts *k* players on *k*
different hallway structs, but not player *i* on hallway *i*.  The script
therefore places every player itself on spawn: hallway ``playernum`` if no
connected player holds it, otherwise the first free one (more players than
hallways share, round robin).  The stock struct and the scripted move agree
on "one player per hallway"; the move makes it the join order.

**Unverified in play**, all of it: that the spawn callback's ``SetOrigin``
lands during the intro freeze without a visible jump; that ``Kill()`` on a
zombie mid-traversal of a barrier is clean; that a player with a self-revive
gum or perk in co-op cannot survive the zero bleedout (``_zm.gsc:2097-2100``
is Treyarch's own kill and does not special-case them either); that a player
joining in the frame of the press is placed correctly; that a hallway held by
a player who has since disconnected reads as free (``isdefined`` on the
departed player's entity is assumed false); that spawning the buttons in the
thread ``main`` starts, after ``initial_blackscreen_passed``, is early enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "Hallway",
    "HubPoint",
    "SplitStartText",
    "split_start_script",
    "install_split_start",
    "hallway_links",
    "SEALED",
]

_SCORE = r"scripts\zm\_zm_score"
_LASTSTAND = r"scripts\shared\laststand_shared"
_ZM_LASTSTAND = r"scripts\zm\_zm_laststand"
_ZONEMGR = r"scripts\zm\_zm_zonemgr"
_CALLBACKS = r"scripts\shared\callbacks_shared"

#: The references the map's ``.str`` carries for this mechanic.
#: The level notify sent once the opening has resolved and the hallways are
#: sealed; anything that belongs to the opening ends on it (P12).
SEALED = "zmf_split_sealed"
PROMPT_REF = "SPLIT_START_PROMPT"
WON_REF = "SPLIT_START_WON"
LOST_REF = "SPLIT_START_LOST"
TIMEOUT_REF = "SPLIT_START_TIMEOUT"
WON_SOLO_REF = "SPLIT_START_WON_SOLO"
WARNING_REF = "SPLIT_START_WARNING"


@dataclass(frozen=True)
class Hallway:
    """One sealed start hallway.

    ``zone`` is its zone's name (spawners and barriers are the recipe's);
    ``spawn`` is where its player starts and respawns until the press,
    facing ``yaw``; ``button`` is the centre of the button's use radius.
    """

    zone: str
    spawn: tuple[float, float, float]
    button: tuple[float, float, float]
    yaw: float = 0.0


@dataclass(frozen=True)
class HubPoint:
    """One place in the hub a player is moved to, and the way they face."""

    origin: tuple[float, float, float]
    yaw: float = 0.0


@dataclass(frozen=True)
class SplitStartText:
    """The words.  ``prompt`` is the button's hint (a ``triggerstring``; it
    must say ``[{+activate}]``, map-principles P5); the rest are lines
    printed bold: ``won`` to the presser, ``lost`` to everyone else at the
    press, ``timeout`` to everyone when round *R* moves them.

    ``lost`` may name the presser as ``&&1`` (the player entity is passed as
    the parameter, the stock way ``zm/gametypes/_globallogic_player.gsc:71
    iPrintLn(&"MP_CONNECTED", self);`` names a player; how it renders is
    unverified in play).  ``won_solo`` (optional) is said to the presser
    instead of ``won`` when nobody else is in the game, where "everyone else
    dies" would be false; without it ``won`` is said either way."""

    prompt: str
    won: str
    lost: str
    timeout: str
    won_solo: str | None = None
    #: Said bold to everyone at the start of the round *before* the deadline
    #: while nobody has pressed: what the timeout will do (a wipe that
    #: zeroes every score must be announced before it lands).  No parameter.
    warning: str | None = None

    @classmethod
    def default(cls, points: int, deadline_round: int) -> "SplitStartText":
        return cls(
            prompt=f"Press ^3[{{+activate}}]^7: everyone else dies and you get {points:,} points",
            won=f"You pressed it. Everyone else is dead. +{points:,} points.",
            lost="Someone else pressed the button. You wake up in the hub next round.",
            timeout=f"Round {deadline_round}: nobody pressed. Everyone goes to the hub with 0 points.",
            warning=(f"Nobody has pressed. At round {deadline_round} everyone goes to the hub "
                     "and every score goes to 0."),
        )


def _v(p: Sequence[float]) -> str:
    return "( " + ", ".join(f"{float(c):g}" for c in p) + " )"


def split_start_script(
    *,
    hallways: Sequence[Hallway],
    hub_zone: str,
    hub: Sequence[HubPoint],
    prompt_asset: str,
    won_asset: str,
    lost_asset: str,
    timeout_asset: str,
    points: int = 5000,
    deadline_round: int = 5,
    radius: float = 64.0,
    won_notify: str = "zmf_opening_accepted",
    resolved_notify: str = "zmf_opening_resolved",
    lost_names_presser: bool = False,
    won_solo_asset: str | None = None,
    warning_asset: str | None = None,
) -> CustomScript:
    """The whole mechanic as one :class:`CustomScript`, given the string
    assets (``&"<asset>"`` names).  :func:`install_split_start` is what a
    recipe calls; this is the part that needs no blueprint.

    What other logic can read, once the opening is over (hallways closed):

    * ``level.zmf_split_resolved`` goes from false (set in ``main``) to
      true, and level notify *resolved_notify* fires.  A variable and a
      notify, not a level flag: check Z3 refuses a ``flag::init`` written
      after the zone hook, which is where custom functions land (the same
      rule :mod:`zmforge.script.quest` lives under);
    * ``level.zmf_split_resolved_by`` is ``"press"`` or ``"round"``, and
      ``level.zmf_split_winner`` the presser (undefined for ``"round"``);
    * on a press only, level notify *won_notify* with the presser;
    * either way, level notify ``zmf_split_sealed`` with the presser or
      undefined.
    """
    for name in (won_notify, resolved_notify):
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"{name!r} is not a usable notify / flag name")
    if not hallways:
        raise ValueError("a split start needs at least one hallway")
    zones = [h.zone for h in hallways]
    if len(set(zones)) != len(zones):
        raise ValueError("every hallway needs a zone of its own")
    if hub_zone in zones:
        raise ValueError(f"the hub zone {hub_zone!r} is also a hallway")
    if not hub:
        raise ValueError("the hub needs at least one point")
    if int(points) < 0:
        raise ValueError("the button's reward is a number of points, 0 or more")
    if int(deadline_round) < 2:
        raise ValueError("the fallback round must leave at least round 1 in the hallways")

    init = [
        "level.zmf_split_halls = [];",
    ]
    for n, h in enumerate(hallways):
        init += [
            "s_hall = SpawnStruct();",
            f's_hall.zone = "{h.zone}";',
            f"s_hall.origin = {_v(h.spawn)};",
            f"s_hall.angles = ( 0, {float(h.yaw):g}, 0 );",
            f"s_hall.button = {_v(h.button)};",
            f"level.zmf_split_halls[ {n} ] = s_hall;",
        ]
    init.append("level.zmf_split_hub = [];")
    for n, p in enumerate(hub):
        init += [
            "s_hub = SpawnStruct();",
            f"s_hub.origin = {_v(p.origin)};",
            f"s_hub.angles = ( 0, {float(p.yaw):g}, 0 );",
            f"level.zmf_split_hub[ {n} ] = s_hub;",
        ]
    init += [
        "level.zmf_split_hub_next = 0;",
        'level.zmf_split_phase = "hallways";',
        "level.zmf_split_resolved = false;",
        # _zm.gsc:3361-3367: the spectator respawn, a late joiner and host
        # migration all take their point from this when it is set.
        "level.check_for_valid_spawn_near_team_callback = &zmf_split_spawn_point;",
        # callbacks_shared.gsc:183, run on every spawn (_globallogic_spawn.gsc:465,
        # _zm.gsc:3338).  Registered here, in main, before any player spawns.
        "callback::on_spawned( &zmf_split_on_spawned );",
        "for ( i = 0; i < level.zmf_split_halls.size; i++ )",
        "{",
        "\tlevel thread zmf_split_button( i );",
        "}",
        "level thread zmf_split_deadline();",
    ]

    spawn_point = [
        "s_where = e_revivee zmf_split_where();",
        "if ( isdefined( b_return_struct ) && b_return_struct )",
        "{",
        "\treturn s_where;",
        "}",
        "return s_where.origin;",
    ]

    where = [
        'if ( level.zmf_split_phase == "hallways" )',
        "{",
        "\treturn level.zmf_split_halls[ self zmf_split_claim() ];",
        "}",
        "return zmf_split_hub_point();",
    ]

    hub_point = [
        "s_hub = level.zmf_split_hub[ level.zmf_split_hub_next % level.zmf_split_hub.size ];",
        "level.zmf_split_hub_next++;",
        "return s_hub;",
    ]

    claim = [
        "if ( isdefined( self.zmf_split_hall ) && self zmf_split_free( self.zmf_split_hall ) )",
        "{",
        "\tlevel.zmf_split_halls[ self.zmf_split_hall ].owner = self;",
        "\treturn self.zmf_split_hall;",
        "}",
        "n_want = 0;",
        # _zm.gsc:673-687: the team's join counter, 0 for the first player.
        "if ( isdefined( self.playernum ) )",
        "{",
        "\tn_want = self.playernum;",
        "}",
        "n_hall = undefined;",
        "if ( n_want < level.zmf_split_halls.size && self zmf_split_free( n_want ) )",
        "{",
        "\tn_hall = n_want;",
        "}",
        "for ( i = 0; !isdefined( n_hall ) && i < level.zmf_split_halls.size; i++ )",
        "{",
        "\tif ( self zmf_split_free( i ) )",
        "\t{",
        "\t\tn_hall = i;",
        "\t}",
        "}",
        "if ( !isdefined( n_hall ) )",
        "{",
        "\tn_hall = n_want % level.zmf_split_halls.size;",
        "}",
        "level.zmf_split_halls[ n_hall ].owner = self;",
        "self.zmf_split_hall = n_hall;",
        "return n_hall;",
    ]

    free = [
        "e_owner = level.zmf_split_halls[ n_hall ].owner;",
        "return !isdefined( e_owner ) || e_owner == self;",
    ]

    on_spawned = [
        'self endon( "disconnect" );',
        # Once the opening is resolved the callback already hands every
        # respawn and late join a hub point, so a player who spawned before
        # and is not standing in a sealed hallway is left where they are.
        # Anyone else -- a late joiner on an initial struct, or any spawn path
        # that bypassed the callback into a hallway (the stock fallback is the
        # initial struct, _zm.gsc:3282, :3315) -- is moved to the hub, or the
        # dead would come back in their hallways.
        "if ( level.zmf_split_resolved && isdefined( self.zmf_split_placed ) && !self zmf_split_in_hall() )",
        "{",
        "\treturn;",
        "}",
        "self.zmf_split_placed = true;",
        "s_where = self zmf_split_where();",
        "self SetOrigin( s_where.origin );",
        "self SetPlayerAngles( s_where.angles );",
        'if ( level.zmf_split_phase != "hallways" )',
        "{",
        "\tself.spectator_respawn = s_where;",
        "}",
    ]

    in_hall = [
        "for ( i = 0; i < level.zmf_split_halls.size; i++ )",
        "{",
        "\tstr_zone = level.zmf_split_halls[ i ].zone;",
        "\tif ( !isdefined( level.zones ) || !isdefined( level.zones[ str_zone ] ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        # _zm_zonemgr.gsc:214; true as _zm_unitrigger.gsc:269 passes it,
        # because a sealed hallway's zone is disabled.
        "\tif ( self zm_zonemgr::entity_in_zone( str_zone, true ) )",
        "\t{",
        "\t\treturn true;",
        "\t}",
        "}",
        "return false;",
    ]

    button = [
        'level endon( "end_game" );',
        'level endon( "zmf_split_sealed" );',
        # _zm.gsc:1612 init, :530 set (as zmforge.script.quest waits): no
        # press, and no trigger, while the screen is still black.
        'level flag::wait_till( "initial_blackscreen_passed" );',
        "s_hall = level.zmf_split_halls[ n_hall ];",
        f't_button = spawn( "trigger_radius_use", s_hall.button, 0, {float(radius):g}, 96 );',
        "t_button TriggerIgnoreTeam();",
        "t_button SetVisibleToAll();",
        't_button SetTeamForTrigger( "none" );',
        't_button SetCursorHint( "HINT_NOICON" );',
        f't_button SetHintString( &"{prompt_asset}" );',
        "s_hall.trigger = t_button;",
        "while ( true )",
        "{",
        '\tt_button waittill( "trigger", e_who );',
        "\tif ( !isplayer( e_who ) || e_who laststand::player_is_in_laststand() )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        # The lock and the hand-off, with no wait between the waittill and
        # them: nothing else runs until this thread yields.
        "\tif ( !zmf_split_lock() )",
        "\t{",
        "\t\treturn;",
        "\t}",
        "\tlevel thread zmf_split_finish( e_who );",
        "\treturn;",
        "}",
    ]

    lock = [
        'if ( level.zmf_split_phase != "hallways" )',
        "{",
        "\treturn false;",
        "}",
        'level.zmf_split_phase = "hub";',
        "return true;",
    ]

    deadline = [
        'level endon( "end_game" );',
        'level endon( "zmf_split_sealed" );',
        "while ( true )",
        "{",
        # _zm.gsc:4433; round_number is already the round that is starting.
        '\tlevel waittill( "start_of_round" );',
        *((
            f"\tif ( level.round_number == {int(deadline_round) - 1} )",
            "\t{",
            "\t\ta_players = getplayers();",
            "\t\tfor ( i = 0; i < a_players.size; i++ )",
            "\t\t{",
            f'\t\t\ta_players[ i ] IPrintLnBold( &"{warning_asset}" );',
            "\t\t}",
            "\t}",
        ) if warning_asset is not None and int(deadline_round) > 1 else ()),
        f"\tif ( level.round_number < {int(deadline_round)} )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tif ( zmf_split_lock() )",
        "\t{",
        "\t\tlevel thread zmf_split_finish( undefined );",
        "\t}",
        "\treturn;",
        "}",
    ]

    # Solo (nobody else in the game): the won line that does not claim
    # anybody died, when the recipe has one.
    won_lines = [f'\te_winner IPrintLnBold( &"{won_asset}" );']
    if won_solo_asset is not None:
        won_lines = [
            "\tif ( a_players.size < 2 )",
            "\t{",
            f'\t\te_winner IPrintLnBold( &"{won_solo_asset}" );',
            "\t}",
            "\telse",
            "\t{",
            f'\t\te_winner IPrintLnBold( &"{won_asset}" );',
            "\t}",
        ]
    finish = [
        'level endon( "end_game" );',
        "level.zmf_split_winner = e_winner;",
        'level.zmf_split_resolved_by = "round";',
        "if ( isdefined( e_winner ) )",
        "{",
        '	level.zmf_split_resolved_by = "press";',
        "}",
        "a_players = getplayers();",
        "if ( isdefined( e_winner ) )",
        "{",
        f"\te_winner zm_score::add_to_player_score( {int(points)} );",
        "\te_winner zmf_split_to_hub();",
        *won_lines,
        "\tfor ( i = 0; i < a_players.size; i++ )",
        "\t{",
        "\t\te_p = a_players[ i ];",
        "\t\tif ( e_p == e_winner )",
        "\t\t{",
        "\t\t\tcontinue;",
        "\t\t}",
        f'\t\te_p IPrintLnBold( &"{lost_asset}"{", e_winner" if lost_names_presser else ""} );',
        "\t\te_p zmf_split_kill();",
        "\t}",
        "}",
        "else",
        "{",
        "\tfor ( i = 0; i < a_players.size; i++ )",
        "\t{",
        "\t\te_p = a_players[ i ];",
        '\t\tif ( e_p.sessionstate != "spectator" )',
        "\t\t{",
        "\t\t\tif ( e_p laststand::player_is_in_laststand() )",
        "\t\t\t{",
        # _zm.gsc:2797
        "\t\t\t\te_p zm_laststand::auto_revive( e_p );",
        "\t\t\t}",
        "\t\t\te_p zmf_split_to_hub();",
        "\t\t}",
        # _zm_score.gsc:565-566: the balance and its pers mirror.
        "\t\te_p.score = 0;",
        '\t\te_p.pers[ "score" ] = 0;',
        f'\t\te_p IPrintLnBold( &"{timeout_asset}" );',
        "\t}",
        "}",
        "zmf_split_close();",
        # The callback stays set: the stock pick finds no point on this map and
        # falls back to self.spectator_respawn (_zm.gsc:3282, :3315), the
        # initial struct in the player's hallway (_zm_gametype.gsc:552).
        # Re-point that fallback too, for everyone, dead or alive.
        "a_players = getplayers();",
        "for ( i = 0; i < a_players.size; i++ )",
        "{",
        "\ta_players[ i ].spectator_respawn = zmf_split_hub_point();",
        "}",
        "level.zmf_split_resolved = true;",
        f'level notify( "{resolved_notify}", e_winner );',
        "if ( isdefined( e_winner ) )",
        "{",
        f'	level notify( "{won_notify}", e_winner );',
        "}",
        'level notify( "zmf_split_sealed", e_winner );',
    ]

    to_hub = [
        "s_hub = zmf_split_hub_point();",
        "self SetOrigin( s_hub.origin );",
        "self SetPlayerAngles( s_hub.angles );",
    ]

    kill = [
        'if ( self.sessionstate == "spectator" )',
        "{",
        "\treturn;",
        "}",
        # _zm.gsc:2097-2100, Treyarch's own outright kill.
        "if ( !self laststand::player_is_in_laststand() )",
        "{",
        "\tself DisableInvulnerability();",
        "\tself.lives = 0;",
        "\tself dodamage( self.health + 1000, self.origin );",
        "}",
        "self.bleedout_time = 0;",
    ]

    close = [
        "for ( i = 0; i < level.zmf_split_halls.size; i++ )",
        "{",
        "\ts_hall = level.zmf_split_halls[ i ];",
        "\tif ( isdefined( s_hall.trigger ) )",
        "\t{",
        "\t\ts_hall.trigger delete();",
        "\t\ts_hall.trigger = undefined;",
        "\t}",
        "\tif ( isdefined( level.zones ) && isdefined( level.zones[ s_hall.zone ] ) )",
        "\t{",
        # _zm_zonemgr.gsc:299, :307 / :1166
        "\t\tlevel.zones[ s_hall.zone ].is_enabled = false;",
        "\t\tlevel.zones[ s_hall.zone ].is_spawning_allowed = false;",
        "\t}",
        "}",
        f'if ( isdefined( level.zones ) && isdefined( level.zones[ "{hub_zone}" ] ) )',
        "{",
        f'\tzm_zonemgr::enable_zone( "{hub_zone}" );',
        "}",
        # _zm_zonemgr.gsc:57, :857, :974: rebuild the spawn list now, not next second.
        "if ( isdefined( level.create_spawner_list_func ) && isdefined( level.zone_keys ) )",
        "{",
        "\t[[ level.create_spawner_list_func ]]( level.zone_keys );",
        "}",
        # zm_giant_cleanup_mgr.gsc:223, :237: back on the round's count, then gone.
        "a_zombies = getaiteamarray( level.zombie_team );",
        "for ( i = 0; i < a_zombies.size; i++ )",
        "{",
        "\tif ( !isdefined( a_zombies[ i ] ) || !isalive( a_zombies[ i ] ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tif ( zm_utility::is_magic_bullet_shield_enabled( a_zombies[ i ] ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tlevel.zombie_total++;",
        "\ta_zombies[ i ] Kill();",
        "}",
    ]

    functions = (
        CustomFunction("zmf_split_init", tuple(init),
                       purpose="Split start: hallways, hub, spawn hooks, buttons, round fallback."),
        CustomFunction("zmf_split_spawn_point", tuple(spawn_point),
                       params=("e_revivee", "b_return_struct"),
                       purpose="level.check_for_valid_spawn_near_team_callback (_zm.gsc:3364): "
                               "own hallway before the press, the hub after."),
        CustomFunction("zmf_split_where", tuple(where),
                       purpose="Where this player belongs now: their hallway, or a hub point."),
        CustomFunction("zmf_split_hub_point", tuple(hub_point),
                       purpose="The next hub point, round robin."),
        CustomFunction("zmf_split_claim", tuple(claim),
                       purpose="This player's hallway: their join number's, else the first free."),
        CustomFunction("zmf_split_free", tuple(free), params=("n_hall",),
                       purpose="Whether no other connected player holds this hallway."),
        CustomFunction("zmf_split_on_spawned", tuple(on_spawned),
                       purpose="Every spawn: put the player where they belong; never a "
                               "sealed hallway once the opening is resolved."),
        CustomFunction("zmf_split_in_hall", tuple(in_hall),
                       purpose="Whether this player stands in any hallway zone "
                               "(_zm_zonemgr.gsc:214 entity_in_zone, enabled or not)."),
        CustomFunction("zmf_split_button", tuple(button), params=("n_hall",),
                       purpose="One hallway's button: the first press wins."),
        CustomFunction("zmf_split_lock", tuple(lock),
                       purpose="Test-and-set of the phase; true for exactly one caller."),
        CustomFunction("zmf_split_deadline", tuple(deadline),
                       purpose=f"Round {int(deadline_round)} with no press: everyone to the hub, 0 points."),
        CustomFunction("zmf_split_finish", tuple(finish), params=("e_winner",),
                       purpose="Pay and move the presser, kill the rest (or move all at 0), close."),
        CustomFunction("zmf_split_to_hub", tuple(to_hub),
                       purpose="Move this player to the next hub point."),
        CustomFunction("zmf_split_kill", tuple(kill),
                       purpose="Kill this player outright (_zm.gsc:2097-2100); a spectator is left."),
        CustomFunction("zmf_split_close", tuple(close),
                       purpose="Delete the buttons, disable the hallway zones, clear their zombies."),
    )
    return CustomScript(
        using=(_SCORE, _LASTSTAND, _ZM_LASTSTAND, _ZONEMGR, _CALLBACKS,
               r"scripts\zm\_zm_utility", r"scripts\shared\flag_shared"),
        functions=functions,
        # Not threaded: it has no wait, and the spawn hooks must be in place
        # before the first player spawns.
        statements=((Slot.AFTER_ENTRY, "zmf_split_init();"),),
        notes=(f"split start: {len(hallways)} hallways, hub {hub_zone!r} ({len(hub)} points), "
               f"{int(points)} points for the press, fallback at round {int(deadline_round)}",),
    )


def install_split_start(
    bp,
    *,
    hallways: Sequence[Hallway],
    hub_zone: str,
    hub: Sequence[HubPoint],
    points: int = 5000,
    deadline_round: int = 5,
    text: SplitStartText | None = None,
    radius: float = 64.0,
    won_notify: str = "zmf_opening_accepted",
    resolved_notify: str = "zmf_opening_resolved",
) -> CustomScript:
    """Put a split start on a blueprint.  Call once, after the zones and the
    player start exist (``set_player_start`` with the map's slot count).

    * Replaces the player start's slot points with the hallway spawns, one
      per slot, so the stock initial spawn already puts every player in a
      different hallway (the hallways get no stock respawn group, blueprint.respawn).
      There must be at least as many hallways as slots.
    * Declares every hallway zone and the hub zone as entered by script
      (:class:`~zmforge.blueprint.script_plan.ScriptEntry`), which is what
      lets Z3 and the flood checks accept zones no door or floor reaches.
    * Ships the four lines (five with ``won_solo``) and returns the merged logic.
    """
    from ..blueprint.elements import PlayerStart, Zone
    from ..blueprint.script_plan import ScriptEntry
    from ..spatial import Point

    names = {z.name for z in bp.elements(Zone)}
    for zone in [h.zone for h in hallways] + [hub_zone]:
        if zone not in names:
            raise ValueError(f"split start: no zone named {zone!r}")
    if any(e.why.startswith("split start") for e in bp.script.entries):
        raise ValueError("split start is already installed on this map")
    starts = bp.elements(PlayerStart)
    if len(starts) != 1:
        raise ValueError("split start: call set_player_start (with the map's slot count) first")
    start = starts[0]
    slots = start.slots
    if len(hallways) < slots:
        raise ValueError(
            f"split start: {slots} player slots and {len(hallways)} hallways; "
            "every slot needs a hallway of its own"
        )
    text = text or SplitStartText.default(int(points), int(deadline_round))
    if "[{+activate}]" not in text.prompt:
        raise ValueError("the button's prompt must say [{+activate}] (map-principles P5)")
    if "&&2" in text.lost or any(
            "&&" in line for line in (text.won, text.timeout, text.won_solo or "",
                                      text.warning or "")):
        raise ValueError("only the lost line takes a parameter (&&1, the presser)")

    # Every hallway is its own sealed pocket of air.  BO3's occlusion pass
    # keeps the open air and one sealed pocket and drops the rest, and a
    # player in a dropped pocket sees floors and walls flicker to the sky.
    # So each hallway's barricade yard is vented to the open air; a hallway without a yard is left for Z83 to report.
    from ..blueprint.elements import Window, Yard

    for hallway in hallways:
        yard_ids = sorted({w.yard_id for w in bp.elements(Window)
                           if w.zone_name == hallway.zone and w.yard_id})
        yards = [bp.find(y) for y in yard_ids]
        yards = [y for y in yards if isinstance(y, Yard)]
        if yards and not any(y.vents for y in yards):
            bp.add_yard_vent(yards[0], id=f"vent_{hallway.zone}")

    script = split_start_script(
        hallways=hallways, hub_zone=hub_zone, hub=hub,
        prompt_asset=bp.add_map_string(PROMPT_REF, text.prompt, kind="triggerstring"),
        won_asset=bp.add_map_string(WON_REF, text.won),
        lost_asset=bp.add_map_string(LOST_REF, text.lost),
        timeout_asset=bp.add_map_string(TIMEOUT_REF, text.timeout),
        points=points, deadline_round=deadline_round, radius=radius,
        won_notify=won_notify, resolved_notify=resolved_notify,
        lost_names_presser="&&1" in text.lost,
        won_solo_asset=(bp.add_map_string(WON_SOLO_REF, text.won_solo)
                        if text.won_solo is not None else None),
        warning_asset=(bp.add_map_string(WARNING_REF,
                                         text.warning)
                       if text.warning is not None else None),
    )
    # In place, so the start keeps its id; the slot count, and with it the
    # player-cap statement set_player_start decided, do not change.
    start.position = Point(*hub[0].origin)
    start.points = tuple(Point(*h.spawn) for h in hallways[:slots])
    # No stock respawn group in a hallway (blueprint.respawn; Z78).
    start.sealed_zones = tuple(h.zone for h in hallways)
    start.slot_positions()
    for h in hallways:
        bp.script.entries.append(ScriptEntry(
            h.zone, (tuple(map(float, h.spawn)),), "split start: a player spawns here"))
    # The buttons are script-spawned triggers the review's element walk cannot
    # see; list one per hallway, with its prompt (review.facts._interactives).
    review = getattr(bp, "review_interactives", None)
    if review is not None:
        for h in hallways:
            review.append({
                "id": f"split_start_button_{h.zone}", "kind": "use_trigger",
                "what": "split-start button (first press wins; everyone else dies)",
                "zone": h.zone, "at": [round(float(c), 1) for c in h.button],
                "radius": float(radius), "prompt": text.prompt, "purchase": False,
                "wired_by": ("script/splitstart.py: a trigger_radius_use spawned at map "
                             f"start in each of the {len(hallways)} hallways, removed "
                             "once someone presses or round "
                             f"{int(deadline_round)} moves everyone to the hub"),
            })
    bp.script.entries.append(ScriptEntry(
        hub_zone, tuple(tuple(map(float, p.origin)) for p in hub),
        "split start: the button and round fallback teleport players here"))
    return bp.add_custom_logic(script)


def hallway_links(bp, hallways: Sequence[Hallway], hub_zone: str) -> list[tuple[str, str]]:
    """Every ``(hallway, zone)`` pair a player can walk between: from each
    hallway's spawn, flood on foot (:func:`~zmforge.verify.reachability.
    flood_from_spawn` from that point alone) and list the other hallways and
    the hub it reaches.  Empty means sealed, which is what the mechanic needs:
    only the teleport leaves a hallway."""
    from ..blueprint.elements import Zone
    from ..spatial import Point
    from ..verify.reachability import _inside, flood_from_spawn

    volumes: dict[str, list] = {}
    for zone in bp.elements(Zone):
        if zone.bounds is not None:
            volumes.setdefault(zone.name, []).append(zone.bounds)
    links: list[tuple[str, str]] = []
    for h in hallways:
        flood = flood_from_spawn(bp, points=[Point(*h.spawn)])
        cells = [flood.cells[i] for i in flood.reached]
        for other in [x.zone for x in hallways if x.zone != h.zone] + [hub_zone]:
            if any(_inside(b, c) for b in volumes.get(other, ()) for c in cells):
                links.append((h.zone, other))
    return links
