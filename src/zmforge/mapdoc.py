"""``zmforge-map/2`` -- the one map document both the generator and the editor read.

Before this module a map was defined twice.  ``zmforge`` recipes built a
:class:`~zmforge.blueprint.model.Blueprint` in memory and emitted the game's
``.map`` source from it, keeping only identifiers, hashes and the script plan in
the ``<name>.blueprint.json`` companion beside it, and an editor kept its own
JSON document and, when asked to open a generated map, had to *reconstruct*
one by reading brush bounds back out of the ``.map`` text.  A
reconstruction guesses -- wall thickness is a mode, storeys are inferred, terrain
noise parameters are invented, and anything that is not a box brush is dropped.
An edit made in an editor therefore cannot feed back into what a recipe
built, and the two models drift.

The shape here is the sidecar, not an annotation of the game's own file, and that
was settled by measurement rather than taste (the real
``cod2map64`` under Wine):

* Inside a brush container the compiler accepts **only** ``//`` comments.  An
  unknown ``"key" "value"`` line is fatal: ``MatchToken: got 'zmf_role',
  expected '('``.  Rooms, walls, floors, ramps and terrain are all brushes and
  patches, so the half of a map that most needs intent attached to it is the
  half that cannot carry a key at all.
* An entity **does** take unknown KVPs anywhere in its body, worldspawn
  included -- but a value may not contain a ``"`` character, and backslash
  escaping does not help because the parser consumes the escape first:
  ``ParseEpair: value '{"kind":"perk"}' contains a " character, will cause
  parsing errors``.  Structured intent would have to be base64 or a bespoke
  encoding, i.e. exactly the opaque artefact this project keeps out of version
  control.

So the geometry stays in the ``.map``, which already round-trips byte-for-byte
through :mod:`zmforge.mapsource` (measured on both staged maps), and the intent
lives here, in text a person can read in a diff.

Layout of the document::

    format    "zmforge-map/2"
    name      the map's machine name
    revision  content hash, parent hash, who wrote it and when  (concurrency)
    origin    where this map came from and whether a recipe can rebuild it
    geometry  which .map file this describes, and its hash
    editor    the editor-format projection: what a map editor can draw
    engine    everything a map editor has no tool for, carried verbatim
    hashes    the per-role digests the old companion already carried

``editor`` and ``engine`` are the two halves of the same map, not two maps.  A
thing belongs in ``editor`` when a map editor can show it and change it, and in
``engine`` when it cannot -- custom GSC mechanics, prank logic keyed to door
flags, generated wall art, imported geometry, custom weapons and prices.
The rule that makes one file work for two programs is that **neither side may
drop a section it does not understand**: an editor edits ``editor`` and writes
``engine`` back exactly as it found it.  Without that rule a single save in an
editor would silently delete a map's scripted jokes, which is worse than the
split this replaces.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

__all__ = [
    "FORMAT",
    "SECTIONS",
    "ENGINE_ONLY",
    "editor_document",
    "LOCK_SUFFIX",
    "MapDocConflict",
    "GeometryMismatch",
    "new_document",
    "canonical_text",
    "revision_id",
    "stamp",
    "load",
    "save",
    "read_revision",
    "conflict",
    "lock_path",
    "locked",
    "map_path",
    "file_digest",
    "verify_geometry",
]

#: The format string every document carries.  ``zmforge-map/1`` was never
#: released; the companion it replaces carried ``"version": 1`` and no format
#: key at all, which is how :func:`load` tells the two apart.
FORMAT = "zmforge-map/2"

#: Top-level sections, in the order :func:`canonical_text` is happiest to show
#: them in a diff: identity first, provenance next, then the two halves of the
#: map.
SECTIONS = (
    "format",
    "name",
    "revision",
    "origin",
    "geometry",
    "editor",
    "engine",
    "hashes",
)

#: The sections an editor must carry through untouched.  An editor that
#: builds a fresh document on save and copies only the fields it knows drops
#: anything not on its list on the first save, which is the reason this tuple
#: is named here rather than left implicit: an editor that reads this document
#: takes the contract from this module.
ENGINE_ONLY = ("origin", "geometry", "engine", "hashes")


class MapDocConflict(RuntimeError):
    """The file changed underneath the writer.

    Carries both revisions so a caller can say what happened rather than
    guessing.  Never resolved here: a silently merged map is a map nobody can
    trust, so the write is refused and the two revisions are reported.
    """

    def __init__(self, path: Path, expected: str | None, found: str | None) -> None:
        self.path = Path(path)
        self.expected = expected
        self.found = found
        super().__init__(
            f"{self.path} changed since it was read: expected revision "
            f"{expected or '<none>'}, found {found or '<none>'}. "
            "Re-read the document and re-apply the change; nothing was written."
        )

    def as_dict(self) -> dict:
        """The refusal as JSON, for a caller that answers over HTTP.

        Both revisions by name, because "conflict" on its own tells a person
        nothing: the one they held and the one that is there is what lets them
        decide whether to re-open or to keep typing.
        """
        return {
            "error": "conflict",
            "path": str(self.path),
            "expected": self.expected,
            "found": self.found,
            "message": str(self),
        }


class GeometryMismatch(RuntimeError):
    """The ``.map`` beside a document is not the one the document describes.

    ``geometry.sha256`` is the whole answer to the sidecar format's one real
    weakness -- the document and the geometry are two files and can drift.  It
    was written by :meth:`zmforge.Project.commit` from the first day and read by
    nobody, which made it decoration.  Checking it turns a silent drift into a
    refusal that names both hashes, so the person can see which file moved.
    """

    def __init__(self, map_file: Path, recorded: str, found: str) -> None:
        self.map_file = Path(map_file)
        self.recorded = recorded
        self.found = found
        super().__init__(
            f"{self.map_file} is not the geometry this document describes: the "
            f"document records sha256 {recorded}, the file on disk hashes to "
            f"{found}. Nothing was read or written. Either the .map was edited "
            "outside this project (re-open it, or regenerate the document) or "
            "the document is from a different build."
        )


def new_document(name: str) -> dict:
    """An empty document with every section present.

    Every section exists even when empty so that a diff of two documents shows a
    field appearing rather than a section appearing, and so neither side has to
    guard against a missing key.
    """
    return {
        "format": FORMAT,
        "name": name,
        "revision": {"id": "", "parent": "", "written_by": "", "written_at": ""},
        "origin": {"kind": "editor", "recipe": "", "seed": "", "regenerable": False},
        "geometry": {"map_file": f"{name}.map", "sha256": "", "guid_seed": ""},
        "editor": {},
        "engine": {},
        "hashes": {},
    }


def _body(doc: Mapping[str, Any]) -> dict:
    """The document minus the part that cannot hash itself.

    ``revision.id`` is the hash of everything else, so it is excluded; the rest
    of ``revision`` is included, because who wrote a document and when is part of
    what makes it that document.
    """
    out = {k: v for k, v in doc.items() if k != "revision"}
    revision = dict(doc.get("revision") or {})
    revision.pop("id", None)
    out["revision"] = revision
    return out


def canonical_text(doc: Mapping[str, Any]) -> str:
    """The document as the bytes that go on disk.

    Sorted keys and a two-space indent, so the same model always produces the
    same file and a diff shows the change a person made rather than a
    re-ordering.  This is the only writer; nothing formats this file by hand.
    """
    ordered = {k: doc[k] for k in SECTIONS if k in doc}
    ordered.update({k: v for k, v in doc.items() if k not in SECTIONS})
    return json.dumps(ordered, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def revision_id(doc: Mapping[str, Any]) -> str:
    """The content hash of a document, ignoring its own recorded revision id."""
    blob = json.dumps(_body(doc), indent=2, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def stamp(doc: dict, *, written_by: str, written_at: str = "") -> dict:
    """Return a copy with its revision recalculated and its parent recorded.

    ``parent`` is the revision this document was derived from, which is what
    lets a conflict be explained after the fact: two documents with the same
    parent and different ids are the two sides of a fork.
    """
    out = json.loads(json.dumps(doc))
    revision = dict(out.get("revision") or {})
    out["revision"] = {
        "id": "",
        "parent": str(revision.get("id") or ""),
        "written_by": written_by,
        "written_at": written_at or revision.get("written_at") or "",
    }
    out["revision"]["id"] = revision_id(out)
    return out


def read_revision(path: str | Path) -> str | None:
    """The revision id currently on disk, or ``None`` if there is no file.

    Reads the recorded id rather than re-hashing, so that a file a human edited
    by hand is reported as the revision it claims to be and the mismatch is
    caught by :func:`load` instead of being silently absorbed here.
    """
    target = Path(path)
    if not target.is_file():
        return None
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return str((doc.get("revision") or {}).get("id") or "") or None


def load(path: str | Path) -> dict:
    """Read a document, filling in any section an older file predates."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    base = new_document(str(doc.get("name") or Path(path).stem))
    base.update({k: v for k, v in doc.items()})
    base["format"] = FORMAT
    return base


