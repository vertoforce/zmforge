"""Props whose geometry our own code builds: no download, no third-party mesh.

A square hay bale is a box, so this module builds one rather than looking for one (no
CC0 realistic bale model exists).
The look comes from its material: ambientCG's CC0 straw photo on the body and
a flat sisal-twine swatch on the bands (``library.STRAW_BALE``).

Every generator returns a :class:`Mesh` in the kits' own convention (+Y up,
counter-clockwise outward faces, v running up the image), so the rest of the
pipeline treats it exactly like a Kenney ``.obj``.  Units are inches, but
:func:`zmforge.props.xmodel.to_game_space` rescales to the prop's
``size_units`` anyway.

The bale: a box with rounded (bevelled) edges, faces bulging slightly
outward, pinched in under each twine band, and each band a flat strap that
stands proud of the straw, with side walls so it reads at a glance.  The
photo UVs are planar per face at one texel density (``TEXTURE_INCHES`` of
straw per image) and kept in the photo rows, clear of the swatch strip.
"""

from __future__ import annotations

import math
from typing import Callable

from .library import PHOTO_V
from .wavefront import Mesh, Triangle

__all__ = ["GENERATORS", "PAINTERS", "corn_stalk", "gamble_atm", "paint", "corn_stalk_thin", "generate", "straw_bale",
           "straw_bale_three_string"]

#: Inches of straw across the whole photo: ThatchedRoof001A's straws come out
#: about hand-length on a 40-inch bale.
TEXTURE_INCHES = 48.0


class _Builder:
    def __init__(self) -> None:
        self.mesh = Mesh(source="generated")

    def quad(self, material: str, corners, uvs, *, reverse: bool = False) -> None:
        """Two triangles from four corners, counter-clockwise seen from outside."""
        if reverse:
            corners, uvs = list(reversed(corners)), list(reversed(uvs))
        base = len(self.mesh.positions)
        self.mesh.positions.extend(corners)
        ub = len(self.mesh.uvs)
        self.mesh.uvs.extend(uvs)
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            self.mesh.triangles.append(Triangle(
                material=material,
                position=(base + a, base + b, base + c),
                normal=(-1, -1, -1),
                uv=(ub + a, ub + b, ub + c),
            ))


def _samples(half: float, radius: float, inner: int) -> list[float]:
    """Coordinates along one axis: the bevel rings at each end, ``inner`` between."""
    flat = half - radius
    ring = [-half, -half + radius * (1 - math.cos(math.pi / 8)),
            -half + radius * (1 - math.cos(math.pi / 4)),
            -half + radius * (1 - math.cos(3 * math.pi / 8))]
    mids = [-flat + 2 * flat * i / (inner + 1) for i in range(inner + 2)]
    return ring + mids + [-v for v in reversed(ring)]


