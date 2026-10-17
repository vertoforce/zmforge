"""``zmforge render <recipe>``: generate a map, then photograph each room in Radiant.

Output layout (one folder per run, never overwritten)::

    build-out/render/<map>/<YYYYmmdd-HHMMSS>/
        <room>--<view>.png     one per camera, at most --width px
        sheet.jpg              contact sheet (sheet-01.jpg ... for many rooms)
        compare/<room>--<view>.jpg   before | after, with --compare
        views.json             manifest: cameras, per-room hashes, shots, timings
        gen/                   the generated tools tree the pictures are of
        hero.png               with --hero: the map's hero camera (render/hero.py)
    build-out/render/<map>/latest -> <newest complete run>

``--changed`` re-renders only rooms whose hash (:mod:`.roomhash`) differs from
the ``latest`` run and hard-links the rest from it, so every run folder is
complete on its own.  When nothing changed it starts no Radiant at all and
reports the ``latest`` run.

``--hero`` shoots only the hero camera (:mod:`.hero`), at the camera pane's
full size, as ``hero.png``; it becomes ``latest`` like any run, with every
room's pictures carried.  A later ordinary run carries ``hero.png`` forward
while the hero room's hash (map blocks, camera, the hero's own settings) is
unchanged, so :func:`zmforge.workshop.hero_shot` keeps finding it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .cameras import View, plan_views
from .hero import HERO_FILE
from .roomhash import changed_rooms, room_hashes

REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO / "build-out" / "render"
#: Bump when a change to the render itself (lighting, crop, material
#: registration) should make every old picture count as stale.
RENDER_VERSION = 5   # 3: --baked really bakes; 4: stock 8-bit textures given 16-bit copies; 5: stock model files found case-insensitively


def add_arguments(parser: argparse.ArgumentParser, recipes) -> None:
    parser.add_argument("recipe", choices=sorted(recipes))
    parser.add_argument("--name", default=None, help="map name (default zm_<recipe>)")
    parser.add_argument("--rooms", default=None,
                        help="comma-separated room keys or ids (default every room)")
    parser.add_argument("--views", type=int, default=3,
                        help="views per room: set pieces, then two high corners (maze rooms: two path views), then one per doorway")
    parser.add_argument("--changed", action="store_true",
                        help="render only rooms whose props or brushes changed since the "
                             "latest run; reuse the others' pictures")
    parser.add_argument("--compare", default=None, metavar="RUN_DIR",
                        help="also write before|after sheets against RUN_DIR "
                             "('latest' = the run before this one)")
    parser.add_argument("--baked", action="store_true",
                        help="light with the map's last local bake (share/raw/maps/zm/<map>.led) "
                             "instead of Radiant's view-based fake lighting")
    parser.add_argument("--out", default=None,
                        help="output folder (default build-out/render/<map>/<time>)")
    parser.add_argument("--width", type=int, default=None,
                        help="longest side of a PNG (default 1024; with --hero the "
                             "camera pane's full size)")
    parser.add_argument("--hero", action="store_true",
                        help="shoot only the map's hero camera (render/hero.py) into "
                             "hero.png, for the Workshop thumbnail and preview card")
    parser.add_argument("--list", action="store_true",
                        help="print the camera positions and stop (no Radiant)")
    parser.add_argument("--quiet", action="store_true")


# ----------------------------------------------------------------------
# Run folders
# ----------------------------------------------------------------------
def map_root(name: str, root: Path | None = None) -> Path:
    return Path(root or DEFAULT_OUT) / name


def latest_run(name: str, root: Path | None = None) -> Path | None:
    """The newest complete run of *name* (its ``latest`` link), or None."""
    link = map_root(name, root) / "latest"
    target = link.resolve() if link.is_symlink() or link.exists() else None
    return target if target and (target / "views.json").is_file() else None


def load_manifest(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "views.json").read_text(encoding="utf-8"))


def set_latest(run_dir: Path) -> None:
    link = run_dir.parent / "latest"
    tmp = run_dir.parent / f".latest-{os.getpid()}"
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(run_dir.name)
    os.replace(tmp, link)


def new_run_dir(name: str, root: Path | None = None) -> Path:
    base = map_root(name, root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run = base / stamp
    n = 1
    while run.exists():
        n += 1
        run = base / f"{stamp}-{n}"
    run.mkdir(parents=True)
    return run


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.unlink(missing_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        import shutil
        shutil.copyfile(src, dst)


def known_rooms(run_dir: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """``(hashes, shots)`` for every room a run has pictures of, carried ones included."""
    m = load_manifest(run_dir)
    hashes = {r: c["hash"] for r, c in m.get("carried", {}).items()}
    shots = {r: c["shots"] for r, c in m.get("carried", {}).items()}
    hashes.update(m.get("room_hashes", {}))
    shots.update(m.get("shots", {}))
    return hashes, shots


def resolve_compare(value: str | None, name: str, before_latest: Path | None) -> Path | None:
    if not value:
        return None
    if value in ("latest", "prev", "previous"):
        return before_latest
    path = Path(value)
    if not (path / "views.json").is_file() and not any(path.glob("*--*.png")):
        raise SystemExit(f"--compare {value}: no render run there")
    return path


# ----------------------------------------------------------------------
def _discard_run(run: Path, *, own_dir: bool, made_run: bool, made_gen: bool) -> None:
    """Undo an unused run directory without touching anything the user owns.

    A run directory zmforge picked itself (*own_dir*) is removed whole.  A
    directory the user named with ``--out`` never is: only the ``gen``
    subdirectory this call generated into goes, and the folder itself only when
    this call created it and nothing else is left in it.
    """
    import shutil

    if own_dir:
        shutil.rmtree(run, ignore_errors=True)
        return
    if made_gen:
        shutil.rmtree(run / "gen", ignore_errors=True)
    if made_run:
        try:
            run.rmdir()
        except OSError:
            pass


def render_recipe(recipe: str, *, name: str | None = None, rooms=None, views: int = 3,
                  out: Path | None = None, width: int | None = None, dry: bool = False,
                  changed: bool = False, compare: str | Path | None = None,
                  baked: bool = False, hero: bool = False, views_for=None,
                  log=lambda s: None) -> dict:
    """Generate *recipe*, place cameras, shoot the rooms that need it; returns the manifest.

    *views_for*, a callable ``blueprint -> [View]``, replaces the room plan
    with exactly those cameras (``zmforge loadscreen`` candidates): full-pane
    width, no --changed reuse, no rooms carried from the latest run.

    The manifest's ``shots`` covers every requested room (reused rooms
    included); ``rendered`` and ``reused`` say which was which.
    """
    from ..review import facts as measure
    from ..review.facts import _areas

    from .hero import HERO_WIDTH

    t0 = time.time()
    width = width or (HERO_WIDTH if hero or views_for else 1024)
    changed = changed and not hero and views_for is None
    name = name or measure.default_map_name(recipe)
    before_latest = latest_run(name)
    run = Path(out) if out else new_run_dir(name)
    # What this call made, so the "nothing changed" exit below removes only
    # that: a user's ``--out`` folder (and anything already in it) is theirs.
    made_run = out is None or not run.exists()
    made_gen = made_run or not (run / "gen").exists()
    run.mkdir(parents=True, exist_ok=True)
    log(f"== generating {recipe} into {run / 'gen'}")
    gen = measure.generate(recipe, name, scratch=run / "gen", keep=True)
    map_file = Path(gen.paths["map"])
    if views_for is not None:
        plan = list(views_for(gen.blueprint))
    else:
        plan = [] if hero else plan_views(gen.blueprint, rooms=rooms, limit=views)
    wanted = list(dict.fromkeys(v.room for v in plan))
    lighting = "baked" if baked else "fake"
    settings = {"width": width, "lighting": lighting, "version": RENDER_VERSION}
    map_text = map_file.read_text(encoding="utf-8", errors="replace")
    hashes = room_hashes(map_text, [a for a in _areas(gen.blueprint) if a.key in wanted],
                         views=plan, settings=settings)
    hero_entry = _hero_entry(recipe, gen.blueprint, map_text, settings) if hero else None
    manifest: dict = {"map": name, "recipe": recipe, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "settings": settings, "room_hashes": hashes,
                      "views": [v.as_dict() for v in plan], "shots": {},
                      "rendered": [], "reused": [], "seconds": {"generate": round(time.time() - t0)}}
    if hero_entry is not None:
        manifest["hero"] = hero_entry
    if dry:
        manifest["out"] = str(run)
        return manifest

    todo = wanted
    prev_hashes, prev_shots = ({}, {}) if before_latest is None else known_rooms(before_latest)
    if changed and before_latest is not None:
        prev = load_manifest(before_latest)
        stale = set(changed_rooms(hashes, prev_hashes))
        todo = [r for r in wanted if r in stale or not prev_shots.get(r)]
        if not todo:
            _discard_run(run, own_dir=out is None, made_run=made_run, made_gen=made_gen)
            log(f"== nothing changed since {before_latest}; reusing it")
            prev = dict(prev)
            prev["shots"] = {r: prev_shots[r] for r in wanted}
            prev["room_hashes"] = {r: prev_hashes[r] for r in wanted}
            prev["rendered"], prev["reused"], prev["out"] = [], wanted, str(before_latest)
            return prev
        for room in wanted:
            if room in todo:
                continue
            paths = []
            for p in prev_shots.get(room, []):
                src = Path(p)
                dst = run / src.name
                _link_or_copy(src, dst)
                paths.append(str(dst))
            manifest["shots"][room] = paths
            manifest["reused"].append(room)
        log(f"== {len(todo)} room(s) changed ({', '.join(todo)}); "
            f"{len(manifest['reused'])} reused from {before_latest.name}")

    shoot = [v for v in plan if v.room in todo]
    if hero_entry is not None:
        shoot = [View(**hero_entry["view"])]
    if shoot:
        from . import assets
        from . import radiant
        from .radiant import RadiantCamera, render_views

        tools = RadiantCamera(map_file).tools
        radiant.require_render_tools(tools)
        try:
            reg = assets.prepare(map_file, tools=tools, work=run / ".assets", gen=run / "gen",
                                 recipe=recipe, log=log)
        except (RuntimeError, OSError, ValueError) as exc:
            # The pictures are still worth having; say plainly what may be black.
            log(f"!! could not check or register the map's own assets ({exc}); "
                "any zmforge material the shared gdt.db lacks will draw black")
            reg = assets.Registration(still_missing=["<unchecked>"])
        manifest["assets"] = reg.as_dict()
        extra = list(reg.mounts)
        from . import propfix

        try:
            mats, models = assets.used_assets(map_file.read_text(encoding="utf-8",
                                                                 errors="replace"))
            brushes = propfix.brush_materials(mats)
            # Opted-in props (own material, generated or imported mesh) come
            # from the current code, not the deployed tools tree.
            overlay, current = propfix.stage_current(models, tools=tools, log=log)
            if overlay is not None:
                reg.db, staged_mounts = assets.register_current_props(
                    overlay, tools=tools, work=run / ".assets", db=reg.db, log=log)
                extra += staged_mounts + current.mounts
                if (reg.db, "/tools/gdtdb/gdt.db") not in extra:
                    extra.append((reg.db, "/tools/gdtdb/gdt.db"))
            manifest["current_props"] = current.models
            fixed = propfix.prepare(models, tools=tools, log=log, overlay=overlay)
            manifest["props"] = fixed.as_dict()
            extra += fixed.mounts
            from .radiant import IMAGE

            # Stock materials and models whose 8-bit sources Radiant cannot
            # convert under Wine drew its missing-image fallback (the blotchy
            # teal surfaces; assets.stock_images).
            stock = assets.stock_images(mats, models, tools=tools)
            tex = propfix.tif16_copies(models, tools=tools, image=IMAGE, log=log,
                                       overlay=overlay, brush_tifs=brushes.values(),
                                       stock_tifs=stock)
            manifest["props"]["16bit_textures"] = tex.textures
            manifest["props"]["regenerated_textures"] = tex.regenerated
            manifest["props"]["texture_warnings"] = tex.warnings
            extra += tex.mounts
            db, relit = assets.relight(propfix.kit_materials(models, tools, overlay) + list(brushes),
                                       tools=tools,
                                       work=run / ".assets", db=reg.db, log=log)
            manifest["props"]["relit_materials"] = relit
            if db and db != reg.db:
                extra.append((db, "/tools/gdtdb/gdt.db"))
        except (OSError, ValueError, RuntimeError) as exc:
            log(f"!! kit prop render copies failed ({exc}); kit props may draw black")
        if baked:
            extra += _baked_mounts(name, tools, log)
        # One mount per target, the last one wins: a staged 8-bit colour map
        # and its 16-bit render copy both name the same path.
        extra = list({target: (host, target) for host, target in extra}.values())
        t1 = time.time()
        timing: dict = {}
        try:
            shots = render_views(map_file, shoot, run, width=width, log=log, mounts=extra,
                                 lighting="baked" if baked else "fake", timing=timing)
        finally:
            manifest["seconds"].update(timing)
            manifest["seconds"]["radiant_total"] = round(time.time() - t1)
            (run / "views.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        for view, path in shots:
            if hero_entry is not None:
                final = run / HERO_FILE
                os.replace(path, final)
                manifest["hero"]["path"] = str(final)
                continue
            manifest["shots"].setdefault(view.room, []).append(str(path))
            if view.room not in manifest["rendered"]:
                manifest["rendered"].append(view.room)
    # Keep the plan's room order in the manifest.
    manifest["shots"] = {r: manifest["shots"][r] for r in wanted if r in manifest["shots"]}
    if baked and not hero and views_for is None and manifest["shots"]:
        # D8's post-bake half: rooms that render far darker than the map's
        # median room (zmforge.verify.lightlevel; advisory, never fails).
        from ..verify.lightlevel import image_advisories, image_levels

        levels = image_levels(manifest["shots"])
        manifest["light_levels"] = levels
        for line in image_advisories(levels) or ["D8 (baked): no room renders dark"]:
            log(line)
    # Rooms this run was not asked for keep their last pictures (hard links),
    # so ``latest`` always shows the whole map and --changed can compare every room.
    carried = {}
    for room, paths in prev_shots.items():
        if room in wanted or room not in prev_hashes or views_for is not None:
            continue
        links = []
        for p in paths:
            if Path(p).is_file():
                _link_or_copy(Path(p), run / Path(p).name)
                links.append(str(run / Path(p).name))
        carried[room] = {"hash": prev_hashes[room], "shots": links}
    manifest["carried"] = carried
    if hero_entry is None and views_for is None and before_latest is not None:
        kept = _carry_hero(before_latest, run, recipe, gen.blueprint, map_text, log)
        if kept:
            manifest["hero"] = kept

    from .sheets import compare_sheets, contact_sheets

    manifest["sheets"] = ([str(p) for p in contact_sheets(manifest["shots"], run)]
                          if manifest["shots"] else [])
    before = resolve_compare(str(compare) if compare else None, name, before_latest)
    if before is not None:
        written = compare_sheets(before, run, run / "compare", rooms=manifest["rendered"] or None)
        manifest["compare"] = {"before": str(before), "sheets": [str(p) for p in written]}
        log(f"== {len(written)} before|after sheet(s) in {run / 'compare'}")
    manifest["seconds"]["total"] = round(time.time() - t0)
    (run / "views.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if not out or Path(out).parent == map_root(name):
        set_latest(run)
    manifest["out"] = str(run)
    return manifest


def _hero_entry(recipe: str, bp, map_text: str, settings: dict) -> dict:
    """The hero camera of *recipe* and its room's hash under *settings*."""
    from ..review.facts import _areas
    from .hero import hero_view

    view = hero_view(recipe, bp)
    area = next(a for a in _areas(bp) if a.key == view.room)
    digest = room_hashes(map_text, [area], views=[view], settings=settings)[area.key]
    return {"view": view.as_dict(), "hash": digest, "settings": dict(settings)}


