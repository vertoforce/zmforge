"""Game texture helpers.

``gdt`` writes the asset-database entries the linker needs for a texture; it
only emits text and reads nothing from the game install.  The names are bound
lazily (PEP 562), so importing the package costs nothing until a name is used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers, which are not lazy
    from .gdt import TextureAsset, gdt_document

#: Public name -> the submodule that defines it.  ``__all__`` is derived from
#: this so the two cannot drift apart.
_SOURCES: dict[str, str] = {
    "TextureAsset": "gdt",
    "gdt_document": "gdt",
}

__all__ = [
    "TextureAsset",
    "gdt_document",
]


def __getattr__(name: str):
    """Import the submodule that owns ``name``, on first use only.

    The binding is cached in the module globals, so the second access costs a
    normal attribute lookup and nothing here runs again.
    """
    where = _SOURCES.get(name)
    if where is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{where}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
