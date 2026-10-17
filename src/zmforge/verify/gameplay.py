"""Gameplay guards over the *generated* script.

Some bugs live only in what the emitter wrote, where the blueprint checks
cannot see them: every zone in ``init_zones`` (so every door-gated wait
passes at load), a fire handler that pays before it knows it has done
anything, a grenade watched with the wrong notify.  So a check reads the
generated text, not the model that was meant to produce it, and every check here takes the
server script (and the map's ``.str`` text) and nothing else.

Z67  init_zones lists only zones open at load (no door-gated zone).
Z68  a handler threaded from a fire watcher that pays points has a cooldown
     and pays after its last early return (it pays only for success).
Z69  a watcher keyed to a thrown weapon waits on ``grenade_fire``.
Z70  ``zombie_spawn_delay`` is restored through the stock getter, never from
     a value saved before a spike.
Z71  a script that moves a player after a wait checks last stand first.
Z72  every ``*_PROMPT`` string names the use key ``[{+activate}]``.
Z73  every boss spawned from a ``zmf_boss_*_spawn`` is guarded against a
     one-shot Insta-Kill.
Z79  at most :data:`FLAVOUR_BROADCAST_LIMIT` flavour broadcasts: lines the gag
     helpers print on entering a zone, at a round end or on a random timer
     (P13, P17).  Replies to a player's own action (downed, a perk, the box,
     the power switch, standing still) and quest lines do not count.
Z82  no perk limit: after ``zm_usermap::main();`` the map
     assigns ``level.perk_purchase_limit`` and the purchase-time pointer
     ``level.get_player_perk_purchase_limit``, both to at least
     :data:`~zmforge.emit.scripts.NO_PERK_LIMIT`, and nothing else sets either.
"""

from __future__ import annotations

import re

from ..emit.scripts import FRAMEWORK_ENTRY, NO_PERK_LIMIT, PERK_LIMIT_HOOK
from ..script.tricks import GRENADE_WEAPON
from ..script.zonegate import open_at_start
from .report import Report, error, warning

__all__ = ["FLAVOUR_BROADCAST_LIMIT", "check_gameplay_script", "check_perk_limit",
           "check_prompt_strings", "flavour_broadcasts"]

#: Z79's ceiling (P13, P17).  The DMV, the corn maze and the cemetery
#: print none; two leaves room for one
#: line that carries something without letting a table of jokes back in.
FLAVOUR_BROADCAST_LIMIT = 2

#: How :mod:`zmforge.script.gags` writes each kind of flavour line into the
#: script: (kind, table entry pattern, the function it must sit in or None).
_FLAVOUR_TABLES = (
    ("zone-entry", re.compile(r'level\.zmf_gag_rooms\[\s*"[^"]*"\s*\]\s*='), None),
    ("round-end PA", re.compile(r"level\.zmf_gag_pa\[\s*\d+\s*\]\[\s*\d+\s*\]\s*="), None),
    ("random PA", re.compile(r"a_lines\[\s*\d+\s*\]\s*="), "zmf_gag_pa_random"),
)

_FUNCTION = re.compile(r"^function\s+(\w+)\s*\(([^)]*)\)\s*\n\{\n(.*?)^\}", re.M | re.S)


def _functions(script: str) -> dict[str, str]:
    return {m.group(1): m.group(3) for m in _FUNCTION.finditer(script)}


def _check_start_zones(script: str, report: Report) -> None:
    listed = [name for _, name in sorted(
        re.findall(r"init_zones\[(\d+)\]\s*=\s*\"([^\"]+)\"\s*;", script),
        key=lambda item: int(item[0]))]
    if not listed:
        return
    edges = re.findall(
        r"add_adjacent_zone\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*\)", script)
    always = re.search(r'flag::init\(\s*"([^"]+)"\s*\);\s*level flag::set\(\s*"\1"', script)
    always_on = always.group(1) if always else "always_on"
    for name in listed[1:]:
        roots = [z for z in listed if z != name]
        open_ = open_at_start(roots, edges, always_on)
        if name in open_:
            continue
        # Reached from the other listed zones through at least one door flag?
        reach = set(open_)
        via = None
        grew = True
        while grew:
            grew = False
            for a, b, flag in edges:
                if (a in reach) != (b in reach):
                    reach |= {a, b}
                    grew = True
                    if name in (a, b) and via is None:
                        via = flag
        if name in reach:
            report.add(error(
                "Z67",
                f"init_zones lists {name!r}, which a door opens (flag {via or '?'!r}): "
                "manage_zones enables every init_zones entry at load "
                "(_zm_zonemgr.gsc:841-844), so every zone_is_enabled wait on it passes "
                "at once and its respawn points unlock before the door is bought"))


