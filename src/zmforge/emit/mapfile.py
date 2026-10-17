"""Blueprint to map-source document.

This is the only place that knows both the model and the file format.  It
walks the blueprint once and produces a :class:`~..mapsource.document.Document`:
worldspawn with all static geometry, then one entity per gameplay element.

Two rules from the spec are enforced here rather than left to callers:

* hull boxes carry art only on the face that looks into the room and ``caulk``
  on the other five, which is what stops an interior wall rendering as the
  skybox (spec 2.2, item E8);
* the pieces that frame an opening are visible on all six faces, because the
  player sees the jambs, sill and lintel walking through (spec 2.3).
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .. import lighting
from ..blueprint import catalogue as fixed
from ..blueprint.windows import sill_wall_solid
from ..blueprint.elements import (
    AmbientFx,
    Traversal,
    Door,
    Enclosure,
    ImportedMap,
    Lamp,
    Machine,
    Massing,
    MysteryBox,
    Wunderfizz,
    PlayerStart,
    PowerSwitch,
    Prefab,
    PropScatter,
    Room,
    Spawn,
    Terrain,
    WallWeapon,
    Window,
    Yard,
    Zone,
)
from ..materials import CAULK, TRIGGER, FaceMaterials, Material
from ..mapsource.document import (
    DEFAULT_LIGHTMAP,
    DEFAULT_SURFACE,
    BrushSolid,
    ControlVertex,
    Document,
    Entity,
    Facet,
    LayerDeclaration,
    PatchSolid,
    Projection,
)
from ..solids.forms import Solid, block
from ..solids.layout import RoomShell, ShellPiece, wall_remainder
from ..spatial import Angles, Axis, Facing, Point, Side, Span
from ..surfaces.patches import band_material, lightmap_uv, planar_uv

__all__ = [
    "build_document",
    "world_solids_of",
    "WORLDSPAWN_KEYS",
    "PREFAB_LAYERS",
]

#: Worldspawn keys a top-level zombies map carries (spec 1.3).  Values are the
#: defaults that played; a caller overrides them through the project.
WORLDSPAWN_KEYS: tuple[tuple[str, str], ...] = (
    ("lightingquality", "1024"),
    ("samplescale", "1"),
    ("skyboxmodel", "skybox_default_day"),
    ("ssi", "default_day"),
    ("wsi", "default_day"),
    ("fsi", "default"),
    ("gravity", "800"),
    ("lutmaterial", "luts_t7_default"),
    ("numOmniShadowSlices", "24"),
    ("numSpotShadowSlices", "64"),
    ("sky_intensity_factor0", "1"),
    ("sky_intensity_factor1", "1"),
    ("state_alias_1", "State 1"),
    ("state_alias_2", "State 2"),
    ("state_alias_3", "State 3"),
    ("state_alias_4", "State 4"),
)

#: A prefab's own worldspawn needs much less (spec 1.3).
PREFAB_WORLDSPAWN_KEYS: tuple[tuple[str, str], ...] = (
    ("fsi", "default"),
    ("gravity", "800"),
    ("sky_intensity_factor0", "1"),
    ("sky_intensity_factor1", "1"),
    ("state_alias_1", "State 1"),
    ("state_alias_2", "State 2"),
    ("state_alias_3", "State 3"),
    ("state_alias_4", "State 4"),
)

#: The minimal layer table real files use (spec 1.1).
PREFAB_LAYERS: tuple[LayerDeclaration, ...] = (
    LayerDeclaration("000_Global", ("expanded", "active")),
    LayerDeclaration("The Map", ("expanded",)),
)

#: Keys the zombie spawner carries: the union of what a generated test map's
#: spawner had and what a shipped map's spawner carries (spec 4.4).  Emitting the union costs
#: nothing and no single key's necessity is established.  The *classname* is
#: separate and lives in ``catalogue.ZOMBIE_SPAWNER_CLASS``; these keys are
#: the same on either zombie ``aitype``, because both inherit them from
#: ``template_aitype`` in ``bin/t7.def.json``.
FACTORY_KEYS: tuple[tuple[str, str], ...] = (
    ("count", "9999"),
    ("export", "1"),
    ("model", fixed.ZOMBIE_BODY_MODEL),
    ("script_forcespawn", "1"),
    ("spawnflags", "19"),
    ("ALERTONSPAWN", "0"),
    ("MAKEROOM", "1"),
    ("SCRIPT_FORCESPAWN", "1"),
    ("SPAWNER", "1"),
    ("script_disable_bleeder", "1"),
    ("engageMaxDist", "700"),
    ("engageMinDist", "250"),
    ("script_dropammo", "1"),
    ("sm_active_count_max", "3"),
    ("sm_active_count_min", "3"),
)

DOG_FACTORY_KEYS: tuple[tuple[str, str], ...] = (
    ("count", "1"),
    ("script_forcespawn", "1"),
    ("spawnflags", "3"),
    ("model", fixed.DOG_BODY_MODEL),
)

#: The omni light template of spec 4.11.  Colour, radius, stops and origin are
#: filled per lamp.
LIGHT_KEYS: tuple[tuple[str, str], ...] = (
    ("PRIMARY_TYPE", "PRIMARY_OMNI"),
    ("def", "white_light"),
    ("bulbRadius", "4"),
    ("falloffdistance", "8"),
    ("ENABLE_FALLOFF", "1"),
    ("PROBE_ONLY", "0"),
    # PRIMARY_NOSHADOWMAP is *not* here: it is per lamp, see _light_entity.
    ("fov_outer", "115"),
    ("far_edge", "0.5"),
    ("roundness", "0.5"),
    ("penumbraRadius", "3"),
    ("shadowmapScale", "1"),
    ("shadowUpdate", "Never"),
    ("lightingstate1", "1"),
    ("lightingstate2", "1"),
    ("lightingstate3", "1"),
    ("lightingstate4", "1"),
    ("client_server", "ClientSide"),
    ("name", "light"),
    ("spawnflags", "66"),
    # No light LOD pair (culling_cutoff / culling_falloff).  Both default to
    # 0 in deffiles/lightdescription.awi (``AddEntry_Float("culling_cutoff",
    # 0, 0, 1080)``), which never culls the lamp, and that was the old default.
    # Now 200 / 300 goes on every lamp:
    # Culling_LOD_Lights.pdf's "generic" pair, in onscreen pixels, where a
    # larger value culls harder.  On small lamps it blacks out narrow
    # corridors.  Stock
    # zm_giant does not use 200 / 300 on small lamps: of its 577 lamps (all
    # _prefabs/zm/zm_giant/**), 158 of radius <= 150 carry 5 / 25 and only 59
    # carry 200 / 300, while ours had 38 lamps of radius 72-140 on 200 / 300.
    # Reverted to the old, played behaviour until a per-radius pair is
    # measured in game; L2 now flags the hazard instead of the absence.
)

#: Every probe key that does not depend on the box.  Read off entity 26 of
#: ``rex/templates/ZM Mod Level/map_source/zm/template.map``, the probe a
#: freshly created zombies level ships with.  ``name``, ``size_min``,
#: ``size_max`` and ``in_play_space`` are *not* here: they are per-probe and
#: :func:`_probe_entities` computes them, because the template's own
#: ``72 72 72`` is an unsized 144-unit cube that covers 0.4% of a three-room
#: generated map.
REFLECTION_PROBE_KEYS: tuple[tuple[str, str], ...] = (
    ("radius", "2048"),
    ("box", "1"),
    ("blend_mins", "3 3 3"),
    ("blend_maxs", "3 3 3"),
    ("placement_offset", "72"),
    ("grid_density", "16"),
    ("high_detail", "1"),
    ("ao_power", "2"),
    ("ao_range", "16"),
    ("ao_strength", "1"),
    ("exploderFade", "1"),
    ("debugColor", "1 1 1"),
    ("client_server", "ClientSide"),
)


def _vector(point: Point) -> str:
    from ..mapsource.scalars import decimal_token

    return " ".join(decimal_token(value) for value in point)


def _angle_text(angles: Angles) -> str:
    """``pitch yaw roll``, every turn folded into ``[0, 360)``.

    One place, because this is the only function that writes an angle.  A
    heading is a direction and not a count of turns, so 360 and 0 are the same
    facing and have to be written the same way or two paths that mean the same
    thing produce different bytes: a prop the recipe turned a full circle came
    out ``0 360 0`` while the same prop rebuilt from the shared document -- where
    the yaw had already been folded once -- came out ``0 0 0``.  Folding here
    makes the byte diff between the two a proof rather than noise, and writes
    the form the file is already full of (``0 0 0`` appears 49 times in
    ``zm_mymap.map``; ``0 360 0`` appeared once).
    """
    from ..mapsource.scalars import decimal_token

    return " ".join(decimal_token(value % 360.0) for value in angles)


class _Guids:
    """Deterministic GUIDs, one stream per element id."""

    def __init__(self, identity) -> None:
        self._identity = identity
        self._used: dict[str, int] = {}

    def next(self, element_id: str) -> str:
        ordinal = self._used.get(element_id, 0)
        self._used[element_id] = ordinal + 1
        return self._identity.guid_for(element_id, ordinal)


#: Which world directions the compiler runs a face's texture along, as the
#: ``(u, v)`` unit vectors, keyed by the axis the face's normal lies on.
#:
#: **Measured**, not assumed: probe maps compiled with the real
#: ``cod2map64.exe`` and the texture coordinates read back out of the vertex
#: lump of the ``.d3dbsp`` it wrote (``docs/mapsource-format-reference.md``
#: 1.4).  A vertex's coordinate is
#:
#:     ``u = (P . U - shift_u) / size_u``   ``v = (P . V - shift_v) / size_v``
#:
#: so the projection is anchored to the **world**, the shift is in world units
#: and it is *subtracted*.  The axes depend on which axis the normal lies on
#: and not on its sign, which is why the pair below is keyed by axis alone.
_TEXTURE_AXES: dict[Axis, tuple[Point, Point]] = {
    Axis.X: (Point(0.0, 1.0, 0.0), Point(0.0, 0.0, -1.0)),
    Axis.Y: (Point(1.0, 0.0, 0.0), Point(0.0, 0.0, -1.0)),
    Axis.Z: (Point(1.0, 0.0, 0.0), Point(0.0, -1.0, 0.0)),
}

#: The two wall directions whose texture axis runs the wrong way for the
#: player standing in front of them, as the outward normal.  Facing north a
#: player has east on his right, so a wall that looks south (normal -Y) runs
#: its ``u`` the way he reads; the wall opposite it shares that same ``+X``
#: axis and therefore runs it backwards, and the same for the two walls on
#: the X axis.  A picture on one of these is mirrored -- readable text comes
#: out reversed -- and the cure is a negative width, which the format carries
#: and the compiler accepts (measured on a probe: ``u`` 0 at the far corner,
#: 1 at the near one, residual 0).  Ordinary tiling surfaces are left alone:
#: nobody can tell which way round a wall of brick is.
_MIRRORED_WALLS: frozenset[tuple[Axis, float]] = frozenset({(Axis.Y, 1.0), (Axis.X, -1.0)})

#: How close two world lengths have to be to count as the same length.  Face
#: corners are decimals, so an exact ``==`` would miss a picture hung at a
#: half unit.
_FIT_TOLERANCE = 1e-6


def _outward_normal(face) -> Point:
    """The direction the face looks, read off the points the compiler reads.

    ``plane`` is the inward half-space (spec 1.4), so the face looks the other
    way; ``inward`` on the face says the same thing but is carried rather than
    derived, and every check in this package re-derives.
    """
    return -face.plane.normal


def _normal_axis(normal: Point) -> tuple[Axis, float] | None:
    """``(axis, sign)`` for an axis-aligned direction, else ``None``."""
    for axis in Axis:
        reach = normal[axis.index]
        if abs(abs(reach) - 1.0) <= 1e-9:
            return axis, 1.0 if reach > 0.0 else -1.0
    return None


def _picture_projection(material, face, corners: Sequence[Point]) -> Projection | None:
    """The projection that puts one copy of a picture on the face it hangs on.

    A hung picture has a shape of its own (spec 2.2, and every piece of wall
    art this generator hangs): a panel whose one visible face carries the
    image and whose other five are ``caulk``, laid at exactly the image's own
    size.  A face like that is not a tiling surface -- it is one image, a
    poster, a sign, a portrait -- and the whole point of it is to show that
    image once, the right way up and the right way round.  A box painted the
    same material all over is a crate and is left alone, however its sides
    happen to measure.

    The projection is anchored to the world origin, though, so an image only
    lands where it was meant to when its panel happens to sit a whole number
    of image widths from that origin, and nothing makes that true.  A poster
    56 units wide whose left edge sits at x 772 starts 44 units into an image:
    the seam falls 12 units across the poster's own face, the tail of its
    right-hand side wraps round to the left of its own left edge, and the
    headline runs off the face's right-hand edge.  Every picture face laid
    this way is misaligned unless its position happens to line up.

    So each shift is the world coordinate, along that texture axis, of the
    corner of the face the image's own corner has to sit on -- which is the
    *far* corner across a mirrored wall, where the width is written negative.
    ``None`` when the face is not one image: an ordinary tiling surface keeps
    the world anchor, which is what lets two brushes of one wall carry the
    pattern across the join between them without a step in it.
    """
    axis = _normal_axis(_outward_normal(face))
    if axis is None:
        return None
    plane = face.plane
    on_face = [point for point in corners if plane.lies_on(point)]
    if len(on_face) < 3:
        return None
    mirrored = axis in _MIRRORED_WALLS
    sizes: list[float] = []
    shifts: list[float] = []
    for direction, size, flip in zip(
        _TEXTURE_AXES[axis[0]], (material.scale, material.scale_v), (mirrored, False)
    ):
        reach = [direction.dot(point) for point in on_face]
        if abs((max(reach) - min(reach)) - size) > _FIT_TOLERANCE:
            return None
        sizes.append(-size if flip else size)
        shifts.append(max(reach) if flip else min(reach))
    return Projection(sizes[0], sizes[1], shifts[0], shifts[1], 0.0, 0.0)


def _surface_projection(material, face=None, corners: Sequence[Point] = ()) -> Projection:
    """The face line's first six numbers: default, or the material's own size.

    The two axes are taken separately: ``Material`` resolves ``scale_v`` to
    ``scale`` when the caller gave one number, so a square tile is written
    exactly as it was before the second axis existed.

    ``face`` is passed only for the one visible face of a panel -- what a hung
    picture is -- together with the brush's ``corners``, and those are what
    turn a size into a *placed* image (:func:`_picture_projection`).  For
    every other face, and for every ordinary tiling surface, the shift stays
    ``0 0``, which is the world anchor Radiant writes.
    """
    if material.scale is None:
        return DEFAULT_SURFACE
    picture = _picture_projection(material, face, corners) if face is not None else None
    if picture is None:
        return Projection(material.scale, material.scale_v, 0.0, 0.0, 0.0, 0.0)
    return picture


def _brush_of(solid: Solid, guid: str) -> BrushSolid:
    # Every corner of the brush, once, so a face can ask which of them lie on
    # it: a face triple is three points on a plane and says nothing about how
    # far the face reaches, and a picture is placed by its own edges.
    corners = tuple(point for face in solid.faces for point in face.points)
    visible = [face for face in solid.faces if face.material.name != CAULK.name]
    hung = visible[0] if len(visible) == 1 else None
    facets = tuple(
        Facet(
            points=face.points,
            material=face.material.name,
            projection=_surface_projection(
                face.material, face if face is hung else None, corners
            ),
            lightmap_projection=DEFAULT_LIGHTMAP,
        )
        for face in solid.faces
    )
    return BrushSolid(guid=guid, contents=solid.contents, facets=facets)


def _piece_materials(piece: ShellPiece, materials) -> FaceMaterials:
    if piece.aperture:
        return materials.aperture_faces(piece.side)
    return materials.hull_faces(piece.side)


def _shell_solids(shell: RoomShell, materials, holes: Sequence[Span]) -> list[Solid]:
    """The shell's boxes with any openings subtracted, materialled per 2.2/2.3."""
    solids: list[Solid] = []
    for piece in shell.pieces:
        mine = [hole for hole in holes if hole.overlaps(piece.box, slack=1e-9)]
        if not mine:
            solids.append(
                block(piece.box, _piece_materials(piece, materials), note=piece.side.name)
            )
            continue
        along = Axis.Y if piece.side.axis is Axis.X else Axis.X
        for box in wall_remainder(piece.box, mine, along):
            frames = any(box.grown(1e-6).overlaps(hole, slack=0.0) for hole in mine)
            tagged = ShellPiece(box, piece.side, aperture=frames)
            solids.append(
                block(box, _piece_materials(tagged, materials), note=piece.side.name)
            )
    return solids


