"""The blueprint drawn as a top-down plan, for the loading screen.

The mod tools take a usermap's loading screen as a ``.png`` in the map's
zone folder (Section 6.1), and a generated map has no artist. What it does
have is an exact description of its own layout, so the honest default is to
draw that: rooms, their walls and doorways, the yards zombies come out of,
the priced doors, and where the players start. Nothing here is decorative
except the caption, and nothing is invented -- every rectangle on the image
is a rectangle in the model.

The render is a pure function of the blueprint: same model, same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..blueprint.elements import (
    Door,
    Machine,
    Massing,
    MysteryBox,
    PlayerStart,
    PowerSwitch,
    PropScatter,
    Room,
    Spawn,
    Terrain,
    WallWeapon,
    Yard,
    Zone,
)
from ..images.raster import Colour, Raster, blend
from .manifest import display_title
from ..solids.forms import Solid
from ..spatial import Axis, Span

__all__ = [
    "PlanPalette",
    "PLAN_PALETTE",
    "PlanView",
    "render_plan",
]

#: World units of the scale bar, largest that still fits the caption row.
_SCALE_STEPS = (64.0, 128.0, 256.0, 512.0, 1024.0, 2048.0, 4096.0)


@dataclass(frozen=True, slots=True)
class PlanPalette:
    """Every colour the plan uses. Dark, because a loading screen is."""

    background: Colour = (11, 12, 16)
    surround: Colour = (16, 18, 23)
    structure: Colour = (56, 59, 68)
    wall: Colour = (104, 108, 118)
    floor: Colour = (44, 47, 55)
    yard: Colour = (32, 34, 40)
    opening: Colour = (140, 143, 151)
    terrain_low: Colour = (24, 30, 25)
    terrain_high: Colour = (78, 88, 64)
    door: Colour = (208, 152, 54)
    machine: Colour = (76, 156, 200)
    mystery_box: Colour = (214, 182, 92)
    power: Colour = (116, 194, 126)
    wall_buy: Colour = (176, 178, 186)
    spawn: Colour = (170, 62, 62)
    start: Colour = (240, 242, 248)
    prop: Colour = (68, 72, 80)
    zone: Colour = (74, 80, 94)
    text: Colour = (228, 231, 238)
    dim_text: Colour = (136, 140, 150)


PLAN_PALETTE = PlanPalette()


@dataclass(frozen=True, slots=True)
class PlanView:
    """A rendered plan and the framing it used."""

    raster: Raster
    world: Span
    pixels_per_unit: float

    def png(self, *, level: int = 6) -> bytes:
        return self.raster.to_png(level=level)


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------
def _solid_footprint(solid: Solid) -> Span | None:
    xs: list[float] = []
    ys: list[float] = []
    for face in solid.faces:
        for point in face.points:
            xs.append(point.x)
            ys.append(point.y)
    if not xs:
        return None
    return Span.flat_ok((min(xs), min(ys), 0.0), (max(xs), max(ys), 0.0))


def _footprints(blueprint) -> list[Span]:
    """Every XY rectangle worth framing. The sky cage is deliberately out.

    Framing on the enclosure would zoom the whole plan out by its gap and
    shell thickness and put a grey border where the map is not.
    """
    boxes: list[Span] = []
    for room in blueprint.elements(Room):
        boxes.append(room.shell.outer if hasattr(room.shell, "outer") else room.outer)
    for yard in blueprint.elements(Yard):
        boxes.append(yard.outer)
    for massing in blueprint.elements(Massing):
        for solid in massing.solids:
            box = _solid_footprint(solid)
            if box is not None:
                boxes.append(box)
    for terrain in blueprint.elements(Terrain):
        boxes.append(terrain.record.footprint)
    for door in blueprint.elements(Door):
        boxes.append(door.box)
    return boxes


class _Frame:
    """World XY to pixels: north up, uniform scale, centred in a box."""

    __slots__ = ("world", "left", "top", "right", "bottom", "scale", "_cx", "_cy")

    def __init__(self, world: Span, box: tuple[int, int, int, int]) -> None:
        self.world = world
        self.left, self.top, self.right, self.bottom = box
        width = max(1, self.right - self.left)
        height = max(1, self.bottom - self.top)
        self.scale = min(width / world.extent(Axis.X), height / world.extent(Axis.Y))
        centre = world.centre
        self._cx = centre.x
        self._cy = centre.y

    def x(self, world_x: float) -> int:
        middle = (self.left + self.right) / 2.0
        return int(round(middle + (world_x - self._cx) * self.scale))

    def y(self, world_y: float) -> int:
        middle = (self.top + self.bottom) / 2.0
        return int(round(middle - (world_y - self._cy) * self.scale))

    def rect(self, box: Span) -> tuple[int, int, int, int]:
        """``(x0, y0, x1, y1)`` in pixels, never thinner than one pixel."""
        x0, x1 = self.x(box.mins.x), self.x(box.maxs.x)
        y0, y1 = self.y(box.maxs.y), self.y(box.mins.y)
        if x1 <= x0:
            x1 = x0 + 1
        if y1 <= y0:
            y1 = y0 + 1
        return x0, y0, x1, y1


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_plan(
    blueprint,
    *,
    width: int,
    height: int,
    title: str | None = None,
    palette: PlanPalette = PLAN_PALETTE,
    caption: bool = True,
) -> PlanView:
    """Draw *blueprint* as a plan filling ``width x height`` pixels."""
    raster = Raster(width, height, palette.background)
    unit = max(1, round(min(width, height) / 180.0))
    pad = unit * 6
    caption_height = (Raster.text_height(scale=_title_scale(height)) + unit * 10) if caption else 0

    box = (pad, pad, width - pad, height - pad - caption_height)
    boxes = _footprints(blueprint)
    world = Span.hull_of(boxes).grown(64.0) if boxes else Span.between(
        (-512.0, -512.0, 0.0), (512.0, 512.0, 1.0)
    )
    frame = _Frame(world, box)

    _draw_terrain(raster, frame, blueprint, palette)
    _draw_massing(raster, frame, blueprint, palette)
    _draw_zone_bounds(raster, frame, blueprint, palette, unit)
    _draw_yards(raster, frame, blueprint, palette)
    _draw_rooms(raster, frame, blueprint, palette)
    _draw_doors(raster, frame, blueprint, palette, unit)
    _draw_markers(raster, frame, blueprint, palette, unit)
    _draw_north(raster, box, palette, unit)
    if caption:
        _draw_caption(raster, blueprint, palette, unit, frame, title)
    return PlanView(raster, world, frame.scale)


def _title_scale(height: int) -> int:
    return max(1, round(height / 160.0))


def _draw_terrain(raster: Raster, frame: _Frame, blueprint, palette: PlanPalette) -> None:
    for terrain in blueprint.elements(Terrain):
        record = terrain.record
        field = record.heights
        lowest = min(field.at(r, c) for r in range(field.rows) for c in range(field.cols))
        highest = max(field.at(r, c) for r in range(field.rows) for c in range(field.cols))
        span = (highest - lowest) or 1.0
        for row in range(field.rows):
            y0 = record.anchor.y + row * record.y_cell
            for col in range(field.cols):
                x0 = record.anchor.x + col * record.x_cell
                cell = Span.flat_ok(
                    (x0, y0, 0.0), (x0 + record.x_cell, y0 + record.y_cell, 0.0)
                )
                weight = (field.at(row, col) - lowest) / span
                colour = blend(palette.terrain_low, palette.terrain_high, weight)
                raster.fill_rect(*frame.rect(cell), colour)


def _draw_massing(raster: Raster, frame: _Frame, blueprint, palette: PlanPalette) -> None:
    for massing in blueprint.elements(Massing):
        for solid in massing.solids:
            box = _solid_footprint(solid)
            if box is not None:
                raster.fill_rect(*frame.rect(box), palette.structure)


def _draw_zone_bounds(
    raster: Raster, frame: _Frame, blueprint, palette: PlanPalette, unit: int
) -> None:
    for zone in blueprint.elements(Zone):
        if zone.bounds is None:
            continue
        raster.outline_rect(*frame.rect(zone.bounds), palette.zone, weight=unit)


def _draw_yards(raster: Raster, frame: _Frame, blueprint, palette: PlanPalette) -> None:
    for yard in blueprint.elements(Yard):
        raster.fill_rect(*frame.rect(yard.outer), palette.wall)
        raster.fill_rect(*frame.rect(yard.interior), palette.yard)


def _draw_rooms(raster: Raster, frame: _Frame, blueprint, palette: PlanPalette) -> None:
    for room in blueprint.elements(Room):
        raster.fill_rect(*frame.rect(room.outer), palette.wall)
        raster.fill_rect(*frame.rect(room.interior), palette.floor)
    # Openings are cut after every wall is down, so a doorway between two
    # rooms is not painted over by the second room's wall.
    for room in blueprint.elements(Room):
        for box in room.aperture_boxes:
            raster.fill_rect(*frame.rect(box), palette.opening)


def _draw_doors(
    raster: Raster, frame: _Frame, blueprint, palette: PlanPalette, unit: int
) -> None:
    for door in blueprint.elements(Door):
        x0, y0, x1, y1 = frame.rect(door.box)
        raster.fill_rect(x0, y0, x1, y1, palette.door)


def _draw_markers(
    raster: Raster, frame: _Frame, blueprint, palette: PlanPalette, unit: int
) -> None:
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            raster.dot(frame.x(prop.origin.x), frame.y(prop.origin.y), unit, palette.prop)
    for spawn in blueprint.elements(Spawn):
        raster.dot(
            frame.x(spawn.position.x),
            frame.y(spawn.position.y),
            unit * 2,
            palette.spawn,
        )
    for machine in blueprint.elements(Machine):
        raster.dot(
            frame.x(machine.position.x),
            frame.y(machine.position.y),
            unit * 3,
            palette.machine,
        )
    for buy in blueprint.elements(WallWeapon):
        raster.dot(
            frame.x(buy.position.x), frame.y(buy.position.y), unit * 2, palette.wall_buy
        )
    for switch in blueprint.elements(PowerSwitch):
        raster.dot(
            frame.x(switch.position.x),
            frame.y(switch.position.y),
            unit * 3,
            palette.power,
        )
    for chest in blueprint.elements(MysteryBox):
        raster.diamond(
            frame.x(chest.position.x),
            frame.y(chest.position.y),
            unit * 4,
            palette.mystery_box,
        )
    for start in blueprint.elements(PlayerStart):
        for point in start.slot_positions():
            raster.diamond(frame.x(point.x), frame.y(point.y), unit * 3, palette.start)


def _draw_north(
    raster: Raster, box: tuple[int, int, int, int], palette: PlanPalette, unit: int
) -> None:
    """North is world +Y, which this projection puts at the top."""
    _left, top, right, _bottom = box
    scale = max(1, unit * 2)
    x = right - Raster.text_width("N", scale=scale) - unit * 2
    y = top + unit * 2
    raster.text(x, y, "N", palette.dim_text, scale=scale)
    tip_x = x + Raster.text_width("N", scale=scale) // 2
    raster.diamond(tip_x, y - unit * 4, unit * 2, palette.dim_text)


def _scale_bar_units(frame: _Frame, allowance_px: int) -> float:
    fitting = [step for step in _SCALE_STEPS if step * frame.scale <= allowance_px]
    return fitting[-1] if fitting else _SCALE_STEPS[0]


def _draw_caption(
    raster: Raster,
    blueprint,
    palette: PlanPalette,
    unit: int,
    frame: _Frame,
    title: str | None,
) -> None:
    scale = _title_scale(raster.height)
    small = max(1, scale // 2)
    baseline = raster.height - unit * 4 - Raster.text_height(scale=scale)
    raster.fill_rect(0, baseline - unit * 4, raster.width, raster.height, palette.surround)
    raster.text(unit * 6, baseline, display_title(blueprint.name, title), palette.text, scale=scale)

    counts = _counts_line(blueprint)
    raster.text(
        unit * 6,
        baseline - unit * 3 - Raster.text_height(scale=small),
        counts,
        palette.dim_text,
        scale=small,
    )

    units = _scale_bar_units(frame, raster.width // 5)
    bar = max(2, int(round(units * frame.scale)))
    label = f"{units:g} UNITS"
    right = raster.width - unit * 6
    label_width = Raster.text_width(label, scale=small)
    raster.fill_rect(
        right - bar,
        baseline + Raster.text_height(scale=scale) - unit * 2,
        right,
        baseline + Raster.text_height(scale=scale),
        palette.dim_text,
    )
    raster.text(
        right - max(bar, label_width),
        baseline - unit * 3 - Raster.text_height(scale=small),
        label,
        palette.dim_text,
        scale=small,
    )


def _counts_line(blueprint) -> str:
    parts: list[tuple[int, str]] = [
        (len(blueprint.elements(Zone)), "ZONE"),
        (len(blueprint.elements(Room)), "ROOM"),
        (len(blueprint.elements(Door)), "DOOR"),
        (len(blueprint.elements(Spawn)), "SPAWN"),
    ]
    return "  ".join(
        f"{count} {word}{'S' if count != 1 else ''}" for count, word in parts if count
    )
