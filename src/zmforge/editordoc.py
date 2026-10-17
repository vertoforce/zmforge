"""A :class:`~zmforge.blueprint.model.Blueprint` as a map editor's own document.

This is the ``editor`` half of the shared map document (:mod:`zmforge.mapdoc`):
the editor-format projection of a map a recipe built, written for a map editor
that reads this document, so that opening a generated map in an editor is a
*read* rather than a reconstruction.

Without an ``editor`` section, an editor that opens a generated map has to
rebuild the geometry from the ``.map`` text.  That
reconstruction has to guess: wall thickness is the
mode of the upright thicknesses rather than a measurement, the floor-slab
convention is sniffed, storeys are inferred from the room under an entity, which is wrong for
most entities in a stack of storeys, terrain noise
parameters are invented, and anything that is not a box brush or a patch mesh
is dropped.  Every one of those numbers is *authored* on the blueprint.  This
module hands them over.

It is the mirror of the editor's own translator, which goes the
other way, and the two agree on the conventions that let the geometry cross
without arithmetic: a room's footprint is the outer face of its walls, ``z`` is
the bottom of the floor slab, ``height`` is floor bottom to ceiling top, an
opening's ``sill`` is measured up from the floor *surface*, and an item's ``z``
is a world height.

What does not fit
-----------------
The editor's document is a smaller model than a blueprint, and where a field has
nowhere to go this module **says so in the document's own ``notes``** rather
than dropping it quietly:

* **Wall thickness is one number for the whole map** -- for the *tool*.  The
  blueprint carries one per room, and a room built from measured geometry keeps
  its own wall thickness (7.032 units, say, against the map's 16), so each
  room is written with its own ``wall`` and the map-wide number is the mode: a
  sensible default thickness for the next room an editor draws.
* **A buyable door is a leaf in a room's doorway, or a gate on a flight.**  A
  door hung in a free span over the head of a stair flight -- which is how a
  zone above another one gets bought, there being no wall between two storeys of
  the same shaft -- has no opening to point at.  It points at the flight
  instead: :func:`~zmforge.solids.forms.stair_gate` derives the box from the
  flight and the editor derives the same box from the same
  flight, so the document carries ``stairs: <flight id>`` and no arithmetic
  crosses.  A door hung in a free span that is *neither* -- some box of its own
  over open floor -- still has nowhere to go, and is written with its price and
  its flag and neither an opening nor a flight.
* **Barricade windows, yards and risers** are one thing in the engine and four
  in the editor.  The hole is a room opening, the riser is a zombie spawner, and
  the yard's five walls are written as blocks, because the editor has no yard.
  The boarded prefab rides on the opening as ``barricade``: which prefab, which
  riser, and the ``script_string`` token joining the two.  Nothing else about it
  is stored -- its origin and heading fall out of the wall and the hole -- so
  the editor rebuilds the same entity and a zombie still climbs in.  The
  yard's floor slab is ``walkable`` and not ``reachable``, which is what lets
  the riser find ground under it without asking the playable-area check to
  cover a pocket no player reaches.
* **Terrain noise parameters** are not on the blueprint either -- only the
  heights the noise produced, which are written exactly.

The heavier losses -- generated wall art, imported geometry, custom GSC,
per-prop collision boxes -- are not losses here at all: they ride in the
``engine`` section of the same file, which an editor carries through untouched
(:data:`zmforge.mapdoc.ENGINE_ONLY`).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["FORMAT", "editor_document"]

#: The editor's format string.  An editor that reads this document spells the
#: same one.
FORMAT = "zmforge-editor/1"

#: The ``script_string`` a spawn struct carries when nothing links it to a
#: barricade -- the default of
#: :meth:`~zmforge.blueprint.model.Blueprint.add_riser`, left out of the
#: document so only a real link is written.
DEFAULT_LINK_TAG = "find_flesh"

#: The editor's grid, in world units.  It is editor state -- what a drag snaps
#: to -- and the blueprint has no opinion, so this is only a starting value.
DEFAULT_GRID = 16.0

#: Fallback wall thickness for a map with no rooms in it at all.
DEFAULT_WALL_THICKNESS = 16.0

#: What the editor calls a material it has no game asset name for.  Only used
#: for a massing that no call authored, which a recipe cannot produce.
FALLBACK_TEXTURE = "concrete"


def editor_document(blueprint: Any) -> dict:
    """The editor-format document for ``blueprint``.

    Pure translation: nothing is read off disk, nothing is written, and the
    blueprint is not changed.  Keys are the editor's, in the editor's spelling,
    with every section present even when empty -- a missing section is a section
    a reader has to guard against, and both sides would rather diff an empty
    list than a ``None``.
    """
    from .blueprint.elements import Lamp

    rooms = _rooms_of(blueprint)
    thickness = _wall_thickness(rooms)
    openings = _opening_ids(rooms)
    lost: list[str] = []

    barricades = _barricades(blueprint)
    doc = {
        "format": FORMAT,
        "name": blueprint.name,
        "title": str(blueprint.title or ""),
        "description": "",
        "grid": DEFAULT_GRID,
        "wall_thickness": thickness,
        "rooms": [_room(room, barricades) for room in rooms],
        "stairs": [],
        "ramps": [],
        "blocks": [],
        "terrains": _terrains(blueprint, lost),
        "zones": _zones(blueprint),
        "doors": _doors(blueprint, openings, lost),
        "items": _items(blueprint, rooms),
        "props": _props(blueprint, rooms),
        "materials": [],
        "pictures": [],
        # How large one tile of a texture is laid, for every texture in this map
        # that is not laid at the editor's default 64.  A scale belongs to the
        # image and not to the wall -- a photographed surface that depicts 20
        # units of real wall has to cover 20 units or its grain reads at the
        # wrong size -- and the editor's document holds a texture *name*, so
        # without this table every photographed face comes back at 64 against
        # the 20 or 24 its photograph asks for.
        "texture_scales": {},
        "lights": _lights(blueprint, rooms),
        "probes": _probes(blueprint, rooms),
        "enclosure": _enclosure(blueprint),
        "lighting": {
            "mode": "placed" if blueprint.elements(Lamp) else "auto",
            # Every generated map is sealed in a sky shell; the editor's switch
            # only turns the 3D view's sky on and off.
            "sky": True,
            "brightness_stops": float(getattr(blueprint, "brightness_stops", 0.0)),
        },
        "presentation": {
            "loading_image": {
                # What a commit actually draws: the map's own plan view.
                "source": "plan",
                "plan": {"caption": True, "theme": "dark"},
                "upload": None,
            }
        },
        "notes": "",
    }
    _massing_into(blueprint, doc, lost)
    doc["texture_scales"] = _texture_scales(blueprint, doc, lost)
    # The order the map was built in.  A `.map` is written class by class --
    # every room's brushes, then every yard's, then every massing's -- so which
    # call came first is in the file, and it cannot be read back out of the
    # boxes: a flight of stairs, a ramp and a block are one class and three of
    # the editor's lists.  Written as ids rather than as a number on every
    # record so that it is one line to read and so an element the editor adds
    # later simply is not in it.
    doc["element_order"] = [str(element.id) for element in blueprint.elements()]
    doc["notes"] = _notes(blueprint, lost)
    return doc


def _enclosure(blueprint: Any) -> dict:
    """The sky shell's own numbers, which are not drawn and cannot be measured.

    Every map is sealed in six sky slabs a clear distance outside the playable
    bounds, and the distance is the recipe's choice: a test map asks
    for 192 units where the default is 128.  Nothing in the finished geometry
    says which was asked for -- the slabs are where they are -- so a document
    that did not carry the gap rebuilt the map inside a shell 64 units tighter on
    every side, six brushes different in a file that otherwise agreed.

    The element's ``id`` rides here too, because a GUID is
    ``sha256(seed, element id, ordinal)``: a shell written under ``enclosure_0``
    instead of ``enclosure`` is the same six boxes with six different GUIDs.
    """
    from .blueprint.elements import Enclosure

    found = blueprint.elements(Enclosure)
    if not found:
        return {}
    enclosure = found[0]
    return {
        "id": enclosure.id,
        "gap": float(enclosure.gap),
        "thickness": float(enclosure.thickness),
        "sun_preset": str(enclosure.sun_preset),
    }


def _texture_scales(blueprint: Any, doc: dict, lost: list[str]) -> dict:
    """``{texture name: [u, v]}`` for every surface not laid at the default.

    Collected from the materials the blueprint holds rather than from the boxes,
    because that is where a scale lives (:class:`zmforge.materials.Material`:
    "it is on the material rather than on the face because the size belongs to
    the image, not to the wall").  Restricted to names this document actually
    names as a texture, so a picture -- which is laid once at its own width and
    height by the element that hangs it, not tiled -- does not turn into a
    map-wide claim about its material.

    A name laid at two different sizes in one map cannot be written as a table
    and is reported instead of being written wrong; measured on
    a test map, none of its 49 materials is.
    """
    from .materials import Material

    used = _texture_names(doc)
    found: dict[str, set[tuple[float, float]]] = {}
    seen: set[int] = set()

    def walk(value: Any, depth: int = 0) -> None:
        if isinstance(value, Material):
            if value.scale is not None and value.name in used:
                found.setdefault(value.name, set()).add((value.scale, value.scale_v))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item, depth + 1)
            return
        if depth > 8 or not hasattr(value, "__dataclass_fields__"):
            return
        if id(value) in seen:
            return
        seen.add(id(value))
        for field_name in type(value).__dataclass_fields__:
            walk(getattr(value, field_name, None), depth + 1)

    for element in blueprint.elements():
        walk(element)
    table: dict[str, list[float]] = {}
    for name, sizes in sorted(found.items()):
        if len(sizes) > 1:
            lost.append(
                f"the texture {name!r} is laid at {len(sizes)} different sizes in this map "
                "and the document holds one size per texture, so the sizes other than the "
                "first are not carried"
            )
        scale, scale_v = sorted(sizes)[0]
        table[name] = [float(scale), float(scale_v)]
    return table


def _texture_names(doc: Mapping[str, Any]) -> set[str]:
    """Every material name this document names as a surface texture."""
    names: set[str] = set()
    for room in doc.get("rooms") or []:
        textures = room.get("textures") or {}
        for key in ("wall", "floor", "ceiling"):
            if textures.get(key):
                names.add(str(textures[key]))
        names.update(str(v) for v in (textures.get("sides") or {}).values() if v)
    for key in ("blocks", "stairs", "ramps", "terrains"):
        for record in doc.get(key) or []:
            if record.get("texture"):
                names.add(str(record["texture"]))
            # A block's per-side paint is a surface texture too, so a material
            # used only on a crate's lid still gets its size carried.
            names.update(str(v) for v in (record.get("faces") or {}).values() if v)
    return names


# ----------------------------------------------------------------------
# Rooms
# ----------------------------------------------------------------------
def _rooms_of(blueprint: Any) -> list:
    from .blueprint.elements import Room

    return list(blueprint.elements(Room))


def _wall_thickness(rooms: Iterable) -> float:
    """The document's map-wide thickness: the one most rooms are built at.

    Every room carries its own ``wall``; this is the map-wide default for the
    *next* room an editor draws, so it is the mode rather than the first or
    the mean: the number a room in this map actually has.
    """
    counts: dict[float, int] = {}
    for room in rooms:
        counts[float(room.thickness)] = counts.get(float(room.thickness), 0) + 1
    if not counts:
        return DEFAULT_WALL_THICKNESS
    return max(counts.items(), key=lambda pair: (pair[1], -pair[0]))[0]


def _opening_id(room: Any, index: int) -> str:
    return f"{room.id}_opening_{index}"


def _opening_ids(rooms: Iterable) -> dict[tuple, tuple[str, str]]:
    """Every cut opening, keyed by its box, so a door can find the hole it fills."""
    found: dict[tuple, tuple[str, str]] = {}
    for room in rooms:
        for index, box in enumerate(room.aperture_boxes):
            found.setdefault(_box_key(box), (room.id, _opening_id(room, index)))
    return found


def _barricades(blueprint: Any) -> dict[tuple[str, int], Any]:
    """Every barricade window, keyed by the room and aperture it was cut in.

    A :class:`~zmforge.blueprint.elements.Window` is four things the editor
    keeps apart -- the hole, the yard, the riser and the boarded prefab -- and
    the first three already cross on their own.  The fourth used to be dropped
    here with a line in ``notes``, which meant a map rebuilt from this document
    came back with the hole and the riser and no barricade over either, so
    nothing linked the two and no zombie ever climbed in.  What is written now
    is only what cannot be derived from the hole: which prefab, which riser,
    and the ``script_string`` token that joins them.
    """
    from .blueprint.elements import Window

    return {
        (window.room_id, window.aperture_index): window
        for window in blueprint.elements(Window)
    }


def _room(room: Any, barricades: Mapping[tuple[str, int], Any] | None = None) -> dict:
    outer = room.outer
    materials = room.materials
    barricades = barricades or {}
    return {
        "id": room.id,
        "name": _label(room.id),
        "x0": float(outer.mins.x),
        "y0": float(outer.mins.y),
        "x1": float(outer.maxs.x),
        "y1": float(outer.maxs.y),
        "z": float(outer.mins.z),
        "height": float(outer.maxs.z - outer.mins.z),
        "ceiling": bool(room.roofed),
        # This room's own walls.  The map-wide `wall_thickness` is what the Room
        # tool draws with; a room that disagrees carries its own number here, so a
        # room with 7.032-unit walls is not rebuilt at the map's 16, which would
        # move every inner face and push its doorway off the end of the wall the
        # editor thinks it has.
        "wall": float(room.thickness),
        # The map's own declaration that nobody gets into this room (`Room.reachable`):
        # a room to be seen into through a sealed pane and never stood in, or a prop
        # box narrower than the player.  Nothing in the geometry can work it out, and
        # the editor's "no way in" and "too small to stand in" checks need the answer.
        "reachable": bool(room.reachable),
        "textures": {
            "wall": materials.wall.name,
            "floor": materials.floor.name,
            "ceiling": materials.ceiling.name,
            "sides": {
                side.name.lower(): material.name
                for side, material in materials.sides.items()
            },
        },
        "openings": [
            _opening(room, index, aperture, barricades.get((room.id, index)))
            for index, aperture in enumerate(room.apertures)
        ],
    }


def _opening(room: Any, index: int, aperture: Any, window: Any | None) -> dict:
    record = {
        "id": _opening_id(room, index),
        "side": aperture.side.name.lower(),
        "center": float(aperture.offset),
        "width": float(aperture.width),
        "height": float(aperture.height),
        "sill": float(aperture.sill),
        # The blueprint has one kind of hole.  A hole with its bottom
        # off the floor is a window in the editor's words and a doorway
        # otherwise; the distinction is the editor's label and the shape
        # is the same either way.
        "kind": "window" if aperture.sill > 0.0 else "doorway",
    }
    if window is not None:
        # The barricade's own origin and heading are not stored: both fall out
        # of the wall and the hole (the interior face at the hole's centre, at
        # floor level, facing out), which is exactly how ``add_window`` derived
        # them, so moving the wall in the editor moves the barricade with it.
        record["barricade"] = {
            # The element's own id, because a GUID is
            # `sha256(seed, element id, ordinal)`: boards rebuilt under an id of
            # the editor's invention are the same entity with a different GUID,
            # and the join between this document and the `.map` is that GUID.
            "id": str(window.id),
            "prefab": str(window.prefab),
            "riser": str(window.riser_id),
            "link": str(window.link_tag),
            # The pocket the riser stands in.  Derivable -- it is the yard whose
            # interior holds the riser -- but written down because the editor
            # holds a yard as five blocks, and a reader should not have to
            # reassemble one to find out which.
            "yard": str(window.yard_id),
            "zone": str(window.zone_name),
        }
    return record


def _label(element_id: str) -> str:
    """A display name for a room, out of the word the recipe called it.

    The blueprint has no room name -- the id *is* the recipe's name for it --
    and the editor shows one in its lists, so `break_room` is shown as
    "Break Room" rather than left blank or renamed "Room 7" by the importer.
    """
    return str(element_id).replace("_", " ").strip().title()


# ----------------------------------------------------------------------
# Massing: blocks, stairs, ramps
# ----------------------------------------------------------------------
def _massing_into(blueprint: Any, doc: dict, lost: list[str]) -> None:
    """Every world box that is not part of a room shell.

    Read off :class:`~zmforge.blueprint.elements.AuthoredForm` -- what the call
    asked for -- and never off the solids it produced.  A flight of stairs is
    seventeen boxes by the time it is solids, and nothing in those boxes says
    they are one flight, which way it climbs or how tall a step is.
    """
    from .blueprint.elements import Massing, Yard
    from .spatial import Side

    unauthored = 0
    for massing in blueprint.elements(Massing):
        authored = getattr(massing, "authored", None)
        if authored is None:
            unauthored += len(massing.solids)
            for index, solid in enumerate(massing.solids):
                doc["blocks"].append(
                    _block_record(
                        f"{massing.id}_{index}" if len(massing.solids) > 1 else massing.id,
                        _solid_hull(solid),
                        FALLBACK_TEXTURE,
                        "solid",
                        walkable=massing.walkable,
                        reachable=massing.reachable,
                    )
                )
            continue
        if authored.form == "steps":
            doc["stairs"].append(
                {
                    "id": massing.id,
                    "x": float(authored.base.x),
                    "y": float(authored.base.y),
                    "z": float(authored.base.z),
                    "direction": _direction(authored.toward),
                    "steps": int(authored.steps),
                    "step_depth": float(authored.step_depth),
                    "step_rise": float(authored.step_rise),
                    "width": float(authored.width),
                    "texture": _texture(authored.materials),
                }
            )
        elif authored.form == "ramp":
            box = authored.box
            doc["ramps"].append(
                {
                    "id": massing.id,
                    "x0": float(box.mins.x),
                    "y0": float(box.mins.y),
                    "x1": float(box.maxs.x),
                    "y1": float(box.maxs.y),
                    "z0": float(box.mins.z),
                    "z1": float(box.maxs.z),
                    "direction": _direction(authored.toward),
                    "texture": _texture(authored.materials),
                }
            )
        else:
            doc["blocks"].append(
                _block_record(
                    massing.id,
                    authored.box,
                    _block_texture(authored.materials),
                    _block_kind(authored.materials),
                    walkable=massing.walkable,
                    reachable=massing.reachable,
                    facing=_block_facing(authored.materials),
                    faces=_block_faces(authored.materials),
                )
            )
    if unauthored:
        lost.append(
            f"{unauthored} world box(es) were built straight out of solids rather than "
            "through add_block/add_steps/add_wedge, so they are written here as plain "
            "blocks with a placeholder material"
        )

    # A yard is a five-sided pocket outside a room wall, where a barricade's
    # riser stands.  The editor has no yard, and calling one a room would put a
    # room in the document that is not in the map, so its shell is written as
    # what it is: boxes.
    for yard in blueprint.elements(Yard):
        for index, piece in enumerate(yard.shell.pieces):
            # The floor slab is the ground a barricade's riser stands on, so it
            # is walkable and *not* reachable: `ground_under` reads the first
            # and the playable-area check reads both, which is how a yard stays
            # out of the zone coverage it must never be in while still
            # answering "what is under this spawn struct?".  Written as neither,
            # the riser came back from a round trip with no floor under it and
            # was refused.  The four walls and the lid are neither.
            floor = piece.side is Side.BOTTOM
            block = _block_record(
                f"{yard.id}_{piece.side.name.lower()}_{index}",
                piece.box,
                yard.materials.for_side(piece.side).name,
                "solid",
                walkable=floor,
                reachable=False,
                # A shell piece shows its material on the face looking into
                # the pocket and caulk on the other five, which is
                # `RoomMaterials.hull_faces`.  Written without it, each of a
                # yard's six boxes came back painted on all six faces.
                facing=_side_name(piece.side.opposite),
            )
            # Which pocket the box is a piece of.  The editor draws and checks
            # five blocks, which is the model it chose on purpose; the generator
            # holds one `Yard`, and its checks read it -- a barricade's riser
            # has to stand inside a yard's interior, and five blocks are not one.
            # So the pieces say what they are part of and the translation puts
            # the pocket back, rather than either side pretending the other's
            # model is its own.
            block["shell"] = {
                "yard": str(yard.id),
                "side": _side_name(piece.side),
                "attached": _side_name(yard.attached),
                "wall": float(yard.thickness),
            }
            doc["blocks"].append(block)


def _block_record(block_id: str, box: Any, texture: str, kind: str,
                  walkable: bool = True, reachable: bool = True,
                  facing: str | None = None,
                  faces: Mapping[str, str] | None = None) -> dict:
    """One world box, with the two things the geometry cannot say about it.

    ``walkable`` is whether its top is a surface a player stands on and
    ``reachable`` whether anything leads onto it
    (:class:`~zmforge.blueprint.elements.Massing`).  A box drawn in the editor is
    a ledge or a crate, so both are true there; a yard's five walls and a shelf in
    a sealed vault are neither, and writing them as ordinary blocks made the
    playable-area check ask for a zone over every one of them.
    """
    record = {
        "id": block_id,
        "x0": float(box.mins.x),
        "y0": float(box.mins.y),
        "x1": float(box.maxs.x),
        "y1": float(box.maxs.y),
        "z0": float(box.mins.z),
        "z1": float(box.maxs.z),
        "texture": texture,
        "kind": kind,
        "walkable": bool(walkable),
        "reachable": bool(reachable),
    }
    if facing is not None:
        # Which face the texture is on.  The hull rule is art on the one face
        # looking into the room and caulk on the other five (spec 2.2); without
        # this the editor paints all six, and every hung picture comes back with
        # its own image wrapped round the panel's edges.
        record["facing"] = facing
    if faces:
        # The sides painted differently from ``texture``.  A box can carry a
        # material per face, and a document that held one name per box brought a
        # crate with a metal lid and a brick end back painted all one material,
        # with nothing saying so.  Only the sides that differ are written, so a
        # box painted the same all over stays one line.
        record["faces"] = dict(faces)
    return record


def _block_kind(materials: Any) -> str:
    """`clip` for a box the player is stopped by and sees through, else `solid`.

    The editor's two kinds are exactly the engine's `clip` material and
    everything else, which is what a sealed opening is written with.
    """
    from .materials import CLIP

    names = materials.names() if materials is not None else set()
    return "clip" if names and names <= {CLIP.name} else "solid"


def _block_facing(materials: Any) -> str | None:
    """The side a one-faced box shows its texture on, or ``None``.

    The hull rule of spec 2.2 is one visible face and ``caulk`` on the other
    five (:meth:`~zmforge.materials.FaceMaterials.only_visible_on`), which is
    what every piece of wall art is built with.  The editor holds one texture
    per block, so the face was lost and a rebuild painted the picture on all
    six; this is the one number that puts it back.  A box painted the same on
    every side -- a crate, a ledge -- has no facing and gets none.
    """
    from .materials import CAULK

    if materials is None or not getattr(materials, "per_side", None):
        return None
    if materials.default.name != CAULK.name:
        return None
    visible = [side for side, material in materials.per_side.items()
               if material.name != CAULK.name]
    return _side_name(visible[0]) if len(visible) == 1 else None


#: The editor's word for a side.  Four of the six are the same on both sides;
#: the horizontal pair are not, because the editor names a room's surfaces
#: rather than a box's faces.
SIDE_NAMES = {"bottom": "floor", "top": "ceiling"}


def _side_name(side: Any) -> str:
    name = side.name.lower()
    return SIDE_NAMES.get(name, name)


def _texture(materials: Any) -> str:
    """One material name for a box the editor paints with one texture.

    A blueprint box can carry a different material per face -- the hull rule is
    art on the face looking in and caulk on the other five -- and the editor
    has one texture per block, so the visible face wins over the hidden default.
    """
    from .materials import CAULK

    if materials is None:
        return FALLBACK_TEXTURE
    for material in materials.per_side.values():
        if material.name != CAULK.name:
            return material.name
    return materials.default.name


def _block_faces(materials: Any) -> dict[str, str]:
    """``{side: material name}`` for the sides painted otherwise than the default.

    A blueprint box carries a material per face and the editor's block carried
    one texture, so a crate with a metal lid and a brick end round-tripped as
    six faces of whatever :func:`_texture` picked first -- silently, with no gap
    and no note.  The sides are spelled the editor's way (:func:`_side_name`:
    ``floor`` and ``ceiling``, not ``bottom`` and ``top``) and only the ones
    that differ are listed, so the common box painted all over stays a single
    ``texture``.

    A hull -- caulk default, one visible face -- says the same thing in one word
    and is left to :func:`_block_facing`, so it is not written twice.
    """
    if materials is None or not getattr(materials, "per_side", None):
        return {}
    if _block_facing(materials) is not None:
        return {}
    default = materials.default.name
    return {_side_name(side): material.name
            for side, material in materials.per_side.items()
            if material.name != default}


def _block_texture(materials: Any) -> str:
    """The one texture a block is written with.

    The default material when the box names sides of its own
    (:func:`_block_faces`), because that is what the faces it does not name are
    painted with; otherwise :func:`_texture`'s choice, which keeps a hull's
    visible face in ``texture`` where every reader of this document expects it.
    """
    if materials is not None and _block_faces(materials):
        return materials.default.name
    return _texture(materials)


def _direction(facing: Any) -> str:
    """A heading in the editor's spelling: `+x`, `-x`, `+y`, `-y`."""
    from .spatial import Axis

    if facing is None:
        return "+y"
    axis = "x" if facing.axis is Axis.X else "y"
    return f"{'+' if facing.sign > 0 else '-'}{axis}"


