#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")"
export LLM_BACKEND=openai
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_API_KEY=ollama
export LLM_MODEL=qwen2.5:3b-instruct
export LLM_FAST_MODEL=qwen2.5:3b-instruct
export MAX_WORKERS=1
export MAX_EXTRA_SPECIALISTS=2
export CRITIC_ROUNDS=3
export COMPETITOR_PROFILES=6
export LLM_MAX_TOKENS=2400
export COORDINATOR_MAX_TOKENS=1000
export LLM_TIMEOUT=240
export LLM_ATTEMPTS=2
export RUN_MINUTES=60
export RESUME=0
# Reliability workflow (2026-11-06). LLM_MAX_TOKENS above stays a ceiling; replies are capped per role so that
# prompt + reply fit the context window below. Raise LLM_CONTEXT_TOKENS only together with OLLAMA_CONTEXT_LENGTH,
# after measuring memory with scripts/measure_context.py.
export LLM_CONTEXT_TOKENS=4096
export SECTION_SEARCHES=5
export SECTION_FETCHES=2
export PLANNER_STEPS=2
export RUN_SEARCHES=45
export RUN_FETCHES=16
export CLAIM_CHECK=1
export OFFLINE=0
exec caffeinate -i .venv/bin/python -m streamlit run app.py
