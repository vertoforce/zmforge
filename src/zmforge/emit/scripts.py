"""The generated GSC server and client scripts.

Spec section 5.3 is the design constraint: **regenerate, never patch**.  The
reference implementation edited its script in place around textual anchors and
lost the file's line endings on every edit (item K10), so there is no editing
path here at all -- the whole file comes from the :class:`ScriptPlan`.

Statement order inside ``main`` is load-bearing, not cosmetic:
``level.dog_rounds_allowed`` must be assigned **before** the framework entry,
because the framework only applies its default when the variable is undefined
(spec 4.12, item E6).  Conformance check Z10 tests exactly that order.
"""

from __future__ import annotations

from ..blueprint import catalogue as fixed
from ..blueprint.script_plan import ScriptPlan
from ..script.custom import CustomFunction, Slot
from .weapons import STOCK_TABLE, TABLE_LOADER, WEAPONS_MODULE, load_call


def _owns_the_weapon_hook(plan: ScriptPlan) -> bool:
    """Whether this map has anything of its own to say about weapons.

    Its own table, its own prompt names, or both: all of it happens in the
    loader the map hangs off ``level._zombie_custom_add_weapons``, so one
    answer decides the ``#using``, the assignment and the function together.
    Renaming without re-pricing is a map that loads only Treyarch's table and
    then overwrites six hints, and that still needs the hook, because winning
    the hook is what puts our code after the load.
    """
    return bool(plan.weapon_table or plan.weapon_hints)

__all__ = [
    "render_server_script",
    "render_client_script",
    "FRAMEWORK_ENTRY",
    "SHARED_MODULES",
    "ZOMBIE_MODULES",
    "CLIENT_MODULES",
    "INSERTS",
]

#: The framework's namespace-qualified entry, called by both scripts.
FRAMEWORK_ENTRY = "zm_usermap::main"

#: Minimum ``#using`` set that compiled and played (spec 5.1 step 1).
SHARED_MODULES: tuple[str, ...] = (
    r"scripts\codescripts\struct",
    r"scripts\shared\callbacks_shared",
    r"scripts\shared\flag_shared",
    r"scripts\shared\util_shared",
)

ZOMBIE_MODULES: tuple[str, ...] = (
    r"scripts\zm\_load",
    r"scripts\zm\_zm",
    r"scripts\zm\_zm_zonemgr",
    r"scripts\zm\_zm_utility",
)

USERMAP_MODULE = r"scripts\zm\zm_usermap"

#: Der Wunderfizz's own module, named in both scripts when one is placed.
WUNDERFIZZ_MODULE = fixed.WUNDERFIZZ_MODULE

INSERTS: tuple[str, ...] = (
    r"scripts\shared\shared.gsh",
    r"scripts\shared\version.gsh",
    r"scripts\zm\_zm_utility.gsh",
)

CLIENT_MODULES: tuple[str, ...] = (
    r"scripts\codescripts\struct",
    r"scripts\shared\callbacks_shared",
    r"scripts\shared\clientfield_shared",
    r"scripts\shared\system_shared",
    r"scripts\shared\util_shared",
)

CLIENT_INSERTS: tuple[str, ...] = (
    r"scripts\shared\shared.gsh",
    r"scripts\shared\version.gsh",
)

#: ``clientfield::register`` lives here, and a map that seats more than four
#: players calls it: the stock per-player registrations are written out four
#: times and the rest are the map's to make.  Only added above four slots, so
#: a stock map emits exactly the ``#using`` set it always emitted.
CLIENTFIELD_MODULE = r"scripts\shared\clientfield_shared"

#: The namespace the client script's extra last-stand fields hand their
#: update callback back to (``&zm_laststand::update_bleedout_timer``,
#: ``_zm_laststand.csc:71``).
LASTSTAND_MODULE = r"scripts\zm\_zm_laststand"

#: The six per-player score fields ``_zm_score.gsc:28-33`` registers, as
#: ``(name, max_count)``.  ``score_cf_register_info`` loops them over
#: ``MAX_CLIENTS_ZM``, which ``_zm_utility.gsh:18`` defines as ``4``, so a
#: fifth player's ``score_cf_increment_info`` (``_zm_score.gsc:115``) names a
#: field nobody registered.  The community's lobby-size page warns that
#: unregistered per-player client fields are what crashes a bigger lobby.
SCORE_FIELDS: tuple[tuple[str, int], ...] = (
    ("damage", 7),
    ("death_normal", 3),
    ("death_torso", 3),
    ("death_neck", 3),
    ("death_head", 3),
    ("death_melee", 3),
)

#: How many of each per-player thing the stock scripts set up.
STOCK_SLOTS = 4

_TAB = "\t"

#: No perk limit on any generated map, ever.  There is no "off" value: the stock gate is the comparison
#: ``if ( self.num_perks < self zm_utility::get_player_perk_purchase_limit() )``
#: (``_zm_utility.gsc:5889``), so "unlimited" is a count no map's machines
#: reach.  Check Z82 holds the value and the wiring.
NO_PERK_LIMIT = 99
#: The level-specific override ``get_player_perk_purchase_limit`` calls
#: instead of reading ``level.perk_purchase_limit`` (``_zm_utility.gsc:5879-5882``).
PERK_LIMIT_HOOK = "zmf_perk_purchase_limit"


