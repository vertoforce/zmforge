"""Carrying editor edits through a regenerate: a three-way merge by element id.

The problem this solves
-----------------------
A map is one document (:mod:`zmforge.mapdoc`) written by two programs.  The
recipe *generates* it; a map editor *edits* it.  Without a merge, re-running
the recipe over a document an editor had touched has to refuse outright, and
the only way past the refusal is ``--discard-edits`` -- so every regenerate
for a play build throws the editing work away.  That makes the format
dual-use in name only: the moment a prop is moved in an editor, the
recipe and the editor are two tools fighting over one file.

What a merge needs, and why a two-way diff is not enough
--------------------------------------------------------
"The document on disk differs from the one the recipe just produced" says
nothing about *who* changed what.  Every difference has two possible authors and
a two-way compare cannot tell them apart, which is why the answer has to be a
**three-way** merge against a common ancestor:

``base``
    the document the last generate wrote, kept beside the map as
    ``<name>.blueprint.base.json`` (:data:`BASE_SUFFIX`).  Without a stored
    ancestor there is no merge to do, only a guess.
``current``
    the document on disk now: the base plus whatever an editor saved.
``new``
    the document this regenerate produced from the recipe.

Per element, by id, the resolution is then a fact rather than a preference:

===========================  ==========================  ======================
current vs base              new vs base                 result
===========================  ==========================  ======================
same (user did not touch)    changed                     the regenerated element
changed (user edited)        same                        the user's element
changed                      changed                     **conflict**
===========================  ==========================  ======================

Conflict policy
---------------
**The user's version wins and the conflict is reported.**  Both halves of that
sentence carry weight.  Taking the generator's version would mean a regenerate
silently undoing hand work, which is the failure this module exists to remove;
taking the user's version silently would mean a map that no longer matches the
recipe with nothing anywhere to say so.  So every conflict -- and every other
outcome that is not "the regenerated version, unchanged" -- becomes a
:class:`MergeNote`, the :class:`MergeResult` carries them, and ``zmforge
generate`` prints them.  Nothing is resolved by averaging, by field-level
cleverness inside a conflicted element, or by picking the newer timestamp.

Two element-level cases are called out because they are the ones a naive merge
loses:

* **An element the user added** exists in ``current`` and in neither ``base``
  nor ``new``.  "Absent" is the same in base and new, so the generator did not
  change it and the user did: it is kept.  It survives every regenerate until
  the user removes it.
* **An element the generator dropped** that the user had also edited is a
  conflict, so the user's version is kept and reported.  A regenerate that
  quietly deleted somebody's edited prop because the recipe no longer emits
  that scene is exactly the silent loss being designed out.

What is merged and what is not
------------------------------
Only the two halves that describe the map: ``editor`` (what a map editor draws)
and ``engine`` (scripts, weapons, sounds, props, models).  Everything else in
the document -- ``format``, ``name``, ``revision``, ``origin``, ``geometry``,
``hashes`` and the pre-``zmforge-map/2`` keys -- is generator-owned bookkeeping
about *this* write and is taken from the new document whole.  Merging a hash
table or a revision id would produce a document describing a write that never
happened.

Inside those two halves the merge is structural and needs no schema: a list of
dicts that all carry a unique ``id`` is merged element by element; any other
dict is merged key by key; anything else is compared whole.  That is deliberate
-- the editor's document grows fields, and a hand-written field list would merge
last month's document.

Measured on a test map's own document (1.58 MB): 36 of the 39 lists of records in the two halves merge by id,
including both 1,916-record prop lists, and one edit merges in 0.07 s.  The
three that do not are ``engine.models`` and the two halves of the generated
GSC, whose records carry no id at all; they are generator-owned and are compared
whole, which for them is the right answer rather than a fallback.

A caveat this module does not hide
----------------------------------
The merge carries edits forward **in the document**.  The ``.map`` beside it is
still rendered from the recipe's blueprint, so a prop added in an editor is in the
merged document and not in that ``.map`` until the map is built from the
document (which is what an editor's build does).  Reversing that -- turning
a merged document back into a blueprint -- is the editor's own translator, and
is not part of this package.  :meth:`MergeResult.summary` says so
when geometry-bearing elements were kept.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "BASE_SUFFIX",
    "MERGED_SECTIONS",
    "MergeNote",
    "MergeResult",
    "merge_document",
]

#: The sidecar holding the last generated document -- the merge's common
#: ancestor.  Beside the map, named for it, so a map is still one directory's
#: worth of files and the ancestor cannot be separated from the document it is
#: the ancestor of.
BASE_SUFFIX = ".blueprint.base.json"

#: The document sections a merge touches.  Everything else is bookkeeping about
#: the write itself and comes from the new document whole; see the module
#: docstring.
MERGED_SECTIONS = ("editor", "engine")


class _Missing:
    """A key or element that is not in a document at all.

    A distinct sentinel rather than ``None``, because ``None`` is a legal value
    in these documents and "the field is absent" and "the field is null" resolve
    differently: absent-in-base and absent-in-new means the generator never had
    it, which is what makes a user-added element survive.
    """

    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


MISSING = _Missing()


#: What a note says happened.  ``conflict`` is the only one that means the
#: recipe and the editor disagreed; the rest are the merge doing its job and
#: are reported so that a regenerate is never silently different from the
#: recipe.
NOTE_KINDS = (
    "kept_user",  # the user changed it, the generator did not: user's version
    "user_added",  # only the user has it: kept
    "user_removed",  # the user deleted something the generator still emits
    "conflict",  # both changed: the user's version is kept
    "conflict_generator_removed",  # generator dropped it, the user had edited it
)


@dataclass(frozen=True)
class MergeNote:
    """One decision the merge made that was not "take the regenerated version"."""

    path: str
    kind: str
    detail: str = ""

    def __str__(self) -> str:
        wording = {
            "kept_user": "kept your version (the recipe did not change it)",
            "user_added": "kept, added in the editor and not generated",
            "user_removed": "left removed, deleted in the editor",
            "conflict": "CONFLICT: both changed; kept your version",
            "conflict_generator_removed": (
                "CONFLICT: the recipe no longer generates it and you had edited "
                "it; kept your version"
            ),
        }.get(self.kind, self.kind)
        return f"{self.path}: {wording}{(' -- ' + self.detail) if self.detail else ''}"


@dataclass
class MergeResult:
    """The merged document and every decision that went into it."""

    document: dict
    notes: list[MergeNote] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Whether the merge carried anything at all."""
        return bool(self.notes)

    @property
    def conflicts(self) -> list[MergeNote]:
        return [n for n in self.notes if n.kind.startswith("conflict")]

    @property
    def carried(self) -> list[MergeNote]:
        return [n for n in self.notes if not n.kind.startswith("conflict")]

    def summary(self, *, limit: int = 40) -> list[str]:
        """The report a caller prints: a header, then one line per decision.

        Empty when the merge was a no-op, so a caller can print it
        unconditionally and say nothing when there was nothing to say.

        **Every conflict is listed, whatever ``limit`` says**, and the carried
        edits are cut off after it: somebody who spent an afternoon in the
        editor can easily have moved two hundred props, and a build log that
        scrolls the conflicts off the top is a report that hid the only part
        of itself worth reading.
        """
        if not self.notes:
            return []
        lines = [
            f"carried {len(self.carried)} editor edit(s) through the "
            f"regenerate, {len(self.conflicts)} conflict(s):"
        ]
        shown, hidden = [], 0
        for note in self.notes:
            if note.kind.startswith("conflict") or len(shown) < limit:
                shown.append(note)
            else:
                hidden += 1
        lines.extend(f"  {note}" for note in shown)
        if hidden:
            lines.append(f"  ... and {hidden} more kept without conflict")
        if any(note.path.startswith("editor.") for note in self.notes):
            lines.append(
                "  note: kept geometry is in the document, not in the .map this "
                "generate wrote; build from the editor to put it in the map."
            )
        return lines


