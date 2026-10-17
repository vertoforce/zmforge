"""A glow that belongs to an object: it goes out when the object is done.

Map-principles P12, "finished means finished", applied to light.  A map
``light`` is baked at compile and no server script can switch it, and a
looping effect played with ``PlayFX`` has no handle, so it burns until the
game ends.  Two stock patterns are script-controlled, and this module is the
one place a recipe asks for either:

* **an exploder light** (:func:`place_owned_glow`): an ordinary radiant light
  carrying the exploder keys the stock perk lights carry
  (``_prefabs/zm/zm_core/vending_revive_struct.map:59-61``:
  ``"exploderDisabled" "1"``, ``"exploder_count" "1"``,
  ``"exploder_index_0" "0 0 quick_revive_lgts"``), switched from the server
  script with ``exploder::exploder( "quick_revive_lgts" )`` and
  ``exploder::stop_exploder( "quick_revive_lgts" )``
  (``_zm_perk_quick_revive.gsc:185`` and ``:791``).  The lamp is lit at start
  by a generated watcher and put out on the level notify that ends its
  object; a recipe that manages the light itself uses :func:`glow_on` /
  :func:`glow_off` in its own script instead;
* **an effect on a tag** for a glow that moves with a script model: spawn a
  ``tag_origin`` script_model, ``PlayFXOnTag`` on it, delete the entity with
  the object (``_zm_ai_raps.gsc:638-640``, ``cleanup_meteor_fx`` at
  ``:714-725``).  :func:`tag_glow_lines` writes those lines.

:func:`own_object` records where a script-removed or quest object stands, so
check ``Z64`` (:mod:`zmforge.verify.glows`) can warn about a static lamp that
would outlive it.

**Unverified in play**: that an exploder light written by the
generator lights and goes out in game.  The keys are the stock ones; the
toggle is the stock call.
"""

from __future__ import annotations

import re

from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "EXPLODER_USING", "LOOPING_FX", "OWNED_GLOW_REACH", "glow_name", "glow_off", "glow_on",
    "own_object", "own_quest_targets", "place_owned_glow", "tag_glow_lines",
]

#: The stock script that defines ``exploder::exploder`` and ``stop_exploder``.
EXPLODER_USING = r"scripts\shared\exploder_shared"

#: Stock effects that loop (``fx/zombie/fx_powerup_on_green_zmb.efx``: every
#: element ``editorFlags looping``).  They are only ever played on a tag in the
#: stock scripts (``_zm_powerups.csc:126``), never with ``PlayFX``: a looping
#: copy played at a point has no entity to delete and never stops.
LOOPING_FX = frozenset({"powerup_on", "powerup_on_red", "powerup_on_solo", "powerup_on_caution"})

#: How close (3D, units) a static lamp may stand to an owned object before
#: Z64 reads it as that object's glow.
OWNED_GLOW_REACH = 96.0

_WATCH = "zmf_glow_watch"
_NAME = re.compile(r"[a-z_][a-z0-9_]*")


def glow_name(ident: str) -> str:
    """The exploder name for a glow id: ``zmf_glow_<id>``, lower case."""
    name = "zmf_glow_" + re.sub(r"[^a-z0-9_]", "_", ident.lower())
    if not _NAME.fullmatch(name):
        raise ValueError(f"{ident!r} makes no usable exploder name")
    return name


def glow_on(name: str) -> str:
    """The GSC statement that lights exploder glow *name* (a literal or an
    expression already quoted by the caller when ``name`` starts with ``(``)."""
    return f"exploder::exploder( {_arg(name)} );"


def glow_off(name: str) -> str:
    """The GSC statement that puts exploder glow *name* out."""
    return f"exploder::stop_exploder( {_arg(name)} );"


def _arg(name: str) -> str:
    return name[1:-1] if name.startswith("(") and name.endswith(")") else f'"{name}"'


def own_object(bp, label: str, point, *, notify: str | None = None) -> None:
    """Record a script-removed or quest object at *point* (``label`` for the
    warning, ``notify`` the level notify that ends it, if there is one)."""
    owned = getattr(bp, "owned_objects", None)
    if owned is None:
        owned = []
        bp.owned_objects = owned
    owned.append({"label": label, "point": [float(c) for c in point], "notify": notify})


def own_quest_targets(bp, quest) -> None:
    """:func:`own_object` for every target of every step of *quest* that has
    targets (shoot, knife, hit): a target is done when it is hit, and so is
    any glow on it."""
    for step in quest.steps:
        for n, target in enumerate(getattr(step, "targets", ()) or (), 1):
            own_object(bp, f"quest {quest.key} step {step.key} target {n}", tuple(target.point),
                       notify=f"zmf_q_end_{step.key}")


