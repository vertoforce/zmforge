"""The optional lore of Cemetery Quest: what happened at Hollow Rest, and the
readables that only a player who reads the other readables goes looking for.

**The story** (principle P11, ``docs/map-principles.md``).  Ezekiel Hollow
founded Hollow Rest in 1851.  The Graves family kept the grounds, the Diggs
family dug the graves, and Dr. Cornelius Moore signed the certificates.  The
Founder was afraid of being buried alive: when Dr. Moore declared him dead
on 28 October 1897 ("cause: none found") he lay three nights in the chapel,
and the groundskeeper, Amos Graves, kept the sarcophagus key and was to seal
the crypt at dawn after the third night.  Jonah Diggs, sacked that year for
digging up graves (Uncle Gary's silver, parts sold to Dr. Moore's lectures),
wanted that key.  At 11:54 on 31 October 1897 Amos heard a shovel on the
knoll, left his kettle on and a sign saying BACK IN 5 MINUTES, and hid the
key in the hole Jonah was digging for him (the Open Grave: the stone Jonah
carved for AMOS now says YOU).  At 11:59 the Founder came back for his
coffin; the night nurse, Agnes, got "just a little bite"; Dave, who came for
the sandwiches, did not leave.  Inside the gates it has been 11:59 ever
since.  Jonah dug his own and is THE GRAVEDIGGER; Amos was never found, his
name on the Graves plate says ON SHIFT, and his voice still reads the PA.  The
quest is his last shift: finishing it lets everyone lie down.

**The optional discovery.**  Amos's real grave is a plain stone with no name
under the dead oak in the south-west corner of the gate lawn.  Nothing on
screen points at it; the groundskeeper's log (the open book on the potting
crate in the shed) says where it is, and the memorial at the gate, the
ON SHIFT line on the Graves plate and the chiselled-off name on the Open Grave's stone
say why somebody would look.  The hymn board (31, 10, 1897) and three stones
dated 31 OCT 1897, 11:59 give the night away to anybody comparing dates.

Nothing here is a quest step; the quest (:mod:`.cemetery_quest`) is unchanged.
The words are in :data:`zmforge.recipes.cemetery.EPITAPHS` and
:data:`~zmforge.recipes.cemetery.NOTICE_LINES`; this module only places the
props they hang on and records the keys in ``features`` for
:func:`~zmforge.recipes.cemetery_dressing.wire_notices`.
"""

from __future__ import annotations

import math
from typing import Mapping

from ..blueprint.elements import Massing
from ..blueprint.model import Blueprint
from ..spatial import Facing, Point
from . import cemetery_kit as kit

__all__ = ["dress_lore", "LORE_EPITAPHS", "LORE_NOTICES", "STORY", "clear_of_paths"]

#: The facts every readable must agree with (``tests/test_cemetery_lore.py``).
STORY = {
    "cemetery": "HOLLOW REST",
    "founded": 1851,
    "founder": "EZEKIEL HOLLOW",
    "declared_dead": "28 OCT 1897",
    "night": "31 OCT 1897",
    "time": "11:59",
    "groundskeeper": "AMOS GRAVES",
    "gravedigger": "JONAH DIGGS",
    "doctor": "DR. CORNELIUS MOORE",
    "nurse": "AGNES",
    #: The families with a tomb, and where their tomb stands.
    "families": {"MOORE": "hills", "DIGGS": "hills", "GRAVES": "row", "HOLLOW": "vault"},
}

#: Readables this module places: EPITAPHS keys and NOTICE_LINES keys.
LORE_EPITAPHS = ("amos",)
LORE_NOTICES = ("shift_log", "graves_plot", "moore_plot", "returned_plot")

#: Path centre lines another pass lays paths along (x0, x1, y) and (x, y0, y1),
#: and how far lore props stand off them.
_PATHS_EW = ((-1300.0, 1200.0, 0.0),)
_PATHS_NS = ((200.0, 0.0, 1800.0),)
PATH_CLEAR = 170.0


def clear_of_paths(x: float, y: float, r: float = 0.0) -> bool:
    """Whether a footprint of radius ``r`` at (x, y) stands ``PATH_CLEAR``
    off every path centre line."""
    for x0, x1, py in _PATHS_EW:
        if x0 - PATH_CLEAR <= x <= x1 + PATH_CLEAR and abs(y - py) < PATH_CLEAR + r:
            return False
    for px, y0, y1 in _PATHS_NS:
        if y0 - PATH_CLEAR <= y <= y1 + PATH_CLEAR and abs(x - px) < PATH_CLEAR + r:
            return False
    return True


