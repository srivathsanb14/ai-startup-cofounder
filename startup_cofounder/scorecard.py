"""Honest quality reporting: execution status kept separate from research quality.

The old single grade rewarded volume (sources collected, findings labelled fact, competitor names seen anywhere).
Here each dimension is measured separately and the overall grade is capped by the worst problems, so irrelevant
facts, duplicate passages and wrong-company matches cannot inflate confidence.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

SECTION_STATES = ("complete", "incomplete", "empty", "off_topic", "failed", "not_run")


def section_state(role: str, result, issues: Sequence) -> str:
    if result is None:
        return "not_run"
    if result.error:
        return "failed" if "budget" not in str(result.error).lower() else "not_run"
    if not result.output:
        return "empty"
    mine = [i for i in issues if i.section == role and i.status in ("open", "unresolved")]
    if any("off-topic" in i.id for i in mine):
        return "off_topic"
    if any(i.severity == "high" for i in mine):
        return "incomplete"
    return "complete"


def build(results: Dict[str, object], claims: Sequence, issues: Sequence, cited_ids: Sequence[str], book, ledger,
          competitors: Sequence[dict], budget_exhausted: Sequence[str], core_roles: Sequence[str],
          fin_mode: str, llm_stats: dict = None, selection_log: Sequence[dict] = ()) -> dict:
    sections = {r: section_state(r, results.get(r), issues) for r in list(core_roles) + [
        k for k in results if k not in core_roles and k not in ("financial", "synthesizer")]}
    failed = [r for r, s in sections.items() if s in ("failed", "not_run", "empty")]
    execution = {
        "status": "partial" if (budget_exhausted or failed) else "complete",
        "sections_not_completed": failed,
        "budget_exhausted_phases": sorted(budget_exhausted),
        "llm": llm_stats or {},
    }
    cited = [i for i in dict.fromkeys(cited_ids) if ledger.get(i)]
    rel = [i for i in cited if book.of(ledger.get(i)).label != "irrelevant"]
    selected = [e for e in selection_log if e.get("decision") == "selected"]
    dupes = [e for e in selection_log if e.get("why") == "duplicate passage"]
    fact_claims = [c for c in claims if c.kind == "fact"]
    supported = [c for c in claims if c.status == "supported"]
    partial = [c for c in claims if c.status == "partially_supported"]
    profiled = [c for c in competitors if isinstance(c, dict)]
    verified = [c for c in profiled if c.get("verified")]
    open_or_unres = [i for i in issues if i.status in ("open", "unresolved")]
    sev = {s: sum(1 for i in open_or_unres if i.severity == s) for s in ("high", "medium", "low")}
    quality = {
        "source_relevance": {"cited": len(cited), "relevant": len(rel),
                             "share": round(len(rel) / len(cited), 2) if cited else None},
        "duplicate_passages_excluded": len(dupes),
        "evidence_items_selected": len(selected),
        "claims": {"total": len(claims), "supported": len(supported), "partially_supported": len(partial),
                   "unsupported": sum(1 for c in claims if c.status == "unsupported"),
                   "contradicted": sum(1 for c in claims if c.status == "contradicted"),
                   "assumptions": sum(1 for c in claims if c.status == "explicit_assumption"),
                   "supported_coverage": round(len(supported) / len(claims), 2) if claims else 0.0,
                   "at_least_partial_coverage": round((len(supported) + len(partial)) / len(claims), 2) if claims else 0.0,
                   "model_checked": sum(1 for c in claims if c.model_check)},
        "competitor_identity": {"profiled": len(profiled), "verified": len(verified),
                                "rejected_irrelevant": sum(1 for c in profiled if c.get("relation") == "irrelevant"),
                                "unresolved": sum(1 for c in profiled if c.get("relation") == "unresolved")},
        "section_completeness": sections,
        "unresolved_issues": sev,
        "financial_mode": fin_mode,
    }
    grade, reasons = _grade(quality, execution)
    return {"execution": execution, "research_quality": quality, "grade": grade, "grade_reasons": reasons}


def _grade(q: dict, execution: dict):
    claims = q["claims"]
    support = claims["supported_coverage"] + 0.5 * (claims["at_least_partial_coverage"] - claims["supported_coverage"])
    rel = q["source_relevance"]["share"] or 0.0
    complete = sum(1 for s in q["section_completeness"].values() if s == "complete")
    total = max(1, len(q["section_completeness"]))
    ident = q["competitor_identity"]
    comp = min(ident["verified"], 3) / 3.0
    score = 0.35 * support + 0.25 * rel + 0.25 * (complete / total) + 0.15 * comp
    grade = "A" if score >= 0.75 else "B" if score >= 0.55 else "C" if score >= 0.35 else "D"
    reasons = ["%.0f%% of claims supported or partially supported (%d model-checked)" % (
        100 * claims["at_least_partial_coverage"], claims["model_checked"]),
        "%s of cited sources are relevant" % ("%.0f%%" % (100 * rel) if q["source_relevance"]["cited"] else "none"),
        "%d of %d sections complete" % (complete, total),
        "%d competitor(s) with identity evidence, %d rejected as unrelated" % (ident["verified"],
                                                                              ident["rejected_irrelevant"])]
    caps = []
    high = q["unresolved_issues"]["high"]
    if high:
        caps.append(("C" if high <= 2 else "D", "%d unresolved high-severity issue(s)" % high))
    if any(s == "off_topic" for s in q["section_completeness"].values()):
        caps.append(("D", "a section is off-topic"))
    if execution["status"] != "complete":
        caps.append(("C", "execution incomplete (%s)" % ", ".join(
            execution["sections_not_completed"] + execution["budget_exhausted_phases"])))
    if q["financial_mode"] != "evidence_backed":
        caps.append(("B", "financial projection is illustrative"))
    for cap, why in caps:
        if "ABCD".index(cap) > "ABCD".index(grade):
            grade = cap
        reasons.append("capped: " + why)
    return grade, reasons
