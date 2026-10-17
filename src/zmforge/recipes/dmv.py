"""DMV of the Damned: a branch office, the queue in it, and nobody to serve you.

A joke map built the way the other recipes in this package are built -- one
call per room, one call per door, every number in a dataclass a caller can
replace -- with the same rule about where the jokes come from: they are picked
off the placement calls that already exist rather than paid for with new
engine features.

**It is laid out like a real one.**  Not as a flourish: the arrangement is the
gag.  A motor vehicle branch is a public half and a staff half with a counter
run between them, and the only way from one to the other is a gate at the end
of the counter -- which is a requirement, not a habit.  PennDOT's photo licence
centre co-location requirements, 4.1.3: "Employee workstations must be behind
the PLC customer service counter area and accessible from the public service
area only through a gate or a door", and 4.1.4, "a counter, located directly in
front of the employee workstations".  So this map's back of house really is
behind the counter, and walking into it is walking round the end of the run
past the EMPLOYEES ONLY sign.  :func:`counter_run` is where that line is.

The site, west to east::

    lot          **the map starts outside.**  the car park: two rows of
                 marked bays with twelve cars still parked in them, two
                 accessible ones and their access aisles
                 either side of the covered walk, a kerbed footway across the
                 frontage, a planted boundary with the risers in it, and the
                 starter sidearm on the wall beside the front door
    entry        the lobby you come in to: the ticket machine (TAKE A NUMBER)
                 immediately inside the door where a number dispenser
                 actually lives, the publications rack opposite, and a
                 self-service kiosk that has never worked
    waiting      ten chairs in two rows facing the counter, a wall of clocks,
                 paperwork on the floor, and Quick Revive
    windows      the counter hall, and the building's spine.  A two-tier
                 counter run crossing it north to south: a partition wall
                 with one service window in it, the NOW SERVING board over
                 it, the lowered ADA section at the south end, the staff
                 gate at the north end, and behind it the employee
                 workstations, the file cabinets and the door to the store.
                 Juggernog and the registration desk (VEHICLE REGISTRATION
                 FEE) stand on the public floor, one at each end
    eye exam     off the *public* side: the chart, in five rows of descending
                 size, and a shotgun whose prompt reads the bottom line out
                 for you
    photo booth  step in, the flash goes off, and you come out facing the
                 other way
    break room   off the staff side, because a staff break room is back of
                 house: the donut box, the coffee, and the breaker for the
                 whole building
    records      the secure store behind the counter: cabinets, shelves,
                 filed paper, Speed Cola, and the mystery box.  No windows in
                 it, which is what a store is required to be (PennDOT 4.2.1:
                 64 square feet minimum, "solid core door construction... no
                 windows, secured ceiling, and a deadbolt lock")
    queue        the switchback, and the pack-a-punch at the end of it
    back office  the operator's window, Stamin-Up, and the stapler

**Which numbers are sourced and which are assumed.**  Every measured one is
cited on the field in :class:`DmvPlan` that carries it.  Sourced: the counter
gate (PennDOT 4.1.3), the counter in front of the workstations (4.1.4), ten
waiting chairs per camera system (4.1.5), the windowless secure store
(4.2.1), the 36-inch lowered counter section and the 36-inch counter height
cap (ADA 904.4.1), the 28.5-inch staff work surface (UC Berkeley's customer
service counter design guidelines), and the 36-inch accessible route.
Assumed, and said so: the centre-to-centre pitch of one service window to the
next -- **no published figure for it was found** -- and every car park
dimension, which are the ordinary suburban ones rather than anything a
motor vehicle department publishes.

**Two counter heights are the engine's, not the code's.**  ADA caps a service
counter at 36 and this engine's jump is 39
(:data:`zmforge.verify.reachability.JUMP_UP`), so a counter built to code is a
step and the public side and the staff side stop being two places.  The run is
42 and the lowered section 40, one unit clear of the jump, and that compromise
is written into the fields rather than hidden in them.

**What it is made of.**  A slightly shabby branch office, inside and out,
out of stock surfaces the install carries (:data:`SKINS` and the table above
it): linoleum, ceramic and stone tile on the public floors and carpet behind
the counter; off-white plaster and worn paint on the walls, wood panelling
behind the staff, glazed tile in the break room; a white acoustic ceiling
with 2x4 light fittings in it.  Every roofed room has a rubber base, a
ceiling moulding and a metal frame round each doorway.  Outside, the car park
is asphalt with a slab footway and a concrete kerb, a lawn in the planted
bed, and the building's street face is red brick over a concrete base band
with pilasters, four framed windows, a sign band over a rubber-roofed canopy,
a cornice and a coping.  ``tests/test_dmv.py`` pins the table and counts the
variety.  The first cut used only the twelve measured names of
:data:`zmforge.materials.SURFACE_CATALOGUE` and read as plain in play.

**Twelve cars are still parked in the car park** (:data:`LOT_CARS`):
the compact, the city car, the GT and a burnt-out city car, solid,
in twelve of the twenty bays a car can use, two of them abandoned askew.
The map needs the civilian cars' stock ``model_export`` folders from the mod
tools, because the link packs a placed car from its LOD0 binary there;
without them the lot stands empty.  The level-common list a usermap gets for free
still holds no vehicle, which is why the registration machine is not shaped
like a car (:func:`vehicle_registration_perk`); a placed ``misc_model`` is
packed from ``model_export`` instead.  The hot-dog cart is still left across
a bay in the far row.  The lot has no roof: the sky over it is the
enclosure's (``default_day``).

**After the outbreak.**  :func:`_furnish_character` is the pass that makes
it a DMV the zombies got to: boards over the street windows and sandbags
under one, what is left of customer 846 still in his seat (the seat height
is measured, :data:`WAITING_SEAT_TOP`), a chair turned to the wall, a teddy
keeping somebody's place, a suggestion box, a broken water cooler, anatomy
charts in the eye test, rejected photos, Gary's retirement cake, a
survivor's camp among the records, a bottle on the manager's desk, and paper
everywhere.  The jokes that need words are :data:`NOTICE_LINES`: use
triggers with the map's own text on them (the forms rack's Form 27-B, POSITION
the SERVICE WINDOW notice, the eye test,
the photo that must not smile, the note on the fridge, SPEAK TO A MANAGER,
and the queue's own signs), placed by :func:`_notice_spots` clear of every
purchase.  Nothing can be tipped over -- a prop has a yaw and nothing else --
and there is no blood: a decal is only emitted under a wall buy's chalk.

**The queue is the map.**  The pack-a-punch is not in a room you open, it is
at the end of a roped line you walk: three legs of :data:`DmvPlan.lane_width`
-wide lane between rails too tall to hop (48 units against
:data:`zmforge.verify.reachability.JUMP_UP`'s 39), with the turns at
alternating ends.  Coming in off the records room the line also offers a
second branch, and that one runs two legs and dead-ends in the corner beside
the door you came through, which is the whole joke: a first-timer walks the
queue twice.  :func:`queue_route` and :func:`queue_dead_end` are those two
walks as lists of points, so a test can measure them instead of trusting this
paragraph.

**The boss, and the way out.**  The DMV operator is the
final boss.  The back office is still the arena it was -- the operator's
counter wall to wall with a service slot and one 164-unit gap at the east
end, buying the door releases the sprinters behind the counter
(``closet_ambush``) and runs the spawns hot for twenty seconds
(``spawn_spike_on_flag``) -- and it now also holds THE EXAMINER, the last of
four registrations the map asks for (:mod:`zmforge.recipes.dmv_quest`, wired
by :func:`_wire_quest`).  Vision test (shoot E, F, P on the eye chart), photo
ID (knife the camera after its flash), written test (three forms to window
3), road test (kill THE EXAMINER); then the front door sells "Leave the DMV"
for 20,000 and ends the game as a win.  THE EXAMINER is an ordinary zombie
from the framework's own spawner made tougher, glowing and named on screen
(:mod:`zmforge.script.bosses`): the mod tools ship no special-enemy aitype a
usermap could use instead (``docs/special-enemies.md``).

**Two gags are left out**, and for the same
reason -- there is nothing to build them out of and inventing it would be
inventing an asset or an engine feature.  A second, *pristine* perk machine
standing beside the working one needs a vending model as a prop, and the two
in the palette (``p7_zm_vending_widows_wine``, ``p7_zm_vending_nuke``) have no
measured box and are ``unverified`` in the install ledger, so a solid one
would ship with no collision and a hollow one is walked through.  A donut box
that heals or pays needs a perk effect this package does not have:
:mod:`zmforge.script.perks` offers two,
:func:`~zmforge.script.perks.points_each_round` and
:func:`~zmforge.script.perks.move_speed`, and neither of them heals -- the
first is spent on the ticket machine and the second on the registration desk.
The break room's donuts are therefore scenery and its reason to exist is the
power switch.

**The registration desk is not shaped like a car**, though a car would
suit it.  A perk machine's model is set at run time, so it has to be a model the
fastfile already carries, and the level-common list a usermap gets for free
holds 326 xmodels and no vehicle; the install's GDTs declare a dozen cars and
not one of them has a measured box, so none can be placed where it looks.  It
would change nothing if one did: the machine's collision is the framework's
own ``zm_collision_perks1`` clip, sized for a vending machine, so a car model
would draw a car a player walks most of the way through.  See
:func:`vehicle_registration_perk`.

**Nobody has played this.**  Every claim here is a property of the model or of
the text a commit writes, checked by ``tests/test_dmv.py``; none of it is an
observation of a session.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..blueprint.catalogue import WALL_WEAPON_WEAPONS
from ..blueprint.elements import (
    FLOATS_ON_PURPOSE,
    STOCK_PLAYER_SLOTS,
    Massing,
    PropScatter,
    RoomMaterials,
)
from ..placement.relations import Placed
from ..atmosphere import OFFICE_DAY
from ..blueprint.model import Blueprint
from ..materials import CAULK, CLIP, FaceMaterials, Material
from ..script.perks import (
    DIVE_TO_NUKE_ICON,
    CustomPerk,
    move_speed,
    points_each_round,
)
from ..script.tricks import (
    STOCK_STARTING_POINTS,
    closet_ambush,
    short_hop_teleporter,
    spawn_spike_on_flag,
    starting_points as _starting_points_logic,
    TicketCalls,
    take_a_ticket,
    use_notices,
)
from ..solids.layout import Aperture
from ..spatial import Bounds, Facing, Point, Side
from .props import MODEL_BOX, SEAT_TOP, collision_box
from ..dressing import centred as _centred
from ..dressing import mounted as _mounted
from ..dressing import on_floor as _floor
from ..dressing import on_surface as _on
from ..dressing import rest_on as _rest_on
from ..dressing import room_skin
from ..dressing import seated as _seated
from ..dressing import top_of as _top_of
from ..dressing import floor_footprints

__all__ = [
    "DmvPlan",
    "FIXTURE",
    "PRICES",
    "dmv_of_the_damned",
    "take_a_number_perk",
    "queue_route",
    "queue_dead_end",
    "counter_run",
    "bay_centres",
    "bay_pitch",
    "window_opening",
    "window_y",
    "parking_bays",
    "PROMPTS",
]


#: Every door costs the same thousand, which is what
#: a test map charges and what a player expects of an opening.  The
#: DMV's joke is the distance, not the fee.
#: The map's menu title (the zone's ``title``), not the derived "Dmv".
MAP_TITLE = "DMV of the Damned"

PRICES: dict[str, int] = {
    # Rising with depth, which is the rule players read a map by: the front
    # door is cheap, each room further from the car park costs more, and the
    # last door before the boss is the dearest.  Flat prices read as
    # prices that never rise.
    "lot_entry": 750,
    "entry_waiting": 1000,
    "waiting_windows": 1250,
    "waiting_photo": 1250,
    "windows_break": 1500,
    "windows_eye_exam": 1250,
    "windows_records": 1500,
    "records_queue": 2000,
    "queue_office": 2500,
}

#: The four wall buys whose prompt this map rewrites, weapon -> line.  The
#: prompt is the one piece of text a usermap can put in a player's face
#: without art: :meth:`zmforge.blueprint.model.Blueprint.rename_weapon_prompt`
#: owns ``level.zombie_weapons[weapon].hint`` between the framework assigning
#: it and the framework reading it back, and the map's own ``.str`` file
#: carries the words.  So the stapler's requisition and the carry permit
#: are said rather than drawn -- this map cuts no art and copies none.  (The
#: eye chart's letters are drawn in brushes, and its bottom line, R U N, is
#: said here as well.)
PROMPTS: dict[str, str] = {
    "pistol_burst": "FORM 1911: STARTER SIDEARM",
    "smg_standard": "CARRY PERMIT (EXPIRED)",
    "shotgun_pump": "EYE TEST, LINE FIVE: R U N",
    "bowie": "STAPLER -- SUPPLY REQUISITION APPROVED",
}

#: Take a number (:func:`zmforge.script.tricks.take_a_ticket`, design).  The kiosk in the lobby hands out tickets 1 to
#: :data:`TICKET_NUMBERS`, one per player, never one another player holds.
#: From round :data:`TICKET_OPEN_ROUND` the PA calls a number every
#: :data:`TICKET_CALL_SECONDS`; its holder has :data:`TICKET_GRACE_SECONDS` to
#: be standing at the service window (the hall has one).  Served: the
#: points and a powerup; missed: the ticket is void.  Being served is the
#: quest's Take a Number stamp (:mod:`zmforge.recipes.dmv_quest`).
TICKET_NUMBERS = 10
#: Seconds between two calls (about once a minute).
TICKET_CALL_SECONDS = 60.0
#: Seconds the holder has to reach the window after their number is called.
#: A deliberately tight window; at a run that is about 3 s x 190 units/s,
#: so in practice you must already be waiting near the window.  Tune here.
TICKET_GRACE_SECONDS = 3.0
#: The first round the window calls numbers; before it the kiosk still hands
#: out tickets and says the window opens then.
TICKET_OPEN_ROUND = 5
#: Percent of calls that pick a number someone not yet served holds: all of
#: them (a call that names a number nobody holds is
#: wasted).  The longest-waiting holder is called first, and a minute with
#: no unserved holder has no call.
TICKET_HELD_CHANCE = 100
#: Index of the quest's Take a Number step in ``level.zmf_q_state``
#: (``dmv_quest``'s step order); when it reads 2 (done) the calls stop.
TICKET_QUEST_STEP = 3
#: Points for being served, on top of the powerup.
TICKET_REWARD_POINTS = 1000
#: How near the ticket window's floor point counts as "at the window".
TICKET_WINDOW_RADIUS = 96.0

#: The ticket lines.  ``&&1`` is the ticket or called number (``served_all``:
#: the served player); ``&&2`` on the ``hud_`` lines is the seconds left.
#: ``{r}`` and ``{p}`` are filled in when the map is built with
#: :data:`TICKET_OPEN_ROUND` and :data:`TICKET_REWARD_POINTS`.  No line
#: names a window number: the hall has one service window.
#: ``prompt`` and ``number`` are ``triggerstring``; the rest ``string``.
TICKET_LINES: dict[str, str] = {
    "prompt": "Hold ^3[{+activate}]^7 to ^3TAKE A NUMBER^7",
    "number": "You are number ^3&&1^7. Wait by the ^3SERVICE WINDOW^7.",
    "yours": "YOUR TICKET: ^3&&1^7. Wait by the ^3SERVICE WINDOW^7 for your call.",
    "yours_early": "YOUR TICKET: ^3&&1^7. The window opens at round {r}.",
    "welcome": "Welcome to the DMV. Please ^3TAKE A NUMBER^7 at the kiosk.",
    "mine": "TICKET ^3&&1^7 - wait by the service window",
    "mine_early": "TICKET ^3&&1^7 - the window opens at round {r}",
    "opened": "^3PA:^7 THE SERVICE WINDOW IS NOW OPEN. Numbers are called every minute.",
    "call": "^3PA:^7 NOW SERVING NUMBER ^3&&1^7",
    "you": "^3THAT'S YOU!^7 Number ^3&&1^7: get to the ^3WINDOW^7!",
    "hud_call": "NOW SERVING ^3&&1^7: &&2",
    "hud_you": "^1NUMBER &&1 - THAT'S YOU!^7 GO TO THE WINDOW: &&2",
    "served": "Your paperwork has been processed. ^3+{p}^7 and a complimentary power-up.",
    "served_all": "&&1 has been served at the window.",
    "missed": "^3PA:^7 NUMBER ^3&&1^7? ... It has been given to the next person.",
    "no_one": "^3PA:^7 NUMBER ^3&&1^7? ... No one? Next!",
    "already": "You have already been served. Please exit the line.",
}


def ticket_lines(plan: "DmvPlan") -> dict[str, str]:
    """:data:`TICKET_LINES` with the round and reward filled in."""
    fill = {"r": TICKET_OPEN_ROUND, "p": f"{TICKET_REWARD_POINTS:,}"}
    return {key: text.replace("{r}", str(fill["r"])).replace("{p}", fill["p"])
            for key, text in TICKET_LINES.items()}


def ticket_window_point(plan: "DmvPlan", rooms: Mapping[str, object]) -> Point:
    """Where a called player stands to be served: the public floor in front
    of the service window, where the ``now_serving`` notice stands."""
    face_x = counter_run(plan)[0]
    return Point(face_x - 60.0, window_y(plan),
                 rooms["waiting"].floor_z)


#: The on-screen gags (:func:`_wire_gags`, built out of
#: :mod:`zmforge.script.gags`), key -> line.  Every one is said in the
#: player's face at the moment it is about, so nobody has to find a prompt to
#: get the joke.  The key's prefix says what fires it:
#:
#: No zone sign-ins and no round-end PA (P13, P17): the only
#: PA voice is the ticket window's calls, :data:`TICKET_LINES`.
#:
#: each key         one event (downed, revived, a perk, the box, ...);
#:                   ``*_feed`` lines go to the other players' kill feed with
#:                   the player as ``&&1``.
GAG_LINES: dict[str, str] = {
    # Going down and getting up.
    "downed": "Your license has been ^1SUSPENDED^7.",
    "downed_feed": "&&1's license has been ^1SUSPENDED^7.",
    "bled_out_feed": "&&1's license has been ^1REVOKED^7. Next!",
    "revived": "License reinstated. The ^3$25^7 reinstatement fee has been deducted.",
    "revived_broke": "License reinstated. You cannot afford the ^3$25^7 fee. "
                     "It has been added to your file.",
    "reviver": "You reinstated &&1's license. Please file Form 27-B.",
    # Buying things.
    "perk_registration": "Vehicle registration fee paid. You may now drive (run).",
    "perk_ticket": "Preferred Customer status approved. "
                   "Your wait is still three to five business eternities.",
    "pap": "Your paperwork has been ^3UPGRADED^7.",
    "box": "MYSTERY BOX: Please take a number.",
    "box_moved": "The Mystery Box has moved to another window. Please rejoin the line.",
    # The two hops, said out loud.
    "express": "EXPRESS LANE: You have been moved to the ^3back of the line^7.",
    "express_feed": "&&1 took the Express Lane.",
    "booth": "^3*FLASH*^7 License photo taken. You were facing the wrong way.",
    # Standing about.
    "idle": "You have been waiting patiently. Your patience has been noted and filed.",
    "power": "The power is back on. The perk machines work. The computers are still down.",
    # No random mid-round PA lines: they read as spam on top of the
    # ticket calls, so the only PA voice mid-round is the
    # ticket window's.
}

#: Calm, because back-to-back messages overwhelm: two
#: centre-screen gag lines to one player are this far apart
#: (the framework default is 1.5).
GAG_SAY_GAP = 2.5

#: The seconds a player stands still in the waiting room before the
#: building notices (``GAG_LINES["idle"]``, HUD text).
GAG_IDLE_SECONDS = 20.0


def ticket_kiosk_xy(entry_interior) -> tuple[float, float]:
    """Where the ticket kiosk stands in the entry lobby, ``(x, y)``: 184 in
    from the front-door wall and 60 south of the door line, so a player
    coming in faces it and the path to the waiting room stays clear.  Its
    trigger is 24 in front of it (:func:`ticket_trigger_point`)."""
    return (entry_interior.mins.x + 184.0, -60.0)


def ticket_trigger_point(entry_interior, floor_z: float) -> Point:
    """The ticket trigger's origin: on the floor, 24 in front of the kiosk."""
    x, y = ticket_kiosk_xy(entry_interior)
    return Point(x - 24.0, y, floor_z)

#: The street face's four framed windows, ``(centre y, span, mullion)``.
#: Shared by :func:`_dress_frontage`, which glazes them, and
#: :func:`_furnish_character`, which boards them up.
FRONTAGE_WINDOWS: tuple[tuple[float, float, bool], ...] = (
    (-410.0, 160.0, True), (410.0, 160.0, True),
    (-604.0, 104.0, False), (604.0, 104.0, False),
)

#: The building's notices, key -> (prompt, replies).  Each is a use trigger
#: (:func:`zmforge.script.tricks.use_notices`) hung on a prop: the prompt is
#: what a player standing there reads, and each press prints the next reply.
#: Text only -- nothing is bought, granted or blocked -- and every word is
#: the map's own, shipped in its ``.str`` like :data:`PROMPTS`.  Where each
#: one stands is :func:`_notice_spots`.
NOTICE_LINES: dict[str, tuple[str, tuple[str, ...]]] = {
    "hot_dogs": ("HOT DOGS $3 -- BACK IN 5 MINUTES -- hold ^3[{+activate}]^7 to order", (
        "The sign has said that since the outbreak.",
        "Somebody left ticket 851 under the mustard.",
    )),
    "forms": ("FORMS: hold ^3[{+activate}]^7 to take a form", (
        "Form 27-B: to request Form 27-A.",
        "Form 27-A: out of stock. Please use Form 27-B.",
        "Form 1: how to fill in a form. (Form not included.)",
    )),
    "cooler": ("OUT OF ORDER: hold ^3[{+activate}]^7 to report a fault", (
        "Out of water. Out of cups. Out of order.",
        "Faults are reported at the service window.",
    )),
    "suggestions": ("SUGGESTION BOX: hold ^3[{+activate}]^7 to make a suggestion", (
        "Thank you. Your suggestion has been filed.",
        "Thank you. Your suggestion has been filed under Z.",
        "The suggestion box is full. Please use Form 27-B.",
    )),
    "customer_846": ("CUSTOMER 846 -- hold ^3[{+activate}]^7 to ask for his seat", (
        "He was here before the outbreak.",
        "NOW SERVING: 12.",
        "He has not lost his place in line.",
    )),
    "now_serving": ("SERVICE WINDOW -- hold ^3[{+activate}]^7 to ask", (
        "Take a number. Numbers are called every minute from round 5.",
        "When your number is called you have 3 seconds to be HERE. Wait by this window.",
        "Being served here is one of your registration stamps. Everybody needs one.",
    )),
    "eye_test": ("EYE TEST: hold ^3[{+activate}]^7 to cover an eye", (
        "Now cover your right eye.",
        "Now cover both eyes.",
        "Good. Read the bottom line.",
        "R U N. Correct. Please do so.",
    )),
    # The sign by the camera: the Photo ID step's instruction, before the
    # step opens and during it (dmv_quest.py's Photo ID knifes the camera beside it).
    "photo": ("PHOTO ID: hold ^3[{+activate}]^7 for help", (
        "PHOTO ID opens after the Vision Test.",
        "The camera counts down, then FLASHES. That is your moment. Get close.",
        "Three photos. Do not smile.",
    )),
    "fridge": ("NOTE ON THE FRIDGE: hold ^3[{+activate}]^7 to read", (
        "TO WHOEVER KEEPS EATING MY YOGURT: I KNOW IT IS YOU, GARY.",
        "HAPPY RETIREMENT GARY! (RETIREMENT REQUEST STILL PENDING)",
        "FRIDGE CLEAN-OUT POSTPONED. DO NOT OPEN THE FRIDGE.",
    )),
    "camp": ("Somebody has been living here. Hold ^3[{+activate}]^7 to read the note", (
        "DAY 212. STILL IN LINE.",
        "IF I LEAVE I LOSE MY PLACE.",
        "MY NUMBER IS 2291. NOW SERVING: 12.",
    )),
    "queue_wait": ("ESTIMATED WAIT FROM THIS POINT: 45 MINUTES -- hold ^3[{+activate}]^7 to ask", (
        "The estimate has not changed since the outbreak.",
        "Thank you for your patience.",
    )),
    "queue_closed": ("THIS LINE IS CLOSED -- hold ^3[{+activate}]^7 to ask why", (
        "Please rejoin the line at the back.",
    )),
    "manager": ("SPEAK TO A MANAGER: hold ^3[{+activate}]^7", (
        "The manager is in a meeting.",
        "The manager is at lunch.",
        "The manager has been notified.",
        "The manager will see you now.",
    )),
}

