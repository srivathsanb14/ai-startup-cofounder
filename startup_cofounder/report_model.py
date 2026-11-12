"""Canonical, validated report data model (schema "report-v3").

One function, `build(assessment_dict)`, turns a saved or freshly produced assessment (adaptive-v2 or v3 JSON) into the
model that the Markdown memo, the evidence appendix, the Streamlit UI and the JSON download all render. Corrections
happen HERE, deterministically, so every output agrees by construction:

* financial headline statements are computed from the projection, never taken from model prose;
* founder targets ("break even in five years") are kept apart from what the scenario shows;
* claims are re-screened with current rules (downgrade only); rejected claims are removed from summaries too;
* competitor relations and identities are re-derived from evidence; missing information never becomes white space;
* product names are rejected as architecture; competitor prices are not willingness to pay;
* unknowns carry why they matter, what is / is not established, and a next action (web research or founder test);
* if critical problems remain, affected conclusions are withheld and the assessment is marked incomplete.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

from . import claims as claimlib
from . import final_review, identity, substance, validators
from .relevance import GENERIC, RelevanceBook, ResearchFrame, terms

SCHEMA = "report-v3"
VENUE_WORDS = ("gym", "club", "court", "studio", "venue", "campus", "office", "school", "park", "store", "restaurant",
               "clinic", "library", "field", "center", "centre")
MATCHING_RX = re.compile(r"\b(match|matching|partner|partners|meet|connect|connecting|pair|buddy|social)\b", re.I)
FORUM_HOSTS = ("reddit.com", "facebook.com", "meetup.com", "mountainproject.com", "discord", "forum", "groups.")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------- formatting helpers
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


def domain(url: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def short(text, limit: int = 140) -> str:
    """Shorten at a sentence or word boundary; never mid-word."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    if end > limit // 2:
        return cut[:end + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


def _strs(items) -> List[str]:
    return [str(i).strip() for i in items if str(i).strip() and str(i).strip().lower() not in ("n/a", "none", "null")] \
        if isinstance(items, list) else []


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in SENT_SPLIT.split(str(text or "")) if s.strip()]


def _jaccard(a: str, b: str) -> float:
    ta, tb = terms(a) - GENERIC, terms(b) - GENERIC
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


class _Ctx:
    def __init__(self, d: dict) -> None:
        from .audit import ledger_from_sources
        self.d = d
        self.frame = ResearchFrame.from_plan(d.get("plan", {}), d.get("idea", ""))
        self.ledger = ledger_from_sources(d.get("sources", []))
        self.book = RelevanceBook(self.frame)
        self.src = {s["id"]: s for s in d.get("sources", [])}
        self.corrections: List[dict] = []
        self.unknowns: List[dict] = []
        self.withheld: List[str] = []

    def out(self, role: str) -> dict:
        a = self.d.get("agents", {}).get(role) or {}
        return a.get("output") or {}

    def correct(self, section: str, what: str, before: str = "", after: str = "") -> None:
        self.corrections.append({"section": section, "correction": what, "before": short(before, 200),
                                 "after": short(after, 200)})

    def unknown(self, what, why, established, not_established, action, action_type, key=None, priority=2) -> None:
        if any(u["key"] == (key or what) for u in self.unknowns):
            return
        self.unknowns.append({"key": key or what, "what": what, "why": why, "established": established,
                              "not_established": not_established, "next_action": action,
                              "action_type": action_type, "priority": priority})

    def cite(self, ids: Sequence[str], text: str = "", k: int = 3) -> List[dict]:
        """At most k readable citations, most relevant first (full provenance stays in the appendix)."""
        cands = []
        for i in dict.fromkeys(ids or []):
            s = self.src.get(i)
            if not s:
                continue
            rel = (s.get("relevance") or {}).get("score")
            if rel is None:
                src = self.ledger.get(i)
                rel = self.book.of(src).score if src else 0
            overlap = len((terms(text) - GENERIC) & terms(s.get("title", "") + " " + s.get("snippet", ""))) if text else 0
            cands.append((overlap, rel, i, s))
        cands.sort(key=lambda c: (-c[0], -c[1]))
        out, seen = [], set()
        for _, _, i, s in cands:
            url = s.get("url", "").split("#p")[0]
            if url in seen:
                continue
            seen.add(url)
            out.append({"id": i, "url": url, "label": domain(url) or i})
            if len(out) >= k:
                break
        return out


# ---------------------------------------------------------------- claims
def _claims(ctx: _Ctx, comps: List[dict]) -> List[dict]:
    out = []
    domains = {identity._clean_name(c.get("name", "")): c.get("official_domain") for c in comps if c.get("official_domain")}
    for c in ctx.d.get("claims", []):
        c2 = claimlib.rescreen(c, ctx.frame)
        if c2.get("rescreen"):
            ctx.correct(c2.get("section", "?"), "claim downgraded on re-screen: " + "; ".join(c2["rescreen"]),
                        c.get("text", ""), c2["status"])
        c2.setdefault("claim_type", "external_fact")
        cited_domains = {domain(ctx.src.get(i, {}).get("url", "")) for i in c2.get("source_ids", []) if i in ctx.src}
        for name, dom in domains.items():
            if dom and name and name in c2.get("text", "").lower() and cited_domains and cited_domains <= {dom}:
                c2["claim_type"] = "source_reported"  # a vendor describing itself
        if c2.get("section") == "technical" and c2.get("status") in ("unsupported", "explicit_assumption"):
            c2["claim_type"] = "proposal"
        if c2.get("status") == "explicit_assumption" and c2["claim_type"] == "external_fact":
            c2["claim_type"] = "assumption"
        out.append(c2)
    return out