def _room_solids(room: Room) -> list[Solid]:
    return _shell_solids(room.shell, room.materials, room.aperture_boxes)


def _yard_solids(yard: Yard) -> list[Solid]:
    return _shell_solids(yard.shell, yard.materials, tuple(yard.vents))


def _terrain_patches(terrain: Terrain, guids: _Guids) -> list[PatchSolid]:
    """One mesh block per chunk, with no ``contents`` line at all.

    That is what makes it solid.  Measured across the shipped ``.map``
    files: ``contents solid`` appears **zero** times, and the walkable base
    layer of ``_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map`` is 172
    meshes with no ``contents`` line, while its 129 decorative alpha-blend
    overlays opt *out* with ``contents nonColliding;``.  Solid is the default
    and is never written.

    No second, coincident mesh per chunk carrying ``contents weaponClip
    detail;`` is emitted as a "collision twin", whatever spec 1.8's claim that
    it "gives a walkable, bullet-stopping surface" suggests.  The shipped
    evidence is the opposite.  ``weaponClip`` stops bullets, and stating it
    *replaces* the default contents rather than adding to it, so such a twin
    is at best redundant and at worst a bullet-only clip laid exactly over the
    ground the player stands on, and a player can fall through the terrain
    and get stuck under it.  The rule rests on those contents semantics, not
    on materials: 20 of that file's 76 ``weaponClip detail ai_nosight``
    patches carry the base layer's own sand.

    Solidity no longer rests on the patch semantics either way: see
    :func:`_terrain_plinth`.
    """
    patches: list[PatchSolid] = []
    for index, grid in enumerate(terrain.grids):
        rows = tuple(
            tuple(
                ControlVertex(
                    position=grid.point(outer, inner),
                    u=planar_uv(grid.point(outer, inner), terrain.texture_scale)[0],
                    v=planar_uv(grid.point(outer, inner), terrain.texture_scale)[1],
                    lu=lightmap_uv(outer, inner)[0],
                    lv=lightmap_uv(outer, inner)[1],
                )
                for inner in range(grid.height)
            )
            for outer in range(grid.width)
        )
        material = terrain.material.name
        patches.append(
            PatchSolid(
                guid=guids.next(f"{terrain.id}_visual_{index}"),
                kind="mesh",
                material=material,
                grid=rows,
            )
        )
    return patches


