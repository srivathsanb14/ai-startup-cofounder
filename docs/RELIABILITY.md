# Reliability workflow (adaptive-v2, 2026-11-06)

This document explains the reliability rework: what failed in the run of 2026-11-05, how the workflow now
works, how to run and compare it, and what the tests prove and don't.
Backups of every file changed are in `backups/before-reliability-20261106/`.

## 1. What went wrong (diagnosis of `outputs/assessment-20261105-155236-096579.*`)

| # | Observed failure | Root cause in the old code |
|---|---|---|
| 1, 2 | KAYA hotels / kaya spread / property software and SENDO phones listed as competitors and "verified" | `name_seen()` marked any name that appeared anywhere in the source pool as verified; profile queries (`"KAYA pricing plans"`) had no category context; a missing `is_competitor` was treated as approval |
| 3 | Specialist wrote about Taylor Swift's Eras Tour | Specialist query `wikipedia(<focus>)` returned unrelated pages; `rank()` filled empty slots with zero-score items; the grounding check passed on shared words |
| 4, 5 | $400/month price from healthcare-marketing software; conflict with $50 willingness to pay | The financial planner received every section, including the off-topic one, plus unclassified price evidence; nothing compared price with willingness to pay |
| 6, 7 | TAM/SAM/SOM = 0; empty technical lists, one sentence repeated six times, still a score and timeline | Only presence of a score was checked; zero values and duplicates were not issues. Likely amplified by prompt overflow (below) |
| 8, 9 | "10,000 paying customers" vs 100 modelled; "$160 gross profit" rendered as "160% gross margin" | No review of the memo after synthesis |
| 10 | Three rounds flagged the same sections, each retry "improved" | One gap per agent with rule gaps first; `followup_task` dropped; `improved` = "returned valid JSON"; follow-up queries were fixed templates, so every retry fetched the same results |
| 11 | Grade B, no warnings | Grade counted volume: 357 sources, findings labelled fact (many about wrong companies), names seen anywhere |
| ctx | (cross-cutting) | Replies could use up to `LLM_MAX_TOKENS=2400` of Ollama's default 4096-token context, leaving ~1.7K tokens for prompts that were often larger (18 × 650-char evidence items + schema + previous answer). Ollama drops the start of an over-long prompt, which is where the rules and task were. `_brief()` also cut JSON at a fixed character count |

## 2. How the workflow works now

```
coordinator plan -> research frame (category anchor terms, customer, payer, geography)
for each section (sequential with MAX_WORKERS=1):
    seed searches (templates, kept as a starting point)
    -> relevance gate: every source scored against the frame; irrelevant sources never enter a prompt
    -> zero relevant results => deterministic reformulation (never the same query twice)
    -> planner model proposes ONE JSON action {search | fetch | finish}; Python validates and executes it
    -> token-fitted evidence (whole items, sentence-boundary shortening, duplicates removed)
    -> extraction -> claim records -> one batched model check of the claims (fallible, recorded separately)
review rounds: deterministic issues + critic issues, stable ids and severities
    -> retry with the FULL correction list (also passed to the planner, so research changes too)
    -> same checks re-run; answers scored; better one kept; outcome labelled honestly
    -> stop when nothing is open, budget is reached, or a whole round makes no measurable progress
financial: inputs validated (value, unit, payer, period, basis, price-evidence type, WTP check)
    -> one correction pass if high-severity problems -> deterministic model -> labelled illustrative unless backed
synthesis -> final review against computed numbers -> one correction -> remaining problems removed in place and disclosed
scorecard: execution status separate from research quality; grade capped by unresolved problems
```

New modules (all small, no framework):

| Module | Responsibility |
|---|---|
| `tokens.py` | conservative token estimates, per-role reply limits, prompt fitting by whole items |
| `relevance.py` | research frame, relevance scoring, removal of instruction-like text from web pages |
| `research.py` | validated action schema, section and run budgets, the adaptive loop, reformulation |
| `identity.py` | competitor identity (domain, description, customer), relation classes, identity-based merge |
| `claims.py` | claim records with exact passage and status; lexical screen vs model check |
| `issues.py` | issue register, deterministic section checks, scheduling, retry measurement |
| `fininputs.py` | financial input records, price-evidence categories, willingness-to-pay check |
| `final_review.py` | memo checks against computed numbers, disclosure |
| `scorecard.py` | execution vs research-quality reporting and capped grade |
| `audit.py` | re-checks any saved assessment JSON (old or new) without a model |