def _rejected(claims: List[dict]) -> List[dict]:
    return [c for c in claims if c.get("status") in ("unsupported", "contradicted") and c.get("kind", "fact") == "fact"
            and c.get("claim_type") not in ("proposal", "assumption")]


def scrub(ctx: _Ctx, section: str, text: str, rejected: List[dict], local_growth_ok: bool = False) -> str:
    """Remove sentences that restate a rejected claim, or assert local growth/demand without local evidence."""
    keep = []
    for sent in _sentences(text):
        hit = next((c for c in rejected if _jaccard(sent, c.get("text", "")) >= 0.5), None)
        local = (substance.GROWTH_RX.search(sent) and (ctx.frame.geo_terms and ctx.frame.geo_terms <= terms(sent)
                                                       or "local" in sent.lower()) and not local_growth_ok)
        if hit is not None:
            ctx.correct(section, "removed a sentence that restates a rejected claim (%s)" % hit.get("id"), sent)
        elif local:
            ctx.correct(section, "removed local growth/demand assertion without local evidence", sent)
        else:
            keep.append(sent)
    return " ".join(keep)


def _evidence_items(ctx: _Ctx, claims: List[dict], section: str, k: int = 4) -> List[dict]:
    """Best observed evidence for a memo section: supported first, then partial; vendors' self-claims labelled."""
    pool = [c for c in claims if c.get("section") == section and c.get("status") in ("supported", "partially_supported")
            and c.get("claim_type") in ("external_fact", "source_reported") and not claimlib.is_question(c.get("passage", ""))]
    pool.sort(key=lambda c: (c.get("status") != "supported", c.get("claim_type") == "source_reported",
                             -(c.get("validation") or {}).get("independent_domains", 0)))
    out, seen = [], []
    for c in pool:
        if any(_jaccard(c.get("text", ""), s) >= 0.6 for s in seen):
            continue
        seen.append(c.get("text", ""))
        out.append({"text": c.get("text", ""), "status": c["status"], "type": c.get("claim_type"),
                    "flags": [f for f in (c.get("validation") or {}).get("flags", [])
                              if not f.startswith("vendor's own claim")],
                    "cites": ctx.cite(c.get("source_ids", []), c.get("text", ""), 2), "claim_id": c.get("id")})
        if len(out) >= k:
            break
    return out


# ---------------------------------------------------------------- sections
def _competition(ctx: _Ctx, claims: List[dict]) -> dict:
    out = ctx.out("competitor")
    all_ids = [s.id for s in ctx.ledger.all()]
    rows, unknowns_c = [], []
    for c in out.get("competitors", []) or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        before = c.get("relation")
        c2 = identity.classify(dict(c), c["name"], ctx.ledger, ctx.book, all_ids)
        if before and c2["relation"] != before:
            ctx.correct("competition", "%s re-classified %s -> %s (%s)" % (c["name"], before, c2["relation"],
                                                                         c2.get("identity_note", "")))
        if before and c.get("verified") and not c2["verified"]:
            ctx.correct("competition", "%s no longer counted: %s" % (c["name"], c2.get("identity_note", "")))
        weak = [w for w in _strs(c.get("weaknesses")) if not substance.UNKNOWN_RX.search(w)]
        if len(weak) < len(_strs(c.get("weaknesses"))):
            ctx.correct("competition", "%s: 'weakness' that only states missing information removed" % c["name"],
                        "; ".join(_strs(c.get("weaknesses"))))
        c2["weaknesses"] = weak
        price = re.sub(r"^(yes|no)[.,]\s*", "", str(c.get("pricing") or ""), flags=re.I).strip()
        if not re.search(r"\d|free", price, re.I) or claimlib.is_question(price):
            price = "not stated in sources"
        elif not re.search(r"\d", price) and re.search(r"free", price, re.I):
            price = "free basic use" + ("; paid plan (price not stated)" if re.search(
                r"pro|premium|paid|plan|subscription", price, re.I) else "")
        c2["price_short"] = short(price, 90)
        rows.append(c2)
    # non-app alternatives that the evidence shows people use (forums, groups)
    forum_ids = [s["id"] for s in ctx.d.get("sources", []) if any(h in s.get("url", "") for h in FORUM_HOSTS)
                 and (s.get("relevance") or {}).get("label") in ("relevant", "weak")
                 and ctx.frame.need & terms(s.get("title", "") + " " + s.get("snippet", ""))]
    if forum_ids:
        rows.append({"name": "Online forums and community groups", "relation": "substitute", "verified": True,
                     "description": "Public threads and groups where people ask for this (e.g. %s)" % ", ".join(
                         sorted({domain(ctx.src[i]["url"]) for i in forum_ids[:6]})[:2]),
                     "price_short": "free", "identity_source_ids": forum_ids, "non_app": True,
                     "identity_note": "threads asking for this exist in the evidence; usage level unknown"})
    for r in rows:
        ids = list(r.get("identity_source_ids") or [])
        own = [i for i in ids if r.get("official_domain") and domain(ctx.src.get(i, {}).get("url", "")) ==
               r.get("official_domain")]
        r["cites"] = ctx.cite(own or ids, r["name"] + " " + str(r.get("description", "")), 2)
    counted = [r for r in rows if r.get("verified") and r.get("relation") in identity.COUNTED]
    rank = {"direct": 0, "substitute": 1, "adjacent": 2}
    counted.sort(key=lambda r: rank.get(r["relation"], 3))
    ws = str(out.get("white_space") or "")
    if ws and substance.UNKNOWN_RX.search(ws):
        ctx.correct("competition", "missing information was presented as white space; moved to unknowns", ws)
        unknowns_c.append(ws)
        ws = ""
    unknowns_c += _strs(out.get("unknowns"))
    diff = str(out.get("differentiation") or "").strip()
    status = str(out.get("differentiation_status") or "hypothesis")
    if status == "established" and not any(_strs(c.get("verified_differences")) for c in counted):
        status = "hypothesis"
        ctx.correct("competition", "differentiation re-labelled hypothesis: no verified difference recorded")
    direct = [r["name"] for r in counted if r["relation"] == "direct"]
    if direct:
        ctx.unknown("Why someone would switch from %s" % ", ".join(direct[:3]),
                    "Direct alternatives already address the same need; without a reason to switch, adoption stalls.",
                    "These products exist and describe the same need.",
                    "Whether their users are dissatisfied, and with what.",
                    "Ask 8-10 current users of these alternatives what fails for them; compare features side by side.",
                    "founder", key="switch", priority=1)
    for u in unknowns_c:
        ctx.unknown(short(u, 120), "Competitor facts drive differentiation and pricing.", "", "Not stated in sources.",
                    "Check the product's own site and app-store listing.", "web research", key="cu:" + u[:40], priority=3)
    return {"rows": counted, "unresolved": [r for r in rows if r not in counted and r.get("relation") != "irrelevant"],
            "rejected": [r for r in rows if r.get("relation") == "irrelevant"] + list(out.get("rejected") or []),
            "differentiation": diff, "differentiation_status": status, "white_space": ws,
            "switch_reasons": _strs(out.get("switch_reasons")), "evidence": _evidence_items(ctx, claims, "competitor", 3)}


