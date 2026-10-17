"""Cemetery Quest: a cemetery at night, rolling
hills of fog, and a crypt.

**Night.**  ``cemetery`` runs The Giant's ``zm_factory`` night preset and sky
under ground fog.  The night link needs that sky's images from the stock
``zm_factory`` folders of the mod tools; ``cemetery-dusk`` (:func:`cemetery_dusk_map`) is
the same map at sunset for a tools tree that lacks them.

The map as a player walks it
============================

**The Front Gate** (start, outdoors).  You spawn inside the locked iron gates
of Hollow Rest Cemetery at night.  The gate behind you says it closes at
midnight; it is 11:59 and it will be 11:59 all night.  A lawn of old graves,
the first headstones you can read, Quick Revive and the starting wall buy.

**The Groundskeeper's Shed** (open from the gate, no door).  Tools, soil, a workbench, Speed Cola, a
shotgun on the wall and the **power switch** -- the groundskeeper ran the
cemetery lights and the chapel's electric crypt lock off a generator in here.

**The Rolling Hills** (1000, through an iron gate that only sells once the
power is on: the shed comes first).  The big one: two
thousand units of heightfield ground that rises and falls up to 160 units,
the fog pooling in the hollow the path runs along.  Rows of headstones,
crosses and obelisks follow the ground; three family mausoleums stand on
hilltops (MOORE, DIGGS and GRAVES); dead trees, iron-fenced family plots,
lantern posts, and **the Open Grave** -- freshly dug, headstone already
carved, reserved for you.  Juggernog, the mystery box, two wall buys.

**Mausoleum Row** (1250).  A street of small tombs north of the hills,
Stamin-Up, a marksman rifle.  At its east end, **the Family Vault** (1000):
walk-in, shelves of coffins, candles, Mule Kick.

**The Chapel of Eternal Rest** (1500).  Pews, an altar with candles, the
Founder's coffin on a bier, Double Tap, a bowie knife on the wall.  Behind the
altar, the **crypt door is on the electric lock** -- it opens when the power
comes on in the shed.

**The Crypt** (down 240 units of stair).  The Crypt Stairs, the **Ossuary**
(750; bones on every shelf, Deadshot) and the **Founder's Tomb** (1500):
Pack-a-Punch, the Founder's sarcophagus and the way out of all this.

**The Gravedigger** is the mini-boss (quest step 5, below).

The story
=========

Ezekiel Hollow founded Hollow Rest in 1851; the Graves family kept it, the
Diggs family dug it, Dr. Cornelius Moore signed the certificates.  Moore
declared the Founder dead on 28 October 1897 ("cause: none found"); he lay
three nights in the chapel and the groundskeeper, Amos Graves, held the
sarcophagus key to seal the crypt at dawn.  At 11:54 on 31 October Amos went
out after Jonah Diggs, the sacked gravedigger who wanted the key, and hid it
in the grave Jonah was digging for him.  At 11:59 the Founder came back for
his coffin, and inside the gates it has been 11:59 ever since.  Jonah is THE
GRAVEDIGGER; Amos's voice still reads the PA, and the quest is his last
shift.  Every named stone, plate and notice tells part of that night; the
optional lore (Amos's unmarked grave, found from his log in the shed) is
:mod:`zmforge.recipes.cemetery_lore`.

The quest: "The Groundskeeper's Last Shift"
===========================================

:mod:`zmforge.recipes.cemetery_quest`, on the shared quest framework
(:mod:`zmforge.script.quest`, :mod:`zmforge.script.bosses`).  The top-left
HUD shows the shift's progress and the current task the whole game; every
step says when it starts and when it is done, centre screen.

1. **COLLECT + DELIVER** -- take the groundskeeper's shovel (the shed's
   workbench) to the Open Grave: it is empty except for a key.
2. **SHOOT** (round 3) -- shoot out the four blue will-o'-wisp lanterns on
   the hills.
3. **KNIFE** (round 4) -- knife the Founder's needle on the tallest hill,
   three times.  "OW."
4. **DEFEND** (round 5) -- stand by the Founder's coffin in the chapel for
   sixty seconds.
5. **BOSS** (round 6) -- THE GRAVEDIGGER climbs out of the Open Grave with six
   friends: a tougher, glowing zombie with his health on the HUD.  He drops
   the Crypt Seal, a max ammo and 1,000 points each.
6. **SURVIVE** -- hold out two more rounds until dawn.
7. **WIN** -- REST IN PEACE at the Founder's sarcophagus, a fixed 20,000
   points: the crypt is sealed, the game ends as a win.

What is new in the generator for this map
=========================================

* :mod:`zmforge.surfaces.hills` -- walkable rolling ground: mounds, pinned
  flat discs for sills and plateaus, and the grading pass that guarantees no
  cell rises more than :data:`~zmforge.surfaces.hills.DEFAULT_MAX_RISE`.
* :mod:`zmforge.atmosphere` -- night sky and fog: ``Blueprint.enclose(
  atmosphere=...)`` names the sun preset, the sky model and a
  ``volume_worldfog``.

**Nobody has played this map.**  Everything above is what the generator
writes; how the fog reads, whether the hills feel like hills, and whether the
jokes land are what a play session answers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from ..atmosphere import (
    CRYPT_LIT_FOG, DUSK_GROUND_FOG, NIGHT_GLOOM, Atmosphere,
)
from ..blueprint.catalogue import WALL_WEAPON_WEAPONS
from ..blueprint.elements import STOCK_PLAYER_SLOTS, RoomMaterials, Terrain
from ..blueprint.model import Blueprint
from ..blueprint.script_plan import ZoneEdge
from ..dressing import link_rooms, room_skin
from ..materials import Material
from ..spatial import Bounds, Facing, Point, Side
from ..surfaces.hills import (
    DEFAULT_MAX_RISE,
    Disc,
    cap_pins,
    Mound,
    limit_rise,
    pin_discs,
    rolling_hills,
    slope_report,
)
from . import cemetery_kit as kit

__all__ = [
    "MAP_TITLE",
    "CemeteryPlan",
    "FIXTURE",
    "PRICES",
    "PROMPTS",
    "EPITAPHS",
    "GAG_LINES",
    "NOTICE_LINES",
    "ENDING_PRICE",
    "cemetery_map",
    "cemetery_dusk_map",
    "build_cemetery",
]

MAP_TITLE = "Cemetery Quest"

#: What every door costs, by zone pair: each door further from the gate
#: costs more than the one before it on its way in.
PRICES: dict[str, int] = {
    # No gate_shed: the shed is open from the gate, so the power switch is
    # reachable before any door (Z80); the hills gate waits for the power.
    "gate_hills": 1000,
    "hills_row": 1250,
    "row_vault": 1500,
    "hills_chapel": 1500,
    # The crypt door is on the electric lock: it opens when the power does,
    # and the price is only what the framework's door record carries.
    "chapel_crypt": 1750,
    "stairs_ossuary": 2000,
    "ossuary_tomb": 2250,
}

#: What the renamed wall buys say (the weapon's own name comes from the engine).
PROMPTS: dict[str, str] = {
    "pistol_burst": "VISITOR'S SIDEARM -- CHECK IN AT THE GATE",
    "shotgun_pump": "GROUNDSKEEPER'S PEST CONTROL",
    "bowie": "GROUNDSKEEPER'S PRUNING KNIFE",
}

#: The price of the ending buy, fixed at about 20,000.
ENDING_PRICE = 20000

#: The readable headstones: ``key -> (name on the stone, what pressing use says)``.
#: All of these are this repository's own words.
EPITAPHS: dict[str, tuple[str, tuple[str, ...]]] = {
    # One story (principle P11; the facts are STORY in cemetery_lore.py):
    # the Founder's vigil, and the night of 31 OCT 1897 when the clocks
    # stopped at 11:59.  The puns are Jonah Diggs's; see "plot_twist".
    "told_you": ("HERE LIES FRED -- read the stone", (
        "HERE LIES FRED. I TOLD YOU I WAS SICK.",
        "Dr. Moore said he was fine. Dr. Moore said that a lot.",
    )),
    "wifi": ("BELOVED UNCLE -- read the stone", (
        "BELOVED UNCLE GARY. BURIED WITH THE FAMILY SILVER.",
        "Somebody dug him up in 1897 to check. It was plate. The spade marks say DIGGS.",
    )),
    "back_soon": ("THE GROUNDSKEEPER -- read the stone", (
        "AMOS GRAVES, GROUNDSKEEPER. 31 OCT 1897. BACK IN 5 MINUTES.",
        "The town paid for the stone. They never found him to put under it.",
    )),
    "pieces": ("REST IN PIECES -- read the stone", (
        "REST IN PIECES. SOME ASSEMBLY REQUIRED.",
        "Parts sent back by Dr. Moore's anatomy class so far: 3 of 206.",
    )),
    "return": ("DAVE -- read the stone", (
        "DAVE. CAME TO THE FOUNDER'S VIGIL FOR THE SANDWICHES.",
        "31 OCT 1897, 11:59. The sandwiches survived.",
    )),
    "reserved": ("RESERVED -- read the stone", (
        "THIS PLOT IS RESERVED FOR: YOU.",
        "Paid in full. No refunds.",
        "Under YOU, a name cut by J. DIGGS is chiselled off. Four letters. It began with A.",
    )),
    "diet": ("NURSE AGNES -- read the stone", (
        "AGNES, NIGHT NURSE. SAT UP WITH THE FOUNDER ALL THREE NIGHTS.",
        "31 OCT 1897, 11:59. She said it was just a little bite.",
    )),
    "plot_twist": ("PLOT TWIST -- read the stone", (
        "PLOT TWIST: THIS IS A PLOT.",
        "Nailed to it: 'JONAH. STOP CARVING PUNS ON THE STONES. -- A. GRAVES'",
    )),
    "moore": ("MOORE FAMILY -- read the plate", (
        "THE MOORE FAMILY. THERE ARE NO MOORE.",
        "(There are, in fact, several more. They are behind you.)",
        "DR. CORNELIUS MOORE signed the Founder's certificate. Cause of death: 'none found'.",
    )),
    "diggs": ("DIGGS FAMILY -- read the plate", (
        "THE DIGGS FAMILY, GRAVEDIGGERS. THEY DUG THEIR OWN.",
        "Very efficient people. Terrible at parties.",
        "Every Diggs is in here but JONAH, sacked in 1897 for digging the wrong way. Up.",
    )),
    "graves": ("GRAVES FAMILY -- read the plate", (
        "THE GRAVES FAMILY, KEEPERS OF HOLLOW REST SINCE 1851.",
        "They had no choice about the career.",
        "The plate lists every Graves inside. The last line reads: AMOS. ON SHIFT.",
    )),
    # The three small tombs on Mausoleum Row (cemetery_dressing._dress_row).
    "tomb_small_a": ("HOLLOW COUSINS -- read the plate", (
        "THE HOLLOW COUSINS. NOT QUITE FAMILY ENOUGH FOR THE FAMILY VAULT.",
        "They sat the Founder's vigil on night one and left early. It did not help.",
    )),
    "tomb_small_b": ("THE PLATT FAMILY -- read the plate", (
        "THE PLATT FAMILY. UNCLE GARY'S LOT.",
        "The real family silver is in here. Jonah Diggs dug up the wrong Platt.",
    )),
    "tomb_small_c": ("DR. MOORE'S PATIENTS -- read the plate", (
        "PATIENTS OF DR. C. MOORE, 1890-1897. EVERY ONE OF THEM DECLARED FINE.",
        "Cause of death, all eleven: 'none found'.",
    )),
    "founder": ("THE FOUNDER -- read the needle", (
        "EZEKIEL HOLLOW, WHO FOUNDED HOLLOW REST IN 1851. 'I WILL BE BACK FOR MY COFFIN.'",
        "Declared dead 28 OCT 1897 by Dr. Moore. He was always a light sleeper.",
    )),
    # Optional lore (placed by cemetery_lore.dress_lore): Amos's own grave,
    # which only his log in the shed tells you how to find.
    "amos": ("A PLAIN STONE -- read the stone", (
        "No name. Two letters cut with the corner of a spade: A.G.",
        "'DUG THIS ONE MYSELF, 1880, FOR WHEN MY SHIFT ENDS. SAVES THE DIGGS BOYS A JOB.'",
        "The soil on top is fresh. It is always fresh.",
    )),
}

#: The notices that are not headstones.
NOTICE_LINES: dict[str, tuple[str, tuple[str, ...]]] = {
    "gate": ("CEMETERY GATE -- read the sign", (
        "GATES CLOSE AT MIDNIGHT.",
        "It is 11:59. It has been 11:59 for a while.",
        "Visitors found inside after closing will be kept.",
    )),
    "open_grave": ("THE OPEN GRAVE -- look in", (
        "Dug up again: old bones and a split coffin lid at the bottom. The stone says YOU.",
        "Whoever finishes digging it had better bring a shovel.",
    )),
    "shed_board": ("GROUNDSKEEPER'S NOTICE BOARD -- read", (
        "DUTY ROSTER: DIG. FILL. DIG AGAIN (THEY KEEP GETTING OUT).",
        "REMINDER: THE GENERATOR RUNS THE LIGHTS AND THE CRYPT LOCK.",
        "FOUNDER'S VIGIL 28-31 OCT: SEAL THE CRYPT AT DAWN. J. DIGGS NOT TO BE LET IN.",
    )),
    "plots_for_sale": ("PLOTS FOR SALE -- read the sign", (
        "PLOTS AVAILABLE. BUY NOW, MOVE IN LATER.",
        "Ask about our two-for-one family deals.",
        "Enquire at the shed. The groundskeeper is back in 5 minutes.",
    )),
    "chapel_hymns": ("HYMN BOARD -- read", (
        "TONIGHT'S HYMNS: 31, 10, 1897.",
        "Nobody has changed the board since the Founder's vigil. There is no hymn 1897.",
    )),
    "crypt_door": ("CRYPT -- read the plaque", (
        "CRYPT. ELECTRIC LOCK. NO POWER, NO ENTRY.",
        "The Founder had the lock fitted in 1897. Nobody asks how. He did not trust shovels.",
    )),
    "ossuary": ("OSSUARY -- read the plaque", (
        "PLEASE DO NOT TAKE THE BONES.",
        "Please do not ADD bones either.",
        "One shelf is labelled RETURNED BY DR. MOORE. It is mostly shins.",
    )),
    "vault": ("HOLLOW FAMILY VAULT -- read the plaque", (
        "THE HOLLOW FAMILY VAULT. MEMBERS ONLY.",
        "Membership is lifelong. And then some.",
        "One shelf is bare: the Founder took his coffin up to the chapel for his vigil.",
    )),
    "sarcophagus": ("THE FOUNDER'S SARCOPHAGUS -- read", (
        "EZEKIEL HOLLOW. REST IN PEACE. Resting here costs 20,000 points, key included.",
        "The lid has a keyhole. The groundskeeper hid the key where nobody would dig.",
    )),
    # Optional lore (placed by cemetery_lore.dress_lore).
    "shift_log": ("THE GROUNDSKEEPER'S LOG -- read the open page", (
        "31 OCT 1897. FOUNDER'S VIGIL, NIGHT 3 OF 3. Kettle on. Key in my coat. Seal at dawn.",
        "11:50. Nurse Agnes says he twitched. Dr. Moore says that is normal. (See: Fred.)",
        "11:54. A shovel on the knoll: Jonah Diggs, after the key. I'll hide it in his hole.",
        "Not back by dawn? Mine is dug, no name, where the dead oak shades the gate.",
        "Back in 5 minutes. -- A.G. (The ink stops there. It is still wet.)",
    )),
    "graves_plot": ("GRAVES FAMILY PLOT -- read the marker", (
        "OBADIAH, RUTH AND ELI GRAVES. THE FIRST KEEPERS OF HOLLOW REST, 1851.",
        "They asked to lie by the gate, to see who came in late.",
    )),
    "moore_plot": ("MORE MOORES -- read the marker", (
        "THE REST OF THE MOORES. THE MOORE MAUSOLEUM FILLED UP IN 1890.",
        "Dr. Moore treated every one of them himself.",
    )),
    "returned_plot": ("FENCED PLOT -- read the marker", (
        "RETURNED WITH APOLOGIES BY DR. C. MOORE, 1897. NAMES UNKNOWN.",
        "Dug up by Jonah Diggs and sold for lectures. The Founder paid for the fence.",
    )),
}

#: Lines said at the player, each a reply to something a player did (P4).  No
#: zone sign-ins and no round-end groundskeeper PA (P13, P17:
#: an announcement that carries no information is noise); the room signs, the
#: gate notice and the props say where you are and what time it is.
GAG_LINES: dict[str, str] = {
    "downed": "Six feet under. Well, five and a half. Get back up.",
    "downed_feed": "&&1 is trying out a plot.",
    "bled_out_feed": "&&1 has moved in permanently.",
    "revived": "Back from the dead. The dead have a fee: 25 points.",
    "revived_broke": "Back from the dead. You could not afford the fee. It is on your tab.",
    "reviver": "You dug &&1 back up.",
    "pap": "Pack-a-Punched. The Founder does not approve of upgrades.",
    "box": "You rifled through a stranger's coffin. Classy.",
    "box_moved": "The coffin got up and walked off.",
    "perk_jugg": "Juggernog: harder to bury.",
    "perk_revive": "Quick Revive: for people who hate commitment.",
    "power": "The cemetery lights are on. The crypt lock is off. Nobody planned this.",
    "idle": "Standing still in a graveyard is how they get you.",
}

#: Seconds a player stands still on the hills before the idle line.
GAG_IDLE_SECONDS = 25.0

_WALL = 16.0

#: How tall the open-air rooms' walls stand over the bottom of the room:
#: a cemetery wall a player sees over, with The
#: Giant's moonlit sky and a backdrop of trees, a spire and rooftops beyond
#: it.  The room keeps its full height in clip above (``add_room``).
OUTDOOR_WALL: Mapping[str, float] = {"gate": 176.0, "hills": 200.0, "row": 176.0}


#: One skin per room: brick cemetery walls outside (the three outdoor rooms
#: are unroofed, open to the sky; their ceiling entry is never laid), stone
#: and panelling inside, brick and stone underground.
SKINS: Mapping[str, RoomMaterials] = {
    "gate": room_skin(kit.WET_BRICK, kit.GROUND, kit.DARK_STONE),
    "shed": room_skin(kit.WOOD, kit.WOOD, kit.WOOD),
    "hills": room_skin(kit.WET_STONE, kit.GRASS, kit.DARK_STONE),
    "row": room_skin(kit.MOSS_BRICK, kit.GRASS, kit.DARK_STONE),
    "vault": room_skin(kit.STONE, kit.STONE, kit.DARK_STONE),
    # Stone walls: panelling draws as a tan box
    # over the hills' walls.
    "chapel": room_skin(kit.WET_STONE, kit.STONE, kit.WOOD),
    # The crypt: flagstones underfoot.
    "stairs": room_skin(kit.BRICK, kit.FLAGSTONE, kit.DARK_STONE),
    "ossuary": room_skin(kit.BRICK, kit.FLAGSTONE, kit.DARK_STONE),
    "tomb": room_skin(kit.OLD_BRICK, kit.FLAGSTONE, kit.BRICK),
}

#: The ground each outdoor room's terrain is laid in: lawn on the hills and
#: the row, the grassy dirt of the old entrance yard at the gate.
GROUND_MATERIAL: Mapping[str, Material] = {
    "gate": kit.GROUND,
    "hills": kit.GRASS,
    "row": kit.GRASS,
}

#: The walks, as axis-aligned centre-line segments ``(key, room, (x0, y0),
#: (x1, y1), half_width)``: in through the gate, a branch to the shed, over
#: the hills to the chapel door, north up to Mausoleum Row, along the row
#: and round to the family vault's door.  Each is laid as a strip of rocky
#: dirt that follows the ground (:func:`_lay_walks`); the path lamps stand
#: either side of them (:mod:`zmforge.recipes.cemetery_dressing`).
PATHS: tuple[tuple[str, str, tuple[float, float], tuple[float, float], float], ...] = (
    ("gate_walk", "gate", (-1460.0, 0.0), (-816.0, 0.0), 88.0),
    ("shed_walk", "gate", (-1550.0, 130.0), (-1550.0, 690.0), 64.0),
    ("hills_walk", "hills", (-784.0, 0.0), (1184.0, 0.0), 88.0),
    ("north_walk", "hills", (200.0, 88.0), (200.0, 1084.0), 72.0),
    ("row_entry", "row", (200.0, 1116.0), (200.0, 1186.0), 72.0),
    ("row_walk", "row", (-700.0, 1250.0), (1164.0, 1250.0), 64.0),
    ("vault_walk", "row", (1100.0, 1314.0), (1100.0, 1436.0), 64.0),
    ("vault_door", "row", (1036.0, 1500.0), (1184.0, 1500.0), 64.0),
)

#: Cobbled forecourts: ``(key, room, x0, y0, x1, y1)`` -- inside the front
#: gate, where the players start, and before the shed door.
FORECOURTS: tuple[tuple[str, str, float, float, float, float], ...] = (
    ("gate_court", "gate", -1780.0, -130.0, -1460.0, 130.0),
    ("shed_court", "gate", -1640.0, 690.0, -1460.0, 780.0),
)

#: How far a walk's surface stands above the ground it follows, and the
#: spacing of its own control grid (a quarter of the hills' cell, so the
#: strip follows the ground's facets closely; see :func:`_strip_field`).
WALK_LIFT = 3.0
WALK_CELL = 21.0


def path_boxes() -> dict[str, tuple[str, float, float, float, float]]:
    """Every walk and forecourt as ``key -> (room, x0, y0, x1, y1)``."""
    boxes: dict[str, tuple[str, float, float, float, float]] = {}
    for key, room_key, (ax, ay), (bx, by), hw in PATHS:
        if ay == by:
            boxes[key] = (room_key, min(ax, bx), ay - hw, max(ax, bx), ay + hw)
        else:
            boxes[key] = (room_key, ax - hw, min(ay, by), ax + hw, max(ay, by))
    for key, room_key, x0, y0, x1, y1 in FORECOURTS:
        boxes[key] = (room_key, x0, y0, x1, y1)
    return boxes


@dataclass(frozen=True)
class CemeteryPlan:
    """Every room's box, so a caller can move one without editing the recipe."""

    gate: Bounds = Bounds.between((-1800, -800, 0), (-800, 800, 448))
    shed: Bounds = Bounds.between((-1800, 800, 0), (-1300, 1400, 224))
    hills: Bounds = Bounds.between((-800, -1100, 0), (1200, 1100, 576))
    row: Bounds = Bounds.between((-800, 1100, 0), (1200, 1800, 448))
    vault: Bounds = Bounds.between((1200, 1300, 0), (1600, 1700, 288))
    chapel: Bounds = Bounds.between((1200, -500, 0), (2000, 500, 416))
    stairs: Bounds = Bounds.between((2000, -480, -240), (2640, -120, 320))
    ossuary: Bounds = Bounds.between((2640, -560, -240), (3280, 160, 16))
    tomb: Bounds = Bounds.between((2640, 160, -240), (3280, 800, 64))
    door_width: float = 112.0
    gate_door_width: float = 128.0
    door_height: float = 128.0
    max_rise: float = DEFAULT_MAX_RISE
    #: Stair flight down to the crypt: 15 steps of 16 is the 240 between the
    #: chapel floor (z 16) and the crypt floor (z -224).
    crypt_steps: int = 15
    step_rise: float = 16.0
    step_run: float = 32.0
    stair_width: float = 128.0


