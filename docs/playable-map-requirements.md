# What a generated BO3 zombies map must have to play correctly

Every requirement here is a thing that compiles, links and loads, and then goes
wrong in play. None of them fails the build. Each comes from playing a
generated map, from reading the stock scripts, or from measuring the shipped
maps.

For *why* each of these goes wrong, read `how-zombies-maps-work.md` first. It
explains the engine and framework mechanisms these requirements fall out of.
This page stays organised by symptom and is the one to run against a map.

Run the whole table against a map with one command:

```
zmforge requirements <map> --tools-root <tools> --recipe <recipe>
```

It prints one line per requirement: `PASS`, `FAIL`, `WARN`, `SKIP` or `MANUAL`.
Without `--recipe` the model-level checks report `SKIP`, because a map read back
off disk has no model behind it. Without build logs the eight log-reading
checks report `SKIP` too, and without the compiled navmesh `H1` reports `SKIP`
as well: nothing then has asked what the *zombies* can reach. A skip is not a
pass and the report says so at the bottom.

In the library the same call is `zmforge.verify.run_all(project)`.

The older `zmforge check` command is not this. It runs the file-level half
only, and prints findings rather than a line per requirement. It stays for
callers that want the short form.

The table lives in `src/zmforge/verify/registry.py`: 144 rows, 139 automated and
5 that need a person. `tests/test_requirements.py` asserts those three counts,
and that this document names every row and invents none.

## Scoreboard: what is guarded and what is not

Automated, by what it reads:

- Model, before anything is written: `Z44`, `Z18`, `Z6`, `W1`, `W2`, `W3`, `Z19`, `N1`, `N2`, `N3`, `N4`, `N5`, `Z25`, `Z48`, `Z46`, `Z74`, `Z75`, `Z76`, `Z77`, `Z40`, `Z23`, `Z41`, `Z42`, `Z43`, `W6`, `Z31`, `Z32`, `Z53`, `Z54`, `Z55`, `Z56`, `Z57`, `Z58`, `Z59`, `Z62`, `Z63`, `Z64`, `Z65`, `Z66`, `Z61`, `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `D1`, `D4`, `D5`, `D6`, `D7`, `D8`, `Z80`, `Z81`, `Z84`, `Z85`, `Z86`, `Z87`, `Z88`, `Z89`, `Z91`, and the model half of `Z1`, `Z3`, `Z4`, `Z5`, `Z7`, `Z8`, `Z9`, `Z10`, `Z11`, `Z12`, `Z13`, `Z15`, `Z28`, `G7`, `Z22`, `W5`, `Z50`.
- Written files: `Z44`, `Z2`, `Z26`, `Z49`, `Z50`, `Z29`, `Z30`, `Z14`, `Z16`, `Z17`, `Z20`, `Z21`, `Z24`, `Z27`, `Z45`, `Z47`, `Z51`, `Z52`, `W4`, `L2`, `P1`, `P2`, `P3`, `Z90`, `Z92`, `F1` through `F9`, `Z67` through `Z73`, `Z79` and `Z82` (`verify/gameplay.py`, over the generated script and `.str`), `Q1` through `Q7` (`verify/quest_safety.py`, over the generated script and `.map`), `Z78` (`verify/sealed_start.py`: after a sealed start resolves, no respawn lands in a sealed zone), `Z83` (`verify/umbra_air.py`: player spawns in at most one sealed pocket of air), and the file half of the codes above.
- Build logs: `leak`, `stage_error`, `stage_failed`, `missing_material`, `missing_material_benign`, `umbra_unset`, `caulk_terrain`, `preview_lighting`, `shadows_dropped`.
- The navmesh the compiler wrote: `H1`. The only row that reads a build artefact, and the only one that answers for the walkers rather than the player. It needs the model too, because the finding is the difference between the two.

Not automated at all: `M1`, `M2`, `M3`, `M5`, `D3`. Each names what a person has to
look at. `Z25` covers reachability for the player: the map is flooded from the spawn slots and anything no route leads to
is reported. `H1` covers the other half of it, for the zombies, by reading the
navmesh instead of predicting it.

Two codes carry two meanings each, for historical reasons the registry records.
`Z13` is models existing on the install at model level and the client entry call
at file level. `Z15` is terrain backing at model level and script soundness at
file level.

## You are killed a second after you spawn, not downed

### The spawn entity you expect is ignored

Symptom: the map loads and the spawn set is empty. On the zombies path the
game never reads `info_player_start`. Emitting one is harmless and relying on
it produces a map with no valid spawns.

Rule: emit `script_struct` entities in three shapes.

- One with `targetname player_respawn_point`. Its bounds become the level's
  spawn bounds and its `script_int` is the ideal distance to another player,
  which is why the shipped value 2000 matches its own `radius`.
- At least four with `script_noteworthy initial_spawn` and
  `targetname initial_spawn_points`, one per player slot, at least 32 units
  apart, over floor, not inside a world brush.
- Every one of them carries `zclassic_start_room` among the space-separated
  tokens of its `script_string`. The framework joins the gametype and
  `level.default_start_location` with `_` to build the match string. It skips
  any struct whose `script_string` does not hold the result.

Check: `Z1`, model and file level.

### A number on a spawn struct deletes it

Symptom: a four-player map seats three, and which slot vanishes depends on team
selection.

Rule: an initial-spawn struct carries no `script_int` at all. On that struct
the key is the team side, and `zm::getfreespawnpoint` deletes candidates whose
value is 1 or 2 depending on `side_selection`. Shipped `zm_giant.map` carries
four `initial_spawn_points` structs with no `script_int`. Numbering the slots
1 to 4 deleted one of them every game.

Check: `Z1`, file level.

### Renaming the start location empties the spawn set

Symptom: same as above, but total.

Rule: never assign `level.default_start_location` to a zone name. The
framework already sets it to `start_room`. Setting it to `start_zone` makes the
match string `zclassic_start_zone`, which matches no struct.

Check: `Z2`.

### Standing in a doorway kills you outright

This is the one that reads as a random death rather than a bug, and it is the
most important paragraph in this document.

Symptom: the player dies instantly, at full health, with Sam's laugh. Not
downed. It happens some of the times they stand in the same spot, because the
monitor polls every 3 seconds.

Mechanism: `_zm.gsc` threads `player_out_of_playable_area_monitor` on every
player. Every 3 seconds, a player who is in no life brush and not
`in_enabled_playable_area` takes `self.health + 1000` damage with bleedout time
zero. `in_enabled_playable_area` walks every entity with
`script_noteworthy player_volume` and returns true only where the zone is
enabled and the player `IsTouching` that volume.

Rule: size a zone volume to the room's **outer** box, walls included, not to
its interior. Two rooms sized to their interiors leave a band as wide as both
wall thicknesses that belongs to no volume. Two 16-unit walls make a 32-unit
band. The player's hull is 30 units across, read from
`#define PLAYER_RADIUS 15` in `scripts/shared/player_shared.gsc:15` and the bot
debug box `Box( self.origin, ( -15, -15, 0 ), ( 15, 15, 72 ) )`. A 30-unit
player standing in the middle of a 32-unit band touches neither volume. Every
doorway passes through that band.

The worst case is a threshold deck laid in that band between two rooms, for
example 128 by 32: a surface the map asks the player to walk over, entirely
out of bounds.

Check: `Z18`, model level. It reports the square units of standing room outside
every volume and the centre of the largest patch.

### A volume over the zombies' side of a barricade spends a powerup nobody collects

Symptom: a round's powerup drops go somewhere unreachable and the players never
see them. Nothing in any log says so.

Rule: a zone volume stops at the ground a player can stand on. A yard -- the
pocket outside a barricade window where the risers stand -- is the zombies'
side, and it belongs outside every volume.

Why. The volume is the switch for two things at once. A zombie spawns with
`self.no_powerups = true` (`_zm_spawner.gsc:359`), and `zombie_entered_playable`
(`:593`) polls `getentarray( "player_volume", "script_noteworthy" )` once a
second until it touches one, at which point
`zombie_complete_emerging_into_playable_area` (`:3253`) clears that flag --
which is what `zombie_can_drop_powerups` (`:1545`) reads. Then the drop itself
is validated the same way: `zm_powerups::powerup_drop` (`_zm_powerups.gsc:586`)
spawns the powerup, keeps it only where it `istouching` a volume -- any volume,
enabled or not -- and deletes it and hands the count back otherwise. So a
volume that stops at the wall line turns a kill in the yard into *no drop at
all*, and a volume that reaches over the yard turns it into one of the round's
four (`zombie_powerup_drop_max_per_round`, `:74`), landing out of reach and
gone after `powerup_timeout`'s 15 seconds.

This is the converse of `Z18` and the community states it as one: Logical
Edits, "Zombie Spawners & Zones", about 7:12, "keep zone volume out from behind
window barricades and traversals". The overlapping-volumes rule from the same
tier is **not** a requirement and has no check.

Check: `Z40`, model level, a **warning** -- it costs powerups, not a life. It
reports the square units of yard each zone's volume covers and the centre of
the largest piece. It deliberately says nothing about floor the map declares
`reachable=False`, or a pocket `Z25`'s flood cannot get to: a partition that
stops a player stops a zombie, so no zombie dies there and no drop is wasted.

### A volume naming a zone the script never enables is worse than no volume

Symptom: the player walks into a room and dies outright, as above.

Rule: a `player_volume`'s `targetname` is the zone name, and that name must be
registered and reachable. `zm_zonemgr::manage_zones` runs `zone_init` and
`enable_zone` on every `init_zones` entry. `add_adjacent_zone` calls
`zone_init` on both of its zones and enables neither, so an adjacent zone is
enabled only when its flag connects it to a zone already enabled. A name in
neither place is in no `level.zones` entry, and `zone_is_enabled` returns false
for it forever.

Check: `Z3`, model and file level. It walks the flag graph, so a zone with a
volume and no route to the starting zone is an error, not a warning.

## The round starts and nothing comes

### No spawner, no zombies

Rule: at least one spawner entity carrying `script_noteworthy zombie_spawner`.
The lookup is on that key, not on the classname. At least one spawn struct
belongs in every zone, or the zone is dead ground the moment the door opens.

The classname still has to name an `aitype` that exists, and the install ships
exactly two zombie ones (`archetypes/archetypes.gdt`).
`actor_spawner_zm_usermap_zombie` is what this package emits and what
`share/zone_source/zm_levelcommon.zone:51` declares for a usermap;
`actor_spawner_zm_factory_zombie` is the older one the mod tools' level
template ships, and it works — the linker resolves it and packs its chain —
but its animation mapping table names 527 animations against the 635 in
`zm_levelcommon`, and 78 of the 140 it omits are traversal moves. So the factory class is a warning, not an error.

Check: `Z5` for the spawner entity and its class, `Z4` for the per-zone structs.

The community makes the per-zone rule stricter than this repo does. See the
disagreements section.

### A riser with the wrong name belongs to no zone

Rule: a zone volume's `target` names the spawn set, and every spawn struct in
that zone carries that value as its `targetname`. Spatial overlap is not a
link. Each struct carries `script_noteworthy riser_location`,
`spawn_location` or `faller_location`, and `script_string find_flesh`. Structs
without `find_flesh` produce zombies that stand still.

Check: `Z4`.

### A riser above the floor produces a stuck zombie

Rule: a spawn struct's origin sits on the floor surface, which is z 16 on a
standard slab and surface plus 4 on terrain. Heights of 32 and 40 produced
floating, stuck zombies. The check allows 8 units.

Check: `Z6`, model level. It also rejects a struct buried inside a world
brush, which has floor under it and passes every floor test.

### Zombies never come through the window

Rule: a barricade window is three things at once.

- An opening at the floor, sill 0, 96 wide by 112 tall. The prefab's own
  traversal channel is 50 wide by 40 tall measured from the floor, and the
  opening has to contain it. A channel that sits inside solid wall is a window
  zombies cannot climb.
- The barricade prefab, `_prefabs/zm/zm_core/barricade_reciever_wood.map`. The
  misspelling is the asset's.
- A riser outside the wall, tagged with the same `script_string` as the
  barricade, standing in sealed space. How far out is not a rule: Treyarch's
  own eight pairs in `zm_giant` stand 94.7 to 487.5 units from their barricade.
  This package emits 96. `Z8` errors only below 64 --
  the prefab's own `exterior_goal` struct is 50 out, so a nearer riser stands
  on top of it -- and warns above 512. A yard at least 144 deep holds the goal
  and barrier entities the prefab places about 50 units beyond the wall.

Check: `Z8`, model and file level.

The numbers above are restated from spec §4.6, which is the single statement of
them; if they ever disagree, §4.6 is the one to trust and the other is the bug.
The spec's §8.4 example uses the same 96 by 112 at sill 0. Appendix C records
the older 64 by 48 window at sill 48 that its map was built with, and sends a
rebuild back to §4.6.

### A spawn that asks for a window nobody declared

Symptom: zombies from one spawn struct stand still or throw script errors as
they appear, while zombies from every other spawn in the same map behave. It
looks intermittent because only that struct's zombies are affected.

Rule: a zombie spawn struct's `script_string` is either `find_flesh` (no
window, just chase) or the tag of an entrance some barricade declares. Any
other value is a dead end. (Reported by t7_companion; mechanism confirmed in
the stock scripts.)

Check: `Z92`, file level, an error. It is the other half of `Z8`, which only
asks whether each window's tag reaches a struct.

<details><summary>Why, and the prefab-tag question</summary>

- The zombie copies its struct's `script_string` into
  `find_flesh_struct_string` (`_zm_spawner.gsc:583`). `findNodesService`
  (`_zm_behavior.gsc:1226-1251`) returns early for `find_flesh`, and otherwise
  looks through `level.exterior_goals` for one with the same `script_string`.
  None found leaves the node undefined; the only guard is an `assert`, and
  asserts do not run on a usermap (see "Asserts are silent on a usermap" in
  `how-zombies-maps-work.md`).
- t7_companion says a `script_string` set on the barricade **prefab instance**
  never reaches the `exterior_goal` struct inside the prefab. Our build output
  says the opposite. The stock `barricade_reciever_wood.map` struct has no
  `script_string`, yet in the compiled entity text of `zm_forge_gate.d3dbsp`
  both of its `exterior_goal` structs carry the window's tag
  (`start_window_south_link`, `start_window_north_link`). Treyarch's
  `zm_giant_nodes.map` uses the same prefab-level tag on its barricades. So
  `Z92` counts a barricade prefab's tag as a declared entrance.

</details>

## The map is black, or washed out, or renders as sky

### A lamp brightness that is right on one map is 2000 times too dark on another

Symptom: the map loads, the bake ran, and the rooms are nearly black.

Mechanism: `stops` is log2 of the emitter's intensity. Read the values off
`_prefabs/zm/zm_giant/zm_giant_light.map` and they are logarithms of round
numbers: `4.64385618977472` is log2(25), `9.96578428466209` is log2(1000). A
logarithm means nothing on its own. It means something against the camera
exposure, which comes from the map's sun and sky preset, the `ssi` named on the
worldspawn and on `volume_sun`. Each preset in `source_data/ssi.gdt` carries an
`ev`.

The measured bands:

| Preset | ev | Lamp stops in the shipped maps |
|---|---|---|
| `zm_factory` | 5 | `zm_giant`'s 543 lamps peak at 4.64 and 5.64, running to about 10 |
| `mp_sector` | 12.75 | `mp_sector` and `mp_combine`'s 275 lamps peak at 15 and 16, band 13 to 17 |
| `default_day` | 15 | no shipped zombies map uses it |

The rule that falls out: a lamp's stops sits at its map's exposure, give or
take a few stops up. A fixed `stops 4` under `default_day`, ev 15, is eleven
stops under the shipped practice, 2048 times too dark, and the map plays
nearly black.

There is no ambient term to fall back on. `volume_sun` carries a
`global_fill_color` pair, and across all of the roughly 730 shipped `.map`
files it appears four times, always black.

Check: `Z11`, model and file level. Both ends are errors. The map-wide
brightness trim is judged separately and gets one warning, because it is the
knob someone turns while looking at a bake.

### One lamp does not light a hall

