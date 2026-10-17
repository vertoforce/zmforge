"""Review packets: what a reviewer needs on disk, and grading what they write back.

``zmforge review <recipe>`` measures the map and writes a packet folder,
``build-out/review/<map>-<time>.packet/``:

- ``README.md``: the reviewer's role and the steps, for whoever opens it;
- ``packet.json``: the calls in order, the facts, the principles, the
  previous review each room is anchored on, and where the report goes;
- per call (``room-<room>`` for each room, then ``map``):
  ``<call>.prompt.md`` (the full prompt), ``<call>.schema.json`` (the JSON
  schema of the answer) and, for rooms, the render PNGs listed in
  ``packet.json`` and at the end of the prompt.

The reviewer (a person, any AI agent, or a runner script) writes
``<call>.findings.json`` next to each prompt; ``zmforge review --import
<packet>`` validates each against its schema, applies the anchoring rules and
writes ``<map>-<time>.json`` and ``.md`` into the review folder, where the
next packet of this map finds it as its anchor.  Nothing here calls a model.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import ai
from .schema import MAP_SCHEMA, anchored_schema, room_schema, validate

FORMAT = "zmforge-review-packet/1"


def call_id(room: str) -> str:
    """``room-<room>`` with anything outside ``[A-Za-z0-9_.-]`` made ``_``."""
    return "room-" + re.sub(r"[^A-Za-z0-9_.-]", "_", room)


def _readme(packet: Mapping) -> str:
    rooms = [c for c in packet["calls"] if c["kind"] == "room"]
    return f"""# Review packet: {packet['map']}

{ai.REVIEWER_ROLE}

## What to do

1. For each room call below, read `<call>.prompt.md`, look at every image it
   lists, and write `<call>.findings.json`: one JSON object that matches
   `<call>.schema.json`.
2. Then read `map.prompt.md`, weigh your room findings as it asks, and write
   `map.findings.json` against `map.schema.json`.
3. Run `zmforge review --import {packet['dir']}`. It checks every file against
   its schema, lists what is wrong if anything is, and otherwise writes the
   report to `{packet['out']}/{packet['stem']}.md`.

The full workflow is in `docs/workflows/review-a-map.md` of the zmforge repo.

## Calls

