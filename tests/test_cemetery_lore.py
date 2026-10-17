"""Cemetery Quest tells one story (principle P11): names, dates and family
plots agree with each other and with the quest, and every optional clue
points at something that is really there.  The facts are
:data:`zmforge.recipes.cemetery_lore.STORY`."""

from __future__ import annotations

import math
import re

import pytest

from zmforge.blueprint.elements import Massing, Room
from zmforge.blueprint.model import _solid_bounds
from zmforge.recipes.cemetery import (
    EPITAPHS, FOUNDER_NEEDLE, GAG_LINES, MAUSOLEUMS, NOTICE_LINES, OPEN_GRAVE, ROW_TOMBS,
    build_cemetery,
)
from zmforge.recipes.cemetery_lore import (
    LORE_EPITAPHS, LORE_NOTICES, STORY, clear_of_paths,
)
from zmforge.script import quest as q
from zmforge.spatial import Facing

#: First names (and initials) the story gives each family.
FAMILY = {
    "GRAVES": {"AMOS", "A", "OBADIAH", "RUTH", "ELI"},
    "DIGGS": {"JONAH", "J"},
    "MOORE": {"CORNELIUS", "C", "DR"},
    "HOLLOW": {"EZEKIEL", "ADELAIDE"},
}
MONTHS = {"OCT": 10}


@pytest.fixture(scope="module")
def built():
    return build_cemetery("zm_cemetery")


@pytest.fixture(scope="module")
def texts(built) -> list[str]:
    """Every line a player can read: stones, notices, gags and the quest."""
    out = [p for p, _ in [*EPITAPHS.values(), *NOTICE_LINES.values()]]
    out += [line for _, lines in [*EPITAPHS.values(), *NOTICE_LINES.values()] for line in lines]
    out += list(GAG_LINES.values())
    out += [text for text, _kind in q.quest_strings(built[1]["quest"]).values()]
    return out


def _lines(table: dict, key: str) -> str:
    return " ".join(table[key][1]).upper()


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------
def test_every_name_belongs_to_its_family(texts) -> None:
    firsts = {name: fam for fam, names in FAMILY.items() for name in names if len(name) > 2}
    for text in texts:
        up = text.upper()
        # "A. GRAVES", "J. DIGGS", "C. MOORE", "DR. MOORE", "AMOS GRAVES" ...
        for first, surname in re.findall(r"\b([A-Z]+)\.? (GRAVES|DIGGS|MOORE|HOLLOW)\b", up):
            if first in firsts or len(first) == 1 or first == "DR":
                assert first in FAMILY[surname], (text, first, surname)
        # ... and a first name never turns up with another family's surname.
        for first, fam in firsts.items():
            for other in re.findall(rf"\b{first}\.? (GRAVES|DIGGS|MOORE|HOLLOW)\b", up):
                assert other == fam, (text, first, other)


def test_every_date_is_a_date_the_story_has(texts) -> None:
    """No date after the night the clocks stopped, none before the founding,
    and every day-month-year date is the Founder's death or that night."""
    for text in texts:
        for year in re.findall(r"\b(1[89]\d\d)\b", text):
            assert STORY["founded"] <= int(year) <= 1897, (text, year)
        for date in re.findall(r"\b\d{1,2} [A-Z]{3} \d{4}\b", text.upper()):
            assert date in (STORY["declared_dead"], STORY["night"]), (text, date)


def test_the_night_matches_everywhere_it_is_written() -> None:
    night, time = STORY["night"], STORY["time"]
    # The ones who died that night say so, to the minute.
    for key in ("return", "diet"):
        assert f"{night}, {time}" in _lines(EPITAPHS, key), key
    # The groundskeeper's memorial and his log carry the date.
    assert night in _lines(EPITAPHS, "back_soon")
    assert night in _lines(NOTICE_LINES, "shift_log")
    # The hymn board is the same date as numbers.
    day, month, year = night.split()
    assert f"{int(day)}, {MONTHS[month]}, {year}" in _lines(NOTICE_LINES, "chapel_hymns")
    # The gate's clock stopped at that minute (the round-end PA that repeated
    # it is gone, P13/P17).
    assert time in _lines(NOTICE_LINES, "gate")


def test_each_family_tomb_names_its_own_family() -> None:
    tombs = {key for key, *_ in MAUSOLEUMS} | {key for key, *_ in ROW_TOMBS}
    for family, where in STORY["families"].items():
        key = "vault" if where == "vault" else family.lower()
        table = NOTICE_LINES if where == "vault" else EPITAPHS
        assert key in table, family
        assert family in _lines(table, key) or family in table[key][0].upper(), family
        if where != "vault":
            assert key in tombs, family
    for key, family, *_ in MAUSOLEUMS:
        assert family == key.upper() and family in EPITAPHS[key][0]
    # The family plots name their family.
    assert "GRAVES" in _lines(NOTICE_LINES, "graves_plot")
    assert "MOORE" in _lines(NOTICE_LINES, "moore_plot")


def test_the_cast_is_who_the_story_says() -> None:
    founder, keeper, digger = STORY["founder"], STORY["groundskeeper"], STORY["gravedigger"]
    assert founder in _lines(EPITAPHS, "founder") and founder in _lines(NOTICE_LINES, "sarcophagus")
    assert str(STORY["founded"]) in _lines(EPITAPHS, "founder")
    assert STORY["declared_dead"] in _lines(EPITAPHS, "founder")
    assert keeper in _lines(EPITAPHS, "back_soon")
    assert keeper.split()[0] in _lines(EPITAPHS, "graves")  # his empty shelf
    assert digger.split()[0] in _lines(EPITAPHS, "diggs")  # the one Diggs not at home
    assert STORY["doctor"] in _lines(EPITAPHS, "moore")
    assert STORY["nurse"] in _lines(EPITAPHS, "diet") and STORY["nurse"] in EPITAPHS["diet"][0]


