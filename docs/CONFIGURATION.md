# Configuration and troubleshooting

Settings come from environment variables, optionally loaded from `.env` in the project root
(copy `.env.example`). Real environment variables override `.env`. CLI flags override both.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BACKEND` | `openai` | `openai` = any OpenAI-compatible server; `mock` = placeholder LLM |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Server root (Ollama default shown) |
| `LLM_MODEL` | `qwen2.5:7b-instruct` | Model name as the server knows it |
| `LLM_FAST_MODEL` | empty | Smaller model for the extraction steps (coordinator, sections, profiles); empty means use `LLM_MODEL` |
| `LLM_API_KEY` | `ollama` | Bearer token; local servers ignore it |
| `LLM_TEMPERATURE` | `0.2` | Low is better for structured output |
| `LLM_TIMEOUT` | `600` | Seconds per model call (a 14B model on a laptop needs minutes for long prompts) |
| `RESUME` | `1` | Resume an interrupted run of the same idea from its stage checkpoints (`0` disables) |
| `MAX_WORKERS` | `4` | Sections/searches running in parallel |
| `CRITIC_ROUNDS` | `1` | Review-and-redo rounds; `0` disables the critic loop |
| `MAX_EXTRA_SPECIALISTS` | `2` | Extra idea-specific researchers the coordinator may add; `0` disables |
| `BRAVE_API_KEY` | empty | Enables Brave Search for `web_search` |
| `SEARXNG_URL` | empty | Enables a SearXNG instance for `web_search` |
| `DISABLED_TOOLS` | empty | Comma-separated tools hidden from the pipeline, e.g. `web_search` when no search provider is available |
| `OFFLINE` | `0` | `1` disables all network tools |
| `AGENT_DESIGN` | `questions` | `questions` = research-planning agent + question-scoped analysts + decision synthesis (report-v4, see [AGENTS_V4.md](AGENTS_V4.md)); `sections` = the previous section agents (report-v3) |
| `QUESTION_REPAIRS` | `3` | Per-question repair attempts per run (questions with no usable evidence or judged off-question) |
| `ILLUSTRATIVE_PROJECTION` | `0` | `1` adds an explicitly illustrative 5-year cohort projection even when its inputs are not evidence-based |

## Setting up Ollama with the script

`scripts/setup_ollama.sh` (macOS and Linux) does the whole local-model setup and is safe to re-run:

| Step | Detail |
|---|---|
| Disk check | refuses to start if free space is below the model's estimate (about 15 GB for 14b, 10 GB for 7b) |
| Install | skips if Ollama exists; macOS uses Homebrew if present, else downloads the official zip, verifies `codesign` and Gatekeeper, and refuses to overwrite an existing app; Linux downloads the official installer to a file, prints its hash, and runs it only after confirmation |
| Server | reuses a running server, else opens the app or runs `ollama serve`, waiting up to 60s |
| Model | `ollama pull` (resumable) unless already pulled |
| Verify | sends a test request to the OpenAI-compatible endpoint and checks for a reply |
| Configure | creates `.env` from `.env.example` if missing (backs up an existing one to `.env.bak`) and sets `LLM_BACKEND`, `LLM_BASE_URL`, `LLM_MODEL` |

Flags: `--dry-run` (print only), `--model NAME`, `--fast-model NAME` (also pulls it and sets `LLM_FAST_MODEL`), `--yes` (no prompts), `--no-pull`, `--disable-web-search`.

## Choosing a model

| Setup | Expectation |
|---|---|
| 7-8B (qwen2.5:7b, llama3.1:8b) | Works; research is thin, occasional malformed JSON, more critic redos |
| 14B (qwen2.5:14b) | Good sweet spot for laptops with 16GB+ |
| 32B+ or hosted vLLM | Best quality; follows the schema and cites reliably |

Other servers: vLLM (`--served-model-name`), llama.cpp (`llama-server`), LM Studio all expose
`/v1/chat/completions`; set `LLM_BASE_URL` and `LLM_MODEL` accordingly.

## Search providers

`web_search` tries providers in order and falls through on error or empty results:

1. **Brave** if `BRAVE_API_KEY` is set (reliable; free tier available).
2. **SearXNG** if `SEARXNG_URL` is set. Your instance must allow JSON: in `settings.yml`, under
   `search: formats:` include `json`.
3. **`ddgs` library** (DuckDuckGo, keyless, installed by `requirements.txt`). Results are cached on disk for 24 hours
   like every other tool. Skipped if the package is missing; it can be rate-limited.
4. **DuckDuckGo HTML scraping**: last resort, usually blocked. When blocked, the tool reports it,
   which then uses `news_search`, `wikipedia` or `hn_search`.

`news_search`, `wikipedia`, `hn_search` and page fetching need no keys.

## Two models: main and fast

Extraction (reading evidence into structured JSON) is the bulk of the calls and does not need the biggest model.
Set `LLM_FAST_MODEL=qwen2.5:7b-instruct` with `LLM_MODEL=qwen2.5:14b-instruct`: the fast model handles the coordinator,
all section extraction and competitor profiles; the main model handles the competitor summary, critic, financial
assumptions and the final memo. Ollama loads both models on demand, so you need memory for them or accept swap time;
with the same model for both (the default) there is no swapping.

## Resuming interrupted runs

The pipeline saves each finished stage to `.cache/runs/<key>.json`. If a run is interrupted (timeout, closed laptop, killed
process), run the same command again and it resumes. The key covers the idea, backend, models, offline flag and
`DISABLED_TOOLS`, so changing any of them starts fresh. Use `--fresh` to force a clean run, or delete `.cache/runs/`.

## Cost and speed

Rough model calls per run with defaults: coordinator 1, sections 3 + extras, competitors about 6 (names, up to 4
profiles, summary), critic 1, up to 3 redos, financial 1, synthesizer 1: about 15-20 calls, each with a short prompt
(retrieval is not an LLM call). To go faster use `--quick` (or `--rounds 0`), a small `LLM_FAST_MODEL` such as `qwen2.5:7b-instruct`, or
`MAX_EXTRA_SPECIALISTS=0`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `LLM call failed ... Is your model server running` | Start it (`ollama serve`), check `LLM_BASE_URL` and that `LLM_MODEL` is pulled |
| Report warns about failed sections | Model server timed out or crashed: raise `LLM_TIMEOUT`, check `ollama ps`, then rerun the same command to resume from the checkpoint |
| Rerun returns instantly with old results | It resumed a completed run; use `--fresh` for new research |
| Evidence grade D, "every finding is an estimate" | Offline mode, no network, or search blocked: set a search provider or check connectivity |
| Many "downgraded" claims in Evidence quality | Normal with small models; they paraphrase numbers. Try a bigger model |
| `web_search` says blocked or returns nothing | Free search was rate-limited or blocked: wait, or set `BRAVE_API_KEY` or `SEARXNG_URL` |
| SearXNG returns nothing | JSON format not enabled in its `settings.yml` |
| Stale results | Delete `.cache/` (24h cache) |
| `.env` value ignored | A real environment variable of the same name takes priority; inline comments must be preceded by a space then `#` |
| Slow runs | Lower `CRITIC_ROUNDS`; if the model server is single-GPU, parallel calls queue anyway |
