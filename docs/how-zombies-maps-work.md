# How Black Ops 3 zombies maps work

This is the mechanism document. It explains what a zombies map is to the
engine, what each build stage does to it, and what the stock scripts do with it
at run time. The design guidance and the failure modes follow from that, in
that order, so a reader can reason about a defect not yet seen.

Our other documents are organised around this project's generator and around
symptoms we hit. This one is organised around how the thing works. Where the
two views disagree, the disagreement is stated here rather than smoothed over.

## The six mechanisms that explain most of it

If you read one screen, read these. Each is expanded below.

- **A zombies map is data for a framework, not a program.** Treyarch's scripts
  run the game. A map places entities the scripts look for by key, and sets a
  handful of level variables in one narrow window. Almost nothing else.
- **Zones do two jobs at once.** A zone decides where zombies may spawn, and a
  zone volume decides where a player is allowed to stand. A player in no
  enabled zone volume is killed outright every 3 seconds.
- **Zombies and players move by different rules and different numbers.** The
  player's limits come from dvars in the stock scripts. The walkers' limits
  come from a settings file the navmesh generator reads at compile time, and
  they are stricter.
- **The build chain reports success it did not achieve.** The compiler exits 0
  on an unsealed map. The linker's exit code carries no information at all.
  Judge every stage on its log and on what landed on disk.
- **Brightness is a logarithm with no absolute meaning.** A lamp's value is
  read against the map's own sky exposure. The same number is correct on one
  map and 2000 times too dark on another.
- **Several registries have to agree, and disagreement is silent.** An asset
  can exist, be packed, and still be unreachable because one of the asset
  database, the zone manifest, and the script precache did not name it.

## How to read the evidence labels

Every claim below carries one. We have been wrong before by stating inference
as fact, so the label is part of the claim.

