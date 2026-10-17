"""The terrain sidecar record and the ground-height lookup (spec 3.4 - 3.6).

A :class:`TerrainRecord` is what later placements read so they can sit an
entity on the surface without regenerating the terrain.  It holds the
*processed* heightfield - lift included, and **before** the one-row/one-column
duplication of spec 3.2, because the lookup's index clamping reproduces that
border by itself.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Literal, Mapping

from ..spatial import Point, Span
from .field import HeightField

__all__ = [
    "SurfaceSample",
    "TerrainRecord",
    "TerrainStyle",
    "read_json",
    "spawner_height",
    "machine_height",
    "prop_sink",
    "SPAWNER_CLEARANCE",
    "PROP_SINK_PER_UNIT_SPREAD",
    "PROP_SINK_CAP",
]

TerrainStyle = Literal["mesh", "columns"]

#: Spawner structs sit this far above the surface (spec 3.6).  A preference: 4
#: played, and it also absorbs the bilinear-versus-triangle error of spec 3.5.
SPAWNER_CLEARANCE = 4.0

#: How far a scattered prop sinks per unit of local spread, and the most it
#: ever sinks.  Both are preferences (spec 3.6 fixes only "linear in spread
#: with a cap"); they are exposed so a recipe can retune them.
PROP_SINK_PER_UNIT_SPREAD = 0.25
PROP_SINK_CAP = 8.0


@dataclass(frozen=True, slots=True)
class SurfaceSample:
    """The answer to "how high is the ground at (x, y)?".

    ``spread`` is ``max - min`` over the four surrounding control heights, a
    steepness measure scatter placement uses.  When ``found`` is false, ``z``
    is the anchor's ``oz`` (the room floor) and ``message`` says why.
    """

    found: bool
    z: float
    spread: float
    message: str = ""


@dataclass(frozen=True, slots=True)
class TerrainRecord:
    """The sidecar of spec 3.4: anchor, cell size, processed grid, style, knobs."""

    anchor: Point
    cell: float
    heights: HeightField
    style: TerrainStyle = "mesh"
    settings: Mapping[str, Any] = dataclass_field(default_factory=dict)
    #: Cell depth along +Y, when it differs from ``cell``.  ``None`` means
    #: square cells and is the usual case.  A terrain fitted to a room whose
    #: interior is not square needs one spacing per axis, because the grid has
    #: to reach every wall with the row and column count it was given; see
    #: :meth:`zmforge.blueprint.model.Blueprint.add_terrain`.
    cell_y: float | None = None

    def __post_init__(self) -> None:
        if self.cell <= 0.0:
            raise ValueError(f"cell size must be positive, got {self.cell}")
        if self.cell_y is not None and self.cell_y <= 0.0:
            raise ValueError(f"cell size must be positive, got {self.cell_y}")
        if self.style not in ("mesh", "columns"):
            raise ValueError(
                f"terrain style must be 'mesh' or 'columns', got {self.style!r}"
            )
        object.__setattr__(self, "anchor", Point.of(self.anchor))
        object.__setattr__(self, "settings", dict(self.settings))

    # -- shape -----------------------------------------------------------
    @property
    def x_cell(self) -> float:
        """Cell width along +X."""
        return self.cell

    @property
    def y_cell(self) -> float:
        """Cell depth along +Y; the same as :attr:`x_cell` for square cells."""
        return self.cell if self.cell_y is None else self.cell_y

    @property
    def square_cells(self) -> bool:
        """True when one spacing describes both axes."""
        return self.cell_y is None or self.cell_y == self.cell

    @property
    def rows(self) -> int:
        return self.heights.rows

    @property
    def cols(self) -> int:
        return self.heights.cols

    @property
    def footprint(self) -> Span:
        """The XY rectangle the terrain covers, flat at the anchor's ``oz``."""
        return Span.flat_ok(
            self.anchor,
            Point(
                self.anchor.x + self.cols * self.x_cell,
                self.anchor.y + self.rows * self.y_cell,
                self.anchor.z,
            ),
        )

    # -- lookup ----------------------------------------------------------
    def sample(self, x: float, y: float) -> SurfaceSample:
        """Ground height at a world point (spec 3.5).

        Cell indices come from ``floor``, never truncation toward zero: a point
        up to one cell outside the low edge truncates to cell 0 and would be
        wrongly reported as inside (spec item K6).

        Column terrain reads the **flat cell top**; only mesh terrain
        interpolates, because a column's top is constant over its whole cell,
        and measurement showed interpolated samples straying as far as 50 units
        from the geometry actually written (spec item K5).  On the mesh path the corner indices are clamped onto
        the grid, which reproduces the duplicated border of spec 3.2.
        """
        u = (x - self.anchor.x) / self.x_cell
        v = (y - self.anchor.y) / self.y_cell
        col = math.floor(u)
        row = math.floor(v)
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            box = self.footprint
            return SurfaceSample(
                found=False,
                z=self.anchor.z,
                spread=0.0,
                message=(
                    f"({x:g}, {y:g}) is outside the terrain footprint "
                    f"x {box.mins.x:g}..{box.maxs.x:g}, "
                    f"y {box.mins.y:g}..{box.maxs.y:g}; "
                    "falling back to the floor height "
                    f"z = {self.anchor.z:g}"
                ),
            )

        corners = (
            self.heights.clamped_at(row, col),
            self.heights.clamped_at(row, col + 1),
            self.heights.clamped_at(row + 1, col),
            self.heights.clamped_at(row + 1, col + 1),
        )
        spread = max(corners) - min(corners)

        if self.style == "columns":
            return SurfaceSample(
                found=True, z=self.anchor.z + self.heights.at(row, col), spread=spread
            )

        fx = min(max(u - col, 0.0), 1.0)
        fy = min(max(v - row, 0.0), 1.0)
        h00, h10, h01, h11 = corners
        low = h00 * (1.0 - fx) + h10 * fx
        high = h01 * (1.0 - fx) + h11 * fx
        return SurfaceSample(
            found=True, z=self.anchor.z + low * (1.0 - fy) + high * fy, spread=spread
        )

    # -- persistence -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """The JSON shape of spec 3.4.

        Every number is written as a float.  ``Point`` does not coerce, so a
        recipe that anchors a patch at ``Point(1624, -552, 16)`` holds three
        ints and the same map rebuilt from its own document holds three floats,
        and ``json.dumps`` spells those ``1624`` and ``1624.0``: the same
        anchor, six different bytes, in a file whose whole job is to be
        compared.
        """
        written = {
            "anchor": [float(self.anchor.x), float(self.anchor.y), float(self.anchor.z)],
            "cell": float(self.cell),
            "heights": [[float(height) for height in row]
                        for row in self.heights.as_lists()],
            "style": self.style,
            "settings": {key: float(value) if isinstance(value, (int, float))
                         and not isinstance(value, bool) else value
                         for key, value in self.settings.items()},
        }
        # Only a terrain with one spacing per axis carries the second number,
        # so the document of a square grid -- every one written so far -- is
        # the same file it always was.
        if not self.square_cells:
            written["cell_y"] = float(self.y_cell)
        return written

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TerrainRecord":
        missing = [key for key in ("anchor", "cell", "heights") if key not in data]
        if missing:
            raise ValueError(
                "terrain record is missing " + ", ".join(sorted(missing))
            )
        return cls(
            anchor=Point.of(data["anchor"]),
            cell=float(data["cell"]),
            cell_y=None if data.get("cell_y") is None else float(data["cell_y"]),
            heights=HeightField.from_rows(data["heights"]),
            style=data.get("style", "mesh"),
            settings=dict(data.get("settings", {})),
        )

    def write_json(self, path: "str | Path") -> Path:
        """Write the record beside the map source; returns the path written."""
        target = Path(path)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target


def read_json(path: "str | Path") -> TerrainRecord:
    """Read a record written by :meth:`TerrainRecord.write_json`."""
    return TerrainRecord.from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


# -- placement helpers (spec 3.6) ----------------------------------------
def spawner_height(sample: SurfaceSample, clearance: float = SPAWNER_CLEARANCE) -> float:
    """Z for a spawner struct: the surface plus a small clearance."""
    return sample.z + clearance


def machine_height(sample: SurfaceSample) -> float:
    """Z for a perk machine or pack-a-punch: exactly the surface.

    Those prefabs are authored with their origin at the floor, so any offset
    leaves them hovering.
    """
    return sample.z


def prop_sink(
    sample: SurfaceSample,
    per_unit_spread: float = PROP_SINK_PER_UNIT_SPREAD,
    cap: float = PROP_SINK_CAP,
) -> float:
    """Z for a scattered prop: the surface, sunk by an amount that grows with slope.

    Returns the placement height, not the depth.  The depth is linear in the
    sample's local spread and capped, so a model spanning a slope does not
    float on its downhill side; both constants are preferences and are exposed
    as module-level defaults.
    """
    depth = min(max(sample.spread, 0.0) * per_unit_spread, cap)
    return sample.z - depth
