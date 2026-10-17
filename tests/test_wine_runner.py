"""The Wine build target: the mod tools under Wine, in a container.

Nothing here needs docker, Wine or the tools. The container is addressed by
an argument list, so the argument list is what is asserted on, and a stub
standing in for ``docker`` proves the whole stage path - argv, working
directory, ``TA_*`` overlay, log capture and the on-disk verdict - against
a throwaway tools copy under ``tmp_path``.

The measurements these tests protect (Wine 11.0) are in
``docker/bo3-wine/SETUP.md``: the compile runs; the
link runs only with Microsoft's own ``msvcr110``/``msvcp110`` in the prefix;
and the bake runs only with a display, the GPU and an embree whose
``SetThreadIdealProcessorEx`` import is renamed, because Wine stubs that call
to FALSE and embree 2.3.3 gives up creating threads on it.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from zmforge.errors import NoInteractiveDesktop, ToolchainError
from zmforge.toolchain.layout import ToolsLayout
from zmforge.toolchain.stages import Toolchain
from zmforge.toolchain.targets import Target, select_target
from zmforge.toolchain.wine import (
    BAKE_DLL_OVERRIDES,
    BAKE_EXPORTED_MARKER,
    DEFAULT_WINDOWS_ROOT,
    EMBREE_IMPORT_NEW,
    EMBREE_IMPORT_OLD,
    RADIANT_LOG_MARKER,
    WineRunner,
)

MAP = "zm_forge_probe"
ROOT = r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"


def _tools_copy(tmp_path: Path) -> Path:
    """A tools folder with the files the availability check looks for."""
    tools = tmp_path / "tools"
    (tools / "bin").mkdir(parents=True)
    (tools / "bin" / "cod2map64.exe").write_bytes(b"MZ stub")
    (tools / "bin" / "linker_modtools.exe").write_bytes(b"MZ stub")
    (tools / "share" / "raw" / "maps" / "zm").mkdir(parents=True)
    (tools / "map_source" / "zm").mkdir(parents=True)
    (tools / "map_source" / "zm" / f"{MAP}.map").write_text("// stub map source\n")
    (tools / "usermaps" / MAP / "zone").mkdir(parents=True)
    return tools


def _embree(tools: Path, imports: bytes = EMBREE_IMPORT_OLD) -> Path:
    """A stand-in embree DLL: some bytes around one import name."""
    dll = tools / "bin" / "avx" / "embree64r.dll"
    dll.parent.mkdir(parents=True, exist_ok=True)
    dll.write_bytes(b"MZ embree 2.3.3 " + imports + b" tail")
    (tools / "bin" / "GdtDBTrayLauncher.exe").write_bytes(b"MZ tray")
    return dll


def _executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# -- addressing ------------------------------------------------------------


def test_command_line_mounts_the_tools_and_keeps_windows_arguments(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix", image="bo3-wine:test")
    layout = ToolsLayout.windows(ROOT)

    argv = runner.command_line([str(layout.compiler), "-platform", "pc"], layout)

    assert argv[:3] == ["docker", "run", "--rm"]
    assert f"{tools}:/tools" in argv
    assert f"{tmp_path / 'prefix'}:/wineprefix" in argv
    # The working directory is the tools' *Windows* bin as the prefix sees
    # it, not /tools/bin: Section 7.2's relative search paths resolve off the
    # C: drive, and /tools is Z:\tools to Wine.
    assert argv[argv.index("-w") + 1] == (
        "/wineprefix/drive_c/Program Files (x86)/Steam/steamapps/common/"
        "Call of Duty Black Ops III 455130/bin"
    )
    assert f"TA_GAME_PATH={ROOT}\\" in argv
    assert f"TA_TOOLS_PATH={ROOT}\\" in argv
    assert f"TA_LOCAL_ASSET_CACHE={ROOT}\\share\\assetconvert\\" in argv
    # The image comes last before the command, and the command keeps its
    # Windows spelling: the prefix answers to the same absolute path.
    assert argv[-5:] == [
        "bo3-wine:test",
        "wine",
        f"{ROOT}\\bin\\cod2map64.exe",
        "-platform",
        "pc",
    ]


def test_windows_paths_under_the_root_map_onto_the_local_copy(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix")
    layout = ToolsLayout.windows(ROOT)

    assert runner.local_path(ROOT) == tools
    assert runner.local_path(layout.compiler) == tools / "bin" / "cod2map64.exe"
    # Windows paths are case-insensitive and the root's case is not something
    # a caller should have to reproduce exactly.
    assert runner.local_path(ROOT.upper() + r"\bin") == tools / "bin"
    # Outside the root there is no answer, and saying so beats inventing one.
    assert runner.local_path(r"C:\Windows\System32\cmd.exe") is None
    assert runner.size_of(r"C:\Windows\System32\cmd.exe") is None
    assert runner.is_directory(r"C:\Windows") is False

    assert runner.size_of(layout.compiler) == len(b"MZ stub")
    assert runner.size_of(rf"{ROOT}\bin\not_here.exe") is None
    assert runner.is_directory(layout.bin_dir) is True
    assert runner.is_directory(layout.compiler) is False


def test_only_the_bake_gets_the_display_the_gpu_and_the_shims(tmp_path: Path) -> None:
    """What the bake needs, and the compile must not be disturbed by.

    Measured: Radiant will not start without an X connection,
    renders through D3D11 (llvmpipe under Xvfb failed to link 246 GLSL
    programs), and spins forever unless embree's thread pinning is shimmed.
    The compile and link were measured without any of this and keep the
    argument list they were measured with.
    """
    tools = _tools_copy(tmp_path)
    _embree(tools)
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix", image="bo3-wine:test")
    layout = ToolsLayout.windows(ROOT)
    assert runner.provides_interactive_desktop is True

    bake = runner.command_line(
        [str(layout.light_baker), "-ledSilent"], layout, stage="bake", container_name="bake-1"
    )
    assert bake[bake.index("--gpus") + 1] == "all"
    assert bake[bake.index("--name") + 1] == "bake-1"
    env = [bake[i + 1] for i, part in enumerate(bake) if part == "-e"]
    # DXVK for D3D11, and only here: the compile and link keep the image's
    # default overrides, under which d3d11 is Wine's builtin.
    assert f"WINEDLLOVERRIDES={BAKE_DLL_OVERRIDES}" in env
    assert "d3d11,dxgi,d3d10core=n" in BAKE_DLL_OVERRIDES
    assert "DXVK_LOG_PATH=/wineprefix/dxvk-logs" in env
    assert (tmp_path / "prefix" / "dxvk-logs").is_dir()
    # The wrapper starts the X server, then wine, then Radiant.
    assert bake[-4:] == ["with-display", "wine", str(layout.light_baker), "-ledSilent"]
    mounts = [bake[i + 1] for i, part in enumerate(bake) if part == "-v"]
    shim = tmp_path / "prefix" / "shims" / "bin" / "avx" / "embree64r.dll"
    assert f"{shim}:/tools/bin/avx/embree64r.dll:ro" in mounts
    blank = tmp_path / "prefix" / "shims" / "bin" / "GdtDBTrayLauncher.exe"
    assert f"{blank}:/tools/bin/GdtDBTrayLauncher.exe:ro" in mounts
    assert blank.read_bytes() == b""

    compile_ = runner.command_line([str(layout.compiler), "-platform", "pc"], layout, stage="compile_full")
    assert "--gpus" not in compile_ and "with-display" not in compile_
    assert not any(part.startswith("WINEDLLOVERRIDES=") for part in compile_)
    assert not any(":ro" in part for part in compile_)
    # Without a GPU the display wrapper still runs (Xvfb inside), but nothing
    # asks docker for a device it may not have.
    cpu_only = WineRunner(tools, prefix_dir=tmp_path / "prefix", gpu=False)
    assert "--gpus" not in cpu_only.command_line([str(layout.light_baker)], layout, stage="bake")


def test_the_embree_shim_renames_one_import_and_changes_nothing_else(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    original = _embree(tools).read_bytes()
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix")

    mounts = dict((str(host), target) for host, target in runner.ensure_shims())
    shim = tmp_path / "prefix" / "shims" / "bin" / "avx" / "embree64r.dll"
    assert mounts[str(shim)] == "/tools/bin/avx/embree64r.dll"
    patched = shim.read_bytes()
    assert len(patched) == len(original)
    assert EMBREE_IMPORT_OLD not in patched
    assert EMBREE_IMPORT_NEW in patched
    assert patched.replace(EMBREE_IMPORT_NEW, EMBREE_IMPORT_OLD) == original
    # The user's own file is untouched: the shim is mounted over it.
    assert (tools / "bin" / "avx" / "embree64r.dll").read_bytes() == original
    # Idempotent, and the shim lives under the (gitignored) prefix.
    assert runner.ensure_shims() == [(shim, "/tools/bin/avx/embree64r.dll"),
                                    (tmp_path / "prefix" / "shims" / "bin" / "GdtDBTrayLauncher.exe",
                                     "/tools/bin/GdtDBTrayLauncher.exe")]

    # A DLL without that import (another embree, or already patched) is left
    # alone and not mounted: there is nothing to fix.
    _embree(tools, imports=b"GetCurrentProcessId\0")
    shim.unlink()
    assert all(target != "/tools/bin/avx/embree64r.dll" for _, target in runner.ensure_shims())
    assert not shim.exists()


# -- a whole stage, with a stub where docker is ----------------------------


DOCKER_STUB = """
import os
import sys

