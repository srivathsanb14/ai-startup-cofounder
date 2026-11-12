"""Decision synthesis: evaluate the findings TOGETHER, then decide what matters and what to do next.

Everything here is deterministic. Inputs are the structured outputs of the other agents (idea brief and its
assumptions map, validated question findings, verified competitors, stage-appropriate economics). Outputs:

* evidence level per hypothesis (none / weak / supported / contradicted), from validated findings only;
* cross-agent checks (rules X1-X8) that turn combinations of findings into implications, e.g. a free direct
  competitor + a paid model, a network product + an unknown local user base, unverified willingness to pay + a price;
* the three to five most consequential findings, ranked;
* a conditional verdict: proceed / validate_first / modify_concept / abandon_current_approach, with the conditions
  that would change it;
* two or three stage-appropriate experiments for the most important, least-evidenced hypotheses (Strategyzer-style
  assumptions mapping), each with hypothesis, segment, method, metric, threshold, cost, duration, meaning and next step.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

USABLE = ("supported", "partially_supported")
LEVEL_RANK = {"contradicted": 0, "none": 1, "mixed": 2, "weak": 2, "supported": 3}
VERDICTS = ("proceed", "validate_first", "modify_concept", "abandon_current_approach")


def _usable(q: dict) -> List[dict]:
    return [f for f in q.get("findings") or [] if f.get("role") == "finding" and f.get("status") in USABLE]


def hypothesis_levels(hypotheses: Sequence, questions: Dict[str, dict]) -> Dict[str, dict]:
    """Evidence level per hypothesis from its linked questions' validated findings."""
    out = {}
    for h in hypotheses:
        hid, qids = (h.id, h.questions) if hasattr(h, "id") else (h["id"], h["questions"])
        sup, con, located, ids, seen = 0, 0, 0, [], set()
        for qid in qids:
            q = questions.get(qid) or {}
            for f in _usable(q):
                key = (f.get("text", "").strip().lower(), tuple(f.get("source_ids") or []))
                if key in seen:
                    continue  # the same passage cited for two questions is one piece of evidence
                seen.add(key)
                independent = (f.get("validation") or {}).get("independent_domains", 0) >= 1
                if not independent:
                    continue  # a company describing itself is not evidence about customers, demand or payment
                if f.get("stance") == "contradicts":
                    con += 1
                elif f.get("stance") == "supports" and independent:
                    sup += 1
                else:
                    located += 1
                ids.append(f["id"])
        level = ("contradicted" if con and not sup else "mixed" if con and sup else
                 "supported" if sup else "weak" if located else "none")
        out[hid] = {"level": level, "supporting": sup, "contradicting": con, "neutral": located, "finding_ids": ids}
    return out


def _find(qs: Dict[str, dict], qid: str) -> List[dict]:
    return _usable(qs.get(qid) or {})


