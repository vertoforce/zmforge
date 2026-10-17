# Building Black Ops III zombies maps: the failures that pass the build

This is a reference for anyone generating or hand-building a custom zombies map
for Call of Duty: Black Ops III. It collects what one map generator project has
established about the ways a map compiles, links, loads and then plays wrong.
Almost nothing here fails the build. That is the point of the list.

This is the list. `../how-zombies-maps-work.md` is the mechanism behind it:
how the round system, zones, navigation, purchasables and lighting actually
work, so a reader can reason about a failure that is not on this list.

Every claim carries where it came from:

- `[measured]` means this project measured it on a mod tools install or in play.
- `[Treyarch: file]` means the number was read out of a file the mod tools ship. The file is named.
- `[community]` means a forum post or a community wiki reports it and this project has not confirmed it.
- `[unverified]` and `[unknown]` mean what they say. Those labels are not softened anywhere below.

## The short version

If you only read one screen, these are the failures that cost the most time.

- A zone volume sized to a room's interior leaves a dead band in every doorway. Standing in that band kills the player outright every 3 seconds `[measured]`.
- A lamp brightness value is a logarithm judged against the map's sky exposure, so a value that lights one map leaves another nearly black `[measured]`.
- The navmesh generator refuses a step over 18 units, a gap under 31 wide, a gap under 72 tall and terrain over 46 degrees. It says nothing when it refuses `[Treyarch: bin\default_navmesh_settings.json]`.
- A mesh terrain is a surface. Without solid fill beneath it the player falls through and is stuck alive underground `[measured]`.
- A prop without `use_collmap` links clean and the player walks through it `[measured]`.
- The linker's exit code carries no information in either direction. Judge every stage on its log and on what landed on disk `[measured]`.
- Purchase prompt text and the loading screen are two things people expect to be asset pipelines. Neither is `[measured]`.
- A sound alias bank is not a compiled format. `.sz` is CSV text: the shipped `mp_sector.all.alias.sz` has a 102-column header and 646 plain rows, so writing the file is building the bank and no GUI is involved `[measured]`.

## Spawning: the player dies a second after loading in

### The zombies path never reads info_player_start

The game builds its spawn set from `script_struct` entities `[measured]`.
Emitting an `info_player_start` is harmless and relying on one gives a map with
no valid spawns. Three shapes are needed.

- One struct with `targetname player_respawn_point`. Its bounds become the level's spawn bounds `[measured]`.
- At least four structs with `script_noteworthy initial_spawn` and `targetname initial_spawn_points`, one per player slot, at least 32 units apart, standing on floor `[measured]`.
- Every one of them carries `zclassic_start_room` among the space-separated tokens of `script_string`. The framework builds a match string from the gametype and `level.default_start_location`, joined with `_`. It skips any struct that does not hold the result `[measured]`.

Two ways to empty that set by accident:

- Put a `script_int` on an initial-spawn struct. On that struct the value is a team side, and the spawn picker deletes candidates by side. Numbering four slots 1 to 4 deletes one every game. Shipped `zm_giant.map` carries four such structs and none of them has a `script_int` `[measured]`.
- Assign `level.default_start_location` yourself. The framework already sets it to `start_room`. A zone name there builds a match string no struct carries `[measured]`.

### Standing in a doorway can kill you at full health

The stock script threads an out-of-playable-area monitor on every player. Every
3 seconds it damages any player who is in no life brush and inside no enabled
zone volume. The damage is their own health plus 1000, with bleedout time zero
`[measured]`. It reads as a random death rather than a bug, because the poll only
sometimes catches the player in the bad spot.

The fix is to size each zone volume to the room's outer box, walls included.

- Two rooms sized to their interiors leave a band as wide as both wall thicknesses. Two 16-unit walls make a 32-unit band that belongs to no volume `[measured]`.
- The player hull is 30 units across, from `PLAYER_RADIUS 15` in the stock shared player script and from the bot debug box `[measured]`.
- A 30-unit player in the middle of a 32-unit band touches neither volume. Every doorway crosses that band.

Treyarch's own scale reference gives the standing player 72 tall by 32 wide
`[Treyarch: docs_modtools\Scale_Standards.pdf]`. The navmesh settings ask for 31
`[Treyarch: bin\default_navmesh_settings.json]`. The stock scripts give 30. The
three numbers cannot all be the collision width and the conflict is
`[unverified]`. Clearing 31 satisfies all of them.

