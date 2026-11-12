"""Render the canonical report model (report_model.build) as two Markdown documents:

* the founder decision memo (main report): decisions, implications, limitations next to the conclusions they affect,
  1-3 readable citations per claim, no raw audit output;
* the evidence and methodology appendix: every source, claim check, assumption, calculation, issue, retry and budget.

Tables stay at five columns or fewer; long text is shortened at sentence boundaries; missing values are written as
plain words ("not established"), never as null or an empty table.
"""
from __future__ import annotations

from typing import List

from .report_model import money, short

VERDICT_LABEL = {"go": "Go to a pilot", "validate_first": "Validate before building", "pivot": "Rework the idea",
                 "no_go": "Do not pursue", "incomplete": "No decision: research incomplete"}
ADEQUACY = {"adequate": "adequate for this decision", "partial": "partial: some conclusions rest on assumptions",
            "insufficient": "insufficient: several critical questions are open"}


def _links(cites) -> str:
    """Readable links; a second link to the same site is numbered instead of repeating the domain."""
    seen, out = {}, []
    for c in cites or []:
        n = seen.get(c["label"], 0) + 1
        seen[c["label"]] = n
        out.append("[%s](%s)" % (c["label"] if n == 1 else str(n), c["url"]))
    return " ".join(out)


def _cites(cites) -> str:
    return (" " + _links(cites)) if cites else ""


def _cell(text, limit=110) -> str:
    return short(text, limit).replace("|", "/").replace("\n", " ") or "not stated"


def _unknowns_for(model, keys, limit: int = 3) -> List[str]:
    """The most important open questions for a section (the full list is in the appendix)."""
    picked = sorted([u for u in model["unknowns"] if u["key"] in keys], key=lambda u: u["priority"])
    out = ["- **Open: %s.** %s Next: %s *(%s)*" % (u["what"], u["why"], u["next_action"], u["action_type"])
           for u in picked[:limit]]
    if len(picked) > limit:
        out.append("- *%d more open question(s) for this section are listed in the appendix.*" % (len(picked) - limit))
    return out


def render_memo(model: dict) -> str:
    """Founder decision memo. A publication gate then checks that every printed number traces to the model; if not,
    a visible warning is added at the top (the memo is never silently published with untraced numbers)."""
    from .validators import publication_gate
    text = _render_memo(model)
    gate = publication_gate(text, model)
    model.setdefault("validation", {})["publication_gate"] = gate
    if not gate["passed"]:
        lines = text.split("\n")
        lines.insert(2, "> **Publication check failed:** these numbers could not be traced to the validated data: %s. "
                        "Treat them as unverified.\n" % ", ".join(gate["untraced"][:8]))
        text = "\n".join(lines)
    return text


