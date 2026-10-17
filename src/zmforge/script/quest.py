"""Quests: a multi-step Easter egg, an objective HUD, and a buyable win.

**Using it (any map).**  A quest is a list of steps, each a small mechanic
with its own words, and an optional exit the finished quest unlocks::

    from zmforge.script import quest as q

    register = q.Quest(
        key="register",
        header="CARS REGISTERED: &&1 OF &&2",           # top-left, always on
        intro="Register four cars to leave the DMV.",   # centre, at start
        step_done="CAR &&1 OF &&2 REGISTERED",           # centre, per step
        complete="ALL FOUR CARS REGISTERED. The exit is open.",
        idle="CURRENT TASK: wait for your next appointment",
        steps=(
            q.HitTargets(key="vision", task="CURRENT TASK: Vision Test - shoot "
                         "E, F, P in order (&&1/&&2)", start=..., done=...,
                         targets=(q.Target(point=(x, y, z)), ...)),
            q.CollectDeliver(key="forms", ...),
            q.DefeatBoss(key="road", boss=bosses.Boss(...), ...),
        ),
        exit=q.BuyableExit(origin=(x, y, z), price=20000, ...),
    )
    q.install_quest(bp, register)          # ships every line, weaves the logic

Every string is plain text here; :func:`install_quest` ships each one with
:meth:`~zmforge.blueprint.model.Blueprint.add_map_string` (prompts on
triggers as ``triggerstring``, the rest as ``string``) and passes ``&&1`` /
``&&2`` as the stock calls do.  :func:`quest_script` is the pure half, for
tests.  :meth:`Quest.use_points` lists every use trigger the quest spawns so
a map test can hold them clear of its purchases.

**Steps** (each a dataclass; the common fields are on :class:`Step`):

=================  ==========================================================
step               what the player does
=================  ==========================================================
:class:`HitTargets`  shoot (``mode="shoot"``) or knife (``"melee"``) points on
                   the map's own props, optionally in order, optionally only
                   in the window after a :class:`Flash`
:class:`CollectDeliver`  pick items up (carried per player; dropped items go
                   back if the carrier bleeds out) and hand them in at a desk
:class:`KillInZone`  kill N zombies inside a radius
:class:`SoulBox`   feed the souls of zombies killed near them to one or
                   more :class:`Vessel` (a pumpkin, a grave) until each is
                   full; each soul flies to its vessel (souls scale with the
                   players connected)
:class:`StandInZone`  hold a spot for T seconds (optionally resetting on exit)
:class:`SurviveRounds`  survive N more rounds
:class:`DefeatBoss`  a :class:`~zmforge.script.bosses.Boss` spawns (when the
                   step starts or when a player enters its arena); kill it
=================  ==========================================================

Steps run **in order** (``Quest.ordered``, the default) or all at once.  A
step may also wait for a round (``unlock_round``), with a ``waiting`` HUD
line meanwhile.  A step whose points stand in a zone behind a door also waits
for that zone to open (``zones``, filled in by :func:`install_quest`; P8,
check Z61), with a ``find`` HUD line meanwhile, so nothing starts, shows
its task or runs a timer before players can reach it.  :class:`HitTargets` and :class:`CollectDeliver` take an
optional ``time_limit`` (seconds from the step's first progress, counted
down under the task on every HUD; out of time, ``timeout`` is said, the
progress goes back to 0, carried and floor items return to their spots, and
the step can be retried at once).  Progress persists in level variables: step ``i`` is done
when ``level.zmf_q_state[ i ] == 2`` (``level notify( "zmf_quest_step_done"
)`` each time one finishes), and the whole quest when
``level.zmf_quest_done`` is 1 (``level notify( "zmf_quest_done" )``).  Not
level *flags*: check Z3 refuses any ``flag::init`` written after the zone
hook's first ``add_adjacent_zone``, and custom functions are emitted after
it.

**Interruptions** (common Workshop complaints; checks Q1-Q3,
Q5, Q7 in :mod:`zmforge.verify.quest_safety`).  Every step thread ends on
``end_game``; a player from a trigger is re-checked with ``isdefined``
after any wait.  A countdown (``time_limit``) and a :class:`StandInZone`
hold pause while the stock ``special_round`` flag is set (a dog round);
with ``lockdown=True`` the step instead holds special rounds back while it
runs (``zmf_quest_hold_specials`` pushes ``level.next_dog_round`` past the
coming round at each ``end_of_round``) and does not start during one.  A
carried item goes back to its spot when its carrier goes down, bleeds out
or leaves; a player down inside a hold zone pauses the hold rather than
resetting it.  "Every player" counts take the players present
(:func:`present_players_lines`).  A :class:`DefeatBoss` never spawns during
a special round, and its boss holds the next one back and eases normal
spawns while it lives (:mod:`zmforge.script.bosses`).

**What the player sees.**  Top-left, always: the quest header with its
count, and under it the current task with that task's progress.  Centre
screen: a line when a step starts (``start``), each time it advances
(``advance``, optional), when it is done (``done``) and the quest's
``step_done`` count, and when everything is done (``complete``).  A step
with a ``hint`` tells a player who walks near its spot, while the step is
the live one, how to start it.

**Evidence** (``share/raw/scripts`` of the mod tools; engine calls are in
:mod:`zmforge.script.symbols` with their lines):

=========================  ===================================================
piece                      stock source
=========================  ===================================================
persistent HUD text        ``NewClientHudElem( player )`` then fields and
                           ``SetText``: ``shared/teamgather_shared.gsc:811-827``
                           (``font "objective"``, ``hidewheninmenu``);
                           ``user_left`` / ``user_top``:
                           ``shared/hud_util_shared.gsc:1035-1036``; two
                           parameters: ``teamgather_shared.gsc:733``
                           ``setText( &"TEAM_GATHER_PLAYERS_READY", a, b )``
centre popups              ``IPrintLnBold`` (:mod:`zmforge.script.gags`)
shooting a point           ``self waittill( "weapon_fired" )``
                           (``zm/_zm_weap_octobomb.gsc:160``), aim from
                           ``GetEye`` + ``GetWeaponForwardDir``, blocked test
                           with ``BulletTrace( eye, point, false, self )`` and
                           ``["fraction"]`` (``shared/colors_shared.gsc:398-399``)
knifing a point            the stock "did a player melee this" test,
                           ``zm/_zm_ai_wasp.gsc:1318`` (``weapon_melee``) and ``:1290-1303``:
                           ``GetEye``, ``Distance2DSquared`` against 72 units,
                           height within 64, ``VectorDot`` of
                           ``GetWeaponForwardDir`` against 0.5
flash / pulse effects      ``PlayFX( level._effect[ name ], origin )``
                           (``zm/_zm_powerups.gsc:925``), names from
                           :data:`zmforge.script.bosses.BOSS_FX`
white screen flash         ``player thread lui::screen_flash( ... )``
                           (``shared/lui_shared.gsc:432``; on the player,
                           since a level call fans out to all, ``:434-439``)
centred countdown text     ``NewClientHudElem`` with ``alignX``/``horzAlign``
                           ``"center"``, ``alignY``/``vertAlign`` ``"middle"``
                           (``zm/_zm.gsc:6070-6073``)
use triggers             ``spawn( "trigger_radius_use", ... )`` set up as
                           :func:`zmforge.script.tricks.take_a_ticket` does
kills in a zone            ``zm_spawner::register_zombie_death_event_callback``
                           (``zm/_zm_spawner.gsc:2463``), called on the
                           zombie with the attacker (``:2344``, ``:2458``)
rounds                     ``start_of_round`` / ``end_of_round``
                           (``zm/_zm.gsc:4433`` / ``:4449``)
bled out = spectator       ``sessionstate == "spectator"`` (``zm/_zm.gsc:1783``)
paying                     ``zm_score::can_player_purchase`` (``zm/_zm_score.gsc:
                           655``) then ``minus_to_player_score`` (``:551``), the
                           pair ``zm/_zm_perk_widows_wine.gsc:681``, ``:704``
ending the game            ``level notify( "end_game" )`` (``zm/_zm.gsc:1791``),
                           which ``end_game()`` waits for (``:5990``)
the win screen             ``level.custom_game_over_hud_elem``: ``end_game()``
                           calls it with ``( player, game_over, survived )``
                           instead of laying out GAME OVER itself
                           (``zm/_zm.gsc:6064-6066``); the stock layout it
                           replaces is ``:6070-6099``
=========================  ===================================================

**What the win looks like** (read from ``end_game()``, not seen): the exit's
``win_line`` centre screen to everyone, three seconds, then the stock end
sequence with this map's ``win_title`` where GAME OVER would be and the stock
"You survived N rounds" under it (``end_game()`` sets that text after the
callback, ``zm/_zm.gsc:6118-6132``), the game-over music state, then the
scoreboard.  The engine records it as an ordinary game end; there is no
separate stock "win" result for a usermap to set.

**Unverified in play:** everything on screen (HUD position, how two-line
text reads, the win title), whether ``weapon_fired`` fires for every weapon
class (it does not for grenades by name), that aim tolerance feels fair,
and whether a script-spawned ``script_model`` of a declared xmodel renders.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Sequence

from .bosses import BOSS_FX, Boss, boss_script, boss_strings, precache_boss_fx
from .custom import CustomFunction, CustomScript, Slot, merge
from .glow import LOOPING_FX, tag_glow_lines
from .tricks import _vector

__all__ = [
    "Quest",
    "Step",
    "Target",
    "Flash",
    "Hint",
    "Item",
    "HitTargets",
    "CollectDeliver",
    "KillInZone",
    "SoulBox",
    "Vessel",
    "StandInZone",
    "EveryPlayerFlag",
    "SurviveRounds",
    "DefeatBoss",
    "BuyableExit",
    "quest_strings",
    "quest_script",
    "install_quest",
    "gate_quest",
    "step_points",
    "gate_quest",
    "step_points",
    "param_count",
]

_FLAG = r"scripts\shared\flag_shared"
_LUI = r"scripts\shared\lui_shared"
_LASTSTAND = r"scripts\shared\laststand_shared"
_SCORE = r"scripts\zm\_zm_score"
_SPAWNER = r"scripts\zm\_zm_spawner"
_ZONEMGR = r"scripts\zm\_zm_zonemgr"

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

#: The HUD's ``level.zmf_quest_cur`` values that are not a step index.
_IDLE, _EXIT, _WON = -1, -2, -3
#: Seconds between an ordered HitTargets step's start line and its first cue,
#: so the two are not printed centre screen at the same moment.
CUE_GAP = 2.0
#: A timed step's countdown line when it names none (seconds left as ``&&1``).
TIMER_LINE = "TIME LEFT: &&1 s"
#: A zone-gated step's HUD line while its zone is still closed, when the step
#: names none (``Step.find``).  Plain on purpose: the point of the gate is that
#: nothing starts early; the line only keeps the HUD saying what to do (P6).
FIND_LINE = "CURRENT TASK: open the doors to reach the next task"


def param_count(text: str) -> int:
    """How many parameters a line uses: ``&&2`` means two, ``&&1`` one."""
    if "&&2" in text:
        if "&&1" not in text:
            raise ValueError(f"{text!r} uses &&2 without &&1")
        return 2
    return 1 if "&&1" in text else 0


def _check_key(key: str, what: str) -> None:
    if not _KEY.match(key):
        raise ValueError(f"{what} key {key!r} must be [a-z][a-z0-9_]*")


def _ms(seconds: float) -> int:
    return int(round(float(seconds) * 1000))


# --------------------------------------------------------------------------
# The pieces a step is made of
# --------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class Hint:
    """A spot that tells a player how to start the live step.  Said centre
    screen once per ``cooldown`` seconds per player while they are within
    ``radius`` of ``point`` (a ``trigger_radius``)."""

    point: tuple[float, float, float]
    text: str
    radius: float = 180.0
    height: float = 128.0
    cooldown: float = 25.0


@dataclass(frozen=True, kw_only=True)
class Target:
    """A point on the map's own geometry to shoot or knife.  ``radius`` is
    the aim tolerance.  ``cue`` (ordered steps) is said when this target
    becomes the next one.  ``model`` spawns a ``script_model`` there for the
    step's life (declared ``xmodel`` in the zone); leave it ``None`` to aim
    at a prop the map already places."""

    point: tuple[float, float, float]
    radius: float = 12.0
    cue: str | None = None
    model: str | None = None
    yaw: float = 0.0


@dataclass(frozen=True, kw_only=True)
class Flash:
    """The target is only live for ``open`` seconds after it flashes, every
    ``every`` seconds (random in range).  ``line`` is said to players within
    ``heard`` units when it flashes; ``late`` to a player who hits it shut."""

    line: str
    late: str
    every: tuple[float, float] = (5.0, 9.0)
    open: float = 2.0
    heard: float = 700.0
    fx: str = "powerup_grabbed_solo"
    #: Optional, all off by default (the maps that predate them are unchanged).
    #: ``countdown`` seconds are counted down before each flash on a centre
    #: HUD line (``count_line``, the seconds left as ``&&1``) for every
    #: player within ``heard``; the same line then shows ``line`` for the
    #: open window instead of a centre print that can queue behind others.
    countdown: int = 0
    count_line: str | None = None
    count_fx: str | None = None
    #: Said to a player who hits it before it has flashed; ``late`` is then
    #: only for a hit after the window shut.  ``None``: ``late`` for both.
    early: str | None = None
    #: A white screen flash (``lui::screen_flash``) on every player within
    #: ``heard`` when it flashes.
    screen: bool = False

    def __post_init__(self) -> None:
        if self.countdown < 0:
            raise ValueError("countdown >= 0")
        if self.countdown and not self.count_line:
            raise ValueError("a countdown needs a count_line (seconds left as &&1)")
        if self.count_line and param_count(self.count_line) != 1:
            raise ValueError("the count_line takes the seconds left as &&1 and nothing else")
        for fx in (self.fx, self.count_fx):
            if fx is not None and fx not in BOSS_FX:
                raise ValueError(f"{fx!r} is not a stock effect name")


@dataclass(frozen=True, kw_only=True)
class Item:
    """One thing to pick up.  ``picked`` is said to whoever takes it."""

    point: tuple[float, float, float]
    picked: str
    model: str | None = None
    yaw: float = 0.0


@dataclass(frozen=True, kw_only=True)
class Step:
    """Fields every step has.

    ``task`` is the HUD's CURRENT TASK line while the step is live, with the
    step's progress as ``&&1`` and its total as ``&&2`` if it wants them.
    ``start`` and ``done`` are said centre screen; ``advance`` (optional) at
    each bit of progress with the same two parameters.  ``waiting`` is the
    HUD line while the step is next but ``unlock_round`` has not come, with
    that round as ``&&1``.

    ``time_limit`` (optional, :class:`HitTargets` and :class:`CollectDeliver`
    only): seconds from the step's first progress to finish it.  The seconds
    left count down on every player's HUD under the task (``timer_line``,
    the seconds as ``&&1``); when they run out ``timeout`` is said to
    everyone, the step's progress goes back to 0 and it can be tried again
    at once.  ``None`` (the default) emits exactly what it did before.
    """

    key: str
    task: str
    start: str
    done: str
    advance: str | None = None
    hint: Hint | None = None
    unlock_round: int = 0
    waiting: str | None = None
    time_limit: float | None = None
    timeout: str | None = None
    #: The countdown's HUD line; ``None`` is :data:`TIMER_LINE`.  Only a
    #: step with a ``time_limit`` has one (an untimed step carries no
    #: countdown text at all, so reviews do not read one into its HUD).
    timer_line: str | None = None
    #: Zones (zone manager names) that must be open before the step starts,
    #: shows its task or runs its timer.  :func:`install_quest` adds every
    #: door-gated zone the step's points stand in (:func:`step_points`), so
    #: a recipe sets this only for a zone its points do not show.
    zones: tuple[str, ...] = ()
    #: The HUD line while a ``zones`` gate is closed; ``None`` is
    #: :data:`FIND_LINE`.  No parameters.
    find: str | None = None
    #: Hold special rounds (dog rounds) back while the step runs: a timed
    #: step while its countdown runs, a hold or kill step while it is live.
    #: The step also does not start during one.  Without it a countdown
    #: or a hold only pauses while a special round is on (Q3: a lockdown
    #: started during a dog round must not soft-lock the quest).  Timed steps and :class:`StandInZone` /
    #: :class:`KillInZone` only.
    lockdown: bool = False

    #: Whether this kind of step takes a ``time_limit``.
    _TIMED = False
    #: Whether this kind of step runs for a while untimed (a hold or a kill
    #: count), so ``lockdown`` means something without a ``time_limit``.
    _HOLDS = False

    def __post_init__(self) -> None:
        _check_key(self.key, "step")
        for zone in self.zones:
            if not re.fullmatch(r"[A-Za-z0-9_]+", zone):
                raise ValueError(f"{self.key}: zone name {zone!r}")
        if self.find is not None and param_count(self.find):
            raise ValueError(f"{self.key}: the find line takes no parameters")
        if self.unlock_round and self.waiting is None:
            raise ValueError(f"{self.key}: a step gated on a round needs a waiting line")
        if self.lockdown and self.time_limit is None and not self._HOLDS:
            raise ValueError(f"{self.key}: lockdown is for a timed step, a hold or a kill count")
        if self.time_limit is None:
            if self.timeout is not None or self.timer_line is not None:
                raise ValueError(f"{self.key}: a timeout or timer line without a time_limit")
            return
        if not self._TIMED:
            raise ValueError(f"{self.key}: {type(self).__name__} does not take a time_limit")
        if self.time_limit <= 0:
            raise ValueError(f"{self.key}: time_limit > 0")
        if not self.timeout:
            raise ValueError(f"{self.key}: a time_limit needs a timeout line")
        if param_count(self.timeout):
            raise ValueError(f"{self.key}: the timeout line takes no parameters")
        if param_count(self.timer_line or TIMER_LINE) != 1:
            raise ValueError(f"{self.key}: the timer_line takes the seconds left as &&1 only")

    # -- what each kind supplies ------------------------------------------
    @property
    def total(self) -> int:
        raise NotImplementedError

    def lines(self) -> dict[str, tuple[str, str]]:
        """role -> (text, kind) for this step's own words."""
        out = {"task": (self.task, "string"), "start": (self.start, "string"),
               "done": (self.done, "string")}
        if self.advance:
            out["advance"] = (self.advance, "string")
        if self.hint:
            out["hint"] = (self.hint.text, "string")
        if self.waiting:
            out["waiting"] = (self.waiting, "string")
        if self.zones:
            out["find"] = (self.find or FIND_LINE, "string")
        if self.time_limit is not None:
            out["timeout"] = (self.timeout, "string")
            out["timer"] = (self.timer_line or TIMER_LINE, "string")
        return out

    def body(self, i: int, s) -> list[str]:
        raise NotImplementedError

    def extra(self, i: int, s) -> list[CustomFunction]:
        return []

    def using(self) -> tuple[str, ...]:
        return ()

    def assets(self) -> tuple[tuple[str, str], ...]:
        return ()

    def use_points(self) -> list[tuple[float, float, float]]:
        return []


