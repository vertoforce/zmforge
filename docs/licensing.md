# Licensing

zmforge is free for personal and non-commercial use, under the PolyForm
Noncommercial License 1.0.0 (`LICENSE`). It ships no Activision or Treyarch
file. It writes text files on your machine, and you build them with your own
licensed copy of the Black Ops III Mod Tools. Every file in this repository
that zmforge did not write is listed, with its source and licence, at the top
of `THIRD_PARTY.md`.

Nothing here is legal advice. The agreements quoted below are the binding
text; read them at their URLs.

## Why non-commercial

The mod tools agreement forbids commercial use of the tools and of the maps
made with them. A permissive licence on zmforge would invite uses the tools'
own terms forbid, so zmforge's licence matches them.

<details><summary>The mod tools EULA (Steam app 455130), quoted</summary>

Source: <https://store.steampowered.com/eula/455130_eula_0>, quoted from that page.

- Scope: "Activision grants you the non-exclusive, non-transferable, limited
  right and license to use the Program Utilities solely for your own personal,
  non-commercial use in order to create the New Game Materials."
- Commercial use: "you will not use or allow third parties to use the Program
  Utilities and/or the New Game Materials created by you for any commercial
  purposes, including, but not limited to, selling, renting, leasing,
  licensing, distributing, or otherwise transferring the ownership of the
  Program Utilities or the New Game Materials".
- Sharing maps: "If you decide to make available the use of the New Game
  Materials created by you to other gamers, you agree to do so solely without
  charge."
- Third-party content in maps: "New Game Materials must not contain any
  illegal, obscene or defamatory materials, materials that infringe rights of
  privacy and publicity of third parties or (without appropriate irrevocable
  licenses granted specifically for that purpose) any trademarks,
  copyright-protected works or other properties of third parties."
- Reverse engineering: "You agree not to reverse engineer the Program
  Utilities, Third Party Materials, or New Game Materials with the exception
  of Qt".
- Ownership of maps: "All New Game Materials created by you shall be
  exclusively owned by Activision as a derivative work [...] of the Program
  Utilities and Call of Duty: Black Ops III".

</details>

<details><summary>What these terms mean for zmforge</summary>

- zmforge is not a Program Utility and not a New Game Material: it contains no
  Activision file and no compiled map. It is an independent program that
  writes `.map`, `.gsc`, `.csc`, `.zone`, `.gdt` and `.csv` text.
- A map you build with it is a New Game Material: Activision owns it, and you
  may share it only free of charge. That is why this repository ships no
  built map, no navmesh, and no file the tools produced, only the generator
  and recipes that describe maps.
- zmforge's licence forbids commercial use, so it never licenses what the
  EULA forbids.
- The third-party content clause is why every model, photo and font zmforge
  puts into a map is CC0, public domain or OFL, with its record in
  `THIRD_PARTY.md`. The props step writes those credits into the map folder.

</details>

<details><summary>Steam Workshop (Steam Subscriber Agreement), quoted</summary>

Source: <https://store.steampowered.com/subscriber_agreement/>, quoted from
that page.

- "you represent and warrant that the Workshop Contribution was originally
  created by you". A map you generate and publish is your contribution; the
  CC0 and public-domain assets it carries are free to use without
  permission, and their credits travel with the map.
- The agreement also says you may not "reverse engineer, derive source code
  from, modify, disassemble, decompile, create derivative works based on [...]
  the Content and Services or any software accessed via Steam without the
  prior consent, in writing, of Valve". See the next section for the one
  place the optional Linux build touches a file of the tools.

No clause of either agreement names, or forbids, a separate program that
writes source files for the tools to compile.

</details>

## The optional Linux build and its Embree patch

Building on Windows with the Mod Tools Launcher touches no tool file. The
optional Linux build under Wine does, in one place, and only on your machine:

- **What it changes:** Radiant's lighting bake uses Intel's Embree library
  (`bin\avx\embree64r.dll`, and `bin\embree64r.dll`), which stops under
  Wine. zmforge writes a *copy* of that DLL with one imported function name
  changed (22 bytes, same file size, no code changed) into your Wine prefix,
  and mounts the copy at run time.
- **Your own copy only:** the patch runs on your machine, against the DLL in
  your own licensed mod tools install. Your install itself is not modified.
- **No tool bytes ship:** this repository contains no Activision, Treyarch or
  Intel file, patched or not. It ships the script that makes the change.
- **Embree is Apache-2.0:** the licence file the mod tools bundle,
  `modtools_license.txt`, has an `Embree` section that is the Apache License,
  Version 2.0 in full.
