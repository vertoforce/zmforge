"""What we have learned about individual stock and kit props, so future maps use them right by default.

Built from render passes and reviews of maps already built, so the next map
does not have to rediscover that a monitor draws black in the preview or that
a stock sink needs legs added by hand.  ``zmforge check`` reads it: ``Z58`` warns on models
measured to render dark, blank or not at all in the editor, and ``Z59`` on a
curtain with no rail or a desk monitor with nothing under it; ``Z60``
(:mod:`zmforge.verify.prop_rules`) on a prop that breaks its ``rules`` block
(:func:`rules_for`): its measured front, what it faces, what it needs under
or near it, where it mounts.

Whether a model links with the mod tools (``local_tools``) is not stored
here: it is derived from ``blueprint/installed_assets.json``, the ledger the
``Z13`` check judges every ``misc_model`` by, so the two cannot disagree.

The data lives in ``notes.json`` next to this file, keyed by model name, with
category-level entries (``"categories"``) for rules that apply to a whole
family (every curtain, every duct segment) and free-standing notes about
materials (``"materials"``) and known asset gaps (``"gaps"``) that are not
about one model at all.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "NOTES_PATH",
    "PropNote",
    "prop_notes",
    "model_note",
    "category_note",
    "material_note",
    "gaps",
    "local_tools",
    "categories_for",
    "needs_of",
    "rules_for",
    "massing_rules",
    "front_of",
    "RULE_KEYS",
]

NOTES_PATH = Path(__file__).with_name("notes.json")


@dataclass(frozen=True, slots=True)
class PropNote:
    """One thing learned about a model, a model family, or a material.

    Every field but the source is optional: a note only fills in what was
    actually observed.  ``confidence`` is ``"measured"`` (code, geometry, a
    linker log, or a swap that was checked to fix the render) or
    ``"review_only"`` (an AI render review's finding, not independently
    checked).
    """

    key: str
    kind: str  # "model" | "category" | "material" | "gap"
    renders: str | None = None
    reads_as: str | None = None
    needs: tuple[str, ...] = ()
    placement: str | None = None
    origin_offset: str | None = None
    local_tools: str | None = None
    use_instead: str | None = None
    match: str | None = None  # categories only: which models this covers, in words
    pattern: str | list[str] | None = None  # categories only: an fnmatch glob (or a list) over model names
    solid: bool | None = None
    size: tuple[float, ...] = ()
    confidence: str = "review_only"
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _note(key: str, kind: str, entry: dict[str, Any]) -> PropNote:
    return PropNote(
        key=key,
        kind=kind,
        renders=entry.get("renders"),
        reads_as=entry.get("reads_as") or entry.get("issue"),
        needs=tuple(entry.get("needs", ())),
        placement=entry.get("placement"),
        origin_offset=entry.get("origin_offset"),
        local_tools=local_tools(key) if kind == "model" else None,
        use_instead=entry.get("use_instead"),
        match=entry.get("match"),
        pattern=entry.get("pattern"),
        solid=entry.get("solid"),
        size=tuple(entry.get("size", ())),
        confidence=entry.get("confidence", "review_only"),
        source=entry.get("source", ""),
        raw=entry,
    )


@lru_cache(maxsize=1)
def prop_notes() -> dict[str, dict[str, PropNote]]:
    """The whole notes file, parsed once: ``{"models": {...}, "categories": {...}, ...}``.

    ``"gaps"`` entries have no natural key in the source JSON (it is a list),
    so they are keyed by their ``want`` text.
    """
    data = json.loads(NOTES_PATH.read_text())
    out: dict[str, dict[str, PropNote]] = {"models": {}, "categories": {}, "materials": {}, "gaps": {}}
    for key, entry in data.get("models", {}).items():
        out["models"][key] = _note(key, "model", entry)
    for key, entry in data.get("categories", {}).items():
        out["categories"][key] = _note(key, "category", entry)
    for key, entry in data.get("materials", {}).items():
        out["materials"][key] = _note(key, "material", entry)
    for entry in data.get("gaps", []):
        key = entry.get("want", "?")
        out["gaps"][key] = _note(key, "gap", entry)
    return out


def model_note(name: str) -> PropNote | None:
    """What is known about model *name*, or ``None``."""
    return prop_notes()["models"].get(name)


def category_note(key: str) -> PropNote | None:
    """A family-level note (e.g. ``"curtain"``, ``"duct_kit"``), or ``None``."""
    return prop_notes()["categories"].get(key)


def material_note(name: str) -> PropNote | None:
    """What is known about material *name*, or ``None``."""
    return prop_notes()["materials"].get(name)


def gaps() -> tuple[PropNote, ...]:
    """Known catalogue gaps: something a map wants that no model provides."""
    return tuple(prop_notes()["gaps"].values())


def local_tools(name: str) -> str | None:
    """``"present"`` or ``"missing"``: whether *name* links with the mod
    tools, by the same ledger and verdict ``Z13`` uses
    (:func:`zmforge.blueprint.installed.judge_misc_model`); ``None`` when
    there is no ledger or the ledger has never seen the name."""
    from ..blueprint.installed import judge_misc_model

    ledger = _ledger()
    if ledger is None:
        return None
    verdict = judge_misc_model(name, ledger)
    return {"ok": "present", "missing": "missing", "unlinkable": "missing"}.get(verdict)


@lru_cache(maxsize=1)
def _ledger():
    from ..blueprint.installed import load_ledger

    return load_ledger()


def _patterns(note: PropNote) -> tuple[str, ...]:
    """A category's ``pattern``: one fnmatch glob, or a list of them."""
    pattern = note.raw.get("pattern")
    if not pattern:
        return ()
    return (pattern,) if isinstance(pattern, str) else tuple(pattern)


