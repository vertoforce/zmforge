# Working on zmforge with Claude Code

zmforge turns a Python recipe into a Black Ops III zombies map and checks it.
Your job is usually to write or change a recipe, then loop until the checks
pass and the pictures look right.

- The loop, step by step: `docs/workflows/build-a-map.md`.
- Reviewing a map against the design rules: `docs/workflows/review-a-map.md`.
- Design rules the review grades against: `docs/map-principles.md`.

Rules:

- Change the recipe or the generator, never the written `.map` files by hand.
- A fix that would help any map belongs in the generator, with a check and a
  test, not as a one-off in one recipe.
- Run `pytest -q` after changing library code, not only the recipe.
- Keep any image you open at or under 1024 px. Contact sheets already are.
- Never launch or close the game for the user. Ask them to playtest.
