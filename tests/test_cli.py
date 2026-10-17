"""The command line: one-line user errors, honest options, quiet defaults."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from zmforge.facade import cli
from zmforge.verify.report import Report, error, note, warning


def _gen(tmp_path: Path, *extra: str, name: str = "zm_clitest") -> int:
    return cli.main(["generate", name, "--tools-root", str(tmp_path),
                     "--recipe", "one-room", *extra])


def test_rerun_without_overwrite_is_one_line_naming_the_flag(tmp_path, capsys):
    assert _gen(tmp_path) == 0
    capsys.readouterr()
    assert _gen(tmp_path) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "pass --overwrite" in err
    assert "overwrite=True" not in err and "Project.open" not in err
    # Refused before the recipe ran, not after.
    assert "building the" not in err


def test_missing_map_is_one_line(tmp_path, capsys):
    assert cli.main(["check", "zm_nope", "--tools-root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("zmforge: error:") and err.count("\n") == 1


def test_option_a_recipe_does_not_take_is_refused_by_name(tmp_path, capsys):
    assert _gen(tmp_path, "--starting-points", "5000") == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "TypeError" not in err
    assert "--starting-points is not offered by the one-room recipe" in err


def test_build_offers_no_duplicate_target_and_documents_language():
    sub = cli._build_parser()._subparsers._group_actions[0].choices
    build = {o: a for a in sub["build"]._actions for o in a.option_strings}
    assert "--target" not in build  # "auto" and "local" were the same place
    assert build["--language"].help
    review = {o: a for a in sub["review"]._actions for o in a.option_strings}
    assert "--visual" not in review and review["--principles"].help
    generate = {o: a for a in sub["generate"]._actions for o in a.option_strings}
    assert "browser" not in generate["--discard-edits"].help


def test_props_only_bad_name_is_one_line(tmp_path, capsys):
    assert cli.main(["props", "zm_x", "--out", str(tmp_path), "--only", "no_such_prop"]) == 1
    err = capsys.readouterr().err
    assert "no prop named 'no_such_prop'" in err and "Traceback" not in err


def test_check_no_loading_screen_and_props_gdt(tmp_path, capsys, monkeypatch):
    assert _gen(tmp_path, "--no-loading-screen") == 0
    capsys.readouterr()
    assert cli.main(["check", "zm_clitest", "--tools-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "P1" in out
    seen = {}
    import zmforge.verify as verify

    real = verify.check_written_files

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)

    monkeypatch.setattr(verify, "check_written_files", spy)
    assert cli.main(["check", "zm_clitest", "--tools-root", str(tmp_path),
                     "--no-loading-screen"]) == 0
    assert "props_gdt_path" in seen and seen["props_gdt_path"]  # Z27 runs here too


def test_requirements_refuses_a_different_recipe_or_seed(tmp_path, capsys):
    assert _gen(tmp_path) == 0
    model = next(tmp_path.rglob("zm_clitest.blueprint.json"))
    origin = json.loads(model.read_text())["origin"]
    assert origin["recipe"] == "one-room" and origin["player_slots"] == 4
    capsys.readouterr()
    base = ["requirements", "zm_clitest", "--tools-root", str(tmp_path)]
    assert cli.main([*base, "--recipe", "three-room"]) == 1
    assert "--recipe three-room but it was generated with one-room" in capsys.readouterr().err
    assert cli.main([*base, "--recipe", "one-room", "--seed", "other"]) == 1
    assert "--seed other" in capsys.readouterr().err
    assert cli.main([*base, "--recipe", "one-room", "--player-slots", "8"]) == 1
    assert "--player-slots 8" in capsys.readouterr().err


def test_warnings_are_summarised_unless_verbose(capsys):
    report = Report()
    report.extend([error("E1", "broken"), warning("S2", "a"), warning("S2", "b"),
                   warning("D1", "c"), note("W1", "expected")])
    cli.print_findings(report, verbose=False)
    err = capsys.readouterr().err
    assert "ERROR E1" in err and "WARNING" not in err and "INFO" not in err
    assert "3 warning(s): S2 x2, D1 x1" in err and "1 note(s)" in err
    cli.print_findings(report, verbose=True)
    err = capsys.readouterr().err
    assert err.count("WARNING") == 3 and "INFO W1" in err
    cli.print_findings(report, verbose=False, starter=True)
    err = capsys.readouterr().err
    assert "warning(s)" not in err and "4 note(s)" in err


def test_starter_generate_prints_no_warnings(tmp_path, capsys):
    assert cli.main(["generate", "zm_t3", "--tools-root", str(tmp_path),
                     "--recipe", "three-room"]) == 0
    err = capsys.readouterr().err
    assert "WARNING" not in err and "warning(s)" not in err


def test_progress_lines_go_to_stderr_only_for_long_runs():
    import io

    from zmforge import progress

    quick = io.StringIO()
    progress.enable(quick)  # default: quiet for the first QUIET_FOR seconds
    progress.stage("building")
    assert quick.getvalue() == ""
    slow = io.StringIO()
    progress.enable(slow, quiet_for=0.0)
    try:
        progress.stage("dressing rooms 3/9")
        progress.count("placing clumps", 1, 10)
        progress.count("placing clumps", 2, 10)  # rate-limited
        progress.count("placing clumps", 10, 10)  # the last step always prints
    finally:
        progress.disable()
    lines = slow.getvalue().splitlines()
    assert lines[0].endswith("dressing rooms 3/9...")
    assert [line.split("] ")[1] for line in lines[1:]] == [
        "placing clumps 1/10...", "placing clumps 10/10..."]
    progress.stage("after disable")  # silent, no error


def test_wall_buy_depth_is_a_note_not_a_warning():
    from zmforge.recipes import three_room_map
    from zmforge.verify import blueprint as check

    w1 = [f for f in check(three_room_map("zm_t3")) if f.code == "W1"]
    assert w1 and all(f.severity == "info" for f in w1)


def test_output_to_a_cp1252_console_does_not_crash(tmp_path):
    """Windows redirects stdout as cp1252, which has no ``└─`` (verify/coverage.py).

    A crash here would be a UnicodeEncodeError after the work was done.
    """
    import os
    import subprocess

    assert _gen(tmp_path, name="zm_cp1252") == 0
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; from zmforge.facade.cli import main; sys.exit(main(sys.argv[1:]))",
         "requirements", "zm_cp1252", "--tools-root", str(tmp_path)],
        capture_output=True, env=env, timeout=240,
    )
    assert b"Traceback" not in done.stderr, done.stderr[-2000:]
    assert done.returncode in (0, 1)
    assert b"?? not run" in done.stdout
    assert "└".encode("utf-8") not in done.stdout


# -- map names (a trailing newline, ../.., Windows MAX_PATH) -------------------

@pytest.mark.parametrize("bad", ["zm_x\n", "../..", "zm_a/../b", "zm_UPPER", "x_map"])
def test_a_bad_map_name_is_one_line_from_every_entry(tmp_path, capsys, bad):
    from zmforge.errors import ForgeError
    from zmforge.project import Project
    from zmforge.toolchain.buildlock import map_lock

    with pytest.raises(ForgeError):
        Project.create(bad, tmp_path)
    with pytest.raises(ForgeError):
        Project.open(bad, tmp_path)
    assert cli.main(["paths", bad, "--tools-root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("zmforge: error: map name") and err.count("\n") == 1
    if "/" in bad:
        with pytest.raises(ValueError):
            map_lock(bad)


def test_a_map_name_whose_deepest_path_passes_windows_max_path_is_refused():
    from zmforge.errors import ForgeError
    from zmforge.toolchain.layout import (
        WINDOWS_MAX_PATH_CHARS, ToolsLayout, deepest_map_path, validate_map_name)

    default = ToolsLayout.windows(
        r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130")
    longest = max(n for n in range(4, 200) if len(str(deepest_map_path(
        default, "zm_" + "a" * (n - 3)))) <= WINDOWS_MAX_PATH_CHARS)
    validate_map_name("zm_" + "a" * (longest - 3))           # fits exactly: accepted
    with pytest.raises(ForgeError, match=f"at most {longest} characters"):
        validate_map_name("zm_" + "a" * (longest - 2))
    # A deeper Steam library leaves less room, and the root actually used counts.
    deep = ToolsLayout.windows("D:\\" + "\\".join(["SteamLibrary"] * 8))
    with pytest.raises(ForgeError, match="too long"):
        validate_map_name("zm_" + "a" * (longest - 3), deep)


def test_render_with_no_tools_is_one_line(tmp_path, monkeypatch, capsys):
    from zmforge.render import radiant

    with pytest.raises(radiant.RenderError, match="no mod tools at"):
        radiant.require_render_tools(tmp_path / "missing")
    monkeypatch.setenv("ZMFORGE_WINE_TOOLS", str(tmp_path / "missing"))
    assert cli.main(["render", "one-room", "--out", str(tmp_path / "out")]) == 1
    err = [line for line in capsys.readouterr().err.splitlines() if line.startswith("zmforge")]
    assert err == [f"zmforge: error: no mod tools at {tmp_path / 'missing'}: render needs "
                   "the Wine tools copy (run docker/bo3-wine/setup.sh, or set ZMFORGE_WINE_TOOLS)"]
