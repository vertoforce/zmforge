"""The measured half of the design review: one map, as numbers and strings.

:func:`generate` builds a recipe into a scratch tools root (the same
``Project.commit`` a real generate runs, so the check results are the real
ones) while recording the quest and the use notices the recipe installs.
:func:`collect` turns that into a JSON-able dict:

* ``rooms``: one entry per room with its bounds, materials, openings, fixtures,
  interactives, notices, quest triggers and **every prop** (model, position
  relative to the room, gap to the nearest wall and opening, what it stands
  on), plus a numeric ``scorecard``;
* ``map``: essentials, the door graph with the cheapest way into each zone,
  the quest and boss, every on-screen string, text issues and the check
  results.

Every threshold is a module constant so a reader of a scorecard can find what
"hugs the wall" meant.  World units are the game's (roughly an inch).
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import heapq
import math
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: A floor prop whose footprint edge is this close to a wall "hugs" it.
WALL_BAND = 24.0
#: A floor prop at least this far from every wall stands "in the middle".
MIDDLE_BAND = 64.0
#: Floor either side of an opening a solid prop should keep out of (Z53's 48).
DOOR_BAND = 48.0
#: A solid prop lower than this over the floor is a step, not an obstacle.
STEP_HEIGHT = 18.0
#: Use triggers this close to a purchase fight it for the prompt.
PURCHASE_CLEARANCE = 80.0
#: The fewest props an indoor room should carry (map-principles P2).  A floor,
#: not a band: more is better up to the engine ceilings below.
DENSITY_FLOOR = 100
#: ...scaled by floor area: this many props per 1,000,000 square units (about a
#: 1000 x 1000 room) in a room of ``BIG_ROOM_K2`` (0.5 k2) or more: 40% of the
#: stock non-trim density, the same bar as ``S2`` (a lower bar passes big
#: rooms at 13-33% of stock).
DENSITY_PER_MILLION_SQ_UNITS = 459
#: ...and in a smaller room, a quarter of stock (``S2``'s ``WARN_SHARE``).
DENSITY_PER_MILLION_SMALL = 287
#: Engine ceilings, measured: 25,000 and 39,975 props compiled,
#: baked and linked with no limit line (a probe; 9,017 in an earlier build; stock zm_giant carries
#: about 21,000); shadowing omni lights past 340 lose their shadow at the bake.
#: The only upper bounds on dressing.  Frame rate at these counts is unmeasured,
#: so the ceiling stays at 32,000 (the corn maze vignette pass,
#: carries about 30,800), well under the 39,975 that linked.
PROP_CEILING = 32000
SHADOW_LAMP_CEILING = 340
#: Floor litter (``recipes.props.is_litter`` lying on the floor) counts toward
#: the density floor only while it is at most this share of the counted
#: props, i.e. one piece of litter per three real props (P2: litter is
#: seasoning, not the meal).  Litter past that is measured
#: but not counted, so scattering paper cannot carry a room over its floor.
LITTER_SHARE_CAP = 0.25
#: How far above its support a prop may start and still stand on it.
SIT_SLACK = 4.0
#: A floor-mounted prop more than this over the highest thing under it floats.
FLOAT_GAP = 8.0
#: Units per foot, for the square-feet figure (one unit is about an inch).
UNITS_PER_FOOT = 12.0

#: The use key, as a prompt spells it for the engine to substitute.
USE_KEY = re.compile(r"\[\{\+(activate|usereload)\}\]")
_PLACEHOLDER = re.compile(
    r"\b(TODO|FIXME|XXX|TBD|lorem|ipsum|placeholder|changeme|foo|asdf)\b"
    r"|%[sd]|\{[a-z_]+\}|<[a-z_]+>",
    re.IGNORECASE,
)
_DOUBLED = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.IGNORECASE)
_CODES = re.compile(r"\^\d|\[\{\+[a-z_]+\}\]|&&\d")
_WORD = re.compile(r"[A-Za-z][A-Za-z']+")
#: Genre words a general dictionary lacks; never reported as typos.
GAME_WORDS = frozenset({
    "undead", "zombie", "zombies", "perk", "perks", "juggernog", "revive", "respawn",
    "powerup", "powerups", "headshot", "headshots", "stamin", "deadshot", "wunderfizz",
    "scarecrow", "scarecrows", "hayride", "ossuary", "gravedigger", "minion", "minions",
})
_DICT_PATHS = ("/usr/share/dict/words", "/usr/share/dict/american-english")

from ..localtools import tools_dir as _local_tools_dir  # noqa: E402

STOCK_TABLE = Path("share/raw/gamedata/weapons/zm/zm_levelcommon_weapons.csv")
LOCAL_STOCK_TABLE = _local_tools_dir() / STOCK_TABLE  # $ZMFORGE_WINE_TOOLS


# ----------------------------------------------------------------------
# Generating, and recording what the recipe installs
# ----------------------------------------------------------------------
@dataclass
class Generated:
    """A recipe built and committed into a scratch tools root."""

    recipe: str
    name: str
    blueprint: Any
    quests: list = field(default_factory=list)
    notices: list = field(default_factory=list)
    report: Any = None
    paths: Mapping[str, Path] = field(default_factory=dict)
    root: Path | None = None


def default_map_name(recipe: str) -> str:
    return "zm_" + recipe.replace("-", "_")


@contextlib.contextmanager
def _recording():
    """Record every quest and use notice a recipe installs, then undo.

    Recipes import ``install_quest``/``use_notices`` by name as well as through
    their module, so every loaded ``zmforge`` module holding the original
    function object gets the recording wrapper for the duration.
    """
    from ..script import quest as quest_module
    from ..script import tricks

    quests: list = []
    notices: list = []
    original_quest = quest_module.install_quest
    original_notices = tricks.use_notices

    def install_quest(bp, quest, *a, **k):
        quests.append(quest)
        return original_quest(bp, quest, *a, **k)

    def use_notices(items, *a, **k):
        items = list(items)
        notices.extend(items)
        return original_notices(items, *a, **k)

    swaps = {id(original_quest): install_quest, id(original_notices): use_notices}
    patched: list[tuple[object, str, object]] = []
    for mod_name, module in list(sys.modules.items()):
        if not mod_name.startswith("zmforge") or module is None:
            continue
        for attr, value in list(vars(module).items()):
            if id(value) in swaps and value in (original_quest, original_notices):
                patched.append((module, attr, value))
                setattr(module, attr, swaps[id(value)])
    try:
        yield quests, notices
    finally:
        for module, attr, value in patched:
            setattr(module, attr, value)
        # A module first imported while the wrappers were in place took the
        # wrapper by name; hand it the original too.
        undo = {id(install_quest): original_quest, id(use_notices): original_notices}
        for mod_name, module in list(sys.modules.items()):
            if not mod_name.startswith("zmforge") or module is None:
                continue
            for attr, value in list(vars(module).items()):
                if id(value) in undo and value in (install_quest, use_notices):
                    setattr(module, attr, undo[id(value)])


def _seed_stock_table(root: Path) -> None:
    """The stock weapon table a priced map overlays (see ``zmforge build``)."""
    target = root / STOCK_TABLE
    target.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_STOCK_TABLE.is_file():
        shutil.copy(LOCAL_STOCK_TABLE, target)
        return
    from ..blueprint.catalogue import LEVEL_WEAPONS
    from ..emit.weapons import COST_COLUMN, NAME_COLUMN, WEAPON_TABLE_COLUMNS

    rows = [",".join(WEAPON_TABLE_COLUMNS)]
    for weapon in sorted(LEVEL_WEAPONS):
        cells = [""] * len(WEAPON_TABLE_COLUMNS)
        cells[NAME_COLUMN] = weapon
        cells[COST_COLUMN] = "1"
        cells[WEAPON_TABLE_COLUMNS.index("upgrade_name")] = f"{weapon}_upgraded"
        cells[WEAPON_TABLE_COLUMNS.index("in_box")] = "TRUE"
        rows.append(",".join(cells))
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_blueprint(recipe: str, name: str | None = None):
    """The recipe's blueprint, plus the quests and notices it installed."""
    from ..facade.cli import RECIPES

    with _recording() as (quests, notices):
        bp = RECIPES[recipe](name or default_map_name(recipe))
    return bp, quests, notices


