"""Stable ids and the GUIDs derived from them.

Every element carries an id the caller chose or the blueprint assigned.  A
re-run with the same inputs must produce the same file, so GUIDs are derived
from the map's seed plus the element id plus an ordinal within that element,
not drawn from the system entropy pool.  Random UUIDs appear only where
nothing identifies the thing being written.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from ..errors import DuplicateId

__all__ = ["Identity", "IdAllocator", "format_guid"]


def format_guid(value: uuid.UUID) -> str:
    """Braced, upper-case, 8-4-4-4-12 — the form BO3 entities carry."""
    return "{" + str(value).upper() + "}"


@dataclass(frozen=True, slots=True)
class Identity:
    """Derives a map's GUIDs deterministically from a seed."""

    seed: str

    def uuid_for(self, element_id: str, ordinal: int = 0) -> uuid.UUID:
        digest = hashlib.sha256(
            f"{self.seed}\x1f{element_id}\x1f{ordinal}".encode("utf-8")
        ).digest()
        # Stamp version 4 / variant 10 so the value is a well-formed UUID.
        raw = bytearray(digest[:16])
        raw[6] = (raw[6] & 0x0F) | 0x40
        raw[8] = (raw[8] & 0x3F) | 0x80
        return uuid.UUID(bytes=bytes(raw))

    def guid_for(self, element_id: str, ordinal: int = 0) -> str:
        return format_guid(self.uuid_for(element_id, ordinal))


@dataclass
class IdAllocator:
    """Hands out unique element ids and rejects collisions."""

    taken: set[str] = field(default_factory=set)
    counters: dict[str, int] = field(default_factory=dict)

    def claim(self, wanted: str) -> str:
        if wanted in self.taken:
            raise DuplicateId(f"element id {wanted!r} is already in use")
        self.taken.add(wanted)
        return wanted

    def next_for(self, kind: str, wanted: str | None = None) -> str:
        if wanted is not None:
            return self.claim(wanted)
        index = self.counters.get(kind, 0)
        while True:
            candidate = f"{kind}_{index}"
            index += 1
            if candidate not in self.taken:
                self.counters[kind] = index
                self.taken.add(candidate)
                return candidate
