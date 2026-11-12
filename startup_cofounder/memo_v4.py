"""Founder decision report (report-v4): a short memo plus a separate evidence appendix.

The memo answers the founder's questions in seven sections and explains what the findings MEAN for the decision.
All text is assembled from validated, structured data (no free-form model prose), so a statement cannot contradict
the computed economics or the evidence levels. Numbers in the memo are checked by the publication gate.
"""
from __future__ import annotations

import re
from typing import Dict, List

from . import report_v4, synthesis, validators
from .report_model import money

VERDICT_LABEL = {"proceed": "Proceed", "validate_first": "Validate first", "modify_concept": "Modify the concept",
                 "abandon_current_approach": "Abandon the current approach"}
LEVEL_WORD = {"supported": "supported by independent evidence", "weak": "only weak or indirect evidence",
              "mixed": "mixed: independent evidence on both sides",
              "none": "no evidence yet", "contradicted": "contradicted by evidence"}
STATUS_WORD = {"answered": "answered", "partial": "partly answered", "insufficient": "not answered by the evidence",
               "evidence_located": "relevant passages located (not analysed by a model)"}


class Cite:
    """Numbers sources in order of first use; the same source keeps its number."""

    def __init__(self, sources: Dict[str, dict]) -> None:
        self.sources, self.order = sources, []

    def __call__(self, ids) -> str:
        out = []
        for i in ids or []:
            if i not in self.sources:
                continue
            if i not in self.order:
                self.order.append(i)
            out.append("[[%d]](%s)" % (self.order.index(i) + 1, self.sources[i].get("url", "")))
        return " " + "".join(out) if out else ""

    def listing(self) -> List[str]:
        return ["%d. [%s](%s) (%s)" % (n + 1, (self.sources[i].get("title") or validators.host(
            self.sources[i].get("url", "")))[:90].replace("[", "(").replace("]", ")"), self.sources[i].get("url", ""), i)
                for n, i in enumerate(self.order)]


def _usable(q: dict) -> List[dict]:
    return [f for f in (q or {}).get("findings") or [] if f.get("role") == "finding"
            and f.get("status") in synthesis.USABLE]


def _q_lines(model: dict, qid: str, cite: Cite, k: int = 2) -> List[str]:
    q = model["questions"].get(qid)
    if not q:
        return []
    lines = []
    texts = [f["text"].strip().lower() for f in _usable(q)[:k]]
    ans = (q.get("answer") or "").strip()
    if ans and not any(_similar(ans.lower(), x) for x in texts):  # an answer that only repeats a finding is skipped
        lines.append("%s%s" % (ans, cite([i for f in _usable(q) for i in f.get("source_ids", [])][:3])))
    for f in _usable(q)[:k]:
        stance = {"contradicts": " (contradicts the founder's assumption)", "supports": ""}.get(f.get("stance"), "")
        quote = f["text"] if q.get("mode") == "model" else '"%s"' % f["text"].strip('" ')
        lines.append("%s%s%s" % (quote, stance, cite(f.get("source_ids"))))
    if not lines:
        lines.append("Not found in the evidence: %s." % (q.get("extract") or q["question"].rstrip("?").lower()))
    return lines


def _see(check: dict, syn: dict) -> str:
    """Refer back to a key finding instead of repeating its implication."""
    for n, k in enumerate(syn["key_findings"], 1):
        if k["id"] == check["id"]:
            return "see key finding %d (%s)." % (n, k["title"].lower())
    return check["implication"]


def _similar(a: str, b: str) -> bool:
    wa, wb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    return bool(wa) and len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.7


def _num(x) -> str:
    return "{:,}".format(x) if isinstance(x, int) else str(x)


