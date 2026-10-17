"""One pass over every check in the table, with a pass/fail line each.

:mod:`zmforge.verify` has three entry points because a mistake can be caught at
three different moments, and a caller who runs one of them learns nothing about
the other two.  This module runs whichever of them the caller can supply
evidence for, joins the findings back onto
:data:`~zmforge.verify.registry.CHECKS`, and prints one line per requirement.

The point is the ``SKIP`` and ``MANUAL`` lines as much as the ``PASS`` ones.  A
map that passes forty checks and skips eight has not been checked forty-eight
times, and the only way to know which eight is to print them.

``docs/playable-map-requirements.md`` is the prose against this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .registry import BY_CODE, CHECKS, Check
from .report import Finding, Report

__all__ = ["Outcome", "Audit", "run_all", "PASS", "FAIL", "WARN", "SKIP", "MANUAL"]

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"
MANUAL = "MANUAL"

#: A check no row of the table claims.  It is printed as a failure rather than
#: dropped: a finding nobody can look up is worse than a noisy line, and the
#: suite asserts this bucket is empty for the shipped recipes.
UNREGISTERED = "unregistered"


@dataclass(frozen=True, slots=True)
class Outcome:
    """One requirement's verdict."""

    check: Check
    status: str
    ran: tuple[str, ...]
    findings: tuple[Finding, ...] = ()

    @property
    def wanted(self) -> tuple[str, ...]:
        return tuple(self.check.where.split())

    @property
    def partial(self) -> bool:
        """Did some, but not all, of this check's entry points run?"""
        return bool(self.ran) and set(self.ran) != set(self.wanted)

    def line(self) -> str:
        head = f"{self.status:<6} {self.check.code:<22} {self.check.rule}"
        if self.status == SKIP:
            missing = ", ".join(self.wanted)
            return f"{head}\n{'':<6} └─ not run: no {missing} evidence was supplied"
        if self.status == MANUAL:
            return f"{head}\n{'':<6} └─ {self.check.note}"
        tail = []
        if self.partial:
            tail.append(
                f"{'':<6} └─ only the {', '.join(self.ran)} side ran; "
                f"the {', '.join(w for w in self.wanted if w not in self.ran)} "
                "side was not checked"
            )
        for finding in self.findings:
            tail.append(f"{'':<6} └─ {finding}")
        return "\n".join([head, *tail])


@dataclass(frozen=True, slots=True)
class Audit:
    """Every requirement's verdict, plus the findings that produced them."""

    outcomes: tuple[Outcome, ...]
    report: Report
    ran: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not any(outcome.status == FAIL for outcome in self.outcomes)

    def by_status(self, status: str) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.status == status)

    def counts(self) -> dict[str, int]:
        tally = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0, MANUAL: 0}
        for outcome in self.outcomes:
            tally[outcome.status] = tally.get(outcome.status, 0) + 1
        return tally

    def render(self) -> str:
        lines = [outcome.line() for outcome in self.outcomes]
        tally = self.counts()
        lines.append("")
        lines.append(
            f"{tally[PASS]} passed, {tally[FAIL]} failed, {tally[WARN]} with "
            f"warnings, {tally[SKIP]} not run, {tally[MANUAL]} for a human."
        )
        if tally[SKIP]:
            lines.append(
                "Checks that did not run are not checks that passed: "
                + ", ".join(o.check.code for o in self.by_status(SKIP))
            )
        return "\n".join(lines)


def _status(findings: Sequence[Finding]) -> str:
    if any(f.is_error for f in findings):
        return FAIL
    if findings:
        return WARN
    return PASS