#: How high the waiting-room chair's seat is above its own base, and how far
#: forward of the chair's origin its middle is, in units.  The height is
#: :data:`zmforge.recipes.props.SEAT_TOP`'s measurement off the chair's LOD0
#: mesh (the box's own top, 34.9, is the backrest); the 2.5 is the same
#: mesh's cushion, which runs from 12 in front of the origin to 7 behind it.
#: Customer 846 sits on it, and so does the teddy.
WAITING_SEAT_TOP = SEAT_TOP["p7_chair_waiting_room_01_blue"]
WAITING_SEAT_FORWARD = 2.5

# --------------------------------------------------------------------------
# Surfaces.  Every name below is catalogued (:func:`zmforge.materials.
# is_catalogued`): the twelve measured names of
# :data:`~zmforge.materials.SURFACE_CATALOGUE` plus the stock surfaces of
# :data:`~zmforge.materials.INSTALL_SURFACES`, which were picked off the
# install's own GDTs for this map (see that set for how).  None of them is an
# asset this map brought with it.
#
# Laid out of the twelve alone, a DMV is grey concrete and dark iron and
# reads as plain in game: trowelled concrete, dark concrete and iron come
# to four faces in five.  So the building is dressed the way a
# slightly shabby branch office is:
#
# ==================  =======================================================
# public floors       linoleum tile in the waiting room and the queue, light
#                     16-inch ceramic in the counter hall, travertine tile in
#                     the lobby, white clinic tile in the eye exam
# back of house       fleck carpet in the operator's office (the speckled
#                     concrete laid at 32, which is the only carpet-grained
#                     surface that links), old 2x2 tile in the store
# walls               smooth light plaster and worn white paint (the
#                     institutional off-white), dirty plaster where nobody
#                     repaints, wood panelling on the wall behind the staff,
#                     glazed white tile in the break room
# ceilings            white acoustic panels on a grid, perforated white metal
#                     in the clinic and the offices, a corrugated diffuser in
#                     the break room, and the water-stained rust sheet only in
#                     the store nobody refurbished
# trim                a black rubber skirting, a white moulding at the
#                     ceiling, hollow-metal door frames, 2x4 light fittings
# counters            sugar-pine laminate tops, panelled fronts, metal staff
#                     side, dark glass screens framed in metal
# outside             asphalt, a 2x2 slab footway with a concrete kerb, lawn
#                     in the planted bed, a red brick frontage over a concrete
#                     base band with pilasters, framed windows, a coping and
#                     a sign band, a slab boundary wall, and a canopy with a
#                     rubber roof, a panelled fascia and a metal soffit
# ==================  =======================================================
#
# **Nobody has seen any of this in game**; the colours above are the mean of
# each colour map's swatch, measured, not a look at a rendered frame.
_IRON = Material("t7_metal_worn_iron_dark")
_DESK = Material("t7_wood_veneer_sugarpine_matte", 64.0)
_WALL = Material("t7_concrete_wall_dark_01")

# floors
_LINO = Material("t7_linoleum_floor_tile_square", 64.0)
_CERAMIC = Material("t7_ceramic_tiles_16x16", 64.0)
_CLINIC = Material("t7_ceramic_tile_large_white", 64.0)
_TRAVERTINE = Material("t7_stone_travertine_tiles", 64.0)
_KITCHEN_FLOOR = Material("t7_ceramic_tiles_6x6_dirty_01", 48.0)
_CARPET = Material("t7_concrete_pebbles_cracked", 32.0)
_STORE_FLOOR = Material("t7_concrete_tiles_2x2_dirty_01", 48.0)
# walls
_PLASTER = Material("t7_plaster_smooth_light_01", 128.0)
_PAINT = Material("t7_concrete_worn_painted_white", 128.0)
_GRIMY = Material("t7_plaster_smooth_dirty_01", 128.0)
_PANELLING = Material("t7_wood_panel_01", 64.0)
_TILE_WALL = Material("t7_ceramic_tile_shower_white", 48.0)
_BRICK = Material("t7_brick_worn_heavy_grout_red", 96.0)
_BOOTH = Material("t7_metal_panel_horizontal_painted", 96.0)
# ceilings
_PANEL = Material("t7_plastic_panels_white", 96.0)
_PERFORATED = Material("t7_metal_panel_white_perforated", 64.0)
_DIFFUSER = Material("t7_plastic_ceiling_corrugated_panel", 48.0)
_STAINED = Material("t7_metal_rust_ceiling_01", 96.0)
# trim and fittings
_SKIRTING = Material("t7_plastic_rubber_trim", 32.0)
_MOULDING = Material("t7_plastic_molding_trim_white", 32.0)
_FRAME = Material("t7_metal_frame_trim_01", 32.0)
_GLASS = Material("t7_glass_plain_opaque", 64.0)
_STEEL = Material("t7_metal_panels_4x1", 64.0)
_BLACK = Material("t7_metal_black_trim_01", 32.0)
_LAMINATE = _DESK

# Outside.
_ASPHALT = Material("t7_asphalt_advanced_strips", 256.0)
_WALK = Material("t7_concrete_sidewalk_2x2_01", 96.0)
_KERB = Material("t7_street_concrete_curb_01a", 32.0)
_STRIPE = Material("t7_plastic_molding_trim_white", 16.0)
_LAWN = Material("t7_grass_lawn_medium_small_green", 128.0)
_FACADE = Material("t7_brick_worn_red", 96.0)
_PLINTH = Material("t7_concrete_floor_trim_01", 64.0)
_COPING = Material("t7_concrete_trim_beveled_03", 32.0)
_FENCE = Material("t7_concrete_slabs_interlocked", 128.0)
_ROOFING = Material("t7_rubber_roof_granular", 128.0)
_FASCIA = Material("t7_metal_panel_horizontal_painted", 64.0)


def _faces(default: Material, **sides: Material) -> FaceMaterials:
    """A box with a material per side and ``default`` on the rest -- caulk,
    usually, for the faces that sit against a wall or a floor."""
    return FaceMaterials(
        default=default,
        per_side={Side[key.upper()]: value for key, value in sides.items()},
    )


# --------------------------------------------------------------------------
# Stanchion belts
# --------------------------------------------------------------------------
#: The retractable belt strung between two stanchion posts: black rubber.
#: The catalogue the install compiles clean has no blue or red cloth, and an
#: image texture of the map's own does not link (the eye chart is brushes for
#: the same reason), so the belt is a brush in the eye chart's own ink material.
_BELT = Material("t7_plastic_rubber_trim", 16.0)
#: Belt band above the floor.  The posts (``p7_handrail_post_middle`` and
#: ``_end``) are 36 tall; the belt hangs just under their caps.
BELT_BOTTOM, BELT_TOP = 30.0, 33.0
#: The belt's own thickness, across the line.
BELT_THICKNESS = 1.0
#: Clip behind every belted line: 48 tall, like the queue rails, so the line
#: cannot be hopped (the jump is 39).  A 33-high belt on its own could be.
BELT_CLIP_HEIGHT = 48.0


def _belt_line(bp: Blueprint, posts: Sequence[tuple[float, float]], floor_z: float,
               ident: str, *, clip_thickness: float | None = 8.0) -> int:
    """Belts between each pair of neighbouring *posts* (a line of ``(x, y)``
    post centres, each pair sharing an x or a y), and one clip box the
    length of the line behind them.

    The belts are detail brushes (solid, no BSP splits): :data:`_BELT` on
    the two broad faces, black metal trim on the 1-wide top and bottom (so
    the belts do not tip rubber trim over a quarter of the map's faces, the
    surface-mix test), caulk on the ends inside the posts; noted
    :data:`~zmforge.blueprint.elements.FLOATS_ON_PURPOSE` (the posts carry
    them, and Z43 does not see props).  The clip is ``clip`` (players and AI,
    not bullets), :data:`BELT_CLIP_HEIGHT` tall and *clip_thickness* across
    the line; ``None`` leaves it out, for the queue, whose rails are the
    clip already.  Everything is ``reachable=False``: nothing leads onto a
    belt.  Returns the number of belts.
    """
    top, bottom = floor_z + BELT_TOP, floor_z + BELT_BOTTOM
    half = BELT_THICKNESS / 2.0
    count = 0
    for index, ((ax, ay), (bx, by)) in enumerate(zip(posts, posts[1:])):
        if abs(ay - by) < 1e-6:
            box = Bounds.between((min(ax, bx), ay - half, bottom), (max(ax, bx), ay + half, top))
            faces = _faces(CAULK, north=_BELT, south=_BELT, top=_BLACK, bottom=_BLACK)
        elif abs(ax - bx) < 1e-6:
            box = Bounds.between((ax - half, min(ay, by), bottom), (ax + half, max(ay, by), top))
            faces = _faces(CAULK, east=_BELT, west=_BELT, top=_BLACK, bottom=_BLACK)
        else:
            raise ValueError(f"{ident}: posts {index} and {index + 1} are not in line")
        # Carried by the two posts at its ends, which are props: Z43 sees
        # brushes only, so the belt says it hangs on purpose.
        bp.add_block(box, faces, contents=("detail",), reachable=False,
                     id=f"{ident}_{index}", note=FLOATS_ON_PURPOSE)
        count += 1
    if clip_thickness is not None and len(posts) > 1:
        xs, ys = [p[0] for p in posts], [p[1] for p in posts]
        across = clip_thickness / 2.0
        if max(ys) - min(ys) < 1e-6:
            mins, maxs = (min(xs), ys[0] - across), (max(xs), ys[0] + across)
        else:
            mins, maxs = (xs[0] - across, min(ys)), (xs[0] + across, max(ys))
        bp.add_block(Bounds.between((mins[0], mins[1], floor_z),
                                    (maxs[0], maxs[1], floor_z + BELT_CLIP_HEIGHT)),
                     CLIP, reachable=False, id=f"{ident}_clip", note="stanchion clip")
    return count


#: One skin per room.  No two rooms share all three surfaces: a player who
#: cannot tell the records room from the waiting room by looking at the floor
#: has no map in their head.  **Nobody has seen any of this in game.**
SKINS: Mapping[str, RoomMaterials] = {
    # Outside, and the only room in the map with no roof: asphalt underfoot,
    # the branch's red brick frontage on the east side -- the wall the front
    # door is cut through -- and a precast slab boundary wall the rest of the
    # way round.  The ceiling material is named because ``RoomMaterials``
    # wants three and then dropped by ``roofed=False``.
    "lot_room": room_skin(_FENCE, _ASPHALT, _ASPHALT, east=_FACADE),
    # The vestibule: travertine tile, plaster, the brick street wall you came
    # in through, and the dropped ceiling that runs through the public half.
    "entry_room": room_skin(_PLASTER, _TRAVERTINE, _PANEL, west=_FACADE),
    # Where you wait: linoleum, worn white paint, and the clock wall in the
    # lighter plaster.
    "waiting_room": room_skin(_PAINT, _LINO, _PANEL, east=_PLASTER),
    # The counter hall: light ceramic, plaster, and the wall behind the staff
    # workstations in wood panelling.
    "windows_room": room_skin(_PLASTER, _CERAMIC, _PANEL, east=_PANELLING),
    # Clinical: white tile, plaster, the chart wall in paint, a perforated
    # metal ceiling.
    "eye_exam_room": room_skin(_PLASTER, _CLINIC, _PERFORATED, north=_PAINT),
    # The photo booth: painted metal panels all round, the backdrop.
    "photo_room": room_skin(_BOOTH, _LINO, _PERFORATED),
    # Kitchenette: small dirty tile underfoot, glazed white tile to the walls,
    # a corrugated diffuser overhead.
    "break_room": room_skin(_TILE_WALL, _KITCHEN_FLOOR, _DIFFUSER),
    # The archive nobody refurbished: bare brick, old tile, the shelving wall
    # in painted metal, and the only water-stained ceiling left in the building.
    # Not _IRON: the whole east wall in t7_metal_worn_iron_dark rendered as a
    # black void.
    "records_room": room_skin(_BRICK, _STORE_FLOOR, _STAINED, east=_BOOTH),
    # The long hall: linoleum, dirty plaster nobody repaints, and the wall at
    # the end of the line in the building's dark block.
    "queue_room": room_skin(_GRIMY, _LINO, _PANEL, east=_WALL),
    # Behind the counter: carpet, painted walls, the booth wall the transom is
    # built into in panelling, and the offices' perforated ceiling.
    "office_room": room_skin(_PAINT, _CARPET, _PERFORATED, north=_PANELLING),
}


@dataclass(frozen=True)
class DmvPlan:
    """Every number this recipe uses, so a caller can change one without
    editing the function."""

    lot: Bounds = Bounds.between((-2800, -700, 0), (-1600, 700, 320))
    entry: Bounds = Bounds.between((-1600, -300, 0), (-1200, 300, 256))
    waiting: Bounds = Bounds.between((-1200, -500, 0), (-700, 500, 288))
    windows: Bounds = Bounds.between((-700, -400, 0), (-100, 400, 288))
    #: North of the counter hall and slid west, so its door lands in the
    #: **public** strip: a vision screening room is somewhere a customer is
    #: sent, not somewhere behind the counter.
    eye_exam: Bounds = Bounds.between((-660, 400, 0), (-400, 700, 224))
    #: Slid east along the waiting room's south wall to the end nearest the
    #: counter.  PA's photo-licence-centre requirements put the picture chair
    #: in the customer service area itself ("a picture chair situated in front
    #: of a PennDOT-provided backdrop", co-location requirements 4.1.4); this
    #: map gives it a booth off the lobby instead, which is the compromise a
    #: teleporter gag needs and is written down here rather than claimed as
    #: what a real branch does.
    photo: Bounds = Bounds.between((-1000, -800, 0), (-700, -500, 224))
    #: Behind the counter, off the staff side of the counter hall, because a
    #: staff break room is back of house.  It used to hang off the waiting
    #: room, which put the building's power switch in the public half.
    break_room: Bounds = Bounds.between((-400, 400, 0), (-100, 700, 224))
    records: Bounds = Bounds.between((-100, -400, 0), (400, 400, 288))
    queue: Bounds = Bounds.between((400, -348, 0), (1300, 468, 320))
    office: Bounds = Bounds.between((880, 468, 0), (1480, 1168, 384))

    wall: float = 16.0
    doorway_width: float = 80.0
    doorway_height: float = 96.0
    yard_depth: float = 176.0

    #: The one opening in the building that is not a doorway.  A real branch
    #: does not put a door between the chairs and the counter -- they are one
    #: room -- and this map cannot merge them, because a zone needs a door to
    #: be bought into.  So the lobby-to-counter opening is widened until it
    #: reads as the threshold of one hall rather than as a door, and the
    #: seating is aimed through it at the counter run.
    lobby_opening: float = 144.0

    # ----------------------------------------------------------------
    # Outside: the car park, the footway and the covered walk.
    #
    # One unit is one inch, so every number below is the imperial one it
    # looks like.  The bay and aisle sizes are the **assumed** ones -- a
    # 9 x 18 ft bay and a 24 ft two-way aisle are what a suburban lot is
    # striped at, and no source was found that fixes them for a motor
    # vehicle branch specifically.  The two accessible bays beside the walk
    # are 8 ft with an 8 ft access aisle, which is the van-accessible
    # figure, and is likewise assumed here rather than quoted.
    # ----------------------------------------------------------------
    stall_width: float = 108.0
    stall_depth: float = 216.0
    drive_aisle: float = 288.0
    accessible_stall_width: float = 96.0
    access_aisle_width: float = 96.0
    stripe_width: float = 4.0
    stripe_height: float = 1.0
    #: The footway across the building frontage, and how far it stands proud
    #: of the asphalt.  Six inches is a kerb; it is under
    #: :data:`zmforge.verify.reachability.STEP_UP`, so it is walked rather
    #: than jumped and needs no ramp to be reachable -- the ramp at the
    #: accessible route is there because a real one is, not because the
    #: engine needs it.
    walk_depth: float = 192.0
    kerb_height: float = 6.0
    #: The covered entry walk: how far the canopy reaches out from the
    #: frontage, how wide it is and how high its underside sits.
    canopy_reach: float = 192.0
    canopy_width: float = 240.0
    canopy_height: float = 144.0
    #: The planted strip along the far boundary, which is also where the
    #: zombies come up out of the ground.
    landscape_depth: float = 256.0

    #: The queue.  ``lane_width`` clears Treyarch's own 96-unit hallway
    #: minimum (``Scale_Standards.pdf``, the number ``N5`` warns under),
    #: ``rail_thickness`` is the rope line's own footprint and ``rail_height``
    #: is the point of the gag: 48 is above
    #: :data:`zmforge.verify.reachability.JUMP_UP` (39), so the line cannot be
    #: hopped.  ``turn_width`` is the gap left at the end of every second
    #: rail for the switchback.
    lane_width: float = 120.0
    last_lane_width: float = 240.0
    rail_thickness: float = 16.0
    rail_height: float = 48.0
    turn_width: float = 144.0

    # ----------------------------------------------------------------
    # The counter run, which is the thing this building is.
    #
    # It does not stand against a wall.  It stands *across* the counter
    # hall, north-south, with the public on its west face and the staff
    # behind it, because that is the one arrangement a motor vehicle branch
    # is actually required to have: PennDOT's photo licence centre
    # co-location requirements, 4.1.3 -- "Employee workstations must be
    # behind the PLC customer service counter area and accessible from the
    # public service area only through a gate or a door" -- and 4.1.4, "a
    # counter, located directly in front of the employee workstations".
    # ``staff_gate`` is that gate.
    # ----------------------------------------------------------------
    #: How deep the public floor is between the lobby wall and the counter's
    #: public face.
    public_depth: float = 216.0
    #: The counter is two tiers, which is what a transaction counter is.  The
    #: patron ledge is the top; the staff work surface sits behind and below
    #: it.  28.5 is measured: UC Berkeley's customer service counter design
    #: guidelines specify "Fixed work surface height at 28.5" with an
    #: unobstructed 27.5" floor to under counter height".
    patron_ledge_depth: float = 16.0
    staff_surface_depth: float = 24.0
    staff_surface_height: float = 28.5
    #: **42 is an engine number, not a sourced one.**  ADA 904.4.1 caps a
    #: sales and service counter at "36 inches (915 mm) high maximum above
    #: the finish floor", and 36 is under
    #: :data:`zmforge.verify.reachability.JUMP_UP` (39) -- a counter built to
    #: code in this engine is a step, and the public side and the staff side
    #: stop being two places.  So the run is 42 and the compromise is written
    #: down here.
    counter_height: float = 42.0
    #: The lowered section, and how long it is.  ADA 904.4.1 again: "A
    #: portion of the counter surface that is 36 inches (915 mm) long
    #: minimum" at 36 high maximum.  The length is the code's; the height is
    #: 40 for the same reason 42 is 42, one unit clear of the jump.
    ada_section_length: float = 36.0
    ada_section_height: float = 40.0
    #: The gap the counter stops short of the north wall by: the staff gate.
    #: ADA 403.5.1 puts an accessible route at 36 in clear minimum and
    #: Treyarch's own scale standards put a hallway at 96, so the gate is
    #: built to the larger of the two.
    staff_gate: float = 96.0
    #: The counter run is laid out on a grid of ``counter_bays`` equal bays.
    #: Only one bay is a service window (``window_bay``, one-based); the rest
    #: of the run is a plain partition wall over the counter, and the grid
    #: only places the staff desks, the dressing and the wall buy along it.
    #: One window and no numbers: eight numbered windows with one open
    #: read as a single window, with the numbers as noise.
    #: The window bay is on the axis of the lobby opening, so the one lit
    #: window and the NOW SERVING board over it are what the two rows of
    #: chairs are looking straight down the room at.
    counter_bays: int = 8
    window_bay: int = 5
    #: The bay whose stretch of partition carries the wall buy (CARRY PERMIT
    #: (EXPIRED)); it must be solid wall, since ``W3`` probes eight units
    #: behind a buy for the wall it is mounted on.
    wallbuy_bay: int = 4
    #: The speak-through slot between the counter top and the screen over it,
    #: and the frame at each side of the service window.
    service_slot: float = 36.0
    mullion_width: float = 12.0

    #: The waiting room's chairs.  Ten of them, in two rows facing the
    #: counter: PennDOT's requirements again, 4.1.5, "ten waiting chairs per
    #: camera system", and this branch has one camera.
    chair_rows: int = 2
    chair_cols: int = 5
    #: Between one row and the row behind it, and between one seat and the
    #: next along a row.
    row_pitch: float = 64.0
    seat_pitch: float = 44.0

    #: What a ticket costs and what it pays back each round.  The machine is
    #: a perk of this repository's own (see :func:`take_a_number_perk`); the
    #: price is the cheapest thing in the map because a number is not a
    #: service.
    ticket_cost: int = 750
    ticket_points: int = 50

    #: The registration desk.  What the fee costs and how much faster it
    #: makes you (see :func:`vehicle_registration_perk`).  The price is the
    #: dearest perk in the building because it is the only one that is a
    #: *fee*, and the per cent is a design choice.
    registration_cost: int = 3000
    registration_speed: float = 20.0  # 1.2x; 1.75x was too fast

    #: The stapler.  The stock knife price: 9,500 under a "REQUISITION
    #: PENDING" line reads as a buy that looks locked, so the requisition
    #: is approved.
    stapler_price: int = 3000

    #: The arena.  The operator's counter stands ``booth_depth`` off the far
    #: wall with a ``service_slot``-tall gap over it, and stops
    #: ``booth_way_in`` short of the east wall: that gap is how a player and a
    #: walker get behind it, and a counter run the whole width would seal the
    #: booth off as floor nobody can reach.  ``ambush_count`` sprinters are
    #: behind it when the door is bought, and the spawns run hot for
    #: ``spike_seconds`` afterwards.
    booth_depth: float = 96.0
    booth_way_in: float = 164.0
    ambush_count: int = 12
    spike_seconds: float = 20.0

    #: A caller's own price list, keyed the same way as :data:`PRICES`.
    door_prices: Mapping[str, int] | None = None

    @property
    def counter_depth(self) -> float:
        """The whole counter front to back: patron ledge plus staff work
        surface."""
        return self.patron_ledge_depth + self.staff_surface_depth

    def price(self, door: str) -> int:
        """What *door* costs: the plan's own list if it has one, else
        :data:`PRICES`."""
        return int((self.door_prices or PRICES)[door])


#: The configuration the map ships with.
FIXTURE = DmvPlan()


def _centre_x(box: Bounds) -> float:
    """The middle of *box* along x, which is where an opening is cut from."""
    return (box.mins.x + box.maxs.x) / 2.0


def counter_run(plan: DmvPlan = FIXTURE) -> tuple[float, float, float, float]:
    """The counter run, as ``(public_face_x, back_x, y_south, y_north)``.

    It crosses the counter hall north to south, ``public_depth`` in from the
    lobby wall, and stops ``staff_gate`` short of the north wall.  Everything
    west of ``public_face_x`` is where a customer stands; everything east of
    ``back_x`` is staff floor, and the only way from one to the other is the
    gate at the north end -- which is the arrangement PennDOT requires of a
    photo licence centre (co-location requirements 4.1.3) and the thing that
    makes walking into the back of this map feel like going behind a counter.
    """
    inner = plan.windows.grown(-plan.wall)
    face = inner.mins.x + plan.public_depth
    return (face, face + plan.counter_depth, inner.mins.y,
            inner.maxs.y - plan.staff_gate)


def bay_centres(plan: DmvPlan = FIXTURE) -> tuple[float, ...]:
    """The y of each bay of the counter run, south to north, bay 1 first.

    The run is divided evenly into ``counter_bays``; one of the bays is the
    service window (:func:`window_y`), the others are partition wall.  The
    pitch is checked against the 48 in of clear floor ADA wants at a
    service counter position by ``tests/test_dmv.py``.
    """
    _face, _back, y0, y1 = counter_run(plan)
    pitch = (y1 - y0) / plan.counter_bays
    return tuple(y0 + (index + 0.5) * pitch for index in range(plan.counter_bays))


def bay_pitch(plan: DmvPlan = FIXTURE) -> float:
    """Centre to centre between one bay of the counter run and the next."""
    _face, _back, y0, y1 = counter_run(plan)
    return (y1 - y0) / plan.counter_bays


def window_y(plan: DmvPlan = FIXTURE) -> float:
    """The y of the hall's one service window (the ticket window)."""
    return bay_centres(plan)[plan.window_bay - 1]


def window_opening(plan: DmvPlan = FIXTURE) -> tuple[float, float]:
    """``(y0, y1)`` of the service window's clear opening: one bay less a
    mullion at each side, so the frame stands inside the bay."""
    y, half = window_y(plan), bay_pitch(plan) / 2.0 - plan.mullion_width
    return (y - half, y + half)


