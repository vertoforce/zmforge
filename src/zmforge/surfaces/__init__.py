"""Patch grids, heightfields and the ground-height lookup.

Terrain comes in two flavours and the difference matters at lookup time: a
column's top is flat over its whole cell, a mesh's is bilinear between control
points, and picking the wrong flavour was measured to skew the answer by as
much as 50 units against the geometry actually written (spec item K5).  :class:`~.ground.TerrainRecord` stores which flavour
applies so a later placement cannot get it wrong.
"""

from __future__ import annotations

from .field import HeightField
from .ground import (
    SurfaceSample,
    TerrainRecord,
    machine_height,
    prop_sink,
    read_json,
    spawner_height,
)
from .noise import fractal_field
from .patches import (
    ColumnRun,
    PatchGrid,
    band_material,
    column_runs,
    lightmap_uv,
    mesh_chunks,
    padded,
    planar_uv,
)
from .relief import Pad, Relief

__all__ = [
    "HeightField",
    "fractal_field",
    "Relief",
    "Pad",
    "PatchGrid",
    "ColumnRun",
    "padded",
    "mesh_chunks",
    "column_runs",
    "band_material",
    "planar_uv",
    "lightmap_uv",
    "TerrainRecord",
    "SurfaceSample",
    "read_json",
    "spawner_height",
    "machine_height",
    "prop_sink",
]
