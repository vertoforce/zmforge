"""The gamble machine: a free-standing, slightly sinister cash machine, built by our own code.

The gamble (2,000 points for a one-in-four shot at 10,000) needs a
body that reads as a cash machine from across a room, and the game ships no
ATM.  So this builds one from its real parts, in inches, Z up, its front
(screen, keypad, cash slot) facing -Y like the stock perk machines:

* a bolted **anchor plate** on the floor and a recessed **kick plinth** in
  diamond plate;
* the **safe**: a chunky steel cabinet, bevelled on every edge, with a proud
  bolted door plate, a lock and a pull handle, angle-iron guards on its front
  corners and a dent knocked into its front left corner;
* the **cash drawer**: a protruding housing with a deep dark mouth and a lip;
* the **console deck**, sloped towards the player, with a raised frame round
  a 4 x 4 keypad of individually modelled keys (digits, CANCEL / CLEAR /
  ENTER and a blank);
* the **fascia**: a thick screen bezel with four soft keys each side, the
  glowing screen set back inside it, a **hood** over it, a card reader with
  a lit mouth, a receipt slot and a taped "OUT OF ORDER?" note;
* the lit **topper** sign on two standoffs, a **security dome** camera on it,
  and a **cable conduit** from a junction box on the back down into the floor.

Every part is a convex piece (a bevelled box, a prism or a dome), so each
piece's faces unwrap by planar projection without overlap: one chart per
(piece, facing axis), packed into the atlas at a fixed texel density
(:data:`BODY_PPI`, 14 px per inch; the keys, labels and bolts denser).
Repeated parts (bolts, soft keys) share one chart per facing axis.

Normals are "weighted": each vertex takes the normal of the flat face it
belongs to, so flat faces shade flat and each chamfer shades as a smooth
round between its two faces -- the standard hard-surface trick that makes a
cheap bevel read as a machined edge.

Two materials: ``body`` (a painted colour map plus a normal map, both baked
here from the same geometry: see :func:`paint_body`) and ``glow`` (the
screen, the topper face and the card reader's mouth light, an emissive
material; :func:`paint_glow`).  The photo sources are ambientCG CC0 sets
(``library.TEXTURES``): scratched paint, rust, bare metal and diamond plate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .wavefront import Mesh, Triangle

__all__ = ["atm_mesh", "paint_body", "paint_glow", "model", "HEIGHT"]

Vec = tuple[float, float, float]

#: Default texel density of the body atlas, pixels per inch (stock props run
#: about 256-512 px per metre, 6.5-13 px per inch).  Scaled down together if
#: the charts do not fit.
BODY_PPI = 14.0
GLOW_PPI = 40.0

# Surface kinds, painted by paint_body.
PAINT, ACCENT, STEEL, DARK, BLACK, TREAD, KEY, KEY_RED, KEY_YEL, KEY_GRN, PAPER, SMOKE, GALV = range(1, 14)
# Glow kinds.
SCREEN, SIGN, LED = range(20, 23)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


@dataclass
class Piece:
    """One convex part: its triangles share vertices; ``flat`` marks the
    triangles of its main faces (their normals win at shared vertices)."""

    name: str
    kind: int
    material: str = "body"
    share: str = ""  # instanced parts share charts under this name
    anchor: Vec = (0.0, 0.0, 0.0)  # chart origin for shared parts
    ppi: float = BODY_PPI
    label: str = ""  # text painted on the piece's most-facing chart
    label_axis: str = ""
    dirt: float = 0.0
    positions: list[Vec] = field(default_factory=list)
    tris: list[tuple[int, int, int]] = field(default_factory=list)
    flat: list[bool] = field(default_factory=list)


def _bevel_box(name: str, kind: int, lo: Vec, hi: Vec, r: float = 0.4, *,
               rot: tuple[float, Vec] | None = None, sub: int = 1, **kw) -> Piece:
    """A box ``lo``..``hi`` with every edge chamfered by ``r``; faces split
    ``sub`` x ``sub`` (for a dent).  ``rot`` = (degrees about X, pivot)."""
    p = Piece(name, kind, **kw)
    # At most 40% of each half-extent, so no face collapses to a sliver the
    # converter drops as degenerate (the door plate did at 2.01).
    r = min(r, 0.4 * (hi[0] - lo[0]) / 2, 0.4 * (hi[1] - lo[1]) / 2, 0.4 * (hi[2] - lo[2]) / 2)
    c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    h = tuple((hi[i] - lo[i]) / 2 for i in range(3))
    index: dict[tuple, int] = {}

    def vert(v: Vec) -> int:
        key = tuple(round(x, 5) for x in v)
        if key not in index:
            index[key] = len(p.positions)
            p.positions.append(v)
        return index[key]

    # Each face is a grid on the inner (h - r) square, pushed out to h.
    faces = []
    for axis in range(3):
        for sign in (-1, 1):
            a1, a2 = [(axis + 1) % 3, (axis + 2) % 3]
            grid = []
            for i in range(sub + 1):
                row = []
                for j in range(sub + 1):
                    v = [0.0, 0.0, 0.0]
                    v[axis] = c[axis] + sign * h[axis]
                    v[a1] = c[a1] - (h[a1] - r) + 2 * (h[a1] - r) * i / sub
                    v[a2] = c[a2] - (h[a2] - r) + 2 * (h[a2] - r) * j / sub
                    row.append(vert(tuple(v)))  # type: ignore[arg-type]
                grid.append(row)
            faces.append((axis, sign, grid))
            for i in range(sub):
                for j in range(sub):
                    q = [grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]]
                    _quad(p, q, True)
    # Edge chamfers and corner triangles: connect face-border vertices.
    # Build by brute force: for each pair of adjacent faces, join their shared edge.
    def border(axis, sign, a_other, s_other):
        """The vertices of face (axis, sign) on the side towards (a_other, s_other)."""
        for ax, sg, grid in faces:
            if ax == axis and sg == sign:
                a1, a2 = (axis + 1) % 3, (axis + 2) % 3
                if a_other == a1:
                    line = grid[0 if s_other < 0 else sub]
                    return [line[j] for j in range(sub + 1)]
                line = [grid[i][0 if s_other < 0 else sub] for i in range(sub + 1)]
                return line
        raise AssertionError

    for ax in range(3):
        for bx in range(ax + 1, 3):
            for sa in (-1, 1):
                for sb in (-1, 1):
                    e1 = border(ax, sa, bx, sb)
                    e2 = border(bx, sb, ax, sa)
                    # Order both along the third axis.
                    third = 3 - ax - bx
                    e1 = sorted(e1, key=lambda i: p.positions[i][third])
                    e2 = sorted(e2, key=lambda i: p.positions[i][third])
                    for k in range(len(e1) - 1):
                        _quad_out(p, [e1[k], e1[k + 1], e2[k + 1], e2[k]], c)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                corner = []
                for axis, s in ((0, sx), (1, sy), (2, sz)):
                    v = [c[0] + sx * (h[0] - r), c[1] + sy * (h[1] - r), c[2] + sz * (h[2] - r)]
                    v[axis] = c[axis] + s * h[axis]
                    corner.append(vert(tuple(v)))  # type: ignore[arg-type]
                _tri_out(p, corner, c, False)
    _fix_winding(p)
    if rot is not None:
        _rotate_x(p, *rot)
    return p


def _rotate_x(p: Piece, degrees: float, pivot: Vec) -> None:
    a = math.radians(degrees)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y, z in p.positions:
        y0, z0 = y - pivot[1], z - pivot[2]
        out.append((x, pivot[1] + y0 * ca - z0 * sa, pivot[2] + y0 * sa + z0 * ca))
    p.positions = out


def _quad(p: Piece, q: list[int], flat: bool) -> None:
    p.tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    p.flat += [flat, flat]


def _orient(p: Piece, t: tuple[int, int, int], centre: Vec) -> tuple[int, int, int]:
    a, b, c = (p.positions[i] for i in t)
    n = _cross(_sub(b, a), _sub(c, a))
    mid = tuple((a[i] + b[i] + c[i]) / 3 for i in range(3))
    return t if _dot(n, _sub(mid, centre)) >= 0 else (t[0], t[2], t[1])  # type: ignore[return-value]


def _quad_out(p: Piece, q: list[int], centre: Vec) -> None:
    for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
        a, b, c = (p.positions[i] for i in t)
        if math.dist(a, b) < 1e-6 or math.dist(b, c) < 1e-6 or math.dist(a, c) < 1e-6:
            continue
        p.tris.append(_orient(p, t, centre))
        p.flat.append(False)


def _tri_out(p: Piece, t: list[int], centre: Vec, flat: bool) -> None:
    p.tris.append(_orient(p, (t[0], t[1], t[2]), centre))
    p.flat.append(flat)


def _fix_winding(p: Piece) -> None:
    """Face every face of the (convex) piece outward, grid faces included."""
    cx = tuple(sum(v[i] for v in p.positions) / len(p.positions) for i in range(3))
    p.tris = [_orient(p, t, cx) for t in p.tris]  # type: ignore[arg-type]


def _prism(name: str, kind: int, centre: Vec, axis: str, radius: float, length: float,
           sides: int = 8, chamfer: float = 0.0, phase: float = 0.0, top_scale: float = 1.0,
           **kw) -> Piece:
    """A closed n-sided prism along ``axis`` ('x','y','z' or '-y' ...) from
    ``centre`` (its base) for ``length``; ``chamfer`` bevels its far end."""
    p = Piece(name, kind, **kw)
    sign = -1.0 if axis.startswith("-") else 1.0
    ax = "xyz".index(axis[-1])
    a1, a2 = (ax + 1) % 3, (ax + 2) % 3

    def ring(t: float, r: float) -> list[int]:
        out = []
        for k in range(sides):
            ang = phase + 2 * math.pi * k / sides
            v = list(centre)
            v[ax] += sign * t
            v[a1] += r * math.cos(ang)
            v[a2] += r * math.sin(ang)
            out.append(len(p.positions))
            p.positions.append(tuple(v))  # type: ignore[arg-type]
        return out

    rings = [ring(0.0, radius), ring(length - chamfer, radius * top_scale)]
    if chamfer > 0:
        rings.append(ring(length, radius * top_scale - chamfer))
    for i in range(len(rings) - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            _quad(p, [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]], i == 0)
    for rg in (rings[0], rings[-1]):
        for k in range(1, sides - 1):
            p.tris.append((rg[0], rg[k], rg[k + 1]))
            p.flat.append(True)
    _fix_winding(p)
    return p


def _dome(name: str, kind: int, centre: Vec, radius: float, rings: int = 5, sides: int = 12,
          **kw) -> Piece:
    """A hemisphere on +Z from ``centre``, closed underneath."""
    p = Piece(name, kind, **kw)
    grid = []
    for i in range(rings + 1):
        el = (math.pi / 2) * i / rings
        row = []
        for k in range(sides if i < rings else 1):
            az = 2 * math.pi * k / sides
            p.positions.append((centre[0] + radius * math.cos(el) * math.cos(az),
                                centre[1] + radius * math.cos(el) * math.sin(az),
                                centre[2] + radius * math.sin(el)))
            row.append(len(p.positions) - 1)
        grid.append(row)
    for i in range(rings):
        for k in range(sides):
            k2 = (k + 1) % sides
            if i + 1 == rings:
                p.tris.append((grid[i][k], grid[i][k2], grid[i + 1][0]))
                p.flat.append(False)
            else:
                _quad(p, [grid[i][k], grid[i][k2], grid[i + 1][k2], grid[i + 1][k]], False)
    for k in range(1, sides - 1):
        p.tris.append((grid[0][0], grid[0][k], grid[0][k + 1]))
        p.flat.append(True)
    _fix_winding(p)
    return p


def _panel(name: str, kind: int, corners: list[Vec], **kw) -> Piece:
    """A single flat quad (the note, the glass), wound so its normal is
    ``cross(c1 - c0, c3 - c0)``."""
    p = Piece(name, kind, **kw)
    p.positions = list(corners)
    p.tris = [(0, 1, 2), (0, 2, 3)]
    p.flat = [True, True]
    return p


# --------------------------------------------------------------------------
# The design.  Inches; the front faces -Y; x and y are centred on the plate.

#: The keypad: rows top (far) to bottom (near), the function column last.
KEYS = (("1", "2", "3", "CANCEL"), ("4", "5", "6", "CLEAR"), ("7", "8", "9", "ENTER"),
        ("*", "0", "#", ""))
DECK_TILT = 15.0
DECK_CENTRE = (0.0, -12.3, 45.6)
DECK_SIZE = (39.4, 11.0, 3.0)


def _deck_point(x: float, w: float, n: float) -> Vec:
    """A point on the console deck: ``x`` across, ``w`` towards the back along
    its top, ``n`` above its top surface."""
    a = math.radians(DECK_TILT)
    top = DECK_SIZE[2] / 2
    y = DECK_CENTRE[1] + w * math.cos(a) - (top + n) * math.sin(a)
    z = DECK_CENTRE[2] + w * math.sin(a) + (top + n) * math.cos(a)
    return (x, y, z)


def _on_deck(p: Piece, pivot_x: float = 0.0) -> Piece:
    """Pieces built flat on z = 0 around (x, w, n) = (x, y, z) are laid onto the deck."""
    p.positions = [_deck_point(x, y, z) for x, y, z in p.positions]
    return p


def _bolt(name: str, at: Vec, axis: str, r: float = 0.42, **kw) -> list[Piece]:
    """A hex bolt head with a washer, standing out of a surface along ``axis``."""
    kw.setdefault("share", f"bolt{r:g}{axis}")
    kw.setdefault("ppi", 40.0)
    washer = _prism(name + "_w", STEEL, at, axis, r * 1.45, 0.08, sides=12, anchor=at,
                    **{**kw, "share": kw["share"] + "w"})
    sign = -1.0 if axis.startswith("-") else 1.0
    ax = "xyz".index(axis[-1])
    top = list(at)
    top[ax] += sign * 0.08
    head = _prism(name, STEEL, tuple(top), axis, r, r * 0.55, sides=6, chamfer=r * 0.18,  # type: ignore[arg-type]
                  phase=math.pi / 6, anchor=at, **kw)
    return [washer, head]


def _dent(p: Piece, centre: Vec, radius: float, depth: float, direction: Vec) -> None:
    """Push the piece's vertices near ``centre`` along ``direction`` (a dent)."""
    out = []
    for v in p.positions:
        d = math.dist(v, centre)
        k = depth * math.exp(-(d / radius) ** 2 * 2.2) if d < radius * 1.6 else 0.0
        out.append((v[0] + direction[0] * k, v[1] + direction[1] * k, v[2] + direction[2] * k))
    p.positions = out


