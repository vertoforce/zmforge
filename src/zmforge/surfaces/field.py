"""The rectangular height grid every terrain style is built from.

Spec section 3 preamble: a heightfield is ``H[row][col]``, heights in world
units above the anchor's ``oz``.  **Rows advance along +Y, columns along +X**,
and cell ``(col, row)`` covers world x in ``[ox + col*c, ox + (col+1)*c]`` and
y in ``[oy + row*c, oy + (row+1)*c]``.

The grid is immutable: every operation returns a new :class:`HeightField`, so
a terrain record can hold the processed grid without anyone editing it from
under the lookup.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterator, Sequence

__all__ = ["HeightField"]


@dataclass(frozen=True, slots=True)
class HeightField:
    """An immutable rectangular grid of heights in world units.

    Construct through :meth:`from_rows` or :meth:`level`; the raw constructor
    accepts any nested sequence and coerces it to tuples of floats.
    """

    cells: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        rows = tuple(tuple(float(value) for value in row) for row in self.cells)
        if not rows:
            raise ValueError("a heightfield needs at least one row")
        width = len(rows[0])
        if width == 0:
            raise ValueError("a heightfield needs at least one column")
        for index, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(
                    "heightfield rows are ragged: row 0 has "
                    f"{width} columns, row {index} has {len(row)}"
                )
            for col, value in enumerate(row):
                if not math.isfinite(value):
                    raise ValueError(
                        f"height at row {index}, column {col} is not finite: {value!r}"
                    )
        object.__setattr__(self, "cells", rows)

    # -- construction ----------------------------------------------------
    @classmethod
    def from_rows(cls, rows: Sequence[Sequence[float]]) -> "HeightField":
        """Build from nested sequences, outer index = row (+Y), inner = column (+X)."""
        return cls(tuple(tuple(row) for row in rows))

    @classmethod
    def level(cls, rows: int, cols: int, value: float = 0.0) -> "HeightField":
        """A flat grid of ``rows`` x ``cols`` cells all at ``value``."""
        if rows <= 0 or cols <= 0:
            raise ValueError(f"grid size must be positive, got {rows}x{cols}")
        line = (float(value),) * cols
        return cls(tuple(line for _ in range(rows)))

    # -- shape -----------------------------------------------------------
    @property
    def rows(self) -> int:
        """Number of grid rows; rows advance along +Y."""
        return len(self.cells)

    @property
    def cols(self) -> int:
        """Number of grid columns; columns advance along +X."""
        return len(self.cells[0])

    @property
    def shape(self) -> tuple[int, int]:
        return (self.rows, self.cols)

    # -- access ----------------------------------------------------------
    def at(self, row: int, col: int) -> float:
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(
                f"cell ({row}, {col}) is outside a {self.rows}x{self.cols} heightfield"
            )
        return self.cells[row][col]

    def clamped_at(self, row: int, col: int) -> float:
        """Like :meth:`at` but clamping the indices onto the grid.

        This is what reproduces the duplicated border of spec 3.2 during a
        lookup, so the record can store the grid *before* padding.
        """
        row = min(max(row, 0), self.rows - 1)
        col = min(max(col, 0), self.cols - 1)
        return self.cells[row][col]

    def row(self, index: int) -> tuple[float, ...]:
        if not 0 <= index < self.rows:
            raise IndexError(f"row {index} is outside a {self.rows}-row heightfield")
        return self.cells[index]

    def column(self, index: int) -> tuple[float, ...]:
        if not 0 <= index < self.cols:
            raise IndexError(f"column {index} is outside a {self.cols}-column heightfield")
        return tuple(row[index] for row in self.cells)

    def __iter__(self) -> Iterator[tuple[float, ...]]:
        return iter(self.cells)

    def values(self) -> Iterator[float]:
        for row in self.cells:
            yield from row

    def as_lists(self) -> list[list[float]]:
        """A plain nested list, for JSON and for callers that want to mutate."""
        return [list(row) for row in self.cells]

    # -- measurement -----------------------------------------------------
    @property
    def lowest(self) -> float:
        return min(self.values())

    @property
    def highest(self) -> float:
        return max(self.values())

    @property
    def relief(self) -> float:
        """Highest minus lowest, the whole grid's vertical range."""
        return self.highest - self.lowest

    # -- derivation ------------------------------------------------------
    def replaced(self, fn: Callable[[int, int, float], float]) -> "HeightField":
        """A new field with ``fn(row, col, height)`` applied to every cell."""
        return HeightField(
            tuple(
                tuple(float(fn(r, c, value)) for c, value in enumerate(row))
                for r, row in enumerate(self.cells)
            )
        )

    def with_cell(self, row: int, col: int, value: float) -> "HeightField":
        """A new field differing from this one in one cell."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(
                f"cell ({row}, {col}) is outside a {self.rows}x{self.cols} heightfield"
            )
        return self.replaced(
            lambda r, c, height: float(value) if (r == row and c == col) else height
        )

    def lifted(self, by: float) -> "HeightField":
        """Every cell raised by ``by`` (spec 3.2's z-fight lift)."""
        return self.replaced(lambda r, c, height: height + by)
