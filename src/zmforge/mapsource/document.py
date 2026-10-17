"""The in-memory shape of a ``.map`` file.

Pure data: no parsing, no formatting, no I/O.  The names here describe what each
thing *is* in this design rather than echoing the file-format keyword that spells
it — a face of a solid is a :class:`Facet`, the twelve texture numbers are two
:class:`Projection` values, and a solid the reader could not understand survives
as an :class:`OpaqueSolid` instead of being dropped.
"""

from __future__ import annotations

import re
import uuid as _uuid
from dataclasses import dataclass, field

from ..spatial import Point
from .scalars import Scalar

__all__ = [
    "GUID_RE",
    "format_guid",
    "Projection",
    "DEFAULT_SURFACE",
    "DEFAULT_LIGHTMAP",
    "Facet",
    "BrushSolid",
    "ControlVertex",
    "PatchSolid",
    "OpaqueSolid",
    "Entity",
    "LayerDeclaration",
    "Document",
    "LIGHTMAP_MATERIAL",
]

#: The lightmap material every BO3 and CoD4 file uses on every face.
LIGHTMAP_MATERIAL = "lightmap_gray"

#: A braced, upper-case, 8-4-4-4-12 UUID: what Radiant writes for ``guid``.
GUID_RE = re.compile(
    r"^\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}$"
)


def format_guid(uuid_obj: _uuid.UUID | str) -> str:
    """Spell a UUID the way the file format wants it."""
    return "{" + str(uuid_obj).upper() + "}"


@dataclass(frozen=True, slots=True)
class Projection:
    """How a material is laid onto a facet: size, shift, rotation.

    The sixth number has no documented meaning (spec 1.5 marks it unverified);
    it is zero on every axis-aligned face in the corpus and is carried through
    untouched rather than guessed at.
    """

    size_u: float = 64.0
    size_v: float = 64.0
    shift_u: float = 0.0
    shift_v: float = 0.0
    rotation: float = 0.0
    sixth: float = 0.0

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.size_u,
            self.size_v,
            self.shift_u,
            self.shift_v,
            self.rotation,
            self.sixth,
        )

    @classmethod
    def of(cls, numbers) -> "Projection":
        values = tuple(numbers)
        if len(values) != 6:
            raise ValueError(f"a projection needs six numbers, got {len(values)}")
        return cls(*values)


#: What Radiant writes for an untouched face.
DEFAULT_SURFACE = Projection(64, 64, 0, 0, 0, 0)
#: What Radiant writes for an untouched face's lightmap.
DEFAULT_LIGHTMAP = Projection(16384, 16384, 0, 0, 0, 0)


@dataclass(slots=True)
class Facet:
    """One half-space of a solid: a plane given by three wound points, plus the
    material laid on it.

    Winding is the engine's, not Quake's: ``(B - A) x (C - A)`` points *into*
    the solid (spec 1.4, measured on 25/25 real brushes).  ``trailing`` holds any
    tokens after the lightmap numbers (``smoothing ...``,
    ``decalLayerSort "..." decalEditorSort N``) verbatim; the writer never
    invents them and never reformats them.
    """

    points: tuple[Point, Point, Point]
    material: str
    projection: Projection = DEFAULT_SURFACE
    lightmap: str = LIGHTMAP_MATERIAL
    lightmap_projection: Projection = DEFAULT_LIGHTMAP
    trailing: str = ""


@dataclass(slots=True)
class BrushSolid:
    """A convex solid: the intersection of its facets' half-spaces.

    ``layer`` is per-solid editor membership.  Neither the spec nor the format
    reference mentions it, but ``zm_giant.map`` carries one on 354 of its
    solids, so it is modelled rather than lost.
    """

    guid: str
    contents: tuple[str, ...] = ()
    facets: tuple[Facet, ...] = ()
    layer: str | None = None


@dataclass(slots=True)
class ControlVertex:
    """One control point of a patch grid.

    ``u``/``v`` are the material coordinates (large, world-projected in real
    files) and ``lu``/``lv`` the lightmap pair (small).  ``colour`` is the
    optional four-component tint; no public map contains one, so it is written
    only when a caller put it there.
    """

    position: Point
    u: Scalar | float = 0.0
    v: Scalar | float = 0.0
    lu: Scalar | float = 0.0
    lv: Scalar | float = 0.0
    colour: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class PatchSolid:
    """A control-point grid: a flat-triangulated ``mesh`` or a smoothed ``curve``.

    ``grid`` is outer groups by inner vertices; :attr:`width` and :attr:`height`
    are the two dimensions the file's dimension line reports.  ``subdivision``
    and ``flavour`` are that line's third and fourth numbers — the third behaves
    like a curve subdivision count and the fourth has no known meaning, so both
    are carried rather than derived.
    """

    guid: str
    kind: str = "mesh"
    contents: tuple[str, ...] = ()
    material: str = "caulk"
    lightmap: str = LIGHTMAP_MATERIAL
    subdivision: int = 0
    flavour: int = 8
    grid: tuple[tuple[ControlVertex, ...], ...] = ()
    layer: str | None = None

    @property
    def width(self) -> int:
        """Number of vertex groups (the outer index)."""
        return len(self.grid)

    @property
    def height(self) -> int:
        """Vertices per group (the inner index)."""
        return len(self.grid[0]) if self.grid else 0


@dataclass(slots=True)
class OpaqueSolid:
    """A solid body the reader did not understand, kept verbatim.

    ``body`` is the text between the container's braces, exactly as it was read.
    Geometry is never dropped silently; the reader also leaves a line in
    :attr:`Document.notes` saying what it could not parse.
    """

    guid: str | None = None
    body: str = ""
    layer: str | None = None


@dataclass(slots=True)
class Entity:
    """One ``{ ... }`` block: identity, layer membership, key/values, solids.

    Key/value pairs stay an ordered list because Radiant's order is not
    alphabetical and duplicate keys are legal; a dict would silently discard one
    of a pair the game may well read.
    """

    guid: str
    layer: str | None = None
    pairs: list[tuple[str, str]] = field(default_factory=list)
    solids: list = field(default_factory=list)

    @property
    def classname(self) -> str | None:
        return self.value("classname")

    def value(self, key: str, default: str | None = None) -> str | None:
        """The first value for ``key``."""
        for name, value in self.pairs:
            if name == key:
                return value
        return default

    def values(self, key: str) -> list[str]:
        """Every value for ``key``, in file order."""
        return [value for name, value in self.pairs if name == key]

    def put(self, key: str, value: str) -> None:
        """Set ``key``, replacing the first occurrence or appending a new pair."""
        for index, (name, _) in enumerate(self.pairs):
            if name == key:
                self.pairs[index] = (key, value)
                return
        self.pairs.append((key, value))


@dataclass(slots=True)
class LayerDeclaration:
    """A row of the layer table: a ``/``-separated path and its editor flags."""

    path: str
    flags: tuple[str, ...] = ()


@dataclass(slots=True)
class Document:
    """A whole ``.map`` file.

    ``newline`` is the ending the file had (or ``"\\n"`` for a fresh one) so an
    edited CRLF file goes back out as CRLF.  ``notes`` collects everything the
    reader tolerated but wants to tell someone about.
    """

    starting_number: int = 0
    layers: list[LayerDeclaration] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    newline: str = "\n"
    notes: list[str] = field(default_factory=list)

    @property
    def worldspawn(self) -> Entity | None:
        for entity in self.entities:
            if entity.classname == "worldspawn":
                return entity
        return None

    def entities_of(self, classname: str) -> list[Entity]:
        return [e for e in self.entities if e.classname == classname]
