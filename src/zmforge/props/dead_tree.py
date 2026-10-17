"""A bare dead tree, built by our own code (no linkable stock or CC0 one exists).

The game ships no bare tree that links in a map build (only the leafy
``p7_foliage_tree_albizia_tall_full``), and Poly Haven's dead-wood models
are a lying log (``dead_tree_trunk``), a stump and a limbless quiver-tree
trunk (``dead_quiver_trunk``, 0.3 x 0.3 x 2 m) [checked against
``api.polyhaven.com``].  Square brush trees read as blocky toys, not
trees.

So this builds one from its real parts, sized as fractions of its height:

* a **trunk** that leans a little and wanders as it rises, round (nine
  sides), flaring into its roots at the foot and tapering to a snapped
  leader;
* **roots**: four to five short flares running out and down into the soil;
* **limbs**: five to seven, leaving the trunk in its upper two thirds at
  45-70 degrees on a golden-angle spiral, each bending up and out;
* **branches** off each limb and **twigs** off each branch, thinner and
  shorter each time, so the crown is a fine, irregular silhouette.

Every piece is a closed tapered tube along a gently wandering centre line,
so the tree has no flat faces and no square corners.  Colour is one photo
(``library.DEAD_BARK``): ambientCG's CC0 oak bark, graded to weathered grey
wood.  ``u`` runs once round each tube and ``v`` runs along it, reflected
every ``BARK_INCHES`` so it stays inside the image (the prop pipeline
clamps UVs to 0..1).

The model's origin is the trunk's foot: each half-axis of the crown is
scaled on its own to a symmetric box (as ``props/corn.py`` does), so a
recipe placing the tree at (x, y) gets the trunk at (x, y), whatever the
crown's lean.
"""

from __future__ import annotations

import math
import random

from .corn import _add, _cross, _Mesh, _unit
from .wavefront import Mesh

__all__ = ["VARIANTS", "dead_tree", "tree_mesh"]

Vec = tuple[float, float, float]

#: Inches of bark along a branch per photo height (reflected, not wrapped).
BARK_INCHES = 64.0

_MAT = "bark"


def _ring(c: Vec, t: Vec, r: float, sides: int, phase: float) -> list[Vec]:
    ref = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = _unit(_cross(t, ref))
    e2 = _cross(t, e1)
    out = []
    for k in range(sides):
        a = phase + 2 * math.pi * k / sides
        out.append(_add(_add(c, e1, r * math.cos(a)), e2, r * math.sin(a)))
    return out


def _v(length: float) -> float:
    """``length`` inches along a branch as a v in 0..1, reflected each period."""
    p = (length / BARK_INCHES) % 2.0
    return 0.02 + 0.96 * (p if p <= 1.0 else 2.0 - p)


def _tube(b: _Mesh, axis: list[Vec], radii: list[float], sides: int, phase: float) -> None:
    """A tapered, closed tube along ``axis``, pointed at its last point."""
    rings = []
    lengths = [0.0]
    for i in range(1, len(axis)):
        a, c = axis[i - 1], axis[i]
        lengths.append(lengths[-1] + math.dist(a, c))
    for i, c in enumerate(axis[:-1]):
        nxt, prv = axis[i + 1], axis[max(i - 1, 0)]
        t = _unit((nxt[0] - prv[0], nxt[1] - prv[1], nxt[2] - prv[2]))
        rings.append(_ring(c, t, radii[i], sides, phase))
    for i in range(len(rings) - 1):
        va, vb = _v(lengths[i]), _v(lengths[i + 1])
        for k in range(sides):
            k2 = k + 1
            ua, ub = k / sides, k2 / sides
            k2 %= sides
            b.quad(_MAT, [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]],
                   [(ua, va), (ub, va), (ub, vb), (ua, vb)])
    tip, vt = axis[-1], _v(lengths[-1])
    last, vl = rings[-1], _v(lengths[-2])
    for k in range(sides):
        k2 = (k + 1) % sides
        b.tri(_MAT, (last[k], last[k2], tip), ((k / sides, vl), ((k + 1) / sides, vl),
                                               ((k + 0.5) / sides, vt)))