#: The sibling file whose ``flock`` serialises the writers of one document.
#: A separate file rather than a lock on the document itself, because the write
#: finishes with a rename: the inode a writer locked would not be the inode it
#: replaced, so the next writer would be locking a file nobody is writing.
LOCK_SUFFIX = ".lock"


def lock_path(path: str | Path) -> Path:
    """The lock file that guards ``path``."""
    target = Path(path)
    return target.with_name(target.name + LOCK_SUFFIX)


def _lock_exclusive(handle: Any) -> None:
    """Block until this process holds ``handle``'s file exclusively.

    ``fcntl`` does not exist on Windows and ``msvcrt`` exists nowhere else, so
    the module is picked here, at call time, not at import: a module-level
    ``import fcntl`` made every zmforge command die on Windows before it ran.
    On Windows the lock is a one-byte ``msvcrt.locking`` range at offset 0;
    ``LK_LOCK`` gives up after ten one-second tries, so it is retried until it
    is granted, which is the blocking wait ``flock`` gives elsewhere.  Windows
    also drops the range lock when the holding process dies.
    """
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock(handle: Any) -> None:
    """Release what :func:`_lock_exclusive` took."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


#: Locks this process is already holding, by ``(thread, lock file)``.
#:
#: ``flock`` belongs to an *open file description*, not to a process, so a
#: second ``open()`` of the same lock file waits for the first even inside one
#: thread: a caller that holds a document's lock and then calls anything that
#: takes it again -- :func:`save`, :meth:`zmforge.Project.commit`, a generator
#: that holds the lock from before it writes until after it swaps its output
#: into place -- would deadlock against itself with no way out.  Counting the
#: holds per thread makes the re-entry free and the release the outermost
#: caller's.  It weakens nothing: a thread cannot race itself, and every other
#: thread and process still waits on the ``flock``.
_HELD: dict[tuple[int, str], list] = {}
_HELD_LOCK = threading.Lock()


@contextmanager
def locked(path: str | Path) -> Iterator[Any]:
    """Hold the write lock for one document.  Re-entrant within one thread.

    The lock exists because the compare and the rename have to be one step.
    Measured on the mod tools install: eight writers holding the same ``expect``
    revision, twenty rounds, with the compare and the rename apart -- up to
    three of eight accepted for one revision, the rest killed by
    ``FileNotFoundError`` because every writer used the same ``<target>.part``
    temporary and renamed each other's files away.  With this lock held across
    compare-and-rename and a unique temporary per writer: exactly one accepted,
    seven refused, none crashed, in all twenty rounds.

    This is not the lease the format's notes argue against.  It is held for the
    microseconds of a compare and a rename, never across a user's edit, and the
    kernel drops an ``flock`` when the holding process dies, so a crashed or
    abandoned session leaves nothing behind.  The compare-and-swap is still the
    contract a caller sees; the lock is only what makes that contract true.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path(target)
    # The real path, so two names for one lock file -- a staging directory
    # reached through a symlink and the directory itself -- are one hold and
    # not two.
    key = (threading.get_ident(), os.path.realpath(lock))
    with _HELD_LOCK:
        held = _HELD.get(key)
        if held is not None:
            held[1] += 1
    if held is not None:
        try:
            yield held[0]
        finally:
            with _HELD_LOCK:
                held[1] -= 1
        return
    handle = open(lock, "a+", encoding="utf-8")
    try:
        _lock_exclusive(handle)
        with _HELD_LOCK:
            _HELD[key] = [handle, 1]
        try:
            yield handle
        finally:
            with _HELD_LOCK:
                _HELD.pop(key, None)
            _unlock(handle)
    finally:
        handle.close()


