# Configuration and troubleshooting

Settings come from environment variables, optionally loaded from `.env` in the project root
(copy `.env.example`). Real environment variables override `.env`. CLI flags override both.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BACKEND` | `openai` | `openai` = any OpenAI-compatible server; `mock` = placeholder LLM |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Server root (Ollama default shown) |
| `LLM_MODEL` | `qwen2.5:7b-instruct` | Model name as the server knows it |
| `LLM_API_KEY` | `ollama` | Bearer token; local servers ignore it |
| `LLM_TEMPERATURE` | `0.2` | Low is better for structured output |
| `LLM_TIMEOUT` | `600` | Seconds per model call (a 14B model on a laptop needs minutes for long prompts) |
| `MAX_TOOL_CALLS` | `6` | Tool calls per agent |
| `MAX_WORKERS` | `4` | Agents running in parallel |
| `CRITIC_ROUNDS` | `1` | Review-and-redo rounds; `0` disables the critic loop |
| `MAX_EXTRA_SPECIALISTS` | `2` | Extra idea-specific agents the coordinator may add; `0` disables |
| `BRAVE_API_KEY` | empty | Enables Brave Search for `web_search` |
| `SEARXNG_URL` | empty | Enables a SearXNG instance for `web_search` |
| `DISABLED_TOOLS` | empty | Comma-separated tools hidden from agents, e.g. `web_search` when no search provider is available |
| `OFFLINE` | `0` | `1` disables all network tools |

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

Flags: `--dry-run` (print only), `--model NAME`, `--yes` (no prompts), `--no-pull`, `--disable-web-search`.

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
3. **DuckDuckGo HTML**: keyless, but may be blocked or return no results. When blocked, the tool tells the agent,
   which then uses `news_search`, `wikipedia` or `hn_search`.

`news_search`, `wikipedia`, `hn_search` and `fetch_page` need no keys.

## Cost and speed

Rough model calls per run with defaults: coordinator 1 + each of 5 researchers up to 7 + critic 1 + redos (up to 3
agents x up to 7) + financial up to 4 + synthesizer 1. A typical run is 30-60 calls. To go faster use
`--rounds 0 --max-tools 3`, or `MAX_EXTRA_SPECIALISTS=0`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `LLM call failed ... Is your model server running` | Start it (`ollama serve`), check `LLM_BASE_URL` and that `LLM_MODEL` is pulled |
| Report warns about failed agents | Model emitted invalid JSON repeatedly: use a larger model, lower `LLM_TEMPERATURE`, or raise `LLM_TIMEOUT` |
| Evidence grade D, "every finding is an estimate" | Offline mode, no network, or search blocked: set a search provider or check connectivity |
| Many "downgraded" claims in Evidence quality | Normal with small models; they paraphrase numbers. Try a bigger model or `MAX_TOOL_CALLS=8` |
| `web_search` says blocked | DuckDuckGo bot check: set `BRAVE_API_KEY` or `SEARXNG_URL` |
| SearXNG returns nothing | JSON format not enabled in its `settings.yml` |
| Stale results | Delete `.cache/` (24h cache) |
| `.env` value ignored | A real environment variable of the same name takes priority; inline comments must be preceded by a space then `#` |
| Slow runs | Lower `MAX_TOOL_CALLS`/`CRITIC_ROUNDS`; if the model server is single-GPU, parallel agents queue anyway |
