# AI Startup Co-Founder

**An evidence-backed startup assessment from a rough business idea, produced by a team of cooperating LLM agents.**

*Agents of Chaos: AI Agents for Engineers, Fall 2026 (project idea #39).
Team: Owen Liston, Jacob Barry, Srivathsan Badrinarayanan, Jimmy Wang.*

You type: *"A subscription service that matches small restaurants with local farms"*.
You get a report with customers, the top-3 competitors, market size, technical feasibility,
organizational structure, a 5-year financial model with scenarios, risks, and a ranked list of
experiments to run next. Every claim is labelled **fact** (with a citation you can click) or
**estimate**, and the report grades how well-supported the whole thing is.

> This is preliminary desk research. It tells you which assumptions to test first; it does not replace
> talking to customers.

---

## Why this is different from asking a chatbot

| Problem with a plain chat answer | What this project does about it |
|---|---|
| Confident claims with no sources | Every search result gets an id (`E1`, `E2`...). Agents must cite ids, and claims are **machine-checked against the cited text**. |
| Invented numbers | A "fact" is downgraded to "estimate" if its numbers don't appear in the cited source. |
| Invented competitors | Competitor names are checked against everything retrieved; unconfirmed ones are flagged and ranked last. |
| Made-up financial math | The LLM only proposes assumptions. Code computes the model, so it is consistent and reproducible. |
| One-shot answer, no self-review | A **critic** (automatic rules + an LLM reviewer) sends weak sections back for another research pass. |
| Over-optimistic "go!" verdicts | A **guardrail** refuses "go" unless evidence is strong, LTV/CAC >= 3 and the business breaks even. |
| One fixed template for every idea | The coordinator can **spawn extra specialists** (e.g. regulation, supply chain) when an idea needs them. |

## How it works

```
                          rough idea
                              │
                        ┌─────▼─────┐
                        │Coordinator│  sharpens the idea, plans tasks,
                        └─────┬─────┘  may add 0-2 idea-specific specialists
        ┌───────────┬─────────┼──────────┬────────────┬ ─ ─ ─ ─ ─ ┐
   ┌────▼───┐ ┌─────▼────┐ ┌──▼───┐ ┌────▼─────┐ ┌ ─ ─▼─ ─ ─ ┐      parallel, each runs a
   │Customer│ │Competitor│ │Market│ │Technical │   Extra            tool-using loop
   └────┬───┘ └─────┬────┘ └──┬───┘ └────┬─────┘ └ ─ ─ ┬ ─ ─ ─ ┘
        └───────────┴─────────┼──────────┴────────────┴ ─ ─ ─ ─ ─ ┘
                       ┌──────▼──────┐
                       │   Critic    │  rule checks + LLM reviewer; redo weak agents
                       └──────┬──────┘
                       ┌──────▼──────┐   verify competitor names against evidence
                       │  Financial  │──► assumptions ─► finance.py (pandas):
                       └──────┬──────┘   projection, unit economics, scenarios, sensitivity
                       ┌──────▼──────┐
                       │ Synthesizer │──► verdict ─► guardrail ─► report.md + report.json
                       └─────────────┘
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
```

It verifies the macOS app's code signature before installing, never overwrites an existing install, and is safe
to re-run. Prefer to do it by hand? Install Ollama from https://ollama.com, run `ollama pull qwen2.5:14b-instruct`
and `cp .env.example .env`.

**3. (Recommended) Add a search provider.** Free DuckDuckGo scraping is unreliable and may be blocked.
Put one of these in `.env`. With none, run `scripts/setup_ollama.sh --disable-web-search` (or set
`DISABLED_TOOLS=web_search`) so agents don't waste calls on a blocked search and use news, Wikipedia,
Hacker News and page fetch instead (competitor recall will be lower).

```
BRAVE_API_KEY=...        # free tier at https://brave.com/search/api/
SEARXNG_URL=http://localhost:8080   # your own SearXNG with the json format enabled
```

**4. Run**

```bash
python -m startup_cofounder "A subscription service matching small restaurants with local farms"
# -> outputs/<idea>.md (report) and outputs/<idea>.json (all agent output, traces, sources)

streamlit run app.py                      # web UI with live agent log, charts and download
```

**No model handy?** `python -m startup_cofounder --mock --offline "Any idea here"` runs the whole
pipeline with a placeholder LLM so you can see the report structure. Its content is scaffolding,
not research, and the report says so.

## What's in the report

| Section | Source |
|---|---|
| **At a glance**: verdict, evidence grade A-D, feasibility, LTV/CAC, break-even, peak funding | computed |
| Verdict + rationale (guardrail note if it was downgraded) | LLM, checked by code |
| Executive summary, scope (target customer, MVP, out of scope, success definition) | LLM |
| Potential customers (segments, pain points, willingness to pay) | Customer agent |
| **Top-3 competitors** with pricing, strengths, weaknesses, "seen in sources" check | Competitor agent + code |
| Market: TAM / SAM / SOM with method, trends, headwinds | Market agent |
| Technical feasibility: score, components, build vs buy, MVP time and team | Technical agent |
| Additional research (idea-specific specialists) | Dynamic agents |
| **Organizational structure** and hiring timeline | Financial agent |
| **5-year projection**: revenue, costs, profit, cumulative cash, break-even | `finance.py` |
| Unit economics, **scenarios** (pessimistic/base/optimistic), **sensitivity**, sanity checks | `finance.py` |
| Risks and **ranked validation experiments** | Synthesizer |
| Future outlook (3-5 years) | Synthesizer |
| Quality review log, evidence quality breakdown, all sources | code |

## Command line options

```
python -m startup_cofounder "idea" [options]
  --mock            use the placeholder LLM (no model server needed)
  --offline         disable all network tools (every finding becomes an estimate)
  --rounds N        critic review rounds (default 1; 0 disables)
  --max-tools N     tool calls per agent (default 6)
  --model NAME      override LLM_MODEL
  --base-url URL    override LLM_BASE_URL
  --out PATH        write the report here instead of outputs/<idea>.md
```

All settings and environment variables: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Testing and evaluation

```bash
pytest -q                                   # 23 tests, no network or model needed
python eval/demo_cases.py                   # Airbnb/Duolingo/Zoom/Uber-style ideas, live
python eval/demo_cases.py --only uber       # one case
```

The eval checks that the agent rediscovers competitors we know exist, how much of its output is sourced,
and whether any agent fails. How to read it: [docs/EVALUATION.md](docs/EVALUATION.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline stages, data flow, concurrency, failure handling |
| [docs/AGENTS.md](docs/AGENTS.md) | Every agent: role, tools, output schema; the tool-calling protocol |
| [docs/QUALITY_AND_EVIDENCE.md](docs/QUALITY_AND_EVIDENCE.md) | Evidence ledger, grounding checks, critic loop, evidence grade, verdict guardrail |
| [docs/FINANCIAL_MODEL.md](docs/FINANCIAL_MODEL.md) | Every formula, scenario multiplier and sanity check |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Env vars, model choice, search providers, troubleshooting |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Validation harness, metrics, how to add test cases |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Project layout, adding agents and tools, testing conventions |
| [docs/COURSE_ALIGNMENT.md](docs/COURSE_ALIGNMENT.md) | Mapping to the course proposal, deliverables and milestones |

## Known limitations

- **Small models are the bottleneck.** 7B models often return thin or malformed research; the critic loop
  and JSON repair help, but a 14B+ model produces much better reports.
- **Free web sources are shallow.** News, Wikipedia and Hacker News are good for trends and pain points but
  rarely contain paid market-size reports. Expect TAM/SAM to be mostly labelled estimates.
- **Grounding is lexical, not semantic.** The checks catch missing citations, numbers absent from the source
  and unrelated claims; they cannot prove a claim is *true* or detect a subtle misreading of a source.
- **Financial numbers are assumptions**, shown with scenarios and sensitivity so you can see which ones matter.
- Search results and pages are cached for 24h in `.cache/` (delete the folder to refresh).

## License / academic note

Course project for *AI Agents for Engineers*, Carnegie Mellon University. Uses only open-source models and
free or free-tier data sources.