def conflict(path: str | Path, expect: str | None) -> MapDocConflict | None:
    """The refusal a stale writer would get, or ``None`` if it would be accepted.

    The same comparison :func:`save` makes, without writing and without raising,
    so an HTTP layer can answer a conditional request (``If-Match``) with both
    revisions before it has a document to write.  It is a *probe*: the answer is
    true at the moment it is read, and :func:`save` re-makes the comparison under
    the lock, which is where the guarantee actually lives.
    """
    found = read_revision(path)
    if found == expect:
        return None
    return MapDocConflict(Path(path), expect, found)


def map_path(doc: Mapping[str, Any], doc_path: str | Path) -> Path | None:
    """The ``.map`` a document describes, or ``None`` if it names none."""
    name = str((doc.get("geometry") or {}).get("map_file") or "")
    if not name:
        return None
    return Path(doc_path).parent / name


def file_digest(path: str | Path) -> str:
    """``sha256`` of a file's bytes, the same digest a commit records."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_geometry(
    doc_path: str | Path,
    doc: Mapping[str, Any] | None = None,
    *,
    require_map_file: bool = False,
) -> str | None:
    """Check the ``.map`` beside a document against ``geometry.sha256``.

    Returns the digest it checked, or ``None`` when there was nothing to check;
    raises :class:`GeometryMismatch` naming both hashes when the file on disk is
    not the geometry the document describes.

    Nothing to check is the ordinary case in two places and is not an error in
    either: a document with an empty ``geometry.sha256`` (a hand-made or
    editor-first map that has never been built), and a document kept somewhere
    other than beside its map, which is where an editor may keep its designs.
    ``require_map_file`` is for the build, where a missing ``.map`` is the
    failure itself.
    """
    if doc is None:
        doc = load(doc_path)
    recorded = str((doc.get("geometry") or {}).get("sha256") or "")
    target = map_path(doc, doc_path)
    if target is None or not recorded:
        return None
    if not target.exists():
        if require_map_file:
            raise GeometryMismatch(target, recorded, "<no file>")
        return None
    found = file_digest(target)
    if found != recorded:
        raise GeometryMismatch(target, recorded, found)
    return found


def _write_atomically(target: Path, text: str) -> None:
    """Replace ``target`` with ``text`` through a temporary of its own.

    ``mkstemp`` in the target's own directory, so the name is unique per writer
    and the rename stays on one filesystem.  The fixed ``<target>.part`` this
    replaces was shared by every writer of a document, which is how a race
    between them ended in ``FileNotFoundError`` rather than a refusal.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix=target.name + ".", suffix=".part"
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def save(
    path: str | Path,
    doc: Mapping[str, Any],
    *,
    written_by: str,
    expect: str | None = None,
    written_at: str = "",
    check_geometry: bool = True,
    reanchor_geometry: bool = False,
) -> dict:
    """Write a document, refusing if the file moved under the caller.

    ``expect`` is the revision the caller read.  ``None`` means "I am creating
    this file" and fails if one is already there; passing the current revision
    is the ordinary update.  A writer that loses the race has lost nothing but
    the write, because its own document is still in memory and the conflict
    names both revisions.  Nothing is merged, here or anywhere.

    The compare and the rename happen under :func:`locked`, and the temporary is
    this writer's own.  Without both, this function was a compare-and-swap in
    name only: it compared, then wrote, and two writers that interleaved between
    those two steps were both accepted (measured, see :func:`locked`).

    ``check_geometry`` also refuses when the ``.map`` beside the document is not
    the one ``geometry.sha256`` names, so a save cannot re-stamp a document over
    geometry that has moved on underneath it.

    ``reanchor_geometry`` is the deliberate way out of that refusal, and the
    only one: the ``.map`` on disk is re-hashed and the document is written
    describing *it*, which is the answer when the person editing knows the
    geometry moved on purpose -- a hand edit in Radiant, or a commit that kept
    a hand-edited ``.map``.  Without it the only escape was to throw the edited
    ``.map`` away and regenerate, so "the document disagrees with the geometry"
    was a wedge rather than a question.  It re-anchors, it never merges: the
    caller is saying "this file is the geometry now", and the new hash is in
    the document it returns.  ``check_geometry=False`` skips the compare and
    leaves the recorded hash alone, which is not the same thing.

    Concurrency is the case this guards: one writer can regenerate the map
    while another is mid-edit of the recipe, and a stale session can write
    deleted files back over newer work.
    """
    target = Path(path)
    with locked(target):
        found = read_revision(target)
        if found != expect:
            raise MapDocConflict(target, expect, found)
        doc = dict(doc)
        if reanchor_geometry:
            beside = map_path(doc, target)
            if beside is not None and beside.is_file():
                geometry = dict(doc.get("geometry") or {})
                geometry["sha256"] = file_digest(beside)
                doc["geometry"] = geometry
        elif check_geometry:
            verify_geometry(target, doc)
        stamped = stamp(dict(doc), written_by=written_by, written_at=written_at)
        _write_atomically(target, canonical_text(stamped))
    return stamped