### A zone the script never enables is worse than no zone at all

A `player_volume`'s `targetname` is a zone name, and that name has to be
registered and reachable `[measured]`. The zone manager initialises and
enables every entry of the `init_zones` array. Adding an adjacent zone
initialises both ends and enables neither. An adjacent zone comes alive only when
a door flag connects it to a zone that is already enabled. A name in
neither place stays disabled forever, and walking into it is the instant death
above.

### Above four players the stock scripts end the match

The stock zombies script freezes the fifth player to spawn and notifies the end
of the game, outside the grief and meat gametypes `[measured, read from the
stock scripts, never playtested]`. Extra spawn structs alone seat nobody. The
one map-side edit that helps is setting `level.player_too_many_players_check`
false after the framework entry, which lands between the framework's write and
its read `[measured]`. The remaining edits community wikis name are in core
game scripts a usermap does not ship `[community]`. A generated map is ready for
eight players and does not seat eight on its own.

## Zombies and rounds: the round starts and nothing comes

### One spawner entity, and one spawn set per zone

- At least one spawner actor carrying `script_noteworthy zombie_spawner`. The lookup is on that key rather than on the classname, and the framework picks the spawner entity at random map-wide `[measured]`.
- The classname still has to name a zombie `aitype` that exists, and only two do: `actor_spawner_zm_usermap_zombie`, which the mod tools' own usermap zone source declares, and the older `actor_spawner_zm_factory_zombie` the level template ships. Both link and both spawn zombies; the factory one's animation mapping table names 527 animations against 635 for the other, and 78 of the 140 it omits are traversal moves -- every jump, mantle and climb `[measured]`.
- A zone volume's `target` names its spawn set. Every spawn struct in that zone carries the same string as its `targetname`. Sitting inside the volume is not a link `[measured]`.
- Each struct carries `script_noteworthy riser_location`, `spawn_location` or `faller_location`, plus `script_string find_flesh`. Without `find_flesh` the zombie stands still `[measured]`.
- A zone with no spawn struct contributes no locations, and the round loop waits on an empty list rather than timing out `[measured]`. The community treats one spawner per zone as a hard rule `[community]`, which is stricter than what the engine appears to need.

### A riser above the floor makes a stuck zombie

The struct origin belongs on the floor surface, which is z 16 on a standard slab
and surface plus 4 on terrain. Heights of 32 and 40 produced floating zombies
that never moved `[measured]`. A struct buried inside a world brush has
floor under it and passes every floor test, so burial needs its own probe.

### A barricade window is three things that have to agree

- An opening at the floor, sill 0, 96 wide by 112 tall. The barricade prefab's own traversal channel is 50 wide by 40 tall measured from the floor, and the opening has to contain it `[measured]`.
- The stock barricade prefab itself, under `_prefabs/zm/zm_core/`. The shipped filename misspells "receiver" and the misspelling is the asset's `[measured]`.
- A riser outside the wall, tagged with the same `script_string` as the barricade, standing in sealed space. Shipped offsets are 93 and 252 units out from the wall, and the prefab's own exterior goal struct sits at 50 `[measured]`. A yard at least 144 deep holds everything the prefab places.

Zombies cross a barricade by playing the prefab's traversal animation rather
than by walking. That is why a 96 by 48 hole is legal below the navmesh corridor
height `[Treyarch: bin\default_navmesh_settings.json,
and measured]`.

### Dog rounds are on until the map turns them off

Set `level.dog_rounds_allowed = 0` before the framework entry unless the map
carries dog spawner entities and `dog_location` structs. After the entry the
framework default has already applied `[measured]`.

The community adds that dog spawners belong in every zone even with dog rounds
disabled `[community]`. Zombie pathing during Zombie Blood and during a solo
Quick Revive down targets those locations. Nothing here has playtested
that, so its cost is `[unverified]`.

Several community weapon packs break against the stock factory spawner class
`[community]`. The reported symptom is a zombie that takes no damage and loses
its hitbox. The reported fix is remapping the class to the usermap variant. This project emits the stock class and has not reproduced the
symptom.

## Lighting: black rooms, sky-textured walls, washed-out everything

### A lamp's stops value only means something against the map's exposure

