"""Per-prop colour overrides on swatch-atlas kits (props/library.py, props/build.py)."""

from __future__ import annotations

import colorsys

import pytest

from zmforge.props.build import palette_colours
from zmforge.props.library import FIELD_CORN, PROPS, Prop, prop
from zmforge.props.textures import build_palette

TEAL = (0.172549, 0.8470588, 0.7215686)  # Kenney Nature Kit "grass" Kd
COB = (0.9607843, 0.7372549, 0.3921569)  # Kenney Nature Kit "corn" Kd
CORN_MTL = {"grass": TEAL, "corn": COB}

# Generated stalks (props/corn.py) have replaced the Kenney stalks that were
# the override's only users; the mechanism stays for kit props, and these
# stand-ins keep it tested.
KIT_STALK = Prop("kit_stalk", "kenney_nature", "crops_cornStageD", 96.0, "test",
                 colours=(("grass", FIELD_CORN),))
KIT_STALK_THIN = Prop("kit_stalk_thin", "kenney_nature", "crops_cornStageC", 90.0, "test",
                      colours=(("grass", FIELD_CORN),))


def test_corn_leaves_are_field_corn_not_teal() -> None:
    hue, _l, sat = colorsys.rgb_to_hls(*FIELD_CORN)
    # Yellow (60 deg) to green (120 deg), and muted, not the kit's 170-deg teal.
    assert 45 <= hue * 360 <= 100
    assert sat < 0.5


def test_corn_stalks_override_leaves_only_and_cobs_keep_the_kit_colour() -> None:
    full, thin = KIT_STALK, KIT_STALK_THIN
    colours = palette_colours([(full, ["grass", "corn"], CORN_MTL),
                               (thin, ["grass"], {"grass": TEAL})])
    assert colours == {"grass": FIELD_CORN, "corn": COB}
    # Same cell as before the override: the models' UVs do not move.
    before = build_palette(CORN_MTL)
    after = build_palette(colours)
    assert after.uv("grass") == before.uv("grass") and after.uv("corn") == before.uv("corn")
    assert after.colours["grass"] == (148, 145, 79)


def test_no_shipped_prop_overrides_colours_since_the_corn_is_generated() -> None:
    assert {p.name for p in PROPS if p.colours} == set()
    assert prop("zmf_prop_corn_stalk").kit == "zmforge_generated"


def test_other_props_keep_the_kit_colours() -> None:
    toilet = prop("zmf_prop_toilet")
    assert palette_colours([(toilet, ["white"], {"white": (1.0, 1.0, 1.0)})]) == {
        "white": (1.0, 1.0, 1.0)}


def test_a_clash_on_a_shared_cell_is_an_error() -> None:
    full = KIT_STALK
    plain = prop("zmf_prop_toilet")  # stands in for a kit prop without the override
    with pytest.raises(ValueError, match="one swatch cell each"):
        palette_colours([(full, ["grass", "corn"], CORN_MTL), (plain, ["grass"], CORN_MTL)])