def _say(s, role: str, a: str = "", b: str = "", target: str | None = None) -> list[str]:
    """Say one of a step's lines centre screen, to ``target`` or everyone,
    with as many parameters as the line uses."""
    ref, n = s(role)
    given = [x for x in (a, b) if x]
    if n > len(given):
        raise ValueError(f"{ref} uses {n} parameter(s) and this line passes {len(given)}")
    args = [f'&"{ref}"'] + given[:n]
    call = f"IPrintLnBold( {', '.join(args)} );"
    if target is not None:
        return [f"{target} {call}"]
    return [f"zmf_quest_all_{n}( {', '.join(args)} );"]


def _when(condition: str, body: list[str], depth: int) -> list[str]:
    """``if ( condition ) { body }`` at ``depth`` tabs, or nothing at all."""
    if not body:
        return []
    pad = "\t" * depth
    return [f"{pad}if ( {condition} )", f"{pad}{{", *(pad + "\t" + x for x in body), f"{pad}}}"]


def _advance(step: Step, s, n: str) -> list[str]:
    if not step.advance:
        return []
    return _say(s, "advance", n, str(step.total))


#: The time-limit countdown's HUD line: under the task (y 40), top left.
TIMER_Y = 64


def _timer_start(step: Step) -> list[str]:
    """Start the step's countdown unless it is already running."""
    k = step.key
    return [f"if ( !level.zmf_q_ton_{k} )", "{", f"\tlevel.zmf_q_ton_{k} = 1;",
            f"\tlevel thread zmf_quest_timer_{k}();", "}"]


def _timer_init(step: Step) -> list[str]:
    k = step.key
    return [f"level.zmf_q_ton_{k} = 0;", f"level.zmf_q_tout_{k} = 0;",
            f"level thread zmf_quest_timer_bye_{k}();"]


def _timer_functions(step: Step, s, wake: str) -> list[CustomFunction]:
    """A step's time limit: the countdown thread, its HUD line on every
    player, and the line off every screen.

    ``zmf_quest_timer_<key>`` runs from the step's first progress (see
    :func:`_timer_start`); when it runs out it sets ``level.zmf_q_tout_<key>``
    and notifies ``wake`` (the event the step's own loop waits on), and the
    step resets itself.  It ends early on the step's end
    (``zmf_q_end_<key>``) or a stop (``zmf_q_tstop_<key>``: an ordered step's
    wrong hit starts the attempt again)."""
    k = step.key
    whole = max(1, math.ceil(float(step.time_limit) - 1e-9))
    first = float(step.time_limit) - (whole - 1)
    line, _ = s("timer")
    el = f"zmf_q_tl_{k}"
    tick = ["\twait 1;"] if abs(first - 1.0) < 1e-9 else [
        f"\tif ( n == {whole} )", "\t{", f"\t\twait {first:g};", "\t}",
        "\telse", "\t{", "\t\twait 1;", "\t}"]
    return [
        CustomFunction(
            f"zmf_quest_timer_{k}",
            (
                'level endon( "end_game" );',
                f'level endon( "zmf_q_end_{k}" );',
                # Only an ordered hit step with a wrong line ever sends the
                # stop; no dead endon anywhere else.
                *((f'level endon( "zmf_q_tstop_{k}" );',)
                  if isinstance(step, HitTargets) and step.ordered and step.wrong else ()),
                f"for ( n = {whole}; n > 0; n-- )",
                "{",
                # A special round (a dog round) pauses the clock rather than
                # running it out under the dogs (Q3); a lockdown step holds
                # them back instead (zmf_quest_hold_specials).
                '\twhile ( level flag::get( "special_round" ) )',
                "\t{",
                "\t\twait 0.5;",
                "\t}",
                f"\tzmf_quest_timer_hud_{k}( n );",
                *tick,
                "}",
                f"zmf_quest_timer_hide_{k}();",
                f"level.zmf_q_ton_{k} = 0;",
                f"level.zmf_q_tout_{k} = 1;",
                f'level notify( "{wake}" );',
            ),
            purpose=(f"{k}: {float(step.time_limit):g}s from the first progress, counted down on\n"
                     "every HUD; out of time, the step's loop is woken to reset it."),
        ),
        CustomFunction(
            f"zmf_quest_timer_hud_{k}",
            (
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                "\te_p = a_players[ i ];",
                f"\tif ( !isdefined( e_p.{el} ) )",
                "\t{",
                f"\t\te_p.{el} = zmf_quest_hud_elem( e_p, {TIMER_Y}, 1.5, ( 1, 0.4, 0.3 ) );",
                "\t}",
                f'\te_p.{el} SetText( &"{line}", n );',
                "}",
            ),
            params=("n",),
            purpose=f"{k}: the seconds left, under the task on every player (and anyone who joined).",
        ),
        CustomFunction(
            f"zmf_quest_timer_hide_{k}",
            (
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                f"\tif ( isdefined( a_players[ i ].{el} ) )",
                "\t{",
                f"\t\ta_players[ i ].{el} destroy();",
                f"\t\ta_players[ i ].{el} = undefined;",
                "\t}",
                "}",
            ),
            purpose=f"{k}: the countdown off every screen.",
        ),
        CustomFunction(
            f"zmf_quest_timer_bye_{k}",
            (
                f'level endon( "zmf_q_end_{k}" );',
                'level waittill( "end_game" );',
                f"zmf_quest_timer_hide_{k}();",
            ),
            purpose=f"{k}: no countdown left over the end screen.",
        ),
    ]