#: How thick the caulk block under a mesh terrain is.  It only has to be
#: thicker than anything could tunnel through in one frame; the shipped
#: equivalent in ``zm_giant_geo.map`` is a hull, not a slab, and is far
#: thicker than it needs to be.
TERRAIN_PLINTH_DEPTH = 64.0


def _terrain_plinth(terrain: Terrain) -> list[Solid]:
    """A caulk block filling the space under a mesh terrain.

    A mesh is a surface, not a volume, so a free-standing heightfield has
    nothing but void beneath it: anything that gets through the surface ends
    up under the world, alive and stuck, which is worse than dying.  Treyarch's own answer is a solid fill under the visible
    world: ``_prefabs/zm/zm_giant/zm_giant_geo.map`` line 6008 is one caulk
    block spanning x -7776..6680, y -10624..8880 down to z -288, roughly 1300
    units below its lowest visible floor.

    So the terrain gets a floor of its own, from its lowest surface point
    down, and the map gets one under everything as well
    (:func:`_catch_volume_entity`).  Both, because that is what the shipped
    map does.

    It follows the heightfield rather than being one flat slab under the
    lowest point.  A flat slab under a hill leaves a tall pocket between it
    and the underside of the mesh, and a player who got into that pocket
    would be exactly as stuck as before, one unit lower down.  So there is one
    box per grid cell, its top at the lowest of the cell's four corners: what
    is left under the sloping mesh is a wedge no taller than the cell's own
    fall, which is nowhere near the 72 units a player stands in.

    The boxes carry ``contents detail;`` -- solid, but not splitting the BSP,
    which a few hundred structural brushes under the ground would.  ``detail``
    is shipped vocabulary, 1500 occurrences across the shipped sources.

    Empty for a column-style terrain: its columns are already solid brushes
    standing on their own bases.
    """
    if terrain.style == "columns" or not terrain.grids:
        return []
    lowest = min(
        grid.point(outer, inner).z
        for grid in terrain.grids
        for outer in range(grid.width)
        for inner in range(grid.height)
    )
    base = lowest - TERRAIN_PLINTH_DEPTH
    boxes: list[Solid] = []
    for grid in terrain.grids:
        for outer in range(grid.width - 1):
            for inner in range(grid.height - 1):
                corners = [
                    grid.point(outer + dx, inner + dy)
                    for dx in (0, 1)
                    for dy in (0, 1)
                ]
                lid = min(corner.z for corner in corners)
                if lid <= base:  # pragma: no cover - lowest defines the base
                    continue
                boxes.append(
                    block(
                        Span.between(
                            Point(
                                min(corner.x for corner in corners),
                                min(corner.y for corner in corners),
                                base,
                            ),
                            Point(
                                max(corner.x for corner in corners),
                                max(corner.y for corner in corners),
                                lid,
                            ),
                        ),
                        FaceMaterials.uniform(CAULK),
                        ("detail",),
                        note="terrain plinth",
                    )
                )
    return boxes


def _terrain_columns(terrain: Terrain) -> list[Solid]:
    solids: list[Solid] = []
    for run in terrain.runs:
        material = (
            band_material(terrain.bands, run.top_z) if terrain.bands else terrain.material
        )
        solids.append(
            block(
                run.box,
                FaceMaterials.only_visible_on(Side.TOP, material),
                note="terrain column",
            )
        )
    return solids


def world_solids_of(blueprint) -> list[Solid]:
    """Every structural world solid, for the overlap scan of spec 2.8 step 7.

    Sky slabs, tool volumes and ``detail`` brushes are excluded: the scan is
    about brushes that split the BSP, and Radiant's own maps overlap the rest
    freely.
    """
    solids: list[Solid] = []
    for room in blueprint.elements(Room):
        solids.extend(_room_solids(room))
    for yard in blueprint.elements(Yard):
        solids.extend(_yard_solids(yard))
    for massing in blueprint.elements(Massing):
        if not massing.targetname:
            solids.extend(massing.solids)
    for terrain in blueprint.elements(Terrain):
        solids.extend(_terrain_columns(terrain))
        solids.extend(_terrain_plinth(terrain))
    return [
        solid
        for solid in solids
        if "detail" not in solid.contents
        and not solid.material_names <= {CAULK.name}
    ]


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
def _entity(guid: str, classname: str, pairs: Iterable[tuple[str, str]], layer: str | None = "The Map") -> Entity:
    return Entity(guid=guid, layer=layer, pairs=[("classname", classname), *pairs])