Rule: no part of a room's floor is further than 226 units from a lamp in plan.
`zm_giant_light.map`'s 536 non-skybox lamps span 4304 by 6389 units, one lamp
per 226 by 226 patch. The generator's first large map carried one per 521 by
521. A lamp inside or above the ceiling slab illuminates nothing.

Check: `Z11`. `Blueprint.light_rooms()` satisfies it.

### No reflection probe, so no bounced light

Symptom: the map bakes flat. Not a missing reflection -- a missing *indirect
solve*. `bin\t7.def.json`'s `reflection_probe` template files most of its keys
under the group `2_DIFFUSE_GI`, describes `brightnessAdjust` as scaling the
bounce brightness during the bake, and describes `virtual` as a probe that is
not exported but still feeds other probes' bake data. The class description,
paraphrased: it captures a cube map at its origin and applies it, with
computed occlusion, to what its volume contains. Geometry inside no probe's volume is
outside that.

Nothing in the toolchain mentions it. `cod2map64.exe` knows the classname and
carries no zero-probe message; neither does the linker. The floor is set by the
tools themselves: `rex/templates/ZM Mod Level/map_source/zm/template.map`, the
map a freshly created zombies level starts from, carries exactly one probe
(entity 26, `"name" "probe"`, origin `4 4 132`). A map with none starts below a
blank one.

The template's probe is the unsized default, `size_min` and `size_max` both
`72 72 72` -- a 144-unit cube, 0.4% of a three-room generated map by volume. A
shipped community map sizes its boxes to the space instead: the 23 probes in
`zm_alien_isolation.map` run 110 to 2164 units per axis, 20 of the 23 with an
axis over 200.

Rule: one probe per room, its box enclosing that room's interior on all three
axes. `size_min` and `size_max` are half-extents (the area of effect on the negative
and on the positive side), so an enclosing box is half the room
interior on each. `in_play_space` follows the database's own note: the key
is unavailable once every side is over 1000.

Check: `Z28`, model and file level. A room no box encloses is an error. A map
that turned probe emission off is a warning, because that is a thing a caller
can mean and nothing in the build objects to it.

### A lamp outside the documented light LOD setup

Symptom: unknown. This is the one rule here whose consequence has not been
measured, which is why it is a warning and not an error.

`docs_modtools\Culling_LOD_Lights.pdf` names two keys on a light,
`culling_cutoff` and `culling_falloff`, and gives 200 and 300 as the generic
pair. 427 of the 543 lamps in Treyarch's own
`_prefabs/zm/zm_giant/zm_giant_light.map` carry them. The generator emits
neither.

Rule: a small lamp (radius 150 or less) carries no light LOD pair over 25.

Check: `L2`, file level, over the written map text. A
lamp with neither key is fine (both default to 0, never culled, in
`deffiles/lightdescription.awi`). `L2` warns when a lamp of radius 150 or less
carries a cutoff or falloff over 25. Writing 200 / 300 on every lamp breaks
corridor lighting.

### Walls render as sky

Rule: one `umbra_volume` and one `volume_sun`, and a sky shell of six slabs
with no gap around everything. Without an umbra volume the compiler defaults
occlusion to a million-unit cube and walls render as sky. It prints a line
about it and exits 0.

Check: `G7` for the shell, `Z11` for the two entities, `umbra_unset` in the
compile log.

### Surfaces render as the error texture, or black

Rule: every face and patch material is in the known-clean catalogue, meaning it
has compiled at least once without a missing-material warning. A patch never
carries `caulk`. Caulk on a terrain patch makes it render black and the
compiler prints its own banner about it.

Check: `Z12` at both levels, `missing_material` and `caulk_terrain` in the
compile log. `missing_material_benign` is the one known exception,
`jun_art_wood_plywood_dark03`, which comes from the mystery box prefab.

### The map renders washed out

Rule: the lighting bake has to run before the final link. It is a GUI program
and hangs with no desktop, so it is not in the automated chain.

Check: `preview_lighting` reads the linker's own line, `Failed to load Lighting
Export Data`, after the fact. `M2` is the human half.

## You fall out of the world and stay there, alive

### A mesh terrain is a surface, not a volume

Symptom: the player gets through the ground and is stuck underneath, alive,
with nothing to kill or reset them. The only way out is to quit.

Rule: fill the volume under a mesh terrain with solid brushes.
`zm_giant_geo.map` line 6008 is one caulk block spanning x -7776 to 6680,
y -10624 to 8880, down to z -288.

Check: `Z15`, model level. It checks the inputs the emitter needs, since the
emitter guarantees the fill itself.

### Every map wants a floor of last resort

Rule: a `trigger_hurt` slab under the whole map, with faces of material
`trigger` and positive `dmg`. The shipped slabs carry 1000 or 10000.
`trigger_hurt` appears six times across the roughly 730 shipped `.map` files
(the count varies by tools version). It has to
lie under and around every `player_volume` in plan, and its top must stay below
every zone floor, or it kills players standing in bounds.

Nothing in the tool chain mentions it. The compile and the link are clean
either way.

Check: `Z20`, over the written map, because the slab exists nowhere else.

## You walk through things, or into them

### A prop with its collision skipped

Symptom: players and bullets pass through the furniture.

Rule: a prop meant to be solid carries `use_collmap "1"` and not
`no_collmap "1"`. Those are the two keys `cod2map64` reads, and the mod tools' own
`bin\t7.def.json` describes them as the switch for whether a model's collmap is
baked into the static BSP: one key turns that on, the other turns it off.

Measured on Windows: six props in `zm_forge_gate` linked
with `Collision: false` and the player walked through all six. The same map
with the key set compiled to 97,556 bytes against 95,708, which is 1,848 bytes
of static collision. `cod2map` prints the word `collmap` zero times in either
log, so the size delta was the only evidence there was.

The other direction is a warning. Baked collision on scatter props is what
takes the navmesh out and stops zombies at a plant pot, and only the prop
library knows which a given prop is meant to be.

Check: `Z21`, over the written map. `M3` is the human half: whether
`export2bin` produced the `_col` binary and the linker converted it is in the
link log, and the prop install step prints it.

### Entities shipped buried inside brickwork

Symptom: depends on what was buried. A spawn slot inside a pillar traps the
player. A riser inside a counter produces no zombie. A lamp inside a pier
leaves the room dark. Each is silent until somebody plays the map.


Rule: nothing the game places sits inside a world brush by more than 2 units.
The test is the half-space one the compiler uses, so a wedge or a step reads as
its real shape rather than as its bounding box. Two probes per entity, the
origin and 8 units above it, because a riser's origin sits on the floor and
only the upper probe sees the pillar standing on that floor around it.

`ground_under` does not answer this. A spawn slot inside a pillar has floor
under it.

Check: reported under the code of whatever was buried. `Z1` for a spawn slot,
`Z6` for a riser, `Z9` for a machine, box or switch, `Z11` for a lamp. Wall
buys are left out on purpose, because the specification fixes their origin 8
units inside the floor slab.

Nothing checks a scattered prop for burial.

### A model the install does not have

Rule: every `misc_model` resolves against the installed asset list and every
`misc_prefab` path exists on disk.

Check: `Z13`, model level.

## You cannot get where the map wants you to go

### A doorway narrower than a body

Rule: a doorway is at least 30 units wide, the player's hull. Between 30 and
48 it is single file and gets a warning with the clearance printed. A room
interior narrower than the hull gets a warning rather than an error, because a
cupboard the depth of its own wall is a legitimate thing to build.

Check: `W2`, model level.

### Stairs that connect at neither end

Symptom: the bottom step is a 200-unit wall, or the top step stops under the
balcony it was meant to reach. Both compile and link.

Rule: a flight of steps has some other walkable surface within one of its own
step rises of both its foot and its head, and within a hull width in plan. The
tolerance is the flight's own rise rather than a constant, because the engine's
real step limit is not documented. Spec 2.5 records 8 as the rise the reference
authors used and report as climbable, and every recipe here climbs in 16s. The
check asks whether the map is consistent with itself.

Adjacency rather than a probe straight ahead: stairs turn, land sideways, and
end on a threshold rather than a floor. A forward probe calls a flight that turns or lands sideways
disconnected, and is wrong to.

Check: `Z19`, model level.

### The navmesh generator has its own numbers, and they are stricter

Symptom: nothing, anywhere. `cod2map64 -navmesh` lays no walkable surface over
the offending geometry, the compile exits 0 and says not a word about it, the
link is clean, the map loads, and in play the walkers simply never go there.
If the place they will not go is where the round's zombies are, the round does
not end.

These four rules are not measurements this repo made. They are read out of
`bin\default_navmesh_settings.json`, which the mod tools ship and the
generator reads, and
`tests/test_documented_rules.py` asserts each threshold against a mirrored
file so a number cannot drift away from its source.

Rule, and the key it comes from:

| Check | Rule | Key |
|---|---|---|
| `N1` | a flight rises no more than 18 units a tread | `maxStepHeight` |
| `N2` | a way through is at least 31 units wide | `minCharacterWidth` |
| `N3` | a way through is at least 72 units tall | `characterHeight` |
| `N4` | no terrain face is steeper than 46 degrees | `maxWalkableSlope` |

All four are model level.

`N2` is the one that is stricter than what was enforced before. `W2` measures a
doorway against the player's own 30-unit hull; the navmesh generator wants 31,
one unit more, so a 30-unit doorway is a doorway a player fits through and no
zombie ever paths through. The two checks disagree on purpose and both are
right about their own subject.

`N1` is the other half of `Z19`. `Z19` asks whether a flight connects to
something at both ends and deliberately takes no position on how high a tread
may be, because the limit was not known when it was written. 18 is that limit.
Every shipped recipe climbs in 16s and is inside it by two units.

A barricade window is exempt from `N2` and `N3`. Zombies cross one by playing
the barricade prefab's traversal animation rather than by walking, which is why
the shipped recipes cut a 96 by 48 hole for it and are right to. `Z8` owns that
opening's own rules.

`N4` takes the slope between neighbouring cells of the heightfield along both
grid axes, which is the same pair of samples the mesh triangulates from, so it
is the slope the compiler sees.

### A route wide enough to exist and not wide enough to move through

Symptom: the walkers do come, in single file, and bunch up on the way. Nothing
about this is visible to any build stage, and unlike the four rules above
nothing about it is broken either -- the mesh is there and the path works.

The two questions are separate and have separate sources, so this is a second
rule and not a correction of `N2`:

- **Is there a navmesh at all?** 31 units, and that number is a measurement,
  not a reading. Sweeping an opening's width and walking the face adjacency of
  the mesh `cod2map64 -navmesh` wrote: 16 to 30.9 units leave the two rooms as
  separate pieces, 30.95 and up join them, reproduced at four positions along
  the wall and at wall depths of 8, 16 and 64, with `minCharacterWidth` set to
  60 moving the boundary to 61. That is `N2`.
- **Is it wide enough to move through?** Treyarch answer this themselves, in
  `docs_modtools\Scale_Standards.pdf` under *Hallways*:
  `Minimum Clearance - 96"`, for runs of at most 128"; `Minimum Pinch Point -
  64"`, ideally at most 32" deep and never over 64"; a non-combat hallway 128
  minimum and a hallway with combat 160. That is `N5`.

The community rule of thumb this began as -- leave 64 units anywhere zombies
travel or they get stuck -- is the same 64, and the document is the better
authority for it. There is no agent width or AI radius in
`default_navmesh_settings.json` beyond `minCharacterWidth`; its `volBig` and
`volSmall` `characterWidth` keys belong to the flying-AI nav *volume*, which
this package does not place.

Rule: `N5`, model level, **warning**. Over the walkable surface `Z25`'s flood
reaches, every stretch that stays under 96 units wide is measured, and one is
reported per element when it runs longer than the document allows it to: 64
units for a stretch under the 64-unit pinch point, 128 units for one between
64 and 96. Two exclusions, both deliberate: a stretch narrower than `N2`'s own
31 is skipped, because the mesh is not laid there and nothing is being slowed
down; and the top of a walkable massing that is not a flight of steps is
skipped, because a table is meant to be 60 units across, which is the same
line `H1` draws for the same reason. Width is measured in plan, per walkable
surface, so a low beam stays `N3`'s question.

It is a warning and not an error because `Scale_Standards.pdf` is a design
standard for Treyarch's own levels, not a threshold this engine enforces, and
because the threshold has not been tested in game.

### A place the player can get to and the zombies cannot

Symptom: a room where nothing ever comes for you. You walk in, the round runs
on, and the horde is somewhere else. It is the same family as a zone with no
spawner, which once gave a round that never started, and it fails no build:
the map compiles, links, loads, and every rule above passes.

## A staircase the walkers will not climb

A flight of bare brush treads can be one players climb and zombies refuse,
and no other rule in this document notices.

`cod2map64 -platform pc -navmesh` **does** lay walkable surface up such a
flight. On a 17-tread flight it lays one simplified face climbing from z 34.8
to z 279.9, joined to the ground at its foot and to the landing at its head,
and a breadth-first search over the compiled mesh crosses it in three faces.
`H1` has nothing to object to, and the build reports `0 error(s)`.

What such a flight lacks is the thing every flight in Treyarch's own
source has. In
`map_source/_prefabs/zm/zm_giant/geo/zm_giant_zone_c_stairs_2.map` the 23
treads are `misc_prefab` tread *models*, which carry no collision at all, and
the only solid thing over the flight is one `metal_clip_nosight` wedge whose
sloped face spans the flight's whole 220 of run and 176 of rise. Its sister
`zm_giant_zone_c_stairs_1.map` is the same in `metal_clip`. So what a walker's
capsule slides along on a shipped map is a *plane*, and the drawn steps are
scenery. A flight of bare brush treads gives the mesh a smooth ramp to
simplify and gives the walker a wall per tread.

Rule: `Z46`, model level. Two halves.

- Every walkable flight of two treads or more carries a clip ramp.
  `add_steps` now lays one ([`stair_clip`](../src/zmforge/solids/forms.py)):
  one gradient, `rise` over `run`, carried from the floor the flight stands
  on to the top of its last tread, so it is level with each tread at that
  tread's nose and above it everywhere after. A flight built with
  `clip_ramp=False` has to be `reachable=False` as well.
- No floor a player reaches is out of reach of the walkers' own movement: the
  same flood `Z25` runs, re-run with no jump, no leap across a gap, and a rise
  of at most `maxStepHeight`. A **route** that fails -- a room floor, a deck,
  a landing, a flight -- is an error; the top of any other walkable massing is
  a warning, on `H1`'s own argument that a crate nothing can climb is what a
  crate is.

Surfaces the map declares `reachable=False` are exempt, and each one is
*printed* as a `Z46` warning naming it and its height, so a deliberate tease,
such as a prop on a ledge nobody can reach, is a line in the report rather
than an absence of one.

<details><summary>Why the ramp starts one tread before the flight</summary>

Run the plane from the top of the first tread instead and its leading edge is
a `rise`-unit wall standing on the floor. Measured: built that way,
`cod2map64` lays no edge at all between a balcony floor at z 288 and the foot
of a flight's ramp at z 304 -- a 16-unit rise, inside the generator's own
18-unit `maxStepHeight` -- and the whole upper storey comes out of the compile
as its own unreachable component. Extending the ramp back one tread brings its
low edge down to the floor, and the compile puts every storey back in one
component. The flight's foot then needs a tread's worth of clear floor in
front of it.

</details>

Everything above this line is a *prediction* about the navmesh. `N1` to `N4`
read the generator's own settings and say what it will refuse to build; `Z25`
floods the map with a player's legs. None of them reads the mesh
`cod2map64 -navmesh` actually wrote, and a zombie does not move like a player:
no jump, no survivable drop, no bought door, and no route at all except the
faces of that mesh.

Rule: `H1`, navmesh level. The compiler writes `<map>_navmesh.hkt` beside the
BSP; the check reads it and asks four questions of it.

- Every **spawn struct** has walkable surface within one zombie's width
  (`minCharacterWidth`, 31) of it. A riser comes up and then has to walk.
- Every **barricade** has surface on both sides. The mesh is *expected* to
  stop at the wall and start again in the yard -- crossing a barricade is an
  animation, not a walk -- so the two sides are joined for the rest of the
  check and a window with surface on only one side is the error.
