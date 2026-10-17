"""Where a map gets built: this machine, under Wine, against a local mod tools folder.

The local target is a container away and needs no credentials. Whether it is
usable is a question about docker, an image and a copy of the tools on disk,
and is therefore *checked* rather than assumed
(:meth:`~zmforge.toolchain.wine.WineRunner.unavailable_because`). The lighting
bake runs here too: the image brings its own display and the runner its own
embree shim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..errors import ToolchainError
from .layout import ToolsLayout
from .runner import StageRunner
from .wine import DEFAULT_IMAGE, DEFAULT_WINDOWS_ROOT, WineRunner

__all__ = ["PREFERENCES", "Target", "local_problem", "local_wine_runner", "select_target"]


#: What ``select_target`` accepts. ``auto`` and ``local`` are the same target.
PREFERENCES: tuple[str, ...] = ("auto", "local")

#: Where the local copy of the tools is, when the caller does not say.
TOOLS_DIR_VARIABLE = "ZMFORGE_WINE_TOOLS"

#: Where the Wine prefix goes, when the caller does not say. Unset keeps the
#: runner's own default, a ``wineprefix`` beside the tools directory, which is
#: right when the tools are a copy in a working area (as in ``docker/bo3-wine``)
#: and wrong when they are the Steam install itself - there the prefix would
#: land in ``steamapps/common``. Anyone pointing this at a real Steam install
#: sets this variable; ``docker/bo3-wine/bo3-wine.env.example`` says so.
PREFIX_DIR_VARIABLE = "ZMFORGE_WINE_PREFIX"


@dataclass(frozen=True)
class Target:
    """A chosen build target, and why it was chosen.

    ``fell_back_because`` is the honest record of a degraded choice: it is
    ``None`` on the local target, and a caller that picked another target
    because the local one was unusable puts the local runner's reason here.
    """

    name: str
    runner: StageRunner
    layout: ToolsLayout
    fell_back_because: str | None = None

    @property
    def is_local(self) -> bool:
        return self.name == "local"


def local_wine_runner(
    tools_dir: Path | str | None = None,
    *,
    windows_root: str = DEFAULT_WINDOWS_ROOT,
    prefix_dir: Path | str | None = None,
    image: str = DEFAULT_IMAGE,
    docker: str = "docker",
    docker_args: Sequence[str] = (),
) -> WineRunner | None:
    """A Wine runner for the configured tools install, or ``None`` when there isn't one.

    ``None`` also covers "nobody said where the tools are": without
    *tools_dir* and without ``ZMFORGE_WINE_TOOLS`` there is nothing to
    guess from, and guessing a 5 GB directory's location is not helpful.

    *prefix_dir* falls back to ``ZMFORGE_WINE_PREFIX`` and then to the
    runner's own default.
    """
    if tools_dir is None:
        tools_dir = os.environ.get(TOOLS_DIR_VARIABLE) or None
    if tools_dir is None:
        return None
    if prefix_dir is None:
        prefix_dir = os.environ.get(PREFIX_DIR_VARIABLE) or None
    return WineRunner(
        tools_dir,
        windows_root=windows_root,
        prefix_dir=prefix_dir,
        image=image,
        docker=docker,
        docker_args=docker_args,
    )


def local_problem(runner: WineRunner | None) -> str | None:
    """Why *runner* cannot build, or ``None`` when it can."""
    if runner is None:
        return f"no mod tools install configured (set {TOOLS_DIR_VARIABLE} or pass --tools-dir)"
    return runner.unavailable_because()


def select_target(
    preference: str = "auto",
    *,
    tools_dir: Path | str | None = None,
    windows_root: str = DEFAULT_WINDOWS_ROOT,
    prefix_dir: Path | str | None = None,
    image: str = DEFAULT_IMAGE,
    docker: str = "docker",
    docker_args: Sequence[str] = (),
) -> Target:
    """The local target, or raise with the reason it cannot build."""
    if preference not in PREFERENCES:
        raise ToolchainError(
            f"build target must be one of {', '.join(PREFERENCES)}, not {preference!r}"
        )
    runner = local_wine_runner(
        tools_dir,
        windows_root=windows_root,
        prefix_dir=prefix_dir,
        image=image,
        docker=docker,
        docker_args=docker_args,
    )
    problem = local_problem(runner)
    if problem is not None:
        raise ToolchainError(f"cannot build locally: {problem}")
    assert runner is not None
    return Target("local", runner, ToolsLayout.windows(windows_root))
