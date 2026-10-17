"""Quadric edge-collapse decimation for dense imported meshes (photoscans).

:func:`zmforge.props.xmodel.decimate` clusters vertices on a grid, which is
fine for a few-hundred-triangle kit prop and wrecks a 100k-triangle scan
(the grid either keeps it all or turns bark into cubes).  This uses
``fast-simplification`` (MIT, pyvista; a wrapper of Sven Forstmann's MIT
Fast-Quadric-Mesh-Simplification): CPU only, numpy only, deterministic.

UVs and normals survive: the collapses are replayed
(``return_collapses`` + ``replay_simplification``) to learn which original
vertices each output vertex stands for, and the output vertex takes the UV
of the closest point on the original triangles round them (it sits at the
quadric's optimum, not on an original vertex: on a test sheet the collapsed
vertex's own UV was off by up to 0.021, this by 0.0002).  Vertices split at
a UV seam are separate vertices, so the seam is an open border to the simplifier, which
collapses along it rather than across it.  Normals are recomputed, area
weighted, from the decimated faces.
"""

from __future__ import annotations

from dataclasses import replace

from .wavefront import Mesh, Triangle

__all__ = ["decimate_quadric"]


def decimate_quadric(mesh: Mesh, max_triangles: int) -> tuple[Mesh, str]:
    """``mesh`` cut to at most ``max_triangles`` (one material per mesh kept per face)."""
    import numpy as np

    before = len(mesh.triangles)
    if before <= max_triangles:
        return mesh, f"{before} tris, under the {max_triangles} budget, left alone"
    try:
        import fast_simplification as fs
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise RuntimeError("quadric decimation needs fast-simplification: "
                           "pip install -e '.[props]'") from exc

    # One vertex per (position, uv) corner pair, so a UV seam stays a seam.
    corner_key: dict[tuple[int, int], int] = {}
    points, uvs, faces, mats = [], [], [], []
    for tri in mesh.triangles:
        face = []
        for p, t in zip(tri.position, tri.uv):
            key = (p, t)
            index = corner_key.get(key)
            if index is None:
                index = len(points)
                corner_key[key] = index
                points.append(mesh.positions[p])
                uvs.append(mesh.uvs[t] if 0 <= t < len(mesh.uvs) else (0.0, 0.0))
            face.append(index)
        faces.append(face)
        mats.append(tri.material)
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(faces, dtype=np.int64)
    uv = np.asarray(uvs, dtype=np.float64)

    # The simplifier stops at about the target; aim a little under and retry
    # lower if it overshoots, so the budget is a real ceiling.
    target = max_triangles
    for _attempt in range(6):
        _p, _t, collapses = fs.simplify(pts, tris, target_count=target, return_collapses=True)
        out_pts, out_tris, mapping = fs.replay_simplification(pts, tris, collapses)
        if len(out_tris) <= max_triangles:
            break
        target = int(target * max_triangles / len(out_tris) * 0.98)
    else:
        raise ValueError(f"could not get {before} triangles under {max_triangles}")

    # Each output vertex stands for the original vertices collapsed into it,
    # but sits at the quadric's best spot, not on any of them.  Its UV is the
    # one the original surface has there: the closest point on the triangles
    # round those vertices, interpolated barycentrically.
    new_uv = _surface_uvs(pts, tris, uv, out_pts, mapping)

    # The material of an output face: its first corner's source faces agree
    # on every mesh we import (one material), so keep the dominant one.
    material = max(set(mats), key=mats.count)

    # The replay can keep vertices no face uses (their normal would be zero);
    # ship only the used ones, as decimate() does.
    used = np.unique(out_tris)
    renumber = np.full(len(out_pts), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    out_pts, new_uv, out_tris = out_pts[used], new_uv[used], renumber[out_tris]

    normals = np.zeros_like(out_pts)
    a, b, c = (out_pts[out_tris[:, i]] for i in range(3))
    cross = np.cross(b - a, c - a)
    for i in range(3):
        np.add.at(normals, out_tris[:, i], cross)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.where(length == 0, [[0.0, 0.0, 1.0]], normals / np.where(length == 0, 1, length))

    out = replace(
        mesh,
        positions=[tuple(p) for p in out_pts.tolist()],
        normals=[tuple(n) for n in normals.tolist()],
        uvs=[tuple(t) for t in new_uv.tolist()],
        triangles=[Triangle(material=material, position=tuple(f), normal=tuple(f),  # type: ignore[arg-type]
                            uv=tuple(f)) for f in out_tris.tolist()],  # type: ignore[arg-type]
    )
    return out, (f"{before} -> {len(out.triangles)} tris by quadric edge collapse "
                 f"(fast-simplification)")


def _closest_on_triangle(p, a, b, c):
    """Barycentric weights of the point of triangle abc closest to p."""
    import numpy as np

    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return np.array([1.0, 0, 0])
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return np.array([0, 1.0, 0])
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return np.array([1 - v, v, 0])
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return np.array([0, 0, 1.0])
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return np.array([1 - w, 0, w])
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return np.array([0, 1 - w, w])
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return np.array([1 - v - w, v, w])


def _surface_uvs(pts, tris, uv, out_pts, mapping):
    import numpy as np

    around: dict[int, list[int]] = {}
    for t, face in enumerate(tris.tolist()):
        for vertex in face:
            around.setdefault(vertex, []).append(t)
    members: dict[int, list[int]] = {}
    for original, new in enumerate(mapping.tolist()):
        if new >= 0:
            members.setdefault(new, []).append(original)
    out = np.zeros((len(out_pts), 2))
    for new, originals in members.items():
        p = out_pts[new]
        best, best_d = None, None
        for t in {t for o in originals for t in around.get(o, ())}:
            a, b, c = pts[tris[t]]
            w = _closest_on_triangle(p, a, b, c)
            d = float(np.sum((w[0] * a + w[1] * b + w[2] * c - p) ** 2))
            if best_d is None or d < best_d:
                best, best_d = w @ uv[tris[t]], d
        out[new] = best if best is not None else uv[originals[0]]
    return out