def _customer(ctx: _Ctx, claims: List[dict], products: List[str], comp_prices: List[str]) -> dict:
    out = ctx.out("customer")
    segs = [s for s in out.get("segments") or [] if isinstance(s, dict)]
    target = str(out.get("target_segment") or "").strip()
    problem = str(out.get("problem") or "").strip()
    if not target and segs:
        target = "%s: %s" % (segs[0].get("name", ""), segs[0].get("description", ""))
    if not problem and segs:
        problem = "; ".join(_strs(segs[0].get("pain_points")))
    named = substance.mentions_product(target + " " + str(out.get("summary") or ""), products)
    who = ctx.d.get("plan", {}).get("customer_type") or ctx.d.get("plan", {}).get("idea_summary") or "the intended users"
    geo = ctx.frame.geography or "the launch area"
    if named:
        ctx.correct("customer", "segment described users of %s, not prospective customers; segment withheld"
                    % ", ".join(sorted(set(named))), target)
        target = ""
    if not target:
        ctx.unknown("Initial target segment", "It decides channels, features and pricing.",
                    "The idea names a broad group (%s)." % short(who[:1].lower() + who[1:], 90),
                    "Which sub-group feels the problem most and can be reached first.",
                    "Interview 10-15 people from that group in %s; ask when the problem last happened and what they "
                    "did." % geo, "founder", key="segment", priority=1)
    wtp = str(out.get("willingness_to_pay") or (segs[0].get("willingness_to_pay") if segs else "") or "").strip()
    wtp_is_price = bool(wtp) and not substance.UNKNOWN_RX.search(wtp) and (
        substance.mentions_product(wtp, products) or any(_jaccard(wtp, p) >= 0.4 for p in comp_prices)
        or re.search(r"\b(free to use|pro plan|premium plan|plan is available)\b", wtp, re.I))
    if wtp_is_price:
        ctx.correct("customer", "competitor pricing was presented as willingness to pay; moved to competition", wtp,
                    "unknown")
        wtp = ""
    if not wtp or substance.UNKNOWN_RX.search(wtp) or re.search(r"moderate|high|low|depend", wtp, re.I) and not \
            re.search(r"\d", wtp):
        if wtp:
            ctx.correct("customer", "non-quantified willingness to pay treated as unknown", wtp, "unknown")
        wtp = ""
        ctx.unknown("Willingness to pay for this product", "Price and conversion decide whether the business can "
                    "cover its costs.", "Competitor prices show what alternatives charge.",
                    "What these customers would pay for this product, and how many would.",
                    "Run a pricing test: landing page with two price points and a pre-order or waitlist button.",
                    "founder", key="wtp", priority=1)
    workarounds = _strs(out.get("current_workarounds"))
    if not workarounds:
        ctx.unknown("Current workaround", "The workaround is the real competitor and sets the bar.", "",
                    "How people solve this today and how well it works.",
                    "Search community forums for how people currently solve it; confirm in interviews.",
                    "web research + founder", key="workaround", priority=2)
    freq = str(out.get("frequency") or "").strip()
    if not freq or substance.UNKNOWN_RX.search(freq):
        freq = ""
        ctx.unknown("How often the problem occurs", "A rare problem does not sustain an app habit.", "",
                    "Frequency and severity for the target group.", "Ask in interviews: 'when did this last happen?'",
                    "founder", key="frequency", priority=2)
    channels = _strs(out.get("reach_channels"))
    if not channels:
        ctx.unknown("How to reach early users", "Acquisition cost depends on a reachable channel.", "",
                    "Which channel brings sign-ups at what cost.",
                    "Test 2 channels (e.g. community posts, venue flyers) with a sign-up form; record cost per sign-up.",
                    "founder", key="channel", priority=2)
    evidence = [e for e in _evidence_items(ctx, claims, "customer", 4)
                if not substance.mentions_product(e["text"], products)]  # product facts belong to competition
    forum = [s for s in ctx.d.get("sources", []) if any(h in s.get("url", "") for h in FORUM_HOSTS)
             and (s.get("relevance") or {}).get("label") in ("relevant", "weak")
             and ctx.frame.need & terms(s.get("title", "") + " " + s.get("snippet", ""))]
    if forum:
        evidence.append({"text": "People publicly ask for help with this problem in community threads (%d found); this "
                                 "shows the need exists, not how common it is." % len(forum),
                         "status": "supported", "type": "external_fact",
                         "cites": ctx.cite([s["id"] for s in forum], "", 2), "claim_id": None})
    return {"target": target, "problem": problem, "frequency": freq, "workarounds": workarounds,
            "unmet_need": str(out.get("unmet_need_evidence") or ""), "wtp": wtp, "channels": channels,
            "evidence": evidence}