| Label | Means |
|---|---|
| `[measured]` | Observed on a mod tools install, in a Windows or Wine build, or in a play session. The file is given. |
| `[stock script]` | Read out of Treyarch's shipped `.gsc` or `.csc`. File and line given. Reading a script is not playing a map. |
| `[Treyarch doc]` | From a document Treyarch ships in `docs_modtools\`, or published on Steam, or wrote on its own wiki. The document is named. |
| `[community]` | A forum post or a community wiki reports it. Nothing here has confirmed it. |
| `[unverified]` | No primary evidence either way. |
| `[unknown]` | We tried to find out and could not. |

The generator specification uses a seventh tag, `[inherited]`, for playtest
reports from the authors whose work this project started from. Those are
second-hand reports, so they read here as `[community]`.

Two script trees are cited. `share/raw/scripts/` is Treyarch's own source,
shipped with the mod tools. `github.com/ate47/bo3-source` is a community decompilation of
the shipped game scripts, used only where the raw tree does not carry the
function. Line numbers can drift between tools versions, so the function name
is always given as well.

## Why so little of this is labelled `[Treyarch doc]`

Worth knowing before the labels start looking lopsided.

**Treyarch published no zombies map-making documentation at all** `[measured]`.
What ships in `docs_modtools\` is 22 PDFs plus a script API reference, and all
of it is about the engine and the editor: lighting, materials, scale, the GSC
language, navmesh settings. None of it mentions zones, rounds, perks, the box
or Pack-a-Punch.

Everything zombies-specific in circulation comes from a community wiki written
between 2016 and 2018, which is dead and survives only in the Internet Archive
`[measured]`. Its own formats section was never written: the page exists and
says it is a work in progress `[Treyarch doc]`. The pages it did publish
document **prefabs, not systems**: download this pack, place it, add these
lines. The underlying entity and script contracts show through only where a
page happened to include the script.

That is why so much of this document is `[stock script]`. Reading Treyarch's
shipped scripts is the only way to learn most of it.

---

# Part 1: what a map is to the engine

## A map is five kinds of file, not one

None of them is optional, and three of them are pure text.

| File | What it holds | Who reads it |
|---|---|---|
| `<map>.map` | Brushes, patches and entities, as text. First line is `iwmap 4`. | `cod2map64` |
| `<map>.gsc` | The map's server script. | The GSC compiler inside the linker |
| `<map>.csc` | The map's client script. | The same |
| `<map>.zone` | The manifest: one line per asset to pack, plus directives. | `linker_modtools` |
| `*.gdt` | Asset definitions (materials, images, models, weapons). | `gdtdb.exe`, then the linker |

Two more files sit beside the built map and are not assets at all:
`loadingimage.png` and `previewimage.png`. Nothing in the build chain reads
them `[measured]`.

The `.map` format is text with no schema published by anyone. Treyarch's own
wiki has a formats section that never got written `[Treyarch doc: Phabricator
black_ops_3/formats]`. Our `mapsource-format-reference.md` is the only
account of it we know of, and it is evidence-first for that reason.

One format fact is worth carrying here because it is counter-intuitive and
because we measured it. A brush face is three points, and the normal
`(B - A) x (C - A)` points **into** the solid `[measured]`. That is the
opposite of the Quake and Quake 3 convention the format otherwise resembles.
The test was to parse the first 25 plain brushes of a shipped map and
brute-force the plane intersections under both conventions: inward gives 25
non-empty solids out of 25, outward gives 0 `[measured]`.

## What each build stage actually does

Five stages, and only one of them has a trustworthy exit code.

**1. Asset database update, `gdtdb.exe /update`.** Reads the `.gdt` files and
writes `gdt.db`, the index the linker resolves asset names against. Exit 0
means success `[measured]`.

**2. Compile, `cod2map64.exe -platform pc -navmesh -navvolume`.** Reads the
`.map` and writes three things:

- `<map>.d3dbsp`, the geometry and static collision.
- `<map>_navmesh.hkt`, the surface the walkers path on.
- `<map>_navvolume.hkt`, for flying enemies, when a `nav_volume` brush exists.

The compiler prints a `Writing <path>` line for all three and then writes only
what it made `[measured]`. A map with no `nav_volume` brush gets a
warning line and no navvolume file, which is correct and not a failure.

**3. Lighting bake, `radiant_modtools.exe -ledSilent`.** Produces `<map>.led`,
the baked lighting the linker folds in. It is a GUI program. What it actually
needs is an X connection and a GPU, not a person at a keyboard `[measured]`.
Run without an interactive desktop, it reaches about 840 MB of working set,
burns 0.2 CPU-seconds in four minutes, prints nothing and never exits
`[measured]`. Under Wine on Linux with a real X server on a GPU it
finishes a small map in 17 seconds `[measured]`. Software
rendering is not enough: the probe pass never finishes under llvmpipe
`[measured]`.

**4. Link, `linker_modtools.exe -language english -modsource`.** Reads the
manifest and packs `<map>.ff`, `en_<map>.ff` and a `.xpak` into
`usermaps\<map>\zone\` under the tools root.

**5. Deploy.** The game reads `usermaps` under its own install, which is a
different Steam app in a different folder. A junction from one to the other is
how a built map becomes visible `[measured]`.

Four host constraints sit outside the stages and each costs a build if missed.

- Every tool runs with its working directory set to the tools' `bin`, with
  `TA_GAME_PATH`, `TA_TOOLS_PATH` and `TA_LOCAL_ASSET_CACHE` set, each with a
  trailing backslash. Without the working directory, navmesh generation fails
  with a message about being unable to load its generation settings
  `[community]`.
- The game and the mod tools must be in the same Steam library folder
  `[Treyarch doc: Steam guide 770558798]`.
- **The Windows decimal symbol has to be a period.** A comma breaks the tools
  `[Treyarch doc: same]`. That is a locale setting, and it produces failures
  that look like nothing else.
- A long stage should run detached and write a marker file when it ends, so
  nothing waits on the shell that started it `[measured]`.

A built map is coupled to the retail game's fastfile format. Game patch 1.27
broke every existing mod's fastfiles, a third-party tool repaired them in
place, and patch 1.28 fixed the format `[Treyarch doc: Phabricator zone_fix]`.
The tools never left beta and the published changelog stops at 2016-10-06
`[measured]`. Which tools version the measurements in this document were taken
on remains `[unknown]`.

## Which stages fail silently, and how to tell

This is the part that costs the most time, so it gets a table.

| Stage | Honest about failure | What it lies about |
|---|---|---|
| `gdtdb` | Yes | Nothing found |
| `cod2map64` | Partly | Exits 0 on a leak. Exits 0 with missing materials. Announces files it did not write. |
| Lighting bake | No | Hangs forever with no display, printing nothing |
| Linker | No, in both directions | Successful links have returned 0, 208, 2000, 5000 and 154000. A failed one returned 2002000 `[measured]` |

The verdict rules that survive contact with this, all `[measured]`:

- **A compile succeeded** when there is no leak banner, no `WROTE BSP
  LEAKFILE`, no `ERROR:` line, and the BSP is on disk.
- **A link succeeded** when no line matches `ERROR:` after colour codes are
  stripped **and** both fastfiles exist above zero bytes. Both halves are
  needed: a failed sound-bank link printed four error lines and still wrote
  both fastfiles.
- **A bake ran** when Radiant's own log carries `LED Exported for <map>.map`
  and `Export Done`.
- **A stage Wine killed** is not an `ERROR:` line. A link aborted by the Wine
  loader before printing anything, with the previous build's fastfiles still on
  disk, reads as success to every other rule `[measured]`.

Two asymmetries in the compiler and linker are worth memorising, because they
push in opposite directions.

- **A missing model is loud at compile and silent at link.** `cod2map64`
  stops on a `misc_model` whose binary it cannot find, prints
  `Missing xmodel '<name>'` plus one precache error per instance, and writes no
  BSP `[measured]`. The linker prints nothing about a model it drops, returns
  its usual meaningless code, and writes plausible fastfiles. One measured link
  packed 68 models out of a map placing 2,171 `misc_model` entities over 129
  distinct models, with no error line `[measured]`. The linker's
  own `<map>_xmodel.csv` under `zone_source/all/assetinfo/` is the membership
  list. Read that, never the log.
- **A missing image is loud at link.** `ERROR: image '<name>' is missing` plus
  the path `[measured]`. Images and models are not treated alike.

## What the game loads

The fastfile plus the `.xpak`. The manifest decides the contents, and six
lines are the minimum the linker needs `[measured]`:

```
>class,zm_mod_level
>group,modtools
col_map,maps/zm/<map>.d3dbsp
gfx_map,maps/zm/<map>.d3dbsp
scriptparsetree,scripts/zm/<map>.gsc
scriptparsetree,scripts/zm/<map>.csc
```

Every other line has to start with an asset prefix the linker recognises. A
typo in a prefix is caught by nothing: the linker acts on the lines it
understands and ignores the rest, and the map dies at run time reaching for an
asset that never arrived `[measured]`.

The `>title,` line is the name in the menu. It is free text up to the first
comma, and the linker rewrites it into a generated `.zone` under `loc/`, where
a comma truncates and every space is removed `[measured on Windows,
confirmed in game]`. A title of `Hall of Mirrors, Part Two` arrives as
`HallofMirrors`. Letters, digits and brackets survive.

The semantics of the `>` prefix itself are inferred from usage. No Treyarch
document explains it `[unverified]`.

---

# Part 2: rounds, spawning and where zombies come from

## The round loop, from the top

The framework owns all of it. A map supplies places and entities, nothing else.

`round_think` drives the game. Each round it threads `round_spawning`, which
does four things in order `[stock script: _zm.gsc:3678]`:

1. Refuses to run if the active spawn-location list is empty, with the assert
   message about no active spawners.
2. Recomputes zombie health for the round.
3. Sets `level.zombie_total`, the number left to spawn.
4. Loops: pick a location, pick a spawner, spawn one zombie, wait, repeat.

The round ends when the total has been spawned and the last zombie is dead.
`level.zombie_total` is decremented only by the round spawner, and the
end-of-round wait tests both the live count and the remaining total `[stock
script: _zm.gsc:3811, :4733]`. Nothing times out. This is why a map defect
produces a hang rather than an error.

One consequence for a map that spawns its own zombies from script: they are
extra, not instead. They do not consume the round's budget, they still have to
be killed before the round ends, and they count against the live cap the round
spawner waits on `[stock script]`.

## The numbers the framework uses

All read on the mod tools install `[stock script: _zm.gsc:1205-1225, :337-343]`.

| Variable | Value | What it does |
|---|---|---|
| `zombie_health_start` | 150 | Round 1 health |
| `zombie_health_increase` | 100 | Added each round, cumulative, to round 10 |
| `zombie_health_increase_multiplier` | 0.1 | After round 10 health is multiplied instead |
| `zombie_max_ai` | 24 | Base count for the round formula |
| `zombie_ai_per_player` | 6 | Added per extra player, scaled by round |
| `zombie_ai_limit` | 24 | Live zombies allowed at once |
| `zombie_actor_limit` | 31 | Live actors, including corpses awaiting cleanup |
| `zombie_spawn_delay` | 2.0 | Seconds between spawns, decayed per round |
| `zombie_between_round_time` | 10 | Pause after a round ends |
| `below_world_check` | -1000 | A zombie below this z is treated as fallen out |

The per-round count is `get_zombie_count_for_round` `[stock script:
_zm.gsc:3842]`. Multiplier is round divided by 5, floored at 1. From round
10 the multiplier is further multiplied by round times 0.15. Solo gets half a
player's worth of extras, everyone else gets one per player past the first.

Spawn delay is per player count and decays by 0.95 per round to a floor
`[stock script: _zm.gsc:4598]`. Base delay is 2.0 solo, 1.5 for two, 0.89 for
three, 0.67 for four.

These matter to a designer for one reason. The live cap is 24. A map with one
long corridor and one spawn location will feed zombies to a player in single
file at 24 at a time no matter how big the round count is, and a map with
spread-out locations will not. The cap is on bodies alive, not on bodies per
place.

## What a map has to supply

Three separate things, and they are linked by string, not by position.

**A spawner entity.** At least one spawner actor carrying
the key `script_noteworthy` with value `zombie_spawner`. The install ships two
zombie `aitype`s and the classname has to name one of them:
`actor_spawner_zm_usermap_zombie`, which
`share/zone_source/zm_levelcommon.zone:51` declares for a usermap, or the older
`actor_spawner_zm_factory_zombie` that the mod tools' level template ships,
whose animation mapping table names no jump, mantle, climb or
`traverse_procedural` move `[measured]`. The framework's lookup
is `GetEntArray( "zombie_spawner", "script_noteworthy" )` `[stock script:
_zm_spawner.gsc:47]`. The classname is not what is looked up. One entity
serves the whole map, because the spawner is drawn at random from that
map-wide array while the position is drawn separately from the active zone set
`[stock script: _zm.gsc:3799]`.

**Spawn location structs.** `script_struct` entities carrying, in
`script_noteworthy`, one of `riser_location`, `spawn_location`,
`faller_location` or `custom_spawner_entry` `[stock script:
_zm_zonemgr.gsc:363]`. These are the places zombies appear. Their
`targetname` must equal the zone volume's `target` value. Sitting inside the
volume is not a link.

**A `script_string` of `find_flesh`** on a riser. Without it the zombie
appears and does not move `[measured]`. Radiant's own entity definition
carries this as the default for a riser location `[Treyarch doc:
bin\t7.def.json]`.

## The four ways spawning dies quietly

Each of these compiles, links, loads, and produces a round that never starts or
never ends.

- **No struct in the zone the player is in.** Both round loops spin in place
  on an empty location array, waiting a tenth of a second and testing again
  `[stock script: _zm.gsc:3756, :4416]`. They wait, they do not time out.
- **A struct whose `targetname` does not match its zone volume's `target`.**
  The zone collects nothing and behaves as the case above.
- **A riser above the floor.** Heights of 32 and 40 units above the floor
  surface produced floating, stuck zombies `[measured]`. The origin belongs on
  the surface.
- **A riser with no walkable navmesh within a zombie's width.** The zombie
  rises and has nowhere to walk to. Covered under navigation below.

## Player spawning is a separate system, and `info_player_start` is not part of it

On the zombies path the game never reads `info_player_start` `[measured]`.
Emitting one is harmless and relying on one gives a map with no valid spawns.

The player spawn set is `script_struct` entities in two shapes.

- One struct with `targetname player_respawn_point`. Its bounds become the
  level's spawn bounds. Its `script_int` on **this** struct is an ideal
  distance to another player, not a team side `[measured]`.
- One struct per slot with `script_noteworthy initial_spawn` and `targetname
  initial_spawn_points`, at least 32 units apart, standing on floor.

Every one of them has to carry the gametype match string among the
space-separated tokens of its `script_string`. The framework builds that string
by joining the gametype and `level.default_start_location` with a `_`,
so the usual value is `zclassic_start_room` `[measured]`. A struct that does
not hold the result is skipped.

Two ways to empty the set by accident, both silent:

- **Putting a `script_int` on an initial-spawn struct.** On that struct the
  value is a team side. `getfreespawnpoint` randomises `side_selection` to 1 or
  2 once per game and then deletes every candidate whose `script_int` matches
  the losing side `[stock script, decompile: _zm.gsc:732-810]`. Numbering four slots 1
  to 4 therefore loses one every game, and which one depends on a coin flip.
  Treyarch's own `zm_giant.map` carries four such structs and no `script_int`
  at all `[measured]`.
- **Assigning `level.default_start_location` yourself.** The framework already
  sets it to `start_room`. Setting it to a zone name makes the match string
  something no struct carries `[measured]`.

After the side filter, the struct is chosen by matching `en_num` to the
player's number, falling back to the first struct `[stock script, decompile:
_zm.gsc:813-828]`. So a fifth player does not get a fifth struct, it stacks
on the first.

## Above four players the stock scripts end the match

Two caps, at two layers.

- The config layer sets `com_maxclients 4` and `party_maxplayers 4` in
  `gamedata/configs/zm/zm_default_gamesettings.cfg`. Not map data `[measured]`.
- The script layer is `player_too_many_players_check`, which takes
  `max_players = 4` outside the grief and meat gametypes, freezes the players
  above that number and notifies `end_game` `[stock script: _zm.gsc:7067]`.
  It is threaded on every player spawn `[stock script: _zm.gsc:1865]`. So on
  stock scripts the fifth player to spawn ends the match.

A map can neutralise the second one and only the second one.
`level.player_too_many_players_check` is assigned true inside `zm::init()`,
which the framework entry reaches synchronously `[stock script:
_zm.gsc:252, via _load.gsc:79]`. A map setting it false **after**
`zm_usermap::main()` lands between the write and the read.

The rest of what a larger lobby needs is core game script a usermap does not
ship: a four-iteration clientfield loop in `_zm_laststand.gsc`, four name
directive strings, and per-player clientfield registration `[stock script]`.
So a map can be *ready* for eight players. It cannot *seat* eight on its own.
None of this has been played.

Extra spawn structs are not the whole map side. The community wiki that says
so is substantially right.

## Dog rounds are on until a map turns them off

`level.dog_rounds_allowed` has to be assigned before the framework entry,
because the framework applies its default only while the variable is undefined
`[measured]`. After the entry it is too late.

The reported symptom of leaving it on with no dog spawners is an endless dog
round, which is a hang `[community]`. One community tool's documentation claims
a hard script error at round 5 instead. We believe the hang: the dog spawner
init bails cleanly on an empty array, and the round the dogs are scheduled for
is `round_number + randomintrange(4,7)`, so it is not a fixed round 5 either
`[measured against the stock scripts]`.

A Treyarch wiki page adds that dog spawners belong in every zone even with dog
rounds disabled, because stock logic paths zombies toward those locations
during Zombie Blood and during a solo Quick Revive down `[Treyarch doc:
Phabricator disabling_dog_rounds_properly]`. That is `[unverified]` here and
needs playing, not a check.

---

# Part 3: zones, which govern both spawning and survival

This is the concept most of our defects came from. It is worth understanding as
a state machine rather than as a list of keys.

## A zone is a name, some volumes, and a bag of locations

`zone_init` creates a struct in `level.zones[<name>]` with four flags, all
false: `is_enabled`, `is_occupied`, `is_active`, `is_spawning_allowed`
`[stock script: _zm_zonemgr.gsc:286]`.

It then does two lookups that define what a zone physically is:

- **Volumes.** Every entity whose `targetname` is the zone name, filtered to
  classname `info_volume`. So the zone name **is** the volume's targetname. A
  zone with no volume trips an assert.
- **Locations.** Every struct whose `targetname` equals the value of the
  zone's **first** volume's `target` key. Note the index: a zone built from
  several volumes takes its spawn set from one of them `[stock script]`.

Each collected struct is sorted by the tokens of its `script_noteworthy`. The
four spawn tokens go into the zone's `zombie_location` bag. Any other token
becomes its own bag under that token's name, which is how a map declares
per-zone locations for anything else.

The `<zone>_spawners` naming most tutorials use is a convention, not a rule.
The string only has to equal the volume's `target`, whatever that is, and a
shipped map uses a different shape `[measured]`. The `<zone>_barriers` suffix,
by contrast, **is** hardcoded in the lookup for barrier goals `[stock script]`.

## The four flags, and what turns each one on

This is the whole model.

| Flag | Set by | Meaning |
|---|---|---|
| `is_enabled` | `enable_zone`, called from `manage_zones` for every `init_zones` entry, and from the flag waiter when a door flag connects it | The zone exists as far as the game is concerned |
| `is_occupied` | The zone loop, once per second, from player positions | A player is inside one of its volumes |
| `is_active` | The same loop: occupied zones, plus their connected and enabled neighbours | The zone contributes spawn locations |
| `is_spawning_allowed` | `enable_zone`, alongside `is_enabled` | Spawning is permitted here |

`manage_zones` runs the loop `[stock script: _zm_zonemgr.gsc:810]`:

1. Lock every player respawn point.
2. Call the map's `level.zone_manager_init_func` hook, which is where
   `add_adjacent_zone` calls live.
3. `zone_init` and `enable_zone` every entry of the `init_zones` array.
4. Set up the flag waiters, set `zones_initialized`, wait for
   `begin_spawning`.
5. Loop once per second: recompute occupied and active, then rebuild the
   spawn-location list from every zone that is enabled and active and allows
   spawning.

`create_spawner_list` is step 5's second half `[stock script:
_zm_zonemgr.gsc:1153]`. It clears `level.zm_loc_types` and refills it from
those zones only. That array is exactly what `round_spawning` draws positions
from. So the chain, end to end, is:

> zone volume names the spawn set → `zone_init` collects the structs → the
> zone loop marks the zone active → `create_spawner_list` flattens it into
> `level.zm_loc_types["zombie_location"]` → `round_spawning` picks from it

Break any link and the round waits forever.

There is a failsafe. If no zone is active or none allows spawning, the loop
forces the first initial zone active and sets `level.player_zone_found = false`
`[stock script]`. That is why a badly zoned map sometimes still spawns
something, in the wrong place.

One debugging trap in the same loop: its continue condition tests the `noclip`
and `notarget` dvars `[stock script]`. Turning noclip on with notarget off
stops zone management entirely.

## Enabling is not adjacency, and that distinction is where bugs live

`add_adjacent_zone` calls `zone_init` on both of its zones and enables
**neither** `[stock script: _zm_zonemgr.gsc:595]`. All it does is register the
pair and the flag that will connect them, and initialise that flag if nothing
else has.

The enabling happens later, in the flag waiter. When a flag is set, it walks
every registered adjacency, and for each one whose condition is now met it
enables **both** ends and marks the pair connected `[stock script:
_zm_zonemgr.gsc:675-730]`. So opening a door does not activate the far zone
directly. It sets a flag, and the waiter turns that into two enabled zones.

Two details of the condition matter to anyone wiring a complicated graph
`[stock script: _zm_zonemgr.gsc:531-568]`:

- Passing an **array** of flags to one `add_adjacent_zone` call means **all**
  of them must be set.
- Calling `add_adjacent_zone` **twice for the same pair** with different flags
  means **either** will do. The second call flips the pair into an or-check.

A separate function disconnects a pair again, for a door that closes
`[stock script: _zm_zonemgr.gsc:760]`. Disconnecting does not disable.

That or-behaviour explains a contested community observation. One tutorial
demonstrates reusing a single flag across two `add_adjacent_zone` calls and it
works. Another has a whole video on that pattern as the cause of zombies
spawning in every zone the moment any door opens `[community]`. Both are right,
and the script says why: **a flag reused across two different pairs opens both
pairs when it is set.** That is the desired behaviour when a door is meant to
open two ways at once, and the bug when it is not.

There is also a second function, `connect_zones`, which takes two zone names
and no flag, and enables both immediately `[stock script:
_zm_zonemgr.gsc:772]`. That is the mechanism behind one logical area spanning
several volumes: give the extra volume its own name, point its `target` at the
parent's spawn set, and join it with no door `[community, and consistent with
the script]`. A volume's `target` does not have to be unique.

So a zone becomes enabled by exactly two routes: being named in `init_zones`,
or being reached through a chain of set flags from a zone that was. A zone in
neither position stays disabled forever, and `zone_is_enabled` returns false
for it for the whole match.

That is not a harmless no-op. It is the next section.

## A player in no enabled zone volume dies outright

This is the single most important mechanism in the document, because it reads
in play as a random death rather than a bug.

`_zm.gsc` threads `player_out_of_playable_area_monitor` on every player
`[stock script: _zm.gsc:2035]`. The poll interval is 3 seconds `[stock
script: _zm.gsc:2022-2031]`. On each poll, a player who is in no life brush
and is either in a kill brush or not in an enabled playable area gets:

- Sam's laugh, played to that player only,
- a half-second wait,
- `self.health + 1000` damage with bleedout time set to zero
  `[stock script: _zm.gsc:2084-2098]`.

That is death at full health, not a down.

`in_enabled_playable_area` is the test `[stock script: _zm.gsc:1999]`. It
walks every entity carrying `script_noteworthy player_volume` and returns true
only where the zone named by that volume's `targetname` is enabled **and** the
player is touching the volume. Floor and walls are irrelevant. Geometry does
not make a place legal. A volume does.

Two consequences a designer has to hold in mind:

- **A zone volume is the playable area, not a spawning hint.** Anywhere a
  player can stand has to be inside one.
- **A volume naming a zone the script never enables is worse than no volume.**
  The room looks finished and kills whoever walks in.

## The doorway band, which is the defect this mechanism produces

Size two rooms' volumes to their interiors and the wall between them belongs to
no volume. Two 16-unit walls make a 32-unit band `[measured]`.

The player's hull is 30 units across. That comes from `PLAYER_RADIUS 15` in
`scripts/shared/player_shared.gsc`, from the same 15 in `_zm_unitrigger.gsc`,
and from the bot debug box drawn at `(-15,-15,0)` to `(15,15,72)` `[stock
script]`.

A 30-unit player standing in the middle of a 32-unit band touches neither
volume. Every doorway passes through that band. The worst case is a
128 by 32 deck laid in the band between two rooms: a surface meant to be walked
on that lies entirely out of bounds `[measured]`.

The rule that falls out: **size a zone volume to the room's outer box, walls
included.** Adjacent volumes should overlap through the wall rather than meet
at its faces. Whether `IsTouching` accepts a hull and a volume meeting exactly
on a plane is `[unverified]`, and a map that depends on the answer is one unit
from killing the player.

The video tutorials arrive at the same defect from the other end and report a
gap between two volumes killing whoever steps into it `[community]`. They ask
for the volumes to be flush. That is the case our own measurement says is one
unit from failing, so we ask for overlap instead.

Three more volume rules come from the same source. Two of them have now been
settled against the stock scripts and Treyarch's own map source, and the third
has not been tested:

- **Volumes of different zones must not overlap. This is false, and shipped
  maps disprove it** `[measured, stock-source]`. Every consumer of the volumes
  takes their union: `in_enabled_playable_area`, `check_point_in_playable_area`
  and the powerup drop test all loop over
  `getentarray( "player_volume", "script_noteworthy" )` and return true on the
  first hit, and `any_player_in_zone` does the same over one zone's own
  volumes. Overlapping two zones therefore makes a player in the overlap count
  as occupying both, which activates both — a spawning decision, not a fault.
  The one thing overlap does make ambiguous is `get_current_zone`
  (`_zm_utility.gsc:3614`): it returns the **first** zone in `level.zone_keys`
  order whose volume the entity is touching, and it caches the answer, so a
  player in an overlap stays in whichever zone claimed them first. Five callers
  read it. Treyarch's own `map_source/zm/zm_giant.map` carries **11 pairs of
  different-zone volumes that interpenetrate with positive volume**, measured
  with this repo's own reader and its SAT interpenetration test.
  `zm_alien_isolation` has six, all of them `main_zone` swallowing another
  zone whole. **Overlap is how this is done, not a defect**, and this package
  has never had a check against it.
- A volume must not cover ground the player cannot reach. **True, and the cost
  is sharper than the drop** `[stock-source]`. A zombie spawns with
  `self.no_powerups = true` (`_zm_spawner.gsc:359`) and
  `zombie_entered_playable` (`:593`) polls the volumes once a second; the first
  one it touches runs `zombie_complete_emerging_into_playable_area` (`:3253`),
  which clears that flag. So volume stopping at the barricade's wall line means
  a zombie killed in the yard drops *nothing*; volume reaching over the yard
  means it is already eligible out there, and
  `zm_powerups::powerup_drop` (`_zm_powerups.gsc:586`) then keeps the drop
  wherever it touches a volume — spending one of the round's four
  (`zombie_powerup_drop_max_per_round`, `:74`) on a spot nobody can walk to,
  for the 15 seconds before it times out. Check `Z40` is this.
- A volume brush stays an unmodified box. Do not carve it. Untested by this project
  `[community]` — though one of `zm_giant`'s 46 volume brushes has seven faces
  rather than six.

The converse also holds and is easy to miss. A room nobody walks to may still
need a volume. A teleporter's holding room is the named case: the player is
moved into a black box out of sight, and without a volume around it the
teleport is fatal `[community]`. A generator that fits volumes to walkable
geometry gets this wrong by construction.

## The flag-line question, settled

The community zone contract says to delete the two `always_on` flag lines from
the map's zone hook and use `add_adjacent_zone` instead `[community]`.

We believe the opposite, on measurement. The mod tools' own ZM template keeps
both lines. So does the framework's own hook. So do six shipped Treyarch zone
hooks, which keep both lines and call `add_adjacent_zone` in the same function
`[measured]`. The guide presents an either/or that the shipped
maps treat as an and/both.

One ordering detail is real. Put the flag lines **before** the adjacency calls.
`add_adjacent_zone` calls `flag::init` itself for a flag nothing has defined
yet, and `flag::init` writes the flag back to 0 and asserts on a re-init in a
dev build `[stock script]`. A door flag that is also the always-on flag gets
initialised twice in the other order.

The community contract also says the first zone must be named `start_zone`
`[community]`. It need not be. The name appears in the zone manager only in a
comment, and shipped maps use four different names `[measured]`. The guide's
own text elsewhere says the name can be anything unique.

## The respawn-point detail nobody has played

`manage_zones` locks every `player_respawn_point` struct and asserts that each
carries a `script_noteworthy` `[stock script: _zm_zonemgr.gsc:821]`.
`enable_zone` unlocks only the structs whose `script_noteworthy` equals the
zone being enabled `[stock script: _zm_zonemgr.gsc:507]`. Treyarch's
`zm_giant.map` carries nine of them, one per zone `[measured]`.

A map that emits one respawn point carrying a name that is not a zone name
never gets it unlocked. Round 1 spawning is unaffected, because the initial
spawn path filters on `script_string` instead. What the locked struct affects
is coop relocation and revive placement `[stock script]`. The consequence is
`[unverified]`: it has not been playtested with a second player.

---

# Part 4: where a player can walk, and where a zombie can

Players and zombies move under two different rule sets with two different sets
of numbers. Confusing them produces the most expensive class of defect in this
game, because both sides compile clean.

## The player's numbers come from dvars in the stock scripts

| Quantity | Value | Source |
|---|---|---|
| Hull width | 30 | `PLAYER_RADIUS 15`, plus the bot debug box `[stock script]` |
| Hull height | 72 | The same debug box `[stock script]` |
| Jump height | 64 | The `jump_height` dvar `[stock script: scripts/zm/gametypes/_globallogic.gsc:142]` |
| Fall damage starts | 256 | The `bg_fallDamageMinHeight` dvar, same file line 144 |
| Fall damage kills | 512 | The `bg_fallDamageMaxHeight` dvar, same file line 145 |
| Step height | not stated | See below |

The caveat on the last three is real and has to be carried. All three
assignments sit inside an `if ( level.oldschool )` branch, next to a doubled
player clip size `[stock script]`. They are what the stock scripts assert for
that mode. The unconditional defaults are stated nowhere in the mod tools,
because the shipped configs only `reset` those dvars `[unknown]`.

There is **no step-size dvar anywhere in the shipped scripts** `[measured]`.
The generator specification records 8 as the rise the authors this project
inherited from used and reported as climbable `[community]`. Our recipes climb
in 16s. Treating 16 as the player's step is an assumption and is labelled one
in our code `[unverified]`. It matters less than it looks, because the jump is
four times larger.

## The zombie's numbers come from a file Treyarch ships

`bin\default_navmesh_settings.json` is the configuration `cod2map64 -navmesh`
runs against `[Treyarch doc]`. Four keys decide what surface exists:

| Key | Value | What it refuses |
|---|---|---|
| `maxStepHeight` | 18 | A tread that rises further |
| `minCharacterWidth` | 31 | A way through narrower than this |
| `characterHeight` | 72 | A way through with less headroom |
| `maxWalkableSlope` | 46 | Terrain steeper than this, in degrees |

Three more keys from the same file matter `[Treyarch doc]`:

- `simplification.maxBorderHeightError` is 30, and the generator spends it. Our
  own measurement over one map's heightfield puts the mesh a median of 2 units
  from the model's samples and 20 at the worst `[measured]`.
- `simplification.minCorridorWidth` is 30, one less than `minCharacterWidth`.
- `pruning.minDistanceToSeedPoints` is 14. Seed points are documented nowhere
  and we do not know how they are placed `[unknown]`.

The file also holds two navvolume blocks for flying enemies, `volBig` and
`volSmall`, with character dimensions of 400 by 300 by 100 and 26 by 20 by 20
`[Treyarch doc]`. Which entities use the volume rather than the mesh is not
documented `[unknown]`. The compiler's own warning line says flying units
`[measured]`.

All four thresholds fail the same way, and it is the worst failure mode in the
game. The compiler lays no walkable surface over the offending geometry, exits
0, says nothing about it, the link is clean, the map loads, and in play the
walkers simply never go there. If the place they will not go is where the
round's zombies are, the round does not end.

Nothing in the file states units. 46 is almost certainly degrees, and the file
does not say so `[unverified]`.

## Treyarch's scale standards, which are the design numbers

One unit is one inch, and the world is built at about 120% of real life
`[Treyarch doc: Scale_Standards.pdf]`. That document is the only published
set of dimensions for this engine, and it is written for multiplayer. It is
worth reading against the navmesh numbers above, because they agree.

| Thing | Number |
|---|---|
| Player standing | 72 tall by 32 wide |
| Player crouched | 52 by 32 |
| Player prone | 32 by 32 |
| Storey, interior and exterior | 112 and 128 default, 144 and 160 high, 96 low interior |
| Floor thickness | 16 |
| Wall thickness | 8 |
| Railing | 32 |
| Door hole | 56 by 96 single, 110 by 96 double |
| Window, default | 56 by 64, sill 32 |
| Window, minimum traversable | 40 by 60, sill 32 |
| Window, maximum non-traversable | 32 by 32, sill 48 |
| Hallway clearance | 96 minimum, never for a run longer than 128 |
| Hallway width | 128 minimum without combat, 160 with |
| Pinch point | 64 minimum, 32 deep or less, never over 64 deep |
| Stairs | 80 minimum width, rise 8 with run 12 |
| Jump, standing | about 100 units of distance, 39 of height |
| Jump, sprinting | about 220 and 50 |
| Cover | 32 minimum width, 72 full, 48 standing, 36 crouch, 16 prone |

Two things fall out of reading that table next to the navmesh settings.

- `characterHeight` 72 is exactly the standing player. `minCharacterWidth` 31 is
  one unit under the documented player width of 32. `maxStepHeight` 18 is well
  over the default stair rise of 8, so standard stairs are walkable by
  construction.
- **Treyarch's traversable window is not a barricade window.** The 40 by 60 at
  sill 32 is a player mantling through. A zombie crossing a barricade plays an
  animation whose channel runs from the floor up 40 units `[measured off the
  prefab's own brushes]`, so a barricade wants sill 0. The two numbers are
  about two different acts and neither is wrong.

## The one-unit trap

The player's hull is 30 and the navmesh wants 31. A 30-unit doorway is a
doorway a player fits through and no zombie ever paths through.

Treyarch's own scale reference gives the standing player 72 tall by 32 wide
`[Treyarch doc: Scale_Standards.pdf]`, and names 32 as the minimum width of
every piece of cover. So there are three numbers in circulation for one
quantity: 30 from the scripts, 31 from the navmesh settings, 32 from the scale
document. They cannot all be the collision width and the conflict is
`[unverified]`.

Clearing 31 satisfies all three. That is the number to design to if the
question is whether a surface exists at all.

It is not the number to build to. 31 is where the navmesh disappears.
Treyarch's own hallway minimum is 96. The video tutorials use 64 as a
rule-of-thumb minimum anywhere zombies travel `[community]`, which sits between
the two and is offered as experience rather than as a measurement.

A barricade window is the documented exception. Zombies cross one by playing
the prefab's traversal animation rather than by walking `[measured]`, which is
why a 96 by 48 hole works despite being below the 72-unit corridor height.
Treyarch's scale document exempts them explicitly `[Treyarch doc]`.

The animation is authored to a fixed height, and the tutorials give the
zombie's hand plant as 40 units `[community]`. That is the top of the traversal
channel we measured off the prefab, which runs from the floor to 40. The two
agree, and both say the same thing about the sill: the opening has to start at
the floor, because the channel starts there.

## What the navmesh actually looks like

The compiler writes `<map>_navmesh.hkt` beside the BSP. It is a Havok binary
tagfile, version `hk_2014.2.0-r1`, and every one the compiler has written for a generated map holds five
tagfiles end to end: generation settings, two small ones, the mesh, and a
one-string tagfile carrying the same JSON as the metadata file `[measured]`.

We read it. The format was worked out by inspection, because no Havok
specification is published. The reader holds itself to the file's own
arithmetic rather than to a guess: face edge ranges chain to exactly the edge
count, the largest vertex index is one less than the vertex count,
`oppositeEdge` is symmetric, and every face is a closed ring `[measured on
eleven meshes]`.

Vertices are in metres, and the conversion is derived rather than assumed. The
settings tagfile inside the same file stores `maxStepHeight` as 0.4572, which
is exactly 18 times 0.0254, and 18 is the documented value `[measured]`. So one
map unit is 0.0254 metres, which is an inch.

Four behaviours of the generator matter to a designer, all `[measured]` on
probe maps:

- **It simplifies stairs into a ramp.** A six-tread flight comes out as one
  sloping face, not six.
- **It stops at a wall and starts again in the yard.** A barricade window
  leaves two disconnected pieces on purpose. A count of mesh islands means
  nothing on its own.
- **It paths straight through a door opening.** A door leaf is an entity, not
  world geometry, so the mesh is continuous across it.
- **It lays no surface on anything more than one step up.** A table top 32
  units above its floor gets no mesh, so it is a place a player can stand and
  nothing can follow.

That last one is a design tool as much as a defect. It is what a table is. It
is also what an arena platform must not be.

## Pathnodes are a second navigation system, and zombies use both

The mesh is what walkers walk on. Pathnodes are what the traversal system uses,
and a barricade's exterior goal is one. Treyarch's entity field listing exposes
what script and the engine read off a pathnode: `script_linkname`,
`script_noteworthy`, `animscript`, `movementtype_ignore`,
`movementtype_require`, `type`, a `suspended` bitflag, and `cost_modifier`
`[Treyarch doc: ScriptObjectFields.pdf]`.

`cost_modifier` is the documented way to bias AI pathing toward or away from a
route. Nothing here has used it.

The same listing confirms something useful about Radiant keys generally: the
entity fields script can read include `targetname`, `target`,
`script_noteworthy`, `script_animname`, `spawnflags`, `health`, `dmg`, `count`
and `team` `[Treyarch doc: same]`. The tutorials' key names are ordinary entity
fields, not special cases. `script_string` and `script_int` are **not** in that
listing, which is consistent with them being Radiant keys the scripts read
rather than engine fields.

## Reachability is a separate question from clearance

Every rule above can pass on a map with a perk machine on a shelf and a room
with no way in. The floor is inside a zone volume, the doorway is wide enough,
the flight of stairs connects at both of its own ends. Nothing notices.

Deciding reachability means flooding the standing surfaces from the spawn
slots, with the player's own movement rules. What stops a player and what does
not, as we model it:

- **Solid structural geometry stops a cell.** Detail brushes and caulk-only
  brushes do not.
- **Height is a gate in three bands.** Up to a step is walked, up to 64 is
  jumped, a drop under 512 is taken.
- **A drop is a one-way link.** A balcony a player can fall off and not climb
  back onto is reached, not unreachable.
- **A bought door does not block.** A door is a price, not a lock, and it is an
  entity rather than world geometry. A sealed opening is world geometry and
  does block. Removing one glass pane from a map turns a sealed room from
  unreachable to reachable, which is the measurement that says the obstacle
  test works `[measured]`.
- **A ramp is not a route, in our model.** Sloped massing is treated as an
  obstacle because the model cannot say what is under a point on a sloped top.
  That is a limitation of our representation, not of the game `[unverified]`.

One correction the flood needed is worth recording because it is a real map
pattern. An opening cut more than a step above its own room's floor looks like
a window. A multi-storey map can enter several rooms through exactly that: a door
cut at an upper floor's height in the wall of a room whose own floor is
hundreds of units lower, where a stair landing meets it `[measured]`. The wall
under that sill is solid by construction, so the sill is a surface a player
stands on.

## Falling out of the world

Two separate mechanisms, and a map wants both.

**A mesh terrain is a surface, not a volume.** A player can get through it and
end up underneath, alive, with nothing to kill or reset them. The only way out
is to quit `[measured]`. The fix is to fill the volume under the mesh with
solid brushes. Treyarch does exactly this: the Giant's geometry source carries
one caulk block spanning the whole map down to z -288 `[measured]`.

**Every map wants a floor of last resort.** A `trigger_hurt` slab under the
whole map, with faces of material `trigger` and positive `dmg`. The shipped
slabs carry 1000 or 10000 `[measured]`. It appears six times across the roughly
730 shipped `.map` files (the count varies by tools version), so it is convention rather than a stated requirement.
Nothing in the tool chain mentions it and the build is clean either way
`[measured]`.

Its top has to stay below every zone floor, or it kills players standing in
bounds.

---

# Part 5: buying things

Doors, wall guns, perks, the box and Pack-a-Punch all follow one shape, and
knowing the shape is worth more than knowing five sets of keys.

## The shape: a map places a marker, the framework builds the rest

With one exception, a map does not place a working machine. It places a struct
or an entity carrying a few keys, and Treyarch's script spawns the model, the
use trigger and the collision at run time.

| Thing | What the map places | What the framework spawns | Lookup |
|---|---|---|---|
| Perk machine | `script_struct`, `targetname zm_perk_machine`, `script_noteworthy <perk>`, `model <machine model>` | `trigger_radius_use` named `zombie_vending`, a `script_model`, and a `zm_collision_perks1` clip | `struct::get_array("zm_perk_machine","targetname")` `[stock script: _zm_perks.gsc:1437]` |
| Pack-a-Punch | A zbarrier entity, `targetname zm_pack_a_punch` | `trigger_radius_use` named `pack_a_punch`, plus a collision model | `GetEntArray("zm_pack_a_punch","targetname")` `[stock script: _zm_pack_a_punch.gsc:84]` |
| Mystery box | `script_struct`, `targetname treasure_chest_use` | A unitrigger offset off the box's own front | `struct::get_array("treasure_chest_use","targetname")` `[stock script: _zm_magicbox.gsc:95]` |
| Power switch | A trigger, `targetname use_elec_switch`, whose `target` names its parts | Nothing, the parts are placed | `GetEntArray("use_elec_switch","targetname")` `[stock script: _zm_power.gsc:41]` |
| Buyable door | A `trigger_use`, `targetname zombie_door`, with `zombie_cost` and `script_flag` | Nothing, the leaf is placed | `GetEntArray("zombie_door","targetname")` `[stock script: _zm_blockers.gsc:80]` |
| Wall buy | A stock `spawnable_weapon_<slug>.map` prefab | Everything inside the prefab | The prefab's own structs |

Three details of that table pay for themselves.

- **The perk trigger is a radius, not a box.** It is spawned at the struct's
  origin plus 60 in z, with radius 40 and height 80 `[stock script:
  _zm_perks.gsc:1513]`. Pack-a-Punch is the same shape with the numbers in
  level variables `[stock script: _zm_pack_a_punch.gsc:106]`. So a player can
  use a perk machine from any side, and a machine facing a wall still sells the
  perk.
- **The mystery box is the exception.** Its unitrigger origin is offset 22.5
  units along the box's own left `[stock script: _zm_magicbox.gsc:294]`. A
  box facing the wrong way loses its prompt. That is why the box is the one
  purchasable whose rotation bug shows up immediately.
- **A perk struct can carry a start-location filter.** If it has a
  `script_string`, one of its tokens must equal `<ui gametype>_perks_<start
  location>`, which is the same match-string pattern player spawns use
  `[stock script: _zm_perks.gsc:1431]`. No `script_string` means always
  spawn.

Our own approach box for a machine, 40 wide by 64 deep starting 24 units out,
is `[inherited, unverified]`. The stock trigger is a 40-radius cylinder, and
the stock machines carry their own `zm_collision_perks1` clip whose dimensions
nothing here has measured `[unknown]`.

## Prefab rotation, which is the bug that hides best

`cod2map64` turns a prefab **counter-clockwise** by its yaw `[measured]`. That
was settled by comparing a wall buy's weapon struct in the source against its
position in the compiled BSP: a clockwise turn would have put it on the
opposite side.

The heading a family's front points at yaw 0 is per family, and the families
disagree. Read off each stock prefab on the install `[measured]`:

| Family | Front at yaw 0 |
|---|---|
| Wall weapon | North |
| Perk machines | South |
| Pack-a-Punch | West |
| Gobblegum | South |
| Mystery box | North |
| Power switch | South |
| Barricade exterior | North |

A generator that assumes one heading for all of them is wrong for most.

This failure hid three ways over `[measured]`:

- A clockwise turn is right on the two headings parallel to a family's front
  and 180 degrees out on the other two. Half of every map looked correct.
- Perk and Pack-a-Punch prompts are radius triggers and survive a wrong yaw
  entirely, so the machine still works while facing a wall.
- Only the box loses its prompt, for the offset reason above.

The wall buy is the one that shows immediately. Turned wrong, the chalk drawing
faces into the brickwork, the mount sticks out into the room, and the
unitrigger origin sits inside the wall. Ten of eleven wall buys on one
generated map shipped that way `[measured]`.

The riser paired with a barricade is not a prefab and does not follow the
table. It is an AI spawn struct whose `angles` are a plain world heading. The
stock barricade prefab's own exterior goal struct faces straight back at the
window, so a riser faces the opposite of the exterior heading `[measured]`.

## What a map controls about a price, and what it does not

**Price: yes.** A price is not a key on a wall buy. It is a column of a string
table. The framework loads the level's weapon table and stores each row's cost
on a struct in `level.zombie_weapons[<weapon>]`, which the purchase reads live
`[stock script: _zm_weapons.gsc load_weapon_spec_from_table and
add_zombie_weapon]`. A map that charges its own prices ships its own table,
exactly as Treyarch's levels do.

Getting that table loaded is **two jobs**, and the second is the one people
miss.

- The server side is a hook. `zm_usermap.gsc` installs the stock loader with a
  `DEFAULT(...)` macro, and `DEFAULT` only assigns while the variable is
  undefined `[stock script]`. So a map that assigns
  `level._zombie_custom_add_weapons` in its own `main()`, before the framework
  entry, wins.
- The client side has no hook at all. `zm_usermap.csc` calls its weapon include
  directly `[stock script]`. **The number on the purchase prompt is filled in
  client side.** A map that does the server half and not the client half
  charges its own price and displays Treyarch's.

Two more ways to ship a table and change nothing `[measured]`: assigning the
hook after the framework entry, where the `DEFAULT` has already filled it in,
and loading the map's table without loading the stock one first, which does not
re-price the level, it empties it down to the map's own rows.

**Name: yes, and it costs a text file.** Spec 5.7 carries the measurement.

- A map ships its own localized strings. `localize,<name>` in the map's zone,
  against a hand-written `share\raw\english\localizedstrings\<name>.str`,
  links clean, and the linker's own dependency file names the `.str` it read
  `[measured]`. The install shipping no `.str` of its own is true
  and says nothing about whether the linker accepts one.
- The linked asset is called `<STR FILE>_<REFERENCE>`, uppercased, always
  prefixed `[measured]`. Script refers to it as `&"<MAP>_<REFERENCE>"`.
- The wall buy reads its hint back off a struct a map can write:
  `get_weapon_hint` returns `level.zombie_weapons[weapon].hint`
  `[stock script: _zm_weapons.gsc:1417]`, and both prompt-building sites call
  it `[:969, :1305]`. The loader force-assigning that field `[:559-566]` sets a
  default, not a constant. Reading the write and missing the read is what
  produced the old "settled" answer.
- The cost still arrives as the first parameter, so the map's string carries
  `&&1` where the price goes `[stock script: _zm_unitrigger.gsc:749-765]`.

What does not change: the buy still hands over Treyarch's weapon, and the
weapon icon on the prompt is still Treyarch's. Only the sentence is the map's.

## A weapon the game does not have fails silently

`getweapon` answers for a name that does not exist, nothing raises, and the
feature that asked for it does nothing `[measured]`. This was found on a rigged
mystery box asking for `shotgun_olympia`, a Black Ops I and II name that is in
no table and no assetlist on the mod tools install. The box behaved like an ordinary box.

A string table is opaque to the linker, which packs the text without reading
it. So a table row naming a weapon that does not exist links clean and hands
out nothing `[measured]`. A `weapon` line in the manifest naming an asset the
database does not have does stop the link, which is the good half.

A wall buy is two strings away from its weapon, not one. The slug names the
`spawnable_weapon_<slug>.map` prefab. The weapon is named inside that file on
the buy struct's `zombie_weapon_upgrade` key. All thirteen were read off the
install `[measured]`. Twelve match their slug. The `bowie` buy
names `bowie_knife`, which is a real row of the level table at cost 3000, not
in the box.

## Doors carry the zone graph

A buyable door is where the purchase system and the zone system meet. The
trigger carries:

- `zombie_cost`, the price.
- `script_flag`, set when bought. Comma-separated for more than one.
- `target`, naming the door leaf and its clip.
- `script_noteworthy`, choosing the variant: default, `electric_door`,
  `electric_buyable_door`, `local_electric_door`, `kill_counter_door`
  `[stock script: _zm_blockers.gsc:161-210]`.

That `script_flag` is the same string the map passes to `add_adjacent_zone`. A
flag named in a door and in no adjacency call opens a door onto nothing. A flag
named in two adjacency calls connects more than the door implies.

Three details that fail silently:

- **The door leaf and its clip both need the dynamic-path flag set.** Without
  it the door opens, the clip is removed, and the navigation mesh does not
  reconnect across the opening. The build says nothing `[community]`. This is
  the same shape as everything else in Part 4: correct geometry, no surface.
- **A power door carries no `zombie_cost`.** `script_noteworthy` of
  `electric_door` makes it wait for power instead of taking points
  `[stock script]`, and it has to slide or rotate rather than be debris
  `[community]`.
- **Debris is a second fixed literal.** The stock scripts scan for
  `zombie_debris` the way they scan for `zombie_door` `[community]`.

Two key conventions on the moving parts are easy to get backwards
`[community, two channels independently]`: on `script_angles` the yaw is the
**middle** of the three numbers, and `script_vector` is an absolute
displacement in units which may be negative.

One geometry trap: a sealed pane and a door leaf in the same opening is a
defect. The pane does not move. The door takes the money, plays its animation,
and leaves the pane standing `[measured]`.

## The generic purchase loop, for anything the framework does not already own

Every wall buy, trap and custom purchase is the same shape, and the community
wiki writes it out `[community: UGX Purchase-Loops]`:

1. `#using scripts\zm\_zm_score;` gives `minus_to_player_score`, which both
   deducts and shows the change on the HUD.
2. `GetEnt( "<name>", "targetname" )` for the `trigger_use`.
3. Inner loop: `trigger waittill( "trigger", player )`, check the player's
   score against the cost, deduct and break out.
4. Outer loop: run the effect, then wait out the cooldown before re-arming.

The rule behind it is general to this language: a `while` loop with no `wait`
or `waittill` in it spins twice in one frame and hangs the script.

## Two indexing rules that look cosmetic and are not

Both come from Treyarch's own wiki and both are flagged there as important
`[Treyarch doc: Phabricator setting_up_different_mystery_boxes,
setup_traps]`.

- **Mystery box locations are numbered from 0 with no gaps, and the number is
  unique across box types.** An Origins box 0 and a different box 0 in one map
  breaks both completely. The value is a bare digit, so `3` and never `03`.
- **Trap letters come from one pool across all trap types**, not one pool per
  type. An electric trap A and a fire trap A cannot coexist.

Getting either wrong links clean and leaves dead furniture.

## What registering a perk actually involves

A perk is not a prefab with a script behind it. It is **six calls into
`zm_perks`, made before the framework entry**, plus one `script_struct` in the
map. Everything else -- the use trigger, the bump trigger, the collision, the
power wiring, the drink animation, the loss-on-down -- the framework builds
from those six calls.

The perk is keyed by its **specialty string**, and that string is three things
at once: the key into `level._custom_perks`, the value of `script_noteworthy`
on the map's struct, and the argument the engine's own `SetPerk` / `HasPerk` /
`UnsetPerk` are given. Treyarch's doc block says so: the specialty names the
perk, must be unique, and is how system scripts identify it `[Treyarch doc: doc
block above register_perk_basic_info in the mod tools' _zm_perks.gsc]`.

The six calls, with what each one buys `[stock script: _zm_perks.gsc:1917,
1936, 1973, 1989, 2013, 2035]`:

| Call | What the framework then does |
|---|---|
| `register_perk_basic_info( specialty, alias, cost, hint, bottle )` | Fills in the price the trigger charges, the prompt it shows, the bottle the player drinks, and the **alias**, which is the name the power switch notifies on. |
| `register_perk_precache_func( specialty, &f )` | Calls `f` during `zm_perks::init`, where it must fill `level.machine_assets[ specialty ]` with the on-model, the off-model and the bottle weapon, and set any `level._effect[...]` handle it will ask for. |
| `register_perk_clientfields( specialty, &register, &set )` | Registers the perk's HUD client field and gives the framework the setter it calls when the perk is gained or lost. |
| `register_perk_machine( specialty, &setup )` | Calls `setup( use_trigger, perk_machine, bump_trigger, collision )` on the four entities it just spawned, so the perk can stamp its own names on them. |
| `register_perk_host_migration_params( specialty, radiant_name, light_fx )` | Turns the generic `perk_machine_think` loop on. Without all three of alias, radiant name and light fx, that loop never starts -- and the buy trigger blocks forever on `level waittill( specialty + "_power_on" )`, which only that loop sends. |
| `register_perk_threads( specialty, &give, &take )` | Threads `give` on the player at purchase and `take` when the perk is lost. |

The map's half is one struct, and the KVPs are the arguments of that machine
setup call rather than a convention `[stock script: `_zm_perks.gsc`
`perk_machine_spawn_init`]`:

- `targetname` `zm_perk_machine` is how the system finds it,
- `script_noteworthy` is the specialty string,
- `model` is the machine's xmodel, and a struct without one is **skipped in
  silence**,
- `script_int` is the power zone, `script_string` filters by start location,
  `script_notify` opts into randomised machine locations.

No trigger is authored. `perk_machine_spawn_init` spawns a
`trigger_radius_use` named `zombie_vending`, a `trigger_radius` named
`audio_bump_trigger` and a `script_model` carrying the one shared
`zm_collision_perks1` clip, and hands all four to the perk's setup callback.

Losing the perk is free and is the framework's, not the perk's. `perk_think`
waits on death, fake death, player-downed or `<specialty>_stop`, calls
`UnsetPerk`, decrements the perk count, threads the perk's own take function
and clears the HUD field `[stock script: _zm_perks.gsc:911]`. A perk's give
thread is expected to `endon( <specialty> + "_stop" )` and its take thread to
send that notify.

### The thirteen slots, and what is actually behind them

Two different thirteens get confused, and only one of them is a HUD limit.

- **Thirteen specialty strings** are `#define`d in `_zm_perks.gsh` and listed
  on Treyarch's Der Wunderfizz page: `specialty_quickrevive`,
  `specialty_armorvest`, `specialty_doubletap2`, `specialty_fastreload`,
  `specialty_deadshot`, `specialty_phdflopper`, `specialty_staminup`,
  `specialty_additionalprimaryweapon`, `specialty_tombstone`,
  `specialty_whoswho`, `specialty_electriccherry`, `specialty_vultureaid`,
  `specialty_widowswine` `[Treyarch doc: Phabricator
  setting_up_the_der_wunderfizz]`.
- **Thirteen HUD client-field names** are `#define`d beside them as
  `PERK_CLIENTFIELD_*`, each of the form `hudItems.perks.<name>`
  `[measured in share/raw/scripts/zm/_zm_perks.gsh, 13 defines,
  lines 8-20]`. Only **nine** of those names appear in any shipped script --
  juggernaut, sleight_of_hand, quick_revive, doubletap2, dead_shot, marathon,
  additional_primary_weapon, widows_wine, electric_cherry -- because only nine
  perks have a module `[stock script: grep of the whole decompiled tree, and of
  the ten _zm_perk_*.gsc files in the mod tools, one of which is Der
  Wunderfizz rather than a perk]`. The other four are **not** four spare HUD
  slots: `tombstone` has a widget in the shipped interface and `phdflopper`,
  `whoswho` and `vultureaid` do not. See "The heads-up icon" below, which is
  where that stops being a curiosity.

So the game names thirteen perks and ships nine modules, of which one --
Electric Cherry -- is a dev stub, leaving **eight that work as shipped**. The
four with a name and no module are PhD Flopper, Vulture Aid, Who's Who and
Tombstone. Seven of the eight have a prefab to stamp; Widow's Wine does not,
which is a missing convenience rather than a missing perk.

### Der Wunderfizz is a machine, not a perk

The tenth `_zm_perk_*` file on the install is `_zm_perk_random`, and it is the
machine that sells a *random* perk rather than a perk of its own. It shares
nothing with the perk-machine mechanism: the perks are structs the framework
finds and dresses (`_zm_perks.gsc:1437`), and this is a real zbarrier entity
the stock script finds by `targetname` and drives by piece index
(`_zm_perk_random.gsc:91`, `:843-910`). What it hands out is a list the *map*
fills in, one `zm_perk_random::include_perk_in_random_rotation` call per perk,
and nothing fills it in for you.

Everything it needs is stock: `xmodel,p7_zm_vending_wonder`, all three script
halves and its four effects are already in
`zone_source/all/assetlist/zm_levelcommon.csv`, so a map declares no asset and
precaches nothing `[measured]`. There is no
Wunderfizz prefab on the mod tools install and none is needed.

`Blueprint.place_wunderfizz` places one, and by default its rotation is every
perk the map places -- which is also the only rotation that is safe by
construction, because the perk's own module is what writes the
`level.machine_assets` entry the machine reads for the bottle it shows. The
four ways it fails quietly are `Z49` in `playable-map-requirements.md`.
**Unplayed**: the entity and both script halves are generated and checked, and
no one has bought a perk from one.

### The heads-up icon: what draws it, and why a fourteenth slot is not ours

**Nothing in script draws a perk icon.** The only thing a perk's own code does
with its icon is `#precache( "material", "specialty_<name>_zombies" )`, which
puts the art in the fastfile and nothing more. The old script-side HUD path is
still in `_zm_perks.gsc` and is dead: every write to `self.perk_hud` is
commented out, `perk_hud_destroy` and `perk_hud_grey` are called from nowhere,
and `update_perk_hud` walks an array nothing ever fills. What actually draws
the icon is the game's own interface layer, and all the perk hands it is a
number written into a UI-model path -- `hudItems.perks.<name>` -- by the engine
builtin behind `clientfield::set_player_uimodel`.

So an icon is two halves, and a map can ship one of them:

- **The art** is an ordinary `material` plus `image` asset. A usermap can build
  and ship those.
- **The binding** from a UI-model path to a widget is not an asset a map can
  write. A stock script says where it lives: `clientfield::register(
  "clientuimodel", "hudItems.proximityAlarm", ... ); // registered client-side
  in raw/ui/uieditor/clientfieldmodels.lua`. That is Lua, inside the game, and
  the mod tools ship no Lua at all.

**The thirteen are a declaration, not a cap.** They are thirteen `#define`
lines in a `.gsh`. Nothing in the perk framework counts them, and registering a
fourteenth `clientuimodel` path is ordinary, legal script that will link. It
simply lights nothing, because the interface layer has no widget listening on a
path it has never heard of. The limit that bites is not a number of slots. It
is that the one file which maps a path to a widget is Lua we cannot pack.

**That is also why the community's answer and our measurement do not
contradict each other.** The published route is to ship an interface file of
your own and load it from the `.csc`, and it is written for an install where
Lua support has been patched into the tools. On a stock install the linker
answers `ERROR: Lua not supported` and writes a fastfile anyway. Both are true:
theirs is an install that was changed, ours is one that was not, and a map that
needs the change is not self contained.

**What a map gets instead: eleven paths that are already wired, and it does not
have to register them.** The binding table is not a registry the game builds at
run time; it is a hard-coded list inside one interface widget, and the published
decompiles of that widget can be read. The zombies factory HUD carries eleven
keys, the Shadows of Evil HUD ten, and each key names the image to draw as a
plain string the widget resolves when the value changes. So:

- **Nine of the eleven are the nine perks with a module**, and their art is on
  the stock list. A custom perk can light one of them by handing the framework
  a do-nothing register function and a setter that writes a path the stock
  module already registered -- `register_perk_clientfields` is optional, and
  every call site of it is `isdefined`-guarded.
- **`tombstone` and `dive_to_nuke` are bound to images that are not in any
  stock asset list.** Two wired slots with nothing drawing in them, and
  `dive_to_nuke` is not even one of the thirteen script names.
- **`phdflopper`, `whoswho` and `vultureaid` are not in the widget's table at
  all.** Setting those paths does nothing, whatever art the map ships. The
  earlier count of "four names with a slot and nothing behind them" was one
  too many on the HUD side: tombstone has a widget, it is the other three that
  have none.
- **The art is a name, so a map can ship its own.** Community practice, not
  measured: put an image asset under the stock name in your own `.gdt` and
  add `image,<stock name>` to the map's zone, and the map's fastfile wins.

That makes the honest answer to "is thirteen a hard limit" a three-parter.
Thirteen is a `.gsh`, not a limit. Eleven is what the shipped interface will
draw without Lua. A fourteenth *key* needs an edit to the interface layer, and
that is an install change, not a map.

<details><summary>The measurements and the sources</summary>

In the mod tools install:

- Dead script HUD: `_zm_perks.gsc:951` (`//self perk_hud_destroy( perk );`),
  `:1258` and `:1282` (both commented `perk_hud_grey`), against live
  definitions at `:978`, `:984`, `:1166`. No uncommented write to
  `self.perk_hud` exists anywhere under `share/raw/scripts`.
- Icon precache and nothing else: the seven `*_SHADER` defines
  (`_zm_perk_*.gsh:6`, quick revive `:5`) are each used once, in a
  `#precache( "material", ... )`. `grep -rn "_SHADER" share/raw/scripts/zm`
  returns those and the Electric Cherry stub's own define, nothing else.
- Where the binding lives: `shared/weapons/_weaponobjects.gsc:70`.
- No Lua on the install: `find -iname "*.lua" -o -iname "*.luac"` returns 0
  files.
- Art on the stock list, `zone_source/all/assetlist/zm_levelcommon.csv:5856-5878`:
  `image,specialty_` `ads_zombies`, `doubletap_`, `fastreload_`,
  `juggernaut_`, `marathon_`, `quickrevive_`, `three_guns_`, `widows_wine_`,
  `blue_electric_cherry_`, each also as a `giant_` variant. `grep -rn
  "tombstone\|divetonuke" zone_source/all/assetlist/*.csv` returns **nothing**.
- All nine modules load in every level: `zm_levelcommon.csv:7041-7061`.
- Optional registration: `_zm_perks.gsc:971`, `:1638`, `_zm_perks.csc:47`,
  `:68`.

From published decompiles of the shipped interface (community tier, quoted):

- `ZMPerksContainerFactory.lua`, 2025 dump, opens with a table of exactly
  eleven keys -- `additional_primary_weapon = "specialty_giant_three_guns_zombies"`,
  `dead_shot`, `dive_to_nuke = "specialty_divetonuke_zombies"`, `doubletap2`,
  `juggernaut`, `marathon`, `quick_revive`, `sleight_of_hand`,
  `tombstone = "specialty_tombstone_zombies"`, `widows_wine`,
  `electric_cherry = "specialty_blue_electric_cherry_zombies"` -- and the only
  use of `hudItems.perks` in the file is `for f5_local4, f5_local5 in pairs(
  f0_local0 )` over that table
  `[https://raw.githubusercontent.com/KingslayerKyle/T7LuaRepo/main/Dumps/PC_Ship_2025-05-31/ui/uieditor/widgets/HUD/ZM_Perks/ZMPerksContainerFactory.lua]`.
  The 2015 launch dump has ten keys and no `electric_cherry`; the Shadows of
  Evil container has ten and uses the non-`giant_` names.
- The image is resolved from the string at run time:
  `PerkImage:setImage( RegisterImage( image ) )` in `PerkListItemFactory.lua`,
  same dump.
- `clientfieldmodels.lua` in every dump registers `hudItems.proximityAlarm`
  and no `hudItems.perks.*` -- the perk models are made by the widget itself
  with `Engine.CreateModel`.
- Overriding the art by name: *"you need to create as many images as you plan
  to override perks ... `specialty_giant_juggernaut_zombies` ... After you
  have you zone file open all you need to do now is add these ... `image,
  specialty_giant_juggernaut_zombies`"* `[community: UGX-Mods 14333, Setting
  Up Custom Perk Shaders, https://www.ugx-mods.com/forum/modding/93/setting-up-custom-perk-shaders/14333/]`,
  corroborated on Modme 1498 where DTZxPorter confirms the names are the real
  asset names. Nobody published a link log either way, so **this is reported
  practice, not a measurement**, and the failure case in that thread is a map
  that edited the `.gdt` and forgot the zone line.
- What the Lua route costs: *"you simply navigate to your `<bo3_root>/bin/`
  and overwrite the file `libtiff64r.dll`"* `[community: Modme Wiki,
  Installing L3akMod, https://wiki.modme.co/wiki/black_ops_3/lua_(lui)/Installation.html]`.
  One replaced DLL in the tools' own `bin`, which is exactly the kind of
  install change a generated map cannot carry. A map-level HUD override is
  further constrained even then: *"you must use a different file name as you
  can't override `FILES` at a zone level ... Mods, however, can override any
  lua file"* `[community: Modme Wiki, Overriding A Map Level Hud]`.
- Someone did draw perk icons from GSC in BO3: Wardogsk93's perk set ships
  `scripts/wardog/perk/_wardog_perk_hud.gsc`, and its reported failure is that
  the icons *"always are on top of any stock perks you buy"* `[community:
  Modme 2855]`. This project has not read the file.

</details>

### The bottle

**The drink is a weapon asset, and the perk does not work without one.** The
bottle is the fifth argument of `register_perk_basic_info` and is asserted
present. On purchase the framework takes the points first, gives and switches
to the bottle, and *only then* grants the perk -- and only if the weapon change
completes. So a perk with a broken bottle is not a perk without a drink
animation: it is a machine that charges the player and gives nothing.

**A bottle is a `grenadeweapon`, not a gun.** `isPerkBottle` is a checkbox on
`deffiles/grenadeweapon.awi` and on no other weapon schema, beside
`isFlourishWeapon`, whose tooltip describes the same shape: a weapon that is
given, plays an animation and is taken away again.

**One can be made without importing anything, and it has never been played.**
Every part a new bottle needs is already on the stock asset list: nine view
models and ten world models (`wpn_t7_zmb_perk_bottle_*`), the four view
animations (`vm_perk_bottle_t7_drink`, `_idle`, `_ads_up`, `_ads_down`), the
two generic view-model animations (`viewmodel_zombie_perksacola_idle`,
`_lower`) and the four third-person drink animations (`pt_perkacola_*_drink`).
A new weapon asset is a `.gdt` entity plus one `weapon,<asset>` line in the
map's zone, and that route links clean in a probe map (`zm_test`). What
nobody has done is play one.

**The community has walked into the same wall from the other side.** A perk
whose bottle was wrong presented as *"There is no animation involving the
drinking of the perk / The shader doesn't appear / The actual perk effect
doesn't happen / Player can no longer sprint or knife"*, answered with *"Its
not properly giving you perks weaponfile, thats why you cant sprint/knife and
animation doesnt play"*, and closed with *"I changed it back to the stock speed
cola bottle and now it works fine"* `[community: UGX-Mods thread 14197]`. That
is the code above seen from a play session: the weapon change never completes,
so the perk is never threaded and the player is left in the drinking state.

**The cheap answer is to reuse a stock bottle by name**, which costs nothing at
all: `GetWeapon( "zombie_perk_bottle_cherry" )` in the map's own script is
valid in any map, because the weapon is in the level-common zone whether or not
anything drinks it.

<details><summary>The nine bottles, the assert, and the order of the purchase</summary>

Bottles in `zone_source/all/assetlist/zm_levelcommon.csv:6283-6291`:
`zombie_perk_bottle_additionalprimaryweapon`, `_cherry`, `_deadshot`,
`_doubletap`, `_jugg`, `_marathon`, `_revive`, `_sleight`, `_widows_wine`.
Electric Cherry's bottle is on the list even though its script is a stub.

`_zm_perks.gsc:1825`: `Assert( isdefined( w_perk_bottle_weapon ),
"w_perk_bottle_weapon is a required argument for register_perk_basic_info!" );`

Order, `_zm_perks.gsc:594-620`: `playsoundatposition( "evt_bottle_dispense" )`,
then `player zm_score::minus_to_player_score( current_cost )`, then
`vending_trigger_post_think`, which calls `perk_give_bottle_begin` (`:992`:
`GiveWeapon( weapon )`, `SwitchToWeapon( weapon )`) and then
`evt = player util::waittill_any_return( "fake_death", "death",
"player_downed", "weapon_change_complete", "perk_abort_drinking", "disconnect"
)`. The perk is threaded only `if (evt == "weapon_change_complete")`.
`perk_give_bottle_begin` defaults `weapon = ""` when no bottle is registered
and passes that empty string straight to `GiveWeapon`; what the engine does
with it is **unverified**, and no shipped perk takes that path.

Models and animations: `zm_levelcommon.csv:2066-2084` and `:1342-1345`;
`zm_common.csv:487-490` and `:587-588`. Schema: `deffiles/grenadeweapon.awi:80`,
and `grep -rli perkbottle deffiles/` matches that file only.

</details>

### The effects and the jingle

**Both are names. The effect is free; the jingle is not.** The machine's light
is a handle into `level._effect`, set by the perk's own precache function and
read back by the framework when it plays the effect on the machine, and the
stock perk effects are in the level-common zone, so naming one costs nothing.
The jingle and the sting are sound *aliases*, stamped onto the use trigger as
`script_sound` and `script_label` -- and a usermap does not have the stock
perk aliases. That is not a guess: the community maintains a page called *Fix
The Missing Perk Jingles And Stings* whose whole subject is that they are
missing from custom maps, and whose per-map fix is an `ALIAS` block naming a
`perk_sounds.csv` in the map's own `.szc` sound zone config `[community: Modme
Wiki, Fix The Missing Perk Jingles And Stings]`. So a custom perk that names
`mus_perks_stamin_jingle` gets what a stock machine in a usermap gets:
silence, until the map wires the alias table in.

**What a perk looks like without them: it never turns on.** The machine-think
loop only starts for a perk that registered all three of an alias, a Radiant
machine name and a light effect, and until that loop runs, the buy trigger
blocks forever on a power-on notify nothing sends. That is the same rule as the
host-migration call in the table above, seen from the effects side. The audio
is less forgiving than it looks, too: the jingle thread reads `self.script_sound`
with no guard, so a perk that registers a machine setup and forgets to set it
hands `undefined` to `playsoundwithnotify`.

**Authoring new ones is where the price is.** A new machine light is an `.efx`,
which nothing in this project has built. A new jingle is a new sound alias,
which means the map building its own sound bank -- the one piece of this whole
chain that has already cost this project a failed link.

<details><summary>Where each of those is read, and what ships</summary>

Stock perk light effects in `zm_levelcommon.csv:6810-6823`: `fx,zombie/fx_perk_`
`daiquiri_factory_zmb`, `doubletap2_zmb`, `juggernaut_zmb`, `mule_kick_zmb`,
`quick_revive_zmb`, `sleight_of_hand_zmb`, `stamin_up_zmb`, `widows_wine_zmb`,
plus four `_factory_` variants. Electric Cherry's stub points its handle at a
Black Ops II effect instead, `_t6/misc/fx_zombie_cola_revive_on`
(`_zm_perk_electric_cherry.gsc:97`).

Set and read: `_zm_perk_juggernaut.gsc:68` sets
`level._effect[JUGGERNAUT_MACHINE_LIGHT_FX]`; `_zm_perks.gsc:302` and `:311`
read it back with `playfxontag( level._effect[ fx ], ... )`. The gate on the
whole machine loop is `_zm_perks.gsc:98`, which requires `alias`,
`radiant_machine_name` and `machine_light_effect` all defined.

Jingles: each module's machine setup sets `use_trigger.script_sound =
"mus_perks_<perk>_jingle"` and `.script_label = "mus_perks_<perk>_sting"`
(e.g. `_zm_perk_juggernaut.gsc:90` and `:92`). `_zm_audio.gsc:1607` reads
`alias = self.script_sound` and `:1620` plays it, with no `isdefined` test.
The bump trigger's `zmb_perks_bump_bottle` is set by the framework itself
(`_zm_perks.gsc:1540`).

**Do not read the tools install as evidence that the alias does not exist.**
It ships no stock alias tables -- `share/raw/sound/aliases` holds a `dummy`
folder and a `user_aliases.csv` with exactly one row in it, `test_sound` -- so
`mus_perks_jugganog_jingle` cannot be found anywhere in the mod tools install. It is in the game.
What the install *does* say is that a stock install wires none in:
`find usermaps -name "*.szc"` returns nothing on it.

The published fix is two-sided `[community: Modme Wiki, Fix The Missing Perk
Jingles And Stings; Creating A Custom Perk]`: per map, an `ALIAS` block in the
map's `.szc` naming a CSV, or globally, appending the rows into
`share/raw/sound/aliases/user_aliases.csv`, which is an install change. Either
way the CSV itself lives in the shared `raw/sound/aliases`, so the per-map half
is the `.szc` reference, not the table. Reported failure modes: a doubled
bracket in the `.szc` `"Sources"` array fails sound compilation, a missing
comma after `NONLOOPING` in the CSV fails the parse, and a missing wave file
links as `ERROR: no files for filespec` `[community: Modme 1326, Modme 2381]`.

</details>

### The cheapest honest perk, and what it would cost

A genuinely new perk -- a new effect, its own price and its own prompt, not a
renamed stock one -- is reachable on a stock install without importing
anything, and it is **script plus one struct plus one string**. Everything it
shows the player is borrowed:

| Piece | Cheapest honest choice | Why it is free |
|---|---|---|
| Specialty string | a new one of the map's own, e.g. `specialty_zmf_<name>` | Nothing counts perks or specialty names. |
| Registration | six server calls, in the map's own script, before the framework entry | Already the shape the generator emits scripts in. |
| Effect | the map's own give and take threads | This is the only genuinely new code, and every function it calls has to earn a symbol-table entry. |
| Machine | one `script_struct`, model `p7_zm_vending_nuke` | On the stock list, and nothing else places it: the Electric Cherry stub names it but ships no machine. |
| HUD icon | a setter writing `hudItems.perks.electric_cherry`, and no register function | Registered by the stub in every level, bound in the shipped interface, and its art is on the stock list. It costs the map the ability to sell Electric Cherry, which it could not sell anyway. |
| Bottle | `GetWeapon( "zombie_perk_bottle_cherry" )` | On the stock list. |
| Jingle and sting | `mus_perks_stamin_jingle` / `mus_perks_stamin_sting`, and accept silence for now | What the stub itself uses -- but a usermap has no sound zone config until one is written, so nothing plays until the map pays for the alias table. |
| Machine light | `level._effect["<own name>"] = "zombie/fx_perk_stamin_up_zmb"` | On the stock list. |
| Prompt and name | one `.str` entry the generator already ships | Already solved. |

Cost, honestly: one new script file of maybe a hundred lines, one struct, one
string, and a playtest. No `.gdt` entity, no image, no sound bank, no `.efx`,
no install change. What it does not buy is a picture of its own or a jingle.

**This is built.** `zmforge.script.perks` writes exactly that chain from one
declaration in a recipe, `zm_dmv` ships one -- TAKE A NUMBER, which pays
the holder back at the start of every round -- and check `Z50` holds the five
ways it fails quietly. It came out slightly cheaper than the table above:
**five** registration calls, not six. The sixth is
`register_perk_clientfields`, and it is skipped deliberately. Both sides
register custom perks by walking `GetArrayKeys( level._custom_perks )`, and a
map's own perk cannot enter that array in the same phase on both sides: the
server half can only register in `main()` and the client half is a preload.
Whether the two orders would still agree has not been measured, and a
clientfield the two sides disagree about is a disconnect on join, so the icon
is written straight to its UI-model path instead: no field registered, nothing
to disagree about, and the worst case is no icon. Spec 4.7.2 is the write-up.
**Still nobody has played it.**

**And the one upgrade worth pricing above it.** A picture of its own is a
single image asset away, and it does not need Lua: the `tombstone` key is bound
in the shipped interface to `specialty_tombstone_zombies`, and that image is in
no stock asset list, so a map that ships an image under that name and adds
`image,specialty_tombstone_zombies` to its zone is not fighting anybody for it.
That buys a perk with its own icon on a stock install. It costs one `.gdt`
image entity, which means Windows, because `gdtdb.exe` does not run under
Wine. It rests on a community technique that has not been linked or played
here, the same caveat as everything else in this section.

**A stock perk cannot be hijacked, and this is the measurement that decides
it.** Every `zm_perks::register_*` call keeps the first registration and
ignores later ones, and all nine stock modules register from a
`REGISTER_SYSTEM` preload, which the engine runs *before* the level's `main()`.
So a map that registers `specialty_electriccherry` in its own `main()` changes
nothing at all. What a map's `main()` *can* still reach is the precache
override hook five of the modules expose -- `level.juggernaut_`,
`staminup_`, `widows_wine_`, `additional_primary_weapon_` and
`electric_cherry_precache_override_func` -- which run later and own the machine
models, the machine-light handle and `level.machine_assets`. The drink weapon
is not among them: it is fixed at registration.

<details><summary>The ordering measurement</summary>

`shared/callbacks_shared.gsc:531` is `CodeCallback_PreInitialization`; the
comment above it says the engine calls it after the autoexecs and before the
level's main. It calls `system::run_pre_systems()` at `:534`.
`shared/system_shared.gsc:19-20` says the same of the preload function every
`REGISTER_SYSTEM` line declares: it runs in the first frame, during level load,
before `_load::main`. Each stock perk module's
`__init__` makes its `register_perk_*` calls there
(`_zm_perk_juggernaut.gsc:39-53`).

First-wins: `_zm_perks.gsc:1903`, `:1959`, `:1964`, `:1994` and their
neighbours are all `if ( !isdefined( level._custom_perks[ str_perk ].<field> ) )`.

The precache functions run later, from `default_vending_precaching`
(`_zm_perks.gsc:172-184`), called by `zm_perks::init` (`:40`) through the
framework entry, which is why a hook set in the map's `main()` is still in time.

</details>

# Part 6: lighting

## Why brightness is relative: the camera exposes automatically

This is the mechanism, and Treyarch documents it, though never for zombies.

- A light's brightness is set in `stops`, not in an absolute unit. The default
  is 11 `[Treyarch doc: Lighting_Parameters.pdf]`.
- The scene's exposure floats. `evauto` on the worldspawn turns on auto
  exposure, bounded by `evmin`, `evmax` and `evcmp`, with a set of those per
  lighting state `[Treyarch doc: same]`.
- So a light's absolute value decides nothing. What decides how it reads is its
  value **relative to the exposure the scene settles on**, which the sun and
  sky drive.

Treyarch's own multiplayer workflow document says to work that way explicitly:
lock exposure where sunlight looks right, then light everything else relative
to it, so that an interior that should look dark looks dark *at the exterior's
exposure* rather than letting exposure chase it `[Treyarch doc:
Multiplayer_Lighting_Workflow.pdf]`. Their numbers:

- Exposure is always set within 8 to 12 stops, stated as a hard number, so that
  effects do not have to be authored per map.
- Average dynamic range across a map is 1.5 stops. Some maps reach 2.5, with
  gradual transitions and no line of sight across the shift.
- Interior to exterior is usually a 1 stop drop. A second interior with no
  exterior visibility can go to 10 or 10.5 from 12.
- **2 stops below scene exposure is where player visibility becomes a problem.**

The same relativity shows up in materials, which is the clearest single proof.
An emissive material's HDR scale is `2^EV` of the area the prop sits in, given
with a worked example `[Treyarch doc: Materials.pdf]`. And effect materials
carry a "physically based emissive" toggle described as making the material
emit one consistent value **instead of adjusting to stay visible across EV
values** `[Treyarch doc: same]`. By default, emissive brightness tracks
exposure. The toggle opts out.

That document also gives the only cross-reference between the two brightness
scales in existence: effect intensity runs 0 to 12,000, with light glows at 16,
fires at 256 and the sun at 10,000, and it states that this is the same value
lights use `[Treyarch doc: Materials.pdf]`. No conversion to `stops` is given
anywhere `[unknown]`.

## What that means for a zombies map, measured

A lamp's `stops` value is log base 2 of the emitter's intensity. The shipped
values give it away: Treyarch's zombies lighting prefab carries
`4.64385618977472`, which is log2 of 25, and `9.96578428466209`, which is log2
of 1000 `[measured]`.

The exposure it is judged against comes from the map's sun and sky preset. That
preset is named on the worldspawn and on `volume_sun` by the `ssi` key, and
each preset carries its own `ev` `[measured]`.

Exposures measured off the shipped presets `[measured]`:

| Preset | `ev` |
|---|---|
| `zm_zod` | 4.0 |
| `zm_factory` | 5.0 |
| `default_night` | 6.0 |
| `default_sunset` | 12.5 |
| `mp_sector` | 12.75 |
| `default_morning` | 13.5 |
| `default_day` | 15.0 |

Where the shipped lamps sit against their own map's exposure `[measured]`:

| Map | Preset | `ev` | Lamp stops |
|---|---|---|---|
| The Giant | `zm_factory` | 5 | 543 lamps peaking at 4.64 and 5.64, running to about 10 |
| `mp_sector` | `mp_sector` | 12.75 | 275 lamps peaking at 15 and 16, band 13 to 17 |

**The rule: a lamp's stops belongs at its map's exposure, give or take a few
stops up.** Roughly `ev - 0.5` to `ev + 4.5`.

The cost of getting it wrong is the largest single number in this document.
A fixed `stops 4` under a `default_day` sky at `ev` 15 is eleven stops under
shipped practice. That is 2048 times too dark, and a map built that way plays nearly black
`[measured]`.

There is no ambient term to rescue it. `volume_sun` carries a global fill
colour pair, and across all of the roughly 730 shipped `.map` files it appears
four times and is black every time `[measured]`.

## One lamp does not light a hall

Treyarch's zombies lighting prefab puts 536 non-skybox lamps across 4304 by
6389 units, which is one lamp per 226 by 226 patch `[measured]`. A generator's
first large map ran one per 521 by 521 and was too dark `[measured]`.

A lamp inside or above the ceiling slab illuminates nothing.

That density rule is derived from shipped practice, and it may be measuring the
wrong variable. A light's reach is its `radius`, default 100, not its spacing
`[Treyarch doc: Lighting_Parameters.pdf]`. A lamp 200 units up at the default
radius lights nothing regardless of how the lamps are spaced `[community]`.
Our own generator runs radii of 340 to 900 against the shipped 5 to 350
`[measured]`, so spacing and radius have been compensating for each other here.
Which of the two is the real constraint is `[unverified]`.

Treyarch's culling document names two more keys on a light, `culling_cutoff`
and `culling_falloff`, both measured in onscreen pixels at 1080p, and gives 200
and 300 as the generic pair, with 1 and 5 for a small light of radius under 10
`[Treyarch doc: Culling_LOD_Lights.pdf]`. Both default to 0. 427 of the 543
lamps in their own zombies lighting prefab carry them at exactly 200 and 300
`[measured]`. What the engine does with a lamp carrying neither is `[unknown]`.

Shadows are the expensive part, and Treyarch gives a budget: 12 live shadows at
normal resolution, or 3 at double resolution, because doubling the map costs
four times the memory. Omni lights do not support soft shadows at all
`[Treyarch doc: Lighting_Parameters.pdf]`.

That budget is spent by two keys, and both are easy to get wrong.
`volume_sun`'s `shadowSplitDistance` is how far the dynamic sun
cascade reaches, and since the cascade's texture is a fixed size, the further
it reaches the coarser every sun shadow edge gets -- which on a stair flight
reads as a hard saw that moves with the camera. `worldspawn`'s
`numOmniShadowSlices` is how many lamps may have a run-time shadow at once;
past that number the engine picks winners by where the player is standing, so
shadows come and go as he walks. Neither key has a safe default: the shipped
value of the first is 2000 and **none of Treyarch's three sun volumes uses it**
(The Giant takes 900 over two splits, the two multiplayer maps 1200 over three),
and the second ships at 24 while The Giant raises it to 96 and still lets only
42 of its 280 omni lights cast at all `[measured]`. The lesson generalises: a
lamp asking for a shadow is a cost, so most lamps should be emitted
`PRIMARY_NOSHADOWMAP 1` and only the ones that were placed to cast should cast.

## Power switches change lighting states, they do not toggle lights

There is no script call to turn a light on or off. No `SetLightIntensity`, no
light-entity call anywhere in the shipped script tree `[measured]`.

What exists instead is lighting states. The sun volume carries up to four sets
of state keys, switchable at run time `[Treyarch doc:
Sun_Sky_Light_Setup.pdf]`. Each light entity has a flag per state saying
which states it appears in. The documented power-switch pattern is a loop that
waits on the `power_on` flag, calls `util::set_lighting_state(0)`, waits on
`power_off`, calls `set_lighting_state(1)`, and recurses `[Treyarch doc:
Phabricator setup_power_switch]`. State 0 is powered, state 1 is unpowered.
The page notes both states can point at the same preset if the lighting is not
meant to change visibly.

What states 3 and 4 are for is documented nowhere `[unknown]`.

One off-by-one to know before wiring a switch: Radiant's lighting state N is
the script's lighting state N minus 1 `[community]`. That is consistent with
the published power-switch pattern, where the powered state is 0 in script.
Reusing one override preset across two states makes Radiant refuse to build the
second one, so each state wants its own `[community]`.

Two further mechanisms worth knowing, because they explain why a bake looks
wrong rather than dark:

- **The sun volume is the global reflection probe.** It has to be a six-sided
  box, cannot be rotated, cut or split, and cannot overlap another one
  `[Treyarch doc: Sun_Sky_Light_Setup.pdf]`. Its `grid_density` is relative
  to its own size, not to world units.
- **Baked and displayed sky can differ.** `ssi` is what bakes into the probes,
  `ssi<n>_runtime_override` is what displays. The documented use is baking with
  a neutral sky so global illumination does not turn the level blue, while
  displaying a saturated one `[Treyarch doc: same]`.

## Reflection probes have an upper density as well as a lower one

Radiant casts random rays from every lighting grid point and reads colour only
from rays that reach a nearby probe. Sampling stops at the **eight nearest
probes** `[Treyarch doc: Reflection_Probes.pdf]`. So crowding an area with
probes can leave the bake without one that sees a point, which makes too many
probes a defect and not merely waste.

A probe also holds six reflection planes at most, so the six walls that matter
have to be chosen `[Treyarch doc]`. Treyarch's zombies prefab carries 176
probes, sized to their rooms rather than left at a constant: 166 distinct
sizes, median 113 by 125 by 105 `[measured]`.

A probe is not only about gloss. It carries the bounced light, so without one
the indirect lighting from the sky preset does not show at all `[community]`.
An undersized probe box leaves a hard brightness seam at its boundary after the
bake, and an alcove wants its own `[community]`.

What the bake does with a probe cannot be checked in an automated chain, so
no rule judges a probe's look. What is checked is coverage: the emitter writes
one `reflection_probe` per room with its box sized to that room, and check
`Z28` fails a room that no probe box encloses.

## Three other ways a map renders wrong

- **No umbra volume: walls render as sky.** Without one the compiler defaults
  occlusion to a million-unit cube. It prints a line about it and exits 0
  `[measured]`. A map also wants exactly one `volume_sun` and a sky shell of
  six slabs with no gap.
- **Caulk on a terrain patch renders black.** The compiler prints its own
  banner and still succeeds `[measured]`.
- **No bake: the map is washed out.** The linker logs that it could not load
  the lighting export data and is falling back to preview lighting. The map
  builds, loads and plays `[measured]`. Photographed textures cannot be judged
  for brightness until it is baked. A solid black sky in game is the same
  symptom, not a broken sky shell `[community]`.
- **A stale bake looks like a lighting bug.** Any change to a light, a sky
  preset or a probe invalidates the export, and the old shadows stay until it
  is rebuilt `[community]`.
- **A patch is one-sided.** Wound the wrong way it is invisible from the other
  side, and a fully reversed patch is simply absent in game with no build
  warning `[community]`. That is consistent with our own measurement that a
  brush face's normal points into the solid.

---

# Part 7: scripting

## The seam is narrow and its ordering is load-bearing

A map's server script does five things and nothing else has to happen in it:

1. `#using` lines for the modules it calls.
2. `#precache` lines for effects.
3. `main()`, which sets a few level variables, calls the framework entry, and
   starts the zone manager.