def _render(model: dict) -> (str, Cite):
    b, syn, econ = model["brief"], model["synthesis"], model["economics"]
    cite = Cite(model["sources"])
    v = syn["verdict"]
    geo = b.get("geography") or "the launch area"
    L: List[str] = ["# %s" % model["title"], ""]
    L.append("**The founder's idea (verbatim):** %s" % b["founder_statement"])
    L.append("")
    L.append("Read as: *%s* for **%s**%s; stage: **%s**; paying customer: **%s**." % (
        b["product"], b["target_customer"], (" in " + b["geography"]) if b.get("geography") else "", b["stage"],
        "users" if b["payer"] == "consumer" else "businesses"))
    for flag in b.get("fidelity_flags") or []:
        L.append("> Interpretation check: %s." % flag)
    if b.get("exclusions"):
        L.append("> Out of scope (founder): %s." % "; ".join(b["exclusions"]))
    if model.get("evidence_mode") == "saved_extractive":
        L.append("> Evidence mode: regenerated from saved sources without new searches or model calls. Quoted "
                 "passages are located evidence, not analysed findings.")
    L.append("")

    # 1
    L += ["## 1. Recommendation: %s" % VERDICT_LABEL[v["verdict"]], "",
          "**Why:** %s." % (v["reason"][:1].upper() + v["reason"][1:]), ""]
    L.append("**Key findings and what they mean**")
    L.append("")
    for n, c in enumerate(syn["key_findings"], 1):
        L.append("%d. **%s.** %s *Implication:* %s" % (n, c["title"], c["finding"], c["implication"]))
    L += ["", "- **Proceed if** %s." % v["proceed_if"], "- **Modify if** %s." % v["modify_if"],
          "- **Stop if** %s." % v["stop_if"], ""]

    # 2
    H = syn["hypotheses"]
    L += ["## 2. Customer problem and evidence", ""]
    L.append("*Is the problem real and frequent?* Evidence level: **%s**." % LEVEL_WORD[H.get("H-D1", {}).get(
        "level", "none")])
    L += ["- " + x for x in _q_lines(model, "Q-C1", cite)]
    L.append("")
    L.append("*How do they solve it today?*")
    L += ["- " + x for x in _q_lines(model, "Q-C2", cite)]
    L.append("")
    L.append("*Would they pay?* Evidence level: **%s**." % LEVEL_WORD[H.get("H-V1", {}).get("level", "none")])
    L += ["- " + x for x in _q_lines(model, "Q-W1", cite, 1)]
    moved = [n for q in model["questions"].values() for n in q.get("validation_notes", []) if "existing product" in n]
    if moved:
        L.append("- %d passage(s) described an existing product's users rather than %s; they were moved to the "
                 "competition analysis." % (len(moved), b["target_customer"]))
    L.append("")

    # 3
    rows = [r for r in model["competition"]["rows"] if r["verified"] and r["relation"] in ("direct", "substitute")]
    L += ["## 3. Competitive landscape and differentiation", ""]
    if rows:
        for r in rows[:5]:
            L.append("- **%s** (%s); price: %s." % (r["name"], r["relation"], r.get("price_short") or "not stated"))
    else:
        L.append("- No direct competitor or substitute was verified in the evidence.")
    adj = [r["name"] for r in model["competition"]["rows"] if r["verified"] and r["relation"] == "adjacent"]
    if adj:
        L.append("- Adjacent (different job, same users): %s." % ", ".join(adj[:5]))
    L.append("")
    L.append("*What users of the alternatives dislike:*")
    L += ["- " + x for x in _q_lines(model, "Q-K2", cite)] if "Q-K2" in model["questions"] else [
        "- Not researched (no verified competitor)."]
    for c in syn["checks"]:
        if c["id"] in ("X2", "X3"):
            L.append("- **So what:** " + _see(c, syn))
    L.append("")

    # 4
    L += ["## 4. Market opportunity and distribution", ""]
    mc = econ.get("market_check")
    if mc:
        L.append("- Counted in %s: about %s %s%s." % (geo, _num(int(mc["count"]["value"])), mc["count"]["unit"],
                                                     cite([mc["count"]["source_id"]])))
        if mc.get("share_needed") is not None:
            L.append("- Break-even in the base scenario needs %s%% of that count as active users." % _num(round(
                100 * mc["share_needed"], 1)))
    else:
        L.append("- Reachable customers in %s: **not found in the evidence**. Bottom-up method instead: count the %ss "
                 "in %s, multiply by their members and by the share who %s; compare with the %s active users the "
                 "base scenario needs (experiment below)." % (
                     geo, b.get("venue") or "venue", geo, b["customer_job"],
                     _num(econ["scenarios"][econ["base_scenario"]]["breakeven_active"] or 0)))
    L.append("")
    L.append("*Where to reach them first:*")
    L += ["- " + x for x in _q_lines(model, "Q-D1", cite)]
    for c in syn["checks"]:
        if c["id"] == "X4":
            L.append("- **Cold start:** " + _see(c, syn))
    L.append("")

    # 5
    L += ["## 5. Product feasibility and business economics", ""]
    L.append("*Feasibility:*")
    L += ["- " + x for x in _q_lines(model, "Q-F1", cite, 1)]
    if "Q-F2" in model["questions"]:
        L += ["- " + x for x in _q_lines(model, "Q-F2", cite, 1)]
    price = next(a for a in econ["assumptions"] if a["name"] == "price_monthly")
    L.append("")
    who = "user" if b["payer"] == "consumer" else "account"
    L.append("*Economics (deterministic; assumptions and sources in Appendix D):* price %s/month per paying %s "
             "(%s); contribution %s per paying %s per month after fees and variable costs." % (
                 money(price["value"]), who, price["basis"].replace("_", " "),
                 money(econ["unit"]["contribution_per_paying_month"]), who))
    L.append("")
    L.append("| Scenario | MVP cash | Monthly costs | %s | Funding to next milestone |" % (
        "Break-even paying / active users" if b["payer"] == "consumer" else "Break-even paying accounts"))
    L.append("|---|---|---|---|---|")
    for key, s in econ["scenarios"].items():
        be = _num(s["breakeven_paying"]) if s["breakeven_paying"] else "n/a"
        if b["payer"] == "consumer":
            be += " / " + (_num(s["breakeven_active"]) if s["breakeven_active"] else "n/a")
        L.append("| %s | %s | %s | %s | %s |" % (s["label"], money(s["mvp_cash"]), money(s["fixed_monthly"]), be,
                                                money(s["funding_to_milestone"])))
    L.append("")
    for chk in econ["checks"]:
        L.append("- %s" % chk)
    if not econ.get("projection"):
        L.append("- No multi-year projection is shown (%s)." % econ.get("projection_note", "inputs insufficient")
                 .replace("not produced: ", ""))
    L.append("")

    # 6
    L += ["## 6. Most consequential risks", ""]
    exp_by_h = {}
    for n, e in enumerate(syn["experiments"], 1):
        for h in [e["hypothesis_id"]] + list(e.get("also_tests") or []):
            exp_by_h.setdefault(h, n)
    L.append("| Risk | Evidence today | Reduced by |")
    L.append("|---|---|---|")
    for c in syn["checks"][:6]:
        if c["id"] == "X7" and econ["unit"]["contribution_per_paying_month"] > 0:
            continue
        test = next(("Experiment %d" % exp_by_h[h] for h in c["hypotheses"] if h in exp_by_h),
                    "bottom-up count (Section 4)" if "H-V2" in c["hypotheses"] else "design decision (Section 5)")
        L.append("| %s | %s | %s |" % (c["title"], LEVEL_WORD.get(c.get("evidence_level", "none"), "-"), test))
    L.append("")

    # 7
    L += ["## 7. Validation experiments and next steps", ""]
    for n, e in enumerate(syn["experiments"], 1):
        L.append("**Experiment %d - %s** (%s%s)" % (n, e["hypothesis"], e["hypothesis_id"], (
            "; also tests " + ", ".join(e["also_tests"])) if e.get("also_tests") else ""))
        L.append("")
        L.append("- Segment: %s" % e["segment"])
        L.append("- Method: %s" % e["method"])
        L.append("- Metric: %s; **threshold:** %s" % (e["metric"], e["threshold"]))
        L.append("- Cost and time: %s, %s" % (e["cost"], e["duration"]))
        L.append("- If it passes: %s. If it fails: %s." % (e["success"], e["failure"]))
        L.append("- Next step: %s" % e["next"])
        L.append("")
    base = econ["scenarios"][econ["base_scenario"]]
    L.append("**Next 30 days:** run Experiment 1 first; start Experiment 2 only if it passes; do not build beyond a "
             "clickable prototype or a manual pilot before both pass. Experiment budget: about %s (%s scenario)."
             % (money(base["experiment_budget"]), base["label"].lower()))
    return "\n".join(L), cite


