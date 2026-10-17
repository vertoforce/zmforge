"""zm_cemetery's quest, "The Groundskeeper's Last Shift", and its ending.

Built from :mod:`zmforge.script.quest` and :mod:`zmforge.script.bosses`;
:func:`zmforge.recipes.cemetery.cemetery_map` installs it with one
:func:`~zmforge.script.quest.install_quest` call.

**As the player meets it.**  The top-left HUD reads ``THE GROUNDSKEEPER'S LAST
SHIFT: 0 OF 7`` from the first second, with the current task under it, and
the Founder's sarcophagus in the crypt says what it is for from the start.
In order, each opening at a round:

1. **Dig** (COLLECT and DELIVER, from the start).  The groundskeeper's shovel
   is on the workbench in his shed; take it to the Open Grave on the hills.
   Bleed out carrying it and it goes back to the bench.  45 seconds from
   picking it up (:data:`DIG_TIME_LIMIT`).
2. **Will-o'-wisps** (SHOOT, round 3).  Four cold blue lanterns burn on four
   hills; shoot each one out, all four within 60 seconds of the first
   (:data:`WISPS_TIME_LIMIT`).
3. **The Founder** (KNIFE, round 4).  Knife the Founder's needle on the
   tallest hill, three times within 20 seconds (:data:`FOUNDER_TIME_LIMIT`).
   He wakes up.

Steps 1 to 3 count down on every HUD under the task once started; out of
time, the step starts over (the shovel goes back to the bench, the wisps
relight) with a "TIME'S UP!" line to everyone.
4. **The coffin** (DEFEND, round 5).  Stand by the Founder's coffin in the
   chapel for sixty seconds while the dead come for it.
5. **The graves** (SOUL BOX, right after the coffin).  The day's two fresh
   graves on the hills walk want filling: every zombie a player kills near
   one sends its soul flying into the nearer grave that is still hungry, and
   a headstone climbs out of the ground as it fills.  12 souls a grave solo,
   5 more a grave for each extra player (:data:`GRAVE_SOULS`).
6. **The Gravedigger** (BOSS, round 6).  Go back to the Open Grave: THE
   GRAVEDIGGER climbs out beside it with six friends -- a glowing, much tougher zombie
   whose health is on the HUD.  Kill him for the Crypt Seal, a max ammo and
   1,000 points each.
7. **Dawn** (SURVIVE).  Hold out two more rounds.

Then the sarcophagus in the Founder's Tomb sells ``REST IN PEACE [Cost:
20000]``; buying it says "The seal sets. The key turns. The crypt is sealed. Everybody gets
to lie down."
and ends the game with ``REST IN PEACE`` where GAME OVER would be.

**Where things are, and why there.**  Every use trigger the quest spawns
(the shovel, the grave, the exit) is at least 80 units from every purchase,
door, window barrier and notice, on floor the spawn flood reaches
(``tests/test_cemetery.py``).  Shot and knifed targets are the lanterns and
the needle themselves.  **Unverified in play**: see :mod:`zmforge.script.quest`.
"""

from __future__ import annotations

from typing import Mapping

from ..script import quest as q
from ..script.bosses import BOSS_TTK, Boss, BossHealth, BossProp
from ..spatial import Point
from .cemetery import ENDING_PRICE

__all__ = ["cemetery_quest", "gravedigger", "UNLOCK_ROUNDS", "EXIT_PRICE",
           "DIG_TIME_LIMIT", "WISPS_TIME_LIMIT", "FOUNDER_TIME_LIMIT",
           "GRAVE_SOULS", "GRAVE_SOULS_PER_EXTRA_PLAYER", "GRAVE_STONE"]