FIXTURE = CemeteryPlan()

#: The rooms below ground: each gets the crypt's thick lit-fog pocket.
CRYPT_ROOMS: tuple[str, ...] = ("stairs", "ossuary", "tomb")

# ---------------------------------------------------------------------------
# Where things stand.  Interactives are fixed points; the terrain is flattened
# under each so a machine is never on a slope.
# ---------------------------------------------------------------------------
START = (-1600.0, 0.0)

#: (key, kind, x, y, facing)
MACHINES: tuple[tuple[str, str, float, float, Facing], ...] = (
    ("gate", "quick_revive", -1600.0, -760.0, Facing.NORTH),
    ("shed", "speed_cola", -1450.0, 1360.0, Facing.SOUTH),
    ("hills", "juggernog", 0.0, -1060.0, Facing.NORTH),
    ("row", "stamin_up", -600.0, 1760.0, Facing.SOUTH),
    ("vault", "mule_kick", 1400.0, 1340.0, Facing.NORTH),
    ("chapel", "double_tap", 1300.0, 460.0, Facing.SOUTH),
    ("ossuary", "deadshot", 3150.0, 120.0, Facing.SOUTH),
)

#: (key, weapon kind, x, y, facing) -- x/y on the wall's inside face.
WALL_BUYS: tuple[tuple[str, str, float, float, Facing], ...] = (
    ("gate", "pistol_burst", -1100.0, 782.0, Facing.SOUTH),
    ("shed", "shotgun_pump", -1782.0, 1000.0, Facing.EAST),
    ("hills", "smg_standard", 400.0, -1082.0, Facing.NORTH),
    ("hills", "ar_standard", 700.0, 1082.0, Facing.SOUTH),
    ("row", "ar_marksman", 500.0, 1782.0, Facing.SOUTH),
    ("chapel", "bowie", 1850.0, 482.0, Facing.SOUTH),
    ("chapel", "smg_fastfire", 1850.0, -482.0, Facing.NORTH),
    ("ossuary", "ar_longburst", 2800.0, -542.0, Facing.NORTH),
    # Not ar_cqb: its prefab's chalk material is not on the install, so it
    # is a buy with no picture (catalogue.WALL_WEAPONS note; the compile
    # log says so too).
    ("tomb", "smg_versatile", 2658.0, 480.0, Facing.EAST),
)

