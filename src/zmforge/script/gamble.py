"""The gamble machine's script: pay 2,000 for a 1 in 4 chance at 10,000.

Every map carries one of these at its farthest point (principle P22,
``docs/map-principles.md``; placement and look are
:mod:`zmforge.dressing.gamble`).  This module is only the mechanic: one
script-spawned use trigger and the thread that answers it.

What a press does, in order, with no ``wait`` between the checks and the
payment so two presses cannot interleave:

1. ignore anyone who is not a player or is down;
2. drop presses closer than :data:`PRESS_GAP_MS` apart per player (the
   trigger fires every frame while use is held, so this is what stops one
   hold printing a line per frame);
3. refuse, with a line to that player, a player who has used up this round's
   plays (``per_round``, default one; ``None`` is no limit);
4. refuse, with the stock "no purchase" sound and a line, a player who
   cannot pay (``zm_score::can_player_purchase``, ``_zm_score.gsc:655``, the
   test every stock buy makes);
5. charge the cost (``zm_score::minus_to_player_score``, ``:556``, so it is
   real spending: ``spent_points`` fires and Shopping Free applies as it
   does to every stock buy) with the stock "purchase" sound;
6. ``RandomInt( out_of ) < wins``: ``RandomInt( n )`` is uniform over
   ``0 .. n-1``, so the odds are exactly ``wins / out_of`` (1 in 4 by
   default);
7. a win pays the prize (``zm_score::add_to_player_score``, ``:521``) and
   says so to the winner, plus one short feed line to everyone else; a loss
   says so to that player only.

Points never go negative: the charge only runs after
``can_player_purchase`` said the score covers it (or Shopping Free, which
charges nothing, ``_zm_score.gsc:561-566``).

**Unverified in play.**  Nothing here has been run in the game.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..spatial import Point
from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "COST",
    "PRIZE",
    "WINS",
    "OUT_OF",
    "PER_ROUND",
    "PRESS_GAP_MS",
    "GambleLines",
    "odds_text",
    "gamble_lines",
    "gamble_script",
]

#: Points a play costs.
COST = 2000
#: Points a win pays.
PRIZE = 10000
#: A win is ``RandomInt( OUT_OF ) < WINS``: 1 in 4.
WINS = 1
OUT_OF = 4
#: Plays per player per round (the rule for anything spammable).
PER_ROUND = 1
#: Presses closer together than this, per player, are ignored.
PRESS_GAP_MS = 1500
#: The use trigger's radius and height, from the machine's front at the floor.
RADIUS = 44.0
HEIGHT = 80.0

_SCORE = r"scripts\zm\_zm_score"
_UTILITY = r"scripts\zm\_zm_utility"
_LASTSTAND = r"scripts\shared\laststand_shared"
_FLAG = r"scripts\shared\flag_shared"


def _points(n: int) -> str:
    return f"{int(n):,}"


def odds_text(wins: int = WINS, out_of: int = OUT_OF) -> str:
    """``"1 in 4"``: the odds as the prompt says them."""
    return f"{int(wins)} in {int(out_of)}"


@dataclass(frozen=True)
class GambleLines:
    """The asset names of the machine's map strings."""

    prompt: str
    win: str
    lose: str
    broke: str
    used: str
    win_all: str | None = None


def gamble_lines(bp, *, name: str = "LUCKY 4", cost: int = COST, prize: int = PRIZE,
                 wins: int = WINS, out_of: int = OUT_OF,
                 per_round: int | None = PER_ROUND) -> GambleLines:
    """Ship the machine's text on *bp* and return the asset names."""
    odds = odds_text(wins, out_of)
    if per_round is None:
        used = "Give it a second"
    elif int(per_round) == 1:
        used = f"The {name} takes one bet a round. Come back next round"
    else:
        used = f"The {name} takes {int(per_round)} bets a round. Come back next round"
    return GambleLines(
        prompt=bp.add_map_string(
            "ZMF_GAMBLE_PROMPT",
            f"Hold ^3[{{+activate}}]^7 to gamble {_points(cost)} for a {odds} "
            f"chance at {_points(prize)}",
            kind="triggerstring"),
        win=bp.add_map_string("ZMF_GAMBLE_WIN", f"JACKPOT! +{_points(prize)}"),
        lose=bp.add_map_string("ZMF_GAMBLE_LOSE",
                               f"No luck. The {name} keeps your {_points(cost)}"),
        broke=bp.add_map_string("ZMF_GAMBLE_BROKE",
                                f"You need {_points(cost)} points to gamble"),
        used=bp.add_map_string("ZMF_GAMBLE_USED", used),
        win_all=bp.add_map_string("ZMF_GAMBLE_WIN_ALL",
                                  f"Somebody just hit the {name} jackpot"),
    )


def _vector(p: Point) -> str:
    return f"( {p.x:g}, {p.y:g}, {p.z:g} )"


