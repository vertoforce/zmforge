"""Regenerating a map carries hand edits forward instead of refusing them.

A recipe run that refused a document another tool had edited and saved, with
``--discard-edits`` as the only way past the refusal, would leave every build
two choices: stop, or destroy the hand work.  A shared document would then be
a document only one of the two tools could really use.

The tests below are the six cases a three-way merge has to get right, held
against :func:`zmforge.docmerge.merge_document` where they are easiest to state,
and then the same behaviour held end to end through :meth:`Project.commit`,
which is where the ancestor file, the lock and the discard switch live.
"""

from __future__ import annotations

import json

import pytest

from zmforge import docmerge, mapdoc
from zmforge.errors import RegenerateWouldDiscard
from zmforge.project import Project
from zmforge.recipes.pranks import prank_map


# ----------------------------------------------------------------------
# Fixtures: documents small enough to read in the assertion
# ----------------------------------------------------------------------
def _doc(props, *, title="Fixture", engine_props=()):
    """A document with the shape the merge cares about and nothing else.

    Only ``editor`` and ``engine`` are merged, so the bookkeeping sections are
    here as themselves rather than as realistic values: a test that had to
    stamp a revision to assert something about a prop would be testing two
    things.
    """
    return {
        "format": mapdoc.FORMAT,
        "name": "zm_merge_fixture",
        "revision": {"id": "whatever"},
        "origin": {"kind": "recipe", "edited_since_generate": False},
        "editor": {"title": title, "grid": 16.0, "props": list(props)},
        "engine": {"props": list(engine_props), "script": {"custom": {}}},
    }


def _prop(identity, x, model="chair"):
    return {"id": identity, "model": model, "x": x, "y": 0, "z": 0}


def _props(document):
    return {p["id"]: p for p in document["editor"]["props"]}


# ----------------------------------------------------------------------
# The six cases
# ----------------------------------------------------------------------
def test_a_document_nobody_edited_merges_to_the_regenerated_one():
    """No edits means the merge is the identity on the regenerated document.

    The property that lets the merge run on every generate: a map nobody has
    edited by hand must come out of a regenerate byte-identical to what
    it would have been with no merge at all, or the feature taxes every build
    for the benefit of the few that need it.
    """
    base = _doc([_prop("chair_1", 0), _prop("chair_2", 64)])
    new = _doc([_prop("chair_1", 0), _prop("chair_2", 96)], title="Regenerated")

    result = docmerge.merge_document(base, json.loads(json.dumps(base)), new)

    assert result.document == new
    assert result.notes == []
    assert result.summary() == []


def test_an_element_only_the_user_changed_keeps_the_users_version():
    """The generator did not touch it, so there is nothing to weigh it against.

    This is the case the old refusal existed for and the one it answered by
    destroying: the recipe re-emits an identical chair, the person moved it,
    and the only defensible result is the chair where they put it.
    """
    base = _doc([_prop("chair_1", 0)])
    current = _doc([_prop("chair_1", 512)])  # moved by hand
    new = _doc([_prop("chair_1", 0)])  # the recipe emits what it always did

    result = docmerge.merge_document(base, current, new)

    assert _props(result.document)["chair_1"]["x"] == 512
    assert [n.kind for n in result.notes] == ["kept_user"]
    assert result.conflicts == []
    assert "editor.props[chair_1].x" == result.notes[0].path


def test_an_element_only_the_generator_changed_takes_the_regenerated_version():
    """The point of regenerating at all.

    A merge that kept the user's document wherever the two differed would be a
    merge that ignored the recipe, which is the mirror of the bug being fixed.
    """
    base = _doc([_prop("chair_1", 0)])
    current = _doc([_prop("chair_1", 0)])  # opened by hand, not moved
    new = _doc([_prop("chair_1", 320)])  # the recipe moved it

    result = docmerge.merge_document(base, current, new)

    assert _props(result.document)["chair_1"]["x"] == 320
    assert result.notes == []


