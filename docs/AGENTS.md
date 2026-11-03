# Agents

Each role below is a single schema-constrained model call over an evidence pack that code has already retrieved
(`pipeline.py`, `extract.py`). Roles are defined as an `AgentSpec` in `agents/specs.py`: a role name, a mission and the
literal JSON shape shown to the model. The matching JSON Schemas used for constrained decoding live in `schemas.py`.

## Common rules every role receives

- Cite evidence ids in `source_ids`; mark a finding `fact` only if a cited source supports it.
- Numbers in facts must appear verbatim in a cited source (this is machine-checked).
- Never invent URLs, companies, statistics or quotes.
- Missing information must be labelled `estimate`, not omitted.

## Role reference

### Coordinator
- **Evidence:** none. **Runs:** once, first.
- **Produces:** `idea_summary`, `category`, `problem`, `industry`, `search_keywords`, `tasks` (research questions per
  section), `extra_specialists` (0-2 `{role, focus, questions}`).
- **Notes:** extra specialist roles are slugified, must be 3+ letters, cannot reuse a core role name, and are
  capped by `MAX_EXTRA_SPECIALISTS`.

### Customer
- **Produces:** `summary`, `segments[{name, description, pain_points, willingness_to_pay, size_estimate}]`, `findings`.

### Competitor
- **Produces:** `summary`, `competitors[{name, url, description, pricing, strengths, weaknesses, source_ids}]`,
  `white_space`, `findings`.
- **How:** candidates are extracted and ranked by how many distinct sources mention them (a name repeated inside one
  niche article does not outrank a widely mentioned one). Each top name is searched and profiled separately; a
  profile the model marks `is_competitor: false` is dropped (`competitors.py`).
- **Post-processing:** `quality.verify_competitors` adds `verified` to each and ranks confirmed ones first;
  the report shows the top three.

### Market
- **Produces:** `summary`, `tam_sam_som{tam_usd, sam_usd, som_usd, method}`, `trends`, `headwinds`, `findings`.

### Technical
- **Produces:** `summary`, `feasibility_score` (1-5), `key_components`, `build_vs_buy`, `main_risks`,
  `mvp_time_months`, `mvp_team_size`, `findings`.

### Extra specialists (dynamic)
- **Produces:** `summary`, `key_points`, `implications_for_founder`, `findings`.
- Created per run from the coordinator's request, e.g. `food_safety`, `supply_chain`.

### Critic
- **Input:** every section's output plus the automatic problems already found.
- **Produces:** `approved`, `gaps[{agent, issue, followup_task}]`. Only gaps naming a real section are used.

### Financial
- **Input:** all research outputs and pricing benchmarks.
- **Produces:** `rationale`, `assumptions{arpu_monthly, year1_new_customers, growth_rate, annual_churn,
  cogs_pct, cac, other_opex_annual, team[], startup_costs[]}`, `findings`.
- **It does not compute anything.** `finance.py` does; see [FINANCIAL_MODEL.md](FINANCIAL_MODEL.md).

### Synthesizer
- **Input:** all research, the computed projection, unit economics, sanity flags and the evidence grade.
- **Produces:** `verdict`, `verdict_rationale`, `executive_summary`, `scope`, `risks`, `validation_steps`
  (ordered by which wrong assumption would kill the business fastest), `future_outlook`.
- The verdict is then passed through the guardrail.

## Writing good prompts for these roles (lessons built in)

- Schemas are shown as literal JSON so small models copy the structure.
- The model is told today's date so it prefers recent sources.
- Arithmetic is never requested from the model.
- Missing information must be labelled `estimate` rather than omitted, so downstream code sees the gap.
