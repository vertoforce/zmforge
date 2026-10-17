"""What a barricade window looks like: the sill wall below it and the closet behind.

A barricade opening is cut from the floor (``model.WINDOW_SILL`` = 0), because
the stock prefab's AI traversal channel starts there.  Cut and left at that,
the hole reads as a doorway with boards hung in its top half and a bright
pocket showing under them (a zombie window
must show wall to waist height).  A zombie window is a
window: solid wall to waist height, boards above, a dark yard behind.

The sill wall here is drawn and does not collide (``contents nonColliding;``,
the stock way to draw a brush that nothing touches: 11,484 brushes in the
shipped prefabs carry it, most with art materials).  So the hole, the
traversal channel, the prefab's clips and the navmesh are exactly what they
were; only what the player sees changes.  Its height comes from the stock
prefab and Treyarch's scale sheet, measured, not guessed:

- ``barricade_reciever_wood.map``: the ``clip_ai``/``clip_missile`` sill band
  is ``z 0..35`` and the ``traverse`` channel ``z 0..40``; the zbarrier (the
  boards) stands at ``z 31``.
- the mod tools' ``Scale_Standards.pdf``: window sill 32.

:data:`SILL_WALL_HEIGHT` is 32: Treyarch's sill, inside the prefab's 35-unit
band that already stops zombies and bullets, and under the 40-unit channel
top the climb-in animation plants its hands on.

The closet behind (``Yard``) gets dark, weathered materials and one dim warm
lamp per window beside its opening, never the default full-strength lamp at
the yard's centre: three windows on one wall stacked three such lamps at one
point, which reads as an overexposed white box.  Check
``Z85`` (:func:`zmforge.verify.windows.check_windows`) holds both.
"""

from __future__ import annotations

from ..materials import CAULK, FaceMaterials, Material
from ..solids.forms import block
from ..spatial import Point, Side, Span

__all__ = [
    "CLOSET_FLOOR",
    "CLOSET_LAMP_COLOUR",
    "CLOSET_LAMP_RADIUS",
    "CLOSET_LAMP_MAX_LUMA",
    "CLOSET_MATERIALS",
    "CLOSET_PROPS",
    "NONCOLLIDING",
    "BRIGHT_MATERIALS",
    "PLACEHOLDER_MATERIALS",
    "SILL_WALL_HEIGHT",
    "closet_prop_spots",
    "sill_wall_box",
    "sill_wall_solid",
]

#: The drawn wall under a barricade opening, from the floor surface up.
SILL_WALL_HEIGHT = 32.0

#: Drawn, collides with nothing: the stock prefabs' own contents for art
#: brushes that must not change collision or the navmesh.
NONCOLLIDING = ("nonColliding",)

#: A closet's walls, floor and lid: dark, stained, stock materials, so the
#: pocket behind a window reads as a service void and not a lit showroom.
#: The old default was bare dark concrete on a smooth trowelled slab, which the
#: full-strength yard lamp blew out to a flat grey-white.
CLOSET_MATERIALS = {
    "wall": "t7_brick_worn_heavy_grout_red",
    "floor": "t7_concrete_pebbles_cracked",
    "ceiling": "t7_metal_rust_ceiling_01",
}
CLOSET_FLOOR = CLOSET_MATERIALS["floor"]

#: Tool and default materials: drawn as nothing or as a flat untextured
#: colour.  A sill or closet in one of these is the "blank box" the check
#: refuses.
PLACEHOLDER_MATERIALS = frozenset({
    "caulk", "clip", "clip_player", "clip_ai", "clip_missile", "nodraw",
    "trigger", "sky", "portal", "hint", "lightmap_gray", "$default",
    "default", "white",
})

#: Real materials, but white: fine on a room wall, a glare box on a closet's
#: walls or floor behind the boards.
BRIGHT_MATERIALS = frozenset({
    "t7_plastic_panels_white", "t7_plaster_smooth_light_01",
    "t7_concrete_worn_painted_white", "t7_ceramic_tile_large_white",
    "t7_ceramic_tile_shower_white", "t7_plastic_molding_trim_white",
})

#: The closet lamp: one per window, over its riser, a warm low fill.  The
#: colour is the dimmer: its luma is about 0.34, a stop and a half under a
#: white room lamp at the same ``stops`` (``verify.lightlevel`` weighs a lamp
#: by ``luma(colour)``), and the radius reaches the closet, not the room.
CLOSET_LAMP_COLOUR = (0.45, 0.32, 0.22)
CLOSET_LAMP_RADIUS = 192.0
#: Brighter than this luma, the closet lamp is the glare the check refuses.
CLOSET_LAMP_MAX_LUMA = 0.5

#: Clutter stacked against a closet's far wall, either side of the riser: stock
#: models that link on every map (``catalogue.PROP_PALETTE``), non-solid so
#: they never stop a zombie.
CLOSET_PROPS = ("p7_crate_wood_01", "p7_debris_concrete_rubble_sm_02")


def _room_and_opening(blueprint, window):
    room = blueprint.find(window.room_id)
    if room is None or not 0 <= window.aperture_index < len(room.apertures):
        return None, None
    return room, room.opening(window.aperture_index)


def sill_wall_box(blueprint, window) -> Span | None:
    """The drawn sill wall of ``window``: the hole's own box, floor to
    :data:`SILL_WALL_HEIGHT`.  ``None`` when the hole already starts at or
    above that (a raised opening has real wall under it) or cannot be found."""
    room, opening = _room_and_opening(blueprint, window)
    if opening is None:
        return None
    box = opening.box
    top = room.floor_z + SILL_WALL_HEIGHT
    if box.mins.z >= top - 1e-6:
        return None
    return Span(box.mins, Point(box.maxs.x, box.maxs.y, min(top, box.maxs.z)))


def sill_wall_solid(blueprint, window):
    """The sill wall as a drawn, non-colliding brush, or ``None``.

    The face into the room carries the room's wall, the top the same, the face
    into the closet the closet's wall; the two ends touching the jambs and the
    bottom on the slab are caulk."""
    box = sill_wall_box(blueprint, window)
    if box is None:
        return None
    room, _ = _room_and_opening(blueprint, window)
    inside = room.materials.for_side(window.side)
    yard = blueprint.find(window.yard_id) if window.yard_id else None
    outside = yard.materials.wall if yard is not None else inside
    outward = window.side
    faces = FaceMaterials(
        default=CAULK,
        per_side={
            outward.opposite: Material.of(inside),
            outward: Material.of(outside),
            Side.TOP: Material.of(inside),
        },
    )
    return block(box, faces, NONCOLLIDING, note="window sill")


def closet_prop_spots(yard, window_origin: Point, outward_step: Point,
                      reach: float, spread: float) -> list[Point]:
    """Two floor points against the closet's far wall, ``spread`` either side
    of the window's axis and clear of the riser ``reach`` out."""
    interior = yard.interior
    axis_out = "x" if abs(outward_step.x) > 0.5 else "y"
    sign = outward_step.x if axis_out == "x" else outward_step.y
    far = (interior.maxs if sign > 0 else interior.mins)
    far_v = getattr(far, axis_out) - sign * 28.0
    spots = []
    for side in (-1.0, 1.0):
        if axis_out == "x":
            p = Point(far_v, window_origin.y + side * spread, yard.floor_z)
        else:
            p = Point(window_origin.x + side * spread, far_v, yard.floor_z)
        if interior.holds_flat(p.x, p.y):
            spots.append(p)
    return spots
