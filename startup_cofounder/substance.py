"""Substantive checks: did each role answer its decision questions?

Field presence and on-topic vocabulary are not enough. These checks catch, deterministically:

* a customer section that describes an existing product's users instead of prospective customers
* competitor prices presented as willingness to pay for the founder's product
* missing information presented as white space / weaknesses
* local demand asserted from broader (national/global) evidence
* product names listed as technical components; no user journey; no effort basis
* risk sections that repeat product marketing instead of scenarios with controls
* instruction text leaking into a rationale; startup costs that duplicate salaries

Each finding is an Issue with a feasible action: "research" (search again), "regenerate" (rewrite from the evidence
already held) or "founder" (a real-world test: goes to the validation plan, never back to a web researcher).
Works on v3 outputs and on saved v2 outputs.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from .issues import Issue
from .relevance import GENERIC, terms

UNKNOWN_RX = re.compile(
    r"\bnot (explicitly |specifically |clearly )?(detailed|mentioned|specified|available|found|provided|stated|clear|"
    r"described|known)\b|\bunknown\b|\bunclear\b|\bno (specific |direct |detailed |clear |explicit )?"
    r"(information|details|data|mention|evidence)\b|\bno (specific |direct |detailed |clear |explicit )?[a-z]+"
    r"( [a-z]+)? (is |are |was |were )?(mentioned|stated|provided|found|given|available|described)\b|"
    r"not in (the )?(sources|evidence)", re.I)
GROWTH_RX = re.compile(r"\b(grow|growth|growing|increas|expand|rising|rapid|boom|surg|demand)", re.I)
INSTRUCTION_RX = re.compile(r"^\s*(use|infer|assume|focus|provide|estimate|consider|make sure|ensure|based on the "
                            r"evidence,? (infer|estimate))\b", re.I)
GUARANTEE_RX = re.compile(r"\b(guarantee[sd]?|ensures? (that )?(users|climbers|partners|people) (are|will be) safe|"
                          r"100% safe|completely safe)\b", re.I)
SALARY_RX = re.compile(r"salar|payroll|wage|team cost|staff", re.I)


def _strs(items) -> List[str]:
    return [str(i).strip() for i in items if str(i).strip()] if isinstance(items, list) else []


def mentions_product(text: str, products: Iterable[str]) -> List[str]:
    low = " %s " % (text or "").lower()
    hits = []
    for p in products:
        name = str(p or "").strip()
        if len(name) < 3:
            continue
        if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(name.lower()), low):
            hits.append(name)
    return hits


def _issue(role, code, severity, message, fix, acceptance, fields=(), action="regenerate"):
    i = Issue("%s:%s" % (role, code), role, severity, message, fix, acceptance, list(fields), "rule")
    i.action = action
    return i


def customer(out: dict, frame, products: Sequence[str]) -> List[Issue]:
    issues: List[Issue] = []
    segs = [s for s in out.get("segments") or [] if isinstance(s, dict)]
    target = str(out.get("target_segment") or (segs[0].get("name", "") + " " + segs[0].get("description", "")
                                                 if segs else ""))
    problem = str(out.get("problem") or (" ".join(_strs(segs[0].get("pain_points"))) if segs else ""))
    if not target.strip() or not problem.strip():
        issues.append(_issue("customer", "no-target-segment", "high", "no initial target segment and problem situation",
                             "Name the first specific customer group and the situation in which the problem occurs.",
                             "target_segment and problem are filled", ["target_segment", "problem"]))
    named = mentions_product(" ".join([target, str(out.get("summary") or "")]), products)
    if named:
        issues.append(_issue("customer", "describes-product-users", "high",
                             "describes users of %s instead of the prospective customers" % ", ".join(sorted(set(named))),
                             "Describe the people who have the problem, independent of any existing product; existing "
                             "products belong in their workarounds.", "target segment and summary name no product",
                             ["target_segment", "summary"]))
    wtp_texts = [str(out.get("willingness_to_pay") or "")] + [str(s.get("willingness_to_pay") or "") for s in segs]
    for wtp in wtp_texts:
        if not wtp.strip() or UNKNOWN_RX.search(wtp):
            continue
        if mentions_product(wtp, products) or re.search(r"\b(free to use|pro plan|premium plan|subscription is|"
                                                         r"pricing|plan is available)\b", wtp, re.I):
            issues.append(_issue("customer", "wtp-is-competitor-price", "high",
                                 "willingness to pay is a competitor's pricing (\"%s\"), not evidence of what these "
                                 "customers would pay for this product" % wtp[:90],
                                 "Set willingness to pay to 'unknown' unless evidence states what these customers "
                                 "would pay; a pricing test belongs in the founder's validation plan.",
                                 "willingness_to_pay is evidence about these customers or 'unknown'",
                                 ["willingness_to_pay"]))
            break
    if "current_workarounds" in out and not _strs(out.get("current_workarounds")):
        issues.append(_issue("customer", "no-workarounds", "medium", "no current workaround identified",
                             "Search for how these people solve the problem today (forums, groups, notice boards).",
                             "at least one current workaround", ["current_workarounds"], "research"))
    return issues


def competitor(out: dict, frame) -> List[Issue]:
    issues: List[Issue] = []
    ws = str(out.get("white_space") or "")
    if ws and UNKNOWN_RX.search(ws):
        issues.append(_issue("competitor", "unknown-as-white-space", "high",
                             "missing information is presented as white space: \"%s\"" % ws[:100],
                             "Move unknowns to 'unknowns'; white space needs evidence of an unmet need.",
                             "white_space is empty or evidence-based", ["white_space"]))
    for c in out.get("competitors") or []:
        if not isinstance(c, dict):
            continue
        bad = [w for w in _strs(c.get("weaknesses")) if UNKNOWN_RX.search(w)]
        if bad:
            issues.append(_issue("competitor", "unknown-as-weakness", "medium",
                                 "%s: a lack of information is listed as a weakness (\"%s\")" % (c.get("name"), bad[0][:70]),
                                 "List only weaknesses shown by evidence; record the rest as unknowns.",
                                 "no weakness states missing information", ["competitors.weaknesses"]))
            break
    if str(out.get("differentiation_status")) == "established" and not any(
            _strs(c.get("verified_differences")) for c in out.get("competitors") or [] if isinstance(c, dict)):
        issues.append(_issue("competitor", "differentiation-unverified", "medium",
                             "differentiation is called established but no verified difference is recorded",
                             "Label differentiation a hypothesis unless evidence shows the difference.",
                             "differentiation_status matches the evidence", ["differentiation_status"]))
    return issues


def market(out: dict, frame, claims: Sequence) -> List[Issue]:
    issues: List[Issue] = []
    text = " ".join([str(out.get("summary") or "")] + _strs(out.get("trends")))
    local_growth = [s for s in re.split(r"(?<=[.!?;])\s+", text)
                    if GROWTH_RX.search(s) and (frame.geo_terms and frame.geo_terms <= terms(s) or "local" in s.lower())]
    backed = [c for c in claims if getattr(c, "status", "") in ("supported", "partially_supported")
              and GROWTH_RX.search(getattr(c, "text", "")) and frame.geo_terms <= terms(getattr(c, "passage", ""))]
    if local_growth and not backed:
        issues.append(_issue("market", "local-demand-unsupported", "high",
                             "asserts local growth/demand (\"%s\") without local evidence" % local_growth[0][:100],
                             "Find evidence specific to %s, or replace the assertion with an open question."
                             % (frame.geography or "the launch area"),
                             "no local growth assertion without a local source", ["summary", "trends"], "research"))
    inputs = [i for i in out.get("inputs") or [] if isinstance(i, dict)]
    if not inputs or all(i.get("value") in (None, "", 0) for i in inputs):
        issues.append(_issue("market", "bottom-up-inputs-missing", "medium",
                             "no bottom-up input for the launch market has a value",
                             "Search for the number of local participants or venues in %s and cite it."
                             % (frame.geography or "the launch area"),
                             "at least one launch-market input with value and source", ["inputs"], "research"))
    return issues


def technical(out: dict, frame, products: Sequence[str]) -> List[Issue]:
    issues: List[Issue] = []
    comps = [c for c in out.get("components") or [] if isinstance(c, dict)]
    names = [str(c.get("name") or "") for c in comps] or _strs(out.get("key_components"))
    bad = []
    for n in names:
        nt = terms(n) - GENERIC
        is_category = bool(nt) and nt <= (frame.core | frame.anchors | frame.geo_terms) and re.search(r"\bapps?\b", n, re.I)
        if mentions_product(n, products) or is_category:
            bad.append(n)
    if bad:
        issues.append(_issue("technical", "components-are-products", "high",
                             "listed components are product or category names, not architecture: %s" % ", ".join(bad[:4]),
                             "Propose generic components (e.g. profile store, matching service, messaging) each with a "
                             "responsibility and a build/buy choice.", "no component is a product or category name",
                             ["components"]))
    if comps and any(not str(c.get("responsibility") or "").strip() for c in comps):
        issues.append(_issue("technical", "components-without-responsibility", "medium",
                             "some components have no responsibility", "State what each component does.",
                             "every component has a responsibility", ["components"]))
    if not _strs(out.get("user_journey")):
        issues.append(_issue("technical", "no-user-journey", "high", "no minimum user journey is proposed",
                             "List the minimum steps a user takes from sign-up to a useful outcome.",
                             "user_journey has at least three steps", ["user_journey"]))
    eff = out.get("effort") if isinstance(out.get("effort"), dict) else {}
    if not (eff.get("weeks_low") and eff.get("team")):
        issues.append(_issue("technical", "effort-without-basis", "medium",
                             "no effort range with its scope and staffing assumption",
                             "Give an effort range in weeks with the team and scope it assumes.",
                             "effort has weeks, team and scope", ["effort"]))
    return issues


def risk(role: str, out: dict, frame, products: Sequence[str]) -> List[Issue]:
    issues: List[Issue] = []
    scen = [s for s in out.get("scenarios") or [] if isinstance(s, dict)]
    items = _strs(out.get("key_points")) + _strs(out.get("implications_for_founder"))
    if not scen:
        marketing = [t for t in items + [str(out.get("summary") or "")] if mentions_product(t, products)]
        issues.append(_issue(role, "no-risk-scenarios", "high",
                             "no concrete misuse or exposure scenario" + (
                                 " (the section repeats what other apps offer)" if marketing else ""),
                             "List scenarios such as exposed location/schedule, unwanted contact or data retention, each "
                             "with harm, proposed control and its limitation.", "at least two scenarios with controls",
                             ["scenarios"]))
    elif any(not str(s.get("control") or "").strip() or not str(s.get("limitation") or "").strip() for s in scen):
        issues.append(_issue(role, "controls-incomplete", "medium", "a scenario lacks a control or its limitation",
                             "Give each scenario a control and the control's limitation.",
                             "every scenario has control and limitation", ["scenarios"]))
    all_text = " ".join([str(out.get("summary") or "")] + items + [" ".join(map(str, s.values())) for s in scen])
    if GUARANTEE_RX.search(all_text):
        issues.append(_issue(role, "safety-guarantee", "high", "claims the product guarantees safety",
                             "Remove guarantees; describe risk reduction and its limits.", "no guarantee language",
                             ["summary"]))
    return issues


def other_specialist(role: str, out: dict, products: Sequence[str]) -> List[Issue]:
    items = _strs(out.get("key_points")) + _strs(out.get("implications_for_founder"))
    marketing = [t for t in items if mentions_product(t, products)]
    if items and len(marketing) > len(items) / 2:
        return [_issue(role, "repeats-product-marketing", "medium",
                       "most points describe existing products rather than the topic",
                       "Answer the specialist questions for the founder's product.", "most points are about the topic",
                       ["key_points"])]
    return []


def financial(out: dict) -> List[Issue]:
    issues: List[Issue] = []
    rationale = str(out.get("rationale") or "")
    if rationale and INSTRUCTION_RX.search(rationale):
        issues.append(_issue("financial", "rationale-is-instruction", "medium",
                             "the rationale repeats an instruction instead of explaining the numbers",
                             "Explain in your own words why each key number was chosen.",
                             "rationale explains the assumptions", ["rationale"]))
    a = out.get("assumptions") if isinstance(out.get("assumptions"), dict) else {}
    overlap = [c.get("item") for c in a.get("startup_costs") or [] if isinstance(c, dict)
               and SALARY_RX.search(str(c.get("item", "")))]
    if overlap and a.get("team"):
        issues.append(_issue("financial", "cost-overlap", "medium",
                             "startup costs include salaries already counted in the team payroll: %s" % ", ".join(
                                 map(str, overlap)),
                             "Keep salaries in 'team' only; startup costs are one-off items.",
                             "no salary item in startup costs", ["startup_costs"]))
    return issues


def leaks_instruction(text: str) -> bool:
    return bool(INSTRUCTION_RX.search(text or ""))