def _market(ctx: _Ctx, claims: List[dict], rejected: List[dict]) -> dict:
    out = ctx.out("market")
    geo = ctx.frame.geography or "the launch area"
    local_backed = any(c.get("status") in ("supported", "partially_supported") and ctx.frame.geo_terms and
                       ctx.frame.geo_terms <= terms(c.get("passage", "")) and substance.GROWTH_RX.search(c.get("text", ""))
                       for c in claims if c.get("section") == "market")
    summary = scrub(ctx, "market", str(out.get("summary") or ""), rejected, local_backed)
    trends = [t for t in (scrub(ctx, "market", t, rejected, local_backed) for t in _strs(out.get("trends"))) if t]
    inputs = [i for i in out.get("inputs") or [] if isinstance(i, dict)]
    known = {str(i.get("name", "")).lower(): i for i in inputs if i.get("value") not in (None, "", 0)}
    venue = next((w for w in VENUE_WORDS if re.search(r"\b%ss?\b" % w, ctx.d.get("idea", ""), re.I)), "venue")
    fin_in = {i["name"]: i for i in ctx.d.get("financial_inputs", [])}
    price = fin_in.get("arpu_monthly", {})
    formula = [
        ("Active local participants", "people in %s who do the activity regularly" % geo,
         "Ask %s operators for active-member counts; search for published local membership figures." % venue),
        ("Share with the problem", "share who face the problem at least monthly",
         "Short survey at 2-3 %ss (founder)." % venue),
        ("Share reachable in year 1", "share the founder can reach and sign up", "Channel test with a sign-up form."),
        ("Paying share", "share of active users who pay", "Pricing test (pre-order or waitlist with price)."),
        ("Monthly price", "USD per paying user per month", "Pricing test; the model's price is an assumption."),
    ]
    rows = []
    for name, meaning, how in formula:
        match = next((v for k, v in known.items() if _jaccard(k, name) >= 0.3), None)
        if name == "Monthly price" and price:
            rows.append({"input": name, "meaning": meaning, "value": "$%g (%s)" % (price.get("value", 0),
                                                                                  price.get("status", "").replace("_", " ")),
                         "how": how})
        elif match is not None:
            rows.append({"input": name, "meaning": meaning, "value": "%s %s" % (match.get("value"), match.get("unit", "")),
                         "how": "cited: " + ", ".join(match.get("source_ids") or []) or how})
        else:
            rows.append({"input": name, "meaning": meaning, "value": "missing", "how": how})
    missing = [r["input"] for r in rows if r["value"] == "missing"]
    if missing:
        ctx.unknown("Size of the reachable %s market" % geo, "Shows whether the launch area can support the business.",
                    "The formula and which inputs are needed.", "Missing inputs: %s." % ", ".join(missing),
                    "Collect the missing inputs as listed in the market table (venue counts first).",
                    "web research + founder", key="market", priority=2)
    tss = out.get("tam_sam_som") if isinstance(out.get("tam_sam_som"), dict) else {}
    vals = [tss.get(k) for k in ("tam_usd", "sam_usd", "som_usd")]
    sizes_valid = all(isinstance(v, (int, float)) and v > 0 for v in vals) and vals[0] >= vals[1] >= vals[2] and \
        re.search(r"\d|E\d+", str(tss.get("method", "")))
    density = None
    if MATCHING_RX.search(ctx.d.get("idea", "")):
        density = ("Matching only works when enough active users share the same %s and time window. A useful launch "
                   "test: a minimum number of active users per %s per week (choose the number before testing, e.g. "
                   "enough for each user to see 3+ compatible options)." % (venue, venue))
        ctx.unknown("Active-user density per %s and time window" % venue,
                    "Too few users at the same place and time means no matches, whatever the total market size.",
                    "", "How many users per %s are needed and achievable." % venue,
                    "Concierge pilot at 1-2 %ss for 4 weeks: collect availability on a form, match by hand, count "
                    "successful sessions." % venue, "founder", key="density", priority=1)
    who = str(ctx.d.get("plan", {}).get("customer_type") or "target customers")
    return {"launch_market": str(out.get("launch_market") or "%s, %s" % (geo, short(who[:1].lower() + who[1:], 60))),
            "summary": summary, "trends": trends, "formula_rows": rows, "missing": missing,
            "sizes": {"tam": vals[0], "sam": vals[1], "som": vals[2], "method": tss.get("method")} if sizes_valid else None,
            "density": density, "evidence": _evidence_items(ctx, claims, "market", 3)}


