# Current version vs. the original repository (assessed 2026-11-09)

Original: https://github.com/srivathsanb14/ai-startup-cofounder (commit `fd03bd2`). Your Nov 5 run used that code
plus your one-hour budget edits, so it stands in for the original workflow. The Nov 6 run used adaptive-v2. Both
saved runs are scored here with the same current validators (`python -m startup_cofounder.audit <json>`), so the
yardstick is identical.

## Outcomes on the same idea

| | Original workflow (Nov 5) | Current (Nov 6 run, report v3.1) |
|---|---|---|
| Code size / tests | 2,650 lines / 47 tests | ~7,900 lines / 126 tests |
| Cited sources that are off-topic | 67 of 99 | 0 of 51 |
| "Verified" competitors that were the wrong company | 5 of 6 | 0 |
| False numeric statements in the memo | 4 (10,000 customers, 160% margin, ...) | 3 in raw model prose, all removed before publishing |
| Retries labelled "improved" | 9 of 9, none fixed anything | measured outcomes; loop stopped on no progress |
| Self-reported quality | grade B, no warnings | no letter grade; evidence adequacy "insufficient", with reasons |
| Citations behind supported claims from the competitors' own sites | not measured | 85% (now measured and shown) |

## Validation layers

| Layer | Original | Current |
|---|---|---|
| Relevance of evidence | none (zero-score passages filled packs) | frame-based gate |
| Competitor identity | name appears anywhere | name + category co-occurrence, domain, relation |
| Claim grounding | number/word overlap = "fact" | lexical screen (max "partial") + model check + re-screen |
| Source credibility and independence | none | source types, vendor-only flag, single-website flag |
| Recency | none | dated statistics capped |
| Questions as evidence, local vs national | none | rejected / capped |
| Role substance (customer, competitor, market, technical, risk) | presence of fields | decision-question checks |
| Financial inputs | clamped to ranges | evidence category, willingness-to-pay check, placeholders, plausibility heuristics |
| Cross-section consistency | none | customers vs market, price vs free alternatives, team vs revenue |
| Memo vs computed numbers | none | financial headlines computed by code; clause-level contradiction check |
| Fact-checker reliability | n/a | control probe per batch; labelled benchmark |
| Publication gate | none | every number in the memo traced to validated data |

## Measured accuracy of the layers

Run `python eval/validator_benchmark.py` (labels: `eval/gold/validator_gold.json`, 77 hand-labelled cases):

| Layer | Cases | Accuracy | False accept | False reject |
|---|---|---|---|---|
| relevance gate | 25 | 1.0 | 0 | 0 |
| source type | 15 | 1.0 | - | - |
| claim support (code only) | 16 | 0.75 | 4 | 0 |
| claim support (as saved: code + 3B check) | 16 | 0.81 | 3 | 0 |
| claim support (published: saved + v3.1 re-screen) | 16 | 0.94 | 1 | 0 |
| competitor identity | 11 | 0.91 | 0 | 1 |
| financial statements | 10 | 1.0 | - | - |

The sample is small and was labelled by the same assistant that wrote the validators, so treat these as regression
checks, not proof. Extend and correct the labels when you inspect real runs. Add `--model qwen2.5:3b-instruct` to
measure the 3B fact-checker itself on your Mac.

## What still limits the results

* Correction lags detection: the Nov 6 run ended with 9 unresolved high-severity issues. Retries with a 3B model
  rarely fix what the checks find.
* The evidence is mostly vendors describing themselves. Independent sources (reviews, forums, local press) are thin.
* The lexical claim screen cannot judge meaning: it accepted 4 of 16 wrong claims on its own. The model check and the
  re-screen bring that down, but the model check is fallible (hence the control probe).
* The publication gate cannot catch small integers (1-10), so a wrong "year 3" would pass.
* Founder-only questions (target segment, willingness to pay, matching density) can't be answered by desk research.