def _volume_entity(
    guids: _Guids,
    element_id: str,
    classname: str,
    box: Span,
    material: Material,
    pairs: Iterable[tuple[str, str]] = (),
    contents: tuple[str, ...] = ("detail",),
) -> Entity:
    entity = _entity(guids.next(element_id), classname, pairs)
    solid = block(box, FaceMaterials.uniform(material), contents)
    if classname == "volume_litfog":
        solid = _right_angle_in_the_middle(solid)
    entity.solids.append(_brush_of(solid, guids.next(element_id)))
    return entity


def _right_angle_in_the_middle(solid: Solid) -> Solid:
    """The same box, each face's triple turned so its right angle is point 2.

    ``block`` writes a face as (lo,lo) (hi,hi) (lo,hi) after orientation: the
    plane is right, but the corner is the *last* point.  Every ``volume_litfog``
    brush in ``_prefabs/zm/zm_giant/zm_giant_light.map`` has the corner in the
    middle, and the linker warned "Lit fog volume ... has faces which are not
    90 degrees to all its neighboring faces" on all four of zm_cemetery's.
   A cyclic turn keeps the winding, so the
    plane and its facing are unchanged.
    """
    from dataclasses import replace as _replace

    def turned(points):
        for k in range(3):
            a, b, c = points[k], points[(k + 1) % 3], points[(k + 2) % 3]
            u = (a.x - b.x, a.y - b.y, a.z - b.z)
            v = (c.x - b.x, c.y - b.y, c.z - b.z)
            if abs(u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) < 1e-6:
                return (a, b, c)
        return points

    return _replace(solid, faces=tuple(_replace(f, points=turned(f.points)) for f in solid.faces))


def _player_start_entities(
    start: PlayerStart, guids: _Guids, groups: Sequence = (), start_zone: str = ""
) -> list[Entity]:
    """The respawn set plus one initial-spawn struct per slot (spec 4.1, K1).

    One ``player_respawn_point`` per zone, each with a ``target`` naming its
    group of points, as shipped ``zm_giant.map`` does
    (:mod:`zmforge.blueprint.respawn`; ``_zm.gsc:3453`` reads the target).
    With no group anywhere the one struct targets the initial spawns, which
    is what ``zm_giant``'s own start zone does.
    """
    tokens = fixed.spawn_string_tokens()
    angles = _angle_text(Angles.facing_yaw(start.facing.world_yaw))

    def respawn_struct(guid: str, zone: str, target: str, origin: Point) -> Entity:
        return _entity(
            guid,
            "script_struct",
            [
                ("targetname", "player_respawn_point"),
                ("script_noteworthy", zone),
                ("target", target),
                ("script_string", tokens),
                ("script_int", "2000"),
                ("radius", str(int(start.respawn_radius))),
                ("origin", _vector(origin)),
                ("angles", angles),
            ],
        )

    first = guids.next(start.id)
    if groups:
        entities = [respawn_struct(first, groups[0].zone, groups[0].target, groups[0].anchor)]
    else:
        entities = [respawn_struct(first, start_zone or fixed.START_LOCATION,
                                   "initial_spawn_points", start.position)]
    for position in start.slot_positions():
        # No script_int.  On an initial-spawn struct that key is the *team
        # side*, not a slot number: zm::getfreespawnpoint deletes every
        # struct whose script_int is 1 or 2, depending on a per-game coin
        # flip, before it hands one out (spec 4.1).  Shipped zm_giant.map
        # omits it on all four of its initial_spawn_points structs.
        entities.append(
            _entity(
                guids.next(start.id),
                "script_struct",
                [
                    ("targetname", "initial_spawn_points"),
                    ("script_noteworthy", "initial_spawn"),
                    ("script_string", tokens),
                    ("radius", "32"),
                    ("origin", _vector(position)),
                    ("angles", angles),
                ],
            )
        )
    for index, group in enumerate(groups):
        ident = f"{start.id}_respawn_{group.zone}"
        if index:
            entities.append(respawn_struct(guids.next(ident), group.zone, group.target,
                                           group.anchor))
        # Stock group points: script_int 1..n, no script_string (zm_giant.map).
        for number, point in enumerate(group.points, start=1):
            entities.append(_entity(guids.next(ident), "script_struct", [
                ("targetname", group.target),
                ("script_int", str(number)),
                ("origin", _vector(point)),
                ("angles", angles),
            ]))
    return entities


def _traversal_entities(trav: Traversal, guids: _Guids) -> list[Entity]:
    """The node pair of stock ``t7_zm_jump_128.map``, keys and all."""
    import math

    yaw = math.degrees(math.atan2(trav.end.y - trav.begin.y, trav.end.x - trav.begin.x))
    end_name = f"{trav.id}_end"
    return [
        _entity(guids.next(f"{trav.id}_end"), "node_negotiation_end", [
            ("angles", f"0 {(yaw + 180.0) % 360.0:g} 0"),
            ("animscript", trav.down),
            ("origin", _vector(trav.end)),
            ("targetname", end_name),
        ]),
        _entity(guids.next(trav.id), "node_negotiation_begin", [
            ("angles", f"0 {yaw % 360.0:g} 0"),
            ("animscript", trav.up),
            ("movementtype_ignore", "civilian,riotshield,zombie_dog"),
            ("origin", _vector(trav.begin)),
            ("target", end_name),
            ("cost_modifier", "1"),
        ]),
    ]


def _spawn_entities(spawn: Spawn, guids: _Guids) -> list[Entity]:
    entities = [
        _entity(
            guids.next(spawn.id),
            "script_struct",
            [
                ("targetname", spawn.spawn_set),
                ("script_noteworthy", spawn.marker),
                ("script_string", spawn.link_tag),
                ("origin", _vector(spawn.position)),
                ("angles", _angle_text(spawn.facing)),
            ],
        )
    ]
    if spawn.with_factory:
        template = DOG_FACTORY_KEYS if spawn.is_dog else FACTORY_KEYS
        classname = (
            fixed.DOG_SPAWNER_CLASS if spawn.is_dog else fixed.ZOMBIE_SPAWNER_CLASS
        )
        marker = "zombie_dog_spawner" if spawn.is_dog else "zombie_spawner"
        entities.append(
            _entity(
                guids.next(spawn.id),
                classname,
                [
                    ("script_noteworthy", marker),
                    *template,
                    ("origin", _vector(spawn.position)),
                ],
            )
        )
    return entities


def _door_entities(door: Door, guids: _Guids) -> list[Entity]:
    """Trigger, moving collision and (optionally) the visible leaf (spec 4.5)."""
    from ..materials import CLIP, TRIGGER

    travel = _vector(door.travel)
    trigger_box = door.trigger_box
    trigger = _entity(
        guids.next(door.id),
        "trigger_use",
        [
            ("targetname", "zombie_door"),
            ("target", door.door_name),
            ("zombie_cost", str(int(door.price))),
            ("script_flag", door.flag),
            ("cursorhint", "HINT_ACTIVATE"),
            (
                "script_noteworthy",
                "electric_door" if door.electric
                else "electric_buyable_door" if door.requires_power else "default",
            ),
            # E12: without an explicit origin a brush entity sits at 0 0 0 and
            # the prompt-visibility check measures from there.
            ("origin", _vector(trigger_box.centre)),
        ],
    )
    trigger.solids.append(
        _brush_of(
            block(trigger_box, FaceMaterials.uniform(TRIGGER), ("detail",)),
            guids.next(door.id),
        )
    )

    collision = _entity(
        guids.next(door.id),
        "script_brushmodel",
        [
            ("targetname", door.door_name),
            ("script_string", "move"),
            ("script_vector", travel),
            ("DYNAMICPATH", "1"),
            ("spawnflags", "1"),
            ("shadow_casting", "1"),
        ],
    )
    collision.solids.append(
        _brush_of(block(door.box, FaceMaterials.uniform(CLIP)), guids.next(door.id))
    )

    entities = [trigger, collision]
    # The leaf is scaled and tiled to fill the opening (Door.leaves); a
    # modelscale-1 leaf is 120 x 102 and left the corn maze's 256 x 176 patch
    # gate open round a small door.  Every leaf shares the
    # door's targetname, so the stock script moves them all together
    # (_zm_blockers.gsc door_init gathers GetEntArray( self.target )).
    for base, scale in door.leaves if door.model else ():
        entities.append(
            _entity(
                guids.next(door.id),
                "script_model",
                [
                    ("model", door.model),
                    ("targetname", door.door_name),
                    ("script_string", "move"),
                    ("script_vector", travel),
                    ("DYNAMICPATH", "1"),
                    ("spawnflags", "1"),
                    ("shadow_casting", "1"),
                    ("client_server", "ServerSide"),
                    ("modelscale", _number(scale)),
                    ("origin", _vector(base)),
                    ("angles", _angle_text(Angles.facing_yaw(door.model_yaw))),
                ],
            )
        )
    return entities


