# Black Ops III zombies map generator: behavioural specification

Written for a clean-room reimplementation. The implementer of
this spec will not see the reference implementation and must not need to.
Everything a builder needs is here: the file formats the tools consume,
the geometry maths, the names the stock game scripts read, the build
chain, a proposed public interface, a conformance test plan, and a list
of defects already paid for so they are not paid for twice.

This is the generator's specification. `how-zombies-maps-work.md` is the
mechanism account behind it: how the engine, the compiler and the stock scripts
actually behave, independent of what this generator emits. Read that first if
you are trying to reason about a defect nobody has seen yet.

Companion document (ours, safe to read):
`mapsource-format-reference.md`, beside this file. It carries the
primary-source quotes behind the format facts below; this document does
not repeat the citations, only the rules.

## 0. How to read this document

### 0.1 Verification legend

Every claim carries one of these tags. Untagged text inherits the tag of
its section heading.

| Tag | Meaning |
|---|---|
| **[measured]** | Observed on real files or real tool runs, or measured on 25+ real brushes in the format reference. |
| **[stock-source]** | Read directly from the stock game scripts or Radiant's entity definitions. |
| **[played]** | Part of a map that compiled, linked and was played in game. Presence of the pattern is verified; that every individual key is load-bearing is not. |
| **[inherited]** | Reported by the original authors from their own playtests. Plausible, not re-verified by us. Treat as a requirement anyway unless it contradicts a higher tag. |
| **[unverified]** | No primary evidence. Implement the safe behaviour and expose it as a knob. |
| **[preference]** / "a preference" | A value or method the reference authors chose that the game does not require. The behaviour around it is the requirement; the value is the implementer's to choose (the one that played is given so the fixture can be reproduced). |

### 0.2 Fixed names versus free names

Two kinds of names appear below.

**Fixed by the game or the tools, must match byte for byte.** File format
tokens, entity classnames, key names and their required values,
script-variable names the stock scripts read, prefab asset paths, model
names, command-line switches, environment variable names, output file
names. These are rendered in `code font` and, where a table lists them,
the table heading says "fixed". Do not rename, re-case, or "tidy" them.

**Free.** Every module, type, function, parameter and internal constant
name in the new implementation. Section 0.3 says how to choose them.

### 0.3 Naming rule for the reimplementation

The new codebase must read as its own work, not as a paraphrase of the
reference. Concretely:

1. Do not reuse the reference implementation's module, class, function
   or parameter names. You have not seen them, so this is easy: choose
   the name that fits the design in Section 8, not a generic verb + noun
   that any author would produce for the same operation when a more
   specific name exists.
2. Names that this document assigns in Section 8 (for example
   `Blueprint`, `commit`, `Toolchain`, `StageOutcome`) are the intended
   public names. Use them.
3. Anything this document does not name explicitly follows the same
   spirit: name it after what it is in *this* design (a blueprint
   element, a stage outcome, a surface sample), not after the file
   format token or the game concept when the two differ.
4. The only exception is Section 0.2's fixed set. Where a fixed name is
   also a natural variable name (for example a key called
   `script_noteworthy`), the *string constant* holds the fixed spelling
   and the *variable* holding it is named for its role
   (`zoneMarkerTag`, not `script_noteworthy`).

### 0.4 Coordinate and unit conventions

- World units are inches. Z is up. +Y is "north", +X is "east" in every
  side name used below (south/north/west/east walls).
- A box is written as two corner points, `mins` and `maxs`, with
  `mins <= maxs` on every axis. Implementations must normalise any
  caller-supplied pair by swapping per axis before use.
- Angles are written `pitch yaw roll` in degrees, in that order, as three
  space-separated numbers in one quoted string. Yaw is rotation about Z.
- Floor slabs are conventionally 16 units thick and occupy z from 0 to
  16, so "floor surface" is z = 16 in the recipes below. Nothing in the
  engine requires this; it is the convention that every verified
  placement height in this document assumes.

---

## 1. The map source text format

The Radiant source format is a line-oriented text file, extension
`.map`. The compiler reads it directly; Radiant reads and writes it. All
rules in this section are **[measured]** on real BO3 files unless
tagged otherwise.

### 1.1 Header

Line 1 is the literal `iwmap 4`. Nothing follows on that line.

Line 2 is `"script_startingnumber" 0`: a quoted key, one space, an
unquoted integer. This is the only quoted-key/unquoted-value line in the
whole format.

Then zero or more layer declarations, one per line:

```
"<layer path>" flags <zero or more flag words>
```

Layer paths use `/` as separator (`"000_Global/Zones"`). Observed flag
words: `expanded`, `active`, `hidden`, `ignore`, `prefab`. A trailing
space after `flags` when there are no words is what Radiant writes and
is harmless; emit `"<path>" flags` with no trailing space or with one,
either parses. A layer with the `ignore` flag is skipped by the compiler
**[inherited]**. Layers are cosmetic organisation for Radiant; an entity
may reference a layer that is not declared and the compiler still picks
it up **[inherited]**. Emit the layer table anyway so Radiant opens the
file cleanly. A minimal table that real files use is two lines,
`"000_Global" flags expanded active` and `"The Map" flags expanded`
**[measured]**; declare sub-layer paths only when entities reference
them. Entity `layer` lines (Section 1.2) are optional; when present the
value should be a declared path.

Layer lines of the form `"_prefabs/<path>.map" flags prefab` appear in
the reference implementation's output and in no public BO3 map
**[unverified]**. They are not required for prefab loading (prefabs load
through `misc_prefab` entities, Section 1.7). Emitting them is harmless
**[played]**; omitting them is the cleaner default.

### 1.2 Entity blocks

After the header, the file is a sequence of entity blocks:

```
// entity N
{
guid "{UUID}"
layer "<layer path>"
"key" "value"
...
// brush 0
{
...
}
}
```

Rules:

- `// entity N` precedes every entity; N counts from 0 in file order.
  The writer renumbers on save; the reader ignores the number.
- Braces are at column 0 for entity blocks.
- `guid "{UUID}"` is the first line inside the braces of every BO3
  entity and every BO3 brush. The UUID is upper-case hexadecimal, braced,
  in the 8-4-4-4-12 form. Generate a fresh random UUID for every entity
  and brush you create. The key `guid` is unquoted; the value is quoted.
- `layer "<path>"` is optional, unquoted key, quoted value, and comes
  before the key/value pairs.
- Key/value pairs are `"key" "value"`, both quoted, one per line, no
  indentation. Values are always strings, even when they are numbers or
  vectors: `"origin" "546 588 0"`, `"zombie_cost" "950"`. Keys are
  case-sensitive as far as the scripts are concerned; some Radiant
  templates write upper-case keys (`"SPAWNER"`, `"MAKEROOM"`) and those
  are reproduced as-is.
- `"classname"` is conventionally the first pair. Order of the rest is
  not load-bearing.
- Brushes owned by the entity are nested inside its braces, each
  preceded by `// brush M`, M counting from 0 **per entity**.
- Entity 0 is `worldspawn` and owns all static geometry.

A reader must accept values containing backslash escapes and must not
choke on blank lines or on indentation variations inside brush blocks
(Radiant indents brush bodies by one space, some tools by none).

### 1.3 Worldspawn keys

A top-level zombies map's worldspawn carries at least these keys
**[played]**, values as shown unless the mapper chooses otherwise:

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
"numOmniShadowSlices" "24"
"numSpotShadowSlices" "64"
"sky_intensity_factor0" "1"
"sky_intensity_factor1" "1"
"state_alias_1" "State 1"
"state_alias_2" "State 2"
"state_alias_3" "State 3"
"state_alias_4" "State 4"
```

Real shipped maps use `"lightingquality" "4096"` and a map-specific
`lutmaterial`. The `ssi`/`wsi` value must name a shipped sun/weather
preset; `default_day` is one, and the sun volume (Section 4.11) repeats
the same preset name.

A prefab file's worldspawn needs only `classname`, `fsi`, `gravity`, the
two `sky_intensity_factor` keys and the four `state_alias` keys
**[played]**.

### 1.4 Brush blocks and the plane triple

A brush is a convex solid defined as the intersection of half-spaces,
one per face line:

```
// brush M
{
 guid "{UUID}"
 contents detail;
 ( x1 y1 z1 ) ( x2 y2 z2 ) ( x3 y3 z3 ) <material> n1 n2 n3 n4 n5 n6 <lightmap> m1 m2 m3 m4 m5 m6 [trailing tokens]
 ...
}
```

- One leading space before `(` and before `guid` is Radiant's style;
  parsers must accept zero or more.
- `contents <tokens>;` is optional, one line, after `guid` and before
  the faces. Absent on ordinary solid geometry.
- Each face line is three points then the texture block.

**Winding [measured on 25/25 real brushes]:** for points A, B, C in the
order written, the normal `n = (B - A) x (C - A)` points **into** the
solid. The solid is the set of points p with `n . p >= n . A` for every
face. This is the reverse of the Quake convention. Under the outward
reading, 0 of 25 real brushes enclose any volume, so a generator that
gets this wrong produces geometry that closes under no interpretation.

Nothing constrains the trio to sit on brush corners, to land on whole
numbers, or to line up with an axis. Any three points on the plane will
do, provided they are not collinear and appear in the correct order.
Corner points are still the sensible pick for a generator, since they
are exact in this format and simple to verify.

### 1.5 Texture fields

The tail of a face line is:

```
<material> n1 n2 n3 n4 n5 n6 <lightmap_material> m1 m2 m3 m4 m5 m6
```

| Field | Meaning | Tag |
|---|---|---|
| `<material>` | Material asset name, case-sensitive, no path. | measured |
| n1, n2 | Horizontal and vertical texture size in world units per repeat. Negative mirrors that axis. | partially verified: values are size-like in every real file; no primary doc names the field |
| n3, n4 | Horizontal and vertical shift in world units. | measured on adjacent faces |
| n5 | Rotation in degrees. | measured (0/90/-90/180 on rotated faces) |
| n6 | Unknown. Zero on every axis-aligned face. Emit `0`. | unverified |
| `<lightmap_material>` | Always `lightmap_gray` in every file read. | measured |
| m1..m6 | Same six fields for the lightmap projection. Defaults `16384 16384 0 0 0 0`. | measured |

**Generator rule:** emit `<material> 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0`
for every face unless the caller asks for a texture size. That string is
what Radiant writes for an untouched face and appears thousands of times
across the corpus. Allow per-face material override; keep the numeric
tail fixed unless a caller explicitly supplies all six.

Optional trailing tokens, after m6, seen in real files and to be
preserved verbatim by a reader:

- `smoothing <group name>` (older-engine files, not seen in BO3).
- `decalLayerSort "<layer name>" decalEditorSort <int>` (BO3, per face).

A reader must carry any unrecognised trailing tokens through unchanged.
A writer never invents them.

### 1.6 Contents flags

`contents <tokens>;` tokens are space-separated, the line ends in `;`,
and spelling is case-sensitive:

| Token | Verified where | Effect (as used) |
|---|---|---|
| `detail` | BO3 zone volumes and decorative brushes | Brush does not split the BSP. Put it on zone-volume brushes and on any brush that is not part of the sealed hull. |
| `nonColliding` | BO3 chalk-outline meshes | No collision. |
| `umbraTarget` | BO3 | Occlusion-culling hint. |
| `weaponClip` | 19,553 occurrences in the 733 shipped `.map` files, every one on a `contents` line **[measured]**; the counts and the combinations live in the format reference's contents table | Blocks bullets, and **replaces** the default solid contents rather than adding to it, so a face carrying it is not walkable. Never emitted on terrain: Section 3.2 retracted the collision twin. |
| `ai_nosight` | 7,044 occurrences in the same files, 5,253 of them in `contents weaponClip detail ai_nosight;` **[measured]** | Blocks AI sight. Do not put it on walkable floor patches (Section 3.5). |

### 1.7 Prefab references

An entity with `"classname" "misc_prefab"` and `"model" "<path>"` pulls
another `.map` file into this one at `origin`/`angles`. The path is
relative to `map_source/` and uses forward slashes:
`"model" "_prefabs/zm/zm_core/vending_juggernaut_struct.map"`. Radiant's
own definition file states this path base **[stock-source]**.

The compiler's entities-only mode does **not** re-read per-map prefab
files (Section 7.3) **[inherited]**; anything the caller wants to iterate
on quickly must live in the top-level map.

### 1.8 Patch primitives (`mesh` and `curve`)

A patch lives inside an ordinary `// brush M { ... }` container, with the
primitive keyword replacing the face list:

```
// brush M
 {
  guid "{UUID}"
  mesh
  {
layer "<layer path>"
  contents <tokens>;
  toolFlags;
   <material>
   <lightmap_material>
   W H T1 T2
   (
	v X Y Z t U V Lu Lv
	...   (H lines)
   )
   ...   (W groups)
  }
 }
```

Inner block order is fixed: optional `layer "<path>"`, then optional
`contents ...;`, then `toolFlags;` (bare, with the semicolon), then the
render material, then the lightmap material (`lightmap_gray`), then the
dimension line, then W parenthesised groups of H vertex lines each.
Only `guid` may stand between the container brace and the keyword
**[measured, 22,795 shipped patch containers]**: a `layer`
line there is parsed by `cod2map64` as a face brush and the compile stops
with `MatchToken: got 'mesh', expected '('`. A patch's layer line goes
first inside the inner block, at column 0, which is where Radiant writes
it **[measured, 328 of 328 layered shipped patches]**. Indentation: three spaces before the
material lines and the parentheses, a tab before each `v` line, is what
Radiant writes; readers must tolerate any whitespace.

- `W` = number of vertex groups (outer index). `H` = vertices per group
  (inner index). **[measured by counting a real 9 3 curve]**
- `T1`: `0` on every real `mesh`, `16` on every real `curve`. Consistent
  with a curve subdivision count **[unverified mapping]**. Emit `0` for
  mesh, `16` for curve.
- `T2`: `8` on real meshes and on most curves; `1` and `6` also seen.
  Emit `8` **[unverified meaning]**.
- Vertex line: `v X Y Z t U V Lu Lv`. `U V` are texture coordinates,
  large world-projected numbers in real files; `Lu Lv` are lightmap
  coordinates, small. The literal `t` separates position from UVs.
- `mesh` is flat-triangulated; `curve` is quadratic-Bezier smoothed over
  3x3 windows **[inherited, consistent with all real curves having odd
  dimensions]**. Use `mesh` for terrain and `curve` for arches.
- An optional per-vertex colour `c R G B A` between Z and `t` appears in
  a stock prefab copied by the reference implementation, in no public
  file **[unverified]**. Only emit it if implementing blend materials,
  and mark the feature experimental.
- `decalLayerSort "<name>"` / `decalEditorSort <int>` as trailing lines
  inside the patch body: same status, **[unverified]**, do not emit.
- Shipped maps wrap a capped `curve` (an arch with end caps) in a
  `func_group` entity carrying `"type" "patchCapped"` **[measured on two
  real files]**. Whether a bare `curve` directly inside `worldspawn`
  compiles is **[unverified]**; a generator emitting arches should use
  the group form. `mesh` blocks for terrain go directly into
  `worldspawn` **[inherited, compiled]**.

**Surface orientation [inherited, from two failed and one successful
playtest]:** the visible side of a patch is determined by the order of
the control grid. For a floor that must be visible from above, the outer
index must increase along +X and the inner index along +Y. A grid with
outer along Y and inner along X, or with either index decreasing, renders
only from below. A generator must normalise any caller grid to
"outer increases in +X, inner increases in +Y" for floors, and reverse
exactly one index for ceilings. Vertical wall ribbons follow the same
rule with the normal `(row direction) x (column direction)` pointing
into the play area.

**Texture coordinates for generated patches [preference]:** real files
carry world-projected texture coordinates (U tracks world X, V tracks
world Y with the sign flipped, both scaled). Any consistent planar
projection of a control point's XY onto (U, V) compiled and rendered
**[inherited]**; the scale factor is the implementer's choice (a value
that makes one texture repeat span a few cells reads well). Lightmap
coordinates only need to increase monotonically along each grid index;
small integers are fine. None of these values is load-bearing for the
compile; they only affect texture appearance.

**Caulk on a patch is wrong [inherited, compiler warning quoted]:** the
compiler prints a banner containing `terrain patches with caulk were
discovered` and the patch renders black in-game. Use a real material on
collision twins too.

### 1.9 Number formatting

Every number written into a `.map` is plain decimal: an optional minus
sign, digits, an optional fractional part. **Never exponent notation.**
None of the real BO3 maps read for the format reference contains an
exponent; Radiant writes
`-1536`, `71.964066`, `2.4000502`. **[measured]**

Rules for the writer:

1. Format with fixed-point at 8 fractional digits, then strip trailing
   zeros and a trailing dot. `16.0` becomes `16`; `65536.25` stays
   `65536.25`.
2. Any value whose formatted form is `-0` or empty becomes `0`. This
   collapses floating-point noise such as `sin(pi) * 100 = 1.22e-14`,
   which arrives whenever a wall is generated on a zero coordinate.
3. Do not use shortest-representation or `%g`-style formatting: `%g`
   both writes `1e-05` and rounds to six significant digits, turning
   `65536.25` into `65536.2`. **[measured on the reference
   before its fix]**
4. Integers must round-trip byte-identically (an integer input produces
   the same digits out).

Whether the compiler would parse an exponent is unknown; the rule exists
because the format has never been observed to contain one, and the cost
of finding out is a broken build with no diagnostic.

### 1.10 Line endings and encoding

Write `.map` files with LF line endings and UTF-8 (they are ASCII in
practice). When editing an existing file, preserve whatever line ending
the file already uses, per line. The same rule applies to `.gsc`/`.csc`
(Section 5), which the original authors shipped with CRLF endings.

### 1.11 Reader contract

A reimplementation needs a reader as well as a writer, because callers
will inspect and mutate maps they generated earlier, and because the
conformance checks (Section 9) parse emitted files.

Required reader behaviour:

- Parses header, layer table, entities, key/values, `guid`, `layer`.
- Parses brush faces structurally (three points, material, twelve
  numbers, trailing tokens kept as an opaque string).
- Parses `mesh`/`curve` patches structurally (contents, material,
  lightmap, dims, control grid with optional colour and the four UVs).
  Note the nested brace: a patch block opens an inner `{` after the
  keyword, so a brace-depth counter is needed to find the end of the
  container.
- Round-trip property: parsing a file the writer produced and writing
  it again yields byte-identical output. Parsing a foreign (Radiant)
  file and writing it back must preserve every entity, key, brush and
  patch, and must preserve unknown trailing tokens; whitespace and the
  brush/entity numbering may be normalised.
- A brush body that does not parse (unknown primitive) is kept as opaque
  text and written back unchanged, with a warning in the parse report.
  Never drop geometry silently.

---

## 2. Brush geometry

### 2.1 Axis-aligned box: six faces with correct winding

Given normalised `mins = (x0, y0, z0)` and `maxs = (x1, y1, z1)` with
strict inequality on every axis, emit six faces, one per plane `x = x0`,
`x = x1`, `y = y0`, `y = y1`, `z = z0`, `z = z1`. The inward normal of
each is the unit axis vector pointing from that plane toward the box
centre (`+X` for `x = x0`, `-X` for `x = x1`, and so on).

For the three points of a face, take any three distinct corners of that
face (for example the face's lowest corner and its two edge neighbours)
and pass them through a general `orient_inward(A, B, C, inward_normal)`
that computes `(B - A) x (C - A)`, takes its dot product with the
requested inward normal, and swaps B and C when the dot product is
negative (raising when it is zero: collinear points, or a plane
perpendicular to the requested normal). Use it for every face of every
primitive. Do not hand-write a per-face point order; the orientation
check is the source of truth and the Section 2.8 checker is its test.

Test vectors on the unit box `(0,0,0)`-`(1,1,1)`:

- bottom face, points `(0,0,0) (0,1,0) (1,1,0)`: cross product
  `(0,0,-1)`, outward for `z = 0`, so the emitted order is
  `(0,0,0) (1,1,0) (0,1,0)`;
- face `x = 1`, points `(1,0,0) (1,1,0) (1,1,1)`: cross product
  `(+1,0,0)`, outward, so the emitted order is `(1,0,0) (1,1,1) (1,1,0)`;
- any face whose three points already give a cross product with a
  positive dot against the inward normal is emitted unchanged.

Reject a box where any axis has `max <= min` with an error naming the
axis. Do not silently emit a zero-thickness brush; the compiler's
behaviour on it is unknown and the reference implementation once crashed
on exactly this (Section 10, item K7).

Per-face material override is required (a floor slab with a visible top
and `caulk` on the other five faces is the common case).

### 2.2 Room with wall thickness (no openings)

Input: outer bounds `mins`/`maxs`, wall thickness `t`, wall/floor/ceiling
materials. Reject if any outer extent is `<= 2t` (the interior would be
empty).

Decompose the shell into six non-overlapping boxes whose union is the
outer box minus the interior void (Section 9.2, G4, checks exactly that;
any decomposition with that property is acceptable). One valid choice:

- floor: `(x0, y0, z0)` to `(x1, y1, z0 + t)`
- ceiling: `(x0, y0, z1 - t)` to `(x1, y1, z1)`
- south wall: `(x0, y0, z0 + t)` to `(x1, y0 + t, z1 - t)`
- north wall: `(x0, y1 - t, z0 + t)` to `(x1, y1, z1 - t)`
- west wall: `(x0, y0 + t, z0 + t)` to `(x0 + t, y1 - t, z1 - t)`
- east wall: `(x1 - t, y0 + t, z0 + t)` to `(x1, y1 - t, z1 - t)`

Floor and ceiling span the full footprint; south/north span the full X
extent between floor and ceiling; west/east are inset by `t` in Y so they
butt against the south/north walls without overlapping them (insetting
the other pair instead is equally valid). The interior void is `(x0+t, y0+t, z0+t)` to `(x1-t, y1-t, z1-t)`; return it,
because that is where entities may be placed.

An open-air variant (no ceiling) omits the ceiling box and runs the four
walls up to `z1`. It only makes sense inside a sky shell (Section 2.7).

**Face materials [inherited, fixes the "walls render as sky" symptom]:**
on each of the six boxes, only the face that looks into the room carries
the visible material; the other five carry `caulk`. Floor: top face.
Ceiling: bottom face. South wall: its north face. North wall: south face.
West wall: east face. East wall: west face. The mechanism is not
understood; the observation is that with the same visible material on
both sides of a hull brush the interior face rendered as the skybox. Make
this the default and allow a caller to request all-visible faces.

### 2.3 Openings (doorways and windows)

An opening is specified per wall side as: width (extent along the wall),
height (Z extent), centre offset along the wall from the wall's midpoint
(default 0), and sill height above the *interior floor surface*
(default 0 = doorway; `> 0` = window).

Validation: sill `>= 0`; sill + height `<= wall height` (wall height is
the interior height, `z1 - z0 - 2t`, or `z1 - z0 - t` for the open-air
variant); width `<= wall length`; the opening's along-wall span must lie
within the wall's span. Report which constraint failed.

Required result for a wall with N openings: a set of non-overlapping
boxes whose union equals the wall box minus the union of the opening
boxes (G5 checks this; any decomposition with that property is
acceptable). One valid method is a sweep along the wall axis with the
openings sorted by their low edge:

1. A full-height fill from the wall's low end to the first opening's low
   edge, if that span is positive.
2. For each opening: a strip **below** it (from the wall's bottom to the
   sill) and a strip **above** it (from the opening's top to the wall's
   top), each spanning exactly the opening's along-wall range. Either
   strip is omitted when its Z extent is zero.
3. A full-height fill between consecutive openings, if positive.
4. A full-height fill from the last opening's high edge to the wall's
   end, if positive.

All pieces share the wall's thickness range. Drop any piece with a
non-positive extent on any axis. Overlapping openings on the same wall
are a caller error; reject rather than emit overlapping fills.

Face materials on opening pieces: **all six faces visible**. The player
sees the jambs, sill and lintel when walking through, and caulk there
showed as a sky-coloured streak **[inherited]**.

Two openings whose along-wall ranges touch produce adjacent, not
overlapping, pieces. Two rooms sharing a wall plane both contribute a
wall there (16 units each, back to back); that is acceptable and plays
**[played]**. A cleaner generator may offer a
"shared wall" mode that emits the wall once, but nothing requires it.

### 2.4 Standalone wall with a hole

Same sweep as Section 2.3 applied to a single caller-supplied box (the
wall) and a caller-supplied opening box. The wall's thickness axis is
either given by the caller or, by default, taken as the axis of smallest
extent (a preference); the opening must span the wall fully on that axis
and lie within the wall on the other two. Emits up to four
pieces (left, right, below, above). It does not delete any pre-existing
wall brush; it is for building walls one at a time.

### 2.5 Stairs

Input: base corner (the bottom of the first riser, at the low-Z, low
along-axis corner), step count `n`, step depth `d`, step height `h`,
step width `w`, ascending direction one of `+x`, `-x`, `+y`, `-y`.

Emit `n` non-overlapping boxes. Step `i` (0-based) occupies the
along-axis slice from `i*d` to `(i+1)*d` measured from the base in the
ascending direction, the full width `w` perpendicular to it, and Z from
the base to `base_z + (i+1)*h`. Each step is a full column down to the
base, so the flight is solid underneath with no overlaps between steps.

(The reference implementation makes each step also cover the volume of
all previous steps, producing `n` mutually overlapping boxes. The
compiler tolerated it, but overlapping structural brushes are what the
conformance checker flags, so do not reproduce that.)

Step height 8 with depth 16 are the defaults the reference authors used
and report as climbable **[inherited, preference]**; the engine's true
step limit is not documented here (Section 3.1). Zombie AI does not
climb tall single steps; for a walkable grade prefer a ramp.

### 2.6 Ramp (wedge)

Input: a box `mins`/`maxs` and a rise direction (`+x`, `-x`, `+y`, `-y`).
The solid is the half of the box below a plane that passes through the
box's bottom edge on the low side and its top edge on the high side.
Five half-spaces bound it:

- the box's bottom plane (inward +Z);
- the box's two planes parallel to the rise axis (inward toward the
  centre);
