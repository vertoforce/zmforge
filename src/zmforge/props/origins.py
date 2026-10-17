"""A stock model's box in the frame the engine draws it in, not the one it was authored in.

The measured-box table (:data:`zmforge.recipes.props.MODEL_BOX`) was read off
an asset catalogue of the stock models, which takes a model's box straight from
the vertex positions in its ``XMODEL_BIN``.  Those are in the artist's scene
frame.  The engine draws a model in its **root bone's** frame, so for a model
whose root bone is not on the scene origin the catalogue box is displaced by
exactly the root bone's offset (and turned by its axes, where it has any).

Measured over the catalogue's root bones: 138 of the 724 catalogue
models the tools tree can read have a moved root bone; 44 of them are in
``MODEL_BOX``.  The worst are the duct and light-fixture kits authored as one
scene: ``p7_duct_metal_circular_straight_32``'s root bone is at y = 150, its
catalogue box y 133.4..166.6, and it draws at its origin (a test map),
which is y -16.6..16.6.  Every check that placed its box by the
catalogue value judged a prop 150 units from where the player sees it.

:func:`drawn_box` swaps a box for the drawn one **only when it is the raw
catalogue box**, to the millimetre.  So a box someone measured or cut by hand
passes through untouched, and when the table the recipes read is corrected at
source this becomes a no-op rather than a double correction.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

__all__ = ["STOCK_ORIGINS_PATH", "stock_origins", "drawn_box", "drawn_boxes"]

Box = tuple[tuple[float, float, float], tuple[float, float, float]]

STOCK_ORIGINS_PATH = Path(__file__).with_name("stock_origins.json")

#: How close a box has to be to the recorded raw catalogue box to count as it.
#: The table rounds to 3 decimals and ``MODEL_BOX`` carries 3 too.
MATCH = 0.01


@lru_cache(maxsize=1)
def stock_origins() -> Mapping[str, Mapping]:
    """``{model: {"root", "raw", "drawn"[, "axes"]}}`` for each moved root bone."""
    return json.loads(STOCK_ORIGINS_PATH.read_text())["models"]


def _same(a, b) -> bool:
    return all(abs(a[i][j] - b[i][j]) <= MATCH for i in range(2) for j in range(3))


def drawn_box(model: str, box: Box | None) -> Box | None:
    """``box`` in the model's drawn frame, if it is the raw catalogue box.

    Anything else -- ``None``, a model with its root bone on the origin, a box
    that is not the catalogue's -- comes back as it went in.
    """
    if box is None:
        return None
    entry = stock_origins().get(model)
    if entry is None or not _same(box, entry["raw"]):
        return box
    lo, hi = entry["drawn"]
    return (tuple(lo), tuple(hi))  # type: ignore[return-value]


def drawn_boxes(table: Mapping[str, Box]) -> dict[str, Box]:
    """A copy of a model -> box table with every raw catalogue box made drawn."""
    return {name: drawn_box(name, box) for name, box in table.items()}  # type: ignore[misc]