def pieces() -> list[Piece]:
    P: list[Piece] = []
    add = P.append
    # Floor: anchor plate and its bolts, the kick plinth.
    add(_bevel_box("plate", DARK, (-22, -18, 0), (22, 18, 0.5), 0.18, dirt=0.8))
    for sx in (-1, 1):
        for sy in (-1, 1):
            P += _bolt(f"plate_bolt_{sx}{sy}", (sx * 20.8, sy * 16.4, 0.5), "z", r=0.62)
    add(_bevel_box("plinth", TREAD, (-19.2, -13.2, 0.5), (19.2, 13.2, 5.0), 0.3, dirt=0.7))
    # The safe, dented at its front left corner.
    safe = _bevel_box("safe", PAINT, (-20, -14, 5), (20, 14, 44), 0.8, sub=10)
    _dent(safe, (-20.0, -14.0, 13.0), 5.5, 1.1, _unit((1.0, 0.7, 0.1)))
    add(safe)
    add(_bevel_box("door", PAINT, (-16.5, -14.4, 9.0), (16.5, -13.9, 32.0), 0.25))
    for bx in (-15.3, 0.0, 15.3):
        for bz in (10.2, 30.8):
            P += _bolt(f"door_bolt_{bx}_{bz}", (bx, -14.4, bz), "-y")
    P.append(_prism("lock", STEEL, (12.0, -14.4, 21.0), "-y", 1.0, 0.45, sides=16, chamfer=0.12,
                    ppi=40.0, label="lock", label_axis="-y"))
    # Pull handle: a bar on two posts.
    add(_bevel_box("handle_bar", STEEL, (5.0, -16.3, 24.4), (10.5, -15.5, 25.4), 0.25, ppi=30.0))
    for hx in (5.6, 9.9):
        add(_bevel_box(f"handle_post_{hx}", STEEL, (hx - 0.35, -15.6, 24.55), (hx + 0.35, -14.4, 25.25),
                       0.12, ppi=30.0))
    # Angle-iron guards on the safe's front corners.
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 20.35, sx * 17.6))
        add(_bevel_box(f"guard_front_{sx}", DARK, (x0, -14.45, 5.2), (x1, -13.8, 43.8), 0.15, dirt=0.3))
        x0, x1 = sorted((sx * 20.35, sx * 19.8))
        add(_bevel_box(f"guard_side_{sx}", DARK, (x0, -14.45, 5.2), (x1, -11.6, 43.8), 0.15, dirt=0.3))
        for bz in (8.0, 24.5, 41.0):
            P += _bolt(f"guard_bolt_{sx}_{bz}", (sx * 18.95, -14.45, bz), "-y", r=0.34)
    # Side panels: a proud armour plate bolted to each side of the safe; the
    # upper body (set in an inch, so the safe's shoulder shows) has bolts and
    # a louvred vent on each side.
    for sx in (-1, 1):
        axis = "x" if sx > 0 else "-x"
        x0, x1 = sorted((sx * 19.9, sx * 20.35))
        add(_bevel_box(f"safe_plate_{sx}", PAINT, (x0, -10.5, 8.5), (x1, 12.0, 40.5), 0.2))
        for by in (-9.3, 10.8):
            for bz in (9.7, 39.3):
                P += _bolt(f"side_bolt_{sx}_{by}_{bz}", (sx * 20.35, by, bz), axis)
            for bz in (47.5, 74.0):
                P += _bolt(f"upper_bolt_{sx}_{by}_{bz}", (sx * 19.0, by, bz), axis)
        x0, x1 = sorted((sx * 18.9, sx * 19.08))
        add(_bevel_box(f"vent_back_{sx}", BLACK, (x0, -5.4, 61.3), (x1, 9.4, 72.2), 0.04, dirt=1.0))
        for i in range(7):
            zc = 62.0 + i * 1.5
            x0, x1 = sorted((sx * 18.95, sx * 19.25))
            slat = _bevel_box(f"vent_{sx}_{i}", DARK, (x0, -5.4, zc - 0.55), (x1, 9.4, zc + 0.55), 0.08,
                              share=f"vent_slat{sx}", anchor=(sx * 18.95, -5.4, zc), ppi=16.0)
            # Tilt: the slat's lower edge stands out, like a louvre shedding rain.
            slat.positions = [(x + sx * 0.5 * (zc + 0.55 - z), y, z) for x, y, z in slat.positions]
            add(slat)
    # Cash drawer: top, lip, cheeks and the dark mouth.
    add(_bevel_box("cash_top", STEEL, (-10.0, -16.6, 37.3), (10.0, -13.9, 39.4), 0.35))
    add(_bevel_box("cash_lip", STEEL, (-10.0, -17.3, 33.0), (10.0, -13.9, 34.8), 0.35))
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 10.0, sx * 8.5))
        add(_bevel_box(f"cash_cheek_{sx}", STEEL, (x0, -16.6, 34.6), (x1, -13.9, 37.5), 0.2))
    add(_bevel_box("cash_mouth", BLACK, (-8.6, -15.3, 34.7), (8.6, -13.9, 37.4), 0.05, dirt=1.0))
    # Console deck, sloped towards the player.
    lo = tuple(DECK_CENTRE[i] - DECK_SIZE[i] / 2 for i in range(3))
    hi = tuple(DECK_CENTRE[i] + DECK_SIZE[i] / 2 for i in range(3))
    add(_bevel_box("deck", ACCENT, lo, hi, 0.5, rot=(DECK_TILT, DECK_CENTRE)))  # type: ignore[arg-type]
    # Keypad: a raised frame and 16 keys.
    kx, kw_ = 1.72, 1.5  # pitch across, pitch along
    cw = -1.55  # keypad centre along the deck
    half_x, half_w = 2 * kx + 0.35, 2 * kw_ + 0.35
    for name, (x0, x1, w0, w1) in {
        "kp_near": (-half_x - 0.5, half_x + 0.5, cw - half_w - 0.5, cw - half_w),
        "kp_far": (-half_x - 0.5, half_x + 0.5, cw + half_w, cw + half_w + 0.5),
        "kp_left": (-half_x - 0.5, -half_x, cw - half_w, cw + half_w),
        "kp_right": (half_x, half_x + 0.5, cw - half_w, cw + half_w),
    }.items():
        add(_on_deck(_bevel_box(name, DARK, (x0, w0, -0.2), (x1, w1, 0.45), 0.12, ppi=24.0)))
    # Privacy shield: two tapered wings and a back plate standing round the keys.
    for side in (-1, 1):
        x0, x1 = sorted((side * (half_x + 0.1), side * (half_x + 0.45)))
        wing = _bevel_box(f"kp_wing_{side}", DARK, (x0, cw - half_w, 0.3),
                          (x1, cw + half_w + 0.5, 2.6), 0.1, ppi=24.0)
        wing.positions = [(x, y, 0.3 + (z - 0.3) * (0.35 + 0.65 * (y - (cw - half_w)) / (2 * half_w + 0.5)))
                          for x, y, z in wing.positions]
        add(_on_deck(wing))
    add(_on_deck(_bevel_box("kp_back", DARK, (-half_x - 0.45, cw + half_w + 0.1, 0.3),
                            (half_x + 0.45, cw + half_w + 0.5, 2.6), 0.1, ppi=24.0)))
    add(_on_deck(_bevel_box("kp_well", DARK, (-half_x, cw - half_w, -0.2), (half_x, cw + half_w, 0.02),
                            0.02, ppi=24.0, dirt=0.8)))
    for row, keys in enumerate(KEYS):
        for col, text in enumerate(keys):
            kind = {"CANCEL": KEY_RED, "CLEAR": KEY_YEL, "ENTER": KEY_GRN}.get(text, KEY)
            x = (col - 1.5) * kx
            w = cw + (1.5 - row) * kw_
            add(_on_deck(_bevel_box(f"key_{row}{col}", kind, (x - 0.68, w - 0.6, 0.0),
                                    (x + 0.68, w + 0.6, 0.42), 0.12, ppi=48.0,
                                    label=text or " ", label_axis="deck")))
    # Upper body, framed at the front by red uprights and a cap rail.
    add(_bevel_box("upper", PAINT, (-19, -10, 44), (19, 14, 77), 0.8, sub=2))
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 19.35, sx * 17.0))
        add(_bevel_box(f"frame_{sx}", ACCENT, (x0, -10.9, 45.5), (x1, -9.6, 75.4), 0.35))
    add(_bevel_box("frame_cap", ACCENT, (-19.35, -10.9, 75.2), (19.35, -9.6, 77.4), 0.35))
    # A rubber nosing along the deck's front edge.
    P.append(_prism("deck_nose", DARK, _deck_point(-19.75, -5.0, -1.5), "x", 0.8, 39.5, sides=12,
                    ppi=18.0, dirt=0.4))
    # Screen bezel: four thick strips round the glass, soft keys in the side strips.
    sx0, sx1, sz0, sz1 = -8.0, 8.0, 55.0, 67.0
    for name, lo_, hi_ in (("bezel_top", (-10.2, -11.4, sz1), (10.2, -9.9, sz1 + 1.6)),
                           ("bezel_bottom", (-10.2, -11.4, sz0 - 1.6), (10.2, -9.9, sz0)),
                           ("bezel_left", (-10.2, -11.4, sz0), (sx0, -9.9, sz1)),
                           ("bezel_right", (sx1, -11.4, sz0), (10.2, -9.9, sz1))):
        add(_bevel_box(name, DARK, lo_, hi_, 0.3, ppi=20.0))
    # The step down to the glass: a thin inner frame, set back.
    for name, lo_, hi_ in (("liner_top", (sx0, -10.6, sz1 - 0.35), (sx1, -9.95, sz1)),
                           ("liner_bottom", (sx0, -10.6, sz0), (sx1, -9.95, sz0 + 0.35)),
                           ("liner_left", (sx0, -10.6, sz0), (sx0 + 0.35, -9.95, sz1)),
                           ("liner_right", (sx1 - 0.35, -10.6, sz0), (sx1, -9.95, sz1))):
        add(_bevel_box(name, BLACK, lo_, hi_, 0.06, ppi=20.0, dirt=0.5))
    add(_panel("screen", SCREEN, [(sx0 + 0.3, -10.02, sz0 + 0.3), (sx1 - 0.3, -10.02, sz0 + 0.3),
                                  (sx1 - 0.3, -10.02, sz1 - 0.3), (sx0 + 0.3, -10.02, sz1 - 0.3)],
               material="glow", ppi=GLOW_PPI))
    for side in (-1, 1):
        for i in range(4):
            z = sz0 + 1.6 + i * 2.9
            x0, x1 = sorted((side * 8.55, side * 9.65))
            add(_bevel_box(f"softkey_{side}_{i}", DARK if side else DARK, (x0, -11.85, z), (x1, -11.35, z + 0.95),
                           0.12, share="softkey", anchor=(side * 9.1, -11.85, z), ppi=40.0))
    # Hood: a top plate and two tapered cheeks.
    add(_bevel_box("hood_top", ACCENT, (-11.9, -17.0, 69.0), (11.9, -9.9, 70.3), 0.3))
    for side in (-1, 1):
        x0, x1 = sorted((side * 10.7, side * 11.9))
        cheek = _bevel_box(f"hood_cheek_{side}", ACCENT, (x0, -17.0, 52.5), (x1, -9.9, 69.2), 0.25)
        cheek.positions = [(x, y, z + max(0.0, (-10.5 - y)) * 1.15 * (69.0 - z) / 16.7)
                           for x, y, z in cheek.positions]
        add(cheek)
    # Card reader (right of the screen) with a lit mouth, and the receipt slot below it.
    add(_bevel_box("card_top", DARK, (12.2, -12.3, 60.1), (17.4, -9.9, 62.2), 0.3, ppi=24.0))
    add(_bevel_box("card_bottom", DARK, (12.2, -12.6, 57.4), (17.4, -9.9, 59.6), 0.3, ppi=24.0))
    add(_bevel_box("card_mouth", BLACK, (12.8, -11.0, 59.4), (16.8, -9.9, 60.3), 0.04, dirt=1.0))
    add(_panel("card_led", LED, [(12.9, -12.64, 59.05), (16.7, -12.64, 59.05), (16.7, -12.64, 59.45),
                                 (12.9, -12.64, 59.45)], material="glow", ppi=GLOW_PPI))
    add(_bevel_box("receipt_top", DARK, (12.2, -11.3, 53.2), (17.4, -9.9, 54.3), 0.2, ppi=24.0))
    add(_bevel_box("receipt_bottom", DARK, (12.2, -11.6, 51.6), (17.4, -9.9, 52.8), 0.2, ppi=24.0))
    add(_bevel_box("receipt_mouth", BLACK, (12.6, -10.6, 52.7), (17.0, -9.9, 53.3), 0.03, dirt=1.0))
    # The taped note, a little crooked, left of the screen.
    a = math.radians(-4.0)

    def note_pt(u: float, v: float) -> Vec:
        cx, cz = -14.5, 61.2
        return (cx + u * math.cos(a) - v * math.sin(a), -10.04, cz + u * math.sin(a) + v * math.cos(a))
    add(_panel("note", PAPER, [note_pt(-2.55, -3.3), note_pt(2.55, -3.3), note_pt(2.55, 3.3),
                               note_pt(-2.55, 3.3)], ppi=44.0, label="note", label_axis="-y"))
    # Topper on two standoffs, its face lit, a lip round the face, a dome camera.
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 11.5, sx * 15.0))
        add(_bevel_box(f"standoff_{sx}", DARK, (x0, -5.0, 76.5), (x1, 5.0, 78.9), 0.25))
    add(_bevel_box("topper", ACCENT, (-19.6, -11.6, 78.6), (19.6, 9.6, 88.6), 0.6))
    for name, lo_, hi_ in (("lip_top", (-19.0, -12.3, 87.3), (19.0, -11.4, 88.2)),
                           ("lip_bottom", (-19.0, -12.3, 79.0), (19.0, -11.4, 79.9)),
                           ("lip_left", (-19.0, -12.3, 79.9), (-18.1, -11.4, 87.3)),
                           ("lip_right", (18.1, -12.3, 79.9), (19.0, -11.4, 87.3))):
        add(_bevel_box(name, STEEL, lo_, hi_, 0.2, ppi=20.0))
    add(_panel("sign", SIGN, [(-18.1, -11.62, 79.9), (18.1, -11.62, 79.9), (18.1, -11.62, 87.3),
                              (-18.1, -11.62, 87.3)], material="glow", ppi=GLOW_PPI))
    for sx in (-1, 1):
        for sz in (79.45, 87.75):
            P += _bolt(f"lip_bolt_{sx}_{sz}", (sx * 18.55, -12.3, sz), "-y", r=0.26)
    P.append(_prism("cam_base", DARK, (14.5, 1.0, 88.6), "z", 2.0, 0.55, sides=16, chamfer=0.15, ppi=30.0))
    P.append(_dome("cam_dome", SMOKE, (14.5, 1.0, 89.15), 1.75, ppi=30.0))
    # Cable conduit: junction box on the back, a tube down into the floor.
    add(_bevel_box("junction", GALV, (10.8, 14.0, 24.5), (15.2, 17.4, 31.0), 0.3, ppi=20.0))
    P.append(_prism("conduit", GALV, (13.0, 16.4, 0.0), "z", 0.85, 24.6, sides=10, ppi=24.0, dirt=0.4))
    P.append(_prism("conduit_flange", GALV, (13.0, 16.4, 0.0), "z", 1.6, 0.9, sides=10, chamfer=0.2,
                    top_scale=0.7, ppi=24.0, dirt=0.6))
    P.append(_prism("conduit_nut", GALV, (13.0, 16.4, 23.4), "z", 1.15, 1.2, sides=6, chamfer=0.12,
                    ppi=24.0))
    # Screws on the junction box lid.
    for jx in (11.5, 14.5):
        for jz in (25.2, 30.3):
            P += _bolt(f"jbox_screw_{jx}_{jz}", (jx, 17.4, jz), "y", r=0.22)
    return P


