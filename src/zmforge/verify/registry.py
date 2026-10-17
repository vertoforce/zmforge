"""One table of every check this package runs, and every rule it does not.

``docs/playable-map-requirements.md`` is written against this table, and
:func:`~zmforge.verify.run_all` prints a pass/fail line per entry from it.  A
requirement that has no automated check is here too, with ``where="manual"``
and a note saying what a human has to look at instead, so the count of
unguarded requirements is a number rather than a feeling.

The code's letter says where the rule came from.  ``Z``, ``W``, ``F``, ``P``
and ``G`` are the specification's own families.  ``N`` and ``L`` are not: they
are the rules read straight out of the documentation the mod tools ship
(``N1`` to ``N4`` from ``bin\\default_navmesh_settings.json``, ``N5`` from
``docs_modtools\\Scale_Standards.pdf``, ``L`` from
``docs_modtools\\Culling_LOD_Lights.pdf``), and they are kept apart because
their thresholds are quotable numbers with a file behind them rather than
things this repo measured.  :mod:`~zmforge.verify.documented` holds them.

``H`` is a third kind again, and there is one of it.  It is read out of the
**navmesh the compiler wrote** -- ``<map>_navmesh.hkt``, a Havok tagfile --
rather than out of the model, the text or a document.  It is the only row that
needs a build artefact, which is why it has a ``where`` of its own:
:mod:`~zmforge.verify.hkt` reads the file and
:mod:`~zmforge.verify.navmesh` asks the questions.

Two codes are used twice, in the specification and here, and renaming them
would break assertions in the suite and in other callers, so the table
records both meanings against the one code:

``Z13``
    models and prefabs exist on the install (model level), and the client
    script calls the framework entry (file level);
``Z15``
    nothing to fall through (model level), and the emitted scripts are
    structurally sound (file level).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Check", "CHECKS", "BY_CODE", "CODES", "automated", "manual"]


@dataclass(frozen=True, slots=True)
class Check:
    """One row of the table.

    ``where`` says which entry point runs it:

    ``blueprint``
        :func:`~zmforge.verify.blueprint`, before anything is written;
    ``files``
        :func:`~zmforge.verify.files`, over the text a commit wrote;
    ``stages``
        :func:`~zmforge.verify.stages`, over the build logs;
    ``navmesh``
        :func:`~zmforge.verify.navmesh_file`, over the ``_navmesh.hkt`` the
        compiler wrote beside the BSP -- the only row that reads a build
        artefact, and the only one that can say what the *walkers* can reach;
    ``manual``
        nothing runs it; ``note`` says what a human has to do instead.
    """

    code: str
    rule: str
    where: str
    note: str = ""

    @property
    def is_automated(self) -> bool:
        return self.where != "manual"


#: Every check, in the order the requirements document presents them.
CHECKS: tuple[Check, ...] = (
    # ---------------------------------------------------------------- spawns
    Check(
        "Z1",
        "a player_respawn_point struct per zone and at least four initial_spawn "
        "structs, each carrying the zclassic_start_room token, none carrying "
        "script_int, at least 32 units apart, over floor and not buried",
        "blueprint files",
    ),
    Check(
        "Z2",
        "the script leaves level.default_start_location alone or sets it to "
        "'start_room'; any other value empties the spawn set",
        "files",
    ),
    Check(
        "Z26",
        "a map with more than four initial_spawn structs sets "
        "level.player_too_many_players_check = false after the framework "
        "entry, or the fifth player to spawn is frozen and the game ends; "
        "extra spawn structs on their own do not seat more than four",
        "files",
    ),
    # ----------------------------------------------------------- standing room
    Check(
        "Z18",
        "nowhere a player can stand is outside every player_volume, or the "
        "out-of-playable-area monitor kills them outright every 3 seconds",
        "blueprint",
    ),
    # Z40, not the next free number: the Z2x codes were already taken.
    Check(
        "Z40",
        "no zone volume reaches over the zombies' side of a barricade -- a "
        "yard, which _standing_patches leaves out of the playable area "
        "because the barricade prefab stops the player at the wall line. The "
        "converse of Z18, and a warning rather than an error because it costs "
        "powerups and not a life: a zombie is not powerup-eligible until it "
        "touches a player_volume (_zm_spawner.gsc:3253 clears the no_powerups "
        ":359 set), and a drop is kept wherever it touches one "
        "(_zm_powerups.gsc:630), so volume over the yard converts a kill that "
        "would have dropped nothing into one of the round's four powerups, "
        "landing out of reach. Floor declared reachable=False and pockets "
        "Z25's flood cannot get to are deliberately not reported: a partition "
        "that stops a player stops a zombie, so nothing dies there",
        "blueprint",
    ),
    Check(
        "Z3",
        "one starting zone; every player_volume's targetname is a zone the "
        "script registers and enables, and every registered zone has a volume "
        "-- by name, never by count, because one zone owns as many volumes as "
        "it likes (zone_init gathers them with GetEntArray(zone_name, "
        "'targetname'), and stock zm_giant.map has 32 volumes over 12 zone "
        "names against one init_zones entry); every zone is reachable through "
        "a door flag, so it actually gets enabled in play; and the zone hook "
        "initialises its flags before its add_adjacent_zone calls, never "
        "after, because flag::init writes a flag back to zero and "
        "add_adjacent_zone has already created any flag it was handed",
        "blueprint files",
    ),
    # ----------------------------------------------------------------- zombies
    Check(
        "Z4",
        "every zone has a spawn struct -- an error, not a warning: a zone "
        "collects its locations from the structs its volume's target names, "
        "only an active zone contributes any, and the round loops wait on an "
        "empty list rather than time out -- every struct names its zone "
        "volume's target and carries a script_string, and interior spawns sit "
        "inside their own volume",
        "blueprint files",
    ),
    Check(
        "Z5",
        "at least one entity tagged zombie_spawner, or the round starts and "
        "no zombie is ever made, and its classname names one of the two "
        "zombie aitypes the install actually ships "
        "(archetypes/archetypes.gdt): actor_spawner_zm_usermap_zombie, which "
        "is what share/zone_source/zm_levelcommon.zone declares for a usermap "
        "and what this package emits, or the older "
        "actor_spawner_zm_factory_zombie the level template ships, which "
        "works but warns because its animation table names no jump, mantle, "
        "climb or traverse_procedural move; map-wide is the "
        "right scope, because the framework picks the spawner entity at "
        "random from every zombie_spawner in the level and the position "
        "separately from the active zones' structs (Z4 holds the per-zone "
        "half)",
        "blueprint files",
    ),
    Check(
        "Z6",
        "a spawn struct sits on the floor under it, within 8 units, and is not "
        "buried in a world solid",
        "blueprint",
    ),
    Check(
        "Z8",
        "a barricade window is an opening the traversal channel fits in, with "
        "a link-tagged riser in a yard behind it",
        "blueprint files",
    ),
    Check(
        "Z10",
        "statement order in main(), and the dog flag set before the framework "
        "entry rather than after it",
        "blueprint files",
    ),
    # ------------------------------------------------------------------- doors
    Check(
        "Z7",
        "a priced door with a collision leaf, an explicit origin inside its "
        "own brush, and a flag in exactly one add_adjacent_zone call",
        "blueprint files",
    ),
    Check(
        "Z30",
        "every part of a door -- the collision leaf and the model, both -- "
        "carries DYNAMICPATH set to 1, the key Radiant's own entity database "
        "(bin\\t7.def.json) declares on script_brushmodel and script_model "
        "and defaults to false. Without it the door still builds, links and "
        "opens, and the AI paths through the opening are never rejoined when "
        "it moves, so zombies path badly around a doorway that looks correct",
        "files",
    ),
    Check(
        "Z31",
        "an opening sealed with nothing but tool materials is a warning, not a "
        "pass. clip, caulk and their kin become collision the compiler draws "
        "nothing on, so the hole reads in play as solid and empty -- which is "
        "also exactly what a missing barricade, an unfilled pane and a model "
        "the packer silently dropped look like. Deliberate is fine; "
        "indistinguishable-from-broken is what the warning is for",
        "blueprint",
    ),
    Check(
        "Z32",
        "no barricade window uses the hide-pieces prefab. Diffed against the "
        "plain one on the install: barricade_reciever_wood.map carries a full "
        "player clip over the whole opening (x -48..50, z 0..113) and "
        "barricade_reciever_wood_hide_pieces.map has no such brush, only the "
        "sill band (x -39..35, z 0..35). Nothing else in this package plugs a "
        "barricade opening, so that variant leaves a 96 x 112 hole the player "
        "walks through into the yard. Treyarch use it throughout zm_giant and "
        "clip their openings by hand",
        "blueprint",
    ),
    Check(
        "Z9",
        "every perk machine, box and switch has its #using module -- in the "
        "client script as well as the server one, because the client half is "
        "the perk's clientfields, HUD and machine effect -- stands on "
        "reachable floor, is not buried in a world solid, has clear space "
        "in front to buy from, and has its back rather than its side to the "
        "brushwork it is up against: facing is the heading the machine's "
        "front points at, and a quarter turn out puts a 64-wide machine "
        "through the wall with its prompt read along it",
        "blueprint files",
    ),
    Check(
        "Z49",
        "a Der Wunderfizz has something to give and something to start it: "
        "the map that places one names its module in both scripts, marks "
        "exactly one machine the starting machine, gives each machine the "
        "six zbarrier boards the stock script drives, and registers at "
        "least one perk in its rotation whose own module the script also "
        "carries.  None of it is optional and all of it is silent: a "
        "machine with an empty rotation links clean, takes 1500 points and "
        "faults on an undefined array, and a map with no starting machine "
        "links clean and never threads one",
        "files",
    ),
    Check(
        "Z50",
        "a perk the map wrote itself is whole: it hands "
        "register_perk_basic_info a bottle, because the framework charges "
        "before the drink and grants the perk only when the weapon change "
        "completes; its registration function is called from main and called "
        "before the framework entry; it has a machine struct carrying its "
        "specialty and no machine carries a specialty nothing registers; the "
        "prompt it names is precached; and no two perks -- ours or a stock "
        "one placed on the same map -- claim the same HUD slot. All of it "
        "links clean and all of it is silent in game",
        "blueprint files",
    ),
    Check(
        "Z51",
        "every clientfield::register the emitted scripts make is written "
        "before the framework entry call; the entry waits inside load::main "
        "and the engine closes the registration period while it waits, so a "
        "registration after it links clean and the game refuses the map at "
        "load",
        "files",
    ),
    Check(
        "Z53",
        "no solid prop taller than a step stands in a doorway or in the 48 "
        "units of floor either side of it, over the opening's width plus 8 "
        "each side: zm_dmv shipped a filing cabinet ten units into the door "
        "behind its counter and the player could not walk through, and "
        "nothing else asked -- Z44 compares props with props, Z25 still "
        "found the narrowed route and Z48 asks only about items",
        "blueprint",
    ),
    Check(
        "Z54",
        "no solid floor prop's measured footprint reaches more than a unit "
        "past the inner wall face of the room it stands in: zm_dmv shipped "
        "fourteen cabinets and shelves turned with their long side into the "
        "wall, 24 to 37 units deep, and nothing asked -- Z44 compares props "
        "with props and Z53 looks only at doorways. A hollow prop resting on "
        "a surface that reaches more than 3 units past the wall is a warning "
        "(zm_corn_maze's barn shelf items, 5 to 11 units in)",
        "blueprint",
    ),
    Check(
        "Z55",
        "inside every room, every doorway, perk, wall buy, box, power switch, "
        "barricade and quest use trigger is joined to the others by floor a "
        "30-unit player fits through past the solid props and brushes (8-unit "
        "raster, footprints grown by the 15-unit radius); a corridor under 40 "
        "units on the widest route is a warning: zm_dmv shipped a planter 26 "
        "units in front of its starting wall buy, and nothing asked -- Z53 looks only at doorways and Z48 floods "
        "from the spawn, not door to door",
        "blueprint",
        "zmforge check re-asks it of the stored <map>.blueprint.json",
    ),
    Check(
        "Z56",
        "no brush lettering lies flat on a floor or the ground (a warning): "
        "words on the floor read as grey planks from eye height in every "
        "render; hang it "
        "with zmforge.dressing.hanging_sign or letter a wall",
        "blueprint",
    ),
    Check(
        "Z57",
        "no solid prop taller than a step stands within 64 units of a "
        "barricade window's opening, either side of the wall, over its width "
        "plus 16 each side (a warning): zombies climb in there and players "
        "rebuild there -- zm_corn_maze had a heap 45 units off a farmhouse "
        "window, caught by a corn-only keep-out",
        "blueprint",
    ),
    Check(
        "Z58",
        "no placed model is on the render deny-list, "
        "zmforge.props.reads_badly.READS_BADLY, or measured in "
        "props/notes.json to draw dark, blank or not at all in the editor "
        "render (a warning): models that render as something they "
        "are not, such as the lobby picture that draws as a dark panel "
        "(zm_corn_maze, settled by a side-by-side render)",
        "blueprint",
    ),
    Check(
        "Z59",
        "no prop stands without a partner props/notes.json says it needs, "
        "where the blueprint can tell (a warning): a curtain has a rail or "
        "bar along its top, a desk monitor has a desk or counter under it",
        "blueprint",
    ),
    Check(
        "Z60",
        "every prop keeps the rules its props/notes.json entry or category "
        "sets, where the blueprint can tell (a warning): a chair does not "
        "turn its back on the desk beside it, a desk monitor has a seat "
        "facing it, a sign faces into its room rather than into its wall, "
        "a wall piece touches a wall, a wall screen hangs 40 to 200 units "
        "up, a vending machine keeps 32 units clear in front, a sink has "
        "legs or a counter under it, a pipe run reaches a floor, ceiling, "
        "wall or fixture, a scarecrow's parts touch; orientation only for "
        "models whose front was measured (a front-measuring pass)",
        "blueprint",
    ),
    Check(
        "Z61",
        "no quest step starts before players can reach it: a step whose "
        "targets, items, desk, hint, zone or boss stand in a zone behind a "
        "door waits for that zone (zm_zonemgr::zone_is_enabled) before its "
        "start line, task and timer (a warning).  zm_dmv's Vision Test "
        "started at game start with a 15-second timer while the eye exam "
        "room was four doors in (P8); a point in a zone "
        "only a script flag opens is a warning too",
        "blueprint",
    ),
    Check(
        "Z62",
        "an open-air room's wall over 600 units long has no bare run over 320 "
        "units: something (a pier, coping, plinth, prop or opening) stands "
        "against its inner face (a warning).  a hero shot "
        "once showed 2,000 units of flat brick",
        "blueprint",
    ),
    Check(
        "Z63",
        "an open-air room shows sky and a backdrop: its walls stand no more "
        "than 320 over its floor, and on a side facing open air something "
        "beyond the wall rises over it (a warning)",
        "blueprint",
    ),
    Check(
        "Z65",
        "a roofed room's outer wall that rises over a neighbouring open "
        "room's low wall is dressed: something stands proud of it (a warning; "
        "zmforge.dressing.facade).  Undressed, a shed, chapel or vault "
        "standing over low walls reads as a blank slab",
        "blueprint",
    ),
    Check(
        "Z66",
        "a room's foliage grows in clumps, not an even scatter (a warning): "
        "with 40 or more plant, grass, weed, hedge or leaf props, their "
        "Clark-Evans nearest-neighbour ratio stays under 0.85 (about 1 is a "
        "random scatter), because bushes grow next to each other "
        "(zmforge.dressing.cluster.mixed_clumps)",
        "blueprint",
    ),
    Check(
        "Z64",
        "a glow that belongs to an object goes out with it (P12, a warning): "
        "no static light within 96 units of an object a script removes or a "
        "quest finishes (script.glow.own_object), and no looping powerup_on* "
        "effect played with PlayFX, which has no handle and never stops "
        "(corn maze lanterns stayed lit after the shot)",
        "blueprint files",
    ),
    Check(
        "Z67",
        "init_zones lists only zones open at load: the starting zone, zones an "
        "always_on edge joins to it, and zones no door leads into (a sealed "
        "spawn hall).  Read from the generated script: manage_zones enables "
        "every entry at load (_zm_zonemgr.gsc:841-844), so a door-gated zone "
        "there passes every zone gate at once ("
        "every map listed every zone)",
        "files",
    ),
    Check(
        "Z68",
        "a handler threaded from a fire watcher that pays points has a "
        "per-player cooldown and pays after its last early return, so it "
        "pays only for success",
        "files",
    ),
    Check(
        "Z69",
        "a watcher keyed to a thrown weapon waits on grenade_fire, as every "
        "stock grenade watcher does (_zm_weapons.gsc:101), not weapon_fired",
        "files",
    ),
    Check(
        "Z70",
        "zombie_spawn_delay is restored through level.func_get_zombie_spawn_delay, "
        "never from a value saved before a spike (a warning; _zm.gsc:4502 "
        "rewrites it every round)",
        "files",
    ),
    Check(
        "Z71",
        "a script that moves a player after a wait (a teleport, a relocation) "
        "checks last stand right before the move",
        "files",
    ),
    Check(
        "Z72",
        "every *_PROMPT string names the use key [{+activate}] (P5, a warning: "
        "a locked quest exit's prompt must say which key to press too)",
        "files",
    ),
    Check(
        "Z73",
        "every boss is guarded against a one-shot Insta-Kill: it sets "
        "zmf_no_instakill and its spawn installs level.check_for_instakill_override "
        "(_zm_powerups.gsc:1440-1445)",
        "files",
    ),
    Check(
        "Z80",
        "no door that waits for the power (electric, or requires_power: the "
        "stock electric_buyable_door) stands on every way from the spawn to "
        "the power switch, which would leave the power unreachable "
        "(verify.power_reach; cemetery)",
        "blueprint",
    ),
    Check(
        "Z81",
        "every door's closed leaf covers its opening (no gap at a jamb or over "
        "the top), stands no taller than it, and the opening fits the player's "
        "30 x 72 hull (verify.door_cover; corn maze patch gate)",
        "blueprint",
    ),
    Check(
        "Z79",
        "at most FLAVOUR_BROADCAST_LIMIT (2) flavour broadcasts: lines printed "
        "on entering a zone, at a round end or on a random timer by the gag "
        "helpers (P13, P17, a warning; the cemetery's 15 sign-in and PA lines "
        "were too many)",
        "files",
    ),
    Check(
        "Z82",
        "no perk limit: after zm_usermap::main() the script sets "
        "level.perk_purchase_limit and the purchase-time pointer "
        "level.get_player_perk_purchase_limit to at least NO_PERK_LIMIT (99), "
        "and nothing else assigns either (_zm_perks.gsc:43 sets 4 inside that "
        "call; _zm_utility.gsc:5874-5889; every map has no perk limit)",
        "files",
    ),
    Check(
        "Z83",
        "player spawns sit in at most one sealed pocket of air; every other "
        "pocket a player stands in is open to the air inside the sky shell "
        "(Blueprint.add_yard_vent), because the linker's occlusion pass keeps "
        "the open air plus one sealed pocket (every link log: 'Filtered N/N+2 "
        "inside clusters') and a player in a dropped pocket sees floors and "
        "walls flicker to the sky",
        "files",
    ),
    Check(
        "Z84",
        "no world box that draws a face leaves an undrawn (caulk) face of 8+ "
        "units open to room or yard air: a raised floor with a caulk back lets "
        "the player see through it from behind, and what stands on it floats; "
        "Z44's support rule passes those props because the floor's top does "
        "hold them up -- support is collision, this is drawing",
        "blueprint",
    ),
    Check(
        "Z85",
        "every barricade window is a window: a drawn sill wall (nonColliding) "
        "to SILL_WALL_HEIGHT (32, Treyarch's sill, inside the prefab's 0..35 "
        "clip band) under its floor-cut hole, and its closet has real "
        "materials, dim unstacked lamps and some clutter (a warning when "
        "bare) (verify.windows; a zombie window shows solid wall to "
        "waist height)",
        "blueprint",
    ),
    Check(
        "Z88",
        "indoor air is lit and exposed as indoors all the way through: every "
        "barricade closet lies in a reflection probe box, and every opening in "
        "a roofed room's wall is inside an indoor probe box at mid-wall, so no "
        "doorway between indoor rooms crosses the sun volume's global "
        "(outdoor) probe and an indoor/outdoor change happens inside the "
        "indoor box's blend (verify.indoor_light; Blueprint.probe_boxes; "
        "otherwise a bright flash between rooms and blown-out closets)",
        "blueprint",
    ),
    Check(
        "Z89",
        "the plants lining a wall hide it: over a spread sample of the faces a "
        "recipe lined (bp.lined_faces), the zmforge-generated plants in each "
        "face's band, drawn head-on from their real meshes, cover at least "
        "MIN_HIDDEN (75%) of the face on average (verify.lining; "
        "dressing.lining.hidden_fraction; 63% still reads as thin), and on every "
        "face no "
        "stretch longer than MAX_BARE (72) is hidden by no plant (half a "
        "plant's leaf spread either side of its stem), outside room "
        "apertures, interactive bodies and bp.lined_openings (otherwise "
        "corn stalks go missing: 78 runs over 80 at a 79% mean)",
        "blueprint",
    ),
    Check(
        "Z91",
        "no wall buy hangs on a face lined with plants (bp.lined_faces): its chalk and "
        "walk-up would clear the plants in front of it and leave bare wall; "
        "placement.wallbuy.place_wall_buy puts it on the nearest unlined "
        "wall of its zone",
        "blueprint",
    ),
    # Q1-Q7: quest, boss and co-op safety over the written script
    # (verify/quest_safety.py).
    Check(
        "Q1",
        "every quest or boss thread that waits ends on end_game, a thread run on a "
        "player ends on disconnect, and a player taken from a trigger is checked "
        "with isdefined after a later wait (quests survive a leave and the game end)",
        "files",
    ),
    Check(
        "Q2",
        "a carried quest item returns to its spot when its carrier goes down, "
        "bleeds out or leaves (the item thread loops back to spawn it)",
        "files",
    ),
    Check(
        "Q3",
        "a timed or hold step pauses while special_round is set or holds special "
        "rounds back (lockdown), and a held step does not start during one, "
        "so a lockdown during a dog round cannot soft-lock the quest",
        "files",
    ),
    Check(
        "Q4",
        "HUD elements are per player (NewClientHudElem stored on that player) or "
        "level-wide on purpose (NewHudElem under a '// level-wide HUD:' line); no "
        "client element in a level field, none for the first player only",
        "files",
    ),
    Check(
        "Q5",
        "co-op: every-player counts and player-count scaling use the players present "
        "(sessionstate playing), and no one-shot trigger moves only the player who "
        "touched it",
        "files",
    ),
    Check(
        "Q6",
        "every boss declares a time-to-kill target (self.zmf_boss_ttk, "
        "BossHealth.ttk); normal zombie spawns ease off while it lives (a warning "
        "when they do not and it does not say so)",
        "files",
    ),
    Check(
        "Q7",
        "no required quest step waits on chance: no random roll in a condition it "
        "depends on without a pity counter, no random teleport destination, no wait "
        "on a random power-up or the box, "
        "no weapon only the box gives",
        "files",
    ),
    Check(
        "S1",
        "every room declares a scene, a one-line 'what happened here' "
        "(zmforge.dressing.declare_scene), and shows the beats it promises "
        "(fire, smoke, embers, wreck, barricade, body, flood, flies); a warning "
        "(docs/map-design-method.md)",
        "blueprint",
    ),
    Check(
        "S2",
        "a room carries at least a quarter of the stock zm_giant density "
        "(1,148 non-trim props per 1000x1000 units; litter not counted), "
        "40% in a room of 0.5 k2 or more, and, over 0.25 k2, something in the mid or "
        "overhead band (a warning)",
        "blueprint",
    ),
    Check(
        "S3",
        "a room over 0.5 k2 has at least one set piece (a solid prop 72+ units "
        "wide and 36+ tall) splitting its lanes (stock: 2.1 per k2); a warning",
        "blueprint",
    ),
    Check(
        "S4",
        "an open-air room has at least one ambient effect (fire, smoke, embers; "
        "zmforge.dressing.fx); a warning (stock: 75 effects per k2)",
        "blueprint",
    ),
    Check(
        "S5",
        "a roofed room of 0.5 k2 or more carries at least 50 overhead props "
        "(origin 160+ units over the floor) per k2: lamps, ducts, pipes, "
        "things hung off beams (stock 113; zmforge.dressing.walldetail); a warning",
        "blueprint",
    ),
    Check(
        "S6",
        "no wall of a roofed room of 0.5 k2 or more runs over 256 units as "
        "one flat material floor to ceiling (no skirting, wainscot, rail, "
        "counter, column or opening crosses it; pictures and lettering do "
        "not count; zmforge.dressing.walldetail); a warning",
        "blueprint",
    ),
    Check(
        "D1",
        "every zone with zombie spawns has a closed walkable ring round a "
        "central block, lanes 128+ units wide and 1000+ units round, to train "
        "zombies round (a warning; docs/map-design-method.md section 8, "
        "and the level-design guides it cites)",
        "blueprint",
    ),
    Check(
        "D3",
        "the cheapest door spend from spawn to Juggernog, Quick Revive, power "
        "and the first box (research item 3)",
        "manual",
        "A fact, not a check: the review facts print it as map.points_to_core "
        "(zmforge.verify.design.points_to_core). Players punish an expensive "
        "way to Juggernog, but no stock map has been measured, so there is no "
        "threshold yet; a reviewer reads the numbers against the map's economy.",
    ),
    Check(
        "D4",
        "a lock (a quest's hand-in desk, its buyable exit) stands in a zone that "
        "opens no later, by cheapest door spend, than the zone of its first key "
        "or part: show the lock before the key (a warning; research item 4)",
        "blueprint",
    ),
    Check(
        "D5",
        "every door, buyable and quest station has a lamp within 192 units at "
        "least as bright as the filler lamps near it, every training ring is lit "
        "at its centre, and no point on the way from a room's doorways to its "
        "doors and buyables is over 256 units from a lamp (a warning; research "
        "item 5). An unlit perk or power switch is an error since the "
        "generator gives every unlit door and buyable a play lamp "
        "(blueprint.autolamp)",
        "blueprint",
    ),
    Check(
        "D7",
        "no stretch of a map's declared walk paths (bp.walk_paths, a maze's "
        "passages) longer than 320 units is over 256 units from every lamp "
        "(a warning; "
        "blueprint.autolamp.light_paths lights them)",
        "blueprint",
    ),
    Check(
        "D8",
        "every roofed room's floor is lit by its own lamps: an estimate from the "
        "emitted lamps (2**(stops - exposure) * min(1, (128/d)**2) * far_edge ramp "
        "* colour luma, on a 48-unit floor grid) leaves no more than 60% of the floor "
        "under 0.25 and a mean of at least 0.2 (calibrated on the cemetery recipe's "
        "rooms, worst shed 36%/0.29, against a dark room's 100%/0.00); two joined rooms are no more than "
        "3 stops apart; a dim room opening onto a sunlit one is named (a warning; "
        "zmforge.verify.lightlevel)",
        "blueprint",
    ),
    Check(
        "D6",
        "no floor-standing prop taller than 24 units stands in the 96 units in front of "
        "anything the player uses (perk, box, power, wall buy, door, quest "
        "station); Z60's clearance_front box, asked of interactables (a "
        "warning; research item 10)",
        "blueprint",
    ),
    # ------------------------------------------- layout rules
    Check(
        "shadows_dropped",
        "the light bake drops no omni light's shadow ('Too many shadowing omni "
        "lights ... is being dropped'); shadowless lamps count too, and lamp "
        "sphere overlap is not the rule (zm_dmv bakes clean at 20, zm_corn_maze "
        "drops at 9) (a warning, read off the bake log)",
        "stages",
    ),
    Check(
        "Z74",
        "no two vignettes from one template, and no two rooms of one size, "
        "share over 60% of their (model, relative position) pairs, and no "
        "litter model is placed more than 40 times in a map (a warning)",
        "blueprint",
    ),
    Check(
        "Z75",
        "no walk-through floor prop over 60 units tall and over 40 wide on "
        "both sides stands in the play space: a player runs into what looks "
        "like a wall and passes through (a warning; small props under 18 "
        "units default to walk-through in recipes.props.is_solid)",
        "blueprint",
    ),
    Check(
        "Z76",
        "no barricade riser feeds a zone with under 0.05 k2 (50,000 square "
        "units) of floor or narrower than 64 units across (a warning)",
        "blueprint",
    ),
    Check(
        "Z77",
        "no room has a whole wall side in a material that renders as a black "
        "void (verify.layout_rules.DARK_WALL_MATERIALS; a warning)",
        "blueprint",
    ),
    Check(
        "Z78",
        "after a sealed start (script.splitstart) resolves, no respawn or late "
        "join can land in a sealed zone: the respawn callback is never cleared "
        "and returns a hub point, every player's spectator_respawn (the stock "
        "fallback, _zm.gsc:3282, :3315) is re-pointed at the hub, the sealed "
        "zones are disabled, the spawn hook moves anyone found in one, and no "
        "player_respawn_point stands in one (verify.sealed_start: otherwise "
        "the dead come back in their hallways)",
        "files",
    ),
    Check(
        "Z86",
        "every player_respawn_point has a target naming a group of points (one "
        "struct per zone, 4-8 points, as zm_giant.map; _zm.gsc:3453 reads the "
        "target, and without it a bled-out player respawns at their initial "
        "spawn), stands in the player_volume its script_noteworthy names, and "
        "no point is inside a colliding brush or off the floor the Z25 flood "
        "reaches (verify.respawn_points; blueprint.respawn)",
        "blueprint files",
    ),
    Check(
        "Z87",
        "every map not opted out (test maps: bp.signature_gamble = False) has "
        "exactly one gamble machine (P22; dressing.gamble, placed by "
        "Project.commit at the farthest walk from the spawn), its stand is on "
        "floor the Z25 flood reaches, and the written script has at most one "
        "machine thread, checks can_player_purchase for the same amount before "
        "it charges, and draws the odds with RandomInt (verify.gamble; no "
        "machine in a script is a warning)",
        "blueprint files",
    ),
    Check(
        "Z52",
        "the server and client scripts register the same clientfields, in "
        "the same order, with the same pool, name, version, bits and type; "
        "the engine compares the two lists at connect and a difference "
        "disconnects even a solo game with 'Clientfield Mismatch', and a "
        "usermap cannot lean on the stock LUI file for a client half the "
        "way the stock score fields do, because that file stops at four "
        "seats and a map cannot ship Lua",
        "files",
    ),
    # ---------------------------------------------------------------- lighting
    Check(
        "Z11",
        "a lamp in every room, below the ceiling, not buried in a world solid, "
        "no further than one lamp spacing from any floor -- in plan, and "
        "down a tall room's height as well, because a grid laid only "
        "at the ceiling leaves the floor of a very tall room dark -- at a stops "
        "value inside the band the shipped maps use for this map's own sun/sky "
        "exposure",
        "blueprint files",
    ),
    Check(
        "Z28",
        "a reflection probe whose box encloses every room on all three axes, "
        "with in_play_space set only where t7.def.json allows it; a map with "
        "no probe at all is a warning, because probes carry the bake's "
        "indirect solve (the entity's own key group is 2_DIFFUSE_GI) and "
        "nothing in the toolchain says a word about having none",
        "blueprint files",
    ),
    Check(
        "G7",
        "six sky slabs with no gap, every room and yard strictly inside them",
        "blueprint files",
    ),
    Check(
        "L2",
        "no lamp of radius 150 or less carries a culling_cutoff or "
        "culling_falloff over 25 (onscreen pixels; larger culls harder); "
        "unset is the engine default 0, never culled, and stock zm_giant "
        "gives its small lamps 5 / 25; 200 / 300 on every lamp breaks "
        "corridor lighting",
        "files",
    ),
    # --------------------------------------------------------------- materials
    Check(
        "Z12",
        "every face and patch material is in the known-clean catalogue; a "
        "patch never carries caulk",
        "blueprint files",
    ),
    Check(
        "Z13",
        "every misc_model resolves on the install, has all its model files in "
        "the local tools (links), and every misc_prefab path exists there "
        "(model level); the client main() calls the framework "
        "entry (file level)",
        "blueprint files",
    ),
    # ----------------------------------------------------------------- terrain
    Check(
        "Z15",
        "a mesh terrain has solid fill under it and a trigger_hurt below the "
        "whole map (model level); both emitted scripts are structurally sound "
        "(file level)",
        "blueprint files",
    ),
    Check(
        "Z20",
        "the written map carries a trigger_hurt with positive damage, under "
        "and around every player_volume, so a player who gets out is killed "
        "rather than left alive in the void",
        "files",
    ),
    Check(
        "Z16",
        "both scripts call only functions that exist and #using every module "
        "they call into",
        "files",
    ),
    Check(
        "Z90",
        "neither script calls a dev-only builtin (PrintLn, Print3d, Line, "
        "Sphere, Box, Circle, DebugStar, RecordLine and the other Record* "
        "draw calls) outside a /# #/ developer block: the retail loader "
        "refuses the whole script at map load with 'Dev only calls must be "
        "wrapped in a devblock'",
        "files",
    ),
    # -------------------------------------------------------------- clearances
    Check(
        "W2",
        "a doorway is at least as wide as the player's 30-unit hull; under 48 "
        "it is single file",
        "blueprint",
    ),
    Check(
        "Z19",
        "a flight of steps has a walkable surface within one of its own step "
        "rises of both its foot and its head, so it can be got onto and it "
        "leads somewhere",
        "blueprint",
    ),
    Check(
        "N1",
        "no flight of steps rises further in one tread than the navmesh "
        "generator will step; Z19 asks whether a flight connects to anything "
        "and takes no position on how high a tread may be, and this is that "
        "number, out of the tools' own default_navmesh_settings.json",
        "blueprint",
    ),
    Check(
        "N2",
        "no way through is narrower than the navmesh generator's own corridor "
        "width, which is one unit wider than the player hull W2 measures "
        "against, so a doorway can pass W2 and still get no navmesh; a "
        "barricade window is exempt, because zombies cross one by animation "
        "and not by walking",
        "blueprint",
    ),
    Check(
        "N3",
        "no way through leaves less headroom than the navmesh generator "
        "assumes a walker needs, which is the standing player height; same "
        "barricade exemption as N2",
        "blueprint",
    ),
    Check(
        "N4",
        "no terrain face is steeper than the navmesh generator treats as "
        "walkable, measured between neighbouring heightfield cells along both "
        "grid axes, which is the pair of samples the mesh triangulates from",
        "blueprint",
    ),
    Check(
        "N5",
        "no route the player's flood reaches stays under the 96-unit minimum "
        "hallway clearance of Scale_Standards.pdf for longer than that "
        "document allows -- 128 units at minimum clearance, 64 for anything "
        "under its 64-unit minimum pinch point. A warning, not an error, and "
        "a separate question from N2: N2's 31 is the measured threshold for a "
        "navmesh existing at all, this is Treyarch's own standard for a space "
        "being wide enough to move through. Stretches narrower than N2's own "
        "threshold are skipped, because nothing walks there to be slowed down",
        "blueprint",
    ),
    Check(
        "H1",
        "the navmesh the compiler wrote has walkable surface where the play "
        "is, and it is joined up: every spawn struct and both sides of every "
        "barricade stand on it, every zone the player reaches has some of it, "
        "and every standing rectangle Z25's flood reaches is covered by a "
        "piece of it a spawn struct can walk from -- the difference between "
        "that flood and this mesh being, exactly, the places a player can get "
        "to and no zombie can",
        "navmesh",
    ),
    Check(
        "Z46",
        "every flight of steps carries a smooth clip ramp, and no floor a "
        "player reaches is out of reach of the walkers' own movement -- no "
        "jump, no leap, and a rise of at most the navmesh generator's "
        "maxStepHeight. H1 asks whether the mesh the compiler wrote is joined "
        "up and Z25 asks whether a player can walk there; this is the third "
        "question, which both of those pass on a staircase of bare treads: "
        "what a walker's capsule actually slides along. Surfaces the map "
        "declares reachable=False are exempt and are each printed as a "
        "warning, so a deliberate tease is a line in the report rather than "
        "an absence of one. A zombie-proof top under 64 units over the floor "
        "of a playable room is an error even when it is cover. And no "
        "camping spot on any collision surface: the top of every brush (detail "
        "included) and solid prop, and every pocket between them, that a player "
        "reaches (jump 39, no mantle) and no walker reaches (step 18) is an "
        "error when no walker-reachable ground is within ZM_MELEE_DIST 64, 3-D "
        "(zombie.gsh), of a 16-unit foothold on it",
        "blueprint",
    ),
    Check(
        "Z48",
        "every machine, box, switch and wall buy can be walked up to with the "
        "dressing in the way: the stand box in front of it is reached by Z25's "
        "own flood, run again with every prop that stands on the floor counted "
        "as an obstacle and grown by half a player's hull. Z42 proves the space "
        "in front of an item is clear and Z25 proves the room is connected; "
        "neither asks whether a player can get to that space, so a room packed "
        "with scenery can wall in the one machine in it that works. Props "
        "that bake collision are an error, walk-through scenery a "
        "warning -- an error for a perk, the box, the power switch and a wall "
        "buy, whose 96-unit approach lane the placer now "
        "keeps clear (blueprint.lanes); a prop low enough to jump onto is not "
        "an obstacle at all, "
        "and an item over floor declared reachable=False is printed as a "
        "warning rather than skipped",
        "blueprint",
    ),
    Check(
        "Z25",
        "every machine, box, switch and wall buy, and every room and zone, is "
        "reachable on foot from the initial-spawn slots, flooding the standing "
        "surfaces through openings and doors and over steps, jumps and "
        "survivable drops; a surface the map declares reachable=False is "
        "exempt",
        "blueprint",
    ),
    # ------------------------------------------------------ weapons and props
    Check(
        "W1",
        "a wall buy's origin against the floor surface under it, which spec "
        "4.10 fixes 8 units below and nothing explains",
        "blueprint",
    ),
    Check(
        "W3",
        "a wall buy's emitted yaw puts its chalk and its use prompt in the "
        "room, not in the wall",
        "blueprint",
    ),
    Check(
        "Z22",
        "every weapon the map or its script names is in this level's weapon "
        "set, so a buy or a rigged box is not asking for a weapon that does "
        "not exist; a wall buy is resolved through its prefab first, because "
        "the slug names the prefab file and the weapon is named inside it",
        "blueprint files",
    ),
    Check(
        "Z27",
        "every collision file a prop's asset-database entry names exists on "
        "this root: the bullet mesh as the .XMODEL_BIN the entry spells, and "
        "the collmap in share\\raw\\collmaps. The prop chain writes the text "
        "export and export2bin makes the binary, so the entry can name a file "
        "no step in this package produces",
        "files",
    ),
    Check(
        "Z45",
        "every collmap the map asks cod2map64 to bake parses with the "
        "compiler the mod tools ship: no physics_* solid primitive where a "
        "face should start. Treyarch authored 28 of the 258 collmaps on this "
        "install with one, and the compile stops at \"MatchToken: got "
        "'physics_cylinder', expected '('\" on a file the map did not write",
        "files",
    ),
    Check(
        "W4",
        "a map that charges its own prices loads its weapon table on both "
        "sides and in the right order: the server assigns "
        "level._zombie_custom_add_weapons before the framework entry and "
        "loads the stock table first, the client loads the same table after "
        "the entry, and the manifest declares it. The client half is the one "
        "that bites: the prompt's number is filled in client side and has no "
        "hook, so without it the player is charged the map's price and shown "
        "Treyarch's",
        "files",
    ),
    Check(
        "W5",
        "every weapon named in the map's own weapon table exists -- a row of "
        "the stock level table or a weapon asset the manifest declares -- and "
        "every row is full width with an integer cost. Nothing else can "
        "check this: a string table is opaque to the linker, so a row naming "
        "a weapon that does not exist links clean and hands out nothing",
        "blueprint files",
    ),
    Check(
        "W6",
        "a custom weapon says where its definition comes from, and no two of "
        "them claim the same weapon asset",
        "blueprint",
    ),
    Check(
        "Z21",
        "a prop meant to be solid carries use_collmap and not no_collmap, and "
        "a collmap named after that model exists for cod2map64 to bake, so "
        "players and bullets do not pass through it. The second half is the "
        "one that bites: use_collmap on a model with no collmap grows the "
        "compiled map by a couple of dozen bytes, leaves the navmesh where it "
        "was, prints nothing, and the prop stays walk-through",
        "files",
    ),
    Check(
        "Z29",
        "a stock model that is one part of an assembly is placed with its "
        "other parts. p7_cai_staircase_01 is a staircase frame and its eleven "
        "treads are a separate model; on its own it draws handrails standing "
        "in mid air with nothing between them, and the compiler, the linker "
        "and the packer are all silent about it because the model it was "
        "asked for is exactly the model it got",
        "files",
    ),
    Check(
        "Z23",
        "a perk, box, switch, scenery prefab or barricade is emitted at a yaw "
        "that does not put its measured front on the heading it was asked to "
        "face, which is how ten of eleven wall buys once shipped aimed into "
        "their own walls",
        "blueprint",
    ),
    Check(
        "Z41",
        "no prop depicts a route -- a staircase, a ladder, a ramp -- because "
        "no prop can be one: a model is drawn rather than built, its "
        "collision is a baked hull and not a set of treads, and a player who "
        "reads one as the way up walks to it and finds nothing.  Z19 asks "
        "whether a flight of steps connects, of brushwork; this asks the "
        "question of the models, which no geometric check could reach, and "
        "which a reachability flood cannot ask at all because a staircase "
        "that goes nowhere strands nobody",
        "blueprint",
    ),
    Check(
        "Z42",
        "no interactive item stops another one being used: two bodies drawn "
        "through each other, a body standing in front of a wall buy's chalk, "
        "or a body filling the floor an item is bought from is an error, and "
        "an item that only reaches into another's apron is a warning.  The "
        "model refuses the error at placement time "
        "(zmforge.blueprint.reach), so this row is what covers a blueprint "
        "that arrived by another road -- read back out of the editor, or "
        "moved after it was placed",
        "blueprint",
    ),
    Check(
        "Z43",
        "nothing stands on nothing: every massing solid rests on something, "
        "hangs from something, or is flush against a vertical face of "
        "something.  A map is built out of arithmetic and arithmetic is how a "
        "slab lands in mid-air -- four columns of a test map began 16 "
        "units above the deck they were meant to stand on and every other "
        "check passed them, because they overlap nothing, block no route and "
        "are inside a zone.  A map that wants something hanging in the air "
        "declares it on the geometry (FLOATS_ON_PURPOSE), the way it declares "
        "a tease with reachable=False",
        "blueprint",
    ),
    Check(
        "Z44",
        "every prop is somewhere a prop can be: a model whose own measured "
        "box says it hangs on a wall or from a ceiling is not standing at "
        "floor level, two solid props do not share more than a quarter of the "
        "smaller one's footprint at the same height, a prop rests on what is "
        "under it rather than floating over it or hanging off its edge, and "
        "no prop stands inside an interactive item's own body.  Measured on "
        "a test map that passed every other row: 135 clocks, "
        "signs and chandeliers in or under the floor tile, 89 solid props "
        "drawn through each other, 31 hanging over a slab 55 to 70 units "
        "below, 77 hanging off the plinth they stand on and 34 through a perk "
        "machine.  A **warning** until the placer states its placements as "
        "relations; an error would fail every build meanwhile",
        "blueprint files",
    ),
    # ------------------------------------------------------------ file format
    Check("F1", "line 1 is 'iwmap 4' and line 2 is the starting-number line", "files"),
    Check("F2", "only layer declarations sit between the header and entity 0", "files"),
    Check("F3", "entities and brushes are numbered consecutively", "files"),
    Check("F4", "entity 0 is the worldspawn", "files"),
    Check("F5", "every entity and brush has a unique, well-formed guid", "files"),
    Check("F6", "every key/value line is two quoted strings", "files"),
    Check(
        "F7",
        "no number uses exponent notation and none is a negative zero; no "
        "shipped map contains one, and what cod2map64 does with one has never "
        "been tested",
        "files",
    ),
    Check("F8", "every face line has three points, a material and two sets of six numbers", "files"),
    Check(
        "F9",
        "every patch parses, including the layer line being the first line "
        "inside the inner block; anywhere else and cod2map64 stops with "
        "\"MatchToken: got 'mesh', expected '('\"",
        "files",
    ),
    # ----------------------------------------------------------- presentation
    Check(
        "Z24",
        "every asset declaration can actually resolve: a sound bank named "
        "after the map, present in the shared raw sound tree and under the "
        "104,729-row ceiling, with a wave file behind every row; no localize "
        "table; no literal purchase prompt in a script",
        "files",
    ),
    Check("Z14", "the manifest carries the six lines the linker needs", "files"),
    Check(
        "Z47",
        "no manifest line names an asset type the linker refuses: "
        "a Lua raw file is answered with 'ERROR: Lua not supported' and the "
        "link fails while still writing a fastfile (measured on "
        "Windows and reproduced under Wine)",
        "files",
    ),
    Check(
        "Z17",
        "every other manifest line is a type the linker acts on, and the two "
        "types that need a second half in the scripts have it: an fx is "
        "precached in the server script as 'fx' and in the client script as "
        "'client_fx', and a loose scriptparsetree is #using'd by the script "
        "of its own extension",
        "files",
    ),
    Check(
        "P1",
        "loadingimage.png is present and parses, at 1920x1080 -- the one size "
        "all 38 published examples agree on",
        "files",
    ),
    Check(
        "P2",
        "previewimage.png is present and parses. Its size is not checked: "
        "600x340 is the template's size and 23 of 39 published maps use it, "
        "but 16 use eight other sizes and are playable, so it is a house style "
        "rather than a requirement",
        "files",
    ),
    Check("P3", "the manifest has a >title line, and no comma in it", "files"),
    # ------------------------------------------------------------ build stages
    Check("leak", "the compiler's leak banner, which it prints while exiting 0", "stages"),
    Check("stage_error", "an ERROR: line in any stage's log", "stages"),
    Check("stage_failed", "a stage judged failed on evidence rather than exit code", "stages"),
    Check("missing_material", "a material the compiler could not find", "stages"),
    Check(
        "missing_material_benign",
        "a missing material known to come from a stock prefab",
        "stages",
    ),
    Check("umbra_unset", "no umbra volume found, so walls render as sky", "stages"),
    Check("caulk_terrain", "terrain patches with caulk, which render black", "stages"),
    Check(
        "preview_lighting",
        "the bake's output was not found, so the map renders washed out",
        "stages",
    ),
    # ----------------------------------------------------------------- manual
    Check(
        "M1",
        "the loading screen actually appears in game",
        "manual",
        "P1 proves the PNG is in the zone folder at the size every published "
        "map uses. That is necessary and, on the evidence so far, not "
        "sufficient: spec 6.1.2 records that previewimage.png shows and "
        "loadingimage.png does not for a local map. The candidate mechanism "
        "is that the full-screen image is not read as a loose file at all: it "
        "overrides a stock image asset named 'black', which also needs that "
        "asset's row commented out of the install's core_gfx.csv and an "
        "'image,black' line in the map's own zone file. A three-run A/B "
        "measured that this builds -- the linker packs the image "
        "only with the row commented out -- but nobody has seen it on screen, "
        "and 38 of 40 published maps ship the loose file anyway. Load the map "
        "and look. Format reference 3.6 has the evidence.",
    ),
    Check(
        "M2",
        "the baked map is lit the way the bake intended",
        "manual",
        "Whether the bake ran is automated now: it is a stage, it runs on any "
        "runner that reports provides_interactive_desktop -- an interactive "
        "Windows session or WineRunner's own X server -- and preview_lighting "
        "catches a missing bake in the link log. What is left is a judgement: "
        "a lighting file baked under Wine is a different size from one baked on "
        "Windows, and nobody has looked at a locally baked map in game.",
    ),
    Check(
        "M3",
        "a prop's collision was actually built and packed",
        "manual",
        "Z21 checks the map's keys. Whether export2bin produced the _col "
        "binary and the linker converted it with Collision: true is in the "
        "link log; the prop install step prints it.",
    ),
    Check(
        "M5",
        "the play-check list of spec 9.6 item 7",
        "manual",
        "Map loads; player spawns on the floor in the starting room; zombies "
        "rise and come through the windows in round 1; the first door opens "
        "and the next zone's risers pursue; perks, box, pack-a-punch and "
        "switch respond; round 7 does not hang; no script error on the "
        "console. A map carrying a loose script belongs on this list twice: "
        "Z17 holds its scriptparsetree and #using lines, and nothing can "
        "hold the entity it looks for, because only that script knows the "
        "targetname it wants.",
    ),
)

#: Every code the table names, in table order.
CODES: tuple[str, ...] = tuple(check.code for check in CHECKS)

BY_CODE: dict[str, Check] = {check.code: check for check in CHECKS}


def automated() -> tuple[Check, ...]:
    return tuple(check for check in CHECKS if check.is_automated)


def manual() -> tuple[Check, ...]:
    return tuple(check for check in CHECKS if not check.is_automated)
