"""How bright a lamp has to be, measured from the shipped maps.

Everything here is a number read off Treyarch's own content in the mod
tools, not a preference.  It exists because the generator's
first lit map came out nearly black, and the reason was a single number in
the wrong unit system.

The unit
--------
A ``light`` entity's brightness is its ``"stops"`` key, and the name is
literal: it is **log2 of the emitter's intensity**.  Read the values off
``_prefabs/zm/zm_giant/zm_giant_light.map`` and they are not round numbers,
they are logarithms of round ones::

    stops 3.32192809488736  = log2(10)
    stops 4.64385618977472  = log2(25)     <- the most common value, 57 lights
    stops 5.64385618977472  = log2(50)     <- second most common, 55 lights
    stops 6.64385618977473  = log2(100)
    stops 7.22881869049588  = log2(150)
    stops 7.96578428466209  = log2(250)
    stops 8.96578428466209  = log2(500)
    stops 9.96578428466209  = log2(1000)
    stops 12.2877123795495  = log2(5000)

So one stop is a factor of two, and the difference between two lamps is a
ratio, never a difference in brightness you can reason about additively.

Why it has to track the sky preset
----------------------------------
A lamp's stops means nothing on its own: what reaches the screen is the
lamp's intensity measured against the camera's exposure, and the exposure
comes from the map's sun/sky preset (the ``ssi`` asset named on the
worldspawn and on ``volume_sun``).  Those presets are in
``source_data/ssi.gdt`` and each carries an ``ev``.  Measured:

    ==================  ====  ==========  =========
    ssi preset            ev  sun stops   enablesun
    ==================  ====  ==========  =========
    default_day           15        14            1
    default_morning     13.5      11.3            1
    default_sunset      12.5        11            1
    default_night          6      -2.2            1
    zm_factory             5        -2            1
    zm_zod                 4      -2.5            0
    mp_sector          12.75      13.3            1
    ==================  ====  ==========  =========

Now put the shipped lamps beside the exposure of the map they are in:

* ``zm_giant`` runs ``ssi zm_factory``, **ev 5**.  Its 543 lamps peak at
  ``stops`` 4.64 and 5.64 and run up to about 10.
* ``mp_sector`` and ``mp_combine`` run ``ssi mp_sector``, **ev 12.75**.
  Their 275 lamps peak at ``stops`` 15 and 16, band 13 to 17.

Two maps ten stops apart in exposure carry lamps ten stops apart in
intensity.  **A lamp's stops sits at its map's exposure ev, give or take a
few stops up.**  That is the rule this module encodes, and it is why the
generator's old fixed ``stops 4`` produced a black map: 4 is right for a
night map like The Giant and is **eleven stops -- 2048x -- under** what a
map running ``default_day`` needs.

What the shipped maps do *not* do
---------------------------------
They do not fill a dark map in with an ambient term.  ``volume_sun`` has a
``global_fill_color``/``global_fill_intensity`` pair, and across all 741
shipped ``.map`` files it appears four times, always as
``"global_fill_color" "0 0 0"`` -- black.  Interiors are lit with many point
lights at an intensity matched to the exposure, and nothing else, so that is
what the generator does too.

Density
-------
``zm_giant_light.map``'s 536 non-skybox lamps span 4304 x 6389 units: one
lamp per 51,300 square units, a 226 x 226 patch.  They are stacked at each
fixture (536 lamps in 360 distinct 32-unit cells), so fixture density is
nearer one per 76,000 square units, a 276 x 276 patch, and fixture-to-fixture
spacing runs a median of 48 with a 90th percentile of 190.
:data:`MAX_LAMP_SPACING` is set to sit inside that band.

Reflection probes
-----------------
A ``reflection_probe`` is not a gloss decoration, and the tools' own entity
database says so.  In ``bin\\t7.def.json`` the probe's keys are grouped, and
the group that holds most of them is called ``2_DIFFUSE_GI``:
``ao_range``/``ao_strength``/``ao_power`` (ambient occlusion),
``inpaint_occluded_rays``, ``brightnessAdjust`` (described as scaling the
*bounce* brightness during the bake) and ``virtual`` (a probe that is not
exported but still feeds other probes' bake data).  The class description,
paraphrased: it captures a cube map at its origin and applies it, with
computed occlusion, to what its volume contains.  So a probe carries the indirect solve for the volume
it covers, and geometry no probe covers has none.

Nothing in the toolchain complains about a map with none: ``cod2map64.exe``
knows the classname and has no zero-probe message, and neither does the
linker.  It is a silent quality floor, and the floor is set by the tools
themselves -- ``rex/templates/ZM Mod Level/map_source/zm/template.map``, the
map a freshly created zombies level starts from, carries exactly one
(entity 26, ``"name" "probe"``, origin ``4 4 132``).  A generated map with
zero probes starts below the blank map.

The template's probe is the *unsized* default, ``size_min`` and ``size_max``
both ``72 72 72`` -- a 144-unit cube, which covers 0.4% of a three-room
generated map by volume.  What shipped content does instead is size the box
to the space: the 23 probes in the community map ``zm_alien_isolation.map``
run 110 to 2164 units per axis, 20 of the 23 with at least one axis over 200,
and heights clustered at 90 to 270 -- room extents, not a fixed cube.  So the
generator sizes each probe's box to the room it sits in.

``size_min`` and ``size_max`` are half-extents (the database describes them
as the area of effect on the negative and the positive side), so a box that encloses a room is
half that room's interior size on each key.
:data:`PROBE_PLAY_SPACE_LIMIT` is the one hard rule the database states about
them: ``in_play_space`` is unavailable once every side is over 1000.
"""