- Every **zone the player reaches** has some of that surface in it.
- Every **standing rectangle `Z25`'s flood reaches** is covered by a piece of
  mesh a spawn struct can walk from. This is the one that matters: the
  difference between the player's flood and the walkers' mesh is exactly the
  defect being hunted.

Islands. The mesh comes apart on purpose -- `zm_one_room` is two faces with no
edge between them, the room and the yard -- so a count of pieces means
nothing on its own. What means something is a piece with player floor on it
that no spawn struct can reach, and that is the error above. The rest is a
warning giving the count and the stranded area.

Furniture is a warning, not an error. Measured on a compiled probe map: the
generator lays no surface on a top more than its own 18-unit
step above the floor, so a table is a place a player can stand and nothing can
follow. For a table that is what a table is; for a platform meant to be fought
on it is the defect this check looks for, and the map does not say which of
its slabs is which. A room floor, a terrain cell and a flight of steps are
routes and stay errors.

What was measured, and what is still inference. The format was worked out by
inspection -- it is a Havok `hk_2014.2.0-r1` binary tagfile, five of them end
to end in one file -- and the reader holds itself to the file's own
arithmetic: the faces' edge ranges chain to exactly the edge count, the
largest vertex index is one less than the vertex count, `oppositeEdge` is
symmetric, and every face is a closed ring. One map unit is 0.0254 m, which is
not a guess either: the settings tagfile in the same file stores
`maxStepHeight` as 0.4572, and `default_navmesh_settings.json` says that key is
18. What is inference: that a surface within one navmesh step of a modelled
floor is that floor, and that a zombie can be spawned onto surface a zombie's
width away. Terrain gets a further 30 units of slack, because the generator's
own `simplification.maxBorderHeightError` is 30 and it spends it: over the 100
cells of a sampled heightfield the mesh sits a median of 2 units
from the model's own samples and 20 at the worst.

### A place with no route to it from the spawn

Symptom: a perk machine on a shelf, a room with no way in, a flight of stairs
that ends in mid air. The map compiles, links, loads and plays, and every
check above passes: the floor is inside a zone volume, the doorway is wide
enough, the flight connects to something at both of its own ends. Hand edits
produce exactly these faults, stairs ending in mid air and a room with no way
in, and without a check only someone looking at the map catches them.

Rule: every machine, box, switch and wall buy, and every room and zone, is
reachable on foot from the initial-spawn slots.

How it is decided. The standing surfaces `Z18` already derives -- a room
floor, a doorway threshold, the top of a walkable massing solid, a terrain
cell -- are cut into the rectangles a standing player's body fits in, linked
where a player can get from one to the next, and flooded from the spawn slots.
The arithmetic is exact rather than sampled, for the reason `Z18` gives: every
box in the model is axis aligned, so cutting each surface where another box's
edge crosses it and testing one point per cell decides the whole rectangle. No
grid resolution has to be chosen or defended.

What stops a player, and what does not:

- Solid geometry. A cell is dropped when a structural world solid stands in
  the player's own body there. It is the same solid set the spec 2.8 step 7
  overlap scan uses, so `detail` brushes and caulk-only brushes are not
  obstacles, and a brush whose top is within one step of the surface is a kerb
  rather than an obstacle.
- Height. Up to 16 units is walked up, up to 64 is jumped up, and a drop of
  under 512 is taken. `setdvar( "jump_height", 64 )`,
  `setdvar( "bg_fallDamageMinHeight", 256 )` and
  `setdvar( "bg_fallDamageMaxHeight", 512 )` are stock, at lines 142, 144 and
  145 of `scripts/zm/gametypes/_globallogic.gsc`, repeated verbatim in the
  campaign copy. The caveat is that all three sit inside
  `if ( level.oldschool )`, next to `player_clipSizeMultiplier 2`, so they are
  what the stock scripts assert for that mode; the unconditional defaults are
  stated nowhere in the mod tools, because the shipped configs only `reset` those
  dvars. The 16-unit step is an **assumption** and is labelled one in the
  code: there is no step-size dvar in the shipped scripts at all, spec 2.5
  records 8 as an inherited preference, and 16 is the rise every recipe here
  climbs in. It decides what counts as a kerb and how a link is described, not
  whether the flood crosses it, since the jump is four times larger.
- A drop is a one-way link. The flood is directed, so a balcony a player can
  fall off and not climb back onto is reached, not unreachable.
- Doors are passable, because a door is bought rather than locked, and because
  a door is an entity and not a world solid. A **sealed** opening is a world
  solid and does block: removing only the brush that seals a room behind a
  40-unit window sill turns that room from unreachable into reachable, which
  is the measurement that says the obstacle half works.
- A ramp is not a route. `add_wedge` massing is not walkable, because the
  model cannot say what is under a point on a sloped top, so a wedge is an
  obstacle here and never a surface. No shipped recipe joins two levels with
  one, and a map that did would be reported unreachable; the fix would be to
  teach the model about slopes.
- Width is `W2`'s question and is not asked again here. Asking it per cell
  pair would let a single obstacle edge landing inside a doorway split that
  doorway's contact in two and report a good map as broken.

Content that is meant to be out of reach says so on the geometry.
`reachable=False` on a room or a massing already existed for exactly this (a
wall buy behind sealed glass, a prop on a ledge nobody can reach), so the
check reads that flag rather than adding one of its own. A surface declared unreachable is not flooded, the room is not
reported, and anything standing on it is passed over in silence.

One correction the flood needed. An opening cut more than a step above its own
room's floor is a window to `Z18`, and a multi-storey map often enters a
room through exactly that: a door cut at the upper floor's height in the
wall of a room whose own floor is hundreds of units lower, where a stair
landing or a graded slope meets it. The wall under that sill is solid brush by
construction, so the sill is a surface a player stands on. The flood adds
those sills and marks them, so that reaching one is not mistaken for entering
the room it is cut into.

On the shipped recipes the check reports nothing. That it can report
anything is not taken on trust: deleting the only flight up to a roof and
changing nothing else reports the perk machine on that roof and the roof's
zone, and clearing `reachable=False` from a sealed room or an unreachable
ledge reports what stands on it.

Check: `Z25`, model level. An error each, with the position of the thing
nobody can get to.

## A machine you can see, in a room you cannot cross

`Z42` proves the space in front of a machine is empty. `Z25` proves the room
it stands in is joined to the spawn. Neither asks whether a player can **get
to** that empty space. A working machine ringed by scenery props passes
every keep-clear rule (its own apron is empty, both door faces are empty) and
still cannot be bought, because scenery is placed by the recipe and the
placement rules are about placement, not *routes*.

Rule: `Z48`, model level. `Z25`'s own flood -- same walk, same 16-unit step,
same 39-unit jump, same 80-unit leap, same survivable drop -- run again with
every prop that stands on the floor counted as an obstacle, and then asked
one question per interactive: is the stand box in front of it reached?

Four things narrow what counts as an obstacle, and each one is a rule this
package already had:

- **On the floor.** `mount_kind`'s own sorting, the one `is_solid` uses. A
  duct along a soffit and a light on a wall are walked under. Without this, a
  corridor with ducts and wall lights hung at z 64 over a floor at z 16 reads
  as sealed.
- **In the body.** The same band `_free_rects` gives a world brush. A cup and
  a newspaper are stepped over.
- **Not climbable.** A prop is only a wall if it stands more than a jump above
  the floor it is on; below that a player gets on top of it. Without this, an
  item at the top of a course of platforms with props bolted to them reads as
  unreachable, because the props are what a player jumps on.
- **Half a hull.** Every prop box is grown by 15 units a side, so a gap has to
  measure a whole player before the flood uses it. The flood links any two
  rectangles that touch however narrow the contact, which is right for a
  doorway (`W2` owns that) and wrong for two crates.

Severity is the difference between two floods. With only the props that bake a
collmap: unreachable is an **error**, because the compiler itself puts
collision there. With every prop: unreachable is a **warning**, because the
engine may let a player push through a walk-through model, and this repo
cannot settle that without a build -- but the room *reads* as sealed either
way, and a player does not walk into a block of machines to find out.

An item over floor the map declares `reachable=False` is printed as a `Z48`
warning naming the declaration, the same way `Z46` prints its exceptions, so a
deliberate tease is a line in the report rather than an absence of one. So is
every prop model nothing could measure a box for: a model in no `MODEL_BOX`
entry is invisible to every prop-aware rule in the package, and a blind spot
that says nothing hides exactly this defect.

A room that packs scenery copies of a machine around a working one needs an
aisle: run the working machine's own apron the length of the room, so the grid
lays the copies in two banks either side of a 128-unit aisle with the one that
works at the end of it. 128 is the apron's own width and it clears `N5`'s 96-unit minimum hallway
clearance, so the aisle reads as a corridor rather than as a gap between two
machines.

## How high a player can actually get, and why 48 was too high

A 48-unit rise cannot be climbed in play, and the reason is not subtle.

**In zombies a player's jump lifts their feet about 39 units, and there is no
mantle unless the mapper builds one.** Mantling in this engine is a property
of a *material*, not something the engine infers from a ledge: a surface only
becomes climbable when a brush is textured with one of the tools' climb
materials. No map this generator has ever written carries one. Neither, as it
turns out, does any of Treyarch's own zombies maps. So the only thing lifting
a player on a generated map is the raw jump, and 48 is nine units above
it.

The reachability check assumes 64. That number is wrong, it is wrong in the
permissive direction, and it has been signing off climbs nobody can make.

<details>
<summary>The numbers, where each came from, and how much to trust it</summary>

"Measured" means grepped out of an installed copy of the mod tools. The
tools ship the engine's dvar *name* table with descriptions and **no default
values**, so several numbers cannot be recovered from the tools at all and are
marked as coming from the community.