@dataclass(frozen=True, kw_only=True)
class HitTargets(Step):
    """Shoot or knife a set of points, ``hits`` times each, in order or not.

    Ordered: hitting the wrong target says ``wrong`` (if given) and, if any
    progress was made, starts the sequence again.  With a :class:`Flash`
    only hits inside the open window count, one per flash."""

    targets: tuple[Target, ...]
    mode: str = "shoot"
    ordered: bool = True
    hits: int = 1
    wrong: str | None = None
    #: Say a target's ``cue`` only after a wrong hit (the next right one),
    #: never up front: a cue printed at every step is the answer, not help.
    cue_after_wrong: bool = False
    flash: Flash | None = None
    pulse_fx: str | None = None
    reach: float | None = None

    _TIMED = True

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if not self.targets:
            raise ValueError(f"{self.key}: no targets")
        if self.mode not in ("shoot", "melee"):
            raise ValueError(f"{self.key}: mode is 'shoot' or 'melee'")
        if self.hits < 1:
            raise ValueError(f"{self.key}: hits >= 1")
        if self.pulse_fx is not None and self.pulse_fx not in BOSS_FX:
            raise ValueError(f"{self.pulse_fx!r} is not a stock effect name")
        if self.flash and self.flash.fx not in BOSS_FX:
            raise ValueError(f"{self.flash.fx!r} is not a stock effect name")

    @property
    def total(self) -> int:
        return len(self.targets) * self.hits

    @property
    def distance(self) -> float:
        if self.reach is not None:
            return float(self.reach)
        return 72.0 if self.mode == "melee" else 3000.0

    def lines(self):
        out = Step.lines(self)
        if self.wrong:
            out["wrong"] = (self.wrong, "string")
        if self.flash:
            out["flash"] = (self.flash.line, "string")
            out["late"] = (self.flash.late, "string")
            if self.flash.early:
                out["early"] = (self.flash.early, "string")
            if self.flash.countdown:
                out["count"] = (self.flash.count_line, "string")
        for j, target in enumerate(self.targets):
            if target.cue:
                out[f"cue{j}"] = (target.cue, "string")
        return out

    def assets(self):
        return tuple(("xmodel", t.model) for t in self.targets if t.model)

    def using(self):
        return (_LUI,) if self.flash and self.flash.screen else ()

    def _cue(self, s, index: str, *, wrong: bool = False) -> list[str]:
        cues = [j for j, t in enumerate(self.targets) if t.cue]
        if not cues or not self.ordered:
            return []
        # ``cue_after_wrong``: the cues are help, not the answer; they are
        # said only after a wrong hit (a Vision Test that prints every letter
        # in order gives the answer away).
        if self.cue_after_wrong != wrong:
            return []
        out = []
        for j in cues:
            ref, _ = s(f"cue{j}")
            out += [f"if ( {index} == {j} )", "{", f'\tzmf_quest_all_0( &"{ref}" );', "}"]
        return out

    def body(self, i, s):
        k = self.key
        hit, end = f"zmf_q_hit_{k}", f"zmf_q_end_{k}"
        lines = ["a_pts = [];"]
        lines += [f"a_pts[ {j} ] = {_vector(t.point)};" for j, t in enumerate(self.targets)]
        lines += ["a_r = [];"]
        lines += [f"a_r[ {j} ] = {float(t.radius):g};" for j, t in enumerate(self.targets)]
        for j, t in enumerate(self.targets):
            if t.model:
                lines += [
                    f'e_mdl_{j} = spawn( "script_model", a_pts[ {j} ] );',
                    f'e_mdl_{j} SetModel( "{t.model}" );',
                    f"e_mdl_{j}.angles = ( 0, {float(t.yaw):g}, 0 );",
                ]
        melee = "1" if self.mode == "melee" else "0"
        lines += [
            f"level.zmf_q_next_{k} = 0;",
            f"level.zmf_q_hits_{k} = [];",
            "for ( j = 0; j < a_pts.size; j++ )",
            "{",
            f"\tlevel.zmf_q_hits_{k}[ j ] = 0;",
            "}",
        ]
        if self._cue(s, "0"):
            # The start line gets the centre of the screen to itself before
            # the first cue joins it; nothing is watched until then, so no
            # hit is dropped between the two.
            lines.append(f"wait {CUE_GAP:g};")
        lines += [
            f'level thread zmf_quest_aim_attach( a_pts, a_r, {melee}, {self.distance:g}, "{hit}", "{end}" );',
        ]
        if self.flash:
            lines.append(f"level thread zmf_quest_flash_{k}( a_pts[ 0 ] );")
        if self.pulse_fx:
            lines.append(f"level thread zmf_quest_pulse_{k}( a_pts );")
        lines += self._cue(s, "0")
        timed = self.time_limit is not None
        if timed:
            lines += _timer_init(self)
        lines += ["n_done = 0;", "n_tgt = 0;", "n_hit = 0;",
                  f"while ( n_done < {self.total} )", "{",
                  f'\tlevel waittill( "{hit}", j, e_who );']
        if timed:
            # Out of time (zmf_quest_timer_<key> woke this loop with no hit):
            # every bit of progress goes, and the first target is next again.
            lines += [
                f"\tif ( level.zmf_q_tout_{k} )",
                "\t{",
                f"\t\tlevel.zmf_q_tout_{k} = 0;",
                "\t\tn_done = 0;",
                "\t\tn_tgt = 0;",
                "\t\tn_hit = 0;",
                f"\t\tlevel.zmf_q_next_{k} = 0;",
                "\t\tfor ( j = 0; j < a_pts.size; j++ )",
                "\t\t{",
                f"\t\t\tlevel.zmf_q_hits_{k}[ j ] = 0;",
                "\t\t}",
                f"\t\tzmf_quest_progress( {i}, 0 );",
                *("\t\t" + x for x in _say(s, "timeout")),
                *("\t\t" + x for x in self._cue(s, "0")),
                "\t\tcontinue;",
                "\t}",
            ]
        lines += ["\tif ( !isdefined( e_who ) )", "\t{", "\t\tcontinue;", "\t}"]
        if self.flash and self.flash.early:
            # Phases (set by zmf_quest_flash_<key>): 0 before the first
            # flash, 1 counting down, 2 open, 3 shut, 4 taken (said nothing:
            # the advance line has just told everyone).
            late, _ = s("late")
            early, _ = s("early")
            ph = f"level.zmf_q_phase_{k}"
            lines += [
                f"\tif ( !isdefined( level.zmf_q_open_{k} ) || gettime() > level.zmf_q_open_{k} )",
                "\t{",
                f"\t\tif ( isdefined( {ph} ) && {ph} == 4 )",
                "\t\t{",
                "\t\t\tcontinue;",
                "\t\t}",
                "\t\tif ( !isdefined( e_who.zmf_q_late ) || gettime() > e_who.zmf_q_late )",
                "\t\t{",
                "\t\t\te_who.zmf_q_late = gettime() + 1500;",
                f"\t\t\tif ( isdefined( {ph} ) && {ph} == 3 )",
                "\t\t\t{",
                f'\t\t\t\te_who IPrintLnBold( &"{late}" );',
                "\t\t\t}",
                "\t\t\telse",
                "\t\t\t{",
                f'\t\t\t\te_who IPrintLnBold( &"{early}" );',
                "\t\t\t}",
                "\t\t}",
                "\t\tcontinue;",
                "\t}",
                f"\tlevel.zmf_q_open_{k} = 0;",
                f"\t{ph} = 4;",
            ]
            if self.flash.countdown:
                lines.append(f"\tzmf_quest_flash_hide_{k}();")
        elif self.flash:
            late, _ = s("late")
            lines += [
                f"\tif ( !isdefined( level.zmf_q_open_{k} ) || gettime() > level.zmf_q_open_{k} )",
                "\t{",
                "\t\tif ( !isdefined( e_who.zmf_q_late ) || gettime() > e_who.zmf_q_late )",
                "\t\t{",
                "\t\t\te_who.zmf_q_late = gettime() + 1500;",
                f'\t\t\te_who IPrintLnBold( &"{late}" );',
                "\t\t}",
                "\t\tcontinue;",
                "\t}",
                f"\tlevel.zmf_q_open_{k} = 0;",
            ]
        if self.ordered:
            # A repeat hit on a target already credited (a burst, automatic
            # fire, a shotgun's pellets) is not a wrong target: ignore it
            # rather than reset the sequence.
            lines += ["\tif ( j < n_tgt )", "\t{", "\t\tcontinue;", "\t}"]
            lines += ["\tif ( j != n_tgt )", "\t{"]
            if self.wrong:
                wrong, _ = s("wrong")
                lines += [
                    "\t\tif ( !isdefined( e_who.zmf_q_wrong ) || gettime() > e_who.zmf_q_wrong )",
                    "\t\t{",
                    "\t\t\te_who.zmf_q_wrong = gettime() + 1500;",
                    f'\t\t\te_who IPrintLnBold( &"{wrong}" );',
                    "\t\t}",
                    "\t\tif ( n_done > 0 )",
                    "\t\t{",
                    "\t\t\tn_done = 0;",
                    "\t\t\tn_tgt = 0;",
                    "\t\t\tn_hit = 0;",
                    f"\t\t\tlevel.zmf_q_next_{k} = 0;",
                    f"\t\t\tzmf_quest_progress( {i}, 0 );",
                    *(("\t\t\t" + x for x in (
                        f'level notify( "zmf_q_tstop_{k}" );',
                        f"level.zmf_q_ton_{k} = 0;",
                        f"zmf_quest_timer_hide_{k}();")) if timed else ()),
                    *("\t\t\t" + x for x in self._cue(s, "0")),
                    "\t\t}",
                    *("\t\t" + x for x in self._cue(s, "n_tgt", wrong=True)),
                ]
            lines += [
                "\t\tcontinue;",
                "\t}",
                "\tn_hit++;",
                f"\tif ( n_hit >= {self.hits} )",
                "\t{",
                "\t\tn_hit = 0;",
                "\t\tn_tgt++;",
                f"\t\tlevel.zmf_q_next_{k} = n_tgt;",
                *("\t\t" + x for x in self._cue(s, "n_tgt")),
                "\t}",
            ]
        else:
            lines += [
                f"\tif ( level.zmf_q_hits_{k}[ j ] >= {self.hits} )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
            ]
        lines += [
            f"\tlevel.zmf_q_hits_{k}[ j ]++;",
            "\tn_done++;",
            f"\tzmf_quest_progress( {i}, n_done );",
            *_when(f"n_done < {self.total}",
                   _advance(self, s, "n_done") + (_timer_start(self) if timed else []), 1),
            "}",
            f'level notify( "{end}" );',
        ]
        if timed:
            lines.append(f"zmf_quest_timer_hide_{k}();")
        if self.flash and self.flash.countdown:
            lines.append(f"zmf_quest_flash_hide_{k}();")
        for j, t in enumerate(self.targets):
            if t.model:
                lines.append(f"e_mdl_{j} delete();")
        # an empty advance block leaves "{ }" -- harmless, but keep it tidy
        return [x for x in lines]

    def _flash_functions(self, s) -> list[CustomFunction]:
        """The flash with its optional countdown, screen flash and early line.

        Phases in ``level.zmf_q_phase_<key>`` (the step's hit loop reads
        them to say "too early" or "too late"): 0 before the first flash,
        1 counting down, 2 open, 3 shut, 4 taken this flash."""
        k, f = self.key, self.flash
        flash, _ = s("flash")
        ph = f"level.zmf_q_phase_{k}"
        near = f"DistanceSquared( a_players[ i ].origin, v_at ) < {f.heard * f.heard:g}"
        loop = [
            'level endon( "end_game" );',
            f'level endon( "zmf_q_end_{k}" );',
            f"{ph} = 0;",
        ]
        if f.countdown:
            loop.append(f"level thread zmf_quest_flash_bye_{k}();")
        loop += ["while ( true )", "{",
                 f"\twait RandomFloatRange( {f.every[0]:g}, {f.every[1]:g} );",
                 # The flash comes at random, so it waits out a live ticket
                 # call instead of counting down over it.
                 "\twhile ( isdefined( level.zmf_ticket_calling ) && level.zmf_ticket_calling )",
                 "\t{",
                 "\t\twait 0.5;",
                 "\t}"]
        if f.countdown:
            count, _ = s("count")
            loop += [
                f"\t{ph} = 1;",
                # The countdown and the open window own the centre of the
                # screen: gag lines (gags.gag_say) wait until they are over.
                f"\tlevel.zmf_gag_hush = gettime() + {_ms(f.countdown + f.open + QUEST_HUSH)};",
                f"\tfor ( n = {int(f.countdown)}; n > 0; n-- )",
                "\t{",
                *([f'\t\tPlayFX( level._effect[ "{f.count_fx}" ], v_at );'] if f.count_fx else []),
                f'\t\tzmf_quest_flash_hud_{k}( v_at, &"{count}", n );',
                "\t\twait 1;",
                "\t}",
            ]
        loop += [
            f"\tlevel.zmf_q_open_{k} = gettime() + {_ms(f.open)};",
            f"\t{ph} = 2;",
            f'\tPlayFX( level._effect[ "{f.fx}" ], v_at );',
            "\ta_players = getplayers();",
            "\tfor ( i = 0; i < a_players.size; i++ )",
            "\t{",
            f"\t\tif ( {near} )",
            "\t\t{",
        ]
        if f.screen:
            # On the player, not on level: lui_shared.gsc:434-439 fans a
            # level-scoped call out to everyone on the map.
            loop.append('\t\t\ta_players[ i ] thread lui::screen_flash( 0.05, 0.2, 0.6, 0.7, "white" );')
        if not f.countdown:
            loop.append(f'\t\t\ta_players[ i ] IPrintLnBold( &"{flash}" );')
        loop += ["\t\t}", "\t}"]
        if f.countdown:
            # The open window in half seconds, redrawn so a player who walks
            # in mid-window sees it, and gone the moment the photo is taken.
            halves = max(1, int(round(f.open * 2)))
            loop += [
                f"\tfor ( n = 0; n < {halves}; n++ )",
                "\t{",
                f"\t\tif ( {ph} == 2 )",
                "\t\t{",
                f'\t\t\tzmf_quest_flash_hud_{k}( v_at, &"{flash}", 0 );',
                "\t\t}",
                "\t\twait 0.5;",
                "\t}",
                f"\tzmf_quest_flash_hide_{k}();",
            ]
        else:
            loop.append(f"\twait {f.open:g};")
        loop += [f"\t{ph} = 3;", "}"]
        out = [CustomFunction(
            f"zmf_quest_flash_{k}", tuple(loop), params=("v_at",),
            purpose=(f"{k}: " + (f"a {f.countdown}s countdown, then " if f.countdown else "")
                     + f"the target flashes (PlayFX, _zm_powerups.gsc:925) and is\n"
                     f"live for {f.open:g}s; players within {f.heard:g} are told"
                     + (" and see a white flash\n(lui::screen_flash, lui_shared.gsc:432)."
                        if f.screen else ".")),
        )]
        if not f.countdown:
            return out
        cd = f"zmf_q_cd_{k}"
        out += [
            CustomFunction(
                f"zmf_quest_flash_hud_{k}",
                (
                    "a_players = getplayers();",
                    "for ( i = 0; i < a_players.size; i++ )",
                    "{",
                    "\te_p = a_players[ i ];",
                    f"\tif ( !( {near} ) )",
                    "\t{",
                    f"\t\tif ( isdefined( e_p.{cd} ) )",
                    "\t\t{",
                    f"\t\t\te_p.{cd} destroy();",
                    f"\t\t\te_p.{cd} = undefined;",
                    "\t\t}",
                    "\t\tcontinue;",
                    "\t}",
                    f"\tif ( !isdefined( e_p.{cd} ) )",
                    "\t{",
                    "\t\te_hud = NewClientHudElem( e_p );",
                    '\t\te_hud.font = "objective";',
                    '\t\te_hud.alignX = "center";',
                    '\t\te_hud.alignY = "middle";',
                    '\t\te_hud.horzAlign = "center";',
                    '\t\te_hud.vertAlign = "middle";',
                    "\t\te_hud.y = -110;",
                    "\t\te_hud.foreground = true;",
                    "\t\te_hud.fontScale = 2;",
                    "\t\te_hud.alpha = 1;",
                    "\t\te_hud.color = ( 1, 0.9, 0.3 );",
                    "\t\te_hud.hidewheninmenu = true;",
                    f"\t\te_p.{cd} = e_hud;",
                    "\t}",
                    "\tif ( n > 0 )",
                    "\t{",
                    f"\t\te_p.{cd} SetText( str_line, n );",
                    "\t}",
                    "\telse",
                    "\t{",
                    f"\t\te_p.{cd} SetText( str_line );",
                    "\t}",
                    "}",
                ),
                params=("v_at", "str_line", "n"),
                purpose=(f"{k}: the countdown / flash line, centre screen, on every player\n"
                         f"within {f.heard:g} (and off anyone who left).  NewClientHudElem:\n"
                         "teamgather_shared.gsc:811-827; centre/middle alignment:\n"
                         "zm/_zm.gsc:6070-6073; destroy(): _zm_laststand.gsc:448."),
            ),
            CustomFunction(
                f"zmf_quest_flash_hide_{k}",
                (
                    "a_players = getplayers();",
                    "for ( i = 0; i < a_players.size; i++ )",
                    "{",
                    f"\tif ( isdefined( a_players[ i ].{cd} ) )",
                    "\t{",
                    f"\t\ta_players[ i ].{cd} destroy();",
                    f"\t\ta_players[ i ].{cd} = undefined;",
                    "\t}",
                    "}",
                ),
                purpose=f"{k}: the countdown line off every screen.",
            ),
            CustomFunction(
                f"zmf_quest_flash_bye_{k}",
                (
                    f'level endon( "zmf_q_end_{k}" );',
                    'level waittill( "end_game" );',
                    f"zmf_quest_flash_hide_{k}();",
                ),
                purpose=f"{k}: no countdown left over the end screen.",
            ),
        ]
        return out

    def extra(self, i, s):
        k = self.key
        out = []
        if self.flash and (self.flash.early or self.flash.countdown or self.flash.screen):
            out += self._flash_functions(s)
        elif self.flash:
            flash, _ = s("flash")
            f = self.flash
            out.append(CustomFunction(
                f"zmf_quest_flash_{k}",
                (
                    'level endon( "end_game" );',
                    f'level endon( "zmf_q_end_{k}" );',
                    "while ( true )",
                    "{",
                    f"\twait RandomFloatRange( {f.every[0]:g}, {f.every[1]:g} );",
                    f"\tlevel.zmf_q_open_{k} = gettime() + {_ms(f.open)};",
                    f'\tPlayFX( level._effect[ "{f.fx}" ], v_at );',
                    "\ta_players = getplayers();",
                    "\tfor ( i = 0; i < a_players.size; i++ )",
                    "\t{",
                    f"\t\tif ( DistanceSquared( a_players[ i ].origin, v_at ) < {f.heard * f.heard:g} )",
                    "\t\t{",
                    f'\t\t\ta_players[ i ] IPrintLnBold( &"{flash}" );',
                    "\t\t}",
                    "\t}",
                    "}",
                ),
                params=("v_at",),
                purpose=(f"{k}: the target flashes (PlayFX, _zm_powerups.gsc:925) and is\n"
                         f"live for {f.open:g}s; nearby players are told."),
            ))
        if self.pulse_fx:
            which = ("level.zmf_q_hits_%s[ j ] < %d" % (k, self.hits)) if not self.ordered \
                else f"j == level.zmf_q_next_{k}"
            out.append(CustomFunction(
                f"zmf_quest_pulse_{k}",
                (
                    'level endon( "end_game" );',
                    f'level endon( "zmf_q_end_{k}" );',
                    "while ( true )",
                    "{",
                    "\tfor ( j = 0; j < a_pts.size; j++ )",
                    "\t{",
                    f"\t\tif ( {which} )",
                    "\t\t{",
                    f'\t\t\tPlayFX( level._effect[ "{self.pulse_fx}" ], a_pts[ j ] );',
                    "\t\t}",
                    "\t}",
                    "\twait 2.5;",
                    "}",
                ),
                params=("a_pts",),
                purpose=f"{k}: a pulse on the target(s) still to hit.",
            ))
        if self.time_limit is not None:
            out += _timer_functions(self, s, f"zmf_q_hit_{k}")
        return out


