"""A late-season field-corn stalk, built by our own code (no CC0 one exists).

Kenney's crop stalks are four flat blocks and two yellow cubes; at a maze's
scale (placed 2.1-2.9x, 200-280 units tall) they read as toys.  This builds
the plant from its real parts, sized as a fraction of its height ``H``:

* a thin **stem**, five-sided and tapering (base radius 0.8% of H);
* **leaves**, alternating up the stem on opposite sides (field corn is
  distichous) with jitter, each a long blade that leaves the stem rising and
  arches over into a droop, folded along its midrib (a shallow V, so it
  catches light) and twisting a little towards the tip.  Every blade is
  **double-sided geometry**, two triangles per face, because the prop
  materials are ``lit_detail`` and cull back faces: from a corridor the
  player looks up at the undersides.  The silhouette is the geometry itself
  (a pointed, tapered strip), so no alpha test is needed;
* one or two **husked ears** on short shanks, drooping as ripe ears do, with
  a husk flag at the tip;
* a **tassel**: a spike and three or four drooping branches.

Colour comes from one image (``library.CORN_LEAF``): a crop of ambientCG's
CC0 Leaf001 photo, graded along u from late-season olive (u = 0) to straw
(u = 1).  A blade maps its length along u, so its base is greener than its
tip; lower leaves take a range further right (drier), the ears and tassel
sit at the straw end.

Two variants ship, one per existing model name (``VARIANTS``).  More names
could take the other seeds, but a new model name does not link until
the prop install step has registered it in the tools install.
"""

from __future__ import annotations

import math
import random

from .wavefront import Mesh, Triangle

__all__ = ["VARIANTS", "WALL_TILE_UNITS", "corn_stalk", "paint_corn_wall", "stalk_mesh"]

Vec = tuple[float, float, float]


def _add(a: Vec, b: Vec, k: float = 1.0) -> Vec:
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec) -> Vec:
    d = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / d, a[1] / d, a[2] / d)


class _Mesh:
    def __init__(self) -> None:
        self.mesh = Mesh(source="generated")

    def tri(self, material: str, pts, uvs, *, both: bool = False) -> None:
        """One triangle, counter-clockwise seen from its front; ``both`` adds the back."""
        for order in ((0, 1, 2), (0, 2, 1)) if both else ((0, 1, 2),):
            base = len(self.mesh.positions)
            self.mesh.positions.extend(pts[i] for i in order)
            ub = len(self.mesh.uvs)
            self.mesh.uvs.extend((min(max(uvs[i][0], 0.002), 0.998),
                                  min(max(uvs[i][1], 0.002), 0.998)) for i in order)
            self.mesh.triangles.append(Triangle(material=material,
                                                position=(base, base + 1, base + 2),
                                                normal=(-1, -1, -1),
                                                uv=(ub, ub + 1, ub + 2)))

    def quad(self, material: str, pts, uvs, *, both: bool = False) -> None:
        self.tri(material, (pts[0], pts[1], pts[2]), (uvs[0], uvs[1], uvs[2]), both=both)
        self.tri(material, (pts[0], pts[2], pts[3]), (uvs[0], uvs[2], uvs[3]), both=both)