def merge_document(
    base: Mapping[str, Any],
    current: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    sections: Sequence[str] = MERGED_SECTIONS,
) -> MergeResult:
    """Three-way merge ``current`` (base + editor edits) onto ``new``.

    Returns the new document with the editor's work merged into ``sections``
    and every other key untouched.  Nothing is read or written; the caller owns
    the files and the lock.
    """
    merged = json.loads(json.dumps(dict(new)))
    notes: list[MergeNote] = []
    for section in sections:
        resolved = _merge(
            section,
            _get(base, section),
            _get(current, section),
            _get(new, section),
            notes,
        )
        if resolved is MISSING:
            merged.pop(section, None)
        else:
            merged[section] = resolved
    return MergeResult(document=merged, notes=notes)


# ----------------------------------------------------------------------
# The merge itself
# ----------------------------------------------------------------------
def _merge(
    path: str,
    base: Any,
    current: Any,
    new: Any,
    notes: list[MergeNote],
) -> Any:
    """Resolve one value, recursing where the shape says a finer answer exists.

    The two cheap answers come first and cover almost every node in a real
    document -- the sides agree, or the user did not touch this one -- and
    neither needs the shape of the value or a line in the report.  Everything
    below them is a node the user changed, which is the only kind worth
    descending into and the only kind worth reporting.
    """
    if _same(current, new):
        return current
    if _same(current, base):
        # The user never touched it: the regenerate is the authority, whole,
        # and there is nothing to report.  This is the branch that keeps a map
        # nobody opened in an editor identical to a plain regenerate.
        return new

    # The user changed something in here.  If the node has an inside, descend:
    # a finer answer beats a conflict when the two sides changed different
    # parts of it, and -- just as much the point -- the *report* is then about
    # the field somebody edited rather than about the section it is in.  A
    # note reading ``editor`` tells nobody anything.
    if _is_id_list(base) and _is_id_list(current) and _is_id_list(new):
        return _merge_elements(path, base, current, new, notes)
    if _is_mapping(base) and _is_mapping(current) and _is_mapping(new):
        return _merge_mapping(path, base, current, new, notes)

    # A leaf, or a node one of the three sides does not have at all -- an
    # element added on one side and absent on another has no inside to compare.
    if _same(new, base):
        return _kept(path, base, current, new, notes)

    notes.append(
        MergeNote(
            path,
            "conflict_generator_removed" if new is MISSING else "conflict",
            _describe(current, new),
        )
    )
    return current