def _solid_hull(solid: Any):
    from .spatial import Point, Span

    points = [point for face in solid.faces for point in face.points]
    return Span.flat_ok(
        Point(
            min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)
        ),
        Point(
            max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)
        ),
    )


# ----------------------------------------------------------------------
# Zones and doors
# ----------------------------------------------------------------------
def _zones(blueprint: Any) -> list[dict]:
    from .blueprint.elements import Zone

    out = []
    for zone in blueprint.elements(Zone):
        box = zone.bounds
        out.append(
            {
                "id": zone.id,
                "name": zone.name,
                "x0": float(box.mins.x),
                "y0": float(box.mins.y),
                "x1": float(box.maxs.x),
                "y1": float(box.maxs.y),
                "z0": float(box.mins.z),
                "z1": float(box.maxs.z),
                "starting": bool(zone.starting),
            }
        )
    return out


def _box_key(box: Any) -> tuple:
    return (
        round(box.mins.x, 4),
        round(box.mins.y, 4),
        round(box.mins.z, 4),
        round(box.maxs.x, 4),
        round(box.maxs.y, 4),
        round(box.maxs.z, 4),
    )


def _stair_gates(blueprint: Any) -> dict[tuple, str]:
    """Every flight's gate box, keyed the same way an opening's is.

    The box is not stored anywhere: it is derived from the flight's authored
    call by :func:`~zmforge.solids.forms.stair_gate`, which is the arithmetic
    the editor repeats from the ``stairs`` record in this document.  So a door
    that fills it is recognised by geometry, exactly as a door in a doorway is,
    and crosses as the id of the flight.
    """
    from .blueprint.elements import Massing
    from .solids.forms import stair_gate

    found: dict[tuple, str] = {}
    for massing in blueprint.elements(Massing):
        authored = getattr(massing, "authored", None)
        if authored is None or authored.form != "steps":
            continue
        box = stair_gate(authored.base, authored.steps, authored.step_depth,
                         authored.step_rise, authored.width, authored.toward)
        found.setdefault(_box_key(box), massing.id)
    return found


