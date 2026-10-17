"""The stock functions the checker will accept, and where each was read.

GSC has no link step a caller can run here: a call to a function that does
not exist compiles, and then kills the game at the moment the line runs.
The only defence available off Windows is a table of what the stock
scripts actually define, so a typo or an invented function is caught while
the text is being written.

Every entry carries the file it was read out of.  **Nothing goes in this
table that was not read from a stock script or from a build this engine ran**
-- a plausible-looking function name is exactly the failure this table
exists to prevent.  ``evidence`` is the quotable source, so an entry can be
audited without Windows.

Adding an entry: read the stock script in the mod tools, copy the
namespace from its ``#namespace`` line and the name from its ``function``
line, and record both the module path a caller must ``#using`` and the line
you read.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "StockFunction",
    "STOCK_FUNCTIONS",
    "ENGINE_BUILTINS",
    "namespace_module",
    "lookup",
    "unresolved",
]


@dataclass(frozen=True, slots=True)
class StockFunction:
    """One callable stock script function.

    ``module`` is the path a script must ``#using`` before calling it;
    ``evidence`` is where the definition was read.
    """

    namespace: str
    name: str
    module: str
    evidence: str

    @property
    def call(self) -> str:
        return f"{self.namespace}::{self.name}"


#: Functions proven by this engine's own builds: every one of them appears in
#: a generated script that compiled and linked (spec 5.1, 7.3), so the table
#: starts from what is known to work rather than from documentation.
_FROM_OUR_BUILDS = (
    StockFunction(
        "zm_usermap",
        "main",
        r"scripts\zm\zm_usermap",
        "called by every generated .gsc and .csc this engine has built and "
        "linked; spec 5.1 step 1",
    ),
    StockFunction(
        "zm_weapons",
        "load_weapon_spec_from_table",
        r"scripts\zm\_zm_weapons",
        "the map's own weapon table: _zm_weapons.gsc:3362 and its client twin "
        "_zm_weapons.csc:466, both function load_weapon_spec_from_table( "
        "table, first_row ). Called by the stock zm_usermap.gsc:433 and "
        "zm_usermap.csc:95 on Treyarch's own table, and by every generated "
        "script that prices a weapon; a probe usermap with both calls linked "
        "clean [measured]",
    ),
    StockFunction(
        "zm_zonemgr",
        "add_adjacent_zone",
        r"scripts\zm\_zm_zonemgr",
        "generated zone hook, spec 5.1; links and runs",
    ),
    StockFunction(
        "zm_zonemgr",
        "manage_zones",
        r"scripts\zm\_zm_zonemgr",
        "generated main(), spec 5.1; links and runs",
    ),
    StockFunction(
        "flag",
        "init",
        r"scripts\shared\flag_shared",
        "generated zone hook, spec 5.1; links and runs",
    ),
    StockFunction(
        "flag",
        "set",
        r"scripts\shared\flag_shared",
        "generated zone hook, spec 5.1; links and runs",
    ),
    StockFunction(
        "callback",
        "on_localplayer_spawned",
        r"scripts\shared\callbacks_shared",
        "generated .csc __init__, spec 5.2; links and runs",
    ),
)

#: Read out of the decompiled stock scripts.  The tree is the
#: public decompile the format reference already cites
#: (``github.com/ate47/bo3-source``); ``evidence`` is ``<file>:<line>`` in it.
#: Read for reference only: no decompiled code is copied here.  Where the mod
#: tools ship the same script in ``share/raw/scripts``, the function is there
#: under the same name (the line can differ).
#: A decompile is not the compiler's opinion, so a real build with the mod
#: tools remains the authority: what this table buys is catching a name that
#: does not exist at all, before a build cycle is spent on it.
_FROM_STOCK_SCRIPTS = (
    StockFunction(
        "zm_score",
        "add_to_player_score",
        r"scripts\zm\_zm_score",
        "_zm_score.gsc:521 function add_to_player_score( points, "
        "b_add_to_total, str_awarded_by ); #namespace zm_score at :14",
    ),
    StockFunction(
        "zm_score",
        "minus_to_player_score",
        r"scripts\zm\_zm_score",
        "_zm_score.gsc:556 function minus_to_player_score( points ), "
        "self.score -= points at :570",
    ),
    # Read in the mod tools' share/raw/scripts, for the signature
    # gamble machine (zmforge.script.gamble).
    StockFunction(
        "zm_utility",
        "play_sound_at_pos",
        r"scripts\zm\_zm_utility",
        "share/raw/scripts/zm/_zm_utility.gsc:3040 function play_sound_at_pos( "
        "ref, pos, ent ); called as zm_utility::play_sound_at_pos( \"purchase\", "
        "self.origin ) at _zm_blockers.gsc:1027 and ( \"no_purchase\", ... ) at "
        ":341; the refs are registered at _zm.gsc:1101-1102 (zmb_cha_ching, "
        "zmb_no_cha_ching)",
    ),
    StockFunction(
        "zm_utility",
        "set_zombie_var",
        r"scripts\zm\_zm_utility",
        "_zm_utility.gsc:3382 function set_zombie_var( zvar, value, is_float, "
        "column, is_team_based ), level.zombie_vars[ zvar ] = value at :3402; "
        "#namespace zm_utility at :24.  The same function exists under the "
        "zombie_utility namespace at shared/ai/zombie_utility.gsc:1805; the "
        "zm_utility one is used here because the generated script already "
        "#usings that module",
    ),
    StockFunction(
        "flag",
        "wait_till",
        r"scripts\shared\flag_shared",
        "flag_shared.gsc:190 function wait_till( str_flag ); used by stock "
        "maps as level flag::wait_till( \"power_on\" ) (zm_castle.gsc:880)",
    ),
    StockFunction(
        "flag",
        "get",
        r"scripts\shared\flag_shared",
        "flag_shared.gsc:163 function get( str_flag )",
    ),
    StockFunction(
        "laststand",
        "player_is_in_laststand",
        r"scripts\shared\laststand_shared",
        "laststand_shared.gsc:12 function player_is_in_laststand(); "
        "#namespace laststand at :4",
    ),
    StockFunction(
        "hud",
        "fade_to_black_for_x_sec",
        r"scripts\shared\hud_shared",
        "hud_shared.gsc:162 function fade_to_black_for_x_sec( startwait, "
        "blackscreenwait, fadeintime, fadeouttime, shadername ); called by "
        "zm_tomb_teleporter.gsc:456 on a teleporting player",
    ),
    StockFunction(
        "zm_perks",
        "set_perk_clientfield",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:978 function set_perk_clientfield( perk, state ); "
        "state 1 on give (:752), 0 on take (:958), 2 while paused (:1286)",
    ),
    StockFunction(
        "zombie_utility",
        "zombie_head_gib",
        r"scripts\shared\ai\zombie_utility",
        "shared/ai/zombie_utility.gsc:3462 function zombie_head_gib( attacker, "
        "means_of_death ); #namespace zombie_utility at :12.  Called with no "
        "arguments by the nuke, _zm_powerup_nuke.gsc:120",
    ),
    StockFunction(
        "zombie_utility",
        "zombie_eye_glow_stop",
        r"scripts\shared\ai\zombie_utility",
        "shared/ai/zombie_utility.gsc:1732 function zombie_eye_glow_stop(); "
        "called as self zombie_eye_glow_stop() by zombie_head_gib (:2967) "
        "just before GibServerUtils::GibHead (stock script source)",
    ),
    StockFunction(
        "zm",
        "register_zombie_damage_override_callback",
        r"scripts\zm\_zm",
        "_zm.gsc:5865 function register_zombie_damage_override_callback( func "
        "); #namespace zm at :160.  actor_damage_override_wrapper (:5847) "
        "threads each callback with ( willBeKilled, inflictor, attacker, "
        "damage, flags, meansofdeath, weapon, vpoint, vdir, sHitLoc, "
        "psOffsetTime, boneIndex, surfaceType ) before it reads "
        "dont_die_on_me (:5859)",
    ),
    StockFunction(
        "zm_utility",
        "is_magic_bullet_shield_enabled",
        r"scripts\zm\_zm_utility",
        "_zm_utility.gsc:3752 function is_magic_bullet_shield_enabled( ent ); "
        "the nuke skips any AI it returns true for, _zm_powerup_nuke.gsc:89",
    ),
    StockFunction(
        "zombie_utility",
        "spawn_zombie",
        r"scripts\shared\ai\zombie_utility",
        "shared/ai/zombie_utility.gsc:1851 function spawn_zombie( spawner, "
        "target_name, spawn_point, round_number ).  Stock map scripts spawn "
        "extra ordinary zombies with it: zm_castle_tram.gsc:496, "
        "zm_island_power.gsc:620, zm_genesis_power.gsc:1278, all as "
        "spawn_zombie( level.zombie_spawners[ 0 ], \"<name>\", <loc> )",
    ),
    StockFunction(
        "zombie_utility",
        "set_zombie_run_cycle",
        r"scripts\shared\ai\zombie_utility",
        "shared/ai/zombie_utility.gsc:2075 function set_zombie_run_cycle( "
        "new_move_speed ), which assigns self.zombie_move_speed at :2088.  "
        "The stock last-zombie sprint is :2005 ai_zombie "
        "zombie_utility::set_zombie_run_cycle( \"sprint\" ); followed by "
        ":2006 ai_zombie.zombie_move_speed_original = "
        "ai_zombie.zombie_move_speed; (line numbers re-read)",
    ),
    StockFunction(
        "zombie_utility",
        "set_zombie_run_cycle_override_value",
        r"scripts\shared\ai\zombie_utility",
        "shared/ai/zombie_utility.gsc:2060 function "
        "set_zombie_run_cycle_override_value( new_move_speed ) { "
        "set_zombie_run_cycle( new_move_speed ); "
        "self.zombie_move_speed_override = new_move_speed; }, and "
        ":2078-2082 set_zombie_run_cycle: if( isdefined( "
        "self.zombie_move_speed_override ) ) { "
        "self.zombie_move_speed_restore = new_move_speed; return; }",
    ),
    StockFunction(
        "lui",
        "screen_flash",
        r"scripts\shared\lui_shared",
        "lui_shared.gsc:442 function screen_flash( n_fadein_time, n_hold_time, "
        "n_fadeout_time, n_target_alpha, v_color, b_force_close_menu ); "
        "#namespace lui at :10.  The nuke's white flash, "
        "_zm_powerup_nuke.gsc:157.  Call it on a player for that player; "
        "called on level it flashes everyone, lui_shared.gsc:434-439 "
        "foreach ( player in level.players ) player thread screen_flash( ... )",
    ),
    # The two below were read out of the mod tools install's own
    # ``share/raw/scripts``, not out of the decompile: these
    # are the sources the linker compiles, so the evidence is the compiler's
    # and not a third party's reading of it.
    StockFunction(
        "clientfield",
        "register",
        r"scripts\shared\clientfield_shared",
        "clientfield_shared.gsc:17 function register( str_pool_name, str_name, "
        "n_version, n_bits, str_type ); #namespace clientfield at :3.  The "
        "client's copy takes three more, clientfield_shared.csc:20 function "
        "register( ..., func_callback, b_host, b_callback_for_zero_when_new )",
    ),
    # The perk registration API, read in the mod tools install's
    # own ``share/raw/scripts/zm/_zm_perks.gsc`` -- the file the linker
    # compiles.  A map that writes a perk of its own calls five of them; the
    # sixth, ``register_perk_clientfields``, is deliberately not used and is
    # not in this table, because nothing in this package emits a call to it
    # (:func:`zmforge.script.perks._icon_lines` says why).
    StockFunction(
        "zm_perks",
        "register_perk_basic_info",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:1819 function register_perk_basic_info( str_perk, "
        "str_alias, n_perk_cost, str_hint_string, w_perk_bottle_weapon ); the "
        "bottle is asserted present at :1825",
    ),
    StockFunction(
        "zm_perks",
        "register_perk_precache_func",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:1896 function register_perk_precache_func( str_perk, "
        "func_precache ); run by default_vending_precaching at :172-184",
    ),
    StockFunction(
        "zm_perks",
        "register_perk_machine",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:1847 function register_perk_machine( str_perk, "
        "func_perk_machine_setup, func_perk_machine_thread ); the setup takes "
        "t_use, perk_machine, bump_trigger, collision (doc block at :1842)",
    ),
    StockFunction(
        "zm_perks",
        "register_perk_threads",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:1919 function register_perk_threads( str_perk, "
        "func_give_player_perk, func_take_player_perk ); give is threaded on "
        "the player at :753, take called at :947 and :1255",
    ),
    StockFunction(
        "zm_perks",
        "register_perk_host_migration_params",
        r"scripts\zm\_zm_perks",
        "_zm_perks.gsc:1979 function register_perk_host_migration_params( "
        "str_perk, str_radiant_name, str_effect_name ); :98 gates the whole "
        "machine-think loop on the alias, the radiant name and the effect "
        "all being defined",
    ),
    StockFunction(
        "clientfield",
        "set_player_uimodel",
        r"scripts\shared\clientfield_shared",
        "clientfield_shared.gsc:71 function set_player_uimodel( "
        "str_field_name, n_value ), whose whole body is "
        "CodeSetUIModelClientField( self, str_field_name, n_value ); every "
        "stock perk's HUD setter is this call "
        "(_zm_perk_juggernaut.gsc:87)",
    ),
    StockFunction(
        "zm_laststand",
        "update_bleedout_timer",
        r"scripts\zm\_zm_laststand",
        "_zm_laststand.csc:71 function update_bleedout_timer( localClientNum, "
        "oldVal, newVal, bNewEnt, bInitialSnap, fieldName, bWasTimeJump ); "
        "#namespace zm_laststand at :12.  It is the callback the stock script "
        "hands its own laststand_update0..3 fields at :26, so a map that "
        "registers more of them hands back the same one",
    ),
    # Read in the mod tools' share/raw/scripts, for the gags
    # (zmforge.script.gags).
    StockFunction(
        "zm_zonemgr",
        "get_player_zone",
        r"scripts\zm\_zm_zonemgr",
        "share/raw/scripts/zm/_zm_zonemgr.gsc:89 function get_player_zone() "
        "{ return zm_utility::get_current_zone(); } ('self = player'); "
        "#namespace zm_zonemgr",
    ),
    # Read in the mod tools' share/raw/scripts, for the quest's
    # zone gate (zmforge.script.quest, P8).
    StockFunction(
        "zm_zonemgr",
        "zone_is_enabled",
        r"scripts\zm\_zm_zonemgr",
        "share/raw/scripts/zm/_zm_zonemgr.gsc:65 function zone_is_enabled( "
        "zone_name ) returns false unless level.zones[ zone_name ].is_enabled, "
        "which enable_zone (:488-499) sets when a door's flag opens the zone; "
        "#namespace zm_zonemgr at :15",
    ),
    StockFunction(
        "zm_equipment",
        "show_hint_text",
        r"scripts\zm\_zm_equipment",
        "share/raw/scripts/zm/_zm_equipment.gsc:587 function show_hint_text( "
        "text, show_for_time = 3.20, font_scale = 1.25, ypos = 220 ); called "
        "as self thread zm_equipment::show_hint_text( "
        '&"ZOMBIE_HERO_WEAPON_HINT", 2 ) at _zm_hero_weapon.gsc:182',
    ),
    # Read in share/raw/scripts, for the quest framework
    # (zmforge.script.quest) and the mini-bosses (zmforge.script.bosses).
    StockFunction(
        "zm_score",
        "can_player_purchase",
        r"scripts\zm\_zm_score",
        "share/raw/scripts/zm/_zm_score.gsc:655 function can_player_purchase( "
        "n_cost ) //self = player; called as self zm_score::can_player_purchase( "
        "cost ) at _zm_perk_widows_wine.gsc:681; #namespace zm_score at :22",
    ),
    StockFunction(
        "zm_spawner",
        "register_zombie_death_event_callback",
        r"scripts\zm\_zm_spawner",
        "share/raw/scripts/zm/_zm_spawner.gsc:2463 function "
        "register_zombie_death_event_callback( func ); run on the dying zombie "
        "with the attacker at :2344 / :2458; called as zm_spawner::"
        "register_zombie_death_event_callback( &check_annihilator_death ) at "
        "_zm_weap_annihilator.gsc:31; #namespace zm_spawner at :41",
    ),
    StockFunction(
        "zm_powerups",
        "specific_powerup_drop",
        r"scripts\zm\_zm_powerups",
        "share/raw/scripts/zm/_zm_powerups.gsc:688 function specific_powerup_drop( "
        "powerup_name, drop_spot, ... ); called as level thread zm_powerups::"
        'specific_powerup_drop( "full_ammo", power_up_origin ) at '
        "_zm_ai_raps.gsc:590; #namespace zm_powerups at :54",
    ),
    # Read in share/raw/scripts, for the split start
    # (zmforge.script.splitstart).
    StockFunction(
        "callback",
        "on_spawned",
        r"scripts\shared\callbacks_shared",
        "share/raw/scripts/shared/callbacks_shared.gsc:183 function on_spawned( "
        'func, obj ), add_callback( #"on_player_spawned", ... ); run by '
        '_globallogic_spawn.gsc:465 and _zm.gsc:3338 callback::callback( '
        '#"on_player_spawned" ); called as callback::on_spawned( '
        "&zm_on_player_spawned ) at _zm.gsc:418; #namespace callback at :11",
    ),
    StockFunction(
        "zm_laststand",
        "auto_revive",
        r"scripts\zm\_zm_laststand",
        "share/raw/scripts/zm/_zm_laststand.gsc:1327 function auto_revive( "
        "reviver, dont_enable_weapons ); called as players[i] zm_laststand::"
        "auto_revive( players[i] ) at _zm.gsc:2797; #namespace zm_laststand at :40",
    ),
    StockFunction(
        "zm_zonemgr",
        "enable_zone",
        r"scripts\zm\_zm_zonemgr",
        "share/raw/scripts/zm/_zm_zonemgr.gsc:488 function enable_zone( "
        "zone_name ), returns at :493 when the zone is already enabled; "
        "called as enable_zone( initial_zone[i] ) at :847; #namespace "
        "zm_zonemgr at :15",
    ),
    StockFunction(
        "zm_zonemgr",
        "entity_in_zone",
        r"scripts\zm\_zm_zonemgr",
        "share/raw/scripts/zm/_zm_zonemgr.gsc:214 function entity_in_zone( "
        "zone_name, ignore_enabled_check = false ); called as "
        "level._unitriggers.contact_ent zm_zonemgr::entity_in_zone(keys[i], "
        "true) at _zm_unitrigger.gsc:269; #namespace zm_zonemgr at :15 "
        "(read for the split start's sealed-hallway respawn guard)",
    ),
    # Read in share/raw/scripts, for per-player use triggers and the entity
    # lookups a mechanic's stations make.
    StockFunction(
        "zm_perks",
        "give_perk",
        r"scripts\zm\_zm_perks",
        "share/raw/scripts/zm/_zm_perks.gsc:738 function give_perk( perk, "
        "bought ); called as self give_perk( random_perk ) by give_random_perk "
        "at :1119; #namespace zm_perks at :39",
    ),
    StockFunction(
        "zm_perks",
        "has_perk_paused",
        r"scripts\zm\_zm_perks",
        "share/raw/scripts/zm/_zm_perks.gsc:1332 function has_perk_paused( "
        "perk ) // self = player; tested beside HasPerk by give_random_perk "
        "at :1109; #namespace zm_perks at :39",
    ),
    StockFunction(
        "zm_utility",
        "give_start_weapon",
        r"scripts\zm\_zm_utility",
        "share/raw/scripts/zm/_zm_utility.gsc:4530 function give_start_weapon( "
        "b_switch_weapon ); called as self zm_utility::give_start_weapon( true ) "
        "by zm/zm_usermap.gsc:428; #namespace zm_utility at :33",
    ),
    StockFunction(
        "zm_utility",
        "get_player_perk_purchase_limit",
        r"scripts\zm\_zm_utility",
        "share/raw/scripts/zm/_zm_utility.gsc:5874 function "
        "get_player_perk_purchase_limit(); called as self.num_perks < self "
        "zm_utility::get_player_perk_purchase_limit() at :5889; #namespace "
        "zm_utility at :33",
    ),
    StockFunction(
        "zm_perks",
        "lose_random_perk",
        r"scripts\zm\_zm_perks",
        "share/raw/scripts/zm/_zm_perks.gsc:1131 function lose_random_perk(); "
        "picks a perk the player has (HasPerk or has_perk_paused, :1145) and "
        "notifies <perk>_stop (:1156-1157), which perk_think waits on (:912-913); #namespace "
        "zm_perks at :39",
    ),
    StockFunction(
        "flag",
        "exists",
        r"scripts\shared\flag_shared",
        "share/raw/scripts/shared/flag_shared.gsc:55 function exists( "
        "str_flag ); called as level flag::exists( \"solo_game\" ) at "
        "zm/_zm_perk_quick_revive.gsc:138; #namespace flag at :6",
    ),
    # A glow owned by an object (script/glow.py): the stock perk-light
    # toggle, called on a radiant exploder name from the server script.
    StockFunction(
        "exploder",
        "exploder",
        r"scripts\shared\exploder_shared",
        "share/raw/scripts/shared/exploder_shared.gsc:275 function exploder( "
        "exploder_id ); a string id goes to activate_radiant_exploder (:663, "
        "ActivateClientRadiantExploder); called as exploder::exploder( "
        "\"quick_revive_lgts\" ) at zm/_zm_perk_quick_revive.gsc:185; "
        "#namespace exploder at :11",
    ),
    StockFunction(
        "exploder",
        "stop_exploder",
        r"scripts\shared\exploder_shared",
        "share/raw/scripts/shared/exploder_shared.gsc:762 function stop_exploder( "
        "num ); a string id goes to delete_exploder_on_clients, DeactivateClientRadiantExploder at :789; "
        "called as exploder::stop_exploder( \"quick_revive_lgts\" ) at "
        "zm/_zm_perk_quick_revive.gsc:791; #namespace exploder at :11",
    ),
    StockFunction(
        "zm_unitrigger",
        "unregister_unitrigger",
        r"scripts\zm\_zm_unitrigger",
        "_zm_unitrigger.gsc:173 function unregister_unitrigger(unitrigger_stub), "
        "threads unregister_unitrigger_internal at :179-217 (deletes the live "
        "trigger, drops the stub from trigger_stubs); #namespace zm_unitrigger at :24",
    ),
)

#: Everything the checker will accept as a namespaced call.
STOCK_FUNCTIONS: tuple[StockFunction, ...] = _FROM_OUR_BUILDS + _FROM_STOCK_SCRIPTS

#: Engine functions, which are callable with no namespace and no ``#using``.
#: Same rule as the table above: read, not remembered.  Each line is where it
#: was read in the decompiled stock tree.
ENGINE_BUILTINS: dict[str, str] = {
    "isdefined": "_zm_perks.gsc:571 if ( isdefined( level.custom_perk_validation ) )",
    "getplayers": "_zm_perks.gsc:203 players = getplayers();",
    "getweapon": '_zm.gsc:1193 level.super_ee_weapon = getweapon( "pistol_burst" );',
    "dodamage": "_zm_ai_astro.gsc:646-647 damage = player.health - 1; "
                "player dodamage( damage, self.origin, self );",
    "distancesquared": "_zm_magicbox.gsc:241 if ( distancesquared( self.origin, "
                       "rubble[ i ].origin ) < 10000 )",
    "setorigin": "zm_tomb_teleporter.gsc:526 player setorigin( s_pos.origin );",
    "setplayerangles": "zm_tomb_teleporter.gsc:527 player setplayerangles( "
                       "s_pos.angles );",
    "playsoundtoplayer": 'zm_tomb_teleporter.gsc:494 player playsoundtoplayer( '
                         '"zmb_teleporter_plr_start", player );',
    "shellshock": 'zm_castle_teleporter.gsc:890 self shellshock( "explosion", 4 );',
    "earthquake": "zm_factory_teleporter.gsc:695 earthquake( 0.3, 2, "
                  "trigger.origin, 3700 );",
    "unsetperk": "_zm_perks.gsc:950 self unsetperk( perk );",
    "hasperk": '_zm_perks.gsc:552 if ( player hasperk( perk ) || ... )',
    "spawn": 'doors_shared.gsc:1190 e_trigger = spawn( "trigger_radius", '
             "e_model.origin, 0, 25, 100 );",
    "triggerignoreteam": "teamgather_shared.gsc:238 e_trigger TriggerIgnoreTeam();",
    "setvisibletoall": "teamgather_shared.gsc:239 e_trigger SetVisibleToAll();",
    "setteamfortrigger": 'teamgather_shared.gsc:240 e_trigger SetTeamForTrigger( "none" );',
    "sethintstring": '_zm_pack_a_punch_util.gsc:117 self SetHintString( '
                     '&"ZOMBIE_PERK_PACKAPUNCH_AAT", self.aat_cost );',
    "setcursorhint": 'teamgather_shared.gsc:242 e_trigger SetCursorHint( "HINT_NOICON" );',
    "iprintlnbold": '_weapons.gsc:979 player iPrintLnBold( &"MP_GRENADE_UNAVAILABLE_FOR_N", ... );',
    "iprintln": 'share/raw/scripts/zm/gametypes/_zm_gametype.gsc:815 self iprintln( '
                '&"MP_HOST_ENDGAME_RESPONSE" ); with an entity parameter, '
                'zm/gametypes/_globallogic_player.gsc:71 iPrintLn(&"MP_CONNECTED", self);',
    "getdvarstring": '_zm_ai_dogs.gsc:66 if ( GetDvarString( "scr_dog_health_walk_multiplier" ) == "" )',
    "tolower": 'load_shared.gsc:53 level.script = Tolower( GetDvarString( "mapname" ) );',
    "randomintrange": "math_shared.gsc:177 return ( RandomIntRange( -1, 1 ) >= 0 ? 1 : -1 );",
    "isplayer": "util_shared.csc:930 if (self IsPlayer())",
    "randomint": "_zm_magicbox.gsc:1457 random = randomint( 100 );",
    "gettime": "_zm_weapons.gsc:424 self.lastfiretime = gettime();",
    "getaiteamarray": "_zm_powerup_nuke.gsc:47 zombies = getaiteamarray( "
                      "level.zombie_team );",
    "isalive": "_zm_spawner.gsc:216 if ( !isalive( self ) )",
    "anglestoforward": "_zm_weap_claymore.gsc:134 objectforward = "
                       "anglestoforward( e_mine.angles );",
    "anglestoright": "_zm_blockers.gsc:1776 spots[0] + ( AnglesToRight( "
                     "self.angles ) * offset )",
    "vectornormalize": "_zm_weap_microwavegun.gsc:291 normal = vectornormalize( "
                       "test_origin - view_pos );",
    "vectordot": "_zm_weap_claymore.gsc:135 dist = vectordot( dirtopos, "
                 "objectforward );",
    "getplayerangles": "zm_genesis_cleanup_mgr.gsc:354 v_player_angles = player "
                       "getplayerangles();",
    "playsound": '_zm_powerup_nuke.gsc:126 zombies_nuked[ i ] playsound( '
                 '"evt_nuked" );',
    "playloopsound": 'shared/weapons/_flashgrenades.gsc:232 flashsound '
                     'playloopsound( level.sound_flash_loop ); a fade-in second '
                     'argument is stock too, _oob.csc:107 playloopsound( '
                     '"uin_out_of_bounds_loop", 0.5 )',
    "stoploopsound": "shared/weapons/_flashgrenades.gsc:240 flashsound "
                     "stoploopsound( 0.5 );",
    "linkto": "shared/weapons/_flashgrenades.gsc:229 flashsound linkto( self );",
    "delete": "shared/weapons/_flashgrenades.gsc:243 flashsound delete();",
    "triggerenable": "shared/trigger_shared.gsc:476 trigger TriggerEnable( false );",
    # Read in the mod tools install's own share/raw/scripts,
    # which is what the linker compiles, rather than in the decompile.
    "getminbitcountfornum": '_zm_score.gsc:106 clientfield::register( '
                            '"clientuimodel", "PlayerList.client" + i + '
                            '".score_cf_" + name, version, '
                            "GetMinBitCountForNum( max_count ), \"counter\" );",
    "luiload": 'shared/debug_menu_shared.csc:16 LuiLoad( '
               '"uieditor.menus.ScriptDebugMenu" );  the one call in the '
               "shipped scripts.  Real, and of no use to a usermap: nothing "
               "generated calls it, because the Lua it would load cannot be "
               "packed -- the linker answers a .lua rawfile with 'ERROR: Lua "
               "not supported'.  Kept because the "
               "builtin exists and a hand-written script may say so",
    "spawnstruct": "_zm_laststand.csc:21 level.laststands[ i ] = SpawnStruct();",
    "setmovespeedscale": "zm_usermap.gsc:336 self SetMoveSpeedScale( 1 ); the "
                         "usermap's own spawn path, and _zm.gsc:4795 self "
                         "setMoveSpeedScale( 0.3 ); on a zombified player, "
                         "which is what says the argument is a scale on base "
                         "movement and that 1 is this game's normal",
    # Read in share/raw/scripts, for zmforge.script.quest and
    # zmforge.script.bosses.
    "newclienthudelem": "shared/teamgather_shared.gsc:813 hud_elem = "
                        "NewClientHudElem( self ); also zm/_zm_laststand.gsc:1199",
    "settext": 'zm/_zm.gsc:6080 game_over[i] SetText( &"ZOMBIE_GAME_OVER" ); two '
               'parameters: shared/teamgather_shared.gsc:733 ready_hud_elem setText( '
               '&"TEAM_GATHER_PLAYERS_READY", m_num_players_ready, m_num_players );',
    "fadeovertime": "zm/_zm.gsc:6082 game_over[i] FadeOverTime( 1 );",
    "destroy": "zm/_zm_laststand.gsc:448 self.reviveTextHud destroy(); (a HUD "
               "element, not an entity: entities use delete)",
    "setmodel": 'shared/containers_shared.gsc:277-278 e_collectable = spawn( '
                '"script_model", v_pos ); e_collectable setModel( '
                '"p7_int_narrative_collectable" ); no #precache of the model in '
                "that file",
    "playfx": 'zm/_zm_powerups.gsc:925 playfx( level._effect["powerup_grabbed_red"], '
              "self.origin );",
    "playfxontag": 'zm/_zm_traps.gsc:1025 PlayFxOnTag( level._effect["elec_torso"], '
                   'self, "J_SpineLower" ); on a zombie',
    "randomfloatrange": "zm/_zm_ai_wasp.gsc:1332 wait randomfloatrange(3,6);",
    "distance2dsquared": "zm/_zm_ai_wasp.gsc:1291 dist2 = Distance2DSquared( peye, "
                         "self.origin );",
    "detach": 'shared/ai/systems/gib.gsc:230 entity Detach( gibModel, "" ); '
              "on an actor, the head model when its head gibs",
    "abs": "zm/_zm_ai_wasp.gsc:483 n_height_diff = abs( v_target[2] - v_position[2] );",
    "geteye": "zm/_zm_ai_wasp.gsc:1290 peye = player GetEye();",
    "getweaponforwarddir": "zm/_zm_ai_wasp.gsc:1298 pfwd = player GetWeaponForwardDir();",
    "vectorscale": "zm/_zm_weap_riotshield.gsc:368 end_pos = view_pos + VectorScale( "
                   'forward_view_angles, level.zombie_vars["riotshield_knockdown_range"] );',
    "bullettrace": "shared/colors_shared.gsc:398 a_trace = BulletTrace( v_eye, target, "
                   'false, player ); read as a_trace["fraction"] at :399',
    "int": "shared/ai/zombie_utility.gsc:1915 level.zombie_health += Int( "
           'level.zombie_health * level.zombie_vars["zombie_health_increase_multiplier"] );',
    # The hayride and the farm gags (zmforge.script.hayride, recipes.corn_maze_script).
    "playerlinktodelta": 'shared/doors_shared.gsc:896 self PlayerLinkToDelta(self.freeze_origin, '
                         '"tag_origin", 1.0, 45.0, 45.0, 45.0, 45.0 );',
    "unlink": "shared/vehicleriders_shared.gsc:632 self Unlink();",
    "moveto": "zm/_zm_blockers.gsc:579 self MoveTo( self.origin + vector, time, time * 0.25, "
              "time * 0.25 );",
    "rotateto": "shared/doors_shared.gsc:208 m_e_door RotateTo( v_angle, "
                "m_s_bundle.door_open_time );",
    "vectortoangles": "shared/util_shared.gsc:1154 plant_angle = VectorToAngles( tangent );",
    "setscale": "shared/ai/archetype_robot.gsc:3520 wasp SetScale( 0.75 );",
    "setcandamage": "shared/weapons/_trophy_system.gsc:367 self SetCanDamage( true );",
    "radiusdamage": "shared/ai/raz.gsc:1637 RadiusDamage( self.origin + (0,0,18), "
                    "RAZ_GUN_DETACH_EXPLOSION_RADIUS, explosion_max_damage, "
                    'explosion_min_damage, entity, "MOD_PROJECTILE_SPLASH" ...',
    "enableinvulnerability": "shared/vehicle_ai_shared.gsc:1749 params.driver "
                             "EnableInvulnerability();",
    "disableinvulnerability": "shared/vehicles/_quadrotor.gsc:502 player "
                              "DisableInvulnerability();",
    # Read in share/raw/scripts, for boarding a moving ride
    # (zmforge.script.hayride: a use trigger linked to the base, parts not
    # solid while it drives).
    "enablelinkto": "zm/_zm_laststand.gsc:850 self.revivetrigger EnableLinkTo(); "
                    "(a spawned trigger_radius, LinkTo( self ) at :852)",
    "setmovingplatformenabled": "zm/_zm_laststand.gsc:849 self.revivetrigger "
                                "SetMovingPlatformEnabled( true );",
    "notsolid": "zm/_zm_perks.gsc:253 newMachine NotSolid();",
    "solid": "zm/_zm_blockers.gsc:526 self Solid();",
    # Read in share/raw/scripts, for a boss that climbs off a
    # prop and must land where it can path (zmforge.script.bosses spawn_snap).
    "getclosestpointonnavmesh": "zm/_zm_behavior.gsc:320 nav_mesh = GetClosestPointOnNavMesh( "
                                "behaviorTreeEntity.attackable_slot.origin, 64 );",
    "hide": "shared/doors_shared.gsc:1103 e_model Hide();",
    "length": "shared/ai_sniper_shared.gsc:540 phase = Length( self.velocity ) / "
              "(decelerateTime * 2);",
    "distance": "zm/_zm_ai_wasp.gsc:469 n_distance_to_target = Distance( v_start, v_target );",
    "forceteleport": "_zm_ai_dogs.gsc:332 ai forceteleport( ent.origin, angles ); "
                     "also _zm_ai_raz.gsc:414 and inside spawn_zombie itself, "
                     "shared/ai/zombie_utility.gsc:1908",
    # Read in share/raw/scripts, for the boss marker
    # (zmforge.script.bosses).
    "newhudelem": "zm/_zm_utility.gsc:3969 level.introblack = NewHudElem();",
    "setshader": 'zm/_zm_ai_wasp.gsc:382 self.hud_damagefeedback SetShader( '
                 '"damage_feedback", 24, 48 );',
    "setwaypoint": "shared/entityheadicons_shared.gsc:164 headicon setwaypoint( "
                   "constant_size );",
    "settargetent": "shared/entityheadicons_shared.gsc:165 headicon SetTargetEnt( entity );",
    # Read in share/raw/scripts, for the split start
    # (zmforge.script.splitstart).
    "kill": "zm/zm_giant_cleanup_mgr.gsc:237 self Kill(); (a zombie, after "
            "level.zombie_total++ at :223 puts it back to be respawned)",
    # Read in share/raw/scripts, for per-player use triggers and the entity
    # lookups a mechanic's stations make.
    "setinvisibletoplayer": "zm/_zm_traps.gsc:429 self SetInvisibleToPlayer( "
                            "level.players[i], true ); (a trap's use trigger, "
                            "false again at :433)",
    "getentarray": 'zm/_zm_blockers.gsc:80 zombie_doors = GetEntArray( '
                   '"zombie_door", "targetname" );',
    "getent": 'zm/_zm_clone.gsc:40 spawner = GetEnt( "fake_player_spawner", '
              '"targetname" );',
    "strtok": 'zm/_zm_blockers.gsc:954 tokens = Strtok( trig.script_flag, "," );',
    # Read in share/raw/scripts, for the GobbleGum gate
    # (zmforge.script.gobblegum).
    "getnumzbarrierpieces": "zm/_zm_blockers.gsc:1426 for( i = 0; i < self "
                            "GetNumZBarrierPieces(); i++ )",
    "hidezbarrierpiece": "zm/_zm_magicbox.gsc:1417 self HideZBarrierPiece(3);",
    # Read in share/raw/scripts, for the boss-health test map
    # (loadout, ammo top-up, HUD numbers, console line).
    "getweaponslistprimaries": "zm/_zm_clone.gsc:24 primaryWeapons = player "
                               "GetWeaponsListPrimaries();",
    "givemaxammo": "zm/_zm_powerup_full_ammo.gsc:111 players[i] GiveMaxAmmo( "
                   "primary_weapons[x] );",
    "giveweapon": "zm/_zm_weapons.gsc:2597 self GiveWeapon( weapon, weapon_options, acvi );",
    "switchtoweapon": "zm/_zm_weapons.gsc:313 self SwitchToWeapon( oldprimary );",
    "setvalue": "zm/_zm.gsc:4036 level.countdown_hud SetValue( delay );",
    "println": "zm/_zm.gsc:7191 PrintLn(outputString); (inside a /# #/ block, as "
               "every stock call is; Treyarch's bo3_scriptapifunctions.htm lists "
               "void PrintLn(<text>) as a Server function)",
}

_INDEX = {function.call: function for function in STOCK_FUNCTIONS}

#: The builtins by lower-cased name.  GSC is case insensitive and the
#: stock scripts prove it -- ``_zm_laststand.gsc:173 if( isdefined( ... ) )``
#: against ``:298 if ( IsDefined(self) ... )``, same file -- so a table
#: keyed by one spelling would reject the other for no reason the compiler
#: would agree with.  The table above keeps the spelling it was read in,
#: because that is the evidence; the lookup folds case.
_BUILTIN_NAMES = {name.lower() for name in ENGINE_BUILTINS}


def namespace_module(namespace: str) -> set[str]:
    """Every module that provides ``namespace``."""
    return {f.module for f in STOCK_FUNCTIONS if f.namespace == namespace}


def lookup(call: str) -> StockFunction | None:
    """The table entry for ``ns::name``, or ``None`` if it is not known."""
    return _INDEX.get(call)


def unresolved(source, *, known_namespaces: set[str] | None = None) -> list:
    """Issues for calls nothing defines, over a scanned :class:`ScriptSource`.

    Three failures, all of which are fatal at run time and silent at compile
    time:

    ``gsc_undefined``
        an unqualified call or ``&pointer`` to a function the file does not
        define;
    ``gsc_unknown_symbol``
        a namespaced call that is not in this table, so nothing here can say
        it exists;
    ``gsc_missing_using``
        a namespaced call whose module the script never ``#using``s.

    ``known_namespaces`` is an escape hatch for a caller that has read a
    stock script this table does not cover yet: the namespace is then
    accepted without a per-function entry, and the missing-``#using`` check
    still applies to the ones the table does know.
    """
    from .gsc import Issue  # local import: gsc imports nothing from here

    known_namespaces = known_namespaces or set()
    issues: list[Issue] = []

    for name, line in source.bare_calls:
        if name not in source.defined and name.lower() not in _BUILTIN_NAMES:
            issues.append(
                Issue(
                    "gsc_undefined",
                    line,
                    f"{name}() is called but nothing in this script defines it",
                )
            )
    for namespace, name, line in source.pointers:
        if namespace is None:
            if name not in source.defined:
                issues.append(
                    Issue(
                        "gsc_undefined",
                        line,
                        f"&{name} points at a function nothing defines; GSC "
                        "resolves function pointers when the script loads",
                    )
                )
            continue
        issues.extend(_check_qualified(namespace, name, line, source,
                                       known_namespaces, Issue))
    for namespace, name, line in source.qualified_calls:
        issues.extend(_check_qualified(namespace, name, line, source,
                                       known_namespaces, Issue))
    return issues


def _check_qualified(namespace, name, line, source, known_namespaces, Issue):
    call = f"{namespace}::{name}"
    entry = lookup(call)
    if entry is None:
        if namespace in known_namespaces:
            return []
        return [
            Issue(
                "gsc_unknown_symbol",
                line,
                f"{call}() is not in the stock symbol table, so nothing here "
                "can say it exists; read it out of the stock script and add "
                "it, or the map dies when the line runs",
            )
        ]
    if entry.module not in source.using:
        return [
            Issue(
                "gsc_missing_using",
                line,
                f"{call}() needs '#using {entry.module};' and the script has "
                "no such line",
            )
        ]
    return []