def gamble_script(at: Point, lines: GambleLines, *, cost: int = COST, prize: int = PRIZE,
                  wins: int = WINS, out_of: int = OUT_OF,
                  per_round: int | None = PER_ROUND,
                  radius: float = RADIUS, height: float = HEIGHT) -> CustomScript:
    """The machine's trigger and thread (module docstring), at *at* (the
    floor in front of the machine)."""
    cost, prize, wins, out_of = int(cost), int(prize), int(wins), int(out_of)
    if cost <= 0 or prize <= 0:
        raise ValueError("a gamble needs a positive cost and prize")
    if not 0 < wins < out_of:
        raise ValueError(f"odds {wins} in {out_of}: need 0 < wins < out_of")
    if per_round is not None and int(per_round) < 1:
        raise ValueError("per_round must be at least 1, or None for no limit")
    limit: list[str] = []
    count: list[str] = []
    if per_round is not None:
        limit = [
            "\tif ( !isdefined( e_who.zmf_gamble_round ) || e_who.zmf_gamble_round != level.round_number )",
            "\t{",
            "\t\te_who.zmf_gamble_round = level.round_number;",
            "\t\te_who.zmf_gamble_plays = 0;",
            "\t}",
            f"\tif ( e_who.zmf_gamble_plays >= {int(per_round)} )",
            "\t{",
            f'\t\te_who IPrintLnBold( &"{lines.used}" );',
            "\t\tcontinue;",
            "\t}",
        ]
        count = ["\te_who.zmf_gamble_plays = e_who.zmf_gamble_plays + 1;"]
    else:
        limit = []
    tell_all = []
    if lines.win_all is not None:
        tell_all = [
            "\t\ta_players = GetPlayers();",
            "\t\tfor ( i = 0; i < a_players.size; i++ )",
            "\t\t{",
            "\t\t\tif ( a_players[ i ] != e_who )",
            "\t\t\t{",
            f'\t\t\t\ta_players[ i ] IPrintLn( &"{lines.win_all}" );',
            "\t\t\t}",
            "\t\t}",
        ]
    body = (
        'level endon( "end_game" );',
        # _zm.gsc:1612 init, :530 set: no trigger while the screen is black.
        'level flag::wait_till( "initial_blackscreen_passed" );',
        f't_gamble = spawn( "trigger_radius_use", {_vector(at)}, 0, {float(radius):g}, '
        f"{float(height):g} );",
        "t_gamble TriggerIgnoreTeam();",
        "t_gamble SetVisibleToAll();",
        't_gamble SetTeamForTrigger( "none" );',
        't_gamble SetCursorHint( "HINT_NOICON" );',
        f't_gamble SetHintString( &"{lines.prompt}" );',
        "level.zmf_gamble_trigger = t_gamble;",
        "while ( true )",
        "{",
        '\tt_gamble waittill( "trigger", e_who );',
        "\tif ( !isplayer( e_who ) || e_who laststand::player_is_in_laststand() )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tn_now = gettime();",
        "\tif ( isdefined( e_who.zmf_gamble_next ) && n_now < e_who.zmf_gamble_next )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        f"\te_who.zmf_gamble_next = n_now + {PRESS_GAP_MS};",
        *limit,
        f"\tif ( !e_who zm_score::can_player_purchase( {cost} ) )",
        "\t{",
        '\t\tzm_utility::play_sound_at_pos( "no_purchase", t_gamble.origin );',
        f'\t\te_who IPrintLnBold( &"{lines.broke}" );',
        "\t\tcontinue;",
        "\t}",
        *count,
        f"\te_who zm_score::minus_to_player_score( {cost} );",
        '\tzm_utility::play_sound_at_pos( "purchase", t_gamble.origin );',
        f"\tif ( RandomInt( {out_of} ) < {wins} )",
        "\t{",
        f"\t\te_who zm_score::add_to_player_score( {prize} );",
        '\t\tzm_utility::play_sound_at_pos( "purchase", t_gamble.origin );',
        f'\t\te_who IPrintLnBold( &"{lines.win}" );',
        *tell_all,
        "\t}",
        "\telse",
        "\t{",
        f'\t\te_who IPrintLnBold( &"{lines.lose}" );',
        "\t}",
        "}",
    )
    limit_text = "no limit" if per_round is None else f"{int(per_round)} per player per round"
    return CustomScript(
        using=(_FLAG, _LASTSTAND, _SCORE, _UTILITY),
        functions=(
            CustomFunction(
                "zmf_gamble",
                body,
                purpose=(
                    f"The gamble machine: pay {cost}, {wins} in {out_of} "
                    f"to win {prize}, {limit_text}.\n"
                    "can_player_purchase _zm_score.gsc:655, minus_to_player_score :556,\n"
                    "add_to_player_score :521; play_sound_at_pos _zm_utility.gsc:3040."
                ),
            ),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_gamble();"),),
        notes=(f"gamble machine: {cost} for a {wins} in {out_of} chance at "
               f"{prize}, {limit_text} (unverified in play)",),
    )