BOX = (-400.0, 1044.0, Facing.SOUTH)
#: Where the box goes when it moves ("The coffin got up and walked off."):
#: the back of Mausoleum Row, behind the small tombs.  A second location
#: is needed: with only one, a box move has nowhere to go.
BOX_MOVES = ((260.0, 1740.0, Facing.SOUTH),)
POWER = (-1680.0, 1360.0, Facing.SOUTH)
PAP = (2960.0, 736.0, Facing.SOUTH)

#: (room key, side, offset along the wall from its midpoint)
WINDOWS: tuple[tuple[str, Side, float], ...] = (
    ("gate", Side.SOUTH, 50.0),
    ("gate", Side.WEST, -500.0),
    ("shed", Side.EAST, 0.0),
    ("hills", Side.SOUTH, -700.0),
    ("hills", Side.SOUTH, 600.0),
    ("row", Side.NORTH, -400.0),
    ("row", Side.NORTH, 700.0),
    ("row", Side.WEST, 0.0),
    ("vault", Side.NORTH, 0.0),
    ("chapel", Side.NORTH, 0.0),
    ("chapel", Side.SOUTH, 0.0),
    ("ossuary", Side.EAST, 0.0),
    ("tomb", Side.EAST, 0.0),
)

#: Extra risers -- zombies climbing out of graves.  (zone, x, y)
RISERS: tuple[tuple[str, float, float], ...] = (
    ("gate", -1250.0, 250.0),
    ("gate", -1000.0, -300.0),
    ("shed", -1600.0, 950.0),
    ("hills", -120.0, -220.0),
    ("hills", 320.0, 260.0),
    ("hills", -560.0, 280.0),
    ("hills", 880.0, 880.0),
    ("hills", 900.0, -780.0),
    ("hills", -600.0, -880.0),
    ("row", 0.0, 1650.0),
    ("row", 950.0, 1250.0),
    ("vault", 1500.0, 1600.0),
    ("chapel", 1800.0, -380.0),
    ("chapel", 1800.0, 380.0),
    ("crypt_stairs", 2580.0, -250.0),
    ("ossuary", 2900.0, -200.0),
    ("tomb", 2760.0, 300.0),
    ("tomb", 3160.0, 300.0),
)