- the box's end plane on the **high** side (inward toward the low side);
- the slope plane itself, containing the low-side bottom edge (at `z0`)
  and the high-side top edge (at `z1`). For rise `+x` this plane contains `(x0, *, z0)` and `(x1, *, z1)`;
  its inward normal is proportional to `(dz, 0, -dx)` where
  `dx = x1 - x0`, `dz = z1 - z0`. For `-x` it is `(-dz, 0, -dx)`; for
  `+y`, `(0, dz, -dy)`; for `-y`, `(0, -dz, -dy)`.

The low end has no vertical face (the slope meets the bottom there). Pass
every triple through `orient_inward`; do not hand-wind the slope. Check
numerically (Section 2.8) that the five half-spaces enclose a non-empty
solid whose volume equals `w * L * H / 2`.

### 2.7 Exterior shell, yard, and the "void" problem

**Sky shell [inherited, required by the compiler when an umbra volume is
present, error text quoted: "When an Umbra brush is present the map must
be sealed by an outer skybox."]:** six slabs of material `sky`
surrounding the playable bounds expanded by a gap `g`, with slab
thickness `s`. The values that played were `g = 128`, `s = 32`; both are
preferences. The gap must exceed the reach of anything a prefab places
outside a wall (about 50 units for a barricade, Section 4.6). With inner
bounds
`I = playable ± g` and outer bounds `O = I ± s`:

- bottom: `(Ox0, Oy0, Oz0)` to `(Ox1, Oy1, Iz0)`
- top: `(Ox0, Oy0, Iz1)` to `(Ox1, Oy1, Oz1)`
- south: `(Ox0, Oy0, Iz0)` to `(Ox1, Iy0, Iz1)`
- north: `(Ox0, Iy1, Iz0)` to `(Ox1, Oy1, Iz1)`
- west: `(Ox0, Iy0, Iz0)` to `(Ix0, Iy1, Iz1)`
- east: `(Ix1, Iy0, Iz0)` to `(Ox1, Iy1, Iz1)`

Any six-slab cover of the shell without overlap is acceptable (G7); the
one above is one choice. The shell makes the void
around the map finite, which matters because barricade prefabs place
entities outside the wall they are mounted on (Section 4.6) and an
entity in unbounded void makes the compiler report a leak. `caulk`
instead of `sky` seals the leak but does not establish the world boundary
the renderer needs **[inherited]**; use `sky`.

**Yard (courtyard) [inherited, mandatory beside every barricade
window]:** a five-sided pocket outside a room wall, where risers stand.
Input: bounds, wall thickness `t`, and the side that touches the room
(that side gets no wall). Emit floor and ceiling slabs over the full
footprint and three walls. In the vocabulary of Section 2.2: floor and
ceiling as for a room; the wall opposite the open side spans the full
footprint on its axis; the two walls flanking the open side span from
the closed wall's inner face **to the open edge**, not to
`open edge - t`. If they stop `t` short (as an inset wall pair would to
leave room for a wall that is not there) a `t x t` vertical slot is left
at each corner, opening the yard into the void **[measured:
flood fill escaped through the slot before the fix]**. Face materials
follow Section 2.2 (visible face inward, the rest `caulk`); the yard is
seen through the window boards, so give it real materials. Depth
(perpendicular to the open side) must be at least 144 **[inherited]**:
with the riser 96 units out (Section 4.6) and a 16-unit far wall that
leaves 32 units of floor beyond the riser. Anything larger is fine (176
played).

### 2.8 Detecting bad brushes

A brush is a set of planes `{(n_i, d_i)}` with the solid
`{p : n_i . p >= d_i}` under the inward convention. Compute, per brush:

1. **Vertices.** Take each triple of planes whose normal matrix is
   non-singular and solve it for a point; a point survives only if it
   sits inside every half-space to within 1e-3 units. Survivors sharing
   a 1e-3 grid cell collapse into one vertex.
2. **Inverted**: rerun the vertex solve with all normals negated. When
   the inward reading yields nothing and the outward one yields
   something, the face points were written in the wrong rotational
   order. Error.
3. **Unused plane**: if fewer than three surviving vertices sit on a
   plane, that plane bounds no part of the finished solid, which means
   the brush was given more planes than its shape needs. Warning.
4. **Degenerate**: under four planes, or under four distinct surviving
   vertices. Error.
5. **Zero volume**: build each plane's polygon (sort its vertices
   rotationally about the normal, fan-triangulate, then add up the
   signed tetrahedra taken to the centroid) and total the result.
   Anything under 1 cubic unit is an error.
6. **Non-convex**: there is nothing here to test. Intersecting
   half-spaces can only ever bound a convex body, so a caller who wants
   a concave shape has to be handed a set of brushes instead of one.
7. **Overlap**: for pairs of *structural* world brushes (no `detail`
   contents, owned by worldspawn, not sky/tool materials) whose bounding
   boxes interpenetrate by more than 1 unit on all three axes, run a
   separating-axis test on the two convex hulls (face normals of both
   plus cross products of edge pairs). Interpenetration is a warning:
   Radiant allows it, but it is the classic source of BSP splits and
   z-fighting, and none of the generators in this document need it.
8. **Entity in solid / over void / floating**: for each placed entity
   with an origin, error if any world solid contains the point by more
   than 2 units; error if no world solid has a top surface under the
   point within a 16-unit radius; warning if the nearest top surface is
   more than 96 units below it.

For axis-aligned boxes steps 1-5 reduce to `mins < maxs` on every axis
and the winding table; still run the general check on the emitted text
in tests, because the text is what the compiler reads.

### 2.9 Materials

A material name that is not in the asset database compiles with the
warning `WARNING: Material '<name>' is missing` and renders as the
engine's error texture **[measured]**. The compile still
succeeds (exit code 0), so this must be surfaced from the log.

Keep a catalogue of material names known to compile clean, tagged by the
build in which each was last seen to compile without that warning. The
catalogue is data, not code; the names below are game asset names
(fixed):

Concrete/brick/wood/plaster/metal/glass/tile/snow walls and floors
verified on shipped map sources include `t7_concrete_trowelled`,
`t7_concrete_wall_dark_01`, `t7_concrete_pebbles_cracked`,
`t7_concrete_tiles_2x2_dirty_01`, `t7_brick_worn_heavy_grout_red`,
`t7_wood_planks_worn`, `t7_metal_worn_iron_dark`,
`t7_metal_rust_ceiling_01`, `t7_zm_der_tile_hexagon`,
`t7_dirt_grassy_forest_ground`, `t7_rock_sand_crumbled_medium_golden`,
`t7_snow_powder_01`. Tool materials: `caulk`, `clip`, `trigger`, `sky`,
`umbra_volume`, `sun_volume`, `volume`.

Known-missing despite appearing in a stock prefab: `jun_art_wood_plywood_dark03`
(the starting mystery-box prefab references it; the warning appears
three times in every compile that includes that prefab and is benign)
**[measured]**. Do not offer that name.

Wall-buy chalk materials (`t7_zm_chalk_buy_kuda` and siblings) are used
on `misc_volume_decal` entities via the `modeloverridematerial` key, not
on brush faces.

---

## 3. Terrain

A heightfield is a rectangular grid `H[row][col]` of heights in world
units above a base `oz`, anchored so that grid cell `(col, row)` covers
world x in `[ox + col*c, ox + (col+1)*c]` and y in `[oy + row*c, oy +
(row+1)*c]` for cell size `c`. Rows advance along +Y, columns along +X.

A heightfield that is a room's ground is anchored and spaced from that
room's **interior**, not from the numbers the caller wrote, so the mesh
meets every wall: a grid stepped out as "anchor plus N cells" stops
wherever the arithmetic runs out, and the strip left over has no ground in
it at all (measured: a mesh stepped out that way stopped 8 units short of
one wall of its room and 24 short of the other, and 37 props placed on the
terrain over the missing strips hung 55 to 70 units in the air). Fitting keeps the row and
column count it was given, so a room that is not square needs one spacing
per axis and `c` becomes `cx` along +X and `cy` along +Y; the terrain
record carries the second only when it differs. A field that reaches no
closer than one cell to the walls is a patch of ground inside a room, not
the room's floor, and is left where it was put.

Two representations exist. Both compiled and played on the reference's
earlier maps **[inherited]**; the mesh one is what the reference now
defaults to.

### 3.1 Column ("blocky") representation

One box per cell: `(ox + col*c, oy + row*c, oz)` to
`(ox + (col+1)*c, oy + (row+1)*c, oz + H[row][col])`. Skip cells with
height `<= 0` (or `<= skip threshold`).

Optional strip merging: walk each row, group consecutive cells whose
heights round to the same integer, emit one box per run. **A run whose
rounded height is `<= 0` must be skipped**, not emitted as a zero-height
box (Section 10, item K7). The reference authors report 30-60% fewer
brushes on smooth data after merging **[inherited]**.

Optional height bands: a list of `(top_z, material)` in ascending order;
a cell takes the material of the first band whose `top_z` is `>= ` the
cell's top. A brush budget must be enforced with a clear error before
any file is written; the limit is a preference (the compiler's own
limit is unknown, **[unverified]**; a few thousand compiled).

Stock precedent: Treyarch's own terrain test map is 1489 box brushes on
128-unit cells **[inherited]**. So columns are a legitimate look, not a
defect.

**The pathing problem [inherited]:** zombie AI paths over a navmesh the
compiler generates from walkable surfaces. Adjacent columns with a
height step larger than the AI can step (exact threshold unknown,
**[unverified]**; 8 units is safe, 32 is not) split the navmesh, and
zombies stop at the edge or walk in place. Post-processing the
heightfield (clamping, smoothing, flattening the low fraction of cells,
feathering the edges) reduces how often this happens but cannot remove
it, because the surface is still piecewise constant. Prefer the mesh
representation for anything zombies must cross.

### 3.2 Mesh ("smooth") representation

Each grid value becomes a control point rather than a cell, at
`(ox + col*c, oy + row*c, oz + H[row][col])`. N values therefore span
only `(N-1)*c` of world space, one cell short of the column footprint on
the high-X and high-Y sides. To give the mesh the same footprint as the
column form and as the room the terrain fills, **duplicate the last
column and the last row** before meshing (N+1 control points spanning N
cells). The duplicated edge forms a flat one-cell border.

Chunk the padded grid into patches of at most `k+1` control points per
side, adjacent chunks sharing their edge control points so there are no
seams. `k = 8` (9x9 control points) is a preference that compiled; the
engine's per-patch limit is **[unverified]** and real files have patches
up to 9 on a side, so stay at or below that until a larger one is
tested. Walk chunks with X outermost. Within a chunk build
the control grid with the **outer index along +X and the inner index
along +Y** (Section 1.8 orientation rule).

Emit **one** `mesh` block per chunk, appended to `worldspawn` like any
brush, with **no `contents` line at all** and the visible material. That
is what makes it solid: `contents solid` appears **zero** times in the
shipped `.map` files, because solid is the default and is never
written **[measured]**. (The format reference defines that corpus; its file
count varies slightly by install.) In
`_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map` the walkable base
layer is 172 meshes with no `contents` line, while its 129 decorative
alpha-blend overlays opt *out* with `contents nonColliding;`.

**No collision twin. This is the single statement of the rule; T2,
lesson E9 and the terrain checks point here.** An inherited claim calls for a
second, coincident mesh per chunk carrying `contents
weaponClip detail;` as a "collision twin", on an inherited claim that it
"gives a walkable, bullet-stopping surface the navmesh generator uses".
It does not: `weaponClip` **replaces** the default contents rather than
adding to it, so a chunk that carries it is not solid, and a map built that
way lets the player fall through the outdoor ground and get stuck underneath
it. Emit the single mesh.

The shipped terrain file says where solidity comes from. Counting all 377
patch blocks in
`_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map`
**[measured]**: 172 carry no `contents` line at all -- that is
the walkable base -- 129 opt out with `contents nonColliding;`, and 76
carry `contents weaponClip detail ai_nosight;`.

One supporting claim is too strong: that all 76 carry blend or drywall materials, "never the
walkable ground". Their materials are 30 `t7_drywall_painted_metallic_black`,
20 `t7_sand_pebbles_fine_golden_blend`, 11
`t7_rock_sand_crumbled_large_golden_blend`, and single figures of decals,
wood, concrete and `t7_dirt_grassy_forest_ground` -- and the base layer
uses the sand and concrete materials too, so the material does not
separate the two sets. Whether any of the 76 is geometrically coincident
with a base patch is **[unmeasured]**; this document does not claim
Treyarch never lays a `weaponClip` patch over ground. It claims the
narrower measured thing, which is the one that matters for emitting:
solidity comes from the no-`contents` block, and a chunk emitted *only*
as a `weaponClip` twin is walked through.

Relatedly, `weaponClip` and `ai_nosight` are real and common contents
tokens in BO3 `.map` files. The count and the source of truth live in the
format reference's contents table (`mapsource-format-reference.md`);
briefly, 19,553 and 7,044 occurrences, every one on a `contents` line,
across the 733 shipped `.map` files under `map_source/`
**[measured]**.

Lift the whole heightfield by a small offset (a preference; 2 units
played) when the mesh sits on top of a room's floor slab, so flat cells at floor height do not
z-fight with the slab. Record the lift in the terrain record (Section
3.4) so height lookups include it.

Patches are one-sided; the underside is open, and a mesh is a surface
rather than a volume, so **a heightfield with nothing under it is void**.
Fill it, and follow the heightfield rather than laying one flat slab
under the lowest point: a flat slab under a hill leaves a pocket a
player can stand in, which is the same bug one unit lower. One
`contents detail;` caulk box per grid cell, its top at the lowest of the
cell's four corners, leaves a wedge no taller than the cell's own fall.

The shipped maps do the same thing at map scale:
`_prefabs/zm/zm_giant/zm_giant_geo.map` line 6008 is one caulk block
spanning x -7776..6680, y -10624..8880 down to z -288, about 1300 units
below its lowest visible floor **[measured]**.

They also put a **floor of last resort under the whole map**, which this
spec did not previously mention and which every generated map should
carry. A `trigger_hurt` brush volume: six occurrences across the
shipped `.map` files, two each in `zm_giant_geo.map`, `mp_sector_geo.map`
and `mp_combine_geo.map`, always a floor slab plus a ceiling slab, always
faces of material `trigger`. `zm_giant_geo.map` entity 2 verbatim:

```
"classname" "trigger_hurt"
"dmg" "1000"
"_color" "1 0.3 0.1"
"script_hazard" "false"
```

`mp_sector_geo.map` uses `"dmg" "10000"`. Killing is the shipped
behaviour, not teleporting, and it is engine-side: `share/raw/scripts`
has no fell-out-of-world handler at all, the engine raises
`MOD_TRIGGER_HURT` and the scripts only react to it
(`shared/ai/zombie_utility.gsc:2543`). MP additionally carries
`trigger_out_of_bounds` volumes with faces of `clip_out_of_bounds`; no
zombies map does.

The compiler prints `building curve/terrain collision...` when it
accepts a patch **[inherited]**; absence of that line with patches in
the map means the format was rejected.

**Open question, terrain lightmap resolution [unverified].** A mesh needs
nothing extra to receive the bake: it carries the same `lightmap_gray`
token a brush face does, with the lightmap coordinates moved onto the
vertices as the second UV pair (`v X Y Z t U V Lu Lv`), which is what the
generator emits. But the *scale* of that pair does not match the shipped
maps. `zmforge.surfaces.patches.lightmap_uv` returns the grid indices
themselves, so Lu and Lv run 0..8 across a chunk, on this document's own
note that "only monotonic growth along each index is needed; small
integers are fine". Measured over the first 4000 vertices of
`_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map`, Treyarch's run
Lu -37.5..1430 and Lv -194..91 — hundreds of units, not single digits,
and not a normalised 0..1 either.

Whether that costs the terrain its lightmap resolution is **not
established**: the units are unknown, and a bake of the generated map did
produce a 1.36 MB `.led`. It is recorded here rather than changed because
guessing at the convention could lose the terrain bake altogether, which
is worse than the present state. Resolving it wants one experiment: bake
the same terrain twice, once with index UVs and once with UVs scaled like
the shipped ones, and compare.

### 3.3 Heightfield filters (optional)

The reference authors found these standard filters useful on noisy
sources. Each is optional and a no-op at its default; the set and the
order are a preference, not a requirement. If several are offered,
apply them to heights already in world units and document the order.
The order below is the one the reference used **[inherited]**:

1. **Broken floor**: compute the height at the `(1 - coverage)` quantile;
   every cell below it becomes the flat floor height; only the top
   `coverage` fraction stays raised.
2. **Clamp**: every cell `min(h, h_max)`.
3. **Smooth**: `k` passes of a five-point average (cell plus its four
   edge neighbours), interior cells only.
4. **Edge feather**: with `f = round(feather_units / c)` cells, a cell at
   grid distance `d < f` from the boundary becomes
   `floor + (h - floor) * d / f`.
5. **Flatten pads**: for each pad `(centre, radius, z)`, every cell whose
   centre is within `radius` of the pad centre is set to `z`. Used under
   doorways so the terrain meets the door sill.

After processing, if no cell is above zero, fail before writing anything
and say why (all below sea level; suggest normalising to the local
minimum or adding a floor thickness).

### 3.4 Terrain record (sidecar)

Every terrain emission writes a JSON record next to the map source (the
name is free; `<map>.terrain-record.json` is suggested, or embed it in
the blueprint file of Section 8) containing: grid origin `(ox, oy, oz)`,
cell size, the processed heightfield (including any lift, and **before**
the one-row/one-column duplication of Section 3.2; the lookup's index
clamping reproduces the border), the representation (`columns` or
`mesh`), and the generation parameters. Later placements
read this record to sit entities on the surface without re-generating.
The record is per map and is overwritten on regeneration.

### 3.5 Ground-height lookup

Input: world `(x, y)`. Let `u = (x - ox) / c`, `v = (y - oy) / c`,
`col = floor(u)`, `row = floor(v)`. **Use floor, not truncation toward
zero**: a point up to one cell outside the low edge truncates to cell 0
and is wrongly reported as inside (Section 10, item K6). The point is
inside the footprint when `0 <= col < cols` and `0 <= row < rows`; if
not, return "not found" with `z = oz` and the footprint bounds in the
message.

- **Columns:** `z = oz + H[row][col]`. The column top is flat over the
  whole cell. Measurement put interpolated results as far as 50 units
  away from the brush top the generator actually writes (Section 10,
  item K5).
- **Mesh:** bilinear over the cell's four corner control points. With
  `fx = u - col`, `fy = v - row` clamped to `[0, 1]`, corner heights
  `h00 = H[row][col]`, `h10 = H[row][col+1]`, `h01 = H[row+1][col]`,
  `h11 = H[row+1][col+1]` where indices are clamped to the grid (which
  reproduces the duplicated border of Section 3.2):
  `z = oz + (h00 (1-fx) + h10 fx)(1-fy) + (h01 (1-fx) + h11 fx) fy`.
  The engine actually triangulates each quad; the true surface is two
  planar triangles whose diagonal is unknown **[unverified]**. Bilinear
  matches it exactly on the edges and differs inside by at most
  `|h00 + h11 - h10 - h01| / 4`. Callers placing spawners add a small
  positive offset (4 units) to absorb that.

Also return the local spread `max - min` of the four corners as a
steepness measure; scatter placement uses it.

### 3.6 Placing on terrain

Spawner structs: `z = surface + c` with a small clearance `c` (4 played
on the reference's lab maps **[inherited]**; it also absorbs the
bilinear-versus-triangle error of Section 3.5). Perk machines:
`z = surface` (their prefabs are authored with the origin at the floor).
Scattered props: sink the origin slightly below the surface by an amount
that grows with the local spread and is capped, so a model whose
footprint spans a slope does not float on its downhill side
**[inherited]**; the exact function is a preference (linear in spread
with a cap is enough) and its constants should be exposed. Anything
placed outside the footprint falls back to the room floor height and is
reported.

### 3.7 Heightfield sources

The generator must accept any rectangular float grid. Two built-in
sources are useful:

- Any seeded, deterministic fractal noise (value or gradient noise
  summed over a few octaves) normalised to roughly `[0, 1]`, scaled by a
  caller-supplied maximum height.
- An external terrain model served over HTTP. The reference consumed a
  third-party diffusion model's REST API (`GET /terrain?...` returning
  little-endian int16 elevations in metres, optionally followed by
  float32 climate channels; readiness at `GET /health`; there is no
  `/seed` endpoint, seed is a query parameter, Section 10, item K9). If
  such an adapter is built: validate the payload length against the
  service's documented layout and reject anything else; reject
  non-finite values; treat an all-zero elevation grid as a failure unless
  the caller overrides (it is the signature of a silent server fault);
  convert metres with `z = (m - baseline) * units_per_metre +
  floor_thickness`, where the baseline is the region's minimum when
  normalising (real-world data is mostly below sea level). This source
  is optional in a reimplementation; the heightfield interface is the
  contract.

---

## 4. Zombies gameplay requirements

Everything the stock zombies framework looks up in the map, with the
exact keys. Names in code font are **fixed by the game**. Structs are
entities with `"classname" "script_struct"`; the compiler turns them
into script-accessible structs with their keys as fields.

### 4.1 Player spawns [stock-source, played]

The gametype script reads three things, in this order of preference:

1. Structs with `"targetname" "player_respawn_point"`. Their bounds are
   expanded into the level's spawn bounds and map centre; they are also
   what revive and relocation logic returns.
2. Structs with `"script_noteworthy" "initial_spawn"`, filtered by
   `script_string` (below).
3. Fallback: structs with `"targetname" "initial_spawn_points"`.

`info_player_start` is **never read on the zombies path**. Emitting one
is harmless; relying on it produces a map with no valid spawns
(Section 10, item K1).

Filter: the script builds `match = <gametype> + "_" + <location>`, where
gametype is `zclassic`/`zcleansed`/`zgrief` and location is
`level.default_start_location`, which the framework sets to `start_room`.
It keeps structs whose space-separated `script_string` tokens contain
`match`. A struct that has a `script_string` and does not match is
skipped, so a wrong token yields zero spawns.

Required emission, per map:

One respawn-set struct:

```
"classname" "script_struct"
"targetname" "player_respawn_point"
"script_noteworthy" "start_room"
"script_string" "zclassic_start_room zcleansed_start_room zgrief_start_room"
"script_int" "2000"
"radius" "2000"
"origin" "<x y z>"
"angles" "<p y r>"
```

One initial-spawn struct per player slot, four for a stock game, spread
apart by at least 32 units so two players do not spawn on one point:

```
"classname" "script_struct"
"targetname" "initial_spawn_points"
"script_noteworthy" "initial_spawn"
"script_string" "zclassic_start_room zcleansed_start_room zgrief_start_room"
"radius" "32"
"origin" "<x y z>"
"angles" "<p y r>"
```

Origin Z is the floor surface plus a small clearance (16 above the slab
top was played). A shipped map lists only one gametype token per
initial-spawn struct; listing all three makes one set serve every mode
and matches the respawn struct that shipped map uses. `_color "1 0 0"`
is Radiant decoration and optional.

**Not a slot number (stock-source):** `script_int` 1..4 on these structs,
"one per player slot", is wrong. `script_int` on an initial-spawn struct is the
**team side**, and the slot is the struct's position in the array, which
the framework fills in itself. `zm::getfreespawnpoint`
(`scripts/zm/_zm.gsc:774-810`) deletes candidates by it before handing
one out:

```
if ( isdefined( spawnpoints[ i ].script_int ) && player.team != "allies"
     && spawnpoints[ i ].script_int == 1 )
{ arrayremovevalue( spawnpoints, spawnpoints[ i ] ); i = 0; }
else if ( isdefined( spawnpoints[ i ].script_int ) && player.team == "allies"
     && spawnpoints[ i ].script_int == 2 )
{ arrayremovevalue( spawnpoints, spawnpoints[ i ] ); i = 0; }
```

which of 1 and 2 is dropped is decided per game by `side_selection`, set
from `randomint( 100 ) > 50` a few lines above. Every survival player is
on `allies`, so a set numbered 1..4 loses one member every game.
Shipped `zm_giant.map` carries four `initial_spawn_points` structs with
**no `script_int` at all**; `zm_alien_isolation.map` uses 1 and 2 as what
they are, the two sides of `zcleansed`, four structs each.

`script_int` stays on `player_respawn_point`, where the same file reads
it as the ideal distance to an existing player
(`check_for_valid_spawn_near_team`, `_zm.gsc:3423`), which is why the
shipped value 2000 matches that struct's `radius`.

#### 4.1.1 Player count [stock-source]

