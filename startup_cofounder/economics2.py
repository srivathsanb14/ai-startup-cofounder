"""Stage-appropriate business economics (deterministic).

For an idea- or prototype-stage startup the useful questions are not "what is revenue in year 5" but:

* what does the first version cost to build, and what does it cost to keep running each month (lean)?
* what does one paying user (or account) contribute after payment fees and variable costs?
* how many paying users / active users are needed to cover the monthly costs (break-even volume)?
* how much money is needed to reach the next validation milestone?
* how sensitive is the required volume to price and conversion?

Three scenarios are computed: a solo founder bootstrapping, a part-time team with a contractor, and a venture-backed
team. No scenario assumes four full-time employees; only the venture scenario pays salaries.

Every assumption records its value, range, basis (evidence / competitor price / rule of thumb / scenario choice),
rationale, uncertainty and source ids. A five-year cohort projection (revenue, churn, CAC, LTV) is computed only on
request (`illustrative=True`) or when price, market size and acquisition cost are all evidence-based; otherwise it is
omitted, so unsupported projections cannot dominate the recommendation.
"""
from __future__ import annotations

import re
import statistics
from typing import Dict, List, Optional, Sequence

PRICE_RX = re.compile(r"(?:US)?\$\s?(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:/|per|a|an)?\s*(month|mo|year|yr|annual|week|"
                      r"session|visit|class|day)?", re.I)
FREE_RX = re.compile(r"\b(free|no cost|\$0)\b", re.I)

SCENARIOS = {
    "solo_bootstrapped": {
        "label": "Solo founder, bootstrapped",
        "team": "the founder builds it in spare time (unpaid); no hires",
        "mvp_cash": 1500.0, "mvp_weeks": 10, "fixed_monthly": 150.0, "experiment_budget": 600.0,
        "why": "design/no-code or own code, app-store and domain fees, low-cost hosting tier, basic tools",
    },
    "part_time_team": {
        "label": "Part-time team with a contractor",
        "team": "two part-time founders (unpaid) and a freelance developer for the MVP",
        "mvp_cash": 15000.0, "mvp_weeks": 8, "fixed_monthly": 600.0, "experiment_budget": 2000.0,
        "why": "about 150-200 contractor hours for an MVP, plus hosting, tools and a small marketing test budget",
    },
    "venture_backed": {
        "label": "Venture-backed team",
        "team": "two full-time hires (engineer, growth) paid from a pre-seed round",
        "mvp_cash": 40000.0, "mvp_weeks": 12, "fixed_monthly": 24000.0, "experiment_budget": 10000.0,
        "why": "two salaries with overhead (~$10k/month each), tools, hosting and paid acquisition tests",
    },
}
MILESTONE_MONTHS = 6  # months of operation after the MVP to reach the next validation milestone


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def prices_in(text: str) -> List[float]:
    """Monthly-equivalent prices in a text ($10/month, $99/year -> 8.25). Per-session prices are skipped."""
    out = []
    for m in PRICE_RX.finditer(text or ""):
        v, unit = _num(m.group(1)), (m.group(2) or "").lower()
        if v <= 0 or v > 5000:
            continue
        if unit in ("year", "yr", "annual"):
            out.append(round(v / 12, 2))
        elif unit in ("week",):
            out.append(round(v * 4.33, 2))
        elif unit in ("month", "mo"):
            out.append(v)
        elif unit in ("session", "visit", "class", "day"):
            continue  # a venue's entry fee is not the price of an app
        else:
            out.append(v)  # no unit: treated as monthly, flagged as uncertain by the caller
    return out


def _assumption(name, value, unit, basis, rationale, uncertainty, low=None, high=None, sources=()) -> dict:
    return {"name": name, "value": value, "unit": unit, "basis": basis, "rationale": rationale,
            "uncertainty": uncertainty, "low": value if low is None else low, "high": value if high is None else high,
            "sources": list(sources)}