def parking_bays(plan: DmvPlan = FIXTURE) -> tuple[tuple[str, float, float, float, float], ...]:
    """Every marked bay in the car park, as ``(kind, x0, x1, y0, y1)``.

    ``kind`` is ``"standard"``, ``"accessible"`` or ``"aisle"`` -- the last
    being the striped access aisle beside an accessible bay, which is not
    somewhere a car goes.  Two rows: one head-in against the footway either
    side of the covered walk, and one against the planted boundary, with the
    drive aisle between them.

    The bays are laid out from the walk outwards rather than from a corner,
    because the accessible ones have to be the pair nearest the door.
    """
    inner = plan.lot.grown(-plan.wall)
    walk_x0 = inner.maxs.x - plan.walk_depth
    row_near = (walk_x0 - plan.stall_depth, walk_x0)
    row_far = (inner.mins.x + plan.landscape_depth,
               inner.mins.x + plan.landscape_depth + plan.stall_depth)

    out: list[tuple[str, float, float, float, float]] = []
    half_walk = plan.canopy_width / 2.0
    # The near row, built outwards from the walk: access aisle, accessible
    # bay, then standard bays until the row runs out of wall.
    for sign in (1.0, -1.0):
        edge = sign * half_walk
        aisle = (edge, edge + sign * plan.access_aisle_width)
        bay = (aisle[1], aisle[1] + sign * plan.accessible_stall_width)
        out.append(("aisle", row_near[0], row_near[1], min(aisle), max(aisle)))
        out.append(("accessible", row_near[0], row_near[1], min(bay), max(bay)))
        cursor = bay[1]
        while abs(cursor + sign * plan.stall_width) <= abs(inner.maxs.y):
            nxt = cursor + sign * plan.stall_width
            out.append(("standard", row_near[0], row_near[1],
                        min(cursor, nxt), max(cursor, nxt)))
            cursor = nxt
    # The far row, built outwards from the centre line so it is symmetric.
    count = int((inner.maxs.y - inner.mins.y) // plan.stall_width)
    span = count * plan.stall_width
    start = -span / 2.0
    for index in range(count):
        y0 = start + index * plan.stall_width
        out.append(("standard", row_far[0], row_far[1], y0, y0 + plan.stall_width))
    return tuple(out)


#: The cars still parked in the lot, as ``(bay index into parking_bays(),
#: model, yaw)``.  Four civilian models, each with its LOD0 binary in the
#: tools tree's ``model_export`` (checked against the GDT
#: ``filename`` of each: ``veh_t7_civ_car_compact.gdt``,
#: ``veh_t7_civ_city_car.gdt`` for the destructible body and the burnt-out
#: static one, ``veh_t7_civ_gt.gdt``); ``veh_t7_civ_city_car_vista`` is left
#: out because it is the distant-vista cut of the city car, not one to stand
#: next to.  Head-in, either way round, a few degrees off true.  Two are
#: abandoned: a compact left slewed across its bay at the south end of the
#: near row, and a burnt-out wreck slewed in the far row -- by 12 degrees,
#: not more: at 17 its corner crossed a bay line, the one-unit paint strip,
#: and Z44 read it as a car standing on the paint by one corner.
#: Left empty on purpose: both access aisles, both accessible bays (the
#: south one is the towed car's), the coned staff bay, and the three far
#: bays round the hot-dog cart; bays 12 and 15 are the gaps the far row's
#: risers reach the aisle through.
LOT_CARS: tuple[tuple[int, str, float], ...] = (
    (2, "veh_t7_civ_car_compact", 182.0),
    (3, "veh_t7_civ_city_car_destructible", 357.0),
    (4, "veh_t7_civ_car_compact", 1.0),
    (7, "veh_t7_civ_city_car_destructible", 178.0),
    (9, "veh_t7_civ_car_compact", 11.0),
    (10, "veh_t7_civ_city_car_destructible", 2.0),
    (11, "veh_t7_civ_gt", 179.0),
    (13, "veh_t7_civ_car_compact", 3.0),
    (14, "veh_t7_city_car_static_dead", 12.0),
    (16, "veh_t7_civ_city_car_destructible", 181.0),
    (17, "veh_t7_civ_gt", 358.0),
    (18, "veh_t7_civ_car_compact", 177.0),
)


def parked_cars(plan: DmvPlan = FIXTURE, floor_z: float = 16.0) -> tuple[tuple, ...]:
    """:data:`LOT_CARS` as solid ``place_props`` items, each car's measured
    box centred on its bay (the models are not authored about their middles:
    the GT's box runs -93 to +111 along its length)."""
    bays = parking_bays(plan)
    out = []
    for index, model, yaw in LOT_CARS:
        _kind, x0, x1, y0, y1 = bays[index]
        (ax, ay, _az), (bx, by, _bz) = collision_box(model)
        cx, cy = (ax + bx) / 2.0, (ay + by) / 2.0
        turn = math.radians(yaw)
        dx = cx * math.cos(turn) - cy * math.sin(turn)
        dy = cx * math.sin(turn) + cy * math.cos(turn)
        at = Point((x0 + x1) / 2.0 - dx, (y0 + y1) / 2.0 - dy, _rest_on(model, floor_z))
        out.append((model, at, yaw, 1.0, True))
    return tuple(out)


def _lanes(plan: DmvPlan) -> tuple[tuple[float, float], ...]:
    """The five lanes of the queue, south to north, as ``(y0, y1)`` pairs.

    Built outwards from the middle lane rather than up from the south wall,
    because the door in from the records room is cut in the middle of the
    queue hall's west wall and the player has to arrive *in* a lane: the
    third one is centred on the hall's own entry height and the ladder is
    measured off it.
    """
    mid = _queue_entry_y(plan)
    half = plan.lane_width / 2.0
    lane3 = (mid - half, mid + half)
    rail = plan.rail_thickness
    lane2 = (lane3[0] - rail - plan.lane_width, lane3[0] - rail)
    lane1 = (lane2[0] - rail - plan.lane_width, lane2[0] - rail)
    lane4 = (lane3[1] + rail, lane3[1] + rail + plan.lane_width)
    lane5 = (lane4[1] + rail, lane4[1] + rail + plan.last_lane_width)
    return (lane1, lane2, lane3, lane4, lane5)


def _queue_entry_y(plan: DmvPlan) -> float:
    """The height the line starts at: the middle of the middle lane.

    The queue hall's interior is not symmetric about it -- the last lane is
    wider than the rest, because the pack-a-punch needs
    :data:`zmforge.blueprint.reach.APRON_SIDE` of room either side of itself
    -- so this is the number every other lane is measured from, and the
    number the west doorway is offset to.
    """
    south = plan.queue.mins.y + plan.wall
    return south + plan.lane_width * 2.0 + plan.rail_thickness * 2.0 + plan.lane_width / 2.0


def _rails(plan: DmvPlan) -> tuple[tuple[str, float, float, float, float], ...]:
    """The four rails, as ``(id, x0, x1, y0, y1)``.

    A rail that runs from the west wall to short of the east one leaves the
    turn at the east end; the next one up runs from short of the west wall to
    the east one and leaves it at the west.  That alternation is the
    switchback, and it is also what makes the southern pair a dead end: the
    branch off the entry lane runs two legs and stops in the corner beside
    the door.
    """
    lanes = _lanes(plan)
    west = plan.queue.mins.x + plan.wall
    east = plan.queue.maxs.x - plan.wall
    turn = plan.turn_width
    out: list[tuple[str, float, float, float, float]] = []
    for index in range(4):
        y0 = lanes[index][1]
        y1 = lanes[index + 1][0]
        # Rails 0 and 2 are fixed to the west wall, 1 and 3 to the east one.
        if index % 2 == 0:
            out.append((f"queue_rail_{index}", west, east - turn, y0, y1))
        else:
            out.append((f"queue_rail_{index}", west + turn, east, y0, y1))
    return tuple(out)


def queue_route(plan: DmvPlan = FIXTURE) -> tuple[Point, ...]:
    """The walk from the queue's door to the pack-a-punch, corner by corner.

    Three legs and two turns, in the order a player meets them: east along
    the entry lane, north at the east end, west along the fourth lane, north
    at the west end, east along the last lane to the machine.  The z is the
    floor, so a test can hand these to
    :func:`zmforge.verify.reachability.flood_from_spawn`'s graph and ask
    whether each point is standing room.
    """
    lanes = _lanes(plan)
    floor = plan.queue.mins.z + plan.wall
    west = plan.queue.mins.x + plan.wall
    east = plan.queue.maxs.x - plan.wall
    turn_east = east - plan.turn_width / 2.0
    turn_west = west + plan.turn_width / 2.0

    def mid(lane: tuple[float, float]) -> float:
        return (lane[0] + lane[1]) / 2.0

    return (
        Point(west + 32.0, mid(lanes[2]), floor),
        Point(turn_east, mid(lanes[2]), floor),
        Point(turn_east, mid(lanes[3]), floor),
        Point(turn_west, mid(lanes[3]), floor),
        Point(turn_west, mid(lanes[4]), floor),
        Point(east - 160.0, mid(lanes[4]), floor),
    )


def queue_dead_end(plan: DmvPlan = FIXTURE) -> tuple[Point, ...]:
    """The other branch: two legs south and west, ending in the entry corner.

    Same shape as :func:`queue_route` and deliberately not shorter.  A player
    who turns the wrong way at the door walks this, finds the wall, and walks
    back.
    """
    lanes = _lanes(plan)
    floor = plan.queue.mins.z + plan.wall
    west = plan.queue.mins.x + plan.wall
    east = plan.queue.maxs.x - plan.wall
    turn_east = east - plan.turn_width / 2.0
    turn_west = west + plan.turn_width / 2.0

    def mid(lane: tuple[float, float]) -> float:
        return (lane[0] + lane[1]) / 2.0

    return (
        Point(turn_west, mid(lanes[2]), floor),
        Point(turn_west, mid(lanes[1]), floor),
        Point(turn_east, mid(lanes[1]), floor),
        Point(turn_east, mid(lanes[0]), floor),
        Point(west + 32.0, mid(lanes[0]), floor),
    )


def take_a_number_perk(plan: DmvPlan = None) -> CustomPerk:
    """TAKE A NUMBER: the ticket machine in the entry hall.

    **A perk of this repository's own.**  The name, the price, the prompt and
    the effect were written here; what it borrows is stock and free to name
    -- a vending model, a bottle, a machine light, and a jingle alias a
    usermap does not ship and therefore never plays.  No other author's map,
    script, art or perk name is involved.

    The effect is :func:`zmforge.script.perks.points_each_round`, the same
    dull, watchable one :data:`zmforge.script.perks.COIN_RETURN` uses: you pay for a
    ticket once and the building pays you a little every round you are still
    waiting.  It is the only effect this package has, which is stated here
    rather than dressed up: a perk that made the queue shorter would need
    code nobody has written.

    **Unplayed.**  See :mod:`zmforge.script.perks` for what is measured and
    what is not.
    """
    plan = plan if plan is not None else FIXTURE
    return CustomPerk(
        slug="take_a_number",
        name="TAKE A NUMBER",
        cost=plan.ticket_cost,
        effect=points_each_round(plan.ticket_points),
        # Takes the default tombstone slot; the map ships its own picture
        # under that slot's image name, since the install has none.
        icon_art="ticket",
    )


def vehicle_registration_perk(plan: DmvPlan = None) -> CustomPerk:
    """VEHICLE REGISTRATION FEE: pay at the window, leave at speed.

    **A perk of this repository's own**, like the ticket machine: the name,
    the price, the prompt and the effect were written here, and what it
    borrows -- a vending model, a bottle, a machine light and a jingle alias a
    usermap does not ship -- is stock and free to name.

    The effect is :func:`zmforge.script.perks.move_speed`, written for this
    perk and reusable by any recipe, and it is a real one:
    ``SetMoveSpeedScale`` is what ``zm_usermap.gsc:336`` sets to 1 on every
    player it spawns, so ``1.75`` is 75% faster than the walk the map already
    gives you.  What is *not* borrowed is Stamin-Up: that perk's own module
    contains no movement call at all, so its boost is engine-side off
    ``specialty_staminup`` and out of reach of a specialty of ours.  Both
    machines stand in this building and **what a player holding both moves
    like is not measured** -- see the effect's own docstring.

    **The machine is a car**.  It first shipped as
    ``p7_zm_vending_doubletap2`` -- that is why it showed Double Tap's
    machine -- because the level-common zone carries no vehicle.  Now
    :data:`REGISTRATION_CAR` is the lot's own compact, which has a measured
    box, is declared in the map's zone (``declare_asset``) for the
    framework's run-time ``SetModel``, and sits along the west wall with
    its side as the front.  The framework's use trigger (radius 40 at the
    origin) is moved out to that side (``trigger_shift``), and two clip
    brushes cover the bonnet and boot beyond the framework's own
    vending-sized clip.

    **Unplayed.**  See :mod:`zmforge.script.perks` for what is measured and
    what is not.
    """
    plan = plan if plan is not None else FIXTURE
    return CustomPerk(
        slug="vehicle_registration",
        name="VEHICLE REGISTRATION FEE",
        cost=plan.registration_cost,
        effect=move_speed(plan.registration_speed),
        # The ticket machine has the other free HUD slot, and two perks on one
        # slot is a Z50 error: the shipped widget draws one image per key.
        icon=DIVE_TO_NUKE_ICON,
        icon_art="licence_plate",
        # Double Tap's bottle (nothing else on this map drinks it) and a car
        # for a machine (it showed Double Tap's machine
        # because this said ``p7_zm_vending_doubletap2``).  The car is the
        # lot's own compact, declared in the zone; the trigger is moved out
        # to the car's side, and the car's clip is the recipe's.
        bottle="zombie_perk_bottle_doubletap",
        machine_model=REGISTRATION_CAR,
        trigger_shift=REGISTRATION_TRIGGER_SHIFT,
    )


#: The registration perk's machine: the lot's compact car (measured box in
#: :data:`zmforge.recipes.props.MODEL_BOX`, 133 x 69 x 62).
REGISTRATION_CAR = "veh_t7_civ_car_compact"
#: The use trigger's shift out of the car's side, units: the side is 34.5
#: from the origin, so a player against it is ~11 from the trigger centre.
REGISTRATION_TRIGGER_SHIFT = 40.0


# --------------------------------------------------------------------------
# Dressing: the trim, the fittings and the frontage
# --------------------------------------------------------------------------
#: How the interior trim is sized, in inches.  A rubber base is four inches
#: tall; a ceiling moulding, a hollow-metal door frame and a 2x4 troffer are
#: the sizes they are sold at, rounded to what an axis-aligned brush can be.
SKIRTING_HEIGHT = 4.0
SKIRTING_DEPTH = 2.0
CORNICE_HEIGHT = 6.0
CORNICE_DEPTH = 3.0
FRAME_WIDTH = 4.0
FRAME_DEPTH = 2.0
TROFFER = (48.0, 24.0, 2.0)
#: Centre-to-centre spacing of the light fittings, and how far the grid keeps
#: off the walls.  Assumed: an office lays a 2x4 troffer in every second or
#: third bay of a 2x2 ft grid, and 144 x 120 is that.
TROFFER_PITCH = (192.0, 168.0)
TROFFER_MARGIN = 56.0


def _overlaps(a: Bounds, b: Bounds, pad: float = 0.0) -> bool:
    return (a.mins.x < b.maxs.x + pad and b.mins.x - pad < a.maxs.x
            and a.mins.y < b.maxs.y + pad and b.mins.y - pad < a.maxs.y
            and a.mins.z < b.maxs.z + pad and b.mins.z - pad < a.maxs.z)


def _runs(lo: float, hi: float, holes: list[tuple[float, float]]
          ) -> list[tuple[float, float]]:
    """``[lo, hi]`` with every ``holes`` interval cut out of it."""
    out = []
    cursor = lo
    for h0, h1 in sorted(holes):
        if h1 <= cursor or h0 >= hi:
            continue
        if h0 > cursor:
            out.append((cursor, h0))
        cursor = max(cursor, h1)
    if cursor < hi:
        out.append((cursor, hi))
    return [(a, b) for a, b in out if b - a >= 4.0]


def _wall_strip(room, side: Side, along: tuple[float, float],
                z: tuple[float, float], depth: float) -> Bounds:
    """A box ``depth`` deep laid flat against *room*'s *side* wall, running
    ``along`` that wall and spanning ``z``."""
    box = room.interior
    a0, a1 = along
    if side is Side.NORTH:
        return Bounds.between((a0, box.maxs.y - depth, z[0]), (a1, box.maxs.y, z[1]))
    if side is Side.SOUTH:
        return Bounds.between((a0, box.mins.y, z[0]), (a1, box.mins.y + depth, z[1]))
    if side is Side.EAST:
        return Bounds.between((box.maxs.x - depth, a0, z[0]), (box.maxs.x, a1, z[1]))
    return Bounds.between((box.mins.x, a0, z[0]), (box.mins.x + depth, a1, z[1]))


def _along(room, side: Side) -> tuple[float, float]:
    box = room.interior
    if side in (Side.NORTH, Side.SOUTH):
        return box.mins.x, box.maxs.x
    return box.mins.y, box.maxs.y


def _hole_along(side: Side, hole: Bounds) -> tuple[float, float]:
    if side in (Side.NORTH, Side.SOUTH):
        return hole.mins.x, hole.maxs.x
    return hole.mins.y, hole.maxs.y


def _trim(material: Material, side: Side) -> FaceMaterials:
    """Art on the face looking into the room, on the top and on the bottom;
    caulk on the back against the wall and on the two cut ends."""
    return _faces(CAULK, **{side.opposite.name.lower(): material,
                            "top": material, "bottom": material})


def _dress_room(bp: Blueprint, room, key: str, *, lights: bool = True,
                rim: Material = None) -> int:
    """Skirting, a ceiling moulding, a frame round every doorway and a grid
    of light fittings, for one room.  Returns how many pieces it laid.

    Every piece is flush against a wall, the floor or the ceiling (``Z43``),
    and the fittings skip anything already standing where they would hang --
    the counter screens and the transom reach the ceiling.
    """
    laid = 0
    floor = room.floor_z
    ceiling = room.interior.maxs.z
    doors = [
        (aperture.side, box)
        for aperture, box in zip(room.apertures, room.aperture_boxes)
        if aperture.sill == 0.0
    ]
    # What stands on this floor, as boxes: the base stops short of anything
    # pushed back against the wall, rather than running under it and leaving
    # it standing on a two-inch ledge (``Z44``).
    footprints = floor_footprints(bp, room, base_below=SKIRTING_HEIGHT)
    for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST):
        holes = [_hole_along(side, box) for s, box in doors if s is side]
        framed = [(h0 - FRAME_WIDTH, h1 + FRAME_WIDTH) for h0, h1 in holes]
        lo, hi = _along(room, side)
        strip = _wall_strip(room, side, (lo, hi),
                            (floor, floor + SKIRTING_HEIGHT), SKIRTING_DEPTH)
        behind = [
            _hole_along(side, fp) for fp in footprints if _overlaps(fp, strip, 1.0)
        ]
        behind = [(a0 - 2.0, a1 + 2.0) for a0, a1 in behind]
        # The rubber base, broken at every doorway and its frame.
        for index, (a0, a1) in enumerate(_runs(lo, hi, framed + behind)):
            bp.add_block(
                _wall_strip(room, side, (a0, a1),
                            (floor, floor + SKIRTING_HEIGHT), SKIRTING_DEPTH),
                _trim(_SKIRTING, side),
                reachable=False,
                id=f"{key}_skirting_{side.name.lower()}_{index}",
            )
            laid += 1
        # The moulding where the wall meets the ceiling.  North and south run
        # the full width; east and west stop short of them.
        if room.roofed:
            if side in (Side.EAST, Side.WEST):
                lo, hi = lo + CORNICE_DEPTH, hi - CORNICE_DEPTH
            bp.add_block(
                _wall_strip(room, side, (lo, hi),
                            (ceiling - CORNICE_HEIGHT, ceiling), CORNICE_DEPTH),
                _trim(_MOULDING, side),
                reachable=False,
                id=f"{key}_cornice_{side.name.lower()}",
            )
            laid += 1
        # A hollow-metal frame round each doorway: two jambs and a head.
        for index, (s, box) in enumerate(doors):
            if s is not side:
                continue
            h0, h1 = _hole_along(side, box)
            top = box.maxs.z
            for jamb, (a0, a1) in enumerate(((h0 - FRAME_WIDTH, h0),
                                             (h1, h1 + FRAME_WIDTH))):
                bp.add_block(
                    _wall_strip(room, side, (a0, a1), (floor, top), FRAME_DEPTH),
                    _faces(CAULK, **{side.opposite.name.lower(): _FRAME,
                                     "top": _FRAME,
                                     ("west" if side in (Side.NORTH, Side.SOUTH)
                                      else "south") if jamb == 1 else
                                     ("east" if side in (Side.NORTH, Side.SOUTH)
                                      else "north"): _FRAME}),
                    reachable=False,
                    id=f"{key}_door_frame_{index}_{jamb}",
                )
                laid += 1
            bp.add_block(
                _wall_strip(room, side, (h0 - FRAME_WIDTH, h1 + FRAME_WIDTH),
                            (top, top + FRAME_WIDTH), FRAME_DEPTH),
                _trim(_FRAME, side),
                reachable=False,
                id=f"{key}_door_head_{index}",
            )
            laid += 1
    if not (lights and room.roofed):
        return laid
    # The light fittings: a 2x4 troffer on a grid, diffuser down, frame
    # round the edge.  Anything already reaching the ceiling (a counter
    # screen, the operator's transom) keeps its fittings off it.
    standing = [
        element.authored.box
        for element in bp.elements(Massing)
        if element.authored is not None and element.authored.box is not None
    ]
    box = room.interior
    length, width, depth = TROFFER
    x0, x1 = box.mins.x + TROFFER_MARGIN, box.maxs.x - TROFFER_MARGIN
    y0, y1 = box.mins.y + TROFFER_MARGIN, box.maxs.y - TROFFER_MARGIN
    cols = max(1, int((x1 - x0) // TROFFER_PITCH[0]) + 1)
    rows = max(1, int((y1 - y0) // TROFFER_PITCH[1]) + 1)
    fitting = 0
    for col in range(cols):
        cx = (x0 + x1) / 2.0 + (col - (cols - 1) / 2.0) * TROFFER_PITCH[0]
        for row in range(rows):
            cy = (y0 + y1) / 2.0 + (row - (rows - 1) / 2.0) * TROFFER_PITCH[1]
            troffer = Bounds.between(
                (cx - length / 2.0, cy - width / 2.0, ceiling - depth),
                (cx + length / 2.0, cy + width / 2.0, ceiling),
            )
            if any(_overlaps(troffer, other, 8.0) for other in standing):
                continue
            bp.add_block(
                troffer,
                _faces(rim or _MOULDING, bottom=_DIFFUSER, top=CAULK),
                reachable=False,
                id=f"{key}_light_{fitting}",
            )
            fitting += 1
            laid += 1
    return laid


def _dress_frontage(bp: Blueprint, lot, plan: "DmvPlan", walk_top: float,
                    keep_clear: list[tuple[float, float]]) -> int:
    """The branch's street face, on the inside of the car park's east wall.

    A concrete base band, brick pilasters, two pairs of framed windows, a sign
    band over the canopy, a cornice and a coping.  ``keep_clear`` is the
    stretches of the wall the base band must leave bare -- the wall buy's
    chalk and the front door's frame.
    """
    laid = 0
    box = lot.interior
    fx = box.maxs.x
    top = box.maxs.z
    y_lo, y_hi = box.mins.y, box.maxs.y
    pilasters = [(y - 12.0, y + 12.0) for y in (-520.0, -300.0, 300.0, 520.0)]
    # Pilasters, full height, six deep.
    for index, (a0, a1) in enumerate(pilasters):
        bp.add_block(
            Bounds.between((fx - 6.0, a0, walk_top), (fx, a1, top - 24.0)),
            _faces(_FACADE, east=CAULK, bottom=CAULK, top=_COPING),
            reachable=False,
            id=f"lot_pilaster_{index}",
        )
        laid += 1
    # The base band: two feet of concrete along the bottom of the brick.
    for index, (a0, a1) in enumerate(_runs(y_lo, y_hi, keep_clear + pilasters)):
        bp.add_block(
            Bounds.between((fx - 3.0, a0, walk_top), (fx, a1, walk_top + 24.0)),
            _faces(CAULK, west=_PLINTH, top=_COPING),
            reachable=False,
            id=f"lot_base_band_{index}",
        )
        laid += 1
    # Windows: dark glass in a black metal frame, a mullion down the wide ones.
    sill, head = walk_top + 36.0, walk_top + 132.0
    for index, (centre, span, mullion) in enumerate(FRONTAGE_WINDOWS):
        a0, a1 = centre - span / 2.0, centre + span / 2.0
        bp.add_block(
            Bounds.between((fx - 1.0, a0, sill), (fx, a1, head)),
            _faces(CAULK, west=_GLASS),
            reachable=False,
            id=f"lot_window_{index}_glass",
        )
        bars = [
            ((a0 - 4.0, sill - 4.0), (a1 + 4.0, sill)),
            ((a0 - 4.0, head), (a1 + 4.0, head + 4.0)),
            ((a0 - 4.0, sill), (a0, head)),
            ((a1, sill), (a1 + 4.0, head)),
        ]
        if mullion:
            bars.append(((centre - 2.0, sill), (centre + 2.0, head)))
        for bar, ((b0, z0), (b1, z1)) in enumerate(bars):
            bp.add_block(
                Bounds.between((fx - 3.0 if bar < 4 else fx - 2.0, b0, z0),
                               (fx if bar < 4 else fx - 1.0, b1, z1)),
                _faces(_BLACK, east=CAULK),
                reachable=False,
                id=f"lot_window_{index}_frame_{bar}",
            )
            laid += 1
        laid += 1
    # The sign band over the canopy, where the branch's name would go.
    canopy_top = walk_top + plan.canopy_height + 16.0
    bp.add_block(
        Bounds.between((fx - 6.0, -240.0, canopy_top + 16.0),
                       (fx, 240.0, canopy_top + 52.0)),
        _faces(_BLACK, east=CAULK, west=_FASCIA),
        reachable=False,
        id="lot_sign_band",
    )
    laid += 1
    # The cornice under the parapet, and the coping on top of every wall of
    # the site: the frontage's in precast trim, the boundary's the same.
    bp.add_block(
        Bounds.between((fx - 8.0, y_lo, top - 24.0), (fx, y_hi, top - 12.0)),
        _faces(_COPING, east=CAULK),
        reachable=False,
        id="lot_cornice",
    )
    laid += 1
    outer = plan.lot
    for side, span in (
        (Side.EAST, Bounds.between((fx - 4.0, outer.mins.y, top), (outer.maxs.x, outer.maxs.y, top + 6.0))),
        (Side.WEST, Bounds.between((outer.mins.x, outer.mins.y, top), (box.mins.x + 4.0, outer.maxs.y, top + 6.0))),
        (Side.NORTH, Bounds.between((box.mins.x + 4.0, box.maxs.y - 4.0, top), (fx - 4.0, outer.maxs.y, top + 6.0))),
        (Side.SOUTH, Bounds.between((box.mins.x + 4.0, outer.mins.y, top), (fx - 4.0, box.mins.y + 4.0, top + 6.0))),
    ):
        # Trim all round, its underside too: it overhangs the lot's inner
        # wall face by 4, and from the car park that lip's caulk underside
        # showed the sky through the coping (Z84).
        bp.add_block(span, FaceMaterials.uniform(_COPING), reachable=False,
                     id=f"lot_coping_{side.name.lower()}")
        laid += 1
    return laid


def _furnish_lived_in(bp: Blueprint, plan: "DmvPlan", rooms: Mapping[str, object], *,
                      walk_top: float, walk_x0: float) -> int:
    """The second furnishing pass: what makes the branch look worked in.

    Rooms with only their fixtures read as too sparse for a real office.
    The first pass put in what each room *is* (the counter, the chairs, the
    chart); this one puts in what people leave behind: a terminal, a mug and a
    paper stack on every staff desk, filing cabinets against the walls, a
    fridge and a coffee maker in the break room, more rows of chairs and a
    line of stanchion posts in the waiting room, clocks, notice boards and
    pictures on the walls, bins, plants and bollards.

    Everything here is scenery.  The gameplay layout -- the queue rails, the
    arena in front of the operator's window, every perk, buy, riser and the
    ticket machine -- is untouched, and every solid piece stands against a
    wall or in a corner, out of every doorway's clear zone (``Z53``) and off
    the lanes the rooms are walked along.  Desk clutter is not solid: a mug
    is not an obstacle.  Models are the measured ones only
    (:data:`zmforge.recipes.props.MODEL_BOX`); there is no desk monitor, phone,
    microwave or stanchion rope in the install's usable set, so the terminal is
    ``p7_keyboard_metal_tech`` (a keyboard deck with its own lit display) and
    the stanchions are handrail posts with brush belts between them
    (:func:`_belt_line`).  Returns how many props it placed.
    """
    placed = 0

    def put(items: list[tuple], ident: str) -> None:
        nonlocal placed
        bp.place_props(items, id=ident)
        placed += len(items)

    terminal = "p7_keyboard_metal_tech"
    chair = "p7_chair_waiting_room_01_blue"
    bin_ = "p7_trashcan_metal_modern_glass"
    picture = "p7_picture_frame_modern_01"
    clock = "p7_clock_metal_wall_01_base"
    board = "p7_zm_der2_bulletin_board"
    cabinet = "p7_file_cab_metal_02"
    # The file cabinet's drawers look along its own -y, so a cabinet backed
    # onto a wall that faces F is turned by F's yaw plus 90.
    cab_yaw = {facing: (facing.world_yaw + 90.0) % 360.0 for facing in Facing}
    # The terminal's display looks along its own +y (and up).
    term_yaw = {facing: (facing.world_yaw - 90.0) % 360.0 for facing in Facing}

    # ---- the car park and the walk -----------------------------------
    lot = rooms["lot"]
    lot_in = lot.interior
    outside: list[tuple] = [
        ("p7_3arc_park_pylon",
         Point(walk_x0 + 8.0, y, _rest_on("p7_3arc_park_pylon", walk_top)),
         0.0, 1.0, True)
        for y in (-580.0, -440.0, -300.0, 300.0, 440.0, 580.0)
    ]
    outside += [
        _floor("p7_bench_modern_01", walk_x0 + 30.0, 190.0, walk_top, 90.0),
        _floor(bin_, lot_in.maxs.x - 44.0, -96.0, walk_top),
        _floor("p7_3arc_park_doormat", lot_in.maxs.x - 20.0, 0.0, walk_top, 90.0,
               solid=False),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(lot_in.maxs.x - 3.0, 300.0, walk_top + 90.0), Facing.WEST),
    ]
    for y in (-560.0, 560.0):
        outside.append(_floor("p7_cai_planter_square_lrg", lot_in.maxs.x - 44.0, y, walk_top))
        outside.append(_on("p7_foliage_plant_aloe_pruned", lot_in.maxs.x - 44.0, y,
                           _top_of("p7_cai_planter_square_lrg", walk_top), float(int(y) % 90)))
    # In the frontage's rectangle planters, which moved from 190 to 270
    # (``lot_frontage``); left at 190 the aloes hung 60 over the footway.
    for y in (-270.0, 270.0):
        outside.append(_on("p7_foliage_plant_aloe_medium", lot_in.maxs.x - 60.0, y,
                           _top_of("p7_cai_planter_rectangle", walk_top), 30.0))
    # (No footway litter here: the lot's 100-prop budget goes to the parked
    # cars, ``lot_cars``.)
    put(outside, "lot_lived_in")

    # ---- entry lobby -------------------------------------------------
    entry = rooms["entry"]
    e_in = entry.interior
    ez = entry.floor_z
    lobby: list[tuple] = [
        _floor("p7_3arc_park_doormat", e_in.mins.x + 24.0, 0.0, ez, 90.0, solid=False),
        _floor("p7_foliage_plant_aloe_pruned", e_in.mins.x + 28.0, e_in.maxs.y - 28.0, ez, 40.0),
        _floor(bin_, e_in.maxs.x - 104.0, e_in.maxs.y - 22.0, ez),
        _mounted(clock, Point(e_in.mins.x + 64.0, e_in.maxs.y - 3.0, ez + 120.0), Facing.SOUTH),
        _mounted(board, Point(e_in.maxs.x - 74.0, e_in.mins.y + 3.0, ez + 90.0), Facing.NORTH),
        _mounted(picture, Point(e_in.maxs.x - 2.0, -150.0, ez + 100.0), Facing.WEST),
        _mounted(picture, Point(e_in.mins.x + 2.0, -230.0, ez + 100.0), Facing.EAST),
    ]
    lobby += [
        _seated(chair, Point(x, e_in.mins.y + 15.0, _rest_on(chair, ez)), Facing.NORTH)
        for x in (e_in.mins.x + 54.0, e_in.mins.x + 78.0, e_in.mins.x + 102.0)
    ]
    put(lobby, "entry_lived_in")

    # ---- waiting room ------------------------------------------------
    waiting = rooms["waiting"]
    w_in = waiting.interior
    wz = waiting.floor_z
    wait: list[tuple] = [
        _seated(chair, Point(x, w_in.maxs.y - 16.0, _rest_on(chair, wz)), Facing.SOUTH)
        for x in (-1070.0, -1026.0, -982.0, -938.0, -894.0)
    ]
    wait += [
        _seated(chair, Point(x, w_in.mins.y + 16.0, _rest_on(chair, wz)), Facing.NORTH)
        # Three, not four: the fourth stood 27 from the photo booth's door.
        for x in (-1060.0, -1016.0, -972.0)
    ]
    # The line: two rows of posts marking a lane along the room's south
    # half, belted post to post (below, after the scatter), so the lane
    # between them is a line you walk in at one end and out at the other.
    # 104 apart: 96 clear between the two clips, Treyarch's hallway minimum
    # (at 64 apart N5 warned of a 56-wide pinch 220 long).
    line_xs = (-1060.0, -1005.0, -950.0, -895.0, -840.0)
    line_ys = (-150.0, -254.0)
    wait += [
        ("p7_handrail_post_middle",
         Point(x, y, _rest_on("p7_handrail_post_middle", wz)), 0.0, 1.0, True)
        for y in line_ys
        for x in line_xs
    ]
    cooler_at = Point(w_in.mins.x + 10.0, -330.0, 0.0)
    wait += [
        _floor("p7_water_cooler_digital_body", cooler_at.x, cooler_at.y, wz, 0.0),
        _on("p7_water_cooler_digital_bottle", cooler_at.x, cooler_at.y,
            _top_of("p7_water_cooler_digital_body", wz)),
        _floor(bin_, w_in.mins.x + 20.0, -380.0, wz),
        _floor("p7_foliage_plant_aloe_medium", w_in.maxs.x - 40.0, w_in.mins.y + 40.0, wz, 15.0),
        _mounted(picture, Point(-1000.0, w_in.mins.y + 2.0, wz + 100.0), Facing.NORTH),
        _mounted(picture, Point(-980.0, w_in.maxs.y - 2.0, wz + 100.0), Facing.SOUTH),
    ]
    put(wait, "waiting_lived_in")
    for index, y in enumerate(line_ys):
        _belt_line(bp, [(x, y) for x in line_xs], wz, f"waiting_belt_{index}")

    # ---- service windows: the staff side of the counter --------------
    windows = rooms["windows"]
    v_in = windows.interior
    vz = windows.floor_z
    face_x, back_x, _run_y0, _run_y1 = counter_run(plan)
    ledge_x1 = face_x + plan.patron_ledge_depth
    centres = bay_centres(plan)
    pitch = bay_pitch(plan)
    staff_x = back_x + 66.0
    desk_top = _top_of("p7_desk_metal_old_01_body", vz)
    staff: list[tuple] = []
    # Every workstation: the terminal at the end the clerk sits at, a stack
    # of forms, a folder and the clerk's mug.
    for index in (0, 2, 4, 6):
        y = centres[index] + pitch / 2.0
        staff += [
            _on(terminal, staff_x + 20.0, y, desk_top, term_yaw[Facing.EAST], scale=0.7),
            _on("p7_office_paper_stack_sml", staff_x - 18.0, y, desk_top),
            _on("p7_office_paper_folder_pink", staff_x + 2.0, y + 6.0, desk_top, 15.0),
            _on("p7_cup_coffee_mug", staff_x + 29.0, y - 12.0, desk_top, index * 40.0),
        ]
    # The work surface behind the partition has somebody's things on it.
    surface = vz + plan.staff_surface_height
    for index, model in ((0, "p7_office_paper_stack_sml"), (2, "p7_cup_coffee_mug"),
                         (3, "p7_office_paper_folder_pink"), (7, "p7_office_paper_sheet_01")):
        staff.append(_on(model, (ledge_x1 + back_x) / 2.0, centres[index] + 12.0,
                         surface, index * 29.0))
    # The two base cabinets on the east wall are the kitchenette and the
    # in-tray: a coffee maker and mugs on one, paperwork on the other.
    cab_top = _top_of("p7_zm_der_cabinet_lab_bottom", vz)
    staff += [
        _on("p7_coffee_maker_digital", v_in.maxs.x - 16.0, 184.0, cab_top, 180.0),
        _on("p7_cup_coffee_mug", v_in.maxs.x - 20.0, 206.0, cab_top, 10.0),
        _on("p7_cup_coffee_mug", v_in.maxs.x - 12.0, 216.0, cab_top, 200.0),
        _on("p7_office_paper_stack_sml", v_in.maxs.x - 16.0, -190.0, cab_top, 0.0),
        _on("p7_book_office_binder_open", v_in.maxs.x - 16.0, -228.0, cab_top, 0.0),
    ]
    staff += [
        _floor(cabinet, v_in.maxs.x - 16.0, y, vz, cab_yaw[Facing.WEST])
        # 48 clear of the records door (y -40..40) edge to edge.
        for y in (100.0, 120.0, 140.0, -100.0, -120.0, -140.0)
    ]
    staff += [
        _floor(bin_, staff_x + 90.0, -250.0, vz),
        _mounted(clock, Point(v_in.maxs.x - 3.0, -300.0, vz + 120.0), Facing.WEST),
        _mounted(picture, Point(v_in.maxs.x - 2.0, 300.0, vz + 100.0), Facing.WEST),
        _mounted(board, Point(v_in.maxs.x - 3.0, -210.0, vz + 96.0), Facing.WEST),
        # The public side's walls.
        _mounted(picture, Point(v_in.mins.x + 2.0, -200.0, vz + 100.0), Facing.EAST),
        _mounted(clock, Point(v_in.mins.x + 3.0, 200.0, vz + 120.0), Facing.EAST),
    ]
    put(staff, "windows_lived_in")

    # ---- vision screening ----------------------------------------------
    eye = rooms["eye"]
    y_in = eye.interior
    yz = eye.floor_z
    table = "p7_cai_work_table_metal_03_white"
    table_x, table_y = y_in.maxs.x - 12.0, y_in.mins.y + 50.0
    table_top = _top_of(table, yz)
    put([
        _floor(table, table_x, table_y, yz, 0.0),
        # The screening machine: the lit deck, turned to the patient's chair.
        _on(terminal, table_x - 2.0, table_y - 14.0, table_top, term_yaw[Facing.WEST], scale=0.8),
        _on("p7_office_paper_stack_sml", table_x, table_y + 22.0, table_top, 5.0),
        _on("p7_cup_coffee_mug", table_x + 2.0, table_y + 36.0, table_top, 120.0),
        _floor(bin_, y_in.mins.x + 19.0, y_in.mins.y + 19.0, yz),
        _mounted(clock, Point(y_in.mins.x + 3.0, y_in.maxs.y - 44.0, yz + 120.0), Facing.EAST),
        _mounted(board, Point(y_in.maxs.x - 33.0, y_in.mins.y + 3.0, yz + 96.0), Facing.NORTH),
        _mounted(picture, Point(y_in.mins.x + 33.0, y_in.mins.y + 2.0, yz + 100.0), Facing.NORTH),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(y_in.mins.x + 3.0, y_in.mins.y + 54.0, yz + 104.0), Facing.EAST),
    ], "eye_lived_in")

    # ---- photo booth ---------------------------------------------------
    photo = rooms["photo"]
    p_in = photo.interior
    pz = photo.floor_z
    put([
        _seated("p7_chair_lab_01",
                Point(p_in.mins.x + 60.0, p_in.maxs.y - 118.0, _rest_on("p7_chair_lab_01", pz)),
                Facing.EAST),
        _floor(bin_, p_in.maxs.x - 20.0, p_in.maxs.y - 20.0, pz),
        _floor("p7_container_cardboard_box_01", p_in.mins.x + 22.0, p_in.maxs.y - 24.0, pz, 90.0),
        _floor("p7_foliage_plant_aloe_pruned", p_in.maxs.x - 26.0, p_in.mins.y + 26.0, pz, 200.0),
        _mounted(clock, Point(p_in.maxs.x - 3.0, p_in.maxs.y - 60.0, pz + 120.0), Facing.WEST),
        _mounted(picture, Point(p_in.mins.x + 2.0, p_in.mins.y + 60.0, pz + 100.0), Facing.EAST),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(p_in.maxs.x - 3.0, p_in.mins.y + 60.0, pz + 100.0), Facing.WEST),
    ], "photo_lived_in")

    # ---- break room ----------------------------------------------------
    brk = rooms["break"]
    b_in = brk.interior
    bz = brk.floor_z
    fridge = "p7_cai_fridge_metal_plant"
    counter = "p7_zm_der_cabinet_lab_bottom"
    # Flush on the wall: clear of the break_power lane (dmv_rooms/break_room.py).
    counter_x, counter_y = b_in.mins.x + 54.0, b_in.maxs.y - 16.0
    counter_top = _top_of(counter, bz)
    table_at = Point(b_in.mins.x + 68.0, b_in.centre.y, 0.0)  # as break_props (below)
    put([
        # The fridge's door is on its own +x, so facing west is yaw 180.
        _floor(fridge, b_in.maxs.x - 13.0, b_in.mins.y + 124.0, bz, 180.0),
        _floor(counter, counter_x, counter_y, bz, 0.0),
        _on("p7_coffee_maker_digital", counter_x - 34.0, counter_y, counter_top, 270.0),
        _on("p7_cup_coffee_mug", counter_x - 14.0, counter_y - 6.0, counter_top, 40.0),
        _on("p7_cup_coffee_mug", counter_x - 6.0, counter_y + 5.0, counter_top, 250.0),
        _on("p7_cleaning_paper_towel", counter_x + 12.0, counter_y - 4.0, counter_top, 20.0),
        _on("p7_food_fruit_banana_bunch", counter_x + 32.0, counter_y, counter_top, 70.0),
        _seated("p7_chair_lab_01",
                Point(table_at.x - 44.0, table_at.y - 26.0, _rest_on("p7_chair_lab_01", bz)),
                Facing.EAST),
        _seated("p7_chair_lab_01",
                Point(table_at.x - 44.0, table_at.y + 26.0, _rest_on("p7_chair_lab_01", bz)),
                Facing.EAST),
        _mounted(clock, Point(b_in.maxs.x - 3.0, b_in.maxs.y - 64.0, bz + 120.0), Facing.WEST),
        _mounted("p7_zm_der_signage_wash_hands",
                 Point(b_in.maxs.x - 34.0, b_in.mins.y + 1.0, bz + 90.0), Facing.NORTH),
        _mounted(picture, Point(b_in.mins.x + 44.0, b_in.mins.y + 2.0, bz + 100.0), Facing.NORTH),
    ], "break_lived_in")

    # ---- records store -------------------------------------------------
    rec = rooms["records"]
    r_in = rec.interior
    rz = rec.floor_z
    lab_top = _top_of("p7_zm_der_cabinet_lab_bottom", rz)
    store: list[tuple] = [
        _on(model, r_in.mins.x + 16.5, y, lab_top, yaw)
        for model, y, yaw in (("p7_container_cardboard_box_01", 326.0, 90.0),
                              ("p7_office_paper_stack_sml", 218.0, 10.0),
                              ("p7_books_office_row_01", 110.0, 90.0),
                              ("p7_book_office_binder_open", -110.0, 75.0),
                              ("p7_container_cardboard_box_01", -218.0, 95.0),
                              ("p7_office_paper_stack_sml", -326.0, 200.0))
    ]
    store += [
        _floor(cabinet, r_in.maxs.x - 16.0, y, rz, cab_yaw[Facing.WEST])
        for y in (310.0, 330.0, -310.0, -330.0)
    ]
    store += [
        _floor(bin_, r_in.mins.x + 24.0, 70.0, rz),
        _mounted(clock, Point(r_in.mins.x + 124.0, r_in.maxs.y - 3.0, rz + 120.0), Facing.SOUTH),
        _mounted(board, Point(r_in.maxs.x - 134.0, r_in.mins.y + 3.0, rz + 96.0), Facing.NORTH),
    ]
    put(store, "records_lived_in")

    # ---- the queue hall --------------------------------------------------
    # Only the walls and the wide last lane's north side: the lanes are the
    # gameplay and stay open.
    queue = rooms["queue"]
    q_in = queue.interior
    qz = queue.floor_z
    lanes = _lanes(plan)
    mid = [(a + b) / 2.0 for a, b in lanes]
    hall: list[tuple] = [
        _seated(chair, Point(x, q_in.maxs.y - 16.0, _rest_on(chair, qz)), Facing.SOUTH)
        for x in (600.0, 644.0, 688.0, 732.0, 776.0)
    ]
    hall += [
        _floor(bin_, 840.0, q_in.maxs.y - 20.0, qz),
        _floor("p7_water_cooler_digital_body", 900.0, q_in.maxs.y - 10.0, qz, 270.0),
        _on("p7_water_cooler_digital_bottle", 900.0, q_in.maxs.y - 10.0,
            _top_of("p7_water_cooler_digital_body", qz)),
        _floor("p7_foliage_plant_aloe_medium", 1070.0, q_in.maxs.y - 36.0, qz, 80.0),
        _floor(bin_, q_in.maxs.x - 20.0, q_in.mins.y + 20.0, qz),
        _mounted(clock, Point(700.0, q_in.maxs.y - 3.0, qz + 120.0), Facing.SOUTH),
        _mounted(clock, Point(800.0, q_in.mins.y + 3.0, qz + 120.0), Facing.NORTH),
        _mounted(picture, Point(q_in.mins.x + 2.0, mid[1], qz + 100.0), Facing.EAST),
        _mounted(picture, Point(q_in.mins.x + 2.0, mid[3], qz + 100.0), Facing.EAST),
        _mounted(picture, Point(q_in.maxs.x - 2.0, mid[2], qz + 100.0), Facing.WEST),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(q_in.maxs.x - 3.0, mid[0], qz + 100.0), Facing.WEST),
    ]
    for index, (x, lane) in enumerate(((700.0, 1), (950.0, 2), (620.0, 3))):
        model = ("p7_debris_trash_cup_coffee_02", "p7_debris_trash_paper_08",
                 "p7_debris_newspaper_01")[index]
        hall.append(_floor(model, x, mid[lane] + 20.0, qz, index * 83.0, solid=False))
    put(hall, "queue_lived_in")

    # ---- back office -------------------------------------------------------
    # The booth behind the counter gets the clutter; the arena in front of it
    # gets only its walls and its south edge.
    office = rooms["office"]
    o_in = office.interior
    oz = office.floor_z
    counter_north = o_in.maxs.y - plan.booth_depth
    counter_mid = counter_north - 8.0
    counter_top_z = oz + plan.counter_height
    desk_x, desk_y = o_in.centre.x - 120.0, counter_north + 40.0
    office_desk_top = _top_of("p7_desk_metal_old_01_body", oz)
    put([
        _on(terminal, desk_x, desk_y + 12.0, office_desk_top, term_yaw[Facing.NORTH], scale=0.7),
        _on("p7_office_paper_stack_sml", desk_x - 8.0, desk_y - 21.0, office_desk_top, 30.0),
        _on("p7_office_paper_folder_pink", desk_x + 8.0, desk_y - 4.0, office_desk_top, 280.0),
        _on("p7_cup_coffee_mug", desk_x + 12.0, desk_y - 28.0, office_desk_top, 90.0),
        _on("p7_cup_coffee_mug", o_in.centre.x - 30.0, counter_mid, counter_top_z, 15.0),
        _on("p7_office_paper_folder_pink", o_in.centre.x - 180.0, counter_mid, counter_top_z, 95.0),
        _on("p7_office_paper_sheet_01", o_in.centre.x + 20.0, counter_mid, counter_top_z, 80.0),
        _floor(cabinet, o_in.centre.x, o_in.maxs.y - 16.0, oz, cab_yaw[Facing.SOUTH]),
        _floor(cabinet, o_in.centre.x + 20.0, o_in.maxs.y - 16.0, oz, cab_yaw[Facing.SOUTH]),
        _floor(bin_, o_in.centre.x - 60.0, o_in.maxs.y - 20.0, oz),
        _floor("p7_container_cardboard_box_01", o_in.centre.x + 70.0, o_in.maxs.y - 20.0, oz),
        _floor("p7_water_cooler_digital_body", o_in.maxs.x - 10.0, o_in.mins.y + 400.0, oz, 180.0),
        _on("p7_water_cooler_digital_bottle", o_in.maxs.x - 10.0, o_in.mins.y + 400.0,
            _top_of("p7_water_cooler_digital_body", oz)),
        _floor(bin_, o_in.maxs.x - 20.0, o_in.mins.y + 450.0, oz),
        _mounted(picture, Point(o_in.mins.x + 110.0, o_in.mins.y + 2.0, oz + 110.0), Facing.NORTH),
        _mounted(picture, Point(o_in.maxs.x - 110.0, o_in.mins.y + 2.0, oz + 110.0), Facing.NORTH),
    ] + [
        _seated(chair, Point(x, o_in.mins.y + 16.0, _rest_on(chair, oz)), Facing.NORTH)
        for x in (o_in.mins.x + 144.0, o_in.mins.x + 168.0, o_in.mins.x + 192.0)
    ], "office_lived_in")
    return placed


