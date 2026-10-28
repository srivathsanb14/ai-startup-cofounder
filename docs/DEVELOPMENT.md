# Development guide

## Layout

```
app.py                          Streamlit UI (live agent log, metrics, scenario chart, download)
startup_cofounder/
  __main__.py, cli.py           command line entry point
  config.py                     Config dataclass, env + .env loading
  llm.py                        OpenAICompatLLM, MockLLM
  jsonutil.py                   extract_json: tolerant JSON extraction from model replies
  evidence.py                   EvidenceLedger, Finding, grounding checks
  quality.py                    rule gaps, competitor verification, evidence grade, verdict guardrail
  finance.py                    projection, unit economics, scenarios, sensitivity, sanity flags
  pipeline.py                   orchestration and the Assessment dataclass
  report.py                     markdown renderer
  agents/
    base.py                     Agent loop, AgentSpec, AgentResult, protocol prompt
    specs.py                    all agent prompts and schemas
  tools/
    base.py                     Tool, ToolResult, Http (cache, offline, headers)
    search.py                   web/news/wikipedia/HN/fetch implementations and registry
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
2. Register it in `ALL_TOOLS` with a one-line description (the model reads it) and an `args` dict.
3. Add the tool name to the relevant `AgentSpec.tools` in `agents/specs.py`.
4. Test it by monkeypatching `Http.get` (see `test_web_search_provider_order`).

Tools must never raise to the agent; `Tool.run` already converts exceptions to error results.

## Adding a core agent

1. Define an `AgentSpec` in `agents/specs.py` with `role`, `mission`, `tools` and a literal JSON `schema`.
   Include `FINDINGS_SCHEMA` so claims are citable.
2. Add it to `RESEARCHERS` (parallel stage) and add a default research question in `DEFAULT_TASKS` (`pipeline.py`).
3. Render it in `report.py`.
4. Optionally add a rule in `quality.rule_gaps` so the critic loop can catch an incomplete output.
5. Teach `MockLLM._final` a placeholder output for the new role so tests keep passing.

Idea-specific agents need no code: the coordinator creates them at run time (`make_extra_specialist`).

## Using a different LLM provider

Implement `chat(messages, temperature=None, json_mode=False) -> str` and pass it to `Pipeline(config, llm=...)`,
or add a branch in `llm.build_llm`. Messages are OpenAI-style `{"role", "content"}` dicts.

## Testing conventions

- Unit-test deterministic logic directly (`finance`, `evidence`, `quality`).
- Test the pipeline with `MockLLM` subclasses that override `chat` for specific roles (see `CriticLLM`,
  `OptimisticLLM` in `tests/test_pipeline.py`) to force the behavior under test.
- Stub tools by replacing entries in `ALL_TOOLS` with `monkeypatch.setitem`.
- Never hit the network or a real model in `pytest`; real-model quality is the job of `eval/demo_cases.py`.

## Debugging a bad report

1. Open `outputs/<idea>.json`. `agents.<role>.trace` shows every tool call, its arguments, the evidence ids returned
   and any error note.
2. `agents.<role>.output` is the raw structured output; `findings[].note` explains each downgrade.
3. `review_log` shows what the critic loop flagged and whether the redo helped.
4. `warnings` lists failed agents and defaults that were used.
5. Common fixes: larger model, search provider key, higher `MAX_TOOL_CALLS`, `CRITIC_ROUNDS=2`.

## Style

Small, typed-where-useful functions; deterministic logic separated from LLM calls; comments explain *why*
(failure modes, guardrails), not what.