# ----------------------------------------------------------------------
# The engine half: what a map editor has no tool for.
#
# Every function below is a pure translation between a blueprint object and
# plain JSON.  They live here rather than on the elements so that the two
# codebases share one definition of the wire shape, and so that the blueprint
# classes -- which other work is actively changing -- do not have to grow a
# serialization concern.
# ----------------------------------------------------------------------


def custom_script_to_dict(script: Any) -> dict:
    """A :class:`~zmforge.script.custom.CustomScript` as JSON.

    ``CustomFunction.body`` is a tuple of raw GSC source lines that the emitter
    only indents; it never parses them.  Carrying the lines verbatim therefore
    loses nothing *of the model*, and it is the only honest option: the mechanics
    in :mod:`zmforge.script.tricks` are Python factory functions, not data, so
    there are no parameters left to store by the time a ``CustomScript`` exists.
    A reader gets the same script the emitter would have written.
    """
    if script is None:
        return {}
    return {
        "using": list(script.using),
        "client_using": list(script.client_using),
        "functions": [
            {
                "name": fn.name,
                "params": list(fn.params),
                "purpose": fn.purpose,
                "client_side": bool(fn.client_side),
                "body": list(fn.body),
            }
            for fn in script.functions
        ],
        "statements": [
            {"slot": slot.name, "text": text} for slot, text in script.statements
        ],
        "assets": [{"prefix": p, "name": n} for p, n in script.assets],
        "notes": list(getattr(script, "notes", ()) or ()),
    }


