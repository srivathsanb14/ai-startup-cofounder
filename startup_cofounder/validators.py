"""Additional validation layers (v3.1). All deterministic, no model calls, usable on live and saved runs.

1. Source credibility and independence: who is speaking (vendor about itself, app store, press, forum, reference,
   statistics aggregator, government/academic) and how many independent websites agree.
2. Recency: statistics resting only on old sources are flagged.
3. Plausibility: assumption values outside heuristic ranges for the payer type (labelled heuristics, not benchmarks).
4. Cross-section consistency: financial inputs against market, customer and competitor findings.
5. Publication gate: every number printed in the memo must trace to the validated report data.

Layers 1-2 only ever DOWNGRADE a claim's status; they never upgrade it.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

SOURCE_TYPES = ("government_academic", "research_firm", "news_editorial", "reference", "official_vendor", "app_store",
                "forum_community", "stats_aggregator", "blog_other")
CREDIBILITY = {"government_academic": "high", "research_firm": "medium", "news_editorial": "medium",
               "reference": "medium", "official_vendor": "self", "app_store": "self", "forum_community": "user_voice",
               "stats_aggregator": "low", "blog_other": "low"}
APP_STORES = ("apps.apple.com", "play.google.com", "appbrain.com", "apkpure.com", "apkmirror.com", "appadvice.com",
              "producthunt.com")
FORUMS = ("reddit.com", "facebook.com", "meetup.com", "quora.com", "discord", "mountainproject.com", "forum",
          "groups.", "community.", "stackexchange.com", "news.ycombinator.com", "ycombinator.com")
REFERENCE = ("wikipedia.org", "britannica.com", "wiktionary.org")
RESEARCH = ("ibisworld.com", "statista.com", "grandviewresearch.com", "mordorintelligence.com", "alliedmarketresearch.com",
            "fortunebusinessinsights.com", "marketsandmarkets.com", "precedenceresearch.com", "gartner.com",
            "mckinsey.com", "pewresearch.org", "nielsen.com")
NEWS = ("news.google.com", "nytimes.com", "wsj.com", "washingtonpost.com", "reuters.com", "apnews.com", "bbc.",
        "theguardian.com", "forbes.com", "techcrunch.com", "theverge.com", "cnbc.com", "bloomberg.com",
        "post-gazette.com", "triblive.com", "wesa.fm", "npr.org", "outsideonline.com", "climbing.com", "gripped.com",
        "ukclimbing.com", "self.com", "nbcnews.com", "cbsnews.com")
# Sites that mass-produce "statistics" or "pricing" pages without primary data (pattern-based, not a blocklist).
AGGREGATOR_RX = re.compile(r"(stat(istic)?s?|metrics|pricing|cost|compare|tiers|bench|rank|zipdo|gitnux|"
                           r"worldmetrics|enterpriseappstoday|demandsage|businessofapps)", re.I)
AGGREGATOR_TITLE_RX = re.compile(r"\b(\d+\+? )?(statistics|stats|facts|figures)\b.*\b(20\d\d)\b|\bpricing 20\d\d\b|"
                                 r"\breal costs?\b|\bwhat others paid\b|\bmarket report\b", re.I)
GOV_RX = re.compile(r"\.(gov|mil|edu|ac\.[a-z]{2}|int)$|\.gov\.[a-z]{2}$|\.edu\.[a-z]{2}$")
_YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")
_NUM = re.compile(r"\d[\d,]*\.?\d*")


COMMON_FIRST_WORDS = {"online", "local", "smart", "social", "daily", "great", "super", "happy", "global", "world",
                      "urban", "first", "best", "simple", "quick", "community", "indoor", "outdoor", "mobile", "digital",
                      "the", "open", "free", "united", "national", "american", "city", "metro"}


def host(url: str) -> str:
    try:
        h = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def vendor_domains(competitors: Iterable[dict]) -> Dict[str, str]:
    """domain/name-token -> competitor name, for recognising a company's own website."""
    out = {}
    for c in competitors or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        if c.get("official_domain"):
            out[c["official_domain"]] = c["name"]
        token = re.sub(r"[^a-z0-9]", "", str(c["name"]).lower())
        if len(token) >= 5:
            out["token:" + token] = c["name"]
        first = re.sub(r"[^a-z0-9]", "", str(c["name"]).lower().split()[0]) if str(c["name"]).split() else ""
        # a first word like "Climbing" (from "Climbing Buddy") would turn every climbing blog into a vendor site
        if len(first) >= 5 and not first.endswith("ing") and first not in COMMON_FIRST_WORDS:
            out["token:" + first] = c["name"]
    return out


