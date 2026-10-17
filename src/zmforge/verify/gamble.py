"""Z87: every map has exactly one gamble machine, and it can be reached.

P22 (``docs/map-principles.md``): every map carries the gamble
machine at its farthest walk from the spawn (:mod:`zmforge.dressing.gamble`,
mechanic :mod:`zmforge.script.gamble`).  Three questions:

* over the blueprint, once ``Project.commit`` has tried to place it: a map not
  opted out (``bp.signature_gamble = False``, test maps only) has one, or an
  error naming why none fits;
* over the blueprint, with ``Z25``'s own flood: its stand is on floor a player
  walks to from the spawn (:func:`check_gamble_reach`);
* over the written server script: at most one machine thread, its cost is
  checked before it is charged, and its odds are a ``RandomInt`` draw
  (:func:`check_gamble_script`).  No machine at all is a warning there,
  because the script alone cannot tell a test map from a real one.
"""

from __future__ import annotations

import re

from .report import Report, error, warning

__all__ = ["CODE", "check_gamble_blueprint", "check_gamble_reach", "check_gamble_script"]

CODE = "Z87"


def _opted_out(blueprint) -> bool:
    return getattr(blueprint, "signature_gamble", None) is False


def check_gamble_blueprint(blueprint) -> Report:
    report = Report()
    if _opted_out(blueprint):
        return report
    placement = getattr(blueprint, "gamble_machine", None)
    failure = getattr(blueprint, "gamble_failure", None)
    if placement is None and failure is None:
        return report  # not committed yet: Project.commit places it
    if placement is None:
        report.add(error(CODE, f"no gamble machine: {failure}"))
        return report
    custom = getattr(blueprint.script, "custom", None)
    functions = [f for f in getattr(custom, "functions", ()) if f.name == "zmf_gamble"]
    if len(functions) != 1:
        report.add(error(CODE, f"{len(functions)} gamble machine scripts; a map "
                               "has exactly one"))
    return report


def check_gamble_reach(blueprint, flood, report: Report) -> None:
    """The machine's stand is on floor the ``Z25`` flood reaches."""
    placement = getattr(blueprint, "gamble_machine", None)
    if placement is None or _opted_out(blueprint):
        return
    s = placement.stand
    if flood.under(s.x, s.y, s.z, only_reached=True) is None:
        report.add(error(CODE, f"the gamble machine's stand ({s.x:g}, {s.y:g}, "
                               f"{s.z:g}) in {placement.room_id!r} is on no floor a player "
                               "can walk to from the spawn"))


_THREAD = re.compile(r"^\s*function\s+zmf_gamble\s*\(", re.M)


def check_gamble_script(script: str, report: Report) -> None:
    count = len(_THREAD.findall(script or ""))
    if count == 0:
        report.add(warning(CODE, "no gamble machine in the server script "
                                 "(fine for a test map; every finished map has one, P22)"))
        return
    if count > 1:
        report.add(error(CODE, f"{count} gamble machine threads; a map has one"))
    body = script[_THREAD.search(script).start():]
    body = body[:body.find("\n}\n") + 3] if "\n}\n" in body else body
    check = re.search(r"can_player_purchase\(\s*(\d+)\s*\)", body)
    charge = re.search(r"minus_to_player_score\(\s*(\d+)\s*\)", body)
    if not check or not charge or check.group(1) != charge.group(1) or \
            check.start() > charge.start():
        report.add(error(CODE, "the gamble machine charges without first checking the "
                               "player can pay the same amount (points could go negative)"))
    if not re.search(r"RandomInt\(\s*\d+\s*\)\s*<\s*\d+", body):
        report.add(error(CODE, "the gamble machine's odds are not a RandomInt draw"))
