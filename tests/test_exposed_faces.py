"""Z84: an undrawn (caulk) face of a drawn box, open to room air, is a hole
the player looks through -- for example a raised step with a caulk back,
which floats when seen from behind."""

from __future__ import annotations

from zmforge.blueprint.elements import Room
from zmforge.materials import CAULK, FaceMaterials, Material
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Bounds, Side
from zmforge.verify import check_blueprint
from zmforge.verify.exposed_faces import check_exposed_faces, open_undrawn_faces

CARPET = Material("t7_concrete_pebbles_cracked", 32.0)
PANEL = Material("t7_wood_panel_01", 64.0)


def _room(bp):
    room = next(iter(bp.elements(Room)))
    return room.interior, room.floor_z


def _tier(bp, x0, x1, y0, y1, f, h, per_side, id):
    bp.add_block(Bounds.between((x0, y0, f), (x1, y1, f + h)),
                 FaceMaterials(default=CAULK, per_side=per_side), walkable=True, id=id)


def test_a_tier_with_a_caulk_back_is_refused() -> None:
    bp = three_room_map("zm_face_probe")
    box, f = _room(bp)
    cx, cy = (box.mins.x + box.maxs.x) / 2.0, (box.mins.y + box.maxs.y) / 2.0
    _tier(bp, cx - 64, cx + 64, cy - 64, cy + 64, f, 48.0,
          {Side.TOP: CARPET, Side.EAST: PANEL, Side.NORTH: PANEL, Side.SOUTH: PANEL}, "tier")
    found = [(m, side) for m, side, *_ in open_undrawn_faces(bp) if m == "tier"]
    assert found == [("tier", "west")]
    assert any(e.code == "Z84" for e in check_exposed_faces(bp).errors)
    assert any(e.code == "Z84" for e in check_blueprint(bp).errors)


def test_a_fully_panelled_tier_and_a_hidden_caulk_back_pass() -> None:
    bp = three_room_map("zm_face_probe")
    box, f = _room(bp)
    cx, cy = (box.mins.x + box.maxs.x) / 2.0, (box.mins.y + box.maxs.y) / 2.0
    _tier(bp, cx - 64, cx + 64, cy - 64, cy + 64, f, 48.0,
          {Side.TOP: CARPET, Side.EAST: PANEL, Side.WEST: PANEL,
           Side.NORTH: PANEL, Side.SOUTH: PANEL}, "panelled")
    # Against the west wall: its caulk back faces the wall, not the room.
    _tier(bp, box.mins.x, box.mins.x + 64, cy + 96, cy + 160, f, 40.0,
          {Side.TOP: CARPET, Side.EAST: PANEL, Side.NORTH: PANEL, Side.SOUTH: PANEL},
          "counter")
    # Two stepped tiers: the lower one's caulk back is covered by the higher.
    _tier(bp, cx - 64, cx, cy - 256, cy - 128, f, 32.0,
          {Side.TOP: CARPET, Side.EAST: PANEL, Side.WEST: PANEL,
           Side.NORTH: PANEL, Side.SOUTH: PANEL}, "upper")
    _tier(bp, cx, cx + 64, cy - 256, cy - 128, f, 16.0,
          {Side.TOP: CARPET, Side.EAST: PANEL, Side.NORTH: PANEL, Side.SOUTH: PANEL},
          "lower")
    assert [m for m, *_ in open_undrawn_faces(bp)
            if m in {"panelled", "counter", "upper", "lower"}] == []


