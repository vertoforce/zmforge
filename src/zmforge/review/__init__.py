"""An advisory design review of a generated map.

The tool side is deterministic; the judgement is done by whoever answers the
review packet (a person or any AI agent).

1. :mod:`zmforge.review.facts` generates the map into a scratch tools root and
   measures it: per-room prop tables (model, position against the walls and
   doors, what each prop stands on), a numeric scorecard per room, every
   on-screen line, the quest, the boss, the essentials and the door graph.
2. :mod:`zmforge.review.packet` writes a review packet: per room and for the
   whole map, a prompt built by :mod:`zmforge.review.ai` from those facts, the
   principles in ``docs/map-principles.md``, the relevant recipe source, the
   room's renders and its previous review, plus the answer's JSON schema
   (:mod:`zmforge.review.schema`).
3. ``zmforge review --import <packet>`` validates the reviewer's findings
   against the schema, holds unexplained verdict flips at the previous
   review, and writes the graded result under ``build-out/review/``.

``docs/workflows/review-a-map.md`` is the reviewer's side of it.  Nothing
here is part of the model checks or the regular test run: the hard rules
live in :mod:`zmforge.verify`; this is the judgement layer on top.
"""