def _carry_hero(before: Path, run: Path, recipe: str, bp, map_text: str, log) -> dict | None:
    """Link *before*'s ``hero.png`` into *run* when its room has not changed."""
    try:
        prev = load_manifest(before).get("hero")
    except (OSError, ValueError):
        return None
    if not prev or not prev.get("path") or not (before / HERO_FILE).is_file():
        return None
    try:
        now = _hero_entry(recipe, bp, map_text, prev.get("settings") or {})
    except (KeyError, LookupError, StopIteration) as exc:
        log(f"!! hero camera: {exc}; not carrying {before / HERO_FILE}")
        return None
    if now["hash"] != prev.get("hash"):
        log(f"== hero room {now['view']['room']} changed; hero.png is stale, "
            "re-shoot it with --hero")
        return None
    _link_or_copy(before / HERO_FILE, run / HERO_FILE)
    return dict(prev, path=str(run / HERO_FILE))


def _baked_mounts(name: str, tools: Path, log) -> list[tuple[str, str]]:
    led = tools / "share" / "raw" / "maps" / "zm" / f"{name}.led"
    if not led.is_file():
        raise SystemExit(f"--baked: no bake at {led}; run docker/bo3-wine/setup.sh, then `zmforge build {name}` first")
    log(f"== lighting from {led} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(led.stat().st_mtime))})")
    return []


