"""The visual check is part of every ``zmforge review``: renders per room, visual_findings, P15.

No model and no Radiant: ``zmforge review`` writes the packet, the example
runner (``scripts/review-with-claude.py``) answers it with a stub ``claude``
script, and ``render_recipe`` is monkeypatched.  The map is ``one-room`` measured once, with its room copied
to a second key so per-room routing can be checked.
"""

from __future__ import annotations

import copy
import json
import stat
import sys
from pathlib import Path

import pytest

from zmforge.review import ai
from zmforge.review import facts as measure

PRINCIPLE_IDS = [p["id"] for p in ai.load_principles()]


@pytest.fixture(scope="module")
def two_room_facts():
    data = measure.collect(measure.generate("one-room"))
    first = data["rooms"][0]
    second = copy.deepcopy(first)
    second["room"], second["room_id"] = "hall", "hall_room"
    data["rooms"] = [first, second]
    return data


@pytest.fixture
def fake_map(monkeypatch, two_room_facts):
    """``review`` measures the canned two-room facts instead of generating."""
    monkeypatch.setattr(measure, "generate", lambda recipe, name=None, **kw: None)
    monkeypatch.setattr(measure, "collect", lambda gen: copy.deepcopy(two_room_facts))
    monkeypatch.setattr(measure, "scorecard_table", lambda data: "table")
    monkeypatch.setattr(measure, "room_source", lambda *a, **k: "")
    monkeypatch.setattr(measure, "map_source", lambda *a, **k: "")
    return [r["room"] for r in two_room_facts["rooms"]]


def _stub(tmp_path: Path, visual_findings: dict | None = None) -> tuple[Path, Path]:
    """A fake ``claude``: logs each call (room, schema keys, image bytes), answers pass."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "claude"
    script.write_text(f"""#!{sys.executable}
import base64, json, sys
argv = sys.argv[1:]
stdin = sys.stdin.read()
schema = json.loads(argv[argv.index("--json-schema") + 1])
streamed = "stream-json" in argv
images = []
prompt = stdin
if streamed:
    content = json.loads(stdin)["message"]["content"]
    images = [base64.b64decode(b["source"]["data"]).decode() for b in content
              if b["type"] == "image"]
    prompt = content[-1]["text"]
room = prompt.split('"room":"', 1)[1].split('"', 1)[0] if "room" in schema["required"] else None
review = {{"grade": "B", "score": 8, "summary": "stub",
          "principles": [{{"id": i, "verdict": "pass", "evidence": "e", "suggested_fix": ""}}
                         for i in {PRINCIPLE_IDS!r}],
          "fixes": [], "doesnt_make_sense": []}}
if room:
    review["room"] = room
if "visual_findings" in schema["properties"]:
    review["visual_findings"] = {visual_findings or {}!r}.get(room, [])
with open({str(log)!r}, "a") as fh:
    fh.write(json.dumps({{"room": room, "images": images, "streamed": streamed,
                         "visual_schema": "visual_findings" in schema["properties"]}}) + "\\n")
event = {{"type": "result", "subtype": "success", "is_error": False, "result": "",
          "structured_output": review, "total_cost_usd": 0.5 if images else 0.1}}
if streamed:
    print(json.dumps({{"type": "system"}}))
print(json.dumps(event))
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, log


def _shots(tmp_path: Path, rooms) -> dict[str, list[str]]:
    """Two fake PNGs per room whose bytes name the room, so routing can be checked."""
    out = {}
    for room in rooms:
        out[room] = []
        for view in ("corner-sw", "corner-ne"):
            png = tmp_path / "render" / f"{room}--{view}.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_text(f"{room}/{view}")
            out[room].append(str(png))
    return out


def _review(tmp_path, stub, *extra) -> tuple[dict, str, list[dict]]:
    """``zmforge review`` builds the packet; the example runner answers it with the stub."""
    from conftest import load_review_runner

    runner = load_review_runner()
    out = tmp_path / "out"
    assert runner.main(["one-room", "--out", str(out), "--claude-bin", str(stub[0]),
                        "--quiet", "--jobs", "1", *extra]) == 0
    (json_path,) = out.glob("zm_one_room-*[0-9].json")
    (md_path,) = out.glob("zm_one_room-*.md")
    calls = [json.loads(line) for line in stub[1].read_text().splitlines()]
    return json.loads(json_path.read_text()), md_path.read_text(), calls


def _fake_render(tmp_path, calls: list, *, reused=()):
    def render_recipe(recipe, **kw):
        calls.append(kw)
        rooms = kw["rooms"] or ["start", "hall"]
        return {"out": str(tmp_path / "render"), "shots": _shots(tmp_path, rooms),
                "rendered": [r for r in rooms if r not in reused],
                "reused": [r for r in rooms if r in reused]}
    return render_recipe


def test_renders_are_attached_to_their_own_room(tmp_path, monkeypatch, fake_map):
    render_calls: list = []
    monkeypatch.setattr("zmforge.render.run.render_recipe", _fake_render(tmp_path, render_calls))
    result, md, calls = _review(tmp_path, _stub(tmp_path))
    rooms = {c["room"]: c for c in calls if c["room"]}
    assert set(rooms) == set(fake_map)
    for room, call in rooms.items():
        assert call["streamed"] and call["visual_schema"]
        assert call["images"] == [f"{room}/corner-sw", f"{room}/corner-ne"]
    map_call = next(c for c in calls if c["room"] is None)
    assert map_call["images"] == [] and not map_call["visual_schema"]
    for review in result["room_reviews"]:
        assert review["images"] == [f"{review['room']}--corner-sw.png",
                                    f"{review['room']}--corner-ne.png"]
        assert review["visual_findings"] == []
    assert result["visual"]["status"] == "ok"
    assert "Visual check: ok" in md


