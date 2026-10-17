# zmforge

Generate Black Ops III zombies maps — Radiant `.map` source, the GSC server and
client scripts, the linker's asset manifest and the map's loading screen — from
one validated model.

zmforge is a set of tools, one per step: `generate`, `check`,
`requirements`, `render`, and `review` (which writes a review packet). None
of them calls an AI model. People or AI agents drive them through the
workflows in `docs/workflows/`: `build-a-map.md` and `review-a-map.md`.

The package name is short and easy to change: it appears in `pyproject.toml`, the `src/zmforge`
directory and the import lines, nowhere else.

## Documentation

`docs/README.md` is the entry point and says which document answers what.
How to design an area (a one-line scene story, set pieces that make lanes,
three layers, light pools and fire, dressed boundaries), with targets measured
from the stock map: `docs/map-design-method.md`.
Behind it: the behavioural specification (`docs/map-generator-spec.md`), the
primary-source format reference (`docs/mapsource-format-reference.md`) and the
licensing position
(`docs/licensing.md`).

## What it does

```python
from zmforge import Project
from zmforge.recipes import three_room_map

project = Project.create(
    "zm_forge_gate",
    r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130",
    blueprint=three_room_map("zm_forge_gate"),
)
result = project.commit()          # writes every file, atomically, or none
assert result.ok                   # every static check passed
```

or from a shell:

```
zmforge generate zm_forge_gate --tools-root "<mod tools root>" --recipe three-room
zmforge check    zm_forge_gate --tools-root "<mod tools root>"
```

Nothing touches disk until `commit`, and `commit` refuses to write while the
model-level checks report an error. A map that fails them is one the game loads
and then kills the player on; finding that out costs a build plus a play
session.

### Loading screen and display name

