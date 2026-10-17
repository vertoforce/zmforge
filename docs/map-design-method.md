# Map design method: every area is a scene

**Short answer.** Design each area as a scene. Write one line saying what happened there. That line picks the set pieces, the damage, the fire and smoke, and the props. Then dress it to the stock map's numbers: dense at three heights, lanes split by set pieces, every fire a pool of light, and dressed walls under a real sky. The numbers come from a density count of the stock map `zm_giant`. The `S1`-`S4` checks and the review's `art` block hold every room to them.

## 1. Scene first
Write the story before placing anything: "The school bus hit the gas main; the houses either side are still burning." Declare it with `dressing.declare_scene(bp, room, story, beats=("fire", "wreck"))`. Each beat is a promise the room must show: `fire`, `smoke`, `embers`, `wreck`, `barricade`, `body`, `flood`, `flies`. A prop that does not serve the story is filler.

<details><summary>What a scene decides</summary>

- **Set pieces**: the one or two big objects the story is about (the bus, the collapsed tower). Stock: 2.1 per 1000 x 1000 units, about 330 units apart.
- **Damage**: which walls are broken, what is burnt, what spilled. Stock: 2.9 fire spots, 4.3 barricade spots and 2.1 wreck spots per 1000 x 1000 units.
- **FX and light**: where it still burns, smoulders or sparks (section 4).
- **Props**: what people left behind, in drifts and heaps where the event threw them.
- **Plants**: in natural clumps of mixed size at the feet of things, with bare gaps, never spread evenly (`dressing.cluster`, `Z66`).
</details>

## 2. Set pieces make the lanes
Players should squeeze between things, not cross an empty floor. Set pieces, wrecks and barricades split the walkable floor. Aim for a median lane of about **256 units**. About a fifth of the floor should be under 160 units wide. Almost none of it (stock 7%) should be over 512. Put at least one pinch point (narrow floor joining two wider areas) in each large area.

<details><summary>Targets and how they are measured</summary>

- Stock widths: p10 112, p50 256, p90 448 units (largest disk in the walkable floor that covers each point). Stock pinch points: 0.66 per 1000 x 1000 units. Brush-only, so an upper bound.
- The review's `art.corridors` reports the same measure per room: solid props taller than a step are the obstacles. `S3` warns on a room over 0.5 k2 (1000 x 1000 units = 1 k2) with no set piece.
- Keep P3 in mind: a lane never closes. Z55 still floods every room.
</details>

## 3. Three layers
Dress the ground, the middle and the space overhead. Stock puts 19% of its props above ground: 399 per k2 at 48-160 units (conduit, lamps, signs, shelves) and 113 overhead (pipes, wires, lamp shades, beams).

<details><summary>Density targets per 1000 x 1000 units</summary>

- Stock: 2,645 props in all, 1,148 if kit trim (beams, brackets, conduit) is left out. zmforge makes trim from brushes, so 1,148 is the fair target. `S2` warns under a quarter of it (287), and when a room over 0.25 k2 has nothing at all above ground.
- Variety: 306 distinct models per 1000 x 1000 cell in stock.
- Litter still counts only up to a quarter (P2).
</details>

## 4. Light pools and FX
Every fire is a light source: flames, embers above, smoke over, a warm lamp under. Leave dark gaps between pools. Stock keeps 95% of the floor within 256 units of a light and 75% of lights warm, with 75 effects per k2. Use `dressing.burning`, `dressing.smouldering` and `dressing.embers`. They place only effects measured to link in a usermap.

<details><summary>FX targets and what links</summary>

- Stock places effects as Radiant `fx` entities (`fxdef`), not script. zmforge does the same (`AmbientFx`), and declares each one in the zone.
- Linked clean with the stock mod tools: rubble fire with embers, window fire (two sizes), ember lines, smoulder, hot ground, a black plume for the skyline, and a smoke line. Barrel fires, sparks and flies do not link (missing images).
- `S4` warns when an open-air room has no effect at all. `S1` warns when a scene promises fire, smoke or embers and the room has none.
</details>

## 5. Boundaries and backdrops
No edge of the play space should be a flat wall under a black sky. Walls get piers, coping, props against them and broken tops (`dressing.boundary_wall`, Z62). Open air shows the sky, with silhouettes rising beyond the wall in rows at growing depth (`dressing.backdrop`, Z63). A roofed building seen over a low wall gets a real facade and roof (`dressing.facade`, Z65).

<details><summary>How stock does it</summary>

- zm_giant is enclosed: building faces just past the play space and a `vsky` sky with lightning. mp_sector stands vista models 5,000 to 30,000 units out (mountains, plateaus, water towers, powerline towers).
- A burning plume (`dressing.smouldering(..., plume=True)`) on the skyline tells the story past the wall.
</details>

