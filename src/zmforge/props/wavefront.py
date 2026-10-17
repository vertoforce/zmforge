"""Read a Wavefront ``.obj`` into the mesh the xmodel writer wants.

Only what a static prop needs: positions, normals, texture coordinates,
triangles and the material name each triangle belongs to.  No dependency on
numpy or a mesh library -- a prop from a free asset kit is a few hundred
triangles of plain text, and a parser that fits on one screen is easier to
trust than a wheel.

Tolerated deliberately: ``v`` lines carrying trailing vertex colours (Kenney's
kits write ``v x y z r g b``), faces of any arity (fanned into triangles),
faces with no ``vt`` or no ``vn`` (the writer substitutes), negative indices,
and ``\\r\\n``.  Rejected loudly: a face that names a vertex that does not
exist, and a file with no faces at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Mesh", "Triangle", "read_obj", "read_mtl"]

Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Triangle:
    """Three corners, each a triple of indices into the mesh's three lists.

    ``normal`` or ``uv`` may be ``-1`` when the file left them out.
    """

    material: str
    position: tuple[int, int, int]
    normal: tuple[int, int, int]
    uv: tuple[int, int, int]


@dataclass(slots=True)
class Mesh:
    """Positions, normals, UVs and triangles, in the source file's own axes."""

    positions: list[Vec3] = field(default_factory=list)
    normals: list[Vec3] = field(default_factory=list)
    uvs: list[Vec2] = field(default_factory=list)
    triangles: list[Triangle] = field(default_factory=list)
    #: ``map_Kd`` per material name, when a ``.mtl`` was read alongside.
    textures: dict[str, str] = field(default_factory=dict)
    source: str = ""

    @property
    def materials(self) -> list[str]:
        seen: dict[str, None] = {}
        for tri in self.triangles:
            seen.setdefault(tri.material, None)
        return list(seen)

    def bounds(self) -> tuple[Vec3, Vec3]:
        used = {i for tri in self.triangles for i in tri.position}
        xs = [self.positions[i][0] for i in used]
        ys = [self.positions[i][1] for i in used]
        zs = [self.positions[i][2] for i in used]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def size(self) -> Vec3:
        lo, hi = self.bounds()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    def describe(self) -> str:
        sx, sy, sz = self.size()
        return (
            f"{len(self.triangles)} tris, {len(self.positions)} verts, "
            f"{len(self.materials)} material(s), "
            f"extent {sx:.4g} x {sy:.4g} x {sz:.4g}"
        )


def _resolve(token: str, count: int) -> int:
    """One ``f`` index: 1-based, or negative counting back from the end."""
    value = int(token)
    if value > 0:
        return value - 1
    if value < 0:
        return count + value
    raise ValueError("index 0 is not a valid .obj reference")


def read_obj(path: str | Path) -> Mesh:
    """Parse ``path``, and its ``mtllib`` if one sits beside it."""
    path = Path(path)
    mesh = Mesh(source=path.name)
    material = "default"
    libs: list[str] = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        parts = rest.split()
        if head == "v":
            mesh.positions.append((float(parts[0]), float(parts[1]), float(parts[2])))
        elif head == "vn":
            mesh.normals.append((float(parts[0]), float(parts[1]), float(parts[2])))
        elif head == "vt":
            mesh.uvs.append((float(parts[0]), float(parts[1]) if len(parts) > 1 else 0.0))
        elif head == "usemtl":
            material = rest.strip() or "default"
        elif head == "mtllib":
            libs.extend(parts)
        elif head == "f":
            corners = []
            for token in parts:
                fields = (token.split("/") + ["", ""])[:3]
                pos = _resolve(fields[0], len(mesh.positions))
                uv = _resolve(fields[1], len(mesh.uvs)) if fields[1] else -1
                nrm = _resolve(fields[2], len(mesh.normals)) if fields[2] else -1
                if not 0 <= pos < len(mesh.positions):
                    raise ValueError(f"{path.name}: face names vertex {token}, which does not exist")
                corners.append((pos, nrm, uv))
            for i in range(1, len(corners) - 1):
                fan = (corners[0], corners[i], corners[i + 1])
                mesh.triangles.append(
                    Triangle(
                        material=material,
                        position=tuple(c[0] for c in fan),  # type: ignore[arg-type]
                        normal=tuple(c[1] for c in fan),  # type: ignore[arg-type]
                        uv=tuple(c[2] for c in fan),  # type: ignore[arg-type]
                    )
                )

    if not mesh.triangles:
        raise ValueError(f"{path.name}: no faces")

    for lib in libs:
        beside = path.parent / lib
        if beside.is_file():
            mesh.textures.update(read_mtl(beside))
    return mesh


def read_mtl(path: str | Path) -> dict[str, str]:
    """``newmtl`` -> its ``map_Kd`` file, for the materials that name one."""
    out: dict[str, str] = {}
    name = ""
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            name = line[7:].strip()
        elif line.startswith("map_Kd ") and name:
            out[name] = line[7:].strip()
    return out