A usermap's loading screen is not an asset: it is `loadingimage.png` (1920 x
1080) in `usermaps\<map>\zone\`, beside `previewimage.png` (600 x 340), and
the map's menu name is the manifest's `>title` line. All three are measured
from the mod tools' own map template — see the format reference §3.6. The
linker cannot complain about any of them, so a map that links cleanly still
loads on a black screen and shows up under its asset name.

`zmforge loadscreen <recipe>` makes the presentation images (principle P21):
the loading screen is the plan below, trimmed and fitted to fill 1920 x 1080
with the title; the preview card and the 512 x 512 Workshop thumbnail are a
baked-lit Radiant photograph (it shoots a few candidate cameras, keeps the
best-scoring one or `--pick`, then grades, hazes foggy maps, vignettes and
titles it). They land in `build-out/presentation/<map>/`, which `generate`
uses ahead of anything else; the loading screen still needs a link to reach
the `.ff`, the other two are plain files. Candidates and finished cards go to
`build-out/loadscreens/<map>/`; per-recipe camera overrides live in
`render/presentation.py` (`CAMERAS`) or on the command line (`--camera`).

`commit` writes both PNGs. The default image is the map's own plan, drawn by
`zmforge.emit.planview` on `zmforge.images`: rooms, walls, doorways, yards,
priced doors, machines, spawns and start points, with the title, the element
counts and a scale bar. Nothing in it is invented, and the same blueprint
always renders the same bytes. Supply your own with
`commit(loading_image=...)` (PNG bytes or a path — checked against the
template's size, never resampled) or turn the pair off with
`loading_screen=False`.

### Eight-player maps

```
zmforge generate zm_forge_eight --tools-root "<mod tools root>" --player-slots 8
```

**A generated map does the whole map side and still needs a mod for the
lobby.** The lobby's limit is LUI, and the mod tools' linker will not pack a
Lua raw file into a usermap at all: it answers with `ERROR: Lua not
supported` and fails the link, measured on Windows and again under
Wine. **Three** things in a
generated map follow the requested player count; the fourth gate is not the
map's to open.

The player count is not something a `.map` declares, and it is not one gate
but two, in different layers. The Workshop mods that raise it ship GSC and
LUI rawfiles, no map assets, and work on any map.

The first is how many `initial_spawn_points` structs it has.
`zm::getfreespawnpoint` returns the struct whose framework-assigned `en_num`
equals `player.playernum`, and `spawnpoints[ 0 ]` when the index runs past
the end of the array, so a four-slot map in an eight-player game puts players
five to eight on one point. Eight structs seat eight, and in a four-player
game the extra four are simply never returned — nothing counts the array.

The second is one line of script, and without it the structs are pointless.
`_zm.gsc:7067 player_too_many_players_check` takes `max_players = 4` (8 only
for `zgrief`/`zmeat`), and above that it calls
`zm_game_module::freeze_players( true )` and `level notify( "end_game" )`.
`_zm.gsc:1865` threads it out of `onPlayerSpawned`, on every spawn, so the
fifth player to join ends the match. A map can switch that off for itself:
`level.player_too_many_players_check` is assigned `true` at `_zm.gsc:252`
inside `zm::init()`, which the framework entry reaches synchronously
(`zm_usermap::main()` → `load::main()` at `_load.gsc:79` → `zm::init()`), and
is read later on spawn, so an assignment after `zm_usermap::main()` lands
between the write and the read. Ask for more than four slots and the emitted
`main()` carries `level.player_too_many_players_check = false;` immediately
after the framework entry. Check `Z26` fails a written map that has the
structs and not the statement, and warns on the statement without the structs.

`--player-slots` defaults to 4 and never goes below it. Four slots land
exactly where they did before the option existed, and emit no cap line; more
than four start a second row behind the first rather than widening the set,
so a start room that fits four fits eight. Every slot is checked for floor
under it.

The third is the per-player state the stock scripts only set up four of:
`level.laststand_update_clientfields` and `level.player_name_directive`
(`_zm_laststand.gsc:52-56, 91-95`), their client twins
(`_zm_laststand.csc:19-27`), and the six score fields `_zm_score.gsc:28-33`
registers per player over `MAX_CLIENTS_ZM` (`_zm_utility.gsh:18`, `4`). The
emitted scripts extend all of them from slot four upward. They are `level`
arrays and public functions, so the map extends them rather than replacing
the scripts that made them.

<details><summary>The lobby gate, and why the map cannot open it (measured)</summary>

The lobby is the gate that actually refuses the fifth player: the in-game
check freezes everyone and ends the match, while the lobby check leaves a
joiner sitting on "waiting for other players". Its limit is LUI, not script
— `Engine.GetLobbyMaxClients`.

The community's lobby-size page offers a map-side route for exactly this:
ship the Lua as a `rawfile` and force-load it from the `.csc` with
`LuiLoad`. **That route does not link.** A usermap zone
carrying `rawfile,ui/zmforge/<map>_lobby.lua` produced one line —
`ERROR: Lua not supported` — on Windows, and the same line under Wine, in a
46 s link. The linker still wrote a fastfile, so only the log said
anything was wrong. Check `Z27` fails any map that declares a `.lua` or
`.luac` raw file, so such a map never reaches a build.

Corroborating this, there is not one `.lua` or `.luac` file anywhere under the mod tools
install, and not one shipped `.zone` mentions Lua. The mod tools ship no
`share/raw/ui` tree at all. Raising the lobby limit stays mod territory.
</details>

<details><summary>Why the map does not just override the stock scripts, which is what every tutorial does</summary>

It cannot. `zm_level.class:5-13` carries `ignore,core_patch`,
`ignore,core_ui`, `ignore,zm_patch` and `ignore,zm_common`, and every
usermap is `>class,zm_mod_level`, which includes it. `ignore` means "if the
asset is already in that shipped fastfile, drop it from this one", so a
usermap zone line for `ui/t7/utility/lobbyutility.lua` (only in
`core_patch`) or `scripts/zm/_zm_laststand.gsc` (only in `zm_patch`) is
silently dropped at link time. Measured: of the
3,088 assets in a built map's fastfile, **0** overlap
`core_patch`, `core_ui`, `core_common`, `zm_patch` or `zm_common`, and 235
of the 653 dropped dependencies are exactly assets that live in one of them.
A mod is not bound this way — `zm_mod.class` and `core_mod.class` carry only
`ignore_missing_shipped` — which is why the community's lobby-size recipe is
written as a mod.

What a usermap *can* carry is an asset at a name no shipped fastfile uses —
Treyarch's own does, `zm_giant.zone:38` `rawfile,vision/zm_factory.vision`.
That is a real freedom and it is not enough for the lobby: a fresh name gets
a Lua file past `ignore`, and then the linker refuses the file type itself.
Two separate walls, and the second one is the one that bites.
</details>

<details><summary>Playing this map with a bigger-lobby mod loaded as well</summary>

The script side is written to lose gracefully to a mod rather than fight
it. Its two `level` arrays are extended per slot and
only where the slot is free, so a mod that seats six and a map that wants
eight add up instead of colliding; the score fields, which have no
per-slot record to test, are skipped entirely when the mod is detected
(slot four of the last-stand array already taken). None of this has been
played, and whether a duplicate client-field registration would actually
have hurt is unmeasured — the guards are cheap and the failure is not.
</details>

**What is still out of reach.** Only four playable characters exist, so
players five to eight share character 0:
`assign_lowest_unused_character_index` returns `0` once the four indices are
taken. And the client half of the per-player *score* fields is a LUI model
file (`_zm_score.gsc:103` points at the client-side registration in
`raw/ui/uieditor/clientfieldmodels.lua`), which is a `core_patch` asset and
therefore not the map's to change: the extra seats' score widgets have no
model behind them. The last-stand path guards for exactly that
(`_zm_laststand.csc:85` `if( isdefined( model ) )`), so the expected cost is
a missing bleed-out indicator rather than a crash — expected, not measured.

**Nothing here has been played.** All of it is a reading of the mod tools'
own raw scripts under `share/raw/scripts/zm`, the shipped assetlists and
class files under `zone_source/`, and Treyarch's shipped `.map` files. The map
side is more than spawn structs, and the rest is possible from a map.

### Placing and surfacing, for a caller with its own editor

Three small calls for a caller that lays a map out in its own editor rather
than through a recipe, each with its own tests:

- `Blueprint.place_prefab(path, position, facing, yaw=)` places any stock
  prefab and nothing else - no script module, no zone, no edge. It is the
  generic form of what `place_perk` and `place_power_switch` already emit.
- `RoomMaterials(..., sides={Side.NORTH: material})` gives one wall of a room
  its own material. A floor or ceiling entry is refused, because `floor` and
  `ceiling` already say that.
- `Material(name, scale, scale_v)` lays a material at a different scale on each
  face axis, which is how a rectangle W x H units shows one copy of an image
  rather than a tiled one.

`zmforge.texture.gdt` imports without the `[textures]` extra, so a
caller can write the asset-database entries for its own images without numpy.

### Build chain

`zmforge.toolchain` runs the compiler, the lighting baker and the linker, and
decides each stage's verdict from **evidence in its log**, never from the exit
code — the compiler exits 0 on an unsealed map and the linker never exits 0 at
all (we measured 2000 on a successful link, and 154000 has been recorded too).

## Layers

Each layer depends only on the ones below it, and each is usable on its own.

| Module | Holds |
|---|---|
| `mapsource` | the `.map` text format: document model, reader, writer, number formatting |
| `solids` | convex-solid maths: half-spaces, winding, box, wedge, stairs, room shells, validation, overlap scan |
| `surfaces` | patch grids and heightfields: meshing, chunking, orientation, ground lookup |
| `blueprint` | the map model: rooms, openings, yards, terrain, zones, spawns, doors, machines, lights |
| `images` | PNG encoder, raster and bitmap font: no imaging dependency |
| `emit` | blueprint → map document, server script, client script, manifest, plan view |
| `verify` | checks over the model, over the written files, and over the build logs |
| `toolchain` | stage runners, evidence parsers, the local and Wine runners |
| `texture` | room-scan photogrammetry to tiling game textures, and the asset-database text for them |
| `props` | third-party `.obj` models into game xmodels, and into a map that exists |
| `script` | custom gameplay script: the model, the stock symbol table, the checker |
| `recipes` | whole-map compositions |
| `facade` | the CLI; argument conversion only, no logic |

`verify` reads files through `mapsource` and never through `emit`'s in-memory
objects, so it tests what was actually written.

## Custom gameplay script

The generated `.gsc` used to be scaffolding and nothing else: the `#using`
lines, `main`, the zone hook. `script` is how gameplay logic gets in without
anyone editing the emitted file, which would not survive the next commit
because the file is regenerated whole every time.

