"""One shape for the wall-art declaration, and the one writer of it.

WHAT THIS FILE IS.  More than one program stages the same texture sets
beside a map, and without one shape each would describe them in its own
words: a map's own wall-art painter (``build-vars.json`` where it draws), a
staging script (``wall-art-vars.json`` where it stages) and any other tool
that stages art beside a map under the same file name.  Every reader then has
to agree with all of them: the install step loops ``art.texture_sets``, and a
reader that stages one set reads ``texture_set``, ``gdt_file``,
``tile_files`` and ``face_scales`` and joins ``<base>/<texture_set>/<tile>``.

THE DRIFT THIS PREVENTS.  If two writers use the same key, ``tile_files``,
for two different things -- bare file names in one file and ``<set>/<name>``
in the other -- a reader that joins the set name onto the
second gets ``texture_assets/<set>/<set>/<name>.tif``, which is no file, and
the deploy then carries a ``.gdt`` registering materials whose tiles were
never delivered -- a build that warns per material, exits 0, and plays with
the missing-texture pattern on every picture.  So there is one function that
writes the file, and ``tile_files`` is bare in it.

WHY IT IS NOT IN ``art.py``.  That module imports numpy and Pillow to draw.
A map editor that writes this shape may have neither installed, and it must be
able to import this module to write it; so this module is standard library
only, and imports nothing from the rest of the package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

__all__ = [
    "ART_DIR",
    "GDT_SUFFIX",
    "GENERATOR_VARS_NAME",
    "VARS_NAME",
    "describe_texture_tree",
    "gdt_name",
    "stage_texture_vars",
    "write_texture_vars",
]

#: The directory, relative to a staging tree, that holds one folder per set.
ART_DIR = "texture_assets"
#: What the file is called beside a map, and where the generator draws.
VARS_NAME = "wall-art-vars.json"
GENERATOR_VARS_NAME = "build-vars.json"
#: The install step rebuilds this name from the set name, so nothing may
#: invent another one.
GDT_SUFFIX = "_tex.gdt"


def gdt_name(texture_set: str) -> str:
    """The one asset-database file name a set is allowed to have."""
    return f"{texture_set}{GDT_SUFFIX}"


def _read(entry: Mapping | Path | str) -> tuple[Mapping | None, str | None]:
    """The declaration ``entry`` holds, and what stopped it being read.

    ``(mapping, None)`` is one that was read; a mapping passed in is itself, and
    a path that is simply not there is ``({}, None)`` - nothing was staged under
    that name, which is not a failure.  ``(None, why)`` is a file that IS there
    and could not be read: unreadable, half-written, or JSON that is not an
    object.  That difference is the whole reason this returns a pair; it used to
    answer ``{}`` to all three and the caller could not tell "this source says
    nothing" from "this source could not be asked".
    """
    if isinstance(entry, Mapping):
        return entry, None
    path = Path(entry)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as problem:
        return None, f"{type(problem).__name__}: {problem}"
    if not isinstance(loaded, Mapping):
        return None, f"it holds {type(loaded).__name__}, not an object"
    return loaded, None


def _inherited(sources: Iterable[Mapping | Path | str],
               on_warn: Callable[[str], None] | None = None) -> dict:
    """What a previous declaration knows that a directory listing cannot.

    ``face_scales``, ``materials`` and ``images`` are properties of the pieces,
    not of the files, so they can only be carried forward from whoever drew
    them.  The FIRST source to know a value wins: callers pass the source
    declaration -- the one beside the art that was actually drawn -- ahead of
    the destination's own file, and a manifest beside the destination can be
    left over from an older staging, while the one beside the source is
    always the one the art was drawn with.  ``face_scales`` is merged rather
    than replaced, so staging a second set does not drop the first set's
    sizes, but a key a source already carries is never overwritten by a
    later, staler source; ``texture_set`` keeps the first non-empty value
    seen; ``materials``/``images`` stay a union in first-seen order.

    A SOURCE THAT CANNOT BE READ STOPS THE CHAIN THERE, AND SAYS SO.  First
    source wins, so a source that is there and unreadable is one whose values
    nobody else is entitled to supply: reading past it handed the keys it was
    supposed to carry to the next file in the list, which is by this function's
    own ordering the staler one - the destination's leftover declaration from an
    older staging, silently putting its ``face_scales`` on pieces this staging
    had already measured.  That is a wrong number written with no warning, which
    is worse than a missing one, so the file is named through ``on_warn`` and
    nothing after it is inherited.  What earlier (fresher) sources already
    carried is kept: those were read.
    """
    carried: dict = {"face_scales": {}, "materials": [], "images": [], "texture_set": None}
    for source in sources:
        described, problem = _read(source)
        if problem is not None:
            if on_warn is not None:
                on_warn(f"{source} could not be read ({problem}), so the face scales, material "
                        "and image names it was to carry forward are not inherited - and are "
                        "not taken from a later declaration either, which would be an older "
                        "staging's numbers on the pieces this one drew")
            break
        scales = described.get("face_scales")
        if isinstance(scales, Mapping):
            for key, value in scales.items():
                carried["face_scales"].setdefault(key, value)
        for key in ("materials", "images"):
            values = described.get(key)
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                carried[key] += [v for v in values if v not in carried[key]]
        if not carried["texture_set"] and described.get("texture_set"):
            carried["texture_set"] = described["texture_set"]
    return carried


def describe_texture_tree(
    texture_root: Path | str,
    *,
    primary: str | None = None,
    face_scales: Mapping[str, Sequence[float]] | None = None,
    materials: Sequence[str] | None = None,
    images: Sequence[str] | None = None,
    inherit: Iterable[Mapping | Path | str] = (),
    on_skip: Callable[[str, str], None] | None = None,
    on_warn: Callable[[str], None] | None = None,
) -> dict:
    """Describe every texture set that is really in ``texture_root``.

    A set is a directory with at least one ``.tif`` in it and its
    ``<set>_tex.gdt`` beside it; anything else is skipped and reported through
    ``on_skip(name, why)``, because a set declared without its tiles is the
    silent failure this whole chain is built to stop.

    ``on_warn(why)`` is the other thing that has to be said out loud: an
    ``inherit`` source that is there and cannot be read (see ``_inherited``).
    A caller that passes ``inherit`` should pass this too, or a file it meant
    to carry facts forward from goes by without a word.

    ``primary`` is the set whose names are repeated in the singular keys
    ``texture_set``/``gdt_file``/``tile_files`` -- the ones an editor's carry
    step reads.
    It is listed first.  ``tile_files`` is **bare names**: a reader joins it
    with ``texture_set`` itself.

    Returns ``{}`` when the tree holds no usable set, so a caller can tell
    "nothing to declare" from "declared nothing".
    """
    texture_root = Path(texture_root)
    carried = _inherited(inherit, on_warn)
    found: list[tuple[str, str, list[str]]] = []
    if texture_root.is_dir():
        for directory in sorted(p for p in texture_root.iterdir() if p.is_dir()):
            name = directory.name
            gdt = texture_root / gdt_name(name)
            tiles = sorted(tile.name for tile in directory.glob("*.tif"))
            if not tiles:
                if on_skip:
                    on_skip(name, f"{ART_DIR}/{name} holds no .tif")
                continue
            if not gdt.is_file():
                if on_skip:
                    on_skip(name, f"{ART_DIR}/{name} has no {gdt.name} beside it")
                continue
            found.append((name, gdt.name, tiles))
    if not found:
        return {}

    names = [name for name, _, _ in found]
    if primary is None:
        primary = carried["texture_set"] if carried["texture_set"] in names else names[0]
    elif primary not in names:
        primary = names[0]
    order = [primary] + [name for name in names if name != primary]
    by_name = {name: (gdt, tiles) for name, gdt, tiles in found}

    described: dict = {
        # The list the install step loops over.  The singular keys below are the
        # same set said again, for a reader that stages one set beside a map.
        "texture_sets": order,
        "sets": [{"texture_set": name,
                  "gdt_file": by_name[name][0],
                  "tile_files": by_name[name][1]} for name in order],
        "gdt_files": [by_name[name][0] for name in order],
        "texture_set": primary,
        "gdt_file": by_name[primary][0],
        "tile_files": by_name[primary][1],
    }
    materials = list(materials) if materials is not None else carried["materials"]
    images = list(images) if images is not None else carried["images"]
    scales = dict(face_scales) if face_scales is not None else carried["face_scales"]
    # Written only when somebody knows them: an empty `face_scales` reads as
    # "this set hangs nothing", which is a different claim from "nobody said".
    if materials:
        described["materials"] = materials
    if images:
        described["images"] = images
    if scales:
        described["face_scales"] = scales
    return described


def write_texture_vars(vars_path: Path | str, described: Mapping) -> dict:
    """Write one declaration, in the one shape, with a trailing newline."""
    vars_path = Path(vars_path)
    vars_path.parent.mkdir(parents=True, exist_ok=True)
    vars_path.write_text(json.dumps(dict(described), indent=2) + "\n", encoding="utf-8")
    return dict(described)


def stage_texture_vars(
    tree: Path | str,
    *,
    vars_name: str = VARS_NAME,
    texture_dir: str = ART_DIR,
    inherit: Iterable[Mapping | Path | str] = (),
    **describe,
) -> dict:
    """Describe ``<tree>/texture_assets`` and write ``<tree>/wall-art-vars.json``.

    This is the call every stager makes, the generator among them (writing
    its own ``build-vars.json``).  Nothing is written when the tree holds no usable set, and
    ``{}`` comes back, so an empty declaration can never be mistaken for one.

    ``inherit`` is read before the tree is described: pass the declaration the
    art was drawn with to carry ``face_scales``/``materials``/``images``
    forward, since no directory listing can recover them.  Pass ``on_warn``
    with it: one of those files being unreadable is a fact about this staging,
    and it stops the ones after it being inherited.
    """
    tree = Path(tree)
    described = describe_texture_tree(tree / texture_dir, inherit=inherit, **describe)
    if not described:
        return {}
    return write_texture_vars(tree / vars_name, described)