def test_both_sides_changing_one_element_is_a_conflict_and_the_user_wins():
    """The conflict policy, stated once.

    Keeping the generator's version would make a regenerate silently undo hand
    work -- exactly what this change exists to stop -- so the user's version is
    kept.  Keeping it *silently* would leave a map that no longer matches the
    recipe with nothing anywhere saying so, so it is reported.  Both halves are
    asserted here because either one alone is a different, worse policy.
    """
    base = _doc([_prop("chair_1", 0)])
    current = _doc([_prop("chair_1", 512)])
    new = _doc([_prop("chair_1", 320)])

    result = docmerge.merge_document(base, current, new)

    assert _props(result.document)["chair_1"]["x"] == 512
    assert [n.kind for n in result.conflicts] == ["conflict"]
    conflict = result.conflicts[0]
    assert conflict.path == "editor.props[chair_1].x"
    assert "512" in conflict.detail and "320" in conflict.detail
    assert any("CONFLICT" in line for line in result.summary())


def test_an_element_the_user_added_survives_the_regenerate():
    """"Absent" is the same in the base and in the regenerate, so nobody removed it.

    A prop added by hand is in no recipe and will be in no regenerate
    ever; if a merge only ever reconciled elements the generator knows about,
    the first rebuild would delete it and the editor would be a scratchpad.
    """
    base = _doc([_prop("chair_1", 0)])
    current = _doc([_prop("chair_1", 0), _prop("barrel_hand", 136, model="barrel")])
    new = _doc([_prop("chair_1", 0)])

    result = docmerge.merge_document(base, current, new)

    merged = _props(result.document)
    assert merged["barrel_hand"]["model"] == "barrel"
    assert [n.kind for n in result.notes] == ["user_added"]
    # The generator's own order is preserved and the addition rides behind it.
    assert [p["id"] for p in result.document["editor"]["props"]] == [
        "chair_1",
        "barrel_hand",
    ]


def test_an_element_the_generator_dropped_is_kept_when_the_user_edited_it():
    """A recipe that stops emitting something must not delete a person's work.

    Both cases are asserted together because the difference between them is the
    whole rule: an element the recipe dropped and nobody touched is *supposed*
    to go, and one the recipe dropped after somebody edited it is a conflict
    whose losing side is a person's afternoon.
    """
    base = _doc([_prop("chair_1", 0), _prop("chair_2", 64)])
    current = _doc([_prop("chair_1", 512), _prop("chair_2", 64)])  # edited chair_1
    new = _doc([])  # the recipe no longer emits either

    result = docmerge.merge_document(base, current, new)

    merged = _props(result.document)
    assert merged["chair_1"]["x"] == 512, "an edited element vanished silently"
    assert "chair_2" not in merged, "an untouched element the recipe dropped was kept"
    assert [n.kind for n in result.conflicts] == ["conflict_generator_removed"]
    assert result.conflicts[0].path == "editor.props[chair_1]"
    assert "<absent>" in result.conflicts[0].detail


# ----------------------------------------------------------------------
# Things the element rules imply
# ----------------------------------------------------------------------
def test_deleting_an_element_in_an_editor_does_not_bring_it_back():
    """A removal is an edit like any other, and is reported because it loses a
    generated element from the map."""
    base = _doc([_prop("chair_1", 0), _prop("chair_2", 64)])
    current = _doc([_prop("chair_2", 64)])
    new = _doc([_prop("chair_1", 0), _prop("chair_2", 64)])

    result = docmerge.merge_document(base, current, new)

    assert "chair_1" not in _props(result.document)
    assert [n.kind for n in result.notes] == ["user_removed"]


def test_two_sides_editing_two_different_elements_is_not_a_conflict():
    """Identity is what makes the merge finer than the file.

    Without per-element resolution this is one changed ``props`` list on each
    side and therefore a whole-list conflict, which would drop the recipe's
    work on every map that has ever been edited by hand.
    """
    base = _doc([_prop("chair_1", 0), _prop("chair_2", 64)])
    current = _doc([_prop("chair_1", 512), _prop("chair_2", 64)])
    new = _doc([_prop("chair_1", 0), _prop("chair_2", 999)])

    result = docmerge.merge_document(base, current, new)

    merged = _props(result.document)
    assert (merged["chair_1"]["x"], merged["chair_2"]["x"]) == (512, 999)
    assert result.conflicts == []