```python
from zmforge.blueprint import CustomFunction, CustomScript, Slot

blueprint.add_custom_logic(CustomScript(
    using=("scripts\\shared\\laststand_shared"),
    functions=(CustomFunction("my_thing", ("wait 1;"))),
    statements=((Slot.AFTER_ENTRY, "level thread my_thing();")),
))
```

Statements bind to one of four slots; functions are appended after everything
the engine writes. There is deliberately no slot between
`level.dog_rounds_allowed` and the framework entry, because that ordering is
load-bearing and nothing a caller supplies should be able to break it.

A GSC error in this game is fatal -- the map dies on load or mid-round -- and
scripts are only compiled inside the link, whose exit code is never zero, so
two checks run in the process that writes the text and fail a commit:

- **Z15**, structure: brackets, string literals, statement terminators,
  statements outside a function, a name defined twice;
- **Z16**, references: a call or `&pointer` to a function nothing defines, a
  namespaced call absent from the stock symbol table, or a known call whose
  module the script never `#using`s.

`script/symbols.py` is that table. Every entry carries the file and line it
was read from, and nothing may be added that was not read: a plausible-looking
function name compiles fine and kills the game when the line runs.

`script/perks.py` is the biggest thing on that seam: **a perk the game does
not have**. A recipe names it, prices it and says what it does, and one call
writes the five `zm_perks::register_*` calls into the map's own script, the
machine struct into the `.map`, the buy prompt into the map's `.str` and both
`#precache` directives. Nothing is imported: the bottle, the machine model and
the machine light are stock names, free to use. `zm_dmv` sells TAKE A
NUMBER, which pays the holder a few points at the start of every round.

