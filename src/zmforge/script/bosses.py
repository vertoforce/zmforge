"""Mini-bosses: an ordinary stock zombie made big enough to be an event.

**Using it (any map).**  Describe the boss once and hand it to a quest step
or to a round schedule::

    from zmforge.script.bosses import Boss, BossHealth, install_boss_rounds

    examiner = Boss(
        key="examiner",                      # [a-z0-9_], names the GSC functions
        name="THE EXAMINER",                 # said on screen, never a model swap
        spawn_at=(x, y, z), yaw=180.0,       # a floor point the navmesh reaches
        arrives="^1THE EXAMINER^7 has entered the building.",
        defeated="^2THE EXAMINER^7 has been failed.",
        health=BossHealth(),                 # 35 of this round's zombies
        minions=4, points=500, powerup="full_ammo",   # runs (default), never sprints
    )
    install_boss_rounds(bp, examiner, rounds=(8, 16))   # stand-alone use
    # or: quest.DefeatBoss(boss=examiner, ...)          # as a quest step

:func:`boss_script` is the pure half (a :class:`~zmforge.script.custom.
CustomScript` plus the text it needs); the ``install_*`` helpers register
every line with :meth:`~zmforge.blueprint.model.Blueprint.add_map_string`
and weave the logic in.  One boss key per map.

**Why a souped-up zombie and not a stock special enemy.**  The research in
``docs/special-enemies.md``: the mod tools ship three aitypes
(the factory zombie, the factory dog, the usermap zombie); Panzer, Margwa,
Raz, thrasher and fury ship only their shared behaviour scripts, with no
aitype, animation state machine or character model a usermap could list.
So the boss is the map's own zombie spawner, as :func:`zmforge.script.
tricks.closet_ambush` uses it, with the differences below.

**Every call, and where it was read** (``share/raw/scripts`` of the mod
tools, the tree the linker compiles):

=====================================  =========================================
what                                   evidence
=====================================  =========================================
spawn one zombie on demand             ``zombie_utility::spawn_zombie`` after
                                       ``script_forcespawn = 1``:
                                       ``shared/ai/zombie_utility.gsc:1454``,
                                       ``:1469`` (the forcespawn test);
                                       ``level.zombie_spawners``:
                                       ``zm/_zm_spawner.gsc:47``
put it in the arena                    ``spawn_zombie``'s ``spawn_point``, a
                                       ``"spawn_location"`` struct
                                       (``zm/_zm.gsc:3965``,
                                       ``zm/_zm_utility.gsc:188-300``); a
                                       ``forceteleport`` after the spawn is
                                       undone by the stock spawn code
                                       (:func:`_arrival_lines`)
wait for the stock init before         ``while ( !IS_TRUE( self.zombie_init_done
raising health                         ) )``: ``zm/_zm_ai_faller.gsc:168``; the
                                       init writes ``maxhealth``/``health`` at
                                       ``zm/_zm_spawner.gsc:293-304`` and sets
                                       ``zombie_init_done`` at ``:389``
more health                            ``self.maxhealth = ...; self.health =
                                       ...`` as ``zm/_zm_ai_raps.gsc:980-988``
                                       does for its own AI; the amount is
                                       :data:`BOSS_ZOMBIE_MULTIPLE` times
                                       ``level.zombie_health``, the value
                                       every zombie gets
                                       (``zm/_zm_spawner.gsc:293-295``),
                                       set per round by
                                       ``ai_calculate_health``
                                       (``shared/ai/zombie_utility.gsc:
                                       1906-1929``, called
                                       ``zm/_zm.gsc:3703``)
no random drop, nuke-proof             ``self.no_powerups = true``
                                       (``zm/_zm_ai_faller.gsc:223``);
                                       ``ignore_nuke`` skipped by the nuke at
                                       ``zm/_zm_powerup_nuke.gsc:87``
never cleaned up                       ``b_ignore_cleanup`` is the flag
                                       ``zm/zm_giant_cleanup_mgr.gsc:125``
                                       honours; a generated usermap does not
                                       run that manager, so it is a guard only
move speed (run by default)            ``zombie_utility::
                                       set_zombie_run_cycle_override_value``
                                       (``zombie_utility.gsc:2060-2064``):
                                       sets the speed and
                                       ``zombie_move_speed_override``, after
                                       which a stock ``set_zombie_run_cycle``
                                       only records its wish and returns
                                       (``:2078-2082``)
stays at that speed                    a watcher re-applies the override
                                       every second if ``zombie_move_speed``
                                       ever differs; see :data:`BOSS_SPEEDS`
a glow on the body                     ``PlayFXOnTag( level._effect[ ... ],
                                       self, "J_SpineLower" )`` on a zombie:
                                       ``zm/_zm_traps.gsc:1025``; the effect
                                       names are the powerup ones
                                       ``zm/_zm_powerups.gsc:80-91``,
                                       precached there ``:44-52``
a pulse where it walks                 ``PlayFX( level._effect[ ... ], origin
                                       )``: ``zm/_zm_powerups.gsc:925``
the ground shakes when it arrives      ``Earthquake``: the table's entry
reward on death                        ``self waittill( "death", attacker )``:
                                       ``shared/spawner_shared.gsc:2532``;
                                       ``zm_powerups::specific_powerup_drop(
                                       name, origin )``:
                                       ``zm/_zm_ai_raps.gsc:590``; points:
                                       ``zm_score::add_to_player_score``
=====================================  =========================================

**Fairness** (a common Workshop complaint; check Q6).
Health is a time to kill (:attr:`BossHealth.ttk`, seconds of one player's
fire with the guns of that round, :data:`GUN_TIERS`, unmeasured estimates)
scaled by the players *present*, under :attr:`BossHealth.cap`.  While any
boss lives ``level.zombie_ai_limit`` drops to
:attr:`Boss.fight_zombie_limit` (10) and special rounds are held back
(:func:`hold_special_lines`); a scheduled boss round that lands on a dog
round waits for the next round.  A tanky boss is slower: it runs, never
sprints, unless a map asks for a second phase (:attr:`Boss.hurt_speed`); with
:attr:`Boss.armour` it takes a share of the damage while its minions live
(at most :attr:`Boss.armour_seconds`).  A boss with about 28,000 solo
health on round 6 dies too easily and a forced sprint is too fast, so the
default is 40 s (:data:`BOSS_TTK`), 100,000 solo at round 6, running.

**What the player sees:** a centre-screen line with the boss's name when it
spawns (with a short earthquake and the hellhounds' lightning strike); a
zombie in a themed outfit of two or three props (the Scarecrow's
jack-o'-lantern head, crossbar arms and chest sign, see :class:`BossProp`),
**on fire** on its head, chest and hips for its whole life
(:data:`BOSS_LOUD_FX`), lit **red** on the same tags with a red burst every
second (red is the boss colour: nothing else in a usermap plays it, see
:data:`BOSS_RED_FX`),
and a red skull marker floating over it that shows through walls; it takes
a magazine or several to drop, and when it dies the prop, the glow and the
marker go and a centre-screen line plus the reward follow.  A quest step
also names it and shows its remaining health on the objective HUD
(:mod:`zmforge.script.quest`).  A single caution glow on the spine alone
does not read as a boss.

**Look, and where it was read.**

=====================================  =========================================
what                                   evidence
=====================================  =========================================
red glow                               ``zombie/fx_powerup_on_red_zmb`` and
                                       ``..._grab_red_zmb`` are ``#precache``d
                                       unconditionally
                                       (``zm/_zm_powerups.gsc:47-48``); only
                                       their ``level._effect`` names sit behind
                                       ``level.using_zombie_powerups``
                                       (``:83-87``), so the boss registers its
                                       own names for the same paths
glow on several body tags              ``PlayFXOnTag`` on ``j_spine4``
                                       (``zm/aats/_zm_aat_turned.csc:41``) and
                                       ``J_SpineLower`` (``zm/_zm_traps.gsc:
                                       1025``) of a zombie; ``j_head`` is the
                                       zombie's head bone
a prop on the body                     ``spawn( "script_model", v )``,
                                       ``SetModel``, ``SetScale`` (as the corn
                                       maze's own script models) and
                                       ``LinkTo( ent, "tag_origin", offset,
                                       angles )`` (``shared/vehicles/
                                       _hunter.gsc:1605``); the xmodel is
                                       declared in the zone through the
                                       script's ``assets``
floating marker                        ``NewHudElem``, ``setShader``,
                                       ``setwaypoint``, ``SetTargetEnt``
                                       (``shared/entityheadicons_shared.gsc:
                                       156-165``); the skull material
                                       ``specialty_instakill_zombies`` is
                                       precached by
                                       ``zm/_zm_powerup_insta_kill.gsc:21``,
                                       which ``zm/zm_usermap.gsc:45`` uses
=====================================  =========================================

Unverified in play: that a script model linked to an actor's
``tag_origin`` follows it smoothly, each prop's offset and facing (the
props are placed from their measured size, not from a screenshot), and the
marker's size.

**Not possible or not verified.**  No body swap and no ``SetScale`` on the
actor: the only ``SetScale`` in the tree is on a spawned ``script_model``
(``shared/ai/archetype_robot.gsc:3520``), never on an actor, and a body
swap would fight the stock gibbing, which swaps the body to the factory
zombie's ``_g_`` gib models by itself.  The distinct look is a prop linked
to the body instead.  **Nor can it be made bigger**:
every ``SetScale`` in the stock tree (``grep -rn SetScale`` over
``share/raw/scripts``) is on a ``script_model`` or a client-side player
model, none on an actor or AI, so the boss is its zombie's size and the
props carry the silhouette.  **No other body to swap to** (checked):
the install's only zombie character is Der Eisendrache's
(``model_export/t7_characters_zombie.gdt``: bodies ``c_zom_der_zombie_body1``
/ ``2``, heads ``_head1``-``3``, ``_helmet1``, all in ``zm_levelcommon``,
all already worn at random by ordinary zombies); every other character model
declared (``c_t7_mp_warrior_*``, ``c_t7_ally_fb``, ``c_t7_enemy_fb``...) is in
``xmodels_unlinkable`` (``installed_assets.json``), and Margwa, Panzer and
the rest ship no model at all.  A custom skinned body would mean rigging a
mesh to this skeleton, exporting it as an animated xmodel plus a character
gdt with the mod tools, and swapping it past the gib system: days,
not a boss option.  **Two appearance options instead**:
:attr:`BossProp.tag` rides a prop on a bone so it moves with the animation
(every prop does, the nearest bone by default, and
``tag_origin`` is refused), and :attr:`Boss.headless` takes the zombie's own
head off for a prop head.  So a costumed boss is still the stock zombie
under its props: that part cannot be made right with stock assets.  **Insta-kill does not kill it**
(without the guard, one shot with the powerup up does):
``check_for_instakill`` (``zm/_zm_powerups.gsc:1438-1500``) calls
``level.check_for_instakill_override`` with the *zombie* as ``self`` and
returns without a kill when it answers false (:1440-1445), so a level-wide
override can still answer per zombie.  Every boss sets
``self.zmf_no_instakill`` and the override answers false for it and "is
insta-kill up for this player" (the stock test, :1467) for everyone else.
The boss also sets the stock per-entity ``instakill_func`` (:1474-1481),
but that is called with ``thread``, and whether a threaded call hands back
its return value is not something this repository can measure, so the
override is the guard that is relied on.  Health is capped
(:attr:`BossHealth.cap`): the uncapped DMV formula was about 1.1 million
at round 8 with 8 players (G4).  Unverified in play: whether the glow loops on an actor or plays
once, whether the powerup fx names resolve in a usermap that never drops
that colour, the health numbers' feel (35 zombies is ~29,750 hit points on
round 8 solo), that a sprint set after spawn changes the gait at once, and
that the forced teleport lands on navmesh.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .custom import CustomFunction, CustomScript, Slot
from .tricks import _ring, _vector, spawn_point_lines

__all__ = [
    "Boss",
    "BossHealth",
    "BossProp",
    "BOSS_FX",
    "BOSS_AUTO_BONES",
    "BOSS_GLOW_TAGS",
    "BOSS_MARKER",
    "BOSS_RED_FX",
    "BOSS_LOUD_FX",
    "BOSS_OWN_FX",
    "BOSS_SPEEDS",
    "BOSS_ZOMBIE_MULTIPLE",
    "stock_zombie_health",
    "boss_fx_paths",
    "boss_script",
    "boss_strings",
    "precache_boss_fx",
    "install_boss_rounds",
]

_ZOMBIE_UTILITY = r"scripts\shared\ai\zombie_utility"
_ZM = r"scripts\zm\_zm"
_POWERUPS = r"scripts\zm\_zm_powerups"
_SCORE = r"scripts\zm\_zm_score"
_FLAG = r"scripts\shared\flag_shared"

#: ``level._effect`` names a map may glow or pulse with.  All are assigned
#: unconditionally in ``zm/_zm_powerups.gsc:80-91`` and precached at
#: ``:44-52``; the red pair (``:85-86``) is inside an ``if`` and is left out.
BOSS_RED_FX: dict[str, str] = {
    "zmf_boss_aura": "zombie/fx_powerup_on_red_zmb",
    "zmf_boss_burst": "zombie/fx_powerup_grab_red_zmb",
}

#: The loud half (a subtle red glow alone does not read).  The
#: hellhound's body fire, ``zombie/fx_dog_fire_trail_zmb`` (precached
#: ``zm/_zm_ai_dogs.gsc:34`` and ``.csc:12``; the dog keeps it burning on
#: ``j_spine2`` for its whole life, ``_zm_ai_dogs.csc:38``, so it loops), set
#: on the boss's head, chest and hips; and the hellhound spawn's lightning
#: strike, ``zombie/fx_dog_lightning_buildup_zmb`` (``_zm_ai_dogs.gsc:31``,
#: named ``lightning_dog_spawn`` at ``:98``), where the boss arrives.
#: ``_zm_ai_dogs`` is in every usermap (``zm/zm_usermap.gsc`` uses it).
BOSS_LOUD_FX: dict[str, str] = {
    "zmf_boss_fire": "zombie/fx_dog_fire_trail_zmb",
    "zmf_boss_arrive": "zombie/fx_dog_lightning_buildup_zmb",
}

#: Every effect name the boss registers itself, name -> stock path.
BOSS_OWN_FX: dict[str, str] = {**BOSS_RED_FX, **BOSS_LOUD_FX}
"""The boss colour.  The red powerup pair is precached unconditionally
(``zm/_zm_powerups.gsc:47-48``) but named in ``level._effect`` only when a
map sets ``level.using_zombie_powerups`` (``:83-87``), which a usermap does
not, so nothing else in these maps plays red: the boss registers the two
paths under its own names at spawn."""

#: Where the red aura is played: head, chest and hips, so the colour covers
#: the body and not one point on it.
BOSS_GLOW_TAGS: tuple[str, ...] = ("j_head", "j_spine4", "J_SpineLower")

#: The floating marker's material: the insta-kill skull, precached by
#: ``zm/_zm_powerup_insta_kill.gsc:21`` (used by ``zm/zm_usermap.gsc:45``).
BOSS_MARKER = "specialty_instakill_zombies"

#: The usermap zombie's skeleton at rest, per tag a prop may ride on:
#: ``(position, (X, Y, Z axes))`` in the boss's own frame (forward, left, up
#: from the feet, ``tag_origin``).  Measured from the bind pose in
#: ``model_export/t7_characters/zombies/zombies/c_zom_der_zombie_body1_LOD0.
#: XMODEL_BIN`` (LZ4 payload: chunk ``0xF099`` names each bone, ``0xDD9A``
#: then ``0x9383`` offset and ``0xDCFD``/``0xCCDC``/``0xBFFC`` axes as int16
#: /32767); ``..._body2`` has the identical skeleton.  Those are the only two
#: bodies the usermap zombie character uses (``model_export/
#: t7_characters_zombie.gdt``, ``c_zom_der_zombie1``...).  Sanity: ``tag_eye``
#: sits 4 forward of ``j_head``, ``tag_weapon_left`` 18 to the left.  A prop
#: linked to one of these tags follows that bone's animation (a script model
#: linked to an actor's bone with an offset and angles:
#: ``shared/ai/archetype_robot.gsc:3521``, ``LinkTo( entity, "j_spine4", ...
#: )``); :meth:`BossProp.link` converts the prop's rest placement into the
#: tag's frame, so a prop is still authored where it sits at rest.
BOSS_BIND_POSE: dict[str, tuple[tuple[float, float, float],
                                tuple[tuple[float, float, float], ...]]] = {
    "j_head": ((0.265, 0.000, 64.533), ((0.132, 0.000, 0.991), (0.991, 0.000, -0.132), (0.000, 1.000, 0.000))),
    "j_neck": ((-0.153, 0.000, 60.974), ((0.132, 0.000, 0.991), (0.991, 0.000, -0.132), (0.000, 1.000, 0.000))),
    "j_spine4": ((-0.752, 0.000, 49.172), ((0.051, 0.000, 0.999), (0.999, 0.000, -0.051), (0.000, 1.000, 0.000))),
    "j_spinelower": ((-0.711, 0.000, 40.416), ((-0.030, 0.000, 1.000), (1.000, 0.000, 0.030), (0.000, 1.000, 0.000))),
    "tag_stowed_back": ((-4.485, 0.000, 49.375), ((0.000, 1.000, 0.000), (-1.000, 0.000, 0.000), (0.000, 0.000, 1.000))),
    "tag_weapon_left": ((13.909, 18.076, 42.668), ((0.856, 0.319, -0.406), (-0.012, 0.798, 0.603), (0.516, -0.511, 0.687))),
    "tag_weapon_right": ((13.874, -17.980, 42.628), ((0.842, -0.337, -0.421), (0.016, 0.796, -0.606), (0.539, 0.503, 0.675))),
    "j_shoulder_le": ((-1.044, 7.979, 55.727), ((0.280, 0.671, -0.687), (-0.959, 0.224, -0.172), (0.039, 0.707, 0.706))),
    "j_shoulder_ri": ((-1.044, -7.979, 55.727), ((-0.280, 0.671, 0.687), (0.959, 0.224, 0.172), (-0.039, 0.707, -0.706))),
    "j_clavicle_le": ((-1.044, 2.255, 57.218), ((0.000, 0.968, -0.252), (-1.000, 0.000, 0.000), (0.000, 0.252, 0.968))),
    "j_clavicle_ri": ((-1.044, -2.255, 57.218), ((0.000, 0.968, 0.252), (1.000, 0.000, 0.000), (0.000, 0.252, -0.968))),
}

#: The bones a prop with ``tag="auto"`` may ride, the nearest at rest
#: winning: the spine chain, the head, the back and the hands.  Shoulders and
#: clavicles are left out (named only on purpose): a crossbar at shoulder
#: height would otherwise ride one clavicle and tilt with every shrug.
#: Frame check against stock: ``archetype_robot.gsc:3521`` links its wasp to
#: ``j_spine4`` at ``( 5, -15, 0 )``, which in this bind pose (x up the spine,
#: y forward, z left) is 15 behind the spine, on the back, where a carried
#: wasp belongs (assuming the robot's ``j_spine4`` is oriented as the
#: zombie's; not measured on the robot's own model).
BOSS_AUTO_BONES: tuple[str, ...] = (
    "j_head", "j_neck", "j_spine4", "j_spinelower", "tag_stowed_back",
    "tag_weapon_left", "tag_weapon_right",
)


def _axes(angles: Sequence[float]) -> tuple[tuple[float, float, float], ...]:
    """Forward, left, up of ``(pitch, yaw, roll)`` in degrees (the engine's
    ``AnglesToForward``/``Right``/``Up``, left = -right)."""
    import math
    p, y, r = (math.radians(float(a)) for a in angles)
    cp, sp, cy, sy, cr, sr = math.cos(p), math.sin(p), math.cos(y), math.sin(y), math.cos(r), math.sin(r)
    forward = (cp * cy, cp * sy, -sp)
    right = (-sr * sp * cy + cr * sy, -sr * sp * sy - cr * cy, -sr * cp)
    up = (cr * sp * cy + sr * sy, cr * sp * sy - sr * cy, cr * cp)
    return forward, (-right[0], -right[1], -right[2]), up


def _angles(forward: Sequence[float], left: Sequence[float], up: Sequence[float]) -> tuple[float, float, float]:
    """The inverse of :func:`_axes` (pitch, yaw, roll in degrees)."""
    import math
    pitch = -math.degrees(math.asin(max(-1.0, min(1.0, forward[2]))))
    if math.hypot(forward[0], forward[1]) < 1e-6:
        # Straight up or down: yaw and roll turn about the same axis, so
        # all of it goes into yaw (roll 0 makes left = (-sin yaw, cos yaw, 0)).
        return pitch, math.degrees(math.atan2(-left[0], left[1])), 0.0
    yaw = math.degrees(math.atan2(forward[1], forward[0]))
    roll = math.degrees(math.atan2(left[2], up[2]))
    return pitch, yaw, roll

BOSS_FX: dict[str, str] = {
    "powerup_on": "zm/_zm_powerups.gsc:80",
    "powerup_grabbed": "zm/_zm_powerups.gsc:82",
    "powerup_on_solo": "zm/_zm_powerups.gsc:88",
    "powerup_grabbed_solo": "zm/_zm_powerups.gsc:89",
    "powerup_on_caution": "zm/_zm_powerups.gsc:90",
    "powerup_grabbed_caution": "zm/_zm_powerups.gsc:91",
}

#: Run cycles ``set_zombie_run_cycle`` takes (``zombie_utility.gsc:2088``
#: assigns ``self.zombie_move_speed`` from them; "sprint" is the stock
#: last-zombie call, ``:2005-2006``).  A boss runs by default (sprint was too fast).
#:
#: **What could slow it down, read.**  In the stock tree the only
#: per-zombie speed writes are the spawn init (``zm/_zm_spawner.gsc:326``
#: ``init_zombie_run_cycle``, which runs before ``zombie_init_done`` at
#: ``:389``, so before the boss's setup), the last-zombie speed-up (only ever
#: to "sprint", ``zombie_utility.gsc:2003-2006``, started each round at
#: ``zm/_zm.gsc:3729``), the grief module's super sprint
#: (``zm/_zm_game_module.gsc:202``) and the level-wide
#: ``level.zombie_move_speed`` recomputed each round (``zm/_zm.gsc:4490-4494``),
#: which is read only when ``set_zombie_run_cycle()`` is called with no speed
#: (``:2092-2095`` via ``set_run_speed``), i.e. for new spawns.  All of those
#: go through ``set_zombie_run_cycle``, which the override blocks; a map's own
#: script could still assign ``zombie_move_speed`` directly, so the boss's
#: watcher re-applies the override whenever the value differs.
BOSS_SPEEDS = ("walk", "run", "sprint")

#: How many of the round's own zombies one boss is worth, before the
#: per-extra-player scaling.  ``level.zombie_health`` is the health every
#: zombie of the round spawns with (``zm/_zm_spawner.gsc:295``
#: ``self.maxhealth = level.zombie_health;``); ``ai_calculate_health``
#: (``shared/ai/zombie_utility.gsc:1906``) sets it at each round start
#: (``zm/_zm.gsc:3703``).  The target range is 30-40; 35 is the middle.
BOSS_ZOMBIE_MULTIPLE = 35.0

#: Powerup names a boss may drop.  ``full_ammo`` is the one the stock tree
#: hands ``specific_powerup_drop`` (``zm/_zm_ai_raps.gsc:590``, and three
#: more sites); the rest are names the stock powerup modules register
#: (``register_powerup( "nuke" ... )`` and so on, grep) and have
#: not been seen passed to the drop call.  Whether a usermap loads every one
#: of those modules is unverified, so ``full_ammo`` is the safe choice.
BOSS_POWERUPS = ("full_ammo", "nuke", "insta_kill", "double_points", "carpenter")

#: Sustained damage per second of one player's *best reachable* guns by a
#: round (Pack-a-Punch included where a map lets players reach it), per
#: tier, and the round each tier starts: what :attr:`BossHealth.ttk`
#: multiplies.  **Estimates, calibrated on two boss fights, not
#: measured**: the mod tools ship no weapon damage tables (``source_data``
#: has no zombies weapon GDT).  The anchor is a design target: THE
#: GRAVEDIGGER at 100,000 health solo on round 6, about 40 s of strong fire,
#: because 30,000 dies too easily to Pack-a-Punched guns (50,000 starting
#: points); that is 2,500 a second for rounds 4-9.  It agrees with zm_dmv's
#: examiner, where about 30,000 on round 8 dies too fast and five times that
#: holds.  The other tiers keep the
#: same shape (about 2x by round 10, 2.5x again by round 16).  Q6 checks
#: that a target is declared, not that it is right.
GUN_TIERS: tuple[tuple[str, int, int], ...] = (
    ("opening", 1, 800),
    ("early", 4, 2500),
    ("middle", 10, 5000),
    ("late", 16, 12000),
)
#: The time to kill every map's bosses start from: 40 s of strong fire solo
#: (the Gravedigger calibration above).  A boss may ask for longer.
BOSS_TTK = 40.0
GUN_TIER_DPS: dict[str, int] = {name: dps for name, _, dps in GUN_TIERS}

#: Live zombies (the boss and its minions count) while a boss lives, against
#: the stock 24 (``zm/_zm.gsc:337-339``; the spawner waits while
#: ``get_current_zombie_count() >= level.zombie_ai_limit``, ``:3735``).
BOSS_FIGHT_ZOMBIE_LIMIT = 10

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def gun_tier(round_number: int) -> str:
    """The gun tier players are assumed to have by ``round_number``."""
    tier = GUN_TIERS[0][0]
    for name, first, _ in GUN_TIERS:
        if round_number >= first:
            tier = name
    return tier


def present_count_lines(var: str) -> list[str]:
    """GSC that sets ``var`` to the players present (``sessionstate ==
    "playing"``, at least 1): the count a boss scales by (Q5), as
    :func:`zmforge.script.quest.present_players_lines` counts a step's."""
    return [
        f"{var} = 0;",
        "a_all_p = getplayers();",
        "for ( k = 0; k < a_all_p.size; k++ )",
        "{",
        '	if ( isdefined( a_all_p[ k ] ) && a_all_p[ k ].sessionstate == "playing" )',
        "	{",
        f"		{var}++;",
        "	}",
        "}",
        f"if ( {var} < 1 )",
        "{",
        f"	{var} = 1;",
        "}",
    ]


