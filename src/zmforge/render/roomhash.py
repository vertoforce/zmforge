"""A fingerprint per room of a generated ``.map``, so only changed rooms are re-rendered.

WHY from the ``.map`` text and not the blueprint: the ``.map`` is exactly what
Radiant draws, so a change that reaches the picture reaches the text, whatever
part of the generator made it.  Each top-level block (a brush of the
worldspawn, a patch, an entity with its brushes) is hashed on its own, without
its ``guid`` lines and ``// brush N`` comments, so inserting one brush does not
change every other block's hash.  A block belongs to every room whose box
(grown by :data:`MARGIN`, so the walls count) it overlaps; a room's hash is
the hash of its blocks' hashes, sorted, plus its camera views and the render
settings, since a new camera or setting is a new picture too.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

#: Units a block may sit outside a room's floor box and still count for it:
#: wall and floor slabs, door frames and props hung on a wall.
MARGIN = 24.0

_POINT = re.compile(r"\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)")
_ORIGIN = re.compile(r'^"origin"\s+"(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)"', re.M)
_PATCH_VERT = re.compile(r"^\s*v\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)", re.M)


@dataclass(frozen=True)
class Block:
    """One top-level piece of the map: its text hash and its box (or None)."""

    digest: str
    box: tuple[float, float, float, float, float, float] | None   # x0 y0 z0 x1 y1 z1


def _clean(lines: Iterable[str]) -> str:
    return "\n".join(ln.strip() for ln in lines
                     if ln.strip() and not ln.lstrip().startswith(("guid", "//")))


def _box(text: str) -> tuple[float, float, float, float, float, float] | None:
    pts = [tuple(map(float, m.groups())) for m in _POINT.finditer(text)]
    pts += [tuple(map(float, m.groups())) for m in _PATCH_VERT.finditer(text)]
    if not pts:
        m = _ORIGIN.search(text)
        if not m:
            return None
        pts = [tuple(map(float, m.groups()))]
    xs, ys, zs = zip(*pts)
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def split_blocks(map_text: str) -> list[Block]:
    """The worldspawn's brushes and patches, and every other entity, as blocks.

    Works on brace depth: depth 1 is an entity, depth 2 a brush or patch
    inside it.  Worldspawn's own key/value lines are one block with no box
    (they change every room: sky, sun, lighting quality).
    """
    blocks: list[Block] = []
    depth = 0
    entity: list[str] = []
    child: list[str] = []
    entity_children: list[str] = []
    worldspawn = False
    for line in map_text.splitlines():
        s = line.strip()
        if s == "{":
            depth += 1
            if depth == 1:
                entity, entity_children, worldspawn = [], [], False
            elif depth == 2:
                child = []
            continue
        if s == "}":
            if depth == 2:
                text = _clean(child)
                if worldspawn:
                    blocks.append(Block(_digest(text), _box(text)))
                else:
                    entity_children.append(text)
            elif depth == 1:
                head = _clean(entity)
                if worldspawn:
                    blocks.append(Block(_digest(head), None))
                else:
                    text = head + "\n" + "\n".join(entity_children)
                    blocks.append(Block(_digest(text), _box(text)))
            depth = max(0, depth - 1)
            continue
        if depth == 1:
            entity.append(line)
            if s == '"classname" "worldspawn"':
                worldspawn = True
        elif depth >= 2:
            child.append(line)
    return blocks


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _overlaps(box, area, margin: float = MARGIN) -> bool:
    x0, y0, z0, x1, y1, z1 = box
    return (x1 >= area.x0 - margin and x0 <= area.x1 + margin
            and y1 >= area.y0 - margin and y0 <= area.y1 + margin
            and z1 >= area.floor_z - margin and z0 <= area.ceiling_z + margin)


def room_hashes(map_text: str, areas: Sequence, *, views: Iterable = (),
                settings: Mapping | None = None) -> dict[str, str]:
    """``{room key: hash}`` over the blocks each room's box touches.

    *views* (``View`` objects or dicts with a ``room`` key) and *settings*
    (width, lighting, ...) are folded in, so a moved camera or a new setting
    counts as a change too.
    """
    blocks = [b for b in split_blocks(map_text) if b.box is not None]
    per_view: dict[str, list[str]] = {}
    for v in views:
        d = v if isinstance(v, Mapping) else v.as_dict()
        per_view.setdefault(d["room"], []).append(json.dumps(d, sort_keys=True))
    extra = json.dumps(dict(settings or {}), sort_keys=True, default=str)
    out = {}
    for area in areas:
        mine = sorted(b.digest for b in blocks if _overlaps(b.box, area))
        payload = "\n".join([*mine, "--views", *sorted(per_view.get(area.key, [])),
                             "--settings", extra])
        out[area.key] = _digest(payload)
    return out


def changed_rooms(now: Mapping[str, str], before: Mapping[str, str]) -> list[str]:
    """Rooms of *now* whose hash is new or differs from *before*, in *now*'s order."""
    return [room for room, h in now.items() if before.get(room) != h]
