"""zm_dmv's dense pass: one module per room, each owning that room's clutter.

The fourth furnishing pass (after :func:`zmforge.recipes.dmv._furnish_lived_in`
and :func:`~zmforge.recipes.dmv._furnish_character`).  A DMV needs
character and a fully populated look, so
each room gets its own module here and fills itself to a real, lived-in,
post-outbreak density -- clutter on every surface, stacks, piles, wall
dressing, floor debris, story vignettes -- without choking movement.

A room module defines:

``dress(ctx: RoomContext) -> None``
    places its props through ``ctx.put(items, "dense_<key>_<what>")``.
``NOTICES: dict[str, tuple[str, tuple[str, ...]]]`` (optional)
    extra use-trigger notices, same shape as
    :data:`zmforge.recipes.dmv.NOTICE_LINES`; keys must start with
    ``<key>_`` so no two rooms collide.
``notice_spots(ctx) -> list[tuple[str, Point]]`` (optional)
    where each of those notices stands.

The rules are the other passes' rules: measured models only
(:data:`zmforge.recipes.props.MODEL_BOX`), solid pieces against walls and
clear of doorways (``Z53``) and walls (``Z54``), small clutter not solid,
nothing inside anything else, nothing on the queue's lanes or in front of a
perk, a buy, the box, the switch or the ticket machine, and nothing that
makes a new step up of more than the jump (39).
"""
from __future__ import annotations

import importlib
from typing import Mapping

from ...spatial import Point

#: Room key -> module name, in the order they are dressed.
ROOM_MODULES: dict[str, str] = {
    "lot": "lot",
    "entry": "entry",
    "waiting": "waiting",
    "windows": "windows",
    "eye": "eye",
    "photo": "photo",
    "break": "break_room",
    "records": "records",
    "queue": "queue",
    "office": "office",
}


def _module(key: str):
    return importlib.import_module(f"{__name__}.{ROOM_MODULES[key]}")


def furnish_dense(bp, plan, rooms: Mapping[str, object], *,
                  walk_top: float, walk_x0: float) -> dict[str, int]:
    """Run every room's ``dress``; returns props placed per room key."""
    from ._kit import RoomContext

    counts: dict[str, int] = {}
    for key in ROOM_MODULES:
        ctx = RoomContext(bp, plan, key, rooms[key], rooms, walk_top, walk_x0)
        _module(key).dress(ctx)
        counts[key] = ctx.placed
    return counts


def dense_notices(plan, rooms: Mapping[str, object], *, walk_top: float,
                  walk_x0: float, bp=None
                  ) -> tuple[dict[str, tuple[str, tuple[str, ...]]], list[tuple[str, Point]]]:
    """Every room module's ``NOTICES`` and their spots, merged and checked
    for key collisions."""
    from ._kit import RoomContext

    lines: dict[str, tuple[str, tuple[str, ...]]] = {}
    spots: list[tuple[str, Point]] = []
    for key in ROOM_MODULES:
        module = _module(key)
        extra = getattr(module, "NOTICES", {})
        for name in extra:
            if not name.startswith(f"{key}_"):
                raise ValueError(f"{name}: a {key} notice key starts with {key}_")
            if name in lines:
                raise ValueError(f"{name}: notice key used twice")
        lines.update(extra)
        if hasattr(module, "notice_spots"):
            ctx = RoomContext(bp, plan, key, rooms[key], rooms, walk_top, walk_x0)
            spots.extend(module.notice_spots(ctx))
    unknown = {name for name, _ in spots} - set(lines)
    if unknown:
        raise ValueError(f"notice spots with no NOTICES entry: {sorted(unknown)}")
    return lines, spots


def dense_notice_lines() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Every room module's ``NOTICES`` merged (text only, no spots)."""
    lines: dict[str, tuple[str, tuple[str, ...]]] = {}
    for key in ROOM_MODULES:
        lines.update(getattr(_module(key), "NOTICES", {}))
    return lines
