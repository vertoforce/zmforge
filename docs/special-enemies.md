# Special enemies in a usermap

**Short answer: a Panzer Soldat final boss is achievable, but only with a community port. Stock Treyarch assets cannot do it.** The mod tools ship the Panzer's behaviour script (`scripts/shared/ai/mechz.gsc`) and the engine knows the `mechz` archetype, but no aitype, character model, animations or state machine for it. A link test proved it: adding `aitype,zm_tomb_mechz` (or the castle/genesis names) to a zone fails with "is not a valid aitype asset". The same is true for Margwa, Raz (Mangler), Thrasher, Fury, Keeper, sentinel drone, parasite, spider and wasp.

The community fills the gap with ports made from assets extracted out of the game with Scobalula's tools. The one still downloadable is **Spiki's asset dump** (Panzer, Origins Panzer, Margwa, Mangler, Thrasher, Fury, Keeper, sentinel, spiders, wasps, raps). Its spawn script is plain: one spawner entity plus a struct, then `mechz_spawn( struct )`, and a `waittill("death")` for the death hook. Using it is a project decision: it ships ripped Activision assets under informal terms (see Licence below), and nobody has yet downloaded it in full and built it into a generated map.

The hellhound is still the only special enemy that works with stock assets alone. See the dog section below.

The options:
- **Panzer final boss via Spiki's pack**: download the 1.47 GB base pack, install its GDTs and scripts into the tools, link one probe map, then wire the boss. Terms say no low-effort maps and no reposting.
- **Stock-only fallback**: a buffed ordinary zombie as the boss, or a hellhound.
- **Unknown**: the "Additional Assets" DLC (Steam app 499270, 104.5 GB) is off in a default tools install. Spiki says it is needed for his spiders, wasps and Margwa. Whether it adds anything for the Panzer is unverified.

<details><summary>Link test: stock mechz aitype names</summary>

A scratch usermap (a compiled bsp and empty scripts), linked with the Wine linker (`docker/bo3-wine/scripts/wine-tool.sh 'bin\linker_modtools.exe' -language english -modsource <map>`), then deleted. Zone lines tested:

```
aitype,archetype_zm_factory_zombie_dog
aitype,zm_tomb_mechz
aitype,zm_castle_mechz
aitype,zm_genesis_mechz
aitype,spawner_zm_tomb_mechz
```

Linker output, verbatim:

```
^1ERROR: 'zm_tomb_mechz' is not a valid aitype asset
^1ERROR: 'zm_castle_mechz' is not a valid aitype asset
^1ERROR: 'zm_genesis_mechz' is not a valid aitype asset
^1ERROR: 'spawner_zm_tomb_mechz' is not a valid aitype asset
```

The dog aitype was accepted as an asset; it then failed on files missing from a tools tree without its bulk source (`Could not find xmodel file: t7_characters\zombies\hellhound\c_c_zom_der_hellhound_LOD0.XMODEL_BIN`, `xanim 'ai_zombie_base_dog_death_hit_back' not found`). Both files ship with the mod tools as bulk source, which a tools tree may not carry in full. The linker builds from source GDTs only; it does not pull assets out of the game's fastfiles.
</details>

<details><summary>What the mod tools carry, and the DLC</summary>

- The engine side is there: the aitype editor's archetype list includes `margwa | mechz | thrasher | raz | keeper | apothicon_fury` (deffiles/aitype.awi:91), and `share/raw/animtables/ast_definitions.json` has mechz mocomps (`mocomp_tomb_mechz_traversal@mechz`).
- None of the 362 shipped `.gdt` files declares a mechz, margwa, raz, thrasher, sentinel, parasite or spider asset (grep).
- The whole tools tree, bulk source included, searched by file name for `mechz|margwa|panzer|thrasher|zm_tomb`: only the shared scripts, `.duk` sound files and 17 Margwa "smash react" anims for ordinary zombies. No model, no anim, no aitype.
- The two bulk source folders are `model_export` (14.6 GB) and `texture_assets` (8.7 GB). A map using the dog (or a ported boss) needs the files it names from them in the tree it links against.
- The DLC is off by default. To check an install, look in `steamapps/appmanifest_455130.acf`: `"DisabledDLC" "499270"` means it is not installed. steamcmd.net names 499270 "BOIII Mod Tools - Additional Assets DLC", depot size 104,515,380,963 bytes. Its contents are not listed publicly.
</details>

<details><summary>Panzer recipe from Spiki's pack (update archive read, base pack not read)</summary>

