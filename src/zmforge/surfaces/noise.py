"""A seeded, deterministic fractal heightfield source (spec section 3.7).

Value noise on an integer lattice, smoothstep-interpolated and summed over a
few octaves, normalised onto ``[0, peak]``.  Pure standard library, and the
lattice values come from an explicit integer mix (never Python's ``hash()``,
which is salted per process), so the same seed gives byte-identical heights
across runs, processes and machines.
"""

from __future__ import annotations

from .field import HeightField

__all__ = ["fractal_field"]

_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15
_MIX_A = 0xBF58476D1CE4E5B9
_MIX_B = 0x94D049BB133111EB
_COL_ODD = 0xC2B2AE3D27D4EB4F
_ROW_ODD = 0x165667B19E3779F9
_OCTAVE_ODD = 0xD6E8FEB86659FD93

#: How many lattice cells the first octave spans across the longer grid side.
#: A preference: low enough that octave 0 reads as the landform, not as noise.
BASE_LATTICE_SPAN = 4.0


def _lattice_value(seed: int, octave: int, col: int, row: int) -> float:
    """A deterministic value in ``[0, 1)`` for one lattice corner.

    A splitmix64-style finaliser over the seed, octave and lattice indices.
    Every step is masked to 64 bits so the result does not depend on Python's
    unbounded integers, and none of it depends on process state.
    """
    state = (seed & _MASK64) ^ ((octave & _MASK64) * _OCTAVE_ODD)
    state = (state + (col & _MASK64) * _COL_ODD) & _MASK64
    state = (state + (row & _MASK64) * _ROW_ODD) & _MASK64
    state = (state + _GOLDEN) & _MASK64
    state = ((state ^ (state >> 30)) * _MIX_A) & _MASK64
    state = ((state ^ (state >> 27)) * _MIX_B) & _MASK64
    state = state ^ (state >> 31)
    return (state >> 11) * (1.0 / (1 << 53))


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _value_noise(seed: int, octave: int, x: float, y: float) -> float:
    """Smoothstep-interpolated value noise at a continuous lattice position."""
    col = int(x // 1)
    row = int(y // 1)
    fx = _smoothstep(x - col)
    fy = _smoothstep(y - row)
    c00 = _lattice_value(seed, octave, col, row)
    c10 = _lattice_value(seed, octave, col + 1, row)
    c01 = _lattice_value(seed, octave, col, row + 1)
    c11 = _lattice_value(seed, octave, col + 1, row + 1)
    low = c00 + (c10 - c00) * fx
    high = c01 + (c11 - c01) * fx
    return low + (high - low) * fy


def fractal_field(
    rows: int,
    cols: int,
    *,
    seed: int,
    octaves: int = 4,
    persistence: float = 0.5,
    lacunarity: float = 2.0,
    peak: float = 1.0,
) -> HeightField:
    """A fractal heightfield of ``rows`` x ``cols`` cells, heights in ``[0, peak]``.

    ``octaves`` layers are summed; each successive layer has ``persistence``
    times the amplitude and ``lacunarity`` times the frequency of the one
    before.  The sum is rescaled onto ``[0, peak]`` by its own extremes, so
    ``peak`` is the tallest height in the returned grid.  A grid whose octaves
    all land on one value (a 1x1 grid, for instance) comes back flat at zero.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError(f"grid size must be positive, got {rows}x{cols}")
    if octaves <= 0:
        raise ValueError(f"octaves must be positive, got {octaves}")
    if persistence <= 0.0:
        raise ValueError(f"persistence must be positive, got {persistence}")
    if lacunarity <= 0.0:
        raise ValueError(f"lacunarity must be positive, got {lacunarity}")

    seed = int(seed) & _MASK64
    longest = max(rows, cols)
    step = BASE_LATTICE_SPAN / longest

    raw: list[list[float]] = []
    for row in range(rows):
        line: list[float] = []
        for col in range(cols):
            total = 0.0
            amplitude = 1.0
            frequency = 1.0
            for octave in range(octaves):
                total += amplitude * _value_noise(
                    seed, octave, col * step * frequency, row * step * frequency
                )
                amplitude *= persistence
                frequency *= lacunarity
            line.append(total)
        raw.append(line)

    lowest = min(min(line) for line in raw)
    highest = max(max(line) for line in raw)
    spread = highest - lowest
    if spread <= 1e-12:
        return HeightField.level(rows, cols, 0.0)
    scale = float(peak) / spread
    return HeightField.from_rows(
        [[(value - lowest) * scale for value in line] for line in raw]
    )
