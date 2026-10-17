"""``Z88``: indoor air is lit and exposed as indoors, all the way through.

WHY
---
Walking from room to room must not flash.  A room lit by the outdoor probe
looks lit by the sun, and an unprobed barricade closet looks blown out, as
if auto exposure swung between "outdoor" and "indoor".  The failure this
guards: every room is roofed, but each reflection probe box is the room's bare
interior, so the wall-thick threshold of every doorway, slot and window lies
in no probe box, and a closet behind a barricade gets no probe at all.

A point in no probe box falls to the sun volume's global probe, which is
the outdoor one (``t7.def.json``: ``volume_sun`` ``global_fill_color`` fills
"occluded parts of the global probe"), and a probe carries an exposure of
its own (``reflection_probe`` ``evcomp``: "EV compensation to final probe
exposure"; the mod tools' lighting workflow documentation, section 5, "probe
exposure").  So an indoor map built that way crosses a slice of "outdoors" at
every doorway.

THE RULE
--------
With probes on (``Enclosure.probe``):

* every closet (:class:`~zmforge.blueprint.elements.Yard`) lies inside a
  probe box: a closet is indoor air;
* every opening in a roofed room's wall (doorway, observation slot,
  barricade window) is inside a probe box at mid-wall, and that box belongs
  to an indoor space (a roofed room or a closet).  Between two indoor rooms
  that means no "outdoor" gap; between an indoor and an outdoor room it puts
  the change of probe at the indoor room's edge, inside the box blend, which
  is the transition.

An unroofed room is outdoors by declaration (``roofed=False``, sky above),
and nothing here asks it to change.  The fix is in
:meth:`zmforge.blueprint.model.Blueprint.probe_boxes`.

Unverified in play: that the global probe is what made the flash.  The
check holds the setup to the one shipped rule that is certain (indoor air in
an indoor probe), whatever the engine keys its exposure on.
"""

from __future__ import annotations

from .report import Report, error

__all__ = ["CODE", "check_indoor_light"]

CODE = "Z88"


def check_indoor_light(bp) -> Report:
    from ..blueprint.elements import Enclosure, Room, Yard

    report = Report()
    enclosures = bp.elements(Enclosure)
    if not enclosures or not enclosures[0].probe:
        return report  # Z28 already says a map without probes is flatter
    boxes = bp.probe_boxes()
    indoor_ids = {r.id for r in bp.elements(Room) if r.roofed}
    indoor_ids |= {y.id for y in bp.elements(Yard)}
    indoor_boxes = [box for owner, box in boxes if owner in indoor_ids]

    for yard in bp.elements(Yard):
        if not any(box.encloses(yard.interior, tolerance=1e-6) for _, box in boxes):
            report.add(error(
                CODE,
                f"closet {yard.id} is in no reflection probe box, so it is lit and "
                "exposed by the sun volume's global (outdoor) probe: an indoor "
                "space set up as outdoors, so it looks blown out",
                yard.id,
            ))

    for room in bp.elements(Room):
        if not room.roofed:
            continue
        for index, hole in enumerate(room.aperture_boxes):
            mid = hole.centre
            if any(box.holds(mid, tolerance=1e-6) for box in indoor_boxes):
                continue
            outdoor = any(box.holds(mid, tolerance=1e-6) for _, box in boxes)
            what = ("only an outdoor room's probe box" if outdoor
                    else "no probe box (the global outdoor probe)")
            report.add(error(
                CODE,
                f"opening {index} of indoor room {room.id} at "
                f"({mid.x:g}, {mid.y:g}, {mid.z:g}) is in {what}: walking through "
                "it crosses an outdoor lighting and exposure setup between "
                "indoor rooms, with no transition, so the screen flashes between "
                "rooms",
                room.id,
            ))
    return report
