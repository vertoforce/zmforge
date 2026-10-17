"""The advisory design review: the measurements, the text rules, the review
packet and grading the findings written into it, and the example claude
runner -- with a stub CLI, never a real call."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from zmforge.review import ai, facts as measure

PRINCIPLES = ai.load_principles()


# ----------------------------------------------------------------------
# Text rules
# ----------------------------------------------------------------------
def test_text_issues_flags_a_prompt_without_the_use_key():
    assert any("use key" in i for i in measure.text_issues("LOST AND FOUND: look", prompt=True))
    assert not measure.text_issues("LOST AND FOUND: hold ^3[{+activate}]^7 to look", prompt=True)


@pytest.mark.parametrize("text, needle", [
    ("TODO write the joke", "placeholder"),
    ("Your {name} is ready", "placeholder"),
    ("Please wait wait to be called", "doubled word"),
    ("Take a  number", "double space"),
    ("The examiner is ^watching", "stray ^"),
    ("Your registraton has expired", "typo"),
])
def test_text_issues_catch_mechanical_problems(text, needle):
    assert any(needle in i for i in measure.text_issues(text)), measure.text_issues(text)


def test_text_issues_leave_game_words_and_codes_alone():
    assert measure.text_issues("^3PA:^7 The undead are asked to take a number.") == []


def test_gsc_literals_keep_sentences_and_drop_identifiers():
    text = 'a = "scripts/zm/foo.gsc"; b = "zmf_notice"; IPrintLnBold("The fridge is open now");'
    assert measure.gsc_literals(text) == ["The fridge is open now"]


# ----------------------------------------------------------------------
# The summary generator
# ----------------------------------------------------------------------
def test_density_is_a_floor_scaled_by_floor_area():
    """P2: at least 100 props; 40% of stock (459 per 1,000,000 sq units) in a
    room of 0.5 k2 or more, a quarter (287) in a smaller one; no band top."""
    assert measure.density_floor(400 * 400) == 100
    assert measure.density_floor(600 * 600) == 103
    assert measure.density_floor(1000 * 1000) == 459
    assert measure.density_floor(2000 * 2000) == 1836
    assert not hasattr(measure, "DENSITY_RANGE")


def test_script_threads_report_loops_their_ends_and_the_lines_they_show():
    """P12/P13: a forever loop, its endon events, who threads it, its lines."""
    gsc = (
        'function main()\n{\n\tlevel thread call_loop();\n}\n\n'
        'function call_loop()\n{\n\tlevel endon( "step_done" );\n\twhile ( true )\n\t{\n'
        '\t\twait RandomFloatRange( 3, 5 );\n\t\tIPrintLnBold( &"ZM_X_CALL", 5 );\n\t}\n}\n\n'
        'function leak()\n{\n\tfor ( ;; )\n\t{\n\t\twait 1; // "}" in a comment string\n\t}\n}\n'
    )
    lookup = {"ZM_X_CALL": ("CALL", "Now serving &&1", "string")}
    out = measure.script_threads(gsc, lookup)
    rows = {r["function"]: r for r in out["threads"]}
    assert set(rows) == {"call_loop", "leak"}
    call = rows["call_loop"]
    assert call["endon"] == ["step_done"] and call["forever_loops"] == 1 and call["random"]
    assert call["threaded_by"] == ["main"]
    assert call["lines_shown"] == [["IPrintLnBold", "ZM_X_CALL", "Now serving &&1"]]
    assert rows["leak"]["endon"] == [] and rows["leak"]["forever_loops"] == 1
    assert "function call_loop" in out["source"] and "function leak" in out["source"]


def test_script_threads_resolve_an_endon_passed_as_a_parameter():
    """``level endon( str_end )`` ends on whatever each caller passes: a quest
    zone pulse ends on its step's end event, not only at end of game; it is
    not a loop that never ends."""
    gsc = (
        'function step()\n{\n\tlevel thread pulse( (1, 2, 3), "fx", "zmf_q_end_subject" );\n'
        '\tlevel notify( "zmf_q_end_subject" );\n}\n\n'
        'function pulse( v_at, str_fx, str_end )\n{\n\tlevel endon( "end_game" );\n'
        '\tlevel endon( str_end );\n\twhile ( true )\n\t{\n\t\twait 2.5;\n\t}\n}\n'
    )
    rows = {r["function"]: r for r in measure.script_threads(gsc, {})["threads"]}
    pulse = rows["pulse"]
    assert pulse["endon"] == ["end_game", "zmf_q_end_subject"]
    assert pulse["endon_passed_by_caller"] == {
        "zmf_q_end_subject": {"passed_by": ["step"], "notified_by": ["step"]}}


def test_floor_litter_counts_toward_density_only_up_to_a_quarter():
    """P2: litter is seasoning, not the meal.  A room padded to 160 props with
    100 pieces of floor paper counts 60 real props + 20 litter = 80."""
    from zmforge.recipes.props import is_litter

    assert is_litter("p7_office_paper_folder_pink") and is_litter("p7_debris_trash_cup_red_02")
    assert not is_litter("p7_trashcan_metal_modern_glass") and not is_litter("p7_file_cab_metal_02")
    area = measure.Area("r", "r_room", 0, 0, 400, 400, 0, 128)

    def prop(i, model, sits_on="floor"):
        p = measure.PropFact(f"p{i}", model, 100.0 + i, 100.0, 0.0, 0.0, 1.0, False,
                             bounds=(99.0 + i, 99.0, 101.0 + i, 101.0), z_low=0.0, z_high=2.0,
                             area=area)
        p.sits_on = sits_on
        return p

    real = [prop(i, "p7_chair_lab_01") for i in range(60)]
    litter = [prop(100 + i, "p7_office_paper_sheet_01") for i in range(100)]
    on_desk = [prop(300 + i, "p7_office_paper_sheet_01", "prop desk (p7_desk_metal_old_01)")
               for i in range(10)]
    card = measure._room_scorecard(area, real + litter, {}, [], 0, [])
    assert card["props"] == 160 and card["floor_litter"] == 100
    assert card["litter_share"] == 0.62 and card["counted_props"] == 80
    assert card["density_band"] == "under"
    # the same paper on a desk is surface clutter, not litter
    card = measure._room_scorecard(area, real + on_desk, {}, [], 0, [])
    assert card["floor_litter"] == 0 and card["counted_props"] == 70
    # a little litter counts in full
    card = measure._room_scorecard(area, real + litter[:20], {}, [], 0, [])
    assert card["counted_props"] == 80 and card["litter_share"] == 0.25
    assert measure.counted_props(100, 0) == 100 and measure.counted_props(50, 50) == 0


@pytest.fixture(scope="module")
def corn_facts():
    return measure.collect(measure.generate("corn_maze"))


def test_collect_measures_every_room_and_prop(corn_facts):
    from zmforge.blueprint.elements import PropScatter, Room

    bp, quests, notices = measure.build_blueprint("corn_maze")
    rooms = bp.elements(Room)
    # Counted after a commit, as the facts are: Project.commit places the
    # gamble machine (Z87) and its approach lane takes
    # out the props that stood there (zmforge.blueprint.lanes).
    from zmforge.dressing.gamble import place_gamble_machine

    place_gamble_machine(bp)
    total = sum(len(s.props) for s in bp.elements(PropScatter))
    assert len(corn_facts["rooms"]) == len(rooms)
    counted = sum(r["scorecard"]["props"] for r in corn_facts["rooms"])
    assert counted + corn_facts["outside_props"]["count"] == total
    for room in corn_facts["rooms"]:
        card = room["scorecard"]
        assert card["props"] == len(room["props"])
        assert len(room["props_columns"]) == len(room["props"][0])
        assert card["density_band"] in ("under", "in", "over")
        assert card["counted_props"] <= card["props"] and 0.0 <= card["litter_share"] <= 1.0
        if card["floor_props"]:
            assert 0.0 <= card["wall_hug_share"] <= 1.0
            assert card["wall_hug_share"] + card["middle_share"] <= 1.0
    assert quests and corn_facts["quests"][0]["type"] == "Quest"
    assert corn_facts["notices_total"] == len(notices) > 0
    assert corn_facts["quest_points"]
    assert corn_facts["progression"]["unreached_zones"] == []


def test_collect_records_the_ending_boss_and_strings(corn_facts):
    quest = corn_facts["quests"][0]
    assert quest["exit"]["price"] == 20000
    assert any(step["type"] == "DefeatBoss" for step in quest["steps"])
    rows = corn_facts["strings"]["map_strings"]
    assert rows and all({"ref", "kind", "text", "issues"} <= set(r) for r in rows)
    assert json.dumps(corn_facts, default=str)  # the whole thing is JSON-able


def test_recording_undoes_itself():
    from zmforge.script import quest, tricks

    before = (quest.install_quest, tricks.use_notices)
    measure.build_blueprint("corn_maze")
    assert (quest.install_quest, tricks.use_notices) == before
    # a module first imported during the build took the name too
    import zmforge.recipes.corn_maze_script as script

    assert script.use_notices is tricks.use_notices


def test_wall_gap_and_sides():
    area = measure.Area("r", "r_room", 0, 0, 400, 300, 0, 128)
    assert area.wall_gap(10, 100, 50, 140) == (10, "west")
    assert area.wall_gap(100, 280, 140, 310) == (-10, "north")
    assert area.rel(110, 20, 16) == [110, 20, 16]


def test_supports_reads_shelf_boards_as_surfaces():
    """A book set on a shelving unit's inner board (props.SHELF_BOARDS) rests
    on the board, not on the floor 50 units down: `_supports` must read
    `layout.shelves` the same way placement/audit.py's own Z44 check does,
    or a legitimately-shelved prop scores as floating."""
    from zmforge.placement.audit import Layout
    from zmforge.review.facts import PropFact, _supports

    shelf = PropFact("shelf", "test_shelf_model", 5.0, 5.0, 0.0, 0.0, 1.0, True,
                      bounds=(0.0, 0.0, 10.0, 10.0), z_low=0.0, z_high=100.0)
    book = PropFact("book", "test_book_model", 5.0, 5.0, 50.0, 0.0, 1.0, False,
                     bounds=(2.0, 2.0, 8.0, 8.0), z_low=50.0, z_high=55.0)
    layout = Layout(shelves={"test_shelf_model": (0.5,)})
    _supports([shelf, book], layout, [])
    assert "shelf" in book.sits_on
    assert book.float_gap <= measure.FLOAT_GAP


def test_room_source_finds_the_dressing_code():
    assert "dmv_rooms/eye.py" in measure.room_source("dmv", "eyeexam", "eye_exam_room")
    assert "_dress_shed" in measure.room_source("cemetery", "shed", "shed_room")
    assert "dmv_quest.py" in measure.map_source("dmv")


# ----------------------------------------------------------------------
# Hard rules the review surfaced, held for every shipped recipe
# ----------------------------------------------------------------------
#: Prompts on a trigger that cannot be used right now say what unlocks it
#: instead of offering a key press.
_NOT_USABLE_YET = ("LOCKED", "CLOSED", "AWAY")


@pytest.mark.parametrize("recipe", ["dmv", "cemetery", "corn_maze"])
def test_every_usable_prompt_names_the_use_key_and_nothing_is_placeholder(recipe):
    bp, _quests, notices = measure.build_blueprint(recipe)
    lookup = measure._string_lookup(bp)
    for _origin, prompt, _replies in notices:
        assert measure.USE_KEY.search(lookup[prompt][1]), lookup[prompt]
    for ref, text, kind in lookup.values():
        if kind == "triggerstring" and "&&" not in text and not any(w in ref for w in _NOT_USABLE_YET):
            assert measure.USE_KEY.search(text), (ref, text)
        assert not measure._PLACEHOLDER.search(text), (ref, text)


# ----------------------------------------------------------------------
# The example runner (scripts/review-with-claude.py), with the CLI stubbed
# ----------------------------------------------------------------------
def _envelope(review: dict, *, structured: bool = True) -> str:
    body = {"type": "result", "subtype": "success", "is_error": False,
            "result": json.dumps(review), "total_cost_usd": 0.01, "num_turns": 1}
    if structured:
        body["structured_output"] = review
    return json.dumps(body)


def test_parse_prefers_structured_output(review_runner):
    review, meta = review_runner.parse_cli_output(_envelope({"grade": "B"}))
    assert review == {"grade": "B"} and meta["total_cost_usd"] == 0.01


def test_parse_falls_back_to_fenced_json_in_the_result(review_runner):
    out = json.dumps({"subtype": "success", "is_error": False,
                      "result": "Here:\n```json\n{\"grade\": \"C\"}\n```"})
    assert review_runner.parse_cli_output(out)[0] == {"grade": "C"}


@pytest.mark.parametrize("stdout", [
    "not json",
    json.dumps({"is_error": True, "subtype": "error_max_turns", "result": "x"}),
    json.dumps({"subtype": "success", "result": "no json here"}),
])
def test_parse_rejects_failures(stdout, review_runner):
    with pytest.raises(ai.ReviewError):
        review_runner.parse_cli_output(stdout)


def test_normalise_fills_gaps_and_counts_odd_verdicts_as_warn():
    raw = {"grade": "b+", "score": 14, "summary": "ok",
           "principles": [{"id": "P1", "verdict": "PASS", "evidence": "e", "suggested_fix": ""},
                          {"id": "P2", "verdict": "maybe", "evidence": "e", "suggested_fix": "f"},
                          {"id": "P3", "verdict": "n/a", "evidence": "", "suggested_fix": ""},
                          {"id": "P99", "verdict": "fail", "evidence": "", "suggested_fix": ""}],
           "doesnt_make_sense": [{"finding": "x", "severity": "CRITICAL", "where": "w"}]}
    out = ai.normalise(raw, PRINCIPLES, allow_na=False)
    verdicts = {p["id"]: p["verdict"] for p in out["principles"]}
    assert [p["id"] for p in out["principles"]] == [p["id"] for p in PRINCIPLES]
    assert verdicts["P1"] == "pass" and verdicts["P2"] == "warn" and verdicts["P3"] == "warn"
    assert verdicts["P4"] == "warn"  # missing -> warn, never a silent pass
    assert out["grade"] == "B" and out["score"] == 10.0
    assert out["doesnt_make_sense"][0]["severity"] == "medium"
    assert any("P99" in n for n in out["normalise_notes"])
    room = ai.normalise(raw, PRINCIPLES, allow_na=True)
    assert {p["id"]: p["verdict"] for p in room["principles"]}["P3"] == "n/a"


def test_exit_code_only_blocks_on_fail_when_strict():
    passing = {"map_review": {"principles": [{"verdict": "pass"}, {"verdict": "warn"}]},
               "room_reviews": [], "errors": []}
    failing = {"map_review": {"principles": [{"verdict": "fail"}]}, "room_reviews": [],
               "errors": []}
    assert ai.exit_code(failing, strict=False) == 0
    assert ai.exit_code(failing, strict=True) == 1
    assert ai.exit_code(passing, strict=True) == 0
    assert ai.exit_code(dict(passing, errors=["map: boom"]), strict=True) == 1


def _stub_cli(tmp_path: Path, verdict: str) -> Path:
    """A fake ``claude`` that answers every call with *verdict* for every principle."""
    ids = [p["id"] for p in PRINCIPLES]
    script = tmp_path / "claude"
    script.write_text(f"""#!{sys.executable}
