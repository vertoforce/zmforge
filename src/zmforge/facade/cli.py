"""A command line over the library, with no logic of its own.

Every subcommand maps one-to-one onto a library call and converts arguments,
nothing more (spec 8.5).  If something here starts making a decision, it
belongs in :mod:`~zmforge.blueprint` or :mod:`~zmforge.toolchain` instead.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Sequence

from .. import mapdoc
from ..project import Project
from ..recipes import (
    cemetery_map,
    cemetery_dusk_map,
    corn_maze_map,
    dmv_of_the_damned,
    one_room_map,
    three_room_map,
)
from ..blueprint.elements import STOCK_PLAYER_SLOTS
from ..errors import ForgeError, MapExists
from ..toolchain.layout import validate_map_name
from .. import progress
from ..verify import run_all

RECIPES = {
    "three-room": three_room_map,
    "one-room": one_room_map,
    "dmv": dmv_of_the_damned,
    "cemetery": cemetery_map,
    "cemetery-dusk": cemetery_dusk_map,
    "corn_maze": corn_maze_map,
}


def _recipes_taking(parameter: str) -> list[str]:
    """The recipe names whose function accepts *parameter*, sorted."""
    return sorted(
        name for name, fn in RECIPES.items()
        if parameter in inspect.signature(fn).parameters
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zmforge",
        description="Generate Black Ops III zombies map sources, scripts and manifests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser(
        "generate", help="write a map from a built-in recipe into a tools root"
    )
    generate.add_argument("name", help="map name, e.g. zm_forge_gate")
    generate.add_argument(
        "--tools-root",
        required=True,
        help="mod tools installation, or any directory shaped like one",
    )
    generate.add_argument("--recipe", choices=sorted(RECIPES), default="three-room")
    generate.add_argument("--seed", default=None, help="GUID seed; defaults to the name")
    generate.add_argument(
        "--player-slots",
        type=int,
        default=STOCK_PLAYER_SLOTS,
        metavar="N",
        help=(
            "players that get an initial-spawn struct of their own "
            f"(default {STOCK_PLAYER_SLOTS}, a stock game).  Above "
            f"{STOCK_PLAYER_SLOTS} the script also turns the framework's "
            "player-count check off, without which the fifth player to spawn "
            "ends the match.  This makes the map ready for a higher-player "
            "mod and changes nothing for four; it does not seat eight on "
            "stock scripts -- four playable characters and the per-player "
            "registrations in _zm_laststand.gsc are core game scripts a "
            "usermap cannot change"
        ),
    )
    generate.add_argument(
        "--starting-points",
        type=int,
        default=None,
        metavar="N",
        help=(
            "TESTING AID: every player starts the game with N points instead "
            "of the stock level.round_number * 500 (_zm.gsc:1201), so a "
            "tester can open the whole door graph in one session.  Omit it "
            "and the map does not touch the score at all.  Offered by the "
            + ", ".join(_recipes_taking("starting_points"))
            + " recipes; a map built with it on is a map where none of its "
            "prices mean anything, so it is not something to ship"
        ),
    )
    generate.add_argument(
        "--overwrite",
        action="store_true",
        help="replace a map of this name that is already in the tools root",
    )
    sound_recipes = _recipes_taking("custom_sound")
    if sound_recipes:
        generate.add_argument(
            "--custom-sound",
            action="store_true",
            help=(
                f"carry the map's own sound bank ({', '.join(sound_recipes)} "
                "only).  Off by default: the first build that carried it "
                "crashed the game at load with 'sound bank ... failed to "
                "load'; turn it on for a test build only"
            ),
        )
    generate.add_argument(
        "--force",
        action="store_true",
        help="write even when the model-level checks report errors",
    )
    generate.add_argument(
        "--discard-edits",
        action="store_true",
        help="throw away edits made to the map's document (<map>.blueprint.json) "
        "since it was last generated, instead of merging them forward. A "
        "regenerate normally carries them across by a three-way merge against "
        "the last generated document; this skips that and writes the recipe's "
        "own document. Does not disable the model-level checks",
    )
    generate.add_argument(
        "--strict-materials",
        action="store_true",
        help="treat an uncatalogued material as an error rather than a warning",
    )
    generate.add_argument(
        "--title",
        default=None,
        help="display name for menus; defaults to the map name made readable",
    )
    generate.add_argument(
        "--loading-image",
        default=None,
        help=(
            "1920x1080 PNG to use as the loading screen; default is the "
            "recipe's own art when it has one (texture.loadscreens), else the "
            "map plan; 'plan' forces the map plan"
        ),
    )
    generate.add_argument(
        "--preview-image",
        default=None,
        help=(
            "600x340 PNG to use as the menu thumbnail; default is cut from the "
            "map's latest `zmforge render` run (its hero shot) when there is "
            "one, else the map plan; 'plan' forces the map plan and also keeps "
            "the Workshop thumbnail on the plan"
        ),
    )
    generate.add_argument(
        "--brightness",
        type=float,
        default=0.0,
        metavar="STOPS",
        help=(
            "nudge every light in the map by this many photographic stops; "
            "+1 doubles the light, -1 halves it, 0 (the default) takes the "
            "brightness the map's sun/sky preset calls for.  Regenerate and "
            "re-bake to see it; no map logic changes"
        ),
    )
    generate.add_argument(
        "--no-loading-screen",
        dest="loading_screen",
        action="store_false",
        help="do not write loadingimage.png or previewimage.png",
    )
    generate.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="list every warning and note in full (default: a count per code)",
    )

    check = sub.add_parser("check", help="run the static checks over written files")
    check.add_argument("name")
    check.add_argument("--tools-root", required=True)
    check.add_argument("--strict-materials", action="store_true")
    check.add_argument(
        "--player-slots",
        type=int,
        default=None,
        metavar="N",
        help="require exactly N initial-spawn structs, not merely at least four",
    )
    check.add_argument(
        "--no-loading-screen",
        dest="presentation",
        action="store_false",
        help="the map was generated with --no-loading-screen, so do not ask for "
        "loadingimage.png and previewimage.png",
    )
    check.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="list every warning and note in full (default: a count per code)",
    )

    requirements = sub.add_parser(
        "requirements",
        help=(
            "run every check in the table against a map and print one pass/fail "
            "line per requirement, including the ones nothing automates"
        ),
    )
    requirements.add_argument("name")
    requirements.add_argument("--tools-root", required=True)
    requirements.add_argument(
        "--recipe",
        choices=sorted(RECIPES),
        default=None,
        help=(
            "rebuild the blueprint from this recipe so the model-level checks "
            "run too; without it they are reported as not run, because a map "
            "read back off disk has no model behind it"
        ),
    )
    requirements.add_argument(
        "--seed", default=None,
        help="with --recipe: the seed the map was generated with (default: the name)",
    )
    requirements.add_argument("--strict-materials", action="store_true")
    requirements.add_argument(
        "--player-slots", type=int, default=None, metavar="N",
        help="the --player-slots the map was generated with",
    )
    requirements.add_argument(
        "--starting-points", type=int, default=None, metavar="N",
        help="with --recipe: the --starting-points the map was generated with",
    )
    requirements.add_argument(
        "--no-loading-screen",
        dest="presentation",
        action="store_false",
        help="the map was committed without the two PNGs, so do not ask for them",
    )

    paths = sub.add_parser("paths", help="print every path a map owns, as JSON")
    paths.add_argument("name")
    paths.add_argument("--tools-root", required=True)

    repair = sub.add_parser(
        "repair-geometry",
        help=(
            "re-anchor a document to the .map on disk after a geometry-hash "
            "mismatch, naming both hashes on the way past"
        ),
        description=(
            "A commit renames the .map and then, a few files later, the "
            "document; a crash in between (or a hand-edited .map) leaves a "
            "document describing geometry that is no longer there, and every "
            "later open, compile and editor save refuses.  This says 'the "
            ".map on disk is the geometry' and re-anchors the document to it.  "
            "It prints the hash the document recorded and the hash the file "
            "actually has first, because they are what tells you which of the "
            "two files moved."
        ),
    )
    repair.add_argument("name")
    repair.add_argument("--tools-root", required=True)

    props = sub.add_parser(
        "props",
        help="convert the third-party prop kit into xmodel sources for a map",
    )
    props.add_argument("name", help="map name the props are built for")
    props.add_argument("--out", required=True, help="staging directory to write")
    props.add_argument(
        "--only",
        default=None,
        help="comma-separated prop asset names; default is the whole library",
    )
    props.add_argument("--cache", default=None, help="kit download cache (default: assets-cache)")
    props.add_argument(
        "--stock-material",
        default=None,
        help="bind every prop to a material the game already ships, and build no "
        "custom image or material at all; wrong colours, but it isolates a "
        "material problem from a model problem",
    )

    place = sub.add_parser(
        "props-place",
        help="scatter the props through a .map that already exists, idempotently",
    )
    place.add_argument("map_file", help="the .map to edit in place")
    place.add_argument("--seed", default=None, help="placement seed; defaults to the map name")
    place.add_argument(
        "--only",
        default=None,
        help="comma-separated prop asset names; default is the whole library",
    )
    place.add_argument(
        "--clear", action="store_true", help="remove every prop and place none"
    )
    place.add_argument(
        "--report", default=None, help="write the placements to this JSON file"
    )
    review = sub.add_parser(
        "review",
        help=(
            "advisory design review: measure and render a map, write a review packet "
            "for any reviewer (person or AI agent); --import grades the findings "
            "against docs/map-principles.md"
        ),
    )
    from ..review.run import add_arguments as _review_arguments

    _review_arguments(review, RECIPES)
    render = sub.add_parser(
        "render",
        help="photograph each room of a generated map in Radiant's 3D camera (PNG)",
    )
    from ..render.run import add_arguments as _render_arguments

    _render_arguments(render, RECIPES)
    loadscreen = sub.add_parser(
        "loadscreen",
        help="make the loading screen (plan + title) and the preview card and Workshop "
             "thumbnail (baked-lit photo + title) that generate picks up",
    )
    from ..render.presentation import add_arguments as _loadscreen_arguments

    _loadscreen_arguments(loadscreen, RECIPES)
    build = sub.add_parser(
        "build",
        help="compile, bake and link a generated map with your local mod tools (Wine)",
    )
    from ..toolchain.build import add_arguments as _build_arguments

    _build_arguments(build)
    return parser


def _chosen_props(only: str | None, props, lookup) -> list:
    """``--only a,b`` as props, or every prop; an unknown name is one clear line."""
    if not only:
        return list(props)
    chosen = []
    for name in (n.strip() for n in only.split(",")):
        try:
            chosen.append(lookup(name))
        except KeyError:
            import difflib

            close = difflib.get_close_matches(name, [p.name for p in props], n=3)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise ForgeError(f"--only: no prop named {name!r}{hint}") from None
    return chosen


def _render_root():
    """Where ``zmforge render`` keeps its runs (build-out/render)."""
    from ..render.run import DEFAULT_OUT

    return DEFAULT_OUT


def _loading_image(args: argparse.Namespace) -> bytes | str | None:
    """``--loading-image``, else ``zmforge loadscreen``'s image, else None (the plan).

    Never the recipe's drawn art (texture.loadscreens): a loading screen is
    the map's plan plus its title (docs/map-principles.md, "Presentation
    images"), and ``zmforge loadscreen`` draws the framed version of it.
    """
    if args.loading_image == "plan" or not args.loading_screen:
        return None
    if args.loading_image is not None:
        return args.loading_image
    from ..render.presentation import LOADING_NAME, presentation_file

    ready = presentation_file(args.name, LOADING_NAME)
    return str(ready) if ready else None


def _preview_image(args: argparse.Namespace) -> str | None:
    """``--preview-image``, else ``zmforge loadscreen``'s card, else None (hero/plan)."""
    if args.preview_image == "plan":
        return None
    if args.preview_image is not None:
        return args.preview_image
    from ..render.presentation import PREVIEW_NAME, presentation_file

    ready = presentation_file(args.name, PREVIEW_NAME)
    return str(ready) if ready else None