def stock_zombie_health(round_number: int, *, start: int = 150, increase: int = 100,
                        multiplier: float = 0.1) -> int:
    """``level.zombie_health`` for a round, as ``ai_calculate_health``
    (``shared/ai/zombie_utility.gsc:1906-1929``) computes it from the stock
    ``zombie_vars`` (``zm/_zm.gsc:1209-1211``: increase 100, multiplier
    0.1, start 150).  For tuning only; the game uses its own value."""
    health = start
    for i in range(2, int(round_number) + 1):
        if i >= 10:
            health += int(health * multiplier)
        else:
            health = int(health + increase)
    return health


@dataclass(frozen=True, kw_only=True)
class BossHealth:
    """``(base + per_round * round + zombie_multiple * level.zombie_health)
    * (1 + per_extra_player * (players - 1))``, read when the boss spawns.

    ``level.zombie_health`` is the round's own zombie health
    (``shared/ai/zombie_utility.gsc:1906-1929``), so the default
    ``zombie_multiple`` (:data:`BOSS_ZOMBIE_MULTIPLE`, 35) means "as tough as
    thirty-five of this round's zombies" and is the whole of the default
    health; ``base`` and ``per_round`` are optional extras on top."""

    base: int = 0
    per_round: int = 0
    zombie_multiple: float = BOSS_ZOMBIE_MULTIPLE
    per_extra_player: float = 0.75
    #: The most health a boss spawns with, whatever the round (G4:
    #: zm_dmv's examiner was about 1.1 million at round 8 with 8
    #: players).  With a ``ttk`` it caps the *solo* health and scales with
    #: the players like the health does, so it never clips a full lobby
    #: (100,000 solo must be 625,000 for eight).
    #: Without one it caps the total, as before.  ``None`` is uncapped.
    cap: int | None = 250_000
    #: Time to kill, in seconds of one player's sustained fire with the guns
    #: they can have by then (:data:`GUN_TIERS`).  When set, the health is
    #: ``ttk * dps * (1 + per_extra_player * (present - 1))`` and ``base``,
    #: ``per_round`` and ``zombie_multiple`` are not used: health follows the
    #: guns, not the zombies' own health, which grows 10% a round from round
    #: 10 while a wall gun does not, so a boss sized off the zombies outgrows
    #: every gun a player has before Pack-a-Punch.  A full lobby of
    #: four kills it in about 0.8x ``ttk``.  Q6 requires one on every boss.
    ttk: float | None = None
    #: The gun tier the ``ttk`` is measured against; ``None`` picks it from
    #: the round the boss spawns on (:func:`gun_tier`).
    tier: str | None = None
    #: A fixed health that overrides the formula: no round, no player-count
    #: scaling and no :attr:`cap`.  For test maps that measure how long a
    #: given number takes to kill; a ``ttk`` set with it
    #: is only the declared target (Q6), it no longer sets the health.
    fixed: int | None = None

    def __post_init__(self) -> None:
        if min(self.base, self.per_round, self.zombie_multiple, self.per_extra_player) < 0:
            raise ValueError("boss health terms are not negative")
        if self.fixed is not None and self.fixed < 1:
            raise ValueError("a fixed boss health is at least 1")
        if not (self.base or self.per_round or self.zombie_multiple or self.ttk or self.fixed):
            raise ValueError("a boss needs some health")
        if self.cap is not None and self.cap < 1:
            raise ValueError("a boss health cap is at least 1")
        if self.ttk is not None:
            if self.ttk <= 0:
                raise ValueError("a time-to-kill target is positive seconds")
            if self.base or self.per_round:
                raise ValueError("a time-to-kill health has no base or per_round terms")
        if self.tier is not None:
            if self.tier not in GUN_TIER_DPS:
                raise ValueError(f"gun tier {self.tier!r}: one of {sorted(GUN_TIER_DPS)}")
            if self.ttk is None:
                raise ValueError("a gun tier goes with a ttk")

    def dps_lines(self, var: str) -> list[str]:
        """GSC that sets ``var`` to the tier's damage per second, from the
        round when no tier is named."""
        if self.tier is not None:
            return [f"{var} = {GUN_TIER_DPS[self.tier]};"]
        out = [f"{var} = {GUN_TIERS[0][2]};"]
        for _, first, dps in GUN_TIERS[1:]:
            out += [f"if ( level.round_number >= {first} )", "{", f"	{var} = {dps};", "}"]
        return out

    def cap_lines(self, var: str) -> list[str]:
        """GSC that holds ``var`` at :attr:`cap` (an ``if``: the checker's
        symbol table knows no ``min``)."""
        if self.cap is None:
            return []
        return [f"if ( {var} > {int(self.cap)} )", "{", f"\t{var} = {int(self.cap)};", "}"]

    def health_lines(self, var: str, players: str = "n_present", dps: str = "n_dps") -> list[str]:
        """GSC that sets ``var`` to the boss's health: the solo figure,
        capped, then scaled by the players present (with a ``ttk``); or the
        old formula with the cap on the total.  :attr:`fixed` overrides all
        of it."""
        if self.fixed is not None:
            return [f"{var} = {int(self.fixed)};"]
        if self.ttk is None:
            return [f"{var} = {self.expression(players, dps)};", *self.cap_lines(var)]
        out = [f"{var} = int( {float(self.ttk):g} * {dps} );", *self.cap_lines(var)]
        if self.per_extra_player:
            out.append(f"{var} = int( {var} * ( 1 + {float(self.per_extra_player):g} * "
                       f"( {players} - 1 ) ) );")
        return out

    def expression(self, players: str = "n_present", dps: str = "n_dps") -> str:
        """The uncapped health; :meth:`cap_lines` applies the cap.
        ``players`` is the GSC count of players present
        (:func:`present_count_lines`), ``dps`` the tier's damage per second
        (:meth:`dps_lines`, used only with a ``ttk``)."""
        if self.ttk is not None:
            scale = (f" * ( 1 + {float(self.per_extra_player):g} * ( {players} - 1 ) )"
                     if self.per_extra_player else "")
            return f"int( {float(self.ttk):g} * {dps}{scale} )"
        parts = [str(int(self.base))] if self.base else []
        if self.per_round:
            parts.append(f"{int(self.per_round)} * level.round_number")
        if self.zombie_multiple:
            parts.append(f"int( {float(self.zombie_multiple):g} * level.zombie_health )")
        total = " + ".join(parts)
        if self.per_extra_player:
            return (f"int( ( {total} ) * ( 1 + {float(self.per_extra_player):g} * "
                    f"( {players} - 1 ) ) )")
        return total

    def at(self, round_number: int, players: int, zombie_health: int | None = None) -> int:
        """What :meth:`expression` evaluates to, for tests and tuning.
        ``zombie_health`` defaults to the stock value for the round
        (:func:`stock_zombie_health`)."""
        if self.fixed is not None:
            return int(self.fixed)
        if self.ttk is not None:
            dps = GUN_TIER_DPS[self.tier or gun_tier(round_number)]
            solo = int(self.ttk * dps)
            if self.cap is not None:
                solo = min(solo, int(self.cap))
            return int(solo * (1 + self.per_extra_player * (players - 1)))
        if zombie_health is None:
            zombie_health = stock_zombie_health(round_number)
        total = (self.base + self.per_round * round_number
                 + int(self.zombie_multiple * zombie_health))
        value = int(total * (1 + self.per_extra_player * (players - 1)))
        return value if self.cap is None else min(value, int(self.cap))


