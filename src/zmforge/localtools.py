"""Where the local copy of the mod tools and its Wine setup live.

Every default here is overridable by an environment variable, and nothing
from the mod tools is ever part of this repository:

``ZMFORGE_WINE_TOOLS``
    your own copy of the Black Ops III mod tools (the folder whose name ends
    in ``455130``, holding ``bin/``, ``share/`` and ``map_source/``).
``ZMFORGE_BO3_WINE``
    the Wine image project: its ``Dockerfile``, ``setup.sh`` and
    ``scripts/patch-embree.py``, and by default the ``wineprefix`` and
    ``tools`` folders that ``setup.sh`` uses.  Defaults to ``docker/bo3-wine``
    in this repository when it is there, else a ``bo3-wine`` folder beside it.
``ZMFORGE_WINE_PREFIX``
    the Wine prefix ``setup.sh`` created (default ``<bo3-wine>/wineprefix``).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["REPO", "bo3_wine_dir", "tools_dir", "wine_prefix_dir"]

REPO = Path(__file__).resolve().parents[2]


def bo3_wine_dir() -> Path:
    """The Wine image project (``ZMFORGE_BO3_WINE``)."""
    named = os.environ.get("ZMFORGE_BO3_WINE")
    if named:
        return Path(named)
    inside = REPO / "docker" / "bo3-wine"
    return inside if inside.is_dir() else REPO.parent / "bo3-wine"


def tools_dir() -> Path:
    """The local mod tools copy (``ZMFORGE_WINE_TOOLS``)."""
    named = os.environ.get("ZMFORGE_WINE_TOOLS")
    return Path(named) if named else bo3_wine_dir() / "tools"


def wine_prefix_dir() -> Path:
    """The Wine prefix ``setup.sh`` made (``ZMFORGE_WINE_PREFIX``)."""
    named = os.environ.get("ZMFORGE_WINE_PREFIX")
    return Path(named) if named else bo3_wine_dir() / "wineprefix"