`stops` is log base 2 of the emitter intensity. The shipped values give it away:
the lamp prefab for the Giant carries `4.64385618977472`, which is log2 of 25,
and `9.96578428466209`, which is log2 of 1000 `[measured]`.

The scale that makes those numbers readable is the exposure of the map's sun and
sky preset. That preset is named on the worldspawn and on `volume_sun`, and each
one carries its own `ev` `[measured]`. Measured bands:

| Sky preset | Exposure | Where the shipped lamps sit |
|---|---|---|
| `zm_factory` | 5 | the Giant's 543 lamps peak at 4.64 and 5.64 |
| `mp_sector` | 12.75 | 275 lamps peak at 15 and 16, band 13 to 17 |
| `default_day` | 15 | no shipped zombies map uses it |

A lamp's stops belongs at its map's exposure, give or take a few stops up. A
fixed `stops 4` under a `default_day` sky is eleven stops under shipped
practice, 2048 times too dark, and the map plays nearly black `[measured]`.

There is no ambient term to rescue it. The fill colour pair on `volume_sun`
appears four times across the roughly 730 shipped map files and is black every time
`[measured]`.

### One lamp does not light a hall

Treyarch's zombies lighting prefab puts 536 non-skybox lamps across 4304 by 6389
units, which is one lamp per 226 by 226 patch `[measured]`. One lamp per 521 by
521 is too dark. A lamp inside or above
the ceiling slab lights nothing.

### Two documented light keys that nothing here emits

Treyarch's culling document names two keys on a light, `culling_cutoff` and
`culling_falloff`, and puts the pair at 200 and 300 for a lamp with no reason to
differ `[Treyarch: docs_modtools\Culling_LOD_Lights.pdf]`. 427 of the 543 lamps in their own
zombies lighting prefab carry them, at exactly those two numbers `[measured]`.

What the engine does with a lamp that carries neither is `[unknown]`. Nobody
has measured it, which is why the check for it is a warning.

### Reflection probes have an upper density as well as a lower one

The same shipped prefab carries 176 reflection probes, with sizes fitted to
their rooms rather than left at a constant `[measured]`. Treyarch's probe
document puts two limits on that `[Treyarch:
docs_modtools\Probe\Reflection_Probes.pdf]`. Sampling for a grid point stops at
the eight nearest probes, so crowding an area can leave the bake without one
that sees the point. A probe also holds six reflection planes at most, so the
six walls that matter have to be chosen. No check exists for probe placement
here, because the bake cannot be falsified in this chain.

### Walls render as sky without an umbra volume

With no `umbra_volume` the compiler defaults occlusion to a million-unit cube,
walls render as sky, and it prints a line about it and exits 0 `[measured]`. A map also wants one `volume_sun` and a sky shell of six slabs with no
gap.

### Caulk on a terrain patch renders black

A patch never carries `caulk`. The compiler prints its own banner about it and
still succeeds `[measured]`. Face and patch materials that are not on the
install produce the error texture, and the compiler reports those as warnings
too.

### Without the bake the map is washed out

The lighting export runs inside Radiant, which needs a display and a GPU behind
it. Started with no desktop session it allocates memory, then sits idle and
never exits `[measured]`. When the bake
has not run, the link log says it fell back to preview lighting and the map
builds, loads and looks washed out `[measured]`.

## Falling out of the world and staying there

### A mesh terrain is a surface, not a volume

The player gets through the ground and is stuck underneath, alive, with nothing
to kill or reset them `[measured]`. Fill the volume under a mesh terrain
with solid brushes. Treyarch's own geometry source for the Giant does this with
a single caulk block spanning the whole map down to z -288 `[measured]`.

### Every map wants a floor of last resort

A `trigger_hurt` slab under the whole map catches anyone who gets out anyway.

- Faces of material `trigger`, positive damage. The shipped slabs carry 1000 or 10000 `[measured]`.
- It appears six times across the roughly 730 shipped map files (the count varies by tools version), so it is convention rather than a requirement the tools state `[measured]`.
- It has to lie under and around every zone volume in plan, with its top below every zone floor, or it kills players standing in bounds `[measured]`.
- Nothing in the tool chain mentions it. The compile and the link are clean either way `[measured]`.

## Collision: walking through props, or into brickwork

### A prop without use_collmap is not solid