@dataclass(frozen=True)
class BossProp:
    """A model worn by the boss: a ``script_model`` linked to one of the
    actor's bones, so it moves with the animation.  ``offset`` is forward, left, up
    from the feet in the boss's own frame; ``angles`` pitch, yaw, roll on top
    of the boss's facing.  The model must be a declared xmodel on the install
    (check Z13); the boss script declares it in the zone.

    ``tag`` (a key of :data:`BOSS_BIND_POSE`) is the bone it rides (a
    pumpkin on ``j_head`` nods, a shovel on ``tag_weapon_right`` swings with
    the hand); ``"auto"``, the default, is the :data:`BOSS_AUTO_BONES` bone
    nearest ``offset`` at rest.  ``offset`` and ``angles`` still say where it
    sits with the zombie at rest, in the boss frame; :meth:`link` turns that
    into the bone's own frame.

    WHY not ``tag_origin``: a prop on the
    feet tag stays at its rest height while the zombie runs hunched and
    bobbing, so the corn maze Scarecrow's pumpkin would float above the
    zombie's own head and its board hang off the shoulders; ``tag_origin``
    is refused."""

    model: str
    offset: tuple[float, float, float] = (0.0, 0.0, 60.0)
    angles: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0
    tag: str = "auto"

    def __post_init__(self) -> None:
        if not re.match(r"^[A-Za-z0-9_]+$", self.model):
            raise ValueError(f"prop model {self.model!r} is not an xmodel name")
        if not 0.1 <= self.scale <= 4.0:
            raise ValueError(f"prop scale {self.scale} out of 0.1-4")
        if self.tag != "auto" and self.tag not in BOSS_BIND_POSE:
            raise ValueError(f"prop tag {self.tag!r}: auto or one of {sorted(BOSS_BIND_POSE)} "
                             "(tag_origin is refused: a prop on the feet floats off the body)")

    @property
    def bone(self) -> str:
        """The bone it is linked to: ``tag``, or the nearest auto bone at rest."""
        if self.tag != "auto":
            return self.tag
        return min(BOSS_AUTO_BONES, key=lambda b: sum(
            (self.offset[i] - BOSS_BIND_POSE[b][0][i]) ** 2 for i in range(3)))

    def link(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """``(offset, angles)`` for ``LinkTo( boss, bone, offset, angles )``."""
        at, axes = BOSS_BIND_POSE[self.bone]
        rel = [self.offset[i] - at[i] for i in range(3)]
        local = tuple(round(sum(a[i] * rel[i] for i in range(3)), 2) for a in axes)
        own = _axes(self.angles)  # the prop's forward, left, up, boss frame
        f, l, u = ([sum(v[i] * a[i] for i in range(3)) for a in axes] for v in own)
        angles = tuple(round(x, 2) + 0.0 for x in _angles(f, l, u))
        return local, angles  # type: ignore[return-value]


@dataclass(frozen=True, kw_only=True)
class Boss:
    key: str
    name: str
    spawn_at: tuple[float, float, float]
    arrives: str
    defeated: str
    yaw: float = 0.0
    #: Snap the boss (and each minion spot) to the nearest navmesh point
    #: within this many units of ``spawn_at`` before it appears, so a boss
    #: that climbs off a prop (a scarecrow's post) can path
    #: (``GetClosestPointOnNavMesh``, ``zm/_zm_behavior.gsc:320``); the
    #: arrival quake and effect play there.  ``None`` teleports to the point
    #: as given and emits what it did before.
    spawn_snap: float | None = None
    health: BossHealth = field(default_factory=BossHealth)
    #: How fast it moves: a tanky boss is slower, not faster (a
    #: forced sprint is too fast for THE GRAVEDIGGER at round 6: run, not
    #: sprint).  ``hurt_speed`` (optional) is a
    #: second phase: the speed once ``hurt_at`` of its health is gone
    #: (``None``, the default: it never changes).
    speed: str = "run"
    hurt_speed: str | None = None
    hurt_at: float = 0.5
    #: Armour: while its minions live the boss takes only this share of the
    #: damage (``self.actor_damage_func``, the stock per-actor hook
    #: ``zm/_zm.gsc:5746-5748``, set on an actor at ``zm/_zm_clone.gsc:79``),
    #: for at most ``armour_seconds`` so a stuck minion never makes it
    #: unkillable.  ``exposed`` is said to everyone when the armour drops
    #: (``None``: a line from the name).  ``armour=None``: no armour.
    armour: float | None = None
    armour_seconds: float = 45.0
    exposed: str | None = None
    #: The body glow, played once on every tag of ``glow_tags``.  Red by
    #: default (:data:`BOSS_RED_FX`); a stock powerup name is still allowed.
    glow_fx: str | None = "zmf_boss_aura"
    glow_tags: tuple[str, ...] = BOSS_GLOW_TAGS
    pulse_fx: str | None = "zmf_boss_burst"
    #: A fire that burns on every ``glow_tags`` tag for the boss's whole life,
    #: and a lightning strike where it arrives (:data:`BOSS_LOUD_FX`).
    fire_fx: str | None = "zmf_boss_fire"
    arrive_fx: str | None = "zmf_boss_arrive"
    #: What the boss wears: its silhouette, per map.  Empty: glow only.
    props: tuple[BossProp, ...] = ()
    #: Take the zombie's own head off so a prop on ``j_head`` *is* its head
    #: (a pumpkin head), the way the stock head gib does it: eyes off, then
    #: ``Detach( self.head, "" )`` (``zombie_utility.gsc:2966-2972`` ->
    #: ``systems/gib.gsc:227-230``, ``self.head`` being the head model name
    #: per ``gib.gsh:5``).  It also sets ``no_gib`` (the stock off switch,
    #: ``zombie_utility.gsc:2499``, ``:2960``, set by ``mechz.gsc:951``) and
    #: ``disable_head_gib`` (``:2968``) so nothing gibs it again or swaps its
    #: torso model from under the props.  Default off.  Unverified in play.
    headless: bool = False
    #: A red skull waypoint over the boss while it lives (:data:`BOSS_MARKER`).
    marker: bool = True
    minions: int = 0
    minion_spread: float = 64.0
    points: int = 0
    powerup: str | None = None
    quake: bool = True
    #: Live zombies allowed while this boss lives (``level.zombie_ai_limit``,
    #: the boss and minions included), put back when the last boss dies, so
    #: the fight is with the boss and not the horde (a common Workshop
    #: complaint is a boss fight that is mostly zombies).  ``None``
    #: keeps normal spawns, on purpose (Q6 then only notes it).
    fight_zombie_limit: int | None = BOSS_FIGHT_ZOMBIE_LIMIT

    def __post_init__(self) -> None:
        if not _KEY.match(self.key):
            raise ValueError(f"boss key {self.key!r} must be [a-z][a-z0-9_]*")
        if self.speed not in BOSS_SPEEDS:
            raise ValueError(f"boss speed {self.speed!r}: one of {BOSS_SPEEDS}")
        for fx in (self.glow_fx, self.pulse_fx):
            if fx is not None and fx not in BOSS_FX and fx not in BOSS_RED_FX:
                raise ValueError(f"{fx!r} is not a stock effect name "
                                 f"({sorted(BOSS_FX) + sorted(BOSS_RED_FX)})")
        if self.fire_fx is not None and self.fire_fx != "zmf_boss_fire":
            raise ValueError("fire_fx is the hellhound fire or None")
        if self.arrive_fx is not None and self.arrive_fx != "zmf_boss_arrive":
            raise ValueError("arrive_fx is the hellhound lightning or None")
        if self.glow_fx and not self.glow_tags:
            raise ValueError("a glow needs at least one tag")
        if self.powerup is not None and self.powerup not in BOSS_POWERUPS:
            raise ValueError(f"powerup {self.powerup!r}: one of {BOSS_POWERUPS}")
        if self.minions < 0 or self.points < 0:
            raise ValueError("minions and points are counts")
        for sp in (self.speed, self.hurt_speed):
            if sp is not None and sp not in BOSS_SPEEDS:
                raise ValueError(f"boss speed {sp!r}: one of {BOSS_SPEEDS}")
        if not 0.0 < self.hurt_at < 1.0:
            raise ValueError("hurt_at is a share of the health, between 0 and 1")
        if self.armour is not None:
            if not 0.0 < self.armour < 1.0:
                raise ValueError("armour is the share of damage taken, between 0 and 1")
            if not self.minions:
                raise ValueError("armour lasts while the minions live: it needs minions")
            if self.armour_seconds <= 0:
                raise ValueError("armour_seconds > 0")
        if self.fight_zombie_limit is not None and self.fight_zombie_limit < 1 + self.minions:
            raise ValueError("fight_zombie_limit leaves room for the boss and its minions")

    @property
    def spawn_function(self) -> str:
        return f"zmf_boss_{self.key}_spawn"

    @property
    def dead_notify(self) -> str:
        return f"zmf_boss_{self.key}_dead"


def boss_strings(boss: Boss) -> dict[str, str]:
    """The boss's own lines, reference -> text (all ``string`` kind)."""
    out = {
        f"BOSS_{boss.key.upper()}_ARRIVES": boss.arrives,
        f"BOSS_{boss.key.upper()}_DEFEATED": boss.defeated,
    }
    if boss.armour is not None:
        out[f"BOSS_{boss.key.upper()}_EXPOSED"] = (
            boss.exposed or f"{boss.name}'s minions are down. Now it can be hurt.")
    return out


def _say_all(asset: str) -> list[str]:
    return [
        "a_players = getplayers();",
        "for ( i = 0; i < a_players.size; i++ )",
        "{",
        f'\ta_players[ i ] IPrintLnBold( &"{asset}" );',
        "}",
    ]


#: Boss props are made ``NotSolid``.  Every prop a boss wears has bullet
#: collision of its own (``BulletCollisionLOD`` in its gdt: the 2x4 board,
#: the caution sign, the hanging clothes and the shovel, read)
#: and a ``spawn( "script_model" )`` keeps it, so a sign over the chest took
#: the shots meant for the boss.  ``NotSolid`` is the stock call for a
#: decorative script model (``grep -c NotSolid`` over ``scripts/zm``: 10).
BOSS_PROPS_NOT_SOLID = True


def _arrival_lines(var: str, at: str, yaw: float) -> list[str]:
    """The boss's spawn point: :func:`zmforge.script.tricks.spawn_point_lines`,
    whose docstring has the measured why (a teleport after the spawn sent the
    boss to a random riser)."""
    return spawn_point_lines(var, at, yaw)


def boss_script(boss: Boss, assets: dict[str, str]) -> CustomScript:
    """The boss's functions.  ``assets`` maps :func:`boss_strings`' references
    to shipped asset names.  Nothing is started: a caller runs
    ``ai = zmf_boss_<key>_spawn();`` (it returns ``undefined`` if the spawner
    is missing or full) and the boss's own death thread pays out and
    notifies ``level`` ``zmf_boss_<key>_dead``."""
    k = boss.key
    up = k.upper()
    arrives = assets[f"BOSS_{up}_ARRIVES"]
    defeated = assets[f"BOSS_{up}_DEFEATED"]
    at = _vector(boss.spawn_at)
    red = [
        line
        for name in _own_fx_names(boss)
        for line in (
            f'if ( !isdefined( level._effect[ "{name}" ] ) )',
            "{",
            f'\tlevel._effect[ "{name}" ] = "{BOSS_OWN_FX[name]}";',
            "}",
        )
    ]
    spawn = [
        *red,
        "if ( !isdefined( level.zombie_spawners ) || level.zombie_spawners.size < 1 )",
        "{",
        "\treturn undefined;",
        "}",
        "e_spawner = level.zombie_spawners[ 0 ];",
        "e_spawner.script_forcespawn = 1;",
        "if ( !isdefined( level.check_for_instakill_override ) )",
        "{",
        f"\tlevel.check_for_instakill_override = &zmf_boss_{k}_instakill_check;",
        "}",
        # Only a player may kill a boss: the stock
        # damage callbacks run before the kill (_zm.gsc:5851-5862).
        f"if ( !isdefined( level.zmf_boss_{k}_guarded ) )",
        "{",
        f"\tlevel.zmf_boss_{k}_guarded = true;",
        f"\tzm::register_zombie_damage_override_callback( &zmf_boss_{k}_guard_damage );",
        "}",
        f"v_at = {at};",
        *((f"v_nav = GetClosestPointOnNavMesh( v_at, {float(boss.spawn_snap):g} );",
           "if ( isdefined( v_nav ) )", "{", "\tv_at = v_nav;", "}")
          if boss.spawn_snap is not None else ()),
        # Hand the arena to the stock spawn-location code instead of
        # teleporting after it (see _arrival_lines).
        *_arrival_lines("s_at", "v_at", boss.yaw),
        f'ai = zombie_utility::spawn_zombie( e_spawner, "zmf_boss_{k}", s_at );',
        "if ( !isdefined( ai ) )",
        "{",
        "\treturn undefined;",
        "}",
        "ai.zmf_boss_guard = true;",
        "ai.ignore_round_spawn_failsafe = true;",
        # A map can put its own staging away the moment the boss is there
        # (Harvest Moon's scarecrow figure leaves its post).
        f'level notify( "zmf_boss_{k}_spawned" );',
        f"ai thread zmf_boss_{k}_setup();",
        f"ai thread zmf_boss_{k}_death();",
        # The fight is with the boss: fewer normal zombies while any boss
        # lives (the spawner reads the limit every spawn, _zm.gsc:3735, and
        # nothing else writes it after init, :337-339), put back by the last
        # boss's death thread.  Special rounds wait until it is dead.
        "if ( !isdefined( level.zmf_boss_live ) || level.zmf_boss_live < 1 )",
        "{",
        "\tlevel.zmf_boss_live = 0;",
        "\tlevel.zmf_boss_ai_limit = level.zombie_ai_limit;",
        "}",
        "level.zmf_boss_live++;",
        *((f"if ( level.zombie_ai_limit > {int(boss.fight_zombie_limit)} )", "{",
           f"\tlevel.zombie_ai_limit = {int(boss.fight_zombie_limit)};", "}")
          if boss.fight_zombie_limit is not None else
          ("// boss fight keeps normal spawns (fight_zombie_limit None)",)),
        f"level thread zmf_boss_{k}_hold( ai );",
        *_say_all(arrives),
    ]
    here = "v_at"
    if boss.quake:
        spawn.append(f"Earthquake( 0.35, 2, {here}, 1500 );")
    if boss.arrive_fx:
        spawn.append(f'PlayFX( level._effect[ "{boss.arrive_fx}" ], {here} );')
    if boss.armour is not None:
        spawn[spawn.index(f"ai thread zmf_boss_{k}_setup();"):
              spawn.index(f"ai thread zmf_boss_{k}_setup();")] = [
            f"level.zmf_boss_{k}_adds = 0;",
            f"level.zmf_boss_{k}_adds_seen = 0;",
            f"level.zmf_boss_{k}_armour_until = gettime() + {int(round(boss.armour_seconds * 1000))};",
        ]
    if boss.minions:
        spawn.append(f"level thread zmf_boss_{k}_minions();")
    if boss.armour is not None:
        spawn.append(f"level thread zmf_boss_{k}_exposed( ai );")
    spawn.append("return ai;")

    setup = [
        'self endon( "death" );',
        "while ( !isdefined( self.zombie_init_done ) )",
        "{",
        "\twait 0.05;",
        "}",
        *present_count_lines("n_present"),
        *(boss.health.dps_lines("n_dps") if boss.health.ttk is not None else ()),
        *((f"self.zmf_boss_ttk = {float(boss.health.ttk):g};",)
          if boss.health.ttk is not None else ()),
        *boss.health.health_lines("n_health"),
        "self.maxhealth = n_health;",
        "self.health = n_health;",
        "self.no_powerups = true;",
        "self.ignore_nuke = true;",
        # G2: no one-shot kill with Insta-Kill up (see the module docstring).
        "self.zmf_no_instakill = true;",
        f"self.instakill_func = &zmf_boss_{k}_no_instakill;",
        "self.b_ignore_cleanup = true;",
        f'self.zmf_boss_speed = "{boss.speed}";',
        f'self zombie_utility::set_zombie_run_cycle_override_value( "{boss.speed}" );',
        "self.zombie_move_speed_original = self.zombie_move_speed;",
        *((f"self.actor_damage_func = &zmf_boss_{k}_armour;",) if boss.armour is not None else ()),
        f"self thread zmf_boss_{k}_speed();",
        f"self thread zmf_boss_{k}_guard();",
    ]
    hurt = [] if boss.hurt_speed is None or boss.hurt_speed == boss.speed else [
        # Phase two: hurt past hurt_at, it speeds up (walk, then run).
        f"\tif ( !isdefined( self.zmf_boss_hurt ) && self.maxhealth > 0 && "
        f"self.health < self.maxhealth * {float(boss.hurt_at):g} )",
        "\t{",
        "\t\tself.zmf_boss_hurt = 1;",
        f'\t\tself.zmf_boss_speed = "{boss.hurt_speed}";',
        "\t}",
    ]
    keep_speed = [
        'self endon( "death" );',
        "while ( isalive( self ) )",
        "{",
        *hurt,
        "\tif ( !isdefined( self.zombie_move_speed ) || self.zombie_move_speed != self.zmf_boss_speed )",
        "\t{",
        "\t\tself.zombie_move_speed_override = undefined;",
        "\t\tself zombie_utility::set_zombie_run_cycle_override_value( self.zmf_boss_speed );",
        "\t\tself.zombie_move_speed_original = self.zombie_move_speed;",
        "\t}",
        "\twait 1;",
        "}",
    ]
    if boss.headless:
        setup += [
            "// headless: the head prop is its head (see Boss.headless)",
            "self.no_gib = true;",
            "self.disable_head_gib = true;",
            "self zombie_utility::zombie_eye_glow_stop();",
            "if ( isdefined( self.head ) )",
            "{",
            '\tself Detach( self.head, "" );',
            "}",
            # and its hat, as the stock hat gib does (zombie_utility.gsc:2707-2709)
            "if ( isdefined( self.hatmodel ) )",
            "{",
            '\tself Detach( self.hatmodel, "" );',
            "}",
        ]
    if boss.props:
        setup.append("self.zmf_boss_props = [];")
        for n, prop in enumerate(boss.props):
            setup += [
                f'e_prop = spawn( "script_model", self.origin + {_vector(prop.offset)} );',
                f'e_prop SetModel( "{prop.model}" );',
            ]
            if prop.scale != 1.0:
                setup.append(f"e_prop SetScale( {float(prop.scale):g} );")
            offset, angles = prop.link()
            setup += [
                # Worn, not furniture: no bullet or movement collision (see
                # BOSS_PROPS_NOT_SOLID).
                "e_prop NotSolid();",
                f'e_prop LinkTo( self, "{prop.bone}", {_vector(offset)}, {_vector(angles)} );',
                f"self.zmf_boss_props[ {n} ] = e_prop;",
            ]
    if boss.marker:
        setup += [
            "// level-wide HUD: the boss's waypoint is for every player (Q4)",
            "self.zmf_boss_marker = NewHudElem();",
            "self.zmf_boss_marker.z = 96;",  # above the head and props, from the feet
            "self.zmf_boss_marker.alpha = 0.9;",
            "self.zmf_boss_marker.color = ( 1, 0.1, 0.1 );",
            f'self.zmf_boss_marker setShader( "{BOSS_MARKER}", 12, 12 );',
            "self.zmf_boss_marker setwaypoint( true );",
            "self.zmf_boss_marker SetTargetEnt( self );",
        ]
    if boss.glow_fx:
        for tag in boss.glow_tags:
            setup.append(f'PlayFXOnTag( level._effect[ "{boss.glow_fx}" ], self, "{tag}" );')
    if boss.fire_fx:
        for tag in boss.glow_tags:
            setup.append(f'PlayFXOnTag( level._effect[ "{boss.fire_fx}" ], self, "{tag}" );')
    if boss.pulse_fx:
        setup += [
            "while ( isalive( self ) )",
            "{",
            f'\tPlayFX( level._effect[ "{boss.pulse_fx}" ], self.origin + ( 0, 0, 36 ) );',
            "\twait 1;",
            "}",
        ]

    death = [
        f'self waittill( "death", e_attacker );',
        "v_at = self.origin;",
        "level.zmf_boss_live--;",
        "if ( level.zmf_boss_live < 1 )",
        "{",
        "\tlevel.zmf_boss_live = 0;",
        "\tlevel.zombie_ai_limit = level.zmf_boss_ai_limit;",
        "}",
    ]
    if boss.marker:
        death += [
            "if ( isdefined( self.zmf_boss_marker ) )",
            "{",
            "\tself.zmf_boss_marker Destroy();",
            "}",
        ]
    if boss.props:
        death += [
            "if ( isdefined( self.zmf_boss_props ) )",
            "{",
            "\tfor ( i = 0; i < self.zmf_boss_props.size; i++ )",
            "\t{",
            "\t\tif ( isdefined( self.zmf_boss_props[ i ] ) )",
            "\t\t{",
            "\t\t\tself.zmf_boss_props[ i ] delete();",
            "\t\t}",
            "\t}",
            "}",
        ]
    if boss.pulse_fx:
        death.append(f'PlayFX( level._effect[ "{boss.pulse_fx}" ], v_at + ( 0, 0, 40 ) );')
    death += _say_all(defeated)
    if boss.points:
        death += [
            "for ( i = 0; i < a_players.size; i++ )",
            "{",
            f"\ta_players[ i ] zm_score::add_to_player_score( {int(boss.points)} );",
            "}",
        ]
    if boss.powerup:
        death.append(f'level thread zm_powerups::specific_powerup_drop( "{boss.powerup}", v_at );')
    death.append(f'level notify( "{boss.dead_notify}" );')

    functions = [
        CustomFunction(
            boss.spawn_function, tuple(spawn),
            purpose=(f"Spawn {boss.name}: one stock zombie (spawn_zombie,\n"
                     "zombie_utility.gsc:1454) at the arena through its spawn_point\n"
                     "(move_zombie_spawn_location, _zm_utility.gsc:188), so the stock\n"
                     "spawn code does not move it to a random riser. Returns the AI\n"
                     "or undefined."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_setup", tuple(setup),
            purpose=("After the stock init (zombie_init_done, _zm_spawner.gsc:389)\n"
                     "raise health as _zm_ai_raps.gsc:980-988 does; lock the run\n"
                     "cycle (set_zombie_run_cycle_override_value,\n"
                     "zombie_utility.gsc:2060); wear the props (script_model LinkTo,\n"
                     "_hunter.gsc:1605), a skull waypoint (entityheadicons_shared.gsc:\n"
                     "156-165), a red glow on head, chest and hips (PlayFXOnTag,\n"
                     "_zm_traps.gsc:1025) and pulse."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_instakill_check",
            (
                "if ( isdefined( self.zmf_no_instakill ) && self.zmf_no_instakill )",
                "{",
                "\treturn false;",
                "}",
                'return level.zombie_vars[ player.team ][ "zombie_insta_kill" ] || '
                "( isdefined( player.personal_instakill ) && player.personal_instakill );",
            ),
            params=("player",),
            purpose=("level.check_for_instakill_override (_zm_powerups.gsc:1440-1445):\n"
                     "false for a boss (no kill), else the stock insta-kill test (:1467)."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_no_instakill", ("return true;",),
            params=("player", "mod", "hit_location"),
            purpose="The stock per-entity veto (instakill_func, _zm_powerups.gsc:1474-1481).",
        ),
        CustomFunction(
            f"zmf_boss_{k}_speed", tuple(keep_speed),
            purpose=(f"Keep {boss.name} at \"{boss.speed}\": the override makes stock\n"
                     "set_zombie_run_cycle calls a no-op (zombie_utility.gsc:2078-2082);\n"
                     "re-apply it if anything writes zombie_move_speed directly."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_guard",
            (
                'self endon( "death" );',
                "while ( isalive( self ) )",
                "{",
                "\tself.lastchunk_destroy_time = gettime();",
                '\tif ( self.origin[ 2 ] < level.zombie_vars[ "below_world_check" ] )',
                "\t{",
                f"\t\tself forceteleport( {at}, ( 0, {float(boss.yaw):g}, 0 ) );",
                "\t}",
                "\twait 1;",
                "}",
            ),
            purpose=("Keep the stock stuck failsafe off the boss: round_spawn_failsafe\n"
                     "(zombie_utility.gsc:1805-1893) kills any zombie that moved under\n"
                     "24 units in 30 s or fell below the world, with no attacker, and it\n"
                     "reads ignore_round_spawn_failsafe only before its first wait; a\n"
                     "lastchunk_destroy_time under 8 s old skips both checks (:1850-1854).\n"
                     "A boss that fell out of the world goes back to its arena."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_guard_damage",
            (
                "if ( !( isdefined( self.zmf_boss_guard ) && self.zmf_boss_guard ) )",
                "{",
                "\treturn;",
                "}",
                "b_player = isplayer( attacker ) || ( isdefined( attacker ) && "
                "isdefined( attacker.owner ) && isplayer( attacker.owner ) );",
                "self.dont_die_on_me = ( willbekilled && !b_player );",
            ),
            params=("willbekilled", "inflictor", "attacker", "damage", "flags",
                    "meansofdeath", "weapon", "vpoint", "vdir", "shitloc",
                    "psoffsettime", "boneindex", "surfacetype"),
            purpose=("Only a player (or a player's turret) may kill a boss. A\n"
                     "zombie_damage_override_callbacks entry (_zm.gsc:5851-5857) runs\n"
                     "before the kill; dont_die_on_me drops a lethal hit (:5859) from\n"
                     "the stuck failsafe, a door closing on it (kill_trapped_zombies,\n"
                     "_zm_blockers.gsc:636), a trap or an unowned explosion."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_hold",
            (
                'level endon( "end_game" );',
                'ai endon( "death" );',
                "while ( true )",
                "{",
                '\tlevel waittill( "end_of_round" );',
                *("\t" + line for line in hold_special_lines()),
                "}",
            ),
            params=("ai",),
            purpose=("No special round while the boss lives: at each round end push the\n"
                     "next dog round past the coming round (dog_round_tracker starts one\n"
                     "at between_round_over when round_number == next_dog_round,\n"
                     "_zm_ai_dogs.gsc:490-501; end_of_round comes first, _zm.gsc:4449)."),
        ),
        CustomFunction(
            f"zmf_boss_{k}_death", tuple(death),
            purpose=("On death drop the marker and props, then pay out: points\n"
                     "(zm_score::add_to_player_score) and a drop\n"
                     "(specific_powerup_drop, _zm_ai_raps.gsc:590)."),
        ),
    ]
    using = [_ZOMBIE_UTILITY, _ZM]
    if boss.points:
        using.append(_SCORE)
    if boss.powerup:
        using.append(_POWERUPS)
    if boss.minions:
        spots = _ring(boss.spawn_at, boss.minions, boss.minion_spread)
        body = [
            'level endon( "end_game" );',
            "e_spawner = level.zombie_spawners[ 0 ];",
            "e_spawner.script_forcespawn = 1;",
            "a_spots = [];",
        ]
        body += [f"a_spots[ {n} ] = {_vector(s)};" for n, s in enumerate(spots)]
        body += [
            "for ( i = 0; i < a_spots.size; i++ )",
            "{",
            "\tv_spot = a_spots[ i ];",
            *((f"\tv_nav = GetClosestPointOnNavMesh( v_spot, {float(boss.spawn_snap):g} );",
               "\tif ( isdefined( v_nav ) )", "\t{", "\t\tv_spot = v_nav;", "\t}")
              if boss.spawn_snap is not None else ()),
            *("\t" + line for line in _arrival_lines("s_spot", "v_spot", boss.yaw)),
            f'\tai = zombie_utility::spawn_zombie( e_spawner, "zmf_boss_{k}_minion", s_spot );',
            "\tif ( !isdefined( ai ) )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            *((f"\tlevel.zmf_boss_{k}_adds++;", f"\tlevel.zmf_boss_{k}_adds_seen++;",
               f"\tai thread zmf_boss_{k}_add_death();") if boss.armour is not None else ()),
            "}",
        ]
        functions.append(CustomFunction(
            f"zmf_boss_{k}_minions", tuple(body),
            purpose=f"{boss.minions} ordinary zombies around {boss.name}, as closet_ambush spawns.",
        ))
    if boss.armour is not None:
        exposed = assets[f"BOSS_{up}_EXPOSED"]
        functions += [
            CustomFunction(
                f"zmf_boss_{k}_armour",
                (
                    f"if ( level.zmf_boss_{k}_adds > 0 && gettime() < level.zmf_boss_{k}_armour_until )",
                    "{",
                    f"\treturn int( damage * {float(boss.armour):g} );",
                    "}",
                    "return damage;",
                ),
                params=("inflictor", "attacker", "damage", "flags", "meansofdeath", "weapon",
                        "vpoint", "vdir", "shitloc", "psoffsettime", "boneindex"),
                purpose=(f"Armour: {boss.name} takes {float(boss.armour):g} of the damage while its\n"
                         f"minions live, for at most {float(boss.armour_seconds):g} s. self.actor_damage_func,\n"
                         "called with these arguments at _zm.gsc:5746-5748."),
            ),
            CustomFunction(
                f"zmf_boss_{k}_add_death",
                ('self waittill( "death" );', f"level.zmf_boss_{k}_adds--;"),
                purpose="A minion died: one fewer holding up the armour.",
            ),
            CustomFunction(
                f"zmf_boss_{k}_exposed",
                (
                    'level endon( "end_game" );',
                    'ai endon( "death" );',
                    f"while ( level.zmf_boss_{k}_adds > 0 && gettime() < level.zmf_boss_{k}_armour_until )",
                    "{",
                    "\twait 0.5;",
                    "}",
                    f"if ( level.zmf_boss_{k}_adds_seen > 0 )",
                    "{",
                    *("\t" + line for line in _say_all(exposed)),
                    "}",
                ),
                params=("ai",),
                purpose=f"Tell everyone when {boss.name}'s armour drops (minions dead or time up).",
            ),
        ]
    return CustomScript(
        using=tuple(using),
        functions=tuple(functions),
        assets=tuple(sorted({("xmodel", p.model) for p in boss.props})),
        notes=(f"mini-boss {boss.name} ({boss.key})",),
    )


def hold_special_lines() -> list[str]:
    """GSC, run on ``end_of_round``, that keeps the coming round from being a
    special round: the stock dog tracker starts one at
    ``between_round_over`` when ``level.round_number ==
    level.next_dog_round`` (``zm/_zm_ai_dogs.gsc:490-501``), and
    ``end_of_round`` (``zm/_zm.gsc:4449``) comes before the round number
    goes up (``:4497``, ``:4551``) and ``between_round_over`` (``:4555``).
    Idempotent, so several holders may run it.  Dogs are the only special
    round a usermap has (``docs/special-enemies.md``)."""
    return [
        "if ( isdefined( level.next_dog_round ) && level.next_dog_round <= level.round_number + 1 )",
        "{",
        "\tlevel.next_dog_round = level.round_number + 2;",
        "}",
    ]


def boss_fx_paths(boss: Boss) -> tuple[str, ...]:
    """The effect paths the boss registers by name (the red pair), which the
    map's own scripts must ``#precache`` as well so the handle is theirs
    (check Z50; the stock precache is ``zm/_zm_powerups.gsc:47-48`` and
    ``.csc:14``)."""
    return tuple(BOSS_OWN_FX[n] for n in _own_fx_names(boss))


def _own_fx_names(boss: Boss) -> list[str]:
    used = {boss.glow_fx, boss.pulse_fx, boss.fire_fx, boss.arrive_fx}
    return sorted(used & set(BOSS_OWN_FX))


def precache_boss_fx(bp, boss: Boss) -> None:
    """Add :func:`boss_fx_paths` to the blueprint's precache list (both the
    ``.gsc`` and ``.csc`` get a ``#precache`` line).  No manifest line: the
    effects are stock and already packed by ``_zm_powerups``."""
    for path in boss_fx_paths(boss):
        if path not in bp.script.precache_fx:
            bp.script.precache_fx.append(path)


def install_boss_rounds(bp, boss: Boss, *, rounds: Sequence[int]) -> CustomScript:
    """Ship the boss's lines and spawn it at the start of each listed round
    (``level waittill( "start_of_round" )``, ``zm/_zm.gsc:4433``)."""
    rounds = sorted({int(r) for r in rounds})
    if not rounds or rounds[0] < 1:
        raise ValueError("boss rounds are round numbers from 1")
    assets = {ref: bp.add_map_string(ref, text) for ref, text in boss_strings(boss).items()}
    precache_boss_fx(bp, boss)
    table = [f"a_rounds[ {n} ] = {r};" for n, r in enumerate(rounds)]
    schedule = CustomScript(
        functions=(CustomFunction(
            f"zmf_boss_{boss.key}_rounds",
            (
                'level endon( "end_game" );',
                "a_rounds = [];",
                *table,
                "n_due = 0;",
                "while ( true )",
                "{",
                '\tlevel waittill( "start_of_round" );',
                "\tfor ( i = 0; i < a_rounds.size; i++ )",
                "\t{",
                "\t\tif ( a_rounds[ i ] == level.round_number )",
                "\t\t{",
                "\t\t\tn_due++;",
                "\t\t}",
                "\t}",
                # Never on top of a dog round: it comes the round after.
                '\tif ( n_due > 0 && !level flag::get( "special_round" ) )',
                "\t{",
                "\t\tn_due--;",
                f"\t\tlevel thread {boss.spawn_function}();",
                "\t}",
                "}",
            ),
            purpose=(f"{boss.name} arrives at the start of rounds {', '.join(map(str, rounds))}\n"
                     "(or the next round that is not a special round)."),
        ),),
        using=(_FLAG,),
        statements=((Slot.AFTER_ENTRY, f"level thread zmf_boss_{boss.key}_rounds();"),),
    )
    from .custom import merge

    return bp.add_custom_logic(merge(boss_script(boss, assets), schedule))