@dataclass(frozen=True, kw_only=True)
class CollectDeliver(Step):
    """Pick up every item and hand them in at ``deliver_at``.

    Items are carried by the player who took them.  If that player goes
    down (last stand), bleeds out (``sessionstate == "spectator"``) or
    leaves, each item they held goes back to where it was and ``dropped``
    (optional) is said to everyone (Q2: a carried form or shovel never
    leaves the step unfinishable).
    Handing in files everything the player carries at once; ``empty`` is
    said to a player who uses the desk with nothing.

    ``deliver=False`` is a plain collect: picking an item up counts at once
    (``advance`` is said, the step ends when the last is taken), there is no
    desk (``deliver_at``, ``deliver_prompt`` and ``empty`` stay unset),
    nothing is carried so nothing drops, and it takes no ``time_limit``."""

    items: tuple[Item, ...]
    pickup_prompt: str
    deliver_at: tuple[float, float, float] | None = None
    deliver_prompt: str | None = None
    empty: str | None = None
    deliver: bool = True
    dropped: str | None = None
    pulse_fx: str | None = "powerup_grabbed"
    radius: float = 44.0
    height: float = 72.0

    _TIMED = True

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if not self.items:
            raise ValueError(f"{self.key}: nothing to collect")
        desk = (self.deliver_at, self.deliver_prompt, self.empty)
        if self.deliver and any(x is None for x in desk):
            raise ValueError(f"{self.key}: a delivery needs deliver_at, deliver_prompt and empty")
        if not self.deliver:
            if any(x is not None for x in desk) or self.dropped:
                raise ValueError(f"{self.key}: a plain collect has no desk and drops nothing")
            if self.time_limit is not None:
                raise ValueError(f"{self.key}: a plain collect takes no time_limit")
        if self.pulse_fx is not None and self.pulse_fx not in BOSS_FX:
            raise ValueError(f"{self.pulse_fx!r} is not a stock effect name")

    @property
    def total(self) -> int:
        return len(self.items)

    def lines(self):
        out = Step.lines(self)
        out["pickup_prompt"] = (self.pickup_prompt, "triggerstring")
        if self.deliver:
            out["deliver_prompt"] = (self.deliver_prompt, "triggerstring")
            out["empty"] = (self.empty, "string")
        if self.dropped:
            out["dropped"] = (self.dropped, "string")
        for j, item in enumerate(self.items):
            out[f"picked{j}"] = (item.picked, "string")
        return out

    def assets(self):
        return tuple(("xmodel", it.model) for it in self.items if it.model)

    def use_points(self):
        return [it.point for it in self.items] + ([self.deliver_at] if self.deliver else [])

    def _spawn_items(self, s) -> list[str]:
        k = self.key
        pick, _ = s("pickup_prompt")
        out = []
        for j, it in enumerate(self.items):
            picked, _ = s(f"picked{j}")
            model = f'"{it.model}"' if it.model else "undefined"
            out.append(
                f'level thread zmf_quest_item_{k}( {j}, {_vector(it.point)}, {float(it.yaw):g}, '
                f'{model}, &"{pick}", &"{picked}" );'
            )
        return out

    def body(self, i, s):
        k = self.key
        lines = [
            f"level.zmf_q_n[ {i} ] = 0;",
        ]
        if self.time_limit is None:
            lines += self._spawn_items(s)
        else:
            lines += [f"level.zmf_q_it_{k} = [];", f"level.zmf_q_im_{k} = [];",
                      *_timer_init(self), f"zmf_quest_items_{k}();"]
        if not self.deliver:
            # A plain collect: each item thread counts its own pickup.
            return lines + [
                f"while ( level.zmf_q_n[ {i} ] < {self.total} )",
                "{",
                f'\tlevel waittill( "zmf_q_filed_{k}" );',
                "}",
                f'level notify( "zmf_q_end_{k}" );',
            ]
        deliver, _ = s("deliver_prompt")
        lines += [
            # The step owns the desk's trigger: the desk thread ends on the
            # step's end notify (P12) and the step then takes the desk away.
            f't_desk = spawn( "trigger_radius_use", {_vector(self.deliver_at)}, 0, '
            f"{self.radius:g}, {self.height:g} );",
            "t_desk TriggerIgnoreTeam();",
            "t_desk SetVisibleToAll();",
            't_desk SetTeamForTrigger( "none" );',
            't_desk SetCursorHint( "HINT_NOICON" );',
            f't_desk SetHintString( &"{deliver}" );',
            f"level thread zmf_quest_desk_{k}( t_desk );",
            f"while ( level.zmf_q_n[ {i} ] < {self.total} )",
            "{",
            f'\tlevel waittill( "zmf_q_filed_{k}" );',
        ]
        if self.time_limit is not None:
            # Out of time (and not filed in the same moment): every form back.
            lines += [
                f"\tif ( level.zmf_q_tout_{k} && level.zmf_q_n[ {i} ] < {self.total} )",
                "\t{",
                f"\t\tlevel.zmf_q_tout_{k} = 0;",
                f"\t\tzmf_quest_reset_{k}();",
                "\t}",
            ]
        lines += [
            "}",
            f'level notify( "zmf_q_end_{k}" );',
            "t_desk delete();",
        ]
        if self.time_limit is not None:
            lines.append(f"zmf_quest_timer_hide_{k}();")
        return lines

    def extra(self, i, s):
        k = self.key
        timed = self.time_limit is not None
        if not self.deliver:
            return [self._collect_item(i, s)]
        empty, _ = s("empty")
        drop = []
        if self.dropped:
            ref, _ = s("dropped")
            drop = [f'\t\tzmf_quest_all_0( &"{ref}" );']
        pulse = ([f'\tlevel thread zmf_quest_item_pulse( t_item, v_at, "{self.pulse_fx}" );']
                 if self.pulse_fx else [])
        item = CustomFunction(
            f"zmf_quest_item_{k}",
            (
                'level endon( "end_game" );',
                f'level endon( "zmf_q_end_{k}" );',
                *([f'level endon( "zmf_q_reset_{k}" );'] if timed else []),
                "while ( true )",
                "{",
                "\te_model = undefined;",
                "\tif ( isdefined( str_model ) )",
                "\t{",
                '\t\te_model = spawn( "script_model", v_at );',
                "\t\te_model SetModel( str_model );",
                "\t\te_model.angles = ( 0, n_yaw, 0 );",
                "\t}",
                f'\tt_item = spawn( "trigger_radius_use", v_at, 0, {self.radius:g}, {self.height:g} );',
                "\tt_item TriggerIgnoreTeam();",
                "\tt_item SetVisibleToAll();",
                '\tt_item SetTeamForTrigger( "none" );',
                '\tt_item SetCursorHint( "HINT_NOICON" );',
                "\tt_item SetHintString( str_prompt );",
                *([f"\tlevel.zmf_q_it_{k}[ n_item ] = t_item;",
                   f"\tlevel.zmf_q_im_{k}[ n_item ] = e_model;"] if timed else []),
                *pulse,
                "\twhile ( true )",
                "\t{",
                '\t\tt_item waittill( "trigger", e_who );',
                "\t\tif ( isplayer( e_who ) && !e_who laststand::player_is_in_laststand() )",
                "\t\t{",
                "\t\t\tbreak;",
                "\t\t}",
                "\t}",
                "\tt_item delete();",
                "\tif ( isdefined( e_model ) )",
                "\t{",
                "\t\te_model delete();",
                "\t}",
                "\tif ( !isdefined( e_who.zmf_q_bag ) )",
                "\t{",
                "\t\te_who.zmf_q_bag = [];",
                "\t\te_who.zmf_q_sent = [];",
                "\t}",
                f"\tif ( !isdefined( e_who.zmf_q_bag[ {i} ] ) )",
                "\t{",
                f"\t\te_who.zmf_q_bag[ {i} ] = 0;",
                f"\t\te_who.zmf_q_sent[ {i} ] = 0;",
                "\t}",
                f"\te_who.zmf_q_bag[ {i} ]++;",
                f"\tn_sent = e_who.zmf_q_sent[ {i} ];",
                "\te_who IPrintLnBold( str_picked );",
                *(("\t" + x for x in _timer_start(self)) if timed else ()),
                "\twhile ( true )",
                "\t{",
                "\t\twait 0.25;",
                "\t\tif ( !isdefined( e_who ) )",
                "\t\t{",
                "\t\t\tbreak;",
                "\t\t}",
                f"\t\tif ( e_who.zmf_q_sent[ {i} ] > n_sent )",
                "\t\t{",
                "\t\t\treturn;",
                "\t\t}",
                # Down, bled out or gone: the item goes back to its spot,
                # not into a revive or a spectator's pocket (Q2).
                '\t\tif ( e_who.sessionstate == "spectator" || e_who laststand::player_is_in_laststand() )',
                "\t\t{",
                f"\t\t\te_who.zmf_q_bag[ {i} ]--;",
                "\t\t\tbreak;",
                "\t\t}",
                "\t}",
                *drop,
                "}",
            ),
            params=("n_item", "v_at", "n_yaw", "str_model", "str_prompt", "str_picked"),
            purpose=(f"{k}: one item. Taken into the taker's bag; back on its spot if\n"
                     "they go down (last stand), bleed out (sessionstate spectator,\n"
                     "_zm.gsc:1783) or leave."),
        )
        # The pulse helper is shared by every CollectDeliver step.
        desk = CustomFunction(
            f"zmf_quest_desk_{k}",
            (
                'level endon( "end_game" );',
                f'level endon( "zmf_q_end_{k}" );',
                "while ( true )",
                "{",
                '\tt_desk waittill( "trigger", e_who );',
                "\tif ( !isplayer( e_who ) )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\tif ( isdefined( e_who.zmf_q_desk ) && gettime() < e_who.zmf_q_desk )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\te_who.zmf_q_desk = gettime() + 1000;",
                f"\tif ( !isdefined( e_who.zmf_q_bag ) || !isdefined( e_who.zmf_q_bag[ {i} ] ) "
                f"|| e_who.zmf_q_bag[ {i} ] < 1 )",
                "\t{",
                f'\t\te_who IPrintLnBold( &"{empty}" );',
                "\t\tcontinue;",
                "\t}",
                f"\tn = level.zmf_q_n[ {i} ] + e_who.zmf_q_bag[ {i} ];",
                f"\te_who.zmf_q_bag[ {i} ] = 0;",
                f"\te_who.zmf_q_sent[ {i} ]++;",
                f"\tzmf_quest_progress( {i}, n );",
                *_when(f"n < {self.total}", _advance(self, s, "n"), 1),
                f'\tlevel notify( "zmf_q_filed_{k}" );',
                "}",
            ),
            params=("t_desk",),
            purpose=f"{k}: the desk. Files everything the player carries, at once; ends with the step.",
        )
        if not timed:
            return [item, desk]
        n = len(self.items)
        return [item, desk, CustomFunction(
            f"zmf_quest_items_{k}", tuple(self._spawn_items(s)),
            purpose=f"{k}: every item on the floor where it starts.",
        ), CustomFunction(
            f"zmf_quest_reset_{k}",
            (
                # The item threads end first, so none puts its item back.
                f'level notify( "zmf_q_reset_{k}" );',
                f"for ( j = 0; j < {n}; j++ )",
                "{",
                f"\tif ( isdefined( level.zmf_q_it_{k}[ j ] ) )",
                "\t{",
                f"\t\tlevel.zmf_q_it_{k}[ j ] delete();",
                "\t}",
                f"\tif ( isdefined( level.zmf_q_im_{k}[ j ] ) )",
                "\t{",
                f"\t\tlevel.zmf_q_im_{k}[ j ] delete();",
                "\t}",
                "}",
                f"level.zmf_q_it_{k} = [];",
                f"level.zmf_q_im_{k} = [];",
                "a_players = getplayers();",
                "for ( j = 0; j < a_players.size; j++ )",
                "{",
                f"\tif ( isdefined( a_players[ j ].zmf_q_bag ) && isdefined( a_players[ j ].zmf_q_bag[ {i} ] ) )",
                "\t{",
                f"\t\ta_players[ j ].zmf_q_bag[ {i} ] = 0;",
                "\t}",
                "}",
                f"zmf_quest_progress( {i}, 0 );",
                *_say(s, "timeout"),
                f"zmf_quest_items_{k}();",
            ),
            purpose=(f"{k}: out of time. Every item still on the floor and every one carried\n"
                     "goes back to its spot, every bag is emptied, the count is 0."),
        ), *_timer_functions(self, s, f"zmf_q_filed_{k}")]

    def _collect_item(self, i, s) -> CustomFunction:
        """``deliver=False``: one item; taking it counts for the step at once."""
        k = self.key
        pulse = ([f'level thread zmf_quest_item_pulse( t_item, v_at, "{self.pulse_fx}" );']
                 if self.pulse_fx else [])
        return CustomFunction(
            f"zmf_quest_item_{k}",
            (
                'level endon( "end_game" );',
                f'level endon( "zmf_q_end_{k}" );',
                "e_model = undefined;",
                "if ( isdefined( str_model ) )",
                "{",
                '\te_model = spawn( "script_model", v_at );',
                "\te_model SetModel( str_model );",
                "\te_model.angles = ( 0, n_yaw, 0 );",
                "}",
                f't_item = spawn( "trigger_radius_use", v_at, 0, {self.radius:g}, {self.height:g} );',
                "t_item TriggerIgnoreTeam();",
                "t_item SetVisibleToAll();",
                't_item SetTeamForTrigger( "none" );',
                't_item SetCursorHint( "HINT_NOICON" );',
                "t_item SetHintString( str_prompt );",
                *pulse,
                "while ( true )",
                "{",
                '\tt_item waittill( "trigger", e_who );',
                "\tif ( isplayer( e_who ) && !e_who laststand::player_is_in_laststand() )",
                "\t{",
                "\t\tbreak;",
                "\t}",
                "}",
                "t_item delete();",
                "if ( isdefined( e_model ) )",
                "{",
                "\te_model delete();",
                "}",
                "e_who IPrintLnBold( str_picked );",
                f"n = level.zmf_q_n[ {i} ] + 1;",
                f"zmf_quest_progress( {i}, n );",
                *_when(f"n < {self.total}", _advance(self, s, "n"), 0),
                f'level notify( "zmf_q_filed_{k}" );',
            ),
            params=("n_item", "v_at", "n_yaw", "str_model", "str_prompt", "str_picked"),
            purpose=f"{k}: one item. Taking it counts for the step at once (no desk).",
        )

    def using(self):
        return (_LASTSTAND,)


@dataclass(frozen=True, kw_only=True)
class KillInZone(Step):
    """Kill ``count`` zombies within ``radius`` (and ``height``) of ``point``
    while the step is live.  ``advance`` is said every ``announce_every``
    kills."""

    point: tuple[float, float, float]
    count: int
    radius: float = 300.0
    height: float = 160.0
    announce_every: int = 5
    pulse_fx: str | None = None

    _HOLDS = True

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if self.count < 1:
            raise ValueError(f"{self.key}: count >= 1")

    @property
    def total(self) -> int:
        return self.count

    def using(self):
        return (_SPAWNER,)

    def body(self, i, s):
        k = self.key
        lines = [
            f"level.zmf_q_live_{k} = 1;",
            f"zm_spawner::register_zombie_death_event_callback( &zmf_quest_kill_{k} );",
        ]
        if self.pulse_fx:
            lines.append(f"level thread zmf_quest_zone_pulse( {_vector(self.point)}, "
                         f'"{self.pulse_fx}", "zmf_q_end_{k}" );')
        lines += [
            f"while ( level.zmf_q_n[ {i} ] < {self.count} )",
            "{",
            f'\tlevel waittill( "zmf_q_kill_{k}" );',
            "}",
            f"level.zmf_q_live_{k} = 0;",
            f'level notify( "zmf_q_end_{k}" );',
        ]
        return lines

    def extra(self, i, s):
        k = self.key
        v = _vector(self.point)
        adv = _advance(self, s, "n")
        return [CustomFunction(
            f"zmf_quest_kill_{k}",
            (
                f"if ( !isdefined( level.zmf_q_live_{k} ) || level.zmf_q_live_{k} != 1 )",
                "{",
                "\treturn;",
                "}",
                f"if ( Distance2DSquared( self.origin, {v} ) > {self.radius * self.radius:g} )",
                "{",
                "\treturn;",
                "}",
                f"if ( abs( self.origin[ 2 ] - {float(self.point[2]):g} ) > {self.height:g} )",
                "{",
                "\treturn;",
                "}",
                f"n = level.zmf_q_n[ {i} ] + 1;",
                f"zmf_quest_progress( {i}, n );",
                *_when(f"n < {self.count} && n % {max(1, int(self.announce_every))} == 0", adv, 0),
                f'level notify( "zmf_q_kill_{k}" );',
            ),
            params=("e_attacker",),
            purpose=(f"{k}: counts a zombie that died in the zone. A death callback\n"
                     "(register_zombie_death_event_callback, _zm_spawner.gsc:2463),\n"
                     "called on the zombie with its attacker (:2458). Never waits."),
        )]


@dataclass(frozen=True, kw_only=True)
class Vessel:
    """One soul box of a :class:`SoulBox` step.

    ``point`` is where the vessel stands (its base on the floor); the souls
    fly to ``mouth`` units above it.  ``model`` (a declared ``xmodel``) is
    spawned there as a ``script_model`` for the step, turned to ``yaw`` and
    scaled to ``scale``; as the vessel fills it grows linearly to
    ``full_scale`` (``None``: it keeps its size) and climbs from ``rise``
    units below ``point`` up to it (``0``: it stays put).  It stays where it
    ended when the step is done (a fed pumpkin, a risen headstone).  With no
    model the vessel is only its glow and the map's own geometry."""

    point: tuple[float, float, float]
    model: str | None = None
    yaw: float = 0.0
    scale: float = 1.0
    full_scale: float | None = None
    rise: float = 0.0
    mouth: float = 32.0

    def __post_init__(self) -> None:
        if self.scale <= 0 or (self.full_scale is not None and self.full_scale <= 0):
            raise ValueError("a vessel's scale is > 0")
        if self.rise < 0:
            raise ValueError("a vessel's rise is >= 0 (units below its point it starts at)")
        if self.model is None and (self.full_scale is not None or self.rise):
            raise ValueError("a vessel with no model cannot grow or rise")