def cross_checks(brief, qs: Dict[str, dict], levels: Dict[str, dict], competitors: Sequence[dict],
                 econ: dict) -> List[dict]:
    """Findings that only appear when the agents' results are read together."""
    F: List[dict] = []
    base = econ["scenarios"][econ["base_scenario"]]
    price = next(a for a in econ["assumptions"] if a["name"] == "price_monthly")
    direct = [c for c in competitors if c.get("verified") and c.get("relation") == "direct"]
    subst = [c for c in competitors if c.get("verified") and c.get("relation") == "substitute"]
    free = [c["name"] for c in direct + subst if c.get("free")]

    def add(fid, title, finding, implication, weight, hyps, ids=()):
        F.append({"id": fid, "title": title, "finding": finding, "implication": implication, "weight": weight,
                  "hypotheses": list(hyps), "evidence": list(ids)})

    lv = lambda h: levels.get(h, {}).get("level", "none")  # noqa: E731
    # X1 problem evidence
    if lv("H-D1") == "contradicted":
        add("X1", "The problem may not be painful enough",
            "Evidence found contradicts the belief that %s experience this problem often." % brief.target_customer,
            "Without a painful, frequent problem, adoption and payment are unlikely; revisit the problem before "
            "building.", 5, ["H-D1"], levels["H-D1"]["finding_ids"])
    elif lv("H-D1") == "mixed":
        hd = levels["H-D1"]
        add("X1", "Evidence on the customer problem is mixed",
            "%d independent finding(s) support the problem and %d contradict it." % (hd["supporting"],
                                                                                    hd["contradicting"]),
            "The problem may matter only to part of the segment; interviews must find out which %s feel it and why "
            "the others do not." % brief.target_customer, 4, ["H-D1"], hd["finding_ids"])
    elif lv("H-D1") in ("none", "weak"):
        add("X1", "The customer problem is not yet evidenced",
            "No independent source shows how often %s run into '%s' or how much it matters to them." % (
                brief.target_customer, brief.problem),
            "This is the first thing to establish: it decides whether the rest of the analysis matters.", 4,
            ["H-D1"], levels.get("H-D1", {}).get("finding_ids", []))
    # X2 free alternatives vs monetization
    if free:
        add("X2", "Free alternatives set the price anchor",
            "%s %s free to use or download, at least in a basic version." % (", ".join(free[:3]),
                                                                           "is" if len(free) == 1 else "are"),
            ("A paid product must deliver something these free options do not; the realistic model is freemium or a "
             "different payer (e.g. venues or businesses), and the price used in the economics is unproven."
             if brief.payer == "consumer" else
             "A paid product must save owners more than the free option does; expect a free tier with paid features "
             "or a bundle with something they already pay for, and treat the price as unproven."), 4,
            ["H-V1", "H-D2"])
    if direct and lv("H-D2") in ("none", "weak", "contradicted"):
        add("X3", "Differentiation from direct competitors is unproven",
            "%s already %s the same need; no evidence shows why %s would switch." % (
                ", ".join(c["name"] for c in direct[:3]), "addresses" if len(direct) == 1 else "address",
                brief.target_customer),
            "The founder needs a specific reason to switch (a job the incumbents do badly) before investing in "
            "the build.", 4, ["H-D2"])
    # X4 network product / cold start
    if brief.network_product:
        need = base.get("breakeven_active")
        add("X4", "The product only works with local density (cold start)",
            "The idea depends on several %s using it at the same %s and time; usefulness for the first users depends "
            "on that." % (brief.target_customer, brief.venue or "place"),
            "Launch must concentrate on one %s or group and seed activity manually; distribution and the MVP scope "
            "must be designed for this, and break-even (%s active users in the base scenario) comes much later "
            "than usefulness." % (brief.venue or "community", "{:,}".format(need) if need else "unknown"), 5,
            ["H-D3"])
    # X5 willingness to pay vs price
    if lv("H-V1") in ("contradicted", "mixed"):
        add("X5", "Evidence suggests customers may not pay",
            "%d independent finding(s) indicate %s will not pay for this (or that free options are good enough)%s; "
            "the $%.2f/month in the economics is %s." % (
                levels["H-V1"]["contradicting"], "users" if brief.payer == "consumer" else "businesses",
                " and %d indicate they would" % levels["H-V1"]["supporting"] if levels["H-V1"]["supporting"] else "",
                price["value"], "what alternatives charge" if price["basis"] == "competitor_price" else
                "a placeholder" if price["basis"] != "evidence" else "from observed payments"),
            "Test payment before building; plan for a lower price, a different payer or a stronger reason to pay.",
            5, ["H-V1"], levels["H-V1"]["finding_ids"])
    elif price["basis"] != "evidence" or lv("H-V1") in ("none", "weak"):
        add("X5", "Willingness to pay is unverified",
            "No evidence shows %s paying for this; the $%.2f/month used in the economics is %s." % (
                "users" if brief.payer == "consumer" else "businesses", price["value"],
                "what alternatives charge" if price["basis"] == "competitor_price" else "a placeholder"),
            "Pricing must be treated as a hypothesis to test, not a plan; volumes below change with it.", 4,
            ["H-V1"], price.get("sources", []))
    # X6 market size vs break-even volume
    mc = econ.get("market_check")
    if not mc:
        add("X6", "Reachable market is unknown",
            "No count of %s in %s was found, so the base scenario's break-even of %s active users cannot be checked "
            "against the market." % (brief.target_customer, brief.geography or "the launch area",
                                     "{:,}".format(base["breakeven_active"]) if base.get("breakeven_active") else "?"),
            "Count the reachable customers bottom-up before assuming any customer base; the financials assume none.",
            3, ["H-V2"])
    elif mc.get("share_needed") and mc["share_needed"] > 0.2:
        add("X6", "Break-even needs an unrealistic share of the local market",
            "Break-even requires about %.0f%% of the counted local market as active users." % (100 * mc["share_needed"]),
            "Either the price/payer must change or the launch market must be larger.", 4, ["H-V2", "H-V1"])
    elif mc.get("share_needed") is not None:
        add("X6", "The local market is not the binding constraint",
            "About %s %s were counted in %s; break-even in the base scenario needs about %.1f%% of them." % (
                "{:,.0f}".format(mc["count"]["value"]), mc["count"]["unit"], brief.geography or "the launch area",
                100 * mc["share_needed"]),
            "Size is sufficient for a lean start; adoption and payment, not market size, decide the outcome.", 2,
            ["H-V2"], [mc["count"].get("finding", "")])
    # X7 economics
    if econ["unit"]["contribution_per_paying_month"] <= 0:
        add("X7", "Each paying user loses money",
            "After fees and variable costs the contribution per paying user is $%.2f/month." %
            econ["unit"]["contribution_per_paying_month"], "The model does not work at this price.", 5, ["H-V1"])
    else:
        add("X7", "Lean economics are small but reachable only with validated demand",
            "In the %s scenario, about %s paying %s (%s active) cover the $%s monthly costs; reaching the next "
            "milestone needs about $%s." % (base["label"].lower(), "{:,}".format(base["breakeven_paying"]),
                                            "users" if brief.payer == "consumer" else "accounts",
                                            "{:,}".format(base["breakeven_active"]), "{:,.0f}".format(
                                                base["fixed_monthly"]), "{:,.0f}".format(base["funding_to_milestone"])),
            "A salaried team multiplies the required volume (see the scenarios); stay lean until demand and "
            "payment are shown.", 2, ["H-V1", "H-V2"])
    # X8 feasibility / trust
    if brief.network_product and lv("H-F2") in ("none", "weak"):
        add("X8", "Trust and privacy need design, not just features",
            "Sharing schedules or locations with others creates safety and privacy risks.",
            "Default to friends-only visibility, block/report, and minimal location data in the MVP.", 2, ["H-F2"])
    for c in F:
        h = levels.get((c["hypotheses"] or [""])[0], {})
        c["evidence_level"] = h.get("level", "none")
    return sorted(F, key=lambda x: -x["weight"])


