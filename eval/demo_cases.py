"""Validation harness: run the agent on businesses that already exist and check it
rediscovers what we know to be true (the proposal's Weeks 9-12 'authenticity' check).

    python eval/demo_cases.py                 # configured model + live web tools, all cases
    python eval/demo_cases.py --only uber     # cases whose idea contains 'uber'
    python eval/demo_cases.py --mock --offline   # smoke test of the harness only

Writes outputs/eval-<case>.md and outputs/eval-results.json and prints a summary table.
See docs/EVALUATION.md for how to read the metrics.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from startup_cofounder.config import Config  # noqa: E402
from startup_cofounder.pipeline import Pipeline  # noqa: E402
from startup_cofounder.report import render_markdown  # noqa: E402

CASES = [
    {"name": "airbnb", "idea": "An online marketplace where homeowners rent out spare rooms and homes to travelers",
     "known_competitors": ["booking", "vrbo", "expedia", "hotels", "hostel"]},
    {"name": "duolingo", "idea": "A mobile app that teaches languages with short gamified daily lessons",
     "known_competitors": ["babbel", "rosetta", "busuu", "memrise", "duolingo"]},
    {"name": "zoom", "idea": "A video-calling app for remote teams and virtual meetings",
     "known_competitors": ["zoom", "teams", "meet", "webex", "slack"]},
    {"name": "uber", "idea": "A ride-hailing app connecting passengers with nearby drivers",
     "known_competitors": ["uber", "lyft", "bolt", "didi", "grab"]},
]


def score(assessment, known):
    comp = assessment.results.get("competitor")
    comps = [c for c in (comp.output.get("competitors", []) if comp else []) if isinstance(c, dict)]
    names = " ".join(str(c.get("name", "")).lower() for c in comps)
    hits = [k for k in known if k in names]
    findings = [f for r in assessment.results.values() for f in r.findings]
    facts = [f for f in findings if f.kind == "fact"]
    top3 = comps[:3]
    return {
        "competitors_found": len(comps),
        "top3_known_hits": [k for k in known if k in " ".join(str(c.get("name", "")).lower() for c in top3)],
        "known_competitor_hits": hits,
        "competitor_recall": round(len(hits) / len(known), 2),
        "top3_confirmed_in_sources": sum(bool(c.get("verified")) for c in top3),
        "fact_ratio": round(len(facts) / len(findings), 2) if findings else 0.0,
        "downgraded_claims": sum(f.downgraded for f in findings),
        "sources": len(assessment.sources),
        "evidence_grade": assessment.grade,
        "critic_redos": sum(1 for e in assessment.review_log if e["agent"] != "-"),
        "verdict": assessment.verdict,
        "breakeven_year": assessment.projection.breakeven_year,
        "ltv_cac": round(assessment.unit_economics["ltv_cac"], 1) if assessment.unit_economics.get("ltv_cac") else None,
        "agent_errors": [r for r, v in assessment.results.items() if v.error],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", help="substring filter on case name or idea")
    args = parser.parse_args()
    config = Config.from_env(backend="mock" if args.mock else None, offline=True if args.offline else None)
    config.output_dir.mkdir(exist_ok=True)
    rows = []
    for case in CASES:
        if args.only and args.only.lower() not in (case["name"] + case["idea"]).lower():
            continue
        print("running:", case["idea"], file=sys.stderr)
        assessment = Pipeline(config).run(case["idea"])
        rows.append({"case": case["name"], **score(assessment, case["known_competitors"])})
        (config.output_dir / ("eval-%s.md" % case["name"])).write_text(render_markdown(assessment))
    (config.output_dir / "eval-results.json").write_text(json.dumps(rows, indent=2))

    print("\n%-10s %-7s %-8s %-9s %-7s %-6s" % ("case", "recall", "top3 ok", "fact %", "grade", "errors"))
    for r in rows:
        print("%-10s %-7s %-8s %-9s %-7s %-6s" % (
            r["case"], r["competitor_recall"], len(r["top3_known_hits"]), int(100 * r["fact_ratio"]),
            r["evidence_grade"], len(r["agent_errors"])))
    print("\nfull results: %s" % (config.output_dir / "eval-results.json"))


if __name__ == "__main__":
    main()
