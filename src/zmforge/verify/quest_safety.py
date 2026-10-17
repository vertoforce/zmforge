"""Quest, boss and co-op safety over the *generated* script.

The Workshop complaint study
ranks broken quest steps and soft-locks first (24 of 29 maps), co-op
breakage third (13) and unfair bosses sixth (11).  Most of those reports are
about two things happening at once: a dog round during a lockdown, a carrier
going down, a second player joining.  Like :mod:`zmforge.verify.gameplay`,
every check here reads the server script the emitter wrote,
not the recipe that meant to write it.

Q1  every quest or boss thread that waits ends on ``end_game``; a thread run
    on a player ends on ``disconnect``; a player taken from a trigger and
    used after a later wait is checked with ``isdefined`` first (they may
    have left).
Q2  a carried quest item has a way back: when its carrier goes down, bleeds
    out or leaves it returns to its spot (the item thread loops to respawn).
Q3  a timed or hold step cannot be broken by a special round: its countdown
    or hold pauses while ``special_round`` is set, or the step holds special
    rounds back (``lockdown``); a held step does not start during one.
Q4  a HUD element is per player (``NewClientHudElem`` stored on a player),
    or level-wide on purpose (``NewHudElem`` in a function that says
    ``// level-wide HUD: <why>``); never a client element in a level field.
Q5  "every player" counts use the present players (``sessionstate ==
    "playing"``), not ``getplayers()``; player-count scaling does too; a
    trigger that moves a player into a place does so for every player, not
    once.
Q6  every boss declares its time-to-kill target (``self.zmf_boss_ttk``);
    normal zombie spawns ease off while it lives, or it says they do not.
Q7  no required quest step waits on chance: no ``random*`` in a condition
    anywhere the step depends on, no random teleport destination, no wait on
    a stock random event (a power-up drop, the box), no weapon only the box
    gives.
"""

from __future__ import annotations

import re

from .report import Report, error, warning

__all__ = ["check_quest_safety", "wall_weapons_in_map", "LEVEL_WIDE_HUD"]

#: The comment a function carries when a ``NewHudElem`` in it is meant for
#: every player (a waypoint over a boss, say).  Q4.
LEVEL_WIDE_HUD = "// level-wide HUD:"

_FUNCTION = re.compile(r"^function\s+(\w+)\s*\(([^)]*)\)\s*\n\{\n(.*?)^\}", re.M | re.S)
_SCOPE = re.compile(r"^zmf_(quest|boss)_")
#: Variables a generated script uses for a player.
_PLAYER_VARS = r"(?:a_players\s*\[\s*\w+\s*\]|player|e_player|e_who|e_p|e_rider)"
_LEVEL_THREAD = re.compile(r"\blevel\s+thread\s+(\w+)\s*\(")
_PLAYER_THREAD = re.compile(rf"\b{_PLAYER_VARS}\s+thread\s+(\w+)\s*\(")
_BLOCKS = re.compile(r"^\s*(?:wait\b|.*\bwaittill\s*\()", re.M)
#: Stock events that happen by chance: a random power-up, the box's roll.
LUCK_EVENTS = ("powerup_grabbed", "powerup_dropped", "user_grabbed_weapon",
               "weapon_fly_away_start", "randomization_done")
#: What every player has without the box: the starting pistol, frag
#: grenades and the knife (zm_usermap's loadout).
ALWAYS_OWNED = frozenset({"pistol_standard", "frag_grenade", "knife", "bowie_knife"})


def _functions(script: str) -> dict[str, tuple[str, str]]:
    return {m.group(1): (m.group(2), m.group(3)) for m in _FUNCTION.finditer(script)}


def wall_weapons_in_map(map_text: str) -> set[str]:
    """Weapons a player can buy off a wall: the stock wall-buy prefabs the
    ``.map`` places (``_prefabs/zm/zm_core/spawnable_weapon_<name>.map``)."""
    return set(re.findall(r"spawnable_weapon_(\w+)\.map", map_text))


# --------------------------------------------------------------------------
# Q1: ends on end_game / disconnect; a player from a trigger may have left
# --------------------------------------------------------------------------
def _threaded(script: str) -> tuple[set[str], set[str]]:
    return set(_LEVEL_THREAD.findall(script)), set(_PLAYER_THREAD.findall(script))


