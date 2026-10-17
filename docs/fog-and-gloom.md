# Fog and gloom

BO3 maps support fog and gloom, and a generated map gets both from one per-recipe setting, `Atmosphere` in `src/zmforge/atmosphere.py`.

- **Visible fog is lit fog.** It is a `volume_litfog` brush over the playable space, naming a shipped fog asset. The engine lights it with the sun, the moon and the lamps, so it takes their colour.
- **Gloom is two worldspawn keys.** `vcolor` and `bloom` set the colour grade. `evauto`, `evmin` and `evmax` pin the exposure. `evcmp` is written too, as 0.
- **Each recipe has its own look:**

| Map | Preset | Fog | Gloom |
|---|---|---|---|
| zm_cemetery | `NIGHT_GLOOM` | The Giant's low lit ground fog; denser pockets in the crypt | The Giant's grade; exposure pinned half a stop darker |
| zm_corn_maze | `HARVEST_HAZE` | The same low lit fog, glowing gold and orange from the moon and the lanterns | None: the maze is dark already |
| zm_dmv | `OFFICE_DAY` | None | None |

**None of this has been checked in the game.**

<details><summary>What the engine supports, and where each setting lives</summary>

All read from the mod tools' own files.

- **Lit fog** (`volume_litfog`): keys `fsi`, `fsi_1`..`fsi_4`, `fogtime`, bank and lighting-state flags, `ENABLE_SUN`, `ENABLE_LIGHTS`. The entity definition is in `bin/t7.def.json`. The Giant uses one over its whole map (`zm_giant_light.map:4136`).
- **World fog** (`volume_worldfog`): the same `fsi` keys. The Giant's asset for it, `zm_factory_afog`, has world fog switched off, so it draws almost nothing on a small map.
- **World fog modifier** (`volume_worldfogmodifier`): scales a world fog's `depthscale`, `heightscale` and `opacity`, and tints it with `_color`. Not used.
- **Grade**: the worldspawn keys `vcolor` and `bloom` name a `.lvi` file in `share/raw/grades`. The Giant writes `"vcolor" "zm_factory"` and `"bloom" "zm_factory"`. The files are binary, so a map can only name a shipped one.
- **Exposure**: the worldspawn keys `evauto`, `evmin`, `evmax` and `evcmp`, or a `volume_exposure` brush for one area. The Giant writes `evauto 1`, `evmin 3`, `evmax 3.5` and `evcmp 2.5`.
- **LUT**: the worldspawn key `lutmaterial`. The Giant's `luts_t7_zm_factory` needs an image that a mod tools tree does not always carry, and a missing one breaks the link. Not used.
- **Area grades**: `pbg_box`, `pbg_omni` and `pbg_spot` apply a grade to one area. Not used.
- **Script**: client calls `SetLitFogBank`, `SetWorldFogActiveBank`, `SetExposureActiveBank` and `SetPBGActiveBank` switch banks at run time. The Giant uses them for dog rounds (`zm_giant_fx.csc:169-178`). Not used.
- The mod tools docs (`docs_modtools\Lighting_Parameters.pdf`) describe the `ev*` keys. `Multiplayer_Lighting_Workflow.pdf` says each map should have its own lighting GDT for sun, sky and fog.

</details>

<details><summary>Why the exposure pin darkens, and what is still a guess</summary>

- `evmin` and `evmax` are the lowest and highest exposure value the camera may use. Setting both to one value fixes the exposure.
- `ev` is the scene brightness the camera is set for: day presets run ev 12 to 15, The Giant's night runs ev 5. Lamps are placed at the preset's ev (`zmforge.lighting`). A higher ev therefore makes the picture darker, and a pin at ev + 0.5 dims every lamp by half a stop.
- **Unverified:** the direction, and whether a map without `ev*` keys really runs at the preset's ev. The spec claims it does, but nobody has measured it. If the cemetery looks brighter than before, the sign is wrong: set `exposure_stops` to -0.5.
- `Atmosphere(exposure_stops=...)` refuses a sun preset whose ev is not measured in `lighting.SSI_EXPOSURE`. It will not pin to a guess.

</details>

<details><summary>Lit fog colour, and the fog assets a map can name</summary>

- In `deffiles/fog.awi`, `fogcolor` applies only when `worldfog` is on. A lit fog has `worldfog` off, so its colour comes from the light it scatters. Where `albedo` is under 1, it also absorbs light, tinted by `extcolor`.
- Fog is compiled into the level, not linked. A zombies map can therefore name a multiplayer map's fog asset.
- The assets named so far are `zm_factory_volumetric` (low ground fog, boosts the moon by 2 stops), `zm_factory_dogs_volumetric` (thick, for crypts) and `mp_apartments_volumetric` (cold and absorbing, half opaque at 2000 units).
- To add another asset, read its fields off `source_data/fog.gdt` and add it to `STOCK_LIT_FOGS`. Anything else is refused.

</details>

## Checking it

What was checked, and what was not:

- **Checked:** the keys are in the generated `.map` files. The cemetery has `vcolor`/`bloom` `zm_factory` and `evmin` = `evmax` = 5.5. The corn maze has a `zm_factory_volumetric` lit fog. The DMV has no fog volume and no gloom keys.
- **Checked:** zm_cemetery compiles, bakes and links under Wine (a build with no install step; the chain finished in 188 s). The compiled `zm_cemetery.d3dbsp` carries `"vcolor"`, `"bloom"`, `"evauto"` and `"evmin"`.
- **Not visible in renders.** `zmforge render --baked --hero` of zm_cemetery with the fog volumes hidden, then shown (`ZMFORGE_RENDER_FOG=1`), gave pixel-identical pictures (mean difference 0.0). Radiant's camera, as the render drives it, draws neither the lit fog nor the grade. Do not judge fog from a render.
- **Not checked in the game.** Nobody has seen any of it played.

<details><summary>The render fog toggle</summary>

`ZMFORGE_RENDER_FOG=1 zmforge render ...` keeps Radiant's fog, exposure and grade volume filters shown (`render/radiant.py`, `FOG_PREVIEW_SHOWN`). Every other render hides all volumes. With the toggle on, the picture did not change. Radiant also has an "Enable Volumetric World Fog" action and a fog-bank menu (strings in `Radiant_modtools.exe`). The render does not click either, and nobody has tried them.

</details>

Low lit fog is the default for every spooky or night map.