| Quantity | Value | Source | Trust |
|---|---|---|---|
| Standing jump, feet rise | **39 units** | Treyarch `Scale_Standards.pdf`, as transcribed at [3dmappers](https://www.3dmappers.com/forum/tutorials-and-helpful-information/1514-black-ops-3-scale-standards): "Standing Jump: ~100 units distance, 39 units height" | Second-hand: the figure is taken from the transcription, not checked against the copy of the PDF that ships in the mod tools' `docs_modtools\`. Corroborated by `jump_height "39"` in the BO1 and WaW dvar dumps. |
| Standing jump, distance | ~100 units | same line | Second-hand |
| Sprint leap | 50 up, ~220 across | same PDF transcription | **Irrelevant to zombies.** `_zm.gsc:216` turns it off: `SetDvar( "sprintLeap_enabled", 0 )`, beside `doublejump_enabled 0`, `wallrun_enabled 0` and `juke_enabled 0`, in `zm::init()` for every zombies map. Measured in the mod tools. |
| Crouch jump | **does not exist** | The engine's dvar name table in `cod2map64.exe` holds 98 names containing "jump" and not one is a stance-modified jump | Measured in the mod tools |
| Mantle height | **no number recoverable** | The tiers exist as dvar names with no values (`trm_ledgeHeight_onLow/onMed/onHigh`, `trm_ledgeHeight_overLow/overMed/overHigh`, `trm_maxSideMantleHeight`, `trm_maxBackMantleHeight`). The animation variants are named for heights -- `trm_timescale_over_high_forward_75`, `_100`, `_140` -- so the "high" tier is authored somewhere around 75 to 140 | Names measured in the mod tools; the heights are **inferred from animation names** and are not defaults |
| Step height (player) | **not found** | No `bg_stepHeight` string in any of the 49 binaries and no player step constant in any script. `jump_stepSize` exists as a name only; BO1/WaW give it 18 | Not found in the mod tools |
| Step height (AI navmesh) | 18 units | `bin/default_navmesh_settings.json`: `"maxStepHeight": 18` | Measured in the mod tools, but it governs the zombie walkers, not the player |
| Stair build standard | rise 8, run 8/12/16 | Tool materials `stair_8x8`, `stair_8x12`, `stair_8x16` in `texture_assets/tools.gdt`; the community transcription says "Default Stairs Rise - 8" Run - 12"" | Measured in the mod tools |
| Sprint speed | **not found** | `g_speed` is not registered in the tools' dvar table at all; `player_sprintSpeedScale` is a name with no value. `player_sprintUnlimited` does not exist in BO3 | Not found in the mod tools |
| Gravity | 800 | `_zm_jump_pad.gsc:85`: `world_gravity = GetDvarInt( "bg_gravity" ); // 800;` and the next line divides it by 60 to get 13.3 | Measured in the mod tools, from a comment whose arithmetic checks out |
| Player body | 72 tall, radius 15 | `player_shared.gsc:15` `#define PLAYER_RADIUS 15`; `bot_traversals.gsc:25` `#define BOT_HEIGHT 72`; `deffiles/aitype.awi:125` `physRadius 15.0` / `physHeight 72.0`; navmesh `characterHeight: 72` | Measured in the mod tools, four independent files agreeing. The community "32 wide" is 30 or 31 in every local source |
| `jump_height 64` | **a mode override, not a default** | `scripts/zm/gametypes/_globallogic.gsc:185-195`, inside `if ( level.oldschool )` beside `player_clipSizeMultiplier 2.0`. A grep of all 17 GB finds this one assignment and nothing else | Measured in the mod tools. Nothing anywhere, local or community, supports 64 as the unconditional default |

</details>

<details>
<summary>Mantling is a material, and no zombies map has ever used one</summary>

`deffiles/material.awi:1286` gives every material a `surfaceClimbType`, one of
`<none>`, `ladder`, `mantleOn`, `mantleOver`, `climbWall`, `climbPipe`. Nine
of the 114 tool materials in `texture_assets/tools.gdt` set it: `mantle_on`,
`mantle_over`, `mount_mantle_on`, `mount_mantle_over`, three `ladder*` and
`pipe_climb` / `wall_climb`. The engine side is
`shared.gsh:120`, `#define CONTENTS_MANTLE (1 << 24)`.

Across Treyarch's 754 shipped `.map` files there are 274 faces textured
`mantle_on`, in **eight files, all multiplayer prefabs** (`mp_combine` and
`mp_sector`). There are **zero mantle faces in all 22 of
`map_source/zm/*.map`**, and zero uses of `mantle_over`, `ladder*`,
`wall_climb` or `pipe_climb` anywhere at all.

`_zm.gsc:222` sets `traverse_mode 2` for every zombies map. That dvar is
engine-only and carries no value in the tools, so what mode 2 permits is not
knowable from here -- which is one of the things the probe map below is for.

The practical reading, still a **hypothesis** until the probe is played: in
zombies the player has no mantle on ordinary brushwork, and a generated map
that wants a climbable ledge has to texture a brush `mantle_on`. This
generator cannot yet do that: `mantle_on` is a tool material and is not in
`SURFACE_CATALOGUE`.

</details>

### A probe map to measure it

One lit room, three instruments, no gameplay. No recipe for it ships; it
is a layout to build with a small recipe of your own. Walk up to each
instrument and try it; the answer is the highest thing you got onto.

- **A. Open ledges** (north row, nearest the far wall). Fifteen ledges at 24,
  28, 32 ... 80 units, each in its own bay so the row cannot be walked up
  four units at a time. Nothing stops a mantle here. **Highest one you can
  get onto = the climb.**
- **B. Capped ledges** (middle row). The same fifteen heights with a ceiling
  80 units over each ledge top, so there is room to stand and none to pull up
  through. **Highest one you can get onto = the raw jump.** If A and B give
  the same answer, there was no mantle to cap, which is the measurement that
  confirms the section above.
- **C. Gap lanes** (south, on the raised deck). Ten lanes, a 288-unit sprint
  run-up shared by all of them, then a void of 48, 64, 80 ... 192 units,
  then a landing at the same height. **Widest one you can clear = the jump
  distance.** Missing costs a 64-unit drop to the floor and a walk back to
  the stair.

Run it on round 1. Put its single barricade window, yard and riser on the
north wall, more than 1,500 units from the gap lanes.

<details>
<summary>Reading a height with no text material, and what the probe does not do</summary>

`SURFACE_CATALOGUE` holds no digits and no letters, so the ledges cannot be
written on. They are counted instead, from an anchor:

- Both ledge rows run **west to east, lowest to highest**, 4 units per bay.
- Every fifth bay -- **24, 44 and 64** -- is white (`t7_snow_powder_01`),
  the only white surface available. The bays east of a white one are +4, +8,
  +12, +16.
- The four bays between white ones cycle worn planks, red brick, dark iron
  and hexagon tile, in that order, so "second east of the white one" is a
  material and not only a count.
- The gap lanes run west to east, narrowest to widest, 16 units per lane.

Keep the legend as one table in the recipe, so the floor and the count
cannot drift apart.

What the probe does not answer: it carries no `mantle_on` brush, so it cannot
say what an authored mantle surface is worth. Measuring that needs a tool
material the generator does not write.

Expect the model checks to pass with one `N5` warning, which is inherent to
instrument C: the floor under a 48-unit gap is a 48-unit
strip, which is narrower than the 96-unit clearance standard. Nothing walks
there; it is the void being measured.

</details>

### What `JUMP_UP` became

**39**, from 64, without waiting for the probe. 64 is not the default of
anything -- it comes from inside an `if ( level.oldschool )` block and a grep
of all 17 GB of the tools finds that one assignment -- and a check that signs
off a 48-unit climb is wrong in play. 39 is second-hand, but it is the only
number anybody has, and a permissive limit is the worse error. If the probe
reads something other than 39, this constant moves again.

Two things changed with it, and a third was added:

- A climbing route of ledges climbs in steps of at most 32, not 48.
  Counters and rails whose tops are 40 to 56 units up are declared
  `reachable=False`, because at 39 they are furniture and not platforms, and
  the check is right to say their surfaces are floor nobody can get to.
- The flood's 16-unit "walked up" kerb is unaffected: it is an assumption
  either way, it is under the AI navmesh's own 18, and it is well under any
  jump.
- **`GAP_JUMP`, and the second kind of link.** The same `Scale_Standards`
  line that gives the 39 gives the standing jump about **100 units of
  distance**, and the sprint leap that would give ~220 is switched off in
  zombies (`_zm.gsc:216`, measured in the mod tools). So `Z25` now links two
  standing surfaces across a gap of up to **80** as well as across a touching
  edge, which is what lets a recipe build a course of platforms and have it
  proved rather than asserted. Four conditions, and each one is what stops it
  being a licence to fly: take-off and landing level to within floating-point
  noise; apart on one plan axis only, so a diagonal leap is refused the way a
  corner is; overlapping by at least a player's own 30 units on the other
  axis, so the landing is a surface and not an edge; and nothing in the lane
  between them whose top is more than a step above the two surfaces. Unlike
  every other number in that module 80 is deliberately **short**, because a
  link the flood makes here is the map asserting a player can clear it.

## Nothing stands on nothing

A map is built out of arithmetic, and arithmetic is how a slab ends up in mid
air. A column written to start at z 288 because 288 is the first floor's
height, on a deck that runs from 272 to 288, begins exactly **16 units above
the thing it was meant to rest on**. No other check can see it -- it overlaps
nothing, it is inside a zone, it blocks no route, it is lit -- and only a look
at the map finds it.

`Z43` is that rule. Every massing solid has to **rest** on something (another
solid, a room's floor or the terrain within 2 units below part of its
footprint), **hang** from something within 2 units above it, or be **fixed**
to something -- one of its vertical faces flush within 2 units against a
vertical face of another solid, over at least half of that face. A poster two
units off a wall, a handrail against a pier and a balcony deck cantilevered
off three walls of a hall are all the third kind, and all three are
ordinary map building.

A shared edge counts as bearing. A lid spanning between two dividers whose
tops are exactly the lid's underside, and whose footprints touch it edge to
edge with no overlap at all, is a lintel and is how anybody would build it.
What the row is looking for is a *gap*, such as the last lid of a row that has
no divider of its own and hangs 4 units over the only one near it.

What it does not ask is whether a thing fixed to a wall is fixed to it 400
units off the floor. That is a design question, not a check.

A map that wants something in mid-air says so on the geometry, once, with
`FLOATS_ON_PURPOSE` on the massing, the same way it says nobody can get onto
something with `reachable=False`.

Check: `Z43`, model level. An error each, with the height of the underside.

## A thing you buy does nothing

### A weapon the game does not have

Symptom: nothing. `getweapon` answers for a name that does not exist, nothing
raises, and the feature that asked for it does nothing.

Measured on the rigged mystery box, which asked for `shotgun_olympia`. That is
a Black Ops I and II name. It is in neither `zm_levelcommon_weapons.csv` nor
any assetlist on the install, and the box behaved like an ordinary box.

Rule: every weapon name the map or its script uses is a row of this level's
weapon table.

Check: `Z22`. A `getweapon` literal in a script is an error, because the script
named the weapon itself.

A wall buy is checked through its prefab rather than on its slug, because the
two are different strings. The slug names the `spawnable_weapon_<slug>.map`
file; the weapon is named inside it, on the buy struct's
`zombie_weapon_upgrade` key. All thirteen were read off the stock prefabs and
are `catalogue.WALL_WEAPON_WEAPONS`. Twelve are identical to
their slug. The thirteenth, `bowie`, carries `bowie_knife`, which is row 7 of
`zm_levelcommon_weapons.csv` at a cost of 3000 with `in_box` FALSE. So the
`bowie` buy hands out a real weapon: the slug is not a weapon name, and a
check must not read it as one.

The rest of that buy is wired in stock too. The prefab's struct has targetname
`bowie_upgrade`, and `_zm_weapons.gsc` collects that name alongside
`weapon_upgrade`, `sickle_upgrade`, `tazer_upgrade` and `claymore_purchase`
(lines 843 and 1326-1356 on the install). `zm_usermap.gsc` line 50 `#using`s
`scripts\zm\_zm_weap_bowie`, whose `__main__` calls
`zm_melee_weapon::init("bowie_knife", ..., cost, "bowie_upgrade", ...)`. A
usermap that does nothing gets the bowie system registered.

A slug with no stock prefab at all is an error. `place_wall_weapon` refuses
one before the model is built, so this is the backstop for a `WallWeapon`
assembled some other way.

### A wall buy facing the wrong way has no picture and no prompt

Symptom: nothing on the wall, and no prompt when you stand where the buy should
be.

Mechanism: `cod2map64` turns a prefab counter-clockwise by its yaw. That is
measured on a wall buy at origin `(-1264, -100, 8)` with yaw 270. The weapon struct inside
`spawnable_weapon_pistol_burst.map` sits at local `(-3, 0, 55)`, and the
compiled `.d3dbsp` carries it at world `(-1264, -97, 63)`. A counter-clockwise
270 maps local `(x, y)` to `(y, -x)`, giving `(0, 3)`. A clockwise turn would
have put it at `(0, -3)`.

The wall-weapon family's front is its local +Y, also measured: all thirteen
prefabs put the chalk patch and the weapon struct on the plane `y = 0` and the
mount brush behind them at `y` in -8 to -1.

Get either wrong and the chalk drawing faces into the brickwork, the mount
sticks out into the room, and the unitrigger origin sits inside the wall, so
the prompt cannot be reached either.

Check: `W3`, model level. It reads the emitted entity rather than the
blueprint, because this failed as an emitter bug and not a recipe one. It
probes 4 and 8 units in front of the buy at chalk height for a world solid, and
8 units behind it for the wall the mount needs.

### The wall buy charges one price and the prompt shows another

Symptom: the prompt over a wall buy says 1250, the player presses it, and 1337
points disappear. Or the reverse. Nothing in the build says anything.

Mechanism: a price is not a key on the buy. `_zm_weapons.gsc:3362
load_weapon_spec_from_table` reads a string table and
`add_zombie_weapon` (`:529`) stores each row's cost on a struct in
`level.zombie_weapons[ weapon ]`, which the purchase reads live. So a map that
charges its own prices ships its own weapon table, exactly as Treyarch's own
levels do (`zm_usermap.gsc:433`).

Getting the table loaded is two separate jobs, and the second is easy to
forget. The server's is a hook: `zm_usermap.gsc:135` installs the stock loader
with `DEFAULT( level._zombie_custom_add_weapons, &custom_add_weapons )`, and
`DEFAULT` only assigns while the variable is undefined, so a map that assigns
it in its own `main()` -- which runs before the framework entry -- wins.
The client has no hook at all: `zm_usermap.csc:83` calls `include_weapons()`
directly and that loads the stock table at `:95`. The number on the purchase
prompt is filled in client side. A map that does the server half and not the
client half charges its own price and displays Treyarch's.

Two more ways to ship a table and change nothing: assigning the hook after the
framework entry, where the `DEFAULT` has already filled it in, and loading the
map's table without loading the stock one first, which does not re-price the
level, it empties it down to the map's own rows.

Check: `W4`, file level, an **error** on each of those four. It reads both
emitted scripts and the manifest: the hook is assigned before
`zm_usermap::main()`, the stock table is loaded first, the same table is
loaded on both sides, and the manifest declares it so the linker packs it.

The name on the prompt does not come from this table: the weapon's name never
passes through it. Spec 5.7 renames a gun by a different route, a localised
string the map links and its own script points the buy at.

### A table row naming a weapon that does not exist

Symptom: a wall buy or a box that takes the points and hands over nothing, or
a weapon that never appears at all.

Mechanism: a `weapon` line in the zone naming an asset the database does not
have stops the link with an error, which is the good half. A **table row**
naming a weapon that does not exist is invisible to every tool: a string table
is opaque to the linker, which packs the text without reading it. `getweapon`
then answers for a name nothing backs, `add_zombie_weapon` files a struct
against it, and the failure happens in a play session.

Check: `W5`, model and file level, an **error**. At model level it refuses a
price for a weapon the stock level table does not have, because a re-priced
row *is* the stock row with one column changed and there is no row to change.
At file level it reads the written table back: every `weapon_name` and
`upgrade_name` is either a row of the stock table or a weapon the manifest
declares (`weapon,<name>_zm`, the pairing that links), every
row is the full 20 columns wide, and every cost is a non-negative integer --
`int( "" )` is 0, and a free wall buy says so out loud.

### A custom weapon whose definition nobody can point at

Symptom: a link that fails on a `weapon` line, or worse, a map that builds
on one machine and not on another.

Mechanism: a weapon is a first-class asset and its definition is a
`bulletweapon.gdf` entity in a `.gdt` -- around a thousand fields. The install
ships no stock weapon source to derive one from, so the definition is the
caller's file and the blueprint can only say where it is.
`zmforge.texture.gdtdb` registers it; `gdt.db` holds the result.

Check: `W6`, model level. A custom weapon with no `definition` is a
**warning**, not an error: registering the asset by hand works and stays
registered, it is simply not reproducible from the blueprint. Two custom
weapons claiming one weapon asset is an **error**.

### A prop's collision file that nothing wrote

Symptom: props that shoot through, or a link that fails on the model rather
than on the collision.

Mechanism: a prop's collision is two files and the asset-database entry names
both by string -- `BulletCollisionFile`, the `<asset>_col.XMODEL_BIN` bullet
mesh, and `CollisionMap`, a bare filename in `share\raw\collmaps`. The prop
chain writes the *text* export and the binary comes from `export2bin`
afterwards, so the entry names a file no step in this package produces. It
went unnoticed because nothing referenced it; when something did, the linker
reported it against the model. Measured: a prop chain's
`model_export/zm_forge_gate_props.gdt` names four `_col.XMODEL_BIN` files and
`model_export/zm_forge_gate/` holds none of them, and none of its four
collmaps are in `share\raw\collmaps` either.

Check: `Z27`, file level, an **error** per named file that is not there. It
also errors on an entry that asks for `BulletCollisionLOD "Custom"` and names
no file, which converts with no collision at all.

### A prefab turned to face somewhere other than where it was asked to

Symptom: a machine, a box, a switch or a barricade that is the right thing in
the right place pointing the wrong way. Against a wall that means into the
wall: the model is in the brickwork and its collision is on the wrong side.

Mechanism: two numbers, and it is easy to get both wrong for every family
except the wall buys. The turn is counter-clockwise -- measured on the
compiled `.d3dbsp`, see the wall-buy entry above -- and the heading each
family's front points at yaw 0 is per family. Every family was read off its
own stock prefab in the install; spec appendix B carries the
table and the evidence line for each row. They disagree: wall buy north, perk
machines south, pack-a-punch **west**, mystery box north, power switch south,
barricade exterior north. The stand under the mystery box has no front at all
and takes the box's yaw.

The failure was invisible three ways over. The clockwise turn is right on the
two headings parallel to a family's front and 180 degrees out on the other
two, so half of every map was correct. The pack-a-punch was being given the
perk front as well, which is a further 90 degrees, so it was wrong on all four
headings and no comparison of the two turns could have shown it. And the
prompts survive all of it: a perk's use trigger is a `trigger_radius_use` at
the machine's origin (`_zm_perks.gsc:1508`), and so is the pack-a-punch's
(`_zm_pack_a_punch.gsc:106`), so a machine facing a wall still sells you the
perk. Only the mystery box loses its prompt, because `_zm_magicbox.gsc:294`
offsets its unitrigger off the box's own front.

One correction rode along with the measurement. The riser paired with a
barricade is not a prefab: it is an AI spawn struct whose angles are a plain
world heading. "Barricade yaw + 180" agrees with the stock convention on no
heading at all. The stock barricade prefab settles
it -- its own `exterior_goal` struct stands outside the window and faces
straight back at the barricade -- so a riser faces the opposite of the
exterior heading.

Check: `Z23`, model level, an **error**. Like `W3` it reads the emitted
entities rather than the blueprint, because this failed as an emitter bug and
not a recipe one: it builds the document and compares every machine, box,
switch, scenery prefab and barricade entity's yaw against the measured
`(heading - front_at_yaw_zero) mod 360`. It stays a **warning** in one case:
a bare scenery prefab whose `.map` path is not in
`catalogue.PREFAB_FRONT_ZERO_BY_MODEL`. Nobody has opened that prefab, the
emitter fell back to a named guess, and the check says so rather than claiming
a defect it cannot prove. A prefab placed with a raw `yaw` is not reported at
all; the caller established its own zero heading.

On the shipped recipes the check reports nothing. That it can report
anything is not taken on trust: putting a clockwise turn into
`catalogue.prefab_yaw` and changing nothing else reports an error for every
east- or west-facing perk and pack-a-punch, and three on `zm_forge_gate`, one
for each of the mystery box's entities.

## A model that promises a way up

A staircase is not an object. Every other model a map places is one -- the
player looks at it, walks round it and is done -- but a staircase is an
**instruction**: whoever sees it reads "that is the way up", walks to it, and
is owed a floor at the top. Nothing in a generated map can keep that promise
with a model. A prop is drawn, not built; its collision is whatever hull
`cod2map64` bakes from a collmap (`Z21`), not a set of treads, and the props
emitted `no_collmap "1"` are walked straight through. So the player walks to
the picture of a staircase and finds a box, or finds nothing.

This is not a defect in where the model was put, which is why the rule is flat
rather than geometric. There is no position that makes a prop staircase true.

What it catches: `p7_cai_staircase_01` (109 x 191.5 x 131.5, the largest
model in the palette) and `p7_zm_der_teleporter_mf_ladder`, dealt out of
themed palettes by `Row` and `Fill`, rules that place whatever model an index
lands on at a computed point. A prop staircase climbs 131.5 units and arrives
at nothing when the floors it stands between are, say, 272 and 320 units
apart, and it can hang part of its footprint over a balcony edge into open
air. Every row of this table passes it.

The interesting part is *why* they passed, because it says what the table was
missing rather than which row was wrong. `Z19` asks whether a flight of steps
connects at both ends, and a map's real flights can all pass it at exactly
zero units of mismatch at every head and foot -- but `Z19` asks it of
`add_steps` brushwork, and a prop staircase is a model, which no
geometric row in the table looks at. `Z25` floods the map and reports what is
**stranded**, and a staircase that goes nowhere strands nobody: a useless
piece of map is invisible to a reachability argument by construction. Between
them those two rows ask whether the map as a whole is traversable. Neither
asks whether a piece of it does the job it was placed to do, and that is the
question a person answers instantly by looking.

Check: `Z41`, model level, an **error**, one per prop. The screen is on the
model's name -- `catalogue.ROUTE_WORDS` -- rather than an allow-list, because
a hand-classified table of a hundred and twenty-nine models goes stale the
first time somebody adds one, and these are stock Treyarch models whose names
describe them. A name that trips the screen and is genuinely not a route goes
in `catalogue.ROUTE_MODELS` as `False`, so an exception is a judgement written
down beside its reason rather than a check turned off.

The recipe side is the real fix and this is the backstop.
`recipes.props._model` takes a `strewn` flag that `Row` and `Fill` pass and
`One` does not: a scatter rule that lands on a route model steps past it to
the next model in the theme. The index a scene was written against still means
"start here", the placement still happens, and the scene keeps its model
count, with the route models replaced by objects instead of instructions. What the backstop covers is
everything that does not go through a scatter rule: a hand-written
`place_props` call, a deliberate `One`, or another recipe entirely.

## Half a model, placed as though it were the whole one

Rule: a stock model that Treyarch only ever ships as part of an assembly is
placed with the rest of that assembly.

`p7_cai_staircase_01` is not a staircase. It is the **frame** of one -- two
stringers, a handrail each side and a glass balustrade -- and its treads are a
separate model, `p7_cai_staircase_step_01`, placed once per step. The
install's own prefab says so:
`_prefabs/mp/mp_combine/geo/mp_combine_aquaculture_bdg_south/mp_combine_lab_staircase.map`
is one frame at `-58 6 40` and eleven treads at `-58 13 46` through
`-58 133 126`, `+12` along Y and `+8` in Z apiece, and
`_prefabs/mp/mp_sector/.../mp_sector_lab_staircase.map` is the same eleven at
the same offsets. The rotation sense is measured off the same corpus rather
than assumed: the outdoor staircase prefabs carry their treads at
`angles "0 270 0"` climbing in `+X` and the external deck carries its at
`"0 90 0"` climbing in `-X`, which is the counter-clockwise turn
`catalogue.prefab_yaw` already records.

What the player sees when the frame goes in alone is **handrails standing
in mid air with nothing between them**: frames, no treads.

Nothing else in the chain can see it, and that is the point of the rule. The
model name is spelled correctly and the model exists; `cod2map64` logs no
`Material ... is missing` and no warning of any kind for it; the linker packs
it, and the build's own
`zone_source/all/assetlist/<map>.csv` carries
`xmodel,p7_cai_staircase_01` with all of its meshes, its collision mesh
and both its materials, so the packer's report says the asset arrived intact.
It did. The asset is half a staircase.

Check: `Z29`, file level, an **error**, one per incomplete assembly. It reads
the written map rather than the blueprint, so it also covers props added
afterwards by the `props-place` pass, and it compares each placed frame
against `catalogue.MODEL_COMPANIONS`, which holds the offsets and names the
prefab each was read from. The emitter writes the companions itself, so the
check is a backstop rather than the fix.

`Z41` and this rule are different questions about the same entities.
`Z41` says a model may not *depict* a route; `Z29` says a model may not be
*half of itself*. A complete prop staircase in a decorative corner still fails
`Z41`; a frame placed deliberately by a caller who wants the object, not the
route, still fails `Z29` until its treads go in.

### A machine you cannot walk up to

Rule: every perk machine has a `#using` line for its module in **both** the
server and the client script. Machines, the box and the switch stand on
reachable floor, sit at most 8 units above it, and have clear floor in front to
be used from. The approach box is 40 wide by 64 deep by 64 high, starting 24
units out from the origin.

A perk is two halves. The server module is the machine's logic; the client
module is the perk's clientfields, its HUD callbacks and its machine effect
(`_zm_perk_juggernaut.csc:20-30` is a `REGISTER_SYSTEM` calling
`zm_perks::register_perk_clientfields`, `register_perk_effects` and
`register_perk_init_thread`), and every perk module in the mod tools' raw
scripts ships a `.csc` beside its `.gsc`. Treyarch's own map names each perk
module in both files: `zm_giant.gsc:30-38` against `zm_giant.csc:21-28`. A
map that names them in the server script only is missing the client half of
every perk it places. **What that looks like in game is unverified**: the
rule is read out of the shipped map source, not seen in a match.

The approach box's dimensions are inherited and unverified. The stock machines
carry their own `zm_collision_perks1` clip and nothing here has measured it.
The width is deliberately tight, because a machine 24 units off a wall is a
working placement.

Check: `Z9`, model and file level. Blocked space is an error. No floor in
front is a warning, because a machine at the edge of a drop is a legitimate, if
cruel, thing to build.

### A machine standing side-on to its wall

Rule: a machine, the box and the switch put their **back** on the brushwork
they are up against, not their side. `facing` is the heading the item's front
points at -- the face with the prompt on it -- so an item against the north
wall faces south. A quarter turn out stands a 64-wide machine broadside to
that wall, with its body through the brickwork and its prompt read along the
wall instead of out of it.

Nothing else can see it. `Z23` cannot: the yaw emitted is exactly the yaw the
authored heading asks for, which is the point of `Z23`. The other `Z9` rows
cannot: the origin is in open air and the 64 units in front of it are clear.
A pack-a-punch 24 units off a north wall facing west has 8 units of the
machine inside the wall, and nothing but this rule reports it.

<details><summary>Why a wall behind it exempts the item, with the numbers</summary>

Two conditions, and only both together are a defect: world brushwork reaches
into the item's own body forward of its origin plane, **and** there is nothing
within `reach.APRON_DEPTH` (96) straight back from its back face. The back is
excluded from the body test because that is what against-the-wall means: a
machine stands flush against its wall.

The behind-probe is 32 wide rather than the item's own 64, or the very wall
cutting across the item's side would answer the question and the defect would
exempt itself.

An item in a nook is deliberate and stays silent: a pack-a-punch standing in
a 48-unit gap between two piers, clipping 8 units of each, with its back wall
31 units behind it, works in game, and the rule leaves it and any machine
clipping brushwork the same way with a wall behind it alone.

</details>

Check: `Z9`, model level, an error.

### A Der Wunderfizz with nothing to give

Rule: a map that places Der Wunderfizz names `scripts\zm\_zm_perk_random`
in **both** scripts, marks exactly one machine the starting machine, gives
every machine the six zbarrier boards the stock script drives, and registers
at least one perk in its rotation whose own perk module the script also
carries.

Plain English: the machine sells a random perk, and the list it draws from is
a separate thing from the perks on the map. Nothing fills it in for you. A map
can place the machine, link with no errors, and hand the player a fault the
first time they spend 1500 points on it.

<details><summary>The four ways it fails quietly, and the lines that say so</summary>

Read out of
`share/raw/scripts/zm/_zm_perk_random.{gsc,csc,gsh}` in the mod tools. **Nothing here is
observed in game.**

- **No rotation.** `include_perk_in_random_rotation` (`:617-624`) is the only
  writer of `level._random_perk_machine_perk_list`, and
  `get_weighted_random_perk` (`:627-658`) reads it with `GetArrayKeys` and
  then indexes `keys[ 0 ]`. Place the machine, register nothing, and both
  reads are against an undefined array.
- **No starting machine.** `init_starting_perk_random_machine_location`
  (`:123-150`) threads `machine_think()` on the first machine whose
  `script_noteworthy` contains `start_perk_random_machine`, and sends every
  other one to `wait_for_power()`. None marked means none ever thinks.
- **A perk the map cannot render.** `get_perk_weapon_model` (`:725`) reads
  `level.machine_assets[ perk ].weapon` for whatever it is about to hand
  over, and only a perk *module* writes that array
  (`_zm_perk_juggernaut.gsc:72`). A rotation entry whose module the script
  does not carry is a bottle with no model. This is why the generator's
  default rotation is exactly the perks the map places.
- **Half a machine.** The `.csc` registers every clientfield the `.gsc` sets
  and precaches the four effects (`_zm_perk_random.csc:19-22`, `:33-41`), so
  the module belongs in both files -- the same rule `Z9` applies to a perk.

Nothing has to be imported for any of this.
`zone_source/all/assetlist/zm_levelcommon.csv` already carries
`xmodel,p7_zm_vending_wonder` (`:1990`), all three script halves
(`:7053-7055`) and the four effects (`:6584-6586`, `:6880`), so the map
declares no asset and precaches nothing. There is no Wunderfizz prefab in
`map_source/_prefabs` in the mod tools and none is needed: the machine is one
`zbarrier_*` entity with its pieces in keys, the same way the mystery box is
written.

</details>

Check: `Z49`, file level, an error (two warnings: more than one machine
marked the starting one, and a rotation registered on a map with no machine).

### A perk the map wrote itself, that nothing can buy

Rule: a map may ship perks of its own, and each one has to be whole. It hands
`register_perk_basic_info` a bottle; its registration function is called from
`main` and called **before** `zm_usermap::main()`; there is a
`zm_perk_machine` struct carrying its specialty, and no struct carries a
specialty nothing registers; the prompt it names is precached; and no two
perks -- one of ours, or one of ours against a stock perk the same map places
-- claim the same HUD slot.

Plain English: a perk is five function calls, one struct and one line of text,
and the game checks none of it. Leave any one of them out and the map links,
loads, and hands the player a vending machine that charges them and does
nothing, or does not charge them at all because it never turns on.

<details><summary>The five ways it fails quietly, and the lines that say so</summary>

Read out of `share/raw/scripts/zm/_zm_perks.gsc` in the mod tools.
**None of it is observed in game.**

- **No bottle.** `:1825` asserts the argument. `:612` takes the points, `:594`
  onwards gives and switches to the bottle, and `:617` grants the perk **only
  if** the weapon change completes. A bottle that does not resolve is a
  machine that charges and gives nothing -- which is what the community
  reported from the other side: no drink animation, no icon, no effect, no
  sprint (UGX-Mods 14197).
- **A script the map never runs.** The registration lives in a function, and a
  function nothing calls does nothing. It has to be called from `main`, and
  before the framework entry: the entry reaches `zm_perks::init`, which runs
  every registered perk's precache function (`:40`, `:172-184`) and starts
  every machine loop (`:84-102`). A registration after it is read by nobody.
- **A perk with no machine.** `perk_machine_spawn_init` builds the use
  trigger, the bump trigger and the collision from the struct and from nothing
  else (`:1419`, `:1437`). A registered perk with no struct is a perk nowhere
  sells.
- **A machine with no perk.** The other way round and quieter: a struct whose
  `script_noteworthy` names a perk neither the stock scripts nor this script
  registers. `:1437` collects it, finds no `level._custom_perks` entry behind
  it, and the machine stands there and never turns on.
- **Two perks, one HUD slot.** The icon is a hard-coded key inside the shipped
  interface widget, which is Lua the mod tools' linker refuses to pack. Two
  perks writing one `hudItems.perks.<key>` path is one widget being told two
  things, and nothing in the map decides which write lands last. Claiming a
  key a stock perk on the same map owns is the same defect with a shipped perk
  on the other side.

And one thing that is cheaper to catch here than in a play session: a prompt
the script names and never precaches, which is a machine with a blank line on
it.

What a perk of ours costs, honestly: no `.gdt` entity, no image, no sound
bank, no effect file and no change to anybody's install. What it does not buy
is a jingle -- a generated usermap has no perk sound aliases at all -- and an icon
only by claiming one of the two keys the shipped widget binds to art the game
never shipped. `docs/how-zombies-maps-work.md`, "What registering a perk
actually involves", is the full reading.

</details>

Check: `Z50`, model and file level, an error (three warnings: a bottle that is
not on the stock list, a HUD path the widget does not bind, and a slot whose
stock owner is not on this map).

### A client field registered after the framework entry

Rule: every `clientfield::register` a map's own scripts make is written
**before** the `zm_usermap::main()` call, on both sides.

The engine closes clientfield registration in
`CodeCallback_FinalizeInitialization`, which `callbacks_shared.gsc:539-546`
introduces as the engine's last initialisation step. The
framework entry yields before it returns -- `zm_usermap::main()` calls
`load::main()` (`zm/_load.gsc:77`), which waits at
`system::wait_till( "all" )` (`:105`) -- so a registration written under the
entry call runs on the far side of that wait, with the period already shut.

<details><summary>The crash this rule prevents, and what moved</summary>

A map generated with eight player slots links clean (exit 2000, no error
lines), installs, and the game refuses it at load with `Attempt to register
ClientField laststand_update4 post finalization of ClientField registration
period failed` when the registration comes after the entry call.
`laststand_update4` is written by one thing: the seats-5-and-up extension a
map with more than four spawn slots emits.

Only the registration moved. The level arrays those names live in --
`level.laststand_update_clientfields`, `level.player_name_directive`,
`level.laststands` -- are assigned empty *inside* the entry
(`_zm_laststand.gsc:52`, `:91`, `.csc:19`), so writing them early would write
them into arrays the entry then replaces. The bookkeeping stays after the
entry; the `clientfield::register` calls go before it, on the server and on
the client together, which keeps the two halves agreeing about which fields
exist.

Not verified in game: what is measured is the crash it is written against.

</details>

Check: `Z51`, file level, an error, over both emitted scripts.

### The server and the client register the same fields

Rule: every clientfield the map's own scripts register is registered on both
sides, in the same order, with the same pool, name, version, bits and type.
The engine compares the two lists at connect and drops the connection on a
difference, even in a solo game where both halves are one machine.

This is measured. An eight-seat map that loads past the Z51 crash is then
refused, even solo: "Server Disconnected - Clientfield Mismatch". The server registered six `clientuimodel` score fields for
each of seats 5 to 8 and the client registered none.

<details><summary>Why the stock score fields get away with it and ours did not</summary>

`_zm_score.gsc` registers the six `PlayerList.client<i>.score_cf_*` fields
server side only, and says the client half lives in
`ui/uieditor/clientfieldmodels.lua`. That file's loop over those names stops
at a hard-coded four (T7LuaRepo PC ship dump, lines 84-91), and a usermap
cannot ship Lua (Z47). A `.csc` can register a `clientuimodel` field, though
(`_zm_perk_juggernaut.csc:42`, `zm/_load.csc:132`), so the client script now
registers seats 5 and up itself, with bits 3 and 2 as the Lua gives seats 1-4.

The check reads both emitted scripts, takes every `clientfield::register`
call's first five arguments plus the `for` loops around it (the name is an
expression, so the loop bound is part of which fields exist), and compares
the two lists entry by entry. Fields the framework registers inside the
entry are not in the map's scripts and are not compared.

