# Agent redesign (questions-v1, report-v4)

This document records why the agents were redesigned, how the new design works, what changed, how it was tested,
and what it still cannot do. The previous section design remains available (`AGENT_DESIGN=sections`).

## 1. Root causes of the report deficiencies

Diagnosed on the saved Nov 5 and Nov 6 climbing-app runs and the code that produced them.

| Problem | Where it came from | Root cause | Fix in this redesign |
|---|---|---|---|
| Customer analysis described a competitor's customers | retrieval + decomposition | The customer agent searched "<category> users/reviews" and got app pages; one call had to research, segment, size and price at once, so it summarised whatever came back. | Separate questions (problem/frequency, workarounds, willingness to pay) with forum-first queries; findings that describe a product (named, or from the product's own site) are moved out of customer evidence. |
| Unrelated businesses as competitors | retrieval + instructions | Candidate names came from any page that mentioned the category; the model was asked to fill a top-3 table. | Kept the existing identity agent (verified domain, direct/substitute/adjacent); competitor names now feed specific questions (complaints, prices). Generic first words such as "Climbing" no longer make every climbing blog a vendor site. |
| TAM/SAM/SOM "unknown" with no alternative | instructions + retrieval | Top-down market-size queries; no local count queries; the schema demanded three dollar figures. | A local-count question (people, venues or businesses in the launch area); out-of-area figures are kept as context only; when no count exists the memo gives the bottom-up method and compares it with the break-even volume. |
| Technical section repeated competitor features | retrieval + decomposition | Technical searches were category searches, which return product pages. | Feasibility questions search technical sources (architecture, APIs, open-source components) and must mention technical terms; trust and safety is a separate question for network products. |
| Arbitrary financials (four salaries, growth, churn) | instructions + model choice | A staffed-company five-year template was the only model; the 3B model guessed every input. | Stage-appropriate economics: MVP cash, lean monthly costs, contribution, break-even volume, funding to the next milestone, for solo / part-time / venture scenarios; every assumption has basis, rationale, range and sources; the 5-year cohort model only appears when inputs are evidence-based or illustration is requested. |
| Conclusions contradicting the numbers | synthesis prose | A model wrote the conclusions from summaries of the sections. | The verdict, key findings and implications are computed from validated data; the memo is assembled from it; a consistency check and the publication gate run on the memo text. |
| Generic or stage-inappropriate validation steps | synthesis templates | The synthesizer produced generic steps (including churn and CAC for a pre-launch app). | Experiments are chosen from the assumptions map (importance x weakest evidence) and use stage- and payer-specific templates (problem interviews, single-venue participation-and-return pilot, concierge service, fake door, paid pilot). |
| Repetition, no synthesis | rendering | Sections were concatenated; each repeated the same sources. | Each passage answers one question; the memo refers back to key findings instead of repeating them (0 duplicate sentences in the comparison below). |
| Retries detected but did not fix | decomposition of retries | A failing section was regenerated whole with the same evidence. | A failing question is retried alone with different source types and a stated reason; the repair is kept only if its status or independent evidence improves, and the outcome is logged. |

## 2. Architecture

Frameworks used for the questions and the decision: Y Combinator's idea-evaluation questions (problem acuteness,
who has it, competition and insight, market size, why now), Sequoia's business-plan outline (problem, solution, why
now, market, competition, business model), and Strategyzer's assumptions mapping (desirability, viability,
feasibility hypotheses; test the important ones with the least evidence first).

| Step | Module | Model use | What code guarantees |
|---|---|---|---|
| Coordinator plan (unchanged) | `pipeline._plan` | 1 call | |
| Research-planning agent | `brief.py` | 1 narrow restatement call | Founder's words kept: a restatement that adds concept-changing words ("stranger", "dating", "marketplace", "AI", ...) is rejected and flagged; geography only if the founder named it; stage never above what the text says; requests to the analyst ("Explore an MVP") are not part of the idea; payer and network effects inferred from the text; assumptions map built deterministically. |
| Competitor identity (unchanged) | `pipeline._competitors`, `identity.py` | as before | verified domains and relations |
| Question catalogue | `questions.py` | none | 8-11 questions from the brief only (no idea-specific code); each has preferred source types, targeted queries, a disconfirming query, fallback queries for repair, and a field check (what a finding must mention to count). |
| Question analysts | `analyst.py` | 1 small call per question (about 450 reply tokens) | Packet of at most 6 items, at most 2 per website, preferred source types first; findings validated for support, source independence, geography and question fit; vendor text is not customer or market evidence; vendor prices are not willingness to pay; a question is "answered" only with independent support. |
| Question-fit review | `analyst.review_answers` | 1 classification call | |
| Repairs | `pipeline._run_questions` | up to `QUESTION_REPAIRS` calls | only the failing question; kept only if measurably better; logged |
| Economics | `economics2.py` | none | all arithmetic |
| Synthesis | `synthesis.py` | none | evidence level per hypothesis (same passage counted once), cross-section checks X1-X8, key findings, conditional verdict, experiments |
| Report | `report_v4.py`, `memo_v4.py`, `render.py` | none | 7-section memo, appendix, publication gate and consistency check |

