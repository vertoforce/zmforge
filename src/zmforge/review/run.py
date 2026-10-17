"""``zmforge review``: build a review packet for a map, and grade the findings.

``zmforge review <recipe>`` measures the map, renders its rooms and writes a
packet (prompts, images, schemas); no model is called.  Anyone can answer the
packet: a person, any AI agent following ``docs/workflows/review-a-map.md``,
or a runner script such as ``scripts/review-with-claude.py``.
``zmforge review --import <packet>`` grades what they wrote.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import ai, facts as measure, packet


def add_arguments(parser: argparse.ArgumentParser, recipes) -> None:
    parser.add_argument("recipe", nargs="?", choices=sorted(recipes),
                        help="the map to review (not needed with --import)")
    parser.add_argument("--name", default=None, help="map name (default zm_<recipe>)")
    parser.add_argument("--out", default=str(ai.DEFAULT_OUT),
                        help="where packets and reports go (default build-out/review)")
    parser.add_argument("--import", dest="import_dir", default=None, metavar="PACKET",
                        help="grade a packet whose findings files are written: check each "
                             "against its schema, apply the anchoring rules, write the report")
    parser.add_argument("--partial", action="store_true",
                        help="with --import: report calls without usable findings as errors "
                             "instead of refusing the import")
    parser.add_argument("--reviewer", default=None,
                        help="with --import: who or what wrote the findings, for the report")
    parser.add_argument("--no-ai", action="store_true",
                        help="measure only: write the facts and scorecard, no renders, no packet")
    parser.add_argument("--strict", action="store_true",
                        help="with --import: exit 1 when any principle fails or a call has "
                             "no usable findings")
    parser.add_argument("--rooms", default=None, help="comma-separated rooms to review")
    parser.add_argument("--principles", default=str(ai.PRINCIPLES_PATH),
                        help="the principles document the findings are graded "
                             "against (default: docs/map-principles.md)")
    parser.add_argument("--no-visual", action="store_true",
                        help="skip the Radiant renders: rooms are judged from facts only and "
                             "P15 is not judged from pictures. By default every room is "
                             "rendered (only rooms changed since the last render are "
                             "re-shot) and its PNGs go in the packet")
    parser.add_argument("--visual-views", type=int, default=3,
                        help="renders per room (default 3)")
    parser.add_argument("--fresh", action="store_true",
                        help="do not anchor each room on this map's previous review "
                             "(build-out/review/<map>-*.json); judge every room from scratch")
    parser.add_argument("--quiet", action="store_true")


def render_rooms(recipe: str, *, name: str | None, rooms: list[str] | None,
                 wanted: list[str], views: int,
                 log) -> tuple[dict[str, list[Path]] | None, dict]:
    """``(room_images, visual)``: Radiant shots per room and what happened.

    ``changed=True`` re-shoots only rooms whose content changed since their
    last render and reuses the rest, so every reviewed room gets current
    pictures.  A render failure does not stop the review: it goes on without
    images and ``visual`` says so (status ``failed``), so the report never
    reads as a visual review that was not one.
    """
    import subprocess

    from ..render.radiant import RenderError
    from ..render.run import render_recipe

    log("== rendering rooms in Radiant for the visual check (changed rooms only)")
    try:
        manifest = render_recipe(recipe, name=name, rooms=rooms, views=views, out=None,
                                 changed=True, log=log)
    except (RenderError, OSError, subprocess.SubprocessError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        log(f"WARNING: rendering failed, reviewing WITHOUT pictures (P15 not judged "
            f"from renders): {error}")
        return None, {"status": "failed", "error": error}
    room_images = {room: [Path(p) for p in paths]
                   for room, paths in (manifest.get("shots") or {}).items() if paths}
    visual = {"status": "ok", "out": manifest.get("out"),
              "rendered": list(manifest.get("rendered") or []),
              "reused": list(manifest.get("reused") or [])}
    missing = [r for r in wanted if r not in room_images]
    if missing:
        visual["no_images"] = missing
        log("WARNING: no renders for " + ", ".join(missing) + "; those rooms are reviewed "
            "without pictures")
    return room_images, visual


def blueprint_time() -> float:
    """When the current blueprint last changed: the newest source file of the
    package that generates it (recipes, placement, emitters, lighting).

    A render older than this may show a map the code no longer makes.  The
    room hashes :func:`render_rooms` reuses by cover the map text but not
    everything a picture shows, so a review can otherwise be judged from
    pictures of an older build.
    """
    root = Path(__file__).resolve().parents[1]
    return max((p.stat().st_mtime for p in root.rglob("*.py")), default=0.0)


def _stale(paths, since: float) -> bool:
    try:
        return any(Path(p).stat().st_mtime < since for p in paths)
    except OSError:
        return True  # a picture that is not there is not a current one


def refuse_stale_renders(room_images, visual: dict, since: float, *, recipe: str,
                         name: str | None, views: int, log):
    """Drop every room whose renders are older than ``since``, after one re-shoot.

    Stale rooms are rendered again in full (``changed=False``); a room still
    stale after that goes into the review without pictures and ``visual``
    records it under ``stale_refused``, so the report never reads as a visual
    review of the current map when it was not one.
    """
    if not room_images:
        return room_images
    stale = sorted(room for room, paths in room_images.items() if _stale(paths, since))
    if not stale:
        return room_images
    log("== renders older than the current blueprint for " + ", ".join(stale)
        + "; re-rendering them")
    try:
        from ..render.run import render_recipe

        manifest = render_recipe(recipe, name=name, rooms=stale, views=views, out=None,
                                 changed=False, log=log)
        for room, paths in (manifest.get("shots") or {}).items():
            if room in room_images and paths:
                room_images[room] = [Path(p) for p in paths]
    except Exception as exc:  # the refusal below still holds
        log(f"WARNING: re-render failed: {type(exc).__name__}: {exc}")
    refused = [room for room in stale if _stale(room_images.get(room, ()), since)]
    for room in refused:
        room_images.pop(room, None)
    if refused:
        visual["stale_refused"] = refused
        log("WARNING: refusing renders older than the current blueprint for "
            + ", ".join(refused) + "; those rooms are reviewed without pictures")
    return room_images


def _log(args):
    return (lambda s: None) if args.quiet else (lambda s: print(s, file=sys.stderr, flush=True))


def build(args: argparse.Namespace) -> Path | None:
    """Measure the map and write its review packet; the packet folder, or None with --no-ai.

    Deterministic: no model is called.  With ``--no-ai`` only the facts and
    the scorecard are written (no renders, no packet).
    """
    log = _log(args)
    log(f"== generating {args.recipe} into a scratch tools root")
    gen = measure.generate(args.recipe, args.name)
    data = measure.collect(gen)
    table = measure.scorecard_table(data)
    stem = f"{data['map']}-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = Path(args.out)
    rooms = [r.strip() for r in args.rooms.split(",")] if args.rooms else None
    if args.no_ai:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{stem}.facts.json"
        path.write_text(json.dumps({"facts": data, "scorecard_table": table,
                                    "generated_at": stem}, indent=1, default=str),
                        encoding="utf-8")
        print(table)
        print(f"facts: {path}")
        return None
    previous: dict = {}
    if getattr(args, "fresh", False):
        log("== fresh review: rooms are not anchored on the previous review")
    else:
        previous = ai.previous_room_reviews(out_dir, data["map"], data, rooms)
        if previous:
            unchanged = sum(1 for a in previous.values() if a.get("facts_changed") == [])
            log(f"== anchoring {len(previous)} room(s) on their previous review "
                f"({unchanged} with unchanged facts; --fresh to skip): "
                + ", ".join(sorted({a['from'] for a in previous.values()})))
        else:
            log("== no previous review of this map: rooms are judged fresh")
    principles = ai.load_principles(Path(args.principles))
    sources = {r["room"]: measure.room_source(args.recipe, r["room"], r["room_id"])
               for r in data["rooms"]}
    if getattr(args, "no_visual", False):
        room_images, visual = None, {"status": "skipped"}
        log("== visual check skipped (--no-visual): P15 is not judged from pictures")
    else:
        wanted = rooms or [r["room"] for r in data["rooms"]]
        room_images, visual = render_rooms(
            args.recipe, name=args.name, rooms=rooms, wanted=wanted,
            views=args.visual_views, log=log)
        room_images = refuse_stale_renders(
            room_images, visual, blueprint_time(), recipe=args.recipe,
            name=args.name, views=args.visual_views, log=log)
    packet_dir = out_dir / f"{stem}.packet"
    built = packet.build(data, principles=principles, room_sources=sources,
                         map_source=measure.map_source(args.recipe), packet_dir=packet_dir,
                         out_dir=out_dir, stem=stem, rooms=rooms, room_images=room_images,
                         previous=previous,
                         extra={"scorecard_table": table, "visual": visual})
    print(table)
    rooms_n = sum(1 for c in built["calls"] if c["kind"] == "room")
    images_n = sum(len(c["images"]) for c in built["calls"])
    print(f"packet: {packet_dir} ({rooms_n} room calls + 1 map call, {images_n} images)")
    print(f"next: write <call>.findings.json for each call (see {packet_dir / 'README.md'}), "
          f"then: zmforge review --import {packet_dir}")
    return packet_dir


def import_findings(packet_dir: Path, *, strict: bool = False, partial: bool = False,
                    reviewer: str | None = None, quiet: bool = False,
                    out: Path | None = None) -> int:
    """Grade a packet's findings and write the report; the exit code.

    2 when a findings file is missing or does not match its schema (the
    problems are printed; nothing is written), else :func:`ai.exit_code`.
    """
    log = (lambda s: None) if quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    try:
        result, problems = packet.grade(Path(packet_dir), partial=partial, reviewer=reviewer,
                                        log=log)
    except ai.ReviewError as exc:
        print(f"review --import: {exc}", file=sys.stderr)
        return 2
    if result is None:
        print(f"review --import: {len(problems)} problem(s) in the findings; nothing written. "
              "Fix them and import again (or --partial to report them as errors):",
              file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 2
    loaded = packet.load(Path(packet_dir))
    out_dir = Path(out) if out else Path(loaded["out"])
    paths = ai.write_outputs(result, out_dir, loaded["stem"])
    paths["packet"] = Path(packet_dir)
    print(ai.screen_summary(result, paths))
    return ai.exit_code(result, strict=strict)


def main(args: argparse.Namespace) -> int:
    if args.import_dir:
        out = args.out if args.out != str(ai.DEFAULT_OUT) else None
        return import_findings(Path(args.import_dir), strict=args.strict,
                               partial=args.partial, reviewer=args.reviewer,
                               quiet=args.quiet, out=out)
    if not args.recipe:
        print("zmforge review: give a recipe, or --import <packet>", file=sys.stderr)
        return 64
    build(args)
    return 0
