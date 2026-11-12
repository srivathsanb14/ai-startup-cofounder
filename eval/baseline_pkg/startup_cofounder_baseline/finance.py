"""Deterministic five-year financial model.

The LLM only proposes *assumptions*; all arithmetic happens here so numbers in
the report are internally consistent and reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import pandas as pd

DEFAULT_ASSUMPTIONS = {
    "arpu_monthly": 30.0,
    "year1_new_customers": 200.0,
    "growth_rate": 0.8,  # year-over-year growth in new customers acquired
    "annual_churn": 0.2,
    "cogs_pct": 0.2,
    "cac": 150.0,
    "other_opex_annual": 24000.0,
    "payroll_burden": 0.2,
    "team": [
        {"role": "Founder/CEO", "count": 1, "annual_salary": 90000, "start_year": 1},
        {"role": "Engineer", "count": 1, "annual_salary": 120000, "start_year": 1},
    ],
    "startup_costs": [
        {"item": "Legal & incorporation", "amount": 5000},
        {"item": "MVP build & tooling", "amount": 30000},
    ],
}

BOUNDS = {
    "arpu_monthly": (0.0, 1e6),
    "year1_new_customers": (0.0, 1e7),
    "growth_rate": (-0.5, 5.0),
    "annual_churn": (0.0, 0.95),
    "cogs_pct": (0.0, 0.95),
    "cac": (0.0, 1e6),
    "other_opex_annual": (0.0, 1e9),
    "payroll_burden": (0.0, 1.0),
}


def _num(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        v = float(str(value).replace(",", "").replace("$", "").replace("%", ""))
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return min(max(v, lo), hi)


def sanitize(raw: Optional[dict]) -> dict:
    """Clamp LLM-proposed assumptions to sane ranges and fill gaps with defaults."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key, (lo, hi) in BOUNDS.items():
        if key in ("annual_churn", "cogs_pct", "payroll_burden"):
            # models often express rates as 20 instead of 0.2
            value = _num(raw.get(key), DEFAULT_ASSUMPTIONS[key], 0.0, 1e6)
            if value > 1:
                value /= 100.0
            out[key] = min(max(value, lo), hi)
        else:
            out[key] = _num(raw.get(key), DEFAULT_ASSUMPTIONS[key], lo, hi)
    team = []
    for m in raw.get("team") or []:
        if not isinstance(m, dict):
            continue
        team.append({
            "role": str(m.get("role", "Team member"))[:60],
            "count": int(_num(m.get("count"), 1, 0, 500)),
            "annual_salary": _num(m.get("annual_salary"), 90000, 0, 1e6),
            "start_year": int(_num(m.get("start_year"), 1, 1, 5)),
        })
    out["team"] = team or [dict(m) for m in DEFAULT_ASSUMPTIONS["team"]]
    costs = []
    for c in raw.get("startup_costs") or []:
        if isinstance(c, dict):
            costs.append({"item": str(c.get("item", "Other"))[:60], "amount": _num(c.get("amount"), 0, 0, 1e9)})
    out["startup_costs"] = costs or [dict(c) for c in DEFAULT_ASSUMPTIONS["startup_costs"]]
    return out


@dataclass
class Projection:
    assumptions: dict
    table: pd.DataFrame
    startup_total: float
    breakeven_year: Optional[int]  # first year with positive operating profit
    payback_year: Optional[int]  # first year cumulative cash is >= 0
    peak_funding_need: float  # deepest cumulative cash deficit

    def to_dict(self) -> dict:
        return {
            "assumptions": self.assumptions,
            "table": self.table.round(0).to_dict(orient="records"),
            "startup_total": self.startup_total,
            "breakeven_year": self.breakeven_year,
            "payback_year": self.payback_year,
            "peak_funding_need": self.peak_funding_need,
        }


def project(raw_assumptions: Optional[dict], years: int = 5) -> Projection:
    a = sanitize(raw_assumptions)
    startup_total = sum(c["amount"] for c in a["startup_costs"])
    rows: List[dict] = []
    customers = 0.0
    new = a["year1_new_customers"]
    cash = -startup_total
    peak = startup_total
    for year in range(1, years + 1):
        if year > 1:
            new *= 1 + a["growth_rate"]
        start = customers
        churned = start * a["annual_churn"]
        customers = start - churned + new
        revenue = a["arpu_monthly"] * 12 * (start + customers) / 2
        cogs = revenue * a["cogs_pct"]
        marketing = new * a["cac"]
        payroll = sum(m["count"] * m["annual_salary"] for m in a["team"] if m["start_year"] <= year)
        payroll *= 1 + a["payroll_burden"]
        profit = revenue - cogs - marketing - payroll - a["other_opex_annual"]
        cash += profit
        peak = max(peak, -cash)
        rows.append({
            "year": year, "customers_end": customers, "new_customers": new, "revenue": revenue,
            "cogs": cogs, "gross_profit": revenue - cogs, "marketing": marketing, "payroll": payroll,
            "other_opex": a["other_opex_annual"], "operating_profit": profit, "cumulative_cash": cash,
        })
    table = pd.DataFrame(rows)
    positive = table[table["operating_profit"] > 0]
    paid = table[table["cumulative_cash"] >= 0]
    return Projection(
        assumptions=a,
        table=table,
        startup_total=startup_total,
        breakeven_year=int(positive.iloc[0]["year"]) if len(positive) else None,
        payback_year=int(paid.iloc[0]["year"]) if len(paid) else None,
        peak_funding_need=max(peak, 0.0),
    )