def _join(lines: list[str], newline: str) -> str:
    return newline.join(lines) + newline


def render_server_script(plan: ScriptPlan, *, newline: str = "\n") -> str:
    """The map's ``<map>.gsc`` (spec 5.1).

    ``newline`` is the ending the existing file had, so regenerating a file the
    original authors shipped with CRLF keeps CRLF (item K10, check F12).
    """
    lines: list[str] = []
    for module in SHARED_MODULES:
        lines.append(f"#using {module};")
    lines.append("")
    for insert in INSERTS:
        lines.append(f"#insert {insert};")
    lines.append("")
    for module in ZOMBIE_MODULES:
        lines.append(f"#using {module};")
    if _owns_the_weapon_hook(plan):
        lines.append(f"#using {WEAPONS_MODULE};")
    if plan.lift_player_cap:
        lines.append(f"#using {CLIENTFIELD_MODULE};")
    for module in plan.module_set():
        lines.append(f"#using {module};")
    if plan.wunderfizz:
        lines.append(f"#using {WUNDERFIZZ_MODULE};")
    # A caller's #using is written only if the scaffold does not already
    # write it: the shared and zombies modules above, the perk modules, and
    # the usermap module below.  The same line twice is what the seam's own
    # merge() dedupes between mechanics; this is the same rule against the
    # generated half of the file.
    emitted = {*SHARED_MODULES, *ZOMBIE_MODULES, *plan.module_set(), USERMAP_MODULE}
    if plan.wunderfizz:
        emitted.add(WUNDERFIZZ_MODULE)
    if _owns_the_weapon_hook(plan):
        emitted.add(WEAPONS_MODULE)
    if plan.lift_player_cap:
        emitted.add(CLIENTFIELD_MODULE)
    for module in plan.custom.using:
        if module not in emitted:
            lines.append(f"#using {module};")
            emitted.add(module)
    lines.append(f"#using {USERMAP_MODULE};")
    lines.append("")
    _precache(lines, plan, "fx")
    _precache_strings(lines, plan)
    _precache_perk_hints(lines, plan)
    _precache_map_strings(lines, plan)

    lines.append("function main()")
    lines.append("{")
    _slot(lines, plan, Slot.BEFORE_ENTRY)
    if _owns_the_weapon_hook(plan):
        # The same shape as the dog-round line below and for the same reason.
        # zm_usermap.gsc:135 installs the stock loader with
        # DEFAULT( level._zombie_custom_add_weapons, &custom_add_weapons ),
        # and DEFAULT only assigns while the variable is undefined, so a map
        # that assigns it here wins and _zm_weapons.gsc:676 calls this one.
        # After the entry would be too late, and it is not a slot a caller
        # can reach: check W4 holds the order.
        lines.append(
            f"{_TAB}// this map charges its own prices: load its weapon table "
            "instead of only Treyarch's (zm_usermap.gsc:135)"
        )
        lines.append(f"{_TAB}level._zombie_custom_add_weapons = &{TABLE_LOADER};")
    # Before the framework entry: the framework's own default only applies
    # while the variable is undefined, so afterwards is too late.  Nothing a
    # caller supplies can land between these two lines; see Slot.
    lines.append(f"{_TAB}level.dog_rounds_allowed = {1 if plan.dog_rounds else 0};")
    if plan.lift_player_cap:
        _extra_seats_register(lines, plan)
    lines.append(f"{_TAB}{FRAMEWORK_ENTRY}();")
    if plan.lift_player_cap:
        # After the entry, deliberately: zm::init() assigns this true at
        # _zm.gsc:252 and onPlayerSpawned reads it at _zm.gsc:1865, so this
        # is the window.  Left alone, the fifth player to spawn freezes
        # everyone and ends the game (_zm.gsc:7067).  Before the caller's
        # AFTER_ENTRY statements, so a map's own logic cannot be what
        # decides whether the cap came off.  Check Z26 holds the pair.
        lines.append(
            f"{_TAB}// more than four spawn slots: stop the framework ending "
            "the game on the fifth player (_zm.gsc:7067, 1865)"
        )
        lines.append(f"{_TAB}level.player_too_many_players_check = false;")
        _extra_seats_server(lines, plan)
    if plan.wunderfizz:
        # After the framework entry: the wunderfizz setup page says to add
        # one line per fizz perk under the ``zm_usermap::main();`` call
        # (the published "Setting up the Der Wunderfizz" page).
        # Nothing reads the list until a player uses the machine --
        # ``get_weighted_random_perk`` (_zm_perk_random.gsc:627) is called
        # from the use trigger -- so this only has to run once, before the
        # first use.  Before the caller's own AFTER_ENTRY statements, so a
        # map's custom logic is never what decides whether the machine has
        # anything to give.  Check Z49 holds the pair.
        rotation = plan.rotation()
        lines.append(
            f"{_TAB}// Der Wunderfizz: what it may hand out "
            f"({len(rotation)} perk{'' if len(rotation) == 1 else 's'})"
        )
        for specialty in rotation:
            lines.append(
                f"{_TAB}zm_perk_random::include_perk_in_random_rotation"
                f'( "{specialty}" );'
            )
    # No perk limit, on every map.  After the framework
    # entry, deliberately: zm_usermap::main (zm_usermap.gsc:144) runs
    # load::main -> zm::init (_load.gsc:79) -> zm_perks::init (_zm.gsc:362),
    # which assigns level.perk_purchase_limit = 4 (_zm_perks.gsc:43), so the
    # same assignment before the entry would be reset.  The pointer is read at
    # purchase time (_zm_utility.gsc:5874-5889) and so cannot lose that race
    # at all.  Before the caller's AFTER_ENTRY statements, so no recipe decides
    # it.  Check Z82 holds the pair.
    lines.append(
        f"{_TAB}// no perk limit: stock is 4 (_zm_perks.gsc:43), "
        "raised after zm_usermap::main set it"
    )
    lines.append(f"{_TAB}level.perk_purchase_limit = {NO_PERK_LIMIT};")
    lines.append(
        f"{_TAB}level.get_player_perk_purchase_limit = &{PERK_LIMIT_HOOK};"
    )
    _slot(lines, plan, Slot.AFTER_ENTRY)
    if plan.repeat_game_mode:
        lines.append(f'{_TAB}level.default_game_mode = "zclassic";')
    if plan.chest_name:
        lines.append(f'{_TAB}level.start_chest_name = "{plan.chest_name}";')
        lines.append(f"{_TAB}level.enable_magic = true;")
    lines.append(f"{_TAB}level.zone_manager_init_func = &{plan.zone_hook};")
    lines.append(f"{_TAB}init_zones = [];")
    # Only the zones open at load (G1): a door-gated zone in this
    # list is enabled at load by manage_zones (_zm_zonemgr.gsc:841-844) and
    # every zone gate on it passes at once.  Check Z67 reads this list back.
    for index, zone in enumerate(_initial_zones(plan)):
        lines.append(f'{_TAB}init_zones[{index}] = "{zone}";')
    lines.append(f"{_TAB}level thread zm_zonemgr::manage_zones( init_zones );")
    lines.append("}")
    lines.append("")

    lines.append(f"function {plan.zone_hook}()")
    lines.append("{")
    # The always-on flag is initialised and set *before* the adjacency calls,
    # which is the order the mod tools' own template and every shipped zone
    # hook use (``rex/templates/ZM Mod Level/.../template.gsc:74-78``;
    # ``zm_castle_zones.gsc:22-29``, ``zm_tomb.gsc:1545-1550``,
    # ``zm_theater.gsc:610-612``, ``zm_stalingrad_zones.gsc:24-67``,
    # ``zm_island_zones.gsc:63``, ``zm_genesis_zones.gsc:84-87``).  It is not
    # cosmetic: ``add_adjacent_zone`` calls ``flag::init`` itself for a flag
    # nothing has defined yet (``_zm_zonemgr.gsc:595-612``) and ``flag::init``
    # writes the flag back to 0 and asserts on a re-init in a dev build
    # (``flag_shared.gsc:17-30``), so a caller whose door flag *is* the
    # always-on flag would get that flag initialised twice in the other
    # order.  Check Z3 holds the order.
    lines.append(f'{_TAB}level flag::init( "{plan.always_on_flag}" );')
    lines.append(f'{_TAB}level flag::set( "{plan.always_on_flag}" );')
    for edge in plan.edges:
        lines.append(
            f'{_TAB}zm_zonemgr::add_adjacent_zone( "{edge.zone_a}", '
            f'"{edge.zone_b}", "{edge.flag}" );'
        )
    _slot(lines, plan, Slot.ZONE_HOOK)
    lines.append("}")
    if _owns_the_weapon_hook(plan):
        lines.append("")
        lines.append(
            "// Winning the hook means the stock table is not loaded by anyone "
            "else,"
        )
        if plan.weapon_table:
            lines.append(
                "// so load it first and this map's own second: add_zombie_weapon "
                "keys"
            )
            lines.append(
                "// level.zombie_weapons by weapon, so the second load replaces a "
                "row"
            )
            lines.append("// rather than adding a duplicate (_zm_weapons.gsc:600).")
        else:
            lines.append(
                "// so this map loads it itself and changes nothing about it: "
                "what it"
            )
            lines.append(
                "// wants is the moment afterwards, which is the only place a "
                "hint can"
            )
            lines.append("// be overwritten (_zm_weapons.gsc:559-566, :969).")
        lines.append(f"function {TABLE_LOADER}()")
        lines.append("{")
        lines.append(f"{_TAB}{load_call(STOCK_TABLE)}")
        if plan.weapon_table:
            lines.append(f"{_TAB}{load_call(plan.weapon_table)}")
        _weapon_hints(lines, plan)
        lines.append("}")
    lines.append("")
    lines.append(
        "// Perks a player may hold at once: more than any map has machines, "
        "so no limit"
    )
    lines.append(
        "// (the override get_player_perk_purchase_limit calls, "
        "_zm_utility.gsc:5879-5882)."
    )
    lines.append(f"function {PERK_LIMIT_HOOK}()")
    lines.append("{")
    lines.append(f"{_TAB}return {NO_PERK_LIMIT};")
    lines.append("}")
    _append_functions(lines, _referenced(plan.custom.server_functions(), lines))
    return _join(lines, newline)


