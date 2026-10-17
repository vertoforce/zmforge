"""zm_dmv's ending: five stamps register your car, then pay 20,000 to leave the DMV.

Built from :mod:`zmforge.script.quest` and :mod:`zmforge.script.bosses`;
:func:`zmforge.recipes.dmv._wire_quest` is the one call that installs it.

**As the player meets it.**  From the first second in the car park the
front-door exit says what the map wants (``FRONT DOOR: register your car
(five stamps) to leave the DMV``), and the top-left HUD reads
``REGISTRATION STAMPS: 0 OF 5`` with the current task under it.  In order,
each opening at a round:

1. **Vision Test** (once the eye exam room is open; until then the HUD
   says "Find the Vision Test room", P8).  In the eye exam room, shoot three
   letters on the wall chart (brush letters, :mod:`zmforge.recipes.dmv_rooms.
   eye`) in order: the E (top line, 25 tall), the F (second line, 15 tall,
   beside a decoy P) and the P (third line, 10 tall, among decoys).  Each
   aim radius is half its letter's height.  The next letter is called centre
   screen and pulses; hitting a later one out of turn resets the sequence.
2. **Photo ID** (round 3, after the Vision Test).  In the photo booth the
   photographer's camera counts down ("say cheese... 3... 2... 1", a centre
   HUD line on everyone in or at the door of the booth), then flashes (an
   effect on the camera and a white screen flash); knife it within
   :data:`PHOTO_WINDOW_SECONDS` of the flash, three times.  Each photo is
   announced ("PHOTO 2 OF 3 TAKEN!"); too early and too late each say so.
   Walking in while it is live says what to do, and the notice by the
   camera says it too.
3. **Written Test** (round 4).  Three forms lie in the waiting room, the
   records store and the break room, each pulsing.  Pick them up and hand
   them in at the FORMS IN-TRAY on the counter (the service window only does
   tickets).  Bleed out holding one and it goes back where it was.  A hint at
   the tray says where the three are.
4. **Take a Number** (round 5).  Every player takes a ticket (1 to 10) at the
   lobby kiosk; from round 5 the PA calls a number a minute and its holder
   has three seconds to stand at the service window (:data:`zmforge.recipes.
   dmv.TICKET_GRACE_SECONDS`).  The hall has one window and no window
   numbers.  The stamp comes when every player present has
   been served (``Served: 2 of 4`` on the HUD).  The number calls and the
   stamp open together, at round 5.
5. **Road Test** (round 8).  Walk into the back office and THE EXAMINER steps
   out from behind the counter with four minions: a glowing, much tougher
   zombie whose health is on the HUD.  Kill it for the last stamp, a max ammo
   and 1,000 points each.  A hint inside the office door says so.

Steps 1 to 3 are timed from their first progress (:data:`VISION_TIME_LIMIT`
15 s, :data:`PHOTO_TIME_LIMIT` 60 s, :data:`FORMS_TIME_LIMIT` 180 s), the
seconds left on every HUD under the task; out of time, the step starts over
(the forms go back where they were) with a "TIME'S UP!" line to everyone.

Then the front door sells ``LEAVE THE DMV [Cost: 20000]``; buying it says
"You are free to go. Please drive safely." and ends the game with ``YOU ARE
FREE TO GO`` where GAME OVER would be.  **Unverified in play**: see
:mod:`zmforge.script.quest`.

**Where things are, and why there.**  Every use trigger (three forms, the
forms in-tray, the exit) is at least 80 units from every purchase, door,
window barrier, notice and the ticket machine, in a room, on floor the spawn
flood reaches (``tests/test_dmv_quest.py``).  The exit is 104 from the front door's buy
trigger on the car-park side.  Shot and knifed targets are not use triggers
and sit on the props they name.
"""

from __future__ import annotations

from typing import Mapping

from ..script import quest as q
from ..script.tricks import TICKET_SERVED_FLAG
from ..script.bosses import Boss, BossHealth, BossProp
from ..spatial import Point

__all__ = ["register_quest", "examiner", "FORM_SPOTS", "EXIT_XY", "FORMS_BAY",
           "UNLOCK_ROUNDS", "EXIT_PRICE", "PHOTO_WINDOW_SECONDS", "PHOTO_COUNTDOWN",
           "PHOTO_HEARD", "VISION_TIME_LIMIT", "PHOTO_TIME_LIMIT", "FORMS_TIME_LIMIT"]