#: How many warning codes the default (non-verbose) summary names.
SUMMARY_CODES = 5


def print_findings(report, *, verbose: bool, stream=None, starter: bool = False) -> None:
    """Errors in full; warnings as a count per code unless *verbose*.

    Notes (severity ``info``: expected on a healthy map, such as the W1
    wall-buy depth every map reproduces) are shown only with ``-v``.  On a
    *starter* map (``Blueprint.starter``) every warning counts as a note: the
    design advisories describe what a starter deliberately leaves out.
    """
    from collections import Counter

    stream = stream or sys.stderr
    findings = list(report)
    for finding in findings:
        if finding.is_error or verbose:
            print(finding, file=stream)
    if verbose:
        return
    warned = [f for f in findings if f.severity == "warning" and not starter]
    notes = sum(1 for f in findings if not f.is_error) - len(warned)
    if warned:
        counts = Counter(f.code for f in warned).most_common()
        top = ", ".join(f"{code} x{n}" for code, n in counts[:SUMMARY_CODES])
        more = f", {len(counts) - SUMMARY_CODES} more code(s)" if len(counts) > SUMMARY_CODES else ""
        print(f"{len(warned)} warning(s): {top}{more} (-v lists them)", file=stream)
    if notes:
        print(f"{notes} note(s) on expected choices (-v lists them)", file=stream)