#: The hills: (key, x, y, radius, height) -- each a mound, and the features
#: that stand on top of one are on a plateau pinned at the mound's height.
HILLS: tuple[tuple[str, float, float, float, float], ...] = (
    ("moore_hill", -380.0, -420.0, 440.0, 112.0),
    ("diggs_hill", 650.0, 560.0, 460.0, 136.0),
    ("grave_hill", -300.0, 520.0, 320.0, 56.0),
    ("founder_hill", 520.0, -520.0, 420.0, 152.0),
    ("east_knoll", 950.0, -60.0, 260.0, 48.0),
)

#: The three mausoleums on the hills: (key, family, x, y, facing, plateau).
MAUSOLEUMS: tuple[tuple[str, str, float, float, Facing, float], ...] = (
    ("moore", "MOORE", -380.0, -420.0, Facing.EAST, 112.0),
    ("diggs", "DIGGS", 650.0, 560.0, Facing.SOUTH, 136.0),
)
#: The Founder's needle on the tallest hill, and the Open Grave.
FOUNDER_NEEDLE = (520.0, -520.0, 152.0)
OPEN_GRAVE = (-300.0, 520.0, 56.0)
#: The GRAVES mausoleum stands on Mausoleum Row with the small tombs.
ROW_TOMBS: tuple[tuple[str, float, float, Facing], ...] = (
    ("graves", -380.0, 1450.0, Facing.SOUTH),
    ("small_a", 20.0, 1480.0, Facing.SOUTH),
    ("small_b", 420.0, 1480.0, Facing.SOUTH),
    ("small_c", 820.0, 1450.0, Facing.SOUTH),
)


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------
#: Grid per outdoor room: (cols, rows).  Chosen so the cells come out within
#: two units of square on each interior (see Blueprint._terrain_fitted_to_its_room).
TERRAIN_GRID: Mapping[str, tuple[int, int]] = {
    "gate": (12, 19),
    "hills": (24, 26),
    "row": (24, 8),
}