def _machine_entity(machine: Machine, guids: _Guids) -> Entity:
    # Per machine, not per family: eight of the nine vending prefabs face south
    # at yaw 0 and the pack-a-punch faces west, both measured on the install.
    yaw = fixed.prefab_yaw(machine.facing, machine.perk.front_zero)
    if not machine.perk.from_prefab:
        # Widow's Wine and Electric Cherry: the install ships the machine's
        # model and its script but no prefab to stamp, so emit the struct the
        # prefabs themselves hold.  ``vending_juggernaut_struct.map`` on the
        # install is a worldspawn, five decorative lights, three attack spots
        # and one ``script_struct`` carrying exactly ``model``,
        # ``script_noteworthy`` and ``targetname "zm_perk_machine"`` -- and
        # ``_zm_perks.gsc:1419`` says in Treyarch's own comment that those are
        # what a machine needs.  The trigger, the bump trigger and the
        # collision are spawned by ``perk_machine_spawn_init`` at runtime, and
        # the collision is the shared ``zm_collision_perks1``, not a
        # per-machine model, so nothing here is lost by skipping the prefab
        # except its decorative lights.
        #
        # The prefab's own struct carries no ``angles``, measured on the
        # install for both the juggernog and the deadshot prefab, so the model
        # sits at the prefab's own heading at yaw 0 and the family's
        # ``front_zero`` turn applies unchanged.
        return _entity(
            guids.next(machine.id),
            "script_struct",
            [
                ("model", machine.perk.xmodel),
                ("script_noteworthy", machine.perk.specialty),
                ("targetname", "zm_perk_machine"),
                ("origin", _vector(machine.position)),
                ("angles", _angle_text(Angles.facing_yaw(yaw))),
            ],
        )
    pairs = [
        ("model", machine.perk.prefab),
        ("origin", _vector(machine.position)),
        ("angles", _angle_text(Angles.facing_yaw(yaw))),
    ]
    if machine.perk.slug == "gobblegum":
        # Treyarch's own gobblegum placement marks the machines that are up at
        # the start with this key on the misc_prefab
        # (_prefabs/zm/zm_giant/script/zm_giant_bgb_machines.map:38, :55);
        # every machine a zmforge map places is one of those.  What an unmarked
        # machine does is in _zm_bgb_machine, whose source is not shipped:
        # unverified in play.
        pairs.append(("script_noteworthy", "start_bgb_machine"))
    return _entity(guids.next(machine.id), "misc_prefab", pairs)


def _wall_weapon_entities(weapon: WallWeapon, guids: _Guids) -> list[Entity]:
    # The family that was measured first: it faces north at yaw 0.  See
    # catalogue.wall_weapon_yaw for the compiled-BSP measurement that
    # established the counter-clockwise turn every family now uses.
    yaw = fixed.wall_weapon_yaw(weapon.facing)
    entities = [
        _entity(
            guids.next(weapon.id),
            "misc_prefab",
            [
                ("model", fixed.wall_weapon_prefab(weapon.slug)),
                ("origin", _vector(weapon.position)),
                ("angles", _angle_text(Angles.facing_yaw(yaw))),
            ],
        )
    ]
    if weapon.chalk_material is not None:
        entities.append(
            _entity(
                guids.next(weapon.id),
                "misc_volume_decal",
                [
                    ("model", "vol_decal_cube"),
                    ("modeloverridematerial", weapon.chalk_material.name),
                    ("decalsize", weapon.decal_size),
                    ("decalLayerSort", "Grunge"),
                    ("decalLayerSortEnum", "14"),
                    ("decalEditorSortEnum", "0"),
                    ("origin", _vector(weapon.position)),
                    (
                        "angles",
                        _angle_text(
                            Angles.facing_yaw(
                                (weapon.facing.opposite.world_yaw) % 360.0
                            )
                        ),
                    ),
                ],
            )
        )
    return entities


def _mystery_box_entities(box: MysteryBox, guids: _Guids) -> list[Entity]:
    # North, the opposite of the perk heading: the stand prefab is symmetric
    # and says nothing, so the front is the one the zbarrier's stock use
    # prompt sits on (catalogue.MYSTERY_BOX_FRONT_ZERO).  One yaw for all
    # three entities is right -- stand and box share a long axis at yaw 0.
    yaw = fixed.prefab_yaw(box.facing, fixed.MYSTERY_BOX_FRONT_ZERO)
    origin = _vector(box.position)
    angles = _angle_text(Angles.facing_yaw(yaw))
    barrier_pairs = [
        (key, value) for key, value in fixed.MAGIC_BOX_BARRIER if key != "classname"
    ]
    return [
        _entity(
            guids.next(box.id),
            "misc_prefab",
            [
                ("model", fixed.MYSTERY_BOX_PREFAB),
                ("origin", origin),
                ("angles", angles),
            ],
        ),
        _entity(
            guids.next(box.id),
            "zbarrier_zmcore_MagicBox",
            [
                ("script_noteworthy", f"{box.chest_name}_zbarrier"),
                *barrier_pairs,
                ("origin", origin),
                ("angles", angles),
            ],
        ),
        _entity(
            guids.next(box.id),
            "script_struct",
            [
                ("targetname", "treasure_chest_use"),
                ("script_noteworthy", box.chest_name),
                ("zombie_cost", str(int(box.price))),
                ("origin", origin),
                ("angles", angles),
            ],
        ),
    ]


def _wunderfizz_entity(fizz: Wunderfizz, guids: _Guids) -> Entity:
    """Der Wunderfizz: one zbarrier entity, pieces and all.

    The stock script finds it by ``targetname`` and drives it by piece
    index, so both of those are the whole contract:
    ``_zm_perk_random.gsc:91`` ``GetEntArray( "perk_random_machine",
    "targetname" )`` and ``:843-910``, which calls ``ShowZBarrierPiece`` and
    ``SetZBarrierPieceState`` on the six indices ``_zm_perk_random.gsh:26-31``
    names.  Six boards, therefore, each spelled out -- the shape Treyarch's
    own ``vending_bgb_struct.map`` and ``vending_weapon_upgrade_spawnable.map``
    use for the same kind of machine.

    The animations are blank on purpose: the mod tools install has one Wunderfizz
    model and no Wunderfizz animation, so the machine is static.  Left out
    rather than blanked, each piece would inherit the pack-a-punch animation
    that the borrowed definition carries.  See
    :data:`~zmforge.blueprint.catalogue.WUNDERFIZZ_PIECES`.

    Not played.
    """
    yaw = fixed.prefab_yaw(fizz.facing, fixed.WUNDERFIZZ_FRONT_ZERO)
    pairs: list[tuple[str, str]] = [
        ("targetname", fixed.WUNDERFIZZ_TARGETNAME),
        ("type", fixed.WUNDERFIZZ_ZBARRIER_TYPE),
        ("zbarriernumboards", str(len(fixed.WUNDERFIZZ_PIECES))),
    ]
    if fizz.starting:
        pairs.append(("script_noteworthy", fixed.WUNDERFIZZ_START_NOTEWORTHY))
    for index, model in enumerate(fixed.WUNDERFIZZ_PIECES, start=1):
        pairs.append((f"zbarrierboardmodel{index}", model))
        pairs.append((f"zbarrierboardanim{index}", ""))
        pairs.append((f"zbarriertearanim{index}", ""))
    pairs.append(("origin", _vector(fizz.position)))
    pairs.append(("angles", _angle_text(Angles.facing_yaw(yaw))))
    return _entity(guids.next(fizz.id), fixed.WUNDERFIZZ_CLASSNAME, pairs)


