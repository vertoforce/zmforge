"""Put one prop where it belongs, by its measured box rather than its origin.

Half the stock palette carries its geometry off to one side of its origin,
authored about its middle rather than its feet, and facing a different way
at yaw 0 from model to model.  Every function here reads the measured box
(:func:`zmforge.recipes.props.collision_box`) or the measured front
(``MODEL_FRONT``, ``_mount_face``) so a recipe says *where the prop should
be* and gets back the origin and yaw that put it there.

Units are map units (1 unit = 1 inch), yaw in degrees.  Every placer
returns a :data:`PropSpec` tuple for :meth:`Blueprint.place_props`; none of
them touch the blueprint.

The prop facts live in :mod:`zmforge.recipes.props`, and importing that
runs the whole ``recipes`` package, which imports this module: the facts
are therefore looked up at call time (:func:`_facts`), never at import.
"""

from __future__ import annotations

import math
from typing import Any

from ..blueprint.elements import PropScatter
from ..placement.relations import Placed
from ..spatial import Bounds, Facing, Point, Side

__all__ = [
    "PropSpec",
    "rest_on",
    "top_of",
    "centred",
    "on_floor",
    "on_surface",
    "mounted",
    "seated",
    "turned_box",
    "on_wall",
    "on_room_wall",
    "fit_within",
    "floor_boxes",
    "floor_footprints",
]

#: What every placer returns and :meth:`Blueprint.place_props` takes:
#: ``(model, origin, yaw, scale, solid)``, or the short ``(model, origin,
#: yaw)`` a wall fixture uses (scale 1, solid).
PropSpec = tuple


def _facts() -> Any:
    """:mod:`zmforge.recipes.props`, imported on first use (see the module
    docstring for why not at import)."""
    from ..recipes import props

    return props


def rest_on(model: str, surface_z: float) -> float:
    """The origin height that puts *model*'s underside on *surface_z*.

    Raises ``KeyError`` for a model with no measured box: it would also be
    a prop with no collmap, so a guess here hides a real fault."""
    box = _facts().collision_box(model)
    if box is None:
        raise KeyError(f"{model}: no measured box, so nothing can be rested on a surface")
    return surface_z - box[0][2]


def top_of(model: str, surface_z: float) -> float:
    """The height of *model*'s top once it rests on *surface_z*: where the
    next thing stacked on it goes."""
    box = _facts().collision_box(model)
    if box is None:
        raise KeyError(f"{model}: no measured box")
    return surface_z + (box[1][2] - box[0][2])


def centred(model: str, x: float, y: float, z: float, yaw: float,
            *, solid: bool = False, scale: float = 1.0) -> PropSpec:
    """*model* with its measured footprint (not its origin) centred on
    (*x*, *y*), origin at height *z*, turned *yaw*.  The checks judge the
    footprint, so the origin is backed out of where the box should be."""
    (x0, y0, _z0), (x1, y1, _z1) = _facts().collision_box(model)
    cx, cy = (x0 + x1) / 2.0 * scale, (y0 + y1) / 2.0 * scale
    turn = math.radians(yaw)
    ox = cx * math.cos(turn) - cy * math.sin(turn)
    oy = cx * math.sin(turn) + cy * math.cos(turn)
    return (model, Point(x - ox, y - oy, z), yaw % 360.0, scale, solid)


def on_floor(model: str, x: float, y: float, floor_z: float, yaw: float = 0.0,
             *, solid: bool = True, scale: float = 1.0) -> PropSpec:
    """A floor-standing *model*: footprint centred on (*x*, *y*), underside
    on *floor_z*.  Solid by default; pass ``solid=False`` for litter."""
    return centred(model, x, y, rest_on(model, floor_z), yaw, solid=solid, scale=scale)


def on_surface(model: str, x: float, y: float, top_z: float, yaw: float = 0.0,
               *, scale: float = 1.0) -> PropSpec:
    """Clutter resting on a desk, shelf or counter whose top is *top_z*:
    footprint centred on (*x*, *y*), never solid.  Put it through
    :func:`fit_within` first when the surface is small."""
    return centred(model, x, y, rest_on(model, top_z), yaw, solid=False, scale=scale)


