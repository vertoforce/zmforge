"""Generic layout rules.

Each rule here is written so it applies to every map, not to one layout.  All of them are warnings: they say what reads
badly or plays badly, and the map decides.

(:data:`OMNI_OVERLAP_LIMIT` records a light-budget rule that was tried and
falsified; ``shadows_dropped`` in :mod:`~zmforge.verify.stages` reads the
bake's own log instead.)

``Z74`` stamping: two rooms, or two vignettes from one template, that share
        most of their (model, relative position) pairs; and one litter model
        placed past :data:`LITTER_CAP` times in a map;
``Z75`` tall walk-through props: non-solid, over 60 tall and over 40 wide on
        both sides, which a player expects to stop him and walks into;
``Z76`` a barricade riser in a zone too small or too narrow to fight in;
``Z77`` a whole wall side of a room in a material that renders as a void.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from ..spatial import Axis, Side
from .report import Report, warning

__all__ = [
    "OMNI_OVERLAP_LIMIT",
    "STAMP_SHARE",
    "LITTER_CAP",
    "DARK_WALL_MATERIALS",
    "check_layout_rules",
]


# ---------------------------------------------------------------------------
# The bake's omni light budget: a record, not a check
# ---------------------------------------------------------------------------
#: How many omni lights may reach one lamp's own position before the bake
#: starts dropping shadows.  **Measured on zm_corn_maze's bake
#: log**: the 26 lamps named by ``ERROR: Too many shadowing omni lights.
#: Shadow for light at ... is being dropped`` all stood where 9 to 19 omni
#: spheres (their own included) reach, and no lamp reached by 8 or fewer was
#: dropped.  All 26 were written ``PRIMARY_NOSHADOWMAP 1``: the bake's limit
#: counts every omni light, not only those given a run-time shadow map, so
#: making fill lamps shadowless (which :meth:`Blueprint.light_rooms` and the
#: play lamps already do) does not get a map under it.  The limit is the
#: boundary of one measured map, not a number out of a document.
#:
#: **Falsified, so the check is not run**: builds of zm_dmv (lamps reached
#: by up to 20 spheres) and of two test maps (23 and 70)
#: baked with no drop at all.  Sphere overlap is not
#: the bake's rule, and what is has not been measured; the bake log is.
OMNI_OVERLAP_LIMIT = 8


# ---------------------------------------------------------------------------
# Z74: stamping and litter
# ---------------------------------------------------------------------------
#: Two copies of one template that share more than this fraction of their
#: (model, relative position) pairs read as stamped.
STAMP_SHARE = 0.60
#: The position grid the pairs are compared on.
STAMP_GRID = 16.0
#: A scatter or room with fewer props than this is too small to call stamped.
STAMP_MIN_PROPS = 6
#: How many times one litter model may appear in a map.
LITTER_CAP = 40
#: Name tokens that make a model litter.  Foliage and corn are not litter:
#: they are ground cover and are expected in thousands.
LITTER_TOKENS = ("debris", "trash", "litter", "paper", "newspaper", "bottle",
                 "garbage", "cigarette", "wrapper", "can_", "cup_", "_cup",
                 "bag_", "leaves_pile", "rubble")

_TRAILING_INDEX = re.compile(r"(?:[_-]?\d+)+$")


def _stem(scatter_id: str) -> str:
    return _TRAILING_INDEX.sub("", scatter_id)


def _signature(props, ox: float, oy: float) -> set:
    return {
        (p.model, round((p.origin.x - ox) / STAMP_GRID), round((p.origin.y - oy) / STAMP_GRID))
        for p in props
    }


def _share(a: set, b: set) -> float:
    small = min(len(a), len(b))
    return len(a & b) / small if small else 0.0


def _stamped_pairs(groups: dict[str, list[tuple[str, set]]]):
    for stem, members in groups.items():
        if len(members) < 2:
            continue
        pairs = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                share = _share(members[i][1], members[j][1])
                if share > STAMP_SHARE:
                    pairs.append((members[i][0], members[j][0], share))
        if pairs:
            yield stem, pairs


def _check_stamping(bp, report: Report) -> None:
    from ..blueprint.elements import PropScatter, Room

    scatters = [s for s in bp.elements(PropScatter) if len(s.props) >= STAMP_MIN_PROPS]
    groups: dict[str, list[tuple[str, set]]] = defaultdict(list)
    for scatter in scatters:
        cx = sum(p.origin.x for p in scatter.props) / len(scatter.props)
        cy = sum(p.origin.y for p in scatter.props) / len(scatter.props)
        groups[_stem(scatter.id)].append((scatter.id, _signature(scatter.props, cx, cy)))
    for stem, pairs in _stamped_pairs(groups):
        a, b, share = max(pairs, key=lambda p: p[2])
        report.add(warning(
            "Z74",
            f"vignette template {stem!r}: {len(pairs)} pair(s) of copies share over "
            f"{STAMP_SHARE:.0%} of their (model, relative position) pairs, worst "
            f"{a} and {b} at {share:.0%}; a player who has seen one has seen "
            "both. Vary the models, the layout or the rotation per copy",
            a,
        ))
    # Rooms: props by room, relative to the room's own corner, rooms of one
    # interior size compared with each other.
    rooms = [r for r in bp.elements(Room)]
    by_room: dict[str, list] = defaultdict(list)
    for scatter in bp.elements(PropScatter):
        for prop in scatter.props:
            for room in rooms:
                i = room.interior
                if i.holds_flat(prop.origin.x, prop.origin.y) and i.mins.z - 8.0 <= prop.origin.z <= i.maxs.z:
                    by_room[room.id].append(prop)
                    break
    room_groups: dict[str, list[tuple[str, set]]] = defaultdict(list)
    for room in rooms:
        props = by_room.get(room.id, [])
        if len(props) < STAMP_MIN_PROPS:
            continue
        i = room.interior
        size = f"{round(i.extent(Axis.X))}x{round(i.extent(Axis.Y))}"
        room_groups[size].append((room.id, _signature(props, i.mins.x, i.mins.y)))
    for size, pairs in _stamped_pairs(room_groups):
        a, b, share = max(pairs, key=lambda p: p[2])
        report.add(warning(
            "Z74",
            f"rooms of size {size}: {a} and {b} share {share:.0%} of their "
            "(model, position in the room) pairs; two rooms dressed from one "
            "template read as copy and paste",
            a,
        ))
    # Litter.
    counts: Counter = Counter()
    for scatter in bp.elements(PropScatter):
        for prop in scatter.props:
            name = prop.model.lower()
            if any(token in name for token in LITTER_TOKENS):
                counts[prop.model] += 1
    for model, count in counts.most_common():
        if count <= LITTER_CAP:
            break
        report.add(warning(
            "Z74",
            f"litter model {model} is placed {count} times, over the cap of "
            f"{LITTER_CAP} per map; one piece of rubbish repeated reads as a "
            "texture, not as a mess. Mix models or thin it",
        ))


# ---------------------------------------------------------------------------
# Z75: tall walk-through props
# ---------------------------------------------------------------------------
#: A non-solid floor prop taller and wider than these is one a player
#: expects to stop him.
WALK_THROUGH_TALL = 60.0
WALK_THROUGH_WIDE = 40.0


def _check_tall_walk_through(bp, report: Report) -> None:
    from ..blueprint.elements import PropScatter, Room
    from ..recipes.props import MODEL_BOX, MOUNT_FLOOR, mount_kind

    reachable_off = [r.interior for r in bp.elements(Room) if not r.reachable]
    found: Counter = Counter()
    for scatter in bp.elements(PropScatter):
        for prop in scatter.props:
            if prop.solid or prop.dynamic:
                continue
            box = MODEL_BOX.get(prop.model)
            if box is None or mount_kind(prop.model) != MOUNT_FLOOR:
                continue
            (x0, y0, z0), (x1, y1, z1) = box
            s = prop.scale
            if (z1 - z0) * s <= WALK_THROUGH_TALL:
                continue
            if min(x1 - x0, y1 - y0) * s <= WALK_THROUGH_WIDE:
                continue
            if any(i.holds_flat(prop.origin.x, prop.origin.y) for i in reachable_off):
                continue
            found[prop.model] += 1
    for model, count in found.most_common():
        report.add(warning(
            "Z75",
            f"{count} walk-through {model} prop(s) over {WALK_THROUGH_TALL:g} "
            f"tall and {WALK_THROUGH_WIDE:g} wide: a player runs into what "
            "looks like a wall and passes through it. Make it solid (with a "
            "collmap) or keep it out of the play space",
        ))


# ---------------------------------------------------------------------------
# Z76: risers in cramped zones
# ---------------------------------------------------------------------------
#: A zone smaller than this (0.05 of a thousand units squared) is too small
#: to fight in with a barricade feeding it.
RISER_ZONE_MIN_AREA = 50_000.0
#: and one narrower than this across its widest volume is a corridor.
RISER_ZONE_MIN_WIDTH = 64.0


def _check_risers(bp, report: Report) -> None:
    from ..blueprint.elements import Window, Zone

    zones: dict[str, list] = defaultdict(list)
    for zone in bp.elements(Zone):
        if zone.bounds is not None:
            zones[zone.name].append(zone.bounds)
    for window in bp.elements(Window):
        boxes = zones.get(window.zone_name)
        if not boxes:
            continue
        area = sum(b.extent(Axis.X) * b.extent(Axis.Y) for b in boxes)
        width = max(min(b.extent(Axis.X), b.extent(Axis.Y)) for b in boxes)
        why = []
        if area < RISER_ZONE_MIN_AREA:
            why.append(f"{area / 1e6:.3f} k2 of floor, under {RISER_ZONE_MIN_AREA / 1e6:g}")
        if width < RISER_ZONE_MIN_WIDTH:
            why.append(f"{width:g} units across, under {RISER_ZONE_MIN_WIDTH:g}")
        if why:
            report.add(warning(
                "Z76",
                f"window {window.id} feeds zone {window.zone_name}, which has "
                + " and ".join(why)
                + ": zombies climb in where there is no room to fight them",
                window.id,
            ))


# ---------------------------------------------------------------------------
# Z77: void walls
# ---------------------------------------------------------------------------
#: Materials that render as a near-black void across a whole wall.  Each is
#: here because a render showed it: ``t7_metal_worn_iron_dark`` on
#: zm_dmv's records room east wall.  Fine as trim
#: or a block face; a whole wall of it reads as a hole in the map.
DARK_WALL_MATERIALS = frozenset({"t7_metal_worn_iron_dark"})


def _check_dark_walls(bp, report: Report) -> None:
    from ..blueprint.elements import Room, Yard

    for kind in (Room, Yard):
        for room in bp.elements(kind):
            materials = getattr(room, "materials", None)
            if materials is None:
                continue
            dark = [
                side.name.lower()
                for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST)
                if materials.for_side(side).name in DARK_WALL_MATERIALS
            ]
            if dark:
                report.add(warning(
                    "Z77",
                    f"room {room.id}: the whole {', '.join(dark)} wall(s) in "
                    f"{materials.for_side(getattr(Side, dark[0].upper())).name}, "
                    "which renders as a black void; use it for trim, not a wall",
                    room.id,
                ))


def check_layout_rules(bp) -> Report:
    """Z74, Z75, Z76 and Z77 over a blueprint."""
    report = Report()
    # _check_omni_overlap is NOT run: see OMNI_OVERLAP_LIMIT.  The bake's own
    # log is read instead (verify.stages, ``shadows_dropped``).
    _check_stamping(bp, report)
    _check_tall_walk_through(bp, report)
    _check_risers(bp, report)
    _check_dark_walls(bp, report)
    return report