def _check_endons(functions, script: str, report: Report) -> None:
    level_threads, player_threads = _threaded(script)
    for name, (_, body) in functions.items():
        if not _SCOPE.match(name):
            continue
        if not _BLOCKS.search(body):
            continue
        is_step = name.startswith("zmf_quest_step_")
        ends = ('endon( "end_game" )' in body or 'waittill( "end_game" )' in body
                or 'self endon( "death" )' in body)
        if (is_step or name in level_threads) and not ends:
            report.add(error(
                "Q1",
                f"{name} is a level thread that waits but has no level endon( \"end_game\" ): "
                "when the game ends it keeps running under the end screen "
                "(the quest HUD, a timer or a trigger outliving the game)"))
        if name in player_threads and 'self endon( "disconnect" )' not in body:
            report.add(error(
                "Q1",
                f"{name} runs on a player and waits, but has no self endon( \"disconnect\" ): "
                "a player who leaves mid-step leaves it running on a removed entity"))
        _check_left_players(name, body, report)


def _check_left_players(name: str, body: str, report: Report) -> None:
    lines = body.splitlines()
    for n, line in enumerate(lines):
        m = re.search(r'waittill\(\s*"trigger"\s*,\s*(\w+)\s*\)', line)
        if not m:
            continue
        who = m.group(1)
        waited = False
        for later in lines[n + 1:]:
            if re.search(rf'waittill\([^)]*\b{who}\b', later):
                break  # the variable is taken again
            if re.match(r"\s*wait\b", later) or ("waittill(" in later and who not in later):
                waited = True
                continue
            if waited and re.search(rf"\b{who}\b", later):
                if f"isdefined( {who} )" in later or f"isdefined({who})" in later:
                    break
                report.add(error(
                    "Q1",
                    f"{name} uses {who} (a player from a trigger) after a later wait "
                    f"without isdefined( {who} ): a player who disconnected meanwhile is "
                    "undefined and the step thread stops with a script error"))
                break


# --------------------------------------------------------------------------
# Q2: carried items come back
# --------------------------------------------------------------------------
def _check_carried(functions, report: Report) -> None:
    for name, (_, body) in functions.items():
        m = re.search(r"\b(\w+)\.(zmf_q_bag|zmf_carry\w*)\s*(?:\[[^\]]*\]\s*)?(\+\+|\+=)", body)
        if not m:
            continue
        who = m.group(1)
        after = body[m.end():]
        missing = []
        if "laststand::player_is_in_laststand" not in after:
            missing.append("goes down (last stand)")
        if '"spectator"' not in after:
            missing.append("bleeds out")
        if f"!isdefined( {who} )" not in after:
            missing.append("leaves")
        if not re.search(r"^\s*while \( true \)", body, re.M) or "spawn(" not in body:
            missing.append("respawn (the item thread loops back to spawn it)")
        if missing:
            report.add(error(
                "Q2",
                f"{name}: a carried item has no way back when its carrier "
                f"{', '.join(missing)}; the step can then never finish (P10)"))


# --------------------------------------------------------------------------
# Q3: timed and hold steps against special rounds
# --------------------------------------------------------------------------
_SPECIAL = 'flag::get( "special_round" )'


def _held_keys(functions) -> set[str]:
    body = functions.get("zmf_quest_holding", ("", ""))[1]
    return set(re.findall(r"zmf_q_ton_(\w+)", body)) | set(re.findall(r"// hold: (\w+)", body))


def _check_specials(functions, report: Report) -> None:
    held = _held_keys(functions)
    if held and "zmf_quest_hold_specials" not in functions:
        report.add(error("Q3", "zmf_quest_holding lists held steps but nothing runs it "
                               "(no zmf_quest_hold_specials)"))
    for name, (_, body) in functions.items():
        m = re.fullmatch(r"zmf_quest_timer_(\w+)", name)
        if m and "for ( n = " in body:
            key = m.group(1)
            if _SPECIAL not in body and key not in held:
                report.add(error(
                    "Q3",
                    f"step {key}'s countdown neither pauses during a special round nor "
                    "holds special rounds back: a dog round that starts mid-attempt runs "
                    "the clock out (the lockdown soft-lock players report on Der Riese: "
                    "Declassified)"))
        m = re.fullmatch(r"zmf_quest_step_(\w+)", name)
        if not m:
            continue
        key = m.group(1)
        hold = re.search(r"while \( (n_t) < \d+ \)", body)
        if hold and _SPECIAL not in body[hold.end():] and key not in held:
            report.add(error(
                "Q3",
                f"step {key} holds a spot for a time but neither pauses during a special "
                "round nor holds special rounds back"))
        if key in held:
            live = re.search(r"level\.zmf_q_state\[\s*\d+\s*\]\s*=\s*1\s*;", body)
            if _SPECIAL not in body[: live.start() if live else 0]:
                report.add(error(
                    "Q3",
                    f"step {key} holds special rounds back but can still start during one: "
                    "its gate does not wait for special_round to clear"))


