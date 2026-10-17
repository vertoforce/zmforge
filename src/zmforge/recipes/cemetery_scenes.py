"""zm_cemetery: every area a scene.

The cemetery's look (reference: a Nuketown-style stock
map) rests on set pieces that pinch the paths, fire, embers and smoke,
overhead wires, real facades on the roofed rooms, weathered mixed stone, a
deeper skyline and stock-level density.  ``docs/map-design-method.md`` is
the method: each area gets a one-line story (:func:`declare_scenes`), the
story picks the set pieces (:func:`walk_scenes`, :func:`gate_scene`,
:func:`row_scene`), the fire and smoke (:func:`fires`), and the props at
three heights (:func:`fill`).  Shared pieces live in :mod:`zmforge.dressing`
(``facade``, ``backdrop``, ``burning``, ``layered``); only the story and the
spots are here.
"""

from __future__ import annotations

import math
import random
from typing import Mapping

from .. import progress
from ..dressing import FacadeStyle, burning, declare_scene, embers, facade, sheared_bar, smouldering
from ..dressing.fx import SMOULDER, place_fx
from ..dressing.outdoor import register_boxes
from ..spatial import Point
from . import cemetery_kit as kit

__all__ = ["SCENES", "declare_scenes", "facades", "walk_scenes", "gate_scene", "row_scene",
           "wires", "fires", "fill", "chapel_ruin"]

#: What happened in each area (docs/map-design-method.md section 1).
SCENES: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "gate": ("The last hearse came in too fast, hit the gate pier and burned out on the "
             "forecourt; the groundskeeper's leaf bonfire is still going by the wall.",
             ("fire", "smoke", "embers", "wreck")),
    "shed": ("The groundskeeper boarded himself into his shed with his tools; the boards "
             "held, he did not.", ("barricade", "body")),
    "hills": ("Fresh burials gone wrong: the day's graves stand open with the digger "
              "left mid-dig, a tree is down across the walk, the Harlow mausoleum has "
              "fallen in and the chapel is burning beyond.",
              ("fire", "smoke", "embers", "wreck")),
    "row": ("The row was desecrated: tombs pried open under work lights, a lamp-oil fire "
            "set among the old graves.", ("fire", "smoke", "wreck")),
    "vault": ("A desecrated vault: the niches were broken open and the bones thrown down.",
              ("body", "wreck")),
    "chapel": ("The burnt chapel: the candles caught the drapes during the last vigil; "
               "the pews are charred and the fire is still in the roof.",
               ("fire", "smoke", "embers", "wreck")),
    "crypt_stairs": ("The way down to the crypt, forced: the rail torn, bones kicked "
                     "down the steps.", ("body",)),
    "ossuary": ("The ossuary shelves were emptied onto the floor by whatever came up "
                "from below.", ("body", "wreck")),
    "tomb": ("The founder's tomb, opened from the inside.", ("body", "wreck")),
}


def declare_scenes(bp, zones) -> None:
    for key, (story, beats) in SCENES.items():
        declare_scene(bp, key, story, beats=beats)


# ---------------------------------------------------------------------------
# Facades: the roofed rooms seen over the low walls
# ---------------------------------------------------------------------------
FACADES = {
    "shed": FacadeStyle(skins=(kit.MOSS_BRICK, kit.WET_BRICK, kit.MOSS_BRICK), trim=kit.DARK_WET,
                        dark=kit.BLACK, roof=kit.PIER_STONE, roof_kind="gable", ridge="y",
                        pitch=0.75, buttress_every=150.0, window="square", window_width=36.0),
    "chapel": FacadeStyle(skins=(kit.WET_STONE, kit.MOSS_BRICK, kit.DARK_WET), trim=kit.TRIM,
                          dark=kit.BLACK, roof=kit.PIER_STONE, roof_kind="gable", ridge="x",
                          pitch=0.62, buttress_every=190.0, window="lancet", window_width=44.0),
    "vault": FacadeStyle(skins=(kit.DARK_WET, kit.WET_STONE), trim=kit.TRIM, dark=kit.BLACK,
                         roof=kit.PIER_STONE, roof_kind="parapet", buttress_every=130.0,
                         window=None),
}


def facades(bp, rooms, seed: str) -> dict:
    out = {}
    for key, style in FACADES.items():
        out[key] = facade(bp, rooms[key], style, seed=seed, ident=f"{key}_facade")
    return out


# ---------------------------------------------------------------------------
# Hanging things: a plate under each so the model rests on something (Z44)
# ---------------------------------------------------------------------------
LAMP = "p7_zm_der2_light_hurricane_lamp"


def _hang(d, area: str, group: str, model: str, x: float, y: float, z_top: float, drop: float,
          ident: str, yaw: float = 0.0) -> None:
    """*model* hung *drop* below *z_top* on a chain, standing on its hook
    plate (floats on purpose: it hangs)."""
    from ..blueprint.elements import FLOATS_ON_PURPOSE

    base = z_top - drop
    kit._box(d.bp, x - 0.6, y - 0.6, base + 26.0, x + 0.6, y + 0.6, z_top, kit.IRON,
             f"{ident}_chain", note=FLOATS_ON_PURPOSE)
    kit._box(d.bp, x - 7.5, y - 7.5, base - 1.0, x + 7.5, y + 7.5, base, kit.IRON,
             f"{ident}_plate", note=FLOATS_ON_PURPOSE)
    d.prop(area, group, model, x, y, yaw, surface=base, check=False, solid=False)


def _sag(d, ident: str, a: tuple[float, float, float], b: tuple[float, float, float], *,
         sag: float = 18.0, pieces: int = 4) -> list[tuple[float, float, float]]:
    """A cable from *a* to *b* sagging *sag* at the middle, as straight
    pieces; returns the joints."""
    pts = []
    for k in range(pieces + 1):
        t = k / pieces
        pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                    a[2] + (b[2] - a[2]) * t - sag * 4.0 * t * (1.0 - t)))
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        lo, hi = (p, q) if p[2] <= q[2] else (q, p)
        if hi[2] - lo[2] < 0.5:
            hi = (hi[0], hi[1], lo[2] + 0.5)
        _flat_cable(d, f"{ident}_{k}", lo, hi)
    return pts


def _flat_cable(d, ident, lo, hi) -> None:
    """One cable piece: a thin box when it runs nearly flat along an axis,
    else a sheared bar."""
    from ..blueprint.elements import FLOATS_ON_PURPOSE

    if abs(hi[2] - lo[2]) < 3.0 and (abs(hi[0] - lo[0]) < 1.0 or abs(hi[1] - lo[1]) < 1.0):
        z = (lo[2] + hi[2]) / 2.0
        kit._box(d.bp, min(lo[0], hi[0]) - 0.6, min(lo[1], hi[1]) - 0.6, z - 0.6,
                 max(lo[0], hi[0]) + 0.6, max(lo[1], hi[1]) + 0.6, z + 0.6, kit.BLACK, ident,
                 note=FLOATS_ON_PURPOSE)
        return
    sheared_bar(d.bp, ident, lo, hi, 0.7, kit.BLACK)


def _pole(d, x: float, y: float, height: float, ident: str, *, crossbar: bool = True) -> float:
    """A creosoted wooden pole with a crossarm; returns its top."""
    g = d.ground(x, y)
    kit._box(d.bp, x - 4, y - 4, g - kit.BURY, x + 4, y + 4, g + height, kit.WOOD, f"{ident}_pole")
    if crossbar:
        kit._box(d.bp, x - 22, y - 2.5, g + height - 18, x + 22, y + 2.5, g + height - 12, kit.WOOD,
                 f"{ident}_arm")
    d.keep_disc(x, y, 12.0)
    return g + height


def wires(d, rooms) -> dict:
    """Work-light cables strung over the hills walk and the row walk from
    poles on alternate sides, lanterns hung under them (the overhead layer:
    stock puts 113 props per k2 over 160 units)."""
    laid = {"poles": 0, "lamps": 0}
    runs = (("gate", 0.0, 88.0, (-1420.0, -1130.0, -870.0)),
            ("hills", 0.0, 88.0, (-700.0, -420.0, -120.0, 190.0, 480.0, 760.0, 1100.0)),
            ("row", 1250.0, 64.0, (-640.0, -330.0, -20.0, 300.0, 620.0, 960.0)))
    for area, cy, hw, xs in runs:
        tops = []
        for n, x in enumerate(xs):
            side = 1.0 if n % 2 else -1.0
            y = cy + side * (hw + 58.0)
            for shift in (0.0, 24.0, -24.0, 48.0, -48.0):
                if d.free(x + shift, y, 6, 6, pad=2.0):
                    top = _pole(d, x + shift, y, 250.0, f"wire_{area}_{n}")
                    tops.append((x + shift, y, top - 14.0))
                    laid["poles"] += 1
                    break
        for n, (a, b) in enumerate(zip(tops, tops[1:])):
            pts = _sag(d, f"wire_{area}_{n}_cable", a, b, sag=26.0)
            for k in (1, 3):
                x, y, z = pts[k]
                _hang(d, area, "overhead", LAMP, x, y, z, 58.0, f"wire_{area}_{n}_lamp{k}",
                      yaw=(n * 53 + k * 31) % 360)
                laid["lamps"] += 1
    return laid