#: Round each step opens at, in order.
UNLOCK_ROUNDS = (0, 3, 4, 5, 0, 6, 0)
#: The ending's fixed price.
EXIT_PRICE = ENDING_PRICE
#: The skill steps' time limits, in seconds from their first progress (P6).
#: The dig: the shed bench to the Open Grave is 1,100 units as the crow flies
#: and about twice that on the walks (shed door, gate, hills door): 10-12 s
#: at a run, so 45 s leaves room to fight through the first rounds' zombies.
DIG_TIME_LIMIT = 45.0
#: The wisps: from the first shot, the other three are 890-1,440 units apart
#: on four hilltops in fog; a tour of all four is about 2,900 units (15 s at
#: a run, uphill), so 60 s allows for walking to a clear sightline on each.
WISPS_TIME_LIMIT = 60.0
#: The Founder: three knife hits on one stone, from the first; 20 s is a
#: lunge every few seconds with the round-4 horde on your back.
FOUNDER_TIME_LIMIT = 20.0
#: The soul graves: souls each of the two fresh graves wants solo, and more
#: for each player past the first (24 solo in all, 34 for two, 54 for four).
#: The step opens at round 5 or 6, when a round is about 15-25 zombies solo,
#: so it is about a round of fighting on the walk.
GRAVE_SOULS = 12
GRAVE_SOULS_PER_EXTRA_PLAYER = 5
#: The headstone that climbs out of each grave as it fills: 48 tall, so 1.2
#: is 58 tall and starts 60 under the ground, out of sight.
GRAVE_STONE = "zmf_prop_gravestone_cross"


def _t(p: Point) -> tuple[float, float, float]:
    return (float(p.x), float(p.y), float(p.z))


def gravedigger(at: Point) -> Boss:
    """THE GRAVEDIGGER, climbing out beside the Open Grave (``at``: on the
    knoll's flat top, clear of the grave's rim and its dig trigger)."""
    return Boss(
        key="gravedigger",
        name="THE GRAVEDIGGER",
        spawn_at=_t(at),
        yaw=270.0,
        arrives="^1THE GRAVEDIGGER^7 climbs out of the Open Grave. Jonah Diggs still wants the groundskeeper's shovel.",
        defeated="^1THE GRAVEDIGGER^7 is back in the ground. He dropped the CRYPT SEAL.",
        # 40 s of one player's best guns at round 6 (Pack-a-Punch included):
        # 100,000 solo, 325,000 for four, 625,000 for eight.  A boss near
        # 30,000 solo falls in seconds to Pack-a-Punched guns, so this fight
        # is the calibration point of GUN_TIERS.
        health=BossHealth(ttk=BOSS_TTK, per_extra_player=0.75),
        # Slower, not faster (a tanky boss should not sprint): he runs, the
        # template default, and never sprints.  His diggers armour him: a
        # quarter of the damage while they live, 45 s at most.
        armour=0.25,
        exposed="THE GRAVEDIGGER's diggers are down. Now he can be hurt.",
        minions=6,
        points=1000,
        powerup="full_ammo",
        # The gravedigger's kit (props.MODEL_BOX sizes).  Unverified in play.
        props=(
            # A grave cross strapped to his back, over his head: authored
            # upright, 78 tall from its base, so 0.8 is 62 tall from z 24.
            # Each rides a bone (back, right hand, left hand) so it moves
            # with him, not with his feet.
            BossProp("zmf_prop_wooden_cross", offset=(-10.0, 0.0, 24.0), scale=0.8,
                     tag="tag_stowed_back"),
            # His shovel, upright at his right side: 60 long on y about its
            # middle, roll 90 stands it up, 1.2 makes it 72 tall.
            BossProp("p7_tools_shovel", offset=(6.0, -16.0, 38.0), angles=(0.0, 0.0, 90.0),
                     scale=1.2, tag="tag_weapon_right"),
            # A hurricane lantern in his left hand, 26.5 tall from its base.
            BossProp("p7_zm_der2_light_hurricane_lamp", offset=(8.0, 16.0, 22.0), scale=1.3,
                     tag="tag_weapon_left"),
        ),
    )