def test_the_engine_half_merges_by_id_too():
    """Solidity, prices and scripts live in the engine half, and an editing
    tool may write there too."""
    base = _doc([], engine_props=[{"id": "p1", "model": "crate", "solid": False}])
    current = _doc([], engine_props=[{"id": "p1", "model": "crate", "solid": True}])
    new = _doc([], engine_props=[{"id": "p1", "model": "crate", "solid": False}])

    result = docmerge.merge_document(base, current, new)

    assert result.document["engine"]["props"][0]["solid"] is True
    assert result.notes[0].path == "engine.props[p1].solid"


def test_bookkeeping_sections_always_come_from_the_regenerate():
    """Merging a hash table or a revision id describes a write that never
    happened, so the merge is scoped to the two halves that describe the map."""
    base = _doc([])
    current = _doc([])
    current["origin"]["edited_since_generate"] = True
    current["hashes"] = {"map": "an old hash"}
    new = _doc([])
    new["hashes"] = {"map": "the hash this commit wrote"}

    result = docmerge.merge_document(base, current, new)

    assert result.document["hashes"] == {"map": "the hash this commit wrote"}
    assert result.document["origin"]["edited_since_generate"] is False


def test_a_list_with_no_ids_is_compared_whole_rather_than_guessed_at():
    """``editor.element_order`` is a list of strings and has no identity to
    merge on; matching by position would move one element's value onto
    another's, which is worse than a conflict."""
    base = _doc([])
    base["editor"]["element_order"] = ["a", "b"]
    current = _doc([])
    current["editor"]["element_order"] = ["a", "b", "hand_added"]
    new = _doc([])
    new["editor"]["element_order"] = ["a", "b", "c"]

    result = docmerge.merge_document(base, current, new)

    assert result.document["editor"]["element_order"] == ["a", "b", "hand_added"]
    assert [n.kind for n in result.conflicts] == ["conflict"]


# ----------------------------------------------------------------------
# End to end, through a real commit
# ----------------------------------------------------------------------
def _committed(tmp_path, name):
    project = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    project.commit()
    return project


def _save_editor_edit(path, mutate):
    """What an editing tool does: change the editor half, mark it, save under
    the revision it read."""
    document = mapdoc.load(path)
    mutate(document)
    document["origin"] = dict(document["origin"], edited_since_generate=True)
    return mapdoc.save(
        path, document, written_by="editor", expect=mapdoc.read_revision(path)
    )


def test_a_commit_leaves_the_ancestor_the_next_merge_needs(tmp_path):
    """Without a stored ancestor there is no three-way merge, only a guess, so
    the file is written by every commit rather than by a separate step somebody
    can forget."""
    project = _committed(tmp_path, "zm_merge_base")
    base_path = project.paths()["model_base"]

    assert base_path.name == "zm_merge_base" + docmerge.BASE_SUFFIX
    assert base_path.parent == project.paths()["model"].parent
    assert base_path.read_bytes() == project.paths()["model"].read_bytes()


def test_a_regenerate_over_an_editor_edit_carries_it_forward(tmp_path):
    """A regenerate over an edited document carries the edit forward, not raises.

    The edit is a renamed room rather than a synthetic key, so what is asserted
    is that a real element of the editor's half survives a real recipe run.
    """
    name = "zm_merge_forward"
    project = _committed(tmp_path, name)
    path = project.paths()["model"]
    room_id = mapdoc.load(path)["editor"]["rooms"][0]["id"]

    def rename_first_room(document):
        document["editor"]["rooms"][0]["name"] = "The Renamed Room"

    _save_editor_edit(path, rename_first_room)

    regenerate = Project.create(
        name, tmp_path, blueprint=prank_map(name), overwrite=True
    )
    result = regenerate.commit()

    assert result.ok
    after = mapdoc.load(path)
    rooms = {room["id"]: room for room in after["editor"]["rooms"]}
    assert rooms[room_id]["name"] == "The Renamed Room"
    assert result.merge is not None and result.merge.changed
    assert result.merge.conflicts == []
    assert any(room_id in line for line in result.merge.summary())
    # The flag is the editor's way of saying "there is work in here"; the work
    # is now in the regenerated document, so the next generate has nothing to
    # carry until somebody saves again.
    assert after["origin"]["edited_since_generate"] is False


