"""Review of the finished memo against the authoritative computed numbers and the research record.

Runs after financial calculation and synthesis. Each problem becomes an Issue (origin "final"). The pipeline asks the
synthesizer for one correction; anything still wrong is then *disclosed*: the offending sentence is replaced by a
visible note and the report carries a publication warning. Missing values are never invented to satisfy a schema.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .issues import Issue
from .relevance import terms

NARRATIVE_FIELDS = ("verdict_rationale", "executive_summary", "future_outlook", "recommendation")
LIST_FIELDS = ("reasons", "key_uncertainties", "would_change_if")

_COUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|million|m)?\+?\s+(?:new\s+|paying\s+|active\s+|monthly\s+)*"
                    r"(customers|users|subscribers|members|clients|accounts|signups|sign-ups)", re.I)
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)", re.I)
_RATIO = re.compile(r"ltv\s*[:/]\s*cac(?:\s+ratio)?(?:\s+of)?(?:\s+(?:at least|about|around|over|above))?\s+(\d+(?:\.\d+)?)", re.I)
_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million|b|billion)?", re.I)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
_DISCLOSE = re.compile(r"unresolved|insufficient|unverified|limited evidence|weak evidence|could not|not (been )?"
                       r"(found|verified|confirmed)|uncertain|illustrative|assumption", re.I)


def _texts(syn: dict) -> List[Tuple[str, str]]:
    """(field path, text) for every narrative string in the synthesis."""
    out = [(k, str(syn.get(k) or "")) for k in NARRATIVE_FIELDS]
    for k in LIST_FIELDS:
        for i, item in enumerate(syn.get(k) or []):
            out.append(("%s[%d]" % (k, i), str(item)))
    scope = syn.get("scope") if isinstance(syn.get("scope"), dict) else {}
    out.append(("scope.success_definition", str(scope.get("success_definition") or "")))
    out.append(("scope.target_customer", str(scope.get("target_customer") or "")))
    for i, r in enumerate(syn.get("risks") or []):
        if isinstance(r, dict):
            out.append(("risks[%d]" % i, "%s %s" % (r.get("risk", ""), r.get("mitigation", ""))))
    for i, v in enumerate(syn.get("validation_steps") or []):
        if isinstance(v, dict):
            out.append(("validation_steps[%d]" % i, " ".join(str(v.get(k, "")) for k in
                                                           ("assumption", "experiment", "success_metric", "timeframe",
                                                            "hypothesis", "test", "metric", "threshold"))))
    return [(k, t) for k, t in out if t.strip()]


def _sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+", text) if s.strip()]


def _near(a: float, b: float, tol: float = 0.1) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(b))


def check(syn: dict, computed: dict, *, customer_output: Optional[dict] = None, open_issues: Sequence = (),
          fin_mode: str = "illustrative", market_valid: bool = True, partial: bool = False) -> List[Issue]:
    issues: List[Issue] = []
    if not isinstance(syn, dict) or not syn:
        return [Issue("synthesizer:no-output", "synthesizer", "high", "no decision memo was produced",
                      "Write the memo.", "memo present", origin="final")]
    proj = computed.get("projection", {})
    table = proj.get("table", [])
    ue = computed.get("unit_economics", {})
    model_counts = sorted({round(float(r.get(k, 0))) for r in table for k in ("new_customers", "customers_end")})
    gm_pct = 100.0 * (1 - float(proj.get("assumptions", {}).get("cogs_pct", 0)))
    allowed_pct = {
        "margin": [gm_pct],
        "churn": [100.0 * float(proj.get("assumptions", {}).get("annual_churn", 0))],
        "growth": [100.0 * float(proj.get("assumptions", {}).get("growth_rate", 0))],
    }
    seen_ids = set()

    def add(code, field_path, sev, msg, fix, sentence=""):
        iid = "synthesizer:%s:%s" % (code, field_path)
        if iid in seen_ids:
            return
        seen_ids.add(iid)
        iss = Issue(iid, "synthesizer", sev, msg, fix, "statement matches the computed model or is removed",
                    [field_path], "final")
        iss.history.append({"sentence": sentence[:300]})
        issues.append(iss)

    for path, text in _texts(syn):
        for sent in _sentences(text):
            low = sent.lower()
            for m in _COUNT.finditer(sent):
                n = float(m.group(1).replace(",", "")) * _SCALE.get((m.group(2) or "").lower(), 1)
                if n < 5 or re.search(r"interview|survey|pilot|beta|pre-?order|waitlist|test", low):
                    continue  # validation-experiment sample sizes are not model claims
                if not any(_near(n, c, 0.15) for c in model_counts):
                    add("customer-count", path, "high",
                        "states %s %s, but the financial model has %s customers (year 1 new: %s)" % (
                            "{:,.0f}".format(n), m.group(3), ", ".join("{:,}".format(c) for c in model_counts[:6]),
                            "{:,.0f}".format(table[0]["new_customers"]) if table else "n/a"),
                        "Use customer numbers from the computed projection only, with their year.", sent)
            for m in _PCT.finditer(sent):
                v = float(m.group(1))
                ctx = low[max(0, m.start() - 60): m.end() + 30]
                if "margin" in ctx and v > 100:
                    add("impossible-percentage", path, "high",
                        "states a %.0f%% margin; a margin cannot exceed 100%% (gross profit per customer is $%.0f/month,"
                        " gross margin is %.0f%%)" % (v, ue.get("gross_margin_monthly", 0), gm_pct),
                        "Report gross margin as a percentage from the model and gross profit per customer in dollars.",
                        sent)
                    continue
                if re.search(r"market|industry|cagr|sector|nationwide|global", ctx):
                    continue  # third-party statistics are checked as claims, not against the model
                for key, vals in allowed_pct.items():
                    if key in ctx and not any(abs(v - x) <= 2.0 for x in vals):
                        add("percentage-mismatch-%s" % key, path, "high",
                            "states %s%% %s, but the model uses %.0f%%" % (m.group(1), key, vals[0]),
                            "Use the model's %s figure." % key, sent)
            for m in _RATIO.finditer(sent):
                v = float(m.group(1))
                actual = ue.get("ltv_cac")
                if actual is not None and not _near(v, actual, 0.1):
                    add("ratio-mismatch", path, "high", "states LTV/CAC %s but the model gives %.1f" % (m.group(1), actual),
                        "Use the computed LTV/CAC.", sent)
            if not market_valid and re.search(r"market (size|of|worth|valued)|tam\b|billion", low) and _MONEY.search(sent):
                add("market-figure-underived", path, "medium",
                    "cites a market-size figure although the market section has no valid TAM/SAM/SOM derivation",
                    "Do not present market figures as this product's market size; state that sizing is unresolved.",
                    sent)
    for iss in financial_statements(syn, proj):
        if iss.id not in seen_ids:
            seen_ids.add(iss.id)
            issues.append(iss)
    # willingness to pay vs modelled price
    from .fininputs import wtp_monthly_max
    wtp = wtp_monthly_max(customer_output or {})
    arpu = float(proj.get("assumptions", {}).get("arpu_monthly", 0) or 0)
    if wtp is not None and arpu > 1.25 * wtp[0]:
        all_text = " ".join(t for _, t in _texts(syn))
        if not re.search(r"willingness to pay|price", all_text, re.I) or not _DISCLOSE.search(all_text):
            add("wtp-conflict-undisclosed", "executive_summary", "high",
                "the model charges $%.0f/month but customer research found willingness to pay up to $%.0f/month; "
                "the memo does not address this" % (arpu, wtp[0]),
                "State the conflict between modelled price and willingness to pay and treat price as unvalidated.")
    # conclusions must reflect unresolved research problems
    high_open = [i for i in open_issues if getattr(i, "severity", "") == "high"]
    narrative = " ".join(str(syn.get(k) or "") for k in NARRATIVE_FIELDS)
    if (high_open or fin_mode != "evidence_backed" or partial) and not _DISCLOSE.search(narrative):
        add("undisclosed-limitations", "executive_summary", "high",
            "the memo does not mention %s" % ("; ".join(filter(None, [
                "%d unresolved high-severity research issue(s)" % len(high_open) if high_open else "",
                "that the financial projection is illustrative" if fin_mode != "evidence_backed" else "",
                "that research is incomplete" if partial else ""]))),
            "Say plainly which research questions remain unresolved and that the numbers are illustrative.")
    # scope contradictions: something declared out of scope is also a feature or a recommended step
    scope = syn.get("scope") if isinstance(syn.get("scope"), dict) else {}
    doing = [str(x) for x in (scope.get("mvp_features") or [])] + [
        "%s %s" % (v.get("assumption", ""), v.get("experiment", "")) for v in syn.get("validation_steps") or []
        if isinstance(v, dict)]
    for item in scope.get("out_of_scope") or []:
        it = terms(str(item))
        for d in doing:
            dt = terms(d)
            if len(it) >= 2 and len(it & dt) >= max(2, int(0.5 * len(it))):
                add("scope-contradiction", "scope.out_of_scope", "medium",
                    "'%s' is out of scope but also a feature or recommended step ('%s')" % (str(item)[:80], d[:80]),
                    "Remove the item from out_of_scope or from the plan.")
                break
    # empty required fields and filler
    for k in ("verdict_rationale", "executive_summary"):
        if not str(syn.get(k) or "").strip():
            add("empty-field", k, "high", "%s is empty" % k, "Write it from the research and computed numbers.")
    texts = [t for _, t in _texts(syn)]
    keys = [" ".join(sorted(terms(t))) for t in texts if len(terms(t)) > 3]
    if len(keys) - len(set(keys)) >= 2:
        add("duplicated-filler", "synthesis", "medium", "memo repeats the same statements",
            "Remove repeated text.")
    return issues


TARGET_RX = re.compile(r"\b(target|goal|aim|aspire|want|plan to|should|must|need to|success (looks like|definition|"
                       r"means)|objective|milestone)\b", re.I)
NEG_RX = re.compile(r"\b(not|no|never|beyond|without|fails? to|unlikely|outside)\b", re.I)
BREAKEVEN_RX = re.compile(r"break[- ]?even|profitab|operating profit|turns? a profit|in the black", re.I)
PAYBACK_RX = re.compile(r"pay ?back|positive cumulative cash|cumulative cash (flow )?(turns|becomes|is) positive|"
                        r"recover(s|ed)? (the )?(initial )?investment", re.I)
YEARS_RX = re.compile(r"(?:within|by|in|after)\s+(?:year\s+)?(\d|one|two|three|four|five)\s*(?:years?)?", re.I)
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def financial_statements(syn: dict, proj: dict) -> List[Issue]:
    """Sentences asserting break-even / profitability / payback are compared with the computed model by meaning:
    an assertion that it happens (optionally by year N) contradicts a model where it does not (or happens later).
    Negated sentences agree with a model that shows none. Targets ("aim to break even") are not assertions; they are
    reported separately as founder targets."""
    issues: List[Issue] = []
    be, pb = proj.get("breakeven_year"), proj.get("payback_year")
    clauses = []
    for path, text in _texts(syn):
        for full in _sentences(text):
            for clause in re.split(r",?\s+\b(?:but|while|whereas|although|however|yet)\b\s+|;\s*", full):
                if clause:
                    clauses.append((path, full, clause))
    for path, full, sent in clauses:
        for kind, rx, actual in (("break-even", BREAKEVEN_RX, be), ("payback", PAYBACK_RX, pb)):
            if not rx.search(sent):
                continue
            if TARGET_RX.search(sent) or path.startswith("scope.success") or path.startswith("validation_steps"):
                continue
            negated = bool(NEG_RX.search(sent))
            m = YEARS_RX.search(sent)
            year = None
            if m:
                g = m.group(1).lower()
                year = int(g) if g.isdigit() else _WORDNUM.get(g)
            wrong = False
            if not negated and actual is None:
                wrong = True
            elif not negated and year is not None and actual is not None and actual > year:
                wrong = True
            elif negated and actual is not None and (year is None or actual <= year):
                wrong = True
            if wrong:
                iss = Issue("synthesizer:%s-contradiction:%s" % (kind, path), "synthesizer", "high",
                            "states %s %s, but the computed model shows %s" % (
                                kind, "does not occur" if negated else "occurs" + (" by year %d" % year if year else ""),
                                "year %d" % actual if actual else "none within 5 years"),
                            "Report %s only from the computed model." % kind,
                            "statement matches the computed model or is removed", [path], "final")
                iss.history.append({"sentence": full[:300]})
                if iss.id not in {i.id for i in issues}:
                    issues.append(iss)
    return issues


def founder_targets(syn: dict) -> List[str]:
    """Goals stated by the memo (founder_targets field, or target-worded sentences about financial milestones)."""
    out = [str(t) for t in syn.get("founder_targets") or [] if str(t).strip()]
    scope = syn.get("scope") if isinstance(syn.get("scope"), dict) else {}
    sd = str(scope.get("success_definition") or "")
    if sd and (BREAKEVEN_RX.search(sd) or PAYBACK_RX.search(sd) or re.search(r"\d", sd)):
        out.append(sd)
    return list(dict.fromkeys(out))


def disclose(syn: dict, issues: Sequence[Issue]) -> Tuple[dict, List[str]]:
    """Remove sentences flagged as contradicting the model and say so in place. Returns (synthesis, notes)."""
    out = dict(syn)
    notes: List[str] = []
    for iss in issues:
        sentence = next((h.get("sentence") for h in iss.history if h.get("sentence")), "")
        path = iss.fields[0] if iss.fields else ""
        note = "[Removed by final review: %s]" % iss.message
        replaced = False
        if sentence:
            for key in NARRATIVE_FIELDS:
                if sentence in str(out.get(key) or ""):
                    out[key] = str(out[key]).replace(sentence, note)
                    replaced = True
            scope = dict(out.get("scope") or {}) if isinstance(out.get("scope"), dict) else {}
            for key in ("success_definition", "target_customer"):
                if sentence in str(scope.get(key) or ""):
                    scope[key] = str(scope[key]).replace(sentence, note)
                    replaced = True
            if scope:
                out["scope"] = scope
            for key in LIST_FIELDS:
                vals = out.get(key)
                if isinstance(vals, list) and any(sentence in str(v) for v in vals):
                    out[key] = [str(v).replace(sentence, note) if sentence in str(v) else v for v in vals]
                    replaced = True
            for listkey in ("risks", "validation_steps"):
                items = []
                for item in out.get(listkey) or []:
                    if isinstance(item, dict) and any(sentence in str(v) for v in item.values()):
                        item = {k: (str(v).replace(sentence, note) if sentence in str(v) else v) for k, v in item.items()}
                        replaced = True
                    items.append(item)
                if items:
                    out[listkey] = items
        iss.status = "disclosed"
        notes.append("%s%s" % (iss.message, "" if replaced or not sentence else " (in %s)" % path))
    return out, notes
