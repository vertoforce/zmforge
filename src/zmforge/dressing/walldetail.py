"""Wall and ceiling detail: the trim, structure and services that make a box read as a building.

A generated room left bare has walls of one flat material from floor to
ceiling, with no skirting, rail, panelling, columns, beams or ducts; measured
on a test map, the overhead layer came to 0 to 23 props per k2 against stock's
113, and 0.3 to 0.8 wall-mounted things per 100 units of wall.  A stock room is never
that: a real wall has a skirting board, a dado rail with a harder-wearing
material under it, columns where the structure comes down, and the ceiling
carries beams, ducts, cable trays, pipes and the lights hung off them.

:func:`dress_walls` adds all of that to one roofed room from a
:class:`WallTheme` (:data:`THEMES` has ``lab``, ``office``, ``clinic``,
``institution`` and ``plant``), and returns a :class:`WallReport` with the
counts the ``S`` checks read (overhead props per k2, wall- and
ceiling-mounted props per 100 units of wall).  The defaults are sized to
clear the checks' bars: overhead at least 60 per k2 and wall-mounted at
least 1.5 per 100 units of wall in a room of 0.5 k2 or more.

What it keeps clear, measured off the blueprint so a recipe need not list it:
every opening in the room's walls (doorways, windows, slots) and 8 units
past each jamb; every interactive's keep-clear (wall buys, perks, the box);
brushes already on the wall (lettering, signs, station plates); props
already mounted on or standing against it; props already on the ceiling
(a beam never swallows a lamp); and any keep-out boxes the recipe passes.
Columns (pilasters) and corner pipe risers also stay off every doorway's
96-unit approach lane and off the floor next to standing furniture, so no
new pinch point opens between a column and a couch.

Brushes are detail brushes with ids ``<ident>_*``.  Units are map units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..blueprint.elements import FLOATS_ON_PURPOSE, Massing
from ..materials import Material
from ..spatial import Bounds, Facing, Point

__all__ = ["WallTheme", "WallReport", "THEMES", "dress_walls", "wall_runs", "wall_boards", "ATTACHED"]

#: Room faces: name, the axis the wall runs along, which end of the other
#: axis it is on, and the way a thing mounted on it looks.
_SIDES = (("south", "x", -1, Facing.NORTH), ("north", "x", +1, Facing.SOUTH),
          ("west", "y", -1, Facing.EAST), ("east", "y", +1, Facing.WEST))

#: Brush-built trim is recorded under this note (the S6 check reads it).
ATTACHED = "wall detail"

DUCT = "p7_duct_metal_circular_straight_32"
PIPE = "p7_pipe_metal_hp_4_straight_32_bare"
#: Head room a climbable solid prop may be capped with (verify.camping.CAP_HEIGHT).
_CAP = 48.0


@dataclass(frozen=True)
class WallTheme:
    """How one room's walls and ceiling are detailed.  ``None`` skips a part."""

    #: Wainscot under the rail (a harder-wearing lower wall).
    lower: Material | None = Material("t7_wood_panel_01", 64.0)
    #: A skin over the wall above the rail; ``None`` keeps the room's own wall.
    upper: Material | None = None
    trim: Material = Material("t7_plastic_molding_trim_white", 32.0)
    base: Material | None = Material("t7_plastic_rubber_trim", 32.0)
    dado: float = 44.0
    base_height: float = 6.0
    #: A crown/cornice band at the top of the wall.
    cornice: float = 8.0
    #: Columns standing proud of the wall every so many units.
    pilaster_every: float | None = 256.0
    pilaster_width: float = 20.0
    pilaster_depth: float = 6.0
    pilaster: Material = Material("t7_concrete_worn_painted_white", 64.0)
    #: Ceiling beams across the short span, every so many units.
    beam_every: float | None = 256.0
    beam_width: float = 12.0
    beam_depth: float = 16.0
    beam: Material = Material("t7_metal_frame_trim_01", 64.0)
    #: Round duct along the longest wall(s): how many walls carry one.
    ducts: int = 2
    #: Cable tray along a wall (brush channel on brackets): how many walls.
    trays: int = 1
    tray: Material = Material("t7_metal_black_trim_01", 16.0)
    #: Pipe risers in the room's corners (props stacked floor to ceiling).
    risers: int = 2
    #: Wall lamps between the columns, and lamps hung off each beam.
    sconce: str | None = "p7_zm_der_light_wall_mount"
    sconce_every: float = 160.0
    sconce_height: float = 150.0
    hanging: str | None = "p7_zm_der_light_shade"
    hanging_every: float = 192.0
    #: Fixtures flush on the ceiling between the beams, one per cell of a
    #: grid this many units wide (LED panels, now and then a dead one, track
    #: lights).  In a room 160-200 high they are the only props whose origin
    #: clears the 160 overhead line (the beam lamps hang under it: a test map's
    #: 160-high rooms stayed at 0-19 per k2 with beams alone).  ``None`` skips.
    ceiling_every: float | None = 100.0
    ceiling_models: tuple[str, ...] = (
        "p7_light_fixture_led_ceiling_01", "p7_light_fixture_led_ceiling_01",
        "p7_light_track_led_01_white", "p7_light_fixture_led_ceiling_01_dmg",
        "p7_light_fixture_led_ceiling_01", "p7_zm_der_light_cage_01")