def _doors(blueprint: Any, openings: Mapping[tuple, tuple[str, str]],
           lost: list[str]) -> list[dict]:
    """Buyable doors, each pointing at the hole it fills.

    The two models join here by geometry rather than by a stored reference: a
    :class:`~zmforge.blueprint.elements.Door` holds the box it fills, and a door
    hung in an :class:`~zmforge.blueprint.elements.Opening` fills that opening's
    box exactly, so the boxes match and nothing has to be inferred.  A door hung
    in a free span matches nothing, which is the honest answer -- see the module
    docstring.
    """
    from .blueprint.elements import Door

    gates = _stair_gates(blueprint)
    out, homeless = [], []
    for door in blueprint.elements(Door):
        key = _box_key(door.box)
        room_id, opening_id = openings.get(key, ("", ""))
        stairs_id = "" if opening_id else gates.get(key, "")
        if not opening_id and not stairs_id:
            homeless.append(door.id)
        out.append(
            {
                "id": door.id,
                "room": room_id,
                "opening": opening_id,
                "stairs": stairs_id,
                "cost": int(door.price),
                "flag": door.flag,
            }
        )
    if homeless:
        lost.append(
            f"{len(homeless)} buyable door(s) are hung in a free span that is neither a "
            f"room's doorway nor the head of a flight ({', '.join(sorted(homeless))}); "
            "the editor's door belongs to one or the other, so these carry their price "
            "and flag but point at nothing"
        )
    return out