# --------------------------------------------------------------------------
# Unwrap: one chart per (piece or share, facing axis), packed on shelves.

AXES = {"x": (1, 0, 0), "-x": (-1, 0, 0), "y": (0, 1, 0), "-y": (0, -1, 0), "z": (0, 0, 1),
        "-z": (0, 0, -1)}
#: (u, v) directions per facing axis, right-handed as seen from outside.
FRAMES = {"x": ((0, 1, 0), (0, 0, 1)), "-x": ((0, -1, 0), (0, 0, 1)),
          "y": ((-1, 0, 0), (0, 0, 1)), "-y": ((1, 0, 0), (0, 0, 1)),
          "z": ((1, 0, 0), (0, 1, 0)), "-z": ((1, 0, 0), (0, -1, 0))}


def _deck_frame():
    a = math.radians(DECK_TILT)
    return ((1.0, 0.0, 0.0), (0.0, math.cos(a), math.sin(a)), (0.0, -math.sin(a), math.cos(a)))


@dataclass
class Chart:
    key: tuple
    material: str
    u_axis: Vec
    v_axis: Vec
    ppi: float
    lo: tuple[float, float] = (1e9, 1e9)
    hi: tuple[float, float] = (-1e9, -1e9)
    px: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y (top), w, h in the atlas
    pieces: list = field(default_factory=list)