def _furnish_character(bp: Blueprint, plan: "DmvPlan", rooms: Mapping[str, object], *,
                       walk_top: float, walk_x0: float) -> int:
    """The third furnishing pass: what the outbreak left behind.

    The aim is character: a DMV after the zombies, funny and
    lived in.  So this pass is set pieces rather than furniture, one or two a
    room, each of them something a person *did* here: boards nailed over the
    street windows and sandbags under one, a hot-dog cart abandoned in a bay,
    what is left of customer 846 still in his seat with his ticket at his
    feet, a chair pulled round to face the wall, a lost teddy and a
    suitcase, a suggestion box, a broken water cooler, anatomy charts in the
    eye test, rejected licence photos, a retirement cake, a survivor's camp
    among the records and a manager's desk with a bottle in it -- and paper,
    everywhere, in more than one kind.  :data:`NOTICE_LINES` is the text
    half of the same pass.

    Same rules as :func:`_furnish_lived_in`: measured models only
    (:data:`zmforge.recipes.props.MODEL_BOX`), every solid piece against a
    wall or in a corner and clear of the doorways (``Z53``) and the walls
    (``Z54``), litter not solid, and nothing on the queue's lanes or in
    front of a perk, a buy, the box or the switch.  No prop here can be
    tipped over -- a prop carries a yaw and nothing else -- so a knocked
    chair is a chair turned the wrong way.  Returns how many props it placed.
    """
    placed = 0

    def put(items: list[tuple], ident: str) -> None:
        nonlocal placed
        bp.place_props(items, id=ident)
        placed += len(items)

    chair = "p7_chair_waiting_room_01_blue"
    board = ("p7_anim_zm_barricade_board_01", "p7_anim_zm_barricade_board_03",
             "p7_anim_zm_barricade_board_05")

    # ---- the car park: boarded windows, a sandbag line, the cart --------
    lot = rooms["lot"]
    fx = lot.interior.maxs.x
    sill = walk_top + 36.0
    # A board's plank is 2.07 through and centred on its origin; the window
    # frame stands 3 proud of the brick, so the board's back is on the frame.
    board_x = fx - 3.0 - 1.04
    outside: list[tuple] = []
    for index, (centre, span, _mullion) in enumerate(FRONTAGE_WINDOWS):
        if span <= 110.0:
            rows = ((centre, 18.0), (centre, 46.0), (centre, 74.0))
        else:
            rows = ((centre - 28.0, 20.0), (centre + 28.0, 44.0),
                    (centre - 20.0, 70.0), (centre + 26.0, 88.0))
        for row, (y, height) in enumerate(rows):
            outside.append(_mounted(board[(index + row) % len(board)],
                                    Point(board_x, y, sill + height), Facing.WEST))
    # Sandbags under the north pair of windows, two courses, on the walk and
    # clear of the base band (3 proud).  Ten units a bag: litter, not a wall.
    bag = "p7_sandbag_02"
    bag_x = fx - 3.5 - 10.1
    # The top course straddles the seams, and a bag is a pillow, not a brick:
    # its box top is its crown, and at a seam the two ends under it are down
    # to 6.5 of their 9.7.  Set on the box tops, the upper bags touched
    # nothing (0.78 clear at best, measured on the p7_sandbag_02 mesh)
    # and read as floating in game; 2 lower they settle into the
    # crowns below the way a filled bag does (1.2 deep at the most).
    bag_top = _top_of(bag, walk_top) - 2.0
    outside += [_floor(bag, bag_x, y, walk_top, 0.0, solid=False)
                for y in (360.0, 396.0, 432.0, 468.0)]
    outside += [_on(bag, bag_x, y, bag_top, 0.0) for y in (378.0, 414.0, 450.0)]
    outside += [
        _floor("p7_pallet_wood_damaged", fx - 64.0, 390.0, walk_top, 80.0, solid=False),
        _floor("p7_debris_wood_board_cluster_01", fx - 104.0, 650.0, walk_top, 25.0,
               solid=False),
        _floor("p7_debris_concrete_rubble_sm_02", fx - 30.0, 506.0, walk_top, 40.0,
               solid=False),
        _floor("p7_debris_brick_single_01", fx - 44.0, 334.0, walk_top, 70.0, solid=False),
    ]
    # The hot-dog cart, left askew across a bay in the far row, and a
    # suitcase somebody put down to run.
    cart_at = Point(-2420.0, 486.0, 0.0)
    outside += [
        _floor("p7_wheel_barrow_street_vendor", cart_at.x, cart_at.y, lot.floor_z, 70.0),
        _floor("p7_luggage_hardshell_handle_down_white", cart_at.x + 60.0, cart_at.y - 70.0,
               lot.floor_z, 30.0),
    ]
    put(outside, "lot_character")

    # ---- entry: the rack's forms on the floor, the chair dragged away -----
    entry = rooms["entry"]
    e_in = entry.interior
    ez = entry.floor_z
    put([
        # West of the north window's clear floor (the barrier is at x -1400).
        # A waiting chair somebody dragged over to watch the window from, not a
        # broken water cooler: beside the ticket machine's cooler body that
        # reads as two coolers.
        _floor("p7_chair_waiting_room_01_blue", -1540.0, e_in.maxs.y - 18.0, ez, 205.0),
        _floor("p7_debris_newspaper_02", e_in.mins.x + 80.0, -150.0, ez, 30.0, solid=False),
        _floor("p7_office_paper_sheet_02", e_in.mins.x + 80.0, -104.0, ez, 75.0, solid=False),
        _floor("p7_office_paper_sheet_12", e_in.mins.x + 56.0, -62.0, ez, 200.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", -1478.0, e_in.maxs.y - 36.0, ez, 0.0,
               solid=False),
    ], "entry_character")

    # ---- waiting: customer 846, the chair facing the wall, lost property -
    waiting = rooms["waiting"]
    w_in = waiting.interior
    wz = waiting.floor_z
    front_x = w_in.maxs.x - 150.0
    last_y = (w_in.centre.y - (plan.chair_cols - 1) * plan.seat_pitch / 2.0
              + (plan.chair_cols - 1) * plan.seat_pitch)
    # The front row faces east, so the seat's centre is 2.5 east of the
    # chair's origin and its top 18.85 above the floor.
    seat_x, seat_top = front_x + WAITING_SEAT_FORWARD, wz + WAITING_SEAT_TOP
    wait: list[tuple] = [
        _on("p7_gib_chunk_bone_01", seat_x - 4.0, last_y - 4.0, seat_top, 20.0),
        _on("p7_gib_chunk_bone_03", seat_x + 2.0, last_y + 5.0, seat_top, 110.0),
        _on("p7_gib_chunk_meat_01", seat_x - 1.0, last_y + 0.5, seat_top, 75.0),
        _on("p7_gib_chunk_flesh_01", seat_x + 5.0, last_y - 3.0, seat_top, 300.0),
        # His ticket, and the rest of him, on the floor in front of the seat.
        _floor("p7_office_paper_sheet_12", front_x + 26.0, last_y - 8.0, wz, 35.0,
               solid=False),
        _floor("p7_gib_chunk_meat_02", front_x + 22.0, last_y + 8.0, wz, 140.0, solid=False),
        # A chair pulled out of the wall row and turned to the wall.
        _seated(chair, Point(w_in.maxs.x - 18.0, 300.0 - 64.0, _rest_on(chair, wz)),
                Facing.EAST),
        # One pulled away from the north row, left at an angle.
        (chair, Point(-1000.0, 404.0, _rest_on(chair, wz)), 205.0, 1.0, True),
        # Lost property: a bag by the north row, and a teddy left sitting in
        # the east chair of the south row, beside the camp (which faces north, so its seat is
        # 2.5 north of its origin), keeping somebody's place.
        _floor("p7_luggage_cloth_a_lg_green", -1120.0, w_in.maxs.y - 12.0, wz, 10.0),
        ("p7_zm_teddybear",
         Point(-972.0, w_in.mins.y + 16.0 + WAITING_SEAT_FORWARD,
               _rest_on("p7_zm_teddybear", wz + WAITING_SEAT_TOP)),
         0.0, 1.0, True),
        # The suggestion box: a crate on the west wall, suggestions on top.
        _floor("p7_crate_wood_01_short", w_in.mins.x + 16.5, 250.0, wz, 0.0),
        _on("p7_office_paper_sheet_02", w_in.mins.x + 16.0, 250.0,
            _top_of("p7_crate_wood_01_short", wz), 20.0),
    ]
    for index, (model, x, y) in enumerate((
        ("p7_debris_trash_drink_carrier_01", -904.0, 150.0),
        ("p7_debris_trash_drink_carrier_01", -962.0, -134.0),
        ("p7_debris_newspaper_06", -1100.0, 240.0),
        ("p7_debris_newspaper_08", -820.0, -380.0),
        ("p7_debris_trash_cup_coffee_02", -812.0, 60.0),
        ("p7_cleaning_paper_ball_brown", -990.0, 300.0),
    )):
        wait.append(_floor(model, x, y, wz, index * 71.0, solid=False))
    put(wait, "waiting_character")

    # ---- counter hall: a spill by the counter, a drawer pulled out -------
    windows = rooms["windows"]
    v_in = windows.interior
    vz = windows.floor_z
    face_x, back_x, _run_y0, _run_y1 = counter_run(plan)
    centres = bay_centres(plan)
    put([
        _floor("p7_debris_newspaper_03", face_x - 40.0, centres[6] - 20.0, vz, 50.0,
               solid=False),
        _floor("p7_office_paper_sheet_02", face_x - 70.0, centres[1] + 10.0, vz, 130.0,
               solid=False),
        _floor("p7_file_cab_metal_02_drawer_02", v_in.maxs.x - 60.0, 150.0, vz, 250.0,
               solid=False),
        _floor("p7_office_paper_sheet_12", v_in.maxs.x - 84.0, 170.0, vz, 15.0, solid=False),
        _floor("p7_debris_newspaper_08", back_x + 200.0, -80.0, vz, 200.0, solid=False),
    ], "windows_character")

    # ---- eye test: the charts a clinic hangs ----------------------------
    eye = rooms["eye"]
    y_in = eye.interior
    yz = eye.floor_z
    put([
        _mounted("p7_zm_der2_poster_anatomy_01",
                 Point(y_in.maxs.x - 0.5, 640.0, yz + 84.0), Facing.WEST),
        _mounted("p7_zm_der2_poster_anatomy_04",
                 Point(-600.0, y_in.maxs.y - 0.5, yz + 100.0), Facing.SOUTH),
        _floor("p7_office_paper_sheet_02", -560.0, 470.0, yz, 60.0, solid=False),
    ], "eye_character")

    # ---- photo booth: the rejects ---------------------------------------
    photo = rooms["photo"]
    p_in = photo.interior
    pz = photo.floor_z
    put([
        _floor(model, x, y, pz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_office_paper_sheet_02", p_in.maxs.x - 60.0, p_in.maxs.y - 44.0, 10.0),
            ("p7_office_paper_sheet_12", p_in.maxs.x - 78.0, p_in.maxs.y - 66.0, 80.0),
            ("p7_cleaning_paper_ball_brown", p_in.maxs.x - 50.0, p_in.maxs.y - 72.0, 0.0),
            ("p7_cleaning_paper_ball_brown", p_in.maxs.x - 36.0, p_in.maxs.y - 84.0, 90.0),
        )
    ], "photo_character")

    # ---- break room: Gary's cake, and the party after it ----------------
    brk = rooms["break"]
    b_in = brk.interior
    bz = brk.floor_z
    table = "p7_cai_work_table_metal_03_white"
    table_at = Point(b_in.mins.x + 68.0, b_in.centre.y, 0.0)  # as break_props (below)
    put([
        # Between the donuts (to y 545) and the mug (from y 561).
        # A kit prop, so solid like the donuts: the kit ships its collmap.
        _centred("zmf_prop_birthday_cake", table_at.x, table_at.y + 3.0,
                 _rest_on("zmf_prop_birthday_cake", _top_of(table, bz)), 0.0, solid=True),
    ] + [
        _floor(model, x, y, bz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_trash_paper_plate_01", -214.0, 560.0, 0.0),
            ("p7_debris_trash_paper_plate_01", -186.0, 628.0, 0.0),
            ("p7_debris_trash_cup_red_02", -200.0, 600.0, 0.0),
            ("p7_debris_trash_cup_red_02", -236.0, 470.0, 0.0),
            ("p7_debris_trash_drink_carrier_01", -170.0, 456.0, 40.0),
        )
    ], "break_character")

    # ---- records: somebody lives here now -------------------------------
    rec = rooms["records"]
    r_in = rec.interior
    rz = rec.floor_z
    bed = "p7_bed_mattress_barrack_made_v2"
    bed_x, bed_y = r_in.maxs.x - 74.0, 110.0
    bed_top = _top_of(bed, rz)
    crate = "p7_crate_wood_01_short_open"
    crate_x, crate_y = bed_x - 70.0, 150.0
    put([
        _floor(bed, bed_x, bed_y, rz, 0.0),
        _on("p7_bed_pillow_barrack", bed_x, bed_y + 32.0, bed_top, 0.0),
        _on("p7_bed_sheet_barrack_02", bed_x, bed_y - 14.0, bed_top, 180.0),
        _floor("p7_zm_der2_light_hurricane_lamp", bed_x + 30.0, bed_y + 60.0, rz, 0.0),
        _floor(crate, crate_x, crate_y, rz, 10.0),
        _on("p7_office_paper_sheet_12", crate_x, crate_y, _top_of(crate, rz), 25.0),
        _floor("p7_bottle_glass_liquor_01", bed_x - 38.0, bed_y - 40.0, rz, 0.0, solid=False),
        _floor("p7_bottle_glass_wine_01", bed_x - 30.0, bed_y - 48.0, rz, 0.0, solid=False),
        _floor("p7_book_office_lrg_red", crate_x - 4.0, crate_y - 34.0, rz, 90.0, solid=False),
        _floor("p7_book_office_med_brown", crate_x + 6.0, crate_y - 34.0, rz, 80.0,
               solid=False),
        # The hoard: drawers pulled out and emptied onto the floor.
        _floor("p7_file_cab_metal_02_drawer_02", r_in.maxs.x - 54.0, 296.0, rz, 90.0,
               solid=False),
        _floor("p7_file_cab_metal_02_drawer_02", r_in.maxs.x - 54.0, -296.0, rz, 90.0,
               solid=False),
        _floor("p7_debris_newspaper_02", r_in.maxs.x - 114.0, -250.0, rz, 60.0, solid=False),
        _floor("p7_office_paper_sheet_02", r_in.maxs.x - 70.0, 270.0, rz, 20.0, solid=False),
        _floor("p7_debris_newspaper_03", 20.0, -300.0, rz, 110.0, solid=False),
    ], "records_character")

    # ---- the queue: more of what a queue drops --------------------------
    queue = rooms["queue"]
    qz = queue.floor_z
    mid = [(a + b) / 2.0 for a, b in _lanes(plan)]
    put([
        _floor(model, x, mid[lane] + dy, qz, index * 61.0, solid=False)
        for index, (model, x, lane, dy) in enumerate((
            ("p7_debris_newspaper_02", 1100.0, 1, 15.0),
            ("p7_debris_trash_drink_carrier_01", 560.0, 3, -18.0),
            ("p7_debris_trash_drink_carrier_01", 820.0, 0, 22.0),
            ("p7_office_paper_sheet_02", 1150.0, 2, 25.0),
            ("p7_debris_newspaper_06", 760.0, 4, -40.0),
        ))
    ], "queue_character")

    # ---- back office: the manager's desk, and the arena floor -----------
    office = rooms["office"]
    o_in = office.interior
    oz = office.floor_z
    counter_north = o_in.maxs.y - plan.booth_depth
    desk_x, desk_y = o_in.centre.x - 120.0, counter_north + 40.0
    desk_top = _top_of("p7_desk_metal_old_01_body", oz)
    put([
        # In the gaps the lived-in pass left on the desk: the bottle beside
        # the folder, the manual stood up by the mug.
        _on("p7_bottle_glass_liquor_01", desk_x - 10.0, desk_y - 1.0, desk_top, 30.0),
        _on("p7_book_office_lrg_red", desk_x + 10.0, desk_y - 19.0, desk_top, 90.0),
    ] + [
        _floor(model, x, y, oz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_newspaper_08", o_in.mins.x + 104.0, o_in.mins.y + 216.0, 30.0),
            ("p7_office_paper_sheet_02", o_in.mins.x + 354.0, o_in.mins.y + 316.0, 110.0),
            ("p7_debris_trash_drink_carrier_01", o_in.mins.x + 254.0, o_in.mins.y + 136.0, 0.0),
            ("p7_office_paper_sheet_12", o_in.mins.x + 404.0, o_in.mins.y + 416.0, 250.0),
        )
    ], "office_character")
    return placed