#: Per-theme defaults (a recipe may ``dataclasses.replace`` any field).
THEMES: dict[str, WallTheme] = {
    "institution": WallTheme(),
    "office": WallTheme(lower=Material("t7_wood_veneer_sugarpine_matte", 64.0), pilaster_every=320.0,
                        ducts=2, trays=1, hanging="p7_zm_der_light_cage_01"),
    "lab": WallTheme(lower=Material("t7_ceramic_tiles_6x6_dirty_01", 48.0),
                     trim=Material("t7_metal_black_trim_01", 16.0),
                     pilaster=Material("t7_metal_panels_4x1", 64.0), ducts=2, trays=2,
                     hanging="p7_zm_der_light_cage_01"),
    "clinic": WallTheme(lower=Material("t7_ceramic_tile_shower_white", 48.0),
                        trim=Material("t7_plastic_rubber_trim", 32.0), dado=40.0, ducts=2, trays=1),
    "plant": WallTheme(lower=Material("t7_concrete_worn_painted_white", 128.0),
                       trim=Material("t7_metal_black_trim_01", 16.0), base=None, cornice=0.0,
                       pilaster=Material("t7_metal_worn_iron_dark", 64.0),
                       beam=Material("t7_metal_rust_ceiling_01", 96.0), ducts=2, trays=2, risers=3,
                       sconce="p7_zm_der_light_wall_mount", hanging="p7_zm_der_light_cage_01"),
}


@dataclass
class WallReport:
    """What :func:`dress_walls` added."""

    brushes: int = 0
    props: int = 0
    overhead: int = 0          # props whose origin is 160+ over the floor
    mounted: int = 0           # wall- or ceiling-mounted props
    wall_length: float = 0.0   # interior perimeter, units
    area_k2: float = 0.0
    parts: dict = field(default_factory=dict)

    def per_k2(self) -> float:
        return self.overhead / self.area_k2 if self.area_k2 else 0.0

    def per_100(self) -> float:
        return 100.0 * self.mounted / self.wall_length if self.wall_length else 0.0


# ---------------------------------------------------------------------------
# What is already on or against each wall
# ---------------------------------------------------------------------------
def _solid_box(solid) -> tuple[float, float, float, float, float, float]:
    pts = [p for f in solid.faces for p in f.points]
    return (min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
            max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))


