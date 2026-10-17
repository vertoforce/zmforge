"""The starting-points testing aid: off by default, and correctly ordered on.

This is the one mechanic in the engine whose failure mode is *silence*. The
stock write is ``_zm.gsc:1201 level.player_starting_points = level.round_number
* 500;`` inside ``init_levelvars()``, which ``zm::init()`` calls at
``_zm.gsc:321`` with no ``wait`` above it, and the framework entry reaches
``zm::init()`` synchronously. So a map that assigns that level var *before*
``zm_usermap::main()`` is overwritten a moment later and nothing anywhere
reports it: the player spawns with 500 and the build looks like it worked.
These tests are the guard on that ordering.

Nothing here says the points arrive in game. They say what the emitted script
says, and where in the file it says it.
"""

from __future__ import annotations

import pytest

from zmforge.emit.scripts import render_server_script
from zmforge.script.custom import Slot
from zmforge.script.tricks import starting_points
from zmforge.verify import check_script_soundness



def test_the_slots_are_after_entry():
    logic = starting_points(25000)
    assert {slot for slot, _ in logic.statements} == {Slot.AFTER_ENTRY}


def test_the_reconciliation_waits_for_a_flag_that_already_exists():
    """The ordering defect this engine has already been bitten by once.

    ``initial_blackscreen_passed`` is created at ``_zm.gsc:318``
    (``init_flags()``), three lines above the ``init_levelvars()`` that sets
    the stock figure, so by AFTER_ENTRY it exists. It is set at
    ``_zm.gsc:545``, after the intro fade, by which point every player that
    started the game has been through ``player_stats_init``.
    """
    body = "\n".join(
        _function_body(starting_points(25000), "zmf_start_points_attach")
    )
    assert 'level flag::wait_till( "initial_blackscreen_passed" );' in body
    # It waits before it touches anybody.
    assert body.index("wait_till") < body.index("getplayers")


def test_it_serves_players_already_here_and_players_who_join():
    body = "\n".join(
        _function_body(starting_points(25000), "zmf_start_points_attach")
    )
    assert "players = getplayers();" in body
    assert 'level waittill( "connected", player );' in body


# --------------------------------------------------------------------------
# What the top-up does to a score
# --------------------------------------------------------------------------
def _function_body(logic, name: str) -> tuple[str, ...]:
    return next(f for f in logic.functions if f.name == name).body


def test_the_top_up_is_a_floor_and_never_lowers_a_score():
    body = _function_body(starting_points(25000), "zmf_start_points_grant")
    assert "if ( self.score < 25000 )" in body
    assert "\tself.score = 25000;" in body


def test_the_top_up_runs_once_per_player():
    body = "\n".join(_function_body(starting_points(25000), "zmf_start_points_grant"))
    assert "isdefined( self.zmf_start_points_done )" in body
    assert "self.zmf_start_points_done = 1;" in body


def test_the_top_up_writes_the_stock_pair():
    """``_zm_stats.gsc:134-135`` writes both, so both are written here."""
    body = _function_body(starting_points(25000), "zmf_start_points_grant")
    assert "\tself.score = 25000;" in body
    assert '\tself.pers[ "score" ] = self.score;' in body


def test_the_top_up_waits_for_the_score_to_exist():
    body = "\n".join(_function_body(starting_points(25000), "zmf_start_points_grant"))
    assert "while ( !isdefined( self.score ) )" in body


def test_a_negative_start_is_refused_at_model_time():
    with pytest.raises(ValueError, match="debt at spawn"):
        starting_points(-1)


def test_zero_is_allowed_because_it_is_a_score():
    logic = starting_points(0)
    assert (Slot.AFTER_ENTRY, "level.player_starting_points = 0;") in logic.statements


def test_the_logic_carries_a_note_that_says_it_is_a_testing_aid():
    """So a blueprint dump shows why the map is rich."""
    assert any("TESTING AID" in note for note in starting_points(25000).notes)