Two limits, said plainly. There is **no jingle** -- the machine's jingle is a
sound alias and a usermap on the mod tools install has none, so a stock perk machine in
a usermap is already silent the same way. And the **icon is a claimed slot**:
the HUD's key-to-image table lives in a Lua widget the linker
refuses to pack, so a perk lights one of the two keys that table binds to art
the game never shipped, or it shows no icon. Check `Z50` holds the five ways a
custom perk fails quietly. **Nobody has played one.**

`script/tricks.py` is a set of mechanics built on the seam -- a weapon that
downs whoever fires it, perk machines that refuse or that charge and give
nothing, a mystery box forced to one weapon, a spawn
spike on a door flag, a short-hop teleporter -- each with its stock-script
evidence in the docstring and in a comment in the emitted file. **None of
them has been played**; each docstring names its unverified parts.

## Seeing a map before a playtest

`zmforge render <recipe>` generates the map and photographs every room in
Radiant's own 3D camera, so the pictures show the real stock models and
materials, and zmforge's own props and textures too. Each room gets two high
corner views and one eye-height view from each doorway (`--views N` caps it).
Every run lands in `build-out/render/<map>/<time>/` with a contact sheet
(`sheet.jpg`), and `build-out/render/<map>/latest` points at the newest run.
`zmforge review <recipe>` renders the changed rooms itself and lists the
pictures with each room's call in the review packet (`--no-visual` skips that).

```
zmforge render dmv --rooms queue,records            # just these rooms
zmforge render dmv --changed --compare latest       # only rooms that changed, before|after sheets
zmforge render dmv --list                           # camera positions only, no Radiant
zmforge build zm_dmv          # compile, bake and link with your mod tools install
```

### How agents should use this

1. After changing a room, render it: `zmforge render <recipe> --changed --compare latest`
   (or `--rooms <room>`). Only rooms whose brushes or props changed are shot again.
