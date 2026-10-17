"""Extra stock models, the night air and two surfaces for ``zm_corn_maze``.

WHAT THIS IS.  A table of stock models the corn maze ("Harvest Moon") may
place that :data:`~zmforge.recipes.props.MODEL_BOX` did not carry, plus the
map's atmosphere and the names of two brush surfaces.  Nothing here places
anything; ``corn_maze.py`` / ``corn_maze_parts.py`` decide where things go.

THE THREE CHECKS each model below passes (the same ones props.py's blocks
pass), all run:

* declared: the name is in ``blueprint/installed_assets.json``
  ``xmodels_declared``;
* measured: the box is the converted-asset catalogue's ``bbox``, copied as
  full min/max because
  several origins are off-centre (see "Off-centre origins" below);
* on disk: the binary the model's GDT entry names (``filename``) is in the
  tools tree's ``model_export``, and every image its materials' GDT
  entries name (``baseImage`` of each image a material points at, colour,
  normal and the rest) is on disk there too.

WHAT THE TOOLS TREE NEEDS.  The map uses eleven stock ``model_export``
folders from the mod tools (138 files, 330 MB)::

    props_zombie/Lab_dead_rat
    t7_beautiful_corner_props/p7_foliage_leaves_dead
    t7_beautiful_corner_props/p7_plank_wood_weathered
    t7_props/p7_boulder_rock
    t7_props/p7_debris_wood_plywood_set
    t7_props/p7_farm_tools
    t7_props/p7_foliage_grass_dry_set
    t7_props/p7_foliage_tree_albizia
    t7_props/p7_foliage_tree_olive_set
    t7_props/p7_wood_plank_rustic_set
    t7_props_zombie/p7_zm_der_plank_wood

With those folders in place every model below resolves all of its GDT
dependencies, with one exception (next paragraph).  **Link status: files
present, link unverified** -- no map build has packed any of these yet.

KNOWN LINK RISK: ``p7_foliage_tree_albizia_tall_full``.  Its binary names
three materials (``mtl_p7_foliage_tree_albizia_bark_sway``, ``..._branch_sway``
and ``..._decals_sway``) that no GDT declares: none of the 360 GDTs
the mod tools ship declares them.  The GDT
declares the non-``_sway`` names.  The install has no LOD0 for this tree
either (the GDT's ``filename`` is ``..._lod1``).  Whether the linker
accepts it is unknown until a link tries; if it refuses, drop the tree.

LOD notes.  ``p7_foliage_tree_albizia_tall_full`` is LOD1-first and
``p7_sandbag_01`` is LOD4-first by their own GDT entries, not because a file
is missing from the tools tree.  A LOD1-only hedge and a LOD2-only table link fine in
zm_dmv.

OFF-CENTRE ORIGINS (why the full min/max matters).
``p7_debris_wood_plywood_4x4_flat`` sits 200 units off its origin
(x -224.6 .. -176.6); ``p7_plank_wood_weathered_01`` .. ``_03`` sit 8 to 32
units off in y; ``zombie_lab_dead_rat`` sits 8 to 13 units off in y.  Place
these by the box centre, not by the origin.

NOT REGISTERED.  ``p7_foliage_leaves_ivy_dead_128x64`` (120 x 63 x 1) reads
as a flat panel to :func:`~zmforge.recipes.props.is_panel_model`, and
``tests/test_props.py`` pins the panel list, so it is kept in
:data:`UNREGISTERED_BOX` and not added to ``MODEL_BOX``.  The small ivy
(33 x 19 x 1) is under the panel size and is registered.  Both lie flat in
x/y (z is 1 unit): hang one on a wall by pitching it 90 degrees.

ALREADY IN MODEL_BOX and worth using here (no change needed):
``p7_foliage_tree_acacia_bush`` (82 x 64 x 45, 2,332 tris),
``p7_sign_aerofarm_01`` (231 x 4 x 59, 306 tris; its three images are in the
mod tools, checked), ``p7_sign_aerofarm_02``, ``p7_foliage_grass_tall_single_lrg``
(48 x 52 x 99, 430 tris), ``p7_foliage_grass_tall_cluster_med``,
``p7_3arc_park_leaves_corner_1`` / ``_grp_2`` (leaf litter, 35-41 tris),
``p7_crate_wood_01_short_open_lid``, ``p7_rock_sing_park_06``.

THE SKY.  Only three sky folders exist in the whole install:
``model_export/t7_skybox`` in the mod tools install holds ``mp_sector``,
``skybox_default`` and ``zm_factory`` (listed), and only eight
``skybox_*`` xmodels are declared in any GDT.  Every other night preset in
``source_data/ssi.gdt`` (``cp_infection_foy_cathedral_night``,
``cp_sh_cairo_night``, ``cp_mi_zurich_nw_ssi``, ``zm_zod`` ...) names a sky
model no GDT declares, and a preset's own sky is packed by the linker, so
none of them can link.  The two night presets that can are ``zm_factory``
and ``default_night`` (whose sky is a cube map from the same
``t7_skybox/zm_factory`` folder).  ``default_night`` is not clearly brighter:
its moon colour is whiter (sRGB 0.79 1 1 against 0.53 0.69 0.69) but 0.2 stop
weaker, and its sky, measured off the ``.exr`` files times the material's
``skyScaleRGB * 2**skyStops``, comes out about 2.7 times dimmer (0.017
against 0.046; how the engine combines those two fields is unverified).
So :data:`HARVEST_NIGHT` stays on The Giant's preset and sky.  A brighter
night has to come from the lamps and the wall surface, not the sky.
"""

