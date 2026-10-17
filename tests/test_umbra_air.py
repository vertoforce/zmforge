"""Z83: players never spawn in more than one sealed pocket of air.

When start corridors are separate sealed boxes, the linker's occlusion pass
keeps only one sealed pocket (the link log reads ``Filtered N/N+2 inside
clusters``) and players in the others see the floor flicker to the sky at
spawn.  A split start therefore vents each hallway's yard.
"""

from __future__ import annotations

from zmforge.blueprint.elements import Yard
from zmforge.blueprint import Blueprint
from zmforge.emit.mapfile import build_document
from zmforge.script import splitstart as ss
from zmforge.verify.report import Report
from zmforge.verify.umbra_air import CODE, check_umbra_air

from test_splitstart import split_map


def _z83(bp) -> list:
    report = Report()
    check_umbra_air(build_document(bp), report)
    return [f for f in report.findings if f.code == CODE]


def test_sealed_hallways_without_vents_are_reported(monkeypatch) -> None:
    monkeypatch.setattr(Blueprint, "add_yard_vent", lambda *a, **k: None)
    bp, hallways, hub = split_map()
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    found = _z83(bp)
    assert len(found) == 1
    assert "5 separate sealed pockets"  # four hallways and the hub in found[0].message


def test_split_start_vents_every_hallway_and_passes() -> None:
    bp, hallways, hub = split_map()
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    vented = [y for y in bp.elements(Yard) if y.vents]
    assert len(vented) == len(hallways)
    assert _z83(bp) == []


def test_vent_is_a_clip_plugged_hole_in_the_far_wall() -> None:
    bp, _, _ = split_map(halls=1)
    yard = next(iter(bp.elements(Yard)))
    plug = bp.add_yard_vent(yard, id="vent")
    hole = yard.vents[0]
    far = yard.shell.of_side(ss_far(yard))[0].box
    assert hole.mins.y == far.mins.y and hole.maxs.y == far.maxs.y  # through the wall
    assert hole.maxs.z <= yard.interior.maxs.z  # below the yard's ceiling


def ss_far(yard):
    from zmforge.spatial import Facing

    return Facing.of(yard.attached).opposite.side
