# Architecture

This document explains how a request flows through the system and why it is built this way.
Code references are to files under `startup_cofounder/`.

## Design principles

1. **LLMs propose, code verifies and computes.** Language models are good at reading messy text and
   making judgment calls, and bad at arithmetic and honesty about what they don't know. So models
   gather and summarize evidence and suggest assumptions; deterministic code checks citations, validates
   competitor names, runs the financial model and caps the verdict.
2. **Every claim is traceable.** Evidence gets an id the moment it is retrieved; claims carry ids to the end.
3. **Degrade, don't crash.** Any single failure (tool error, bad JSON, crashed agent) lowers report quality
   and adds a warning; it never aborts the run.
4. **Works with small open models.** Tool calling uses a plain-JSON protocol (no native function-calling
   support needed) with lenient parsing.

## Pipeline (`pipeline.py`)

| # | Stage | Runs | What happens |
|---|---|---|---|
| 1 | Coordinator | 1 agent, no tools | Rewrites the idea as one precise sentence, picks search keywords, writes research questions for each specialist, and may request 0-2 **extra specialists** for idea-specific topics (regulation, supply chain, ...). |
| 2 | Researchers | 4 core + extras, **in parallel** (thread pool, `MAX_WORKERS`) | Customer, Competitor, Market, Technical (+ extras). Each runs the tool loop and returns structured JSON plus cited findings. |
| 3 | Review loop | rule checks + Critic agent, then redo | See below. Repeats for `CRITIC_ROUNDS`. |
| 4 | Competitor verification | code | Each competitor name is searched for in all retrieved evidence; confirmed ones rank first and are marked in the report. |
| 5 | Financial | 1 agent, then code | The agent reads the research and proposes assumptions (price, churn, CAC, team, startup costs). `finance.py` sanitizes them and computes the projection, unit economics, 3 scenarios and a sensitivity table; `sanity_flags` list implausible results. |
| 6 | Synthesizer | 1 agent, no tools | Reads all research plus the **computed** numbers, flags and evidence grade, and writes the verdict, scope, risks, validation steps and outlook. |
| 7 | Guardrail | code | `quality.cap_verdict` downgrades "go" to "validate_first" unless evidence grade is A/B, LTV/CAC >= 3 and break-even happens within 5 years. |
| 8 | Report | code | `report.py` renders markdown; `Assessment.to_dict()` gives the full JSON. |

### The review loop (stage 3)

```
for round in 1..CRITIC_ROUNDS:
    rule_gaps   = quality.rule_gaps(results)          # deterministic: counts, missing fields, unconfirmed names
    critic_gaps = Critic agent(research + rule_gaps)  # judgment: unsupported claims, implausible numbers
    gaps        = merge(rule_gaps, critic_gaps)[:3]   # one per agent, rules first, capped for cost
    if no gaps: stop
    for each gap (in parallel): re-run that agent with
        - its previous answer
        - the specific feedback
        - a request to return the COMPLETE improved output
    keep the new output only if it is valid, otherwise keep the old one
```

Rules come first because they are cheap and reliable; the LLM critic only adds what rules cannot see.
Re-runs add to the shared evidence ledger, so new sources are available to later stages.

## Data model

- `Source` (`evidence.py`): `id`, `title`, `url`, `snippet`, `tool`.
- `EvidenceLedger`: thread-safe, de-duplicates by URL, shared by every agent in a run.
- `Finding`: `claim`, `kind` (fact/estimate), `source_ids`, `downgraded`, `note`.
- `AgentResult`: `role`, `output` (dict), `findings`, `trace` (every tool call), `error`.
- `Assessment` (`pipeline.py`): everything the report needs, including `review_log`, `scenarios`,
  `sensitivity`, `unit_economics`, `flags`, `grade`, `verdict`, `verdict_note`.

## Tool layer (`tools/`)

Tools return `ToolResult(sources=[{title,url,snippet}], text, error)`. `Tool.run` catches every
exception and returns it as an error result, so an agent sees "tool error: ..." and can try something else.

| Tool | Backend | Best for |
|---|---|---|
| `web_search` | Brave API, then SearXNG, then DuckDuckGo HTML | competitors, pricing, product pages |
| `news_search` | Google News RSS | market trends, funding, launches |
| `wikipedia` | MediaWiki API | industry and company background |
| `hn_search` | Hacker News (Algolia) | customer pain points, technical feasibility |
| `fetch_page` | `requests` + BeautifulSoup | reading a specific page (pricing page, report) |

All network access goes through `Http.get`, which adds a 24-hour disk cache (`.cache/`) so repeated runs
and evals are fast and reproducible, and which raises `OfflineError` in `--offline` mode.

## LLM layer (`llm.py`)

- `OpenAICompatLLM`: `POST {LLM_BASE_URL}/chat/completions`. Retries on server/network errors, and retries
  without `response_format` if a server rejects JSON mode.
- `MockLLM`: deterministic stand-in that follows the same protocol for every role. Used by the tests and
  by `--mock`. It cites real retrieved evidence when available but its prose is placeholder text.

## Concurrency

Agents are I/O-bound (model server + web), so a `ThreadPoolExecutor` runs them in parallel. The ledger uses
a lock. With a single local GPU the model server serializes generation anyway, so parallelism mostly helps
overlap web calls; set `MAX_WORKERS=1` if your model server struggles with concurrent requests.

## Failure handling summary

| Failure | Behavior |
|---|---|
| Tool raises / network down / blocked | Returned to the agent as an error observation; agent tries another tool or finishes with estimates |
| Model emits invalid JSON | Up to 2 repair nudges, then the agent returns an error result |
| Model skips the `{"final": ...}` wrapper | Accepted if the object has real content |
| Agent crashes or returns nothing | Stage continues; the critic/rules flag it and it is retried once; a warning is added if still failing |
| Coordinator fails | Default research plan is used |
| Financial agent gives no/garbage assumptions | Generic SaaS defaults after clamping; warning added |
| Synthesizer gives no/invalid verdict | `validate_first` |
