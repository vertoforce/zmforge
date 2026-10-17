"""Collision for a converted prop: a bullet mesh and a collmap, both a box.

HOW A STOCK MODEL CARRIES COLLISION -- measured on the mod tools install,
not assumed.  There are two separate mechanisms and a prop needs both:

**1. The bullet mesh.**  A second, much simpler model, named
``<model>_col.XMODEL_BIN`` and named by the asset-database key
``BulletCollisionFile``, with ``BulletCollisionLOD "Custom"``.  Counted over
the 114 top-level ``model_export`` GDTs the install ships: ``BulletCollisionFile``
is set on 706 entities and empty on 769; of the set ones **675 end in
``_col``** (then 20 ``_BULCOL``, 7 ``_BULCOLL``, 1 ``_BULLET``).
``BulletCollisionLOD`` reads ``Custom`` 686 times and ``None`` 476, and of the
686 ``Custom`` entities **zero** name no file -- so the pair is the convention.
It is simple geometry, not a copy of the art: on disk,
``p7_barrel_metal_55gal_col.XMODEL_BIN`` is **1,405 bytes** against its own
``p7_barrel_metal_55gal_lod0.xmodel_bin`` at **46,581 bytes**.

This is the one the linker reports.  Our first build logged
``Converting xmesh zmf_prop_teddy_bear (Desired Faces: 0, Scale: 1.000000,
Collision: false)`` for all six props, which is what ``BulletCollisionLOD
"None"`` and an empty ``BulletCollisionFile`` buy.

**2. The collmap.**  A ``.map`` file of *brushes* in ``share\\raw\\collmaps\\``,
named by the ``CollisionMap`` key as a bare filename, which ``cod2map`` bakes
into the static BSP.  The install ships **199** of them.  The mod tools' own
entity definition, ``bin\\t7.def.json``, is explicit about the switch, in
our words: ``no_collmap`` keeps this model's collmap out of the static BSP
(and points at the worldspawn key ``use_misc_models_collmaps`` for a global
setting), and ``use_collmap`` bakes it in.

Both are ``"type":"bool"``, both ``"value":"false"``, and the worldspawn key
``use_misc_models_collmaps``, which makes ``cod2map`` bake every misc model's
collmap into the BSP, also defaults to false.  So a ``misc_model`` gets its
collmap baked only when it says ``use_collmap``, and our props said the exact
opposite: ``no_collmap "1"``.

WHY A BOX, NOT THE MESH.  A stock collmap is a box.  ``p7_proto_door_raid_red.map``
(2,144 bytes) is **one brush**, six faces, ``clip_full 32 32 0 0 0 0``, spanning
x 0..60, y -1..1, z 0..102 -- a door-shaped slab, not a door-shaped mesh.  The
install also ships purpose-built single-box collmaps by size
(``collision_player_32x32x128.map``, ``collision_clip_wall_128x128x10.map``).
A background prop is a few hundred triangles of decoration; per-triangle
collision would cost the compiler and the runtime real work to let the player
brush past a donut's icing more accurately.  A box around the bounding volume
is what the game does for its own props, and it is what this module generates.

Coordinates are the model's own local frame, which is also what the stock
collmaps use: ``collision_player_32x32x128.map`` spans -16..16 on x and y and
-64..64 on z, centred on the model origin.  Our props are built with x and y
centred and z = 0 at the base, so the box is ``(-w/2, -d/2, 0)`` to
``(w/2, d/2, h)``.
"""

from __future__ import annotations

from dataclasses import replace

from ..emit.mapfile import WORLDSPAWN_KEYS
from ..blueprint.identity import Identity
from ..mapsource.document import (
    DEFAULT_LIGHTMAP,
    BrushSolid,
    Document,
    Entity,
    Facet,
    LayerDeclaration,
)
from ..materials import Material
from ..solids.forms import block
from ..spatial import Point, Span
from .wavefront import Mesh, Triangle, Vec3


def _stock_collmaps() -> frozenset[str]:
    import json
    from pathlib import Path

    path = Path(__file__).with_name("stock_collmaps.json")
    return frozenset(json.loads(path.read_text(encoding="utf-8")))