def _kept(path: str, base: Any, current: Any, new: Any, notes: list[MergeNote]) -> Any:
    """The generator left this node alone, so the user's version stands."""
    if base is MISSING:
        notes.append(MergeNote(path, "user_added"))
    elif current is MISSING:
        notes.append(MergeNote(path, "user_removed"))
    else:
        notes.append(MergeNote(path, "kept_user", _describe(current, base)))
    return current


def _merge_mapping(
    path: str,
    base: Any,
    current: Any,
    new: Any,
    notes: list[MergeNote],
) -> dict:
    out: dict = {}
    for key in _ordered_keys(new, current):
        resolved = _merge(
            f"{path}.{key}",
            _get(base, key),
            _get(current, key),
            _get(new, key),
            notes,
        )
        if resolved is not MISSING:
            out[key] = resolved
    return out


def _merge_elements(
    path: str,
    base: Any,
    current: Any,
    new: Any,
    notes: list[MergeNote],
) -> list:
    """Merge three lists of id-carrying records, element by element.

    The order is the generator's, with anything the user added and the
    generator does not know about kept in your own order behind it: a
    regenerate that reordered the recipe's own output would show up as noise in
    every later diff, and a user-added element has no place in an order the
    generator never saw it in.
    """
    by_base = _by_id(base)
    by_current = _by_id(current)
    by_new = _by_id(new)

    order = [_element_id(e) for e in new]
    order += [
        _element_id(e) for e in current if _element_id(e) not in by_new
    ]

    out: list = []
    for element_id in order:
        resolved = _merge(
            f"{path}[{element_id}]",
            by_base.get(element_id, MISSING),
            by_current.get(element_id, MISSING),
            by_new.get(element_id, MISSING),
            notes,
        )
        if resolved is not MISSING:
            out.append(resolved)
    # Every id in `current` is in `order` by construction, and an id only the
    # base had is one both sides removed, so there is nothing left to sweep up.
    return out


# ----------------------------------------------------------------------
# Shapes
# ----------------------------------------------------------------------
def _same(left: Any, right: Any) -> bool:
    """Value equality that treats the sentinel as its own value."""
    if left is MISSING or right is MISSING:
        return left is right
    return left == right


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _element_id(element: Any) -> str:
    return str(element.get("id"))


def _is_id_list(value: Any) -> bool:
    """A list of records each carrying a unique, non-empty ``id``.

    Anything else -- a list of strings such as ``editor.element_order``, a list
    of records where one is missing an id, a list with a duplicate id -- is not
    something that can be merged by identity, and is compared whole instead.
    Guessing at identity is how a merge moves somebody's prop onto another
    one.
    """
    if not isinstance(value, list):
        return False
    seen: set[str] = set()
    for element in value:
        if not isinstance(element, Mapping):
            return False
        identity = element.get("id")
        if not isinstance(identity, (str, int)) or str(identity) == "":
            return False
        if str(identity) in seen:
            return False
        seen.add(str(identity))
    return True


def _by_id(elements: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {_element_id(element): element for element in elements}


def _get(container: Any, key: str) -> Any:
    if not isinstance(container, Mapping):
        return MISSING
    return container.get(key, MISSING)


def _ordered_keys(new: Any, current: Any) -> list[str]:
    """New document's keys first, then keys only the user's document has."""
    keys = list(new.keys()) if isinstance(new, Mapping) else []
    if isinstance(current, Mapping):
        keys += [key for key in current if key not in keys]
    return keys


def _describe(current: Any, other: Any) -> str:
    """A short, safe "yours vs theirs" for a report line.

    Truncated hard: a merge note is read in a terminal beside a build log, and a
    prop record printed in full is a screen of JSON for a change of one number.
    """
    return f"yours {_brief(current)} / recipe {_brief(other)}"


def _brief(value: Any, limit: int = 60) -> str:
    if value is MISSING:
        return "<absent>"
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."