def main(args: argparse.Namespace) -> int:
    log = (lambda s: None) if args.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    rooms = [r.strip() for r in args.rooms.split(",")] if args.rooms else None
    manifest = render_recipe(args.recipe, name=args.name, rooms=rooms, views=args.views,
                             out=args.out, width=args.width, dry=args.list,
                             changed=args.changed, compare=args.compare,
                             baked=getattr(args, "baked", False),
                             hero=getattr(args, "hero", False), log=log)
    if args.list:
        for v in manifest["views"] + ([manifest["hero"]["view"]] if manifest.get("hero") else []):
            print(f"{v['room']:<14} {v['name']:<12} {View(**v).radiant_text()}")
        return 0
    for room, paths in manifest["shots"].items():
        tag = "reused" if room in manifest.get("reused", []) else "rendered"
        print(f"{room}: {len(paths)} view(s) {tag}")
    missing = manifest.get("assets", {}).get("still_missing") or []
    if missing:
        print(f"not in any asset database (Radiant draws them missing or black): {', '.join(missing)}")
    for sheet in manifest.get("sheets", []):
        print(f"sheet: {sheet}")
    if manifest.get("compare"):
        print(f"compare: {Path(manifest['out']) / 'compare'}")
    if manifest.get("hero", {}).get("path"):
        print(f"hero: {manifest['hero']['path']}")
    print(f"renders: {manifest['out']}")
    return 0 if manifest["shots"] or manifest.get("hero", {}).get("path") else 1