def run_all(
    project=None,
    *,
    blueprint=None,
    stage_outcomes: Iterable | None = None,
    navmesh=None,
    strict_materials: bool = False,
    presentation: bool = True,
    player_slots: int | None = None,
) -> Audit:
    """Run every check the caller has evidence for, and score the whole table.

    ``blueprint``
        the model, checked before anything is written.  Defaults to
        ``project.blueprint``, which is the real model only when the project
        was built from a recipe: :meth:`zmforge.Project.open` synthesises a
        blueprint that has adopted the map text and has no rooms, zones or
        lamps of its own, so a caller opening a map off disk should pass
        ``blueprint=False`` and take the ``SKIP`` lines.
    ``project``
        supplies the written files.  Its ``.map``, scripts and manifest are
        read if they are all there, and the file-level checks are skipped if
        they are not.
    ``stage_outcomes``
        build-stage results.  Left out, the eight log-reading checks skip:
        this process did not run a build and has nothing to read.
    ``navmesh``
        the path of the ``<map>_navmesh.hkt`` the compiler wrote.  Left out,
        ``H1`` skips, and a skipped ``H1`` means nobody has asked what the
        zombies can reach -- ``Z25`` answers for the player and no more.  It
        needs the blueprint too, because the finding is the difference between
        the two.
    """
    from . import blueprint as run_blueprint, files as run_files, stages as run_stages

    report = Report()
    ran: list[str] = []

    model = project.blueprint if (blueprint is None and project is not None) else blueprint
    if model:
        report.extend(run_blueprint(model, strict_materials=strict_materials))
        ran.append("blueprint")

    if project is not None and _files_present(project):
        report.extend(
            run_files(
                project,
                strict_materials=strict_materials,
                presentation=presentation,
            )
            if player_slots is None
            else _files_with_slots(project, strict_materials, presentation, player_slots)
        )
        ran.append("files")

    if stage_outcomes is not None:
        report.extend(run_stages(stage_outcomes))
        ran.append("stages")

    if navmesh is not None and model:
        from .navmesh import check_navmesh_file

        report.extend(check_navmesh_file(model, navmesh))
        ran.append("navmesh")

    return _score(report, tuple(ran))


def _files_with_slots(project, strict_materials, presentation, player_slots) -> Report:
    from .files import check_written_files

    paths = project.paths()
    return check_written_files(
        paths["map"],
        paths["server_script"],
        paths["client_script"],
        paths["manifest"],
        map_name=project.name,
        strict_materials=strict_materials,
        loading_image_path=paths["loading_image"] if presentation else None,
        preview_image_path=paths["preview_image"] if presentation else None,
        player_slots=player_slots,
        weapon_table_path=paths.get("weapon_table"),
        # The same list the run above passes: a map checked with a seat count
        # must not be checked for less than one checked without one, and a
        # declared string with no .str is a link that stops (Z24).
        localized_strings_path=paths.get("localized_strings"),
        props_gdt_path=paths.get("props_gdt"),
        model_export_dir=paths.get("model_export_dir"),
        collmap_dir=paths.get("collmap_dir"),
    )


def _files_present(project) -> bool:
    paths = project.paths()
    return all(
        Path(paths[role]).exists()
        for role in ("map", "server_script", "client_script", "manifest")
    )


def _score(report: Report, ran: tuple[str, ...]) -> Audit:
    found: dict[str, list[Finding]] = {}
    for finding in report:
        found.setdefault(finding.code, []).append(finding)

    outcomes: list[Outcome] = []
    for check in CHECKS:
        wanted = tuple(check.where.split())
        if not check.is_automated:
            outcomes.append(Outcome(check, MANUAL, ()))
            continue
        mine = tuple(w for w in wanted if w in ran)
        if not mine:
            outcomes.append(Outcome(check, SKIP, ()))
            continue
        findings = tuple(found.get(check.code, ()))
        outcomes.append(Outcome(check, _status(findings), mine, findings))

    stray = sorted(code for code in found if code not in BY_CODE)
    for code in stray:
        findings = tuple(found[code])
        outcomes.append(
            Outcome(
                Check(
                    code,
                    "a finding whose code is in no row of the table; either the "
                    "check is new and registry.py was not updated, or the code "
                    "is a typo",
                    UNREGISTERED,
                ),
                FAIL,
                (UNREGISTERED,),
                findings,
            )
        )
    return Audit(tuple(outcomes), report, ran)
