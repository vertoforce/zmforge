"""A room review is anchored on the previous one: old findings answered, flips justified."""

from __future__ import annotations

import json
from pathlib import Path

from zmforge.review import ai

PRINCIPLES = [{"id": "P1", "name": "Theme", "text": "strong theme"},
              {"id": "P15", "name": "Looks right", "text": "check how it looks"}]


def _room(name: str, props: int = 3) -> dict:
    return {"room": name, "room_id": f"room_{name}", "size": [256, 256, 128],
            "props": [[f"p{i}"] for i in range(props)], "scorecard": {"props": props},
            "materials": [], "notices": [], "interactives": []}


def _facts(*rooms: dict) -> dict:
    return {"map": "zm_test", "recipe": "test", "thresholds": {}, "rooms": list(rooms)}


def _review(room: str, p1: str = "pass", p15: str = "pass", findings=(), visual=()) -> dict:
    return {"room": room, "grade": "B", "score": 7.0, "summary": "",
            "principles": [{"id": "P1", "name": "Theme", "verdict": p1, "evidence": "mottos on walls"},
                           {"id": "P15", "name": "Looks right", "verdict": p15, "evidence": "reads fine"}],
            "fixes": [], "doesnt_make_sense": [{"finding": f, "severity": "medium", "where": "desk",
                                                "suggested_fix": ""} for f in findings],
            "visual_findings": [{"what": v, "where": "north wall", "view": "a--corner-sw.png",
                                 "severity": "medium"} for v in visual],
            "images": ["a--corner-sw.png"] if visual else []}