def _recipe_extra(args: argparse.Namespace) -> dict:
    """Optional recipe parameters, refused by name when the recipe lacks them."""
    extra: dict = {}
    for option, parameter, value in (
        ("--starting-points", "starting_points", args.starting_points),
        ("--custom-sound", "custom_sound", getattr(args, "custom_sound", False) or None),
    ):
        if value is None:
            continue
        taking = _recipes_taking(parameter)
        if args.recipe not in taking:
            raise ForgeError(
                f"{option} is not offered by the {args.recipe} recipe"
                + (f"; recipes that take it: {', '.join(taking)}" if taking else "")
            )
        extra[parameter] = value
    return extra


def _origin_args(args: argparse.Namespace) -> dict:
    """The generate options ``requirements --recipe`` must match, for the document."""
    return {
        "recipe": args.recipe,
        "player_slots": args.player_slots,
        "starting_points": args.starting_points,
    }


def _check_origin(args: argparse.Namespace) -> None:
    """Refuse ``requirements --recipe`` when it would rebuild a different map.

    The model checks run over a blueprint rebuilt from the recipe; if the
    recipe, seed, player slots or starting points differ from what the map
    on disk was generated with, they would grade some other map.  The
    document beside the .map records them (``origin``).
    """
    layout_paths = Project.create(args.name, args.tools_root, overwrite=True).paths()
    model_path = Path(layout_paths["model"])
    if not model_path.is_file():
        raise ForgeError(
            f"no {model_path.name} beside the map: generate {args.name} first "
            "(zmforge generate), or leave out --recipe"
        )
    origin = json.loads(model_path.read_text(encoding="utf-8")).get("origin") or {}
    wanted = {
        "recipe": args.recipe,
        "seed": args.seed if args.seed is not None else args.name,
        "player_slots": args.player_slots or STOCK_PLAYER_SLOTS,
        "starting_points": args.starting_points,
    }
    flags = {"recipe": "--recipe", "seed": "--seed", "player_slots": "--player-slots",
             "starting_points": "--starting-points"}
    wrong = []
    for key, value in wanted.items():
        if key not in origin:  # a map generated before this was recorded
            continue
        if origin[key] != value:
            recorded = origin[key]
            wrong.append(f"{flags[key]} {value if value is not None else '(none)'} "
                         f"but it was generated with {recorded if recorded is not None else '(none)'}")
    if wrong:
        raise ForgeError(f"{args.name} does not match: " + "; ".join(wrong))


