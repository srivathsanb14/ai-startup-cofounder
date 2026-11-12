"""Measure what a larger context window would cost in memory BEFORE changing it (local Ollama only).

Nothing is downloaded and no setting is changed. For each requested context size the script sends one tiny request
through Ollama's native API with options.num_ctx, then reads /api/ps to report the loaded model's memory.

    .venv/bin/python scripts/measure_context.py                       # current model, 4096 and 8192
    .venv/bin/python scripts/measure_context.py --sizes 4096 6144 8192 --model qwen2.5:3b-instruct

To actually use a larger window afterwards, start Ollama with OLLAMA_CONTEXT_LENGTH=<n> (the OpenAI-compatible
endpoint this app uses does not accept num_ctx per request) AND set LLM_CONTEXT_TOKENS=<n> for this app, so prompts
are fitted to the real window. Keep at least ~2 GB of memory free on an 8 GB Mac.
"""
import argparse
import json
import os
import sys

import requests


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen2.5:3b-instruct"))
    p.add_argument("--host", default="http://localhost:11434")
    p.add_argument("--sizes", type=int, nargs="+", default=[4096, 8192])
    args = p.parse_args()
    try:
        ps = requests.get(args.host + "/api/ps", timeout=10).json()
    except Exception as exc:
        print("Ollama is not reachable at %s: %s" % (args.host, exc), file=sys.stderr)
        return 1
    print("Currently loaded:", json.dumps([{k: m.get(k) for k in ("name", "size", "size_vram", "context_length")}
                                          for m in ps.get("models", [])]))
    for n in args.sizes:
        requests.post(args.host + "/api/generate", json={"model": args.model, "prompt": "ok", "stream": False,
                                                          "options": {"num_ctx": n, "num_predict": 1}}, timeout=600)
        models = requests.get(args.host + "/api/ps", timeout=10).json().get("models", [])
        m = next((m for m in models if m.get("name", "").startswith(args.model.split(":")[0])), {})
        print("num_ctx=%-6d loaded size=%.2f GB (in GPU/unified: %.2f GB) reported context=%s" % (
            n, (m.get("size") or 0) / 1e9, (m.get("size_vram") or 0) / 1e9, m.get("context_length", "n/a")))
    print("Compare with free memory (Activity Monitor > Memory) before choosing a size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