#: How far a solid floor prop keeps from any doorway, measured edge to edge
#: in plan in every direction.  ``Z53`` keeps the path *through* an opening
#: clear (48 either side, 8 past each jamb); the plain distance matters too:
#: cabinets, chairs and bins flanking the jambs crowd the approach even
#: where they miss the path.  This map keeps both.
DOOR_BAND = 48.0
#: A solid prop no taller than this over its floor is a step, not a crowd.
DOOR_BAND_STEP = 18.0


def _clear_door_bands(bp: Blueprint, rooms: Mapping[str, object]) -> dict[str, str]:
    """Slide every solid floor prop out of :data:`DOOR_BAND` of each doorway.

    Runs after the furnishing passes, over all of them, so no placer has to
    remember it.  A prop within the band is slid along the wall it stands
    against, away from the opening, until its footprint is :data:`DOOR_BAND`
    (+2) clear; whatever sits on it (a plant in a planter, papers on a
    cabinet, a customer in a chair) goes with it.  If the slide would leave
    the room or run into another solid prop it is dropped instead.  Returns
    ``{prop id: "moved"|"dropped"}``.
    """
    from dataclasses import replace

    def gap(a, b) -> float:
        dx = max(b[0] - a[2], a[0] - b[2], 0.0)
        dy = max(b[1] - a[3], a[1] - b[3], 0.0)
        return math.hypot(dx, dy)

    openings: list[tuple[object, tuple[float, float, float, float], bool]] = []
    room_list: list = []
    for room in rooms.values():
        if not any(room is r for r in room_list):
            room_list.append(room)
    for room in room_list:
        for aperture, box in zip(room.apertures, room.aperture_boxes):
            if aperture.sill > 0.0:
                continue
            along_x = aperture.side in (Side.NORTH, Side.SOUTH)
            openings.append((room, (box.mins.x, box.mins.y, box.maxs.x, box.maxs.y), along_x))

    def room_of(x: float, y: float):
        for room in room_list:
            i = room.interior
            if i.mins.x <= x <= i.maxs.x and i.mins.y <= y <= i.maxs.y:
                return room
        return None

    entries = []   # (scatter, index, prop, footprint, z_low, z_high)
    for scatter in bp.elements(PropScatter):
        for index, prop in enumerate(scatter.props):
            measured = collision_box(prop.model)
            if measured is None:
                continue
            placed = Placed.from_model(prop.model, measured,
                                       (prop.origin.x, prop.origin.y, prop.origin.z),
                                       prop.yaw, prop.scale, solid=prop.solid,
                                       ident=prop.id)
            entries.append([scatter, index, prop, tuple(placed.footprint.bounds),
                            placed.z_low, placed.z_high])

    outcome: dict[str, str] = {}
    gone: set[int] = set()
    for n, (scatter, index, prop, fp, z_low, z_high) in enumerate(entries):
        if not prop.solid:
            continue
        room = room_of(prop.origin.x, prop.origin.y)
        if room is None or abs(z_low - room.floor_z) > 8.0:
            continue
        if z_high - room.floor_z <= DOOR_BAND_STEP:
            continue
        inner = (room.interior.mins.x, room.interior.mins.y,
                 room.interior.maxs.x, room.interior.maxs.y)
        # Only this room's own openings: a hole in the next room's wall on
        # the far side of a partition is not this prop's doorway.
        near = [(gap(fp, rect), rect, along_x) for _r, rect, along_x in openings
                if gap(fp, rect) < DOOR_BAND and gap(rect, inner) <= 1.0]
        if not near:
            continue
        _g, rect, along_x = min(near)
        # Along the wall, away from the opening's centre.
        if along_x:
            centre, lo, hi, plo, phi = (rect[0] + rect[2]) / 2.0, rect[0], rect[2], fp[0], fp[2]
            depth = max(rect[1] - fp[3], fp[1] - rect[3], 0.0)
        else:
            centre, lo, hi, plo, phi = (rect[1] + rect[3]) / 2.0, rect[1], rect[3], fp[1], fp[3]
            depth = max(rect[0] - fp[2], fp[0] - rect[2], 0.0)
        sign = 1.0 if (plo + phi) / 2.0 >= centre else -1.0
        need = math.sqrt(max((DOOR_BAND + 2.0) ** 2 - depth ** 2, 0.0))
        along_now = (plo - hi) if sign > 0 else (lo - phi)
        shift = sign * max(need - max(along_now, 0.0), 0.0)
        dx, dy = (shift, 0.0) if along_x else (0.0, shift)
        new_fp = (fp[0] + dx, fp[1] + dy, fp[2] + dx, fp[3] + dy)
        riders = [m for m, e in enumerate(entries)
                  if m != n and m not in gone
                  and fp[0] <= e[2].origin.x <= fp[2] and fp[1] <= e[2].origin.y <= fp[3]
                  and z_high - 24.0 <= e[4] <= z_high + 6.0 and e[4] > z_low + 8.0
                  # a wall fixture (its box straddles its origin in Z) is
                  # hung on the wall above, not standing on the piece
                  and (MODEL_BOX.get(e[2].model) or ((0, 0, 0),))[0][2] >= -2.0]
        i = room.interior
        ok = (i.mins.x <= new_fp[0] and new_fp[2] <= i.maxs.x
              and i.mins.y <= new_fp[1] and new_fp[3] <= i.maxs.y)
        if ok:
            for m, e in enumerate(entries):
                if m == n or m in riders or m in gone or not e[2].solid:
                    continue
                if e[5] <= z_low + 1.0 or e[4] >= z_high - 1.0:
                    continue
                if (new_fp[0] < e[3][2] and e[3][0] < new_fp[2]
                        and new_fp[1] < e[3][3] and e[3][1] < new_fp[3]):
                    ok = False
                    break
        if ok:
            ok = all(gap(new_fp, rect) >= DOOR_BAND for _r, rect, _a in openings)
        if ok:
            for m in [n, *riders]:
                e = entries[m]
                o = e[2].origin
                moved = replace(e[2], origin=Point(o.x + dx, o.y + dy, o.z))
                e[0].props[e[1]] = moved
                e[2] = moved
                e[3] = (e[3][0] + dx, e[3][1] + dy, e[3][2] + dx, e[3][3] + dy)
                outcome[moved.id] = "moved"
        else:
            for m in [n, *riders]:
                gone.add(m)
                outcome[entries[m][2].id] = "dropped"
    for scatter in bp.elements(PropScatter):
        drop = {entries[m][2].id for m in gone if entries[m][0] is scatter}
        if drop:
            scatter.props[:] = [p for p in scatter.props if p.id not in drop]
    return outcome