_FIRE_WAIT = re.compile(r'waittill\(\s*"(weapon_fired|grenade_fire)"')


def _fire_watchers(functions: dict[str, str]) -> list[tuple[str, str, str | None, list[str]]]:
    """(watcher, notify, weapon, handlers) for each per-player fire watcher."""
    out = []
    for name, body in functions.items():
        m = _FIRE_WAIT.search(body)
        if not m:
            continue
        weapon = re.search(r'getweapon\(\s*"([^"]+)"\s*\)', body)
        handlers = re.findall(r"self thread (\w+)\(", body)
        out.append((name, m.group(1), weapon.group(1) if weapon else None, handlers))
    return out


def _check_fire_handlers(functions: dict[str, str], report: Report) -> None:
    for watcher, notify, weapon, handlers in _fire_watchers(functions):
        if weapon and GRENADE_WEAPON.search(weapon) and notify != "grenade_fire":
            report.add(error(
                "Z69",
                f"{watcher} watches {weapon!r} on {notify!r}; a thrown weapon is notified "
                "as grenade_fire ( grenade, weapon ), which is what every stock grenade "
                "watcher waits on (_zm_weapons.gsc:101), so this handler may never run"))
        for handler in handlers:
            body = functions.get(handler)
            if body is None or "add_to_player_score" not in body:
                continue
            pay = body.rfind("add_to_player_score")
            cooled = (re.search(r"isdefined\(\s*self\.\w+\s*\)", body)
                      or re.search(r"gettime\(\)\s*<", body))
            if not cooled:
                report.add(error(
                    "Z68",
                    f"{handler} pays points from a fire watcher ({watcher}) with no "
                    "per-player cooldown, so holding the trigger prints points"))
            if "return" in body[pay:]:
                report.add(error(
                    "Z68",
                    f"{handler} pays points and can still return early afterwards: pay "
                    "only once the thing the points are for has happened"))


def _check_spawn_delay(functions: dict[str, str], report: Report) -> None:
    for name, body in functions.items():
        if re.search(r'=\s*level\.zombie_vars\[\s*"zombie_spawn_delay"\s*\]', body) and \
                re.search(r'set_zombie_var\(\s*"zombie_spawn_delay",\s*n_\w+', body):
            report.add(warning(
                "Z70",
                f"{name} restores zombie_spawn_delay from a value saved before the "
                "change; a round that starts meanwhile resets it "
                "(_zm.gsc:4502), so restore through level.func_get_zombie_spawn_delay"))


def _check_moves(functions: dict[str, str], report: Report) -> None:
    for name, body in functions.items():
        m = re.search(r"\bself\s+setorigin\s*\(", body, re.I)
        if not m:
            continue
        before = body[: m.start()]
        waited = [w.end() for w in re.finditer(r"\bwait\b", before)]
        if not waited:
            continue
        if "player_is_in_laststand" not in before[waited[-1]:]:
            report.add(error(
                "Z71",
                f"{name} moves the player after a wait without checking last stand: a "
                "player who went down during the wait is carried away from revives"))


def _check_boss_guard(functions: dict[str, str], report: Report) -> None:
    for name in functions:
        m = re.fullmatch(r"zmf_boss_(\w+)_setup", name)
        if not m:
            continue
        body = functions[name]
        if "zmf_no_instakill" not in body:
            report.add(error(
                "Z73",
                f"{name} does not mark its boss against Insta-Kill: check_for_instakill "
                "kills any zombie in one hit while the powerup is up "
                "(_zm_powerups.gsc:1466-1500)"))
        spawn = functions.get(f"zmf_boss_{m.group(1)}_spawn", "")
        if "check_for_instakill_override" not in spawn:
            report.add(error(
                "Z73",
                f"zmf_boss_{m.group(1)}_spawn installs no level.check_for_instakill_override, "
                "the one hook that can veto the kill (_zm_powerups.gsc:1440-1445)"))


