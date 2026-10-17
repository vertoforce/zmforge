# Wiring zmforge to your own mod tools

zmforge writes a map. Your own copy of the Black Ops III Mod Tools (Steam app
455130) compiles, lights and links it. This page says what zmforge expects
from that copy and how to hook each step into your own setup.

There are two ways to build:

- **Windows, by hand.** Run `zmforge generate` with `--tools-root` pointing at
  your mod tools folder, then compile, light and link in the Mod Tools
  Launcher as usual. Nothing else to set up.
- **Linux, from the command line.** `zmforge build` and `zmforge render` run
  the tools and Radiant under Wine in a container, against a local copy of
  your mod tools folder. The one-time setup is below. For the lighting bake
  it patches one import in a copy of your own tools' Embree DLL (an
  Apache-2.0 library); Steam's terms restrict modifying software accessed
  via Steam, so that step is your call (`docker/bo3-wine/PATCHES.md`).
  Compile and link work without it.

Nothing from the mod tools ever goes into this repository. zmforge reads the
stock files it needs from your copy when it runs.

## What zmforge expects

- **A mod tools folder.** The one whose name ends in `455130`, holding
  `bin/`, `share/`, `map_source/`, `deffiles/` and `source_data/`. It must be
  writable: every stage writes into it.
- **Its tools.** `bin/cod2map64.exe` (compile), `bin/linker_modtools.exe`
  (link) and `bin/radiant_modtools.exe` (lighting bake and the pictures).
- **On Linux only:** Docker, an NVIDIA GPU with `nvidia-container-toolkit`
  for the lighting bake and the pictures, and about 12 GB free for the Wine
  prefix. Compile and link run without a GPU.

<details><summary>Environment variables zmforge reads</summary>

- `ZMFORGE_WINE_TOOLS`: your local mod tools copy. `zmforge build` needs it
  (or `--tools-dir`); `zmforge render` defaults to `docker/bo3-wine/tools`.
- `ZMFORGE_WINE_PREFIX`: the Wine prefix `setup.sh` made. `zmforge build`
  defaults to a `wineprefix` folder beside the tools folder; `zmforge render`
  defaults to `docker/bo3-wine/wineprefix`. Both defaults are the same folder
  when the tools sit at `docker/bo3-wine/tools`, which is why that is the
  suggested place.
- `ZMFORGE_BO3_WINE`: the Wine image project, default `docker/bo3-wine`.

</details>

## One-time setup on Linux

Run these from the root of your zmforge checkout.

1. **Copy your mod tools folder** from your Steam install to
   `docker/bo3-wine/tools`. Git ignores that folder. A symlink to a copy
   elsewhere works too.
2. **Point zmforge at it:**
   `export ZMFORGE_WINE_TOOLS="$PWD/docker/bo3-wine/tools"`
3. **Write the setup file:**
   `cp docker/bo3-wine/bo3-wine.env.example docker/bo3-wine/bo3-wine.env`,
   then set `ZMFORGE_WINE_TOOLS=` in it to the same path.
4. **Build the Wine image and prefix:** `docker/bo3-wine/setup.sh`. It builds
   `bo3-wine:local`, creates the prefix, patches the ray tracer into a shim
   folder, and runs `check.sh`, which says in plain words what is missing.
5. **Build the render image:**
   `docker build -t zmforge-radiant-render:local docker/radiant-render`.
   `zmforge render` also builds it the first time if it is missing.
6. **Build the asset-database library:**
   `.venv/bin/python scripts/asset-setup.py --build-sqlite`. It downloads the
   SQLite source once and compiles it with `gcc` into
   `assets-cache/sqlite-wide/`. Without it, `zmforge render` still runs but
   cannot register the map's own textures, so custom props may draw black.
7. **Scan your tools for broken models:** `.venv/bin/python scripts/scan-local-tools.py`.
   It lists the models a GDT declares but whose files your copy lacks, so
   `zmforge verify` refuses them before the linker does. Rerun it after
   updating the tools.

<details><summary>Where to get the mod tools folder</summary>

- On Windows: `...\Steam\steamapps\common\Call of Duty Black Ops III 455130`.
  Copy the whole folder (about 28 GB) to the Linux machine, with `rsync`,
  `scp` or a USB drive.
- On Linux with Steam: install app 455130, then copy or symlink
  `~/.steam/steam/steamapps/common/Call of Duty Black Ops III 455130`. If you
  point `ZMFORGE_WINE_TOOLS` straight at a Steam folder, also set
  `ZMFORGE_WINE_PREFIX` to a folder outside `steamapps`.
- `docker/bo3-wine/SETUP.md` and `PATCHES.md` explain each setup step and the
  one patched file (your own `embree64r.dll`, written to a copy).

</details>

## Build, render and install

```sh
.venv/bin/zmforge generate zm_forge_gate --recipe three-room --tools-root "$ZMFORGE_WINE_TOOLS"
.venv/bin/zmforge build zm_forge_gate            # compile, bake, link
.venv/bin/zmforge render three-room --name zm_forge_gate
```

- `zmforge build` prints each stage's verdict and log path. A stage passes on
  the evidence in its log and outputs, never on its exit code: the linker
  never exits 0.
- `zmforge render` writes PNGs and a contact sheet under
  `build-out/render/<map>/`. It waits for free GPU memory rather than fall
  back to the CPU. A render runs alone: it holds the lock file
  `build-out/.radiant.lock` exclusively, so it waits for running builds and
  they wait for it.