**The number of these structs is the only thing in a `.map` that scales
with the player count.** After the team filter, `getfreespawnpoint` ends
(`_zm.gsc:815-831`, paraphrased): it walks the points, numbers any point
that lacks an `en_num` by its array index, returns the first point whose
`en_num` equals `player.playernum`, and if none matches returns
`spawnpoints[ 0 ]`.

`en_num` is the array index, assigned by the framework, so N structs are
numbered 0..N-1 with no extra key. `player.playernum` is an unbounded
counter (`_zm.gsc:712-725`). So with N structs and P players, players
0..N-1 get a point of their own and **every player past the Nth falls
through to `spawnpoints[ 0 ]`** — they stack on the first point. There is
no assert, no wrap-around and no fall back to `player_respawn_point`; the
only assert in the path checks `isdefined` on the array, not its size
(`_zm_gametype.gsc:379`).

The consequences of this, both directions:

- A four-slot map in an eight-player game is not broken, it is crowded:
  players five to eight materialise together on struct 0.
- An eight-slot map in a four-player game is unaffected: playernums 0..3
  match `en_num` 0..3 and the extra four structs are never returned.
  Nothing counts the array. **Unverified by play**, derived from the code
  above.

Nothing else map-side scales in the `.map` itself; the script side is the
correction below. The per-round zombie total is a formula,
not a table indexed by player count (`get_zombie_count_for_round`,
`_zm.gsc:3872-3894`: `max += int( ( n_player_count - 1 ) *
zombie_ai_per_player * multiplier )`), so it has no bound to overrun; the
concurrent caps are level vars (`level.zombie_ai_limit = 24`,
`level.zombie_actor_limit = 31`, `_zm.gsc:310-315`), not map data.

**The zombies scripts enforce four.** `_zm.gsc:7067
player_too_many_players_check` takes `max_players = 4` outside
`zgrief`/`zmeat`, and above that calls `zm_game_module::freeze_players(
true )` and `level notify( "end_game" )`. `_zm.gsc:1865` threads it out of
`onPlayerSpawned`, on every spawn, so the fifth player to join ends the
match and the extra structs seat nobody. The gate is
`level.player_too_many_players_check`, assigned `true` at `_zm.gsc:252`
inside `zm::init()`, which the framework entry reaches synchronously
(`zm_usermap::main()` -> `load::main()`, `_load.gsc:79`), and read on
spawn, so a map that sets it `false` after `zm_usermap::main()` lands
between the write and the read and switches the check off for itself.
That is the second thing map-side that scales with the player count, and
`Z26` requires it above four slots. Read from the raw scripts on the mod tools
install, not played.

**What is separately a dvar.** The lobby size itself: `set com_maxclients
4` and `set party_maxplayers 4` in
`gamedata/configs/zm/zm_default_gamesettings.cfg`.
Higher-player Workshop mods raise that and patch the lobby LUI; they ship
GSC and LUI rawfiles and no map assets, and advertise working on any map
(All-around Enhancement, id 2631943123: "make the mod usable on as many
custom maps as possible"). What they do not fix is the spawn array,
because it is in the map.

Two script-side limits survive any map change and are not ours to solve
(the player-count check above is a third that a map *can* solve, and now
does): only four playable characters exist, and
`assign_lowest_unused_character_index` (`zm_usermap.gsc`) returns `0`
once all four are taken, so players five to eight share character 0; and
the mods' own pages report GobbleGums disabled and no HUD for players
5-8 in eight-player games (Zombies Experience, id 2383464164, which states
plainly that GobbleGums do not function once a game is eight-player).
Every recipe now places GobbleGum machines (`gobblegums=`, default 2) and
emits a runtime gate, `zmforge.script.gobblegum`: from the end of the intro,
once `GetPlayers().size` passes four, the `bgb_machine_use` zbarriers are
hidden and every unitrigger stub within 72 units of one is unregistered
(`_zm_unitrigger.gsc:173-217`), for the rest of the match. The system switch
`level.bgb_in_use` cannot follow the count: `bgb::__init__` reads it once,
before `main`, to register its client fields. Unverified in play.

**The lobby is reachable from a usermap, and so are the per-player
registrations**, so a map can do more than get *ready* for a higher-player
mod. What a usermap
cannot do is **edit** a core script or a core LUI file: `zm_level.class:5-13`
carries `ignore,core_patch`, `ignore,core_ui`, `ignore,zm_patch` and
`ignore,zm_common`, every usermap is `>class,zm_mod_level` which includes it,
and `ignore` drops an asset the shipped fastfile already has. Measured: of the 3,088 assets in a built map's fastfile,
zero come from those five fastfiles. What a usermap *can* ship is an asset at
a name nothing else ships, and both remaining gates yield to that:

- the lobby's limit is `Engine.GetLobbyMaxClients`, and that one does
  **not** yield. A rawfile of the map's own under `ui/zmforge/` clears
  `ignore` — the name is unique — and then the linker refuses the file type
  itself: `ERROR: Lua not supported`, measured on Windows and reproduced
  under Wine, with the fastfile still written. The community page's
  `LuiLoad`-from-csc route does not link.
  Check `Z47` fails any map declaring a `.lua` or `.luac` raw file;
- the per-player registrations are `level` arrays the stock scripts build
  and leave behind -- `level.laststand_update_clientfields`,
  `level.player_name_directive`, `level.laststands` -- so the map's own
  scripts extend them after the framework entry instead of editing the
  scripts that made them.

**Generator rule:** emit `slots` initial-spawn structs, default 4,
minimum 4, none of them carrying `script_int`, every one of them over
floor and at least 32 units from every other; and above 4, emit
`level.player_too_many_players_check = false;` in `main()` immediately
after `zm_usermap::main()`, then the per-player extensions. No Lua: the
linker will not pack it. `zmforge generate --player-slots 8` is the option.
A map that has the structs without the statement fails `Z26`; a map that
declares a Lua raw file fails `Z47`. What still does not work from a map is
the lobby limit, the character indices (players five and up share character
0) and the score widgets, whose client-side models live in a `core_patch`
LUI file. None of it has been played.

**Requirement (Section 10, item K2):** never write
`level.default_start_location` to a zone name. It is the spawn-set label
(`start_room`) that the framework already sets; setting it to
`start_zone` produces `zclassic_start_zone`, which matches no struct and
empties the spawn set. The conformance check fails any script that
assigns it to anything other than `"start_room"`.

### 4.2 Zones [stock-source, played]

A zone is an `info_volume` brush entity:

```
"classname" "info_volume"
"targetname" "<zone name>"
"script_noteworthy" "player_volume"
"target" "<spawn set name>"
// brush 0  { contents detail; ... }
```

- `targetname` **is** the zone name the script registers (`init_zones`,
  `add_adjacent_zone` arguments). Wrong tagging asserts on load and the
  game ends within a second of spawning **[inherited]**.
- `script_noteworthy "player_volume"` marks the volume as playable area.
  With no player volumes the player dies on spawn **[stock-source via
  community doc, consistent with code]**.
- `target` names the spawn-struct set for this zone: the zone manager
  collects structs whose `targetname` equals this value. The convention
  `<zone>_spawners` is a convention only; the requirement is that the
  volume's `target` and the structs' `targetname` agree.
- The brush is the volume's bounds; use `caulk` faces and
  `contents detail;` (`caulk` played; a shipped map uses the `volume`
  tool material there, either is fine). **Size it to the room's outer box,
  walls included, not to its interior**: sizing it to the room interior
  kills players at random. An interior stops at the inside face of the wall, so two rooms
  sharing a wall leave a band of both wall thicknesses (32 units at
  `wall = 16`) in no volume, and the doorway through the wall is in that
  band. A player is 30 units across (`PLAYER_RADIUS 15`,
  `scripts/shared/player_shared.gsc:15` and
  `scripts/zm/_zm_unitrigger.gsc:20`; the bot debug box is
  `(-15,-15,0)..(15,15,72)`, `scripts/shared/bots/_bot.gsc:741`), so in the
  middle of a 32-unit band the player touches neither volume,
  `zm::in_enabled_playable_area` (`_zm.gsc:1999`) is false, and
  `player_out_of_playable_area_monitor` (:2035, polling every 3 seconds)
  does `health + 1000` damage with bleedout zero: an instant death, not a
  down, some of the times the player stands there. Outer boxes of adjacent
  rooms meet on the wall's centre plane and leave nothing over. A volume
  written by hand rather than derived from a room — a storey of a tall room,
  a zone spanning two rooms — has to reach the same wall lines itself.
  The zone that is active at start is the first entry of `init_zones` in the
  script (Section 5), not anything on the entity.

Zone names in the reference end in `_zone`; the game does not require
that suffix. Whatever naming a generator picks, apply it consistently in
the volume, the spawn set, the script and the door graph.

### 4.3 Zombie spawn locations (risers and walk-ins) [stock-source, played]

```
"classname" "script_struct"
"targetname" "<spawn set name>"         (matches the zone volume's target)
"script_noteworthy" "riser_location"    (or spawn_location / faller_location / custom_spawner_entry)
"script_string" "find_flesh"            (interior spawns)
"origin" "<x y z>"
"angles" "<p y r>"
```

- `riser_location`: rises from the ground with the stock rise animation.
  Default. `spawn_location`: appears standing and walks in (looked wrong
  in playtests **[inherited]**). `faller_location`: drops from above.
- `script_string "find_flesh"` is Radiant's default for both riser and
  walk-in templates **[stock-source]** and is what the spawner code
  notifies on rise; structs without it produce zombies that stand still
  **[inherited]**. Barricade-linked risers use the barricade's link tag
  instead (Section 4.6).
- Origin Z = floor surface (16 on a standard slab), never higher
  **[inherited: 32 and 40 produced floating, stuck zombies]**. On
  terrain: surface + 4.
- The struct's XY must be inside its zone's volume for interior spawns,
  and inside the yard for barricade spawns.

### 4.4 Zombie AI factory [stock-source, played]

At least one spawner entity per map, found by
`"script_noteworthy" "zombie_spawner"` (the lookup is on that key, not
the classname). With none, round start sets its flag and returns
silently: no error, no zombies.

```
"classname" "actor_spawner_zm_usermap_zombie"
"script_noteworthy" "zombie_spawner"
"count" "9999"
"script_forcespawn" "1"
"spawnflags" "19"
"model" "c_zom_test_body1"
"origin" "<x y z>"
```

Additional keys the reference copied from a stock map and that a test map
carried in play **[played, load-bearing status unverified]**:
`"ALERTONSPAWN" "0"`, `"MAKEROOM" "1"`, `"SCRIPT_FORCESPAWN" "1"`,
`"SPAWNER" "1"`, `"script_disable_bleeder" "1"`,
`"engageMaxDist" "700"`, `"engageMinDist" "250"`,
`"script_dropammo" "1"`, `"sm_active_count_max" "3"`,
`"sm_active_count_min" "3"`. A shipped map's factory carries `count`,
`export "1"`, `model`, `script_disable_bleeder`, `script_forcespawn`,
`script_noteworthy`, `spawnflags "3"`. Emit the union; it costs nothing.

The factory's position is not where zombies appear (the structs are), and
the lookup is global, not per zone, so at least one factory anywhere in
the map suffices **[stock-source]**. A test map had one factory
co-located with each interior riser struct (four in total) and none in
the starting zone, whose window risers still spawned **[played]**.
Emitting one per interior riser is a harmless preference.

### 4.5 Buyable door [stock-source, played]

Three entities sharing a door name:

Trigger (found by `"targetname" "zombie_door"`):

```
"classname" "trigger_use"
"targetname" "zombie_door"
"target" "<door name>"
"zombie_cost" "<integer, default 1000 when absent>"
"script_flag" "<flag name>"          (comma-separated list allowed)
"cursorhint" "HINT_ACTIVATE"
"script_noteworthy" "default"        ([played]; necessity unverified)
"origin" "<centre of the trigger brush>"
// brush 0 with material trigger: a slab across the doorway -- the door box
// widened 16 at each jamb, deepened 64 in front and 64 behind, and left at the
// opening's own height.  The volume is the buy range, so it is sized to a
// player standing at the door.  Inflating the box by 128 on every axis
// instead would sell the door from about 150 units away.
```

The explicit `origin` on the trigger matters: brush entities default to
origin `0 0 0` and the prompt-visibility check measures distance from the
player to the trigger's origin **[inherited]**.

Door collision (moves when bought):

```
"classname" "script_brushmodel"
"targetname" "<door name>"
"script_string" "move"
"script_vector" "<dx dy dz>"         (sinking the door by its own height, 0 0 -height, played; the direction is a preference as long as the moved door clears the opening)
"DYNAMICPATH" "1"
"spawnflags" "1"
"shadow_casting" "1"
// brush 0 with material clip, the door box
```

Visible door (optional; same movement keys so it slides with the clip):

```
"classname" "script_model"
"model" "p7_zm_der_door_buy_std_onepiece"
"targetname" "<door name>"
"script_string" "move"
"script_vector" "<same as above>"
"DYNAMICPATH" "1"
"spawnflags" "1"
"shadow_casting" "1"
"client_server" "ServerSide"
"modelscale" "1"
"origin" "<door bottom centre>"
"angles" "0 <yaw> 0"
```

The stock one-piece door model is about 96 units tall; a 96-unit doorway
opening with a 16-thick, 80-wide, 96-tall door box fits it **[played]**.
The model's broad face lies along X at yaw 0; a door in an east/west
wall needs yaw 90 **[played]**. Other stock door models:
`p7_zm_der_door_buy_med`, `p7_zm_der_door_buy_std_left`,
`p7_zm_der_door_buy_std_right`, `p7_zm_der_door_buy_lrg_left`,
`p7_zm_der_door_buy_lrg_right`.

Electric doors: `script_noteworthy` of `electric_door` or
`electric_buyable_door` on the trigger makes the door wait for power
**[stock-source]**.

Buying the door sets the flag(s) in `script_flag`. The zone graph
(Section 5.1, step 5) is what turns that flag into an activated zone.

### 4.6 Barricade windows [inherited, played]

Prefab: `_prefabs/zm/zm_core/barricade_reciever_wood.map` (the spelling
`reciever` is the asset's). Variant with despawning debris:
`_prefabs/zm/zm_core/barricade_reciever_wood_hide_pieces.map`.

```
"classname" "misc_prefab"
"model" "_prefabs/zm/zm_core/barricade_reciever_wood.map"
"script_string" "<link tag>"
"origin" "<x y z at the wall, z = floor surface>"
"angles" "0 <yaw> 0"
```

paired with a riser outside the wall:

```
"classname" "script_struct"
"targetname" "<spawn set name of the zone the window feeds>"
"script_noteworthy" "riser_location"
"script_string" "<same link tag>"
"origin" "<barricade origin moved outward; 96 is this package's default, see the range below>"
"angles" "0 <world yaw from the riser back toward the barricade> 0"
```

Facts and constraints:

- The prefab's exterior faces +Y at yaw 0 **[measured: the
  `exterior_goal` struct at `(0, 50, 16)`, the pathnode at `(0, 63, 16)`
  and the zbarrier at `(0, 47, 31)` are all on +Y]**, and the compiler
  turns it counter-clockwise, so the exterior points -X at yaw 90, -Y at
  180 and +X at 270. Yaw must be axis-aligned.
- The riser's angles are **not** the barricade's yaw plus 180. A riser is
  an AI spawn struct and its angles are a plain world heading: the
  direction from the riser back to the barricade, which is the opposite of
  the exterior heading. The old rule agreed with that on no heading at all.
  **[measured: the prefab's own `exterior_goal` stands outside
  at +Y carrying `"angles" "0 270 0"`, a world heading of south, pointing
  back at the barricade at the origin]** See appendix B.
- The window opening starts **at the floor
  surface**, sill 0, and is 96 wide by 112 tall. Measured from the
  prefab's own brushes, in prefab-local units with local z = 0 at the
  floor surface:

  | brush | material | width (X) | height (Z) |
  |---|---|---|---|
  | 0 | `clip` / `clip_player` | -48..50 (98) | 0..113 |
  | 1 | `traverse`, `contents nonColliding` | -25..25 (50) | 0..40 |
  | 2 | `clip_missile` / `clip`+`clip_ai` | -32..32 (64) | 0..35 |

  **The channel the zombies climb through runs from the floor up 40
  units.** An inherited claim puts the sill "48 units above the floor
  surface (waist height)", saying a floor-level sill "makes zombies vault
  onto nothing and fall through the world". A 48-unit sill buries the entire
  `traverse` brush in solid wall, and the window is dead in play. 96 and 112 are
  rounded in from the player clip's 98 x 113 so the clip overlaps the
  wall rather than leaving a gap.

  The vault-onto-nothing worry is answered by the yard, not by the sill:
  the generator digs a yard whose floor is at the room's own z, and Z8
  refuses a riser that is not standing in one.
- The prefab places goal and barrier entities roughly 50 units beyond the
  wall. They must be inside sealed space: a yard (Section 2.7) at least
  144 deep, plus the sky shell. Without the yard the riser falls into
  void; without the shell the compiler reports a leak.
- **The riser's 96 units out is this package's default, not a number the
  game has an opinion about, and this bullet is the only place the range
  is stated.** Pairing every `riser_location` struct in
  `_prefabs/zm/zm_giant/script/zm_giant_nodes.map` with the barricade
  carrying the same `script_string`, the eight shipped pairs stand 94.7,
  104.8, 198.1, 205.1, 257.6, 258.0, 343.9 and 487.5 units from their
  barricade **[measured]**. An
  earlier pass through the same file reported 93 and 252; those are two
  of the same eight, and the range around them was drawn too tight. Note
  also that a tag is not one-to-one: three of Treyarch's receiver tags
  carry two risers each, at different distances.

  What that supports: a floor, and no useful ceiling. The floor is the
  prefab's own `exterior_goal` struct at 50 — a riser nearer than that
  stands inside the prefab's own footprint — rounded to **64** on the
  grid. Above it, the widest shipped pair is 487.5, so a checker has no
  business erroring on distance at all; Z8 errors below 64 and warns
  above 512, and the rule it actually enforces is the one that matters:
  the riser stands on yard floor, outside the wall, in sealed space.
- The link tag is any string unique per window. Derive it
  deterministically from the window's element id so re-runs produce the
  same file.
- Position across the wall's thickness: a test map put the prefab
  origin at the wall's **interior** face (`y = -240` for a wall spanning
  `-256..-240`) **[played]**; the reference's other maps used the outer
  face **[inherited]**. Both work; measure the riser's offset from
  wherever the prefab origin is.
- The zone manager also looks up `"script_noteworthy" "<zone>_barriers"`
  structs **[stock-source]**; that suffix *is* hard-coded. The prefab
  provides those internally; a generator does not emit them.

### 4.7 Perk machines and pack-a-punch [stock-source, played]

Each is one `misc_prefab` into the stock library; the framework spawns
the trigger, the model and the collision from the struct inside the
prefab.

| Perk (free slug) | Fixed prefab path under `_prefabs/zm/zm_core/` | Fixed script module to `#using` |
|---|---|---|
| Widow's Wine | (none ships; emitted as the struct, model `p7_zm_vending_widows_wine`) | `scripts\zm\_zm_perk_widows_wine` |
| Electric Cherry | (none ships; emitted as the struct, model `p7_zm_vending_nuke`) | `scripts\zm\_zm_perk_electric_cherry` |
| Juggernog | `vending_juggernaut_struct.map` | `scripts\zm\_zm_perk_juggernaut` |
| Speed Cola | `vending_sleight_struct.map` | `scripts\zm\_zm_perk_sleight_of_hand` |
| Quick Revive | `vending_revive_struct.map` | `scripts\zm\_zm_perk_quick_revive` |
| Double Tap | `vending_doubletap_struct.map` | `scripts\zm\_zm_perk_doubletap2` |
| Deadshot | `vending_deadshot_struct.map` | `scripts\zm\_zm_perk_deadshot` |
| Stamin-Up | `vending_marathon_struct.map` | `scripts\zm\_zm_perk_staminup` |
| Mule Kick | `vending_additionalprimaryweapon_struct.map` | `scripts\zm\_zm_perk_additionalprimaryweapon` |
| GobbleGum | `vending_bgb_struct.map` | (none; provided by the usermap framework) |
| Pack-a-Punch | `vending_weapon_upgrade_spawnable.map` | `scripts\zm\_zm_pack_a_punch` |

Placing a machine **requires** the matching `#using` line in the map's
server script (Section 5.1) or the machine has no logic. Eight of the nine
prefabs face -Y at yaw 0 **[measured, appendix B]**, so with the
counter-clockwise turn a machine facing north takes yaw 180, east 90, south 0
and west 270. **The pack-a-punch is not one of them**: its prefab's entities
are authored at yaw 270 and its front is -X, so it takes yaw 270 / 180 / 90 /
0 for the same four headings. A machine given the perk front is 90 degrees
out on every heading, not 180 degrees out on two. Origin Z = floor surface for perks; pack-a-punch
sat right at z = floor + 4 to floor + 16 in playtests (its origin is
below the visible model) **[inherited]**.

What the framework does with the struct inside the prefab: finds structs
with `"targetname" "zm_perk_machine"`, reads `script_noteworthy` for the
specialty and `model` for the machine model, spawns a
`trigger_radius_use` with `targetname "zombie_vending"`, a `script_model`
and a `zm_collision_perks1` clip **[stock-source]**. A generator that
wants to bypass the prefab would emit that struct directly; using the
prefab is simpler.

#### 4.7.1 The two machines with no prefab [measured]

Nine prefabs ship, but eleven machines are reachable. The install has the
model *and* both script halves for Widow's Wine and Electric Cherry and
simply never shipped a prefab to stamp, so zmforge emits the struct instead
of a `misc_prefab`. Nothing is imported and nothing is added to the map's
manifest.

<details><summary>What was measured on the install, and why the missing prefab is not the missing asset</summary>

- `zone_source/all/assetlist/zm_levelcommon.csv` is the stock asset list a
  zombies usermap links against. It carries `xmodel,p7_zm_vending_widows_wine`
  and `xmodel,p7_zm_vending_nuke` in the same list as
  `xmodel,p7_zm_vending_jugg`, plus
  `scriptparsetree,scripts/zm/_zm_perk_widows_wine.{gsc,csc}` and
  `..._electric_cherry.{gsc,csc}`, `weapon,zombie_perk_bottle_widows_wine`,
  `weapon,zombie_perk_bottle_cherry`, `image,specialty_widows_wine_zombies`
  and `fx,zombie/fx_perk_widows_wine_zmb`.
- No perk machine model is a *file* in the tools install -- not Juggernog's
  either. `model_export` holds only the pack-a-punch. So "there is no file
  named `*widows_wine*`" says nothing about whether the asset exists; the
  asset list is the authority.
- `share/raw/collmaps/` holds a per-machine collision map for the seven
  prefabbed perks only, and it is not needed: `perk_machine_spawn_init` gives
  every machine the one shared `zm_collision_perks1` model
  (`_zm_perks.gsc:1554`).
- The struct's three keys are Treyarch's own contract:
  the comment at `_zm_perks.gsc:1419` says the struct must carry `model` and
  `script_noteworthy`, and `:1437` collects them with
  `struct::get_array("zm_perk_machine", "targetname")`. The stock prefab
  carries nothing else load-bearing -- `vending_juggernaut_struct.map` is
  that one struct, five decorative lights and three `attack_spot` structs.
  Its struct has no `angles`, so the model's yaw-0 heading is the prefab's
  and the family's turn applies unchanged.