@dataclass(frozen=True, kw_only=True)
class SoulBox(Step):
    """Feed souls to one or more vessels (the Origins soul chests, the Der
    Eisendrache wolf heads): a zombie a player kills within ``radius`` (and
    ``height``) of a hungry vessel sends its soul there, and the step is done
    when every vessel is full.  A soul goes to the nearest vessel that still
    wants one.

    **How many.**  Each vessel wants ``souls`` plus ``per_extra_player`` for
    every connected player past the first, counted when the step opens
    (``getplayers()``: a downed or bled-out player still counts, so nothing
    changes when someone dies); if a player leaves the game the need is
    lowered for the rest, never raised.  The HUD's task line gets the souls
    fed (``&&1``) and the souls wanted over all vessels (``&&2``);
    ``advance`` (optional) is said every ``announce_every`` souls with the
    same two, and ``full`` (optional, several vessels) when one vessel
    fills, with the full vessels as ``&&1`` and the vessel count as ``&&2``.
    Only a player's kill counts (``isplayer`` on the attacker): a zombie
    the round cleans up, a trap with no owner or a map gag is no soul.
    Nothing is reset: not by a death, a down, a special round, or the step
    being slow.

    **What the player sees.**  While a vessel is hungry, ``glow_fx`` loops on
    a ``tag_origin`` at its mouth.  Each soul is a ``tag_origin`` with
    ``orb_fx`` looping on it that flies from the zombie's chest to the mouth
    (``MoveTo`` at about 450 units a second, 0.5-2 s), then ``arrive_fx``
    bursts there, ``sound`` plays on the vessel and the vessel jolts, grows
    and rises by its share.  At most ``max_orbs`` souls fly at once (a nuke
    kill of twenty zombies shows twelve; every one still counts).  A full
    vessel bursts ``full_fx`` three times and its glow goes out (P12).

    **Evidence.**  The soul flight is the stock Grief-mode "soul firework"
    (``zm/_zm_game_module.gsc:272-295``: a ``tag_origin`` script_model,
    ``util::wait_network_frame``, ``PlayFXOnTag`` on ``"tag_origin"``,
    ``playloopsound( "zmb_souls_loop" )``, ``MoveTo`` at ``dist / 700``,
    ``waittill( "movedone" )``, ``playsound( "zmb_souls_end" )``, a burst
    and ``delete``).  The zm_tomb and zm_castle soul chest scripts are not
    among the mod tools' raw scripts, so nothing else is borrowed.  Effects
    are the stock powerup set (:data:`zmforge.script.bosses.BOSS_FX`,
    ``zm/_zm_powerups.gsc:80-91``), which every zombies map precaches; the
    looping ones only ever on a tag (:data:`zmforge.script.glow.LOOPING_FX`).
    Kills: ``zm_spawner::register_zombie_death_event_callback``
    (``zm/_zm_spawner.gsc:2463``, called on the zombie with the attacker,
    ``:2458``).  ``SetScale``: ``shared/ai/archetype_robot.gsc:3520``.

    **Unverified in play:** that a soul orb reads as a soul at night, that
    ``zmb_souls_end`` is in a usermap's sound banks (no alias file for it
    ships with the mod tools; a missing alias is silent), and how large a
    ``SetScale`` a prop takes before it looks wrong."""

    vessels: tuple[Vessel, ...]
    souls: int = 15
    per_extra_player: int = 8
    radius: float = 400.0
    height: float = 200.0
    glow_fx: str | None = "powerup_on_solo"
    orb_fx: str = "powerup_on_solo"
    arrive_fx: str = "powerup_grabbed_solo"
    full_fx: str = "powerup_grabbed"
    sound: str | None = "zmb_souls_end"
    full: str | None = None
    announce_every: int = 5
    max_orbs: int = 12

    _HOLDS = True

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if not self.vessels:
            raise ValueError(f"{self.key}: a soul box step needs a vessel")
        if self.souls < 1 or self.per_extra_player < 0:
            raise ValueError(f"{self.key}: souls >= 1 and per_extra_player >= 0")
        if self.radius <= 0 or self.height <= 0 or self.max_orbs < 1:
            raise ValueError(f"{self.key}: radius, height and max_orbs > 0")
        for fx in (self.glow_fx, self.orb_fx):
            # Looping: only ever on a tag that is deleted (glow.LOOPING_FX).
            if fx is not None and (fx not in LOOPING_FX or fx not in BOSS_FX):
                raise ValueError(f"{self.key}: {fx!r} is not a stock looping powerup effect")
        for fx in (self.arrive_fx, self.full_fx):
            # One-shot: PlayFX at a point has no handle, so never a loop.
            if fx not in BOSS_FX or fx in LOOPING_FX:
                raise ValueError(f"{self.key}: {fx!r} is not a stock one-shot powerup effect")
        if self.sound is not None and not re.fullmatch(r"[a-z0-9_]+", self.sound):
            raise ValueError(f"{self.key}: sound alias {self.sound!r}")
        if self.full is not None and len(self.vessels) < 2:
            raise ValueError(f"{self.key}: the 'full' line is for several vessels")

    @property
    def total(self) -> int:
        # The solo total; the body sets level.zmf_q_of[ i ] for the players.
        return int(self.souls) * len(self.vessels)

    def lines(self):
        out = Step.lines(self)
        if self.full:
            out["full"] = (self.full, "string")
        return out

    def assets(self):
        return tuple(dict.fromkeys(("xmodel", v.model) for v in self.vessels if v.model))

    def using(self):
        return (_SPAWNER,)

    def body(self, i, s):
        k = self.key
        n_v = len(self.vessels)
        lines = [
            # The need, for the players connected now (a bled-out player is
            # still connected: dying changes nothing).
            f"n_players = getplayers().size;",
            "if ( n_players < 1 )",
            "{",
            "\tn_players = 1;",
            "}",
            f"level.zmf_q_need_{k} = {int(self.souls)} + {int(self.per_extra_player)} * ( n_players - 1 );",
            f"level.zmf_q_of[ {i} ] = level.zmf_q_need_{k} * {n_v};",
            f"zmf_quest_progress( {i}, 0 );",
            f"level.zmf_q_at_{k} = [];",
            f"level.zmf_q_mouth_{k} = [];",
            f"level.zmf_q_fill_{k} = [];",
            f"level.zmf_q_full_{k} = [];",
            f"level.zmf_q_box_{k} = [];",
            f"level.zmf_q_glow_{k} = [];",
            f"level.zmf_q_orbs_{k} = 0;",
        ]
        for j, v in enumerate(self.vessels):
            x, y, z = (float(c) for c in v.point)
            lines += [
                f"level.zmf_q_at_{k}[ {j} ] = {_vector((x, y, z))};",
                f"level.zmf_q_mouth_{k}[ {j} ] = {_vector((x, y, z + v.mouth))};",
                f"level.zmf_q_fill_{k}[ {j} ] = 0;",
                f"level.zmf_q_full_{k}[ {j} ] = 0;",
            ]
            if v.model:
                lines += [
                    f'e_box = spawn( "script_model", {_vector((x, y, z - v.rise))} );',
                    f'e_box SetModel( "{v.model}" );',
                    f"e_box.angles = ( 0, {float(v.yaw):g}, 0 );",
                    *([f"e_box SetScale( {float(v.scale):g} );"] if v.scale != 1.0 else []),
                    f"level.zmf_q_box_{k}[ {j} ] = e_box;",
                ]
            if self.glow_fx:
                lines += [*tag_glow_lines("e_glow", _vector((x, y, z + v.mouth)), self.glow_fx),
                          f"level.zmf_q_glow_{k}[ {j} ] = e_glow;"]
        lines += [
            f"level.zmf_q_live_{k} = 1;",
            f"zm_spawner::register_zombie_death_event_callback( &zmf_quest_soul_kill_{k} );",
            f"while ( level.zmf_q_n[ {i} ] < level.zmf_q_of[ {i} ] )",
            "{",
            "\twait 1;",
            # A player who left lowers the need for the rest; never raised.
            "\tn_now = getplayers().size;",
            "\tif ( n_now < n_players && n_now > 0 )",
            "\t{",
            "\t\tn_players = n_now;",
            f"\t\tlevel.zmf_q_need_{k} = {int(self.souls)} + {int(self.per_extra_player)} * ( n_players - 1 );",
            f"\t\tlevel.zmf_q_of[ {i} ] = level.zmf_q_need_{k} * {n_v};",
            f"\t\tzmf_quest_progress( {i}, zmf_quest_soul_count_{k}() );",
            "\t}",
            "}",
            f"level.zmf_q_live_{k} = 0;",
            # The last souls land before the step says it is done.
            "wait 2.2;",
            f"for ( j = 0; j < {n_v}; j++ )",
            "{",
            f"\tzmf_quest_soul_full_{k}( j );",
            "}",
            f'level notify( "zmf_q_end_{k}" );',
        ]
        return lines

    def extra(self, i, s):
        k = self.key
        n_v = len(self.vessels)
        r2 = self.radius * self.radius
        adv = _say(s, "advance", "n", f"level.zmf_q_of[ {i} ]") if self.advance else []
        full_say = []
        if self.full:
            full_say = [
                "n_full = 0;",
                f"for ( m = 0; m < {n_v}; m++ )",
                "{",
                f"\tif ( level.zmf_q_full_{k}[ m ] )",
                "\t{",
                "\t\tn_full++;",
                "\t}",
                "}",
                *_when(f"n_full < {n_v}", _say(s, "full", "n_full", str(n_v)), 0),
            ]
        # Per-vessel growth and rise, unrolled (each vessel has its own).
        react = []
        for j, v in enumerate(self.vessels):
            if not v.model:
                continue
            x, y, z = (float(c) for c in v.point)
            body = []
            if self.sound:
                body.append(f'e_box playsound( "{self.sound}" );')
            if v.full_scale is not None and v.full_scale != v.scale:
                body.append(f"e_box SetScale( {float(v.scale):g} + "
                            f"{float(v.full_scale - v.scale):g} * n_f );")
            if v.rise:
                body.append(f"e_box MoveTo( ( {x:g}, {y:g}, {z - v.rise:g} + "
                            f"{float(v.rise):g} * n_f ), 0.3 );")
            body += [
                f"e_box RotateTo( ( randomfloatrange( -6, 6 ), {float(v.yaw):g}, "
                "randomfloatrange( -6, 6 ) ), 0.1 );",
                "wait 0.1;",
                "if ( isdefined( e_box ) )",
                "{",
                f"\te_box RotateTo( ( 0, {float(v.yaw):g}, 0 ), 0.2 );",
                "}",
            ]
            react += _when(f"j == {j}", body, 0)
        return [
            CustomFunction(
                f"zmf_quest_soul_kill_{k}",
                (
                    f"if ( !isdefined( level.zmf_q_live_{k} ) || level.zmf_q_live_{k} != 1 )",
                    "{",
                    "\treturn;",
                    "}",
                    "if ( !isdefined( e_attacker ) || !isplayer( e_attacker ) )",
                    "{",
                    "\treturn;",
                    "}",
                    "v_at = self.origin;",
                    "n_best = -1;",
                    f"n_d = {r2:g};",
                    f"for ( j = 0; j < {n_v}; j++ )",
                    "{",
                    f"\tif ( level.zmf_q_fill_{k}[ j ] >= level.zmf_q_need_{k} )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\tv_box = level.zmf_q_at_{k}[ j ];",
                    "\tn_dj = Distance2DSquared( v_at, v_box );",
                    f"\tif ( n_dj <= n_d && abs( v_at[ 2 ] - v_box[ 2 ] ) <= {self.height:g} )",
                    "\t{",
                    "\t\tn_best = j;",
                    "\t\tn_d = n_dj;",
                    "\t}",
                    "}",
                    "if ( n_best < 0 )",
                    "{",
                    "\treturn;",
                    "}",
                    f"level.zmf_q_fill_{k}[ n_best ]++;",
                    f"n = zmf_quest_soul_count_{k}();",
                    f"zmf_quest_progress( {i}, n );",
                    *_when(f"n < level.zmf_q_of[ {i} ] && n % "
                           f"{max(1, int(self.announce_every))} == 0", adv, 0),
                    f"level thread zmf_quest_soul_fly_{k}( v_at + ( 0, 0, 40 ), n_best );",
                ),
                params=("e_attacker",),
                purpose=(f"{k}: a zombie a player killed near a hungry vessel feeds it one soul.\n"
                         "A death callback (register_zombie_death_event_callback,\n"
                         "_zm_spawner.gsc:2463), on the zombie with its attacker (:2458).\n"
                         "Never waits: the flight is its own thread."),
            ),
            CustomFunction(
                f"zmf_quest_soul_count_{k}",
                (
                    "n = 0;",
                    f"for ( j = 0; j < {n_v}; j++ )",
                    "{",
                    f"\tn_j = level.zmf_q_fill_{k}[ j ];",
                    f"\tif ( n_j > level.zmf_q_need_{k} )",
                    "\t{",
                    f"\t\tn_j = level.zmf_q_need_{k};",
                    "\t}",
                    "\tn += n_j;",
                    "}",
                    "return n;",
                ),
                purpose=f"{k}: souls fed over every vessel, none counted past a vessel's need.",
            ),
            CustomFunction(
                f"zmf_quest_soul_fly_{k}",
                (
                    'level endon( "end_game" );',
                    f"v_to = level.zmf_q_mouth_{k}[ j ];",
                    f"if ( level.zmf_q_orbs_{k} < {int(self.max_orbs)} )",
                    "{",
                    f"\tlevel.zmf_q_orbs_{k}++;",
                    *("\t" + x for x in tag_glow_lines("e_orb", "v_from", self.orb_fx)[:2]),
                    # One frame before the effect goes on the new entity, as
                    # the stock soul firework waits a network frame
                    # (_zm_game_module.gsc:276).
                    "\twait 0.05;",
                    f'\tPlayFXOnTag( level._effect[ "{self.orb_fx}" ], e_orb, "tag_origin" );',
                    "\tn_t = Distance( v_from, v_to ) / 450;",
                    "\tif ( n_t < 0.5 )",
                    "\t{",
                    "\t\tn_t = 0.5;",
                    "\t}",
                    "\tif ( n_t > 2 )",
                    "\t{",
                    "\t\tn_t = 2;",
                    "\t}",
                    "\te_orb MoveTo( v_to, n_t );",
                    "\twait n_t;",
                    "\te_orb delete();",
                    f"\tlevel.zmf_q_orbs_{k}--;",
                    "}",
                    f'PlayFX( level._effect[ "{self.arrive_fx}" ], v_to );',
                    f"n_f = ( level.zmf_q_fill_{k}[ j ] * 1.0 ) / level.zmf_q_need_{k};",
                    "if ( n_f > 1 )",
                    "{",
                    "\tn_f = 1;",
                    "}",
                    *([f"e_box = level.zmf_q_box_{k}[ j ];",
                       "if ( isdefined( e_box ) )",
                       "{",
                       *("\t" + x for x in react),
                       "}"] if react else []),
                    f"if ( level.zmf_q_fill_{k}[ j ] >= level.zmf_q_need_{k} && !level.zmf_q_full_{k}[ j ] )",
                    "{",
                    f"\tzmf_quest_soul_full_{k}( j );",
                    *("\t" + x for x in full_say),
                    "}",
                ),
                params=("v_from", "j"),
                purpose=(f"{k}: one soul flies to vessel j and the vessel takes it. The stock\n"
                         "soul firework (_zm_game_module.gsc:272-295): a tag_origin with a\n"
                         "looping effect on its tag, MoveTo, a burst, delete."),
            ),
            CustomFunction(
                f"zmf_quest_soul_full_{k}",
                (
                    f"if ( level.zmf_q_full_{k}[ j ] )",
                    "{",
                    "\treturn;",
                    "}",
                    f"level.zmf_q_full_{k}[ j ] = 1;",
                    f"v_to = level.zmf_q_mouth_{k}[ j ];",
                    f"e_glow = level.zmf_q_glow_{k}[ j ];",
                    "if ( isdefined( e_glow ) )",
                    "{",
                    "\te_glow delete();",
                    "}",
                    f'PlayFX( level._effect[ "{self.full_fx}" ], v_to );',
                    f'PlayFX( level._effect[ "{self.full_fx}" ], v_to + ( 0, 0, 24 ) );',
                    f'PlayFX( level._effect[ "{self.full_fx}" ], v_to + ( 0, 0, 48 ) );',
                ),
                params=("j",),
                purpose=f"{k}: vessel j is full: its glow goes out (P12) and it bursts. Never waits.",
            ),
        ]


@dataclass(frozen=True, kw_only=True)
class StandInZone(Step):
    """Some living player must stand within ``radius`` of ``point`` for
    ``seconds`` in total (or in one go, with ``reset_on_leave``; ``left`` is
    then said to everyone when the count resets).

    The count pauses (no progress, no reset) while a special round is on,
    and while the only players in the zone are down: going down is not
    leaving (Q3)."""

    point: tuple[float, float, float]
    seconds: int
    radius: float = 96.0
    height: float = 96.0
    reset_on_leave: bool = False
    left: str | None = None
    announce_every: int = 10
    pulse_fx: str | None = "powerup_grabbed"

    _HOLDS = True

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if self.seconds < 1:
            raise ValueError(f"{self.key}: seconds >= 1")
        if self.reset_on_leave and not self.left:
            raise ValueError(f"{self.key}: a resetting hold needs a 'left' line")

    @property
    def total(self) -> int:
        return int(self.seconds)

    def lines(self):
        out = Step.lines(self)
        if self.left:
            out["left"] = (self.left, "string")
        return out

    def using(self):
        return (_LASTSTAND,)

    def body(self, i, s):
        k = self.key
        v = _vector(self.point)
        lines = []
        if self.pulse_fx:
            lines.append(f'level thread zmf_quest_zone_pulse( {v}, "{self.pulse_fx}", "zmf_q_end_{k}" );')
        on_leave = []
        if self.reset_on_leave:
            on_leave = [
                "\telse if ( n_t > 0 && !b_down_in )",
                "\t{",
                "\t\tn_t = 0;",
                f"\t\tzmf_quest_progress( {i}, 0 );",
                *("\t\t" + x for x in _say(s, "left")),
                "\t}",
            ]
        lines += [
            "n_t = 0;",
            f"while ( n_t < {self.total} )",
            "{",
            "\twait 0.5;",
            # A dog round pauses the hold: no progress, no reset (Q3).
            '\tif ( level flag::get( "special_round" ) )',
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\tb_in = false;",
            "\tb_down_in = false;",
            "\ta_players = getplayers();",
            "\tfor ( n = 0; n < a_players.size; n++ )",
            "\t{",
            "\t\te_p = a_players[ n ];",
            '\t\tif ( !isdefined( e_p ) || e_p.sessionstate == "spectator" )',
            "\t\t{",
            "\t\t\tcontinue;",
            "\t\t}",
            f"\t\tif ( Distance2DSquared( e_p.origin, {v} ) <= {self.radius * self.radius:g} "
            f"&& abs( e_p.origin[ 2 ] - {float(self.point[2]):g} ) <= {self.height:g} )",
            "\t\t{",
            "\t\t\tif ( e_p laststand::player_is_in_laststand() )",
            "\t\t\t{",
            "\t\t\t\tb_down_in = true;",
            "\t\t\t}",
            "\t\t\telse",
            "\t\t\t{",
            "\t\t\t\tb_in = true;",
            "\t\t\t}",
            "\t\t}",
            "\t}",
            "\tif ( b_in )",
            "\t{",
            "\t\tn_before = int( n_t );",
            "\t\tn_t += 0.5;",
            "\t\tif ( int( n_t ) != n_before )",
            "\t\t{",
            f"\t\t\tzmf_quest_progress( {i}, int( n_t ) );",
            *_when(f"int( n_t ) < {self.total} && int( n_t ) % "
                   f"{max(1, int(self.announce_every))} == 0",
                   _advance(self, s, "int( n_t )"), 3),
            "\t\t}",
            "\t}",
            *on_leave,
            "}",
            f'level notify( "zmf_q_end_{k}" );',
        ]
        return lines


