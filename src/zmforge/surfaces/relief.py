"""Optional shaping passes over a heightfield (spec section 3.3).

Every pass is optional and a no-op at its default value, so a bare
``Relief()`` returns the field it was given.  The set and the order are a
**preference** of the reference authors, not something the game requires; they
are fixed here so a record can be reproduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..errors import BlueprintError
from ..spatial import Point
from .field import HeightField

__all__ = ["Pad", "Relief", "PostProcess", "TerrainBelowFloor"]


class TerrainBelowFloor(BlueprintError):
    """Post-processing left no cell above zero, so nothing could be built."""


@dataclass(frozen=True, slots=True)
class Pad:
    """A flattened disc of terrain, used to meet a door sill (spec 3.3 pass 5).

    ``centre_x`` / ``centre_y`` are world coordinates, ``radius`` is in world
    units, ``height`` is the heightfield value (above ``oz``) the covered cells
    take.
    """

    centre_x: float
    centre_y: float
    radius: float
    height: float

    def covers(self, x: float, y: float) -> bool:
        """True when the world point lies within ``radius`` of the centre."""
        dx = x - self.centre_x
        dy = y - self.centre_y
        return (dx * dx + dy * dy) <= (self.radius * self.radius)


@dataclass(frozen=True, slots=True)
class Relief:
    """The heightfield post-process pipeline of spec 3.3.

    ``Relief`` is this design's name for the pipeline; the public interface
    passes it as ``post=PostProcess(...)``, and :data:`PostProcess` is an alias
    of this class.

    Passes run in this documented order, on heights already in world units:

    1. **Broken floor** (``coverage``): the height at the ``1 - coverage``
       quantile becomes a threshold; every cell below it drops to
       ``floor_height``, so only the top ``coverage`` fraction stays raised.
    2. **Clamp** (``ceiling``): every cell becomes ``min(h, ceiling)``.
    3. **Smooth** (``smooth_passes``): that many passes of a five-point
       average (the cell plus its four edge neighbours), interior cells only.
    4. **Edge feather** (``feather_units``): with ``f = round(feather_units /
       cell)``, a cell at grid distance ``d < f`` from the boundary becomes
       ``floor_height + (h - floor_height) * d / f``.
    5. **Flatten pads** (``pads``): every cell whose centre lies within a pad's
       radius is set to that pad's height.

    Afterwards, a field with no cell above zero is rejected
    (:class:`TerrainBelowFloor`): nothing would be emitted and the failure
    should be seen before any file is written.
    """

    floor_height: float = 0.0
    coverage: float | None = None
    ceiling: float | None = None
    smooth_passes: int = 0
    feather_units: float = 0.0
    pads: tuple[Pad, ...] = ()

    def __post_init__(self) -> None:
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ValueError(f"coverage must be a fraction in [0, 1], got {self.coverage}")
        if self.smooth_passes < 0:
            raise ValueError(f"smooth_passes must not be negative, got {self.smooth_passes}")
        if self.feather_units < 0.0:
            raise ValueError(f"feather_units must not be negative, got {self.feather_units}")
        object.__setattr__(self, "pads", tuple(self.pads))

    # -- the pipeline ----------------------------------------------------
    def applied_to(
        self,
        field: HeightField,
        anchor: Point,
        cell: float,
        cell_y: float | None = None,
    ) -> HeightField:
        """Run all five passes in the documented order and check the result.

        ``anchor`` and ``cell`` place the grid in the world, which passes 4 and
        5 need (feathering counts cells, pads are given in world coordinates).
        """
        if cell <= 0.0:
            raise ValueError(f"cell size must be positive, got {cell}")
        down = cell if cell_y is None else cell_y
        if down <= 0.0:
            raise ValueError(f"cell size must be positive, got {down}")
        working = self._broken_floor(field)
        working = self._clamp(working)
        working = self._smooth(working)
        working = self._feather(working, min(cell, down))
        working = self._flatten_pads(working, anchor, cell, down)
        self._reject_if_all_sunk(working)
        return working

    # -- pass 1 ----------------------------------------------------------
    def _broken_floor(self, field: HeightField) -> HeightField:
        if self.coverage is None:
            return field
        threshold = _quantile(sorted(field.values()), 1.0 - self.coverage)
        floor = self.floor_height
        return field.replaced(
            lambda r, c, height: floor if height < threshold else height
        )

    # -- pass 2 ----------------------------------------------------------
    def _clamp(self, field: HeightField) -> HeightField:
        if self.ceiling is None:
            return field
        top = self.ceiling
        return field.replaced(lambda r, c, height: min(height, top))

    # -- pass 3 ----------------------------------------------------------
    def _smooth(self, field: HeightField) -> HeightField:
        working = field
        for _ in range(self.smooth_passes):
            source = working
            working = source.replaced(
                lambda r, c, height: height
                if (r == 0 or c == 0 or r == source.rows - 1 or c == source.cols - 1)
                else (
                    height
                    + source.at(r - 1, c)
                    + source.at(r + 1, c)
                    + source.at(r, c - 1)
                    + source.at(r, c + 1)
                )
                / 5.0
            )
        return working

    # -- pass 4 ----------------------------------------------------------
    def _feather(self, field: HeightField, cell: float) -> HeightField:
        span = int(round(self.feather_units / cell))
        if span <= 0:
            return field
        floor = self.floor_height
        rows, cols = field.rows, field.cols

        def blend(r: int, c: int, height: float) -> float:
            distance = min(r, c, rows - 1 - r, cols - 1 - c)
            if distance >= span:
                return height
            return floor + (height - floor) * distance / span

        return field.replaced(blend)

    # -- pass 5 ----------------------------------------------------------
    def _flatten_pads(
        self, field: HeightField, anchor: Point, cell: float, cell_y: float
    ) -> HeightField:
        if not self.pads:
            return field
        pads = self.pads

        def flatten(r: int, c: int, height: float) -> float:
            x = anchor.x + (c + 0.5) * cell
            y = anchor.y + (r + 0.5) * cell_y
            for pad in pads:
                if pad.covers(x, y):
                    return pad.height
            return height

        return field.replaced(flatten)

    # -- guard -----------------------------------------------------------
    @staticmethod
    def _reject_if_all_sunk(field: HeightField) -> None:
        if field.highest > 0.0:
            return
        raise TerrainBelowFloor(
            "every terrain cell is at or below the floor after post-processing "
            f"(highest cell is {field.highest:g}); nothing would be emitted. "
            "Normalise the heights to the local minimum, or add a floor "
            "thickness, so at least one cell rises above zero."
        )


#: The spec's interface spells this parameter ``post=PostProcess(...)``.
PostProcess = Relief


def _quantile(ordered: Sequence[float], fraction: float) -> float:
    """Linear-interpolated quantile of an already sorted sequence."""
    if not ordered:
        raise ValueError("no values to take a quantile of")
    if len(ordered) == 1:
        return ordered[0]
    position = min(max(fraction, 0.0), 1.0) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight
