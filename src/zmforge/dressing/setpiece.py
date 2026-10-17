"""Set pieces that split a room's open floor into lanes and pinch points.

A big room dressed only round its walls leaves the middle as one open
field: 13 to 33% of stock density, the corridor-width distribution dominated
by 512+ unit stretches, and nothing to run round.  A stock room puts a set piece every ~330 units (2.1
per k2): a bench island, a row of shelving, a partition, a booth, each big
enough to stop a sight line and make two lanes of the floor round it.

:func:`split_open_floor` finds the widest open stretch of a room (the
largest disk of floor clear of solid props and brushes, the review's own
width measure, :mod:`zmforge.review.scene_metrics`), and while one of at
least *min_width* (512) is left it stands a set piece in its middle, sized
so a lane of at least *lane* units stays free all round it.  The piece goes
through the room's :class:`~.indoor.RoomPlacer` (door lanes, windows,
interactives, keep-outs) and :func:`~.vignette.place_vignette`, so it is all
or nothing, and it cannot cut a route: it stands inside a disk of free
floor with a free ring round it, so any path through the disk goes round.

:data:`SETPIECE_KINDS`: ``lab_bench_island``, ``partition_bay``,
``shelving_rows``, ``isolation_booth``.  Each carries at least one solid
stock model 72+ units wide and 36+ tall, so the ``S3`` check counts it.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from ..materials import Material
from ..spatial import Bounds
from .fixtures import RAIL
from .indoor import PANEL, IndoorSpot, RoomPlacer, _gurney
from .vignette import Block, Item, Kind, Vignette, place_vignette

__all__ = ["SETPIECE_KINDS", "CLUTTER_KINDS", "CLUTTER_THEMES", "open_stretches", "split_open_floor",
           "break_up_floor"]

TOP = Material("t7_metal_panels_4x1", 64.0)
BOOTH = Material("t7_metal_panel_white_perforated", 64.0)
_CAB, _CAB_TOP = "p7_zm_der_cabinet_lab_bottom", "p7_zm_der_cabinet_lab_top"
_SHELF = "p7_shelf_industrial_vintage_96"
_SHELF_BOARDS = (23.44, 51.91, 79.94)   # recipes.props.shelf_boards(_SHELF, 0)
_CLUTTER = ("p7_container_cardboard_box_01", "p7_box_wood_01_sm", "p7_books_office_row_01",
            "p7_box_wood_wine_storage_tan", "p7_office_paper_stack_sml", "p7_box_wood_01_long")


def _j(rng: random.Random, amount: float = 4.0) -> float:
    return rng.uniform(-amount, amount)


# Builders: the spot is the piece's centre, ``u`` from ``-back`` to ``reach``.
def _lab_bench_island(rng, spot):
    parts: list = [
        Item(_CAB, -16.5, 0, 90, solid=True, core=True),
        Item(_CAB, 16.5, 0, 270, solid=True, core=True),
        Block(-34, -56, 36, 34, 56, 38, TOP, "worktop", floats=True),
        Item(_CAB_TOP, 0, 0, 90, on=2, solid=True),
        Item("p7_tank_nitrogen_metal", -22, -40, 0, on=2, solid=False),
        Item("p7_keyboard_metal_tech", 22, 30, 90 + _j(rng, 10), on=2, solid=False),
        Item("p7_book_office_binder_open", -22, 14, rng.uniform(0, 360), on=2, solid=False),
        Item("p7_office_paper_stack_sml", 22, -24, rng.uniform(0, 360), on=2, solid=False),
        Item("p7_bottle_plastic_16oz_water", -24, 36, 0, on=2, solid=False),
        Item("p7_cup_coffee_mug", 26, -44, rng.uniform(0, 360), on=2, solid=False),
        Item("p7_chair_lab_01", -58, -26, rng.uniform(0, 360), solid=True),
        Item("p7_chair_lab_02", 58, 30, rng.uniform(0, 360), solid=True),
        Item("p7_chair_lab_01", 60, -40, rng.uniform(0, 360), solid=True),
    ]
    return parts


def _partition_bay(rng, spot):
    parts: list = [
        Block(-1.5, -96, 0, 1.5, 96, 64, PANEL, "partition"),
        Block(1.5, -1.5, 0, 88, 1.5, 64, PANEL, "partition_arm"),
        Block(-2, -96, 64, 2, 96, 65.5, RAIL, "partition_cap", core=False, floats=True),
        Item("p7_desk_metal_old_01_body", 22, -48, 90, solid=True, core=True),
        Item("p7_desk_metal_old_01_body", 22, 48, 90, solid=True),
        Item("p7_keyboard_metal_tech", 12, -48, 90, on=3, solid=False),
        Item("p7_keyboard_metal_tech", 12, 48, 90, on=4, solid=False),
        Item("p7_book_office_binder_open", 28, -30, rng.uniform(0, 360), on=3, solid=False),
        Item("p7_office_paper_stack_sml", 28, 64, rng.uniform(0, 360), on=4, solid=False),
        Item("p7_chair_lab_01", 62, -44, rng.uniform(0, 360), solid=True),
        Item("p7_chair_lab_02", 64, 52, rng.uniform(0, 360), solid=True),
        # The other face: a filing wall and its bin.
        Item("p7_file_cab_metal_02", -18, -60, 90, solid=True),
        Item("p7_file_cab_metal_02", -18, -38, 90, solid=True),
        Item("p7_zm_der_cabinet_lab_bottom", -19, 34, 90, solid=True, core=True),
        Item("p7_trashcan_metal_modern_glass", -24, 84, 0, solid=True),
        Item("p7_container_cardboard_box_01", -20, 34, rng.uniform(0, 360), 0.8, on=13, solid=False),
    ]
    return parts


def _shelving_rows(rng, spot):
    parts: list = []
    for k, (u, v, yaw) in enumerate(((-18, -52, 90), (-18, 52, 90), (18, -52, 270), (18, 52, 270))):
        parts.append(Item(_SHELF, u, v, yaw, solid=True, core=k < 2))
    for k, (u, v, _yaw) in enumerate(((-18, -52, 90), (-18, 52, 90), (18, -52, 270), (18, 52, 270))):
        for board in _SHELF_BOARDS:
            for dv in (-26, 0, 26):
                if rng.random() < 0.7:
                    parts.append(Item(_CLUTTER[rng.randrange(len(_CLUTTER))], u + _j(rng, 2), v + dv,
                                      rng.choice((0, 90, 180, 270)) + _j(rng, 6), dz=board, solid=False))
    parts.append(Item("p7_container_cardboard_box_01", 0, 118, rng.uniform(0, 360), solid=True))
    parts.append(Item("zmf_prop_hand_cart", 46, 118, 0, solid=True))
    return parts


def _isolation_booth(rng, spot):
    s, t, hgt = 60.0, 4.0, 112.0
    parts: list = [
        # four walls with a viewing slot 20 high on the two long faces
        Block(-s, -s, 0, -s + t, s, 64, BOOTH, "booth_wall"),
        Block(-s, -s, 84, -s + t, s, hgt, BOOTH, "booth_wall", floats=True),
        Block(s - t, -s, 0, s, s, 64, BOOTH, "booth_wall"),
        Block(s - t, -s, 84, s, s, hgt, BOOTH, "booth_wall", floats=True),
        Block(-s + t, -s, 0, s - t, -s + t, hgt, BOOTH, "booth_wall"),
        Block(-s + t, s - t, 0, s - t, s, hgt, BOOTH, "booth_wall"),
        Block(-s, -s, hgt, s, s, hgt + 3, RAIL, "booth_roof", floats=True),
        # slot frames
        Block(-s - 0.5, -s, 63, -s + t + 0.5, s, 64, RAIL, "slot_sill", core=False, floats=True),
        Block(s - t - 0.5, -s, 63, s + 0.5, s, 64, RAIL, "slot_sill", core=False, floats=True),
        # inside: the chair it was for
        Item("p7_chair_lab_01", 0, 0, rng.uniform(0, 360), solid=True),
        # outside: its service cabinet and gas
        Item(_CAB, 0, s + 17, 0, solid=True, core=True),
        Item("p7_tank_nitrogen_metal", -s - 12, -s + 12, 0, solid=True),
        Item("p7_tank_nitrogen_metal", -s - 12, -s + 32, 0, solid=True),
        Item("p7_office_paper_stack_sml", 30, s + 17, rng.uniform(0, 360), on=10, solid=False),
    ]
    return parts


SETPIECE_KINDS: dict[str, Kind] = {k.name: k for k in (
    Kind("lab_bench_island", "A lab bench island, still set up for the last test.", ("floor",),
         _lab_bench_island, (130.0, 160.0), (0.0, 0.0, 44.0), large=True),
    Kind("partition_bay", "An office bay of partitions, desks back to back, a filing wall behind.",
         ("floor",), _partition_bay, (200.0, 190.0), (20.0, 0.0, 40.0), large=True),
    Kind("shelving_rows", "Back-to-back rows of storage shelving across the floor.", ("floor",),
         _shelving_rows, (270.0, 110.0), (0.0, 0.0, 50.0), large=True),
    Kind("isolation_booth", "A sealed isolation booth, a chair inside, the slot left open.", ("floor",),
         _isolation_booth, (200.0, 170.0), (0.0, 0.0, 70.0), large=True),
)}


# ---------------------------------------------------------------------------
# Where the floor is open
# ---------------------------------------------------------------------------
RES = 16.0


def _obstacles(bp, room, placer: RoomPlacer | None) -> list[tuple[float, float, float, float]]:
    """Plan boxes of what a player cannot walk through in *room*: solid props
    taller than a step, brushes at head height, and what *placer* reserved."""
    from ..blueprint.elements import Massing
    from .place import _placed_props
    from .walldetail import _solid_box

    b, f = room.interior, room.floor_z
    out = []
    for p, pl in _placed_props(bp):
        if p.solid and pl.z_high - f > 18.0 and pl.z_low < f + 60.0:
            x0, y0, x1, y1 = pl.footprint.bounds
            if x1 > b.mins.x and x0 < b.maxs.x and y1 > b.mins.y and y0 < b.maxs.y:
                out.append((x0, y0, x1, y1))
    for m in bp.elements(Massing):
        for s in m.solids:
            x0, y0, z0, x1, y1, z1 = _solid_box(s)
            if x1 > b.mins.x and x0 < b.maxs.x and y1 > b.mins.y and y0 < b.maxs.y \
                    and z0 < f + 60.0 and z1 > f + 18.0:
                out.append((x0, y0, x1, y1))
    if placer is not None:
        out += placer.reserved
    return out


def open_stretches(bp, room, *, placer: RoomPlacer | None = None,
                   obstacles: Sequence[tuple[float, float, float, float]] | None = None
                   ) -> list[tuple[float, float, float]]:
    """Centres of *room*'s open floor, ``(x, y, radius)``: the radius of the
    largest disk of walkable floor centred there, largest first (one per
    local peak, peaks within one radius of a larger one dropped)."""
    from ..review.scene_metrics import _chamfer

    b = room.interior
    nx = max(1, int((b.maxs.x - b.mins.x) / RES))
    ny = max(1, int((b.maxs.y - b.mins.y) / RES))
    walk = [[True] * ny for _ in range(nx)]
    for (x0, y0, x1, y1) in (obstacles if obstacles is not None else _obstacles(bp, room, placer)):
        i0, i1 = max(0, int((x0 - b.mins.x) / RES)), min(nx - 1, int((x1 - b.mins.x) / RES))
        j0, j1 = max(0, int((y0 - b.mins.y) / RES)), min(ny - 1, int((y1 - b.mins.y) / RES))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                walk[i][j] = False
    padded = [[False] * (ny + 2)] + [[False] + r + [False] for r in walk] + [[False] * (ny + 2)]
    edt = _chamfer(padded, nx + 2, ny + 2)
    cells = sorted(((edt[i][j], i, j) for i in range(1, nx + 1) for j in range(1, ny + 1)
                    if padded[i][j]), reverse=True)
    peaks: list[tuple[float, float, float]] = []
    for r, i, j in cells:
        if r < 2 * RES:
            break
        x, y = b.mins.x + (i - 0.5) * RES, b.mins.y + (j - 0.5) * RES
        if any(math.hypot(x - px, y - py) < pr for px, py, pr in peaks):
            continue
        peaks.append((x, y, r))
        if len(peaks) >= 32:
            break
    return peaks


def split_open_floor(bp, room, placer: RoomPlacer, rng: random.Random, *, ident: str,
                     kinds: Sequence[str] | None = None, min_width: float = 512.0,
                     lane: float = 128.0, most: int = 4) -> list[Vignette]:
    """While *room* has an open stretch at least *min_width* wide, stand a set
    piece in its middle with *lane* units of floor free all round it (at
    most *most* pieces).  Call ``placer.flush()`` after.  Returns the placed
    records (also on ``bp.vignettes``)."""
    names = list(kinds or SETPIECE_KINDS)
    placed: list[Vignette] = []
    tried: set[tuple[int, int]] = set()
    while len(placed) < most:
        peaks = [p for p in open_stretches(bp, room, placer=placer)
                 if 2 * p[2] >= min_width and (round(p[0]), round(p[1])) not in tried]
        if not peaks:
            break
        x, y, r = peaks[0]
        tried.add((round(x), round(y)))
        budget = r - lane
        order = sorted(names, key=lambda n: sum(1 for v in placed if v.kind == n) + rng.random())
        for name in order:
            k = SETPIECE_KINDS[name]
            w, d = k.needs
            if math.hypot(w / 2, d / 2) > budget:
                continue
            for yaw in rng.sample((0.0, 90.0, 180.0, 270.0), 4):
                spot = IndoorSpot(x, y, room.floor_z, yaw, "floor", getattr(room, "id", "room"),
                                  width=w, back=d / 2, reach=d / 2,
                                  height=room.interior.maxs.z - room.floor_z)
                made = place_vignette(bp, name, spot, rng, placer, ident=f"{ident}_{len(placed)}",
                                      library=SETPIECE_KINDS, settle=(0, 0))
                if made is not None:
                    placed.append(made)
                    break
            else:
                continue
            break
    return placed


# ---------------------------------------------------------------------------
# Mid-height floor clutter: small groups that break up a bare patch
# ---------------------------------------------------------------------------
# The set pieces above need a 512 stretch and a 128 lane; a room whose
# groups stand 300 apart still reads as open floor between them (the
# floors read open and institutional).  These groups
# are 50-120 across, mid-height (30-90 tall), and go in the middle of every
# clear patch 192+ wide with a walkable lane (48, a player is 32) left all
# round; the small ones fit the gaps between a room's groups.  Centred on the
# spot: ``u`` and ``v`` run from minus to plus half their size.

_DRIP = RAIL


def _gurney_drip(rng, spot):
    parts: list = _gurney(-40, -39, "gurney")
    pad = len(parts) - 1
    parts[0] = Block(-40, -39, 27, -14, 39, 30, parts[0].material, "gurney_frame", core=True, floats=True)
    parts += [
        Item("p7_bed_sheet_barrack_02", -27, -8, 90 + _j(rng, 12), 0.5, on=pad, solid=False),
        Item("p7_bed_pillow_barrack", -27, 26, 90 + _j(rng, 10), 0.7, on=pad, solid=False),
        # an IV stand: pole on a cross foot
        Block(3, -31, 2, 4.5, -29.5, 76, _DRIP, "iv_pole", core=False),
        Block(-3, -37, 0, 10.5, -23.5, 2, _DRIP, "iv_foot", core=False),
        Item("p7_tank_nitrogen_metal", 30, 20, 0, solid=True, core=True),
        Item("p7_bed_pillow_barrack", 18, -12, rng.uniform(0, 360), 0.8, solid=False),
    ]
    return parts


def _pulled_cabinets(rng, spot):
    return [
        Item("p7_file_cab_metal_02", -30, -20, _j(rng, 8), solid=True, core=True),
        Item("p7_file_cab_metal_02", -8, 22, 25 + _j(rng, 8), solid=True),
        Item("p7_file_cab_metal_02_drawer_02", 8, -14, rng.uniform(0, 360), solid=False, core=True),
        Item("p7_file_cab_metal_02_drawer_02", 26, -30, rng.uniform(0, 360), solid=False),
        Item("p7_container_cardboard_box_01", 30, 26, rng.uniform(0, 360), 0.8, solid=True),
        Item("p7_book_vintage_02", 4, -8, rng.uniform(0, 360), solid=False),
    ]


def _file_boxes(rng, spot):
    return [
        Item("p7_crate_wood_01_short", -18, -10, _j(rng, 10), solid=True, core=True),
        Item("p7_container_cardboard_box_01", -18, -10, rng.uniform(0, 30), 0.7, on=0, solid=False),
        Item("p7_crate_wood_01_short", 18, 16, 20 + _j(rng, 10), solid=True),
        Item("p7_box_wood_01_sm", 18, 16, rng.uniform(0, 360), on=2, solid=False),
        Item("p7_luggage_cloth_a_lg_green", 26, -26, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_05", -30, 26, rng.uniform(0, 360), solid=False),
        Item("p7_box_wood_wine_storage_tan", -2, 30, rng.uniform(0, 360), solid=False),
    ]


def _chair_scatter(rng, spot):
    return [
        Item("p7_chair_lab_01", -30, -26, rng.uniform(0, 360), solid=True, core=True),
        Item("p7_chair_lab_02", 28, -20, rng.uniform(0, 360), solid=True),
        Item("p7_chair_waiting_room_01_blue", -6, 26, rng.uniform(0, 360), solid=True),
        Item("p7_sgen_chair_dining_future", 36, 32, rng.uniform(0, 360), solid=True),
        Item("p7_book_vintage_open_04", 2, -2, rng.uniform(0, 360), solid=False),
    ]


def _lab_trolley(rng, spot):
    return [
        Item(_CAB, 0, 0, 0, solid=True, core=True),
        Item("p7_tank_nitrogen_metal", -38, 0, 0, on=0, solid=False),
        Item("p7_keyboard_metal_tech", -10, -2, _j(rng, 8), on=0, solid=False),
        Item("p7_box_wood_wine_storage", 18, 0, _j(rng, 12), on=0, solid=False),
        Item("p7_book_vintage_04", 42, 0, rng.uniform(0, 360), on=0, solid=False),
        Item("p7_chair_lab_01", 22, 38, rng.uniform(0, 360), solid=True),
    ]


def _screen_partition(rng, spot):
    return [
        Block(-1.5, -48, 0, 1.5, 48, 60, PANEL, "screen", core=True),
        Block(-2, -48, 60, 2, 48, 61.5, RAIL, "screen_cap", core=False, floats=True),
        Item("p7_chair_lab_02", 22, 20, rng.uniform(0, 360), solid=True),
        Item("p7_trashcan_metal_modern_glass", -22, -22, 0, solid=True),
        Item("p7_box_wood_wine_storage_tan", 20, -24, rng.uniform(0, 360), solid=False),
    ]


def _plant_spares(rng, spot):
    return [
        Item("p7_barrel_metal_55gal_blue", -26, -14, 0, solid=True, core=True),
        Item("p7_barrel_metal_55gal_blue", 2, -26, 0, solid=True),
        Item("p7_crate_wood_01_short", 22, 14, _j(rng, 12), solid=True, core=True),
        Item("p7_electrical_box_set_box_4", 22, 14, rng.uniform(0, 360), on=2, solid=False),
        Item("p7_cinder_block", -20, 22, rng.uniform(0, 360), solid=False),
        Item("p7_cinder_block", -4, 30, rng.uniform(0, 360), solid=False),
    ]


def _chair_pair(rng, spot):
    return [
        Item(rng.choice(("p7_chair_lab_01", "p7_chair_lab_02")), -14, -8, rng.uniform(0, 360), solid=True,
             core=True),
        Item(rng.choice(("p7_chair_waiting_room_01_blue", "p7_chair_wood_fancy_01")), 16, 10,
             rng.uniform(0, 360), solid=True),
    ]


def _drum_pair(rng, spot):
    return [
        Item("p7_barrel_metal_55gal_blue", -13, 0, 0, solid=True, core=True),
        Item("p7_barrel_metal_55gal_blue", 13, 4, 0, solid=True),
        Item("p7_cinder_block", 0, 22, rng.uniform(0, 360), solid=False),
    ]


def _box_pile(rng, spot):
    return [
        Item("p7_crate_wood_01_short", -6, -4, _j(rng, 15), solid=True, core=True),
        Item("p7_box_wood_01_sm", -6, -4, rng.uniform(0, 360), on=0, solid=False),
        Item("p7_box_wood_wine_storage_tan", 20, 16, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_01", -24, 18, rng.uniform(0, 360), solid=False),
    ]


def _iv_stand(rng, spot):
    return [
        Block(-0.75, -0.75, 2, 0.75, 0.75, 76, RAIL, "iv_pole", core=True),
        Block(-7, -7, 0, 7, 7, 2, RAIL, "iv_foot", core=True),
        Item("p7_tank_nitrogen_metal", 18, 6, 0, solid=True),
        Item("p7_bed_pillow_barrack", -10, 28, rng.uniform(0, 360), 0.7, solid=False),
    ]


def _cabinet_out(rng, spot):
    return [
        Item("p7_file_cab_metal_02", -8, 0, rng.uniform(0, 360), solid=True, core=True),
        Item("p7_file_cab_metal_02_drawer_02", 20, -10, rng.uniform(0, 360), solid=False),
        Item("p7_book_vintage_05", 18, 16, rng.uniform(0, 360), solid=False),
    ]


CLUTTER_KINDS: dict[str, Kind] = {k.name: k for k in (
    Kind("chair_pair", "Two chairs knocked askew and left.", ("floor",), _chair_pair, (64.0, 52.0),
         (0.0, 0.0, 30.0)),
    Kind("drum_pair", "Two drums dragged off the wall.", ("floor",), _drum_pair, (56.0, 56.0),
         (0.0, 0.0, 30.0)),
    Kind("box_pile", "A crate and boxes put down on the way out.", ("floor",), _box_pile, (64.0, 56.0),
         (0.0, 0.0, 30.0)),
    Kind("iv_stand", "A drip stand wheeled away from its bed.", ("floor",), _iv_stand, (50.0, 50.0),
         (0.0, 0.0, 40.0)),
    Kind("cabinet_out", "A filing cabinet walked out into the room, a drawer pulled.", ("floor",),
         _cabinet_out, (60.0, 50.0), (0.0, 0.0, 40.0)),
    Kind("gurney_drip", "A gurney left where it stopped, the drip stand still beside it.", ("floor",),
         _gurney_drip, (110.0, 90.0), (-27.0, 0.0, 34.0)),
    Kind("pulled_cabinets", "Two filing cabinets dragged out and emptied, the drawers on the floor.",
         ("floor",), _pulled_cabinets, (100.0, 90.0), (-10.0, 0.0, 40.0)),
    Kind("file_boxes", "File boxes and a suitcase, stacked to go and left.", ("floor",), _file_boxes,
         (90.0, 90.0), (0.0, 0.0, 30.0)),
    Kind("chair_scatter", "Chairs scattered where people jumped up and ran.", ("floor",),
         _chair_scatter, (110.0, 100.0), (0.0, 0.0, 30.0)),
    Kind("lab_trolley", "A lab cabinet wheeled out mid-test, its kit still on top.", ("floor",),
         _lab_trolley, (120.0, 90.0), (0.0, 0.0, 40.0)),
    Kind("screen_partition", "A privacy screen pulled across the floor, a chair behind it.", ("floor",),
         _screen_partition, (70.0, 100.0), (0.0, 0.0, 40.0)),
    Kind("plant_spares", "Drums and a crate of spares, dragged out for a repair nobody finished.",
         ("floor",), _plant_spares, (90.0, 90.0), (0.0, 0.0, 30.0)),
)}

def _measured(kind: Kind, samples: int = 16) -> Kind:
    """*kind* with ``needs`` widened to what its parts really reach at any of
    their random turns (a part past the spot's box is refused, so a group
    sized to its middle turn was placed one time in a hundred)."""
    from dataclasses import replace as _replace

    from .vignette import _extents

    spot = IndoorSpot(0.0, 0.0, 0.0, 0.0, "floor", "r", width=1e6, back=1e6, reach=1e6, height=160.0)
    ru = rv = 0.0
    for n in range(samples):
        for part in kind.build(random.Random(f"{kind.name} {n}"), spot):
            if isinstance(part, Item):
                eu, ev = _extents(part.model, part.scale, part.yaw)
                ru, rv = max(ru, abs(part.u) + eu), max(rv, abs(part.v) + ev)
            elif isinstance(part, Block):
                ru = max(ru, abs(part.u0), abs(part.u1))
                rv = max(rv, abs(part.v0), abs(part.v1))
    return _replace(kind, needs=(2.0 * rv + 2.0, 2.0 * ru + 2.0))


CLUTTER_KINDS = {name: _measured(k) for name, k in CLUTTER_KINDS.items()}

#: Which clutter suits which room theme.
CLUTTER_THEMES: dict[str, tuple[str, ...]] = {
    "clinic": ("gurney_drip", "chair_scatter", "pulled_cabinets", "screen_partition", "file_boxes",
               "iv_stand", "chair_pair", "cabinet_out", "box_pile"),
    "office": ("pulled_cabinets", "chair_scatter", "file_boxes", "screen_partition", "lab_trolley",
               "chair_pair", "cabinet_out", "box_pile"),
    "lab": ("lab_trolley", "chair_scatter", "file_boxes", "pulled_cabinets", "screen_partition",
            "chair_pair", "cabinet_out", "box_pile"),
    "plant": ("plant_spares", "file_boxes", "lab_trolley", "pulled_cabinets", "drum_pair", "box_pile",
              "cabinet_out"),
}


def break_up_floor(bp, room, placer: RoomPlacer, rng: random.Random, *, ident: str,
                   kinds: Sequence[str] | str = "office", patch: float = 192.0, lane: float = 48.0,
                   most: int = 10, hug: int = 0) -> list[Vignette]:
    """While *room* has a clear patch at least *patch* wide (the largest disk
    of walkable floor, :func:`open_stretches`; 192 by default, as the 256+
    patches were the lanes the keep-outs already hold), stand a clutter group
    (:data:`CLUTTER_KINDS`) in its middle, turned any of four ways, with
    *lane* units of walkable floor left all round it (at most *most*).  The
    placer's own rules hold (door lanes, windows, interactives, keep-outs).
    Then *hug* more small groups beside what already stands
    (:func:`_hug_groups`), each only where every doorway stays joined for a
    player.  Call ``placer.flush()`` after.  Returns the placed records."""
    names = list(CLUTTER_THEMES[kinds] if isinstance(kinds, str) else kinds)
    placed: list[Vignette] = []
    tried: set[tuple[int, int]] = set()
    h = room.interior.maxs.z - room.floor_z
    while len(placed) < most:
        peaks = [p for p in open_stretches(bp, room, placer=placer)
                 if 2 * p[2] >= patch and (round(p[0]), round(p[1])) not in tried]
        if not peaks:
            break
        x, y, r = peaks[0]
        tried.add((round(x), round(y)))
        budget = r - lane
        order = sorted(names, key=lambda n: sum(1 for v in placed if v.kind == n) + rng.random())
        for name in order:
            k = CLUTTER_KINDS[name]
            w, d = k.needs
            if math.hypot(w / 2, d / 2) > budget:
                continue
            made = None
            for yaw in rng.sample((0.0, 90.0, 180.0, 270.0), 4):
                spot = IndoorSpot(x, y, room.floor_z, yaw + rng.uniform(-12.0, 12.0), "floor",
                                  getattr(room, "id", "room"), width=w, back=d / 2, reach=d / 2, height=h)
                made = place_vignette(bp, name, spot, rng, placer, ident=f"{ident}_{len(placed)}",
                                      library=CLUTTER_KINDS, settle=(0, 0))
                if made is not None:
                    break
            if made is not None:
                placed.append(made)
                break
    if hug:
        placed += _hug_groups(bp, room, placer, rng, names, ident=f"{ident}_h", most=hug,
                              first=len(placed))
    return placed


#: A player's half-width plus a margin: a cell is walkable for a player
#: when it is this far from every obstacle (world units).
_BODY = 24.0


def _grid(room, obstacles):
    from ..review.scene_metrics import _chamfer

    b = room.interior
    nx = max(1, int((b.maxs.x - b.mins.x) / RES))
    ny = max(1, int((b.maxs.y - b.mins.y) / RES))
    walk = [[True] * ny for _ in range(nx)]
    for (x0, y0, x1, y1) in obstacles:
        i0, i1 = max(0, int((x0 - b.mins.x) / RES)), min(nx - 1, int((x1 - b.mins.x) / RES))
        j0, j1 = max(0, int((y0 - b.mins.y) / RES)), min(ny - 1, int((y1 - b.mins.y) / RES))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                walk[i][j] = False
    padded = [[False] * (ny + 2)] + [[False] + r + [False] for r in walk] + [[False] * (ny + 2)]
    return _chamfer(padded, nx + 2, ny + 2), nx, ny


def _cell(room, x, y):
    b = room.interior
    return int((x - b.mins.x) / RES) + 1, int((y - b.mins.y) / RES) + 1


def _joined(edt, nx, ny, cells) -> frozenset:
    """Which of *cells* a player can walk between (cells at least
    :data:`_BODY` from an obstacle, 8-connected), as a partition: a set of
    frozensets of cell indices.  A cell not walkable is its own group."""
    ok = lambda i, j: 0 < i <= nx and 0 < j <= ny and edt[i][j] >= _BODY  # noqa: E731
    groups = []
    done: set[int] = set()
    for n, start in enumerate(cells):
        if n in done:
            continue
        seen = {start}
        todo = [start] if ok(*start) else []
        while todo:
            i, j = todo.pop()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    q = (i + di, j + dj)
                    if q not in seen and ok(*q):
                        seen.add(q)
                        todo.append(q)
        members = frozenset(m for m, c in enumerate(cells) if c in seen)
        done |= members
        groups.append(members)
    return frozenset(groups)


def _hug_groups(bp, room, placer: RoomPlacer, rng: random.Random, names, *, ident: str, most: int,
                first: int = 0, gap: float = 80.0) -> list[Vignette]:
    """Small clutter groups in the gaps next to what already stands, where
    a centred patch is too narrow: each at a cell 4-40 units clearer than
    its own half-diagonal (so it sits beside a group, not in the middle of a
    lane), *gap* apart, and only if every doorway's approach and every
    other walkable region the room had stays joined for a player (checked
    on the 16-unit raster).  Returns the placed records."""
    from .indoor import door_lanes

    b = room.interior
    h = b.maxs.z - room.floor_z
    obstacles = list(_obstacles(bp, room, placer))
    edt, nx, ny = _grid(room, obstacles)
    targets = []
    for lane in door_lanes(room):
        c = _cell(room, lane.centre.x, lane.centre.y)
        if 0 < c[0] <= nx and 0 < c[1] <= ny:
            targets.append(c)
    # interactives and station points count too: nothing may cut a way to them
    for x0, y0, x1, y1, _z0, _z1 in bp.interactive_keep_clear():
        c = _cell(room, (x0 + x1) / 2.0, (y0 + y1) / 2.0)
        if 0 < c[0] <= nx and 0 < c[1] <= ny:
            targets.append(c)
    if len(targets) < 2:
        return []
    joined = _joined(edt, nx, ny, targets)
    small = [n for n in names if max(CLUTTER_KINDS[n].needs) <= 86.0] or list(names)
    placed: list[Vignette] = []
    cand = [(i, j) for i in range(1, nx + 1) for j in range(1, ny + 1)]
    rng.shuffle(cand)
    for i, j in cand:
        if len(placed) >= most:
            break
        x, y = b.mins.x + (i - 0.5) * RES, b.mins.y + (j - 0.5) * RES
        if any(math.hypot(x - v.focus[0], y - v.focus[1]) < gap for v in placed):
            continue
        name = min(small, key=lambda n: sum(1 for v in placed if v.kind == n) + rng.random())
        k = CLUTTER_KINDS[name]
        w, d = k.needs
        half = math.hypot(w / 2, d / 2)
        r = edt[i][j]
        if not (half + 4.0 <= r <= half + 40.0):
            continue
        box = (x - half, y - half, x + half, y + half)
        e2, _, _ = _grid(room, obstacles + [box])
        # the way between doors and interactives stays as joined as it was
        if _joined(e2, nx, ny, targets) != joined:
            continue
        yaw = rng.choice((0.0, 90.0, 180.0, 270.0)) + rng.uniform(-15.0, 15.0)
        spot = IndoorSpot(x, y, room.floor_z, yaw, "floor", getattr(room, "id", "room"), width=w,
                          back=d / 2, reach=d / 2, height=h)
        made = place_vignette(bp, name, spot, rng, placer, ident=f"{ident}_{first + len(placed)}",
                              library=CLUTTER_KINDS, settle=(0, 0))
        if made is not None:
            placed.append(made)
            placer.reserve(getattr(room, "id", "room"), Bounds.between((box[0], box[1], room.floor_z),
                                                                       (box[2], box[3], room.floor_z + 64.0)))
            obstacles.append(box)
            edt = e2
    return placed