def _mvp(ctx: _Ctx, products: List[str], risk_roles: List[str]) -> dict:
    out = ctx.out("technical")
    comps = [c for c in out.get("components") or [] if isinstance(c, dict) and c.get("name")]
    if not comps:
        comps = [{"name": n, "responsibility": "", "approach": ""} for n in _strs(out.get("key_components"))]
    good, bad = [], []
    for c in comps:
        nt = terms(c["name"]) - GENERIC
        is_cat = bool(nt) and nt <= (ctx.frame.core | ctx.frame.anchors | ctx.frame.geo_terms) and \
            re.search(r"\bapps?\b", c["name"], re.I)
        (bad if substance.mentions_product(c["name"], products) or is_cat else good).append(c)
    if bad:
        ctx.correct("mvp", "removed product/category names listed as architecture components",
                    ", ".join(c["name"] for c in bad))
    journey = _strs(out.get("user_journey"))
    effort = out.get("effort") if isinstance(out.get("effort"), dict) else {}
    effort_text = ""
    if effort.get("weeks_low") and good:
        effort_text = "%s-%s weeks with %s; scope: %s (engineering proposal, not verified)" % (
            effort.get("weeks_low"), effort.get("weeks_high", "?"), effort.get("team", "team not stated"),
            effort.get("scope", "not stated"))
    elif out.get("mvp_time_months") and good:
        effort_text = "~%s months with ~%s people (agent estimate without stated scope)" % (
            out.get("mvp_time_months"), out.get("mvp_team_size", "?"))
    elif out.get("mvp_time_months") or effort:
        ctx.correct("mvp", "effort estimate withheld: it was not tied to a component list",
                    "%s months" % out.get("mvp_time_months"))
    if not good or not journey:
        ctx.unknown("Minimum user journey and architecture", "Determines build cost, timeline and which risks matter.",
                    "", "A component list with responsibilities and build/buy choices was not produced.",
                    "Rerun the technical role (it now requires generic components), or sketch the journey: sign up -> "
                    "set availability -> see matches -> message -> meet.", "web research", key="arch", priority=3)
    risks = [{"risk": r.get("risk"), "control": r.get("mitigation", "")} for r in out.get("delivery_risks") or []
             if isinstance(r, dict) and r.get("risk")]
    risks += [{"risk": r, "control": "", "unvalidated": True} for r in _strs(out.get("main_risks"))]
    safety = []
    for role in risk_roles:
        ro = ctx.out(role)
        scen = [s for s in ro.get("scenarios") or [] if isinstance(s, dict) and s.get("scenario")]
        if scen:
            safety += [dict(s, area=role.replace("_", " ")) for s in scen]
        elif ro:
            ctx.correct("mvp", "%s section repeated product descriptions instead of risk analysis; not used"
                        % role.replace("_", " "), str(ro.get("summary", "")))
    if risk_roles and not safety:
        ctx.unknown("Safety and privacy risks", "A partner-matching or meeting product exposes users to strangers; "
                    "controls shape the MVP scope." if MATCHING_RX.search(ctx.d.get("idea", "")) else
                    "Risks shape MVP scope and obligations.",
                    "", "No concrete misuse scenario was analysed.",
                    "Analyse: who can see location and availability, unwanted contact, blocking/reporting, "
                    "moderation, data minimisation, access, retention and deletion; check applicable law.",
                    "web research", key="safety", priority=2)
    return {"journey": journey, "components": good, "rejected_components": [c["name"] for c in bad],
            "effort": effort_text, "risks": risks[:6], "safety": safety[:6],
            "feasibility": out.get("feasibility_score") if good else None}