def _initial_zones(plan: ScriptPlan) -> list[str]:
    """``plan.zones`` cut to the zones open at load (starting zone first)."""
    from ..script.zonegate import initial_zones

    zones = list(plan.zones)
    return initial_zones(
        zones, zones[0] if zones else None,
        [(e.zone_a, e.zone_b, e.flag) for e in plan.edges], plan.always_on_flag,
    )


def render_client_script(plan: ScriptPlan, *, newline: str = "\n") -> str:
    """The map's ``<map>.csc`` (spec 5.2).

    ``main`` must call the framework's client entry or the server and client
    disagree about registered client fields and the game disconnects on join
    (item E11, check Z13).
    """
    lines: list[str] = []
    for module in CLIENT_MODULES:
        lines.append(f"#using {module};")
    lines.append("")
    for insert in CLIENT_INSERTS:
        lines.append(f"#insert {insert};")
    lines.append("")
    if plan.weapon_table:
        lines.append(f"#using {WEAPONS_MODULE};")
    if plan.lift_player_cap:
        lines.append(f"#using {LASTSTAND_MODULE};")
    # The same perk modules the server script carries, and from the same
    # list: each perk ships a client half as well, and the client half is
    # what registers the perk's clientfields, its HUD callbacks and its
    # machine effect (``_zm_perk_juggernaut.csc:20-30`` is a REGISTER_SYSTEM
    # calling ``zm_perks::register_perk_clientfields`` and
    # ``register_perk_effects``).  Treyarch's own map lists every perk module
    # in both scripts -- ``zm_giant.gsc:30-38`` against ``zm_giant.csc:21-28``
    # -- and each of those modules has a ``.csc`` beside its ``.gsc`` in the
    # mod tools' raw scripts.  Check Z9 holds the two lists equal.
    for module in plan.module_set():
        lines.append(f"#using {module};")
    # Der Wunderfizz is two halves for the same reason a perk is.  Its
    # ``.csc`` is the one that registers every clientfield the ``.gsc``
    # sets -- the machine's lights, its rock emissive, its bottle cycle --
    # and precaches the four effects it plays
    # (``_zm_perk_random.csc:19-22`` and ``:33-41``).  Without it the
    # server sets fields nothing is listening for.
    if plan.wunderfizz:
        lines.append(f"#using {WUNDERFIZZ_MODULE};")
    emitted = {*CLIENT_MODULES, *plan.module_set(), USERMAP_MODULE}
    if plan.wunderfizz:
        emitted.add(WUNDERFIZZ_MODULE)
    if plan.weapon_table:
        emitted.add(WEAPONS_MODULE)
    if plan.lift_player_cap:
        emitted.add(LASTSTAND_MODULE)
    for module in plan.custom.client_using:
        if module not in emitted:
            lines.append(f"#using {module};")
            emitted.add(module)
    lines.append(f"#using {USERMAP_MODULE};")
    lines.append("")
    _precache(lines, plan, "client_fx")
    lines.append(f'REGISTER_SYSTEM( "{plan.map_name}", &__init__, undefined )')
    lines.append("")
    lines.append("function __init__()")
    lines.append("{")
    lines.append(f"{_TAB}callback::on_localplayer_spawned( &on_player_spawned );")
    _slot(lines, plan, Slot.CLIENT_INIT)
    lines.append("}")
    lines.append("")
    lines.append("function main()")
    lines.append("{")
    if plan.lift_player_cap:
        _extra_seats_register(lines, plan, client=True)
    lines.append(f"{_TAB}{FRAMEWORK_ENTRY}();")
    _extra_seats_client(lines, plan)
    if plan.weapon_table:
        # After the entry, and it has to be: the number on the purchase
        # prompt is filled in client side, the client has no hook to win --
        # zm_usermap.csc:83 calls include_weapons() directly, which loads the
        # stock table at :95 -- so the map's overlay goes on top afterwards.
        # Without this line the player is charged the map's price and shown
        # Treyarch's.  Check W4.
        lines.append(
            f"{_TAB}// the prompt's number is client side and has no hook: "
            "reload the map's"
        )
        lines.append(
            f"{_TAB}// own table over the stock one zm_usermap.csc:95 just "
            "loaded"
        )
        lines.append(f"{_TAB}{load_call(plan.weapon_table)}")
    lines.append("}")
    lines.append("")
    lines.append("function on_player_spawned( localClientNum )")
    lines.append("{")
    lines.append("}")
    _append_functions(lines, plan.custom.client_functions())
    return _join(lines, newline)