def price_assumption(payer: str, wtp_findings: Sequence[dict], comp_prices: Sequence[dict]) -> dict:
    """Price from customers' own payments if found; else what alternatives charge (clearly labelled); else default."""
    wtp = [(p, f["id"]) for f in wtp_findings for p in prices_in(f.get("text", "") + " " + f.get("passage", ""))]
    if wtp:
        vals = [p for p, _ in wtp]
        return _assumption("price_monthly", round(statistics.median(vals), 2), "$/paying user/month", "evidence",
                           "median of prices these customers were observed paying or said they would pay", "medium",
                           min(vals), max(vals), sorted({i for _, i in wtp}))
    paid = [(p, c["name"], c.get("source", "")) for c in comp_prices for p in c.get("monthly", []) if p > 0]
    if paid:
        vals = [p for p, _, _ in paid]
        return _assumption("price_monthly", round(statistics.median(vals), 2), "$/paying user/month",
                           "competitor_price",
                           "median of what alternatives charge (%s); this is NOT evidence that these customers will "
                           "pay it" % ", ".join(sorted({n for _, n, _ in paid})[:4]), "high", min(vals), max(vals),
                           sorted({s for _, _, s in paid if s}))
    base = 8.0 if payer == "consumer" else 49.0
    return _assumption("price_monthly", base, "$/paying user/month", "rule_of_thumb",
                       "no price evidence was found; placeholder typical of a low-cost %s subscription" % (
                           "consumer app" if payer == "consumer" else "small-business software tool"), "high",
                       base / 2, base * 2)