argv = sys.argv[1:]
# Prove the two things a wrong argv would break silently: the tools mount
# and the TA_* overlay.
mounts = [argv[i + 1] for i, part in enumerate(argv) if part == "-v"]
tools = [m.split(":")[0] for m in mounts if m.endswith(":/tools")][0]
env = dict(
    part.split("=", 1) for i, part in enumerate(argv) if part == "-e" for part in [argv[i + 1]]
)
print("TOOLS=" + tools)
print("TA_TOOLS_PATH=" + env.get("TA_TOOLS_PATH", "<unset>"))
print("WORKDIR=" + argv[argv.index("-w") + 1])

# Behave like cod2map64 far enough for the verdict: write the BSP the last
# argument names, translated back onto the mounted copy.
root = env["TA_TOOLS_PATH"].rstrip("\\\\")
target = argv[-1]
relative = target[len(root) + 1 :].replace("\\\\", os.sep)
output = os.path.join(tools, relative)
os.makedirs(os.path.dirname(output), exist_ok=True)
with open(output, "wb") as handle:
    handle.write(b"BSP bytes from the stub")
print("Writing " + target)
"""


def test_a_compile_runs_through_the_container_and_is_judged_on_local_disk(
    tmp_path: Path,
) -> None:
    tools = _tools_copy(tmp_path)
    docker = tmp_path / "docker-stub"
    _executable(docker, DOCKER_STUB)
    runner = WineRunner(
        tools, prefix_dir=tmp_path / "prefix", docker=str(docker), image="bo3-wine:test"
    )
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.compile_bsp(MAP, mode="full")

    assert outcome.ok, outcome.evidence
    printed = dict(
        line.split("=", 1)
        for line in Path(outcome.log_path).read_text().splitlines()
        if "=" in line
    )
    assert printed["TOOLS"] == str(tools)
    assert printed["TA_TOOLS_PATH"] == ROOT + "\\"
    assert printed["WORKDIR"].endswith("Call of Duty Black Ops III 455130/bin")
    # The verdict read the file the container wrote, through the mount.
    bsp = tools / "share" / "raw" / "maps" / "zm" / f"{MAP}.d3dbsp"
    assert bsp.read_bytes() == b"BSP bytes from the stub"
    assert str(ToolsLayout.windows(ROOT).compiled_bsp(MAP)) in outcome.artifacts


RADIANT_LOG_OK = """Radiant Log
08:13:48: ERROR: Can't find xmodel 'p7_zm_vending_jugg' in gdtDB
08:13:48: ERROR: Can't find xmodel 'c_zom_test_body1' in gdtDB
08:13:49: Time to sort probes for render: 0.000016 s08:13:49:           Sun....
08:13:50: Sun bake Done (0.92 s)08:13:50: Ray tracing scene build (0.23 s)
08:14:52:           Probes....
08:14:52: Bounce 1 Complete (62.21 s)08:14:53: Bounce 2 Complete (0.20 s)
08:14:55: Exported c:\\program files (x86)\\steam\\steamapps\\common\\call of duty black ops iii 455130\\\\share\\raw\\maps\\zm\\{map}.led
08:14:55: Export Done (66.73 s)
08:14:55: Closing current map
"""

BAKE_STUB = """
import os
import sys
import time

