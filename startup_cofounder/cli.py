from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .config import Config
from .pipeline import Pipeline
from .report import render_markdown


def _print_event(event: dict) -> None:
    detail = (" - " + event["detail"]) if event.get("detail") else ""
    print("  [%-11s] %s%s" % (event["stage"], event["status"], detail), file=sys.stderr, flush=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "idea"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="startup_cofounder", description="Evidence-backed startup assessment from a rough idea.")
    parser.add_argument("idea", help="your business idea, in plain English")
    parser.add_argument("--mock", action="store_true", help="use the placeholder LLM (no model server needed)")
    parser.add_argument("--offline", action="store_true", help="disable network tools")
    parser.add_argument("--rounds", type=int, help="critic review rounds (0 disables), default CRITIC_ROUNDS")
    parser.add_argument("--max-tools", type=int, help="tool calls per agent, default MAX_TOOL_CALLS")
    parser.add_argument("--model", help="override LLM_MODEL")
    parser.add_argument("--base-url", help="override LLM_BASE_URL")
    parser.add_argument("--out", help="markdown output path (default outputs/<slug>.md)")
    args = parser.parse_args(argv)

    config = Config.from_env(
        backend="mock" if args.mock else None, offline=True if args.offline else None,
        model=args.model, base_url=args.base_url, critic_rounds=args.rounds, max_tool_calls=args.max_tools)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    print("Researching: %s" % args.idea, file=sys.stderr)
    try:
        assessment = Pipeline(config, on_event=_print_event).run(args.idea)
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    md_path = Path(args.out) if args.out else config.output_dir / (slugify(args.idea) + ".md")
    md_path.write_text(render_markdown(assessment))
    md_path.with_suffix(".json").write_text(json.dumps(assessment.to_dict(), indent=2, default=str))
    print("\nReport written to %s (raw data: %s)" % (md_path, md_path.with_suffix(".json")), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
