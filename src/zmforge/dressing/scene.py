"""Scenes: what happened in each area, declared by the recipe.

``docs/map-design-method.md`` asks every area to be a *scene*: one line of
"what happened here" that decides its set pieces, damage, fire, smoke and
props.  A recipe says so with :func:`declare_scene`; the review facts
(:mod:`zmforge.review.scene_metrics`) print the story next to the numbers,
and the ``S`` checks (:mod:`zmforge.verify.scenes`) hold a room to the beats
its scene promises (a scene with a ``fire`` beat and no fire is a warning).

The targets below are the stock numbers, measured on
``zm_giant`` (the only stock zombies map
whose source ships with the mod tools).  Units are per 1000 x 1000 map
units of play-space footprint ("per k2").

    >>> from zmforge.dressing import declare_scene
    >>> declare_scene(bp, "street", "The school bus hit the gas main; the "
    ...               "houses either side are still burning.",
    ...               beats=("fire", "wreck", "barricade"))
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BEATS",
    "STOCK",
    "WARN_SHARE",
    "BIG_ROOM_K2",
    "BIG_ROOM_SHARE",
    "OVERHEAD_WARN",
    "FLAT_WALL_RUN",
    "Scene",
    "declare_scene",
    "scenes_of",
    "scene_for",
    "tell_matches",
]

#: The vignette kinds a scene may promise.  Each is something the checks can
#: look for: ``fire``/``smoke``/``embers`` an effect from
#: :mod:`zmforge.dressing.fx` in the room, the rest a prop whose model name
#: says so (:data:`BEAT_WORDS`).
BEATS = ("fire", "smoke", "embers", "wreck", "barricade", "body", "flood", "flies")

#: Model-name words that count as each prop beat (the study's vignette words).
BEAT_WORDS = {
    "wreck": ("wreck", "crash", "destroyed", "collapsed", "fallen", "rubble", "debris", "overturn",
              "burnt", "burned", "broken", "dmg", "damaged", "car", "truck", "bus", "veh_"),
    "barricade": ("barricade", "sandbag", "barbed", "boarded", "barrier", "jersey", "plank", "board"),
    "body": ("corpse", "skeleton", "skull", "bones", "blood", "body_bag", "cadaver", "gore", "dead",
             "gib_", "_bone"),
    "flood": ("puddle", "water", "flood", "wet"),
}

#: Stock targets per k2 (1000 x 1000 units of footprint), zm_giant, measured.
#: ``*_props`` count props whose origin is in the height band
#: over the local floor: ground < 48 <= mid < 160 <= overhead.
STOCK = {
    "props": 2645.0,           # every prop, incl. kit trim zmforge builds from brushes
    "props_non_trim": 1148.0,  # debris + dressing + foliage + set pieces
    "ground_props": 2134.0,
    "mid_props": 399.0,
    "overhead_props": 113.0,
    "above_ground_share": 0.19,
    "distinct_models": 306.0,  # per 1000 x 1000 cell, median
    "set_pieces": 2.1,         # clusters of big set-piece models (160-unit link)
    "set_piece_spacing": 329.0,  # median nearest set piece, units
    "fire_spots": 2.9,
    "barricade_spots": 4.3,
    "wreck_spots": 2.1,
    "fx": 75.0,
    "fx_spots": 43.0,          # effects merged within 64 units
    "light_positions": 51.0,
    "light_fixtures": 15.0,    # lights merged within 128 units
    "lit_within_256": 0.95,    # walkable share within 256 units of a light
    "corridor_p50": 256.0,     # largest-inscribed-disk width, units
    "corridor_share_under_160": 0.21,
    "corridor_share_512_up": 0.07,
    "pinch_points": 0.66,
}

#: A room is "far below" stock when a measure is under this share of it.
WARN_SHARE = 0.25
#: ...but a big room (this many k2 or more) is held to a higher share: the
#: quarter bar alone passes big rooms at 13 to 33% of stock as a B.  ``S2`` and the review's density floor
#: (``review.facts.density_floor``) both use it.
BIG_ROOM_K2 = 0.5
BIG_ROOM_SHARE = 0.40
#: ``S5``: a big roofed room with fewer overhead props (origin 160+ over the
#: floor: beams' lamps, ducts, pipes, hung lights) per k2 than this warns
#: (stock 113; ``dressing.walldetail`` aims at 60+).
OVERHEAD_WARN = 50.0
#: ``S6``: a wall run longer than this that is one flat material floor to
#: ceiling (no skirting, wainscot, rail or column) warns in a big roofed room.
FLAT_WALL_RUN = 256.0


@dataclass(frozen=True, slots=True)
class Scene:
    """One area's story.

    ``room`` is a room id or zone name (:func:`scene_for` matches either);
    ``story`` is one line saying what happened here; ``beats`` are the
    vignette kinds (:data:`BEATS`) the story promises, which the checks look
    for; ``outdoor`` overrides the room's own roofed flag when the scene is
    open-air dressing inside a roofed shell (a courtyard under a sky brush).
    ``focus`` are the ``(x, y, z)`` points the story centres on (a wreck, a
    burning); the render cameras aim a view at each.  ``cause`` says what did
    it (the gas main, the escaped subject) and ``tell`` names the one telling
    detail that proves it, the paintbrush left under the slogan (Worch and
    Smith, GDC 2010): a model name, part of one, or a prop id.  ``S1`` warns
    when a room shows no prop matching its ``tell``, or names a ``cause``
    with no ``tell`` (docs/map-design-method.md section 8).
    """

    room: str
    story: str
    beats: tuple[str, ...] = ()
    outdoor: bool | None = None
    focus: tuple[tuple[float, float, float], ...] = ()
    cause: str | None = None
    tell: str | None = None


def declare_scene(bp, room, story: str, *, beats=(), outdoor: bool | None = None,
                  focus=(), cause: str | None = None, tell: str | None = None) -> Scene:
    """Declare *room*'s scene on the blueprint and return it.

    *room* may be a room element, a room id or a zone name.  A second
    declaration for the same room replaces the first.  *focus* are the set
    pieces' points (``Point`` or ``(x, y, z)``), for the render cameras.
    *cause* is what did it; *tell* is the one prop that proves it (a model
    name, part of one, or a prop id; see :func:`tell_matches`).
    """
    key = getattr(room, "id", room)
    story = " ".join(str(story).split())
    if not story:
        raise ValueError(f"scene for {key!r} needs a one-line story")
    bad = [b for b in beats if b not in BEATS]
    if bad:
        raise ValueError(f"unknown beats {bad} for {key!r}; use {BEATS}")
    points = tuple(tuple(float(v) for v in ((f.x, f.y, f.z) if hasattr(f, "x") else f[:3]))
                   for f in focus)
    cause = " ".join(str(cause).split()) or None if cause is not None else None
    tell = str(tell).strip() or None if tell is not None else None
    scene = Scene(str(key), story, tuple(beats), outdoor, points, cause, tell)
    scenes = getattr(bp, "scenes", None)
    if scenes is None:
        scenes = []
        bp.scenes = scenes
    scenes[:] = [s for s in scenes if s.room != scene.room]
    scenes.append(scene)
    return scene


def scenes_of(bp) -> list[Scene]:
    return list(getattr(bp, "scenes", None) or ())


def scene_for(bp, room_id: str, zone_name: str | None = None) -> Scene | None:
    for scene in scenes_of(bp):
        if scene.room in (room_id, zone_name):
            return scene
    return None


def tell_matches(tell: str, model: str, ident: str | None = None) -> bool:
    """Is a prop (*model*, *ident*) the scene's telling detail *tell*?

    The prop's id equals *tell*, or its model name contains it (case folded).
    """
    t = tell.strip().lower()
    return bool(t) and (ident == tell or t in (model or "").lower())

