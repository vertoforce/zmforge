"""One collmap per kit prop: the props converter and the map generator write
the same bytes to ``share/raw/collmaps/zmf_prop_*.map``.

Otherwise the converter writes the mesh's exact bounds with GUIDs seeded
by the name, the generator the recorded box (3 decimals) with GUIDs seeded
by ``stock:<name>``, and whichever runs last wins.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from zmforge import mapsource
from zmforge.props.collision import (
    KIT_BOX_TOLERANCE,
    check_kit_box,
    kit_box,
    kit_collmap_document,
)
from zmforge.props.library import PROPS
from zmforge.recipes.props import MODEL_BOX
from zmforge.spatial import Point, Span

KIT_NAMES = sorted(n for n in MODEL_BOX if n.startswith("zmf_prop_"))


def _text(document, tmp: Path, name: str) -> bytes:
    path = tmp / f"{name}.map"
    mapsource.write(path, document)
    return path.read_bytes()


def test_every_library_prop_has_a_recorded_box():
    solid = sorted(p.name for p in PROPS if p.solid)
    assert [n for n in solid if n not in MODEL_BOX] == []


def test_the_kit_collmap_is_deterministic(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for name in KIT_NAMES:
        a = _text(kit_collmap_document(name), tmp_path / "a", name)
        b = _text(kit_collmap_document(name), tmp_path / "b", name)
        assert a == b, name


def _generator_writes(tmp: Path, models: list[str]) -> Path:
    """Run the generator's collmap step (Project._write_prop_collmaps) on a stub."""
    from zmforge.blueprint.elements import PropScatter
    from zmforge.project import Project

    props = [SimpleNamespace(model=m, solid=True, collision_box=MODEL_BOX[m]) for m in models]
    scatter = SimpleNamespace(props=props)
    out = tmp / "generator"
    stub = SimpleNamespace(
        blueprint=SimpleNamespace(elements=lambda kind: [scatter] if kind is PropScatter else []),
        layout=SimpleNamespace(collmap_dir=out),
    )
    Project._write_prop_collmaps(stub)  # type: ignore[arg-type]
    return out


def test_the_generator_writes_the_kit_collmap(tmp_path):
    out = _generator_writes(tmp_path, KIT_NAMES)
    for name in KIT_NAMES:
        assert (out / f"{name}.map").read_bytes() == _text(
            kit_collmap_document(name), tmp_path, name), name


def test_converter_and_generator_write_the_same_bytes(tmp_path):
    from zmforge.props.build import build as build_props

    prop = next(p for p in PROPS if p.solid and p.name in MODEL_BOX)
    try:
        build_props("zm_one_source", tmp_path / "staging", [prop])
    except (OSError, RuntimeError) as exc:  # no kit archive and no network
        pytest.skip(f"cannot convert {prop.name} here: {exc}")
    converter = (tmp_path / "staging" / "collmaps" / f"{prop.name}.map").read_bytes()
    generator = (_generator_writes(tmp_path, [prop.name]) / f"{prop.name}.map").read_bytes()
    assert converter == generator


def test_a_missing_or_drifted_box_is_refused():
    box = kit_box(KIT_NAMES[0])
    check_kit_box(KIT_NAMES[0], box)
    with pytest.raises(ValueError, match="CATALOGUE_BOX first"):
        check_kit_box("zmf_prop_not_recorded", box)
    moved = Span(Point(box.mins.x - 2 * KIT_BOX_TOLERANCE, box.mins.y, box.mins.z), box.maxs)
    with pytest.raises(ValueError, match="units off"):
        check_kit_box(KIT_NAMES[0], moved)