# ---------------------------------------------------------------------------
# The hero walk: set pieces that pinch it
# ---------------------------------------------------------------------------
HEARSE = "veh_t7_city_car_static_dead"
DIGGER = "zmf_prop_tractor"
GENERATOR = "p7_generator_large_01_housing_rusted"


def _open_grave(d, x: float, y: float, *, ident: str, yaw_x: bool = True) -> None:
    """A fresh grave dug in the lawn: a dark pit, a rim of wet spoil round
    it, planks across one end and the coffin still on its straps."""
    g = d.low(x - 50, y - 30, x + 50, y + 30)
    hx, hy = (40.0, 18.0) if yaw_x else (18.0, 40.0)
    kit._box(d.bp, x - hx, y - hy, g - 2.0, x + hx, y + hy, g + 0.8, kit.BLACK, f"{ident}_pit")
    for k, (a, b, c, e, h) in enumerate(((-hx - 10, -hy - 10, hx + 10, -hy, 6.0),
                                         (-hx - 10, hy, hx + 10, hy + 10, 6.0),
                                         (-hx - 10, -hy, -hx, hy, 5.0),
                                         (hx, -hy, hx + 10, hy, 5.0))):
        kit._box(d.bp, x + a, y + b, g - kit.BURY, x + c, y + e, g + h, kit.MUD, f"{ident}_rim{k}")
    # The spoil heap beside it, three tiers of mud.
    sx, sy = (x, y + hy + 40.0) if yaw_x else (x + hx + 40.0, y)
    gs = d.low(sx - 50, sy - 30, sx + 50, sy + 30)
    for k, (w, dd, h) in enumerate(((52, 28, 12), (40, 20, 22), (24, 12, 30))):
        if yaw_x:
            kit._box(d.bp, sx - w, sy - dd, gs - kit.BURY, sx + w, sy + dd, gs + h, kit.MUD,
                     f"{ident}_spoil{k}")
        else:
            kit._box(d.bp, sx - dd, sy - w, gs - kit.BURY, sx + dd, sy + w, gs + h, kit.MUD,
                     f"{ident}_spoil{k}")
    # Planks across the near end and the coffin on them.
    for k in range(3):
        o = -hx + 8 + 9 * k
        if yaw_x:
            kit._box(d.bp, x + o, y - hy - 8, g + 0.8, x + o + 6, y + hy + 8, g + 2.8, kit.WOOD,
                     f"{ident}_plank{k}")
        else:
            kit._box(d.bp, x - hx - 8, y + o, g + 0.8, x + hx + 8, y + o + 6, g + 2.8, kit.WOOD,
                     f"{ident}_plank{k}")
    d.keep(x - hx - 12, y - hy - 12, x + hx + 12, y + hy + 12)
    d.keep(sx - 56, sy - 56, sx + 56, sy + 56)


def _coffin(d, x: float, y: float, *, ident: str, open_lid: bool = True) -> None:
    g = d.low(x - 40, y - 14, x + 40, y + 14)
    kit._box(d.bp, x - 38, y - 12, g, x + 38, y + 12, g + 16, kit.WOOD, f"{ident}_box")
    if open_lid:
        sheared_bar(d.bp, f"{ident}_lid", (x - 36, y + 18, g), (x - 36, y + 26, g + 22), 1.5, kit.WOOD,
                    half_y=12.0, note="coffin lid leaning")
        kit._box(d.bp, x - 36, y + 14, g, x + 36, y + 28, g + 2, kit.WOOD, f"{ident}_lidfoot")
    d.keep(x - 44, y - 18, x + 44, y + 32)