- UGX-Mods, "How to put Widows Wine in your map"
  (<https://www.ugx-mods.com/forum/scripting/91/tutorial-how-to-put-widows-wine-in-your-map/12894/>):
  "Treyarch did not give us the prefabs for Widows Wine, but they did give us
  the scripts, and the assets for Widows Wine."

</details>

<details><summary>Electric Cherry is a dev stub, and the whole of what is wrong with it</summary>

`share/raw/scripts/zm/_zm_perk_electric_cherry.gsc` on the install is an
unfinished file Treyarch shipped with its own to-do comment still in it, at
line 29: `//TODO update these to proper settings`. Everything below is read
off `share/raw/scripts/zm/` in the mod tools, so the line numbers are
checkable in any copy. The same defines are quoted on the Modme
"Setting up perk machines" page, which is how the community knows about them.

| What it should be | What the file says |
|---|---|
| Cost 2000, like every other perk | `#define ELECTRIC_CHERRY_PERK_COST 10` (:30) |
| Its own HUD material, in its own `.gsh`, precached | `#define ELECTRIC_CHERRY_SHADER "specialty_quickrevive_zombies"` (:32) -- Quick Revive's material, and it is the file's only mention: there is no `#precache( "material", ... )`. Every working perk has a `.gsh` of its own carrying its own shader name and does precache it (`_zm_perk_widows_wine.gsh:6` + `.gsc:43`, and the same pair in juggernaut, quick_revive, deadshot, doubletap2, staminup, sleight_of_hand). Electric Cherry has no `.gsh` at all |
| Its own prompt | `register_perk_basic_info( PERK_ELECTRIC_CHERRY, "electric_cherry", ELECTRIC_CHERRY_PERK_COST, &"ZOMBIE_PERK_WIDOWSWINE", ... )` (:73) -- the player is told this is Widow's Wine |
| `p6_zm_vending_electric_cherry_off` / `_on` | `p7_zm_vending_nuke` for both, with the real names left commented out beside them |
| Its own machine name, which line 35 defines as `vending_electriccherry` | `electric_cherry_perk_machine_setup` (line 115) sets `script_string` `marathon_perk` at :118 and `targetname` `vending_marathon` at :122 -- Stamin-Up's |
| Burst size scaled by how empty the clip was | lines 383-384 are `n_clip_current = 1; n_clip_max = 10;`, hardcoded, with the real `GetWeaponAmmoClip` / `WeaponClipSize` pair commented out at :381-382, so every burst fires at the same near-maximum |

The machine-name collision is the one that touches a map rather than a play
session: place Electric Cherry and Stamin-Up together and two machines answer
to `vending_marathon`, so which one any `GetEnt` finds is not the map's to
decide. What the *in-game* symptom is has not been measured.

The gameplay the file does implement is complete and is the reference for what
the perk is: on `reload_start`, radius and damage are `math::linear_map`ped
over how full the clip was, from 32 to 128 units and from 1 to 1045 damage;
zombies under the damage threshold die for 40 points each and the rest are
stunned; one burst per weapon until that weapon finishes reloading, and a
consecutive-use ladder capping the zombies affected at 8, then 4, then 2, then
none, reset three seconds after a reload.

**The published fix is a change to the install, not to a map.** Modme's
"Setting up perk machines" page has the find-and-replace: rewrite the defines,
rewrite `electric_cherry_perk_machine_setup`, and replace every
`vending_marathon` with `vending_electriccherry` in the shipped file. It also
requires ripping the real machine model out of the game with Wraith and
importing it with APE, because `p6_zm_vending_electric_cherry_off/on` is not on
the install. None of that travels with a map, so zmforge does not do it, and
check `Z9` refuses the pair instead of pretending the stub works.

**What a map does instead, and it is built.** A map ships the registration in
its own script, under a specialty nothing else uses, and gets its own price,
its own prompt and its own machine name without touching the install. That is
section 4.7.2 below. A map that wants the effect Electric Cherry was going to
have writes it rather than repairing the stub.

</details>

#### 4.7.2 A perk of our own [generated, unplayed]

A map can sell a perk the game does not have. It is **five registration calls
in the map's own script, one `script_struct` and one line in the map's `.str`**
-- no new asset of any kind, and no change to anybody's install.

```python
from zmforge.script.perks import CustomPerk, points_each_round

blueprint.place_custom_perk(
    CustomPerk(
        slug="coin_return",          # the specialty, the alias and the
        name="COIN RETURN",          # function names are built from this
        cost=1500,
        effect=points_each_round(100),
    ),
    Point(-676.0, 100.0, floor_z),
    Facing.EAST,
    id="perk_coin_return",
)
```

That one call writes the script, the struct, the prompt, the `localize` line
and both `#precache` directives. The defaults are all stock names and all free:
the Electric Cherry bottle, the `p7_zm_vending_nuke` machine, a stock machine
light and the `tombstone` HUD slot. `zm_dmv` ships TAKE A NUMBER in its
entry hall, and it is the worked example.

**Everything ours is written here.** No other author's perk, script, art or
name is involved, and nothing is extracted from anybody's published map. Where
a community perk is known to do something similar, the effect is written from
the stock scripts.

**Two limits, and they are real.** There is **no jingle**: the machine's
jingle and sting are sound aliases, and a usermap on the mod tools install has no perk
aliases at all, so a stock machine in a usermap is already silent in exactly
the same way. And the **icon is a claimed slot**, not a new one: the HUD table
is inside a Lua widget the linker refuses to pack, so a perk lights
one of the two keys that table binds to art the game never shipped
(`tombstone`, `dive_to_nuke`) or it has no icon.

**Nobody has played one.** What is checked is the text: `Z50` at model and
file level, `tests/test_custom_perks.py`, and the failure modes are in
`playable-map-requirements.md`, "A perk the map wrote itself, that nothing can
buy".

<details><summary>What each of the five calls buys, and where it was read</summary>

Read from `share/raw/scripts/zm/_zm_perks.gsc` in the mod tools, which is the
source the linker compiles.

| Call | What it buys | Line |
|---|---|---|
| `register_perk_basic_info( specialty, alias, cost, hint, bottle )` | the price the trigger charges, the prompt it shows, the drink, and the alias the power switch notifies on | :1819, bottle asserted at :1825 |
| `register_perk_precache_func` | a function run inside `zm_perks::init` that fills `level.machine_assets[ specialty ]` with the bottle and the on/off models, and sets the `level._effect` handle | :1896, run from :172-184 |
| `register_perk_machine` | a setup function called on the use trigger, machine, bump trigger and collision the framework spawned, which is where the machine gets its own `targetname` | :1847 |
| `register_perk_threads` | the give and take threads -- the only genuinely new code a perk has | :1919, threaded at :753 and :947 |
| `register_perk_host_migration_params` | the Radiant name and the light effect; with the alias these three are what start the machine loop at all | :1979, gate at :98 |

The sixth call, `register_perk_clientfields`, is **not** made. Every stock
perk makes it on both sides, and both sides register by walking
`GetArrayKeys( level._custom_perks )` (`.gsc:1631-1643`, `.csc:41-52`). A
stock perk is in that array from a preload on both sides; a map's own perk
cannot be -- its server half can only register in `main()`, while its client
half is a `REGISTER_SYSTEM` preload -- so the two sides would fill that array
in different orders, and whether `GetArrayKeys` still returns the same order
either way is **not measured**. A clientfield the two sides disagree
about is a disconnect on join. Writing the UI-model path directly costs
nothing and registers nothing --
`clientfield_shared.gsc:71 set_player_uimodel` is one engine call -- so a map
with one of these perks registers exactly the clientfields it registered
without one. Whether the widget draws an unregistered path is unverified; the
failure if it does not is no icon.

Ordering: the registrations run before `zm_usermap::main()`, because the entry
reaches `zm_perks::init` (`:40`). First registration wins (`:1903`, `:1926`,
`:1959`, `:1987`), and the stock modules register from a `REGISTER_SYSTEM`
preload, which runs before any level `main()`
(`shared/callbacks_shared.gsc:531`). So a stock perk cannot be taken over, and
a specialty nothing else registers is ours outright.

Nothing is imported. The bottles (`zm_levelcommon.csv:6283-6291`), the vending
models (`:1978-1990`) and the machine lights (`:6810-6823`) are on the
level-common list, so the map declares no asset for any of them; the machine
light still needs its `#precache` in both scripts, which is the rule every
stock perk module follows.

</details>

### 4.8 Mystery box [inherited, played]

Three entities at one origin, plus two script variables:

1. `misc_prefab` with `"model" "_prefabs/zm/zm_core/buyable_magic_box_start.map"`
   (the visual base; it is what references the missing plywood material). The
   stand has no front of its own - see appendix B - and takes the box's yaw.
2. The animated chest:

```
"classname" "zbarrier_zmcore_MagicBox"
"script_noteworthy" "<chest name>_zbarrier"
"type" "zmcore_MagicBox"
"barrieranimtime" "0"
"showalternatemodel" "0"
"showupgradedmodel" "0"
"zbarriernumboards" "5"
"zbarrierboardmodel1" "p6_anim_zm_magic_box_fake"
"zbarrierboardmodel2" "p6_anim_zm_magic_box"
"zbarrierboardmodel3" "p6_anim_zm_magic_box"
"zbarrierboardmodel4" "tag_origin"
"zbarrierboardmodel5" "tag_origin"
"zbarrierboardanim1" "o_zombie_magic_box_fake_idle_twitch_a"
"zbarrierboardanim2" "o_zombie_magic_box_leave"
"zbarrierboardanim3" "o_zombie_magic_box_close"
"zbarrierboardanim4" "o_zombie_magic_box_teddy_rise"
"zbarrierboardanim5" "o_zombie_magic_box_teddy_rise"
"zbarriertearanim1" "o_zombie_magic_box_fake_idle_twitch_b"
"zbarriertearanim2" "o_zombie_magic_box_arrive"
"zbarriertearanim3" "o_zombie_magic_box_open"
"zbarriertearanim4" "o_zombie_magic_box_weapon_rise"
"zbarriertearanim5" "o_zombie_magic_box_weapon_dual_rise"
```

3. The use struct:

```
"classname" "script_struct"
"targetname" "treasure_chest_use"
"script_noteworthy" "<chest name>"
"zombie_cost" "950"
```

The stock starting-box prefab uses chest name `start_chest`
**[stock-source: a prefab lifted from a stock map carries
`start_chest_zbarrier` and `start_chest`]**. The starting box also
needs, in the server script before the framework's zone hook:
`level.start_chest_name = "start_chest";` and
`level.enable_magic = true;` **[inherited; a test map had them in play; the
variable names are not quoted from stock source, so
[unverified] as to necessity]**. Additional boxes use unique chest names
and no script change.

### 4.9 Power switch [stock-source, played]

`misc_prefab` with `"model" "_prefabs/zm/zm_core/power_switch.map"`,
origin at floor + 8, yaw facing into the room. Its front is -Y at yaw 0
**[measured]**: the prefab's own `trigger_use` brush stands off
that face at `y in [-24, -5]`. The prefab contains the
triplet the framework reads: a `trigger_use` with
`"targetname" "use_elec_switch"` whose `target` names a `script_model`
with `"script_noteworthy" "elec_switch"` and a `script_struct` with
`"script_noteworthy" "elec_switch_fx"`.

### 4.10 Wall weapons [played]

`misc_prefab` with `"model" "_prefabs/zm/zm_core/spawnable_weapon_<slug>.map"`
for slug in `ar_standard`, `ar_cqb`, `ar_longburst`, `ar_marksman`,
`smg_standard`, `smg_fastfire`, `smg_versatile`, `shotgun_pump`,
`pistol_burst`, `pistol_fullauto`, `frag_grenade`, `bouncingbetty`,
`bowie`. Origin at the wall's interior face (2 units into the room from
it also played), yaw facing into the room -- but **not** the perk
convention. All thirteen stock prefabs are read and every one is built the same way: the chalk patch mesh and the weapon's
`script_struct` lie on the plane `y = 0` and the mount brush sits behind
them at `y` in `[-8, -1]`, so the prefab wants the wall surface at its own
origin plane, the wall body at negative Y and the room at positive Y. Its
front is **+Y**, and with the counter-clockwise yaw of appendix B a buy
facing north is yaw 0. Emitting the perk convention here (yaw 180 for north)
puts the drawing inside the brickwork, the mount out in the room, and the
unitrigger origin `_zm_weapons.gsc:962` offsets sideways inside the wall as
well, so the buy has neither a picture nor a prompt and nothing in the
compile or link log says so. `verify` code **W3** is the guard.
**Z: a test map used `z = 8` with the floor surface at 16, that is
8 units *below* the surface**; the prefab's own geometry accounts for
it. Treat the relation as **[played, not derived]** and expose it.
An optional chalk outline is a `misc_volume_decal`:

```
"classname" "misc_volume_decal"
"model" "vol_decal_cube"
"modeloverridematerial" "t7_zm_chalk_buy_<weapon>"
"decalsize" "4 64 32"
"decalLayerSort" "Grunge"
"decalLayerSortEnum" "14"
"decalEditorSortEnum" "0"
```

with yaw pointing its forward axis into the wall **[inherited]**.

### 4.11 Lighting and visibility entities [inherited, played]

All of these are brush volumes that wrap the whole space inside the sky
shell (Section 2.7), inset by a small margin so they lie strictly inside
the slabs (a few units; a preference).

Sun volume (required for the bake):

```
"classname" "volume_sun"
"ssi" "default_day"
"ssi1" "default_day"
"grid_density" "32"
"shadowBiasScale" "1"
"shadowSplitDistance" "2000"
"streamLighting" "1"
// brush with material sun_volume
```

Umbra volume (required; without it the compiler prints a line about the
umbra volume not being set and defaulting to a million-unit cube, and
walls render as sky **[inherited]**):

```
"classname" "umbra_volume"
// brush with material umbra_volume
```

FPS tool volume (present in the stock template; not required):
`"classname" "volume_fpstool"`, brush material `caulk`.

Reflection probe (optional; the bake errors with a message about a probe
having no counterpart when it sits where no sample was taken
**[inherited]**, so off by default):
`"classname" "reflection_probe"` with, from the stock template:
`"radius" "2048"`, `"name" "probe"`, `"box" "1"`,
`"size_min" "72 72 72"`, `"size_max" "72 72 72"`,
`"blend_mins" "3 3 3"`, `"blend_maxs" "3 3 3"`,
`"placement_offset" "72"`, `"grid_density" "16"`, `"high_detail" "1"`,
`"in_play_space" "1"`, `"ao_power" "2"`, `"ao_range" "16"`,
`"ao_strength" "1"`, `"exploderFade" "1"`, `"debugColor" "1 1 1"`,
`"client_server" "ClientSide"`, and an `origin` at the room centre.

Point light (required in every sealed room; the sun cannot reach inside a
closed box **[inherited]**):

```
"classname" "light"
"PRIMARY_TYPE" "PRIMARY_OMNI"
"def" "white_light"
"_color" "<r g b in 0..1>"
"radius" "<units>"
"stops" "<log2 of the intensity; see below -- NOT a fixed 4>"
"bulbRadius" "4"
"falloffdistance" "8"
"ENABLE_FALLOFF" "1"
"PROBE_ONLY" "0"
"PRIMARY_NOSHADOWMAP" "0"
"fov_outer" "115"
"far_edge" "0.5"
"roundness" "0.5"
"penumbraRadius" "3"
"shadowmapScale" "1"
"shadowUpdate" "Never"
"lightingstate1" "1"  ... "lightingstate4" "1"
"client_server" "ClientSide"
"name" "light"
"spawnflags" "66"
"origin" "<inside the room's void, below the ceiling slab>"
```

A light whose origin lies inside the ceiling brush illuminates nothing.

`stops` is not "photographic stops, 4 = medium": a map emitted with a
fixed `"stops" "4"` plays nearly black. `stops` is literally **log2 of the
emitter's intensity** — read the values off
`_prefabs/zm/zm_giant/zm_giant_light.map` and they are logarithms of
round numbers: `4.64385618977472` = log2(25), `5.64385618977472` =
log2(50), `9.96578428466209` = log2(1000) **[measured]**.

It therefore only means anything against the camera's exposure, which
comes from the map's sun/sky preset — the `ssi` named on the worldspawn
and on `volume_sun`. Those presets live in `source_data/ssi.gdt` and each
carries an `ev`:

| ssi preset | ev | sun `stops` | `enablesun` |
|---|---|---|---|
| `default_day` | 15 | 14 | 1 |
| `default_morning` | 13.5 | 11.3 | 1 |
| `default_sunset` | 12.5 | 11 | 1 |
| `default_night` | 6 | -2.2 | 1 |
| `zm_factory` | 5 | -2 | 1 |
| `zm_zod` | 4 | -2.5 | 0 |
| `mp_sector` | 12.75 | 13.3 | 1 |

Now put the shipped lamps beside the exposure of the map they are in:

- `zm_giant` runs `ssi zm_factory`, **ev 5**. Its 543 lamps peak at
  `stops` 4.64 and 5.64 and run to about 10.
- `mp_sector` and `mp_combine` run `ssi mp_sector`, **ev 12.75**. Their
  275 lamps peak at `stops` 15 and 16, band 13 to 17.

Two maps ten stops apart in exposure carry lamps ten stops apart in
intensity. **A lamp's `stops` sits at its map's exposure `ev`, give or
take a few stops up.** The old fixed 4 was The Giant's night value
copied into a `default_day` map: eleven stops, 2048x, too dark.

Two more measured facts a generator needs:

- **There is no ambient term to lean on.** `volume_sun` carries a
  `global_fill_color`/`global_fill_intensity` pair, and across all the
  shipped `.map` files it appears four times, always as
  `"global_fill_color" "0 0 0"` — black. Interiors are lit with many
  point lights at an intensity matched to the exposure, and nothing else.
- **Density.** `zm_giant_light.map`'s 536 non-skybox lamps span
  4304 x 6389 units: one lamp per 51,300 square units, a 226 x 226
  patch. They stack at each fixture (536 lamps in 360 distinct 32-unit
  cells), so fixture density is nearer one per 76,000 square units, a
  276 x 276 patch, and fixture-to-fixture spacing runs a median of 48
  with a 90th percentile of 190. One lamp per room is not enough for any
  room bigger than that patch.

`zm_giant.map` itself contains **zero** `light` entities: all 543 live in
one linked prefab, `_prefabs/zm/zm_giant/zm_giant_light.map`. Its
worldspawn also carries exposure keys the generator does not emit
(`evauto 1`, `evcmp 2.5`, `evmax 3.5`, `evmin 3`, `bloom`, `vcolor`,
`vsky`, `secondsLerpToDarker/Lighter`) and carries no `ssi`, `wsi`,
`samplescale`, `lightingquality` or `skyboxmodel` at all — the
`skyboxmodel` lives in the `ssi` asset. Omitting the `ev*` keys, as the
generator does, leaves the `ssi`'s own `ev` in force, which is what makes
the rule above work.

### 4.12 Dog rounds [stock-source]

The usermap framework does `if (!isdefined(level.dog_rounds_allowed))
level.dog_rounds_allowed = 1;` and then enables dog rounds when the flag
is set. The first dog round after round 1 is `round + randomintrange(4, 7)`,
so 5, 6 or 7. The dog spawn path dereferences the first element of the
array of entities with `"script_noteworthy" "zombie_dog_spawner"` without
a guard; with none present the round cannot complete (community reports
an infinite dog round; a script error is also possible). Therefore:

- A map with no dog spawners **must** assign
  `level.dog_rounds_allowed = 0;` **before** calling the framework's
  main entry, because the framework's default only applies when the
  variable is undefined. After the call is too late.
- A map that wants dogs places `actor_spawner_zm_factory_zombie_dog`
  entities with `"script_noteworthy" "zombie_dog_spawner"` (stock keys
  seen: `count 1`, `script_forcespawn 1`, `spawnflags 3`,
  `model zombie_wolf`) and structs with
  `"script_noteworthy" "dog_location"` in each zone's spawn set, and
  leaves the flag at 1.

### 4.13 Prop scatter [inherited]

Decorative models as `misc_model` with `"no_collmap" "1"` (no collision,
so they cannot break the navmesh), `"static" "1"`, `"modelscale"`,
`"lightingstate1".."4" "1"`, random yaw, seeded deterministic placement
(a jittered grid or any other even sampler; a preference) with keep-clear
regions around interactables and doorways. Model names
must come from real map sources; `p7_foliage_grass_02`,
`p7_debris_concrete_rubble_sm_02`, `p7_crate_wood_01` are examples that
linked (the linker collects `misc_model` models automatically; no
manifest entry needed **[inherited: linker log showed the mesh
conversion]**).

### 4.14 Summary of load-bearing agreements

A conformance checker must verify these cross-references:

| A | must equal | B |
|---|---|---|
| zone volume `target` | | every spawn struct `targetname` in that zone |
| zone volume `targetname` | | the `init_zones` entry and `add_adjacent_zone` arguments in the script |
| door trigger `target` | | door brushmodel and door model `targetname` |
| door trigger `script_flag` | | the flag argument of the `add_adjacent_zone` call for that door |
| barricade prefab `script_string` | | its riser's `script_string` |
| spawn struct `script_string` tokens | | `<gametype>_start_room` for the default location |
| every placed perk | | a `#using` of its module in the server script |
| `level.dog_rounds_allowed` | | `0` unless dog spawners and dog locations exist |

---

## 5. The generated game script

Two files: the server script `share/raw/scripts/zm/<map>.gsc` and the
client script `share/raw/scripts/zm/<map>.csc`. Paths relative to the
mod tools root. Script syntax is Treyarch's GSC; the following is what
the map's scripts must contain and in what order. The original authors
shipped CRLF line endings; either works.

### 5.1 Server script structure

In order:

1. `#using` directives for the shared and zombies modules the body
   needs. Minimum set that compiled and played:
   `scripts\codescripts\struct`, `scripts\shared\callbacks_shared`,
   `scripts\shared\flag_shared`, `scripts\shared\util_shared`,
   `scripts\zm\_load`, `scripts\zm\_zm`, `scripts\zm\_zm_zonemgr`,
   `scripts\zm\_zm_utility`, and last `scripts\zm\zm_usermap`. Each is
   written `#using <path>;` with backslashes.
2. `#insert` directives: `scripts\shared\shared.gsh`,
   `scripts\shared\version.gsh`, `scripts\zm\_zm_utility.gsh`.
3. One `#using` per placed perk/pack-a-punch module (Section 4.7 table).
   Emitting all of them regardless of placement is **[unverified]**;
   emit exactly the set that is placed.
4. `function main()`:
   1. `level.dog_rounds_allowed = 0;` (or 1 with dog spawners), **before**
      the next line (Section 4.12).
   2. `zm_usermap::main();` (the framework entry; it sets
      `level.default_start_location = "start_room"` and
      `level.default_game_mode = "zclassic"`, loads the level, and
      applies the dog default).
   3. Optionally `level.default_game_mode = "zclassic";` (the framework
      already sets it; the played script repeated it, so it is harmless,
      not required).
   4. Mystery box variables if a starting box exists (Section 4.8).
   5. `level.zone_manager_init_func = &<zone hook function>;`
   6. `init_zones[0] = "<starting zone>";`, `init_zones[1] = ...` for
      every zone. `init_zones[0]` is the zone active at game start.
   7. `level thread zm_zonemgr::manage_zones( init_zones );`
5. The zone hook function, `function <zone hook>()` (its name is free;
   it only has to match the address taken in step 4.5):
   1. One `zm_zonemgr::add_adjacent_zone( "<zone a>", "<zone b>",
      "<flag>" );` per buyable door with a flag. The call creates the
      flag and both zones if needed; setting the flag (buying the door)
      activates the far zone. Order the calls in door order; direction
      does not matter for a two-way door.
   2. `level flag::init( "always_on" );` and `level flag::set( "always_on" );`
      (what shipped maps do; keeps zones that need no door active).

Skeleton (the syntax is the game's; fill the angle-bracket slots from the
script model):

```
#using scripts\codescripts\struct;
#using scripts\shared\callbacks_shared;
#using scripts\shared\flag_shared;
#using scripts\shared\util_shared;

#insert scripts\shared\shared.gsh;
#insert scripts\shared\version.gsh;
#insert scripts\zm\_zm_utility.gsh;

#using scripts\zm\_load;
#using scripts\zm\_zm;
#using scripts\zm\_zm_zonemgr;
#using scripts\zm\_zm_utility;
<one line per placed machine:>  #using scripts\zm\_zm_perk_juggernaut;
#using scripts\zm\zm_usermap;

function main()
{
	level.dog_rounds_allowed = <0 or 1>;
	zm_usermap::main();
	<optional:>  level.default_game_mode = "zclassic";
	<if a starting mystery box:>  level.start_chest_name = "<chest name>";
	<if a starting mystery box:>  level.enable_magic = true;
	level.zone_manager_init_func = &<zone hook>;
	init_zones = [];
	init_zones[0] = "<starting zone>";
	init_zones[1] = "<next zone>";
	level thread zm_zonemgr::manage_zones( init_zones );
}

function <zone hook>()
{
	zm_zonemgr::add_adjacent_zone( "<zone a>", "<zone b>", "<door flag>" );
	level flag::init( "always_on" );
	level flag::set( "always_on" );
}
```

Tabs for indentation, one statement per line, `;` terminators, and the
`&` before a function name to take its address. Write the file as plain
ASCII/UTF-8 without a byte-order mark **[played without one; BOM
behaviour unverified]**. Shipped maps add a
`#namespace <name>;` line after the inserts; it is not required
**[played without one]**.

The framework entry never creates zones and never calls the zone manager;
the map must (`manage_zones` runs the hook, then initialises and enables
each `init_zones` entry) **[stock-source]**.

`level.default_start_location` must not be assigned by the map script
unless spawn structs carry the matching token (Section 4.1).

### 5.2 Client script structure

```
#using scripts\codescripts\struct;
#using scripts\shared\callbacks_shared;
#using scripts\shared\clientfield_shared;
#using scripts\shared\system_shared;
#using scripts\shared\util_shared;
#insert scripts\shared\shared.gsh;
#insert scripts\shared\version.gsh;
#using scripts\zm\zm_usermap;

REGISTER_SYSTEM( "<map>", &__init__, undefined )

function __init__() { callback::on_localplayer_spawned( &on_player_spawned ); }
function main() { zm_usermap::main(); }
function on_player_spawned( localClientNum ) { }
```

The client `main` **must** call the framework's client entry; without it
the server and client disagree on registered client fields and the game
disconnects on join with a clientfield mismatch error **[inherited]**.

### 5.3 Generate, do not patch

Do not edit the script in place around textual anchors. That design
must track anchors, indentation and line endings, and it lost CRLF
endings on every edit until fixed (Section 10, item K10). A
reimplementation should hold a script model (perk modules, zone list,
door edges, box variables, dog flag) and **regenerate the whole file**
from it on every commit. The generator must refuse to overwrite a file
whose content it did not produce: it compares the file against a hash it
stored at the last commit, leaves the file alone, and reports it
(`hand_edited`), unless the caller forces the write.

**Custom gameplay goes through the seam in Section 5.5, not through this
file.** Hand edits are not "imported once and preserved as an opaque
block", because preserving a block means reading the
emitted file back and locating one half of it inside the other, which is
the anchor-tracking this section exists to forbid. Under 5.5 the
scaffolding is written top-down from the model and custom functions are
appended whole below it, so neither half has to find the other and
nothing survives from the previous file.

### 5.4 Script facts table (fixed)

