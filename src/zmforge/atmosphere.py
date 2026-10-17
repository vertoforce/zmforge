"""Night, sky and fog: what a map's air looks like, and where each key goes.

A generated map's air is three things the mod tools keep in three places.

**The sun/sky preset** (``ssi``) is named on ``volume_sun`` and sets the
exposure every lamp is measured against (:mod:`zmforge.lighting`).  A night
map runs a night preset: The Giant runs ``zm_factory`` (ev 5).

**The sky model** is the worldspawn's ``skyboxmodel``.  The mod tools' own
template writes ``skybox_default_day``; the night sky The Giant's prefabs
carry is ``skybox_zm_factory``
(``map_source/_prefabs/zm/zm_giant/script/zm_giant_weapons.map`` and four
other ``zm_giant`` prefab worldspawns, read).  A sun preset also
names its own sky model and the linker packs that one too, so a night preset
only links where its sky's images are (see :data:`GIANT_NIGHT_SKY`).

**The fog** is a *volume*, not a worldspawn key.  Evidence, read on
the mod tools install:

* ``map_source/_prefabs/zm/zm_giant/zm_giant_light.map:4344-4362`` is a
  ``volume_worldfog`` entity: one brush textured ``fog``, keys ``fsi``,
  ``fsi_1`` .. ``fsi_4`` (one fog asset per lighting state), ``fogtime``
  (the blend time, seconds), ``BANK_1``/``BANK_2``, ``LIGHTSTATE_1`` ..
  ``LIGHTSTATE_4``, ``ENABLE_SUN_FOG``, ``DISABLE_FOG``, ``AUTO_PRIORITY`` and
  ``spawnflags "14851"``.  Lines ``25792-25809`` of the same file are a second
  one with ``priority "2"`` over one part of the map: fog volumes nest.
* The worldspawn of ``map_source/zm/zm_giant.map`` names ``"fsi" "default"``
  and ``"fogtime" "1"`` -- the map-wide fallback, not the look.
* ``fsi`` names an entry in ``source_data/fog.gdt`` (definition
  ``deffiles/fog.awi``).  25 entries ship; the ones a zombies map can name
  are :data:`STOCK_FOGS`, with the fields that decide how they look read off
  that file.

So a map gets fog by one ``volume_worldfog`` over its playable space naming a
shipped fog asset.  ``zm_factory_afog`` is the ground fog: its ``halfheight``
of 264 (``fog.gdt:895-941``) means the density halves every 264 units up, so
it pools in the low ground and thins over a hilltop -- which is what "rolling
hills of fog" is on a heightfield.

**Packing.**  Fog is not a linked asset: no asset list in the install has a
``fog`` row (395 shipped ``zone_source`` asset lists grepped), and
the linker's list for zm_cemetery has none either.  The compiler writes the
fog settings into the level itself: ``zm_cemetery.d3dbsp`` carries the name
``zm_factory_afog`` five times, the way it carries the sun preset.

**Correction.**  That ``volume_worldfog`` is not the fog The Giant shows.  The asset
it names, ``zm_factory_afog``, has ``"worldfog" "0"``, ``"litfog" "0"`` and
``"sunfog" "0"`` (``fog.gdt:895-941``): it is atmospheric scattering only,
whose sun haze starts at ``atmospherehazebasedist`` 61000 units, far past any
generated map.  So the height/distance fields above (``halfheight`` 264) are
never switched on by it, and in a map a few thousand units across it draws
next to nothing.  ``deffiles/fog.awi:5-8`` is where the four switches
(``worldfog``, ``sunfog``, ``litfog``, ``atmospherefog``) gate which fields
apply.

The ground fog you can see in The Giant is **lit fog**: a ``volume_litfog``
(``zm_giant_light.map:4136-4154``, brush ``litfog_volume``) over the whole
map, x -3070..4463, y -2895..6248, z 3..3075 by its planes, naming
``zm_factory_volumetric`` (``fog.gdt:1083-1129``: ``"litfog" "1"``, half
density at 1250 units, halving every 300 units up from z 0, a cold blue
``fogcolor`` 0.67 0.74 0.99).  The engine lights it with the sun and the
lamps, which is why it reads at night.  Small nested ``volume_litfog``
brushes (``zm_giant_light.map:30411``, ``30771``) sit inside the big one for
local pockets; The Giant's dog rounds swap to ``zm_factory_dogs_volumetric``
(``fog.gdt:1036``: half density at 650 units, ``fogintensity`` 5), the
densest shipped lit fog a zombies map has.

So a map now gets visible fog from :attr:`Atmosphere.lit_fog`: one
``volume_litfog`` over the playable space, plus optional denser pockets
(``Enclosure.lit_fog_pockets``).  The ``volume_worldfog`` stays as it was.

**Unverified in play:** how dense the lit fog reads at ev 5 in these maps.
Nothing here writes a fog asset of its own.

**Gloom: grade and exposure, both worldspawn keys.**
The worldspawn of ``map_source/zm/zm_giant.map`` carries, besides ``fsi``:
``"bloom" "zm_factory"``, ``"vcolor" "zm_factory"``, ``"lutmaterial"
"luts_t7_zm_factory"``, ``"evauto" "1"``, ``"evcmp" "2.5"``, ``"evmax"
"3.5"``, ``"evmin" "3"`` and ``"secondsLerpToDarker"`` /
``"secondsLerpToLighter"`` ``"1"``.

* ``vcolor`` and ``bloom`` name a colour grade and a bloom grade: a ``.lvi``
  file in ``share/raw/grades`` (the ``pbg_box`` definition in
  ``bin/t7.def.json`` says so for its own ``color_lvi`` / ``bloom_lvi``:
  ``"filePath": "%TA_GAME_PATH%/share/raw/grades"``, ``"fileExtension":
  "lvi"``).  The files are binary (``LV20`` header), so a map can only name a
  shipped one: :data:`STOCK_GRADES`.
* ``lutmaterial`` names a ``material.gdf`` entry in ``texture_assets/luts.gdt``.
  ``luts_t7_zm_factory`` needs ``texture_assets\\t7_luts\\t7_mp_apartments_lut.tif``,
  which a tools tree set up under Wine may lack (``t7_luts`` can hold only
  ``lut_curve.tif``), and a missing image stops the link.  Not used.
* ``evauto`` / ``evmin`` / ``evmax`` / ``evcmp`` are the auto exposure
  (the mod tools' lighting parameters document: "evmin (minimum global
  exposure value)", "evmax (maximum global exposure value)").
  :attr:`Atmosphere.exposure_stops` pins the exposure by setting
  ``evmin`` = ``evmax`` = the sun preset's ``ev`` plus that many stops.  A
  higher ev is a darker picture: ev is the scene brightness the camera is set
  for (day presets run ev 12-15, the night one ev 5, :mod:`zmforge.lighting`),
  so a lamp placed at the preset's ev reads half a stop dimmer under a pin
  half a stop higher.  **Unverified in play**, including the sign: the
  in-game check is in ``docs/fog-and-gloom.md``.

Also supported by the engine and not used here: ``volume_exposure`` (a
brush volume with the same ``evmin``/``evmax``/``evcmp`` keys, for one
area), ``volume_worldfogmodifier`` (scales a world fog's ``depthscale``,
``heightscale``, ``opacity`` and tints it with ``_color``), ``pbg_box`` /
``pbg_omni`` / ``pbg_spot`` (a grade for one area), and the client script
calls ``SetLitFogBank``, ``SetWorldFogActiveBank``, ``SetExposureActiveBank``
and ``SetPBGActiveBank`` that switch banks at run time
(``scripts/zm/zm_giant_fx.csc:169-178`` does it for dog rounds).

**Lit fog colour.**  In ``deffiles/fog.awi`` the ``fogcolor`` field sits
inside ``if ( worldFog )``; a lit fog has ``"worldfog" "0"``, so its colour is
the colour of the light it scatters (lamps, moon), darkened and tinted by
``extcolor`` where ``albedo`` is under 1.  The Giant's lit fog is not blue by
itself; it takes the colour of the lamps around it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = [
    "FogFacts",
    "STOCK_FOGS",
    "Atmosphere",
    "NIGHT_GROUND_FOG",
    "GIANT_NIGHT_SKY",
    "DUSK_GROUND_FOG",
    "DAY_CLEAR",
    "FOG_VOLUME_KEYS",
    "fog_volume_pairs",
    "LitFogFacts",
    "STOCK_LIT_FOGS",
    "NIGHT_LIT_GROUND_FOG",
    "CRYPT_LIT_FOG",
    "LIT_FOG_VOLUME_KEYS",
    "lit_fog_volume_pairs",
    "STOCK_GRADES",
    "NIGHT_GLOOM",
    "HARVEST_HAZE",
    "CLINIC_COLD",
    "OFFICE_DAY",
    "worldspawn_pairs",
]


@dataclass(frozen=True)
class FogFacts:
    """The fields of one ``fog.gdt`` entry that decide how it looks.

    ``halfdist``: distance at which the fog is half opaque; ``basedist``: how
    far from the eye it starts; ``halfheight``: height over which its
    density halves (small = ground fog); ``colour``: ``fogcolor``, linear RGB.
    ``line`` is where the entry starts in ``source_data/fog.gdt``.
    """

    halfdist: float
    basedist: float
    halfheight: float
    opacity: float
    colour: tuple[float, float, float]
    line: int


#: The shipped fog assets a zombies map has reason to name, read off
#: ``source_data/fog.gdt`` (entry start line in ``line``).
STOCK_FOGS: Mapping[str, FogFacts] = {
    "default": FogFacts(1024.0, 0.0, 1.0, 0.0, (0.735, 0.735, 0.735), 2),
    "zm_factory_afog": FogFacts(3358.0, 700.0, 264.0, 0.5, (0.709, 0.917, 0.941), 895),
}


@dataclass(frozen=True)
class LitFogFacts:
    """The fields of one ``litfog`` entry of ``fog.gdt`` that decide how it looks.

    ``halfdist``: distance at which it is half opaque; ``halfheight``: height
    over which its density halves, measured up from ``baseheight`` (world z);
    ``intensity``: ``fogintensity``; ``colour``: ``fogcolor``.  ``line`` is
    where the entry starts in ``source_data/fog.gdt``.
    """

    halfdist: float
    halfheight: float
    baseheight: float
    intensity: float
    colour: tuple[float, float, float]
    line: int
    #: ``albedo``: 1 scatters all the light it catches; under 1 it absorbs
    #: the rest, tinted by ``extcolor`` (``extinction``), so it dims.
    albedo: float = 1.0
    extinction: tuple[float, float, float] = (0.0, 0.0, 0.0)


#: The shipped lit fogs (``"litfog" "1"``) a zombies map has reason to name,
#: read off ``source_data/fog.gdt``.
STOCK_LIT_FOGS: Mapping[str, LitFogFacts] = {
    "zm_factory_volumetric": LitFogFacts(1250.0, 300.0, 0.0, 1.0, (0.665, 0.737, 0.991), 1083),
    "zm_factory_dogs_volumetric": LitFogFacts(650.0, 1500.0, 0.0, 5.0,
                                              (0.665, 0.737, 0.991), 1036),
    # A multiplayer map's lit fog, read.  Fog is compiled into the
    # level, not linked, so a zombies map can name it like The Giant's.  Half
    # opaque at 2000 units, nearly flat with height, and it absorbs 60 % of
    # the light it catches (albedo 0.4) with a blue extinction colour: a cold
    # haze that dims the far end of a corridor.
    "mp_apartments_volumetric": LitFogFacts(2000.0, 3000.0, 0.0, 1.0, (1.0, 1.0, 1.0), 190,
                                            albedo=0.4, extinction=(0.427, 0.656, 1.0)),
}

#: Shipped colour/bloom grades (``share/raw/grades/<name>.lvi``) a map can
#: name on its worldspawn ``vcolor`` / ``bloom``.  ``zm_factory`` is the one
#: The Giant's own worldspawn names; the other 25 files are multiplayer and
#: teleporter grades whose look has not been checked in a zombies map.
STOCK_GRADES: Mapping[str, str] = {
    "zm_factory": "share/raw/grades/zm_factory.lvi",
}


@dataclass(frozen=True)
class Atmosphere:
    """One map's air: the sun preset, the sky model and the fog asset.

    ``fog`` names a :data:`STOCK_FOGS` entry, or ``None`` for no fog volume.
    ``fog_states`` is the asset per lighting state 1..4 (``fsi_1`` ..
    ``fsi_4``); left empty, every state uses ``fog``.
    """

    sun_preset: str = "default_day"
    skybox: str | None = None
    fog: str | None = None
    fog_states: tuple[str, str, str, str] | None = None
    fog_time: float = 1.0
    #: A :data:`STOCK_LIT_FOGS` entry for a ``volume_litfog`` over the
    #: playable space (the fog you can see), or ``None`` for none.
    lit_fog: str | None = None
    #: A :data:`STOCK_GRADES` name for the worldspawn ``vcolor`` and
    #: ``bloom`` (the colour grade), or ``None`` for the engine default.
    grade: str | None = None
    #: Pin the exposure this many stops above the sun preset's ``ev``
    #: (positive = darker, see the module docstring), or ``None`` to leave the
    #: worldspawn without ``ev*`` keys.
    exposure_stops: float | None = None

    def __post_init__(self) -> None:
        if self.grade is not None and self.grade not in STOCK_GRADES:
            raise ValueError(
                f"grade {self.grade!r} is not a shipped .lvi this package names; "
                f"known: {', '.join(sorted(STOCK_GRADES))}"
            )
        if self.exposure_stops is not None and not -3.0 <= self.exposure_stops <= 3.0:
            raise ValueError("exposure_stops is a small offset in stops (-3..3)")
        if self.lit_fog is not None and self.lit_fog not in STOCK_LIT_FOGS:
            raise ValueError(
                f"lit fog asset {self.lit_fog!r} is not one this package has read in "
                f"source_data/fog.gdt; known: {', '.join(sorted(STOCK_LIT_FOGS))}"
            )
        if self.fog is not None and self.fog not in STOCK_FOGS:
            raise ValueError(
                f"fog asset {self.fog!r} is not one this package has read in "
                f"source_data/fog.gdt; known: {', '.join(sorted(STOCK_FOGS))}"
            )
        for state in self.fog_states or ():
            if state not in STOCK_FOGS:
                raise ValueError(f"fog asset {state!r} is not in STOCK_FOGS")
        if self.fog_time < 0.0:
            raise ValueError("fog_time is a blend time in seconds and cannot be negative")


#: The Giant's night sky model, which the ``zm_factory`` sun preset names
#: itself (``source_data/ssi.gdt:2823`` onward: ``"skyboxmodel"
#: "skybox_zm_factory"``), so the linker packs it whatever the worldspawn
#: says.  Its images (``model_export\t7_skybox\zm_factory\...``) must be present
#: in the tools tree: a link without them stops
#: on ``ERROR: image 'skybox_zm_factory_ft' is missing``; the folder holds
#: seven .exr files from the stock mod tools install.  ``default_night`` names ``skybox_default_night``, whose
#: images are the same files.
GIANT_NIGHT_SKY = "skybox_zm_factory"

#: A night map in ground fog: The Giant's sun preset (ev 5) and sky, and the
#: shipped ground fog that pools in hollows (see the module docstring).  Needs
#: the zm_factory sky images in ``model_export`` (:data:`GIANT_NIGHT_SKY`).
NIGHT_GROUND_FOG = Atmosphere(
    sun_preset="zm_factory",
    skybox=GIANT_NIGHT_SKY,
    fog="zm_factory_afog",
)

#: :data:`NIGHT_GROUND_FOG` plus the lit ground fog The Giant shows
#: (``zm_factory_volumetric``, see the module docstring): the one to use when
#: the fog should be seen.  Added; the corn maze still runs
#: :data:`NIGHT_GROUND_FOG`.
NIGHT_LIT_GROUND_FOG = Atmosphere(
    sun_preset="zm_factory",
    skybox=GIANT_NIGHT_SKY,
    fog="zm_factory_afog",
    lit_fog="zm_factory_volumetric",
)

#: The thick pocket for an underground space: The Giant's dog-round lit fog,
#: twice as dense by distance and five times as bright as the ground fog, and
#: it barely thins with height (``halfheight`` 1500).
CRYPT_LIT_FOG = "zm_factory_dogs_volumetric"

#: The darkest air that links without the zm_factory sky images: the sunset preset
#: (ev 12.5; of the 93 presets only the four day ones name a sky whose images
#: are in ``model_export/t7_skybox/skybox_default/``) under the same ground
#: fog.  Dusk, not night.
DUSK_GROUND_FOG = Atmosphere(
    sun_preset="default_sunset",
    skybox="skybox_default_sunset",
    fog="zm_factory_afog",
)

#: What a map gets when it names nothing: the template's day, no fog volume.
DAY_CLEAR = Atmosphere()

# ---------------------------------------------------------------------------
# Per-recipe looks.  All unverified in play.
# ---------------------------------------------------------------------------

#: The cemetery at night: The Giant's lit ground fog pooling in the low
#: ground, The Giant's own colour/bloom grade, and the exposure pinned half a
#: stop darker than the preset's ev 5.
NIGHT_GLOOM = Atmosphere(
    sun_preset="zm_factory",
    skybox=GIANT_NIGHT_SKY,
    fog="zm_factory_afog",
    lit_fog="zm_factory_volumetric",
    grade="zm_factory",
    exposure_stops=0.5,
)

#: The corn maze: the same low lit fog, which boosts the moon's scatter two
#: stops (``sunintensityscale`` 2) and takes the colour of the golden moon and
#: the orange lanterns.  No grade and no exposure pin: this map is dark
#: already.
HARVEST_HAZE = Atmosphere(
    sun_preset="zm_factory",
    skybox=GIANT_NIGHT_SKY,
    fog="zm_factory_afog",
    lit_fog="zm_factory_volumetric",
)

#: A test map: indoors under the template's day, a cold absorbing
#: haze (``mp_apartments_volumetric``) and the exposure half a stop darker.
#: No grade: no shipped cold grade is known.
CLINIC_COLD = Atmosphere(
    lit_fog="mp_apartments_volumetric",
    exposure_stops=0.5,
)

#: The DMV stays a lit office: the template's day, no fog, no gloom.
OFFICE_DAY = DAY_CLEAR


def worldspawn_pairs(sun_preset: str, grade: str | None,
                     exposure_stops: float | None) -> list[tuple[str, str]]:
    """The worldspawn keys an atmosphere's gloom adds (none by default).

    Named the way ``map_source/zm/zm_giant.map``'s worldspawn names them:
    ``vcolor`` and ``bloom`` for the grade; ``evauto``, ``evmin``,
    ``evmax`` and ``evcmp`` for the exposure.
    """
    pairs: list[tuple[str, str]] = []
    if grade is not None:
        if grade not in STOCK_GRADES:
            raise ValueError(f"grade {grade!r} is not in STOCK_GRADES")
        pairs += [("vcolor", grade), ("bloom", grade)]
    if exposure_stops is not None:
        from .lighting import SSI_EXPOSURE

        # No fallback: pinning to a guessed ev could be stops off.
        if sun_preset not in SSI_EXPOSURE:
            raise ValueError(f"no measured ev for sun preset {sun_preset!r}; "
                             "cannot pin the exposure relative to it")
        ev = f"{SSI_EXPOSURE[sun_preset] + float(exposure_stops):g}"
        pairs += [("evauto", "1"), ("evmin", ev), ("evmax", ev), ("evcmp", "0")]
    return pairs

#: The fixed keys of a ``volume_worldfog``, as ``zm_giant_light.map:4346-4362``
#: writes them (the per-state ``fsi`` keys and ``fogtime`` are added per map).
FOG_VOLUME_KEYS: tuple[tuple[str, str], ...] = (
    ("BANK_1", "1"),
    ("BANK_2", "1"),
    ("DISABLE_FOG", "0"),
    ("ENABLE_SUN_FOG", "1"),
    ("LIGHTSTATE_1", "1"),
    ("LIGHTSTATE_2", "1"),
    ("LIGHTSTATE_3", "1"),
    ("LIGHTSTATE_4", "1"),
    ("AUTO_PRIORITY", "1"),
    ("spawnflags", "14851"),
)


def fog_volume_pairs(fog: str, fog_time: float = 1.0,
                     states: tuple[str, str, str, str] | None = None) -> list[tuple[str, str]]:
    """Every key a ``volume_worldfog`` naming *fog* carries.

    The Giant turns states 3 and 4 off on its fog volume and falls back to
    the worldspawn's ``default``; a generated map has one look, so all four
    states are on and all four name the same asset unless *states* says
    otherwise.
    """
    per_state = states or (fog, fog, fog, fog)
    time = f"{float(fog_time):g}"
    pairs = [("fsi", fog)]
    pairs += [(f"fsi_{index}", name) for index, name in enumerate(per_state, start=1)]
    pairs.append(("fogtime", time))
    pairs += list(FOG_VOLUME_KEYS)
    return pairs


#: The fixed keys of a ``volume_litfog``, as ``zm_giant_light.map:4136-4154``
#: writes them (the per-state ``fsi`` keys and ``fogtime`` are added per
#: volume).  All four lighting states are on here: a generated map has one
#: look (The Giant turns 3 and 4 off and names ``default`` for them).
LIT_FOG_VOLUME_KEYS: tuple[tuple[str, str], ...] = (
    ("BANK_1", "1"),
    ("BANK_2", "1"),
    ("LIGHTSTATE_1", "1"),
    ("LIGHTSTATE_2", "1"),
    ("LIGHTSTATE_3", "1"),
    ("LIGHTSTATE_4", "1"),
    ("AUTO_PRIORITY", "1"),
    ("ENABLE_LIGHTS", "1"),
    ("ENABLE_SUN", "1"),
    ("ambientColor", "0 0 0"),
    ("ambientIntensity", "1"),
    ("spawnflags", "14435"),
)


def lit_fog_volume_pairs(fog: str, fog_time: float = 1.0, *,
                         priority: int | None = None) -> list[tuple[str, str]]:
    """Every key a ``volume_litfog`` naming *fog* carries.

    ``priority`` is for a pocket nested inside the map-wide volume: The
    Giant's nested fog volume writes ``"priority" "2"`` next to
    ``AUTO_PRIORITY`` (``zm_giant_light.map:25802``).
    """
    if fog not in STOCK_LIT_FOGS:
        raise ValueError(f"lit fog asset {fog!r} is not in STOCK_LIT_FOGS")
    pairs = [("fsi", fog)]
    pairs += [(f"fsi_{index}", fog) for index in range(1, 5)]
    pairs.append(("fogtime", f"{float(fog_time):g}"))
    pairs += list(LIT_FOG_VOLUME_KEYS)
    if priority is not None:
        pairs.append(("priority", str(int(priority))))
    return pairs
