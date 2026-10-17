"""The response schema of the design review: the one place it is defined.

Whoever grades a review packet (a person, any AI agent, or a script such as
``scripts/review-with-claude.py``) writes one findings file per call, and
``zmforge review --import`` checks each file against the schema below with
:func:`validate` before it grades anything.  Every packet also carries the
exact schema of each call as ``<call>.schema.json``, so a reviewer never has
to read this module.

Room call (``room-<room>.findings.json``), :func:`room_schema`:

- ``room``, ``grade`` (A-F), ``score`` (0-10), ``summary``;
- ``principles``: one ``{id, verdict, evidence, suggested_fix}`` per
  principle, verdict ``pass``/``warn``/``fail``/``n/a``;
- ``fixes``: ``{target, change, priority}``;
- ``doesnt_make_sense``: ``{finding, severity, where, suggested_fix}``;
- with renders in the packet, also ``visual_findings``:
  ``{what, where, view, severity}``;
- when the room is anchored on its previous review, also
  ``previous_findings`` (``{n, status, note}``, status ``still_present``/
  ``fixed``/``cannot_tell``) and ``verdict_changes``
  (``{id, previous, now, reason}``).

Map call (``map.findings.json``), :data:`MAP_SCHEMA`: the room fields minus
``room``, verdicts without ``n/a``.

Extra keys are allowed and ignored.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

VERDICTS = ("pass", "warn", "fail")
ROOM_VERDICTS = VERDICTS + ("n/a",)
SEVERITIES = ("high", "medium", "low")
GRADES = ("A", "B", "C", "D", "F")
#: The principle the rendered views are for ("check how it actually looks").
VISUAL_PRINCIPLE = "P15"
#: What an anchored room call says about each finding of the previous review.
PREVIOUS_STATUS = ("still_present", "fixed", "cannot_tell")


def _verdict_items(verdicts: Sequence[str]) -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "verdict": {"type": "string", "enum": list(verdicts)},
                "evidence": {"type": "string"},
                "suggested_fix": {"type": "string"},
            },
            "required": ["id", "verdict", "evidence", "suggested_fix"],
        },
    }


_FINDINGS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "finding": {"type": "string"},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "where": {"type": "string"},
            "suggested_fix": {"type": "string"},
        },
        "required": ["finding", "severity", "where", "suggested_fix"],
    },
}

_FIXES = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "prop id, element id or file:line"},
            "change": {"type": "string"},
            "priority": {"type": "string", "enum": list(SEVERITIES)},
        },
        "required": ["target", "change", "priority"],
    },
}

ROOM_SCHEMA = {
    "type": "object",
    "properties": {
        "room": {"type": "string"},
        "grade": {"type": "string", "enum": list(GRADES)},
        "score": {"type": "number", "minimum": 0, "maximum": 10},
        "summary": {"type": "string"},
        "principles": _verdict_items(ROOM_VERDICTS),
        "fixes": _FIXES,
        "doesnt_make_sense": _FINDINGS,
    },
    "required": ["room", "grade", "score", "summary", "principles", "fixes",
                 "doesnt_make_sense"],
}

_VISUAL_FINDINGS = {
    "type": "array",
    "description": "one entry per thing that looks wrong in the attached renders",
    "items": {
        "type": "object",
        "properties": {
            "what": {"type": "string", "description": "what looks wrong and why"},
            "where": {"type": "string", "description": "where in the room; prop ids if known"},
            "view": {"type": "string",
                     "description": "file name of the image it shows in, e.g. queue--corner-sw.png"},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
        },
        "required": ["what", "where", "view"],
    },
}

_PREVIOUS_FINDINGS = {
    "type": "array",
    "description": "one entry per finding of the previous review, in its order",
    "items": {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "the finding's number in PREVIOUS REVIEW"},
            "status": {"type": "string", "enum": list(PREVIOUS_STATUS)},
            "note": {"type": "string", "description": "what in the facts or pictures shows it"},
        },
        "required": ["n", "status", "note"],
    },
}

_VERDICT_CHANGES = {
    "type": "array",
    "description": "every principle whose verdict differs from the previous review",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "previous": {"type": "string"},
            "now": {"type": "string"},
            "reason": {"type": "string",
                       "description": "what changed in the room, or the new concrete defect"},
        },
        "required": ["id", "previous", "now", "reason"],
    },
}

MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "grade": {"type": "string", "enum": list(GRADES)},
        "score": {"type": "number", "minimum": 0, "maximum": 10},
        "summary": {"type": "string"},
        "principles": _verdict_items(VERDICTS),
        "fixes": _FIXES,
        "doesnt_make_sense": _FINDINGS,
    },
    "required": ["grade", "score", "summary", "principles", "fixes", "doesnt_make_sense"],
}


def room_schema(visual: bool = False) -> dict:
    """The room call's schema; with renders attached it also asks for visual_findings."""
    if not visual:
        return ROOM_SCHEMA
    return {**ROOM_SCHEMA,
            "properties": {**ROOM_SCHEMA["properties"], "visual_findings": _VISUAL_FINDINGS},
            "required": ROOM_SCHEMA["required"] + ["visual_findings"]}


def anchored_schema(schema: Mapping) -> dict:
    """A room schema that also asks about the previous review's findings and verdicts."""
    return {**schema,
            "properties": {**schema["properties"], "previous_findings": _PREVIOUS_FINDINGS,
                           "verdict_changes": _VERDICT_CHANGES},
            "required": list(schema["required"]) + ["previous_findings", "verdict_changes"]}


# ----------------------------------------------------------------------
# Validation (the subset of JSON Schema used above; no dependency)
# ----------------------------------------------------------------------
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def validate(value: Any, schema: Mapping, path: str = "$") -> list[str]:
    """Every way *value* breaks *schema*, as ``"<json path>: <problem>"`` lines.

    Handles ``type``, ``enum``, ``required``, ``properties``, ``items``,
    ``minimum`` and ``maximum``: all the schemas in this module use.  An
    empty list means the value is valid.
    """
    problems: list[str] = []
    kind = schema.get("type")
    if kind and not _TYPES[kind](value):
        return [f"{path}: expected {kind}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if kind == "number" or kind == "integer":
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: {value} is above {schema['maximum']}")
    if kind == "object":
        for key in schema.get("required", ()):
            if key not in value:
                problems.append(f"{path}: missing required key {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                problems += validate(value[key], sub, f"{path}.{key}")
    if kind == "array" and "items" in schema:
        for i, item in enumerate(value):
            problems += validate(item, schema["items"], f"{path}[{i}]")
    return problems
