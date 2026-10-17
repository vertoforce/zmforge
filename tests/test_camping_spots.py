"""Z46, every collision surface: no place a player stands that no zombie can hit.

A player must not be able to stand where no zombie can reach: on top of
objects, or on a stair landing.
The declared-floor flood never looked at the top of a crate or a pocket inside
a ring of tombs; :mod:`zmforge.verify.camping` does.
"""

from __future__ import annotations

from zmforge.blueprint.model import Blueprint
from zmforge.materials import Material
from zmforge.spatial import Facing, Point, Span
from zmforge.verify.camping import (
    PLAYER_CLIMB,
    ZM_MELEE_DIST,
    ZOMBIE_STEP,
    camping_spots,
    check_camping_spots,
)

ART = Material("t7_concrete_trowelled")


def _room() -> Blueprint:
    bp = Blueprint("zm_test")
    bp.add_room(Span.between(Point(0, 0, 0), Point(1024, 1024, 256)), id="hall")
    bp.set_player_start(Point(120, 120, 16), Facing.EAST)
    return bp


def _block(bp, x0, y0, x1, y1, top, **kw):
    floor = 16.0  # add_room's floor slab is the wall thickness
    return bp.add_block(Span.between(Point(x0, y0, floor), Point(x1, y1, floor + top)),
                        ART, **kw)


def _errors(bp):
    return [f for f in check_camping_spots(bp).findings if f.is_error]


def test_the_stock_numbers():
    assert PLAYER_CLIMB == 39.0      # Scale_Standards "Standing Jump ... 39"
    assert ZOMBIE_STEP == 18.0       # default_navmesh_settings maxStepHeight
    assert ZM_MELEE_DIST == 64.0     # scripts/shared/ai/zombie.gsh ZM_MELEE_DIST


def test_a_wide_top_a_player_jumps_onto_is_a_camping_spot():
    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="dais")
    errors = _errors(bp)
    assert [f.element_id for f in errors] == ["dais"]
    assert "camping spot" in errors[0].message


def test_a_narrow_top_inside_the_swing_is_kept_and_not_reported():
    # 24 across: too narrow for a navmesh island (minCharacterWidth 31), and
    # a zombie at its side is 12 + 15 from the middle, 32 below: inside 64.
    bp = _room()
    _block(bp, 400, 400, 424, 448, 32.0, id="post")
    assert _errors(bp) == []
    assert not any(f.code == "Z46" and "camping spot" in f.message
                   for f in check_camping_spots(bp).findings)


def test_a_top_wide_enough_for_a_navmesh_island_is_an_error_even_in_the_swing():
    # 48 across: every foothold is in reach, but the top can carry mesh of its
    # own, and the walkers are sent to an island they cannot path onto.
    bp = _room()
    _block(bp, 400, 400, 448, 448, 32.0, id="crate")
    assert [f.element_id for f in _errors(bp)] == ["crate"]


def test_a_clip_cap_closes_a_camping_top():
    from zmforge.verify.camping import clip_camping_tops

    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="dais")
    assert clip_camping_tops(bp) == 1
    assert _errors(bp) == []


def test_a_top_under_a_step_is_walked_onto_by_zombies():
    bp = _room()
    _block(bp, 400, 400, 600, 600, 16.0, id="plinth")
    assert _errors(bp) == []


def test_a_top_out_of_jump_reach_is_not_standing_room():
    bp = _room()
    _block(bp, 400, 400, 600, 600, 48.0, id="tall")
    assert _errors(bp) == []


def test_a_pocket_inside_a_ring_a_player_hops_is_a_camping_spot():
    # Four 32-high kerbs round a 160-square pocket: a player jumps them, a
    # walker steps 18 and cannot, and the middle is 95 from any walker.
    bp = _room()
    _block(bp, 400, 400, 592, 416, 32.0, id="ring_s")
    _block(bp, 400, 576, 592, 592, 32.0, id="ring_n")
    _block(bp, 400, 416, 416, 576, 32.0, id="ring_w")
    _block(bp, 576, 416, 592, 576, 32.0, id="ring_e")
    spots = camping_spots(bp)
    assert any(s[0].element_id == "hall" and s[0].z == 16.0 and s[2] for s in spots)
    assert any(f.element_id == "hall" for f in _errors(bp))


def test_the_same_pocket_with_a_way_in_passes():
    bp = _room()
    _block(bp, 400, 400, 592, 416, 32.0, id="ring_s")
    _block(bp, 400, 576, 592, 592, 32.0, id="ring_n")
    _block(bp, 400, 416, 416, 576, 32.0, id="ring_w")
    # the east side has a 96-wide gap a zombie walks through
    _block(bp, 576, 416, 592, 448, 32.0, id="ring_e1")
    _block(bp, 576, 544, 592, 576, 32.0, id="ring_e2")
    assert not any(f.element_id == "hall" for f in _errors(bp))


def test_a_declared_top_is_not_a_finding():
    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="stage", reachable=False)
    assert _errors(bp) == []


def test_a_solid_prop_top_counts_like_a_brush():
    from zmforge.blueprint.elements import Prop

    bp = _room()
    bp.place_props([Prop("zmf_test_table", Point(500, 500, 16), 0.0, solid=True,
                         collision_box=((-100, -100, 0), (100, 100, 34)))], id="tables")
    errors = _errors(bp)
    assert len(errors) == 1 and "zmf_test_table" in errors[0].message


