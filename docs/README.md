# zmforge documentation

Start with the project `README.md` one level up: what zmforge is, how to
install it and how to build a map. The pages below go deeper. Each one is
self-contained.

## Getting a map built

| Page | What it covers |
|---|---|
| `public/wiring-your-build.md` | Installing the mod tools, then compiling, lighting and linking a generated map: in the Mod Tools Launcher on Windows, or with `zmforge build` under Wine on Linux. |
| `../docker/bo3-wine/SETUP.md` | The Linux (Wine) build in detail: what to supply, the setup commands, and the one patched file (`PATCHES.md`). |
| `workflows/build-a-map.md` | The step-by-step loop for a person or an AI agent: write a recipe, generate, check, render, fix. |
| `workflows/review-a-map.md` | Answering a `zmforge review` packet and importing the findings. |
| `developer-guide.md` | The full API walk-through: blueprints, rooms, doors, perks, scripts, the build chain. |

## How zombies maps work

| Page | What it covers |
|---|---|
| `public/building-bo3-zombies-maps.md` | A standalone guide to the failures that pass the build and break in game. |
| `how-zombies-maps-work.md` | How the engine, the compiler and the stock scripts behave, independent of zmforge. |
| `map-generator-spec.md` | The generator's behaviour specification: file formats, geometry, build chain, conformance tests. |
| `mapsource-format-reference.md` | The `.map`, `.gdt`, zone and script formats the tools consume. |
| `special-enemies.md` | Which special enemies work in a usermap with stock assets. |

## What makes a map good, and how it is checked

| Page | What it covers |
|---|---|
| `playable-map-requirements.md` | Every requirement a map must meet, with the check that tests it. `zmforge requirements` reads this file. |
| `map-principles.md` | The design principles `zmforge review` grades against. The review reads this file. |
| `map-design-method.md` | Designing every area as a scene. |
| `fog-and-gloom.md` | Fog, light and atmosphere settings. |

## Assets

| Page | What it covers |
|---|---|
| `open-source-assets.md` | Finding CC0 models and photos, checking a licence, turning an OBJ into an xmodel. |

## Licensing

`licensing.md` covers zmforge's licence, the mod tools terms and how they
apply to a tool that drives the tools, and the provenance of this code.
`../THIRD_PARTY.md` lists every file in this repository that is not
zmforge's own work, with its source and licence.
