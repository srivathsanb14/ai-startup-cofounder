# Agents

All agents share one implementation (`agents/base.py`); they differ only in their `AgentSpec`
(`agents/specs.py`): role, mission, tools and output schema.

## The tool-calling protocol

Each turn the model must reply with exactly **one JSON object**:

```json
{"thought": "why", "tool": "news_search", "args": {"query": "meal kit market size 2026"}}
```
or, to finish:
```json
{"final": { ...output matching the agent's schema... }}
```

The loop (`Agent.run`):

1. Send the system prompt (role, mission, protocol, tool list, today's date, rules, output schema) and the task.
2. Parse the reply with `jsonutil.extract_json` (handles `<think>` blocks, markdown fences, prose around JSON).
3. If it is a tool call: run the tool, register results in the evidence ledger, and feed back a
   `TOOL_OBSERVATION` listing each result as `[E7] title / url / snippet`.
4. If it is a final answer: normalize findings against the ledger (see
   [QUALITY_AND_EVIDENCE.md](QUALITY_AND_EVIDENCE.md)) and return.
5. Guardrails: a per-agent tool budget (`MAX_TOOL_CALLS`), unknown tools and over-budget calls get a nudge to
   finish, invalid JSON gets up to two repair nudges.

The same loop is used for agents with no tools (coordinator, critic, synthesizer); they simply finish immediately.

## Common rules every agent receives

- Cite evidence ids in `source_ids`; mark a finding `fact` only if a cited source supports it.
- Numbers in facts must appear verbatim in a cited source (this is machine-checked).
- Never invent URLs, companies, statistics or quotes.
- Use specific, varied queries; never repeat a query; `fetch_page` a key result instead of guessing.
- Look for two sources for important numbers.

## Agent reference

### Coordinator
- **Tools:** none. **Runs:** once, first.
- **Produces:** `idea_summary`, `industry`, `search_keywords`, `tasks` (research questions per agent),
  `extra_specialists` (0-2 `{role, focus, questions}`).
- **Notes:** extra specialist roles are slugified, must be 3+ letters, cannot reuse a core role name, and are
  capped by `MAX_EXTRA_SPECIALISTS`.

### Customer
- **Tools:** `web_search`, `hn_search`, `news_search`, `fetch_page`.
- **Produces:** `summary`, `segments[{name, description, pain_points, willingness_to_pay, size_estimate}]`, `findings`.

### Competitor
- **Tools:** `web_search`, `news_search`, `wikipedia`, `fetch_page`.
- **Produces:** `summary`, `competitors[{name, url, description, pricing, strengths, weaknesses, source_ids}]`,
  `white_space`, `findings`.
- **Post-processing:** `quality.verify_competitors` adds `verified` to each and ranks confirmed ones first;
  the report shows the top three.

### Market
- **Tools:** `news_search`, `web_search`, `wikipedia`, `fetch_page`.
- **Produces:** `summary`, `tam_sam_som{tam_usd, sam_usd, som_usd, method}`, `trends`, `headwinds`, `findings`.

### Technical
- **Tools:** `web_search`, `hn_search`, `wikipedia`, `fetch_page`.
- **Produces:** `summary`, `feasibility_score` (1-5), `key_components`, `build_vs_buy`, `main_risks`,
  `mvp_time_months`, `mvp_team_size`, `findings`.

### Extra specialists (dynamic)
- **Tools:** `web_search`, `news_search`, `wikipedia`, `fetch_page`.
- **Produces:** `summary`, `key_points`, `implications_for_founder`, `findings`.
- Created per run from the coordinator's request, e.g. `food_safety`, `supply_chain`.

### Critic
- **Tools:** none. **Input:** every researcher's output plus the automatic problems already found.
- **Produces:** `approved`, `gaps[{agent, issue, followup_task}]`. Only gaps naming a real agent are used.

### Financial
- **Tools:** `web_search`, `fetch_page` (2 calls max, for pricing benchmarks).
- **Input:** all research outputs.
- **Produces:** `rationale`, `assumptions{arpu_monthly, year1_new_customers, growth_rate, annual_churn,
  cogs_pct, cac, other_opex_annual, team[], startup_costs[]}`, `findings`.
- **It does not compute anything.** `finance.py` does; see [FINANCIAL_MODEL.md](FINANCIAL_MODEL.md).

### Synthesizer
- **Tools:** none. **Input:** all research, the computed projection, unit economics, sanity flags and the evidence grade.
- **Produces:** `verdict`, `verdict_rationale`, `executive_summary`, `scope`, `risks`, `validation_steps`
  (ordered by which wrong assumption would kill the business fastest), `future_outlook`.
- The verdict is then passed through the guardrail.

## Writing good prompts for these agents (lessons built in)

- Schemas are shown as literal JSON so small models copy the structure.
- The model is told today's date so it prefers recent sources.
- Arithmetic is never requested from the model.
- Missing information must be labelled `estimate` rather than omitted, so downstream code sees the gap.