# ----------------------------------------------------------------------
# Gameplay items
# ----------------------------------------------------------------------
def _storey_of(rooms: Iterable, x: float, y: float, z: float) -> float | None:
    """Which storey a point is standing on: the floor bottom of its room.

    The editor keeps this per element (`level`) because a `.map` does not have
    it, and an importer reading it back off the geometry gets it wrong in a
    stacked building.  Here it is not read back off anything: the room is known.
    The smallest room covering the point wins.
    """
    best = None
    for room in rooms:
        outer = room.outer
        if not (outer.mins.x <= x <= outer.maxs.x and outer.mins.y <= y <= outer.maxs.y):
            continue
        if not (outer.mins.z - 1.0 <= z <= outer.maxs.z + 1.0):
            continue
        area = (outer.maxs.x - outer.mins.x) * (outer.maxs.y - outer.mins.y)
        if best is None or area < best[0]:
            best = (area, outer.mins.z)
    return None if best is None else best[1]


def _placed(rooms: Iterable, position: Any, yaw: float, z: float | None = None) -> dict:
    """The four fields every placed thing shares: where, which storey, which way."""
    height = position.z if z is None else z
    return {
        "x": float(position.x),
        "y": float(position.y),
        # A world height, not a hover: the position is known exactly, so the
        # editor is told it rather than asked to resolve a floor under it.
        "z": float(height),
        "level": _storey_of(rooms, position.x, position.y, height),
        "yaw": float(yaw) % 360.0,
    }