#: Errors a user can cause and fix: printed as one line, no traceback.
def _expected_errors() -> tuple[type[BaseException], ...]:
    from ..mapdoc import GeometryMismatch, MapDocConflict
    from ..render.radiant import RenderError
    from ..review.ai import ReviewError

    return (ForgeError, MapDocConflict, GeometryMismatch, RenderError, ReviewError)


def _safe_console() -> None:
    """Never die on a character the console cannot encode.

    Output redirected on Windows is cp1252, which has no box-drawing ``└─``
    (verify/coverage.py) and no arrows; printing one raised UnicodeEncodeError
    and killed the command after its work was done.  Unencodable characters
    become ``?`` instead; the encoding itself is left as it is.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):  # pragma: no cover - a closed stream
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _safe_console()
    args = _build_parser().parse_args(argv)
    progress.enable(sys.stderr)
    try:
        return _run(args)
    except MapExists as exc:
        print(f"zmforge: error: {exc.path} already exists; pass --overwrite to replace it",
              file=sys.stderr)
        return 1
    except _expected_errors() as exc:
        print(f"zmforge: error: {exc}", file=sys.stderr)
        return 1
    finally:
        progress.disable()


def _run(args: argparse.Namespace) -> int:
    # Every subcommand's positional ``name`` is a map name, spelled into paths;
    # refuse a bad one before anything is created from it.
    if isinstance(getattr(args, "name", None), str):
        validate_map_name(args.name)
    if args.command == "generate":
        # Passed only when asked for, because they are some recipes'
        # parameters and not part of the shape every recipe shares.  A recipe
        # that does not take one says so by name rather than accepting a
        # testing aid and ignoring it.
        recipe_extra = _recipe_extra(args)
        # Refuse before the recipe runs (minutes, for a big one), not after.
        existing = Project.create(args.name, args.tools_root, overwrite=True).paths()["map"]
        if Path(existing).exists() and not args.overwrite:
            raise MapExists(existing)
        progress.stage(f"building the {args.recipe} blueprint")
        blueprint = RECIPES[args.recipe](
            args.name, seed=args.seed, player_slots=args.player_slots,
            **recipe_extra,
        )
        blueprint.brightness_stops = args.brightness
        blueprint.origin_args = _origin_args(args)
        progress.stage("writing files and running the checks")
        project = Project.create(
            args.name,
            args.tools_root,
            blueprint=blueprint,
            overwrite=args.overwrite,
            title=args.title,
        )
        result = project.commit(
            force=args.force,
            discard_edits=args.discard_edits,
            strict_materials=args.strict_materials,
            loading_screen=args.loading_screen,
            loading_image=_loading_image(args),
            preview_image=_preview_image(args),
            render_root=None if args.preview_image == "plan" else _render_root(),
        )
        # Z46's fix passes now run inside Project.commit (zmforge.verify.camping)
        print(f"Z46: {result.camping[0]} camping top(s) given a zombie "
              f"traversal, {result.camping[1]} capped with clip", file=sys.stderr)
        # P22: where the gamble machine went (dressing.gamble).
        gamble = getattr(blueprint, "gamble_machine", None)
        if gamble is not None:
            p = gamble.position
            walk = f"{gamble.walk:.0f}" if gamble.walk is not None else "?"
            print(f"gamble machine: room {gamble.room_id} (zone {gamble.zone}) at "
                  f"({p.x:g}, {p.y:g}, {p.z:g}) facing {gamble.facing.name.lower()}, "
                  f"walk {walk} units from the spawn, model "
                  f"{gamble.model or 'brush fallback'}", file=sys.stderr)
        elif getattr(blueprint, "gamble_failure", None) not in (None, "opted out"):
            print(f"gamble machine: none ({blueprint.gamble_failure})", file=sys.stderr)
        for path in result.written:
            print(f"wrote {path}")
        for path in result.skipped:
            print(f"kept  {path} (changed since this project last wrote it)")
        # What the regenerate carried across from an editor, and what the
        # recipe and the editor disagreed about.  Printed rather than left in
        # the document because a conflict resolved in the user's favour and
        # never mentioned is the same silent loss the refusal used to prevent,
        # turned the other way round (zmforge.docmerge).
        if result.merge is not None:
            for line in result.merge.summary():
                print(line)
        print_findings(result.report, verbose=args.verbose,
                       starter=getattr(blueprint, "starter", False))
        if not result.ok:
            print(
                f"{len(result.report.errors)} error(s); nothing usable was produced",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.command == "check":
        from ..verify import files as check_files

        project = Project.open(args.name, args.tools_root)
        files = project.paths()
        # The same file set ``requirements`` checks (verify.files): weapon
        # table, strings, collmaps and props GDT (Z27) included.
        report = check_files(
            project,
            strict_materials=args.strict_materials,
            presentation=args.presentation,
            player_slots=args.player_slots,
        )
        # Z55 asks about rooms, doors and furniture, which the .map text does
        # not carry as such; the stored model document beside it does.
        model_path = Path(files["map"]).with_name(f"{args.name}.blueprint.json")
        if model_path.exists():
            from ..verify.routes import check_room_routes_document

            from ..verify.quest_gates import check_quest_gates_document

            document = json.loads(model_path.read_text(encoding="utf-8"))
            report.extend(check_room_routes_document(document))
            report.extend(check_quest_gates_document(document))
        else:
            document = None
        from ..verify.glows import check_glows_files

        report.extend(check_glows_files(
            Path(files["map"]).read_text(encoding="utf-8", errors="replace"),
            Path(files["server_script"]).read_text(encoding="utf-8", errors="replace"),
            document))
        # Z67-Z73, Z79, Z82: gameplay guards over the generated script and
        # strings (check what was written, not the model).
        from ..verify.gameplay import (check_gameplay_script, check_perk_limit,
                                       check_prompt_strings)

        report.extend(check_gameplay_script(
            Path(files["server_script"]).read_text(encoding="utf-8", errors="replace")))
        report.extend(check_perk_limit(
            Path(files["server_script"]).read_text(encoding="utf-8", errors="replace")))
        if files.get("localized_strings") and Path(files["localized_strings"]).exists():
            report.extend(check_prompt_strings(
                Path(files["localized_strings"]).read_text(encoding="utf-8", errors="replace")))
        # Q1-Q7: quests survive interruptions, co-op, fair bosses, no luck
        # gates.
        from ..verify.quest_safety import check_quest_safety, wall_weapons_in_map

        report.extend(check_quest_safety(
            Path(files["server_script"]).read_text(encoding="utf-8", errors="replace"),
            wall_weapons=wall_weapons_in_map(
                Path(files["map"]).read_text(encoding="utf-8", errors="replace"))))
        print_findings(report, verbose=args.verbose, stream=sys.stdout)
        print(report.summary().split(":")[0])
        return 0 if report.ok else 1

    if args.command == "requirements":
        if args.recipe:
            _check_origin(args)
            blueprint = RECIPES[args.recipe](
                args.name, seed=args.seed,
                player_slots=args.player_slots or STOCK_PLAYER_SLOTS,
                **_recipe_extra(args),
            )
            project = Project.create(
                args.name, args.tools_root, blueprint=blueprint, overwrite=True
            )
        else:
            # No model behind it: Project.open synthesises a blueprint that has
            # adopted the map text and owns no rooms, zones or lamps, so running
            # the model checks over it would report the reader's own emptiness
            # as the map's.  Skip them and say so.
            project = Project.open(args.name, args.tools_root)
        audit = run_all(
            project,
            blueprint=None if args.recipe else False,
            strict_materials=args.strict_materials,
            presentation=args.presentation,
            player_slots=args.player_slots,
        )
        print(audit.render())
        return 0 if audit.ok else 1

    if args.command == "props":
        from ..props.build import build as build_props
        from ..props.library import PROPS, prop as prop_by_name

        chosen = _chosen_props(args.only, PROPS, prop_by_name)
        result = build_props(
            args.name,
            Path(args.out),
            chosen,
            cache=Path(args.cache) if args.cache else None,
            stock_material=args.stock_material,
        )
        for built in result.props:
            print(
                f"{built.prop.name:26s} {built.triangles:5d} tris  "
                f"{built.size[0]:.1f} x {built.size[1]:.1f} x {built.size[2]:.1f} units  "
                f"{built.decimation}"
            )
        for stem, note in sorted(result.images.items()):
            print(f"image {stem}: {note}")
        for note in result.notes:
            print(note)
        print(f"{len(result.props)} props, {result.triangles} triangles, staged in {result.out}")
        return 0

    if args.command == "props-place":
        from .. import mapsource
        from ..props import place as placer
        from ..props.library import PROPS, prop as prop_by_name

        map_path = Path(args.map_file)
        document = mapsource.read(map_path)
        seed = args.seed or map_path.stem
        if args.clear:
            placements = []
        else:
            chosen = _chosen_props(args.only, PROPS, prop_by_name)
            placements = placer.scatter(
                document,
                [(p.name, p.name, p.size_units) for p in chosen],
                seed=seed,
                solid={p.name: p.solid for p in chosen},
            )
        written = placer.apply(document, placements, seed=seed)
        mapsource.write(map_path, document)
        for placement in placements:
            x, y, z = placement.rounded
            print(
                f"{placement.model:26s} at {x:8.1f} {y:8.1f} {z:8.1f}  "
                f"yaw {placement.yaw:5.1f}  "
                f"{'solid' if placement.solid else 'walk-through'}"
            )
        print(f"{written} prop(s) in {map_path}")
        if args.report:
            Path(args.report).write_text(
                json.dumps(
                    {
                        "map": map_path.stem,
                        "seed": seed,
                        "props": [
                            {
                                "asset": p.model,
                                "origin": list(p.rounded),
                                "yaw": p.yaw,
                                "solid": p.solid,
                            }
                            for p in placements
                        ],
                    },
                    indent=2,
                )
                + "\n"
            )
        return 0

    if args.command == "paths":
        project = Project.create(args.name, args.tools_root, overwrite=True)
        print(json.dumps({k: str(v) for k, v in project.paths().items()}, indent=2))
        return 0

    if args.command == "review":
        from ..review.run import main as review_main

        return review_main(args)
    if args.command == "render":
        from ..render.run import main as render_main

        return render_main(args)
    if args.command == "loadscreen":
        from ..render.presentation import main as loadscreen_main

        return loadscreen_main(args)
    if args.command == "build":
        from ..toolchain.build import run as build_run

        return build_run(args)

    if args.command == "repair-geometry":
        # Same route to the paths as the ``paths`` subcommand: a project that
        # opens is exactly what is broken here, so the document cannot be
        # reached through Project.open.
        model_path = Project.create(
            args.name, args.tools_root, overwrite=True
        ).paths()["model"]
        try:
            recorded = found = mapdoc.verify_geometry(model_path)
        except mapdoc.GeometryMismatch as mismatch:
            recorded, found = mismatch.recorded, mismatch.found
        was = mapdoc.read_revision(model_path)
        # "<none>" rather than None: a document that has never been built
        # records no geometry at all, which is not a mismatch and reads as a
        # blank rather than as a hash.
        print(f"document records sha256 {recorded or '<none>'}")
        print(f".map on disk hashes to  {found or '<none>'}")
        project = Project.open(args.name, args.tools_root, repair_geometry=True)
        print(f"anchored to             {mapdoc.verify_geometry(model_path)}")
        print(f"revision {was} -> {mapdoc.read_revision(model_path)}")
        print(f"{project.name} opens again")
        return 0

    return 2  # pragma: no cover - argparse rejects unknown commands first


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