- **Steam's terms:** the Steam Subscriber Agreement restricts modifying
  software accessed via Steam without Valve's written consent (quoted above).
  Whether that reaches an Apache-licensed component patched in a private copy
  is not settled here. **Use the Linux build at your own discretion.** If you
  would rather not, build on Windows: nothing else in zmforge needs the patch.

<details><summary>The licence text and the full record</summary>

- From the `Embree` section of `modtools_license.txt` in the mod tools
  install (Apache License, Version 2.0, January 2004), clause 2: "each
  Contributor hereby grants to You a perpetual, worldwide, non-exclusive,
  no-charge, royalty-free, irrevocable copyright license to reproduce,
  prepare Derivative Works of, publicly display, publicly perform,
  sublicense, and distribute the Work and such Derivative Works in Source or
  Object form."
- The mod tools EULA forbids reverse engineering the Program Utilities and
  the Third Party Materials. The patch reads no code and changes no code; it
  renames one entry in the DLL's import table.
- The byte offsets, the before and after strings, and why Wine needs it are in
  `docker/bo3-wine/PATCHES.md`. The code is `docker/bo3-wine/scripts/patch-embree.py`
  and `zmforge.toolchain.wine.WineRunner.ensure_shims`.

</details>

## File formats zmforge writes

zmforge writes the tools' input formats from its own code. It learned them
from the tools' documentation, from community guides cited by link, and by
reading files the tools wrote for zmforge's own test maps.

<details><summary>The binary formats, and public precedent</summary>

- `props/xmodel_bin.py` writes `.XMODEL_BIN`, the tools' binary model format,
  so a prop converts without `export2bin.exe`. The layout was read off the
  tools' output for zmforge's own hay bale model. Public implementations of
  the same format exist: Scobalula's CallOfFile (MIT, public since 2022,
  <https://github.com/Scobalula/CallOfFile>) and OpenAssetTools'
  `XModelBinWriter` (GPL-3.0, <https://github.com/Laupetin/OpenAssetTools>).
  No code was taken from either.
- `props/lz4block.py` is a Python port of LZ4 r131's block compressor, so the
  output matches the tools byte for byte. LZ4 is BSD 2-Clause; its notice is
  in `THIRD_PARTY.md`.
- `verify/navmesh.py` reads the navmesh the tools build for your own map.
  No navmesh file ships here.

</details>

## Provenance

zmforge was written from a specification (`map-generator-spec.md`) distilled
from the findings of [hetri-courses/mcp-radiant](https://github.com/hetri-courses/mcp-radiant),
an earlier MCP server for authoring Black Ops III zombies maps with Claude,
together with the mod tools' documentation and the stock scripts' interfaces.
That repository carries no licence, so none of its code is used: the
specification carries facts and interfaces only and was reviewed for copied
expression before any code was written, and the implementation was written
from the specification alone.
[`ACKNOWLEDGEMENTS.md`](../ACKNOWLEDGEMENTS.md) credits it.

<details><summary>What the code contains from the game, and why that is allowed</summary>

- Asset names, entity keys, script function names and `file:line` pointers
  into the stock scripts: identifiers and references a map cannot work
  without. Names and facts are not copyrightable expression
  (17 U.S.C. 102(b): "In no case does copyright protection [...] extend to
  any idea, procedure, process, system, method of operation").
- Measured data tables (`props/stock_origins.json`, `props/stock_collmaps.json`,
  `blueprint/installed_assets.json`, `tests/corpus/shipped-solid-shapes.json`):
  names, counts and a few coordinates per model, measured from the mod tools
  install. No model, texture or script can be rebuilt from them.
- Format templates (`texture/templates/*.gdt.tmpl`): the key list of a
  material, image or HUD image entry. The keys and their default values come
  from the mod tools' own schema files (`deffiles/material.awi`,
  `deffiles/image.awi`), which define the format; the linker rejects an entry
  without them. That is the format, not copied content.
- `tests/logs/*.log`: the tools' console output when building zmforge's own
  test maps, kept as parser fixtures. Status lines about our maps, no game
  content.
- Stock script code: none. The emitted scripts call the stock functions by
  name; no stock script block is copied.
- Decompiles, read for reference only: some `file:line` citations in code
  comments and the reference docs point into a public community decompile of
  the shipped game scripts (`github.com/ate47/bo3-source`) or of the shipped
  HUD Lua (`ZMPerksContainerFactory.lua`, T7LuaRepo dumps), because the mod
  tools ship some scripts only as stubs and the HUD Lua not at all. Where the
  mod tools ship the script in `share/raw/scripts`, the same function is there
  under the same name. No decompiled code is in this repository; only
  function, field and key names (identifiers) are used.

</details>
