"""Render an Assessment as a markdown report. Numbers come from code, prose from the LLM."""
from __future__ import annotations

from typing import List

from .pipeline import Assessment

VERDICTS = {
    "go": "GO: evidence and economics support moving to a pilot",
    "validate_first": "VALIDATE FIRST: promising, but key assumptions are untested",
    "pivot": "PIVOT: the current framing looks weak, consider the white space below",
    "no_go": "NO-GO: evidence and economics do not support this",
    "incomplete": "INCOMPLETE: research did not finish, so no go/no-go conclusion is drawn",
}
STATUS_LABEL = {"supported": "SUPPORTED", "partially_supported": "PARTIAL", "unsupported": "UNSUPPORTED",
                "contradicted": "CONTRADICTED", "explicit_assumption": "ASSUMPTION"}
GRADE_MEANING = {"A": "strong, relevant sourcing", "B": "good sourcing with gaps",
                 "C": "thin or partly unresolved research, treat numbers as rough",
                 "D": "unreliable: major research problems unresolved"}


def money(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if x >= div:
            return "%s$%.1f%s" % (sign, x / div, unit)
    return "%s$%.0f" % (sign, x)


def _s(value) -> str:
    return str(value).strip() if value not in (None, "") else "n/a"


def _list(items) -> List[str]:
    return [str(i) for i in items] if isinstance(items, list) else []


def _cell(text) -> str:
    return _s(text).replace("|", "/").replace("\n", " ")


def _pos(v) -> bool:
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def _feas(to: dict, a) -> str:
    if to.get("feasibility_score") in (None, ""):
        return "n/a"
    if a.scorecard and not _list(to.get("key_components")):
        return "not rated (no components identified)"
    return "%s/5" % to.get("feasibility_score")


def _cites(ids) -> str:
    return " " + " ".join("[%s]" % i for i in ids) if ids else ""


def _findings(a: Assessment, role: str) -> List[str]:
    claims = [c for c in a.claims if c.get("section") == role]
    if claims:
        out = ["", "*Claims and support (status from code checks plus a fallible model check):*"]
        for c in claims:
            tag = STATUS_LABEL.get(c.get("status"), c.get("status", "?"))
            where = "" if c.get("field", "").startswith("findings") else " *(field %s)*" % c.get("field")
            line = "- **%s** %s%s%s" % (tag, c.get("text", ""), where, _cites(c.get("source_ids")))
            if c.get("explanation"):
                line += " — %s" % c["explanation"]
            if c.get("passage") and c.get("status") in ("supported", "partially_supported"):
                line += "\n  > \"%s\"" % c["passage"][:240].replace("\n", " ")
            out.append(line)
        return out
    res = a.results.get(role)
    out = []
    for f in (res.findings if res else []):
        tag = "FACT" if f.kind == "fact" else "ESTIMATE"
        if f.downgraded:
            tag += ", unverified: " + (f.note or "no citation")
        out.append("- **%s** %s%s" % (tag, f.claim, _cites(f.source_ids)))
    return out


def _scorecard(a: Assessment) -> List[str]:
    card = a.scorecard or {}
    if not card:
        return _evidence_quality_legacy(a)
    ex, q = card["execution"], card["research_quality"]
    out = ["**Research quality grade: %s** (%s)\n" % (a.grade, GRADE_MEANING.get(a.grade, ""))]
    out += ["- " + r for r in a.grade_reasons]
    out.append("\n| Dimension | Result |\n|---|---|")
    out.append("| Execution | %s%s |" % (ex["status"].upper(), (" — not completed: " + ", ".join(
        ex["sections_not_completed"] + ex["budget_exhausted_phases"])) if ex["status"] != "complete" else ""))
    sr = q["source_relevance"]
    out.append("| Cited sources relevant to the product category | %d of %d |" % (sr["relevant"], sr["cited"]))
    cl = q["claims"]
    out.append("| Claims supported / partial / unsupported / contradicted / assumptions | %d / %d / %d / %d / %d (of %d; "
               "%d model-checked) |" % (cl["supported"], cl["partially_supported"], cl["unsupported"],
                                        cl["contradicted"], cl["assumptions"], cl["total"], cl["model_checked"]))
    ci = q["competitor_identity"]
    out.append("| Competitors with identity evidence / unresolved / rejected as unrelated | %d / %d / %d |" % (
        ci["verified"], ci["unresolved"], ci["rejected_irrelevant"]))
    out.append("| Duplicate passages excluded from prompts | %d |" % q["duplicate_passages_excluded"])
    out.append("| Section completeness | %s |" % ", ".join("%s: %s" % kv for kv in q["section_completeness"].items()))
    u = q["unresolved_issues"]
    out.append("| Unresolved issues (high / medium / low) | %d / %d / %d |" % (u["high"], u["medium"], u["low"]))
    out.append("| Financial projection | %s |" % q["financial_mode"].replace("_", " "))
    return out


def _evidence_quality_legacy(a: Assessment) -> List[str]:
    findings = [f for r in a.results.values() for f in r.findings]
    facts = sum(f.kind == "fact" for f in findings)
    total = len(findings)
    pct = (100.0 * facts / total) if total else 0.0
    reasons = {}
    for f in findings:
        if f.downgraded:
            reasons[f.note] = reasons.get(f.note, 0) + 1
    out = ["**Evidence grade: %s** (%s)\n" % (a.grade, GRADE_MEANING.get(a.grade, ""))]
    out += ["- " + r for r in a.grade_reasons]
    out.append("- %d findings: **%d sourced facts** (%.0f%%), %d estimates" % (total, facts, pct, total - facts))
    for note, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        n_text = "claim" if n == 1 else "claims"
        out.append("- %d %s labelled fact were downgraded to estimates: %s" % (n, n_text, note))
    return out


def report_data(a: Assessment) -> dict:
    """The canonical validated report model for an assessment (shared by Markdown, UI and JSON)."""
    from . import report_model
    return a.to_dict()["report"]


def render_markdown(a: Assessment) -> str:
    """Main report: the founder decision memo (report-v4 for the question design, report-v3 otherwise)."""
    from .render import render
    d = a.to_dict()
    return render(d["report"], d)[0]


def render_appendix(a: Assessment) -> str:
    """Evidence and methodology appendix (matching the memo's schema)."""
    from .render import render
    d = a.to_dict()
    return render(d["report"], d)[1]


def render_legacy_markdown(a: Assessment) -> str:
    """The pre-v3 single long report, kept for comparison only."""
    syn, r, p, ue = a.synthesis, a.results, a.projection, a.unit_economics
    L: List[str] = []
    add = L.append
    add("# Startup Assessment: %s" % a.plan.get("idea_summary", a.idea))
    add("*Generated %s by AI Startup Co-Founder. Preliminary desk research: it does not replace talking to customers.*\n" % a.created)
    if a.status != "complete":
        add("> **PARTIAL RESULT.** Research did not complete within its budget. Sections marked incomplete were not "
            "researched; no conclusion is drawn from missing evidence.\n")
    for w in a.warnings:
        add("> **Warning:** %s" % w)
    if a.warnings:
        add("")

    tech = r.get("technical")
    to = tech.output if tech else {}
    add("## At a glance")
    add("| Verdict | Research quality | Feasibility | LTV / CAC | Operating break-even | Peak funding need | Year-5 revenue |")
    add("|---|---|---|---|---|---|---|")
    add("| %s | %s | %s | %s | %s | %s | %s |\n" % (
        a.verdict.replace("_", " ").upper(), a.grade, _feas(to, a),
        "%.1f" % ue["ltv_cac"] if ue.get("ltv_cac") is not None else "n/a",
        "year %d" % p.breakeven_year if p.breakeven_year else "beyond year 5",
        money(p.peak_funding_need), money(p.table.iloc[-1]["revenue"])))
    if a.fin_mode != "evidence_backed":
        add("*Financial figures are an ILLUSTRATIVE scenario, not an evidence-backed forecast (see Financial inputs).*\n")

    add("## Verdict")
    add("**%s**\n" % VERDICTS.get(a.verdict, "No verdict produced"))
    if a.verdict_note:
        add("> %s\n" % a.verdict_note)
    add(_s(syn.get("verdict_rationale")) + "\n")
    add("## Executive summary")
    add(_s(syn.get("executive_summary")) + "\n")

    scope = syn.get("scope") or {}
    add("## Idea scope")
    add("- **Target customer:** %s" % _s(scope.get("target_customer")))
    add("- **MVP features:** %s" % ("; ".join(_list(scope.get("mvp_features"))) or "n/a"))
    add("- **Out of scope for now:** %s" % ("; ".join(_list(scope.get("out_of_scope"))) or "n/a"))
    add("- **Success looks like:** %s\n" % _s(scope.get("success_definition")))

    cust = r.get("customer")
    add("## Potential customers")
    add(_s(cust.output.get("summary") if cust else None) + "\n")
    for seg in (cust.output.get("segments", []) if cust else [])[:4]:
        if isinstance(seg, dict):
            add("- **%s**: %s. Pain points: %s. Willingness to pay: %s. Size: %s." % (
                _s(seg.get("name")), _s(seg.get("description")).rstrip("."),
                "; ".join(_list(seg.get("pain_points"))) or "n/a",
                _s(seg.get("willingness_to_pay")), _s(seg.get("size_estimate"))))
    L += _findings(a, "customer")
    add("")

    comp = r.get("competitor")
    add("## Competitive landscape (top 3)")
    add(_s(comp.output.get("summary") if comp else None) + "\n")
    allc = [c for c in (comp.output.get("competitors", []) if comp else []) if isinstance(c, dict)]
    comps = [c for c in allc if c.get("verified")][:3] if a.scorecard else allc[:3]
    if comps:
        add("| Competitor | Relation | Official domain | What they do | Pricing | Strengths | Weaknesses | Identity evidence |")
        add("|---|---|---|---|---|---|---|---|")
        for c in comps:
            name = _cell(c.get("name"))
            if c.get("url"):
                name = "[%s](%s)" % (name, c["url"])
            seen = ("confirmed" + _cites(c.get("identity_source_ids"))) if c.get("verified") else "NOT confirmed"
            add("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                name, _cell(c.get("relation", "?")), _cell(c.get("official_domain") or "unknown"),
                _cell(c.get("description")), _cell(c.get("pricing")),
                _cell("; ".join(_list(c.get("strengths"))) or None), _cell("; ".join(_list(c.get("weaknesses"))) or None),
                seen))
    else:
        add("*No competitor could be confirmed with evidence that it serves this product category.*")
    unresolved = [c for c in allc if not c.get("verified")] if a.scorecard else []
    if unresolved:
        add("\n**Unresolved identity** (not counted): " + "; ".join(
            "%s (%s)" % (c.get("name"), c.get("identity_note") or "insufficient evidence") for c in unresolved))
    rejected = comp.output.get("rejected", []) if comp else []
    if rejected:
        add("\n**Rejected as unrelated** (same name, different business): " + "; ".join(
            "%s%s" % (c.get("name"), " — " + str(c.get("description"))[:90] if c.get("description") else "")
            for c in rejected))
    add("\n**White space:** %s\n" % _s(comp.output.get("white_space") if comp else None))
    L += _findings(a, "competitor")
    add("")

    mkt = r.get("market")
    add("## Market")
    add(_s(mkt.output.get("summary") if mkt else None) + "\n")
    tss = (mkt.output.get("tam_sam_som") if mkt else None) or {}
    add("| TAM | SAM | SOM |\n|---|---|---|")
    add("| %s | %s | %s |" % tuple(money(tss.get(k)) if _pos(tss.get(k)) else "unknown"
                                  for k in ("tam_usd", "sam_usd", "som_usd")))
    add("\n*Method:* %s\n" % _s(tss.get("method")))
    for key, title in (("trends", "Trends"), ("headwinds", "Headwinds")):
        items = _list(mkt.output.get(key)) if mkt else []
        if items:
            add("**%s:** %s\n" % (title, "; ".join(items)))
    L += _findings(a, "market")
    add("")

    add("## Technical feasibility")
    add(_s(to.get("summary")) + "\n")
    add("- **Feasibility:** %s" % _feas(to, a))
    add("- **Key components:** %s" % ("; ".join(_list(to.get("key_components"))) or "n/a"))
    add("- **Build vs buy:** %s" % _s(to.get("build_vs_buy")))
    if _list(to.get("key_components")):
        add("- **MVP:** ~%s months with ~%s people" % (_s(to.get("mvp_time_months")), _s(to.get("mvp_team_size"))))
    else:
        add("- **MVP:** not estimated (no components identified)")
    add("- **Main risks:** %s\n" % ("; ".join(_list(to.get("main_risks"))) or "n/a"))
    L += _findings(a, "technical")
    add("")

    for role in a.extra_roles:
        res = r.get(role)
        if not res:
            continue
        add("## Additional research: %s" % role.replace("_", " ").title())
        add(_s(res.output.get("summary")) + "\n")
        for key, title in (("key_points", "Key points"), ("implications_for_founder", "What it means for you")):
            items = _list(res.output.get(key))
            if items:
                add("**%s:** %s\n" % (title, "; ".join(items)))
        L += _findings(a, role)
        add("")

    add("## Organizational structure")
    add("| Role | Headcount | Hired in year | Salary each |\n|---|---|---|---|")
    for m in sorted(p.assumptions["team"], key=lambda m: m["start_year"]):
        add("| %s | %d | %d | %s |" % (_cell(m["role"]), m["count"], m["start_year"], money(m["annual_salary"])))
    add("")

    add("## Financial projection (%s, 5 years, base case)" % (
        "evidence-backed estimates" if a.fin_mode == "evidence_backed" else "ILLUSTRATIVE scenario, not a forecast"))
    fin = r.get("financial")
    if a.fin_inputs:
        add("### Financial inputs and their support\n")
        add("| Input | Value | Unit | Basis | Status | Price evidence type | Sources | Why / uncertainty |")
        add("|---|---|---|---|---|---|---|---|")
        for i in a.fin_inputs:
            add("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                i["name"], "{:,.3g}".format(i["value"]), _cell(i["unit"]), i["basis"], i["status"].replace("_", " "),
                (i.get("price_category") or "-").replace("_", " "), " ".join(i.get("source_ids") or []) or "-",
                _cell(" ".join(filter(None, [i.get("reason"), i.get("uncertainty")])) or "-")))
        add("")
    add(_s(fin.output.get("rationale") if fin else None) + "\n")
    add("**Startup costs:** " + ", ".join("%s %s" % (c["item"], money(c["amount"])) for c in p.assumptions["startup_costs"])
        + " = **%s total**\n" % money(p.startup_total))
    a_ = p.assumptions
    add("**Key assumptions:** price %s/customer/month, %s new customers in year 1 growing %.0f%%/yr, "
        "%.0f%% annual churn, CAC %s, COGS %.0f%% of revenue.\n" % (
            money(a_["arpu_monthly"]), "{:,.0f}".format(a_["year1_new_customers"]), a_["growth_rate"] * 100,
            a_["annual_churn"] * 100, money(a_["cac"]), a_["cogs_pct"] * 100))
    add("| Year | Customers | Revenue | Costs | Operating profit | Cumulative cash |\n|---|---|---|---|---|---|")
    for _, row in p.table.iterrows():
        costs = row["cogs"] + row["marketing"] + row["payroll"] + row["other_opex"]
        add("| %d | %s | %s | %s | %s | %s |" % (
            row["year"], "{:,.0f}".format(row["customers_end"]), money(row["revenue"]), money(costs),
            money(row["operating_profit"]), money(row["cumulative_cash"])))
    add("")
    add("- **Operating break-even:** %s" % ("year %d" % p.breakeven_year if p.breakeven_year else "not within 5 years"))
    add("- **Cash payback:** %s" % ("year %d" % p.payback_year if p.payback_year else "not within 5 years"))
    add("- **Peak funding need:** %s\n" % money(p.peak_funding_need))

    add("### Unit economics")
    add("- **Gross profit per customer:** %s/month (dollars); **gross margin** %.0f%% of revenue; expected lifetime "
        "%.0f months" % (money(ue.get("gross_margin_monthly")), 100 * (1 - p.assumptions["cogs_pct"]),
                         ue.get("lifetime_months", 0)))
    add("- **Lifetime value (LTV):** %s vs **CAC** %s, LTV/CAC = %s" % (
        money(ue.get("ltv")), money(ue.get("cac")),
        "%.1f" % ue["ltv_cac"] if ue.get("ltv_cac") is not None else "n/a"))
    pb = ue.get("cac_payback_months")
    add("- **CAC payback:** %s\n" % ("%.1f months" % pb if pb is not None else "never (no gross margin)"))

    if a.scenarios:
        add("### Scenarios")
        add("| Scenario | Year-5 customers | Year-5 revenue | Year-5 operating profit | Break-even | Peak funding |\n|---|---|---|---|---|---|")
        for name, sc in a.scenarios.items():
            last = sc.table.iloc[-1]
            add("| %s | %s | %s | %s | %s | %s |" % (
                name.title(), "{:,.0f}".format(last["customers_end"]), money(last["revenue"]), money(last["operating_profit"]),
                "year %d" % sc.breakeven_year if sc.breakeven_year else "none", money(sc.peak_funding_need)))
        add("\n*Pessimistic = fewer customers, slower growth, higher churn and CAC, lower price. Optimistic is the reverse."
            "%s*\n" % (" Wtp_anchored = base case with the price set to the highest willingness to pay found by "
                       "customer research." if "wtp_anchored" in a.scenarios else ""))

    if a.sensitivity:
        add("### What matters most (sensitivity)")
        add("Change in year-5 operating profit if one assumption is 20% lower or higher:\n")
        add("| Assumption | 20% lower | 20% higher |\n|---|---|---|")
        for row in a.sensitivity:
            add("| %s | %s | %s |" % (row["assumption"], money(row["low"]), money(row["high"])))
        add("")

    if a.flags:
        add("### Sanity checks")
        for flag in a.flags:
            add("- %s" % flag)
        add("")
    L += _findings(a, "financial")
    add("")

    add("## Risks")
    for risk in syn.get("risks", []) if isinstance(syn.get("risks"), list) else []:
        if isinstance(risk, dict):
            add("- **[%s]** %s. *Mitigation:* %s" % (_s(risk.get("severity")).upper(), _s(risk.get("risk")).rstrip("."),
                                                     _s(risk.get("mitigation"))))
    add("")
    add("## Recommended validation steps")
    steps = syn.get("validation_steps", []) if isinstance(syn.get("validation_steps"), list) else []
    for i, s in enumerate(steps, 1):
        if isinstance(s, dict):
            add("%d. **Assumption:** %s\n   - Experiment: %s\n   - Success metric: %s\n   - Timeframe: %s" % (
                i, _s(s.get("assumption")), _s(s.get("experiment")), _s(s.get("success_metric")), _s(s.get("timeframe"))))
    add("")
    add("## Future outlook")
    add(_s(syn.get("future_outlook")) + "\n")

    add("## Quality review")
    if a.review_log:
        add("Each retry targets specific issues; the same checks are re-run afterwards and the better answer is kept.\n")
        for e in a.review_log:
            if e["agent"] == "-":
                add("- Round %d: %s" % (e["round"], e["issue"]))
            elif "outcome" in e:
                add("- Round %d, **%s** (%s): %s → **%s** (issue score %s → %s, kept %s answer%s%s)" % (
                    e["round"], e["agent"], e["origin"], e["issue"][:220], e["outcome"].replace("_", " "),
                    e.get("score_before"), e.get("score_after"), e.get("kept"),
                    "; resolved " + ", ".join(e["resolved"]) if e.get("resolved") else "",
                    "; still open " + ", ".join(e["unresolved"]) if e.get("unresolved") else ""))
            else:
                result = "improved" if e["improved"] else "redo failed, kept original"
                add("- Round %d, **%s** (%s check): %s → %s" % (e["round"], e["agent"], e["origin"], e["issue"], result))
    else:
        add("Review loop disabled.")
    unresolved = [i for i in a.issues if i.get("status") in ("unresolved", "open")]
    if unresolved:
        add("\n**Unresolved issues** (reported, not hidden):\n")
        order = {"high": 0, "medium": 1, "low": 2}
        for i in sorted(unresolved, key=lambda i: order.get(i["severity"], 3)):
            add("- [%s] `%s` %s (attempts: %d)" % (i["severity"].upper(), i["id"], i["message"], i.get("attempts", 0)))
    if a.publication_notes:
        add("\n**Final review** (memo checked against computed numbers before publishing):\n")
        for n in a.publication_notes:
            add("- Removed or flagged: %s" % n)
    add("")
    add("## Evidence quality")
    L += _scorecard(a)
    add("\n## Sources")
    cited = {i for c in a.claims for i in c.get("source_ids", [])}
    for res in a.results.values():
        for c in res.output.get("competitors", []) if isinstance(res.output, dict) else []:
            cited |= set(c.get("identity_source_ids") or []) if isinstance(c, dict) else set()
    shown = [s for s in a.sources if s["id"] in cited] if cited else a.sources
    if cited:
        add("*Sources cited by claims or identity checks (%d of %d collected; all are in the JSON file with relevance "
            "scores).*\n" % (len(shown), len(a.sources)))
    for s in shown:
        rel = (s.get("relevance") or {}).get("label")
        add("- **[%s]** [%s](%s)%s" % (s["id"], s["title"].replace("[", "(").replace("]", ")"), s["url"],
                                      " *(%s)*" % rel if rel and rel != "relevant" else ""))
    if not a.sources:
        add("- none collected")
    return "\n".join(L) + "\n"