argv = sys.argv[1:]
if argv[0] == "kill":
    open(os.environ["STUB_KILLED"], "w").write(argv[1])
    sys.exit(0)
mounts = [argv[i + 1] for i, part in enumerate(argv) if part == "-v"]
tools = [m.split(":")[0] for m in mounts if m.endswith(":/tools")][0]
prefix = [m.split(":")[0] for m in mounts if m.endswith(":/wineprefix")][0]
mode = os.environ.get("STUB_MODE", "ok")
map_name = argv[-1].rsplit("\\\\", 1)[-1][:-4]
docs = [m.split(":")[0] for m in mounts if m.endswith("/drive_c/users/root/Documents")]
log = os.path.join(docs[0] if docs else os.path.join(prefix, "drive_c", "users", "root", "Documents"), "Radiant.log")
os.makedirs(os.path.dirname(log), exist_ok=True)
led = os.path.join(tools, "share", "raw", "maps", "zm", map_name + ".led")
if mode == "ok" or mode == "linger":
    with open(log, "w") as handle:
        handle.write({radiant!r}.format(map=map_name))
    with open(led, "wb") as handle:
        handle.write(b"lit")
    print("LED Exported for " + argv[-1], flush=True)
    if mode == "linger":
        time.sleep(60)
elif mode == "unfinished":
    with open(log, "w") as handle:
        handle.write("Radiant Log\\n08:13:50: Sun bake Done (0.92 s)08:14:52:           Probes....\\n")