""" + "\n".join(
        f"- `{c['id']}`: {len(c['images'])} image(s)"
        + (", anchored on the previous review" if c.get("anchored") else "")
        for c in rooms) + "\n- `map`: after every room\n"


def build(facts: Mapping, *, principles: Sequence[Mapping], room_sources: Mapping[str, str],
          map_source: str, packet_dir: Path, out_dir: Path, stem: str,
          rooms: Sequence[str] | None = None,
          room_images: Mapping[str, Sequence[Path]] | None = None,
          previous: Mapping[str, Mapping] | None = None,
          extra: Mapping[str, Any] | None = None) -> dict:
    """Write the packet into *packet_dir* and return ``packet.json``'s content.

    *room_images* (room key -> PNG paths) are listed with their room's call,
    whose prompt and schema then ask for the P15 judgement from them.
    *previous* (room key -> :func:`ai.previous_room_reviews` anchor) goes into
    that room's prompt and schema.  *extra* is stored as-is (the scorecard
    table, the render status).
    """
    packet_dir = Path(packet_dir)
    packet_dir.mkdir(parents=True, exist_ok=True)
    wanted = [r for r in facts["rooms"] if rooms is None or r["room"] in rooms]
    calls: list[dict] = []

    def write(cid: str, prompt: str, schema: Mapping) -> None:
        (packet_dir / f"{cid}.prompt.md").write_text(prompt, encoding="utf-8")
        (packet_dir / f"{cid}.schema.json").write_text(json.dumps(schema, indent=1),
                                                       encoding="utf-8")

    for room in wanted:
        key = room["room"]
        images = [str(Path(p).resolve()) for p in (room_images or {}).get(key, ())]
        anchor = (previous or {}).get(key)
        prompt = ai.room_prompt(principles, room, room_sources.get(key, ""),
                                map_name=facts["map"], thresholds=facts["thresholds"],
                                images=[Path(p).name for p in images], previous=anchor)
        if images:
            prompt += "\nIMAGE FILES (open each one):\n" + "\n".join(f"- {p}" for p in images) + "\n"
        schema = room_schema(bool(images))
        if anchor:
            schema = anchored_schema(schema)
        cid = call_id(key)
        write(cid, prompt, schema)
        calls.append({"id": cid, "kind": "room", "room": key, "images": images,
                      "anchored": bool(anchor), "prompt": f"{cid}.prompt.md",
                      "schema": f"{cid}.schema.json", "findings": f"{cid}.findings.json"})
    write("map", ai.map_prompt(principles, facts, None, map_source), MAP_SCHEMA)
    calls.append({"id": "map", "kind": "map", "images": [], "anchored": False,
                  "after": [c["id"] for c in calls], "prompt": "map.prompt.md",
                  "schema": "map.schema.json", "findings": "map.findings.json"})
    packet = {
        "format": FORMAT, "map": facts["map"], "recipe": facts.get("recipe"),
        "stem": stem, "dir": str(packet_dir.resolve()), "out": str(Path(out_dir).resolve()),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"), "reviewer_role": ai.REVIEWER_ROLE,
        "calls": calls, "principles": list(principles), "previous": dict(previous or {}),
        "facts": facts, **dict(extra or {}),
    }
    (packet_dir / "packet.json").write_text(json.dumps(packet, indent=1, default=str),
                                            encoding="utf-8")
    (packet_dir / "README.md").write_text(_readme(packet), encoding="utf-8")
    return packet


def load(packet_dir: Path) -> dict:
    path = Path(packet_dir) / "packet.json"
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ai.ReviewError(f"not a review packet ({path}): {exc}") from exc
    if packet.get("format") != FORMAT:
        raise ai.ReviewError(f"{path}: unknown packet format {packet.get('format')!r}")
    return packet


def read_findings(packet_dir: Path, call: Mapping) -> tuple[dict | None, list[str]]:
    """``(findings, problems)`` for one call; findings None when unusable."""
    path = Path(packet_dir) / call["findings"]
    if not path.exists():
        error = Path(packet_dir) / f"{call['id']}.error.txt"   # a runner's failed call
        if error.exists():
            return None, [f"{call['id']}: {error.read_text(encoding='utf-8').strip()[:300]}"]
        return None, [f"{call['id']}: no findings file {call['findings']}"]
    try:
        raw = ai.extract_json(path.read_text(encoding="utf-8"))
    except ai.ReviewError as exc:
        return None, [f"{call['id']}: {exc}"]
    schema = json.loads((Path(packet_dir) / call["schema"]).read_text(encoding="utf-8"))
    problems = [f"{call['id']}: {p}" for p in validate(raw, schema)]
    return (None if problems else raw), problems


def grade(packet_dir: Path, *, partial: bool = False, reviewer: str | None = None,
          log=lambda s: None) -> tuple[dict | None, list[str]]:
    """``(result, problems)``: the graded review of a packet with its findings.

    Every findings file is checked against its call's schema.  Without
    *partial* any problem stops the import (result None) so the reviewer can
    fix the files and import again; with *partial* a room without usable
    findings is recorded as an error in the report (and fails ``--strict``),
    as is a missing map call.  An optional ``<call>.meta.json`` (cost, time,
    model, written by a runner) is kept in the report's ``calls``.
    """
    packet_dir = Path(packet_dir)
    packet = load(packet_dir)
    principles = packet["principles"]
    previous = packet.get("previous") or {}
    problems: list[str] = []
    answers: dict[str, dict | None] = {}
    for call in packet["calls"]:
        answers[call["id"]], found = read_findings(packet_dir, call)
        problems += found
    if problems and not partial:
        return None, problems
    errors = list(problems)
    calls: list[dict] = []
    room_reviews: list[dict] = []
    map_review: dict | None = None
    for call in packet["calls"]:
        raw = answers[call["id"]]
        if raw is not None:
            meta_path = packet_dir / f"{call['id']}.meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except ValueError:
                    meta = {}
            calls.append({"call": call["id"], **(meta if isinstance(meta, dict) else {})})
        if call["kind"] == "map":
            if raw is not None:
                map_review = ai.normalise(raw, principles, allow_na=False)
            continue
        room = call["room"]
        if raw is None:
            room_reviews.append({"room": room, "error": "no usable findings", "principles": []})
            continue
        review = ai.normalise(raw, principles, allow_na=True, visual=bool(call["images"]))
        anchor = previous.get(room)
        if anchor:
            ai.apply_anchor(review, raw, anchor)
        review["room"] = room
        review["images"] = [Path(p).name for p in call["images"]]
        room_reviews.append(review)
        log(f"room {room}: {review['grade']} ({review['score']})")
    result = {
        "facts": packet["facts"], "scorecard_table": packet.get("scorecard_table", ""),
        "generated_at": packet["stem"], "visual": packet.get("visual"),
        "map_review": map_review, "room_reviews": room_reviews, "errors": errors,
        "calls": calls, "anchored_on": sorted({a["from"] for a in previous.values()}),
        "principles": principles, "packet": str(packet_dir.resolve()),
        "reviewer": reviewer,
        "cost_usd": round(sum(c.get("total_cost_usd") or 0 for c in calls), 2),
    }
    return result, problems
