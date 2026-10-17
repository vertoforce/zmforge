"""The prop notes file: every model it names must be a real catalogue or kit model.

``src/zmforge/props/notes.json`` is read by ``Z58`` and ``Z59``
(``verify/looks.py``) and by ``Z13`` for its suggested swap.  These tests guard against the notes drifting from
reality: a typo'd model name, a made-up confidence level, a note that quietly
stops parsing, or a fact kept in two places.
"""

from __future__ import annotations

from zmforge.props.notes import (
    NOTES_PATH,
    PropNote,
    category_note,
    gaps,
    material_note,
    model_note,
    prop_notes,
)
from zmforge.props.library import PROPS
from zmforge.recipes.props import CATALOGUE_BOX

_VALID_RENDERS = {"ok", "dark", "blank", "wrong_colour", "editor_invisible"}
_VALID_PLACEMENT = {"wall", "floor", "surface", "ceiling", "hanging"}
_VALID_CONFIDENCE = {"measured", "review_only"}
_VALID_LOCAL_TOOLS = {"present", "missing"}


def _known_model_names() -> set[str]:
    return set(CATALOGUE_BOX) | {p.name for p in PROPS}


def test_the_notes_file_exists_and_parses():
    assert NOTES_PATH.exists(), NOTES_PATH
    notes = prop_notes()
    assert set(notes) == {"models", "categories", "materials", "gaps"}


def test_every_named_model_is_in_the_catalogue_or_the_kit():
    known = _known_model_names()
    notes = prop_notes()
    missing = [name for name in notes["models"] if name not in known]
    assert not missing, f"notes.json names models zmforge does not know: {missing}"


def test_every_model_note_has_a_source():
    for name, note in prop_notes()["models"].items():
        assert note.source, f"{name} has no source"


def test_every_category_note_says_what_it_matches():
    for key, note in prop_notes()["categories"].items():
        assert note.match, f"category {key!r} has no match description"
        assert note.source, f"category {key!r} has no source"


def test_every_material_note_has_a_source():
    for name, note in prop_notes()["materials"].items():
        assert note.source, f"material {name!r} has no source"


def test_every_gap_has_a_source():
    for note in gaps():
        assert note.source, f"gap {note.key!r} has no source"


def test_renders_placement_and_confidence_are_from_the_known_vocabulary():
    for section in ("models", "categories"):
        for key, note in prop_notes()[section].items():
            if note.renders is not None:
                assert note.renders in _VALID_RENDERS, (section, key, note.renders)
            if note.placement is not None:
                assert note.placement in _VALID_PLACEMENT, (section, key, note.placement)
            assert note.confidence in _VALID_CONFIDENCE, (section, key, note.confidence)
    for section in ("models",):
        for key, note in prop_notes()[section].items():
            if note.local_tools is not None:
                assert note.local_tools in _VALID_LOCAL_TOOLS, (key, note.local_tools)


def test_local_tools_comes_from_the_z13_ledger_not_the_notes_file():
    """One source: notes.json stores no ``local_tools``; the loader derives it
    from installed_assets.json by the verdict Z13 uses."""
    import json

    from zmforge.blueprint.installed import judge_misc_model, load_ledger

    raw = json.loads(NOTES_PATH.read_text())
    for section in ("models", "categories"):
        for key, entry in raw[section].items():
            assert "local_tools" not in entry, (section, key)
    ledger = load_ledger()
    assert ledger is not None, "installed_assets.json ledger is missing"
    assert model_note("p6_bar_beer_glass").local_tools == "missing"
    assert judge_misc_model("p6_bar_beer_glass", ledger) == "unlinkable"
    assert model_note("p7_picture_frame_modern_01").local_tools == "present"


def test_z13_names_the_swap_the_notes_record():
    from zmforge.blueprint.elements import Room
    from zmforge.recipes.layouts import three_room_map
    from zmforge.spatial import Point
    from zmforge.verify import check_blueprint

    bp = three_room_map("zm_notes_probe")
    room = next(r for r in bp.elements(Room) if r.id == "arena_room")
    bp.place_props([("p6_bar_beer_glass", Point(0.0, 0.0, room.floor_z), 0.0, 1.0, False)],
                   id="probe_glass")
    found = [str(f) for f in check_blueprint(bp).errors if f.code == "Z13" and "p6_bar_beer_glass" in str(f)]
    assert found and "use coffee mugs" in found[0], found


def test_categories_match_by_pattern_and_needs_merge():
    from zmforge.props.notes import categories_for, needs_of

    assert [n.key for n in categories_for("p7_cloth_drape_02_beige")] == ["curtain"]
    # poster_or_wall_sign has a pattern (the Z60 rules)
    assert [n.key for n in categories_for("p7_picture_frame_modern_01")] == ["poster_or_wall_sign"]
    assert categories_for("p7_zm_der_cabinet_lab_bottom") == ()
    assert needs_of("p7_cloth_drape_02_beige") == ("rail",)
    assert needs_of("p7_consumer_grade_monitor_medium") == ("desk", "chair_facing")


def test_round_8_corn_facts():
    stalk, thin = model_note("zmf_prop_corn_stalk"), model_note("zmf_prop_corn_stalk_thin")
    assert stalk.solid is False and stalk.size == (34, 34, 96)
    assert thin.solid is False and thin.size == (22, 22, 90)
    assert model_note("zmf_prop_jack_o_lantern").size == (16, 16, 13.6)
    assert any("sack-head" in g.key for g in gaps())
    assert category_note("named_brush_entity").renders == "ok"
    assert material_note("t7_wood_planks_worn") is not None


def test_every_noted_size_matches_the_measured_box():
    from zmforge.recipes.props import MODEL_BOX

    for key, note in prop_notes()["models"].items():
        if note.size:
            lo, hi = MODEL_BOX[key]
            assert all(abs((h - l) - n) < 0.5 for l, h, n in zip(lo, hi, note.size)), (key, note.size)


def test_model_note_lookup():
    note = model_note("p7_3arc_lobby_picture_41x29")
    assert isinstance(note, PropNote)
    assert note.renders == "dark"
    assert note.use_instead == "p7_picture_frame_modern_01"
    assert model_note("zmforge_probe_definitely_not_a_model") is None


def test_category_note_lookup():
    note = category_note("perk_machine")
    assert note is not None
    assert note.renders == "editor_invisible"
    assert category_note("not_a_real_category") is None


def test_material_note_lookup():
    note = material_note("t7_acrylic_red_flake")
    assert note is not None
    assert note.use_instead
    assert material_note("not_a_real_material") is None


def test_gaps_lists_at_least_the_wooden_table():
    wants = [g.key for g in gaps()]
    assert any("table" in w for w in wants)


def test_prop_notes_is_cached_and_returns_the_same_object():
    assert prop_notes() is prop_notes()