def _extra_seats_register(
    lines: list[str], plan: ScriptPlan, *, client: bool = False
) -> None:
    """Register seats 5+ **before** the framework entry, because afterwards is
    too late.

    This is the half that has to be here, and it is here because of a crash
    rather than because of a reading.  ``zm_dmv``, generated with eight seats,
    linked clean (exit 2000, no error lines), installed, and the game refused
    the map at load with::

        Attempt to register ClientField laststand_update4 post finalization
        of ClientField registration period failed

    (measured on Windows).  ``laststand_update4`` is emitted by nothing but
    this pair of functions.

    **Why after the entry is after the window.**  The engine closes
    registration in ``CodeCallback_FinalizeInitialization``, which
    ``callbacks_shared.gsc:539-546`` documents as the engine's last
    initialisation step -- and the framework entry *yields* before it
    returns: ``zm_usermap::main()`` calls ``load::main()``
    (``zm/_load.gsc:77``), which waits at ``system::wait_till( "all" )``
    (``:105``) on the ``system_init_complete`` flag
    (``system_shared.gsc:150-156``).  So a statement written after
    ``zm_usermap::main();`` runs on the far side of that wait, with the
    period already shut.  Everything the framework itself registers -- the
    stock ``laststand_update0..3`` at ``_zm_laststand.gsc:52-56``, and the
    custom-perk fields at ``_zm_perks.gsc:1631-1643`` -- is registered inside
    that window, not after it.

    **What stays behind.**  Only the registration moves.  The level arrays
    these names live in (``level.laststand_update_clientfields``,
    ``level.player_name_directive``, ``level.laststands``) are assigned inside
    the entry (``_zm_laststand.gsc:52``, ``:91``, ``.csc:19``), so writing
    them early would be writing them into an array the entry then replaces:
    that bookkeeping stays after the entry in :func:`_extra_seats_server` and
    :func:`_extra_seats_client`, with no ``clientfield::register`` left in
    either.

    **Both sides move together**, which is the property that matters more
    than either side's position: the two halves have to agree about which
    fields exist or a joining client is disconnected.  Before the entry on the
    server and before the entry on the client leaves our seats registered
    ahead of the stock four on *both* sides, which is the same relative order
    the old code had behind them.

    **The score fields have a client half too.**  The build with the
    registrations moved above the entry loaded past that crash and was then
    disconnected in a solo game: "Server Disconnected - Clientfield Mismatch"
    (measured on Windows).  The server registered six ``clientuimodel``
    score fields per extra seat and the client registered none.  Stock gets
    away with a server-only loop because its client half is the LUI file
    ``ui/uieditor/clientfieldmodels.lua``, whose loop over
    ``PlayerList.client<i>.score_cf_*`` stops at a hard-coded four (read in
    the T7LuaRepo PC ship dump, lines 84-91; bits 3 for damage and 2 for the
    rest, matching ``GetMinBitCountForNum`` of 7 and 3).  A usermap cannot
    ship Lua (Z27), but a ``.csc`` can register a ``clientuimodel`` field --
    ``_zm_perk_juggernaut.csc:42`` and ``zm/_load.csc:132`` do -- so the
    client half of seats 5+ is registered here, with the flags
    ``_load.csc:132`` gives its own counter.  Check Z52 compares the two
    scripts' registration lists.

    **Unverified.**  Nothing here has been played since the change; what is
    measured is the crash and the disconnect it is written against and the
    lines above.
    """
    slots = max(plan.player_slots, STOCK_SLOTS)
    if slots <= STOCK_SLOTS:
        return
    side = "client" if client else "server"
    lines.append(
        f"{_TAB}// seats {STOCK_SLOTS + 1}-{slots}, {side} half: their client "
        "fields, registered"
    )
    lines.append(
        f"{_TAB}// before the framework entry because the entry yields "
        "(zm_usermap::main ->"
    )
    lines.append(
        f'{_TAB}// load::main, zm/_load.gsc:105 system::wait_till( "all" )) and the '
        "engine"
    )
    lines.append(
        f"{_TAB}// closes the registration period while it waits "
        "(callbacks_shared.gsc:539-546)."
    )
    lines.append(
        f"{_TAB}// Measured: registering these after the entry crashed the map "
        "at load with"
    )
    lines.append(
        f'{_TAB}// "register ClientField laststand_update{STOCK_SLOTS} post '
        'finalization ... failed".'
    )
    lines.append(
        f"{_TAB}// The arrays these names go into are written after the entry, "
        "where they exist."
    )
    if client:
        lines.append(f"{_TAB}zmf_bigger_lobby_mod = false;")
        lines.append(f"{_TAB}if ( isdefined( level.laststands ) )")
        lines.append(f"{_TAB}{{")
        lines.append(
            f"{_TAB}{_TAB}zmf_bigger_lobby_mod = isdefined( "
            f"level.laststands[ {STOCK_SLOTS} ] );"
        )
        lines.append(f"{_TAB}}}")
    else:
        lines.append(f"{_TAB}zmf_bigger_lobby_mod = false;")
        lines.append(
            f"{_TAB}if ( isdefined( level.laststand_update_clientfields ) )"
        )
        lines.append(f"{_TAB}{{")
        lines.append(
            f"{_TAB}{_TAB}zmf_bigger_lobby_mod = isdefined( "
            f"level.laststand_update_clientfields[ {STOCK_SLOTS} ] );"
        )
        lines.append(f"{_TAB}}}")
    lines.append(
        f"{_TAB}// a bigger-lobby mod that got here first registered these "
        "itself, and a"
    )
    lines.append(
        f"{_TAB}// second registration of one field is not ours to risk."
    )
    lines.append(f"{_TAB}if ( !zmf_bigger_lobby_mod )")
    lines.append(f"{_TAB}{{")
    lines.append(f"{_TAB}{_TAB}for ( i = {STOCK_SLOTS}; i < {slots}; i++ )")
    lines.append(f"{_TAB}{_TAB}{{")
    if client:
        lines.append(
            f'{_TAB}{_TAB}{_TAB}clientfield::register( "world", '
            '"laststand_update" + i, VERSION_SHIP, 5, "counter", '
            "&zm_laststand::update_bleedout_timer, !CF_HOST_ONLY, "
            "!CF_CALLBACK_ZERO_ON_NEW_ENT );"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// and the client half of the six score "
            "fields the server registers"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// for these seats.  The stock client half "
            "is the LUI model file,"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// whose loop stops at four seats, so without "
            "these the server has"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// fields the client lacks and the game "
            'disconnects: "Clientfield Mismatch".'
        )
        for name, max_count in SCORE_FIELDS:
            lines.append(
                f'{_TAB}{_TAB}{_TAB}clientfield::register( "clientuimodel", '
                f'"PlayerList.client" + i + ".score_cf_{name}", VERSION_SHIP, '
                f'GetMinBitCountForNum( {max_count} ), "counter", undefined, '
                "!CF_HOST_ONLY, !CF_CALLBACK_ZERO_ON_NEW_ENT );"
            )
    else:
        lines.append(
            f'{_TAB}{_TAB}{_TAB}clientfield::register( "world", '
            '"laststand_update" + i, VERSION_SHIP, 5, "counter" );'
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// and the six score fields "
            "_zm_score.gsc:28-33 registers per player,"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// which loop over MAX_CLIENTS_ZM "
            "(_zm_utility.gsh:18, 4).  The client"
        )
        lines.append(
            f"{_TAB}{_TAB}{_TAB}// script registers the same six for the "
            "same seats (check Z52)."
        )
        for name, max_count in SCORE_FIELDS:
            lines.append(
                f'{_TAB}{_TAB}{_TAB}clientfield::register( "clientuimodel", '
                f'"PlayerList.client" + i + ".score_cf_{name}", VERSION_SHIP, '
                f'GetMinBitCountForNum( {max_count} ), "counter" );'
            )
    lines.append(f"{_TAB}{_TAB}}}")
    lines.append(f"{_TAB}}}")