def _notice_spots(plan: "DmvPlan", rooms: Mapping[str, object]
                  ) -> list[tuple[str, Point]]:
    """Where each of :data:`NOTICE_LINES` stands, ``(key, point)``.

    Each is on the floor in front of the prop it belongs to, and every one
    keeps clear of the map's own use triggers -- a perk's, a wall buy's, the
    box's, the switch's, the ticket machine's -- because two use triggers in
    reach of one player show one prompt, and the one that loses might be a
    purchase.  ``tests/test_dmv.py`` measures that distance.
    """
    lot, entry, waiting = rooms["lot"], rooms["entry"], rooms["waiting"]
    eye, photo, brk = rooms["eye"], rooms["photo"], rooms["break"]
    rec, queue, office = rooms["records"], rooms["queue"], rooms["office"]
    e_in, w_in = entry.interior, waiting.interior
    face_x, _back_x, _y0, _y1 = counter_run(plan)
    front_x = w_in.maxs.x - 150.0
    last_y = (w_in.centre.y - (plan.chair_cols - 1) * plan.seat_pitch / 2.0
              + (plan.chair_cols - 1) * plan.seat_pitch)
    dead_end = queue_dead_end(plan)[-1]
    o_in = office.interior
    counter_north = o_in.maxs.y - plan.booth_depth
    spots: list[tuple[str, Point]] = [
        ("hot_dogs", Point(-2420.0, 430.0, lot.floor_z)),
        ("forms", Point(e_in.mins.x + 60.0, -140.0, entry.floor_z)),
        ("cooler", Point(-1500.0, e_in.maxs.y - 48.0, entry.floor_z)),
        ("suggestions", Point(w_in.mins.x + 50.0, 250.0, waiting.floor_z)),
        ("customer_846", Point(front_x + 34.0, last_y, waiting.floor_z)),
        ("now_serving", Point(face_x - 60.0, window_y(plan), waiting.floor_z)),
    ]
    spots += [
        ("eye_test", Point(-530.0, 610.0, eye.floor_z)),
        ("photo", Point(photo.interior.maxs.x - 60.0, photo.interior.maxs.y - 124.0,
                        photo.floor_z)),
        ("fridge", Point(brk.interior.maxs.x - 50.0, brk.interior.mins.y + 124.0,
                         brk.floor_z)),
        ("camp", Point(rec.interior.maxs.x - 134.0, 96.0, rec.floor_z)),
        ("queue_wait", Point(queue_route(plan)[0].x + 42.0, queue_route(plan)[0].y,
                             queue.floor_z)),
        ("queue_closed", Point(dead_end.x + 22.0, dead_end.y, queue.floor_z)),
        ("manager", Point(o_in.centre.x - 120.0, counter_north - 50.0, office.floor_z)),
    ]
    return spots


def lot_walk(plan: "DmvPlan", lot) -> tuple[float, float]:
    """The lot footway's ``(walk_top, walk_x0)``: its top face and west edge,
    the two numbers :func:`dmv_of_the_damned` derives for the frontage."""
    return lot.floor_z + plan.kerb_height, lot.interior.maxs.x - plan.walk_depth


def all_notices(plan: "DmvPlan", rooms: Mapping[str, object], *,
                walk_top: float | None = None, walk_x0: float | None = None
                ) -> tuple[dict[str, tuple[str, tuple[str, ...]]], list[tuple[str, Point]]]:
    """:data:`NOTICE_LINES` plus every dense-pass room module's ``NOTICES``,
    and where each stands: ``(lines, [(key, point), ...])``.  The footway
    numbers default to :func:`lot_walk`'s, so no caller can pass wrong ones
    by leaving them out."""
    from .dmv_rooms import dense_notices

    top, x0 = lot_walk(plan, rooms["lot"])
    walk_top = top if walk_top is None else walk_top
    walk_x0 = x0 if walk_x0 is None else walk_x0

    extra, extra_spots = dense_notices(plan, rooms, walk_top=walk_top, walk_x0=walk_x0)
    clash = set(extra) & set(NOTICE_LINES)
    if clash:
        raise ValueError(f"dense notice keys shadow NOTICE_LINES: {sorted(clash)}")
    return {**NOTICE_LINES, **extra}, _notice_spots(plan, rooms) + extra_spots


def _wire_notices(bp: Blueprint, plan: "DmvPlan", rooms: Mapping[str, object], *,
                  walk_top: float | None = None, walk_x0: float | None = None) -> None:
    """Ship every notice (:func:`all_notices`) and hang each on its spot."""
    lines, spots = all_notices(plan, rooms, walk_top=walk_top, walk_x0=walk_x0)
    assets: dict[str, tuple[str, tuple[str, ...]]] = {}
    for key, (prompt, replies) in lines.items():
        ref = f"NOTICE_{key.upper()}"
        assets[key] = (
            # Only this module's own notices: the room modules' prompts are
            # pinned word for word by their tests and theirs to change.
            bp.add_map_string(ref, _notice_prompt(prompt) if key in NOTICE_LINES else prompt,
                              kind="triggerstring"),
            tuple(bp.add_map_string(f"{ref}_{n}", line) for n, line in enumerate(replies)),
        )
    bp.add_custom_logic(use_notices(
        [(point, *assets[key]) for key, point in spots]
    ))


def _wire_quest(bp: Blueprint, plan: "DmvPlan", rooms: Mapping[str, object], *,
                walk_top: float) -> None:
    """The ending: four registrations, THE EXAMINER and the 20,000-point exit
    (:mod:`zmforge.recipes.dmv_quest`, built on :mod:`zmforge.script.quest`)."""
    from ..script.quest import install_quest
    from .dmv_quest import register_quest

    install_quest(bp, register_quest(plan, rooms, walk_top=walk_top))


def _notice_prompt(prompt: str) -> str:
    """A notice's prompt as shipped: its own words, plus the use key when
    they do not already name it -- "POSITION CLOSED" alone does not tell a
    player there is anything to press.  The words are the module's own;
    only the instruction is added after them."""
    if "{+activate}" in prompt:
        return prompt
    return f"{prompt} -- hold ^3[{{+activate}}]^7 to read"


def _wire_gags(bp: Blueprint, plan: "DmvPlan", rooms: Mapping[str, object]) -> None:
    """Ship :data:`GAG_LINES` and hang each on its trigger.

    The lines go through :mod:`zmforge.script.gags`, which says them centre
    screen (or in the feed, or as HUD text) rate-limited per player and per
    gag; see that module for every hook's stock source.  ``rooms`` is only
    checked: each ``room_<zone>`` line must name a room the map has, because
    a sign-in keyed to a zone that does not exist never fires and says so
    nowhere.
    """
    from ..script.gags import (
        box_reactions,
        gag_say,
        player_reactions,
        power_on_announcement,
    )

    zones = {"lot", "entry", "waiting", "windows", "eyeexam", "photo",
             "breakroom", "records", "queue", "office"}
    if len(rooms) != len(zones):
        raise ValueError(f"the gags sign in {len(zones)} rooms, not {len(rooms)}")
    said = {key: bp.add_map_string(f"GAG_{key.upper()}", text)
            for key, text in GAG_LINES.items()}

    bp.add_custom_logic(gag_say(gap=GAG_SAY_GAP))
    bp.add_custom_logic(player_reactions(
        downed=said["downed"],
        downed_feed=said["downed_feed"],
        bled_out_feed=said["bled_out_feed"],
        revived=said["revived"],
        revived_broke=said["revived_broke"],
        reviver=said["reviver"],
        fee=25,
        perks={
            vehicle_registration_perk(plan).specialty: said["perk_registration"],
            take_a_number_perk(plan).specialty: said["perk_ticket"],
        },
        pap=said["pap"],
        hops={"_express": (said["express"], said["express_feed"]),
              "_booth": (said["booth"], None)},
        idle=("waiting", GAG_IDLE_SECONDS, said["idle"]),
    ))
    bp.add_custom_logic(box_reactions(used=said["box"], moved=said["box_moved"]))
    # No round-end PA flavour and no room sign-in lines (P13, P17):
    # the PA voice left is the ticket window's calls.
    bp.add_custom_logic(power_on_announcement(said["power"]))


