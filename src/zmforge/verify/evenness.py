"""Z66: foliage spread too evenly over a room.

Plants grow in clumps: next to each other, gathered at wall feet, grave
edges, kerbs and the bases of trees, with bare ground between.  A seeded
uniform scatter reads as too even however dense it is.  The measure is the Clark-Evans
nearest-neighbour ratio *R* of a room's foliage props
(:func:`zmforge.dressing.cluster.clark_evans`, Donnelly edge-corrected over
the room's floor): about 1 for a random scatter, over 1 for a spaced one,
well under 1 for clumps.  A room with at least
:data:`~zmforge.dressing.cluster.MIN_FOLIAGE` foliage props and *R* at or
over :data:`~zmforge.dressing.cluster.EVEN_R` warns.  The helper that fixes
it is :func:`zmforge.dressing.cluster.mixed_clumps`.
"""

from __future__ import annotations

from ..dressing.cluster import EVEN_R, MIN_FOLIAGE, clark_evans, is_foliage
from .report import Report, warning

__all__ = ["CODE", "SHRUB_HEIGHT", "foliage_evenness", "check_foliage_evenness"]

CODE = "Z66"


#: A foliage prop at least this tall (its box times its scale) is a shrub:
#: the bushes and hedges the eye reads the planting by.
SHRUB_HEIGHT = 30.0


def _height(model: str, scale: float) -> float:
    from ..recipes.props import MODEL_BOX

    box = MODEL_BOX.get(model)
    return (box[1][2] - box[0][2]) * scale if box else 0.0


def foliage_evenness(blueprint) -> list[dict]:
    """Per room: its foliage count, all its props, the foliage's Clark-Evans
    *R* (``None`` under two plants), and the same for its shrubs alone
    (foliage :data:`SHRUB_HEIGHT` or taller).  A prop belongs to the room
    whose plan holds it and whose floor-to-ceiling band its height is in."""
    from ..blueprint.elements import PropScatter, Room

    rooms = []
    for room in blueprint.elements(Room):
        i = room.interior
        rooms.append((room, i.mins.x, i.mins.y, i.maxs.x, i.maxs.y, room.floor_z,
                      max(room.shell.ceiling_underside_z, room.floor_z + 64.0), [], [0], []))
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            o = prop.origin
            for r in rooms:
                if r[1] <= o.x <= r[3] and r[2] <= o.y <= r[4] and r[5] - 48.0 <= o.z <= r[6]:
                    r[8][0] += 1
                    if is_foliage(prop.model):
                        r[7].append((o.x, o.y))
                        if _height(prop.model, prop.scale) >= SHRUB_HEIGHT:
                            r[9].append((o.x, o.y))
                    break
    out = []
    for room, x0, y0, x1, y1, _f, _c, pts, n, shrubs in rooms:
        area, perim = (x1 - x0) * (y1 - y0), 2.0 * ((x1 - x0) + (y1 - y0))
        out.append({"room": room.id, "foliage": len(pts), "props": n[0],
                    "r": clark_evans(pts, area, perim), "shrubs": len(shrubs),
                    "r_shrub": clark_evans(shrubs, area, perim)})
    return out


def check_foliage_evenness(blueprint) -> Report:
    """Z66: a warning per room whose foliage is spread too evenly."""
    report = Report()
    for row in foliage_evenness(blueprint):
        r = row["r"]
        if row["foliage"] >= MIN_FOLIAGE and r is not None and r >= EVEN_R:
            report.add(warning(
                CODE,
                f"{row['foliage']} foliage props in {row['room']} are spread evenly "
                f"(Clark-Evans R {r:.2f}, at or over {EVEN_R}): plant in clumps at wall "
                f"feet, grave edges, kerbs and tree bases with bare ground between "
                f"(zmforge.dressing.cluster.mixed_clumps)",
                row["room"]))
    return report