The compiler reads two keys off a model, one to bake its collision map into the
static BSP and one to keep it out `[Treyarch: bin\t7.def.json]`. Measured on
Windows: six props linked with collision off and the player
walked through all six. Setting the key changed the compiled map from 95,708 to
97,556 bytes, which is 1,848 bytes of static collision, and the compiler printed
the word `collmap` zero times in either log `[measured]`. The size delta was
the only evidence available.

The other direction is a warning rather than an error. Collision baked onto
scatter props is thought to cut the navmesh and stop zombies at a plant pot, and
only the prop library knows which props are meant to be solid `[unverified]`.

### Entities buried in brickwork fail silently and differently

A spawn slot inside a pillar traps the player. A riser inside a counter produces
no zombie. A lamp inside a pier leaves the room dark. None of them is reported by
anything `[measured]`.

Testing for burial takes two probes per entity, at the origin and 8 units above
it `[measured]`. A riser's origin sits on the floor, so only the upper probe
sees the pillar standing on that floor. A ground-under test does not
answer this question, since a spawn slot inside a pillar has floor under it.

## Navigation: the places zombies will not go

### The navmesh generator has its own numbers and they are stricter than the player's

Four thresholds come out of the settings file the mod tools ship, and the
generator runs against that file `[Treyarch:
bin\default_navmesh_settings.json]`:

| Setting | Value | What it refuses |
|---|---|---|
| `maxStepHeight` | 18 | a tread that rises further |
| `minCharacterWidth` | 31 | a way through that is narrower |
| `characterHeight` | 72 | a way through with less headroom |
| `maxWalkableSlope` | 46 | terrain steeper than this, in degrees |

All four fail the same way. The compile omits the surface, exits 0 and says
nothing, the link is clean, the map loads, and in play the walkers never go
there `[measured]`. If the round's zombies are meant to spawn there, the
round never ends.

The corridor width is the trap worth naming. A 30-unit doorway is wide enough
for the player and gets no navmesh `[Treyarch:
bin\default_navmesh_settings.json]`. Across three shipped recipes here the
narrowest aperture measures 40.2 units, so the one-unit gap has never actually
been landed in `[measured]`.

### Stairs that connect at neither end still compile

A flight whose bottom step is a 200-unit wall, or whose top stops under the
balcony it was meant to reach, compiles and links `[measured]`. Both ends
need another walkable surface within one step rise and within a hull width in
plan. Testing for it with a probe straight ahead gives false failures, because
stairs turn and land sideways: a forward probe called three of five flights on
one map disconnected, all three wrongly `[measured]`.

### Reachability is its own question and every other check passes without it

A perk machine on a shelf, or a room with no way in, satisfies every rule above.
The floor is inside a zone volume, the doorway is wide enough, the flight
connects at both of its own ends `[measured]`. Deciding reachability means
flooding the standing surfaces from the spawn slots.

What the flood assumes about the player, and where those numbers come from:

- Jump height 64, fall damage floor 256 and ceiling 512, from the stock game logic script `[measured]`. All three sit inside an old-school mode branch, and the unconditional defaults are stated nowhere on the mod tools install, because the shipped configs only reset those dvars `[unknown]`.
- A 16-unit step. There is no step-size dvar in the shipped scripts at all. 16 is the rise every recipe here climbs in, and it is labelled an assumption in the code `[unverified]`.
- A drop is a one-way link. A balcony a player can fall off and not climb back onto is reached, not unreachable.
- A bought door is an entity rather than a world solid, so it does not block. A sealed opening is a world solid and does `[measured]`.
- Sloped massing is treated as an obstacle, because the model cannot say what is under a point on a sloped top. No shipped recipe joins two levels with a ramp.

### A teleporter's holding room has to sit inside a zone

Community practice says a zone volume has to enclose the black box room a
player is moved to during a teleport, sited out of sight `[community]`. A
generator that fits zone volumes to walkable geometry would kill anyone who
teleports.

## Buyables and prefabs: the thing you bought does nothing

### A weapon name that does not exist fails silently

Asking the engine for a weapon by name answers for a name that does not exist,
nothing raises, and the feature that asked does nothing `[measured]`. A
rigged mystery box asking for `shotgun_olympia`, a Black Ops I and II name,
behaved like an ordinary box. Every weapon a map or its script names belongs in
this level's weapon table.