Read from the pack's `UPDATE_20200728.rar` (6.8 MB, the author's open release, password in the post): `zm_ai_playground.gsc` and `AI/share/zone_source/mechz.zpkg`. The aitype, spawner classname, models and anims are in the 1.47 GB base pack, which was not downloaded.

- Zone: the pack ships `share/zone_source/mechz.zpkg` with `scriptparsetree,scripts/shared/ai/mechz.gsc|csc`, `scriptparsetree,scripts/zm/mechz_spiki.gsc|csc`, `rawfile,animtrees/mechz_tomb.atr`, `xmodel,c_zom_mech_body_lod0`, `xmodel,c_t7_zm_dlchd_origins_mech_body_lod0`, scene bundles `ai_zm_dlc1_soldat_arrive(_2)`, `weapon,electroball_grenade_zm`, `beam,flamethrower_beam_3p_zm_mechz`, about 35 fx lines. How the map zone pulls it in (probably `include,mechz`) is in the base pack's instructions; unverified. Spiki: "You'll need to comment some lines in bo3/zone_source for scripts".
- Map: one spawner with `targetname mechz_genesis_spawner` (or `mechz_tomb_spawner` for the Origins look); spawn structs are picked by `choose_a_spawn("mechz_spot")`. A struct with `script_string flyin` plays the fly-in scene.
- Script: `#using scripts\shared\ai\mechz;` and `#using scripts\zm\mechz_spiki;`, then `mechz_spawn( s_struct, tomb, health )`. Inside: `zombie_utility::spawn_zombie( spawner, "mechz", s_struct.origin )`, `e_ai.is_boss = true`, `e_ai.b_ignore_cleanup = 1`, default `e_ai.health = 1500`.
- Death hook, the pack's own: `self waittill("death"); self.attacker zm_score::player_add_points("death_mechz", 1500);` then a Max Ammo drop. A final-boss version would `waittill("death")` on the returned `e_ai` and set the win flag.
- Stock Treyarch convention, for comparison (decompiled `_zm_ai_mechz.gsc`, github.com/ate47/bo3-source, no licence, reference only): `getentarray( "zombie_mechz_spawner", "script_noteworthy" )`, `struct::get_array( "mechz_location", "script_noteworthy" )`, `spawn_mechz( s_location, flyin )`, `level.mechz_base_health = 1200`.
</details>

<details><summary>Other special enemies, short answer</summary>

None has a stock aitype or model; all need a port. Spiki's `zm_ai_playground.gsc` spawns each from one spawner found by targetname: `margwa_spawner` (and `margwa_elemental_spawner`), `thrasher_spawner`, `mangler_spawner` (Raz), `apothicon_fury_spawner`, `keeper_spawner`, `sentinel_spawner`, `spider_spawner`, `meatball_spawner` (raps). Zpkgs ship for margwa, mangler, thrasher, apothicon_fury, keeper, sentinel_drone, vehicle_parasite, vehicle_spider, vehicle_raps. Spiders, wasps and Margwa need the Additional Assets DLC per the author. Users reported the Panzers' destructible armour does not work and that the Origins Panzer grab cannot be escaped (thread 3087).
</details>

<details><summary>Online sources (URL + what each says, paraphrased) and licence notes</summary>

