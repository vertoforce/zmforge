# Third-party material and notices

zmforge's own code and docs are under the PolyForm Noncommercial License
1.0.0 (`LICENSE`). Everything else keeps its own licence. This file lists
every source and data file in the repository that is not entirely zmforge's own work, and
everything zmforge downloads or reads at build time.

- **No game file is in this repository.** No Activision or Treyarch model,
  texture, script, table, map source, compiled map or document. zmforge reads
  what it needs from your own mod tools install at build time.
- **No third-party model, texture, photo or font is committed.** Downloads go
  to `assets-cache/`, which git ignores. The repository keeps only the record
  of where each came from and under what licence.

## Files that are not entirely ours, with the licence evidence

| File | What it is | Source and licence | Why shipping it is allowed |
|---|---|---|---|
| `src/zmforge/props/lz4block.py` | Python port of LZ4 r131's block compressor | LZ4 by Yann Collet, BSD 2-Clause: header of `lib/lz4.c` at tag r131, <https://github.com/lz4/lz4/blob/r131/lib/lz4.c> | BSD 2-Clause allows modified source redistribution with the notice kept. The notice is below. |
| `src/zmforge/props/library.py` | Download records for the CC0 prop kits and textures, with each licence sentence quoted | Kenney (`License.txt` in each archive: CC0 1.0), Poly Haven (<https://polyhaven.com/license>: CC0), ambientCG (<https://docs.ambientcg.com/license/>: CC0 1.0) | Records and quoted licence notices only. No asset bytes. |
| `assets-cache/fonts/FONTS.json` | Records of the fonts the painters use | Anton, Oswald and the PT faces: SIL OFL 1.1 (<https://github.com/google/fonts/tree/main/ofl>); Liberation, URW base35, DejaVu: read from Debian packages in place | Records only. No font file is committed. |
| `src/zmforge/props/stock_origins.json` | Root bone position, axes and two box corners per stock model (about 1,800 models) | Measured from the mod tools install | Facts about the models, a few numbers each. No model can be rebuilt from them. 17 U.S.C. 102(b), see `docs/licensing.md`. |
| `src/zmforge/fonts.py` | Download records for the PT Sans, PT Sans Narrow, PT Serif and PT Mono faces the painters fetch on first use when no OS font fits, each with its `OFL.txt` | ParaType, SIL OFL 1.1, from Google Fonts (<https://github.com/google/fonts/tree/main/ofl>); recorded in `assets-cache/fonts/FONTS.json` | Records only. The font files are downloaded into the font cache on first use; none is committed. |
| `src/zmforge/props/notes.json` | Our notes on how stock models and materials render and read in a map, keyed by stock model and material name | zmforge's own observations; the keys are stock asset names | Our text; identifiers only. |
| `src/zmforge/props/stock_collmaps.json` | 171 stock model names | Listed from the mod tools install | Names (identifiers) only. |
| `src/zmforge/blueprint/installed_assets.json` | Stock asset names grouped by what a map can use them for | Listed from the mod tools install | Names (identifiers) only. |
| `tests/corpus/shipped-solid-shapes.json` | Counts of each brush and patch block shape across the stock map sources | Counted from the mod tools install | Counts of syntax shapes. No brush, map or text is copied. |
| `src/zmforge/texture/templates/*.gdt.tmpl` | The key list of a material, image and HUD image entry, with default values | The keys and defaults come from the mod tools' schema files (`deffiles/material.awi`, `deffiles/image.awi`) that define the asset format | The format, not copied content; the linker rejects an entry without them. |
| `src/zmforge/emit/strings.py`, `src/zmforge/emit/sound.py` | The `.str` file header (`VERSION`, `CONFIG`, `FILENOTES`) and the sound alias CSV header row | The tools' file formats; the `.str` header as StringEd writes it | Three-line format header and a column list, required by the tools. |
| `src/zmforge/script/symbols.py` and other `src/` files | Stock script function names, signatures and `file:line` pointers | The stock scripts' interfaces, read in `share/raw/scripts` and, where that ships only a stub, in a public community decompile (`github.com/ate47/bo3-source`) read for reference | Identifiers and references. No stock script block is copied (checked by shingle overlap, see `docs/licensing.md`). |
| `tests/logs/*.log` | Console output of the mod tools building zmforge's own test maps | Tool status messages about our maps | Parser fixtures; no game content. |
| `docs/images/*-plan.png` | README pictures: the loading-screen plans of the two maps the README shows (Cemetery Quest and Harvest Moon) | Drawn by zmforge's own plan renderer (`emit/planview.py`, `render/presentation.py`) from each map's blueprint: flat shapes, a grid and the title. No game texture, model or screenshot is in them. The title is set in Liberation Sans (GPL-2.0 with font exception; rendered text is not the font software) | Our own drawing; downscaled to 1024 px with no metadata. |
| `docs/licensing.md` | Short quotes of the mod tools EULA, the Steam Subscriber Agreement and US statute | <https://store.steampowered.com/eula/455130_eula_0>, <https://store.steampowered.com/subscriber_agreement/>, 17 U.S.C. 102(b) | Short quotation for commentary on the terms; US statute carries no copyright. |
| `docker/bo3-wine/` | Our scripts to run the mod tools under Wine | Ours. Builds from Debian and WineHQ packages at image build time; no image or tool file is committed | `PATCHES.md` records the one change it makes to a copy of the tools' Embree DLL (Apache-2.0) on your machine. |

Not in the repository, on purpose: the navmesh, `.ff` and other files the
tools compile (Activision owns compiled maps, see `docs/licensing.md`), any
stock file, any community map or prefab, and the mod tools' documentation.

<details><summary>LZ4 notice (BSD 2-Clause), for props/lz4block.py</summary>

```
LZ4 - Fast LZ compression algorithm
Copyright (C) 2011-2015, Yann Collet.

BSD 2-Clause License (http://www.opensource.org/licenses/bsd-license.php)

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

    * Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above
copyright notice, this list of conditions and the following disclaimer
in the documentation and/or other materials provided with the
distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

</details>

<details><summary>Black Ops III mod tools terms (Steam app 455130)</summary>

- The mod tools licence is personal and non-commercial.
- Maps you build may be shared only free of charge.
- Activision owns maps made with the tools, as derivative works.
- zmforge ships no Activision material and compiles nothing on a server. It
  generates text files on your machine that you then build with your own
  licensed copy of the tools.
- The relevant clauses, quoted: `docs/licensing.md`. The agreements
  themselves are the binding text:
  <https://store.steampowered.com/eula/455130_eula_0>.

</details>

<details><summary>Prop kits: Kenney, CC0 1.0</summary>

- Source: <https://kenney.nl/assets>. Licence: CC0 1.0,
  <http://creativecommons.org/publicdomain/zero/1.0/>.
- `src/zmforge/props/library.py` records each kit's page, download URL and
  licence text. `zmforge props` downloads them into `assets-cache/`.
- `zmforge props` writes `PROP-CREDITS.md` from that record into its output,
  so the credits can travel with a published map.

</details>

<details><summary>Photoscans and textures on props: Poly Haven and ambientCG, CC0 1.0</summary>

- Poly Haven models (<https://polyhaven.com/license>, CC0): `dead_tree_trunk`
  by Rob Tuytel (`zmf_prop_dead_log`), `tree_stump_01` by Rob Tuytel
  (`zmf_prop_tree_stump`), `wooden_crate_02` by James Ray Cock and Jurita
  Burger (`zmf_prop_wooden_crate`). Their 1k glTF files and colour maps are
  downloaded into `assets-cache/downloads/polyhaven_*/`.
- ambientCG `ThatchedRoof001A` (<https://ambientcg.com/view?id=ThatchedRoof001A>,
  CC0 1.0, <https://docs.ambientcg.com/license/>): the straw photo on the
  generated hay bales. Downloaded into `assets-cache/downloads/`.
- ambientCG `Leaf001` (<https://ambientcg.com/view?id=Leaf001>, CC0 1.0,
  <https://docs.ambientcg.com/license/>): the leaf photo on the generated corn
  stalks (`zmf_prop_corn_stalk`, `_thin`), cropped to its opaque middle and
  colour-graded olive to straw. Downloaded into `assets-cache/downloads/`.
- ambientCG `Bark012` (<https://ambientcg.com/view?id=Bark012>, CC0 1.0,
  <https://docs.ambientcg.com/license/>): the bark photo on the generated dead
  trees (`zmf_prop_dead_tree_a`, `_b`, `_c`), graded to weathered grey-brown.
  Downloaded into `assets-cache/downloads/`.
- `src/zmforge/props/library.py` (`KITS`, `TEXTURES`) records each page,
  download URL, author and the licence sentence, and `PROP-CREDITS.md` carries
  them with a built map.

</details>

<details><summary>Fonts: SIL Open Font License 1.1</summary>

- Anton and Oswald, both under the SIL Open Font License 1.1, recorded in
  `assets-cache/fonts/FONTS.json`. They are downloaded, not bundled.
- `scripts/asset-setup.py --fetch-fonts` downloads each font together with its
  `OFL.txt`. Keep that file next to the font if you redistribute it.
- PT Sans, PT Sans Narrow, PT Serif and PT Mono (ParaType, SIL OFL 1.1) are the
  fallback faces `src/zmforge/fonts.py` downloads on first use, with their
  `OFL.txt`, when no OS font fits a job. Also recorded in `FONTS.json`.
- The poster painter also reads three OS font packages in place: Liberation
  (GPL-2 with a font exception), URW base35 (AGPL-3 with a font exception)
  and DejaVu (Bitstream Vera licence). No font file is in this repository.

</details>

<details><summary>Python dependencies</summary>

Installed by pip from PyPI, never vendored into this repository.

| Needed for | Package | Licence |
|---|---|---|
| everything (core) | numpy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 (package metadata) |
| everything (core) | pillow | MIT-CMU (HPND) |
| everything (core) | scipy | BSD-3-Clause (package classifier: BSD) |
| `dev` extra: tests | pytest | MIT |
| `dev` and `props` extras: tests, photoscan props | fast-simplification | MIT |
| optional speed-up, if installed | lz4 (python-lz4) | BSD (package classifier) |

Their own dependencies carry MIT, BSD, Apache-2.0 or ISC licences.

</details>

<details><summary>Community knowledge</summary>

- The docs cite community wikis (UGX-Mods, the archived AviaCreations wiki),
  forum threads and video tutorials by link, in our own words. No page or post
  is reproduced.
- No other author's map, prefab or asset pack is included.

</details>