def _write(out: Path, stem: str, facts: dict, reviews: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.json").write_text(json.dumps({"facts": facts, "room_reviews": reviews}))


def test_the_newest_good_review_of_each_room_is_the_anchor(tmp_path):
    facts = _facts(_room("a"), _room("b", props=5))
    _write(tmp_path, "zm_test-20260920-100000", facts,
           [_review("a", findings=["old a"]), _review("b", p1="warn", findings=["b chair"])])
    # A later --rooms run reviewed only "a", and a later one errored on it.
    _write(tmp_path, "zm_test-20260921-100000", facts, [_review("a", p1="fail", findings=["new a"])])
    _write(tmp_path, "zm_test-20260922-100000", facts, [{"room": "a", "error": "boom", "principles": []}])
    (tmp_path / "zm_test-20260923-100000.facts.json").write_text("{}")   # --no-ai output
    (tmp_path / "zm_test2-20260924-100000.json").write_text("{}")        # another map

    now = _facts(_room("a"), _room("b", props=6))
    anchors = ai.previous_room_reviews(tmp_path, "zm_test", now)
    assert anchors["a"]["from"] == "zm_test-20260921-100000"
    assert [f["text"] for f in anchors["a"]["findings"]] == ["new a"]
    assert anchors["a"]["facts_changed"] == []
    assert anchors["b"]["from"] == "zm_test-20260920-100000"
    assert anchors["b"]["facts_changed"] == ["props", "scorecard"]
    assert ai.previous_room_reviews(tmp_path, "zm_test", now, rooms=["b"]).keys() == {"b"}
    assert ai.previous_room_reviews(tmp_path / "none", "zm_test", now) == {}


def test_the_room_prompt_carries_every_old_verdict_and_numbered_finding(tmp_path):
    facts = _facts(_room("a"))
    _write(tmp_path, "zm_test-20260920-100000", facts,
           [_review("a", p15="warn", findings=["desk has no chair"], visual=["posts with no belts"])])
    anchor = ai.previous_room_reviews(tmp_path, "zm_test", facts)["a"]
    prompt = ai.room_prompt(PRINCIPLES, facts["rooms"][0], "src", map_name="zm_test",
                            thresholds={}, previous=anchor)
    assert "PREVIOUS REVIEW OF THIS ROOM (zm_test-20260920-100000" in prompt
    assert "changed since then: none" in prompt
    assert "- P1: pass -- mottos on walls" in prompt
    assert "- P15: warn -- reads fine" in prompt
    assert "1. [doesnt_make_sense, medium] desk has no chair -- where: desk" in prompt
    assert "2. [visual, medium] posts with no belts -- where: north wall -- view: a--corner-sw.png" in prompt
    assert "verdict_changes" in prompt and "previous_findings" in prompt
    # Without an anchor the prompt is what it was.
    plain = ai.room_prompt(PRINCIPLES, facts["rooms"][0], "src", map_name="zm_test", thresholds={})
    assert "PREVIOUS REVIEW" not in plain


def test_an_unexplained_flip_is_held_and_an_explained_one_kept():
    anchor = {"from": "old", "principles": [{"id": "P1", "verdict": "pass"},
                                            {"id": "P15", "verdict": "pass"}],
              "findings": [{"n": 1}, {"n": 2}]}
    raw = {"principles": [{"id": "P1", "verdict": "fail", "evidence": "vibes"},
                          {"id": "P15", "verdict": "fail", "evidence": "x"}],
           "verdict_changes": [{"id": "P15", "previous": "pass", "now": "fail",
                                "reason": "ic_duct_3 now floats 40 units over the floor"}],
           "previous_findings": [{"n": 1, "status": "fixed", "note": "chair added"}]}
    review = ai.normalise(raw, PRINCIPLES, allow_na=True)
    ai.apply_anchor(review, raw, anchor)
    verdicts = {p["id"]: p["verdict"] for p in review["principles"]}
    assert verdicts == {"P1": "pass", "P15": "fail"}
    assert review["principles"][0]["evidence"].startswith("(kept pass from old")
    assert review["anchor"]["reverted"] == [{"id": "P1", "previous": "pass", "answered": "fail"}]
    assert review["anchor"]["unanswered"] == [2]


def test_a_visual_finding_still_keeps_p15_off_pass():
    anchor = {"from": "old", "principles": [{"id": "P15", "verdict": "pass"}], "findings": []}
    raw = {"principles": [{"id": "P15", "verdict": "pass", "evidence": ""}],
           "visual_findings": [{"what": "desk in wall", "where": "n", "view": "v.png",
                                "severity": "medium"}]}
    review = ai.normalise(raw, PRINCIPLES, allow_na=True, visual=True)
    ai.apply_anchor(review, raw, anchor)
    assert {p["id"]: p["verdict"] for p in review["principles"]}["P15"] == "warn"


def test_the_packet_anchors_each_room_and_import_holds_unexplained_flips(tmp_path):
    from zmforge.review import packet

    facts = _facts(_room("a"), _room("b"))
    _write(tmp_path, "zm_test-20260920-100000", facts, [_review("a", findings=["old a"])])
    previous = ai.previous_room_reviews(tmp_path, "zm_test", facts)
    pk = tmp_path / "zm_test-20260921-100000.packet"
    built = packet.build(facts, principles=PRINCIPLES, room_sources={}, map_source="",
                         packet_dir=pk, out_dir=tmp_path, stem="zm_test-20260921-100000",
                         previous=previous)
    assert [c["id"] for c in built["calls"]] == ["room-a", "room-b", "map"]   # one call each
    assert "old a" in (pk / "room-a.prompt.md").read_text()
    assert "old a" not in (pk / "room-b.prompt.md").read_text()
    schemas = {c["id"]: json.loads((pk / c["schema"]).read_text()) for c in built["calls"]}
    assert "verdict_changes" in schemas["room-a"]["required"]
    assert "verdict_changes" not in schemas["room-b"]["required"]
    answer = {"grade": "B", "score": 7, "summary": "", "fixes": [], "doesnt_make_sense": [],
              "principles": [{"id": "P1", "verdict": "warn", "evidence": "e", "suggested_fix": ""},
                             {"id": "P15", "verdict": "pass", "evidence": "e",
                              "suggested_fix": ""}]}
    (pk / "room-a.findings.json").write_text(json.dumps(
        dict(answer, room="a", previous_findings=[], verdict_changes=[])))
    (pk / "room-b.findings.json").write_text(json.dumps(dict(answer, room="b")))
    (pk / "map.findings.json").write_text(json.dumps(answer))
    result, problems = packet.grade(pk)
    assert problems == []
    by_room = {r["room"]: r for r in result["room_reviews"]}
    assert by_room["a"]["principles"][0]["verdict"] == "pass"   # held: flip gave no reason
    assert by_room["a"]["anchor"]["unanswered"] == [1]
    assert "anchor" not in by_room["b"]
    assert by_room["b"]["principles"][0]["verdict"] == "warn"
    assert result["anchored_on"] == ["zm_test-20260920-100000"]
    ai.write_outputs(result, tmp_path, "zm_test-20260921-100000")
    again = ai.previous_room_reviews(tmp_path, "zm_test", facts)   # the next packet's anchor
    assert again["a"]["from"] == "zm_test-20260921-100000"


def test_the_report_says_how_the_anchor_went():
    review = {"room": "a", "grade": "B", "score": 7, "summary": "", "principles": [],
              "fixes": [], "doesnt_make_sense": [],
              "anchor": {"from": "old", "previous_findings": [{"n": 1, "status": "fixed", "note": ""}],
                         "verdict_changes": [], "reverted": [{"id": "P1"}], "unanswered": []}}
    text = ai.markdown_report({"facts": {"map": "zm_test", "recipe": "test"}, "room_reviews": [review],
                               "map_review": None, "errors": [], "calls": []})
    assert "1 fixed" in text and "1 unexplained flip(s) held" in text
