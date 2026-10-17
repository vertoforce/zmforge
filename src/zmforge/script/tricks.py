"""Gameplay mechanics built on the seam, each one traced to a stock script.

Every function here returns a :class:`~zmforge.script.custom.CustomScript` a
caller can hand to ``Blueprint.add_custom_logic``.  They are ordinary users
of the seam and hold no privileges: what they buy is that the hook each one
relies on has been read out of the stock scripts and the reference is
recorded next to the code that uses it.

**None of this has been played.**  The evidence below is what the stock
scripts say the hooks are; whether a gag is funny, whether the timing lands,
and whether a HUD icon lingers are questions only a play session answers.
Every docstring says which parts are unverified.

Sources are the decompiled stock tree at ``github.com/ate47/bo3-source``,
cited as ``<file>:<line>`` (read for reference only, no decompiled code is copied; where the
mod tools ship the same script in ``share/raw/scripts``, search it for the
function name, the line can differ), read.  Two hooks are level-wide
singletons -- ``level.custom_perk_validation`` and ``level.perk_bought_func``
-- so the perk gags are one function with lists rather than one function per
gag, which is the only way two of them can coexist.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

from ..blueprint.catalogue import BOX_WEAPONS, LEVEL_WEAPONS
from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "spawn_point_lines",
    "take_a_ticket",
    "TicketCalls",
    "TICKET_SERVED_FLAG",
    "use_notices",
    "mega_blast_on_fire",
    "overtime_on_fire",
    "relocation_on_fire",
    "consultancy_fee_on_fire",
    "job_creation_on_fire",
    "panic_button_on_fire",
    "perk_pranks",
    "rigged_mystery_box",
    "spawn_spike_on_flag",
    "closet_ambush",
    "short_hop_teleporter",
    "PERK_SPECIALTY",
    "starting_points",
    "STOCK_STARTING_POINTS",
]

#: Perk slug -> the ``specialty_`` string the machine's trigger carries and
#: the hooks are passed.  Read from each perk module's own script:
#: ``_zm_perk_juggernaut.gsc`` "specialty_armorvest",
#: ``_zm_perk_sleight_of_hand.gsc`` "specialty_fastreload",
#: ``_zm_perk_quick_revive.gsc`` "specialty_quickrevive",
#: ``_zm_perk_doubletap2.gsc`` "specialty_doubletap2",
#: ``_zm_perk_deadshot.gsc`` "specialty_deadshot",
#: ``_zm_perk_staminup.gsc`` "specialty_staminup",
#: ``_zm_perk_additionalprimaryweapon.gsc`` "specialty_additionalprimaryweapon".
PERK_SPECIALTY: dict[str, str] = {
    "juggernog": "specialty_armorvest",
    "speed_cola": "specialty_fastreload",
    "quick_revive": "specialty_quickrevive",
    "double_tap": "specialty_doubletap2",
    "deadshot": "specialty_deadshot",
    "stamin_up": "specialty_staminup",
    "mule_kick": "specialty_additionalprimaryweapon",
}

_LASTSTAND = r"scripts\shared\laststand_shared"
_LUI = r"scripts\shared\lui_shared"
_ZOMBIE_UTILITY = r"scripts\shared\ai\zombie_utility"
_HUD = r"scripts\shared\hud_shared"
_PERKS = r"scripts\zm\_zm_perks"
_SCORE = r"scripts\zm\_zm_score"
_POWERUPS = r"scripts\zm\_zm_powerups"
_FLAG = r"scripts\shared\flag_shared"
#: Powerups the ticket window may hand out: the names the modules
#: ``zm_usermap.gsc:40-47`` loads register (``_zm_powerup_double_points.gsc:35``,
#: ``_zm_powerup_insta_kill.gsc:34``, ``_zm_powerup_full_ammo.gsc:37``).
_TICKET_POWERUPS = ("double_points", "insta_kill", "full_ammo")


def _ms(seconds: float) -> int:
    return int(round(float(seconds) * 1000))


def _vector(point) -> str:
    x, y, z = (getattr(point, axis, None) for axis in ("x", "y", "z"))
    if x is None:
        x, y, z = point
    return f"( {float(x):g}, {float(y):g}, {float(z):g} )"


# --------------------------------------------------------------------------
# The gun that downs you
# --------------------------------------------------------------------------
def mega_blast_on_fire(
    weapon: str = "shotgun_pump",
    *,
    range_units: float = 768.0,
    cone_degrees: float = 120.0,
    down_delay: float = 0.25,
    deafen_asset: str | None = "explosion",
    deafen_seconds: float = 6.0,
    ring_alias: str | None = None,
    ring_seconds: float = 6.0,
    ring_fade: float = 0.25,
    ring_bank: str | None = None,
) -> CustomScript:
    """Firing ``weapon`` wipes out the zombies in front of you, and downs you.

    A trade, not a punishment: the blast is real, the kills are real, and the
    shooter is on the floor a quarter of a second later.

    **The kill** is the nuke's, function for function, because the nuke is
    the stock code for "kill these zombies with something worth watching":

    * ``_zm_powerup_nuke.gsc:47`` ``zombies = getaiteamarray( level.zombie_team );``
      is how a script gets every live zombie;
    * ``:120`` ``zombies_nuked[ i ] zombie_utility::zombie_head_gib();`` and
      ``:126`` ``playsound( "evt_nuked" );`` are the visible and audible part;
    * ``:127`` ``zombies_nuked[ i ] dodamage( zombies_nuked[ i ].health + 666,
      zombies_nuked[ i ].origin );`` is the kill itself;
    * ``:89`` skips any AI with ``zm_utility::is_magic_bullet_shield_enabled``,
      which is what keeps a boss or a scripted character out of it, and
      ``:96`` marks each one ``marked_for_death`` so nothing processes it twice.
    * ``:157`` ``lui::screen_flash( 0.2, 0.5, 1, 0.8, "white" );`` is the flash.

    Two things the nuke does are deliberately **not** copied.
    ``clientfield::increment( "zm_nuked" )`` (``:100``) is skipped because
    that client field is registered by the nuke's own ``__init__``
    (``:34``), and incrementing an unregistered field is exactly the kind of
    fatal error this engine exists to avoid.  ``playfx`` is skipped because
    it takes a ``level._effect[ ... ]`` handle (``zm_asylum.gsc:815``) and a
    usermap registers no effects, so the handle would be undefined.

    **The cone.**  A cone in front is not harder than a radius, so it is a
    cone: ``anglestoforward`` (``_zm_weap_claymore.gsc:134``) and
    ``vectordot`` (``:135``) are the stock pair for "is this in front of
    that", and ``vectornormalize`` of a vector flattened to XY is stock too
    (``_zm_weap_elemental_bow.gsc:524``).  Player aim comes from
    ``getplayerangles`` (``zm_genesis_cleanup_mgr.gsc:354``).  The test is
    flattened to the ground plane, so a zombie up a staircase in front still
    counts; ``cone_degrees`` at 360 or more drops the test and the blast
    becomes a radius around the player.

    **The shooter's hearing.**  ``shellshock( <asset>, <duration>, <flag> )``
    is the game's own concussion effect: the flashbang applies it to whoever
    it caught, ``shared/weapons/_flashgrenades.gsc:203 self shellshock(
    "flashbang", self.flashduration, 0 );``, and in zombies it is what core
    code does to a player standing near a blast --
    ``_zm_ai_napalm.gsc:740 players[ i ] shellshock( "explosion",
    shellshocktime );``, ``_zm_ai_quad.gsc:348 players[ i ] shellshock(
    "explosion", 2.5 );``.  ``deafen_asset`` defaults to ``"explosion"`` for
    that reason, and to ``None`` turns it off.

    **The ringing tone is a separate thing and stock zombies does not wire
    one up.**  The flashbang's ringing is a looping alias played on a
    script_origin linked to the player, ``_flashgrenades.gsc:227-243``, and
    the alias comes from ``level.sound_flash_loop`` -- which the shared code
    sets to ``""`` at ``:15-17`` and which nothing in the zombies or campaign
    trees ever assigns.  The only tinnitus loop in the whole script tree is
    ``cp_prologue_player_sacrifice.gsc:966 playloopsound(
    "evt_outro_tinnitus_lp", 4 )``, a **campaign** alias whose sound bank a
    zombies usermap does not load.  Whether the ``explosion`` shock asset
    itself carries a ring as well as a muffle cannot be read here: shock
    assets are not script, they are in the tools install.

    So ``ring_alias`` is off by default and plays nothing rather than
    guessing an alias: an unregistered sound is exactly the class of runtime
    failure this engine refuses to ship.  Given an alias it plays it the
    flashbang's way, and ``ring_bank`` declares the sound bank that carries
    it so the manifest asks the linker for it.

    **The down** is unchanged: damage above health takes the laststand branch
    (``_zm.gsc:5354`` returns early below health, ``:5464`` threads
    ``playerlaststand``), and ``down_delay`` puts it after the kills so the
    shooter watches the room fall over before they do.

    The trap keys on the **weapon**, because that is what ``weapon_fired``
    carries: every copy of it is trapped, wherever the map sells it and
    however the player came by it.  Pick a weapon the map sells once.

    **The shooter's screen.**  The white flash is threaded on the shooter,
    ``self thread lui::screen_flash( ... )``, the way stock threads a fade on
    one player (``archetype_thrasher.gsc:1201 player thread
    lui::screen_fade_in( 10 );``).  It used to be threaded on ``level``, the
    way the nuke does it, and that is a broadcast: ``screen_flash`` tests
    ``if ( self == level )`` and re-threads itself on every player in
    ``level.players`` (``shared/lui_shared.gsc:434-439``), which its own
    header states -- ``"CallOn: player or level (for all players)"``.  The
    unscoped call flashes every player off one shooter's gun, so the call is scoped to the shooter.  The hearing
    (``shellshock``) was always on ``self`` and is unchanged.

    The ``earthquake( scale, duration, origin, radius )`` shake is **not**
    per-player and is left alone: it is an engine call that takes a point and
    a radius, and stock always calls it that way (``_fx.gsc:156``,
    ``zm_factory_teleporter.gsc:695``), so a player standing inside the
    radius feels it.  It is a rumble, not a flash.

    **Unverified:** everything about how it reads in play.  Specifically:
    that the gibs land before the shooter does; that ``evt_nuked`` is a sound
    a usermap's zone carries; and that a solo player with no Quick Revive
    dies rather than goes down (``_zm.gsc:5457``).
    """
    if range_units <= 0:
        raise ValueError("a blast with no range would kill nothing")
    if ring_bank and not ring_alias:
        raise ValueError(
            "a sound bank was declared but no alias is played from it"
        )
    radius_sq = float(range_units) ** 2
    cone = float(cone_degrees)
    everywhere = cone >= 360.0
    cos_half = math.cos(math.radians(cone / 2.0))

    blast: list[str] = [
        'self endon( "disconnect" );',
        'level endon( "end_game" );',
        "v_from = self.origin;",
    ]
    if not everywhere:
        blast += [
            "v_forward = anglestoforward( self getplayerangles() );",
            "v_forward = vectornormalize( ( v_forward[ 0 ], v_forward[ 1 ], 0 ) );",
        ]
    if deafen_asset:
        # First, so the bang and the hearing loss land together.
        blast.append(
            f'self shellshock( "{deafen_asset}", {float(deafen_seconds):g}, 0 );'
        )
    if ring_alias:
        blast.append("self thread zmf_mega_blast_ring();")
    blast += [
        # On the shooter, not on level: lui_shared.gsc:434-439 fans a
        # level-scoped call out to every player.
        'self thread lui::screen_flash( 0.1, 0.4, 0.6, 0.8, "white" );',
        "earthquake( 0.6, 1.5, v_from, 1200 );",
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
        "\tif ( isdefined( a_zombies[ i ].marked_for_death ) && "
        "a_zombies[ i ].marked_for_death )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tn_dist_sq = distancesquared( v_from, a_zombies[ i ].origin );",
        f"\tif ( n_dist_sq > {radius_sq:g} )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
    ]
    if not everywhere:
        blast += [
            "\tif ( n_dist_sq > 1 )",
            "\t{",
            "\t\tv_to = a_zombies[ i ].origin - v_from;",
            "\t\tv_to = vectornormalize( ( v_to[ 0 ], v_to[ 1 ], 0 ) );",
            f"\t\tif ( vectordot( v_to, v_forward ) < {cos_half:.6g} )",
            "\t\t{",
            "\t\t\tcontinue;",
            "\t\t}",
            "\t}",
        ]
    blast += [
        "\ta_zombies[ i ].marked_for_death = 1;",
        '\ta_zombies[ i ] playsound( "evt_nuked" );',
        "\tif ( !( isdefined( a_zombies[ i ].no_gib ) && a_zombies[ i ].no_gib ) )",
        "\t{",
        "\t\ta_zombies[ i ] zombie_utility::zombie_head_gib();",
        "\t}",
        "\ta_zombies[ i ] dodamage( a_zombies[ i ].health + 666, "
        "a_zombies[ i ].origin );",
        "}",
        f"wait {float(down_delay):g};",
        "if ( self laststand::player_is_in_laststand() )",
        "{",
        "\treturn;",
        "}",
        "self dodamage( self.health + 100, self.origin, self );",
    ]

    watcher = CustomFunction(
        "zmf_trap_gun_watch",
        (
            'self endon( "disconnect" );',
            'level endon( "end_game" );',
            "if ( isdefined( self.zmf_trap_gun_watching ) )",
            "{",
            "\treturn;",
            "}",
            "self.zmf_trap_gun_watching = 1;",
            f'w_trap = getweapon( "{weapon}" );',
            "while ( true )",
            "{",
            '\tself waittill( "weapon_fired", w_fired );',
            "\tif ( !isdefined( w_fired ) || w_fired != w_trap )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\tif ( self laststand::player_is_in_laststand() )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\tself thread zmf_mega_blast();",
            "}",
        ),
        purpose=(
            f"Watch for a shot from {weapon}.\n"
            "weapon_fired carries the weapon: _zm_weapons.gsc:423.\n"
            "getweapon: _zm.gsc:1193."
        ),
    )
    detonation = CustomFunction(
        "zmf_mega_blast",
        tuple(blast),
        purpose=(
            (
                f"Kill every zombie within {float(range_units):g} units"
                + (
                    " of the shooter"
                    if everywhere
                    else f" in a {cone:g} degree cone in front"
                )
                + ", then down the shooter.\n"
            )
            + "The kill is the nuke's: getaiteamarray _zm_powerup_nuke.gsc:47,\n"
            "head gib :120, evt_nuked :126, dodamage health+666 :127,\n"
            "shielded AI skipped :89, screen flash :157 but on the\n"
            "shooter, not on level (lui_shared.gsc:434-439 fans a\n"
            "level-scoped flash out to every player).\n"
            + (
                ""
                if everywhere
                else "In front: anglestoforward and the dot product, "
                "_zm_weap_claymore.gsc:134-135.\n"
            )
            + "The down: damage above health, _zm.gsc:5354 and :5464."
        ),
    )
    extra: list[CustomFunction] = []
    if ring_alias:
        extra.append(
            CustomFunction(
                "zmf_mega_blast_ring",
                (
                    'self endon( "death" );',
                    'self endon( "disconnect" );',
                    'e_snd = spawn( "script_origin", ( 0, 0, 1 ) );',
                    "e_snd.origin = self.origin;",
                    "e_snd linkto( self );",
                    "e_snd thread zmf_sound_follows( self );",
                    f'e_snd playloopsound( "{ring_alias}", {float(ring_fade):g} );',
                    f"wait {float(ring_seconds):g};",
                    "e_snd stoploopsound( 0.5 );",
                    "wait 0.5;",
                    'e_snd notify( "delete" );',
                    "e_snd delete();",
                ),
                purpose=(
                    "The ringing, played the flashbang's way.\n"
                    "shared/weapons/_flashgrenades.gsc:227-243: a script_origin\n"
                    "linked to the player, a looping alias, then stop and delete."
                ),
            )
        )
        extra.append(
            CustomFunction(
                "zmf_sound_follows",
                (
                    'self endon( "delete" );',
                    'e_owner waittill( "death" );',
                    "self delete();",
                ),
                params=("e_owner",),
                purpose=(
                    "So the sound entity cannot outlive who it follows.\n"
                    "shared/weapons/_flashgrenades.gsc:250-255."
                ),
            )
        )

    watcher_all = CustomFunction(
        "zmf_trap_gun_watch_players",
        (
            'level endon( "end_game" );',
            "players = getplayers();",
            "for ( i = 0; i < players.size; i++ )",
            "{",
            "\tplayers[ i ] thread zmf_trap_gun_watch();",
            "}",
            "while ( true )",
            "{",
            '\tlevel waittill( "connected", player );',
            "\tplayer thread zmf_trap_gun_watch();",
            "}",
        ),
        purpose=(
            "One watcher per player, now and on join.\n"
            'level waittill( #"connected", player ): _zm.gsc:482.\n'
            "getplayers(): _zm_perks.gsc:203."
        ),
    )
    hearing = []
    if deafen_asset:
        hearing.append(f"{float(deafen_seconds):g}s of {deafen_asset} shellshock")
    if ring_alias:
        hearing.append(f"{float(ring_seconds):g}s of {ring_alias} ringing")

    return CustomScript(
        using=(_LASTSTAND, _LUI, _ZOMBIE_UTILITY),
        functions=(watcher_all, watcher, detonation, *extra),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_trap_gun_watch_players();"),),
        assets=(("sound", ring_bank),) if ring_bank else (),
        notes=(
            f"wall weapon {weapon} clears "
            + ("a radius" if everywhere else f"a {cone:g} degree cone")
            + f" of {float(range_units):g} units and downs the shooter"
            + (", with " + " and ".join(hearing) if hearing else ""),
        ),
    )


# --------------------------------------------------------------------------
# Perk machine gags
# --------------------------------------------------------------------------
def perk_pranks(
    *,
    refuse: Sequence[str] = (),
    takes_money: Sequence[str] = (),
    take_back_after: float = 4.0,
) -> CustomScript:
    """Machines that refuse, and machines that charge and give nothing.

    Both stock hooks are single level variables, so both gags live in one
    pair of functions and are selected by perk:

    * ``_zm_perks.gsc:571`` ``if ( isdefined( level.custom_perk_validation ) )``
      / ``:573`` ``valid = self [[ level.custom_perk_validation ]]( player );``
      with ``continue`` on a false return.  ``self`` there is the machine's
      trigger, whose ``script_noteworthy`` is the perk's specialty string, so
      one function can answer for every machine.  This runs **before**
      ``player zm_score::minus_to_player_score( current_cost );`` at ``:612``,
      so a refused machine costs the player nothing.  That is the "looks
      available, is not" gag.
    * ``give_perk`` grants the perk at ``_zm_perks.gsc:737``
      ``self setperk( perk );``.  The money is already gone by then (``:612``)
      and the jingle already played (``:619``
      ``self thread zm_audio::sndperksjingles_player( 1 );``).  Taking the
      perk back afterwards is therefore "jingle, charge, nothing", and the
      sequence used is the stock one from the perk-lose path,
      ``_zm_perks.gsc:950-958``: ``self unsetperk( perk ); self.num_perks--;
      self set_perk_clientfield( perk, 0 );``.  The hook that tells us a
      purchase happened is ``:657`` ``player [[ level.perk_bought_func ]]( perk );``.

    ``take_back_after`` is a wait, not a synchronisation: the grant is
    threaded from ``vending_trigger_post_think`` and the hook call is not
    ordered against it, so the function waits and then checks ``hasperk``
    before taking anything.

    **Unverified:** the wait being long enough to let the drink animation
    finish, and whether the HUD icon clears when the client field goes to 0.
    """
    refused = [PERK_SPECIALTY.get(p, p) for p in refuse]
    robbed = [PERK_SPECIALTY.get(p, p) for p in takes_money]
    if not refused and not robbed:
        return CustomScript()

    functions: list[CustomFunction] = []
    statements: list[tuple[Slot, str]] = []

    if refused:
        body = [
            "if ( !isdefined( self.script_noteworthy ) )",
            "{",
            "\treturn 1;",
            "}",
        ]
        for specialty in refused:
            body += [
                f'if ( self.script_noteworthy == "{specialty}" )',
                "{",
                "\treturn 0;",
                "}",
            ]
        body.append("return 1;")
        functions.append(
            CustomFunction(
                "zmf_perk_validation",
                tuple(body),
                params=("player",),
                purpose=(
                    "Machines that never sell. self is the vending trigger.\n"
                    "_zm_perks.gsc:571-573; returning 0 makes the think loop\n"
                    "continue before the charge at :612, so it costs nothing."
                ),
            )
        )
        statements.append(
            (Slot.AFTER_ENTRY, "level.custom_perk_validation = &zmf_perk_validation;")
        )

    if robbed:
        tests = " && ".join(f'perk != "{specialty}"' for specialty in robbed)
        functions.append(
            CustomFunction(
                "zmf_perk_bought",
                (
                    "if ( !isdefined( perk ) )",
                    "{",
                    "\treturn;",
                    "}",
                    f"if ( {tests} )",
                    "{",
                    "\treturn;",
                    "}",
                    "self thread zmf_perk_take_back( perk );",
                ),
                params=("perk",),
                purpose=(
                    "Charged, jingled, granted, then quietly taken back.\n"
                    "_zm_perks.gsc:657 player [[ level.perk_bought_func ]]( perk );"
                ),
            )
        )
        functions.append(
            CustomFunction(
                "zmf_perk_take_back",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    f"wait {float(take_back_after):g};",
                    "if ( !self hasperk( perk ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "self unsetperk( perk );",
                    "if ( isdefined( self.num_perks ) && self.num_perks > 0 )",
                    "{",
                    "\tself.num_perks--;",
                    "}",
                    "self zm_perks::set_perk_clientfield( perk, 0 );",
                    "self.perk_purchased = undefined;",
                ),
                params=("perk",),
                purpose=(
                    "The stock take-a-perk-back sequence, _zm_perks.gsc:950-959."
                ),
            )
        )
        statements.append(
            (Slot.AFTER_ENTRY, "level.perk_bought_func = &zmf_perk_bought;")
        )

    return CustomScript(
        using=(_PERKS,) if robbed else (),
        functions=tuple(functions),
        statements=tuple(statements),
        notes=tuple(
            [f"perk machine {p} refuses to sell" for p in refuse]
            + [f"perk machine {p} charges and gives nothing" for p in takes_money]
        ),
    )


# --------------------------------------------------------------------------
# The rigged box
# --------------------------------------------------------------------------
def rigged_mystery_box(
    weapon: str = "shotgun_semiauto",
    *,
    origin=None,
    radius: float = 160.0,
    also: Sequence[tuple[str, object, float]] = (),
) -> CustomScript:
    """A box that spins, opens, and always produces the same weapon.

    The box picks in ``_zm_magicbox.gsc:1262``
    ``treasure_chest_chooseweightedrandomweapon( player )``, which shuffles
    the candidate array at ``:1264``
    ``keys = array::randomize( getarraykeys( level.zombie_weapons ) );`` and
    returns the first candidate that passes eligibility at ``:1279-1281``.
    Immediately after the shuffle, ``:1266-1268``:
    ``if ( isdefined( level.customrandomweaponweights ) )`` /
    ``keys = player [[ level.customrandomweaponweights ]]( keys );``.  The
    hook replaces the candidate array, so putting one weapon first forces
    every spin **without touching the animation or the reveal** -- the choice
    is made before any of the presentation runs.  Stock maps use the hook as
    a passthrough: ``zm_zod.gsc:197`` sets it and ``zm_zod.gsc:1422-1424``
    returns ``keys`` unchanged.

    **Two boxes, one hook.**  ``level.customrandomweaponweights`` is a single
    level variable and the hook is passed the player, not the chest, so two
    calls to this function cannot both own it and merging them is refused.
    ``also`` is how a map rigs more than one box: each entry is
    ``(weapon, origin, radius)`` and the emitted hook tests them in order by
    how far the player is from each box when the spin resolves
    (``distancesquared``, ``_zm_magicbox.gsc:241``), falling through to the
    untouched array when the player is near none of them.  So a map can have a
    box that always gives one thing in one room and a box that always gives
    another somewhere else, and an unrigged box anywhere in between still
    behaves normally.

    Two honest limits, both read rather than assumed:

    * the discrimination is by distance, not by identity, so two rigged boxes
      closer together than their radii would shadow each other -- the first
      match wins.
    * a weapon the player already owns is rejected at ``:1199``
      ``player zm_weapons::has_weapon_or_upgrade( weapon )``, and the loop
      then falls back to ``return keys[ 0 ]`` at ``:1285``, which is this
      weapon again.  The rest of the array is kept behind it so the box still
      has something to give if the forced weapon is not in the map's weapon
      set at all.

    The second limit is why the weapon is checked here rather than left to
    the game.  ``shotgun_olympia`` used to be the default and it is **not** a
    Black Ops III weapon at all: it is in neither
    ``gamedata/weapons/zm/zm_levelcommon_weapons.csv`` nor any assetlist
    under ``zone_source/*/assetlist`` on the install.
    ``a_out`` therefore came back empty on every spin, the hook returned
    ``a_keys`` untouched, and the box gave out random weapons with no sign
    that anything had been asked of it.  A name outside
    :data:`~zmforge.blueprint.catalogue.BOX_WEAPONS` now raises instead.

    **Unverified:** that the player is standing inside ``radius`` of the box
    at the moment the choice resolves.
    """
    rigs: list[tuple[str, object, float]] = [(weapon, origin, radius)]
    rigs.extend((str(w), o, float(r)) for w, o, r in also)
    for name, spot, _reach in rigs:
        if name not in BOX_WEAPONS:
            known = ", ".join(BOX_WEAPONS)
            if name in LEVEL_WEAPONS:
                raise KeyError(
                    f"{name!r} is in the level weapon table but its in_box flag is "
                    "FALSE, so the chest's eligibility loop rejects it and the box "
                    f"cannot be rigged to it; box weapons: {known}"
                )
            raise KeyError(
                f"{name!r} is not in this level's weapon set, so the hook would "
                f"return the candidate array untouched and the box would behave "
                f"normally; box weapons: {known}"
            )
    if len(rigs) > 1 and any(spot is None for _n, spot, _r in rigs):
        raise ValueError(
            "a map with more than one rigged box has to say where each one is: "
            "the hook cannot tell the chests apart and discriminates by "
            "distance, so a rig with no origin would answer for all of them"
        )

    body = ["// self is the player who used a box"]
    for index, (name, spot, reach) in enumerate(rigs):
        forced = f'zmf_box_prefer( a_keys, getweapon( "{name}" ) )'
        if spot is None:
            body.append(f"return {forced};")
            break
        body += [
            f"if ( distancesquared( self.origin, {_vector(spot)} ) <= "
            f"{float(reach) ** 2:g} )",
            "{",
            f"\treturn {forced};",
            "}",
        ]
    else:
        body.append("return a_keys;")

    return CustomScript(
        functions=(
            CustomFunction(
                "zmf_box_weights",
                tuple(body),
                params=("a_keys",),
                purpose=(
                    "Which box the player is standing at decides what it gives.\n"
                    "_zm_magicbox.gsc:1266-1268 replaces the candidate array\n"
                    "after the shuffle and before the eligibility loop;\n"
                    "distancesquared: _zm_magicbox.gsc:241."
                ),
            ),
            CustomFunction(
                "zmf_box_prefer",
                (
                    "a_out = [];",
                    "for ( i = 0; i < a_keys.size; i++ )",
                    "{",
                    "\tif ( a_keys[ i ] == w_forced )",
                    "\t{",
                    "\t\ta_out[ a_out.size ] = a_keys[ i ];",
                    "\t}",
                    "}",
                    "if ( a_out.size == 0 )",
                    "{",
                    "\treturn a_keys;",
                    "}",
                    "for ( i = 0; i < a_keys.size; i++ )",
                    "{",
                    "\tif ( a_keys[ i ] != w_forced )",
                    "\t{",
                    "\t\ta_out[ a_out.size ] = a_keys[ i ];",
                    "\t}",
                    "}",
                    "return a_out;",
                ),
                params=("a_keys", "w_forced"),
                purpose=(
                    "The forced weapon first, the rest of the array behind it.\n"
                    "An empty result means the weapon is not in this level's\n"
                    "set at all, and the box is left alone rather than broken."
                ),
            ),
        ),
        statements=(
            (Slot.AFTER_ENTRY, "level.customrandomweaponweights = &zmf_box_weights;"),
        ),
        notes=tuple(
            f"mystery box rigged to {n}" + ("" if o is None else f" at {_vector(o)}")
            for n, o, _r in rigs
        ),
    )


# --------------------------------------------------------------------------
# Spawn spike on a door
# --------------------------------------------------------------------------
def spawn_spike_on_flag(
    flag: str,
    *,
    spike_delay: float = 0.25,
    seconds: float = 20.0,
    normal_delay: float = 2.0,
) -> CustomScript:
    """Zombies come faster for a while once a particular door is bought.

    A door's flag is the one the generated zone hook already passes to
    ``zm_zonemgr::add_adjacent_zone``, and flags are waitable:
    ``flag_shared.gsc:190 function wait_till( str_flag )``, used by stock
    maps as ``zm_castle.gsc:880`` ``level flag::wait_till( "power_on" );``.

    The rate itself is a zombie var.  ``_zm.gsc:1247``
    ``zombie_utility::set_zombie_var( "zombie_spawn_delay", 2, 1, column );``
    is the stock default, consumed at ``_zm.gsc:3860``
    ``wait level.zombie_vars[ "zombie_spawn_delay" ];``.  The setter is
    ``_zm_utility.gsc:3382 function set_zombie_var( zvar, value, is_float,
    column, is_team_based )``, which defaults ``column`` to 1 when it is not
    passed (``:3389-3391``), so three arguments is a complete call.

    Afterwards the var goes back to **what the round should have now**,
    through the stock getter (:func:`restore_spawn_delay_lines`): not a
    literal 2 (the round-1 figure), and not a value saved before the spike,
    which is stale once a round ends mid-spike.
    ``normal_delay`` is kept for callers and no longer used.

    **Unverified:** how hard the spike feels, and whether the round's
    zombie budget makes it visible at all.
    """
    return CustomScript(
        functions=(
            CustomFunction(
                "zmf_spawn_spike",
                (
                    'level endon( "end_game" );',
                    f'level flag::wait_till( "{flag}" );',
                    f'zm_utility::set_zombie_var( "zombie_spawn_delay", '
                    f"{float(spike_delay):g}, 1 );",
                    f"wait {float(seconds):g};",
                    *restore_spawn_delay_lines(),
                ),
                purpose=(
                    f"Buying the {flag} door speeds the spawns up for "
                    f"{float(seconds):g}s.\n"
                    "flag::wait_till: flag_shared.gsc:190. zombie_spawn_delay\n"
                    "default 2: _zm.gsc:1247, consumed at _zm.gsc:3860."
                ),
            ),
        ),
        # ZONE_HOOK for the same reason :func:`closet_ambush` uses it: this
        # waits on a door flag, and a door flag does not exist until the zone
        # hook has run.
        statements=((Slot.ZONE_HOOK, "level thread zmf_spawn_spike();"),),
        notes=(f"spawn spike when the {flag} door is bought",),
    )


# --------------------------------------------------------------------------
# The cupboard full of zombies
# --------------------------------------------------------------------------
def closet_ambush(
    flag: str,
    origin,
    *,
    count: int = 10,
    spread: float = 24.0,
    facing_yaw: float = 0.0,
    sprint: bool = True,
) -> CustomScript:
    """Buying one door releases a cupboard packed with sprinting zombies.

    The three parts, each read out of the stock scripts:

    **Spawning a fixed number on a trigger.**
    ``shared/ai/zombie_utility.gsc:1851 function spawn_zombie( spawner,
    target_name, spawn_point, round_number )`` is the stock way for a map
    script to make an ordinary zombie outside the round system, and stock
    maps call it exactly as this does -- ``zm_castle_tram.gsc:496``,
    ``zm_island_power.gsc:620``, ``zm_genesis_power.gsc:1278``, all
    ``spawn_zombie( level.zombie_spawners[ 0 ], "<name>", <loc> )``.  The
    spawner array is the framework's own, ``_zm_spawner.gsc:39``
    ``level.zombie_spawners = getentarray( "zombie_spawner",
    "script_noteworthy" );``.

    ``spawn_zombie`` returns ``undefined`` unless the spawner has
    ``script_forcespawn`` set (``:1865``), so this sets it first, which is
    what every stock script that spawns its own AI does:
    ``_zm_ai_dogs.gsc:135 level.dog_spawners[ i ].script_forcespawn = 1;``,
    ``_zm_ai_raps.gsc:105``, ``zm_tomb_mech.gsc:45``.

    **Putting them in the cupboard.**  ``spawn_zombie``'s ``spawn_point``
    argument, a walk-in struct built at run time (:func:`spawn_point_lines`),
    through ``level.move_spawn_func`` (``zombie_utility.gsc:1918``,
    ``zm_utility::move_zombie_spawn_location``).  Teleporting
    them after the spawn does not work: the stock spawn code undoes it by
    moving each to a random riser of the open zones (see
    :func:`spawn_point_lines`).  Nothing has to be placed in the closet.

    **Forcing sprint at any round.**  ``set_zombie_run_cycle( "sprint" )``
    assigns ``self.zombie_move_speed`` (``zombie_utility.gsc:2500``,
    ``:2511``), and the stock last-zombie-sprints code is precisely
    ``:2393-2394`` ``ai_zombie set_zombie_run_cycle( "sprint" );
    ai_zombie.zombie_move_speed_original = ai_zombie.zombie_move_speed;``,
    which is copied here including the ``_original`` assignment.

    **Do they count toward the round?**  They are extra, not instead.  The
    round's budget ``level.zombie_total`` is only decremented by the round
    spawner (``_zm.gsc:3839``), so these ten do not use it up; but the round
    cannot end while any zombie lives (``_zm.gsc:4766`` ``should_wait =
    zombie_utility::get_current_zombie_count() > 0 || level.zombie_total > 0
    ...``), so they must be killed like anything else.  They also count
    against the live-AI cap the round spawner waits on (``_zm.gsc:3772``),
    and ``spawn_zombie`` itself waits for a free actor slot (``:1859``), so
    at a high round the ten arrive as slots free rather than all at once.
    The round loop is not modified in any way.

    **Unverified:** that the closet point is somewhere a zombie can path
    from; that one frame at the spawner's origin before the teleport is
    invisible; that sprint set immediately after spawn is not overwritten by
    the framework's own per-round speed roll; and whether ten bodies in a
    cupboard-sized volume push each other through a wall.  Nothing here has
    been played.
    """
    if count < 1:
        raise ValueError("an ambush with no zombies is just a cupboard")

    spots = _ring(origin, count, spread)
    body: list[str] = [
        'level endon( "end_game" );',
        f'level flag::wait_till( "{flag}" );',
        "if ( !isdefined( level.zombie_spawners ) || level.zombie_spawners.size < 1 )",
        "{",
        "\treturn;",
        "}",
        "e_spawner = level.zombie_spawners[ 0 ];",
        "e_spawner.script_forcespawn = 1;",
        "a_spots = [];",
    ]
    for index, spot in enumerate(spots):
        body.append(f"a_spots[ {index} ] = {_vector(spot)};")
    body += [
        f"for ( i = 0; i < {int(count)}; i++ )",
        "{",
        *("\t" + line for line in spawn_point_lines("s_spot", "a_spots[ i ]", facing_yaw)),
        '\tai = zombie_utility::spawn_zombie( e_spawner, "zmf_closet_zombie", s_spot );',
        "\tif ( !isdefined( ai ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
    ]
    if sprint:
        body.append("\tai thread zmf_closet_sprint();")
    body.append("}")

    functions = [
        CustomFunction(
            "zmf_closet_ambush",
            tuple(body),
            purpose=(
                f"{int(count)} zombies waiting behind the {flag} door.\n"
                "spawn_zombie: shared/ai/zombie_utility.gsc:1851, as stock maps\n"
                "call it (zm_island_power.gsc:620). script_forcespawn first:\n"
                ":1865, set as _zm_ai_dogs.gsc:135 does. Placed by its spawn_point\n"
                "(move_zombie_spawn_location, _zm_utility.gsc:188)."
            ),
        )
    ]
    if sprint:
        functions.append(
            CustomFunction(
                "zmf_closet_sprint",
                (
                    'self endon( "death" );',
                    'level endon( "end_game" );',
                    "wait 0.05;",
                    'self zombie_utility::set_zombie_run_cycle( "sprint" );',
                    "self.zombie_move_speed_original = self.zombie_move_speed;",
                ),
                purpose=(
                    "Sprint whatever the round is.\n"
                    "The stock last-zombie sprint, zombie_utility.gsc:2393-2394.\n"
                    "One frame late so the framework's own speed roll lands first."
                ),
            )
        )

    return CustomScript(
        using=(_ZOMBIE_UTILITY,),
        functions=tuple(functions),
        # ZONE_HOOK, not AFTER_ENTRY.  The flag this waits on is created by
        # the ``add_adjacent_zone`` call in the generated zone hook
        # (``_zm_zonemgr.gsc:595-612`` calls ``flag::init`` for a flag nothing
        # has defined), and the zone hook runs *after* ``main`` returns.  A
        # thread started in ``main`` therefore reaches
        # ``flag::wait_till( "<door>" )`` before the flag exists, and
        # ``wait_till`` calls ``get``, which is
        # ``Assert( exists( str_flag ), ... ); return self.flag[ str_flag ];``
        # (``flag_shared.gsc:203-208``) -- an assert that is *not* inside a
        # ``/# #/`` developer block, unlike the one in ``init`` at :23-28.
        # Whether that assert is live in a retail build is not something a
        # tools-only install can answer, so the map does not rely on the answer: emitted from
        # the zone hook, which the emitter writes after every
        # ``add_adjacent_zone`` line, the flag is always already there.
        statements=((Slot.ZONE_HOOK, "level thread zmf_closet_ambush();"),),
        notes=(
            f"{int(count)} "
            + ("sprinting " if sprint else "")
            + f"zombies released when the {flag} door is bought",
        ),
    )


def spawn_point_lines(var: str, at: str, yaw: float = 0.0) -> list[str]:
    """A walk-in spawn point for ``zombie_utility::spawn_zombie``'s third
    argument: every generated AI spawn passes one instead of teleporting
    after the spawn.

    WHY [read from the stock scripts]: a ``forceteleport`` right after ``spawn_zombie`` is
    undone.  The stock spawn functions run after ``waittillframeend``
    (``spawner_shared.gsc:563-590``), so ``zombie_spawn_init`` ->
    ``zombie_think`` -> ``do_zombie_spawn`` (``_zm_spawner.gsc:2867``) then
    picks a random ``zombie_location`` of the open zones and
    ``move_zombie_spawn_location`` moves the zombie there and makes it rise
    (``_zm_utility.gsc:188-300``).  With a spawn point the stock code moves
    it to *this* spot once and marks it ``spawn_pos``; the later
    ``do_zombie_spawn`` only says ``risen`` (``:191-195``).
    ``"spawn_location"`` walks in (no rise animation) and ``"find_flesh"``
    sends it straight at the players (``should_skip_teardown``,
    ``_zm_spawner.gsc:446``): the path the stock ``round_spawning_test``
    uses (``_zm.gsc:3965``)."""
    return [
        f"{var} = SpawnStruct();",
        f"{var}.origin = {at};",
        f"{var}.angles = ( 0, {float(yaw):g}, 0 );",
        f'{var}.script_noteworthy = "spawn_location";',
        f'{var}.script_string = "find_flesh";',
    ]


def _ring(centre, count: int, spread: float) -> list[tuple[float, float, float]]:
    """``count`` points around ``centre``, so the bodies are not co-located.

    A cupboard cannot hold ten zombies at arm's length, so this is a small
    ring inside ``spread`` and the AI push each other apart from there.
    """
    x, y, z = (getattr(centre, axis, None) for axis in ("x", "y", "z"))
    if x is None:
        x, y, z = centre
    points = []
    for index in range(count):
        angle = 2.0 * math.pi * index / max(count, 1)
        radius = spread * (0.35 if index % 2 else 1.0)
        points.append(
            (
                float(x) + radius * math.cos(angle),
                float(y) + radius * math.sin(angle),
                float(z),
            )
        )
    return points


# --------------------------------------------------------------------------
# The anticlimactic teleporter
# --------------------------------------------------------------------------
def short_hop_teleporter(
    pad_origin,
    arrival_origin,
    *,
    radius: float = 40.0,
    height: float = 72.0,
    arrival_yaw: float = 0.0,
    charge_seconds: float = 1.5,
    cooldown_seconds: float = 4.0,
    suffix: str = "",
) -> CustomScript:
    """A teleporter with the full ceremony that moves you about five feet.

    **What the stock teleporters actually are:** not a reusable mechanism.
    ``zm_factory_teleporter.gsc`` needs a linked pad set and a mainframe:
    ``:51`` ``level flag::init( "teleporter_pad_link_1" );``, ``:65``
    ``trig = getent( "trigger_teleport_pad_" + i, "targetname" );``, ``:639``
    ``trigger = getent( "trigger_teleport_core", "targetname" );``, ``:643``
    ``level flag::wait_till( "power_on" );``, plus wire structs at ``:902``.
    All of that is radiant-placed entity work before a line of it runs, and
    none of it reduces to a five-foot hop.

    **What the move itself is:** raw engine calls, which is what every stock
    map does inline.  ``zm_tomb_teleporter.gsc:526-527``
    ``player setorigin( s_pos.origin ); player setplayerangles( s_pos.angles );``
    and the same pair at ``zm_castle_ee.gsc:2561-2562``.  There is no shared
    teleport helper in ``_zm_utility.gsc`` or ``util_shared.gsc``.

    **The ceremony** is stock too, borrowed from the same file:
    ``zm_tomb_teleporter.gsc:494`` ``player playsoundtoplayer(
    "zmb_teleporter_plr_start", player );``, ``:456`` ``player thread
    hud::fade_to_black_for_x_sec( 0, 0.3, 0, 0.5, "white" );``, and
    ``zm_factory_teleporter.gsc:695`` ``earthquake( 0.3, 2, trigger.origin,
    3700 );``.  The visionset overlay is deliberately not used: it needs a
    prior ``visionset_mgr::register_info``, so it is not free to call.

    **The pad** is a script-spawned trigger, not a map entity, so this needs
    nothing from the layout: ``doors_shared.gsc:1190`` ``e_trigger = spawn(
    "trigger_radius", e_model.origin, 0, 25, 100 );`` and the wait is the
    stock ``self waittill( #"trigger", e_who );`` (``_zm_ai_spiders.gsc:1673``).
    A radius trigger fires on touch, so the player walks onto the pad rather
    than pressing a use key: there is no prompt, because a prompt would need
    a localized string the mod tools install cannot supply (see the spec's note on
    purchase text).

    **Two of them in one map.**  ``CustomScript`` refuses two functions with
    the same name, which is right: a second copy of ``zmf_teleporter_pad``
    would silently replace the first in the emitted ``.gsc``.  ``suffix``
    names the pair apart -- functions, thread statement and the per-player
    busy flag -- so a map can carry a joke hop and a real shortcut without
    either knowing about the other.  It must be a bare identifier tail: it is
    pasted straight into a GSC function name.

    **After the move** the player is notified ``zmf_hopped<suffix>``, so a gag
    (:func:`zmforge.script.gags.player_reactions`, ``hops``) can say on screen
    what just happened without this function knowing any words.

    **Unverified:** everything about how it feels -- the fade timing against
    the move, whether the arrival point is inside the world, and whether the
    player can see the pad they left.
    """
    tail = str(suffix)
    if tail and not tail.replace("_", "").isalnum():
        raise ValueError(
            f"teleporter suffix {suffix!r} is pasted into a GSC function name, "
            "so it must be letters, digits and underscores"
        )
    pad_fn = f"zmf_teleporter_pad{tail}"
    move_fn = f"zmf_teleport_player{tail}"
    busy = f"zmf_teleporting{tail}"
    return CustomScript(
        using=(_HUD, _LASTSTAND),
        functions=(
            CustomFunction(
                pad_fn,
                (
                    'level endon( "end_game" );',
                    f't_pad = spawn( "trigger_radius", {_vector(pad_origin)}, 0, '
                    f"{float(radius):g}, {float(height):g} );",
                    "while ( true )",
                    "{",
                    '\tt_pad waittill( "trigger", e_who );',
                    f"\tif ( !isdefined( e_who ) || isdefined( e_who.{busy} ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\te_who thread {move_fn}();",
                    "}",
                ),
                purpose=(
                    "The pad: a script-spawned radius trigger, no map entity.\n"
                    'spawn( "trigger_radius", ... ): doors_shared.gsc:1190.'
                ),
            ),
            CustomFunction(
                move_fn,
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    f"self.{busy} = 1;",
                    'self playsoundtoplayer( "zmb_teleporter_plr_start", self );',
                    "self thread hud::fade_to_black_for_x_sec( 0, 0.3, 0, 0.5, "
                    '"white" );',
                    "earthquake( 0.3, 2, self.origin, 512 );",
                    f"wait {float(charge_seconds):g};",
                    *skip_if_down_lines(busy),
                    f"self setorigin( {_vector(arrival_origin)} );",
                    f"self setplayerangles( ( 0, {float(arrival_yaw):g}, 0 ) );",
                    # For zmforge.script.gags: whoever wants to say what just
                    # happened waits on the player for this.
                    f'self notify( "zmf_hopped{tail}" );',
                    f"wait {float(cooldown_seconds):g};",
                    f"self.{busy} = undefined;",
                ),
                purpose=(
                    "Sound, fade, shake, then a very short move.\n"
                    "setorigin / setplayerangles: zm_tomb_teleporter.gsc:526-527.\n"
                    "sound :494, fade :456, earthquake: "
                    "zm_factory_teleporter.gsc:695."
                ),
            ),
        ),
        statements=((Slot.AFTER_ENTRY, f"level thread {pad_fn}();"),),
        notes=(f"teleporter {pad_fn}: pad {_vector(pad_origin)} -> "
               f"arrival {_vector(arrival_origin)}",),
    )


# --------------------------------------------------------------------------
# Trick guns: five more weapons that do something other than shoot
# --------------------------------------------------------------------------
# Every one of these hangs off the same hook the mega blast uses -- the
# player's own ``weapon_fired`` notify, which carries the weapon
# (``_zm_weapons.gsc:423``) -- and every one of them is bound to a weapon
# name checked against this level's table before anything is emitted.  That
# check is not ceremony: ``shotgun_olympia`` cost a build and a play session
# because it is a Black Ops II weapon, and a hook keyed to a weapon the level
# does not have is a hook that never fires and reports nothing.
#
# The shape of a good one is a **trade**: a real benefit for a real cost, with
# the cost found out the hard way.  A gun that only punishes is a tax; a gun
# that only rewards is a balance bug.  What each of these actually feels like
# in play is unverified -- nobody has fired any of them.


# --------------------------------------------------------------------------
# Shared guards: every trick that watches a
# weapon, moves a player or bends the spawn rate goes through these, and
# zmforge.verify.gameplay checks the generated script for the same shapes.
# --------------------------------------------------------------------------
#: Weapons thrown or placed, not fired: the engine notifies these on the
#: player as ``grenade_fire`` ( grenade, weapon ), which is what every stock
#: grenade watcher waits on (``_zm_weapons.gsc:101``, ``gametypes/
#: _weapons.gsc:891``, ``_zm_weap_octobomb.gsc:1034``); no stock script
#: waits on ``weapon_fired`` for one.  Check Z69.
GRENADE_WEAPON = re.compile(
    r"grenade|cymbal_monkey|octobomb|claymore|bouncingbetty|bouncing_betty|"
    r"tripmine|trip_mine|widows_wine|emp_grenade|hatchet|tomahawk")


def fire_wait_line(weapon: str) -> str:
    """The ``waittill`` a per-player watcher for ``weapon`` uses, leaving the
    weapon in ``w_fired``: ``grenade_fire`` for a thrown weapon, else
    ``weapon_fired`` (``_zm_weapons.gsc:423``)."""
    if GRENADE_WEAPON.search(weapon):
        return 'self waittill( "grenade_fire", e_grenade, w_fired );'
    return 'self waittill( "weapon_fired", w_fired );'


def restore_spawn_delay_lines() -> list[str]:
    """Put ``zombie_spawn_delay`` back to what the round *should* have now.

    Through the stock getter, not a value saved before a spike: the round
    loop rewrites the var at every round start from
    ``[[ level.func_get_zombie_spawn_delay ]]( get_round_number() )``
    (``_zm.gsc:4502``, set at ``:307``), so a saved value is stale the
    moment a round ends mid-spike and restoring it would undo that round's
    speed-up.  Check Z70."""
    return [
        "if ( isdefined( level.func_get_zombie_spawn_delay ) )",
        "{",
        '\tzm_utility::set_zombie_var( "zombie_spawn_delay", '
        "[[ level.func_get_zombie_spawn_delay ]]( level.round_number ), 1 );",
        "}",
    ]


def skip_if_down_lines(busy: str | None = None) -> list[str]:
    """Return early when ``self`` is in last stand, clearing ``busy`` first.

    Every script that moves a player (a teleporter, a relocation) puts this
    right before its ``setorigin``: moving a downed player carries them out
    of their teammates' reach and out of the zombies', which makes a
    Relocate a free last-stand escape.  Check Z71."""
    clear = [f"\tself.{busy} = undefined;"] if busy else []
    return [
        "if ( self laststand::player_is_in_laststand() )",
        "{",
        *clear,
        "\treturn;",
        "}",
    ]


def _must_be_a_level_weapon(weapon: str, what: str) -> str:
    """The weapon name, or a refusal naming what the level does have.

    Two builds have now been lost to a weapon the game does not carry, so
    this is a hard failure at model time rather than a silent no-op at run
    time: a ``weapon_fired`` handler keyed to an absent weapon never runs and
    prints nothing to say so.
    """
    if weapon not in LEVEL_WEAPONS:
        raise KeyError(
            f"{weapon!r} is not in this level's weapon table, so {what} would "
            "never fire and would report nothing; the table is "
            "zmforge.blueprint.catalogue.LEVEL_WEAPONS"
        )
    return weapon


def _fired_watchers(prefix: str, weapon: str, handler: str) -> tuple[CustomFunction, ...]:
    """The pair that puts a ``weapon_fired`` watcher on every player.

    Two functions, not one, for the reason :func:`mega_blast_on_fire` needs
    two: there is no slot in the generated ``main`` that runs per player (the
    four safe positions are in :class:`~zmforge.script.custom.Slot`), so a
    level thread attaches a watcher to everyone present and then to everyone
    who joins.  ``level waittill( "connected", player )`` is ``_zm.gsc:482``
    and ``getplayers()`` is ``_zm_perks.gsc:203``.

    The watcher itself is an equality test against ``getweapon``, because
    ``weapon_fired`` is notified on the player and carries the weapon fired
    (``_zm_weapons.gsc:423``).
    """
    attach = f"{prefix}_attach"
    watch = f"{prefix}_watch"
    return (
        CustomFunction(
            attach,
            (
                'level endon( "end_game" );',
                "players = getplayers();",
                "for ( i = 0; i < players.size; i++ )",
                "{",
                f"\tplayers[ i ] thread {watch}();",
                "}",
                "while ( true )",
                "{",
                '\tlevel waittill( "connected", player );',
                f"\tplayer thread {watch}();",
                "}",
            ),
            purpose=(
                "One watcher per player, now and on join.\n"
                'level waittill( #"connected", player ): _zm.gsc:482.\n'
                "getplayers(): _zm_perks.gsc:203."
            ),
        ),
        CustomFunction(
            watch,
            (
                'self endon( "disconnect" );',
                'level endon( "end_game" );',
                f'w_trap = getweapon( "{weapon}" );',
                "while ( true )",
                "{",
                "\t" + fire_wait_line(weapon),
                "\tif ( !isdefined( w_fired ) || w_fired != w_trap )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                f"\tself thread {handler}();",
                "}",
            ),
            purpose=(
                f"Watch for a shot from {weapon}.\n"
                + ("grenade_fire carries the weapon: _zm_weapons.gsc:101."
                   if GRENADE_WEAPON.search(weapon) else
                   "weapon_fired carries the weapon: _zm_weapons.gsc:423.")
            ),
        ),
    )


def overtime_on_fire(
    weapon: str = "frag_grenade",
    *,
    payout: int = 250,
    spike_delay: float = 0.4,
    seconds: float = 15.0,
    normal_delay: float = 2.0,
    lockout: float = 20.0,
) -> CustomScript:
    """Overtime: throwing this pays you, and the round gets worse for a while.

    The trade is money for pressure, and it is the cheapest gun on the map, so
    it is the one a player reaches for first and the one whose cost they work
    out last.  Nothing announces the spike; the round simply starts arriving
    faster and keeps doing it for fifteen seconds.

    **The payment** is ``zm_score::add_to_player_score``
    (``_zm_score.gsc:521``), which is what every stock points award goes
    through.  **The pressure** is ``zombie_spawn_delay``, the same zombie var
    :func:`spawn_spike_on_flag` moves: stock sets it to 2
    (``_zm.gsc:1247``) and the round loop waits on it every spawn
    (``_zm.gsc:3860``).

    ``lockout`` stops it being a money printer: the handler sets a flag on the
    player, and the flag outlasts the spike, so holding the trigger down buys
    nothing and a second thrower cannot stack a second spike on the first.

    The delay is restored through the stock getter, not to a literal or a
    saved value: see :func:`spawn_spike_on_flag`.

    **Unverified:** whether the spike is visible at all inside a round's own
    zombie budget, and whether 250 points a throw reads as generous or as
    obviously suspicious.
    """
    _must_be_a_level_weapon(weapon, "the overtime payout")
    return CustomScript(
        using=(_SCORE,),
        functions=(
            *_fired_watchers("zmf_overtime", weapon, "zmf_overtime_claim"),
            CustomFunction(
                "zmf_overtime_claim",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    "if ( isdefined( self.zmf_overtime_busy ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "self.zmf_overtime_busy = 1;",
                    f"self zm_score::add_to_player_score( {int(payout)} );",
                    f'zm_utility::set_zombie_var( "zombie_spawn_delay", '
                    f"{float(spike_delay):g}, 1 );",
                    f"wait {float(seconds):g};",
                    *restore_spawn_delay_lines(),
                    f"wait {float(lockout) - float(seconds):g};",
                    "self.zmf_overtime_busy = undefined;",
                ),
                purpose=(
                    f"Pay {payout}, then run the spawns at {spike_delay:g}s for "
                    f"{seconds:g}s.\n"
                    "add_to_player_score: _zm_score.gsc:521. zombie_spawn_delay\n"
                    "default 2: _zm.gsc:1247, consumed at _zm.gsc:3860."
                ),
            ),
        ),
        statements=(
            (Slot.AFTER_ENTRY, "level thread zmf_overtime_attach();"),
        ),
        notes=(f"{weapon} pays {payout} and speeds the spawns up for {seconds:g}s",),
    )


def relocation_on_fire(
    weapon: str = "pistol_fullauto",
    arrival=None,
    *,
    arrival_yaw: float = 0.0,
    charge_seconds: float = 0.4,
    lockout: float = 30.0,
) -> CustomScript:
    """A relocation notice: firing this puts you back where you started.

    The best escape tool in the map and the worst thing that can happen to a
    good run, which is the same sentence.  It is free, it is repeatable, and
    it costs every door you have walked through since the spawn.  Nobody reads
    a gun's small print; they find this one out by panic-firing it in a corner
    on round twenty.

    The move is the pair every stock teleport uses,
    ``zm_tomb_teleporter.gsc:526-527`` ``player setorigin( ... ); player
    setplayerangles( ... );``, and the ceremony around it is
    :func:`short_hop_teleporter`'s, kept short because a gun that takes two
    seconds to save you does not save you.

    **Unverified:** whether the arrival point is clear when a player lands on
    it, and whether a second player standing there is pushed out or overlapped.
    """
    _must_be_a_level_weapon(weapon, "the relocation notice")
    if arrival is None:
        raise ValueError("a relocation gun needs somewhere to relocate you to")
    return CustomScript(
        using=(_HUD, _LASTSTAND),
        functions=(
            *_fired_watchers("zmf_relocate", weapon, "zmf_relocate_player"),
            CustomFunction(
                "zmf_relocate_player",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    "if ( isdefined( self.zmf_relocating ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "self.zmf_relocating = 1;",
                    'self playsoundtoplayer( "zmb_teleporter_plr_start", self );',
                    "self thread hud::fade_to_black_for_x_sec( 0, 0.2, 0, 0.4, "
                    '"white" );',
                    f"wait {float(charge_seconds):g};",
                    *skip_if_down_lines("zmf_relocating"),
                    f"self setorigin( {_vector(arrival)} );",
                    f"self setplayerangles( ( 0, {float(arrival_yaw):g}, 0 ) );",
                    f"wait {float(lockout):g};",
                    "self.zmf_relocating = undefined;",
                ),
                purpose=(
                    "Fade, then put the shooter back at the spawn.\n"
                    "setorigin / setplayerangles: zm_tomb_teleporter.gsc:526-527.\n"
                    "sound :494, fade :456."
                ),
            ),
        ),
        statements=(
            (Slot.AFTER_ENTRY, "level thread zmf_relocate_attach();"),
        ),
        notes=(f"{weapon} teleports the shooter to {_vector(arrival)}",),
    )


def consultancy_fee_on_fire(
    weapon: str = "smg_fastfire",
    *,
    fee: int = 100,
    range_units: float = 256.0,
    cone_degrees: float = 90.0,
) -> CustomScript:
    """A consultancy fee: this gun clears the room and bills you for it.

    Straightforwardly strong -- everything inside a ninety-degree cone at
    close range dies on the trigger pull, which is a horde answered -- and it
    takes a hundred points every time it is fired, hit or miss.  The cost is
    not hidden and it is not survivable arithmetic either: a player who fights
    with this all round arrives at Pack-a-Punch unable to pay for it.  The
    honest version of that sentence is the point of the gun.

    The kill is the nuke's, as :func:`mega_blast_on_fire`'s is:
    ``getaiteamarray( level.zombie_team )`` (``_zm_powerup_nuke.gsc:47``),
    ``zombie_head_gib()`` (``:120``) and ``dodamage( health + 666, origin )``
    (``:127``), skipping anything with a magic-bullet shield (``:89``).  The
    cone is ``anglestoforward``/``vectordot`` (``_zm_weap_claymore.gsc:134-135``)
    flattened to the ground plane.  The bill is
    ``zm_score::minus_to_player_score`` (``_zm_score.gsc:556``).

    **Unverified:** what the game does when the fee is larger than the score.
    Stock code calls this function freely and nothing here has read what it
    does at zero, so a player at 0 points may simply keep a free gun.
    """
    _must_be_a_level_weapon(weapon, "the consultancy fee")
    if range_units <= 0:
        raise ValueError("a fee with no range would charge for nothing")
    half_cos = math.cos(math.radians(min(float(cone_degrees), 360.0) / 2.0))
    return CustomScript(
        using=(_SCORE, _ZOMBIE_UTILITY),
        functions=(
            *_fired_watchers("zmf_fee", weapon, "zmf_fee_charge"),
            CustomFunction(
                "zmf_fee_charge",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    f"self zm_score::minus_to_player_score( {int(fee)} );",
                    "v_angles = self getplayerangles();",
                    "v_forward = anglestoforward( ( 0, v_angles[ 1 ], 0 ) );",
                    "a_zombies = getaiteamarray( level.zombie_team );",
                    "for ( i = 0; i < a_zombies.size; i++ )",
                    "{",
                    "\tai = a_zombies[ i ];",
                    "\tif ( !isdefined( ai ) || !isalive( ai ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tif ( ai zm_utility::is_magic_bullet_shield_enabled() )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tv_to = ai.origin - self.origin;",
                    "\tv_flat = vectornormalize( ( v_to[ 0 ], v_to[ 1 ], 0 ) );",
                    f"\tif ( distancesquared( ai.origin, self.origin ) > "
                    f"{float(range_units) ** 2:g} )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\tif ( vectordot( v_flat, v_forward ) < {half_cos:g} )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tai zombie_utility::zombie_head_gib();",
                    "\tai dodamage( ai.health + 666, ai.origin );",
                    "}",
                ),
                purpose=(
                    f"Charge {fee}, then kill the cone in front at "
                    f"{range_units:g} units.\n"
                    "minus_to_player_score: _zm_score.gsc:556.\n"
                    "getaiteamarray :47, head gib :120, dodamage :127 of\n"
                    "_zm_powerup_nuke.gsc; cone: _zm_weap_claymore.gsc:134-135."
                ),
            ),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_fee_attach();"),),
        notes=(f"{weapon} charges {fee} a shot and kills the cone in front",),
    )


def job_creation_on_fire(
    weapon: str = "smg_versatile",
    origin=None,
    *,
    payout: int = 150,
    one_in: int = 4,
    spread: float = 48.0,
    sprint: bool = True,
    cooldown: float = 3.0,
) -> CustomScript:
    """Job creation: this gun pays well and makes its own work.

    One shot in four pays a hundred and fifty points and puts one more zombie
    behind you.  Fire it a little and it is a wall buy that funds itself; fire
    it all round and you have built a second round inside the first.  The
    trade is visible in principle and invisible in practice, because nobody
    counts the zombies they did not ask for.

    The roll is ``randomint`` (``_zm_magicbox.gsc:1457``).  The zombie is
    ``zombie_utility::spawn_zombie``, the same call
    :func:`closet_ambush` uses to put bodies in a map outside the round
    system, and ``set_zombie_run_cycle( "sprint" )``
    (``shared/ai/zombie_utility.gsc:2500``) is what makes it a sprinter.  The
    payment is ``zm_score::add_to_player_score`` (``_zm_score.gsc:521``).

    **Paid only for a hire, at most once per ``cooldown`` seconds**.  Paying
    before the spawn, on every lucky shot, would let an SMG with no spawner
    free or a full actor pool print 150 points a quarter of the time, without
    end.  The roll happens only
    once the per-player cooldown has run out, and the points come after
    ``spawn_zombie`` has handed back a zombie.  Check Z68 holds every fire
    handler to the same shape.

    **Unverified:** whether a zombie spawned outside the round counts against
    the round's own budget, so whether this lengthens a round or only
    thickens it.
    """
    _must_be_a_level_weapon(weapon, "the job creation payout")
    if cooldown <= 0:
        raise ValueError("a paying fire handler needs a cooldown (check Z68)")
    if origin is None:
        raise ValueError("a job-creation gun needs somewhere to put the new hire")
    if one_in < 1:
        raise ValueError("one_in must be at least 1")
    body = [
        'self endon( "disconnect" );',
        'level endon( "end_game" );',
        "if ( isdefined( self.zmf_hire_next ) && gettime() < self.zmf_hire_next )",
        "{",
        "\treturn;",
        "}",
        f"self.zmf_hire_next = gettime() + {_ms(cooldown)};",
        f"if ( randomint( {int(one_in)} ) != 0 )",
        "{",
        "\treturn;",
        "}",
        "if ( !isdefined( level.zombie_spawners ) || level.zombie_spawners.size < 1 )",
        "{",
        "\treturn;",
        "}",
        "e_spawner = level.zombie_spawners[ 0 ];",
        "e_spawner.script_forcespawn = 1;",
        f"v_at = {_vector(origin)};",
        *spawn_point_lines("s_at", "v_at"),
        'ai = zombie_utility::spawn_zombie( e_spawner, "zmf_new_hire", s_at );',
        "if ( !isdefined( ai ) )",
        "{",
        "\treturn;",
        "}",
    ]
    if sprint:
        body.append('ai zombie_utility::set_zombie_run_cycle( "sprint" );')
    # Paid last: only a hire that happened earns anything (Z68).
    body.append(f"self zm_score::add_to_player_score( {int(payout)} );")
    return CustomScript(
        using=(_SCORE, _ZOMBIE_UTILITY),
        functions=(
            *_fired_watchers("zmf_hire", weapon, "zmf_hire_one"),
            CustomFunction(
                "zmf_hire_one",
                tuple(body),
                purpose=(
                    f"One shot in {one_in} pays {payout} and hires one more "
                    "zombie.\n"
                    "randomint: _zm_magicbox.gsc:1457. spawn_zombie:\n"
                    "shared/ai/zombie_utility.gsc:1851. sprint cycle: :2500.\n"
                    "add_to_player_score: _zm_score.gsc:521."
                ),
            ),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_hire_attach();"),),
        notes=(f"{weapon} pays {payout} and spawns a zombie one shot in {one_in}",),
    )


def panic_button_on_fire(
    weapon: str = "ar_longburst",
    *,
    radius: float = 160.0,
    deafen_asset: str = "explosion",
    deafen_seconds: float = 3.0,
    lockout: float = 10.0,
) -> CustomScript:
    """A panic button: everything touching you dies and you cannot hear or see.

    A real answer to being cornered -- a sphere, not a cone, so it clears the
    two behind you as well -- paid for with three seconds of being no use to
    anybody.  Whether that is a good trade depends entirely on whether there
    was a third zombie on the way, which is exactly the decision worth making.

    The kill is the nuke's again (``_zm_powerup_nuke.gsc:47``, ``:120``,
    ``:127``, skipping magic-bullet shields at ``:89``) and the blindness is
    ``shellshock``, which is what core zombies code does to a player standing
    near a blast: ``_zm_ai_napalm.gsc:740``, ``_zm_ai_quad.gsc:348``, and
    ``zm_castle_teleporter.gsc:890 self shellshock( "explosion", 4 );``.

    ``lockout`` is what keeps it a panic button rather than a play style.

    **Unverified:** how disabling three seconds of shellshock actually is with
    zombies still arriving, and whether the sphere reaches a zombie standing
    on a step above the shooter (it is measured in three dimensions, so it
    should).
    """
    _must_be_a_level_weapon(weapon, "the panic button")
    if radius <= 0:
        raise ValueError("a panic button with no radius would clear nothing")
    return CustomScript(
        using=(_ZOMBIE_UTILITY,),
        functions=(
            *_fired_watchers("zmf_panic", weapon, "zmf_panic_clear"),
            CustomFunction(
                "zmf_panic_clear",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    "if ( isdefined( self.zmf_panicking ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "self.zmf_panicking = 1;",
                    "a_zombies = getaiteamarray( level.zombie_team );",
                    "n_hit = 0;",
                    "for ( i = 0; i < a_zombies.size; i++ )",
                    "{",
                    "\tai = a_zombies[ i ];",
                    "\tif ( !isdefined( ai ) || !isalive( ai ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tif ( ai zm_utility::is_magic_bullet_shield_enabled() )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\tif ( distancesquared( ai.origin, self.origin ) > "
                    f"{float(radius) ** 2:g} )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tai zombie_utility::zombie_head_gib();",
                    "\tai dodamage( ai.health + 666, ai.origin );",
                    "\tn_hit = n_hit + 1;",
                    "}",
                    "if ( n_hit > 0 )",
                    "{",
                    f'\tself shellshock( "{deafen_asset}", '
                    f"{float(deafen_seconds):g} );",
                    "\tearthquake( 0.3, 1, self.origin, 384 );",
                    "}",
                    f"wait {float(lockout):g};",
                    "self.zmf_panicking = undefined;",
                ),
                purpose=(
                    f"Kill everything within {radius:g} units, then blind the "
                    "shooter.\n"
                    "getaiteamarray :47, head gib :120, dodamage :127 of\n"
                    "_zm_powerup_nuke.gsc. shellshock:\n"
                    'zm_castle_teleporter.gsc:890 self shellshock( "explosion", 4 ).'
                ),
            ),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_panic_attach();"),),
        notes=(f"{weapon} clears {radius:g} units and blinds the shooter",),
    )


# --------------------------------------------------------------------------
# A testing aid: start the game rich
# --------------------------------------------------------------------------
#: What the stock scripts give a player at the start of the game, as an
#: expression rather than a number: ``_zm.gsc:1201``
#: ``level.player_starting_points = level.round_number * 500;``, where
#: ``level.round_number`` is ``level.start_round`` from the game settings
#: (``_zm.gsc:1197-1199``).  It is 500 on a normal game and 5,000 on one
#: started at round 10, which is why :func:`starting_points` takes ``None``
#: for "leave it alone" rather than a literal 500: a literal would quietly
#: make every custom start round poorer than stock.
STOCK_STARTING_POINTS: None = None


def starting_points(points: int) -> CustomScript:
    """Every player starts the game with ``points`` instead of the stock 500.

    **This is a testing aid.**  It exists so a tester can open every door in
    a map in one session instead of earning their way round it, and a map
    that ships with it on is a map where nothing costs anything.  The recipe
    that offers it defaults to the stock value, so turning it on is a
    decision a build makes.

    TIMING IS THE WHOLE PROBLEM, so here is the ordering, read out of the
    stock tree.  There are two writes and they are at opposite ends of the
    level's life:

    * ``_zm.gsc:1201`` ``level.player_starting_points = level.round_number *
      500;`` runs inside ``init_levelvars()``, which ``zm::init()`` calls at
      ``_zm.gsc:321``.  ``zm::init()`` has no ``wait`` above that line, and
      the framework entry reaches it synchronously
      (``zm_usermap::main()`` -> ``load::main()`` -> ``zm::init()``), so by
      the time *anything* in ``main`` after ``zm_usermap::main()`` runs, the
      stock figure is already in the level var.
    * ``_zm_stats.gsc:134-135`` ``self.pers[ "score" ] =
      level.player_starting_points; self.score = self.pers[ "score" ];`` is
      the read, and it happens per player inside ``player_stats_init()``,
      which ``callback_playerconnect()`` calls at
      ``zm/gametypes/_globallogic_player.gsc:131``.

    So :attr:`~zmforge.script.custom.Slot.BEFORE_ENTRY` is the wrong slot and
    would fail **silently**: an assignment there is overwritten by
    ``init_levelvars`` a moment later and nothing reports it.
    :attr:`~zmforge.script.custom.Slot.AFTER_ENTRY` is the slot that lands
    between the stock write and the per-player read, which is the same
    argument the emitted ``level.player_too_many_players_check = false;``
    rests on.

    **And that argument is not quite enough, so this does not rely on it.**
    Whether a player has already connected by the time ``main`` resumes after
    ``zm_usermap::main()`` is not something the stock scripts settle, and no
    stock map assigns ``level.player_starting_points`` at all -- the only two
    mentions in the tree are the write at ``_zm.gsc:1201`` and the read at
    ``_zm_stats.gsc:134`` -- so there is no precedent to read it off.  The
    level var is therefore the *first* of two mechanisms, and the second is a
    reconciliation that runs demonstrably after the player exists:

    ``level flag::wait_till( "initial_blackscreen_passed" )``.  That flag is
    created at ``_zm.gsc:318`` ``init_flags()`` -- three lines above the
    ``init_levelvars()`` that sets the stock figure, so it exists before this
    logic is allowed to run, which is the ordering defect this engine has
    already been bitten by once -- and it is set at ``_zm.gsc:545``, at the
    bottom of ``fade_out_intro_screen_zm``, after the intro fade has ended
    and every player has been handed their controls.  ``flag::wait_till``
    returns immediately on a flag that is already set
    (``flag_shared.gsc:190``, ``while ( !get( str_flag ) )``), so a player
    who joins later is served the same way.

    The top-up writes ``self.score`` and ``self.pers[ "score" ]`` directly,
    which is not a liberty: it is the stock line.  ``_zm_stats.gsc:134-135``
    is exactly that pair, and ``zm_island_planting.gsc:2703-2704`` is a
    second stock site doing it to restore a saved score.  Going through
    ``zm_score::add_to_player_score`` instead would have been worse for a
    testing aid on three counts read out of ``_zm_score.gsc:521-553``: it
    rounds the amount with ``zm_utility::round_up_score( points, 10 )``, it
    passes the amount through ``bgb::add_to_player_score_override``
    (``_zm_bgb.gsc:1617``), which a bubblegum can rewrite -- and
    ``zm_usermap.gsc`` turns bubblegum on for every usermap in its
    ``autoexec opt_in`` -- and it returns without doing anything at all if
    ``level.intermission`` is set.  A tester who asks for 25,000 should get
    25,000.

    The top-up is a *floor*, not a refill: it fires once per player, guarded
    by ``self.zmf_start_points_done``, and only when the score it finds is
    below the target.  So if the level var landed, the player is already at
    the target and this writes nothing; if it did not, this is what puts the
    points there.  Either way spending them does not bring them back.

    **Unverified:** everything about how it looks.  Whether the HUD shows the
    figure without a frame of 500 first, and whether the two mechanisms ever
    disagree visibly, are questions a play session answers and the scripts do
    not.  The stat side is knowingly polluted -- the level-var route runs
    through ``_zm_stats.gsc:137`` ``incrementplayerstat( "score", ... )`` --
    which is the price of a testing aid and a reason not to ship it on.
    """
    target = int(points)
    if target < 0:
        raise ValueError(
            f"starting points of {target} is not a score the stock scripts "
            'can express; _zm_stats.gsc:134 assigns self.pers[ "score" ] a '
            "count of points, and a negative one would put the player in "
            "debt at spawn"
        )
    return CustomScript(
        functions=(
            CustomFunction(
                "zmf_start_points_attach",
                (
                    'level endon( "end_game" );',
                    # The flag exists from _zm.gsc:318, which is above the
                    # _zm.gsc:321 that sets the stock figure, so this cannot
                    # wait on a flag that has not been created yet.  It is
                    # set at _zm.gsc:545, by which point every player that
                    # started the game has spawned and been through
                    # player_stats_init.
                    'level flag::wait_till( "initial_blackscreen_passed" );',
                    "players = getplayers();",
                    "for ( i = 0; i < players.size; i++ )",
                    "{",
                    "\tplayers[ i ] thread zmf_start_points_grant();",
                    "}",
                    "while ( true )",
                    "{",
                    '\tlevel waittill( "connected", player );',
                    "\tplayer thread zmf_start_points_grant();",
                    "}",
                ),
                purpose=(
                    "Top every player up to the target once the game has\n"
                    "actually started, now and on join.\n"
                    'flag "initial_blackscreen_passed": created _zm.gsc:318\n'
                    "(init_flags), set _zm.gsc:545. wait_till returns at once\n"
                    "on a set flag: flag_shared.gsc:190.\n"
                    'level waittill( #"connected", player ): _zm.gsc:482.\n'
                    "getplayers(): _zm_perks.gsc:203."
                ),
            ),
            CustomFunction(
                "zmf_start_points_grant",
                (
                    'self endon( "disconnect" );',
                    'level endon( "end_game" );',
                    "if ( isdefined( self.zmf_start_points_done ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "self.zmf_start_points_done = 1;",
                    # player_stats_init is what defines it (_zm_stats.gsc:135)
                    # and it runs on connect, so on a player who is already in
                    # getplayers() this is already true and the loop does not
                    # run at all.
                    "while ( !isdefined( self.score ) )",
                    "{",
                    "\twait 0.05;",
                    "}",
                    f"if ( self.score < {target} )",
                    "{",
                    f"\tself.score = {target};",
                    '\tself.pers[ "score" ] = self.score;',
                    "}",
                ),
                purpose=(
                    f"Once per player, raise the score to {target} if it is\n"
                    "below it.  Never lowers, never refills.\n"
                    'self.score / self.pers[ "score" ] as a pair is the stock\n'
                    "way: _zm_stats.gsc:134-135, and again at\n"
                    "zm_island_planting.gsc:2703-2704."
                ),
            ),
        ),
        statements=(
            # AFTER_ENTRY, not BEFORE_ENTRY: init_levelvars (_zm.gsc:321,
            # reached synchronously from the framework entry) writes
            # level.player_starting_points, so an assignment before the entry
            # is overwritten and reports nothing.
            (
                Slot.AFTER_ENTRY,
                f"level.player_starting_points = {target};",
            ),
            (Slot.AFTER_ENTRY, "level thread zmf_start_points_attach();"),
        ),
        notes=(
            f"TESTING AID: every player starts with {target} points "
            "instead of the stock round_number * 500",
        ),
    )


# --------------------------------------------------------------------------
# Take a number
# --------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class TicketCalls:
    """The call half of :func:`take_a_ticket`: the PA calls a number, and the
    player holding it has ``grace`` seconds to be at the window.

    Every text field is the asset name of a ``string``
    (:meth:`~zmforge.blueprint.model.Blueprint.add_map_string`); ``&&1`` is
    the called number unless said otherwise.

    ``call``        bold to everyone at each call.
    ``you``         bold to the holder, after ``call``.
    ``hud_call``    the centre-top countdown everyone but the holder sees
                    while the call is open: ``&&1`` number, ``&&2`` seconds.
    ``hud_you``     the same line on the holder's screen.
    ``served``      bold to the holder when they make it (no parameter).
    ``served_all``  bold to everyone else, ``&&1`` the served player.
    ``missed``      bold to everyone when the holder does not make it; their
                    ticket is void.
    ``no_one``      bold to everyone when nobody holds the number.
    ``opened``      bold to everyone once, when the calls start.
    """

    window: tuple[float, float, float]
    call: str
    you: str
    hud_call: str
    hud_you: str
    served: str
    served_all: str
    missed: str
    no_one: str
    opened: str | None = None
    every: float = 60.0
    grace: float = 3.0
    start_round: int = 1
    radius: float = 96.0
    height: float = 96.0
    points: int = 1000
    powerups: tuple[str, ...] = ("double_points", "insta_kill", "full_ammo")
    held_chance: int = 75
    pulse_fx: str | None = "powerup_grabbed"
    #: A GSC condition that ends the calls for good (checked before each
    #: call): the loop stops and the kiosk's trigger is deleted, so nothing
    #: is called once the map's use for the tickets is over.
    stop_when: str | None = None
    #: Zones the window stands in that a door opens: the calls do not start
    #: until the zone manager has enabled every one (``zone_is_enabled``,
    #: ``_zm_zonemgr.gsc:65-73``), the same gate a quest step gets (P8).
    #: A missed call voids the ticket, so a call to a window behind unbought
    #: doors is a punishment nobody could avoid.
    #: Fill it with :func:`zmforge.script.quest.gate_callout`.
    zones: tuple[str, ...] = ()
    #: With more than ``busy_holders`` unserved tickets out, calls come every
    #: ``busy_every`` seconds instead of ``every`` (8 players at one call a
    #: minute takes at least 8 minutes).  ``None``: never.
    busy_every: float | None = 30.0
    busy_holders: int = 4

    def __post_init__(self) -> None:
        if self.every <= self.grace + 1.0:
            raise ValueError("calls must be further apart than the grace window")
        if self.grace <= 0:
            raise ValueError("grace > 0")
        if self.busy_every is not None and self.busy_every <= self.grace + 1.0:
            raise ValueError("busy calls must be further apart than the grace window")
        if not 0 <= self.held_chance <= 100:
            raise ValueError("held_chance is a percentage")
        if self.start_round < 1:
            raise ValueError("start_round >= 1")
        if not self.powerups or any(p not in _TICKET_POWERUPS for p in self.powerups):
            raise ValueError(f"powerups: one or more of {_TICKET_POWERUPS}")


#: The player field a served player carries, for anything that counts
#: serves (:class:`zmforge.script.quest.EveryPlayerFlag`).
TICKET_SERVED_FLAG = "zmf_served"


def take_a_ticket(
    origin,
    *,
    prompt: str,
    number: str,
    yours: str,
    yours_early: str | None = None,
    welcome: str | None = None,
    mine: str | None = None,
    mine_early: str | None = None,
    calls: TicketCalls | None = None,
    already_served: str | None = None,
    numbers: int = 10,
    radius: float = 64.0,
    height: float = 80.0,
    reset_after: float = 4.0,
    welcome_radius: float = 160.0,
    hush: float = 4.0,
) -> CustomScript:
    """Take a number, and (with ``calls``) get called to the window.

    **The kiosk.**  A use trigger at ``origin`` hands the player a ticket
    numbered 1 to ``numbers``, at random from the numbers no other player
    holds, so two players never share a call.  Taking one replaces the one
    you had.  ``prompt`` (``triggerstring``) is its idle prompt; ``number``
    (``triggerstring``, ``&&1`` the ticket, passed the way a wall buy passes
    its cost to ``SetHintString( hint, cost )``) is shown for
    ``reset_after`` seconds after a take.  ``yours`` (``string``, ``&&1`` the
    ticket) is printed bold to the taker; ``yours_early`` instead of it
    before the calls start.  ``welcome`` is printed bold, once per player,
    the first time they come within ``welcome_radius`` of the kiosk.
    ``already_served`` (``string``) is printed bold instead of a ticket to a
    player who is already served (:data:`TICKET_SERVED_FLAG`): the calls
    skip served players, so a ticket for them would never be called.
    ``mine`` / ``mine_early`` (``string``, ``&&1`` the ticket) switch on a
    quiet HUD line, top left under the objective, that shows the ticket you
    hold.

    **The calls** (:class:`TicketCalls`).  From round ``start_round`` on,
    every ``every`` seconds the PA calls a number.  With ``held_chance``
    percent odds it is the number of the longest-waiting player not yet
    served, otherwise any number 1 to ``numbers`` (the joke: nobody has it,
    "Next!").  At 100 every call is a held number, and a minute with no
    unserved holder has no call at all.  The
    holder has ``grace`` seconds to be standing (not down, not spectating)
    within ``radius`` of ``window``.  Made it: ``points`` and one of
    ``powerups`` dropped at their feet, the player gets
    :data:`TICKET_SERVED_FLAG` set and the ticket is spent.  Did not: the
    ticket is void; take another.  ``level notify( "zmf_ticket_served",
    e_player )`` is sent on each serve.

    **Priority.**  Every ticket line sets ``level.zmf_gag_hush`` (calls) or
    ``player.zmf_gag_hush`` (the kiosk) ``hush`` seconds ahead, and
    :func:`zmforge.script.gags.gag_say` holds its centre-screen lines until
    then, so the gags never stack on a call.

    Stock sources: the trigger as the perk machine's (``_zm_perks.gsc:
    1513-1523``) and team-gather trigger's (``teamgather_shared.gsc:
    237-242``); ``IPrintLnBold( &"...", value )`` ``_weapons.gsc:979``;
    ``level.round_number`` / ``start_of_round`` ``_zm.gsc:4433``;
    ``add_to_player_score`` ``_zm_score.gsc:521``; ``specific_powerup_drop``
    ``_zm_ai_raps.gsc:590`` (the names are registered by the modules
    ``zm_usermap.gsc:40-47`` uses: ``register_powerup( "double_points" ...
    )`` ``_zm_powerup_double_points.gsc:35``, ``"insta_kill"``
    ``_zm_powerup_insta_kill.gsc:34``, ``"full_ammo"``
    ``_zm_powerup_full_ammo.gsc:37``); HUD text ``NewClientHudElem`` +
    ``SetText( line, a, b )`` ``teamgather_shared.gsc:733,813``, centred as
    ``_zm.gsc:4881-4884``.  **Unverified in play.**
    """
    if not 2 <= int(numbers) <= 99:
        raise ValueError("numbers: 2 to 99")
    if (mine is None) != (mine_early is None) and calls is not None:
        raise ValueError("give mine and mine_early together")
    n_max = int(numbers)
    at = _vector(origin)
    early = yours_early if (calls is not None and yours_early is not None) else yours
    setup = [
        'level endon( "end_game" );',
        # The calls close the kiosk for good (TicketCalls.stop_when): this
        # loop ends then, before the trigger is deleted under it.
        'level endon( "zmf_ticket_closed" );',
        f"level.zmf_ticket_open = {0 if calls is not None else 1};",
        f't_ticket = spawn( "trigger_radius_use", {at}, 0, '
        f"{float(radius):g}, {float(height):g} );",
        "level.zmf_ticket_kiosk = t_ticket;",
        "t_ticket TriggerIgnoreTeam();",
        "t_ticket SetVisibleToAll();",
        't_ticket SetTeamForTrigger( "none" );',
        't_ticket SetCursorHint( "HINT_NOICON" );',
        f't_ticket SetHintString( &"{prompt}" );',
    ]
    if welcome is not None:
        setup.append("level thread zmf_ticket_welcome();")
    if calls is not None:
        setup.append("level thread zmf_ticket_caller();")
    if mine is not None:
        setup.append("level thread zmf_ticket_hud_attach();")
    functions = [
        CustomFunction(
            "zmf_take_a_ticket",
            (
                *setup,
                "while ( true )",
                "{",
                '\tt_ticket waittill( "trigger", e_who );',
                "\tif ( !isplayer( e_who ) )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                *((
                    f"\tif ( isdefined( e_who.{TICKET_SERVED_FLAG} ) )",
                    "\t{",
                    f"\t\te_who.zmf_gag_hush = gettime() + {_ms(hush)};",
                    f'\t\te_who IPrintLnBold( &"{already_served}" );',
                    f"\t\twait {float(reset_after):g};",
                    "\t\tcontinue;",
                    "\t}",
                ) if already_served else ()),
                "\te_who.zmf_my_ticket = zmf_ticket_free( e_who );",
                # When it was taken: calls go to the longest-waiting holder.
                "\te_who.zmf_ticket_time = gettime();",
                f'\tt_ticket SetHintString( &"{number}", e_who.zmf_my_ticket );',
                '\tlevel notify( "zmf_ticket_hud" );',
                f"\te_who.zmf_gag_hush = gettime() + {_ms(hush)};",
                "\tif ( level.zmf_ticket_open )",
                "\t{",
                f'\t\te_who IPrintLnBold( &"{yours}", e_who.zmf_my_ticket );',
                "\t}",
                "\telse",
                "\t{",
                f'\t\te_who IPrintLnBold( &"{early}", e_who.zmf_my_ticket );',
                "\t}",
                f"\twait {float(reset_after):g};",
                # Closed (and deleted) during the wait: touch nothing.
                "\tif ( !isdefined( t_ticket ) || isdefined( level.zmf_ticket_closed ) )",
                "\t{",
                "\t\treturn;",
                "\t}",
                f'\tt_ticket SetHintString( &"{prompt}" );',
                "}",
            ),
            purpose=(
                "Take a number: a script-spawned use trigger that hands out\n"
                f"tickets 1 to {n_max}, one per player, never one another player holds."
            ),
        ),
        CustomFunction(
            "zmf_ticket_free",
            (
                "a_free = [];",
                "a_players = getplayers();",
                f"for ( n = 1; n <= {n_max}; n++ )",
                "{",
                "\tb_held = false;",
                "\tfor ( i = 0; i < a_players.size; i++ )",
                "\t{",
                "\t\tif ( a_players[ i ] != e_who && isdefined( a_players[ i ].zmf_my_ticket ) "
                "&& a_players[ i ].zmf_my_ticket == n )",
                "\t\t{",
                "\t\t\tb_held = true;",
                "\t\t}",
                "\t}",
                "\tif ( !b_held )",
                "\t{",
                "\t\ta_free[ a_free.size ] = n;",
                "\t}",
                "}",
                "if ( a_free.size == 0 )",
                "{",
                f"\treturn randomintrange( 1, {n_max + 1} );",
                "}",
                "return a_free[ randomint( a_free.size ) ];",
            ),
            params=("e_who",),
            purpose="A ticket number no other player holds (a player who left holds none).",
        ),
    ]
    if welcome is not None:
        functions.append(
            CustomFunction(
                "zmf_ticket_welcome",
                (
                    'level endon( "end_game" );',
                    f't_near = spawn( "trigger_radius", {at}, 0, '
                    f"{float(welcome_radius):g}, {float(height):g} );",
                    "while ( true )",
                    "{",
                    '\tt_near waittill( "trigger", e_who );',
                    "\tif ( !isplayer( e_who ) || isdefined( e_who.zmf_ticket_welcomed ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\te_who.zmf_ticket_welcomed = 1;",
                    f'\te_who IPrintLnBold( &"{welcome}" );',
                    "}",
                ),
                purpose=(
                    "Once per player, near the ticket machine: tell them to take\n"
                    "a number.  spawn( \"trigger_radius\" ): doors_shared.gsc:1190."
                ),
            )
        )
    using: list[str] = []
    notes = [f"take-a-number kiosk, tickets 1-{n_max}"]
    if calls is not None:
        c = calls
        functions += _ticket_call_functions(c, n_max)
        using += [_LASTSTAND, _SCORE, _POWERUPS]
        notes.append(f"a call every {c.every:g}s from round {c.start_round}, "
                     f"{c.grace:g}s to reach the window")
    if mine is not None:
        functions += _ticket_hud_functions(mine, mine_early or mine, calls)
        using.append(_FLAG)
    return CustomScript(
        using=tuple(dict.fromkeys(using)),
        functions=tuple(functions),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_take_a_ticket();"),),
        notes=tuple(notes),
    )


def _ticket_call_functions(c: TicketCalls, n_max: int) -> list[CustomFunction]:
    win = _vector(c.window)
    steps = max(1, math.ceil(c.grace))
    step_wait = c.grace / steps
    pows = list(c.powerups)
    caller = [
        'level endon( "end_game" );',
        "level.zmf_ticket_calling = 0;",
        f"while ( level.round_number < {int(c.start_round)} )",
        "{",
        '\tlevel waittill( "start_of_round" );',
        "}",
        *(line for z in c.zones for line in (
            f'while ( !zm_zonemgr::zone_is_enabled( "{z}" ) )',
            "{",
            "\twait 1;",
            "}",
        )),
        "level.zmf_ticket_open = 1;",
        'level notify( "zmf_ticket_hud" );',
    ]
    if c.opened:
        caller += [
            f"level.zmf_gag_hush = gettime() + {_ms(4.0)};",
            f'zmf_ticket_all( &"{c.opened}", undefined, undefined );',
        ]
    caller += [
        "a_pow = [];",
        *(f'a_pow[ {n} ] = "{p}";' for n, p in enumerate(pows)),
        "while ( true )",
        "{",
        *((
            f"\tn_wait = {float(c.every):g};",
            f"\tif ( zmf_ticket_holders() > {int(c.busy_holders)} )",
            "\t{",
            f"\t\tn_wait = {float(c.busy_every):g};",
            "\t}",
            "\twait n_wait;",
        ) if c.busy_every is not None else (f"\twait {float(c.every):g};",)),
        *((
            f"\tif ( {c.stop_when} )",
            "\t{",
            "\t\tbreak;",
            "\t}",
        ) if c.stop_when else ()),
        "\tn_call = zmf_ticket_pick();",
        # 0: nobody holds a ticket and every call is a held one; skip it.
        "\tif ( n_call == 0 )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\te_called = undefined;",
        "\ta_players = getplayers();",
        "\tfor ( i = 0; i < a_players.size; i++ )",
        "\t{",
        "\t\tif ( isdefined( a_players[ i ].zmf_my_ticket ) && a_players[ i ].zmf_my_ticket == n_call )",
        "\t\t{",
        "\t\t\te_called = a_players[ i ];",
        "\t\t}",
        "\t}",
        # The call owns the centre of the screen: gags wait until it is over.
        f"\tlevel.zmf_gag_hush = gettime() + {_ms(c.grace + 4.0)};",
        "\tlevel.zmf_ticket_calling = n_call;",
        "\tlevel.zmf_ticket_called = e_called;",
        f'\tzmf_ticket_all( &"{c.call}", n_call, undefined );',
        "\tif ( isdefined( e_called ) )",
        "\t{",
        f'\t\te_called IPrintLnBold( &"{c.you}", n_call );',
        "\t}",
        "\tlevel thread zmf_ticket_countdown( n_call, e_called );",
        "\tb_served = false;",
        f"\tn_end = gettime() + {_ms(c.grace)};",
        "\tn_fx = 0;",
        "\twhile ( gettime() < n_end )",
        "\t{",
    ]
    if c.pulse_fx:
        caller += [
            "\t\tif ( gettime() >= n_fx )",
            "\t\t{",
            f'\t\t\tPlayFX( level._effect[ "{c.pulse_fx}" ], {win} );',
            "\t\t\tn_fx = gettime() + 1000;",
            "\t\t}",
        ]
    caller += [
        "\t\tif ( isdefined( e_called ) && isdefined( e_called.zmf_my_ticket ) "
        "&& e_called.zmf_my_ticket == n_call && e_called zmf_ticket_at_window() )",
        "\t\t{",
        "\t\t\tb_served = true;",
        "\t\t\tbreak;",
        "\t\t}",
        "\t\twait 0.1;",
        "\t}",
        "\tlevel.zmf_ticket_calling = 0;",
        '\tlevel notify( "zmf_ticket_call_over" );',
        f"\tlevel.zmf_gag_hush = gettime() + {_ms(3.0)};",
        "\tif ( b_served )",
        "\t{",
        "\t\te_called.zmf_my_ticket = undefined;",
        f"\t\te_called.{TICKET_SERVED_FLAG} = 1;",
        f"\t\te_called zm_score::add_to_player_score( {int(c.points)} );",
        "\t\tlevel thread zm_powerups::specific_powerup_drop( a_pow[ randomint( a_pow.size ) ], "
        "e_called.origin );",
        f'\t\te_called IPrintLnBold( &"{c.served}" );',
        "\t\ta_players = getplayers();",
        "\t\tfor ( i = 0; i < a_players.size; i++ )",
        "\t\t{",
        "\t\t\tif ( a_players[ i ] != e_called )",
        "\t\t\t{",
        f'\t\t\t\ta_players[ i ] IPrintLnBold( &"{c.served_all}", e_called );',
        "\t\t\t}",
        "\t\t}",
        '\t\tlevel notify( "zmf_ticket_served", e_called );',
        "\t}",
        "\telse if ( isdefined( e_called ) )",
        "\t{",
        "\t\te_called.zmf_my_ticket = undefined;",
        f'\t\tzmf_ticket_all( &"{c.missed}", n_call, undefined );',
        "\t}",
        "\telse",
        "\t{",
        f'\t\tzmf_ticket_all( &"{c.no_one}", n_call, undefined );',
        "\t}",
        '\tlevel notify( "zmf_ticket_hud" );',
        "}",
    ]
    if c.stop_when:
        # The calls are over for good: no more numbers, no kiosk prompt.
        caller += [
            "level.zmf_ticket_open = 0;",
            "level.zmf_ticket_closed = 1;",
            # Stop the kiosk loop and stop taking presses before the delete.
            'level notify( "zmf_ticket_closed" );',
            "if ( isdefined( level.zmf_ticket_kiosk ) )",
            "{",
            '\tlevel.zmf_ticket_kiosk SetHintString( "" );',
            "\tlevel.zmf_ticket_kiosk TriggerEnable( false );",
            "\tlevel.zmf_ticket_kiosk delete();",
            "}",
            'level notify( "zmf_ticket_hud" );',
        ]
    return [
        CustomFunction(
            "zmf_ticket_caller",
            tuple(caller),
            purpose=(
                f"From round {c.start_round}: a number every {c.every:g}s; its holder has\n"
                f"{c.grace:g}s to stand at the window.  Served: points and a powerup\n"
                "(add_to_player_score _zm_score.gsc:521, specific_powerup_drop\n"
                "_zm_ai_raps.gsc:590).  Missed: the ticket is void."
            ),
        ),
        CustomFunction(
            "zmf_ticket_pick",
            (
                # The longest-waiting unserved holder's number, so calls
                # rotate fairly and a solo player is called every time.
                "n_best = 0;",
                "n_since = 0;",
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                "\te_p = a_players[ i ];",
                f"\tif ( isdefined( e_p.zmf_my_ticket ) && !isdefined( e_p.{TICKET_SERVED_FLAG} ) )",
                "\t{",
                "\t\tn_t = 0;",
                "\t\tif ( isdefined( e_p.zmf_ticket_time ) )",
                "\t\t{",
                "\t\t\tn_t = e_p.zmf_ticket_time;",
                "\t\t}",
                "\t\tif ( n_best == 0 || n_t < n_since )",
                "\t\t{",
                "\t\t\tn_best = e_p.zmf_my_ticket;",
                "\t\t\tn_since = n_t;",
                "\t\t}",
                "\t}",
                "}",
                *((
                    "return n_best;",
                ) if c.held_chance >= 100 else (
                    f"if ( n_best > 0 && randomint( 100 ) < {int(c.held_chance)} )",
                    "{",
                    "\treturn n_best;",
                    "}",
                    f"return randomintrange( 1, {n_max + 1} );",
                )),
            ),
            purpose=("The number to call: the longest-waiting unserved holder's, or 0\n"
                     "(no call) when nobody holds one." if c.held_chance >= 100 else
                     f"The number to call: {c.held_chance}% the longest-waiting unserved\n"
                     f"holder's, else any of 1-{n_max}."),
        ),
        *((CustomFunction(
            "zmf_ticket_holders",
            (
                "n = 0;",
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                f"\tif ( isdefined( a_players[ i ].zmf_my_ticket ) && !isdefined( a_players[ i ].{TICKET_SERVED_FLAG} ) )",
                "\t{",
                "\t\tn++;",
                "\t}",
                "}",
                "return n;",
            ),
            purpose="Unserved ticket holders: more than a few and the calls come faster.",
        ),) if c.busy_every is not None else ()),
        CustomFunction(
            "zmf_ticket_at_window",
            (
                'if ( self.sessionstate == "spectator" || self laststand::player_is_in_laststand() )',
                "{",
                "\treturn false;",
                "}",
                f"if ( Distance2DSquared( self.origin, {win} ) > {c.radius * c.radius:g} )",
                "{",
                "\treturn false;",
                "}",
                f"return abs( self.origin[ 2 ] - {float(c.window[2]):g} ) <= {c.height:g};",
            ),
            purpose=("Standing at the window: not down (laststand_shared.gsc:12),\n"
                     "within the radius (Distance2DSquared, _zm_ai_wasp.gsc:1291)."),
        ),
        CustomFunction(
            "zmf_ticket_countdown",
            (
                'level endon( "end_game" );',
                'level endon( "zmf_ticket_call_over" );',
                "a_players = getplayers();",
                f"for ( n = {steps}; n > 0; n-- )",
                "{",
                "\tfor ( i = 0; i < a_players.size; i++ )",
                "\t{",
                "\t\te_p = a_players[ i ];",
                "\t\tif ( !isdefined( e_p ) || !isdefined( e_p.zmf_tk_call ) )",
                "\t\t{",
                "\t\t\tcontinue;",
                "\t\t}",
                "\t\tif ( isdefined( e_called ) && e_p == e_called )",
                "\t\t{",
                f'\t\t\te_p.zmf_tk_call SetText( &"{c.hud_you}", n_call, n );',
                "\t\t}",
                "\t\telse",
                "\t\t{",
                f'\t\t\te_p.zmf_tk_call SetText( &"{c.hud_call}", n_call, n );',
                "\t\t}",
                "\t\te_p.zmf_tk_call.alpha = 1;",
                "\t}",
                f"\twait {step_wait:g};",
                "}",
            ),
            params=("n_call", "e_called"),
            purpose="The called number and the seconds left, centre top, for the call.",
        ),
        CustomFunction(
            "zmf_ticket_all",
            (
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                "\tif ( isdefined( a ) )",
                "\t{",
                "\t\ta_players[ i ] IPrintLnBold( str_line, a );",
                "\t}",
                "\telse",
                "\t{",
                "\t\ta_players[ i ] IPrintLnBold( str_line );",
                "\t}",
                "}",
            ),
            params=("str_line", "a", "b"),
            purpose="A ticket line bold to everyone, with or without its number.",
        ),
    ]


def _ticket_hud_functions(mine: str, mine_early: str,
                          calls: TicketCalls | None) -> list[CustomFunction]:
    clear_call = [
        "\tif ( isdefined( self.zmf_tk_call ) && !level.zmf_ticket_calling )",
        "\t{",
        "\t\tself.zmf_tk_call.alpha = 0;",
        "\t}",
    ] if calls is not None else []
    return [
        CustomFunction(
            "zmf_ticket_hud_attach",
            (
                'level endon( "end_game" );',
                'level flag::wait_till( "initial_blackscreen_passed" );',
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                "\ta_players[ i ] thread zmf_ticket_hud_player();",
                "}",
                "while ( true )",
                "{",
                '\tlevel waittill( "connected", player );',
                "\tplayer thread zmf_ticket_hud_player();",
                "}",
            ),
            purpose=('The ticket HUD on everyone, now and on join (level waittill(\n'
                     '"connected", player ): _zm.gsc:463).'),
        ),
        CustomFunction(
            "zmf_ticket_hud_player",
            (
                'self endon( "disconnect" );',
                "if ( isdefined( self.zmf_tk_mine ) )",
                "{",
                "\treturn;",
                "}",
                "self.zmf_tk_mine = NewClientHudElem( self );",
                'self.zmf_tk_mine.font = "objective";',
                'self.zmf_tk_mine.alignX = "left";',
                'self.zmf_tk_mine.alignY = "top";',
                'self.zmf_tk_mine.horzAlign = "user_left";',
                'self.zmf_tk_mine.vertAlign = "user_top";',
                "self.zmf_tk_mine.x = 16;",
                "self.zmf_tk_mine.y = 62;",
                "self.zmf_tk_mine.foreground = true;",
                "self.zmf_tk_mine.fontScale = 1.2;",
                "self.zmf_tk_mine.color = ( 0.75, 0.9, 1 );",
                "self.zmf_tk_mine.hidewheninmenu = true;",
                "self.zmf_tk_mine.alpha = 0;",
                "self.zmf_tk_call = NewClientHudElem( self );",
                'self.zmf_tk_call.font = "objective";',
                'self.zmf_tk_call.alignX = "center";',
                'self.zmf_tk_call.alignY = "top";',
                'self.zmf_tk_call.horzAlign = "user_center";',
                'self.zmf_tk_call.vertAlign = "user_top";',
                "self.zmf_tk_call.x = 0;",
                "self.zmf_tk_call.y = 90;",
                "self.zmf_tk_call.foreground = true;",
                "self.zmf_tk_call.fontScale = 1.8;",
                "self.zmf_tk_call.color = ( 1, 0.82, 0.3 );",
                "self.zmf_tk_call.hidewheninmenu = true;",
                "self.zmf_tk_call.alpha = 0;",
                "self thread zmf_ticket_hud_end();",
                'level endon( "end_game" );',
                "while ( true )",
                "{",
                "\tif ( isdefined( self.zmf_my_ticket ) )",
                "\t{",
                "\t\tif ( level.zmf_ticket_open )",
                "\t\t{",
                f'\t\t\tself.zmf_tk_mine SetText( &"{mine}", self.zmf_my_ticket );',
                "\t\t}",
                "\t\telse",
                "\t\t{",
                f'\t\t\tself.zmf_tk_mine SetText( &"{mine_early}", self.zmf_my_ticket );',
                "\t\t}",
                "\t\tself.zmf_tk_mine.alpha = 1;",
                "\t}",
                "\telse",
                "\t{",
                "\t\tself.zmf_tk_mine.alpha = 0;",
                "\t}",
                *clear_call,
                '\tlevel waittill( "zmf_ticket_hud" );',
                "}",
            ),
            purpose=("This player's ticket line (top left, under the objective) and the\n"
                     "call countdown line (centre top).  NewClientHudElem and fields:\n"
                     "teamgather_shared.gsc:811-827; user_center: _zm.gsc:4883."),
        ),
        CustomFunction(
            "zmf_ticket_hud_end",
            (
                'self endon( "disconnect" );',
                'level waittill( "end_game" );',
                "self.zmf_tk_mine destroy();",
                "self.zmf_tk_call destroy();",
            ),
            purpose="Off the screen before the end screen (destroy: _zm_laststand.gsc:448).",
        ),
    ]


def use_notices(
    notices: Sequence[tuple[object, str, Sequence[str]]],
    *,
    radius: float = 36.0,
    height: float = 72.0,
    cooldown: float = 1.5,
    gap: float = 0.25,
    ends: Sequence[str | None] | None = None,
) -> CustomScript:
    """Use triggers that say something and do nothing else.

    Each notice is ``(origin, prompt, replies)``: *prompt* is the asset name
    of a ``triggerstring`` (:meth:`~zmforge.blueprint.model.Blueprint.
    add_map_string`) shown while a player stands in reach, and *replies* are
    ``string`` assets printed, in turn, to whoever presses use -- the next
    press gets the next line, and the last wraps round to the first.  It is
    :func:`take_a_ticket` without the counter: the same script-spawned
    ``trigger_radius_use`` set up the same way (``teamgather_shared.gsc:237-
    242``), one thread per notice, so a map can hang a line of text on any
    prop without art and without Lua.  Nothing is bought, granted or blocked:
    a notice is not an element, so no model check sees it, and the caller
    keeps it clear of the map's real use triggers.

    **Every reply is a centre-screen line** (``IPrintLnBold``, the call the
    ticket machine uses), so what the notice says is on screen and not only
    on a prompt the player is walking away from.  **Rate limit:** one reply
    per player per ``cooldown`` seconds across all notices (``gettime()``
    against ``zmf_notice_next`` on the player), and ``gap`` seconds between
    two replies from one notice.  **Unverified in play.**

    ``ends`` (optional, one entry per notice) names a level notify that
    retires the notice: its thread ends and its trigger is deleted, so a
    notice about something that is over (the rules of an opening that has
    resolved) does not outlive it (P12).  ``None`` keeps a notice for the
    whole game.  With no ends at all the script is exactly what it was.
    """
    notices = list(notices)
    if not notices:
        raise ValueError("use_notices needs at least one notice")
    end_list = list(ends) if ends is not None else [None] * len(notices)
    if len(end_list) != len(notices):
        raise ValueError("use_notices: one end (or None) per notice")
    for end in end_list:
        if end is not None and not re.fullmatch(r"[a-z_][a-z0-9_]*", end):
            raise ValueError(f"use_notices: {end!r} is not a notify name")
    ending = any(end is not None for end in end_list)
    calls: list[str] = []
    for index, (origin, prompt, replies) in enumerate(notices):
        if not prompt:
            raise ValueError(f"notice {index} has no prompt")
        replies = list(replies)
        if not replies:
            raise ValueError(f"notice {index} ({prompt}) says nothing when used")
        # One array per notice, never reused: whether a thread's array
        # argument is a copy or a reference is not something this package
        # has measured, so nothing is written to one after it is passed.
        name = f"a_lines_{index}"
        calls.append(f"{name} = [];")
        calls += [f'{name}[{n}] = &"{reply}";' for n, reply in enumerate(replies)]
        end = end_list[index]
        tail = (f', "{end}"' if end is not None else ", undefined") if ending else ""
        calls.append(
            f'level thread zmf_notice( {_vector(origin)}, &"{prompt}", {name}{tail} );'
        )
    retire = (
        ["if ( isdefined( str_end ) )", "{", "\tlevel endon( str_end );", "}"]
        if ending else []
    )
    watch = (
        ["if ( isdefined( str_end ) )", "{",
         "\tlevel thread zmf_notice_end( t_notice, str_end );", "}"]
        if ending else []
    )
    end_fns = (
        CustomFunction(
            "zmf_notice_end",
            (
                'level endon( "end_game" );',
                "level waittill( str_end );",
                "if ( isdefined( t_notice ) )",
                "{",
                "\tt_notice delete();",
                "}",
            ),
            params=("t_notice", "str_end"),
            purpose="Delete a notice's trigger when what it is about is over.",
        ),
    ) if ending else ()
    return CustomScript(
        functions=(
            CustomFunction(
                "zmf_notice",
                (
                    'level endon( "end_game" );',
                    *retire,
                    't_notice = spawn( "trigger_radius_use", v_origin, 0, '
                    f"{float(radius):g}, {float(height):g} );",
                    *watch,
                    "t_notice TriggerIgnoreTeam();",
                    "t_notice SetVisibleToAll();",
                    't_notice SetTeamForTrigger( "none" );',
                    't_notice SetCursorHint( "HINT_NOICON" );',
                    "t_notice SetHintString( str_prompt );",
                    "n_line = 0;",
                    "while ( true )",
                    "{",
                    '\tt_notice waittill( "trigger", e_who );',
                    "\tif ( !isplayer( e_who ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    # Per player: one reply per cooldown, whichever
                    # notice it came from, so holding use (the trigger fires
                    # every frame) or running along a row of them does not
                    # stack lines.  Per notice: a short gap between players.
                    "\tn_now = gettime();",
                    "\tif ( isdefined( e_who.zmf_notice_next ) && n_now < e_who.zmf_notice_next )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\te_who.zmf_notice_next = n_now + {int(round(float(cooldown) * 1000))};",
                    "\te_who IPrintLnBold( a_lines[ n_line ] );",
                    "\tn_line = ( n_line + 1 ) % a_lines.size;",
                    f"\twait {float(gap):g};",
                    "}",
                ),
                params=("v_origin", "str_prompt", "a_lines",
                        *(("str_end",) if ending else ())),
                purpose=(
                    "One notice: a script-spawned use trigger whose prompt is a\n"
                    "line of the map's own text, and whose use prints the next reply."
                ),
            ),
            *end_fns,
            CustomFunction(
                "zmf_notices",
                ('level endon( "end_game" );', *calls),
                purpose="Every notice the map hangs on a prop, one thread each.",
            ),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_notices();"),),
        notes=(f"{len(notices)} use notices (text only, nothing bought)",),
    )