2. Look at the contact sheet and the `compare/` sheets, never the raw PNGs
   first. They are at most 1024 px; keep anything you open at or under that.
3. Fix what looks wrong: floating or buried props, props through walls,
   black or missing surfaces, empty rooms, blocked doorways, text you cannot read.
4. Render again with `--compare latest` and check the before|after sheet
   shows the fix. Keep both run folders; they are the evidence.
5. A render runs alone on its host; `render` waits for running builds and
   renders to finish by itself. Builds of different maps run side by side
   (`docs/public/wiring-your-build.md`, "Running builds side by side").

<details><summary>Output layout and options</summary>

- `<room>--<view>.png`: one per camera, at most `--width` (1024) px.
- `sheet.jpg` (or `sheet-01.jpg`... for more than 4 rooms): the contact sheet.
- `compare/<room>--<view>.jpg`: before on the left, after on the right, with
  `--compare latest` (the run before this one) or `--compare <run dir>`.
- `views.json`: cameras, per-room hashes, which rooms were rendered or reused,
  the map's own assets registered for the render, and timings.
- `--changed` hashes each room's brushes and props in the generated `.map`
  (plus its cameras and the render settings) and re-shoots only rooms whose
  hash differs from `latest`; the rest are hard-linked, so every run folder is
  complete. Rooms a partial run was not asked for are carried forward too.
- `--baked`: see "Lighting" below.

</details>

<details><summary>How it works and what it cannot show</summary>

- Radiant runs under Wine in `docker/radiant-render` (the `bo3-wine` image plus
  xdotool, xwd and imagemagick), on the GPU through DXVK, inside a Wine virtual
  desktop; it waits for free VRAM rather than falling back to the CPU.
- It needs the mod tools at `docker/bo3-wine/tools`; the map is copied to
  `map_source/zm/zmforge_render/`, and a private copy of the Wine prefix
  (`build-out/render/.radiant`) carries the filter settings (Game View on,
  clip, caulk, sky brushes, triggers and volumes hidden).
- One Radiant session shoots every view of a run: the load is paid once.
- zmforge's own assets: before Radiant starts, the render lists every material
  and model the `.map` names that the shared `gdt.db` lacks, registers any
  zmforge `.gdt` declaring them into a private copy of `gdt.db` mounted only
  into the render container, and prints what is still missing. Radiant
  multiplies a model's texture by its vertex colours, so a kit prop
  (`zmf_prop_*`) whose vertex colours are 0,0,0 draws as a black shape. The
  render lays copies of such props' `.XMODEL_BIN` with white vertex colours
  over the originals, in the render container only (`render/propfix.py`), so
  they draw with their real shapes; `props/xmodel.py` writes white vertex
  colours, so props it builds need no patch. The kit materials' wall-texture
  layout (`lit_detail`, no normal map) also hid their colour map on a model.
  The render's private gdt.db rewrites those rows to a stock `lit` layout,
  keeping their colour map, and mounts 16-bit copies of their 8-bit `.tif`s,
  which Radiant does not convert. Game appearance is unverified.
- Lighting is Radiant's view-based fake lighting. Its "real" mode draws a
  room the same as fake. Whether Radiant can show a bake's `.led` has
  not been measured, so `--baked` only checks that
  the `.led` exists and switches to "real" mode.
- The render does not use the game itself, so it gives no in-engine
  screenshot.

</details>

## Install and test