import json, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
assert "-p" in argv and "--json-schema" in argv and "--tools" in argv, argv
schema = json.loads(argv[argv.index("--json-schema") + 1])
room = "room" in schema["required"]
review = {{"grade": "C", "score": 6, "summary": "stub",
          "principles": [{{"id": i, "verdict": {verdict!r}, "evidence": "e", "suggested_fix": "f"}}
                         for i in {ids!r}],
          "fixes": [{{"target": "x_0", "change": "move it", "priority": "low"}}],
          "doesnt_make_sense": []}}
if room:
    review["room"] = prompt.split('"room":"', 1)[1].split('"', 1)[0]
open({str(tmp_path / 'calls.log')!r}, "a").write(("room" if room else "map") + "\\n")
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "result": "", "structured_output": review, "total_cost_usd": 0.0}}))
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _packet(tmp_path: Path, facts, rooms=None) -> Path:
    from zmforge.review import packet

    packet.build(facts, principles=PRINCIPLES,
                 room_sources={r["room"]: "" for r in facts["rooms"]}, map_source="",
                 packet_dir=tmp_path / "pk", out_dir=tmp_path / "out", stem="zm_corn_maze-test",
                 rooms=rooms, extra={"scorecard_table": "table", "visual": {"status": "skipped"}})
    return tmp_path / "pk"


