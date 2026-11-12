from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .config import Config
from .pipeline import Pipeline
from .report import render_appendix, render_markdown


def describe_event(event: dict) -> str:
    """One readable progress line: agent, activity, question/reason, elapsed and remaining budget."""
    clock = "%dm%02ds" % divmod(int(event.get("elapsed_s") or 0), 60)
    if event.get("remaining_s") is not None:
        clock += " (phase budget left %dm%02ds)" % divmod(int(event["remaining_s"]), 60)
    bits = ["[%s] %-11s %s" % (clock, event.get("stage", ""), event.get("status", ""))]
    if event.get("detail"):
        bits.append("- " + str(event["detail"]))
    if event.get("question") and event.get("status") in ("start", "extracting", "searching"):
        bits.append("| question: " + str(event["question"])[:90])
    if event.get("reason"):
        bits.append("| why: " + str(event["reason"])[:120])
    return " ".join(bits)


def _print_event(event: dict) -> None:
    print("  " + describe_event(event), file=sys.stderr, flush=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "idea"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="startup_cofounder", description="Evidence-backed startup assessment from a rough idea.")
    parser.add_argument("idea", help="your business idea, in plain English")
    parser.add_argument("--mock", action="store_true", help="use the placeholder LLM (no model server needed)")
    parser.add_argument("--offline", action="store_true", help="disable network tools")
    parser.add_argument("--fresh", action="store_true", help="ignore checkpoints from an interrupted run of the same idea")
    parser.add_argument("--fast-model", help="smaller model for extraction steps (override LLM_FAST_MODEL)")
    parser.add_argument("--rounds", type=int, help="critic review rounds (0 disables), default CRITIC_ROUNDS")
    parser.add_argument("--quick", action="store_true", help="faster, thinner run: no extra specialists, no critic review")
    parser.add_argument("--model", help="override LLM_MODEL")
    parser.add_argument("--base-url", help="override LLM_BASE_URL")
    parser.add_argument("--out", help="markdown output path (default outputs/<slug>.md)")
    parser.add_argument("--minutes", type=int, help="time budget ceiling in minutes (overrides RUN_MINUTES)")
    parser.add_argument("--smoke", action="store_true",
                        help="short live smoke test: 1 review round, 1 specialist, 3 competitor profiles, small search "
                             "budget, 12-minute ceiling")
    args = parser.parse_args(argv)

    config = Config.from_env(
        backend="mock" if args.mock else None, offline=True if args.offline else None,
        model=args.model, fast_model=args.fast_model, base_url=args.base_url, critic_rounds=0 if args.quick and args.rounds is None else args.rounds,
        max_extra_specialists=0 if args.quick else (1 if args.smoke else None),
        run_minutes=args.minutes if args.minutes is not None else (12 if args.smoke else None),
        competitor_profiles=3 if args.smoke else None,
        section_searches=3 if args.smoke else None, planner_steps=1 if args.smoke else None,
        run_searches=25 if args.smoke else None)
    if args.smoke and args.rounds is None:
        object.__setattr__(config, "critic_rounds", 1)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    print("Researching: %s" % args.idea, file=sys.stderr)
    try:
        assessment = Pipeline(config, on_event=_print_event).run(args.idea, fresh=args.fresh)
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    md_path = Path(args.out) if args.out else config.output_dir / (slugify(args.idea) + ".md")
    md_path.write_text(render_markdown(assessment))
    appendix = md_path.with_name(md_path.stem + "-appendix.md")
    appendix.write_text(render_appendix(assessment))
    md_path.with_suffix(".json").write_text(json.dumps(assessment.to_dict(), indent=2, default=str))
    print("\nDecision memo: %s\nEvidence appendix: %s\nData (JSON): %s" % (md_path, appendix,
                                                                         md_path.with_suffix(".json")), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