def verdict(brief, levels: Dict[str, dict], checks: Sequence[dict], econ: dict) -> dict:
    lv = lambda h: levels.get(h, {}).get("level", "none")  # noqa: E731
    ids = {c["id"] for c in checks}
    problem_bad = lv("H-D1") == "contradicted"
    if problem_bad and ("X2" in ids or "X3" in ids):
        v, why = "abandon_current_approach", ("the evidence contradicts the problem and alternatives already "
                                               "cover the need")
    elif lv("H-V1") == "contradicted" and levels["H-V1"]["contradicting"] >= 2 and ("X2" in ids or "X3" in ids):
        v, why = "modify_concept", ("independent evidence says these customers will not pay and alternatives "
                                    "already cover the need; change the payer, price or value proposition")
    elif "X7" in ids and econ["unit"]["contribution_per_paying_month"] <= 0 or (
            ((econ.get("market_check") or {}).get("share_needed") or 0) > 0.2):
        v, why = "modify_concept", "the economics cannot work as specified (price, payer or market must change)"
    elif all(lv(h) == "supported" for h in ("H-D1", "H-D2", "H-V1")) and econ.get("market_check"):
        v, why = "proceed", "problem, switching and payment are supported by independent evidence"
    else:
        v, why = "validate_first", "the decisive assumptions are not yet supported by independent evidence (%s)" % (
            ", ".join("%s: %s" % (h, lv(h)) for h in ("H-D1", "H-D2", "H-D3", "H-V1") if h in levels
                      and lv(h) != "supported"))
    if brief.payer == "business":
        cond = {"proceed_if": "owners confirm the problem, keep using the manual service, and commit to a paid pilot "
                              "at the tested price",
                "modify_if": "they use the service but will not pay (try a lower price, a different buyer or a "
                             "bundle) or only one type of business keeps using it",
                "stop_if": "few owners describe the problem or keep using the service even when it is done for them"}
    else:
        cond = {"proceed_if": "the first experiments meet their thresholds (people take part, come back, and show "
                              "willingness to pay)",
                "modify_if": "people use it but will not pay (try a different payer such as venues or sponsors) or "
                             "only a narrower segment comes back",
                "stop_if": "few people take part or come back in the pilot even when it is run by hand"}
    return dict({"verdict": v, "reason": why}, **cond)


