"""Convex-solid maths: half-spaces, winding, primitives and the brush checker.

The one rule everything here exists to protect is the engine's winding
convention (spec 1.4): for face points ``A, B, C`` the cross product
``(B - A) x (C - A)`` points **into** the solid, which is the reverse of the
Quake convention every other map format uses.  No point order is ever written
by hand; :func:`~.halfspace.orient_inward` decides, and
:func:`~.inspect.inspect_solid` is its test.
"""

from __future__ import annotations

from .forms import (
    STAIR_GATE_HEIGHT,
    Solid,
    SolidFace,
    block,
    flight,
    stair_clip,
    stair_gate,
    wedge,
)
from .halfspace import InwardPlane, orient_inward, plane_through
from .inspect import (
    SolidFinding,
    SolidInspection,
    inspect_planes,
    inspect_solid,
    overlap_scan,
)
from .layout import (
    Aperture,
    RoomShell,
    ShellPiece,
    SkyCage,
    aperture_box,
    room_shell,
    sky_cage,
    wall_remainder,
    yard_shell,
)

__all__ = [
    "InwardPlane",
    "orient_inward",
    "plane_through",
    "Solid",
    "SolidFace",
    "block",
    "wedge",
    "flight",
    "stair_clip",
    "stair_gate",
    "STAIR_GATE_HEIGHT",
    "Aperture",
    "ShellPiece",
    "RoomShell",
    "SkyCage",
    "room_shell",
    "yard_shell",
    "aperture_box",
    "wall_remainder",
    "sky_cage",
    "SolidFinding",
    "SolidInspection",
    "inspect_planes",
    "inspect_solid",
    "overlap_scan",
]
