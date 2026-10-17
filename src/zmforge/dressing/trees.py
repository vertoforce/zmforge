"""Trees for open-air maps: realistic models by default, brush trees only as a fallback.

Brush trees (square trunks and limbs, or sheared bars) read as blocky
stand-ins, so every tree helper stands a model unless a recipe asks for
brushes by passing an empty model list:

* :data:`DEAD_TREES` -- five generated bare trees (two big gnarled ones,
  :data:`GNARLED_TREES`) with a CC0 bark photo
  (``props/dead_tree.py``), round tapering limbs, trunk at the origin.
  Solid like a stock tree, at the trunk only: their collmap and bullet mesh
  are ``recipes/props.KIT_COLLISION_BOX``, not the crown's box.
* :data:`ALBIZIA` -- the one realistic stock tree proven to link (leafy,
  571 x 548 x 764).  Used for depth in the far rows of a backdrop only, at
  varied scale and yaw so it does not read as one tree cloned.

A placed tree takes a random yaw and a scale from the height wanted, so the
same three models never line up the same way twice.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from ..spatial import Point
from .place import PropSpec

__all__ = ["ALBIZIA", "DEAD_TREES", "GNARLED_TREES", "TREELINE", "as_prop", "model_height",
           "model_reach", "pick", "tree", "trunk_clip"]

DEAD_TREES: tuple[str, ...] = ("zmf_prop_dead_tree_a", "zmf_prop_dead_tree_b",
                               "zmf_prop_dead_tree_c", "zmf_prop_dead_tree_d",
                               "zmf_prop_dead_tree_e")
#: The big gnarled ones (400-440 tall): play-area trees mix them in.
GNARLED_TREES: tuple[str, ...] = ("zmf_prop_dead_tree_d", "zmf_prop_dead_tree_e")
ALBIZIA = "p7_foliage_tree_albizia_tall_full"

#: Backdrop models per depth row (near to far): dead trees in front, then a
#: mix with leafy albizias further back for a wood behind the wall.
TREELINE: tuple[tuple[str, ...], ...] = (
    DEAD_TREES,
    DEAD_TREES + (ALBIZIA,),
    (ALBIZIA,) + DEAD_TREES + (ALBIZIA,),
)

#: Boxes of the tree models not in ``recipes/props.MODEL_BOX`` (the albizia's
#: is measured in ``recipes/corn_maze_assets.py``).
EXTRA_BOX = {ALBIZIA: ((-282.839, -269.59, -0.001), (288.115, 278.096, 763.581))}

#: How deep a generated tree's trunk foot sits under its model's z = 0
#: (``props/dead_tree.SINK``), per unit of scale.
SINK = 6.0
def _box(model: str):
    from ..recipes.props import MODEL_BOX

    box = MODEL_BOX.get(model) or EXTRA_BOX.get(model)
    if box is None:
        raise KeyError(f"{model} is not a measured tree model")
    return box


def model_height(model: str) -> float:
    (_x0, _y0, z0), (_x1, _y1, z1) = _box(model)
    return z1 - z0


def model_reach(model: str, scale: float = 1.0) -> float:
    """How far the crown reaches from the placed point, at *scale*."""
    (x0, y0, _z0), (x1, y1, _z1) = _box(model)
    return max(abs(x0), abs(x1), abs(y0), abs(y1)) * scale


def tree(model: str, x: float, y: float, ground: float, *, height: float,
         rng: random.Random, solid: bool | None = None) -> PropSpec:
    """*model* standing at (*x*, *y*) on *ground*, scaled to about *height*
    (+-8%), at a random yaw.  A generated tree's trunk lands on the point
    (its origin is the trunk foot) and is sunk by its root depth.  Solid by
    default for the generated trees (their collision is the trunk), not for
    the albizia (no collmap of its own)."""
    if solid is None:
        solid = model in DEAD_TREES
    scale = height / model_height(model) * rng.uniform(0.92, 1.08)
    yaw = rng.uniform(0.0, 360.0)
    (x0, y0, z0), (x1, y1, _z1) = _box(model)
    cx, cy = (x0 + x1) / 2.0 * scale, (y0 + y1) / 2.0 * scale
    t = math.radians(yaw)
    ox, oy = cx * math.cos(t) - cy * math.sin(t), cx * math.sin(t) + cy * math.cos(t)
    sink = SINK * scale if model in DEAD_TREES else 0.0
    return (model, Point(x - ox, y - oy, ground - z0 * scale - sink), yaw % 360.0, scale, solid)


#: The albizia's trunk half-width and height as a body box, generous (its
#: canopy is 571 across).
_ALBIZIA_TRUNK = ((-20.0, -20.0, 0.0), (20.0, 20.0, 230.0))


def as_prop(spec: PropSpec):
    """The placed tree as a :class:`~zmforge.blueprint.elements.Prop` whose
    ``collision_box`` is its trunk, not its crown.  That box is what a solid
    prop's collmap is cut from, and the reach checks (Z48 approach, routes,
    lanes, camping) read it as the part of a prop that stands in a player's
    way; a crown's box would wall off every perk and aisle under the
    branches, which a player walks straight through."""
    from ..blueprint.elements import Prop
    from ..recipes.props import KIT_COLLISION_BOX

    model, at, yaw, scale, solid = spec
    return Prop(model=model, origin=at, yaw=yaw, scale=scale, solid=solid,
                collision_box=KIT_COLLISION_BOX.get(model, _ALBIZIA_TRUNK))


def trunk_clip(bp, spec: PropSpec, ground: float, *, ident: str, height: float = 110.0) -> None:
    """A clip column at a walk-through tree's trunk (the stock albizia has no
    measured box to cut a collmap from), so players and zombies go round it.
    The column is :func:`as_prop`'s trunk box, scaled."""
    from ..materials import CLIP
    from ..spatial import Bounds

    model, at, _yaw, scale, _solid = spec
    half = _ALBIZIA_TRUNK[1][0] * scale if model == ALBIZIA else 12.0 * scale
    bp.add_block(Bounds.between((at.x - half, at.y - half, ground - 4.0),
                                (at.x + half, at.y + half, ground + height)),
                 CLIP, reachable=False, id=f"{ident}_clip", note="tree trunk clip")


def pick(models: Sequence[str], rng: random.Random, last: str | None = None) -> str:
    """One of *models*, never the same as *last* when there is a choice."""
    options = [m for m in models if m != last] or list(models)
    return rng.choice(options)