def _extra_seats_server(lines: list[str], plan: ScriptPlan) -> None:
    """Fill in the per-player state the stock scripts stop at four of.

    The **arrays** only.  Their client fields are registered before the
    framework entry (:func:`_extra_seats_register`) because the engine shuts
    the registration period while the entry is waiting; what is left here is
    the bookkeeping, and it is written after the entry because it has to be:
    ``_zm_laststand.gsc:52`` assigns ``level.laststand_update_clientfields =
    []`` and ``:91`` assigns ``level.player_name_directive = []`` inside the
    system init the entry runs, so anything written before the entry is
    thrown away.  Appending afterwards extends arrays that already exist.

    Nothing here touches a core script.  Both arrays are ``level`` fields, so
    the extension is the map's own script, which is the whole reason a usermap
    can do this at all.  A usermap could not take the tutorials' route even if
    it wanted to: ``scripts/zm/_zm_laststand.gsc`` is a ``zm_patch`` asset and
    ``zm_level.class:12`` carries ``ignore,zm_patch``, so a zone line for it
    is dropped at link time (measured on the install).

    **Under a bigger-lobby mod.**  Every write is guarded per slot, so a mod
    that seats six and a map that wants eight still add up.
    """
    slots = max(plan.player_slots, STOCK_SLOTS)
    if slots <= STOCK_SLOTS:
        return
    lines.append(
        f"{_TAB}// seats {STOCK_SLOTS + 1}-{slots}: the arrays behind the "
        "fields registered above."
    )
    lines.append(
        f"{_TAB}// _zm_laststand.gsc:52-56 and :91-95 stop at four and "
        "_zm_laststand.gsc:263"
    )
    lines.append(
        f"{_TAB}// addresses them by GetEntityNumber(), so a fifth player "
        "going down names a"
    )
    lines.append(f"{_TAB}// client field nobody registered.")
    lines.append(
        f"{_TAB}// After the entry because the entry assigns both arrays "
        "empty; no client"
    )
    lines.append(
        f"{_TAB}// field is registered here, the registration period is "
        "shut by now."
    )
    lines.append(f"{_TAB}for ( i = {STOCK_SLOTS}; i < {slots}; i++ )")
    lines.append(f"{_TAB}{{")
    lines.append(
        f"{_TAB}{_TAB}// guarded, because a bigger-lobby mod may already own "
        "this seat"
    )
    lines.append(
        f"{_TAB}{_TAB}if ( !isdefined( level.laststand_update_clientfields"
        "[ i ] ) )"
    )
    lines.append(f"{_TAB}{_TAB}{{")
    lines.append(
        f'{_TAB}{_TAB}{_TAB}level.laststand_update_clientfields[ i ] = '
        '"laststand_update" + i;'
    )
    lines.append(f"{_TAB}{_TAB}}}")
    lines.append(
        f"{_TAB}{_TAB}if ( !isdefined( level.player_name_directive[ i ] ) )"
    )
    lines.append(f"{_TAB}{_TAB}{{")
    lines.append(
        f"{_TAB}{_TAB}{_TAB}level.player_name_directive[ i ] = "
        f"level.player_name_directive[ i % {STOCK_SLOTS} ];"
    )
    lines.append(f"{_TAB}{_TAB}}}")
    lines.append(f"{_TAB}}}")