4. A zone hook function, which declares the flag-to-zone graph.
5. Whatever custom logic the map wants, hung off the framework.

`main()` has four distinct windows, and which window a statement lands in
decides whether it works `[measured]`.

| Window | What belongs there | Why |
|---|---|---|
| Before `zm_usermap::main()` | `level.dog_rounds_allowed`, `level._zombie_custom_add_weapons` | The framework applies its own default only while the variable is undefined, so afterwards is too late |
| After `zm_usermap::main()` | `level.player_too_many_players_check` | The framework assigns it during the entry and reads it later, on player spawn |
| After that | `level.zone_manager_init_func`, the `init_zones` array | The zone manager reads both when it starts |
| Last | `level thread zm_zonemgr::manage_zones( init_zones )` | It has to see a filled array |

The `DEFAULT` macro is the mechanism behind the first row. It assigns only
while the target is undefined `[stock script]`. That is the whole reason
ordering matters, and it is worth knowing as a pattern rather than as three
separate rules: **anything the framework `DEFAULT`s, a map must set earlier.
Anything the framework assigns outright, a map must set later.**

The client script is shorter. Its `main()` has to call the framework's client
entry. Without it the server and client disagree about registered client fields
and the join is dropped `[measured]`.

## What the framework lets a map override

The hooks are function pointers on `level` that the framework calls if defined.
The ones read out of the stock scripts here include the weapon table loader,
the zone manager init function, the max-zombie function, the custom round spawn
function, the spawner selection function, the zone occupied function, and the
out-of-playable-area override `[stock script]`. A map assigns one and the
framework calls it in place of its own.

That is the supported way to change behaviour. Editing the framework's own
scripts is not available to a usermap, because a usermap does not ship them.

## The language, in the parts that surprise people

All from Treyarch's own language document `[Treyarch doc: GSC_Language.pdf]`.

- **`#using` does more than resolve names.** The file it names is incorporated
  into the runtime script set, so anything it pulls in gets a chance to execute
  even with no call into it. That is how a usermap that does nothing still gets
  stock systems registered.
- **A `#using` below the first function declaration is a syntax error.**
- **An unqualified call resolves in the current namespace, then falls back to
  `sys`, the engine builtin library.** That is why a call to a function nobody
  wrote compiles cleanly.
- **A file with no `#namespace` takes its filename as its namespace.**
- **`#insert` is textual.** Inserted content reports every error at the single
  line the insert sits on, which makes a macro bug hard to locate.
- **`autoexec` on a function runs it just before the level entry point**, in an
  order the document says is undefined and must not be relied on.
- **`#precache` types are a closed list**, and a map's effects have to be in it:
  `fx` on the server side, `client_fx` on the client side, alongside `model`,
  `weapon`, `material`, `string`, `menu` and the rest.

The combination of the third and fourth rules is the whole hazard. A call to a
function that does not exist compiles. The failure arrives when the line runs,
and it kills the map. A missing semicolon behaves the same way.

