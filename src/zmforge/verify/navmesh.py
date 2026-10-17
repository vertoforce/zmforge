"""H1: can the zombies get there, read off the mesh the compiler built.

``Z25`` floods the map from the player's spawn and asks what a *player* can
reach.  A zombie does not move like a player: it has no jump and no survivable
drop, it does not walk through a door because somebody bought it, and it goes
where ``cod2map64 -navmesh`` laid walkable surface and nowhere else.  So a map
can pass every check in this package -- every doorway wide enough (``W2``,
``N2``), every step low enough (``N1``), every zone with a spawn struct in it
(``Z4``), every room reachable on foot (``Z25``) -- and still hold a room
nothing ever comes to.  In play that is a corner of the map where the round
never ends, and it is the same family of defect as the zone with no spawner
that once gave a round that never started.

This check is the only one in the package that reads a build artefact rather
than the model or the text: :mod:`~zmforge.verify.hkt` parses
``<map>_navmesh.hkt`` and hands back the faces, edges and vertices the
compiler wrote, in map units.  The four ``N`` checks read the *settings* the
generator obeys and predict what it will refuse to build; this one reads what
it actually built.

What it reports
---------------
``no walkable surface at all``
    the compiler wrote a mesh with no faces, or none this reader could find.
    Nothing walks anywhere; the round never ends.
``a spawn struct with no surface under or beside it``
    a zombie rises at the struct and then has to walk.  A struct more than a
    zombie's own width (:data:`~zmforge.verify.documented.MIN_CHARACTER_WIDTH`)
    from any walkable surface is a zombie that rises and stands still.
``a barricade with surface on only one side``
    the walkers cross a barricade by animation, not by walking, so the mesh is
    *expected* to stop at the wall and start again in the yard -- that is what
    a one-room map's two islands are.  What is not expected is a window with
    surface on one side and none on the other: the yard is where they come
    from and the room is where they are going.
``a zone with standing room and no walkable surface``
    the player can stand there and nothing can path there.
``floor a player can reach that no zombie can``
    the headline.  Every standing rectangle ``Z25``'s flood reaches is tested
    against the mesh a spawner can actually get to, and the difference is
    reported by surface, with its area and the middle of its largest piece --
    the same shape of line ``Z18`` and ``Z25`` print, because it is the same
    question asked a third time.  A room floor, a terrain cell and a flight of
    steps are routes and are errors; the top of any other walkable massing is a
    warning, because a table nothing can climb is what a table is and a
    platform nothing can climb is the defect, and the model does not say which
    of its slabs is which.
``islands``
    a warning that counts the pieces the mesh falls into and how many no
    spawner can reach.  An island with no player floor on it costs nothing,
    which is why it is a warning and why the error above is the one that
    matters.

Islands, and why a count on its own means nothing
-------------------------------------------------
The mesh is *meant* to come apart.  ``zm_one_room`` is two faces with no edge
between them: the room, and the yard behind the barricade.  A zombie crosses
that gap by playing the barricade's traversal animation, so the two islands
are one place as far as play is concerned.  This check therefore joins the
islands either side of every :class:`~zmforge.blueprint.elements.Window`
before it decides what a spawner can reach, and only then calls the rest
unreachable.  Doors need no such treatment: a door leaf is an entity, not
world geometry, so the compiler lays surface straight through the opening and
the mesh is continuous across it -- which matches ``Z25``'s own decision that
a door is not a wall.

What is inference and what is measurement
-----------------------------------------
The mesh itself is measured: every number below comes out of a file the
compiler wrote with the mod tools.  Two judgements are not:

* **a surface within one navmesh step of a floor is that floor.**  The band
  this check matches a face to a standing rectangle with is
  :data:`~zmforge.verify.documented.MAX_STEP_HEIGHT`, the generator's own
  ``maxStepHeight``.  Nothing states that the mesh sits exactly on the
  surface it was built from, so a band is used rather than equality; measured
  on ``zm_forge_gate`` and ``zm_one_room`` the mesh sits at exactly the floor
  height, so the band is slack this check has never needed.
* **a zombie can be spawned onto surface a zombie's width away.**  A riser
  comes up through the floor and then walks, and how far off the mesh a struct
  may sit before the walker is stuck has not been tested in play.  The width is
  the documented one so the number has a file behind it, and the finding says
  what it measured.

Two more rules earn their place by having caught themselves out on a real map,
and both are written up where they are implemented:
:data:`SIMPLIFIED_GROUND`, which is the slack a heightfield gets and a slab
does not, and :meth:`NavMesh.buried`, which drops a standing rectangle the mesh
says is under something -- on a test map, an outdoor room had its floor at
16 and terrain laid over it reaching 89, and ``Z25``'s flood offered that
floor as somewhere to stand.

Nothing here has been played.  The chain from "no face under this rectangle" to
"no zombie comes" is read off the generator's own settings and Havok's own
mesh, not off a round of zombies; ``M5`` is still the playtest.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..blueprint.elements import Massing, Spawn, Terrain, Window, Zone
from ..spatial import Axis, Point, Span
from .documented import CHARACTER_HEIGHT, MAX_STEP_HEIGHT, MIN_CHARACTER_WIDTH
from .hkt import NavmeshUnreadable, RawNavMesh, read_navmesh
from .reachability import flood_from_spawn
from .report import Report, error, warning

__all__ = [
    "NavMesh",
    "NavFace",
    "check_navmesh",
    "check_navmesh_file",
    "SAME_SURFACE",
    "WITHIN_REACH",
]

#: How far from a standing surface a navmesh face may sit and still be that
#: surface, in units.  The generator's own ``maxStepHeight`` (``N1``).
SAME_SURFACE = MAX_STEP_HEIGHT

#: How far from a thing the nearest walkable surface may be and still count as
#: under it, in units.  The generator's own ``minCharacterWidth`` (``N2``): one
#: zombie's width.
WITHIN_REACH = MIN_CHARACTER_WIDTH

#: How much further off a *heightfield* the mesh is allowed to be before a
#: cell counts as having no surface, in units.  **[documented, with a
#: measurement]** -- ``default_navmesh_settings.json`` carries
#: ``"simplification.maxBorderHeightError": 30``, and the generator spends it:
#: measured over the 100 cells of a test map's heightfield, the mesh
#: sits a median of 2 units from the model's own sample, 18 at the ninetieth
#: percentile and 20 at the worst away from the staircase.  Terrain only: a
#: slab is flat and the mesh over it is flat, so a slab gets no slack and a
#: table top 32 units above its floor is still reported.
SIMPLIFIED_GROUND = 30.0

#: How far either side of a barricade to look for the surface it joins.  Three
#: quarters of a zombie's width, which clears the 16-unit wall the recipes cut
#: a window in without reaching across the room behind it.
ACROSS_BARRICADE = 24.0


# --------------------------------------------------------------------------
# The mesh, as a graph of convex faces
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NavFace:
    """One face of the navmesh: a plan polygon and the heights it spans.

    A face is not flat, and treating it as flat gets the answer wrong in both
    directions.  Measured on the probe map: the mesh over a
    six-tread flight is *one* face sloping from 32 to 112, and the mesh over a
    heightfield is a few faces spanning 100 units each -- the generator
    simplifies a staircase into a ramp rather than tiling it tread by tread,
    which its own ``enableSimplification`` and ``maxBorderHeightError``
    settings say it may.  Matching a surface against one averaged height
    reported that staircase and half that hillside as unreachable; matching
    against the face's whole height band instead let a room floor that ramps
    up in one corner answer for a table top 32 units above it, three hundred
    units away.

    So a face carries its corners in three dimensions and answers
    :meth:`height_at`, the height of the surface *at a point*, interpolated
    over a triangulation of the face.  Two simpler readings were tried first
    and both misreported a real map:

    * a **plane** fitted through the corners.  The staircase face of
      a test map is one eight-sided face holding both a ramp (2320
      at height 33, 1840 at 280) and the landing it arrives on (flat at 288),
      which no plane fits; the fitted plane put the top of that flight 52
      units below the mesh and condemned a staircase the walkers use.
    * a **fan** from the first corner.  A fan is a valid tessellation of a
      convex polygon but an arbitrary one, and on that same face it ran a
      triangle from the landing clean across to the foot of the ramp, reading
      260 where the surface is 280, and reported the spawn struct on that
      landing as standing on nothing.

    The triangulation is by shortest diagonal instead, which keeps the flat
    part flat and the ramp linear, and is what the surface obviously is.
    """

    index: int
    points: tuple[tuple[float, float, float], ...]
    low: float
    high: float
    bounds: Span
    #: The face cut into triangles, as triples of indices into ``points``.
    triangles: tuple[tuple[int, int, int], ...]

    @property
    def plan(self) -> tuple[tuple[float, float], ...]:
        return tuple((x, y) for x, y, _ in self.points)

    @property
    def z(self) -> float:
        """The middle of the band, for a line a reader has to place on a map."""
        return (self.low + self.high) / 2.0

    def height_at(self, x: float, y: float) -> float:
        """Where the surface of this face is above ``(x, y)``.

        Inside the face: the height of the triangle the point falls in, fanned
        from the first corner, interpolated by area.  Outside it -- which is
        where the "or beside it" tests ask -- the height of the nearest point
        on its border, which is the surface a walker standing at the edge is
        on.  Either way the answer is a height the face really has, never an
        extrapolated one.
        """
        for a, b, c in self.triangles:
            first, second, third = self.points[a], self.points[b], self.points[c]
            area = (second[0] - first[0]) * (third[1] - first[1]) - (
                second[1] - first[1]
            ) * (third[0] - first[0])
            if abs(area) < 1e-9:
                continue
            one = (
                (second[0] - x) * (third[1] - y) - (second[1] - y) * (third[0] - x)
            ) / area
            two = (
                (third[0] - x) * (first[1] - y) - (third[1] - y) * (first[0] - x)
            ) / area
            three = 1.0 - one - two
            if one >= -1e-9 and two >= -1e-9 and three >= -1e-9:
                return one * first[2] + two * second[2] + three * third[2]
        return self._height_on_border(x, y)

    def _height_on_border(self, x: float, y: float) -> float:
        best, height = math.inf, self.points[0][2]
        count = len(self.points)
        for at in range(count):
            x0, y0, z0 = self.points[at]
            x1, y1, z1 = self.points[(at + 1) % count]
            dx, dy = x1 - x0, y1 - y0
            length = dx * dx + dy * dy
            along = 0.0 if length == 0.0 else ((x - x0) * dx + (y - y0) * dy) / length
            along = min(1.0, max(0.0, along))
            gap = math.hypot(x - (x0 + along * dx), y - (y0 + along * dy))
            if gap < best:
                best, height = gap, z0 + along * (z1 - z0)
        return height

    def spans(self, x: float, y: float, z: float) -> bool:
        """Is ``z`` this face's own surface above ``(x, y)``, within one step?"""
        return abs(self.height_at(x, y) - z) <= SAME_SURFACE

    def band_over(self, box: Span) -> tuple[float, float]:
        """The heights this face has over the part of ``box`` it covers.

        Sampled at the five points of the shared rectangle -- its corners and
        its middle -- rather than taken from the whole face, because a face can
        be enormous: one face measured on a test map is 175,000 square
        units of hillside spanning 51 to 89, and asking whether it has *any*
        corner near a height would let it answer for a table top on the far
        side of the room.
        """
        low_x = max(self.bounds.mins.x, box.mins.x)
        high_x = min(self.bounds.maxs.x, box.maxs.x)
        low_y = max(self.bounds.mins.y, box.mins.y)
        high_y = min(self.bounds.maxs.y, box.maxs.y)
        heights = [
            self.height_at(x, y)
            for x, y in (
                (low_x, low_y),
                (high_x, low_y),
                (low_x, high_y),
                (high_x, high_y),
                ((low_x + high_x) / 2.0, (low_y + high_y) / 2.0),
            )
        ]
        return min(heights), max(heights)

    def covers(self, box: Span, z: float, slack: float = SAME_SURFACE) -> bool:
        """Is this face the walkable surface of ``box`` at height ``z``?

        The face has to reach that height *somewhere over the rectangle*, give
        or take ``slack``.  Taking the band the face has over the rectangle,
        rather than a single sampled height, is what lets a sloping face answer
        for ground it slopes across while a floor that is flat under a table
        still answers 16 there and leaves the table top 32 above it reported.
        """
        low, high = self.band_over(box)
        return low - slack <= z <= high + slack

    @property
    def area(self) -> float:
        """The shoelace area, in square units."""
        total = 0.0
        plan = self.plan
        for at, (x, y) in enumerate(plan):
            nx, ny = plan[(at + 1) % len(plan)]
            total += x * ny - nx * y
        return abs(total) / 2.0

    def holds(self, x: float, y: float) -> bool:
        """Is ``(x, y)`` inside the face, in plan?

        Ray casting rather than a half-plane test, so the answer does not
        depend on which way the generator wound the polygon (its own
        ``triangleWinding`` setting is one of the things this reader does not
        interpret).
        """
        inside = False
        plan = self.plan
        count = len(plan)
        for at in range(count):
            x0, y0 = plan[at]
            x1, y1 = plan[(at + 1) % count]
            if (y0 > y) != (y1 > y):
                crossing = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if crossing > x:
                    inside = not inside
        return inside

    def distance_to(self, x: float, y: float) -> float:
        """How far ``(x, y)`` is from the face in plan; zero inside it."""
        if self.holds(x, y):
            return 0.0
        best = math.inf
        plan = self.plan
        count = len(plan)
        for at in range(count):
            x0, y0 = plan[at]
            x1, y1 = plan[(at + 1) % count]
            dx, dy = x1 - x0, y1 - y0
            length = dx * dx + dy * dy
            along = 0.0 if length == 0.0 else ((x - x0) * dx + (y - y0) * dy) / length
            along = min(1.0, max(0.0, along))
            best = min(best, math.hypot(x - (x0 + along * dx), y - (y0 + along * dy)))
        return best

    def overlaps(self, box: Span) -> bool:
        """Does the face cover any part of an axis-aligned rectangle?

        Exact for any simple polygon: two convex-or-not shapes overlap when a
        corner of one is inside the other or two of their edges cross, and all
        three are tested.
        """
        if not _plan_overlap(self.bounds, box):
            return False
        corners = (
            (box.mins.x, box.mins.y),
            (box.maxs.x, box.mins.y),
            (box.maxs.x, box.maxs.y),
            (box.mins.x, box.maxs.y),
        )
        if any(self.holds(x, y) for x, y in corners):
            return True
        if any(
            box.mins.x <= x <= box.maxs.x and box.mins.y <= y <= box.maxs.y
            for x, y in self.plan
        ):
            return True
        plan = self.plan
        count = len(plan)
        for at in range(count):
            first = plan[at]
            second = plan[(at + 1) % count]
            for corner in range(4):
                if _cross(first, second, corners[corner], corners[(corner + 1) % 4]):
                    return True
        return False