def test_review_asks_for_changed_rooms_and_uses_reused_shots(tmp_path, monkeypatch, fake_map):
    render_calls: list = []
    monkeypatch.setattr("zmforge.render.run.render_recipe",
                        _fake_render(tmp_path, render_calls, reused=("hall",)))
    result, _, calls = _review(tmp_path, _stub(tmp_path), "--visual-views", "2")
    (kw,) = render_calls
    assert kw["changed"] is True and kw["views"] == 2 and kw["out"] is None
    assert result["visual"] == {"status": "ok", "out": str(tmp_path / "render"),
                                "rendered": ["start"], "reused": ["hall"]}
    hall = next(c for c in calls if c["room"] == "hall")
    assert hall["images"] == ["hall/corner-sw", "hall/corner-ne"]   # reused shots still attached


def test_rooms_flag_limits_the_render(tmp_path, monkeypatch, fake_map):
    render_calls: list = []
    monkeypatch.setattr("zmforge.render.run.render_recipe", _fake_render(tmp_path, render_calls))
    result, _, calls = _review(tmp_path, _stub(tmp_path), "--rooms", "hall")
    assert render_calls[0]["rooms"] == ["hall"]
    assert [c["room"] for c in calls if c["room"]] == ["hall"]
    assert "no_images" not in result["visual"]


def test_no_visual_renders_nothing_and_attaches_nothing(tmp_path, monkeypatch, fake_map):
    def boom(*a, **k):
        raise AssertionError("render_recipe must not run with --no-visual")

    monkeypatch.setattr("zmforge.render.run.render_recipe", boom)
    result, md, calls = _review(tmp_path, _stub(tmp_path), "--no-visual")
    assert all(c["images"] == [] and not c["streamed"] and not c["visual_schema"] for c in calls)
    assert result["visual"] == {"status": "skipped"}
    assert all("visual_findings" not in r for r in result["room_reviews"])
    assert "Visual check: skipped" in md and "## Visual findings" not in md


def test_visual_findings_reach_json_and_report_and_fail_p15(tmp_path, monkeypatch, fake_map):
    monkeypatch.setattr("zmforge.render.run.render_recipe", _fake_render(tmp_path, []))
    findings = {
        "start": [{"what": "stanchion posts with no belts between them", "where": "queue line, props 12-17",
                   "view": "start--corner-sw.png", "severity": "medium"}],
        "hall": [{"what": "desk floats above the floor", "where": "desk_3",
                  "view": "/tmp/render/hall--corner-ne.png", "severity": "high"}],
    }
    result, md, _ = _review(tmp_path, _stub(tmp_path, findings))
    reviews = {r["room"]: r for r in result["room_reviews"]}
    assert reviews["start"]["visual_findings"] == [dict(findings["start"][0])]
    assert reviews["hall"]["visual_findings"][0]["view"] == "hall--corner-ne.png"
    p15 = {room: next(p for p in r["principles"] if p["id"] == "P15")
           for room, r in reviews.items()}
    assert p15["start"]["verdict"] == "warn"      # medium finding: at least warn
    assert p15["hall"]["verdict"] == "fail"       # high finding: fail
    assert "visual finding" in p15["hall"]["evidence"]
    assert "## Visual findings" in md and "### start" in md and "### hall" in md
    assert "stanchion posts with no belts" in md and "`start--corner-sw.png`" in md
    assert "desk floats above the floor" in md


def test_normalise_keeps_a_worse_p15_and_ignores_findings_without_images():
    principles = [{"id": "P15", "name": "Check how it actually looks", "text": ""}]
    finding = [{"what": "x", "where": "y", "view": "a.png"}]
    failed = {"principles": [{"id": "P15", "verdict": "fail"}], "visual_findings": finding}
    assert ai.normalise(failed, principles, allow_na=True,
                        visual=True)["principles"][0]["verdict"] == "fail"
    na = {"principles": [{"id": "P15", "verdict": "n/a"}], "visual_findings": finding}
    assert ai.normalise(na, principles, allow_na=True,
                        visual=True)["principles"][0]["verdict"] == "warn"
    blind = ai.normalise(dict(na, principles=[{"id": "P15", "verdict": "pass"}]), principles,
                         allow_na=True)
    assert "visual_findings" not in blind and blind["principles"][0]["verdict"] == "pass"
    assert "visual_findings" in ai.room_schema(True)["required"]
    assert "visual_findings" not in ai.room_schema(False)["properties"]


def test_render_failure_reviews_without_pictures_and_says_so(tmp_path, monkeypatch, fake_map):
    from zmforge.render.radiant import RenderError

    def broken(*a, **k):
        raise RenderError("Radiant did not start")

    monkeypatch.setattr("zmforge.render.run.render_recipe", broken)
    result, md, calls = _review(tmp_path, _stub(tmp_path))
    assert result["visual"]["status"] == "failed"
    assert "Radiant did not start" in result["visual"]["error"]
    assert all(c["images"] == [] for c in calls)
    assert len([c for c in calls if c["room"]]) == 2 and result["map_review"]["grade"] == "B"
    assert "Visual check: FAILED" in md and "P15 not judged from pictures" in md
