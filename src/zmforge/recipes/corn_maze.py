"""Harvest Moon: a corn maze farm at night, on Halloween, with a hayride you ride.

The map, as a player meets it (``zm_corn_maze``, recipe ``corn_maze``)::

    +------------------------------------------+
    | MAZE NORTH (entry zone, 2nd volume)  [bw]|   the maze: 15 x 15 cells of
    +-------+------------------+  <- gaps ->   |   288, round a 5 x 5 heart
    | MAZE  |     THE HEART    |               |
    | WEST  |   (scarecrow's   |  MAZE ENTRY   |  +-----------+
    | (deep |    clearing)     |  (water tower |  | FARMHOUSE |
    | zone) |                  |   clearing)   |  +---[750]---+--------------+
    |windmill+-----[1500]------+               +--+           |              |
    | [1250]  MAZE DEEP (deep zone, the power    [1000] FARMYARD | PUMPKIN      |
    | door  |   switch in a dead end)          |  |  (start)   | PATCH        |
    +-------+----------------------------------+  +---[power]--+--------------+
                                                     | BARN: PaP in the hayloft |
                                                     +--------------------------+

**The maze is one big maze in four rooms**, a pinwheel round the heart
(:data:`MAZE_ROOMS`, two rooms to a zone): in at the east from the farmyard,
north through the entry rows, west along the north rows, through the one
bought door into the west rows, south, and east along the south rows to the
gate of the heart, the middle of the whole field.  It is carved from a seed
(:func:`maze_passages`: a growing-tree carve, mostly depth-first, so long
winding corridors with side branches and about thirty dead ends, then a
dozen loops cut where no dead end is lost), and the tests walk it.  The
water tower and the windmill stand in two clearings, tall enough to see
over the corn from anywhere in it; a lantern every few cells marks the way
to the heart, and every dead end has a small scene, most with a light.

**Every outdoor area is walled in corn.**  Each is an unroofed room whose
walls are ``corn_height`` tall (well over :data:`zmforge.verify.reachability.
JUMP_UP`), so the corn blocks both movement and sight.  Four staggered
rows of the project's generated corn stalks, one every 8 units along the face,
each leaning a few degrees, the back row 280-320 tall over the wall top, on a
painted corn surface (``zmf_corn_wall``), line both faces of every corn wall (:func:`.corn_maze_parts._corn_band`, the
shared :func:`zmforge.dressing.lining.line_face`), 76 units deep, leaving 112 units of
clear path down a maze corridor (88 beside a room's own outer corn, which
is twice as thick; measured off the built map).  Beyond the walls a field of taller corn
(300-365 units, over the walls) and the ground under it run out on every side
(:func:`.corn_maze_parts._outskirts`), so the corn seen over any wall goes on.
Grass grows over all the outdoor ground (:func:`.corn_maze_parts._grass`,
about 4,000 cheap walk-through clumps): tall against the corn and fences, low
in the open, leaf litter down the trampled middle of a maze corridor, and
none on the walkways, the hayride lane or a buy spot.  The farmyard's north
and south are board fences, the farmhouse and barn side.  The pumpkins, hay bales, fences, scarecrows and the tractor are kit
props too (:mod:`.corn_maze_parts`).

**The hayride** (:mod:`zmforge.script.hayride`) is a flatbed trailer and the
farm's tractor, spawned by script at the stop in the farmyard, which drives the route :func:`hayride_route` out
through the gate, round the pumpkin patch and home.  Hold use at the stop,
pay 500, and you are linked onto a seat on the trailer and carried the whole
lap; everyone who boards in the five-second call rides together.  Out on
the route the prompt travels with the trailer: walk up to it, pay 500 and
hop on; you get off at the stop, but only a full lap counts for the quest.
The trailer and tractor are not solid while they drive, so they do not
shove anyone.

**Pack-a-Punch is in the hayloft**, up a flight of steps in the barn.  The
barn's door is electric: it opens when the power is on, and the power switch
is in the deepest dead end of the deep zone, so Pack-a-Punch comes after 2250
points of doors and a long walk through the corn, not one door from spawn.
The maze heart is the scarecrow's clearing.

The quest (Easter egg) and the win ending, designed here and wired through
the shared quest framework (``zmforge.script.quest``) when it lands:

1. **Light the way** (shoot) -- three jack-o'-lanterns burn with an unnatural
   light, one in the farmyard, one in the pumpkin patch, one in the maze;
   shoot all three out, within 90 seconds of the first (they light again
   if time runs out).
2. **Take the hayride** (ride) -- ride one full lap; the tractor comes back
   without a driver, and its keys are gone (the scarecrow has them).
3. **Feed the Great Pumpkin** (soul box) -- a giant jack-o'-lantern in the
   middle of the pumpkin patch, inside the hayride's loop, glows and eats
   the soul of every zombie a player kills near it, growing as it fills:
   20 souls solo, 8 more for each extra player.
4. **Golden ears** (collect) -- three golden ears of corn lie in the maze
   sections and the heart; each counts the moment you pick it up.
5. **Wake the scarecrow** (knife) -- knife the scarecrow in the maze heart
   three times within 15 seconds, and it climbs off its post.
6. **The Scarecrow** (mini-boss) -- kill it in the clearing; the tractor
   keys are in its pocket.
7. **Warm up the tractor** (defend) -- stay by the tractor while it
   warms up, 60 seconds, zombies pouring in.
8. **Leave at sunrise** (win) -- drive the tractor out of the farm
   for 20,000 points; buying it ends the game in a win.

The HUD line and the popups for each step, and the boss itself, belong to the
framework; :data:`QUEST_STEPS` is this map's text for them.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..atmosphere import HARVEST_HAZE
from ..dressing.maze import wall_runs
from . import corn_maze_layout as _layout
from ..blueprint.elements import STOCK_PLAYER_SLOTS, RoomMaterials
from ..blueprint.model import Blueprint
from ..materials import CAULK, SKY, FaceMaterials, Material
from ..props.corn import WALL_TILE_UNITS
from ..solids.layout import Aperture
from ..spatial import Bounds, Facing, Point, Side

__all__ = [
    "MAP_TITLE",
    "CornMazePlan",
    "FIXTURE",
    "ZONES",
    "QUEST_STEPS",
    "MAZE_ROOMS",
    "HEART_CELLS",
    "maze_passages",
    "maze_boxes",
    "dead_ends",
    "hayride_route",
    "corn_maze_map",
]

MAP_TITLE = "Harvest Moon"

#: The zones, in the order a player opens them.
ZONES = ("farmyard", "patch", "farmhouse", "mazeentry", "mazenorth", "mazewest", "mazedeep", "heart", "barn")

# --------------------------------------------------------------------------
# Surfaces.  All catalogued (materials.SURFACE_CATALOGUE / INSTALL_SURFACES):
# the install ships no corn, hay or pumpkin surface (grep of every
# texture_assets GDT for corn|wheat|hay|straw|thatch|pumpkin), so
# the corn is a wall of foliage: the grass surface behind close-set rows of
# kit corn stalks, so the wall reads as dense growth.  The golden sand
# (:data:`.corn_maze_assets.CORN_WALL_MATERIAL`, which links: it is
# in ``texture_assets/t7_rock.gdt`` with its images) was tried twice, with
# and without the dense stalk bands, and both times the outdoor rooms read as
# a quarry where it shows between the stalks; the lawn read as a hedge, the
# lesser fault.  The hay bales are kit props.
# The lawn draws as blue-grey slabs through the corn in
# every maze and yard view.  The walls are now
# the floor's own dark forest ground: the render draws it dark brown (it is
# the floor in every outdoor view), so the wall behind the stalks reads as
# shadowed earth between the rows.  No hedge, leaf or corn surface is in the
# install's texture GDTs (t7_grass has only lawn and crab grass).
# Outdoor rooms have no roof: their ceiling is the sky.
# --------------------------------------------------------------------------
# Corn walls need more than the stalks: the earth showed as a dirt wall through every gap
# in the stalk rows.  The walls are now a painted corn tile of our own
# (``props.library.CORN_WALL``, registered with the stalks), so a gap shows
# more corn further in.
_CORN = Material("zmf_corn_wall", WALL_TILE_UNITS)
_DIRT = Material("t7_dirt_grassy_forest_ground", 256.0)
_PLANKS = Material("t7_wood_planks_worn", 96.0)
_PANEL = Material("t7_wood_panel_01", 64.0)
#: Posts, beams and the farmhouse ceiling.  The sugar-pine veneer drew teal
#: (the table) and chequered teal on the farm stand posts; the
#: worn planks draw as wood.
_BEAM = Material("t7_wood_planks_worn", 64.0)
#: Ground cover on the outdoor floors: the pale rocky dirt, which
#: the render draws a light dry beige against the dark floor, laid coarse as
#: the trodden tracks, finer as the hoed crop rows and finest as the chaff
#: under a heap.  Not used: the
#: wet mud draws as slate-blue strips and the golden sand as a dark square.
#: Catalogued (CEMETERY_SURFACES).
#: In the pale dirt the tracks and rows read as pavement and parking bays,
#: so both are the floor's own grassy ground at a finer
#: repeat: the same colour, a different grain, low contrast; grass along the
#: tracks' edges (parts._edge_tufts) marks them.  Only the chaff under a heap
#: keeps the pale dirt.
_PATH = Material("t7_dirt_grassy_forest_ground", 96.0)
_TILLED = Material("t7_dirt_grassy_forest_ground", 40.0)
_STRAW = Material("t7_dirt_rocky_01", 24.0)
#: The scarecrow's clothes (parts._scarecrow_body): a red flannel shirt (the
#: worn brick laid small, as on the farmhouse rug) and denim legs (the wet
#: mud, which the render draws slate blue).
_FLANNEL = Material("t7_brick_worn_red", 12.0)
_DENIM = Material("t7_mud_ground_dirt_wet_01", 32.0)
_ROOF = Material("t7_rubber_roof_granular", 128.0)
_IRON = Material("t7_metal_worn_iron_dark", 64.0)
_BRICK = Material("t7_brick_worn_red", 96.0)
_KITCHEN = Material("t7_ceramic_tiles_6x6_dirty_01", 48.0)
#: Farmhouse walls: whitewashed plaster over a wood-panel wainscot is what the
#: catalogue can do; the plaster reads as a lived-in house, not an office.
_WHITEWASH = Material("t7_plaster_smooth_dirty_01", 128.0)

_OUTDOOR = RoomMaterials(wall=_CORN, floor=_DIRT, ceiling=SKY)
#: The farmyard: corn east and west, and board fences north and south, the
#: weathered planks the farmhouse and the barn face the yard with.
_YARD = RoomMaterials(wall=_CORN, floor=_DIRT, ceiling=SKY,
                      sides={Side.NORTH: _PLANKS, Side.SOUTH: _PLANKS})
_BARN = RoomMaterials(wall=_PLANKS, floor=_DIRT, ceiling=_PLANKS)
#: Farmhouse walls: weathered planks all round, like the barn and the yard
#: boards (the wood panel draws pink, a lone brick wall reads as odd and
#: whitewash reads as a bare plaster box).
_HOUSE = RoomMaterials(wall=_PLANKS, floor=_PLANKS, ceiling=_BEAM)

#: The night: The Giant's night preset and its real night sky, with a lit
#: harvest-moon haze pooling between the corn rows
#: (:data:`zmforge.atmosphere.HARVEST_HAZE`; the link needs the
#: stock zm_factory sky images in ``model_export``).
NIGHT_SKY = HARVEST_HAZE

#: Lantern light: a warm orange flame.  Moonlight: a harvest moon, low,
#: big and golden (a cold blue night reads as gloomy).
LANTERN = (1.0, 0.55, 0.18)
MOON = (0.95, 0.84, 0.62)
#: The whole map's lamps, a stop brighter than the preset's own exposure
#: (Blueprint.brightness_stops; the night reads as gloomy, and no
#: brighter night sky links: corn_maze_assets.HARVEST_NIGHT).
BRIGHTNESS_STOPS = 1.0


#: The maze: eight rooms in a ring round
#: the heart, two to a zone, laid out and carved by :mod:`.corn_maze_layout`
#: with the shared :func:`zmforge.dressing.maze.carve_maze`.  key -> (zone,
#: cell rectangle ``(i0, j0, i1, j1)``, ends exclusive).  A player buys their
#: way along a spiral: in from the farmyard at the east, north, west, south
#: (deep), then the heart, each gate dearer than the last (:data:`MAZE_GATES`).
#: The two rooms of one zone meet through a few open gaps in their corn.
MAZE_ROOMS: dict[str, tuple[str, tuple[int, int, int, int]]] = dict(_layout.ROOMS)
#: The heart's cells: the middle 5 x 5 of the 17 x 17 field (halved).
HEART_CELLS = _layout.HEART
#: The cell the farmyard gate opens into (east edge).
MAZE_ENTRANCE = _layout.ENTRANCE
#: The bought gates between the maze zones and into the heart, cheapest first.
MAZE_GATES = _layout.GATES
#: The gate into the deep zone (its deep-side cell first) and the heart's gate
#: (maze side first), as cell pairs.
DOOR_DEEP = next(g.cells for g in MAZE_GATES if g.key == "mazedeep")
DOOR_HEART = next(g.cells for g in MAZE_GATES if g.key == "heart")
_OPEN_BETWEEN = tuple(frozenset({a, b}) for a in MAZE_ROOMS for b in MAZE_ROOMS
                      if a < b and MAZE_ROOMS[a][0] == MAZE_ROOMS[b][0])
#: The landmark clearings (the lower-left cell of a 2 x 2 block with no walls
#: inside it): the water tower in the entry, the windmill in the west rows.
#: The layout's other clearings (:data:`.corn_maze_layout.CLEARINGS`) are the
#: burnt truck, the hay lookout and the creepy clearing.
CLEARINGS: dict[str, tuple[int, int]] = {
    key: _layout.CLEARINGS[key][:2] for key in ("water_tower", "windmill")}
#: Barricade windows in the maze: one on the outer edge of every maze room,
#: on a cell's middle, where no lattice post stands.  (room key, side, cell, id)
MAZE_WINDOWS: tuple[tuple[str, str, tuple[int, int], str], ...] = (
    ("mazeentry", "south", (14, 0), "mazeentry_window_south"),
    ("mazeentry_b", "east", (16, 9), "mazeentry_window_east"),
    ("mazenorth", "north", (14, 16), "mazenorth_window"),
    ("mazenorth_b", "north", (8, 16), "mazenorth_window_west"),
    ("mazewest", "west", (0, 14), "mazewest_window"),
    ("mazewest_b", "west", (0, 8), "mazewest_window_south"),
    ("mazedeep", "south", (2, 0), "mazedeep_window_south"),
    ("mazedeep_b", "south", (8, 0), "mazedeep_window_east"),
)

#: How often the carve grows from its newest cell rather than an older one.
BRANCH_NEWEST = _layout.BRANCH_NEWEST
#: The most gaps the carve cuts in the corn between the two rooms of a zone.
MAX_ROOM_GAPS = _layout.ZONE_GAPS

Cell = tuple[int, int]
Pair = tuple[Cell, Cell]


@dataclass(frozen=True)
class CornMazePlan:
    """Every number the recipe uses."""

    corn_height: float = 200.0
    wall: float = 24.0
    farmyard: Bounds = Bounds.between((-700, -600, 0), (700, 600, 200))
    patch: Bounds = Bounds.between((700, -600, 0), (2300, 900, 200))
    farmhouse: Bounds = Bounds.between((-450, 600, 0), (450, 1250, 272))
    barn: Bounds = Bounds.between((-550, -1600, 0), (550, -600, 480))
    #: The maze: a ``maze_size`` x ``maze_size`` grid of ``maze_pitch`` cells
    #: west of the farmyard, its south edge in line with the farmyard's, the
    #: heart its middle 5 x 5 (:data:`HEART_CELLS`).  A 288 cell leaves a
    #: 264-unit corridor between two corn walls: a band of stalks up to 76
    #: deep on each side and 112 of clear path down the middle.
    maze_size: int = _layout.SIZE
    maze_pitch: float = _layout.PITCH
    #: The seed the maze is carved from, and how many extra gaps are cut in it
    #: after the carve (each one a loop; never at a dead end).
    maze_seed: str = _layout.SEED
    maze_loops: int = 7
    #: The lane the hayride drives, across the farmyard and through the gate.
    lane_y: float = -300.0
    gate_width: float = 256.0
    #: The maze gates: a doorway-sized gap under an arch of corn, so the
    #: stock door leaf fills it (the leaf is sized for a doorway, and the
    #: door's collision is clip, so a bigger gap is a small door in an
    #: invisible wall).  The patch gate is the exception: the hayride
    #: drives through it, so it is wide and the full height of the corn.
    maze_gate_width: float = 96.0
    maze_gate_height: float = 112.0
    house_door: tuple[float, float] = (112.0, 112.0)
    barn_door: tuple[float, float] = (128.0, 144.0)
    door_prices: Mapping[str, int] = None  # type: ignore[assignment]
    #: The hayloft deck: its top height above the barn floor, and how far it
    #: reaches north from the barn's south wall.
    loft_height: float = 192.0
    loft_depth: float = 400.0
    hayride_price: int = 500
    hayride_speed: float = 170.0
    ending_price: int = 20000

    def __post_init__(self) -> None:
        if self.door_prices is None:
            object.__setattr__(self, "door_prices", {
                "patch": 1000, "farmhouse": 750, "mazeentry": 1000,
                **{g.key: g.price for g in _layout.GATES},
                # Electric: the checks want a positive price, but the stock
                # electric_door opens itself when the power comes on and
                # never charges it (_zm_blockers.gsc:819-826 waits for
                # "power_on" and calls door_opened itself).
                "barn": 1250,
            })

    @property
    def maze_origin(self) -> tuple[float, float]:
        """The south-west corner of cell (0, 0)."""
        return (self.farmyard.mins.x - self.maze_size * self.maze_pitch, self.farmyard.mins.y)

    def cells_box(self, rect: tuple[int, int, int, int]) -> Bounds:
        x0, y0 = self.maze_origin
        p = self.maze_pitch
        i0, j0, i1, j1 = rect
        return Bounds.between((x0 + i0 * p, y0 + j0 * p, 0.0), (x0 + i1 * p, y0 + j1 * p, self.corn_height))

    def maze_room(self, key: str) -> Bounds:
        return self.cells_box(MAZE_ROOMS[key][1])

    @property
    def heart(self) -> Bounds:
        return self.cells_box(HEART_CELLS)

    def cell_centre(self, cell: Cell) -> tuple[float, float]:
        x0, y0 = self.maze_origin
        return (x0 + (cell[0] + 0.5) * self.maze_pitch, y0 + (cell[1] + 0.5) * self.maze_pitch)

    def cell_of(self, x: float, y: float) -> Cell:
        x0, y0 = self.maze_origin
        return (int((x - x0) // self.maze_pitch), int((y - y0) // self.maze_pitch))


FIXTURE = CornMazePlan()


# --------------------------------------------------------------------------
# The maze
# --------------------------------------------------------------------------
def room_of(cell: Cell) -> str | None:
    """The maze room *cell* is in, or ``None`` (the heart, or off the grid)."""
    i, j = cell
    for key, (_, (i0, j0, i1, j1)) in MAZE_ROOMS.items():
        if i0 <= i < i1 and j0 <= j < j1:
            return key
    return None


def _pair(a: Cell, b: Cell) -> Pair:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _allowed(a: Cell, b: Cell) -> bool:
    """May the carve open the wall between neighbours *a* and *b*?  Inside one
    zone always (rationed between its two rooms); between zones only at a
    :data:`MAZE_GATES` pair."""
    return _layout._allowed(a, b)


def _neighbours(c: Cell, n: int) -> list[Cell]:
    return [(c[0] + dx, c[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= c[0] + dx < n and 0 <= c[1] + dy < n]


def maze_cells_all(n: int = FIXTURE.maze_size) -> list[Cell]:
    """Every cell of the maze (the heart's are not maze cells)."""
    return [(i, j) for j in range(n) for i in range(n) if room_of((i, j))]


def maze_passages(n: int = FIXTURE.maze_size, seed: str = FIXTURE.maze_seed,
                  loops: int = FIXTURE.maze_loops) -> frozenset[Pair]:
    """The open walls of the maze, as cell pairs: the v2 carve
    (:func:`.corn_maze_layout.carve`, the shared growing-tree carve with
    clearings, loops and a dead-end cap) plus its secret shortcuts, which are
    open for pathing and dressed as walk-through corn (:func:`secret_gaps`).
    *n* and *loops* are kept for callers; the layout fixes both."""
    return _layout.carve(seed)[0].passages


def secret_gaps(seed: str = FIXTURE.maze_seed) -> frozenset[Pair]:
    """The secret shortcuts: passages with no corn brush, planted with
    walk-through stalks so they look like wall until pushed through."""
    return _layout.carve(seed)[1]


def maze_graph(passages: frozenset[Pair] | None = None) -> dict[Cell, set[Cell]]:
    """Each maze cell's open neighbours."""
    passages = maze_passages() if passages is None else passages
    graph: dict[Cell, set[Cell]] = {c: set() for c in maze_cells_all()}
    for a, b in passages:
        graph[a].add(b)
        graph[b].add(a)
    return graph


def maze_distances(start: Cell, passages: frozenset[Pair] | None = None) -> dict[Cell, int]:
    """Steps from *start* to every cell, walking the passages."""
    graph = maze_graph(passages)
    dist = {start: 0}
    queue = [start]
    for c in queue:
        for nb in sorted(graph[c]):
            if nb not in dist:
                dist[nb] = dist[c] + 1
                queue.append(nb)
    return dist


def dead_ends(passages: frozenset[Pair] | None = None) -> list[Cell]:
    """Cells with one way in and out (the entrance and the heart's gate cell
    have a second, through their gate, so they are not dead ends)."""
    graph = maze_graph(passages)
    gates = {MAZE_ENTRANCE, DOOR_HEART[0]}
    return sorted(c for c, nbs in graph.items() if len(nbs) == 1 and c not in gates)


def room_gaps(a_key: str, b_key: str, passages: frozenset[Pair] | None = None) -> list[Pair]:
    """The open passages between maze rooms *a_key* and *b_key*."""
    passages = maze_passages() if passages is None else passages
    return sorted(p for p in passages if {room_of(p[0]), room_of(p[1])} == {a_key, b_key})


def maze_boxes(plan: CornMazePlan, key: str, interior: Bounds, floor_z: float,
               passages: frozenset[Pair] | None = None) -> list[Bounds]:
    """The corn brushes inside maze room *key*: one box per straight run of
    closed walls, on the cell lattice, clipped to the room's *interior* (its
    own walls do the rest).  North-south runs go the full length of the run
    and over its end posts; east-west runs stop at their faces, so nothing
    overlaps."""
    passages = maze_passages() if passages is None else passages
    return wall_runs(passages, MAZE_ROOMS[key][1], plan.maze_origin, plan.maze_pitch, plan.wall,
                     floor_z, plan.corn_height, clip=interior)


# --------------------------------------------------------------------------
# The hayride's route
# --------------------------------------------------------------------------
def hayride_route(plan: CornMazePlan = FIXTURE) -> tuple[tuple[float, float], ...]:
    """The hayride's waypoints in plan, starting and ending at the stop.

    Out along the lane across the farmyard, through the patch gate, one lap
    round the pumpkin field and back down the same lane.  Every point is at
    least :data:`HAYRIDE_WALL_CLEARANCE` inside the corn, which the tests pin.
    """
    y = plan.lane_y
    px0, px1 = plan.patch.mins.x, plan.patch.maxs.x
    py1 = plan.patch.maxs.y
    return (
        (plan.farmyard.mins.x + 300.0, y),          # the stop
        (px1 - 600.0, y),
        (px1 - 300.0, y + 200.0),
        (px1 - 300.0, py1 - 450.0),
        (px1 - 550.0, py1 - 250.0),
        (px0 + 550.0, py1 - 250.0),
        (px0 + 350.0, py1 - 450.0),
        (px0 + 350.0, y + 200.0),
        (px0 + 300.0, y),
        (plan.farmyard.mins.x + 300.0, y),
    )


#: How far any point of the route keeps from any corn wall's inside face.
HAYRIDE_WALL_CLEARANCE = 200.0
#: How far, in plan, set dressing and solids keep from the route's centre line.
HAYRIDE_LANE_HALF = 130.0


def distance_to_route(x: float, y: float, route: Sequence[tuple[float, float]]) -> float:
    best = math.inf
    for (ax, ay), (bx, by) in zip(route, route[1:]):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def _box_clear_of_route(box: Bounds, route, margin: float = HAYRIDE_LANE_HALF) -> bool:
    """True when no point of *box*'s plan footprint is within *margin* of the route."""
    xs = [box.mins.x + (box.maxs.x - box.mins.x) * i / 6 for i in range(7)]
    ys = [box.mins.y + (box.maxs.y - box.mins.y) * i / 6 for i in range(7)]
    return all(distance_to_route(x, y, route) >= margin for x in xs for y in ys)


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------
def _mid(a: float, b: float) -> float:
    return (a + b) / 2.0


def corn_maze_map(
    name: str,
    plan: CornMazePlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
    starting_points: int | None = None,
    gobblegums: int | None = None,
) -> Blueprint:
    """Harvest Moon.  See the module docstring for the map a player meets.

    ``starting_points`` is a testing aid (``zmforge generate
    --starting-points``), as on the DMV: every player starts with that many
    points.  ``None`` leaves the stock 500."""
    from . import corn_maze_parts as parts

    bp = Blueprint(name, seed=seed, title=MAP_TITLE)
    w = plan.wall
    corn_open = plan.corn_height - w  # an opening the full height of the corn

    def ap(side: Side, room_box: Bounds, at: float, width: float, height: float) -> Aperture:
        """An aperture centred on absolute coordinate *at* along *side*."""
        if side in (Side.EAST, Side.WEST):
            mid = _mid(room_box.mins.y, room_box.maxs.y)
        else:
            mid = _mid(room_box.mins.x, room_box.maxs.x)
        return Aperture(side, width, height, offset=at - mid)

    # Every maze gate and gap lands on a cell's middle, so no lattice post
    # stands in it.
    entry_gate_y = plan.cell_centre(MAZE_ENTRANCE)[1]
    heart_gate_x = plan.cell_centre(DOOR_HEART[0])[0]
    gap_width = plan.maze_pitch - 2 * w

    farmyard = bp.add_room(plan.farmyard, wall=w, roofed=False, materials=_YARD, openings=[
        ap(Side.EAST, plan.farmyard, plan.lane_y, plan.gate_width, corn_open),
        ap(Side.WEST, plan.farmyard, entry_gate_y, plan.maze_gate_width, plan.maze_gate_height),
        ap(Side.NORTH, plan.farmyard, 0.0, *plan.house_door),
        ap(Side.SOUTH, plan.farmyard, 0.0, *plan.barn_door),
    ], id="farmyard_room")
    patch = bp.add_room(plan.patch, wall=w, roofed=False, materials=_OUTDOOR, openings=[
        ap(Side.WEST, plan.patch, plan.lane_y, plan.gate_width, corn_open),
    ], id="patch_room")

    # ---- the maze: eight rooms round the heart (MAZE_ROOMS) --------------
    passages = maze_passages(plan.maze_size, plan.maze_seed, plan.maze_loops)
    boxes = {key: plan.maze_room(key) for key in MAZE_ROOMS}
    gate_pairs = {_pair(*g.cells): g for g in MAZE_GATES if g.key != "heart"}
    maze_openings: dict[str, list[Aperture]] = {
        "mazeentry": [ap(Side.EAST, boxes["mazeentry"], entry_gate_y, plan.maze_gate_width,
                         plan.maze_gate_height)]}
    #: (room a, room b, gate or None, index of the opening in room b)
    crossings: list[tuple[str, str, object, int]] = []
    _sides = {(1, 0): (Side.EAST, Side.WEST), (-1, 0): (Side.WEST, Side.EAST),
              (0, 1): (Side.NORTH, Side.SOUTH), (0, -1): (Side.SOUTH, Side.NORTH)}
    for a, b in sorted(passages):
        ra, rb = room_of(a), room_of(b)
        if ra == rb:
            continue
        gate = gate_pairs.get(_pair(a, b))
        if gate is not None and MAZE_ROOMS[ra][0] == gate.key:
            a, b, ra, rb = b, a, rb, ra          # the gate opens into its own zone, b
        side_a, side_b = _sides[(b[0] - a[0], b[1] - a[1])]
        at = plan.cell_centre(a)[0] if side_a in (Side.NORTH, Side.SOUTH) else plan.cell_centre(a)[1]
        width, height = ((plan.maze_gate_width, plan.maze_gate_height) if gate is not None
                         else (gap_width, corn_open))
        maze_openings.setdefault(ra, []).append(ap(side_a, boxes[ra], at, width, height))
        maze_openings.setdefault(rb, []).append(ap(side_b, boxes[rb], at, width, height))
        crossings.append((ra, rb, gate, len(maze_openings[rb]) - 1))
    maze_openings["mazedeep_b"] = maze_openings.get("mazedeep_b", []) + [
        ap(Side.NORTH, boxes["mazedeep_b"], heart_gate_x, plan.maze_gate_width, plan.maze_gate_height)]
    maze_rooms = {key: bp.add_room(boxes[key], wall=w, roofed=False, sunlit=True, materials=_OUTDOOR,
                                   openings=maze_openings.get(key, []), id=f"maze_{key[4:]}_room")
                  for key in MAZE_ROOMS}
    heart = bp.add_room(plan.heart, wall=w, roofed=False, materials=_OUTDOOR, openings=[
        ap(Side.SOUTH, plan.heart, heart_gate_x, plan.maze_gate_width, plan.maze_gate_height),
    ], id="heart_room")
    farmhouse = bp.add_room(plan.farmhouse, wall=w, materials=_HOUSE, openings=[
        ap(Side.SOUTH, plan.farmhouse, 0.0, *plan.house_door),
    ], id="farmhouse_room")
    barn = bp.add_room(plan.barn, wall=w, materials=_BARN, openings=[
        ap(Side.NORTH, plan.barn, 0.0, *plan.barn_door),
    ], id="barn_room")
    rooms = {"farmyard": farmyard, "patch": patch, **maze_rooms,
             "heart": heart, "farmhouse": farmhouse, "barn": barn}

    # Zones are keyed by room: the north and west maze rooms are second
    # volumes of the entry and deep zones (MAZE_ROOMS).
    zones = {
        "farmyard": bp.add_zone("farmyard", farmyard, starting=True),
        "patch": bp.add_zone("patch", patch),
        "farmhouse": bp.add_zone("farmhouse", farmhouse),
        **{key: bp.add_zone(zone, maze_rooms[key], id=f"zone_{key}")
           for key, (zone, _) in MAZE_ROOMS.items()},
        "heart": bp.add_zone("heart", heart),
        "barn": bp.add_zone("barn", barn),
    }

    # ---- the doors: buy through the corn --------------------------------
    price = plan.door_prices
    bp.add_door((zones["farmyard"], zones["patch"]), patch.opening(0),
                price=price["patch"], id="door_patch")
    bp.add_door((zones["farmyard"], zones["farmhouse"]), farmhouse.opening(0),
                price=price["farmhouse"], id="door_farmhouse")
    bp.add_door((zones["farmyard"], zones["mazeentry"]), maze_rooms["mazeentry"].opening(0),
                price=price["mazeentry"], id="door_mazeentry")
    # The maze gates (MAZE_GATES): each opens into its own zone, dearer as
    # the spiral goes in; the heart's is last.
    for ra, rb, gate, index in crossings:
        if gate is not None:
            bp.add_door((zones[ra], zones[rb]), maze_rooms[rb].opening(index),
                        price=price[gate.key], id=f"door_{gate.key}")
    bp.add_door((zones["mazedeep_b"], zones["heart"]), heart.opening(0),
                price=price["heart"], id="door_heart")
    # Electric: the barn opens when the power (deep in the maze) comes on.
    bp.add_door((zones["farmyard"], zones["barn"]), barn.opening(0),
                price=price["barn"], electric=True, id="door_barn")

    # ---- the corn inside the maze ----------------------------------------
    for key, room in maze_rooms.items():
        for index, box in enumerate(maze_boxes(plan, key, room.interior, room.floor_z, passages)):
            bp.add_block(box, _CORN, reachable=False, id=f"{key}_corn_{index}",
                         note="maze corn wall")

    dresser = parts.build_all(bp, plan, rooms, zones, player_slots=player_slots)
    _barn_battens(bp, rooms["barn"])
    bp.dressing_counts = dict(dresser.counts)  # type: ignore[attr-defined]
    # A set piece splitting a corridor in every maze room, the clearings'
    # scenes, fire and smoke, the secret shortcuts.
    from .corn_maze_setpieces import dress_set_pieces
    bp.set_piece_counts = dress_set_pieces(  # type: ignore[attr-defined]
        bp, plan, rooms, parts.maze_spots(plan, passages))
    # Vignettes: micro-stories at bends, wall faces, dead ends and clearing
    # rims (dressing.vignette), before the density
    # pass so its ground cover keeps off them.
    from .corn_maze_vignettes import dress_vignettes
    bp.vignette_counts = dress_vignettes(  # type: ignore[attr-defined]
        bp, plan, rooms, dresser, parts.maze_spots(plan, passages))
    # Density: ground cover under and along the corn, waist pieces in quiet
    # dead ends, pole lines overhead.
    from .corn_maze_setpieces import dress_maze_density
    bp.density_counts = dress_maze_density(  # type: ignore[attr-defined]
        bp, plan, rooms, dresser, parts.maze_spots(plan, passages))
    # Pieces a later pass left half on a blanket, or off their shelf (Z44).
    from ..placement.audit import drop_unsupported_dressing
    bp.unsupported_dropped = drop_unsupported_dressing(bp)  # type: ignore[attr-defined]
    # The corn those passes took from the back rows, put back where it fits
    # (Z89 bounds the longest bare stretch of a lined wall), then the support
    # pass again for any refill that landed on a blanket, and smaller again.
    bp.corn_refilled = 0  # type: ignore[attr-defined]
    for sizes in parts.REFILL_SIZES:
        bp.corn_refilled += parts.refill_bare(bp, dresser, sizes=sizes)  # type: ignore[attr-defined]
        bp.unsupported_dropped += drop_unsupported_dressing(bp)  # type: ignore[attr-defined]
    from .corn_maze_script import wire_script
    bp.quest = wire_script(bp, plan, rooms)  # type: ignore[attr-defined]

    if starting_points is not None:
        from ..script.tricks import starting_points as _starting_points

        bp.add_custom_logic(_starting_points(starting_points))

    bp.brightness_stops = BRIGHTNESS_STOPS
    bp.set_dog_rounds(False)
    # Night under The Giant's sky, ground fog in the rows (NIGHT_SKY).
    # GobbleGum beside the boxes, off above four players (script.gobblegum).
    from ..script.gobblegum import place_gobblegum_machines

    place_gobblegum_machines(bp, gobblegums)
    bp.enclose(atmosphere=NIGHT_SKY, id="enclosure")
    bp.light_rooms(colour=MOON)
    return bp


#: The quest's own text: ``(key, objective HUD line, popup when done)``.
QUEST_STEPS: tuple[tuple[str, str, str], ...] = (
    ("lanterns", "Shoot out the three burning jack-o'-lanterns",
     "The lanterns are out. Something in the corn noticed."),
    ("hayride", "Ride the hayride one full lap",
     "The hayride came back without its driver. It never had one."),
    ("pumpkin", "Feed the Great Pumpkin the souls of the dead killed near it",
     "The Great Pumpkin is full. It burps up a corn husk. A golden one."),
    ("ears", "Find the three golden ears of corn",
     "You found all the golden corn. The scarecrow wants it back."),
    ("wake", "Knife the scarecrow in the middle of the maze",
     "The scarecrow is climbing down off its post."),
    ("boss", "Kill the Scarecrow",
     "The Scarecrow is straw. You have the tractor keys."),
    ("defend", "Stay by the tractor while it warms up",
     "The engine caught. The ride out leaves at sunrise."),
    ("ending", "Drive the tractor out of the farm at sunrise",
     "The sun comes up over the corn. You drive out of Harvest Moon Farm. The corn waves goodbye."),
)


#: Board-and-batten siding on the barn's outer walls where they rise over an
#: open room's low wall (Z65: the north wall stood 256 units over the
#: farmyard's wall as one blank slab).  Battens every
#: ``BATTEN_EVERY`` along the wall, ``BATTEN_PROUD`` out, with a rail under
#: the eaves.
BATTEN_EVERY, BATTEN_WIDTH, BATTEN_PROUD = 56.0, 6.0, 3.0


def _barn_battens(bp, room) -> int:
    from ..dressing.facade import exposed_faces
    from ..spatial import Bounds

    n = 0
    for ex in exposed_faces(bp, room, least=48.0):
        if ex.seen_from is None:
            continue
        f = ex.face
        out = -f.inward
        c0, c1 = sorted((f.back, f.back + out * BATTEN_PROUD))
        z0, z1 = ex.base - 8.0, f.top

        def strip(a0: float, a1: float, lo: float, hi: float, ident: str) -> None:
            lo_pt = (a0, c0, lo) if f.along_x else (c0, a0, lo)
            hi_pt = (a1, c1, hi) if f.along_x else (c1, a1, hi)
            bp.add_block(Bounds.between(lo_pt, hi_pt), _BEAM, contents=("detail",), reachable=False,
                         id=ident, note="barn batten")

        a = f.a0 + BATTEN_EVERY / 2.0
        while a < f.a1 - BATTEN_WIDTH:
            strip(a, a + BATTEN_WIDTH, z0, z1, f"barn_batten_{ex.side.name.lower()}_{n}")
            n += 1
            a += BATTEN_EVERY
        strip(f.a0, f.a1, z1 - 14.0, z1 - 4.0, f"barn_eave_rail_{ex.side.name.lower()}")
    return n
