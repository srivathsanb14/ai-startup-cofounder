"""Re-check a saved assessment JSON (old or new format) with the current validators, without calling a model.

Used by the regression tests (the failed 2026-11-05 run) and by eval/compare_workflows.py to score baseline and
improved outputs on the same yardstick:  python -m startup_cofounder.audit outputs/assessment-....json
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List

from . import claims as claimlib
from . import final_review, fininputs, identity, issues as issuelib
from .evidence import EvidenceLedger, Source
from .finance import project, unit_economics
from .relevance import RelevanceBook, ResearchFrame

CORE = ("customer", "competitor", "market", "technical")


def ledger_from_sources(sources: List[dict]) -> EvidenceLedger:
    """Rebuild a ledger with the exact saved ids (no renumbering)."""
    ledger = EvidenceLedger()
    for s in sources:
        src = Source(s["id"], s.get("title", ""), s.get("url", ""), s.get("snippet", ""), s.get("tool", ""))
        ledger._by_id[src.id] = src
        if src.url and src.url not in ledger._by_url:
            ledger._by_url[src.url] = src
    return ledger


def audit(d: dict) -> dict:
    ledger = ledger_from_sources(d.get("sources", []))
    frame = ResearchFrame.from_plan(d.get("plan", {}), d.get("idea", ""))
    book = RelevanceBook(frame)
    agents = d.get("agents", {})
    tracker = issuelib.Tracker()
    all_claims: List[claimlib.Claim] = []
    sections: Dict[str, dict] = {}
    for role, a in agents.items():
        if role in ("financial", "synthesizer"):
            continue
        out = dict(a.get("output") or {})
        cl = claimlib.claims_from_findings(role, out.get("findings") or [], ledger, book, frame)
        ev = []
        for t in a.get("trace") or []:
            ev += t.get("source_ids", []) or []
        if role == "competitor":
            reclassified = []
            for c in out.get("competitors", []):
                if isinstance(c, dict) and c.get("name"):
                    reclassified.append(identity.classify(c, c["name"], ledger, book, [s.id for s in ledger.all()]))
            out["competitors"] = [c for c in reclassified if c["relation"] != "irrelevant"]
            out["rejected"] = [c for c in reclassified if c["relation"] == "irrelevant"]
            sections[role] = {"competitors": [{k: c.get(k) for k in ("name", "relation", "verified", "official_domain",
                                                                     "identity_note")} for c in reclassified]}
        found = issuelib.section_issues(role, out, a.get("error"), frame, cl, ev, book, ledger)
        tracker.update(role, found)
        all_claims += cl
        sections.setdefault(role, {})["issues"] = [i.id for i in found]
        sections[role]["claims"] = claimlib.coverage(cl)
        cited = [i for c in cl for i in c.source_ids]
        sections[role]["cited_sources"] = len(set(cited))
        sections[role]["cited_irrelevant"] = sorted({i for i in cited if ledger.get(i) and
                                                     book.of(ledger.get(i)).label == "irrelevant"})
    fin = agents.get("financial", {})
    fout = fin.get("output") or {}
    fin_cited = [i for f in fout.get("findings") or [] if isinstance(f, dict) for i in f.get("source_ids") or []]
    for t in fin.get("trace") or []:
        fin_cited += t.get("source_ids", []) or []
    cust = (agents.get("customer") or {}).get("output") or {}
    inputs, fin_issues, mode = fininputs.validate(fout.get("assumptions"), fout.get("inputs"), frame, ledger, book,
                                                  list(dict.fromkeys(fin_cited)), cust)
    fin_claims = claimlib.claims_from_findings("financial", fout.get("findings") or [], ledger, book, frame)
    fin_rule = issuelib.section_issues("financial", {"summary": fout.get("rationale", ""),
                                                     "findings": fout.get("findings", [])}, None, frame, fin_claims)
    for i in fin_issues + [x for x in fin_rule if "off-topic" in x.id or "irrelevant-citations" in x.id]:
        tracker.issues[i.id] = i
    proj = project(fout.get("assumptions"))
    ue = unit_economics(proj.assumptions)
    computed = {"projection": proj.to_dict(), "unit_economics": ue}
    market_valid = not any(i.section == "market" and "sizing" in i.id for i in tracker.open())
    final = final_review.check(d.get("synthesis") or {}, computed, customer_output=cust, open_issues=tracker.open(),
                               fin_mode=mode, market_valid=market_valid)
    for i in final:
        tracker.issues[i.id] = i
    sev = {s: sum(1 for i in tracker.issues.values() if i.severity == s and i.status == "open")
           for s in ("high", "medium", "low")}
    return {
        "frame": frame.describe(),
        "sections": sections,
        "financial": {"mode": mode, "inputs": [i.to_dict() for i in inputs]},
        "final_review": [i.id for i in final],
        "issues": [i.to_dict() for i in tracker.issues.values()],
        "open_issue_counts": sev,
        "claims": claimlib.coverage(all_claims),
        "review_log_labels": [e.get("outcome", "improved" if e.get("improved") else "failed")
                              for e in d.get("review_log", []) if e.get("agent") != "-"],
        "saved_grade": d.get("evidence_grade"),
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m startup_cofounder.audit <assessment.json>", file=sys.stderr)
        return 2
    report = audit(json.load(open(argv[0])))
    print("Frame: %s" % report["frame"])
    print("Saved grade: %s | open issues now: %s | claim statuses: %s" % (report["saved_grade"],
                                                                       report["open_issue_counts"], report["claims"]))
    print("Financial mode: %s" % report["financial"]["mode"])
    for i in sorted(report["issues"], key=lambda i: issuelib.SEVERITY_RANK.get(i["severity"], 3)):
        if i["status"] == "open":
            print("  [%s] %s: %s" % (i["severity"].upper(), i["id"], i["message"][:150]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
