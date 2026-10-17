"""Reading build-stage logs for the things that do not fail the build.

The compiler exits 0 on a leak and 0 with missing materials, and the linker
never exits 0 at all, so a stage's log is the only honest account of what
happened (spec 7.3, item K3).  These checks turn a log into findings a caller
can act on rather than a wall of text.
"""

from __future__ import annotations

from typing import Iterable

from ..materials import BENIGN_MISSING
from .report import Report, error, warning

__all__ = ["check_stage_evidence", "check_outcomes"]

#: What the linker prints when the bake never ran.  Measured on a
#: link of a generated map with no ``.led`` beside it; the full line is
#: ``Failed to load Lighting Export Data. Please (re)export from Radiant.
#: Falling back to preview lighting.``  The map still links and still loads,
#: it just renders washed out, so this is a warning and not a failure.
_PREVIEW_LIGHTING = "falling back to preview lighting"

#: What the bake prints per omni light whose shadow it drops; the link still
#: succeeds.  Measured: 26 of zm_corn_maze's barn lamps, every one
#: written ``PRIMARY_NOSHADOWMAP 1``, while zm_dmv and two
#: test maps -- with far denser lamp overlap -- dropped none.
import re as _re

_SHADOW_DROPPED = _re.compile(
    r"Too many shadowing omni lights\. Shadow for light at "
    r"(-?[\d.]+ -?[\d.]+ -?[\d.]+) is being dropped"
)


def check_stage_evidence(stage: str, evidence, log_text: str = "") -> Report:
    """Findings from one stage's parsed evidence."""
    report = Report()
    for line in getattr(evidence, "errors", ()) or ():
        report.add(error("stage_error", f"{stage}: {line.strip()}"))
    if getattr(evidence, "leaked", False):
        path = getattr(evidence, "leakfile", None)
        report.add(
            error(
                "leak",
                f"{stage}: the map is not sealed"
                + (f"; load {path} in Radiant to find the seam" if path else ""),
            )
        )
    for name in getattr(evidence, "missing_materials", ()) or ():
        if name in BENIGN_MISSING:
            report.add(
                warning(
                    "missing_material_benign",
                    f"{stage}: {name!r} is missing, which is expected: it comes from "
                    "a stock prefab and has never mattered",
                )
            )
        else:
            report.add(
                warning(
                    "missing_material",
                    f"{stage}: material {name!r} is missing and will render as the "
                    "error texture",
                )
            )
    if getattr(evidence, "umbra_volume_unset", False):
        report.add(
            error(
                "umbra_unset",
                f"{stage}: no umbra volume was found, so occlusion defaults to a "
                "million-unit cube and walls render as sky",
            )
        )
    if getattr(evidence, "caulk_terrain_patches", False):
        report.add(
            error(
                "caulk_terrain",
                f"{stage}: terrain patches with caulk were discovered; those patches "
                "render black",
            )
        )
    dropped = sorted(set(_SHADOW_DROPPED.findall(log_text or "")))
    if dropped:
        report.add(
            warning(
                "shadows_dropped",
                f"{stage}: the bake dropped the shadow of {len(dropped)} omni "
                "light(s) ('Too many shadowing omni lights'), first at "
                + "; ".join(dropped[:4])
                + ". Shadowless lamps count too (zm_corn_maze's barn): "
                "thin the lamps in that area",
            )
        )
    if log_text and _PREVIEW_LIGHTING in log_text.lower():
        report.add(
            warning(
                "preview_lighting",
                f"{stage}: the lighting bake's output was not found, so the map is "
                "lit with preview lighting and renders washed out",
            )
        )
    return report


def check_outcomes(outcomes: Iterable) -> Report:
    """Findings across a whole chain of :class:`StageOutcome` values."""
    report = Report()
    for outcome in outcomes:
        evidence = getattr(outcome, "evidence_detail", None)
        if evidence is not None:
            report.extend(check_stage_evidence(outcome.stage, evidence))
        if not outcome.ok:
            report.add(
                error(
                    "stage_failed",
                    f"{outcome.stage} failed: "
                    + "; ".join(getattr(outcome, "evidence", []) or ["no evidence"]),
                )
            )
    return report