def classify_source(src: dict, vendors: Dict[str, str]) -> str:
    h = host(src.get("url", ""))
    title = str(src.get("title", ""))
    if not h:
        return "blog_other"
    if GOV_RX.search(h):
        return "government_academic"
    if any(h == a or h.endswith("." + a) or a in h for a in APP_STORES):
        return "app_store"
    if any(f in h for f in FORUMS):
        return "forum_community"
    if any(r in h for r in REFERENCE):
        return "reference"
    if any(r in h for r in RESEARCH):
        return "research_firm"
    if any(n in h for n in NEWS):
        return "news_editorial"
    bare = h.replace("-", "").replace(".", "")
    for key, _ in vendors.items():
        if (key.startswith("token:") and key[6:] in bare) or (not key.startswith("token:") and (h == key or
                                                                                                h.endswith("." + key))):
            return "official_vendor"
    if AGGREGATOR_RX.search(h.split(".")[0]) or AGGREGATOR_TITLE_RX.search(title):
        return "stats_aggregator"
    return "blog_other"


def assess_claim(claim: dict, sources: Dict[str, dict], vendors: Dict[str, str],
                 today_year: Optional[int] = None) -> dict:
    """Credibility, independence and recency of one claim's support. Returns a dict of findings and the
    (possibly downgraded) status. Never upgrades."""
    today_year = today_year or date.today().year
    ids = [i for i in claim.get("source_ids") or [] if i in sources]
    types = {i: classify_source(sources[i], vendors) for i in ids}
    domains = {host(sources[i].get("url", "")) for i in ids}
    independent = {host(sources[i].get("url", "")) for i in ids if types[i] not in ("official_vendor", "app_store")}
    flags: List[str] = []
    status = claim.get("status")
    has_number = bool(re.search(r"\d", re.sub(_YEAR, "", claim.get("text", ""))))
    supported = status in ("supported", "partially_supported")
    if supported and ids:
        kinds = set(types.values())
        if kinds <= {"official_vendor", "app_store"}:
            flags.append("vendor's own claim: no independent source")
        if has_number and kinds <= {"stats_aggregator", "blog_other"}:
            flags.append("statistic only from low-credibility pages (aggregators/blogs)")
            if status == "supported":
                status = "partially_supported"
        if has_number and kinds <= {"forum_community"}:
            flags.append("figure only from forum posts")
            if status == "supported":
                status = "partially_supported"
        if len(domains) == 1 and claim.get("section") in ("market", "customer", "financial"):
            flags.append("single website")
        years = [int(y) for i in ids for y in _YEAR.findall(sources[i].get("snippet", "") + " " +
                                                             sources[i].get("title", ""))]
        if has_number and years and max(years) < today_year - 5:
            flags.append("dated: newest year in the source is %d" % max(years))
            if status == "supported":
                status = "partially_supported"
    credibility = "none"
    if ids:
        levels = [CREDIBILITY[t] for t in types.values()]
        credibility = ("high" if "high" in levels else "medium" if "medium" in levels else
                       "user_voice" if "user_voice" in levels else "self" if "self" in levels else "low")
    return {"source_types": sorted(set(types.values())), "domains": len(domains),
            "independent_domains": len(independent), "credibility": credibility, "flags": flags,
            "status_after": status, "downgraded": status != claim.get("status")}


