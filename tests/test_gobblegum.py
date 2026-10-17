"""GobbleGum machines: placement beside the boxes and the four-player gate."""

from __future__ import annotations

import pytest

from zmforge.blueprint.model import Blueprint
from zmforge.script.custom import Slot
from zmforge.script.gobblegum import (
    MAX_BGB_PLAYERS,
    TARGETNAME,
    gobblegum_gate,
    gobblegum_machines,
    place_gobblegum_machines,
)
from zmforge.spatial import Facing, Point


def _gate_text(custom) -> str:
    return "\n".join(line for f in custom.functions for line in f.body)


def test_gate_waits_for_more_than_four_and_then_hides_every_machine():
    custom = gobblegum_gate("ZMF_BGB_OFF")
    text = _gate_text(custom)
    assert f"while ( GetPlayers().size <= {MAX_BGB_PLAYERS} )" in text
    assert 'level flag::wait_till( "initial_blackscreen_passed" );' in text
    assert f'GetEntArray( "{TARGETNAME}", "targetname" )' in text
    assert "HideZBarrierPiece( i )" in text
    assert "zm_unitrigger::unregister_unitrigger( s_stub );" in text
    assert 'IPrintLnBold( &"ZMF_BGB_OFF" );' in text
    assert custom.in_slot(Slot.ZONE_HOOK) == ("level thread zmf_bgb_gate();",)
    assert "level thread zmf_bgb_gate();" not in custom.in_slot(Slot.AFTER_ENTRY)
    assert r"scripts\zm\_zm_unitrigger" in custom.using


def test_gate_says_its_line_once_not_in_the_loop():
    body = gobblegum_gate("X").functions[0].body
    say = [i for i, line in enumerate(body) if "IPrintLnBold" in line]
    loop = body.index("while ( true )")
    assert len(say) == 1 and say[0] < loop


def _room_with_box() -> Blueprint:
    from zmforge.spatial import Bounds

    bp = Blueprint("zm_bgb_test")
    bp.add_room(Bounds(Point(-512, -512, 0), Point(512, 512, 256)), id="hall")
    bp.place_mystery_box(Point(0, -440, 16), Facing.NORTH, id="box")
    return bp


def test_two_machines_go_beside_the_box_on_its_wall_line():
    bp = _room_with_box()
    machines = place_gobblegum_machines(bp, 2)
    assert len(machines) == 2 == len(gobblegum_machines(bp))
    for machine in machines:
        assert machine.facing is Facing.NORTH
        assert machine.position.y == -440
        assert abs(machine.position.x) >= 128
    assert any("zmf_bgb_gate" in f.name for c in [bp.script.custom] for f in c.functions)


def test_zero_places_nothing_and_emits_no_gate():
    bp = _room_with_box()
    assert place_gobblegum_machines(bp, 0) == []
    assert not any(f.name == "zmf_bgb_gate" for f in bp.script.custom.functions)


def test_too_many_is_an_error_not_a_short_map():
    bp = _room_with_box()
    with pytest.raises(ValueError, match="only"):
        place_gobblegum_machines(bp, 50)
