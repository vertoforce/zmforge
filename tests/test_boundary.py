"""Boundary walls of open-air rooms: ``add_room``'s
``wall_height``, the ``dressing.boundary_wall`` and ``dressing.backdrop``
helpers, and checks ``Z62``/``Z63``.  Each check gets a map that breaks it and
one that does not."""

from __future__ import annotations

from zmforge.blueprint.elements import Massing
from zmforge.blueprint.model import Blueprint
from zmforge.dressing import WallStyle, backdrop, boundary_wall, wall_faces
from zmforge.materials import CLIP, Material
from zmforge.spatial import Bounds, Side
from zmforge.verify.boundary import check_boundary_walls

STONE = Material("t7_stone_slate_tile_grey", 64.0)
IRON = Material("t7_metal_black_trim_01", 16.0)
STYLE = WallStyle(pier=STONE, coping=STONE, plinth=STONE, rail=IRON)


def _yard(wall_height=None):
    bp = Blueprint("zm_boundary_probe")
    room = bp.add_room(Bounds.between((0, 0, 0), (1600, 1200, 480)), roofed=False, sunlit=True,
                       wall_height=wall_height, id="yard_room")
    return bp, room


def _codes(bp, code):
    return [f for f in check_boundary_walls(bp).findings if f.code == code]


def test_wall_height_lowers_walls_and_caps_them_in_clip() -> None:
    bp, room = _yard(wall_height=176.0)
    assert {f.top for f in wall_faces(room).values()} == {176.0}
    clips = [m for m in bp.elements(Massing) if "_clip_" in m.id]
    assert len(clips) == 4
    assert all(CLIP.name in repr(m.solids[0]) for m in clips)


def test_tall_open_walls_warn_z63() -> None:
    bp, _room = _yard()
    assert _codes(bp, "Z63")


def test_low_walls_with_nothing_over_them_warn_z63() -> None:
    bp, _room = _yard(wall_height=176.0)
    found = _codes(bp, "Z63")
    assert found and "nothing stands beyond" in found[0].message


def test_backdrop_clears_z63() -> None:
    bp, room = _yard(wall_height=176.0)
    assert backdrop(bp, room, (Side.NORTH, Side.SOUTH), IRON, seed="t", spire=Side.NORTH) > 5
    assert not _codes(bp, "Z63")


def test_bare_long_wall_warns_z62() -> None:
    bp, _room = _yard(wall_height=176.0)
    assert len(_codes(bp, "Z62")) == 4


def test_boundary_wall_clears_z62_and_keeps_off_keepouts() -> None:
    bp, room = _yard(wall_height=176.0)
    for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST):
        _props, taken = boundary_wall(bp, room, side, STYLE, ground_at=lambda x, y: 16.0,
                                      seed="t", keep=((800.0, 1184.0, 80.0),))
        assert taken
    assert not _codes(bp, "Z62")
    # The keep-out at x 800 on the north wall: no plinth or pier stands in it.
    from zmforge.blueprint.model import _solid_bounds

    for m in bp.elements(Massing):
        if "_bwall_north_p" in m.id:
            b = _solid_bounds(m.solids[0])
            assert b.maxs.x <= 724.0 or b.mins.x >= 876.0, m.id   # caps overhang 3


def test_boundary_wall_is_seeded() -> None:
    def run():
        bp, room = _yard(wall_height=176.0)
        boundary_wall(bp, room, Side.SOUTH, STYLE, ground_at=lambda x, y: 16.0, seed="s")
        return sorted(m.id for m in bp.elements(Massing))
    assert run() == run()


# -- Z65: a roofed room seen over a low wall ---------------------------------
def _yard_and_chapel():
    from zmforge.dressing import link_rooms

    bp, yard = _yard(wall_height=176.0)
    chapel = bp.add_room(Bounds.between((1600, 200, 0), (2200, 1000, 416)), id="chapel_room")
    link_rooms(bp, yard, Side.EAST, chapel, Side.WEST, centre=600.0, width=112.0, height=128.0,
               bottom_z=yard.floor_z)
    return bp, yard, chapel


def _facade_codes(bp):
    from zmforge.verify.boundary import check_facades

    return [f for f in check_facades(bp).findings if f.code == "Z65"]


def test_a_bare_roofed_wall_over_a_low_wall_warns_z65() -> None:
    bp, _yard_room, _chapel = _yard_and_chapel()
    found = _facade_codes(bp)
    assert len(found) == 1 and "chapel_room west" in found[0].message


def test_facade_clears_z65_and_roofs_the_room() -> None:
    from zmforge.dressing import FacadeStyle, exposed_faces, facade

    bp, _yard_room, chapel = _yard_and_chapel()
    [west] = [e for e in exposed_faces(bp, chapel) if e.base > 1.0]
    assert west.side is Side.WEST and west.base == 176.0
    style = FacadeStyle(skins=(STONE, IRON), trim=STONE, dark=IRON, roof=STONE)
    out = facade(bp, chapel, style, seed="t")
    assert out["blocks"] > 40 and out["windows"]
    assert not _facade_codes(bp)
    roof = [m for m in bp.elements(Massing) if m.id.startswith("chapel_room_facade_roof")]
    assert len(roof) == 2