#: Rounds each step opens at: vision, photo, written, take a number, road.
#: Take a Number is :data:`zmforge.recipes.dmv.TICKET_OPEN_ROUND`, when the
#: windows start calling numbers.
UNLOCK_ROUNDS = (0, 3, 4, 5, 8)
EXIT_PRICE = 20000
#: Photo ID: seconds the camera stays knifeable after each flash (2 is too
#: short for a player who has not seen the flash coming).
PHOTO_WINDOW_SECONDS = 3.0
#: Photo ID: "say cheese... 3... 2... 1" before every flash, in seconds.
PHOTO_COUNTDOWN = 3
#: Photo ID: seconds of quiet between one flash and the next countdown.
PHOTO_GAP = (3.0, 5.0)
#: Photo ID: who sees the countdown and the flash, in units from the camera.
#: The booth's far corner is 295 from it; 320 takes in the whole booth and
#: its doorway and stops short of the rest of the waiting room.
PHOTO_HEARD = 320.0
#: Time limits, in seconds from the step's first progress (the first letter
#: read, the first photo taken, the first form picked up) to finishing it:
#: all three letters, all three photos, all three forms handed in.  Out of
#: time, the step's progress goes back to 0 (the forms back where they
#: were) and it can be tried again at once.
VISION_TIME_LIMIT = 15.0
PHOTO_TIME_LIMIT = 60.0
FORMS_TIME_LIMIT = 180.0
#: The counter bay (1-based, :func:`zmforge.recipes.dmv.bay_centres`) whose
#: stretch of counter carries the forms in-tray, two bays from the service
#: window so the two use triggers never share a player's reach.
FORMS_BAY = 3
#: Floor points ``(room key, x, y)`` for the three forms, measured clear of
#: every use trigger (the clearance scan in the test).
FORM_SPOTS = (("waiting", -904.0, -172.0), ("records", 148.0, -112.0),
              ("break", -272.0, 536.0))
#: The exit, on the car-park side of the front door.
EXIT_XY = (-1696.0, 0.0)


def _chart_target(eye, n: int, cue: str):
    """The Vision Test's ``n``-th letter, as :mod:`zmforge.recipes.dmv_rooms.
    eye` draws it on the chart: its centre, and an aim radius of half the
    letter's height (12.5 for the E, 7.5 for the F, 5 for the P)."""
    from .dmv_rooms.eye import VISION_LETTERS, chart_target

    point, radius = chart_target(eye, *VISION_LETTERS[n])
    return q.Target(point=point, radius=radius, cue=cue)


def examiner(office, plan) -> Boss:
    """THE EXAMINER, stepping out from behind the operator's counter."""
    o_in = office.interior
    booth_y = o_in.maxs.y - plan.booth_depth + 40.0
    return Boss(
        key="examiner",
        name="THE EXAMINER",
        spawn_at=(o_in.centre.x - 60.0, booth_y + 8.0, office.floor_z),
        yaw=270.0,
        arrives="^1THE EXAMINER^7 has arrived. Your road test begins now. You are being graded.",
        defeated="^1THE EXAMINER^7 has been failed. Final stamp awarded.",
        # 5x the shared boss default (at the plain default a boss falls in
        # seconds), kept as a time to kill: 70 s of one player's wall-gun
        # fire, about the 175,250 that 5x the zombie-health default comes to
        # solo at round 8 (its unlock round), so health follows the guns
        # rather than zombie health (Q6).
        health=BossHealth(ttk=70.0, per_extra_player=0.75),
        # Runs, the template default, never sprints; its minions armour it
        # (a quarter of the damage, 45 s at most).
        armour=0.25,
        minions=4,
        points=1000,
        powerup="full_ammo",
        # A DMV clerk's outfit (the boss needs a
        # different zombie model to read as a boss; the install has no cap, badge or
        # uniform model, so it is office props).  Sizes are props.MODEL_BOX;
        # a wall sign's or clock's face is its -y (props._mount_face), so yaw
        # 90 faces forward and 270 faces back.  Saying +y here
        # shows both pieces' backs (the Scarecrow's sign, same
        # rule, read as a flat grey plate).  Each rides
        # the nearest bone (BossProp tag "auto").  Placement unverified in play.
        props=(
            # "Your time is up": the office wall clock for a head, 32 across.
            BossProp("p7_clock_metal_wall_01_base", offset=(4.0, 0.0, 68.0),
                     angles=(0.0, 90.0, 0.0), scale=1.0),
            # The clipboard: an open binder held upright at the chest, 17x31.
            BossProp("p7_book_office_binder_open", offset=(13.0, 0.0, 36.0),
                     angles=(-90.0, 0.0, 0.0), scale=1.2),
            # The staff badge: the OFFICE sign across its back, 41 wide.
            BossProp("p7_zm_der_signage_office_maxis", offset=(-8.0, 0.0, 50.0),
                     angles=(0.0, 270.0, 0.0), scale=1.2),
        ),
    )