from __future__ import annotations

from ..atmosphere import GIANT_NIGHT_SKY, Atmosphere
from .props import MODEL_BOX

__all__ = [
    "EXTRA_BOX",
    "EXTRA_TRIS",
    "UNREGISTERED_BOX",
    "WALK_THROUGH",
    "SOLID",
    "HARVEST_NIGHT",
    "CORN_WALL_MATERIAL",
    "BOARD_MATERIAL",
    "NEEDED_FOLDERS",
]

Box = tuple[tuple[float, float, float], tuple[float, float, float]]

#: Bounding boxes, measured from each model's converted geometry, of the
#: extra models registered into ``MODEL_BOX``.  Size and triangles in the comment.
EXTRA_BOX: dict[str, Box] = {
    # trees (solid)
    "p7_foliage_tree_albizia_tall_full": ((-282.839, -269.59, -0.001), (288.115, 278.096, 763.581)),  # 571x548x764, canopy
    "p7_foliage_tree_olive_small": ((-45.473, -31.595, -0.007), (29.877, 56.45, 96.134)),  # 75x88x96
    # dead ivy, dry grass, rock (walk-through)
    "p7_foliage_leaves_ivy_dead_32x16": ((-16.426, -9.944, -0.046), (16.834, 8.927, 0.997)),  # 33x19x1
    "p7_foliage_grass_dry_01": ((-20.194, -23.679, -0.325), (19.632, 25.635, 44.224)),  # 40x49x45
    "p7_foliage_grass_dry_03": ((-13.478, -12.169, 0.0), (13.478, 12.221, 14.484)),  # 27x24x14
    "p7_boulder_rock_05": ((-9.895, -5.807, -3.328), (9.606, 5.878, 3.286)),  # 20x12x7
    # boards and planks for signs and fences (walk-through)
    "p7_plank_wood_weathered_01": ((-24.164, -32.0, -0.167), (24.164, -28.0, 0.58)),  # 48x4x1
    "p7_plank_wood_weathered_02": ((-22.25, -22.0, 0.0), (22.25, -18.0, 0.58)),  # 44x4x1
    "p7_plank_wood_weathered_03": ((-22.25, -12.0, -0.095), (22.25, -8.0, 0.777)),  # 44x4x1
    "p7_plank_wood_weathered_04": ((-18.007, -2.318, -0.255), (18.007, 2.318, 0.526)),  # 36x5x1
    "p7_wood_plank_rustic01_2x12x96": ((-52.076, -6.127, -1.125), (52.024, 6.127, 1.125)),  # 104x12x2
    "p7_wood_plank_rustic01_2x16x48": ((-27.122, -8.212, -1.493), (26.367, 8.212, 1.493)),  # 53x16x3
    "p7_zm_der_plank_wood_2x12x96_dmg": ((-48.24, -6.302, -1.01), (48.526, 6.314, 1.031)),  # 97x13x2
    "p7_debris_wood_plywood_4x4_flat": ((-224.596, -24.0, -0.021), (-176.596, 24.0, 0.903)),  # 48x48x1, off-centre
    # farm and Halloween clutter (walk-through)
    "p7_farm_tools_hammer": ((-3.96, -11.24, 0.064), (4.434, 11.16, 2.202)),  # 8x22x2
    "p7_sandbag_01": ((-10.043, -15.643, 0.089), (9.765, 19.706, 9.668)),  # 20x35x10, burlap sack
    "zombie_lab_dead_rat": ((-4.237, 8.29, -0.149), (9.214, 13.115, 2.85)),  # 13x5x3
}

#: Kept out of ``MODEL_BOX`` on purpose (see the module docstring, "NOT
#: REGISTERED"): registering it would add it to the pinned flat-panel list.
UNREGISTERED_BOX: dict[str, Box] = {
    "p7_foliage_leaves_ivy_dead_128x64": ((-62.459, -31.45, -0.053), (57.518, 31.916, 1.168)),  # 120x63x1
}

