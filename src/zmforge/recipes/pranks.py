"""A map that lies to the player, built from the three-room fixture.

This recipe exists to exercise the custom-script seam end to end: it is the
three-room layout that has compiled, linked and played (spec appendix C) with
:mod:`zmforge.script.tricks` wired onto the elements that layout already
places.  Nothing about the geometry changes, so a failure here is a failure
of the script and not of the map.

**None of these mechanics has been played.**  Each one's evidence is in its
function's docstring in :mod:`zmforge.script.tricks`, and each one's
unverified parts are named there.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..blueprint.elements import Door, MysteryBox, Room
from ..blueprint.model import Blueprint
from ..script import merge, tricks
from ..spatial import Facing, Point
from .layouts import FIXTURE, ThreeRoomPlan, three_room_map

__all__ = ["PrankPlan", "prank_map", "add_prank_logic"]


@dataclass(frozen=True)
class PrankPlan:
    """Every choice the prank layer makes.

    ``trap_weapon`` is deliberately not the layout's starting weapon: the
    trap keys on the *weapon*, because that is what the ``weapon_fired``
    notify carries, so a weapon sold in two places is trapped in both.

    The two broken perk machines that used to be here are gone from this
    map: they read as broken, not as a joke.  :func:`zmforge.script.tricks.perk_pranks`
    still exists and is still tested; nothing calls it.
    """

    trap_weapon: str = "shotgun_pump"
    trap_price: int = 4950
    blast_range: float = 768.0
    blast_cone_degrees: float = 120.0
    ambush_count: int = 10
    ambush_sprint: bool = True
    box_weapon: str = "shotgun_semiauto"
    hop_distance: float = 60.0
    arrival_yaw: float = 180.0
    spike_seconds: float = 20.0


def add_prank_logic(
    blueprint: Blueprint,
    plan: PrankPlan = PrankPlan(),
    *,
    box: MysteryBox | str | None = None,
    door: Door | str | None = None,
    pad: Point | None = None,
    arrival: Point | None = None,
    ambush_door: Door | str | None = None,
    closet: Point | None = None,
) -> Blueprint:
    """Attach the mechanics to a blueprint someone else laid out.

    One call, so a layout recipe adds its gags on a single line and keeps
    owning its geometry.  Defaults are read off the blueprint rather than
    written down twice: the map's first mystery box, and its most expensive
    door for the spawn spike, which is the one a player has just paid the
    most to open.

    The teleporter is only attached when ``pad`` is given, because where a
    disappointing teleporter belongs is a judgement about the layout and not
    something to guess from element bounds.  ``arrival`` defaults to
    ``plan.hop_distance`` east of the pad.

    Mechanics are skipped rather than faked when the map has nothing to hang
    them on: no box means no rigged box, no doors means no spawn spike.

    The cupboard ambush needs both ``ambush_door`` and ``closet``: which door
    hides it and where inside the closet the bodies wait are both facts about
    a layout this function did not build, and guessing either would put ten
    zombies inside a wall.  Naming one without the other is an error rather
    than a silent skip.
    """
    parts = [
        tricks.mega_blast_on_fire(
            plan.trap_weapon,
            range_units=plan.blast_range,
            cone_degrees=plan.blast_cone_degrees,
        ),
    ]

    chest = _resolve(blueprint, box, MysteryBox)
    if chest is not None:
        parts.append(
            tricks.rigged_mystery_box(plan.box_weapon, origin=chest.position)
        )

    gate = _resolve(blueprint, door, Door)
    if gate is not None:
        parts.append(
            tricks.spawn_spike_on_flag(gate.flag, seconds=plan.spike_seconds)
        )

    if ambush_door is not None or closet is not None:
        if ambush_door is None or closet is None:
            raise ValueError(
                "the cupboard ambush needs both the door that opens it and the "
                "point inside the closet; one without the other would put ten "
                "zombies somewhere nobody chose"
            )
        hinge = _resolve(blueprint, ambush_door, Door)
        if hinge is None:
            raise ValueError("the blueprint has no door to hang the ambush on")
        parts.append(
            tricks.closet_ambush(
                hinge.flag,
                closet,
                count=plan.ambush_count,
                sprint=plan.ambush_sprint,
            )
        )

    if pad is not None:
        landing = arrival or Point(pad.x + plan.hop_distance, pad.y, pad.z)
        parts.append(
            tricks.short_hop_teleporter(pad, landing, arrival_yaw=plan.arrival_yaw)
        )

    blueprint.add_custom_logic(merge(*parts))
    return blueprint


def _resolve(blueprint: Blueprint, wanted, kind):
    """An element by id, by value, or the sensible default of its kind."""
    if isinstance(wanted, kind):
        return wanted
    if isinstance(wanted, str):
        found = blueprint.find(wanted)
        if not isinstance(found, kind):
            raise TypeError(f"{wanted!r} is a {found.kind}, not a {kind.__name__}")
        return found
    candidates = [e for e in blueprint.elements(kind)]
    if not candidates:
        return None
    if kind is Door:
        return max(candidates, key=lambda d: (d.price, d.id))
    return candidates[0]


def prank_map(
    name: str,
    plan: PrankPlan = PrankPlan(),
    *,
    layout: ThreeRoomPlan = FIXTURE,
    seed: str | None = None,
) -> Blueprint:
    """The three-room map, plus every mechanic that could be evidenced.

    The mechanics are attached to what the layout already built -- the real
    door's flag, the real box's origin, the real vault room -- rather than to
    coordinates written down twice.
    """
    blueprint = three_room_map(name, layout, seed=seed)

    vault = blueprint.find("room_vault") if _has(blueprint, "room_vault") else None
    if vault is None:  # the fixture names it by position, so find it by kind
        vault = [r for r in blueprint.elements(Room)][-1]
    interior = vault.interior

    # The expensive wall buy that downs whoever fires it.
    trap_position = Point(
        interior.maxs.x - 8.0,
        (interior.mins.y + interior.maxs.y) / 2.0 - 96.0,
        vault.floor_z - 8.0,
    )
    blueprint.place_wall_weapon(
        plan.trap_weapon, trap_position, Facing.WEST, id="vault_trap_wallbuy"
    )

    box = next(iter(blueprint.elements(MysteryBox)))
    door = blueprint.find("door_arena_vault")
    if not isinstance(door, Door):  # pragma: no cover - fixture guarantees it
        raise TypeError("the fixture's vault door is not a Door")

    pad = Point(
        interior.mins.x + 72.0,
        interior.maxs.y - 72.0,
        vault.floor_z + 4.0,
    )
    arrival = Point(pad.x + plan.hop_distance, pad.y, pad.z)

    add_prank_logic(blueprint, plan, box=box, door=door, pad=pad, arrival=arrival)
    return blueprint


def _has(blueprint: Blueprint, element_id: str) -> bool:
    try:
        blueprint.find(element_id)
    except Exception:
        return False
    return True