# --------------------------------------------------------------------------
# Q4: HUD scope
# --------------------------------------------------------------------------
def _check_hud(functions, report: Report) -> None:
    for name, (_, body) in functions.items():
        for m in re.finditer(r"^(.*?)=\s*NewClientHudElem\s*\(\s*(.*?)\s*\)\s*;", body, re.M):
            target, owner = m.group(1).strip(), m.group(2)
            if target.startswith("level."):
                report.add(error(
                    "Q4",
                    f"{name} stores a per-player HUD element in {target}: one level field "
                    "holds only one player's element, so the next player's overwrites it "
                    "(splitscreen: player 2 sees player 1's line)"))
            if re.search(r"getplayers\(\)\s*\[\s*0\s*\]|level\.players\s*\[\s*0\s*\]", owner):
                report.add(error(
                    "Q4",
                    f"{name} makes a HUD element for the first player only ({owner}); "
                    "everyone else never sees it"))
        for m in re.finditer(r"^(.*?)=\s*NewHudElem\s*\(\s*\)", body, re.M):
            if LEVEL_WIDE_HUD in body:
                continue
            target = m.group(1).strip()
            report.add(error(
                "Q4",
                f"{name} makes a level-wide HUD element ({target} = NewHudElem()): every "
                "player sees it.  Make it per player (NewClientHudElem( player )) or say "
                f"why every player should see it with a '{LEVEL_WIDE_HUD}' line"))


# --------------------------------------------------------------------------
# Q5: co-op counts, scaling and movers
# --------------------------------------------------------------------------
def _check_coop(functions, report: Report) -> None:
    for name, (_, body) in functions.items():
        # (a) a count of flagged players compared with everyone in getplayers().
        for m in re.finditer(r"\bn\w*\s*>=\s*(\w+)\.size", body):
            var = m.group(1)
            before = body[: m.start()]
            last = [a for a in re.finditer(rf"\b{var}\s*=\s*([^;]+);", before)]
            if last and last[-1].group(1).strip() == "getplayers()" \
                    and "sessionstate" not in before[last[-1].end():]:
                report.add(error(
                    "Q5",
                    f"{name} compares a count with {var}.size where {var} = getplayers(): a "
                    "bled-out spectator holds the step up.  Count the present players "
                    "(quest.present_players_lines)"))
        # (b) player-count scaling over everyone, spectators included.
        if re.search(r"getplayers\(\)\.size\s*[-*+/]|[-*+/]\s*getplayers\(\)\.size", body):
            report.add(error(
                "Q5",
                f"{name} scales by getplayers().size, which counts bled-out spectators; "
                "scale by the players present (sessionstate \"playing\")"))
        # (c) a one-shot trigger that moves only the player who touched it.
        for m in re.finditer(r'waittill\(\s*"trigger"\s*,\s*(\w+)\s*\)', body):
            who = m.group(1)
            if re.search(r"\bwhile\b", body[: m.start()]):
                continue
            after = body[m.end():]
            mover = re.search(rf"\b{who}\s+(?:setorigin|SetOrigin)\s*\(", after)
            thread = re.search(rf"\b{who}\s+thread\s+(\w+)\s*\(", after)
            moves = bool(mover) or bool(
                thread and re.search(r"\bsetorigin\s*\(",
                                     functions.get(thread.group(1), ("", ""))[1], re.I))
            if moves:
                report.add(error(
                    "Q5",
                    f"{name} moves the one player who touched a trigger and never waits "
                    "again: in co-op only that player gets in (\"only one person can go "
                    "into the boss fight\").  Move every present player, or keep the "
                    "trigger for each"))