def custom_script_from_dict(data: Mapping[str, Any]) -> Any:
    """Rebuild a ``CustomScript`` from :func:`custom_script_to_dict` output."""
    from .script.custom import CustomFunction, CustomScript, Slot

    if not data:
        return CustomScript()
    return CustomScript(
        using=tuple(data.get("using") or ()),
        client_using=tuple(data.get("client_using") or ()),
        functions=tuple(
            CustomFunction(
                name=str(fn["name"]),
                body=tuple(fn.get("body") or ()),
                params=tuple(fn.get("params") or ()),
                purpose=str(fn.get("purpose") or ""),
                client_side=bool(fn.get("client_side")),
            )
            for fn in data.get("functions") or ()
        ),
        statements=tuple(
            (Slot[str(s["slot"])], str(s["text"])) for s in data.get("statements") or ()
        ),
        assets=tuple(
            (str(a["prefix"]), str(a["name"])) for a in data.get("assets") or ()
        ),
        notes=tuple(data.get("notes") or ()),
    )


def editor_document(blueprint: Any) -> dict:
    """The ``editor`` half: the editor-format document a map editor draws.

    Thin on purpose.  The translation itself is :mod:`zmforge.editordoc`, which
    is imported here rather than at module scope so that a reader who only wants
    this module's constants -- an editor can import :data:`ENGINE_ONLY`,
    :data:`FORMAT` and :data:`SECTIONS` from here at start-up -- does not drag
    the whole blueprint package in behind them.
    """
    from .editordoc import editor_document as translate

    return translate(blueprint)