## Reading a script error is a build-time decision

Script debug information lives inside the built fastfile, not in the game
`[community: UGX]`. The base game ships none.

The consequence is sharp: **a runtime error raised inside one of Treyarch's own
`_zm_*` scripts will not resolve to a line unless you added that script to your
own zone file.** Most zombies errors originate in stock scripts, so a map that
wants readable errors packs the stock scripts it suspects.

Turning on the output at all is `developer 1` or `developer 2`, and `logfile`
writes the console to the current mod folder `[community]`.

The script API reference Treyarch ships documents 2,332 engine functions, each
with a signature and a Client or Server tag `[Treyarch doc:
bo3_scriptapifunctions.htm]`. Counted off an index of it: 1,684
Server, 511 Client, 137 Both `[measured]`.

That tag is not reliable. 132 distinct Server-only-tagged names are called from
`.csc` client scripts across the shipped tree, one of them in 24 files
`[measured]`. The reverse direction holds much better, with five Client-tagged
names in `.gsc`. Treat the column as a hint, not a gate.

The signatures are also less useful than they look. Every one of them reads
`void`, including obvious value-returning functions, so the reference gives
arity and existence and not types `[measured]`.

## The script-pack question, settled narrower than the community states it

The community rule is that a pack's `#using` belongs in both the `.gsc` and the
`.csc`, and that one alone gives a clientfield mismatch at launch `[community]`.

