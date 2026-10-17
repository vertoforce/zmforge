"""Turn a parsed mesh into the mod tools' own ``.XMODEL_EXPORT`` text.

The format is the text one Treyarch's exporters write and the asset converter
reads.  Every rule below is taken from a real BO3-era export
(``marinesciencedude/Black-Ops-Trilogy-Weapon-Packs``,
``model_export/wallbuy/wb_m16_chalk_LOD0.xmodel_export``, ``VERSION 7``), not
from a tutorial:

* ``VERSION 7`` numbers are space separated.  (Version 6 used commas; do not
  mix the two.)
* One bone, ``TAG_ORIGIN``, at the origin with an identity basis.  A static
  prop needs no skeleton, but the block is not optional.
* ``NUMVERTS`` is a flat list of positions.  Normals, vertex colours and UVs
  hang off the *face corners*, not the vertices, so one position may carry as
  many normals as it has faces.
* ``TRI <object> <material> 0 0`` then three ``VERT``/``NORMAL``/``COLOR``/
  ``UV 1 u v`` corners; the corner ``COLOR`` is white (it tints the texture).
* ``MATERIAL <n> "<asset name>" "Lambert" "color_map:<file>.tif"`` -- the
  first field is the name the game resolves against the asset database, so it
  must be the custom material's asset name.

Two conversions happen on the way in:

**Axes.**  The kits export Y-up right-handed; Radiant is Z-up.  We map
``(x, y, z) -> (x, -z, y)``, whose determinant is +1, so the axis change
itself preserves winding.  The engine's winding is the reverse of Wavefront's,
so the writer emits each triangle's corners in :data:`EXPORT_CORNER_ORDER`.

**Units.**  A BO3 unit is an inch and the kits work in arbitrary "blocks", so
scale is driven by the size the prop should *be* in the map rather than by a
conversion factor: :func:`to_game_space` scales uniformly until the model's
**longest** axis matches ``size_units``, centres it on X and Y and drops its
lowest point to z = 0, so the placement origin is the spot on the floor the
prop stands on.  Longest, not tallest: a donut is wide and thin, and fitting
its height to 6 in would make it a five-foot donut.

``UV`` v runs *down* in this format: in the reference export the corners at
the low end of the quad carry ``v 1.0`` and the high end ``v 0.0``, the
opposite of Wavefront's convention, so v is flipped on the way in.  Pass
``flip_v=False`` if a prop's texture ever comes out mirrored top to bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .wavefront import Mesh, Triangle, Vec2, Vec3

__all__ = [
    "to_game_space",
    "decimate",
    "xmodel_export_text",
    "MaterialBinding",
]


@dataclass(frozen=True, slots=True)
class MaterialBinding:
    """One ``.obj`` material name mapped onto a game material asset."""

    obj_material: str
    asset: str  # the BO3 material asset name, as the GDT spells it
    color_map: str  # the source image file name the MATERIAL line records
    #: When set, every corner of every triangle of this material gets this one
    #: UV instead of the file's own -- how a flat colour swatch is applied to a
    #: mesh that ships no texture.
    flat_uv: Vec2 | None = None


def to_game_space(mesh: Mesh, size_units: float, up: str = "y") -> tuple[Mesh, float]:
    """Y-up blocks in, Z-up game units out.  Returns the mesh and the scale used.

    ``size_units`` is the length the model's longest axis should end up with.
    The mesh is centred on X and Y and sits on z = 0.
    """
    if up not in ("y", "z"):
        raise ValueError("up must be 'y' or 'z'")
    if size_units <= 0:
        raise ValueError("size_units must be positive")

    def rot(v: Vec3) -> Vec3:
        return (v[0], -v[2], v[1]) if up == "y" else v

    turned = [rot(p) for p in mesh.positions]
    used = {i for tri in mesh.triangles for i in tri.position}
    zs = [turned[i][2] for i in used]
    xs = [turned[i][0] for i in used]
    ys = [turned[i][1] for i in used]
    longest = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    if longest <= 0:
        raise ValueError("model has no extent")
    scale = size_units / longest
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    floor = min(zs)

    positions = [
        ((p[0] - cx) * scale, (p[1] - cy) * scale, (p[2] - floor) * scale) for p in turned
    ]
    normals = [_unit(rot(n)) for n in mesh.normals]
    out = replace(mesh, positions=positions, normals=normals)
    return out, scale


def _unit(v: Vec3) -> Vec3:
    length = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    if length == 0:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def decimate(mesh: Mesh, max_triangles: int, min_cells: int = 6) -> tuple[Mesh, str]:
    """Collapse vertices onto a grid until the mesh fits ``max_triangles``.

    Vertex clustering: quantise every position to a cell, keep one vertex per
    cell, drop the triangles whose corners collapsed together.  Crude next to a
    quadric collapse and entirely deterministic, which is what matters for a
    background prop -- the same input always yields the same prop, and the
    report says what it cost.

    Returns the mesh and a one-line account of what happened.
    """
    before = len(mesh.triangles)
    if before <= max_triangles:
        return mesh, f"{before} tris, under the {max_triangles} budget, left alone"

    lo, hi = mesh.bounds()
    span = max(hi[i] - lo[i] for i in range(3)) or 1.0
    cells = 128
    best = mesh
    while cells >= min_cells:
        candidate = _cluster(mesh, lo, span / cells)
        best = candidate
        if len(candidate.triangles) <= max_triangles:
            return candidate, (
                f"{before} -> {len(candidate.triangles)} tris by vertex clustering "
                f"on a {cells}-cell grid ({span / cells:.4g} units per cell)"
            )
        cells //= 2
    return best, (
        f"{before} -> {len(best.triangles)} tris by vertex clustering, still over "
        f"the {max_triangles} budget at the coarsest grid tried"
    )


def _cluster(mesh: Mesh, lo: Vec3, cell: float) -> Mesh:
    keep: dict[tuple[int, int, int], int] = {}
    remap: list[int] = []
    positions: list[Vec3] = []
    for p in mesh.positions:
        key = tuple(int((p[i] - lo[i]) // cell) for i in range(3))
        index = keep.get(key)  # type: ignore[arg-type]
        if index is None:
            index = len(positions)
            keep[key] = index  # type: ignore[index]
            positions.append(p)
        remap.append(index)

    triangles: list[Triangle] = []
    for tri in mesh.triangles:
        a, b, c = (remap[i] for i in tri.position)
        if a == b or b == c or a == c:
            continue
        triangles.append(replace(tri, position=(a, b, c)))

    # Collapsing can leave a kept vertex with no triangle on it.  NUMVERTS is a
    # declared count the converter reads, so ship only vertices the faces use.
    used = sorted({i for tri in triangles for i in tri.position})
    renumber = {old: new for new, old in enumerate(used)}
    return replace(
        mesh,
        positions=[positions[i] for i in used],
        triangles=[
            replace(tri, position=tuple(renumber[i] for i in tri.position))  # type: ignore[arg-type]
            for tri in triangles
        ],
    )


def _n(value: float) -> str:
    return f"{value:.6f}"


#: The order a triangle's corners are written in.  Wavefront faces are
#: counter-clockwise seen from outside; the engine's are the other way round.
#: Measured on converted meshes in ``share/assetconvert/xmesh``:
#: for the stock ``p7_crate_wood_01``, ``p7_barrel_metal_55gal`` and
#: ``p7_sandbag_02`` the counter-clockwise face normal points against the
#: vertex normals on 0/384, 1/1628 and 0/254 triangles, while every kit prop
#: written in .obj order (pumpkin, tractor, donut, teddy bear) agreed on all of
#: them -- and those rendered inside out in game.  Writing corners 0, 2, 1
#: reverses the winding and leaves each corner's normal and UV with it.
EXPORT_CORNER_ORDER = (0, 2, 1)


def xmodel_export_text(
    mesh: Mesh,
    object_name: str,
    bindings: list[MaterialBinding],
    *,
    flip_v: bool = True,
    stamp: str | None = None,
) -> str:
    """The whole ``.XMODEL_EXPORT`` file, LF endings, for one static prop."""
    by_obj = {b.obj_material: b for b in bindings}
    missing = [m for m in mesh.materials if m not in by_obj]
    if missing:
        raise ValueError(f"{object_name}: no game material bound for {missing}")
    # One MATERIAL block per *game* material, not per .obj material: a kit
    # whose toilet is four named materials all bound to one game material must
    # not declare that material four times over.
    used = set(mesh.materials)
    order: list[MaterialBinding] = []
    slot: dict[str, int] = {}
    for binding in bindings:
        if binding.obj_material not in used:
            continue
        for index, seen in enumerate(order):
            if seen.asset == binding.asset:
                slot[binding.obj_material] = index
                break
        else:
            slot[binding.obj_material] = len(order)
            order.append(binding)

    when = stamp or datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S %Y")
    out: list[str] = [f"// Export time: {when}", "", "MODEL", "VERSION 7", ""]
    out += ["NUMBONES 1", 'BONE 0 -1 "TAG_ORIGIN"', "", "BONE 0"]
    out += [
        f"OFFSET {_n(0)} {_n(0)} {_n(0)}",
        f"SCALE {_n(1)} {_n(1)} {_n(1)}",
        f"X {_n(1)} {_n(0)} {_n(0)}",
        f"Y {_n(0)} {_n(1)} {_n(0)}",
        f"Z {_n(0)} {_n(0)} {_n(1)}",
        "",
        "",
    ]

    out.append(f"NUMVERTS {len(mesh.positions)}")
    for index, (x, y, z) in enumerate(mesh.positions):
        out += [
            f"VERT {index}",
            f"OFFSET {_n(x)} {_n(y)} {_n(z)}",
            "BONES 1",
            f"BONE 0 {_n(1)}",
            "",
        ]

    out.append(f"NUMFACES {len(mesh.triangles)}")
    for tri in mesh.triangles:
        binding = by_obj[tri.material]
        out.append(f"TRI 0 {slot[tri.material]} 0 0")
        for corner in EXPORT_CORNER_ORDER:
            vertex = tri.position[corner]
            normal = (
                mesh.normals[tri.normal[corner]]
                if tri.normal[corner] >= 0 and tri.normal[corner] < len(mesh.normals)
                else _face_normal(mesh, tri)
            )
            if binding.flat_uv is not None:
                u, v = binding.flat_uv
            elif 0 <= tri.uv[corner] < len(mesh.uvs):
                u, v = mesh.uvs[tri.uv[corner]]
                if flip_v:
                    v = 1.0 - v
            else:
                u, v = 0.0, 0.0
            out += [
                f"VERT {vertex}",
                f"NORMAL {_n(normal[0])} {_n(normal[1])} {_n(normal[2])}",
                # Vertex colour multiplies the colour map, so it is white.
                # The reference export (a chalk wall-buy decal) has 0 0 0 1
                # here, and copying that drew every kit prop black in Radiant
                # [measured, render/propfix.py].  The game is
                # unverified; the stock renderer is assumed to multiply too.
                f"COLOR {_n(1)} {_n(1)} {_n(1)} {_n(1)}",
                f"UV 1 {_n(u)} {_n(v)}",
                "",
            ]
        out.append("")

    out += ["NUMOBJECTS 1", f'OBJECT 0 "{object_name}"', ""]
    out.append(f"NUMMATERIALS {len(order)}")
    for index, binding in enumerate(order):
        out += [
            f'MATERIAL {index} "{binding.asset}" "Lambert" "color_map:{binding.color_map}"',
            f"COLOR {_n(0)} {_n(0)} {_n(0)} {_n(1)}",
            f"TRANSPARENCY {_n(0)} {_n(0)} {_n(0)} {_n(1)}",
            f"AMBIENTCOLOR {_n(0)} {_n(0)} {_n(0)} {_n(1)}",
            f"INCANDESCENCE {_n(0)} {_n(0)} {_n(0)} {_n(1)}",
            f"COEFFS {_n(0.8)} {_n(0)}",
            f"GLOW {_n(0)} 0",
            f"REFRACTIVE 6 {_n(1)}",
            f"SPECULARCOLOR {_n(-1)} {_n(-1)} {_n(-1)} {_n(1)}",
            f"REFLECTIVECOLOR {_n(-1)} {_n(-1)} {_n(-1)} {_n(1)}",
            f"REFLECTIVE -1 {_n(1)}",
            f"BLINN {_n(-1)} {_n(-1)}",
            f"PHONG {_n(-1)}",
        ]
    return "\n".join(out) + "\n"


def _face_normal(mesh: Mesh, tri: Triangle) -> Vec3:
    a, b, c = (mesh.positions[i] for i in tri.position)
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return _unit(
        (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    )