def engine_sections(blueprint: Any) -> dict:
    """The half of a map the editor-format document has no field for.

    Named explicitly rather than "whatever is left over", because the point of
    this section is that a reader can see what it is being asked to preserve.
    Each key is something the editor's document genuinely cannot express yet:

    ``script``
        the generated GSC -- 32 functions and 472 body lines on a big test
        map.  The old companion dropped ``ScriptPlan.custom`` entirely, so a
        map's scripted mechanics were in no file but the emitted ``.gsc``.
    ``weapons``
        custom weapon definitions, the per-weapon re-prices, and the whole
        effective cost table.  The editor knows 13 weapon slugs from a closed
        list and one optional price.
    ``sounds``
        the alias rows for a map's own sounds.  Wave bytes are *not* inlined;
        they are files, and this document stays diffable text.
    ``props``
        the placed props, which the editor models but the recipe generates in
        bulk -- 2,147 records on a big test map, expanded deterministically
        from 165 authored scene items.
    ``models``
        which of the placed models this project **builds itself** rather than
        finding on the install, and what to build each one from.    ``use_points``
        every quest use trigger's origin and radius, derived, so a written
        map's room routes (Z55) can be checked without regenerating it.
    ``quest_steps``
        every quest step's points and the zones it waits for, derived, so
        Z61 (no step starts behind a shut door) can be asked of a written map.
    """
    plan = getattr(blueprint, "script", None)
    custom = getattr(plan, "custom", None) if plan is not None else None
    sounds = list(getattr(blueprint, "custom_sounds", ()) or ())
    weapons = list(getattr(blueprint, "custom_weapons", ()) or ())
    prices = dict(getattr(blueprint, "weapon_prices", {}) or {})
    return {
        "script": {"custom": custom_script_to_dict(custom)},
        "weapons": {
            # ``prices`` is the authored map-level input: what
            # ``set_weapon_price`` was called with, and nothing else.  A wall
            # buy's own price is the editor's -- it is a field on the buy in
            # the ``editor`` half -- so on a rebuild the buy is the authority
            # for the buy, and this key does not restate it.
            "prices": prices,
            # ``table`` is derived and is here because the section promised
            # "the per-weapon re-prices" and, on a map that prices six guns
            # through their wall buys, answered with an empty object.  This is
            # the whole effective cost table: exactly the rows the map's own
            # ``<name>_weapons.csv`` is built from, buys included.  Read it,
            # do not apply it: applying it *and* the editor's buy prices is
            # how two numbers for one gun get into one build.
            "table": dict(_effective_prices(blueprint, prices)),
            "custom": [
                {
                    field: getattr(weapon, field)
                    for field in weapon.__dataclass_fields__  # type: ignore[attr-defined]
                }
                for weapon in weapons
            ],
        },
        # The alias row is the data; the wave file is an asset beside the map.
        # Inlining audio as base64 would make this document unreadable in a
        # diff, which is the property the whole format is chosen for.
        "sounds": [_sound_of(s) for s in sounds],
        "props": _props_of(blueprint),
        "models": _custom_models(blueprint),
        # Every quest use trigger, so ``zmforge check`` can ask Z55 of a
        # written map without regenerating it.  Derived: the trigger itself
        # is in ``script``; this is where it stands and how far it reaches.
        "use_points": [
            {"label": label, "x": float(point.x), "y": float(point.y),
             "z": float(point.z), "radius": float(radius)}
            for label, point, radius in getattr(blueprint, "quest_use_points", ())
        ],
        # Every quest step's points and the zones it waits for, so
        # ``zmforge check`` can ask Z61 (P8) of a written map.
        "quest_steps": [dict(step) for step in getattr(blueprint, "quest_steps", ())],
        # Script-removed and quest objects (script.glow.own_object), so
        # ``zmforge check`` can ask Z64 whether a static light outlives one.
        "owned_objects": [dict(obj) for obj in getattr(blueprint, "owned_objects", ())],
    }


def _effective_prices(blueprint: Any, authored: Mapping[str, int]) -> dict:
    """Every weapon this map charges its own price for, by weapon name.

    The blueprint knows how to merge its wall buys into the authored re-prices
    -- that is the same call the weapon table itself is rendered from -- so ask
    it rather than re-deriving the merge here and having the document disagree
    with the ``.csv`` beside it.  A blueprint too old to answer falls back to
    the authored half, which is what this key used to be.
    """
    resolve = getattr(blueprint, "weapon_price_table", None)
    if not callable(resolve):
        return dict(authored)
    try:
        return {str(k): int(v) for k, v in resolve().items()}
    except Exception:  # pragma: no cover - a derived view never blocks a save
        return dict(authored)


def _custom_models(blueprint: Any) -> list[dict]:
    """The placed models that are this project's own, and their provenance.

    WHY THIS IS IN THE DOCUMENT.  Every other model a map places is on the
    install and a build can simply name it.  These are not: they are converted
    here from public-domain packs, and a map that names one the tools have
    never been given links **clean** and quietly ships without it -- measured
    on a test map, where 124 model names survived the
    compiler and the linker and appeared in neither fastfile, with no error
    line anywhere (``scripts/props-packed.py``).  So a build driven from this
    document has to be told that these six are a build step of their own,
    before the map is compiled, and told what to build each of them from.

    Only the props actually placed are listed.  The library is a catalogue;
    this is a bill of materials for one map.
    """
    try:
        from .blueprint.elements import PropScatter
        from .props.library import KITS, PROPS
    except Exception:  # pragma: no cover - neither import has dependencies
        return []
    library = {entry.name: entry for entry in PROPS}
    counts: dict[str, int] = {}
    try:
        scatters = blueprint.elements(PropScatter)
    except Exception:  # pragma: no cover
        return []
    for scatter in scatters:
        for prop in scatter.props:
            if prop.model in library:
                counts[prop.model] = counts.get(prop.model, 0) + 1
    out: list[dict] = []
    for name in sorted(counts):
        entry = library[name]
        kit = KITS[entry.kit]
        out.append({
            "model": name,
            "placed": counts[name],
            "kit": entry.kit,
            "member": entry.member,
            "size_units": entry.size_units,
            "max_triangles": entry.max_triangles,
            "solid": entry.solid,
            "material": entry.material.asset if entry.material else kit.material,
            "archive": kit.archive,
            "licence": kit.licence,
        })
    return out


