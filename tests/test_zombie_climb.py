"""Z46: the clip ramp over a flight, and the safe spot a walker cannot follow to.

Why this check exists rather than another navmesh assertion: measured,
``cod2map64 -platform pc -navmesh`` laid a perfectly good
mesh up a 17-tread outdoor flight -- one simplified face
from z 34.8 to z 279.9, joined at both ends, three faces from the ground to
the landing -- and in game the zombies still would not climb
it.  Nothing in the package had anything to say: the whole run reported ``0
error(s)``.  What the flight did not have, and every flight in Treyarch's own
source does, is a smooth clip ramp over the treads.
"""

from __future__ import annotations

from zmforge.blueprint.elements import STAIR_CLIP, Massing
from zmforge.blueprint.model import Blueprint
from zmforge.materials import Material
from zmforge.solids.forms import flight, stair_clip
from zmforge.spatial import Facing, Point
from zmforge.verify.climb import check_zombie_climb, zombie_how
from zmforge.verify.reachability import Standing
from zmforge.spatial import Span

ART = Material("t7_concrete_trowelled")


def _codes(report):
    return sorted({f.code for f in report.findings if f.is_error})


# -- the ramp's own arithmetic ---------------------------------------------
def test_the_ramp_meets_the_floor_and_the_last_tread():
    ramp = stair_clip(Point(0, 0, 100), 8, 32.0, 16.0, 128.0, Facing.NORTH)
    assert ramp is not None
    # One tread back from the foot, at the height the flight stands on.
    assert ramp.mins.y == -32.0
    assert ramp.mins.z == 100.0
    # Up to the back of the last tread, at that tread's top.
    assert ramp.maxs.y == 32.0 * 7
    assert ramp.maxs.z == 100.0 + 16.0 * 8


def test_the_ramp_is_never_below_a_tread_it_covers():
    base, count, depth, rise = Point(0, 0, 0), 9, 32.0, 16.0
    ramp = stair_clip(base, count, depth, rise, 128.0, Facing.NORTH)
    run = ramp.maxs.y - ramp.mins.y
    climb = ramp.maxs.z - ramp.mins.z
    for index, tread in enumerate(flight(base, count, depth, rise, 128.0, Facing.NORTH)):
        at_nose = ramp.mins.z + (tread.mins.y - ramp.mins.y) * climb / run
        assert at_nose >= tread.maxs.z - 1e-9, index


def test_one_step_gets_no_ramp():
    assert stair_clip(Point(0, 0, 0), 1, 32.0, 16.0, 128.0, Facing.NORTH) is None


# -- what add_steps installs -----------------------------------------------
def test_add_steps_lays_a_clip_ramp_and_z46_is_quiet():
    blueprint = Blueprint("zm_test")
    blueprint.add_steps(
        Point(0, 0, 0), 6, 32.0, 16.0, 128.0, Facing.NORTH, ART, id="stairs"
    )
    clips = [e for e in blueprint.elements(Massing) if e.note == STAIR_CLIP]
    assert [e.id for e in clips] == ["stairs_clip"]
    assert "Z46" not in _codes(check_zombie_climb(blueprint))


def test_a_flight_with_no_clip_ramp_is_a_z46_error():
    blueprint = Blueprint("zm_test")
    blueprint.add_steps(
        Point(0, 0, 0),
        6,
        32.0,
        16.0,
        128.0,
        Facing.NORTH,
        ART,
        clip_ramp=False,
        id="stairs",
    )
    assert _codes(check_zombie_climb(blueprint)) == ["Z46"]


def test_a_flight_nothing_is_meant_to_climb_may_say_so():
    blueprint = Blueprint("zm_test")
    blueprint.add_steps(
        Point(0, 0, 0),
        6,
        32.0,
        16.0,
        128.0,
        Facing.NORTH,
        ART,
        clip_ramp=False,
        reachable=False,
        id="stairs",
    )
    report = check_zombie_climb(blueprint)
    assert _codes(report) == []
    # And the exception is printed rather than skipped in silence.
    assert any(
        f.code == "Z46" and "declared out of reach" in f.message
        for f in report.findings
    )


# -- the walkers' own movement ---------------------------------------------
def _cell(z: float, x0=0.0, y0=0.0, x1=128.0, y1=128.0) -> Standing:
    return Standing(
        "the top of t",
        "t",
        Span.flat_ok(Point(x0, y0, z), Point(x1, y1, z)),
        z,
        False,
    )


def test_a_walker_steps_eighteen_and_not_nineteen():
    low = _cell(0.0)
    assert zombie_how(low, _cell(18.0, 0.0, 128.0, 128.0, 256.0)) == "walked up"
    assert zombie_how(low, _cell(19.0, 0.0, 128.0, 128.0, 256.0)) is None


def test_a_walker_does_not_jump_what_a_player_jumps():
    """39 units is ``Z25``'s jump.  Nothing in the shipped AI makes it."""
    low = _cell(0.0)
    assert zombie_how(low, _cell(39.0, 0.0, 128.0, 128.0, 256.0)) is None
