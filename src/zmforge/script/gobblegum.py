"""GobbleGum machines, on for four players or fewer and off above that.

WHAT THE STOCK FRAMEWORK ALREADY DOES
-------------------------------------
A usermap gets GobbleGum from the framework with no script of its own:

* ``zm_usermap.gsc:97`` ``DEFAULT(level.bgb_in_use,true);`` in the
  ``autoexec opt_in``, and ``zm_usermap.csc:64`` the same on the client.
* ``share/zone_source/zm_levelcommon.zone:67-68`` ``include,zm_bgb_machine``
  and ``zbarrier,zmcore_bgb_machine``, plus the machine's fx at ``:119-130``.
* The machine itself is the stock prefab
  ``map_source/_prefabs/zm/zm_core/vending_bgb_struct.map``: one clip brush
  and one ``zbarrier_zmcore_bgb_machine`` with ``targetname
  "bgb_machine_use"`` (``:42-43``), six pieces.  No trigger and no struct: the
  trigger is spawned by ``_zm_bgb_machine``, whose source the mod tools install does
  not ship (``share/raw/scripts/zm/_zm_bgb_machine.gsc`` is a six-line stub).
* Treyarch's own placement, ``_prefabs/zm/zm_giant/script/
  zm_giant_bgb_machines.map``, stamps five of those prefabs and marks two
  ``"script_noteworthy" "start_bgb_machine"`` (``:38``, ``:55``).

WHY IT IS DECIDED AT RUNTIME, AND ONLY FOR THE MACHINES
-------------------------------------------------------
``level.bgb_in_use`` is read once, in ``bgb::__init__`` (a system
``__init__``, before the map's ``main``), which registers seven
``clientuimodel`` fields when it is true (decompiled ``_zm_bgb.gsc:56-71``;
the client half registers the same list, and the two lists must agree).  The
player count is not known then, so the system itself cannot follow it: a map
built for eight seats and played by three must keep it on.  What *can*
follow it is the machines, which are ordinary entities with unitriggers.

So the gate hides every ``bgb_machine_use`` zbarrier piece and unregisters
every unitrigger stub within :data:`STUB_RADIUS` of one
(``_zm_unitrigger.gsc:173-217`` deletes the live trigger and drops the stub
from every list), at the end of the intro and on every poll after, once more
than :data:`MAX_BGB_PLAYERS` are in the game.  It is one-way for the match:
the stub's think function belongs to the unshipped machine script, so there
is nothing to register it again with.  A gum a player already chewed keeps
working; nobody can buy another.

Why above four at all: the only evidence on the mod tools install is second-hand -- the
Zombies Experience mod page (Workshop 2383464164), quoted in
``docs/map-generator-spec.md``, says GobbleGums do not function in an
eight-player game and seats 5-8 get no HUD.  Nothing in the decompiled
``_zm_bgb.gsc`` sizes an array by four; **the concrete cause is
unverified**.

**Unverified in play.**  Nothing here has been run in the game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ..errors import InteractiveBlocked
from ..spatial import Facing, Point
from .custom import CustomFunction, CustomScript, Slot

if TYPE_CHECKING:  # pragma: no cover
    from ..blueprint.elements import Machine
    from ..blueprint.model import Blueprint

__all__ = [
    "MAX_BGB_PLAYERS",
    "STUB_RADIUS",
    "DEFAULT_GOBBLEGUMS",
    "gobblegum_machines",
    "place_gobblegum_machines",
    "gobblegum_gate",
]

#: The most players a game may have and keep its GobbleGum machines.
MAX_BGB_PLAYERS = 4
#: How close to a machine's origin a unitrigger stub is taken to be its own.
#: The machine is 32 units square (the prefab's clip, ``x, y in [-16, 16]``);
#: :data:`CLEAR_OF_OTHERS` keeps every other interactive further out than this.
STUB_RADIUS = 72.0
#: No other interactive's origin within this of a gobblegum machine, so the
#: gate's radius test can only ever find the machine's own trigger.
CLEAR_OF_OTHERS = 128.0
#: Machines on a map when its recipe does not say.
DEFAULT_GOBBLEGUMS = 2
#: Along the anchor's wall, how far from it a machine is tried, nearest first.
_OFFSETS = (128.0, 160.0, 192.0, 224.0, 256.0, 288.0, 320.0)
#: The machine's floor may differ from the anchor's by at most this.
_FLOOR_TOLERANCE = 6.0

TARGETNAME = "bgb_machine_use"
_UNITRIGGER = r"scripts\zm\_zm_unitrigger"
_FLAG = r"scripts\shared\flag_shared"


def gobblegum_machines(bp: "Blueprint") -> list["Machine"]:
    """Every gobblegum machine on ``bp``, in placement order."""
    from ..blueprint.elements import Machine

    return [m for m in bp.elements(Machine) if m.perk.slug == "gobblegum"]


def _interactive_origins(bp: "Blueprint") -> list[tuple[str, Point]]:
    from ..blueprint.elements import (Machine, MysteryBox, PowerSwitch,
                                      WallWeapon, Wunderfizz)

    out = []
    for kind in (Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz):
        for element in bp.elements(kind):
            position = getattr(element, "position", None)
            if position is not None:
                out.append((element.id, position))
    return out


def _clear_of_others(bp: "Blueprint", at: Point, skip: str | None = None) -> bool:
    limit = CLEAR_OF_OTHERS * CLEAR_OF_OTHERS
    for ident, p in _interactive_origins(bp):
        if ident == skip:
            continue
        if abs(p.z - at.z) < 96.0 and (p.x - at.x) ** 2 + (p.y - at.y) ** 2 < limit:
            return False
    return True


def _room_of(bp: "Blueprint", at: Point):
    from ..blueprint.elements import Room
    from ..verify.looks import _room_at

    rooms = [r for r in bp.elements(Room) if r.reachable]
    return _room_at(rooms, at.x, at.y, at.z + 8.0)


def _candidates(anchor) -> Iterable[Point]:
    """Spots beside ``anchor`` on its own wall line, nearest first."""
    facing: Facing = anchor.facing
    step = facing.step
    along = Point(-step.y, step.x, 0.0)  # the wall's direction
    for offset in _OFFSETS:
        for sign in (1.0, -1.0):
            yield Point(anchor.position.x + along.x * offset * sign,
                        anchor.position.y + along.y * offset * sign,
                        anchor.position.z)


def _wall_candidates(bp: "Blueprint", first: Point) -> Iterable[tuple[Point, Facing]]:
    """The fallback: along every reachable room's four walls, 20 units in and
    facing into the room, rooms nearest ``first`` first, every 32 units."""
    from ..blueprint.elements import Room

    rooms = [r for r in bp.elements(Room) if r.reachable]

    def centre_distance(room) -> float:
        box = room.interior
        cx, cy = (box.mins.x + box.maxs.x) / 2.0, (box.mins.y + box.maxs.y) / 2.0
        return (cx - first.x) ** 2 + (cy - first.y) ** 2 + (room.floor_z - first.z) ** 2

    for room in sorted(rooms, key=centre_distance):
        box = room.interior
        inset = 20.0
        x0, x1 = box.mins.x + 48.0, box.maxs.x - 48.0
        y0, y1 = box.mins.y + 48.0, box.maxs.y - 48.0
        z = room.floor_z
        xs = [x0 + 32.0 * i for i in range(int((x1 - x0) // 32.0) + 1)]
        ys = [y0 + 32.0 * i for i in range(int((y1 - y0) // 32.0) + 1)]
        for x in xs:
            yield Point(x, box.maxs.y - inset, z), Facing.SOUTH
            yield Point(x, box.mins.y + inset, z), Facing.NORTH
        for y in ys:
            yield Point(box.maxs.x - inset, y, z), Facing.WEST
            yield Point(box.mins.x + inset, y, z), Facing.EAST


def _fits(bp: "Blueprint", at: Point, facing: Facing, anchor_at: Point) -> Point | None:
    """``at`` on the floor, if a machine there is in the same room as
    ``anchor_at`` and on its floor, clear of every other interactive, of every
    floor prop, and blocks no interactive's stand; else ``None``."""
    from ..blueprint import reach
    from ..blueprint.catalogue import perk_named
    from ..blueprint.elements import Machine

    ground = bp.ground_under(at.x, at.y, below=at.z + 32.0)
    if not ground.found or not ground.reachable:
        return None
    if abs(ground.z - anchor_at.z) > _FLOOR_TOLERANCE:
        return None
    # Flat ground only: the cemetery test holds every interactive to a
    # terrain spread of 1 unit (test_cemetery.py:208; zm_cemetery).
    if ground.spread > 1.0:
        return None
    spot = Point(at.x, at.y, ground.z)
    room = _room_of(bp, spot)
    if room is None or room is not _room_of(bp, anchor_at):
        return None
    if not _clear_of_others(bp, spot):
        return None
    probe = Machine(id="gobblegum_probe", perk=perk_named("gobblegum"),
                    position=spot, facing=facing)
    keep = reach.keep_of(probe)
    if keep is not None and reach.first_clash(keep, bp.interactive_keeps()) is not None:
        return None
    if keep is not None and _body_hits_a_prop(bp, keep.body):
        return None
    if _front_hits_brushwork(bp, probe, ground.z):
        return None
    return spot


