# Architecture

How a request flows through the system and why it is built this way. Code references are to files under
`startup_cofounder/`.

The project has two engines that share the same evidence ledger, quality checks, financial model and report:

| Engine | Module | Idea | Use it when |
|---|---|---|---|
| **v2** (default) | `pipeline_v2.py` | **Retrieve first, then extract.** Code gathers evidence; the model only reads it and answers in a fixed schema. | normally; it is faster and finds more evidence |
| **agentic** | `pipeline.py` + `agents/` | Each agent runs its own tool-calling loop and chooses its own searches. | strong models that plan searches well, or for comparison |

Select with `ENGINE=v2|agentic`, `--engine`, or the UI sidebar.

## Design principles

1. **LLMs read and judge; code retrieves, verifies and computes.** Models are good at reading messy text and bad at
   arithmetic and at knowing when they don't know. So code plans and runs searches, ranks passages, checks
   citations, validates competitor names, runs the financial model and caps the verdict.
2. **Every claim is traceable.** Evidence gets an id when retrieved and keeps it through to the report.
3. **Degrade, don't crash.** Any single failure lowers report quality and adds a warning; it never aborts the run.
4. **Don't redo finished work.** Every v2 stage is checkpointed.
5. **Works with small open models.** Schema-constrained output removes most format failures.

## Why v2 exists (what the first live evaluation showed)

With the agentic engine and a 14B local model, one evaluation case took 34 minutes, found 1 of 5 known competitors,
and only 17% of findings were sourced facts; the synthesizer timed out. The causes were architectural:
the model chose its own queries (poorly), each agent saw only its own search results, evidence was a 400-character
snippet, malformed JSON caused redos, and one timeout lost the whole run. v2 addresses each directly.

| Problem | v2 change |
|---|---|
| Model picks weak queries | Query **templates** per section run in parallel, no LLM involved (`retrieval.py`) |
| Agents can't see each other's evidence | One shared evidence ledger; sections draw their packs from it |
| Snippets too short to support claims | Top pages fetched **in full**, split into passages, ranked by BM25 against the question (`passages.py`) |
| Competitor list depends on model memory | **Staged discovery**: extract names, rank by mentions in all evidence, drop unseen names, profile each top name with its own searches (`competitors.py`) |
| Invalid JSON, "no usable output" redos | **Schema-constrained decoding** (`schemas.py`, `llm.py`) with automatic fallback |
| Everything runs on the biggest model | Optional **fast model** for extraction; main model for judgment (`LLM_FAST_MODEL`) |
| A timeout loses the run | **Stage checkpoints**; rerun resumes (`checkpoint.py`) |

## v2 pipeline (`pipeline_v2.py`)

| # | Stage | LLM? | What happens |
|---|---|---|---|
| 1 | Plan | fast | Coordinator returns the sharpened idea, a short search **category** and **problem** phrase, per-section tasks and 0-2 extra specialists. |
| 2 | Retrieval | no | `retrieval.build_queries` fills templates for customer, competitor, market, technical, financial (and extras); `run_queries` executes them in parallel. A disabled or blocked `web_search` falls back to news headlines. |
| 3 | Page fetch | no | The top pages per section are downloaded in full (cached) and split into ~650-character passages. |
| 4 | Extraction | fast | Customer, market, technical and extras run in parallel. Each receives an **evidence pack**: the most relevant snippets and passages for its question, with ids. Output is schema-constrained JSON with cited findings. |
| 4b | Competitors | fast | Names extracted from the competitor evidence, ranked by mentions across *all* evidence (unseen names dropped), top names searched and profiled in parallel, then summarized by the main model. |
| 5 | Review | main | `quality.rule_gaps` plus a critic LLM. A flagged section gets **follow-up queries**, more pages, and re-extraction with its previous answer and the feedback. Repeats for `CRITIC_ROUNDS`. |
| 6 | Verify | no | Competitor names checked against evidence; confirmed ones rank first. |
| 7 | Financial | main | Reads the research plus pricing benchmarks and proposes assumptions. |
| 8 | Economics | no | `finance.py`: projection, unit economics, scenarios, sensitivity, sanity flags; `quality.evidence_grade`. |
| 9 | Synthesis | main | Decision memo from research summaries and the computed numbers. |
| 10 | Guardrail | no | `quality.cap_verdict` downgrades an unsupported "go". |