def _path(rng: random.Random, start: Vec, direction: Vec, length: float, segments: int,
          *, rise: float, wander: float) -> list[Vec]:
    """A wandering centre line: each step turns a little at random and bends
    towards up by ``rise`` (negative droops)."""
    pts = [start]
    d = _unit(direction)
    step = length / segments
    for _ in range(segments):
        d = _unit((d[0] + rng.uniform(-wander, wander), d[1] + rng.uniform(-wander, wander),
                   d[2] + rng.uniform(-wander, wander) * 0.5 + rise))
        pts.append(_add(pts[-1], d, step))
    return pts


def _branch(b: _Mesh, rng: random.Random, start: Vec, direction: Vec, length: float,
            radius: float, depth: int, max_depth: int, gnarl: float = 0.28) -> None:
    sides = (8, 7, 5, 4)[min(depth, 3)]
    segments = max(3, int(length / 22.0))
    axis = _path(rng, start, direction, length, segments, rise=0.10 if depth < 2 else 0.04,
                 wander=gnarl)
    # A strong taper (to a fifth, faster near the tip): heavy at the fork.
    radii = [radius * (1.0 - 0.8 * (i / segments) ** 0.8) for i in range(segments + 1)]
    _tube(b, axis, radii, sides, rng.uniform(0, math.pi))
    if depth >= max_depth:
        return
    kids = rng.randint(2, 4) if depth == 0 else rng.randint(1, 3)
    for n in range(kids):
        t = rng.uniform(0.35, 0.9)
        i = min(int(t * segments), segments - 1)
        at = axis[i]
        here = _unit(tuple(axis[i + 1][j] - axis[i][j] for j in range(3)))  # type: ignore[arg-type]
        az = rng.uniform(0, 2 * math.pi)
        side = _unit(_cross(here, (math.cos(az), math.sin(az), 0.3)))
        tilt = math.radians(rng.uniform(30, 60))
        kid = _unit(_add(tuple(c * math.cos(tilt) for c in here), side, math.sin(tilt)))  # type: ignore[arg-type]
        _branch(b, rng, at, kid, length * rng.uniform(0.4, 0.62), radii[i] * 0.62,
                depth + 1, max_depth, gnarl)
        del n


def tree_mesh(seed: int, height: float, *, limbs: int, lean: float, snag: float,
              gnarl: float = 0.12) -> Mesh:
    """A dead tree ``height`` tall (Z up, trunk foot at the origin).

    Proportions (a thinner trunk reads as a pale sapling against the night
    sky): a trunk radius of 11% of the height at
    the foot, flared 1.4x into the roots and tapering hard to 30%
    at the snag; few, heavy limbs (70% of the trunk's radius where they
    leave it).  ``gnarl`` is how much the trunk wanders as it rises (the
    limbs wander twice as much)."""
    rng = random.Random(seed)
    b = _Mesh()
    base_r = height * 0.11
    # Trunk: wandering, leaning, flared at the foot, snapped at ``snag`` of height.
    trunk_h = height * snag
    segments = 14
    lean_dir = rng.uniform(0, 2 * math.pi)
    axis = [(0.0, 0.0, -6.0)]
    d = (math.cos(lean_dir) * lean, math.sin(lean_dir) * lean, 1.0)
    for i in range(segments):
        # The foot stays plumb (its collision is a straight column); it wanders above.
        w = gnarl if i >= 3 else 0.02
        d = _unit((d[0] + rng.uniform(-w, w), d[1] + rng.uniform(-w, w), 1.0))
        axis.append(_add(axis[-1], d, (trunk_h + 6.0) / segments))
    radii = []
    for i in range(segments + 1):
        t = i / segments
        flare = 1.0 + 0.4 * max(0.0, 1.0 - t / 0.12) ** 2
        radii.append(base_r * flare * (1.0 - 0.7 * t ** 0.85))
    _tube(b, axis, radii, 11, rng.uniform(0, math.pi))
    # Roots: short, thick flares out and down into the soil.
    for k in range(rng.randint(4, 6)):
        az = 2 * math.pi * k / 5 + rng.uniform(-0.4, 0.4)
        start = (math.cos(az) * base_r * 0.5, math.sin(az) * base_r * 0.5, height * 0.06)
        _branch(b, rng, start, (math.cos(az), math.sin(az), -0.5), height * 0.16,
                base_r * 0.5, 2, 2, 0.15)
    # Few, heavy limbs on a golden-angle spiral up the upper half.
    golden = math.pi * (3 - math.sqrt(5))
    az0 = rng.uniform(0, 2 * math.pi)
    for n in range(limbs):
        t = 0.45 + 0.5 * (n + rng.uniform(0.0, 0.6)) / limbs
        i = min(int(t * segments), segments - 1)
        at = axis[i]
        az = az0 + golden * n
        up = math.radians(rng.uniform(20, 48))
        direction = (math.cos(az) * math.cos(up), math.sin(az) * math.cos(up), math.sin(up))
        length = height * rng.uniform(0.42, 0.58) * (1.15 - 0.4 * t)
        _branch(b, rng, at, direction, length, radii[i] * 0.7, 1, 3, gnarl * 2.0)
    # The leader: the trunk carries on as a thinner, crooked top.
    top = axis[-1]
    _branch(b, rng, top, (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0),
            height * (1.0 - snag) * 1.1, radii[-1] * 0.95, 1, 3, gnarl * 2.0)
    # Root tips below the trunk's foot are flattened there: out of sight in
    # the soil, and it pins the model's lowest point to the foot (``SINK``).
    b.mesh.positions = [(x, y, max(z, -6.0)) for x, y, z in b.mesh.positions]
    return b.mesh