def mounted(model: str, position: Point, facing: Facing) -> PropSpec:
    """A wall fixture with its origin at *position*, turned to look *facing*
    (out of its wall).  Uses the measured mount face, so a sign, a clock or
    a notice board all come out facing the room; doing it by hand is how ten
    of eleven wall buys once shipped facing their own walls."""
    return (model, position, (facing.world_yaw - _facts()._mount_face(model)) % 360.0)


def seated(model: str, position: Point, facing: Facing, *, solid: bool = True) -> PropSpec:
    """A chair or bench at *position*, turned so whoever sits in it looks
    *facing* (from the measured ``MODEL_FRONT``, off the backrest)."""
    yaw = (facing.world_yaw - _facts().MODEL_FRONT.get(model, 0.0)) % 360.0
    return (model, position, yaw, 1.0, solid)


def turned_box(model: str, yaw: float) -> tuple[float, float, float, float]:
    """*model*'s measured plan box turned by *yaw* about its origin, as
    ``(x0, y0, x1, y1)`` offsets from the origin."""
    (x0, y0, _z0), (x1, y1, _z1) = _facts().collision_box(model)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    xs, ys = [], []
    for px, py in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        xs.append(px * c - py * s)
        ys.append(px * s + py * c)
    return min(xs), min(ys), max(xs), max(ys)


def on_wall(model: str, facing: Facing, along: float, wall: float, *,
            centre_z: float | None = None, bottom_z: float | None = None,
            gap: float = 0.5) -> PropSpec:
    """*model* hung flat on a wall, looking *facing*: its turned body's back
    *gap* off the wall plane *wall* (the x of an east/west wall, the y of a
    north/south one), centred on *along* on that wall, and either centred on
    height *centre_z* or with its underside at *bottom_z* (give exactly one).
    Unlike :func:`mounted` it measures the turned box, so a model whose body
    sits well off its origin still lands on the wall."""
    if (centre_z is None) == (bottom_z is None):
        raise ValueError("on_wall: give exactly one of centre_z and bottom_z")
    yaw = mounted(model, Point(0.0, 0.0, 0.0), facing)[2]
    (_bx0, _by0, z0), (_bx1, _by1, z1) = _facts().collision_box(model)
    x0, y0, x1, y1 = turned_box(model, yaw)
    if facing is Facing.NORTH:
        ox, oy = along - (x0 + x1) / 2.0, wall + gap - y0
    elif facing is Facing.SOUTH:
        ox, oy = along - (x0 + x1) / 2.0, wall - gap - y1
    elif facing is Facing.EAST:
        ox, oy = wall + gap - x0, along - (y0 + y1) / 2.0
    else:
        ox, oy = wall - gap - x1, along - (y0 + y1) / 2.0
    z = centre_z - (z0 + z1) / 2.0 if centre_z is not None else bottom_z - z0
    return (model, Point(ox, oy, z), yaw)


#: The wall a letter names, the way a piece on it looks, and which side of
#: the room's interior its plane is.
_ROOM_WALLS = {
    "n": (Facing.SOUTH, "maxs", "y"), "s": (Facing.NORTH, "mins", "y"),
    "e": (Facing.WEST, "maxs", "x"), "w": (Facing.EAST, "mins", "x"),
}


def on_room_wall(model: str, room, wall: str | Side, along: float, bottom: float,
                 *, gap: float = 0.5) -> PropSpec:
    """:func:`on_wall` on one of *room*'s walls (``"n"``, ``"s"``, ``"e"``,
    ``"w"`` or a :class:`Side`): centred at *along* on it, its underside
    *bottom* above the room's floor, looking into the room.  *room* needs
    ``.interior`` and ``.floor_z``."""
    key = wall if isinstance(wall, str) else wall.name[0].lower()
    facing, end, axis = _ROOM_WALLS[key]
    plane = getattr(getattr(room.interior, end), axis)
    return on_wall(model, facing, along, plane, bottom_z=room.floor_z + bottom, gap=gap)