def render_memo(model: dict) -> str:
    body, cite = _render(model)
    gate = gate_check(body, model)
    model.setdefault("publication", {})["memo_gate"] = gate
    tail = ["", "---", "", "**Sources cited** (full evidence log, calculations and validation results are in the "
                         "appendix)", ""] + cite.listing()
    if not gate["passed"]:
        tail += ["", "> Publication check: %d number(s) in this memo could not be traced to validated data: %s." % (
            len(gate["untraced"]), ", ".join(gate["untraced"][:8]))]
    if gate["contradictions"]:
        tail += ["", "> Consistency check: %s." % "; ".join(gate["contradictions"])]
    return body + "\n" + "\n".join(tail) + "\n"


def gate_check(body: str, model: dict) -> dict:
    text = re.sub(r"\[\[\d+\]\]\([^)]*\)", "", body)
    g = validators.publication_gate(text, report_v4.trusted_view(model))
    g["contradictions"] = synthesis.consistency(text, model["synthesis"], model["economics"])
    return g


def render_appendix(model: dict, v3_appendix: str = "") -> str:
    b, syn, econ = model["brief"], model["synthesis"], model["economics"]
    src = model["sources"]
    L = ["# Appendix: evidence, calculations and validation", ""]
    L += ["## A. Idea brief (research-planning agent)", ""]
    for k in ("founder_statement", "product", "target_customer", "problem", "customer_job", "geography", "stage",
              "payer", "business_model", "network_product", "venue", "category"):
        L.append("- %s: %s" % (k.replace("_", " "), b.get(k) if b.get(k) not in ("", None) else "-"))
    L.append("- interpretation flags: %s" % ("; ".join(b.get("fidelity_flags") or []) or "none"))
    L += ["", "## B. Assumptions map (most important first)", "",
          "| ID | Hypothesis | Importance | Evidence | Questions |", "|---|---|---|---|---|"]
    for h in b["hypotheses"]:
        lv = syn["hypotheses"].get(h["id"], {})
        L.append("| %s | %s | %d | %s (%d supporting, %d contradicting, %d neutral) | %s |" % (
            h["id"], h["statement"].replace("|", "/"), h["importance"], lv.get("level", "none"),
            lv.get("supporting", 0), lv.get("contradicting", 0), lv.get("neutral", 0), ", ".join(h["questions"])))
    L += ["", "## C. Research questions and findings", ""]
    for qid, q in model["questions"].items():
        L.append("### %s %s" % (qid, q["question"]))
        L.append("")
        L.append("- Status: %s; attempts: %s%s" % (STATUS_WORD.get(q["status"], q["status"]), q.get("attempt", 1),
                                                  ("; repair reason: " + q["repair_reason"]) if q.get(
                                                      "repair_reason") else ""))
        for qq in q.get("queries", [])[:8]:
            L.append("- Query (%s): %s%s" % (qq.get("origin", ""), qq.get("query", ""),
                                             (" -> %s results, %s relevant" % (qq.get("results"), qq.get("relevant")))
                                             if "results" in qq else (" (%s)" % qq["skipped"] if qq.get("skipped")
                                                                      else "")))
        L.append("- Evidence packet: %s" % (", ".join("%s (%s)" % (i, validators.host(src.get(i, {}).get("url", "")))
                                                       for i in q.get("packet", [])) or "none"))
        for f in q.get("findings") or []:
            val = f.get("validation") or {}
            L.append("- %s [%s | %s | %s | %s] %s - sources: %s; types: %s%s" % (
                f["id"], f.get("kind"), f.get("status"), f.get("role"), f.get("stance"), f["text"][:220],
                ", ".join(f.get("source_ids") or []) or "none", ", ".join(val.get("source_types", [])) or "-",
                ("; flags: " + "; ".join(val["flags"])) if val.get("flags") else ""))
        for n in q.get("validation_notes", []):
            L.append("- Note: %s" % n)
        if q.get("unknown"):
            L.append("- Unknown: %s" % q["unknown"])
        L.append("")
    L += ["## D. Economics: assumptions, calculations and sensitivity", "",
          "| Assumption | Value | Range | Basis | Uncertainty | Rationale | Sources |", "|---|---|---|---|---|---|---|"]
    for a in econ["assumptions"]:
        L.append("| %s | %s %s | %s to %s | %s | %s | %s | %s |" % (
            a["name"], a["value"], a["unit"], a["low"], a["high"], a["basis"], a["uncertainty"],
            a["rationale"].replace("|", "/"), ", ".join(a["sources"]) or "-"))
    L += ["", "Formulas: contribution per paying user = price x (1 - payment fee) - variable cost per active user / "
              "paying share; break-even paying users = monthly fixed costs / contribution; break-even active users = "
              "break-even paying users / paying share; funding to milestone = MVP cash + monthly costs x (MVP months "
              "+ %d) + experiment budget." % 6, ""]
    g = econ["sensitivity"]
    L.append("Sensitivity of break-even ACTIVE users (base scenario, monthly costs %s):" % money(g["fixed_monthly"]))
    L += ["", "| Paying share | " + " | ".join("price %s" % money(p) for p in g["prices"]) + " |",
          "|---|" + "---|" * len(g["prices"])]
    for r in g["rows"]:
        L.append("| %.0f%% | %s |" % (100 * r["paying_share"], " | ".join(_num(x) if x else "n/a"
                                                                          for x in r["breakeven_active"])))
    L.append("")
    if econ.get("projection"):
        p = econ["projection"]
        L.append("Five-year cohort projection (%s). Inputs: %s." % (
            "ILLUSTRATIVE - inputs are not evidence-based" if p.get("illustrative") else "evidence-based inputs",
            ", ".join("%s=%s" % kv for kv in p["inputs"].items())))
        L += ["", "| Year | Active | Paying | Revenue | Profit (last month) | Cumulative cash |", "|---|---|---|---|---|---|"]
        for r in p["rows"]:
            L.append("| %d | %s | %s | %s | %s | %s |" % (r["year"], _num(r["active_end"]), _num(r["paying_end"]),
                                                       money(r["revenue"]), money(r["operating_profit_last_month"]),
                                                       money(r["cumulative_cash"])))
        L.append("")
        L.append("LTV per paying user %s; CAC per paying user %s; LTV/CAC %s; first profitable month: %s." % (
            money(p["ltv_paying"]) if p["ltv_paying"] is not None else "n/a", money(p["cac_paying"]),
            p["ltv_cac"], p["breakeven_month"] or "not within 60 months"))
    else:
        L.append("Multi-year projection: %s." % econ.get("projection_note"))
    L += ["", "## E. Cross-section checks (decision synthesis)", ""]
    for c in syn["checks"]:
        L.append("- %s %s (weight %d; hypotheses %s; evidence %s): %s -> %s" % (
            c["id"], c["title"], c["weight"], ", ".join(c["hypotheses"]), c.get("evidence_level"), c["finding"],
            c["implication"]))
    pub = (model.get("publication") or {}).get("memo_gate")
    L += ["", "## F. Report checks", ""]
    if pub:
        L.append("- Numbers checked in the memo: %d; untraced: %s" % (pub["checked"], ", ".join(pub["untraced"]) or
                                                                   "none"))
        L.append("- Contradictions with computed results: %s" % ("; ".join(pub["contradictions"]) or "none"))
    L.append("- Evidence mode: %s" % model.get("evidence_mode"))
    L += ["", "## G. Method", "",
          "The research-planning agent restates the idea and builds an assumptions map (desirability, viability, "
          "feasibility; Strategyzer assumptions mapping). Each research question is answered from a small evidence "
          "packet (at most two items per website, preferred source types first) by one narrow extraction call; code "
          "validates every finding (support, source independence, geography, question fit). The synthesis rules, "
          "economics and experiments are deterministic. Frameworks: Y Combinator's idea-evaluation questions, "
          "Sequoia's business-plan outline, Strategyzer's assumptions mapping.", ""]
    if v3_appendix:
        L += ["---", "", "# Part 2: research-run evidence log (report-v3 appendix)", "",
              re.sub(r"^# ", "## ", v3_appendix, flags=re.M)]
    return "\n".join(L) + "\n"
