"""Z28: the reflection probes a generated map ships, and the check on them.

A probe is the bake's indirect solve, not a gloss layer, so a map with none
is a map with no bounced light.  The numbers these tests assert against come
from two files on the mod tools install and one community map:

* ``rex/templates/ZM Mod Level/map_source/zm/template.map`` -- the map a
  freshly created zombies level starts from -- carries exactly one probe,
  entity 26, ``"name" "probe"``, origin ``4 4 132``, with the unsized
  default box ``size_min``/``size_max`` ``72 72 72``;
* ``bin/t7.def.json``'s ``reflection_probe`` template files most of its keys
  under the group ``2_DIFFUSE_GI`` and says ``in_play_space`` is unavailable
  once every side is over 1000;
* a published community map, ``zm_alien_isolation``, carries 23 probes
  whose boxes run 110 to 2164 units per axis, which is what "sized to
  the room" looks like in released content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zmforge.blueprint.elements import Enclosure, Room, Yard
from zmforge.blueprint.model import Blueprint
from zmforge.emit.mapfile import build_document
from zmforge.lighting import PROBE_PLAY_SPACE_LIMIT, probe_in_play_space
from zmforge.mapsource import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import three_room_map
from zmforge.spatial import Bounds, Point
from zmforge.verify.files import check_gameplay
from zmforge.verify.model import check_blueprint


#: The map a freshly created zombies level starts from, on a local mod
#: tools install.  Same convention as
#: ``tests/test_navmesh.py``'s ``BUILT``: a constant, skipped when absent.
ZM_LEVEL_TEMPLATE = Path(
    "<bo3-wine>/tools/rex/templates/ZM Mod Level/map_source/zm/template.map"
)


def _probes(blueprint):
    return build_document(blueprint).entities_of("reflection_probe")


def _triple(entity, key) -> tuple[float, float, float]:
    x, y, z = entity.value(key).split()
    return (float(x), float(y), float(z))


# --------------------------------------------------------------------------
# What gets emitted
# --------------------------------------------------------------------------
def test_a_generated_map_ships_probes_without_being_asked() -> None:
    """The blank map the tools generate ships one, so zero is below the floor."""
    blueprint = three_room_map("zm_forge_gate")
    assert blueprint.elements(Enclosure)[0].probe is True
    # One per room and one per barricade closet (Z88: a closet is indoor air).
    assert len(blueprint.elements(Room)) == 3
    assert len(_probes(blueprint)) == 3 + len(blueprint.elements(Yard))


def test_each_probe_box_encloses_its_own_room_on_all_three_axes() -> None:
    """The tutorials' rule and the corpus's practice, as arithmetic.

    ``size_min`` and ``size_max`` are half-extents on the negative and the
    positive side, so the box a probe covers is the two summed, centred on
    its origin.
    """
    blueprint = three_room_map("zm_forge_gate")
    rooms = {room.id: room for room in blueprint.elements(Room)}
    covered: set[str] = set()
    for probe in _probes(blueprint):
        origin = Point(*_triple(probe, "origin"))
        low = _triple(probe, "size_min")
        high = _triple(probe, "size_max")
        box = Bounds.between(
            (origin.x - low[0], origin.y - low[1], origin.z - low[2]),
            (origin.x + high[0], origin.y + high[1], origin.z + high[2]),
        )
        for room in rooms.values():
            if box.encloses(room.interior, tolerance=1e-6):
                covered.add(room.id)
    assert covered == set(rooms)


def test_the_boxes_are_not_the_templates_unsized_144_cube() -> None:
    """The template's own probe covers 0.4% of this map; sizing is the point."""
    blueprint = three_room_map("zm_forge_gate")
    for probe in _probes(blueprint):
        low = _triple(probe, "size_min")
        high = _triple(probe, "size_max")
        extents = tuple(a + b for a, b in zip(low, high))
        assert extents != (144.0, 144.0, 144.0)
        assert min(extents) > 0.0


