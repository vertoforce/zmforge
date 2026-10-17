"""Z64: a glow that belongs to an object goes out with it (P12).

Two ways a light outlives the thing it belonged to, both warnings:

* a **static lamp** (a baked radiant light, no exploder) within
  :data:`~zmforge.script.glow.OWNED_GLOW_REACH` of an object a script removes
  or a quest finishes (:func:`zmforge.script.glow.own_object`): no script can
  switch it off.  Such a glow stays lit after
  its object is gone; use :func:`zmforge.script.glow.place_owned_glow`;
* a **looping effect played with PlayFX** (``powerup_on*``,
  :data:`~zmforge.script.glow.LOOPING_FX`): it has no entity to delete and
  burns for the rest of the game.  The corn maze's lantern pulse played one
  every 2.5 s, and a shot lantern stayed lit.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Mapping, Sequence

from ..script.glow import LOOPING_FX, OWNED_GLOW_REACH
from .report import Report, warning

__all__ = ["check_glows", "check_glows_blueprint", "check_glows_files", "looping_playfx"]

CODE = "Z64"
#: Room fill (``Blueprint.light_rooms`` names its lamps ``<room>_fill_<n>``,
#: recipes their corridor fill the same way): light for the room, not any
#: object's glow, so never an owned object's.
_FILL = re.compile(r"_fill_\d+$")
_PLAYFX = re.compile(r'\bPlayFX\s*\(\s*level\._effect\[\s*"(\w+)"\s*\]', re.IGNORECASE)


def looping_playfx(texts: Iterable[str]) -> list[str]:
    """Every looping effect name some line plays with ``PlayFX``."""
    out = []
    for text in texts:
        for name in _PLAYFX.findall(text):
            if name in LOOPING_FX and name not in out:
                out.append(name)
    return out


def check_glows(static_lamps: Sequence[tuple[str, tuple[float, float, float]]],
                owned: Sequence[Mapping], looping: Sequence[str]) -> Report:
    """The rule over plain data: lamps as ``(id, origin)``, owned objects as
    ``{"label", "point"}``, and the looping effect names played with PlayFX."""
    report = Report()
    for lamp_id, origin in static_lamps:
        if _FILL.search(str(lamp_id)):
            continue
        for obj in owned:
            d = math.dist(origin, obj["point"])
            if d <= OWNED_GLOW_REACH:
                report.add(warning(
                    CODE,
                    f"static light {d:.0f} units from {obj['label']}: a baked light cannot go "
                    "out when its object is done (P12); place it with "
                    "script.glow.place_owned_glow (an exploder light)",
                    lamp_id, " ".join(f"{c:g}" for c in origin)))
                break
    for name in looping:
        report.add(warning(
            CODE,
            f'PlayFX of the looping effect "{name}": it has no handle and never stops; '
            "play a one-shot effect, or PlayFXOnTag on a tag_origin you delete (P12)"))
    return report


def check_glows_blueprint(blueprint) -> Report:
    """Z64 over a live blueprint."""
    from ..blueprint.elements import Lamp

    lamps = [(lamp.id, tuple(lamp.position)) for lamp in blueprint.elements(Lamp)
             if not getattr(lamp, "exploder", None)]
    owned = getattr(blueprint, "owned_objects", ()) or ()
    bodies = ["\n".join(f.body) for f in blueprint.script.custom.functions]
    return check_glows(lamps, owned, looping_playfx(bodies))


def _map_lights(map_text: str) -> list[tuple[str, tuple[float, float, float]]]:
    """Static lights of a written .map: ``(guid, origin)`` for every
    ``light`` entity with no exploder."""
    out, cur = [], None
    for line in map_text.splitlines():
        s = line.strip()
        if s == "{":
            cur = {}
        elif s == "}" and cur is not None:
            if cur.get("classname") == "light" and "exploder_count" not in cur and "origin" in cur:
                out.append((cur.get("guid", "light"), tuple(float(v) for v in cur["origin"].split())))
            cur = None
        elif cur is not None:
            m = re.match(r'"?([^"\s]+)"?\s+"(.*)"$', s)
            if m:
                cur[m.group(1)] = m.group(2)
    return out


def check_glows_files(map_text: str, server_script: str, document: Mapping | None) -> Report:
    """Z64 over a written map, for ``zmforge check``: the .map's lights, the
    server script's PlayFX calls and the stored model's owned objects."""
    owned = ((document or {}).get("engine") or {}).get("owned_objects") or []
    lights = ((document or {}).get("editor") or {}).get("lights")
    if not owned:
        lamps = []
    elif lights:
        # The stored model names its lamps, so room fill can be told apart.
        lamps = [(d["id"], (d["x"], d["y"], d["z"])) for d in lights if not d.get("exploder")]
    else:
        lamps = _map_lights(map_text)
    return check_glows(lamps, owned, looping_playfx([server_script]))