#: Every collmap the mod tools install ships, by bare name, read off this
#: install.  It is recorded rather than looked up so that the
#: decision "is this file Treyarch's?" is the same wherever zmforge runs: the
#: staging tree a build writes has no collmaps in it at all, and a rule that
#: asked the local filesystem would happily generate a box over one of their
#: authored shapes and then install it over Treyarch's own.
STOCK_COLLMAPS: frozenset[str] = _stock_collmaps()

__all__ = [
    "STOCK_COLLMAPS",
    "COLLISION_MATERIAL",
    "COLLISION_SUFFIX",
    "box_mesh",
    "collmap_document",
    "stock_collmap_document",
    "bounds_of",
]

#: The material on a collision brush.  ``clip_full`` is what the one shipped
#: prop collmap we can read uses (``p7_proto_door_raid_red.map``); it blocks
#: movement rather than only the player, which is what a solid object should do.
COLLISION_MATERIAL = "clip_full"

#: What the collision model's name ends in: 675 of the 706 stock models that
#: carry one spell it this way.
COLLISION_SUFFIX = "_col"


def bounds_of(mesh: Mesh) -> Span:
    """The mesh's axis-aligned bounding box, as a :class:`Span`."""
    low, high = mesh.bounds()
    return Span(Point(*low), Point(*high))


def box_mesh(box: Span, material: str) -> Mesh:
    """A twelve-triangle box, wound the way the visual meshes are.

    The bullet mesh is a model like any other, so it goes through the same
    writer; it just has eight vertices.
    """
    x0, y0, z0 = box.mins.x, box.mins.y, box.mins.z
    x1, y1, z1 = box.maxs.x, box.maxs.y, box.maxs.z
    corners: list[Vec3] = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    # Each face listed anticlockwise seen from outside, so the winding matches
    # a mesh read out of an .obj and the faces are not lit inside out.
    faces: list[tuple[tuple[int, int, int, int], Vec3]] = [
        ((0, 3, 2, 1), (0.0, 0.0, -1.0)),  # bottom
        ((4, 5, 6, 7), (0.0, 0.0, 1.0)),   # top
        ((0, 1, 5, 4), (0.0, -1.0, 0.0)),  # -y
        ((1, 2, 6, 5), (1.0, 0.0, 0.0)),   # +x
        ((2, 3, 7, 6), (0.0, 1.0, 0.0)),   # +y
        ((3, 0, 4, 7), (-1.0, 0.0, 0.0)),  # -x
    ]
    mesh = Mesh(positions=corners, source="generated collision box")
    for quad, normal in faces:
        index = len(mesh.normals)
        mesh.normals.append(normal)
        a, b, c, d = quad
        for tri in ((a, b, c), (a, c, d)):
            mesh.triangles.append(
                Triangle(
                    material=material,
                    position=tri,
                    normal=(index, index, index),
                    uv=(-1, -1, -1),
                )
            )
    return mesh


def collmap_document(box: Span, *, seed: str, material: str = COLLISION_MATERIAL) -> Document:
    """A one-brush collmap, shaped like the ones the install ships.

    ``iwmap 4``, the layer table, a worldspawn carrying the same keys a stock
    collmap does, and a single box brush of ``clip_full``.
    """
    identity = Identity(seed=seed)
    solid = block(box, Material(material))
    brush = BrushSolid(
        guid=identity.guid_for("collmap_brush"),
        contents=solid.contents,
        facets=tuple(
            Facet(
                points=face.points,
                material=face.material.name,
                lightmap_projection=DEFAULT_LIGHTMAP,
            )
            for face in solid.faces
        ),
    )
    world = Entity(
        guid=identity.guid_for("collmap_worldspawn"),
        layer=None,
        pairs=[("classname", "worldspawn"), *WORLDSPAWN_KEYS],
    )
    world.solids.append(brush)
    return Document(
        starting_number=0,
        layers=[
            LayerDeclaration("000_Global", ("active",)),
            LayerDeclaration("The Map", ("expanded",)),
        ],
        entities=[world],
    )


