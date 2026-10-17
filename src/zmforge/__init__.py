"""zmforge: generate Black Ops III zombies maps from a validated model.

Build a map by adding elements to a :class:`~zmforge.project.Project`'s
blueprint and committing once::

    from zmforge import Project, Bounds, Point

    project = Project.create("zm_example", tools_root)
    room = project.blueprint.add_room(Bounds.between((-512, -256, 0), (-128, 256, 256)))
    project.blueprint.add_zone("start", room, starting=True)
    ...
    result = project.commit()

Nothing touches disk until ``commit``, and ``commit`` refuses to write while
the model-level checks report an error -- a map that fails them is one the
game loads and then kills the player on.

The layers below are independent and usable on their own:
:mod:`~zmforge.mapsource` (the text format), :mod:`~zmforge.solids` (convex
geometry), :mod:`~zmforge.surfaces` (terrain), :mod:`~zmforge.blueprint` (the
model), :mod:`~zmforge.emit` (model to files), :mod:`~zmforge.verify` (checks)
and :mod:`~zmforge.toolchain` (running the compiler, baker and linker).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import (
    BlueprintError,
    DuplicateId,
    ForgeError,
    InvalidBounds,
    MapTextError,
    NoInteractiveDesktop,
    NotOnFloor,
    OpeningDoesNotFit,
    ToolchainError,
    UnknownMaterial,
    UnknownZone,
)
from .materials import FaceMaterials, Material
from .spatial import Angles, Axis, Bounds, Facing, Point, Side, Span
from .solids.layout import Aperture
from .blueprint.model import Blueprint
from .project import CommitResult, Project

__all__ = [
    "__version__",
    "Project",
    "CommitResult",
    "Blueprint",
    "Aperture",
    "Bounds",
    "Span",
    "Point",
    "Angles",
    "Axis",
    "Side",
    "Facing",
    "Material",
    "FaceMaterials",
    "ForgeError",
    "BlueprintError",
    "InvalidBounds",
    "OpeningDoesNotFit",
    "UnknownMaterial",
    "UnknownZone",
    "DuplicateId",
    "NotOnFloor",
    "MapTextError",
    "ToolchainError",
    "NoInteractiveDesktop",
]