def _items(blueprint: Any, rooms: Iterable) -> list[dict]:
    """Perks, boxes, buys, spawners and the player start, in element order.

    Order is the blueprint's own, and it matters twice: a ``.map`` writer
    treats the *first* mystery box as the starting one and gives the *first*
    zombie spawner the zone's spawn factory, exactly as this blueprint did.
    """
    from .blueprint.elements import (
        Machine,
        MysteryBox,
        PlayerStart,
        PowerSwitch,
        Spawn,
        WallWeapon,
    )
    from .blueprint.model import PLAYER_START_CLEARANCE, WALL_WEAPON_DROP

    out: list[dict] = []
    for element in blueprint.elements():
        if isinstance(element, Machine):
            slug = element.perk.slug
            item = {"id": element.id, "type": "perk", "perk": slug}
            if slug == "pack_a_punch":
                item = {"id": element.id, "type": "pack_a_punch"}
            item.update(_placed(rooms, element.position, element.facing.world_yaw))
            out.append(item)
        elif isinstance(element, PowerSwitch):
            out.append(
                {"id": element.id, "type": "power_switch",
                 **_placed(rooms, element.position, element.facing.world_yaw)}
            )
        elif isinstance(element, MysteryBox):
            out.append(
                {"id": element.id, "type": "mystery_box",
                 # The chest's own name is what the script calls it and what
                 # goes on its ``script_noteworthy``; it is not the element id
                 # and it is not derivable from the order boxes were placed in.
                 # Without it a rebuild renamed the map's second box and moved
                 # its price back to the default, so two lines of the map
                 # disagreed with the script that reads them.
                 "chest": str(element.chest_name),
                 "price": int(element.price),
                 **_placed(rooms, element.position, element.facing.world_yaw)}
            )
        elif isinstance(element, WallWeapon):
            # The buy sits 8 units into the floor in the map (spec 4.10, and
            # what a built map does); the editor puts it on the wall at floor
            # level and its engine applies the drop again on the way back.
            out.append(
                {
                    "id": element.id,
                    "type": "wall_buy",
                    "weapon": element.slug,
                    "price": element.price,
                    **_placed(
                        rooms,
                        element.position,
                        element.facing.world_yaw,
                        z=element.position.z + WALL_WEAPON_DROP,
                    ),
                }
            )
        elif isinstance(element, Spawn):
            item = {
                "id": element.id,
                "type": "zombie_spawner",
                "zone": element.zone_name or None,
                **_placed(rooms, element.position, element.facing.yaw),
            }
            # The ``script_string`` on the struct.  ``find_flesh`` is the
            # default every free-standing riser carries and is left off; a
            # barricade's riser carries the tag that joins it to its boarded
            # window, which is the whole of the wiring between the two.
            if element.link_tag and element.link_tag != DEFAULT_LINK_TAG:
                item["link"] = str(element.link_tag)
            out.append(item)
        elif isinstance(element, PlayerStart):
            # The engine holds one start point and lays the slots out around it;
            # the editor holds one spawn per slot.  Writing the laid-out points
            # is what the engine would put in the map, so a round trip through
            # the editor -- which averages them back to a centre -- lands on the
            # same point it started from.
            for index, point in enumerate(element.slot_positions()):
                out.append(
                    {
                        "id": f"{element.id}_slot_{index + 1}",
                        "type": "player_spawn",
                        "slot": index + 1,
                        **_placed(
                            rooms,
                            point,
                            element.facing.world_yaw,
                            z=point.z - PLAYER_START_CLEARANCE,
                        ),
                    }
                )
    return out


