"""The four build stages, and the verdict each one gets.

WHY this module exists apart from the runners: on this toolchain the exit
code is not the answer (Section 10, K3). The linker returned 154000 and
2000 on seven successful links and never 0; the compiler returns 0 with a
leak and 0 with missing materials. So every stage here is judged by what it
printed and what it left on disk, and the exit code is carried through only
as a fact about the process.

The rules, from Section 7.3:

* refresh - exit 0 and no ``ERROR:`` line;
* compile - exit 0 **and** no leak banner **and** no ``ERROR:`` line;
* link    - no ``ERROR:`` line **and** each of the two fastfiles sized above zero
  **and**, when the link's own reports say it packed a sound bank for this
  map, that bank carrying audio (a bank of aliases with no audio
  behind them linked clean and crashed the game at load), whatever the exit
  code says;
* bake    - it is a GUI program: refused outright when the runner cannot
  promise a display, killed by the stall detector when it was allowed to
  start and then made no progress (K4), or by the Wine runner's time limit;
  good only when it printed no error, left ``<map>.led`` on disk, and - when
  Radiant's own log was captured - that log says ``Export Done``.

Full logs are never returned to a caller. Section 7.4 asks for the raw
bytes on disk next to the result and a structured summary in hand, so a
caller that wants the 97 seconds of linker chatter opens ``log_path``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Callable, Sequence

from .. import mapdoc
from ..errors import NoInteractiveDesktop, ToolchainError
from ..verify.report import Finding, error, warning
from .evidence import (
    BENIGN_MISSING_MATERIALS,
    StageEvidence,
    decode_tool_output,
    read_bake_log,
    read_compile_log,
    read_link_log,
    read_refresh_log,
)
from .layout import LANGUAGE_PREFIXES, ToolsLayout, resolve_layout
from .runner import LocalRunner, RunResult, StageRunner

#: ``Linking "<zone>" (...): processing...`` / ``unchanged...``, one per fastfile.
_LINK_HEADER = re.compile(
    r'Linking\s+"([^"]+)"[^\n]*?(?::\s*(processing|unchanged))?\.\.\.', re.IGNORECASE
)
_DONE = re.compile(r"\bdone:\s*\S+", re.IGNORECASE)
#: Lines only docker itself prints: the tool never started, whatever is on disk.
_DOCKER_FAILURE = re.compile(
    r"^docker: |Error response from daemon|Cannot connect to the Docker daemon"
    r"|error during connect",
    re.IGNORECASE | re.MULTILINE,
)
#: Exit codes no linker run produces: docker's own (125 daemon error, 126
#: cannot execute, 127 not found) and 128+N for a process killed by signal N
#: (HUP, INT, QUIT, ABRT, KILL, SEGV, TERM).  The linker's own codes are
#: 154000 and 2000; a negative code is a POSIX signal death.
_NOT_A_LINK_EXIT = {125, 126, 127} | {128 + n for n in (1, 2, 3, 6, 9, 11, 15)}
#: Filesystem timestamps can be up to 2 s coarse (FAT) and Wine rounds them.
_MTIME_SLACK_S = 2.0


def link_zone_states(text: str) -> dict[str, str]:
    """``{zone: mode}`` for every zone whose ``Linking`` block reached ``done:``.

    *mode* is ``"processing"``, ``"unchanged"`` (a cached re-link, which leaves
    the fastfile's mtime alone) or ``""`` when the header did not say.  A zone
    whose header is followed by the next header or the end of the log without a
    ``done:`` is absent: the linker did not finish it.
    """
    states: dict[str, str] = {}
    headers = list(_LINK_HEADER.finditer(text))
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        if _DONE.search(text, match.end(), end):
            states[match.group(1).lower()] = (match.group(2) or "").lower()
    return states


__all__ = [
    "BAKE_QUALITIES",
    "CHAIN_STAGES",
    "ChainOutcome",
    "StageOutcome",
    "Toolchain",
]


# Section 7.3: the bake's quality switch takes exactly these three.
BAKE_QUALITIES: tuple[str, ...] = ("draft", "medium", "final")

# Stage keys ``run_chain`` understands. The compile appears twice because
# the two modes are different stages to a caller: one rebuilds geometry and
# navmesh, the other only moves entities around (Section 7.5).
CHAIN_STAGES: tuple[str, ...] = (
    "refresh",
    "compile_full",
    "compile_entities",
    "bake",
    "link",
)

_DEFAULT_STALL_WINDOW_S = 60.0  # Section 7.3: the measured headless bake.


@dataclass
class StageOutcome:
    """One stage, its verdict, and where to read the rest.

    ``ok`` is derived from ``details`` and from what landed on disk; it is
    never assigned from ``exit_code``. ``evidence`` is the short, human-
    readable "why" - the error lines, the notable log banners, the file that
    should have been written and was not - so a caller can print a failure
    without opening the log.
    """

    stage: str
    ok: bool
    evidence: list[str] = field(default_factory=list)
    exit_code: int = 0
    duration_s: float = 0.0
    log_path: str = ""
    artifacts: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    details: StageEvidence | None = None

    def __str__(self) -> str:  # pragma: no cover - operator convenience
        verdict = "ok" if self.ok else "FAILED"
        return f"{self.stage}: {verdict} ({self.duration_s:.1f}s, log {self.log_path})"


@dataclass
class ChainOutcome:
    """A sequence of stages and the first one whose evidence said no.

    ``ok`` and ``failed_stage`` are computed rather than stored so they can
    never disagree with the outcomes they summarise.
    """

    outcomes: list[StageOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(outcome.ok for outcome in self.outcomes)

    @property
    def failed_stage(self) -> str | None:
        for outcome in self.outcomes:
            if not outcome.ok:
                return outcome.stage
        return None


def _describe(evidence: StageEvidence, extra: Sequence[str] = ()) -> list[str]:
    """Flatten a parsed log into the lines worth showing a human."""
    lines = list(evidence.errors)
    lines.extend(evidence.notes)
    lines.extend(f"missing material: {name}" for name in evidence.missing_materials)
    lines.extend(extra)
    return lines


def _log_findings(evidence: StageEvidence) -> list[Finding]:
    """Findings every stage shares: one per ``ERROR:`` line, one per material."""
    found = [error("stage_error", line) for line in evidence.errors]
    for name in evidence.missing_materials:
        if name in BENIGN_MISSING_MATERIALS:
            found.append(warning("missing_material", f"{name} (known benign, K13)"))
        else:
            found.append(error("missing_material", name))
    return found


class Toolchain:
    """Runs the mod tools against one installation.

    The layout says where everything is, the runner says how a process is
    started; this class owns only the argument order and the verdicts, which
    is why it can be exercised end to end with stub executables.
    """

    def __init__(
        self,
        tools: ToolsLayout | str | PurePath,
        runner: StageRunner | None = None,
        *,
        log_dir: Path | str | None = None,
        stall_window_s: float = _DEFAULT_STALL_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.layout = resolve_layout(tools)
        self.runner: StageRunner = runner if runner is not None else LocalRunner()
        self.log_dir = Path(log_dir) if log_dir is not None else Path.cwd() / "zmforge-logs"
        self.stall_window_s = stall_window_s
        self.clock = clock

    # -- stages ------------------------------------------------------------

    def refresh_assets(self) -> StageOutcome:
        """``gdtdb.exe /update``: rebuild the asset database.

        Only needed after assets change; a generated map made of stock
        assets does not need it on every build (Section 7.3).
        """
        self._require_directories(self.layout.bin_dir)
        command = [str(self.layout.gdt_database), "/update"]
        result, evidence, log_path = self._run("refresh", command, read_refresh_log)
        ok = result.exit_code == 0 and evidence.clean
        extra = [] if ok else [f"exit code {result.exit_code}"]
        return self._outcome("refresh", ok, result, evidence, log_path, command, extra=extra)

    def compile_bsp(self, map_name: str, mode: str = "entities") -> StageOutcome:
        """``cod2map64.exe``: geometry and navigation, or entities only (B2).

        ``entities`` is the seconds-long iteration loop and deliberately
        does not touch geometry or navmesh; ``full`` is the one that must
        carry ``-navmesh -navvolume``, without which the AI has no pathing.
        """
        if mode == "entities":
            mode_flags = ["-onlyents"]
        elif mode == "full":
            mode_flags = ["-navmesh", "-navvolume"]
        else:
            raise ToolchainError(f"compile mode must be 'entities' or 'full', not {mode!r}")

        self._require_geometry_matches_document(map_name)

        self._require_directories(self.layout.bin_dir, self.layout.compiler_output_dir)
        bsp = self.layout.compiled_bsp(map_name)
        command = [
            str(self.layout.compiler),
            "-platform",
            "pc",
            *mode_flags,
            "-loadFrom",
            str(self.layout.map_source(map_name)),
            str(bsp),
        ]
        result, evidence, log_path = self._run(
            f"compile_{mode}", command, read_compile_log, map_name=map_name
        )

        # The BSP is the compile's product and its absence is a failure; the
        # two navigation files are not, because the compiler skips them by
        # design when the map has no `nav_volume` brush. Measured on a test map:
        # exit 0, no `ERROR:`, no leak, BSP
        # 519,800 bytes and navmesh 25,035 bytes written - and no navvolume on
        # disk at all, under its own
        # "WARNING: NavVolume generation is skipped ... there is no nav_volume
        # brush in the level", printed one line above "Writing
        # <map>_navvolume.hkt". So the tool announces a file it does not write,
        # which is precisely the case a log-only verdict cannot see; and
        # requiring all three would fail every map that has no flying enemies.
        required = [bsp]
        optional: list[PurePath] = []
        if mode == "full":
            optional += [self.layout.navmesh(map_name), self.layout.navvolume(map_name)]
        written, missing_required = self._split_written(required)
        written_optional, missing_optional = self._split_written(optional)
        artifacts = written + written_optional

        extra: list[str] = []
        findings: list[Finding] = []
        if evidence.leaked:
            where = evidence.leakfile or "no leakfile path in the log"
            extra.append(f"map leaked; leakfile {where}")
            findings.append(error("leak", f"map is not sealed; leakfile: {where}"))
        if result.exit_code != 0:
            extra.append(f"exit code {result.exit_code}")
        for path in missing_required:
            extra.append(f"not written or empty: {path}")
            findings.append(error("missing_output", str(path)))
        for path in missing_optional:
            extra.append(f"not written (the log says whether that was deliberate): {path}")
            findings.append(warning("missing_output", str(path)))

        ok = (
            result.exit_code == 0
            and not evidence.leaked
            and evidence.clean
            and not missing_required
        )
        return self._outcome(
            f"compile_{mode}",
            ok,
            result,
            evidence,
            log_path,
            command,
            extra=extra,
            artifacts=artifacts,
            findings=findings,
        )

    def _require_geometry_matches_document(self, map_name: str) -> None:
        """Refuse to compile a ``.map`` the map's document does not describe.

        The shared document records the hash of the geometry it belongs to.  A
        build that ignores that can compile last week's ``.map`` against this
        week's script plan, weapon prices and prop list and produce a map that
        loads and is wrong in ways no log line mentions -- which is precisely
        the staleness a sidecar format is accused of and the reason the hash is
        written in the first place.  Refuse, naming both hashes, and let the
        person decide which of the two files is the stale one.

        A map with no document beside it is not checked: a hand-authored or
        imported ``.map`` is a legitimate thing to compile, and there is nothing
        to disagree with it.
        """
        doc_path = Path(str(self.layout.map_source_dir)) / f"{map_name}.blueprint.json"
        if not doc_path.is_file():
            return
        try:
            mapdoc.verify_geometry(doc_path, require_map_file=True)
        except mapdoc.GeometryMismatch as problem:
            raise ToolchainError(str(problem)) from problem

    def bake_lights(self, map_name: str, quality: str = "medium") -> StageOutcome:
        """``radiant_modtools.exe``: bake lighting into ``<map>.led`` (B3).

        Two defences, because this one program cost four minutes of hang per
        attempt (K4). First: a runner that cannot promise an interactive
        desktop is refused before anything starts - a process with no
        desktop will never draw a window. Second: even
        where a desktop is claimed, the process is watched and killed once
        it has made no progress for the stall window, because "claimed" is
        not "had".
        """
        if quality not in BAKE_QUALITIES:
            raise ToolchainError(
                f"bake quality must be one of {', '.join(BAKE_QUALITIES)}, not {quality!r}"
            )
        if not getattr(self.runner, "provides_interactive_desktop", False):
            raise NoInteractiveDesktop(
                f"{type(self.runner).__name__} cannot provide an interactive desktop; "
                "the lighting bake is a GUI program and hangs without a desktop session"
            )

        self._require_directories(self.layout.bin_dir, self.layout.compiler_output_dir)
        command = [
            str(self.layout.light_baker),
            "-ledSilent",
            f"+{quality}",
            "+localprobes",
            "+forceclean",
            "+recompute",
            str(self.layout.map_source(map_name)),
        ]
        result, evidence, log_path = self._run(
            "bake",
            command,
            read_bake_log,
            map_name=map_name,
            stall_window_s=self.stall_window_s,
        )

        led = self.layout.led(map_name)
        artifacts, missing = self._split_written([led])
        extra: list[str] = []
        findings: list[Finding] = []
        if result.timed_out:
            extra.append(f"did not finish within {result.duration_s:.0f}s and was killed")
            findings.append(error("bake_unfinished", "bake ran past its time limit"))
        elif result.stalled:
            extra.append(
                f"no output and no CPU progress for {self.stall_window_s:g}s: "
                "needs interactive desktop"
            )
            findings.append(
                error("needs_interactive_desktop", "bake made no progress and was killed")
            )
        for path in missing:
            extra.append(f"not written or empty: {path}")
            if not result.stalled:
                findings.append(warning("missing_output", str(path)))

        ok = not result.stalled and evidence.clean and not missing
        return self._outcome(
            "bake",
            ok,
            result,
            evidence,
            log_path,
            command,
            extra=extra,
            artifacts=artifacts,
            findings=findings,
        )

    def link_fastfiles(self, map_name: str, language: str = "english") -> StageOutcome:
        """``linker_modtools.exe``: build the two fastfiles (B4, B5).

        The verdict ignores the linker's own exit codes (154000, 2000). Each
        of the two fastfiles has to be on disk with a size above zero *and*
        this run's log has to show the linker finishing it: a ``Linking
        "<zone>"`` block that reaches ``done:``.  A zone the linker rebuilt
        (``processing``) must also have a fastfile no older than this stage's
        start; a cached re-link (``unchanged``) leaves the mtime alone, so age
        is only tested for rebuilt zones, and only where the runner can see
        mtimes.  A killed linker (exit 137, no output) or a docker that never
        started it (exit 125, ``Error response from daemon``) leaves the last
        build's fastfiles in place, so those are failures whatever is on disk.
        """
        prefix = LANGUAGE_PREFIXES.get(language)
        if prefix is None:
            raise ToolchainError(f"unknown link language {language!r}")

        self._require_directories(self.layout.bin_dir, self.layout.fastfile_dir(map_name))
        command = [
            str(self.layout.linker),
            "-language",
            language,
            "-modsource",
            map_name,
        ]
        started = time.time()
        result, evidence, log_path = self._run(
            "link", command, read_link_log, map_name=map_name
        )
        log_text = decode_tool_output(result.stdout_bytes)

        expected = [
            self.layout.fastfile(map_name),
            self.layout.localised_fastfile(map_name, prefix),
        ]
        artifacts, missing = self._split_written(expected)
        extra: list[str] = []
        findings: list[Finding] = []
        for path in missing:
            extra.append(f"fastfile missing or empty: {path}")
            findings.append(error("missing_fastfile", str(path)))
        if result.stalled:
            # A cached re-link leaves the fastfiles' mtimes alone, so a pair
            # of fastfiles on disk proves nothing about *this* run: a linker
            # killed on timeout, or one that never ran, leaves
            # the previous build's files exactly where they were.
            extra.append(
                "the link did not finish (killed on timeout), so any fastfile "
                "on disk is from an earlier run"
            )
            findings.append(
                error("link_unfinished", "linker killed on timeout; fastfiles are stale")
            )

        unfinished = self._link_not_finished(result, log_text, expected, started)
        for message in unfinished:
            extra.append(message)
            findings.append(error("link_unfinished", message))

        sound = self._packed_sound_report(map_name, language)
        for finding in sound:
            extra.append(finding.message)
        findings.extend(sound)

        ok = (
            evidence.clean
            and not missing
            and not result.stalled
            and not unfinished
            and not sound.errors
        )
        return self._outcome(
            "link",
            ok,
            result,
            evidence,
            log_path,
            command,
            extra=extra,
            artifacts=artifacts,
            findings=findings,
        )

    def _link_not_finished(
        self,
        result: RunResult,
        text: str,
        expected: Sequence[PurePath],
        started: float,
    ) -> list[str]:
        """Why this run's log does not prove it wrote *expected*; empty if it does."""
        problems: list[str] = []
        if result.exit_code < 0 or result.exit_code in _NOT_A_LINK_EXIT:
            problems.append(
                f"the linker or its container died (exit {result.exit_code}); "
                "any fastfile on disk is from an earlier run"
            )
        if _DOCKER_FAILURE.search(text):
            problems.append(
                "docker failed before the linker ran; any fastfile on disk is "
                "from an earlier run"
            )
        states = link_zone_states(text)
        mtime_of = getattr(self.runner, "mtime_of", None)
        for path in expected:
            zone = PurePath(str(path)).stem.lower()
            if zone not in states:
                problems.append(f"the log never shows the link of {zone!r} finishing (no done:)")
                continue
            if states[zone] == "unchanged" or mtime_of is None:
                continue
            mtime = mtime_of(path)
            if mtime is not None and mtime < started - _MTIME_SLACK_S:
                problems.append(
                    f"{path} is older than this link: the linker said it rebuilt "
                    f"{zone!r} but the file on disk is an earlier build's"
                )
        return problems

    def _packed_sound_report(self, map_name: str, language: str):
        """Did the link pack a sound bank, and does that bank carry audio?

        A clean link is not evidence that a packed asset is usable. This
        exact stage once returned a good verdict on a map whose
        sound bank held aliases and no audio, and the game took an access
        violation on it part way through loading the level. The rule and the
        reasoning are in :func:`zmforge.verify.check_linked_sound_audio`;
        this reads the three reports the link left beside the fastfiles and
        hands them to it, once per zone, because the bank the game named was
        the language one and the ``all`` zone can fail the same way.

        Nothing here can fail the stage for the wrong reason: a runner too
        old to read files, or a report the link never wrote, leaves the
        report empty or carrying a warning.
        """
        from ..verify.files import check_linked_sound_audio
        from ..verify.report import Report

        report = Report()
        read = getattr(self.runner, "read_text", None)
        if read is None:
            return report
        for zone in dict.fromkeys(("all", language)):
            try:
                report.extend(
                    check_linked_sound_audio(
                        map_name,
                        pool_report=read(self.layout.link_pool_report(map_name, zone)),
                        asset_list=read(self.layout.link_asset_list(map_name, zone)),
                        deps=read(self.layout.link_deps(map_name, zone)),
                        label=f"link, {zone} zone",
                    )
                )
            except OSError:  # pragma: no cover - the runner already swallows these
                continue
        return report

    # -- the chain ---------------------------------------------------------

    def run_chain(
        self,
        map_name: str,
        stages: Sequence[str] = ("compile_full", "link"),
        stop_on_failure: bool = True,
        *,
        quality: str = "medium",
        language: str = "english",
    ) -> ChainOutcome:
        """Run *stages* in order and stop at the first failing verdict (B9).

        Stopping is the point: a link after a leaked compile produces a
        fastfile that loads and then plays wrong, which costs a playtest to
        discover.
        """
        steps: dict[str, Callable[[], StageOutcome]] = {
            "refresh": self.refresh_assets,
            "compile_full": lambda: self.compile_bsp(map_name, mode="full"),
            "compile_entities": lambda: self.compile_bsp(map_name, mode="entities"),
            "bake": lambda: self.bake_lights(map_name, quality=quality),
            "link": lambda: self.link_fastfiles(map_name, language=language),
        }
        unknown = [name for name in stages if name not in steps]
        if unknown:
            raise ToolchainError(
                f"unknown chain stage(s) {', '.join(unknown)}; "
                f"known: {', '.join(CHAIN_STAGES)}"
            )

        chain = ChainOutcome()
        for name in stages:
            outcome = steps[name]()
            chain.outcomes.append(outcome)
            if stop_on_failure and not outcome.ok:
                break
        return chain

    # -- plumbing ----------------------------------------------------------

    def _run(
        self,
        stage: str,
        command: Sequence[str],
        reader: Callable[[str], StageEvidence],
        *,
        map_name: str | None = None,
        stall_window_s: float | None = None,
        timeout_s: float | None = None,
    ) -> tuple[RunResult, StageEvidence, str]:
        """Start the stage, persist its raw bytes, parse what it printed."""
        result = self.runner.run(
            list(command),
            layout=self.layout,
            stage=stage,
            stall_window_s=stall_window_s,
            timeout_s=timeout_s,
        )
        log_path = self._persist(stage, map_name, result.stdout_bytes)
        evidence = reader(decode_tool_output(result.stdout_bytes))
        return result, evidence, log_path

    def _persist(self, stage: str, map_name: str | None, raw: bytes) -> str:
        """Write the untouched bytes to a log file and hand back its path.

        Untouched matters: the log is the only artefact that can be re-read
        when a parser turns out to be wrong about a line.
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{map_name}.{stage}" if map_name else stage
        path = self.log_dir / f"{stem}.log"
        suffix = 0
        while path.exists():
            suffix += 1
            path = self.log_dir / f"{stem}-{suffix}.log"
        path.write_bytes(raw)
        return str(path)

    def _outcome(
        self,
        stage: str,
        ok: bool,
        result: RunResult,
        evidence: StageEvidence,
        log_path: str,
        command: Sequence[str],
        *,
        extra: Sequence[str] = (),
        artifacts: Sequence[PurePath] = (),
        findings: Sequence[Finding] = (),
    ) -> StageOutcome:
        return StageOutcome(
            stage=stage,
            ok=ok,
            evidence=_describe(evidence, extra),
            exit_code=result.exit_code,
            duration_s=result.duration_s,
            log_path=log_path,
            artifacts=[str(path) for path in artifacts],
            findings=_log_findings(evidence) + list(findings),
            command=list(command),
            details=evidence,
        )

    def _split_written(
        self, expected: Sequence[PurePath]
    ) -> tuple[list[PurePath], list[PurePath]]:
        """Partition expected outputs into written (non-empty) and not."""
        written: list[PurePath] = []
        missing: list[PurePath] = []
        for path in expected:
            size = self.runner.size_of(path)
            (written if size else missing).append(path)
        return written, missing

    def _require_directories(self, *paths: PurePath) -> None:
        """A missing tools directory is a configuration error (Section 7.1).

        Whether the tools create these themselves is unverified, so silently
        creating them here would hide a wrong root behind a build that then
        fails much later for an unrelated-looking reason.
        """
        absent = [str(path) for path in paths if not self.runner.is_directory(path)]
        if absent:
            raise ToolchainError(
                "missing tools directory (wrong root, or the map was never "
                f"committed): {', '.join(absent)}"
            )