def _occupied(bp, room, extra: Sequence[Bounds] = ()) -> list[tuple[float, ...]]:
    """World boxes ``(x0, y0, z0, x1, y1, z1)`` of everything in *room* a
    detail part must not run through: brushes, props, openings (8 past each
    jamb), interactive keep-clears and the caller's keep-outs."""
    from .place import _placed_props

    b = room.interior
    out: list[tuple[float, ...]] = []

    def inside(x0, y0, x1, y1) -> bool:
        return x1 >= b.mins.x - 2 and x0 <= b.maxs.x + 2 and y1 >= b.mins.y - 2 and y0 <= b.maxs.y + 2

    for m in bp.elements(Massing):
        for s in m.solids:
            box = _solid_box(s)
            if inside(box[0], box[1], box[3], box[4]) and box[5] > b.mins.z and box[2] < b.maxs.z:
                out.append(box)
    for _p, pl in _placed_props(bp):
        x0, y0, x1, y1 = pl.footprint.bounds
        if inside(x0, y0, x1, y1) and pl.z_high > b.mins.z and pl.z_low < b.maxs.z + 1:
            # a solid prop a player can climb may get an invisible cap
            # (verify.camping.clip_camping_tops, CAP_HEIGHT over its top)
            # after dressing: keep ducts and lamps off that too
            out.append((x0, y0, pl.z_low, x1, y1, pl.z_high + (_CAP if pl.solid else 0.0)))
    for box in room.aperture_boxes:
        out.append((box.mins.x - 8, box.mins.y - 8, box.mins.z - 2, box.maxs.x + 8, box.maxs.y + 8,
                    box.maxs.z + 2))
    for x0, y0, x1, y1, z0, z1 in bp.interactive_keep_clear():
        if inside(x0, y0, x1, y1) and z1 > b.mins.z - 8 and z0 < b.maxs.z:
            out.append((x0, y0, z0, x1, y1, z1))
    out += [(k.mins.x, k.mins.y, k.mins.z, k.maxs.x, k.maxs.y, k.maxs.z) for k in extra]
    return out


def _strip(room, side: str, depth: float) -> tuple[float, float, float, float]:
    """The plan strip *depth* deep inside *room* along wall *side*."""
    b = room.interior
    if side == "south":
        return b.mins.x, b.mins.y, b.maxs.x, b.mins.y + depth
    if side == "north":
        return b.mins.x, b.maxs.y - depth, b.maxs.x, b.maxs.y
    if side == "west":
        return b.mins.x, b.mins.y, b.mins.x + depth, b.maxs.y
    return b.maxs.x - depth, b.mins.y, b.maxs.x, b.maxs.y