A wall buy is a second string away from its weapon. The slug names the
`spawnable_weapon_<slug>.map` prefab, and the weapon is named inside that file
on the buy struct. All thirteen are read off the stock prefabs. Twelve
match their slug. The bowie buy's prefab names `bowie_knife`, which is a real row
of the level weapon table at cost 3000 and not in the box `[measured]`.

### A prefab facing the wrong way is the emitter bug that hides best

The compiler turns a prefab counter-clockwise by its yaw `[measured]`. That
was settled by comparing a wall buy's weapon struct in the source against its
position in the compiled map. A clockwise turn would have put it on the opposite
side.

The heading a family's front points at yaw 0 is per family, read off each stock
prefab: wall buy north, perk machines south, pack-a-punch west,
mystery box north, power switch south, barricade exterior north `[measured]`. They disagree with each other, and a generator that assumes one heading
for all of them is wrong for most.

The failure hides three ways over:

- A clockwise turn is right on the two headings parallel to a family's front and 180 degrees out on the other two. Half of every map looks correct `[measured]`.
- A perk's use trigger and the pack-a-punch's are radius triggers at the machine origin, so a machine facing a wall still sells the perk `[measured]`.
- Only the mystery box loses its prompt, because its trigger is offset off the box's own front `[measured]`.

A wall buy is the exception that shows up immediately. Turned wrong, the chalk
drawing faces into the brickwork, the mount sticks into the room, and the prompt
origin sits inside the wall. Ten of eleven wall buys on one generated map
shipped that way `[measured]`.

The riser paired with a barricade is not a prefab. It is an AI spawn struct
whose angles are a plain world heading. The stock barricade prefab's own exterior
goal faces straight back at the window, so the riser faces the opposite of the
exterior heading `[measured]`.

### A machine needs floor in front of it and a script module behind it

- Every perk machine needs a `#using` line for its module in the server script `[measured]`.
- Machines, the box and the switch stand on reachable floor, within 8 units of it, unburied `[measured]`.
- The approach space used here is 40 wide by 64 deep by 64 high, starting 24 units out from the origin. Those dimensions are inherited and `[unverified]`. The stock machines carry their own collision clip and nothing here has measured it.

### A buyable door needs four things to agree

A priced trigger, a collision leaf, an explicit origin at the trigger's centre,
and a `script_flag` that appears in exactly one adjacent-zone call. The trigger's
`target` equals the door brushmodel's and the door model's `targetname`
`[measured]`.

### Stamping a prefab drops its internal pairings

Stamping resolves a prefab into loose entities and loses the `target` and
`targetname` links between them `[community]`. Writing map source directly is
equivalent to stamping, so every pairing a prefab would have carried has to be
emitted by hand.

Community practice also records two indexing rules that look cosmetic. Mystery
box locations are numbered from 0 with no gaps, and the value is a bare digit
rather than a zero-padded one `[community]`. Trap letters come from one pool
across all trap types rather than one pool per type. Getting either wrong
links clean and leaves dead furniture.

## Scripts, the manifest and the two screens nobody sees

### An unresolved call is fatal at run time, not at build time

Both emitted scripts have to parse `[measured]`. Every call has to resolve
to a function the file defines, or to a stock symbol whose module the script
`#using`s. A missing semicolon or an unresolved call kills the map in
play.

Two rules come from Treyarch's own language document `[Treyarch:
docs_modtools\GSC_Language.pdf]`:

- Every `#using` line belongs above the first function in the file. One below it will not compile, and nothing here checks the order.
- A call with no explicit namespace falls back to the builtin library, which is why unknown engine functions still compile.

The script API reference the tools ship documents 2,332 engine functions
`[Treyarch: docs_modtools\bo3_scriptapifunctions.htm]`. The symbol table here
carries 27 builtins harvested by hand `[measured]`. Any call outside those
27 is reported as an unknown symbol, and most of those reports are false.

The client script's `main()` has to call the framework entry. Without it the
server and client disagree about client fields and the join is dropped
`[measured]`. Community practice adds that a script pack referenced in only
one of the two scripts fails the same way `[community]`, and nothing here
compares the two sets.

### The manifest is where a typo goes unpunished

Six lines the linker needs, naming the class, the group, the collision map, the
graphics map and both script parse trees `[measured]`. Every other line has
to be an asset prefix real zone files use. The linker acts on the lines it
understands and the map dies at run time reaching for the asset that never
arrived `[measured]`.