def flavour_broadcasts(script: str) -> dict[str, int]:
    """Flavour lines per kind (zone-entry, round-end PA, random PA) the gag
    helpers wrote into a server script."""
    functions = _functions(script)
    counts = {}
    for kind, pattern, inside in _FLAVOUR_TABLES:
        text = functions.get(inside, "") if inside else script
        counts[kind] = len(pattern.findall(text))
    return counts


def _check_flavour_broadcasts(script: str, report: Report) -> None:
    counts = flavour_broadcasts(script)
    total = sum(counts.values())
    if total > FLAVOUR_BROADCAST_LIMIT:
        found = ", ".join(f"{n} {kind}" for kind, n in counts.items() if n)
        report.add(warning(
            "Z79",
            f"{total} flavour broadcasts ({found}), over {FLAVOUR_BROADCAST_LIMIT}: "
            "lines on entering a zone, at a round end or on a timer must carry "
            "something the player needs (P13, P17); cut the rest"))


def check_perk_limit(script: str) -> Report:
    """Z82: the stock four-perk ceiling is lifted, after the entry that sets it.

    ``zm_perks::init`` assigns ``level.perk_purchase_limit = 4``
    (``_zm_perks.gsc:43``) from inside ``zm_usermap::main`` (via
    ``_load.gsc:79`` and ``_zm.gsc:362``), so an assignment before that call
    is reset.  The pointer is read at purchase time
    (``_zm_utility.gsc:5874-5889``).  Separate from
    :func:`check_gameplay_script` because it reads the whole scaffold (the
    framework entry), which that check's fragments do not carry."""
    report = Report()

    def fail(message: str) -> None:
        report.add(error("Z82", f"{message} (every map has no perk limit, "
                                "the emitter writes it after "
                                "the framework entry)"))

    main = _functions(script).get("main", "")
    entry = main.find(f"{FRAMEWORK_ENTRY}();")
    value = re.search(r"^\s*level\.perk_purchase_limit\s*=\s*(\d+)\s*;", main, re.M)
    hook = re.search(r"^\s*level\.get_player_perk_purchase_limit\s*=\s*&(\w+)\s*;",
                     main, re.M)
    if entry < 0:
        fail(f"main() never calls {FRAMEWORK_ENTRY}()")
        return report
    if value is None or value.start() < entry:
        fail("main() does not set level.perk_purchase_limit after "
             f"{FRAMEWORK_ENTRY}(), so the stock limit of 4 stands")
    elif int(value.group(1)) < NO_PERK_LIMIT:
        fail(f"level.perk_purchase_limit is {value.group(1)}, "
             f"below {NO_PERK_LIMIT}")
    if hook is None or hook.start() < entry:
        fail("main() does not set level.get_player_perk_purchase_limit after "
             f"{FRAMEWORK_ENTRY}()")
    else:
        body = _functions(script).get(hook.group(1))
        returned = re.search(r"return\s+(\d+)\s*;", body or "")
        if returned is None or int(returned.group(1)) < NO_PERK_LIMIT:
            fail(f"{hook.group(1)}() does not return at least {NO_PERK_LIMIT}")
    for pattern, name in ((r"level\.perk_purchase_limit\s*=", "level.perk_purchase_limit"),
                          (r"level\.get_player_perk_purchase_limit\s*=",
                           "level.get_player_perk_purchase_limit")):
        if len(re.findall(pattern, script)) > 1:
            fail(f"{name} is assigned more than once; only the emitter's "
                 f"{PERK_LIMIT_HOOK} line may set it")
    return report


def check_gameplay_script(script: str) -> Report:
    """Z67-Z71, Z73 and Z79 over the generated server script."""
    report = Report()
    functions = _functions(script)
    _check_flavour_broadcasts(script, report)
    _check_start_zones(script, report)
    _check_fire_handlers(functions, report)
    _check_spawn_delay(functions, report)
    _check_moves(functions, report)
    _check_boss_guard(functions, report)
    return report


def check_prompt_strings(strings: str) -> Report:
    """Z72 over the map's ``.str`` text: every ``*_PROMPT`` names the use key."""
    report = Report()
    for ref, value in re.findall(r'REFERENCE\s+(\S+)\s*\n\s*LANG_ENGLISH\s+"(.*)"', strings):
        if ref.endswith("PROMPT") and "[{+activate}]" not in value:
            report.add(warning(
                "Z72",
                f"prompt {ref} does not name the use key [{{+activate}}] (P5): "
                f"{value[:80]!r}"))
    return report