#: Catalogue triangle counts (the mesh the GDT's ``filename`` names).
EXTRA_TRIS: dict[str, int] = {
    "p7_foliage_tree_albizia_tall_full": 10_851,
    "p7_foliage_tree_olive_small": 14_102,
    "p7_foliage_leaves_ivy_dead_128x64": 96,
    "p7_foliage_leaves_ivy_dead_32x16": 64,
    "p7_foliage_grass_dry_01": 946,
    "p7_foliage_grass_dry_03": 470,
    "p7_boulder_rock_05": 470,
    "p7_plank_wood_weathered_01": 96,
    "p7_plank_wood_weathered_02": 68,
    "p7_plank_wood_weathered_03": 140,
    "p7_plank_wood_weathered_04": 128,
    "p7_wood_plank_rustic01_2x12x96": 861,
    "p7_wood_plank_rustic01_2x16x48": 615,
    "p7_zm_der_plank_wood_2x12x96_dmg": 1_188,
    "p7_debris_wood_plywood_4x4_flat": 412,
    "p7_farm_tools_hammer": 372,
    "p7_sandbag_01": 258,
    "zombie_lab_dead_rat": 1_010,
}

#: The two trees stop the player.  Their boxes are the canopy, far wider than
#: the trunk (the albizia is 571 across): keep paths clear of the trunk, not
#: of the whole box.
SOLID: frozenset[str] = frozenset({"p7_foliage_tree_albizia_tall_full", "p7_foliage_tree_olive_small"})

#: Everything else is placed walk-through: foliage, ivy, boards flat to a
#: wall, and small clutter.
WALK_THROUGH: frozenset[str] = frozenset((set(EXTRA_BOX) | set(UNREGISTERED_BOX)) - SOLID)

#: The stock mod tools folders these models need in the tools tree (see the
#: module docstring).
NEEDED_FOLDERS: tuple[str, ...] = (
    "model_export/props_zombie/Lab_dead_rat",
    "model_export/t7_beautiful_corner_props/p7_foliage_leaves_dead",
    "model_export/t7_beautiful_corner_props/p7_plank_wood_weathered",
    "model_export/t7_props/p7_boulder_rock",
    "model_export/t7_props/p7_debris_wood_plywood_set",
    "model_export/t7_props/p7_farm_tools",
    "model_export/t7_props/p7_foliage_grass_dry_set",
    "model_export/t7_props/p7_foliage_tree_albizia",
    "model_export/t7_props/p7_foliage_tree_olive_set",
    "model_export/t7_props/p7_wood_plank_rustic_set",
    "model_export/t7_props_zombie/p7_zm_der_plank_wood",
)

for _name, _box in EXTRA_BOX.items():
    MODEL_BOX.setdefault(_name, _box)  # type: ignore[attr-defined]

#: The corn maze's air.  The Giant's night preset and sky, because they are
#: the only night pair the install can link that is not dimmer (module
#: docstring, "THE SKY").  The ground fog is kept as it was:
#: ``zm_factory_afog`` is atmospheric scattering only and draws next to
#: nothing on a map this size (``atmosphere`` module docstring), so swapping
#: it for ``default`` would change nothing visible.  No lit fog: the only two
#: shipped lit fogs are The Giant's cold blue ones, which add haze, not light.
#: To try one anyway, set ``lit_fog="zm_factory_volumetric"`` (same as
#: ``atmosphere.NIGHT_LIT_GROUND_FOG``).
HARVEST_NIGHT = Atmosphere(
    sun_preset="zm_factory",
    skybox=GIANT_NIGHT_SKY,
    fog="zm_factory_afog",
)

#: Corn wall surface: straw-coloured.  ``t7_rock_sand_crumbled_medium_golden``
#: is in ``materials.SURFACE_CATALOGUE`` (it has compiled on shipped map
#: sources).  Its colour image, times its GDT ``colorTint`` (0.85 0.74 0.58),
#: averages sRGB 0.54 0.43 0.29, luminance 0.44, against 0.29 0.30 0.19,
#: luminance 0.29, for the lawn ``t7_grass_lawn_medium_small_green`` the walls
#: use now: about 1.5 times the albedo, and warm instead of olive (means
#: measured off the mod tools' ``texture_assets/t7_materials`` .tif
#: files).  Not seen in game yet: at wall scale the crumbled-sand pattern may
#: read as sandstone rather than dry stalks, or as a quarry between the
#: stalks, so the walls
#: stay lawn (``corn_maze`` surfaces note).
CORN_WALL_MATERIAL = "t7_rock_sand_crumbled_medium_golden"

#: Sign-board surface: ``t7_wood_panel_01`` (``materials.INSTALL_SURFACES``,
#: linked in zm_dmv), mean sRGB 0.57 0.44 0.36, luminance 0.46.  The darker
#: barn-board alternative is ``t7_wood_planks_worn`` (``SURFACE_CATALOGUE``,
#: luminance 0.33).  No painted-wood surface is catalogued.
BOARD_MATERIAL = "t7_wood_panel_01"