def outdoor_discs(key: str, rooms: Mapping[str, object], plan: CemeteryPlan) -> list[Disc]:
    """Every flat spot an outdoor room's ground must keep: door sills, window
    sills, machines, wall buys, the box, the start, and the plateaus."""
    room = rooms[key]
    discs: list[Disc] = []
    for opening_box in room.aperture_boxes:
        cx = (opening_box.mins.x + opening_box.maxs.x) / 2.0
        cy = (opening_box.mins.y + opening_box.maxs.y) / 2.0
        discs.append(Disc(cx, cy, 120.0, 0.0, square=True))
    for zone_key, _kind, x, y, _f in MACHINES:
        if zone_key == key:
            discs.append(Disc(x, y, 104.0, 0.0, square=True))
    for zone_key, _kind, x, y, _f in WALL_BUYS:
        if zone_key == key:
            discs.append(Disc(x, y, 104.0, 0.0, square=True))
    if key == "gate":
        discs.append(Disc(START[0], START[1], 140.0, 0.0, square=True))
        discs.append(Disc(room.interior.mins.x + 40.0, 0.0, 160.0, 0.0, square=True))
    if key == "row":
        for bx, by, _f in BOX_MOVES:
            discs.append(Disc(bx, by, 150.0, 0.0, square=True))
    if key == "hills":
        discs.append(Disc(BOX[0], BOX[1], 150.0, 0.0, square=True))
        for _k, _fam, x, y, _f, h in MAUSOLEUMS:
            discs.append(Disc(x, y, 150.0, h, square=True))
        fx, fy, fh = FOUNDER_NEEDLE
        discs.append(Disc(fx, fy, 64.0, fh, square=True))
        gx, gy, gh = OPEN_GRAVE
        discs.append(Disc(gx, gy, 90.0, gh, square=True))
    if key == "row":
        for _k, x, y, _f in ROW_TOMBS:
            discs.append(Disc(x, y, 140.0, 0.0, square=True))
    return discs


