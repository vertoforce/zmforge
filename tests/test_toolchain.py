"""Conformance checks B1-B9 of specification section 9.5.

Every check runs against a throwaway tools root under ``tmp_path`` holding
stub executables, so the argument order, the environment and the verdict
rules are all exercised for real without Windows or a 97-second
link. Where a check names an exit code the host cannot produce (a POSIX
process cannot exit 154000), the process is replaced by a scripted runner
so the code under test still sees the number the field reported.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Sequence

import pytest

from zmforge import mapdoc
from zmforge.errors import NoInteractiveDesktop, ToolchainError
from zmforge.toolchain.layout import ToolsLayout, stage_environment
from zmforge.toolchain.runner import LocalRunner, RunResult
from zmforge.toolchain.stages import Toolchain

MAP = "zm_forge_probe"


# -- fixtures and doubles --------------------------------------------------


def _install(tmp_path: Path) -> ToolsLayout:
    """A tools root with the directories a stage refuses to run without."""
    layout = ToolsLayout.posix(tmp_path / "Call of Duty Black Ops III 455130")
    for directory in (
        layout.bin_dir,
        layout.root / "gdtdb",
        layout.map_source_dir,
        layout.compiler_output_dir,
        layout.fastfile_dir(MAP),
        layout.zone_source_dir(MAP),
    ):
        Path(str(directory)).mkdir(parents=True, exist_ok=True)
    Path(str(layout.map_source(MAP))).write_text("// stub map source\n")
    return layout


def _stub(path: "os.PathLike[str] | str", body: str) -> None:
    """Drop an executable python script where a tool executable belongs."""
    target = Path(str(path))
    target.write_text("#!/usr/bin/env python3\n" + body)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


#: A clean link's log: both zones reach ``done:`` (shape of tests/logs/*.link.log).
_LINK_OK = (
    f'Linking "{MAP}" (usermaps\\{MAP} stable 3421953 v593): processing...done: 1m37s\n'
    f'Linking "en_{MAP}" (usermaps\\{MAP} stable 3421953 v593): unchanged...done: 0m02s\n'
).encode()


def _fastfiles(layout: ToolsLayout, *, localised: bool = True) -> None:
    Path(str(layout.fastfile(MAP))).write_bytes(b"fastfile bytes")
    if localised:
        Path(str(layout.localised_fastfile(MAP, "en"))).write_bytes(b"fastfile bytes")


class ScriptedRunner:
    """A runner that answers from a script and records what it was asked.

    It keeps the real filesystem for ``size_of``/``is_directory`` so the
    evidence rules that look at disk are still tested for real; only process
    start-up is faked.
    """

    def __init__(
        self,
        replies: Sequence[RunResult] = (),
        *,
        interactive_desktop: bool = False,
    ) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, list[str]]] = []
        self.provides_interactive_desktop = interactive_desktop

    def run(
        self,
        command: Sequence[str],
        *,
        layout: ToolsLayout,
        stage: str,
        stall_window_s: float | None = None,
        timeout_s: float | None = None,
    ) -> RunResult:
        self.calls.append((stage, list(command)))
        if self.replies:
            return self.replies.pop(0)
        return RunResult(0, b"", 0.0)

    def size_of(self, path: "os.PathLike[str] | str") -> int | None:
        try:
            return os.stat(str(path)).st_size
        except OSError:
            return None

    def is_directory(self, path: "os.PathLike[str] | str") -> bool:
        return os.path.isdir(str(path))

    def read_text(self, path: "os.PathLike[str] | str") -> str:
        try:
            return Path(str(path)).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def _link_reports(layout: ToolsLayout, *, pool: str, asset_list: str, deps: str) -> None:
    """The three small reports a real link leaves beside the fastfiles.

    Written here in the shape the reports use rather than copied from a link:
    the verdict reads three lines out of them.
    """
    for zone in ("all", "english"):
        Path(str(layout.link_report_dir(MAP, zone))).mkdir(parents=True, exist_ok=True)
        Path(str(layout.link_asset_list(MAP, zone))).parent.mkdir(
            parents=True, exist_ok=True
        )
        Path(str(layout.link_pool_report(MAP, zone))).write_text(pool)
        Path(str(layout.link_asset_list(MAP, zone))).write_text(asset_list)
        Path(str(layout.link_deps(MAP, zone))).write_text(deps)


# -- B1 --------------------------------------------------------------------


def test_b1_stage_runs_in_bin_dir_with_ta_variables(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _stub(
        layout.compiler,
        "import os\n"
        "print('CWD=' + os.path.realpath(os.getcwd()))\n"
        "for name in ('TA_GAME_PATH', 'TA_TOOLS_PATH', 'TA_LOCAL_ASSET_CACHE'):\n"
        "    print(name + '=' + os.environ.get(name, '<unset>'))\n",
    )
    chain = Toolchain(layout, LocalRunner(), log_dir=tmp_path / "logs")

    outcome = chain.compile_bsp(MAP, mode="full")

    printed = dict(
        line.split("=", 1)
        for line in Path(outcome.log_path).read_text().splitlines()
        if "=" in line
    )
    assert printed["CWD"] == os.path.realpath(str(layout.bin_dir))
    assert printed["TA_GAME_PATH"] == str(layout.root) + "/"
    assert printed["TA_TOOLS_PATH"] == str(layout.root) + "/"
    assert printed["TA_LOCAL_ASSET_CACHE"] == str(layout.asset_cache) + "/"

    # On the real (Windows) root the same three carry trailing backslashes.
    windows = stage_environment(ToolsLayout.windows(r"C:\Steam\bo3 455130"))
    assert windows["TA_GAME_PATH"] == "C:\\Steam\\bo3 455130\\"
    assert windows["TA_TOOLS_PATH"] == "C:\\Steam\\bo3 455130\\"
    assert windows["TA_LOCAL_ASSET_CACHE"] == "C:\\Steam\\bo3 455130\\share\\assetconvert\\"


# -- B2 --------------------------------------------------------------------


def test_b2_compile_argument_order_per_mode(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    runner = ScriptedRunner()
    chain = Toolchain(layout, runner, log_dir=tmp_path / "logs")

    full = chain.compile_bsp(MAP, mode="full")
    entities = chain.compile_bsp(MAP, mode="entities")

    assert full.command == [
        str(layout.compiler),
        "-platform",
        "pc",
        "-navmesh",
        "-navvolume",
        "-loadFrom",
        str(layout.map_source(MAP)),
        str(layout.compiled_bsp(MAP)),
    ]
    assert "-onlyents" not in full.command
    assert entities.command == [
        str(layout.compiler),
        "-platform",
        "pc",
        "-onlyents",
        "-loadFrom",
        str(layout.map_source(MAP)),
        str(layout.compiled_bsp(MAP)),
    ]
    assert "-navmesh" not in entities.command and "-navvolume" not in entities.command

    with pytest.raises(ToolchainError):
        chain.compile_bsp(MAP, mode="quick")


# -- B3 --------------------------------------------------------------------


def test_b3_bake_argument_order_and_quality_set(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    runner = ScriptedRunner(interactive_desktop=True)
    chain = Toolchain(layout, runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP, quality="final")

    assert outcome.command == [
        str(layout.light_baker),
        "-ledSilent",
        "+final",
        "+localprobes",
        "+forceclean",
        "+recompute",
        str(layout.map_source(MAP)),
    ]
    assert "-platform" not in outcome.command and "-loadFrom" not in outcome.command

    for quality in ("draft", "medium", "final"):
        chain.bake_lights(MAP, quality=quality)
    for rejected in ("ultra", "FINAL", "", "high"):
        with pytest.raises(ToolchainError):
            chain.bake_lights(MAP, quality=rejected)


# -- B4 --------------------------------------------------------------------


def test_b4_link_arguments_are_language_then_modsource(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    runner = ScriptedRunner()
    chain = Toolchain(layout, runner, log_dir=tmp_path / "logs")

    outcome = chain.link_fastfiles(MAP, language="english")

    assert outcome.command == [
        str(layout.linker),
        "-language",
        "english",
        "-modsource",
        MAP,
    ]
    with pytest.raises(ToolchainError):
        chain.link_fastfiles(MAP, language="klingon")


# -- B5 --------------------------------------------------------------------


def test_b5_link_verdict_ignores_exit_code(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    success_log = (
        b'Linking "' + MAP.encode() + b'" ...\n'
        b"^3DROPPED VERTS. 12 warnings encountered while processing xmodel 'p7_crate'\n"
        b"done: 1m37s\n"
        b'Linking "en_' + MAP.encode() + b'" ... done: 0m02s\n'
    )

    # 154000 with both fastfiles written: success.
    _fastfiles(layout)
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(154000, success_log, 97.0)]),
        log_dir=tmp_path / "logs",
    )
    good = chain.link_fastfiles(MAP)
    assert good.exit_code == 154000
    assert good.ok is True
    assert len(good.artifacts) == 2

    # Exit 0 but an ERROR: line: failure.
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(0, b"^1ERROR: Lua not supported\n", 3.0)]),
        log_dir=tmp_path / "logs",
    )
    broken = chain.link_fastfiles(MAP)
    assert broken.exit_code == 0
    assert broken.ok is False
    assert any("Lua not supported" in line for line in broken.evidence)

    # Exit 2000, the cached-success code, but one fastfile missing: failure.
    Path(str(layout.localised_fastfile(MAP, "en"))).unlink()
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(2000, success_log, 1.8)]),
        log_dir=tmp_path / "logs",
    )
    partial = chain.link_fastfiles(MAP)
    assert partial.exit_code == 2000
    assert partial.ok is False
    assert any(finding.code == "missing_fastfile" for finding in partial.findings)


# -- B6 --------------------------------------------------------------------


def test_b6_leak_banner_and_missing_material_reach_the_outcome(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    leakfile = str(layout.compiler_output_dir / f"{MAP}.lin")
    _stub(
        layout.compiler,
        "print('Processing map...')\n"
        "print(\"WARNING: Material 'me_metal_floor_rusted' is missing\")\n"
        "print('******* leaked *******')\n"
        f"print('WROTE BSP LEAKFILE: {leakfile}')\n",
    )
    chain = Toolchain(layout, LocalRunner(), log_dir=tmp_path / "logs")

    outcome = chain.compile_bsp(MAP, mode="full")

    assert outcome.exit_code == 0
    assert outcome.ok is False
    leaks = [finding for finding in outcome.findings if finding.code == "leak"]
    assert len(leaks) == 1
    assert leakfile in leaks[0].message
    assert outcome.details is not None and outcome.details.leakfile == leakfile
    assert "me_metal_floor_rusted" in " ".join(outcome.evidence)
    assert any(
        finding.code == "missing_material" and "me_metal_floor_rusted" in finding.message
        for finding in outcome.findings
    )


# -- B7 --------------------------------------------------------------------


def test_b7_undecodable_byte_does_not_discard_the_result(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _stub(
        layout.compiler,
        "import sys\n"
        "sys.stdout.buffer.write(b'Loading map\\n')\n"
        "sys.stdout.buffer.write(b'ERROR: bad byte \\xff in brush 41\\n')\n"
        "sys.stdout.buffer.write(b'Compile finished\\n')\n"
        "sys.stdout.buffer.flush()\n",
    )
    chain = Toolchain(layout, LocalRunner(), log_dir=tmp_path / "logs")

    outcome = chain.compile_bsp(MAP, mode="entities")

    assert outcome.ok is False
    joined = " ".join(outcome.evidence)
    assert "\ufffd" in joined
    assert "bad byte" in joined and "brush 41" in joined
    raw = Path(outcome.log_path).read_bytes()
    assert raw.startswith(b"Loading map\n") and raw.endswith(b"Compile finished\n")


# -- B8 --------------------------------------------------------------------


def test_b8_stalled_bake_is_killed_and_named(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _stub(layout.light_baker, "import time\ntime.sleep(120)\n")
    chain = Toolchain(
        layout,
        LocalRunner(interactive_desktop=True, poll_interval_s=0.05),
        log_dir=tmp_path / "logs",
        stall_window_s=0.4,
    )

    started = time.monotonic()
    outcome = chain.bake_lights(MAP, quality="medium")
    elapsed = time.monotonic() - started

    assert elapsed < 30.0
    assert outcome.ok is False
    assert "needs interactive desktop" in " ".join(outcome.evidence)
    assert any(finding.code == "needs_interactive_desktop" for finding in outcome.findings)

    # A runner that cannot promise a desktop never starts the program at all.
    refusing = ScriptedRunner(interactive_desktop=False)
    with pytest.raises(NoInteractiveDesktop):
        Toolchain(layout, refusing, log_dir=tmp_path / "logs").bake_lights(MAP)
    assert refusing.calls == []


# -- B9 --------------------------------------------------------------------


def test_b9_run_chain_stops_at_first_failing_stage(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _fastfiles(layout)
    leaked = RunResult(0, b"***** leaked *****\nWROTE BSP LEAKFILE: /tmp/x.lin\n", 4.0)
    linked = RunResult(154000, _LINK_OK, 2.0)
    runner = ScriptedRunner([leaked, linked])
    chain = Toolchain(layout, runner, log_dir=tmp_path / "logs")

    result = chain.run_chain(MAP, stages=("compile_full", "link"))

    assert result.ok is False
    assert result.failed_stage == "compile_full"
    assert [outcome.stage for outcome in result.outcomes] == ["compile_full"]
    assert [stage for stage, _ in runner.calls] == ["compile_full"]

    # ... and runs on when asked to.
    runner = ScriptedRunner([leaked, linked])
    keep_going = Toolchain(layout, runner, log_dir=tmp_path / "logs").run_chain(
        MAP, stages=("compile_full", "link"), stop_on_failure=False
    )
    assert keep_going.failed_stage == "compile_full"
    assert [stage for stage, _ in runner.calls] == ["compile_full", "link"]


_NAVVOLUME_SKIPPED = (
    b"navvolume = full generation\n"
    b"WARNING: NavVolume generation is skipped. Flying units might not behave "
    b"correctly. This might be due to there is no nav_volume brush in the level, "
    b"or the generation is skipped purposely by skipping -navvolume option.\n"
    b"Writing /x/zm_forge_probe_navmesh.hkt\n"
    b"Writing /x/zm_forge_probe_navvolume.hkt\n"
    b"    2 seconds elapsed\n"
)


def test_a_clean_compile_that_wrote_no_bsp_is_a_failure(tmp_path: Path) -> None:
    """The log cannot see a file the tool announced and did not write.

    Measured on the mod tools: a compile can exit 0 with no ``ERROR:`` line
    and no leak, print ``Writing <map>_navvolume.hkt``, and leave no
    navvolume on disk.  A log-only verdict called that a success.
    The BSP is the compile's product, so its absence is now a failure.
    """
    layout = _install(tmp_path)
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(0, b"    2 seconds elapsed\n", 2.0)]),
        log_dir=tmp_path / "logs",
    )
    outcome = chain.compile_bsp(MAP, mode="full")
    assert outcome.ok is False
    assert any("not written or empty" in line for line in outcome.evidence)
    assert [f.code for f in outcome.findings if f.severity == "error"] == ["missing_output"]


def test_a_skipped_navvolume_is_a_warning_and_still_builds(tmp_path: Path) -> None:
    """A map with no nav_volume brush is legitimate: no flying enemies.

    The same measured run wrote the BSP and the navmesh but no navvolume, and
    said so in its own words.  Requiring all three would fail every such map,
    so the two navigation files are reported and not gated on.
    """
    layout = _install(tmp_path)
    Path(str(layout.compiled_bsp(MAP))).write_bytes(b"bsp bytes")
    Path(str(layout.navmesh(MAP))).write_bytes(b"navmesh bytes")
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(0, _NAVVOLUME_SKIPPED, 2.0)]),
        log_dir=tmp_path / "logs",
    )
    outcome = chain.compile_bsp(MAP, mode="full")
    assert outcome.ok is True
    assert outcome.details is not None and outcome.details.navvolume_skipped
    assert any("flying units" in note for note in outcome.details.notes)
    assert [f.code for f in outcome.findings if f.severity == "error"] == []


def test_b5_a_link_killed_on_timeout_is_not_a_success(tmp_path: Path) -> None:
    """Stale fastfiles prove nothing about a run that never finished.

    A cached re-link leaves the fastfiles' mtimes alone, so their presence
    is the success evidence for a run that *did* finish.  A run the runner
    killed on timeout (or one that never started) leaves the
    previous build's files exactly where they were, and an empty log has no
    ``ERROR:`` line in it: without ``stalled`` in the verdict this read as a
    clean link.
    """
    layout = _install(tmp_path)
    _fastfiles(layout)  # left over from an earlier, real link
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(-1, b"", 3600.0, stalled=True)]),
        log_dir=tmp_path / "logs",
    )
    outcome = chain.link_fastfiles(MAP)
    assert outcome.ok is False
    assert any(finding.code == "link_unfinished" for finding in outcome.findings)
    assert any("did not finish" in line for line in outcome.evidence)


class _MtimeRunner(ScriptedRunner):
    def mtime_of(self, path: "os.PathLike[str] | str") -> float | None:
        try:
            return os.stat(str(path)).st_mtime
        except OSError:
            return None


@pytest.mark.parametrize(
    "reply",
    [
        RunResult(137, b"", 4.0),  # linker OOM-killed / SIGKILL, no output
        RunResult(
            125,
            b"docker: Error response from daemon: error while creating mount source "
            b"path: mkdir /x: permission denied.\nSee 'docker run --help'.\n",
            0.2,
        ),
        RunResult(154000, _LINK_OK.split(b"\n")[0] + b"\n", 9.0),  # one zone only
        RunResult(154000, f'Linking "{MAP}" (x): processing...\n'.encode(), 9.0),  # no done:
    ],
    ids=["killed-137", "docker-125", "one-zone", "no-done"],
)
def test_b5_a_link_that_did_not_run_to_done_fails_on_stale_fastfiles(
    tmp_path: Path, reply: RunResult
) -> None:
    layout = _install(tmp_path)
    _fastfiles(layout)  # left over from an earlier, real link
    chain = Toolchain(layout, _MtimeRunner([reply]), log_dir=tmp_path / "logs")
    outcome = chain.link_fastfiles(MAP)
    assert outcome.ok is False
    assert any(finding.code == "link_unfinished" for finding in outcome.findings)


def test_b5_a_rebuilt_zone_needs_a_fastfile_newer_than_the_link(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _fastfiles(layout)
    old = time.time() - 3600
    for ff in (layout.fastfile(MAP), layout.localised_fastfile(MAP, "en")):
        os.utime(str(ff), (old, old))
    # The main zone says "processing" but its file is an hour old: stale.
    stale = Toolchain(layout, _MtimeRunner([RunResult(154000, _LINK_OK, 9.0)]),
                      log_dir=tmp_path / "logs").link_fastfiles(MAP)
    assert stale.ok is False
    assert any("older than this link" in f.message for f in stale.findings)
    # Rewritten main zone, cached ("unchanged") localised zone left old: fine.
    os.utime(str(layout.fastfile(MAP)), None)
    fresh = Toolchain(layout, _MtimeRunner([RunResult(154000, _LINK_OK, 9.0)]),
                      log_dir=tmp_path / "logs").link_fastfiles(MAP)
    assert fresh.ok is True


def test_a_compile_refuses_geometry_the_document_does_not_describe(tmp_path: Path) -> None:
    """B-side of ``geometry.sha256``: a build must not compile a stale ``.map``.

    The shared document carries the script plan, the weapon prices and the prop
    list for one specific geometry and records its hash.  Compiling a ``.map``
    that is not that one produces a map that links, loads and is wrong, with
    nothing in any log saying so -- the exact staleness a sidecar format is
    accused of, and the reason the hash is written at all.  So the stage refuses
    before the compiler is started, naming both hashes.
    """
    layout = _install(tmp_path)
    map_path = Path(str(layout.map_source(MAP)))
    document = Path(str(layout.map_source_dir)) / f"{MAP}.blueprint.json"
    stale = "0" * 64
    document.write_text(
        json.dumps({"format": "zmforge-map/2", "name": MAP,
                    "geometry": {"map_file": f"{MAP}.map", "sha256": stale}}),
        encoding="utf-8",
    )
    runner = ScriptedRunner()
    chain = Toolchain(layout, runner, log_dir=tmp_path / "logs")

    with pytest.raises(ToolchainError) as caught:
        chain.compile_bsp(MAP, mode="full")
    on_disk = mapdoc.file_digest(map_path)
    assert stale in str(caught.value) and on_disk in str(caught.value)
    assert runner.calls == [], "the compiler was started anyway"

    # And the check is not a blanket refusal: the same map with the hash it
    # actually has compiles.
    document.write_text(
        json.dumps({"format": "zmforge-map/2", "name": MAP,
                    "geometry": {"map_file": f"{MAP}.map", "sha256": on_disk}}),
        encoding="utf-8",
    )
    chain.compile_bsp(MAP, mode="full")
    assert [stage for stage, _ in runner.calls] == ["compile_full"]


# -- B5, the silent sound bank ---------------------------------------------


_SILENT_DEPS = (
    f"sound,{MAP},english\n"
    f"assetlist,{MAP}\n"
    f"\tfile,C:\\tools\\share\\raw\\sound\\zone\\{MAP}.english.alias.sz,1234567800,\n"
    "errorcount,0\n"
)


def test_b5_a_link_that_packed_a_silent_sound_bank_is_not_a_success(
    tmp_path: Path,
) -> None:
    """The sound-bank crash, at the stage that should have caught it.

    A clean linker log and two written fastfiles, and the link's own reports
    saying it packed a sound bank whose dependencies name no audio. The game
    refuses that bank and dies at load, so the stage has to refuse it here.
    """
    layout = _install(tmp_path)
    _fastfiles(layout)
    _link_reports(
        layout,
        pool="type,limit,total\nsound,32,1\n",
        asset_list=f"material,mc/mtl_wall\nsound,{MAP}\n",
        deps=_SILENT_DEPS,
    )
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(154000, _LINK_OK, 97.0)]),
        log_dir=tmp_path / "logs",
    )

    outcome = chain.link_fastfiles(MAP)

    assert outcome.ok is False
    assert "Z24" in {finding.code for finding in outcome.findings}
    assert any("no audio file" in line for line in outcome.evidence)


def test_b5_a_link_whose_bank_carries_audio_still_passes(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _fastfiles(layout)
    _link_reports(
        layout,
        pool="type,limit,total\nsound,32,1\n",
        asset_list=f"material,mc/mtl_wall\nsound,{MAP}\n",
        deps=_SILENT_DEPS.replace(
            "errorcount,0\n",
            f"\tfile,C:\\tools\\sound_assets\\{MAP}\\ring_loop.wav,1234567890,\n"
            "errorcount,0\n",
        ),
    )
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(154000, _LINK_OK, 97.0)]),
        log_dir=tmp_path / "logs",
    )

    assert chain.link_fastfiles(MAP).ok is True


def test_b5_a_map_with_no_sound_bank_is_unaffected(tmp_path: Path) -> None:
    layout = _install(tmp_path)
    _fastfiles(layout)
    _link_reports(
        layout,
        pool="type,limit,total\nsound,32,0\n",
        asset_list="material,mc/mtl_wall\n",
        deps=_SILENT_DEPS,
    )
    chain = Toolchain(
        layout,
        ScriptedRunner([RunResult(154000, _LINK_OK, 97.0)]),
        log_dir=tmp_path / "logs",
    )

    assert chain.link_fastfiles(MAP).ok is True


def test_the_local_runner_reads_a_report_and_shrugs_at_a_missing_one(
    tmp_path: Path,
) -> None:
    """``read_text`` is how a runner reads a report the tools wrote; a missing one reads as empty."""
    report = tmp_path / "pool.csv"
    report.write_text("type,limit,total\nsound,32,1\n")
    runner = LocalRunner()
    assert "sound,32,1" in runner.read_text(report)
    assert runner.read_text(tmp_path / "absent.csv") == ""