from __future__ import annotations

from typing import Mapping

__all__ = [
    "SSI_EXPOSURE",
    "DEFAULT_SSI",
    "STOPS_OVER_EXPOSURE",
    "SHIPPED_STOPS_OVER_EXPOSURE",
    "MAX_LAMP_SPACING",
    "CEILING_CLEARANCE",
    "LAMP_FAR_EDGE",
    "useful_reach",
    "GLOW_RADIUS",
    "is_glow",
    "fill_radius",
    "FILL_DROP",
    "fill_boost",
    "PROBE_PLAY_SPACE_LIMIT",
    "probe_in_play_space",
    "SUN_SHADOW_SPLIT_DISTANCE",
    "SUN_SHADOW_SPLIT_COUNT",
    "OMNI_SHADOW_SLICES",
    "omni_shadow_slices",
    "exposure_of",
    "default_stops",
    "intensity_of",
]

#: The ``ev`` each sun/sky preset declares, read from
#: ``source_data/ssi.gdt`` (the gdf is ``ssi.gdf``; 93 presets ship, these
#: are the ones a generated map has any reason to name).
SSI_EXPOSURE: Mapping[str, float] = {
    "default_day": 15.0,
    "default_morning": 13.5,
    "default_sunset": 12.5,
    "default_night": 6.0,
    "zm_factory": 5.0,
    "zm_zod": 4.0,
    "mp_sector": 12.75,
}

#: What :meth:`zmforge.blueprint.model.Blueprint.enclose` names by default,
#: and therefore the exposure a map gets when nobody chooses one.
DEFAULT_SSI = "default_day"

#: Where a lamp's ``stops`` sits relative to its map's exposure.  Zero: at
#: it.  The Giant is at ev + 0.0 to ev + 0.6 at its peak; mp_sector is at
#: ev + 2.3 to ev + 3.3.  Zero is the bottom of the shipped range, which is
#: the conservative end for a generator that also uses radii two to six
#: times larger than either map's (340 to 900 against 5 to 350), since reach
#: at a fixed intensity only ever adds light.
STOPS_OVER_EXPOSURE = 0.0

#: The band the shipped maps actually occupy, as an offset from their own
#: map's exposure ev.  The low end is mp_sector's dimmest fixture lamp
#: (stops 13 at ev 12.75); the high end is its brightest (stops 17).  A lamp
#: outside this band is what the conformance check Z11 reports.
SHIPPED_STOPS_OVER_EXPOSURE = (-0.5, 4.5)

#: No point on a room's floor should be further than this from a lamp, in
#: plan.  Between The Giant's 226-unit lamp patch and its 276-unit fixture
#: patch, rounded to the grid.
MAX_LAMP_SPACING = 256.0

#: How far below the ceiling's underside an automatically placed lamp hangs.
#: Spec 4.11: a lamp inside the ceiling slab lights nothing.
CEILING_CLEARANCE = 40.0

#: The ``far_edge`` every emitted lamp carries.  ``t7.def.json``'s ``light``
#: template calls it "the width of the transition region for cut-off ... mapped
#: to equal the cuton and radius(cutoff) range", so a lamp of radius *r* is at
#: full inverse-square strength out to ``r * (1 - far_edge)`` and is then ramped
#: to nothing by *r*.  It lives here rather than only in the emitter's key table
#: because the placement rule below is stated in terms of it.
LAMP_FAR_EDGE = 0.5