def fit_within(model: str, x: float, y: float, yaw: float, box: Bounds, *,
               scale: float = 1.0, inset: float = 2.0) -> tuple[float, float, float] | None:
    """``(x, y, yaw)`` for *model* moved so its turned, measured footprint
    lies inside *box*'s plan less *inset* (a shelf, desk, dresser or counter
    top), or ``None`` when it fits neither at *yaw*, a quarter turn from it,
    nor square to the box.  Put surface items through this instead of at the
    surface's middle: an item wider than the board behind it pokes into the
    wall (as shelf items on zm_corn_maze did)."""
    lo, hi = _facts().MODEL_BOX[model]
    square = round(yaw / 90.0) * 90.0
    bx0, bx1 = box.mins.x + inset, box.maxs.x - inset
    by0, by1 = box.mins.y + inset, box.maxs.y - inset
    for turn in (yaw, yaw + 90.0, square, square + 90.0):
        a = math.radians(turn)
        c, s = math.cos(a), math.sin(a)
        corners = [(px * scale * c - py * scale * s, px * scale * s + py * scale * c)
                   for px in (lo[0], hi[0]) for py in (lo[1], hi[1])]
        fx0, fx1 = min(p[0] for p in corners), max(p[0] for p in corners)
        fy0, fy1 = min(p[1] for p in corners), max(p[1] for p in corners)
        if fx1 - fx0 > bx1 - bx0 or fy1 - fy0 > by1 - by0:
            continue
        nx = min(max(x, bx0 - fx0), bx1 - fx1)
        ny = min(max(y, by0 - fy0), by1 - fy1)
        return nx, ny, turn
    return None


def _placed_props(bp):
    """Every measured prop in *bp* as ``(prop, Placed)``."""
    collision_box = _facts().collision_box
    for scatter in bp.elements(PropScatter):
        for p in scatter.props:
            box = collision_box(p.model)
            if box is None:
                continue
            yield p, Placed.from_model(p.model, box, (p.origin.x, p.origin.y, p.origin.z),
                                       p.yaw, p.scale, solid=p.solid, ident=p.id)


def floor_boxes(bp, room, *, reach: float = 4.0, low: float = 12.0
                ) -> list[tuple[float, float, float, float, bool]]:
    """Plan boxes ``(x0, y0, x1, y1, solid)`` of the props already standing
    in *room* (origin within *reach* of its interior): every solid prop,
    and the non-solid ones whose underside is within *low* of the floor.
    Hand it to a strewer so new litter steps round what is there."""
    b, fz = room.interior, room.floor_z
    out = []
    for p, pl in _placed_props(bp):
        if not (b.mins.x - reach <= pl.x <= b.maxs.x + reach
                and b.mins.y - reach <= pl.y <= b.maxs.y + reach):
            continue
        if not p.solid and pl.z_low > fz + low:
            continue
        c, s = abs(math.cos(math.radians(pl.yaw))), abs(math.sin(math.radians(pl.yaw)))
        ex, ey = pl.hx * c + pl.hy * s, pl.hx * s + pl.hy * c
        out.append((pl.x - ex, pl.y - ey, pl.x + ex, pl.y + ey, bool(p.solid)))
    return out


def floor_footprints(bp, room, *, base_below: float = 4.0) -> list[Bounds]:
    """Every measured prop standing on *room*'s floor (origin within one
    unit of its interior, underside no more than *base_below* over the
    floor: a skirting's height), as an axis-aligned box from the floor to
    its top."""
    out = []
    box = room.interior
    for _p, placed in _placed_props(bp):
        x0, y0, x1, y1 = placed.footprint.bounds
        if not (box.mins.x - 1.0 <= placed.x <= box.maxs.x + 1.0
                and box.mins.y - 1.0 <= placed.y <= box.maxs.y + 1.0):
            continue
        if placed.z_low > room.floor_z + base_below:
            continue
        out.append(Bounds.between((x0, y0, room.floor_z),
                                  (x1, y1, max(placed.z_high, room.floor_z + 1.0))))
    return out