def _world_boxes(bp: "Blueprint") -> list:
    """Bounding boxes of every world solid, as ``Z9`` reads them; cached on
    the blueprint for one placement run (see :func:`place_gobblegum_machines`)."""
    cached = getattr(bp, "_zmf_bgb_world_boxes", None)
    if cached is None:
        from ..solids import inspect_solid

        cached = [b for b in (inspect_solid(solid).bounds() for solid in bp.world_solids())
                  if b is not None]
        bp._zmf_bgb_world_boxes = cached
    return cached


def _front_hits_brushwork(bp: "Blueprint", probe, floor_z: float) -> bool:
    """The two ``Z9`` questions a spot must pass, asked with the checker's own
    boxes (:mod:`zmforge.verify.model`): the 64 units in front of the machine
    clear of every world solid (``_check_machine_clearance``), with floor at
    the machine's height under the stand; and no brushwork in the front half
    of its body (``_check_interactives_have_their_backs_to_the_wall``).
    Found on zm_cemetery: two machines on a wall line whose stands
    ran into a solid."""
    from ..blueprint import reach
    from ..verify.model import (STEP_TOLERANCE, _approach_box,
                                _interactive_body)

    boxes = _world_boxes(bp)
    stand = _approach_box(probe, floor_z)
    if any(b.overlaps(stand, slack=0.0) for b in boxes):
        return True
    centre = stand.centre
    under = bp.ground_under(centre.x, centre.y, below=probe.position.z)
    if not under.found or abs(under.z - floor_z) > STEP_TOLERANCE:
        return True
    body = reach.BODIES["machine"]
    front = _interactive_body(probe, body, front=body.front, back=0.0,
                              half_width=body.half_width)
    return any(b.overlaps(front, slack=0.0) for b in boxes)