def _digger(d, x: float, y: float, *, ident: str, reach_to: tuple[float, float]) -> None:
    """The small digger, all brushes seated on the ground under each part
    (the kit tractor sank 20 units into this slope): two tracks, the body,
    a cab with dark glass, a counterweight, and a backhoe arm reaching over
    the grave it was digging."""
    for k, dy in enumerate((-30.0, 30.0)):
        lo = d.low(x - 50, y + dy - 11, x + 50, y + dy + 11)
        kit._box(d.bp, x - 50, y + dy - 11, lo - kit.BURY, x + 50, y + dy + 11, lo + 18, kit.BLACK,
                 f"{ident}_track{k}")
    g = d.low(x - 50, y - 41, x + 50, y + 41)
    kit._box(d.bp, x - 44, y - 34, g + 18, x + 40, y + 34, g + 52, kit.IRON, f"{ident}_body")
    kit._box(d.bp, x - 40, y - 30, g + 52, x - 2, y + 22, g + 104, kit.IRON, f"{ident}_cab")
    kit._box(d.bp, x - 38, y - 31, g + 64, x - 4, y + 23, g + 96, kit.BLACK, f"{ident}_glass")
    kit._box(d.bp, x - 42, y - 32, g + 104, x, y + 24, g + 108, kit.IRON, f"{ident}_roof")
    kit._box(d.bp, x + 22, y - 30, g + 52, x + 40, y + 30, g + 70, kit.BLACK, f"{ident}_weight")
    d.keep(x - 56, y - 46, x + 56, y + 46)
    bx, by = x + 40.0, y
    tx, ty = reach_to
    gt = d.ground(tx, ty)
    elbow = ((bx + tx) / 2.0, (by + ty) / 2.0, max(g, gt) + 150.0)
    sheared_bar(d.bp, f"{ident}_boom", (bx, by, g + 70.0), elbow, 5.0, kit.IRON)
    sheared_bar(d.bp, f"{ident}_stick", (tx, ty, gt + 24.0), elbow, 4.0, kit.IRON)
    kit._box(d.bp, tx - 14, ty - 12, gt + 2.0, tx + 14, ty + 12, gt + 24.0, kit.BLACK, f"{ident}_bucket",
             note="digger bucket resting in the spoil")


def _set_piece(d, area: str, model: str, x: float, y: float, yaw: float, scale: float = 1.0):
    """A set piece at exactly (x, y), placed over the walk keep-outs on
    purpose (it is there to pinch the walk), then kept clear of."""
    from .cemetery_dressing import _half

    d.prop(area, "setpiece", model, x, y, yaw, check=False, solid=True, scale=scale)
    hx, hy = _half(model, yaw, scale)
    d.keep(x - hx - 6, y - hy - 6, x + hx + 6, y + hy + 6)
    return x, y


def _hearse(d, x: float, y: float, yaw: float) -> None:
    _set_piece(d, "hills", HEARSE, x, y, yaw, scale=1.2)


def _collapsed_mausoleum(d, x: float, y: float, *, ident: str) -> list[tuple[float, float]]:
    """The Harlow mausoleum, fallen in: three broken wall stubs, a roof slab
    slid off onto the lawn, toppled columns and rubble spilling toward the
    walk.  Returns fire spots inside the ruin."""
    g = d.low(x - 90, y - 70, x + 90, y + 70)
    W = kit.MOSS_BRICK
    kit._box(d.bp, x - 90, y - 70, g - kit.BURY, x + 90, y + 70, g + 8, kit.DARK_WET, f"{ident}_floor")
    # Back wall, broken to two heights; side walls stepped down toward the walk.
    kit._box(d.bp, x - 84, y + 52, g, x - 10, y + 68, g + 150, W, f"{ident}_back0")
    kit._box(d.bp, x - 10, y + 52, g, x + 84, y + 68, g + 96, W, f"{ident}_back1")
    for s, sx in enumerate((x - 84, x + 68)):
        for k, (y0, y1, h) in enumerate(((y + 10, y + 52, 132), (y - 30, y + 10, 84), (y - 56, y - 30, 34))):
            kit._box(d.bp, sx, y0, g, sx + 16, y1, g + h - (18 if s else 0), W if k % 2 else kit.WET_STONE,
                     f"{ident}_side{s}_{k}")
    # The roof slab slid off to the east, one edge on the wall stub, one on the grass.
    sheared_bar(d.bp, f"{ident}_roof", (x + 150, y + 10, g), (x + 88, y + 10, g + 84), 10.0, kit.PIER_STONE,
                half_y=66.0, note="fallen roof slab")
    kit._box(d.bp, x + 84, y + 60, g + 76, x + 96, y + 76, g + 84, kit.TRIM, f"{ident}_roofcorner")
    # Toppled columns and the pediment on the ground.
    sheared_bar(d.bp, f"{ident}_column0", (x - 60, y - 70, g), (x - 20, y - 96, g + 12), 7.0, kit.STONE)
    kit._box(d.bp, x - 10, y - 100, g, x + 60, y - 86, g + 14, kit.STONE, f"{ident}_column1")
    kit._box(d.bp, x + 20, y - 76, g, x + 70, y - 60, g + 24, kit.TRIM, f"{ident}_pediment")
    kit._box(d.bp, x - 44, y + 30, g + 8, x + 30, y + 50, g + 30, kit.STONE, f"{ident}_sarcophagus")
    d.keep(x - 94, y - 104, x + 156, y + 80)
    return [(x - 20, y + 10), (x + 120, y - 30)]