def test_the_ancestor_is_the_recipes_output_not_the_merged_document(tmp_path):
    """An edit is carried on *every* regenerate, and is not a conflict on the
    second one.

    This is the one design decision in the ancestor file and it was got wrong
    first: storing the merged document as the base made every edit the merge
    had just carried look like a change the recipe had made, so the next
    regenerate reported a conflict on each of them and the noise grew with
    every build.  Storing what the recipe produced keeps the question the base
    is there to answer -- "what would the generator have written?" -- and both
    assertions below fail if it is stored the other way.
    """
    name = "zm_merge_ancestor"
    project = _committed(tmp_path, name)
    path = project.paths()["model"]

    def rename(document):
        document["editor"]["rooms"][0]["name"] = "Carried"

    _save_editor_edit(path, rename)

    for _ in range(2):  # two regenerates, one hand save between them
        result = Project.create(
            name, tmp_path, blueprint=prank_map(name), overwrite=True
        ).commit()
        assert mapdoc.load(path)["editor"]["rooms"][0]["name"] == "Carried"
        assert result.merge is not None
        assert result.merge.conflicts == [], "a carried edit became a conflict"

    # And the hand edit is still in charge of itself: putting the recipe's
    # name back is honoured rather than merged away.
    def revert(document):
        document["editor"]["rooms"][0]["name"] = "Start Room"

    _save_editor_edit(path, revert)
    Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True).commit()
    assert mapdoc.load(path)["editor"]["rooms"][0]["name"] == "Start Room"


def test_a_regenerate_with_no_editor_edit_reports_no_merge(tmp_path):
    """A map nobody edited by hand goes through a plain generate and says
    nothing about merging."""
    name = "zm_merge_quiet"
    _committed(tmp_path, name)

    result = Project.create(
        name, tmp_path, blueprint=prank_map(name), overwrite=True
    ).commit()

    assert result.ok
    assert result.merge is None


def test_discard_edits_still_means_start_clean(tmp_path):
    """The escape hatch has to keep working, and has to keep meaning what it
    says: the recipe's own document, with the hand work gone."""
    name = "zm_merge_discard"
    project = _committed(tmp_path, name)
    path = project.paths()["model"]

    def rename(document):
        document["editor"]["rooms"][0]["name"] = "Thrown Away"

    _save_editor_edit(path, rename)

    regenerate = Project.create(
        name, tmp_path, blueprint=prank_map(name), overwrite=True
    )
    result = regenerate.commit(discard_edits=True)

    after = mapdoc.load(path)
    assert "Thrown Away" not in json.dumps(after["editor"])
    assert result.merge is None
    # And the ancestor was reset to the recipe's own output, so the next
    # regenerate does not merge the discarded edit back in.
    assert (
        project.paths()["model_base"].read_bytes() == path.read_bytes()
    )


def test_an_editor_edit_with_no_ancestor_still_refuses(tmp_path):
    """The one case a merge cannot be attempted on.

    With no record of what the last generate wrote, a difference between the
    document and the recipe's output cannot be attributed to either side, so
    the old refusal stands -- and says how to get out of it, which for any map
    generated from now on is a single discarding run.
    """
    name = "zm_merge_no_base"
    project = _committed(tmp_path, name)
    path = project.paths()["model"]

    def rename(document):
        document["editor"]["rooms"][0]["name"] = "Edited"

    _save_editor_edit(path, rename)
    project.paths()["model_base"].unlink()  # a map generated before this existed

    regenerate = Project.create(
        name, tmp_path, blueprint=prank_map(name), overwrite=True
    )
    with pytest.raises(RegenerateWouldDiscard) as caught:
        regenerate.commit()
    assert docmerge.BASE_SUFFIX in str(caught.value)
    assert "--discard-edits" in str(caught.value)
    assert mapdoc.load(path)["editor"]["rooms"][0]["name"] == "Edited"


def test_the_report_cuts_the_list_off_but_never_hides_a_conflict():
    """One editing session can easily move two hundred props.

    The whole point of the report is that a conflict is seen; a list long
    enough to scroll the conflicts off the top of a build log would be a report
    that hid the only part of itself worth reading.
    """
    notes = [
        docmerge.MergeNote(f"editor.props[p{i}].x", "kept_user") for i in range(60)
    ]
    notes.append(docmerge.MergeNote("editor.props[p99].x", "conflict"))
    lines = docmerge.MergeResult({}, notes).summary(limit=10)

    assert sum("CONFLICT" in line for line in lines) == 1
    assert any("and 50 more kept without conflict" in line for line in lines)
    assert len(lines) < 20
