# Development guide

## Layout

```
app.py                          Streamlit UI (live progress log, metrics, scenario chart, download)
startup_cofounder/
  __main__.py, cli.py           command line entry point
  config.py                     Config dataclass, env + .env loading
  llm.py                        OpenAICompatLLM, MockLLM
  jsonutil.py                   extract_json: tolerant JSON extraction from model replies
  evidence.py                   EvidenceLedger, Finding, grounding checks
  quality.py                    rule gaps, competitor verification, evidence grade, verdict guardrail
  finance.py                    projection, unit economics, scenarios, sensitivity, sanity flags
  pipeline.py                   Pipeline (retrieve-then-extract), Assessment dataclass, economics()
  retrieval.py                  query templates, parallel search, page fetch, evidence packs
  passages.py                   chunking and BM25 ranking, PassageIndex
  competitors.py                candidate ranking and profile helpers
  extract.py                    Extractor: schema-constrained JSON calls with repair
  schemas.py                    JSON Schemas for constrained decoding
  checkpoint.py                 stage checkpoints for resume
  report.py                     markdown renderer
  agents/
    base.py                     AgentSpec, AgentResult
    specs.py                    all role prompts and output shapes
  tools/
    base.py                     Tool, ToolResult, Http (cache, offline, headers)
    search.py                   web/news/wikipedia/HN search, page_text, and the registry
tests/                          pytest suite (no network or model needed)
eval/demo_cases.py              validation harness
docs/                           documentation
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m startup_cofounder --mock --offline "test idea for development"
```

Python 3.9+ is supported; modules use `from __future__ import annotations`.

## Adding a tool

1. Write a function in `tools/search.py` (or a new module) returning `ToolResult(sources=[{title, url, snippet}])`.
   Use `Http.get(...)` for network access so caching and `--offline` work.
2. Register it in `ALL_TOOLS` with a one-line description and an `args` dict.
3. Add queries that use it to `SECTION_QUERIES` in `retrieval.py`.
4. Test it by monkeypatching `Http.get` (see `test_web_search_provider_order`).

Tools must never raise to the caller; `Tool.run` already converts exceptions to error results.

## Adding a section

1. Add an `AgentSpec` in `agents/specs.py` (its `mission` and `schema` text are reused as the extraction prompt) and a JSON
   Schema in `schemas.py` registered in `BY_ROLE`.
2. Add query templates to `SECTION_QUERIES` (and optionally `FOLLOWUP_QUERIES`) in `retrieval.py`.
3. Add the role to `CORE_SECTIONS` and `specs.RESEARCHERS`, a default task in `DEFAULT_TASKS`, and render it in `report.py`.
4. Optionally add a rule in `quality.rule_gaps`, and a placeholder in `MockLLM._final`.

Extra specialists need no code: the coordinator creates them per idea (`make_extra_specialist`).

## Using a different LLM provider

Implement `chat(messages, temperature=None, json_mode=False, schema=None) -> str` and pass it to `Pipeline(config, llm=...)`,
or add a branch in `llm.build_llm`. Messages are OpenAI-style `{"role", "content"}` dicts.

## Testing conventions

- Unit-test deterministic logic directly (`finance`, `evidence`, `quality`).
- Test the pipeline with `MockLLM` subclasses that override `chat` for specific roles (see `CriticLLM`,
  `OptimisticLLM` in `tests/test_pipeline.py`) to force the behavior under test.
- Stub tools by replacing entries in `ALL_TOOLS` with `monkeypatch.setitem`.
- Never hit the network or a real model in `pytest`; real-model quality is the job of `eval/demo_cases.py`.

## Debugging a bad report

1. Open `outputs/<idea>.json`. `agents.<role>.trace` lists the evidence ids each result was drawn from.
2. `agents.<role>.output` is the raw structured output; `findings[].note` explains each downgrade.
3. `review_log` shows what the critic loop flagged and whether the redo helped.
4. `warnings` lists failed sections and defaults that were used.
5. Common fixes: larger model, search provider key, `CRITIC_ROUNDS=2`.

## Style

Small, typed-where-useful functions; deterministic logic separated from LLM calls; comments explain *why*
(failure modes, guardrails), not what.