@dataclass(frozen=True, kw_only=True)
class EveryPlayerFlag(Step):
    """Done when every player *present* carries the field ``flag`` (set by
    some other script: :data:`zmforge.script.tricks.TICKET_SERVED_FLAG` is
    the ticket window's "served").

    **Who counts**: the count is re-taken
    every ``poll`` seconds over :func:`present_players_lines`, the players
    whose ``sessionstate`` is ``"playing"`` (``_zm.gsc`` puts a bled-out
    player in ``"spectator"`` until the round ends), so a spectator does not
    hold the step up.  A downed player still counts, and a player who joins
    late raises the total (they have to do it too).  The HUD task line gets
    ``&&1`` flagged players and ``&&2`` players present; ``advance``
    (optional) is said to everyone when the count goes up, with the same
    two.  ``missing`` (``&&1`` the player) is said to everyone for each
    player still to do it, every ``nag`` seconds, so the group can see who
    is holding it up.

    **The flag is cleared on every player when the step opens**, always:
    a flag set before the step (zm_dmv's ticket window serves from round 5
    whatever the quest is doing) used to finish the step the moment it
    opened.  ``reset`` names further player fields to clear with it (the
    setter's own cooldown field, so a player who pressed a round ago can
    press again); ``reset_notify`` is a level notify sent after the clear,
    for a setter that redraws its prompts on one.
    """

    flag: str
    poll: float = 0.5
    reset: tuple[str, ...] = ()
    reset_notify: str | None = None
    missing: str = "STILL WAITING ON &&1"
    nag: float = 30.0

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        for field_name in (self.flag, *self.reset):
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", field_name):
                raise ValueError(f"{self.key}: {field_name!r} must be a GSC field name")
        if self.poll <= 0:
            raise ValueError(f"{self.key}: poll > 0")
        if self.nag <= 0:
            raise ValueError(f"{self.key}: nag > 0")
        if self.reset_notify is not None and not re.fullmatch(r"[a-z_][a-z0-9_]*",
                                                              self.reset_notify):
            raise ValueError(f"{self.key}: reset_notify must be a notify name")

    @property
    def total(self) -> int:
        # The starting total; the body keeps level.zmf_q_of[ i ] at the
        # number of players present.
        return 1

    def lines(self):
        out = Step.lines(self)
        out["missing"] = (self.missing, "string")
        return out

    def body(self, i, s):
        advance = _say(s, "advance", "n", "a_players.size") if self.advance else []
        missing_ref, _ = s("missing")
        cleared = tuple(dict.fromkeys((self.flag, *self.reset)))
        clear = ["a_players = getplayers();",
                 "for ( j = 0; j < a_players.size; j++ )",
                 "{",
                 *[f"\ta_players[ j ].{name} = undefined;" for name in cleared],
                 "}"]
        if self.reset_notify:
            clear.append(f'level notify( "{self.reset_notify}" );')
        return [
            *clear,
            "n_last = -1;",
            "n_of_last = -1;",
            f"n_nag = gettime() + {_ms(self.nag)};",
            "while ( true )",
            "{",
            *("\t" + line for line in present_players_lines("a_players")),
            "\tn = 0;",
            "\tfor ( j = 0; j < a_players.size; j++ )",
            "\t{",
            f"\t\tif ( isdefined( a_players[ j ].{self.flag} ) )",
            "\t\t{",
            "\t\t\tn++;",
            "\t\t}",
            "\t}",
            "\tif ( n != n_last || a_players.size != n_of_last )",
            "\t{",
            f"\t\tlevel.zmf_q_of[ {i} ] = a_players.size;",
            f"\t\tzmf_quest_progress( {i}, n );",
            *_when("n > n_last && n_last >= 0 && n < a_players.size", advance, 2),
            "\t\tn_last = n;",
            "\t\tn_of_last = a_players.size;",
            "\t}",
            "\tif ( a_players.size > 0 && n >= a_players.size )",
            "\t{",
            "\t\tbreak;",
            "\t}",
            # Who is holding it up, named, every nag seconds.
            "\tif ( gettime() >= n_nag )",
            "\t{",
            f"\t\tn_nag = gettime() + {_ms(self.nag)};",
            "\t\tfor ( j = 0; j < a_players.size; j++ )",
            "\t\t{",
            f"\t\t\tif ( !isdefined( a_players[ j ].{self.flag} ) )",
            "\t\t\t{",
            f'\t\t\t\tzmf_quest_all_1( &"{missing_ref}", a_players[ j ] );',
            "\t\t\t}",
            "\t\t}",
            "\t}",
            f"\twait {float(self.poll):g};",
            "}",
            f'level notify( "zmf_q_end_{self.key}" );',
        ]


def present_players_lines(target: str) -> list[str]:
    """GSC that fills ``target`` with the players who are *in* the game:
    ``sessionstate == "playing"`` (a downed player is still playing; a
    bled-out one is ``"spectator"`` until the round ends).  The one helper
    every "every player" count uses (G3), so a spectator never
    holds a step up.  AFK is not detectable from script and is not handled."""
    return [
        f"{target} = [];",
        "a_all_p = getplayers();",
        "for ( k = 0; k < a_all_p.size; k++ )",
        "{",
        '\tif ( isdefined( a_all_p[ k ] ) && a_all_p[ k ].sessionstate == "playing" )',
        "\t{",
        f"\t\t{target}[ {target}.size ] = a_all_p[ k ];",
        "\t}",
        "}",
    ]


@dataclass(frozen=True, kw_only=True)
class SurviveRounds(Step):
    """Survive ``rounds`` more round ends (``end_of_round``, ``_zm.gsc:4449``)."""

    rounds: int

    def __post_init__(self) -> None:
        Step.__post_init__(self)
        if self.rounds < 1:
            raise ValueError(f"{self.key}: rounds >= 1")

    @property
    def total(self) -> int:
        return int(self.rounds)

    def body(self, i, s):
        return [
            "n = 0;",
            f"while ( n < {self.total} )",
            "{",
            '\tlevel waittill( "end_of_round" );',
            "\tn++;",
            f"\tzmf_quest_progress( {i}, n );",
            *_when(f"n < {self.total}", _advance(self, s, "n"), 1),
            "}",
        ]


@dataclass(frozen=True, kw_only=True)
class DefeatBoss(Step):
    """Kill a :class:`~zmforge.script.bosses.Boss`.

    With ``arena`` (a point) the boss spawns when a player first comes within
    ``arena_radius`` of it; without, when the step starts.  The HUD's
    progress is the boss's health in percent (``&&1``; ``&&2`` is 100).

    The arena is open ground, never a lock-in or a teleport, so every
    present player can join the fight whenever they get there (Q5).  The
    boss does not spawn during a special round and holds the next one back
    while it lives; its health is set for the players present when it
    spawns (:class:`~zmforge.script.bosses.BossHealth`)."""

    boss: Boss
    arena: tuple[float, float, float] | None = None
    arena_radius: float = 200.0

    @property
    def total(self) -> int:
        return 100

    def lines(self):
        out = Step.lines(self)
        for ref, text in boss_strings(self.boss).items():
            out["boss:" + ref] = (text, "string")
        return out

    def body(self, i, s):
        k = self.key
        # Full health on the HUD while the players walk to the arena.
        lines = [f"zmf_quest_progress( {i}, 100 );"]
        if self.arena is not None:
            lines += [
                f't_arena = spawn( "trigger_radius", {_vector(self.arena)}, 0, '
                f"{self.arena_radius:g}, 128 );",
                "while ( true )",
                "{",
                '\tt_arena waittill( "trigger", e_who );',
                "\tif ( isplayer( e_who ) )",
                "\t{",
                "\t\tbreak;",
                "\t}",
                "}",
                "t_arena delete();",
            ]
        lines += [
            # Not on top of a dog round (Q3): the boss waits for it to end,
            # and holds the next one back while it lives (bosses.py).
            'while ( level flag::get( "special_round" ) )',
            "{",
            "\twait 1;",
            "}",
            f"ai = {self.boss.spawn_function}();",
            "while ( !isdefined( ai ) )",
            "{",
            "\twait 1;",
            f"\tai = {self.boss.spawn_function}();",
            "}",
            f"zmf_quest_progress( {i}, 100 );",
            "n_last = 100;",
            "while ( isalive( ai ) )",
            "{",
            "\twait 0.5;",
            "\tif ( !isalive( ai ) || !isdefined( ai.maxhealth ) || ai.maxhealth < 1 )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\tn_pct = int( ( ai.health * 100 ) / ai.maxhealth );",
            "\tif ( n_pct != n_last )",
            "\t{",
            "\t\tn_last = n_pct;",
            f"\t\tzmf_quest_progress( {i}, n_pct );",
            "\t}",
            "}",
            f'level notify( "zmf_q_end_{k}" );',
        ]
        return lines


# --------------------------------------------------------------------------
# The exit and the quest
# --------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class BuyableExit:
    """A use trigger that ends the game as a win once the quest is done.

    ``locked_prompt`` shows until then (and ``locked`` is said on use);
    ``prompt`` after, with the price as ``&&1``.  ``poor`` is said to a
    player short of the price (``&&1`` the price).  ``task`` is the HUD's
    CURRENT TASK line once the quest is done (``&&1`` the price).  On a
    purchase ``win_line`` is said to everyone and, three seconds later, the
    game ends with ``win_title`` where GAME OVER would be."""

    origin: tuple[float, float, float]
    locked_prompt: str
    prompt: str
    locked: str
    poor: str
    task: str
    win_line: str
    win_title: str
    price: int = 20000
    radius: float = 56.0
    height: float = 80.0

    def lines(self) -> dict[str, tuple[str, str]]:
        return {
            "locked_prompt": (with_use_key(self.locked_prompt), "triggerstring"),
            "prompt": (self.prompt, "triggerstring"),
            "locked": (self.locked, "string"),
            "poor": (self.poor, "string"),
            "task": (self.task, "string"),
            "win_line": (self.win_line, "string"),
            "win_title": (self.win_title, "string"),
        }


@dataclass(frozen=True, kw_only=True)
class Quest:
    key: str
    header: str
    intro: str
    step_done: str
    complete: str
    idle: str
    steps: tuple[Step, ...]
    exit: BuyableExit | None = None
    ordered: bool = True
    #: A level variable (``level.<name>``) that must be true before the intro
    #: shows, e.g. ``zmf_split_resolved`` so the intro waits until a split
    #: opening is over rather than landing on its lines (P13).
    intro_after: str | None = None

    def __post_init__(self) -> None:
        _check_key(self.key, "quest")
        if self.intro_after is not None:
            _check_key(self.intro_after, "intro_after")
        if not self.steps:
            raise ValueError("a quest needs steps")
        keys = [s.key for s in self.steps]
        if len(set(keys)) != len(keys):
            raise ValueError(f"step keys repeat: {keys}")
        bosses = [s.boss.key for s in self.steps if isinstance(s, DefeatBoss)]
        if len(set(bosses)) != len(bosses):
            raise ValueError("one boss per DefeatBoss step")

    def use_points(self) -> list[tuple[float, float, float]]:
        """Every ``trigger_radius_use`` the quest spawns, for clearance tests."""
        out = []
        for step in self.steps:
            out += step.use_points()
        if self.exit:
            out.append(self.exit.origin)
        return out


USE_KEY = "[{+activate}]"


def with_use_key(prompt: str) -> str:
    """``prompt`` with the use key in it: every use prompt names the key it
    is used with (P5).  A locked exit that says only that it is locked
    leaves the player guessing, though pressing it says why.  Check Z72."""
    if USE_KEY in prompt:
        return prompt
    return f"{prompt.rstrip()} - ^3{USE_KEY}^7"


def quest_strings(quest: Quest) -> dict[str, tuple[str, str]]:
    """reference -> (text, kind) for every line the quest ships."""
    out: dict[str, tuple[str, str]] = {}
    base = f"Q_{quest.key.upper()}"
    for role in ("header", "intro", "step_done", "complete", "idle"):
        out[f"{base}_{role.upper()}"] = (getattr(quest, role), "string")
    for step in quest.steps:
        for role, (text, kind) in step.lines().items():
            if role.startswith("boss:"):
                out[role[len("boss:"):]] = (text, kind)
            else:
                out[f"{base}_{step.key.upper()}_{role.upper()}"] = (text, kind)
    if quest.exit:
        for role, (text, kind) in quest.exit.lines().items():
            out[f"{base}_EXIT_{role.upper()}"] = (text, kind)
    for ref, (text, _) in out.items():
        param_count(text)
    return out


#: Seconds after a quest line to everyone during which gag lines wait.
QUEST_HUSH = 3.0
#: Seconds between the quest's intro line and the first step's start line.
INTRO_PAUSE = 4.0


def _all_players(n: int) -> CustomFunction:
    params = ("str_line", "a", "b")[: n + 1]
    call = f"IPrintLnBold( {', '.join(params)} );"
    return CustomFunction(
        f"zmf_quest_all_{n}",
        (
            # Quest lines own the centre of the screen: the gags
            # (zmforge.script.gags.gag_say) hold theirs until this is read.
            # Raise the hush, never lower it: a ticket call's is longer.
            f"if ( !isdefined( level.zmf_gag_hush ) || level.zmf_gag_hush < gettime() + {_ms(QUEST_HUSH)} )",
            "{",
            f"\tlevel.zmf_gag_hush = gettime() + {_ms(QUEST_HUSH)};",
            "}",
            "a_players = getplayers();",
            "for ( i = 0; i < a_players.size; i++ )",
            "{",
            f"\ta_players[ i ] {call}",
            "}",
        ),
        params=params,
        purpose=f"Say a quest line with {n} parameter(s) centre screen to everyone.",
    )


def _set_text(elem: str, line: str, np_expr: str | int, a: str, b: str) -> list[str]:
    if isinstance(np_expr, int):
        args = [line] + [a, b][:np_expr]
        return [f"{elem} SetText( {', '.join(args)} );"]
    return [
        f"if ( {np_expr} == 2 )", "{", f"\t{elem} SetText( {line}, {a}, {b} );", "}",
        f"else if ( {np_expr} == 1 )", "{", f"\t{elem} SetText( {line}, {a} );", "}",
        "else", "{", f"\t{elem} SetText( {line} );", "}",
    ]


