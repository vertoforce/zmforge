"""Harvest Moon's script: the hayride, the gags, the notices and the quest.

Everything here is text the player sees plus the logic that shows it, woven
into the blueprint with :meth:`~zmforge.blueprint.model.Blueprint.
add_custom_logic`.  The mechanics are the shared ones -- :mod:`zmforge.script.
hayride`, :mod:`zmforge.script.gags`, :func:`zmforge.script.tricks.
use_notices`, :mod:`zmforge.script.quest` and :mod:`zmforge.script.bosses`
-- plus two gags of this map's own, written here:

* **the scarecrows turn to face you.**  Each scarecrow is a wooden cross
  (a solid kit prop, placed by :mod:`.corn_maze_parts`) with a figure on
  top -- a carved jack-o'-lantern head and a warning sign pinned to its
  chest -- spawned by script and linked to one ``tag_origin``.  Every 0.3 s
  the figure turns (``RotateTo``) to face the nearest player within 900
  units, and the first time a player comes within 320 it says so.  The
  carved face and the sign are what make the turn readable: the cross
  stays put and the head comes round to look at you.
* **the prize pumpkins explode.**  Six giant pumpkins in the patch (the
  plain pumpkin at 2.5x, over twice the size of any other, each on a green
  glow; the signs say the giant glowing ones explode) are script models
  that take damage (``SetCanDamage``, ``shared/weapons/
  _trophy_system.gsc:367``; ``waittill( "damage", ... )``, ``shared/
  destructible_cover_shared.gsc:167``).  Shot, one plays the framework's
  default explosion (``level._effect["def_explosion"]``, registered at
  ``zm/_zm.gsc:1720`` and precached at ``:145``, played the same way at
  ``zm/_zm_blockers.gsc:440``), does ``RadiusDamage`` round itself
  (``shared/ai/raz.gsc:1637``) and tells the shooter what it was.  They
  grow back at the start of every round.

**Unverified in play:** everything on screen; that a scaled ``script_model``
of the kit pumpkin takes bullet damage at its scaled size (unscaled, its
bullet mesh is the middle 16 units); that the figure's parts follow their
base's ``RotateTo``; which end of the kit tractor reads as its front (the
small wheels are at the kit's +z, measured off tractor.obj, and yaw 90 puts
them ahead of the trailer).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from ..blueprint.catalogue import PERKS
from ..blueprint.model import Blueprint
from ..script.glow import own_object
from ..script import bosses as b
from ..script import quest as q
from ..script.custom import CustomFunction, CustomScript, Slot
from ..script.gags import (
    SAY_BOLD,
    box_reactions,
    gag_say,
    player_reactions,
    power_on_announcement,
)
from ..script.hayride import RidePart, Seat, hayride
from ..script.tricks import use_notices
from . import corn_maze as cm
from . import corn_maze_parts as parts
from .props import MODEL_BOX

__all__ = [
    "GAG_LINES", "NOTICES", "HAYRIDE_LINES", "RideHayride", "harvest_quest",
    "hayride_parts", "hayride_seats", "EXPLODING_PUMPKINS", "wire_script",
    "GREAT_PUMPKIN", "PUMPKIN_SOULS", "PUMPKIN_SOULS_PER_EXTRA_PLAYER",
]

# --------------------------------------------------------------------------
# The words
# --------------------------------------------------------------------------
HAYRIDE_LINES: dict[str, tuple[str, str]] = {
    "prompt": ("Hold ^3[{+activate}]^7 to board the hayride [Cost: 500]", "triggerstring"),
    "away": ("The hayride is out on the route. It will be back.", "triggerstring"),
    "closed": ("HAYRIDE: the route runs through the pumpkin patch. Open the patch gate first.",
               "triggerstring"),
    "boarded": ("You are on the hayride. Keep your arms inside the trailer.", "string"),
    "leaving": ("The hayride leaves in five seconds. Hop on at the stop!", "string"),
    "broke": ("The hayride is 500 points. The farmer does not take IOUs.", "string"),
    "full": ("The hayride is full. Wait for the next one.", "string"),
    "closed_said": ("The hayride cannot leave until the pumpkin patch gate is open.", "string"),
}

GAG_LINES: dict[str, str] = {
    "downed": "You fell over in a farm. The corn saw everything.",
    "downed_feed": "&&1 went down in the dirt.",
    "bled_out_feed": "&&1 is part of the harvest now.",
    "revived": "Back on your feet. That will be 25 points for the hay in your hair.",
    "revived_broke": "Back on your feet. You could not pay for the hay. It is on the house.",
    "reviver": "You picked &&1 up out of the dirt.",
    "perk_revive": "That was not apple cider.",
    "perk_speed": "Cold cider. It tastes like batteries.",
    "perk_jugg": "Farmhouse lemonade. It is ninety percent iron.",
    "perk_stamin": "Pumpkin spice. You feel like you could outrun a scarecrow.",
    "perk_double": "Moonshine. Everything happens twice now.",
    "perk_mule": "The mule kicked you. You feel stronger somehow.",
    "pap": "The hayloft ate your gun and spat it back angrier.",
    "box": "The box was in the farmhouse all along. Do not ask the farmhouse.",
    "box_moved": "The mystery box went to live on a nicer farm upstate.",
    "power": "The power is back on. The barn's electric doors swung open by themselves. No charge.",
    "idle": "Standing still in a corn maze is how the stories start.",
    "scarecrow_turn": "The scarecrow turned its head to look at you.",
    "pumpkin_boom": "That was a prize pumpkin. The prize pumpkins here do that.",
}

#: The use notices: key -> (prompt, replies).  Each is placed by
#: :func:`notice_spots`.
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "cider": ("FRESH APPLE CIDER -- hold ^3[{+activate}]^7 to ask", (
        "The cider is in the machines. The machines are perks.",
        "Hot cider picks you up. Cold cider reloads faster. Do not ask how.",
        "No refunds. No apples. The apples in the crate are oranges.",
    )),
    "tractor": ("THE TRACTOR -- hold ^3[{+activate}]^7 to look it over", (
        "It is the farm's tractor. Its brother pulls the hayride. It is very tired.",
        "No keys. They went missing the night the scarecrow went up.",
        "It will run at sunrise, once the harvest tasks are done.",
    )),
    "patch_sign": ("PICK YOUR OWN PUMPKIN -- hold ^3[{+activate}]^7 to read", (
        "PICK YOUR OWN PUMPKIN. Any size. Not the giant ones.",
        "The giant glowing ones are prize pumpkins. They are not for picking.",
        "Prize pumpkins explode when shot. Stand well back, then shoot one.",
    )),
    "farm_sign": ("HARVEST MOON FARM -- hold ^3[{+activate}]^7 to read", (
        "HARVEST MOON FARM. Pumpkins, hayrides, corn maze. Open late.",
        "Under it, in smaller paint: CLOSED FOR THE HARVEST. Somebody painted over CLOSED.",
        "The farmer kept the tractor keys in his pocket. Nobody has seen him since the scarecrow went up.",
    )),
    "schedule": ("HAYRIDE ROUTE -- hold ^3[{+activate}]^7 to read", (
        "Farmyard, the lane, the pumpkin patch, the scarecrow, and home.",
        "Rides every few minutes. The driver never sleeps. There is no driver.",
        "500 points. Keep your arms inside the trailer.",
    )),
}


# --------------------------------------------------------------------------
# The hayride's vehicle
# --------------------------------------------------------------------------
def _centred(model: str, centre: tuple[float, float, float], yaw: float = 0.0,
             scale: float = 1.0) -> RidePart:
    """A part whose measured box centre (plan) and underside (z) land at
    *centre*, relative to the base at yaw 0."""
    lo, hi = MODEL_BOX[model]
    cx, cy = (lo[0] + hi[0]) / 2 * scale, (lo[1] + hi[1]) / 2 * scale
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    wx, wy = cx * c - cy * s, cx * s + cy * c
    return RidePart(model, (centre[0] - wx, centre[1] - wy, centre[2] - lo[2] * scale), yaw, scale)


#: Where the tractor's middle rides, ahead of the trailer's middle: its tail
#: 20 units off the bed's front edge (bed 66 + 20 + half the tractor's 150).
TRACTOR_X = 161.0
#: The trailer bed's top, above the base (the ground).
BED_TOP = 36.0
#: The benches' top, where a rider's feet go.
BENCH_TOP = BED_TOP + 31.0


def hayride_parts() -> tuple[RidePart, ...]:
    """The flatbed trailer on its wheels, two benches of crates, pumpkins and
    a lantern, and the tractor in front on a tow bar.  The rig drives +x,
    so the tractor is turned to point that way (:data:`parts.TRACTOR_YAW`)."""
    bed_z = BED_TOP - 12.0
    return (
        _centred(parts.FLATBED, (0.0, 0.0, bed_z)),
        _centred("veh_t7_mil_macv_wheel_attach", (-40.0, 40.0, 0.0), 0.0),
        _centred("veh_t7_mil_macv_wheel_attach", (40.0, 40.0, 0.0), 0.0),
        _centred("veh_t7_mil_macv_wheel_attach", (-40.0, -40.0, 0.0), 180.0),
        _centred("veh_t7_mil_macv_wheel_attach", (40.0, -40.0, 0.0), 180.0),
        _centred(parts.CRATE_LONG, (-5.0, 20.0, BED_TOP)),
        _centred(parts.CRATE_LONG, (-5.0, -20.0, BED_TOP)),
        _centred(parts.PUMPKIN, (50.0, 18.0, BED_TOP), 30.0, 1.3),
        _centred(parts.JACK, (52.0, -16.0, BED_TOP), 270.0, 1.2),
        _centred(parts.SACK, (-52.0, 0.0, BED_TOP), 90.0),
        _centred(parts.LAMP, (-52.0, 0.0, BED_TOP + 10.0)),
        # The tow bar: half a 2x4 from under the bed to under the tractor.
        _centred("p7_debris_wood_board_2x4x128", (85.0, 0.0, 18.0), 0.0, 0.5),
        _centred(parts.TRACTOR, (TRACTOR_X, 0.0, 0.0), parts.TRACTOR_YAW),
    )


def hayride_seats() -> tuple[Seat, ...]:
    """Four seats on the two benches, riders facing out over the sides."""
    return (
        Seat((-25.0, 20.0, BENCH_TOP), 90.0),
        Seat((15.0, 20.0, BENCH_TOP), 90.0),
        Seat((-25.0, -20.0, BENCH_TOP), 270.0),
        Seat((15.0, -20.0, BENCH_TOP), 270.0),
    )


def hayride_trigger(plan: "cm.CornMazePlan", floor_z: float) -> tuple[float, float, float]:
    x, y = cm.hayride_route(plan)[0]
    return (x - 60.0, y - 175.0, floor_z + 12.0)


def hayride_unload(plan: "cm.CornMazePlan", floor_z: float) -> tuple[tuple[float, float, float], ...]:
    x, y = cm.hayride_route(plan)[0]
    return tuple((x - 120.0 + i * 45.0, y - 200.0, floor_z + 14.0) for i in range(4))


# --------------------------------------------------------------------------
# The two gags of this map's own
# --------------------------------------------------------------------------
#: The turning figure: parts relative to the top of the post, at yaw 0 the
#: figure faces +x (the sign on its chest looks +x).
#: The base is the top of the scarecrow's pole (:data:`parts.POLE_TOP`).
def scarecrow_parts() -> tuple[RidePart, ...]:
    return (
        # The head: a carved jack-o'-lantern sat on the post top, its face
        # (-y at yaw 0 on a kit model) turned to +x.
        _centred(parts.JACK, (0.0, 0.0, -3.0), 90.0, SCARECROW_HEAD_SCALE),
        # No arms here: the arms and the shirt are static, on the cross
        # (parts._scarecrow_body), so the figure reads in the editor too; in
        # game only the head and its sign turn, which is the gag.
        # The chest sign, pinned in front of the pole on the shirt, under
        # the cross-arm (arms at 128, pole top 150).
        _centred("p7_signage_caution_warning_01", (5.0, 0.0, -32.0), 270.0),
    )


#: The scarecrow's head: 1.35x the kit jack-o'-lantern, 22 across.
SCARECROW_HEAD_SCALE = 1.35


EXPLODING_PUMPKINS: tuple[tuple[float, float], ...] = (
    (1260.0, 60.0), (1780.0, 260.0), (1420.0, 470.0), (1650.0, -40.0), (2180.0, 560.0), (820.0, -470.0),
)


def _v(p) -> str:
    return "( " + ", ".join(f"{float(c):g}" for c in p) + " )"


def scarecrow_script(heads: Mapping[str, tuple[float, float, float]], line: str,
                     climbs_down_on: str | None = None) -> CustomScript:
    """One turning figure per entry of *heads* (name -> top of post).

    *climbs_down_on* (a level notify, e.g. the boss's ``zmf_boss_<key>_spawned``)
    takes the heart's figure off its post the moment it fires: until then it
    stays up and keeps watching, so the boss reads as the scarecrow climbing
    down."""
    spawn = ['level endon( "end_game" );', "level.zmf_scarecrows = [];"]
    for name, top in heads.items():
        spawn += [f'e_base = spawn( "script_model", {_v(top)} );', 'e_base SetModel( "tag_origin" );',
                  "e_base.angles = ( 0, 0, 0 );", "e_base.zmf_parts = [];"]
        for part in scarecrow_parts():
            spawn += [
                f'e_part = spawn( "script_model", {_v(top)} + {_v(part.offset)} );',
                f'e_part SetModel( "{part.model}" );',
                f"e_part.angles = ( 0, {part.yaw:g}, 0 );",
                *([f"e_part SetScale( {part.scale:g} );"] if part.scale != 1.0 else []),
                "e_part LinkTo( e_base );",
                "e_base.zmf_parts[ e_base.zmf_parts.size ] = e_part;",
            ]
        # The map carries a static sack head on this post so the figure
        # reads in the editor (parts._scarecrow_body); the turning head takes
        # its place, so it goes as soon as that is up.
        spawn += [f'e_static = GetEnt( "{parts.static_head_name(name)}", "targetname" );',
                  "if ( isdefined( e_static ) )", "{", "\te_static Delete();", "}"]
        spawn += [f'level.zmf_scarecrows[ "{name}" ] = e_base;', "e_base thread zmf_scarecrow_watch();"]
    if climbs_down_on is not None:
        spawn += ["level thread zmf_scarecrow_climbs_down();"]
    watch = [
        'self endon( "death" );',
        'level endon( "end_game" );',
        "while ( true )",
        "{",
        "\twait 0.3;",
        "\te_near = undefined;",
        "\tn_best = 900 * 900;",
        "\ta_players = getplayers();",
        "\tfor ( i = 0; i < a_players.size; i++ )",
        "\t{",
        "\t\tn_d = DistanceSquared( a_players[ i ].origin, self.origin );",
        "\t\tif ( n_d < n_best )",
        "\t\t{",
        "\t\t\tn_best = n_d;",
        "\t\t\te_near = a_players[ i ];",
        "\t\t}",
        "\t}",
        "\tif ( !isdefined( e_near ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        "\tv_face = VectorToAngles( e_near.origin - self.origin );",
        "\tself RotateTo( ( 0, v_face[ 1 ], 0 ), 0.25 );",
        "\tif ( n_best < 320 * 320 )",
        "\t{",
        f'\t\te_near thread zmf_gag_say( "scarecrow", &"{line}", 45000, {SAY_BOLD} );',
        "\t}",
        "}",
    ]
    functions = [
        CustomFunction("zmf_scarecrows_init", tuple(spawn),
                       purpose="Spawn each scarecrow's figure on its post and start it watching."),
        CustomFunction("zmf_scarecrow_watch", tuple(watch),
                       purpose="Turn this figure to face the nearest player (RotateTo, VectorToAngles)."),
    ]
    if climbs_down_on is not None:
        functions.append(CustomFunction("zmf_scarecrow_climbs_down", (
            'level endon( "end_game" );',
            f'level waittill( "{climbs_down_on}" );',
            'e_base = level.zmf_scarecrows[ "heart" ];',
            "for ( i = 0; i < e_base.zmf_parts.size; i++ )",
            "{",
            "\te_base.zmf_parts[ i ] Delete();",
            "}",
            # The watch thread ends on the base's "death": nothing is left on
            # the post to turn or to say it turned.
            'e_base notify( "death" );',
            'level.zmf_scarecrows[ "heart" ] = undefined;',
            "e_base Delete();",
        ), purpose="The boss is here: the heart's scarecrow has climbed down off its post (it is the boss)."))
    return CustomScript(
        functions=tuple(functions),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_scarecrows_init();"),),
        assets=tuple(sorted({("xmodel", p.model) for p in scarecrow_parts()})),
        notes=(f"{len(heads)} turning scarecrows",),
    )


#: The prize pumpkins' glow: the stock green powerup glow
#: (``zm/_zm_powerups.gsc:80``, registered unconditionally), the sickly green
#: tell they had as a baked light (:data:`.corn_maze_parts.PRIZE_GLOW`), and
#: not the quest lanterns' orange.  It replaces that light: a baked light
#: stays on after the pumpkin is shot (as a lantern's would).
#: **Unverified in play**, like the lanterns': that it loops for the entity's
#: life and reads at night.
PUMPKIN_GLOW_FX = "powerup_on"

#: A prize pumpkin's blast: radius and (max, min) damage.  The radius keeps
#: the hayride's riders out of it: the nearest pumpkin is 170 units off the
#: route's line and the seats sit 20 either side of it
#: (it was 200, which reached riders passing the patch).  A player who
#: follows the sign ("stand well back, then shoot") is well outside it.
PUMPKIN_BLAST_RADIUS = 120.0
PUMPKIN_BLAST_DAMAGE = (1000, 200)


def pumpkin_script(points, z: float, line: str) -> CustomScript:
    body = ['level endon( "end_game" );', "a_spots = [];"]
    body += [f"a_spots[ {n} ] = {_v((x, y, z))};" for n, (x, y) in enumerate(points)]
    body += [
        "while ( true )",
        "{",
        "\tfor ( i = 0; i < a_spots.size; i++ )",
        "\t{",
        "\t\tif ( !isdefined( level.zmf_pumpkins ) )",
        "\t\t{",
        "\t\t\tlevel.zmf_pumpkins = [];",
        "\t\t}",
        "\t\tif ( !isdefined( level.zmf_pumpkins[ i ] ) )",
        "\t\t{",
        "\t\t\tlevel.zmf_pumpkins[ i ] = zmf_pumpkin_spawn( a_spots[ i ] );",
        "\t\t}",
        "\t}",
        '\tlevel waittill( "start_of_round" );',
        "}",
    ]
    glow_up = round(MODEL_BOX[parts.PRIZE][1][2] * parts.PRIZE_SCALE / 2.0, 1)
    spawn = [
        'e_pumpkin = spawn( "script_model", v_spot );',
        f'e_pumpkin SetModel( "{parts.PRIZE}" );',
        "e_pumpkin.angles = ( 0, RandomIntRange( 0, 360 ), 0 );",
        f"e_pumpkin SetScale( {parts.PRIZE_SCALE:g} );",
        "e_pumpkin SetCanDamage( true );",
        # The glow the signs promise: a looped effect on a tag_origin at the
        # pumpkin's middle (the quest lanterns' pattern, lantern_script), gone
        # with its entity when the pumpkin is shot.
        f"e_glow = spawn( \"script_model\", v_spot + ( 0, 0, {glow_up:g} ) );",
        'e_glow SetModel( "tag_origin" );',
        f'PlayFXOnTag( level._effect[ "{PUMPKIN_GLOW_FX}" ], e_glow, "tag_origin" );',
        "e_pumpkin.e_glow = e_glow;",
        "e_pumpkin thread zmf_pumpkin_wait();",
        "return e_pumpkin;",
    ]
    blast = f"v_at + ( 0, 0, 16 ), {PUMPKIN_BLAST_RADIUS:g}, {PUMPKIN_BLAST_DAMAGE[0]}, {PUMPKIN_BLAST_DAMAGE[1]}"
    wait = [
        'self endon( "death" );',
        'level endon( "end_game" );',
        'self waittill( "damage", n_amount, e_attacker );',
        "v_at = self.origin;",
        "if ( isdefined( self.e_glow ) )",
        "{",
        "\tself.e_glow Delete();",
        "}",
        'PlayFX( level._effect[ "def_explosion" ], v_at );',
        "if ( isplayer( e_attacker ) )",
        "{",
        f'\tRadiusDamage( {blast}, e_attacker, "MOD_EXPLOSIVE" );',
        f'\te_attacker thread zmf_gag_say( "pumpkin", &"{line}", 20000, {SAY_BOLD} );',
        "}",
        "else",
        "{",
        f"\tRadiusDamage( {blast} );",
        "}",
        "self Delete();",
    ]
    return CustomScript(
        functions=(
            CustomFunction("zmf_pumpkins", tuple(body), purpose="Grow the exploding pumpkins, again every round."),
            CustomFunction("zmf_pumpkin_spawn", tuple(spawn), params=("v_spot",),
                           purpose="One exploding pumpkin (SetCanDamage, _trophy_system.gsc:367)."),
            CustomFunction("zmf_pumpkin_wait", tuple(wait),
                           purpose="Shot: the stock default explosion (_zm_blockers.gsc:440), RadiusDamage."),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_pumpkins();"),),
        assets=(("xmodel", parts.PRIZE), ("xmodel", "tag_origin")),
        notes=(f"{len(points)} exploding prize pumpkins, each glowing ({PUMPKIN_GLOW_FX})",),
    )


#: The quest lanterns' glow while lit, and the puff when one is put out
#: (both assigned in ``zm/_zm_powerups.gsc:90-91``).
LANTERN_GLOW_FX = "powerup_on_caution"
LANTERN_OUT_FX = "powerup_grabbed_caution"


def lantern_script(jacks, step_key: str = "lanterns") -> CustomScript:
    """The quest's three jack-o'-lanterns, lit and put out by script.

    A map ``light`` is baked at compile and a placed model is static, so a
    shot lantern used to stay lit.  Here each lantern is
    a ``script_model`` of the tall carved jack on its bale, and its glow is
    the looped effect played on a ``tag_origin`` beside it -- the stock
    pattern of ``zm/_zm_ai_raps.gsc:638-640`` (spawn a ``tag_origin``
    script_model, ``playfxontag`` on it) whose effect ends when the entity is
    deleted (``cleanup_meteor_fx``).  On the quest's hit notify for lantern
    *j* (``zmf_q_hit_<step>``, sent by ``zmf_quest_aim_attach``) the glow
    entity is deleted, the model becomes the plain uncarved pumpkin, and the
    stock grab puff plays where it was.  Idempotent: a second hit on an
    already dark lantern does nothing.

    **Unverified in play:** that ``powerup_on_caution`` loops for as long as
    its entity lives (it is the stock powerup glow) and how bright it reads
    at night.

    The step is timed (:data:`LANTERNS_TIME_LIMIT`): when its countdown runs
    out the quest wakes the hit notify with no target, and every dark
    lantern lights again (``zmf_lanterns_relight``), so the step's reset to
    0 of 3 matches what the player sees.  The loop ends on the step's end
    (``zmf_q_end_<step>``): the lanterns that are out stay out."""
    k = step_key
    init = ['level endon( "end_game" );', "level.zmf_lanterns = [];", "level.zmf_lantern_fx = [];",
            "level.zmf_lantern_mid = [];"]
    for j, (x, y, top, yaw) in enumerate(jacks):
        mid = top + MODEL_BOX[parts.JACK_TALL][1][2] * parts.QUEST_JACK_SCALE / 2.0
        init += [
            f'e_jack = spawn( "script_model", {_v((x, y, top))} );',
            f'e_jack SetModel( "{parts.JACK_TALL}" );',
            f"e_jack.angles = ( 0, {float(yaw):g}, 0 );",
            f"e_jack SetScale( {parts.QUEST_JACK_SCALE:g} );",
            f"level.zmf_lanterns[ {j} ] = e_jack;",
            f'e_fx = spawn( "script_model", {_v((x, y, mid))} );',
            'e_fx SetModel( "tag_origin" );',
            f'PlayFXOnTag( level._effect[ "{LANTERN_GLOW_FX}" ], e_fx, "tag_origin" );',
            f"level.zmf_lantern_fx[ {j} ] = e_fx;",
            f"level.zmf_lantern_mid[ {j} ] = {_v((x, y, mid))};",
        ]
    init += [
        f'level endon( "zmf_q_end_{k}" );',
        "while ( true )",
        "{",
        f'	level waittill( "zmf_q_hit_{k}", j, e_who );',
        # The quest's countdown ran out: it wakes the step with no target
        # (quest._timer_functions), and every dark lantern lights again, so
        # the three the step now asks for are the three that burn.
        "\tif ( !isdefined( j ) && !isdefined( e_who ) )",
        "\t{",
        "\t\tzmf_lanterns_relight();",
        "\t\tcontinue;",
        "\t}",
        "	if ( !isdefined( j ) || !isdefined( level.zmf_lantern_fx[ j ] ) )",
        "	{",
        "		continue;",
        "	}",
        "	level thread zmf_lantern_out( j );",
        "}",
    ]
    out = [
        "e_fx = level.zmf_lantern_fx[ n ];",
        "level.zmf_lantern_fx[ n ] = undefined;",
        "e_fx Delete();",
        "e_jack = level.zmf_lanterns[ n ];",
        f'e_jack SetModel( "{parts.PUMPKIN}" );',
        f'PlayFX( level._effect[ "{LANTERN_OUT_FX}" ], e_jack.origin + ( 0, 0, 12 ) );',
    ]
    relight = [
        "for ( n = 0; n < level.zmf_lanterns.size; n++ )",
        "{",
        "\tif ( isdefined( level.zmf_lantern_fx[ n ] ) )",
        "\t{",
        "\t\tcontinue;",
        "\t}",
        f'\tlevel.zmf_lanterns[ n ] SetModel( "{parts.JACK_TALL}" );',
        '\te_fx = spawn( "script_model", level.zmf_lantern_mid[ n ] );',
        '\te_fx SetModel( "tag_origin" );',
        f'\tPlayFXOnTag( level._effect[ "{LANTERN_GLOW_FX}" ], e_fx, "tag_origin" );',
        "\tlevel.zmf_lantern_fx[ n ] = e_fx;",
        "}",
    ]
    return CustomScript(
        functions=(
            CustomFunction("zmf_lanterns", tuple(init),
                           purpose="Light the quest lanterns (script_model + looped fx on a tag_origin) and put each out when hit."),
            CustomFunction("zmf_lantern_out", tuple(out), params=("n",),
                           purpose="One lantern goes dark: glow entity deleted, model swapped to the plain pumpkin, a puff."),
            CustomFunction("zmf_lanterns_relight", tuple(relight),
                           purpose="Out of time: every dark lantern is the carved jack again, glowing."),
        ),
        statements=((Slot.AFTER_ENTRY, "level thread zmf_lanterns();"),),
        assets=(("xmodel", parts.JACK_TALL), ("xmodel", parts.PUMPKIN), ("xmodel", "tag_origin")),
        notes=(f"{len(jacks)} quest lanterns, lit by script",),
    )


# --------------------------------------------------------------------------
# The quest
# --------------------------------------------------------------------------
#: The skill steps' time limits (map-principles P6), in seconds from the
#: step's first progress, counted down on the HUD; out of time the step
#: starts again.  Sized off the built map (measured with
#: :func:`.corn_maze.maze_distances`, 288 units a maze cell, a run of about
#: 190 units/s):
#:
#: * lanterns: farmyard (-100, -105), patch (1330, -30) and maze entry
#:   (-1738, 954).  The worst order is about 5,000 units of running, 26 s;
#:   90 s leaves room for zombies, reloads and a miss or two.
#: * wake: three knife hits on one post, 15 s with the horde on you.
LANTERNS_TIME_LIMIT = 90.0
#: The boss's key; its spawn notify (``zmf_boss_<key>_spawned``) takes the
#: heart's scarecrow figure off its post.
SCARECROW_BOSS_KEY = "scarecrow"
WAKE_TIME_LIMIT = 15.0
#: The Great Pumpkin, the quest's soul box (step "pumpkin", after the
#: hayride): plan x, y in the middle of the pumpkin patch, inside the loop
#: the hayride drives round it, 300 units off the ride's track.  The crop
#: rows keep clear of it (corn_maze_parts, next to the prize pumpkins).
GREAT_PUMPKIN = (1700.0, 150.0)
#: Souls it wants solo, and more for each player past the first (20 solo,
#: 28 for two, 44 for four): about a round or two of fighting in the patch
#: at rounds 3-5.
PUMPKIN_SOULS = 20
PUMPKIN_SOULS_PER_EXTRA_PLAYER = 8
#: The kit jack-o'-lantern (16 across, 13.6 tall) at 3x when the step opens,
#: growing to 5x (80 across, 68 tall) as it eats.
PUMPKIN_SCALE_EMPTY, PUMPKIN_SCALE_FULL = 3.0, 5.0


@dataclass(frozen=True, kw_only=True)
class RideHayride(q.Step):
    """Ride the hayride ``laps`` full laps (with at least one rider on
    board): waits for :mod:`zmforge.script.hayride`'s ``zmf_hayride_lap``
    notify, which carries the riders."""

    laps: int = 1

    @property
    def total(self) -> int:
        return int(self.laps)

    def body(self, i, s):
        return [
            "n = 0;",
            f"while ( n < {self.total} )",
            "{",
            '\tlevel waittill( "zmf_hayride_lap", a_riders );',
            "\tif ( !isdefined( a_riders ) || a_riders.size < 1 )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\tn++;",
            f"\tzmf_quest_progress( {i}, n );",
            "}",
        ]


def golden_ears(plan: "cm.CornMazePlan", rooms: Mapping[str, object]) -> tuple[tuple[float, float, float], ...]:
    """Where the three golden ears lie: a dead end of the front rows, one of
    the deep rows (:data:`.corn_maze_parts.MAZE_SPOTS`), and the heart's
    south-east corner."""
    me, md, hi = rooms["mazeentry"], rooms["mazedeep"], rooms["heart"].interior
    entry_ear, deep_ear = parts.MAZE_SPOTS["ears"]
    return (
        (*plan.cell_centre(entry_ear), me.floor_z + 2.0),
        (*plan.cell_centre(deep_ear), md.floor_z + 2.0),
        (hi.maxs.x - 120.0, hi.mins.y + 120.0, rooms["heart"].floor_z + 2.0),
    )


def quest_points(plan: "cm.CornMazePlan", rooms: Mapping[str, object]) -> list[tuple[float, float]]:
    """Plan spots a player has to find, read or use that the dresser does not
    know about (they are wired after it): the golden ears, the heart
    scarecrow's knife target, the tractor's exit trigger,
    the hayride's trigger, every notice and every prize pumpkin.  The grass
    keeps off them (:func:`.corn_maze_parts._grass`).  Needs
    :func:`.corn_maze_parts.build_all`'s ``SCARECROWS`` and ``MAZE_SPOTS``."""
    rig_x, rig_y, _ = parts.SCARECROWS["tractor"]
    heart_x, heart_y, _ = parts.SCARECROWS["heart"]
    points = [(x, y) for x, y, _ in golden_ears(plan, rooms)]
    points += [(heart_x, heart_y), (rig_x - 110.0, rig_y)]
    points.append(hayride_trigger(plan, rooms["farmyard"].floor_z)[:2])
    points += [(x, y) for x, y, _ in notice_spots(plan, rooms).values()]
    points += list(EXPLODING_PUMPKINS)
    points.append(GREAT_PUMPKIN)
    return points


def harvest_quest(plan: "cm.CornMazePlan", rooms: Mapping[str, object]) -> q.Quest:
    """The Easter egg as the framework's :class:`~zmforge.script.quest.Quest`.
    See :data:`zmforge.recipes.corn_maze.QUEST_STEPS` for the plain story."""
    fy, pa, me, md, he = (rooms[k] for k in ("farmyard", "patch", "mazeentry", "mazedeep", "heart"))
    fz, pz, tz = fy.floor_z, pa.floor_z, he.floor_z
    fi, hi = fy.interior, he.interior
    lantern_targets = (
        q.Target(point=parts.JACKS["farmyard"][0], radius=18.0),
        q.Target(point=parts.JACKS["patch"][0], radius=20.0),
        q.Target(point=parts.JACKS["mazeentry"][0], radius=20.0),
    )
    ear_points = golden_ears(plan, rooms)
    heart_x, heart_y, heart_top = parts.SCARECROWS["heart"]
    rig_x, rig_y, _ = parts.SCARECROWS["tractor"]
    scarecrow = b.Boss(
        key=SCARECROW_BOSS_KEY,
        name="The Scarecrow",
        # At the foot of its post, facing the gate like the figure, snapped
        # to the navmesh so it can path (the figure leaves the post as it
        # appears: scarecrow_script's climbs_down_on).
        spawn_at=parts.BOSS_SPAWN[0],
        yaw=270.0,
        spawn_snap=128.0,
        arrives="THE SCARECROW is off its post and coming out of the corn. The tractor keys jingle in its pocket.",
        defeated="The Scarecrow is only straw again. The tractor keys fall out of it.",
        # 40 s of one player's best guns at its round (the Gravedigger
        # calibration): 100,000 solo on rounds 4-9; it runs,
        # never sprints; armoured while its minions live.
        health=b.BossHealth(ttk=b.BOSS_TTK, per_extra_player=0.75),
        armour=0.25,
        minions=4,
        points=1500,
        powerup="full_ammo",
        # Dressed as the maze's own scarecrow figures (scarecrow_parts): a
        # jack-o'-lantern head, 2x4 crossbar arms and a caution sign on the
        # chest, each riding a bone so it moves with the body.  On the feet
        # tag the pumpkin floats above the zombie's own head and the sign
        # shows its grey back, so the zombie's head comes off and the jack (30 across, 26 tall
        # at 1.9) sits on the neck on j_head; the sign's face is its -y
        # (props._mount_face), so yaw 90 turns it forward.  Unverified in play.
        headless=True,
        props=(
            b.BossProp(parts.JACK, offset=(1.0, 0.0, 59.0), angles=(0.0, 90.0, 0.0), scale=1.9,
                       tag="j_head"),
            b.BossProp("p7_debris_wood_board_2x4x128", offset=(-3.0, 0.0, 57.0),
                       angles=(0.0, 90.0, 0.0), scale=0.55, tag="j_spine4"),
            b.BossProp("p7_signage_caution_warning_01", offset=(11.0, 0.0, 38.0),
                       angles=(0.0, 90.0, 0.0), scale=1.0, tag="j_spine4"),
        ),
    )
    return q.Quest(
        key="harvest",
        header="HARVEST MOON: &&1 OF &&2 DONE",
        intro="Survive until sunrise. Something in the corn wants you to stay for the harvest.",
        step_done="HARVEST TASK &&1 OF &&2 DONE",
        complete="The harvest is in. The tractor will take you out at sunrise.",
        idle="CURRENT TASK: survive",
        steps=(
            q.HitTargets(
                key="lanterns",
                # What to do, not where: players find the lanterns.
                task="CURRENT TASK: Shoot out the jack-o'-lanterns (&&1/&&2)",
                start=("Shoot out the jack-o'-lanterns. Once one goes dark you have "
                       f"{LANTERNS_TIME_LIMIT:.0f} seconds to shoot out the other two."),
                advance="A jack-o'-lantern goes dark (&&1/&&2).",
                done="The lanterns are out. Something in the corn noticed.",
                targets=lantern_targets, mode="shoot", ordered=False,
                # A one-shot puff, never a looping "powerup_on*" effect: PlayFX has no
                # handle, so every looping copy the pulse played (one per 2.5 s)
                # kept burning after the lantern was shot.
                pulse_fx=LANTERN_OUT_FX,
                time_limit=LANTERNS_TIME_LIMIT,
                lockdown=True,
                timeout="TIME'S UP! The jack-o'-lanterns light themselves again. Shoot all three.",
                timer_line="LANTERNS: &&1 s left",
            ),
            RideHayride(
                key="hayride",
                task="CURRENT TASK: take the hayride all the way round",
                start="The hayride is waiting. Take a lap. Keep your arms inside.",
                done="The hayride came back without its driver. It never had one.",
            ),
            q.SoulBox(
                key="pumpkin",
                # What to do, not where (P17): the pumpkin glows; players find it.
                task="CURRENT TASK: feed the Great Pumpkin (&&1/&&2 souls)",
                start=("The Great Pumpkin is hungry. Kill the dead near it and it eats "
                       "their souls. Do not ask what it eats the rest of the year."),
                done="The Great Pumpkin is full. It burps up a corn husk. A golden one.",
                vessels=(q.Vessel(point=(*GREAT_PUMPKIN, pz), model=parts.JACK, yaw=180.0,
                                  scale=PUMPKIN_SCALE_EMPTY, full_scale=PUMPKIN_SCALE_FULL,
                                  mouth=48.0),),
                souls=PUMPKIN_SOULS,
                per_extra_player=PUMPKIN_SOULS_PER_EXTRA_PLAYER,
                radius=450.0,
                glow_fx="powerup_on_caution",
                arrive_fx="powerup_grabbed_caution",
                full_fx="powerup_grabbed_caution",
            ),
            q.CollectDeliver(
                key="ears",
                # A plain collect: each pickup counts at once,
                # no hand-in at the cider stand and no clock.
                deliver=False,
                task="CURRENT TASK: find the golden corn (&&1/&&2)",
                start="Three golden ears are lost in the maze. Find them.",
                advance="Golden corn found (&&1/&&2).",
                done="You found all the golden corn. The scarecrow wants it back.",
                items=tuple(q.Item(point=p, picked="You picked up a golden ear of corn. It is a banana.",
                                   model="p7_food_fruit_banana_bunch") for p in ear_points),
                pickup_prompt="Hold ^3[{+activate}]^7 to pick up the golden corn",
            ),
            q.HitTargets(
                key="wake",
                task="CURRENT TASK: wake the scarecrow (&&1/&&2)",
                start=("The scarecrow is pretending to be asleep. Poke it awake: "
                       f"{WAKE_TIME_LIMIT:.0f} seconds from the first poke."),
                advance="The scarecrow twitches (&&1/&&2).",
                done="The scarecrow is climbing down off its post.",
                targets=(q.Target(point=(heart_x, heart_y, tz + 60.0), radius=40.0),),
                mode="melee", hits=3,
                time_limit=WAKE_TIME_LIMIT,
                lockdown=True,
                timeout="TIME'S UP! The scarecrow went back to sleep. Faster this time.",
                timer_line="WAKE THE SCARECROW: &&1 s left",
            ),
            q.DefeatBoss(
                key="boss",
                task="CURRENT TASK: kill the Scarecrow (&&1 percent left)",
                start="The Scarecrow is loose.",
                done="The Scarecrow is straw. You have the tractor keys.",
                boss=scarecrow,
                arena=(heart_x, heart_y, tz),
                arena_radius=400.0,
            ),
            q.StandInZone(
                key="defend",
                lockdown=True,
                task="CURRENT TASK: stay by the tractor while it warms up (&&1/&&2 seconds)",
                start="You have the keys. The tractor is warming up. Stay by it. Everything in the corn heard it.",
                advance="The engine coughs (&&1/&&2 seconds).",
                done="The engine caught. The ride out leaves at sunrise.",
                point=(rig_x, rig_y, fz),
                seconds=60,
                radius=200.0,
            ),
        ),
        exit=q.BuyableExit(
            origin=(rig_x - 110.0, rig_y, fz + 30.0),
            locked_prompt="The tractor will not start until the harvest is in: finish the Harvest Moon tasks.",
            prompt="Hold ^3[{+activate}]^7 to drive out of the farm at sunrise [Cost: &&1]",
            locked="The tractor will not start until the harvest is in.",
            poor="The ride out of the farm costs &&1. The farmer does not take IOUs.",
            task="CURRENT TASK: drive out of the farm at sunrise (&&1 points)",
            win_line="The sun comes up over the corn. You drive out of Harvest Moon Farm. The corn waves goodbye.",
            win_title="YOU SURVIVED THE HARVEST",
            price=plan.ending_price,
        ),
    )


def notice_spots(plan: "cm.CornMazePlan", rooms: Mapping[str, object]) -> dict[str, tuple[float, float, float]]:
    fy, pa = rooms["farmyard"], rooms["patch"]
    fz, fi, pz = fy.floor_z, fy.interior, pa.floor_z
    stop_x, stop_y = cm.hayride_route(plan)[0]
    rig_x, rig_y, _ = parts.SCARECROWS["tractor"]
    return {
        "cider": (40.0, fi.maxs.y - 60.0, fz + 4.0),
        "tractor": (rig_x + 220.0, rig_y + 20.0, fz + 4.0),
        "patch_sign": (pa.interior.mins.x + 80.0, plan.lane_y + 250.0, pz + 4.0),
        "schedule": (stop_x + 80.0, stop_y - 175.0, fz + 16.0),
        "farm_sign": (parts.FARM_SIGN_X, fi.maxs.y - 40.0, fz + 4.0),
    }


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
def wire_script(bp: Blueprint, plan: "cm.CornMazePlan", rooms: Mapping[str, object]) -> q.Quest:
    fy, pa = rooms["farmyard"], rooms["patch"]
    fz, pz = fy.floor_z, pa.floor_z
    said = {key: bp.add_map_string(f"GAG_{key.upper()}", text) for key, text in GAG_LINES.items()}

    # The gags every map gets, with this map's words.
    specialty = {p.slug: p.specialty for p in PERKS}
    bp.add_custom_logic(gag_say())
    bp.add_custom_logic(player_reactions(
        downed=said["downed"], downed_feed=said["downed_feed"], bled_out_feed=said["bled_out_feed"],
        revived=said["revived"], revived_broke=said["revived_broke"], reviver=said["reviver"], fee=25,
        perks={
            specialty["quick_revive"]: said["perk_revive"],
            specialty["speed_cola"]: said["perk_speed"],
            specialty["juggernog"]: said["perk_jugg"],
            specialty["stamin_up"]: said["perk_stamin"],
            specialty["double_tap"]: said["perk_double"],
            specialty["mule_kick"]: said["perk_mule"],
        },
        pap=said["pap"],
        idle=("mazedeep", 25.0, said["idle"]),
    ))
    bp.add_custom_logic(box_reactions(used=said["box"], moved=said["box_moved"]))
    # No round-end radio and no zone sign-in lines (P13, P17):
    # the radio told players where the power and Pack-a-Punch were.
    bp.add_custom_logic(power_on_announcement(said["power"]))

    # The notices.
    spots = notice_spots(plan, rooms)
    notices = []
    for key, (prompt, replies) in NOTICES.items():
        ref = f"NOTICE_{key.upper()}"
        notices.append((spots[key], bp.add_map_string(ref, prompt, kind="triggerstring"),
                        [bp.add_map_string(f"{ref}_{n}", line) for n, line in enumerate(replies)]))
    bp.add_custom_logic(use_notices(notices))

    # The hayride.
    hl = {key: bp.add_map_string(f"HAYRIDE_{key.upper()}", text, kind=kind)
          for key, (text, kind) in HAYRIDE_LINES.items()}
    patch_flag = next(d.flag for d in bp.elements() if type(d).__name__ == "Door" and d.zone_b == "patch")
    bp.add_custom_logic(hayride(
        route=cm.hayride_route(plan), z=fz, parts=hayride_parts(), seats=hayride_seats(),
        unload=hayride_unload(plan, fz), trigger=hayride_trigger(plan, fz), price=plan.hayride_price,
        prompt=hl["prompt"], prompt_away=hl["away"], prompt_closed=hl["closed"],
        said_boarded=hl["boarded"], said_leaving=hl["leaving"], said_broke=hl["broke"],
        said_full=hl["full"], said_closed=hl["closed_said"],
        requires_flag=patch_flag, speed=plan.hayride_speed, radius=64.0,
    ))
    for model in {p.model for p in hayride_parts()}:
        bp.declare_asset("xmodel", model)

    # The map's own gags.
    # Only the heart's scarecrow turns: the patch's was removed.
    heads = {k: v for k, v in parts.SCARECROWS.items() if k == "heart"}
    bp.add_custom_logic(scarecrow_script(heads, said["scarecrow_turn"],
                                         climbs_down_on=f"zmf_boss_{SCARECROW_BOSS_KEY}_spawned"))
    bp.add_custom_logic(pumpkin_script(EXPLODING_PUMPKINS, pz, said["pumpkin_boom"]))
    bp.add_custom_logic(lantern_script(parts.QUEST_JACKS))

    # The quest, through the shared framework.
    quest = harvest_quest(plan, rooms)
    q.install_quest(bp, quest)
    # The prize pumpkins are removed by script, so Z64 warns about a static
    # light that would outlive one (P12); install_quest records the quest
    # lanterns.  Both glows are effects on tag_origins deleted with them
    # (lantern_script, pumpkin_script).
    for n, (x, y) in enumerate(EXPLODING_PUMPKINS, 1):
        own_object(bp, f"prize pumpkin {n}", (x, y, pz))
    return quest
