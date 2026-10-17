"""Fire, smoke and embers: stock looping effects placed like Radiant does.

``burning``, ``smouldering`` and ``embers`` each put a Radiant
``fx`` entity (:class:`zmforge.blueprint.elements.AmbientFx`) at a spot and
declare the effect in the zone, so the linker packs it; ``burning`` also
lights the spot with a warm, shadowless lamp, because every stock fire is a
light pool (``docs/map-design-method.md``, "Light pools and FX").

Only effects measured to link on the local mod tools are offered.  The stock
``.efx`` sources all ship under ``share/raw/fx``, but many reference images
the mod tools do not ship (``texture_assets/gfx/*.tif``), and the linker then
fails the map.  :data:`LINKED_FX` is the set that linked with no error in a
real link of the ``zm_fxprobe`` probe (eight effects, no effect
error).  An
effect that already ships in ``zm_common`` (``zone_source/all/assetlist``)
must **not** be listed in the zone: listing it makes the linker rebuild it
and fail on the same missing images (``animals/fx_bio_fly_dark_50x50`` did).
"""

from __future__ import annotations

from ..blueprint.elements import AmbientFx
from ..spatial import Point

__all__ = [
    "LINKED_FX",
    "FIRE",
    "SMOULDER",
    "EMBERS",
    "FIRE_LIGHT",
    "place_fx",
    "burning",
    "smouldering",
    "embers",
]

#: Fire by size: a pile of burning rubble, a window on fire, a lamp flame.
FIRE = {
    "small": "fire/fx_fire_ground_rubble_embers_50x50",
    "window": "fire/fx_fire_window_embers_100x100",
    "window_small": "fire/fx_fire_window_embers_50x100",
}
#: Smoke for something that burned out: a low smoulder, hot ground, a plume
#: for the skyline.
SMOULDER = {
    "smoulder": "smoke/fx_smk_smolder_lg",
    "ground": "smoke/fx_smk_hot_ground_md",
    "plume": "smoke/fx_smk_plume_4000_slow_black",
    "line": "smoke/fx_smk_line_60",
}
#: Ember lines rising off a fire or a burnt edge.
EMBERS = {"line": "fire/fx_fire_line_embers_50"}
#: No fly effect linked clean (fx_bio_fly_light_100x100 and _multicolor_200x200
#: miss fxt_bio_fly_top; fx_bio_fly_dark_50x50 is in zm_common and fails when
#: listed), so flies are not offered yet.

#: Every effect this module may place; each linked clean.
LINKED_FX = frozenset({*FIRE.values(), *SMOULDER.values(), *EMBERS.values()})

#: A fire's lamp: warm orange (the stock fire lights run about 1.0 0.36 0.16
#: to 1.0 0.51 0.29), shadowless so it does not spend a shadow slice.
FIRE_LIGHT = (1.0, 0.45, 0.2)


def place_fx(bp, at, fx: str, *, id: str | None = None, pitch: float = -90.0,
             yaw: float = 0.0, note: str = "") -> AmbientFx:
    """Place one stock effect at *at* and declare it in the zone."""
    if fx not in LINKED_FX:
        raise ValueError(f"{fx!r} is not in LINKED_FX (measured to link clean in a usermap); "
                         "add it only after a clean link")
    point = at if isinstance(at, Point) else Point(*at)
    element = AmbientFx(id=bp._claim("fx", id), position=point, fx=fx, pitch=pitch,
                        yaw=yaw, note=note)
    bp._install(element)
    bp.declare_asset("fx", fx)
    return element


def burning(bp, at, *, size: str = "small", light: bool = True, radius: float = 320.0,
            smoke: bool = True, id: str | None = None, note: str = "burning") -> list:
    """A fire: flames, embers rising off them, smoke over, and a warm light pool."""
    point = at if isinstance(at, Point) else Point(*at)
    out = [place_fx(bp, point, FIRE[size], id=id, note=note)]
    out.append(place_fx(bp, point, EMBERS["line"], note=f"{note} embers"))
    if smoke:
        out.append(place_fx(bp, Point(point.x, point.y, point.z + 48.0), SMOULDER["smoulder"],
                            note=f"{note} smoke"))
    if light:
        out.append(bp.place_light(Point(point.x, point.y, point.z + 40.0), colour=FIRE_LIGHT,
                                  radius=radius, shadows=False))
    return out


def smouldering(bp, at, *, plume: bool = False, id: str | None = None,
                note: str = "smouldering") -> list:
    """Something that burned out: low smoke and hot ground, a plume if it is on the skyline."""
    point = at if isinstance(at, Point) else Point(*at)
    out = [place_fx(bp, point, SMOULDER["smoulder"], id=id, note=note),
           place_fx(bp, point, SMOULDER["ground"], note=f"{note} ground")]
    if plume:
        out.append(place_fx(bp, point, SMOULDER["plume"], note=f"{note} plume"))
    return out


def embers(bp, at, *, id: str | None = None, note: str = "embers") -> AmbientFx:
    """Embers drifting up off a burnt edge, with no flame."""
    return place_fx(bp, at, EMBERS["line"], id=id, note=note)