def _prefab_entity(prefab: Prefab, guids: _Guids) -> Entity:
    """A bare ``misc_prefab``: the same three keys the machines carry.

    A raw ``yaw`` on the element wins: the caller has established this
    prefab's own zero heading and the facing is not read.  Otherwise the
    heading is turned counter-clockwise off the front-at-yaw-zero measured for
    that model, and a model nobody has opened falls back to
    :data:`~zmforge.blueprint.catalogue.UNMEASURED_PREFAB_FRONT_ZERO`, which
    is a guess and which ``Z23`` reports as one.
    """
    if prefab.yaw is not None:
        yaw = prefab.yaw
    else:
        zero = fixed.prefab_front_zero(prefab.model) or fixed.UNMEASURED_PREFAB_FRONT_ZERO
        yaw = fixed.prefab_yaw(prefab.facing, zero)
    pairs = [("model", prefab.model)]
    # Where ``add_window``'s own barricade carries it, so a barricade written
    # through this call and one written through ``add_window`` are the same
    # entity, key for key.
    if prefab.script_string:
        pairs.append(("script_string", prefab.script_string))
    pairs.append(("origin", _vector(prefab.position)))
    pairs.append(("angles", _angle_text(Angles.facing_yaw(yaw))))
    return _entity(guids.next(prefab.id), "misc_prefab", pairs)


def _lamp_entity(lamp: Lamp, stops: float, guids: _Guids) -> Entity:
    """One ``light`` entity.

    ``stops`` is resolved by the blueprint rather than read off the lamp:
    a lamp that names no intensity of its own takes the one the map's
    sun/sky preset calls for, and the map-wide brightness offset applies to
    every lamp either way (:mod:`zmforge.lighting`).
    """
    from ..mapsource.scalars import decimal_token

    colour = " ".join(decimal_token(channel) for channel in lamp.colour)
    return _entity(
        guids.next(lamp.id),
        "light",
        [
            *(pair if pair[0] != "spawnflags" or not getattr(lamp, "exploder", None)
              else ("spawnflags", EXPLODER_SPAWNFLAGS) for pair in LIGHT_KEYS),
            # Per lamp, not a constant: a run-time omni shadow costs one of
            # the map's ``numOmniShadowSlices`` and lights past that number
            # trade the slice between them as the camera moves.  See
            # :attr:`zmforge.blueprint.elements.Lamp.shadows`.
            ("PRIMARY_NOSHADOWMAP", "0" if lamp.shadows else "1"),
            ("_color", colour),
            ("radius", decimal_token(lamp.radius)),
            ("stops", decimal_token(stops)),
            ("origin", _vector(lamp.position)),
            # Only for a lamp that asks: the glow it throws into lit fog.
            *((("volumetric", "1"),) if getattr(lamp, "volumetric", False) else ()),
            *_exploder_keys(lamp),
        ],
    )



def _fx_entity(effect: AmbientFx, guids: _Guids) -> Entity:
    """One Radiant ``fx`` entity, keyed as the stock prefabs key theirs
    (``_prefabs/zm/zm_giant``: ``fxdef``, ``delay``, ``fxstate1``-``4``,
    ``primaryLightFraction``, ``timescale``).  A negative ``delay`` starts
    the loop part-way through, so neighbouring fires do not flicker in step;
    it is derived from the id so a build is repeatable."""
    import zlib

    delay = -(zlib.crc32(effect.id.encode()) % 20000) - 1
    return _entity(
        guids.next(effect.id),
        "fx",
        [
            ("fxdef", effect.fx),
            ("origin", _vector(effect.position)),
            ("angles", _angle_text(Angles(effect.pitch, effect.yaw, 0.0))),
            ("delay", str(delay)),
            ("fxstate1", "1"),
            ("fxstate2", "1"),
            ("fxstate3", "1"),
            ("fxstate4", "1"),
            ("primaryLightFraction", "1"),
            ("timescale", "1"),
        ],
    )

#: The keys a script-switched lamp adds, as the stock perk lights carry them
#: (``_prefabs/zm/zm_core/vending_marathon_struct.map``, light_marathon_001:
#: ``exploderDisabled 1``, ``exploderFade 1``, ``exploder_count 1``,
#: ``exploder_index_0 "ver=2 ... name=lgt_vending_stamina_up"``).  37 of the 85
#: stock exploder lights in the shipped prefabs and mp maps are omnis with
#: exactly these plus ``spawnflags 82`` (a plain lamp here is 66).
EXPLODER_SPAWNFLAGS = "82"


def _exploder_keys(lamp: Lamp) -> tuple[tuple[str, str], ...]:
    name = getattr(lamp, "exploder", None)
    if not name:
        return ()
    return (
        ("exploderDisabled", "1"),
        ("exploderFade", "1"),
        ("exploder_count", "1"),
        ("exploder_index_0", f"ver=2 don=0 doff=0 fin=0 fout=0 off=0 name={name}"),
    )


def _enclosure_entities(enclosure: Enclosure, guids: _Guids) -> list[Entity]:
    from .. import lighting
    from ..materials import SUN_VOLUME, UMBRA_VOLUME
    from ..mapsource.scalars import decimal_token

    cage = enclosure.cage
    if cage is None:  # pragma: no cover - resolve_enclosure runs first
        raise ValueError("the enclosure has not been resolved against the geometry")
    inside = cage.inner.shrunk(enclosure.margin)
    entities = [
        _volume_entity(
            guids,
            f"{enclosure.id}_sun",
            "volume_sun",
            inside,
            SUN_VOLUME,
            [
                ("ssi", enclosure.sun_preset),
                ("ssi1", enclosure.sun_preset),
                ("grid_density", str(int(enclosure.grid_density))),
                ("shadowBiasScale", "1"),
                # The pair The Giant ships, not the database default.  A
                # cascade has a fixed texture budget, so the distance it
                # covers sets how coarse a sun shadow edge is, and 2000 --
                # which no shipped map uses -- is what puts a saw along
                # stair flights.  See
                # :data:`zmforge.lighting.SUN_SHADOW_SPLIT_DISTANCE`.
                ("shadowSplitCount", str(int(lighting.SUN_SHADOW_SPLIT_COUNT))),
                (
                    "shadowSplitDistance",
                    decimal_token(lighting.SUN_SHADOW_SPLIT_DISTANCE),
                ),
                ("streamLighting", "1"),
            ],
            contents=(),
        ),
        _volume_entity(
            guids,
            f"{enclosure.id}_umbra",
            "umbra_volume",
            inside,
            UMBRA_VOLUME,
            contents=(),
        ),
        _volume_entity(
            guids,
            f"{enclosure.id}_fpstool",
            "volume_fpstool",
            inside,
            CAULK,
            contents=(),
        ),
    ]
    if enclosure.fog is not None:
        # One ``volume_worldfog`` over the playable space, keyed the way
        # ``zm_giant_light.map:4346-4362`` keys its own (zmforge.atmosphere).
        from ..atmosphere import fog_volume_pairs
        from ..materials import FOG_VOLUME

        entities.append(
            _volume_entity(
                guids,
                f"{enclosure.id}_fog",
                "volume_worldfog",
                inside,
                FOG_VOLUME,
                fog_volume_pairs(enclosure.fog, enclosure.fog_time),
                contents=(),
            )
        )
    lit_fog = getattr(enclosure, "lit_fog", None)
    if lit_fog is not None:
        # The fog you can see: a ``volume_litfog`` over the playable space,
        # keyed the way ``zm_giant_light.map:4136-4154`` keys The Giant's own
        # map-wide one, and a nested one per denser pocket (zmforge.atmosphere).
        from ..atmosphere import lit_fog_volume_pairs
        from ..materials import LITFOG_VOLUME

        entities.append(
            _volume_entity(
                guids,
                f"{enclosure.id}_litfog",
                "volume_litfog",
                inside,
                LITFOG_VOLUME,
                lit_fog_volume_pairs(lit_fog, enclosure.fog_time),
                contents=(),
            )
        )
        for index, (box, pocket_fog) in enumerate(getattr(enclosure, "lit_fog_pockets", ())):
            entities.append(
                _volume_entity(
                    guids,
                    f"{enclosure.id}_litfog_pocket{index}",
                    "volume_litfog",
                    box,
                    LITFOG_VOLUME,
                    lit_fog_volume_pairs(pocket_fog, enclosure.fog_time, priority=2),
                    contents=(),
                )
            )
    entities.append(_catch_volume_entity(enclosure, guids))
    return entities