# ---------------------------------------------------------------------------
# Unit economics, scenarios, sensitivity and sanity checks
# ---------------------------------------------------------------------------

MAX_LIFETIME_MONTHS = 60  # cap customer lifetime so near-zero churn does not produce absurd LTV


def unit_economics(assumptions: dict) -> dict:
    a = sanitize(assumptions)
    gross_monthly = a["arpu_monthly"] * (1 - a["cogs_pct"])
    monthly_churn = 1 - (1 - a["annual_churn"]) ** (1 / 12.0)
    lifetime = min(1 / monthly_churn, MAX_LIFETIME_MONTHS) if monthly_churn > 0 else MAX_LIFETIME_MONTHS
    ltv = gross_monthly * lifetime
    return {
        "gross_margin_monthly": gross_monthly,
        "lifetime_months": lifetime,
        "ltv": ltv,
        "cac": a["cac"],
        "ltv_cac": (ltv / a["cac"]) if a["cac"] > 0 else None,
        "cac_payback_months": (a["cac"] / gross_monthly) if gross_monthly > 0 and a["cac"] > 0 else (0.0 if a["cac"] == 0 else None),
    }


SCENARIO_MULTIPLIERS = {
    # name: (arpu, new customers, growth, churn, cac)
    "pessimistic": (0.85, 0.5, 0.6, 1.4, 1.4),
    "base": (1.0, 1.0, 1.0, 1.0, 1.0),
    "optimistic": (1.1, 1.4, 1.2, 0.75, 0.85),
}


def scenarios(assumptions: dict, years: int = 5) -> dict:
    base = sanitize(assumptions)
    out = {}
    for name, (arpu, cust, growth, churn, cac) in SCENARIO_MULTIPLIERS.items():
        a = dict(base)
        a["arpu_monthly"] *= arpu
        a["year1_new_customers"] *= cust
        a["growth_rate"] *= growth
        a["annual_churn"] = min(a["annual_churn"] * churn, BOUNDS["annual_churn"][1])
        a["cac"] *= cac
        out[name] = project(a, years)
    return out


SENSITIVITY_KEYS = [
    ("arpu_monthly", "Price per customer"),
    ("year1_new_customers", "Year-1 new customers"),
    ("growth_rate", "Growth in new customers"),
    ("annual_churn", "Annual churn"),
    ("cogs_pct", "Cost of goods %"),
    ("cac", "Acquisition cost (CAC)"),
]


def sensitivity(assumptions: dict, delta: float = 0.2, years: int = 5) -> List[dict]:
    """Year-5 operating profit when each assumption moves -/+delta. Sorted by impact (tornado order)."""
    base = sanitize(assumptions)
    base_profit = float(project(base, years).table.iloc[-1]["operating_profit"])
    rows = []
    for key, label in SENSITIVITY_KEYS:
        deltas = []
        for factor in (1 - delta, 1 + delta):
            a = dict(base)
            a[key] = a[key] * factor
            deltas.append(float(project(a, years).table.iloc[-1]["operating_profit"]) - base_profit)
        rows.append({"assumption": label, "low": deltas[0], "high": deltas[1], "swing": abs(deltas[1] - deltas[0])})
    return sorted(rows, key=lambda r: r["swing"], reverse=True)


def sanity_flags(proj: Projection, ue: dict, sam_usd=None) -> List[str]:
    """Plain-English warnings about implausible or worrying economics."""
    flags = []
    ratio = ue.get("ltv_cac")
    if ratio is not None and ratio < 3:
        flags.append("LTV/CAC is %.1f; healthy subscription businesses target 3 or more." % ratio)
    payback = ue.get("cac_payback_months")
    if payback is None:
        flags.append("Gross margin per customer is zero or negative, so acquisition cost is never recovered.")
    elif payback > 18:
        flags.append("CAC payback takes %.0f months (over 18 is hard to finance)." % payback)
    last = proj.table.iloc[-1]
    try:
        sam = float(sam_usd)
    except (TypeError, ValueError):
        sam = 0.0
    if sam > 0 and last["revenue"] / sam > 0.05:
        flags.append("Year-5 revenue would be %.0f%% of the serviceable market (SAM); that is aggressive." % (100 * last["revenue"] / sam))
    headcount = sum(m["count"] for m in proj.assumptions["team"] if m["start_year"] <= 5)
    if headcount and last["revenue"] / headcount < 80000:
        flags.append("Year-5 revenue per employee is only $%s." % "{:,.0f}".format(last["revenue"] / headcount))
    if proj.peak_funding_need > 2e6:
        flags.append("Peak funding need of $%.1fM implies outside capital, not bootstrapping." % (proj.peak_funding_need / 1e6))
    if proj.breakeven_year is None:
        flags.append("No operating break-even within 5 years under the base case.")
    return flags