def _lay_ground(bp: Blueprint, key: str, room, rooms, plan: CemeteryPlan) -> Terrain:
    cols, rows = TERRAIN_GRID[key]
    inside = room.interior
    cell_x = (inside.maxs.x - inside.mins.x) / cols
    cell_y = (inside.maxs.y - inside.mins.y) / rows
    anchor = Point(inside.mins.x, inside.mins.y, room.floor_z)
    if key == "hills":
        mounds = [Mound(x, y, r, h) for _k, x, y, r, h in HILLS]
        noise, seed = 10.0, 1897
    elif key == "gate":
        mounds = [Mound(-1180.0, 360.0, 300.0, 44.0), Mound(-1080.0, -380.0, 260.0, 36.0),
                  Mound(-1500.0, 480.0, 200.0, 28.0)]
        noise, seed = 6.0, 1898
    else:
        mounds = [Mound(-150.0, 1700.0, 220.0, 28.0), Mound(620.0, 1250.0, 200.0, 24.0),
                  Mound(1000.0, 1700.0, 180.0, 30.0)]
        noise, seed = 6.0, 1899
    field = rolling_hills(anchor, cols, rows, cell_x, cell_y=cell_y, mounds=mounds,
                          noise_peak=noise, seed=seed)
    pins = pin_discs(anchor, field, cell_x, outdoor_discs(key, rooms, plan), cell_y=cell_y)
    field = limit_rise(field, plan.max_rise, pinned=cap_pins(pins, plan.max_rise))
    material = GROUND_MATERIAL[key]
    return bp.add_terrain(field, anchor, cell_x, style="mesh", material=material,
                          lift=2.0, texture_scale=kit.terrain_texture_scale(material),
                          id=f"{key}_ground")


def _strip_field(bp: Blueprint, x0: float, y0: float, x1: float, y1: float,
                 floor_z: float) -> tuple[object, Point, float]:
    """A heightfield over ``[x0, x1] x [y0, y1]`` that follows the ground.

    Sampled from the room's terrain every :data:`WALK_CELL` units and lifted
    :data:`WALK_LIFT`, so the strip lies just over the grass however the hill
    under it runs.  The field is padded by one cell on its far sides
    (:func:`zmforge.surfaces.patches.mesh_chunks`), so it is sampled one
    cell short of the far edges and the padding meets them.
    """
    from ..surfaces.field import HeightField

    # One cell size for both axes (add_terrain takes one for a patch of
    # ground): fitted exactly along the walk, and the width rounded down to
    # whole cells and centred.
    width, depth = x1 - x0, y1 - y0
    if width >= depth:
        cols = max(1, round(width / WALK_CELL))
        step = width / cols
        rows = max(1, math.floor(depth / step))
        pad = (depth - rows * step) / 2.0
        y0, y1 = y0 + pad, y1 - pad
    else:
        rows = max(1, round(depth / WALK_CELL))
        step = depth / rows
        cols = max(1, math.floor(width / step))
        pad = (width - cols * step) / 2.0
        x0, x1 = x0 + pad, x1 - pad
    step_x = step_y = step
    def ground(x: float, y: float) -> float:
        return bp.ground_under(x, y).z

    heights = []
    for r in range(rows):
        row = []
        for c in range(cols):
            x, y = x0 + c * step_x, y0 + r * step_y
            # The last row and column also stand for the padded edge one
            # step on, which copies their height: take the higher of the two
            # so that last cell never dips into the slope.
            xs = (x, x1) if c == cols - 1 else (x,)
            ys = (y, y1) if r == rows - 1 else (y,)
            z = max(ground(px, py) for px in xs for py in ys)
            row.append(z - floor_z + WALK_LIFT - 2.0)
        heights.append(row)
    return HeightField.from_rows(heights), Point(x0, y0, floor_z), step


def _lay_walks(bp: Blueprint, rooms) -> list[Terrain]:
    """The walks (rocky dirt) and the forecourts (cobbles), laid over the
    outdoor ground as strips of mesh that follow it.  Each is a patch of
    ground inside its room, not the room's floor, so
    ``Blueprint._terrain_fitted_to_its_room`` leaves it where it is put."""
    laid = []
    courts = {key for key, *_ in FORECOURTS}
    for key, (room_key, x0, y0, x1, y1) in path_boxes().items():
        inside = rooms[room_key].interior
        x0, x1 = max(x0, inside.mins.x + 2.0), min(x1, inside.maxs.x - 2.0)
        y0, y1 = max(y0, inside.mins.y + 2.0), min(y1, inside.maxs.y - 2.0)
        field, anchor, cell = _strip_field(bp, x0, y0, x1, y1, rooms[room_key].floor_z)
        material = kit.COBBLE if key in courts else kit.PATH
        pixels = kit.TEXTURE_PIXELS.get(material.name, 1024)
        laid.append(bp.add_terrain(field, anchor, cell, style="mesh", material=material,
                                   lift=2.0, texture_scale=float(material.scale) / pixels,
                                   id=f"{key}_path"))
    return laid


