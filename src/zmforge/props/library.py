"""Which third-party props we ship, where each came from, and under what licence.

Every entry carries the download URL, the licence and the quoted licence terms
that were read at the time, because a published map has to be able to carry its
own credits: :func:`credits_markdown` renders exactly that, and the build drops
it into the map's own directory.

Sources are restricted on purpose to public-domain game-asset kits.  Paid
marketplaces are excluded -- their licences forbid redistributing the model in
an extractable form, which is precisely what a fastfile in a published map is.

Adding a prop is one entry here plus one line in ``KITS``; nothing else in the
pipeline needs to know about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Kit", "Prop", "PropMaterial", "TextureSource", "KITS", "PROPS", "TEXTURES",
           "prop", "credits_markdown"]


@dataclass(frozen=True, slots=True)
class Kit:
    """A downloadable asset pack: one archive, one licence, one texture."""

    slug: str
    title: str
    author: str
    page: str
    archive: str
    licence: str
    licence_url: str
    #: Quoted from the pack's own ``License.txt`` or its page, verbatim.
    terms: str
    #: Where the ``.obj`` files sit inside the archive.
    obj_dir: str
    #: The shared texture inside the archive, or None for a kit whose models
    #: carry no texture (a flat-colour palette is generated instead).
    texture: str | None
    #: The BO3 material asset name every model of this kit binds to.
    material: str
    #: The source image file name under ``texture_assets/<map>/``.
    image_stem: str
    #: How the models arrive.  ``"zip"``: an archive of ``.obj`` files (the
    #: Kenney kits).  ``"gltf"``: one ``.gltf`` at ``archive`` plus the buffers
    #: and images it names, fetched beside it (Poly Haven); ``obj_dir`` is
    #: unused and a prop's ``member`` is the ``.gltf`` file name.
    #: ``"generated"``: no download at all; ``member`` names a function in
    #: ``props/generated.py`` that builds the mesh.
    kind: str = "zip"


@dataclass(frozen=True, slots=True)
class TextureSource:
    """A downloadable texture set (one zip) that a prop's own material uses."""

    slug: str
    title: str
    author: str
    page: str
    archive: str
    licence: str
    licence_url: str
    #: Quoted from the source's licence page, verbatim.
    terms: str


@dataclass(frozen=True, slots=True)
class PropMaterial:
    """A prop's own material and colour map, instead of its kit's shared atlas.

    ``source`` is a :data:`TEXTURES` slug and ``member`` the image inside its
    zip; with ``source`` empty the colour map is the model's own (a glTF's
    ``baseColorTexture``).  ``swatches`` paint flat colours for named mesh
    materials into a strip along the bottom of the image, each pinned to its
    own cell like the kit swatch atlas (a bale's twine), and squeeze the
    photo into the rows above; the mesh must keep its photo UVs within
    ``0 <= v < PHOTO_V`` (``props/generated.py`` does).
    """

    asset: str  # the BO3 material asset name
    image_stem: str  # the .tif under texture_assets/<map>/
    source: str = ""
    member: str = ""
    size: int = 1024  # the colour map is resized to size x size
    swatches: tuple[tuple[str, tuple[float, float, float]], ...] = ()
    #: Colour grade: scale each channel so the photo's mean colour becomes
    #: this (0..1), keeping all its detail.  For a photo whose subject is
    #: right and whose colour is not (weathered grey thatch used as fresh hay).
    grade: tuple[float, float, float] | None = None
    #: With ``grade``: the target at the image's right edge, blended from
    #: ``grade`` at the left edge column by column (a corn leaf, olive to straw).
    grade_end: tuple[float, float, float] | None = None
    #: A pixel box ``(left, top, right, bottom)`` cut from the source image
    #: first (the opaque middle of a cut-out leaf photo), then turned
    #: ``rotate`` degrees counter-clockwise.
    crop: tuple[int, int, int, int] | None = None
    rotate: int = 0
    #: A key of ``props/generated.py`` ``PAINTERS``: our own code paints the
    #: colour map (and, with ``normal``, a tangent-space normal map) instead
    #: of a photo being resized.  ``source``/``member`` are then unused.
    painter: str = ""
    #: The painter also returns a normal map; it is bound as the material's
    #: ``normalMap`` (an image asset like the shipped ``_n`` images).
    normal: bool = False
    #: Above zero: the material is ``lit_emissive`` with the colour map as its
    #: emissive map too and this ``scaleRGB`` (stock screens use 1-1000, most 7-128;
    #: ``mtl_p7_elevator_screen_graphic`` 100).  Zero: ``lit_detail``.
    emissive: float = 0.0
    #: For a prop's ``extra_materials``: the mesh material names it covers.
    faces: tuple[str, ...] = ()
    #: With ``painter``: the :data:`TEXTURES` slugs it paints from, for the credits.
    sources: tuple[str, ...] = ()