def _economics(ctx: _Ctx, cust: dict) -> dict:
    d = ctx.d
    p = d.get("projection") or {}
    table = p.get("table") or []
    a = p.get("assumptions") or {}
    fin = (d.get("agents", {}).get("financial") or {}).get("output") or {}
    mode = d.get("financial_mode", "illustrative")
    inputs = d.get("financial_inputs") or []
    heads = []
    if table:
        last = table[-1]
        neg_all = all(r["operating_profit"] < 0 for r in table)
        first_pos = next((r["year"] for r in table if r["operating_profit"] > 0), None)
        heads.append("Operating result: %s (year 5: %s on revenue of %s from %s paying customers)." % (
            "negative in every year" if neg_all else "first positive in year %d" % first_pos,
            money(last["operating_profit"]), money(last["revenue"]), "{:,.0f}".format(last["customers_end"])))
        heads.append("Operating break-even: %s." % ("year %d" % p["breakeven_year"] if p.get("breakeven_year")
                                                     else "not reached within 5 years"))
        heads.append("Cumulative cash payback: %s." % ("year %d" % p["payback_year"] if p.get("payback_year")
                                                        else "not reached within 5 years"))
        heads.append("Funding requirement (deepest cumulative cash deficit): %s." % money(p.get("peak_funding_need")))
    payroll_y1 = table[0]["payroll"] if table else 0
    marketing_y1 = table[0]["marketing"] if table else 0
    startup = a.get("startup_costs") or []
    overlap = [c for c in startup if substance.SALARY_RX.search(str(c.get("item", "")))]
    drivers = []
    if table:
        total_y1 = table[0]["cogs"] + marketing_y1 + payroll_y1 + table[0]["other_opex"]
        drivers.append("Payroll %s/yr (%.0f%% of year-1 costs) - %s" % (
            money(payroll_y1), 100 * payroll_y1 / total_y1 if total_y1 else 0,
            ", ".join("%d %s" % (m["count"], m["role"]) for m in a.get("team", []))))
        drivers.append("Acquisition %s in year 1 (%s per paying customer, assumed)" % (money(marketing_y1),
                                                                                      money(a.get("cac"))))
        drivers.append("One-off startup costs %s" % money(sum(c.get("amount", 0) for c in startup)))
    if overlap:
        ctx.correct("economics", "startup costs include salaries already in payroll (double count of %s)"
                    % money(sum(c.get("amount", 0) for c in overlap)), ", ".join(c["item"] for c in overlap))
    lean = sum(c.get("amount", 0) for c in startup if c not in overlap) + marketing_y1
    rationale = str(fin.get("rationale") or "")
    if substance.leaks_instruction(rationale):
        ctx.correct("economics", "removed rationale text that was an instruction, not an explanation", rationale)
        rationale = ""
    labels = {"arpu_monthly": "price", "year1_new_customers": "year-1 paying customers", "growth_rate": "growth",
              "annual_churn": "churn", "cogs_pct": "cost of revenue", "cac": "acquisition cost"}
    assumed = [labels.get(i["name"], i["name"]) for i in inputs if i.get("status") not in ("supported",
                                                                                           "partially_supported")]
    credible = mode == "evidence_backed" and not assumed
    targets = final_review.founder_targets(d.get("synthesis") or {})
    target_rows = []
    for t in targets:
        if re.search(r"margin[^.]{0,40}?\b(\d{3,})\s*%|\b(\d{3,})\s*%[^.]{0,30}margin", t, re.I) and any(
                int(x) > 100 for x in re.findall(r"(\d+)\s*%", t)):
            ctx.correct("economics", "dropped a target with an impossible margin (above 100%; dollars and percentages "
                        "were confused)", t)
            continue
        shows = []
        m_cust = re.search(r"([\d,]{3,})\s+(?:paying\s+)?(?:customers|users|subscribers)", t, re.I)
        if m_cust and table:
            shows.append("%s paying customers at the end of year 1 (target %s)" % (
                "{:,.0f}".format(table[0]["customers_end"]), m_cust.group(1)))
        if final_review.BREAKEVEN_RX.search(t):
            shows.append("break-even %s" % ("in year %d" % p["breakeven_year"] if p.get("breakeven_year") else
                                            "not within 5 years"))
        if final_review.PAYBACK_RX.search(t) or "cash" in t.lower():
            shows.append("payback %s" % ("in year %d" % p["payback_year"] if p.get("payback_year") else
                                         "not within 5 years"))
        target_rows.append({"target": t, "scenario_shows": "; ".join(shows) or "not modelled"})
    scen = []
    for name, sc in (d.get("scenarios") or {}).items():
        t = (sc.get("table") or [{}])[-1]
        scen.append({"name": name.replace("_", " "), "customers": t.get("customers_end", 0), "revenue": t.get("revenue", 0),
                     "operating": t.get("operating_profit", 0), "breakeven": sc.get("breakeven_year")})
    price_note = ""
    if not cust.get("wtp"):
        price_note = "The modelled price ($%g/month) is an assumption; willingness to pay is unknown." % a.get(
            "arpu_monthly", 0)
    return {"payer": fin.get("payer") or ("individual users (assumed)" if ctx.frame.payer == "consumer" else
                                          "businesses (assumed)"),
            "price_basis": fin.get("price_basis") or price_note, "rationale": rationale, "mode": mode,
            "headlines": heads, "scenarios": scen, "drivers": drivers, "lean_cost": lean,
            "overlap": [c["item"] for c in overlap], "credible": credible, "assumed_inputs": assumed,
            "targets": target_rows, "price": a.get("arpu_monthly"), "inputs": inputs, "projection": p,
            "unit_economics": d.get("unit_economics") or {}}