def _tube(b: _Mesh, material: str, axis: list[Vec], radii: list[float], sides: int,
          u_range: tuple[float, float], *, tip: Vec | None = None, cap: bool = False) -> None:
    """A tapered tube along ``axis`` (points), closed to ``tip`` if given."""
    rings = []
    for i, (c, r) in enumerate(zip(axis, radii)):
        nxt = axis[min(i + 1, len(axis) - 1)]
        prv = axis[max(i - 1, 0)]
        t = _unit((nxt[0] - prv[0], nxt[1] - prv[1], nxt[2] - prv[2]))
        ref = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
        e1 = _unit(_cross(t, ref))
        e2 = _cross(t, e1)
        rings.append([_add(_add(c, e1, r * math.cos(2 * math.pi * k / sides)),
                           e2, r * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    u0, u1 = u_range
    n = len(rings)
    for i in range(n - 1):
        ua, ub = u0 + (u1 - u0) * i / max(n - 1, 1), u0 + (u1 - u0) * (i + 1) / max(n - 1, 1)
        for k in range(sides):
            k2 = (k + 1) % sides
            va, vb = 0.15 + 0.7 * k / sides, 0.15 + 0.7 * (k + 1) / sides
            b.quad(material, [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]],
                   [(ua, va), (ua, vb), (ub, vb), (ub, va)])
    if tip is not None:
        for k in range(sides):
            k2 = (k + 1) % sides
            b.tri(material, (rings[-1][k], rings[-1][k2], tip),
                  ((u1, 0.4), (u1, 0.6), (min(u1 + 0.05, 0.99), 0.5)))
    if cap:
        c = axis[0]
        for k in range(sides):
            k2 = (k + 1) % sides
            b.tri(material, (rings[0][k2], rings[0][k], c),
                  ((u0, 0.4), (u0, 0.6), (u0, 0.5)))


def _blade(b: _Mesh, material: str, root: Vec, azimuth: float, length: float, width: float,
           rise: float, droop: float, twist: float, fold: float, u0: float, u_span: float,
           sections: tuple[float, ...]) -> None:
    """One leaf: rises at ``rise`` degrees, arches to ``-droop`` at the tip."""
    d = (math.cos(azimuth), math.sin(azimuth), 0.0)
    side0 = (-d[1], d[0], 0.0)
    ts = list(sections) + [1.0]
    # Centreline by integrating the elevation angle along the length.
    pts, tangents = [root], []
    steps = 24
    p = root
    for s in range(steps):
        t = (s + 0.5) / steps
        e = math.radians(rise + (-droop - rise) * t ** 1.4)
        tan = (d[0] * math.cos(e), d[1] * math.cos(e), math.sin(e))
        p = _add(p, tan, length / steps)
        pts.append(p)
        tangents.append(tan)

    def at(t: float):
        f = t * steps
        i = min(int(f), steps - 1)
        a = f - i
        c = _add(pts[i], (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1],
                          pts[i + 1][2] - pts[i][2]), a)
        return c, tangents[i]

    rows = []
    for t in ts:
        c, tan = at(t)
        # A blade is narrow at the collar, widest a third out, pointed at the tip.
        w = width * min(0.5 + 1.6 * t, ((1 - t) / 0.68) ** 0.8) / 2
        up = _unit(_cross(side0, tan))
        ang = math.radians(twist) * t
        side = _add(_add((0, 0, 0), side0, math.cos(ang)), up, math.sin(ang))
        up2 = _unit(_cross(side, tan))
        lift = fold * w
        rows.append((_add(_add(c, side, -w), up2, lift), c, _add(_add(c, side, w), up2, lift)))
    tip = rows[-1][1]
    for i in range(len(rows) - 1):
        ua = u0 + u_span * ts[i]
        ubb = u0 + u_span * ts[i + 1]
        l0, m0, r0 = rows[i]
        l1, m1, r1 = rows[i + 1]
        if i == len(rows) - 2:  # the pointed tip: two triangles, no sliver
            b.tri(material, (l0, m0, tip), ((ua, 0.2), (ua, 0.5), (ubb, 0.5)), both=True)
            b.tri(material, (m0, r0, tip), ((ua, 0.5), (ua, 0.8), (ubb, 0.5)), both=True)
            continue
        b.quad(material, [l0, m0, m1, l1], [(ua, 0.2), (ua, 0.5), (ubb, 0.5), (ubb, 0.2)], both=True)
        b.quad(material, [m0, r0, r1, m1], [(ua, 0.5), (ua, 0.8), (ubb, 0.8), (ubb, 0.5)], both=True)


def stalk_mesh(seed: int, height: float, leaves: int, ears: int, reach: float) -> Mesh:
    """A stalk ``height`` tall (Z-up inches); ``reach`` scales the leaf length."""
    rng = random.Random(seed)
    H = height
    b = _Mesh()
    # Stem: five sides, tapering; it runs up into the tassel's spike.
    top = 0.86 * H
    lean = (rng.uniform(-0.01, 0.01) * H, rng.uniform(-0.01, 0.01) * H)
    stem_axis = [(lean[0] * f * f, lean[1] * f * f, f * top) for f in (0.0, 0.3, 0.62, 1.0)]
    _tube(b, "stem", stem_axis, [0.0085 * H, 0.0075 * H, 0.006 * H, 0.004 * H], 5, (0.35, 0.65))

    def stem_at(z: float) -> Vec:
        f = z / top
        return (lean[0] * f * f, lean[1] * f * f, z)

    # Leaves, bottom to top.
    az = rng.uniform(0, 2 * math.pi)
    for i in range(leaves):
        f = i / max(leaves - 1, 1)
        z = H * (0.05 + 0.7 * f + rng.uniform(-0.015, 0.015))
        az += math.pi + rng.uniform(-0.55, 0.55)
        # The ear leaf (a third of the way up) is the longest.
        length = reach * H * (0.42 - 0.5 * (f - 0.38) ** 2) * rng.uniform(0.9, 1.08)
        rise = 40 + 30 * f + rng.uniform(-8, 8)
        droop = 88 - 38 * f + rng.uniform(-10, 10)
        dry = 1 - f  # lower leaves are drier: their colour range sits right
        u0 = min(0.45, 0.05 + 0.4 * dry + rng.uniform(-0.05, 0.08))
        _blade(b, "leaf", stem_at(z), az, length, 0.06 * H * rng.uniform(0.85, 1.1),
               rise, droop, rng.uniform(-35, 35), 0.22, u0, rng.uniform(0.45, 0.55),
               (0.0, 0.33, 0.66))

    # Ears: a shank out of a leaf axil, the husked ear drooping from it.
    for k in range(ears):
        z = H * (0.4 + 0.1 * k + rng.uniform(-0.02, 0.02))
        a = rng.uniform(0, 2 * math.pi)
        d = (math.cos(a), math.sin(a))
        base = stem_at(z)
        shank = _add(base, (d[0], d[1], 0.6), 0.03 * H)
        hang = math.radians(rng.uniform(-35, 15))  # most ripe ears droop
        axis_dir = _unit((d[0] * math.cos(hang), d[1] * math.cos(hang), math.sin(hang)))
        L = 0.1 * H * rng.uniform(0.9, 1.1)
        ear_axis = [shank, _add(shank, axis_dir, 0.3 * L), _add(shank, axis_dir, 0.8 * L)]
        tip = _add(shank, axis_dir, L)
        _tube(b, "ear", [base, shank], [0.004 * H, 0.004 * H], 4, (0.8, 0.85))
        _tube(b, "ear", ear_axis, [0.009 * H, 0.013 * H, 0.009 * H], 5, (0.84, 0.95),
              tip=tip, cap=True)
        # The husk flag: a loose husk leaf curling off the tip.
        flag_d = _unit(_add(axis_dir, (0, 0, 1), 0.6))
        side = _unit(_cross(axis_dir, (0, 0, 1)))
        fl = _add(tip, flag_d, 0.035 * H)
        b.tri("ear", (_add(tip, side, -0.008 * H), _add(tip, side, 0.008 * H), fl),
              ((0.9, 0.3), (0.9, 0.7), (0.98, 0.5)), both=True)

    # Tassel: a spike and drooping branches, all thin double-sided strips.
    crown = stem_at(top)
    spike = _add(crown, (0, 0, 1), H - top)
    w = 0.004 * H
    b.quad("tassel", [_add(crown, (1, 0, 0), -w), _add(crown, (1, 0, 0), w),
                      _add(spike, (1, 0, 0), w * 0.3), _add(spike, (1, 0, 0), -w * 0.3)],
           [(0.8, 0.4), (0.8, 0.6), (0.97, 0.6), (0.97, 0.4)], both=True)
    branches = 3 + rng.randint(0, 1)
    a0 = rng.uniform(0, 2 * math.pi)
    for j in range(branches):
        a = a0 + 2 * math.pi * j / branches + rng.uniform(-0.3, 0.3)
        d = (math.cos(a), math.sin(a), 0.0)
        start = _add(crown, (0, 0, 1), (H - top) * rng.uniform(0.15, 0.4))
        mid = _add(_add(start, d, 0.05 * H), (0, 0, 1), 0.035 * H)
        end = _add(_add(mid, d, 0.045 * H), (0, 0, 1), -0.05 * H)
        side = (-d[1], d[0], 0.0)
        pts = [start, mid, end]
        widths = [w, w * 0.8, 0.0]
        for i in range(2):
            p0, p1 = pts[i], pts[i + 1]
            if widths[i + 1] == 0.0:
                b.tri("tassel", (_add(p0, side, -widths[i]), _add(p0, side, widths[i]), p1),
                      ((0.85, 0.4), (0.85, 0.6), (0.97, 0.5)), both=True)
            else:
                b.quad("tassel", [_add(p0, side, -widths[i]), _add(p0, side, widths[i]),
                                  _add(p1, side, widths[i + 1]), _add(p1, side, -widths[i + 1])],
                       [(0.8, 0.4), (0.8, 0.6), (0.9, 0.6), (0.9, 0.4)], both=True)
    return b.mesh


def _fit_footprint(mesh: Mesh, half_width: float, height: float) -> Mesh:
    """Stem on the origin, footprint exactly +-half_width, top exactly ``height``.

    Each half-axis is scaled on its own, so the stem stays at x = y = 0 and
    the box is symmetric: the recipes place stalks by the recorded
    ``MODEL_BOX`` (``recipes/props.py``), and ``to_game_space`` centres the
    box, so a lopsided plant would shift off its planted point.
    """
    # Turn the plant (its leaves fan out in one plane) to the heading that
    # needs the least squeeze to fit the square box.
    def factors(a: float) -> list[float]:
        c, s = math.cos(a), math.sin(a)
        xs = [x * c - y * s for x, y, _ in mesh.positions]
        ys = [x * s + y * c for x, y, _ in mesh.positions]
        return [half_width / max(xs), half_width / -min(xs),
                half_width / max(ys), half_width / -min(ys)]

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
    # Z-up to the kits' Y-up (x, z, -y); to_game_space turns it back.
    mesh.positions = [(x, z, -y) for x, y, z in mesh.positions]
    return mesh


#: The two shipped variants: ``(seed, leaves, ears, reach, half-width,
#: height)``.  Half-widths and heights are the Kenney stalks' boxes the maze
#: is laid out by (``MODEL_BOX``), so walls and clear zones do not move.
#: Leaves 14 -> 18 and 12 -> 18 (the walls still
#: read as thin): the silhouette, averaged over yaw, grew 13% and 11% (measured with
#: ``dressing.lining.hidden_fraction``) for 492 and 452 triangles, inside
#: the library's 600.
VARIANTS: dict[str, tuple[int, int, int, float, float, float]] = {
    "corn_stalk": (7, 18, 2, 0.8, 16.956, 96.0),
    "corn_stalk_thin": (23, 18, 1, 0.58, 10.951, 90.0),
}


def corn_stalk(member: str) -> Mesh:
    seed, leaves, ears, reach, half, height = VARIANTS[member]
    return _fit_footprint(stalk_mesh(seed, height, leaves, ears, reach), half, height)


#: The corn-wall surface's tile: how many game units one repeat of
#: :func:`paint_corn_wall` covers (the recipe's ``Material`` size must match).
#: 384, not 128 (a 128-unit repeat on a 200-tall
#: wall showed the same stalks three times over and read as wallpaper).
WALL_TILE_UNITS = 384.0
#: The painted tile's pixel size (:class:`library.PropMaterial` ``size``).
WALL_TILE_PIXELS = 2048
#: How dark each of the three depths is drawn (back, middle, front): the
#: wall is what shows *between* the lining stalks, so it is drawn as corn in
#: shadow further in, not lit corn (the brighter
#: paint read as a flat painted wall behind the stalks).
WALL_DEPTH_DIM = (0.16, 0.27, 0.42)


def paint_corn_wall(size: int = WALL_TILE_PIXELS, seed: int = 11):
    """A seamless tile of a corn field seen from its edge: stalks and arching
    leaves in three depths, darkest at the back, on deep shadow.

    Whatever the lining leaves open shows the wall behind it.  The dark earth surface read as a dirt wall between the
    stalks; this one reads as more corn further in.  It repeats every
    :data:`WALL_TILE_UNITS` both ways, so every stroke is drawn wrapped
    (each shape nine times, offset a tile each way).  Colours are the
    stalk material's own range (``library.CORN_LEAF``: late-season olive to
    straw), dimmed with depth (:data:`WALL_DEPTH_DIM`), under pools of
    shadow.  Returns ``(colour, None)``: the prop
    materials are ``lit_detail`` with no normal map.
    """
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    ss = 2  # draw at twice the size, then downsample: anti-aliased edges
    n = size * ss
    px = n / WALL_TILE_UNITS  # pixels per game unit
    img = Image.new("RGB", (n, n), (7, 8, 4))
    # Stalk counts are per 128 units of tile, both ways.
    area = (WALL_TILE_UNITS / 128.0) ** 2
    draw = ImageDraw.Draw(img)

    def wrapped(points):
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                yield [(x + dx, y + dy) for x, y in points]

    def colour(t: float, depth: int) -> tuple[int, int, int]:
        olive, straw = (0.40, 0.44, 0.20), (0.74, 0.63, 0.40)
        dim = WALL_DEPTH_DIM[depth] * rng.uniform(0.75, 1.15)
        return tuple(int(255 * min(1.0, (a + (b - a) * t) * dim)) for a, b in zip(olive, straw))

    def blade(x0: float, y0: float, side: int, length: float, width: float, depth: int) -> None:
        # A leaf leaving the stem upwards and out, arching over into a droop
        # (image y grows downwards).
        rise, droop = rng.uniform(0.35, 0.8), rng.uniform(0.6, 1.4)
        steps = 10
        spine = []
        for i in range(steps + 1):
            f = i / steps
            spine.append((x0 + side * length * f, y0 - length * (rise * f - droop * f * f)))
        left, right = [], []
        for i, (x, y) in enumerate(spine):
            f = i / steps
            w = width * (1.0 - f) ** 0.7 * (0.6 + 0.4 * math.sin(math.pi * min(1.0, f * 1.6)))
            left.append((x, y - w / 2))
            right.append((x, y + w / 2))
        fill = colour(rng.uniform(0.0, 1.0), depth)
        for poly in wrapped(left + right[::-1]):
            draw.polygon(poly, fill=fill)

    for depth, count in ((0, 30), (1, 16), (2, 9)):
        for _ in range(int(count * area)):
            x = rng.uniform(0, n)
            stem_w = rng.uniform(0.7, 1.1) * px * (0.7 + 0.15 * depth)
            sway = rng.uniform(-1.5, 1.5) * px
            fill = colour(rng.uniform(0.15, 0.55), depth)
            # The stem: a full-height strip, swaying once per tile so it wraps.
            pts_l = [(x + sway * math.sin(2 * math.pi * k / 16), n * k / 16) for k in range(17)]
            poly = [(a - stem_w / 2, b) for a, b in pts_l] + [(a + stem_w / 2, b) for a, b in pts_l[::-1]]
            for p in wrapped(poly):
                draw.polygon(p, fill=fill)
            for _ in range(rng.randint(4, 6)):
                y = rng.uniform(0, n)
                blade(x, y, rng.choice((-1, 1)), rng.uniform(26, 56) * px * (0.8 + 0.1 * depth),
                      rng.uniform(2.6, 4.2) * px * (0.8 + 0.1 * depth), depth)
        if depth < 2:
            img = img.filter(ImageFilter.GaussianBlur(radius=(1.6 - 0.8 * depth) * ss))
            draw = ImageDraw.Draw(img)
    img = img.resize((size, size), Image.LANCZOS)
    # Mottle: a seamless low-frequency light/shade and a fine grain, so the
    # flat-filled shapes read as lit leaves rather than vector art.
    import numpy as np
    from scipy import ndimage

    nrng = np.random.default_rng(seed)
    # Pools of deeper shadow about a stalk-row apart (40-80 units), so no
    # two stretches of wall are lit alike and a gap between the lining
    # stalks reads as depth.
    unit = size / WALL_TILE_UNITS
    low = ndimage.gaussian_filter(nrng.standard_normal((size, size)), 24 * unit, mode="wrap")
    fine = ndimage.gaussian_filter(nrng.standard_normal((size, size)), 1.2, mode="wrap")
    shade = np.clip(1.0 + 0.55 * low / (np.abs(low).max() or 1.0) + 0.12 * fine / (np.abs(fine).max() or 1.0),
                    0.35, 1.6)
    a = np.asarray(img).astype(np.float32) * shade[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), None