#: How much of a :class:`PropMaterial` image the photo keeps when it has
#: swatches (the rest, at the bottom, is the swatch strip).
PHOTO_V = 0.875

AMBIENTCG_TERMS = (
    "All ambientCG assets are provided under the Creative Commons CC0 1.0 "
    "Universal License. This applies to the downloadable asset files and the "
    "material preview renders shown for each asset on the site."
)
POLYHAVEN_TERMS = (
    "Our assets are all licensed as CC0, which is effectively Public Domain "
    "even in jurisdictions that do not support the Public Domain."
)

TEXTURES: dict[str, TextureSource] = {
    "ambientcg_bark_012": TextureSource(
        slug="ambientcg_bark_012",
        title="Bark 012",
        author="ambientCG",
        page="https://ambientcg.com/view?id=Bark012",
        archive="https://ambientcg.com/get?file=Bark012_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_leaf_001": TextureSource(
        slug="ambientcg_leaf_001",
        title="Leaf 001",
        author="ambientCG",
        page="https://ambientcg.com/view?id=Leaf001",
        archive="https://ambientcg.com/get?file=Leaf001_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_painted_metal_004": TextureSource(
        slug="ambientcg_painted_metal_004",
        title="Painted Metal 004",
        author="ambientCG",
        page="https://ambientcg.com/view?id=PaintedMetal004",
        archive="https://ambientcg.com/get?file=PaintedMetal004_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_rust_004": TextureSource(
        slug="ambientcg_rust_004",
        title="Rust 004",
        author="ambientCG",
        page="https://ambientcg.com/view?id=Rust004",
        archive="https://ambientcg.com/get?file=Rust004_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_metal_032": TextureSource(
        slug="ambientcg_metal_032",
        title="Metal 032",
        author="ambientCG",
        page="https://ambientcg.com/view?id=Metal032",
        archive="https://ambientcg.com/get?file=Metal032_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_diamond_plate_008a": TextureSource(
        slug="ambientcg_diamond_plate_008a",
        title="Diamond Plate 008 A",
        author="ambientCG",
        page="https://ambientcg.com/view?id=DiamondPlate008A",
        archive="https://ambientcg.com/get?file=DiamondPlate008A_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
    "ambientcg_thatched_roof_001a": TextureSource(
        slug="ambientcg_thatched_roof_001a",
        title="Thatched Roof 001 A",
        author="ambientCG",
        page="https://ambientcg.com/view?id=ThatchedRoof001A",
        archive="https://ambientcg.com/get?file=ThatchedRoof001A_1K-JPG.zip",
        licence="CC0 1.0",
        licence_url="https://docs.ambientcg.com/license/",
        terms=AMBIENTCG_TERMS,
    ),
}


def _polyhaven(slug: str, title: str, author: str) -> "Kit":
    """One Poly Haven model as a one-model kit: its 1k glTF and textures."""
    return Kit(
        slug=f"polyhaven_{slug}",
        title=f"{title} (Poly Haven)",
        author=author,
        page=f"https://polyhaven.com/a/{slug}",
        archive=(f"https://dl.polyhaven.org/file/ph-assets/Models/gltf/1k/"
                 f"{slug}/{slug}_1k.gltf"),
        licence="CC0 1.0",
        licence_url="https://polyhaven.com/license",
        terms=POLYHAVEN_TERMS,
        obj_dir="",
        texture=None,
        material=f"zmf_ph_{slug}",
        image_stem=f"zmf_ph_{slug}_c",
        kind="gltf",
    )


KENNEY_TERMS = (
    "License: (Creative Commons Zero, CC0) "
    "http://creativecommons.org/publicdomain/zero/1.0/ — You can use this "
    "content for personal, educational, and commercial purposes. Support by "
    "crediting 'Kenney' or 'www.kenney.nl' (this is not a requirement)"
)

KITS: dict[str, Kit] = {
    "kenney_food": Kit(
        slug="kenney_food",
        title="Food Kit (2.0)",
        author="Kenney",
        page="https://kenney.nl/assets/food-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/food-kit/"
            "83086fa91c-1719418518/kenney_food-kit.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        terms=KENNEY_TERMS,
        obj_dir="Models/OBJ format",
        texture="Models/OBJ format/Textures/colormap.png",
        material="zmf_kenney_food",
        image_stem="zmf_kenney_food_c",
    ),
    "kenney_furniture": Kit(
        slug="kenney_furniture",
        title="Furniture Kit (1.0)",
        author="Kenney",
        page="https://kenney.nl/assets/furniture-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/furniture-kit/"
            "440e0608a4-1677580847/kenney_furniture-kit.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        terms=KENNEY_TERMS,
        obj_dir="Models/OBJ format",
        # This kit ships no texture: its .mtl files carry one flat Kd colour
        # per material, so the build generates a swatch atlas from them.
        texture=None,
        material="zmf_kenney_furniture",
        image_stem="zmf_kenney_furniture_c",
    ),
    "kenney_graveyard": Kit(
        slug="kenney_graveyard",
        title="Graveyard Kit (5.0)",
        author="Kenney",
        page="https://kenney.nl/assets/graveyard-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/graveyard-kit/"
            "ba8d4b4517-1760691807/kenney_graveyard-kit_5.0.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        terms=KENNEY_TERMS,
        obj_dir="Models/OBJ format",
        texture="Models/OBJ format/Textures/colormap.png",
        material="zmf_kenney_graveyard",
        image_stem="zmf_kenney_graveyard_c",
    ),
    "kenney_nature": Kit(
        slug="kenney_nature",
        title="Nature Kit (2.1)",
        author="Kenney",
        page="https://kenney.nl/assets/nature-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/nature-kit/"
            "37ac38a37b-1677698939/kenney_nature-kit.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        # This pack's License.txt words it slightly differently from the
        # newer kits; quoted verbatim.
        terms=(
            "License: (Creative Commons Zero, CC0) "
            "http://creativecommons.org/publicdomain/zero/1.0/ — This content "
            "is free to use in personal, educational and commercial projects. "
            "Support us by crediting Kenney or www.kenney.nl (this is not "
            "mandatory)"
        ),
        obj_dir="Models/OBJ format",
        # Flat Kd colours only, like the furniture kit: a swatch atlas.
        texture=None,
        material="zmf_kenney_nature",
        image_stem="zmf_kenney_nature_c",
    ),
    "kenney_car": Kit(
        slug="kenney_car",
        title="Car Kit (3.1)",
        author="Kenney",
        page="https://kenney.nl/assets/car-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/car-kit/"
            "1a312ec241-1775131960/kenney_car-kit.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        terms=KENNEY_TERMS,
        obj_dir="Models/OBJ format",
        texture="Models/OBJ format/Textures/colormap.png",
        material="zmf_kenney_car",
        image_stem="zmf_kenney_car_c",
    ),
    "kenney_fantasy_town": Kit(
        slug="kenney_fantasy_town",
        title="Fantasy Town Kit (2.0)",
        author="Kenney",
        page="https://kenney.nl/assets/fantasy-town-kit",
        archive=(
            "https://kenney.nl/media/pages/assets/fantasy-town-kit/"
            "efe948d309-1754222374/kenney_fantasy-town-kit_2.0.zip"
        ),
        licence="CC0 1.0",
        licence_url="http://creativecommons.org/publicdomain/zero/1.0/",
        terms=KENNEY_TERMS,
        obj_dir="Models/OBJ format",
        texture="Models/OBJ format/Textures/colormap.png",
        material="zmf_kenney_fantasy_town",
        image_stem="zmf_kenney_fantasy_town_c",
    ),
    # Meshes built by our own code (props/generated.py): nothing to download,
    # no licence beyond this repository's.  Each prop has its own material.
    "zmforge_generated": Kit(
        slug="zmforge_generated",
        title="zmforge generated props",
        author="zmforge",
        page="src/zmforge/props/generated.py (this repository)",
        archive="",
        licence="zmforge's own (PolyForm Noncommercial 1.0.0)",
        licence_url="LICENSE (this repository)",
        terms="Geometry generated by zmforge's own code (props/generated.py); "
              "its textures carry their own licence below.",
        obj_dir="",
        texture=None,
        material="zmf_generated",
        image_stem="zmf_generated_c",
        kind="generated",
    ),
    # Poly Haven CC0 photoscans: decimated on import to fit a budget.
    "polyhaven_dead_tree_trunk": _polyhaven("dead_tree_trunk", "Dead Tree Trunk", "Rob Tuytel"),
    "polyhaven_tree_stump_01": _polyhaven("tree_stump_01", "Tree Stump 01", "Rob Tuytel"),
    "polyhaven_wooden_crate_02": _polyhaven(
        "wooden_crate_02", "Wooden Crate 02", "James Ray Cock, Jurita Burger"),
}


@dataclass(frozen=True, slots=True)
class Prop:
    """One model: which kit file it is, how big it should be, what it is for."""

    name: str  # the xmodel asset name, and the model key in the .map
    kit: str
    member: str  # the .obj stem inside the kit
    size_units: float  # longest axis, in game units (1 unit = 1 inch)
    joke: str  # why it is in the map, for the credits file
    yaw_spread: bool = True
    max_triangles: int = 1500
    #: Solid by default: a placed object the player walks through is a
    #: surprise, and the game's own props carry collision.  Set False for a
    #: prop that is meant to be walked through -- a puddle, a rug, a shadow.
    solid: bool = True
    #: Kit colours this prop overrides: ``(obj material, (r, g, b))``, 0..1
    #: like an ``.mtl`` ``Kd``.  Only for kits that ship flat colours (a swatch
    #: atlas); the cell keeps its place, so the model's UVs do not change.
    colours: tuple[tuple[str, tuple[float, float, float]], ...] = ()
    #: The prop's own material and colour map (opt-in).  None keeps the kit's
    #: shared material and atlas cell, as every Kenney prop does.
    material: PropMaterial | None = None
    #: ``"cluster"`` (vertex clustering, the kit default) or ``"quadric"``
    #: (edge collapse, for dense photoscans; ``props/simplify.py``).
    decimation: str = "cluster"
    #: More materials for one model (a screen that glows beside a painted
    #: cabinet): each covers the mesh materials its ``faces`` names; every
    #: other mesh material binds to ``material``.
    extra_materials: tuple[PropMaterial, ...] = ()


#: Late-season field corn: a muted olive fading to straw.  Kenney's Nature Kit
#: colours its crop leaves "grass" Kd 0.17 0.85 0.72 [measured:
#: crops_cornStageD.mtl, the kit's own isometric render reads (40,216,184)],
#: a teal that renders cyan and does not read as corn.  The cobs keep theirs.
FIELD_CORN = (0.58, 0.57, 0.31)


#: The straw bales' own material: ambientCG's CC0 thatch photo, with a
#: sisal-twine swatch (a bale's ``twine`` mesh material) along the bottom.
STRAW_BALE = PropMaterial(
    asset="zmf_straw_bale",
    image_stem="zmf_straw_bale_c",
    source="ambientcg_thatched_roof_001a",
    member="ThatchedRoof001A_1K-JPG_Color.jpg",
    swatches=(("twine", (0.40, 0.30, 0.18)),),
    # The thatch photo is old grey straw: mean rgb (110, 98, 84) [measured],
    # which renders as grey stone blocks.  Graded to a sun-bleached hay gold.
    grade=(0.74, 0.62, 0.36),
)

#: The generated corn stalks' material (props/corn.py): the opaque middle of
#: ambientCG's CC0 Leaf001 cut-out photo (its Opacity map is 255 over this
#: 240 x 416 px box [measured]), turned so the long side runs
#: along u, and graded from late-season olive (u = 0, leaf bases) to straw
#: (u = 1, dry tips, husks and tassel).  The Kenney-era FIELD_CORN colour
#: sits between the two ends.
CORN_LEAF = PropMaterial(
    asset="zmf_corn_leaf",
    image_stem="zmf_corn_leaf_c",
    source="ambientcg_leaf_001",
    member="Leaf001_1K-JPG_Color.jpg",
    crop=(128, 336, 368, 752),
    rotate=90,
    grade=(0.40, 0.44, 0.20),
    grade_end=(0.74, 0.63, 0.40),
)


#: The corn walls' own surface (props/corn.py ``paint_corn_wall``): a
#: seamless painted tile of stalks and leaves in three depths on deep
#: shadow, one repeat per ``corn.WALL_TILE_UNITS``.  It is a brush surface,
#: not a model's: it rides on the full stalk's build as an extra material
#: that names no mesh faces, so it is made and registered wherever the
#: stalks are (the prop install step), and the corn maze lays it on its corn
#: walls, because the dark earth surface shows as a dirt wall through every
#: gap in the stalk rows.
CORN_WALL = PropMaterial(
    asset="zmf_corn_wall",
    image_stem="zmf_corn_wall_c",
    painter="corn_wall",
    size=2048,  # props.corn.WALL_TILE_PIXELS: a 384-unit tile
)


#: The generated dead trees' bark (props/dead_tree.py): ambientCG's CC0 oak
#: bark photo, graded to weathered grey-brown dead wood.
DEAD_BARK = PropMaterial(
    asset="zmf_dead_bark",
    image_stem="zmf_dead_bark_c",
    source="ambientcg_bark_012",
    member="Bark012_1K-JPG_Color.jpg",
    # Dark and nearly grey, weathered dead wood: a lighter grade such as
    # (0.36, 0.33, 0.29) reads pale against the night sky.
    grade=(0.17, 0.16, 0.15),
)


#: The gamble machine's two materials (props/atm.py): a painted, rusted,
#: bolted steel cabinet (colour and normal map baked from the model itself
#: over ambientCG's CC0 paint, rust, metal and diamond-plate photos) and the
#: glowing screen / topper / card-reader light.
ATM_BODY = PropMaterial(asset="zmf_atm_body", image_stem="zmf_atm_body_c", size=2048,
                        painter="atm_body", normal=True,
                        sources=("ambientcg_painted_metal_004", "ambientcg_rust_004",
                                 "ambientcg_metal_032", "ambientcg_diamond_plate_008a"))
ATM_GLOW = PropMaterial(asset="zmf_atm_glow", image_stem="zmf_atm_glow_c", size=1024,
                        painter="atm_glow", emissive=48.0, faces=("glow",))


PROPS: tuple[Prop, ...] = (
    Prop("zmf_prop_donut", "kenney_food", "donut-sprinkles", 9.0,
         "a sprinkled donut, dropped in the middle of the apocalypse"),
    Prop("zmf_prop_birthday_cake", "kenney_food", "cake-birthday", 14.0,
         "a birthday cake, candles and all, nobody left to blow them out"),
    Prop("zmf_prop_lollipop", "kenney_food", "lollypop", 18.0,
         "an absurdly large lollipop standing on the floor"),
    Prop("zmf_prop_roast_turkey", "kenney_food", "turkey", 15.0,
         "a whole roast turkey, still on its platter, going cold"),
    # Walk-through (Z46): 20 tall is two units over a walker's
    # 18 step and far under a player's 39 jump, so a heap of solid bears was a
    # ring a player hopped into and no zombie crossed -- a camping pocket.
    Prop("zmf_prop_teddy_bear", "kenney_furniture", "bear", 20.0,
         "a teddy bear sitting out the end of the world", solid=False),
    Prop("zmf_prop_toilet", "kenney_furniture", "toilet", 28.0,
         "a toilet, plumbed into nothing, in a room it has no business in"),
    # Halloween set, added: the game ships no pumpkin, corn, hay
    # bale, tractor or headstone that reads as one, and the corn maze was
    # making do with scaled oranges and tall grass.
    Prop("zmf_prop_pumpkin", "kenney_graveyard", "pumpkin", 16.0,
         "a round orange pumpkin, uncarved"),
    Prop("zmf_prop_jack_o_lantern", "kenney_graveyard", "pumpkin-carved", 16.0,
         "a round pumpkin carved into a jack-o'-lantern face"),
    Prop("zmf_prop_jack_o_lantern_tall", "kenney_graveyard",
         "pumpkin-tall-carved", 18.0,
         "a tall pumpkin carved into a jack-o'-lantern face"),
    # A generated bale with a CC0 straw photo, not Kenney's pink bale with red
    # bands (which reads as a cartoon); it keeps the kit bale's name and box,
    # so every recipe places it unchanged.
    Prop("zmf_prop_hay_bale", "zmforge_generated", "straw_bale", 40.0,
         "a square hay bale, tied with twine", material=STRAW_BALE,
         max_triangles=4500),
    Prop("zmf_prop_gravestone_round", "kenney_graveyard", "gravestone-round",
         34.0, "a round-topped headstone"),
    Prop("zmf_prop_gravestone_cross", "kenney_graveyard", "gravestone-cross",
         48.0, "a stone cross headstone"),
    Prop("zmf_prop_gravestone_broken", "kenney_graveyard", "gravestone-broken",
         26.0, "a headstone snapped off near its base"),
    Prop("zmf_prop_wooden_cross", "kenney_graveyard", "cross-wood", 78.0,
         "a wooden cross on a post: a grave marker, or with a pumpkin on "
         "top, the frame of a scarecrow"),
    Prop("zmf_prop_fence_wood", "kenney_graveyard", "fence", 64.0,
         "one section of wooden picket fence"),
    Prop("zmf_prop_fence_iron", "kenney_graveyard", "iron-fence", 64.0,
         "one section of wrought-iron cemetery fence"),
    # Corn is walked through, like tall grass: collision off.
    # a generated late-season stalk (props/corn.py) with a
    # graded CC0 leaf photo, not Kenney's block stalks; names and boxes kept.
    Prop("zmf_prop_corn_stalk", "zmforge_generated", "corn_stalk", 96.0,
         "a full-grown late-season corn stalk, two husked ears", solid=False,
         material=CORN_LEAF, extra_materials=(CORN_WALL,), max_triangles=600),
    Prop("zmf_prop_corn_stalk_thin", "zmforge_generated", "corn_stalk_thin", 90.0,
         "a leaner corn stalk, for variety between full ones", solid=False,
         material=CORN_LEAF, max_triangles=600),
    Prop("zmf_prop_tractor", "kenney_car", "tractor", 150.0,
         "a farm tractor, parked where the harvest stopped",
         max_triangles=2100),
    # No CC0 wheelbarrow or scarecrow was found (Kenney kits,
    # Poly Pizza's CC0 filter, OpenGameArt, KayKit's free Halloween Bits: the
    # KayKit scarecrow is in the paid tier).  A two-wheeled farm hand cart
    # stands in for the wheelbarrow; a scarecrow is the wooden cross with a
    # pumpkin on top, placed as two props.
    Prop("zmf_prop_hay_bale_stack", "zmforge_generated", "straw_bale_three_string",
         40.0, "a bigger three-string hay bale, the bottom of a stack",
         material=STRAW_BALE, max_triangles=4500),
    Prop("zmf_prop_hand_cart", "kenney_fantasy_town", "cart", 60.0,
         "a two-wheeled wooden farm cart, left where it was tipped"),
    # Poly Haven CC0 photoscans: realistic dressing, each with its
    # own photo colour map, decimated from 5k-100k triangles to the budget.
    Prop("zmf_prop_dead_log", "polyhaven_dead_tree_trunk", "dead_tree_trunk_1k.gltf",
         120.0, "a fallen dead tree trunk, bark peeling",
         max_triangles=12000, decimation="quadric", yaw_spread=True,
         material=PropMaterial("zmf_ph_dead_tree_trunk", "zmf_ph_dead_tree_trunk_c")),
    Prop("zmf_prop_tree_stump", "polyhaven_tree_stump_01", "tree_stump_01_1k.gltf",
         63.0, "an old tree stump with its roots out of the ground",
         max_triangles=10000, decimation="quadric",
         material=PropMaterial("zmf_ph_tree_stump_01", "zmf_ph_tree_stump_01_c")),
    Prop("zmf_prop_wooden_crate", "polyhaven_wooden_crate_02", "wooden_crate_02_1k.gltf",
         46.0, "a weathered wooden shipping crate",
         max_triangles=6000, decimation="quadric",
         material=PropMaterial("zmf_ph_wooden_crate_02", "zmf_ph_wooden_crate_02_c")),
    # Bare dead trees: generated round-limbed trees with a CC0
    # bark photo, in place of square brush trees, which read as blocky toys.
    # Solid like a stock tree, but only at the trunk: the collmap and bullet
    # mesh are recipes/props.py KIT_COLLISION_BOX, not the crown's box.
    Prop("zmf_prop_dead_tree_a", "zmforge_generated", "dead_tree_a", 300.0,
         "a bare dead tree, limbs clawing at the sky",
         material=DEAD_BARK, max_triangles=4000),
    Prop("zmf_prop_dead_tree_b", "zmforge_generated", "dead_tree_b", 270.0,
         "a leaning dead tree, crooked and bare",
         material=DEAD_BARK, max_triangles=4000),
    Prop("zmf_prop_dead_tree_c", "zmforge_generated", "dead_tree_c", 330.0,
         "a tall, wide-crowned dead tree",
         material=DEAD_BARK, max_triangles=4000),
    Prop("zmf_prop_dead_tree_d", "zmforge_generated", "dead_tree_d", 400.0,
         "a big gnarled dead oak, its trunk twisted with age",
         material=DEAD_BARK, max_triangles=4000),
    Prop("zmf_prop_dead_tree_e", "zmforge_generated", "dead_tree_e", 440.0,
         "the oldest dead tree in the yard, leaning and gnarled",
         material=DEAD_BARK, max_triangles=4000),
    # The gamble machine: a generated cash machine (props/atm.py),
    # front to -Y like the stock perk machines, origin at its floor centre.
    Prop("zmf_prop_gamble_atm", "zmforge_generated", "gamble_atm", 90.9,
         "a battered cash machine that takes 2,000 points for a one-in-four shot at 10,000",
         yaw_spread=False, material=ATM_BODY, extra_materials=(ATM_GLOW,), max_triangles=15000),
)


def prop(name: str) -> Prop:
    for entry in PROPS:
        if entry.name == name:
            return entry
    raise KeyError(f"no prop named {name!r}; have {[p.name for p in PROPS]}")


def source_file(entry: Prop) -> str:
    """The file a prop's mesh comes from, as the credits and report name it."""
    kind = KITS[entry.kit].kind
    if kind == "zip":
        return f"{entry.member}.obj"
    if kind == "generated":
        return f"generated.py:{entry.member}"
    return entry.member


def credits_markdown(props: list[Prop], placements: dict[str, tuple[float, float, float]] | None = None) -> str:
    """The credits file that ships beside the map.

    Lists every model, its source page, its download URL and its licence, with
    the licence terms quoted once per kit.  A published map carries this.
    """
    used = sorted({p.kit for p in props})
    lines = [
        "# Third-party models in this map",
        "",
        "Every model below is a free, public-domain game asset. Nothing here is",
        "from a paid marketplace: those licences forbid redistributing a model in",
        "an extractable form, which is what a shipped fastfile is.",
        "",
        "## Models",
        "",
        "| Model asset | Source file | Kit | Licence |",
        "|---|---|---|---|",
    ]
    for entry in sorted(props, key=lambda p: p.name):
        kit = KITS[entry.kit]
        lines.append(
            f"| `{entry.name}` | `{source_file(entry)}` | "
            f"[{kit.title}]({kit.page}) by {kit.author} | {kit.licence} |"
        )
    lines += ["", "## Kits and licences", ""]
    for slug in used:
        kit = KITS[slug]
        lines += [
            f"### {kit.title} — {kit.author}",
            "",
            f"- Page: {kit.page}",
            f"- Downloaded from: {kit.archive or 'nothing (generated)'}",
            f"- Licence: {kit.licence} ({kit.licence_url})",
            f"- Terms, as published: “{kit.terms}”",
            "",
        ]
    textures = sorted({slug for p in props for m in (p.material, *p.extra_materials) if m
                       for slug in ((m.source,) if m.source else ()) + m.sources})
    if textures:
        lines += ["## Textures and licences", ""]
        for slug in textures:
            tex = TEXTURES[slug]
            users = sorted(p.name for p in props if p.material and p.material.source == slug)
            lines += [
                f"### {tex.title} — {tex.author}",
                "",
                f"- Used by: {', '.join(f'`{u}`' for u in users)}",
                f"- Page: {tex.page}",
                f"- Downloaded from: {tex.archive}",
                f"- Licence: {tex.licence} ({tex.licence_url})",
                f"- Terms, as published: “{tex.terms}”",
                "",
            ]
    lines += [
        "Attribution is not required by CC0. It is here because a map that",
        "ships other people's work should say whose work it is.",
        "",
    ]
    if placements:
        lines += ["## Where they are", "", "| Model | origin (x y z) |", "|---|---|"]
        for name in sorted(placements):
            x, y, z = placements[name]
            lines.append(f"| `{name}` | {x:.0f} {y:.0f} {z:.0f} |")
        lines.append("")
    return "\n".join(lines)
