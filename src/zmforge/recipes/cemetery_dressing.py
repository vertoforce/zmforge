"""Set dressing, notices and gags for :mod:`zmforge.recipes.cemetery`.

Every area gets its brushwork (headstones, mausoleums, fences, trees -- see
:mod:`zmforge.recipes.cemetery_kit`) and at least :data:`MIN_MODELS` measured
models from :data:`zmforge.recipes.props.MODEL_BOX` (ground cover, rocks,
bones, tools, candles' company), placed by one :class:`Dresser` that keeps
everything off doorways, window fronts, spawns, the walking paths and every
interactive's standing room, and seats each model on the lowest ground under
its own footprint so nothing hangs off a slope.

Prop groups are named ``dress_<area>_<what>`` so a test can count an area.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from .. import progress
from ..script.glow import place_owned_glow
from ..blueprint.elements import Spawn, Window
from ..blueprint.model import Blueprint
from ..dressing import RAIL, hang_bar
from ..dressing.cluster import Tier, clustered_points, mixed_clumps, rect_edges
from ..placement.audit import SUPPORT_REACH
from ..spatial import Bounds, Facing, Point, Side
from . import cemetery_kit as kit
from .props import MODEL_BOX, _mount_face, collision_box, is_solid

__all__ = ["MIN_MODELS", "Dresser", "dress", "wire_notices", "wire_gags", "AREAS"]

#: Measured models every area carries at least (50 to 100 props per area
#: is the target; brushwork is on top of this).
MIN_MODELS = 50

#: Area key -> the zone its props are counted under.
AREAS = ("gate", "shed", "hills", "row", "vault", "chapel", "stairs", "ossuary", "tomb")

#: Warm light for torches, lanterns and candles.
FLAME = (1.0, 0.62, 0.3)
#: Cold light for the will-o'-wisp lanterns.
WISP = (0.55, 0.85, 1.0)

GROUND_COVER = (
    "p7_foliage_grass_tall_cluster_sml",
    "p7_foliage_grass_tall_single_sml",
    "p7_foliage_weed_cluster_lrg",
    "p7_foliage_weed_cluster_med",
    "p7_foliage_weed_cluster_sml_a",
    "p7_3arc_park_leaves_grp_2",
    "p7_3arc_park_leaves_corner_1",
    "p7_debris_rockychunks_small_05",
    "p7_debris_rockychunks_small_08",
    "p7_debris_rockychunks_small_10",
)
BIG_COVER = (
    "p7_foliage_grass_tall_cluster_med",
    "p7_foliage_grass_tall_single_lrg",
    "p7_rock_sing_park_06",
    "p7_debris_rockychunks_small_12",
    "p7_foliage_tree_acacia_bush",
)
#: Graveside planting: kept plants and a flower pot or two by the stones.
GRAVESIDE = ("p7_foliage_plant_meskel_3_noflower", "p7_foliage_grass_tall_cluster_sml",
             "p7_foliage_weed_cluster_sml_a")
#: What lies on the floor of the family vault: bones, dust and grave goods.
VAULT_FLOOR = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03",
               "p7_debris_concrete_rubble_sm_02", "p7_debris_rockychunks_small_05",
               "p7_bottle_glass_wine_01", "p7_book_vintage_01_burn")
#: Bones without meat on them, for niches, lids and treads.
SKULL_BONES = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03")
#: The crypt's floors: bones, broken brick and stone, no modern blocks.
CRYPT_FLOOR = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03",
               "p7_brick_dirty_01", "p7_brick_dirty_02", "p7_brick_dirty_03", "p7_brick_dirty_04",
               "p7_debris_brick_chunk_01", "p7_debris_brick_chunk_02", "p7_debris_brick_chunk_03",
               "p7_debris_brick_single_01", "p7_debris_rockychunks_small_01",
               "p7_debris_rockychunks_small_07", "p7_debris_rockychunks_small_09",
               "p7_debris_plaster_rubble_med_01", "p7_debris_concrete_rubble_sm_02")
#: What else lies in a burial niche beside the bones: crumbled mortar.
NICHE_BITS = SKULL_BONES + ("p7_debris_brick_chunk_hlf_01", "p7_debris_brick_chunk_hlf_02")
BONES = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03", "p7_gib_chunk_meat_01")
RUBBLE = ("p7_debris_concrete_rubble_sm_02", "p7_brick_dirty_01", "p7_debris_brick_single_01",
          "p7_cinder_block", "p7_debris_rockychunks_small_05")
BOOKS = ("p7_book_vintage_01", "p7_book_vintage_open_04", "p7_book_vintage_01_burn")
BOTTLES = ("p7_bottle_glass_wine_01", "p7_decanter_glass_bottle", "p7_bottle_glass_liquor_01")

#: The CC0 graveyard kit (``recipes.props.PALETTE["zmforge_kit"]``): real
#: headstone, cross, fence and pumpkin models.
STONE_ROUND = "zmf_prop_gravestone_round"
STONE_CROSS = "zmf_prop_gravestone_cross"
STONE_BROKEN = "zmf_prop_gravestone_broken"
WOODEN_CROSS = "zmf_prop_wooden_cross"
FENCE_IRON = "zmf_prop_fence_iron"
JACK = "zmf_prop_jack_o_lantern"
JACK_TALL = "zmf_prop_jack_o_lantern_tall"
PUMPKIN = "zmf_prop_pumpkin"
HAND_CART = "zmf_prop_hand_cart"
#: Which way the kit's models look at yaw 0, in world degrees.  The kits
#: author Y-up with the front on +Z, and ``props.xmodel`` maps (x, y, z) to
#: (x, -z, y), so the front ends up on -y: south.  Measured off the meshes:
#: the carved pumpkin has 120 vertices on +Z to 51 on -Z (the
#: cut face), the round headstone 54 to 35 (the carving).
KIT_FACE = 270.0
#: Grave markers for an ordinary plot: (cumulative chance, model).  Whatever
#: the roll leaves over is a brush stone, cross or needle (``kit``).
PLOT_MARKERS = ((0.30, STONE_ROUND), (0.48, STONE_CROSS), (0.62, STONE_BROKEN))
#: How much further back from its mound a model marker stands than a brush one.
MARKER_SETBACK = 10.0
#: The older section: wooden crosses and broken stones.
OLD_MARKERS = ((0.6, WOODEN_CROSS), (0.8, STONE_BROKEN), (0.88, STONE_ROUND))


def kit_yaw(facing: Facing) -> float:
    """The yaw that turns a kit model's front to ``facing``."""
    return (facing.world_yaw - KIT_FACE) % 360.0


_CELL = 128.0


def _index(grid: dict, box, item) -> None:
    """File *item* under every grid cell its plan *box* touches."""
    x0, y0, x1, y1 = box
    for i in range(math.floor(x0 / _CELL), math.floor(x1 / _CELL) + 1):
        for j in range(math.floor(y0 / _CELL), math.floor(y1 / _CELL) + 1):
            grid.setdefault((i, j), []).append(item)


def _near(grid: dict, box):
    """Every item filed under a cell *box* touches (an item may repeat)."""
    x0, y0, x1, y1 = box
    for i in range(math.floor(x0 / _CELL), math.floor(x1 / _CELL) + 1):
        for j in range(math.floor(y0 / _CELL), math.floor(y1 / _CELL) + 1):
            yield from grid.get((i, j), ())


def _half(model: str, yaw: float, scale: float = 1.0) -> tuple[float, float]:
    (x0, y0, _), (x1, y1, _) = collision_box(model)
    w, d = (x1 - x0) * scale / 2.0, (y1 - y0) * scale / 2.0
    c, s = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
    return w * c + d * s, w * s + d * c