def categories_for(model: str) -> tuple[PropNote, ...]:
    """Every category note whose ``pattern`` (a glob or a list of globs)
    matches *model*.  Categories that apply to brushes
    (``"applies_to": "massing"``) are not model categories and never match."""
    return tuple(n for n in prop_notes()["categories"].values()
                 if n.raw.get("applies_to", "model") == "model"
                 and any(fnmatch.fnmatchcase(model, p) for p in _patterns(n)))


#: The rule types a ``"rules"`` block may carry, read by
#: ``Z60`` (:mod:`zmforge.verify.prop_rules`).
RULE_KEYS = (
    "front", "front_how", "faces", "faced_by", "clearance_front", "mount",
    "needs_near", "connects", "max_per_room", "not_in", "assembly",
)


def rules_for(model: str) -> dict[str, Any]:
    """The rules *model* is held to: every matching category's ``rules`` in
    file order, then the model's own on top.  A model key set to ``null``
    drops the category's rule for that model (a double-sided exit sign is a
    sign that need not face away from a wall)."""
    out: dict[str, Any] = {}
    note = model_note(model)
    for source in categories_for(model) + ((note,) if note else ()):
        out.update(source.raw.get("rules", {}))
    return {k: v for k, v in out.items() if v is not None}


def massing_rules() -> tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...]:
    """``(category key, patterns, rules)`` for every category over brush
    ids (``"applies_to": "massing"``), such as the scarecrow's parts."""
    return tuple((n.key, _patterns(n), n.raw.get("rules", {}))
                 for n in prop_notes()["categories"].values()
                 if n.raw.get("applies_to") == "massing")


#: A ``front`` axis as the local yaw it points along, in degrees.
_AXIS_YAW = {"+x": 0.0, "+y": 90.0, "-x": 180.0, "-y": -90.0}


def front_of(model: str) -> float | None:
    """Which way *model* faces in its own frame, in degrees (``+x`` is 0),
    from its measured ``front`` rule; ``None`` when unknown or unmeasured."""
    return _AXIS_YAW.get(rules_for(model).get("front", "unknown"))


def needs_of(model: str) -> tuple[str, ...]:
    """What *model* needs to read right: its own note's ``needs`` and every
    matching category's, in order, without repeats."""
    out: list[str] = []
    note = model_note(model)
    for source in ((note,) if note else ()) + categories_for(model):
        for need in source.needs:
            if need not in out:
                out.append(need)
    return tuple(out)