def _bale(length: float, width: float, height: float, bands: int) -> Mesh:
    """A bale ``length`` (x) by ``width`` (y) by ``height`` (z), in Z-up inches."""
    hx, hy, hz = length / 2, width / 2, height / 2
    radius = min(hy, hz) * 0.28
    bulge = min(hy, hz) * 0.035
    band_x = [(-hx + length * (i + 1) / (bands + 1)) for i in range(bands)]
    band_w = 0.7
    pinch = min(hy, hz) * 0.045

    def squeeze(x: float) -> float:
        """How far the girth is pulled in at x, by the twine."""
        return sum(pinch * math.exp(-((x - b) / 2.2) ** 2) for b in band_x)

    def surface(p):
        """Round the box's edges, bulge its faces, pinch it under the bands."""
        x, y, z = p
        ix = max(-(hx - radius), min(hx - radius, x))
        iy = max(-(hy - radius), min(hy - radius, y))
        iz = max(-(hz - radius), min(hz - radius, z))
        dx, dy, dz = x - ix, y - iy, z - iz
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        x, y, z = ix + dx / d * radius, iy + dy / d * radius, iz + dz / d * radius
        # Faces bow outward a little in the middle, as packed straw does.
        fy = 1 - (x / hx) ** 2
        y += math.copysign(bulge * fy * (1 - (z / hz) ** 2), y) if abs(y) > hy - radius else 0
        z += math.copysign(bulge * fy * (1 - (y / hy) ** 2), z) if abs(z) > hz - radius else 0
        k = squeeze(x)
        y -= math.copysign(k, y) * min(1.0, abs(y) / hy)
        z -= math.copysign(k, z) * min(1.0, abs(z) / hz)
        return (x, y, z + hz)  # stand it on z = 0

    build = _Builder()
    xs = _samples(hx, radius, 16)
    ys = _samples(hy, radius, 5)
    zs = _samples(hz, radius, 4)
    tex = TEXTURE_INCHES

    def uv(a: float, b: float, span_a: float, span_b: float):
        # Planar, one density everywhere, centred and kept inside the photo
        # rows.  v here runs up (Wavefront); the image's top PHOTO_V of rows
        # hold the photo, squeezed, so in these terms it is v > 1 - PHOTO_V.
        u = 0.5 + a / tex
        v = (1 - PHOTO_V) + PHOTO_V * (0.5 + b / tex)
        return (min(max(u, 0.002), 0.998), min(max(v, 1 - PHOTO_V + 0.004), 0.998))

    # Six faces of a subdivided box; (axis, sign, the two in-face axes).
    faces = [
        (0, +1, ys, zs), (0, -1, ys, zs),
        (1, +1, xs, zs), (1, -1, xs, zs),
        (2, +1, xs, ys), (2, -1, xs, ys),
    ]
    half = (hx, hy, hz)
    for axis, sign, us, vs in faces:
        a_axis, b_axis = [i for i in range(3) if i != axis]
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                corners, uvs = [], []
                for (ii, jj) in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = sign * half[axis]
                    p[a_axis], p[b_axis] = us[ii], vs[jj]
                    corners.append(surface(p))
                    uvs.append(uv(us[ii], vs[jj], half[a_axis], half[b_axis]))
                # Counter-clockwise from outside: flip the order on the faces
                # whose in-face axes run the wrong way round the normal.
                right_handed = (a_axis, b_axis) in ((1, 2), (2, 0), (0, 1))
                if (sign > 0) != right_handed:
                    corners.reverse()
                    uvs.reverse()
                build.quad("straw", corners, uvs)

    # Twine: a strap round the girth at each band, standing proud of the straw.
    ring = []
    steps = 10
    for cy, cz, start in ((hy, hz, 0), (-hy, hz, 90), (-hy, -hz, 180), (hy, -hz, 270)):
        for s in range(steps + 1):
            ang = math.radians(start + 90 * s / steps)
            ring.append((cy - math.copysign(radius, cy) + radius * math.cos(ang),
                         cz - math.copysign(radius, cz) + radius * math.sin(ang)))
    twine_uv = [(0.5, 0.95)] * 4  # replaced by the swatch's flat UV at build
    lift, sink = 0.28, 0.35
    for bx in band_x:
        pts = [surface((bx, y, z)) for (y, z) in ring]
        n = len(pts)
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            outward = []
            for p in (p0, p1):
                cy, cz = p[1], p[2] - hz
                d = math.hypot(cy, cz) or 1.0
                outward.append((cy / d, cz / d))
            def at(p, o, dx, off):
                return (p[0] + dx, p[1] + o[0] * off, p[2] + o[1] * off)
            w = band_w / 2
            # Corners below go clockwise seen from outside (the ring runs
            # counter-clockwise round +x), so each quad is reversed on the way in.
            # outer face of the strap
            build.quad("twine", [at(p0, outward[0], -w, lift), at(p0, outward[0], w, lift),
                                 at(p1, outward[1], w, lift), at(p1, outward[1], -w, lift)],
                       twine_uv, reverse=True)
            # its two side walls, down into the straw
            build.quad("twine", [at(p0, outward[0], w, -sink), at(p1, outward[1], w, -sink),
                                 at(p1, outward[1], w, lift), at(p0, outward[0], w, lift)],
                       twine_uv, reverse=True)
            build.quad("twine", [at(p1, outward[1], -w, -sink), at(p0, outward[0], -w, -sink),
                                 at(p0, outward[0], -w, lift), at(p1, outward[1], -w, lift)],
                       twine_uv, reverse=True)
    return _fit(_to_y_up(build.mesh), (length, width, height))