The title line is free text up to the first comma. The linker rewrites it into a
generated zone file, where a comma truncates and every space is removed.
Measured on Windows and confirmed in game: a title with a
comma in it arrives with everything after the comma gone and the spaces
stripped `[measured]`.

### Two things that are not asset pipelines

- **Purchase and use prompt text.** The weapon name never passes through script. It reaches the prompt through the engine's cursor hint, and the hint text is a localized reference the framework chooses, with cost as the only script-supplied parameter. Of 614 stock call sites that set a hint string, every non-localized literal is the empty string, which clears a prompt `[measured]`. Renaming would need a new localized string asset and the install carries no `.str` file to copy the format from.
- **The loading screen.** Two loose PNGs in the map's zone folder, 1920 by 1080 and 600 by 340, bit depth 8, colour type 2, no interlace. Neither is a fastfile asset, so no build stage complains when one is missing or malformed `[measured]`. Published Workshop items carry the same two filenames in the same place.

The preview image shows on the map selection card. The loading image does not
appear for a local map load, despite matching every published map's format, size
and location. The cause is `[unknown]`. The install declares stock placeholder
assets for both that no shipped zone file references, which may be what a mod is
meant to override instead `[unverified]`.

### Custom sound, which is a pipeline after all

It looks impossible on the strength of one failed link and one file
extension, but the extension lies: `file` calls the
shipped `mp_sector.all.alias.sz` **CSV text**, its first line is a 102-column
header and it has 646 plain rows `[measured]`. Writing the file is
building the bank.

Four rules, each of which fails quietly:

- The bank is named after the map. `sound,<bank>` is the name the linker opens `<bank>.all.alias.sz` under `[measured]`.
- It goes in the **shared** raw tree, `share\raw\sound\zone\`, not the per-platform `pc\raw\sound\zone\` where Treyarch's own `mp_sector` bank sits. A bank in `pc\raw` links as though it were not there `[measured]`.
- A bank holds at most 104,729 rows, roughly 160 times what a real map uses `[measured]`.
- Every required column carries a value: 53 of the 102. The one example row the tools ship leaves nearly all of them blank, which reads like the `Template` column filling them in, and the linker does not do that. A bank of rows shaped like that example produced 108 error lines, two per column `[measured]`.

Two companion tables beside the bank are load-bearing: without
`<map>.all.ducklist.sz` and `<map>.all.reverb.sz` the link stops with
`ducklist failed to load` and `reverb failed to load for zone <map>`. A `Name`
header and no rows is enough for the duck list; a reverb table of zero presets
links too `[measured]`. The wave file goes under `sound_assets\`, which is
what a row's `FileSpec` is relative to, at 48 kHz signed 16-bit PCM.

Proved by building a one-room map with one synthesised 4.5 kHz looping alias:
link with no error line, and `1261,sound,<map>.all,7179,0` in the linker's own
packed asset list `[measured]`. Whether the alias is **audible** is
`[unknown]`: nobody has heard it.

## Build stages: what a successful build looks like

Exit codes are close to useless here `[measured]`.

- The asset database updater returns 0 on success and is trustworthy.
- The compiler returns 0 on success, 0 with a leak and 0 with missing materials. A missing model is the exception and is fatal, with no map written.
- The linker's code means nothing in either direction. Successful links have returned 0, 2000, 5000, 154000 and 208. A failed one returned 2002000.
- The bake never returns at all without a display and a GPU.

So the log and the disk are the evidence. A link succeeded when no line matches
`ERROR:` after colour codes are stripped and both fastfiles exist above zero
bytes. Both halves are needed: a failed sound-bank link printed four error lines
and still wrote both fastfiles `[measured]`.

The compiler also announces files it does not write. It prints a writing line
for the map, the navmesh and the nav volume, then writes only what it made. A
map with no flying enemies legitimately gets no nav volume and a warning line
explains it `[measured]`.

Community reports give compiler and linker ceilings with their error strings,
covering map triangles, windings per face and per concave group, terrain
collision vertices and map nodes `[community]`. Nothing here enforces a map-wide
bound. The only ceiling in this project is a per-prop 1500-triangle limit
applied by decimation at asset-build time `[measured]`.

Two publishing steps come from Treyarch's own Steam guide rather than from the
tools: delete the `.xpak` files out of the zone folder before uploading, and
select all languages in the tools' options `[Treyarch: published mod tools
Steam guide]`. Both failures appear only on someone else's machine.

## What the checks cover, and what they do not

The verification table in this project holds about 140 rows. Most run
automatically and a handful need a person. The table itself is
`src/zmforge/verify/registry.py`, a test asserts its counts, and this document
points at it rather than carrying its own copy of the list, so the numbers
cannot go stale here.

The letter in each code says where the rule came from, which is the whole reason
the families are kept apart.

- `Z`, `W`, `F`, `P` and `G` are rules this project derived, by playing generated maps, by reading the stock scripts, or by measuring shipped map sources.
- `N` holds the four navmesh thresholds read out of `bin\default_navmesh_settings.json`, and `L` holds the light LOD keys read out of `docs_modtools\Culling_LOD_Lights.pdf`. Their numbers are quotable with a file behind them. A test asserts each against a local mirror of that file, so a number cannot drift away from its source.

The automated rows are split by what they read.

Against the model, before anything is written:

- spawn structs and their tokens, standing room outside every zone volume, zone registration and the door flag graph
- spawn locations, barricade windows, lamp placement and lamp brightness
- doorway clearance, stair connection, the four navmesh thresholds, and reachability from the spawn slots
- prefab yaw, and whether models and prefabs exist on the install

Against the written map and script text:

- the manifest, the title line and the two loading PNGs
- the trigger hurt slab, prop collision keys and material names
- script structure, symbol resolution and the light LOD keys
- nine rules about the map file's own text format

Against the build logs: the leak banner, error lines, stages judged failed on
evidence, missing materials, an unset umbra volume, caulk on terrain, and a bake
whose output the linker could not find. These only run when logs are supplied. A
static run reports them as skipped rather than passed.

The rows that need a human say so:

- Whether the loading screen appears in game. The cause of its not appearing is unknown.
- Whether the baked map looks right. The bake runs in the chain. Whether its output lights the map correctly is unverified, and a Wine bake's exported lighting data is a different size from a Windows bake's.
- Whether a prop's collision was built and packed, which is visible in the link log.
- The playtest list itself. The map loads. The player spawns on the floor of the starting room. Zombies rise and come through the windows in round 1. The first door opens and the next zone pursues. The buyables respond, round 7 does not hang, and the console shows no script error.

Known holes with no check at all:

- A scattered prop buried in a world brush. Burial is checked for spawns, machines and lamps only.
- The server and client `#using` sets agreeing with each other.
- Effect precache lines in the client script.
- Map-wide compiler and linker ceilings.

