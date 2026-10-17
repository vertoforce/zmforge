"""On-screen gags: rate-limited lines a player cannot miss, and the hooks that say them.

A joke that lives only on a use prompt is a joke most players walk past.  The
pieces here put a line of the map's own text **in the player's face** at the
moment something happens -- they go down, they buy a perk, they walk into a
room -- and say plainly what happened.  Every line is a map string
(:meth:`~zmforge.blueprint.model.Blueprint.add_map_string`, kind ``string``),
so each is precached and shipped in the map's ``.str``; nothing here is Lua.

**What a usermap server script may print, and how its text ships.**  Read in
the mod tools' own ``share/raw/scripts`` (what the linker compiles):

=====================  ==============================================================
call                   evidence
=====================  ==============================================================
``p IPrintLnBold``     centre-screen bold, one player.  Localized with a parameter:
                       ``shared/weapons/_weapons.gsc:979 player iPrintLnBold(
                       &"MP_GRENADE_UNAVAILABLE_FOR_N", " " + timeLeft + " ",
                       &"EXE_SECONDS" );``; localized, no parameter:
                       ``mp/killstreaks/_sentinel.gsc:284 self iPrintLnBold(
                       &"KILLSTREAK_SENTINEL_NOT_AVAILABLE" );``.
``p IPrintLn``         the kill-feed line, one player:
                       ``zm/gametypes/_zm_gametype.gsc:815 self iprintln(
                       &"MP_HOST_ENDGAME_RESPONSE" );``.  With a *player* as the
                       parameter: ``zm/gametypes/_globallogic_player.gsc:71
                       iPrintLn(&"MP_CONNECTED", self);``.
``show_hint_text``     HUD text low in the middle, one player, fades itself:
                       ``zm/_zm_equipment.gsc:587 function show_hint_text( text,
                       show_for_time = 3.20, ... )`` -> ``self.hintelem
                       setText(text)``; called as ``zm/_zm_hero_weapon.gsc:182
                       self thread zm_equipment::show_hint_text(
                       &"ZOMBIE_HERO_WEAPON_HINT", 2 );``.  No parameter.
=====================  ==============================================================

**Localized, always.**  Plain literals compile too
(``shared/abilities/gadgets/_gadget_shield.gsc:148 self IPrintlnBold( "Shield
Flicker: " + ... )``, behind a dvar) and community maps print them, but whether
``&&1`` substitutes inside a plain literal is unresolved (spec, "wall buy's
hint"), so every line here is a ``&"<MAP>_..."`` string and ``&&1`` is only
ever used where the stock scripts pass a parameter to a localized string.
There is no ``zm_utility`` hint helper: ``_zm_utility.gsc`` has none, and the
one HUD-text helper the ZM scripts share is ``zm_equipment::show_hint_text``
above.  ``NewClientHudElem`` + ``setText`` (``zm/_zm.gsc:4880``,
``zm/craftables/_zm_craftables.gsc:2659 hintTextHudElem setText(
&"ZOMBIE_CRAFTABLE_CHANGE_BUILD" );``) is what that helper wraps, so it is not
used raw.

**Unverified in play:** that a player-entity parameter renders as the
player's name in ``&&1`` (``MP_CONNECTED``'s own text is not in the install to
read), and how any of these lines look on screen.  The feed lines that name a
player (``*_feed``) are the ones that lean on it.

**Rate limits.**  :func:`gag_say` keeps two clocks per player: a per-gag
cooldown (a gag already said to this player inside its cooldown is dropped),
and one slot clock for the centre of the screen, so bold and HUD lines to one
player are at least :data:`SAY_GAP` apart and a backlog deeper than
:data:`SAY_BACKLOG` is dropped rather than queued.  Feed lines skip the slot
(the feed scrolls on its own) but keep the per-gag cooldown.  Lines to
everybody also keep a level-wide per-gag cooldown.

**The hooks**, every one a stock notify or hook read in the same tree:

====================  =======================================================
event                 wait
====================  =======================================================
downed                ``self waittill( "player_downed" )``
                      (``zm/_zm_laststand.gsc:270 self notify( "player_downed" );``)
bled out              ``"bled_out"`` (``zm/_zm_laststand.gsc:523``, ``:580``)
revived               ``self waittill( "player_revived", e_reviver )``
                      (``zm/_zm_laststand.gsc:1392``, ``:1430 self notify (
                      "player_revived", reviver );``; waited the same way at
                      ``zm/_zm.gsc:2403``)
perk bought           ``self waittill( "perk_bought", str_perk )``
                      (``zm/_zm_perks.gsc:747 self notify( "perk_bought", perk
                      );`` in ``give_perk`` when bought), matched on the
                      specialty string
pack-a-punch          ``self waittill( "pap_taken" )``
                      (``zm/_zm_pack_a_punch.gsc:637 player notify( "pap_taken" );``)
mystery box used      ``level._magic_box_used_VO`` (``zm/_zm_magicbox.gsc:655-657``:
                      ``user thread [[ level._magic_box_used_VO ]]();`` after the
                      box is paid for).  Nothing in the stock tree assigns it,
                     so taking it clobbers nothing.
box moved             ``level waittill( "weapon_fly_away_start" )``
                      (``zm/_zm_magicbox.gsc:1750``)
round start / end     ``level waittill( "start_of_round" )`` / ``"end_of_round"``
                      (``zm/_zm.gsc:4433`` / ``:4449``)
room entered          ``self zm_zonemgr::get_player_zone()``
                      (``zm/_zm_zonemgr.gsc:89``, returns
                      ``zm_utility::get_current_zone()``), polled; the zone
                      names are the ones the generated ``main`` passes to
                      ``manage_zones``
power on              ``level flag::wait_till( "power_on" )``
teleporter hop        ``self waittill( "zmf_hopped<suffix>" )``, notified by
                      :func:`zmforge.script.tricks.short_hop_teleporter` on
                      the player it moved
====================  =======================================================

A player's watchers go on everyone present and everyone who joins, the way
:func:`zmforge.script.tricks._fired_watchers` does it
(``level waittill( "connected", player )``).  **Unverified in play.**
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "SAY_BOLD",
    "SAY_FEED",
    "SAY_HINT",
    "SAY_GAP",
    "SAY_BACKLOG",
    "COOLDOWNS",
    "gag_say",
    "player_reactions",
    "box_reactions",
    "round_announcer",
    "random_announcements",
    "power_on_announcement",
]

_EQUIPMENT = r"scripts\zm\_zm_equipment"
_ZONEMGR = r"scripts\zm\_zm_zonemgr"
_SCORE = r"scripts\zm\_zm_score"
_FLAG = r"scripts\shared\flag_shared"

#: How a line is said: centre-screen bold, the feed line, or HUD hint text.
SAY_BOLD, SAY_FEED, SAY_HINT = 0, 1, 2
#: Seconds between two centre-screen lines to one player.
SAY_GAP = 1.5
#: A centre-screen line that would wait longer than this is dropped.
SAY_BACKLOG = 6.0

#: Per-gag cooldowns, seconds.  Per player for the reactions, level-wide for
#: the lines everybody gets.
COOLDOWNS: dict[str, float] = {
    "downed": 10.0,
    "downed_feed": 3.0,
    "bled_out_feed": 3.0,
    "revived": 10.0,
    "reviver": 10.0,
    "perk": 5.0,
    "pap": 15.0,
    "box": 20.0,
    "box_moved": 30.0,
    "hop": 6.0,
    "hop_feed": 10.0,
    "idle": 120.0,
    "pa_random": 60.0,
}


def _ms(seconds: float) -> int:
    return int(round(float(seconds) * 1000))


def _str(asset: str) -> str:
    return f'&"{asset}"'


def gag_say(*, gap: float = SAY_GAP, backlog: float = SAY_BACKLOG) -> CustomScript:
    """The two sayers every gag goes through.

    ``player zmf_gag_say( str_gag, str_line, n_cooldown_ms, n_mode, param )``
    says one line to one player; ``zmf_gag_say_all( ..., param, e_skip )``
    says it to everybody but ``e_skip``, once per level-wide cooldown.
    ``n_mode`` is :data:`SAY_BOLD`, :data:`SAY_FEED` or :data:`SAY_HINT`;
    ``param`` (optional) is the line's ``&&1``.  Rate limits: the module
    docstring.  **Unverified in play.**
    """
    say = CustomFunction(
        "zmf_gag_say",
        (
            'self endon( "disconnect" );',
            "if ( !isplayer( self ) )",
            "{",
            "\treturn;",
            "}",
            "n_now = gettime();",
            "if ( !isdefined( self.zmf_gag_next ) )",
            "{",
            "\tself.zmf_gag_next = [];",
            "}",
            "if ( isdefined( self.zmf_gag_next[ str_gag ] ) && n_now < self.zmf_gag_next[ str_gag ] )",
            "{",
            "\treturn;",
            "}",
            f"if ( n_mode == {SAY_FEED} )",
            "{",
            "\tself.zmf_gag_next[ str_gag ] = n_now + n_cooldown;",
            "\tif ( isdefined( param ) )",
            "\t{",
            "\t\tself IPrintLn( str_line, param );",
            "\t}",
            "\telse",
            "\t{",
            "\t\tself IPrintLn( str_line );",
            "\t}",
            "\treturn;",
            "}",
            "if ( !isdefined( self.zmf_gag_slot ) || self.zmf_gag_slot < n_now )",
            "{",
            "\tself.zmf_gag_slot = n_now;",
            "}",
            # Quest lines and ticket calls own the centre of the screen: a
            # gag waits until their hush is over (or is dropped, below).
            "if ( isdefined( level.zmf_gag_hush ) && self.zmf_gag_slot < level.zmf_gag_hush )",
            "{",
            "\tself.zmf_gag_slot = level.zmf_gag_hush;",
            "}",
            "if ( isdefined( self.zmf_gag_hush ) && self.zmf_gag_slot < self.zmf_gag_hush )",
            "{",
            "\tself.zmf_gag_slot = self.zmf_gag_hush;",
            "}",
            f"if ( self.zmf_gag_slot - n_now > {_ms(backlog)} )",
            "{",
            "\treturn;",
            "}",
            "self.zmf_gag_next[ str_gag ] = n_now + n_cooldown;",
            "n_wait = self.zmf_gag_slot - n_now;",
            f"self.zmf_gag_slot = self.zmf_gag_slot + {_ms(gap)};",
            "if ( n_wait > 0 )",
            "{",
            "\twait( n_wait / 1000 );",
            "}",
            f"if ( n_mode == {SAY_HINT} )",
            "{",
            "\tself thread zm_equipment::show_hint_text( str_line, 4 );",
            "}",
            "else if ( isdefined( param ) )",
            "{",
            "\tself IPrintLnBold( str_line, param );",
            "}",
            "else",
            "{",
            "\tself IPrintLnBold( str_line );",
            "}",
        ),
        params=("str_gag", "str_line", "n_cooldown", "n_mode", "param"),
        purpose=(
            "Say one gag line to this player, rate-limited per gag and spaced\n"
            "on the centre of the screen.  IPrintLnBold: _weapons.gsc:979;\n"
            "IPrintLn: _zm_gametype.gsc:815; show_hint_text: _zm_equipment.gsc:587."
        ),
    )
    say_all = CustomFunction(
        "zmf_gag_say_all",
        (
            "if ( !isdefined( level.zmf_gag_next ) )",
            "{",
            "\tlevel.zmf_gag_next = [];",
            "}",
            "n_now = gettime();",
            "if ( isdefined( level.zmf_gag_next[ str_gag ] ) && n_now < level.zmf_gag_next[ str_gag ] )",
            "{",
            "\treturn;",
            "}",
            "level.zmf_gag_next[ str_gag ] = n_now + n_cooldown;",
            "a_players = getplayers();",
            "for ( i = 0; i < a_players.size; i++ )",
            "{",
            "\tif ( isdefined( e_skip ) && a_players[ i ] == e_skip )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\ta_players[ i ] thread zmf_gag_say( str_gag, str_line, 0, n_mode, param );",
            "}",
        ),
        params=("str_gag", "str_line", "n_cooldown", "n_mode", "param", "e_skip"),
        purpose="Say one gag line to every player (but e_skip), once per cooldown.",
    )
    can_say = CustomFunction(
        "zmf_gag_can_say",
        (
            "n_now = gettime();",
            "n_slot = n_now;",
            "if ( isdefined( self.zmf_gag_slot ) && self.zmf_gag_slot > n_slot )",
            "{",
            "\tn_slot = self.zmf_gag_slot;",
            "}",
            "if ( isdefined( level.zmf_gag_hush ) && level.zmf_gag_hush > n_slot )",
            "{",
            "\tn_slot = level.zmf_gag_hush;",
            "}",
            "if ( isdefined( self.zmf_gag_hush ) && self.zmf_gag_hush > n_slot )",
            "{",
            "\tn_slot = self.zmf_gag_hush;",
            "}",
            f"return n_slot - n_now <= {_ms(backlog)};",
        ),
        purpose="Would a centre-screen gag said now be shown (not dropped)?",
    )
    return CustomScript(
        using=(_EQUIPMENT,),
        functions=(say, say_all, can_say),
        notes=(f"gag sayer: {gap:g}s between centre lines, backlog {backlog:g}s",),
    )


def _say(target: str, gag: str, asset: str, mode: int, param: str | None = None,
         cooldown: float | None = None) -> str:
    wait = COOLDOWNS.get(gag, 0.0) if cooldown is None else cooldown
    args = [f'"{gag}"', _str(asset), str(_ms(wait)), str(mode)]
    if param is not None:
        args.append(param)
    return f"{target} thread zmf_gag_say( {', '.join(args)} );"


def _say_all(gag: str, asset: str, mode: int, param: str | None = None,
             skip: str | None = None, cooldown: float | None = None) -> str:
    wait = COOLDOWNS.get(gag, 0.0) if cooldown is None else cooldown
    args = [f'"{gag}"', _str(asset), str(_ms(wait)), str(mode),
            param if param is not None else "undefined"]
    if skip is not None:
        args.append(skip)
    return f"level thread zmf_gag_say_all( {', '.join(args)} );"


def _watcher(name: str, wait: str, body: Sequence[str], purpose: str) -> CustomFunction:
    return CustomFunction(
        name,
        (
            'self endon( "disconnect" );',
            'level endon( "end_game" );',
            "while ( true )",
            "{",
            f"\t{wait}",
            *(f"\t{line}" for line in body),
            "}",
        ),
        purpose=purpose,
    )


def player_reactions(
    *,
    downed: str | None = None,
    downed_feed: str | None = None,
    bled_out_feed: str | None = None,
    revived: str | None = None,
    revived_broke: str | None = None,
    reviver: str | None = None,
    fee: int = 25,
    perks: Mapping[str, str] = {},
    pap: str | None = None,
    hops: Mapping[str, tuple[str, str | None]] = {},
    rooms: Mapping[str, str] = {},
    idle: tuple[str, float, str] | None = None,
    poll: float = 0.5,
) -> CustomScript:
    """Per-player reactions: one watcher thread per event, on every player.

    Every argument is a ``string`` asset (or a mapping of them) and each one
    switches a watcher on:

    ``downed``/``downed_feed``  bold to the downed player; feed line to the
                                rest with the player as ``&&1``.
    ``bled_out_feed``           feed line to the rest when a player bleeds out.
    ``revived``                 bold to the revived player, **and the fee is
                                taken**: ``fee`` points through
                                ``zm_score::minus_to_player_score``
                                (``_zm_score.gsc:556``) when the player has
                                them, else ``revived_broke`` is said instead.
    ``reviver``                 feed line to whoever revived, ``&&1`` the
                                revived player.
    ``perks``                   specialty -> line, said on ``perk_bought``.
    ``pap``                     said on ``pap_taken``.
    ``hops``                    teleporter suffix -> ``(line, feed)``: said on
                                the hop's ``zmf_hopped<suffix>`` notify; the
                                feed (optional) goes to the rest.
    ``rooms``                   zone name -> sign-in line, said once per
                                player the first time the zone manager puts
                                them in it (polled every ``poll`` seconds).
    ``idle``                    ``(zone, seconds, line)``: HUD text to a player
                                who has stood still that long in that zone.

    **Unverified in play.**
    """
    functions: list[CustomFunction] = []
    threads: list[str] = []
    using: list[str] = []

    def add(fn: CustomFunction) -> None:
        functions.append(fn)
        threads.append(f"self thread {fn.name}();")

    if downed or downed_feed:
        body = []
        if downed:
            body.append(_say("self", "downed", downed, SAY_BOLD))
        if downed_feed:
            body.append(_say_all("downed_feed", downed_feed, SAY_FEED, "self", "self"))
        add(_watcher("zmf_gag_on_downed", 'self waittill( "player_downed" );', body,
                     'Downed.  self notify( "player_downed" ): _zm_laststand.gsc:270.'))
    if bled_out_feed:
        add(_watcher("zmf_gag_on_bled_out", 'self waittill( "bled_out" );',
                     [_say_all("bled_out_feed", bled_out_feed, SAY_FEED, "self", "self")],
                     'Bled out.  self notify("bled_out"): _zm_laststand.gsc:523, :580.'))
    if revived or reviver:
        body: list[str] = []
        if revived:
            using.append(_SCORE)
            broke = revived_broke or revived
            body += [
                f"if ( isdefined( self.score ) && self.score >= {int(fee)} )",
                "{",
                f"\tself zm_score::minus_to_player_score( {int(fee)} );",
                f"\t{_say('self', 'revived', revived, SAY_BOLD)}",
                "}",
                "else",
                "{",
                f"\t{_say('self', 'revived', broke, SAY_BOLD)}",
                "}",
            ]
        if reviver:
            body += [
                "if ( isdefined( e_reviver ) && isplayer( e_reviver ) && e_reviver != self )",
                "{",
                f"\t{_say('e_reviver', 'reviver', reviver, SAY_FEED, 'self')}",
                "}",
            ]
        add(_watcher("zmf_gag_on_revived", 'self waittill( "player_revived", e_reviver );',
                     body,
                     'Revived, and the reinstatement fee.  self notify ( "player_revived",\n'
                     "reviver ): _zm_laststand.gsc:1392, :1430; minus_to_player_score:\n"
                     "_zm_score.gsc:556."))
    if perks:
        body = []
        for n, (specialty, line) in enumerate(perks.items()):
            body += [
                f'{"if" if n == 0 else "else if"} ( str_perk == "{specialty}" )',
                "{",
                f"\t{_say('self', 'perk_' + str(n), line, SAY_BOLD, cooldown=COOLDOWNS['perk'])}",
                "}",
            ]
        add(_watcher("zmf_gag_on_perk", 'self waittill( "perk_bought", str_perk );', body,
                     'A perk of ours bought.  self notify( "perk_bought", perk ):\n'
                     "_zm_perks.gsc:747."))
    if pap:
        add(_watcher("zmf_gag_on_pap", 'self waittill( "pap_taken" );',
                     [_say("self", "pap", pap, SAY_BOLD)],
                     'Pack-a-Punch used.  player notify( "pap_taken" ):\n'
                     "_zm_pack_a_punch.gsc:637."))
    for suffix, (line, feed) in hops.items():
        tail = str(suffix)
        if not tail.replace("_", "").isalnum():
            raise ValueError(f"hop suffix {suffix!r} is pasted into a GSC name")
        body = [_say("self", f"hop{tail}", line, SAY_BOLD, cooldown=COOLDOWNS["hop"])]
        if feed:
            body.append(_say_all(f"hop{tail}_feed", feed, SAY_FEED, "self", "self",
                                 cooldown=COOLDOWNS["hop_feed"]))
        add(_watcher(f"zmf_gag_on_hop{tail}", f'self waittill( "zmf_hopped{tail}" );', body,
                     f"Say what the teleporter{tail} just did to you."))
    setup: list[str] = []
    if rooms or idle:
        using.append(_ZONEMGR)
        # The room table only when there are room lines: an idle-only map
        # (zm_dmv, P13) would otherwise poll an empty table for nothing.
        if rooms:
            setup.append("level.zmf_gag_rooms = [];")
            setup += [f'level.zmf_gag_rooms[ "{zone}" ] = {_str(line)};'
                      for zone, line in rooms.items()]
        loop = [
            'self endon( "disconnect" );',
            'level endon( "end_game" );',
            *(("self.zmf_gag_seen = [];",) if rooms else ()),
            "v_last = self.origin;",
            "n_still = 0;",
            "while ( true )",
            "{",
            f"\twait {float(poll):g};",
            "\tstr_zone = self zm_zonemgr::get_player_zone();",
            "\tif ( !isdefined( str_zone ) )",
            "\t{",
            "\t\tn_still = 0;",
            "\t\tcontinue;",
            "\t}",
        ]
        if rooms:
            # Marked seen only when the line will be said: a sign-in that
            # would be dropped (the centre queue past its backlog, or held
            # by a quest line / ticket call) waits for a later poll instead
            # of being lost for good.
            loop += [
                "\tif ( !isdefined( self.zmf_gag_seen[ str_zone ] ) && "
                "isdefined( level.zmf_gag_rooms[ str_zone ] ) && self zmf_gag_can_say() )",
                "\t{",
                "\t\tself.zmf_gag_seen[ str_zone ] = 1;",
                f'\t\tself thread zmf_gag_say( "room_" + str_zone, '
                f"level.zmf_gag_rooms[ str_zone ], 0, {SAY_BOLD} );",
                "\t}",
            ]
        if idle:
            zone, seconds, line = idle
            ticks = max(1, int(round(float(seconds) / float(poll))))
            loop += [
                f'\tif ( str_zone == "{zone}" && distancesquared( self.origin, v_last ) < 256 )',
                "\t{",
                "\t\tn_still++;",
                "\t}",
                "\telse",
                "\t{",
                "\t\tn_still = 0;",
                "\t}",
                "\tv_last = self.origin;",
                f"\tif ( n_still >= {ticks} )",
                "\t{",
                "\t\tn_still = 0;",
                f"\t\t{_say('self', 'idle', line, SAY_HINT)}",
                "\t}",
            ]
        loop.append("}")
        fn = CustomFunction(
            "zmf_gag_rooms",
            tuple(loop),
            purpose=(
                "Sign in: the first time the zone manager puts this player in a\n"
                "room, say that room's line.  get_player_zone: _zm_zonemgr.gsc:89."
            ),
        )
        add(fn)
    if not functions:
        raise ValueError("player_reactions needs at least one line to say")
    attach = CustomFunction(
        "zmf_gag_attach",
        (
            'level endon( "end_game" );',
            *setup,
            "players = getplayers();",
            "for ( i = 0; i < players.size; i++ )",
            "{",
            "\tplayers[ i ] thread zmf_gag_player();",
            "}",
            "while ( true )",
            "{",
            '\tlevel waittill( "connected", player );',
            "\tplayer thread zmf_gag_player();",
            "}",
        ),
        purpose=(
            "Every player's gag watchers, now and on join.\n"
            'level waittill( "connected", player ): _zm.gsc:482.'
        ),
    )
    player = CustomFunction(
        "zmf_gag_player",
        ('self endon( "disconnect" );', *threads),
        purpose="One player's gag watchers.",
    )
    return CustomScript(
        using=tuple(dict.fromkeys(using)),
        functions=(attach, player, *functions),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_gag_attach();"),),
        notes=(f"{len(functions)} gag watchers per player",),
    )


def box_reactions(*, used: str | None = None, moved: str | None = None) -> CustomScript:
    """The mystery box: ``used`` said bold to whoever paid for a spin (the
    framework's own ``level._magic_box_used_VO`` hook), ``moved`` said to
    everyone when the box flies away.  **Unverified in play.**"""
    functions: list[CustomFunction] = []
    statements: list[tuple[Slot, str]] = []
    if used:
        functions.append(CustomFunction(
            "zmf_gag_on_box",
            (_say("self", "box", used, SAY_BOLD),),
            purpose=(
                "The box was paid for; self is the player.\n"
                "user thread [[ level._magic_box_used_VO ]](): _zm_magicbox.gsc:655-657."
            ),
        ))
        statements.append((Slot.AFTER_ENTRY, "level._magic_box_used_VO = &zmf_gag_on_box;"))
    if moved:
        functions.append(CustomFunction(
            "zmf_gag_box_moved",
            (
                'level endon( "end_game" );',
                "while ( true )",
                "{",
                '\tlevel waittill( "weapon_fly_away_start" );',
                f"\t{_say_all('box_moved', moved, SAY_BOLD)}",
                "}",
            ),
            purpose='The box is moving.  level notify("weapon_fly_away_start"): _zm_magicbox.gsc:1750.',
        ))
        statements.append((Slot.AFTER_ENTRY, "level thread zmf_gag_box_moved();"))
    if not functions:
        raise ValueError("box_reactions needs used or moved")
    return CustomScript(functions=tuple(functions), statements=tuple(statements),
                        notes=("mystery box gag lines",))


def round_announcer(
    sequences: Sequence[Sequence[str]],
    *,
    pause: float = 2.5,
    delay: float = 2.0,
    every_rounds: int = 1,
) -> CustomScript:
    """The PA system, at round ends (``end_of_round``, ``_zm.gsc:4449``).

    Every ``every_rounds``-th round end reads one of ``sequences`` (lines
    bold to everyone, ``pause`` seconds apart), in turn.  The lines go
    through :func:`gag_say`, so they yield to quest lines and ticket calls.
    (The DMV's old "the PA calls your own ticket and you miss it" gag lived
    here; the real calls are :class:`zmforge.script.tricks.TicketCalls`.)
    **Unverified in play.**

    No sequences (or only empty ones) means no announcer: an empty
    :class:`CustomScript`, so a map that cut its PA flavour (P13, P17) can
    pass whatever is left without wiring around the helper.
    """
    if int(every_rounds) < 1:
        raise ValueError("every_rounds >= 1")
    sequences = [list(seq) for seq in (sequences or ()) if seq]
    if not sequences:
        return CustomScript()
    body = ['level endon( "end_game" );', "level.zmf_gag_pa = [];"]
    for n, seq in enumerate(sequences):
        body.append(f"level.zmf_gag_pa[ {n} ] = [];")
        body += [f"level.zmf_gag_pa[ {n} ][ {k} ] = {_str(line)};"
                 for k, line in enumerate(seq)]
    body += [
        "n_turn = 0;",
        "n_round = 0;",
        "while ( true )",
        "{",
        '\tlevel waittill( "end_of_round" );',
        "\tn_round++;",
        f"\tif ( n_round % {int(every_rounds)} != 0 )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        f"\twait {float(delay):g};",
        "\ta_seq = level.zmf_gag_pa[ n_turn ];",
        "\tfor ( i = 0; i < a_seq.size; i++ )",
        "\t{",
        f'\t\tlevel thread zmf_gag_say_all( "pa_" + i, a_seq[ i ], 0, {SAY_BOLD}, undefined );',
        f"\t\twait {float(pause):g};",
        "\t}",
        "\tn_turn = ( n_turn + 1 ) % level.zmf_gag_pa.size;",
        "}",
    ]
    return CustomScript(
        functions=(CustomFunction(
            "zmf_gag_announcer",
            tuple(body),
            purpose=(
                "The PA at round ends (_zm.gsc:4449), one announcement every\n"
                f"{int(every_rounds)} round(s)."
            ),
        ),),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_gag_announcer();"),),
        notes=(f"PA announcer: {len(sequences)} round-end announcements"
               + (f", every {int(every_rounds)} rounds" if int(every_rounds) > 1 else ""),),
    )


def random_announcements(lines: Sequence[str], *, every: tuple[int, int] = (75, 150)
                         ) -> CustomScript:
    """A PA line to everybody every ``every`` seconds (a random wait in the
    range), in turn, from the first round start on; level-wide cooldown
    :data:`COOLDOWNS` ``["pa_random"]``.  No lines means no thread (an
    empty :class:`CustomScript`).  **Unverified in play.**"""
    low, high = (int(v) for v in every)
    if not 0 < low <= high:
        raise ValueError(f"bad interval {every!r}")
    lines = [line for line in (lines or ()) if line]
    if not lines:
        return CustomScript()
    body = ['level endon( "end_game" );', "a_lines = [];"]
    body += [f"a_lines[ {n} ] = {_str(line)};" for n, line in enumerate(lines)]
    body += [
        'level waittill( "start_of_round" );',
        "n_line = randomint( a_lines.size );",
        "while ( true )",
        "{",
        f"\twait randomintrange( {low}, {high + 1} );",
        f'\tlevel thread zmf_gag_say_all( "pa_random", a_lines[ n_line ], '
        f"{_ms(COOLDOWNS['pa_random'])}, {SAY_BOLD}, undefined );",
        "\tn_line = ( n_line + 1 ) % a_lines.size;",
        "}",
    ]
    return CustomScript(
        functions=(CustomFunction(
            "zmf_gag_pa_random",
            tuple(body),
            purpose="Random PA announcements, one every minute or two.",
        ),),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_gag_pa_random();"),),
        notes=(f"{len(lines)} random PA lines",),
    )


def power_on_announcement(line: str | None) -> CustomScript:
    """Bold to everyone when the power comes on (``level flag::wait_till(
    "power_on" )``, as ``zm_castle.gsc:880`` waits for it).  No line means no
    thread (an empty :class:`CustomScript`).  **Unverified in play.**"""
    if not line:
        return CustomScript()
    return CustomScript(
        using=(_FLAG,),
        functions=(CustomFunction(
            "zmf_gag_power_on",
            (
                'level endon( "end_game" );',
                'level flag::wait_till( "power_on" );',
                _say_all("power", line, SAY_BOLD),
            ),
            purpose='The power is on: level flag::wait_till( "power_on" ).',
        ),),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_gag_power_on();"),),
        notes=("power-on gag line",),
    )