def register_quest(plan, rooms: Mapping[str, object], *, walk_top: float) -> q.Quest:
    """The whole ending for ``rooms`` (keys as :func:`zmforge.recipes.dmv.
    _notice_spots` uses them)."""
    from .dmv import (TICKET_GRACE_SECONDS, TICKET_OPEN_ROUND, counter_run,
                      bay_centres, ticket_window_point)

    if UNLOCK_ROUNDS[3] != TICKET_OPEN_ROUND:
        raise ValueError("the Take a Number stamp opens when the window does")
    window = ticket_window_point(plan, rooms)
    grace = f"{TICKET_GRACE_SECONDS:g}"

    eye, photo, office, lot = rooms["eye"], rooms["photo"], rooms["office"], rooms["lot"]
    face_x = counter_run(plan)[0]
    desk_y = bay_centres(plan)[FORMS_BAY - 1]
    p_in = photo.interior
    # The photographer's display on the east-wall table (dmv_rooms/photo.py:
    # table at maxs.x - 12, y -650; keyboard 1 west, 12 south of it).
    from .dmv_rooms.photo import camera_point

    camera = camera_point(photo)
    o_in = office.interior

    steps = (
        q.HitTargets(
            key="vision",
            # The zone gate (P8) is automatic; this is only its HUD line.
            find="CURRENT TASK: Find the Vision Test room",
            task="CURRENT TASK: Vision Test - shoot the right letters, in the right order (&&1/&&2)",
            start="VISION TEST: please read the chart. The examiner only accepts answers in lead.",
            advance="CORRECT. &&1 OF &&2 letters read.",
            done="VISION TEST PASSED. You can see. Unfortunately.",
            wrong="WRONG LETTER. Please start again from the top.",
            hint=q.Hint(point=(eye.interior.centre.x, eye.interior.centre.y, eye.floor_z),
                        radius=150.0,
                        text="EYE CHART: the examiner reads from the top down. So should you."),
            targets=(
                _chart_target(eye, 0, "NEXT LETTER: ^3E^7"),
                _chart_target(eye, 1, "NEXT LETTER: ^3F^7"),
                _chart_target(eye, 2, "NEXT LETTER: ^3P^7"),
            ),
            pulse_fx="powerup_grabbed_solo",
            # The letters are the puzzle: a cue only after a wrong hit.
            cue_after_wrong=True,
            time_limit=VISION_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! The examiner sighs. Start again from the E.",
            timer_line="VISION TEST: &&1 s left",
        ),
        q.HitTargets(
            key="photo",
            unlock_round=UNLOCK_ROUNDS[1],
            waiting="CURRENT TASK: Photo ID opens at round &&1. Please wait to be called.",
            task="CURRENT TASK: Photo ID - get your three photos taken (&&1/&&2)",
            start="PHOTO ID is open. The photographer is ready for you. Three photos.",
            advance="PHOTO &&1 OF &&2 TAKEN! Wait for the next flash.",
            done="PHOTO ID ACCEPTED. You look terrible. It is valid for ten years.",
            mode="melee",
            hits=3,
            # The welcome: said to each player who walks in while the step is
            # live (the radius reaches the camera and the door).
            hint=q.Hint(point=(p_in.centre.x, p_in.centre.y, photo.floor_z), radius=170.0,
                        cooldown=45.0,
                        text="WELCOME TO THE PHOTO BOOTH. Watch the camera. It will tell you when."),
            targets=(q.Target(point=camera, radius=14.0),),
            flash=q.Flash(line="^3*FLASH*^7 KNIFE THE CAMERA NOW!",
                          count_line="PHOTO ID: say cheese... &&1",
                          early="Too early. Wait for the FLASH.",
                          late="Too late. Wait for the next flash.",
                          every=PHOTO_GAP, open=PHOTO_WINDOW_SECONDS,
                          countdown=PHOTO_COUNTDOWN, heard=PHOTO_HEARD,
                          count_fx="powerup_grabbed_caution", screen=True),
            time_limit=PHOTO_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! The photographer sighs. Three new photos, please.",
            timer_line="PHOTO ID: &&1 s left",
        ),
        q.CollectDeliver(
            key="written",
            unlock_round=UNLOCK_ROUNDS[2],
            waiting="CURRENT TASK: Written Test opens at round &&1. Please take a seat.",
            task="CURRENT TASK: Written Test - find the missing forms and hand them in (&&1/&&2)",
            start="WRITTEN TEST: three forms are lost in the building. The clerk wants them back.",
            advance="&&1 OF &&2 FORMS FILED. The rest are still out there.",
            done="WRITTEN TEST PASSED. Nobody read it.",
            items=tuple(
                q.Item(point=(x, y, rooms[room].floor_z), model="p7_office_paper_folder_blue",
                       picked=picked)
                for (room, x, y), picked in zip(FORM_SPOTS, (
                    "You took FORM MV-1 (Application). The clerk wants it.",
                    "You took FORM MV-2 (Proof of Residence). The clerk wants it.",
                    "You took FORM 27-B (Request for Form 27-A). The clerk wants it.",
                ))
            ),
            deliver_at=(face_x - 30.0, desk_y, rooms["windows"].floor_z),
            pickup_prompt="Hold ^3[{+activate}]^7 to take the FORM",
            deliver_prompt="FORMS IN-TRAY: hold ^3[{+activate}]^7 to hand in your forms",
            empty="FORMS IN-TRAY: You have no forms. They are somewhere in the building.",
            dropped="A form was lost with its owner. It is back where it was found.",
            time_limit=FORMS_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! The clerk sighs and puts every form back. Start again.",
            timer_line="WRITTEN TEST: &&1 s left",
            hint=q.Hint(point=(face_x - 30.0, desk_y, rooms["windows"].floor_z), radius=160.0,
                        text="FORMS IN-TRAY: three forms wandered off. Bring them here."),
        ),
        q.EveryPlayerFlag(
            key="number",
            unlock_round=UNLOCK_ROUNDS[3],
            waiting="CURRENT TASK: Take a Number. Service opens at round &&1.",
            task=(f"CURRENT TASK: Take a Number - answer your call within {grace} s. "
                  "Served: &&1 of &&2"),
            start="TAKE A NUMBER: now serving. Everybody must be served.",
            done="EVERYONE HAS BEEN SERVED. That has never happened before.",
            hint=q.Hint(point=tuple(window), radius=170.0,
                        text=("SERVICE WINDOW: no number, no service. When yours is called "
                              f"you have {grace} seconds.")),
            flag=TICKET_SERVED_FLAG,
        ),
        q.DefeatBoss(
            key="road",
            unlock_round=UNLOCK_ROUNDS[4],
            waiting="CURRENT TASK: Road Test opens at round &&1. Please remain seated.",
            task="CURRENT TASK: Road Test - fail THE EXAMINER (&&1% left)",
            start="ROAD TEST: THE EXAMINER will see you now.",
            done="ROAD TEST PASSED. Your car is registered.",
            hint=q.Hint(point=(o_in.centre.x, o_in.mins.y + 120.0, office.floor_z), radius=220.0,
                        text="ROAD TEST: THE EXAMINER has never passed anyone. Return the favour."),
            boss=examiner(office, plan),
            arena=(o_in.centre.x, o_in.mins.y + 216.0, office.floor_z),
            arena_radius=220.0,
        ),
    )
    exit_z = walk_top if EXIT_XY[0] >= lot.interior.maxs.x - plan.walk_depth else lot.floor_z
    return q.Quest(
        key="register",
        header="REGISTRATION STAMPS: &&1 OF &&2",
        intro="WELCOME TO THE DMV. Get all five stamps to register your car and leave.",
        step_done="STAMP &&1 OF &&2",
        complete="ALL FIVE STAMPS. Your car is registered. You may leave.",
        idle="CURRENT TASK: please wait to be called.",
        steps=steps,
        exit=q.BuyableExit(
            origin=(EXIT_XY[0], EXIT_XY[1], exit_z),
            price=EXIT_PRICE,
            locked_prompt="FRONT DOOR: register your car (five stamps) to leave the DMV",
            prompt="Hold ^3[{+activate}]^7 to LEAVE THE DMV [Cost: &&1]",
            locked="You may not leave until your registration has all five stamps.",
            poor="Leaving costs &&1 points. There is a processing fee.",
            task="CURRENT TASK: leave the DMV (&&1 points)",
            win_line="You are free to go. Please drive safely.",
            win_title="YOU ARE FREE TO GO",
        ),
    )


def use_points(quest: q.Quest) -> list[Point]:
    """The quest's use triggers as :class:`~zmforge.spatial.Point`, for tests."""
    return [Point(*p) for p in quest.use_points()]