Create a virtualenv at `.venv`:

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,textures]'
.venv/bin/python -m pytest -q
```

The map generator itself has no dependencies. Only `texture` needs numpy,
pillow and scipy, and it is the `[textures]` extra. `generate`, `check` and
`paths` keep working without them.

`tests/corpus/` holds `shipped-solid-shapes.json`, a counts-only ledger measured
off the shipped maps. Treyarch's own `.map` files are not redistributed; tests
that round-trip them look for copies in `tests/corpus/`. `tests/logs/` holds
three logs captured from the real tools, so the evidence parsers are pinned to the tools' actual
wording rather than to a paraphrase of it.

## Custom prices, and a gun of the map's own

```python
blueprint.place_wall_weapon("smg_standard", point, Facing.EAST, price=1337)
blueprint.set_weapon_price("ray_gun", 4200)
blueprint.add_custom_weapon(CustomWeapon("zmf_test", 4200, definition=r"source_data\my_gun.gdt"))
```

A price is not a key on the wall buy. `_zm_weapons.gsc:3362
load_weapon_spec_from_table` reads a string table and `add_zombie_weapon`
(`:529`) stores each row's cost on a struct in `level.zombie_weapons[ weapon ]`
that the purchase reads live, so a map that charges its own prices ships its
own weapon table — which is what Treyarch's own levels do
(`zm_usermap.gsc:433`). Ask for a price and the map grows one file, one zone
line and three lines of script; ask for none and it emits exactly the map it
emitted before the option existed. That is the whole default.

The generated table is an **overlay**, not a copy of Treyarch's fifty rows.
The map wins the loader hook — `zm_usermap.gsc:135` installs the stock loader
with `DEFAULT( level._zombie_custom_add_weapons, &custom_add_weapons )` and
`DEFAULT` only assigns while the variable is undefined, so a map that assigns
it in its own `main()` before the framework entry wins — and the generated
loader then loads Treyarch's table first and the map's own second.
`add_zombie_weapon` ends with `level.zombie_weapons[ weapon ] = struct`, keyed
by the weapon, so the second load replaces a row rather than adding a
duplicate. A re-priced row is the install's own row with the cost column
changed and nothing else, read at commit time: invent the row instead and the
weapon silently loses its upgrade, its voice-over and its box eligibility.

**The client half is the one that bites.** The number on the purchase prompt is
filled in client side, and the client has no hook: `zm_usermap.csc:83` calls
`include_weapons()` directly, which loads the stock table at `:95`. So the
generated `.csc` loads the map's table again, after the framework entry. Miss
that and the player is charged the map's price and shown Treyarch's. Check
**W4** holds all four halves of this together — hook before the entry, stock
table first, same table both sides, declared in the manifest.

**The name still cannot be changed.** Spec 5.7 is unchanged: the weapon's name
never passes through script, the framework overwrites the hint with a localized
reference whatever the table says. Price yes, name no.

A custom weapon is a `weapon` line in the zone, a row in that table, and a
`bulletweapon.gdf` entity in a `.gdt` that `zmforge.texture.gdtdb` registers —
one entry wider than it was, and the same two rows it writes for an image or a
material. The definition itself is the caller's file: a bullet weapon states
around a thousand fields and the install ships no stock weapon source to derive
them from. The linker fails loudly on a `weapon` line it cannot resolve, which
is the good half; a **table row** naming a weapon that does not exist is
invisible to it, because a string table is opaque, so check **W5** is what
stands there instead.

Measured: a one-room probe map whose
`smg_standard` wall buy asks 1337, compiled and linked under Wine, and
the linker's own `zone_source/all/assetlist/zm_test.csv` carries
`stringtable,gamedata/weapons/zm/zm_test.csv`. **Nothing here
has been played.** What the buy charges and what its prompt says are both
things only a play session can settle.

## Prior art

An earlier project by other authors built Black Ops III zombies maps
programmatically and drove the same tool chain. It is the reason this one
exists: the questions it answered — which entity keys the stock scripts read,
the reversed brush winding, the yard a barricade needs, that the linker's exit
code means nothing — were paid for with playtests, and a specification distilled
from that experience is what this implementation was written against.

**This implementation was written from that written specification
(`docs/map-generator-spec.md`) without reference to the earlier
project's source code.** No file of it was read, listed, searched or executed
during development. Where the spec records a value as a preference rather than a
requirement, this implementation is free to differ and sometimes does; where it
records a fixed name or a measured constant, that is reproduced exactly.

## Licence

PolyForm Noncommercial License 1.0.0 (free for personal and non-commercial use; source-available, not OSI open source). See `LICENSE`. Asset names, entity keys and prefab paths referenced in the
code are identifiers belonging to the game and its tools; none of the game's
data is included here.