def generate(recipe: str, name: str | None = None, *, scratch: Path | None = None,
             keep: bool = False) -> Generated:
    """Build *recipe* and commit it into a scratch tools root.

    The scratch root is deleted afterwards unless *keep*; the server script's
    text is read before that so inline strings can still be listed.
    """
    from ..project import Project

    name = name or default_map_name(recipe)
    bp, quests, notices = build_blueprint(recipe, name)
    root = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="zmforge-review-"))
    root.mkdir(parents=True, exist_ok=True)
    _seed_stock_table(root)
    project = Project.create(name, root, blueprint=bp, overwrite=True)
    result = project.commit(force=True, loading_screen=False)
    paths = dict(project.paths())
    generated = Generated(recipe, name, bp, quests, notices, result.report, paths, root)
    server = paths.get("server_script")
    generated.server_text = (  # type: ignore[attr-defined]
        Path(server).read_text(encoding="utf-8", errors="replace")
        if server and Path(server).is_file() else ""
    )
    if not keep and scratch is None:
        shutil.rmtree(root, ignore_errors=True)
        generated.root = None
    return generated


# ----------------------------------------------------------------------
# Text checks
# ----------------------------------------------------------------------
_dictionary: frozenset[str] | None = None


def _words() -> frozenset[str]:
    global _dictionary
    if _dictionary is None:
        words: set[str] = set()
        for path in _DICT_PATHS:
            p = Path(path)
            if p.is_file():
                words |= {w.strip().lower() for w in p.read_text(errors="ignore").split()}
                break
        _dictionary = frozenset(words)
    return _dictionary


def _edits1(word: str) -> Iterable[str]:
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    for a, b in splits:
        if b:
            yield a + b[1:]
            for c in letters:
                yield a + c + b[1:]
        if len(b) > 1:
            yield a + b[1] + b[0] + b[2:]
        for c in letters:
            yield a + c + b


def _known(word: str, words: frozenset[str]) -> bool:
    w = word.lower().strip("'")
    if w in words:
        return True
    for suffix in ("'s", "s", "es", "ed", "ing", "d", "er", "ers", "ly"):
        if w.endswith(suffix) and w[: -len(suffix)] in words:
            return True
    return False


def spelling_suspects(text: str, *, ignore: Iterable[str] = ()) -> list[str]:
    """Words one edit away from a dictionary word and not in it: likely typos.

    Deliberately narrow: a made-up brand name or an acronym is not one edit
    from a real word, so it is not reported.  Returns ``"word->guess"``.
    """
    words = _words()
    if not words:
        return []
    skip = {w.lower() for w in ignore} | GAME_WORDS
    found = []
    for word in _WORD.findall(_CODES.sub(" ", text)):
        low = word.lower().strip("'")
        if len(low) < 5 or low in skip or word.isupper() and len(word) <= 5:
            continue
        if _known(low, words):
            continue
        guesses = sorted({e for e in _edits1(low) if e in words and len(e) >= 4})
        if guesses:
            found.append(f"{word}->{guesses[0]}")
    return found


def text_issues(text: str, *, prompt: bool = False, ignore: Iterable[str] = ()) -> list[str]:
    """Mechanical problems with one on-screen line.

    ``prompt`` marks a line shown on a use trigger, which must name the use key.
    """
    issues = []
    if prompt and not USE_KEY.search(text):
        issues.append("prompt does not name the use key ([{+activate}])")
    for match in _PLACEHOLDER.finditer(text):
        issues.append(f"placeholder text {match.group(0)!r}")
    for match in _DOUBLED.finditer(_CODES.sub(" ", text)):
        issues.append(f"doubled word {match.group(0)!r}")
    if "  " in text:
        issues.append("double space")
    if re.search(r"\^(?!\d)", text):
        issues.append("stray ^ colour code")
    for suspect in spelling_suspects(text, ignore=ignore):
        issues.append(f"possible typo {suspect}")
    return issues


# ----------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------
@dataclass
class Area:
    key: str
    room_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    floor_z: float
    ceiling_z: float
    room: Any = None

    def holds(self, x: float, y: float, slack: float = 0.0) -> bool:
        return (self.x0 - slack <= x <= self.x1 + slack
                and self.y0 - slack <= y <= self.y1 + slack)

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def rel(self, x: float, y: float, z: float | None = None) -> list[float]:
        out = [round(x - self.x0), round(y - self.y0)]
        if z is not None:
            out.append(round(z - self.floor_z))
        return out

    def wall_gap(self, bx0: float, by0: float, bx1: float, by1: float) -> tuple[float, str]:
        gaps = {"west": bx0 - self.x0, "east": self.x1 - bx1,
                "south": by0 - self.y0, "north": self.y1 - by1}
        side = min(gaps, key=gaps.get)
        return gaps[side], side