- Builds of different maps can run side by side; see "Running builds side by
  side" below.
- **Custom props** (the `zmf_prop_*` models) are converted on Linux too, once
  before the first build and again after changing one:

  ```sh
  .venv/bin/zmforge props zm_forge_gate --out build-out/props-staging
  .venv/bin/python -m zmforge.props.install build-out/props-staging \
      --map zm_forge_gate --tools "$ZMFORGE_WINE_TOOLS"
  ```

  The second command writes the binary models, copies the models, collision
  boxes, images and asset files into the tools folder, and registers them in
  its asset database. It needs the SQLite library from setup step 6.
  Treyarch's `export2bin.exe` and `gdtdb.exe` are not used: the first writes
  broken files under Wine and the second does not run there.
- **Installing** means putting the built map where the game looks. The linker
  writes `usermaps/<map>/zone/` inside the mod tools folder; the game reads
  `usermaps/<map>/` inside its own folder (Steam app 311210). Copy the
  folder there, or on Windows make a junction:
  `mklink /J "<game>\usermaps\<map>" "<modtools>\usermaps\<map>"`.

<details><summary>Hooking each step into your own setup</summary>

Each step is a separate command, so you can run any of them wherever suits
you and move files between them yourself.

- **Generate anywhere.** `zmforge generate` is pure Python. Point
  `--tools-root` at the mod tools folder directly, or at an empty staging
  folder that mirrors its layout and copy that into the tools folder later.
  A recipe with priced wall guns reads one stock table,
  `share/raw/gamedata/weapons/zm/zm_levelcommon_weapons.csv`; copy it into
  the staging folder first.
- **Build on Linux, play on Windows.** Run `zmforge build` on Linux, then
  copy `usermaps/<map>/zone/*` and `share/raw/maps/zm/<map>.d3dbsp` and
  `<map>.led` to the Windows tools folder. Use any copy tool you already
  have.
- **Build on Windows.** Use the Mod Tools Launcher, or call the tools from
  your own script. `zmforge.toolchain` has the stage verdict rules
  (`Toolchain`, `LocalRunner`) if you want them from Python; driving it
  natively on Windows is untested.
- **Review.** `zmforge review` writes a packet any agent or person can
  answer; `scripts/review-with-claude.py` is one example runner. See
  `docs/workflows/review-a-map.md`.

</details>

<details><summary>What works on Windows natively</summary>

- `generate`, `check`, `requirements`, `paths` and `review` are pure Python
  and run anywhere.
- `zmforge build` and `zmforge render` need Docker, Wine and an X display and
  run on Linux only.
- Rendering on Windows without Wine is untested. Radiant runs there, but
  `zmforge render` drives it with Linux X tools (`xdotool`, `xwd`), so it
  would need a Windows port of that driver.

</details>

## Running builds side by side

`zmforge build` can run for several maps at once in separate shells. Each
build shares the mod tools copy and the Wine prefix with the others, so the
steps that write shared files wait for each other, and the lighting bake,
the heavy step, waits until the GPU has room for it. Nothing to set up: the
locks are files under `build-out/` (`$ZMFORGE_LOCK_DIR` moves them).

- **Safe side by side** (each map's own files): `usermaps/<map>/`,
  `map_source/zm/<map>.map`, `share/raw/maps/zm/<map>.*` and the bake itself.
- **One at a time** (files every map shares): the compile and the link.
  They write the conversion cache in `share/assetconvert` and read the
  collision files in `share/raw/collmaps`. The link with `--loading-screen`
  also points the stock `black` image in `gdtdb/gdt.db` at one map's picture
  for as long as it runs.
- **As many as fit**: bakes. A bake starts when free GPU memory covers its
  own reservation, every running bake's reservation, and a headroom left for
  the other programs on the GPU. RAM and CPU cores are checked the same way.
  With no `nvidia-smi` on the machine, one bake runs at a time.

<details><summary>The locks</summary>

- `build-out/.radiant.lock`: build steps hold it shared. Anything that holds
  it exclusively runs alone, so `flock build-out/.radiant.lock <command>`
  runs a command with nothing else building. Renders hold it exclusively.
- `build-out/locks/map-<map>.lock`: one build of a map at a time.
- `build-out/locks/tools.lock`: compile, link, and the loading-screen
  override around the link.
- `build-out/locks/heavy/*.json`: one file per running bake with its
  reservation. A file whose owner died is removed by the next bake that looks.
- `python -m zmforge.toolchain.buildlock status` shows who holds what;
  `python -m zmforge.toolchain.buildlock hold --map <map> --tools -- <cmd>`
  runs your own step under the same locks.

</details>

<details><summary>Tuning the bake gate</summary>

- `BAKE_VRAM_MB`, `BAKE_RAM_MB`, `BAKE_CORES`: what one bake reserves.
  The defaults are measured peaks plus a margin (see below).
- `ZMFORGE_GPU_HEADROOM_MB` (default 2048) and `ZMFORGE_RAM_HEADROOM_MB`
  (default 8192): what is always left free for other programs.
- Running bakes are counted at their full reservation even though part of
  it is already in use, so the gate errs towards starting fewer bakes.

The per-bake reservations were sized by sampling whole bakes of two of the
example maps (the X server plus Radiant): each default sits a margin above
what one bake was seen to use, so set them from your own bakes if your maps
are much larger.

</details>
