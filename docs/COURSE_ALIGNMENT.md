# Alignment with the course proposal

*AI Agents for Engineers, Fall 2026. Team: Agents of Chaos. Project idea #39: AI Startup Co-Founder / Market Research Agent.*

## Promised deliverable

> An agent able to conduct market research including the competitive landscape (top three players in a market),
> develop a business plan that includes basic organizational structure, estimated startup and operating costs,
> and estimated revenues and profits over time.

| Requirement | Where it lives |
|---|---|
| Market research | Market agent: TAM/SAM/SOM with method, trends, headwinds (`agents/specs.py`, report "Market") |
| Competitive landscape, top three players | Competitor agent + `quality.verify_competitors`; report table "Competitive landscape (top 3)" |
| Customer research | Customer agent: segments, pain points, willingness to pay |
| Technical feasibility | Technical agent: score, components, build vs buy, MVP time/team |
| Basic organizational structure | Financial agent's `team[]`, rendered as the "Organizational structure" table with hiring years |
| Estimated startup and operating costs | `startup_costs[]`, payroll, marketing (CAC), COGS, other opex in `finance.project` |
| Revenues and profits over time | 5-year table, 3 scenarios, break-even, cash payback, peak funding |
| Well-defined scope for the idea | Synthesizer's `scope`: target customer, MVP features, out of scope, success definition |
| Recommended validation steps | Synthesizer's ranked `validation_steps` with experiment, metric and timeframe |
| Looks into the future | Market trends/headwinds, scenarios, and the "Future outlook" section |

## Promised approach

| Proposal statement | Implementation |
|---|---|
| Open-source LLMs (Llama/Qwen) with a small tool library | `OpenAICompatLLM` for Ollama/vLLM/llama.cpp; five tools in `tools/search.py` |
| APIs such as Google RSS to scrape news | `news_search` uses Google News RSS; plus Wikipedia, Hacker News and page fetch |
| transformers, pandas and similar | pandas for the financial model; model inference via an OpenAI-compatible server |
| Coordinator divides the idea into research tasks | Coordinator agent writes per-agent research questions |
| "Swarm" of agentic LLMs access the right tools | Parallel researchers with per-agent tool sets; coordinator can add specialists dynamically |
| Results ingested by a different agent instance to write a report backed by evidence | Synthesizer agent + evidence ledger + grounding checks |
| Separate sourced facts from estimates (problem statement) | Fact/estimate labels, machine-checked citations, evidence grade |

## Beyond the proposal (agentic behavior)

- **Tool loops with autonomy:** each agent chooses queries, reads results, fetches pages and decides when to stop.
- **Critic loop:** automated plus LLM review that sends weak sections back for another pass.
- **Dynamic planning:** the coordinator can create new specialist agents per idea.
- **Guardrails:** deterministic verdict cap and sanity checks around LLM judgments.

## Milestones

| Phase | Planned | Status in this repository |
|---|---|---|
| Weeks 1-4 | Choose approach and tools; coordinator and idea-input workflow | Done: coordinator, CLI and web UI input, tool library |
| Weeks 5-8 | Specialized agents (customer, competitor, ...) | Done: customer, competitor, market, technical, financial, synthesizer, critic, dynamic extras |
| Weeks 9-12 | Tune agents, change tools/resources, demo on existing businesses | Harness ready in `eval/demo_cases.py`; **running it with the team's chosen model and recording results is the next step** |
| Final weeks | Final validation, fine-tuning, deployment | Streamlit app and CLI are the deployment surface; remaining: model selection, tuning from eval results |

## Stretch goal: product and technology recommendations

Not implemented. A natural extension: a "Differentiation" agent that reads the competitor weaknesses and technical
findings and proposes 3 differentiators with a feasibility check, wired in as another entry in `RESEARCHERS`
(see [DEVELOPMENT.md](DEVELOPMENT.md)).

## Risks named in the proposal and mitigations

| Risk | Mitigation |
|---|---|
| Outdated or unavailable information | Agents are told today's date and to note statistic years; news RSS for recency; unsupported numbers become labelled estimates |
| Ill-advised recommendations from lack of context | Critic loop, evidence grade, sanity flags, and the verdict guardrail that blocks unsupported "go" |

## Suggested team split (from the proposal roles)

| Member | Role | Natural ownership |
|---|---|---|
| Srivathsan Badrinarayanan | Agents building | `agents/`, `pipeline.py`, prompts |
| Jimmy Wang | Data collection | `tools/`, search providers, new data sources |
| Jacob Barry | Debugging and validation | `tests/`, `eval/`, `quality.py` |
| Owen Liston | Agents deploying | `app.py`, model serving, configuration, packaging |