# ----------------------------------------------------------------------
# Lights, probes, props, terrain
# ----------------------------------------------------------------------
def _lights(blueprint: Any, rooms: Iterable) -> list[dict]:
    from .blueprint.elements import Lamp

    out = []
    for lamp in blueprint.elements(Lamp):
        out.append(
            {
                "id": lamp.id,
                "x": float(lamp.position.x),
                "y": float(lamp.position.y),
                "z": float(lamp.position.z),
                "level": _storey_of(rooms, lamp.position.x, lamp.position.y, lamp.position.z),
                "color": [float(c) for c in lamp.colour],
                "radius": float(lamp.radius),
                # `null` is the engine's own default and means "whatever this
                # map's sky preset calls for"; a number frozen here would be
                # wrong the moment the preset changed.
                "stops": None if lamp.stops is None else float(lamp.stops),
                # Whether this lamp gets a run-time shadow map
                # (`PRIMARY_NOSHADOWMAP`).  It is not a display setting and it
                # is not the same for every lamp: a recipe's own lamps cast and
                # the room fill's do not (`Blueprint.light_rooms`), and the
                # map's `numOmniShadowSlices` is computed from how many cast.
                # Left out of the document, a map rebuilt from it came back
                # with every lamp casting and a different slice count.
                "shadows": bool(lamp.shadows),
                # The radiant exploder that switches it, for a glow that
                # belongs to an object (script.glow); null for a static lamp.
                "exploder": getattr(lamp, "exploder", None),
            }
        )
    return out