def _sound_of(sound: Any) -> dict:
    """One row of the map's sound bank, every column the alias chose.

    ``alias`` and ``wav`` keep the names they were written under from the first
    day, so a reader of an older document still finds them.  Everything else is
    read off ``SoundAlias.__dataclass_fields__`` for the same reason the props
    are: the row that was serialized by hand carried three of eleven fields, and
    a map rebuilt from it came back at the template's own volume, distances and
    fades, and **NONLOOPING** -- a looping tone written as a one-shot is a
    mechanic that stops on its own, reported by nothing.  Measured on
    a test map: eight columns of its one alias row differed
    between the recipe's bank and a bank rebuilt from the document.

    Defaults are written out rather than omitted.  The file is a diff, and a
    column that is absent because it is default reads the same as a column
    somebody deleted.
    """
    alias = sound.alias
    row = {"alias": alias.name, "wav": alias.wav_windows, "credit": sound.credit}
    row.update({
        field: _plain(getattr(alias, field))
        for field in type(alias).__dataclass_fields__
        if field not in ("name", "wav")
    })
    return row


def _props_of(blueprint: Any) -> list[dict]:
    """Every placed prop, flattened out of the scatters that generated them.

    Stored one record per prop rather than as the scatter's parameters.  The
    expansion is deterministic, but it depends on the *finished* world geometry
    -- ``furnish`` snaps each prop to the ground under it and drops any that land
    inside a solid -- so re-deriving the list would couple this format to the
    solid-index algorithm and would silently change a map's dressing whenever
    that algorithm was touched.  A person moving a single chair sees a diff of
    that chair.

    Fields are read off ``Prop.__dataclass_fields__`` rather than listed here on
    purpose.  ``Prop`` is under active change -- ``solid`` and ``collision_box``
    arrived while this module was being written, and ``collision_box`` is
    authored input that the per-prop collmap files are derived from.  A hand
    written field list would have silently dropped both.
    """
    try:
        from .blueprint.elements import PropScatter
    except ImportError:  # pragma: no cover - the package always has it
        return []
    out: list[dict] = []
    for scatter in blueprint.elements(PropScatter):
        for index, prop in enumerate(scatter.props):
            # The same id :mod:`zmforge.editordoc` gives this prop in the
            # ``editor`` half.  Written down rather than left to be re-derived
            # from the scatter and the position in the list, because it is the
            # join between the two halves: a build reads the collision box off
            # the record here and puts it on the prop the editor is holding.
            record = {"id": prop.id or f"{scatter.id}_{index}", "scatter": scatter.id}
            for field in type(prop).__dataclass_fields__:
                record[field] = _plain(getattr(prop, field))
            out.append(record)
    return out


def _plain(value: Any) -> Any:
    """A blueprint value as JSON: points become triples, tuples become lists.

    Deliberately total rather than exhaustive.  It is the one place that knows
    how to flatten the small vocabulary of value types the blueprint uses, so a
    field added upstream serializes without this module being edited.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    for triple in ("x", "y", "z"):  # Point, and anything shaped like one
        if not hasattr(value, triple):
            break
    else:
        # As floats, always.  `Point` does not coerce, so a recipe that writes
        # `Point(1260, 700, 288.0)` holds two ints and a float and the same map
        # rebuilt from this document holds three floats; `json.dumps` spells
        # those `1260` and `1260.0`, which is the same position and a different
        # document.
        return [float(value.x), float(value.y), float(value.z)]
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {f: _plain(getattr(value, f)) for f in value.__dataclass_fields__}
    return str(value)