def _prop_box(prop):
    """World ``(x0, y0, z0, x1, y1, z1)`` of any prop with a measured box --
    floor, wall or ceiling, since a bulletin board hung at 88 units is inside
    a 96-unit machine too (zm_dmv) -- or ``None``.  The same
    arithmetic as :func:`zmforge.blueprint.lanes._prop_span`, without its
    floor-only filter."""
    import math

    from ..blueprint.lanes import _table
    from ..props.origins import drawn_box

    local = drawn_box(prop.model, prop.collision_box) or _table().get(prop.model)
    if local is None:
        return None
    (x0, y0, z0), (x1, y1, z1) = local
    scale = prop.scale
    angle = math.radians(prop.yaw)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx = (x0 + x1) / 2.0 * scale
    cy = (y0 + y1) / 2.0 * scale
    wx = prop.origin.x + cx * cos_a - cy * sin_a
    wy = prop.origin.y + cx * sin_a + cy * cos_a
    hx = ((x1 - x0) * abs(cos_a) + (y1 - y0) * abs(sin_a)) * scale / 2.0
    hy = ((x1 - x0) * abs(sin_a) + (y1 - y0) * abs(cos_a)) * scale / 2.0
    return (wx - hx, wy - hy, prop.origin.z + z0 * scale,
            wx + hx, wy + hy, prop.origin.z + z1 * scale)


