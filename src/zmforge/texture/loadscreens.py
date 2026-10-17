"""Which recipes draw their own full-screen loading image, and how.

``zmforge generate`` writes ``loadingimage.png`` for every map. With no
``--loading-image`` it asks here first: a recipe listed in
:data:`LOADING_SCREENS` gets its own art, any other recipe gets the plan view
``Project.commit`` draws. Adding a map's loading screen is one line in this
table and a function returning 1920 x 1080 PNG bytes; the recipe module itself
does not change.

What makes the image reach the screen is a separate step, the link-time
override of the stock ``black`` image (:mod:`zmforge.toolchain.loadscreen_override`).
"""

from __future__ import annotations

from typing import Callable

__all__ = ["LOADING_SCREENS", "loading_screen_for"]


def _dmv() -> bytes:
    from .dmv_loadscreen import loadscreen_png

    return loadscreen_png()


def _corn_maze() -> bytes:
    from .corn_maze_loadscreen import loadscreen_png

    return loadscreen_png()


def _cemetery() -> bytes:
    from .cemetery_loadscreen import loadscreen_png

    return loadscreen_png()


#: recipe name (as ``--recipe`` spells it) -> PNG bytes of its loading screen.
LOADING_SCREENS: dict[str, Callable[[], bytes]] = {
    "dmv": _dmv,
    "corn_maze": _corn_maze,
    "cemetery": _cemetery,
    "cemetery-dusk": _cemetery,
}


def loading_screen_for(recipe: str) -> bytes | None:
    """The recipe's own loading screen, or None to fall back to the plan view."""
    draw = LOADING_SCREENS.get(recipe)
    return draw() if draw is not None else None
