"""Read a glTF 2.0 model (``.gltf`` + ``.bin``, or ``.glb``) into a :class:`Mesh`.

For the CC0 photoscans (Poly Haven ships glTF, not OBJ).  Only what a static
prop needs: every triangle primitive of every mesh the default scene reaches,
with its node transforms applied, positions, normals, the first UV set and
the material name.  The material's ``baseColorTexture`` file is recorded in
``Mesh.textures`` so the build can make it the prop's own colour map.

The mesh comes out in the same convention :func:`read_obj` gives: glTF is
+Y up and right-handed like the kits' OBJ files, and counter-clockwise front
faces like Wavefront, so :func:`zmforge.props.xmodel.to_game_space` treats it
the same.  Only the UV ``v`` differs: glTF runs it down the image, Wavefront
up, so it is flipped here and the writer flips it back.

Needs numpy (the ``textures`` extra).  Rejected loudly: a primitive that is
not triangles, a buffer outside the model folder, a sparse accessor.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

from .wavefront import Mesh, Triangle

__all__ = ["read_gltf"]

_COMPONENTS = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
               5125: ("I", 4), 5126: ("f", 4)}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _load(path: Path) -> tuple[dict, list[bytes]]:
    data = path.read_bytes()
    chunk_bin = b""
    if data[:4] == b"glTF":
        _magic, _version, _length = struct.unpack_from("<III", data, 0)
        at, doc = 12, None
        while at < len(data):
            size, kind = struct.unpack_from("<II", data, at)
            body = data[at + 8:at + 8 + size]
            if kind == 0x4E4F534A:
                doc = json.loads(body)
            elif kind == 0x004E4942:
                chunk_bin = body
            at += 8 + size
        if doc is None:
            raise ValueError(f"{path.name}: .glb with no JSON chunk")
    else:
        doc = json.loads(data)
    buffers = []
    for buf in doc.get("buffers", []):
        uri = buf.get("uri")
        if uri is None:
            buffers.append(chunk_bin)
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            rel = Path(uri)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"{path.name}: buffer {uri!r} is outside the model folder")
            buffers.append((path.parent / rel).read_bytes())
    return doc, buffers


def _accessor(doc: dict, buffers: list[bytes], index: int):
    import numpy as np

    acc = doc["accessors"][index]
    if "sparse" in acc:
        raise ValueError("sparse accessors are not supported")
    code, size = _COMPONENTS[acc["componentType"]]
    width = _WIDTH[acc["type"]]
    count = acc["count"]
    view = doc["bufferViews"][acc["bufferView"]]
    raw = buffers[view["buffer"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or size * width
    dtype = np.dtype(code).newbyteorder("<")
    if stride == size * width:
        arr = np.frombuffer(raw, dtype=dtype, count=count * width, offset=start)
        return arr.reshape(count, width) if width > 1 else arr
    rows = np.lib.stride_tricks.as_strided(
        np.frombuffer(raw, dtype=np.uint8, offset=start),
        shape=(count, size * width), strides=(stride, 1))
    return rows.copy().view(dtype).reshape(count, width)


def _local(node: dict):
    import numpy as np

    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    t = np.eye(4)
    t[:3, 3] = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    s = np.diag(node.get("scale", [1, 1, 1]))
    m = np.eye(4)
    m[:3, :3] = r @ s
    return t @ m


def read_gltf(path: str | Path) -> Mesh:
    """Parse ``path`` (``.gltf`` or ``.glb``) into one mesh, node transforms applied."""
    import numpy as np

    path = Path(path)
    doc, buffers = _load(path)
    mesh = Mesh(source=path.name)
    images = doc.get("images", [])
    textures = doc.get("textures", [])
    materials = doc.get("materials", [])

    def material_name(index: int | None) -> str:
        if index is None:
            return "default"
        mat = materials[index]
        name = mat.get("name") or f"material{index}"
        tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex is not None:
            source = textures[tex["index"]].get("source")
            uri = images[source].get("uri") if source is not None else None
            if uri and not uri.startswith("data:"):
                mesh.textures.setdefault(name, str(path.parent / uri))
        return name

    def visit(node_index: int, parent) -> None:
        node = doc["nodes"][node_index]
        world = parent @ _local(node)
        if "mesh" in node:
            linear = world[:3, :3]
            normal_m = np.linalg.inv(linear).T
            flip = np.linalg.det(linear) < 0
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    raise ValueError(f"{path.name}: primitive mode {prim['mode']} is not triangles")
                attrs = prim["attributes"]
                pos = _accessor(doc, buffers, attrs["POSITION"]).astype(float)
                base = len(mesh.positions)
                pos = pos @ linear.T + world[:3, 3]
                mesh.positions.extend(map(tuple, pos.tolist()))
                n_base = len(mesh.normals)
                has_n = "NORMAL" in attrs
                if has_n:
                    nrm = _accessor(doc, buffers, attrs["NORMAL"]).astype(float) @ normal_m.T
                    length = np.linalg.norm(nrm, axis=1, keepdims=True)
                    nrm = nrm / np.where(length == 0, 1, length)
                    mesh.normals.extend(map(tuple, nrm.tolist()))
                uv_base = len(mesh.uvs)
                has_uv = "TEXCOORD_0" in attrs
                if has_uv:
                    uv = _accessor(doc, buffers, attrs["TEXCOORD_0"]).astype(float)
                    mesh.uvs.extend((float(u), 1.0 - float(v)) for u, v in uv.tolist())
                if "indices" in prim:
                    idx = _accessor(doc, buffers, prim["indices"]).astype(np.int64).reshape(-1, 3)
                else:
                    idx = np.arange(len(pos), dtype=np.int64).reshape(-1, 3)
                if flip:
                    idx = idx[:, [0, 2, 1]]
                name = material_name(prim.get("material"))
                for a, b, c in idx.tolist():
                    mesh.triangles.append(Triangle(
                        material=name,
                        position=(base + a, base + b, base + c),
                        normal=(n_base + a, n_base + b, n_base + c) if has_n else (-1, -1, -1),
                        uv=(uv_base + a, uv_base + b, uv_base + c) if has_uv else (-1, -1, -1),
                    ))
        for child in node.get("children", []):
            visit(child, world)

    scene = doc.get("scenes", [{}])[doc.get("scene", 0)] if doc.get("scenes") else {}
    roots = scene.get("nodes") or list(range(len(doc.get("nodes", []))))
    for root in roots:
        visit(root, np.eye(4))
    if not mesh.triangles:
        raise ValueError(f"{path.name}: no triangles")
    return mesh
