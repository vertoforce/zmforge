"""Shared fixtures and helpers for the test suite.

- :func:`seed_stock_weapon_table`: several modules commit the shipped recipes
  into a throwaway tools root, and the shipped recipe prices its own guns.
- a built-map cache: a big recipe takes ~15 s to build and a dozen modules
  read it, so each distinct call is built once per process and handed out
  as a deep copy (~0.3 s) that a test may mutate freely.
"""

from __future__ import annotations

import copy
import functools
from pathlib import Path

import pytest


def seed_stock_weapon_table(root) -> Path:
    r"""Put a stand-in for the install's own weapon table under *root*.

    A map that prices a gun **overlays** the install's
    ``zm_levelcommon_weapons.csv`` rather than inventing rows: a row built from
    defaults would link, load and hand the player a gun with no upgrade name,
    no voice-over and no box eligibility, and nothing downstream would say so.
    Committing such a map into a tools root with no stock table is therefore a
    hard error by design (:meth:`zmforge.Project._weapon_table_text`), which is
    what a bare ``tmp_path`` is.

    Treyarch's file is their data and is deliberately not in this repository,
    so this writes a stand-in carrying the real column names -- read from
    :data:`zmforge.emit.weapons.WEAPON_TABLE_COLUMNS`, which was measured off
    the install -- and one row per weapon this level has.  The costs in it are
    placeholders and nothing asserts they are Treyarch's: what the tests using
    it check is that the *map's* costs reach the overlay and that the columns
    beside the cost survive the re-price.
    """
    from zmforge.blueprint.catalogue import LEVEL_WEAPONS
    from zmforge.emit.weapons import COST_COLUMN, NAME_COLUMN, WEAPON_TABLE_COLUMNS

    rows = [",".join(WEAPON_TABLE_COLUMNS)]
    for weapon in sorted(LEVEL_WEAPONS):
        fields = [""] * len(WEAPON_TABLE_COLUMNS)
        fields[NAME_COLUMN] = weapon
        fields[COST_COLUMN] = "1"
        fields[WEAPON_TABLE_COLUMNS.index("upgrade_name")] = f"{weapon}_upgraded"
        fields[WEAPON_TABLE_COLUMNS.index("in_box")] = "TRUE"
        rows.append(",".join(fields))
    directory = Path(root) / "share" / "raw" / "gamedata" / "weapons" / "zm"
    directory.mkdir(parents=True, exist_ok=True)
    table = directory / "zm_levelcommon_weapons.csv"
    table.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return table


@pytest.fixture(scope="session")
def dmv_committed(tmp_path_factory):
    """``zm_dmv`` as the recipe ships it, committed once into a throwaway
    tools root.  Several modules read its files; none writes to it."""
    from zmforge import Project
    from zmforge.mapsource import parse_map_text
    from zmforge.recipes import dmv_of_the_damned

    root = tmp_path_factory.mktemp("dmv_tools_root")
    seed_stock_weapon_table(root)
    project = Project.create("zm_dmv", root, blueprint=dmv_of_the_damned("zm_dmv"))
    result = project.commit()
    paths = project.paths()
    map_text = paths["map"].read_text(encoding="utf-8")
    return {
        "result": result,
        "root": Path(root),
        "document": parse_map_text(map_text),
        "map_text": map_text,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "manifest": paths["manifest"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8")
        if "localized_strings" in paths
        else "",
    }


def draw_or_skip(draw, *args, **kwargs):
    """Call ``draw``; skip when it needs downloaded art or fonts that are absent.

    The photographs and fonts live in the gitignored ``assets-cache/`` (their
    licence records are committed; ``scripts/asset-setup.py --fetch-fonts`` fetches the bytes), so a fresh clone
    skips these rather than fails.  Any other missing file still fails.
    """
    try:
        return draw(*args, **kwargs)
    except FileNotFoundError as exc:
        if "assets-cache" in str(exc):
            pytest.skip(f"downloaded art or font not on this machine: {exc}")
        raise


def load_review_runner():
    """``scripts/review-with-claude.py`` as a module (the example review runner)."""
    import importlib.util
    import sys

    if "review_with_claude" in sys.modules:
        return sys.modules["review_with_claude"]
    path = Path(__file__).resolve().parents[1] / "scripts" / "review-with-claude.py"
    spec = importlib.util.spec_from_file_location("review_with_claude", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["review_with_claude"] = module      # dataclasses look the module up
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def review_runner():
    return load_review_runner()


@pytest.fixture(autouse=True)
def _private_build_locks(tmp_path_factory, monkeypatch):
    """Build locks and heavy-stage reservations in a private directory.

    Without it a test that runs a stage through the Wine runner would wait on
    (or hold) the real build's locks in build-out (zmforge.toolchain.buildlock).
    """
    monkeypatch.setenv("ZMFORGE_LOCK_DIR", str(tmp_path_factory.mktemp("locks")))
    monkeypatch.setenv("ZMFORGE_NO_HEAVY_GATE", "1")


@pytest.fixture
def past_the_lane_rule(monkeypatch):
    """Plant props inside a buyable's approach lane.

    Since :func:`zmforge.blueprint.lanes.enforce`
    drops, at install, any floor prop that reaches into a buyable's lane.  A
    test of a *check* that catches such a prop has to get one past that rule,
    the way a hand-edited map or a future placer bug would.
    """
    from zmforge.blueprint import lanes

    monkeypatch.setattr(lanes, "enforce", lambda blueprint, element: None)


#: The design and layout advisories (docs/playable-map-requirements.md:
#: S1-S6 dressing density and story, D1 training ring, D4 key before lock, D5
#: play lighting, D6 clean fronts, D7 lit paths, D8 room light level, Z74 repeated
#: vignettes and litter, Z75-Z77 walk-through walls, thin riser zones, black
#: walls).  All warnings, every shipped map carries some, and they are each
#: map's room for improvement rather than decisions, so the per-map "only the deliberate
#: warnings" tests leave them out, as they already did Z44.
DESIGN_ADVISORIES = frozenset({
    "S1", "S2", "S3", "S4", "S5", "S6",
    "D1", "D4", "D5", "D6", "D7", "D8",
    "Z74", "Z75", "Z76", "Z77",
})