elif mode == "hang":
    time.sleep(60)
elif mode == "refused":
    print("Error: Failed to export " + argv[-1] + " because Unable to process the zone file.")
"""


def _bake_runner(tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch, **kw) -> tuple[Path, WineRunner]:
    tools = _tools_copy(tmp_path)
    _embree(tools)
    docker = tmp_path / "docker-stub"
    _executable(docker, BAKE_STUB.format(radiant=RADIANT_LOG_OK))
    monkeypatch.setenv("STUB_MODE", mode)
    monkeypatch.setenv("STUB_KILLED", str(tmp_path / "killed"))
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix", docker=str(docker), poll_interval_s=0.05, **kw)
    return tools, runner


def test_a_bake_runs_through_the_container_and_is_judged_on_the_led_and_radiant_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools, runner = _bake_runner(tmp_path, "ok", monkeypatch)
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP, quality="medium")

    assert outcome.ok, outcome.evidence
    assert str(ToolsLayout.windows(ROOT).led(MAP)) in outcome.artifacts
    assert (tools / "share" / "raw" / "maps" / "zm" / f"{MAP}.led").read_bytes() == b"lit"
    log = Path(outcome.log_path).read_text()
    # The stage log carries both the console line and Radiant's own log.
    assert BAKE_EXPORTED_MARKER.decode() in log
    assert RADIANT_LOG_MARKER in log and "Export Done (66.73 s)" in log
    # Radiant.log's asset ERROR lines are noted, not failed: a successful
    # bake on Windows prints the same kind [measured].
    assert outcome.details is not None and outcome.details.clean
    assert len(outcome.details.ignored_asset_warnings) == 2
    assert any("asset ERROR lines in Radiant.log ignored" in line for line in outcome.evidence)
    assert not [f for f in outcome.findings if f.code == "stage_error"]
    assert "Export Done (66.73 s)" in outcome.details.completion_lines
    # A stale Radiant.log in the shared prefix is never read: each bake gets
    # its own fresh Documents directory, so two bakes side by side cannot
    # read each other's log either.
    runner.radiant_log.parent.mkdir(parents=True, exist_ok=True)
    runner.radiant_log.write_text("stale")
    outcome = chain.bake_lights(MAP)
    assert outcome.ok and "stale" not in Path(outcome.log_path).read_text()


def test_a_bake_whose_log_has_no_export_done_is_not_ok_even_with_a_led_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The .led alone proves nothing: +forceclean or not, one from an earlier
    bake can be sitting there. Radiant's log has to say the export finished."""
    tools, runner = _bake_runner(tmp_path, "unfinished", monkeypatch)
    (tools / "share" / "raw" / "maps" / "zm" / f"{MAP}.led").write_bytes(b"from last week")
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP)

    assert not outcome.ok
    assert any("no 'Export Done' line" in line for line in outcome.evidence)