def _spot(d, x: float, y: float, hx: float, hy: float, *, reach: float, what: str,
          inside=None) -> tuple[float, float]:
    """The free spot nearest (x, y), on rings out to ``reach``, clear of the
    paths and inside ``inside`` (a room interior) when given.  Raises when
    there is none, so a planned readable never silently drops out."""
    r = math.hypot(hx, hy)
    tries = [(x, y)] + [(x + k * 12.0 * math.cos(a), y + k * 12.0 * math.sin(a))
                        for k in range(1, int(reach // 12) + 1)
                        for a in [n * math.pi / 8 for n in range(16)]]
    for tx, ty in tries:
        if inside is not None and not (inside.mins.x + r + 8 <= tx <= inside.maxs.x - r - 8
                                       and inside.mins.y + r + 8 <= ty <= inside.maxs.y - r - 8):
            continue
        if clear_of_paths(tx, ty, r) and d.free(tx, ty, hx, hy):
            return tx, ty
    raise ValueError(f"lore {what} found no free spot within {reach:g} of ({x:g}, {y:g})")


def _block_centre(bp: Blueprint, prefix: str) -> tuple[float, float]:
    """Plan centre of the first brush block whose id starts with ``prefix``."""
    from ..blueprint.model import _solid_bounds

    from ..blueprint.elements import PropScatter

    for m in bp.elements(Massing):
        if m.id.startswith(prefix):
            b = _solid_bounds(m.solids[0])
            return (b.mins.x + b.maxs.x) / 2.0, (b.mins.y + b.maxs.y) / 2.0
    # A dead tree is a model (cemetery_dressing._trees places
    # it as its own scatter, ``dress_<area>_<ident><n>``): its trunk is the
    # prop's origin.
    for s in bp.elements(PropScatter):
        if s.id.endswith(f"_{prefix}") and s.props:
            return s.props[0].origin.x, s.props[0].origin.y
    raise ValueError(f"no block {prefix}* to hang the lore on")


def _marker_post(d, x: float, y: float, *, facing: Facing, ident: str) -> float:
    """A short iron post with a small dark plate on it, the plate square to
    ``facing``: a plot's name marker.  Returns the ground under it."""
    g = d.low(x - 12, y - 12, x + 12, y + 12)
    kit._box(d.bp, x - 2, y - 2, g - kit.BURY, x + 2, y + 2, g + 34.0, kit.IRON, f"{ident}_post")
    if facing in (Facing.NORTH, Facing.SOUTH):
        kit._box(d.bp, x - 12, y - 1.5, g + 30.0, x + 12, y + 1.5, g + 46.0, kit.BLACK,
                 f"{ident}_plate")
    else:
        kit._box(d.bp, x - 1.5, y - 12, g + 30.0, x + 1.5, y + 12, g + 46.0, kit.BLACK,
                 f"{ident}_plate")
    d.claim(x, y, 24.0)
    return g


_FRONT = {Facing.NORTH: (0.0, 1.0), Facing.SOUTH: (0.0, -1.0), Facing.EAST: (1.0, 0.0),
          Facing.WEST: (-1.0, 0.0)}


def dress_lore(d, bp: Blueprint, rooms: Mapping[str, object], features: dict) -> None:
    """Place the lore readables (after every area is dressed, so nothing
    else moves) and record where each one is read from."""
    # 1. The groundskeeper's log: an open book on the potting crate in the
    #    shed, where he took his breaks.  Nowhere near the bench and its shovel.
    shed = rooms["shed"]
    f = shed.floor_z
    crate = next(item for item in d.pending["dress_shed_potting"]
                 if item[0] == "p7_crate_wood_01_short")
    cx, cy = crate[1].x, crate[1].y
    d.prop("shed", "lore", "p7_book_vintage_open_01", cx - 8.0, cy - 10.0, 15.0,
           surface=f + 31.0, check=False, solid=False)
    features["notices"]["shift_log"] = Point(cx, cy, f + 40.0)

    # 2. Amos's own grave: a plain stone, no candle, facing the gate from
    #    beside the dead oak in the south-west corner of the gate lawn.
    gate = rooms["gate"].interior
    tx, ty = _block_centre(bp, "gate_tree2")
    sx, sy = _spot(d, tx + 70.0, ty + 40.0, 20.0, 20.0, reach=150.0, what="amos stone",
                   inside=gate)
    g = d.low(sx - 16, sy - 16, sx + 16, sy + 16)
    kit.headstone(bp, sx, sy, g, facing=Facing.WEST, ident="lore_amos", width=24.0,
                  height=30.0, material=kit.DARK_STONE)
    d.claim(sx, sy, 28.0)
    # "The soil on top is fresh": a dirt mound in front of the stone, so the
    # line has something under it.  A kerb 6
    # units proud, walked over; the reading spot is on it.
    mx = sx - 44.0
    kit.grave_mound(bp, mx, sy, d.low(mx - 36, sy - 14, mx + 36, sy + 14), facing=Facing.WEST,
                    ident="lore_amos_mound")
    d.claim(mx, sy, 40.0)
    features["epitaphs"]["amos"] = Point(sx - 30.0, sy, g + 30.0)

    # 3. The family plots' name markers, each outside its plot, facing out.
    #    Gate: the first Graves keepers, by the gate they kept.
    for key, (x, y), facing, within in (
        ("graves_plot", (-1330.0, 410.0), Facing.WEST, gate),
        # Behind the MOORE mausoleum (it faces east): more Moores.
        ("moore_plot", (-640.0, -590.0), Facing.SOUTH, rooms["hills"].interior),
        # Beside the Founder's needle: the plot of the returned.
        ("returned_plot", (1020.0, -380.0), Facing.SOUTH, rooms["hills"].interior),
    ):
        px, py = _spot(d, x, y, 14.0, 14.0, reach=120.0, what=key, inside=within)
        g = _marker_post(d, px, py, facing=facing, ident=f"lore_{key}")
        fx, fy = _FRONT[facing]
        features["notices"][key] = Point(px + 26.0 * fx, py + 26.0 * fy, g + 36.0)