def test_a_top_with_a_zombie_traversal_passes():
    from zmforge.blueprint.elements import Traversal
    from zmforge.verify.camping import reach_camping_tops

    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="dais")
    assert reach_camping_tops(bp) == (1, 0)
    [trav] = bp.elements(Traversal)
    assert trav.up == "jump_up_36" and trav.down == "jump_down_36"
    assert trav.end.z == 48.0 and trav.begin.z == 16.0
    assert _errors(bp) == []


def test_a_traversal_is_written_as_the_stock_node_pair():
    from zmforge.emit.mapfile import build_document
    from zmforge.verify.camping import reach_camping_tops

    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="dais")
    reach_camping_tops(bp)
    doc = build_document(bp)
    begin = [e for e in doc.entities if e.classname == "node_negotiation_begin"]
    end = [e for e in doc.entities if e.classname == "node_negotiation_end"]
    assert len(begin) == len(end) == 1
    assert begin[0].value("animscript") == "jump_up_36"
    assert end[0].value("animscript") == "jump_down_36"
    assert begin[0].value("target") == end[0].value("targetname")


def test_a_top_no_stock_traversal_fits_is_capped():
    from zmforge.verify.camping import clip_camping_tops, reach_camping_tops

    # A 200-square deck 120 over the floor, climbed on three 24-square posts
    # (30, 60, 90): too high for jump_up_96 from the floor, and every post is
    # too narrow for a navmesh island to begin a traversal on.
    bp = _room()
    _block(bp, 400, 400, 424, 424, 30.0, id="post1")
    _block(bp, 424, 400, 448, 424, 60.0, id="post2")
    _block(bp, 448, 400, 472, 424, 90.0, id="post3")
    from zmforge.blueprint.elements import Prop

    # the deck is a solid prop, so its cap rests on nothing Z43 counts as a
    # floor (unchecked, this gave the corn maze 134 Z43 errors)
    bp.place_props([Prop("zmf_test_deck", Point(572, 400, 16), 0.0, solid=True,
                         collision_box=((-100, -100, 0), (100, 100, 120)))], id="deck")
    assert "deck_0" in [f.element_id for f in _errors(bp)]
    made, left = reach_camping_tops(bp)
    assert made == 0 and left >= 1
    assert clip_camping_tops(bp) >= 1
    assert "deck_0" not in [f.element_id for f in _errors(bp)]
    # the cap rests on the deck, not on a floor, and Z43 is told so
    from zmforge.verify.hanging import check_nothing_hangs

    assert not [f for f in check_nothing_hangs(bp).findings
                if f.is_error and "campclip" in (f.element_id or "")]


def test_a_traversal_end_node_keeps_off_a_lamp_standing_on_the_top():
    # zm_corn_maze: an end node inside a solid hurricane lamp on a hay bale
    # fails the compile with "Could not drop node".
    from zmforge.blueprint.elements import Prop, Traversal
    from zmforge.verify.camping import NAV_ERODE, reach_camping_tops

    bp = _room()
    _block(bp, 400, 400, 600, 600, 32.0, id="dais")
    bp.place_props([Prop("zmf_test_lamp", Point(500, 420, 48), 0.0, solid=True,
                         collision_box=((-8, -8, 0), (8, 8, 24)))], id="lamp")
    reach_camping_tops(bp)
    for trav in bp.elements(Traversal):
        assert not (500 - 8 - NAV_ERODE < trav.end.x < 500 + 8 + NAV_ERODE
                    and 420 - 8 - NAV_ERODE < trav.end.y < 420 + 8 + NAV_ERODE)
    assert _errors(bp) == []


def test_an_end_node_off_the_navmesh_is_an_error():
    from zmforge.blueprint.elements import Traversal

    bp = _room()
    _block(bp, 400, 400, 431, 600, 32.0, id="bale")  # 31 wide: no mesh
    bp._install(Traversal(id="t0", begin=Point(415, 353, 16), end=Point(415, 420, 48),
                          up="jump_up_36", down="jump_down_36"))
    assert any("not on navmesh" in f.message for f in _errors(bp))


def test_a_cap_never_swallows_a_lamp_on_the_top():
    # zm_cemetery: a cap over a lamp-post top puts the lamp inside
    # a world solid (Z11).
    from zmforge.blueprint.elements import Lamp, Massing
    from zmforge.blueprint.model import _solid_bounds
    from zmforge.verify.camping import clip_camping_tops

    bp = _room()
    _block(bp, 472, 300, 488, 316, 120.0, id="post")
    bp._install(Lamp(id="post_light", position=Point(480, 308, 144)))
    _block(bp, 488, 300, 688, 500, 120.0, id="deck")
    clip_camping_tops(bp)
    for m in bp.elements(Massing):
        if "campclip" in m.id:
            b = _solid_bounds(m.solids[0])
            assert not (b.mins.x <= 480 <= b.maxs.x and b.mins.y <= 308 <= b.maxs.y
                        and b.mins.z <= 144 <= b.maxs.z)
