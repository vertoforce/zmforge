"""Map-wide litter variety: keep every litter model under Z74's cap.

``Z74`` (``verify.layout_rules``) warns when one litter-named model (``paper``,
``cup_``, ``bottle``, ``trash``...) is placed more than ``LITTER_CAP`` (40)
times in a map: one piece of rubbish repeated reads as a texture, not as a
mess.  A test map placed ``p7_office_paper_stack_sml`` 214 times and the
coffee mug 123, because every room's litter helper draws from a
short list of its own.

:func:`vary_litter` runs once, after every room is dressed.  It walks the
placements of each over-cap model in a spread-out order (so the copies it
keeps are all over the map, not the first room's), keeps the first
``cap``, and swaps each of the rest (one on a desk or shelf only for a model at
least as big in plan: a smaller one there read as floating, Z44) for the least-used model of the same
family (:data:`FAMILIES`) that is no bigger in plan and no taller than the
original plus a little, so it fits where the original lay without reaching
onto a neighbour; the swap keeps the footprint centre, the turn and the
underside height.  Families mix in non-litter models (books lying flat,
clothes, newspapers' neighbours), which have no cap.  A placement with no
candidate left is thinned (removed) when *thin* is set, as Z74 suggests.
Returns ``(swapped, thinned)``.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace
from typing import Sequence

__all__ = ["FAMILIES", "vary_litter"]

#: Swap families: a model in the key's family may become any of these.
#: Flat sheets and folders, crumpled and torn paper, cups and bottles.
FAMILIES: dict[str, tuple[str, ...]] = {
    "flat": ("p7_office_paper_sheet_01", "p7_office_paper_sheet_02", "p7_office_paper_sheet_03",
             "p7_office_paper_sheet_08", "p7_office_paper_sheet_09", "p7_office_paper_sheet_10",
             "p7_office_paper_sheet_12", "p7_office_paper_folder_blue", "p7_office_paper_folder_pink",
             "p7_office_paper_stack_sml", "p7_box_copy_paper_sheet", "p7_cleaning_paper_brown",
             "p7_cleaning_paper_towel", "p7_debris_newspaper_01", "p7_debris_newspaper_02",
             "p7_debris_newspaper_03", "p7_debris_newspaper_04", "p7_debris_newspaper_05",
             "p7_debris_newspaper_06", "p7_book_office_binder_open",
             # not litter, no cap: books lying flat
             "p7_book_vintage_01", "p7_book_vintage_02", "p7_book_vintage_03", "p7_book_vintage_04",
             "p7_book_vintage_05", "p7_book_vintage_06", "p7_book_vintage_open_01",
             "p7_book_vintage_open_04", "p7_desk_metal_old_01_drawer_small_01"),
    "crumpled": ("p7_debris_trash_paper_02", "p7_debris_trash_paper_03", "p7_debris_trash_paper_04",
                 "p7_debris_trash_paper_05", "p7_debris_trash_paper_08", "p7_debris_trash_paper_09",
                 "p7_debris_trash_paper_10", "p7_cleaning_paper_ball_brown",
                 "p7_cleaning_paper_folded_wrapped", "p7_debris_paper_sheet_01"),
    "vessel": ("p7_cup_coffee_mug", "p7_debris_trash_cup_coffee_02", "p7_debris_trash_cup_red_02",
               "p7_bottle_plastic_16oz_water", "p7_bottle_plastic_soap_orange_clean",
               "p7_bottle_glass_liquor_01", "p7_bottle_glass_liquor_03", "p7_bottle_glass_wine_01",
               "p7_decanter_glass_bottle", "p7_container_bottle_wine_01"),
}


def _family(model: str) -> str | None:
    for name, members in FAMILIES.items():
        if model in members:
            return name
    return None


def _spread_order(n: int) -> list[int]:
    """0..n-1 in bit-reversed order: the first k of it are spread evenly
    over the whole run, whatever k is."""
    bits = max(1, (n - 1).bit_length())
    order = sorted(range(1 << bits), key=lambda i: int(f"{i:0{bits}b}"[::-1], 2))
    return [i for i in order if i < n]


def vary_litter(bp, *, cap: int | None = None, thin: bool = True, grow: float = 1.1,
                taller: float = 4.0, skip: Sequence[str] = ()) -> tuple[int, int]:
    """Swap (or thin) every litter placement past *cap* per model in *bp*
    (see the module docstring).  *grow* is how much bigger in plan a swap may
    be (1.1: a tenth), *taller* how many units taller; *skip* scatter-id
    prefixes to leave alone (a vignette whose parts are counted on)."""
    from ..blueprint.elements import PropScatter
    from ..recipes.props import MODEL_BOX
    from ..verify.layout_rules import LITTER_CAP, LITTER_TOKENS

    cap = LITTER_CAP if cap is None else cap
    litter = lambda m: any(t in m.lower() for t in LITTER_TOKENS)  # noqa: E731
    scatters = list(bp.elements(PropScatter))
    where: dict[str, list[tuple[int, int]]] = {}
    counts: Counter = Counter()
    for si, sc in enumerate(scatters):
        if any(sc.id.startswith(p) for p in skip):
            continue
        for pi, p in enumerate(sc.props):
            if litter(p.model):
                where.setdefault(p.model, []).append((si, pi))
    for sc in scatters:
        for p in sc.props:
            counts[p.model] += 1

    from ..blueprint.elements import Room

    rooms = [r for r in bp.elements(Room)]

    def on_floor(p) -> bool:
        """Lying on a room's floor (a swap on a shelf or desk can leave the
        new model floating by Z44's reading of what is under it)."""
        box = MODEL_BOX.get(p.model)
        if box is None:
            return False
        under = p.origin.z + box[0][2] * p.scale
        for r in rooms:
            i = r.interior
            if i.mins.x <= p.origin.x <= i.maxs.x and i.mins.y <= p.origin.y <= i.maxs.y \
                    and abs(under - r.floor_z) <= 1.5:
                return True
        return False

    tops = [(p.origin.x, p.origin.y, p.origin.z + MODEL_BOX[p.model][0][2] * p.scale, p.id)
            for sc in scatters for p in sc.props if p.model in MODEL_BOX]

    def carries(p) -> bool:
        """Something rests on *p* (a folder on a paper stack): swapping or
        thinning *p* would leave it floating."""
        (lx, ly, _lz), (hx, hy, hz) = MODEL_BOX[p.model]
        r = max(hx - lx, hy - ly) * p.scale / 2.0 + 1.0
        top = p.origin.z + hz * p.scale
        bottom = p.origin.z + _lz * p.scale
        return any(abs(x - p.origin.x) < r and abs(y - p.origin.y) < r and abs(z - top) <= 1.5
                   and z > bottom + 0.5 and ident != p.id for x, y, z, ident in tops)

    def dims(m: str):
        (lx, ly, lz), (hx, hy, hz) = MODEL_BOX[m]
        return hx - lx, hy - ly, hz - lz

    swapped = thinned = 0
    drop: dict[int, set[int]] = {}
    for model in sorted(where, key=lambda m: -len(where[m])):
        spots = where[model]
        if counts[model] <= cap or model not in MODEL_BOX:
            continue
        fam = _family(model)
        w0, d0, h0 = dims(model)
        big0 = max(w0, d0) * grow + 1.0
        area0 = w0 * d0 * grow * grow + 1.0
        pool = [m for m in (FAMILIES[fam] if fam else ()) if m != model and m in MODEL_BOX]
        pool = [m for m in pool if max(dims(m)[:2]) <= big0 and dims(m)[0] * dims(m)[1] <= area0
                and dims(m)[2] <= h0 + taller]
        order = _spread_order(len(spots))
        for k in order[cap:]:
            if counts[model] <= cap:
                break
            si, pi = spots[k]
            p = scatters[si].props[pi]
            if carries(p):
                continue
            floor = on_floor(p)
            free = [m for m in pool if (not litter(m) or counts[m] < cap)
                    and (floor or (min(dims(m)[:2]) >= min(w0, d0)
                                   and max(dims(m)[:2]) >= max(w0, d0)))]
            if not floor and not free:
                continue
            if free:
                new = min(free, key=lambda m: (counts[m], m))
                scatters[si].props[pi] = _swap(p, new, MODEL_BOX)
                counts[new] += 1
                counts[model] -= 1
                swapped += 1
            elif thin:
                drop.setdefault(si, set()).add(pi)
                counts[model] -= 1
                thinned += 1
    for si, gone in drop.items():
        sc = scatters[si]
        sc.props = [p for i, p in enumerate(sc.props) if i not in gone]
    return swapped, thinned


def _swap(prop, model: str, boxes):
    """*prop* as *model*: same footprint centre, turn and underside."""
    (ol, oh), (nl, nh) = boxes[prop.model], boxes[model]
    s = prop.scale
    c, sn = math.cos(math.radians(prop.yaw)), math.sin(math.radians(prop.yaw))

    def centre(lo, hi):
        mx, my = (lo[0] + hi[0]) / 2.0 * s, (lo[1] + hi[1]) / 2.0 * s
        return mx * c - my * sn, mx * sn + my * c

    ox, oy = centre(ol, oh)
    nx, ny = centre(nl, nh)
    o = prop.origin
    at = type(o)(o.x + ox - nx, o.y + oy - ny, o.z + (ol[2] - nl[2]) * s)
    return replace(prop, model=model, origin=at, collision_box=None if not prop.solid else prop.collision_box)