## What is still unverified or unknown

Collected so nobody spends a day assuming one of these is settled.

- The player collision width. Three shipped sources give 30, 31 and 32 `[unverified]`.
- What the engine does with a lamp carrying neither light LOD key `[unknown]`.
- The unconditional values of jump height and fall damage thresholds. The ones that can be read sit inside an old-school mode branch `[unknown]`.
- The engine's real step limit for a player, as opposed to the navmesh generator's 18 `[unknown]`.
- Why the loading image does not appear for a local map load `[unknown]`.
- What the compiler does with exponent notation in a map file number. No shipped map contains one and the cost of finding out is a broken build with no diagnostic `[unknown]`.
- Whether a custom sound alias is audible in a session. The bank builds, links clean and lands in the packed asset list; the linker never mentions the wave file and the map's `.xpak` is the same size with a valid bank as with a broken one, so where the audio comes from at run time is `[unknown]`.
- Whether a Wine-baked map looks right in game. Windows and Wine builds produce differently sized lighting exports `[unverified]`.
- The community claim that an inactive zone kills a player who enters it. Its own author hedges `[community, unverified]`.
- Whether dog spawners are needed with dog rounds disabled `[community, unverified]`.
- Whether the always-on flag pattern used here is better or worse than the community's zone contract. Neither has been playtested against the other `[unverified]`.
- The respawn point struct emitted here carries a name that is not a zone name, so the zone manager never unlocks it. Round 1 spawning is unaffected, and the code that skips a locked struct is coop relocation and revive placement, which no playtest has exercised `[measured, consequence unverified]`.

## Building on Linux

The compile, the link and the lighting bake all run under Wine on a Linux host,
using the mod tools' own Windows binaries `[measured]`. That
toolchain is documented separately, including what the bake needs from the GPU
and the X server. See `docker/bo3-wine/SETUP.md`.

Playing a built map is outside that toolchain: it needs the game itself.