@dataclass
class Model:
    mesh: Mesh
    charts: list[Chart]
    #: Per triangle: (piece index, chart index, flat, corner positions, corner normals, uvs px)
    tris: list
    pieces: list[Piece]
    sizes: dict[str, int]


def _axis_of(n: Vec, piece: Piece) -> str:
    if piece.label_axis == "deck" or piece.name.startswith(("kp_", "key_", "deck")):
        _, _, dn = _deck_frame()
        if _dot(n, dn) > 0.8:
            return "deck"
    best = max(AXES, key=lambda k: _dot(n, AXES[k]))
    return best


PAD = 5

#: Faces nobody sees (buried in another part or on the floor) get few texels.
HIDDEN = {("safe", "z"): 0.05, ("safe", "-z"): 0.03, ("upper", "-z"): 0.03, ("plinth", "z"): 0.05,
          ("plinth", "-z"): 0.03, ("plate", "-z"): 0.03, ("conduit", "-z"): 0.1,
          ("conduit_flange", "-z"): 0.1, ("junction", "-y"): 0.05, ("cash_mouth", "y"): 0.05,
          ("card_mouth", "y"): 0.05, ("receipt_mouth", "y"): 0.05, ("kp_well", "-z"): 0.05}


def _pack(charts: list[Chart], size: int, scale: float) -> bool:
    x = y = row_h = 0
    for c in sorted(charts, key=lambda c: -(c.hi[1] - c.lo[1]) * c.ppi):
        w = max(2, math.ceil((c.hi[0] - c.lo[0]) * c.ppi * scale)) + 2 * PAD
        h = max(2, math.ceil((c.hi[1] - c.lo[1]) * c.ppi * scale)) + 2 * PAD
        if x + w > size:
            x, y, row_h = 0, y + row_h, 0
        if y + h > size or w > size:
            return False
        c.px = (x + PAD, y + PAD, w - 2 * PAD, h - 2 * PAD)
        x += w
        row_h = max(row_h, h)
    return True