def _extra_seats_client(lines: list[str], plan: ScriptPlan) -> None:
    """The client half's bookkeeping: the last-stand structs, not the fields.

    The fields themselves are registered before the framework entry
    (:func:`_extra_seats_register`), the same as the server's, because the
    engine closes the registration period while the entry waits.  What is
    left here is ``level.laststands``, which the entry itself creates --
    ``_zm_laststand.csc:19`` assigns ``level.laststands = []`` from a
    ``REGISTER_SYSTEM`` init -- so it is filled in afterwards or not at all.
    """
    slots = max(plan.player_slots, STOCK_SLOTS)
    if slots <= STOCK_SLOTS:
        return
    lines.append(
        f"{_TAB}// seats {STOCK_SLOTS + 1}-{slots}: the structs the client "
        "half reads the fields"
    )
    lines.append(
        f"{_TAB}// registered above through (_zm_laststand.csc:19-27).  After "
        "the entry"
    )
    lines.append(
        f"{_TAB}// because the entry assigns level.laststands empty; no "
        "registration here."
    )
    lines.append(f"{_TAB}for ( i = {STOCK_SLOTS}; i < {slots}; i++ )")
    lines.append(f"{_TAB}{{")
    lines.append(
        f"{_TAB}{_TAB}// the same guard the server half carries, and it has "
        "to be the same:"
    )
    lines.append(
        f"{_TAB}{_TAB}// the two sides must agree about which fields exist"
    )
    lines.append(f"{_TAB}{_TAB}if ( isdefined( level.laststands[ i ] ) )")
    lines.append(f"{_TAB}{_TAB}{{")
    lines.append(f"{_TAB}{_TAB}{_TAB}continue;")
    lines.append(f"{_TAB}{_TAB}}}")
    lines.append(f"{_TAB}{_TAB}level.laststands[ i ] = SpawnStruct();")
    lines.append(f"{_TAB}{_TAB}level.laststands[ i ].bleedoutTime = 0;")
    lines.append(f"{_TAB}{_TAB}level.laststands[ i ].lastBleedoutTime = 0;")
    lines.append(
        f"{_TAB}{_TAB}level.laststands[ i ].laststand_update_clientfields = "
        '"laststand_update" + i;'
    )
    lines.append(f"{_TAB}}}")


