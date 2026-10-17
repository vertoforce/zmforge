"""Turn ``.map`` text into a :class:`~zmforge.mapsource.document.Document`.

The format is line-oriented, so this is a cursor over lines rather than a
tokeniser.  Two things make it more than a loop: a patch opens a second brace
inside its container, so finding the end of a solid needs a depth counter, and
real files contain constructs the format reference does not mention (a missing
``script_startingnumber`` line, dangling ``// entity`` comments at EOF).  The
policy throughout is to tolerate and take a note; only a missing ``iwmap 4`` or
a brace that never closes is fatal.
"""

from __future__ import annotations

import re

from ..errors import MapTextError
from ..spatial import Point
from .document import (
    BrushSolid,
    ControlVertex,
    Document,
    Entity,
    Facet,
    LayerDeclaration,
    OpaqueSolid,
    PatchSolid,
    Projection,
)
from .scalars import Scalar, parse_scalar

__all__ = ["parse_map_text"]

_HEADER = "iwmap 4"
_PATCH_KEYWORDS = ("mesh", "curve")

_STARTING_NUMBER_RE = re.compile(r'^"script_startingnumber"\s+(-?\d+)\s*$')
_LAYER_RE = re.compile(r'^"([^"]*)"\s+flags\b\s*(.*)$')
_PAIR_RE = re.compile(r'^"([^"]*)"\s+"(.*)"\s*$')
_TAGGED_RE = re.compile(r'^(guid|layer)\s+"(.*)"\s*$')
_CONTENTS_RE = re.compile(r"^contents\s+([^;]*);\s*$")
_POINTS_RE = re.compile(
    r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)\s*"
    r"\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)\s*"
    r"\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)\s*"
)


