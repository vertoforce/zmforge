"""Every data file shipped under src/zmforge must be listed in package-data.

A wheel install only carries the non-Python files that
`[tool.setuptools.package-data]` names; anything missing works from a
checkout and crashes with FileNotFoundError after `pip install` (seen with
props/stock_collmaps.json at props/collision.py).
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "zmforge"
DATA_SUFFIXES = {".json", ".csv", ".tmpl", ".txt", ".ttf", ".otf", ".gdt", ".gsc", ".csc"}


def _package_data() -> dict[str, list[str]]:
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return cfg["tool"]["setuptools"].get("package-data", {})


def _covered(path: Path, globs: dict[str, list[str]]) -> bool:
    rel_parts = path.relative_to(PKG.parent).parts
    for pkg, patterns in globs.items():
        pkg_parts = tuple(pkg.split("."))
        if rel_parts[: len(pkg_parts)] != pkg_parts:
            continue
        inner = "/".join(rel_parts[len(pkg_parts):])
        if any(fnmatch.fnmatch(inner, pat) for pat in patterns):
            # The owning directory must also be an importable package.
            if (PKG.parent.joinpath(*pkg_parts) / "__init__.py").exists():
                return True
    return False


def test_every_data_file_is_in_package_data():
    globs = _package_data()
    data = [
        p for p in PKG.rglob("*")
        if p.is_file() and p.suffix in DATA_SUFFIXES and "__pycache__" not in p.parts
    ]
    assert data, "expected data files under src/zmforge"
    missing = [str(p.relative_to(PKG)) for p in data if not _covered(p, globs)]
    assert not missing, f"not in [tool.setuptools.package-data]: {missing}"


def test_code_opened_data_files_exist_and_are_covered():
    """The files the code opens by `Path(__file__)` are the ones that crashed."""
    globs = _package_data()
    for rel in ("props/stock_collmaps.json", "props/stock_origins.json",
                "props/notes.json", "blueprint/installed_assets.json",
                "texture/templates/hud_image_entry.gdt.tmpl"):
        p = PKG / rel
        assert p.is_file(), rel
        assert _covered(p, globs), rel
