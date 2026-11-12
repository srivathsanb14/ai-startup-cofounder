"""Competitor identity: a name is not an identity.

A competitor is identified by (name, official domain, what it is, who it is for). Verification needs *positive*
evidence: at least one retrieved source in which the name appears together with the product category (anchor terms of
the research frame). Missing identity or relevance evidence yields "unresolved", never automatic approval.

Relation to the founder's product:
    direct      same need, same customer
    substitute  different product the same customer uses for the same need (forums, groups, generic tools)
    adjacent    same category and customer, different need (e.g. a logbook app for the same climbers)
    irrelevant  a different company or category that merely shares the name
    unresolved  not enough evidence to tell
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

from .quality import _clean_name, valid_company_name

RELATIONS = ("direct", "substitute", "adjacent", "irrelevant", "unresolved")
COUNTED = ("direct", "substitute", "adjacent")
AGGREGATORS = ("wikipedia.org", "news.google.com", "tripadvisor.", "indeed.com", "capterra.", "g2.com", "reddit.com",
               "youtube.com", "facebook.com", "linkedin.com", "crunchbase.com", "apps.apple.com", "play.google.com",
               "medium.com", "trustpilot.", "glassdoor.", "yelp.com", "amazon.", "ycombinator.com")


def name_token(name: str) -> str:
    clean = _clean_name(name)
    return clean.split()[0] if clean else ""


def _mentions(name: str, text: str, avoid=()) -> bool:
    """Full name, or its distinctive first word. A first word that is an ordinary category word ("Climbing" in
    "Climbing Place") is not distinctive: it would match every page about the category."""
    clean = _clean_name(name)
    if not clean:
        return False
    low = text.lower()
    if clean in low:
        return True
    first = clean.split()[0]
    from .relevance import GENERIC, stem
    if len(clean.split()) > 1 and (stem(first) in avoid or first in GENERIC):
        return False
    return len(first) >= 4 and re.search(r"\b%s\b" % re.escape(first), low) is not None


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def identity_sources(name: str, ids: Sequence[str], ledger, book) -> List[str]:
    """Sources that mention the name AND the product category (positive evidence of competitive relevance)."""
    out = []
    for sid in ids:
        src = ledger.get(sid)
        if src is None:
            continue
        text = src.text + " " + src.url
        avoid = book.frame.core | book.frame.context | book.frame.need | book.frame.anchors
        if _mentions(name, text, avoid) and book.of(src).label != "irrelevant":
            out.append(sid)
    return out


def official_domain(name: str, sources: Sequence, claimed_url: str = "") -> str:
    """Domain whose host contains the name token, from identity-confirming sources (or the claimed URL if it is one)."""
    token = re.sub(r"[^a-z0-9]", "", name_token(name))
    if len(token) < 3:
        return ""
    candidates = [domain_of(s.url) for s in sources] + [domain_of(claimed_url)]
    for host in candidates:
        if host and token in host.replace("-", "") and not any(a in host for a in AGGREGATORS):
            return host
    return ""


def classify(profile: dict, name: str, ledger, book, ids: Sequence[str]) -> dict:
    """Attach identity fields and a relation that requires positive evidence.

    The model's stated relation is accepted only when the code finds name+category co-occurrence and the profile
    description itself is about the category; otherwise the relation is downgraded to unresolved/irrelevant.
    """
    frame = book.frame
    support = identity_sources(name, ids, ledger, book)
    srcs = [ledger.get(i) for i in support]
    description = str(profile.get("description") or "")
    desc_on_topic = bool(frame.anchors & _terms(description))
    claimed = str(profile.get("relation") or "").strip().lower()
    if claimed not in RELATIONS:
        claimed = "unresolved"
    if profile.get("is_competitor") is False and claimed in COUNTED:
        claimed = "irrelevant"
    reasons = []
    from .relevance import GENERIC
    name_terms = _terms(name)
    if not valid_company_name(name):
        relation, reasons = "irrelevant", ["not a company or product name"]
    elif name_terms and name_terms <= (frame.core | frame.context | frame.geo_terms | {_t for _t in _terms(" ".join(GENERIC))}):
        relation, reasons = "unresolved", ["name consists only of category words, so co-occurrence proves nothing"]
        support = []
    elif not support:
        relation = "irrelevant" if any(_mentions(name, s.text) for s in (ledger.get(i) for i in ids) if s) else "unresolved"
        reasons.append("no retrieved source mentions %s together with the product category" % name)
    elif not desc_on_topic:
        relation = "unresolved" if claimed in COUNTED else claimed
        reasons.append("profile description does not describe a product in this category")
    elif claimed == "unresolved":
        relation = "unresolved"
        reasons.append("relation to the founder's product was not stated")
    else:
        relation = claimed
        reasons.append("name co-occurs with category terms in %d source(s)" % len(support))
    # Same customer need => direct, whatever the model called it (e.g. a partner-finding app is not "adjacent"
    # to a partner-finding app). Needs positive evidence: identity sources, on-topic description, need words.
    need_text = description + " " + str(profile.get("intended_customer") or "")
    need_hit = sorted(frame.need & _terms(need_text))
    if support and desc_on_topic and need_hit and relation in ("adjacent", "substitute", "unresolved"):
        from .relevance import stem
        words = sorted({w for w in re.findall(r"[A-Za-z][A-Za-z-]+", need_text) if stem(w) in frame.need})
        reasons.append("reclassified %s -> direct by code: its description addresses the same need (\"%s\")"
                       % (relation, ", ".join(words[:3]).lower()))
        relation = "direct"
    domain = official_domain(name, srcs, str(profile.get("url") or ""))
    out = dict(profile)
    out.update({
        "name": name, "relation": relation, "official_domain": domain,
        "intended_customer": str(profile.get("intended_customer") or ""),
        "identity_source_ids": support, "identity_note": "; ".join(reasons),
        "verified": relation in COUNTED and bool(support),
    })
    if domain:
        out["url"] = out.get("url") if domain_of(out.get("url", "")) == domain else "https://" + domain
    elif out.get("url") and domain_of(out["url"]) not in {domain_of(s.url) for s in srcs}:
        out["url"] = ""  # a URL the evidence does not show is not kept
    return out


def _terms(text: str):
    from .relevance import terms
    return terms(text)


def identity_key(c: dict) -> str:
    """Two profiles are the same entity only with the same official domain. Without a domain they stay separate."""
    domain = c.get("official_domain") or ""
    return ("domain:" + domain) if domain else ("name:%s|%s" % (_clean_name(c.get("name", "")), id(c)))


def merge(existing: Sequence[dict], new: Sequence[dict]) -> List[dict]:
    """Union by identity (domain), never by name alone. Same-name entities with different/unknown domains are kept
    apart and flagged so a reader can see the ambiguity."""
    out: List[dict] = []
    keys: Dict[str, dict] = {}
    for c in list(existing) + list(new):
        key = identity_key(c)
        if key in keys:
            continue
        keys[key] = c
        out.append(c)
    by_name: Dict[str, List[dict]] = {}
    for c in out:
        by_name.setdefault(_clean_name(c.get("name", "")), []).append(c)
    for group in by_name.values():
        if len(group) > 1:
            for c in group:
                c["identity_note"] = (c.get("identity_note", "") + "; same name as another profiled entity with a "
                                      "different or unknown domain (not merged)").strip("; ")
    rank = {"direct": 0, "substitute": 1, "adjacent": 2, "unresolved": 3, "irrelevant": 4}
    out.sort(key=lambda c: (rank.get(c.get("relation"), 3), not c.get("verified")))
    return out


def profile_queries(name: str, frame) -> List[tuple]:
    """Follow-up searches keep the category (and domain, once known) in the query, so 'KAYA' does not drift to hotels."""
    ctx = " ".join(sorted(frame.anchors))
    return [("web_search", '"%s" %s app' % (name, ctx)), ("web_search", "%s %s pricing" % (name, ctx)),
            ("web_search", "%s %s reviews" % (name, ctx))]
