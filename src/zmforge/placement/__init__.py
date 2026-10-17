"""Placement: where a thing goes, stated as rules rather than as coordinates.

This package is the layout half of set dressing, built out of the four ideas
worth taking from existing level-dressing tools:

``relations``
    a constraint vocabulary -- ``StableAgainst``, ``SupportedBy``, ``OnWall``,
    ``HangsFrom``, ``Touching``, ``CoPlanar``, ``NoOverlap`` -- and a mount
    kind read off a model's own measured box;
``clearance``
    the room a model needs, as the Minkowski sum of its own footprint with a
    player-sized disc or a front-apron segment, plus a circulation count and a
    focal-point score for a room;
``scatter``
    a modifier stack: point generators and transform modifiers as separate
    passes over one point list, with keep-clear zones as negative shapes in
    the same stack rather than as special cases in the placer;
``reachability``
    a flood from declared seeds -- spawns and risers -- over a walkable grid,
    reporting everything the flood does not reach;
``groups``
    a model family placed and validated as one unit;
``audit``
    the same relations run over a finished blueprint or a parsed ``.map``, as
    a registered check, so the rule that chooses a position and the rule that
    judges one are the same rule.

**Attribution.**  The ideas come from named projects and are reimplemented
here; no code is copied from any of them.

* the relation vocabulary and the hard/soft split: Infinigen
  (princeton-vl/infinigen, BSD-3-Clause);
* sampling a wall asset's height on the wall plane, and placing a model family
  as one unit that is rejected if any member intersects: ProcTHOR
  (allenai/procthor, Apache-2.0);
* clearance as a Minkowski sum, circulation as a connected-component count,
  and emphasis as a focal point: Merrell et al., *Interactive Furniture Layout
  Using Interior Design Guidelines*, SIGGRAPH 2011 (a paper, not code);
* flood-filling from seed points and discarding what is not reached: navcat
  (isaac-mason/navcat, MIT), whose implementation is JavaScript;
* the modifier stack and negative shapes: ProtonScatter
  (HungryProton/scatter, MIT), whose implementation is GDScript.

Nothing in this package is taken from GPL, NVIDIA-research-licence or
academic-only projects, and nothing is taken from Treyarch.

**Nothing here is wired into the placer yet.**  :mod:`zmforge.recipes.props`
still places everything, and switching it over is still to do.
"""

from __future__ import annotations

from . import clearance, geometry, groups, reachability, relations, scatter
from .geometry import (
    Poly2,
    convex_hull,
    minkowski_disc,
    minkowski_segment,
    rotate,
    segment_distance,
    unit_hash,
)
from .relations import (
    CoPlanar,
    HangsFrom,
    MountKind,
    NoOverlap,
    OnWall,
    PLAYER_HEIGHT,
    PLAYER_RADIUS,
    Placed,
    StableAgainst,
    SupportedBy,
    Surface,
    Touching,
    Violation,
    Wall,
    mount_kind_of_box,
    walls_of_rect,
)

#: The vocabulary every layer shares is re-exported here; everything else is
#: reached through its own module (``placement.scatter.Stack``,
#: ``placement.reachability.flood``).  Deliberate: three modules define a
#: ``Link``, a ``Report`` or a ``Finding`` of their own, and flattening them
#: into one namespace would mean the same word naming a required circulation
#: link in one line and a jump connection in the next.
__all__ = [
    "clearance",
    "geometry",
    "groups",
    "reachability",
    "relations",
    "scatter",
    "Poly2",
    "convex_hull",
    "minkowski_disc",
    "minkowski_segment",
    "rotate",
    "segment_distance",
    "unit_hash",
    "CoPlanar",
    "HangsFrom",
    "MountKind",
    "NoOverlap",
    "OnWall",
    "PLAYER_HEIGHT",
    "PLAYER_RADIUS",
    "Placed",
    "StableAgainst",
    "SupportedBy",
    "Surface",
    "Touching",
    "Violation",
    "Wall",
    "mount_kind_of_box",
    "walls_of_rect",
]