### Safety of tool use
The only model-controlled actions are `search` (known tool, 3-120 characters, no URLs or shell characters,
not a repeat) and `fetch` (only a result id already shown to the model, public http(s) host, HTML only,
not read before). Nothing a model writes is executed. Retrieved pages are framed as untrusted data and
instruction-like phrases are removed.

### Budgets (all configurable)
`RUN_MINUTES` remains a ceiling, with time reserved for financials and the report. Per section:
`SECTION_SEARCHES` (5), `SECTION_FETCHES` (2), `PLANNER_STEPS` (2), and a time share of what's left.
Per run: `RUN_SEARCHES` (45), `RUN_FETCHES` (16). Review: `CRITIC_ROUNDS` (≤3), at most 3 sections per
round, each issue retried at most twice. Extraction repairs: at most 2. `LLM_CONTEXT_TOKENS` (4096) must
match the real server window; `LLM_MAX_TOKENS` stays the reply ceiling.

## 3. Before/after for each observed error

| Failure | Now |
|---|---|
| 1 KAYA mixed with hotels and software | Profile searches include category terms; a profile counts only if a source mentions the name together with the category and its description is in-category; merging is by official domain, never by name |
| 2 SENDO verified | Name-only matches give `unresolved` or `irrelevant`; those are listed separately and never counted |
| 3 Eras Tour specialist | Off-topic sources are excluded before extraction; an off-topic section raises a high-severity issue; claims citing only off-topic sources are `unsupported` |
| 4 $400 from healthcare software | Price evidence is classified (consumer app / category business software / venue or membership fee / unrelated business software); a mismatch with the payer makes the input unsupported; off-topic sections are excluded from the planner's context |
| 5 $50 WTP vs $400 | High-severity contradiction issue, one corrective retry, a WTP-anchored scenario, and the projection labelled ILLUSTRATIVE |
| 6 TAM = 0 | High-severity issue unless the method states sizing is unknown; reported as "unknown", not $0 |
| 7 Empty technical, repeated sentence | Empty components/risks, duplicates and an unfounded score are high-severity issues; the score isn't shown without components |
| 8 10,000 customers | Final review checks customer counts against the projection; the sentence is corrected or removed and disclosed |
| 9 160% margin | Dollar vs percentage check; facts sheet states "gross profit $X (dollars, NOT a percentage)" and "gross margin Y%" |
| 10 "improved" every time | Outcomes are improved / partially improved / no progress / unchanged / worse / failed, with scores before and after and which answer was kept; the round stops if nothing moves |
| 11 Grade B | Scorecard: source relevance, claim support, competitor identity, section completeness and unresolved issues are shown separately. Grade is capped by high-severity issues, off-topic sections, incomplete execution and an illustrative projection. Re-auditing the saved run finds 13 high-severity issues |

## 4. Commands

Run the tests (needs pytest in the project venv: `.venv/bin/pip install pytest`, already in requirements.txt):

    .venv/bin/python -m pytest -q

Re-audit a saved run with the new validators (no model, seconds):

    .venv/bin/python -m startup_cofounder.audit outputs/assessment-20261105-155236-096579.json

Short live smoke test (Ollama running, ~12-minute ceiling, live web search):

    ./run-smoke-test.command

Full research run (Streamlit UI, 60-minute ceiling, report auto-saved in outputs/):

    ./run-one-hour.command

Same-evidence comparison of baseline vs improved workflow (two full runs with the local model; run only when
you have the time):

    .venv/bin/python eval/compare_workflows.py --evidence outputs/assessment-20261105-155236-096579.json --minutes 45

Measure memory before raising the context window:

    .venv/bin/python scripts/measure_context.py --sizes 4096 8192

## 5. What the tests prove, and what they don't

They prove, deterministically and without a model or network:
the saved failed run is re-detected (wrong companies, off-topic specialist, wrong-category price, WTP
conflict, empty market and technical sections, customer-count and %/$ errors); identity-based merging;
honest retry labels and keeping the better answer; that high-severity issues aren't crowded out; that full
reviewer instructions reach the extractor and the planner; that unsafe or repeated actions are rejected;
budgets and a marked partial result; prompt fitting; traces saved without secrets; and that both workflows
replay on the same frozen evidence.

They don't prove that a 3B model will *produce* good research: whether it follows the action schema,
writes on-topic sections, or fixes issues when asked. That needs the live smoke test, the same-evidence
comparison, and a human read of the report. Relevance scoring is lexical, so a page that uses the
category words but is about something else can pass as "weak" or "relevant", and a relevant page that
uses synonyms can be missed. The model check of claims is itself fallible and is labelled as such.