- Spiki's asset dump, https://forum.modme.co/wiki/threads/3087.html (archive: github.com/dtzxporter/ModmeForum wiki/threads/3087.md). The post lists the AI in the pack: Panzer, Origins Panzer, Apothicon Fury, Mangler, Margwa, Sentinel drone, Thrasher, Spiders, Wasps, Raps (the Shadows of Evil meatballs) and a Keeper without sound. Spiki credits Scobalula's tools for much of the work and says the spiders, wasps and Margwa need the Additional Assets DLC. Downloads on Mega (base 1,474,024,263 bytes, update 6,790,023 bytes).
- Its terms (paraphrased): Spiki will take the post down if the AI turn up in a low-effort map such as a box map, and forbids reposting the pack. No formal licence. The post also says Harry's pack must be uninstalled before installing this one, because the two conflict in the gdt.
- Fix for Panzers that stand still (thread 3087, Spiki): comment out the gsc/csc entries in `zone_source\all\assetlist` and copy in the new spawn functions if older ones are present; after that they move out of the box.
- natesmithzombies, https://forum.modme.co/wiki/threads/651.html : the stock Panzer script and assets are not available, so adding him means scripting him from scratch.
- mathfag, https://forum.modme.co/wiki/threads/437.html : Margwa and spiders have to be built by the mapper; Margwa would spawn the way NSZ's Brutus or mathfag's Panzer Soldat does, and spiders the way dogs do.
- Harry Bo21's Panzer existed (aitype `spawner_zm_genesis_mechz`, `hb21_mechz.ai_am`), https://forum.modme.co/wiki/threads/3263.html names that aitype. No current download or terms found.
- https://www.ugx-mods.com/forum/models/125/panzer-soldat-v1-5-new-spawn-system/23087/ is a Black Ops 1 (WaW-engine) Panzer by shippuden1592, not usable in BO3.
- Not to be used: github.com/NightwalkerLots/BO3-Workshop-Decompiled-Maps-Mods contains decompiled Workshop maps (other authors' packed maps).
- Brutus 2, https://forum.modme.co/wiki/threads/2875.html : custom archetype; the setup step is to remap the spawner's class to `actor_spawner_cellbreaker`.
- Dog setup, https://wiki.modme.co/wiki/black_ops_3/basics/Setting-up-dog-rounds.html : a single actor prefab placed in the map is enough to enable dog spawning in general.
</details>

<details><summary>Evidence per enemy in the mod tools install</summary>

- Aitypes that ship: only `archetype_zm_factory_zombie`, `archetype_zm_factory_zombie_dog`, `archetype_zm_usermap_zombie` (archetypes/archetypes.gdt:2, :166, :330). No other `aitype.gdf` entry in any .gdt under tools.
- Anim state machines / behavior trees: only `zm_factory_zombie_dog`, `zm_genesis_zombie`, `zm_zombie` (share/raw/animstatemachines, share/raw/behavior).
- Dog: script ships (share/raw/scripts/zm/_zm_ai_dogs.gsc), dog aitype uses character `c_zom_der_hellhound` (archetypes.gdt, defined in model_export/t7_characters_zombie.gdt), dog fx are in zm common assetlists (`fx,zombie/fx_dog_*`). zm_usermap.gsc:69 `#using` it and :146-149 enables dog rounds when `level.dog_rounds_allowed`.
- Raps/wasp: zm scripts ship (_zm_ai_raps.gsc, _zm_ai_wasp.gsc) and shared/vehicles/_raps, _wasp, _parasite, _sentinel_drone, _spider ship, but no vehicle def asset for any of them (0 hits in .gdt and assetlists).
- Mechz, margwa, raz, thrasher, apothicon fury: only the shared archetype behaviour script ships (shared/ai/mechz.gsc, margwa.gsc, raz.gsc, archetype_thrasher.gsc, archetype_apothicon_fury.gsc). No zm spawn script (no zm/*mechz*, *margwa* etc.), no aitype, no ASM, no character. The 17 "margwa" xanims are ordinary zombies' smash reactions.
- Keeper, parasite, spider: nothing beyond the vehicle scripts above; "keeper" assetlist hits are peacekeeper/Genesis UI.
</details>

<details><summary>How a stock hellhound would be spawned (not yet built into a generated map)</summary>

- Map: an `actor_spawner_zm_factory_zombie_dog` entity with `script_noteworthy zombie_dog_spawner`, `script_forcespawn 1` (example: map_source/_prefabs/zm/zm_giant/script/zm_giant_nodes.map:2520-2528).
- Spawn points: structs targeted by a zone volume with `script_noteworthy dog_location` (_zm_zonemgr.gsc:345 collects zone structs, :364-383 buckets tokens; _zm_ai_dogs.gsc:364 reads `level.zm_loc_types["dog_location"]`).
- Init: `dog_spawner_init` collects spawners by `zombie_dog_spawner` (_zm_ai_dogs.gsc:122) and returns silently when there are none (:126).
- Script: `zm_ai_dogs::special_dog_spawn( 1 )` (_zm_ai_dogs.gsc:845); caps at 9 live dogs (:849). Set `level.dog_rounds_allowed = 0` before `zm_usermap::main()` if the map should not get dog rounds.
- Zone: no extra lines found necessary; dog scripts and fx are already in zm common assetlists. Unverified until a build links it.
</details>

<details><summary>Not yet known</summary>

- Whether the linker pulls the dog aitype into the fastfile from the spawner entity alone (no `aitype,` zone line). Our zm_dmv.zone has no aitype lines and ordinary zombies work, which suggests yes; not tested for the dog.
- Whether `SetModel` on a spawned zombie actor keeps anims and gibs correct (not needed for the fallback design; unverified).
- What the Additional Assets DLC (app 499270, 104.5 GB, off by default) contains. Enabling it and grepping its GDTs for mechz would settle whether any stock Panzer source ships there.
- Spiki's base pack: the aitype and spawner classname, and whether its zone and GDTs link cleanly next to a generated map's.
</details>