def _validation_plan(ctx: _Ctx, comp: dict, econ: dict) -> List[dict]:
    """Most critical hypotheses first. Thresholds are PROPOSED decision rules, not benchmarks."""
    geo = ctx.frame.geography or "the launch area"
    venue = next((w for w in VENUE_WORDS if re.search(r"\b%ss?\b" % w, ctx.d.get("idea", ""), re.I)), "venue")
    problem = ctx.d.get("plan", {}).get("problem") or "the problem"
    direct = [r["name"] for r in comp["rows"] if r["relation"] == "direct"][:2]
    plan = [
        {"hypothesis": "People in the target group in %s run into '%s' often enough to want a dedicated tool."
                       % (geo, short(problem, 80)), "category": "desirability", "owner": "founder",
         "test": "15 short interviews at 2-3 %ss; ask about the last time it happened and what they did." % venue,
         "metric": "share who had the problem in the last month and used a workaround",
         "threshold": "proposed: at least 6 of 15", "time_cost": "2 weeks, under $100",
         "pass_rule": "6 or more of 15 interviewees had the problem in the last month",
         "if_pass": "test density and price", "if_fail": "narrow the segment or stop"},
    ]
    if MATCHING_RX.search(ctx.d.get("idea", "")):
        plan.append({"hypothesis": "Enough active users share the same %s and time windows for useful matches." % venue,
                     "category": "desirability/feasibility", "owner": "founder",
                     "test": "Concierge pilot: sign-up form at 1-2 %ss, match by hand for 4 weeks." % venue,
                     "metric": "share of sign-ups who complete a session with a match",
                     "threshold": "proposed: at least 30% within 2 weeks", "time_cost": "4 weeks, under $200",
                     "pass_rule": "30% or more of sign-ups complete a matched session within 2 weeks",
                     "if_pass": "build the minimum journey", "if_fail": "focus on one %s or widen time windows" % venue})
    plan.append({"hypothesis": "Users will pay for the product at the modelled price ($%g/month)." % (econ.get("price") or 0),
                 "category": "viability", "owner": "founder",
                 "test": "Landing page with two price points and a pre-order/waitlist button, promoted in 2 channels.",
                 "metric": "visitors choosing a paid option; cost per sign-up",
                 "threshold": "proposed: at least 5% choose a paid option", "time_cost": "2-3 weeks, $100-300",
                 "pass_rule": "5% or more of visitors choose a paid option",
                 "if_pass": "use the measured price and conversion in the model",
                 "if_fail": "test a free model with another payer (e.g. %ss) or stop" % venue})
    if direct:
        plan.append({"hypothesis": "Users would switch from %s for a specific reason." % " and ".join(direct),
                     "category": "desirability", "owner": "founder",
                     "test": "Ask 8-10 users of these products what fails for them; compare features side by side.",
                     "metric": "repeated, specific complaint the new product can fix",
                     "threshold": "proposed: the same complaint from at least 4 of 10",
                     "time_cost": "1-2 weeks, no cost", "if_pass": "make it the core differentiator",
                     "pass_rule": "4 or more of 10 users give the same specific complaint",
                     "if_fail": "partner with or build on an existing product instead"})
    plan.append({"hypothesis": "Local market inputs (participants, %ss) are large enough for the plan." % venue,
                 "category": "viability", "owner": "software",
                 "test": "Search for published participant/membership counts and %s listings in %s." % (venue, geo),
                 "metric": "sourced counts for each market input", "threshold": "all inputs sourced or marked unknown",
                 "time_cost": "a short research run", "if_pass": "compute the bottom-up market estimate",
                 "if_fail": "ask %s operators directly (founder)" % venue})
    return plan


def _verifier_reliability(d: dict) -> dict:
    """Control-probe results recorded during the run (absent for runs made before v3.1)."""
    probes = [t for t in d.get("trace", []) if t.get("type") == "claim_check" and "control" in t]
    if not probes:
        return {"status": "not measured in this run"}
    failed = [p for p in probes if p["control"] == "failed"]
    return {"status": "unreliable in %d of %d batches" % (len(failed), len(probes)) if failed else
            "passed all %d control probes" % len(probes), "batches": len(probes), "failed": len(failed)}


