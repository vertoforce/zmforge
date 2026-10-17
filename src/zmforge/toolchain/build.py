"""``zmforge build``: compile, bake and link a generated map with the mod tools.

The verdict rules are written once, in :mod:`zmforge.toolchain.stages`: a
compile is good when it exits 0, printed no leak banner and no ``ERROR:`` line
and left its outputs on disk; a link is good when it printed no ``ERROR:``
line and both fastfiles are non-empty, whatever its exit code (it never
returns 0). This is the command line over them.

The tools run under Wine in a container on this machine, against a local copy
of the Black Ops III mod tools (``--tools-dir`` or ``$ZMFORGE_WINE_TOOLS``).
The image brings its own display, so the lighting bake runs too and the map
comes out lit. ``docs/public/wiring-your-build.md`` covers the setup.

    zmforge build zm_forge_gate --tools-dir ~/bo3-modtools
    zmforge build zm_forge_gate --stages compile_full,link
    zmforge build zm_forge_gate --loading-screen
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from ..errors import ForgeError, ToolchainError
from .layout import validate_map_name
from .stages import ChainOutcome, Toolchain
from .targets import PREFERENCES, Target, select_target

#: Stages ``zmforge build`` runs when ``--stages`` is not given.
DEFAULT_STAGES = ("compile_full", "bake", "link")


def add_arguments(parser: argparse.ArgumentParser, *, targets: Sequence[str] = PREFERENCES) -> None:
    """The build options, on *parser* (a subcommand or a script's own)."""
    parser.add_argument("map_name")
    parser.add_argument(
        "--stages",
        default=None,
        help="comma-separated: refresh, compile_full, compile_entities, bake, link "
        f"(default: {','.join(DEFAULT_STAGES)})",
    )
    parser.add_argument("--log-dir", default=None, help="default: ./zmforge-logs/<map>")
    parser.add_argument(
        "--language",
        default="english",
        help="localisation the link stage builds the map's strings for "
        "(default %(default)s)",
    )
    # "auto" and "local" are the same place when Wine on this machine is the
    # only target, so offer the choice only when there is a real one.
    if len(set(targets) - {"auto"}) > 1:
        parser.add_argument(
            "--target",
            default="auto",
            choices=tuple(targets),
            help="where to build (default %(default)s: Wine on this machine)",
        )
    else:
        parser.set_defaults(target="auto")
    parser.add_argument(
        "--tools-dir",
        default=None,
        help="your local copy of the mod tools (default: $ZMFORGE_WINE_TOOLS)",
    )
    parser.add_argument(
        "--prefix-dir",
        default=None,
        help="where the Wine prefix lives (default: $ZMFORGE_WINE_PREFIX, else a "
        "wineprefix beside --tools-dir). Set it when --tools-dir is a real Steam "
        "install, so the prefix does not land in steamapps/common",
    )
    parser.add_argument(
        "--loading-screen",
        action="store_true",
        help="link with the stock 'black' image pointed at "
        "usermaps/<map>/zone/loadingimage.png, which is what the game draws as "
        "the loading screen, and put the tools copy back afterwards "
        "(zmforge.toolchain.loadscreen_override)",
    )


def parse_stages(text: str | None, default: Sequence[str] = DEFAULT_STAGES) -> list[str]:
    if not text:
        return list(default)
    return [stage.strip() for stage in text.split(",") if stage.strip()]


def _override(command: list[str]) -> None:
    """Run the loading-screen override in its own process.

    Its own process because ``gdt.db`` needs a wide-column SQLite preloaded,
    and a preload here would be inherited by every Wine process the chain
    starts.
    """
    done = subprocess.run(
        [sys.executable, "-m", "zmforge.toolchain.loadscreen_override", *command],
        check=False,
    )
    if done.returncode != 0:
        raise ToolchainError(f"loading-screen override {command[0]} failed ({done.returncode})")


@contextlib.contextmanager
def _exit_on_termination():
    """Turn SIGTERM/SIGHUP into ``SystemExit`` for the block, so ``finally`` runs."""
    import signal
    import threading

    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def _stop(signum, frame):
        raise SystemExit(128 + signum)

    names = [n for n in ("SIGTERM", "SIGHUP") if hasattr(signal, n)]
    before = {n: signal.signal(getattr(signal, n), _stop) for n in names}
    try:
        yield
    finally:
        for n, handler in before.items():
            signal.signal(getattr(signal, n), handler)


def _restore_leftover_swap(args: argparse.Namespace) -> None:
    """Undo a loading-screen swap a killed build left in the tools install.

    :mod:`.loadscreen_override` writes its state file before it changes
    anything and deletes it last, so the file existing with no build holding
    the tools lock means a build died inside the window (SIGKILL, power loss)
    and the stock 'black' image still shows that map's picture.
    """
    from .loadscreen_override import STATE_NAME

    tools = args.tools_dir or os.environ.get("ZMFORGE_WINE_TOOLS")
    if not tools or not (Path(tools) / "gdtdb" / STATE_NAME).exists():
        return
    from .buildlock import tools_lock  # not at the top: see WineRunner.run

    with tools_lock():      # a live --loading-screen build holds it for its window
        if (Path(tools) / "gdtdb" / STATE_NAME).exists():
            print("== loading screen: a killed build left 'black' swapped; restoring it")
            _override(["restore", tools])


def _run_with_loading_screen(
    chain: Toolchain, args: argparse.Namespace, stages: list[str]
) -> ChainOutcome:
    """The stages before the link as usual, then the link inside the override."""
    tools = args.tools_dir or os.environ.get("ZMFORGE_WINE_TOOLS")
    if not tools:
        raise ToolchainError("--loading-screen needs --tools-dir or $ZMFORGE_WINE_TOOLS")
    from .buildlock import tools_lock  # not at the top: see WineRunner.run

    at = stages.index("link")
    outcome = chain.run_chain(args.map_name, stages=stages[:at], language=args.language)
    if not outcome.ok:
        return outcome
    # The override points the stock 'black' image, which every map shares, at
    # this map's picture; another map's link inside this window would pack
    # it. So the whole window is one hold of the shared-tools lock.
    # A SIGTERM (``kill``, a CI cancel, a closed terminal) would otherwise end
    # the process without running ``finally``, leaving 'black' pointed at this
    # map for every later link; SIGKILL cannot be caught, which is what
    # :func:`_restore_leftover_swap` at the next build start is for.
    with tools_lock(), _exit_on_termination():
        try:
            _override(["set", tools, args.map_name])
            rest = chain.run_chain(args.map_name, stages=stages[at:], language=args.language)
        finally:
            _override(["restore", tools])
    outcome.outcomes.extend(rest.outcomes)
    return outcome


def run_build(
    args: argparse.Namespace, target: Target, stages: list[str], *, where: str
) -> tuple[int, ChainOutcome | None]:
    """Run *stages* on *target*, print every verdict; ``(exit code, outcome)``."""
    log_dir = Path(args.log_dir or Path.cwd() / "zmforge-logs" / args.map_name)
    chain = Toolchain(target.layout, target.runner, log_dir=log_dir)

    print(f"== {args.map_name}: {', '.join(stages)} on {where}")
    if target.fell_back_because:
        print(f"== not building locally: {target.fell_back_because}")
    print(f"== tools root {target.layout.root}")
    print(f"== logs {log_dir}")
    started = time.monotonic()
    # Builds on one tools install share it: every step holds the global lock
    # shared (an old `flock build-out/.radiant.lock` caller still runs alone)
    # and this map's own lock; the stages take the finer locks themselves
    # (zmforge.toolchain.buildlock).
    from .buildlock import global_lock, map_lock  # not at the top: see WineRunner.run

    held = [global_lock().acquire(), map_lock(args.map_name).acquire()] if target.is_local else []
    try:
        if target.is_local:
            _restore_leftover_swap(args)
        if args.loading_screen and "link" in stages:
            if not target.is_local:
                print("!! --loading-screen needs the local target: the override edits "
                      "the tools install's gdt.db")
                return 2, None
            outcome = _run_with_loading_screen(chain, args, stages)
        else:
            outcome = chain.run_chain(args.map_name, stages=stages, language=args.language)
    except ToolchainError as problem:
        print(f"!! {problem}")
        return 2, None
    finally:
        for lock in reversed(held):
            lock.release()

    for stage in outcome.outcomes:
        print(f"\n-- {stage.stage}: {'ok' if stage.ok else 'FAILED'}")
        print(f"   exit code {stage.exit_code} (not the verdict), {stage.duration_s:.1f}s")
        print(f"   log {stage.log_path}")
        for artifact in stage.artifacts:
            size = chain.runner.size_of(artifact)
            print(f"   wrote {artifact} ({size} bytes)")
        for line in stage.evidence:
            print(f"   {line}")

    print(f"\n== chain {'ok' if outcome.ok else 'FAILED at ' + str(outcome.failed_stage)}"
          f" in {time.monotonic() - started:.1f}s")
    return (0 if outcome.ok else 1), outcome


def run(args: argparse.Namespace) -> int:
    """``zmforge build`` with parsed *args*."""
    try:
        target = select_target(
            args.target, tools_dir=args.tools_dir, prefix_dir=args.prefix_dir
        )
    except ToolchainError as problem:
        print(f"!! {problem}")
        return 2
    try:
        # Before anything is named after it: ``build ../..`` made
        # build-out/locks/map-.. and a log folder outside zmforge-logs.
        validate_map_name(args.map_name, target.layout)
    except ForgeError as problem:
        print(f"!! {problem}")
        return 2
    code, _ = run_build(args, target, parse_stages(args.stages), where="wine on this machine")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zmforge build", description=__doc__.splitlines()[0])
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