def _templates(brief, econ: dict) -> Dict[str, dict]:
    cust = brief.target_customer
    geo = brief.geography or "one launch area"
    venue = brief.venue or ("business" if brief.payer == "business" else "community")
    pre = brief.stage in ("idea", "prototype")
    base = econ["scenarios"][econ["base_scenario"]]
    price = next(a for a in econ["assumptions"] if a["name"] == "price_monthly")["value"]
    b2b = brief.payer == "business"
    T = {
        "H-D1": dict(method="Problem interviews: 12-15 conversations with %s in %s about the LAST time they tried to %s "
                            "(past behaviour, not opinions about the idea)." % (
                                ("the people who do this job at " + cust) if b2b else cust, geo, brief.customer_job),
                     metric="share who describe the problem in the last month without prompting, and what they did",
                     threshold="at least 6 of 12 describe a recent, specific occurrence", cost="$0-150 (coffee/gift "
                     "cards)", duration="1-2 weeks",
                     success="the problem is real and frequent: design the pilot around the situations they described",
                     failure="the problem is rare or mild: change the problem or customer before building",
                     next="run the participation pilot with the people who described the problem"),
        "H-D2": (dict(method="Concierge service: for 5 %s in %s, deliver the result by hand each week for 3 weeks "
                             "(%s), with no software." % (cust, geo, brief.customer_job),
                      metric="how many keep using the service each week, and time saved per week as they report it",
                      threshold="at least 3 of 5 still use it in week 3 and report saving at least 1 hour a week",
                      cost="$0 (founder time)", duration="3 weeks",
                      success="the job is worth outsourcing: automate exactly what you did by hand",
                      failure="they return to their current way: the pain is too small or the switch too costly",
                      next="build the smallest tool that replaces your manual work") if b2b else
                 dict(method=("Concierge pilot: run the core loop by hand for one %s (sign-up form + group chat) for "
                              "3 weeks, no app." % venue) if pre else "Switching test with current users of "
                      "alternatives: offer the product side by side for 2 weeks.",
                      metric="share of sign-ups who take part at least once, and share still taking part in week 3",
                      threshold="at least 40% of sign-ups take part; at least 25% are active in week 3",
                      cost="$0-200", duration="3 weeks",
                      success="people prefer it to their current way: build only the parts used in the pilot",
                      failure="they keep their current way: the switch reason is too weak; find the job incumbents do "
                              "badly", next="build the smallest app version of what was used, or rethink the "
                                            "differentiation")),
        "H-D3": dict(method="Single-%s density pilot: recruit a seed group at one %s in %s and run sessions for 4 "
                            "weeks; count how often a user finds someone to join at a given time." % (venue, venue, geo),
                     metric="weekly active participants per %s, share of requests that find someone, and share of "
                            "participants who come back in week 3 (participation and return)" % venue,
                     threshold="at least 30 weekly active participants, at least 50% of requests find someone, and at "
                               "least 30% of week-1 participants return in week 3",
                     cost="$100-300 (posters, small incentives)", duration="4 weeks",
                     success="density is reachable at one location: expand %s by %s" % (venue, venue),
                     failure="activity stays too thin: narrow to existing groups or change the product to work for "
                             "one user alone", next="decide the second location only after week-4 numbers"),
        "H-V1": (dict(method="Paid pilot offer to 10 %s: a 30-day pilot at $%.0f/month, with a signed letter of intent."
                             % (cust, price), metric="number of businesses that sign up and pay or sign an LOI",
                      threshold="at least 3 of 10 commit at the stated price", cost="$0-100", duration="2-3 weeks",
                      success="a business will pay: confirm price and the buyer's budget owner",
                      failure="no commitment: try a lower price, a different buyer, or a different job",
                      next="convert pilots to paid accounts and measure usage") if b2b else
                 dict(method="Fake-door / pre-sale test: a landing page describing the premium features at "
                             "$%.2f/month, promoted to %s in %s; collect pre-orders or refundable deposits."
                             % (price, cust, geo), metric="share of qualified visitors who click 'buy', and who pay a "
                                                          "deposit", threshold="at least 5% click buy and at least 1% "
                                                                               "pay a deposit (from 300+ visitors)",
                      cost="$100-300 in targeted ads", duration="2 weeks",
                      success="some will pay: keep the price and plan the paid tier",
                      failure="nobody pays: plan a free product with another payer (venues, sponsors) or stop",
                      next="put the paid tier into the pilot app")),
        "H-V2": dict(method="Bottom-up count: list every %s in %s from directories and ask 5 of them for member or "
                            "visitor numbers." % (venue, geo),
                     metric="estimated reachable %s (sum of counted members, de-duplicated)" % cust,
                     threshold="reachable users at least 3x the base break-even volume (%s active users)" % (
                         "{:,}".format(base["breakeven_active"]) if base.get("breakeven_active") else "?"),
                     cost="$0", duration="3-5 days",
                     success="the local market can support the lean scenario", failure="plan a wider launch area or a "
                     "different payer before building", next="use the count in the economics model"),
        "H-V3": dict(method="Channel test: post the pilot sign-up in 3 named channels (club, %s, online group) with "
                            "a trackable link." % venue, metric="sign-ups per channel and cost per sign-up",
                     threshold="at least 30 sign-ups from one channel for under $2 each",
                     cost="$0-100", duration="1-2 weeks", success="a cheap first channel exists",
                     failure="acquisition will be expensive: partner with %s owners instead" % venue,
                     next="use the best channel for the pilot"),
        "H-F1": dict(method="Technical spike: prototype the hardest component with off-the-shelf services in one week.",
                     metric="works end-to-end with test users", threshold="core flow works on two phones",
                     cost="$0-50", duration="1 week", success="build the MVP on this stack",
                     failure="simplify the feature or buy a service", next="scope the MVP"),
        "H-F2": dict(method="In the pilot, ask each participant what they are willing to share (schedule, location, "
                            "profile) and log blocks/reports.", metric="share willing to share schedules with "
                     "non-friends; number of safety reports", threshold="at least 50% willing; zero unresolved reports",
                     cost="$0", duration="during the pilot", success="keep sharing defaults",
                     failure="default to friends-only and invite links", next="write the privacy defaults"),
    }
    return T