def stock_collmap_document(
    name: str,
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> Document:
    """A collmap for one of *Treyarch's* models, from its measured bounds.

    WHY THIS EXISTS.  ``cod2map64`` bakes a ``misc_model``'s collision only
    when the entity says ``use_collmap "1"`` **and** a file named after the
    model sits in ``share\\raw\\collmaps``.  Measured on the install:
    of the 123 stock models one generated map used for set
    dressing, 26 ship such a file and 97 do not, and for those 97 the key
    bakes nothing at all -- ``p7_shelf_metal_lab_01`` with ``use_collmap "1"``
    grew the compiled BSP by 28 bytes and left the navmesh untouched.  Putting
    a collmap at that filename made the same map bake it (BSP 26,636 ->
    31,304, navmesh 6,678 -> 7,315), so the lookup is by filename at compile
    time and a generated file is all that is missing.

    The box is the model's own bounding volume, which is both what Treyarch's
    own prop collmaps are and the one shape that cannot repeat
    ``p7_cai_watertank_body``'s failure: that model leaks a sealed map because
    its collision reaches below where its visible mesh starts, and a box cut
    from the visible mesh has nothing below it to reach with.

    Nothing here is written over an existing file; the caller checks.
    """
    (x0, y0, z0), (x1, y1, z1) = bounds
    box = Span(Point(x0, y0, z0), Point(x1, y1, z1))
    return collmap_document(box, seed=f"stock:{name}")


#: How far a kit prop's recorded box may sit from its converted mesh's bounds
#: before the converter refuses it.  Measured: the recorded boxes
#: are the mesh bounds rounded to 3 decimals, off by at most 0.0005 units.
KIT_BOX_TOLERANCE = 0.01


def kit_box(name: str) -> Span:
    """The collision box of a zmforge kit prop (``zmf_*``): its entry in
    ``recipes/props.py`` ``KIT_COLLISION_BOX`` (a tree's trunk) or else
    ``CATALOGUE_BOX``, the one record of it."""
    from ..recipes.props import KIT_COLLISION_BOX, MODEL_BOX

    bounds = KIT_COLLISION_BOX.get(name) or MODEL_BOX.get(name)
    if bounds is None:
        raise KeyError(f"{name} has no box in recipes/props.py CATALOGUE_BOX")
    (x0, y0, z0), (x1, y1, z1) = bounds
    return Span(Point(x0, y0, z0), Point(x1, y1, z1))


def kit_collmap_document(name: str) -> Document:
    """The one collmap for a zmforge kit prop, whoever writes it.

    WHY [measured]: ``share\\raw\\collmaps\\zmf_prop_*.map`` was
    written by two code paths with different text for the same prop: the
    props converter (the converted mesh's exact bounds, GUIDs seeded by the
    name) and the map generator (the recorded box, rounded to 3 decimals,
    GUIDs seeded by ``stock:<name>``).  Whichever ran last won, so a file
    changed every time the other one ran.  Both now write this: the
    recorded box (:func:`kit_box`) and GUIDs seeded by the name, so the two
    produce the same bytes.
    """
    return collmap_document(kit_box(name), seed=name)


def check_kit_box(name: str, mesh_box: Span) -> None:
    """Refuse a kit prop whose recorded box is missing or has drifted from its mesh."""
    from ..recipes.props import MODEL_BOX

    try:
        if name not in MODEL_BOX:
            raise KeyError(name)
        (x0, y0, z0), (x1, y1, z1) = MODEL_BOX[name]
        recorded = Span(Point(x0, y0, z0), Point(x1, y1, z1))
    except KeyError:
        raise ValueError(
            f"{name}: record its box in recipes/props.py CATALOGUE_BOX first: "
            f'"{name}": (({mesh_box.mins.x:.3f}, {mesh_box.mins.y:.3f}, {mesh_box.mins.z:.3f}), '
            f"({mesh_box.maxs.x:.3f}, {mesh_box.maxs.y:.3f}, {mesh_box.maxs.z:.3f})),"
        ) from None
    worst = max(
        abs(a - b)
        for a, b in zip(
            (recorded.mins.x, recorded.mins.y, recorded.mins.z,
             recorded.maxs.x, recorded.maxs.y, recorded.maxs.z),
            (mesh_box.mins.x, mesh_box.mins.y, mesh_box.mins.z,
             mesh_box.maxs.x, mesh_box.maxs.y, mesh_box.maxs.z),
        )
    )
    if worst > KIT_BOX_TOLERANCE:
        raise ValueError(
            f"{name}: its recorded box is {worst:.4f} units off the converted mesh; "
            "update recipes/props.py CATALOGUE_BOX"
        )
