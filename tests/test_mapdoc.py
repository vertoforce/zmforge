"""``zmforge-map/2``: the document a recipe emits and a document-editing client opens.

The recipe is a generator, not the map.  It runs and produces this document
beside the ``.map``; an editing tool may open that document and save it, and the build
chain compiles from it.  These tests hold the properties that make that safe --
that the document carries the half of a map the editor has no tool for, that the
half survives a round trip, and that a map still builds to the same bytes after
one.
"""

from __future__ import annotations

import json
import multiprocessing
import threading
import time

import pytest

from zmforge import mapdoc
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.project import Project
from zmforge.recipes.pranks import prank_map


@pytest.fixture(scope="module")
def blueprint():
    """The fixture that actually carries custom GSC.

    The three-room layout on its own emits no custom script, so a test written
    against it would pass by asserting that nothing was lost from nothing.
    ``prank_map`` wires :mod:`zmforge.script.tricks` onto the same layout.
    """
    return prank_map("zm_mapdoc_fixture")


def test_the_document_carries_the_generated_script(blueprint):
    """The mechanics are in the file, not only in the emitted ``.gsc``.

    The companion this replaces omitted ``ScriptPlan.custom`` entirely, so a
    map's scripted mechanics existed in no document at all -- which is why an
    import had to reconstruct and why an edit could not feed back.
    """
    sections = mapdoc.engine_sections(blueprint)
    functions = sections["script"]["custom"]["functions"]
    assert functions, "the fixture carries no custom script"
    assert any(fn["body"] for fn in functions)
    assert all(isinstance(line, str) for fn in functions for line in fn["body"])


def test_the_script_survives_the_round_trip_byte_for_byte(blueprint):
    """The proof that the format is not lossy where it matters most.

    ``CustomFunction.body`` is raw GSC that the emitter only indents, so the
    test is not "the dict compares equal" but "the emitted game script is the
    same text".  That is what the build chain consumes.
    """
    original = blueprint.script.custom
    restored = mapdoc.custom_script_from_dict(mapdoc.custom_script_to_dict(original))
    assert restored == original

    before_server = render_server_script(blueprint.script)
    before_client = render_client_script(blueprint.script)
    blueprint.script.custom = restored
    assert render_server_script(blueprint.script) == before_server
    assert render_client_script(blueprint.script) == before_client
    blueprint.script.custom = original


def test_every_prop_field_is_carried_including_ones_added_later():
    """Props are serialized from the dataclass, not from a list written by hand.

    ``Prop`` gained ``solid`` and ``collision_box`` while this format was being
    written, and ``collision_box`` is authored input that the per-prop collmap
    files are derived from.  A hand-maintained field list would have dropped
    both silently, so the test is that the document's keys track the dataclass.
    """
    from zmforge.blueprint.elements import Prop
    from zmforge.recipes.layouts import three_room_map

    bp = three_room_map("zm_mapdoc_props")
    bp.place_props([Prop(model="p7_test", origin=_point(8, 16, 0), yaw=90.0)])
    props = mapdoc.engine_sections(bp)["props"]
    assert props, "the blueprint placed no props"
    assert set(props[0]) == set(Prop.__dataclass_fields__) | {"scatter", "id"}
    # The id the `editor` half gives the same prop, so a build can put this
    # record's collision box back on the prop an editing tool is holding.
    assert props[0]["id"] == f"{props[0]['scatter']}_0"


def test_every_sound_column_is_carried_not_only_the_name_and_the_file():
    """A bank row has eleven fields and the document used to carry three.

    A map rebuilt from the short form came back at the template's own volume,
    distances and fades and **NONLOOPING** -- eight columns of an alias row
    differ from the recipe's.
    Nothing reported it: a looping tone written as a one-shot is a mechanic
    that stops on its own.
    """
    from zmforge.emit.sound import CustomSound, SoundAlias, render_alias_bank
    from zmforge.recipes.layouts import three_room_map

    alias = SoundAlias(name="zmf_test_ring", wav="zm_test\\ring.wav", looping=True,
                       volume=88, dist_min=64.0, dist_max_dry=1024.0,
                       dist_max_wet=1200.0, fade_in_ms=250, fade_out_ms=1500)
    bp = three_room_map("zm_mapdoc_sound")
    bp.add_custom_sound(CustomSound(alias=alias, wav_bytes=b"RIFF", credit="synthesised"))

    row = mapdoc.engine_sections(bp)["sounds"][0]
    # `name` rides under the key `alias`, which it has been written under since
    # the format's first day; every other column is spelled as the field is.
    assert set(row) == (set(SoundAlias.__dataclass_fields__) - {"name"}) | {
        "alias", "wav", "credit"}

    # The round trip is the bank, not the dict: that is what the linker reads.
    restored = SoundAlias(name=row["alias"], wav=row["wav"],
                          **{k: v for k, v in row.items()
                             if k in SoundAlias.__dataclass_fields__
                             and k not in ("name", "wav")})
    # The columns this row fills; the install's full header is not needed to
    # compare one bank against another.
    header = ("Name", "Behavior", "Storage", "FileSpec", "Template", "Looping",
              "VolMin", "VolMax", "DistMin", "DistMaxDry", "DistMaxWet",
              "FadeIn", "FadeOut")
    assert render_alias_bank([restored], header) == render_alias_bank([alias], header)