def experiments(brief, levels: Dict[str, dict], econ: dict, k: int = 3) -> List[dict]:
    """The k most decision-critical hypotheses = high importance x low evidence; one experiment each."""
    T = _templates(brief, econ)
    hyps = [h for h in brief.hypotheses if h.founder_test or h.id == "H-V2"]
    ranked = sorted(hyps, key=lambda h: (-h.importance, LEVEL_RANK.get(levels.get(h.id, {}).get("level", "none"), 1),
                                         h.id))
    out = []
    for h in ranked:
        if levels.get(h.id, {}).get("level") == "supported" or h.id not in T:
            continue
        if h.id == "H-D2" and brief.network_product and any(x.id == "H-D3" for x in hyps):
            continue  # for a network product the participation-and-return pilot (H-D3) also tests switching
        t = dict(T[h.id])
        t["also_tests"] = ["H-D2"] if h.id == "H-D3" and brief.network_product else []
        out.append({"hypothesis_id": h.id, "hypothesis": h.statement, "segment": "%s%s" % (
            brief.target_customer, (" in " + brief.geography) if brief.geography else ""),
            "evidence_level": levels.get(h.id, {}).get("level", "none"), **t})
        if len(out) >= k:
            break
    order = ["H-D1", "H-D3", "H-D2", "H-V1", "H-V2", "H-V3", "H-F2", "H-F1", "H-X1"]  # problem -> use -> payment
    return sorted(out, key=lambda e: order.index(e["hypothesis_id"]) if e["hypothesis_id"] in order else 99)


def synthesize(brief, questions: Dict[str, dict], competitors: Sequence[dict], econ: dict) -> dict:
    levels = hypothesis_levels(brief.hypotheses, questions)
    checks = cross_checks(brief, questions, levels, competitors, econ)
    key = checks[:5] if len(checks) >= 3 else checks
    return {"hypotheses": levels, "checks": checks, "key_findings": key,
            "verdict": verdict(brief, levels, checks, econ), "experiments": experiments(brief, levels, econ)}


def consistency(text: str, syn: dict, econ: dict) -> List[str]:
    """Statements in narrative text that contradict the computed results (used on any model-written prose)."""
    import re
    problems = []
    low = text.lower()
    if re.search(r"\bvalidated (price|pricing)|\bproven demand\b|\bcustomers (will|are willing to) pay\b", low) and \
            syn["hypotheses"].get("H-V1", {}).get("level") != "supported":
        problems.append("claims validated pricing/payment while willingness to pay is not supported")
    proj = econ.get("projection") or {}
    if re.search(r"break[- ]?even (in|by|within) (year|month)", low) and proj and not proj.get("breakeven_month"):
        problems.append("claims a break-even date the projection does not reach")
    if re.search(r"\b(large|huge|growing) (local )?market\b", low) and not econ.get("market_check"):
        problems.append("describes the market as large while the reachable market is unknown")
    if re.search(r"\bno (direct )?competitors?\b", low) and any(c["id"] == "X3" for c in syn["checks"]):
        problems.append("says there are no competitors while direct competitors were verified")
    return problems