def quest_script(quest: Quest, assets: dict[str, str]) -> CustomScript:
    """The quest's logic.  ``assets`` maps :func:`quest_strings`' references
    to shipped asset names (what ``add_map_string`` returned)."""
    texts = quest_strings(quest)
    base = f"Q_{quest.key.upper()}"

    def q(role: str) -> tuple[str, int]:
        ref = f"{base}_{role.upper()}"
        return assets[ref], param_count(texts[ref][0])

    n_steps = len(quest.steps)
    header, header_np = q("header")
    idle, idle_np = q("idle")
    if idle_np:
        raise ValueError("the idle line takes no parameters")

    init = [
        'level endon( "end_game" );',
        "level.zmf_quest_done = 0;",
    ]
    init += [
        f"level.zmf_quest_steps = {n_steps};",
        "level.zmf_quest_count = 0;",
        f"level.zmf_quest_cur = {_IDLE};",
        "level.zmf_quest_task = [];",
        "level.zmf_quest_np = [];",
        "level.zmf_quest_wait = [];",
        "level.zmf_q_n = [];",
        "level.zmf_q_of = [];",
        "level.zmf_q_state = [];",
        "level.zmf_q_locked = [];",
        "level.zmf_quest_find = [];",
    ]
    functions: list[CustomFunction] = []
    using: list[str] = [_FLAG]
    assets_decl: list[tuple[str, str]] = []
    step_threads: list[str] = []
    held: list[tuple[int, str, bool]] = []
    for i, step in enumerate(quest.steps):
        up = step.key.upper()

        def s(role: str, _up=up) -> tuple[str, int]:
            if role.startswith("BOSS_"):
                return assets[role], 0
            ref = f"{base}_{_up}_{role.upper()}"
            return assets[ref], param_count(texts[ref][0])

        task, task_np = s("task")
        init += [
            f'level.zmf_quest_task[ {i} ] = &"{task}";',
            f"level.zmf_quest_np[ {i} ] = {task_np};",
            f"level.zmf_q_n[ {i} ] = 0;",
            f"level.zmf_q_of[ {i} ] = {step.total};",
            f"level.zmf_q_state[ {i} ] = 0;",
            f"level.zmf_q_locked[ {i} ] = 0;",
        ]
        if step.zones:
            find_ref, _ = s("find")
            init.append(f'level.zmf_quest_find[ {i} ] = &"{find_ref}";')
        if step.waiting:
            wait_ref, wait_np = s("waiting")
            if wait_np > 1:
                raise ValueError(f"{step.key}: the waiting line takes the round as &&1 only")
            init.append(f'level.zmf_quest_wait[ {i} ] = &"{wait_ref}";')

        gate: list[str] = ['level endon( "end_game" );']
        if quest.ordered and i > 0:
            gate += [
                f"while ( level.zmf_q_state[ {i - 1} ] != 2 )",
                "{",
                '\tlevel waittill( "zmf_quest_step_done" );',
                "}",
            ]
        if step.unlock_round:
            gate += [
                f"level.zmf_quest_cur = {i};",
                'level notify( "zmf_quest_hud" );',
                f"while ( level.round_number < {int(step.unlock_round)} )",
                "{",
                '\tlevel waittill( "start_of_round" );',
                "}",
            ]
        if step.zones:
            # Not before its zone is open (P8): no task, no start
            # line, no timer while the room is still behind a door.  The HUD
            # says the find line meanwhile, unless another step is live.
            # zm_zonemgr::zone_is_enabled: _zm_zonemgr.gsc:65, set true by
            # enable_zone when a door's flag opens the zone (:488-499).
            opened = " && ".join(f'zm_zonemgr::zone_is_enabled( "{z}" )' for z in step.zones)
            gate += [
                f"if ( !( {opened} ) )",
                "{",
                f"\tlevel.zmf_q_locked[ {i} ] = 1;",
                "\tb_take = level.zmf_quest_cur < 0;",
                "\tif ( !b_take )",
                "\t{",
                "\t\tb_take = level.zmf_q_state[ level.zmf_quest_cur ] != 1;",
                "\t}",
                "\tif ( b_take )",
                "\t{",
                f"\t\tlevel.zmf_quest_cur = {i};",
                "\t}",
                '\tlevel notify( "zmf_quest_hud" );',
                f"\twhile ( !( {opened} ) )",
                "\t{",
                "\t\twait 0.5;",
                "\t}",
                f"\tlevel.zmf_q_locked[ {i} ] = 0;",
                "}",
            ]
        if step.lockdown:
            # A lockdown never starts during a special round (Q3): it would
            # hold back the next one, not the one already on.
            gate += [
                'while ( level flag::get( "special_round" ) )',
                "{",
                "\twait 1;",
                "}",
            ]
            timed = step.time_limit is not None
            held.append((i, step.key, timed))
        gate += [
            # A step that opens at a round start waits out a live ticket
            # call rather than print over it.
            "while ( isdefined( level.zmf_ticket_calling ) && level.zmf_ticket_calling )",
            "{",
            "\twait 0.5;",
            "}",
            f"level.zmf_q_state[ {i} ] = 1;",
            f"zmf_quest_progress( {i}, 0 );",
            *_say(s, "start"),
        ]
        end = f"zmf_q_end_{step.key}"
        hint_drop: list[str] = []
        if step.hint:
            # The step thread owns the hint's trigger and deletes it once the
            # step's end notify has stopped the watcher (P12): the watcher no
            # longer sits on a live trigger until someone walks into it.
            h = step.hint
            gate += [
                f't_hint = spawn( "trigger_radius", {_vector(h.point)}, 0, {h.radius:g}, {h.height:g} );',
                f"level thread zmf_quest_hint_{step.key}( t_hint );",
            ]
            hint_drop = ["t_hint delete();"]
            hint_ref, _ = s("hint")
            functions.append(CustomFunction(
                f"zmf_quest_hint_{step.key}",
                (
                    'level endon( "end_game" );',
                    f'level endon( "{end}" );',
                    "while ( true )",
                    "{",
                    '\tt_hint waittill( "trigger", e_who );',
                    "\tif ( !isplayer( e_who ) )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\tif ( isdefined( e_who.zmf_q_hint_{step.key} ) && gettime() < "
                    f"e_who.zmf_q_hint_{step.key} )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    # A hint is automatic, so it waits while a ticket call
                    # or a quest line owns the centre of the screen (the
                    # number hint's spot is the ticket window itself).
                    "\tif ( isdefined( level.zmf_gag_hush ) && gettime() < level.zmf_gag_hush )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    "\tif ( isdefined( e_who.zmf_gag_hush ) && gettime() < e_who.zmf_gag_hush )",
                    "\t{",
                    "\t\tcontinue;",
                    "\t}",
                    f"\te_who.zmf_q_hint_{step.key} = gettime() + {_ms(h.cooldown)};",
                    f'\te_who IPrintLnBold( &"{hint_ref}" );',
                    "}",
                ),
                params=("t_hint",),
                purpose=f"{step.key}: tell a player near the spot how to start it; ends with the step.",
            ))
        done_ref, done_np = s("done")
        body = step.body(i, s)
        # Every step ends on its own notify, which is what each thread it
        # started (watchers, pulses, timers, the hint) ends on (P12).  The
        # built-in steps send it themselves; a step that does not (survive
        # rounds, a recipe's own Step) gets it here.
        if f'level notify( "{end}" );' not in body:
            body = [*body, f'level notify( "{end}" );']
        finish = [*hint_drop, *_say(s, "done"), f"zmf_quest_finish( {i} );"]
        functions.append(CustomFunction(
            f"zmf_quest_step_{step.key}",
            tuple(gate + body + finish),
            purpose=f"Quest step {i + 1} of {n_steps}: {step.key} ({type(step).__name__}).",
        ))
        functions += step.extra(i, s)
        using += list(step.using())
        if step.zones:
            using.append(_ZONEMGR)
        assets_decl += list(step.assets())
        if isinstance(step, DefeatBoss):
            boss_assets = {ref: assets[ref] for ref in boss_strings(step.boss)}
            b = boss_script(step.boss, boss_assets)
            functions += list(b.functions)
            using += list(b.using)
            assets_decl += list(b.assets)  # the boss's worn props (xmodels)
        step_threads.append(f"level thread zmf_quest_step_{step.key}();")

    intro, intro_np = q("intro")
    if intro_np:
        raise ValueError("the intro line takes no parameters")
    if held:
        init.append("level thread zmf_quest_hold_specials();")
        functions += _hold_functions(held)
    init += [
        "level thread zmf_quest_hud_attach();",
        'level flag::wait_till( "initial_blackscreen_passed" );',
        *([f"while ( !( isdefined( level.{quest.intro_after} ) && level.{quest.intro_after} ) )",
           "{", "\twait 1;", "}", f"wait {float(INTRO_PAUSE):g};"] if quest.intro_after else []),
        f'zmf_quest_all_0( &"{intro}" );',
        # The intro gets the screen to itself before the first step's start
        # line and cue (three lines at once at game start).
        f"wait {float(INTRO_PAUSE):g};",
        *step_threads,
    ]
    if quest.exit:
        init.append("level thread zmf_quest_exit();")
    functions.insert(0, CustomFunction(
        "zmf_quest_init", tuple(init),
        purpose=("The quest: its flags, the HUD's tables, and every step's thread.\n"
                 'flag "initial_blackscreen_passed": _zm.gsc:1612 init, :530 set.'),
    ))

    # -- shared runtime -----------------------------------------------------
    step_done, sd_np = q("step_done")
    complete, c_np = q("complete")
    if c_np:
        raise ValueError("the complete line takes no parameters")
    sd_args = ["level.zmf_quest_count", "level.zmf_quest_steps"][:sd_np]
    functions += [
        CustomFunction(
            "zmf_quest_progress",
            (
                "level.zmf_quest_cur = n_step;",
                "level.zmf_q_n[ n_step ] = n;",
                'level notify( "zmf_quest_hud" );',
            ),
            params=("n_step", "n"),
            purpose="A step moved: record it and redraw every HUD.",
        ),
        CustomFunction(
            "zmf_quest_finish",
            (
                "level.zmf_q_state[ n_step ] = 2;",
                "level.zmf_quest_count++;",
                f'zmf_quest_all_{sd_np}( &"{step_done}"{"".join(", " + a for a in sd_args)} );',
                "if ( level.zmf_quest_count >= level.zmf_quest_steps )",
                "{",
                f"\tlevel.zmf_quest_cur = {_EXIT if quest.exit else _IDLE};",
                f'\tzmf_quest_all_0( &"{complete}" );',
                "\tlevel.zmf_quest_done = 1;",
                '\tlevel notify( "zmf_quest_done" );',
                "}",
                "else",
                "{",
                f"\tlevel.zmf_quest_cur = {_IDLE};",
                "\tfor ( i = 0; i < level.zmf_quest_steps; i++ )",
                "\t{",
                "\t\tif ( level.zmf_q_state[ i ] == 1 )",
                "\t\t{",
                "\t\t\tlevel.zmf_quest_cur = i;",
                "\t\t}",
                "\t}",
                # No live step: a step waiting for its zone keeps its find line.
                "\tfor ( i = 0; i < level.zmf_quest_steps && level.zmf_quest_cur < 0; i++ )",
                "\t{",
                "\t\tif ( level.zmf_q_state[ i ] == 0 && level.zmf_q_locked[ i ] )",
                "\t\t{",
                "\t\t\tlevel.zmf_quest_cur = i;",
                "\t\t}",
                "\t}",
                "}",
                'level notify( "zmf_quest_hud" );',
                # Last, so the next step's gate (which may put its "opens at
                # round N" line on the HUD) runs after the HUD was reset here.
                'level notify( "zmf_quest_step_done" );',
            ),
            params=("n_step",),
            purpose="A step is done: its state, the count, the popups, the HUD.",
        ),
    ]

    draw = [
        *_set_text("self.zmf_qh_head", f'&"{header}"', header_np,
                   "level.zmf_quest_count", "level.zmf_quest_steps"),
        "n = level.zmf_quest_cur;",
        f"if ( n == {_WON} )",
        "{",
        "\tself.zmf_qh_task.alpha = 0;",
        "\treturn;",
        "}",
    ]
    if quest.exit:
        exit_task, et_np = q("exit_task")
        draw += [
            f"if ( n == {_EXIT} )",
            "{",
            *("\t" + x for x in _set_text("self.zmf_qh_task", f'&"{exit_task}"', et_np,
                                          str(int(quest.exit.price)), "0")),
            "\treturn;",
            "}",
        ]
    draw += [
        "if ( n < 0 )",
        "{",
        f'\tself.zmf_qh_task SetText( &"{idle}" );',
        "\treturn;",
        "}",
        "if ( level.zmf_q_state[ n ] == 0 && level.zmf_q_locked[ n ] )",
        "{",
        "\tself.zmf_qh_task SetText( level.zmf_quest_find[ n ] );",
        "\treturn;",
        "}",
        "if ( level.zmf_q_state[ n ] == 0 && isdefined( level.zmf_quest_wait[ n ] ) )",
        "{",
        "\tself.zmf_qh_task SetText( level.zmf_quest_wait[ n ], level.zmf_q_unlock[ n ] );",
        "\treturn;",
        "}",
        *_set_text("self.zmf_qh_task", "level.zmf_quest_task[ n ]", "level.zmf_quest_np[ n ]",
                   "level.zmf_q_n[ n ]", "level.zmf_q_of[ n ]"),
    ]
    init_unlock = ["level.zmf_q_unlock = [];"] + [
        f"level.zmf_q_unlock[ {i} ] = {int(s.unlock_round)};" for i, s in enumerate(quest.steps)
    ]
    body0 = list(functions[0].body)
    at = body0.index("level.zmf_q_state = [];") + 1
    functions[0] = CustomFunction(functions[0].name, tuple(body0[:at] + init_unlock + body0[at:]),
                                  purpose=functions[0].purpose)
    functions += [
        CustomFunction(
            "zmf_quest_hud_attach",
            (
                'level endon( "end_game" );',
                'level flag::wait_till( "initial_blackscreen_passed" );',
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                "\ta_players[ i ] thread zmf_quest_hud_player();",
                "}",
                "while ( true )",
                "{",
                '\tlevel waittill( "connected", player );',
                "\tplayer thread zmf_quest_hud_player();",
                "}",
            ),
            purpose=("The objective HUD on everyone, now and on join.\n"
                     'level waittill( "connected", player ): _zm.gsc:463.'),
        ),
        CustomFunction(
            "zmf_quest_hud_elem",
            (
                "e_hud = NewClientHudElem( e_player );",
                'e_hud.font = "objective";',
                'e_hud.alignX = "left";',
                'e_hud.alignY = "top";',
                'e_hud.horzAlign = "user_left";',
                'e_hud.vertAlign = "user_top";',
                "e_hud.x = 16;",
                "e_hud.y = n_y;",
                "e_hud.foreground = true;",
                "e_hud.fontScale = n_scale;",
                "e_hud.alpha = 1;",
                "e_hud.color = v_color;",
                "e_hud.hidewheninmenu = true;",
                "return e_hud;",
            ),
            params=("e_player", "n_y", "n_scale", "v_color"),
            purpose=("One line of persistent text, top left. NewClientHudElem and the\n"
                     "fields: teamgather_shared.gsc:811-827; user_left/user_top:\n"
                     "hud_util_shared.gsc:1035-1036."),
        ),
        CustomFunction(
            "zmf_quest_hud_player",
            (
                'self endon( "disconnect" );',
                "if ( isdefined( self.zmf_qh_head ) )",
                "{",
                "\treturn;",
                "}",
                "self.zmf_qh_head = zmf_quest_hud_elem( self, 16, 1.6, ( 1, 0.82, 0.3 ) );",
                "self.zmf_qh_task = zmf_quest_hud_elem( self, 40, 1.3, ( 1, 1, 1 ) );",
                "self thread zmf_quest_hud_end();",
                'level endon( "end_game" );',
                "while ( true )",
                "{",
                "\tself zmf_quest_hud_draw();",
                '\tlevel waittill( "zmf_quest_hud" );',
                "}",
            ),
            purpose="This player's two HUD lines, redrawn on every change.",
        ),
        CustomFunction(
            "zmf_quest_hud_end",
            (
                'self endon( "disconnect" );',
                'level waittill( "end_game" );',
                "self.zmf_qh_head destroy();",
                "self.zmf_qh_task destroy();",
            ),
            purpose=("Off the screen before the end screen. destroy() on a HUD\n"
                     "element: _zm_laststand.gsc:448."),
        ),
        CustomFunction("zmf_quest_hud_draw", tuple(draw),
                       purpose="Header with the count; the live task with its progress."),
        _all_players(0), _all_players(1), _all_players(2),
    ]

    # -- the aim / melee watchers (shared by every HitTargets step) ---------
    if any(isinstance(s, HitTargets) for s in quest.steps):
        functions += _aim_functions()
    if any(isinstance(s, CollectDeliver) and s.pulse_fx for s in quest.steps):
        functions.append(CustomFunction(
            "zmf_quest_item_pulse",
            (
                'level endon( "end_game" );',
                "fx = level._effect[ str_fx ];",
                "while ( isdefined( t_item ) )",
                "{",
                "\tPlayFX( fx, v_at );",
                "\twait 2.5;",
                "}",
            ),
            params=("t_item", "v_at", "str_fx"),
            purpose="A pulse on an item for as long as it is on the floor.",
        ))
    if any(getattr(s, "pulse_fx", None) and isinstance(s, (KillInZone, StandInZone))
           for s in quest.steps):
        functions.append(CustomFunction(
            "zmf_quest_zone_pulse",
            (
                'level endon( "end_game" );',
                "level endon( str_end );",
                "while ( true )",
                "{",
                "\tPlayFX( level._effect[ str_fx ], v_at );",
                "\twait 2.5;",
                "}",
            ),
            params=("v_at", "str_fx", "str_end"),
            purpose="A pulse on a zone while its step is live.",
        ))

    if quest.exit:
        functions += _exit_functions(quest, q)
        using += [_SCORE, _LASTSTAND]

    return CustomScript(
        using=tuple(dict.fromkeys(using)),
        functions=tuple(functions),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_quest_init();"),),
        assets=tuple(dict.fromkeys(assets_decl)),
        notes=(f"quest {quest.key}: {n_steps} steps"
               + (f", exit for {quest.exit.price}" if quest.exit else ""),),
    )


