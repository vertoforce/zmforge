"""Reading and writing Radiant ``.map`` source text.

This package is the only part of zmforge that knows the file format exists.
Everything above it works with the document model in :mod:`.document`; the
blueprint and emit layers never touch a string of map text.

    >>> from zmforge import mapsource
    >>> doc = mapsource.read("zm_example.map")      # doctest: +SKIP
    >>> doc.worldspawn.put("gravity", "800")        # doctest: +SKIP
    >>> mapsource.write("zm_example.map", doc)      # doctest: +SKIP

:func:`read` never fails on encoding and records the file's line ending on the
document, so :func:`write` puts a CRLF file back the way it found it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .document import (
    DEFAULT_LIGHTMAP,
    DEFAULT_SURFACE,
    GUID_RE,
    LIGHTMAP_MATERIAL,
    BrushSolid,
    ControlVertex,
    Document,
    Entity,
    Facet,
    LayerDeclaration,
    OpaqueSolid,
    PatchSolid,
    Projection,
    format_guid,
)
from .reader import parse_map_text
from .scalars import NUMBER_RE, Scalar, decimal_token, parse_scalar
from .writer import render_map_text

__all__ = [
    "read",
    "write",
    "parse_map_text",
    "render_map_text",
    "decimal_token",
    "parse_scalar",
    "Scalar",
    "NUMBER_RE",
    "GUID_RE",
    "format_guid",
    "Projection",
    "DEFAULT_SURFACE",
    "DEFAULT_LIGHTMAP",
    "LIGHTMAP_MATERIAL",
    "Facet",
    "BrushSolid",
    "ControlVertex",
    "PatchSolid",
    "OpaqueSolid",
    "Entity",
    "LayerDeclaration",
    "Document",
]

_BOM = "﻿"


def read(path: str | os.PathLike[str]) -> Document:
    """Read a ``.map`` file.

    Decoding is lossy on purpose: one undecodable byte in a mapper's file must
    not cost the caller the other 60 000 lines.  The dominant line ending is
    detected and stored on the document; a file that mixes endings gets a note
    and is normalised to whichever ending it uses most.
    """
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    notes: list[str] = []
    if text.startswith(_BOM):
        text = text[len(_BOM) :]
        notes.append("dropped a byte-order mark; the file is written back without one")

    newline, mixed = _dominant_newline(text)
    if mixed:
        notes.append(
            f"mixed line endings; writing every line with {newline!r} from now on"
        )

    doc = parse_map_text(text, newline=newline)
    doc.notes[:0] = notes
    return doc


def write(path: str | os.PathLike[str], doc: Document) -> None:
    """Write ``doc`` to ``path`` atomically.

    The text lands in a temporary file beside the target and is renamed over it,
    so an interrupted write can never leave a mapper with half a map.
    """
    target = Path(path)
    payload = render_map_text(doc).encode("utf-8")
    handle, temporary = tempfile.mkstemp(
        dir=str(target.parent or "."), prefix=target.name, suffix=".part"
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _dominant_newline(text: str) -> tuple[str, bool]:
    """The ending the file mostly uses, and whether it uses more than one."""
    windows = text.count("\r\n")
    unix = text.count("\n") - windows
    classic = text.count("\r") - windows
    counts = (("\r\n", windows), ("\n", unix), ("\r", classic))
    used = [ending for ending, count in counts if count]
    if not used:
        return "\n", False
    best = max(counts, key=lambda item: item[1])[0]
    return best, len(used) > 1