def _precache(lines: list[str], plan: ScriptPlan, kind: str) -> None:
    """The map's own effects, registered by name, after the last ``#using``.

    An ``fx`` line in the manifest packs the effect into the fastfile and
    nothing else: ``level._effect[...] = "<path>"`` hands the game a name it
    has no handle for unless the file precached it, and a prefab that plays
    an unprecached effect renders nothing and says nothing.  The two scripts
    spell the same directive differently -- ``fx`` on the server,
    ``client_fx`` on the client -- which is the half the community's own
    install steps say is forgotten most (traps page, and
    ``zm_giant_fx.csc:9-28``).  Position is the mod tools' own: below the
    last ``#using``, above the first function.
    """
    names = [name for name in dict.fromkeys(plan.precache_fx) if name]
    if not names:
        return
    for name in names:
        lines.append(f'#precache( "{kind}", "{name}" );')
    lines.append("")


def _precache_strings(lines: list[str], plan: ScriptPlan) -> None:
    """The map's own prompt strings, registered by name, with the effects.

    The same rule an effect lives under: the ``localize`` line in the
    manifest packs the string into the English fastfile, and the handle a
    script may hand the engine comes from the ``#precache`` directive.  The
    kind is ``triggerstring``, which is what community scripts spell for a
    string a use prompt shows -- ``#precache( "triggerstring",
    "ZM_ABBEY_TELEPORTER_ACTIVATE" );`` in ``ohm-nabar/zm_building``'s
    ``scripts/zm/zm_abbey_teleporter.gsc:29``.  Server script only: the hint
    is assigned on ``level.zombie_weapons``, which is the server's, and the
    client half of a wall buy reads the cost and not the text.
    """
    names = [name for _, name in plan.weapon_hints if name]
    if not names:
        return
    for name in dict.fromkeys(names):
        lines.append(f'#precache( "triggerstring", "{name}" );')
    lines.append("")