def _body_hits_a_prop(bp: "Blueprint", body) -> bool:
    """Does a floor prop stand inside the machine's own body (``Z44``)?  The
    lane rule clears the apron in front (:mod:`zmforge.blueprint.lanes`); the
    body is this placer's to keep clear, by not going there."""
    from ..blueprint.elements import PropScatter

    cx = (body.mins.x + body.maxs.x) / 2.0
    cy = (body.mins.y + body.maxs.y) / 2.0
    for prop in (p for scatter in bp.elements(PropScatter) for p in scatter.props):
        if abs(prop.origin.x - cx) > 160.0 or abs(prop.origin.y - cy) > 160.0:
            continue
        span = _prop_box(prop)
        if span is None:
            continue
        x0, y0, z0, x1, y1, z1 = span
        if (x0 < body.maxs.x and x1 > body.mins.x and y0 < body.maxs.y
                and y1 > body.mins.y and z0 < body.maxs.z and z1 > body.mins.z):
            return True
    return False


def place_gobblegum_machines(
    bp: "Blueprint",
    count: int | None = None,
    *,
    spots: Iterable[tuple[Point, Facing]] = (),
    gate: bool = True,
) -> list["Machine"]:
    """Make ``bp`` carry ``count`` gobblegum machines and the four-player gate.

    Machines the recipe already placed count toward ``count``.  ``spots``
    are tried first, as given; the rest go beside the mystery boxes (the
    starting box first), on the box's own wall line and facing its way, at
    the first offset in :data:`_OFFSETS` that keeps the machine on the box's
    floor, in the box's room, :data:`CLEAR_OF_OTHERS` from every other
    interactive and out of every interactive's stand (the model's own
    refusal, :meth:`Blueprint._refuse_a_blocked_interactive`) and clear of
    every floor prop's box.  When the boxes' walls are full, any reachable
    room's wall is tried, 20 units in and facing the room, nearest the
    starting box first (:func:`_wall_candidates`).  The approach
    lane and the play lamp come from the blueprint as for any machine:
    :func:`zmforge.blueprint.lanes.enforce` clears props from the lane when
    the machine goes in, and ``light_rooms`` lights it, so call this before
    that.  ``count=0`` places nothing and emits no gate.

    Raises :class:`ValueError` when fewer than ``count`` fit, naming how many
    did, rather than shipping a map with fewer than asked for.
    """
    from ..blueprint.elements import MysteryBox

    bp._zmf_bgb_world_boxes = None  # the solids as they stand now
    want = DEFAULT_GOBBLEGUMS if count is None else int(count)
    if want < 0:
        raise ValueError(f"gobblegum count {want} is negative")
    have = gobblegum_machines(bp)
    placed: list = []
    for point, facing in spots:
        if len(have) + len(placed) >= want:
            break
        facing = Facing.of(facing)
        if not _clear_of_others(bp, point):
            raise ValueError(f"gobblegum spot {point}: another interactive within "
                             f"{CLEAR_OF_OTHERS:g} units")
        machine = bp.place_perk("gobblegum", point, facing,
                                id=f"gobblegum_{len(have) + len(placed) + 1}")
        if _front_hits_brushwork(bp, machine, point.z):
            raise ValueError(f"gobblegum spot {point}: brushwork in its body front or "
                             "its 64-unit stand, or no floor there (Z9)")
        placed.append(machine)
    boxes = sorted(bp.elements(MysteryBox), key=lambda b: (not b.starting, b.id))
    # Round-robin: one machine beside each box, then a second beside each.
    for box in [b for _round in range(2) for b in boxes]:
        if len(have) + len(placed) >= want:
            break
        for at in _candidates(box):
            if _try(bp, at, box.facing, box.position, have, placed):
                break
    # Fallback, when the boxes' own walls are full: any room's wall, nearest
    # the starting box first.
    if len(have) + len(placed) < want and boxes:
        for at, facing in _wall_candidates(bp, boxes[0].position):
            if len(have) + len(placed) >= want:
                break
            _try(bp, at, facing, at, have, placed)
    total = len(have) + len(placed)
    if total < want:
        raise ValueError(f"asked for {want} gobblegum machine(s) and only {total} fit "
                         f"beside the {len(boxes)} mystery box(es) or on a room wall; "
                         "pass spots=")
    if gate and total:
        message = bp.add_map_string(
            "ZMF_BGB_OFF",
            f"More than {MAX_BGB_PLAYERS} players: GobbleGum machines are off")
        bp.add_custom_logic(gobblegum_gate(message))
    return have + placed


