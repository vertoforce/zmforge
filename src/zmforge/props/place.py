"""Put props into a map that already exists, without touching how it was built.

This is deliberately a *pass over the written ``.map``* rather than a feature of
one layout: the map's own author keeps owning its rooms, and props are added,
re-added or removed afterwards without either side editing the other's code.
Every entity this writes carries a ``zmf_prop`` key, and :func:`apply` drops
every entity carrying that key before adding the new ones, so running the pass
twice leaves the same map, and running it with an empty list removes the props
entirely.

Where they go.  The map is read for its **floor slabs** -- worldspawn brushes
that are wide, thin, horizontal and whose top face sits within a storey's
height below the entities that stand in the playable space.  A prop is placed
on a slab's top surface, inset from the edges, at a seeded offset, and never
within :data:`KEEP_CLEAR` of an entity origin, because the things with origins
in a zombies map are the things the player has to walk up to and use.

Entity shape is spec section 4.13's ``misc_model`` with ``static``,
``modelscale``, a lighting state and a seeded yaw -- but **not** its
``no_collmap``.  The mod tools' own entity definition (``bin\t7.def.json``)
reads ``no_collmap``, the switch for not baking this model's collmap into the static
bsp, and ``use_collmap``, the switch that does bake it in, both defaulting
to false.  A prop that is meant to be solid therefore
carries ``use_collmap "1"``; one that is meant to be walked through keeps
``no_collmap "1"``, which is also what keeps it clear of the navmesh.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import cos, sin

from ..blueprint.identity import Identity
from ..materials import TOOL_MATERIALS
from ..mapsource.document import Document, Entity
from ..solids.halfspace import plane_through
from ..solids.inspect import inspect_planes
from ..spatial import Point, Span

__all__ = [
    "Placement",
    "FloorSlab",
    "KEEP_CLEAR",
    "floor_slabs",
    "scatter",
    "apply",
    "placed",
]

#: Marker key on every entity this module writes.
MARKER = "zmf_prop"

#: How far a prop stays from anything with an origin: perk machines, doors,
#: spawn points, the power switch.  A prop the player has to walk through to
#: buy a perk is not funny twice.
KEEP_CLEAR = 56.0

#: A slab has to be at least this wide on both horizontal axes to be a floor.
#: A corridor in a real map is narrower than a room, so this is the width of a
#: doorway rather than of a room.
MIN_FLOOR_SPAN = 64.0

#: and no thicker than this.
MAX_FLOOR_THICKNESS = 64.0

#: How far below a reference height a floor's top face may sit, when a caller
#: asks for one.  Not applied by default: a map with storeys has floors at
#: several heights and pinning them to the lowest entity in the map put every
#: prop in whichever room happened to be lowest.
STOREY = 160.0


@dataclass(frozen=True, slots=True)
class FloorSlab:
    """A horizontal worldspawn brush a prop can stand on."""

    bounds: Span
    material: str

    @property
    def top(self) -> float:
        return self.bounds.maxs.z

    @property
    def area(self) -> float:
        return (self.bounds.maxs.x - self.bounds.mins.x) * (
            self.bounds.maxs.y - self.bounds.mins.y
        )


@dataclass(frozen=True, slots=True)
class Placement:
    """One prop, sited."""

    name: str  # the zmf_prop marker value, unique in the map
    model: str  # the xmodel asset name
    origin: tuple[float, float, float]
    yaw: float
    modelscale: float = 1.0
    #: Whether cod2map bakes this model's collmap into the static BSP.
    solid: bool = True

    @property
    def rounded(self) -> tuple[float, float, float]:
        return tuple(round(v, 1) for v in self.origin)  # type: ignore[return-value]


def _seed(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256("\x1f".join(parts).encode()).digest()[:8], "big")


def _unit_interval(seed: int, index: int) -> float:
    """A stable value in [0, 1) from a seed and a slot number."""
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _brush_bounds(solid) -> Span | None:
    try:
        planes = [plane_through(*facet.points) for facet in solid.facets]
    except (TypeError, ValueError):
        return None
    if len(planes) < 4:
        return None
    return inspect_planes(planes).bounds()


def floor_slabs(document: Document, reference_z: float | None = None) -> list[FloorSlab]:
    """Every worldspawn brush a prop could stand on, largest first.

    A floor is a worldspawn brush that is wide on both horizontal axes, thin in
    z, and whose upward face carries an art material.  Those three together
    exclude the things that otherwise look like floors: a wall is thick in z, a
    sky cage's ground is caulk or sky, and a ceiling's *upper* face looks into
    the void above and is caulk, so picking the upward face rejects it.

    ``reference_z``, when given, additionally keeps only floors within one
    storey below it.  It is off by default because a map with storeys has
    floors at several heights.
    """
    world = document.worldspawn
    if world is None:
        return []

    slabs: list[FloorSlab] = []
    for solid in world.solids:
        facets = getattr(solid, "facets", None)
        if not facets:
            continue  # a patch, not a brush
        bounds = _brush_bounds(solid)
        if bounds is None:
            continue
        width = bounds.maxs.x - bounds.mins.x
        depth = bounds.maxs.y - bounds.mins.y
        thickness = bounds.maxs.z - bounds.mins.z
        if width < MIN_FLOOR_SPAN or depth < MIN_FLOOR_SPAN:
            continue
        if thickness > MAX_FLOOR_THICKNESS or thickness <= 0:
            continue
        if reference_z is not None and not (
            reference_z - STOREY <= bounds.maxs.z <= reference_z + 8.0
        ):
            continue
        top = max(
            (f for f in facets if _is_up(f)),
            key=lambda f: max(p.z for p in f.points),
            default=None,
        )
        # A sky cage's ground and the caulk backing of a wall are both wide,
        # thin and horizontal.  What separates a floor is that its top face
        # carries art: a tool material is the compiler's surface, not one the
        # player ever stands on.
        if top is None or top.material in TOOL_MATERIALS:
            continue
        slabs.append(FloorSlab(bounds=bounds, material=top.material))
    slabs.sort(key=lambda s: (-s.area, s.bounds.mins.x, s.bounds.mins.y))
    return slabs


def _is_up(facet) -> bool:
    try:
        plane = plane_through(*facet.points)
    except ValueError:
        return False
    # Inward normal: a floor's top face looks *down* into the slab.
    return plane.normal.z < -0.9


def _entity_origins(document: Document) -> list[tuple[float, float, float]]:
    """Every origin in the map *except* our own props.

    A second run must see the map the first run saw, or the props walk: the
    entities this pass wrote would themselves become things to keep clear of.
    """
    out: list[tuple[float, float, float]] = []
    for entity in document.entities:
        if entity.value(MARKER) is not None:
            continue
        raw = entity.value("origin")
        if not raw:
            continue
        parts = raw.split()
        if len(parts) != 3:
            continue
        try:
            out.append((float(parts[0]), float(parts[1]), float(parts[2])))
        except ValueError:
            continue
    return out


def scatter(
    document: Document,
    models: list[tuple[str, str, float]],
    *,
    seed: str = "zmforge-props",
    inset: float = 40.0,
    sink: float = 0.5,
    solid: dict[str, bool] | None = None,
) -> list[Placement]:
    """Site each ``(name, xmodel asset, size in units)`` on its own floor slab.

    Deterministic: the same document, models and seed give the same origins.
    Props are spread over as many different slabs as the map has, largest
    first, so they do not pile into one room.
    """
    slabs = floor_slabs(document)
    if not slabs:
        raise ValueError("no floor slab in this map is wide, thin and low enough to stand a prop on")
    avoid = _entity_origins(document)

    placements: list[Placement] = []
    for index, (name, model, size) in enumerate(sorted(models)):
        slab = slabs[index % len(slabs)]
        base = _seed(seed, name)
        margin = max(inset, size * 0.75)
        origin = _site(slab, base, margin, avoid)
        yaw = round(_unit_interval(base, 9) * 360.0, 1)
        placements.append(
            Placement(
                name=name,
                model=model,
                origin=(origin[0], origin[1], slab.top - sink),
                yaw=yaw,
                solid=True if solid is None else solid.get(name, True),
            )
        )
        avoid.append((origin[0], origin[1], slab.top))
    return placements


def _site(
    slab: FloorSlab,
    base: int,
    margin: float,
    avoid: list[tuple[float, float, float]],
) -> tuple[float, float]:
    low, high = slab.bounds.mins, slab.bounds.maxs
    x0, x1 = low.x + margin, high.x - margin
    y0, y1 = low.y + margin, high.y - margin
    if x1 <= x0:
        x0 = x1 = (low.x + high.x) / 2.0
    if y1 <= y0:
        y0 = y1 = (low.y + high.y) / 2.0

    best: tuple[float, float] | None = None
    best_clearance = -1.0
    for attempt in range(24):
        x = x0 + (x1 - x0) * _unit_interval(base, attempt * 2)
        y = y0 + (y1 - y0) * _unit_interval(base, attempt * 2 + 1)
        clearance = min(
            ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5 for ax, ay, _ in avoid
        ) if avoid else KEEP_CLEAR * 2
        if clearance >= KEEP_CLEAR:
            return (round(x, 1), round(y, 1))
        if clearance > best_clearance:
            best_clearance, best = clearance, (round(x, 1), round(y, 1))
    assert best is not None
    return best


def entity_for(placement: Placement, guid: str, layer: str | None = "The Map") -> Entity:
    """The ``misc_model`` entity for one placement (spec 4.13)."""
    x, y, z = placement.origin
    return Entity(
        guid=guid,
        layer=layer,
        pairs=[
            ("classname", "misc_model"),
            (MARKER, placement.name),
            ("model", placement.model),
            ("origin", f"{x:g} {y:g} {z:g}"),
            ("angles", f"0 {placement.yaw:g} 0"),
            ("modelscale", f"{placement.modelscale:g}"),
            # Exactly one of the pair, never both: the tools define them as
            # opposites and both default to false.
            ("use_collmap", "1") if placement.solid else ("no_collmap", "1"),
            ("static", "1"),
            ("lightingstate1", "1"),
            ("lightingstate2", "1"),
            ("lightingstate3", "1"),
            ("lightingstate4", "1"),
        ],
    )


def placed(document: Document) -> list[Entity]:
    """Every entity a previous run of this pass added."""
    return [e for e in document.entities if e.value(MARKER) is not None]


def apply(document: Document, placements: list[Placement], *, seed: str) -> int:
    """Replace this map's props with ``placements``.  Returns how many were written."""
    document.entities = [e for e in document.entities if e.value(MARKER) is None]
    identity = Identity(seed=seed)
    for placement in placements:
        document.entities.append(
            entity_for(placement, identity.guid_for(f"zmf_prop_{placement.name}"))
        )
    return len(placements)