def build(brief, wtp_findings: Sequence[dict] = (), comp_prices: Sequence[dict] = (),
          market_count: Optional[dict] = None, free_alternatives: Sequence[str] = (),
          illustrative: bool = False) -> dict:
    """All numbers deterministic. `comp_prices`: [{"name", "monthly": [..], "source"}];
    `market_count`: {"value", "unit", "source_id", "text"} for a local count, if one was found."""
    consumer = brief.payer != "business"
    price = price_assumption(brief.payer, wtp_findings, comp_prices)
    A = [price]
    if consumer:
        share = _assumption("paying_share", 0.04, "share of active users who pay", "rule_of_thumb",
                            "freemium consumer apps usually convert a low single-digit share of active users; "
                            "not measured for this idea", "high", 0.02, 0.08)
        fee = _assumption("payment_fee", 0.15, "share of price", "rule_of_thumb",
                          "app-store commission for small developers' subscriptions (check the stores' current terms); "
                          "web payments cost ~3%", "low", 0.03, 0.30)
        var = _assumption("variable_cost", 0.10, "$/active user/month", "rule_of_thumb",
                          "hosting, notifications and storage for a light mobile app", "medium", 0.05, 0.50)
    else:
        share = _assumption("paying_share", 1.0, "share of active accounts that pay", "scenario_choice",
                            "business accounts pay after a trial; trial-to-paid conversion is tested separately",
                            "medium", 1.0, 1.0)
        fee = _assumption("payment_fee", 0.03, "share of price", "rule_of_thumb", "card processing for web billing",
                          "low", 0.02, 0.05)
        var = _assumption("variable_cost", 3.0, "$/active account/month", "rule_of_thumb",
                          "hosting plus a little support time per account", "medium", 1.0, 10.0)
    A += [share, fee, var]
    p, s, f, v = price["value"], share["value"], fee["value"], var["value"]
    contrib_paying = p * (1 - f) - v / max(s, 1e-6)  # each paying user also carries the free users' costs
    contrib_active = s * p * (1 - f) - v
    scen = {}
    for key, sc in SCENARIOS.items():
        fixed = sc["fixed_monthly"]
        be_paying = fixed / contrib_paying if contrib_paying > 0 else None
        be_active = be_paying / s if be_paying is not None and s else None
        months = MILESTONE_MONTHS + sc["mvp_weeks"] / 4.33
        funding = sc["mvp_cash"] + fixed * months + sc["experiment_budget"]
        scen[key] = {"label": sc["label"], "team": sc["team"], "mvp_cash": sc["mvp_cash"],
                     "mvp_weeks": sc["mvp_weeks"], "fixed_monthly": fixed, "cost_basis": sc["why"],
                     "experiment_budget": sc["experiment_budget"],
                     "breakeven_paying": None if be_paying is None else int(-(-be_paying // 1)),
                     "breakeven_active": None if be_active is None else int(-(-be_active // 1)),
                     "funding_to_milestone": round(funding, -2),
                     "milestone": "MVP plus %d months of operation and validation experiments" % MILESTONE_MONTHS}
    for key, sc in SCENARIOS.items():
        A.append(_assumption("fixed_monthly[%s]" % key, sc["fixed_monthly"], "$/month", "scenario_choice", sc["why"],
                             "medium", sc["fixed_monthly"] * 0.7, sc["fixed_monthly"] * 1.5))
        A.append(_assumption("mvp_cash[%s]" % key, sc["mvp_cash"], "$", "scenario_choice", sc["why"], "high",
                             sc["mvp_cash"] * 0.5, sc["mvp_cash"] * 2))
    base_key = "solo_bootstrapped" if brief.stage in ("idea", "prototype") else "part_time_team"
    grid = sensitivity(p, s, f, v, SCENARIOS[base_key]["fixed_monthly"], price, share, consumer)
    market = None
    if market_count and market_count.get("value"):
        need = scen[base_key]["breakeven_active"]
        market = {"count": market_count, "share_needed": (round(need / market_count["value"], 3)
                                                          if need and market_count["value"] else None)}
    checks = []
    if price["basis"] != "evidence":
        checks.append("Price is %s, not observed willingness to pay; break-even volumes are only as good as this "
                      "price." % ("borrowed from competitors" if price["basis"] == "competitor_price" else "a placeholder"))
    if free_alternatives:
        checks.append("Free alternative(s) exist (%s): the paid tier must offer something the free option does not."
                      % ", ".join(free_alternatives[:3]))
    if not market:
        checks.append("The number of reachable customers in the launch area is unknown, so it is not known whether the "
                      "break-even volume is achievable.")
    elif market.get("share_needed") and market["share_needed"] > 0.2:
        checks.append("Break-even needs %.0f%% of the counted local market as active users: unrealistic without "
                      "expanding beyond it." % (100 * market["share_needed"]))
    if contrib_paying <= 0:
        checks.append("Each paying user loses money after fees and variable costs at this price.")
    sufficient = price["basis"] == "evidence" and bool(market)
    out = {"stage": brief.stage, "payer": brief.payer, "base_scenario": base_key, "assumptions": A,
           "unit": {"contribution_per_paying_month": round(contrib_paying, 2),
                    "contribution_per_active_month": round(contrib_active, 3)},
           "scenarios": scen, "sensitivity": grid, "market_check": market, "checks": checks,
           "inputs_sufficient_for_projection": sufficient, "projection": None,
           "projection_note": ("not produced: price and reachable-market inputs are not evidence-based" if not
                               (sufficient or illustrative) else "")}
    if sufficient or illustrative:
        out["projection"] = cohort_projection(p, s, f, v, SCENARIOS["venture_backed" if not consumer or brief.stage
                                                                    == "launched" else base_key]["fixed_monthly"],
                                              consumer)
        out["projection"]["illustrative"] = not sufficient
    return out


def sensitivity(p, s, f, v, fixed, price, share, consumer) -> dict:
    prices = sorted({round(price["low"], 2), round(p, 2), round(price["high"], 2)})
    shares = sorted({share["low"], s, share["high"]}) if consumer else [s]
    rows = []
    for sh in shares:
        row = {"paying_share": sh, "breakeven_active": []}
        for pr in prices:
            unit = pr * (1 - f) - (v / sh if sh else v)
            row["breakeven_active"].append(None if unit <= 0 else int(-(-fixed / unit / sh // 1)))
        rows.append(row)
    return {"fixed_monthly": fixed, "prices": prices, "rows": rows}


def cohort_projection(p, s, f, v, fixed, consumer, months: int = 60, new_active_m1: float = 50.0,
                      monthly_growth: float = 0.08, monthly_churn: float = 0.06, cac: float = 4.0) -> dict:
    """Monthly cohorts of ACTIVE users (paying share applied to revenue). Every input is explicit and returned."""
    cohorts: List[float] = []
    rows = []
    cash = 0.0
    breakeven_month = None
    for m in range(1, months + 1):
        new = new_active_m1 * (1 + monthly_growth) ** (m - 1)
        cohorts = [c * (1 - monthly_churn) for c in cohorts] + [new]
        active = sum(cohorts)
        revenue = active * s * p
        costs = revenue * f + active * v + fixed + new * cac
        profit = revenue - costs
        cash += profit
        if breakeven_month is None and profit > 0:
            breakeven_month = m
        if m % 12 == 0:
            rows.append({"year": m // 12, "active_end": round(active), "paying_end": round(active * s),
                         "revenue": round(revenue * 12, -2), "operating_profit_last_month": round(profit),
                         "cumulative_cash": round(cash, -2)})
    margin = p * (1 - f) - (v / s if s else v)
    ltv = margin / monthly_churn if monthly_churn else None
    cac_paying = cac / s if s else cac
    return {"inputs": {"new_active_month1": new_active_m1, "monthly_growth": monthly_growth,
                       "monthly_churn": monthly_churn, "cac_per_active": cac, "fixed_monthly": fixed},
            "rows": rows, "breakeven_month": breakeven_month,
            "ltv_paying": None if ltv is None else round(ltv, 2), "cac_paying": round(cac_paying, 2),
            "ltv_cac": None if not ltv or not cac_paying else round(ltv / cac_paying, 2)}