| Name | Kind | Who reads or sets it |
|---|---|---|
| `zm_usermap::main` | framework entry, server | must be called by the map's `main` |
| `zm_usermap::main` (client) | framework entry, client | must be called by the client `main` |
| `level.dog_rounds_allowed` | level variable | framework defaults to 1 if undefined, then enables dog rounds |
| `level.default_start_location` | level variable | framework sets `"start_room"`; gametype code builds the spawn match string from it |
| `level.default_game_mode` | level variable | framework sets `"zclassic"` |
| `level.zone_manager_init_func` | function pointer | zone manager calls it before initialising zones |
| `zm_zonemgr::manage_zones( init_zones )` | thread | initialises and enables the listed zones; must be started by the map |
| `zm_zonemgr::add_adjacent_zone( a, b, flag )` | call | links two zones through a flag |
| `level flag::init( name )`, `level flag::set( name )` | calls | flag helpers |
| `level.start_chest_name`, `level.enable_magic` | level variables | mystery box start [inherited] |
| `REGISTER_SYSTEM( name, init, undefined )` | client macro | registers the client system |
| `callback::on_localplayer_spawned( fn )` | client call | spawn callback |

### 5.5 Custom gameplay script [this design]

The generated script above is scaffolding: it defines what the framework
requires and nothing else. Custom gameplay logic is supplied as a
**model**, never as an edit to the emitted file, because Section 5.3
regenerates that file whole on every commit.

**The seam.** A caller builds a `CustomScript` holding:

| Part | Where it lands in the emitted file |
|---|---|
| `using` / `client_using` | extra `#using` lines, after the perk modules, before `scripts\zm\zm_usermap` |
| `functions` | appended after every function the engine generates |
| statements at slot `BEFORE_ENTRY` | top of `main`, above `level.dog_rounds_allowed` |
| statements at slot `AFTER_ENTRY` | in `main`, immediately after `zm_usermap::main()` |
| statements at slot `ZONE_HOOK` | end of the generated zone hook |
| statements at slot `CLIENT_INIT` | in the client script's `__init__` |

**There is deliberately no slot between `level.dog_rounds_allowed` and
`zm_usermap::main()`.** Section 4.12 makes that adjacency load-bearing,
and a slot there would let a caller break the ordering Z10 exists to
test. The emitter writes statements verbatim and one tab in; it never
parses them back or edits around anchors.

**Why the two halves cannot corrupt each other.** Generated scaffolding
is written top-down from the model; custom functions are appended whole
below it. A regeneration rewrites the top and re-emits the bottom, so
neither half has to locate the other in the text, and nothing survives
from the previous file. This replaces 5.3's "opaque preserved block"
idea, which required reading the emitted file back.

**Validation before a build.** A GSC error is fatal at run time
(the `SCRIPT ERROR` failures listed in Section 7.3), the compiler is a
Windows program, and the linker never
exits zero, so a mistake found there costs a whole build cycle. Two
checks therefore run in the process that writes the text, over the
finished file, and are listed in Section 9.4 as Z15 and Z16:

- structure: unbalanced brackets, unterminated string literals,
  statements with no terminator, a statement outside any function, one
  function name defined twice. Comments and string bodies are blanked
  before counting, so a brace inside `"a{b"` is text and not syntax.
- references: an unqualified call or `&pointer` to a function the file
  does not define; a namespaced call absent from the stock symbol table;
  a known namespaced call whose module the script never `#using`s.

**The stock symbol table** is the list of stock functions a custom
script may call. Every entry records the file and line it was read from.
Nothing may be added to it that was not read out of a stock script or
proven by a build: a plausible-looking function name that does not exist
compiles fine and kills the game when the line runs, which is exactly
the failure the table exists to prevent. A caller who has read a stock
script the table does not cover yet can pass the namespace through
explicitly, which keeps the missing-`#using` check but waives the
per-function one.

**For a map editor.** The seam is data, not text: a `CustomScript` is
a list of `#using` paths, a list of named functions with bodies, and a
list of (slot, statement) pairs. An editor can offer the slot list as a
fixed menu, hold the bodies as text areas, and run the same two checks
before it will let a build start.

### 5.6 Gameplay hooks read from the stock scripts [stock-source]

Hooks a usermap can use from its own script without editing a stock file.
Every line reference is into the public decompile the format reference
already cites (`github.com/ate47/bo3-source`). A decompile
is not the compiler, so the build on Windows stays the authority;
what this table settles is which names exist at all.

| Want | Hook | Evidence |
|---|---|---|
| know a player fired a weapon | `player waittill( "weapon_fired", weapon )` | `_zm_weapons.gsc:423`, `_zm_altbody_beast.gsc:1511` |
| a weapon object by name | `getweapon( "pistol_burst" )` | `_zm.gsc:1193`, `_zm_weap_ball.gsc:1422` |
| down a player, not kill | `player dodamage( damage, origin, attacker )` with damage above health | `_zm.gsc:5354` returns early below health, `:5464` threads `playerlaststand`; "hurt but do not kill" idiom at `_zm_ai_astro.gsc:646` |
| is a player already down | `laststand::player_is_in_laststand()` | `laststand_shared.gsc:12` |
| perks a player may hold | count, stock default 4; override pointer `level.get_player_perk_purchase_limit` read at purchase time | `_zm_perks.gsc:34`, `_zm_utility.gsc:6409-6415`, gate at `:6427` |
| refuse a perk sale, free | `level.custom_perk_validation` returning 0 | `_zm_perks.gsc:571-573`, charge is later at `:612` |
| after a perk sale | `level.perk_bought_func` | `_zm_perks.gsc:657`, grant at `:737` |
| take a perk back | `unsetperk`, `num_perks--`, `set_perk_clientfield( perk, 0 )` | `_zm_perks.gsc:950-958` |
| force the box's weapon | `level.customrandomweaponweights`, which replaces the candidate array after the shuffle and before eligibility | `_zm_magicbox.gsc:1264-1268`; stock passthrough at `zm_zod.gsc:197`, `:1422` |
| spawn rate | `zm_utility::set_zombie_var( "zombie_spawn_delay", n, 1 )`, stock default 2 | `_zm.gsc:1247`, consumed `_zm.gsc:3860`, setter `_zm_utility.gsc:3382` |
| wait on a door or power | `level flag::wait_till( name )` | `flag_shared.gsc:190`, stock use `zm_castle.gsc:880` |
| move a player | `setorigin` + `setplayerangles`, inline, as every stock map does | `zm_tomb_teleporter.gsc:526-527`, `zm_castle_ee.gsc:2561-2562` |
| a trigger with no map entity | `spawn( "trigger_radius", origin, 0, radius, height )`, then `waittill( "trigger", who )` | `doors_shared.gsc:1190`, `_zm_ai_spiders.gsc:1673` |
| per-player threads | `level waittill( "connected", player )`, plus `getplayers()` for those already in | `_zm.gsc:482`, `_zm_perks.gsc:203` |
| kill zombies with something worth watching | `getaiteamarray( level.zombie_team )`, then per zombie `zombie_utility::zombie_head_gib()`, `playsound( "evt_nuked" )`, `dodamage( health + 666, origin )`; skip `zm_utility::is_magic_bullet_shield_enabled` and mark `marked_for_death` | `_zm_powerup_nuke.gsc:47`, `:120`, `:126`, `:127`, `:89`, `:96` |
| deafen a player, the concussion effect | `player shellshock( "explosion", seconds, 0 )` | `_zm_ai_napalm.gsc:740`, `_zm_ai_quad.gsc:348`; the flashbang's own call `shared/weapons/_flashgrenades.gsc:203` |
| a looping sound on a player | spawn a `script_origin`, `linkto` the player, `playloopsound( alias, fade )`, then `stoploopsound` and delete | `_flashgrenades.gsc:227-243`, cleanup `:250-255` |
| screen flash | `lui::screen_flash( fadein, hold, fadeout, alpha, colour )`, **on the player it is meant for**: called on `level` it re-threads itself on every player in `level.players` | `lui_shared.gsc:442`, the level fan-out `:434-439`, one player `archetype_thrasher.gsc:1201`, stock use `_zm_powerup_nuke.gsc:157` |
| is this in front of me | `anglestoforward( self getplayerangles() )` + `vectordot`, flattened to XY with `vectornormalize` | `_zm_weap_claymore.gsc:134-135`, `_zm_weap_elemental_bow.gsc:524`, `zm_genesis_cleanup_mgr.gsc:354` |
| spawn ordinary zombies outside the round | `zombie_utility::spawn_zombie( level.zombie_spawners[ 0 ], "<name>" )`, after setting `spawner.script_forcespawn = 1` | `shared/ai/zombie_utility.gsc:1851`, guard `:1865`; stock callers `zm_island_power.gsc:620`, `zm_castle_tram.gsc:496`; forcespawn set as `_zm_ai_dogs.gsc:135` |
| put an AI somewhere specific | `ai forceteleport( origin, angles )` | `_zm_ai_dogs.gsc:332`, `_zm_ai_raz.gsc:414`, and inside `spawn_zombie` itself `:1908` |
| make a zombie sprint at any round | `ai zombie_utility::set_zombie_run_cycle( "sprint" )`, then `ai.zombie_move_speed_original = ai.zombie_move_speed` | `zombie_utility.gsc:2500`, `:2511`; the stock last-zombie sprint `:2393-2394` |

Perk specialty strings, which the hooks above are passed and which a
machine's trigger carries as `script_noteworthy`, read from each perk's own
module: juggernog `specialty_armorvest`, speed cola `specialty_fastreload`,
quick revive `specialty_quickrevive`, double tap `specialty_doubletap2`,
deadshot `specialty_deadshot`, stamin-up `specialty_staminup`, mule kick
`specialty_additionalprimaryweapon`.

**Script-spawned zombies and the round.** They are extra, not instead.
`level.zombie_total` is decremented only by the round spawner
(`_zm.gsc:3839`), so a script spawn does not consume the round's budget; but
the round cannot end while any zombie lives (`_zm.gsc:4766` `should_wait =
zombie_utility::get_current_zombie_count() > 0 || level.zombie_total > 0`),
so script-spawned zombies must be killed like any other. They also count
against the live-AI cap the round spawner waits on (`_zm.gsc:3772`), and
`spawn_zombie` blocks on `getfreeactorcount()` (`:1859`), so at a high round
a batch arrives as slots free rather than all at once. Nothing about the
round loop is modified.

**What the stock scripts do not let a usermap do**, each a negative result
rather than an untried idea:

- **A perk machine that gives nothing without editing a stock script.** The
  hooks exist (`level.custom_perk_validation`, `level.perk_bought_func`), but
  no shipped recipe uses them.
- **Turn lights on or off from script.** There is no `SetLightIntensity` or
  light-entity call anywhere in the tree. Stock maps fire radiant-placed
  exploders instead (`zm_castle.gsc:1272-1274`
  `exploder::exploder( "exp_lgt_power_on" )`), and an exploder id comes from
  a KVP the level designer set (`exploder_shared.gsc:55`). So "the power
  switch turns the lights off" needs entity work in the layout; the power
  hook itself is available (`_zm_power.gsc:977` sets the `power_on` flag).
- **Rig one box and not another.** `level.customrandomweaponweights` is
  passed the player and the candidate array and **not** the chest
  (`_zm_magicbox.gsc:1266-1268`), so with two boxes in a map the only
  discriminator available to script is where the player is standing.
- **Make the box move away on its first use.** The decision is level-wide
  and probabilistic: `treasure_chest_should_move` (`:1453`) needs
  `magic_chest_movable`, compares `level.chest_accessed` against
  `level.chest_min_move_usage` (default 4, `:1459-1461`) and rolls
  `randomint( 100 )` (`:1457`). Moving also needs somewhere to move to,
  which is more box locations in the layout.
- **Charge more than a door advertises.** No hook was found between a door
  trigger's `zombie_cost` and the charge.

### 5.7 A map can name its own guns, and it does it with a localised string [measured]

**A wall buy's prompt text is a map's to set.** The name is not baked into the
weapon and the prompt is not hardcoded: a usermap ships its own localised
strings, and a line of the map's own script points the buy at one of them.
This section replaces a negative result that was wrong; what it got wrong is
written out at the end, because the mistake is instructive.

#### 5.7.1 The three facts that make it work

**1. The linker links `localize`, and it reads a hand-written `.str`.**
[measured] A probe usermap `zm_test` whose **main** zone
(`usermaps/zm_test/zone_source/zm_test.zone`) carried

```
localize,zmf_test
```

linked under Wine with no `ERROR:` line, against a `.str` written by hand at

```
<root>\share\raw\english\localizedstrings\zmf_test.str
```

The linker's own dependency record says so in its own words --
`usermaps/zm_test/zone_source/english/assetinfo/zm_test.deps`:

```
localize,zmf_test
	file,C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130\share\raw\english\localizedstrings\zmf_test.str,1234567890,
```

