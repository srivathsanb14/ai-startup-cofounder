"""Research questions: what each analyst must find out, where to look, and what would contradict it.

Each question is small enough for one focused model call. Queries target the source type that can actually answer
it (people's own discussions for behaviour, app reviews for dissatisfaction, official pages for features and prices,
local sources for market counts, technical documentation for feasibility), and every question also searches for
evidence AGAINST the founder's hypothesis.

Templates use only fields of the IdeaBrief, so the catalog is not specific to any one idea.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from .relevance import GENERIC, terms


@dataclass
class Question:
    id: str
    topic: str  # customer | competition | market | distribution | revenue | feasibility | risk
    text: str
    hypotheses: List[str]
    prefer: List[str]  # preferred source types (validators.SOURCE_TYPES)
    queries: List[tuple]  # (tool, query) seeds
    disconfirm: List[tuple] = field(default_factory=list)
    fallback: List[tuple] = field(default_factory=list)  # different source types for a repair attempt
    extract: str = ""  # what the analyst must extract
    local: bool = False  # findings must be about the founder's geography
    off_category_ok: bool = False  # technical/ops sources need not mention the product category
    vendor_ok: bool = False  # vendor pages are the right source (features, prices)
    keywords: List[str] = field(default_factory=list)
    must: str = ""  # regex a finding must match to be about THIS question (field-level check, also for model output)

    def to_dict(self) -> dict:
        return asdict(self)


def _short(text: str, words: int = 5) -> str:
    ws = [w for w in re.findall(r"[A-Za-z0-9'-]+", text or "") if w.lower() not in ("a", "an", "the")]
    return " ".join(ws[:words])


def _plural(word: str) -> str:
    return word if not word or word.endswith("s") else word + "s"


def catalog(brief, competitors: Sequence[str] = ()) -> List[Question]:
    cust = _short(brief.target_customer, 4)
    job = _short(brief.customer_job, 6)
    cat = _short(brief.category or brief.product, 4)
    catn = re.sub(r"\s+(apps?|platforms?|tools?|software)$", "", cat, flags=re.I) or cat  # avoid "apps app"
    geo = brief.geography
    venue = brief.venue or ("business" if brief.payer == "business" else "place")
    where = (" " + geo) if geo else ""
    comp = [c for c in competitors if c][:2]
    Q = [
        Question("Q-C1", "customer", "Do %s actually experience the problem '%s'? In what situations and how often?"
                 % (cust, _short(brief.problem, 10)), ["H-D1"], ["forum_community", "news_editorial", "blog_other"],
                 [("web_search", "site:reddit.com %s" % job), ("web_search", "%s %s forum" % (cust, job)),
                  ("hn_search", job)],
                 disconfirm=[("web_search", "%s easy %s" % (job, cust))],
                 fallback=[("web_search", "%s struggle %s" % (cust, job)), ("news_search", "%s %s" % (cust, job))],
                 extract="situations where the problem occurs, how often, and how much it matters to them",
                 keywords=_kw(job + " " + brief.problem), must=_must(job, cat)),
        Question("Q-C2", "customer", "How do %s currently %s, and what is wrong with those ways?" % (cust, job),
                 ["H-D1", "H-D2"], ["forum_community", "blog_other"],
                 [("web_search", "how do you %s reddit" % job), ("web_search", "best way to %s%s" % (job, where))],
                 disconfirm=[("web_search", "%s works fine without an app" % job)],
                 fallback=[("web_search", "%s tips %s" % (job, cust))],
                 extract="current workarounds people actually use and their shortcomings",
                 keywords=_kw(job), must=_must(job, cat)),
        Question("Q-W1", "customer", "Is there evidence that %s spend money to %s? What do they say about paying?"
                 % (cust, job), ["H-V1"], ["forum_community", "app_store", "news_editorial"],
                 [("web_search", "%s worth paying for reddit" % cat), ("web_search", "%s subscription price review" % cat)],
                 disconfirm=[("web_search", "%s should be free" % cat)],
                 fallback=[("web_search", "would you pay for %s" % cat)],
                 extract="observed spending or stated willingness to pay by these customers (not vendor prices)",
                 keywords=_kw(cat + " pay price paid subscription free"), must=MONEY),
        Question("Q-R1", "revenue", "How do comparable products make money and at what prices?", ["H-V1"],
                 ["official_vendor", "app_store"],
                 [("web_search", "%s pricing premium plan" % cat)] + [("web_search", "%s pricing" % c) for c in comp],
                 fallback=[("web_search", "%s in-app purchase" % cat)],
                 extract="business models and stated prices of comparable products, with the product name",
                 vendor_ok=True, keywords=_kw("price pricing plan premium free subscription"), must=MONEY),
        Question("Q-M1", "market", "How many %s are there%s, or how many %s and members, as a basis for a bottom-up "
                 "market estimate?" % (_plural(cust.split()[-1]) if cust else "customers", where, _plural(venue)),
                 ["H-V2"], ["government_academic", "news_editorial", "official_vendor", "blog_other"],
                 [("web_search", "%s %s%s" % (_plural(venue), cat, where)),
                  ("web_search", "number of %s%s" % (cust, where)), ("news_search", "%s%s" % (cat, where))],
                 fallback=[("web_search", "%s membership numbers%s" % (venue, where))],
                 extract="counts of people, venues or members in the launch area, with the place and year",
                 local=bool(geo), keywords=_kw(venue + " members number " + cust), must=r"\d"),
        Question("Q-D1", "distribution", "Where do %s%s gather or look for this today (groups, clubs, venues, "
                 "events, online communities)?" % (cust, where), ["H-V3", "H-D3"],
                 ["forum_community", "official_vendor", "news_editorial", "blog_other"],
                 [("web_search", "%s %s group%s" % (cust, cat, where)), ("web_search", "%s club meetup%s" % (cat, where))],
                 fallback=[("web_search", "%s community%s" % (cust, where))],
                 extract="specific channels to reach these customers, with names where given",
                 local=bool(geo), keywords=_kw("group club meetup community event " + cust), must=CHANNEL),
        Question("Q-F1", "feasibility", "Which technical components does the first version of '%s' need, and which "
                 "can be bought or reused?" % _short(brief.product, 8), ["H-F1"], ["blog_other", "official_vendor"],
                 [("web_search", "%s app architecture backend" % _feature(brief)),
                  ("web_search", "%s API service pricing" % _feature(brief))],
                 fallback=[("web_search", "open source %s" % _feature(brief))],
                 extract="required components, available services or libraries, and hard parts",
                 off_category_ok=True, keywords=_kw("api architecture backend service sdk build " + _feature(brief)),
                 must=TECH),
        Question("Q-X1", "risk", "Why have similar products failed or shut down?", ["H-D1", "H-D2", "H-V1"],
                 ["news_editorial", "blog_other", "forum_community"],
                 [("web_search", "%s startup shut down why" % cat), ("web_search", "%s app failed lessons" % catn)],
                 extract="reasons similar products failed", off_category_ok=False,
                 keywords=_kw("shut down failed closing lessons why"), must=FAILURE),
    ]
    if comp:
        Q.append(Question("Q-K2", "competition", "What do users of %s dislike or wish were different?" % " and ".join(comp),
                          ["H-D2"], ["app_store", "forum_community"],
                          [("web_search", "%s app reviews" % c) for c in comp] + [("web_search", "%s reddit" % comp[0])],
                          fallback=[("web_search", "%s alternative" % comp[0])],
                          extract="specific complaints or unmet needs of current users, with the product name",
                          keywords=_kw("review complaint problem wish bug " + " ".join(comp)), must=COMPLAINT,
                          off_category_ok=True))  # anchored by the verified product names instead of the category
    if brief.network_product:
        Q.append(Question("Q-D2", "distribution", "How do products that depend on many active users solve the "
                          "cold-start problem when they launch in one place?", ["H-D3"], ["blog_other", "news_editorial"],
                          [("web_search", "cold start problem community app launch one city"),
                           ("web_search", "how %s apps get first users" % catn)],
                          extract="tactics used to reach useful density, and evidence of what worked",
                          off_category_ok=True, keywords=_kw("cold start density launch first users network"), must=COLD))
        Q.append(Question("Q-F2", "feasibility", "What trust, safety and privacy measures does a product where people "
                          "%s need (e.g. visibility of location and schedules, blocking, reporting)?" % job, ["H-F2"],
                          ["government_academic", "blog_other", "official_vendor"],
                          [("web_search", "%s app safety features block report" % catn),
                           ("web_search", "location sharing privacy app best practices")],
                          extract="concrete risks and the controls used for them; legal requirements only if stated",
                          off_category_ok=True, keywords=_kw("safety privacy block report location data moderation"),
                          must=SAFETY))
    return Q


MONEY = r"\$|\bpa(y|id)\b|\bpric|\bfree\b|subscri|\bworth\b|\bcost|premium|\bplan\b|\bfee"
COMPLAINT = (r"\bwish|\bbug|crash|annoy|missing|\bproblem|n't|\bcannot|\bhate|\bslow|expensive|\bads\b|issue|"
             r"frustrat|\black|\bdead\b|\bempty\b|nobody|no one|\bfew\b")
FAILURE = r"shut|\bfail|clos(ed|ing)|\bdied\b|struggl|lesson|post-?mortem|wound down|pivot"
CHANNEL = r"\bgroup|\bclub|meetup|communit|\bevent|forum|facebook|discord|reddit|\bclass|league|newsletter|partner"
TECH = r"\bapi|sdk|backend|database|server|architect|open source|library|framework|firebase|notification|\bmap"
SAFETY = r"safe|privacy|private|\bblock|report(ing)? (a |an )?(user|abuse|profile|behavio)|moderat|harass|consent|location|verif|trust"
COLD = r"cold start|chicken|density|first users|seed|launch|critical mass|network effect"


def _must(text: str, category: str = "") -> str:
    """Words of the customer's job that are NOT just the product category (so 'climbing gym' pages do not pass a
    question about finding partners)."""
    stems = [s for s in _kw(text) if len(s) >= 4 and s not in terms(category)] or [s for s in _kw(text) if len(s) >= 4]
    return r"\b(%s)" % "|".join(re.escape(s) for s in stems) if stems else ""


def _kw(text: str) -> List[str]:
    return sorted(terms(text) - GENERIC)


def _feature(brief) -> str:
    """The core capability, from the founder's job phrase (e.g. 'matching', 'scheduling')."""
    job = brief.customer_job.lower()
    for kw, feat in (("schedul", "scheduling"), ("roster", "scheduling"), ("shift", "scheduling"), ("match", "matching"), ("partner", "matching"), ("book", "booking"),
                     ("track", "tracking"), ("deliver", "delivery tracking"), ("pay", "payments"),
                     ("message", "messaging"), ("chat", "messaging"), ("find", "search and matching"),
                     ("learn", "learning content"), ("manage", "management dashboard")):
        if kw in job:
            return feat
    return _short(job, 3)


def question_relevance(q: Question, text: str, book) -> float:
    """0..1: how well a source fits THIS question. Category relevance from the run's RelevanceBook still applies,
    except for questions whose right sources are general (technical, cold start, safety)."""
    t = terms(text)
    kw = set(q.keywords) - GENERIC
    hit = len(kw & t) / max(1, min(len(kw), 4)) if kw else 0.0
    if q.off_category_ok:
        return min(1.0, hit)
    rel = book.frame.score(text)
    if rel.label == "irrelevant":
        return 0.0
    return min(1.0, 0.6 * rel.score + 0.4 * hit + 0.1)