def test_the_runner_answers_every_call_of_a_packet(tmp_path, corn_facts, review_runner):
    from zmforge.review import packet

    stub = _stub_cli(tmp_path, "pass")
    pk = _packet(tmp_path, corn_facts)
    errors = review_runner.answer_packet(
        pk, review_runner.ClaudeCLI(binary=str(stub), timeout=60, retries=0), jobs=3)
    assert errors == []
    calls = (tmp_path / "calls.log").read_text().split()
    assert calls.count("map") == 1 and calls.count("room") == len(corn_facts["rooms"])
    stored = sorted(p.name for p in pk.iterdir())
    assert "map.prompt.md" in stored and "map.findings.json" in stored
    assert "map.meta.json" in stored
    result, problems = packet.grade(pk)
    assert problems == [] and result["errors"] == []
    assert [r["room"] for r in result["room_reviews"]] == [r["room"] for r in corn_facts["rooms"]]
    assert result["map_review"]["grade"] == "C"
    paths = ai.write_outputs(result, tmp_path / "out", "zm_corn_maze-test")
    assert json.loads(paths["json"].read_text())["map_review"]["grade"] == "C"
    assert "Map grade C" in paths["report"].read_text()


def test_a_failed_call_is_recorded_not_raised(tmp_path, corn_facts, review_runner):
    from zmforge.review import packet

    bad = tmp_path / "claude"
    bad.write_text(f"#!{sys.executable}\nimport sys; sys.stdin.read(); sys.exit(3)\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    pk = _packet(tmp_path, corn_facts, rooms=["barn"])
    errors = review_runner.answer_packet(
        pk, review_runner.ClaudeCLI(binary=str(bad), timeout=60, retries=0))
    assert len(errors) == 2
    assert packet.grade(pk)[0] is None                       # strict import refuses
    result, _ = packet.grade(pk, partial=True)
    assert len(result["errors"]) == 2 and result["map_review"] is None
    assert "exit 3" in result["errors"][0]
    assert ai.exit_code(result, strict=True) == 1


# ----------------------------------------------------------------------
# The packet and the import, with a fake agent writing the findings
# ----------------------------------------------------------------------
def _answer(principle_ids, verdict="pass", **extra) -> dict:
    return {"grade": "C", "score": 6, "summary": "fake agent",
            "principles": [{"id": i, "verdict": verdict, "evidence": "e", "suggested_fix": "f"}
                           for i in principle_ids],
            "fixes": [], "doesnt_make_sense": [], **extra}


def _fake_agent(pk: Path, verdict: str = "pass") -> None:
    """Answers every call of the packet the way an agent following the workflow would."""
    meta = json.loads((pk / "packet.json").read_text())
    ids = [p["id"] for p in meta["principles"]]
    for call in meta["calls"]:
        schema = json.loads((pk / call["schema"]).read_text())
        answer = _answer(ids, verdict)
        if call["kind"] == "room":
            answer["room"] = call["room"]
        for key in ("visual_findings", "previous_findings", "verdict_changes"):
            if key in schema["required"]:
                answer[key] = []
        (pk / call["findings"]).write_text(json.dumps(answer))


def test_the_packet_holds_every_call_prompt_schema_and_the_facts(tmp_path, corn_facts):
    pk = _packet(tmp_path, corn_facts)
    meta = json.loads((pk / "packet.json").read_text())
    assert meta["format"] == "zmforge-review-packet/1"
    ids = [c["id"] for c in meta["calls"]]
    assert ids[-1] == "map" and len(ids) == len(corn_facts["rooms"]) + 1
    for call in meta["calls"]:
        assert (pk / call["prompt"]).read_text().strip()
        assert json.loads((pk / call["schema"]).read_text())["type"] == "object"
    assert ai.ROOM_REVIEWS_LATER in (pk / "map.prompt.md").read_text()
    assert "zmforge review --import" in (pk / "README.md").read_text()
    assert meta["facts"]["map"] == corn_facts["map"]


def test_import_refuses_missing_or_invalid_findings_and_says_why(tmp_path, corn_facts):
    from zmforge.review import packet

    pk = _packet(tmp_path, corn_facts, rooms=["barn"])
    result, problems = packet.grade(pk)
    assert result is None and any("no findings file" in p for p in problems)
    _fake_agent(pk)
    bad = json.loads((pk / "room-barn.findings.json").read_text())
    bad["principles"][0]["verdict"] = "great"
    del bad["summary"]
    (pk / "room-barn.findings.json").write_text("```json\n" + json.dumps(bad) + "\n```")
    result, problems = packet.grade(pk)
    assert result is None
    assert any("missing required key 'summary'" in p for p in problems)
    assert any("principles[0].verdict" in p and "'great'" in p for p in problems)


def test_a_fake_agent_answers_the_packet_and_import_writes_the_report(tmp_path, corn_facts,
                                                                       capsys):
    from zmforge.review import run

    pk = _packet(tmp_path, corn_facts, rooms=["barn"])
    assert run.import_findings(pk, quiet=True) == 2          # nothing answered yet
    _fake_agent(pk, "fail")
    assert run.import_findings(pk, quiet=True, reviewer="fake agent") == 0
    assert run.import_findings(pk, quiet=True, strict=True) == 1
    out = capsys.readouterr().out
    assert "map grade C" in out and "FAIL" in out
    (report,) = (tmp_path / "out").glob("zm_corn_maze-test.json")
    data = json.loads(report.read_text())
    assert data["room_reviews"][0]["room"] == "barn" and data["packet"] == str(pk.resolve())


def test_schema_validation_covers_types_enums_ranges_and_nesting():
    from zmforge.review.schema import MAP_SCHEMA, validate

    good = _answer([p["id"] for p in PRINCIPLES])
    assert validate(good, MAP_SCHEMA) == []
    assert validate(dict(good, score=11), MAP_SCHEMA) == ["$.score: 11 is above 10"]
    assert validate(dict(good, score="6"), MAP_SCHEMA) == ["$.score: expected number, got str"]
    assert validate([], MAP_SCHEMA) == ["$: expected object, got list"]
    bad_fix = dict(good, fixes=[{"target": "x", "change": "y", "priority": "urgent"}])
    assert validate(bad_fix, MAP_SCHEMA) == [
        "$.fixes[0].priority: 'urgent' is not one of ['high', 'medium', 'low']"]


def test_cli_strict_exits_one_on_a_fail(tmp_path, capsys, monkeypatch, corn_facts):
    from zmforge.facade.cli import main
    from zmforge.review import run as review_run

    # Build the packet from the facts measured once for this module
    # (generating corn_maze again took minutes).
    monkeypatch.setattr(review_run.measure, "generate", lambda *a, **k: None)
    monkeypatch.setattr(review_run.measure, "collect",
                        lambda gen: __import__("copy").deepcopy(corn_facts))
    argv = ["review", "corn_maze", "--out", str(tmp_path / "out"), "--rooms", "barn",
            "--quiet", "--no-visual"]
    assert main(argv) == 0
    (pk,) = (tmp_path / "out").glob("zm_corn_maze-*.packet")
    _fake_agent(pk, "fail")
    assert main(["review", "--import", str(pk), "--quiet"]) == 0
    assert main(["review", "--import", str(pk), "--quiet", "--strict"]) == 1
    out = capsys.readouterr().out
    assert "map grade C" in out and "FAIL" in out
    assert list((tmp_path / "out").glob("zm_corn_maze-*.md"))