def cemetery_quest(features: Mapping[str, object], rooms: Mapping[str, object]) -> q.Quest:
    """The whole quest for a dressed cemetery (``features`` as
    :func:`zmforge.recipes.cemetery_dressing.dress` returns them)."""
    shovel: Point = features["shovel"]
    grave: Point = features["open_grave"]
    founder: Point = features["founder"]
    coffin: Point = features["coffin"]
    exit_at: Point = features["exit"]
    wisps = features["wisps"]
    graves = features["fresh_graves"]
    chapel = rooms["chapel"]
    steps = (
        q.CollectDeliver(
            key="dig",
            task="CURRENT TASK: finish the groundskeeper's dig (&&1/&&2)",
            start="THE GROUNDSKEEPER'S LAST SHIFT: he left a grave half dug. Finish it.",
            done="Under the old bones: a KEY stamped 'FOUNDER' and a note: 'BACK SOON -- A.G.'. Keep the key.",
            items=(q.Item(point=_t(shovel), model="p7_tools_shovel",
                          picked="You took the groundskeeper's SHOVEL. Somewhere, a grave is waiting."),),
            deliver_at=_t(grave),
            pickup_prompt="Hold ^3[{+activate}]^7 to take the SHOVEL",
            deliver_prompt="OPEN GRAVE: hold ^3[{+activate}]^7 to dig",
            empty="You cannot dig with your hands. The groundskeeper had a SHOVEL somewhere.",
            dropped="The shovel went back where it came from. The dead tidy up after themselves.",
            hint=q.Hint(point=_t(grave), radius=200.0,
                        text="THE OPEN GRAVE: half dug. It needs a shovel, not hands."),
            time_limit=DIG_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! The shovel is back where it was. The dead tidied up again.",
            timer_line="THE DIG: &&1 s left",
        ),
        q.HitTargets(
            key="wisps",
            unlock_round=UNLOCK_ROUNDS[1],
            waiting="CURRENT TASK: the will-o'-wisps come out at round &&1.",
            task="CURRENT TASK: put out the WILL-O'-WISPS (&&1/&&2)",
            start="WILL-O'-WISPS: cold lights are burning out in the fog. Put them out.",
            advance="&&1 OF &&2 wisps out. The fog gets thicker.",
            done="The wisps are out. Something on the big hill is annoyed.",
            targets=tuple(q.Target(point=_t(p), radius=14.0) for p in wisps),
            ordered=False,
            pulse_fx="powerup_grabbed_solo",
            time_limit=WISPS_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! All four wisps are burning again. Start again.",
            timer_line="WILL-O'-WISPS: &&1 s left",
            hint=q.Hint(point=_t(wisps[0]), radius=260.0,
                        text="WILL-O'-WISP: the path lamps burn warm. The wisps do not."),
        ),
        q.HitTargets(
            key="founder",
            unlock_round=UNLOCK_ROUNDS[2],
            waiting="CURRENT TASK: the Founder is asleep until round &&1.",
            task="CURRENT TASK: wake the Founder (&&1/&&2)",
            start="THE FOUNDER sleeps deeply. Wake him. Up close.",
            advance="OW. (&&1 of &&2)",
            done="OW! The Founder is awake. The dead are after his funeral COFFIN.",
            mode="melee",
            hits=3,
            targets=(q.Target(point=_t(founder), radius=16.0),),
            time_limit=FOUNDER_TIME_LIMIT,
            lockdown=True,
            timeout="TIME'S UP! The Founder rolled over and went back to sleep. Three more.",
            timer_line="WAKE THE FOUNDER: &&1 s left",
            hint=q.Hint(point=_t(founder), radius=180.0,
                        text="THE FOUNDER'S NEEDLE: he sleeps through gunfire. Try something sharper."),
        ),
        q.StandInZone(
            key="coffin",
            lockdown=True,
            unlock_round=UNLOCK_ROUNDS[3],
            waiting="CURRENT TASK: the Founder's coffin is safe until round &&1.",
            task="CURRENT TASK: guard the Founder's COFFIN (&&1/&&2 seconds)",
            start="THE COFFIN: the dead want the Founder's funeral coffin. Guard it for 60 seconds.",
            advance="&&1 of &&2 seconds guarded.",
            done="The coffin is safe; his bones can go down to the sarcophagus. The Gravedigger heard about this.",
            point=(float(coffin.x) - 90.0, float(coffin.y), float(chapel.floor_z)),
            seconds=60,
            radius=150.0,
            announce_every=15,
        ),
        q.SoulBox(
            key="graves",
            task="CURRENT TASK: fill the fresh GRAVES with the dead (&&1/&&2 souls)",
            start=("THE DAY'S BURIALS: two fresh graves stand open, and nobody came to fill them. "
                   "Kill the dead beside them. The graves will take their souls."),
            full="One grave is full and its stone is up. &&1 of &&2.",
            done="Both graves are full and their stones are up. Those were HIS graves. Somebody is coming to complain.",
            # Each pit's north end (the pit is 80 long, planks across its
            # middle), facing the walk; the stone climbs out of the ground as
            # the grave fills (cemetery_scenes.walk_scenes).
            vessels=tuple(q.Vessel(point=(float(g.x), float(g.y) + 28.0, float(g.z)),
                                   model=GRAVE_STONE, scale=1.2, rise=60.0, mouth=24.0)
                          for g in graves),
            souls=GRAVE_SOULS,
            per_extra_player=GRAVE_SOULS_PER_EXTRA_PLAYER,
            radius=450.0,
        ),
        q.DefeatBoss(
            key="gravedigger",
            unlock_round=UNLOCK_ROUNDS[5],
            waiting="CURRENT TASK: the Gravedigger clocks on at round &&1.",
            task="CURRENT TASK: put THE GRAVEDIGGER back in the ground (&&1% left)",
            start="THE GRAVEDIGGER is back for his hole.",
            done="THE CRYPT SEAL is yours. Now hold on until dawn.",
            boss=gravedigger(features.get("boss_spawn", grave)),
            arena=_t(grave),
            arena_radius=320.0,
        ),
        q.SurviveRounds(
            key="dawn",
            task="CURRENT TASK: hold out until DAWN (&&1/&&2 rounds)",
            start="DAWN is two rounds away. Hold on.",
            advance="&&1 of &&2: the sky is getting lighter. Slightly.",
            done="DAWN. The dead are yawning.",
            rounds=2,
        ),
    )
    return q.Quest(
        key="lastshift",
        header="THE GROUNDSKEEPER'S LAST SHIFT: &&1 OF &&2",
        intro="HOLLOW REST CEMETERY. Finish the groundskeeper's last shift to rest in peace.",
        step_done="SHIFT TASK &&1 OF &&2 DONE",
        complete="THE SHIFT IS DONE. The FOUNDER KEY and the CRYPT SEAL belong with the Founder.",
        idle="CURRENT TASK: wait for the next task.",
        steps=steps,
        exit=q.BuyableExit(
            origin=_t(exit_at),
            price=EXIT_PRICE,
            locked_prompt="THE FOUNDER'S SARCOPHAGUS: it is locked. Finish the groundskeeper's shift first",
            prompt="Hold ^3[{+activate}]^7 to set the CRYPT SEAL, turn the KEY and REST IN PEACE [Cost: &&1]",
            locked="The key will not turn until the shift is done.",
            poor="Eternal rest costs &&1 points. Funerals are expensive.",
            task="CURRENT TASK: lay the Founder to REST IN PEACE (&&1 points)",
            win_line="The seal sets. The key turns. The crypt is sealed. Everybody gets to lie down.",
            win_title="REST IN PEACE",
        ),
    )
