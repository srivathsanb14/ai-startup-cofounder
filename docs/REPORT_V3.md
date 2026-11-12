# Report v3: decision memo, evidence appendix, structured JSON

Since 2026-11-06 every run (and any saved run) produces three outputs from one validated data model
(`startup_cofounder/report_model.py`, schema `report-v3`):

| Output | File | Purpose |
|---|---|---|
| Founder decision memo | `assessment-<time>.md` | 7 sections, about 1,200-1,800 words: decision, customer, competition, reachable market, MVP and risks, economics, validation plan |
| Evidence and methodology appendix | `assessment-<time>-appendix.md` | corrections, open questions, claim checks, assumption register, calculations, issues, research history, sources, runtime |
| Structured data | `assessment-<time>.json` | the raw run plus `report_schema: "report-v3"` and `report` (the model the memo was rendered from) |

The structure follows the lean-plan idea (a short, decision-focused plan with details in an appendix) and tests the
most critical hypotheses first, grouped as desirability, feasibility and viability.

## What is guaranteed by construction

* **Financial headlines come from code.** Break-even, cash payback, yearly operating result and funding need are
  computed from the projection. Model prose that contradicts them is removed, checked clause by clause, so
  "break-even within 5 years, *but* payback is not" is still caught.
* **Targets are not forecasts.** A goal such as "break even in five years" is shown as a founder target, next to what
  the scenario actually shows. Targets with impossible values (e.g. a margin above 100%) are dropped.
* **Rejected claims don't survive.** Unsupported or contradicted claims are removed from summaries, and so is local
  growth asserted from national or global evidence.
* **Evidence rules.** A question ("Is X free to use?") can't support its answer. A source about a broader area
  can't fully support a local claim. A vendor describing itself is labelled "source-reported". A factual statement
  without a citation is "unsupported"; it doesn't become an "assumption" by lacking a number. Saved labels are
  only ever downgraded.
* **Role purpose.** A customer section about an existing product's users is withheld. Competitor prices are not
  willingness to pay. Missing information is never white space or a weakness. Product names are not architecture
  components, and an effort estimate without components is withheld. Safety and privacy sections need concrete
  scenarios with controls and limitations.
* **Unknowns are actionable.** Each open question says why it matters, what is and isn't established, the next
  action, and whether that action is web research or a founder test. Founder tests are never sent back to a web
  research agent as a retry.
* **Honest status.** Run status (finished or incomplete) is shown separately from evidence adequacy (adequate,
  partial, insufficient). The old letter grade is no longer shown. If research didn't finish, the decision is withheld.

## Commands

    # re-render a saved run (no research, no model calls); writes -memo.md, -appendix.md, -v3.json beside it
    .venv/bin/python -m startup_cofounder.regenerate outputs/assessment-20261106-140151-696771.json

    # the app can also open any saved run: sidebar -> "Open a saved report"
    ./run-one-hour.command

## Live-run changes behind the report

Role prompts and schemas now ask each agent its decision questions (`agents/specs.py`, `schemas.py`).
`substance.py` checks the answers deterministically. Research keeps a reserve of searches and page reads for later
sections and review retries. Impossible or duplicate actions are rejected with a reason the agent sees, and research
stops after two such rejections in a row. A retry counts as success only if it resolves an issue or adds supporting
evidence.

## v3.1 validation layers (2026-11-09)

`startup_cofounder/validators.py` adds five deterministic layers, used by both live runs and regeneration:
source credibility and independence, recency, plausibility heuristics, cross-section consistency, and a publication
gate on the rendered memo. Claim verification now includes a hidden control item; when the model fact-checker accepts
it, its upgrades for that batch are ignored. `eval/validator_benchmark.py` measures each layer against
hand-labelled cases. See `docs/COMPARISON_WITH_ORIGINAL.md` for results.