def walk_scenes(d, rooms) -> dict:
    """The hills walk (176 wide, 2,000 long), which read as wide and
    empty: a hearse slewed across its north half, the Harlow mausoleum
    fallen in beside it, open graves with their spoil and the digger on the
    south side.  Lanes stay at least 100 wide (P3, N5)."""
    register_boxes()
    out: dict = {"fires": [], "smoulder": []}
    _hearse(d, 150.0, 38.0, 14.0)
    out["fires"].append((150.0, 70.0, "hearse"))
    ruin = _collapsed_mausoleum(d, 560.0, 190.0, ident="harlow_ruin")
    out["smoulder"] += ruin
    # The day's burials, south of the walk under the Founder's hill.  The
    # quest's soul graves (cemetery_quest, SoulBox): each pit's centre on
    # the ground _open_grave levels it to.
    out["graves"] = []
    for n, (gx, gy) in enumerate(((720.0, -170.0), (860.0, -170.0))):
        out["graves"].append(Point(gx, gy, d.low(gx - 50, gy - 30, gx + 50, gy + 30)))
        _open_grave(d, gx, gy, ident=f"fresh_grave{n}", yaw_x=False)
    _coffin(d, 990.0, -150.0, ident="fresh_coffin0")
    _digger(d, 760.0, -300.0, ident="digger", reach_to=(720.0, -210.0))
    out["digger"] = (760.0, -300.0)
    return out


def gate_scene(d, rooms) -> dict:
    """The burnt-out hearse on the forecourt and the leaf bonfire by the wall."""
    at = _set_piece(d, "gate", HEARSE, -1340.0, -330.0, 152.0, scale=1.2)
    return {"fires": [(at[0], at[1], "hearse"), (-1700.0, -560.0, "bonfire")]}


def row_scene(d, rooms) -> dict:
    """The work lights' generator between the tombs, its cable run to the
    poles, and the opened tomb."""
    at = _set_piece(d, "row", GENERATOR, -420.0, 1636.0, 90.0, scale=0.6)
    return {"fires": [(-120.0, 1560.0, "tomb fire")], "generator": at}


# ---------------------------------------------------------------------------
# Fire, embers and smoke as light pools with dark gaps between
# ---------------------------------------------------------------------------
def fires(d, spots, *, facade_windows=(), chapel=None) -> dict:
    """Light the story's fires: each ``(x, y, note)`` in *spots* burns with
    embers, smoke over and a warm pool; ``smoulder`` spots only smoke.  The
    chapel burns in its west windows and inside; a black plume stands over
    its roof for the skyline."""
    from ..dressing.outdoor import light_pool_points

    placed = {"fire": 0, "smoulder": 0, "window": 0}
    lit = light_pool_points([(x, y) for x, y, _ in spots["fires"]], 300.0, dark_gap=0.3)
    for x, y, note in spots["fires"]:
        g = d.ground(x, y)
        burning(d.bp, Point(x, y, g + 4.0), light=(x, y) in lit, radius=300.0, note=note)
        placed["fire"] += 1
    for x, y in spots["smoulder"]:
        smouldering(d.bp, Point(x, y, d.ground(x, y) + 4.0))
        embers(d.bp, Point(x + 12.0, y - 8.0, d.ground(x, y) + 10.0))
        placed["smoulder"] += 1
    for n, (x, y, z, _side) in enumerate(facade_windows):
        place_fx(d.bp, Point(x, y, z - 20.0), "fire/fx_fire_window_embers_50x100", yaw=0.0,
                 pitch=0.0, note="chapel window fire")
        if n % 2 == 0:
            # The pool falls on the grass in front (the pane itself is in the wall).
            lx, ly = _out_from(chapel, x, y, 40.0) if chapel is not None else (x, y)
            d.bp.place_light(Point(lx, ly, z - 30.0), colour=(1.0, 0.45, 0.2), radius=260.0,
                             shadows=False)
        placed["window"] += 1
    if chapel is not None:
        o = chapel.outer
        place_fx(d.bp, Point((o.mins.x + o.maxs.x) / 2.0, (o.mins.y + o.maxs.y) / 2.0, o.maxs.z + 120.0),
                 SMOULDER["plume"], note="chapel roof plume")
    return placed