def terrain_report(bp: Blueprint, key: str):
    """The slope report of one outdoor room's ground, for the tests."""
    record = bp.find(f"{key}_ground").record
    return slope_report(record.heights, record.x_cell, record.y_cell)


# ---------------------------------------------------------------------------
# The map
# ---------------------------------------------------------------------------
def cemetery_map(
    name: str,
    plan: CemeteryPlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
    atmosphere: Atmosphere = NIGHT_GLOOM,
    starting_points: int | None = None,
    gobblegums: int | None = None,
) -> Blueprint:
    """Hollow Rest Cemetery at night: see the module docstring.

    ``starting_points`` is a testing aid (``zmforge generate
    --starting-points``), as on the DMV: every player starts with that many
    points.  ``None`` leaves the stock 500."""
    return build_cemetery(name, plan, seed=seed, player_slots=player_slots,
                          atmosphere=atmosphere, starting_points=starting_points,
                          gobblegums=gobblegums)[0]


def cemetery_dusk_map(
    name: str,
    plan: CemeteryPlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
    starting_points: int | None = None,
    gobblegums: int | None = None,
) -> Blueprint:
    """The same map at sunset (:data:`zmforge.atmosphere.DUSK_GROUND_FOG`),
    for a tools tree without The Giant's sky images."""
    return build_cemetery(name, plan, seed=seed, player_slots=player_slots,
                          atmosphere=DUSK_GROUND_FOG, starting_points=starting_points,
                          gobblegums=gobblegums)[0]


