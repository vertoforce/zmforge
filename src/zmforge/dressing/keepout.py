"""Keep-outs: the floor a placer must leave empty.

A keep-out is a :class:`~zmforge.spatial.Bounds` box a placer is handed so
nothing solid lands in it.  Units are map units (inches).
"""

from __future__ import annotations

from ..spatial import Bounds

__all__ = ["window_keepouts"]


def window_keepouts(bp, *, approach: float | None = None, side: float | None = None,
                    below: float = 10.0, height: float | None = None) -> list[Bounds]:
    """One keep-out box per barricade window: the floor either side of its
    opening that a zombie climbs through and a player rebuilds from, from
    *below* under the floor to the opening's top (or *height* over the
    floor, to keep a raised deck clear too).  With no arguments it is exactly the
    ``Z57`` zone (:func:`zmforge.verify.looks.window_zones`); a recipe that
    wants more room passes a larger *approach* or *side*.  Hand the boxes to
    the recipe's placer as keep-outs so nothing solid lands there."""
    from ..verify.looks import WINDOW_APPROACH, WINDOW_SIDE, window_zones

    out: list[Bounds] = []
    for _win, _room, (x0, y0, x1, y1), floor, top in window_zones(
            bp, approach=WINDOW_APPROACH if approach is None else approach,
            side=WINDOW_SIDE if side is None else side):
        z1 = floor + height if height is not None else top
        out.append(Bounds.between((x0, y0, floor - below), (x1, y1, z1)))
    return out