def _out_from(room, x: float, y: float, dist: float) -> tuple[float, float]:
    """(x, y) moved *dist* further out from *room*'s nearest outer face."""
    o = room.outer
    gaps = {(-1, 0): abs(x - o.mins.x), (1, 0): abs(x - o.maxs.x), (0, -1): abs(y - o.mins.y),
            (0, 1): abs(y - o.maxs.y)}
    dx, dy = min(gaps, key=gaps.get)
    return x + dx * dist, y + dy * dist


def shed_remains(d, rooms) -> int:
    """What is left of the groundskeeper: bones in the corner behind his
    boarded door (the shed's ``body`` beat)."""
    inside = rooms["shed"].interior
    rng = random.Random(f"{d.seed}:shed_remains")
    placed = 0
    for _ in range(600):
        if placed >= 7:
            break
        x = rng.uniform(inside.mins.x + 24, inside.maxs.x - 24)
        y = rng.uniform(inside.mins.y + 24, inside.maxs.y - 24)
        m = rng.choice(("p7_gib_chunk_bone_01", "p7_gib_chunk_bone_03", "p7_gib_chunk_meat_01"))
        if d.free(x, y, 3.0, 3.0, pad=2.0) and d.prop("shed", "remains", m, x, y,
                                                        rng.uniform(0, 360), surface=inside.mins.z,
                                                        check=False, solid=False):
            placed += 1
    return placed


def chapel_ruin(d, rooms) -> int:
    """The burnt chapel's floor: charred boards, burnt hymn books, fallen
    plaster and brick at the wall feet and round the pews, fires in two
    pews' ends with smoke under the roof."""
    room = rooms["chapel"]
    inside = room.interior
    rng = random.Random(f"{d.seed}:chapel_ruin")
    floor = inside.mins.z
    burnt = ("p7_debris_wood_board_cluster_burn_01", "p7_book_vintage_01_burn",
             "p7_book_vintage_open_02_burn", "p7_book_vintage_03_burn",
             "p7_book_vintage_02_burn", "p7_book_vintage_05_burn", "p7_book_vintage_open_04_burn",
             "p7_debris_wood_board_2pc_2x4x128_lt_burn", "p7_debris_plaster_rubble_med_01",
             "p7_debris_brick_chunk_hlf_01", "p7_debris_concrete_rubble_sm_02",
             "p7_brick_dirty_01", "p7_debris_brick_single_01")
    placed = 0
    for _ in range(4000):
        if placed >= 320:
            break
        m = rng.choice(burnt)
        x = rng.uniform(inside.mins.x + 30, inside.maxs.x - 30)
        y = rng.uniform(inside.mins.y + 30, inside.maxs.y - 30)
        # Drifts at the walls and under the windows, not an even spread.
        edge = min(x - inside.mins.x, inside.maxs.x - x, y - inside.mins.y, inside.maxs.y - y)
        # Drifts at the wall feet only, never confetti.
        if edge > 120:
            continue
        yaw = rng.uniform(0, 360)
        from .cemetery_dressing import _half

        if d.clear(x, y, max(6.0, *_half(m, yaw))) and d.prop("chapel", "ruin", m, x, y, yaw,
                                                             surface=floor, check=False, solid=False):
            placed += 1
    for n, (fx_, fy_) in enumerate(((inside.mins.x + 160, inside.mins.y + 120),
                                    (inside.maxs.x - 220, inside.maxs.y - 140))):
        burning(d.bp, Point(fx_, fy_, floor + 4.0), radius=280.0, note=f"chapel fire {n}")
    smouldering(d.bp, Point((inside.mins.x + inside.maxs.x) / 2.0, 0.0, floor + 4.0))
    return placed


