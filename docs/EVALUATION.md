# Evaluation

How do we know the agent produces good research? We run it on businesses that **already exist**, where we
know the real competitors and broad shape of the market, and measure whether it rediscovers them and how well
it supports what it says. This is the "run demos on existing businesses to verify authenticity" milestone of
the project proposal.

## Running it

```bash
python eval/demo_cases.py                    # all cases, your configured model, live web
python eval/demo_cases.py --only zoom        # filter by name or idea text
python eval/demo_cases.py --mock --offline   # harness smoke test only (scores will be ~0)
```

Outputs: `outputs/eval-<case>.md` (full report), `outputs/eval-results.json` (metrics), and a summary table:

```
case       recall  top3 ok  fact %    grade   errors
uber       0.6     2        41        B       0
```

## Running without a search provider

If you have no Brave key or SearXNG instance, set `DISABLED_TOOLS=web_search` (or use
`scripts/setup_ollama.sh --disable-web-search`). Agents then rely on news, Wikipedia, Hacker News and page fetch.
Expect lower `competitor_recall` and `sources`; record this setting alongside your results so runs are comparable.

## Built-in cases (`eval/demo_cases.py`)

| Case | Idea given (deliberately generic; the company is never named) | Known competitors checked |
|---|---|---|
| airbnb | online marketplace for renting spare rooms and homes | booking, vrbo, expedia, hotels, hostel |
| duolingo | mobile app teaching languages with short gamified lessons | babbel, rosetta, busuu, memrise, duolingo |
| zoom | video-calling app for remote teams | zoom, teams, meet, webex, slack |
| uber | ride-hailing app connecting passengers and drivers | uber, lyft, bolt, didi, grab |

## Metrics

| Metric | Meaning | Good looks like |
|---|---|---|
| `competitor_recall` | known competitors found among all competitors listed / known list size | >= 0.6 |
| `top3_known_hits` | known competitors that landed in the report's top 3 | >= 2 |
| `top3_confirmed_in_sources` | top-3 names found in retrieved evidence | 3 |
| `fact_ratio` | share of findings that survived grounding checks as facts | >= 0.4 with a 14B+ model and a good search provider |
| `downgraded_claims` | claims the agent called facts that failed the checks | low, but non-zero is healthy: it shows the checker works |
| `sources` | distinct sources collected | >= 15 |
| `evidence_grade` | A-D, see [QUALITY_AND_EVIDENCE.md](QUALITY_AND_EVIDENCE.md) | B or better |
| `critic_redos` | number of agent redos the review loop triggered | 0-3 |
| `agent_errors` | agents that failed outright | none |
| `breakeven_year`, `ltv_cac` | plausibility of the economics for a known-successful business | break-even within 5 years, LTV/CAC around 3+ |
| `verdict` | what the system concluded | for a proven business, `go` or `validate_first`, not `no_go` |

## Reading results honestly

- **Low recall is not always the agent's fault.** Check the report: if the competitor was found in sources but
  listed as 4th, that is a ranking issue; if never retrieved, it is a search issue.
- **High `fact_ratio` with a weak model can still hide errors** (see the limits of lexical grounding). Spot-check
  a few cited claims by opening the source links.
- **Compare configurations, not just models.** Run the same cases with `--rounds 0` vs `--rounds 1` to measure what the
  critic loop buys, and with/without `BRAVE_API_KEY` to measure the search provider's effect.
- Results vary run to run and with the 24h cache; delete `.cache/` for a fresh measurement.

## Adding a case

Append to `CASES` in `eval/demo_cases.py`:

```python
{"name": "notion", "idea": "A workspace app combining notes, docs and lightweight databases for teams",
 "known_competitors": ["coda", "confluence", "evernote", "obsidian", "airtable"]},
```
Keep the idea generic (never name the company) and use lowercase substrings for the competitor list.

## Automated tests (`tests/`)

`pytest -q` runs 23 fast tests with no network or model: grounding checks, ledger behavior, financial math,
scenarios and sensitivity, competitor verification, rule-based gaps, grade and guardrail, provider fallback order,
the full pipeline with the mock LLM, the critic loop re-running an agent, and survival of a model that never emits
valid JSON. These test the *machinery*; the eval harness tests the *research quality*.
