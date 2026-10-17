"""Third-party models into a map: download, convert, register, place.

The chain, and which module owns each link:

===========================  ==========================================
``library``                  which props, from which kit, under which licence
``fetch``                    the kit archive, cached outside the repo
``wavefront``                the ``.obj`` in
``xmodel``                   game axes, game units, and ``.XMODEL_EXPORT`` out
``textures``                 the one source image per kit
``gdt``                      the ``xmodel`` asset-database entity
``build``                    all of the above into a staging tree
``place``                    ``misc_model`` entities into a map that exists
===========================  ==========================================

The one step that is not here is ``export2bin``, which turns the text export
into the ``.XMODEL_BIN`` the GDT points at.  It is a Windows binary that ships
with the mod tools, so it runs in the install step (under Wine,
:mod:`zmforge.props.xmodel_bin` writes the same bytes instead).
"""

from __future__ import annotations

from .build import BuildResult, BuiltProp, build
from .gdt import XModelAsset, gdt_document, xmodel_entry
from .library import KITS, PROPS, Kit, Prop, credits_markdown, prop
from .place import Placement, apply, floor_slabs, placed, scatter
from .wavefront import Mesh, Triangle, read_obj
from .xmodel import MaterialBinding, decimate, to_game_space, xmodel_export_text

__all__ = [
    "BuildResult",
    "BuiltProp",
    "build",
    "KITS",
    "PROPS",
    "Kit",
    "Prop",
    "credits_markdown",
    "prop",
    "Placement",
    "apply",
    "floor_slabs",
    "placed",
    "scatter",
    "Mesh",
    "Triangle",
    "read_obj",
    "MaterialBinding",
    "decimate",
    "to_game_space",
    "xmodel_export_text",
    "XModelAsset",
    "gdt_document",
    "xmodel_entry",
]
