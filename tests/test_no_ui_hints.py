"""Player-facing text never explains the HUD ("your task is top left").

Players can see where the task tracker is; text that points at screen
corners is noise, so intro lines like that are removed.
"""
import re
from pathlib import Path

RECIPES = Path(__file__).resolve().parents[1] / "src" / "zmforge" / "recipes"
PATTERN = re.compile(r"\b(top|bottom) (left|right)\b|your task is", re.IGNORECASE)


def _string_literals(text):
    return re.findall(r'"([^"\n]*)"', text)


def test_recipe_text_never_points_at_screen_corners():
    hits = []
    for path in sorted(RECIPES.glob("*.py")):
        for literal in _string_literals(path.read_text()):
            if PATTERN.search(literal):
                hits.append(f"{path.name}: {literal[:80]}")
    assert not hits, "HUD-pointing text in player strings:\n" + "\n".join(hits)
