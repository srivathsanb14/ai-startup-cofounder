# AI Startup Co-Founder

**An evidence-backed startup assessment from a rough business idea, produced by a team of cooperating LLM roles.**

*Agents of Chaos: AI Agents for Engineers, Fall 2026 (project idea #39).
Team: Owen Liston, Jacob Barry, Srivathsan Badrinarayanan, Jimmy Wang.*

You type: *"A subscription service that matches small restaurants with local farms"*.
You get a report with customers, the top-3 competitors, market size, technical feasibility,
organizational structure, a 5-year financial model with scenarios, risks, and a ranked list of
experiments to run next. Every claim is labelled **fact** (with a citation you can click) or
**estimate**, and the report grades how well-supported the whole thing is.

> This is preliminary desk research. It tells you which assumptions to test first; it does not replace
> talking to customers.

> **Reliability workflow (Nov 2026).** Research is now a bounded adaptive loop (agents request searches and page
> reads; Python validates and runs them). Evidence is gated by relevance, competitors need identity evidence,
> claims carry exact passages and support status, retries are measured, financial inputs are validated against
> willingness to pay, and the memo is checked against the computed numbers before it is saved. The report shows
> execution status separately from research quality. See [docs/RELIABILITY.md](docs/RELIABILITY.md).

---

## Why this is different from asking a chatbot

| Problem with a plain chat answer | What this project does about it |
|---|---|
| Confident claims with no sources | Every search result gets an id (`E1`, `E2`...). Every claim must cite ids, and claims are **machine-checked against the cited text**. |
| Invented numbers | A "fact" is downgraded to "estimate" if its numbers don't appear in the cited source. |
| Invented competitors | Names are extracted from search results, ranked by how often they appear in the evidence, profiled with their own searches, and checked again against everything retrieved. |
| Made-up financial math | The LLM only proposes assumptions. Code computes the model, so it is consistent and reproducible. |
| Slow, brittle generation | Code runs the searches, pages are read in full, output is schema-constrained, and every stage is checkpointed. |
| One-shot answer, no self-review | A **critic** (automatic rules + an LLM reviewer) sends weak sections back for another research pass. |
| Over-optimistic "go!" verdicts | A **guardrail** refuses "go" unless evidence is strong, LTV/CAC >= 3 and the business breaks even. |
| One fixed template for every idea | The coordinator can **spawn extra specialists** (e.g. regulation, supply chain) when an idea needs them. |

## How it works

The default design (`AGENT_DESIGN=questions`, report-v4) works like a careful analyst: first understand the idea,
then answer specific questions with targeted evidence, then decide. Models make small, narrow JSON calls; code does
the searching, validation, arithmetic and synthesis. Every stage is checkpointed, so an interrupted run resumes.

```
 founder's idea
     │
     ▼
 Research-planning agent ─► idea brief (founder's words kept; drift flagged) + assumptions map
     │                       (desirability / viability / feasibility hypotheses, most important first)
     ▼
 Competitor identity agent ─► verified direct competitors, substitutes, adjacent products
     │
     ▼
 Question analysts (one small call each): problem & frequency, current workarounds, willingness to pay,
   revenue models, local market count, channels, feasibility, failure cases, competitor complaints,
   cold start and trust (network products)
     targeted queries by source type + a disconfirming query ─► packet (≤2 items per website)
     ─► findings typed fact/estimate, stance supports/contradicts ─► code validation (support, independence,
     geography, question fit, product-vs-customer)
     │
     ▼
 Question-fit review (1 call) ─► bounded repairs of the weakest questions (kept only if measurably better)
     │
     ▼
 Deterministic: stage-appropriate economics (solo / part-time / venture) ─► cross-section checks
   ─► 3-5 key findings ─► conditional verdict ─► 2-3 experiments for the riskiest assumptions
     │
     ▼
 Decision memo (7 sections, ~2-4 pages) + evidence appendix + JSON; numbers checked by a publication gate
```

Details: [docs/AGENTS_V4.md](docs/AGENTS_V4.md). The previous section workflow is still available with
`AGENT_DESIGN=sections` ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Quick start

**1. Install**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Get an open-source model** (any OpenAI-compatible server works: Ollama, vLLM, llama.cpp, LM Studio)

The setup script installs Ollama, pulls a model, checks that it answers, and points `.env` at it. Preview first:

```bash
scripts/setup_ollama.sh --dry-run          # prints every step, changes nothing
scripts/setup_ollama.sh                    # installs, pulls qwen2.5:14b-instruct (~9 GB), asks before each download
scripts/setup_ollama.sh --model qwen2.5:7b-instruct   # smaller (~5 GB) for tight disks or RAM
scripts/setup_ollama.sh --fast-model qwen2.5:7b-instruct   # also pull a small model for the extraction steps
```

It verifies the macOS app's code signature before installing, never overwrites an existing install, and is safe
to re-run. Prefer to do it by hand? Install Ollama from https://ollama.com, run `ollama pull qwen2.5:14b-instruct`
and `cp .env.example .env`.

**3. (Optional) Add a search provider.** Web search works out of the box through the keyless `ddgs` library
(installed by `requirements.txt`), but free search can be rate-limited or blocked. For reliable results put one of
these in `.env`; they are tried first. If all web search fails, the pipeline falls back to news headlines, Wikipedia
and Hacker News (competitor recall will be lower). To skip web search entirely, set `DISABLED_TOOLS=web_search`.

```
BRAVE_API_KEY=...        # free tier at https://brave.com/search/api/
SEARXNG_URL=http://localhost:8080   # your own SearXNG with the json format enabled
```

**4. Run**

```bash
python -m startup_cofounder "A subscription service matching small restaurants with local farms"
# -> outputs/<idea>.md (report) and outputs/<idea>.json (all section output, evidence ids, sources)

streamlit run app.py                      # web UI with live progress log, charts and download
```

**No model handy?** `python -m startup_cofounder --mock --offline "Any idea here"` runs the whole
pipeline with a placeholder LLM so you can see the report structure. Its content is scaffolding,
not research, and the report says so.

## What's in the report

| Memo section | Built from |
|---|---|
| The founder's idea (verbatim) and how it was read; interpretation flags | research-planning agent + fidelity check |
| 1. Recommendation (proceed / validate first / modify / abandon), 3-5 key findings with implications, proceed-if / modify-if / stop-if | deterministic synthesis |
| 2. Customer problem and evidence (problem, frequency, workarounds, willingness to pay; evidence level per hypothesis) | question analysts, validated |
| 3. Competitive landscape and differentiation | competitor identity agent + complaints about alternatives |
| 4. Market opportunity and distribution (local count or bottom-up method; channels; cold start) | question analysts + synthesis |
| 5. Product feasibility and business economics (MVP cost, monthly costs, break-even volume, funding to next milestone, by scenario) | `economics2.py` |
| 6. Most consequential risks, each linked to the experiment that reduces it | synthesis |
| 7. 2-3 validation experiments (hypothesis, segment, method, metric, threshold, cost, duration, meaning, next step) | synthesis |
| Appendix: idea brief, assumptions map, every question with queries, packet, findings and validation notes, economics assumptions with basis and sensitivity, cross-section checks, report checks, research-run evidence log | code |

Regenerate an older saved run in this format (no new searches, no model calls):
`python -m startup_cofounder.regenerate outputs/<file>.json` (add `--with-model` to let your local model read the
saved evidence, or `--v3` for the previous format).

## Command line options

```
python -m startup_cofounder "idea" [options]
  --mock            use the placeholder LLM (no model server needed)
  --offline         disable all network tools (every finding becomes an estimate)
  --fresh           ignore checkpoints from an interrupted run of the same idea
  --fast-model NAME smaller model for extraction steps (default: same as --model)
  --quick           faster, thinner run: no extra specialists and no critic review
  --rounds N        critic review rounds (default 1; 0 disables)
  --model NAME      override LLM_MODEL
  --base-url URL    override LLM_BASE_URL
  --out PATH        write the report here instead of outputs/<idea>.md
```

All settings and environment variables: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Testing and evaluation

```bash
pytest -q                                   # 161 tests, no network or model needed
python eval/report_rubric.py                # old vs new report comparison (mechanical, transparent)
python eval/demo_cases.py                   # Airbnb/Duolingo/Zoom/Uber-style ideas, live
python eval/demo_cases.py --only uber       # one case
```

The eval checks that the pipeline rediscovers competitors we know exist, how much of its output is sourced,
and whether any section fails. How to read it: [docs/EVALUATION.md](docs/EVALUATION.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline stages, retrieval, evidence packs, checkpoints, failure handling |
| [docs/AGENTS.md](docs/AGENTS.md) | Every role: purpose and output schema |
| [docs/QUALITY_AND_EVIDENCE.md](docs/QUALITY_AND_EVIDENCE.md) | Evidence ledger, grounding checks, critic loop, evidence grade, verdict guardrail |
| [docs/FINANCIAL_MODEL.md](docs/FINANCIAL_MODEL.md) | Every formula, scenario multiplier and sanity check |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Env vars, model choice, search providers, troubleshooting |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Validation harness, metrics, how to add test cases |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Project layout, adding sections and tools, testing conventions |
| [docs/COURSE_ALIGNMENT.md](docs/COURSE_ALIGNMENT.md) | Mapping to the course proposal, deliverables and milestones |

## Known limitations

- **Model size still matters.** Schema-constrained output removes most malformed JSON, but 7B models write thin
  summaries; 14B+ is recommended. Local generation is slow (minutes per section on a laptop).
- **Free web sources are shallow.** News, Wikipedia and Hacker News are good for trends and pain points but
  rarely contain paid market-size reports. Expect TAM/SAM to be mostly labelled estimates.
- **Grounding is lexical, not semantic.** The checks catch missing citations, numbers absent from the source
  and unrelated claims; they cannot prove a claim is *true* or detect a subtle misreading of a source.
- **Financial numbers are assumptions**, shown with scenarios and sensitivity so you can see which ones matter.
- Search results and pages are cached for 24h in `.cache/` (delete the folder to refresh).

## License / academic note

Course project for *AI Agents for Engineers*, Carnegie Mellon University. Uses only open-source models and
free or free-tier data sources.
