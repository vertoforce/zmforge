# BO3 mod-tools source formats — verified ground truth

Reference for programmatically generating Call of Duty: Black Ops III
(T7) custom-zombies map source.

`how-zombies-maps-work.md` is the mechanism account: what the engine and the
stock scripts do with the data these formats carry. This page is the formats
themselves, with the evidence behind each rule.

**Every rule below carries a source URL, plus either a real file snippet
or a statement of what that source says.** Anything that could not be confirmed
against a real file or real tool output is in [§5 Unverified / folklore](#5-unverified--folklore),
not in the rule sections.

## Source tiers used

| Tier | What | Why it counts |
|---|---|---|
| A | Real BO3 `.map` / `.gdt` / `.zone` / `.gsc` files in public repos | These are files Radiant / gdtdb / linker actually produced or consumed |
| A | `t7.def.json` — BO3 Radiant's own entity-definition file | Shipped with the mod tools (copy mirrored in a Radiant mod repo) |
| A | Treyarch's mod-tools **raw** `zm_usermap.gsc` + decompiled stock `scripts/zm/*.gsc` | The code that performs the entity lookups |
| B | Official **CoD4 / World at War** mod-tools releases (same `iwmap 4` text format, earlier engine) | Used only where BO3 files did not exercise a feature; always flagged |
| C | UGX-Mods community wiki, Modme forum mirror | Community docs; flagged as such |

Sources quoted most:

- `https://raw.githubusercontent.com/MattFiler/zm_alien_isolation/master/map_source/zm/zm_alien_isolation.map` (2.2 MB, released BO3 zombies usermap)
- `https://github.com/JKClaytonDev/zm/blob/main/zm_giant.map` (BO3 zm map, contains `curve` patches)
- `https://github.com/opeexcuuseme/prep/blob/main/tunnels_original.map` (BO3, 38 `curve` blocks)
- `https://github.com/FugXBL/bo3triggertest/blob/main/map_source/mp/mp_triggertest.map` (BO3, decal faces)
- `https://github.com/UGX-Mods/community-wiki/blob/main/attachments/modding/bo3/dog-spawners/dog_spawner.map` and `.../pandoras-box/box_start.map` (BO3 prefabs lifted from stock The Giant)
- `https://github.com/gamedev44/Radiant-/blob/main/Radiant%2B%2B%20Editor%20Improvements%20Mod/vkRadiant%20(Standard)/bin/t7.def.json`
- `https://raw.githubusercontent.com/marcogravbrot/bo3-mod-tools/master/raw_scripts/zm/zm_usermap.gsc`
- `https://github.com/ate47/bo3-source` (decompiled stock `scripts/zm/*.gsc`)

---

# 1. The Radiant `.map` source format (`iwmap 4`)

## 1.1 File header and layer table

A `.map` starts with the literal line `iwmap 4`, then optional
editor-state lines, then `// entity N` blocks. The first 4 lines zmforge
writes (`zm_fmtdemo.map`, three-room recipe):

```
iwmap 4
"script_startingnumber" 0
"000_Global" flags expanded active
"The Map" flags expanded
```

A released BO3 zombies map
(`https://raw.githubusercontent.com/MattFiler/zm_alien_isolation/master/map_source/zm/zm_alien_isolation.map`)
opens the same way, with two more layer lines (`"000_Global/No Comp"` with
`hidden ignore`, and `"000_Global/buyable"` with no flags), a doubled space
before `active`, and trailing spaces after some lines.

Rules confirmed across every BO3 `.map` examined:

- `iwmap 4` is the whole header. No version number follows, no braces.
- `"script_startingnumber" 0` is a quoted key with an **unquoted** value —
  the only place in the file where that happens.
- Each following quoted string is a **layer** declaration: `"<path>" flags <flag words>`.
  Observed flag words: `expanded`, `active`, `hidden`, `ignore`, `prefab`.
  Layer paths use `/` as a separator. Layers are optional; the CoD4/WaW
  official prefabs ship with only `"000_Global" flags  active` and
  `"The Map" flags ` (e.g. `https://github.com/promod/CoD4-Mod-Tools/blob/master/map_source/prefabs/bog/rubble/cinderblock_01_weaponclip.map`).
- An entity opts into a layer with a `layer "<path>"` line inside its
  brace block (entity 1 of the alien-isolation map files its zombie
  spawner under `"000_Global/No Comp"` this way). zmforge's output:
  ```
  // entity 1
  {
  guid "{D933A463-5BB8-4FCC-91B3-D4362CA7091A}"
  layer "The Map"
  "classname" "info_volume"
  ```
  Note `guid` and `layer` are written **unquoted-key / quoted-value**, and
  they come before the KVPs.

`"_prefabs/..." flags prefab` layer lines also exist, and some generators
emit them. They do not appear in any public BO3 `.map`
examined; see [§5](#5-unverified--folklore).

## 1.2 Entity blocks and key/values

```
// entity 1
{
guid "{D933A463-5BB8-4FCC-91B3-D4362CA7091A}"
layer "The Map"
"classname" "info_volume"
"targetname" "start"
"script_noteworthy" "player_volume"
"target" "start_spawners"
// brush 0
{
 guid "{68D62EAA-6362-4AA9-A332-67FA9F78EA18}"
 contents detail;
 ( -512 -256 0 ) ( -512 256 256 ) ( -512 -256 256 ) caulk 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
 ...
}
}
```
(zmforge output: `zmforge generate zm_fmtdemo --recipe three-room`, the
start zone's `info_volume`. The same shape, a zone `info_volume` carrying
`script_noteworthy player_volume` and a `target` naming its spawners, is
entity 402 of `zm_alien_isolation.map`.)

- Entities are preceded by a `// entity N` comment, N counting from 0 in
  file order, and wrapped in `{ … }` at column 0.
- `guid "{UUID}"` is the first line of every BO3 entity and every BO3
  brush. Format is an upper-case braced UUID. CoD4/WaW files have **no**
  guid line at all, so the guid is a BO3-era addition.
- KVPs are `"key" "value"`, one per line, no indentation, both sides
  always double-quoted. Numeric and vector values are quoted strings
  (`"origin" "546 588 0"`, `"angles" "0 196 0"`, `"zombie_cost" "950"`).
- `"classname"` is conventionally first after `guid`. Radiant then writes
  the rest roughly alphabetically but not strictly (`_color` and
  `spawnflags` routinely appear out of order) — order is not load-bearing.
- Brushes belonging to an entity are nested inside the entity's braces,
  each preceded by `// brush N` numbered **per entity**, starting at 0.
- `worldspawn` is entity 0 and owns all unowned brushes.

worldspawn as zmforge writes it (same generated map; the `state_alias_2..4`
lines that follow are trimmed). Entity 0 of `zm_alien_isolation.map` carries
the same keys plus `"lodbias" "default"`; values such as `lightingquality`,
`lutmaterial` and `numOmniShadowSlices` differ per map:

```
"classname" "worldspawn"
"lightingquality" "1024"
"samplescale" "1"
"skyboxmodel" "skybox_default_day"
"ssi" "default_day"
"wsi" "default_day"
"fsi" "default"
"gravity" "800"
"lutmaterial" "luts_t7_default"
"numOmniShadowSlices" "96"
"numSpotShadowSlices" "64"
"sky_intensity_factor0" "1"
"sky_intensity_factor1" "1"
"state_alias_1" "State 1"
```

## 1.3 Brush plane triples and winding direction — MEASURED

A brush is a set of half-space planes; each line is three points then the
texture block (a face line from zmforge's `zm_fmtdemo.map`):

```
 ( -512 -256 0 ) ( -512 256 256 ) ( -512 -256 256 ) caulk 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
```

**Winding: `n = (B − A) × (C − A)` points INTO the solid.**

This is not folklore and it is not inferred — it was measured.
The first 25 plain brushes of `zm_alien_isolation.map` were parsed, the
half-space set built under each sign convention, and all plane triples
brute-force intersected:

```
INWARD (n=(B-A)x(C-A) points into solid) -> nonempty solids: 25 /25
OUTWARD                                  -> nonempty solids: 0 /25
```

Worked example from brush 0 of that map (a 1-unit floor slab):
face `( -1536 -1792 -1 ) ( 768 -1792 -1 ) ( 768 768 -1 )` lies on z = −1 and
its cross product is `(0, 0, +5898240)` → +Z; face
`( -1537 768 0 ) ( 767 768 0 ) ( 767 -1792 0 )` lies on z = 0 and gives −Z.
The solid is the slab between them, so both normals point inward.

This is the opposite of the Quake/Q3 convention, where the three points
are wound so the plane normal faces out of the brush.

**An inward face table is correct.** Running a face table that winds all six
sides of a box inward through the same intersection test produces a closed
8-vertex solid. Treyarch's brush format winds faces **inward**, so the cross product
`(B - A) x (C - A)` over the three face points aims into the solid rather
than out of it. The measurement agrees.

Other facts about the plane triple, from real files:

- The three points need **not** be corners of the final brush and need not
  be axis-aligned or integral: `( 557 1305.75 569 ) ( 559.5 1296.25 0 ) ( 1619.5 -1315.25 0 )`
  from the `info_volume` above. They only have to be three non-collinear
  points on the plane, in the right winding order.
- Numbers are written plainly (`-1536`, `71.964066`, `2.4000502`); no
  exponent notation appears in any file examined.
- Faces are separated by newlines; the leading space before `(` is
  Radiant's style, and CoD4/WaW official prefabs use the same single
  leading space.

## 1.4 Texture fields: order and meaning

Layout of the tail of a face line, counted off real files:

```
<render_material> n1 n2 n3 n4 n5 n6 <lightmap_material> m1 m2 m3 m4 m5 m6 [smoothing <name>] [decalLayerSort "<name>" decalEditorSort <int>]
```

Six numbers, then the lightmap material (always `lightmap_gray` in every
BO3 and CoD4/WaW file examined), then six more numbers for the lightmap
projection, then optional trailing tokens.

Field-by-field, with the evidence available:

| Field | Meaning | Evidence |
|---|---|---|
| n1, n2 | horizontal / vertical texture size in world units (the distance one texture repeat spans). Negative = mirrored on that axis. | Real values are size-like, not scale-like: `64 64`, `128 128`, `16 16`, `32 32`, `15.36 10.24` (`t7_cloth_cargo_netting_01_green_no_cull`), and `0.5 0.5` on a tiny decal face in `mp_triggertest.map`. Negative form `seelow_wall_wood_old02 128 -128 -39 46 0 0` in the official WaW tools (`https://github.com/CallOfDutyModding/call_of_duty_world_at_war_mod_tools/blob/main/map_source/_prefabs/windows/wood/see1_barn_curve01.map`). **Partially verified**: no primary doc names the field. |
| n3, n4 | horizontal / vertical shift, in world units, **subtracted** before the divide (see the formula below) | Measured, not inferred, two ways. `ayz_floor 16 16 -35 0 0 0` vs the same material at `16 16 0 0 0 0` elsewhere in the same brush; `me_cinderblock_wall2 128 128 10 0 0 0` vs `128 128 14 8 0 0` on adjacent faces of one prefab (CoD4 tools). UGX/zeroy wiki describes the Surface Inspector control as the number of units the texture moves across the face (`https://wiki.zeroy.com/index.php?title=Call_of_Duty_5%3A_Texturing`). |
| n5 | rotation in degrees | Official WaW prefab `see1_barn_curve01.map` carries `128 128 45 -46 180 0`, `128 128 -2 -1 -90 0`, `128 -128 8 1 90 0` — exactly the 0/90/−90/180 values a rotate control produces. the zeroy wiki describes the control as rotating the texture by the number of degrees entered beside it. |
| n6 | **unknown.** Zero in every axis-aligned face. Tiny non-integers (`0.00030217317`, `-0.0099198651`) only on faces of skewed/rotated brushes. | Observed only; see [§5](#5-unverified--folklore). |
| m1..m6 | same six fields for the lightmap projection. Defaults `16384 16384 0 0 0 0`. | Universal across BO3, CoD4 and WaW files. |

**Where the image actually lands [measured].** A vertex's
texture coordinate is `u = (P . U - n3) / n1` and `v = (P . V - n4) / n2`,
with the axes taken from the face's normal — `U, V = +Y, -Z` for a face on
the X axis, `+X, -Z` on the Y axis, `+X, -Y` on the Z axis — and the sign of
the normal does not change them, so the two walls of a pair share an axis and
a picture on one of them comes out mirrored unless `n1` is written negative.
Two independent measurements agree: probe maps compiled with
`cod2map64.exe`, reading the coordinates back out of the vertex lump of the
`.d3dbsp` (lump id 10, 68-byte stride, `u` and `v` at floats 7 and 8); and
643 pairs of translated-but-identical brushes across four BO3 map sources
(not distributed with this project), where the shift moves by exactly the world translation along
that axis and never by anything involving the image's pixel size. So the
projection is anchored to the **world**, not to the face: a face that does not
start a whole number of images from the world origin shows a seam inside
itself at `0 0`, as all 43 picture faces of one measured map did. To put one image on one face, write the face's
own extent as the size and the world coordinate of the image's top-left corner
as the shift — for a south-looking wall, `x_min` and `-z_max`.

**Practical generator rule (safe, evidence-backed):** emit
`<material> 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0`. That exact
string is what Radiant writes for an untouched face, and it appears
thousands of times across the BO3, CoD4 and WaW corpora, so it is the right
default for a generator to write.

**Optional per-face trailing tokens (real, BO3 and WaW):**

- `smoothing smoothing_smooth_other` — WaW/CoD4 official tools, e.g.
  `... me_cinderblock_wall2 128 128 14 8 0 0 lightmap_gray 16384 16384 0 0 0 0 smoothing smoothing_smooth_other`
  (`https://github.com/promod/CoD4-Mod-Tools/blob/master/map_source/prefabs/bog/rubble/cinderblock_01_weaponclip.map`).
  It does not appear in any BO3 file examined.
- `decalLayerSort "<layer>" decalEditorSort <int>` — BO3, per face:
  ```
  ( 528.45386 1158.8495 6 ) ( 341.53375 1158.8495 6 ) ( 341.53375 994.8175 6 ) color_blue 0.5 0.5 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0 decalLayerSort "Asphalt (bottom)" decalEditorSort -1
  ```
  (`https://github.com/FugXBL/bo3triggertest/blob/main/map_source/mp/mp_triggertest.map`, brush 14.)

## 1.5 `contents` flags

`contents <tokens>;` is an optional single line **inside** a brush block
(after `guid`, before the faces) or inside a patch block (after the
primitive's opening brace). It is absent on ordinary solid geometry.

Verified token spellings, each with a real file:

| Token | Source |
|---|---|
| `detail` | `contents detail;` — `zm_alien_isolation.map` brush of entity 402; also `contents detail;` in `promod/CoD4-Mod-Tools .../zipline/awning_02.map` |
| `nonColliding` | `contents nonColliding;` — `zm_alien_isolation.map` brush 659 (a chalk-outline mesh); `tunnels_original.map`; official WaW `see1_barn_curve01.map` |
| `umbraTarget` | `contents umbraTarget;` — `https://github.com/opeexcuuseme/prep/blob/main/tunnels_original.map` (3 occurrences) |
| `weaponClip` | `contents weaponClip;` — 19,553 occurrences, every one on a `contents` line, across the 733 shipped `.map` files under `<tools>/map_source` **[measured]**; also official CoD4 tools, `cinderblock_01_weaponclip.map`. GitHub code search over *public* `.map` files still returns nothing, which says what mappers publish, not what the token is. |
| `ai_nosight` | `contents weaponClip detail ai_nosight;` — 7,044 occurrences in the same 733 files **[measured]**. Same note about public `.map` files. |
| `triangulatedWeaponClip` | `contents triangulatedWeaponClip;` — 40 occurrences in the same files **[measured]**. Not emitted by this package; recorded so a reader does not think the spelling is a typo. |

**What "the shipped `.map` files" means here, once.** The mod tools' own
`map_source` tree: `_prefabs` (718), `_prefabs_maya` (12), `mp` (2) and
`zm_giant.map`, 733 files in the tools version counted, excluding any
generated maps written into the same tree. The count varies by tools version by
a few files. That does not move any count in this document by more than a
rounding, and every figure quoted as "the 733 shipped files" was taken in one
pass. Elsewhere in this repo the same tree is called "about 730 files".

Case matters in the spellings above (`nonColliding`, `weaponClip`,
`umbraTarget` are camelCase; `detail` is lower-case). Multiple tokens are
space-separated on one line and the line ends in `;`.

Corroboration for the underlying flag vocabulary (engine bit names, CoD4,
reverse-engineered — Tier B/C):
`https://github.com/callofduty4x/CoD4x_Server/blob/master/src/game/surfaceflags.h`

```
#define CONTENTS_NONCOLLIDING   4           //Never used
#define CONTENTS_AI_NOSIGHT     0x1000  // AI cannot see through this
#define CONTENTS_CLIPSHOT       0x2000  // stops bullets
#define CONTENTS_DETAIL         0x8000000   // brushes not used for the bsp - don't include in structural bsp
#define CONTENTS_STRUCTURAL     0x10000000  // brushes used for the bsp
```

`ai_nosight` as a **`.map` text token** is verified: 7,044
occurrences on `contents` lines in the shipped `map_source` tree. The token
table above holds the count; §5 records how the entry was settled.

## 1.6 Patch / mesh primitives (`curve` and `mesh`)

BO3 has two patch primitives, both written inside an ordinary
`// brush N { … }` container, with the primitive keyword replacing the
face list.

**A `mesh`**, as zmforge's writer emits it (`zmforge.mapsource.writer`,
a 2x2 grid built for this doc). Brush 659 of `zm_alien_isolation.map` has
the same layout: a `contents nonColliding;` line, a bare `toolFlags;`, and
dimension line `2 2 0 8`.

```
// brush 0
 {
  guid "{00000000-0000-4000-8000-000000000001}"
  mesh
  {
  contents nonColliding;
  toolFlags;
   caulk
   lightmap_gray
   2 2 0 8
   (
	v 0 128 32 t 0 0 0 0
	v 0 128 96 t 0 -1024 0 0.5
   )
   (
	v 0 136 32 t 1024 0 0.5 0
	v 0 136 96 t 1024 -1024 0.5 0.5
   )
  }
 }
```

**A `curve`**, same writer, wrapped in the `func_group` entity with
`"type" "patchCapped"` that released maps put patches in (entity 211 of
`https://github.com/JKClaytonDev/zm/blob/main/zm_giant.map` is one; its
grid is `9 3 16 1`). GUIDs elided:

```
// entity 7
{
guid "{<guid>}"
"classname" "func_group"
"type" "patchCapped"
// brush 0
 {
  guid "{<guid>}"
  curve
  {
  toolFlags;
   caulk
   lightmap_gray
   3 3 16 1
   (
	v 0 128 32 t 0 0 0 0
	v 0 128 96 t 0 -1024 0 0.5
	v 0 128 160 t 0 -2048 0 1
   )
   (
	v 0 136 32 t 1024 0 0.5 0
	v 0 136 96 t 1024 -1024 0.5 0.5
	v 0 136 160 t 1024 -2048 0.5 1
   )
   (
	v 0 144 32 t 2048 0 1 0
	v 0 144 96 t 2048 -1024 1 0.5
	v 0 144 160 t 2048 -2048 1 1
   )
  }
 }
}
```

Structure rules, confirmed against the two released maps named above plus
38 more `curve` blocks in `tunnels_original.map`:

1. Brush container: `// brush N`, then ` {`, then ` guid "{…}"`, then the
   primitive keyword (`mesh` or `curve`) on its own line, then an inner
   `{ … }`. **Nothing else precedes the keyword.** Measured over the mod
   tools' own `map_source` (the shipped files, 22,795 patch
   containers): every one has exactly `guid` between
   the container brace and the keyword. A `layer` line there is read by
   `cod2map64` as the start of a face brush and stops the compile:
   `ERROR: File ...\<map>.map, line 3989: MatchToken: got 'mesh',
   expected '('`.
2. Inner block order: optional `layer "<path>"` (column 0), then optional
   `contents …;`, then `toolFlags;`, then the render material, then the
   lightmap material, then the dimension line, then the control-point rows.
   The layer line is where Radiant records a patch's layer membership: 328
   layered patches in the shipped files, all with `layer` as the first inner
   line, none anywhere else (brush 0 of
   `_prefabs\zm\zm_giant\geo\zm_giant_warehouse_bridge_ramp.map` is one).
   The same layout from zmforge's writer, for a layered patch built for this
   doc, GUID elided:

   ```
   // brush 0
    {
     guid "{<guid>}"
     mesh
     {
   layer "The Map/terrain"
     contents detail;
     toolFlags;
      caulk
      lightmap_gray
      2 2 16 8
      (
   	v 0 128 32 t 0 0 0 0
   	v 0 128 96 t 0 -1024 0 0.5
      )
      (
   	v 0 136 32 t 1024 0 0.5 0
   	v 0 136 96 t 1024 -1024 0.5 0.5
      )
     }
    }
   ```

   The shape ledger those counts come from is
   `tests/corpus/shipped-solid-shapes.json` (regenerated from a tools
   install).
3. `toolFlags;` with no value is what BO3 writes. It can carry a value:
   the official WaW tools write `toolFlags splitGeo;`
   (`see1_barn_curve01.map`). Every BO3 patch examined has a bare
   `toolFlags;` — 38/38 in `tunnels_original.map`, 2/2 in `zm_giant.map`,
   1/1 in `zm_alien_isolation.map`.
4. Dimension line is four integers: `W H T1 T2`, indented 3 spaces.
   Observed real values: `2 2 0 8` (mesh), `9 3 16 1` (curve),
   `3 3 16 8` (curve, ×38), `7 3 16 1` (WaW curve), `5 3 16 6`
   (a generator's fixture). `W` = number of control-point rows, `H` =
   control points per row — verified by counting: the `9 3 16 1` block
   contains 9 parenthesised rows of 3 `v` lines each.
5. Each row is `   (` / one `v` line per control point (tab-indented) /
   `   )`.
6. Vertex line: `v X Y Z t U V Lu Lv` — position, literal `t`, then two
   texture UVs and two lightmap UVs. The UVs are large world-projected
   numbers (`t 0 -1264 1 23`); the lightmap pair is small.
7. `curve` is Bezier-interpolated, `mesh` is flat-triangulated. In the
   corpus, `T1` is `0` on the one real `mesh` in it and `16` on every
   real `curve` — consistent with T1 being the curve subdivision count,
   but that mapping is inference from 41 samples, not documentation.
8. A capped patch is grouped into a `func_group` entity carrying
   `"type" "patchCapped"` (real, `zm_giant.map`, both occurrences).

**Not confirmed in any public file:** the optional per-vertex colour
(`v X Y Z c R G B A t …`) and the block-trailing `decalLayerSort` /
`decalEditorSort` inside a patch body. See [§5](#5-unverified--folklore).

---

# 2. The `.gdt` asset database format

## 2.1 File syntax

There is **no header, no version line, no magic**. The whole file is one
anonymous brace block. The smallest valid `.gdt` is an empty pair of
braces on two lines; MattFiler's
`https://raw.githubusercontent.com/MattFiler/zm_alien_isolation/master/archetypes/alien_isolation_archetypes.gdt`
is exactly that.

Byte layout: `{` at column 0, each entity header indented one tab, its
properties two tabs, LF endings. Stock Treyarch GDTs have this layout;
checked with a hexdump and `cat -A` of `sharedweaponsounds.gdt` from
`https://github.com/shidouri/T7-GDT-Backup` (a repository whose README
says it holds Treyarch's GDTs exactly as the mod tools install them,
unmodified). zmforge writes the same layout; `cat -A` of the head of a GDT
from `zmforge.texture.gdt.gdt_document` (`^I` = tab, `$` = LF, no `^M`):

```
{$
^I"i_zmf_demo_wall_c" ( "image.gdf" )$
^I{$
^I^I"arabicUnsafe" "0"$
```

- Properties are two tabs deep, `"key" "value"`, one per line, both sides
  always double-quoted. Empty value is `""`. Vectors/colours are one
  quoted string: `"colorSRGB" "1 0.857603 0.67451 1"`. Booleans are
  `"0"`/`"1"`. No `=`, no commas, no semicolons, no comments anywhere.
- **Backslashes in paths are doubled.** Verified with `cat -A` on the
  `baseImage` line (917) of
  `https://raw.githubusercontent.com/MattFiler/zm_alien_isolation/master/texture_assets/alien_isolation_decals.gdt`.
  zmforge's output, same check:
  ```
  ^I^I"baseImage" "texture_assets\\zm_fmtdemo\\demo_wall_c.tif"$
  ```
  A generator that writes single backslashes is wrong.
- Keys within an entity are written in ASCII-sort order in every real
  file. Whether gdtdb *requires* it is unverified.

## 2.2 Entity blocks and `.gdf` parents

Exact form is `<TAB>"assetname" ( "parent.gdf" )`, then `<TAB>{ … <TAB>}`.
zmforge's xmodel entry (`zmforge.props.gdt.gdt_document`), abridged:

```
	"zmf_demo_crate" ( "xmodel.gdf" )
	{
		"arabicUnsafe" "0"
		...
	}
```
(The `ai_skybox` entity of MattFiler's
`https://raw.githubusercontent.com/MattFiler/zm_alien_isolation/master/model_export/alien_isolation_models.gdt`
has the same form.)

- One space after the closing quote of the name, one space inside each
  paren.
- **The `.gdf` reference is a bare filename, never a path.** Across all
  stock `source_data` GDTs plus the usermap GDTs checked, the pattern
  `\( *"[^"]*\.gdf" *\)` matched only bare names — zero slashes.
- **Blocks never nest.** Depth is exactly 2: file brace → entity brace.
- The asset name is the global key and must be unique across every GDT the
  database sees. On a clash `gdtdb.exe` prints an `ERROR: Duplicate
  '<asset type>' asset '<name>' found in <gdt path>` line and still ends
  with its processed-GDTs/assets summary (example run shown in the
  `https://github.com/shidouri/GDTDupePurgerPy` README).

Entity header lines seen in real files, showing the `.gdf` names in use:

```
	"dirt_run" ( "material.gdf" )
	"dirt_run_c" ( "image.gdf" )
	"ai_skybox" ( "xmodel.gdf" )
	"ai_zombie_base_ad_attack_v1" ( "xanim.gdf" )
	"dog_ai_defaultmelee_zm" ( "meleeweapon.gdf" )
	"m2_flamethrower_zombie_bo3" ( "gasweapon.gdf" )
	"ai_skybox_settings_spawn" ( "ssi.gdf" )
	"smg" ( "sharedweaponsounds.gdf" )
```

Other `.gdf` parents present in the stock GDTs: `attachment.gdf`,
`attachmentunique.gdf`, `fog.gdf`, `light.gdf`, `physpreset.gdf`,
`rumble.gdf`, `tracer.gdf`, `xcam.gdf`, `zbarrier.gdf`,
`scriptbundle.gdf`, `aitype.gdf`, `objective.gdf`, `weaponcamo.gdf`,
`surfacesounddef.gdf`, `surfacefxtable.gdf`.

Two negatives worth knowing: **BO3 has no `weapon.gdf`** (it is
`bulletweapon.gdf` / `meleeweapon.gdf` / `gasweapon.gdf`) and **no
`fx.gdf` / `sound.gdf`** — FX ship as raw `.efx` under
`share/raw/fx/<mapname>/`. (Exhaustive over all 58 stock `source_data`
GDTs and the usermap GDTs checked; not over all 354 stock GDTs.)

## 2.3 Property sets that matter

**image**, as zmforge writes it (`zmforge.texture.gdt`, abridged to the
keys that matter; the `dirt_run_c` entity of `alien_isolation_decals.gdt`
sets the same keys, with `compressionMethod` `compressed high color`):

```
	"i_zmf_demo_wall_c" ( "image.gdf" )
	{
		"baseImage" "texture_assets\\zm_fmtdemo\\demo_wall_c.tif"
		"compressionMethod" "compressed no alpha"
		"coreSemantic" "sRGB3chAlpha"
		"imageType" "Texture"
		"mipMode" "Average"
		"semantic" "diffuseMap"
		"streamable" "1"
		"type" "image"
	}
```

**material**, same emitter (abridged; `dirt_run` in the same MattFiler file
is a `lit_decal_diffuse` decal that also sets `alphaRevealMap` and
`materialCategory` `Decal`):

```
		"colorMap" "i_zmf_demo_wall_c"
		"materialCategory" "Geometry"
		"materialType" "lit_detail"
		"sort" "<default>*"
		"surfaceType" "plaster"
		"template" "material.template"
		"usage" "interior wall"
```

Notes from real files: `"template" "material.template"` is on every
material entity seen; enum defaults carry a trailing `*`
(`"sort" "<default>*"`, `"alphaTest" "Always*"`); materials have **no**
`"type"` key, unlike image/xmodel/xanim. `colorMap` may be either an image
**asset name** in the same GDT (`dirt_run_c`) or a **raw path**
(`"colorMap" "raw\\images\\loadscreen_mapname.tga"`, from
`https://raw.githubusercontent.com/shippuden1592/BO-Zombies-Maps-Maker/main/Shippuden%20Map%20Maker/template/source_data/preview_mapname.gdt`).

**xmodel**, zmforge's entry (abridged); `alien_isolation_models.gdt` sets the
same keys for its skybox model:

```
		"filename" "zm_fmtdemo\\crate.xmodel_bin"
		"type" "rigid"
		"lodPresets" "custom"
		"scale" "1"
		"BulletCollisionLOD" "None"
```

**xanim** (`T7-GDT-Backup .../xanim_export/t7_ai_zombie.gdt`): an entity
carries `filename` (the `ai\\zombie\\<name>.XANIM_BIN` path),
`looping` (`0` for an attack) and `type` (`delta` for
`ai_zombie_base_ad_attack_v1`). zmforge does not emit xanims.

## 2.4 Where `.gdt` files live

Four directories under the BO3 install root, from the stock manifest
(`https://raw.githubusercontent.com/shidouri/GDTDupePurgerPy/HEAD/stock.gdtdef`,
counted by directory):

```
2169  model_export
 162  texture_assets
  65  source_data
  16  xanim_export
```

plus `archetypes/` and `art_assets/t6_legacy/texture_assets/`. Manifest
header (`https://raw.githubusercontent.com/shidouri/T7-GDT-Backup/HEAD/stock.gdtmanifest`):
its comment lines describe the file as a cache of every `.gdt` in a fresh
mod tools install, and count 354 GDT files in the stock tools.

Subdirectories are allowed
(`model_export/t7_props/p7_weapon_rack_safehouse_01/p7_weapon_rack_safehouse_01.gdt`
is a real stock path).

Community doc on where to save
(`https://wiki.modme.co/wiki/black_ops_3/basics/Custom-materials.html`,
Tier C): it tells the reader to save every GDT under
`Black Ops 3\source_data`. Otherwise the asset is missing from APE and
Radiant the next time they open.

The same README shows gdtdb run as `gdtdb\gdtdb.exe /update` from the
install root; it answers `gdtDB: updating`.

**Observed (not documented) split by directory:** `texture_assets/` →
image + material; `model_export/` → xmodel; `xanim_export/` → xanim;
`source_data/` → everything else; `archetypes/` → aitype. Evidence is the
alien-isolation repo's own layout (1017 material + 116 image in
`texture_assets/alien_isolation_textures.gdt`; 280 xmodel in
`model_export/alien_isolation_models.gdt`).

**There is no required `zm_<mapname>.gdt`.** `MattFiler/zm_alien_isolation`
is a fully released BO3 usermap and has no GDT named after the map; its
`source_data/` holds one freely-named file. Asset resolution is by asset
name, not filename. The only per-map GDT a usermap template ships is the
loadscreen/preview material, duplicated into `source_data/` and
`texture_assets/` (`preview_mapname.gdt`, 648 lines, one `material.gdf`
entity). There is no evidence of a minimum required `source_data` content
for a usermap.

---

# 3. The `.zone` / zone_source manifest

## 3.1 Location and naming

`usermaps/<mapname>/zone_source/<mapname>.zone`, with a companion
localization zone at `usermaps/<mapname>/zone_source/loc/<mapname>.zone`.
Real trees:

- `clixmods/zm_nuked` (Steam-Workshop-published BO3 zombies map):
  ```
  zone_source/loc/zm_nuked.zone
  zone_source/zm_nuked.zone
  zone_source/zm_nuked.zpkg
  ```
- `FugXBL/bo3triggertest`: `usermaps/mp/mp_triggertest/zone_source/mp_triggertest.zone`
  (MP, shown for the `usermaps/<mode?>/<map>/zone_source/` shape).

`.zpkg` files are zone fragments pulled in with `include,<name>`
(extension omitted in the reference). `zm_nuked.zone` contains
`include,zm_nuked` and `zone_source/zm_nuked.zpkg` exists.

No `core_*.zone` is ever authored by the mapper.

## 3.2 Line syntax

- `>prefix,value` — zone metadata / linker directive.
- `prefix,value` — an asset reference to pull into the fastfile.
- `//` — comment, whole-line or trailing. Blank lines are free.

The head of the zone zmforge writes for a generated map
(`usermaps/zm_fmtdemo/zone_source/zm_fmtdemo.zone`):

```
>class,zm_mod_level
>group,modtools
>title,Fmtdemo
```

Released maps use the same two opening directives: clixmods' `zm_nuked.zone`
(`https://raw.githubusercontent.com/clixmods/zm_nuked/main/zone_source/zm_nuked.zone`)
starts with `>class,zm_mod_level` and `>group,modtools`. Its companion
`.../zone_source/loc/zm_nuked.zone` holds only directives: `>mode,zm`,
`>type,level`, `>expect,core_all`, `>expect,zm_common_all`,
`>level.xpak_write,zm_nuked` and `>linker.animation_mode,ZM`.

Comments: ohm-nabar's `zm_building.zone`
(`https://raw.githubusercontent.com/ohm-nabar/zm_building/master/zone_source/zm_building.zone`)
has a commented-out asset line (`//image,...`), a whole-line section
comment, and a trailing `//` comment after a `ttf,` asset line: a
released map uses comments in both positions.

The exact semantics of `>` are inferred from usage — no primary doc
exists (wiki.modme.co has no `.zone` syntax page; confirmed by listing its
full BO3 tree).

## 3.3 Asset type prefixes (all quoted from real BO3 files)

| Prefix | Real line | File |
|---|---|---|
| `xmodel` | `xmodel,skybox_default_day` | zm_nuked.zone |
| `material` | `material,luts_t7_default` | zm_nuked.zone |
| `image` | `image,uie_t7_zm_hud_score_char1` | zm_building.zone |
| `sound` | `sound,zm_building` | zm_building.zone |
| `col_map` | `col_map,maps/zm/zm_nuked.d3dbsp` | zm_nuked.zone |
| `gfx_map` | `gfx_map,maps/zm/zm_nuked.d3dbsp` | zm_nuked.zone |
| `fx` | `fx,zombie/fx_perk_quick_revive_factory_zmb` | zm_nuked.zpkg |
| `xanim` | `xanim,t6_ai_zombie_base_attack_v1` | zm_building.zone |
| `weapon` | `weapon,raygun_mark2_zm` | zm_nuked.zpkg |
| `stringtable` | `stringtable,gamedata/weapons/zm/zm_nuked_weapons.csv` | zm_nuked.zpkg |
| `localize` | `localize,nuked_string` | zm_nuked.zpkg |
| `rawfile` | `rawfile,ui/uieditor/widgets/hud/solo_lives.lua` | zm_building.zone |
| `scriptparsetree` | `scriptparsetree,scripts/zm/zm_nuked.gsc` | zm_nuked.zpkg |
| `aitype` | `aitype,archetype_zm_shadowrunner_zombie` | zm_building.zone |
| `scriptbundle` | `scriptbundle,cloak_conjuring` | zm_building.zone |
| `zbarrier` | `zbarrier,zmcore_magicbox_fade` | zm_building.zone |
| `weaponcamo` | `weaponcamo,camo_t7_zmb_bgb` | bgb_pack.zpkg |
| `postfxbundle` | `postfxbundle,pstfx_zm_castle_teleport` | zm_building.zone |
| `ttf` | `ttf,fonts/default.ttf` | zm_building.zone |
| `include` | `include,bgb_pack` | zm_building.zone |
| `ignore` | `ignore,core_common` | loc/zm_nuked.zone |
| `ignore_missing_shipped` | `ignore_missing_shipped,core_pre_gfx` | loc/zm_nuked.zone |

Searched for and **not found** in any BO3 zone file: `col_map_sp`,
`lua_file`, a bare `character,` prefix, a bare `csv,` prefix. CSV-backed
tables use `stringtable,<file>.csv`.

## 3.4 What a zombies usermap must list

The whole zone zmforge writes for the `three-room` recipe
(`zmforge generate zm_fmtdemo --recipe three-room`):

```
>class,zm_mod_level
>group,modtools
>title,Fmtdemo
>level.forced_model_lods,-4
>level.force_static_models,1
>level.force_view_models,1
>level.force_world_materials,1

col_map,maps/zm/zm_fmtdemo.d3dbsp
gfx_map,maps/zm/zm_fmtdemo.d3dbsp

scriptparsetree,scripts/zm/zm_fmtdemo.gsc
scriptparsetree,scripts/zm/zm_fmtdemo.csc
```

The `>level.force_*` / `>level.forced_model_lods` lines are zmforge
settings, not requirements. clixmods' released `zm_nuked.zone`
(`https://raw.githubusercontent.com/clixmods/zm_nuked/main/zone_source/zm_nuked.zone`)
is a similarly small file: the two `>class` / `>group` directives, an
`xmodel,skybox_default_day` and a `material,luts_t7_default` line, the
`col_map` / `gfx_map` pair for `maps/zm/zm_nuked.d3dbsp`, `sound,zm_nuked`,
and `include,zm_nuked`; it puts its scripts in the included package rather
than in the zone itself.

Its `include,zm_nuked` → `zm_nuked.zpkg`, which carries
`scriptparsetree,scripts/zm/zm_nuked.gsc`,
`scriptparsetree,scripts/zm/zm_nuked.csc`, the weapon stringtable and
`scriptparsetree,scripts/zm/zm_usermap.csc // Required to use custom table weapon`.

So the minimum set is: `>class,zm_mod_level` + `>group,modtools`,
`col_map` and `gfx_map` pointing at `maps/zm/<map>.d3dbsp`, and
`scriptparsetree` for the map's `.gsc` and `.csc`. `sound,<map>` is **not**
in the minimum: every released map carries it, but zmforge's zone omits it
unless the map has a sound bank (`sound_bank=False` by default in
`zmforge.emit.manifest`), and a zmforge map linked without it
(`map-generator-spec.md`, "Entries real shipped maps carry that the reference omits";
`tests/logs/zm_forge_gate.link.log` ends in `done` with only
lighting-export warnings). Whether leaving it out costs anything at runtime
is **[unverified]**.
A larger real example (711 lines) is
`https://raw.githubusercontent.com/ohm-nabar/zm_building/master/zone_source/zm_building.zone`.

`ignore,core_common`-style lines live in the **loc** companion file, not
the main zone — see [§5](#5-unverified--folklore).

## 3.5 A real linker failure

A linker transcript posted in Modme forum thread 1388
(`https://raw.githubusercontent.com/dtzxporter/ModmeForum/main/wiki/threads/1388.md`)
shows how a failure reads. The map being linked was a usermap (`zm_thehill`).
The linker first reported that Lua was not supported for a `rawfile` HUD
widget (`ui/uieditor/widgets/hud/zm_perks/customperkicons.lua`). It printed
the chain that pulled that asset in, indented one level per step: the
widget, then the perk pack's `hb21_perks.zpkg`, then the map's
`zone_source/zm_thehill.zone`. It then stopped with an unrecoverable
script error saying there was no generated data for
`scripts/zm/_zm_perk_doubletap2.gscc`.

In that chain the linker labels the `.zone` and `.zpkg` files `csv:`,
consistent with them being parsed as generic comma-separated files.

---

## 3.6 Presentation: loading screen, thumbnail and display name

**[measured on Windows]** Both presentation images are loose
`.png` files in the map's `zone\` folder, beside the fastfiles, under fixed
file names. The linker never sees either one.

That is the whole story for the **menu thumbnail**, and it is measured: a
generated `previewimage.png` shows on the map-selection card of a locally
built map, with no `.zone` line and no `.gdt` entity involved.

It is **not** the whole story for the **loading screen**: the same map,
built the same way, shows its card and shows **nothing** while it loads.
See "The loading screen needs more than the file" at the end of this section,
and `map-generator-spec.md` §6.1.2.

Primary source: the mod tools' own "ZM Mod Level" template, at
`C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops
III 455130\rex\templates\ZM Mod Level\usermaps\template\`. Its whole
tree, with sizes:

```
\scripts\zm\template.csc            1372 bytes
\scripts\zm\template.gsc            2394 bytes
\sound\zoneconfig\template.szc        541 bytes
\zone\loadingimage.png              11303 bytes
\zone\previewimage.png               3825 bytes
\zone_source\template.zone            288 bytes
```

The two PNG headers, read as raw bytes:

```
89 50 4e 47 0d 0a 1a 0a 00 00 00 0d 49 48 44 52 00 00 07 80 00 00 04 38 08 02 00 00 00 ...
89 50 4e 47 0d 0a 1a 0a 00 00 00 0d 49 48 44 52 00 00 02 58 00 00 01 54 08 02 00 00 00 ...
```

So `loadingimage.png` is `0x780 x 0x438` = **1920 x 1080** and
`previewimage.png` is `0x258 x 0x154` = **600 x 340**; both are IHDR
`08 02 00 00 00`, i.e. bit depth 8, colour type 2 (truecolour, no alpha),
no interlace.

**Those are the template's numbers, and only one of them is a rule.** A
sample of 46 published Workshop items says the rest are not, and they are the better evidence, because every one of them is a
map somebody shipped and people play:

| Property | What the corpus says | What this project does |
|---|---|---|
| `loadingimage.png` size | **1920 x 1080 in all 38** examples. No exception. | Required. Check `P1` warns on anything else. |
| `previewimage.png` size | 600 x 340 in 23 of 39; the other 16 use eight sizes, from 600 x 338 to 3126 x 2027. All published, all playable. | **Convention, not a requirement.** Check `P2` does not look at the size. It is the size a generated card is *drawn* at, nothing more. |
| Colour type | 32-bit ARGB in 17 of the 38 loading screens and 19 of the 39 previews; one preview is 8-bit palette; the rest are 24-bit RGB. | **Not a requirement.** Alpha and palette both reach a shipped map. Nothing checks colour type. This section's "colour type 2" was a fact about the template read as a rule about the format. |
| Interlace | Not measured across the corpus. | Not checked. The template is non-interlaced. Nothing else about interlacing is known. |

The eight non-template preview sizes, for the record: 1920 x 1080 (six maps),
600 x 338 (four), and one each at 600 x 360, 600 x 460, 1200 x 680,
1992 x 1306, 2218 x 1214 and 3126 x 2027. Aspect ratio is not constant
either, running from 1.30 to 1.83, so no ratio rule can be read out of
them. What this package emits is 8-bit truecolour at the template sizes,
because that is a defensible house style, not because the game demands it.

Published Workshop maps ship the same two names flat in the item folder:
a typical item under `steamapps\workshop\content\311210\<item id>\` holds `loadingimage.png`, `loadingimage.jpg`, `previewimage.png`,
`workshop.json` and the per-language `.ff`/`.xpak` pairs, so `.jpg` is
accepted as well as `.png`.

Across 40 published maps surveyed, **38 ship both names flat**, one ships
the preview only, one ships
neither. All six published *mods* ship neither, which fits: a mod has no
card on the map-selection screen. Publishing lifts `zone\*` up a level and
changes nothing else, so the images keep their position relative to the
fastfiles.

`template.zone` itself has **no** `>title` line, so a map made from the
template has no display name. It holds the `>class,zm_mod_level` and
`>group,modtools` directives, `xmodel,skybox_default_day`,
`material,luts_t7_default`, the `col_map` / `gfx_map` pair for
`maps/zm/template.d3dbsp`, `sound,template`, and `scriptparsetree` lines for
`scripts/zm/template.gsc` and `.csc`, with `// BSP` and `// Audio` section
comments.

**Display name** is the manifest's `>title,` line, free text. Treyarch's
shipped example usermap proves it: `usermaps\mp_combine\zone_source\
mp_combine.zone` starts

```
>class,mp_mod_level
>group,modtools
>title,Mod Combine
```

while its folder — and its asset name — is `mp_combine`. No `.str`
localisation file is involved; there are **zero** `*.str` files anywhere
under the tools root, and no `ui_scripts`, `LUI` or `lui` directory
exists (searched recursively). A usermap's `workshop.json` carries a
title again for the Workshop page, in the shape (`"FolderName": "zm_example"`,
`"Title": "Example Map [V1.0]"`, `"Type": "map"`, `"Thumbnail":
"<absolute path to a png>"`).

**What the engine falls back to.** `model_export\code.gdt` declares two
stock 2d images: `img_t7_mod_preview` (an `image.gdf` entity whose
`baseImage` is `texture_assets\\menu_T7\\loadscreens\\img_t7_mod_preview.png`,
with `semantic` `2d` and `noMipMaps` `1`) and `img_t7_mod_loading` beside it, and both are listed in
`zone_source\all\assetlist\core_patch.csv:594-595` as
`image,img_t7_mod_loading` / `image,img_t7_mod_preview`. That is the
generic mod artwork; it is what the menu has to work with when a map
ships neither PNG. Grepping every `*.lua`, `*.csv`, `*.gsc` and `*.txt`
under `share\raw` for `loadscreen` returns exactly one unrelated
comment, so the lookup itself lives in the shipped game, not in the
tools. **Which image the game draws for a usermap with no
`loadingimage.png` is not established here** — the observed symptom is a
black loading screen.

Note that the `preview_mapname` **material** quoted in
[§2.3](#23-property-sets-that-matter) (`"colorMap"
"raw\\images\\loadscreen_mapname.tga"`, from a community map-maker
template) is *not* this mechanism, and no stock `.gdt` under the tools
root contains a `loadscreen_<map>` material.

### The loading screen needs more than the file

**A loose `loadingimage.png` does not make a loading screen; the
`black`-image override does.** Two sources establish the first half and name
the mechanism, and the run under Wine below measures the second half:

1. **In game [measured].** A locally built map with a
   valid 1920 x 1080 `loadingimage.png` in its `zone\` folder shows its
   preview card and shows nothing at all while loading. Name, location,
   format, size and bit depth were each ruled out against the published
   corpus (`map-generator-spec.md` §6.1.2). So the loose file is **not
   sufficient** for a local map, whatever else is true.
2. **A tutorial that states the mechanism [lead, not measured].**
   Logical Edits, "Preview Image, Loading Screens, & Steam Workshop Page"
   (2022-10-03, 1:11–3:25), says the full-screen image is not read as a file
   at all: it is drawn from a stock image asset named `black`, which a map
   overrides in three steps that have to be done together:

   - point the `black` image asset at your PNG in APE, image usage `2D`,
     compressed texture bitmap off, streamable on;
   - comment out the `image,black` row in
     `zone_source\all\assetlist\core_gfx.csv` with a leading `//`;
   - add `image,black` to the map's own `.zone`.

**The override reproduces under Wine [measured].** A scratch map `zm_test` was linked three times
with the same inputs and only these two edits varying:

| Run | `core_gfx.csv` row 304 | `image,black` in the `.zone` | Linker log | Packed |
|---|---|---|---|---|
| baseline | `image,black`, live | absent | silent | no, 24,466,048 byte `.ff` |
| override | `//image,black` | present | `Converting image black`, then `Load 1920x1080 (1920x1080) Expand .. Mipmap . Compress R8G8B8A8 . Save` | **yes**, and `image,black` appears in the linker's own output assetlist; `.ff` grows to 24,600,064 |
| control | `image,black`, live | present | silent | no, back to 24,466,048 |

No `ERROR:` line in any run. The control run is the one that earns its keep:
with the stock row live, the map's own `image,black` line is **silently
ignored**. So commenting the row out is not optional bookkeeping, it is the
thing that makes the linker willing to pack the asset at all.

Three further facts fell out of that run:

- **APE is not required.** `black` is one image row in `gdt.db`, declared in
  `texture_assets\code.gdt` with a stock `baseImage` of
  `texture_assets\t7_default\default_black_0.tif`, `semantic` `glossMap`,
  `compressionMethod` `compressed`. The tutorial's three APE controls are
  those fields: image usage `2D` is `semantic` `2d`, compressed-bitmap-off is
  `compressionMethod` `uncompressed`, streamable is `streamable` `1`. The row
  can be written directly.
- **A `.png` is accepted as the source.** The TIFF requirement is for 3D
  textures. `img_t7_mod_loading` and `img_t7_mod_preview` both carry `.png`
  in `baseImage`, and the link above converted a PNG without complaint.
- **No shipped `.zone` does this.** `image,black` appears in none of the 22
  `.zone` files on the install, template included.

**What is still not proven is that this is the cause.** The mechanism builds;
that it is what draws a usermap's loading screen has not been seen on screen,
and one measured fact argues against the strong form of the claim: 38 of the
40 published maps ship a loose `loadingimage.png`, which would be pointless
for all 38 if the file were inert. Loading a packed map in the game is what
settles it.

The contested thread this page quoted against the technique
(`https://forum.modme.co/wiki/threads/1560.html`, which warns that `black` is
also drawn by several script HUD elements, so an overridden loading screen
turns up in unexpected places) is not a reason to disbelieve the mechanism. It
is a reported side effect *of* the mechanism, and the `black` asset really is
shared: one row in one `gdt.db`, with `core_gfx.csv` one file per install and
no per-map assetlist override anywhere on it. A map's own
`usermaps\<map>\zone_source\all\assetlist\<map>.csv` is the linker's
**output**, not an input.

The mutation does not have to persist, though, and that is the measured part
that decides how a generator should use this. The linker bakes the converted
image into `<map>.ff` at link time: after both `gdt.db` and `core_gfx.csv`
were restored to stock, the test fastfile kept its 24,600,064 bytes and its
`image,black` assetlist row. So the shape is **set, link, restore**, taken
under a lock, and two maps built that way each carry their own loading screen
rather than fighting over one asset. What must not happen is a build that
sets and never restores: that leaves the whole install's `black` image
pointing at one map's artwork, and `black` is used by HUD elements, which is
what the forum thread was complaining about. See `map-generator-spec.md`
§6.1.2 for where the verification stands.

---

# 4. Zombies-mode requirements for a usermap

## 4.1 What the map's `.gsc` must do

Treyarch's own raw mod-tools `zm_usermap.gsc`
(`https://raw.githubusercontent.com/marcogravbrot/bo3-mod-tools/master/raw_scripts/zm/zm_usermap.gsc`,
lines 122-150; re-fetched and grepped): `main()` sets
`level.default_start_location` to `"start_room"` and
`level.default_game_mode` to `"zclassic"`, calls `load::main()`, then
applies `DEFAULT` to `level.dog_rounds_allowed` with a default of 1 and,
when the result is true, calls `zm_ai_dogs::enable_dog_rounds()`.

`DEFAULT(var, default)` is a macro in `scripts/shared/shared.gsh` that
assigns the default only when the variable is undefined, so a map that sets
`level.dog_rounds_allowed` before calling `zm_usermap::main()` wins.

**`zm_usermap::main()` never creates zones.** It does not set
`level.zone_manager_init_func` and does not call `manage_zones`. The map
script must. What zmforge emits for the three-room recipe
(`share/raw/scripts/zm/zm_fmtdemo.gsc`, after its `#using` / `#insert`
header, which includes `scripts\zm\_zm_zonemgr` and `scripts\zm\zm_usermap`):

```
function main()
{
	level.dog_rounds_allowed = 0;
	zm_usermap::main();
	level.start_chest_name = "start_chest";
	level.enable_magic = true;
	level.zone_manager_init_func = &connect_zones;
	init_zones = [];
	init_zones[0] = "start";
	init_zones[1] = "arena";
	init_zones[2] = "vault";
	level thread zm_zonemgr::manage_zones( init_zones );
}

function connect_zones()
{
	level flag::init( "always_on" );
	level flag::set( "always_on" );
	zm_zonemgr::add_adjacent_zone( "start", "arena", "enter_arena" );
	zm_zonemgr::add_adjacent_zone( "arena", "vault", "enter_vault" );
}
```

Released maps follow the same pattern: MattFiler's
`zm_alien_isolation.gsc`
(`https://github.com/MattFiler/zm_alien_isolation/blob/master/usermaps/zm_alien_isolation/scripts/zm/zm_alien_isolation.gsc`)
calls `zm_usermap::main()`, assigns its zone function to
`level.zone_manager_init_func`, fills `init_zones[]`, threads
`zm_zonemgr::manage_zones`, and in the zone function calls
`add_adjacent_zone` per connection plus `flag::init` / `flag::set` on
`"always_on"`.

`manage_zones` (`_zm_zonemgr.gsc:874`) calls
`level.zone_manager_init_func` if one is set, then, for each entry of the
initial-zone array, runs `zone_init` and `enable_zone` on it.

`add_adjacent_zone( a, b, flag_name, … )` auto-creates the flag and both
zones.

## 4.2 The entity lookups the stock scripts perform

All quotes from the decompiled stock scripts at
`https://github.com/ate47/bo3-source/tree/main/scripts/zm`.

| Thing | Lookup | Entity that satisfies it |
|---|---|---|
| Playable area | `level.playable_areas = getentarray( "player_volume", "script_noteworthy" );` (`_zm.gsc:2007`, `_zm_spawner.gsc:635`) | `info_volume` + `"script_noteworthy" "player_volume"` |
| Zone volume | `volumes = getentarray( zone_name, "targetname" ); … if ( volumes[i].classname == "info_volume" )` (`_zm_zonemgr.gsc` `zone_init`) | `info_volume` whose `targetname` **is** the zone name |
| Zone's spawn structs | `spots = struct::get_array( zone.volumes[0].target, "targetname" );` | structs whose `targetname` equals the volume's `target` |
| Spawn-location type | `tokens = strtok( spot.script_noteworthy, " " ); … case "riser_location": case "spawn_location": case "faller_location": case "custom_spawner_entry":` | `script_struct` with one of those tokens |
| Riser dispatch | `if ( token == "riser_location" ) { self thread zm_spawner::do_zombie_rise( spot ); continue; }` (`_zm_utility.gsc:252`) | — |
| `find_flesh` | `self notify( #"risen", spot.script_string );` (`_zm_spawner.gsc:3146`) and `if ( isdefined( self.script_string ) && self.script_string == "find_flesh" ) { return true; }` (`should_skip_teardown`, `_zm_spawner.gsc:485`) | `"script_string" "find_flesh"` on the struct |
| AI factory | `level.zombie_spawners = getentarray( "zombie_spawner", "script_noteworthy" );` (`_zm_spawner.gsc:40`) | `actor_spawner_zm_factory_zombie` + `"script_noteworthy" "zombie_spawner"` |
| Player spawns | `structs = struct::get_array( "player_respawn_point", "targetname" );` then `structs = struct::get_array( "initial_spawn", "script_noteworthy" );` with fallback `struct::get_array( "initial_spawn_points", "targetname" );` (`gametypes/_zm_gametype.gsc:288, 353, 376`) | `script_struct`s — **`info_player_start` is never read in the ZM path** |
| Which spawn a player gets | `if ( spawnpoints[ j ].en_num == player.playernum ) { return spawnpoints[ j ]; } … return spawnpoints[ 0 ];` (`zm::getfreespawnpoint`, `_zm.gsc:815-831`), with `en_num` assigned by the framework as the array index | one struct per player; players past the end of the array all land on the **first** struct |
| `script_int` on an initial-spawn struct | `if ( isdefined( spawnpoints[ i ].script_int ) && player.team == "allies" && spawnpoints[ i ].script_int == 2 ) { arrayremovevalue( … ); }` (`_zm.gsc:774-810`) | the **team side**, 1 or 2 — *not* a slot number. Omit it: one of the two is deleted every game, chosen by `side_selection = randomint( 100 ) > 50` |
| `script_int` on `player_respawn_point` | `ideal_distance = spawn_points[ j ].script_int;` else `1000` (`check_for_valid_spawn_near_team`, `_zm.gsc:3423-3429`) | a distance in units, which is why the shipped value 2000 equals that struct's `radius` |
| The four-player limit | `set com_maxclients 4` / `set party_maxplayers 4` (`gamedata/configs/zm/zm_default_gamesettings.cfg:8-9`) | **not map data** — no per-map, zone or GDT file declares a player count |
| Gamemode match | `match_string = level.scr_zm_ui_gametype + "_" + location;` → e.g. `zclassic_start_room`, matched against the struct's `script_string` tokens | `"script_string" "zclassic_start_room zcleansed_start_room zgrief_start_room"` |
| Barricades | `entry_points = struct::get_array( zone_name + "_barriers", "script_noteworthy" );` (`_zm_zonemgr.gsc:555`) | structs with `script_noteworthy "<zone>_barriers"` — this suffix **is** hardcoded |
| Buyable doors | `zombie_doors = getentarray( "zombie_door", "targetname" );` (`_zm_blockers.gsc:63`) | `trigger_use` with `targetname "zombie_door"` |
| Door cost / flag | `cost = 1000; if ( isdefined( self.zombie_cost ) ) { cost = self.zombie_cost; }` and `tokens = strtok( self.script_flag, "," ); … level flag::init(…)` | `"zombie_cost"`, comma-separated `"script_flag"` |
| Electric doors | `if ( self.script_noteworthy == "electric_door" \|\| self.script_noteworthy == "electric_buyable_door" )` | — |
| Perk machines | `structs = struct::get_array( "zm_perk_machine", "targetname" );` (`_zm_perks.gsc` ~1488) | `script_struct` with `targetname "zm_perk_machine"`, `script_noteworthy "<specialty>"`, `model "<vending model>"` |
| Hand-placed perk triggers | `vending_triggers = getentarray( "zombie_vending", "targetname" );` (`_zm_perks.gsc:45`) | — |
| Power switch | `trigs = getentarray( "use_elec_switch", "targetname" );` (`_zm_power.gsc:80`), then the trigger's `target` is resolved to an ent with `script_noteworthy "elec_switch"` and a struct with `script_noteworthy "elec_switch_fx"` | `trigger_use` + `script_model` + `script_struct` triplet |
| Dog spawners | `level.dog_spawners = getentarray( "zombie_dog_spawner", "script_noteworthy" );` (`_zm_ai_dogs.gsc:117` — verified by direct fetch) | `actor_spawner_zm_factory_zombie_dog` |
| Dog spawn points | `dog_locs = array::randomize( level.zm_loc_types[ "dog_location" ] );` (`_zm_ai_dogs.gsc:350`) | `script_struct` + `script_noteworthy "dog_location"` |

### Purchase prompts are localized references, not text the mapper supplies

Read from the same decompiled tree. This decides what a map can
name things, so it belongs with the lookups above.

| Prompt | What the script sets | Where |
|---|---|---|
| wall buy | `struct.hint = &"ZOMBIE_WEAPONCOSTONLYFILL";` (or the `_CFILL` variant) | `_zm_weapons.gsc:664`, `:668`; read back by `get_weapon_hint` `:1543-1546`; pushed at `:1329`, `:1341` |
| wall buy weapon name | never passes through script: the engine draws it from the cursor hint | `_zm_unitrigger.gsc:908-910` `trigger setcursorhint( stub.cursor_hint, stub.cursor_hint_weapon )` with `"HINT_WEAPON"` |
| closed mystery box | `&"ZOMBIE_RANDOM_WEAPON_COST"`, registered once by ref | `_zm.gsc:1136` `add_zombie_hint( "default_treasure_chest", … )`, fetched `_zm_magicbox.gsc:331` |
| open box (grab) | `&"ZOMBIE_TRADE_WEAPON_FILL"` / `&"ZOMBIE_TRADE_EQUIP_FILL"` | `_zm_magicbox.gsc:320`, `:324` |

The only script-supplied parameter in any of them is the **cost**. Of 614
`sethintstring(` call sites in the tree, every non-localized literal is `""`,
which clears a prompt (`_zm_blockers.gsc:865`). A custom display name would
need a new localized string asset (`.str` plus a `localize` zone entry), and
no `.str` file exists in the decompiled tree or anywhere in the install; a
map can still ship its own (spec 5.7).

**The perk machine trigger/clip/model triplet is built by the framework,
not the mapper.** From one struct, `_zm_perks.gsc` spawns three things at
the struct's origin: a `trigger_radius_use` (radius 40, height 80, raised
60 units) with `targetname` `zombie_vending`; a `script_model` that takes
the struct's `model`; and a second `script_model` set to
`zm_collision_perks1` with `script_noteworthy` `clip`.

## 4.3 The exact KVPs, from real map files

**Riser**, as zmforge emits it (`zm_fmtdemo.map` from the three-room
recipe):

```
{
guid "{51D709DD-D656-403E-96E5-324DF99F1799}"
layer "The Map"
"classname" "script_struct"
"targetname" "arena_spawners"
"script_noteworthy" "riser_location"
"script_string" "find_flesh"
"origin" "0 -460 16"
"angles" "0 90 0"
}
```

Entity 1041 of `zm_alien_isolation.map` is a riser with the same three
load-bearing keys (`script_noteworthy riser_location`, `script_string
find_flesh`, and a `targetname` equal to its zone volume's `target`), plus
Radiant's `"_color"` editor key.

**Zone volume** (same file, entity 402):

```
"classname" "info_volume"
"script_noteworthy" "player_volume"
"target" "start_zone_spawners"
"targetname" "main_zone"
```

Note the volume is a **brush entity** — its brushes follow inside the same
braces and carry `contents detail;`.

**Player spawn pair** (same file, entities 2478 and 3326):

```
"classname" "script_struct"
"radius" "2000"
"script_int" "2000"
"script_noteworthy" "start_room"
"script_string" "zclassic_start_room zcleansed_start_room zgrief_start_room"
"targetname" "player_respawn_point"

"classname" "script_struct"
"radius" "32"
"script_int" "1"
"script_noteworthy" "initial_spawn"
"script_string" "zcleansed_start_room"
"targetname" "initial_spawn_points"
```

**Read the `script_int` on that second struct correctly.** It is a team
side, not a slot. `zm_alien_isolation.map` has **eight** initial-spawn
structs, all tagged `zcleansed_start_room`, four with `script_int 1` and
four with `script_int 2` — the two sides of a team mode, four places
each — and **none at all** for `zclassic`, which therefore takes the
`player_respawn_point` fallback. Shipped `zm_giant.map` goes the other
way: four `initial_spawn_points` structs carrying only `classname`,
`angles`, `origin` and `targetname`, no `script_int`, no `script_string`,
no `script_noteworthy`, reached from `"target" "initial_spawn_points"` on
its `player_respawn_point` (entity 190). Both are valid; a numbered
1..2..3..4 set for survival is not, because `getfreespawnpoint` deletes
1 or 2 on a per-game coin flip.

**How many to emit.** One per player you want placed separately. The
framework numbers them itself (`en_num` = array index) and returns
`spawnpoints[ 0 ]` for any player whose index runs past the end, so four
structs seat four players and stack the fifth onward on the first point.
Eight structs seat eight and are inert in a four-player game. Nothing in
the map declares a player count; `com_maxclients` does.

**Zombie AI factory** (same file, entity 1):

```
"classname" "actor_zm_nuked_basic_01"
"count" "9999"
"export" "1"
"model" "c_t6_default_character_fb"
"script_disable_bleeder" "1"
"script_forcespawn" "1"
"script_noteworthy" "zombie_spawner"
"spawnflags" "3"
```

The stock-derived version uses classname `actor_spawner_zm_factory_zombie`
with the same `script_noteworthy "zombie_spawner"`. This package emits
`actor_spawner_zm_usermap_zombie` instead -- the other of the
two zombie `aitype`s in `archetypes/archetypes.gdt`, and the one
`share/zone_source/zm_levelcommon.zone:51` declares for a usermap. Both link.

**Dog spawner + location struct**, as zmforge's spawn emitter writes them
(`zmforge.emit.mapfile._spawn_entities` for a `kind="dog"` spawn; GUIDs
elided):

```
// entity 0
{
guid "{<guid>}"
layer "The Map"
"classname" "script_struct"
"targetname" "start_spawners"
"script_noteworthy" "dog_location"
"script_string" ""
"origin" "64 16 0"
"angles" "0 0 0"
}
// entity 1
{
guid "{<guid>}"
layer "The Map"
"classname" "actor_spawner_zm_factory_zombie_dog"
"script_noteworthy" "zombie_dog_spawner"
"count" "1"
"script_forcespawn" "1"
"spawnflags" "3"
"model" "zombie_wolf"
"origin" "64 16 0"
}
```

UGX's prefab extracted from The Giant
(`https://github.com/UGX-Mods/community-wiki/blob/main/attachments/modding/bo3/dog-spawners/dog_spawner.map`)
has the same two entities. Its struct carries `script_noteworthy
dog_location` and `targetname start_zone_spawners`. Its spawner is an
`actor_spawner_zm_factory_zombie_dog` with `script_noteworthy
zombie_dog_spawner`, `targetname special_dog_spawner`, `model zombie_wolf`,
`spawnflags 3`, `count 1`, `script_forcespawn 1`, `export 3`, and
further AI tuning keys (`engageMinDist`/`engageMaxDist`,
`sm_active_count_min`/`_max`, `script_dropammo`, the `ALERTONSPAWN` /
`MAKEROOM` / `SPAWNER` flags) that zmforge does not write.

**Mystery box** (`.../pandoras-box/box_start.map`, entities 1-3): a
`zbarrier_zmcore_MagicBox` with `"script_noteworthy" "start_chest_zbarrier"`
and 5 board/tear anim slots, plus a `script_struct` with
`"script_noteworthy" "start_chest"`, `"targetname" "treasure_chest_use"`,
`"zombie_cost" "950"`, plus a `misc_prefab` for the platform.

**Buyable door** (`kelson8/bo3-Zombies-Test-Map/map_source/zm_test_map.map`):

```
"classname" "trigger_use"
"script_flag" "activate_room1_zone"
"target" "test_door1"
"targetname" "zombie_door"
"zombie_cost" "750"
"cursorhint" "HINT_ACTIVATE"
```

**Power switch triplet** (`zm_alien_isolation`, `spaceflight_terminal_power.map`):

```
"classname" "trigger_use"   "targetname" "use_elec_switch"   "target" "auto1"   "script_flag" "enter_noodlebar_zone"
"classname" "script_model"  "targetname" "auto1"             "model" "generator_handle"   "script_noteworthy" "elec_switch"
"classname" "script_struct" "targetname" "auto1"             "script_noteworthy" "elec_switch_fx"
```

## 4.4 Radiant's own entity definitions

BO3 Radiant's `t7.def.json` defines 208 entity templates and confirms
default KVPs directly
(`https://github.com/gamedev44/Radiant-/blob/main/Radiant%2B%2B%20Editor%20Improvements%20Mod/vkRadiant%20(Standard)/bin/t7.def.json`).
Each template is a JSON object with a `classname`, optional `bboxmin` /
`bboxmax` strings, and one member per key, whose value is an object with
`type`, an optional default `value`, and an editor `group`. Shape only,
written for this doc:

```json
{ "classname": "<template>", "<key>": { "type": "string", "value": "<default>", "group": "<group>" } }
```

| Template | Keys it sets | Defaults |
|---|---|---|
| `zm_spawner_riserLocation` | `targetname` (group `ZONE`), `script_string`, `script_noteworthy` (group `TYPE`); 16-unit box | `script_string` `find_flesh`, `script_noteworthy` `riser_location` |
| `zm_spawner_spawnLocation` | `script_string`, `script_noteworthy` (group `TYPE`) | `script_string` `find_flesh`, `script_noteworthy` `spawn_location` |

So `script_string "find_flesh"` is Radiant's **default for both** riser and
spawn locations. These templates are saved into the `.map` as
`"classname" "script_struct"`. The real maps contain no
`zm_spawner_riserLocation` classname, only `script_struct` carrying those
KVPs.

The same file defines `misc_prefab`'s `model` key as a string with
`fileExtension` `map`, a `filePath` of `%TA_GAME_PATH%/map_source/_prefabs`
and a `fileTrimLeft` of `%TA_GAME_PATH%/map_source/`, and describes it as
the map to use as the prefab. So the value is the prefab path relative to
`map_source/`, which is why real files read
`"model" "_prefabs/zm/zm_giant/geo/zm_giant_magicbox_platform.map"`.

It also defines `nav_volume` (the space a Nav Volume covers),
`nav_volume_passable` and `trigger_navmesh` (a volume valid for
pathfinding).

## 4.5 Dog rounds

- `DEFAULT(level.dog_rounds_allowed,1);` runs inside `zm_usermap::main()`,
  so a map that wants dogs off **must** set the value before calling it.
  A real map does exactly this
  (`kelson8/bo3-Zombies-Test-Map/scripts/zm/zm_test_map.gsc`):
  `// This has to be above the zm_usermap::main` / `level.dog_rounds_allowed = false;` / `zm_usermap::main();`
- `dog_spawner_init()` bails cleanly when there are no spawners:
  `if ( level.dog_spawners.size == 0 ) { return; }` (`_zm_ai_dogs.gsc`).
- But the spawn path dereferences without a guard —
  `ai = zombie_utility::spawn_zombie( level.dog_spawners[ 0 ] );` at lines
  221 and 235 (line numbers checked against the fetched file).
- The first dog round is **not** fixed at 5:
  `level.next_dog_round = level.round_number + randomintrange( 4, 7 );`
  (line 478) → round 5, 6 or 7.
- UGX describes the symptom as a hang, not a crash
  (`https://wiki.ugx-mods.com/Modding/Black-Ops-3-Modtools/Mapping/Adding-Dog-Spawners-or-Disabling-Dog-Rounds.html`):
  it says the test map ships without dog spawners while the scripts leave
  dog rounds enabled, so play gets stuck on an infinite dog round. The fix
  it gives is `level.dog_rounds_allowed = false;` before
  `zm_usermap::main();`.

## 4.6 Community mapping instructions (Tier C, but consistent with the code)

`https://wiki.ugx-mods.com/Modding/Black-Ops-3-Modtools/Mapping/Adding-Zombie-Spawners-Risers-and-Window-Barriers.html`
has the mapper drag an `actor\spawner_zm_factory_zombie` in from the entity
browser and set four KVPs on it:

| Key | Value |
|---|---|
| `script_noteworthy` | `zombie_spawner` |
| `coop_count` | `{9999, 0, 0, 0}` |
| `count` | `9999` |
| `script_forcespawn` | `1` |

Risers are `script\struct` entities with `targetname` `<zone_name>_spawners`,
`script_noteworthy` `riser_location` and `script_string` `find_flesh`. The
page says that `targetname` decides which zone activates the spawner. It has
to match the `target` KVP of the zone the spawner is used for.

Windows are a `misc\_prefab` pointed at
`_prefabs/zm/zm_core/barricade_reciever_wood.map`, carrying `script_string`
`<entry_name>`. The page has the mapper put a riser struct anywhere behind
the window and give it that same KVP value.

`https://wiki.ugx-mods.com/Modding/Black-Ops-3-Modtools/Mapping/Adding-Zones.html`
has the mapper drag an `info\volume` in from the entity browser. It states
that a zone is also the area a player is allowed to occupy. The KVP that
marks one is `script_noteworthy` / `player_volume`. A map with no player
volume at all kills the player on spawn.

---

# 5. Unverified / folklore

Things that could not be confirmed against a primary source. Do not treat these as
rules.

1. ~~**`ai_nosight` as a `.map` `contents` token.**~~ **SETTLED, it is
   real.** GitHub code search over public `.map` files returns zero hits,
   but the mod tools' own `map_source` carries 7,044
   `ai_nosight` occurrences and 19,553 `weaponClip` occurrences across 733
   `.map` files, all on `contents` lines **[measured]**. The spellings and
   counts are in the verified-token table above. What is *not* confirmed
   is a collision twin built from them (spec §3.2).
2. **Per-vertex colour in patches (`v X Y Z c R G B A t …`).** Claimed by
   a generator's patch fixture. Zero of the 41
   real patch blocks examined (BO3 and WaW) contain a `c` component.
   **Unverified.**
3. **`decalLayerSort` / `decalEditorSort` as trailing lines inside a patch
   body.** Verified as trailing tokens on ordinary brush **faces** in a real
   BO3 map; the patch-body placement in the fixture is **unverified**.
4. **Meaning of the 6th texture field.** Non-zero only on skewed faces,
   tiny magnitudes. No source. Emit `0`.
5. **Exact meaning of `T1`/`T2` in the patch dimension line.** Consistent
   with "curve subdivision" and "tessellation/lightmap density" across 41
   samples, but no documentation. `T1=16 T2=8` (curve) and `T1=0 T2=8`
   (mesh) are values that appear in real files.
6. **Whether `"_prefabs/<path>.map" flags prefab` layer lines are required
   for prefab auto-loading.** Some generators emit them. No
   public BO3 `.map` examined contains them; real maps reference prefabs
   purely through `misc_prefab` entities.
7. **Whether `ignore,core_common` must be hand-written into the main
   `<map>.zone`.** It appears only in the `loc/<map>.zone` companion, and
   nothing documents who writes that companion file. **Unverified.**
8. **Whether a `zm_<mapname>.gdt` is required.** No evidence; a released
   usermap has none. Treat as folklore.
9. **Whether gdtdb tolerates CRLF, spaces instead of tabs, or unsorted
   keys.** Unverified — only Treyarch's own output shape is known.
10. **Whether gdtdb scans `model_export`/`texture_assets`/`xanim_export`
    directly or only `source_data`.** Stock GDTs live in all of them, so it
    must, but no primary doc says so.
11. **Navmesh requirement.** No GSC in `scripts/zm/*.gsc` reads a nav
    entity; it is a compile-time concern. The only statement found is a
    forum post (**folklore**, Modme mirror thread 506): "it autogenerates
    navmesh if you don't place one in radiant / so if you don't place one,
    and the auto generation fails. No ai will … move".
12. **`-navmesh -navvolume` compiler flags, `bake_lighting` ordering, and
    the `cwd=bin/` + `TA_GAME_PATH` requirement** claimed in an earlier
    generator's notes. No primary source was found for them, so they stay
    **unverified** here; the generator spec (Section 7.2 and 7.3) records the
    flags, working directory and environment that a measured compile used.
13. **`smoothing smoothing_smooth_other`** is verified in official CoD4/WaW
    tools output only; not seen in a BO3 file.

---