Not verified in game. Without a `logfile` dvar the game writes no console
log, so the mismatching field names come from reading the scripts, not from
the engine's own report.

</details>

Check: `Z52`, file level, an error, over both emitted scripts.

### A prop standing in a doorway

Rule: no solid prop taller than a step (18 units) stands in a doorway or in
the floor either side of it. The clear zone is the opening's width plus 8
units each side along the wall, and 48 units into each room (a 32-unit
player plus margin). Paper and props raised on something else do not count.

Measured on `zm_dmv`: a filing cabinet against a wall that reaches 10 units
into an 80-unit doorway blocks the player from the machine behind it, and
nothing else catches it: `Z44` compares props with each other, `Z25` still found a route
through the narrowed door, and `Z48` only checks items.

Check: `Z53`, model level, an error (`verify/doorways.py`).

### A prop reaching into a wall

Rule: a solid floor prop keeps every corner of its measured, turned footprint
inside the room it stands in, to within 1 unit of the inner wall face. Hollow
props and wall or ceiling fixtures are not checked. A model placed through a
wall on purpose must be listed, with its reason, in `THROUGH_WALL` in
`verify/walls.py` (empty by default).

Measured on `zm_dmv`: cabinets and shelves turned with their long side into
the wall reach 24 to 37 units past its inner face, and nothing else flags
them: `Z44` compares props with each other and `Z53` only checks doorways.
Run along their walls with their backs flush, they pass.

Check: `Z54`, model level, an error (`verify/walls.py`).

### No invisible side on a box the player can see

Rule: a world box that draws any face leaves no undrawn (caulk) face of 8+
units open to room or outdoor air. Caulk draws nothing, so the player looks
through that side, and whatever stands on the box floats. A face flush with a
wall, the floor, the ceiling, another box or a placed prop is hidden and may
stay caulk; an underside under 40 units over the floor is below a crouching
eye and is not asked.

