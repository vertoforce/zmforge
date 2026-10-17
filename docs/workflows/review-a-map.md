# Workflow: review a map

zmforge does not call any AI model. It measures and photographs a map and
writes a **review packet**: one prompt per room plus one for the whole map,
each with its pictures and the JSON shape the answer must have. You, or any
AI agent you use, answer the packet. `zmforge review --import` then checks
the answers and writes the report.

```sh
zmforge review dmv                                   # 1. build the packet
#   ... answer every call in build-out/review/<map>-<time>.packet/ ...
zmforge review --import build-out/review/<map>-<time>.packet   # 3. grade it
```

## Steps for the reviewer

1. **Open the packet.** Read its `README.md`. It lists the calls in order:
   `room-<room>` for each room, then `map`.
2. **Review each room.** Read `room-<room>.prompt.md`. Open every image it
   lists under IMAGE FILES; they are Radiant renders with the real models.
   Judge the room against each principle in the prompt (P1 to P22 from
   `docs/map-principles.md`), citing prop ids, numbers or `file:line`.
   Quest text is meant to be terse (P17): an objective that names the
   challenge without saying where or how ("Shoot out the jack-o'-lanterns")
   is a pass, not a warning. Mark down the opposite: directions, room
   names used as locations, in-world maps, and broadcast chatter.
   Write `room-<room>.findings.json`: one JSON object that matches
   `room-<room>.schema.json`.
3. **Review the map.** Read `map.prompt.md`. Where it says ROOM REVIEWS,
   use your own room findings. Write `map.findings.json` against
   `map.schema.json`.
4. **Import.** Run `zmforge review --import <packet>`. If a file is missing
   or does not match its schema, it prints each problem and writes nothing;
   fix the files and run it again.
5. **Read the report** (`build-out/review/<map>-<time>.md`) and fix the
   recipe. The next `zmforge review` of the same map anchors each room on
   this report.

<details><summary>Rules the reviewer should keep</summary>

- Judge only what the facts, the source and the pictures show. Do not invent
  facts.
- Every verdict carries evidence: a prop id, an element id, a number, a
  string, a `file:line`, or an image file name.
- With pictures, judge P15 from the pictures first and list each problem
  under `visual_findings`. Any visual finding means P15 is not a pass.
- `n/a` is only for principles one room cannot show (quest variety,
  essentials, progression); judge the parts that live in the room.
- A room anchored on its previous review must answer every numbered old
  finding in `previous_findings` and list every changed verdict in
  `verdict_changes` with a reason. A changed verdict without a listed
  reason is set back to the old verdict on import.

</details>

<details><summary>Judgement items from the level design research</summary>

No check measures these yet, so the reviewer judges them. They come from published level design guides. Report each problem under `doesnt_make_sense`, citing the prop or room.

- **Landmark:** does each zone have one hero object players would name the zone after? Is it seen from where it fits the theme, and not from zones where it breaks the theme?
- **Telling detail:** does each scene show its cause with one prop (the paintbrush left under the slogan)? Does the cause echo the map's premise? An anonymous wreck is a missed chance.
- **Simulation boundaries:** nothing shows a death by something players use every day (a corpse crushed by a buyable door).
- **Something to miss:** is there an optional find off the main route that rewards the curious?
- **Quest payoff:** are targets not bullet sponges? Does a costly ending pay something back? Is the ending an event rather than a fade?
- **Views:** judge routes and landmarks from player-height views along the walk, not from the widest hero render.

</details>

<details><summary>The response schema</summary>

- Each call's exact schema is in the packet as `<call>.schema.json`.
- The source of truth is `src/zmforge/review/schema.py`. Its docstring lists
  every field.
- Room findings: `room`, `grade` (A to F), `score` (0 to 10), `summary`,
  `principles` (`id`, `verdict`, `evidence`, `suggested_fix`), `fixes`
  (`target`, `change`, `priority`), `doesnt_make_sense` (`finding`,
  `severity`, `where`, `suggested_fix`); plus `visual_findings` when the room
  has pictures, and `previous_findings` and `verdict_changes` when it is
  anchored.
- Map findings: the same without `room`, and verdicts without `n/a`.
- Extra keys are ignored. A findings file may wrap the JSON in a Markdown
  code fence.

</details>

<details><summary>Options: fewer rooms, no pictures, partial imports</summary>

- `--rooms a,b` builds calls for those rooms only.
- `--no-visual` skips the renders. P15 is then not judged from pictures.
- `--fresh` does not anchor rooms on the previous review.
- `--no-ai` only measures: it writes the facts and scorecard, no packet.
- `--import <packet> --partial` reports calls with no usable findings as
  errors instead of refusing the import.
- `--import <packet> --strict` exits 1 when any principle fails or a call
  has no usable findings.
- `--import <packet> --reviewer "<name>"` records who wrote the findings.
- A runner may write `<call>.meta.json` next to a findings file (cost, time,
  model). The report keeps it and adds up `total_cost_usd`.

</details>

<details><summary>Running it with a script instead of by hand</summary>

A runner is any program that answers the packet. It reads each prompt,
sends it with the call's images and schema to a model, and writes the
findings file. Room calls can run in parallel. The map call runs last,
with `zmforge.review.ai.room_digest()` of the room answers put in place of
the `ROOM_REVIEWS_LATER` text of `map.prompt.md`.

`scripts/review-with-claude.py <recipe> [review options]` is an example
runner. It calls the Claude Code CLI headless, with tools
off. Copy it as a template for any other model or agent.

</details>
