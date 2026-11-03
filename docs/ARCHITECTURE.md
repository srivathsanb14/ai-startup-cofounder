# Architecture

How a request flows through the system and why it is built this way. Code references are to files under
`startup_cofounder/`.

The pipeline is **retrieve first, then extract**: code gathers evidence, and the model only reads it and answers in a
fixed JSON schema.

## Design principles

1. **LLMs read and judge; code retrieves, verifies and computes.** Models are good at reading messy text and bad at
   arithmetic and at knowing when they don't know. So code plans and runs searches, ranks passages, checks
   citations, validates competitor names, runs the financial model and caps the verdict.
2. **Every claim is traceable.** Evidence gets an id when retrieved and keeps it through to the report.
3. **Degrade, don't crash.** Any single failure lowers report quality and adds a warning; it never aborts the run.
4. **Don't redo finished work.** Every stage is checkpointed.
5. **Works with small open models.** Schema-constrained output removes most format failures.

## Design choices

| Problem | Approach |
|---|---|
| Model-chosen queries are weak | Query **templates** per section run in parallel, no LLM involved (`retrieval.py`) |
| Sections can't see each other's evidence | One shared evidence ledger; sections draw their packs from it |
| Snippets are too short to support claims | Top pages are fetched **in full**, split into passages, ranked by BM25 against the question (`passages.py`) |
| Competitor list depends on model memory | **Staged discovery**: extract names, rank by mentions in all evidence, drop unseen names, profile each top name with its own searches (`competitors.py`) |
| Invalid JSON and "no usable output" redos | **Schema-constrained decoding** (`schemas.py`, `llm.py`) with automatic fallback |
| Everything runs on the biggest model | Optional **fast model** for extraction; main model for judgment (`LLM_FAST_MODEL`) |
| A timeout loses the run | **Stage checkpoints**; rerun resumes (`checkpoint.py`) |

## Pipeline (`pipeline.py`)

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

## Shared layers

### Data model
- `Source` (`evidence.py`): `id`, `title`, `url`, `snippet`, `tool`. `EvidenceLedger`: thread-safe, de-duplicates by URL.
- `Finding`: `claim`, `kind` (fact/estimate), `source_ids`, `downgraded`, `note`.
- `AgentResult`: `role`, `output`, `findings`, `trace`, `error`. Built from checkpointed raw outputs so the quality
  rules and the report work from one shape.
- `Assessment`: everything the report needs, including `review_log`, `scenarios`, `sensitivity`, `grade`, `verdict`.

### Tool layer (`tools/`)
Tools return `ToolResult(sources, text, error)` and never raise to callers (`Tool.run` converts exceptions). All network
access goes through `Http.get` with a 24-hour disk cache and an offline switch.

| Tool | Backend | Best for |
|---|---|---|
| `web_search` | Brave API, then SearXNG, then `ddgs`, then DuckDuckGo HTML | competitors, pricing |
| `news_search` | Google News RSS | trends, funding, launches |
| `wikipedia` | MediaWiki API | background |
| `hn_search` | Hacker News (Algolia) | pain points, feasibility |
| `page_text` | requests + BeautifulSoup | reading a specific page in full (used by page fetch) |

`DISABLED_TOOLS` hides tools; retrieval substitutes news headlines for a disabled or failing `web_search`.

### LLM layer (`llm.py`)
`OpenAICompatLLM.chat(messages, json_mode, schema)` calls `/chat/completions`. With a `schema` it sends
`response_format: json_schema`; if the server answers HTTP 400 it degrades to `json_object`, then to unconstrained
output, without using up retries. `build_llm(config, fast=True)` returns the cheaper model when `LLM_FAST_MODEL` is
set. `MockLLM` powers the tests and `--mock`.

### Concurrency
Retrieval and page fetching are I/O-bound and run in thread pools. Extraction calls run in parallel too, though a
single local GPU serializes generation, so the large wins come from needing few, short model calls.

## Failure handling

| Failure | Behavior |
|---|---|
| Search provider blocked or tool error | Empty result; retrieval falls back to news headlines |
| Page fetch fails | Skipped; the rest of the pack is used |
| Model emits invalid JSON | Constrained decoding prevents most; the extractor repairs up to twice; then the section errors |
| A section errors or is thin | Rule check flags it; the review loop retries with follow-up retrieval |
| Model server timeout or crash mid-run | Rerun the same command; finished stages are restored from the checkpoint |
| Coordinator fails | Default plan using the raw idea as the category |
| Financial planner gives nothing usable | Generic SaaS defaults after clamping; warning added |
| Synthesizer fails or gives an invalid verdict | `validate_first` plus a note |
