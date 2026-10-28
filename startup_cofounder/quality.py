"""Quality control: rule-based gap detection, competitor verification, evidence grade, verdict guardrail.

Rules here are deliberately deterministic. LLM reviewers are useful but unreliable;
anything we can check with code (counts, presence, string matching) we check with code,
and the LLM critic only adds judgment on top.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

from .evidence import EvidenceLedger

CORE_ROLES = ("customer", "competitor", "market", "technical")
SUFFIXES = r"\b(inc|llc|ltd|corp|corporation|co|company|gmbh|plc|the|\(mock\))\b\.?"


@dataclass
class Gap:
    agent: str
    issue: str
    followup: str
    origin: str = "rule"  # "rule" | "critic"

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(SUFFIXES, " ", str(name).lower())).strip(" .,-")


def name_seen(name: str, corpus: str) -> bool:
    """True if a company/product name (or its distinctive first word) appears in collected evidence."""
    clean = _clean_name(name)
    if not clean or not corpus:
        return False
    if clean in corpus:
        return True
    first = clean.split()[0]
    return len(first) >= 4 and re.search(r"\b%s\b" % re.escape(first), corpus) is not None


def verify_competitors(result, ledger: EvidenceLedger) -> None:
    """Mark each competitor as seen/unseen in evidence and rank evidence-backed ones first."""
    if result is None or not isinstance(result.output.get("competitors"), list):
        return
    corpus = ledger.corpus()
    comps = [c for c in result.output["competitors"] if isinstance(c, dict) and c.get("name")]
    for c in comps:
        ids = ledger.valid_ids(c.get("source_ids"))
        c["source_ids"] = ids
        c["verified"] = name_seen(c["name"], corpus)
    comps.sort(key=lambda c: not c["verified"])  # stable: relevance order kept within each group
    result.output["competitors"] = comps


def rule_gaps(results: Dict[str, object], ledger: EvidenceLedger) -> List[Gap]:
    gaps: List[Gap] = []
    have_sources = bool(ledger.all())
    corpus = ledger.corpus()
    for role, res in results.items():
        if res.error or not res.output:
            gaps.append(Gap(role, "produced no usable output", "Redo this research from scratch and finish with valid JSON."))
            continue
        out = res.output
        facts = sum(f.kind == "fact" for f in res.findings)
        if have_sources and res.findings and facts == 0 and res.trace:
            gaps.append(Gap(role, "no finding is backed by a cited source",
                            "Cite evidence ids for the claims that your tool results support, quoting numbers exactly."))
        if role == "customer" and not out.get("segments"):
            gaps.append(Gap(role, "no customer segments identified",
                            "Identify at least two concrete customer segments with pain points and what they pay today."))
        if role == "competitor":
            comps = [c for c in out.get("competitors", []) if isinstance(c, dict) and c.get("name")]
            if len(comps) < 3:
                gaps.append(Gap(role, "found only %d competitors (need 3)" % len(comps),
                                "Search 'alternatives to ...' and 'top ... companies' and name at least three real players."))
            elif have_sources and sum(name_seen(c["name"], corpus) for c in comps) < min(2, len(comps)):
                gaps.append(Gap(role, "competitor names do not appear in any retrieved source",
                                "Confirm each competitor with a search result or by fetching its website; drop any you cannot confirm."))
        if role == "market":
            tss = out.get("tam_sam_som") if isinstance(out.get("tam_sam_som"), dict) else {}
            if not all(_positive(tss.get(k)) for k in ("tam_usd", "sam_usd", "som_usd")) or not tss.get("method"):
                gaps.append(Gap(role, "market sizing is incomplete (TAM/SAM/SOM and method required)",
                                "Provide numeric TAM, SAM and SOM in USD and explain the method; search for industry size reports."))
        if role == "technical" and out.get("feasibility_score") in (None, ""):
            gaps.append(Gap(role, "no feasibility score", "Give a 1-5 feasibility score with the reasons."))
    return gaps


def _positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def merge_gaps(rule: List[Gap], critic: List[Gap], valid_agents, limit: int = 3) -> List[Gap]:
    """One gap per agent (rules first, since they are checkable), capped to bound cost."""
    merged: Dict[str, Gap] = {}
    for g in list(rule) + list(critic):
        if g.agent in valid_agents and g.agent not in merged:
            merged[g.agent] = g
    return list(merged.values())[:limit]


def parse_critic(output: dict) -> List[Gap]:
    gaps = []
    for g in output.get("gaps", []) if isinstance(output.get("gaps"), list) else []:
        if isinstance(g, dict) and g.get("agent") and g.get("issue"):
            gaps.append(Gap(str(g["agent"]).strip().lower(), str(g["issue"]),
                            str(g.get("followup_task") or g["issue"]), "critic"))
    return gaps


def evidence_grade(results: Dict[str, object], sources_count: int) -> Tuple[str, List[str]]:
    """A-D grade of how well-supported the research is, with the reasons."""
    findings = [f for r in results.values() for f in r.findings]
    facts = sum(f.kind == "fact" for f in findings)
    fact_ratio = facts / len(findings) if findings else 0.0
    comps = [c for c in (results.get("competitor").output.get("competitors", []) if results.get("competitor") else [])
             if isinstance(c, dict)][:3]
    comp_ratio = sum(bool(c.get("verified")) for c in comps) / 3.0  # the target is three confirmed competitors, so finding one is not full marks
    errors = sum(bool(r.error) for r in results.values())
    score = 0.5 * fact_ratio + 0.2 * min(sources_count / 15.0, 1.0) + 0.2 * comp_ratio + 0.1 * (errors == 0)
    grade = "A" if score >= 0.7 else "B" if score >= 0.5 else "C" if score >= 0.3 else "D"
    reasons = ["%d%% of findings are sourced facts" % round(100 * fact_ratio),
               "%d sources collected" % sources_count,
               "%d of 3 target competitors confirmed in evidence" % sum(bool(c.get("verified")) for c in comps)]
    if errors:
        reasons.append("%d agent(s) failed" % errors)
    return grade, reasons


def cap_verdict(verdict: Optional[str], grade: str, ue: dict, breakeven_year: Optional[int]) -> Tuple[str, str]:
    """Never let an LLM say 'go' when evidence or economics do not support it."""
    verdict = (verdict or "").lower()
    if verdict not in ("go", "validate_first", "pivot", "no_go"):
        return "validate_first", "No valid verdict from the synthesizer; defaulting to validate_first."
    if verdict == "go":
        reasons = []
        if grade not in ("A", "B"):
            reasons.append("evidence grade is %s" % grade)
        ratio = ue.get("ltv_cac")
        if ratio is None or ratio < 3:
            reasons.append("LTV/CAC is %s (needs >= 3)" % ("n/a" if ratio is None else "%.1f" % ratio))
        if breakeven_year is None:
            reasons.append("no operating break-even within 5 years")
        if reasons:
            return "validate_first", "Downgraded from 'go' by guardrail: " + "; ".join(reasons) + "."
    return verdict, ""
