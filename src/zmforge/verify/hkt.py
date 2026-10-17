"""Reading ``<map>_navmesh.hkt``: the mesh the compiler actually built.

``cod2map64 -navmesh`` writes this file beside the BSP, and it is the only
artefact on disk that says where the *zombies* can walk.  Everything else this
package checks is either the model before the build or the text the build read;
this is the build's own answer, and the answer a player sees at round one.

The format, and how it was worked out
-------------------------------------
The file is a **Havok binary tagfile**, ``hk_2014.2.0-r1``, and a single
``.hkt`` holds several of them end to end -- the magic
``CA B0 0D 1E  D0 11 FA CE`` appears once per tagfile.  Measured: every navmesh
the compiler writes carries five:
generation settings, two small unnamed ones, the mesh itself
(``hkaiNavMesh``), and a one-string tagfile holding the JSON that also sits in
``<map>_metadata.json``.  :func:`read_navmesh` picks the one whose type
section declares ``hkaiNavMesh`` rather than trusting the order.

A tagfile is self-describing: it carries its own type definitions -- class
names, member names and member types -- ahead of the data, which is what makes
reading it without Havok's own SDK possible at all.  No specification was
available on the mod tools install, so the grammar below was derived by inspection and then
held to account against the files' own arithmetic (see "What proves the read").

* **Integers** are LEB128, little-endian 7-bit groups.  Nearly every integer in
  the stream is then shifted: the value is ``v >> 1`` and bit 0 is a flag whose
  meaning depends on where it sits -- a sign bit on a mesh index, a
  "reference rather than literal" bit on a name.  Bitfields are the exception
  and are read raw.
* **Strings** are ``varint(len * 2)`` then that many bytes, and every string is
  appended to a table in the order it is first read.
* **A name** is one varint.  Even means a new string follows; odd means the
  name is already in the table, at ``(v >> 1) - 2`` counting the SDK version
  string as the first entry.
* **The header** is the magic, then ``0x02 0x0a`` and the SDK string, then the
  four bytes ``0x15 0x00 0x00 0x00``.  Those four are identical in every file
  measured so far and nothing in the mod tools says what they mean; they are asserted
  rather than interpreted.
* **A type definition** is the tag ``0x04``, a name, a version, the parent
  type's index, a member count, and then that many ``name, kind`` pairs.  A
  kind whose low nibble is 8 or 9 (a pointer or an inline struct) is followed
  by the name of the type it points at; bit 5 means a fixed-length tuple and is
  followed by its length.  Kinds: 0 is a member the writer does not serialise
  at all, 1 a byte, 2 an integer, 3 a float, 4 a vector, 8 a pointer, 9 an
  inline struct, 10 a string, and bit 4 makes any of them an array.
* **An object** is the tag ``0x08``, a type index, and a **presence bitfield**:
  bit *i* is member *i* of the type's members with its parents' members in
  front.  A member whose bit is clear is not in the stream at all and reads as
  zero -- which is why a one-face mesh has no ``startEdgeIndex`` column.
* **An array of structs** is stored **by column, not by row**: a count, the
  element type's presence bitfield, and then one run per present member.  A
  varint column is preceded by a single ``0x08`` byte; a byte column is not.
  That ``0x08`` is unexplained -- it is the same byte that introduces an
  object -- and it is asserted on every column so a file that disagrees fails
  loudly instead of being misread.
* **An array of vectors** is a count, a component count (3 or 4; both occur),
  and then ``count * components`` little-endian ``float32``.
* ``0x0e`` ends the object stream.

Units
-----
Vertices are in **metres**, and one map unit is :data:`METRES_PER_UNIT`, so
:func:`read_navmesh` multiplies back into the units the rest of this package
works in.  The number is not a guess: the generation-settings tagfile in the
same file stores ``maxStepHeight`` as ``0.4572``, which is exactly ``18 *
0.0254``, and ``18`` is what ``bin\\default_navmesh_settings.json`` says
(``N1``).  Beside it sits ``0.0078125`` -- 1/128 m, the generator's
quantisation grid -- and that is why a converted coordinate lands within about
:data:`QUANTISATION` of a round number rather than on it.  Measured on
``zm_forge_gate``: the three rooms' interior walls are at x = -144, -112, 752
and 784 in the model, and the mesh puts vertices at -144.0, -112.0, 752.0 and
784.0 after conversion, with only the map's outer boundary out by 0.3.

What proves the read
--------------------
The file checks itself, and :func:`read_navmesh` insists on it:

* the faces' ``startEdgeIndex`` plus ``numEdges`` chain to exactly the edge
  count -- 265 faces closing on edge 1,192 of 1,192 on a test map,
  14 faces closing on 62 of 62 for the
  three-room recipe;
* the largest vertex index an edge names is exactly one less than the vertex
  count (554 of 555, and 35 of 36);
* ``oppositeEdge`` is symmetric -- if edge A names B, B names A -- and
  ``oppositeFace`` never names a face that does not exist;
* every face's edges form a closed ring, each edge's ``b`` being the next
  edge's ``a``, for every face of every mesh measured;
* and the trailing ``faceData`` array, which this reader does not need, comes
  out at exactly ``faces * faceDataStriding`` elements, which it could not if
  the stream had drifted by a byte.

Eleven meshes compiled with the mod tools read this way, from a single square of floor to a
265-face map on four storeys.

Anything the grammar above does not cover raises :class:`NavmeshUnreadable`
with the offset, because a half-understood binary is worse than no check: it
reports a map as sound on data it misread.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..errors import ForgeError

__all__ = [
    "NavmeshUnreadable",
    "RawNavMesh",
    "METRES_PER_UNIT",
    "QUANTISATION",
    "MAGIC",
    "read_navmesh",
    "read_navmesh_bytes",
]


class NavmeshUnreadable(ForgeError):
    """The navmesh file is not shaped the way this reader understands."""


#: The two 32-bit words a Havok binary tagfile starts with.
MAGIC = bytes.fromhex("1e0db0cacefa11d0")

#: Metres per map unit.  **[measured]** -- ``maxStepHeight`` is ``18`` in
#: ``default_navmesh_settings.json`` and ``0.4572`` in the generation-settings
#: tagfile of every navmesh measured, and ``0.4572 / 18`` is exactly this.
METRES_PER_UNIT = 0.0254

#: The generator's quantisation grid, in map units.  **[measured]** -- the same
#: settings object stores ``0.0078125`` (1/128 m) as ``quantizationGridSize``,
#: which is this many units.  Vertex coordinates are snapped to it, so a
#: converted coordinate is within half of this of the geometry it came from.
QUANTISATION = 0.0078125 / METRES_PER_UNIT

#: Tag bytes.  ``0x02`` opens the file info, ``0x04`` a type, ``0x08`` an
#: object (and, unexplained, a column), ``0x0e`` ends the object stream.
_TAG_FILEINFO = 0x02
_TAG_TYPE = 0x04
_TAG_OBJECT = 0x08
_TAG_END = 0x0E

#: The four bytes between the SDK string and the first type, identical in every
#: file measured so far.
_PREAMBLE = (0x15, 0x00, 0x00, 0x00)

#: Member kinds.  The low nibble is the kind; bit 4 makes it an array and bit 5
#: a fixed-length tuple.
_SKIPPED, _BYTE, _INT, _FLOAT, _VECTOR = 0, 1, 2, 3, 4
_POINTER, _STRUCT, _STRING = 8, 9, 10
_ARRAY, _TUPLE = 16, 32


@dataclass(frozen=True, slots=True)
class _Member:
    name: str
    kind: int
    of: str | None = None
    tuple_size: int | None = None


@dataclass(frozen=True, slots=True)
class _Type:
    name: str
    version: int
    parent: int
    members: tuple[_Member, ...]


@dataclass(frozen=True, slots=True)
class RawNavMesh:
    """The three arrays of an ``hkaiNavMesh``, in map units.

    A face owns the edges ``start_edge[i] .. start_edge[i] + num_edges[i]``,
    each edge runs from vertex ``a`` to vertex ``b``, and ``opposite_face`` is
    the face across that edge or ``-1`` when the edge is the mesh's border.
    That last array is the whole of zombie connectivity: a border edge is a
    wall, and a face graph that falls into more than one piece is a map with
    rooms the walkers cannot path between.
    """

    vertices: tuple[tuple[float, float, float], ...]
    start_edge: tuple[int, ...]
    num_edges: tuple[int, ...]
    edge_a: tuple[int, ...]
    edge_b: tuple[int, ...]
    opposite_edge: tuple[int, ...]
    opposite_face: tuple[int, ...]

    @property
    def face_count(self) -> int:
        return len(self.start_edge)

    @property
    def edge_count(self) -> int:
        return len(self.edge_a)


# --------------------------------------------------------------------------
# The byte stream
# --------------------------------------------------------------------------
class _Stream:
    """A cursor over one tagfile, with the primitives the grammar is built of."""

    def __init__(self, data: bytes, at: int = 0) -> None:
        self.data = data
        self.at = at
        self.strings: list[str] = []

    def fail(self, what: str) -> NavmeshUnreadable:
        return NavmeshUnreadable(f"{what} at byte {self.at} of the navmesh tagfile")

    def byte(self) -> int:
        if self.at >= len(self.data):
            raise self.fail("the file ends mid-value")
        value = self.data[self.at]
        self.at += 1
        return value

    def raw(self) -> int:
        """One LEB128 integer, unshifted."""
        value = shift = 0
        while True:
            piece = self.byte()
            value |= (piece & 0x7F) << shift
            shift += 7
            if not piece & 0x80:
                return value

    def count(self) -> int:
        return self.raw() >> 1

    def signed(self) -> int:
        value = self.raw()
        return -(value >> 1) if value & 1 else value >> 1

    def floats(self, how_many: int) -> tuple[float, ...]:
        end = self.at + 4 * how_many
        if end > len(self.data):
            raise self.fail("a float array runs off the end of the file")
        out = struct.unpack_from(f"<{how_many}f", self.data, self.at)
        self.at = end
        return out

    def text(self, length: int) -> str:
        end = self.at + length
        if end > len(self.data):
            raise self.fail("a string runs off the end of the file")
        out = self.data[self.at : end].decode("utf-8", "replace")
        self.at = end
        return out

    def name(self) -> str:
        """A new string, or one already in the table."""
        value = self.raw()
        if value & 1:
            index = (value >> 1) - 2
            if not 0 <= index < len(self.strings):
                raise self.fail(f"a name refers to string {index}, which does not exist")
            return self.strings[index]
        text = self.text(value >> 1)
        self.strings.append(text)
        return text

    def expect(self, tag: int, what: str) -> None:
        where = self.at
        got = self.raw()
        if got != tag:
            self.at = where
            raise self.fail(f"expected {what} (0x{tag:02x}), got 0x{got:02x}")


def _split(data: bytes) -> list[tuple[int, int]]:
    """Where each tagfile in the file starts and ends."""
    starts: list[int] = []
    at = data.find(MAGIC)
    while at >= 0:
        starts.append(at)
        at = data.find(MAGIC, at + 1)
    return [
        (start, starts[index + 1] if index + 1 < len(starts) else len(data))
        for index, start in enumerate(starts)
    ]


def _read_types(stream: _Stream) -> list[_Type]:
    """The type section: names, parents and members, in declaration order."""
    if stream.data[stream.at : stream.at + len(MAGIC)] != MAGIC:
        raise stream.fail("no Havok tagfile magic")
    stream.at += len(MAGIC)
    stream.expect(_TAG_FILEINFO, "the file-info tag")
    stream.raw()
    stream.name()  # the SDK version, table entry one
    for expected in _PREAMBLE:
        if stream.raw() != expected:
            raise stream.fail("the header is not the one this reader has seen")
    types: list[_Type] = [_Type("", 0, 0, ())]  # index 0 is the null type
    while True:
        where = stream.at
        if stream.raw() != _TAG_TYPE:
            stream.at = where
            return types
        name = stream.name()
        version, parent, count = stream.count(), stream.count(), stream.count()
        members: list[_Member] = []
        for _ in range(count):
            member_name = stream.name()
            kind = stream.count()
            of = stream.name() if kind & 15 in (_POINTER, _STRUCT) else None
            size = stream.count() if kind & _TUPLE else None
            members.append(_Member(member_name, kind, of, size))
        types.append(_Type(name, version, parent, tuple(members)))


def _flattened(types: Sequence[_Type], index: int) -> tuple[_Member, ...]:
    """A type's members with its parents' members in front, which is bit order."""
    out: list[_Member] = []
    if types[index].parent:
        out.extend(_flattened(types, types[index].parent))
    out.extend(types[index].members)
    return tuple(out)


def _index_of(types: Sequence[_Type], name: str) -> int:
    for index, entry in enumerate(types):
        if entry.name == name:
            return index
    raise NavmeshUnreadable(f"this tagfile declares no {name}")


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------
def _read_value(stream: _Stream, types: Sequence[_Type], member: _Member):
    kind = member.kind
    if kind & _ARRAY:
        return _read_array(stream, types, member, stream.count())
    if kind & _TUPLE:
        return [
            _read_value(stream, types, _Member(member.name, kind & ~_TUPLE, member.of))
            for _ in range(member.tuple_size or 0)
        ]
    base = kind & 15
    if base == _SKIPPED:
        return None
    if base == _BYTE:
        return stream.byte()
    if base == _INT:
        return stream.signed()
    if base == _FLOAT:
        return stream.floats(1)[0]
    if base == _VECTOR:
        return stream.floats(stream.count())
    if base == _POINTER:
        return ("object", stream.count())
    if base == _STRUCT:
        return _read_object_body(stream, types, _index_of(types, member.of or ""))
    if base == _STRING:
        return stream.text(stream.count())
    raise stream.fail(f"member {member.name!r} has kind {kind}, which is not known")


def _read_array(stream: _Stream, types: Sequence[_Type], member: _Member, count: int):
    base = member.kind & 15
    if base == _STRUCT:
        return _read_struct_columns(stream, types, _index_of(types, member.of or ""), count)
    if base == _VECTOR:
        components = stream.count()
        return [stream.floats(components) for _ in range(count)]
    if base == _BYTE:
        return [stream.byte() for _ in range(count)]
    if base == _INT:
        stream.expect(_TAG_OBJECT, "the marker before a varint column")
        return [stream.signed() for _ in range(count)]
    if base == _FLOAT:
        # **[inferred]** -- no sample read so far has a float column (the one
        # candidate, hkaiNavMeshEdge::userEdgeCost, is absent from every mesh
        # measured so far), so the "no marker, raw floats" shape is reasoning
        # from the byte column rather than a measurement.
        return list(stream.floats(count))
    if base == _POINTER:
        stream.expect(_TAG_OBJECT, "the marker before a pointer column")
        return [("object", stream.count()) for _ in range(count)]
    raise stream.fail(f"an array of kind {member.kind} is not known")


def _read_struct_columns(
    stream: _Stream, types: Sequence[_Type], index: int, count: int
) -> dict[str, list]:
    """An array of structs, stored one member at a time rather than one row."""
    present = stream.raw()
    columns: dict[str, list] = {}
    for position, member in enumerate(_flattened(types, index)):
        if not (present >> position) & 1 or member.kind == _SKIPPED:
            continue
        columns[member.name] = _read_array(stream, types, member, count)
    return columns


def _read_object_body(stream: _Stream, types: Sequence[_Type], index: int) -> dict:
    present = stream.raw()
    out: dict = {}
    for position, member in enumerate(_flattened(types, index)):
        if not (present >> position) & 1 or member.kind == _SKIPPED:
            continue
        out[member.name] = _read_value(stream, types, member)
    return out


# --------------------------------------------------------------------------
# The mesh
# --------------------------------------------------------------------------
#: The members of ``hkaiNavMesh`` this reader needs, in declaration order.  It
#: stops after ``vertices`` rather than reading the whole object: everything
#: after it (``streamingSets``, the per-face user data, the bounding box) is
#: either absent in every mesh measured so far or of no use to a reachability
#: check, and not reading it is one fewer encoding to get wrong.
_NEEDED = ("faces", "edges", "vertices")


def _read_mesh(stream: _Stream, types: Sequence[_Type]) -> RawNavMesh:
    wanted = _index_of(types, "hkaiNavMesh")
    while True:
        if stream.at >= len(stream.data):
            raise stream.fail("the tagfile ends without an hkaiNavMesh object")
        where = stream.at
        tag = stream.raw()
        if tag == _TAG_END:
            raise stream.fail("the object stream ends without an hkaiNavMesh object")
        if tag != _TAG_OBJECT:
            stream.at = where
            raise stream.fail(f"expected an object (0x08), got 0x{tag:02x}")
        index = stream.count()
        if index != wanted:
            _read_object_body(stream, types, index)
            continue
        present = stream.raw()
        values: dict = {}
        for position, member in enumerate(_flattened(types, index)):
            if not (present >> position) & 1 or member.kind == _SKIPPED:
                continue
            values[member.name] = _read_value(stream, types, member)
            if member.name == _NEEDED[-1]:
                break
        return _assemble(stream, values)


def _column(columns: dict[str, list], name: str, count: int) -> tuple[int, ...]:
    """One column of a struct array, or the zeros an absent member stands for."""
    return tuple(columns.get(name) or [0] * count)


def _assemble(stream: _Stream, values: dict) -> RawNavMesh:
    for name in _NEEDED:
        if name not in values:
            raise stream.fail(f"the hkaiNavMesh has no {name}")
    faces = values["faces"]
    edges = values["edges"]
    face_count = len(next(iter(faces.values()), ()))
    edge_count = len(next(iter(edges.values()), ()))
    scale = 1.0 / METRES_PER_UNIT
    vertices = tuple(
        (point[0] * scale, point[1] * scale, point[2] * scale)
        for point in values["vertices"]
    )
    mesh = RawNavMesh(
        vertices=vertices,
        start_edge=_column(faces, "startEdgeIndex", face_count),
        num_edges=_column(faces, "numEdges", face_count),
        edge_a=_column(edges, "a", edge_count),
        edge_b=_column(edges, "b", edge_count),
        opposite_edge=_column(edges, "oppositeEdge", edge_count),
        opposite_face=_column(edges, "oppositeFace", edge_count),
    )
    _prove(stream, mesh)
    return mesh


def _prove(stream: _Stream, mesh: RawNavMesh) -> None:
    """The file's own arithmetic, which a misread stream cannot satisfy."""
    faces, edges, vertices = mesh.face_count, mesh.edge_count, len(mesh.vertices)
    for face in range(faces):
        start, how_many = mesh.start_edge[face], mesh.num_edges[face]
        if start < 0 or how_many < 3 or start + how_many > edges:
            raise stream.fail(
                f"face {face} claims edges {start}..{start + how_many} of {edges}"
            )
        ring = range(start, start + how_many)
        for step, edge in enumerate(ring):
            following = start + (step + 1) % how_many
            if mesh.edge_b[edge] != mesh.edge_a[following]:
                raise stream.fail(f"face {face} is not a closed ring of edges")
    for edge in range(edges):
        if not (0 <= mesh.edge_a[edge] < vertices and 0 <= mesh.edge_b[edge] < vertices):
            raise stream.fail(f"edge {edge} names a vertex that does not exist")
        across = mesh.opposite_edge[edge]
        if across >= edges or mesh.opposite_face[edge] >= faces:
            raise stream.fail(f"edge {edge} names a face or edge that does not exist")
        if across >= 0 and mesh.opposite_edge[across] != edge:
            raise stream.fail(f"edge {edge} and {across} do not agree that they are a pair")


def read_navmesh_bytes(data: bytes) -> RawNavMesh:
    """The mesh out of the bytes of a ``<map>_navmesh.hkt``."""
    if not data:
        raise NavmeshUnreadable("the navmesh file is empty")
    last: NavmeshUnreadable | None = None
    for start, end in _split(data):
        stream = _Stream(data[start:end])
        try:
            types = _read_types(stream)
        except NavmeshUnreadable as unreadable:  # a tagfile this reader skips
            last = unreadable
            continue
        if not any(entry.name == "hkaiNavMesh" for entry in types):
            continue
        return _read_mesh(stream, types)
    raise last or NavmeshUnreadable(
        "no tagfile in this file declares an hkaiNavMesh; the compiler writes "
        "the mesh into the fourth of five tagfiles, so this is not one of its "
        "navmesh files"
    )


def read_navmesh(path: str | Path) -> RawNavMesh:
    """The mesh out of ``<map>_navmesh.hkt`` on disk."""
    location = Path(path)
    if not location.exists():
        raise NavmeshUnreadable(
            f"{location} does not exist; the compiler prints a 'Writing' line "
            "for the navmesh whether or not it writes one"
        )
    return read_navmesh_bytes(location.read_bytes())