def place_owned_glow(bp, position, *, owner: str, off_notify: str | None,
                     on_notify: str | None = None, colour=(1.0, 1.0, 1.0), radius: float = 96.0,
                     stops: float | None = None, zone_name: str | None = None,
                     hit: tuple[str, int] | None = None, id: str) -> object:
    """A glow that belongs to *owner*: an exploder lamp, lit at start and out
    on level notify *off_notify* (lit again on *on_notify*, if given).

    ``off_notify=None`` places the switchable lamp and leaves both calls to
    the caller's own script (:func:`glow_on` / :func:`glow_off` with
    :func:`glow_name` of *id*): the recipe then owns when it is lit.  The
    owner's position is recorded for Z64 either way.  Returns the lamp.

    ``hit=(step_key, n)`` ties the glow to target *n* of a quest ``HitTargets``
    step instead: out on ``zmf_q_hit_<step>`` for that target, lit again when
    the step's countdown runs out (the quest wakes the hit notify with no
    target, ``quest._timer_functions``), and left as it is at
    ``zmf_q_end_<step>``.  *off_notify* is ignored then.
    """
    for notify in (off_notify, on_notify):
        if notify is not None and not _NAME.fullmatch(notify.lower()):
            raise ValueError(f"{notify!r} is not a notify name")
    lamp = bp.place_light(position, colour=colour, radius=radius, stops=stops,
                          zone_name=zone_name, shadows=False, id=id)
    name = glow_name(id)
    lamp.exploder = name
    if hit is not None:
        return _hit_glow(bp, lamp, name, owner, position, *hit)
    own_object(bp, owner, (position.x, position.y, position.z), notify=off_notify)
    if off_notify is None:
        bp.add_custom_logic(CustomScript(using=(EXPLODER_USING,)))
        return lamp
    functions = ()
    if not any(f.name == _WATCH for f in bp.script.custom.functions):
        functions = (CustomFunction(_WATCH, (
            'level endon( "end_game" );',
            "exploder::exploder( str_glow );",
            "while ( true )",
            "{",
            "\tlevel waittill( str_off );",
            "\texploder::stop_exploder( str_glow );",
            "\tif ( !isdefined( str_on ) )",
            "\t{",
            "\t\treturn;",
            "\t}",
            "\tlevel waittill( str_on );",
            "\texploder::exploder( str_glow );",
            "}",
        ), params=("str_glow", "str_off", "str_on"),
            purpose="A glow owned by an object: lit at start, out on the object's end notify\n"
                    "(stock exploder toggle, _zm_perk_quick_revive.gsc:185,791; P12)."),)
    on = f'"{on_notify}"' if on_notify else "undefined"
    bp.add_custom_logic(CustomScript(
        using=(EXPLODER_USING,),
        functions=functions,
        statements=((Slot.AFTER_ENTRY, f'level thread {_WATCH}( "{name}", "{off_notify}", {on} );'),),
        notes=(f"glow {name} ({owner}) goes out on {off_notify}",),
    ))
    return lamp


_WATCH_HIT = "zmf_glow_watch_hit"


def _hit_glow(bp, lamp, name: str, owner: str, position, step: str, n: int):
    if not _NAME.fullmatch(step.lower()) or int(n) < 0:
        raise ValueError(f"{step!r}/{n!r} is not a quest step key and target index")
    own_object(bp, owner, (position.x, position.y, position.z), notify=f"zmf_q_hit_{step}")
    functions = ()
    if not any(f.name == _WATCH_HIT for f in bp.script.custom.functions):
        functions = (CustomFunction(_WATCH_HIT, (
            'level endon( "end_game" );',
            "level endon( str_end );",
            "exploder::exploder( str_glow );",
            "while ( true )",
            "{",
            "	level waittill( str_hit, j, e_who );",
            "	if ( !isdefined( j ) && !isdefined( e_who ) )",
            "	{",
            "		exploder::exploder( str_glow );",
            "	}",
            "	else if ( isdefined( j ) && j == n_target )",
            "	{",
            "		exploder::stop_exploder( str_glow );",
            "	}",
            "}",
        ), params=("str_glow", "str_hit", "n_target", "str_end"),
            purpose="A quest target's glow: out when that target is hit, lit again when the\n"
                    "step's countdown resets it (stock exploder toggle; P12)."),)
    bp.add_custom_logic(CustomScript(
        using=(EXPLODER_USING,),
        functions=functions,
        statements=((Slot.AFTER_ENTRY, f'level thread {_WATCH_HIT}( "{name}", "zmf_q_hit_{step}", '
                                       f'{int(n)}, "zmf_q_end_{step}" );'),),
        notes=(f"glow {name} ({owner}) goes out when target {int(n)} of step {step} is hit",),
    ))
    return lamp


def tag_glow_lines(var: str, origin: str, fx: str) -> list[str]:
    """GSC lines for a looped effect on a fresh ``tag_origin`` script_model,
    held in *var*; delete *var* and the glow is gone.  *fx* must be a
    ``level._effect`` key."""
    return [
        f'{var} = spawn( "script_model", {origin} );',
        f'{var} SetModel( "tag_origin" );',
        f'PlayFXOnTag( level._effect[ "{fx}" ], {var}, "tag_origin" );',
    ]