def test_the_probes_carry_the_templates_keys() -> None:
    """Everything that does not depend on the box is entity 26's, verbatim."""
    probe = _probes(three_room_map("zm_forge_gate"))[0]
    assert probe.value("box") == "1"
    assert probe.value("blend_mins") == "3 3 3"
    assert probe.value("blend_maxs") == "3 3 3"
    assert probe.value("placement_offset") == "72"
    assert probe.value("grid_density") == "16"
    assert probe.value("high_detail") == "1"
    assert probe.value("ao_power") == "2"
    assert probe.value("ao_range") == "16"
    assert probe.value("client_server") == "ClientSide"


def test_the_probes_are_named_the_way_radiant_names_them() -> None:
    """``probe``, then ``probe_001`` up, as published maps number them."""
    names = [probe.value("name") for probe in _probes(three_room_map("zm_forge_gate"))]
    assert names == ["probe", *(f"probe_{k:03d}" for k in range(1, len(names)))]
    assert len(names) == 5  # three rooms and two closets


def test_turning_probes_off_emits_none() -> None:
    blueprint = three_room_map("zm_forge_gate")
    blueprint.elements(Enclosure)[0].probe = False
    assert _probes(blueprint) == []


def test_a_map_with_no_rooms_still_gets_one_probe() -> None:
    """Terrain-and-massing maps are not exempt from the blank map's baseline."""
    blueprint = Blueprint("zm_probe_massing_only")
    blueprint.add_block(
        Bounds.between((0.0, 0.0, 0.0), (256.0, 256.0, 64.0)),
        "caulk",
        walkable=True,
        id="slab",
    )
    blueprint.enclose(id="enclosure")
    probes = _probes(blueprint)
    assert len(probes) == 1
    assert probes[0].value("name") == "probe"


# --------------------------------------------------------------------------
# in_play_space, the one rule t7.def.json states
# --------------------------------------------------------------------------
def test_in_play_space_is_set_on_an_ordinary_room_sized_box() -> None:
    for probe in _probes(three_room_map("zm_forge_gate")):
        assert probe.value("in_play_space") == "1"


def test_in_play_space_is_an_all_and_not_an_any() -> None:
    """Unavailable only when **every** side is over 1000, so a long thin
    corridor box keeps it and only a box big on every axis loses it."""
    limit = PROBE_PLAY_SPACE_LIMIT
    assert probe_in_play_space((limit + 1, limit + 1, 64.0)) is True
    assert probe_in_play_space((limit, limit, limit)) is True
    assert probe_in_play_space((limit + 1, limit + 1, limit + 1)) is False


def test_a_room_bigger_than_1000_on_every_axis_drops_in_play_space() -> None:
    blueprint = Blueprint("zm_probe_hall")
    blueprint.add_room(
        Bounds.between((0.0, 0.0, 0.0), (1600.0, 1600.0, 1200.0)), id="hall"
    )
    blueprint.enclose(id="enclosure")
    probe = _probes(blueprint)[0]
    assert probe.value("in_play_space") == "0"


# --------------------------------------------------------------------------
# The check, both ends
# --------------------------------------------------------------------------
def test_z28_passes_on_the_fixture() -> None:
    blueprint = three_room_map("zm_forge_gate")
    report = check_blueprint(blueprint)
    assert [f for f in report.errors if f.code == "Z28"] == []
    assert [f for f in report.warnings if f.code == "Z28"] == []

    document = parse_map_text(render_map_text(build_document(blueprint)))
    files = check_gameplay(document, "")
    assert [f for f in files.errors if f.code == "Z28"] == []
    assert [f for f in files.warnings if f.code == "Z28"] == []