def test_a_bake_radiant_refuses_is_not_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured: a map with no zone file gets
    ``Error: Failed to export ... Unable to process the zone file`` on stdout."""
    _, runner = _bake_runner(tmp_path, "refused", monkeypatch)
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP)

    assert not outcome.ok
    assert any("Failed to export" in line for line in outcome.evidence)


def test_a_bake_over_its_time_limit_is_killed_by_container_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``docker run`` proxies SIGTERM to a Wine loader that ignores it
    [measured: a ``timeout 300`` left the container running], so
    the container is named and killed by name."""
    _, runner = _bake_runner(tmp_path, "hang", monkeypatch, bake_timeout_s=0.5)
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP)

    assert not outcome.ok
    assert outcome.duration_s < 10
    assert any("did not finish" in line for line in outcome.evidence)
    assert any(f.code == "bake_unfinished" for f in outcome.findings)
    assert (tmp_path / "killed").read_text().startswith("zmforge-bake-")


def test_a_bake_that_lingers_after_exporting_is_stopped_and_still_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured: after ``Export Done`` Radiant stayed alive at
    250% CPU and never exited; the .led was complete."""
    _, runner = _bake_runner(tmp_path, "linger", monkeypatch, bake_linger_s=0.3, bake_timeout_s=30)
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.bake_lights(MAP)

    assert outcome.ok, outcome.evidence
    assert outcome.duration_s < 10
    assert (tmp_path / "killed").exists()
    assert not any(f.code == "bake_unfinished" for f in outcome.findings)


def test_a_missing_prefix_directory_is_created_rather_than_left_to_the_daemon(
    tmp_path: Path,
) -> None:
    tools = _tools_copy(tmp_path)
    docker = tmp_path / "docker-stub"
    _executable(docker, DOCKER_STUB)
    prefix = tmp_path / "nested" / "prefix"
    runner = WineRunner(tools, prefix_dir=prefix, docker=str(docker))

    runner.run(
        [str(ToolsLayout.windows(ROOT).compiler), str(ToolsLayout.windows(ROOT).compiled_bsp(MAP))],
        layout=ToolsLayout.windows(ROOT),
        stage="compile_full",
    )

    assert prefix.is_dir()


# -- availability and target choice ----------------------------------------


def test_unavailable_because_names_the_one_thing_that_is_missing(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    yes = tmp_path / "docker-yes"
    _executable(yes, "import sys\nsys.exit(0)\n")
    no = tmp_path / "docker-no"
    _executable(no, "import sys\nsys.exit(1)\n")

    assert WineRunner(tools, docker=str(yes)).unavailable_because() is None
    assert "is not built" in (WineRunner(tools, docker=str(no)).unavailable_because() or "")
    missing = WineRunner(tmp_path / "nowhere", docker=str(yes)).unavailable_because()
    assert "no local mod-tools copy" in (missing or "")
    # Each missing piece is named on its own, so the message says which file
    # to go and fetch rather than "incomplete".
    (tools / "bin" / "cod2map64.exe").unlink()
    incomplete = WineRunner(tools, docker=str(yes)).unavailable_because() or ""
    assert "incomplete tools copy" in incomplete
    assert "cod2map64.exe" in incomplete
    (tools / "bin" / "cod2map64.exe").write_bytes(b"MZ stub")
    (tools / "bin" / "linker_modtools.exe").unlink()
    assert "linker_modtools.exe" in (WineRunner(tools, docker=str(yes)).unavailable_because() or "")
    (tools / "bin" / "linker_modtools.exe").write_bytes(b"MZ stub")
    (tools / "share" / "raw" / "maps" / "zm").rmdir()
    (tools / "share" / "raw" / "maps").rmdir()
    (tools / "share" / "raw").rmdir()
    assert "share/raw" in (WineRunner(tools, docker=str(yes)).unavailable_because() or "")
    (tools / "share" / "raw").mkdir(parents=True)
    assert "not on PATH" in (
        WineRunner(tools, docker="zmforge-no-such-docker").unavailable_because() or ""
    )


def test_auto_prefers_the_local_target(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    yes = tmp_path / "docker-yes"
    _executable(yes, "import sys\nsys.exit(0)\n")

    target = select_target("auto", tools_dir=tools, docker=str(yes))

    assert isinstance(target, Target)
    assert target.name == "local"
    assert target.is_local
    assert target.fell_back_because is None
    assert isinstance(target.runner, WineRunner)
    # The layout is the Windows root even locally: the prefix answers to it.
    assert str(target.layout.root) == ROOT


def test_local_target_refuses_a_missing_tools_copy(tmp_path: Path) -> None:
    with pytest.raises(ToolchainError) as problem:
        select_target("local", tools_dir=tmp_path / "nowhere")
    assert "cannot build locally" in str(problem.value)


def test_an_unknown_target_name_is_refused() -> None:
    for name in ("somewhere-else", "windows"):
        with pytest.raises(ToolchainError):
            select_target(name)


def test_auto_without_a_local_copy_says_why(tmp_path: Path) -> None:
    with pytest.raises(ToolchainError) as problem:
        select_target("auto", tools_dir=tmp_path / "nowhere")
    assert "cannot build locally" in str(problem.value)


def test_the_tools_directory_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = _tools_copy(tmp_path)
    monkeypatch.setenv("ZMFORGE_WINE_TOOLS", str(tools))
    yes = tmp_path / "docker-yes"
    _executable(yes, "import sys\nsys.exit(0)\n")

    target = select_target("auto", docker=str(yes))

    assert target.name == "local"
    assert target.runner.tools_dir == tools.resolve()


def test_the_default_windows_root_is_the_measured_steam_path() -> None:
    assert DEFAULT_WINDOWS_ROOT == ROOT
    assert os.sep not in DEFAULT_WINDOWS_ROOT.replace("\\", "")


# -- the loader-failure trap -----------------------------------------------


WINE_ABORT = """wine: Unimplemented function msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ called at address 00006FFFFF3CD887.
wine: Call from 00006FFFFF3CD887 to unimplemented function msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ, aborting
"""

LINKER_ABORT_STUB = """
import sys