# ---------------------------------------------------------------------------
# Density at three heights
# ---------------------------------------------------------------------------
#: The ground layer (walk-through: dry grass, weeds, leaves, stones,
#: bones): the fringe of every clump and the whole of a bare patch.
GROUND = (
    # (p7_foliage_grass_dry_* fail the link on missing grass images, corn
    # maze build: only models this map has linked before.)
    ("p7_foliage_grass_tall_single_sml", (0.6, 1.0), 6),
    ("p7_foliage_grass_tall_cluster_sml", (0.6, 1.0), 6),
    ("p7_foliage_weed_cluster_med", (1.5, 2.5), 4),
    ("p7_foliage_plant_meskel_3_noflower", (0.7, 1.1), 3),
    ("p7_foliage_grass_tall_cluster_sml", (0.8, 1.3), 5),
    ("p7_boulder_rock_05", (1.5, 3.0), 2),
    ("p7_gib_chunk_bone_01", (1.0, 1.6), 1),
    ("p7_gib_chunk_bone_03", (1.0, 1.6), 1),
    ("p7_3arc_park_leaves_grp_2", (0.9, 1.3), 2),
)
#: An even scatter reads as artificial, and bushes grow next to each
#: other, so the fill grows in mixed
#: clumps, a big core (a box hedge, a bush, a tall bush or a wheelbarrow
#: left in the grass), a ring of smaller bushes and tall grass round it and
#: a fringe of the ground layer, drawn toward the feet of things.
CORE = (
    ("p7_foliage_hedge_box_48_48_36", (1.0, 1.0), 8),
    ("p7_foliage_tree_acacia_bush", (0.75, 0.9), 6),
    ("p7_foliage_tree_acacia_bush", (1.6, 2.2), 1),
    ("p7_wheel_barrow_street_vendor", (1.0, 1.0), 1),
)
RING = (
    ("p7_foliage_grass_tall_cluster_med", (1.0, 1.4), 3),
    ("p7_foliage_tree_acacia_bush", (0.55, 0.8), 3),
    ("p7_foliage_plant_meskel_3_noflower", (1.1, 1.5), 2),
    ("p7_foliage_weed_cluster_med", (2.0, 2.8), 2),
)
#: The share of each area's fill laid as grass-and-stone patches with no
#: core (the rest: a core, one to three ring pieces 50-100 out, four to ten
#: ground pieces 35-150 out).
PATCH_SHARE = 0.15
#: The share laid as clumps along the walks' kerbs.
KERB_SHARE = 0.3


def fill(d, rooms, targets: Mapping[str, tuple[int, int, int]]) -> dict:
    """Fill the open areas toward the stock density at three heights, in
    mixed clumps with bare ground between (:func:`dressing.cluster.mixed_clumps`),
    keeping off everything claimed.  Each area's ``(ground, waist, tall)``
    target is laid as one clump per waist or tall piece, then grass-and-
    stone patches with no core for what is left of the count."""
    from ..dressing.cluster import Tier, mixed_clumps
    from ..recipes.props import is_solid
    from .cemetery_dressing import _half, shelter_edges

    register_boxes()
    walk_through = {m for m, _s, _w in GROUND}
    ring = {m for m, _s, _w in RING}
    # Full clumps, because thin ones leave the foreground bare: a core,
    # three to six ring pieces packed round it, ten to twenty-two fringe pieces; the same total, fewer and fuller
    # clumps, and the ring crowds in as walk-through cover.
    clump = (Tier(CORE, (1, 1), (0.0, 6.0)), Tier(RING, (3, 6), (30.0, 85.0)),
             Tier(GROUND, (10, 22), (25.0, 130.0)))
    patch = (Tier(RING, (1, 2), (0.0, 40.0)), Tier(GROUND, (12, 28), (0.0, 100.0)))
    placed = {}
    for done, (area, (ground, waist, tall)) in enumerate(targets.items(), 1):
        progress.stage(f"filling the grounds {done}/{len(targets)} ({area})")
        inside = rooms[area].interior
        rng = random.Random(f"{d.seed}:fill:{area}")
        rect = (inside.mins.x + 50, inside.mins.y + 50, inside.maxs.x - 50, inside.maxs.y - 50)
        edges = shelter_edges(d, rect)

        def place(model, x, y, yaw, scale, area=area):
            if model in ring and model not in walk_through:
                # A ring piece is scaled, so never solid (Z21): it may crowd
                # the core and its neighbours like the ground layer, moved
                # into one terrain cell first (Z44).
                hx, hy = _half(model, yaw, scale)
                x, y = d.into_cell(x, y, max(hx, hy))
                return d.clear(x, y, max(hx, hy)) and d.prop(
                    area, "fill", model, x, y, yaw, scale=scale, check=False, solid=False)
            if model in walk_through:
                # Ankle-high cover is walked through: it keeps off the ways,
                # the blocks and the kit (d.clear, by its own size), not off
                # other cover.
                hx, hy = _half(model, yaw, scale)
                return d.clear(x, y, max(hx, hy)) and d.prop(
                    area, "fill", model, x, y, yaw, scale=scale, check=False, solid=False)
            # a solid prop's collmap is its unscaled box (Z21): scaled pieces
            # (the ring's small bushes, the tall bushes) are walked through
            solid = (is_solid(model) and scale == 1.0
                     and model != "p7_foliage_grass_tall_cluster_med")
            # snapped into one terrain cell (Z44), as the shrubs are: unsnapped,
            # few bushes fit (a 48-82 wide footprint in an 82-unit cell)
            return d.prop(area, "fill", model, x, y, yaw, scale=scale, solid=solid, snap=True)

        total = ground + waist + tall
        # A share of the clumps lines the walks' kerbs, with gaps: the walks
        # are what a player looks along, and a uniform draw can leave the
        # near verge of a walk bare.
        from .cemetery import path_boxes
        from ..dressing.cluster import rect_edges

        kerbs = [e for _r, a, b, c, f in path_boxes().values()
                 if a < rect[2] and c > rect[0] and b < rect[3] and f > rect[1]
                 for e in rect_edges(a, b, c, f)]
        verge = mixed_clumps(rng, rect, clump, int(total * KERB_SHARE), place=place,
                             edges=kerbs, edge_bias=0.97, edge_reach=50.0, edge_offset=45.0,
                             parent_gap=170.0) if kerbs else []
        cores = verge + mixed_clumps(rng, rect, clump, int(total * (1.0 - PATCH_SHARE)) - len(verge),
                                     place=place, edges=edges, edge_offset=40.0, parent_gap=200.0)
        patches = mixed_clumps(rng, rect, patch, total - len(cores), place=place,
                               edges=edges, edge_offset=30.0, parent_gap=220.0)
        placed[area] = len(cores) + len(patches)
    return placed


