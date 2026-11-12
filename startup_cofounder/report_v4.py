"""report-v4: the decision model built from the question-driven agents.

Inputs (from a live run, `d["v4"]`): the idea brief, validated question findings, economics and synthesis.
For older saved runs (v2/v3 JSON with no v4 data) the same agents are re-run over the SAVED evidence only: no web
access and, by default, no model calls. In that mode each question gets the most relevant verbatim passages from
the saved sources ("evidence located; not analysed by a model"); passing `extract_fn` (e.g. the local Ollama model)
lets the analyst interpret the same saved evidence.

The verified competitor table, claim validation and publication gate come from the existing report-v3 model.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Dict, List, Optional

from . import economics2, report_model, synthesis, validators
from .analyst import Analyst, packet
from .audit import ledger_from_sources
from .brief import IdeaBrief, build_brief
from .passages import rank
from .questions import catalog
from .relevance import RelevanceBook, ResearchFrame, terms

SCHEMA = "report-v4"
PEOPLE_RX = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?(?:k|thousand|million)?|\d{2,})(?:\s+[a-z-]+){0,3}?\s+"
                       r"(members|climbers|users|people|players|runners|customers|residents|students|"
                       r"participants|subscribers|businesses|shops|owners|households)\b", re.I)


def competitor_rows(v3: dict) -> List[dict]:
    rows = []
    for r in (v3.get("competition") or {}).get("rows", []):
        price_text = "%s %s" % (r.get("price_short", ""), r.get("pricing", ""))
        free = bool(re.search(r"^free\b|\bfree (basic|to use|tier|plan)|\bare all free|\bis free", price_text, re.I))
        rows.append({"name": r.get("name", ""), "relation": r.get("relation"), "verified": str(r.get("verified"))
                     in ("True", "true", "1") or r.get("verified") is True, "free": free,
                     "price_short": r.get("price_short", ""), "monthly": economics2.prices_in(r.get("pricing", "")),
                     "source": (r.get("cites") or [{}])[0].get("id", "") if isinstance(r.get("cites"), list) else "",
                     "non_app": bool(r.get("non_app"))})
    return rows


def prices_from_findings(questions: Dict[str, dict], comps: List[dict]) -> List[dict]:
    """Competitor prices stated in validated Q-R1 findings (a vendor's own page is the right source for its price),
    attributed to the competitor named in the finding. Marks competitors whose finding says they are free."""
    out = []
    for f in (questions.get("Q-R1") or {}).get("findings") or []:
        if f.get("role") != "finding" or f.get("status") not in synthesis.USABLE:
            continue
        text = f.get("text", "")
        for c in comps:
            first = c["name"].split()[0] if c["name"].split() else ""
            if not first or len(first) < 4 or not re.search(r"\b%s" % re.escape(first), text, re.I):
                continue
            if re.search(r"\bfree\b", text, re.I) and not economics2.prices_in(text):
                c["free"] = True
                c["price_short"] = c["price_short"] if c["price_short"] not in ("", "not stated in sources") else \
                    "free (%s)" % f["id"]
            vals = economics2.prices_in(text)
            if vals:
                out.append({"name": c["name"], "monthly": vals, "source": (f.get("source_ids") or [""])[0]})
                if c["price_short"] in ("", "not stated in sources"):
                    c["price_short"] = "$%s/month (%s)" % ("/".join("%g" % v for v in vals), f["id"])
    return out


def _to_num(tok: str) -> float:
    t = tok.lower().replace(",", "").strip()
    mult = 1000 if t.endswith(("k", "thousand")) else 1e6 if t.endswith("million") else 1
    t = re.sub(r"\s?(k|thousand|million)$", "", t)
    try:
        return float(t) * mult
    except ValueError:
        return 0.0


def market_count(questions: Dict[str, dict], brief) -> Optional[dict]:
    """A local count of people/businesses from validated, local Q-M1 findings (None if there is none)."""
    q = questions.get("Q-M1") or {}
    for f in q.get("findings") or []:
        if f.get("role") != "finding" or f.get("status") not in synthesis.USABLE:
            continue
        text = f.get("text", "") + " " + f.get("passage", "")
        if brief.geography and not (terms(brief.geography) <= terms(text)):
            continue
        for m in PEOPLE_RX.finditer(text):
            v = _to_num(m.group(1))
            if v >= 50:
                return {"value": v, "unit": m.group(2).lower(), "source_id": (f.get("source_ids") or [""])[0],
                        "text": f.get("text", "")[:200], "finding": f["id"]}
    return None


def wtp_findings(questions: Dict[str, dict]) -> List[dict]:
    q = questions.get("Q-W1") or {}
    return [f for f in q.get("findings") or [] if f.get("role") == "finding" and f.get("status") in synthesis.USABLE
            and economics2.prices_in(f.get("text", ""))]


def saved_questions(d: dict, brief, comps: List[dict], extract_fn: Optional[Callable] = None) -> Dict[str, dict]:
    """Answer each research question from the saved sources only (no web)."""
    frame = ResearchFrame.from_plan(d.get("plan", {}), d.get("idea", ""))
    book = RelevanceBook(frame)
    ledger = ledger_from_sources(d.get("sources", []))
    vendors = validators.vendor_domains([{"name": c["name"], "official_domain": next(
        (r.get("official_domain") for r in (d.get("agents", {}).get("competitor", {}).get("output", {})
                                            .get("competitors", []) or []) if r.get("name") == c["name"]), None)}
        for c in comps])
    products = [c["name"] for c in comps if not c.get("non_app")]
    names = [c["name"] for c in comps if c.get("verified") and c.get("relation") in ("direct", "substitute")
             and not c.get("non_app")]
    analyst = Analyst(ledger, None, book, brief, None, lambda *a, **k: None, extract_fn)
    out = {}
    used: set = set()  # one passage answers one question; no repetition across sections
    sources = ledger.all()
    for q in catalog(brief, names):
        query = " ".join([q.text, " ".join(q.keywords)] + [t for _, t in q.queries + q.disconfirm])
        ids = [s.id for s in rank(query, sources, lambda s: s.text + " " + s.url, 30)]
        pk = packet(q, ids, ledger, book, vendors)
        res = {"id": q.id, "topic": q.topic, "question": q.text, "extract": q.extract, "hypotheses": q.hypotheses,
               "queries": [{"query": "(saved evidence only; no new searches)", "origin": "saved"}],
               "candidate_ids": ids, "packet": [s.id for s in pk], "attempt": 1, "repair_reason": ""}
        if extract_fn is None:
            from .analyst import extractive
            res.update(extractive(q, pk, frozenset(frame.core | frame.need), used))
        else:
            res.update(analyst._ask(q, pk, None))
        res.update(analyst.validate(q, res, vendors, products))
        out[q.id] = res
    return out


def build(d: dict, regenerated: bool = False, illustrative: bool = False,
          extract_fn: Optional[Callable] = None) -> dict:
    v3 = report_model.build(d, regenerated=regenerated)
    v4 = d.get("v4") or {}
    brief = IdeaBrief.from_dict(v4["brief"]) if v4.get("brief") else build_brief(d.get("idea", ""), {}, d.get("plan"))
    comps = competitor_rows(v3)
    mode = "live" if v4.get("questions") else ("saved_model" if extract_fn else "saved_extractive")
    questions = v4.get("questions") or saved_questions(d, brief, comps, extract_fn)
    stated = prices_from_findings(questions, comps)
    free = [c["name"] for c in comps if c["verified"] and c["relation"] in ("direct", "substitute") and c["free"]]
    econ = v4.get("economics") or economics2.build(
        brief, wtp_findings(questions),
        [c for c in comps if c["verified"] and c["relation"] in ("direct", "substitute", "adjacent") and c["monthly"]]
        + stated,
        market_count(questions, brief), free, illustrative or bool(v4.get("illustrative_projection")))
    syn = synthesis.synthesize(brief, questions, comps, econ)
    for h in brief.hypotheses:
        h.evidence = syn["hypotheses"].get(h.id, {}).get("level", "none")
    srcs = {s["id"]: s for s in d.get("sources", [])}
    model = {
        "schema": SCHEMA, "generated": date.today().isoformat(), "regenerated_from_saved_data": regenerated,
        "evidence_mode": mode, "title": "Startup assessment: %s" % (brief.product[:60] or "idea"),
        "idea": brief.founder_statement, "brief": brief.to_dict(), "questions": questions,
        "competition": {"rows": comps, "v3": v3["competition"]}, "economics": econ, "synthesis": syn,
        "claims": v3["claims"], "validation": v3["validation"], "source_run": v3.get("source_run"),
        "status": v3.get("status"), "sources": {k: {"url": v.get("url", ""), "title": v.get("title", "")}
                                                for k, v in srcs.items()},
        "repairs": v4.get("repairs", []), "question_review": v4.get("question_review", {}), "v3": v3,
    }
    return model


def trusted_view(model: dict) -> dict:
    """What the publication gate may take numbers from: computed economics, the brief, experiments, competitor
    prices, and only validated question findings."""
    qs = {}
    for k, q in model["questions"].items():
        qs[k] = {"findings": [{"text": f.get("text"), "passage": f.get("passage")} for f in q.get("findings") or []
                              if f.get("status") in synthesis.USABLE]}
    return {"brief": model["brief"], "economics": model["economics"], "experiments": model["synthesis"]["experiments"],
            "checks": model["synthesis"]["checks"], "competition": model["competition"]["rows"], "questions": qs,
            "claims": [c for c in model.get("claims", []) if c.get("status") in synthesis.USABLE]}
