"""The building blocks a recipe dresses a map with.

A recipe says what it wants where; these functions work out the origin,
yaw and brushes that put it there, by the measured boxes of the props, so
the know-how of one map's render reviews reaches every map by default.

* :mod:`.place` -- one prop by its measured box: :func:`on_floor`,
  :func:`on_surface`, :func:`on_wall`, :func:`on_room_wall`,
  :func:`mounted`, :func:`seated`, :func:`fit_within`, and what already
  stands in a room (:func:`floor_boxes`, :func:`floor_footprints`).
* :mod:`.fixtures` -- brushes hung or leaned: :func:`hanging_sign`,
  :func:`hang_bar`, :func:`sheared_bar`.
* :mod:`.spread` -- seeded litter and variety: :func:`litter_in_drifts`,
  :func:`litter_by_weight`, :func:`litter_heaps`, :func:`drift_points`,
  :func:`no_repeat`.
* :mod:`.cluster` -- natural clumps and how even a spread is:
  :func:`mixed_clumps`, :func:`clustered_points`, :func:`clark_evans`.
* :mod:`.keepout` -- floor to leave empty: :func:`window_keepouts`.
* :mod:`.scene` -- what happened here: :func:`declare_scene` and the
  stock targets (:data:`STOCK`) the ``S`` checks and the review use.
* :mod:`.fx` -- stock fire, smoke and embers that link locally:
  :func:`burning`, :func:`smouldering`, :func:`embers`.
* :mod:`.vignette` -- small stories of 5-30 props at a bend, dead end or
  clearing rim: :data:`~.vignette.KINDS`, :func:`~.vignette.place_vignette`,
  :func:`~.vignette.choose_kind`, :func:`~.vignette.add_focus`.
* :mod:`.boundary` / :mod:`.facade` -- open-air walls and backdrops, and
  the outside of a roofed room seen over them: :func:`boundary_wall`,
  :func:`backdrop`, :func:`facade`.
* :mod:`.interior` -- dense indoor dressing: :func:`fill_board` (a packed
  shelf), :func:`stack_clump` (a heap that climbs), :func:`hang_under`
  (lamps and washing hung from a bar).
* :mod:`.shell` -- room surfaces and holes: :func:`room_skin`,
  :func:`cut_hole`, :func:`link_rooms`.

Units are map units (1 unit = 1 inch), yaw in degrees; everything random
takes its own seed or ``random.Random``, so a map is the same every build.
"""

from .fixtures import RAIL, hang_bar, hanging_sign, sheared_bar
from .keepout import window_keepouts
from .place import (
    PropSpec,
    centred,
    fit_within,
    floor_boxes,
    floor_footprints,
    mounted,
    on_floor,
    on_room_wall,
    on_surface,
    on_wall,
    rest_on,
    seated,
    top_of,
    turned_box,
)
from .shell import cut_hole, link_rooms, room_skin, wall_midpoint
from .spread import (
    bins_in,
    corner_heaps,
    drift_points,
    litter_by_weight,
    litter_heaps,
    litter_in_drifts,
    no_repeat,
    seats_in,
)

from .cluster import Planting, Tier, clark_evans, clustered_points, is_foliage, mixed_clumps, rect_edges
from .scene import STOCK, Scene, declare_scene, scene_for, scenes_of
from .fx import LINKED_FX, burning, embers, place_fx, smouldering
from .boundary import WallStyle, backdrop, boundary_wall, open_spans, wall_faces
from .facade import ExposedFace, FacadeStyle, exposed_faces, facade

__all__ = [
    "Scene", "declare_scene", "scenes_of", "scene_for", "STOCK",
    "LINKED_FX", "place_fx", "burning", "smouldering", "embers",
    "WallStyle", "boundary_wall", "backdrop", "open_spans", "wall_faces",
    "FacadeStyle", "ExposedFace", "exposed_faces", "facade",
    "PropSpec", "rest_on", "top_of", "centred", "on_floor", "on_surface", "mounted",
    "seated", "turned_box", "on_wall", "on_room_wall", "fit_within", "floor_boxes",
    "floor_footprints",
    "RAIL", "hanging_sign", "hang_bar", "sheared_bar",
    "drift_points", "litter_in_drifts", "litter_by_weight", "litter_heaps", "bins_in",
    "seats_in", "corner_heaps", "no_repeat",
    "window_keepouts",
    "Tier", "Planting", "clustered_points", "mixed_clumps", "clark_evans", "is_foliage", "rect_edges",
    "room_skin", "wall_midpoint", "cut_hole", "link_rooms",
]
from .interior import Piece, fill_board, hang_under, stack_clump  # noqa: E402

__all__ += ["Piece", "fill_board", "stack_clump", "hang_under"]