Blind syncing does not work. The mod tools' own template does not keep the two
sets in sync, the framework pair is 50 lines against 35, and two zombie modules
have no `.csc` at all on the mod tools install, so a synced set would not compile
`[measured]`.

The narrower rule we believe: **only a pack that registers client fields needs
both sides, and only the pack knows that.**

A loose script needs three artefacts, not two: the `#using`, the
`scriptparsetree` line in the manifest, and the entity it looks for by
`targetname` `[community, half confirmed]`. The third is unknowable from
outside the pack, which is why it cannot be checked and has to be playtested.

---

# Part 8: assets, and the several places a missing thing is silent

## Three registries, and all three have to agree

An asset reaching the game passes three gates. Missing any one of them
produces a different silence.

| Gate | What it is | What a miss looks like |
|---|---|---|
| Asset database | A `.gdt` entity, indexed by `gdtdb.exe /update` | The linker cannot resolve the name. Loud for images, silent for models |
| Zone manifest | A line in `<map>.zone` | The asset is not packed. The map reaches for it at run time and dies |
| Script precache | `#precache("fx", ...)` in the `.gsc` and `#precache("client_fx", ...)` in the `.csc` | The asset is packed and the game has no handle. Whatever plays it renders nothing and reports nothing |

The third gate is the one people do not know exists. Assigning
`level._effect[x] = "<path>"` is a name, not a registration. Treyarch's own raw
sources do the precaching in both files with the two different spellings
`[measured, confirmed against a shipped map's .gsc and _fx.csc]`.

