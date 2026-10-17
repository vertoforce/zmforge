"""Render-only kit atlases rebuilt from the current props code (render/propfix.py)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from zmforge.props.library import FIELD_CORN
from zmforge.props.textures import build_palette, write_tif
from zmforge.render import propfix

TEAL = (0.172549, 0.8470588, 0.7215686)
COB = (0.9607843, 0.7372549, 0.3921569)
BARK = (0.45, 0.3, 0.2)
DEPLOYED = {"grass": TEAL, "corn": COB, "bark": BARK}
NAME = "zmf_kenney_nature_c.tif"  # a real flat-colour kit whose corn recolours "grass"


def _deployed(tmp: Path) -> Path:
    p = build_palette(DEPLOYED)
    tools_tif = tmp / "tools" / "texture_assets" / "zm_x" / NAME
    return write_tif(p.size, p.size, p.pixels(), tools_tif)


def _rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def test_rebuilt_atlas_changes_only_the_recoloured_cell(tmp_path: Path, monkeypatch) -> None:
    # No shipped prop recolours a kit cell now that the corn is generated;
    # a stand-in kit stalk keeps the mechanism tested.
    from zmforge.props import library

    stalk = library.Prop("kit_stalk", "kenney_nature", "crops_cornStageD", 96.0, "test",
                         colours=(("grass", FIELD_CORN),))
    monkeypatch.setattr(library, "PROPS", library.PROPS + (stalk,))
    old = _deployed(tmp_path)
    current = build_palette({**DEPLOYED, "grass": FIELD_CORN})
    made, why = propfix.regenerate(old, tmp_path / "regen", palette_for=lambda _s: current)
    assert made is not None, why
    a, b = _rgb(old), _rgb(made)
    changed = (a != b).any(axis=2)
    grass = propfix._cells_of(current, ["grass"])
    assert changed.sum() == grass.sum() > 0        # the whole grass cell, nothing else
    assert not (changed & ~grass).any()            # every other pixel identical
    u, v = current.uv("grass")
    y, x = int(v * current.size), int(u * current.size)
    assert tuple(b[y, x]) == current.colours["grass"] == (148, 145, 79)


def test_moved_layout_is_refused_not_used(tmp_path: Path) -> None:
    old = _deployed(tmp_path)
    # A new material sorts first and shifts every cell: the deployed models'
    # UVs would now sample the wrong colours.
    shifted = build_palette({**DEPLOYED, "grass": FIELD_CORN, "aaa_new": (1.0, 0.0, 0.0)})
    made, why = propfix.regenerate(old, tmp_path / "regen", palette_for=lambda _s: shifted)
    assert made is None and why.startswith("layout differs")
    assert not (tmp_path / "regen" / NAME).exists()


def test_same_colours_keep_the_tools_copy(tmp_path: Path) -> None:
    old = _deployed(tmp_path)
    made, why = propfix.regenerate(old, tmp_path / "regen",
                                   palette_for=lambda _s: build_palette(DEPLOYED))
    assert (made, why) == (None, "unchanged")


def test_layout_mismatch_falls_back_to_tools_copy_with_a_warning(tmp_path, monkeypatch) -> None:
    old = _deployed(tmp_path)
    tools, cache = tmp_path / "tools", tmp_path / "cache"
    monkeypatch.setattr(propfix, "plan", lambda models, tools: ([], [old]))
    monkeypatch.setattr(propfix, "regenerate",
                        lambda tif, scratch: (None, "layout differs: 5 pixel(s) changed"))
    # The tools-tree copy is already converted, so no container runs.
    cache.mkdir()
    # The cache key carries the copy's colour type (render v4:
    # copies are forced to 16-bit true colour, so old grey copies are not reused).
    salt = "16bit-zip-v1" + propfix._colour_type(old)
    fallback = cache / f"{old.stem}-{propfix._digest(old, salt)}.tif"
    fallback.write_bytes(b"x")
    lines: list[str] = []
    fix = propfix.tif16_copies(["zmf_prop_corn_stalk"], tools=tools, image="unused",
                               cache=cache, log=lines.append)
    assert fix.regenerated == []
    assert fix.mounts == [(str(fallback), f"/tools/texture_assets/zm_x/{NAME}")]
    assert any(line.startswith("!! WARNING") and NAME in line for line in lines)