def build_cemetery(
    name: str,
    plan: CemeteryPlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
    atmosphere: Atmosphere = NIGHT_GLOOM,
    starting_points: int | None = None,
    gobblegums: int | None = None,
) -> tuple[Blueprint, dict]:
    """:func:`cemetery_map`, plus what the tests read: ``rooms`` (key ->
    room), ``features`` (see :func:`~zmforge.recipes.cemetery_dressing.dress`),
    ``notices`` (key, point) for every readable spot, and ``quest``."""
    bp = Blueprint(name, seed=seed, title=MAP_TITLE)
    W = _WALL

    def room(key, box, *, outdoor=False):
        return bp.add_room(box, wall=W, roofed=not outdoor, sunlit=outdoor,
                           wall_height=OUTDOOR_WALL.get(key) if outdoor else None,
                           materials=SKINS[key], id=f"{key}_room")

    gate = room("gate", plan.gate, outdoor=True)
    shed = room("shed", plan.shed)
    hills = room("hills", plan.hills, outdoor=True)
    row = room("row", plan.row, outdoor=True)
    vault = room("vault", plan.vault)
    chapel = room("chapel", plan.chapel)
    stairs = room("stairs", plan.stairs)
    ossuary = room("ossuary", plan.ossuary)
    tomb = room("tomb", plan.tomb)
    rooms = {"gate": gate, "shed": shed, "hills": hills, "row": row, "vault": vault,
             "chapel": chapel, "stairs": stairs, "ossuary": ossuary, "tomb": tomb}

    ground = gate.floor_z
    crypt = stairs.floor_z
    dw, dh = plan.door_width, plan.door_height
    # The shed's doorway stays open (no door): the way to the power switch.
    link_rooms(bp, gate, Side.NORTH, shed, Side.SOUTH, centre=-1550.0,
               width=dw, height=dh, bottom_z=ground)
    to_hills, _ = link_rooms(bp, gate, Side.EAST, hills, Side.WEST, centre=0.0,
                        width=plan.gate_door_width, height=dh + 16, bottom_z=ground)
    to_row, _ = link_rooms(bp, hills, Side.NORTH, row, Side.SOUTH, centre=200.0,
                      width=plan.gate_door_width, height=dh + 16, bottom_z=ground)
    to_vault, _ = link_rooms(bp, row, Side.EAST, vault, Side.WEST, centre=1500.0,
                        width=dw, height=dh, bottom_z=ground)
    to_chapel, _ = link_rooms(bp, hills, Side.EAST, chapel, Side.WEST, centre=0.0,
                         width=plan.gate_door_width, height=dh + 32, bottom_z=ground)
    to_stairs, _ = link_rooms(bp, chapel, Side.EAST, stairs, Side.WEST, centre=-300.0,
                         width=dw, height=dh, bottom_z=ground)
    to_ossuary, _ = link_rooms(bp, stairs, Side.EAST, ossuary, Side.WEST, centre=-300.0,
                          width=dw, height=dh, bottom_z=crypt)
    to_tomb, _ = link_rooms(bp, ossuary, Side.NORTH, tomb, Side.SOUTH, centre=2960.0,
                       width=dw, height=dh, bottom_z=crypt)

    zones = {
        "gate": bp.add_zone("gate", gate, starting=True),
        "shed": bp.add_zone("shed", shed),
        "hills": bp.add_zone("hills", hills),
        "row": bp.add_zone("row", row),
        "vault": bp.add_zone("vault", vault),
        "chapel": bp.add_zone("chapel", chapel),
        "crypt_stairs": bp.add_zone("crypt_stairs", stairs),
        "ossuary": bp.add_zone("ossuary", ossuary),
        "tomb": bp.add_zone("tomb", tomb),
    }
    zone_room = {"crypt_stairs": "stairs"}
    # Every area is a scene (docs/map-design-method.md).
    from .cemetery_scenes import declare_scenes

    declare_scenes(bp, zones)

    # Windows first: each one cuts a hole the terrain has to meet.
    for key, side, offset in WINDOWS:
        zone_name = next((z for z, r in zone_room.items() if r == key), key)
        bp.add_window(zones[zone_name], rooms[key], side, offset,
                      id=f"{key}_window_{side.name.lower()}_{int(offset)}")

    # The ground outdoors, graded to every sill and machine.
    for key in ("gate", "hills", "row"):
        _lay_ground(bp, key, rooms[key], rooms, plan)
    # The walks and forecourts over it (a clear pathway).
    _lay_walks(bp, rooms)

    def gz(x: float, y: float) -> float:
        return bp.ground_under(x, y).z

    # The stair down to the crypt, against the chapel door (see the plan).
    bp.add_steps(
        Point(stairs.interior.mins.x + plan.crypt_steps * plan.step_run,
              -300.0 - plan.stair_width / 2.0, crypt),
        plan.crypt_steps, plan.step_run, plan.step_rise, plan.stair_width,
        Facing.WEST, kit.DARK_STONE, id="crypt_stairs",
    )

    bp.set_player_start(Point(START[0], START[1], gz(*START) + 16.0), Facing.EAST,
                        slots=player_slots)

    for key, kind, x, y, facing in MACHINES:
        zone_name = next((z for z, r in zone_room.items() if r == key), key)
        bp.place_perk(kind, Point(x, y, gz(x, y)), facing, id=f"perk_{kind}")
    for key, kind, x, y, facing in WALL_BUYS:
        bp.place_wall_weapon(kind, Point(x, y, gz(x, y) - 8.0), facing,
                             id=f"{key}_wallbuy_{kind}")
    bp.place_mystery_box(Point(BOX[0], BOX[1], gz(BOX[0], BOX[1])), BOX[2], id="hills_box")
    for n, (bx, by, bf) in enumerate(BOX_MOVES):
        bp.place_mystery_box(Point(bx, by, gz(bx, by)), bf, starting=False, id=f"row_box_{n}")
    bp.place_power_switch(Point(POWER[0], POWER[1], gz(POWER[0], POWER[1]) + 8.0), POWER[2],
                          id="shed_power")
    bp.place_pack_a_punch(Point(PAP[0], PAP[1], gz(PAP[0], PAP[1]) + 4.0), PAP[2],
                          id="tomb_pap")

    for index, (zone_name, x, y) in enumerate(RISERS):
        bp.add_riser(zones[zone_name], Point(x, y, gz(x, y)), Facing.NORTH,
                     id=f"{zone_name}_riser_{index}")

    # Doors: the iron gates between the grounds, the chapel's front door, and
    # the crypt door behind the altar on the electric lock.
    # The shed is an open doorway (players go to the
    # groundskeeper's shed first), and the first door on, the hills gate, sells
    # only once the power is on (the stock electric_buyable_door).
    bp.script.edges.append(ZoneEdge(zones["gate"].name, zones["shed"].name,
                                    bp.script.always_on_flag))
    bp.add_door((zones["gate"], zones["hills"]), to_hills, price=PRICES["gate_hills"],
                requires_power=True, id="door_gate_hills")
    bp.add_door((zones["hills"], zones["row"]), to_row, price=PRICES["hills_row"],
                id="door_hills_row")
    bp.add_door((zones["row"], zones["vault"]), to_vault, price=PRICES["row_vault"],
                id="door_row_vault")
    bp.add_door((zones["hills"], zones["chapel"]), to_chapel, price=PRICES["hills_chapel"],
                id="door_hills_chapel")
    bp.add_door((zones["chapel"], zones["crypt_stairs"]), to_stairs,
                price=PRICES["chapel_crypt"], electric=True, id="door_crypt_electric")
    bp.add_door((zones["crypt_stairs"], zones["ossuary"]), to_ossuary,
                price=PRICES["stairs_ossuary"], id="door_stairs_ossuary")
    bp.add_door((zones["ossuary"], zones["tomb"]), to_tomb, price=PRICES["ossuary_tomb"],
                id="door_ossuary_tomb")

    for kind, line in PROMPTS.items():
        bp.rename_weapon_prompt(WALL_WEAPON_WEAPONS.get(kind, kind), line)

    from .cemetery_dressing import dress, wire_gags, wire_notices

    features = dress(bp, plan, rooms)
    # The path lanterns and the wisps glow in the lit fog (zmforge.atmosphere).
    from ..blueprint.elements import Lamp

    for lamp in bp.elements(Lamp):
        if "lantern" in lamp.id or "wisp" in lamp.id or lamp.id.startswith("path_lamp"):
            lamp.volumetric = True
    notices = wire_notices(bp, plan, rooms, features)
    wire_gags(bp)

    # The quest, its objective HUD, the Gravedigger and the 20,000 ending
    # (zmforge.recipes.cemetery_quest, on the shared quest framework).
    from ..script.quest import install_quest
    from .cemetery_quest import cemetery_quest

    quest = cemetery_quest(features, rooms)
    install_quest(bp, quest)

    if starting_points is not None:
        from ..script.tricks import starting_points as _starting_points

        bp.add_custom_logic(_starting_points(starting_points))

    bp.set_dog_rounds(False)
    enclosure = bp.enclose(id="enclosure", atmosphere=atmosphere)
    if atmosphere.lit_fog is not None:
        # The crypt's own thicker, colder fog, one nested lit-fog pocket per
        # room below ground (zmforge.atmosphere.CRYPT_LIT_FOG).
        enclosure.lit_fog_pockets = tuple(
            (rooms[key].interior, CRYPT_LIT_FOG) for key in CRYPT_ROOMS)
    # GobbleGum beside the boxes, off above four players (script.gobblegum).
    from ..script.gobblegum import place_gobblegum_machines

    place_gobblegum_machines(bp, gobblegums)
    from .cemetery_dressing import clear_grass_from_interactives

    clear_grass_from_interactives(bp)
    # Pieces a later pass left half on a plinth or a grave edge (Z44).
    from ..placement.audit import drop_unsupported_dressing

    bp.unsupported_dropped = drop_unsupported_dressing(  # type: ignore[attr-defined]
        bp, contains=("_wallfoot_", "_backdrop_trees"), overlaps=True)
    bp.light_rooms()
    return bp, {"rooms": rooms, "features": features, "notices": notices, "quest": quest,
                "zones": zones}