Example: a raised floor with a caulk face on the side behind it looks solid
from the front and, from behind, leaves the props on it hanging in the air.
`Z44` passes them because the floor's top does hold them up. The same
rule catches the unpainted back of a name plate on a prop and a coping's
4-unit overhang (on `zm_dmv`); plates on props paint their backs, and a coping
is trim all round.

Check: `Z84`, model level, an error (`verify/exposed_faces.py`).

### Furniture that cuts a room in two

Rule: inside each room, every doorway, perk machine, wall buy, mystery box,
power switch, barricade and quest use trigger is joined to the others by floor
a 30-unit player fits through, past the solid props and brushes. The floor is
rasterised at 8 units and each obstacle's footprint is grown by the 15-unit
player radius. A corridor under 40 units on the widest route is a warning.
A quest trigger counts as reached from anywhere inside its own radius.

<details><summary>What is measured, what is not</summary>

- Obstacles: solid props (turned measured footprint) and world brushes that
  rise out of this floor into the band from 18 to 72 units over it.
- Out of scope: targets and props on raised ground (terrain, platforms) are
  left to `Z25` and `Z48`, which flood in 3D. A target on a desk is kept.
- `zmforge check` re-asks it of the stored `<map>.blueprint.json`; a
  blueprint written by an older version carries no quest triggers, so they are
  not checked there.
- What it catches: a planter 26 units in front of a wall buy, or a chair
  standing on a quest item so the item is usable only from the edge of its
  44-unit trigger. `cemetery`, `corn_maze` and `dmv`: 0 findings.
- The raster is 8 units, so a cell counts as walkable at 11 units' clearance:
  a 30-unit gap always passes and one under 22 always fails.
</details>

Check: `Z55`, model level, an error (`verify/routes.py`).

### How it looks: three recurring visual defects

Three warnings for visual defects that recur from map to map. They are
warnings because a look fault does not stop a map playing, and a commit
refuses a map on any error. Some look rules are enforced by a shared helper or
a principle (`map-principles.md`) rather than a check.

- **Flat floor lettering.** No brush lettering lies flat on a floor or the
  ground (within 18 units of it). From eye height it reads as grey planks in
  every render: flat floor signs belong on a
  hung board. Use `zmforge.dressing.hanging_sign`
  or letter a wall. Check: `Z56`, model level, a warning (`verify/looks.py`).
- **A bare open-air wall.** An open-air room's wall over 600 units long has
  no run over 320 with nothing against its inner face (a pier, a coping, a
  plinth, a prop or an opening); otherwise a long shot of it is 2,000 units of
  flat brick. Use `zmforge.dressing.boundary_wall`. Check: `Z62`,
  model level, a warning (`verify/boundary.py`).
- **A hidden or empty sky.** An open-air room's walls stand no more than 320
  over its floor (build it with `add_room(wall_height=...)`, which caps the
  rest in clip), and on a side facing open air something beyond the wall
  rises over it. Use `zmforge.dressing.backdrop`. Check: `Z63`, model level,
  a warning (`verify/boundary.py`).
- **A solid in front of a barricade window.** No solid prop taller than a
  step stands within 64 units of a barricade window's opening, either side of
  the wall, over its width plus 16 each side, below the opening's top.
  Zombies climb in there and players rebuild there. zm_corn_maze had a heap
  45 units off a farmhouse window, caught only by a corn-only keep-out.
  Check: `Z57`, model level, a warning (`verify/looks.py`).
- **A model that reads badly.** No placed model is on the deny-list
  `READS_BADLY` in `src/zmforge/props/reads_badly.py`: models that render as something they are not (such as a picture that draws as a dark panel). The same warning covers a model whose `src/zmforge/props/notes.json`
  entry is measured to render `dark`, `blank` or `editor_invisible`, so a
  reviewer knows what the preview will show. One warning per model per map,
  with the count. Check: `Z58`, model level, a warning (`verify/looks.py`).