def pier_tops(d, rooms, *, every: int = 3) -> int:
    """Lanterns and jack-o'-lanterns on every *every*-th boundary pier cap
    (the mid and overhead layers along the walls)."""
    from ..blueprint.elements import Massing

    from ..blueprint.model import _solid_bounds

    n = 0
    k = 0
    ids = {m.id for m in d.bp.elements(Massing)}
    raised = [_solid_bounds(m.solids[0]) for m in d.bp.elements(Massing)
              if "_bwall_" in m.id and ("_raised" in m.id or "_rail" in m.id or "_spear" in m.id)]
    for m in list(d.bp.elements(Massing)):
        if "_bwall_" not in m.id or "_piercap" not in m.id:
            continue
        if m.id.replace("_piercap", "_finial") in ids:
            continue
        k += 1
        if k % every:
            continue
        b = _solid_bounds(m.solids[0])
        area = m.id.split("_")[0]
        if area not in ("gate", "hills", "row"):
            continue
        inside = rooms[area].interior
        if any(r.maxs.x > b.mins.x - 4 and r.mins.x < b.maxs.x + 4 and r.maxs.y > b.mins.y - 4
               and r.mins.y < b.maxs.y + 4 for r in raised):
            continue
        x, y = (b.mins.x + b.maxs.x) / 2.0, (b.mins.y + b.maxs.y) / 2.0
        # Onto the cap's inner half, over the room's side of the wall.
        if b.mins.y < inside.mins.y < b.maxs.y or b.mins.y < inside.maxs.y < b.maxs.y:
            y = inside.mins.y + 7.0 if abs(y - inside.mins.y) < abs(y - inside.maxs.y) else inside.maxs.y - 7.0
        elif b.mins.x < inside.mins.x < b.maxs.x or b.mins.x < inside.maxs.x < b.maxs.x:
            x = inside.mins.x + 7.0 if abs(x - inside.mins.x) < abs(x - inside.maxs.x) else inside.maxs.x - 7.0
        else:
            continue
        model = LAMP if k % 2 else kit_jack(k)
        # Each model keeps its own collision flag (a kit prop meant solid
        # must not be placed with no_collmap, Z21).
        d.prop(area, "piertop", model, x, y, (k * 37) % 360, surface=b.maxs.z, check=False)
        n += 1
    return n


def kit_jack(k: int) -> str:
    from .cemetery_dressing import JACK, JACK_TALL

    return JACK_TALL if k % 3 == 0 else JACK
