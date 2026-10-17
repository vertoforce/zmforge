"""Emit the asset-database text the linker needs for a custom texture.

A ``.gdt`` is the mod tools' plain-text asset database.  One entry per asset,
keyed by asset name, tagged with the ``.gdf`` definition it follows.  The
material definition carries 909 keys, almost all of them defaults for shader
features this surface does not use (ocean foam, cloud layers, tree canopy
sway), and the linker is unforgiving about a missing one -- so the two
templates in ``templates/`` are the entries from the pair that the linker
already accepted on the mod tools install, verbatim, with only the handful of fields
that must vary replaced by ``@@slot@@`` markers.

:func:`gdt_document` rendered with the original field values reproduces that
accepted file byte for byte; a test asserts it.

Custom source images live in ``texture_assets/<map>/`` and ``baseImage`` is
the path from the mod tools root **including** the ``texture_assets``
component, with backslashes doubled -- e.g.
``texture_assets\\\\zm_mymap\\\\wall_c.tif``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "TextureAsset",
    "NormalAsset",
    "gdt_document",
    "image_asset_name",
    "base_image_path",
]

_TEMPLATES = Path(__file__).parent / "templates"
_SLOT = re.compile(r"@@([a-z_]+)@@")


def _render(template: str, values: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"template slot {key!r} has no value")
        return values[key]

    out = _SLOT.sub(repl, template)
    if "@@" in out:
        raise AssertionError("unfilled template slot")
    return out


def image_asset_name(material: str) -> str:
    """``rs_shed_wall`` -> ``i_rs_shed_wall_c``, the convention the install uses."""
    return f"i_{material}_c"


def base_image_path(map_name: str, file_stem: str) -> str:
    """The ``baseImage`` value for ``texture_assets/<map_name>/<file_stem>.tif``."""
    return f"texture_assets\\\\{map_name}\\\\{file_stem}.tif"


@dataclass(frozen=True)
class TextureAsset:
    """One material plus the colour image it points at.

    WHAT THE SURFACE-DETAIL BINDINGS DO, AND WHY THE DEFAULTS CHANGED.
    ``materialType`` is ``lit_detail``, so the visible micro-structure of the
    surface comes from ``detail_map`` and ``normal_map``, not from the
    photograph: the colour map supplies the tint and the large shapes, and the
    detail map supplies everything finer than a texel.  That matters more than
    it sounds for a photographed surface, because a smooth painted wall has
    almost no fine structure of its own to compete with: a painted wall or
    ceiling tile carries well under 1 / 255 of luminance at the 1-pixel
    octave, a carpet several times that.  With a cracked-plaster normal map
    and a concrete detail map bound to such surfaces, a room renders as
    cracked concrete with a tint -- the photograph contributes a colour and
    nothing else.

    So the defaults are now **neutral**: no normal map, no occlusion map, and
    a drywall detail map.  Every value here is one observed on a shipped
    material in the mod tools, never invented:

    * empty ``normalMap`` and ``occMap`` are what ``t7_cloth_carpet_cairo_01``
      (``t7_cloth.gdt``) carries -- a surface with no relief of its own leaves
      them blank rather than borrowing another surface's;
    * ``i_t7_detail_drywall_01`` is a shipped detail map (used by 4 stock
      materials against ``i_t7_detail_concrete_02``'s 16);
    * ``plaster`` is a real ``surfaceType`` (18 stock materials).

    A surface that *is* concrete should say so explicitly.
    """

    material: str  # e.g. "rs_shed_wall" -- how the .map face line spells it
    file_stem: str  # e.g. "shed_wall_c" -- the .tif under texture_assets/<map>/
    surface_type: str = "plaster"
    gloss_surface_type: str = "plaster"
    normal_map: str = ""
    occ_map: str = ""
    detail_map: str = "i_t7_detail_drywall_01"
    usage: str = "interior wall"
    #: ``lit_detail`` for every surface so far; ``lit_emissive`` for a glowing
    #: prop screen, which also sets ``emissive_map`` (``colorMap00``) and
    #: ``scale_rgb`` -- the stock emissive screens' layout (t7_props gdts).
    material_type: str = "lit_detail"
    emissive_map: str = ""
    scale_rgb: str = "8"
    # Set by the recipe; carried here only so the manifest can record it.
    notes: str = ""

    @property
    def image(self) -> str:
        return image_asset_name(self.material)

    def entries(self, map_name: str) -> str:
        img = _render(
            (_TEMPLATES / "image_entry.gdt.tmpl").read_text(),
            {"image_name": self.image, "base_image": base_image_path(map_name, self.file_stem)},
        )
        mat = _render(
            (_TEMPLATES / "material_entry.gdt.tmpl").read_text(),
            {
                "material_name": self.material,
                "image_name": self.image,
                "surface_type": self.surface_type,
                "gloss_surface_type": self.gloss_surface_type,
                "normal_map": self.normal_map,
                "occ_map": self.occ_map,
                "detail_map": self.detail_map,
                "usage": self.usage,
                "material_type": self.material_type,
                "emissive_map": self.emissive_map,
                "scale_rgb": self.scale_rgb,
            },
        )
        return img + mat


@dataclass(frozen=True)
class NormalAsset:
    """A normal-map image asset on its own, with no material of its own.

    WHY this exists: ``materialType`` is ``lit_detail``, so everything finer
    than a texel comes from the material's ``detail_map``, which is an
    **image** asset carrying ``semantic normalMap``.  A surface that borrows a
    stock one gets that stock surface's micro-relief -- a photographed room
    renders as cracked concrete for exactly this reason -- and the mod tools
    install carries the source ``.tif`` for only three of the shipped detail
    normals anyway, so a map that wants paper, canvas or painted board has to
    bring its own.

    The template is the shipped ``i_t7_detail_concrete_02`` entry from
    ``texture_assets/t7_detail_material.gdt`` verbatim -- an entry the linker
    has accepted -- with the name and ``baseImage`` replaced.  Its
    ``coreSemantic`` is ``Normal``, ``semantic`` is ``normalMap``,
    ``compressionMethod`` is ``compressed`` (not ``compressed no alpha``) and
    ``mipBase`` is ``1/1``: all four differ from a colour image, which is why
    this is a second template rather than a flag on the first.
    """

    name: str  # e.g. "i_zmf_detail_paper_n" -- what detail_map points at
    file_stem: str  # e.g. "detail_paper_n" -- the .tif under texture_assets/<map>/

    @property
    def image(self) -> str:
        return self.name

    def entries(self, map_name: str) -> str:
        return _render(
            (_TEMPLATES / "normal_image_entry.gdt.tmpl").read_text(),
            {"image_name": self.name, "base_image": base_image_path(map_name, self.file_stem)},
        )

    @property
    def material(self) -> str:
        """The name a duplicate check keys on; a normal has no material."""
        return self.name


def gdt_document(map_name: str, assets: "list[TextureAsset | NormalAsset]") -> str:
    """The whole ``.gdt`` file: one brace-wrapped list of entries, LF endings."""
    if not assets:
        raise ValueError("no assets")
    names = [a.material for a in assets]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate material names in {names}")
    return "{\n" + "".join(a.entries(map_name) for a in assets) + "}\n"