@lru_cache(maxsize=1)
def model() -> Model:
    P = pieces()
    tris = []
    charts: dict[tuple, Chart] = {}
    share_axes: dict[str, list] = {}
    for pi, piece in enumerate(P):
        # Weighted vertex normals: flat faces dominate, chamfers interpolate.
        acc = [[0.0, 0.0, 0.0] for _ in piece.positions]
        for t, fl in zip(piece.tris, piece.flat):
            a, b, c = (piece.positions[i] for i in t)
            n = _cross(_sub(b, a), _sub(c, a))
            area = math.sqrt(_dot(n, n)) / 2
            if area < 1e-9:
                continue
            nu = _unit(n)
            wgt = area * (1000.0 if fl else 1.0)
            for i in t:
                for k in range(3):
                    acc[i][k] += nu[k] * wgt
        vn = [_unit(tuple(v)) for v in acc]  # type: ignore[arg-type]
        first = piece.share and piece.share not in share_axes
        if first:
            share_axes[piece.share] = []
        for ti, (t, fl) in enumerate(zip(piece.tris, piece.flat)):
            a, b, c = (piece.positions[i] for i in t)
            n = _cross(_sub(b, a), _sub(c, a))
            if _dot(n, n) < 1e-14:
                continue
            fn = _unit(n)
            # Instances of a shared part take the first one's axis per
            # triangle: a facet on a 45-degree tie must not flip between them.
            if piece.share and not first:
                axis = share_axes[piece.share][ti]
            else:
                axis = _axis_of(fn, piece)
                if first:
                    share_axes[piece.share] += [None] * (ti + 1 - len(share_axes[piece.share]))
                    share_axes[piece.share][ti] = axis
            if axis == "deck":
                u_ax, v_ax, _ = _deck_frame()
            else:
                u_ax, v_ax = FRAMES[axis]
            key = (piece.share or piece.name, axis)
            ch = charts.get(key)
            if ch is None:
                ch = charts[key] = Chart(key, piece.material, u_ax, v_ax, piece.ppi)  # type: ignore[arg-type]
            if piece.name not in ch.pieces:
                ch.pieces.append(piece.name)
            local = []
            for i in t:
                q = _sub(piece.positions[i], piece.anchor if piece.share else (0.0, 0.0, 0.0))
                local.append((_dot(q, u_ax), _dot(q, v_ax)))  # type: ignore[arg-type]
            if not (piece.share and ch.lo[0] < 1e8 and len(ch.pieces) > 1):
                ch.lo = (min(ch.lo[0], *(l[0] for l in local)), min(ch.lo[1], *(l[1] for l in local)))
                ch.hi = (max(ch.hi[0], *(l[0] for l in local)), max(ch.hi[1], *(l[1] for l in local)))
            tris.append((pi, key, fl, [piece.positions[i] for i in t], [vn[i] for i in t], local))
    chart_list = list(charts.values())
    for c in chart_list:
        c.ppi *= HIDDEN.get(c.key, 0.4 if c.key[1] == "-z" else 1.0)
    sizes = {"body": 2048, "glow": 1024}
    for material, size in sizes.items():
        group = [c for c in chart_list if c.material == material]
        scale = 1.0
        while not _pack(group, size, scale):
            scale *= 0.95
        # Grow into spare room (up to 1.6x) so the atlas is used.
        while scale < 1.6 and _pack(group, size, scale * 1.04):
            scale *= 1.04
        _pack(group, size, scale)
        for c in group:
            c.ppi *= scale
    # Mesh in the kits' convention: Y up (x, z, -y), v up the image.
    mesh = Mesh(source="generated: props/atm.py")
    out_tris = []
    for pi, key, fl, pos, nrm, local in tris:
        ch = charts[key]
        size = sizes[ch.material]
        base = len(mesh.positions)
        uvs = []
        for (x, y, z), (nx, ny, nz), (u, v) in zip(pos, nrm, local):
            mesh.positions.append((x, z, -y))
            mesh.normals.append((nx, nz, -ny))
            px = ch.px[0] + (u - ch.lo[0]) * ch.ppi
            py = ch.px[1] + ch.px[3] - (v - ch.lo[1]) * ch.ppi
            uvs.append((px, py))
            mesh.uvs.append((px / size, 1.0 - py / size))
        mesh.triangles.append(Triangle(material=ch.material, position=(base, base + 1, base + 2),
                                       normal=(base, base + 1, base + 2), uv=(base, base + 1, base + 2)))
        out_tris.append((pi, key, fl, pos, nrm, uvs))
    return Model(mesh, chart_list, out_tris, P, sizes)


HEIGHT = 90.9  # measured by tests/test_realistic_props.py against model()


def atm_mesh() -> Mesh:
    """The mesh (a fresh copy each call: the pipeline rewrites positions)."""
    m = model().mesh
    return Mesh(positions=list(m.positions), normals=list(m.normals), uvs=list(m.uvs),
                triangles=list(m.triangles), source=m.source)


# --------------------------------------------------------------------------
# Baking: rasterise every triangle into its atlas, interpolating world
# position and normal, then paint from those.


def _bake(material: str):
    m = model()
    size = m.sizes[material]
    pos = np.zeros((size, size, 3), np.float32)
    nrm = np.zeros((size, size, 3), np.float32)
    kind = np.zeros((size, size), np.int16)
    edge = np.zeros((size, size), np.float32)
    dirt = np.zeros((size, size), np.float32)
    piece_id = np.full((size, size), -1, np.int32)
    chart_id = np.full((size, size), -1, np.int32)
    keys = {c.key: i for i, c in enumerate(m.charts)}
    for pi, key, fl, P3, N3, uv in m.tris:
        if m.charts[keys[key]].material != material:
            continue
        piece = m.pieces[pi]
        (x0, y0), (x1, y1), (x2, y2) = uv
        minx, maxx = int(math.floor(min(x0, x1, x2))) - 1, int(math.ceil(max(x0, x1, x2))) + 1
        miny, maxy = int(math.floor(min(y0, y1, y2))) - 1, int(math.ceil(max(y0, y1, y2))) + 1
        minx, miny = max(minx, 0), max(miny, 0)
        maxx, maxy = min(maxx, size - 1), min(maxy, size - 1)
        if maxx < minx or maxy < miny:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-9:
            continue
        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
        l2 = 1 - l0 - l1
        eps = -0.02
        inside = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
        if not inside.any():
            continue
        yy, xx = np.nonzero(inside)
        yy, xx = yy + miny, xx + minx
        L = np.stack([l0[inside], l1[inside], l2[inside]], 1)
        pos[yy, xx] = L @ np.array(P3, np.float32)
        nn = L @ np.array(N3, np.float32)
        nrm[yy, xx] = nn / np.linalg.norm(nn, axis=1, keepdims=True)
        kind[yy, xx] = piece.kind
        edge[yy, xx] = 0.0 if fl else 1.0
        dirt[yy, xx] = piece.dirt
        piece_id[yy, xx] = pi
        chart_id[yy, xx] = keys[key]
    return m, size, pos, nrm, kind, edge, dirt, piece_id, chart_id