class _Cursor:
    """A line cursor that remembers file line numbers for error messages."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._at = 0

    @property
    def line_number(self) -> int:
        return self._at + 1

    def done(self) -> bool:
        return self._at >= len(self._lines)

    def peek(self) -> str:
        return self._lines[self._at]

    def take(self) -> str:
        line = self._lines[self._at]
        self._at += 1
        return line

    def skip(self) -> None:
        self._at += 1


def parse_map_text(text: str, newline: str = "\n") -> Document:
    """Parse ``text`` into a document, tolerating everything recoverable."""
    lines = text.split("\n")
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    cursor = _Cursor(lines)
    doc = Document(newline=newline)

    _read_header(cursor, doc)

    while not cursor.done():
        raw = cursor.peek()
        line = raw.strip()
        if not line:
            cursor.skip()
            continue
        if line.startswith("//"):
            cursor.skip()
            continue
        if line == "{":
            opened_at = cursor.line_number
            cursor.skip()
            doc.entities.append(_read_entity(cursor, doc, opened_at))
            continue
        starting = _STARTING_NUMBER_RE.match(line)
        if starting is not None:
            doc.starting_number = int(starting.group(1))
            cursor.skip()
            continue
        layer = _LAYER_RE.match(line)
        if layer is not None:
            doc.layers.append(
                LayerDeclaration(layer.group(1), tuple(layer.group(2).split()))
            )
            cursor.skip()
            continue
        doc.notes.append(f"line {cursor.line_number}: ignored stray line {line!r}")
        cursor.skip()

    return doc


def _read_header(cursor: _Cursor, doc: Document) -> None:
    while not cursor.done() and not cursor.peek().strip():
        cursor.skip()
    if cursor.done() or cursor.peek().strip() != _HEADER:
        raise MapTextError(
            f"not a Radiant map source: first line is not {_HEADER!r}",
            cursor.line_number if not cursor.done() else None,
        )
    cursor.skip()


# -- entities ------------------------------------------------------------


def _read_entity(cursor: _Cursor, doc: Document, opened_at: int) -> Entity:
    entity = Entity(guid="")
    while True:
        if cursor.done():
            raise MapTextError("entity block is never closed", opened_at)
        raw = cursor.peek()
        line = raw.strip()
        if not line or line.startswith("//"):
            cursor.skip()
            continue
        if line == "}":
            cursor.skip()
            return entity
        if line == "{":
            solid_at = cursor.line_number
            cursor.skip()
            body = _read_block_body(cursor, solid_at)
            entity.solids.append(_read_solid(body, doc, solid_at))
            continue
        tagged = _TAGGED_RE.match(line)
        if tagged is not None:
            if tagged.group(1) == "guid":
                entity.guid = tagged.group(2)
            else:
                entity.layer = tagged.group(2)
            cursor.skip()
            continue
        pair = _PAIR_RE.match(line)
        if pair is not None:
            entity.pairs.append((pair.group(1), pair.group(2)))
            cursor.skip()
            continue
        doc.notes.append(
            f"line {cursor.line_number}: ignored unrecognised entity line {line!r}"
        )
        cursor.skip()


def _read_block_body(cursor: _Cursor, opened_at: int) -> list[str]:
    """Collect the lines of a ``{ ... }`` body, counting nested braces."""
    depth = 1
    body: list[str] = []
    while True:
        if cursor.done():
            raise MapTextError("brace is never closed", opened_at)
        raw = cursor.take()
        line = raw.strip()
        if line.endswith("{") and not line.startswith("//"):
            depth += 1
        elif line == "}":
            depth -= 1
            if depth == 0:
                return body
        body.append(raw)


# -- solids --------------------------------------------------------------


def _read_solid(body: list[str], doc: Document, opened_at: int):
    stripped = [line.strip() for line in body]
    kind = next((k for k in _PATCH_KEYWORDS if k in stripped), None)
    try:
        if kind is not None:
            return _read_patch(body, kind)
        return _read_brush(body)
    except MapTextError as problem:
        doc.notes.append(
            f"line {opened_at}: solid kept verbatim, could not parse it ({problem})"
        )
        return OpaqueSolid(guid=_find_guid(stripped), body="\n".join(body))


def _find_guid(stripped: list[str]) -> str | None:
    for line in stripped:
        tagged = _TAGGED_RE.match(line)
        if tagged is not None and tagged.group(1) == "guid":
            return tagged.group(2)
    return None


def _read_brush(body: list[str]) -> BrushSolid:
    guid = ""
    layer: str | None = None
    contents: tuple[str, ...] = ()
    facets: list[Facet] = []
    for raw in body:
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        tagged = _TAGGED_RE.match(line)
        if tagged is not None:
            if tagged.group(1) == "guid":
                guid = tagged.group(2)
            else:
                layer = tagged.group(2)
            continue
        flags = _CONTENTS_RE.match(line)
        if flags is not None:
            contents = tuple(flags.group(1).split())
            continue
        if line.startswith("("):
            facets.append(_read_facet(line))
            continue
        raise MapTextError(f"unrecognised line in a brush: {line!r}")
    if not facets:
        raise MapTextError("a brush with no faces")
    return BrushSolid(
        guid=guid, contents=contents, facets=tuple(facets), layer=layer
    )


def _read_facet(line: str) -> Facet:
    triples = _POINTS_RE.match(line)
    if triples is None:
        raise MapTextError(f"a face without three point triples: {line!r}")
    coordinates = [parse_scalar(token) for token in triples.groups()]
    points = (
        Point(*coordinates[0:3]),
        Point(*coordinates[3:6]),
        Point(*coordinates[6:9]),
    )
    tail = line[triples.end():]
    tokens = tail.split()
    if len(tokens) < 14:
        raise MapTextError(f"a face with a short texture block: {line!r}")
    material = tokens[0]
    projection = Projection.of(parse_scalar(t) for t in tokens[1:7])
    lightmap = tokens[7]
    lightmap_projection = Projection.of(parse_scalar(t) for t in tokens[8:14])
    consumed = 0
    offset = 0
    for match in re.finditer(r"\S+", tail):
        consumed += 1
        if consumed == 14:
            offset = match.end()
            break
    return Facet(
        points=points,
        material=material,
        projection=projection,
        lightmap=lightmap,
        lightmap_projection=lightmap_projection,
        trailing=tail[offset:].strip(),
    )


def _read_patch(body: list[str], kind: str) -> PatchSolid:
    lines = [raw.strip() for raw in body]
    lines = [line for line in lines if line and not line.startswith("//")]
    guid = ""
    layer: str | None = None
    at = 0
    while at < len(lines) and lines[at] != kind:
        tagged = _TAGGED_RE.match(lines[at])
        if tagged is not None and tagged.group(1) == "guid":
            guid = tagged.group(2)
        elif lines[at] not in ("{", "}"):
            # Only ``guid`` precedes the keyword in a shipped file (22,795 of
            # 22,795 patch containers, mod tools map_source).  A
            # ``layer`` here is what the compiler rejects as a brush face.
            raise MapTextError(f"unexpected line before a patch: {lines[at]!r}")
        at += 1
    if at >= len(lines):
        raise MapTextError("a patch keyword with no body")
    at += 1
    if at < len(lines) and lines[at] == "{":
        at += 1

    # Radiant writes a patch's layer as the first line of the inner block,
    # before ``contents`` (zm_giant_warehouse_bridge_ramp.map brush 0).
    if at < len(lines):
        tagged = _TAGGED_RE.match(lines[at])
        if tagged is not None and tagged.group(1) == "layer":
            layer = tagged.group(2)
            at += 1

    contents: tuple[str, ...] = ()
    if at < len(lines):
        flags = _CONTENTS_RE.match(lines[at])
        if flags is not None:
            contents = tuple(flags.group(1).split())
            at += 1
    if at < len(lines) and lines[at].startswith("toolFlags"):
        at += 1
    else:
        raise MapTextError("a patch without a toolFlags line")
    if at + 2 >= len(lines):
        raise MapTextError("a patch without material, lightmap and dimensions")
    material = lines[at]
    lightmap = lines[at + 1]
    dimensions = lines[at + 2].split()
    at += 3
    if len(dimensions) != 4:
        raise MapTextError(f"a patch dimension line of {len(dimensions)} numbers")
    try:
        width, height, subdivision, flavour = (int(float(n)) for n in dimensions)
    except ValueError as exc:
        raise MapTextError(f"a non-numeric patch dimension: {dimensions!r}") from exc

    grid: list[tuple[ControlVertex, ...]] = []
    group: list[ControlVertex] | None = None
    for line in lines[at:]:
        if line == "(":
            group = []
        elif line == ")":
            if group is None:
                raise MapTextError("a patch group that closes before it opens")
            grid.append(tuple(group))
            group = None
        elif line.startswith("v "):
            if group is None:
                raise MapTextError("a patch vertex outside a group")
            group.append(_read_control_vertex(line))
        elif line in ("{", "}"):
            continue
        else:
            raise MapTextError(f"unrecognised line in a patch body: {line!r}")
    if group is not None:
        raise MapTextError("a patch group that never closes")
    if len(grid) != width or any(len(g) != height for g in grid):
        raise MapTextError(
            f"a patch that says {width}x{height} but holds "
            f"{len(grid)}x{[len(g) for g in grid]}"
        )
    return PatchSolid(
        guid=guid,
        kind=kind,
        contents=contents,
        material=material,
        lightmap=lightmap,
        subdivision=subdivision,
        flavour=flavour,
        grid=tuple(grid),
        layer=layer,
    )


def _read_control_vertex(line: str) -> ControlVertex:
    tokens = line.split()
    at = 1
    if len(tokens) < 9:
        raise MapTextError(f"a short patch vertex: {line!r}")
    position = Point(*(parse_scalar(t) for t in tokens[at : at + 3]))
    at += 3
    colour: tuple[Scalar, Scalar, Scalar, Scalar] | None = None
    if tokens[at] == "c":
        at += 1
        colour = tuple(parse_scalar(t) for t in tokens[at : at + 4])  # type: ignore[assignment]
        at += 4
    if tokens[at] != "t":
        raise MapTextError(f"a patch vertex without its 't' marker: {line!r}")
    at += 1
    coordinates = [parse_scalar(t) for t in tokens[at : at + 4]]
    if len(coordinates) != 4:
        raise MapTextError(f"a patch vertex with {len(coordinates)} texture numbers")
    return ControlVertex(
        position=position,
        u=coordinates[0],
        v=coordinates[1],
        lu=coordinates[2],
        lv=coordinates[3],
        colour=colour,
    )
