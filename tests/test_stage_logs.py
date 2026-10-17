"""The evidence parsers, against logs the real tools actually produced.

Every other test in this suite can be satisfied by code that agrees with
itself.  These cannot: the files in ``tests/logs`` were captured from
``cod2map64.exe`` and ``linker_modtools.exe``, two of them building the
three-room fixture and one a link with a missing weapon table, so they pin the parsers to the tools' real wording rather
than to the spec's paraphrase of it.

Two things here were measured, not inherited:

* the linker's preview-lighting sentence, whose exact wording the spec marks
  as unverified;
* the linker's exit code on a successful cached link, which is 2000 -- proof
  that item K3 is right and the code is not a verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zmforge.toolchain.evidence import read_compile_log, read_link_log, strip_colour
from zmforge.verify import check_stage_evidence

LOGS = Path(__file__).parent / "logs"


@pytest.fixture(scope="module")
def compile_log() -> str:
    return (LOGS / "zm_forge_gate.compile.log").read_text(errors="replace")


@pytest.fixture(scope="module")
def link_log() -> str:
    return (LOGS / "zm_forge_gate.link.log").read_text(errors="replace")


@pytest.fixture(scope="module")
def missing_table_link_log() -> str:
    """A real link of zm_price_probe with its weapon table moved aside.

    Captured from a run under Wine.  The linker writes both fastfiles
    and prints "done:", so nothing about the run looks wrong except one
    warning line.
    """
    return (LOGS / "zm_price_probe.missing-table.link.log").read_text(errors="replace")


def test_a_clean_compile_reports_no_leak_and_no_errors(compile_log: str) -> None:
    evidence = read_compile_log(compile_log)
    assert not evidence.leaked
    assert evidence.errors == []


def test_the_only_missing_material_is_the_known_benign_one(compile_log: str) -> None:
    """The stock mystery-box prefab references a name that is not an asset.

    The spec records three warnings per compile; this build produced six.  The
    count is not load-bearing -- what matters is that the name is recognised
    and does not raise the report's severity.
    """
    evidence = read_compile_log(compile_log)
    assert evidence.missing_materials == ["jun_art_wood_plywood_dark03"]
    assert evidence.unexpected_missing_materials == []
    assert compile_log.count("jun_art_wood_plywood_dark03") == 6


def test_the_expected_compile_banners_are_present(compile_log: str) -> None:
    """Both strings the spec predicts for a sealed map with patches."""
    evidence = read_compile_log(compile_log)
    assert evidence.sky_restricted
    assert evidence.curve_collision
    assert not evidence.umbra_volume_unset
    assert not evidence.caulk_terrain_patches


def test_a_successful_link_prints_no_error_lines(link_log: str) -> None:
    evidence = read_link_log(link_log)
    assert evidence.errors == []
    assert "done:" in strip_colour(link_log)


def test_the_missing_bake_is_reported_as_preview_lighting(link_log: str) -> None:
    """Measured wording, replacing the spec's unverified paraphrase."""
    assert "Falling back to preview lighting." in link_log
    report = check_stage_evidence("link", read_link_log(link_log), link_log)
    assert [f.code for f in report.warnings] == ["preview_lighting"]
    assert report.ok, "a missing bake costs appearance, not a build"


def test_a_declared_string_table_the_linker_could_not_find_fails_the_link(
    missing_table_link_log: str,
) -> None:
    """The one warning that must not pass: the map ships with stock prices.

    The link finishes, both fastfiles are written, the exit code is the usual
    non-zero one, and the only sign is a WARNING line.  For a usermap the
    string table it declares is its weapon table, so the silent outcome is a
    map that charges Treyarch's prices and says nothing about it.
    """
    assert "done:" in missing_table_link_log, "the link really did finish"
    evidence = read_link_log(missing_table_link_log)
    assert not evidence.clean
    assert evidence.errors == [
        "WARNING: missing stringTable gamedata/weapons/zm/zm_price_probe_weapons.csv"
    ]
    report = check_stage_evidence("link", evidence, missing_table_link_log)
    assert not report.ok


def test_colour_codes_are_stripped_before_matching(link_log: str) -> None:
    """The linker prefixes its warnings with ``^3``; a naive match misses them."""
    assert "^3Failed to open file" in link_log
    assert "^3" not in strip_colour(link_log)


def test_the_umbra_and_caulk_terrain_checks_fire_when_they_should() -> None:
    """A check that has never fired is not evidence that anything is fine.

    Both of these once silently read attribute names the evidence object
    does not have, so the fixture is a typo guard as much as
    a behaviour test.
    """
    fabricated = (
        "Umbra volume is not set, defaulting to a 1000000 unit cube\n"
        "terrain patches with caulk were discovered\n"
    )
    report = check_stage_evidence("compile", read_compile_log(fabricated), fabricated)
    assert {f.code for f in report.errors} == {"umbra_unset", "caulk_terrain"}