# --------------------------------------------------------------------------
# Q6: bosses declare a time-to-kill target and ease normal spawns
# --------------------------------------------------------------------------
def _check_bosses(functions, report: Report) -> None:
    for name, (_, body) in functions.items():
        m = re.fullmatch(r"zmf_boss_(\w+)_setup", name)
        if not m:
            continue
        key = m.group(1)
        if not re.search(r"self\.zmf_boss_ttk\s*=\s*[\d.]+\s*;", body):
            report.add(error(
                "Q6",
                f"boss {key} declares no time-to-kill target (self.zmf_boss_ttk): its health "
                "is not tied to how long the guns players have by then take to kill it "
                "(BossHealth.ttk)"))
        spawn = functions.get(f"zmf_boss_{key}_spawn", ("", ""))[1]
        if "level.zombie_ai_limit" not in spawn and "// boss fight keeps normal spawns" not in spawn:
            report.add(warning(
                "Q6",
                f"boss {key}: normal zombie spawns do not ease off while it lives "
                "(\"you fight more with the zombies than the actual boss\"); set "
                "Boss.fight_zombie_limit, or None to say so on purpose"))


# --------------------------------------------------------------------------
# Q7: no required step waits on chance
# --------------------------------------------------------------------------
_CALL = re.compile(r"(?:\bthread\s+|^\s*|=\s*|\(\s*|&)(zmf_\w+)\s*\(", re.M)
_RANDOM_IN_CONDITION = re.compile(
    r"^\s*(?:if|while|else if)\s*\(.*\brandom\w*\s*\(|"
    r"\brandom\w*\s*\([^;]*\)\s*(?:<|>|==|!=|<=|>=)", re.M)


def _depends(functions, root: str) -> set[str]:
    """``root`` and what it calls or threads, what sets the player fields it
    tests and what sends the notifies it waits on."""
    seen: set[str] = set()
    todo = [root]
    while todo:
        name = todo.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        body = functions[name][1]
        todo += [c for c in _CALL.findall(body) if c in functions]
        for field in set(re.findall(r"isdefined\(\s*[\w\[\] ]+\.(\w+)\s*\)", body)):
            todo += [f for f, (_, b) in functions.items()
                     if re.search(rf"\.{field}\s*=\s*(?!undefined)", b)]
        for event in set(re.findall(r'level\s+waittill\(\s*"(\w+)"', body)):
            todo += [f for f, (_, b) in functions.items()
                     if re.search(rf'level\s+notify\(\s*"{event}"', b)]
    return seen


def _check_luck(functions, report: Report, wall_weapons: set[str] | None) -> None:
    for name in functions:
        m = re.fullmatch(r"zmf_quest_step_(\w+)", name)
        if not m:
            continue
        key = m.group(1)
        for dep in sorted(_depends(functions, name)):
            body = functions[dep][1]
            if _RANDOM_IN_CONDITION.search(body) and "zmf_pity" not in body:
                report.add(error(
                    "Q7",
                    f"required step {key} depends on chance: {dep} tests a random roll "
                    "with no guarantee (\"an hour of bad RNG\").  Make it deterministic "
                    "or add a pity counter (a zmf_pity variable) that forces success"))
            rolls = [ln for ln in body.splitlines()
                     if re.search(r"\brandom\w*\s*\(", ln) and not re.match(r"\s*wait\b", ln)]
            if rolls and re.search(r"\b(?:setorigin|forceteleport)\s*\(", body, re.I) \
                    and "zmf_pity" not in body:
                report.add(error(
                    "Q7",
                    f"required step {key} depends on a random teleport in {dep} "
                    "(\"never get teleported where you need to go\"): pick the "
                    "destination the step needs, or add a pity counter"))
            for event in LUCK_EVENTS:
                if re.search(rf'waittill\(\s*"{event}"', body):
                    report.add(error(
                        "Q7",
                        f"required step {key} waits on {event!r} in {dep}, a stock event that "
                        "happens by chance (a random drop or the box)"))
            if wall_weapons is not None:
                for weapon in re.findall(r'getweapon\(\s*"(\w+)"\s*\)', body):
                    if weapon not in wall_weapons and weapon not in ALWAYS_OWNED:
                        report.add(error(
                            "Q7",
                            f"required step {key} needs {weapon!r} ({dep}), which is on no "
                            "wall and not in the starting loadout: only the box gives it"))


def check_quest_safety(script: str, *, wall_weapons: set[str] | None = None) -> Report:
    """Q1-Q7 over the generated server script.  ``wall_weapons`` (from
    :func:`wall_weapons_in_map`) turns on Q7's box-only weapon test."""
    report = Report()
    functions = _functions(script)
    _check_endons(functions, script, report)
    _check_carried(functions, report)
    _check_specials(functions, report)
    _check_hud(functions, report)
    _check_coop(functions, report)
    _check_bosses(functions, report)
    _check_luck(functions, report, wall_weapons)
    return report