## 6. Weathered materials
Nothing is clean. Half of stock brush materials are named wet, worn, rust, dirty, aged or grunge. Pick the worn variant, add decals, and let moss, soot and peeling paint follow the story (soot above a fire, damp under a leak).

## 7. Let players figure it out (P17)
The scene tells the story without text. No sign explains the wreck and no map shows the way. The objective names the challenge and the player works out the rest.

## 8. Play structure and telling details (from the literature)
*Research-derived.* Items marked **Enforced** are warnings in `verify/design.py` (`D` codes) or `verify/scenes.py` (`S1`); the rest are guidance a check does not enforce. Each item comes from published level design guides. Sections 1-7 make an area look like a real place. This section makes it play and read like a zombies map.

- **Train, then transit.** Every area the player can hold has a closed ring round a central block, with lanes of at least 128 units. Narrow lanes and pinch points (section 2) belong in transit between areas, not in the training ring. **Enforced:** `D1` (every zone with zombie spawns; ring at least 1000 units round).
- **One way out is fine.** A room with a perk or a buy does not need a second exit. Not checked.
- **Cheap to the core.** Juggernog, Quick Revive and the first quest part lie on, or one door off, the cheapest path from spawn to power. Keep the door spend to reach Juggernog modest. Wall buys rise in value the deeper they sit. **Enforced as a fact:** `D3`, the review's `map.points_to_core` (door spend from spawn to Juggernog, Quick Revive, power and the first box), with no threshold until stock maps are measured.
- **Lock before key.** Players see the lock (buildable table, Pack-a-Punch, quest door) before they find its first key. A lock that needs N keys shows N sockets or lamps. **Enforced:** `D4` (a quest's hand-in desk and buyable exit open no later, by door spend, than their first key's zone); the sockets are not checked.
- **Light the play first.** Light doors, buyables and quest stations before the mood pools, and brighter than filler. Light the centre of each training ring. Dark gaps never sit on the route to a door or buyable. **Enforced:** `D5` (a lamp within 192 units, as bright as filler within 512; a lamp within 256 of each ring's centre; no point over 256 from a lamp on the straight way from a room's doorways).
- **One landmark per zone.** Each zone has one unique, tall hero object that stands out against short surroundings. Players see it from the zone's entrances and from next door, and it fits the theme wherever it shows. Hub rooms show two or more.
- **Telegraph the threat.** Riser spawns sit on disturbed ground (mud, split graves, broken floor), and barricade windows read as entries.
- **Cause and the telling detail.** Beside "what happened", each scene names its cause and one prop that proves it: the paintbrush left under the slogan. The cause ties back to the map's premise. Never show a death by something players use every day, such as a buyable door. **Enforced:** `declare_scene(..., cause=, tell=)`; `S1` warns when no prop in the room matches `tell`, or a `cause` has no `tell`. The tie to the premise is the reviewer's.
- **Derelict enough.** If people could still live or work in a room without worry, it is too tidy. Tip, break, burn and scatter.
- **Clean fronts.** Keep tall dressing out of the space in front of anything the player uses. Keep dressing along the main route low. **Enforced:** `D6` (no floor-standing prop over 24 units tall in the 96 units in front; the `Z60` `clearance_front` box).
- **Tension, then quiet.** No random loud stingers. A scare lands only at a quest step's peak, and the moments after a step stay quiet.
- **Walk it before the test.** A timed quest step runs through zones the player has already crossed.
- **Something to miss.** Put at least one optional find off the main route.
- **Power changes the light** (*unverified in BO3*): electric lamps are dark before the switch and come on with it.

<details><summary>What the literature warns against</summary>

- Do not judge wayfinding or landmarks from a framed hero shot. The Level Design Book calls this the "shot composition fallacy". Keep the renders for defects, and judge routes from player-height views along them.
- Prospect-refuge and shape or colour psychology are weak theory. Use genre conventions instead (the lightning bolt means power).
- Lightning-bolt symbols toward power are allowed (P17): every commit paints one beside each door on the cheapest spawn-to-power route, on the approach side, but not the door into the power room or within 300 units of the switch (`dressing.power_bolts`; opt out with `bp.power_bolts = False`).
</details>

<details><summary>Checklist for a new area</summary>

1. One-line story and beats: `declare_scene`.
2. One or two set pieces that split the floor into lanes near 256 wide, with a pinch.
3. Props at three heights; worn materials; litter in drifts.
   Plants grow in clumps, not an even scatter: a big bush with smaller ones and grass round it, gathered at wall feet, grave edges, kerbs and tree bases, bare ground between and along the walks (`dressing.cluster.mixed_clumps`; `Z66`).
4. Every fire lit; dark between pools; smoke on the skyline.
5. Walls dressed; sky and silhouettes over them.
6. Run `zmforge review`: read each room's `art` block against its `stock` numbers, and fix any `S` warnings.
</details>

**Reference map:** the cemetery map is the reference for atmosphere, paths, props and quest, and every other map is judged against it.