def _dilate(image: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Fill empty texels from the nearest filled one (no mip bleed at seams)."""
    from scipy import ndimage

    _, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)
    return image[iy, ix]


def _photo(slug: str, member: str, gray: bool = False) -> np.ndarray:
    from pathlib import Path

    from .fetch import extract_texture_member

    path = extract_texture_member(slug, member, Path("/tmp/zmforge-atm-textures"))
    from PIL import Image

    with Image.open(path) as im:
        a = np.asarray(im.convert("L" if gray else "RGB").resize((1024, 1024)), np.float32) / 255.0
    return a


def _tri(photo: np.ndarray, pos: np.ndarray, nrm: np.ndarray, inches: float) -> np.ndarray:
    """Sample a tiling photo by world position on the texel's dominant plane."""
    ax = np.argmax(np.abs(nrm), axis=-1)
    u = np.where(ax == 0, pos[..., 1], pos[..., 0])
    v = np.where(ax == 2, pos[..., 1], pos[..., 2])
    n = photo.shape[0]
    iu = (np.floor(u / inches * n).astype(np.int64)) % n
    iv = (np.floor(-v / inches * n).astype(np.int64)) % n
    return photo[iv, iu]


def _noise(shape, scale: float, seed: int) -> np.ndarray:
    from scipy import ndimage

    rng = np.random.default_rng(seed)
    small = rng.random((max(2, int(shape[0] / scale)), max(2, int(shape[1] / scale))))
    return np.clip(ndimage.zoom(small, (shape[0] / small.shape[0], shape[1] / small.shape[1]),
                                order=3)[: shape[0], : shape[1]], 0, 1)


_FILLED: list = []  # the texel mask noise is evaluated on (set by the painter)


def _world_noise(pos: np.ndarray, inches: float, seed: int) -> np.ndarray:
    """Smooth value noise of world position (continuous across charts).
    Evaluated only on the painter's filled texels when the shape matches."""
    mask = next((f for f in _FILLED if f.shape == pos.shape[:-1]), None)
    pts = pos[mask] if mask is not None else pos.reshape(-1, 3)
    table = np.random.default_rng(seed).random(64 ** 3).astype(np.float32)
    g = pts / np.float32(inches)
    fl = np.floor(g)
    f = g - fl
    f = f * f * (3 - 2 * f)
    i = fl.astype(np.int32) & 63
    j = (i + 1) & 63
    out = np.zeros(len(pts), np.float32)
    for dx in (0, 1):
        ix = (j if dx else i)[:, 0]
        wx = f[:, 0] if dx else 1 - f[:, 0]
        for dy in (0, 1):
            iy = (j if dy else i)[:, 1]
            wy = wx * (f[:, 1] if dy else 1 - f[:, 1])
            for dz in (0, 1):
                iz = (j if dz else i)[:, 2]
                w = wy * (f[:, 2] if dz else 1 - f[:, 2])
                out += w * np.take(table, ix + 64 * (iy + 64 * iz))
    if mask is None:
        return out.reshape(pos.shape[:-1])
    full = np.zeros(pos.shape[:-1], np.float32)
    full[mask] = out
    return full


def _fbm(pos: np.ndarray, inches: float, seed: int, octaves: int = 4) -> np.ndarray:
    out = np.zeros(pos.shape[:-1], np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        out += amp * _world_noise(pos, inches / 2 ** o, seed + o)
        total += amp
        amp *= 0.5
    return out / total


def _font(size: int, face: str = "impact"):
    from pathlib import Path

    from PIL import ImageFont

    anton = Path(__file__).resolve().parents[3] / "assets-cache" / "fonts" / "anton" / "Anton-Regular.ttf"
    if face == "impact" and anton.is_file():
        return ImageFont.truetype(str(anton), size)
    from ..texture.paint import font

    return font({"impact": "sign_narrow", "mono": "typewriter", "hand": "script"}.get(face, face), size)


def _bolt_list(m: Model):
    """(centre, axis unit, radius) for every bolt head on a painted surface."""
    out = []
    for p in m.pieces:
        if p.share.startswith("bolt") and not p.share.endswith("w"):
            out.append(p.anchor)
    return out


@lru_cache(maxsize=1)
def paint_body(size: int = 2048):
    """The body's colour map and normal map, both ``size`` square (RGB images)."""
    from PIL import Image, ImageDraw
    from scipy import ndimage

    m, n, pos, nrm, kind, edge, dirt, piece_id, chart_id = _bake("body")
    filled = kind > 0
    _FILLED[:] = [filled, filled[::2, ::2]]
    H = np.zeros((n, n), np.float32)  # height in inches, for the normal map
    ppi = np.zeros((n, n), np.float32)
    for i, c in enumerate(m.charts):
        ppi[chart_id == i] = c.ppi
    ppi[~filled] = BODY_PPI

    paint_src = _photo("ambientcg_painted_metal_004", "PaintedMetal004_1K-JPG_Color.jpg")
    rust_src = _photo("ambientcg_rust_004", "Rust004_1K-JPG_Color.jpg")
    steel_src = _photo("ambientcg_metal_032", "Metal032_1K-JPG_Color.jpg")
    tread_src = _photo("ambientcg_diamond_plate_008a", "DiamondPlate008A_1K-JPG_Color.jpg")
    tread_h = _photo("ambientcg_diamond_plate_008a", "DiamondPlate008A_1K-JPG_Displacement.jpg", gray=True)

    # Scratches in the paint photo: its grey/white marks on the red.
    pp = _tri(paint_src, pos, nrm, 44.0)
    sat = pp.max(-1) - pp.min(-1)
    scratch = np.clip((0.55 - sat) * 3.0, 0, 1) * np.clip(pp.mean(-1) * 2 - 0.4, 0, 1)
    scratch_lo = ndimage.gaussian_filter(scratch, 3.0)
    grain = _tri(steel_src, pos, nrm, 20.0).mean(-1)
    grain = (grain - grain.mean()) * 2.0

    # Edge wear: chamfer texels, spread a little onto the faces, broken up by noise.
    e = np.clip(ndimage.gaussian_filter(edge, 1.5) * 1.6, 0, 1)
    wobble = _fbm(pos, 1.3, 11, 3)
    # Paint survives on most of each chamfer: chips only where the noise is high.
    chip = np.clip((e * 0.9 - 0.62 + (wobble - 0.5) * 1.8) * 4.0, 0, 1)
    z = pos[..., 2]
    # Grime: rises from the floor, sits in recesses, streaks down the faces.
    streak_n = _world_noise(pos * np.array([1.0, 1.0, 0.08], np.float32), 1.2, 5)
    grime = np.clip(1.0 - z / 14.0, 0, 1) ** 1.5 * 0.8 + dirt * 0.6
    grime += np.clip(streak_n - 0.66, 0, 1) * 0.9 * (nrm[..., 2] < 0.5)
    grime = np.clip(grime + (_fbm(pos, 10.0, 21) - 0.5) * 0.5, 0, 1)

    # Rust: in chips, round bolts and in streaks running down from them.
    rust = chip * np.clip(_fbm(pos, 2.0, 31, 2) * 1.8 - 0.75, 0, 1)
    rust += np.clip(_fbm(pos, 7.0, 41) - 0.62, 0, 1) * 2.0 * np.clip(1 - z / 30.0, 0, 1)
    # Streaks from the bolts, at half resolution (60 bolts over the atlas).
    hp, hn = pos[::2, ::2], nrm[::2, ::2]
    wav = _world_noise(hp * np.array([1, 1, 0.2], np.float32), 0.25, 7)
    side = np.abs(hn[..., 0]) > 0.7
    upright = np.abs(hn[..., 2]) < 0.6
    streaks = np.zeros(hp.shape[:2], np.float32)
    for b in _bolt_list(m):
        dz = b[2] - hp[..., 2]
        near = upright & (dz > -1.5) & (dz < 22.0)
        if not near.any():
            continue
        horiz = np.where(side, np.abs(hp[..., 1] - b[1]), np.abs(hp[..., 0] - b[0]))
        plane = np.where(side, np.abs(hp[..., 0] - b[0]), np.abs(hp[..., 1] - b[1]))
        on = near & (plane < 0.35)
        width = 0.3 + np.clip(dz, 0, None) * 0.045
        st = on * np.exp(-np.clip(dz, 0, None) / 7.0) * np.clip(1.0 - horiz / width - (wav - 0.5) * 0.8, 0, 1)
        ring = on * np.clip(1.0 - np.hypot(horiz, np.abs(dz)) / 1.1, 0, 1)
        streaks = np.maximum(streaks, st * 0.9 + ring * 0.7)
    rust += ndimage.zoom(streaks, 2, order=1)[:n, :n]
    rust = np.clip(rust, 0, 1)

    col = np.zeros((n, n, 3), np.float32)

    def blend(mask, rgb):
        nonlocal col
        col = col * (1 - mask[..., None]) + rgb * mask[..., None]

    paint_rgb = np.array([0.15, 0.158, 0.155], np.float32)
    accent_rgb = np.array([0.30, 0.055, 0.045], np.float32)
    bare = _tri(steel_src, pos, nrm, 14.0) * np.array([0.95, 0.95, 0.97]) * 0.9
    rust_rgb = _tri(rust_src, pos, nrm, 18.0) * 1.15
    photo_l = pp.mean(-1, keepdims=True)
    for k, base in ((PAINT, paint_rgb), (ACCENT, accent_rgb)):
        sel = kind == k
        tone = base * (0.85 + 0.3 * (_fbm(pos, 16.0, 3)[..., None]))
        c = tone * (0.95 + 0.1 * photo_l)
        # Only thin scratches: a high-pass of the photo's marks (its big
        # paint-loss patches read as camouflage blotches at a distance).
        fine = np.clip((scratch - scratch_lo) * 3.0, 0, 1)
        c = c * (1 - fine[..., None] * 0.45) + bare * fine[..., None] * 0.45
        c = c * (1 - chip[..., None]) + bare * 0.7 * chip[..., None]
        col[sel] = c[sel]
    # Metals.
    steel_rgb = bare * (1.0 + 0.1 * grain[..., None])
    for k, mul in ((STEEL, 0.72), (DARK, 0.36), (GALV, 0.62)):
        sel = kind == k
        c = steel_rgb * mul
        if k == DARK:
            c = c * (1 - chip[..., None] * 0.0) + bare * chip[..., None] * 0.6
        if k == GALV:
            c = c * np.array([0.95, 0.98, 1.0]) * (0.8 + 0.4 * _fbm(pos, 1.5, 51)[..., None])
        col[sel] = c[sel]
    sel = kind == TREAD
    col[sel] = (_tri(tread_src, pos, nrm, 12.0) * 0.55)[sel]
    col[kind == BLACK] = np.array([0.02, 0.02, 0.022])
    col[kind == SMOKE] = np.array([0.03, 0.035, 0.04])
    # Keys: brushed steel caps; the three function keys coloured plastic.
    for k, rgb in ((KEY, None), (KEY_RED, (0.55, 0.06, 0.05)), (KEY_YEL, (0.72, 0.56, 0.07)),
                   (KEY_GRN, (0.07, 0.42, 0.14))):
        sel = kind == k
        c = np.clip(steel_rgb * 1.25, 0, 1) if rgb is None else np.broadcast_to(np.array(rgb, np.float32), col.shape)
        col[sel] = c[sel]
    col[kind == PAPER] = np.array([0.86, 0.84, 0.76])

    # Wear layers over everything but paper and glass-like parts.
    worn = filled & (kind != PAPER) & (kind != SMOKE) & (kind != BLACK)
    rust_c = rust_rgb * (0.8 + 0.4 * _fbm(pos, 1.0, 61)[..., None])
    rmask = (rust * worn * np.isin(kind, (PAINT, ACCENT, DARK, GALV, TREAD, STEEL))).astype(np.float32)
    rmask *= np.where(np.isin(kind, (STEEL, GALV)), 0.45, 1.0)
    blend(rmask, rust_c)
    gmask = grime * worn * 0.55
    blend(gmask.astype(np.float32), np.array([0.05, 0.045, 0.035], np.float32))

    # Heights: chips sit below the paint, rust is rough, the tread is raised.
    H += np.where(np.isin(kind, (PAINT, ACCENT)), -(chip + scratch * 0.4) * 0.02, 0)
    H += rust * (_fbm(pos, 0.4, 71) - 0.5) * 0.05
    sel = kind == TREAD
    H[sel] += (_tri(tread_h[..., None], pos, nrm, 12.0)[..., 0] * 0.09)[sel]

    # Panel seams, labels and other painted detail, drawn per chart.
    img = Image.fromarray(np.clip(col * 255, 0, 255).astype(np.uint8), "RGB")
    hmask = Image.new("L", (n, n), 0)  # 255 = seam groove
    draw, hdraw = ImageDraw.Draw(img), ImageDraw.Draw(hmask)

    def rect_px(c: Chart, u0, v0, u1, v1):
        x0 = c.px[0] + (u0 - c.lo[0]) * c.ppi
        x1 = c.px[0] + (u1 - c.lo[0]) * c.ppi
        y0 = c.px[1] + c.px[3] - (v1 - c.lo[1]) * c.ppi
        y1 = c.px[1] + c.px[3] - (v0 - c.lo[1]) * c.ppi
        return x0, y0, x1, y1

    def chart(name, axis):
        for c in m.charts:
            if c.key == (name, axis):
                return c
        return None

    # Side panels of the safe and the upper body: a groove inset from the edges.
    for name, inset in (("safe", 2.6), ("upper", 2.6)):
        for axis in ("x", "-x", "y"):
            c = chart(name, axis)
            if c is None:
                continue
            x0, y0, x1, y1 = rect_px(c, c.lo[0] + inset, c.lo[1] + inset, c.hi[0] - inset, c.hi[1] - inset)
            w = max(2, round(0.12 * c.ppi))
            hdraw.rectangle((x0, y0, x1, y1), outline=255, width=w)
            draw.rectangle((x0, y0, x1, y1), outline=(18, 18, 17), width=max(1, w // 2))
    # The safe's back: a vented service panel.
    c = chart("upper", "y")
    if c is not None:
        for i in range(10):
            vz = 60.0 + i * 1.1
            x0, y0, x1, y1 = rect_px(c, -10.0, vz, 10.0, vz + 0.45)
            hdraw.rectangle((x0, y0, x1, y1), fill=255)
            draw.rectangle((x0, y0, x1, y1), fill=(10, 10, 10))
    # Fascia print: labels under the card reader and receipt slot, a brand plate.
    c = chart("upper", "-y")
    if c is not None:
        def text_at(u, v, txt, h_in, fill, face="sign"):
            f = _font(max(8, round(h_in * c.ppi)), face)
            x0, y0, _, _ = rect_px(c, u, v, u, v)
            bb = draw.textbbox((0, 0), txt, font=f)
            draw.text((x0 - (bb[2] - bb[0]) / 2, y0 - (bb[3] - bb[1]) / 2 - bb[1]), txt, font=f, fill=fill)
        text_at(14.8, 63.4, "INSERT CARD", 0.55, (205, 196, 170))
        text_at(14.8, 50.7, "RECEIPT", 0.5, (205, 196, 170))
        # Card logos: three plain coloured tabs.
        for i, rgb in enumerate(((150, 32, 28), (190, 140, 30), (40, 80, 150))):
            x0, y0, x1, y1 = rect_px(c, 12.4 + i * 1.8, 64.4, 13.9 + i * 1.8, 65.4)
            draw.rounded_rectangle((x0, y0, x1, y1), radius=4, fill=rgb)
        # Brand plate below the hood: engraved steel.
        x0, y0, x1, y1 = rect_px(c, -7.5, 45.4, 7.5, 48.8)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=6, fill=(120, 116, 104), outline=(40, 38, 34), width=3)
        hdraw.rounded_rectangle((x0, y0, x1, y1), radius=6, outline=255, width=3)
        text_at(0.0, 47.1, "LUCKY 4 SAVINGS & LOAN", 0.9, (36, 30, 24), "sign_narrow")
    # The safe door: a stencil and a warning placard.
    c = chart("door", "-y")
    if c is not None:
        f = _font(round(1.6 * c.ppi), "stencil")
        x0, y0, x1, y1 = rect_px(c, -12.0, 13.0, 12.0, 15.0)
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), "NO REFUNDS", font=f, fill=(150, 140, 110), anchor="mm")
        x0, y0, x1, y1 = rect_px(c, -12.5, 18.5, -4.5, 24.5)
        draw.rectangle((x0, y0, x1, y1), fill=(196, 160, 40), outline=(20, 20, 20), width=4)
        f2 = _font(round(0.95 * c.ppi), "sign")
        draw.text(((x0 + x1) / 2, y0 + (y1 - y0) * 0.32), "WARNING", font=f2, fill=(20, 20, 20), anchor="mm")
        f3 = _font(round(0.55 * c.ppi), "sign")
        draw.text(((x0 + x1) / 2, y0 + (y1 - y0) * 0.68), "HOUSE ALWAYS WINS", font=f3, fill=(20, 20, 20),
                  anchor="mm")
    # Deck: "PRESS ENTER" arrow and a worn stripe along the front.
    c = chart("deck", "deck")
    if c is not None:
        f = _font(round(0.55 * c.ppi), "sign")
        x0, y0, x1, y1 = rect_px(c, 7.0, -3.0, 16.0, -1.0)
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), "KEEP YOUR PIN SECRET", font=f, fill=(190, 170, 140), anchor="mm")
    # Keys: their labels.
    for p in m.pieces:
        if not p.name.startswith("key_"):
            continue
        c = chart(p.name, "deck")
        if c is None or not p.label.strip():
            continue
        cx, cy = c.px[0] + c.px[2] / 2, c.px[1] + c.px[3] / 2
        big = len(p.label) == 1
        f = _font(round((0.78 if big else 0.30) * c.ppi), "sign")
        ink = (10, 10, 10) if p.kind == KEY else (245, 240, 230)
        draw.text((cx, cy), p.label, font=f, fill=ink, anchor="mm",
                  stroke_width=max(1, round(0.03 * c.ppi)), stroke_fill=ink)
    # Lock: a keyhole.
    c = chart("lock", "-y")
    if c is not None:
        cx, cy = c.px[0] + c.px[2] / 2, c.px[1] + c.px[3] / 2
        r = 0.18 * c.ppi
        draw.ellipse((cx - r, cy - r * 1.6, cx + r, cy + r * 0.4), fill=(8, 8, 8))
        draw.polygon([(cx - r * 0.5, cy), (cx + r * 0.5, cy), (cx + r * 0.9, cy + r * 2.2),
                      (cx - r * 0.9, cy + r * 2.2)], fill=(8, 8, 8))
    # The note.
    c = chart("note", "-y")
    if c is not None:
        x0, y0, w, h = c.px
        note = Image.new("RGB", (w, h), (226, 221, 200))
        nd = ImageDraw.Draw(note)
        for i in range(1, 12):
            yy = h * (0.18 + i * 0.066)
            nd.line((w * 0.06, yy, w * 0.94, yy), fill=(170, 190, 210), width=2)
        f = _font(round(h * 0.16), "impact")
        nd.text((w / 2, h * 0.28), "OUT OF", font=f, fill=(28, 26, 70), anchor="mm")
        nd.text((w / 2, h * 0.47), "ORDER?", font=f, fill=(28, 26, 70), anchor="mm")
        f2 = _font(round(h * 0.075), "mono")
        nd.text((w / 2, h * 0.66), "it still takes", font=f2, fill=(40, 40, 60), anchor="mm")
        nd.text((w / 2, h * 0.75), "your points", font=f2, fill=(40, 40, 60), anchor="mm")
        nd.text((w * 0.7, h * 0.88), "- mgmt", font=f2, fill=(120, 30, 30), anchor="mm")
        arr = np.asarray(note, np.float32)
        stain = _noise((h, w), 30, 5)[..., None]
        arr *= 0.82 + 0.25 * stain
        arr[: int(h * 0.1), int(w * 0.3): int(w * 0.7)] = arr[: int(h * 0.1), int(w * 0.3): int(w * 0.7)] * 0.7 + np.array([200, 196, 170]) * 0.3
        note = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        img.paste(note, (x0, y0))
        # Tape strips across the top corners.
        td = ImageDraw.Draw(img, "RGBA")
        for sx in (0.12, 0.88):
            cxp, cyp = x0 + w * sx, y0 + h * 0.03
            tw, th = w * 0.22, h * 0.05
            ang = math.radians(35 if sx < 0.5 else -35)
            pts = [(cxp + dx * math.cos(ang) - dy * math.sin(ang), cyp + dx * math.sin(ang) + dy * math.cos(ang))
                   for dx, dy in ((-tw, -th), (tw, -th), (tw, th), (-tw, th))]
            td.polygon(pts, fill=(222, 214, 170, 190))

    col = np.asarray(img, np.float32) / 255.0
    groove = np.asarray(hmask, np.float32) / 255.0
    H -= ndimage.gaussian_filter(groove, 0.7) * 0.06
    col = _dilate(col, filled)
    Hd = _dilate(H, filled)
    ppi_d = _dilate(ppi, filled)
    # Normals from heights, per texel density (height and slope in inches).
    gy, gx = np.gradient(Hd)
    dhdu = gx * ppi_d
    dhdv = -gy * ppi_d
    nmap = np.dstack([-dhdu, -dhdv, np.ones_like(Hd)])
    nmap /= np.linalg.norm(nmap, axis=2, keepdims=True)
    colour = Image.fromarray(np.clip(col * 255, 0, 255).round().astype(np.uint8), "RGB")
    normal = Image.fromarray(((nmap * 0.5 + 0.5) * 255).round().astype(np.uint8), "RGB")
    if size != n:
        colour = colour.resize((size, size), Image.LANCZOS)
        normal = normal.resize((size, size), Image.LANCZOS)
    return colour, normal