def _rect_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _xyz(value) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if hasattr(value, "x") and hasattr(value, "y"):
        return (float(value.x), float(value.y), float(getattr(value, "z", 0.0)))
    if (isinstance(value, (tuple, list)) and len(value) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        return (float(value[0]), float(value[1]), float(value[2]))
    return None


def _areas(bp) -> list[Area]:
    from ..blueprint.elements import Room, Zone
    from ..placement.audit import _zone_named

    zones = bp.elements(Zone)
    out = []
    for room in bp.elements(Room):
        i = room.interior
        key = _zone_named(room, zones)
        # A zone may own several rooms (corn maze: two volumes a zone); each
        # room after the first is its own area, or its props count twice.
        if any(a.key == key for a in out):
            key = f"{key} ({room.id})"
        out.append(Area(key, room.id, i.mins.x, i.mins.y,
                        i.maxs.x, i.maxs.y, room.floor_z,
                        room.shell.ceiling_underside_z, room))
    return out


def _area_of(areas: Sequence[Area], x: float, y: float, z: float | None = None,
             slack: float = 0.0) -> Area | None:
    best, best_dz = None, math.inf
    for area in areas:
        if not area.holds(x, y, slack):
            continue
        dz = 0.0 if z is None else (
            0.0 if area.floor_z - 8 <= z <= area.ceiling_z else
            min(abs(z - area.floor_z), abs(z - area.ceiling_z)))
        if dz < best_dz:
            best, best_dz = area, dz
    return best


def _material_name(material) -> str:
    return str(getattr(material, "name", material))


# ----------------------------------------------------------------------
# Props
# ----------------------------------------------------------------------
@dataclass
class PropFact:
    id: str
    model: str
    x: float
    y: float
    z: float
    yaw: float
    scale: float
    solid: bool
    mount: str = "floor"
    bounds: tuple[float, float, float, float] | None = None  # footprint in plan
    z_low: float | None = None
    z_high: float | None = None
    area: Area | None = None
    sits_on: str = "?"
    float_gap: float = 0.0
    wall_gap: float | None = None
    wall_side: str = ""
    door_gap: float | None = None
    door: str = ""


def _props(bp, areas: Sequence[Area]) -> list[PropFact]:
    from ..blueprint.elements import PropScatter
    from ..placement.audit import layout_from_blueprint

    layout = layout_from_blueprint(bp)
    placed = {p.ident: p for p in layout.props if p.ident}
    out: list[PropFact] = []
    for scatter in bp.elements(PropScatter):
        for index, prop in enumerate(scatter.props):
            ident = prop.id or f"{scatter.id}_{index}"
            fact = PropFact(ident, prop.model, prop.origin.x, prop.origin.y, prop.origin.z,
                            float(prop.yaw), float(prop.scale), bool(prop.solid))
            p = placed.get(prop.id)
            if p is not None:
                fact.bounds = p.footprint.bounds
                fact.z_low, fact.z_high = p.z_low, p.z_high
                kind = layout.mounts.get(p.name)
                fact.mount = kind.value if isinstance(kind, Enum) else "floor"
                cx, cy = (fact.bounds[0] + fact.bounds[2]) / 2, (fact.bounds[1] + fact.bounds[3]) / 2
            else:
                fact.mount = "unmeasured"
                cx, cy = fact.x, fact.y
            fact.area = _area_of(areas, cx, cy, fact.z_low if fact.z_low is not None else fact.z)
            out.append(fact)
    _supports(out, layout, areas)
    return out


def _supports(props: Sequence[PropFact], layout, areas: Sequence[Area]) -> None:
    """Fill ``sits_on``: the highest thing under a prop's footprint centre."""
    tops: list[tuple[tuple[float, float, float, float], float, str]] = []
    for surface in layout.surfaces:
        tops.append((surface.poly.bounds, surface.top_z, f"fixture {surface.name}"))
    for ground in layout.ground:
        tops.append((ground.poly.bounds, ground.top_z, "floor"))
    from ..recipes.props import SEAT_TOP

    for prop in props:
        if prop.bounds is not None and prop.z_high is not None:
            tops.append((prop.bounds, prop.z_high, f"prop {prop.id} ({prop.model})"))
            # A chair's seat is a surface too: what is sat on it (a customer,
            # a teddy, a pillow) stands on the seat, below the chair's back.
            seat = SEAT_TOP.get(prop.model)
            if seat is not None and prop.z_low is not None:
                tops.append((prop.bounds, prop.z_low + seat,
                             f"prop {prop.id} ({prop.model}) seat"))
            # A shelving unit's boards are surfaces too (props.SHELF_BOARDS,
            # the same `layout.shelves` share map placement/audit.py's own
            # float check reads), or a book set on an inner board reads as
            # floating over the floor -- it is really resting on the board.
            if prop.z_low is not None:
                for share in layout.shelves.get(prop.model, ()):
                    board_z = prop.z_low + (prop.z_high - prop.z_low) * share
                    tops.append((prop.bounds, board_z, f"prop {prop.id} ({prop.model}) shelf"))
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (b, _, _) in enumerate(tops):
        for i in range(int(b[0] // 256), int(b[2] // 256) + 1):
            for j in range(int(b[1] // 256), int(b[3] // 256) + 1):
                buckets[(i, j)].append(index)
    for prop in props:
        if prop.mount in ("wall", "ceiling"):
            prop.sits_on = f"{prop.mount}-mounted"
            continue
        if prop.bounds is None or prop.z_low is None:
            prop.sits_on = "unmeasured"
            continue
        cx, cy = (prop.bounds[0] + prop.bounds[2]) / 2, (prop.bounds[1] + prop.bounds[3]) / 2
        own = f"prop {prop.id} ("
        best: tuple[float, str] | None = None
        #: The floor (ground or terrain) over the prop's base at its centre: a
        #: model seated on the lowest ground under its footprint on a slope is
        #: part buried there, not floating over the next thing down.
        buried: float | None = None
        for index in buckets.get((int(cx // 256), int(cy // 256)), ()):
            b, top, what = tops[index]
            if what.startswith(own):
                continue
            if not (b[0] <= cx <= b[2] and b[1] <= cy <= b[3]):
                continue
            if top > prop.z_low + SIT_SLACK:
                if what == "floor":
                    buried = top if buried is None else max(buried, top)
                continue
            if best is None or top > best[0]:
                best = (top, what)
        if buried is not None and (best is None or buried > best[0]):
            best = (buried, "floor (base part buried on a slope)")
        if best is None:
            prop.sits_on = "nothing measured under it"
            continue
        prop.sits_on = best[1]
        prop.float_gap = round(prop.z_low - best[0], 1)


def _openings(bp, areas: Sequence[Area]) -> dict[str, list[tuple[str, tuple[float, float, float, float], dict]]]:
    """Every doorway, per area: bought doors and free openings alike."""
    from ..blueprint.elements import Door, Room

    doors = []
    for door in bp.elements(Door):
        b = door.box
        doors.append((door.id, (b.mins.x, b.mins.y, b.maxs.x, b.maxs.y),
                      {"price": door.price, "electric": door.electric,
                       "requires_power": door.requires_power,
                       "zones": [door.zone_a, door.zone_b]}))
    free = []
    for room in bp.elements(Room):
        for index, b in enumerate(room.aperture_boxes):
            rect = (b.mins.x, b.mins.y, b.maxs.x, b.maxs.y)
            if any(_rect_gap(rect, d[1]) <= 8.0 for d in doors):
                continue
            ap = room.apertures[index] if index < len(room.apertures) else None
            sill = getattr(ap, "sill", 0.0) if ap else 0.0
            free.append((f"{room.id}.opening{index}", rect,
                         {"free": True, "sill": sill, "width": getattr(ap, "width", None)}))
    out: dict[str, list] = {a.key: [] for a in areas}
    for name, rect, info in doors + free:
        for area in areas:
            if _rect_gap(rect, (area.x0, area.y0, area.x1, area.y1)) <= 24.0:
                if not any(o[0] == name for o in out[area.key]):
                    out[area.key].append((name, rect, info))
    return out


def _measure_props(props: Sequence[PropFact], openings) -> None:
    for prop in props:
        if prop.area is None:
            continue
        b = prop.bounds or (prop.x, prop.y, prop.x, prop.y)
        prop.wall_gap, prop.wall_side = prop.area.wall_gap(*b)
        best = None
        for name, rect, _info in openings.get(prop.area.key, ()):
            gap = _rect_gap(b, rect)
            if best is None or gap < best[0]:
                best = (gap, name)
        if best is not None:
            prop.door_gap, prop.door = round(best[0]), best[1]


# ----------------------------------------------------------------------
# Interactives, notices, quest
# ----------------------------------------------------------------------
def _interactives(bp) -> list[dict]:
    from ..blueprint.elements import (Door, Machine, MysteryBox, PowerSwitch, Wunderfizz,
                                      WallWeapon, Window)

    prices = {}
    try:
        prices = bp.weapon_price_table()
    except Exception:  # pragma: no cover - a recipe with no table
        prices = {}
    out = []
    # Use triggers a recipe wires through custom logic (a ticket dispenser,
    # say) are invisible to the element walk below; a recipe lists them on
    # ``bp.review_interactives`` so the review does not report them missing.
    for extra in getattr(bp, "review_interactives", ()) or ():
        out.append(dict(extra))
    # P14: the model a machine shows, next to the name the player reads.
    custom_names = {c.slug: c.name for c in getattr(bp, "custom_perks", ()) or ()}
    for m in bp.elements(Machine):
        slug = m.perk.slug
        kind = "pack_a_punch" if slug == "pack_a_punch" else "perk"
        model = (m.perk.xmodel if m.perk.xmodel
                 else f"stock prefab {m.perk.prefab}" if m.perk.prefab else None)
        out.append({"id": m.id, "kind": kind, "what": slug,
                    "name": custom_names.get(slug, f"stock {slug}"), "model": model,
                    "at": _xyz(m.position), "purchase": True})
    from ..blueprint.catalogue import wall_weapon_weapon
    from ..emit.strings import weapon_prompt

    stock = _stock_prices()
    for w in bp.elements(WallWeapon):
        weapon = wall_weapon_weapon(w.slug) or w.slug
        price = w.price if w.price is not None else prices.get(weapon)
        out.append({"id": w.id, "kind": "wall_buy", "what": weapon,
                    "price": price if price is not None else stock.get(weapon),
                    "price_source": "map" if price is not None else "stock table",
                    # what the player reads: the map's name inside the
                    # framework's "Hold [use] to buy ... [Cost: n]" line
                    "prompt": weapon_prompt(bp.weapon_prompts[weapon]).replace(
                        "&&1", str(price if price is not None else stock.get(weapon)))
                    if weapon in bp.weapon_prompts
                    else "(stock weapon name, in the stock Hold [use] to buy ... [Cost] line)",
                    "at": _xyz(w.position), "purchase": True})
    for box in bp.elements(MysteryBox):
        out.append({"id": box.id, "kind": "mystery_box", "price": box.price,
                    "starting": box.starting, "at": _xyz(box.position), "purchase": True})
    for wf in bp.elements(Wunderfizz):
        out.append({"id": wf.id, "kind": "wunderfizz", "at": _xyz(wf.position), "purchase": True})
    for ps in bp.elements(PowerSwitch):
        out.append({"id": ps.id, "kind": "power_switch", "at": _xyz(ps.position), "purchase": True})
    for window in bp.elements(Window):
        out.append({"id": window.id, "kind": "barrier", "zone": window.zone_name,
                    "at": _xyz(window.barricade_origin), "purchase": True})
    for door in bp.elements(Door):
        c = door.box.centre
        out.append({"id": door.id, "kind": "door", "price": door.price,
                    "electric": door.electric, "requires_power": door.requires_power,
                    "zones": [door.zone_a, door.zone_b],
                    "at": (c.x, c.y, door.box.mins.z), "purchase": True})
    return out


def _stock_prices() -> dict[str, int]:
    """Treyarch's wall-buy prices from the local install's table, if present."""
    from ..emit.weapons import COST_COLUMN, NAME_COLUMN

    out: dict[str, int] = {}
    if not LOCAL_STOCK_TABLE.is_file():
        return out
    for line in LOCAL_STOCK_TABLE.read_text(errors="ignore").splitlines()[1:]:
        cells = line.split(",")
        try:
            out[cells[NAME_COLUMN]] = int(cells[COST_COLUMN])
        except (IndexError, ValueError):
            continue
    return out


def _string_lookup(bp) -> dict[str, tuple[str, str, str]]:
    """Asset name -> (reference, text, kind)."""
    from ..emit.strings import asset_name

    kinds = {asset: kind for kind, asset in bp.script.map_strings}
    out = {}
    for ref, text in bp.map_strings.items():
        asset = asset_name(bp.name, ref)
        out[asset] = (ref, text, kinds.get(asset, "string"))
    return out


def _notices(bp, notices, lookup) -> list[dict]:
    out = []
    for origin, prompt, replies in notices:
        ref, text, _ = lookup.get(prompt, (prompt, prompt, "triggerstring"))
        out.append({
            "id": ref, "at": _xyz(origin), "prompt": text,
            "replies": [lookup.get(r, (r, r, ""))[1] for r in replies],
        })
    return out


def _jsonable(value, points: list, label: str) -> Any:
    """A quest object as plain JSON, gathering every point it names."""
    xyz = _xyz(value) if isinstance(value, (tuple, list)) else None
    if xyz is not None:
        points.append((label, xyz))
        return {"point": label}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out = {"type": type(value).__name__}
        for f in dataclasses.fields(value):
            v = getattr(value, f.name)
            if v is None or v == () or v == []:
                continue
            out[f.name] = _jsonable(v, points, f"{label}.{f.name}")
        return out
    if isinstance(value, (tuple, list)):
        return [_jsonable(v, points, f"{label}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _perk_facts(bp, perk) -> dict:
    """A custom perk as JSON, plus whether this map ships its HUD icon's image.

    The icon slot's own ``evidence`` says the install has no image under that
    name, which is true of the install and was read as "the icon is blank".
    When the map packs its own image under the name (``Blueprint.hud_images``,
    declared ``image,<name>`` in the zone), the icon is not blank, so say so.
    """
    out = _jsonable(perk, [], "perk")
    icon = getattr(perk, "icon", None)
    if icon is None:
        out["hud_icon"] = "none: this perk takes no HUD slot"
        return out
    shipped = icon.image in (getattr(bp, "hud_images", None) or {})
    declared = any(
        getattr(ref, "line", "") == f"image,{icon.image}" for ref in getattr(bp, "assets", ())
    )
    out["hud_icon_image_shipped_by_map"] = bool(shipped and declared)
    out["hud_icon"] = (
        f"shipped: this map packs its own image {icon.image!r} "
        f"(texture_assets/zmforge_hud/{bp.name}/{icon.image}.png, image,{icon.image} in the zone), "
        "so the slot draws it even though the stock install has none"
        if shipped and declared
        else f"blank: no image {icon.image!r} on the install and this map ships none"
    )
    return out


def _quest_facts(quests, areas, flood, props: Sequence[PropFact] = ()) -> tuple[list[dict], list[dict]]:
    """The quests as JSON and every point they name, located and checked.

    Each point also names the props nearest it (P14): a step that aims at a
    prop the map already places has no model of its own to judge.
    """
    out, located = [], []
    for quest in quests:
        points: list[tuple[str, tuple[float, float, float]]] = []
        body = _jsonable(quest, points, quest.key)
        use = {tuple(p) for p in quest.use_points()}
        for label, (x, y, z) in points:
            area = _area_of(areas, x, y, z, slack=24.0)
            entry = {"label": label, "room": area.key if area else "outside",
                     "rel": area.rel(x, y, z) if area else [round(x), round(y), round(z)],
                     "use_trigger": (x, y, z) in use}
            if flood is not None and area is not None:
                entry["reachable"] = _reachable(flood, x, y, area.floor_z)
            near = sorted(((math.hypot(p.x - x, p.y - y), p) for p in props
                           if abs(p.x - x) < 64 and abs(p.y - y) < 64 and abs(p.z - z) < 128),
                          key=lambda t: t[0])
            entry["nearest_props"] = [[p.id, p.model, round(d)] for d, p in near[:2] if d < 64]
            located.append(entry)
        out.append(body)
    return out, located


def _reachable(flood, x: float, y: float, floor_z: float) -> str:
    """Is there spawn-reached floor at, or within 64 units of, this point?"""
    if flood.under(x, y, floor_z + 4.0, only_reached=True) is not None:
        return "yes"
    for r in (32.0, 64.0):
        for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, -r), (r, -r), (-r, r)):
            if flood.under(x + dx, y + dy, floor_z + 4.0, only_reached=True) is not None:
                return f"within {int(r)}"
    return "no"


# ----------------------------------------------------------------------
# Progression
# ----------------------------------------------------------------------
def _player_facts(bp) -> dict:
    """How many players the map seats (the initial-spawn slots) and whether
    it lifts the stock scripts' four-player check for the rest."""
    from ..blueprint.elements import PlayerStart

    starts = bp.elements(PlayerStart)
    slots = starts[0].slots if starts else None
    lifted = bool(getattr(bp.script, "lift_player_cap", False))
    return {
        "slots": slots,
        "script_player_cap_lifted": lifted,
        "note": ("slots is the number of players this build seats, one initial spawn each; "
                 + ("above four the map lifts the stock four-player check "
                    "(ScriptPlan.lift_player_cap), so slots 5 and up are real seats for "
                    "players 5 and up, not dead content"
                    if lifted else "a stock game seats four")),
    }


def _engine_limits(bp, props: int) -> dict:
    """The map's totals against the only upper bounds on dressing (P2)."""
    from ..blueprint.elements import Lamp

    lamps = list(bp.elements(Lamp))
    shadowing = sum(1 for lamp in lamps if lamp.shadows)
    return {
        "props": props, "prop_ceiling": PROP_CEILING,
        "lamps": len(lamps), "shadowing_lamps": shadowing,
        "shadowing_lamp_ceiling": SHADOW_LAMP_CEILING,
        "over": [name for name, n, cap in (("props", props, PROP_CEILING),
                                          ("shadowing_lamps", shadowing, SHADOW_LAMP_CEILING))
                 if n > cap],
    }


def _progression(bp, areas: Sequence[Area], openings) -> dict:
    """Cheapest points to open a way into every zone from the start."""
    from ..blueprint.elements import Door, Zone

    edges: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for door in bp.elements(Door):
        label = f"{door.id} ({door.price}{', needs power' if door.power_gated else ''})"
        edges[door.zone_a].append((door.zone_b, door.price, label))
        edges[door.zone_b].append((door.zone_a, door.price, label))
    # free openings join the two areas either side of them
    for area in areas:
        for name, rect, info in openings.get(area.key, ()):
            if not info.get("free") or info.get("sill", 0) > 0:
                continue
            for other in areas:
                if other.key != area.key and _rect_gap(rect, (other.x0, other.y0, other.x1, other.y1)) <= 24.0:
                    edges[area.key].append((other.key, 0, f"{name} (free)"))
    starts = [z.name for z in bp.elements(Zone) if z.starting]
    cost = {s: 0 for s in starts}
    via: dict[str, list[str]] = {s: [] for s in starts}
    heap = [(0, s) for s in starts]
    while heap:
        c, zone = heapq.heappop(heap)
        if c > cost.get(zone, math.inf):
            continue
        for other, price, label in edges.get(zone, ()):
            if c + price < cost.get(other, math.inf):
                cost[other] = c + price
                via[other] = via[zone] + [label]
                heapq.heappush(heap, (c + price, other))
    zones = [z.name for z in bp.elements(Zone)]
    return {
        "starting_zones": starts,
        "zones": {z: {"cheapest_cost": cost.get(z), "via": via.get(z)} for z in zones},
        "unreached_zones": [z for z in zones if z not in cost],
    }


def _points_to_core(bp) -> dict:
    """Cheapest door spend from spawn to Juggernog, Quick Revive, power and
    the first box (``D3``; :func:`zmforge.verify.design.points_to_core`)."""
    from ..verify.design import points_to_core

    try:
        return points_to_core(bp)
    except Exception as exc:  # pragma: no cover - reported, not fatal
        return {"error": f"{type(exc).__name__}: {exc}"}


# ----------------------------------------------------------------------
# Strings
# ----------------------------------------------------------------------
_GSC_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def gsc_literals(text: str, limit: int = 200) -> list[str]:
    """Human-looking string literals written straight into a script."""
    seen, out = set(), []
    for match in _GSC_LITERAL.finditer(text):
        s = match.group(1)
        if s in seen or len(s) < 6 or " " not in s:
            continue
        if re.search(r"[\\/]|\.(gsc|csc|map|xmodel)\b|^[a-z_]+$", s):
            continue
        if not re.search(r"[A-Za-z]{3,}.*\s.*[A-Za-z]{2,}", s):
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------
# Script threads (P12 finished means finished, P13 calm screen)
# ----------------------------------------------------------------------
_GSC_FUNCTION = re.compile(r"^function\s+(?:(?:autoexec|private)\s+)*([A-Za-z_]\w*)\s*\(", re.M)
_GSC_LOOP = re.compile(r"\b(?:while|for)\s*\(")
_GSC_FOREVER = re.compile(r"\bwhile\s*\(\s*(?:true|1)\s*\)|\bfor\s*\(\s*;\s*;\s*\)", re.I)
_GSC_EVENT = re.compile(r"\b(endon|waittill|notify)\s*\(\s*\"([^\"]+)\"")
_GSC_REF = re.compile(r"([A-Za-z_][\w:]*)\s*\([^;\n]*?&\"([A-Za-z0-9_]+)\"")
_GSC_THREAD = re.compile(r"\bthread\s+(?:[\w:]+::)?([A-Za-z_]\w*)\s*\(")
_GSC_RANDOM = re.compile(r"\brandom\w*\s*\(", re.I)
_GSC_WAIT = re.compile(r"\bwait\s*\(?\s*([^;]+);")
_GSC_ENDON_VAR = re.compile(r"\bendon\s*\(\s*([A-Za-z_]\w*)\s*\)")
_GSC_PARAMS = re.compile(r"^function\s+(?:(?:autoexec|private)\s+)*([A-Za-z_]\w*)\s*\(([^)]*)\)", re.M)


def _gsc_call_args(body: str, name: str) -> list[list[str]]:
    """The argument lists of every call to *name* in *body*, split at top-level commas."""
    out = []
    for m in re.finditer(r"(?<![\w:])(?:[\w]+::)?" + re.escape(name) + r"\s*\(", body):
        if re.search(r"\bfunction\s+(?:(?:autoexec|private)\s+)*$", body[max(0, m.start() - 40):m.start()]):
            continue  # the definition, not a call
        i, depth, arg, args, quoted = m.end(), 1, [], [], False
        while i < len(body) and depth:
            ch = body[i]
            if ch == '"' and body[i - 1] != "\\":
                quoted = not quoted
            elif not quoted and ch == "(":
                depth += 1
            elif not quoted and ch == ")":
                depth -= 1
                if not depth:
                    break
            elif not quoted and ch == "," and depth == 1:
                args.append("".join(arg).strip())
                arg = []
                i += 1
                continue
            arg.append(ch)
            i += 1
        args.append("".join(arg).strip())
        out.append(args)
    return out


def _gsc_functions(text: str) -> list[tuple[str, int, str]]:
    """``(name, line, body)`` for every top-level function, by brace matching."""
    out = []
    for match in _GSC_FUNCTION.finditer(text):
        start = text.find("{", match.end())
        if start < 0:
            continue
        depth, i = 0, start
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            elif ch == '"':  # skip string literals (braces in text)
                i = text.find('"', i + 1)
                while i > 0 and text[i - 1] == "\\":
                    i = text.find('"', i + 1)
                if i < 0:
                    break
            i += 1
        out.append((match.group(1), text.count("\n", 0, match.start()) + 1,
                    text[match.start():i + 1]))
    return out


def script_threads(server_text: str, lookup: Mapping[str, tuple[str, str, str]],
                   source_limit: int = 30000) -> dict:
    """Every looping or timed function in the generated server script.

    For P12: what each loop waits on and what ends it (``endon`` events,
    ``break``/``return`` inside, or a loop condition that is not forever),
    who threads it, what it notifies.  For P13: every line such a function
    shows, with the string's text, and whether its timing is random.  The
    sources of the functions that show lines or loop forever follow, up to
    *source_limit* characters, so the reviewer can check the end condition.
    """
    functions = _gsc_functions(server_text)
    callers: dict[str, list[str]] = defaultdict(list)
    notified_by: dict[str, list[str]] = defaultdict(list)
    for name, _, body in functions:
        for callee in set(_GSC_THREAD.findall(body)):
            callers[callee].append(name)
        for kind, event in _GSC_EVENT.findall(body):
            if kind == "notify" and name not in notified_by[event]:
                notified_by[event].append(name)
    params = {m.group(1): [a.strip() for a in m.group(2).split(",") if a.strip()]
              for m in _GSC_PARAMS.finditer(server_text)}
    rows, sources = [], []
    for name, line, body in functions:
        loops = len(_GSC_LOOP.findall(body))
        waits = _GSC_WAIT.findall(body)
        refs = [(call, ref) for call, ref in _GSC_REF.findall(body)
                if not call.lower().startswith(("precache", "istring"))]
        if not loops and not (waits and refs):
            continue
        events: dict[str, list[str]] = defaultdict(list)
        for kind, event in _GSC_EVENT.findall(body):
            if event not in events[kind]:
                events[kind].append(event)
        lines = []
        for call, ref in refs:
            text = lookup.get(ref, (ref, None, ""))[1]
            item = [call, ref, text[:160] if text else "(not a map string)"]
            if item not in lines:
                lines.append(item)
        # ``level endon( str_end )``: the event is a parameter, so what ends
        # the loop is whatever each caller passes there (a quest pulse ends on
        # its own step's end event, not only at end of game).
        endon = list(events.get("endon", []))
        passed: dict[str, list[str]] = {}
        for var in dict.fromkeys(_GSC_ENDON_VAR.findall(body)):
            if var not in params.get(name, []):
                continue
            index = params[name].index(var)
            for caller, _, caller_body in functions:
                for args in _gsc_call_args(caller_body, name):
                    arg = args[index] if index < len(args) else ""
                    lit = arg[1:-1] if len(arg) > 1 and arg[0] == arg[-1] == '"' else None
                    event = lit if lit is not None else f"<{arg or 'nothing'}>"
                    if event not in endon:
                        endon.append(event)
                    passed.setdefault(event, [])
                    if caller not in passed[event]:
                        passed[event].append(caller)
        forever = len(_GSC_FOREVER.findall(body))
        row = {
            "function": name, "line": line, "loops": loops, "forever_loops": forever,
            "endon": endon, "waittill": events.get("waittill", [])[:8],
            "notify": events.get("notify", [])[:8],
            "exits_inside": len(re.findall(r"\b(?:break|return)\b", body)),
            "waits": [w.strip()[:40] for w in waits][:6],
            "random": bool(_GSC_RANDOM.search(body)),
            "threaded_by": callers.get(name, [])[:6],
            "lines_shown": lines[:12],
        }
        if passed:
            # an endon event that is a parameter: the event each caller passes
            # and which functions send it (an event nobody sends never ends it)
            row["endon_passed_by_caller"] = {
                event: {"passed_by": who[:6], "notified_by": notified_by.get(event, [])[:6]}
                for event, who in passed.items()}
        rows.append(row)
        if lines or (forever and not row["endon"]):
            sources.append((0 if lines else 1, f"// {name} (server script line {line})\n{body}"))
    text_out, used = [], 0
    for _, src in sorted(sources, key=lambda t: t[0]):
        if used + len(src) > source_limit:
            text_out.append(f"// ... the remaining functions are omitted (limit {source_limit} characters)")
            break
        text_out.append(src)
        used += len(src)
    return {
        "note": ("functions of the generated server script that loop, or wait and then "
                 "show a line; 'lines_shown' are [call, string ref, text]; a forever "
                 "loop ends only through its endon events or an exit inside it; an endon "
                 "on a parameter is resolved per caller in 'endon_passed_by_caller' "
                 "(the event each caller passes, and who notifies it)"),
        "threads": rows,
        "source": "\n\n".join(text_out),
    }


def _strings(bp, lookup, notices_facts, server_text: str, ignore: Iterable[str]) -> dict:
    from ..emit.strings import weapon_prompt

    prompts = {n["prompt"] for n in notices_facts}
    rows = []
    for asset, (ref, text, kind) in sorted(lookup.items(), key=lambda kv: kv[1][0]):
        is_prompt = kind == "triggerstring" or text in prompts
        rows.append({"ref": ref, "kind": "prompt" if is_prompt else "line", "text": text,
                     "issues": text_issues(text, prompt=is_prompt and "&&" not in text, ignore=ignore)})
    wall = [{"weapon": w, "text": t, "shown_as": weapon_prompt(t),
             "issues": text_issues(t, ignore=ignore)}
            for w, t in sorted(bp.weapon_prompts.items())]
    inline = gsc_literals(server_text)
    inline_rows = [{"text": s, "issues": text_issues(s, ignore=ignore)} for s in inline]
    return {"map_strings": rows, "wall_buy_names": wall, "inline_script_literals": inline_rows}


def _ignore_words(bp) -> set[str]:
    """Names the map made up (zones, models, perk slugs) are not typos."""
    words = set()
    for text in list(bp.map_strings.keys()) + [bp.name]:
        words |= {w.lower() for w in re.split(r"[^A-Za-z]+", text) if w}
    return words


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------
def density_floor(floor_area: float) -> int:
    """The fewest props a room of *floor_area* square units should carry."""
    from ..dressing.scene import BIG_ROOM_K2

    per = DENSITY_PER_MILLION_SQ_UNITS if floor_area >= BIG_ROOM_K2 * 1e6 else DENSITY_PER_MILLION_SMALL
    return max(DENSITY_FLOOR, int(per * floor_area / 1_000_000))


def is_floor_litter(prop: PropFact, area: Area | None = None) -> bool:
    """A litter model (``recipes.props.is_litter``) lying on the floor, not
    on a desk, shelf or other surface."""
    from ..recipes.props import is_litter

    if not is_litter(prop.model):
        return False
    if prop.sits_on.startswith("floor"):
        return True
    if prop.sits_on in ("unmeasured", "nothing measured under it"):
        area = area or prop.area
        base = prop.z_low if prop.z_low is not None else prop.z
        return area is not None and base - area.floor_z <= FLOAT_GAP
    return False


def counted_props(n: int, litter: int, cap: float = LITTER_SHARE_CAP) -> int:
    """Props that count toward the density floor: every real prop, plus floor
    litter up to *cap* of the counted total (``litter <= cap * counted``)."""
    real = n - litter
    allowed = int(real * cap / (1.0 - cap)) if cap < 1.0 else litter
    return real + min(litter, allowed)


def _room_scorecard(area: Area, props: Sequence[PropFact], findings: Mapping[str, Counter],
                    near_purchase: Sequence[dict], text_flags: int,
                    quest_points: Sequence[dict]) -> dict:
    from ..dressing.cluster import clark_evans, is_foliage

    n = len(props)
    litter = [p for p in props if is_floor_litter(p, area)]
    foliage = [(p.x, p.y) for p in props if is_foliage(p.model)]
    counted = counted_props(n, len(litter))
    models = Counter(p.model for p in props)
    floor = [p for p in props if p.mount in ("floor", "either") and p.sits_on == "floor"]
    hug = [p for p in floor if p.wall_gap is not None and p.wall_gap <= WALL_BAND]
    middle = [p for p in floor if p.wall_gap is not None and p.wall_gap >= MIDDLE_BAND]
    surfaces = [p for p in props if p.sits_on.startswith(("prop ", "fixture "))]
    floating = [p for p in props if p.mount in ("floor", "either") and p.float_gap > FLOAT_GAP]
    through = [p for p in props if p.wall_gap is not None and p.wall_gap < -1.0
               and p.mount in ("floor", "either")]
    blocking = [p for p in props if p.solid and p.door_gap is not None and p.door_gap < DOOR_BAND
                and p.z_high is not None and p.z_high - area.floor_z > STEP_HEIGHT
                and p.mount in ("floor", "either")]
    area_units = area.area
    top = models.most_common(3)
    floor_n = density_floor(area_units)
    return {
        "props": n,
        "floor_litter": len(litter),
        "litter_share": round(len(litter) / n, 2) if n else 0.0,
        # Clark-Evans nearest-neighbour ratio of the room's plants (Z66):
        # about 1 an even scatter, under 1 clumps.
        "foliage": len(foliage),
        "foliage_evenness": clark_evans(foliage, area.area, 2.0 * ((area.x1 - area.x0) + (area.y1 - area.y0))),
        "counted_props": counted,
        "density_floor": floor_n,
        "density_band": "under" if counted < floor_n else "in",
        "area_sq_units": round(area_units),
        "area_sq_ft": round(area_units / UNITS_PER_FOOT ** 2),
        "props_per_100x100_units": round(n / (area_units / 10000.0), 2) if area_units else None,
        "props_per_100_sq_ft": round(n / (area_units / UNITS_PER_FOOT ** 2) * 100, 2) if area_units else None,
        "distinct_models": len(models),
        "top_models": [[m, c, round(c / n, 2)] for m, c in top] if n else [],
        "repetition_top_share": round(top[0][1] / n, 2) if n else 0.0,
        "floor_props": len(floor),
        "wall_hug_share": round(len(hug) / len(floor), 2) if floor else None,
        "middle_share": round(len(middle) / len(floor), 2) if floor else None,
        "on_surfaces": len(surfaces),
        "wall_or_ceiling_mounted": sum(1 for p in props if p.mount in ("wall", "ceiling")),
        "unmeasured_models": sum(1 for p in props if p.mount == "unmeasured"),
        "floating": [[p.id, p.float_gap] for p in floating][:15],
        "through_wall": [[p.id, round(p.wall_gap, 1), p.wall_side] for p in through][:15],
        "solid_near_doorway": [[p.id, p.door_gap, p.door] for p in blocking][:15],
        "use_triggers_near_purchases": list(near_purchase)[:15],
        "quest_points": len(quest_points),
        "quest_points_unreachable": [q["label"] for q in quest_points if q.get("reachable") == "no"],
        "string_issues": text_flags,
        "check_findings": {code: c for code, c in sorted(findings.items())},
    }


def collect(gen: Generated) -> dict:
    """Everything the review reads, measured off a generated map."""
    from ..blueprint.elements import Massing, Spawn, Zone
    from ..verify.reachability import flood_from_spawn

    bp = gen.blueprint
    areas = _areas(bp)
    props = _props(bp, areas)
    openings = _openings(bp, areas)
    _measure_props(props, openings)
    try:
        flood = flood_from_spawn(bp)
    except Exception:  # pragma: no cover - reported, not fatal
        flood = None
    lookup = _string_lookup(bp)
    ignore = _ignore_words(bp)
    notices = _notices(bp, gen.notices, lookup)
    inter = _interactives(bp)
    quests, quest_points = _quest_facts(gen.quests, areas, flood, props)
    strings = _strings(bp, lookup, notices, getattr(gen, "server_text", ""), ignore)

    # check findings, by element, then by room
    by_element: dict[str, list] = defaultdict(list)
    all_findings = list(gen.report.findings) if gen.report is not None else []
    for finding in all_findings:
        if finding.element_id:
            by_element[finding.element_id].append(finding)
    element_area: dict[str, str] = {p.id: p.area.key for p in props if p.area}
    for item in inter:
        a = _area_of(areas, *item["at"][:2]) if item.get("at") else None
        item["room"] = a.key if a else "outside"
        if a:
            item["rel"] = a.rel(*item["at"])
        element_area[item["id"]] = item["room"]
    for massing in bp.elements(Massing):
        if massing.solids:
            from ..blueprint.model import _solid_bounds
            b = _solid_bounds(massing.solids[0])
            a = _area_of(areas, b.centre.x, b.centre.y, b.mins.z)
            if a:
                element_area[massing.id] = a.key

    # use triggers (notices and quest use points) against purchases
    purchases = [i for i in inter if i.get("purchase") and i.get("at")]
    triggers = [(f"notice {n['id']}", n["at"]) for n in notices if n["at"]]
    for quest in gen.quests:
        for index, p in enumerate(quest.use_points()):
            triggers.append((f"quest {quest.key} use point {index}", tuple(p)))
    near: dict[str, list] = defaultdict(list)
    for label, at in triggers:
        a = _area_of(areas, at[0], at[1], at[2], slack=24.0)
        for item in purchases:
            d = math.hypot(at[0] - item["at"][0], at[1] - item["at"][1])
            if d < PURCHASE_CLEARANCE and abs(at[2] - item["at"][2]) < 96:
                near[a.key if a else "outside"].append([label, item["id"], round(d)])

    from .scene_metrics import collect_art

    art = collect_art(bp, areas, props)
    rooms = []
    per_room_props: dict[str, list[PropFact]] = defaultdict(list)
    for p in props:
        per_room_props[p.area.key if p.area else "outside"].append(p)
    string_refs_by_room: dict[str, int] = Counter()
    for n in notices:
        a = _area_of(areas, *n["at"]) if n["at"] else None
        n["room"] = a.key if a else "outside"
        if a:
            n["rel"] = a.rel(*n["at"])
        issues = text_issues(n["prompt"], prompt=True, ignore=ignore)
        for reply in n["replies"]:
            issues += text_issues(reply, ignore=ignore)
        n["issues"] = issues
        string_refs_by_room[n["room"]] += len(issues)

    spawns = Counter(s.zone_name for s in bp.elements(Spawn))
    for area in areas:
        room_props = per_room_props.get(area.key, [])
        codes: Counter = Counter()
        for element_id, found in by_element.items():
            if element_area.get(element_id) == area.key:
                for f in found:
                    codes[f.code] += 1
        room_quest = [q for q in quest_points if q["room"] == area.key]
        card = _room_scorecard(area, room_props, codes, near.get(area.key, []),
                               string_refs_by_room.get(area.key, 0), room_quest)
        room = area.room
        mats = getattr(room, "materials", None)
        fixtures = []
        for massing in bp.elements(Massing):
            if element_area.get(massing.id) == area.key and massing.solids:
                from ..blueprint.model import _solid_bounds
                b = _solid_bounds(massing.solids[0])
                fixtures.append([massing.id, (massing.note or "")[:50],
                                 area.rel(b.mins.x, b.mins.y, b.mins.z),
                                 [round(b.size.x), round(b.size.y), round(b.size.z)]])
        rooms.append({
            "room": area.key,
            "room_id": area.room_id,
            "size": [round(area.x1 - area.x0), round(area.y1 - area.y0),
                     round(area.ceiling_z - area.floor_z)],
            "origin_note": "positions are [x, y, z] relative to the room's south-west "
                           "floor corner; x runs east, y runs north",
            "materials": {k: (_material_name(getattr(mats, k))
                              if k != "ceiling" or getattr(room, "roofed", True)
                              else "none: unroofed, open to the sky box")
                          for k in ("wall", "floor", "ceiling")}
            if mats else {},
            "openings": [{"id": name, "rel": area.rel(r[0], r[1]),
                          "size": [round(r[2] - r[0]), round(r[3] - r[1])], **info}
                         for name, r, info in openings.get(area.key, ())],
            "zombie_spawns": spawns.get(area.key, 0),
            "interactives": [{k: v for k, v in i.items() if k not in ("at", "purchase")}
                             for i in inter if i["room"] == area.key],
            "notices": [{k: v for k, v in n.items() if k != "at"} for n in notices
                        if n["room"] == area.key],
            "quest_points": room_quest,
            "fixtures_columns": ["id", "note", "rel_min", "size"],
            "fixtures": fixtures,
            "props_columns": ["id", "model", "rel", "yaw", "solid", "mount", "height",
                              "wall_gap", "wall", "door_gap", "door", "sits_on"],
            "props": [[p.id, p.model, area.rel(p.x, p.y, p.z), round(p.yaw), p.solid, p.mount,
                       round(p.z_high - p.z_low) if p.z_high is not None else None,
                       round(p.wall_gap) if p.wall_gap is not None else None, p.wall_side,
                       p.door_gap, p.door, p.sits_on] for p in room_props],
            "scorecard": card,
            "art": art.get(area.key),
        })
    outside = per_room_props.get("outside", [])

    findings_summary = Counter((f.severity, f.code) for f in all_findings)
    return {
        "map": gen.name,
        "recipe": gen.recipe,
        "thresholds": {
            "wall_band": WALL_BAND, "middle_band": MIDDLE_BAND, "door_band": DOOR_BAND,
            "purchase_clearance": PURCHASE_CLEARANCE,
            "density_floor": f"max({DENSITY_FLOOR}, {DENSITY_PER_MILLION_SQ_UNITS} per "
                             "1,000,000 sq units of floor in a room of 500,000 sq units or more, "
                             f"{DENSITY_PER_MILLION_SMALL} in a smaller one); no upper limit "
                             "but the engine's",
            "litter_share_cap": (f"floor litter counts toward the density floor only up to "
                                 f"{LITTER_SHARE_CAP:.0%} of counted_props; the rest is measured, "
                                 "not counted"),
            "float_gap": FLOAT_GAP,
        },
        "engine_limits": _engine_limits(bp, len(props)),
        "players": _player_facts(bp),
        "design_notes": list(getattr(bp, "review_notes", ()) or ()),
        "rooms": rooms,
        "outside_props": {"count": len(outside),
                          "models": Counter(p.model for p in outside).most_common(12)},
        "essentials": [{k: v for k, v in i.items() if k not in ("at", "purchase")}
                       for i in inter if i["kind"] != "barrier"],
        "barriers_per_zone": dict(Counter(i["zone"] for i in inter if i["kind"] == "barrier")),
        "spawns_per_zone": dict(spawns),
        "custom_perks": [_perk_facts(bp, p) for p in bp.custom_perks],
        "progression": _progression(bp, areas, openings),
        # D3 (docs/map-design-method.md section 8): a fact, no threshold yet.
        "points_to_core": _points_to_core(bp),
        "quests": quests,
        "quest_points": quest_points,
        "notices_total": len(notices),
        "strings": strings,
        "script": script_threads(getattr(gen, "server_text", "") or "", lookup),
        "checks": {
            "ok": bool(gen.report.ok) if gen.report is not None else None,
            "counts": {f"{sev}:{code}": c for (sev, code), c in sorted(findings_summary.items())},
            "messages": [f"{f.severity} {f.code} {f.element_id or ''}: {f.message[:220]}"
                         for f in all_findings if f.code not in ("L2",)][:40],
        },
    }


def scorecard_table(facts: Mapping) -> str:
    """One line per room, for a terminal or a markdown report."""
    head = (f"{'room':12s} {'props':>5s} {'count':>5s} {'lit%':>4s} {'band':>5s} {'/100sqft':>8s} {'models':>6s} "
            f"{'top%':>4s} {'hug':>4s} {'mid':>4s} {'onsurf':>6s} {'float':>5s} "
            f"{'thru':>4s} {'door':>4s} {'text':>4s}")
    lines = [head]
    for room in facts["rooms"]:
        c = room["scorecard"]
        pct = lambda v: "-" if v is None else f"{round(v * 100)}"
        lines.append(
            f"{room['room'][:12]:12s} {c['props']:5d} {c['counted_props']:5d} "
            f"{pct(c['litter_share']):>4s} {c['density_band']:>5s} "
            f"{c['props_per_100_sq_ft'] or 0:8.2f} {c['distinct_models']:6d} "
            f"{pct(c['repetition_top_share']):>4s} {pct(c['wall_hug_share']):>4s} "
            f"{pct(c['middle_share']):>4s} {c['on_surfaces']:6d} {len(c['floating']):5d} "
            f"{len(c['through_wall']):4d} {len(c['solid_near_doorway']):4d} {c['string_issues']:4d}"
        )
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Source excerpts for the AI layer
# ----------------------------------------------------------------------
SRC = Path(__file__).resolve().parents[1]

#: Per recipe: the modules that dress rooms, and those holding the map's
#: quest, gags and strings.  Paths relative to ``src/zmforge``.
RECIPE_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "dmv": {"rooms": ("recipes/dmv_rooms",),
            "map": ("recipes/dmv_quest.py", "recipes/dmv.py")},
    "cemetery": {"rooms": ("recipes/cemetery_dressing.py",),
                 "map": ("recipes/cemetery_quest.py", "recipes/cemetery_dressing.py",
                         "recipes/cemetery.py")},
    "corn_maze": {"rooms": ("recipes/corn_maze_parts.py",),
                  "map": ("recipes/corn_maze_script.py", "recipes/corn_maze.py")},
}

_MAP_DEF_WORDS = re.compile(r"quest|gag|notice|announce|react|string|prompt|boss|exit|wire|line",
                            re.IGNORECASE)


def _defs(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover
        return [(path.stem, text)]
    lines = text.splitlines()
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)):
            start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None)
                     else node.lineno)
            name = getattr(node, "name", None) or ast.unparse(
                node.targets[0] if isinstance(node, ast.Assign) else node.target)
            out.append((name, f"# {path.name}:{start}\n" + "\n".join(lines[start - 1:node.end_lineno])))
    return out


def _compact(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def room_source(recipe: str, room_key: str, room_id: str, limit: int = 40000) -> str:
    """The recipe code that dresses one room, capped at *limit* characters.

    A package of per-room modules (``dmv_rooms``) gives the module whose name
    matches the room; a single dressing module gives every top-level
    definition that names the room.
    """
    spec = RECIPE_SOURCES.get(recipe)
    if not spec:
        return ""
    key = _compact(room_key)
    parts: list[str] = []
    for rel in spec["rooms"]:
        path = SRC / rel
        if path.is_dir():
            for module in sorted(path.glob("*.py")):
                stem = _compact(module.stem)
                if stem and (key.startswith(stem) or stem.startswith(key)):
                    parts.append(f"# ==== {rel}/{module.name}\n" + module.read_text(encoding="utf-8"))
        elif path.is_file():
            needle = re.compile(rf"[\"'_]{re.escape(room_key)}[\"'_]|_dress_{re.escape(room_key)}\b|\b{re.escape(room_id)}\b")
            hits = [src for name, src in _defs(path) if needle.search(src) or key in _compact(name)]
            if hits:
                parts.append(f"# ==== {rel} (definitions naming {room_key!r})\n" + "\n\n".join(hits))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n# ... [truncated]"


def map_source(recipe: str, limit: int = 90000) -> str:
    """The quest module in full, plus quest/gag/notice/string code elsewhere."""
    spec = RECIPE_SOURCES.get(recipe)
    if not spec:
        return ""
    parts = []
    for index, rel in enumerate(spec["map"]):
        path = SRC / rel
        if not path.is_file():
            continue
        if index == 0:
            parts.append(f"# ==== {rel}\n" + path.read_text(encoding="utf-8"))
            continue
        hits = [src for name, src in _defs(path) if _MAP_DEF_WORDS.search(name)]
        if hits:
            parts.append(f"# ==== {rel} (quest/gag/notice/string definitions)\n" + "\n\n".join(hits))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n# ... [truncated]"
