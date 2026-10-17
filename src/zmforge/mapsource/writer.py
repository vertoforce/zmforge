"""Render a :class:`~zmforge.mapsource.document.Document` back to ``.map`` text.

Radiant's own layout is reproduced closely — one leading space on a brush body,
three spaces and a tab inside a patch, ``guid`` first in every block — because a
file that looks like Radiant's own output is one a mapper can diff and one the
editor reopens without reformatting the whole thing.  Entity and solid numbering
is regenerated here, so the reader is free to ignore whatever numbers a file
carried.  Every number leaves through :func:`decimal_token`.
"""

from __future__ import annotations

from .document import (
    BrushSolid,
    ControlVertex,
    Document,
    Entity,
    Facet,
    OpaqueSolid,
    PatchSolid,
    Projection,
)
from .scalars import decimal_token

__all__ = ["render_map_text"]

_HEADER = "iwmap 4"
_BRUSH_INDENT = " "
_PATCH_INDENT = "  "
_PATCH_FIELD_INDENT = "   "
_VERTEX_INDENT = "\t"


def render_map_text(doc: Document) -> str:
    """Render the whole document, joined with the document's line ending."""
    lines: list[str] = [_HEADER, f'"script_startingnumber" {doc.starting_number}']
    for layer in doc.layers:
        lines.append(_render_layer(layer.path, layer.flags))
    for number, entity in enumerate(doc.entities):
        lines.extend(_render_entity(entity, number))
    return doc.newline.join(lines) + doc.newline


def _render_layer(path: str, flags) -> str:
    words = " ".join(flags)
    if not words:
        return f'"{path}" flags'
    return f'"{path}" flags {words}'


def _render_entity(entity: Entity, number: int) -> list[str]:
    lines = [f"// entity {number}", "{", f'guid "{entity.guid}"']
    if entity.layer is not None:
        lines.append(f'layer "{entity.layer}"')
    for key, value in entity.pairs:
        lines.append(f'"{key}" "{value}"')
    for index, solid in enumerate(entity.solids):
        lines.append(f"// brush {index}")
        lines.extend(_render_solid(solid))
    lines.append("}")
    return lines


def _render_solid(solid) -> list[str]:
    if isinstance(solid, BrushSolid):
        return _render_brush(solid)
    if isinstance(solid, PatchSolid):
        return _render_patch(solid)
    if isinstance(solid, OpaqueSolid):
        body = solid.body.split("\n") if solid.body else []
        return ["{", *body, "}"]
    raise TypeError(f"not something this writer can emit: {type(solid).__name__}")


def _render_brush(brush: BrushSolid) -> list[str]:
    lines = ["{", f'{_BRUSH_INDENT}guid "{brush.guid}"']
    if brush.layer is not None:
        lines.append(f'{_BRUSH_INDENT}layer "{brush.layer}"')
    if brush.contents:
        lines.append(f"{_BRUSH_INDENT}contents {' '.join(brush.contents)};")
    for facet in brush.facets:
        lines.append(_BRUSH_INDENT + _render_facet(facet))
    lines.append("}")
    return lines


def _render_facet(facet: Facet) -> str:
    places = " ".join(
        "( " + " ".join(decimal_token(c) for c in point) + " )"
        for point in facet.points
    )
    line = (
        f"{places} {facet.material} {_render_projection(facet.projection)}"
        f" {facet.lightmap} {_render_projection(facet.lightmap_projection)}"
    )
    if facet.trailing:
        line = f"{line} {facet.trailing}"
    return line


def _render_projection(projection: Projection) -> str:
    return " ".join(decimal_token(number) for number in projection.as_tuple())


def _render_patch(patch: PatchSolid) -> list[str]:
    lines = [
        f"{_BRUSH_INDENT}{{",
        f'{_PATCH_INDENT}guid "{patch.guid}"',
    ]
    lines.append(f"{_PATCH_INDENT}{patch.kind}")
    lines.append(f"{_PATCH_INDENT}{{")
    # A patch's layer line lives INSIDE the inner block, first, at column 0.
    # That is where Radiant writes it (328 of 328 layered patches across the
    # shipped .map files of the mod tools, measured; e.g. brush 0 of the
    # mod tools' own zm_giant_warehouse_bridge_ramp.map).  Between the
    # container's guid and the keyword the compiler reads ``layer`` as the
    # start of a face brush and fails with "MatchToken: got 'mesh', expected
    # '('" (cod2map64, a test map line 3989).
    if patch.layer is not None:
        lines.append(f'layer "{patch.layer}"')
    if patch.contents:
        lines.append(f"{_PATCH_INDENT}contents {' '.join(patch.contents)};")
    lines.append(f"{_PATCH_INDENT}toolFlags;")
    lines.append(f"{_PATCH_FIELD_INDENT}{patch.material}")
    lines.append(f"{_PATCH_FIELD_INDENT}{patch.lightmap}")
    lines.append(
        f"{_PATCH_FIELD_INDENT}{patch.width} {patch.height}"
        f" {patch.subdivision} {patch.flavour}"
    )
    for group in patch.grid:
        lines.append(f"{_PATCH_FIELD_INDENT}(")
        for vertex in group:
            lines.append(_VERTEX_INDENT + _render_control_vertex(vertex))
        lines.append(f"{_PATCH_FIELD_INDENT})")
    lines.append(f"{_PATCH_INDENT}}}")
    lines.append(f"{_BRUSH_INDENT}}}")
    return lines


def _render_control_vertex(vertex: ControlVertex) -> str:
    parts = ["v", *(decimal_token(c) for c in vertex.position)]
    if vertex.colour is not None:
        parts.append("c")
        parts.extend(decimal_token(c) for c in vertex.colour)
    parts.append("t")
    parts.extend(
        decimal_token(c) for c in (vertex.u, vertex.v, vertex.lu, vertex.lv)
    )
    return " ".join(parts)