@lru_cache(maxsize=1)
def paint_glow(size: int = 1024):
    """The screen, topper face and card-reader light (the emissive map)."""
    from PIL import Image, ImageDraw, ImageFilter

    m = model()
    n = m.sizes["glow"]
    img = Image.new("RGB", (n, n), (0, 0, 0))

    def chart(name):
        return next(c for c in m.charts if c.key[0] == name)

    # Screen: a deep blue ATM screen with a gold-and-white UI.
    c = chart("screen")
    x0, y0, w, h = c.px
    scr = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    scr[...] = (np.array([0.02, 0.10, 0.24]) * (1 - yy[..., None]) + np.array([0.01, 0.04, 0.12]) * yy[..., None])
    s = Image.fromarray((scr * 255).astype(np.uint8))
    d = ImageDraw.Draw(s)
    d.rectangle((0, 0, w, h * 0.17), fill=(170, 26, 22))
    d.text((w / 2, h * 0.085), "LUCKY 4  CASH POINT", font=_font(round(h * 0.11), "impact"), fill=(255, 226, 120),
           anchor="mm")
    d.text((w / 2, h * 0.30), "INSERT", font=_font(round(h * 0.085), "sign"), fill=(200, 215, 240), anchor="mm")
    d.text((w / 2, h * 0.43), "2,000", font=_font(round(h * 0.15), "impact"), fill=(255, 255, 255), anchor="mm")
    d.text((w / 2, h * 0.585), "1 IN 4 CHANCE TO", font=_font(round(h * 0.07), "sign"), fill=(200, 215, 240),
           anchor="mm")
    d.text((w / 2, h * 0.73), "WIN 10,000", font=_font(round(h * 0.17), "impact"), fill=(255, 208, 60), anchor="mm")
    # Soft-key prompts at the sides.
    fk = _font(round(h * 0.05), "sign")
    d.text((w * 0.03, h * 0.90), "< PLAY", font=fk, fill=(255, 255, 255), anchor="lm")
    d.text((w * 0.97, h * 0.90), "WALK AWAY >", font=fk, fill=(160, 170, 190), anchor="rm")
    arr = np.asarray(s, np.float32) / 255.0
    arr *= (0.93 + 0.07 * np.sin(np.arange(h) * math.pi / 2.0))[:, None, None]  # scanlines
    vign = 1 - 0.35 * (((xx - 0.5) * 1.8) ** 2 + ((yy - 0.5) * 1.8) ** 2)
    arr *= vign[..., None]
    # A glass reflection streak.
    streak = np.clip(1 - np.abs((xx * 0.9 + yy * 0.6) - 0.55) / 0.08, 0, 1) * 0.10
    arr = arr + streak[..., None]
    img.paste(Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8)), (x0, y0))

    # Topper: red letters on black, a bulb border with a couple dead.
    c = chart("sign")
    x0, y0, w, h = c.px
    t = Image.new("RGB", (w, h), (12, 4, 4))
    d = ImageDraw.Draw(t)
    rng = np.random.default_rng(4)
    bulbs = []
    step = h * 0.13
    for i in range(int(w / step) + 1):
        bulbs += [(i * step + step / 2, h * 0.08), (i * step + step / 2, h * 0.92)]
    for j in range(1, int(h / step) - 1):
        bulbs += [(w * 0.02, j * step + step * 0.5), (w * 0.98, j * step + step * 0.5)]
    dead = set(rng.choice(len(bulbs), 4, replace=False).tolist())
    for i, (bx, by) in enumerate(bulbs):
        r = h * 0.035
        fill = (60, 40, 30) if i in dead else (255, 214, 120)
        d.ellipse((bx - r, by - r, bx + r, by + r), fill=fill)
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    f = _font(round(h * 0.62), "impact")
    gd.text((w / 2, h * 0.46), "LUCKY 4", font=f, fill=(255, 40, 30), anchor="mm")
    halo = glow.filter(ImageFilter.GaussianBlur(h * 0.05))
    t = Image.fromarray(np.clip(np.asarray(t, np.float32) + np.asarray(halo, np.float32) * 0.9, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(t)
    d.text((w / 2, h * 0.46), "LUCKY 4", font=f, fill=(255, 120, 90), anchor="mm")
    d.text((w / 2, h * 0.80), "ONE IN FOUR WINS", font=_font(round(h * 0.12), "sign"), fill=(255, 220, 160),
           anchor="mm")
    img.paste(t, (x0, y0))

    # Card reader mouth: a green light.
    c = chart("card_led")
    x0, y0, w, h = c.px
    img.paste(Image.new("RGB", (w, h), (60, 255, 110)), (x0, y0))

    arr = np.asarray(img, np.float32)
    filled = arr.sum(-1) > 0
    for c in m.charts:
        if c.material == "glow":
            x0, y0, w, h = c.px
            filled[y0:y0 + h, x0:x0 + w] = True
    arr = _dilate(arr, filled)
    out = Image.fromarray(arr.astype(np.uint8), "RGB")
    if size != n:
        out = out.resize((size, size), Image.LANCZOS)
    return out, None