def source_profile(claims: Sequence[dict], sources: Dict[str, dict], vendors: Dict[str, str]) -> dict:
    """Who the supported claims rest on, overall."""
    counts: Dict[str, int] = {}
    total = 0
    for c in claims:
        if c.get("status") not in ("supported", "partially_supported"):
            continue
        for i in c.get("source_ids") or []:
            if i in sources:
                t = classify_source(sources[i], vendors)
                counts[t] = counts.get(t, 0) + 1
                total += 1
    vendor = counts.get("official_vendor", 0) + counts.get("app_store", 0)
    return {"citations": total, "by_type": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "vendor_share": round(vendor / total, 2) if total else 0.0}


# ---------------------------------------------------------------- plausibility (heuristics)
HEURISTIC_NOTE = "heuristic range for a first check, not an industry benchmark"


def plausibility(assumptions: dict, payer: str, paying_share: Optional[float] = None) -> List[dict]:
    a = assumptions or {}
    out = []

    def add(name, value, rule, why, severity="warning"):
        out.append({"input": name, "value": value, "rule": rule, "why": why, "severity": severity,
                    "basis": HEURISTIC_NOTE})

    arpu = float(a.get("arpu_monthly") or 0)
    churn = float(a.get("annual_churn") or 0)
    if payer == "consumer" and arpu > 30:
        add("arpu_monthly", arpu, "consumer price above $30/month", "Few consumer apps sustain this price; it needs "
            "direct evidence from this customer group.")
    if payer == "business" and 0 < arpu < 10:
        add("arpu_monthly", arpu, "business price below $10/month", "Sales and support costs rarely fit this price.")
    if payer == "consumer" and 0 < churn < 0.3:
        add("annual_churn", churn, "consumer churn below 30%/year", "Consumer subscriptions usually lose customers "
            "faster; low churn flatters lifetime value.")
    if churn >= 0.95:
        add("annual_churn", churn, "churn at or above 95%/year", "Almost every customer leaves within a year.")
    if float(a.get("cac") or 0) <= 0:
        add("cac", a.get("cac"), "zero acquisition cost", "Even organic growth costs time or money.")
    if float(a.get("growth_rate") or 0) > 2:
        add("growth_rate", a.get("growth_rate"), "new customers more than triple every year", "Sustained only with "
            "strong evidence of demand and a scalable channel.")
    if float(a.get("cogs_pct") or 0) > 0.6:
        add("cogs_pct", a.get("cogs_pct"), "cost of revenue above 60% for software", "Unusual for software; check "
            "what is counted.", "note")
    if paying_share is not None and payer == "consumer" and paying_share > 0.2:
        add("paying_share_of_active", paying_share, "more than 20% of active consumers pay", "Freemium consumer apps "
            "usually convert a much smaller share.")
    return out