def _hold_functions(held: list[tuple[int, str, bool]]) -> list[CustomFunction]:
    """The lockdown: while any ``lockdown`` step runs (a timed one while its
    countdown runs), each round end pushes the next dog round past the
    coming round (:func:`zmforge.script.bosses.hold_special_lines`)."""
    from .bosses import hold_special_lines

    test = []
    for i, key, timed in held:
        cond = f"level.zmf_q_state[ {i} ] == 1"
        if timed:
            cond += f" && isdefined( level.zmf_q_ton_{key} ) && level.zmf_q_ton_{key}"
        test += [f"// hold: {key}", f"if ( {cond} )", "{", "\treturn true;", "}"]
    return [
        CustomFunction(
            "zmf_quest_holding", (*test, "return false;"),
            purpose="Whether a lockdown step is running now (Q3).",
        ),
        CustomFunction(
            "zmf_quest_hold_specials",
            (
                'level endon( "end_game" );',
                "while ( true )",
                "{",
                '\tlevel waittill( "end_of_round" );',
                "\tif ( zmf_quest_holding() )",
                "\t{",
                *("\t\t" + line for line in hold_special_lines()),
                "\t}",
                "}",
            ),
            purpose=("Lockdown: no special round starts while a lockdown step runs\n"
                     "(dog_round_tracker, _zm_ai_dogs.gsc:490-501)."),
        ),
    ]


def _aim_functions() -> list[CustomFunction]:
    watch_args = "a_pts, a_r, b_melee, n_reach, str_hit, str_end"
    return [
        CustomFunction(
            "zmf_quest_aim_attach",
            (
                'level endon( "end_game" );',
                "level endon( str_end );",
                "a_players = getplayers();",
                "for ( i = 0; i < a_players.size; i++ )",
                "{",
                f"\ta_players[ i ] thread zmf_quest_aim_watch( {watch_args} );",
                "}",
                "while ( true )",
                "{",
                '\tlevel waittill( "connected", player );',
                f"\tplayer thread zmf_quest_aim_watch( {watch_args} );",
                "}",
            ),
            params=tuple(a.strip() for a in watch_args.split(",")),
            purpose="Watch every player's shots (or swings) at a step's targets.",
        ),
        CustomFunction(
            "zmf_quest_aim_watch",
            (
                'self endon( "disconnect" );',
                'level endon( "end_game" );',
                "level endon( str_end );",
                "while ( true )",
                "{",
                "\tif ( b_melee )",
                "\t{",
                '\t\tself waittill( "weapon_melee" );',
                "\t}",
                "\telse",
                "\t{",
                '\t\tself waittill( "weapon_fired" );',
                "\t}",
                "\tj = self zmf_quest_aimed_at( a_pts, a_r, b_melee, n_reach );",
                "\tif ( j >= 0 )",
                "\t{",
                "\t\tlevel notify( str_hit, j, self );",
                "\t}",
                "}",
            ),
            params=tuple(a.strip() for a in watch_args.split(",")),
            purpose=('weapon_fired: _zm_weap_octobomb.gsc:160; weapon_melee:\n'
                     "_zm_ai_wasp.gsc:1318."),
        ),
        CustomFunction(
            "zmf_quest_aimed_at",
            (
                "v_eye = self GetEye();",
                "v_fwd = self GetWeaponForwardDir();",
                "n_best = -1;",
                "n_score = 0;",
                "for ( j = 0; j < a_pts.size; j++ )",
                "{",
                "\tv_to = a_pts[ j ] - v_eye;",
                "\tif ( b_melee )",
                "\t{",
                "\t\tif ( Distance2DSquared( v_eye, a_pts[ j ] ) > n_reach * n_reach )",
                "\t\t{",
                "\t\t\tcontinue;",
                "\t\t}",
                "\t\tif ( abs( v_to[ 2 ] ) > 64 )",
                "\t\t{",
                "\t\t\tcontinue;",
                "\t\t}",
                "\t\tn_dot = VectorDot( v_fwd, VectorNormalize( v_to ) );",
                "\t\tif ( n_dot < 0.5 )",
                "\t\t{",
                "\t\t\tcontinue;",
                "\t\t}",
                "\t\tif ( n_best < 0 || n_dot > n_score )",
                "\t\t{",
                "\t\t\tn_best = j;",
                "\t\t\tn_score = n_dot;",
                "\t\t}",
                "\t\tcontinue;",
                "\t}",
                "\tn_along = VectorDot( v_to, v_fwd );",
                "\tif ( n_along <= 0 || n_along > n_reach )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\tn_miss = DistanceSquared( v_eye + VectorScale( v_fwd, n_along ), a_pts[ j ] );",
                "\tif ( n_miss > a_r[ j ] * a_r[ j ] )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\ta_trace = BulletTrace( v_eye, a_pts[ j ], false, self );",
                '\tif ( a_trace[ "fraction" ] < 1 && DistanceSquared( a_trace[ "position" ], '
                "a_pts[ j ] ) > a_r[ j ] * a_r[ j ] )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\tif ( n_best < 0 || n_miss < n_score )",
                "\t{",
                "\t\tn_best = j;",
                "\t\tn_score = n_miss;",
                "\t}",
                "}",
                "return n_best;",
            ),
            params=("a_pts", "a_r", "b_melee", "n_reach"),
            purpose=("Which target this player just shot or knifed, or -1.\n"
                     "Melee: the stock test at _zm_ai_wasp.gsc:1290-1303 (72 units,\n"
                     "64 high, dot 0.5). Shot: the aim ray passes within the\n"
                     "target's radius and BulletTrace (colors_shared.gsc:398) is\n"
                     "not stopped short of it."),
        ),
    ]


def _exit_functions(quest: Quest, q) -> list[CustomFunction]:
    ex = quest.exit
    locked_prompt, _ = q("exit_locked_prompt")
    prompt, prompt_np = q("exit_prompt")
    locked, _ = q("exit_locked")
    poor, poor_np = q("exit_poor")
    win_line, _ = q("exit_win_line")
    win_title, _ = q("exit_win_title")
    price = int(ex.price)
    prompt_args = f', {price}' if prompt_np else ""
    poor_args = f', {price}' if poor_np else ""
    return [
        CustomFunction(
            "zmf_quest_exit",
            (
                'level endon( "end_game" );',
                f't_exit = spawn( "trigger_radius_use", {_vector(ex.origin)}, 0, '
                f"{ex.radius:g}, {ex.height:g} );",
                "t_exit TriggerIgnoreTeam();",
                "t_exit SetVisibleToAll();",
                't_exit SetTeamForTrigger( "none" );',
                't_exit SetCursorHint( "HINT_NOICON" );',
                f't_exit SetHintString( &"{locked_prompt}" );',
                "level thread zmf_quest_exit_open( t_exit );",
                "while ( true )",
                "{",
                '\tt_exit waittill( "trigger", e_who );',
                "\tif ( !isplayer( e_who ) || e_who laststand::player_is_in_laststand() )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\tif ( isdefined( e_who.zmf_q_exit ) && gettime() < e_who.zmf_q_exit )",
                "\t{",
                "\t\tcontinue;",
                "\t}",
                "\te_who.zmf_q_exit = gettime() + 1500;",
                "\tif ( !level.zmf_quest_done )",
                "\t{",
                f'\t\te_who IPrintLnBold( &"{locked}" );',
                "\t\tcontinue;",
                "\t}",
                f"\tif ( !e_who zm_score::can_player_purchase( {price} ) )",
                "\t{",
                f'\t\te_who IPrintLnBold( &"{poor}"{poor_args} );',
                "\t\tcontinue;",
                "\t}",
                f"\te_who zm_score::minus_to_player_score( {price} );",
                "\tt_exit delete();",
                "\tzmf_quest_win();",
                "\treturn;",
                "}",
            ),
            purpose=(f"The exit: locked until the quest is done, then {price} points\n"
                     "ends the game. can_player_purchase / minus_to_player_score:\n"
                     "_zm_score.gsc:655 / :551, as _zm_perk_widows_wine.gsc:681/:704."),
        ),
        CustomFunction(
            "zmf_quest_exit_open",
            (
                'level endon( "end_game" );',
                "while ( !level.zmf_quest_done )",
                "{",
                '\tlevel waittill( "zmf_quest_done" );',
                "}",
                "if ( isdefined( t_exit ) )",
                "{",
                f'\tt_exit SetHintString( &"{prompt}"{prompt_args} );',
                "}",
            ),
            params=("t_exit",),
            purpose=("The price on the prompt once it opens: SetHintString with a\n"
                     "parameter, _zm_pack_a_punch_util.gsc:117."),
        ),
        CustomFunction(
            "zmf_quest_win",
            (
                f"level.zmf_quest_cur = {_WON};",
                'level notify( "zmf_quest_hud" );',
                f'zmf_quest_all_0( &"{win_line}" );',
                "wait 3;",
                "level.custom_game_over_hud_elem = &zmf_quest_win_hud;",
                'level notify( "end_game" );',
            ),
            purpose=("Win: the line, then the stock end_game (level notify, _zm.gsc:1791)\n"
                     "with this map's title in GAME OVER's place (the hook read at\n"
                     "_zm.gsc:6064-6066)."),
        ),
        CustomFunction(
            "zmf_quest_win_hud",
            (
                'e_game_over.alignX = "center";',
                'e_game_over.alignY = "middle";',
                'e_game_over.horzAlign = "center";',
                'e_game_over.vertAlign = "middle";',
                "e_game_over.y = e_game_over.y - 130;",
                "e_game_over.foreground = true;",
                "e_game_over.fontScale = 3;",
                "e_game_over.alpha = 0;",
                "e_game_over.color = ( 0.55, 1, 0.55 );",
                "e_game_over.hidewheninmenu = true;",
                f'e_game_over SetText( &"{win_title}" );',
                "e_game_over FadeOverTime( 1 );",
                "e_game_over.alpha = 1;",
                'e_survived.alignX = "center";',
                'e_survived.alignY = "middle";',
                'e_survived.horzAlign = "center";',
                'e_survived.vertAlign = "middle";',
                "e_survived.y = e_survived.y - 100;",
                "e_survived.foreground = true;",
                "e_survived.fontScale = 2;",
                "e_survived.alpha = 0;",
                "e_survived.color = ( 1, 1, 1 );",
                "e_survived.hidewheninmenu = true;",
            ),
            params=("e_player", "e_game_over", "e_survived"),
            purpose=("level.custom_game_over_hud_elem: end_game() hands it the two\n"
                     "elements (_zm.gsc:6066) and skips its own layout (:6070-6099);\n"
                     "it still writes the rounds-survived text after (:6118-6132)."),
        ),
    ]


def step_points(step: Step) -> list[tuple[float, float, float]]:
    """Everywhere a player must be to do ``step``: its hint, use triggers,
    targets, zone and boss.  What the zone gate (P8) and Z61 look at."""
    out = [tuple(p) for p in step.use_points()]
    if step.hint:
        out.append(tuple(step.hint.point))
    out += [tuple(t.point) for t in getattr(step, "targets", ())]
    if isinstance(step, (KillInZone, StandInZone)):
        out.append(tuple(step.point))
    if isinstance(step, SoulBox):
        out += [tuple(v.point) for v in step.vessels]
    if isinstance(step, DefeatBoss):
        out.append(tuple(step.arena or step.boss.spawn_at))
    return out


def blueprint_zone_gates(bp) -> tuple[list, set[str], set[str]]:
    """``(zone boxes, door-gated zones, zones only a script opens)`` of a
    live blueprint, for :mod:`zmforge.script.zonegate`."""
    from ..blueprint.elements import Door, Zone
    from .zonegate import door_opened, open_at_start

    zones = list(bp.elements(Zone))
    boxes = [(z.name, z.bounds.mins.x, z.bounds.maxs.x, z.bounds.mins.y, z.bounds.maxs.y,
              z.bounds.mins.z, z.bounds.maxs.z) for z in zones if z.bounds is not None]
    plan = bp.script
    edges = [(e.zone_a, e.zone_b, e.flag) for e in plan.edges]
    starting = [z.name for z in zones if z.starting]
    always_on = plan.always_on_flag
    open_ = open_at_start(starting, edges, always_on)
    doors = door_opened(starting, edges, [d.flag for d in bp.elements(Door)], always_on)
    names = {z.name for z in zones}
    return boxes, doors - open_, names - doors


def gate_quest(bp, quest: Quest) -> Quest:
    """``quest`` with every step whose points (:func:`step_points`) stand in
    a door-gated zone of ``bp`` waiting for that zone (``Step.zones``, P8)."""
    from dataclasses import replace

    from .zonegate import step_gates

    boxes, gated, _ = blueprint_zone_gates(bp)
    steps = []
    for step in quest.steps:
        zones = tuple(sorted(set(step.zones) | set(step_gates(step_points(step), boxes, gated))))
        steps.append(replace(step, zones=zones) if zones != step.zones else step)
    return replace(quest, steps=tuple(steps))


def gate_callout(bp, label: str, points) -> tuple[str, ...]:
    """The door-gated zones ``points`` stand in, for a timed callout that is
    not a quest step (a ticket call, a PA summons, an event with a timer).

    Generic form of :func:`gate_quest` (zm_dmv's ticket
    calls started at round 5 at a window behind 3,000 points of doors, and
    a missed call voids the ticket).  The callout is recorded with the quest
    steps (``bp.quest_steps``), so Z61 checks its gate like any step's: a
    caller that ignores the returned zones is reported."""
    from .zonegate import step_gates

    pts = [tuple(float(c) for c in p) for p in points]
    boxes, gated, _ = blueprint_zone_gates(bp)
    zones = step_gates(pts, boxes, gated)
    record = getattr(bp, "quest_steps", None)
    if record is not None:
        record.append({"label": label, "points": [list(p) for p in pts],
                       "gates": list(zones)})
    return zones


def install_quest(bp, quest: Quest) -> CustomScript:
    """Ship every line of ``quest`` and weave its logic into ``bp``, each
    step gated on its zones first (:func:`gate_quest`)."""
    from ..spatial import Point

    quest = gate_quest(bp, quest)
    # Every hit target is an object the quest finishes: Z64 warns about a
    # static light that would outlive it (script.glow, P12).
    from .glow import own_quest_targets

    own_quest_targets(bp, quest)
    record_steps = getattr(bp, "quest_steps", None)
    if record_steps is not None:
        for step in quest.steps:
            record_steps.append({
                "label": f"quest {quest.key} step {step.key}",
                "points": [[float(c) for c in p] for p in step_points(step)],
                "gates": list(step.zones),
            })
        # D4 (lock before key): every lock and the keys or parts it takes.
        from ..verify.design import quest_locks

        locks = getattr(bp, "quest_locks", None)
        if locks is None:
            locks = []
            bp.quest_locks = locks
        locks.extend(quest_locks(quest))

    record = getattr(bp, "quest_use_points", None)
    if record is not None:
        for step in quest.steps:
            radius = float(getattr(step, "radius", 0.0) or 0.0)
            for n, point in enumerate(step.use_points(), 1):
                record.append((f"quest {quest.key} step {step.key} point {n}",
                               Point(*point), radius))
        if quest.exit:
            record.append((f"quest {quest.key} exit", Point(*quest.exit.origin),
                           float(quest.exit.radius)))
    assets = {
        ref: bp.add_map_string(ref, text, kind=kind)
        for ref, (text, kind) in quest_strings(quest).items()
    }
    for step in quest.steps:
        if isinstance(step, DefeatBoss):
            precache_boss_fx(bp, step.boss)
    return bp.add_custom_logic(quest_script(quest, assets))
