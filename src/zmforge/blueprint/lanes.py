"""The approach lane: a clear walk-up in front of every buyable, on every map.

WHY THIS IS A BLUEPRINT RULE AND NOT A RECIPE ONE
-------------------------------------------------
A buyable can be closed in by props that no placer put there on purpose: on
``zm_corn_maze``, corn stalks laid with no lane rule leave every route into
the stand box in front of a perk or a mystery box running through
walk-through stalks (``Z48``).  The
prop recipes already keep an apron clear (:func:`zmforge.recipes.props._clear_of_items`,
:meth:`~zmforge.blueprint.model.Blueprint.interactive_blocks`), but only for the
placers that ask.  Corn, vignettes and any hand-listed ``place_props`` call do
not ask, so the rule has to live where every prop goes in:
:meth:`Blueprint._install`.

THE RULE
--------
Each machine, mystery box, Wunderfizz, power switch and wall buy owns its
apron (:attr:`zmforge.blueprint.reach.Keep.aprons`): the item's width plus
32 units a side, :data:`APPROACH_LANE` (96) units deep in front of it (128 for
the box and pack-a-punch), a player tall.  A floor-standing prop whose own box
reaches into that lane and rises more than :data:`LANE_STEP_OVER` over the
lane's floor is taken out, whichever went in first: a prop installed into a
lane is dropped from its scatter, and a buyable installed over props drops
them.  One exception: a walk-through prop against a wall buy's own wall,
beside its chalk and not in front of it (:func:`beside_the_chalk`; a lined
corn wall).  Floor clutter a player steps over (a newspaper, a leaf) stays, and so
does anything hung on a wall or a ceiling (:func:`zmforge.recipes.props.mount_kind`).

A prop whose model has no measured box is left alone, for the reason
:mod:`zmforge.verify.approach` gives: a footprint invented for it is a removal
invented for it.  ``Z48`` still counts it as unmeasured.

Every removal is recorded on :attr:`Blueprint.lane_cleared` (prop id, the item
it was cleared for), so a map that lost a set piece to this rule says so.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from . import reach

if TYPE_CHECKING:  # pragma: no cover
    from .elements import Element, Prop

__all__ = ["APPROACH_LANE", "CHALK_MARGIN", "CHALK_SIDE_DEPTH", "CHALK_SIDE_STEM", "LANE_STEP_OVER",
           "beside_the_chalk", "lane_keeps", "blocks_lane", "enforce"]

#: How deep the clear lane in front of a buyable is: :data:`reach.APRON_DEPTH`.
APPROACH_LANE = reach.APRON_DEPTH

#: A prop that rises at most this far above the lane's floor is walked over
#: and may stay.  The same 24 units
#: :data:`zmforge.recipes.props.ITEM_BLOCKS_HEIGHT` uses for "tall enough to
#: stand between a player and the buy".
LANE_STEP_OVER = 24.0

#: A walk-through prop against a wall buy's wall, beside its chalk
#: (:func:`beside_the_chalk`), is not in its lane: how far its stem may stand
#: from the wall, how far out its box may reach, and how much wall it leaves
#: bare either side of the chalk.  The lane is 96 deep; past 48 out the floor
#: a player stands on is clear.
CHALK_SIDE_STEM = 26.0
CHALK_SIDE_DEPTH = 48.0
CHALK_MARGIN = 16.0

_BOX_CACHE: dict = {}


def _is_buyable(element) -> bool:
    from .elements import Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz

    return isinstance(element, (Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz))


def lane_keeps(elements) -> list[reach.Keep]:
    """The keeps of every buyable among ``elements`` (doors are not buyables)."""
    keeps = []
    for element in elements:
        if not _is_buyable(element):
            continue
        keep = reach.keep_of(element)
        if keep is not None and keep.aprons:
            keeps.append(keep)
    return keeps


def _table() -> dict:
    if not _BOX_CACHE:
        from ..props.origins import drawn_boxes
        from ..recipes.props import MODEL_BOX

        _BOX_CACHE.update(drawn_boxes(MODEL_BOX))
    return _BOX_CACHE


def _prop_span(prop):
    """World-space ``(x0, y0, z0, x1, y1, z1)`` of a floor prop, or ``None``."""
    from ..props.origins import drawn_box
    from ..recipes.props import MOUNT_FLOOR, mount_kind

    if mount_kind(prop.model) != MOUNT_FLOOR:
        return None
    local = drawn_box(prop.model, prop.collision_box) or _table().get(prop.model)
    if local is None:
        return None
    (x0, y0, z0), (x1, y1, z1) = local
    scale = prop.scale
    angle = math.radians(prop.yaw)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx = (x0 + x1) / 2.0 * scale
    cy = (y0 + y1) / 2.0 * scale
    wx = prop.origin.x + cx * cos_a - cy * sin_a
    wy = prop.origin.y + cx * sin_a + cy * cos_a
    hx = ((x1 - x0) * abs(cos_a) + (y1 - y0) * abs(sin_a)) * scale / 2.0
    hy = ((x1 - x0) * abs(sin_a) + (y1 - y0) * abs(cos_a)) * scale / 2.0
    return (wx - hx, wy - hy, prop.origin.z + z0 * scale,
            wx + hx, wy + hy, prop.origin.z + z1 * scale)


#: No prop in the palette reaches further than this from its origin in plan;
#: a prop whose origin is further than this outside every lane is not
#: measured at all, which is what keeps a map of forty thousand stalks cheap.
_NEAR = 160.0


def _near(prop, keep: reach.Keep) -> bool:
    x, y = prop.origin.x, prop.origin.y
    return any(
        lane.mins.x - _NEAR <= x <= lane.maxs.x + _NEAR
        and lane.mins.y - _NEAR <= y <= lane.maxs.y + _NEAR
        for lane in keep.aprons
    )


def beside_the_chalk(prop, keep: reach.Keep, span) -> bool:
    """A walk-through prop (a lining stalk) standing against the wall a wall
    buy hangs on, to either side of its chalk: its stem within
    :data:`CHALK_SIDE_STEM` of the wall, its box no further out than
    :data:`CHALK_SIDE_DEPTH`, and clear of the chalk by :data:`CHALK_MARGIN`
    along the wall.  It leaves the drawing and the floor a player stands on
    to use it clear, so it is not in the lane.

    Without this, the lane rule would bare the whole 112-unit apron of every
    wall buy on a corn wall, which reads as a flat painted wall with nothing
    growing on it."""
    if keep.face is None or getattr(prop, "solid", False):
        return False
    body, face = keep.body, keep.face
    bc, fc = body.centre, face.centre
    if abs(fc.x - bc.x) >= abs(fc.y - bc.y):
        out = 1.0 if fc.x > bc.x else -1.0
        wall = body.mins.x if out > 0 else body.maxs.x
        n0, n1, a0, a1 = span[0], span[3], span[1], span[4]
        stem, along0, along1 = prop.origin.x, body.mins.y, body.maxs.y
    else:
        out = 1.0 if fc.y > bc.y else -1.0
        wall = body.mins.y if out > 0 else body.maxs.y
        n0, n1, a0, a1 = span[1], span[4], span[0], span[3]
        stem, along0, along1 = prop.origin.y, body.mins.x, body.maxs.x
    reach_out = max((n0 - wall) * out, (n1 - wall) * out)
    if not -CHALK_SIDE_STEM <= (stem - wall) * out <= CHALK_SIDE_STEM or reach_out > CHALK_SIDE_DEPTH:
        return False
    return a1 <= along0 - CHALK_MARGIN or a0 >= along1 + CHALK_MARGIN


def blocks_lane(prop, keep: reach.Keep) -> bool:
    """Does this prop stand in ``keep``'s approach lane, tall enough to matter?"""
    if not _near(prop, keep):
        return False
    span = _prop_span(prop)
    if span is None:
        return False
    if beside_the_chalk(prop, keep, span):
        return False
    x0, y0, z0, x1, y1, z1 = span
    for lane in keep.aprons:
        if x1 <= lane.mins.x or x0 >= lane.maxs.x:
            continue
        if y1 <= lane.mins.y or y0 >= lane.maxs.y:
            continue
        floor = lane.mins.z + reach.BASE_SLACK
        if z1 <= lane.mins.z or z0 >= lane.maxs.z:
            continue
        if z1 - max(z0, floor) <= LANE_STEP_OVER:
            continue
        return True
    return False


