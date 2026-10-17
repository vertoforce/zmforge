# Workflow: write a recipe and iterate

A map is a Python **recipe**: a function that returns a blueprint (rooms,
doors, props, quest, strings). zmforge turns it into the Radiant `.map`, the
scripts and the zone files, and checks it on the way. Any person or AI agent
can drive this loop; nothing in it calls a model.

```sh
zmforge generate zm_mymap --recipe <recipe> --tools-root "$TOOLS"  # write + model checks
zmforge check zm_mymap --tools-root "$TOOLS"                       # cross-file checks
zmforge render <recipe> --changed --compare latest                 # pictures of each room
zmforge review <recipe>                                            # review packet
```

## The loop

1. **Write or change the recipe.** Start from `one_room_map` or
   `three_room_map` in `src/zmforge/recipes/layouts.py`, and register the
   function in `RECIPES` in `src/zmforge/facade/cli.py`.
2. **Generate.** `generate` refuses to write a map that fails a model
   check, and names the element and the rule (Z-codes, listed in
   `src/zmforge/verify/registry.py`). Fix and run it again.
3. **Check.** `check` re-reads the written files; `requirements` prints one
   line per playability requirement.
4. **Look at it.** `render` shoots each changed room in Radiant. Open the
   contact sheet `build-out/render/<map>/latest/sheet.jpg` and the
   `compare/` before and after sheets. Fix floating, buried or clipped
   props, black surfaces, empty rooms and blocked doorways.
5. **Review it.** Build a packet and answer it (see
   [review-a-map.md](review-a-map.md)). Fix the high-severity findings
   first.
6. **Repeat** until the checks pass, the pictures look right and the review
   has no fails. Then build it with the mod tools and playtest.

<details><summary>Tips for agents</summary>

- Keep images you open at or under 1024 px. Contact sheets already are.
- Read `docs/map-principles.md` before designing a room; the review grades
  against it.
- A render runs alone on a machine; `render` waits for running builds and
  renders. Builds of different maps may run side by side
  (`docs/public/wiring-your-build.md`, "Running builds side by side").
- Run the tests (`pytest -q`) after changing library code, not only the
  recipe.

</details>