def _try(bp, at: Point, facing: Facing, anchor_at: Point, have, placed) -> bool:
    spot = _fits(bp, at, facing, anchor_at)
    if spot is None:
        return False
    try:
        placed.append(bp.place_perk("gobblegum", spot, facing,
                                    id=f"gobblegum_{len(have) + len(placed) + 1}"))
    except InteractiveBlocked:
        return False
    return True


def gobblegum_gate(message: str, *, limit: int = MAX_BGB_PLAYERS) -> CustomScript:
    """The runtime gate: over ``limit`` players, hide the machines and pull
    their triggers, and say so once.

    Polled once a second from the end of the intro (``initial_blackscreen_
    passed``, the flag ``_zm.gsc`` sets when the players can move), so a
    fifth player joining mid-game switches the machines off within a second.
    One-way for the match; see the module docstring.
    """
    radius_sq = int(STUB_RADIUS * STUB_RADIUS)
    gate = CustomFunction(
        "zmf_bgb_gate",
        (
            'level endon( "end_game" );',
            'level flag::wait_till( "initial_blackscreen_passed" );',
            f"while ( GetPlayers().size <= {int(limit)} )",
            "{",
            "\twait 1;",
            "}",
            "level.zmf_bgb_off = true;",
            "foreach ( e_player in GetPlayers() )",
            "{",
            f'\te_player IPrintLnBold( &"{message}" );',
            "}",
            "while ( true )",
            "{",
            "\tzmf_bgb_hide_all();",
            "\twait 1;",
            "}",
        ),
        purpose=(f"GobbleGum off above {int(limit)} players: poll the count "
                 "from the end of the intro; once over, hide the machines and "
                 "pull their triggers every second for the rest of the match."),
    )
    hide = CustomFunction(
        "zmf_bgb_hide_all",
        (
            f'a_machines = GetEntArray( "{TARGETNAME}", "targetname" );',
            "foreach ( e_machine in a_machines )",
            "{",
            "\tfor ( i = 0; i < e_machine GetNumZBarrierPieces(); i++ )",
            "\t{",
            "\t\te_machine HideZBarrierPiece( i );",
            "\t}",
            "\te_machine Hide();",
            "\tif ( !isdefined( level._unitriggers ) || !isdefined( level._unitriggers.trigger_stubs ) )",
            "\t{",
            "\t\tcontinue;",
            "\t}",
            "\ta_stubs = [];",
            "\tforeach ( s_each in level._unitriggers.trigger_stubs )",
            "\t{",
            "\t\ta_stubs[ a_stubs.size ] = s_each;",
            "\t}",
            "\tforeach ( s_stub in a_stubs )",
            "\t{",
            "\t\tif ( !isdefined( s_stub ) || !isdefined( s_stub.origin ) )",
            "\t\t{",
            "\t\t\tcontinue;",
            "\t\t}",
            "\t\tif ( Abs( s_stub.origin[2] - e_machine.origin[2] ) > 96 )",
            "\t\t{",
            "\t\t\tcontinue;",
            "\t\t}",
            f"\t\tif ( Distance2DSquared( s_stub.origin, e_machine.origin ) <= {radius_sq} )",
            "\t\t{",
            "\t\t\tzm_unitrigger::unregister_unitrigger( s_stub );",
            "\t\t}",
            "\t}",
            "}",
        ),
        purpose=(f'Hide every "{TARGETNAME}" zbarrier and unregister each '
                 f"unitrigger stub within {STUB_RADIUS:g} units of one "
                 "(_zm_unitrigger.gsc:173-217)."),
    )
    return CustomScript(
        using=(_FLAG, _UNITRIGGER),
        functions=(gate, hide),
        # From the zone hook, as every thread that waits on a flag (the
        # zone hook runs after main returns and after every flag the map
        # waits on exists).
        statements=((Slot.ZONE_HOOK, "level thread zmf_bgb_gate();"),),
        notes=(f"GobbleGum gate: machines off above {int(limit)} players (unverified in play)",),
    )