def _plan_overlap(one: Span, other: Span) -> bool:
    return (
        min(one.maxs.x, other.maxs.x) > max(one.mins.x, other.mins.x)
        and min(one.maxs.y, other.maxs.y) > max(one.mins.y, other.mins.y)
    )


def _side(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _cross(a, b, c, d) -> bool:
    """Do the segments ``ab`` and ``cd`` properly cross?"""
    return (_side(a, b, c) > 0) != (_side(a, b, d) > 0) and (
        _side(c, d, a) > 0
    ) != (_side(c, d, b) > 0)


def _triangulate(points: Sequence[tuple[float, float, float]]) -> tuple[tuple[int, int, int], ...]:
    """Cut a face into triangles, always taking the shortest diagonal going.

    Ear clipping, with the ear chosen by the length of the diagonal it cuts
    rather than by position in the ring.  On a convex polygon -- which is what
    the generator makes, by its own ``convexThreshold`` -- every ear is valid,
    so the choice is entirely about which triangulation describes the surface,
    and the short-diagonal one keeps a landing flat instead of running a
    triangle from it to the bottom of the ramp next door.
    """
    if len(points) < 3:
        return ()
    ring = list(range(len(points)))
    out: list[tuple[int, int, int]] = []
    while len(ring) > 3:
        best = None
        for at in range(len(ring)):
            before = ring[at - 1]
            here = ring[at]
            after = ring[(at + 1) % len(ring)]
            if not _is_ear(points, ring, before, here, after):
                continue
            length = math.hypot(
                points[before][0] - points[after][0],
                points[before][1] - points[after][1],
            )
            if best is None or length < best[0]:
                best = (length, at, (before, here, after))
        if best is None:  # a ring no ear fits: fall back to a fan
            return tuple(
                (ring[0], ring[at], ring[at + 1]) for at in range(1, len(ring) - 1)
            )
        out.append(best[2])
        ring.pop(best[1])
    out.append((ring[0], ring[1], ring[2]))
    return tuple(out)


def _is_ear(points, ring, before, here, after) -> bool:
    """A corner that turns the polygon's own way and covers no other corner."""
    turn = _side(points[before], points[here], points[after])
    if abs(turn) < 1e-9:
        return False
    if (turn > 0) != (_winding(points, ring) > 0):
        return False
    for other in ring:
        if other in (before, here, after):
            continue
        if _in_triangle(points[other], points[before], points[here], points[after]):
            return False
    return True


def _winding(points, ring) -> float:
    total = 0.0
    for at, index in enumerate(ring):
        x0, y0 = points[index][0], points[index][1]
        following = points[ring[(at + 1) % len(ring)]]
        total += x0 * following[1] - following[0] * y0
    return total


def _in_triangle(point, a, b, c) -> bool:
    first = _side(a, b, point)
    second = _side(b, c, point)
    third = _side(c, a, point)
    return (first >= 0 and second >= 0 and third >= 0) or (
        first <= 0 and second <= 0 and third <= 0
    )


@dataclass(frozen=True, slots=True)
class NavMesh:
    """The compiler's mesh: faces, which of them touch, and what is on them."""

    faces: tuple[NavFace, ...]
    #: ``links[i]`` is every face that shares an edge with face ``i``.
    links: tuple[frozenset[int], ...]

    @classmethod
    def of(cls, raw: RawNavMesh) -> "NavMesh":
        faces: list[NavFace] = []
        links: list[set[int]] = []
        for index in range(raw.face_count):
            start, how_many = raw.start_edge[index], raw.num_edges[index]
            ring = range(start, start + how_many)
            points = tuple(raw.vertices[raw.edge_a[edge]] for edge in ring)
            heights = [point[2] for point in points]
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            faces.append(
                NavFace(
                    index,
                    points,
                    min(heights),
                    max(heights),
                    Span.flat_ok(
                        Point(min(xs), min(ys), min(heights)),
                        Point(max(xs), max(ys), max(heights)),
                    ),
                    _triangulate(points),
                )
            )
            links.append(
                {raw.opposite_face[edge] for edge in ring if raw.opposite_face[edge] >= 0}
            )
        return cls(tuple(faces), tuple(frozenset(one) for one in links))

    def under(self, x: float, y: float, z: float, *, within: float = 0.0) -> int | None:
        """The face a thing at ``(x, y, z)`` stands on, if any is close enough."""
        best: int | None = None
        best_gap = math.inf
        for face in self.faces:
            if not face.spans(x, y, z):
                continue
            gap = face.distance_to(x, y)
            if gap > within or gap >= best_gap:
                continue
            best, best_gap = face.index, gap
        return best

    def over(self, box: Span, z: float, slack: float = SAME_SURFACE) -> list[int]:
        """Every face covering part of a standing rectangle at height ``z``."""
        return [
            face.index
            for face in self.faces
            if face.overlaps(box) and face.covers(box, z, slack)
        ]

    def buried(self, box: Span, z: float) -> bool:
        """Is the real surface here *above* ``z``, by the mesh's own account?

        The flood of ``Z25`` derives standing room from the model, and the
        model will hand it a room's floor even where something later sits on
        top of that floor.  Measured on a test map: the yard is a
        room whose floor is at 16 with a heightfield laid over it that reaches
        89, so the flood offers 385,712 square units of "floor" at z=16 that
        nothing stands on and no mesh covers, and the terrain's own low corners
        come with it.  The mesh knows better -- it has surface over that ground
        at the height the ground actually is -- so a rectangle with mesh above
        it is a rectangle the flood should not have offered, and reporting it
        would be reporting that limitation rather than a defect in the map.
        """
        for face in self.faces:
            if face.overlaps(box) and face.band_over(box)[0] > z + SAME_SURFACE:
                return True
        return False

    def islands(self, joins: Iterable[tuple[int, int]] = ()) -> list[frozenset[int]]:
        """The mesh cut into pieces nothing can walk between.

        ``joins`` are the pairs a walker crosses without a shared edge -- the
        two sides of a barricade -- and they are treated as links.
        """
        extra: dict[int, set[int]] = {}
        for one, other in joins:
            extra.setdefault(one, set()).add(other)
            extra.setdefault(other, set()).add(one)
        seen: set[int] = set()
        out: list[frozenset[int]] = []
        for start in range(len(self.faces)):
            if start in seen:
                continue
            piece = {start}
            queue = deque([start])
            while queue:
                here = queue.popleft()
                for there in self.links[here] | extra.get(here, set()):
                    if there not in piece:
                        piece.add(there)
                        queue.append(there)
            seen |= piece
            out.append(frozenset(piece))
        return out

    @property
    def area(self) -> float:
        return sum(face.area for face in self.faces)


# --------------------------------------------------------------------------
# The check
# --------------------------------------------------------------------------
def check_navmesh_file(blueprint, path: str | Path) -> Report:
    """``H1`` over a navmesh on disk, reporting a file it cannot read."""
    report = Report()
    try:
        raw = read_navmesh(path)
    except NavmeshUnreadable as unreadable:
        report.add(
            error(
                "H1",
                f"the navmesh the compiler wrote could not be read: {unreadable}. "
                "Nothing below it was checked, so this is not a map that passed",
                Path(path).name,
            )
        )
        return report
    return check_navmesh(blueprint, NavMesh.of(raw))


def check_navmesh(blueprint, mesh: NavMesh) -> Report:
    """``H1``: the mesh has surface where the play is, and it is joined up."""
    report = Report()
    if not mesh.faces:
        report.add(
            error(
                "H1",
                "the compiler wrote a navmesh with no walkable surface in it at "
                "all: no zombie can path anywhere in this map, so no round can "
                "end. N1 to N4 say which of the generator's own limits the "
                "geometry broke",
            )
        )
        return report

    joins = _barricade_joins(blueprint, mesh, report)
    islands = mesh.islands(joins)
    seeded = _spawner_islands(blueprint, mesh, islands, report)
    walkable = frozenset().union(*seeded) if seeded else frozenset()

    _check_zones(blueprint, mesh, walkable, report)
    _check_player_difference(blueprint, mesh, walkable, report)
    _report_islands(mesh, islands, seeded, report)
    return report


# --------------------------------------------------------------------------
def _barricade_joins(blueprint, mesh: NavMesh, report: Report) -> list[tuple[int, int]]:
    """The face pairs a barricade animation joins, and the windows that join none."""
    joins: list[tuple[int, int]] = []
    for window in blueprint.elements(Window):
        origin = window.barricade_origin
        if origin is None:
            continue
        step = window.side.outward
        outside = origin + step.scaled(ACROSS_BARRICADE)
        inside = origin - step.scaled(ACROSS_BARRICADE)
        # Inside the face, not merely near it: the two probes are only
        # :data:`ACROSS_BARRICADE` apart, so a tolerance of a zombie's width
        # would let one face on the room side answer for both of them and a
        # barricade opening onto nothing would pass.
        yard = mesh.under(outside.x, outside.y, origin.z)
        room = mesh.under(inside.x, inside.y, origin.z)
        if yard is not None and room is not None:
            joins.append((yard, room))
            continue
        missing = "the yard behind it" if yard is None else "the room it opens into"
        report.add(
            error(
                "H1",
                f"the barricade at ({origin.x:g}, {origin.y:g}, {origin.z:g}) has "
                f"walkable surface on one side and none on {missing}. A zombie "
                "crosses a barricade by animation, from surface to surface: with "
                "surface on only one side it either never arrives or arrives and "
                "stops",
                window.id,
                f"({origin.x:g}, {origin.y:g}, {origin.z:g})",
            )
        )
    return joins


def _spawner_islands(
    blueprint, mesh: NavMesh, islands: Sequence[frozenset[int]], report: Report
) -> list[frozenset[int]]:
    """The pieces of mesh a spawn struct can put a zombie onto."""
    seeded: list[frozenset[int]] = []
    for spawn in blueprint.elements(Spawn):
        where = spawn.position
        if where is None:
            continue
        face = mesh.under(where.x, where.y, where.z, within=WITHIN_REACH)
        if face is None:
            below = mesh.under(where.x, where.y, where.z - CHARACTER_HEIGHT, within=0.0)
            report.add(
                error(
                    "H1",
                    f"the {spawn.kind} spawn struct of zone {spawn.zone_name!r} has "
                    f"no walkable surface within {WITHIN_REACH:g} units of it"
                    + (
                        ", though there is some a storey below: it is over the "
                        "wrong floor"
                        if below is not None
                        else ". A zombie rises here and then has to walk, and the "
                        "compiler laid no surface for it to walk on"
                    ),
                    spawn.id,
                    f"({where.x:g}, {where.y:g}, {where.z:g})",
                )
            )
            continue
        for island in islands:
            if face in island and island not in seeded:
                seeded.append(island)
    return seeded


def _check_zones(blueprint, mesh: NavMesh, walkable: frozenset[int], report: Report) -> None:
    """A zone the player stands in, with nothing for a zombie to stand on."""
    flood = flood_from_spawn(blueprint)
    for zone in blueprint.elements(Zone):
        if zone.bounds is None:
            continue
        mine = [
            cell
            for index, cell in enumerate(flood.cells)
            if index in flood.reached and _in_zone(zone.bounds, cell)
        ]
        if not mine:
            continue  # no player standing room in it: Z3, Z18 and Z25 own that
        if any(
            face.index in walkable
            and _plan_overlap(zone.bounds, face.bounds)
            and zone.bounds.mins.z - SAME_SURFACE <= face.high
            and face.low <= zone.bounds.maxs.z
            for face in mesh.faces
        ):
            continue
        spot = zone.bounds.centre
        report.add(
            error(
                "H1",
                f"zone {zone.name!r} is somewhere the player can walk to and has "
                "no walkable surface a zombie can reach in it, so nothing that "
                "spawns will ever come: the round runs on with the zone empty",
                zone.id,
                f"({spot.x:g}, {spot.y:g}, {spot.z:g})",
            )
        )


def _in_zone(bounds: Span, cell) -> bool:
    return (
        _plan_overlap(bounds, cell.floor)
        and bounds.mins.z - SAME_SURFACE <= cell.z <= bounds.maxs.z
    )


def _check_player_difference(
    blueprint, mesh: NavMesh, walkable: frozenset[int], report: Report
) -> None:
    """The finding this check exists for: where a player goes and nothing follows.

    Every rectangle ``Z25``'s flood reaches is tested against the mesh a
    spawner can get to.  A rectangle narrower than a zombie is passed over:
    the generator will not lay surface in a gap under its own
    ``minCharacterWidth`` (``N2``), so reporting one would be reporting the
    rule rather than a defect.
    """
    flood = flood_from_spawn(blueprint)
    if not flood.seeds:
        return  # Z25 says so; there is nothing to compare against
    ground = frozenset(terrain.id for terrain in blueprint.elements(Terrain))
    worst: dict[tuple[str, str], tuple[float, Span]] = {}
    for index in sorted(flood.reached):
        cell = flood.cells[index]
        if (
            cell.floor.extent(Axis.X) < MIN_CHARACTER_WIDTH
            or cell.floor.extent(Axis.Y) < MIN_CHARACTER_WIDTH
        ):
            continue
        slack = SAME_SURFACE + (
            SIMPLIFIED_GROUND if cell.element_id in ground else 0.0
        )
        if any(face in walkable for face in mesh.over(cell.floor, cell.z, slack)):
            continue
        if mesh.buried(cell.floor, cell.z):
            continue
        area = cell.floor.extent(Axis.X) * cell.floor.extent(Axis.Y)
        total, biggest = worst.get((cell.label, cell.element_id), (0.0, cell.floor))
        if area > biggest.extent(Axis.X) * biggest.extent(Axis.Y):
            biggest = cell.floor
        worst[(cell.label, cell.element_id)] = (total + area, biggest)
    furniture = _furniture(blueprint)
    for (label, element_id), (area, biggest) in sorted(
        worst.items(), key=lambda item: -item[1][0]
    ):
        spot = biggest.centre
        where = f"({spot.x:g}, {spot.y:g}, {biggest.mins.z:g})"
        if element_id in furniture:
            report.add(
                warning(
                    "H1",
                    f"{label} has {area:.0f} square units the player stands on and "
                    "no zombie can path to, the largest piece around "
                    f"({spot.x:g}, {spot.y:g}): a place they can be stood on and "
                    "not followed onto. For a table that is what a table is -- "
                    "measured, the generator lays no surface on anything "
                    f"more than {SAME_SURFACE:g} units up -- and for a platform "
                    "meant to be fought on it is the defect this check looks "
                    "for, so which one this is, is a question for the map",
                    element_id,
                    where,
                )
            )
            continue
        report.add(
            error(
                "H1",
                f"{label} has {area:.0f} square units the player walks to and no "
                "zombie can path to, the largest piece around "
                f"({spot.x:g}, {spot.y:g}); either the compiler laid no surface "
                "there, or the surface it laid is cut off from every spawn "
                "struct. This is the corner of the map where nothing comes for "
                "you",
                element_id,
                where,
            )
        )


def _furniture(blueprint) -> frozenset[str]:
    """Massings that are stood on rather than walked through.

    A room floor, a terrain cell and a flight of steps are *routes*: surface
    with no navmesh on them is an error, because that is where the walkers are
    supposed to go.  The top of any other walkable massing -- a table, a
    counter, a plinth, a crate -- is furniture, and the generator declining to
    put surface on it is the ordinary case rather than a defect.  The map does
    not say which of its slabs are meant to be fought on, so those are a
    warning and the reader decides.
    """
    return frozenset(
        massing.id
        for massing in blueprint.elements(Massing)
        if massing.note != "steps"
    )


def _report_islands(
    mesh: NavMesh,
    islands: Sequence[frozenset[int]],
    seeded: Sequence[frozenset[int]],
    report: Report,
) -> None:
    """How many pieces the mesh is in, and how much of it nothing can reach."""
    stranded = [island for island in islands if island not in seeded]
    if not stranded:
        return
    area = sum(mesh.faces[face].area for island in stranded for face in island)
    biggest = max(
        (mesh.faces[face] for island in stranded for face in island),
        key=lambda face: face.area,
    )
    spot = biggest.bounds.centre
    report.add(
        warning(
            "H1",
            f"the navmesh is in {len(islands)} pieces and {len(stranded)} of them, "
            f"{area:.0f} square units, no spawn struct can reach, the largest "
            f"around ({spot.x:g}, {spot.y:g}, {biggest.z:g}). Surface nothing "
            "stands on costs only the build; it is an error only where the "
            "player can walk there, which is reported separately",
        )
    )