Saved runs (`python -m startup_cofounder.regenerate <run>.json`) are re-analysed from their saved sources only:
BM25 over the saved evidence per question, verbatim passages instead of model interpretation (labelled "evidence
located; not analysed"), no searches and no model calls. `--with-model` lets the local model interpret the same
saved evidence (about one small call per question).

## 3. Files

New: `startup_cofounder/brief.py`, `questions.py`, `analyst.py`, `economics2.py`, `synthesis.py`, `report_v4.py`,
`memo_v4.py`, `render.py`; `tests/test_agents_v4.py`, `tests/stubweb.py`; `eval/report_rubric.py`,
`eval/rubric_inputs.json`, `eval/examples/make_second_concept.py` and its two example files; this document.

Changed: `pipeline.py` (question design behind `AGENT_DESIGN`, `Assessment.v4`, report-v4 in `to_dict`),
`config.py` (`AGENT_DESIGN`, `QUESTION_REPAIRS`, `ILLUSTRATIVE_PROJECTION`), `tokens.py` and `llm.py` (reply budgets
and mock replies for the new roles), `validators.py` (generic first words no longer mark vendor sites),
`report.py`, `regenerate.py`, `app.py` (render either schema; v4 by default), tests that exercise the section design
now pin `agent_design="sections"`, README and CONFIGURATION.

## 4. Tests

`pytest -q`: 161 tests, no network and no model. `tests/test_agents_v4.py` (35 tests) covers: founder-idea
preservation (planner drift, analyst requests, drifting category, verbatim quote), competitor identity, customer
segmentation (product text is not customer evidence; contradicting evidence is kept and counted), geographic
applicability (national figure is not a local count; out-of-area findings are context only), unsupported pricing
(competitor price labelled; vendor price is not willingness to pay; placeholder disclosed), financial consistency
(break-even arithmetic, no automatic team, every assumption labelled, monthly normalisation, traceable memo
numbers), evidence independence (2 items per site; same passage counted once; vendor-only support does not answer
a customer question), cross-section contradictions (free competitor, cold start, unknown market; consistency check),
stage-appropriate experiments (no churn/LTV/CAC before launch; participation and return; B2B pilots), and a second
concept run end-to-end (B2B staff scheduling for coffee shops, on a fixed stub web with a scripted small model:
drift flagged, repairs measured, memo structure and length).

Mutation checks: disabling the fidelity check, the per-site limit, or adding "churn" to a pre-launch experiment
each makes the corresponding tests fail.

## 5. Old vs new (transparent comparison)

`python eval/report_rubric.py` computes these mechanically from the report text (no model). They are proxies; read
the reports themselves for judgement. D and E re-use the evidence the old agents gathered, so they show the effect
of the new planning, validation, synthesis, economics and experiments, not of the new research queries.

| Metric | A original workflow (Nov 5) | B adaptive-v2 (Nov 6) | C report-v3 memo (Nov 6 data) | D report-v4 (Nov 6 data, no model) | E report-v4 (Nov 5 data, no model) |
|---|---|---|---|---|---|
| words in main report | 3503 | 5025 | 1830 | 1581 | 1592 |
| duplicate sentences | 18 | 15 | 0 | 0 | 0 |
| founder's idea quoted verbatim | no | no | no | yes | yes |
| cited sources | 61 | 85 | 6 | 4 | 5 |
| distinct websites | 51 | 51 | 3 | 4 | 5 |
| vendor / app-listing share of citations | 0.13 | 0.36 | 0.67 | 0.0 | 0.0 |
| off-topic share of citations | 0.64 | 0.04 | 0.0 | 0.0 | 0.0 |
| implication statements | 0 | 0 | 5 | 10 | 10 |
| conditional verdict | no | no | yes | yes | yes |
| 5-year table shown | yes | yes | no | no | no |
| salaried roles in main report | 2 | 2 | 0 | 0 | 0 |
| lean / solo scenario | no | yes | no | yes | yes |
| regex overclaims | market "large/growing" | none | none | none | none |
| experiments with thresholds | 0 | 0 | 1 | 3 | 3 |
| stage-inappropriate terms in validation | none | CAC, churn | none | none | none |
| untraced numbers (publication gate) | - | - | 0 | 0 | 0 |

What this supports: the v4 memo is shorter, does not repeat itself, keeps the founder's wording, cites no vendor
or off-topic pages as evidence, gives conditional reasons and stage-appropriate experiments, and does not show
unsupported multi-year projections. What it does not show: that the new research queries find better evidence (no
live run was made), or that a founder would find the report more useful (no user study). "Contradicting evidence
mentions" is 0 in D and E because the saved evidence was not analysed by a model, so no stance was assigned; the
second-concept test shows contradicting evidence being found and counted when a model assigns stances.

## 6. Limitations and next steps

- Not yet run live. The question design has been exercised with the mock model, a scripted small model and a
  fixed stub web. A short live run with qwen2.5:3b (for example `--smoke`) is needed to measure answer quality,
  JSON reliability and run time on the 8 GB Mac; this needs your approval.
- Stance (supports / contradicts) is assigned by the 3B model and is fallible; code checks support and question
  fit, not whether the stance is right.
- The field checks (what a finding must mention) are keyword rules; they can reject a valid paraphrase or accept
  an on-topic but useless sentence.
- Economics defaults (scenario costs, 4% paying share, fees) are rules of thumb, clearly labelled; they should be
  replaced by the founder's own numbers or test results.
- Experiment templates cover common consumer, network and B2B cases; unusual ideas (hardware, regulated health,
  marketplaces with two sides) need additional templates.
- Free web search rarely yields local counts; the memo then gives the bottom-up method instead of a number.
- Next: run the smoke test live; add founder inputs (budget, time, team) to the brief; add a second-side question
  set for marketplaces; let the founder record experiment results so the assumptions map updates.