#: A lamp with a radius under this is a *glow* -- a sensor's red pip, a
#: warning light, an indicator -- and not a room light.  It is never the
#: style a room's fill lamps copy and it never counts as lighting a patch of
#: floor.  Measured: when a room's first lamp is a sensor glow (radius 72,
#: colour 1 0.12 0.08), a fill grid that copies it lays seven radius-72 red
#: pips 120 units over the floor, and the only real light left in the room
#: is the day through its windows.  A radius-140 glow does the same.  256 is
#: :data:`zmforge.blueprint.autolamp.MIN_RADIUS`, the smallest radius a play
#: lamp may copy, and :data:`MAX_LAMP_SPACING`.
GLOW_RADIUS = 256.0


def is_glow(radius: float) -> bool:
    """Whether a lamp of this radius is a glow rather than a room light."""
    return radius < GLOW_RADIUS


def fill_radius(drop: float, spacing: float = MAX_LAMP_SPACING,
                far_edge: float = LAMP_FAR_EDGE) -> float:
    """The smallest radius a fill lamp *drop* units over the floor needs.

    A fill lamp stands on a grid ``spacing`` apart, so the furthest floor it
    answers for is half a grid diagonal away in plan and *drop* below; that
    point has to be inside the lamp's :func:`useful_reach`, or the cut-off
    ramp takes the light before inverse square does.  Radius-300 fill hung
    248 units over a floor has a useful reach of 150, so the floor gets only
    the ramp's tail (``D8`` estimate 0.05).
    """
    import math

    half_diagonal = spacing / math.sqrt(2.0)
    return math.hypot(drop, half_diagonal) / (1.0 - far_edge)


#: How far over the floor a fill lamp hangs in an ordinary room (a 192-unit
#: storey: ceiling underside 176, less :data:`CEILING_CLEARANCE`, over a floor
#: at 16 is 120; 128 rounds it).  A fill lamp hung further up is brightened by
#: :func:`fill_boost` so its floor gets the same light.
FILL_DROP = 128.0
#: The most :func:`fill_boost` adds, in stops.
FILL_BOOST_MAX = 2.0


def fill_boost(drop: float) -> float:
    """Stops over the map's exposure for a fill lamp *drop* units over its floor.

    Inverse square: a lamp twice as high puts a quarter of the light on the
    floor under it, so it is made 2 stops brighter, and every room's floor
    gets the light an ordinary storey's does.  Measured with ``D8``: a tall
    room's fill hung 248 over its floor estimates 0.40 against 0.9 to 1.5 in
    storey-high rooms, and its light reads as flat and brown.  Capped at
    :data:`FILL_BOOST_MAX`; a room taller than one grid step gets tiers
    instead (:meth:`zmforge.blueprint.model.Blueprint._lamp_tiers`).
    """
    import math

    if drop <= FILL_DROP:
        return 0.0
    return min(FILL_BOOST_MAX, 2.0 * math.log2(drop / FILL_DROP))


def useful_reach(radius: float, far_edge: float = LAMP_FAR_EDGE) -> float:
    """How far a lamp of this radius carries before the cut-off ramp starts.

    Past this distance the lamp is being faded out by ``far_edge`` on top of
    the inverse-square term, so a surface further away than this is not lit by
    it in any useful sense however large its ``radius`` is.

    It is a ceiling on a lamp's reach and **not** the distance at which a lamp
    is still worth having: inverse square has already taken most of the light
    long before the ramp starts.  Measured: a radius-900 lamp hung
    856 units above a floor is inside its own ``useful_reach`` of 450 only by
    the ramp's reckoning, and delivers 2.5e-4 of its peak there -- twelve
    stops down.  What a lamp has to be *near* to light it
    is :data:`MAX_LAMP_SPACING`, on all three axes; see
    :meth:`zmforge.blueprint.model.Blueprint._lamp_tiers`.  This function is
    for asking whether a lamp reaches a point at all, not how well.
    """
    return radius * (1.0 - far_edge)

#: Above this, on *every* axis at once, a reflection probe may not claim to be
#: in play space.  ``bin\\t7.def.json``'s ``reflection_probe`` template, key
#: ``in_play_space``, paraphrased: the probe is in play space and boosts sun
#: shadow quality, and the key is unavailable once every side is over 1000.
PROBE_PLAY_SPACE_LIMIT = 1000.0


