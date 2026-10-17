"""Compositions: whole maps built from the core operations.

Recipes hold no geometry knowledge of their own -- they are ordinary callers
of :class:`~zmforge.blueprint.model.Blueprint`, parameterised so nothing is
baked in.  Two are shipped:

:func:`three_room_map`
    the windowed-start / arena / vault layout with two priced doors.  Spec
    item E15 records that this is the only layout with a recorded in-game
    pass, and its default numbers are the ones that compiled, linked and
    played, so it doubles as the end-to-end fixture.
:func:`one_room_map`
    the smallest thing that is still a zombies map: one room, one window, one
    yard.  Useful for exercising the build chain in seconds.

Neither claims anything about how they play.  The numbers below are the
fixture's; a caller changing them is off the verified path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..blueprint.elements import STOCK_PLAYER_SLOTS
from ..blueprint.model import Blueprint
from ..solids.layout import Aperture
from ..spatial import Bounds, Facing, Point, Side

__all__ = ["ThreeRoomPlan", "three_room_map", "one_room_map", "FIXTURE"]


@dataclass(frozen=True)
class ThreeRoomPlan:
    """Every number the three-room layout uses.

    The defaults reproduce spec appendix C exactly, because that is the
    configuration the conformance gate compares against.  Everything here is a
    parameter: the spec is explicit that the *pattern* is what has been
    played, not these particular extents.
    """

    start: Bounds = Bounds.between((-512, -256, 0), (-128, 256, 256))
    arena: Bounds = Bounds.between((-128, -512, 0), (768, 512, 384))
    vault: Bounds = Bounds.between((768, -256, 0), (1280, 256, 256))
    wall: float = 16.0
    doorway_width: float = 80.0
    doorway_height: float = 96.0
    window_height: float = 48.0
    yard_depth: float = 176.0
    start_zone: str = "start"
    arena_zone: str = "arena"
    vault_zone: str = "vault"
    arena_door_price: int = 500
    vault_door_price: int = 1500
    perk_margin: float = 160.0
    perks: Sequence[str] = ("juggernog", "speed_cola", "quick_revive", "double_tap")
    start_weapon: str = "pistol_burst"
    arena_weapons: Sequence[str] = ("smg_standard", "ar_standard")
    gap: float = 128.0
    shell_thickness: float = 32.0


#: The configuration of spec appendix C, for the end-to-end gate.
FIXTURE = ThreeRoomPlan()


def _floor_surface(bounds: Bounds, wall: float) -> float:
    return bounds.mins.z + wall


def three_room_map(
    name: str,
    plan: ThreeRoomPlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
) -> Blueprint:
    """A windowed start room, an arena and a vault, joined by two priced doors."""
    blueprint = Blueprint(name, seed=seed)
    blueprint.starter = True  # design advisories shown only with -v
    floor = _floor_surface(plan.start, plan.wall)

    start = blueprint.add_room(
        plan.start,
        wall=plan.wall,
        openings=[
            Aperture(
                side=Side.EAST, width=plan.doorway_width, height=plan.doorway_height
            )
        ],
        id="start_room",
    )
    arena = blueprint.add_room(
        plan.arena,
        wall=plan.wall,
        openings=[
            Aperture(
                side=Side.WEST, width=plan.doorway_width, height=plan.doorway_height
            ),
            Aperture(
                side=Side.EAST, width=plan.doorway_width, height=plan.doorway_height
            ),
        ],
        id="arena_room",
    )
    vault = blueprint.add_room(
        plan.vault,
        wall=plan.wall,
        openings=[
            Aperture(
                side=Side.WEST, width=plan.doorway_width, height=plan.doorway_height
            )
        ],
        id="vault_room",
    )

    start_zone = blueprint.add_zone(plan.start_zone, start, starting=True)
    arena_zone = blueprint.add_zone(plan.arena_zone, arena)
    vault_zone = blueprint.add_zone(plan.vault_zone, vault)

    # The starting zone's zombies come through barricade windows from yards
    # outside it (item E3); one call per window does hole, yard, prefab, riser
    # and yard light.
    for side in (Side.SOUTH, Side.NORTH):
        blueprint.add_window(
            start_zone,
            start,
            side,
            yard_depth=plan.yard_depth,
            height=plan.window_height,
            id=f"start_window_{side.name.lower()}",
        )

    centre_x = (plan.start.mins.x + plan.start.maxs.x) / 2.0
    blueprint.place_light(
        Point(centre_x, 0.0, plan.start.maxs.z - plan.wall - 40.0),
        zone_name=plan.start_zone,
        id="start_light",
    )
    blueprint.set_player_start(
        Point(centre_x, 0.0, floor + 16.0), Facing.EAST, slots=player_slots
    )
    blueprint.place_wall_weapon(
        plan.start_weapon,
        Point(plan.start.mins.x + 18.0, -100.0, floor - 8.0),
        Facing.EAST,
        id="start_wallbuy",
    )

    # Arena: interior risers, four perks inset from the corners, two wall buys
    # and a light over each quadrant.
    arena_interior = arena.interior
    blueprint.add_riser(
        arena_zone,
        Point(0.0, arena_interior.mins.y + 36.0, arena.floor_z),
        Facing.NORTH,
        id="arena_riser_south",
    )
    blueprint.add_riser(
        arena_zone,
        Point(700.0, arena_interior.maxs.y - 36.0, arena.floor_z),
        Facing.SOUTH,
        id="arena_riser_north",
    )
    corners = (
        (arena_interior.mins.x + plan.perk_margin, arena_interior.mins.y + plan.perk_margin, Facing.NORTH),
        (arena_interior.maxs.x - plan.perk_margin, arena_interior.mins.y + plan.perk_margin, Facing.NORTH),
        (arena_interior.mins.x + plan.perk_margin, arena_interior.maxs.y - plan.perk_margin, Facing.SOUTH),
        (arena_interior.maxs.x - plan.perk_margin, arena_interior.maxs.y - plan.perk_margin, Facing.SOUTH),
    )
    for perk, (x, y, facing) in zip(plan.perks, corners):
        blueprint.place_perk(perk, Point(x, y, arena.floor_z), facing, id=f"perk_{perk}")
        blueprint.place_light(
            Point(x, y, plan.arena.maxs.z - plan.wall - 48.0),
            zone_name=plan.arena_zone,
            id=f"arena_light_{perk}",
        )
    # Appendix B's table decides the facings: a buy on the north wall faces
    # south into the room (prefab yaw 0), one on the south wall faces north
    # (yaw 180).
    for slug, side, facing in (
        (plan.arena_weapons[0], Side.NORTH, Facing.SOUTH),
        (plan.arena_weapons[1], Side.SOUTH, Facing.NORTH),
    ):
        y = arena_interior.maxs.y if side is Side.NORTH else arena_interior.mins.y
        blueprint.place_wall_weapon(
            slug, Point(320.0, y, arena.floor_z - 8.0), facing, id=f"arena_wallbuy_{slug}"
        )

    # Vault: two risers, the starting mystery box, pack-a-punch and the power
    # switch.
    vault_interior = vault.interior
    for index, y in enumerate((-200.0, 200.0)):
        blueprint.add_riser(
            vault_zone,
            Point(vault_interior.mins.x + 58.0, y, vault.floor_z),
            Facing.EAST,
            id=f"vault_riser_{index}",
        )
    vault_centre_x = (plan.vault.mins.x + plan.vault.maxs.x) / 2.0
    blueprint.place_mystery_box(
        Point(vault_centre_x, 0.0, vault.floor_z), Facing.WEST, id="vault_box"
    )
    # Against the vault's north wall, so it faces south, out into the room.
    # ``facing`` is the heading the machine's *front* points at, and
    # Facing.WEST would stand it broadside to that wall, with 8 units
    # of a 64-wide machine inside it.  A later map was written from this block and inherited the same quarter
    # turn, which is why Z9 now asks
    # the question (verify.model._check_interactives_have_their_backs_to_the_wall).
    blueprint.place_pack_a_punch(
        Point(vault_interior.maxs.x - 64.0, vault_interior.maxs.y - 24.0,
              vault.floor_z + 4.0),
        Facing.SOUTH,
        id="vault_pap",
    )
    blueprint.place_power_switch(
        Point(vault_centre_x, vault_interior.mins.y + 8.0, vault.floor_z + 8.0),
        Facing.NORTH,
        id="vault_power",
    )
    blueprint.place_light(
        Point(vault_centre_x, 0.0, plan.vault.maxs.z - plan.wall - 40.0),
        zone_name=plan.vault_zone,
        id="vault_light",
    )

    blueprint.add_door(
        (start_zone, arena_zone),
        arena.opening(0),
        price=plan.arena_door_price,
        id="door_start_arena",
    )
    blueprint.add_door(
        (arena_zone, vault_zone),
        vault.opening(0),
        price=plan.vault_door_price,
        id="door_arena_vault",
    )

    blueprint.set_dog_rounds(False)
    blueprint.enclose(gap=plan.gap, thickness=plan.shell_thickness, id="enclosure")
    # The arena is 864 x 992: four hand-placed lamps leave the middle of it
    # beyond any of them.  light_rooms tops every room up to the lamp density
    # the shipped maps carry (zmforge.lighting), and does nothing to a room
    # already covered, so the deliberate placements above still read.
    blueprint.light_rooms()
    return blueprint


def one_room_map(
    name: str,
    *,
    bounds: Bounds = Bounds.between((-256, -256, 0), (256, 256, 256)),
    wall: float = 16.0,
    yard_depth: float = 176.0,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
) -> Blueprint:
    """One room, one barricade window, one yard: the smallest playable shape.

    Single-zone maps are **unverified** as playable -- spec item E15 records
    single-zone maps of that shape have failed in play for reasons never isolated -- so this
    exists to exercise the build chain quickly, not as a template to ship.
    """
    blueprint = Blueprint(name, seed=seed)
    blueprint.starter = True  # design advisories shown only with -v
    room = blueprint.add_room(bounds, wall=wall, id="room")
    zone = blueprint.add_zone("start", room, starting=True)
    blueprint.add_window(zone, room, Side.SOUTH, yard_depth=yard_depth, height=48.0, id="window")
    blueprint.add_riser(
        zone,
        Point(room.interior.centre.x, room.interior.maxs.y - 48.0, room.floor_z),
        Facing.SOUTH,
        id="interior_riser",
    )
    blueprint.place_light(
        Point(room.interior.centre.x, room.interior.centre.y, bounds.maxs.z - wall - 40.0),
        zone_name="start",
        id="room_light",
    )
    blueprint.set_player_start(
        Point(room.interior.centre.x, room.interior.centre.y, room.floor_z + 16.0),
        Facing.EAST,
        slots=player_slots,
    )
    blueprint.set_dog_rounds(False)
    blueprint.enclose(id="enclosure")
    blueprint.light_rooms()
    # A one-room smoke-test layout: no gamble machine (P22).
    blueprint.signature_gamble = False
    return blueprint