def test_z28_warns_rather_than_errors_when_a_caller_turns_probes_off() -> None:
    """Nothing in the build objects to zero probes, so neither does this."""
    blueprint = three_room_map("zm_forge_gate")
    blueprint.elements(Enclosure)[0].probe = False

    model = check_blueprint(blueprint)
    assert [f for f in model.errors if f.code == "Z28"] == []
    notes = [f for f in model.warnings if f.code == "Z28"]
    assert len(notes) == 1
    assert "template ships one" in notes[0].message

    document = parse_map_text(render_map_text(build_document(blueprint)))
    files = check_gameplay(document, "")
    assert [f for f in files.errors if f.code == "Z28"] == []
    assert len([f for f in files.warnings if f.code == "Z28"]) == 1


def test_z28_fires_when_a_box_no_longer_reaches_its_room() -> None:
    """The tutorials' demonstrated symptom: a brightness step at the box edge.

    Shrinking the boxes back to the mod tools' template cube is exactly the
    defect, so that is what the negative test does.
    """
    blueprint = three_room_map("zm_forge_gate")
    document = build_document(blueprint)
    for probe in document.entities_of("reflection_probe"):
        probe.pairs[:] = [
            (key, "72 72 72" if key in ("size_min", "size_max") else value)
            for key, value in probe.pairs
        ]
    report = check_gameplay(parse_map_text(render_map_text(document)), "")
    # The text-level check only judges the box's own shape, so an undersized
    # but well-formed box is silent here; it is the model side that knows
    # which room the box was meant to cover.
    assert [f for f in report.errors if f.code == "Z28"] == []

    class _Narrowed:
        """A blueprint whose probe boxes have stopped covering its rooms."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def probe_boxes(self):
            return [
                (owner, Bounds.between(box.centre, box.centre + Point(72.0, 72.0, 72.0)))
                for owner, box in self._inner.probe_boxes()
            ]

    errors = [f for f in check_blueprint(_Narrowed(blueprint)).errors if f.code == "Z28"]
    assert sorted(f.element_id for f in errors) == sorted(
        room.id for room in blueprint.elements(Room)
    )


def test_z28_fires_on_a_probe_with_a_flat_box() -> None:
    blueprint = three_room_map("zm_forge_gate")
    document = build_document(blueprint)
    probe = document.entities_of("reflection_probe")[0]
    probe.pairs[:] = [
        (key, "0 0 0" if key in ("size_min", "size_max") else value)
        for key, value in probe.pairs
    ]
    report = check_gameplay(parse_map_text(render_map_text(document)), "")
    errors = [f for f in report.errors if f.code == "Z28"]
    assert len(errors) == 1
    assert "encloses no volume" in errors[0].message


def test_z28_fires_on_in_play_space_the_database_does_not_allow() -> None:
    blueprint = Blueprint("zm_probe_hall")
    blueprint.add_room(
        Bounds.between((0.0, 0.0, 0.0), (1600.0, 1600.0, 1200.0)), id="hall"
    )
    blueprint.enclose(id="enclosure")
    document = build_document(blueprint)
    probe = document.entities_of("reflection_probe")[0]
    probe.pairs[:] = [
        (key, "1" if key == "in_play_space" else value) for key, value in probe.pairs
    ]
    report = check_gameplay(parse_map_text(render_map_text(document)), "")
    errors = [f for f in report.errors if f.code == "Z28"]
    assert len(errors) == 1
    assert "unavailable once every side is over 1000" in errors[0].message


# --------------------------------------------------------------------------
# The corpus this was measured against
# --------------------------------------------------------------------------
def test_the_shipped_template_probe_is_the_one_we_copied() -> None:
    """If the mod tools' template ever stops shipping a probe, say so here."""
    if not ZM_LEVEL_TEMPLATE.exists():
        pytest.skip(f"no mod tools install mirrored at {ZM_LEVEL_TEMPLATE}")
    document = parse_map_text(
        ZM_LEVEL_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    )
    probes = document.entities_of("reflection_probe")
    assert len(probes) == 1
    assert probes[0].value("name") == "probe"
    assert probes[0].value("size_min") == "72 72 72"
