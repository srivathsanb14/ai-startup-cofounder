"""Compare workflows and models on the SAME saved evidence (no live web).

Isolates interpretation and validation from retrieval: every search is answered from the sources stored in a saved
assessment JSON (BM25 over saved titles/snippets) and every page fetch returns the saved passages of that page.
Both workflows therefore see identical evidence; differences come from the workflow (and model) only.

    # plumbing check, no model needed (seconds):
    python eval/compare_workflows.py --evidence outputs/assessment-20261105-155236-096579.json --mock

    # current model, baseline vs improved workflow (two full runs; ~1-2 h on an 8 GB Mac with a 3B model):
    python eval/compare_workflows.py --evidence outputs/assessment-20261105-155236-096579.json --minutes 45

    # a stronger model later, only if you authorise it (same evidence, same scoring):
    python eval/compare_workflows.py --evidence ... --model qwen2.5:7b-instruct --workflow improved

Every output is scored by startup_cofounder.audit (the same validators for both), and a summary table is written to
outputs/compare-<timestamp>/summary.md. Live adaptive retrieval is tested separately with the normal CLI or app.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval" / "baseline_pkg"))

from startup_cofounder.audit import audit  # noqa: E402
from startup_cofounder.passages import bm25  # noqa: E402

PACKAGES = {"baseline": "startup_cofounder_baseline", "improved": "startup_cofounder"}


class FrozenWeb:
    """Answers searches and page fetches from a saved assessment's sources only."""

    def __init__(self, sources):
        self.results = [s for s in sources if s.get("tool") != "passage"]
        self.pages = {}
        for s in sources:
            if s.get("tool") == "passage" and "#p" in s.get("url", ""):
                base, _, idx = s["url"].rpartition("#p")
                self.pages.setdefault(base, []).append((int(idx) if idx.isdigit() else 0, s.get("snippet", "")))
        self.calls = []

    def search(self, query):
        scores = bm25(query, ["%s %s" % (s.get("title", ""), s.get("snippet", "")) for s in self.results])
        order = sorted(range(len(self.results)), key=lambda i: -scores[i])
        hits = [self.results[i] for i in order[:8] if scores[i] > 0]
        self.calls.append({"query": query, "hits": len(hits)})
        return [{"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("snippet", "")} for h in hits]

    def page(self, url, limit=30000):
        parts = sorted(self.pages.get(url, []))
        if not parts:
            raise RuntimeError("page not in saved evidence")
        return url, " ".join(p for _, p in parts)[:limit]


def patch(pkg, web: FrozenWeb) -> None:
    tools = importlib.import_module(pkg + ".tools")
    search = importlib.import_module(pkg + ".tools.search")
    retrieval = importlib.import_module(pkg + ".retrieval")
    for name in list(search.ALL_TOOLS):
        t = search.ALL_TOOLS[name]
        search.ALL_TOOLS[name] = tools.Tool(name, t.description, t.args,
                                            lambda query, _w=web: tools.ToolResult(sources=_w.search(query)))
    retrieval.page_text = web.page


def run_one(workflow: str, idea: str, web: FrozenWeb, args, out_dir: Path) -> dict:
    pkg = PACKAGES[workflow]
    patch(pkg, web)
    cfg_mod = importlib.import_module(pkg + ".config")
    pipe_mod = importlib.import_module(pkg + ".pipeline")
    report_mod = importlib.import_module(pkg + ".report")
    overrides = dict(backend="mock" if args.mock else None, model=args.model, fast_model=args.model or None,
                     cache_dir=out_dir / ("cache-" + workflow), offline=False, resume=False,
                     run_minutes=args.minutes, max_workers=1)
    cfg = cfg_mod.Config.from_env(**{k: v for k, v in overrides.items() if v is not None})
    started = time.monotonic()
    events = []
    result = pipe_mod.Pipeline(cfg, on_event=events.append).run(idea, fresh=True)
    elapsed = time.monotonic() - started
    data = result.to_dict()
    (out_dir / ("%s.json" % workflow)).write_text(json.dumps(data, indent=2, default=str))
    (out_dir / ("%s.md" % workflow)).write_text(report_mod.render_markdown(result))
    scored = audit(data)
    return {"workflow": workflow, "model": cfg.model if not args.mock else "mock", "elapsed_s": round(elapsed),
            "self_reported_grade": data.get("evidence_grade"), "verdict": data.get("verdict"),
            "audit_open_issues": scored["open_issue_counts"], "audit_claims": scored["claims"],
            "audit_financial_mode": scored["financial"]["mode"], "audit_final_review": scored["final_review"],
            "verified_competitors": [c["name"] for c in scored["sections"].get("competitor", {}).get("competitors", [])
                                     if c.get("verified")],
            "searches_answered": len(web.calls)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--evidence", required=True, help="saved assessment JSON whose sources become the frozen web")
    p.add_argument("--idea", help="idea text (default: the idea in the evidence file)")
    p.add_argument("--workflow", choices=["baseline", "improved", "both"], default="both")
    p.add_argument("--model", help="model name for both main and fast roles (default: LLM_MODEL from env)")
    p.add_argument("--minutes", type=int, help="time budget per run (default: RUN_MINUTES)")
    p.add_argument("--mock", action="store_true", help="placeholder model: checks the harness only")
    args = p.parse_args(argv)
    saved = json.loads(Path(args.evidence).read_text())
    idea = args.idea or saved["idea"]
    out_dir = ROOT / "outputs" / ("compare-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for wf in (["baseline", "improved"] if args.workflow == "both" else [args.workflow]):
        print("Running %s workflow on frozen evidence (%d sources)..." % (wf, len(saved["sources"])), file=sys.stderr)
        rows.append(run_one(wf, idea, FrozenWeb(saved["sources"]), args, out_dir))
    lines = ["# Workflow comparison on frozen evidence", "", "Evidence: `%s` (%d sources). Idea: %s" % (
        args.evidence, len(saved["sources"]), idea), "",
        "| Workflow | Model | Minutes | Self-reported grade | Verdict | Audit: open high/med/low | Claims supported/partial/"
        "unsupported | Financial mode | Final-review issues | Verified competitors |",
        "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        oi, cl = r["audit_open_issues"], r["audit_claims"]
        lines.append("| %s | %s | %.1f | %s | %s | %d/%d/%d | %d/%d/%d | %s | %d | %s |" % (
            r["workflow"], r["model"], r["elapsed_s"] / 60, r["self_reported_grade"], r["verdict"], oi["high"],
            oi["medium"], oi["low"], cl["supported"], cl["partially_supported"], cl["unsupported"],
            r["audit_financial_mode"], len(r["audit_final_review"]), ", ".join(r["verified_competitors"]) or "none"))
    lines += ["", "The audit columns re-check each output with the same validators, so a workflow cannot score well "
              "by grading itself. Inspect the per-workflow .md/.json files for details."]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2))
    print("\n".join(lines))
    print("\nWritten to %s" % out_dir, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