def _to_y_up(mesh: Mesh) -> Mesh:
    """Z-up (x, y, z) to the kits' Y-up (x, z, -y); to_game_space undoes it."""
    mesh.positions = [(x, z, -y) for x, y, z in mesh.positions]
    return mesh


def _fit(mesh: Mesh, size: tuple[float, float, float]) -> Mesh:
    """Scale each axis so the whole bale (twine included) is exactly ``size``.

    The recipes place the bales by a recorded box (``recipes/props.py``
    ``MODEL_BOX``); hitting it exactly lets the generated bale replace the
    kit's under the same name without moving a single placement.
    """
    lo, hi = mesh.bounds()
    # Y-up: game x = x, game y = -z, game z = y.
    want = (size[0], size[2], size[1])
    scale = [want[i] / (hi[i] - lo[i]) for i in range(3)]
    mesh.positions = [tuple(p[i] * scale[i] for i in range(3)) for p in mesh.positions]  # type: ignore[misc]
    return mesh


def straw_bale() -> Mesh:
    """A two-string small square bale, the kit hay bale's box (40 x 26.5 x 23.35)."""
    return _bale(40.0, 26.506, 23.35, bands=2)


def straw_bale_three_string() -> Mesh:
    """A bigger three-string bale, the kit stack's box (40 x 28.43 x 25.05)."""
    return _bale(40.0, 28.434, 25.048, bands=3)


def corn_stalk() -> Mesh:
    """A full late-season corn stalk (``props/corn.py``), the kit stalk's box."""
    from .corn import corn_stalk as build

    return build("corn_stalk")


def corn_stalk_thin() -> Mesh:
    """A leaner stalk, one ear, the kit thin stalk's box."""
    from .corn import corn_stalk as build

    return build("corn_stalk_thin")


def _dead_tree(member: str) -> Callable[[], Mesh]:
    def build() -> Mesh:
        from .dead_tree import dead_tree

        return dead_tree(member)

    build.__doc__ = f"A bare dead tree (``props/dead_tree.py`` variant {member!r})."
    return build


def gamble_atm() -> Mesh:
    """The gamble machine's cash-machine cabinet (``props/atm.py``)."""
    from .atm import atm_mesh

    return atm_mesh()


GENERATORS: dict[str, Callable[[], Mesh]] = {
    "gamble_atm": gamble_atm,
    "dead_tree_a": _dead_tree("dead_tree_a"),
    "dead_tree_b": _dead_tree("dead_tree_b"),
    "dead_tree_c": _dead_tree("dead_tree_c"),
    "dead_tree_d": _dead_tree("dead_tree_d"),
    "dead_tree_e": _dead_tree("dead_tree_e"),
    "straw_bale": straw_bale,
    "straw_bale_three_string": straw_bale_three_string,
    "corn_stalk": corn_stalk,
    "corn_stalk_thin": corn_stalk_thin,
}


def generate(member: str) -> Mesh:
    try:
        return GENERATORS[member]()
    except KeyError:
        raise KeyError(f"no generated prop {member!r}; have {sorted(GENERATORS)}") from None


def _painter(name: str):
    def run(size: int):
        from . import atm

        return getattr(atm, name)(size)
    return run


#: Painters for :class:`library.PropMaterial` ``painter``: ``size -> (colour, normal or None)``.
def _corn_wall(size: int):
    from .corn import paint_corn_wall

    return paint_corn_wall(size)


PAINTERS: dict[str, Callable[[int], tuple]] = {
    "atm_body": _painter("paint_body"),
    "atm_glow": _painter("paint_glow"),
    "corn_wall": _corn_wall,
}


def paint(name: str, size: int) -> tuple:
    try:
        return PAINTERS[name](size)
    except KeyError:
        raise KeyError(f"no prop painter {name!r}; have {sorted(PAINTERS)}") from None