# ---------------------------------------------------------------- cross-section consistency
def consistency(projection: dict, market_rows: Sequence[dict], competitors: Sequence[dict], wtp: str,
                plan_type: str = "", team: Sequence[dict] = ()) -> List[dict]:
    out = []
    table = projection.get("table") or []
    a = projection.get("assumptions") or {}
    y1 = table[0]["customers_end"] if table else 0
    participants = None
    for r in market_rows or []:
        if r.get("input", "").lower().startswith("active local") and r.get("value") not in (None, "missing"):
            m = _NUM.search(str(r["value"]))
            participants = float(m.group().replace(",", "")) if m else None
    if participants:
        if y1 > 0.25 * participants:
            out.append({"check": "year-1 paying customers vs local participants", "result": "inconsistent",
                        "detail": "%s paying customers in year 1 is more than a quarter of %s local participants"
                                  % ("{:,.0f}".format(y1), "{:,.0f}".format(participants))})
        else:
            out.append({"check": "year-1 paying customers vs local participants", "result": "consistent",
                        "detail": "%s of %s" % ("{:,.0f}".format(y1), "{:,.0f}".format(participants))})
    else:
        out.append({"check": "year-1 paying customers vs local participants", "result": "not checkable",
                    "detail": "local participant count is unknown, so %s year-1 paying customers cannot be checked "
                              "against the market" % "{:,.0f}".format(y1)})
    direct = [c for c in competitors if c.get("relation") == "direct"]
    free = [c["name"] for c in direct if "free" in str(c.get("price_short", "")).lower()]
    if free and float(a.get("arpu_monthly") or 0) > 0:
        out.append({"check": "modelled price vs direct alternatives", "result": "tension",
                    "detail": "the model charges $%g/month while %s can be used free; paying needs a clear reason to "
                              "switch" % (a.get("arpu_monthly"), ", ".join(free))})
    if not wtp:
        out.append({"check": "modelled price vs willingness to pay", "result": "not checkable",
                    "detail": "willingness to pay is unknown"})
    if plan_type == "lean_validation" and any(float(m.get("annual_salary") or 0) > 0 for m in team or []):
        out.append({"check": "plan type vs team", "result": "inconsistent",
                    "detail": "labelled lean validation but includes salaried staff"})
    payroll = table[0]["payroll"] if table else 0
    rev5 = table[-1]["revenue"] if table else 0
    if table and payroll > 3 * max(rev5, 1):
        out.append({"check": "team cost vs revenue", "result": "tension",
                    "detail": "year-1 payroll (%s) is more than 3x year-5 revenue (%s)" % (
                        _money(payroll), _money(rev5))})
    return out


def _money(x) -> str:
    from .report_model import money
    return money(x)


# ---------------------------------------------------------------- publication gate
_MEMO_NUM = re.compile(r"(?<![\w.])\$?-?\d[\d,]*(?:\.\d+)?(?:[KMB]\b|%)?")


def _numbers_in(obj, acc: set) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, acc)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        from .report_model import money
        for form in (obj, round(obj), round(obj, 1), round(obj, 2), obj * 100, round(obj * 100)):
            acc.add(_norm(str(form)))
        acc.add(_norm(money(obj)))
        acc.add(_norm("{:,.0f}".format(obj)))
        acc.add(_norm("%g" % obj))
    else:
        for tok in _MEMO_NUM.findall(str(obj)):
            acc.add(_norm(tok))


def _norm(tok: str) -> str:
    t = tok.replace(",", "").replace("$", "").replace("%", "").strip()
    if t.endswith(".0"):
        t = t[:-2]
    return t.lstrip("-")


def publication_gate(memo: str, model: dict) -> dict:
    """Every number in the memo's prose must appear in the validated model (or be a small structural integer such
    as a section number). Returns {"passed": bool, "untraced": [...], "checked": n}."""
    allowed: set = set()
    # narrative decision text is checked, not trusted; corrections and rejected claims are never a source of numbers
    trusted = {k: v for k, v in model.items() if k not in ("corrections", "claims", "rejected_claim_ids", "decision")}
    trusted["claims"] = [c for c in model.get("claims", []) if c.get("status") in ("supported", "partially_supported")]
    _numbers_in(trusted, allowed)  # numbers only found in rejected claims or correction notes are NOT traceable
    text = re.sub(r"\]\([^)]*\)", "]", memo)  # drop link targets
    untraced, checked = [], 0
    for line in text.splitlines():
        line = re.sub(r"^\s*(#+\s*\d+\.|\d+\.)\s", " ", line)  # heading and list numbering
        for tok in _MEMO_NUM.findall(line):
            n = _norm(tok)
            if not n or not re.search(r"\d", n):
                continue
            checked += 1
            base = re.sub(r"[KMB]$", "", n)
            try:
                small = float(base) <= 10 and "." not in base and not n.endswith(("K", "M", "B"))
            except ValueError:
                small = False
            if n in allowed or small:
                continue
            untraced.append(tok)
    return {"passed": not untraced, "untraced": sorted(set(untraced)), "checked": checked}