Stages 1, 2, 4/4b, 5, 7 and 9 are saved to `.cache/runs/<key>.json` together with the evidence ledger. Restoring
the ledger in order reproduces the same ids, so a resumed run is indistinguishable from an uninterrupted one.
The key hashes the idea, backend, models, offline flag and disabled tools; `--fresh` ignores it.

### Evidence packs

For a section, `evidence_pack(question, ids, ...)` ranks that section's search snippets and the passages of its
fetched pages against the question with BM25 and keeps the best ~10 snippets and ~8 passages. Chosen passages are
registered in the ledger as sources (`<page-url>#p<n>`, tool `passage`), so the model cites them like any source
and the grounding check compares claims against the exact passage text rather than a short snippet.

## The agentic engine (`pipeline.py`, `agents/`)

Coordinator, then parallel tool-using agents (customer, competitor, market, technical, plus dynamic specialists),
a critic loop, a financial agent and a synthesizer. Each agent replies with one JSON object per turn, either a
tool call or `{"final": ...}`. Details in [AGENTS.md](AGENTS.md). It shares `economics()`, `quality.py`,
`finance.py` and `report.py` with v2.

## Shared layers

### Data model
- `Source` (`evidence.py`): `id`, `title`, `url`, `snippet`, `tool`. `EvidenceLedger`: thread-safe, de-duplicates by URL.
- `Finding`: `claim`, `kind` (fact/estimate), `source_ids`, `downgraded`, `note`.
- `AgentResult`: `role`, `output`, `findings`, `trace`, `error`. v2 builds these from checkpointed raw outputs so the
  quality rules and the report work unchanged.
- `Assessment`: everything the report needs, including `review_log`, `scenarios`, `sensitivity`, `grade`, `verdict`.

### Tool layer (`tools/`)
Tools return `ToolResult(sources, text, error)` and never raise to callers (`Tool.run` converts exceptions). All network
access goes through `Http.get` with a 24-hour disk cache and an offline switch.

| Tool | Backend | Best for |
|---|---|---|
| `web_search` | Brave API, then SearXNG, then DuckDuckGo HTML | competitors, pricing |
| `news_search` | Google News RSS | trends, funding, launches |
| `wikipedia` | MediaWiki API | background |
| `hn_search` | Hacker News (Algolia) | pain points, feasibility |
| `fetch_page` / `page_text` | requests + BeautifulSoup | reading a specific page in full |

`DISABLED_TOOLS` hides tools; v2 retrieval substitutes news headlines for a disabled or failing `web_search`.

### LLM layer (`llm.py`)
`OpenAICompatLLM.chat(messages, json_mode, schema)` calls `/chat/completions`. With a `schema` it sends
`response_format: json_schema`; if the server answers HTTP 400 it degrades to `json_object`, then to unconstrained
output, without using up retries. `build_llm(config, fast=True)` returns the cheaper model when `LLM_FAST_MODEL` is
set. `MockLLM` follows both protocols and powers the tests and `--mock`.

### Concurrency
Retrieval and page fetching are I/O-bound and run in thread pools. Extraction calls run in parallel too, though a
single local GPU serializes generation, so the large wins come from needing far fewer, shorter model calls.

## Failure handling

| Failure | Behavior |
|---|---|
| Search provider blocked or tool error | Observation/empty result; v2 falls back to news headlines |
| Page fetch fails | Skipped; the rest of the pack is used |
| Model emits invalid JSON | Constrained decoding prevents most; the extractor repairs up to twice; then the section errors |
| A section errors or is thin | Rule check flags it; the review loop retries with follow-up retrieval |
| Model server timeout or crash mid-run | Rerun the same command; finished stages are restored from the checkpoint |
| Coordinator fails | Default plan using the raw idea as the category |
| Financial agent gives nothing usable | Generic SaaS defaults after clamping; warning added |
| Synthesizer fails or gives an invalid verdict | `validate_first` plus a note |