# ---------------------------------------------------------------- decision
def build(d: dict, regenerated: bool = False) -> dict:
    ctx = _Ctx(d)
    comp_out = ctx.out("competitor")
    products = [c.get("name") for c in (comp_out.get("competitors") or []) + (comp_out.get("rejected") or [])
                if isinstance(c, dict) and c.get("name")]
    comp_prices = [str(c.get("pricing")) for c in comp_out.get("competitors") or [] if isinstance(c, dict)
                   and c.get("pricing")]
    competition = _competition(ctx, [])
    claims = _claims(ctx, competition["rows"])
    # layer: source credibility, independence, recency (downgrade only)
    vendors = validators.vendor_domains(list(competition["rows"]) + list(comp_out.get("competitors") or []))
    for c in claims:
        res = validators.assess_claim(c, ctx.src, vendors)
        c["validation"] = res
        if res["downgraded"]:
            ctx.correct(c.get("section", "?"), "claim downgraded: " + "; ".join(res["flags"]), c.get("text", ""),
                        res["status_after"])
            c["status"] = res["status_after"]
        if any(f.startswith("vendor's own claim") for f in res["flags"]) and c.get("claim_type") == "external_fact":
            c["claim_type"] = "source_reported"
    profile = validators.source_profile(claims, ctx.src, vendors)
    if profile["vendor_share"] > 0.5:
        ctx.unknown("Independent evidence", "Most supported claims come from the competitors' own websites (%.0f%% of "
                    "citations), which describe themselves favourably." % (100 * profile["vendor_share"]),
                    "What the products say about themselves.", "Independent confirmation (users, press, data).",
                    "Search app-store reviews, forums and local press for independent accounts.", "web research",
                    key="independent", priority=2)
    competition["evidence"] = _evidence_items(ctx, claims, "competitor", 3)
    rejected = _rejected(claims)
    customer = _customer(ctx, claims, products, comp_prices)
    market = _market(ctx, claims, rejected)
    extra = d.get("extra_roles") or []
    from .agents.specs import is_risk_role
    risk_roles = [r for r in extra if is_risk_role(r)]
    mvp = _mvp(ctx, products, risk_roles)
    econ = _economics(ctx, customer)
    fin_out = ctx.out("financial")
    plaus = validators.plausibility(econ["projection"].get("assumptions") or {}, ctx.frame.payer,
                                    fin_out.get("paying_share_of_active"))
    consist = validators.consistency(econ["projection"], market["formula_rows"], competition["rows"], customer["wtp"],
                                     str(fin_out.get("plan_type") or ""),
                                     (econ["projection"].get("assumptions") or {}).get("team") or [])
    plan = _validation_plan(ctx, competition, econ)
    syn = d.get("synthesis") or {}

    # synthesizer prose is used only after the same checks: financial statements, rejected claims, local growth
    fin_bad = final_review.financial_statements(syn, econ["projection"])
    for iss in fin_bad:
        ctx.correct("decision", "removed a statement that contradicts the financial model: " + iss.message,
                    next((h.get("sentence") for h in iss.history if h.get("sentence")), ""))
    bad_sentences = {h.get("sentence") for i in fin_bad for h in i.history if h.get("sentence")}

    def clean(text: str, section: str = "decision") -> str:
        kept = [s for s in _sentences(text) if s not in bad_sentences and not any(s in b for b in bad_sentences)]
        return scrub(ctx, section, " ".join(kept), rejected)

    reasons = [r for r in (clean(x) for x in _strs(syn.get("reasons"))) if r]
    if not reasons:  # computed reasons, each tied to a section of this report
        if competition["rows"]:
            direct = [r["name"] for r in competition["rows"] if r["relation"] == "direct"]
            reasons.append("Direct alternatives already exist (%s); a reason to switch is not yet established."
                           % ", ".join(direct) if direct else "Substitutes exist (%s)." % ", ".join(
                               r["name"] for r in competition["rows"][:3]))
        if not customer["wtp"]:
            reasons.append("Willingness to pay is unknown; the price in the model is an assumption.")
        if econ["headlines"]:
            reasons.append("The illustrative scenario %s." % (
                "does not reach operating break-even within 5 years" if not econ["projection"].get("breakeven_year")
                else "breaks even in year %d" % econ["projection"]["breakeven_year"]))
        if market["missing"]:
            reasons.append("Local market size is not established (%d of %d inputs missing)."
                           % (len(market["missing"]), len(market["formula_rows"])))
    uncertainties = sorted(ctx.unknowns, key=lambda u: u["priority"])
    would_change = [clean(x) for x in _strs(syn.get("would_change_if"))] or [
        "If %s: %s; if not: %s." % (v.get("pass_rule") or v["threshold"], v["if_pass"], v["if_fail"])
        for v in plan[:3] if v["owner"] == "founder"]

    status_exec = d.get("status", "complete")
    critical_unknown = [u for u in uncertainties if u["priority"] == 1]
    high_open = [i for i in d.get("issues", []) if i.get("severity") == "high" and i.get("status") in ("open", "unresolved")]
    inconsistent = [c for c in consist if c["result"] == "inconsistent"]
    adequacy = "insufficient" if len(critical_unknown) >= 2 else "partial" if (
        critical_unknown or high_open or inconsistent or profile["vendor_share"] > 0.5) else "adequate"
    verdict = d.get("verdict", "validate_first")
    if status_exec != "complete":
        ctx.withheld.append("go/no-go decision: research did not finish")
    if verdict in ("go", "no_go") and adequacy == "insufficient":
        ctx.withheld.append("'%s' verdict: evidence is insufficient for it" % verdict)
        ctx.correct("decision", "verdict '%s' replaced by 'validate first': evidence adequacy is insufficient" % verdict)
        verdict = "validate_first"
    rec = clean(str(syn.get("recommendation") or ""))
    if not rec:
        rec = {"validate_first": "Do not build yet. Spend the next 4-6 weeks on the founder tests in the validation "
                                 "plan: problem frequency, %swillingness to pay." % (
                                     "matching density and " if MATCHING_RX.search(d.get("idea", "")) else ""),
               "go": "Proceed to a pilot while running the validation tests below.",
               "pivot": "Rework the idea around the gaps identified below before testing.",
               "no_go": "Do not pursue this version of the idea.",
               "incomplete": "No recommendation: the research did not finish. Rerun before deciding."}.get(
            verdict, "Run the validation tests below before deciding.")
    for c in ctx.corrections:
        c.setdefault("type", "deterministic")
    model = {
        "schema": SCHEMA, "generated": date.today().isoformat(), "regenerated_from_saved_data": regenerated,
        "title": short(ctx.d.get("plan", {}).get("category") or "Startup idea", 60).title() + " - Founder Decision Memo",
        "idea": d.get("idea", ""), "idea_summary": d.get("plan", {}).get("idea_summary", ""),
        "source_run": {"created": d.get("created"), "workflow": d.get("workflow", "adaptive-v2"),
                       "models": (d.get("run_info") or {}).get("models", {})},
        "status": {"execution": status_exec, "evidence_adequacy": adequacy,
                   "critical_unknowns": [u["what"] for u in critical_unknown],
                   "high_issues_open": [i.get("message") for i in high_open], "withheld": ctx.withheld},
        "decision": {"verdict": verdict, "recommendation": rec, "reasons": reasons[:4],
                     "uncertainties": [u["what"] for u in uncertainties[:4]], "would_change": would_change[:3]},
        "customer": customer, "competition": competition, "market": market, "mvp": mvp, "economics": econ,
        "validation_plan": plan, "unknowns": uncertainties, "corrections": ctx.corrections,
        "claims": claims, "rejected_claim_ids": [c.get("id") for c in rejected],
        "validation": {"version": "v3.1", "sources": profile, "plausibility": plaus, "consistency": consist,
                       "claims_flagged": sum(1 for c in claims if (c.get("validation") or {}).get("flags")),
                       "claims_downgraded": sum(1 for c in claims if (c.get("validation") or {}).get("downgraded")),
                       "verifier": _verifier_reliability(d)},
    }
    return model