def dmv_of_the_damned(
    name: str,
    plan: DmvPlan = FIXTURE,
    *,
    seed: str | None = None,
    player_slots: int = STOCK_PLAYER_SLOTS,
    starting_points: int | None = STOCK_STARTING_POINTS,
    gobblegums: int | None = None,
) -> Blueprint:
    """A haunted Department of Motor Vehicles, and the queue for its
    pack-a-punch.

    ``starting_points`` is a testing aid, as in the other recipes: pass a
    number and every player starts with it, so a tester can walk the queue and
    open every door in one session.  It defaults to
    :data:`~zmforge.script.tricks.STOCK_STARTING_POINTS`, which is ``None`` and
    leaves the score alone.  The ticket machine and the 9,500-point stapler are
    jokes about paying for things, so a build with this on is a build where
    neither lands: turn it off before anybody plays it for real.
    """
    # What the menus call it; ``generate --title`` still overrides this.
    bp = Blueprint(name, seed=seed, title=MAP_TITLE)
    door = plan.doorway_width
    tall = plan.doorway_height

    # ==================================================================
    # The building
    # ==================================================================
    # Outside first.  The car park is a room with no roof, so its four walls
    # are the site boundary and the sky over it is the enclosure's -- which
    # is also what seals the map: there is no hole in the lot's shell but the
    # front door.
    lot = bp.add_room(
        plan.lot,
        wall=plan.wall,
        roofed=False,
        # Lit by the sun, not by fill lamps: 60 of them at full exposure on
        # top of daylight is what made the car park play blinding (Room.sunlit).
        # The lamps-back experiment settled it: the dark lot was a
        # stale bake, not the missing lamps, so the lot stays sunlit.
        sunlit=True,
        openings=[Aperture(Side.EAST, door, tall)],
        materials=SKINS["lot_room"],
        id="lot_room",
    )
    entry = bp.add_room(
        plan.entry,
        wall=plan.wall,
        openings=[
            Aperture(Side.WEST, door, tall),
            Aperture(Side.EAST, door, tall),
        ],
        materials=SKINS["entry_room"],
        id="entry_room",
    )
    # The break room is not centred on the waiting room, so the doorway
    # between them is slid along the wall until the two rooms' apertures are
    # the same hole: an opening is cut from the middle of the wall it is in,
    # and each of these rooms has its own middle.
    break_offset = _centre_x(plan.break_room) - _centre_x(plan.windows)
    photo_offset = _centre_x(plan.photo) - _centre_x(plan.waiting)
    # The counter hall's north doorway is slid west so it opens off the
    # **public** strip: the vision screening room is a room a customer is
    # sent to, so its door cannot be behind the counter.
    eye_offset = _centre_x(plan.eye_exam) - _centre_x(plan.windows)
    waiting = bp.add_room(
        plan.waiting,
        wall=plan.wall,
        openings=[
            Aperture(Side.WEST, door, tall),
            Aperture(Side.EAST, plan.lobby_opening, tall),
            Aperture(Side.SOUTH, door, tall, offset=photo_offset),
        ],
        materials=SKINS["waiting_room"],
        id="waiting_room",
    )
    windows = bp.add_room(
        plan.windows,
        wall=plan.wall,
        openings=[
            Aperture(Side.WEST, plan.lobby_opening, tall),
            Aperture(Side.EAST, door, tall),
            Aperture(Side.NORTH, door, tall, offset=eye_offset),
            Aperture(Side.NORTH, door, tall, offset=break_offset),
        ],
        materials=SKINS["windows_room"],
        id="windows_room",
    )
    eye_exam = bp.add_room(
        plan.eye_exam,
        wall=plan.wall,
        openings=[Aperture(Side.SOUTH, door, tall)],
        materials=SKINS["eye_exam_room"],
        id="eye_exam_room",
    )
    photo = bp.add_room(
        plan.photo,
        wall=plan.wall,
        openings=[Aperture(Side.NORTH, door, tall)],
        materials=SKINS["photo_room"],
        id="photo_room",
    )
    break_room = bp.add_room(
        plan.break_room,
        wall=plan.wall,
        openings=[Aperture(Side.SOUTH, door, tall)],
        materials=SKINS["break_room"],
        id="break_room",
    )
    records = bp.add_room(
        plan.records,
        wall=plan.wall,
        openings=[
            Aperture(Side.WEST, door, tall),
            Aperture(Side.EAST, door, tall),
        ],
        materials=SKINS["records_room"],
        id="records_room",
    )
    # The queue hall's two doorways are both offset.  The one in from the
    # records room is slid down to the middle lane, because a player who
    # arrives anywhere else arrives in the middle of a rail; the one out to
    # the back office is slid along the north wall to the far end of the last
    # lane, so the arena is the thing you reach after walking the line, and
    # it is clear of the machine standing in the corner beside it.
    queue_centre_y = (plan.queue.mins.y + plan.queue.maxs.y) / 2.0
    entry_y = _queue_entry_y(plan)
    office_door_x = _centre_x(plan.office)
    queue_centre_x = _centre_x(plan.queue)
    queue = bp.add_room(
        plan.queue,
        wall=plan.wall,
        openings=[
            Aperture(Side.WEST, door, tall, offset=entry_y - queue_centre_y),
            Aperture(Side.NORTH, door, tall, offset=office_door_x - queue_centre_x),
        ],
        materials=SKINS["queue_room"],
        id="queue_room",
    )
    office = bp.add_room(
        plan.office,
        wall=plan.wall,
        openings=[Aperture(Side.SOUTH, door, tall)],
        materials=SKINS["office_room"],
        id="office_room",
    )

    lot_zone = bp.add_zone("lot", lot, starting=True)
    entry_zone = bp.add_zone("entry", entry)
    waiting_zone = bp.add_zone("waiting", waiting)
    windows_zone = bp.add_zone("windows", windows)
    eye_zone = bp.add_zone("eyeexam", eye_exam)
    photo_zone = bp.add_zone("photo", photo)
    break_zone = bp.add_zone("breakroom", break_room)
    records_zone = bp.add_zone("records", records)
    queue_zone = bp.add_zone("queue", queue)
    office_zone = bp.add_zone("office", office)

    # ==================================================================
    # The car park: where the map starts, and the walk to the front door
    # ==================================================================
    lot_in = lot.interior
    walk_top, walk_x0 = lot_walk(plan, lot)
    # The footway across the whole frontage, six inches proud of the asphalt,
    # and the planted bed along the far boundary at the same height.  A kerb
    # is under STEP_UP, so both are walked onto rather than jumped onto and
    # neither is ground the flood cannot reach.
    bp.add_slab(
        Bounds.between((walk_x0, lot_in.mins.y, lot.floor_z),
                       (lot_in.maxs.x, lot_in.maxs.y, walk_top)),
        walk_top, plan.kerb_height,
        # Slab paving on top and a concrete kerb on the face you step up;
        # the faces against the boundary and the frontage are caulk.
        _faces(CAULK, top=_WALK, west=_KERB), id="lot_footway",
    )
    bed_x1 = lot_in.mins.x + plan.landscape_depth
    bp.add_slab(
        Bounds.between((lot_in.mins.x, lot_in.mins.y, lot.floor_z),
                       (bed_x1, lot_in.maxs.y, walk_top)),
        walk_top, plan.kerb_height,
        _faces(CAULK, top=_LAWN, east=_KERB), id="lot_planting_bed",
    )
    # The kerb ramp, and it is the landing rather than a ramp on the walk
    # alone: the covered walk and the two access aisles either side of it all
    # meet the kerb along the same line, so the ramp spans all three.  A
    # six-inch kerb is under STEP_UP and the engine does not need this; a
    # real accessible route does.
    ramp_half = plan.canopy_width / 2.0 + plan.access_aisle_width
    bp.add_wedge(
        Bounds.between((walk_x0 - 48.0, -ramp_half, lot.floor_z),
                       (walk_x0, ramp_half, walk_top)),
        Facing.EAST, _WALK, id="lot_kerb_ramp",
    )
    # Every bay line in the car park, drawn as a four-inch strip of paint one
    # unit proud of the asphalt.  The access aisles get three cross strips
    # each instead of the diagonal hatching a real one has, because a
    # diagonal is not a thing an axis-aligned brush can be.
    seen: set[tuple[float, float, float]] = set()
    marks = 0
    for kind, x0, x1, y0, y1 in parking_bays(plan):
        edges = [y0, y1]
        if kind == "aisle":
            edges += [y0 + (y1 - y0) * f for f in (0.25, 0.5, 0.75)]
        for y in edges:
            key = (round(x0, 1), round(x1, 1), round(y, 1))
            if key in seen:
                continue
            seen.add(key)
            bp.add_slab(
                Bounds.between(
                    (x0, y - plan.stripe_width / 2.0, lot.floor_z),
                    (x1, y + plan.stripe_width / 2.0,
                     lot.floor_z + plan.stripe_height)),
                lot.floor_z + plan.stripe_height, plan.stripe_height,
                # Paint on top; the one-unit edges are the asphalt's.
                _faces(_ASPHALT, top=_STRIPE, bottom=CAULK),
                id=f"lot_bay_line_{marks}",
            )
            marks += 1
    # The covered entry walk.  Its roof is 144 above the footway, which is
    # well over a jump, so it is declared unreachable rather than reported as
    # a slab nobody can stand on; the two posts are the same.
    canopy_y = plan.canopy_width / 2.0
    for index, y in enumerate((-canopy_y, canopy_y - 16.0)):
        bp.add_block(
            Bounds.between((walk_x0, y, walk_top),
                           (walk_x0 + 16.0, y + 16.0, walk_top + plan.canopy_height)),
            _faces(_BLACK, top=CAULK, bottom=CAULK),
            reachable=False, id=f"lot_canopy_post_{index}",
        )
    bp.add_slab(
        Bounds.between((walk_x0, -canopy_y, walk_top),
                       (lot_in.maxs.x, canopy_y, walk_top + plan.canopy_height + 16.0)),
        walk_top + plan.canopy_height + 16.0, 16.0,
        # A rubber roof, a panelled fascia round the three open edges and a
        # metal soffit under it; the edge against the brick is caulk.
        _faces(_FASCIA, top=_ROOFING, bottom=_STEEL, east=CAULK),
        walkable=False, reachable=False, id="lot_canopy",
    )
    bp.set_player_start(
        Point(walk_x0 - plan.stall_depth - plan.drive_aisle / 2.0, 0.0,
              lot.floor_z + 16.0),
        Facing.EAST,
        slots=player_slots,
    )
    # The starter sidearm is outside now, on the frontage beside the doors,
    # because the spawn is outside and a spawn with nothing to buy is a round
    # one spent running.  The buy origin is eight units inside the floor it
    # stands on -- the footway, not the asphalt -- which is what the spec
    # fixes and what W1 says so.
    bp.place_wall_weapon(
        "pistol_burst",
        Point(plan.lot.maxs.x - 18.0, -150.0, walk_top - 8.0),
        Facing.WEST,
        id="lot_wallbuy",
    )
    for index, (x, y) in enumerate((
        (lot_in.mins.x + 96.0, -420.0),
        (lot_in.mins.x + 96.0, 420.0),
        (lot_in.mins.x + 96.0, 0.0),
    )):
        bp.add_riser(lot_zone, Point(x, y, walk_top), Facing.EAST,
                     id=f"lot_riser_{index}")
    # What a branch's frontage has on it, out of models that exist: two
    # planters either side of the doors, a bench and a bin under the canopy,
    # bollards down the edge of the accessible route, and the plate by the
    # door that would carry the opening hours if this map cut art, which it
    # does not.  The cars are placed further down (``lot_cars``).
    frontage: list[tuple] = [
        ("p7_cai_planter_rectangle",
         Point(lot_in.maxs.x - 60.0, y,
               _rest_on("p7_cai_planter_rectangle", walk_top)),
         90.0, 1.0, True)
        # 270, not 190: at 190 the south planter stood 26 units in front of
        # the pistol_burst chalk at y -150 and no player fits in that gap
        # (Z55).  At 270 its near end is 38 past the buy's centre.
        for y in (-270.0, 270.0)
    ]
    frontage += [
        # Beside the walk, not across it: a bench on the centre line is a
        # bench between the player and the front door.
        ("p7_bench_modern_01",
         Point(walk_x0 + 30.0, -190.0,
               _rest_on("p7_bench_modern_01", walk_top)),
         90.0, 1.0, True),
        ("p7_trashcan_metal_modern_glass",
         Point(lot_in.maxs.x - 44.0, 96.0,
               _rest_on("p7_trashcan_metal_modern_glass", walk_top)),
         0.0, 1.0, True),
        _mounted("p7_signage_loading_zone_01",
                 Point(lot_in.maxs.x - 3.0, 90.0, walk_top + 104.0), Facing.WEST),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(lot_in.maxs.x - 3.0, -90.0, walk_top + 96.0), Facing.WEST),
    ]
    frontage += [
        ("p7_3arc_park_pylon",
         Point(walk_x0 + 8.0, y, _rest_on("p7_3arc_park_pylon", walk_top)),
         0.0, 1.0, True)
        for y in (-canopy_y - 40.0, canopy_y + 40.0)
    ]
    bp.place_props(frontage, id="lot_frontage")
    # The planted boundary: a hedge run, two trees and the boulder somebody's
    # landscaping budget bought instead of maintenance.  Solid, all of it, so
    # the strip is a boundary and not a shortcut -- and clear of the three
    # risers standing in it.
    planting: list[tuple] = []
    for index in range(7):
        y = -576.0 + index * 192.0
        if abs(y) < 120.0 or abs(abs(y) - 420.0) < 120.0:
            continue
        planting.append(
            ("p7_foliage_hedge_box_48_48_36",
             Point(lot_in.mins.x + 56.0, y,
                   _rest_on("p7_foliage_hedge_box_48_48_36", walk_top)),
             0.0, 1.0, True)
        )
    planting += [
        ("p7_foliage_tree_acacia_bush",
         Point(lot_in.mins.x + 170.0, y,
               _rest_on("p7_foliage_tree_acacia_bush", walk_top)),
         float(int(y) % 360), 1.0, True)
        for y in (-300.0, 300.0)
    ]
    planting.append(
        ("p7_rock_sing_park_06",
         Point(lot_in.mins.x + 168.0, 0.0,
               _rest_on("p7_rock_sing_park_06", walk_top)),
         25.0, 1.0, True)
    )
    bp.place_props(planting, id="lot_planting")
    # Asphalt dressing: the manhole in the drive aisle.  Not solid.  The
    # eight scraps of litter that used to lie across the bays went when the
    # cars came in: most of them were under a car, and the lot
    # was at the top of the 50-100 props-a-room band, so each car had to
    # cost a prop.
    aisle_x = walk_x0 - plan.stall_depth - plan.drive_aisle / 2.0
    tarmac: list[tuple] = [
        ("p7_street_manhole_cover_cairo_01",
         Point(aisle_x, -240.0,
               _rest_on("p7_street_manhole_cover_cairo_01", lot.floor_z)), 0.0),
    ]
    bp.place_props(tarmac, id="lot_litter")
    # The cars (:data:`LOT_CARS`): twelve of the twenty bays a car can use,
    # solid, head-in, none in the drive aisle the player starts in, on the
    # walk, in an access aisle or near a riser.
    bp.place_props(list(parked_cars(plan, lot.floor_z)), id="lot_cars")

    # ==================================================================
    # Entry lobby: the front doors, the ticket machine, the kiosk
    # ==================================================================
    entry_in = entry.interior
    for side in (Side.SOUTH, Side.NORTH):
        bp.add_window(
            entry_zone,
            entry,
            side,
            yard_depth=plan.yard_depth,
            id=f"entry_window_{side.name.lower()}",
        )
    # Boarded windows in the other rooms with a free outside wall (P7: with
    # boards only in the entry, zombies would come out of the floor
    # everywhere else and the waiting room and the store would have one
    # spawn apiece).  Each is on a stretch of wall nothing stands against,
    # and each yard clears its neighbours.  The three small rooms keep their
    # one riser: the eye test's two outside walls carry the chart and the
    # shotgun, and the photo booth's and break room's are lined with the
    # sitter's chairs, the cart, the fridge and the kitchenette; the back
    # office keeps its two risers, since every free stretch of its walls is
    # within 80 of Stamin-Up or the stapler.  Every board here is 80 or more
    # from every perk, buy and the box.  The records
    # store was "no windows" (PennDOT 4.2.1); its board is over a hole
    # something has made in it since.
    for zone, room, side, offset, name in (
        (waiting_zone, waiting, Side.NORTH, 150.0, "waiting"),
        (windows_zone, windows, Side.SOUTH, 225.0, "windows"),
        (records_zone, records, Side.NORTH, -40.0, "records"),
        (queue_zone, queue, Side.SOUTH, 250.0, "queue"),
    ):
        bp.add_window(zone, room, side, offset, yard_depth=plan.yard_depth,
                      id=f"{name}_window_{side.name.lower()}")
    bp.place_custom_perk(
        take_a_number_perk(plan),
        Point(entry_in.mins.x + 24.0, 120.0, entry.floor_z),
        Facing.EAST,
        id="perk_take_a_number",
    )
    # The self-service kiosk: permanently out of order, and out of order in
    # the deepest sense -- it is the palette's water cooler, the nearest thing
    # in it to a standing terminal, and there is no kiosk model to be had
    # without cutting one.  Scenery, and solid, so it is in the way like the
    # real thing.
    kiosk = "p7_water_cooler_digital_body"
    bp.place_props(
        [
            # In the middle of the lobby, a few steps in from the front door
            # and on the way to the waiting room, facing the door: the one
            # thing a player walks straight past is a machine in a corner.
            (kiosk, Point(*ticket_kiosk_xy(entry_in),
                          _rest_on(kiosk, entry.floor_z)),
             Facing.WEST.world_yaw, 1.0, True),
            _mounted("p7_zm_der_signage_no_smoking",
                     Point(entry_in.maxs.x - 3.0, 200.0, entry.floor_z + 96.0),
                     Facing.WEST),
            _mounted("p7_signage_caution_exit",
                     Point(entry_in.mins.x + 3.0, 210.0, entry.floor_z + 104.0),
                     Facing.EAST),
            # "an information and publications rack" is one of the five
            # things PennDOT's requirements say a waiting area has (4.1.5);
            # it stands where the starter sidearm used to, which is the other
            # side of the front door from the ticket machine.
            ("p7_shelf_metal_lab_01",
             Point(entry_in.mins.x + 24.0, -140.0,
                   _rest_on("p7_shelf_metal_lab_01", entry.floor_z)),
             90.0, 1.0, True),
        ],
        id="entry_props",
    )
    # The fittings a lobby grows on its own: the plant somebody's predecessor
    # brought in and nobody has watered since, and the bin under the sign.
    # Solid, both of them, because the point of a lobby plant is that it is in
    # the way.
    bp.place_props(
        [
            ("p7_3arc_lobby_plant",
             Point(entry_in.maxs.x - 56.0, -230.0,
                   _rest_on("p7_3arc_lobby_plant", entry.floor_z)),
             25.0, 1.0, True),
            ("p7_trashcan_metal_modern_glass",
             Point(entry_in.maxs.x - 44.0, 130.0,
                   _rest_on("p7_trashcan_metal_modern_glass", entry.floor_z)),
             0.0, 1.0, True),
        ],
        id="entry_fittings",
    )

    # ==================================================================
    # Waiting room: the chairs, the clocks, the paperwork
    # ==================================================================
    wait_in = waiting.interior
    bp.add_riser(
        waiting_zone,
        Point(wait_in.maxs.x - 48.0, wait_in.maxs.y - 48.0, waiting.floor_z),
        Facing.SOUTH,
        id="waiting_riser",
    )
    bp.place_perk(
        "quick_revive",
        Point(wait_in.mins.x + 64.0, wait_in.mins.y + 24.0, waiting.floor_z),
        Facing.NORTH,
        id="perk_quick_revive",
    )
    # Ten chairs, in two rows of five, all of them facing east: through the
    # lobby opening, down the public floor, at the counter run and the board
    # over it.  Ten is PennDOT's number -- "ten waiting chairs per camera
    # system" (photo licence centre co-location requirements 4.1.5) -- and
    # this branch has one camera, in the booth off the other side of this
    # room.  A row is five seats abreast across y because that is the axis
    # the counter is long in; the rows stack along x so the back row looks
    # over the front one.
    chair = "p7_chair_waiting_room_01_blue"
    chair_z = _rest_on(chair, waiting.floor_z)
    seating: list[tuple] = []
    front_x = wait_in.maxs.x - 150.0
    start_y = wait_in.centre.y - (plan.chair_cols - 1) * plan.seat_pitch / 2.0
    for row in range(plan.chair_rows):
        for seat in range(plan.chair_cols):
            seating.append(
                _seated(
                    chair,
                    Point(front_x - row * plan.row_pitch,
                          start_y + seat * plan.seat_pitch, chair_z),
                    Facing.EAST,
                )
            )
    bp.place_props(seating, id="waiting_chairs")
    # Four clocks on the east wall, hung at four heights, and the notice
    # board opposite.  One thing they do not do is disagree: the model has
    # one face with one time painted on it, and a map that cuts no art cannot
    # repaint it, so what the row actually says is that somebody hung four
    # identical clocks and none of them is the reason you are still here.
    # Wall-mounted and not solid: a clock is not an obstacle and bakes no
    # collmap.
    clocks: list[tuple] = []
    for index, y in enumerate((-300.0, -180.0, 180.0, 300.0)):
        clocks.append(
            _mounted(
                "p7_clock_metal_wall_01_base",
                Point(wait_in.maxs.x - 3.0, y, waiting.floor_z + 112.0 + index * 4.0),
                Facing.WEST,
            )
        )
    clocks.append(
        _mounted("p7_zm_der2_bulletin_board",
                 Point(wait_in.mins.x + 3.0, -240.0, waiting.floor_z + 96.0),
                 Facing.EAST)
    )
    bp.place_props(clocks, id="waiting_clocks")
    # Ticket stubs and forms, dropped where people gave up.  Not solid: a
    # sheet of paper the player cannot walk over is the joke told badly.
    litter: list[tuple] = []
    paper = ("p7_debris_newspaper_01", "p7_debris_trash_paper_02",
             "p7_office_paper_stack_sml", "p7_debris_newspaper_04")
    for index in range(12):
        model = paper[index % len(paper)]
        litter.append(
            (
                model,
                Point(wait_in.mins.x + 60.0 + (index * 61) % 160,
                      wait_in.mins.y + 60.0 + (index * 141) % 780,
                      _rest_on(model, waiting.floor_z)),
                float((index * 53) % 360),
            )
        )
    bp.place_props(litter, id="waiting_litter")
    # Two planters either side of the door to the service windows, a plant in
    # the far corner and a bin: municipal landscaping, which is a square tub
    # of something plastic placed where it narrows a doorway.  They stand
    # clear of the chair grid and of the litter scatter, which is what Z44
    # measures.
    planter = "p7_cai_planter_square"
    bp.place_props(
        [
            (planter,
             Point(wait_in.maxs.x - 40.0, y, _rest_on(planter, waiting.floor_z)),
             0.0, 1.0, True)
            for y in (-118.0, 118.0)
        ]
        + [
            ("p7_3arc_lobby_plant",
             Point(wait_in.mins.x + 56.0, wait_in.maxs.y - 56.0,
                   _rest_on("p7_3arc_lobby_plant", waiting.floor_z)),
             200.0, 1.0, True),
            ("p7_trashcan_metal_modern_glass",
             Point(wait_in.maxs.x - 44.0, -140.0,
                   _rest_on("p7_trashcan_metal_modern_glass", waiting.floor_z)),
             0.0, 1.0, True),
        ],
        id="waiting_fittings",
    )

    # ==================================================================
    # Service window row: the counter, the partition, the one window
    # ==================================================================
    win_in = windows.interior
    face_x, back_x, run_y0, run_y1 = counter_run(plan)
    counter_top = windows.floor_z + plan.counter_height
    ledge_x1 = face_x + plan.patron_ledge_depth
    screen_low = counter_top + plan.service_slot
    screen_high = plan.windows.maxs.z - plan.wall
    centres = bay_centres(plan)
    pitch = bay_pitch(plan)
    # One riser on the public floor and one behind the counter, because the
    # staff side is a place a player stands and a room with a spawner only on
    # the far side of a counter is a room with a safe half.
    bp.add_riser(
        windows_zone,
        Point(win_in.mins.x + 48.0, win_in.maxs.y - 48.0, windows.floor_z),
        Facing.SOUTH,
        id="windows_riser",
    )
    bp.add_riser(
        windows_zone,
        Point(win_in.maxs.x - 48.0, win_in.mins.y + 48.0, windows.floor_z),
        Facing.NORTH,
        id="windows_riser_staff",
    )
    # The patron ledge: the top of the counter, the side a customer leans on,
    # in three pieces because one of them is lower than the other two.
    #
    # 42 rather than the 36 ADA 904.4.1 caps a service counter at, because 36
    # is under the 39-unit jump and a counter a player can hop is not a
    # counter -- see DmvPlan.counter_height.  The lowered section is at
    # the south end of the run (bay 1) and is ``ada_section_length`` long, which *is* the code's
    # number: "a portion of the counter surface that is 36 inches (915 mm)
    # long minimum".
    ada_lo = centres[0] - plan.ada_section_length / 2.0
    ada_hi = centres[0] + plan.ada_section_length / 2.0
    for index, (y0, y1, top) in enumerate((
        (run_y0, ada_lo, counter_top),
        (ada_lo, ada_hi, windows.floor_z + plan.ada_section_height),
        (ada_hi, run_y1, counter_top),
    )):
        bp.add_block(
            Bounds.between((face_x, y0, windows.floor_z), (ledge_x1, y1, top)),
            # A laminate top on a panelled front: the public face is wood,
            # which is the side a customer stands at.
            _faces(_PANELLING, top=_DESK, bottom=CAULK),
            reachable=False,
            id="windows_counter" if index == 0 else f"windows_counter_{index}",
        )
    # The staff work surface behind it, lower and deeper: 28.5, which is the
    # measured one (UC Berkeley's counter design guidelines).  This one is
    # *not* declared unreachable -- it is under the jump, a member of staff
    # can get onto it from the staff floor, and saying otherwise would be
    # declaring away something the flood can reach.
    bp.add_block(
        Bounds.between(
            (ledge_x1, run_y0, windows.floor_z),
            (back_x, run_y1, windows.floor_z + plan.staff_surface_height),
        ),
        # The same laminate on the staff surface, on a steel carcass.
        _faces(_STEEL, top=_DESK, bottom=CAULK),
        id="windows_worktop",
    )
    # One service window; the rest of the run is a partition wall.  Eight
    # numbered bays with one open read as one long black window: repeated
    # units that do not read as separate units are noise, so the run has
    # only the one window the ticket mechanic needs.
    #
    # The partition stands 4 units proud of the counter's public face, from
    # the counter top (the ADA section's lower top where it is under it) to
    # the ceiling, so the run is a plain wall with a counter in front of it.
    # The window bay keeps the old construction: a glass screen from
    # ``screen_low`` up, the open speak-through slot under it, a frame
    # (mullion) at each side, and a lamp on the clerk's side so the one
    # opening in the wall is the one lit thing in it.
    win_y0, win_y1 = window_opening(plan)
    open_y = window_y(plan)
    tops = ((run_y0, ada_lo, counter_top),
            (ada_lo, ada_hi, windows.floor_z + plan.ada_section_height),
            (ada_hi, run_y1, counter_top))
    for side, (y0, y1) in enumerate(((run_y0, win_y0 - plan.mullion_width),
                                     (win_y1 + plan.mullion_width, run_y1))):
        for piece, (c0, c1, low) in enumerate(tops):
            lo, hi = max(y0, c0), min(y1, c1)
            if hi - lo < 1.0:
                continue
            bp.add_block(
                Bounds.between((face_x - 4.0, lo, low), (ledge_x1, hi, screen_high)),
                # Plaster to the hall like the room's walls, with the
                # panelling's wood on the staff side.
                _faces(_PLASTER, east=_PANELLING, top=CAULK),
                reachable=False,
                id=f"windows_partition_{side}_{piece}",
            )
    bp.add_block(
        Bounds.between((face_x, win_y0, screen_low), (ledge_x1, win_y1, screen_high)),
        # The screen is glass: dark and opaque, the thing a clerk sits behind.
        _faces(_GLASS, top=CAULK),
        reachable=False,
        id="windows_screen",
    )
    for side, y in enumerate((win_y0 - plan.mullion_width, win_y1)):
        bp.add_block(
            Bounds.between((face_x - 6.0, y, windows.floor_z),
                           (ledge_x1, y + plan.mullion_width, screen_high)),
            # The frame the glass is held in, proud of the partition.
            _faces(_FRAME, top=CAULK, bottom=CAULK),
            reachable=False,
            id=f"windows_mullion_{side}",
        )
    bp.place_light(
        Point((ledge_x1 + back_x) / 2.0 + 24.0, open_y, screen_low + 24.0),
        colour=(1.0, 0.93, 0.8),
        radius=200.0,
        zone_name="windows",
        shadows=False,
        id="windows_clerk_light",
    )
    # The NOW SERVING board, on the strip of wall the open bay leaves above
    # the counter.  It is a board and not a screen, and it carries no number:
    # a usermap that cuts no art of its own cannot draw one, and inventing a
    # model that says "47" would be inventing an asset.  The number gag is
    # told by the machine in the entry hall instead -- you take one, and
    # nothing in the building ever calls it.
    #
    # The one screen model in the palette is not usable here:
    # ``p7_consumer_grade_monitor_medium``'s measured box sits 103 to 165
    # units away from its own origin, so placing it by its origin puts the
    # art in the next room -- which is what Z44 reported when this row was
    # first written (the prop came out at -443,-520 for an origin of
    # -400,-356).
    bp.place_props(
        [
            # The NOW SERVING board, on the screen over the one open bay,
            # looking west down the public floor at the chairs -- which is
            # the only reason the chairs face east.
            # On the screen's own face (face_x), between two mullions: at
            # face_x - 9 it hung 7 units off the mullions and 9 off the
            # screen (Z60 mount).
            _mounted("p7_zm_der2_bulletin_board",
                     Point(face_x, open_y, screen_low + 46.0),
                     Facing.WEST),
            # The sign at the gate, on the wall over the one way round the
            # counter.  The words are the palette's, and they are the right
            # words: this is the gate PennDOT's 4.1.3 requires.
            _mounted("p7_zm_der_signage_employees_only",
                     Point((face_x + back_x) / 2.0, win_in.maxs.y - 3.0,
                           windows.floor_z + 104.0),
                     Facing.SOUTH),
            # BACK IN 5 MINUTES, in the only words there are: a plate on
            # the partition at each end of the run.
            # On the partition's face, 4 units proud of the counter: at
            # face_x - 9 both plates floated 5 units off it (Z60 mount).
            _mounted("p7_signage_loading_zone_01",
                     Point(face_x - 4.0, centres[0], windows.floor_z + 60.0),
                     Facing.WEST),
            _mounted("p7_signage_caution_exit",
                     Point(face_x - 4.0, centres[-1], windows.floor_z + 62.0),
                     Facing.WEST),
        ]
        + [
            # The staff side of the counter, which is what makes it a
            # counter: paperwork left on the work surface behind the ledge.
            (model,
             Point((ledge_x1 + back_x) / 2.0, centres[index],
                   _rest_on(model, windows.floor_z + plan.staff_surface_height)),
             float(index * 37 % 360))
            for index, model in ((1, "p7_office_paper_folder_blue"),
                                 (5, "p7_books_office_row_01"),
                                 (6, "p7_office_paper_stack_sml"))
        ],
        id="windows_props",
    )
    # The public floor's own fittings: the bin for the form you filled in
    # wrong, by the counter where you find out, and the plant in the corner.
    bp.place_props(
        [
            ("p7_trashcan_metal_modern_glass",
             Point(face_x - 44.0, win_in.mins.y + 90.0,
                   _rest_on("p7_trashcan_metal_modern_glass", windows.floor_z)),
             0.0, 1.0, True),
            ("p7_3arc_lobby_plant",
             # South of the registration car, which has its old corner, and
             # clear of it: at maxs.y - 262 the pot stood 30 units inside the
             # car's south clip.
             Point(win_in.mins.x + 30.0, win_in.maxs.y - 300.0,
                   _rest_on("p7_3arc_lobby_plant", windows.floor_z)),
             110.0, 1.0, True),
        ],
        id="windows_fittings",
    )
    # Behind the counter: the employee workstations the counter is "located
    # directly in front of" (PennDOT 4.1.4), one per pair of windows, facing
    # the run; the supervisor's desk at the north end by the gate; and the
    # file cabinets by the door into the secure store.
    staff_x = back_x + 66.0
    back_of_house: list[tuple] = []
    for index in (0, 2, 4, 6):
        back_of_house.append(
            ("p7_desk_metal_old_01_body",
             Point(staff_x, centres[index] + pitch / 2.0,
                   _rest_on("p7_desk_metal_old_01_body", windows.floor_z)),
             Facing.WEST.world_yaw, 1.0, True)
        )
        back_of_house.append(
            _seated("p7_chair_lab_01",
                    Point(staff_x + 58.0, centres[index] + pitch / 2.0,
                          _rest_on("p7_chair_lab_01", windows.floor_z)),
                    Facing.WEST)
        )
    for index, y in enumerate((-210.0, 210.0)):
        back_of_house.append(
            # Run along the wall, back flush to it (Z54): the cabinet's
            # doors are on its own -y, so looking west is yaw 270.
            _floor("p7_zm_der_cabinet_lab_bottom", win_in.maxs.x - 16.5, y,
                   windows.floor_z, (Facing.WEST.world_yaw + 90.0) % 360.0)
        )
    back_of_house.append(
        ("p7_trashcan_metal_modern_glass",
         Point(staff_x + 90.0, run_y1 - 40.0,
               _rest_on("p7_trashcan_metal_modern_glass", windows.floor_z)),
         0.0, 1.0, True)
    )
    bp.place_props(back_of_house, id="windows_back_of_house")
    # Both machines stand on the **public** floor, one at each end of the
    # run, because both of them are things a customer pays for.  Juggernog's
    # back is to the south wall and the registration desk's to the north,
    # clear of the door into the vision screening room.
    bp.place_perk(
        "juggernog",
        Point(win_in.mins.x + 96.0, win_in.mins.y + 24.0, windows.floor_z),
        Facing.NORTH,
        id="perk_juggernog",
    )
    # CARRY PERMIT (EXPIRED): the buy is on the partition over the counter,
    # one bay short of the service window.
    bp.place_wall_weapon(
        "smg_standard",
        Point(face_x - 6.0, bay_centres(plan)[plan.wallbuy_bay - 1], windows.floor_z - 8.0),
        Facing.WEST,
        id="windows_wallbuy",
    )
    # The registration desk is a car: parked along the west wall, facing
    # into the hall (its side is the front), with a clip over the whole car
    # because the framework's own clip is vending-machine sized.
    car_at = Point(win_in.mins.x + 40.0, win_in.maxs.y - 170.0, windows.floor_z)
    bp.declare_asset("xmodel", REGISTRATION_CAR)
    (c0, c1) = collision_box(REGISTRATION_CAR)
    # Facing east is yaw 90 on the perk family (front south at yaw 0), so
    # the car's own x runs north and its own y runs west.
    # The framework also spawns its own clip in the middle at run time (no
    # check sees it); these two cover the bonnet and the boot beyond it, and
    # the third, below, covers the middle short of the approach in front (Z9).
    for end, (y0, y1) in enumerate(((car_at.y + c0[0], car_at.y - 28.0),
                                    (car_at.y + 28.0, car_at.y + c1[0]))):
        bp.add_block(
            Bounds.between((car_at.x - c1[1], y0, windows.floor_z),
                           (car_at.x - c0[1], y1, windows.floor_z + c1[2])),
            CLIP,
            reachable=False,
            id=f"perk_registration_car_clip_{end}",
            note="registration car clip",
        )
    # The middle, from the back of the car to the line the Z9 approach box
    # starts at (MACHINE_BODY_DEPTH in front of the origin).  Without it the
    # checks see a 56-wide, 69-deep slot between the two brushes above: the
    # framework's clip fills it at run time, but nothing that runs here sees
    # that clip, so the slot read as floor and N5 warned that it was a pinch.
    # It stops short of the approach box (Z9 errors on a solid there) and
    # leaves a 24-unit hole round the origin (Z9 also errors on a machine
    # origin inside a solid).  What is left -- 10.5 units of the car's side
    # and the 24-wide hole -- is narrower than the 31 a navmesh needs (N2),
    # so it is not a route.
    from ..verify.model import MACHINE_BODY_DEPTH

    hole = 12.0
    back_x, front_x = car_at.x - c1[1], car_at.x + MACHINE_BODY_DEPTH
    for name, (x0, y0, x1, y1) in (
        ("south", (back_x, car_at.y - 28.0, front_x, car_at.y - hole)),
        ("north", (back_x, car_at.y + hole, front_x, car_at.y + 28.0)),
        ("back", (back_x, car_at.y - hole, car_at.x - hole, car_at.y + hole)),
    ):
        bp.add_block(
            Bounds.between((x0, y0, windows.floor_z),
                           (x1, y1, windows.floor_z + c1[2])),
            CLIP,
            reachable=False,
            id=f"perk_registration_car_clip_middle_{name}",
            note="registration car clip",
        )
    bp.place_custom_perk(
        vehicle_registration_perk(plan),
        car_at,
        Facing.EAST,
        id="perk_vehicle_registration",
    )

    # ==================================================================
    # Eye exam: the chart, and the line at the bottom of it
    # ==================================================================
    eye_in = eye_exam.interior
    bp.add_riser(
        eye_zone,
        Point(eye_in.mins.x + 48.0, eye_in.maxs.y - 48.0, eye_exam.floor_z),
        Facing.SOUTH,
        id="eye_riser",
    )
    # The chart: a white board with real letters, drawn in brushes
    # (:mod:`zmforge.recipes.dmv_rooms.eye` owns the layout, and the Vision
    # Test's targets are read off it).  Detail brushes: solid to bullets, no
    # BSP splits.  Board and letters look south, caulk against the wall.
    # **Nobody has seen this in game.**
    from .dmv_rooms.eye import chart_board, chart_letters

    ink = Material("t7_plastic_rubber_trim", 16.0)
    board = Material("t7_plastic_molding_trim_white", 64.0)
    bp.add_block(
        chart_board(eye_in, eye_exam.floor_z),
        _faces(CAULK, south=board, top=board, bottom=board, east=board, west=board),
        contents=("detail",),
        reachable=False,
        id="eye_chart",
        note="eye chart board",
    )
    for letter in chart_letters(eye_in, eye_exam.floor_z):
        for index, box in enumerate(letter.boxes):
            bp.add_block(
                box,
                # Ink on the face only: the edges are 0.75 deep, and 57
                # boxes inked on five sides made rubber trim a quarter of
                # the map's faces (the surface-mix test caught it).
                _faces(CAULK, south=ink),
                contents=("detail",),
                reachable=False,
                id=f"eye_chart_{letter.row}_{letter.col}_{letter.char.lower()}_{index}",
                note="eye chart letter",
            )
    # The chair you are told to sit in, looking at the chart, and the corner
    # plant every examination room has.  The chair is clear of the doorway:
    # a seat in the door is the one piece of dressing that costs a player a
    # life.
    bp.place_props(
        [
            _seated("p7_chair_lab_01",
                    Point(eye_in.centre.x - 80.0, eye_in.mins.y + 64.0,
                          _rest_on("p7_chair_lab_01", eye_exam.floor_z)),
                    Facing.NORTH),
            ("p7_3arc_lobby_plant",
             Point(eye_in.mins.x + 56.0, eye_in.maxs.y - 56.0,
                   _rest_on("p7_3arc_lobby_plant", eye_exam.floor_z)),
             340.0, 1.0, True),
        ],
        id="eye_fittings",
    )
    bp.place_perk(
        "deadshot",
        Point(eye_in.maxs.x - 24.0, eye_in.centre.y, eye_exam.floor_z),
        Facing.WEST,
        id="perk_deadshot",
    )
    bp.place_wall_weapon(
        "shotgun_pump",
        Point(plan.eye_exam.mins.x + 18.0, eye_in.centre.y, eye_exam.floor_z - 8.0),
        Facing.EAST,
        id="eye_wallbuy",
    )

    # ==================================================================
    # Photo booth: the flash, and which way you come out
    # ==================================================================
    photo_in = photo.interior
    bp.add_riser(
        photo_zone,
        Point(photo_in.centre.x, photo_in.mins.y + 40.0, photo.floor_z),
        Facing.NORTH,
        id="photo_riser",
    )
    booth = Point(photo_in.centre.x, photo_in.mins.y + 72.0, photo.floor_z)
    bp.place_props(
        [
            _seated("p7_chair_lab_01",
                    Point(photo_in.mins.x + 60.0, photo_in.maxs.y - 72.0,
                          _rest_on("p7_chair_lab_01", photo.floor_z)),
                    Facing.EAST),
            _mounted("p7_signage_caution_biohazard_01",
                     Point(photo_in.mins.x + 3.0, photo_in.centre.y, photo.floor_z + 100.0),
                     Facing.EAST),
            _mounted("p7_light_fixture_led_wall_01",
                     Point(photo_in.maxs.x - 3.0, photo_in.centre.y, photo.floor_z + 140.0),
                     Facing.WEST),
        ],
        id="photo_props",
    )
    # Two sample photographs on the wall you face on the way in, which is the
    # only thing the booth can show you about what it is going to do: the
    # frame model carries whatever art it carries and this map cuts none, so
    # what they actually say is that the DMV hung two identical pictures.
    bp.place_props(
        [
            _mounted("p7_picture_frame_modern_01",
                     Point(photo_in.centre.x + offset, photo_in.maxs.y - 3.0,
                           photo.floor_z + 100.0),
                     Facing.SOUTH)
            for offset in (-110.0, 110.0)
        ],
        id="photo_frames",
    )

    # ==================================================================
    # Break room: the donuts, and the breaker
    # ==================================================================
    break_in = break_room.interior
    bp.add_riser(
        break_zone,
        Point(break_in.centre.x, break_in.mins.y + 40.0, break_room.floor_z),
        Facing.NORTH,
        id="break_riser",
    )
    bp.place_power_switch(
        Point(break_in.centre.x, break_in.maxs.y - 24.0, break_room.floor_z + 8.0),
        Facing.SOUTH,
        id="break_power",
    )
    table = "p7_cai_work_table_metal_03_white"
    # 68 in from the west wall, not 80: the switch's approach lane (x -302..-198,
    # y 556..652; zmforge.blueprint.lanes) took the table and the
    # cake on it out of the room.
    # dmv_rooms/break_room.py places the table 68.0 in as well; keep the two equal.
    table_at = Point(break_in.mins.x + 68.0, break_in.centre.y, _rest_on(table, break_room.floor_z))
    table_top = _top_of(table, break_room.floor_z)
    bp.place_props(
        [
            (table, table_at, 0.0, 1.0, True),
            # The table is 21 x 81 in plan (its measured box), so everything
            # on it stays inside that: a mug 30 units off the side of it
            # hangs in the air, which is what Z44 reported the first time
            # this room was written.
            # Solid, because the kit's own table says a donut is solid and a
            # kit prop placed any other way writes ``no_collmap 1`` over a
            # model this project builds a collmap for -- which is the Z21
            # error this room shipped the first time it was written.
            ("zmf_prop_donut",
             Point(table_at.x, table_at.y - 26.0, _rest_on("zmf_prop_donut", table_top)),
             30.0, 1.0, True),
            ("zmf_prop_donut",
             Point(table_at.x + 1.0, table_at.y - 11.0, _rest_on("zmf_prop_donut", table_top)),
             200.0, 1.0, True),
            ("p7_coffee_maker_digital_pot",
             Point(table_at.x, table_at.y + 28.0,
                   _rest_on("p7_coffee_maker_digital_pot", table_top)), 0.0),
            ("p7_cup_coffee_mug",
             Point(table_at.x - 4.0, table_at.y + 12.0,
                   _rest_on("p7_cup_coffee_mug", table_top)), 0.0),
            ("p7_water_cooler_digital_body",
             Point(break_in.maxs.x - 44.0, break_in.mins.y + 60.0,
                   _rest_on("p7_water_cooler_digital_body", break_room.floor_z)),
             180.0, 1.0, True),
            ("p7_trashcan_metal_modern_glass",
             Point(break_in.maxs.x - 44.0, break_in.maxs.y - 80.0,
                   _rest_on("p7_trashcan_metal_modern_glass", break_room.floor_z)),
             0.0, 1.0, True),
        ],
        id="break_props",
    )
    # Two chairs at the table, and the notices nobody reads over it.
    bp.place_props(
        [
            _seated("p7_chair_lab_01",
                    Point(table_at.x + dx, table_at.y + dy,
                          _rest_on("p7_chair_lab_01", break_room.floor_z)),
                    facing)
            # 40 apart from the table's centre line, not 26: at 26 the first
            # chair stood on the written-test form at (-272, 536) and no floor
            # within reach of it was walkable (Z55).  The north
            # chair sits on the west side: east of the table it stood in the
            # power switch's approach lane and was taken out.
            for dx, dy, facing in ((44.0, -40.0, Facing.WEST), (-40.0, 40.0, Facing.EAST))
        ]
        + [
            _mounted("p7_zm_der2_bulletin_board",
                     Point(break_in.mins.x + 3.0, break_in.centre.y,
                           break_room.floor_z + 72.0),
                     Facing.EAST),
        ],
        id="break_seating",
    )

    # ==================================================================
    # Records: the archive, Speed Cola, and the box
    # ==================================================================
    rec_in = records.interior
    bp.add_riser(
        records_zone,
        Point(rec_in.centre.x, rec_in.maxs.y - 48.0, records.floor_z),
        Facing.SOUTH,
        id="records_riser",
    )
    bp.place_perk(
        "speed_cola",
        Point(rec_in.centre.x + 120.0, rec_in.maxs.y - 24.0, records.floor_z),
        Facing.SOUTH,
        id="perk_speed_cola",
    )
    bp.place_mystery_box(
        Point(rec_in.centre.x + 40.0, rec_in.mins.y + 24.0, records.floor_z),
        Facing.NORTH,
        id="records_box",
    )
    # Cabinets and shelves down both long walls, and the paper that came out
    # of them.  Solid, so the archive is an archive rather than a mural, and
    # clear of the doors and of the two machines: the approach to each of
    # those is what Z48 floods.
    archive: list[tuple] = []
    # Three cabinets each side of the west door and two shelving units each
    # side of the east one, every one of them clear of the door's approach
    # (Z53): a cabinet ten units into the west doorway blocks the way
    # through to Speed Cola.
    for y in (-326.0, -218.0, -110.0, 110.0, 218.0, 326.0):
        archive.append(
            # One run along the west wall, back flush to it (Z54), doors
            # (the model's -y) looking east; 108 long each, so the six meet
            # end to end either side of the doorway.
            _floor("p7_zm_der_cabinet_lab_bottom", rec_in.mins.x + 16.5, y,
                   records.floor_z, (Facing.EAST.world_yaw + 90.0) % 360.0)
        )
    # The shelves run along the east wall too (Z54); 113 long, so two a
    # side, clear of the doorway and of the filing cabinets at the ends.
    for y in (-230.0, -115.0, 115.0, 230.0):
        archive.append(
            _floor("p7_shelf_metal_lab_01", rec_in.maxs.x - 17.0, y,
                   records.floor_z, 90.0)
        )
    # Boxes and paper in two drifts, north and south of the walk from one
    # door to the other, which stays open down the middle of the room.
    for index in range(12):
        model = ("p7_container_cardboard_box_01", "p7_office_paper_stack_sml",
                 "p7_book_office_binder_open")[index % 3]
        side = 1.0 if index % 2 else -1.0
        archive.append(
            (model,
             Point(rec_in.mins.x + 110.0 + (index * 37) % 170,
                   side * (120.0 + (index * 53) % 130),
                   _rest_on(model, records.floor_z)),
             float((index * 71) % 360), 1.0, model == "p7_container_cardboard_box_01")
        )
    bp.place_props(archive, id="records_archive")

    # ==================================================================
    # The queue, and the pack-a-punch at the end of it
    # ==================================================================
    queue_in = queue.interior
    lanes = _lanes(plan)
    for rail_id, x0, x1, y0, y1 in _rails(plan):
        bp.add_block(
            Bounds.between((x0, y0, queue.floor_z), (x1, y1, queue.floor_z + plan.rail_height)),
            # Clip, not iron (bare poles do not read as
            # waiting lines).  What a player
            # sees is stanchion posts and belts along the rail's middle
            # (:mod:`zmforge.recipes.dmv_rooms.queue`, ``dense_queue_posts``
            # and ``queue_belt_*``); what stops them is the box, the same
            # box the solid iron rail was, so every route check measures the
            # same switchback.  ``clip`` stops players and AI, not bullets.
            CLIP,
            # The line is 48 units tall against a 39-unit jump: the top of a
            # rail is not standing room, and saying so is what keeps Z46 and
            # Z48 reporting a decision rather than a defect.
            reachable=False,
            id=rail_id,
            note="queue rail clip",
        )
    # Two spawners: one in the dead-end branch and one at the far end, so the
    # walk is not a safe corridor in either direction.
    bp.add_riser(
        queue_zone,
        Point(queue_in.mins.x + 56.0, (lanes[0][0] + lanes[0][1]) / 2.0, queue.floor_z),
        Facing.EAST,
        id="queue_riser_dead_end",
    )
    bp.add_riser(
        queue_zone,
        Point(queue_in.mins.x + 56.0, (lanes[4][0] + lanes[4][1]) / 2.0, queue.floor_z),
        Facing.EAST,
        id="queue_riser_last_lane",
    )
    # The machine, its back to the east wall at the end of the last lane.
    # ``facing`` is the heading its front points at, not the wall it stands
    # against: authored perpendicular to that wall it stands broadside with
    # part of itself inside it, which is what Z9 reports.
    bp.place_pack_a_punch(
        Point(queue_in.maxs.x - 24.0, (lanes[4][0] + lanes[4][1]) / 2.0, queue.floor_z + 4.0),
        Facing.WEST,
        id="queue_pap",
    )
    bp.place_props(
        [
            _mounted("p7_signage_loading_zone_01",
                     Point(queue_in.mins.x + 3.0, (lanes[2][0] + lanes[2][1]) / 2.0,
                           queue.floor_z + 104.0), Facing.EAST),
            _mounted("p7_zm_der_signage_employees_only",
                     Point(queue_in.mins.x + 3.0, (lanes[0][0] + lanes[0][1]) / 2.0,
                           queue.floor_z + 104.0), Facing.EAST),
            ("p7_debris_newspaper_04",
             Point(queue_in.mins.x + 120.0, (lanes[0][0] + lanes[0][1]) / 2.0,
                   _rest_on("p7_debris_newspaper_04", queue.floor_z)), 40.0),
            ("p7_debris_trash_paper_02",
             Point(queue_in.mins.x + 220.0, (lanes[0][0] + lanes[0][1]) / 2.0 + 30.0,
                   _rest_on("p7_debris_trash_paper_02", queue.floor_z)), 110.0),
        ],
        id="queue_props",
    )

    # ==================================================================
    # Back office: the operator's window, and the arena in front of it
    # ==================================================================
    off_in = office.interior
    counter_north = off_in.maxs.y - plan.booth_depth
    counter_south = counter_north - 16.0
    gap_x = off_in.maxs.x - plan.booth_way_in
    bp.add_block(
        Bounds.between(
            (off_in.mins.x, counter_south, office.floor_z),
            (gap_x, counter_north, office.floor_z + plan.counter_height),
        ),
        _faces(_PANELLING, top=_DESK, bottom=CAULK),
        reachable=False,
        id="office_counter",
    )
    # Above the counter, the shutter and its transom, up to the ceiling: the
    # slot between the two is the operator's window, and ``booth_way_in`` at
    # the east end is the way in behind it -- without which the booth is floor
    # nobody can reach.
    bp.add_block(
        Bounds.between(
            (off_in.mins.x, counter_south,
             office.floor_z + plan.counter_height + plan.service_slot),
            (gap_x, counter_north, plan.office.maxs.z - plan.wall),
        ),
        # Glazed like the counter hall's screens: the operator is behind
        # glass too.
        _faces(_GLASS, top=CAULK),
        id="office_transom",
    )
    bp.place_perk(
        "stamin_up",
        Point(off_in.mins.x + 24.0, off_in.mins.y + 200.0, office.floor_z),
        Facing.EAST,
        id="perk_stamin_up",
    )
    bp.place_wall_weapon(
        "bowie",
        Point(plan.office.maxs.x - 18.0, off_in.mins.y + 200.0, office.floor_z - 8.0),
        Facing.WEST,
        price=plan.stapler_price,
        id="office_wallbuy",
    )
    for index, x in enumerate((off_in.mins.x + 56.0, off_in.maxs.x - 56.0)):
        bp.add_riser(
            office_zone,
            Point(x, off_in.mins.y + 48.0, office.floor_z),
            Facing.NORTH,
            id=f"office_riser_{index}",
        )
    # Two lamps in the booth itself, which is the one part of this room
    # ``light_rooms`` cannot fill: its grid keeps a lamp 40 units clear of
    # solids and the transom runs the width of the room, so the two cells
    # the counter line crosses come out dark and Z11 says so.  Lighting them
    # from behind the glass is also the right answer for the gag: the
    # operator's window is the only lit one in the building.
    booth_light_z = plan.office.maxs.z - plan.wall - 40.0
    booth_light_y = (counter_north + off_in.maxs.y) / 2.0
    for index, x in enumerate((off_in.mins.x + 96.0, off_in.centre.x)):
        bp.place_light(
            Point(x, booth_light_y, booth_light_z),
            zone_name="office",
            id=f"office_booth_light_{index}",
        )

    desk = "p7_desk_metal_old_01_body"
    booth_y = counter_north + 40.0
    bp.place_props(
        [
            (desk, Point(off_in.centre.x - 120.0, booth_y, _rest_on(desk, office.floor_z)),
             Facing.SOUTH.world_yaw, 1.0, True),
            _seated("p7_chair_lab_01",
                    Point(off_in.centre.x - 120.0, booth_y + 40.0,
                          _rest_on("p7_chair_lab_01", office.floor_z)),
                    Facing.SOUTH),
            # Along the booth's back wall, flush to it (Z54).
            _floor("p7_shelf_industrial_vintage_96", off_in.mins.x + 52.0,
                   off_in.maxs.y - 18.0, office.floor_z, 0.0),
            # On the counter's own face, over the shutter slot, looking out
            # into the arena: the sign is the operator's whole personality.
            _mounted("p7_zm_der_signage_employees_only",
                     Point(off_in.centre.x + 60.0, counter_south - 3.0,
                           office.floor_z + 104.0),
                     Facing.SOUTH),
            ("p7_office_paper_stack_sml",
             Point(off_in.centre.x - 60.0, counter_south + 8.0,
                   _rest_on("p7_office_paper_stack_sml",
                            office.floor_z + plan.counter_height)), 15.0),
            _mounted("p7_clock_metal_wall_01_base",
                     Point(off_in.mins.x + 3.0, off_in.centre.y, office.floor_z + 120.0),
                     Facing.EAST),
        ],
        id="office_props",
    )
    # The rest of a back office, pushed back against the walls so the arena
    # stays open: a run of filing cabinets on the west wall with the notice
    # board over them, and the plant in the far corner.
    bp.place_props(
        [
            _floor("p7_zm_der_cabinet_lab_bottom", off_in.mins.x + 16.5, y,
                   office.floor_z, (Facing.EAST.world_yaw + 90.0) % 360.0)
            for y in (off_in.mins.y + 370.0, off_in.mins.y + 480.0)
        ]
        + [
            _mounted("p7_zm_der2_bulletin_board",
                     Point(off_in.mins.x + 3.0, off_in.mins.y + 425.0,
                           office.floor_z + 80.0),
                     Facing.EAST),
            ("p7_3arc_lobby_plant",
             Point(off_in.mins.x + 40.0, off_in.mins.y + 40.0,
                   _rest_on("p7_3arc_lobby_plant", office.floor_z)),
             70.0, 1.0, True),
        ],
        id="office_filing",
    )

    # ==================================================================
    # The doors
    # ==================================================================
    # The front door, which is the first one: the map starts on the asphalt.
    bp.add_door((lot_zone, entry_zone), entry.opening(0),
                price=plan.price("lot_entry"), id="door_lot_entry")
    bp.add_door((entry_zone, waiting_zone), waiting.opening(0),
                price=plan.price("entry_waiting"), id="door_entry_waiting")
    bp.add_door((waiting_zone, windows_zone), windows.opening(0),
                price=plan.price("waiting_windows"), id="door_waiting_windows")
    bp.add_door((waiting_zone, photo_zone), photo.opening(0),
                price=plan.price("waiting_photo"), id="door_waiting_photo")
    # The staff break room, which is reached from behind the counter.
    bp.add_door((windows_zone, break_zone), break_room.opening(0),
                price=plan.price("windows_break"), id="door_windows_break")
    bp.add_door((windows_zone, eye_zone), eye_exam.opening(0),
                price=plan.price("windows_eye_exam"), id="door_windows_eye_exam")
    bp.add_door((windows_zone, records_zone), records.opening(0),
                price=plan.price("windows_records"), id="door_windows_records")
    bp.add_door((records_zone, queue_zone), queue.opening(0),
                price=plan.price("records_queue"), id="door_records_queue")
    office_door = bp.add_door((queue_zone, office_zone), office.opening(0),
                              price=plan.price("queue_office"), id="door_queue_office")

    # ==================================================================
    # The mechanics
    # ==================================================================
    # Six machines and a stock ceiling of four: the ceiling goes, which is
    # what makes a building this size worth walking.  The emitter lifts it on
    # every map (check Z82), so there is no line for it here.
    # The photo booth.  The pad is the booth floor and the arrival is the
    # same square foot turned round, so the ceremony *is* the gag: the white
    # fade and the sound land on the one player who stepped in
    # (``hud::fade_to_black_for_x_sec`` and ``playsoundtoplayer`` are both
    # per-player calls, see zmforge.script.tricks.short_hop_teleporter),
    # nobody else's screen moves, and the photograph comes out backwards.
    bp.add_custom_logic(
        short_hop_teleporter(
            booth,
            Point(booth.x, booth.y + 56.0, booth.z),
            arrival_yaw=Facing.NORTH.world_yaw,
            suffix="_booth",
        )
    )
    # The Express Lane: a second hop, in the queue's dead end, that moves
    # whoever takes it to the back of the line (the queue's own entry).
    from .dmv_rooms.queue import express_lane

    express_pad, express_arrival = express_lane(plan)
    bp.add_custom_logic(
        short_hop_teleporter(
            express_pad,
            express_arrival,
            arrival_yaw=Facing.EAST.world_yaw,
            suffix="_express",
        )
    )
    # Buying the back office is the encounter.  The sprinters are behind the
    # operator's counter, in the booth, facing the counter they come round;
    # and the spawns run hot for twenty seconds on top of them.  This is an
    # arena, not a boss: see the module docstring for what an operator would
    # actually need.
    bp.add_custom_logic(
        closet_ambush(
            office_door.flag,
            Point(off_in.centre.x + 60.0, booth_y + 8.0, office.floor_z),
            count=plan.ambush_count,
            facing_yaw=Facing.SOUTH.world_yaw,
        )
    )
    bp.add_custom_logic(spawn_spike_on_flag(office_door.flag, seconds=plan.spike_seconds))

    # The words.  Four prompts, one localized string each, and the map's own
    # .str file: this is the only text in the map and it is all this map's.
    #
    # Keyed by the wall buy's own kind and translated through
    # :data:`zmforge.blueprint.catalogue.WALL_WEAPON_WEAPONS`, because the
    # hint lives on ``level.zombie_weapons[<weapon>]`` and the bowie buy
    # sells ``bowie_knife``: renaming "bowie" writes a getweapon() for a
    # name this level's weapon set does not have, which is what Z22 reported.
    for kind, line in PROMPTS.items():
        bp.rename_weapon_prompt(WALL_WEAPON_WEAPONS.get(kind, kind), line)

    # Take a number.  The self-service kiosk inside the front door hands out
    # tickets 1 to 10; from round 5 the PA calls one a minute and its holder
    # has three seconds to be at the service window (TICKET_LINES; the quest's Take a
    # Number stamp counts the serves).
    from ..script.quest import gate_callout

    lines = ticket_lines(plan)
    ticket = {
        key: bp.add_map_string(
            f"TICKET_{key.upper()}", text,
            kind="triggerstring" if key in ("prompt", "number") else "string")
        for key, text in lines.items()
    }
    bp.add_custom_logic(
        take_a_ticket(
            ticket_trigger_point(entry_in, entry.floor_z),
            prompt=ticket["prompt"],
            number=ticket["number"],
            yours=ticket["yours"],
            yours_early=ticket["yours_early"],
            welcome=ticket["welcome"],
            mine=ticket["mine"],
            mine_early=ticket["mine_early"],
            numbers=TICKET_NUMBERS,
            already_served=ticket["already"],
            calls=TicketCalls(
                window=tuple(ticket_window_point(plan, {"waiting": waiting})),
                # No call before the window's room is open: ungated, calls
                # would begin at round 5, behind 3,000 points of doors.
                zones=gate_callout(bp, "ticket calls",
                                   [tuple(ticket_window_point(plan, {"waiting": waiting}))]),
                call=ticket["call"],
                you=ticket["you"],
                hud_call=ticket["hud_call"],
                hud_you=ticket["hud_you"],
                served=ticket["served"],
                served_all=ticket["served_all"],
                missed=ticket["missed"],
                no_one=ticket["no_one"],
                opened=ticket["opened"],
                every=TICKET_CALL_SECONDS,
                grace=TICKET_GRACE_SECONDS,
                start_round=TICKET_OPEN_ROUND,
                radius=TICKET_WINDOW_RADIUS,
                points=TICKET_REWARD_POINTS,
                held_chance=TICKET_HELD_CHANCE,
                # The calls must stop once that task is over (P12).  The quest's Take a Number step done ends
                # the calls and removes the kiosk.
                stop_when=(f"isdefined( level.zmf_q_state ) && "
                           f"level.zmf_q_state[ {TICKET_QUEST_STEP} ] == 2"),
            ),
        )
    )
    # The dispenser's trigger is custom logic, so the design review's element
    # walk cannot see it; say it is there (see review.facts._interactives).
    _tp = ticket_trigger_point(entry_in, entry.floor_z)
    try:
        bp.review_interactives = [{  # type: ignore[attr-defined]
            "id": "ticket_dispenser", "kind": "use_trigger", "what": "take a number",
            "at": [round(_tp.x, 1), round(_tp.y, 1), round(_tp.z, 1)],
            "prompt": TICKET_LINES["prompt"], "purchase": False,
        }]
    except AttributeError:  # pragma: no cover - a slotted blueprint
        pass

    if starting_points is not None:
        bp.add_custom_logic(_starting_points_logic(starting_points))

    # The second furnishing pass -- desks worked at, walls hung, bins and
    # plants -- before the trim, so the skirting and the light grid keep off it.
    _furnish_lived_in(
        bp, plan,
        {"lot": lot, "entry": entry, "waiting": waiting, "windows": windows,
         "eye": eye_exam, "photo": photo, "break": break_room, "records": records,
         "queue": queue, "office": office},
        walk_top=walk_top, walk_x0=walk_x0,
    )
    # The third: what the outbreak left, and the notices that go with it.
    character_rooms = {"lot": lot, "entry": entry, "waiting": waiting,
                       "windows": windows, "eye": eye_exam, "photo": photo,
                       "break": break_room, "records": records, "queue": queue,
                       "office": office}
    _furnish_character(bp, plan, character_rooms, walk_top=walk_top, walk_x0=walk_x0)
    # The fourth: the dense pass, one module per room (``dmv_rooms``), each
    # filling its own room to a lived-in, post-outbreak density.
    from .dmv_rooms import furnish_dense

    furnish_dense(bp, plan, character_rooms, walk_top=walk_top, walk_x0=walk_x0)
    # Last over all four passes: nothing solid within DOOR_BAND of a doorway.
    bp._zmf_dmv_door_bands = _clear_door_bands(bp, character_rooms)  # type: ignore[attr-defined]
    _wire_notices(bp, plan, character_rooms, walk_top=walk_top, walk_x0=walk_x0)
    _wire_gags(bp, plan, character_rooms)
    _wire_quest(bp, plan, character_rooms, walk_top=walk_top)

    # ==================================================================
    # The trim, the fittings and the frontage, last: the light grid keeps
    # off everything already standing, so it is laid after all of it.
    # ==================================================================
    # The fittings' rims: white enamelled metal in the public half, plain
    # steel panel behind the counter, plastic in the small rooms.
    for room, key, rim in ((entry, "entry", _PERFORATED),
                           (waiting, "waiting", _PERFORATED),
                           (windows, "windows", _PERFORATED),
                           (eye_exam, "eye", _MOULDING), (photo, "photo", _MOULDING),
                           (break_room, "break", _MOULDING),
                           (records, "records", _STEEL), (queue, "queue", _STEEL),
                           (office, "office", _STEEL)):
        _dress_room(bp, room, key, rim=rim)
    lot_door = lot.aperture_boxes[0]
    _dress_room(bp, lot, "lot", lights=False)
    _dress_frontage(
        bp, lot, plan, walk_top,
        keep_clear=[
            (lot_door.mins.y - FRAME_WIDTH, lot_door.maxs.y + FRAME_WIDTH),
            (-200.0, -100.0),
        ],
    )

    bp.set_dog_rounds(False)
    # A lit office: no fog, no gloom (zmforge.atmosphere.OFFICE_DAY).
    # GobbleGum beside the boxes, off above four players (script.gobblegum).
    from ..script.gobblegum import place_gobblegum_machines

    place_gobblegum_machines(bp, gobblegums)
    bp.enclose(id="enclosure", atmosphere=OFFICE_DAY)
    bp.light_rooms()
    return bp