- **A prop without its partner.** A prop whose `notes.json` entry (its own,
  or a category's by `pattern`) says it `needs` a partner has one, where the
  blueprint can tell: a curtain has a rail or bar within 8 units of its top
  (`zmforge.dressing.hang_bar`), a desk monitor has a desk, counter or other
  top within 4 units under it. `chair_facing` and free-text needs are not
  judged: a chair model's front is not known from its box. One warning per
  model and need per map, with the count. Check: `Z59`, model level, a
  warning (`verify/looks.py`).
- **A prop that breaks its own rules.** A prop's `rules` block in
  `src/zmforge/props/notes.json` (its own, merged over its categories') is
  kept, where the blueprint can tell: a chair does not turn its back on a
  desk within 24 units, a desk monitor has a seat within 72 facing it, a
  sign or wall screen faces into its room and touches a wall, a wall screen
  hangs with its middle 40 to 200 over the floor, a vending machine keeps 32
  units clear in front, a sink has legs or a counter under it, a pipe run
  reaches a floor, ceiling, wall or fixture, and a scarecrow's brush parts
  touch. Orientation is judged only for models whose front was measured
  (measured once; the result is in ``src/zmforge/props/notes.json``); the rest are skipped. One warning per rule and
  model per map, with the count. Check: `Z60`, model level, a warning
  (`verify/prop_rules.py`, which lists the rule types).
- **A glow that belongs to an object goes out with it** (P12). A static
  (baked) light within 96 units of an object a script removes or a quest
  finishes, and a looping `powerup_on*` effect played with `PlayFX`, are both
  warnings: neither can be switched off (the corn maze's shot lanterns stayed
  lit). Use `zmforge.script.glow.place_owned_glow` (an
  exploder light, off on the object's notify). Check: `Z64`, model and file
  level, a warning (`verify/glows.py`).
- **A roofed room seen over a low wall has a facade.** Where a roofed room's
  outer wall rises over a neighbouring open room's low wall, something must
  stand proud of it (buttresses, a cornice, windows, a roof); a bare outer
  wall reads as a huge blank slab. Use `zmforge.dressing.facade`. Check: `Z65`, model level, a
  warning (`verify/boundary.py`).
- **Foliage grows in clumps.** A room's plants, grass, weeds, hedges and
  fallen leaves gather at wall feet, grave edges, kerbs and the bases of
  trees and monuments, big bushes with smaller ones and grass round them,
  with bare ground between the clumps and along the walks. An even scatter
  reads as planted by a machine however dense it is. The measure is the Clark-Evans nearest-neighbour ratio of
  the room's foliage (about 1 is a random scatter). Use
  `zmforge.dressing.cluster.mixed_clumps`. Check: `Z66`, model level, a
  warning at a ratio of 0.85 or more over 40 or more foliage props
  (`verify/evenness.py`).

`Z54` also warns (not an error) on a hollow prop resting on a surface, such
as a shelf or a desk, that reaches more than 3 units past its room's wall:
zm_corn_maze's barn shelf items stood 5 to 11 units into the walls. Placers
keep surface items on their surface with `zmforge.dressing.fit_within`.

### Scenes, quests and play structure

These come from [map-design-method.md](map-design-method.md): sections 1-4
(every area is a scene, dressed near the stock density) and section 8 (play
structure, from published level design guides).
All are warnings: a map that breaks one still plays.

- **Every area is a scene.** Each room declares a one-line story and shows the
  beats it promises; a scene may name its `cause` and the one telling detail
  that proves it (`tell`, a model name or prop id). Check: `S1` (no scene, a
  promised beat missing, a `tell` no prop in the room matches, or a `cause`
  with no `tell`); `S2` density at a quarter of stock (40% in a room of
  0.5 k2 or more) and something above head height; `S3` a set piece in a
  room over 0.5 k2; `S4` an effect in an open-air room; `S5` 50+ overhead
  props per k2 and `S6` no flat wall run over 256 units in a roofed room of
  0.5 k2 or more (`verify/scenes.py`, `zmforge.dressing.declare_scene`,
  `zmforge.dressing.walldetail`).
- **No quest step before its room is open.** Check: `Z61` (`verify/quest_gates.py`).
- **The power switch is reachable before the power is on.** A door can wait
  for the power (`electric`: opens by itself; `requires_power`: the stock
  `electric_buyable_door`, sold only after it, with the stock "power required"
  hint until then). Check: `Z80` error when such doors cut every way from the
  spawn to the switch (`verify/power_reach.py`).
- **A closed door fills its opening.** The stock one-piece leaf is 120 x 102
  at modelscale 1; the generator scales and tiles it to each opening
  (`Door.leaves`). Check: `Z81` error on a gap at a jamb or over the leaf, an
  unmeasured or missing leaf model, or an opening under the 30 x 72 player
  hull (`verify/door_cover.py`).
- **Every playable map has the gamble machine at its farthest walk**
  (P22): 2,000 for a 1 in 4 chance at 10,000, once per player per round.
  Check: `Z87` error when a map not opted out (`bp.signature_gamble = False`,
  test maps) has none or more than one, when its stand is off the `Z25`
  flood, or when the written script charges before `can_player_purchase`
  for the same amount or draws its odds without `RandomInt`
  (`verify/gamble.py`, `dressing/gamble.py`, `script/gamble.py`).
- **A wall lined with plants is hidden by them** (a wall that shows
  between the plants reads as bare wall).
  Check: `Z89` error when the zmforge-generated plants in the band of a
  spread sample of the faces a recipe lined (`bp.lined_faces`), drawn
  head-on from their real meshes, hide under 75% of the face on average
  (`verify/lining.py`, `dressing/lining.py` `hidden_fraction`).
- **No developer-only script calls outside a devblock** (otherwise the map
  fails to load with "Dev only calls must be wrapped in a devblock").
  Check: `Z90` error when a generated `.gsc`/`.csc` calls a builtin the
  stock scripts only ever call inside `/# #/` (`PrintLn`, `Print3d`,
  `Line`, ...) outside one (`script/gsc.py` `dev_only_calls`,
  `verify/files.py`).
- **No wall buy on a wall lined with plants** (a wall
  buy's chalk and walk-up cleared the corn in front of it and left bare wall).
  Check: `Z91` error when a wall buy hangs on a face a recipe lined with
  plants (`bp.lined_faces`); `placement/wallbuy.py` `place_wall_buy` puts it
  on the nearest unlined wall of its zone.
- **Gameplay guards over the written script** (`verify/gameplay.py`, run by
  `zmforge check`).
  `Z67` error: `init_zones` holds a zone a door opens (manage_zones enables
  every entry at load, `_zm_zonemgr.gsc:841-844`). `Z68` error: a fire
  handler that pays points has no per-player cooldown, or can return after
  paying. `Z69` error: a thrown weapon watched on `weapon_fired` instead of
  `grenade_fire`. `Z70` warning: `zombie_spawn_delay` restored from a saved
  value instead of `level.func_get_zombie_spawn_delay`. `Z71` error: a player
  moved after a wait with no last-stand check. `Z72` warning: a `*_PROMPT`
  string without `[{+activate}]`. `Z73` error: a boss without the Insta-Kill
  guard (`zmf_no_instakill` and `level.check_for_instakill_override`).
  `Z79` warning: more than 2 flavour broadcasts (gag lines printed on
  entering a zone, at a round end or on a random timer; P13,
  P17). `Z82` error: no perk limit; after `zm_usermap::main()` the
  script sets `level.perk_purchase_limit` and the purchase-time pointer
  `level.get_player_perk_purchase_limit` to at least 99 (`NO_PERK_LIMIT`),
  and nothing else assigns either (`_zm_perks.gsc:43` sets 4 inside that
  call; every map has no perk limit).
- **Players spawn in at most one sealed pocket of air.** The linker's
  occlusion pass keeps the open air plus one sealed pocket (every link log:
  "Filtered N/N+2 inside clusters"), and a player in a dropped pocket sees
  floors and walls flicker to the sky. Every other pocket a player stands in
  is opened to the air inside the sky shell (`Blueprint.add_yard_vent`).
  Check: `Z83` error (`verify/umbra_air.py`).
- **Every barricade window is a window.** A drawn, non-colliding sill wall to
  `SILL_WALL_HEIGHT` (32, Treyarch's sill) under its floor-cut hole, and a
  closet with real materials, dim unstacked lamps and some clutter. Check:
  `Z85` error for a missing sill, a warning for a bare closet
  (`verify/windows.py`).
- **A bled-out player respawns near the team.** Every
  `player_respawn_point` has a `target` naming a group of 4-8 points (one
  struct per zone, as `zm_giant.map`; `_zm.gsc:3453` reads it, and without it
  the player respawns at their initial spawn), stands in the
  `player_volume` its `script_noteworthy` names, and is off every colliding
  brush and on the `Z25` flood. Check: `Z86` error
  (`verify/respawn_points.py`, `blueprint/respawn.py`).
- **Quests survive interruptions, co-op works, bosses are fair, no luck
  gates** (common Workshop player complaints; `verify/quest_safety.py`, run
  by `zmforge check`).
  All errors except the second half of `Q6`.
  `Q1`: every quest or boss thread that waits ends on `end_game`, a thread on
  a player ends on `disconnect`, a player from a trigger is re-checked with
  `isdefined` after a later wait.
  `Q2`: a carried item (a form, the shovel) goes back to its spot when its
  carrier goes down, bleeds out or leaves.
  `Q3`: a timed or hold step pauses during a special round or holds special
  rounds back (`Step.lockdown`), and a held step does not start during one.
  `Q4`: HUD elements are per player, or level-wide under a
  `// level-wide HUD:` line (the boss waypoint).
  `Q5`: every-player counts and player-count scaling use the players present;
  no one-shot trigger moves only the player who touched it.
  `Q6`: every boss declares `self.zmf_boss_ttk` (`BossHealth.ttk`, seconds of
  one player's fire with the best guns reachable by that round,
  `bosses.GUN_TIERS`: estimates calibrated on the Gravedigger design target,
  100,000 solo at round 6 = 40 s at 2,500 a second); a warning when normal
  spawns do not ease off during the fight (`Boss.fight_zombie_limit`, 10 by
  default). Not checked, template defaults: a boss runs, never sprints
  (`Boss.speed`; `hurt_speed` adds an optional second phase), and
  `Boss.armour` cuts its damage taken while its minions live.
  `Q7`: no required step depends on a random roll without a pity counter, a
  random teleport, a random power-up, the box, or a weapon on no wall.
  Co-op itself is not automated: a test game with two or more players is the
  manual pass.
- **A ring to train round.** Every zone with zombie spawns has a closed
  walkable ring round a central block, lanes at least 128 units wide and at
  least 1000 units round, measured on a 16-unit floor grid of the zone's rooms
  and the doorways between them (solid props over a step and every brush are
  obstacles). Narrow lanes and pinch points belong in transit between areas.
  Check: `D1` (`verify/design.py`).
- **Points to core.** The cheapest door spend from spawn to Juggernog, Quick
  Revive, power and the first box. A fact, not a check: the review facts print
  it as `map.points_to_core`; there is no threshold until stock maps are
  measured. Row: `D3`, manual. (Two ways out of a room with an essential is
  not a rule; code D2 is unused.)
- **Show the lock before the key.** A quest's hand-in desk and its buyable
  exit stand in a zone that opens no later, by cheapest door spend, than the
  zone of their first key or part (`install_quest` records them on
  `bp.quest_locks`). Check: `D4`.
- **Light the play first.** Every door, buyable and quest station has a lamp
  within 192 units at least as bright as the filler lamps within 512; every
  training ring has a lamp within 256 of its centre; no point on the straight
  way from a room's doorways to its doors and buyables is more than 256 units
  from a lamp. Check: `D5`.
- **Clean fronts.** No floor-standing prop taller than 24 units stands in the
  96 units in front of a perk, box, power switch, wall buy, door or quest
  station (the `Z60` `clearance_front` box, `verify/prop_rules.front_box`).
  Check: `D6`.
- **Light the paths.** No stretch of a map's declared walk paths
  (`bp.walk_paths`, a maze's passages) longer than 320 units is over 256
  units from every lamp; `blueprint.autolamp.light_paths` lights them.
  Check: `D7`, a warning (a dark stretch of path
  reads as unlit).
- **Every roofed room lights its own floor.** An estimate from the emitted
  lamps on a 48-unit floor grid leaves no more than 60% of the floor under
  0.25 and a mean of at least 0.2 (calibrated on the cemetery recipe's
  rooms against a dark room's 100%/0.00); two joined rooms are no
  more than 3 stops apart; a dim room opening onto a sunlit one is named.
  Check: `D8`, a warning (`verify/lightlevel.py`).

### An item another item stands in front of

Rule: no interactive item may stop another one being used. Every perk
machine, the pack-a-punch, every mystery box, the power switch, every wall
buy and every door owns two volumes, and they are checked against each other
at placement time.

**Body** -- the item itself. Measured off the stock prefabs in
`_prefabs/zm/zm_core/`, by reading their own brushes:

| Item | Body | Read from |
|---|---|---|
| perk machine | 64 wide, 24 in front of the origin, 24 behind, 72 tall | the three `attack_spot` structs at x = -30, 0, +30, and `vending_revive_struct.map`'s `shadowcaster` at x -19.25..18.75, y 12..17 |
| pack-a-punch | 64 wide, 68 in front, 16 behind, 96 tall | its prefab's entities span x -66.6..14.7 along the axis it faces; the width is the perk machines' and is **unverified** |
| mystery box | 104 wide, 18 in front, 16 behind, 145 tall | `buyable_magic_box_start.map`'s clip brush, x -52..49, y -16..18, z -10..145 |
| power switch | 40 wide, 8 in front, 7 behind, 94 tall | `power_switch.map`'s clip brush x -20..20, y -8..7, z -1..94, with its own `trigger_use` off the -Y face at y -24..-5 |
| wall buy | 48 wide, 8 *into* the wall, nothing in front, 66 tall | the 13 `spawnable_weapon_*.map` mount brushes (the widest is `shotgun_pump`'s x -19..20 by y -8..-1 by z 0..56) and their chalk patches (the widest is `ar_standard`'s and `smg_versatile`'s x -22..24 by z 40..64) |
| door | the opening box | `add_door` |

**Apron** -- where a player stands to use it: the item's own width plus 32 a
side, 96 deep in front of a wall buy, a machine or the switch and 128 in
front of the mystery box and the pack-a-punch, a player's 72 units tall. A
door gets one on each face of its leaf.

A wall buy's mount and a door's leaf are part of the wall they are cut into,
so they are asked whether they are blocked and never whether they block: a
bought door is not in the world at all, and most wall buys are mounted
beside a doorway. Only a body that **stands in a room** --
machine, pack-a-punch, box, switch -- can be the thing in the way.

Apron against apron is deliberately allowed. Shared standing room is one spot
to stand in and two things to buy without moving, which is a well-laid corner
and not a fault.

Check: `Z42`, model level. An **error** is an item that cannot be used:

- two standing bodies drawn through each other;
- a standing body in the 24 units in front of a wall buy's chalk, at the
  chalk's own height (z 40 to 66 above the buy's origin);
- a standing body filling the 32 units of floor -- one player hull, and the
  navmesh generator's own corridor width is 31 (`N2`) -- directly in front of
  an item, across that item's own width.

A **warning** is crowding: a body inside the generous apron that still leaves
32 units to stand in. The split is measured rather than chosen. Refusing
anything that touched the full apron would have refused four more placements
that are all usable, such as a machine whose body starts 94 units in front of
a wall buy on the opposite wall, two units inside that buy's 96.

**The model refuses the error rather than reporting it.** `Blueprint._install`
raises `errors.InteractiveBlocked`, so a blocked item cannot be held by the
model at all; `Z42` is the backstop for a blueprint that arrived by another
road -- read back out of a map editor, or moved after it was placed. The
volumes, and every measurement above, are in `blueprint/reach.py`.

That it can report anything is not taken on trust. The defect this rule is
named after is a wall buy with a perk machine on the same wall facing the
same way 24 units in front of it: the buy cannot be pressed. Placing that
pair refuses the placement with both ids and the 48 x 24 x 26 unit overlap.

`Z9` and this rule are different questions. `Z9` asks whether a machine has
world brushwork and floor in front of it; `Z42` asks whether the thing in
front of it is another item the player also has to reach.

### Set dressing standing where set dressing cannot stand

Rule: every prop is somewhere a prop can be. Four things, and each of them is
a thing a player sees in the first minute:

- a model whose own measured box says it is **mounted** -- centred on its
  origin in Z, or wholly below it -- is not dealt onto a floor. That is what a
  wall clock, a sign, a picture frame and a notice board are authored like,
  because a fixture is positioned by where it meets the wall, and a chandelier
  is authored wholly below its hook. Put one on the floor and half of it is in
  the tile, or all of it is under it;
- two **solid** props do not share more than a quarter of the smaller one's
  footprint at the same height. Two boxes at different heights sharing floor
  is a shelf; two boxes at the same height sharing floor are drawn through
  each other;
- a prop **rests** on what is under it. Not two units over it, and not with
  half its footprint off the plinth, the counter or the block it stands on;
- no prop stands inside an **interactive item's own body**. The apron is
  `Z42`'s question and crowding is a warning there; this is the body itself,
  which is the machine and the prop occupying the same cubic units.

Check: `Z44`, model and file level, a **warning** on both. A densely
dressed map can have hundreds of these that the caller running the check did
not introduce, so an error would fail every build until the placer is
switched over. One word in `verify/model.py` (`LAYOUT_SEVERITY`) makes it an
error on the day it is.

What it catches, and what every other check in this document passes: wall
and ceiling fixtures in or under the floor tile, solid props drawn through
each other, props hanging 55 to 70 units over a slab because the terrain mesh
stops short of the wall, props hanging off the edge of what they stand on,
and props inside an interactive body, such as a bench through a perk machine
or a generator over the power switch.

Both sides ask the same question of the same rules. The model side reads the
blueprint before anything is written; the file side reads the props, the zone
manager's own player volumes, the floor brushes, the terrain patches and the
stock interactive prefabs back out of the `.map` text, which is what a map
edited in a map editor and written again has instead of a blueprint.

What it does not ask, because each of these needs evidence it is not given:
props poking into world brushwork, props on stairs and
landings, sight lines from a spawn to a door, and whether a model suits the
room's theme. The rules live in `src/zmforge/placement/audit.py` and are the
same relation objects the placer states its placements with, so the rule that
chooses a position and the rule that judges one cannot drift apart.

### A door that opens onto a zone nothing connects

Rule: a buyable door needs a priced trigger, a collision leaf, an explicit
`origin` at the trigger's centre, and a `script_flag` that appears in exactly
one `add_adjacent_zone` call. The trigger's `target` equals the door
brushmodel's and the door model's `targetname`.

Check: `Z7`, model and file level.

### Zombies path badly through a door that works

Rule: every part of a door -- the `script_brushmodel` collision leaf and the
`script_model` leaf both -- carries `DYNAMICPATH` set to `1`. The key is
declared in Radiant's own entity database, `bin\t7.def.json`, on
`script_brushmodel` and on `script_model`, and its default there is `false`.
Stock `zm_giant.map` sets it on its barricade clip, its pack-a-punch door clip
and its dog clips.

Without it the door compiles, links, is bought and opens, and the AI paths
through the opening are never rejoined when the leaf moves. Nothing in any log
says so. This package has always emitted the key; the check exists so that
cannot quietly stop being true.

Check: `Z30`, file level.

### A barricade window you can walk through

Rule: no barricade window uses `barricade_reciever_wood_hide_pieces.map`.
Diffed against the plain prefab on the install:
`barricade_reciever_wood.map` carries a full player `clip` over the whole
opening (`x -48..50` by `z 0..113`), and the hide-pieces file has no such
brush -- only the sill band (`x -39..35` by `z 0..35`). Nothing else in this
package plugs a barricade opening, so that variant leaves the 96 x 112 hole
`add_window` cut wide open and the player walks out into the yard.

Treyarch use the hide-pieces variant throughout `zm_giant` and clip their
openings by hand, which this package does not do. An error until it does.

Check: `Z32`, model level.

### An opening with nothing in it

Rule: an opening sealed with nothing but tool materials -- `clip`, `caulk` and
their kin -- is a warning. The compiler turns them into collision it draws
nothing on, which is the point when the fill is meant to be a view. It is also
exactly what a missing barricade, an unfilled pane, and a model the packer
silently dropped all look like from inside the room, so a player reporting "an
opening with nothing there" cannot tell the deliberate one from the broken one
and neither can we.

A warning, not an error: `seal_opening(material=CLIP)` is a supported and
useful thing to do. The warning's job is to make the count visible so the
deliberate ones are known.

Check: `Z31`, model level.

### The dog round never ends

Rule: `level.dog_rounds_allowed = 0` unless the map carries
`zombie_dog_spawner` entities and `dog_location` structs, and the assignment
comes before `zm_usermap::main()`. After the entry the framework's default has
already applied.

Statement order in `main()` is fixed beyond that. The zone hook is set after
the framework entry, `init_zones` entries come after the hook, and
`zm_zonemgr::manage_zones` starts after the array is filled.

Check: `Z10`, model and file level.

### The client drops your join

Rule: the client script's `main()` calls `zm_usermap::main()`. Without it the
server and client disagree about client fields and the join is dropped.

Check: `Z13`, file level.

### A script that calls something that does not exist

Rule: both emitted scripts parse, and every call resolves to a function the
file defines or to a stock symbol whose module the script `#using`s. A missing
semicolon or an unresolved call is fatal at run time in this game, and the GSC
compiler lives on Windows behind a linker that never exits zero.

Check: `Z15` for structure and `Z16` for references, both in the same process
that writes the text.

## Menus, loading screens and the manifest

### An asset type the linker will not pack

A usermap may not ship Lua. The manifest accepts the line, the linker reads
it, answers `ERROR: Lua not supported`, and then **writes a fastfile anyway**,
so nothing but the log says the build failed. Measured on Windows and
reproduced under Wine, where the failing and passing link
logs differ by that one line and nothing else. The tools ship no Lua of any
kind, no shipped zone mentions it, and there is no `share/raw/ui` tree, so
the community's advice to load an interface file from a map's client script
does not apply to a usermap.

Check: `Z47`, file level, an **error** per offending manifest line. It reads
the manifest only, so it costs nothing and runs everywhere the file checks
run.

<details><summary>Why this is an error and not a warning</summary>

The link still produces a fastfile of a plausible size, and the install step
that follows sees two files where it expects two files. A build that fails
this way looks exactly like a build that worked, so nothing short of this
check stops it from being installed and played.

</details>


### The map does not appear, or appears with no name

Rule: the manifest carries six lines the linker needs.

```
>class,zm_mod_level
>group,modtools
col_map,maps/zm/<map>.d3dbsp
gfx_map,maps/zm/<map>.d3dbsp
scriptparsetree,scripts/zm/<map>.gsc
scriptparsetree,scripts/zm/<map>.csc
```

Every other line has to be an asset prefix real zone files use. A typo there
is caught by nothing else. The linker acts on the lines it understands and the
map dies at run time reaching for the asset that never arrived.

Check: `Z14` for the six, `Z17` for the rest.

### A comma in the title throws the rest away

Rule: the `>title,` line is free text up to the first comma. The linker
rewrites the title into `zone_source/loc/<map>.zone`, and there a comma
truncates and every space is removed. Measured on Windows and confirmed in
game: `>title,Hall of Mirrors, Part Two` arrives as `>title,HallofMirrors`. Letters, digits and brackets survive.

The space stripping is not warned about, because it happens to every readable
title. A comma is different, because it silently throws text away.

Check: `P3`.

### The two presentation files, and which of their properties are rules

Rule: `loadingimage.png` and `previewimage.png`, dropped flat in
`usermaps\<map>\zone\`. Neither is a fastfile asset, so no build stage will
ever complain about one being absent or malformed. 38 of 40 published
Workshop maps sampled carry both names flat beside their fastfiles,
one carries the preview only, one carries neither.

Rule on the sizes, and it is only one rule. All 38 published
`loadingimage.png` files are 1920 by 1080, with no exception, so that size is
enforced. The 39 published `previewimage.png` files use **nine** sizes: 23 are
the mod tools' template 600 by 340 and 16 are not, spread over eight other
sizes ranging to 3126 by 2027,
and every one of those maps is published and playable. So the preview's size
is a house style and is not checked: 600 by 340 as a rule would object to
41% of the real corpus.

No rule on colour type. The mod tools' template is bit depth 8, colour type
2, no interlace, but published files include
32-bit ARGB for 17 of the 38 loading screens and 19 of the 39 previews, and
one 8-bit palette preview, so alpha and palette both reach a shipped map. Nothing checks it.

Check: `P1` and `P2` read the bytes and the header. `P1` warns on a size other
than 1920 by 1080; `P2` reports only a missing or unreadable file.

Known and unresolved: `previewimage.png` shows on the map-selection card and
`loadingimage.png` does not appear for a local map load, despite matching every
published map's format, size and location. The leading explanation is that the loose file is not how the full-screen image is read at
all. It overrides a stock image asset named `black`, which needs the asset
repointed at the map's PNG, the `image,black` row commented out of the
install's `zone_source\all\assetlist\core_gfx.csv`, and `image,black` added
to the map's own `.zone`. A three-run A/B under Wine confirms that override **builds**: with the row commented out the linker logs
`Converting image black` and packs the image, and with the row live the same
`.zone` line is silently ignored. What it does not confirm is that this is
what draws the screen, and 38 of the 40 published maps ship a loose
`loadingimage.png` anyway, which would be pointless if the file were inert.
Loading the packed test map in the game is what settles it. Detail, evidence
and the set-link-restore consequence: `mapsource-format-reference.md`
section 3.6.

Check for the symptom: none. `M1`. Load the map and look.

## The file format traps that stop the compiler with no useful message

These are the only requirements in this document that fail the build rather
than the playtest. They are here because two of them fail with an error
message that points at the wrong line.

### A patch layer line in the wrong place

Rule: a patch's `layer` line goes first inside the inner block, at column 0,
which is where Radiant writes it. Measured on 328 of 328 layered shipped
patches, out of 22,795 patch containers. Only `guid` may stand between the
container brace and the `mesh` or `curve` keyword. A `layer` line there is
parsed by `cod2map64` as a face brush and the compile stops with:

```
MatchToken: got 'mesh', expected '('
```

Check: `F9`.

### A stock collision file the compiler will not parse

Rule: every collmap the map asks `cod2map64` to bake is plain brushes. A bare
`physics_*` word where a face should start is a solid primitive from a newer
authoring tool than the compiler the mod tools ship, and the compile stops the
same way a misplaced patch `layer` line does:

```
ERROR: File .../share/raw/collmaps/p7_food_fruit_watermelon.map, line 23:
MatchToken: got 'physics_cylinder', expected '('
```

Measured: marking the watermelon solid puts `use_collmap "1"` on Treyarch's
own model, so the compiler opens Treyarch's own collision file for it and no
BSP is written. 28 of the 258 collmaps the mod tools ship carry a
`physics_cylinder`; all 28 are out of the trusted set in
`src/zmforge/props/stock_collmaps.json`, so a prop that needs one gets a
generated box instead, and `tests/test_props.py` fails if one comes back.

This check is the backstop for the file that is actually staged: the trusted
set is a recorded list, a deploy can put any file at that filename, and finding
out from `cod2map64` costs a whole build.

Check: `Z45`, file level, an **error** per offending line, over the collmap of
every `misc_model` in the map that sets `use_collmap "1"`. A collmap that is
not there at all is `Z21`'s finding and `Z27`'s, not this one.

### Exponent notation in any number

Rule: every number in a `.map` is plain decimal. Never exponent notation. Any
value whose formatted form is `-0` or empty becomes `0`, which collapses the
floating-point noise a wall generated on a zero coordinate produces.

What the compiler actually does with an exponent is unverified. No shipped map
contains one, and the cost of finding out is a broken build with no diagnostic.
`%g` formatting is banned for a measured reason: it writes `1e-05` and rounds
to six significant digits, turning `65536.25` into `65536.2`.

Check: `F7`.

### The rest of the text format

- `F1`: line 1 is `iwmap 4` and line 2 is the starting-number line.
- `F2`: only layer declarations sit between the header and entity 0.
- `F3`: entities and brushes are numbered consecutively.
- `F4`: entity 0 is the worldspawn.
- `F5`: every entity and brush has a unique, well-formed guid.
- `F6`: every key and value line is two quoted strings.
- `F8`: every face line has three points, a material and two sets of six numbers.

## What the build logs say while the build succeeds

The compiler exits 0 on a leak and 0 with missing materials. The linker never
exits 0 at all, on success or failure. So a stage's log is the only honest
account of what happened.

- `leak`: the compiler's leak banner. The map is not sealed. Load the named leakfile in Radiant to find the seam.
- `stage_error`: an `ERROR:` line in any stage's log.
- `stage_failed`: a stage judged failed on evidence rather than on its exit code.
- `missing_material`, `missing_material_benign`, `umbra_unset`, `caulk_terrain`, `preview_lighting`: covered in their sections above.

These eight only run when build logs are supplied. A static run reports them
as `SKIP`.

## Impossible, not unimplemented

Two things look impossible and are not, and they follow, so nobody gives up on
them early.

### Purchase prompt text *can* be customised

A wall buy's weapon name and a mystery box's prompt can be replaced with the
map's own text. Spec 5.7 carries the measurement and the method. In short:

- a usermap links its own localised strings. `localize,<name>` in the map's
  main zone, against a hand-written
  `share\raw\english\localizedstrings\<name>.str`, links with no
  `ERROR:` line, and the linker's own `.deps` names the file it read
  **[measured on a probe map]**;
- the asset name is `<STR FILE>_<REFERENCE>` uppercased, always prefixed
  **[measured, four references in one link]**;
- the wall buy reads its hint back off a struct the map can write:
  `get_weapon_hint` returns `level.zombie_weapons[weapon].hint`
  (`_zm_weapons.gsc:1417-1422`), and both prompt-building sites call it
  (`:969`, `:1305`). `add_zombie_weapon` force-assigning that field
  (`:559-566`) sets a default, not a constant -- reading the write and not
  the read is the mistake that produced the old conclusion.

There is also a stock hook for it, `level.func_override_wallbuy_prompt`
(`_zm_weapons.gsc:1194-1200`): the trigger calls it with the player, it may
set the hint text, and a false return blocks the buy.

Check: `Z24` no longer flags a `localize,` manifest line. It still warns on a
non-empty `sethintstring` **literal**, for a narrower reason: released maps do
pass literals (see spec 5.7 for the quoted examples), but the localised route
is the one that has been measured, and whether `&&1` substitutes inside a literal is
unresolved.

### The loading screen is loose image files

Covered above under `P1` and `P2`. Repeated here because it is the second
thing people expect to be an asset pipeline and it is not. Two PNGs dropped in
the zone folder, and no build stage reads either.

## Custom sound from the command line

**Custom sound can be built from the command line.** It looks as though the
linker loads an already-compiled `<bank>.all.alias.sz`, that nothing in `bin`
produces a `.sz`, and that only the GUI asset editor can, but that rests on
one failed link and one file extension.

Measured on Treyarch's own shipped bank
`pc\raw\sound\zone\mp_sector.all.alias.sz`:

```
$ file mp_sector.all.alias.sz
mp_sector.all.alias.sz: CSV text
$ head -1 mp_sector.all.alias.sz | awk -F, '{print NF}'
102
$ wc -l mp_sector.all.alias.sz
647 mp_sector.all.alias.sz
```

A `.sz` is a comma-separated spreadsheet with a 102-column header, saved
under an extension that reads like a compiled format. Nothing compiles it.
Writing the file **is** building the bank, and the asset editor is not
needed for it.

The failed link that started the wrong belief was real, and it was one of
the three rules below being broken rather than the format being closed.

### The four rules, each measured, each silent when broken

**The bank is named after the map.** `sound,<bank>` in the manifest is the
name the linker opens `<bank>.all.alias.sz` under. Any other name gives

```
ERROR: unable to load file 'sound/zone//<bank>.all.alias.sz'
ERROR: sound aliases failed to load
```

**The bank is read from the shared raw tree**, `share\raw\sound\zone\`, not
from the per-platform `pc\raw\sound\zone\` where Treyarch's own `mp_sector`
bank sits. A bank in `pc\raw` links exactly as though it were not there.

**A bank holds at most 104,729 rows**, about 160 times what a real map uses.
It is a ceiling a person never reaches and a generator can.

**Every required column carries a value.** Fifty-three of the 102. Treyarch's
own example row in `user_aliases.csv` leaves nearly all of them blank, which
reads like "the template in the `Template` column fills these in", and the
linker does not do that: template inheritance is the asset editor's
behaviour. A bank of rows shaped like that example produced 108 `ERROR:`
lines, two per column:

```
ERROR: sound/zone//zm_test.all.alias.sz row 1 had empty required column Storage
ERROR: Sound alias file sound/zone//zm_test.all.alias.sz: Unknown Storage ''
```

The linker reports them in waves, so a build that fixes fifty columns finds
three more. The list is `zmforge.emit.sound._REQUIRED_DEFAULTS`.

### The files that sit beside the bank

The English companion `<bank>.english.alias.sz` is opened alongside the `all`
bank. A map whose sound is not voice-over ships it as a header and no rows,
and that links clean.

Two more are load-bearing and have nothing to do with the map's sound. With
the alias bank and nothing else the link stops with:

```
ERROR: unable to load file 'sound/zone//zm_test.all.ducklist.sz'
ERROR: ducklist failed to load - sound/zone//zm_test.all.ducklist.sz
ERROR: unable to load file 'sound/zone//zm_test.all.reverb.sz'
ERROR: reverb failed to load for zone zm_test
```

`<map>.all.ducklist.sz` is a `Name` header and no rows. `<map>.all.reverb.sz`
is the install's own `share\raw\sound\reverb\common_reverb.csv` passed
through. `ambient`, `musiclist` and `scriptid` are written header-only
because every shipped bank has them; the link never asked for them. Passing
`ambients\ambient_mod.csv`'s row through as the ambient table instead fails
with `Unknown defaultRoom 'yes'`, so that file is the asset editor's input
and not a zone table.

### What a map does with that

`zmforge.emit.sound` writes the bank, `zmforge.audio` synthesises tones to
put in it, and `Blueprint.add_custom_sound` ties the three files together:
the wave file under `sound_assets\<map>\`, the row in
`share\raw\sound\zone\<map>.all.alias.sz`, and `sound,<map>` in the manifest.
The 102 column names are read from the install's own
`share\raw\sound\aliases\user_aliases.csv` rather than carried in this
repository, the same policy the weapon table follows.

A row's `FileSpec` is relative to the tools' `sound_assets` folder. Treyarch's
own rows carry both spellings side by side, `FileSpec
amb\electronics\wall_servo\wall_servo_a_00_01.wav` next to `FileSource
Q:\t7\pc\game\sound_assets\amb\...`, and an empty cell inherits from the
template named in the `Template` column, which is how the one example row in
`user_aliases.csv` is written.

Proved by building a one-room probe map carrying one synthesised 4.5 kHz
ring: compile and link run under Wine, and the
packed asset list carries the bank. What is **not** proved is that it is
audible in a play session. Nobody has heard it.

### What the game says: it refuses a bank built this way

The first full map to carry a bank written as above crashed the game at
load. Windows logged an access violation with no module and offset 0, and a
minidump of the still-open process held the game's own message:

```
Com_ERROR: ERROR: sound bank - name: zm_mymap.en, zone: zm_mymap, game lang: english, sound lang: en failed to load
```

raised while reading `usermaps/zm_mymap/zone//en_zm_mymap.ff`.
So "the linker accepts the tables" and "the game loads the bank" are two
different facts, and only the first is true. Two measurements bound the cause:

- The linker never reads the wave. Its `.deps` for both fastfiles names the
  seven `.sz` tables and nothing under `sound_assets`, so the bank it packs
  has aliases and no audio. The `.sz` header carries `RowSourceFileName`,
  `RowSourceShortName` and `RowSourceLineNumber`, which are the marks of a
  tool that read alias CSVs and wrote these tables; we wrote the tables and
  skipped that tool.
- `linker_modtools.exe` does not run that tool. Treyarch's own sound doc
  describes `usermaps\<map>\sound\zoneconfig\<map>.szc` naming alias CSVs
  under `share\raw\sound\aliases`. Linking `zm_test` with such a `.szc`
  and the hand-written tables moved away fails exactly as with no sound at
  all: `unable to load file 'sound/zone//zm_test.all.alias.sz'`. Nothing
  in `bin` carries the strings `zoneconfig` or `.szc`, so the step lives in
  the launcher or the asset editor, and neither runs headless.

Which of the two the game objects to (a header-only English table, or a bank
with no audio behind it) is not separable without a play session. Until a
bank is proven to load, the shipped recipes ship none by default
(`custom_sound=False`; `generate --custom-sound` turns it back on for a test
build).

Check: `Z24` now errors on a bank named after anything but the map, on a
declared bank that is not in the shared raw tree (naming the per-platform
copy when that is where it is), on a bank over the row ceiling, and on a row
whose wave file is not on disk.

Check, after the link: `Z24` also fails the link verdict when the link's own
reports say a sound bank was packed for the map (`sound` above zero in
`<map>_poolinfo.csv`, or `sound,<map>` in `assetlist/<map>.csv`) and the
`.deps` beside them names no audio file at all, because that is exactly the
bank the game refused above (`zmforge.verify.check_linked_sound_audio`, run
by the link stage).

## Where the community disagrees with our own measurements

Ten years of forum and wiki practice agree with this document on zones doubling as the playable area,
on dog rounds, on the riser name chain and on the client entry. Four places it
does not, or where it asks for more than this table does.

**Zone activation may kill you on entry.** The UGX wiki says an inactive zone
may still kill a player who enters it. Its own author hedges ("I believe").
Our `Z3` requires every zone to be reachable through the flag graph, which
makes the question moot for a generated map. Treat the wiki claim as
unverified.

**More than four players. Settled, and the community was substantially
right.** Eight-player support needs more than extra spawn structs on the map
side. The AviaCreations wiki says any lobby above four needs edits to
`_zm.gsc`, `_zm_laststand.gsc`, `zclassic.gsc` and localized name strings.
Reading the stock scripts: `_zm.gsc:7067 player_too_many_players_check`
takes `max_players = 4` outside `zgrief`/`zmeat`, freezes the players above
that and notifies `end_game`, and `_zm.gsc:1865` threads it on every player
spawn, so on stock scripts the fifth player to join ends the match. Extra spawn
structs alone seat nobody. One of the wiki's four edits is inside a map's
reach, and `Z26` now requires it: `level.player_too_many_players_check` is
assigned at `_zm.gsc:252` inside `zm::init()`, which the framework entry
reaches synchronously (`zm_usermap::main()` -> `load::main()`, `_load.gsc:79`),
so a map setting it `false` after `zm_usermap::main()` lands between the write
and the read. A map with more than four `initial_spawn` structs now emits that
statement, and `Z26` fails it if it does not. The rest of the wiki's list is
core game scripts a usermap does not ship -- `_zm_laststand.gsc:53-56`
registers `laststand_update0..3` in a `for( i = 0; i < 4; i++ )` loop and
`:91-95` names four `level.player_name_directive` strings -- and only a mod
can change them, so a generated map is ready for eight players and does not
seat eight on its own. None of this was played; it is a reading of the raw
scripts under `share/raw/scripts/zm`.

**The `always_on` flag in `connect_zones`.** The community zone contract says
not to do what `emit/scripts.py` does, which is emit
`level flag::init( "always_on" )` and `level flag::set( "always_on" )`. Neither
position has been playtested against the other. Unresolved.

**Per-zone spawners.** The community treats one spawner per zone as a hard
requirement. `Z5` enforces at least one spawner map-wide and `Z4` warns rather
than errors on a zone with no spawn struct. The community is stricter and no
measurement here contradicts it.

Two things the community requires that nothing here checks at all:

- A `#using` line for a script pack belongs in both the `.gsc` and the `.csc`. One alone fails the join with a client field mismatch. `emit/scripts.py` builds the two sets from separate lists and no check compares them.
- An effect needs a precache line in the client script. No precache line is emitted in either script.

The community also reports compiler and linker ceilings on triangle, brush,
winding and collision counts, with error strings. Nothing in `verify/` or
`solids/inspect.py` holds a map-wide bound. The only ceiling here is a per-prop
1500-triangle limit enforced by decimation at asset-build time.

## What still has no automated check

Eight things, in the order they are likely to bite.

1. Whether the loading screen appears. `M1`. Unresolved cause.
2. Whether the baked map looks right. `M2`. Whether the bake *ran* is not the open question: it runs in the chain and the stage log says so. Whether a Wine bake lights the map the way a Windows bake does is unverified -- the two `.led` files are not the same size.
3. Whether a prop's collision was built and packed. `M3`. The evidence is in the link log. Whether the prop's **model** was packed at all is not in the link log and is not a warning: a link that drops a model prints nothing and returns 0. `scripts/props-packed.py` reads the linker's own `<map>_xmodel.csv` instead.
4. The playtest list itself. `M5`. Map loads and the player spawns on the floor of the starting room. Zombies rise and come through the windows in round 1. The first door opens and the next zone's risers pursue. Perks, box, pack-a-punch and switch respond. Round 7 does not hang. No script error on the console.
5. A scattered prop buried in a world brush. The burial check covers spawns, machines and lamps, not props. The prop recipe carries its own guard instead: `recipes/props.furnish` stands every model on `Blueprint.ground_under` and then tests its origin against the world solids, dropping anything still inside one, and the recipe refuses to build when more than a quarter of a scene is dropped. A dressing pass has put 570 of 2,811 models inside a solid while every other check passed.
6. Server and client `#using` sets agreeing.
7. Effect precache lines.
8. Map-wide compiler ceilings.

One more is checked but unsettled rather than unguarded. `Z23` warns where
this repo knows the rotation sense is wrong and does not know the correction.

`Z22` resolves the `bowie` slug through its prefab, which names
`bowie_knife`, a weapon this level has. No shipped recipe raises a `Z22`
finding.

## Layout rules

Five warnings that apply to every map. They live in `src/zmforge/verify/layout_rules.py`.

- `shadows_dropped` (build log): the bake dropped an omni light's shadow. Shadowless lamps count too.
- `Z74`: no stamped copies. Two vignettes from one template, or two rooms of one size, may share at most 60% of their (model, relative position) pairs. No litter model may appear more than 40 times.
- `Z75`: no walk-through floor prop over 60 tall and over 40 wide stands in play.
- `Z76`: no barricade riser feeds a zone under 0.05 k2 of floor or narrower than 64 units.
- `Z77`: no whole wall side in a material that renders as a black void.

<details><summary>What was tightened on existing rows, and the evidence</summary>

- `Z48` is an error for a perk, the box, the power switch and a wall buy that scenery closes in. The placer now keeps a 96-unit approach lane in front of each clear of any floor prop over 24 tall (`blueprint/lanes.py`).
- `D5` is an error for an unlit perk or power switch. `Blueprint.light_rooms` now gives every door and buyable with no lamp within 192 units a shadowless play lamp in the map's lamp style (`blueprint/autolamp.py`).
- `Z46` is an error for a zombie-proof top under 64 units over the floor of a playable room, unless the element is declared `reachable=False`.
- `L2` warns when a lamp of radius 150 or less carries a light LOD pair over 25. The emitter writes no pair at all, so both keys default to 0 and the lamp is never culled: `200 / 300` on every lamp blacks out narrow corridors, and in `zm_giant` the small lamps carry 5/25, not 200/300.
- `shadows_dropped` reads the bake log because no pre-bake rule fits the evidence: `zm_corn_maze` dropped 26 lamps reached by 9 to 19 omni spheres (all written `PRIMARY_NOSHADOWMAP 1`), while `zm_dmv`, with up to 20, dropped none.
- `ar_cqb` is banned as a wall buy: its prefab's chalk `t7_zm_chalk_buy_hvk30` is missing on the install, so `wall_weapon_prefab` raises.

</details>