def enforce(blueprint, element: "Element") -> None:
    """Keep every approach lane clear after ``element`` goes in.

    Called by :meth:`Blueprint._install` for every element; does nothing for
    anything that is neither a prop scatter nor a buyable.
    """
    from .elements import PropScatter

    if isinstance(element, PropScatter):
        # The blueprint already holds one Keep per interactive placed so far
        # (Blueprint._keeps); the buyables' are the lanes.
        held = getattr(blueprint, "_keeps", None)
        if held is None:
            keeps = lane_keeps(blueprint.elements())
        else:
            by_id = getattr(blueprint, "_by_id", {})
            keeps = [k for k in held
                     if k.aprons and _is_buyable(by_id.get(k.element_id))]
        scatters = [element]
    elif _is_buyable(element):
        keeps = lane_keeps([element])
        scatters = blueprint.elements(PropScatter)
    else:
        return
    if not keeps:
        return
    cleared = getattr(blueprint, "lane_cleared", None)
    if cleared is None:
        cleared = []
        blueprint.lane_cleared = cleared
    removed: list[tuple[tuple, str]] = []
    for scatter in scatters:
        kept = []
        for prop in scatter.props:
            hit = next((k for k in keeps if blocks_lane(prop, k)), None)
            if hit is None:
                kept.append(prop)
            else:
                cleared.append((prop.id or scatter.id, hit.element_id))
                span = _prop_span(prop)
                if span is not None:
                    removed.append((span, hit.element_id))
        if len(kept) != len(scatter.props):
            scatter.props = kept
    history = getattr(blueprint, "_lane_removed", None)
    if history is None:
        history = []
        blueprint._lane_removed = history
    if removed:
        history.extend(removed)
        _drop_what_stood_on(blueprint, removed, cleared)
    if history and isinstance(element, PropScatter):
        # Something placed later on top of a prop an earlier lane took out
        # (the party spread on the break room's table) goes the same way.
        _drop_what_stood_on(blueprint, list(history), cleared, only=element)


def _drop_what_stood_on(blueprint, removed, cleared, only=None) -> None:
    """Take out whatever rested on a prop the lane took out.

    A donut left floating where its table was is a worse defect (``Z44``) than
    the table was; measured on zm_dmv's break room, where the power
    switch's lane took the table and left 32 things in the air.
    """
    from .elements import PropScatter

    history = getattr(blueprint, "_lane_removed", None)
    for _round in range(3):  # a jar on a crate on a table
        more = []
        for scatter in ([only] if only is not None else blueprint.elements(PropScatter)):
            kept = []
            for prop in scatter.props:
                o = prop.origin
                under = next(
                    (item for (x0, y0, z0, x1, y1, z1), item in removed
                     if x0 <= o.x <= x1 and y0 <= o.y <= y1 and z0 + 1.0 < o.z <= z1 + 8.0),
                    None,
                )
                if under is None:
                    kept.append(prop)
                else:
                    cleared.append((prop.id or scatter.id, under))
                    span = _prop_span(prop)
                    if span is not None:
                        more.append((span, under))
            if len(kept) != len(scatter.props):
                scatter.props = kept
        if not more:
            return
        if history is not None:
            history.extend(more)
        removed = more
