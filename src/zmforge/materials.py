"""Material names and the catalogue of names known to compile clean.

The catalogue is data, not behaviour: the names are game asset names fixed by
the shipped asset database (spec section 2.9), so they are spelled here
exactly and never derived.  A name outside the catalogue is a ``verify``
error, unless it is one of our own staged materials
(:data:`PIPELINE_MATERIAL_PREFIXES`: a warning normally, an error in strict
mode) or the known-benign prefab name, because
the compiler only prints ``WARNING: Material '<name>' is missing`` and still
exits 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .errors import UnknownMaterial
from .spatial import Side

__all__ = [
    "Material",
    "FaceMaterials",
    "CAULK",
    "SKY",
    "CLIP",
    "TRIGGER",
    "TOOL_MATERIALS",
    "SURFACE_CATALOGUE",
    "INSTALL_SURFACES",
    "CEMETERY_SURFACES",
    "BENIGN_MISSING",
    "PIPELINE_MATERIAL_PREFIXES",
    "PLACEHOLDER_IMAGES",
    "is_pipeline_material",
    "is_catalogued",
    "assert_catalogued",
    "chalk_material_for",
]


@dataclass(frozen=True, slots=True)
class Material:
    """A material asset name, and optionally how large to lay it.

    ``scale`` is how many world units one tile of the texture spans across a
    face, and ``scale_v`` how many it spans up it: the first two numbers of the
    face line's surface projection (spec 1.5).  ``None`` means the editor's
    default of 64, which is right for art authored for the game and wrong for a
    texture cut from a photograph of a real surface: a tile that depicts 20
    units of real wall has to be told to cover 20 units, or the grain reads at
    the wrong size.  It is on the material rather than on the face because the
    size belongs to the image, not to the wall.

    The two axes are separate because a tiling surface and a picture are laid
    differently.  A photographed wall tiles, so one square number repeats it;
    a poster, a sign or a painting is one rectangle W x H units that must show
    its image once and not repeat, which is the scale pair (W, H) and cannot be
    said with a single number unless the image happens to be square.
    ``scale_v`` left at ``None`` falls back to ``scale``, so every square case
    is written exactly as before.
    """

    name: str
    scale: float | None = None
    scale_v: float | None = None

    def __post_init__(self) -> None:
        if not self.name or any(ch.isspace() for ch in self.name):
            raise ValueError(f"bad material name {self.name!r}")
        for axis, value in (("u", self.scale), ("v", self.scale_v)):
            if value is not None and value <= 0.0:
                raise ValueError(f"texture {axis} scale must be positive, got {value}")
        if self.scale is None:
            if self.scale_v is not None:
                raise ValueError(
                    "a v scale needs a u scale; the default projection is both "
                    "axes or neither"
                )
            return
        # Resolve the fallback once, here, so nothing downstream has to know
        # about it: after construction the pair is always either both None or
        # both set.
        if self.scale_v is None:
            object.__setattr__(self, "scale_v", self.scale)

    def __str__(self) -> str:  # so it can be dropped straight into a face line
        return self.name

    def sized(self, u: float, v: float | None = None) -> "Material":
        """The same material laid at ``u`` units across and ``v`` units up.

        One argument is the square case, unchanged: ``sized(64)`` is a tile 64
        units on a side.
        """
        return Material(self.name, u, v)

    @classmethod
    def of(cls, value: "Material | str") -> "Material":
        return value if isinstance(value, Material) else cls(str(value))


# Tool materials.  These are compiler/editor surfaces, not art.
CAULK = Material("caulk")
CLIP = Material("clip")
TRIGGER = Material("trigger")
SKY = Material("sky")
UMBRA_VOLUME = Material("umbra_volume")
SUN_VOLUME = Material("sun_volume")
VOLUME = Material("volume")
#: The texture on a ``volume_worldfog`` brush (``zm_giant_light.map:4366``).
FOG_VOLUME = Material("fog")
#: The texture on a ``volume_litfog`` brush (``zm_giant_light.map:4159``).
LITFOG_VOLUME = Material("litfog_volume")

TOOL_MATERIALS: frozenset[str] = frozenset(
    {
        CAULK.name,
        CLIP.name,
        TRIGGER.name,
        SKY.name,
        UMBRA_VOLUME.name,
        SUN_VOLUME.name,
        VOLUME.name,
        FOG_VOLUME.name,
        LITFOG_VOLUME.name,
    }
)

#: Art materials verified on shipped map sources (spec section 2.9).  Each is
#: a name that has compiled without a missing-material warning.
SURFACE_CATALOGUE: frozenset[str] = frozenset(
    {
        "t7_concrete_trowelled",
        "t7_concrete_wall_dark_01",
        "t7_concrete_pebbles_cracked",
        "t7_concrete_tiles_2x2_dirty_01",
        "t7_brick_worn_heavy_grout_red",
        "t7_wood_planks_worn",
        "t7_metal_worn_iron_dark",
        "t7_metal_rust_ceiling_01",
        "t7_zm_der_tile_hexagon",
        "t7_dirt_grassy_forest_ground",
        "t7_rock_sand_crumbled_medium_golden",
        "t7_snow_powder_01",
    }
)

#: Stock surfaces picked off the install for ``zm_dmv``'s interiors and
#: frontage.  Each one is a ``material.gdf`` entry in one of the
#: install's ``texture_assets`` GDTs whose colour ``.tif`` exists on disk in
#: the mod tools install, of type ``lit``, ``lit_detail`` or
#: ``lit_plus`` (the three types the names above already compile as), and --
#: all but ``t7_asphalt_advanced_strips`` -- with no detail map or with one of
#: the detail maps a name above already links with.  The asphalt's detail map
#: (``i_t7_detail_asphalt_02``) is the sibling of the grass ground's
#: ``i_t7_detail_asphalt_01`` and has not been linked on its own.
#:
#: Measured on a Windows link of zm_dmv with all thirty laid: the
#: compile's only ``Material ... is missing`` line was the benign prefab name
#: below, the link verdict was ok with no ``ERROR:`` line, and zm_dmv.ff came
#: out at 29,607,104 bytes -- so the asphalt's detail image links too.  Kept
#: as its own set so the provenance stays readable; :func:`is_catalogued`
#: accepts both.
INSTALL_SURFACES: frozenset[str] = frozenset(
    {
        # floors
        "t7_linoleum_floor_tile_square",
        "t7_ceramic_tiles_16x16",
        "t7_ceramic_tile_large_white",
        "t7_ceramic_tiles_6x6_dirty_01",
        "t7_stone_travertine_tiles",
        # walls, trim and ceilings
        "t7_plaster_smooth_light_01",
        "t7_plaster_smooth_dirty_01",
        "t7_concrete_worn_painted_white",
        "t7_ceramic_tile_shower_white",
        "t7_wood_panel_01",
        "t7_wood_veneer_sugarpine_matte",
        "t7_plastic_rubber_trim",
        "t7_plastic_molding_trim_white",
        "t7_plastic_panels_white",
        "t7_plastic_ceiling_corrugated_panel",
        "t7_metal_panel_white_perforated",
        "t7_metal_panel_horizontal_painted",
        "t7_metal_panels_4x1",
        "t7_metal_frame_trim_01",
        "t7_metal_black_trim_01",
        "t7_glass_plain_opaque",
        # outside
        "t7_brick_worn_red",
        "t7_concrete_floor_trim_01",
        "t7_concrete_trim_beveled_03",
        "t7_concrete_slabs_interlocked",
        "t7_concrete_sidewalk_2x2_01",
        "t7_street_concrete_curb_01a",
        "t7_asphalt_advanced_strips",
        "t7_grass_lawn_medium_small_green",
        "t7_rubber_roof_granular",
    }
)

#: Outdoor ground and crypt floor surfaces picked off the install for
#: ``zm_cemetery``.  Same test as :data:`INSTALL_SURFACES`: a
#: ``material.gdf`` entry in the install's ``texture_assets`` GDTs (``t7_dirt``,
#: ``t7_mud``, ``t7_rock``, ``t7_stone``), type ``lit`` or ``lit_plus``, its
#: colour ``.tif`` present under ``texture_assets/t7_materials`` on the local
#: Wine tools copy, and no detail map or the one the grassy ground already
#: links with (``i_t7_detail_asphalt_01``, for the rocky dirt).  Linked for the
#: first time by the zm_cemetery build.
CEMETERY_SURFACES: frozenset[str] = frozenset(
    {
        "t7_dirt_rocky_01",
        "t7_mud_ground_dirt_wet_01",
        "t7_rock_cobblestone_round",
        "t7_stone_flagstone_floor",
    }
)

#: Missing-material warnings that are known to be harmless.  The stock
#: starting mystery-box prefab references this name and the compiler prints the
#: warning three times per build; it is not offered as a choice.
#: Weathered stone for outdoor walls, headstones and benches, picked off the
#: install for zm_cemetery: the flat red brick and the tan travertine read as cardboard in the
#: hero shot.  Same test as :data:`CEMETERY_SURFACES`: a ``lit`` material in
#: ``texture_assets/t7_stone.gdt`` or ``t7_concrete.gdt`` with its colour
#: ``.tif`` present in the mod tools install and no detail map.  zm_cemetery
#: links all of them.
LOOK_SURFACES: frozenset[str] = frozenset(
    {
        "t7_concrete_bunker_layered_02",   # layered, streaked old masonry: walls
        "t7_stone_slate_tile_grey",        # dark grey coursed blocks: piers, copings
        "t7_stone_marble_tile_4x4",        # speckled grey granite: headstones, benches
        # Weathered mixes for zm_cemetery.
        "t7_brick_worn_heavy_grout_brown_wet",  # old brown brick, streaked wet and green
        "t7_brick_worn_dirty_red_wet",          # worn red brick, wet
        "t7_concrete_wall_weathered_01_wet",    # stained wet stone
        "t7_concrete_bare_dark_01_wet",         # dark wet stone
    }
)

BENIGN_MISSING: frozenset[str] = frozenset({"jun_art_wood_plywood_dark03"})

#: Name prefixes of the materials our own pipeline writes a GDT for:
#: ``zmf_*`` for the prop, wall-art and texture lanes.  Not in
#: the stock catalogue, but they are proven by the build that stages them, so
#: ``Z12`` only warns on them.  Any other uncatalogued brush material is a
#: ``Z12`` error: it is the magenta error texture in game.
PIPELINE_MATERIAL_PREFIXES: tuple[str, ...] = ("zmf_",)

#: Placeholder images a stock material can name as its colour map.  The
#: material exists and links, but Radiant prints ``Failed to load image
#: 'deleteme' for material '<m>'`` and the game draws it bright magenta with
#: black ``DELETE`` lettering: ``mtl_p_ger_metal_desk``, the only material of
#: ``p7_desk_metal_old_01`` (zm_cemetery's shed desk and 22 desks on a
#: test map).  :func:`zmforge.blueprint.installed.scan_unlinkable`
#: refuses every model using one, and the bake verdict fails on the line.
PLACEHOLDER_IMAGES: frozenset[str] = frozenset({"deleteme"})


def is_pipeline_material(name: "Material | str") -> bool:
    """Whether *name* is one of our own staged materials (see
    :data:`PIPELINE_MATERIAL_PREFIXES`)."""
    return Material.of(name).name.startswith(PIPELINE_MATERIAL_PREFIXES)


def is_catalogued(name: "Material | str") -> bool:
    text = Material.of(name).name
    return (
        text in SURFACE_CATALOGUE
        or text in INSTALL_SURFACES
        or text in CEMETERY_SURFACES
        or text in LOOK_SURFACES
        or text in TOOL_MATERIALS
        or text in prop_library_surfaces()
    )


def prop_library_surfaces() -> frozenset[str]:
    """Brush surfaces the prop library makes and registers with its props
    (a ``PropMaterial`` in a prop's ``extra_materials`` naming no mesh faces,
    e.g. ``zmf_corn_wall``): the prop install step installs them wherever the
    props go, so a map that places the props has them.  Proven for
    ``zmf_corn_wall`` by the zm_corn_maze local link."""
    from .props.library import PROPS

    return frozenset(m.asset for p in PROPS for m in p.extra_materials if not m.faces)


def assert_catalogued(name: "Material | str") -> Material:
    material = Material.of(name)
    if not is_catalogued(material):
        raise UnknownMaterial(
            f"{material.name!r} is not in the known-clean catalogue; "
            "the compiler will warn and the surface will render as the error texture"
        )
    return material


def chalk_material_for(weapon_name: str) -> Material:
    """The wall-buy chalk decal material for a **weapon name**.

    Applied through ``modeloverridematerial`` on a ``misc_volume_decal``, never
    on a brush face (spec section 4.10).

    The argument is the game's weapon name (the spec's worked example is
    ``t7_zm_chalk_buy_kuda``), **not** the spawnable-weapon prefab slug.  The
    two are different namespaces and the spec does not say so: a compile
    printed ``WARNING: Material 't7_zm_chalk_buy_ar_standard' is
    missing`` (and the same for ``smg_standard`` and ``pistol_burst``) for
    names built from the slug.  No slug-to-weapon-name mapping has been
    verified, so callers must supply the material themselves.
    """
    return Material(f"t7_zm_chalk_buy_{weapon_name}")


@dataclass(frozen=True, slots=True)
class FaceMaterials:
    """What material each side of a box gets.

    ``default`` covers sides not named in ``per_side``.  The hull-brush rule of
    spec section 2.2 is expressed with :meth:`only_visible_on`: one side carries
    the art and the other five carry ``caulk``, which is what stops an interior
    wall rendering as the skybox.
    """

    default: Material = CAULK
    per_side: Mapping[Side, Material] = field(default_factory=dict)

    @classmethod
    def uniform(cls, material: "Material | str") -> "FaceMaterials":
        return cls(default=Material.of(material), per_side={})

    @classmethod
    def only_visible_on(
        cls, side: Side, material: "Material | str", hidden: "Material | str" = CAULK
    ) -> "FaceMaterials":
        return cls(default=Material.of(hidden), per_side={side: Material.of(material)})

    def on(self, side: Side) -> Material:
        return self.per_side.get(side, self.default)

    def names(self) -> set[str]:
        return {self.default.name} | {m.name for m in self.per_side.values()}
