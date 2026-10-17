"""The map model: what the mapper decided, with no file format in sight.

A :class:`~.model.Blueprint` holds elements -- rooms, zones, doors, machines,
lights -- each carrying its decision and a stable id.  Handles returned by the
operations *are* the elements, so ``room.interior`` and ``door.flag`` need no
lookup, and re-running the same inputs yields the same ids, the same GUIDs and
the same bytes.
"""

from __future__ import annotations

from .catalogue import PERKS, PerkKind, perk_named
from .elements import (
    Door,
    DoorRef,
    Element,
    Enclosure,
    Lamp,
    Machine,
    MachineRef,
    Massing,
    MysteryBox,
    Opening,
    OpeningRef,
    PlayerStart,
    PowerSwitch,
    Prefab,
    PropScatter,
    Room,
    RoomMaterials,
    RoomRef,
    Spawn,
    SpawnRef,
    Terrain,
    WallWeapon,
    Window,
    WindowRef,
    Yard,
    YardRef,
    Zone,
    ZoneRef,
)
from .reach import Clash, Keep
from ..script.custom import CustomFunction, CustomScript, Slot
from .model import Blueprint, GroundHit
from .script_plan import ScriptPlan, ZoneEdge

__all__ = [
    "Blueprint",
    "GroundHit",
    "Keep",
    "Clash",
    "CustomScript",
    "CustomFunction",
    "Slot",
    "ScriptPlan",
    "ZoneEdge",
    "PerkKind",
    "PERKS",
    "perk_named",
    "Element",
    "Massing",
    "Room",
    "RoomMaterials",
    "Opening",
    "Yard",
    "Enclosure",
    "Terrain",
    "PlayerStart",
    "Zone",
    "Spawn",
    "Door",
    "Machine",
    "WallWeapon",
    "MysteryBox",
    "PowerSwitch",
    "Lamp",
    "Window",
    "Prefab",
    "PropScatter",
    "RoomRef",
    "ZoneRef",
    "DoorRef",
    "YardRef",
    "WindowRef",
    "MachineRef",
    "SpawnRef",
    "OpeningRef",
]