@dataclass
class Dresser:
    """Places models and brush features for one map, keeping them apart and
    off everything a player or a zombie needs."""

    bp: Blueprint
    seed: int = 1897
    keepouts: list[tuple[float, float, float, float]] = field(default_factory=list)
    taken: list[tuple[float, float, float]] = field(default_factory=list)
    pending: dict[str, list[tuple]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    #: Iron fence cells laid as the panel model / as brush (``_iron_fence_line``).
    fences: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        # Grid indexes over keepouts, claimed discs and block boxes, so a
        # free-space test looks at its neighbourhood, not every item laid
        # (the three-height fill lays thousands of props).
        self._kidx: dict = {}
        self._tidx: dict = {}
        self._bidx: dict = {}
        for box in self.keepouts:
            _index(self._kidx, box, box)
        for x, y, r in self.taken:
            _index(self._tidx, (x - r, y - r, x + r, y + r), (x, y, r))

    # -- where nothing goes ------------------------------------------------
    def keep(self, x0: float, y0: float, x1: float, y1: float) -> None:
        box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self.keepouts.append(box)
        _index(self._kidx, box, box)

    def keep_disc(self, x: float, y: float, r: float) -> None:
        self.keep(x - r, y - r, x + r, y + r)

    def free(self, x: float, y: float, hx: float, hy: float, *, pad: float = 6.0,
             z: float | None = None) -> bool:
        for kx0, ky0, kx1, ky1 in _near(self._kidx, (x - hx, y - hy, x + hx, y + hy)):
            if x + hx > kx0 and x - hx < kx1 and y + hy > ky0 and y - hy < ky1:
                return False
        self._blocks()
        for bx0, by0, bx1, by1 in _near(self._bidx, (x - hx - pad, y - hy - pad, x + hx + pad, y + hy + pad)):
            if x + hx > bx0 - pad and x - hx < bx1 + pad and y + hy > by0 - pad and y - hy < by1 + pad:
                return False
        for cx, cy in ((x - hx, y - hy), (x + hx, y - hy), (x - hx, y + hy), (x + hx, y + hy)):
            if not self.bp.ground_under(cx, cy).found:
                return False
        r = math.hypot(hx, hy)
        for tx, ty, tr in _near(self._tidx, (x - r - pad, y - r - pad, x + r + pad, y + r + pad)):
            if math.hypot(x - tx, y - ty) < r + tr + pad:
                return False
        at = Point(x, y, self.ground(x, y) if z is None else z)
        return not self.bp.interactive_blocks(at, hx + 8.0, hy + 8.0)

    def clear(self, x: float, y: float, r: float) -> bool:
        """Nothing kept clear and no brush block within *r* of (x, y), not
        on a claimed piece's core, and ground under it: the test for
        walk-through cover, which may crowd other cover but never a way, a
        door or the kit."""
        for kx0, ky0, kx1, ky1 in _near(self._kidx, (x - r, y - r, x + r, y + r)):
            if x + r > kx0 and x - r < kx1 and y + r > ky0 and y - r < ky1:
                return False
        self._blocks()
        m = r + 14.0  # off every block's edge, so no cover grazes a kerb or mound (Z44)
        for bx0, by0, bx1, by1 in _near(self._bidx, (x - m, y - m, x + m, y + m)):
            if x + m > bx0 and x - m < bx1 and y + m > by0 and y - m < by1:
                return False
        for tx, ty, tr in _near(self._tidx, (x - r, y - r, x + r, y + r)):
            if math.hypot(x - tx, y - ty) < 0.5 * tr + r:
                return False
        hit = self.bp.ground_under(x, y)
        if not hit.found:
            return False
        # Never in front of a perk, box or wall buy (Z48).
        return not self.bp.interactive_blocks(Point(x, y, hit.z), r + 56.0, r + 56.0)

    def _blocks(self) -> list[tuple[float, float, float, float]]:
        """Plan boxes of every brush block laid so far (the kit's headstones,
        tombs, trees...), so a model never stands half on one.  Blocks that
        start well over the ground under them (a roof, a cable, a lantern's
        hook plate) leave the floor under them free."""
        from ..blueprint.elements import Massing
        from ..blueprint.model import _solid_bounds

        massings = self.bp.elements(Massing)
        done = getattr(self, "_block_count", 0)
        if len(massings) < done:
            done = 0
            self._block_cache = []
            self._bidx = {}
        if len(massings) != done:
            # Only the blocks laid since the last call (elements keep their
            # install order); the ground test makes a full rebuild costly.
            boxes = list(getattr(self, "_block_cache", []))
            for m in massings[done:]:
                for solid in m.solids:
                    b = _solid_bounds(solid)
                    if b.mins.z > 90.0:
                        hit = self.bp.ground_under((b.mins.x + b.maxs.x) / 2.0,
                                                   (b.mins.y + b.maxs.y) / 2.0)
                        if not hit.found or b.mins.z > hit.z + 90.0:
                            continue
                    boxes.append((b.mins.x, b.mins.y, b.maxs.x, b.maxs.y))
                    _index(self._bidx, boxes[-1], boxes[-1])
            self._block_cache = boxes
            self._block_count = len(massings)
        return self._block_cache

    def _one_cell(self, x: float, y: float, hx: float, hy: float) -> bool:
        """On terrain, whether the footprint lies inside one grid cell.

        Under a mesh terrain the emitter fills each cell with a caulk block
        whose top is that cell's lowest corner (``emit.mapfile._terrain_plinth``),
        and the written-map layout check (``Z44``) reads the highest of those
        under a prop as what it stands on; a prop straddling two cells stands
        partly over the lower one and is reported as overhanging.  Inside one
        cell it is wholly over one block.
        """
        hit = self.bp.ground_under(x, y)
        if not hit.source.startswith("terrain"):
            return True
        record = self.bp.find(hit.element_id).record
        ax, ay = record.anchor.x, record.anchor.y
        cols = {math.floor((px - ax) / record.x_cell) for px in (x - hx, x + hx)}
        rows = {math.floor((py - ay) / record.y_cell) for py in (y - hy, y + hy)}
        return len(cols) == 1 and len(rows) == 1

    def terrain_cell(self, x: float, y: float) -> tuple[float, float, float, float] | None:
        """The terrain grid cell ``(x0, y0, x1, y1)`` under (x, y), or None
        off the terrain."""
        hit = self.bp.ground_under(x, y)
        if not hit.found or not hit.source.startswith("terrain"):
            return None
        record = self.bp.find(hit.element_id).record
        ax, ay = record.anchor.x, record.anchor.y
        i = math.floor((x - ax) / record.x_cell)
        j = math.floor((y - ay) / record.y_cell)
        return (ax + i * record.x_cell, ay + j * record.y_cell,
                ax + (i + 1) * record.x_cell, ay + (j + 1) * record.y_cell)

    def into_cell(self, x: float, y: float, margin: float) -> tuple[float, float]:
        """(x, y) moved the least distance that puts a footprint ``margin``
        each way wholly inside the terrain cell it is in (see
        :meth:`_one_cell`).  Off the terrain it stays put."""
        cell = self.terrain_cell(x, y)
        if cell is None:
            return x, y
        x0, y0, x1, y1 = cell
        return (min(max(x, x0 + margin + 1.0), x1 - margin - 1.0),
                min(max(y, y0 + margin + 1.0), y1 - margin - 1.0))

    def claim(self, x: float, y: float, r: float) -> None:
        self.taken.append((x, y, r))
        _index(self._tidx, (x - r, y - r, x + r, y + r), (x, y, r))

    # -- ground ------------------------------------------------------------
    def ground(self, x: float, y: float) -> float:
        return self.bp.ground_under(x, y).z

    def low(self, x0: float, y0: float, x1: float, y1: float) -> float:
        pts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2)]
        steps = 4
        for i in range(steps + 1):
            for j in range(steps + 1):
                pts.append((x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * j / steps))
        found = [hit.z for hit in (self.bp.ground_under(px, py) for px, py in pts) if hit.found]
        if not found:
            raise ValueError(f"no ground under ({x0:g},{y0:g})..({x1:g},{y1:g})")
        return min(found)

    def high(self, x0: float, y0: float, x1: float, y1: float) -> float:
        """The highest ground under the box, sampled as :meth:`low` samples it."""
        steps = 4
        found = [hit.z for hit in (self.bp.ground_under(x0 + (x1 - x0) * i / steps,
                                                        y0 + (y1 - y0) * j / steps)
                                   for i in range(steps + 1) for j in range(steps + 1))
                 if hit.found]
        if not found:
            raise ValueError(f"no ground under ({x0:g},{y0:g})..({x1:g},{y1:g})")
        return max(found)

    # -- models ------------------------------------------------------------
    def prop(self, area: str, group: str, model: str, x: float, y: float, yaw: float = 0.0,
             *, surface: float | None = None, solid: bool | None = None, check: bool = True,
             scale: float = 1.0, snap: bool = False) -> bool:
        """One model centred on (x, y), resting on ``surface`` or on the
        lowest ground under it.  Returns False (and places nothing) when the
        spot is taken or kept clear.  With ``snap`` the spot first moves the
        least that puts the footprint in one terrain cell (:meth:`into_cell`),
        which a shrub nearly a cell wide needs."""
        if model not in MODEL_BOX:
            raise KeyError(f"{model} is not a measured model")
        hx, hy = _half(model, yaw, scale)
        if snap:
            x, y = self.into_cell(x, y, max(hx, hy))
        if check and not self.free(x, y, hx, hy, z=surface):
            return False
        if check and surface is None and not self._one_cell(x, y, hx, hy):
            return False
        box = collision_box(model)
        rest = surface if surface is not None else self._seat(model, x, y, hx, hy, scale)
        z = rest - box[0][2] * scale
        cx, cy = (box[0][0] + box[1][0]) / 2.0 * scale, (box[0][1] + box[1][1]) / 2.0 * scale
        t = math.radians(yaw)
        ox, oy = cx * math.cos(t) - cy * math.sin(t), cx * math.sin(t) + cy * math.cos(t)
        solid = is_solid(model) if solid is None else solid
        self.pending.setdefault(f"dress_{area}_{group}", []).append(
            (model, Point(x - ox, y - oy, z), yaw % 360.0, scale, solid))
        self.counts[area] = self.counts.get(area, 0) + 1
        if check:
            self.claim(x, y, max(hx, hy))
        return True

    def _seat(self, model: str, x: float, y: float, hx: float, hy: float,
              scale: float) -> float:
        """Where a model on the ground rests: the lowest ground under its
        footprint, but on a slope never sunk more than a third of its height
        (at most 3 units) below the ground at its centre, so a low leaf pile
        or weed is not buried on the uphill side."""
        low = self.low(x - hx, y - hy, x + hx, y + hy)
        hit = self.bp.ground_under(x, y)
        if not hit.found:
            return low
        (_, _, z0), (_, _, z1) = collision_box(model)
        sink = min(3.0, (z1 - z0) * scale / 3.0)
        return max(low, hit.z - sink)

    def piece(self, area: str, group: str, model: str, x: float, y: float, yaw: float = 0.0,
              *, surface: float | None = None, solid: bool | None = None,
              reach: float = 96.0) -> tuple[float, float]:
        """A named set piece the story or the notices rely on: the spot asked
        for, else the nearest free spot on rings round it (up to ``reach``
        out).  Raises when there is none, so a planned piece never silently
        drops out of the map.  Returns where it went."""
        tries = [(x, y)] + [(x + r * math.cos(a), y + r * math.sin(a))
                            for r in [16.0 * k for k in range(1, int(reach // 16) + 1)]
                            for a in [k * math.pi / 6 for k in range(12)]]
        for tx, ty in tries:
            if self.prop(area, group, model, tx, ty, yaw, surface=surface, solid=solid):
                return tx, ty
        raise ValueError(f"set piece {model} ({area}/{group}) found no free spot within "
                         f"{reach:g} of ({x:g}, {y:g})")

    def mounted(self, area: str, group: str, model: str, x: float, y: float, z: float,
                facing: Facing) -> None:
        """A wall fixture at (x, y, z) looking ``facing``."""
        yaw = (facing.world_yaw - _mount_face(model)) % 360.0
        self.pending.setdefault(f"dress_{area}_{group}", []).append(
            (model, Point(x, y, z), yaw, 1.0, False))
        self.counts[area] = self.counts.get(area, 0) + 1

    def scatter(self, area: str, group: str, palette: Sequence[str], x0: float, y0: float,
                x1: float, y1: float, count: int, *, tries: int = 30) -> int:
        """``count`` models from ``palette`` at seeded free spots in a rectangle."""
        placed = 0
        for _ in range(count * tries):
            if placed >= count:
                break
            model = self.rng.choice(list(palette))
            x, y = self.rng.uniform(x0, x1), self.rng.uniform(y0, y1)
            if self.prop(area, group, model, x, y, self.rng.uniform(0.0, 360.0)):
                placed += 1
        return placed

    def clumped(self, area: str, group: str, palette: Sequence[str], x0: float, y0: float,
                x1: float, y1: float, count: int, *, per: tuple[int, int] = (3, 6),
                reach: float = 60.0, edges: Sequence | None = None, edge_bias: float = 0.85,
                parent_gap: float = 90.0, scale: tuple[float, float] = (1.0, 1.0),
                snap: bool = False) -> int:
        """``count`` models from ``palette`` in seeded clumps of *per*
        pieces within *reach* of each clump's centre, the centres drawn
        toward *edges* (default :func:`shelter_edges` of the rectangle)
        with bare ground between them (:func:`dressing.cluster.mixed_clumps`),
        because an even spread reads as artificial.  Returns pieces laid."""
        if edges is None:
            edges = shelter_edges(self, (x0, y0, x1, y1))
        tier = Tier(tuple((m, scale, 1) for m in palette), per, (0.0, reach))

        def place(model, x, y, yaw, sc):
            return self.prop(area, group, model, x, y, yaw, scale=sc, snap=snap)

        return len(mixed_clumps(self.rng, (x0, y0, x1, y1), (tier,), count, place=place,
                                edges=edges, edge_bias=edge_bias, edge_offset=24.0,
                                parent_gap=parent_gap))

    def flush(self) -> None:
        for ident, items in self.pending.items():
            if items:
                self.bp.place_props(items, id=ident)
        self.pending = {}


# ---------------------------------------------------------------------------
# Keep-outs
# ---------------------------------------------------------------------------
def shelter_edges(d: Dresser, rect: tuple[float, float, float, float], *,
                  graves_only: bool = False) -> list:
    """What plants gather against inside *rect* ``(x0, y0, x1, y1)``: its
    sides (the walls' feet), the walks' kerbs, every brush block standing
    on the ground (headstones, grave mounds, tombs, tree trunks, monuments,
    benches, piers) and every claimed piece 20 or more across, as
    :mod:`dressing.cluster` edges.  With *graves_only*, the grave mounds
    and plot stones alone (blocks under 200 across).  Plants
    grow at the feet of things, not spread evenly."""
    from .cemetery import path_boxes

    x0, y0, x1, y1 = rect
    edges: list = [] if graves_only else rect_edges(x0, y0, x1, y1)

    def inside(a, b, c, e) -> bool:
        return a < x1 and c > x0 and b < y1 and e > y0

    if not graves_only:
        for _room, a, b, c, e in path_boxes().values():
            if inside(a, b, c, e):
                edges += rect_edges(a, b, c, e)
    limit = 200.0 if graves_only else 600.0
    for a, b, c, e in d._blocks():
        if c - a <= limit and e - b <= limit and inside(a, b, c, e):
            edges += rect_edges(a, b, c, e)
    if not graves_only:
        edges += [(tx, ty, 0.6 * tr) for tx, ty, tr in d.taken
                  if tr >= 20.0 and x0 <= tx <= x1 and y0 <= ty <= y1]
    return edges


def _keep_the_ways_clear(d: Dresser, bp: Blueprint, rooms: Mapping[str, object]) -> None:
    for room in rooms.values():
        for box in room.aperture_boxes:
            d.keep(box.mins.x - 110, box.mins.y - 110, box.maxs.x + 110, box.maxs.y + 110)
    for window in bp.elements(Window):
        o = window.barricade_origin
        d.keep_disc(o.x, o.y, 120.0)
    for spawn in bp.elements(Spawn):
        d.keep_disc(spawn.position.x, spawn.position.y, 64.0)
    from .cemetery import START

    d.keep_disc(START[0], START[1], 150.0)
    # The walks and forecourts (``cemetery.PATHS``/``FORECOURTS``), each with
    # a little margin, so nothing is dressed onto the dirt a player follows.
    from .cemetery import path_boxes

    for _room, x0, y0, x1, y1 in path_boxes().values():
        d.keep(x0 - PATH_MARGIN, y0 - PATH_MARGIN, x1 + PATH_MARGIN, y1 + PATH_MARGIN)
    # The crypt stair, top to bottom.
    stairs = rooms["stairs"].interior
    d.keep(stairs.mins.x, -380, stairs.maxs.x - 60, -228)


#: How far past a walk's edge the dressing keeps clear.
PATH_MARGIN = 8.0
#: The readable headstones, laid at these spots without a free-space check
#: (:func:`_dress_gate`, :func:`_dress_hills`): (key, x, y, facing).
GATE_STONES = (("told_you", -1380.0, 170.0, Facing.SOUTH),
               ("back_soon", -1180.0, -170.0, Facing.NORTH),
               ("return", -960.0, 170.0, Facing.SOUTH))
HILLS_STONES = (("pieces", -520.0, 170.0, Facing.SOUTH),
                ("wifi", 60.0, -170.0, Facing.NORTH),
                ("diet", 700.0, 170.0, Facing.SOUTH),
                ("plot_twist", 360.0, 700.0, Facing.WEST))
#: The will-o'-wisp lanterns (quest step 3), on four hills.
WISP_SPOTS = ((-240.0, -520.0), (500.0, 700.0), (-420.0, 620.0), (640.0, -360.0))
#: The "plots for sale" sign by the gate walk.
SALE_SIGN = (-1300.0, -150.0)


def _reserve_set_pieces(d: Dresser) -> None:
    """Claim the ground of every set piece laid later at a fixed spot and
    without a free-space check (readable stones, the sale sign, the wisps,
    mausoleums, tombs, the Founder's needle, the Open Grave), so the path
    lamps and the scatter laid before them keep off it."""
    from .cemetery import FOUNDER_NEEDLE, MAUSOLEUMS, OPEN_GRAVE, ROW_TOMBS

    for _key, x, y, _facing in GATE_STONES + HILLS_STONES:
        d.claim(x, y, 40.0)
    d.claim(SALE_SIGN[0], SALE_SIGN[1], 36.0)
    for x, y in WISP_SPOTS:
        d.claim(x, y, 44.0)
    for _key, _family, x, y, _facing, _h in MAUSOLEUMS:
        d.keep(x - 150, y - 150, x + 150, y + 150)
    for _key, x, y, _facing in ROW_TOMBS:
        d.keep(x - 110, y - 140, x + 110, y + 140)
    fx, fy, _ = FOUNDER_NEEDLE
    d.keep(fx - 70, fy - 70, fx + 70, fy + 70)
    ox, oy, _ = OPEN_GRAVE
    d.keep(ox - 90, oy - 90, ox + 90, oy + 100)


# ---------------------------------------------------------------------------
# Path lamps
# ---------------------------------------------------------------------------
#: How far out from a walk's edge a lamp post stands, and the spacing along
#: the walk the pairs aim for.
LAMP_SETBACK = 36.0
LAMP_SPACING = 300.0
#: Walks shorter than this (the links through the row's gate and round to
#: the vault door) get no lamps: they lie in doors' keep-outs and corners.
MIN_LAMP_WALK = 200.0
#: Boxes this close count as meeting (a junction, or a door's wall gap).
JUNCTION_GAP = 40.0
#: No lamp within this of a walk that meets this one, along it.
JUNCTION_MARGIN = 40.0
#: How far a lamp may slide along its walk when its spot is taken, and how
#: far a pair slides together; past that each side finds its own spot (the
#: row's north side stands between the tombs' doorsteps).
LAMP_SHIFTS = tuple(s for k in range(8) for s in ((20.0 * k, -20.0 * k) if k else (0.0,)))
LAMP_PAIR_SHIFT = 60.0


def rect_gap(a, b) -> float:
    """The distance between two plan rectangles ``(x0, y0, x1, y1)`` (0 when
    they touch or overlap)."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _spans(lo: float, hi: float, cuts) -> list[tuple[float, float]]:
    """[lo, hi] with every (c0, c1) in ``cuts`` taken out."""
    spans = [(lo, hi)]
    for c0, c1 in cuts:
        spans = [piece for s0, s1 in spans
                 for piece in ((s0, min(s1, c0)), (max(s0, c1), s1)) if piece[1] - piece[0] > 1.0]
    return spans


def _path_lamps(d: Dresser, rooms) -> dict[str, list[tuple[float, float, float]]]:
    """Lamp posts in pairs, one either side of each walk
    (``cemetery.PATHS``), :data:`LAMP_SETBACK` out from its edge and spaced
    evenly (about :data:`LAMP_SPACING`) along the stretches between the
    junctions.  A pair whose spot is taken (a door's keep-out, a set piece)
    slides along the walk, together up to :data:`LAMP_PAIR_SHIFT` and then
    each side on its own (:data:`LAMP_SHIFTS`); a lamp that finds no spot,
    or would slide within half a spacing of another, is left out.  Returns
    walk key -> [(side, x, y)] for each lamp, side -1 or +1 across the walk."""
    from .cemetery import PATHS, path_boxes

    boxes = path_boxes()
    laid: dict[str, list[tuple[float, float, float]]] = {}
    for key, room_key, (ax, ay), (bx, by), hw in PATHS:
        along_x = ay == by
        centre = ay if along_x else ax
        lo, hi = (min(ax, bx), max(ax, bx)) if along_x else (min(ay, by), max(ay, by))
        if hi - lo < MIN_LAMP_WALK:
            laid[key] = []  # a short link through a door or round a corner
            continue
        own = boxes[key][1:]
        cuts = []
        for other, (_room, *box) in boxes.items():
            if other != key and rect_gap(own, box) <= JUNCTION_GAP:
                a0, a1 = (box[0], box[2]) if along_x else (box[1], box[3])
                cuts.append((a0 - JUNCTION_MARGIN, a1 + JUNCTION_MARGIN))
        inside = rooms[room_key].interior
        off = hw + LAMP_SETBACK
        laid[key] = []
        pairs = 0
        placed: list[tuple[float, float]] = []
        for s0, s1 in _spans(lo, hi, cuts):
            n = max(1, round((s1 - s0) / LAMP_SPACING))
            step = (s1 - s0) / n
            for i in range(n):
                t = s0 + (i + 0.5) * step

                def spot(side: float, shift: float) -> tuple[float, float]:
                    return ((t + shift, centre + side * off) if along_x
                            else (centre + side * off, t + shift))

                def ok(x: float, y: float) -> bool:
                    return (inside.mins.x + 24 <= x <= inside.maxs.x - 24
                            and inside.mins.y + 24 <= y <= inside.maxs.y - 24
                            and d.free(x, y, 10.0, 10.0))

                pair = next((s for s in LAMP_SHIFTS if abs(s) <= LAMP_PAIR_SHIFT
                             and ok(*spot(-1.0, s)) and ok(*spot(1.0, s))), None)
                for side, tag in ((-1.0, "a"), (1.0, "b")):
                    shift = pair if pair is not None else next(
                        (s for s in LAMP_SHIFTS if ok(*spot(side, s))), None)
                    if shift is None:
                        continue
                    x, y = spot(side, shift)
                    if any(math.hypot(x - px, y - py) < LAMP_SPACING / 2
                           for px, py in placed):
                        continue  # slid into its neighbour's gap: one lamp there
                    placed.append((x, y))
                    _lantern(d, room_key, x, y, ident=f"path_lamp_{key}_{pairs}{tag}",
                             zone=room_key)
                    laid[key].append((side, x, y))
                pairs += 1
    return laid


def _walk(key: str):
    """(room, along_x, centre, half_width) of one walk in ``cemetery.PATHS``."""
    from .cemetery import PATHS

    for k, room_key, (ax, ay), (_bx, by), hw in PATHS:
        if k == key:
            return room_key, ay == by, (ay if ay == by else ax), hw
    raise KeyError(key)


#: The walkside furniture between the lamps: a stone bench facing the walk
#: (:func:`kit.stone_bench`; the one bench model, ``p7_bench_modern_01``, is
#: 80 long and fits no terrain cell of these grounds, Z44) and a box hedge
#: either side of it, on every other gap, the sides taking turns.
HEDGE = "p7_foliage_hedge_box_48_48_36"
#: Shrubs among the graves.
BUSHES = ("p7_foliage_tree_acacia_bush", HEDGE, "p7_foliage_grass_tall_cluster_med")


def _walkside(d: Dresser, lamps) -> int:
    """A bench halfway between each other pair of neighbouring lamps on one
    side of a walk (:func:`_path_lamps`), set back so its front is a step off
    the walk's edge, with a box hedge either side of it.  Laid right after
    the lamps, before the areas, so the walks read as kept.  Returns benches
    laid."""
    benches = 0
    for key, row in lamps.items():
        if not row:
            continue
        room_key, along_x, centre, hw = _walk(key)
        for k, side in enumerate((-1.0, 1.0)):
            ts = sorted((x if along_x else y) for s, x, y in row if s == side)
            for n, (t0, t1) in enumerate(zip(ts, ts[1:])):
                if (n + k) % 2 or t1 - t0 < 200.0:
                    continue
                t = (t0 + t1) / 2.0
                off = centre + side * (hw + PATH_MARGIN + 16.0)
                x, y = (t, off) if along_x else (off, t)
                # the seat looks at the walk, its long side along it
                if along_x:
                    facing, hx, hy = (Facing.NORTH if side < 0 else Facing.SOUTH), 32.0, 9.0
                else:
                    facing, hx, hy = (Facing.EAST if side < 0 else Facing.WEST), 9.0, 32.0
                if not d.free(x, y, hx, hy):
                    continue
                legs = [(x - 25.0, y) if along_x else (x, y - 25.0),
                        (x + 25.0, y) if along_x else (x, y + 25.0)]
                grounds = tuple(d.low(lx - 7, ly - 7, lx + 7, ly + 7) for lx, ly in legs)
                kit.stone_bench(d.bp, x, y, grounds, facing=facing,
                                ident=f"bench_{key}_{n}{'ab'[k]}")
                d.claim(x, y, 34.0)
                benches += 1
                for dt in (-74.0, 74.0):
                    hoff = centre + side * (hw + PATH_MARGIN + 34.0)
                    hx, hy = (t + dt, hoff) if along_x else (hoff, t + dt)
                    d.prop(room_key, "walkside", HEDGE, hx, hy, 0.0 if along_x else 90.0,
                           snap=True)
    return benches


def _shrubs(d: Dresser, area: str, inside, count: int, *, inset: float = 60.0) -> int:
    """``count`` shrubs (:data:`BUSHES`) inside ``inside``, each a little
    under full size and moved into one terrain cell (the acacia is 82
    across, the cells 81-83), in clumps of two to four against the walls,
    graves, kerbs and monuments (bushes grow next to each other), turned
    a quarter at a time."""
    rect = (inside.mins.x + inset, inside.mins.y + inset, inside.maxs.x - inset, inside.maxs.y - inset)
    palette = tuple((m, (0.75, 0.9), 1) for m in BUSHES)
    tiers = (Tier(palette, (1, 1), (0.0, 8.0)), Tier(palette, (1, 3), (70.0, 110.0)))

    def place(model, x, y, yaw, scale):
        return d.prop(area, "bushes", model, x, y, 90.0 * round(yaw / 90.0) % 360.0,
                      scale=scale, snap=True)

    return len(mixed_clumps(d.rng, rect, tiers, count, place=place,
                            edges=shelter_edges(d, rect), edge_offset=40.0, parent_gap=220.0))


#: Fallen leaves along the walks' verges.
LEAVES = ("p7_3arc_park_leaves_grp_2", "p7_3arc_park_leaves_corner_1",
          "p7_3arc_park_leaves_corner_1", "p7_foliage_weed_cluster_med")


def _verges(d: Dresser, rooms, *, every: float = 50.0) -> int:
    """Fallen leaves and weeds on the verges either side of each walk (off
    its dirt, inside the lamp line and out to 90 past the edge), about one
    per ``every`` units of walk a side.  Laid last, into what is left."""
    from .cemetery import PATHS

    laid = 0
    for key, room_key, (ax, ay), (bx, by), hw in PATHS:
        along_x = ay == by
        lo, hi = (min(ax, bx), max(ax, bx)) if along_x else (min(ay, by), max(ay, by))
        centre = ay if along_x else ax
        inside = rooms[room_key].interior
        for side in (-1.0, 1.0):
            want = int((hi - lo) / every)
            got = 0
            for _ in range(want * 12):
                if got >= want:
                    break
                t = d.rng.uniform(lo, hi)
                off = centre + side * (hw + d.rng.uniform(PATH_MARGIN + 14.0, 90.0))
                x, y = (t, off) if along_x else (off, t)
                if not (inside.mins.x + 30 < x < inside.maxs.x - 30
                        and inside.mins.y + 30 < y < inside.maxs.y - 30):
                    continue
                if d.prop(room_key, "verge", d.rng.choice(LEAVES), x, y,
                          d.rng.uniform(0.0, 360.0)):
                    got += 1
            laid += got
    return laid


def density_cap(floor_area: float) -> int:
    """The most dressing models one area of the cemetery may carry: 300 for
    a small room, and past that 1,500 per million square units of floor
    (filled toward the stock maps' 1,148 per million), so a runaway loop still
    trips the test."""
    return max(300, int(1500.0 * floor_area / 1_000_000.0))


# ---------------------------------------------------------------------------
# Grass
# ---------------------------------------------------------------------------
#: The grass and weed clumps (non-solid), with how often each is drawn and
#: the scale range it is drawn at.  The tall single blade is 99 high at full
#: size, so it is drawn smaller; the large weed cluster is left out (744
#: triangles for a 17-unit weed, ``props.PALETTE``).
GRASS = (("p7_foliage_grass_tall_cluster_sml", 6, (0.7, 1.3)),
         ("p7_foliage_grass_tall_single_sml", 4, (0.7, 1.3)),
         ("p7_foliage_weed_cluster_med", 3, (0.8, 1.3)),
         ("p7_foliage_weed_cluster_sml_a", 2, (0.8, 1.3)),
         ("p7_foliage_weed_cluster_sml_b", 1, (0.8, 1.3)),
         ("p7_foliage_grass_tall_single_lrg", 1, (0.6, 0.9)))
#: The outdoor grounds that get grass.
GRASS_AREAS = ("gate", "hills", "row")
#: No clump within this of a place a player stands to read or use something.
GRASS_CLEAR = 40.0
#: The grass's own layers, per million square units of floor: a thin even
#: sprinkle, and clusters of 3-6 clumps; along the walls one clump per
#: GRASS_WALL_STEP; GRASS_PER_GRAVE against each grave mound, two against
#: each fence panel.  Tried spots that land on something are dropped, so
#: about half of these are laid.
GRASS_EVEN = 450.0
#: The chance a wall's run of grass breaks for a bare stretch after a clump.
GRASS_WALL_GAP = 0.18
#: Clusters carry most of the grass, not a thicker even sprinkle, so the
#: grass reads as clumps with bare ground between.
GRASS_CLUSTERS = 340.0
GRASS_WALL_STEP = 22.0
GRASS_PER_GRAVE = 6
#: Models low enough for grass to grow over (fallen leaves, weeds, flowers).
GRASS_OVER = 14.0


class _Obstacles:
    """Plan rectangles grass keeps out of, bucketed on a 128 grid so a few
    thousand clumps test only their neighbours."""

    CELL = 128.0

    def __init__(self) -> None:
        self.grid: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}

    def add(self, x0: float, y0: float, x1: float, y1: float) -> None:
        c = self.CELL
        for i in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for j in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                self.grid.setdefault((i, j), []).append((x0, y0, x1, y1))

    def hit(self, x: float, y: float, hx: float, hy: float) -> bool:
        c = self.CELL
        seen = set()
        for i in range(math.floor((x - hx) / c), math.floor((x + hx) / c) + 1):
            for j in range(math.floor((y - hy) / c), math.floor((y + hy) / c) + 1):
                for r in self.grid.get((i, j), ()):
                    if r in seen:
                        continue
                    seen.add(r)
                    if x + hx > r[0] and x - hx < r[2] and y + hy > r[1] and y - hy < r[3]:
                        return True
        return False


def clear_grass_from_interactives(bp) -> int:
    """Take the grass tufts out of every interactive's stand; returns how many.

    The grass is laid before the recipe's last interactives go in (the
    GobbleGum machines beside the boxes, script.gobblegum), and
    the lane rule (zmforge.blueprint.lanes) leaves low walk-through clutter
    where it is, so eight tufts ended up in the first machine's stand.  The
    same test the grass placer applies (``Blueprint.interactive_blocks``),
    asked again once everything is in.
    """
    from ..blueprint.elements import PropScatter

    gone = 0
    for scatter in bp.elements(PropScatter):
        if not scatter.id.startswith("grass_"):
            continue
        kept = []
        for p in scatter.props:
            hx, hy = _half(p.model, p.yaw, p.scale)
            if bp.interactive_blocks(p.origin, hx, hy):
                gone += 1
            else:
                kept.append(p)
        if gone:
            scatter.props = kept
    return gone


def _grass(d: Dresser, rooms, features) -> dict[str, int]:
    """Grass and weed clumps over the outdoor grounds, laid last and kept in
    their own prop groups (``grass_<area>``, not ``dress_``, so the areas'
    dressing counts stay the set dressing).  Clumps are non-solid, of varied
    model, size and turn (:data:`GRASS`), seated on the lowest ground under
    their footprint inside one terrain cell, and kept off the walks and
    forecourts, every keep-out (doors, windows, spawns), every brush block
    (stones, mounds, tombs, trees), every other model, every interactive's
    keep-clear and every spot a player reads or uses something.  They lie
    thickest along the walls, the fences and the graves, in clusters over
    the open ground, and thin in between.  Returns clumps per area."""
    from ..blueprint import reach
    from ..blueprint.elements import Massing

    from ..blueprint.model import _solid_bounds
    from .cemetery import FOUNDER_NEEDLE, OPEN_GRAVE, START, path_boxes

    rng = random.Random(f"{d.seed}:grass")
    grounds = {area: d.bp.find(f"{area}_ground").record for area in GRASS_AREAS}
    obstacles = _Obstacles()
    # Not the dresser's keep-outs, which hold whole plots and tombs clear
    # for the set dressing: grass grows up to the stones.  Just the ways:
    # walks, forecourts, doorways, windows, spawns, the start.
    for _room, x0, y0, x1, y1 in path_boxes().values():
        obstacles.add(x0 - PATH_MARGIN, y0 - PATH_MARGIN, x1 + PATH_MARGIN, y1 + PATH_MARGIN)
    for room in rooms.values():
        for box in room.aperture_boxes:
            obstacles.add(box.mins.x - 64, box.mins.y - 64, box.maxs.x + 64, box.maxs.y + 64)
    discs = [(w.barricade_origin.x, w.barricade_origin.y, 96.0) for w in d.bp.elements(Window)]
    discs += [(s.position.x, s.position.y, 64.0) for s in d.bp.elements(Spawn)]
    discs += [(START[0], START[1], 150.0), (OPEN_GRAVE[0], OPEN_GRAVE[1], 110.0),
              (FOUNDER_NEEDLE[0], FOUNDER_NEEDLE[1], 60.0)]
    for x, y, r in discs:
        obstacles.add(x - r, y - r, x + r, y + r)
    # Every brush block standing on the ground (not the trees' limbs or a
    # lamp's cap overhead), and every model.
    for m in d.bp.elements(Massing):
        for solid in m.solids:
            b = _solid_bounds(solid)
            mx, my = (b.mins.x + b.maxs.x) / 2.0, (b.mins.y + b.maxs.y) / 2.0
            under = [z.z for z in (rec.sample(mx, my) for rec in grounds.values()) if z.found]
            if under and b.mins.z > max(under) + 24.0:
                continue
            obstacles.add(b.mins.x - 2.0, b.mins.y - 2.0, b.maxs.x + 2.0, b.maxs.y + 2.0)
    for items in d.pending.values():
        for model, at, yaw, scale, solid in items:
            (bx0, by0, bz0), (bx1, by1, bz1) = collision_box(model)
            if not solid and (bz1 - bz0) * scale <= GRASS_OVER:
                continue
            r = max(abs(bx0), abs(bx1), abs(by0), abs(by1)) * scale
            obstacles.add(at.x - r, at.y - r, at.x + r, at.y + r)
    spots = [p for group in ("epitaphs", "notices") for p in features.get(group, {}).values()]
    spots += list(features.get("wisps", ()))
    spots += [features[k] for k in ("open_grave", "founder", "boss_spawn") if k in features]
    for p in spots:
        obstacles.add(p.x - GRASS_CLEAR, p.y - GRASS_CLEAR, p.x + GRASS_CLEAR, p.y + GRASS_CLEAR)
    zones = d.bp.interactive_keep_clear()
    weights = [w for _m, w, _s in GRASS]

    def clump(area: str, inside, x: float, y: float) -> bool:
        # The room's own ground terrain, sampled directly: grass keeps off
        # every block and walk strip, so the ground here is that terrain
        # (Blueprint.ground_under answers the same, a hundred times slower).
        rec = grounds[area]
        model, _w, (s0, s1) = rng.choices(GRASS, weights)[0]
        scale, yaw = rng.uniform(s0, s1), rng.uniform(0.0, 360.0)
        hx, hy = _half(model, yaw, scale)
        # into one terrain cell (Z44, Dresser._one_cell)
        ax, ay, xc, yc = rec.anchor.x, rec.anchor.y, rec.x_cell, rec.y_cell
        cx0 = ax + math.floor((x - ax) / xc) * xc
        cy0 = ay + math.floor((y - ay) / yc) * yc
        if 2 * hx + 2.0 >= xc or 2 * hy + 2.0 >= yc:
            return False
        x = min(max(x, cx0 + hx + 1.0), cx0 + xc - hx - 1.0)
        y = min(max(y, cy0 + hy + 1.0), cy0 + yc - hy - 1.0)
        if not (inside.mins.x + 8 + hx < x < inside.maxs.x - 8 - hx
                and inside.mins.y + 8 + hy < y < inside.maxs.y - 8 - hy):
            return False
        if obstacles.hit(x, y, hx, hy):
            return False
        pts = [(x + hx * i / 2.0, y + hy * j / 2.0) for i in range(-2, 3) for j in range(-2, 3)]
        zs = [rec.sample(px, py) for px, py in pts]
        if not all(z.found for z in zs):
            return False
        centre = zs[12].z
        if reach.zone_hit(zones, x, y, centre, hx + 8.0, hy + 8.0):
            return False
        box = collision_box(model)
        # as Dresser._seat: the lowest ground under the footprint, never
        # sunk more than a third of the clump's height below its centre
        sink = min(3.0, (box[1][2] - box[0][2]) * scale / 3.0)
        z = max(min(z.z for z in zs), centre - sink) - box[0][2] * scale
        cx, cy = (box[0][0] + box[1][0]) / 2.0 * scale, (box[0][1] + box[1][1]) / 2.0 * scale
        t = math.radians(yaw)
        ox, oy = cx * math.cos(t) - cy * math.sin(t), cx * math.sin(t) + cy * math.cos(t)
        d.pending.setdefault(f"grass_{area}", []).append(
            (model, Point(x - ox, y - oy, z), yaw, scale, False))
        return True

    mounds = [m for m in d.bp.elements(Massing) if m.id.endswith("_mound")]
    laid: dict[str, int] = {}
    for area in GRASS_AREAS:
        inside = rooms[area].interior
        x0, y0, x1, y1 = inside.mins.x, inside.mins.y, inside.maxs.x, inside.maxs.y
        floor = (x1 - x0) * (y1 - y0) / 1_000_000.0
        tries: list[tuple[float, float]] = []
        # along the walls
        for a0, a1, fixed, horizontal in ((x0, x1, y0, True), (x0, x1, y1, True),
                                          (y0, y1, x0, False), (y0, y1, x1, False)):
            inward = 1.0 if fixed in (x0, y0) else -1.0
            t = a0 + rng.uniform(0.0, GRASS_WALL_STEP)
            while t < a1:
                off = fixed + inward * rng.uniform(16.0, 44.0)
                tries.append((t, off) if horizontal else (off, t))
                t += GRASS_WALL_STEP * rng.uniform(0.5, 1.1)
                # patchy, not a hem: a bare stretch now and then
                if rng.random() < GRASS_WALL_GAP:
                    t += rng.uniform(60.0, 180.0)
        # against the graves and the fences
        for m in mounds:
            b = _solid_bounds_of(m)
            if not (x0 <= (b[0] + b[2]) / 2.0 <= x1 and y0 <= (b[1] + b[3]) / 2.0 <= y1):
                continue
            long_x = b[2] - b[0] > b[3] - b[1]
            for k in range(GRASS_PER_GRAVE):
                side, out = (-1.0 if k % 2 else 1.0), rng.uniform(12.0, 26.0)
                if long_x:
                    tries.append((rng.uniform(b[0], b[2]), (b[1] if side < 0 else b[3]) + side * out))
                else:
                    tries.append(((b[0] if side < 0 else b[2]) + side * out, rng.uniform(b[1], b[3])))
        for model, at, yaw, _scale, _solid in d.pending.get(f"dress_{area}_fence", ()):
            across = math.radians(yaw + 90.0)
            for side in (-1.0, 1.0):
                tries.append((at.x + side * 18.0 * math.cos(across) + rng.uniform(-16, 16),
                              at.y + side * 18.0 * math.sin(across)))
        # Tussocks over the open ground, as many tries as the clusters
        # plus the even sprinkle, but grown in clumps drawn toward the feet
        # of things with bare ground between (an even spread reads as
        # artificial).
        n_open = int((GRASS_CLUSTERS * 4.5 + GRASS_EVEN) * floor)
        edges = shelter_edges(d, (x0, y0, x1, y1))
        tries += [(x, y) for x, y, _c in clustered_points(
            rng, (x0, y0, x1, y1), n_open, clumps=max(1, n_open // 30), spread=45.0,
            edges=edges, edge_reach=140.0, edge_offset=30.0, parent_gap=200.0)]
        laid[area] = sum(clump(area, inside, x, y) for x, y in tries)
    return laid


def _solid_bounds_of(massing) -> tuple[float, float, float, float]:
    """The plan box of a one-block brush feature."""
    from ..blueprint.model import _solid_bounds

    b = _solid_bounds(massing.solids[0])
    return b.mins.x, b.mins.y, b.maxs.x, b.maxs.y


#: What lies on the foot of a grave mound, grave by grave in turn: flowers,
#: fallen leaves, an unlit grave lantern, weeds.
GRAVE_GOODS = ("p7_foliage_plant_meskel_1_yellow", "p7_3arc_park_leaves_corner_1",
               "p7_foliage_plant_meskel_1_yellow", "p7_zm_der2_light_hurricane_lamp",
               "p7_foliage_weed_cluster_med", "p7_3arc_park_leaves_corner_1")
FLOWERS = "p7_foliage_plant_meskel_1_yellow"


def _grave_goods(d: Dresser, area: str, x: float, y: float, top: float, *, n: int,
                 across: float) -> None:
    """One thing on the foot of a grave mound whose top is at ``top`` (28
    wide, :func:`kit.grave_mound`): :data:`GRAVE_GOODS` by turn.  ``across``
    is the yaw that turns the flowers' 23-unit side across the mound."""
    model = GRAVE_GOODS[n % len(GRAVE_GOODS)]
    yaw = across if model == FLOWERS else (37.0 * n) % 360.0
    d.prop(area, "offerings", model, x, y, yaw, surface=top, check=False, solid=False)


def _statues(d: Dresser, area: str, spots, *, ident: str, reach: float = 120.0) -> int:
    """Brush grave monuments near each spot, ``(x, y, kind, facing)`` with
    kind ``angel`` or ``urn`` (:func:`kit.angel`, :func:`kit.urn`): the spot
    if it is free, else the first free point on rings round it; one that
    finds none is left out.  Returns how many stand."""
    laid = 0
    for n, (x, y, kind, facing) in enumerate(spots):
        half = 26.0 if kind == "angel" else 16.0
        tries = [(x, y)] + [(x + r * math.cos(a), y + r * math.sin(a))
                            for r in [20.0 * k for k in range(1, int(reach // 20) + 1)]
                            for a in [k * math.pi / 4 for k in range(8)]]
        for tx, ty in tries:
            if d.free(tx, ty, half, half, pad=10.0):
                g = d.low(tx - half, ty - half, tx + half, ty + half)
                if kind == "angel":
                    kit.angel(d.bp, tx, ty, g, facing=facing, ident=f"{ident}{n}")
                else:
                    kit.urn(d.bp, tx, ty, g, ident=f"{ident}{n}")
                d.claim(tx, ty, half + 8.0)
                laid += 1
                break
    return laid


# ---------------------------------------------------------------------------
# Areas
# ---------------------------------------------------------------------------
def _marker(d: Dresser, area: str, x: float, y: float, *, facing: Facing, tag: str,
            rng: random.Random, markers=PLOT_MARKERS) -> str | None:
    """One grave marker at (x, y): a kit model (headstone, stone cross,
    broken stone or wooden cross) when the roll picks one and it seats in one
    terrain cell, else a brush headstone, cross or needle.  Returns the model
    placed, or None for brushwork."""
    roll = rng.random()
    jitter = rng.uniform(-7.0, 7.0)
    # A model stands ``MARKER_SETBACK`` further from its mound than a brush
    # stone, so its footprint (a stone 10 deep either side, a wooden cross 16)
    # clears the mound's
    # end instead of grazing it and reading as standing on it (Z44).
    bx = x - {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0) * MARKER_SETBACK
    by = y - {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0) * MARKER_SETBACK
    for cut, model in markers:
        if roll < cut:
            # the wooden cross is as deep as it is wide: turned, it outgrows its cell
            turn = 0.0 if model == WOODEN_CROSS else jitter
            if d.prop(area, "graves", model, bx, by, (kit_yaw(facing) + turn) % 360.0):
                return model
            roll = markers[-1][0] + (roll / cut) * (1.0 - markers[-1][0])
            break
    # Brushwork: the rest of the roll, split as the plots always were.
    rest = (roll - markers[-1][0]) / (1.0 - markers[-1][0])
    g = d.low(x - 20, y - 20, x + 20, y + 20)
    if rest < 0.55:
        kit.headstone(d.bp, x, y, g, facing=facing, ident=tag,
                      width=rng.choice((24.0, 28.0, 32.0)),
                      height=rng.choice((28.0, 36.0, 44.0, 52.0)),
                      material=rng.choice((kit.STONE, kit.DARK_STONE)))
    elif rest < 0.85:
        kit.cross(d.bp, x, y, g, facing=facing, ident=tag, height=rng.choice((56.0, 64.0, 72.0)))
    else:
        kit.obelisk(d.bp, x, y, g, ident=tag, height=rng.choice((72.0, 96.0)))
    return None


#: A grave's footprint: from GRAVE_REACH behind its marker (an obelisk's
#: base, a model marker set back) to the foot of its mound 80 in front, and
#: GRAVE_WIDTH either side; rows of graves are laid at least GRAVE_PITCH
#: apart along them (the length, the 4 pad and the jitter).
GRAVE_REACH = 24.0
GRAVE_LENGTH = GRAVE_REACH + 80.0
GRAVE_WIDTH = 24.0
GRAVE_PITCH = 116.0
#: How far in from a terrain cell's edges a model marker's centre keeps
#: (the wooden cross is 16 each way), and the most a grave is nudged along
#: its row's axis to get there.
CELL_MARGIN = 17.0
CELL_NUDGE = 10.0


def _into_row_cell(d: Dresser, x: float, y: float, fx: float, fy: float) -> tuple[float, float]:
    """A grave's spot (x, y), moved so its model marker (MARKER_SETBACK
    behind) seats in one terrain cell (Z44, :meth:`Dresser._one_cell`):
    across the row as far as it takes, along the graves by at most
    :data:`CELL_NUDGE`, so the rows keep their spacing.  A marker still over
    a cell edge is built of brush instead (:func:`_marker`)."""
    bx, by = x - fx * MARKER_SETBACK, y - fy * MARKER_SETBACK
    cell = d.terrain_cell(bx, by)
    if cell is None:
        return x, y
    x0, y0, x1, y1 = cell
    nx = min(max(bx, x0 + CELL_MARGIN), x1 - CELL_MARGIN)
    ny = min(max(by, y0 + CELL_MARGIN), y1 - CELL_MARGIN)
    if fy and abs(ny - by) > CELL_NUDGE:
        ny = by
    if fx and abs(nx - bx) > CELL_NUDGE:
        nx = bx
    return x + (nx - bx), y + (ny - by)


def _headstone_plot(d: Dresser, area: str, x0: float, y0: float, x1: float, y1: float, *,
                    dx: float, dy: float, facing: Facing, ident: str,
                    rng: random.Random, markers=PLOT_MARKERS, jack_every: int = 0) -> int:
    """A plot of graves on a grid, each a marker (:func:`_marker`) with its
    mound in front, skipping anything kept clear.  Every ``jack_every``-th
    grave gets a jack-o'-lantern on its mound (0: none)."""
    laid = 0
    fy = 1.0 if facing is Facing.NORTH else -1.0 if facing is Facing.SOUTH else 0.0
    fx = 1.0 if facing is Facing.EAST else -1.0 if facing is Facing.WEST else 0.0
    n = 0
    # One grave runs GRAVE_LENGTH from the back of its stone to the foot of
    # its mound: rows closer than that (plus the pad) would refuse every
    # other grave.
    if fy:
        dy = max(dy, GRAVE_PITCH)
    else:
        dx = max(dx, GRAVE_PITCH)
    y = y0
    while y <= y1:
        x = x0 + (rng.uniform(-8, 8))
        while x <= x1:
            n += 1
            # jittered more across the row than along the graves
            jx = x + rng.uniform(-10, 10) if fy else x + rng.uniform(-3, 3)
            jy = y + rng.uniform(-3, 3) if fy else y + rng.uniform(-8, 8)
            jx, jy = _into_row_cell(d, jx, jy, fx, fy)
            # the stone plus its mound in front: one footprint to test
            mx, my = jx + fx * 44.0, jy + fy * 44.0
            span_x = GRAVE_WIDTH if fy else GRAVE_LENGTH / 2.0
            span_y = GRAVE_LENGTH / 2.0 if fy else GRAVE_WIDTH
            back = GRAVE_LENGTH / 2.0 - GRAVE_REACH
            cx, cy = jx + fx * back, jy + fy * back
            if d.free(cx, cy, span_x, span_y, pad=4.0):
                tag = f"{ident}_{n}"
                _marker(d, area, jx, jy, facing=facing, tag=tag, rng=rng, markers=markers)
                gm = d.low(mx - 16, my - 36, mx + 16, my + 36)
                kit.grave_mound(d.bp, mx, my, gm, facing=facing, ident=f"{tag}_mound")
                # Grave goods on some mounds: a potted plant, or a grave
                # candle, and on the odd one a jack-o'-lantern.
                hx_, hy_ = mx - fx * 8.0, my - fy * 8.0
                if jack_every and n % jack_every == jack_every // 2:
                    d.prop(area, "offerings", JACK if n % 2 else JACK_TALL, hx_, hy_,
                           kit_yaw(facing), surface=gm + 6.0, check=False)
                elif n % 3 == 0:
                    d.prop(area, "offerings", "p7_foliage_plant_meskel_3_noflower", hx_, hy_,
                           rng.uniform(0.0, 360.0), surface=gm + 6.0, check=False, solid=False)
                elif n % 3 == 1:
                    kit.candle(d.bp, hx_, hy_, gm + 6.0, ident=f"{tag}_candle", height=8.0)
                _grave_goods(d, area, mx + fx * 18.0, my + fy * 18.0, gm + 6.0, n=n,
                             across=90.0 if fy else 0.0)
                # The grave's own footprint kept clear, not a disc as wide as
                # it is long: the disc (radius 50) refused the next grave of
                # a row closer than ~118, so the plots were laid at half
                # their grid (they read as empty in game).
                d.keep(cx - span_x, cy - span_y, cx + span_x, cy + span_y)
                laid += 1
            x += dx
        y += dy
    return laid


#: How far a brush dead tree's longest limb (and its twig) reaches from the
#: trunk's centre: ``cemetery_kit._BRANCHES`` longest 72 out from a 10-unit
#: trunk.  Only the brush fallback (``models=()``) uses it.
TREE_REACH = 86.0


#: How far a trunk's downhill edge may stand over the ground once it is
#: raised so its uphill side is no deeper than the support reach.
_TRUNK_GAP = 2.0


def _trees(d: Dresser, spots, *, ident: str, inside, heights=(230.0, 260.0, 290.0),
           models: Sequence[str] | None = None, area: str | None = None,
           leafy_every: int = 3) -> int:
    """A dead tree near each spot: the spot itself if it is free, else the
    first free point on a ring round it (up to 260 units out), always far
    enough in from the walls that no limb reaches into one.  Raises if a
    tree finds no spot.

    Trees are models by default (``dressing.trees.DEAD_TREES``: generated
    round-limbed trees with a bark photo, solid at the trunk), each at a
    random yaw and scaled to its height.  ``models=()`` stands
    the old square brush trees instead (fallback only)."""
    from ..dressing.trees import (ALBIZIA, DEAD_TREES, GNARLED_TREES, as_prop, model_reach, pick,
                                  tree, trunk_clip)

    if models is None:
        models = DEAD_TREES
    area = area or ident.split("_")[0]
    rng = random.Random(f"{d.seed}:{ident}:trees")
    laid = 0
    last = None
    for n, (x, y) in enumerate(spots):
        # Every third tree is a big leafy albizia (a cemetery of only dead
        # trees reads as monotonous), about one leafy to two dead.
        leafy = bool(models) and leafy_every and n % leafy_every == 1
        first = ALBIZIA if leafy else (pick(models, rng, last) if models else None)
        height = heights[n % len(heights)]
        tries = [(x, y)] + [(x + r * math.cos(a), y + r * math.sin(a))
                            for r in (60.0, 110.0, 160.0, 210.0, 260.0)
                            for a in [k * math.pi / 4 for k in range(8)]]

        def tall(m):
            # The big gnarled trees stand 40% over the others (a few heavy
            # old trees among the thinner ones), the
            # leafy albizia 50% (an anchor tree, about half its stock size).
            if m == ALBIZIA:
                return height * 1.5
            return height * 1.4 if m in GNARLED_TREES else height

        def reach_of(m):
            # The scale (and so the crown's reach) does not depend on the spot.
            if m is None:
                return TREE_REACH
            return model_reach(m, tree(m, x, y, 0.0, height=tall(m),
                                       rng=random.Random(f"{ident}{n}"))[3])

        # A corner too tight for the chosen crown takes a narrower one.
        choices = [first] + sorted((m for m in models if m != first), key=reach_of)
        placed = False
        # A trunk sits at the low point under it, but never sunk deeper than
        # the support reach (placement.audit.SUPPORT_REACH) on its uphill
        # side: on a steeper slope it is raised until the uphill side is
        # exactly that deep.  Spots where that leaves the downhill edge more
        # than ``_TRUNK_GAP`` over the ground are tried last.
        for model, strict in [(m, True) for m in choices] + [(m, False) for m in choices]:
            reach = reach_of(model)
            for tx, ty in tries:
                if not (inside.mins.x + reach <= tx <= inside.maxs.x - reach
                        and inside.mins.y + reach <= ty <= inside.maxs.y - reach):
                    continue
                if not d.free(tx, ty, 34, 34):
                    continue
                g = d.low(tx - 14, ty - 14, tx + 14, ty + 14)
                top = d.high(tx - 14, ty - 14, tx + 14, ty + 14)
                if strict and top - g > SUPPORT_REACH + _TRUNK_GAP:
                    continue
                g = max(g, top - SUPPORT_REACH)
                if model is None:
                    kit.dead_tree(d.bp, tx, ty, g, ident=f"{ident}{n}", height=height, turn=n)
                    d.claim(tx, ty, 64.0)
                else:
                    spec = tree(model, tx, ty, g, height=tall(model),
                                rng=random.Random(f"{ident}{n}"))
                    # The dead trees are sunk on purpose (trees.SINK); on a
                    # slope that sink adds to the uphill depth, so lift the
                    # tree until no side of its trunk is deeper than the reach.
                    at = spec[1]
                    deep = d.high(at.x - 14, at.y - 14, at.x + 14, at.y + 14) - at.z
                    if deep > SUPPORT_REACH:
                        spec = (spec[0], replace(at, z=at.z + deep - SUPPORT_REACH), *spec[2:])
                    # Placed now, as a Prop whose body box is its trunk (not
                    # through ``d.pending``, whose readers take the crown's box).
                    d.bp.place_props([as_prop(spec)], id=f"dress_{area}_{ident}{n}")
                    d.counts[area] = d.counts.get(area, 0) + 1
                    if not spec[4]:
                        # A walk-through stock tree: a clip column at its trunk.
                        trunk_clip(d.bp, spec, g, ident=f"{ident}{n}")
                    last = model
                    d.claim(tx, ty, 64.0)
                    _tree_foot(d, area, tx, ty, random.Random(f"{d.seed}:{ident}{n}:foot"))
                laid += 1
                placed = True
                break
            if placed:
                break
        if not placed:
            raise ValueError(f"dead tree {ident}{n} found no spot near ({x:g}, {y:g})")
    return laid


#: What gathers round a dead tree's foot: (model, count range, scale range,
#: distance range from the trunk's centre, clear of its root flare).  Walk-through litter, so a clump, not a
#: ring: each piece is thrown toward one side more than the other.
TREE_FOOT = (
    ("p7_3arc_park_leaves_grp_2", (3, 5), (0.9, 1.4), (59.0, 145.0)),
    ("p7_3arc_park_leaves_corner_1", (1, 3), (1.0, 1.5), (59.0, 115.0)),
    ("p7_foliage_weed_cluster_sml_a", (2, 4), (0.8, 1.3), (59.0, 105.0)),
    ("p7_foliage_grass_tall_cluster_sml", (2, 4), (0.6, 1.0), (65.0, 145.0)),
    ("p7_foliage_weed_cluster_med", (1, 2), (1.5, 2.0), (75.0, 145.0)),
    ("p7_gib_chunk_bone_01", (0, 2), (1.0, 1.5), (65.0, 135.0)),
    ("p7_boulder_rock_05", (0, 2), (1.5, 2.5), (85.0, 165.0)),
    # (No fallen limb: zmf_prop_dead_log is a solid kit prop, and a scaled
    # walk-through copy of it fails Z21, measured.)
)


def _tree_foot(d: Dresser, area: str, x: float, y: float, rng: random.Random) -> int:
    """A clump of leaves, weeds, grass, a bone or a stone
    round a dead tree's foot, heavier on its downwind side."""
    lee = rng.uniform(0.0, 2 * math.pi)
    laid = 0
    for model, (lo, hi), (s0, s1), (r0, r1) in TREE_FOOT:
        for _ in range(rng.randint(lo, hi)):
            for _try in range(6):
                a = lee + rng.gauss(0.0, 0.9)
                r = rng.uniform(r0, r1)
                px, py = x + r * math.cos(a), y + r * math.sin(a)
                yaw, scale = rng.uniform(0.0, 360.0), rng.uniform(s0, s1)
                hx, hy = _half(model, yaw, scale)
                if d.clear(px, py, max(hx, hy)) and d.prop(
                        area, "tree_foot", model, px, py, yaw, scale=scale, check=False,
                        solid=False):
                    laid += 1
                    break
    return laid


def _lantern(d: Dresser, area: str, x: float, y: float, *, colour=FLAME, height: float = 80.0,
             ident: str, zone: str) -> Point:
    g = d.low(x - 8, y - 8, x + 8, y + 8)
    top = kit.lantern_post(d.bp, x, y, g, ident=ident, height=height)
    d.prop(area, "lanterns", "p7_zm_der2_light_hurricane_lamp", x, y, surface=top,
           check=False, solid=False)
    d.bp.place_light(Point(x, y, top + 20.0), colour=colour, radius=384.0, zone_name=zone,
                     shadows=False, id=f"{ident}_light")
    d.claim(x, y, 16.0)
    return Point(x, y, top + 13.0)


def _wisp(d: Dresser, area: str, x: float, y: float, *, ident: str, zone: str) -> Point:
    """A will-o'-wisp lantern, built to be told apart from the path lamps: a
    tall gallows post on a heap of stones, a big lamp out on the end of its
    arm (half as large again as a path lamp) and a wide cold blue light.
    Returns the lamp's centre, the quest's shoot target."""
    g = d.low(x - 20, y - 20, x + 20, y + 20)
    kit._box(d.bp, x - 18, y - 18, g - kit.BURY, x + 18, y + 18, g + 10, kit.DARK_STONE,
             f"{ident}_cairn")
    top = g + 150.0
    kit._box(d.bp, x - 3, y - 3, g + 10, x + 3, y + 3, top, kit.BLACK, f"{ident}_post")
    kit._box(d.bp, x - 3, y - 3, top, x + 34, y + 3, top + 5, kit.BLACK, f"{ident}_arm")
    kit._box(d.bp, x + 19, y - 8, top + 5, x + 35, y + 8, top + 7, kit.IRON, f"{ident}_cap")
    rest = top + 7.0
    d.prop(area, "wisps", "p7_zm_der2_light_hurricane_lamp", x + 27.0, y, surface=rest,
           check=False, solid=False, scale=1.5)
    # The wisp's own light: out when it is shot, lit again if the step's
    # time runs out (an exploder light, not a baked one; Z64, P12).
    place_owned_glow(d.bp, Point(x + 27.0, y, rest + 44.0), owner=f"will-o'-wisp {ident}",
                     off_notify=None, hit=("wisps", int(ident.removeprefix("wisp"))),
                     colour=WISP, radius=512.0, zone_name=zone, id=f"{ident}_light")
    d.claim(x, y, 40.0)
    return Point(x + 27.0, y, rest + 18.0)


def _plaque(d: Dresser, x: float, y: float, z: float, *, facing: Facing, ident: str) -> None:
    """A dark bronze plaque on a wall face at (x, y), centred at height ``z``:
    what a "read the plaque" notice points at."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    if fx:
        kit._box(d.bp, min(x, x + 2 * fx), y - 16, z - 12, max(x, x + 2 * fx), y + 16, z + 12,
                 kit.IRON, ident)
    else:
        kit._box(d.bp, x - 16, min(y, y + 2 * fy), z - 12, x + 16, max(y, y + 2 * fy), z + 12,
                 kit.IRON, ident)


def _candles(d: Dresser, area: str, spots: Sequence[tuple[float, float, float]], *,
             ident: str, zone: str, light_every: int = 3) -> None:
    for n, (x, y, z) in enumerate(spots):
        wick = kit.candle(d.bp, x, y, z, ident=f"{ident}_{n}",
                          height=6.0 + (n % 3) * 3.0)
        if n % light_every == 0:
            d.bp.place_light(Point(x, y, wick + 6.0), colour=FLAME, radius=192.0,
                             zone_name=zone, shadows=False, id=f"{ident}_light_{n}")


#: How far a pile's pieces lie from its centre: close enough that they read
#: as one heap somebody swept up, or that fell there, not as confetti (P15:
#: bricks, pages and bones spread evenly over a floor read as litter).
PILE_REACH = 18.0


def _pile(d: Dresser, area: str, group: str, models: Sequence[str], x: float, y: float,
          n: int, *, rng, surface: float | None = None, reach: float = PILE_REACH,
          solid: bool | None = False) -> int:
    """``n`` pieces heaped within ``reach`` of (x, y), the first at the centre.
    The pile's whole disc must be free; the pieces then lie against and on
    each other as a heap does.  Places nothing and returns 0 otherwise."""
    if not d.free(x, y, reach, reach, z=surface):
        return 0
    for k in range(n):
        a, r = rng.uniform(0.0, 2.0 * math.pi), (0.0 if k == 0 else rng.uniform(5.0, reach))
        d.prop(area, group, rng.choice(list(models)), x + r * math.cos(a), y + r * math.sin(a),
               rng.uniform(0.0, 360.0), surface=surface, check=False, solid=solid)
    d.claim(x, y, reach)
    return n


def _wall_piles(d: Dresser, area: str, group: str, models: Sequence[str], x0: float, y0: float,
                x1: float, y1: float, *, piles: int, per: int, walls: str = "nsew",
                surface: float | None = None, solid: bool | None = False,
                reach: float = PILE_REACH) -> int:
    """``piles`` heaps of ``per`` pieces along the ``walls`` edges of the
    rectangle (``n``/``s``/``e``/``w``): the foot of a wall, where sweepings,
    fallen mortar and blown-in leaves end up."""
    placed = 0
    inset = reach + 4.0
    for _ in range(piles):
        for _ in range(80):
            side = d.rng.choice(walls)
            if side in "ns":
                x, y = d.rng.uniform(x0 + inset, x1 - inset), (y1 - inset if side == "n"
                                                                else y0 + inset)
            else:
                x, y = (x1 - inset if side == "e" else x0 + inset), d.rng.uniform(y0 + inset,
                                                                                  y1 - inset)
            got = _pile(d, area, group, models, x, y, per, rng=d.rng, surface=surface,
                        reach=reach, solid=solid)
            if got:
                placed += got
                break
    return placed


def _graveside(d: Dresser, area: str, palette: Sequence[str], x0: float, y0: float,
               x1: float, y1: float, count: int) -> int:
    """Graveside planting in twos to fours at the graves' edges (mounds
    and plot stones), not over the lawn."""
    edges = shelter_edges(d, (x0, y0, x1, y1), graves_only=True)
    return d.clumped(area, "graveside", palette, x0, y0, x1, y1, count, per=(2, 4), reach=36.0,
                     edges=edges, edge_bias=0.95, parent_gap=60.0)


def _cover(d: Dresser, area: str, inside, count_small: int, count_big: int) -> None:
    x0, y0, x1, y1 = inside.mins.x + 40, inside.mins.y + 40, inside.maxs.x - 40, inside.maxs.y - 40
    # In drifts at the feet of things, not over the lawn.
    d.clumped(area, "cover", GROUND_COVER, x0, y0, x1, y1, count_small, per=(3, 6), reach=50.0)
    d.clumped(area, "brush", BIG_COVER, x0, y0, x1, y1, count_big, per=(2, 3), reach=80.0)


def _dress_gate(d: Dresser, rooms, features) -> None:
    room = rooms["gate"]
    inside = room.interior
    area = "gate"
    # The iron gate you came in by, shut, against the west wall.
    gx = inside.mins.x + 18.0
    kit.fence_gate(d.bp, gx, 0.0, d.ground(gx, 0.0), facing=Facing.EAST, ident="front_gate")
    d.keep(inside.mins.x, -150, inside.mins.x + 60, 150)
    features["notices"]["gate"] = Point(gx + 40.0, 60.0, d.ground(gx + 40, 60) + 48.0)
    # Jack-o'-lanterns either side of the gate, at the foot of its piers.
    for n, y in enumerate((-150.0, 150.0)):
        d.prop(area, "halloween", JACK_TALL if n else JACK, gx + 30.0, y, kit_yaw(Facing.EAST),
               check=False)
    # The gate line: the iron boundary fence along the west wall, either side
    # of the gate (the gate's own keep-out leaves it open there).
    _iron_fence_line(d, area, "gate_line_fence", at=inside.mins.x + FENCE_INSET,
                     a0=inside.mins.y, a1=inside.maxs.y, horizontal=False, tally=d.fences)
    # Laid before the plots so the plots fill in round them.
    # A family plot with an iron fence, on the north mound, and the family in it.
    plot = _fence_box(d, area, -1290.0, 330.0, -1060.0, 490.0, ident="gate_plot_fence",
                      gap="south", tally=d.fences)
    _family_graves(d, area, plot, ident="gate_family", facing=Facing.SOUTH,
                   models=(STONE_ROUND, STONE_CROSS, STONE_ROUND), jack=0)
    # The groundskeeper's barrow, abandoned mid-job beside the stone that
    # says BACK IN 5 MINUTES, with the soil he was bringing (before the
    # plots, which now fill the lawn round it).
    wx, wy = d.piece(area, "work", "p7_wheel_barrow_street_vendor", -1100.0, -215.0, 30.0,
                     reach=128.0)
    for n, (x, y) in enumerate(((wx - 50, wy + 10), (wx - 40, wy - 40), (wx + 10, wy - 55))):
        d.piece(area, "work", "p7_bag_plastic_soil", x, y, 40.0 * n, reach=112.0)
    rng = random.Random(11)
    _headstone_plot(d, area, -1450, 260, -900, 640, dx=120, dy=130, facing=Facing.SOUTH,
                    ident="gate_n", rng=rng, jack_every=5)
    _headstone_plot(d, area, -1450, -620, -900, -260, dx=120, dy=130, facing=Facing.NORTH,
                    ident="gate_s", rng=rng)
    # The readable stones, on the path's edge where the player walks past.
    for key, x, y, facing in GATE_STONES:
        g = d.low(x - 20, y - 20, x + 20, y + 20)
        kit.headstone(d.bp, x, y, g, facing=facing, ident=f"epitaph_{key}", width=36.0,
                      height=48.0)
        front = 30.0 if facing is Facing.NORTH else -30.0
        features["epitaphs"][key] = Point(x, y + front, g + 36.0)
        d.claim(x, y, 30.0)
        # Somebody still visits: a grave candle either side of the stone.
        _candles(d, area, [(x + side, y + front * 0.5, d.low(x + side - 2, y + front * 0.5 - 2,
                                                              x + side + 2, y + front * 0.5 + 2))
                           for side in (-16.0, 16.0)],
                 ident=f"epitaph_{key}_candle", zone="gate", light_every=2)
    _trees(d, ((-1660.0, 560.0), (-940.0, 670.0), (-1600.0, -500.0)), ident="gate_tree",
           inside=inside)
    # "Plots for sale": a sign on a post by the path.
    sx, sy = SALE_SIGN
    g = d.low(sx - 30, sy - 4, sx + 30, sy + 4)
    kit._box(d.bp, sx - 2, sy - 2, g - kit.BURY, sx + 2, sy + 2, g + 56, kit.WOOD, "sale_post")
    kit._box(d.bp, sx - 28, sy - 2, g + 40, sx + 28, sy + 2, g + 70, kit.WOOD, "sale_board")
    features["notices"]["plots_for_sale"] = Point(sx, sy + 24, g + 48)
    d.claim(sx, sy, 32.0)
    for n in range(4):
        d.prop(area, "bones", BONES[n % 3], -1580.0 + 14 * n, 420.0 + 9 * n, 50.0 * n)
    # Graveside plants at the plot stones, then the lawn's weeds and rocks.
    _graveside(d, area, GRAVESIDE, -1450, -620, -900, 640, 10)
    # Sparse grounds read as empty: an angel over the
    # north plots, urns by the walk and the family plot, flowers and shrubs.
    _statues(d, area, ((-900.0, 560.0, "angel", Facing.SOUTH), (-1480.0, 240.0, "urn", None),
                       (-1480.0, -240.0, "urn", None), (-1040.0, 300.0, "urn", None),
                       (-860.0, -680.0, "angel", Facing.NORTH)), ident="gate_monument")
    _shrubs(d, area, inside, 12)
    _graveside(d, area, (FLOWERS,) + GRAVESIDE, inside.mins.x + 40, inside.mins.y + 40,
              inside.maxs.x - 40, inside.maxs.y - 40, 14)
    _cover(d, area, inside, 22, 8)


#: How far an iron fence line stands in from the terrain cell edge it runs
#: along: the panel model (7 deep) then lies inside one cell row (Z44).
FENCE_INSET = 6.0
#: The kit's iron fence model samples a teal cell of the graveyard atlas
#: and draws teal, so every cell gets
#: the black brush fence (:func:`kit.fence_run`) instead.
IRON_FENCE_MODEL = False
#: The most the ground may climb under one fence panel's footprint for the
#: model to stand there; over it the cell gets the brush fence
#: (:func:`kit.fence_run`), which seats every post on its own ground.
#: Seated on the lowest ground, the model's uphill end is then in the grass
#: by at most this, the engine's step height (``placement.audit.SUPPORT_REACH``).
FENCE_RELIEF = 8.0


def _high(d: Dresser, x0: float, y0: float, x1: float, y1: float) -> float:
    """The highest ground under a rectangle (the counterpart of ``d.low``)."""
    pts = [(x0 + (x1 - x0) * i / 4, y0 + (y1 - y0) * j / 4) for i in range(5) for j in range(5)]
    return max(hit.z for hit in (d.bp.ground_under(px, py) for px, py in pts) if hit.found)


def _kept(d: Dresser, x: float, y: float, r: float) -> bool:
    return any(x + r > kx0 and x - r < kx1 and y + r > ky0 and y - r < ky1
               for kx0, ky0, kx1, ky1 in d.keepouts)


def _grid_node(d: Dresser, x: float, y: float) -> tuple[float, float]:
    """The terrain grid corner nearest (x, y)."""
    record = d.bp.find(d.bp.ground_under(x, y).element_id).record
    ax, ay, cx, cy = record.anchor.x, record.anchor.y, record.x_cell, record.y_cell
    return ax + round((x - ax) / cx) * cx, ay + round((y - ay) / cy) * cy


def _iron_fence_line(d: Dresser, area: str, ident: str, *, at: float, a0: float, a1: float,
                     horizontal: bool, skip: Sequence[int] = (), end_piers: bool = True,
                     keep: bool = True, tally: dict | None = None) -> None:
    """An iron fence along one axis-aligned line, ``at`` its fixed coordinate,
    from ``a0`` to ``a1`` (terrain cell edges): one ``zmf_prop_fence_iron``
    panel centred in each cell, a stone pier (:func:`kit.fence_pier`) on each
    cell edge between them.  Cells numbered in ``skip`` are left open, as is
    any whose panel would stand on something kept clear; a cell whose ground
    climbs more than :data:`FENCE_RELIEF` under the panel gets the brush
    fence instead of the model.  With ``keep`` the laid cells are then kept
    clear of everything placed after (a fence box keeps its own, once all
    four sides are down, so its corners do not refuse each other)."""
    yaw = 0.0 if horizontal else 90.0
    hx, hy = _half(FENCE_IRON, yaw)
    tally = {} if tally is None else tally
    edges = [a0]
    while edges[-1] < a1 - 1.0:
        probe = edges[-1] + 1.0
        cell = d.terrain_cell(probe, at) if horizontal else d.terrain_cell(at, probe)
        if cell is None:
            raise ValueError(f"fence {ident} runs off the terrain at {probe:g}")
        edges.append(min(cell[2] if horizontal else cell[3], a1))
    laid: list[bool] = []
    strips: list[tuple[float, float, float, float]] = []
    for n, (c0, c1) in enumerate(zip(edges, edges[1:])):
        mid = (c0 + c1) / 2.0
        px, py = (mid, at) if horizontal else (at, mid)
        if n in skip or c1 - c0 < 2 * max(hx, hy) + 8.0 or not d.free(px, py, hx, hy, pad=2.0):
            laid.append(False)
            continue
        lo = d.low(px - hx, py - hy, px + hx, py + hy)
        if IRON_FENCE_MODEL and _high(d, px - hx, py - hy, px + hx, py + hy) - lo <= FENCE_RELIEF:
            d.prop(area, "fence", FENCE_IRON, px, py, yaw, surface=lo, check=False, solid=True)
            tally["models"] = tally.get("models", 0) + 1
        else:
            ax_, ay_ = (c0 + 8.0, at) if horizontal else (at, c0 + 8.0)
            bx_, by_ = (c1 - 8.0, at) if horizontal else (at, c1 - 8.0)
            kit.fence_run(d.bp, ax_, ay_, bx_, by_, d.ground, ident=f"{ident}_run{n}")
            tally["brush"] = tally.get("brush", 0) + 1
        strips.append((px - hx - 2, py - hy - 2, px + hx + 2, py + hy + 2))
        laid.append(True)
    for n, e in enumerate(edges):
        if not end_piers and n in (0, len(edges) - 1):
            continue
        near = [laid[k] for k in (n - 1, n) if 0 <= k < len(laid)]
        px, py = (e, at) if horizontal else (at, e)
        if not any(near) or _kept(d, px, py, 8.0):
            continue
        kit.fence_pier(d.bp, px, py, d.low(px - 6, py - 6, px + 6, py + 6),
                       ident=f"{ident}_pier{n}")
    if keep:
        for strip in strips:
            d.keep(*strip)


def _fence_box(d: Dresser, area: str, x0, y0, x1, y1, *, ident: str, gap: str,
               tally: dict | None = None) -> tuple[float, float, float, float]:
    """A fenced family plot with a one-cell gap in the ``gap`` side: iron
    panels between stone piers (:func:`_iron_fence_line`) on the terrain
    grid lines nearest the corners asked for.  Returns the plot's corners as
    laid, cell edges."""
    x0, y0 = _grid_node(d, x0, y0)
    x1, y1 = _grid_node(d, x1, y1)
    e = FENCE_INSET
    for side, at, a0, a1, horizontal in (("south", y0 + e, x0, x1, True),
                                         ("north", y1 - e, x0, x1, True),
                                         ("west", x0 + e, y0, y1, False),
                                         ("east", x1 - e, y0, y1, False)):
        cells = max(1, round((a1 - a0) / 80.0))
        skip = (cells // 2,) if side == gap else ()
        _iron_fence_line(d, area, f"{ident}_{side}", at=at, a0=a0, a1=a1,
                         horizontal=horizontal, skip=skip, end_piers=False, keep=False,
                         tally=tally)
    for n, (px, py) in enumerate(((x0 + e, y0 + e), (x1 - e, y0 + e), (x0 + e, y1 - e),
                                  (x1 - e, y1 - e))):
        kit.fence_pier(d.bp, px, py, d.low(px - 6, py - 6, px + 6, py + 6),
                       ident=f"{ident}_corner{n}")
    for kx0, ky0, kx1, ky1 in ((x0, y0, x1, y0 + 2 * e), (x0, y1 - 2 * e, x1, y1),
                               (x0, y0, x0 + 2 * e, y1), (x1 - 2 * e, y0, x1, y1)):
        d.keep(kx0 - 4, ky0 - 4, kx1 + 4, ky1 + 4)
    return x0, y0, x1, y1


def _family_graves(d: Dresser, area: str, plot, *, ident: str, facing: Facing,
                   models: Sequence[str], jack: int | None = None) -> int:
    """The family's graves inside a fenced plot: one marker per cell along
    the side opposite ``facing`` (NORTH or SOUTH), each with its mound and a
    candle, a jack-o'-lantern on grave ``jack``.  A grave whose spot is taken
    is skipped.  Returns how many were laid."""
    x0, y0, x1, y1 = plot
    fy = -1.0 if facing is Facing.SOUTH else 1.0
    cell = d.terrain_cell((x0 + x1) / 2.0, y1 - 1.0 if fy < 0 else y0 + 1.0)
    row_mid = (cell[1] + cell[3]) / 2.0
    cols = []
    x = x0 + 1.0
    while x < x1 - 1.0:
        c = d.terrain_cell(x, row_mid)
        cols.append((c[0] + c[2]) / 2.0)
        x = c[2] + 1.0
    laid = 0
    for n, cx in enumerate(cols):
        model = models[n % len(models)]
        if not d.prop(area, "family", model, cx, row_mid, kit_yaw(facing)):
            continue
        mx, my = cx, row_mid + fy * (44.0 + MARKER_SETBACK)
        gm = d.low(mx - 14, my - 36, mx + 14, my + 36)
        kit.grave_mound(d.bp, mx, my, gm, facing=facing, ident=f"{ident}_{n}_mound")
        if n == jack:
            d.prop(area, "family", JACK, mx, my - fy * 8.0, kit_yaw(facing), surface=gm + 6.0,
                   check=False)
        else:
            kit.candle(d.bp, mx + 8.0, my - fy * 12.0, gm + 6.0, ident=f"{ident}_{n}_candle")
        _grave_goods(d, area, mx, my + fy * 18.0, gm + 6.0, n=n, across=90.0)
        laid += 1
    return laid


def _fits(inside, x: float, y: float, hx: float, hy: float, margin: float = 4.0) -> bool:
    """Whether a footprint centred on (x, y) lies wholly inside a room."""
    return (inside.mins.x + margin <= x - hx and x + hx <= inside.maxs.x - margin
            and inside.mins.y + margin <= y - hy and y + hy <= inside.maxs.y - margin)


def _piece_in(d: Dresser, area: str, group: str, model: str, x: float, y: float,
              yaw: float, inside, *, surface: float, reach: float = 96.0,
              solid: bool | None = None) -> tuple[float, float]:
    """:meth:`Dresser.piece`, but only at spots whose footprint stays inside
    the room (a ring search can otherwise carry a piece through a wall)."""
    hx, hy = _half(model, yaw)
    tries = [(x, y)] + [(x + r * math.cos(a), y + r * math.sin(a))
                        for r in [16.0 * k for k in range(1, int(reach // 16) + 1)]
                        for a in [k * math.pi / 6 for k in range(12)]]
    for tx, ty in tries:
        if _fits(inside, tx, ty, hx, hy) and d.prop(area, group, model, tx, ty, yaw,
                                                     surface=surface, solid=solid):
            return tx, ty
    raise ValueError(f"{model} ({area}/{group}) found no free spot inside the room within "
                     f"{reach:g} of ({x:g}, {y:g})")


def _lay_row(d: Dresser, area: str, group: str, models: Sequence[str], a0: float, a1: float,
             across: float, z: float, *, depth: float, along_y: bool = True) -> int:
    """Set ``models`` out in a line from ``a0`` to ``a1`` on a top at ``z``
    (a shelf board, a table), each turned so it fits the top's ``depth``,
    evenly spaced by their own widths.  Surface clutter: not solid, not
    claimed."""
    turned = []
    for m in models:
        fits = []
        for yaw in (0.0, 90.0):
            hx, hy = _half(m, yaw)
            deep, wide = (hx, hy) if along_y else (hy, hx)
            if deep * 2.0 <= depth - 1.0:
                fits.append((wide, yaw))
        if fits:
            wide, yaw = min(fits)
            turned.append((m, yaw, wide))
    while turned and sum(2.0 * h for _m, _y, h in turned) > a1 - a0:
        turned.pop()
    width = sum(2.0 * h for _m, _y, h in turned)
    gap = max(0.0, (a1 - a0 - width) / (len(turned) + 1))
    a = a0 + gap
    for m, yaw, h in turned:
        c = a + h
        x, y = (across, c) if along_y else (c, across)
        d.prop(area, group, m, x, y, yaw, surface=z, check=False, solid=False)
        a = c + h + gap
    return len(turned)


#: What the groundskeeper keeps on his shed shelves, board by board (lowest
#: first): sacks, seed trays and tins low, jars and bottles higher, the spare
#: lamp and the tall bottles on the top board.
SHED_SHELVES = (
    ("p7_bag_plastic_soil", "p7_box_wood_wine_storage", "p7_pot_metal_boiling_lg",
     "p7_box_wood_01_sm", "p7_cinder_block", "p7_box_wood_wine_storage_tan",
     "p7_pan_metal_sauce", "p7_bag_plastic_soil", "p7_pot_metal_boiling_lg"),
    ("p7_chemistry_kit_large_bottle", "p7_bottle_glass_liquor_03", "p7_decanter_glass_bottle",
     "p7_pan_metal_sauce", "p7_container_bottle_wine_01", "p7_zm_der_magic_box_fake",
     "p7_chemistry_kit_large_bottle", "p7_bottle_glass_wine_01", "p7_pot_metal_boiling_lg",
     "p7_electrical_box_set2_meter05", "p7_bottle_glass_liquor_01"),
    ("p7_book_vintage_02", "p7_book_vintage_03", "p7_book_vintage_05", "p7_box_wood_01_sm",
     "p7_zm_der_light_bulb_glass_cover", "p7_cleaning_paper_folded_wrapped",
     "p7_office_paper_stack_sml", "p7_book_vintage_04", "p7_book_vintage_06",
     "p7_zm_der_light_bulb_small", "p7_box_wood_wine_storage"),
    ("p7_chemistry_kit_measuring_bottle", "p7_zm_der2_light_hurricane_lamp",
     "p7_bottle_glass_wine_01", "p7_box_wood_01_long", "p7_decanter_glass_bottle",
     "p7_zm_der_magic_box_fake", "p7_chemistry_kit_measuring_bottle", "p7_pot_metal_boiling_lg",
     "p7_bottle_glass_liquor_03", "p7_bag_plastic_soil", "p7_container_bottle_wine_01"),
)
#: Tins and jars on the two planks over the workbench.
SHED_BENCH_SHELF = (
    ("p7_pot_metal_boiling_lg", "p7_bottle_glass_liquor_01", "p7_chemistry_kit_large_bottle",
     "p7_pan_metal_lid", "p7_decanter_glass_bottle", "p7_container_bottle_wine_01"),
    ("p7_book_vintage_03", "p7_bottle_glass_wine_01", "p7_book_vintage_01",
     "p7_zm_der_light_bulb_glass_cover", "p7_pot_metal_boiling_lg", "p7_bottle_glass_liquor_03"),
)
#: The floor, in heaps rather than a spread: off-cuts swept against the
#: walls, his screwed-up pages, and weeds blown in under the door.
SHED_OFFCUTS = ("p7_debris_wood_board_splinter_01", "p7_debris_wood_board_splinter_02",
                "p7_debris_wood_board_splinter_03")
SHED_PAPERS = ("p7_debris_trash_paper_02", "p7_debris_trash_paper_03",
               "p7_cleaning_paper_ball_brown")
SHED_WEEDS = ("p7_foliage_weed_cluster_sml_a", "p7_3arc_park_leaves_corner_1")


def _dress_shed(d: Dresser, rooms, features) -> None:
    room = rooms["shed"]
    inside = room.interior
    area = "shed"
    f = room.floor_z
    ceiling = inside.maxs.z
    x_w, x_e, y_s, y_n = inside.mins.x, inside.maxs.x, inside.mins.y, inside.maxs.y
    # The workbench in the south-east corner, the shovel on it (quest step 1).
    bx, by = x_e - 22.0, y_s + 64.0
    if not d.prop(area, "bench", "p7_desk_metal_old_01_body", bx, by, 90.0, surface=f):
        raise ValueError("the shed's workbench has nowhere to stand")
    bench_top = f + 34.0
    # The shovel itself is the quest's item: the quest spawns its model on
    # the bench and takes it away when it is picked up (cemetery_quest).
    features["shovel"] = Point(bx, by, bench_top)
    d.keep_disc(bx - 40.0, by, 44.0)  # room to stand at the bench and take it
    d.prop(area, "bench", "p7_zm_der2_light_hurricane_lamp", bx + 4, by + 28, surface=bench_top,
           check=False, solid=False)
    d.bp.place_light(Point(bx, by + 28, bench_top + 40), colour=FLAME, radius=256.0,
                     zone_name="shed", shadows=False, id="shed_bench_lamp")
    # Along the back and front edges of the bench, clear of the shovel in
    # the middle so it reads on its own: a bottle, a book, a mug, a bulb, a
    # page of notes and a rag.
    for m, x, y, yaw in (("p7_bottle_glass_liquor_01", bx + 12, by - 28, 0.0),
                         ("p7_book_vintage_01", bx + 12, by - 14, 20.0),
                         ("p7_cup_coffee_mug", bx + 13, by + 4, 30.0),
                         ("p7_zm_der_light_bulb_small", bx + 13, by + 13, 0.0),
                         ("p7_office_paper_sheet_01", bx - 12, by - 20, 5.0),
                         ("p7_cleaning_paper_brown", bx - 12, by + 22, 90.0)):
        d.prop(area, "bench", m, x, y, yaw, surface=bench_top, check=False, solid=False)
    # Two planks over the bench for his tins and jars.
    for z, row in zip(kit.plank_shelves(d.bp, by - 34, by + 34, x_e, f, facing=Facing.WEST,
                                        ident="shed_bench_shelf", boards=(72.0, 98.0),
                                        depth=14.0), SHED_BENCH_SHELF):
        _lay_row(d, area, "bench_shelf", row, by - 32, by + 32, x_e - 7.0, z, depth=14.0)
    # His coat on a peg by the bench ("Key in my coat.") and a shirt beside it.
    for n, (m, y) in enumerate((("p7_clothes_hanging_01_suit", by + 56.0),
                                ("p7_clothes_hanging_01_shirt", by + 80.0))):
        out = kit.hook_peg(d.bp, x_e, y, f + 92.0, facing=Facing.WEST, ident=f"shed_coat_peg{n}")
        (_, _, z0), (_, _, z1) = collision_box(m)
        d.prop(area, "coat", m, x_e - out, y, 0.0, surface=f + 91.0 - (z1 - z0), check=False,
               solid=False)
    # Shelving on the west wall, north of the notice board: four planks.
    s0, s1 = y_n - 236.0, y_n - 88.0
    for z, row in zip(kit.plank_shelves(d.bp, s0, s1, x_w, f, facing=Facing.EAST,
                                        ident="shed_shelves"), SHED_SHELVES):
        _lay_row(d, area, "shelves", row, s0 + 2.0, s1 - 2.0, x_w + 10.0, z, depth=20.0)
    d.keep(x_w, s0, x_w + 22, s1 + 4)
    # Seed trays and soil stacked on the floor in front of the shelves.
    for k, (m, z) in enumerate((("p7_box_wood_wine_storage", f), ("p7_box_wood_wine_storage_tan", f + 9.0),
                                ("p7_box_wood_wine_storage", f + 18.0))):
        d.prop(area, "seed_trays", m, x_w + 40.0, s0 + 50.0, 4.0 * k, surface=z,
               check=k == 0, solid=False)
    for k in range(2):
        d.prop(area, "seed_trays", "p7_bag_plastic_soil", x_w + 40.0, s0 + 86.0, 90.0 + 8.0 * k,
               surface=f + 4.0 * k, check=k == 0, solid=False)
    # The generator the notice board talks about, by the power switch, with
    # his toolbox and a rag on its housing and the warning signs over it.
    from .cemetery import POWER

    gx, gy = _piece_in(d, area, "generator", "p7_zm_der_generator_01", POWER[0] + 130.0,
                       POWER[1] - 50.0, 0.0, inside, surface=f, reach=96.0)
    gtop = f + 73.0
    for m, dx, dy, yaw in (("p7_zm_der_magic_box_fake_trunk", -18.0, -6.0, 0.0),
                           ("p7_cleaning_paper_brown", 14.0, 8.0, 30.0),
                           ("p7_bottle_glass_liquor_03", 22.0, -14.0, 0.0)):
        d.prop(area, "generator", m, gx + dx, gy + dy, yaw, surface=gtop, check=False, solid=False)
    for m, dx in (("p7_zm_der_signage_no_smoking", -20.0), ("p7_zm_der2_signage_hazard_01", 20.0)):
        d.mounted(area, "signs", m, gx + dx, y_n - 1.0, f + 108.0, Facing.SOUTH)
    # The tool rack on the east wall, north corner: rake, pick, hoe, broom
    # (the one shovel in the shed is the quest's, on the bench).
    kit.tool_rack(d.bp, y_n - 116.0, y_n - 8.0, x_e, f, facing=Facing.WEST, ident="shed_tools")
    d.keep(x_e - 14, y_n - 120, x_e, y_n)
    # Crates by the rack, one stacked on the other, a lid and a box on top.
    cx, cy = _piece_in(d, area, "stores", "p7_crate_wood_01_short", x_e - 46.0, y_n - 70.0, 0.0,
                       inside, surface=f, reach=48.0)
    d.prop(area, "stores", "p7_crate_wood_01_short_open", cx, cy, 8.0, surface=f + 31.0,
           check=False, solid=False)
    d.prop(area, "stores", "p7_box_wood_01_long", cx, cy, 90.0, surface=f + 61.0, check=False,
           solid=False)
    ox, oy = _piece_in(d, area, "stores", "p7_crate_wood_01_short_open", x_e - 46.0, y_n - 28.0,
                       0.0, inside, surface=f, reach=48.0)
    d.prop(area, "stores", "p7_crate_wood_01_short_open_lid", ox, oy, 90.0, surface=f + 30.0,
           check=False, solid=False)
    d.prop(area, "stores", "p7_bag_plastic_soil", ox, oy, 80.0, surface=f + 32.0, check=False,
           solid=False)
    # Sand for the graves, bagged against the wall under the rack.
    for k, (dy, z) in enumerate(((-22.0, f), (14.0, f), (-12.0, f + 10.0))):
        d.prop(area, "stores", "p7_sandbag_02", x_e - 20.0, y_n - 92.0 + dy, 180.0 * k, surface=z,
               check=False, solid=False)
    # Barrels: one in the north-west corner (lid on, a bottle and a lamp
    # glass on the lid), one in the south-west.
    nx, ny = _piece_in(d, area, "stores", "p7_barrel_metal_55gal_blue", x_w + 24.0, y_n - 24.0,
                       0.0, inside, surface=f, reach=48.0)
    d.prop(area, "stores", "p7_zm_der2_barrel_metal_55gal_lid", nx, ny, surface=f + 35.0,
           check=False, solid=False)
    for m, dx, dy in (("p7_bottle_glass_wine_01", -5.0, 4.0), ("p7_cup_coffee_mug", 5.0, -4.0)):
        d.prop(area, "stores", m, nx + dx, ny + dy, surface=f + 37.0, check=False, solid=False)
    # His wheelbarrow in the south-west corner, soil heaped in it, and the
    # other barrel beside it.
    wx, wy = _piece_in(d, area, "barrow", "p7_wheel_barrow_street_vendor", x_w + 22.0, y_s + 56.0,
                       0.0, inside, surface=f, reach=48.0)
    for k in range(2):
        d.prop(area, "barrow", "p7_bag_plastic_soil", wx, wy - 8.0 + 16.0 * k, 90.0 + 10.0 * k,
               surface=f + 39.0, check=False, solid=False)
    sx_, sy_ = _piece_in(d, area, "stores", "p7_barrel_metal_55gal_blue", x_w + 56.0, y_s + 104.0,
                         0.0, inside, surface=f, reach=48.0)
    d.prop(area, "stores", "p7_zm_der2_barrel_metal_55gal_lid", sx_, sy_, surface=f + 35.0,
           check=False, solid=False)
    for m, dx, dy, yaw in (("p7_cleaning_paper_brown", -3.0, 2.0, 40.0),
                           ("p7_bottle_glass_liquor_01", 6.0, -5.0, 0.0)):
        d.prop(area, "stores", m, sx_ + dx, sy_ + dy, yaw, surface=f + 37.0, check=False,
               solid=False)
    # The groundskeeper's hand cart, parked where he left it, a load on it.
    hx_, hy_ = _piece_in(d, area, "stores", HAND_CART, x_w + 200.0, y_n - 190.0, 0.0, inside,
                         surface=f, reach=240.0)
    for m, dy, yaw in (("p7_box_wood_01_long", -14.0, 0.0), ("p7_bag_plastic_soil", 12.0, 0.0),
                       ("p7_debris_wood_board_splinter_02", 0.0, 80.0)):
        d.prop(area, "stores", m, hx_, hy_ + dy, yaw, surface=f + 24.0, check=False, solid=False)
    # Blank headstones waiting to be cut, a wooden cross for the next one,
    # and the stone chips round them: the mason's corner, mid-room.
    for n, (m, dx, dy) in enumerate(((STONE_ROUND, 0.0, 0.0), (STONE_CROSS, 34.0, 0.0),
                                     (STONE_BROKEN, 16.0, 36.0), (WOODEN_CROSS, -30.0, 40.0))):
        d.prop(area, "stones", m, x_e - 170.0 + dx, y_n - 210.0 + dy, kit_yaw(Facing.WEST))
    for k, m in enumerate(("p7_debris_concrete_rubble_sm_06", "p7_debris_brick_chunk_01",
                           "p7_debris_concrete_rubble_sm_07", "p7_debris_brick_chunk_hlf_01",
                           "p7_debris_brick_chunk_03", "p7_debris_concrete_rubble_sm_00")):
        a = k * 1.05
        d.prop(area, "stones", m, x_e - 150.0 + 46.0 * math.cos(a), y_n - 190.0 + 40.0 * math.sin(a),
               40.0 * k, surface=f, check=False, solid=False)
    # The potting corner in the middle of the floor where he took his
    # breaks: a crate for a table, the lamp and a mug on it (his log goes on
    # it too, cemetery_lore), a seedling, a plain stool pulled up, and the
    # stove with the kettle on ("Kettle on.").
    tx, ty = _piece_in(d, area, "potting", "p7_crate_wood_01_short", x_w + 230.0, y_s + 250.0, 0.0,
                       inside, surface=f, reach=96.0)
    for m, dx, dy, yaw in (("p7_zm_der2_light_hurricane_lamp", 8.0, 8.0, 0.0),
                           ("p7_cup_coffee_mug", 9.0, -9.0, 60.0),
                           ("p7_foliage_plant_meskel_3_noflower", -8.0, 9.0, 0.0),
                           ("p7_office_paper_sheet_09", 3.0, 3.0, 25.0)):
        d.prop(area, "potting", m, tx + dx, ty + dy, yaw, surface=f + 31.0, check=False,
               solid=False)
    kit.stool(d.bp, tx + 40.0, ty, f, ident="shed_stool")
    d.claim(tx + 40.0, ty, 10.0)
    ovx, ovy = tx - 50.0, ty - 20.0
    hob = kit.stove(d.bp, ovx, ovy, f, ident="shed_stove", ceiling=ceiling)
    d.claim(ovx, ovy, 16.0)
    kit.kettle(d.bp, ovx - 5.0, ovy - 5.0, hob, ident="shed_kettle")
    d.prop(area, "potting", "p7_pan_metal_lid", ovx - 5.0, ovy + 7.0, surface=hob, check=False,
           solid=False)
    # Kindling by the stove.
    kx, ky = ovx - 48.0, ovy
    kx, ky = _piece_in(d, area, "kindling", "p7_debris_wood_board_cluster_01", kx, ky, 10.0,
                       inside, surface=f, reach=64.0)
    if True:
        for k, m in enumerate(("p7_debris_wood_board_splinter_01", "p7_debris_wood_board_splinter_03")):
            d.prop(area, "kindling", m, kx - 6.0 + 12.0 * k, ky + 4.0, 70.0 * k, surface=f + 4.0,
                   check=False, solid=False)
    # His desk under the notice board: the day's papers, a ledger, a lamp,
    # a mug and an ink bottle, a stool at it, the Founder's picture over it.
    board_y = y_s + 284.0
    dx_, dy_ = x_w + 20.0, board_y + 1.0
    # The _body model: the whole p7_desk_metal_old_01 draws magenta DELETE
    # (placeholder material; Z13 refuses it).
    if d.prop(area, "desk", "p7_desk_metal_old_01_body", dx_, dy_, 90.0, surface=f):
        top = f + 34.0
        for m, ox_, oy_, yaw in (("p7_book_vintage_open_04", 2.0, -20.0, 95.0),
                                 ("p7_office_paper_sheet_02", -4.0, 2.0, 10.0),
                                 ("p7_office_paper_sheet_08", 6.0, 12.0, 80.0),
                                 ("p7_office_paper_stack_sml", -2.0, 26.0, 0.0),
                                 ("p7_zm_der2_light_hurricane_lamp", -8.0, -30.0, 0.0),
                                 ("p7_cup_coffee_mug", 10.0, -6.0, 0.0),
                                 ("p7_bottle_glass_liquor_03", -10.0, 12.0, 0.0),
                                 ("p7_box_copy_paper_sheet", 10.0, 28.0, 30.0),
                                 ("p7_book_vintage_02", -8.0, -4.0, 75.0)):
            d.prop(area, "desk", m, dx_ + ox_, dy_ + oy_, yaw, surface=top, check=False,
                   solid=False)
        kit.stool(d.bp, dx_ + 40.0, dy_, f, ident="shed_desk_stool")
        d.claim(dx_ + 40.0, dy_, 10.0)
    d.mounted(area, "wall", "p7_clock_metal_wall_01_base", x_w + 3, board_y, f + 112.0,
              Facing.EAST)
    d.mounted(area, "wall", "p7_picture_frame_modern_01", x_w + 2, board_y, f + 150.0,
              Facing.EAST)
    # Staff notices by the door, and two old photographs of the grounds.
    d.mounted(area, "wall", "p7_zm_der_signage_employees_only", x_w + 150.0, y_s + 1.0, f + 104.0,
              Facing.NORTH)
    for n, x in enumerate((x_w + 40.0, x_w + 100.0)):
        d.mounted(area, "wall", "p7_picture_frame_modern_01", x, y_s + 2.0, f + 140.0 + 8.0 * n,
                  Facing.NORTH)
    # The notice board itself, on the west wall over the desk.
    d.mounted(area, "board", "p7_zm_der2_bulletin_board", x_w + 1.0, board_y, f + 64.0,
              Facing.EAST)
    features["notices"]["shed_board"] = Point(x_w + 24, board_y, f + 56.0)
    _wall_piles(d, area, "floor", SHED_OFFCUTS, x_w + 20, y_s + 20, x_e - 20, y_n - 20,
                piles=2, per=6, surface=f)
    _wall_piles(d, area, "floor", SHED_PAPERS, x_w + 20, y_s + 20, x_e - 20, y_n - 20,
                piles=2, per=3, surface=f, walls="w")
    _wall_piles(d, area, "floor", SHED_WEEDS, x_w + 20, y_s + 20, x_e - 20, y_n - 20,
                piles=2, per=2, surface=f, walls="s")


def _dress_hills(d: Dresser, rooms, features) -> None:
    from .cemetery import FOUNDER_NEEDLE, MAUSOLEUMS, OPEN_GRAVE

    room = rooms["hills"]
    inside = room.interior
    area = "hills"
    # The mausoleums on their hilltops, each with its name plate.
    for key, family, x, y, facing, _h in MAUSOLEUMS:
        g = d.low(x - 130, y - 130, x + 130, y + 130)
        info = kit.mausoleum(d.bp, x, y, g, facing=facing, ident=f"mausoleum_{key}")
        features["epitaphs"][key] = Point(info["door_x"], info["door_y"], g + 60.0)
        d.keep(x - 150, y - 150, x + 150, y + 150)
        _lantern(d, area, info["door_x"] + (60 if facing in (Facing.NORTH, Facing.SOUTH) else 0),
                 info["door_y"] + (60 if facing in (Facing.EAST, Facing.WEST) else 0),
                 ident=f"{key}_lantern", zone="hills")
    # The Founder's needle, the tallest thing on the tallest hill.
    fx, fy, _ = FOUNDER_NEEDLE
    g = d.low(fx - 24, fy - 24, fx + 24, fy + 24)
    kit.obelisk(d.bp, fx, fy, g, ident="founder_needle", height=224.0)
    features["founder"] = Point(fx - 12.0, fy, g + 56.0)
    features["epitaphs"]["founder"] = Point(fx - 30.0, fy, g + 40.0)
    d.keep(fx - 70, fy - 70, fx + 70, fy + 70)
    # The Open Grave, dug on its own knoll, with the stone already carved.
    ox, oy, _ = OPEN_GRAVE
    g = d.ground(ox, oy)
    pit = kit.open_grave(d.bp, ox, oy, g, ident="open_grave")
    features["open_grave"] = Point(ox, oy, g)
    features["notices"]["open_grave"] = Point(ox - 120.0, oy - 40.0, g + 30.0)
    # The Gravedigger climbs out beside the grave, on the knoll's flat top,
    # not inside the rim where the dig trigger is.
    features["boss_spawn"] = Point(ox + 72.0, oy - 70.0, d.ground(ox + 72.0, oy - 70.0))
    kit.headstone(d.bp, ox, pit[3] + 40.0, d.low(ox - 20, pit[3] + 30, ox + 20, pit[3] + 50),
                  facing=Facing.SOUTH, ident="epitaph_reserved", width=40.0, height=56.0)
    features["epitaphs"]["reserved"] = Point(ox - 60.0, pit[3] + 40.0, g + 40.0)
    d.keep(ox - 90, oy - 90, ox + 90, oy + 100)
    # (the pit itself: a broken coffin and bones in it)
    kit._box(d.bp, ox - 14, oy - 36, g, ox + 14, oy - 4, g + 10, kit.WOOD, "open_grave_coffin_lid")
    for n in range(5):
        d.prop(area, "grave", BONES[n % 3], ox - 12 + 6 * n, oy + 10 + 5 * n, 40.0 * n,
               surface=g, check=False, solid=False)
    d.prop(area, "grave", "p7_debris_wood_board_splinter_01", ox + 6, oy + 30, 25.0,
           surface=g, check=False, solid=False)
    # Headstone plots on the slopes, off the paths.
    rng = random.Random(23)
    _headstone_plot(d, area, -700, -980, -120, -620, dx=96, dy=110, facing=Facing.NORTH,
                    ident="hills_sw", rng=rng)
    _headstone_plot(d, area, -700, 200, -100, 400, dx=110, dy=120, facing=Facing.SOUTH,
                    ident="hills_nw", rng=rng)
    _headstone_plot(d, area, 330, 180, 1050, 360, dx=110, dy=110, facing=Facing.SOUTH,
                    ident="hills_ne", rng=rng, jack_every=5)
    _headstone_plot(d, area, 150, -960, 1100, -760, dx=96, dy=110, facing=Facing.NORTH,
                    ident="hills_se", rng=rng)
    # Two more plots on the open slopes north-west and east of the hub, so
    # the hills read as a graveyard end to end, not as lawn between plots.
    # The north-west one is old ground, like the far north slope below.
    _headstone_plot(d, area, -700, 520, -160, 1000, dx=96, dy=110, facing=Facing.SOUTH,
                    ident="hills_nw_upper", rng=rng, markers=OLD_MARKERS, jack_every=6)
    _headstone_plot(d, area, 480, 460, 1100, 760, dx=96, dy=110, facing=Facing.SOUTH,
                    ident="hills_e", rng=rng)
    # The far north slope is the old ground: wooden crosses and broken stones.
    _headstone_plot(d, area, 330, 820, 1100, 1000, dx=100, dy=110, facing=Facing.SOUTH,
                    ident="hills_far", rng=rng, markers=OLD_MARKERS, jack_every=4)
    _headstone_plot(d, area, -720, -560, -560, -200, dx=110, dy=110, facing=Facing.EAST,
                    ident="hills_w", rng=rng)
    _headstone_plot(d, area, 150, 560, 330, 1000, dx=110, dy=110, facing=Facing.EAST,
                    ident="hills_n", rng=rng, markers=OLD_MARKERS)
    # Sparse grounds read as empty: the open ground
    # left between the plots gets graves too -- the slope south of the walk
    # between Moore's hill and the Founder's, the strip west of the north
    # walk, the foot of the south slope and the east edge below the knoll.
    for ident, box, facing in (("hills_s_mid", (-170, -660, 400, -290), Facing.NORTH),
                               ("hills_n_mid", (-130, 250, 60, 1000), Facing.EAST),
                               # two columns: a third one pinched the lane to
                               # the south-east plot to 42 wide (N5)
                               ("hills_s_low", (-110, -1010, 20, -720), Facing.NORTH),
                               ("hills_e_low", (960, -730, 1120, -430), Facing.NORTH),
                               ("hills_e_mid", (380, 240, 560, 400), Facing.SOUTH)):
        _headstone_plot(d, area, *box, dx=100, dy=110, facing=facing, ident=ident, rng=rng,
                        jack_every=7 if ident == "hills_s_mid" else 0)
    # The readable stones by the paths.
    for key, x, y, facing in HILLS_STONES:
        g2 = d.low(x - 20, y - 20, x + 20, y + 20)
        kit.headstone(d.bp, x, y, g2, facing=facing, ident=f"epitaph_{key}", width=36.0,
                      height=48.0)
        off = {Facing.NORTH: (0, 30), Facing.SOUTH: (0, -30), Facing.WEST: (-30, 0),
               Facing.EAST: (30, 0)}[facing]
        features["epitaphs"][key] = Point(x + off[0], y + off[1], g2 + 36.0)
        d.claim(x, y, 30.0)
    # Dead trees, the silhouettes in the fog.
    _trees(d, ((-620.0, -200.0), (100.0, 420.0), (1000.0, 620.0), (-150.0, -700.0),
               (850.0, -380.0), (-640.0, 900.0), (380.0, -240.0)), ident="hills_tree", inside=inside)
    # A fenced family plot round the east knoll, the family facing its gap.
    plot = _fence_box(d, area, 940.0, -340.0, 1100.0, -170.0, ident="hills_plot_fence",
                      gap="north", tally=d.fences)
    _family_graves(d, area, plot, ident="hills_family", facing=Facing.NORTH,
                   models=(STONE_CROSS, STONE_BROKEN), jack=1)
    # Jack-o'-lanterns at the chapel door, either side of the opening: the
    # short ones, under the 18-unit step a solid prop by a door may be.
    for box in rooms["chapel"].aperture_boxes:
        if abs((box.mins.y + box.maxs.y) / 2.0) < 1.0:
            for n, y in enumerate((box.mins.y - 52.0, box.maxs.y + 52.0)):
                d.prop(area, "halloween", JACK, box.mins.x - 26.0, y,
                       (kit_yaw(Facing.WEST) + 20.0 * (1 - 2 * n)) % 360.0, check=False)
    # The will-o'-wisp lanterns: the tall cold ones on four hills (quest step 3).
    wisps = []
    for n, (x, y) in enumerate(WISP_SPOTS):
        wisps.append(_wisp(d, area, x, y, ident=f"wisp{n}", zone="hills"))
    features["wisps"] = wisps
    # More dead trees on the open edges, stone angels watching the walks and
    # urns on plinths at the plots' corners, then bushes among the graves.
    _trees(d, ((1090.0, -640.0), (-40.0, 980.0), (1090.0, 980.0)),
           ident="hills_tree_edge", inside=inside, heights=(250.0, 280.0))
    _statues(d, area, ((330.0, 240.0, "angel", Facing.SOUTH), (-160.0, -250.0, "angel", Facing.NORTH),
                       (1080.0, 420.0, "angel", Facing.WEST),
                       (-700.0, 470.0, "urn", None), (-160.0, 470.0, "urn", None),
                       (480.0, 440.0, "urn", None), (1100.0, 440.0, "urn", None),
                       (160.0, -600.0, "urn", None)),
             ident="hills_monument")
    _shrubs(d, area, inside, 18)
    _graveside(d, area, GRAVESIDE + (FLOWERS,), inside.mins.x + 40, inside.mins.y + 40,
              inside.maxs.x - 40, inside.maxs.y - 40, 16)
    # Less lawn litter than the other grounds: the hills' count goes on
    # readable graves rather than 3-12u cover.
    _cover(d, area, inside, 12, 8)


def _dress_row(d: Dresser, rooms, features) -> None:
    from .cemetery import ROW_TOMBS

    room = rooms["row"]
    inside = room.interior
    area = "row"
    for key, x, y, facing in ROW_TOMBS:
        big = key == "graves"
        g = d.low(x - 120, y - 140, x + 120, y + 140)
        info = kit.mausoleum(d.bp, x, y, g, facing=facing, ident=f"tomb_{key}",
                             width=176.0 if big else 128.0, depth=224.0 if big else 160.0,
                             height=168.0 if big else 128.0)
        d.keep(x - 110, y - 140, x + 110, y + 140)
        # Every tomb's plate is read at its door (three
        # blank plates next to a named one).
        features["epitaphs"]["graves" if big else f"tomb_{key}"] = Point(
            info["door_x"], info["door_y"], g + 60.0)
        # Somebody still visits: grave candles either side of the tomb door
        # and a potted plant at each front corner.
        dx_, dy_ = info["door_x"], info["door_y"] - 20.0
        gd = d.low(dx_ - 50, dy_ - 6, dx_ + 50, dy_ + 6)
        _candles(d, area, [(dx_ + side, dy_, gd) for side in (-44.0, 44.0)],
                 ident=f"tomb_{key}_candle", zone="row", light_every=2)
        for side in (-1.0, 1.0):
            d.prop(area, "offerings", "p7_foliage_plant_meskel_3_noflower",
                   x + side * (80.0 if big else 64.0), dy_ - 4.0, surface=gd, check=False,
                   solid=False)
    # Crosses and stones between the tombs, in two lines; a marker whose spot
    # is taken moves along its line, and one that cannot stops the build.
    # The front line stands back off the row walk (y 1186-1314).
    for n, x in enumerate((-580.0, -180.0, 220.0, 620.0, 1020.0)):
        for k, y in enumerate((1400.0, 1620.0)):
            for mx, my in [(x + ox, y + oy) for oy in (0.0, -50.0, 50.0, -90.0)
                           for ox in (0.0, -40.0, 40.0, -70.0, 70.0)]:
                if d.free(mx, my, 20, 20):
                    break
            else:
                raise ValueError(f"row marker {n}_{k} found no spot near ({x:g}, {y:g})")
            y = my
            g = d.low(mx - 16, y - 16, mx + 16, y + 16)
            # The kit's stone cross or round stone where it seats in one
            # terrain cell, else the brush cross or tablet.
            model = STONE_CROSS if (n + k) % 2 else STONE_ROUND
            if d.prop(area, "markers", model, mx, y, kit_yaw(Facing.SOUTH)):
                pass
            elif (n + k) % 2:
                kit.cross(d.bp, mx, y, g, facing=Facing.SOUTH, ident=f"row_cross{n}_{k}")
            else:
                kit.headstone(d.bp, mx, y, g, facing=Facing.SOUTH, ident=f"row_stone{n}_{k}")
            d.claim(mx, y, 24.0)
            d.prop(area, "offerings", GRAVESIDE[(n + k) % 2], mx + 18.0, y - 26.0,
                   surface=None)
    _trees(d, ((-700.0, 1640.0), (-20.0, 1650.0)), ident="row_tree", inside=inside)
    # Sparse grounds read as empty: a line of graves
    # along the back wall behind the tombs, facing the row, and urns and
    # shrubs between the tombs.
    _headstone_plot(d, area, -740, 1735, 1140, 1735, dx=96, dy=110, facing=Facing.SOUTH,
                    ident="row_back", rng=random.Random(31), jack_every=6)
    _statues(d, area, ((-640.0, 1400.0, "urn", None), (-180.0, 1500.0, "urn", None),
                       (220.0, 1500.0, "urn", None), (620.0, 1500.0, "urn", None)),
             ident="row_urn", reach=80.0)
    # (One more shrub and four more graveside pieces since the box's second
    # spot, cemetery.BOX_MOVES, took a stretch of the back row.)
    _shrubs(d, area, inside, 14, inset=50.0)
    _graveside(d, area, GRAVESIDE + (FLOWERS,), inside.mins.x + 40, inside.mins.y + 40,
              inside.maxs.x - 40, inside.maxs.y - 40, 24)
    _cover(d, area, inside, 36, 8)


#: What the Hollows left in their niches, one recipe per niche in turn:
#: ``(brush piece, props)``, the brush piece a skull, an urn, a candle stub
#: or a bundle of shins, the props bones, dried flowers, a prayer book, a
#: vase, crumbled mortar.
VAULT_NICHES = (
    ("skull", ("p7_gib_chunk_bone_01", "p7_foliage_plant_meskel_3_noflower", "p7_gib_chunk_bone_03")),
    ("urn", ("p7_foliage_weed_cluster_sml_a", "p7_book_vintage_02", "p7_debris_brick_chunk_hlf_01")),
    ("candle", ("p7_decanter_glass_bottle", "p7_foliage_weed_cluster_med", "p7_gib_chunk_bone_01")),
    ("shins", ("p7_debris_brick_chunk_hlf_02", "p7_foliage_weed_cluster_sml_b", "p7_book_vintage_05")),
    ("urn", ("p7_gib_chunk_bone_03", "p7_container_bottle_wine_01", "p7_foliage_weed_cluster_med")),
    ("skull", ("p7_book_vintage_01", "p7_foliage_plant_meskel_3_noflower", "p7_debris_brick_chunk_02")),
)
#: On each coffin lid: dried flowers, a prayer book or a vase, a sprig.
VAULT_COFFIN_TOPS = (
    ("p7_foliage_plant_meskel_3_noflower", "p7_book_vintage_03", "p7_foliage_weed_cluster_sml_a",
     "p7_3arc_park_leaves_corner_1"),
    ("p7_decanter_glass_bottle", "p7_foliage_weed_cluster_lrg", "p7_book_vintage_open_04",
     "p7_foliage_plant_meskel_3_noflower"),
    ("p7_foliage_plant_meskel_3_noflower", "p7_book_vintage_06", "p7_container_bottle_wine_01",
     "p7_foliage_weed_cluster_sml_b"),
)
#: Swept into the corners: bone chips, crumbled mortar, dry petals.
VAULT_DUST = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03",
              "p7_debris_brick_chunk_hlf_01", "p7_debris_brick_chunk_03",
              "p7_debris_brick_chunk_04", "p7_foliage_weed_cluster_sml_a",
              "p7_3arc_park_leaves_corner_1", "p7_foliage_weed_cluster_med")
#: Where a niche's three props sit, ``(along the wall, out from the niche
#: centre)``: one beside the brush piece, two stacked front and back in
#: the middle, all clear of the piece at along -10.
NICHE_SPOTS = ((10.0, 0.0), (1.0, -5.0), (1.0, 5.0))


def _vault_niches(d: Dresser, area: str, tops, facing: Facing, ident: str, start: int) -> None:
    """Dress each niche top ``(x, y, z)`` with the next :data:`VAULT_NICHES`
    recipe: its brush piece at one end, its props beside it, each turned
    thin side along the wall so it stays on the shelf and off the piece."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    ax, ay = (0.0, 1.0) if fx else (1.0, 0.0)   # along the wall
    for n, (x, y, z) in enumerate(tops):
        piece, models = VAULT_NICHES[(start + n) % len(VAULT_NICHES)]
        bx, by = x - fx * 3.0 - ax * 10.0, y - fy * 3.0 - ay * 10.0
        tag = f"{ident}_{n}"
        if piece == "skull":
            kit.skull(d.bp, bx, by, z, facing=facing, ident=f"{tag}_skull")
        elif piece == "urn":
            kit.small_urn(d.bp, bx, by, z, ident=f"{tag}_urn")
        elif piece == "candle":
            kit.candle(d.bp, bx, by, z, ident=f"{tag}_candle", height=4.0)
        else:
            kit.long_bones(d.bp, bx, by, z, facing=facing, ident=f"{tag}_shins", count=2,
                           length=10.0)
        for m, (s, o) in zip(models, NICHE_SPOTS):
            # the yaw that puts the model's thinner side along the wall
            yaw = min((0.0, 90.0), key=lambda w: _half(m, w)[1 if fx else 0])
            d.prop(area, "niches", m, x + ax * s + fx * o, y + ay * s + fy * o, yaw,
                   surface=z, check=False, solid=False)


def _dress_vault(d: Dresser, rooms, features) -> None:
    room = rooms["vault"]
    inside = room.interior
    area = "vault"
    f = room.floor_z
    x_wall = inside.maxs.x
    x_w, y_s, y_n = inside.mins.x, inside.mins.y, inside.maxs.y
    # Coffins on stone shelves, three high, along the east wall, with room
    # over each coffin for what the family left on it.  One slot, the top
    # right, is bare: the Founder took his coffin up to the chapel for his
    # vigil (the plaque says so) -- a candle stub and dust where it lay.
    tops = []
    for level in range(3):
        z = f + 8 + level * 56
        kit._box(d.bp, x_wall - 60, y_s + 110, z, x_wall, y_n - 60, z + 6,
                 kit.DARK_STONE, f"vault_shelf{level}")
        for k, y in enumerate((y_s + 150, y_s + 250)):
            if (level, k) == (2, 1):
                kit.candle(d.bp, x_wall - 44, y + 26, z + 6, ident="vault_bare_candle",
                           height=3.0)
                for m, dx, dy in (("p7_debris_brick_chunk_hlf_01", -8.0, -12.0),
                                  ("p7_debris_brick_chunk_04", 6.0, 14.0)):
                    d.prop(area, "bare_shelf", m, x_wall - 30 + dx, y + dy, 20.0, surface=z + 6,
                           check=False, solid=False)
                continue
            kit._box(d.bp, x_wall - 52, y - 40, z + 6, x_wall - 8, y + 40, z + 30, kit.WOOD,
                     f"vault_coffin{level}_{k}")
            # an iron name plate on the coffin's foot, facing the room
            kit._box(d.bp, x_wall - 53, y - 8, z + 14, x_wall - 52, y + 8, z + 22, kit.IRON,
                     f"vault_coffin{level}_{k}_plate")
            tops.append((x_wall - 30, y, z + 30))
        # the shelf's free end, past the second coffin: a bone and a sprig
        for m, dx in (("p7_gib_chunk_bone_03", -6.0), ("p7_foliage_weed_cluster_sml_b", 8.0)):
            d.prop(area, "shelf_ends", m, x_wall - 30 + dx, y_n - 68, 60.0 * level, surface=z + 6,
                   check=False, solid=False)
    kit._box(d.bp, x_wall - 60, y_s + 104, f, x_wall, y_s + 110,
             f + 176, kit.BRICK, "vault_shelf_end")
    d.keep(x_wall - 64, y_s + 100, x_wall, y_n - 56)
    _candles(d, area, [(x, y + 20, z) for x, y, z in tops[::2]], ident="vault_candle",
             zone="vault", light_every=2)
    for n, (x, y, z) in enumerate(tops):
        row = VAULT_COFFIN_TOPS[n % len(VAULT_COFFIN_TOPS)]
        for k, (m, dx, dy) in enumerate(zip(row, (-10.0, 8.0, -6.0, 10.0),
                                            (-26.0, -10.0, 4.0, 28.0))):
            d.prop(area, "offerings", m, x + dx, y + dy, 30.0 * (n + k), surface=z, check=False,
                   solid=False)
    # The family's plaque on the west wall, beside the door in: what the
    # notice reads.
    py = y_n - 94.0
    _plaque(d, x_w, py, f + 60.0, facing=Facing.EAST, ident="vault_plaque")
    features["notices"]["vault"] = Point(x_w + 24.0, py, f + 56.0)
    # Burial niches, four rows high, in every stretch of wall the doors,
    # the window, the perk and the coffin shelves leave: urns, skulls,
    # shins, candle stubs, dried flowers and prayer books in them.
    runs = (
        (y_s + 4.0, y_s + 80.0, x_w, Facing.EAST, 38.0),     # west wall, south of the door
        (y_n - 72.0, y_n - 4.0, x_w, Facing.EAST, 34.0),     # west wall, north of the plaque
        (x_w + 24.0, x_w + 104.0, y_s, Facing.NORTH, 40.0),  # south wall, west of the perk
        (x_wall - 114.0, x_wall - 64.0, y_s, Facing.NORTH, 48.0),  # south wall, east of it
        (x_w + 24.0, x_w + 64.0, y_n, Facing.SOUTH, 40.0),   # north wall, west of the window
        (x_wall - 54.0, x_wall - 4.0, y_n, Facing.SOUTH, 48.0),   # north wall, east corner
    )
    start = 0
    for n, (a0, a1, wall, facing, pitch) in enumerate(runs):
        tops_n = kit.niche_run(d.bp, a0, a1, wall, f, facing=facing, ident=f"vault_niche{n}",
                               rows=4, pitch=pitch)
        _vault_niches(d, area, tops_n, facing, f"vault_niche{n}", start)
        start += len(tops_n)
    # Name slabs high on the south wall over the perk, and two family
    # portraits over the north niches.
    kit.loculi(d.bp, x_w + 124.0, x_wall - 124.0, y_s, f + 132.0, facing=Facing.NORTH,
               ident="vault_slabs", rows=2)
    for n, x in enumerate((x_w + 44.0, x_wall - 29.0)):
        d.mounted(area, "portraits", "p7_picture_frame_modern_01", x, y_n - 2.0, f + 200.0,
                  Facing.SOUTH)
    # Iron sconces on the west wall either side of the door, lit.
    for n, y in enumerate((y_s + 110.0, y_n - 110.0)):
        fx_, fy_, fz = kit.sconce(d.bp, x_w, y, f + 96.0, facing=Facing.EAST,
                                  ident=f"vault_sconce{n}")
        kit.candle(d.bp, fx_, fy_, fz - 7.0, ident=f"vault_sconce{n}_candle", height=6.0)
        d.bp.place_light(Point(fx_, fy_, fz + 6.0), colour=FLAME, radius=192.0,
                         zone_name="vault", shadows=False, id=f"vault_sconce{n}_light")
    # A small sarcophagus in the middle of the floor, candles and an offering
    # on its lid.
    cx, cy = (x_w + x_wall - 64) / 2.0 - 20.0, (y_s + y_n) / 2.0
    lid = kit.sarcophagus(d.bp, cx, cy, f, ident="vault_sarc", length=72.0)
    d.keep(cx - 50, cy - 36, cx + 50, cy + 36)
    _candles(d, area, [(cx - 30, cy + 12, lid), (cx + 30, cy + 12, lid)], ident="vault_sarc_candle",
             zone="vault", light_every=2)
    for m, dx, dy, yaw in (("p7_decanter_glass_bottle", -8.0, -6.0, 0.0),
                           ("p7_book_vintage_open_04", 12.0, -4.0, 90.0),
                           ("p7_foliage_plant_meskel_3_noflower", -20.0, -10.0, 0.0),
                           ("p7_foliage_weed_cluster_lrg", 2.0, 10.0, 70.0),
                           ("p7_foliage_weed_cluster_sml_b", 22.0, -12.0, 0.0),
                           ("p7_3arc_park_leaves_corner_1", -30.0, -8.0, 40.0)):
        d.prop(area, "offerings", m, cx + dx, cy + dy, yaw, surface=lid, check=False, solid=False)
    kit.chain(d.bp, cx, cy, inside.maxs.z, length=60.0, ident="vault_lamp_chain")
    (_, _, z0), (_, _, z1) = collision_box("p7_zm_der_light_shade")
    d.prop(area, "lamp", "p7_zm_der_light_shade", cx, cy, surface=inside.maxs.z - 62.0 - (z1 - z0),
           check=False, solid=False)
    d.bp.place_light(Point(cx, cy, inside.maxs.z - 80.0), colour=FLAME, radius=256.0,
                     zone_name="vault", shadows=False, id="vault_shade_light")
    # A kneeler at the sarcophagus's east end, looking at it, and an iron
    # candelabrum behind the kneeler.
    kit.kneeler(d.bp, cx + 62.0, cy, f, facing=Facing.WEST, ident="vault_kneeler")
    d.claim(cx + 62.0, cy, 22.0)
    cups = kit.candelabra(d.bp, cx + 104.0, cy + 30.0, f, ident="vault_candelabra")
    d.claim(cx + 104.0, cy + 30.0, 14.0)
    _candles(d, area, cups, ident="vault_candelabra_candle", zone="vault", light_every=3)
    # Bones and mortar fallen from the niches at the foot of their walls,
    # leaves blown in heaped in the corners by the door.
    _wall_piles(d, area, "floor", VAULT_DUST[:5], x_w + 20, y_s + 20, x_wall - 66, y_n - 20,
                piles=2, per=5, surface=f)
    _wall_piles(d, area, "floor", VAULT_DUST[5:], x_w + 20, y_s + 20, x_wall - 66, y_n - 20,
                piles=2, per=4, surface=f)


#: What the vigil left on the chapel floor, kept to the side aisles.
CHAPEL_FLOOR = ("p7_3arc_park_leaves_grp_2", "p7_3arc_park_leaves_corner_1",
                "p7_debris_trash_paper_02", "p7_debris_trash_paper_03",
                "p7_foliage_weed_cluster_sml_a", "p7_office_paper_sheet_10",
                "p7_cleaning_paper_ball_brown", "p7_foliage_weed_cluster_sml_b")
#: A table's worth of vigil tributes: flowers, books, a vase, a box.
CHAPEL_TRIBUTES = ("p7_book_vintage_open_01", "p7_decanter_glass_bottle", FLOWERS,
                   "p7_book_vintage_04", "p7_box_wood_01_sm",
                   "p7_foliage_plant_meskel_3_noflower", FLOWERS, "p7_book_vintage_02")


def _chapel_table(d: Dresser, area: str, x: float, y: float, *, half_x: float, half_y: float,
                  ident: str, count: int, zone: str = "chapel") -> None:
    """A plain table of tributes: ``count`` of :data:`CHAPEL_TRIBUTES` in a
    row along its length, a candle at one end."""
    f = d.ground(x, y)
    top = kit.side_table(d.bp, x, y, f, ident=ident, half_x=half_x, half_y=half_y)
    d.claim(x, y, max(half_x, half_y))
    along_y = half_y > half_x
    a0, a1 = ((y - half_y + 12, y + half_y - 2) if along_y else (x - half_x + 12, x + half_x - 2))
    _lay_row(d, area, "tributes", CHAPEL_TRIBUTES[:count], a0, a1, x if along_y else y, top,
             depth=2.0 * (half_x if along_y else half_y), along_y=along_y)
    cx, cy = (x, y - half_y + 6) if along_y else (x - half_x + 6, y)
    _candles(d, area, [(cx, cy, top)], ident=f"{ident}_candle", zone=zone, light_every=1)


def _dress_chapel(d: Dresser, rooms, features) -> None:
    room = rooms["chapel"]
    inside = room.interior
    area = "chapel"
    f = room.floor_z
    x_w, x_e, y_s, y_n = inside.mins.x, inside.maxs.x, inside.mins.y, inside.maxs.y
    # The altar at the east end, the Founder's coffin on its bier before it.
    top = kit.altar(d.bp, x_e, 0.0, f, ident="altar")
    ax = x_e - 24.0
    d.keep(x_e - 110, -110, x_e, 110)
    _candles(d, area, [(ax, y, top) for y in (-56.0, -28.0, 0.0, 28.0, 56.0)],
             ident="altar_candle", zone="chapel", light_every=2)
    for n, y in enumerate((-40.0, 40.0)):
        d.prop(area, "altar", BOOKS[n], ax - 10, y, 90.0, surface=top, check=False, solid=False)
    for m, x, y in (("p7_decanter_glass_bottle", ax + 12, -12.0), ("p7_container_bottle_wine_01", ax - 14, 12.0),
                    ("p7_box_wood_01_sm", ax + 12, 14.0)):
        d.prop(area, "altar", m, x, y, surface=top, check=False, solid=False)
    # A plain cross on the wall over the altar, curtains either side of it,
    # and a spray of flowers on a stand at each front corner of the dais.
    kit.wall_cross(d.bp, x_e, 0.0, top + 40.0, facing=Facing.WEST, ident="altar_cross",
                   height=80.0)
    drape = "p7_cloth_drape_02_beige"
    (_dx0, dy0, _dz0), (_dx1, dy1, dz1) = MODEL_BOX[drape]
    for n, y in enumerate((-135.0, 135.0)):
        d.prop(area, "drapes", drape, x_e - 9.0, y, 90.0, surface=f,
               check=False, solid=False)
        # Its rail (Z59): a curtain hangs from something.
        # Held off the east wall on two brackets, not rods from the 400-high
        # ceiling.
        rz = f + dz1 + 1.5
        y0, y1 = y + dy0 - 4.0, y + dy1 + 4.0
        hang_bar(d.bp, f"altar_drape_rail{n}", (x_e - 9.0, y0), (x_e - 9.0, y1), rz,
                 ceiling=inside.maxs.z, rods=False)
        for k, by in enumerate((y0 + 3.0, y1 - 3.0)):
            d.bp.add_block(Bounds.between((x_e - 9.0, by - 0.5, rz - 1.5), (x_e, by + 0.5, rz)), RAIL,
                           contents=("detail",), reachable=False,
                           id=f"altar_drape_rail{n}_bracket_{k}", note="curtain rail bracket")
    for n, y in enumerate((-84.0, 84.0)):
        tray = kit.flower_stand(d.bp, x_e - 94.0, y, f + 8.0, ident=f"altar_flowers{n}")
        d.prop(area, "altar", FLOWERS, x_e - 94.0, y, 60.0 * n, surface=tray, check=False,
               solid=False)
    bier_x = ax - 150.0
    kit._box(d.bp, bier_x - 56, -18, f, bier_x + 56, 18, f + 30, kit.PANEL, "coffin_bier")
    kit._box(d.bp, bier_x - 52, -16, f + 30, bier_x + 52, 16, f + 52, kit.WOOD, "founder_coffin")
    features["coffin"] = Point(bier_x, 0.0, f + 52.0)
    d.keep(bier_x - 60, -60, bier_x + 60, 60)
    # Flowers and a pair of candles on the Founder's funeral coffin, a
    # wreath on its foot, and a spray on a stand at each corner of the bier.
    for n, dx in enumerate((-14.0, 16.0)):
        d.prop(area, "coffin", FLOWERS, bier_x + dx, 0.0, 90.0 * n, surface=f + 52.0,
               check=False, solid=False)
    _candles(d, area, [(bier_x - 40, 0.0, f + 52.0), (bier_x + 40, 0.0, f + 52.0)],
             ident="coffin_candle", zone="chapel", light_every=2)
    kit.wreath(d.bp, bier_x - 52, 0.0, f + 42.0, facing=Facing.WEST, ident="founder_wreath",
               radius=8.0)
    for n, (dx, dy) in enumerate(((-34.0, -44.0), (-34.0, 44.0), (34.0, -44.0), (34.0, 44.0))):
        tray = kit.flower_stand(d.bp, bier_x + dx, dy, f, ident=f"bier_flowers{n}")
        d.prop(area, "coffin", FLOWERS, bier_x + dx, dy, 45.0 * n, surface=tray, check=False,
               solid=False)
    # The lectern beside the dais, north of the aisle, the Bible open on it.
    lx, ly = x_e - 132.0, 132.0
    lt = kit.lectern(d.bp, lx, ly, f, ident="chapel_lectern")
    d.claim(lx, ly, 16.0)
    d.prop(area, "lectern", "p7_book_vintage_open_04", lx, ly, 0.0, surface=lt, check=False,
           solid=False)
    d.prop(area, "lectern", "p7_office_paper_sheet_03", lx + 4.0, ly + 8.0, 10.0, surface=lt + 2.0,
           check=False, solid=False)
    # Pews in two blocks either side of the aisle, facing the altar.
    # 84 apart: 20 of pew and a 64-unit aisle between rows, the pinch
    # point Scale_Standards.pdf allows (N5).  On each: hymnals, a cushion,
    # an order of service and a folded handkerchief.
    extras = ((-8.0, 46.0, -25.0, 14.0), (36.0, -18.0, -3.0, 50.0), (20.0, 45.0, -25.0, 2.0))
    for n, x in enumerate(range(1400, 1740, 84)):
        for side, y in (("s", -200.0), ("n", 200.0)):
            if d.free(x + 10, y, 14, 62):
                kit.pew(d.bp, float(x), float(x) + 20.0, y, f, ident=f"pew_{side}{n}",
                        facing=Facing.EAST)
                d.prop(area, "hymnals", BOOKS[n % 3], x + 10, y + 30 - 20 * (n % 3), 90.0,
                       surface=f + 20.0, check=False, solid=False)
                d.prop(area, "hymnals", BOOKS[(n + 1) % 3], x + 10, y - 40, 80.0,
                       surface=f + 20.0, check=False, solid=False)
                cushion, paper, book, hanky = extras[n % 3]
                d.prop(area, "hymnals", BOOKS[(n + 2) % 3], x + 11, y + book, 95.0,
                       surface=f + 20.0, check=False, solid=False)
                d.prop(area, "pew_cushions", "p7_cai_apt_couch_cushion_sml", x + 13, y + cushion,
                       90.0, surface=f + 20.0, check=False, solid=False)
                d.prop(area, "pew_papers", "p7_office_paper_sheet_01", x + 12, y + paper, 0.0,
                       surface=f + 20.0, check=False, solid=False)
                d.prop(area, "pew_papers", "p7_cleaning_paper_folded_wrapped", x + 14,
                       y + hanky + 4.0, 90.0, surface=f + 20.0, check=False, solid=False)
    # Beyond the pew ends, in the side aisles: iron candle stands and flower
    # stands, turn about, one between each pair of rows -- clear of the
    # corners, the windows and the machines.
    stands = []
    for n, x in enumerate((1452.0, 1536.0, 1620.0, 1704.0)):
        for y in (-285.0, 285.0):
            if not d.free(x, y, 9, 9) or d.bp.interactive_blocks(Point(x, y, f), 82.0, 82.0):
                continue
            if n % 2 == 0:
                kit._box(d.bp, x - 3, y - 3, f, x + 3, y + 3, f + 44, kit.BLACK,
                         f"candlestand_{n}_{int(y)}")
                stands.append((x, y, f + 44.0))
            else:
                tray = kit.flower_stand(d.bp, x, y, f, ident=f"aisle_flowers_{n}_{int(y)}")
                d.prop(area, "aisle_flowers", FLOWERS, x, y, 30.0 * n, surface=tray,
                       check=False, solid=False)
            d.claim(x, y, 10.0)
    _candles(d, area, stands, ident="stand_candle", zone="chapel", light_every=1)
    # The organ in the south-west corner, the organist's chair at it, books
    # and a page of music on its case, and a stack of hymnals beside it.
    _keys, case = kit.organ(d.bp, x_w + 10.0, x_w + 84.0, y_s, f, facing=Facing.NORTH,
                            ident="chapel_organ")
    d.keep(x_w + 6.0, y_s, x_w + 88.0, y_s + 32.0)
    for m, x in (("p7_book_vintage_02", x_w + 22.0), ("p7_office_paper_sheet_03", x_w + 48.0),
                 ("p7_book_vintage_04", x_w + 70.0)):
        d.prop(area, "organ", m, x, y_s + 10.0, 0.0, surface=case, check=False, solid=False)
    kit.candle(d.bp, x_w + 36.0, y_s + 10.0, case, ident="chapel_organ_candle", height=8.0)
    d.piece(area, "chairs", "p7_chair_wood_fancy_01", x_w + 44.0, y_s + 50.0, 0.0, surface=f)
    if d.prop(area, "organ", "p7_book_vintage_05", x_w + 104.0, y_s + 16.0, 0.0, surface=f):
        for k, m in enumerate(("p7_book_vintage_03", "p7_book_vintage_01")):
            d.prop(area, "organ", m, x_w + 104.0, y_s + 16.0, 20.0 * (k + 1), surface=f + 3.0 + 2.0 * k,
                   check=False, solid=False)
    # By the west door: the font on the north side, the guest book on a
    # table on the south, and the mourners' coats on pegs either side.
    kit.font(d.bp, x_w + 54.0, 236.0, f, ident="chapel_font")
    d.claim(x_w + 54.0, 236.0, 18.0)
    gt = kit.side_table(d.bp, x_w + 46.0, -222.0, f, ident="guest_table", half_x=12.0,
                        half_y=16.0, height=32.0)
    d.claim(x_w + 46.0, -222.0, 18.0)
    d.prop(area, "guest_book", "p7_book_vintage_open_01", x_w + 46.0, -226.0, 0.0, surface=gt,
           check=False, solid=False)
    d.prop(area, "guest_book", "p7_office_paper_sheet_12", x_w + 44.0, -210.0, 15.0, surface=gt,
           check=False, solid=False)
    for side in (1.0, -1.0):
        for k, (m, y) in enumerate((("p7_clothes_hanging_01_suit", 100.0),
                                    ("p7_clothes_hanging_01_dress", 124.0),
                                    ("p7_clothes_hanging_01_shirt", 148.0))):
            out = kit.hook_peg(d.bp, x_w, side * y, f + 92.0, facing=Facing.EAST,
                               ident=f"chapel_peg{int(side)}_{k}")
            (_, _, z0), (_, _, z1) = collision_box(m)
            d.prop(area, "coats", m, x_w + out, side * y, 0.0, surface=f + 91.0 - (z1 - z0),
                   check=False, solid=False)
    # Tribute tables: one against each long wall between the double tap and
    # the window, one by the east wall north of the altar.
    _chapel_table(d, area, x_w + 187.0, y_n - 22.0, half_x=36.0, half_y=12.0,
                  ident="tribute_n", count=5)
    _chapel_table(d, area, x_w + 187.0, y_s + 22.0, half_x=36.0, half_y=12.0,
                  ident="tribute_s", count=5)
    _chapel_table(d, area, x_e - 62.0, 250.0, half_x=58.0, half_y=14.0, ident="tribute_e",
                  count=8)
    # Portraits of the family and the Founder, a clock over the altar end.
    for n, y in enumerate((-400.0, -200.0, 200.0, 300.0)):
        d.mounted(area, "portraits", "p7_picture_frame_modern_01", x_w + 2, y,
                  f + 96.0, Facing.EAST)
    for n, x in enumerate((x_w + 187.0, x_e - 200.0)):
        d.mounted(area, "portraits", "p7_picture_frame_modern_01", x, y_n - 2.0, f + 140.0,
                  Facing.SOUTH)
        d.mounted(area, "portraits", "p7_picture_frame_modern_01", x, y_s + 2.0, f + 140.0,
                  Facing.NORTH)
    d.mounted(area, "portraits", "p7_picture_frame_modern_01", x_e - 2.0, 330.0, f + 110.0,
              Facing.WEST)
    d.mounted(area, "portraits", "p7_clock_metal_wall_01_base", x_e - 3, 200.0,
              f + 150.0, Facing.WEST)
    # Three lamp shades hung down the aisle on long iron rods.
    for n, x in enumerate((1440.0, 1580.0, 1700.0)):
        low = inside.maxs.z - 200.0
        kit._box(d.bp, x - 0.5, -0.5, low, x + 0.5, 0.5, inside.maxs.z, kit.BLACK,
                 f"chapel_lamp_rod{n}")
        (_, _, z0), (_, _, z1) = collision_box("p7_zm_der_light_shade")
        d.prop(area, "lamps", "p7_zm_der_light_shade", x, 0.0, surface=low - (z1 - z0),
               check=False, solid=False)
        d.bp.place_light(Point(x, 0.0, low - 20.0), colour=FLAME, radius=320.0,
                         zone_name="chapel", shadows=False, id=f"chapel_lamp_light{n}")
    # The hymn board: a standing board against the west wall.
    hx_, hy = d.piece(area, "hymn_board", "p7_zm_der_chalkboard_vintage", x_w + 16.0,
                      -300.0,
                      (Facing.EAST.world_yaw - _mount_face("p7_zm_der_chalkboard_vintage")) % 360.0,
                      surface=f, reach=64.0)
    features["notices"]["chapel_hymns"] = Point(hx_ + 32.0, hy, f + 56.0)
    # The crypt's plaque, on the east wall beside the crypt door.
    _plaque(d, x_e, -210.0, f + 60.0, facing=Facing.WEST, ident="crypt_plaque")
    features["notices"]["crypt_door"] = Point(x_e - 40.0, -210.0, f + 56.0)
    # Leaves blown in, heaped against the side walls, and the vigil's
    # dropped orders of service in little drifts beside them: in the side
    # aisles only, out of the pews and the aisle.
    for y0_, y1_, wall in ((272.0, y_n - 16, "n"), (y_s + 16, -272.0, "s")):
        _wall_piles(d, area, "floor", CHAPEL_FLOOR[:2] + CHAPEL_FLOOR[4:5] + CHAPEL_FLOOR[7:],
                    x_w + 110, y0_, x_e - 120, y1_, piles=2, per=4, walls=wall, surface=f)
        _wall_piles(d, area, "floor", CHAPEL_FLOOR[2:4] + CHAPEL_FLOOR[5:7],
                    x_w + 110, y0_, x_e - 120, y1_, piles=2, per=4, walls=wall, surface=f)


#: Bone models laid in a niche or on a sill, beside its (brush) skull.  The
#: install has no skull or long-bone model (MODEL_BOX grepped), so
#: skulls, shins, chains, candelabra and wreaths are kit brushes and the
#: models here are the loose bones round them.
#: (Not p7_gib_chunk_bone_02: the model checks read its origin-straddling
#: box as a ceiling fixture, Z44.)
CRYPT_BONES = ("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03")
#: Grave goods a tomb niche keeps beside its skull: jars, a flask, a book.
TOMB_GOODS = ("p7_container_bottle_wine_01", "p7_chemistry_kit_large_bottle",
              "p7_book_vintage_03_burn", "p7_bottle_glass_liquor_03")
#: What else a niche keeps at its ends: crumbled mortar, a prayer book,
#: a jar or a letter left by a visitor.
NICHE_KEEPSAKES = ("p7_debris_brick_chunk_hlf_01", "p7_book_vintage_02",
                   "p7_container_bottle_wine_01", "p7_debris_brick_chunk_hlf_02",
                   "p7_book_vintage_03_burn", "p7_debris_trash_paper_09",
                   "p7_bottle_glass_liquor_03", "p7_debris_brick_chunk_03")
#: Along-the-shelf offsets of the pieces either side of a niche's skull,
#: at least 8 apart and clear of the skull (6 wide).
NICHE_SLOTS = (-18.0, -10.0, 10.0, 18.0)
#: Crypt floor clutter besides bones and brick: splinters, rags, burnt pages.
CRYPT_LITTER = ("p7_debris_wood_board_splinter_01", "p7_debris_wood_board_splinter_02",
                "p7_book_vintage_02_burn", "p7_debris_trash_paper_08",
                "p7_debris_brick_chunk_hlf_01", "p7_debris_concrete_rubble_sm_06")
#: The crypt stair's flight (``cemetery.Plan``): centred on y -300, 128 wide,
#: 15 treads of 32 x 16 rising west from x 2496.
FLIGHT_EDGE_Y = -300.0 + 128.0 / 2.0
FLIGHT_STEPS, FLIGHT_RUN, FLIGHT_RISE = 15, 32.0, 16.0


def _toward(facing: Facing, x: float, y: float, along: float, out: float = 0.0):
    """(x, y) moved ``along`` the wall a ``facing`` shelf is on and ``out`` from it."""
    fx = {Facing.EAST: 1.0, Facing.WEST: -1.0}.get(facing, 0.0)
    fy = {Facing.NORTH: 1.0, Facing.SOUTH: -1.0}.get(facing, 0.0)
    return (x + along, y + fy * out) if fy else (x + fx * out, y + along)


def _fill_niches(d: Dresser, area: str, rng, tops, *, facing: Facing, ident: str, zone: str,
                 skip=(), goods: Sequence[str] = (), lit_every: int = 4,
                 span: float = 20.0) -> int:
    """Lay out burial niches or opened slots: every ``lit_every``-th holds a
    candle, the rest a skull (kit) in the middle and bone models either side
    along the shelf, inside its depth; ``goods`` put a jar or a book in some.
    Returns the models laid."""
    laid, lit = 0, []
    slots = [s for s in NICHE_SLOTS if abs(s) <= span]
    for n, (x, y, z) in enumerate(tops):
        if n in skip:
            continue
        if lit_every and n % lit_every == 0:
            lit.append((x, y, z))
            continue
        kit.skull(d.bp, x, y, z, facing=facing, ident=f"{ident}_skull{n}")
        for k, s in enumerate(slots):
            if goods and k == len(slots) - 1 and n % 3 == 1:
                model, group = goods[n % len(goods)], "niche_goods"
            elif rng.random() < 0.15:
                continue
            elif abs(s) > 15.0:
                model, group = NICHE_KEEPSAKES[(2 * n + k) % len(NICHE_KEEPSAKES)], "niche_goods"
            else:
                model, group = CRYPT_BONES[(n + k) % len(CRYPT_BONES)], "niche_bones"
            bx, by = _toward(facing, x, y, s, rng.uniform(-1.5, 1.5))
            # keepsakes lie along the shelf so they stay inside its depth
            yaw = (rng.uniform(0.0, 360.0) if group == "niche_bones" else
                   (0.0 if facing in (Facing.NORTH, Facing.SOUTH) else 90.0)
                   + rng.uniform(-10.0, 10.0))
            d.prop(area, group, model, bx, by, yaw, surface=z, check=False, solid=False)
            laid += 1
    if lit:
        _candles(d, area, lit, ident=f"{ident}_candle", zone=zone, light_every=3)
    return laid


def _first_free(d: Dresser, area: str, group: str, model: str, spots, yaw: float = 0.0,
                **kw) -> tuple[float, float] | None:
    """``model`` at the first of ``spots`` that is free; None if none is."""
    for x, y in spots:
        if d.prop(area, group, model, x, y, yaw, **kw):
            return x, y
    return None


def _bone_pile(d: Dresser, area: str, rng, x: float, y: float, floor: float, *, ident: str,
               facing: Facing) -> None:
    """A collapsed heap of bones: kit skulls tumbled together and loose
    bones round them, all inside 30 of (x, y)."""
    for n, (dx, dy) in enumerate(((0, 0), (9, 4), (-8, 6), (3, -9), (-4, 14))):
        kit.skull(d.bp, x + dx, y + dy, floor, facing=facing, ident=f"{ident}_skull{n}")
    kit.long_bones(d.bp, x, y - 17, floor, facing=Facing.NORTH, ident=f"{ident}_shins",
                   count=4)
    for n in range(10):
        a, r = n * 2.0 * math.pi / 10, 25.0 + (n % 3) * 4.0
        d.prop(area, "bone_pile", CRYPT_BONES[n % len(CRYPT_BONES)], x + r * math.cos(a),
               y + r * math.sin(a), rng.uniform(0.0, 360.0), surface=floor, check=False,
               solid=False)
    d.claim(x, y, 30.0)


def _dress_crypt(d: Dresser, rooms, features) -> None:
    # --- the stairs: candles in the wall niches over the gallery
    stairs = rooms["stairs"]
    si = stairs.interior
    f = stairs.floor_z
    rng = random.Random(41)
    spots = []
    for n in range(6):
        x = si.mins.x + 60 + n * 80
        # The gallery beside the flight is at the crypt floor, so the niches
        # are set at a hand's height over it, two rows alternating.
        z = f + 44.0 + (n % 2) * 36.0
        kit._box(d.bp, x - 8, si.maxs.y - 12, z - 4, x + 8, si.maxs.y, z, kit.DARK_STONE,
                 f"stair_niche{n}", note="a candle niche in the gallery wall")
        # a name plate under each niche
        kit._box(d.bp, x - 9, si.maxs.y - 1, z - 14, x + 9, si.maxs.y, z - 8, kit.IRON,
                 f"stair_niche{n}_plate")
        spots.append((x - 3, si.maxs.y - 6, z))
        kit.skull(d.bp, x + 4, si.maxs.y - 6, z, facing=Facing.SOUTH, ident=f"stair_niche{n}_skull")
    _candles(d, "stairs", spots, ident="stair_candle", zone="crypt_stairs", light_every=2)
    # A few bones kicked onto the treads, back from the flight's north edge
    # (where the handrail stands).
    for n in range(6):
        step = 2 + n * 2
        tx = si.mins.x + step * FLIGHT_RUN + 16.0
        tz = f + FLIGHT_RISE * (FLIGHT_STEPS - step)
        d.prop("stairs", "treads", CRYPT_BONES[(n + 1) % len(CRYPT_BONES)], tx,
               FLIGHT_EDGE_Y - 14.0, rng.uniform(0.0, 360.0), surface=tz, check=False, solid=False)
    # An iron handrail down the flight's north edge, over the drop to the
    # gallery: a stepped bar on posts every second tread.
    rail_y = FLIGHT_EDGE_Y - 3.0
    kit.stair_rail(d.bp, si.mins.x, rail_y, f, steps=FLIGHT_STEPS, run=FLIGHT_RUN,
                   rise=FLIGHT_RISE, ident="stair_rail", first=2)
    for s in range(2, FLIGHT_STEPS, 2):
        post = ("p7_zm_der_handrail_post_end" if s in (2, FLIGHT_STEPS - 1)
                else "p7_zm_der_handrail_post_middle")
        d.prop("stairs", "rail_posts", post, si.mins.x + s * FLIGHT_RUN + 16.0, rail_y, 0.0,
               surface=f + FLIGHT_RISE * (FLIGHT_STEPS - s), check=False)
    # Sealed burial slots high on both long walls, a few broken open with
    # their bones on the sill -- the stairwell was a burial gallery first.
    for wall, facing, z0, rows, ident, opened in (
            (si.maxs.y, Facing.SOUTH, f + 130.0, 3, "stair_loculi_n",
             {(0, 1), (0, 4), (0, 7), (1, 2), (1, 5), (1, 8), (2, 0), (2, 3), (2, 6), (2, 9),
              (0, 9), (1, 0)}),
            (si.mins.y, Facing.NORTH, f + 60.0, 4, "stair_loculi_s",
             {(0, 0), (0, 3), (0, 6), (0, 8), (1, 1), (1, 5), (2, 2), (2, 7), (2, 9), (3, 4),
              (3, 0), (1, 9)})):
        sills = kit.loculi(d.bp, si.mins.x + 24, si.maxs.x - 24, wall, z0, facing=facing,
                           ident=ident, rows=rows, opened=frozenset(opened))
        _fill_niches(d, "stairs", rng, sills, facing=facing, ident=ident, zone="crypt_stairs",
                     lit_every=5)
    for n, (x, y) in enumerate(((2200.0, -172.0), (2380.0, -172.0), (2280.0, -430.0),
                                (2460.0, -430.0))):
        kit.chain(d.bp, x, y, si.maxs.z, length=96.0 + 24.0 * (n % 2), ident=f"stair_chain{n}")
    # The gallery beside the flight: a bone-strewn ledge nobody sweeps, the
    # bones in heaps rather than an even spread; nothing in it snags a foot.
    _heaps(d, "stairs", "gallery", CRYPT_FLOOR, si.mins.x + 24, -228.0, si.maxs.x - 24,
           si.maxs.y - 16, heaps=14, per_heap=6, solid=False)
    for n, x in enumerate((2180.0, 2440.0)):
        _first_free(d, "stairs", "gallery_lamps", "p7_zm_der2_light_hurricane_lamp",
                    [(x + 20 * k, si.maxs.y - 26) for k in range(4)])
    _first_free(d, "stairs", "gallery_box", "p7_box_wood_01_long",
                [(2320.0 + 16 * k, si.maxs.y - 30) for k in range(6)], 90.0)
    # The strip south of the flight: a broken coffin, fallen slabs, a shroud
    # and the gravedigger's shovel among the bones.
    sy0, sy1 = si.mins.y + 12, -386.0
    _first_free(d, "stairs", "south_coffin", "p7_crate_wood_01",
                [(2300.0 + 20 * k, sy0 + 26) for k in range(6)])
    _first_free(d, "stairs", "south_coffin", "p7_crate_wood_01_short_open_lid",
                [(2250.0 - 12 * k, sy0 + 30) for k in range(6)], 20.0)
    for n, x in enumerate((2170.0, 2400.0, 2480.0)):
        _first_free(d, "stairs", "south_slabs", STONE_BROKEN, [(x + 10 * k, sy0 + 20) for k in range(5)],
                    70.0 * n)
    for model, x, yaw in (("p7_pallet_wood_damaged", 2210.0, 10.0),
                          ("p7_tools_shovel", 2360.0, 80.0),
                          ("p7_bed_sheet_barrack_03", 2440.0, 0.0),
                          ("p7_zm_der2_light_hurricane_lamp", 2140.0, 0.0),
                          ("p7_box_wood_01_sm", 2340.0, 0.0),
                          ("p7_debris_wood_board_cluster_burn_02", 2270.0, 30.0)):
        _first_free(d, "stairs", "south_goods", model,
                    [(x + 12 * k, sy1 - 22 - 6 * (k % 3)) for k in range(6)], yaw)
    _heaps(d, "stairs", "south", CRYPT_FLOOR + CRYPT_LITTER, si.mins.x + 110, sy0,
           si.maxs.x - 110, sy1, heaps=8, per_heap=5, solid=False)

    # --- the ossuary: shelves of bones
    oss = rooms["ossuary"]
    oi = oss.interior
    f = oss.floor_z
    tops_s = kit.niche_wall(d.bp, 2900.0, 3240.0, oi.mins.y, f, facing=Facing.NORTH,
                            ident="ossuary_niches_s")
    tops_n = kit.niche_wall(d.bp, 2680.0, 2880.0, oi.maxs.y, f, facing=Facing.SOUTH,
                            ident="ossuary_niches_n")
    d.keep(2900.0, oi.mins.y, 3240.0, oi.mins.y + 24)
    d.keep(2680.0, oi.maxs.y - 24, 2880.0, oi.maxs.y)
    _fill_niches(d, "ossuary", rng, tops_s, facing=Facing.NORTH, ident="ossuary_niches_s",
                 zone="ossuary")
    # Dr. Moore's shelf: the middle bay of the north run's middle row,
    # labelled, and nothing on it but shins.
    moore = 4
    _fill_niches(d, "ossuary", rng, tops_n, facing=Facing.SOUTH, ident="ossuary_niches_n",
                 zone="ossuary", skip={moore})
    mx, my, mz = tops_n[moore]
    for n, dx in enumerate((-15.0, 15.0)):
        kit.long_bones(d.bp, mx + dx, my, mz, facing=Facing.SOUTH, ident=f"ossuary_moore_shins{n}",
                       count=6)
    for n, dy in enumerate((-5.0, 5.0)):
        d.prop("ossuary", "moore_shelf", CRYPT_BONES[n], mx, my + dy, 45.0 * n,
               surface=mz, check=False, solid=False)
    kit._box(d.bp, mx - 18, oi.maxs.y - 22, mz - 12, mx + 18, oi.maxs.y - 20, mz - 2, kit.IRON,
             "ossuary_moore_label", note="label: RETURNED BY DR. MOORE")
    # More runs on the west wall (either side of the stair door) and the
    # east wall south of the window, clear of the torches.
    for a0, a1, wall, facing, pitch, ident in (
            (-500.0, -376.0, oi.mins.x, Facing.EAST, 62.0, "ossuary_niches_w0"),
            (-216.0, 40.0, oi.mins.x, Facing.EAST, 64.0, "ossuary_niches_w1"),
            (-524.0, -436.0, oi.maxs.x, Facing.WEST, 44.0, "ossuary_niches_e0"),
            (-404.0, -316.0, oi.maxs.x, Facing.WEST, 44.0, "ossuary_niches_e1")):
        tops = kit.niche_run(d.bp, a0, a1, wall, f, facing=facing, ident=ident, pitch=pitch)
        d.keep(min(wall, wall + (24 if facing is Facing.EAST else -24)), a0,
               max(wall, wall + (24 if facing is Facing.EAST else -24)), a1)
        _fill_niches(d, "ossuary", rng, tops, facing=facing, ident=ident, zone="ossuary",
                     span=20.0 if pitch > 50 else 12.0)
    # Solid clutter stays out of the strip in front of the wall buy.
    d.keep(2740.0, oi.mins.y, 2860.0, oi.mins.y + 84.0)
    lids = []
    for n, x in enumerate((2800.0, 3100.0)):
        lid = kit.sarcophagus(d.bp, x, -200.0 + 60 * n, f, ident=f"ossuary_sarc{n}")
        lids.append((x, -200.0 + 60 * n, lid))
        d.keep(x - 70, -240.0 + 60 * n, x + 70, -160.0 + 60 * n)
    # Candles and bones on both lids; the ossuary's plaque lies on the first.
    for n, (x, y, lid) in enumerate(lids):
        _candles(d, "ossuary", [(x - 40, y + 10, lid), (x + 40, y + 10, lid)],
                 ident=f"ossuary_sarc{n}_candle", zone="ossuary", light_every=2)
        for k in range(3):
            d.prop("ossuary", "lid_bones", CRYPT_BONES[k % 2], x - 12 + 14 * k, y - 10,
                   rng.uniform(0.0, 360.0), surface=lid, check=False, solid=False)
        d.prop("ossuary", "lid_lamp", "p7_zm_der2_light_hurricane_lamp", x - 30, y - 8, 0.0,
               surface=lid, check=False, solid=False)
    px, py, plid = lids[0]
    kit._box(d.bp, px - 16, py + 6, plid, px + 16, py + 20, plid + 1, kit.IRON, "ossuary_plaque")
    features["notices"]["ossuary"] = Point(px, py + 50.0, f + 56.0)
    # Stone urns against the south run, a collapsed bone pile in the
    # south-west corner, ossuary chests and a broken coffin lid.
    for n, x in enumerate((2960.0, 3140.0)):
        kit.urn(d.bp, x, oi.mins.y + 64.0, f, ident=f"ossuary_urn{n}")
        d.claim(x, oi.mins.y + 64.0, 16.0)
    _bone_pile(d, "ossuary", rng, oi.mins.x + 56.0, oi.mins.y + 70.0, f, ident="ossuary_pile",
               facing=Facing.NORTH)
    for model, spots, yaw in (
            ("p7_box_wood_01_long", [(3050.0 + 8 * k, oi.mins.y + 62.0) for k in range(5)], 90.0),
            ("p7_box_wood_01_long", [(oi.mins.x + 44.0, -60.0 + 20 * k) for k in range(5)], 0.0),
            ("p7_box_wood_01_sm", [(oi.mins.x + 44.0, -130.0 - 12 * k) for k in range(4)], 0.0),
            ("p7_zm_der_magic_box_fake_trunk", [(3040.0 - 20 * k, -10.0) for k in range(5)], 0.0),
            ("p7_crate_wood_01_short_open_lid", [(2950.0 + 12 * k, -380.0) for k in range(5)], 25.0),
            ("p7_pallet_wood_damaged", [(3040.0 + 12 * k, -330.0) for k in range(5)], 70.0),
            ("p7_debris_wood_board_splinter_02", [(2990.0, -360.0 + 8 * k) for k in range(5)], 40.0),
            ("p7_zm_der2_light_hurricane_lamp", [(2860.0 + 12 * k, -440.0) for k in range(5)], 0.0)):
        _first_free(d, "ossuary", "floor_goods", model, spots, yaw)
    for n, (x, y) in enumerate(((2800.0, -300.0), (3100.0, -60.0))):
        kit.chain(d.bp, x, y, oi.maxs.z, length=72.0, ident=f"ossuary_chain{n}")
    _heaps(d, "ossuary", "floor", CRYPT_FLOOR + CRYPT_LITTER, oi.mins.x + 20, oi.mins.y + 30,
           oi.maxs.x - 20, oi.maxs.y - 30, heaps=12, per_heap=4)

    # --- the Founder's Tomb
    tomb = rooms["tomb"]
    ti = tomb.interior
    f = tomb.floor_z
    lid = kit.sarcophagus(d.bp, 2960.0, 470.0, f, ident="founder_sarcophagus", length=128.0)
    features["sarcophagus"] = Point(2960.0, 470.0 - 40.0, lid)
    # The ending is bought standing south of the sarcophagus; its plaque is
    # read from the north side, clear of that trigger.
    features["exit"] = Point(2960.0, 400.0, f)
    features["notices"]["sarcophagus"] = Point(2960.0, 540.0, f + 40.0)
    d.keep(2880.0, 360.0, 3040.0, 520.0)
    # Solid clutter stays out of an 80 strip in front of the wall buy.
    d.keep(ti.mins.x, 400.0, ti.mins.x + 90.0, 560.0)
    # A ring of candles round it, open on the south where the ending is bought.
    ring = [(2960.0 + 110.0 * math.cos(a), 470.0 + 90.0 * math.sin(a), f)
            for k, a in enumerate([k * math.pi / 5 for k in range(10)]) if k not in (7, 8)]
    _candles(d, "tomb", ring, ident="tomb_candle", zone="tomb", light_every=2)
    for n, x in enumerate((2760.0, 3160.0)):
        kit.obelisk(d.bp, x, 620.0, f, ident=f"tomb_needle{n}", height=112.0)
        d.claim(x, 620.0, 30.0)
        # Offerings on the needle's steps: bones and a candle each corner.
        _candles(d, "tomb", [(x - 14, 606.0, f + 16.0), (x + 14, 634.0, f + 16.0)],
                 ident=f"tomb_needle{n}_candle", zone="tomb", light_every=2)
        for k, (ox, oy) in enumerate(((x + 10, 610.0), (x - 10, 630.0), (x + 10, 630.0))):
            d.prop("tomb", "offerings", CRYPT_BONES[k % 2], ox, oy, 60.0 * k, surface=f + 16.0,
                   check=False, solid=False)
    for k, (m, ox, oy, yaw) in enumerate((
            ("p7_decanter_glass_bottle", 2930.0, 470.0, 0.0),
            ("p7_book_vintage_open_04", 2990.0, 470.0, 90.0),
            # a dried wreath of leaves where the flowers were
            ("p7_3arc_park_leaves_corner_1", 2960.0, 478.0, 0.0),
            ("p7_gib_chunk_bone_03", 2912.0, 462.0, 30.0),
            ("p7_bottle_glass_wine_01", 3010.0, 482.0, 0.0))):
        d.prop("tomb", "offerings", m, ox, oy, yaw, surface=lid, check=False, solid=False)
    # The door's name lintel, and dried wreaths either side of it.
    kit.name_lintel(d.bp, 2896.0, 3024.0, ti.mins.y, -96.0, facing=Facing.NORTH,
                    ident="tomb_lintel")
    for n, x in enumerate((2840.0, 3080.0)):
        kit.wreath(d.bp, ti.mins.y, x, f + 110.0, facing=Facing.NORTH, ident=f"tomb_wreath{n}")
    # Niche walls on the west (either side of the wall buy) and the north
    # (either side of Pack-a-Punch), clear of the torches.
    for a0, a1, wall, facing, pitch, ident in (
            (280.0, 420.0, ti.mins.x, Facing.EAST, 70.0, "tomb_niches_w0"),
            (560.0, 690.0, ti.mins.x, Facing.EAST, 65.0, "tomb_niches_w1"),
            (2672.0, 2750.0, ti.maxs.y, Facing.SOUTH, 78.0, "tomb_niches_n0"),
            (2770.0, 2880.0, ti.maxs.y, Facing.SOUTH, 55.0, "tomb_niches_n1"),
            (3040.0, 3150.0, ti.maxs.y, Facing.SOUTH, 55.0, "tomb_niches_n2"),
            (3170.0, 3248.0, ti.maxs.y, Facing.SOUTH, 78.0, "tomb_niches_n3")):
        tops = kit.niche_run(d.bp, a0, a1, wall, f, facing=facing, ident=ident, pitch=pitch)
        if facing is Facing.EAST:
            d.keep(wall, a0, wall + 24.0, a1)
        else:
            d.keep(a0, wall - 24.0, a1, wall)
        _fill_niches(d, "tomb", rng, tops, facing=facing, ident=ident, zone="tomb",
                     goods=TOMB_GOODS, span=20.0 if pitch > 60 else 11.0)
    # Sealed slots above, over the whole north wall and the west.
    for wall, a0, a1, facing, ident, opened in (
            (ti.maxs.y, ti.mins.x + 16, ti.maxs.x - 16, Facing.SOUTH, "tomb_loculi_n",
             {(0, 0), (0, 3), (0, 5), (0, 8), (1, 1), (1, 4), (1, 7), (1, 9)}),
            (ti.mins.x, ti.mins.y + 24, ti.maxs.y - 24, Facing.EAST, "tomb_loculi_w",
             {(0, 1), (0, 6), (1, 3), (1, 8), (0, 9)})):
        sills = kit.loculi(d.bp, a0, a1, wall, f + 150.0, facing=facing, ident=ident,
                           opened=frozenset(opened))
        _fill_niches(d, "tomb", rng, sills, facing=facing, ident=ident, zone="tomb",
                     lit_every=0)
    # Standing candelabra either side of Pack-a-Punch's approach, urns in
    # three corners, chains over the sarcophagus.
    for n, (x, y) in enumerate(((2850.0, 690.0), (3070.0, 690.0))):
        cups = kit.candelabra(d.bp, x, y, f, ident=f"tomb_candelabrum{n}")
        _candles(d, "tomb", cups, ident=f"tomb_candelabrum{n}_candle", zone="tomb",
                 light_every=3)
        d.claim(x, y, 14.0)
    for n, (x, y) in enumerate(((ti.mins.x + 34.0, ti.mins.y + 34.0),
                                (ti.maxs.x - 34.0, ti.mins.y + 34.0),
                                (ti.maxs.x - 36.0, ti.maxs.y - 56.0))):
        kit.urn(d.bp, x, y, f, ident=f"tomb_urn{n}")
        d.claim(x, y, 16.0)
    for n, (x, y) in enumerate(((2880.0, 400.0), (3040.0, 400.0), (2880.0, 545.0),
                                (3040.0, 545.0))):
        kit.chain(d.bp, x, y, ti.maxs.z, length=120.0 + 16.0 * (n % 2), ident=f"tomb_chain{n}")
    # The reliquary: an iron-bound chest on a low stone plinth east of the
    # sarcophagus.
    kit._box(d.bp, 3094.0, 452.0, f, 3130.0, 488.0, f + 14.0, kit.TRIM, "tomb_reliquary_plinth")
    d.prop("tomb", "reliquary", "p7_zm_der_magic_box_fake_trunk", 3112.0, 470.0, 90.0,
           surface=f + 14.0, check=False, solid=False)
    d.claim(3112.0, 470.0, 20.0)
    # The east window: a hole broken through into a tunnel, shored with
    # timber, broken brick either side of it.
    east = next(b for b in tomb.aperture_boxes if b.mins.x >= ti.maxs.x - 1.0)
    kit.tunnel_mouth(d.bp, ti.maxs.x, east.mins.y, east.maxs.y, f, east.maxs.z,
                     facing=Facing.WEST, ident="tomb_tunnel")
    for n, (m, dy, yaw) in enumerate((("p7_debris_rockychunks_small_01", -44.0, 0.0),
                                      ("p7_brick_dirty_breakout_07", -30.0, 0.0),
                                      ("p7_debris_plaster_rubble_med_02", -58.0, 180.0),
                                      ("p7_debris_rockychunks_small_11", 44.0, 180.0),
                                      ("p7_brick_dirty_breakout_07", 32.0, 180.0),
                                      ("p7_debris_concrete_rubble_sm_12", 58.0, 90.0))):
        y = (east.mins.y if dy < 0 else east.maxs.y) + dy
        d.prop("tomb", "tunnel_rubble", m, ti.maxs.x - 22.0, y, yaw, surface=f,
               check=False, solid=False)
    # Only a few generic heaps: the room's budget is on the pieces.
    _heaps(d, "tomb", "floor", CRYPT_FLOOR + CRYPT_LITTER, ti.mins.x + 20, ti.mins.y + 20,
           ti.maxs.x - 20, ti.maxs.y - 20, heaps=8, per_heap=5)


def _heaps(d: Dresser, area: str, group: str, palette: Sequence[str], x0: float, y0: float,
           x1: float, y1: float, *, heaps: int, per_heap: int, solid: bool | None = None) -> int:
    """Bones and rubble in ``heaps`` tight piles of ``per_heap`` pieces,
    each drawn again until its whole disc is free (a pile drawn once into a
    keep-out would place nothing, and the room would come up short).
    Returns how many pieces went down."""
    # P15: pieces anywhere within 40 of a random centre read as litter
    # spread over the floor, not heaps.  So each heap is one tight pile
    # (``_pile``) at the foot of the rectangle's edge, where bones fall from
    # the niches and mortar from the walls.
    placed = 0
    for _ in range(heaps):
        # A heap's pieces lie on each other, so none of them is solid (Z44).
        solid = False
        got = _wall_piles(d, area, group, palette, x0, y0, x1, y1, piles=1, per=per_heap,
                          solid=solid)
        if not got:
            # No room on an edge: a free-standing pile anywhere in the box.
            for _ in range(60):
                got = _pile(d, area, group, palette, d.rng.uniform(x0 + 22, x1 - 22),
                            d.rng.uniform(y0 + 22, y1 - 22), per_heap, rng=d.rng, solid=solid)
                if got:
                    break
        placed += got
    return placed


def _torches(d: Dresser, rooms) -> int:
    """Iron torch sconces down the crypt: along the stair gallery's wall and
    round the ossuary and the tomb, each with a flame light."""
    laid = 0
    runs = (
        ("stairs", "crypt_stairs", "north", (2100.0, 2260.0, 2420.0, 2580.0)),
        ("ossuary", "ossuary", "west", (-520.0, 60.0)),
        ("ossuary", "ossuary", "east", (-420.0, 40.0)),
        ("tomb", "tomb", "west", (260.0, 700.0)),
        ("tomb", "tomb", "north", (2760.0, 3160.0)),
        ("tomb", "tomb", "south", (2760.0, 3160.0)),
    )
    for key, zone, side, spots in runs:
        room = rooms[key]
        inside = room.interior
        z = room.floor_z + 88.0
        for n, along in enumerate(spots):
            if side == "north":
                x, y, facing = along, inside.maxs.y, Facing.SOUTH
            elif side == "south":
                x, y, facing = along, inside.mins.y, Facing.NORTH
            elif side == "west":
                x, y, facing = inside.mins.x, along, Facing.EAST
            else:
                x, y, facing = inside.maxs.x, along, Facing.WEST
            if d.bp.interactive_blocks(Point(x, y, room.floor_z), 24.0, 24.0):
                continue
            flame = kit.sconce(d.bp, x, y, z, facing=facing, ident=f"torch_{key}_{side}{n}")
            d.bp.place_light(Point(*flame), colour=FLAME, radius=256.0, zone_name=zone,
                             shadows=False, id=f"torch_{key}_{side}{n}_light")
            laid += 1
    return laid


def _gates(d: Dresser, rooms) -> None:
    """Stone piers either side of the two big iron gates into the grounds:
    front lawn -> hills (in the hills' west wall, y = 0) and hills -> row (in
    the row's south wall, x = 200)."""
    for key, into, ident, pick in (
        ("hills", Facing.EAST, "gate_hills_piers",
         lambda box, room: abs((box.mins.y + box.maxs.y) / 2.0) < 1.0
         and box.maxs.x <= room.interior.mins.x + 1.0),
        ("row", Facing.NORTH, "hills_row_piers",
         lambda box, room: abs((box.mins.x + box.maxs.x) / 2.0 - 200.0) < 1.0
         and box.maxs.y <= room.interior.mins.y + 1.0),
    ):
        room = rooms[key]
        for box in room.aperture_boxes:
            if pick(box, room):
                kit.gate_piers(d.bp, box, room.floor_z + 2.0, into=into, ident=ident)


def dress(bp: Blueprint, plan, rooms: Mapping[str, object]) -> dict:
    """Dress every area.  Returns where the quest and the notices hang:
    ``epitaphs`` and ``notices`` (key -> Point), ``shovel``, ``open_grave``,
    ``founder``, ``wisps``, ``coffin``, ``sarcophagus``, and ``counts``
    (models per area)."""
    del plan
    d = Dresser(bp)
    _keep_the_ways_clear(d, bp, rooms)
    features: dict = {"epitaphs": {}, "notices": {}}
    _gates(d, rooms)
    # Walls, backdrop and walk set pieces claim their ground before the
    # lamps and the scatter.
    features["boundaries"] = _boundaries(d, bp, rooms)
    from . import cemetery_scenes as scenes

    features["facades"] = scenes.facades(bp, rooms, d.seed)
    features["walk_set_pieces"] = _walk_set_pieces(d, rooms)
    story = scenes.walk_scenes(d, rooms)
    features["fresh_graves"] = story["graves"]  # the quest's soul graves
    gate = scenes.gate_scene(d, rooms)
    row = scenes.row_scene(d, rooms)
    features["wires"] = scenes.wires(d, rooms)
    features["kerbs"] = _kerbs(d)
    # Before the areas, so their scatter keeps off the lamps.
    _reserve_set_pieces(d)
    lamps = _path_lamps(d, rooms)
    features["path_lamps"] = {key: len(row) for key, row in lamps.items()}
    d.rng = random.Random(f"{d.seed}:walks")
    features["benches"] = _walkside(d, lamps)
    # Each area draws from its own seeded stream, so a change to one area's
    # dressing does not reshuffle every area dressed after it (otherwise
    # adding a model to the hills would move bones in the crypt stair).
    areas = (("gate", _dress_gate), ("shed", _dress_shed), ("hills", _dress_hills),
             ("row", _dress_row), ("vault", _dress_vault),
             ("chapel", _dress_chapel), ("crypt", _dress_crypt))
    for done, (key, dresser) in enumerate(areas, 1):
        progress.stage(f"dressing areas {done}/{len(areas)} ({key})")
        d.rng = random.Random(f"{d.seed}:{key}")
        dresser(d, rooms, features)
    progress.stage("dressing the open grounds")
    features["torches"] = _torches(d, rooms)
    # Then the chapel's burnt floor, the fires as light pools, lanterns
    # on the pier caps, then the open grounds filled at three heights.
    d.rng = random.Random(f"{d.seed}:round2")
    features["chapel_ruin"] = scenes.chapel_ruin(d, rooms)
    features["shed_remains"] = scenes.shed_remains(d, rooms)
    spots = {"fires": story["fires"] + gate["fires"] + row["fires"], "smoulder": story["smoulder"]}
    features["fires"] = scenes.fires(d, spots, facade_windows=[
        w for w in features["facades"]["chapel"]["windows"] if w[3] is Side.WEST],
        chapel=rooms["chapel"])
    features["pier_tops"] = scenes.pier_tops(d, rooms)
    from .cemetery_lore import dress_lore
    dress_lore(d, bp, rooms, features)  # optional story readables (P11), placed last
    d.rng = random.Random(f"{d.seed}:verges")
    _verges(d, rooms)
    features["grass"] = _grass(d, rooms, features)
    # The three-height fill takes what the grass left.
    features["fill"] = scenes.fill(d, rooms, FILL)
    features["counts"] = dict(d.counts)
    features["fences"] = dict(d.fences)
    d.flush()
    return features


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------
def _prompt(text: str) -> str:
    return text if "{+activate}" in text else f"{text} -- hold ^3[{{+activate}}]^7"


def wire_notices(bp: Blueprint, plan, rooms, features: dict) -> list[tuple[str, Point]]:
    """Every readable headstone and notice: a use prompt and its lines."""
    from ..script.tricks import use_notices
    from .cemetery import EPITAPHS, NOTICE_LINES

    del plan, rooms
    entries = []
    spots: list[tuple[str, Point]] = []
    for table, where, prefix in ((EPITAPHS, features["epitaphs"], "EPITAPH"),
                                 (NOTICE_LINES, features["notices"], "NOTICE")):
        missing = set(table) - set(where)
        if missing:
            raise ValueError(f"{prefix.lower()}s with nowhere to hang: {sorted(missing)}")
        for key, (prompt, lines) in table.items():
            ref = f"{prefix}_{key.upper()}"
            prompt_asset = bp.add_map_string(ref, _prompt(prompt), kind="triggerstring")
            replies = tuple(bp.add_map_string(f"{ref}_{n}", line) for n, line in enumerate(lines))
            entries.append((where[key], prompt_asset, replies))
            spots.append((key, where[key]))
    bp.add_custom_logic(use_notices(entries, radius=56.0))
    return spots


def wire_gags(bp: Blueprint) -> None:
    """The reactions to what players do; no zone sign-ins and no round-end PA
    (P13, P17)."""
    from ..blueprint.catalogue import PERKS
    from ..script.gags import (
        box_reactions,
        gag_say,
        player_reactions,
        power_on_announcement,
    )
    from .cemetery import GAG_IDLE_SECONDS, GAG_LINES

    said = {key: bp.add_map_string(f"GAG_{key.upper()}", text) for key, text in GAG_LINES.items()}
    specialty = {p.slug: p.specialty for p in PERKS}
    bp.add_custom_logic(gag_say())
    bp.add_custom_logic(player_reactions(
        downed=said["downed"],
        downed_feed=said["downed_feed"],
        bled_out_feed=said["bled_out_feed"],
        revived=said["revived"],
        revived_broke=said["revived_broke"],
        reviver=said["reviver"],
        fee=25,
        perks={specialty["juggernog"]: said["perk_jugg"],
               specialty["quick_revive"]: said["perk_revive"]},
        pap=said["pap"],
        idle=("hills", GAG_IDLE_SECONDS, said["idle"]),
    ))
    bp.add_custom_logic(box_reactions(used=said["box"], moved=said["box_moved"]))
    # No round-end PA, no random PA and no zone sign-ins (P13, P17): lines on a timer or on walking in carry no
    # information and crowd the quest's timed cues.  The power line stays: it
    # answers the switch and says the crypt is open.
    bp.add_custom_logic(power_on_announcement(said["power"]))


# ---------------------------------------------------------------------------
# Boundary walls, a backdrop over them, and set
# pieces that narrow and roof the long walk.
# ---------------------------------------------------------------------------
#: Weeds, leaf drifts and fallen brick gathered at the foot of the walls.
WALL_FOOT = ("p7_foliage_weed_cluster_med", "p7_foliage_weed_cluster_lrg",
             "p7_foliage_weed_cluster_sml_a", "p7_3arc_park_leaves_corner_1",
             "p7_3arc_park_leaves_grp_2", "p7_debris_brick_chunk_hlf_01",
             "p7_debris_brick_chunk_03", "p7_foliage_grass_tall_cluster_med")
#: Up to this many wall-foot pieces per wall panel, drifted toward one end
#: (``WallStyle.foot_per_panel``, default 3): raised for more
#: props in drifts, not spread evenly.
FOOT_PER_PANEL = 7
#: Which walls of which open rooms face open air (the backdrop's sides), and
#: which of them gets the church spire.
#: The three-height fill per open area: (ground, waist, tall) pieces tried.
FILL = {"gate": (1450, 118, 18), "hills": (3450, 290, 40), "row": (1450, 118, 16)}
BACKDROP_SIDES = {"gate": (Side.SOUTH, Side.WEST, Side.NORTH),
                  "hills": (Side.SOUTH, Side.EAST),
                  "row": (Side.NORTH, Side.WEST, Side.EAST)}
SPIRE_SIDE = {"hills": Side.SOUTH}


def _wall_keepouts(rooms) -> list[tuple[float, float, float]]:
    from .cemetery import BOX, BOX_MOVES, MACHINES, POWER, WALL_BUYS

    keep = [(x, y, 90.0) for _k, _kind, x, y, _f in MACHINES]
    keep += [(x, y, 70.0) for _k, _kind, x, y, _f in WALL_BUYS]
    keep += [(BOX[0], BOX[1], 90.0), (POWER[0], POWER[1], 60.0)]
    keep += [(x, y, 90.0) for x, y, _f in BOX_MOVES]
    return keep


def _on_a_walk(x: float, y: float, margin: float) -> bool:
    """(x, y) on a walk or forecourt, or within *margin* of one (its kerb)."""
    from .cemetery import path_boxes

    return any(x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin
               for _r, x0, y0, x1, y1 in path_boxes().values())


def _boundaries(d: Dresser, bp: Blueprint, rooms) -> dict[str, int]:
    """Dress every wall of the three open rooms and stand the backdrop."""
    from ..dressing import WallStyle, backdrop, boundary_wall

    styles = {
        "gate": WallStyle(pier=kit.DARK_WET, coping=kit.PIER_STONE, plinth=kit.MOSS_BRICK,
                          rail=kit.BLACK, foot_models=WALL_FOOT, foot_per_panel=FOOT_PER_PANEL),
        "hills": WallStyle(pier=kit.MOSS_BRICK, coping=kit.DARK_WET, plinth=kit.DARK_STONE,
                           rail=kit.BLACK, foot_models=WALL_FOOT, foot_per_panel=FOOT_PER_PANEL),
        "row": WallStyle(pier=kit.WET_STONE, coping=kit.PIER_STONE, plinth=kit.DARK_WET,
                         rail=kit.BLACK, foot_models=WALL_FOOT, foot_per_panel=FOOT_PER_PANEL),
    }
    keep = _wall_keepouts(rooms)
    counts = {"walls": 0, "backdrop": 0}
    for key in ("gate", "hills", "row"):
        room = rooms[key]
        style = styles[key]
        for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST):
            props, taken = boundary_wall(bp, room, side, style, ground_at=d.ground,
                                         seed=d.seed, keep=keep)
            for x0, y0, x1, y1 in taken:
                d.keep(x0 - 4, y0 - 4, x1 + 4, y1 + 4)
            props = [p for p in props if not _on_a_walk(p[1].x, p[1].y, 16.0)]
            if props:
                bp.place_props(props, id=f"{key}_wallfoot_{side.name.lower()}")
                for spec in props:
                    d.keep_disc(spec[1].x, spec[1].y, 18.0)
            counts["walls"] += 1
        counts["backdrop"] += backdrop(bp, room, BACKDROP_SIDES[key], kit.IRON, seed=d.seed,
                                       spire=SPIRE_SIDE.get(key), far_material=kit.BLACK)
    return counts


def _arch(d: Dresser, x: float, y0: float, y1: float, *, ident: str) -> None:
    """An iron arch over a walk running east-west: two posts, a shallow
    pointed top, and a lantern hung from the apex."""
    from ..dressing import sheared_bar

    g0, g1 = d.ground(x, y0), d.ground(x, y1)
    top = max(g0, g1) + 150.0
    for n, (y, g) in enumerate(((y0, g0), (y1, g1))):
        kit._box(d.bp, x - 3, y - 3, g - kit.BURY, x + 3, y + 3, top, kit.BLACK, f"{ident}_post{n}")
        kit._box(d.bp, x - 5, y - 5, g - kit.BURY, x + 5, y + 5, g + 14, kit.PIER_STONE,
                 f"{ident}_foot{n}")
    mid = (y0 + y1) / 2.0
    for n, y in enumerate((y0, y1)):
        sheared_bar(d.bp, f"{ident}_rib{n}", (x, y, top), (x, mid, top + 30.0), 1.8, kit.IRON)
    kit._box(d.bp, x - 1.5, y0, top - 8, x + 1.5, y1, top - 5, kit.IRON, f"{ident}_tie")
    from ..blueprint.elements import FLOATS_ON_PURPOSE

    kit._box(d.bp, x - 0.6, mid - 0.6, top - 30, x + 0.6, mid + 0.6, top + 26, kit.IRON,
             f"{ident}_chain", note=FLOATS_ON_PURPOSE)
    # The lantern stands on its hook plate (Z44 wants something under it).
    kit._box(d.bp, x - 7.5, mid - 7.5, top - 57.0, x + 7.5, mid + 7.5, top - 56.0, kit.IRON,
             f"{ident}_plate", note=FLOATS_ON_PURPOSE)
    d.prop("hills", "arches", "p7_zm_der2_light_hurricane_lamp", x, mid, 0.0,
           surface=top - 56.0, check=False, solid=False)
    d.keep_disc(x, y0, 14.0)
    d.keep_disc(x, y1, 14.0)


def _fallen_tree(d: Dresser, x0: float, y0: float, x1: float, y1: float, *, ident: str) -> None:
    """A dead tree down across part of the walk: its trunk on the ground,
    a snapped stump at the root end and branches jutting up."""
    from ..dressing import sheared_bar

    g0, g1 = d.ground(x0, y0), d.ground(x1, y1)
    sheared_bar(d.bp, f"{ident}_trunk", (x0, y0, g0 + 8), (x1, y1, g1 + 6), 9.0, kit.IRON)
    kit._box(d.bp, x0 - 12, y0 - 12, g0 - kit.BURY, x0 + 12, y0 + 12, g0 + 30, kit.IRON,
             f"{ident}_stump")
    for k, t in enumerate((0.35, 0.6, 0.85)):
        bx, by = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        bz = g0 + (g1 - g0) * t + 12
        sheared_bar(d.bp, f"{ident}_branch{k}", (bx, by, bz),
                    (bx + (34 if k % 2 else -38), by + (40 if k % 2 else -30), bz + 16 + 6 * k),
                    2.5, kit.IRON)
    lo_x, hi_x = sorted((x0, x1))
    lo_y, hi_y = sorted((y0, y1))
    d.keep(lo_x - 16, lo_y - 16, hi_x + 16, hi_y + 16)


def _toppled_angel(d: Dresser, x: float, y: float, *, ident: str) -> None:
    """A mourning angel knocked off its plinth, lying along the walk's edge."""
    g = d.ground(x, y)
    kit._box(d.bp, x - 22, y + 30, g - kit.BURY, x + 22, y + 74, g + 26, kit.TRIM, f"{ident}_plinth")
    kit._box(d.bp, x - 44, y - 9, g - 2, x + 22, y + 9, g + 14, kit.STONE, f"{ident}_robe")
    kit._box(d.bp, x - 58, y - 5, g - 2, x - 44, y + 5, g + 10, kit.STONE, f"{ident}_head")
    kit._box(d.bp, x - 30, y + 9, g - 2, x + 10, y + 34, g + 4, kit.STONE, f"{ident}_wing")
    kit._box(d.bp, x + 26, y - 20, g - 2, x + 44, y - 4, g + 6, kit.STONE, f"{ident}_wingbroken")
    d.keep(x - 64, y - 24, x + 48, y + 78)


def _collapsed_wall(d: Dresser, x: float, y: float, facing_y: float, *, ident: str) -> None:
    """A stub of a mausoleum's garden wall, fallen into the walk: stepped
    broken courses and loose blocks."""
    g = d.ground(x, y)
    s = 1.0 if facing_y > 0 else -1.0
    for k, (w, h) in enumerate(((120, 56), (84, 38), (48, 22))):
        y0, y1 = sorted((y, y + s * (16 + 14 * k)))
        kit._box(d.bp, x - w / 2 + 10 * k, y0, g - kit.BURY, x + w / 2 - 6 * k, y1, g + h,
                 kit.PIER_STONE, f"{ident}_course{k}")
    for k, (dx, dy) in enumerate(((-40, 60), (10, 70), (46, 52))):
        bx, by = x + dx, y + s * dy
        gb = d.low(bx - 8, by - 6, bx + 8, by + 6)
        kit._box(d.bp, bx - 8, by - 6, gb - kit.BURY, bx + 8, by + 6, gb + 9,
                 kit.PIER_STONE, f"{ident}_block{k}")
    y0, y1 = sorted((y - s * 10, y + s * 80))
    d.keep(x - 70, y0, x + 70, y1)


def _dirt_mound(d: Dresser, x: float, y: float, *, ident: str) -> None:
    """A fresh grave's spoil heap at the walk's edge, a shovel stuck in it."""
    g = d.ground(x, y)
    for k, (hw, hd, h) in enumerate(((46, 26, 10), (34, 18, 18), (20, 10, 24))):
        kit._box(d.bp, x - hw, y - hd, g - kit.BURY, x + hw, y + hd, g + h, kit.MUD,
                 f"{ident}_heap{k}")
    kit._box(d.bp, x + 12, y - 1, g + 20, x + 14, y + 1, g + 58, kit.WOOD, f"{ident}_shaft")
    kit._box(d.bp, x + 8, y - 5, g + 14, x + 18, y + 5, g + 26, kit.IRON, f"{ident}_blade")
    d.keep(x - 52, y - 32, x + 52, y + 32)


def _walk_set_pieces(d: Dresser, rooms) -> int:
    """Break the hills walk (176 wide, 2,000 long) with set pieces that each
    take up to half its width, alternating sides, and roof it with arches.
    At least 100 units stay clear at every point."""
    laid = 0
    _fallen_tree(d, -470.0, 150.0, -360.0, 30.0, ident="walk_fallen_tree")
    laid += 1
    _toppled_angel(d, -60.0, -66.0, ident="walk_toppled_angel")
    laid += 1
    _collapsed_wall(d, 470.0, 96.0, -1.0, ident="walk_collapsed_wall")
    laid += 1
    _dirt_mound(d, 820.0, -70.0, ident="walk_spoil")
    laid += 1
    for n, x in enumerate((-640.0, -230.0, 330.0, 660.0, 1040.0)):
        for shift in (0.0, 30.0, -30.0, 60.0, -60.0):
            # Posts just off the walk's edge (88) and its 8-unit margin.
            if d.free(x + shift, -106.0, 4, 4) and d.free(x + shift, 106.0, 4, 4):
                _arch(d, x + shift, -106.0, 106.0, ident=f"walk_arch{n}")
                laid += 1
                break
    return laid


def _kerbs(d: Dresser, *, seg: float = 64.0) -> int:
    """Low stone kerbs along both edges of the long walks: 5
    units high, under a step, so nothing stops a player crossing them."""
    from .cemetery import PATHS

    laid = 0
    for key, _room, (ax, ay), (bx, by), hw in PATHS:
        if key not in ("gate_walk", "hills_walk", "north_walk", "row_walk", "shed_walk"):
            continue
        horizontal = ay == by
        lo, hi = (min(ax, bx), max(ax, bx)) if horizontal else (min(ay, by), max(ay, by))
        c = ay if horizontal else ax
        n = max(1, int((hi - lo) // seg))
        step = (hi - lo) / n
        for s in (-1.0, 1.0):
            e = c + s * hw
            for k in range(n):
                a0, a1 = lo + k * step, lo + (k + 1) * step
                pts = [(a, e) if horizontal else (e, a) for a in (a0, a1)]
                g_lo = min(d.ground(*p) for p in pts)
                g_hi = max(d.ground(*p) for p in pts)
                if horizontal:
                    box = (a0, e - 3, a1, e + 3)
                else:
                    box = (e - 3, a0, e + 3, a1)
                kit._box(d.bp, box[0], box[1], g_lo - 8.0, box[2], box[3], g_hi + 5.0, kit.TRIM,
                         f"kerb_{key}_{'lr'[s > 0]}{k}")
                laid += 1
    return laid