def _probe_entities(blueprint, enclosure: Enclosure | None, guids: _Guids) -> list[Entity]:
    """One ``reflection_probe`` per room, its box sized to that room.

    The box is the indirect-lighting solve's domain, not a gloss decoration:
    ``t7.def.json`` files most of the probe's keys under ``2_DIFFUSE_GI`` and
    describes ``brightnessAdjust`` as scaling the bounce brightness during
    the bake.  Geometry inside no probe has no bounce.

    ``size_min`` and ``size_max`` are half-extents on the negative and the
    positive side, so an enclosing box is half the room's interior size on
    each, and the two are equal because the probe stands at the centre.
    ``in_play_space`` follows the database's own rule rather than the
    template's constant ``1`` -- see :func:`zmforge.lighting.probe_in_play_space`.

    Naming follows what Radiant leaves in a real map: the first is ``probe``
    and the rest are ``probe_001`` upwards, which is how the 23 probes in
    ``zm_alien_isolation.map`` are named.
    """
    from ..lighting import probe_in_play_space

    if enclosure is None or not enclosure.probe:
        return []
    entities: list[Entity] = []
    for index, (owner, box) in enumerate(blueprint.probe_boxes()):
        size = box.size
        half = _vector(Point(size.x / 2.0, size.y / 2.0, size.z / 2.0))
        entities.append(
            _entity(
                guids.next(f"{owner}_probe"),
                "reflection_probe",
                [
                    *REFLECTION_PROBE_KEYS,
                    ("name", "probe" if index == 0 else f"probe_{index:03d}"),
                    ("size_min", half),
                    ("size_max", half),
                    ("in_play_space", "1" if probe_in_play_space(size) else "0"),
                    ("origin", _vector(box.centre)),
                ],
            )
        )
    return entities


#: What a shipped kill volume does to whatever enters it.  ``zm_giant_geo.map``
#: entity 2 uses ``"dmg" "1000"``; ``mp_sector_geo.map`` entity 1 uses
#: ``"10000"``.  Either is far past a player's health; the lower one is The
#: Giant's, so it is the zombies number.
CATCH_VOLUME_DAMAGE = "1000"


