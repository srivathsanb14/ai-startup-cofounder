"""Validated financial inputs.

The financial planner proposes numbers; this module records, for each important input, its value and unit, who pays,
the period, its basis (evidence / assumption / generic default), the supporting passage, why it is used and how
uncertain it is, and checks it:

* price evidence is classified by *what is being priced* (consumer app, software sold to businesses in this category,
  venue / membership fees, unrelated business software) and must match who pays for the founder's product;
* the modelled price is compared with willingness to pay found by customer research;
* inputs that are unsupported or generic defaults keep that label, and the projection is then labelled
  ILLUSTRATIVE rather than an evidence-backed forecast.

Arithmetic stays in finance.py.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .evidence import _numbers
from .finance import DEFAULT_ASSUMPTIONS, sanitize
from .issues import Issue
from .relevance import terms

PRICE_CATEGORIES = ("consumer_app", "category_business_software", "venue_or_membership_fee",
                    "unrelated_business_software", "unknown")

_BUSINESS = re.compile(r"per (location|seat|door|provider|practice|site|clinic|agent|employee|unit)\b|per user per month|"
                       r"enterprise|crm|saas|b2b|management (software|platform|system)|practice management|"
                       r"marketing (platform|software|automation)|for (gyms|businesses|clinics|practices|teams|agencies|"
                       r"landlords|owners|operators|facilities)|patient|healthcare|property management|implementation fee|"
                       r"point of sale|pos system|billing software|staff scheduling", re.I)
_VENUE = re.compile(r"membership|day pass|drop-in|punch card|admission|entry fee|per visit|guest pass|monthly dues|"
                    r"initiation fee|class pass|annual pass", re.I)
_CONSUMER = re.compile(r"app store|google play|in-app|premium|pro (plan|version|tier)|free to download|freemium|"
                       r"subscription for (you|individuals)|per month for (individuals|users)|individual plan|"
                       r"\bios\b|\bandroid\b|upgrade to", re.I)

KEY_INPUTS = {
    "arpu_monthly": ("USD per paying customer per month", "price"),
    "year1_new_customers": ("paying customers acquired in year 1", "count"),
    "growth_rate": ("year-over-year growth in new customers (fraction)", "rate"),
    "annual_churn": ("share of paying customers lost per year (fraction)", "rate"),
    "cogs_pct": ("cost of revenue as a fraction of revenue", "rate"),
    "cac": ("USD to acquire one paying customer", "price"),
}
REQUIRED_POSITIVE = ("arpu_monthly", "year1_new_customers")  # a model with zero price or zero customers is no model


def classify_price(text: str, frame) -> str:
    on_topic = bool(frame.anchors & terms(text))
    if _BUSINESS.search(text):
        return "category_business_software" if on_topic else "unrelated_business_software"
    if _VENUE.search(text) and on_topic:
        return "venue_or_membership_fee"
    if _CONSUMER.search(text) and on_topic:
        return "consumer_app"
    return "unknown" if on_topic else "unrelated_business_software" if re.search(r"\$\s?\d", text) else "unknown"


def acceptable_categories(payer: str) -> Tuple[str, ...]:
    return ("consumer_app",) if payer == "consumer" else ("category_business_software",)


@dataclass
class FinInput:
    name: str
    value: float
    unit: str
    payer: str
    period: str
    basis: str  # "evidence" | "assumption" | "default"
    status: str  # supported | partially_supported | unsupported | contradicted | explicit_assumption | generic_default
    source_ids: List[str] = field(default_factory=list)
    passage: str = ""
    price_category: str = ""
    reason: str = ""
    uncertainty: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_DOLLARS = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?(?:\s*(?:-|to|–)\s*\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?)?"
                      r"(\s*(?:/|per|a)\s*(month|mo|year|yr|annum|week|session|visit))?", re.I)


def wtp_monthly_max(customer_output: dict) -> Optional[Tuple[float, str]]:
    """Highest monthly willingness to pay stated by customer research, normalised to USD/month."""
    best = None
    for seg in (customer_output or {}).get("segments", []) or []:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("willingness_to_pay") or "")
        for m in _DOLLARS.finditer(text):
            lo = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
            hi = float(m.group(3).replace(",", "")) * (1000 if m.group(4) else 1) if m.group(3) else lo
            per = (m.group(6) or "month").lower()
            monthly = hi / 12 if per in ("year", "yr", "annum") else hi * 4.3 if per == "week" else hi
            if per in ("session", "visit"):
                monthly = hi * 4  # roughly weekly use; recorded in the note
            if best is None or monthly > best[0]:
                best = (monthly, text)
    return best


def _support(value: float, kind: str, ids: Sequence[str], ledger, book) -> Tuple[List[str], str]:
    if kind == "rate":
        needles = {("%g" % (value * 100)).rstrip("0").rstrip(".")} if value else set()
    else:
        needles = {("%g" % value)} if value else set()
    hits, passage = [], ""
    for sid in ids:
        src = ledger.get(sid)
        if src is None or (book is not None and book.of(src).label == "irrelevant" and kind != "price"):
            continue
        if needles and needles & _numbers(src.text):
            hits.append(sid)
            if not passage:
                for sent in re.split(r"(?<=[.!?])\s+", src.snippet or src.title):
                    if needles & _numbers(sent):
                        passage = sent.strip()[:300]
                        break
    return hits, passage


def validate(raw_assumptions: Optional[dict], detail: Optional[list], frame, ledger, book, cited_ids: Sequence[str],
             customer_output: dict) -> Tuple[List[FinInput], List[Issue], str]:
    """Return (inputs, issues, mode) where mode is 'evidence_backed' or 'illustrative'."""
    raw = raw_assumptions if isinstance(raw_assumptions, dict) else {}
    clean = sanitize(raw)
    details = {str(d.get("name", "")).strip(): d for d in detail or [] if isinstance(d, dict)}
    inputs: List[FinInput] = []
    issues: List[Issue] = []
    payer = frame.payer
    ok_cats = acceptable_categories(payer)
    for key, (unit, kind) in KEY_INPUTS.items():
        provided = key in raw and raw.get(key) not in (None, "")
        value = clean[key]
        if provided and key in REQUIRED_POSITIVE and value <= 0:
            provided = False  # zero is a placeholder, not an assumption (small models copy "0" from schemas)
        d = details.get(key, {})
        ids = ledger.valid_ids(d.get("source_ids") or []) or list(cited_ids)
        inp = FinInput(key, value, unit, payer, "per month" if key == "arpu_monthly" else "per year" if kind == "rate"
                       or key == "year1_new_customers" else "one-off per customer", "assumption", "explicit_assumption",
                       reason=str(d.get("reason") or "")[:240], uncertainty=str(d.get("uncertainty") or "")[:200])
        if not provided:
            inp.value = DEFAULT_ASSUMPTIONS[key]
            inp.basis, inp.status = "default", "generic_default"
            inp.reason = "planner gave no usable value%s; generic placeholder %s used" % (
                " (it returned %s)" % raw.get(key) if key in raw else "", DEFAULT_ASSUMPTIONS[key])
            inp.uncertainty = "high: not specific to this idea"
            inputs.append(inp)
            continue
        hits, passage = _support(value, kind, ids, ledger, book)
        if hits:
            inp.source_ids, inp.passage, inp.basis = hits[:3], passage, "evidence"
            if kind == "price":
                text = " ".join(ledger.get(i).text for i in hits)
                inp.price_category = classify_price(text, frame)
                if inp.price_category in ok_cats:
                    inp.status = "partially_supported"
                    inp.reason = inp.reason or "price found in %s evidence" % inp.price_category.replace("_", " ")
                else:
                    inp.status = "unsupported"
                    inp.reason = ("cited figure is %s pricing, but the paying customer is a %s; it cannot anchor this "
                                  "input" % (inp.price_category.replace("_", " "), payer))
            else:
                inp.status = "partially_supported"
        elif str(d.get("basis", "")).lower() == "evidence":
            inp.status, inp.reason = "unsupported", "planner said this is evidence-based but no cited source contains it"
        inputs.append(inp)

    by = {i.name: i for i in inputs}
    arpu = by["arpu_monthly"]
    wrong_category = arpu.status == "unsupported" and arpu.price_category not in ("", "unknown")
    wtp = wtp_monthly_max(customer_output)
    if wtp is not None and arpu.value > 1.25 * wtp[0]:
        arpu.status = "contradicted" if arpu.status != "generic_default" else arpu.status
        issues.append(Issue("financial:price-above-wtp:arpu_monthly", "financial", "high",
                            "modelled price $%.0f/month exceeds the highest willingness to pay found by customer "
                            "research ($%.0f/month: \"%s\")" % (arpu.value, wtp[0], wtp[1][:80]),
                            "Set arpu_monthly consistent with customer willingness to pay and evidence of what %s "
                            "customers pay for comparable products; explain any difference." % payer,
                            "price <= 1.25 x stated willingness to pay, or the gap is justified with evidence",
                            ["arpu_monthly"], "rule"))
    if arpu.status == "unsupported" and not wrong_category:
        issues.append(Issue("financial:price-unsupported:arpu_monthly", "financial", "medium",
                            "price was labelled evidence-based but no cited source contains $%g" % arpu.value,
                            "Cite the source that states this price, or label it an assumption.",
                            "price is found in a cited source or labelled an assumption", ["arpu_monthly"], "rule"))
    if wrong_category:
        issues.append(Issue("financial:price-wrong-category:arpu_monthly", "financial", "high",
                            "price is anchored to %s pricing (%s), not to what a %s pays for this product"
                            % (arpu.price_category.replace("_", " "), ", ".join(arpu.source_ids), payer),
                            "Use only price evidence for products the same %s customer buys; otherwise mark the "
                            "price an explicit assumption." % payer,
                            "price evidence category matches the payer, or price is labelled an assumption",
                            ["arpu_monthly"], "rule"))
    missing = [k for k in REQUIRED_POSITIVE if by[k].status == "generic_default"]
    if missing:
        issues.append(Issue("financial:missing-inputs", "financial", "high",
                            "required inputs missing or zero: %s; generic placeholders were used, so the projection says "
                            "nothing about this idea" % ", ".join(missing),
                            "Give a positive value for %s with a reason (an explicit assumption is acceptable)."
                            % ", ".join(missing), "price and year-1 customers are positive", missing, "rule"))
    defaults = [i.name for i in inputs if i.status == "generic_default" and i.name not in missing]
    if defaults:
        issues.append(Issue("financial:generic-defaults", "financial", "medium",
                            "inputs fell back to generic defaults: %s" % ", ".join(defaults),
                            "Provide a value for each input with a reason, or state that it is unknown.",
                            "no key input uses a generic default", defaults, "rule"))
    core = ("arpu_monthly", "year1_new_customers", "cac")
    backed = all(by[k].status in ("supported", "partially_supported") for k in core)
    mode = "evidence_backed" if backed and not any(i.severity == "high" for i in issues) else "illustrative"
    return inputs, issues, mode