sys.stdout.write({abort!r})
sys.exit(1)
""".format(abort=WINE_ABORT)


def test_a_link_wine_killed_is_not_ok_even_with_fastfiles_on_disk(tmp_path: Path) -> None:
    """The trap this rule exists for [measured].

    Wine aborted `linker_modtools.exe` on an unimplemented `msvcr110` entry
    point before it printed a line of its own. No `ERROR:` line was in the
    log, the previous build's two fastfiles were still on disk, and the
    chain reported `link: ok`.
    """
    tools = _tools_copy(tmp_path)
    zone = tools / "usermaps" / MAP / "zone"
    (zone / f"{MAP}.ff").write_bytes(b"stale fastfile from an earlier build")
    (zone / f"en_{MAP}.ff").write_bytes(b"stale fastfile from an earlier build")
    docker = tmp_path / "docker-stub"
    _executable(docker, LINKER_ABORT_STUB)
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix", docker=str(docker))
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.link_fastfiles(MAP)

    assert not outcome.ok
    assert any("unimplemented function" in line for line in outcome.evidence)
    assert [f for f in outcome.findings if f.code == "stage_error"]


def test_a_benign_wine_notice_does_not_fail_a_stage(tmp_path: Path) -> None:
    tools = _tools_copy(tmp_path)
    docker = tmp_path / "docker-stub"
    _executable(
        docker,
        DOCKER_STUB + "\nprint('wine: created the configuration directory /wineprefix')\n",
    )
    runner = WineRunner(tools, prefix_dir=tmp_path / "prefix", docker=str(docker))
    chain = Toolchain(ToolsLayout.windows(ROOT), runner, log_dir=tmp_path / "logs")

    outcome = chain.compile_bsp(MAP, mode="full")

    assert outcome.ok, outcome.evidence


def test_the_prefix_directory_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prefix is not forced to sit beside the tools.

    WHY it matters: the default puts it next to the tools directory, which is
    right for a working copy and wrong when the tools *are* the Steam install
    - there the prefix would be created inside ``steamapps/common``.
    """
    tools = _tools_copy(tmp_path)
    elsewhere = tmp_path / "var" / "prefix"
    monkeypatch.setenv("ZMFORGE_WINE_TOOLS", str(tools))
    monkeypatch.setenv("ZMFORGE_WINE_PREFIX", str(elsewhere))
    yes = tmp_path / "docker-yes"
    _executable(yes, "import sys\nsys.exit(0)\n")

    target = select_target("auto", docker=str(yes))

    assert target.name == "local"
    assert target.runner.prefix_dir == elsewhere.resolve()  # type: ignore[union-attr]

    monkeypatch.delenv("ZMFORGE_WINE_PREFIX")
    default = select_target("auto", docker=str(yes))
    assert default.runner.prefix_dir == (tools.parent / "wineprefix").resolve()  # type: ignore[union-attr]
