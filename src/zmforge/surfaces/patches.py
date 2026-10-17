"""Turning a heightfield into the shapes the emitter writes (spec 3.1, 3.2).

This layer produces geometry only: :class:`PatchGrid` control grids for the
mesh style, :class:`ColumnRun` boxes for the blocky style, and the UV helpers
a writer needs.  Nothing here knows the ``.map`` text format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..errors import BlueprintError, InvalidBounds
from ..materials import Material
from ..spatial import Point, Span
from .field import HeightField

__all__ = [
    "PatchGrid",
    "ColumnRun",
    "padded",
    "mesh_chunks",
    "column_runs",
    "band_material",
    "planar_uv",
    "lightmap_uv",
    "DEFAULT_CHUNK",
    "DEFAULT_TEXTURE_SCALE",
]

#: Control points per patch side are ``chunk + 1``; 8 (a 9x9 grid) is the
#: preference that compiled, and real files go no higher (spec 3.2).
DEFAULT_CHUNK = 8

#: World units one texture repeat spans.  A preference (spec 1.8): nothing in
#: the compile depends on it, it only changes how the terrain looks.
DEFAULT_TEXTURE_SCALE = 128.0


@dataclass(frozen=True, slots=True)
class PatchGrid:
    """A patch control grid in the orientation spec 1.8 requires for floors.

    ``points[outer][inner]``: the **outer** index increases along +X and the
    **inner** index along +Y.  A grid built the other way round (or with an
    index decreasing) renders only from below, which is the defect behind
    spec item E10.
    """

    points: tuple[tuple[Point, ...], ...]

    def __post_init__(self) -> None:
        grid = tuple(tuple(Point.of(point) for point in group) for group in self.points)
        if not grid or not grid[0]:
            raise InvalidBounds("a patch grid needs at least one control point")
        inner = len(grid[0])
        for index, group in enumerate(grid):
            if len(group) != inner:
                raise InvalidBounds(
                    "patch control grid is ragged: group 0 holds "
                    f"{inner} points, group {index} holds {len(group)}"
                )
        object.__setattr__(self, "points", grid)

    # -- shape -----------------------------------------------------------
    @property
    def width(self) -> int:
        """Control points along the outer index (+X).  ``W`` in the patch text."""
        return len(self.points)

    @property
    def height(self) -> int:
        """Control points along the inner index (+Y).  ``H`` in the patch text."""
        return len(self.points[0])

    def point(self, outer: int, inner: int) -> Point:
        return self.points[outer][inner]

    def corners(self) -> tuple[Point, Point, Point, Point]:
        """The four extreme control points, outer-low first."""
        return (
            self.points[0][0],
            self.points[0][-1],
            self.points[-1][0],
            self.points[-1][-1],
        )

    def footprint(self) -> Span:
        """The XY box the grid covers (zero extent in Z when the grid is flat)."""
        flat: list[Point] = [point for group in self.points for point in group]
        return Span.flat_ok(
            Point(
                min(p.x for p in flat), min(p.y for p in flat), min(p.z for p in flat)
            ),
            Point(
                max(p.x for p in flat), max(p.y for p in flat), max(p.z for p in flat)
            ),
        )

    # -- derivation ------------------------------------------------------
    def reversed_inner(self) -> "PatchGrid":
        """The same surface facing the other way, for a ceiling (spec 1.8).

        Exactly one index is reversed, which is what flips the visible side.
        """
        return PatchGrid(tuple(tuple(reversed(group)) for group in self.points))

    def transposed(self) -> "PatchGrid":
        return PatchGrid(
            tuple(
                tuple(self.points[outer][inner] for outer in range(self.width))
                for inner in range(self.height)
            )
        )

    # -- construction ----------------------------------------------------
    @classmethod
    def normalised(
        cls, points: Sequence[Sequence[Point | Sequence[float]]]
    ) -> "PatchGrid":
        """Reorder any caller grid into outer-+X / inner-+Y (spec 1.8).

        The grid is transposed when its outer index runs along Y, and either
        index is reversed when it decreases.  A grid that is not monotone on
        both indices - the axes mixed, or a line doubling back - is rejected,
        because the orientation rule cannot be satisfied by reordering it.
        """
        grid = cls(tuple(tuple(Point.of(point) for point in group) for group in points))
        if grid.width < 2 or grid.height < 2:
            raise InvalidBounds(
                "a patch grid needs at least 2x2 control points to have an "
                f"orientation, got {grid.width}x{grid.height}"
            )
        outer_x = _axis_direction(grid, along_outer=True, use_x=True)
        outer_y = _axis_direction(grid, along_outer=True, use_x=False)
        inner_x = _axis_direction(grid, along_outer=False, use_x=True)
        inner_y = _axis_direction(grid, along_outer=False, use_x=False)

        if outer_x != 0 and outer_y == 0 and inner_y != 0 and inner_x == 0:
            pass
        elif outer_y != 0 and outer_x == 0 and inner_x != 0 and inner_y == 0:
            grid = grid.transposed()
            outer_x, inner_y = inner_x, outer_y
        else:
            raise InvalidBounds(
                "patch control grid is not monotone on both indices: one index "
                "must run along X and the other along Y, each without doubling "
                "back, before it can be oriented outer +X / inner +Y"
            )
        if outer_x < 0:
            grid = PatchGrid(tuple(reversed(grid.points)))
        if inner_y < 0:
            grid = grid.reversed_inner()
        return grid


def _axis_direction(grid: PatchGrid, *, along_outer: bool, use_x: bool) -> int:
    """+1 rising, -1 falling, 0 constant, for one coordinate along one index.

    Every line along that index must agree, otherwise the grid is not monotone
    and :exc:`InvalidBounds` is raised.
    """
    lines: list[list[float]] = []
    if along_outer:
        for inner in range(grid.height):
            lines.append(
                [
                    grid.points[outer][inner].x if use_x else grid.points[outer][inner].y
                    for outer in range(grid.width)
                ]
            )
    else:
        for outer in range(grid.width):
            lines.append(
                [point.x if use_x else point.y for point in grid.points[outer]]
            )

    verdict: int | None = None
    for line in lines:
        direction = _line_direction(line)
        if verdict is None:
            verdict = direction
        elif verdict != direction:
            raise InvalidBounds(
                "patch control grid is not monotone: its lines disagree about "
                "which way the "
                + ("X" if use_x else "Y")
                + " coordinate runs along the "
                + ("outer" if along_outer else "inner")
                + " index"
            )
    return verdict or 0


def _line_direction(values: Sequence[float], tolerance: float = 1e-9) -> int:
    direction = 0
    for before, after in zip(values, values[1:]):
        delta = after - before
        if abs(delta) <= tolerance:
            step = 0
        else:
            step = 1 if delta > 0.0 else -1
        if step == 0:
            continue
        if direction == 0:
            direction = step
        elif direction != step:
            raise InvalidBounds(
                "patch control grid is not monotone: a line doubles back on itself"
            )
    return direction


@dataclass(frozen=True, slots=True)
class ColumnRun:
    """One emitted box of the blocky terrain style (spec 3.1).

    ``first_col`` and ``last_col`` are inclusive; an unmerged run covers one
    cell and has ``first_col == last_col``.  ``height`` is the height above the
    anchor that the box top sits at, which is the rounded integer height when
    the run was merged.
    """

    box: Span
    row: int
    first_col: int
    last_col: int
    height: float

    @property
    def cells(self) -> int:
        return self.last_col - self.first_col + 1

    @property
    def top_z(self) -> float:
        return self.box.maxs.z


def padded(field: HeightField) -> HeightField:
    """Duplicate the last row and the last column (spec 3.2, item E13).

    ``N`` heights span only ``(N-1)`` cells as control points, so a mesh built
    from the raw grid falls one cell short on the high-X and high-Y sides.  The
    duplicate gives the mesh the column style's footprint; the extra border is
    one flat cell wide.
    """
    rows = [list(row) + [row[-1]] for row in field.cells]
    rows.append(list(rows[-1]))
    return HeightField.from_rows(rows)


def mesh_chunks(
    field: HeightField,
    anchor: Point,
    cell: float,
    chunk: int = DEFAULT_CHUNK,
    cell_y: float | None = None,
) -> list[PatchGrid]:
    """Split a heightfield into patch control grids (spec 3.2).

    The field is padded first, then the padded grid is cut into chunks of at
    most ``chunk + 1`` control points per side, with **adjacent chunks sharing
    their edge control points** so no seam opens between patches.  Chunks are
    walked with X outermost, and every chunk carries the outer-+X / inner-+Y
    orientation of spec 1.8.
    """
    if cell <= 0.0:
        raise ValueError(f"cell size must be positive, got {cell}")
    down = cell if cell_y is None else cell_y
    if down <= 0.0:
        raise ValueError(f"cell size must be positive, got {down}")
    if chunk < 1:
        raise ValueError(f"chunk must be at least 1 control interval, got {chunk}")

    grid = padded(field)
    chunks: list[PatchGrid] = []
    for col_start in _chunk_starts(grid.cols, chunk):
        col_stop = min(col_start + chunk, grid.cols - 1)
        for row_start in _chunk_starts(grid.rows, chunk):
            row_stop = min(row_start + chunk, grid.rows - 1)
            groups: list[tuple[Point, ...]] = []
            for col in range(col_start, col_stop + 1):
                groups.append(
                    tuple(
                        Point(
                            anchor.x + col * cell,
                            anchor.y + row * down,
                            anchor.z + grid.at(row, col),
                        )
                        for row in range(row_start, row_stop + 1)
                    )
                )
            chunks.append(PatchGrid(tuple(groups)))
    return chunks


def _chunk_starts(count: int, chunk: int) -> list[int]:
    """Start indices of chunks over ``count`` control points, sharing edges."""
    if count <= 1:
        return [0]
    return list(range(0, count - 1, chunk))


def column_runs(
    field: HeightField,
    anchor: Point,
    cell: float,
    *,
    cell_y: float | None = None,
    merge: bool = True,
    skip_at: float = 0.0,
) -> list[ColumnRun]:
    """One box per cell, or per merged run of cells (spec 3.1).

    Cells at or below ``skip_at`` are left out.  With ``merge`` on, consecutive
    cells in a row whose heights round to the same integer become one box whose
    top is that integer; with it off, each cell keeps its exact height.

    A run whose emitted height is ``<= 0`` is **skipped, never emitted as a
    zero-height box** (spec item K7): quantising a 0.3-unit cell to 0 is what
    made the box constructor abort a whole terrain in the reference.
    """
    if cell <= 0.0:
        raise ValueError(f"cell size must be positive, got {cell}")
    down = cell if cell_y is None else cell_y
    if down <= 0.0:
        raise ValueError(f"cell size must be positive, got {down}")

    runs: list[ColumnRun] = []
    for row in range(field.rows):
        col = 0
        while col < field.cols:
            height = field.at(row, col)
            if height <= skip_at:
                col += 1
                continue
            if merge:
                emitted = float(round(height))
                last = col
                while (
                    last + 1 < field.cols
                    and field.at(row, last + 1) > skip_at
                    and round(field.at(row, last + 1)) == round(height)
                ):
                    last += 1
            else:
                emitted = height
                last = col
            if emitted <= 0.0:
                # K7: the run rounded down to nothing, so there is no brush.
                col = last + 1
                continue
            runs.append(
                ColumnRun(
                    box=Span.between(
                        Point(
                            anchor.x + col * cell, anchor.y + row * down, anchor.z
                        ),
                        Point(
                            anchor.x + (last + 1) * cell,
                            anchor.y + (row + 1) * down,
                            anchor.z + emitted,
                        ),
                    ),
                    row=row,
                    first_col=col,
                    last_col=last,
                    height=emitted,
                )
            )
            col = last + 1
    return runs


def band_material(bands: Sequence[tuple[float, Material]], top_z: float) -> Material:
    """The material of the first band whose ``top_z`` is ``>=`` the cell top.

    ``bands`` is in ascending order of ``top_z``.  A cell above every band
    keeps the topmost band's material, so the list never has to name a ceiling
    (a preference; the spec only fixes the first-band-wins rule).
    """
    if not bands:
        raise BlueprintError("no height bands were given, so no material can be chosen")
    for limit, material in bands:
        if limit >= top_z:
            return Material.of(material)
    return Material.of(bands[-1][1])


def planar_uv(point: Point, scale: float = DEFAULT_TEXTURE_SCALE) -> tuple[float, float]:
    """Project a control point's XY onto texture coordinates.

    ``U`` tracks world X and ``V`` tracks world Y with the sign flipped, both
    divided by ``scale``, which matches how real files read.  This is a
    **preference** (spec 1.8): any consistent planar projection renders, and
    the scale only sets how often the texture repeats.
    """
    if scale == 0.0:
        raise ValueError("texture scale must not be zero")
    return (point.x / scale, -point.y / scale)


def lightmap_uv(outer_index: int, inner_index: int) -> tuple[float, float]:
    """Lightmap coordinates for a control point at these grid indices.

    Only monotonic growth along each index is needed, so the indices themselves
    are used.  Also a **preference** (spec 1.8); small integers are fine.
    """
    return (float(outer_index), float(inner_index))
