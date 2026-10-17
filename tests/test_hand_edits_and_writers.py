"""Regenerating a committed project: hand edits and concurrent writers.

Two promises are pinned here.  A hand-edited ``.map`` is kept on regenerate
and the project still opens, saves and builds afterwards.  And a commit
refuses when the document on disk is not the revision this project read, so
two regenerates started from one revision cannot both land.
"""

from __future__ import annotations

import json

import pytest

from zmforge import mapdoc
from zmforge.errors import RegenerateWouldDiscard
from zmforge.project import Project
from zmforge.recipes.pranks import prank_map


def _committed(tmp_path, name):
    project = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    result = project.commit()
    assert result.ok, [str(f) for f in result.report.errors]
    return project


def test_a_kept_hand_edit_is_the_geometry_the_document_records(tmp_path):
    """A hand-edited ``.map`` is kept (a hand_edited warning, not overwritten),
    and the document's ``geometry.sha256`` is the hash of that kept file.

    Open, save and build all refuse a ``.map`` whose hash disagrees with the
    document.  A document that recorded the ``.map`` the commit would have
    written, rather than the one it kept, would be refused by all three, and
    the only way out would be ``force=True``, which throws the hand edit away.
    """
    name = "zm_review_handedit"
    _committed(tmp_path, name)
    regen = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    paths = regen.paths()
    map_path, doc_path = paths["map"], paths["model"]

    map_path.write_text(map_path.read_text(encoding="utf-8") + "// a mapper's hand edit\n",
                        encoding="utf-8")

    result = regen.commit()          # the documented default: keep hand edits
    assert str(map_path) in result.skipped, "the hand edit was not kept"

    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    on_disk = mapdoc.file_digest(map_path)
    # The document now describes geometry that is not on disk...
    assert doc["geometry"]["sha256"] == on_disk, (
        "geometry.sha256 names the .map the commit did NOT write; "
        f"recorded {doc['geometry']['sha256'][:12]}, on disk {on_disk[:12]}")


def test_a_project_with_a_kept_hand_edit_opens(tmp_path):
    """After a kept hand edit, ``Project.open`` succeeds."""
    name = "zm_review_handedit2"
    _committed(tmp_path, name)
    regen = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    map_path = regen.paths()["map"]
    map_path.write_text(map_path.read_text(encoding="utf-8") + "// hand edit\n", encoding="utf-8")
    assert str(map_path) in regen.commit().skipped
    # The project reopens with the hand edit kept (no GeometryMismatch).
    Project.open(name, tmp_path)


def test_two_overwrite_regenerates_from_one_revision_cannot_both_commit(tmp_path):
    """Commit refuses when the document on disk is not the revision this
    project read, and that holds for ``Project.create(overwrite=True)`` too.

    An overwrite reads the revision id but must also arm the compare;
    otherwise two regenerates started from the same revision are both
    accepted and the second silently replaces the first.
    """
    name = "zm_review_overwrite_race"
    _committed(tmp_path, name)
    doc_path = Project.create(name, tmp_path, blueprint=prank_map(name),
                              overwrite=True).paths()["model"]
    r0 = mapdoc.read_revision(doc_path)

    first = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    second = Project.create(name, tmp_path, blueprint=prank_map(name), overwrite=True)
    assert first._doc_revision == r0 and second._doc_revision == r0

    assert first.commit().ok
    r1 = mapdoc.read_revision(doc_path)
    assert r1 != r0

    with pytest.raises(mapdoc.MapDocConflict):
        second.commit()              # holds r0, disk is at r1: must refuse


def test_a_document_saved_after_open_is_not_replaced_blind(tmp_path):
    """A project opened with a ``.map`` but no document refuses to commit over
    a document another writer saved in the meantime."""
    name = "zm_review_nodoc"
    project = _committed(tmp_path, name)
    doc_path = project.paths()["model"]
    doc_path.unlink()
    reopened = Project.open(name, tmp_path)
    # meanwhile another writer saves a document there
    other = _committed(tmp_path, name)
    theirs = mapdoc.read_revision(other.paths()["model"])
    assert theirs
    with pytest.raises((mapdoc.MapDocConflict, RegenerateWouldDiscard)):
        reopened.commit(force=True if False else False)