The asset is routed into the **English** fastfile without being named
anywhere else: it appears in `zone_source/english/assetlist/<map>.csv` and in
`zone_source/english/assetinfo/<map>.csv`, never in the `all` pair. So the
`loc/<map>.zone` companion is **not** needed for this -- one line in the main
zone is the whole declaration. (Published maps put theirs in the loc zone
instead; both reach the same fastfile. `clixmods/zm_nuked`'s
`zone_source/loc/zm_nuked.zone` ends `sound,zm_nuked` / `localize,nuked_string`
-- <https://raw.githubusercontent.com/clixmods/zm_nuked/main/zone_source/loc/zm_nuked.zone>.)

**2. The asset name is `<STR FILE>_<REFERENCE>`, uppercased, always
prefixed.** [measured] Four references linked in one run, read back
out of `english/assetinfo/zm_test.csv`:

| `.str` file | `REFERENCE` | linked asset name |
|---|---|---|
| `zmf_test.str` | `ZMFORGE_LOCPROBE` | `ZMF_TEST_ZMFORGE_LOCPROBE` |
| `zmforge.str` | `ZMFORGE_BIG_GUN` | `ZMFORGE_ZMFORGE_BIG_GUN` |
| `zmforge.str` | `BIG_GUN_TWO` | `ZMFORGE_BIG_GUN_TWO` |
| `zmforge.str` | `ZOMBIE_WEAPONCOSTONLYFILL` | `ZMFORGE_ZOMBIE_WEAPONCOSTONLYFILL` |

There is no de-duplication: the file name is glued on even when the reference
already starts with it. Two consequences. A map whose `.str` is named after
the map refers to `&"<MAP>_<REFERENCE>"` from script -- which is what Resxt's
BO3 script pack documents ("If you named your `.str` file
`zm_resxt_minecraft` you would refer to `EXAMPLE_HINTSTRING` as
`"ZM_RESXT_MINECRAFT_EXAMPLE_HINTSTRING"` in your code",
<https://github.com/Resxt/T7-Scripts>). And a map that wants to **replace** a
stock string has to name its `.str` after the stock prefix, which is exactly
why Harry Bo21's fix pack is a file called `zombie.str` and one zone line,
`localize,zombie`
(<https://wiki.modme.co/wiki/black_ops_3/basics/Adding-The-Missing-Localized-Strings.html>).

**3. The wall buy's hint IS read back off a struct the map can write.** The
stock loader ignores the table's `hint` column and forces the value
(`_zm_weapons.gsc:559-566`), which is true and was the whole basis of the old
conclusion. But `get_weapon_hint` does not return a constant:

```
function get_weapon_hint( weapon )        // _zm_weapons.gsc:1417-1422
{
	return level.zombie_weapons[weapon].hint;
}
```

and that is what the buy uses, at both the places that build a prompt --
`unitrigger_stub.hint_string = get_weapon_hint( spawn_list[i].weapon );`
(`:969`) and `hint_string = get_weapon_hint( self.weapon );` inside
`reset_wallbuy_internal` (`:1305`). The trigger then prints it with the cost
as the first parameter, `SetHintString(stub.hint_string, stub.cost)`
(`_zm_unitrigger.gsc:749-765`), so `&&1` in the string is the price.

So a map overwrites `level.zombie_weapons[ GetWeapon( "shotgun_pump" ) ].hint`
after the weapon tables load and before the stubs are built, and the buy says
what the map says.

#### 5.7.1a The other two routes, and why this one

Two further routes exist and are not taken. Both are written down because
somebody will find them.

**A plain literal.** Released maps pass ordinary quoted English straight to
`SetHintString`, which is the part Treyarch's own tree never does. Real
examples: `n_talk1 SetHintString("Hold ^3[{+activate}]^7 to talk to Nathan");`
and `pack_part_trig1 SetCursorHint("HINT_NOICON");` in Nathan's Donuts
(<https://raw.githubusercontent.com/carsongooch/BO3-GSC-Mod-Library/main/Nathan's-Donuts-Scripts/zm_nathans_crib.gsc>);
`meteor SetHintString( "Hold ^3&&1 ^7To Place " + string );` in Project
Elemental, which concatenates at runtime and so cannot be a localised
reference
(<https://raw.githubusercontent.com/Polystyreeni/BO3/main/scripts/zm/zm_project_e_ee.gsc>);
and a full wall-buy prompt rebuilt as a literal in EliotDucky's progressive
weapons,
`hs1 = "Press ^3[{+activate}]^7 for ^5" +_name+ "^7 Cost: ^1" +wpn_cost+ "^7 ";`
then `self.trig SetHintString(hs1+hs2+hs3);`
(<https://raw.githubusercontent.com/EliotDucky/progressive_weapons/main/zm_progressive_weapons.gsc>).
The older community statement is blunter: told to pass
`&"Press & hold &&1 to buy Olympia [Cost: 500]"`, BluntStuffy answers "remove
the &, that's for localized strings and only works for stock weapons"
(<https://www.ugx-mods.com/forum/scripting/11/wall-buy-hintstring-custom-guns/12155/>).

Not taken because **one thing about it is unresolved**: whether `&&1`
substitutes a passed parameter inside a plain literal, or only inside a
localised string. Every community literal that contains `&&1` passes no
second argument, so those examples do not decide it. The wall buy's price
arrives as exactly that parameter (`SetHintString(stub.hint_string,
stub.cost)`), so a literal would have to either resolve that question or
hard-code the price into the text -- and a baked price that a plan field can
change is the same staleness the wall plates were designed to avoid (5.7.2).
The localised route inherits the stock string's own parameter behaviour and
so has no such question.

**The stock override hook.** `_zm_weapons.gsc:1194-1200` runs a map-supplied
function before a buy is allowed. If `level.func_override_wallbuy_prompt`
is defined, the trigger calls it on itself with the player; the function may
set the hint text, and a false return blocks the buy (Treyarch's comment on
that line says as much).

Community use of it is real but only ever sets the prompt *empty* to hide a
buy -- `self.stub.hint_string = ""; self.stub.cursor_hint = "HINT_NOICON";`
(<https://www.ugx-mods.com/forum/scripting/91/tutorial-one-in-the-chamber-survival-script/16140/>).
No example found sets a non-empty one. It also runs per interaction rather
than once, which is more machinery than a one-line assignment at load time.
Worth remembering if the `.hint` assignment ever turns out to be overwritten
by something later in a play session.

#### 5.7.2 What the generator emits

A map keeps its own table of renamed guns, and a wall plate can still carry
the small print, which will not fit in a prompt. From that table:

- `zmforge.emit.strings` renders `share/raw/english/localizedstrings/<map>.str`
  in the format real maps ship, one entry per renamed gun, text shaped
  `Hold ^3[{+activate}]^7 to buy <NAME> [Cost: &&1]`. The shape is copied from
  a shipped map's own file (`ohm-nabar/zm_building`,
  `english/localizedstrings/zm_abbey.str`:
  `REFERENCE PERK_DOUBLETAP_ORIGINAL` /
  `LANG_ENGLISH "Hold ^3[{+activate}]^7 for Double Tap Root Beer [Cost: &&1]"`
  -- <https://raw.githubusercontent.com/ohm-nabar/zm_building/master/english/localizedstrings/zm_abbey.str>).
- the zone gains `localize,<map>`;
- the server script precaches each string
  (`#precache( "triggerstring", "<ASSET>" );`, the form shipped maps use --
  `zm_building`'s `scripts/zm/zm_abbey_teleporter.gsc:29`) and, inside the
  existing `custom_add_weapons` loader after the two
  `load_weapon_spec_from_table` calls, assigns one `.hint` per renamed gun.

A `renamed=False` entry gets no string: a stock gun should read as a stock
gun.

**The generator's own output has been through the linker** [measured]. `zmforge.emit.strings` rendered `zm_mymap.str`, the file
went to `share\raw\english\localizedstrings\`, and a probe zone declaring
`localize,zm_mymap` linked it with no `ERROR:` line. The six assets
came out of `english/assetinfo/zm_test.csv` under exactly the names the
emitted script references:

```
84,localize,ZM_MYMAP_BUY_PISTOL_FULLAUTO,102,0,||assetlist
85,localize,ZM_MYMAP_BUY_SMG_FASTFIRE,97,0,||assetlist
86,localize,ZM_MYMAP_BUY_FRAG_GRENADE,86,0,||assetlist
87,localize,ZM_MYMAP_BUY_SMG_VERSATILE,91,0,||assetlist
88,localize,ZM_MYMAP_BUY_AR_LONGBURST,94,0,||assetlist
89,localize,ZM_MYMAP_BUY_SHOTGUN_PUMP,90,0,||assetlist
```

So the chain from a map's table of renamed guns to an asset in a fastfile is measured end to
end. What is not measured is the last hop, the engine drawing it.

**The file has to be in place before the link.** [measured] A `.str` that is
generated but not in the tools' `share/raw` tree when the linker runs makes the
linker stop, twice, once per fastfile:

```
^1Localization ERROR: Unable to load "localizedstrings/zm_mymap.str"!
  localize:zm_mymap
```

Moving the file aside and re-linking printed the same two lines, so the
message means what it says and names no path we did not already know. So:

- the install step carries `share/raw/english/localizedstrings/<map>.str`
  when the map has one, the same way as the `.led` and the weapon table, and
  fails if the file is not in place afterwards. A static check of the
  generated output cannot answer this: the output can hold the file while the
  tree the linker reads does not, so the question has to be asked of that
  tree, just before the link;
- `verify.check_localized_strings` makes a declared `localize,` line with no
  `.str` an **error**, which is the question `W5` already asks of a declared
  weapon table. It catches the half of this fault in the generated output, not
  the half in the tools' tree.

Every new asset type is two commitments, one to write the file and one to
carry it, and both need writing down.

**Cost.** One asset type the map already had permission to use, one generated
text file, and one line of script per gun. Nothing about the gun changes: the
buy still hands over Treyarch's `shotgun_pump`, the trick scripts still key on
it, and the weapon icon on the prompt is still Treyarch's. Only the sentence
is ours.

**Still unverified:** what the prompt *renders* has not been checked in
game. The link is measured; the pixels are not. The one thing
to watch on a first play is that the buy is not showing the raw asset name in
capitals, which is how a missing localised string presents (Harry Bo21's page
describes that symptom: the rocket shield's prompt showed its string key in
capitals).

**Languages.** The strings live in the English fastfile, and the build is
English-only, so a player whose game is set to another language is in the same
position as before: the map's other-language fastfiles do not exist. The fix
is the same one the community documents -- ship every language, which for a
map that does not translate means copying the English text under
`LANG_FRENCH` and friends, as `zm_building` does across twelve folders -- and
it is a build-language change, not a design one.

#### 5.7.3 A ported gun's own name

A map that brings its own gun names it in `displayName` in the weapon's GDT, as
community practice and shipped maps do (`MattFiler/zm_alien_isolation`,
`ayz_flamethrower.gdt`: `"displayName" "F1W Nitrogen Cooled"`). A map that
renames somebody else's gun ships a localised string instead, which any map
may do.

### 5.8 The price is customisable, and it is a table [measured]

The counterpart to 5.7, and the reason that section is about *text* and not
about wall buys generally. **A map can charge whatever it likes.** The cost is
the one thing the stock scripts take from data rather than from the engine:
`_zm_weapons.gsc:3362 load_weapon_spec_from_table` reads a string table row by
row, `add_zombie_weapon` (`:529`) writes each row's cost onto a struct in
`level.zombie_weapons[ weapon ]`, and the purchase reads that struct live --
so a later reload of the table also overwrites the price a buy already has.

What the generator emits for a map that prices anything:

1. `share\raw\gamedata\weapons\zm\<map>_weapons.csv`, the map's own table.
   It is an **overlay**: the header plus one row per change, each re-priced row
   being the install's own row with the `cost` column replaced. The 20-column
   order is the install's, because the loader addresses columns by index.
2. `stringtable,gamedata/weapons/zm/<map>_weapons.csv` in the zone.
3. In `<map>.gsc`, before the framework entry:
   `level._zombie_custom_add_weapons = &load_weapon_table;`, and that function
   loading `zm_levelcommon_weapons.csv` first and the map's own second.
   `zm_usermap.gsc:135` installs the stock loader with
   `DEFAULT( level._zombie_custom_add_weapons, &custom_add_weapons )`, and
   `DEFAULT` only assigns while the variable is undefined, so the map's own
   `main()` -- which runs first -- wins. Loading the stock table first is not
   optional: winning the hook means nobody else loads it, and a map that
   skips it does not re-price the level, it empties it.
4. In `<map>.csc`, **after** the framework entry: the same load again. The
   number on the purchase prompt is filled in client side and the client has
   no hook -- `zm_usermap.csc:83` calls `include_weapons()` directly and that
   loads the stock table at `:95`. Without the client half the player is
   charged the map's price and shown Treyarch's.

A custom **weapon** is the same table plus two more things: `weapon,<asset>` in
the zone, and a `bulletweapon.gdf` entity in a `.gdt` registered into
`gdt.db` (`_gdf.PK_id` 16 in the stock database; `zmforge.texture.gdtdb` writes the
same two rows it writes for an image). The linker fails loudly on a `weapon`
line it cannot resolve. It cannot see a *table row* naming a weapon that does
not exist -- a string table is opaque to it -- which is check `W5`.

Evidence. Two probe maps. The first, a usermap whose zone declared its own
table and a weapon of its own, linked clean. The second, `zm_test`, a
generated one-room map whose `smg_standard` buy asks 1337, compiled and linked
under Wine with `stringtable,gamedata/weapons/zm/zm_test.csv` in the
linker's own assetlist. Linking the same map with the table moved aside prints
`WARNING: missing stringTable ...`, writes both fastfiles anyway, and this package's verdict fails it.

**Unverified: everything only a play session can settle** -- what the buy
actually charges, and what its prompt actually says.

---

## 6. The asset manifest for linking

Path: `usermaps/<map>/zone_source/<map>.zone`. Comma-separated lines;
`>` prefix marks a directive, `//` a comment. **[measured on real
manifests; the minimal set links]**

Minimum that linked and played:

```
>class,zm_mod_level
>group,modtools

col_map,maps/zm/<map>.d3dbsp
gfx_map,maps/zm/<map>.d3dbsp

scriptparsetree,scripts/zm/<map>.gsc
scriptparsetree,scripts/zm/<map>.csc
```

The manifest that played, modelled on the stock map template, also
carried `>title,<map>`, `>level.forced_model_lods,-4`,
`>level.force_static_models,1`, `>level.force_view_models,1`,
`>level.force_world_materials,1` **[played; necessity unverified]**.

**Entries real shipped maps carry that the reference omits:**

- `sound,<map>` — every released map lists its sound bank. A link succeeds
  without it, so it is not required for linking; whether its
  absence costs anything at runtime is **[unverified]**. Emit it only if
  a sound bank of that name exists, otherwise the linker will complain
  about a missing asset (**[unverified]** which).
- The localisation companion `usermaps/<map>/zone_source/loc/<map>.zone`
  with `>mode,zm`, `>type,level`, `>expect,core_all`,
  `>expect,zm_common_all`, `>level.xpak_write,<map>`,
  `>linker.animation_mode,ZM`, `ignore,core_common`,
  `ignore_missing_shipped,core_pre_gfx`. A link writes `en_<map>.ff` without
  this file, so it is not required for the English
  fastfile **[measured]**. Emit it as an option, off by default, until a
  build shows it matters.
- `xmodel,skybox_default_day` and `material,luts_t7_default` — the mod
  tools' own ZM template lists both, and our manifest lists neither
  **[measured on Windows]**. A map without them links clean
  and loads, so neither is required; the LUT is a colour-grading lookup,
  so its absence is a candidate explanation for a washed-out image, but
  that is **[unverified]** and needs someone in game with and without the
  two lines. Cheap to add, not yet shown to change anything.

- `material,<name>` lines for materials the compiler reported missing
  only when they genuinely exist in the asset database under another
  path; for `jun_art_wood_plywood_dark03` this is **[unverified]** and
  the warning is benign.

Other asset prefixes that exist (for future features): `xmodel`,
`material`, `image`, `fx`, `xanim`, `weapon`, `stringtable`, `localize`,
`rawfile`, `aitype`, `scriptbundle`, `zbarrier`, `weaponcamo`,
`postfxbundle`, `ttf`, `include` (pulls a `.zpkg` fragment by name
without extension).

The linker labels manifests `csv:` in its dependency traces; it treats
them as generic comma-separated files.

**No per-map `.gdt` asset-database file is required** for a map that uses
only stock assets: a map with none links **[measured]**;
a released usermap with custom assets keeps its GDTs under freely named
files, resolved by asset name, not by file name.

### 6.1 Presentation files [measured on Windows]

Three things decide whether a map looks finished before the player is even
in it, and none of them is an asset in a fastfile:

| What | Where | Fixed name / size |
|---|---|---|
| Loading screen | `usermaps\<map>\zone\loadingimage.png` | 1920 x 1080 (all 38 published examples agree); any PNG the engine can read |
| Menu thumbnail | `usermaps\<map>\zone\previewimage.png` | **no size rule**; 600 x 340 is the template's size and the commonest choice, not a requirement |
| Display name | `>title,<free text>` in `<map>.zone` | free text, not a localised string, but **not as free as it looks**: see below |

Evidence is the mod tools' own map template,
`<root>\rex\templates\ZM Mod Level\usermaps\template\`, which ships
`zone\loadingimage.png` (11,303 bytes, IHDR `00 00 07 80 00 00 04 38 08 02
00 00 00`) and `zone\previewimage.png` (3,825 bytes, IHDR `00 00 02 58 00
00 01 54 08 02 00 00 00`); and Treyarch's shipped example usermap
`usermaps\mp_combine\zone_source\mp_combine.zone`, whose third line is
`>title,Mod Combine` against a folder named `mp_combine`. Published
Workshop maps carry the same two file names flat beside their fastfiles.
`.jpg` is accepted for the loading image as well as `.png`. Full quoted
evidence: format reference §3.6.

Consequences for the generator:

- The linker cannot report any of this. A map with no `loadingimage.png`
  links perfectly and loads on a black screen, so the only place it can be
  caught is a static check over the written files (checks P1-P3 of
  Section 9.7).
- No `.gdt` entity, no `image,` or `material,` manifest line, and no asset
  refresh is needed. The stock `img_t7_mod_loading` / `img_t7_mod_preview`
  images (declared in `model_export\code.gdt`, listed in
  `zone_source\all\assetlist\core_patch.csv`) are the engine's own mod
  artwork and are **not** referenced by a usermap.
- The template itself has no `>title`, so a map built to the template's
  shape shows its asset name in menus. Deriving a display name from the
  map name (`zm_forge_gate` -> `Forge Gate`) is free and always better.
- The default loading screen should be **generated from the map**: a
  top-down plan of rooms, walls, doorways, yards, doors and start points
  is truthful, needs no artwork, and is a pure function of the blueprint.
  An explicit PNG may be supplied instead; it is never resampled, and the
  only size remark it can draw is P1's warning on a loading image that is
  not 1920 x 1080.

---

#### 6.1.1 The title is cut at a comma, and loses its spaces [measured]

`>title` is "free text" only up to the first comma after the directive. The
manifest is a comma-separated file and the linker means it.

The measurement. `zm_example` was given
`>title,My Map, Night` in its `zone_source` manifest and linked.
The linker rewrites an expanded manifest at
`usermaps\<map>\zone_source\loc\<map>.zone` - it held the previous title
before the link and the new one after, so it is the linker's own output - and
what it holds is:

```
>title,MyMap
```

Two separate things happened to that string:

1. **Everything from the second comma on is gone.** ` Night` was dropped.
   A comma in a title is a field separator, so the title ends there. There is
   no escape or quoting to reach for: the only quotes in any shipped `.zone`
   on the install are on four `#include "..."` directives, never around a
   field value, and no shipped `>title` anywhere contains a comma.
2. **The spaces were removed.** `My Map` became `MyMap`.
   This is not specific to the comma case: every generated title shows it.
   `>title,My Map (Night)` comes out as `>title,MyMap(Night)`, and
   `>title,Sample Title` as `>title,SampleTitle`.

The link does **not** fail on either: it returned 2000 with no `ERROR:` line
and both fastfiles written. So a comma silently truncates a menu name and
spaces silently vanish from it.

**Confirmed in game**: the map-selection card shows the
run-together internal name beside the title, exactly as the expanded manifest
carries it. So this is not a quirk of that one file, it is what reaches the
menu.

What survives a `>title`, plainly:

| Characters | Survives? |
|---|---|
| Letters and digits | yes |
| Brackets `(` `)` | yes - `My Map (Night)` kept both |
| Space | **no** - removed, `Sample Title` becomes `SampleTitle` |
| Comma | **no** - the title ends there, and the rest is discarded |

Write a title as one word if it must read correctly. `zmforge`'s `verify`
warns on a comma (check P3) because that throws text away and few titles have
one; it does not warn on spaces, because every readable title has them and the
loss is a property of the toolchain rather than a fault in the map.

What is **[unverified]**: what the game's menu actually draws. The title
string does not appear as plain ASCII in the localised fastfile, and nobody
has read the menu. What is measured is what the linker's own manifest carries,
which is the last place the string can be seen before it goes into the
fastfile. Generators should treat a comma in a title as data loss and a title
as a single word.

#### 6.1.2 The full-screen loading image does not appear for a local map [open, measured]

**Where this question is answered, so two documents do not disagree.** The
mechanism -- loose PNG versus overriding the stock `black` image asset -- is
covered by `mapsource-format-reference.md` §3.6, "The loading screen needs
more than the file", which holds the set/link/restore measurement. This
subsection is the *symptom* and the elimination evidence, and is deliberately
left without a verdict. Until a map load settles
it, neither document asserts a mechanism: what is measured is that a valid
loose PNG alone did not draw a loading screen locally, and that the override
links.

In game, `previewimage.png` works - the map-selection card shows the
generated plan view with its room and zone counts and the title - and
`loadingimage.png` does not appear while the map loads. Since one of the two
works, the difference is the thing to chase. Ruled out by measurement
against the sample of 46 published Workshop items (40 maps and six mods):

- **Not the name.** `loadingimage.png` is what 38 of the 40 maps carry.
  `loadingimage.jpg` appears on 2, one of which carries both. No other
  full-screen name occurs.
- **Not the place.** `usermaps\<map>\zone\`, beside the fastfiles, is where
  the mod tools' own ZM template puts both files
  (`rex\templates\ZM Mod Level\usermaps\template\zone\`) and where the
  launcher's new-map scaffold puts them - a fresh scaffold carries the
  untouched 11,303-byte template pair there. A published item is *flat*: the
  `.ff`, the `.xpak` and both PNGs sit together, so publishing lifts
  `zone\*` up rather than moving the images relative to the fastfiles. The
  preview that *does* work is read out of that same folder, through the same
  directory junction.
- **Not the format, size or bit depth.** Ours is 1920x1080, 8-bit truecolour,
  non-interlaced; so is every published one. Ours is structurally identical to
  published ones: same minimal `IHDR,IDAT,IEND` chunk set, same zlib level. Three published maps ship the template's 11,303-byte file, which
  is *smaller* than our 25,803 bytes, so size is not a floor either.
- **Not "Workshop only" on its own.** Published maps carry the same loose
  file, and a published item carries a generated file correctly.

What could **not** be obtained: the game's own account of what it looked for.
The game keeps no console log by default: `%LOCALAPPDATA%\Activision\CoD BO3`
holds crash reports only, and BO3 writes a console log only when asked.
`BlackOps3.exe` is DRM-packed, and a plain string search finds neither
`loadingimage` nor even `usermaps`, so nothing can be concluded from its
absence. Neither `modlauncher.exe` nor `linker_modtools.exe` contains either
filename, which does say the names are read by the *game* and not by the
tools.

One asymmetry is worth recording as the next thing to try. `code.gdt` declares
two stock image assets, `img_t7_mod_loading` and `img_t7_mod_preview`, with
`baseImage` under `texture_assets\menu_T7\loadscreens\`, and **no shipped
`.zone` references either**. Our map's fastfile packs 244 images and overrides
neither. That is the shape of a placeholder a mod is meant to replace.

**The next test needs one map load.** Replace a built map's
`zone\loadingimage.png` with the tools' own template image (md5
`f4536617deaf66e408fbcb4413dce8ed`, the 11,303-byte file three published
maps ship unchanged) and load that map:

- the template's loading screen appears -> our PNG is at fault despite
  matching every published one, and the generator's encoder is where to look;
- nothing appears -> a loose `loadingimage.png` is not what draws a local
  map's loading screen, and overriding `img_t7_mod_loading` is the route to
  try next.

#### 6.1.3 Publishing: visibility is set after the upload [reported]

The Mod Tools Launcher uploads a map to the Workshop **private and hidden**.
Visibility is opened afterwards, on the map's own Workshop page. So
"friends only" is a setting changed after publishing, not a choice made at
upload time, and a map is never briefly public by accident.

The launcher writes a `workshop.json` beside the fastfiles carrying `Title`,
`Description`, `FolderName`, `PublisherID`, `Tags`, `Type` and `Thumbnail`
[measured: a published item's `workshop.json` carries `PublisherID`]. `Thumbnail` is the **Workshop
page image, not the in-game loading screen**; the launcher can leave it
empty, and community items point it at a PNG inside the map's own folder. Note also that
`Title` here is free text that Steam shows verbatim - it is not subject to the
space and comma losses of 6.1.1, which apply to the `>title` line in the
manifest.

### 6.2 Custom sound [BUILT, measured]

**Status: a custom sound builds from the command line, and this generator
ships one.** The working procedure is at the end of the section. A failed run
comes first, because it is what a broken bank looks like.

The five-step procedure below, run on Windows, stops at the linker, which is
the procedure's own failure branch.

What was done: `sound_assets\tst\test_sound.wav`, which the mod tools ship,
was copied to `zmforge_probe.wav`; the shipped `test_sound` row of
`share\raw\sound\aliases\user_aliases.csv` was cloned into a new bank table
`share\raw\sound\aliases\zm_example.csv` with only the name and
`FileSpec` changed; `sound,zm_example` was added to that map's manifest; and
the map was linked.

What the linker said:

```
ERROR: unable to load file 'sound/zone//zm_example.all.alias.sz'
ERROR: sound aliases failed to load
ERROR: unable to load file 'sound/zone//zm_example.english.alias.sz'
ERROR: sound aliases failed to load
```

It is tempting to conclude from that that the linker loads an
**already compiled** bank, that nothing in `bin` produces a `.sz`, and that
the only candidate, `asseteditor_modtools.exe`, is a GUI. The first half is
a misreading of the extension and the second half is true and irrelevant.
What the run actually got wrong: it wrote the table to
`share\raw\sound\aliases\zm_example.csv`, which is where the UGX wiki says
to put it, and the linker reads `share\raw\sound\zone\<bank>.all.alias.sz`.
The error message names the path it wanted.

Two side facts from the same run. The link wrote **both fastfiles anyway**
(3,985,984 and 960 bytes) while printing those errors, so the "both fastfiles
exist" half of the link rule would have passed it and only the `ERROR:` half
caught it. And its exit code was 2002000 - a fourth distinct linker code, and
this one a real failure, which is one more reason the code is never the
verdict.

**Established.**

- A script never names a sound file, it names an **alias**:
  `_zm_powerup_nuke.gsc:126 zombies_nuked[ i ] playsound( "evt_nuked" );`.
  Shipping a custom sound means shipping an alias, not a path.
- A map's zone declares a **sound bank** named after the map, and every
  released usermap carries one: `sound,zm_nuked` in the verbatim minimal
  zone in the format reference §3.4.
- The engine can declare it: `commit(sound_bank=True)` writes `sound,<map>`,
  and any mechanic can declare a bank through `CustomScript.assets`,
  validated by `AssetRef` and checked by Z17.
- `gamedata/audio/zm/<map>_vox.csv` is **not** the alias table to copy. Its
  rows are `category,event,alias,chance`
  (`zm_factory_vox.csv:1 general,crawl_spawn,crawler_start,30`): a
  dialogue-selection table over aliases that already exist.
- No zone file has been seen to declare a `shellshock` asset (§3.3 lists the
  twenty-two prefixes that have appeared), so a usermap cannot ship one; a
  script calling `shellshock()` relies on the asset being in a zone the map
  already loads.

**Settled by building it.**

A `.sz` is not a compiled format. `file` calls Treyarch's own shipped
`pc\raw\sound\zone\mp_sector.all.alias.sz` **CSV text**; its first line is a
102-column header, it has 646 data rows, and its line endings are CRLF.
Writing that file is building the bank.

Four rules, each measured, each silent or near-silent when broken:

1. **Named after the map.** `sound,<bank>` is the name the linker opens
   `<bank>.all.alias.sz` under.
2. **In the shared raw tree**, `share\raw\sound\zone\`, not the
   per-platform `pc\raw\sound\zone\` where `mp_sector` sits. The failed run above broke this rule and the naming
   one together.
3. **At most 104,729 rows**, about 160 times what a map uses.
4. **Every required column carries a value.** Fifty-three of the 102, listed
   in `zmforge.emit.sound._REQUIRED_DEFAULTS`. Treyarch's own example row in
   `user_aliases.csv` leaves them blank, which reads like template
   inheritance; the linker does not inherit. A bank of rows shaped like that
   example produced 108 `ERROR:` lines, two per column:
   `row 1 had empty required column Storage`, `Unknown Storage ''`.

Five companion tables sit beside the bank and two of them are load-bearing:
without `<map>.all.ducklist.sz` and `<map>.all.reverb.sz` the link stops with
`ducklist failed to load` and `reverb failed to load for zone <map>`.
`ambient`, `musiclist` and `scriptid` are written header-only. The reverb
table is the install's own `share\raw\sound\reverb\common_reverb.csv` passed
through; passing `ambients\ambient_mod.csv`'s row through instead fails with
`Unknown defaultRoom 'yes'`.

The wave file goes under `sound_assets\`, which is what a row's `FileSpec` is
relative to: Treyarch's rows carry `FileSpec
amb\electronics\wall_servo\wall_servo_a_00_01.wav` beside `FileSource
Q:\t7\pc\game\sound_assets\amb\...`. Format per the UGX wiki and the tools'
one shipped example: 48 kHz, signed 16-bit PCM.

**Proved** by building a one-room probe map with one
synthesised 4.5 kHz looping alias, under Wine: compile exit 0 with no
`ERROR:`, link with **zero** `ERROR:` lines, both fastfiles written, and

```
zone_source/all/assetinfo/zm_test.csv:1149,sound,zm_test.all,7179,0,||assetlist
zone_source/all/assetinfo/zm_test.csv:sound,32,1
```

**Not proved, and it is the part that matters to a player:** that the alias
is audible. The linker never mentions the wave file, and the map's `.xpak` is
the same size with a valid bank as with a broken one, so where the audio data
comes from at run time is unread. Somebody has to load the map and fire the
gun.

**Consequence for a ringing tone.** Stock zombies wires up no ringing loop.
The flashbang plays `level.sound_flash_loop` (`_flashgrenades.gsc:232`),
which shared code sets to `""` at `:15-17` and nothing in the zombies or
campaign trees assigns. The only tinnitus loop in the script tree,
`evt_outro_tinnitus_lp` (`cp_prologue_player_sacrifice.gsc:966`), is a
campaign alias whose bank a zombies map does not load. So the engine plays
no ringing alias by default and takes one, with its bank, as a parameter.

## 7. The build chain

### 7.1 Installation layout [measured on Windows]

- Mod tools root: the Steam library folder
  `steamapps\common\Call of Duty Black Ops III 455130\` (the Steam app
  id **455130** is appended to the folder name). In a default Steam install:
  `C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130`.
  Make the root configurable (environment variable or explicit argument);
  never hard-code a drive.
- The game executable lives in a **different** folder (the game's own
  Steam install), not under the tools root. Launching the game is a
  separate concern from building.
- Under the root: `bin\` (tool executables), `gdtdb\gdtdb.exe`,
  `map_source\zm\<map>.map`, `map_source\_prefabs\zm\zm_core\` (stock
  prefabs), `map_source\_prefabs\zm\<map>\` (per-map prefabs),
  `share\raw\scripts\zm\<map>.gsc|.csc`, `share\raw\maps\zm\` (compiler
  output), `share\assetconvert\` (asset cache),
  `usermaps\<map>\zone_source\<map>.zone`, `usermaps\<map>\zone\*.ff`
  (linker output).
- Create `map_source\zm\`, `share\raw\scripts\zm\` and
  `usermaps\<map>\zone_source\` yourself when writing; they may not
  exist for a new map. `share\raw\maps\zm\` and `usermaps\<map>\zone\`
  existed on the measured install; whether the tools create them is
  **[unverified]**, so check before running a stage and report a
  missing directory as a configuration error.

### 7.2 Environment and working directory [inherited, used]

Every tool is started with:

- working directory `<root>\bin`;
- environment variables `TA_GAME_PATH=<root>\`, `TA_TOOLS_PATH=<root>\`,
  `TA_LOCAL_ASSET_CACHE=<root>\share\assetconvert\` (all with a trailing
  backslash), on top of the inherited environment.

Without the `bin` working directory the compiler's file system start-up
fails to resolve relative search paths and navmesh generation fails with
a message about being unable to load navigation mesh generation settings
**[inherited]**.

### 7.3 Stages

Each stage: executable, arguments, reads, writes, how to judge it.

**Asset database refresh**
`<root>\gdtdb\gdtdb.exe /update`. Reads every `.gdt` under the root.
Prints `gdtDB: updating` then `gdtDB: processed (N GDTs) (M assets) in S sec`.
Fails with `ERROR: Duplicate '<type>' asset '<name>' found in <file>:<line>`.
Exit code 0 on success **[measured]**. Needed only when assets
changed; a generated map with stock assets does not need it after the
first run.

**Compile**
`<root>\bin\cod2map64.exe -platform pc <mode flags> -loadFrom <root>\map_source\zm\<map>.map <root>\share\raw\maps\zm\<map>.d3dbsp`

- Mode flags: `-onlyents` for entity-only recompile (seconds; **does not
  re-read per-map prefab files [inherited] and does not touch geometry
  or navmesh**), or `-navmesh -navvolume` for a full compile (geometry,
  navigation mesh and volume) **[measured: a full compile uses exactly
  these]**. Without the navmesh flags the AI has no pathing data
  **[inherited]**.
- Writes `<map>.d3dbsp`, `<map>_navmesh.hkt`, `<map>_navvolume.hkt` under
  `share\raw\maps\zm\`.
- Exit code 0 on success **[measured]**, also 0 with a leak and 0 with
  missing materials, so parse the log:
  - leak: a banner of asterisks around the word `leaked`, and
    `WROTE BSP LEAKFILE: <path>.lin`. The map is unsealed; find the seam
    by loading the `.lin` in Radiant.
  - `WARNING: Material '<name>' is missing` (collect unique names).
  - the umbra line saying the volume is not set (missing umbra volume).
  - `restricting BSP to sky brushes` (expected when the sky shell and
    umbra volume are both present).
  - `building curve/terrain collision...` (expected when patches exist).
  - the `terrain patches with caulk were discovered` banner (a defect).
  - `ERROR:` lines (real failures, including the sealing error when an
    umbra volume exists without a sky shell).
- Duration: about a second for entities-only, seconds to a minute for a
  small full compile.

**Lighting bake**
`<root>\bin\radiant_modtools.exe -ledSilent +<quality> +localprobes +forceclean +recompute <root>\map_source\zm\<map>.map`
with quality one of `draft`, `medium`, `final`. The quality and option
switches use a `+` prefix; the map path is positional; there is no
`-platform` and no `-loadFrom`. Writes `share\raw\maps\zm\<map>.led`
(and probe data). **It is a GUI program, but what it needs is a display
and a GPU, not a person.** Started without an interactive desktop it
reaches about 840 MB working set, accrues about 0.2 CPU-seconds in four
minutes, prints nothing and never exits **[measured]**. `WineRunner` on Linux
supplies what the bake needs -- a real X server on the GPU, an embree
import-table shim, and DXVK for D3D11 -- and bakes `zm_forge_gate`'s `.led`
in 17 s this way **[measured; mechanism in `docker/bo3-wine/SETUP.md`]**. A reimplementation must: (a) refuse to start
the bake unless the runner reports `provides_interactive_desktop = True`
(the name is historical; it means "this runner can supply what the bake
needs" -- an interactive Windows session and `WineRunner`'s own X server
both satisfy it), or (b) start it and detect a stall (CPU time not
advancing over 60 seconds with no output) and kill it, reporting "needs
interactive desktop". Without the bake the linker prints a warning about
failing to open the `.led` file and falling back to preview lighting, and
the map renders washed out **[inherited]**. The Mod Tools Launcher's
"Light" checkbox runs the same program.

**Link**
`<root>\bin\linker_modtools.exe -language english -modsource <map>`

- Reads the manifest and everything it references, converts assets on
  first use (cached under `share\assetconvert\`).
- Writes `usermaps\<map>\zone\<map>.ff` and
  `usermaps\<map>\zone\en_<map>.ff` (prefix `en` for English; other
  languages use their own two-letter prefix: `fr`, `ge`, `it`, `sp`,
  `ru`, `po`, `br`, `ja`, `ko` for french, german, italian, spanish,
  russian, polish, portuguese, japanese, korean **[inherited,
  unverified]**; only `english`/`en` was exercised).
- **The exit code is never 0 and is not stable.** Seven successful links
  returned 154000 (cold, 97 s, 152 mesh-conversion warnings; and a
  2 s re-link with 24 warnings) and 2000 (four fully cached ~1.8 s runs
  with 497 bytes of output and no warnings) **[measured]**. It is not a
  warning count and not an error count. Do not read it as a verdict.
- The linker does not print a `There were N errors and M warnings`
  summary in this version **[measured]**.
- Success is decided from evidence: no line matching `ERROR:` (after
  stripping `^` colour codes) **and** each of the two fastfiles on disk
  with a size above zero once the run finishes. A cached re-link leaves the files' mtime
  alone, so "rewritten by this run" is informational, not required.
- Expected tail on success: `done: <m>m<s>s` for the main fastfile then
  `Linking "en_<map>" ... done: <time>`.
- Failure examples from the field: `^1ERROR: Lua not supported` and
  `UNRECOVERABLE ERROR: ^1SCRIPT ERROR: No generated data for '<script>.gscc'`.
- Warning noise to ignore: per-asset lines like
  `^3DROPPED VERTS. N warnings encountered while processing xmodel '<asset>'`.
- Duration: 1-2 minutes cold for a small map, 2 s cached; large maps
  5-10 minutes cold.

**Run**
In-game console `devmap <map>`, or Mods > Custom Games. Not automatable
without an interactive desktop: the game needs one and exits with it.

### 7.4 Output handling

Tool output contains `^N` colour codes (strip for display) and,
occasionally, bytes that are not valid in the console code page. Decode
with replacement, never strictly: a single undecodable byte otherwise
throws away the whole result (Section 10, item K12). Always persist the
full raw log to a file next to the stage result, and return only a
structured summary plus the log path.

### 7.5 Stage ordering

Full build: refresh (optional) → compile full → bake (needs a runner with
`provides_interactive_desktop`, Section 7.3) → link. Fast iteration on entities: compile `-onlyents` → link. The
chain stops at the first stage whose *evidence* says it failed, and the
result names that stage.

---

## 8. Public interface (this design)

This section is a design, not a description of the reference. Where it
departs from the reference, it says why. Names introduced here are the
intended public names (Section 0.3).

### 8.1 Why this shape

The reference exposes many flat tools that each open the map file from disk,
append an entity or a few brushes, save, and (for some) regex-edit the
script. Consequences: every call re-parses and rewrites a growing file;
cross-file invariants (zone name here, `init_zones` there, door flag in
a third place) are enforced by convention in each helper rather than by
a model; the script is patched, so anchors drift; per-concern prefab
files mean the fast entity-only compile does not see perk moves; and
build stages report exit codes that mean nothing.

The design below keeps one in-memory model, derives every file from it,
validates the model as a whole before writing, writes all files in one
commit, and reports build stages by evidence.

### 8.2 Layers and modules

```
mapsource/     text format: document model, reader, writer, number formatting
solids/        convex-solid maths: half-spaces, winding, box, wedge, validation, overlap
surfaces/      patch grids and heightfields: meshing, chunking, orientation, sampling
blueprint/     the map model: rooms, openings, yards, terrain, zones, spawns, doors, machines, lights
emit/          blueprint -> mapsource document, server script, client script, manifest
toolchain/     stage runners (local and Wine), evidence parsers
verify/        static conformance checks over emitted files and over the blueprint
recipes/       compositions (three-room template, barricaded start room)
facade/        thin adapters for a CLI and for an MCP server; no logic
```

Dependencies point downward only. `blueprint` knows nothing about text
formats; `emit` knows nothing about tools; `verify` reads files through
`mapsource` and never through `emit`'s in-memory objects (so it tests
what was written).

### 8.3 Core types

- `Bounds(mins, maxs)`: normalised on construction; raises on a
  non-positive extent unless created through `Bounds.degenerate_ok`.
- `Facing`: one of `north`, `south`, `east`, `west` (yaw 90 multiples)
  or an explicit `Angles(pitch, yaw, roll)`. Every placement takes a
  `Facing`; the conversion to a prefab-specific yaw lives in one table
  in `blueprint` (perk fronts face -Y at yaw 0, the pack-a-punch -X,
  the mystery box and barricades +Y, and so on: appendix B), so callers
  say "facing into the room" once.
- `Material(name)` and `FaceMaterials(default, per_face={...})`.
- `Blueprint`: the whole map model. Elements are added through the
  operations in 8.4 and referenced by returned handles (`RoomRef`,
  `ZoneRef`, `DoorRef`, ...). Every element has a stable `id` the caller
  chooses or the blueprint assigns, so a re-run with the same inputs
  yields the same ids and the same GUIDs (derive GUIDs from a per-map
  seed plus the element id; use random UUIDs only when no id exists).
- `Project(name, tools_root)`: owns a `Blueprint`, knows every path under
  the tools root, and performs `commit()`.
- `StageOutcome(stage, ok, evidence, exit_code, duration_s, log_path,
  artifacts)`: `ok` is a boolean derived by the rules of Section 7;
  `evidence` is a list of short strings saying why (`"both fastfiles
  present"`, `"no ERROR lines"`, `"leak banner found"`).
- `Report(findings)`: from `verify`, each finding with `severity`
  (`error`/`warning`), `code` (stable identifier), `message`, optional
  `position` and `element_id`.

### 8.4 Operations

All operations validate their own arguments and raise a typed error
(`BlueprintError` subclasses: `InvalidBounds`, `OpeningDoesNotFit`,
`UnknownMaterial` (warning by default, error in strict mode),
`UnknownZone`, `DuplicateId`, `NotOnFloor`). Nothing touches disk until
`commit`.

**Project**

- `Project.create(name, tools_root, *, seed=None) -> Project`. Name must
  match `^zm_[a-z0-9_]+$`. Fails if the map exists unless `overwrite`.
- `Project.open(name, tools_root) -> Project`. Loads the blueprint from
  the project's stored model file (`<map>.blueprint.json` next to the
  map source). If only a `.map` exists (foreign or older), loads it as
  an `ImportedMap` element that is preserved verbatim and reports that
  blueprint operations cannot edit its contents.
- `project.commit(*, partition_prefabs=False, loading_screen=True,
  loading_image=None, preview_image=None) -> CommitResult`
  (`loading_screen` writes the two PNGs of Section 6.1; the two image
  arguments take PNG bytes or a path instead of the generated plan)
  (written paths, hashes, the `Report` from a pre-commit verify; refuses
  to write when the report has errors unless `force`). Writes: top-level
  map, optional per-concern prefab maps, server and client scripts,
  manifest, terrain record, blueprint file. All writes are
  temp-file-then-rename. Default is **everything in the top-level map**
  so that the entities-only compile sees every change; the prefab
  partition is opt-in for mappers who want Radiant's tree organised the
  way stock maps are.

**Geometry (on `project.blueprint`)**

- `add_block(bounds, materials) -> SolidRef`
- `add_slab(footprint_bounds_xy, z, thickness, materials) -> SolidRef`
- `add_wedge(bounds, rise_toward: Facing, material) -> SolidRef`
- `add_steps(base, count, depth, height, width, toward: Facing, material) -> SolidRef`
- `add_room(bounds, wall=16, openings=[Opening(side, width, height,
  sill=0, offset=0)], roofed=True, materials=RoomMaterials(wall, floor,
  ceiling)) -> RoomRef` with `.interior: Bounds`, `.floor_z`, and
  `.opening(index) -> OpeningRef` (its world bounds, for doors).
- `add_yard(bounds, attached_side: Facing, wall=16, materials) -> YardRef`
- `enclose(playable: Bounds | None = None, gap=128, thickness=32,
  sun_preset="default_day", probe=False) -> EnclosureRef`: the sky shell
  plus sun, umbra and fpstool volumes. With `playable=None` the blueprint
  computes the union of all rooms and yards at commit time, so the
  caller cannot get the bounds wrong. Exactly one enclosure per map.
- `add_terrain(heightfield: HeightField, anchor, cell, style="mesh" |
  "columns", materials, chunk=8, lift=2, post=PostProcess(...)) -> TerrainRef`
  with `.surface(x, y) -> SurfaceSample(found, z, spread)`. `anchor` and
  `cell` are a request: a field that comes within one cell of every wall of
  the room it lies in is fitted to that room's interior (Section 3).

**Gameplay**

- `set_player_start(position, facing, spread=32) -> None`: emits the
  respawn-set struct and four initial-spawn structs (slots 1-4 spread
  along the axis perpendicular to `facing`). One per map; calling again
  replaces.
- `add_zone(name, bounds | RoomRef, *, starting=False) -> ZoneRef`.
  Exactly one zone must be `starting`; it becomes `init_zones[0]`.
  Others follow in insertion order.
- `add_riser(zone, position, facing, kind="rise" | "walk" | "drop",
  factory=True) -> SpawnRef`: the struct plus (by default) a factory
  entity. `position.z` is checked against the floor under it (a room
  floor or a terrain sample) and rejected if more than 8 above it
  (`NotOnFloor`), unless `allow_float`.
- `add_window(zone, room, side: Facing, offset=0, *, yard_depth=None,
  width=96, height=112, sill=0, hide_debris=False, light=True)
  -> WindowRef`: cuts the opening in that wall (the room must be a
  blueprint room, not imported), adds the yard on the outside if none
  covers the spot (`yard_depth=None` means the implementation's default,
  which must be at least the Section 2.7 minimum; 176 played), places the
  barricade prefab at the wall's interior face, the linked riser outside
  it, and a light in the yard. One call, no coordinates to get wrong.
  **The opening's numbers are stated once, in Section 4.6, and are not
  repeated here**: the defaults are the prefab's own measured hole, and
  an opening that does not contain the prefab's traversal channel is
  refused rather than emitted, because it compiles, links, looks right in
  the editor and is dead in play.
- `add_door(between: (ZoneRef, ZoneRef), at: OpeningRef, price, flag,
  model="p7_zm_der_door_buy_std_onepiece" | None, slide=None) -> DoorRef`:
  door box = the opening's bounds thickened to the wall; the trigger is a
  slab across it (`trigger_margin` 16 at each jamb, `trigger_depth` 64 each
  side, the opening's own height); model yaw from the wall orientation; the
  zone edge and flag go into
  the script model. `flag` defaults to `enter_<zone b>`.
- `place_perk(kind, position, facing) -> MachineRef` where `kind` is one
  of the free slugs of Section 4.7; accept the common community names
  for each perk as aliases. Records the script module.
- `place_pack_a_punch(position, facing)`, `place_power_switch(position,
  facing)`, `place_wall_weapon(kind, position, facing, chalk=True)`,
  `place_mystery_box(position, facing, price=950, starting=True,
  chest_name=None)`, `place_light(position, colour, radius, stops)`,
  `strew_props(footprint, palette, spacing, density, seed, keep_clear=[...])`.
- `set_dog_rounds(enabled: bool)`: default off; turning it on without
  dog spawners is a verify error.

**Inspection (read-only, work on the blueprint or on a parsed map)**

- `blueprint.elements(kind=None) -> list[Element]`
- `blueprint.find(id) -> Element`, `blueprint.near(point, radius) -> list`
- `mapsource.read(path) -> Document`, `Document.entities(classname=None)`

**Verify**

- `verify.blueprint(bp) -> Report` (model-level: agreements of Section
  4.14, one starting zone, every zone has at least one spawn set entry
  or is reachable by a door, every room has a light, enclosure present,
  perks have modules, dog flag consistent).
- `verify.files(project) -> Report` (parses the written files and runs
  Section 9's static checks).
- `verify.stages(outcomes) -> Report` (reads stage logs: leak, missing
  materials, preview-lighting fallback, umbra warning).

**Toolchain**

- `Toolchain(tools_root, runner=LocalRunner() | WineRunner(...))`
- `.refresh_assets() -> StageOutcome`
- `.compile_bsp(map, mode="entities" | "full") -> StageOutcome`
- `.bake_lights(map, quality="medium") -> StageOutcome`; raises
  `NoInteractiveDesktop` when the runner cannot provide one; otherwise
  applies the stall detector of Section 7.3.
- `.link_fastfiles(map, language="english") -> StageOutcome`
- `.run_chain(map, stages=("compile_full", "link"), stop_on_failure=True) -> ChainOutcome`
  (list of `StageOutcome`, overall `ok`, `failed_stage`).

Runners are the only place that knows how a process is started: locally
(subprocess with the env of Section 7.2), or under Wine with `WineRunner` (Section 7.3). Both return the same
`StageOutcome`.

### 8.5 Facade

The CLI and the MCP adapter expose the operations above one-to-one with
JSON-friendly arguments (lists for points, strings for facings). They
contain no logic beyond argument conversion. A hot-reload tool for
development belongs to the adapter, not to the library.

### 8.6 Where the reference design is poor and what changes

| Reference behaviour | Problem | This design |
|---|---|---|
| Each helper loads, mutates and saves the map file | O(file) per call; no whole-map validation; partial writes on error | One in-memory blueprint, validated, committed atomically |
| Script edited by regex around anchors | Anchor drift, lost line endings, duplicate lines when anchors move | Script regenerated from the model every commit; hand code isolated |
| Perks/box/weapons in per-concern prefab maps | Entity-only compile cannot see them; three extra files to keep consistent | Top-level by default; partition opt-in |
| Zone name suffix `_zone` appended implicitly | Callers guess whether to pass it; strings compared in four places | Zone names are ids on `ZoneRef`; strings emitted from one place |
| Spawner Z passed by the caller | Floating spawners shipped repeatedly | Z checked against the floor at add time |
| Enclosure bounds passed by the caller | Wrong bounds leak or clip rooms | Computed from the blueprint unless overridden |
| Success judged from exit codes | Linker never exits 0; compile exits 0 on leaks | Evidence-based `StageOutcome` |
| Bake started blindly | Hangs forever headless | Interactive-session check plus stall detector |
| Stairs as overlapping boxes | Trips the overlap check; more BSP work | Non-overlapping columns |
| Many flat tools, several of them layout-specific recipes with baked-in coordinates | Hard to discover; coordinates duplicated across recipes | Small core set plus `recipes/` that call the core with parameters |

---

## 9. Conformance test plan

A reimplementation is correct when all of the following hold. Static
checks run on the *files written by commit*, parsed back with the
reader, not on in-memory objects.

**Which list is authoritative, and what this one is for.** The table of
checks that actually run is `src/zmforge/verify/registry.py` -- 144 rows,
139 automated and 5 that need a person. `docs/playable-map-requirements.md`
states those counts and `tests/test_requirements.py` asserts them there. `docs/playable-map-requirements.md` is its prose mirror, organised
by symptom, and it names every row. This section is **not** that list and
is no longer maintained as a copy of it: it is the properties the
specification itself asserts, written so a reimplementation can be tested
without this package's code. Where the two disagree about a rule, the
registry is the authority, because it is what runs.

Two consequences:

- Codes cited elsewhere in this specification but not defined below --
  `Z19` through `Z27`, `W1` through `W6`, `M1`, `M2`, `M3`, `M5`, `N1`
  through `N4`, `L2` and `H1` (there is no `M4`, and no `L1`) -- are
  defined in the registry and in the requirements
  document, and deliberately not restated here. The three the text cites
  are `Z26` (Section 4.1.1: a map with more than four spawn slots must
  lift the player cap itself), `W3` (Section 4.10: a wall buy's emitted
  yaw puts its chalk and its prompt in the room rather than in the wall)
  and `Z23` (Appendix B: a prefab emitted at a yaw that does not put its
  measured front where it was asked to face).
- `Z13` and `Z15` each carry **two** meanings, one at model level and one
  at file level, in this section and in the registry alike. That is
  deliberate rather than a collision: renaming either would break
  assertions in the suite and in callers. Both are labelled below.

### 9.1 Text format properties (per emitted `.map`)

- F1. First line is exactly `iwmap 4`; second is `"script_startingnumber" 0`.
- F2. Every line between the header and the first `// entity` is a layer
  declaration `"<path>" flags ...`.
- F3. Entities are numbered `// entity 0..N-1` consecutively; brushes
  inside each entity `// brush 0..M-1`.
- F4. Entity 0 has `"classname" "worldspawn"`.
- F5. Every entity and every brush has a `guid "{...}"` first line with a
  valid upper-case braced UUID; all GUIDs in the file are unique.
- F6. Every key/value line matches `^"[^"]+" ".*"$`; the only exceptions
  are `guid`, `layer`, and the header line.
- F7. No number anywhere in the file contains `e` or `E`; every number
  matches `^-?\d+(\.\d+)?$`; no `-0`.
- F8. Every face line has exactly three point triples, a material token,
  six numbers, `lightmap_gray`, six numbers, then optional known
  trailing tokens.
- F9. Every patch block has, in order: optional `contents ...;`,
  `toolFlags;`, material, lightmap, four integers `W H T1 T2`, then
  exactly W groups of exactly H `v` lines each with 3 + 4 numbers (plus
  an optional `c` and four integers).
- F10. Round trip: `write(read(write(bp))) == write(bp)` byte for byte.
- F11. Foreign round trip: for each real BO3 map in the test corpus,
  `read` then `write` preserves entity count, per-entity key/value
  multiset, brush count, face count, patch dims and control counts, and
  all trailing tokens.
- F12. Line endings: files created by the generator are LF; a file read
  with CRLF and written back keeps CRLF on every line.
- F13. Shipped shape: every `// brush` container the generator writes has a
  line-kind shape (guid / layer / contents / face / keyword / inner block)
  that occurs in the mod tools' own `map_source` or the public corpus. The
  ledger of shipped shapes is measured against the mod tools, counts only, no
  content. F9-F11 alone can pass a file `cod2map64` refuses.

### 9.2 Geometry properties

- G1. Every brush passes Section 2.8 steps 1-5 under the inward reading
  (non-degenerate, volume ≥ 1, not inverted, no unused plane). Test on
  every primitive with random bounds, including bounds crossing zero and
  bounds with fractional coordinates.
- G2. Box brush: eight unique vertices equal to the corners of
  `mins`/`maxs`; volume equals the product of extents.
- G3. Wedge: five planes; volume equals half the box volume; the highest
  vertex lies on the high end.
- G4. Room decomposition: the union of the six boxes equals the outer
  box minus the interior box (test by voxel sampling at 1-unit or
  4-unit resolution); no pair of boxes overlaps by more than 0 units.
- G5. Room with openings: the union of all wall pieces equals the wall
  box minus the union of opening boxes; pieces do not overlap; each
  opening box is fully void.
- G6. Yard: the interior is enclosed on five sides and open only on the
  attached side; a 4-unit flood fill from the yard interior cannot reach
  any point outside the yard's outer bounds except through the open
  side. (This is the check that caught the corner-slot defect.)
- G7. Enclosure: the six sky slabs leave no gap; a flood fill from the
  playable interior never escapes the outer bounds; all rooms and yards
  lie strictly inside the inner bounds.
- G8. Stairs: `n` boxes, mutually non-overlapping, step `i` top at
  `base_z + (i+1)h`.
- G9. Face materials: in a generated room, each hull box has exactly one
  non-caulk face and it faces the interior; opening pieces have six
  visible faces.
- G10. Overlap scan (Section 2.8 step 7) over all structural world
  brushes of a committed demo map yields zero findings.

### 9.3 Terrain properties

- T1. Columns: number of emitted boxes equals the number of cells with
  positive rounded height (merged runs counted once); every box top
  equals `oz + H` of its cell; no zero-height box.
- T2. Mesh: control-point count per chunk ≤ (k+1)²; adjacent chunks
  share edge control points exactly; the union of chunk footprints
  equals the padded grid footprint `(N cells) * c`; every chunk has its
  outer index increasing in +X and inner in +Y; each chunk is **one**
  `mesh` block with **no `contents` line at all** and the visible
  material, and carries **no coincident `weaponClip` twin** -- Section
  3.2 rules out the twin, because `weaponClip` *replaces*
  the default contents rather than adding to it, so a twinned chunk is
  not solid and the player falls through the ground; no patch uses
  `caulk`. Solid fill under the mesh is the model half of Z15, not this
  property.
- T3. Lookup, columns: for 100 random points inside random cells,
  `surface(x, y).z` equals the emitted box top within 1e-6; for points
  one cell outside the low edges, `found` is false.
- T4. Lookup, mesh: at every control point the lookup returns the control
  height exactly; along cell edges it is linear between the two corner
  heights; the returned value never leaves `[min, max]` of the four
  corners.
- T5. Post-processing: each pass is a no-op at its default; feathering
  brings boundary cells to floor height; pads flatten exactly the cells
  whose centres are within radius.

### 9.4 Gameplay properties (parse the committed map and script)

- Z1. Exactly one `player_respawn_point` struct, and at least four
  `initial_spawn_points` structs with `script_noteworthy initial_spawn`
  and `script_string` containing `zclassic_start_room`; **none of them
  carrying `script_int`** (Section 4.1: on this struct it is the team
  side, and 1 or 2 is deleted every game); pairwise distance ≥ 32; no two
  at the same point; every one of them over floor. A caller that asked
  for a slot count may pin the number exactly rather than at-least-four.
- Z2. The script does not assign `level.default_start_location`, or
  assigns it `"start_room"`.
- Z3. Every `info_volume` with `script_noteworthy player_volume` has a
  `targetname` that appears as an `init_zones[N]` value; the count of
  such volumes equals the count of `init_zones` entries; `init_zones[0]`
  is the zone marked starting. A volume naming a zone the script never
  **registers** (no `init_zones` entry and no `add_adjacent_zone`
  argument) or never **enables** (no `init_zones` entry and no chain of
  `add_adjacent_zone` flags from one) is an error, not a curiosity:
  `zone_is_enabled` is false for it forever, so the volume is not
  playable area and standing in it is the instant death of Z18. A
  registered zone name that no volume carries is an error too —
  `zone_init` finds no volume for it.
- Z18. Nowhere a player can stand is outside every player volume. Tested
  on the model, not the file, because the model knows what is walkable:
  every room floor, every walkable massing solid's top, every opening
  whose sill is within a step of the floor, and every terrain cell, with
  a player's hull (30 across, 72 tall) placed on it. The covered set is
  the union of the enabled zone volumes grown by half a hull, and a
  touch that is exactly on a plane does not count — whether `IsTouching`
  accepts it is unmeasured and a map that needs that answer is one unit
  from killing the player. A room or a massing the map declares
  `reachable=False`, and a yard (the barricade stops the player at the
  wall line), are not standing positions.
- Z4. Every `script_struct` with `script_noteworthy` in {riser_location,
  spawn_location, faller_location} has a `targetname` equal to the
  `target` of exactly one zone volume, a non-empty `script_string`, and
  (for `find_flesh` structs) XY inside that volume's brush bounds;
  barricade-linked structs have XY inside a yard.
- Z5. At least one entity with `script_noteworthy zombie_spawner`; each
  names one of the two zombie `aitype`s the install ships. Error on
  anything else, warning on `actor_spawner_zm_factory_zombie` (it works;
  its animation table names no jump, mantle, climb or
  `traverse_procedural` move), pass on
  `actor_spawner_zm_usermap_zombie`, which is what this package emits
  and what `share/zone_source/zm_levelcommon.zone:51` declares for a
  usermap `[measured]`.
- Z6. Spawn struct Z is within 8 units above the floor surface under it
  (room floor or terrain sample); never > 128.
- Z7. For each `trigger_use` with `targetname zombie_door`: its `target`
  names at least one `script_brushmodel` and (if a model was requested)
  one `script_model`, all sharing `script_vector`; it has an explicit
  `origin` inside its brush; its `script_flag` appears in exactly one
  `add_adjacent_zone` call whose two zone names are both zone volume
  targetnames; `zombie_cost` is a positive integer.
- Z8. Every `misc_prefab` barricade with a `script_string` has exactly
  one riser struct with the same `script_string`, 96 ± 1 units away in
  the barricade's outward direction, facing back at it.
- Z9. For every perk prefab path in the map, the script contains the
  matching `#using` line (Section 4.7 table); for pack-a-punch likewise.
- Z10. Script order: `level.dog_rounds_allowed = <0|1>;` occurs before
  `zm_usermap::main();`, which occurs before `level.zone_manager_init_func`,
  before all `init_zones[N]`, before `zm_zonemgr::manage_zones`. If the
  flag is 1, the map contains at least one `zombie_dog_spawner` entity
  and one `dog_location` struct.
- Z11. Exactly one `volume_sun`, one `umbra_volume`, six `sky` slabs
  forming an enclosure (G7), and at least one `light` per zone with its
  origin inside that zone's interior and below the ceiling slab.
- Z12. Every material on every brush face and patch is in the
  known-clean catalogue, or the report lists it as a warning (strict
  mode: error).
- Z13 (model level; the code carries two meanings, see the preamble).
  Every `misc_model` the emitted document places is a name cod2map64
  resolved when probed against the mod tools, or one a `.gdt` in the install
  declares; every `misc_prefab` path exists under `map_source/_prefabs`.
  A name the compiler reported as `Missing xmodel` is an error; a name
  nobody has probed is a warning. The ledger is
  `src/zmforge/blueprint/installed_assets.json`, measured with a probe map
  the mod tools compile; `scripts/scan-local-tools.py` refreshes its list
  of models that compile but do not link. A stock model can still stop a
  compile: `zombie_sign_please_wait`, read out of shipped `zm_giant.map`, is
  one. Without a ledger the check is one warning, never an error.
- Z13 (file level). The client script calls `zm_usermap::main();` inside
  `main()`.
- Z14. Manifest contains `>class,zm_mod_level`, `>group,modtools`,
  `col_map,maps/zm/<map>.d3dbsp`, `gfx_map,maps/zm/<map>.d3dbsp`,
  `scriptparsetree,scripts/zm/<map>.gsc`, `scriptparsetree,scripts/zm/<map>.csc`.
- Z15 (file level; its model half, in the registry, is the one that says
  a mesh terrain has solid fill under it and a `trigger_hurt` under the
  whole map -- Section 3.2). Both emitted scripts are structurally sound:
  brackets balance,
  every string literal closes, every statement inside a function body
  ends in `;`, `{`, `}`, `:` or `,` unless it heads a block, nothing but
  `#using` / `#insert` / `#define` / `REGISTER_SYSTEM` sits outside a
  function, and no function name is defined twice.
- Z16. Both emitted scripts reference only things that exist: every
  unqualified call and `&pointer` resolves to a function the same file
  defines; every `ns::name` call is in the stock symbol table; every
  such call's module appears in a `#using` line of that file.
- Z17. Every manifest line that is not one of Z14's six and not a `>`
  directive or `//` comment is `<type>,<name>` with a type the format
  reference has read out of a real zone file, and a non-empty name.

### 9.5 Toolchain properties (unit-testable with stub executables)

- B1. Every stage runs with cwd `<root>\bin` and the three `TA_*`
  variables set with trailing backslashes.
- B2. Compile argument order: `-platform pc`, mode flags, `-loadFrom
  <map path>`, `<bsp path>`; entities mode passes `-onlyents` and not the
  navmesh flags; full mode passes `-navmesh -navvolume` and not
  `-onlyents`.
- B3. Bake argument order: `-ledSilent`, `+<quality>`, `+localprobes`,
  `+forceclean`, `+recompute`, `<map path>`; quality restricted to
  draft/medium/final.
- B4. Link arguments: `-language <lang>` then `-modsource <map>`.
- B5. A stub linker that exits 154000 and writes two non-empty fastfiles
  yields `ok = True`; exit 0 with an `ERROR:` line yields `ok = False`;
  exit 2000 with one fastfile missing yields `ok = False`.
- B6. A stub compiler printing the leak banner with exit 0 yields a
  finding of code `leak` with the `.lin` path; printing the missing
  material line yields the material name in the outcome.
- B7. A stub that emits byte 0xFF does not raise; the outcome contains
  the replacement character and the rest of the log.
- B8. A stub bake that sleeps without output is killed after the stall
  window and the outcome says `needs interactive desktop`.
- B9. `run_chain` stops at the first `ok = False` stage and names it.

### 9.6 End-to-end gate (with the mod tools)

Run once per release candidate against the three-room recipe
(Section 8, `recipes/`) and against a one-room-plus-yard minimal map:

1. Commit → verify.files reports zero errors.
2. Asset refresh exits 0.
3. Full compile exits 0; log has no leak banner, no `ERROR:`, no missing
   materials other than `jun_art_wood_plywood_dark03` (if the mystery
   box is present), and `<map>.d3dbsp`, `<map>_navmesh.hkt`,
   `<map>_navvolume.hkt` exist and are non-empty. The log is expected to
   contain `restricting BSP to sky brushes` and, when the map has
   patches, `building curve/terrain collision` **[inherited: both
   strings come from the original authors' logs, not re-read]**;
   record their presence but do not fail the gate on them until one
   build has confirmed the exact wording.
4. Link: `ok = True` by evidence; each of the two fastfiles on disk with a size above zero;
   log ends with the `done:` lines. `loadingimage.png` and
   `previewimage.png` are still in the zone folder afterwards — the link
   writes into the same directory.
5. Entities-only recompile after moving one spawn struct exits 0 in
   under 10 s, and re-link `ok = True` in under 10 s.
6. Bake from an interactive session on the host writes `<map>.led`; a
   subsequent link log contains no preview-lighting fallback warning.
7. Playtest checklist (manual, recorded per build): map loads; player
   spawns on the floor in the starting room; zombies rise in yards and
   come through the windows in round 1; the first door opens for its
   price and interior risers appear in the next zone and pursue; perks,
   box, pack-a-punch and power switch respond; reaching round 7 does not
   hang (dog flag 0); no script error on the console.

The bar for "conformant" is 1-5 passing automatically, 6 passing once on
an interactive desktop, and 7 recorded as passed by a human.

### 9.7 Presentation properties (Section 6.1)

- P1. After a commit, `usermaps\<map>\zone\loadingimage.png` exists and
  parses as a PNG; a missing or unreadable file is an error. A size other
  than 1920 x 1080 is a **warning**, because that is the one size all 38
  published examples agree on, not a thing the engine enforces. Bit depth
  and colour type are not checked at all: 17 published loading screens are
  32-bit with alpha. Every room interior in the model is drawn somewhere
  on the default image, and two renders of the same blueprint are
  byte-identical.
- P2. `previewimage.png` exists and parses as a PNG, and **nothing about
  its size or colour type is checked**. 23 of the 39 published previews
  are the template's 600 x 340 and 16 are one of eight other sizes, from
  600 x 338 to 3126 x 2027; ten carry alpha and one is an 8-bit palette.
  All of them shipped and play, so 600 x 340 as a rule would fail 41% of the
  real corpus.
- P3. The manifest carries a `>title,` line; its absence is a warning, not
  an error, because the linker does not care.

---

## 10. Known-bad list

Every defect found and fixed in the reference, restated as
a requirement on the reimplementation. The section-9 check that guards
each is given where one exists.

| # | Requirement | Was | Guard |
|---|---|---|---|
| K1 | Player spawns are emitted as the struct set of Section 4.1 (`player_respawn_point` + one `initial_spawn_points` struct per player slot, four by default, with `initial_spawn`, the gametype tokens and no `script_int`). `info_player_start` is optional and never the only spawn marker. Moving the start moves the whole set. | Scaffold emitted `info_player_start` plus one struct; the gametype code reads neither of those alone. Numbering the slots 1..4 deleted one of them every game (Section 4.1). | Z1 |
| K2 | The map script never assigns `level.default_start_location` to a zone name. The starting zone is `init_zones[0]`. | Marking a zone as starting rewrote the variable to the zone name; the match string became `zclassic_start_zone`, and the spawn set was empty. | Z2 |
| K3 | Link success is decided from evidence (no `ERROR:` lines, each of the two fastfiles on disk with a size above zero), never from the exit code. The build chain gates the next stage on that verdict. | Chain treated non-zero exit as failure; the linker returns 154000 or 2000 on success and never 0. | B5, B9 |
| K4 | The lighting bake is only started when the runner reports `provides_interactive_desktop` (a display and a GPU; an interactive Windows session is one way to supply that, `WineRunner`'s own X server is another), and a started bake that shows no CPU progress and no output for 60 s is killed and reported as needing interactive desktop. | Bake invoked headless, hung with 0.2 CPU-seconds in 4 minutes until a 240 s timeout. | B8 |
| K5 | Ground-height lookup uses the flat cell top for column terrain and bilinear interpolation only for mesh terrain; the terrain record stores which one applies. | Bilinear used for both; on column terrain the lookup disagreed with the written brush tops by as much as 50 units. | T3, T4 |
| K6 | Cell index computation uses floor, not truncation toward zero; points just outside the low edges report not-found. | `int()` mapped `(-30, -30)` to cell (0, 0). | T3 |
| K7 | Column terrain never emits a brush whose rounded height is ≤ 0; such cells are skipped like below-threshold cells. | Merged-run path quantised a 0.3-unit cell to 0 and emitted a zero-height box, which the box constructor rejected, aborting the whole terrain. | T1, G1 |
| K8 | All numbers in emitted map text are fixed-point decimals with trailing zeros stripped and noise collapsed to `0`; exponent notation never appears; integers are byte-identical. | Every number went through `%g`: `1.2e-16`, `1e-05`, `1.23457e+06`, and `65536.25` → `65536.2`. | F7, F10 |
| K9 | Readiness of the external terrain server is polled at `/health`; user-facing notes never mention a `/seed` endpoint (it does not exist; seed is a query parameter of `/terrain`). | Note told callers to poll `/seed`. | unit test on the message |
| K10 | Script and map editors preserve the file's existing line endings per line; inserted lines take the ending of their neighbour. (Under this design the script is regenerated, so the requirement reduces to: regenerate with the ending the file had, default LF.) | Read with universal newlines turned every CRLF into LF before inspection; every "preserved" file came out LF. | F12 |
| K11 | Yard flanking walls run to the open edge; no `t x t` corner slot opens the yard to the void. | West/east walls stopped `t` short of the open side; a 4-unit flood fill escaped west of the room. | G6 |
| K12 | Tool output is decoded with replacement; one undecodable byte never discards a stage result. | Strict decoding raised on byte 0xFF (and on 0x81/0x8D/0x8F/0x90/0x9D under cp1252). | B7 |
| K13 | The material catalogue only lists names that have compiled without a missing-material warning; `jun_art_wood_plywood_dark03` is not offered, and its warning (from the mystery box prefab) is recognised as benign. | Listed as vetted; compiles printed the warning three times. | Z12, gate 3 |
| K14 | Documentation and emitted comments state the first dog round as 5, 6 or 7. | Said 5. | manual |
| K15 | Third-party dependencies are pinned to a compatible major version (the reference's server import broke when its framework library released a new major). | Unpinned major; fresh installs failed to import. | CI install test |
| K16 | Wedge brushes are wound by the numeric `orient_inward` check, never by a hand-written point order per direction. | Present in the reference; the requirement is to keep it. | G3 |
| K17 | Open-air rooms (no ceiling) are supported and their walls run to the top of the bounds. | Present in the reference. | G4 variant |

Earlier lessons the reference recorded from playtests,
**[inherited]**, restated as requirements because the cost of relearning
them is an in-game session each:

| # | Requirement |
|---|---|
| E1 | Spawn structs sit at the floor surface (z = slab top, or terrain + 4), never 16 or 24 above it. |
| E2 | A zone's spawn structs use the `targetname` that the zone volume's `target` names; spatial overlap is not a link. |
| E3 | The starting zone's zombies come through barricade windows from yards; yards are at least 144 deep and lit. **The sill half of this lesson is wrong**: a 48-unit sill buries the prefab's traversal channel in solid wall and the window is dead in play. Section 4.6 holds the opening's numbers; nothing else states them. |
| E4 | Interior spawns default to `riser_location` with `script_string "find_flesh"` and are paired with a factory entity. |
| E5 | Multi-zone maps wire every door into the zone graph; without the edge the far zone never activates. |
| E6 | `level.dog_rounds_allowed = 0` before the framework entry unless dog spawners exist. |
| E7 | Sky shell, umbra volume, sun volume and a light per sealed room are all present before compiling; the bake runs before the final link. |
| E8 | Hull brushes carry the visible material only on the interior face; opening pieces are visible on all faces. |
| E9 | **Not a rule: terrain patches get no collision twins.** Giving one a real material and `weaponClip detail` is wrong. There are no collision twins: `weaponClip` replaces the default contents, a twinned chunk is not solid, and a map built to this rule let the player fall through the outdoor ground and get stuck under it. Terrain meshes are one block per chunk with no `contents` line (Section 3.2, which is the single statement of this rule). The material half does hold: a terrain patch never uses `caulk`. |
| E10 | Patch control grids are oriented outer +X, inner +Y for floors; a floor patch invisible from above has its grid transposed or reversed. |
| E11 | The client script calls the framework's client entry. |
| E12 | Buyable-door triggers carry an explicit `origin` at the trigger's centre. |
| E13 | Terrain meshes are padded by one duplicated row and column so their footprint equals the column footprint and fills the room. |
| E14 | Scattered props are `misc_model` with `no_collmap "1"`. |
| E15 | Single-zone maps failed five playtests in the reference's history for reasons never isolated; the three-room layout (start with windows → arena → vault, two doors) is the only layout with a recorded pass. Ship it as the default recipe and treat other layouts as unverified until played. |

---

## Appendix A. Facts table: fixed names by category

**File format tokens:** `iwmap 4`, `script_startingnumber`, `flags`,
`expanded`, `active`, `hidden`, `ignore`, `prefab`, `// entity`,
`// brush`, `guid`, `layer`, `contents`, `detail`, `nonColliding`,
`umbraTarget`, `weaponClip`, `ai_nosight` (both measured in the shipped
sources; Section 1.6), `lightmap_gray`,
`mesh`, `curve`, `toolFlags;`, `v`, `t`, `c`, `smoothing`,
`decalLayerSort`, `decalEditorSort`.

**Classnames:** `worldspawn`, `misc_prefab`, `script_struct`,
`info_volume`, `actor_spawner_zm_factory_zombie`,
`actor_spawner_zm_factory_zombie_dog`, `trigger_use`,
`script_brushmodel`, `script_model`, `zbarrier_zmcore_MagicBox`,
`misc_volume_decal`, `misc_model`, `light`, `volume_sun`,
`umbra_volume`, `volume_fpstool`, `reflection_probe`,
`info_player_start` (unread on the zombies path), `func_group`.

**Keys:** `classname`, `origin`, `angles`, `targetname`, `target`,
`script_noteworthy`, `script_string`, `script_int`, `script_flag`,
`script_vector`, `radius`, `zombie_cost`, `cursorhint`, `model`,
`modeloverridematerial`, `decalsize`, `count`, `spawnflags`,
`script_forcespawn`, `script_disable_bleeder`, `export`, `DYNAMICPATH`,
`shadow_casting`, `client_server`, `modelscale`, `no_collmap`, `static`,
`ssi`, `ssi1`, `wsi`, `fsi`, `lutmaterial`, `skyboxmodel`, `gravity`,
`lightingquality`, `samplescale`, `_color`, and the zbarrier board/anim
keys of Section 4.8.

**Values:** `player_volume`, `player_respawn_point`, `initial_spawn`,
`initial_spawn_points`, `start_room`, `zclassic_start_room`,
`zcleansed_start_room`, `zgrief_start_room`, `riser_location`,
`spawn_location`, `faller_location`, `custom_spawner_entry`,
`find_flesh`, `zombie_spawner`, `zombie_dog_spawner`, `dog_location`,
`zombie_door`, `electric_door`, `electric_buyable_door`,
`HINT_ACTIVATE`, `move`, `treasure_chest_use`, `start_chest`,
`zmcore_MagicBox`, `use_elec_switch`, `elec_switch`, `elec_switch_fx`,
`zm_perk_machine`, `zombie_vending`, `PRIMARY_OMNI`, `white_light`,
`vol_decal_cube`, `default_day`.

**Asset paths and models:** the `_prefabs/zm/zm_core/` prefabs of
Sections 4.6-4.10; `p7_zm_der_door_buy_*` door models;
`c_zom_test_body1`; `zombie_wolf`; `skybox_default_day`;
`luts_t7_default`; `zm_collision_perks1`.

**Script names:** Section 5.4.

**Tools and switches:** `gdtdb.exe /update`; `cod2map64.exe -platform pc
-onlyents -navmesh -navvolume -loadFrom`; `radiant_modtools.exe
-ledSilent +draft +medium +final +localprobes +forceclean +recompute`;
`linker_modtools.exe -language -modsource`; environment `TA_GAME_PATH`,
`TA_TOOLS_PATH`, `TA_LOCAL_ASSET_CACHE`; Steam app id `455130`.

**Manifest tokens:** `>class`, `>group`, `>title`, `>mode`, `>type`,
`>expect`, `>level.*`, `>linker.animation_mode`, `col_map`, `gfx_map`,
`scriptparsetree`, `sound`, `xmodel`, `material`, `image`, `fx`,
`xanim`, `weapon`, `stringtable`, `localize`, `rawfile`, `aitype`,
`scriptbundle`, `zbarrier`, `weaponcamo`, `postfxbundle`, `ttf`,
`include`, `ignore`, `ignore_missing_shipped`, `zm_mod_level`,
`modtools`.

## Appendix B. Orientation conventions [measured]

Two numbers decide where a prefab points: which way the asset faces when its
yaw is 0, and which way the yaw turns it. Both are now measured, and this
appendix states each once. What it said before this revision - that the perk
front was `[inherited]`, and a prose line claiming yaw increases
counter-clockwise sitting over a table whose numbers were clockwise - was the
contradiction that kept `Z23` a warning. The tables below are the clockwise
ones rewritten; the numbers changed, the prose did not.

**The turn is counter-clockwise.** Measured on a wall buy emitted at origin `(-1264, -100, 8)` yaw
270: the weapon struct inside `spawnable_weapon_pistol_burst.map` sits at
local `(-3, 0, 55)`, and the compiled `zm_mymap.d3dbsp` carries it at
world `(-1264, -97, 63)`. Counter-clockwise by 270 maps local `(x, y)` to
`(y, -x)`, so `(-3, 0)` goes to `(0, +3)`, which is the offset in the BSP; a
clockwise reading would have put it at `(0, -3)`. The engine turns the
entities a map emits directly - the magic-box zbarrier, the chest struct - the
same way. So there is one formula for every family:

```
yaw = (heading - front_at_yaw_zero) mod 360
```

A generator that turns prefabs clockwise instead agrees with the engine on the
two headings parallel to the family's front-at-yaw-zero and is 180 degrees out
on the perpendicular pair, so half its wall buys face into their own walls.

**The front-at-yaw-zero is per family, and the families disagree.** Every row
below was read off the stock prefab under
`map_source/_prefabs/zm/zm_core/` on the tools install.

| Family | Front at yaw 0 | Yaw for north / east / south / west | Evidence |
|---|---|---|---|
| Wall weapon (`spawnable_weapon_*`) | **+Y** north | 0 / 270 / 180 / 90 | All thirteen prefabs are built identically: the chalk patch mesh and the weapon `script_struct` lie on the plane `y = 0` and the mount brush sits behind them at `y in [-8, -1]`. [measured] |
| Perk machine (eight `vending_*_struct.map`) | **-Y** south | 180 / 90 / 0 / 270 | Three marks in the prefabs, all on -Y: the `attack_spot` structs form an arc in front at `y` from -19 to -38 with `x` at 0 and ±30; the `PRIMARY_SPOT` lights that light the face stand 80-87 units out at `y` about -80 aimed back at the machine (`light_perk_doubletap_001`); `vending_revive_struct.map`'s one shadowcaster brush sits behind at `y in [11, 17]`. [measured] |
| Pack-a-punch (`vending_weapon_upgrade_spawnable.map`) | **-X** west | 270 / 180 / 90 / 0 | The one vending prefab whose own entities are not at yaw 0: the `zbarrier_zmcore_packapunch` and the `perksacola` struct both carry `"angles" "0 270 0"`, which turns the -Y vending front onto -X. Its lighting agrees without assuming anything about the model: the spot light at `(8.75, 4.75, 68)` targets an `info_null` 71 units away at `(-63, 4.8, 68)`, and the second `info_null` is at `x = -59`. [measured] |
| GobbleGum (`vending_bgb_struct.map`) | **-Y** south | 180 / 90 / 0 / 270 | The weakest row: no trigger, no struct, no light in the prefab, and the machine's logic is not in the shipped scripts. Its one clip brush is symmetric in plan, `x in [-16, 16]` by `y in [-16, 16]`, but its top is a `clip_slick` slope running from `z = 64` at `y = -16` up to `z = 96` at `y = +16`. The low, sheds-you-forward side is -Y, the same front as the other eight machines. [measured from the clip, not from a trigger] |
| Mystery box (`zbarrier_zmcore_MagicBox`) | **+Y** north | 0 / 270 / 180 / 90 | `_zm_magicbox.gsc:294` puts the use prompt at `origin + anglestoright(angles) * -22.5`, which is 22.5 units along +Y at yaw 0. `anglestoright` is pinned by the wall buys, whose front is already measured: `_zm_weapons.gsc:959` pushes their unitrigger the same way and for those it has to land in the room at +Y. [measured] |
| Mystery box stand (`buyable_magic_box_start.map`) | none | takes the box's yaw | A plank on four cinder blocks under a clip: no trigger, no struct, no model with a face, symmetric about its own origin bar decorative yaw jitter on the blocks. It has an axis but no front. Its plank runs `x in [-46, 48]` by `y in [-13, 12.5]`, long axis X, and the box's long axis at yaw 0 is X too, so stand and box take one yaw. (Treyarch's own pairing in `zm_giant_magicboxes.map` puts their platform at the zbarrier's yaw + 90 at all six chests, and that platform's long axis is Y.) [measured] |
| Power switch (`power_switch.map`) | **-Y** south | 180 / 90 / 0 / 270 | The least ambiguous of the set, because the prefab carries its own `trigger_use`: that brush spans `y in [-24, -5]` while the switch body's clip is `y in [-8, 7]`, so the trigger stands entirely off the -Y face. The handle `script_model` is at `y = -7` and the `elec_switch_fx` struct at `y = -8.3`. [measured] |
| Barricade (`barricade_reciever_wood*.map`), exterior | **+Y** north | 0 / 270 / 180 / 90 | The zombie side is all at +Y: `exterior_goal` struct at `(0, 50, 16)`, `node_pathnode` at `(0, 63, 16)`, `zbarrier` at `(0, 47, 31)`, with the window's traverse brush at `y in [-2, 14]`. [measured] |
| Riser paired with a barricade | not a prefab | the world yaw from the riser toward the barricade, i.e. the opposite of the exterior heading | It is an AI spawn struct and its angles are a plain world heading, not a prefab convention. The stock file settles it: `barricade_reciever_wood.map`'s own `exterior_goal` stands outside at `(0, 50, 16)` carrying `"angles" "0 270 0"`, a world heading of south, pointing straight back at the barricade at the origin. The old rule here, "barricade yaw + 180", agrees with that on no heading at all and was wrong on all four. [measured] |
| Door model broad face | along X | door in east/west wall: 90 | [inherited] |
| Chalk decal forward | +X (reported as yaw 0 = +X, 90 = -Y; sign convention unverified) | choose so forward points into the wall | [unverified]; expose it directly |

Three consequences worth stating, because each one hid the defect for a while:

- A perk machine's use prompt is a `trigger_radius_use` spawned at the struct
  origin (`_zm_perks.gsc:1508`), and so is the pack-a-punch's
  (`_zm_pack_a_punch.gsc:106`). A machine turned into a wall still takes your
  points. What you lose is the machine: the model faces the brickwork and the
  `zm_collision_perks1` clip, which takes the same angles
  (`_zm_perks.gsc:1549`), blocks the wrong side. The mystery box is the
  opposite case - its prompt is a unitrigger offset off the box's own front,
  so turning it wrong costs the prompt too.
- The pack-a-punch was wrong on **all four** headings, not just the
  perpendicular pair, because it was being given the perk family's front as
  well as the clockwise turn: 90 degrees out everywhere. No amount of
  comparing the two rotation senses would have found it; only opening the
  prefab did.
- The mystery box's two errors cancelled on east and west. Reading the
  clockwise table and the perk front together gave the right yaw there by
  accident, which is why a check comparing only the senses reported a defect
  on a box that was, on those two headings, correct.

## Appendix C. Three-room configuration that played

This is the exact configuration that compiled, linked and played; it is
the conformance fixture for Section 9.6 and a worked example of the
operations, not a design to copy. The default recipe in `recipes/` must
be parameterised (room extents, zone names, prices, flags, which
machines go where) and may ship different values. What E15 records as
verified is this structural pattern (a windowed start room with a yard
on each windowed side, a larger central room, a third room, two priced
doors in a line) together with these particular numbers; any other
numbers are unverified until played. Coordinates in world units; wall
thickness 16; floor surface z = 16.

**One number in it is known-bad rather than merely unverified.** The
windows' 64 x 48 opening at sill 48 is what was in the file that played,
and it is the reason nothing came through them. Anything rebuilt from
this appendix takes the opening from Section 4.6 instead. The rest is
kept exactly as played and is deliberately not edited, because this
appendix is a verified fixture rather than a design.

- Start room bounds (-512, -256, 0) to (-128, 256, 256): east doorway
  80 wide x 96 tall at the wall midpoint; south and north windows
  64 x 48 at sill 48 — **the numbers this map was built with, and the
  reason its two windows were dead: no zombie ever came through either
  one. A rebuild uses Section 4.6's 96 x 112 at sill 0.** Yards
  (-512, -432, 0)-(-128, -256, 256) attached on
  its north side and (-512, 256, 0)-(-128, 432, 256) attached on its
  south side; barricades at (-320, -240, 16) yaw 180 and (-320, 240, 16)
  yaw 0 with risers 96 out; one interior light at (-320, 0, 200), one per
  yard at (-320, ±344, 200); player start (-320, 0, 32) facing +X;
  pistol wall weapon at (-494, -100, 8) yaw 270; zone = interior.
- Arena bounds (-128, -512, 0) to (768, 512, 384): west and east
  doorways 80 x 96; four perks near the corners with margin 160 facing
  inward; SMG and AR wall weapons at (320, ∓496, 8) yaw 0/180; two
  risers at (0, -460, 16) and (700, 460, 16); four lights at z 320;
  zone = interior.
- Vault bounds (768, -256, 0) to (1280, 256, 256): west doorway 80 x 96;
  two risers at (810, ±200, 16); mystery box (1024, 0, 16); pack-a-punch
  (1024, 216, 20) yaw 90; power switch (1024, -232, 24) yaw 180; one
  light (1024, 0, 200); zone = interior.
- Doors: (-128, -40, 16)-(-112, 40, 112) price 500 flag `enter_arena`
  between start and arena, model yaw 90; (768, -40, 16)-(784, 40, 112)
  price 1500 flag `enter_vault` between arena and vault, model yaw 90.
- Enclosure around (-512, -512, 0)-(1280, 512, 384) with gap 128,
  thickness 32, sun preset `default_day`, no probe.
- Script: dog rounds 0; init zones start, arena, vault; two
  `add_adjacent_zone` edges; seven perk/pack modules as placed.

Compile (full) exit 0, no leak, three benign plywood warnings; link
`ok`, `<map>.ff` 24.3 MB and `en_<map>.ff` 230 KB; played.
