"""Models that render badly or read as the wrong thing: a deny-list every map is checked against.

A model lands here when it renders, on sight, as something it is
not (a blank panel, a fin, a slab) and a swap to another model fixed the
view.  ``Z58`` warns on every placement of one (``verify/looks.py``); the
reason says what it drew as and what replaced it, so the fix is one lookup.

Only models go here.  Brush materials that draw the wrong colour in the
preview renderer (the sugar-pine veneer drawing teal, the golden sand dark)
are a renderer question, not a map one, and are not listed.
"""

from __future__ import annotations

__all__ = ["READS_BADLY", "reads_badly"]

#: ``model -> what it drew as, where it was seen, and the replacement``.
READS_BADLY: dict[str, str] = {
    "p7_3arc_lobby_picture_41x29": (
        "draws as a flat dark grey-teal panel on every wall and at every yaw "
        "(zm_corn_maze renders; settled "
        "by one render of the zm_dmv photo room, where it hangs 55 units "
        "from p7_picture_frame_modern_01 on the same lit wall: the frame drew "
        "its painting, this drew a dark checkered teal panel, straight on and "
        "at 35 degrees); use p7_picture_frame_modern_01"
    ),
    "p7_sign_aerofarm_01": (
        "a modern indoor-farm company sign: reads as a different farm, not "
        "the map's (zm_corn_maze review); letter a board instead"
    ),
}


def reads_badly(model: str) -> str | None:
    """Why *model* is on the deny-list, or ``None``."""
    return READS_BADLY.get(model)