def _point(x, y, z):
    from zmforge.spatial import Point

    return Point(x, y, z)


def test_a_commit_writes_a_document_with_both_halves(tmp_path):
    """The file on disk has the editor's half and the engine's half."""
    bp = prank_map("zm_mapdoc_commit")
    project = Project.create("zm_mapdoc_commit", tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    doc = json.loads(project.paths()["model"].read_text(encoding="utf-8"))

    assert doc["format"] == mapdoc.FORMAT
    assert doc["engine"]["script"]["custom"]["functions"]
    assert doc["origin"] == {
        "kind": "recipe",
        "seed": bp.seed,
        "regenerable": True,
        "edited_since_generate": False,
    }
    assert doc["geometry"]["map_file"] == "zm_mapdoc_commit.map"
    assert doc["geometry"]["guid_seed"] == bp.seed
    # The keys the old companion carried are still there, so an older reader
    # still opens a newer file: Project.open reads seed, title, script, hashes.
    for key in ("version", "name", "seed", "title", "hashes", "script", "elements"):
        assert key in doc


def test_a_reopened_project_still_loads_the_new_document(tmp_path):
    """Growing the companion must not break the reader that already used it."""
    bp = prank_map("zm_mapdoc_reopen")
    Project.create("zm_mapdoc_reopen", tmp_path, blueprint=bp, overwrite=True).commit(
        force=True
    )
    reopened = Project.open("zm_mapdoc_reopen", tmp_path)
    assert reopened.blueprint.seed == bp.seed
    assert reopened.blueprint.script.zones == bp.script.zones


def test_a_write_against_a_stale_revision_is_refused(tmp_path):
    """Compare-and-swap, not a lock: the loser is told and nothing is merged.

    Several writers may edit the same map concurrently, and without a check a
    regenerate can ship another writer's in-flight change.  A lock would need
    a lease and would strand a crashed writer; a revision check has nothing to
    abandon.
    """
    path = tmp_path / "zm_cas.blueprint.json"
    first = mapdoc.save(path, mapdoc.new_document("zm_cas"), written_by="a", expect=None)

    second = dict(first)
    second["editor"] = {"title": "second writer"}
    mapdoc.save(path, second, written_by="b", expect=first["revision"]["id"])

    stale = dict(first)
    stale["editor"] = {"title": "stale writer"}
    with pytest.raises(mapdoc.MapDocConflict):
        mapdoc.save(path, stale, written_by="c", expect=first["revision"]["id"])
    assert json.loads(path.read_text())["editor"]["title"] == "second writer"


def test_creating_a_document_that_already_exists_is_refused(tmp_path):
    """``expect=None`` means "I am making this file", and must not clobber one."""
    path = tmp_path / "zm_new.blueprint.json"
    mapdoc.save(path, mapdoc.new_document("zm_new"), written_by="a", expect=None)
    with pytest.raises(mapdoc.MapDocConflict):
        mapdoc.save(path, mapdoc.new_document("zm_new"), written_by="b", expect=None)


def test_the_same_model_always_produces_the_same_bytes(tmp_path):
    """Diffable means a re-run with no change shows no change of substance.

    Two independent runs of one model are byte-for-byte the same file: that is
    the canonical speller's whole job, and it is what makes a diff of two
    builds the change a person made.

    A re-run *over an existing document* is the same file except for its
    revision, and it has to be: a revision that did not move is a document that
    did not move, and the compare-and-swap in :func:`zmforge.mapdoc.save` reads
    exactly that.  Asserting the identical bytes there asserted that a
    regenerate is undetectable, and two sessions regenerating from one revision
    would both be accepted (pinned in ``tests/test_hand_edits_and_writers.py``).
    So the content is compared and the provenance is expected to move.
    """
    bp = prank_map("zm_mapdoc_stable")
    texts = []
    for index in range(2):
        root = tmp_path / f"run{index}"
        project = Project.create("zm_mapdoc_stable", root, blueprint=bp, overwrite=True)
        project.commit(force=True)
        texts.append(project.paths()["model"].read_text(encoding="utf-8"))
    assert texts[0] == texts[1]

    root = tmp_path / "run0"
    again = Project.create("zm_mapdoc_stable", root, blueprint=bp, overwrite=True)
    again.commit(force=True)
    before, after = (json.loads(texts[0]),
                     json.loads(again.paths()["model"].read_text(encoding="utf-8")))
    assert {k: v for k, v in after.items() if k != "revision"} == {
        k: v for k, v in before.items() if k != "revision"
    }
    assert after["revision"]["parent"] == before["revision"]["id"]
    assert after["revision"]["id"] != before["revision"]["id"]


# ----------------------------------------------------------------------
# Two writers, for real
# ----------------------------------------------------------------------


def _race_writer(job):
    """One racing writer, run in its own process: read, then try to save.

    Module level because it has to be picklable for the pool, and it busy-waits
    to a shared start time so that all eight processes are inside the compare
    at the same moment.  A sleep would let the first writer finish before the
    last one had read, which is the case that always passes.
    """
    path, expect, index, start = job
    doc = mapdoc.load(path)
    doc["editor"] = {"writer": index}
    while time.time() < start:
        pass
    try:
        mapdoc.save(path, doc, written_by=f"writer-{index}", expect=expect)
        return "accepted"
    except mapdoc.MapDocConflict:
        return "refused"
    except OSError as problem:  # a shared temporary file killing a writer
        return f"crashed: {problem!r}"


def test_exactly_one_of_eight_racing_writers_is_accepted(tmp_path):
    """The property the name "compare-and-swap" claimed and did not have.

    Measured without the lock: eight writers holding the same
    revision, twenty rounds -- up to three accepted for one revision, and the
    rest killed by ``FileNotFoundError`` because every writer wrote through the
    same ``<target>.part`` and renamed each other's temporaries away.  Both
    faults are in this one test: more than one acceptance is a lost edit, and a
    crash is a writer that cannot even tell its caller it lost.
    """
    path = tmp_path / "zm_race.blueprint.json"
    seed = mapdoc.save(path, mapdoc.new_document("zm_race"), written_by="seed",
                       expect=None)
    expect = seed["revision"]["id"]
    text = mapdoc.canonical_text(seed)

    context = multiprocessing.get_context("fork")
    for _ in range(3):
        path.write_text(text, encoding="utf-8")       # back to the seed revision
        start = time.time() + 0.3
        with context.Pool(8) as pool:
            verdicts = pool.map(
                _race_writer, [(str(path), expect, i, start) for i in range(8)]
            )
        assert [v for v in verdicts if v.startswith("crashed")] == []
        assert verdicts.count("accepted") == 1, verdicts
        assert verdicts.count("refused") == 7, verdicts
        # And the file is one writer's document, not two spliced together.
        landed = json.loads(path.read_text(encoding="utf-8"))
        assert landed["revision"]["written_by"].startswith("writer-")
        assert set(landed["editor"]) == {"writer"}


def test_the_lock_is_re_entrant_in_one_thread_and_still_shuts_another_out(tmp_path):
    """One thread may take a document's lock twice; a second thread may not.

    ``flock`` belongs to the open file description, so without re-entry a
    second ``open()`` in one thread would wait for the first for ever.  That is
    not an exotic case: :meth:`zmforge.Project.commit` takes the lock, and so
    does every :func:`save`, so anything that holds a document across a commit
    would deadlock against itself.

    Both halves are here.  Re-entering has to work, and it must not be a hole:
    while the outer hold is open another thread still waits.
    """
    path = tmp_path / "zm_reentrant.blueprint.json"
    first = mapdoc.save(path, mapdoc.new_document("zm_reentrant"), written_by="seed",
                        expect=None)

    other_got_in = threading.Event()
    release = threading.Event()

    def other_thread():
        with mapdoc.locked(path):
            other_got_in.set()

    with mapdoc.locked(path):
        with mapdoc.locked(path):                  # the same thread, again
            # and a save, which takes it a third time
            second = mapdoc.save(path, mapdoc.load(path), written_by="inner",
                                 expect=first["revision"]["id"])
        waiter = threading.Thread(target=other_thread)
        waiter.start()
        assert not other_got_in.wait(0.5), "another thread walked straight in"
        release.set()
    waiter.join(10)
    assert other_got_in.is_set(), "the lock was never released"
    assert mapdoc.read_revision(path) == second["revision"]["id"]
    assert not mapdoc._HELD, "a hold was left behind"


def test_the_conflict_probe_answers_without_writing(tmp_path):
    """What a writer asks before it writes, so one holding an old revision is told early.

    A probe, not the guarantee: :func:`~zmforge.mapdoc.save` makes the same
    comparison again under the lock.  What matters here is that a refusal names
    both revisions, because "conflict" on its own leaves a person with no way to
    tell whether to re-open or to keep typing.
    """
    path = tmp_path / "zm_probe.blueprint.json"
    written = mapdoc.save(path, mapdoc.new_document("zm_probe"), written_by="a",
                          expect=None)
    current = written["revision"]["id"]

    assert mapdoc.conflict(path, current) is None

    refusal = mapdoc.conflict(path, "0" * 64)
    assert isinstance(refusal, mapdoc.MapDocConflict)
    assert refusal.expected == "0" * 64
    assert refusal.found == current
    body = refusal.as_dict()
    assert body["expected"] == "0" * 64 and body["found"] == current
    assert mapdoc.read_revision(path) == current      # the probe wrote nothing


# ----------------------------------------------------------------------
# The document and the geometry it describes
# ----------------------------------------------------------------------


def _committed(tmp_path, name):
    project = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    project.commit()
    return project


def test_open_refuses_a_map_that_is_not_the_one_the_document_describes(tmp_path):
    """``geometry.sha256`` was written from the first day and read by nobody.

    The sidecar's one real weakness is that the document and the geometry are
    two files and can drift; the hash is the answer to it, and a hash nothing
    checks is decoration.  Opening a document against a ``.map`` somebody edited
    in Radiant would give a project whose script plan, prop list and hashes are
    all about a map that is no longer there.
    """
    project = _committed(tmp_path, "zm_geom_open")
    map_path = project.paths()["map"]
    recorded = json.loads(project.paths()["model"].read_text())["geometry"]["sha256"]
    map_path.write_text(map_path.read_text() + "\n// edited in Radiant\n")

    with pytest.raises(mapdoc.GeometryMismatch) as caught:
        Project.open("zm_geom_open", tmp_path)
    assert caught.value.recorded == recorded
    assert caught.value.found != recorded
    # Both hashes in the message, or the reader cannot tell which file moved.
    assert recorded in str(caught.value) and caught.value.found in str(caught.value)


def test_a_save_over_geometry_that_moved_is_refused(tmp_path):
    """A save must not re-stamp a document onto a ``.map`` it no longer describes."""
    project = _committed(tmp_path, "zm_geom_save")
    path = project.paths()["model"]
    map_path = project.paths()["map"]
    before = path.read_text(encoding="utf-8")

    doc = mapdoc.load(path)
    map_path.write_text(map_path.read_text() + "\n// edited in Radiant\n")
    with pytest.raises(mapdoc.GeometryMismatch):
        mapdoc.save(path, doc, written_by="editor", expect=mapdoc.read_revision(path))
    assert path.read_text(encoding="utf-8") == before      # nothing was written


def test_a_commit_that_keeps_a_hand_edited_map_describes_the_map_it_kept(tmp_path):
    """The kept file is the geometry now, so the document has to say so.

    A commit that keeps a hand-edited ``.map`` used to record the hash of the
    text it did *not* write, which left a document describing geometry nobody
    had: open, save and compile all refused it, and ``force`` -- the only way
    out -- threw the hand edit away.  ``hashes["map"]`` still holds the
    generator's own last write, which is what tells a hand edit from our text,
    so the next commit keeps the edit again rather than overwriting it.
    """
    project = _committed(tmp_path, "zm_geom_kept")
    paths = project.paths()
    generated = json.loads(paths["model"].read_text(encoding="utf-8"))["hashes"]["map"]
    paths["map"].write_text(paths["map"].read_text(encoding="utf-8") + "// by hand\n",
                            encoding="utf-8")

    again = Project.create("zm_geom_kept", tmp_path,
                           blueprint=prank_map("zm_geom_kept"), overwrite=True)
    assert str(paths["map"]) in again.commit().skipped

    doc = json.loads(paths["model"].read_text(encoding="utf-8"))
    assert doc["geometry"]["sha256"] == mapdoc.file_digest(paths["map"])
    assert doc["hashes"]["map"] == generated       # still the generator's own write
    Project.open("zm_geom_kept", tmp_path)         # opens, rather than refusing
    # And the editor can still save against it, because they now agree.
    mapdoc.save(paths["model"], mapdoc.load(paths["model"]), written_by="editor",
                expect=mapdoc.read_revision(paths["model"]))
    # A third commit keeps the hand edit too: the hand edit is still not ours.
    third = Project.create("zm_geom_kept", tmp_path,
                           blueprint=prank_map("zm_geom_kept"), overwrite=True)
    assert str(paths["map"]) in third.commit().skipped


def test_a_crash_between_the_map_and_the_document_is_repairable(tmp_path):
    """The one window a commit cannot close, and the way out of it.

    A commit renames the ``.map`` and then, a few files later, the document.  A
    crash in between leaves a document describing the previous geometry, and
    every later open, compile and hand save then refuses.  ``force`` is not
    an answer -- it regenerates over the ``.map`` that landed.  Opening with
    ``repair_geometry=True`` adopts the file on disk, names both hashes on the
    way past, and the project opens and commits again.
    """
    project = _committed(tmp_path, "zm_geom_crash")
    paths = project.paths()
    stored = json.loads(paths["model"].read_text(encoding="utf-8"))
    recorded, was = stored["geometry"]["sha256"], stored["revision"]["id"]
    # The .map of the next commit landed; the document of that commit did not.
    paths["map"].write_text(paths["map"].read_text(encoding="utf-8") + "// landed\n",
                            encoding="utf-8")
    landed = mapdoc.file_digest(paths["map"])

    with pytest.raises(mapdoc.GeometryMismatch) as caught:
        Project.open("zm_geom_crash", tmp_path)
    assert recorded in str(caught.value) and landed in str(caught.value)

    repaired = Project.open("zm_geom_crash", tmp_path, repair_geometry=True)
    doc = json.loads(paths["model"].read_text(encoding="utf-8"))
    assert doc["geometry"]["sha256"] == landed
    assert doc["revision"]["parent"] == was    # the repair is a revision of its own
    assert mapdoc.verify_geometry(paths["model"]) == landed
    # and the project is workable again: it commits, and the pair still agree.
    assert repaired.commit(force=True).written
    assert mapdoc.verify_geometry(paths["model"]) == mapdoc.file_digest(paths["map"])


def test_repair_geometry_is_reachable_from_the_command_line(tmp_path, capsys):
    """The way out of a mid-commit crash has to be reachable without Python.

    ``Project.open(repair_geometry=True)`` was library-only, so the mapper who
    hit the refusal had nowhere to go: every command that opens the map refuses
    and none of them offer the repair.  The subcommand names both hashes the
    same way the refusal does -- the recorded one and the one on disk -- so the
    person can still see which file moved before the document is re-anchored.
    """
    from zmforge.facade.cli import main

    project = _committed(tmp_path, "zm_geom_crash")
    paths = project.paths()
    recorded = json.loads(paths["model"].read_text(encoding="utf-8"))["geometry"]["sha256"]
    # The .map of the next commit landed; the document of that commit did not.
    paths["map"].write_text(paths["map"].read_text(encoding="utf-8") + "// landed\n",
                            encoding="utf-8")
    landed = mapdoc.file_digest(paths["map"])

    exit_code = main(["repair-geometry", "zm_geom_crash", "--tools-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert recorded in out and landed in out
    # and the map opens again, which is the whole point of running it.
    assert mapdoc.verify_geometry(paths["model"]) == landed
    assert Project.open("zm_geom_crash", tmp_path)


def test_a_document_with_no_geometry_recorded_is_not_a_mismatch(tmp_path):
    """Nothing to check is not a failure: an editor-first map has never built."""
    path = tmp_path / "zm_nogeom.blueprint.json"
    mapdoc.save(path, mapdoc.new_document("zm_nogeom"), written_by="a", expect=None)
    assert mapdoc.verify_geometry(path) is None


# ----------------------------------------------------------------------
# A commit is a write of eleven files, so it refuses before the first one
# ----------------------------------------------------------------------


def test_a_commit_refuses_when_the_document_moved_under_it(tmp_path):
    """Half a map from each of two sessions is the failure this format exists to stop.

    A commit writes the ``.map``, both scripts, the manifest, the images, the
    collmaps and the document.  Finding the conflict at the document -- the last
    of them -- would mean all the others had already been replaced, so the check
    is before the first write and the refusal is total.
    """
    _committed(tmp_path, "zm_commit_cas")
    project = Project.open("zm_commit_cas", tmp_path)
    path, map_path = project.paths()["model"], project.paths()["map"]

    # Another writer saves in the meantime.
    theirs = mapdoc.load(path)
    theirs["editor"] = {"title": "another session"}
    moved = mapdoc.save(path, theirs, written_by="other",
                        expect=mapdoc.read_revision(path))
    map_before = map_path.read_text(encoding="utf-8")

    with pytest.raises(mapdoc.MapDocConflict) as caught:
        project.commit()
    assert caught.value.found == moved["revision"]["id"]
    assert caught.value.expected != caught.value.found
    assert map_path.read_text(encoding="utf-8") == map_before
    assert mapdoc.load(path)["editor"] == {"title": "another session"}

    # Saying so is what force is for.
    assert project.commit(force=True).written


def test_a_commit_carries_an_editor_edit_through_a_regenerate(tmp_path):
    """A recipe run over an edited document merges rather than refusing.

    ``origin.edited_since_generate`` is the editor saying there is work in the
    file that a replace would destroy.  Refusing would make every regenerate
    for a play build either stop or, with ``--discard-edits``, throw the work
    away, so hand edits are
    carried across by a three-way merge against the last generated document
    (:mod:`zmforge.docmerge`, ``tests/test_docmerge.py``); what survives here
    is that the generate does not lose them and that the discard switch still
    exists for a caller that means it.
    """
    project = _committed(tmp_path, "zm_commit_edited")
    path = project.paths()["model"]

    edited = mapdoc.load(path)
    edited["editor"] = dict(edited["editor"], title="moved a chair in an editor")
    edited["origin"] = dict(edited["origin"], edited_since_generate=True)
    mapdoc.save(path, edited, written_by="editor", expect=mapdoc.read_revision(path))

    regenerate = Project.create(
        "zm_commit_edited", tmp_path,
        blueprint=prank_map("zm_commit_edited"), overwrite=True,
    )
    result = regenerate.commit()
    assert result.merge is not None and result.merge.changed
    after = mapdoc.load(path)
    assert after["editor"]["title"] == "moved a chair in an editor"
    # The work is in the regenerated document now, so the flag that said "there
    # is unmerged work here" is back down.
    assert after["origin"]["edited_since_generate"] is False

    # And a caller that means to throw the edit away still says so, and then
    # the recipe's own `editor` projection is what is on disk.
    edited = mapdoc.load(path)
    edited["editor"] = dict(edited["editor"], title="moved another chair")
    edited["origin"] = dict(edited["origin"], edited_since_generate=True)
    mapdoc.save(path, edited, written_by="editor", expect=mapdoc.read_revision(path))
    again = Project.create(
        "zm_commit_edited", tmp_path,
        blueprint=prank_map("zm_commit_edited"), overwrite=True,
    )
    again.commit(discard_edits=True)
    after = mapdoc.load(path)
    assert after["editor"].get("title") != "moved another chair"
    assert after["origin"]["edited_since_generate"] is False


def test_discard_edits_answers_the_edit_flag_but_not_a_moved_revision(tmp_path):
    """``discard_edits`` is not a second spelling of ``force``.

    The two guards protect different things.  ``origin.edited_since_generate``
    is this map's hand work, which the caller can knowingly throw away; a
    revision that moved is *another writer* having generated or saved over the
    document, which nobody asked to discard.  Answering both with one flag
    would let two writers regenerate from the same revision and both succeed,
    the second silently replacing the first's map with no hand edit anywhere
    in it.
    """
    name = "zm_discard_scope"
    path = _committed(tmp_path, name).paths()["model"]
    start = mapdoc.read_revision(path)

    # Two writers that read the same document, neither of them edited by
    # hand: `edited_since_generate` is false, so the edit guard has nothing
    # to say and only the revision compare stands between them.
    first = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    second = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    assert first.commit().ok
    moved = mapdoc.read_revision(path)
    assert moved != start
    assert mapdoc.load(path)["origin"]["edited_since_generate"] is False

    with pytest.raises(mapdoc.MapDocConflict) as caught:
        second.commit(discard_edits=True)
    assert caught.value.expected == start
    assert caught.value.found == moved
    assert mapdoc.read_revision(path) == moved  # nothing was written

    # And the flag still does its own job: the document this project read,
    # edited by hand since, is discarded when the caller says so.
    edited = mapdoc.load(path)
    edited["editor"] = {"title": "moved a chair in an editor"}
    edited["origin"] = dict(edited["origin"], edited_since_generate=True)
    mapdoc.save(path, edited, written_by="editor", expect=moved)

    regenerate = Project.create(
        name, tmp_path, blueprint=prank_map(name), overwrite=True
    )
    assert regenerate.commit(discard_edits=True).written
    assert mapdoc.load(path)["origin"]["edited_since_generate"] is False


# ----------------------------------------------------------------------
# The editor half: the geometry an editing tool draws
# ----------------------------------------------------------------------
def _editor_fixture(name="zm_editorhalf"):
    """A blueprint with one of everything the editor's document can hold.

    Built by hand rather than taken from a recipe so that each number under test
    is visible in the test: a room with a doorway cut in it, a second room, a
    door hung in that doorway, two zones, a flight of stairs and a box.
    """
    from zmforge import Blueprint
    from zmforge.solids.layout import Aperture
    from zmforge.spatial import Bounds, Facing, Point, Side

    bp = Blueprint(name, seed=name)
    hall = bp.add_room(
        Bounds.between((0, 0, 0), (512, 512, 256)),
        wall=16.0,
        openings=[Aperture(side=Side.NORTH, width=96, height=112)],
        id="hall",
    )
    bp.add_room(Bounds.between((0, 512, 0), (512, 960, 256)), wall=16.0, id="back")
    bp.add_zone("hall", hall, starting=True)
    bp.add_zone("back", bp.find("back"))
    bp.add_door(("hall", "back"), hall.opening(0), price=750, id="door_back")
    bp.add_steps(
        Point(64, 64, 16), 8, 16.0, 8.0, 96.0, Facing.EAST, "t7_metal_worn_iron_dark",
        id="flight",
    )
    bp.add_block(
        Bounds.between((256, 64, 16), (320, 128, 80)), "t7_wood_planks_worn", id="crate"
    )
    return bp


def test_a_recipe_writes_the_half_an_editor_draws(tmp_path):
    """The geometry is in the document, so opening it is a read, not a guess.

    Without an ``editor`` section in a recipe's document, an editing tool has
    to rebuild the geometry from the ``.map`` text -- guessing wall
    thickness from the mode of the upright brushes, sniffing the floor-slab
    convention and inferring which storey an entity stands on.  Each of those is
    a number the blueprint authored.
    """
    from zmforge.blueprint.elements import Room

    bp = _editor_fixture()
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    doc = json.loads(project.paths()["model"].read_text(encoding="utf-8"))

    editor = doc["editor"]
    assert editor["format"] == "zmforge-editor/1"
    assert editor["name"] == bp.name
    assert len(editor["rooms"]) == len(bp.elements(Room))
    # Not the mode of anything: the thickness the rooms were built with.
    assert editor["wall_thickness"] == 16.0
    hall = next(r for r in editor["rooms"] if r["id"] == "hall")
    assert (hall["x0"], hall["y0"], hall["x1"], hall["y1"]) == (0.0, 0.0, 512.0, 512.0)
    assert (hall["z"], hall["height"]) == (0.0, 256.0)
    assert hall["ceiling"] is True
    assert [op["side"] for op in hall["openings"]] == ["north"]


def test_a_flight_of_stairs_is_a_flight_and_not_eight_boxes(tmp_path):
    """The authored form is kept, because it cannot be read back out.

    ``add_steps`` lowers to one box per step the moment it is called.  Eight
    boxes do not say they are a flight, which way it climbs or how tall a step
    is, so the document would either lose the flight or carry it as eight
    blocks; the blueprint keeps the call it was given instead
    (:class:`zmforge.blueprint.elements.AuthoredForm`).
    """
    bp = _editor_fixture()
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    flight = next(s for s in editor["stairs"] if s["id"] == "flight")
    assert flight["steps"] == 8
    assert (flight["step_depth"], flight["step_rise"], flight["width"]) == (16.0, 8.0, 96.0)
    assert flight["direction"] == "+x"
    assert (flight["x"], flight["y"], flight["z"]) == (64.0, 64.0, 16.0)
    # The eight boxes it became are not *also* in the document.
    assert not any(b["id"].startswith("flight") for b in editor["blocks"])
    assert [b["id"] for b in editor["blocks"]] == ["crate"]


def test_a_buyable_door_points_at_the_doorway_it_fills(tmp_path):
    """The two models join by geometry: a door fills its opening's box exactly."""
    bp = _editor_fixture()
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    door = next(d for d in editor["doors"] if d["id"] == "door_back")
    assert door["cost"] == 750
    assert door["room"] == "hall"
    hall = next(r for r in editor["rooms"] if r["id"] == "hall")
    assert door["opening"] in {op["id"] for op in hall["openings"]}
    assert door["flag"] == "enter_back"


def test_a_room_carries_its_own_wall_thickness(tmp_path):
    """One thickness for the map is the default a new room is drawn with, not a narrowing.

    The blueprint keeps a thickness per room, and a room may be built with walls
    thinner than the map's.  Writing only the map-wide number moves every inner
    face of such a room when an editing client rebuilds it: a room with 7.5-unit
    walls in a map of 16 would have its doorways measured against 16 and run past
    corners its real walls do not have.  So the room carries ``wall`` and the
    map-wide number stays the default for the next room drawn.
    """
    from zmforge.spatial import Bounds

    bp = _editor_fixture()
    bp.add_room(Bounds.between((1024, 0, 0), (1280, 256, 256)), wall=7.5, id="scanned")
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    assert editor["wall_thickness"] == 16.0        # what most rooms are built at
    assert next(r for r in editor["rooms"] if r["id"] == "scanned")["wall"] == 7.5
    assert next(r for r in editor["rooms"] if r["id"] == "hall")["wall"] == 16.0
    assert "7.5" not in editor["notes"]            # carried, so not a loss to confess


def test_a_room_nobody_can_reach_says_so_in_the_document(tmp_path):
    """``reachable`` is a declaration, and no geometry can work it out.

    A room with no door yet may be the room the next door opens onto, so the map
    says which rooms are meant to be stood in.  A map editor's reachability and
    size checks can read it: a room that is only ever seen through a sealed
    pane, or a deliberately tiny room 24 units deep, would read as a mistake
    without the declaration.
    """
    from zmforge.spatial import Bounds

    bp = _editor_fixture()
    bp.add_room(Bounds.between((1024, 0, 0), (1280, 256, 256)), reachable=False,
                id="sealed")
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    assert next(r for r in editor["rooms"] if r["id"] == "sealed")["reachable"] is False
    assert next(r for r in editor["rooms"] if r["id"] == "hall")["reachable"] is True


def test_a_door_over_a_stair_flight_crosses_as_that_flight(tmp_path):
    """A gate on a flight points at the flight, not at six numbers.

    A zone stacked over another one has no wall between it and the zone below, so
    the door that sells it hangs across the head of a flight.  The box is derived
    from the flight on both sides of the crossing (``solids.forms.stair_gate``),
    so the document carries the flight's
    id and the editor can put the leaf back on the same step.
    """
    from zmforge.solids.forms import stair_gate
    from zmforge.spatial import Facing, Point

    bp = _editor_fixture()
    gate = bp.add_stair_gate(("hall", "back"), bp.find("flight"), price=1250,
                             id="door_gate")
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    assert gate.box == stair_gate(Point(64, 64, 16), 8, 16.0, 8.0, 96.0, Facing.EAST)
    door = next(d for d in editor["doors"] if d["id"] == "door_gate")
    assert door["stairs"] == "flight"
    assert door["room"] == "" and door["opening"] == ""
    assert door["cost"] == 1250
    # a door in a wall still points at its hole, and at no flight
    in_wall = next(d for d in editor["doors"] if d["id"] == "door_back")
    assert in_wall["stairs"] == "" and in_wall["opening"]


def test_a_block_says_whether_a_player_stands_on_it_and_can_get_to_it(tmp_path):
    """Two flags no geometry carries, and the build needs both.

    A box drawn in the editor is a ledge: you stand on it and you can reach it.  A
    yard's five walls and a shelf in a sealed vault are neither, and rebuilt as
    ordinary blocks the engine's playable-area check asks for a zone over every
    one of them, and a map rebuilt from its own document fails with ``Z18``
    errors.
    """
    from zmforge.spatial import Bounds

    bp = _editor_fixture()
    bp.add_block(Bounds.between((300, 300, 16), (360, 360, 80)), "t7_metal_worn_iron_dark",
                 walkable=False, reachable=False, id="shelf")
    bp.add_block(Bounds.between((300, 400, 16), (360, 460, 80)), "t7_metal_worn_iron_dark",
                 walkable=True, id="ledge")
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    shelf = next(b for b in editor["blocks"] if b["id"] == "shelf")
    assert shelf["walkable"] is False and shelf["reachable"] is False
    ledge = next(b for b in editor["blocks"] if b["id"] == "ledge")
    assert ledge["walkable"] is True and ledge["reachable"] is True


def test_what_the_editor_cannot_hold_is_written_down_rather_than_dropped(tmp_path):
    """A narrowing is in the document's notes, where a person reads it.

    A buyable door belongs to a hole in a wall or to the head of a flight.  One
    hung in a free span that is neither -- a box of its own over open floor -- has
    nowhere to go in the editor's model, and that is a real loss and a silent one
    unless the document says so.
    """
    from zmforge.spatial import Bounds

    bp = _editor_fixture()
    # Over the hall's open floor, well clear of `door_back`'s own leaf in the
    # north wall: two door leaves drawn through each other is refused by the
    # standing-room rule (`blueprint/reach.py`), and what this test is about
    # is a door belonging to no opening, not two doors in one place.
    bp.add_door(("hall", "back"), Bounds.between((64, 200, 16), (128, 216, 112)),
                price=900, id="door_nowhere")
    project = Project.create(bp.name, tmp_path, blueprint=bp, overwrite=True)
    project.commit(force=True)
    editor = json.loads(project.paths()["model"].read_text(encoding="utf-8"))["editor"]

    homeless = next(d for d in editor["doors"] if d["id"] == "door_nowhere")
    assert homeless["opening"] == "" and homeless["stairs"] == ""
    assert "door_nowhere" in editor["notes"]


# --------------------------------------------------------------------------
# What the engine half has to carry for a build driven from the document
# --------------------------------------------------------------------------
def test_the_document_carries_what_the_map_charges_for_a_gun() -> None:
    """A price set on a wall buy is a re-price, and the section has to say so.

    ``weapons.prices`` is only what ``set_weapon_price`` was called with, and a
    map can price every gun it sells through the buys instead -- the shipped
    recipe does exactly that, six times -- at which point the section that
    promises "the per-weapon re-prices" answered with an empty object.
    ``weapons.table`` is the effective table: the rows the map's own
    ``<name>_weapons.csv`` is built from, buys included.
    """
    from zmforge.recipes import three_room_map
    from zmforge.spatial import Facing, Point

    bp = three_room_map("zm_mapdoc_prices")
    bp.set_weapon_price("ar_standard", 1234)
    bp.place_wall_weapon(
        "smg_fastfire",
        Point(0, 0, 0),
        Facing.NORTH,
        price=200,
        id="mapdoc_buy",
    )
    weapons = mapdoc.engine_sections(bp)["weapons"]
    assert weapons["prices"] == {"ar_standard": 1234}
    assert weapons["table"] == {"ar_standard": 1234, "smg_fastfire": 200}
    assert weapons["table"] == bp.weapon_price_table()


def test_the_document_names_the_models_this_project_builds_itself() -> None:
    """A model the install has never seen is a build step, not a name.

    A map that names one and is compiled without it links **clean** and ships
    without the model, with no error line anywhere. So the document has to say
    which of the placed models are ours and what to build each from; a build
    driven from this file cannot work that out from a model name.
    """
    from zmforge.blueprint.elements import Prop
    from zmforge.props.library import KITS, prop as kit_prop
    from zmforge.recipes import three_room_map
    from zmforge.spatial import Point

    entry = kit_prop("zmf_prop_toilet")
    bp = three_room_map("zm_mapdoc_models")
    bp.place_props(
        [
            Prop(model=entry.name, origin=Point(0, 0, 0), yaw=0.0, solid=True),
            Prop(model=entry.name, origin=Point(64, 0, 0), yaw=0.0, solid=True),
            # A stock model in the same scatter is not ours and is not listed.
            Prop(model="p7_crate_wood_01", origin=Point(128, 0, 0), yaw=0.0),
        ],
        id="mapdoc_kit",
    )
    models = mapdoc.engine_sections(bp)["models"]
    assert [row["model"] for row in models] == [entry.name]
    row = models[0]
    assert row["placed"] == 2
    assert row["kit"] == entry.kit and row["member"] == entry.member
    assert row["solid"] is entry.solid
    assert row["archive"] == KITS[entry.kit].archive
    assert row["licence"] == KITS[entry.kit].licence


def test_a_map_that_prices_nothing_and_builds_no_model_says_so(blueprint) -> None:
    """The two new keys are empty on a map that needs neither, not absent.

    A key that disappears when it has nothing to say reads, in a diff, the
    same as a key somebody deleted.
    """
    sections = mapdoc.engine_sections(blueprint)
    assert sections["weapons"]["table"] == {}
    assert sections["models"] == []


def test_a_commit_that_cannot_replace_one_file_leaves_the_previous_map_whole(
    tmp_path, monkeypatch
):
    """Windows refuses a rename over a file another program holds open (WinError 5).

    The commit used to rename file by file, so a refusal part way left the new
    ``.map`` and scripts beside the old document.  Now every file is staged
    first and a failed rename puts back the ones already replaced.  The refusal
    here is on the document, the last rename, so every other file had already
    been replaced and has to come back.
    """
    import os

    from zmforge import project as project_module

    project = _committed(tmp_path, "zm_held_open")
    paths = project.paths()

    def snapshot():
        return {
            p.relative_to(tmp_path): p.read_bytes()
            for p in tmp_path.rglob("*")
            if p.is_file() and not p.name.endswith(".lock")
        }

    before = snapshot()
    again = Project.open("zm_held_open", tmp_path)
    again.blueprint.title = "A different title"
    real_replace = os.replace

    def refuse_document(src, dst, *a, **kw):
        if str(dst) == str(paths["model"]):
            raise PermissionError(13, "Access is denied", str(dst))
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(project_module.os, "replace", refuse_document)
    changed = {"force": True, "worldspawn_overrides": [("zmforge_probe", "1")]}
    with pytest.raises(project_module.FileHeldOpen) as caught:
        again.commit(**changed)
    assert str(paths["model"]) in str(caught.value)
    monkeypatch.setattr(project_module.os, "replace", real_replace)
    assert snapshot() == before
    # and the next commit, with the file released, goes through.
    assert again.commit(**changed).written
    assert paths["map"].read_bytes() != before[paths["map"].relative_to(tmp_path)]
    assert mapdoc.verify_geometry(paths["model"]) == mapdoc.file_digest(paths["map"])
