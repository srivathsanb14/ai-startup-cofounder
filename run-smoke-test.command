#!/bin/zsh
# Short live smoke test (about 12-minute ceiling): live web search + local Ollama model, 1 review round,
# 1 optional specialist, 3 competitor profiles, small search budget. Writes outputs/smoke-<time>.md and .json.
set -eu
cd -- "$(dirname -- "$0")"
export LLM_BACKEND=openai
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:3b-instruct
export LLM_FAST_MODEL=qwen2.5:3b-instruct
export MAX_WORKERS=1
export LLM_MAX_TOKENS=2400
export COORDINATOR_MAX_TOKENS=1000
export LLM_CONTEXT_TOKENS=4096
export LLM_TIMEOUT=240
export LLM_ATTEMPTS=2
export RESUME=0
export OFFLINE=0
IDEA="A social app that helps adult indoor climbers in Pittsburgh find compatible climbing partners based on gym, availability, experience, and climbing discipline"
exec caffeinate -i .venv/bin/python -m startup_cofounder --smoke --fresh --out "outputs/smoke-$(date +%Y%m%d-%H%M%S).md" "$IDEA"