def test_the_quest_tells_the_same_story(built) -> None:
    quest = built[1]["quest"]
    initials = ".".join(w[0] for w in STORY["groundskeeper"].split()) + "."
    assert initials in quest.steps[0].done  # the note in the grave is his
    boss = next(s.boss for s in quest.steps if s.key == "gravedigger")
    first, surname = STORY["gravedigger"].title().split()
    assert f"{first} {surname}" in boss.arrives
    # Steps and rounds are the quest's; this file only checks the words.
    # "graves": the soul-box step at the fresh graves (quest.SoulBox)
    assert [s.key for s in quest.steps] == ["dig", "wisps", "founder", "coffin",
                                            "graves", "gravedigger", "dawn"]


def test_the_open_grave_was_dug_for_the_groundskeeper() -> None:
    hint = _lines(EPITAPHS, "reserved")
    m = re.search(r"(\w+) LETTERS\. IT BEGAN WITH (\w)", hint)
    name = STORY["groundskeeper"].split()[0]
    assert m and len(name) == {"FOUR": 4}[m.group(1)] and name.startswith(m.group(2))


def test_every_line_fits_on_screen() -> None:
    for key, (prompt, lines) in {**EPITAPHS, **NOTICE_LINES}.items():
        for line in lines:
            assert len(line) <= 84, (key, len(line))


# --------------------------------------------------------------------------
# Where the lore stands
# --------------------------------------------------------------------------
def _room_of(bp, p) -> str:
    rooms = [r.id for r in bp.elements(Room) if r.interior.holds_flat(p.x, p.y)]
    assert len(rooms) == 1, (p, rooms)
    return rooms[0]


def _centre(bp, prefix: str) -> tuple[float, float]:
    for m in bp.elements(Massing):
        if m.id.startswith(prefix):
            b = _solid_bounds(m.solids[0])
            return (b.mins.x + b.maxs.x) / 2.0, (b.mins.y + b.maxs.y) / 2.0
    raise AssertionError(prefix)


def test_every_lore_readable_is_placed_in_its_room(built) -> None:
    bp, extras = built
    f = extras["features"]
    where = {"amos": "gate_room", "shift_log": "shed_room", "graves_plot": "gate_room",
             "moore_plot": "hills_room", "returned_plot": "hills_room"}
    for key in LORE_EPITAPHS:
        assert _room_of(bp, f["epitaphs"][key]) == where[key]
    for key in LORE_NOTICES:
        assert _room_of(bp, f["notices"][key]) == where[key]
    # The outdoor ones stand off the paths.
    for key in ("amos", "graves_plot", "moore_plot", "returned_plot"):
        x, y = _centre(bp, f"lore_{key}")
        assert clear_of_paths(x, y, 14.0), key


def test_the_log_leads_to_amoss_grave(built) -> None:
    """The log says: by the dead oak, gate lawn, south-west.  It is."""
    bp, extras = built
    log = _lines(NOTICE_LINES, "shift_log")
    # P17: a clue to piece together, not directions.
    assert "DEAD OAK" in log and "GATE" in log
    x, y = _centre(bp, "lore_amos_tablet")
    gate = bp.find("gate_room").interior
    assert x < (gate.mins.x + gate.maxs.x) / 2.0 and y < (gate.mins.y + gate.maxs.y) / 2.0
    # The dead trees are models (cemetery_dressing._trees:
    # one scatter per tree, ``dress_gate_gate_tree<n>``, trunk at the origin).
    from zmforge.blueprint.elements import PropScatter

    trunks = [s.props[0].origin for s in bp.elements(PropScatter)
              if "_gate_tree" in s.id and s.props]
    assert trunks
    near = min(math.dist((x, y), (t.x, t.y)) for t in trunks)
    assert near <= 150.0, near
    # Amos's stone has his initials, and nothing on screen names it.
    assert "A.G." in _lines(EPITAPHS, "amos")
    assert "AMOS" not in EPITAPHS["amos"][0].upper()


def test_the_family_plots_hold_the_right_family(built) -> None:
    bp, _ = built
    # GRAVES: at the fenced plot by the gate.
    gx, gy = _centre(bp, "lore_graves_plot_post")
    assert -1290.0 - 120.0 <= gx <= -1060.0 + 120.0 and 330.0 - 120.0 <= gy <= 490.0 + 120.0
    # MOORE: "they are behind you" -- behind (west of) the east-facing Moore tomb.
    _, _, mx, my, facing, _ = next(m for m in MAUSOLEUMS if m[0] == "moore")
    assert facing is Facing.EAST
    px, py = _centre(bp, "lore_moore_plot_post")
    assert px < mx - 150.0 and math.dist((px, py), (mx, my)) <= 450.0
    # The returned: the fenced plot beside the Founder's needle.
    rx, ry = _centre(bp, "lore_returned_plot_post")
    assert 940.0 - 120.0 <= rx <= 1100.0 + 120.0 and -340.0 - 120.0 <= ry <= -170.0 + 120.0
    assert math.dist((rx, ry), FOUNDER_NEEDLE[:2]) <= 700.0
    # The grave dug for Amos is the one the quest digs.
    grave = built[1]["features"]["open_grave"]
    assert math.dist(OPEN_GRAVE[:2], (grave.x, grave.y)) < 1.0