`.gdt` shape, for completeness `[measured]`: no header or magic, one anonymous
brace block, entities two levels deep, LF line endings, backslashes in paths
doubled, and the asset name is a global unique key across all GDTs. There is no
required `zm_<mapname>.gdt` `[measured]`, despite folklore to the contrary.

## A fourth gate, for replacing something stock

A map that wants to replace a Treyarch script rather than add to one has to
stop the stock one being packed. The published route is to comment out its
`scriptparsetree` line in `zone_source/all/assetlist/zm_patch.csv` and then
pull the replacement in through the map's own zone file `[Treyarch doc:
Phabricator, the alternate box and Pack-a-Punch pages]`. Every community pack
that swaps a stock system does exactly this.

That is worth knowing even if you never do it, because it explains why two
asset packs installed together produce duplicate-asset link errors often enough
that a community tool exists solely to parse those errors out of linker output
`[community]`.

A related case is text that shows as an ALL-CAPS token in game, usually
starting `ZOMBIE_`. That is a localized string the map's fastfile does not
carry, and the published fix is a single manifest line, `localize,zombie`
`[Treyarch doc: Phabricator adding_the_missing_localized_strings]`. That line
packs Treyarch's existing string table. **Defining a string of the map's own is
a separate thing, and it works**: `localize,<name>` against a hand-written
`share\raw\english\localizedstrings\<name>.str` links clean `[measured]`. Part 5 has the measurement.

## Where silence is by design

Three things people expect to be asset pipelines and are not.

**The loading screen is two loose files.** `loadingimage.png` and
`previewimage.png`, dropped flat in `usermaps\<map>\zone\` `[measured]`.
Neither is a fastfile asset. A link log mentions `png` zero times and `image`
zero times, which is what "not an asset" looks like `[measured]`.

The mod tools' template puts them at 1920 by 1080 and 600 by 340, 8-bit,
colour type 2, no interlace. **Only the first of those is a constraint.** Of 40
published Workshop maps surveyed, all 38 that carry a loading image are
1920 by 1080, but only 23 of 39 preview images are 600 by 340, and the rest run
from 600 by 338 to 3126 by 2027 `[measured]`. 17 of the 38 loading screens and
19 of the 39 preview images are 32-bit with alpha, and one preview image is
8-bit palette `[measured]`. Alpha and palette both
survive to a published, playable map, so the template's numbers are a template
and not a requirement.

Neither the template's size nor its colour type is a rule: `P2` checks that
the file is there and parses and nothing else, `P1` warns rather than fails on a size other than
1920 by 1080, and the specification's §6.1 and §9.7 say the same.

An unresolved defect sits here. The preview image shows on the map-selection
card. The loading image does **not** appear for a local map load, despite
matching every published map's format, size and location.

The best current explanation is that the two are not the same mechanism. The
video tutorials describe the loading screen as an **asset override**, not a
loose file: repoint the stock image asset named `black` at your PNG in the
asset editor, comment out its row in `zone_source/all/assetlist/core_gfx.csv`,
and add `image,black` to the map's own manifest `[community]`. That would
explain the split we see, with the menu card reading a loose file and the
in-game loading screen reading an asset.

Three things keep it a hypothesis rather than an answer.

- The route has a known cost. The `black` image is used by HUD elements, so
  overriding it has been reported to put the loading screen in odd places
  `[community, contested in its own thread]`.
- It mutates shared install state. The `black` asset and the `core_gfx.csv`
  edit are global, so building two maps on one host would have the second
  clobber the first `[community]`.
- Published maps ship the loose PNGs and no such manifest line `[measured]`.

The install also declares stock placeholder assets for both images that no
shipped zone file references, which may be the intended override target instead
`[unverified]`. What settles this is one build with the override in place.
Nothing here has run it.

**Custom sound builds from the command line.** A `.sz` is CSV text: Treyarch's own shipped `mp_sector.all.alias.sz` has a
102-column header and 646 plain rows `[measured]`. Writing the file is
building the bank, and the asset editor is not in the path.

The bank goes in `share\raw\sound\zone\` under the map's own name, with at
most 104,729 rows, every required column filled, and the wave file under
`sound_assets\` at 48 kHz signed 16-bit PCM. Proved by building
`zm_test`: link with no `ERROR:` line, and
`sound,zm_test.all` in the packed asset list `[measured]`. Whether the
alias is audible in a session is `[unverified]`: nobody has heard it. The
detail is in `playable-map-requirements.md` and spec section 6.2.

Treyarch's sound document is the only account anywhere of the `.szc` alias
format, with all 78 columns and their defaults `[Treyarch doc:
Sound_Mod_Docs.pdf]`. It names `sound,<mapname>` as the manifest line. The
model it describes is what the bank implements:

- A script names an **alias**, never a file. The alias is the abstraction that
  lets the file or its parameters change without touching the trigger.
- Two randomisations fall out of that. Several aliases with one name in one
  sound zone are a random pool, and a folder name in the file spec makes the
  engine pick a random file from it.
- `Secondary` chains one alias to another, so a single trigger can result in
  anywhere from zero to ten sounds depending on chaining and which banks loaded.
- Loaded sounds go into `.sabl` banks, streamed ones into `.sabs`.

That document contradicts itself on where source files live, giving the path
root as the install's `sound_assets` in one section and
`share\raw\sound\aliases\` in another `[Treyarch doc, internally
inconsistent]`. A map maker cannot resolve it from the documents.

**Localized strings ship no source on the mod tools install.** No `.str` file
exists anywhere to copy `[measured]`, so a map that wants its own strings
writes one. A `localize,<name>` line against a hand-written `.str` links clean
`[measured]`; Part 5 and spec 5.7 carry the measurement.

## Prop collision is two keys and two files

Two keys on a `misc_model` decide whether the compiler bakes its collision map
into the static BSP. The mod tools' own entity definition describes them as the
switch `[Treyarch doc: bin\t7.def.json]`. One turns it on, the other turns it
off.

Measured on Windows `[measured]`: six props linked with collision off and the player walked through all six. The same map with the key
set compiled to 97,556 bytes against 95,708, which is 1,848 bytes of static
collision for six boxes. `cod2map` prints the word `collmap` zero times in
either log, so the size delta was the only evidence there was.

The other direction is a real cost, not just waste. Baked collision on scatter
props is what takes the navmesh out and stops zombies at a plant pot
`[unverified]`. Only the prop library knows which props are meant to be solid.

There is a second half to this that our own checks do not cover. A model
arrives with no collision by default, and the common practice is to build a
clip volume around a placed prop by hand rather than to rely on the model's own
`[community]`. So a prop can be solid two ways, and we only test one of them.

Separately, a prop's asset database entry names two collision files by string,
a `_col.XMODEL_BIN` bullet mesh and a bare collmap filename. The text export
comes from the model chain and the binary comes from `export2bin`. When the
binary is absent the linker reports it **against the model**, not against the
collision, which is why it reads as an unrelated failure `[measured]`.

## Compiler and linker ceilings

The community reports several, with their error strings `[community]`:
3,072,000 map triangles, 64 winding points per brush face, 32,768 windings per
concave group, 262,144 curve and terrain collision vertices, and a map-node
limit printed with no number.

One correction from measurement. `MAX_MAP_TRIANGLES` counts **world brush and
patch** triangles, not model triangles. A generated map whose props come to 2.16
million model triangles compiled with the compiler reporting a set of 7,640
`[measured]`. Model triangles are xmodel assets and are bounded per
model.

Two community-reported limits are not worth carrying, because their own
authors do not stand behind the numbers: weapon lines per zone file, reported
as 309 in one thread and 1536 in another, and sound aliases at 2000, hedged in
one thread and disproved as a cause in a third `[community, unverified]`.

---

# Part 9: designing a map that plays well, not one that merely loads

Everything above is about correctness. This section is about the map being
worth playing, and it follows from the same mechanisms.

## Design the zone graph first, not the geometry

The zone graph is the game. It decides where zombies come from, where the
player may stand, and what a door is worth. Rooms are how the graph is
expressed.

- **One zone per space a player can be alone in.** A zone is the unit of
  "where the horde comes from right now".
- **Volumes to the outer box, overlapping through walls.** Not for tidiness.
  For the 3-second monitor.
- **Every zone gets spawn locations.** A zone with none is dead ground the
  moment its door opens, and the round waits rather than failing.
- **The starting zone is the one in `init_zones`.** Everything else is reached
  by a flag.

## Spawn locations decide the shape of a fight

The live cap is 24 zombies `[stock script]`. Where they appear is drawn at
random from the active zones' pooled locations, once per spawn.

- **Locations behind the player make a room a fight. Locations ahead of the
  player make it a corridor.** The framework does not care which. The layout
  does.
- **Barricade windows are the pressure valve.** A zombie crossing one plays an
  animation and is briefly stationary. A room with four windows plays
  differently from a room with one wide opening, for reasons the round counter
  never shows.
- **Spread locations across the zone.** A single riser feeds 24 zombies through
  one point, which is a queue rather than a horde.

## Train the map, which is what makes rounds survivable

The standard zombies loop depends on the player being able to walk a closed
route while the horde follows. That needs, from the geometry:

- A loop, not a dead end. A dead end at 24 live zombies is a down.
- Corridors above 31 units so the walkers path at all. Treyarch's own minimum
  for a hallway is 96, and 128 where there is combat, so 31 is the cliff and
  not the target.
- No step over 18 units on a route zombies have to take.
- No slope over 46 degrees on terrain they have to cross.
- Pinch points kept short. Treyarch's rule is 64 wide minimum and no deeper
  than 64, ideally 32.

The whole dimension table is in Part 4. Design to it, not to the navmesh
thresholds. The thresholds are where the surface disappears.

A platform a player can stand on and a zombie cannot is a map-breaking
exploit if it is on the route, and a piece of furniture if it is not. The
geometry does not say which. The generator lays no navmesh more than one step
up `[measured]`, so this is a decision the map's author makes and the tools will
not question.

## Price the map, not the weapons

A map's economy is three numbers: the first door, the first perk, and the box.
The stock defaults are a starting point, and the mystery box's default cost is
950 `[stock script: _zm_magicbox.gsc:142]`.

What a map can change is the price. What it cannot change is the prompt text
`[measured]`. So the first weapon on the wall is a design decision about what
the player reads, not just what they get.

## Light the map to its sky, then judge it baked

- Pick the sky preset first. Everything else is relative to it.
- One lamp per 226 by 226 units of floor is the shipped density `[measured]`.
- Nothing can be judged for brightness until the bake has run `[measured]`.
  Preview lighting is washed out by construction.

## Publishing

Two steps come from Treyarch's own guide rather than from the tools
`[Treyarch doc: Steam guide 770558798]`:

- Delete the `.xpak` files from the zone folder before uploading.
- Select every language in the tools' options, or the map works only for
  players whose language matches the author's.

Both failures appear only on somebody else's machine.

What a published item actually is, surveyed over a sample of 46 Workshop items
`[measured]`:

- **The item is the `zone` folder, uploaded flat.** No `zone_source`, no
  `.map`, no `.gsc`, no `.gdt` appears in any of them. The upload is the
  folder rather than a curated list, which is visible in the editor backups and
  stray logs that rode along.
- **A finished map ships 13 fastfiles**, the base plus 12 language prefixes, in
  35 of 46 items. The other 11 ship English plus base and are also fine.
- **Audio does not live in the fastfile.** It ships as loose `.sabs` and
  `.sabl` banks under `snd\<language>\`, in 45 of 46 items. Every non-`all`
  language bank is exactly 2048 bytes, so the real audio is in one bank and the
  rest are placeholders. Our own maps ship no banks at all and play, so these
  are how custom audio arrives rather than a load requirement.
- **Eight items ship a loading video**, an `.mkv` or `.mp4` named for the map
  and sitting beside the static loading image. That a `_load` video plays, and
  what the engine needs to play it, is `[unverified]`. The naming convention is
  the evidence, not the behaviour.
- **Scale.** The median published map is 6.23 GB, of which the `.xpak` is 89%.
  The median fastfile is 233 MB. Our own built maps come to under 250 MB total,
  because they carry no custom audio and one language.

---

# Part 10: what we genuinely do not know

These are collected so nobody spends a day assuming one is settled. Each is
either `[unknown]` or `[unverified]`.

**Numbers and engine behaviour**

- The player's real collision width. Three sources give 30, 31 and 32.
  Clearing 31 satisfies all three, which is a workaround, not an answer.
- The engine's real step limit for a player. There is no step dvar in the
  shipped scripts. 18 is the navmesh generator's number, not the player's.
- The unconditional values of `jump_height`, `bg_fallDamageMinHeight` and
  `bg_fallDamageMaxHeight`. The readable ones sit inside an old-school mode
  branch, and the shipped configs only reset those dvars.
- Whether `IsTouching` accepts a hull and a volume meeting exactly on a plane.
- What the engine does with a lamp carrying neither `culling_cutoff` nor
  `culling_falloff`.
- The dimensions of the `zm_collision_perks1` clip, which is what actually
  stops a player walking into a perk machine.
- The units of `maxWalkableSlope`. 46 is almost certainly degrees and the file
  does not say.
- How navmesh seed points are placed, which `pruning.minDistanceToSeedPoints`
  depends on.
- Which entities path on the nav volume rather than the mesh. The compiler's
  warning says flying units and nothing elaborates.
- Any conversion between a light's `stops` and the 0 to 12,000 effect intensity
  scale. Treyarch's material document says they are the same value and gives no
  table.
- What lighting states 3 and 4 are for. Two exist in every documented workflow.
- Whether a lamp's reach is governed by its `radius` or by lamp spacing. Our
  density rule and our radii have been compensating for each other.
- Whether `get_current_zone`'s answer in an overlap has any consequence a
  player sees. That it is order-dependent and sticky is read out of
  `_zm_utility.gsc:3614`; which of its five callers cares is not settled. (Whether
  volumes of different zones may overlap is answered above: they may, and
  `zm_giant` does it 11 times.)
- The exact key name for the door flag that lets navigation reconnect across an
  opened door. It is a checkbox in the editor and no transcript spells it.
- Whether the wall buy's origin really belongs 8 units below the floor surface.
  One play session put it there, and nothing corroborates it.

**Toolchain**

- Why the loading image does not appear for a local map load, when the preview
  image does and both match published practice.
- What image the engine draws for a usermap with no `loadingimage.png`. The
  observed symptom is a black screen.
- What `cod2map64` does with exponent notation in a `.map` number. No shipped
  map contains one and the cost of finding out is a broken build with no
  diagnostic.
- Whether the asset editor can be driven without a person at the keyboard,
  which is what stands between this chain and custom sound.
- Which stage writes the `.xpak` files.
- Why a Wine compile's BSP differs from a Windows compile's in 3 of 25 lumps
  and is 152 bytes shorter, when two Wine compiles are byte-identical to each
  other.
- Whether a Wine-baked map looks right in game. Windows and Wine builds
  produce different-sized lighting exports.
- Which tools version the measurements here were taken on. The changelog stops at 2016-10-06 and the
  wikis reference two later versions Treyarch never documented. This matters
  because one wiki page says a zone fix stopped being necessary at one of them.
- Where sound source files are meant to live. Treyarch's own document gives two
  different path roots in two sections.
- Whether overriding the stock `black` image asset is what draws a local map's
  loading screen. One build would settle it.
- Whether a loading video plays, and what the engine needs to play one. Eight
  published maps ship a file named for it. The naming is the only evidence.
- Any map-wide budget for triangles, brushes, draw calls or models. No video
  across six years states one, so our limits table rests entirely on forum
  error reports.

**Format**

- The meaning of the sixth texture field on a brush face. Non-zero only on
  skewed faces, tiny magnitudes, no source.
- The meaning of `T1` and `T2` in a patch's dimension line.
- Whether per-vertex colour in patches is real. Zero of 41 real patch blocks
  carry it.
- Whether prefab layer declarations are required for prefab loading. Real maps
  reference prefabs only through `misc_prefab`.
- Four header bytes in the Havok tagfile that are identical in every file
  measured so far, and a per-column marker byte in the same format. Both asserted
  rather than interpreted.
- How a float column is encoded in that tagfile. No sample we have carries
  one.

Two entries are settled and are not on the list, both by measuring the mod
tools' own `map_source` rather than by argument:
`weaponClip` and `ai_nosight` are real contents tokens, at 19,553 and 7,044
occurrences across 733 shipped `.map` files, every one on a `contents` line.
The token table in `mapsource-format-reference.md` holds the counts and the
combinations. What they are *for* is a separate question, and the collision
twin they were thought to build does not exist.

**Gameplay claims not yet played**

- Whether an inactive zone kills a player who enters it. The wiki's own author
  hedges.
- Whether dog spawners are needed in every zone with dog rounds disabled, for
  Zombie Blood and solo Quick Revive pathing.
- Whether the always-on flag pattern is better or worse than the community's
  zone contract. Neither has been playtested against the other.
- Whether a map's never-unlocked `player_respawn_point` breaks coop relocation
  and revive placement.
- Whether remapping the spawner class fixes the community's invisible,
  unkillable zombies. The weapons said to cause it are not on the mod tools install.
- Everything about eight-player lobbies. The whole finding is a reading of
  scripts.

---