def _probes(blueprint: Any, rooms: Iterable) -> list[dict]:
    """One reflection probe per room, which is what a commit writes.

    ``Blueprint.probe_boxes`` is the same call ``emit/mapfile.py`` makes, so the
    boxes here are the boxes in the map rather than a second opinion about where
    probes belong.  A map whose enclosure has probes turned off gets none, and
    a reader of this document takes it back the same way: probes present means
    ``enclose(probe=True)``.
    """
    from .blueprint.elements import Enclosure

    enclosure = next(iter(blueprint.elements(Enclosure)), None)
    if enclosure is None or not enclosure.probe:
        return []
    out = []
    for owner, box in blueprint.probe_boxes():
        centre = (
            (box.mins.x + box.maxs.x) / 2.0,
            (box.mins.y + box.maxs.y) / 2.0,
            (box.mins.z + box.maxs.z) / 2.0,
        )
        out.append(
            {
                "id": f"{owner}_probe",
                "x": centre[0],
                "y": centre[1],
                "z": centre[2],
                "level": _storey_of(rooms, centre[0], centre[1], centre[2]),
                "size": [
                    float(box.maxs.x - box.mins.x),
                    float(box.maxs.y - box.mins.y),
                    float(box.maxs.z - box.mins.z),
                ],
            }
        )
    return out


def _props(blueprint: Any, rooms: Iterable) -> list[dict]:
    """Every placed model and stock prefab.

    The same props ride in the ``engine`` section, which carries the two fields
    the editor's prop has no room for (whether the compiler bakes collision for
    it, and the collision box a generated collmap is written from).  They are
    written here as well because this is the half an editor draws and builds
    from: an ``editor`` section with no props would show an empty building and
    would build one, which is worse than the reconstruction it replaces.
    """
    from .blueprint.elements import Prefab, PropScatter

    out = []
    for scatter in blueprint.elements(PropScatter):
        for index, prop in enumerate(scatter.props):
            out.append(
                {
                    "id": prop.id or f"{scatter.id}_{index}",
                    "kind": "model",
                    # Which placement this prop came out of.  A recipe furnishes
                    # room by room -- twenty-five scatters on this map -- and the
                    # editor holds one flat list, so without the group the whole
                    # map rebuilds as a single scatter: the same props in the
                    # same places, and a different map to every reader that
                    # counts elements, including this document written again.
                    "scatter": scatter.id,
                    "asset": prop.model,
                    "scale": float(prop.scale),
                    # Only on the props that have it, so every other row is
                    # the row it always was.  It is carried and `solid` is
                    # not because getting this one wrong is not a cosmetic
                    # loss: a dynamic prop rebuilt as a `misc_model` is a
                    # model cod2map64 cannot resolve, and the compiler writes
                    # no BSP at all (Prop.dynamic carries the probe).
                    **({"dynamic": True} if prop.dynamic else {}),
                    # A lean, only where there is one (Prop.pitch / roll).
                    **({"tilt": [float(prop.pitch), float(prop.roll)]} if prop.pitch or prop.roll else {}),
                    **_placed(rooms, prop.origin, prop.yaw),
                }
            )
    for prefab in blueprint.elements(Prefab):
        yaw = prefab.yaw if prefab.yaw is not None else prefab.facing.world_yaw
        out.append(
            {
                "id": prefab.id,
                "kind": "prefab",
                "asset": prefab.model,
                "scale": 1.0,
                **_placed(rooms, prefab.position, yaw),
            }
        )
    return out