def wall_runs(room, occupied: Sequence[tuple[float, ...]], side: str, z0: float, z1: float, *,
              depth: float = 8.0, cell: float = 8.0, min_run: float = 24.0) -> list[tuple[float, float]]:
    """Free stretches ``(a, b)`` along wall *side* of *room* for a band from
    *z0* to *z1* over the floor, *depth* out from the face: every cell no
    occupied box overlaps (in plan and in height), merged, runs shorter than
    *min_run* dropped."""
    b = room.interior
    f = room.floor_z
    sx0, sy0, sx1, sy1 = _strip(room, side, depth)
    along_x = side in ("south", "north")
    lo, hi = (b.mins.x, b.maxs.x) if along_x else (b.mins.y, b.maxs.y)
    hits: list[tuple[float, float]] = []
    for o in occupied:
        if o[3] <= sx0 or o[0] >= sx1 or o[4] <= sy0 or o[1] >= sy1:
            continue
        if o[5] <= f + z0 or o[2] >= f + z1:
            continue
        hits.append((o[0], o[3]) if along_x else (o[1], o[4]))
    n = max(1, int((hi - lo) / cell))
    free = []
    for i in range(n):
        a, c = lo + i * cell, lo + (i + 1) * cell
        free.append(not any(h0 < c and h1 > a for h0, h1 in hits))
    runs: list[tuple[float, float]] = []
    start = None
    for i, ok in enumerate(free + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            a, c = lo + start * cell, min(hi, lo + i * cell)
            if c - a >= min_run:
                runs.append((a, c))
            start = None
    return runs


def _band(room, side: str, a: float, c: float, z0: float, z1: float, depth: float) -> Bounds:
    b = room.interior
    f = room.floor_z
    if side == "south":
        return Bounds.between((a, b.mins.y, f + z0), (c, b.mins.y + depth, f + z1))
    if side == "north":
        return Bounds.between((a, b.maxs.y - depth, f + z0), (c, b.maxs.y, f + z1))
    if side == "west":
        return Bounds.between((b.mins.x, a, f + z0), (b.mins.x + depth, c, f + z1))
    return Bounds.between((b.maxs.x - depth, a, f + z0), (b.maxs.x, c, f + z1))


def _clear_floor(box: Bounds, occupied, lanes) -> bool:
    for o in list(occupied) + lanes:
        if o[0] < box.maxs.x and o[3] > box.mins.x and o[1] < box.maxs.y and o[4] > box.mins.y \
                and o[2] < box.maxs.z and o[5] > box.mins.z:
            return False
    return True


# ---------------------------------------------------------------------------
# The dresser
# ---------------------------------------------------------------------------
def dress_walls(bp, room, theme: WallTheme | str = "institution", *, ident: str,
                keepouts: Sequence[Bounds] = (), sides: Sequence[str] = ("south", "north", "west", "east"),
                ) -> WallReport:
    """Detail *room*'s walls and ceiling after *theme* (see the module
    docstring for what it keeps clear).  Call it **after** the room's own
    dressing, so it can step round what is there.  Returns a :class:`WallReport`."""
    from .indoor import door_lanes
    from .keepout import window_keepouts
    from .place import on_wall

    th = THEMES[theme] if isinstance(theme, str) else theme
    b = room.interior
    f = room.floor_z
    h = b.maxs.z - f
    occ = _occupied(bp, room, keepouts)
    lanes = [(k.mins.x, k.mins.y, k.mins.z, k.maxs.x, k.maxs.y, k.maxs.z)
             for k in list(door_lanes(room)) + list(window_keepouts(bp))]
    # What already hangs from the ceiling (before this adds its own ducts,
    # which run under the beams): a beam never swallows a lamp or a sign rod.
    ceiling = [o for o in occ if o[5] >= b.maxs.z - th.beam_depth - 2 and o[2] > f + 48]
    rep = WallReport(wall_length=2.0 * ((b.maxs.x - b.mins.x) + (b.maxs.y - b.mins.y)),
                     area_k2=(b.maxs.x - b.mins.x) * (b.maxs.y - b.mins.y) / 1e6)
    props: list[tuple] = []
    n = [0]

    def brush(box: Bounds, mat: Material, what: str, floats: bool = False) -> None:
        bp.add_block(box, mat, contents=("detail",), reachable=False, id=f"{ident}_{what}_{n[0]}",
                     note=FLOATS_ON_PURPOSE if floats else ATTACHED)
        n[0] += 1
        rep.brushes += 1
        rep.parts[what] = rep.parts.get(what, 0) + 1

    def prop(item: tuple, what: str, mount: bool) -> None:
        props.append(item)
        rep.props += 1
        rep.parts[what] = rep.parts.get(what, 0) + 1
        if item[1].z - f >= 160.0:
            rep.overhead += 1
        if mount:
            rep.mounted += 1

    # ---- horizontal bands: skirting, wainscot, rail, upper skin, cornice ----
    bands = []
    if th.base is not None:
        bands.append(("skirting", 0.0, th.base_height, 1.5, th.base))
    if th.lower is not None:
        bands.append(("wainscot", th.base_height if th.base is not None else 0.0, th.dado, 1.0, th.lower))
    bands.append(("rail", th.dado, th.dado + 3.0, 2.0, th.trim))
    if th.upper is not None:
        bands.append(("upper", th.dado + 3.0, h - max(th.cornice, 0.0), 0.5, th.upper))
    if th.cornice > 0:
        bands.append(("cornice", h - th.cornice, h, 3.0, th.trim))
    for side, _axis, _sign, _facing in _SIDES:
        if side not in sides:
            continue
        for what, z0, z1, depth, mat in bands:
            for a, c in wall_runs(room, occ, side, z0, z1, depth=depth + 0.5):
                brush(_band(room, side, a, c, z0, z1, depth), mat, what)
    # ---- pilasters: full-height columns every pilaster_every -------------
    columns: list[tuple[str, float]] = []
    if th.pilaster_every:
        for side, _axis, _sign, _facing in _SIDES:
            if side not in sides:
                continue
            runs = wall_runs(room, occ, side, 0.0, h, depth=th.pilaster_depth + 2.0)
            lo = b.mins.x if side in ("south", "north") else b.mins.y
            hi = b.maxs.x if side in ("south", "north") else b.maxs.y
            count = max(1, int((hi - lo) / th.pilaster_every))
            step = (hi - lo) / (count + 1)
            for k in range(1, count + 1):
                for nudge in (0.0, 32.0, -32.0, 64.0, -64.0):
                    t = lo + k * step + nudge
                    a, c = t - th.pilaster_width / 2, t + th.pilaster_width / 2
                    if not any(r0 <= a - 4 and c + 4 <= r1 for r0, r1 in runs):
                        continue
                    box = _band(room, side, a, c, 0.0, h, th.pilaster_depth)
                    # the floor beside it: no furniture within a player's width
                    apron = _band(room, side, a - 36, c + 36, 0.0, 72.0, th.pilaster_depth + 36)
                    if _clear_floor(apron, occ, lanes):
                        break
                else:
                    continue
                brush(box, th.pilaster, "pilaster")
                columns.append((side, t))
                occ.append((box.mins.x, box.mins.y, box.mins.z, box.maxs.x, box.maxs.y, box.maxs.z))
    # ---- wall lamps between the columns ----------------------------------
    if th.sconce:
        for side, _axis, _sign, facing in _SIDES:
            if side not in sides:
                continue
            z0, z1 = th.sconce_height - 12, th.sconce_height + 12
            for a, c in wall_runs(room, occ, side, z0, z1, depth=12.0):
                span = c - a
                k = int(span // th.sconce_every)
                for j in range(k):
                    t = a + (j + 0.5) * span / k
                    if any(s == side and abs(t - ct) < 48 for s, ct in columns):
                        continue
                    wall = {"south": b.mins.y, "north": b.maxs.y, "west": b.mins.x, "east": b.maxs.x}[side]
                    item = on_wall(th.sconce, facing, t, wall, centre_z=f + th.sconce_height)
                    prop((*item, 1.0, False), "sconce", True)
    # ---- pipe risers in the corners ----------------------------------------
    if th.risers:
        pieces = int(h // 32.0)
        corners = [(b.mins.x, b.mins.y, 1, 1), (b.maxs.x, b.maxs.y, -1, -1),
                   (b.mins.x, b.maxs.y, 1, -1), (b.maxs.x, b.mins.y, -1, 1)]
        for cx, cy, dx, dy in corners:
            for r in range(th.risers):
                x, y = cx + dx * (5.0 + 9.0 * r), cy + dy * 5.0
                foot = Bounds.between((x - 4, y - 4, f), (x + 4, y + 4, f + h - 1))
                apron = Bounds.between((min(x, x + dx * 40) - 4, min(y, y + dy * 40) - 4, f),
                                       (max(x, x + dx * 40) + 4, max(y, y + dy * 40) + 4, f + 72))
                if not (_clear_floor(foot, occ, lanes) and _clear_floor(apron, occ, lanes)):
                    continue
                for k in range(pieces):
                    prop((PIPE, Point(x, y, f + 32.0 * k), 0.0, 1.0, True), "riser", False)
                occ.append((x - 4, y - 4, f, x + 4, y + 4, f + h))
    # ---- ducts along the longest free high runs --------------------------
    duct_z = h - th.beam_depth - 21.0   # its top 4 under the beams
    high = []
    for side, _axis, _sign, facing in _SIDES:
        if side not in sides:
            continue
        runs = wall_runs(room, occ, side, duct_z - 18, duct_z + 18, depth=38.0, min_run=96.0)
        high.append((sum(c - a for a, c in runs), side, facing, runs))
    high.sort(key=lambda r: -r[0])
    for _total, side, facing, runs in high[:th.ducts]:
        for a, c in runs:
            k = int((c - a) // 32.0)
            start = a + ((c - a) - 32.0 * k) / 2.0
            for j in range(k):
                t = start + 32.0 * j + 32.0       # the segment's origin is its +x end
                if side == "south":
                    at, yaw = Point(t, b.mins.y + 18.0, f + duct_z), 0.0
                elif side == "north":
                    at, yaw = Point(t, b.maxs.y - 18.0, f + duct_z), 0.0
                elif side == "west":
                    at, yaw = Point(b.mins.x + 18.0, t, f + duct_z), 90.0
                else:
                    at, yaw = Point(b.maxs.x - 18.0, t, f + duct_z), 90.0
                prop((DUCT, at, yaw, 1.0, False), "duct", True)
            box = _band(room, side, a, c, duct_z - 18, duct_z + 18, 36.0)
            occ.append((box.mins.x, box.mins.y, box.mins.z, box.maxs.x, box.maxs.y, box.maxs.z))
    # ---- cable trays on the next walls ------------------------------------
    tray_z = h - 64.0
    for _total, side, facing, _runs in high[th.ducts:th.ducts + th.trays]:
        for a, c in wall_runs(room, occ, side, tray_z - 6, tray_z + 4, depth=16.0, min_run=96.0):
            brush(_band(room, side, a, c, tray_z - 1.0, tray_z, 14.0), th.tray, "tray", floats=True)
            lip = _band(room, side, a, c, tray_z, tray_z + 3.0, 14.0)
            inner = _band(room, side, a, c, tray_z, tray_z + 3.0, 13.0)
            # the lip is the outer 1 unit of the channel
            lx0 = lip.mins.x if side != "west" else inner.maxs.x
            lx1 = lip.maxs.x if side != "east" else inner.mins.x
            ly0 = lip.mins.y if side != "south" else inner.maxs.y
            ly1 = lip.maxs.y if side != "north" else inner.mins.y
            brush(Bounds.between((lx0, ly0, lip.mins.z), (lx1, ly1, lip.maxs.z)), th.tray, "tray_lip",
                  floats=True)
            for t in range(int(a) + 16, int(c) - 8, 64):
                brush(_band(room, side, t, t + 2.0, tray_z - 10.0, tray_z - 1.0, 14.0), th.tray,
                      "tray_bracket", floats=True)
    # ---- ceiling beams across the short span, lamps hung off them --------
    taken: list[tuple[float, float, float, float]] = []   # beams and lamps, plan boxes
    if th.beam_every:
        across_x = (b.maxs.x - b.mins.x) <= (b.maxs.y - b.mins.y)   # beams run along x
        lo, hi = (b.mins.y, b.maxs.y) if across_x else (b.mins.x, b.maxs.x)
        count = max(1, int((hi - lo) / th.beam_every))
        step = (hi - lo) / (count + 1)
        for k in range(1, count + 1):
            for nudge in (0, 24, -24, 48, -48, 72, -72):
                t = lo + k * step + nudge
                t0, t1 = t - th.beam_width / 2, t + th.beam_width / 2
                if across_x:
                    box = Bounds.between((b.mins.x, t0, b.maxs.z - th.beam_depth), (b.maxs.x, t1, b.maxs.z))
                else:
                    box = Bounds.between((t0, b.mins.y, b.maxs.z - th.beam_depth), (t1, b.maxs.y, b.maxs.z))
                hit = [o for o in ceiling if o[0] < box.maxs.x and o[3] > box.mins.x
                       and o[1] < box.maxs.y and o[4] > box.mins.y]
                if not hit:
                    break
            else:
                continue
            brush(box, th.beam, "beam")
            if th.hanging:
                a0, a1 = (b.mins.x, b.maxs.x) if across_x else (b.mins.y, b.maxs.y)
                m = max(1, int((a1 - a0) // th.hanging_every))
                for j in range(m):
                    s = a0 + (j + 0.5) * (a1 - a0) / m
                    # not in front of the wall's top: a lamp there hid the
                    # lettering high on a tall room's walls
                    if s - a0 < 160.0 or a1 - s < 160.0:
                        continue
                    at = Point(s, t, b.maxs.z - th.beam_depth) if across_x else \
                        Point(t, s, b.maxs.z - th.beam_depth)
                    # not onto a sign board hung under the beam (Z44 reports
                    # a lamp and a sign sharing the same space)
                    if any(o[0] < at.x + 14 and o[3] > at.x - 14 and o[1] < at.y + 14
                           and o[4] > at.y - 14 and o[5] > at.z - 16.0 and o[2] < at.z for o in occ):
                        continue
                    prop((th.hanging, at, 0.0, 1.0, False), "hanging", True)
                    taken.append((at.x - 16.0, at.y - 16.0, at.x + 16.0, at.y + 16.0))
            taken.append((box.mins.x, box.mins.y, box.maxs.x, box.maxs.y))
    # ---- fixtures flush on the ceiling, in a grid between the beams ------
    if th.ceiling_every and th.ceiling_models:
        _ceiling_grid(room, th, taken, ceiling + [o for o in occ if o[5] >= b.maxs.z - 24.0], prop)
    if props:
        for k in range(0, len(props), 40):
            bp.place_props(props[k:k + 40], id=f"{ident}_props_{k // 40}")
    return rep


def _ceiling_grid(room, th: WallTheme, taken, occupied, prop) -> None:
    """One of *th*'s ceiling fixtures per ``ceiling_every`` cell, flush on
    *room*'s ceiling (origin on it: each model's box hangs below its
    origin), 64 in from the walls, off the beams and lamps in *taken* and
    anything already reaching the ceiling (*occupied*, 6-tuples).  The model
    turns its long side down the room's long axis; which model goes where
    is fixed by the cell, so a build is repeatable."""
    from ..recipes.props import MODEL_BOX

    b = room.interior
    step = th.ceiling_every
    long_x = (b.maxs.x - b.mins.x) >= (b.maxs.y - b.mins.y)
    nx = max(1, int((b.maxs.x - b.mins.x - 128.0) // step) + 1)
    ny = max(1, int((b.maxs.y - b.mins.y - 128.0) // step) + 1)
    x0 = (b.mins.x + b.maxs.x) / 2.0 - (nx - 1) * step / 2.0
    y0 = (b.mins.y + b.maxs.y) / 2.0 - (ny - 1) * step / 2.0
    boxes = [o[:2] + o[3:5] for o in occupied] + list(taken)
    for i in range(nx):
        for j in range(ny):
            model = th.ceiling_models[(i * 7 + j * 3) % len(th.ceiling_models)]
            box = MODEL_BOX.get(model)
            if box is None:
                continue
            (lx, ly, _lz), (hx, hy, _hz) = box
            # long side along the room: a model long in y turns 90 in a room long in x
            turn = long_x == ((hy - ly) > (hx - lx))
            ex, ey = ((hy - ly) / 2.0, (hx - lx) / 2.0) if turn else ((hx - lx) / 2.0, (hy - ly) / 2.0)
            x, y = x0 + i * step, y0 + j * step
            if any(a < x + ex + 8.0 and c > x - ex - 8.0 and d < y + ey + 8.0 and e > y - ey - 8.0
                   for a, d, c, e in boxes):
                continue
            prop((model, Point(x, y, b.maxs.z), 90.0 if turn else 0.0, 1.0, False), "ceiling", True)


#: A wall shelf's board and brackets: dark painted steel.
BOARD = Material("t7_metal_black_trim_01", 16.0)


def wall_boards(bp, room, rng, *, stock, ident: str, levels: Sequence[float] = (100.0,),
                depth: float = 14.0, clearance: float = 30.0, min_run: float = 64.0,
                most: float | None = None, keepouts: Sequence[Bounds] = (),
                sides: Sequence[str] = ("south", "north", "west", "east"),
                material: Material = BOARD) -> int:
    """Shelf boards on brackets along *room*'s free walls over head height
    (each of *levels* over the floor), packed end to end from *stock* (an
    ``indoor.SHELF_STOCK`` key or palette) by ``interior.fill_board``: the
    store-room wall that is shelves to the ceiling rather than one flat
    material.  A board goes only where the wall is free from just under it
    to *clearance* over it (openings, signs, pictures, buys, lamps and the
    caller's keep-outs measured as :func:`dress_walls` does), on runs of
    *min_run* or more, and at most *most* units of board in all.  Call it
    before :func:`dress_walls`, which then steps its lamps round the boards.
    Returns how many props it placed."""
    from .indoor import SHELF_STOCK, _model_box
    from .interior import fill_board

    palette = SHELF_STOCK[stock] if isinstance(stock, str) else tuple(stock)
    f = room.floor_z
    occ = _occupied(bp, room, keepouts)
    items: list[tuple] = []
    used = 0.0
    n = 0
    order = list(sides)
    rng.shuffle(order)
    for z in levels:
        if f + z + clearance > room.interior.maxs.z - 4.0:
            continue
        for side in order:
            for a, c in wall_runs(room, occ, side, z - 12.0, z + clearance, depth=depth + 1.0,
                                  min_run=min_run):
                a, c = a + 8.0, c - 8.0
                if most is not None:
                    c = min(c, a + max(0.0, most - used))
                if c - a < min_run - 16.0:
                    continue
                used += c - a
                board = _band(room, side, a, c, z - 2.0, z, depth)
                bp.add_block(board, material, contents=("detail",), reachable=False,
                             id=f"{ident}_board_{n}", note=ATTACHED)
                t = a + 6.0
                while t < c - 4.0:
                    bp.add_block(_band(room, side, t, t + 2.0, z - 12.0, z - 2.0, depth - 2.0), material,
                                 contents=("detail",), reachable=False, id=f"{ident}_bracket_{n}_{int(t)}",
                                 note=ATTACHED)
                    t += 48.0
                plan = Bounds.between((board.mins.x + 1.0, board.mins.y + 1.0, 0.0),
                                      (board.maxs.x - 1.0, board.maxs.y - 1.0, 1.0))
                for p in fill_board(rng, palette, plan, f + z, max_height=clearance - 2.0):
                    lo = _model_box(p.model)[0]
                    items.append((p.model, Point(p.x, p.y, p.surface - lo[2] * p.scale), p.yaw, p.scale,
                                  False))
                occ.append((board.mins.x, board.mins.y, f + z - 12.0, board.maxs.x, board.maxs.y,
                            f + z + clearance))
                n += 1
    for k in range(0, len(items), 40):
        bp.place_props(items[k:k + 40], id=f"{ident}_props_{k // 40}")
    return len(items)