def _render_memo(model: dict) -> str:
    L: List[str] = []
    add = L.append
    st = model["status"]
    add("# %s" % model["title"])
    add("")
    add("**Idea:** %s" % (model["idea_summary"] or model["idea"]))
    add("")
    meta = "Generated %s" % model["generated"]
    if model.get("regenerated_from_saved_data"):
        meta += (" by re-rendering the saved run of %s with current validation rules. **No new research was done**; "
                 "corrections are listed in the appendix." % model["source_run"].get("created"))
    add("*%s. Desk research only; it does not replace talking to customers.*" % meta.rstrip("."))
    add("")
    vs = (model.get("validation") or {}).get("sources") or {}
    indep = ("%.0f%% of citations" % (100 * (1 - vs["vendor_share"]))) if vs.get("citations") else "not measured"
    add("| Run status | Evidence adequacy | Independent of vendors | Critical open questions |")
    add("|---|---|---|---|")
    add("| %s | %s | %s | %d |" % ("finished" if st["execution"] == "complete" else "INCOMPLETE",
                                   ADEQUACY.get(st["evidence_adequacy"], st["evidence_adequacy"]), indep,
                                   len(st["critical_unknowns"])))
    add("")
    if st["execution"] != "complete":
        add("> **INCOMPLETE ASSESSMENT.** The research did not finish. Conclusions that depend on missing sections are "
            "withheld.")
        add("")
    for w in st["withheld"]:
        add("> **Withheld:** %s." % w)
    if st["withheld"]:
        add("")

    # 1 decision
    dec = model["decision"]
    add("## 1. Decision and rationale")
    add("")
    add("**%s.** %s" % (VERDICT_LABEL.get(dec["verdict"], dec["verdict"]), dec["recommendation"]))
    add("")
    if dec["reasons"]:
        add("**Why:**")
        L.extend("- %s" % r for r in dec["reasons"])
        add("")
    if dec["uncertainties"]:
        add("**Most important uncertainties:** " + "; ".join(dec["uncertainties"]) + ".")
        add("")
    if dec["would_change"]:
        add("**What would change this:**")
        L.extend("- %s" % w for w in dec["would_change"])
        add("")

    # 2 customer
    c = model["customer"]
    add("## 2. Customer and problem")
    add("")
    add("- **Initial segment:** %s" % (c["target"] or "not established (see open question below)"))
    add("- **Problem:** %s" % (short(c["problem"], 220) or "not established"))
    add("- **How often:** %s" % (c["frequency"] or "unknown"))
    add("- **Current workaround:** %s" % ("; ".join(c["workarounds"]) if c["workarounds"] else "not established"))
    add("- **Willingness to pay:** %s" % (c["wtp"] or "unknown (competitor prices are not evidence of it)"))
    add("- **Reach:** %s" % ("; ".join(c["channels"]) if c["channels"] else "not established"))
    add("")
    if c["evidence"]:
        add("*Observed evidence:*")
        for e in c["evidence"]:
            labels = ["vendor's own claim"] if e["type"] == "source_reported" else []
            if e["status"] == "partially_supported":
                labels.append("partly supported")
            labels += [f.split(":")[0] for f in e.get("flags", [])]
            tag = " *(%s)*" % "; ".join(labels) if labels else ""
            add("- %s%s%s" % (short(e["text"], 200), tag, _cites(e["cites"])))
        add("")
    L.extend(_unknowns_for(model, ("segment", "wtp", "frequency", "workaround", "channel")))
    add("")
    add("**Implication:** the target customer and their willingness to pay are %s; the first tests should establish "
        "them before any build." % ("still hypotheses" if not (c["target"] and c["wtp"]) else "partly evidenced"))
    add("")

    # 3 competition
    comp = model["competition"]
    add("## 3. Competition and reason to switch")
    add("")
    main = [r for r in comp["rows"] if r["relation"] in ("direct", "substitute")]
    adj = [r for r in comp["rows"] if r["relation"] == "adjacent"]
    if main:
        add("| Alternative | Type | What it offers | Price | Evidence |")
        add("|---|---|---|---|---|")
        for r in main[:5]:
            ev = r.get("cites") or []
            add("| %s | %s | %s | %s | %s |" % (_cell(r["name"], 40), r["relation"], _cell(r.get("description"), 100),
                                               _cell(r.get("price_short"), 50),
                                               _links(ev) or "-"))
        add("")
    else:
        add("No alternative was confirmed with evidence that it serves the same need.")
        add("")
    if adj:
        add("*Adjacent (same customers, different need):* " + ", ".join(r["name"] for r in adj) + ".")
        add("")
    status = comp["differentiation_status"]
    add("**Differentiation:** %s *(%s)*" % (comp["differentiation"] or "not yet defined", "established by evidence"
                                            if status == "established" else "hypothesis, not established"))
    add("")
    L.extend(_unknowns_for(model, ("switch",)))
    add("")
    if main:
        add("**Implication:** the need is already served by %s; the product must show a concrete reason to switch, or "
            "the founder should consider building on or partnering with an existing option." % ", ".join(
                r["name"] for r in main[:3]))
        add("")

    # 4 market
    m = model["market"]
    add("## 4. Reachable market and launch approach")
    add("")
    add("**Launch market:** %s." % m["launch_market"].rstrip("."))
    add("")
    if m["summary"]:
        add(m["summary"])
        add("")
    if m["sizes"]:
        add("Market sizes: TAM %s, SAM %s, SOM %s (%s)." % (money(m["sizes"]["tam"]), money(m["sizes"]["sam"]),
                                                          money(m["sizes"]["som"]), short(m["sizes"]["method"], 120)))
        add("")
    add("Bottom-up estimate: *paying users = participants x share with the problem x share reached x paying share; "
        "revenue = paying users x monthly price x 12.*")
    add("")
    add("| Input | Meaning | Value | How to get it |")
    add("|---|---|---|---|")
    for r in m["formula_rows"]:
        add("| %s | %s | %s | %s |" % (r["input"], _cell(r["meaning"], 70), _cell(r["value"], 40), _cell(r["how"], 110)))
    add("")
    if m["density"]:
        add("**Matching density:** %s" % m["density"])
        add("")
    add("**Implication:** %s" % ("the local market cannot be sized from the saved evidence; national or global "
                                 "statistics do not show demand in the launch area. Collect the missing inputs first."
                                 if m["missing"] else "the inputs above support a first estimate; check them locally."))
    add("")

    # 5 MVP
    v = model["mvp"]
    add("## 5. MVP, delivery and material risks")
    add("")
    if v["journey"]:
        add("**Minimum user journey:** " + " -> ".join(v["journey"]))
        add("")
    if v["components"]:
        add("| Component | Responsibility | Approach |")
        add("|---|---|---|")
        for comp_ in v["components"][:8]:
            add("| %s | %s | %s |" % (_cell(comp_["name"], 40), _cell(comp_.get("responsibility") or "not stated", 90),
                                      comp_.get("approach") or "-"))
        add("")
        add("*Engineering proposals, not verified facts.*%s" % (" Effort: %s." % v["effort"] if v["effort"] else ""))
        add("")
    else:
        add("No usable architecture was produced (the saved run listed product names as components%s)." % (
            ": " + ", ".join(v["rejected_components"][:4]) if v["rejected_components"] else ""))
        add("")
    if v["risks"]:
        unval = any(r.get("unvalidated") for r in v["risks"])
        add("**Delivery risks%s:** " % (" (listed by the saved run, not analysed)" if unval else "") + "; ".join(
            r["risk"] + (" (control: %s)" % r["control"] if r["control"] else "") for r in v["risks"][:5]) + ".")
        add("")
    if v["safety"]:
        add("| Risk scenario | Proposed control | Limitation |")
        add("|---|---|---|")
        for s in v["safety"]:
            add("| %s | %s | %s |" % (_cell(s.get("scenario"), 90), _cell(s.get("control"), 80),
                                      _cell(s.get("limitation"), 80)))
        add("")
        add("*Controls are proposals unless marked as a legal requirement in the appendix. No matching product can "
            "guarantee a safe partner.*")
        add("")
    L.extend(_unknowns_for(model, ("arch", "safety")))
    add("")
    add("**Implication:** %s" % (
        "build effort and safety controls are not yet known; the first version should be a manual (concierge) test "
        "that needs no build." if not v["components"] else
        "the proposed scope is small enough to test; safety and privacy controls belong in the first version."))
    add("")

    # 6 economics
    e = model["economics"]
    add("## 6. Business model and economics")
    add("")
    add("- **Who pays:** %s" % e["payer"])
    if e["price_basis"]:
        add("- **Pricing basis:** %s" % short(e["price_basis"], 200))
    add("")
    add("**What the current scenario shows** (computed by code from the inputs in the appendix):")
    L.extend("- %s" % h for h in e["headlines"])
    add("")
    if e["targets"]:
        for t in e["targets"]:
            add("*Founder target (not a forecast):* \"%s\". The scenario shows %s." % (short(t["target"], 120),
                                                                                       t["scenario_shows"]))
        add("")
    if e["scenarios"]:
        add("| Scenario | Year-5 paying customers | Year-5 revenue | Year-5 operating result | Break-even |")
        add("|---|---|---|---|---|")
        for s in e["scenarios"]:
            add("| %s | %s | %s | %s | %s |" % (s["name"].title(), "{:,.0f}".format(s["customers"]), money(s["revenue"]),
                                               money(s["operating"]), "year %d" % s["breakeven"] if s["breakeven"]
                                               else "none in 5 years"))
        add("")
    if e["drivers"]:
        add("**Main cost drivers:** " + "; ".join(e["drivers"]) + ".")
        add("")
    val = model.get("validation") or {}
    def _fmt(name, value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return str(value)
        return ("%.0f%%" % (100 * v)) if name in ("annual_churn", "growth_rate", "cogs_pct", "paying_share_of_active") \
            else money(v) if name in ("arpu_monthly", "cac") else "%g" % v
    checks = ["%s of %s: %s" % (p["input"].replace("_", " ").replace("arpu monthly", "price per month"),
                                _fmt(p["input"], p["value"]), p["why"]) for p in val.get("plausibility", [])
              if p["severity"] == "warning"]
    checks += [c["detail"][:1].upper() + c["detail"][1:].rstrip(".") + "." for c in val.get("consistency", [])
               if c["result"] in ("inconsistent", "tension")]
    if checks:
        add("**Checks on these numbers** (plausibility ranges are heuristics, not benchmarks):")
        L.extend("- %s" % c for c in checks[:5])
        add("")
    if e["overlap"]:
        add("*Note:* startup costs include %s, which is also in payroll (counted twice in the saved scenario)."
            % ", ".join(e["overlap"]))
        add("")
    add("**Credibility:** %s" % (
        "inputs are evidence-backed." if e["credible"] else
        "this is an illustrative scenario, not a forecast; it is not credible enough for investment planning because "
        "%s %s assumed. Without salaries, the scenario's one-off and first-year acquisition costs total %s; the "
        "founder tests in section 7 need far less." % (", ".join(n.replace("_", " ") for n in e["assumed_inputs"][:4]),
                                                         "is" if len(e["assumed_inputs"]) == 1 else "are",
                                                         money(e["lean_cost"]))))
    add("")

    # 7 validation plan
    add("## 7. Prioritized validation plan")
    add("")
    add("Thresholds are proposed decision rules, not industry benchmarks.")
    add("")
    for i, vstep in enumerate([s for s in model["validation_plan"] if s["owner"] == "founder"], 1):
        add("%d. **%s** *(%s)*" % (i, vstep["hypothesis"], vstep["category"]))
        add("   - Test: %s" % vstep["test"])
        add("   - Measure: %s; %s; %s." % (vstep["metric"], vstep["threshold"], vstep["time_cost"]))
        add("   - If it passes: %s. If not: %s." % (vstep["if_pass"], vstep["if_fail"]))
    soft = [s for s in model["validation_plan"] if s["owner"] == "software"]
    if soft:
        add("")
        add("**Research the software can do next:** " + "; ".join(s["test"].rstrip(".") for s in soft) + ".")
    add("")
    add("---")
    add("*Sources, claim checks, assumptions, calculations, corrections and run history are in the evidence appendix.*")
    return "\n".join(L).replace("\n\n\n", "\n\n") + "\n"


def render_appendix(model: dict, d: dict) -> str:
    L: List[str] = []
    add = L.append
    add("# Evidence and methodology appendix")
    add("")
    add("For: %s. Report schema %s; source run %s (%s)." % (model["title"], model["schema"],
                                                           model["source_run"].get("created"),
                                                           model["source_run"].get("workflow")))
    add("")
    add("## A. Corrections applied to this report")
    add("")
    if model["corrections"]:
        add("Deterministic checks changed or removed the following before publishing:")
        add("")
        for c in model["corrections"]:
            line = "- **%s:** %s" % (c["section"], c["correction"])
            if c.get("before"):
                line += " — was: \"%s\"" % c["before"]
            add(line)
    else:
        add("None.")
    add("")
    add("## B. Open questions and next actions")
    add("")
    add("| Question | Why it matters | Not yet established | Next action | Who |")
    add("|---|---|---|---|---|")
    for u in model["unknowns"]:
        add("| %s | %s | %s | %s | %s |" % (_cell(u["what"], 90), _cell(u["why"], 130), _cell(u["not_established"], 100),
                                           _cell(u["next_action"], 120), u["action_type"]))
    add("")
    add("## C. Claims and support")
    add("")
    add("Status comes from a lexical screen by code plus a fallible model check (recorded separately in the JSON). "
        "Lexical matches alone are at most 'partially supported'. Type: external fact, source-reported (a vendor about "
        "itself), assumption or proposal.")
    add("")
    by_section = {}
    for c in model["claims"]:
        by_section.setdefault(c.get("section", "?"), []).append(c)
    for section, cl in by_section.items():
        add("### %s" % section.replace("_", " ").title())
        add("")
        add("| Claim | Status | Type | Sources | Note |")
        add("|---|---|---|---|---|")
        for c in cl:
            ids = c.get("source_ids") or []
            add("| %s | %s | %s | %s | %s |" % (_cell(c.get("text"), 130), c.get("status", "").replace("_", " "),
                                               c.get("claim_type", "").replace("_", " "),
                                               " ".join(ids[:3]) + (" +%d" % (len(ids) - 3) if len(ids) > 3 else ""),
                                               _cell(c.get("explanation"), 110)))
        add("")
    add("## D. Assumption register")
    add("")
    add("| Assumption | Value | Basis | Status | Reason |")
    add("|---|---|---|---|---|")
    for i in model["economics"]["inputs"]:
        add("| %s | %s %s | %s | %s | %s |" % (i["name"], "{:,.3g}".format(i["value"]), _cell(i.get("unit"), 30),
                                              i.get("basis"), i.get("status", "").replace("_", " "),
                                              _cell(i.get("reason") or "-", 100)))
    for r in model["market"]["formula_rows"]:
        add("| market: %s | %s | %s | %s | %s |" % (r["input"], _cell(r["value"], 40), "market input",
                                                  "missing" if r["value"] == "missing" else "stated",
                                                  _cell(r["how"], 90)))
    add("")
    add("## E. Financial calculations")
    add("")
    p = model["economics"]["projection"]
    a = p.get("assumptions", {})
    add("Price %s/month, %s new paying customers in year 1 growing %.0f%%/yr, churn %.0f%%/yr, CAC %s, cost of "
        "revenue %.0f%%." % (money(a.get("arpu_monthly")), "{:,.0f}".format(a.get("year1_new_customers", 0)),
                            100 * a.get("growth_rate", 0), 100 * a.get("annual_churn", 0), money(a.get("cac")),
                            100 * a.get("cogs_pct", 0)))
    add("")
    add("| Year | Paying customers | Revenue | Operating result | Cumulative cash |")
    add("|---|---|---|---|---|")
    for r in p.get("table", []):
        add("| %d | %s | %s | %s | %s |" % (r["year"], "{:,.0f}".format(r["customers_end"]), money(r["revenue"]),
                                           money(r["operating_profit"]), money(r["cumulative_cash"])))
    add("")
    ue = model["economics"]["unit_economics"]
    if ue:
        add("Unit economics: gross profit %s per customer per month (a dollar amount); gross margin %.0f%%; LTV %s; "
            "CAC %s; LTV/CAC %s." % (money(ue.get("gross_margin_monthly")), 100 * (1 - a.get("cogs_pct", 0)),
                                     money(ue.get("ltv")), money(ue.get("cac")),
                                     "%.1f" % ue["ltv_cac"] if ue.get("ltv_cac") is not None else "n/a"))
        add("")
    add("Team: " + "; ".join("%d %s from year %d at %s" % (m["count"], m["role"], m["start_year"], money(m["annual_salary"]))
                             for m in a.get("team", [])) + ". One-off startup costs: " + "; ".join(
        "%s %s" % (c["item"], money(c["amount"])) for c in a.get("startup_costs", [])) + ".")
    add("")
    if d.get("sensitivity"):
        add("| Assumption (±20%) | Year-5 result if lower | Year-5 result if higher |")
        add("|---|---|---|")
        for s in d["sensitivity"]:
            add("| %s | %s | %s |" % (s["assumption"], money(s["low"]), money(s["high"])))
        add("")
    add("## F. Issues and review history")
    add("")
    issues = d.get("issues") or []
    if issues:
        add("| Issue | Severity | Status | Action | Message |")
        add("|---|---|---|---|---|")
        for i in issues:
            add("| `%s` | %s | %s | %s | %s |" % (i["id"], i["severity"], i["status"], i.get("action", "research"),
                                                _cell(i["message"], 120)))
        add("")
    for e in d.get("review_log") or []:
        if e.get("agent") == "-":
            add("- Round %s: %s" % (e.get("round"), e.get("issue")))
        else:
            add("- Round %s, %s: %s -> %s (score %s -> %s, kept %s)" % (
                e.get("round"), e.get("agent"), short(e.get("issue"), 140), e.get("outcome", "?"),
                e.get("score_before"), e.get("score_after"), e.get("kept")))
    add("")
    add("## G. Research history and budgets")
    add("")
    for role, r in (d.get("research") or {}).items():
        if role == "run_limits" or not isinstance(r, dict) or not r:
            continue
        qs = r.get("queries") or []
        add("- **%s:** %d searches (%d with relevant results), %d pages read; stopped: %s%s" % (
            role, len(qs), sum(1 for q in qs if q.get("relevant")), len(r.get("fetched") or []), r.get("stopped") or "-",
            "; rejected actions: " + ", ".join(sorted({a.get("rejected_because") for a in r.get("actions", [])
                                                      if a.get("rejected_because")})) if any(
                a.get("rejected_because") for a in r.get("actions", [])) else ""))
    lim = (d.get("research") or {}).get("run_limits")
    if lim:
        add("- Run budget used: %s of %s searches, %s of %s page reads." % (lim["searches"], lim["max_searches"],
                                                                          lim["fetches"], lim["max_fetches"]))
    add("")
    add("## H. Sources")
    add("")
    cited = {i for c in model["claims"] for i in c.get("source_ids", [])}
    for r in model["competition"]["rows"]:
        cited |= set(r.get("identity_source_ids") or [])
    for s in d.get("sources", []):
        if s["id"] not in cited:
            continue
        rel = (s.get("relevance") or {}).get("label", "")
        add("- **%s** [%s](%s) *(%s)*: \"%s\"" % (s["id"], s.get("title", "").replace("[", "(").replace("]", ")")[:110],
                                                  s.get("url", ""), rel, short(s.get("snippet", ""), 200)))
    add("")
    add("%d sources were collected; %d are cited above. All are in the JSON with relevance scores." % (
        len(d.get("sources", [])), len(cited)))
    add("")
    val = model.get("validation") or {}
    add("## I. Validation layers")
    add("")
    gate = val.get("publication_gate") or __import__("startup_cofounder.validators", fromlist=["x"]).publication_gate(
        render_memo(model), model)
    vs = val.get("sources") or {}
    add("| Layer | Result |")
    add("|---|---|")
    add("| Source credibility | %s citations behind supported claims: %s |" % (
        vs.get("citations", 0), ", ".join("%s %d" % (k.replace("_", " "), v) for k, v in vs.get("by_type", {}).items())
        or "none"))
    add("| Independence | %.0f%% of those citations come from the companies' own sites or app stores |"
        % (100 * vs.get("vendor_share", 0)))
    add("| Claim flags | %d claims flagged (vendor-only, single website, low-credibility statistic, dated); %d "
        "downgraded |" % (val.get("claims_flagged", 0), val.get("claims_downgraded", 0)))
    add("| Plausibility | %d warning(s); ranges are heuristics, not benchmarks |" % sum(
        1 for p in val.get("plausibility", []) if p["severity"] == "warning"))
    add("| Consistency | %s |" % ("; ".join("%s: %s" % (c["check"], c["result"]) for c in val.get("consistency", []))
                                 or "none"))
    add("| Fact-checker reliability | %s |" % (val.get("verifier") or {}).get("status", "not measured"))
    add("| Publication gate | %s (%d numbers checked)%s |" % ("passed" if gate["passed"] else "FAILED", gate["checked"],
                                                             "; untraced: " + ", ".join(gate["untraced"][:6])
                                                             if not gate["passed"] else ""))
    add("")
    for p in val.get("plausibility", []):
        add("- Plausibility (%s): %s = %s — %s. %s" % (p["severity"], p["input"], p["value"], p["rule"], p["why"]))
    for c in val.get("consistency", []):
        add("- Consistency, %s: **%s** — %s." % (c["check"], c["result"], c["detail"]))
    add("")
    add("## J. Runtime and models")
    add("")
    ri = d.get("run_info") or {}
    add("- Workflow: %s; models: %s; elapsed: %s s." % (ri.get("workflow", d.get("workflow", "?")),
                                                         ri.get("models", {}), ri.get("elapsed_s", "?")))
    llm = ri.get("llm") or {}
    for k, v in llm.items():
        add("- %s model: %s calls, %s incomplete replies, largest prompt ~%s tokens, %s over context." % (
            k, v.get("calls"), v.get("incomplete"), v.get("max_prompt_tokens_est"), v.get("over_context")))
    cfg = ri.get("config") or {}
    if cfg:
        add("- Budget: %s min; context %s tokens; reply ceiling %s; review rounds %s." % (
            cfg.get("run_minutes"), cfg.get("context_tokens"), cfg.get("max_tokens"), cfg.get("critic_rounds")))
    return "\n".join(L) + "\n"