def _terrains(blueprint: Any, lost: list[str]) -> list[dict]:
    """Heightfields, as the editor's normalised grid.

    The editor stores a height as a fraction of the patch's own ``max_height``;
    the blueprint stores it in world units above the anchor.  What is not on the
    blueprint at all is the noise the heights came from -- the field is the
    input, the generator that made it is the recipe's -- so the document carries
    no noise settings, and the note says so.

    ``max_height`` is rounded **up to a power of two** rather than set to the
    tallest cell.  The fraction is a division on the way out and a multiplication
    on the way back, and dividing by 18.3 and multiplying by it again does not
    return the number you started with: on a 100-cell terrain,
    2 cells came back one unit in the last place out, which is
    invisible in the map file (the patch coordinates are written to three
    decimals) and is two changed characters in ``.terrain-record.json``.
    Scaling by a power of two is exact in both directions, so the round trip
    returns the same doubles.  The cost is that the tallest cell is no longer
    exactly 1.0, which is a slider's top and not a measurement.
    """
    import math
    from .blueprint.elements import Terrain

    out = []
    for terrain in blueprint.elements(Terrain):
        record = terrain.record
        rows = [list(row) for row in record.heights.cells]
        tallest = max((max(row) for row in rows), default=0.0)
        if tallest <= 0.0:
            tallest = 1.0
        ceiling = float(2.0 ** math.ceil(math.log2(tallest)))
        if min((min(row) for row in rows), default=0.0) < 0.0:
            lost.append(
                f"the terrain {terrain.id!r} dips below its own anchor; the editor measures a "
                "height as a fraction of the patch's tallest point and cannot hold a negative "
                "one, so those cells open flat"
            )
        out.append(
            {
                "id": terrain.id,
                "x": float(record.anchor.x),
                "y": float(record.anchor.y),
                "z": float(record.anchor.z),
                "cell": float(record.x_cell),
                # Only written when the two axes differ, so the document of a
                # square grid is the file it always was.
                **({} if record.square_cells else {"cell_y": float(record.y_cell)}),
                "max_height": ceiling,
                "cols": int(record.cols),
                "rows": int(record.rows),
                "heights": [[max(0.0, min(1.0, v / ceiling)) for v in row] for row in rows],
                "texture": terrain.material.name,
                # How the patch was built, which is provenance rather than
                # shape: the mesh-or-columns choice, the chunk the patches are
                # cut at, how far the whole field was lifted off its anchor to
                # stop it z-fighting with the floor under it, and how large the
                # ground texture is laid.  None of it is readable back out of
                # the heights, and the record the map ships beside it
                # (`<name>.terrain-record.json`) states all four, so a document
                # that did not carry them rebuilt the same landscape with a
                # record that disagreed about how it was made.
                "style": str(terrain.style),
                "chunk": int(terrain.chunk),
                "lift": float(terrain.lift),
                "texture_scale": float(terrain.texture_scale),
            }
        )
        if terrain.bands:
            lost.append(
                f"the terrain {terrain.id!r} is painted in {len(terrain.bands)} height bands "
                "and the editor's patch has one texture, so it is rebuilt in the material of "
                "its lowest band"
            )
        lost.append(
            f"the terrain {terrain.id!r} carries its heights exactly and not the noise that "
            "made them, which is a recipe's and not a map's; regenerating it in the editor "
            "draws a different landscape rather than the same one"
        )
    return out


# ----------------------------------------------------------------------
def _notes(blueprint: Any, lost: list[str]) -> str:
    """The document's own account of what did not fit, in the editor's notes.

    A shared format that dropped these silently would be worse than the split it
    replaces, and the editor has no other field to put them in: `notes` is shown
    to whoever opens the map and survives a save.
    """
    from .blueprint.elements import Spawn, WallWeapon, Window

    lines = [
        f"Generated by the zmforge recipe for {blueprint.name}. The geometry here is what "
        "the recipe authored, not a reading of the .map."
    ]
    spawns = [s for s in blueprint.elements(Spawn) if s.kind != "rise"]
    if spawns:
        lines.append(
            f"{len(spawns)} zombie spawner(s) are a walker, a faller or a dog run in the "
            "generator and are written here as ordinary risers, because a zombie spawner is "
            "the only kind this editor has; building from here makes them all risers."
        )
    chalk = [w for w in blueprint.elements(WallWeapon) if w.chalk]
    if chalk:
        lines.append(
            f"{len(chalk)} wall buy(s) carry a chalk outline on the wall, which the editor "
            "has no field for; it is lost on a build from here."
        )
    windows = blueprint.elements(Window)
    if windows:
        lines.append(
            f"{len(windows)} barricade window(s) are one thing in the generator and four "
            "here: the hole is an opening in its room carrying the barricade, the zombie "
            "riser outside it is a zombie spawner, and the yard around it is blocks. All "
            "four cross, so a build from here puts the barricade back; editing them "
            "separately is editing four things."
        )
    lines.extend(lost)
    lines.append(
        "The custom script, the generated wall art, imported geometry and the "
        "per-prop collision boxes are in this file's engine section, which the editor carries "
        "through untouched rather than showing."
    )
    return "\n".join(f"- {line}" if index else line for index, line in enumerate(lines))
