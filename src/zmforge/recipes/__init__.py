"""Whole-map compositions built from the core operations.

A recipe is an ordinary caller of the blueprint: it holds no geometry
knowledge of its own and bakes in no coordinates that a caller cannot change.
That is the difference from the flat, layout-specific tools this package
replaces, where the same numbers appeared in several places.
"""

from __future__ import annotations

from .cemetery import CemeteryPlan, cemetery_map, cemetery_dusk_map
from .corn_maze import CornMazePlan, corn_maze_map
from .dmv import DmvPlan, dmv_of_the_damned
from .layouts import FIXTURE, ThreeRoomPlan, one_room_map, three_room_map
from .pranks import PrankPlan, add_prank_logic, prank_map

__all__ = [
    "ThreeRoomPlan",
    "FIXTURE",
    "three_room_map",
    "one_room_map",
    "PrankPlan",
    "prank_map",
    "add_prank_logic",
    "DmvPlan",
    "dmv_of_the_damned",
    "CemeteryPlan",
    "cemetery_map",
    "cemetery_dusk_map",
    "CornMazePlan",
    "corn_maze_map",
]