def _precache_map_strings(lines: list[str], plan: ScriptPlan) -> None:
    """The map's own words a custom script shows: a prompt on a trigger it
    spawned (``triggerstring``, as for a wall buy's hint) or a line it prints
    (``string``, as a perk module precaches its own).  Server script only."""
    pairs = list(dict.fromkeys(plan.map_strings))
    if not pairs:
        return
    for kind, name in pairs:
        lines.append(f'#precache( "{kind}", "{name}" );')
    lines.append("")


def _precache_perk_hints(lines: list[str], plan: ScriptPlan) -> None:
    """A custom perk's buy prompt, registered the way a perk module does it.

    ``triggerstring`` is what a script spells for a prompt it sets on a
    trigger of its own; a perk does not set its own -- it hands the reference
    to ``zm_perks::register_perk_basic_info`` and the framework calls
    ``SetHintString`` with it -- and every stock perk module precaches its
    hint as ``string`` (``_zm_perk_juggernaut.gsc:29``,
    ``_zm_perk_widows_wine.gsc:30``).  Server script only: the prompt is set
    on the use trigger, which is the server's.
    """
    names = [name for name in dict.fromkeys(plan.perk_hints) if name]
    if not names:
        return
    for name in names:
        lines.append(f'#precache( "string", "{name}" );')
    lines.append("")


def _weapon_hints(lines: list[str], plan: ScriptPlan) -> None:
    """Say this map's own name on a wall buy, one assignment per weapon.

    Position is the whole trick.  ``add_zombie_weapon`` has just run for
    every row of every table loaded above and written
    ``&"ZOMBIE_WEAPONCOSTONLYFILL"`` over the ``hint`` column
    (``_zm_weapons.gsc:559-566``), so anything earlier is overwritten; the
    unitrigger stubs have not been built yet, and they take their text from
    ``get_weapon_hint()`` when they are (``_zm_weapons.gsc:969``, and again
    on every ``reset_wallbuy_internal`` at ``:1305``), so anything later is
    read too late by a buy already standing on the wall.

    The weapon icon stays Treyarch's: the stub's ``cursor_hint`` is still
    ``HINT_WEAPON``.  Only the line of text is ours, and the cost is still
    the engine's own ``&&1`` parameter.
    """
    if not plan.weapon_hints:
        return
    lines.append(
        f"{_TAB}// this map calls these guns something of its own: overwrite the "
        "framework's"
    )
    lines.append(
        f"{_TAB}// own hint now the tables are loaded and before the wall buys "
        "are built"
    )
    lines.append(f"{_TAB}// (_zm_weapons.gsc:559-566 writes it, :969 reads it)")
    for weapon, asset in plan.weapon_hints:
        lines.append(
            f'{_TAB}level.zombie_weapons[ GetWeapon( "{weapon}" ) ].hint = '
            f'&"{asset}";'
        )


def _slot(lines: list[str], plan: ScriptPlan, slot: Slot) -> None:
    """Write a caller's statements at one slot position.

    Statements are written verbatim and indented one tab.  They are never
    parsed or rewritten here: the checker in :mod:`zmforge.script.gsc` reads
    the finished file, which is the text the compiler will read.
    """
    for statement in plan.custom.in_slot(slot):
        lines.append(f"{_TAB}{statement}")


def _referenced(functions, scaffold: list[str]):
    """``functions`` less those nothing calls.

    A mechanic ships its helpers whole, and some go unused on a given map
    (a test map carried six helpers no line called).  A
    function is kept when its name appears as a word in the scaffold above
    (the slot statements) or in the body of another kept function, which
    covers ``thread f()``, ``f()`` and ``&f`` alike; the pass repeats until
    nothing more drops, so a helper only a dropped helper called goes too."""
    import re

    kept = list(functions)
    head = "\n".join(scaffold)
    while True:
        bodies = {f.name: "\n".join(f.body) for f in kept}
        drop = [
            f for f in kept
            if not re.search(rf"\b{re.escape(f.name)}\b", head)
            and not any(re.search(rf"\b{re.escape(f.name)}\b", text)
                        for name, text in bodies.items() if name != f.name)
        ]
        if not drop:
            return kept
        gone = {f.name for f in drop}
        kept = [f for f in kept if f.name not in gone]


def _append_functions(lines: list[str], functions) -> None:
    """Custom functions, after everything the engine generates.

    Appending rather than interleaving is what keeps the two halves of the
    file from corrupting each other: a regeneration rewrites the scaffolding
    above and re-emits these below, and neither half has to find the other.
    """
    for function in functions:
        lines.append("")
        if function.purpose:
            for line in function.purpose.splitlines():
                lines.append(f"// {line}")
        lines.append(function.signature)
        lines.append("{")
        for statement in function.body:
            lines.append(f"{_TAB}{statement}" if statement.strip() else "")
        lines.append("}")