def _fit(mesh: Mesh, half_width: float, height: float) -> Mesh:
    """Trunk on the origin, footprint exactly +-half_width, top exactly ``height``;
    each half-axis scaled on its own (a few percent on a tree reads as nothing),
    then Z-up to the kits' Y-up.  The mesh's lowest point (the buried roots)
    sits at z = 0 after ``to_game_space``; the recipes sink it by ``SINK``."""
    def factors(a: float) -> list[float]:
        c, s = math.cos(a), math.sin(a)
        xs = [x * c - y * s for x, y, _ in mesh.positions]
        ys = [x * s + y * c for x, y, _ in mesh.positions]
        return [half_width / max(xs), half_width / -min(xs),
                half_width / max(ys), half_width / -min(ys)]

    # Turn the crown to the heading that needs the least squeeze.
    best = min((math.radians(d) for d in range(0, 180, 3)),
               key=lambda a: max(abs(math.log(k)) for k in factors(a)))
    c, s = math.cos(best), math.sin(best)
    mesh.positions = [(x * c - y * s, x * s + y * c, z) for x, y, z in mesh.positions]
    xs = [p[0] for p in mesh.positions]
    ys = [p[1] for p in mesh.positions]
    zs = [p[2] for p in mesh.positions]
    kz = height / (max(zs) - min(zs))
    z0 = min(zs)
    kx = (half_width / max(xs), half_width / -min(xs))
    ky = (half_width / max(ys), half_width / -min(ys))
    mesh.positions = [(x * kx[0 if x > 0 else 1], y * ky[0 if y > 0 else 1], (z - z0) * kz)
                      for x, y, z in mesh.positions]
    mesh.positions = [(x, z, -y) for x, y, z in mesh.positions]
    return mesh


#: The shipped variants: ``(seed, limbs, lean, snag, gnarl, half-width, height)``.
#: _a-_c are the standard trees, _d and _e the big gnarled ones (more
#: wander, 400-440 tall).  Seeds picked for a balanced crown (widest half
#: over narrowest 1.05-1.12, measured), each box close to the
#: crown's own size, so the per-half fit squeezes by a few percent at most.
VARIANTS: dict[str, tuple[int, int, float, float, float, float, float]] = {
    "dead_tree_a": (110, 5, 0.08, 0.60, 0.12, 113.0, 300.0),
    "dead_tree_b": (134, 4, 0.16, 0.55, 0.14, 95.0, 270.0),
    "dead_tree_c": (138, 4, 0.05, 0.68, 0.12, 109.0, 330.0),
    "dead_tree_d": (110, 4, 0.12, 0.55, 0.24, 130.0, 400.0),
    "dead_tree_e": (132, 5, 0.20, 0.50, 0.26, 142.0, 440.0),
}

#: How far below the ground each variant's roots reach (their lowest point is
#: the model's z = 0): the trunk starts 6 units down, roots dip further.
SINK = 6.0


def dead_tree(member: str) -> Mesh:
    seed, limbs, lean, snag, gnarl, half, height = VARIANTS[member]
    return _fit(tree_mesh(seed, height, limbs=limbs, lean=lean, snag=snag, gnarl=gnarl),
                half, height)