#: What ``volume_sun``'s ``shadowSplitDistance`` is set to, in inches.  The
#: key is the one that decides how coarse a dynamic sun shadow is:
#: ``t7.def.json`` describes it as the distance, in inches, that the dynamic
#: split shadows cover, range 100 to 5000, default 2000.  The cascade has
#: a fixed texture budget, so doubling the distance it covers halves the texels
#: per world unit, and a shadow edge crossing stepped geometry then reads as a
#: saw.  Because the cascade is anchored to the camera, the saw also moves and
#: reappears as the player walks -- which is exactly how it reads in game.
#:
#: **Measured** over every ``.map`` under the tools'
#: ``map_source/``: three shipped ``volume_sun`` entities exist and not one of
#: them takes the default.  ``_prefabs/zm/zm_giant/zm_giant_light.map`` uses
#: ``900`` with ``shadowSplitCount 2``; ``_prefabs/mp/mp_sector/mp_sector_light.map``
#: and ``_prefabs/mp/mp_combine/mp_combine_light.map`` use ``1200`` with
#: ``shadowSplitCount 3``.  Every other file carrying ``shadowSplitDistance
#: 2000`` in that tree is a map this generator wrote.  The Giant's pair is
#: taken here because it is the only shipped *zombies* map and the only one
#: built, like a generated map, as tight interiors rather than open ground.
SUN_SHADOW_SPLIT_DISTANCE = 900.0

#: How many cascades the sun shadow is split into, the other half of The
#: Giant's pair.  ``shadowSplitCount`` is not declared on ``volume_sun`` in
#: ``t7.def.json`` -- the only declared split count is ``volume_performance``'s
#: ``sunShadowSplitCount`` -- but The Giant's own ``volume_sun`` carries it, so
#: the compiler is the authority on whether it is accepted, not the database.
SUN_SHADOW_SPLIT_COUNT = 2

#: ``worldspawn``'s ``numOmniShadowSlices``.  ``t7.def.json`` declares it as
#: "Number of omni shadow slices", range 8 to 256, default 24: the number of
#: run-time shadow maps the engine can hold for omni lights at once.  When more
#: lights want a slice than there are slices, which lights get one is decided
#: per frame from where the camera is, so their shadows come and go as the
#: player moves.
#:
#: **Measured**: ``zm_giant.map``'s worldspawn raises it to ``96``
#: while only 42 of that map's 280 omni lights cast a shadow map at all
#: (``PRIMARY_NOSHADOWMAP 0``); ``mp_sector.map`` and ``mp_combine.map`` keep
#: ``24``.  A generated map can carry 143 casters against 24 slices.  The Giant's value is taken here, and :func:`omni_shadow_slices`
#: refuses to hand back fewer slices than the map has casters.
OMNI_SHADOW_SLICES = 96

#: The range ``t7.def.json`` declares for ``numOmniShadowSlices``.
OMNI_SHADOW_SLICE_RANGE = (8, 256)


def omni_shadow_slices(casters: int) -> int:
    """Slices for a map with this many shadow-casting omni lights.

    :data:`OMNI_SHADOW_SLICES` unless the map has more casters than that, in
    which case every caster still gets a slice, up to the database's declared
    ceiling.  Handing out fewer slices than there are casters is the setting
    that makes a shadow depend on where the player stands.
    """
    low, high = OMNI_SHADOW_SLICE_RANGE
    return max(low, min(high, max(OMNI_SHADOW_SLICES, int(casters))))


def probe_in_play_space(size) -> bool:
    """Whether a probe box of this full size may set ``in_play_space``.

    ``size`` is the box's full extent on each axis, not the half-extent the
    ``size_min``/``size_max`` keys carry.  The rule is the database's own and
    it is an *all* rather than an *any*: a long thin box over a corridor is
    still in play space however long it is.
    """
    return not all(extent > PROBE_PLAY_SPACE_LIMIT for extent in size)


def exposure_of(ssi_preset: str) -> float:
    """The ``ev`` of a sun/sky preset, or ``default_day``'s if it is unknown.

    An unknown preset is not an error: the generator can name any of the 93
    shipped presets, or one the user authored, and the table here only
    carries the measured ones.  Falling back to the default keeps a lamp
    bright rather than silently dark, which is the failure that matters.
    """
    return SSI_EXPOSURE.get(ssi_preset, SSI_EXPOSURE[DEFAULT_SSI])


def default_stops(ssi_preset: str = DEFAULT_SSI) -> float:
    """The ``stops`` a lamp gets when the caller does not name one."""
    return exposure_of(ssi_preset) + STOPS_OVER_EXPOSURE


def intensity_of(stops: float) -> float:
    """``stops`` back in the linear units the logarithm was taken of.

    Only for reporting: nothing in the emitted file uses it.
    """
    return 2.0**stops