def _catch_volume_entity(enclosure: Enclosure, guids: _Guids) -> Entity:
    """A ``trigger_hurt`` slab under the whole map: the floor of last resort.

    A player who gets through the world anywhere -- a terrain seam, a gap
    at a wall foot, a hole in a floor -- lands in the void inside the sky shell and is
    stuck there, alive, with nothing to kill or reset them.  The shipped
    answer is not a script: ``share/raw/scripts`` has no fell-out-of-world
    handler at all, and ``trigger_hurt`` is engine-side (the scripts only
    react to it, e.g. ``zombie_utility.gsc:2543 case "MOD_TRIGGER_HURT":``).
    It is a brush volume, and it appears exactly six times in the shipped
    ``.map`` files: two each in ``zm_giant_geo.map``, ``mp_sector_geo.map``
    and ``mp_combine_geo.map``, always a floor slab plus a ceiling slab,
    always with faces of material ``trigger``.  ``zm_giant_geo.map`` entity 2
    verbatim::

        "classname" "trigger_hurt"
        "dmg" "1000"
        "_color" "1 0.3 0.1"
        "script_hazard" "false"
        // brush with faces of material `trigger`

    Killing the player is the shipped behaviour, not teleporting them: in
    zombies that means they go down where the others can revive them, or the
    round ends, and either way play continues.

    Extent and depth come from the enclosure rather than from a constant, so
    the slab scales with whatever gap a map leaves under itself.  It fills the
    bottom half of that gap across the enclosure's whole inner footprint: its
    top is therefore ``gap / 2`` below the lowest geometry in the map --
    clear of any floor a player can stand on -- and its bottom rests on the
    shell, so nothing can pass it without leaving sealed space.
    """
    cage = enclosure.cage
    assert cage is not None  # resolve_enclosure runs first
    inside = cage.inner.shrunk(enclosure.margin)
    lid = inside.mins.z + enclosure.gap / 2.0
    box = Span.between(
        inside.mins,
        Point(inside.maxs.x, inside.maxs.y, lid),
    )
    return _volume_entity(
        guids,
        f"{enclosure.id}_catch",
        "trigger_hurt",
        box,
        TRIGGER,
        [
            ("dmg", CATCH_VOLUME_DAMAGE),
            ("script_hazard", "false"),
            ("_color", "1 0.3 0.1"),
        ],
        contents=("detail",),
    )


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------
def build_document(blueprint, *, worldspawn_overrides: Sequence[tuple[str, str]] = ()) -> Document:
    """Turn a blueprint into a whole map-source document.

    The enclosure is resolved first, so its slabs are computed from the final
    geometry rather than from whatever the caller guessed (spec 8.6).
    """
    from ..materials import SKY

    guids = _Guids(blueprint.identity)
    doc = Document(layers=list(PREFAB_LAYERS))

    world = _entity(guids.next("worldspawn"), "worldspawn", [], layer=None)
    overrides = dict(worldspawn_overrides)
    # A night map names its own sky model (zmforge.atmosphere); a caller's
    # explicit override still wins.
    for _enclosure in blueprint.elements(Enclosure):
        if getattr(_enclosure, "skybox", None):
            overrides.setdefault("skyboxmodel", _enclosure.skybox)
        # Gloom: the colour grade and the exposure pin, worldspawn keys the
        # way zm_giant.map's worldspawn writes them (zmforge.atmosphere).
        from ..atmosphere import worldspawn_pairs

        for _key, _value in worldspawn_pairs(
            _enclosure.sun_preset,
            getattr(_enclosure, "grade", None),
            getattr(_enclosure, "exposure_stops", None),
        ):
            overrides.setdefault(_key, _value)
    # Enough run-time omni shadow slices for every lamp that asks for one.
    # Short of that the engine hands the slices out from where the camera is,
    # so a shadow comes and goes as the player walks
    # (:func:`zmforge.lighting.omni_shadow_slices`).
    overrides.setdefault(
        "numOmniShadowSlices",
        str(
            lighting.omni_shadow_slices(
                sum(1 for lamp in blueprint.elements(Lamp) if lamp.shadows)
            )
        ),
    )
    for key, value in WORLDSPAWN_KEYS:
        world.pairs.append((key, overrides.pop(key, value)))
    for key, value in overrides.items():
        world.pairs.append((key, value))
    doc.entities.append(world)

    def add_solid(solid: Solid, element_id: str, layer: str) -> None:
        brush = _brush_of(solid, guids.next(element_id))
        brush.layer = layer
        world.solids.append(brush)

    for room in blueprint.elements(Room):
        for solid in _room_solids(room):
            add_solid(solid, room.id, room.layer)
    for yard in blueprint.elements(Yard):
        for solid in _yard_solids(yard):
            add_solid(solid, yard.id, yard.layer)
    # The drawn wall under each barricade opening (blueprint/windows.py):
    # nonColliding, so collision and the navmesh are the hole's as before.
    for window in blueprint.elements(Window):
        sill = sill_wall_solid(blueprint, window)
        if sill is not None:
            add_solid(sill, f"{window.id}_sill", window.layer)
    named: dict[str, Entity] = {}
    for massing in blueprint.elements(Massing):
        if massing.targetname:
            # A scripted brush group (Massing.targetname): one
            # script_brushmodel per name, which a script can hide.
            entity = named.get(massing.targetname)
            if entity is None:
                entity = _entity(guids.next(f"{massing.id}_entity"), "script_brushmodel",
                                 [("targetname", massing.targetname)])
                named[massing.targetname] = entity
                doc.entities.append(entity)
            for solid in massing.solids:
                entity.solids.append(_brush_of(solid, guids.next(massing.id)))
            continue
        for solid in massing.solids:
            add_solid(solid, massing.id, massing.layer)
    for terrain in blueprint.elements(Terrain):
        if terrain.style == "columns":
            for solid in _terrain_columns(terrain):
                add_solid(solid, terrain.id, terrain.layer)
        else:
            for patch in _terrain_patches(terrain, guids):
                patch.layer = terrain.layer
                world.solids.append(patch)
            for step, plinth in enumerate(_terrain_plinth(terrain)):
                add_solid(plinth, f"{terrain.id}_plinth_{step}", terrain.layer)

    enclosure = blueprint.resolve_enclosure()
    if enclosure is not None and enclosure.cage is not None:
        for slab in enclosure.cage.slabs:
            add_solid(
                block(slab.box, FaceMaterials.uniform(SKY), note="sky shell"),
                f"{enclosure.id}_shell",
                enclosure.layer,
            )

    # Gameplay entities, in a stable order so the file is reproducible.
    for zone in blueprint.elements(Zone):
        doc.entities.append(
            _volume_entity(
                guids,
                zone.id,
                "info_volume",
                zone.bounds,
                CAULK,
                [
                    ("targetname", zone.name),
                    ("script_noteworthy", "player_volume"),
                    ("target", zone.spawn_set),
                ],
            )
        )
    for start in blueprint.elements(PlayerStart):
        from ..blueprint.respawn import respawn_groups

        start_zone = next((z.name for z in blueprint.elements(Zone) if z.starting), "")
        doc.entities.extend(_player_start_entities(
            start, guids, respawn_groups(blueprint), start_zone))
    for spawn in blueprint.elements(Spawn):
        doc.entities.extend(_spawn_entities(spawn, guids))
    for trav in blueprint.elements(Traversal):
        doc.entities.extend(_traversal_entities(trav, guids))
    for window in blueprint.elements(Window):
        doc.entities.append(
            _entity(
                guids.next(window.id),
                "misc_prefab",
                [
                    ("model", window.prefab),
                    ("script_string", window.link_tag),
                    ("origin", _vector(window.barricade_origin)),
                    ("angles", _angle_text(Angles.facing_yaw(window.barricade_yaw))),
                ],
            )
        )
    for door in blueprint.elements(Door):
        doc.entities.extend(_door_entities(door, guids))
    for machine in blueprint.elements(Machine):
        doc.entities.append(_machine_entity(machine, guids))
    for weapon in blueprint.elements(WallWeapon):
        doc.entities.extend(_wall_weapon_entities(weapon, guids))
    for box in blueprint.elements(MysteryBox):
        doc.entities.extend(_mystery_box_entities(box, guids))
    for fizz in blueprint.elements(Wunderfizz):
        doc.entities.append(_wunderfizz_entity(fizz, guids))
    for switch in blueprint.elements(PowerSwitch):
        yaw = fixed.prefab_yaw(switch.facing, fixed.POWER_SWITCH_FRONT_ZERO)
        doc.entities.append(
            _entity(
                guids.next(switch.id),
                "misc_prefab",
                [
                    ("model", fixed.POWER_SWITCH_PREFAB),
                    ("origin", _vector(switch.position)),
                    ("angles", _angle_text(Angles.facing_yaw(yaw))),
                ],
            )
        )
    for prefab in blueprint.elements(Prefab):
        doc.entities.append(_prefab_entity(prefab, guids))
    for lamp in blueprint.elements(Lamp):
        doc.entities.append(_lamp_entity(lamp, blueprint.stops_of(lamp), guids))
    for effect in blueprint.elements(AmbientFx):
        doc.entities.append(_fx_entity(effect, guids))
    for scatter in blueprint.elements(PropScatter):
        for index, prop in enumerate(scatter.props):
            if prop.dynamic:
                # A model the compiler cannot resolve and the game can: see
                # Prop.dynamic for the probe that established the difference.
                # No collmap key, no `static`, no lighting states -- none of
                # them mean anything on an entity cod2map64 does not bake.
                doc.entities.append(
                    _entity(
                        guids.next(prop.id),
                        "script_model",
                        [
                            ("model", prop.model),
                            ("modelscale", _number(prop.scale)),
                            ("origin", _vector(prop.origin)),
                            ("angles", _angle_text(Angles(prop.pitch, prop.yaw, prop.roll))),
                        ],
                    )
                )
                continue
            # Some stock models are half of an assembly.  A staircase frame
            # placed on its own draws its handrails and nothing between them,
            # because its treads are a separate model Treyarch places once per
            # step; see catalogue.MODEL_COMPANIONS for the prefab that was
            # read for each offset.  The parts are walk-through whatever the
            # frame is: the frame carries the assembly's collision, and a
            # tread with a collmap of its own would step the player up a prop
            # the navmesh does not know about.
            for part_index, (part_model, part_origin) in enumerate(
                fixed.companion_origins(
                    prop.model, tuple(prop.origin), prop.yaw, prop.scale
                )
            ):
                doc.entities.append(
                    _entity(
                        guids.next(f"{prop.id}_part_{part_index}"),
                        "misc_model",
                        [
                            ("model", part_model),
                            ("no_collmap", "1"),
                            ("static", "1"),
                            ("modelscale", _number(prop.scale)),
                            ("lightingstate1", "1"),
                            ("lightingstate2", "1"),
                            ("lightingstate3", "1"),
                            ("lightingstate4", "1"),
                            ("origin", _vector(Point(*part_origin))),
                            ("angles", _angle_text(Angles(prop.pitch, prop.yaw, prop.roll))),
                        ],
                    )
                )
            doc.entities.append(
                _entity(
                    # The prop's own name, not its place in the scatter: that
                    # is what lets a map rebuilt from the shared document -
                    # where every prop in the map is one list - write the same
                    # GUIDs as the recipe that placed them in twenty-five.
                    guids.next(prop.id),
                    "misc_model",
                    [
                        ("model", prop.model),
                        # Measured on the mod tools install: cod2map64
                        # resolves the collmap by filename under
                        # share/raw/collmaps at compile time, so use_collmap
                        # bakes collision for a stock model too -- 25 crates
                        # took the probe BSP from 26,484 to 31,176 bytes and
                        # its navmesh from 6,678 to 7,315, which is the
                        # zombies routing around them.
                        ("use_collmap", "1") if prop.solid else ("no_collmap", "1"),
                        ("static", "1"),
                        ("modelscale", _number(prop.scale)),
                        ("lightingstate1", "1"),
                        ("lightingstate2", "1"),
                        ("lightingstate3", "1"),
                        ("lightingstate4", "1"),
                        ("origin", _vector(prop.origin)),
                        ("angles", _angle_text(Angles(prop.pitch, prop.yaw, prop.roll))),
                    ],
                )
            )
    if enclosure is not None:
        doc.entities.extend(_enclosure_entities(enclosure, guids))
    doc.entities.extend(_probe_entities(blueprint, enclosure, guids))

    for imported in blueprint.elements(ImportedMap):
        for entity in imported.document.entities:
            if entity.classname == "worldspawn":
                world.solids.extend(entity.solids)
            else:
                doc.entities.append(entity)

    return doc


def _number(value: float) -> str:
    from ..mapsource.scalars import decimal_token

    return decimal_token(value)
