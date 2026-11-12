"""Evidence relevance: is a source about *this* product category, customer, place and period?

A non-empty search result is not evidence. Every source is scored against a ResearchFrame built from the plan:

* core terms      distinctive words of the product category (generic words such as "app" or "platform" removed);
                  a source that mentions none of them is irrelevant, however well it matches the query wording
* context terms   words from the idea, problem and keywords (customer, use case)
* geography       place named in the idea, when there is one
* period          sources whose newest year is old are marked dated

The score is deterministic and explainable (matched terms are recorded). It is a filter, not proof of support:
claim-level support is checked separately (claims.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Set

GENERIC = {
    "app", "apps", "application", "platform", "software", "service", "services", "social", "online", "digital",
    "tool", "tools", "company", "companies", "market", "business", "businesses", "user", "users", "customer",
    "customers", "product", "products", "startup", "startups", "solution", "solutions", "best", "new", "top",
    "people", "community", "communities", "local", "network", "networking", "mobile", "website", "web", "system",
    "connect", "connecting", "connects", "help", "helps", "find", "finding", "based", "match", "matching", "adult",
    "adults", "compatible", "using", "use", "their", "they", "with", "for", "and", "the", "that", "this", "from",
    "into", "about", "your", "who", "what", "how", "industry", "category", "mock", "idea", "problem", "data",
}
# words that describe places or settings, not the customer's need ("partners" is a need; "gym" is a place)
NEED_STOP = {"new", "setting", "time", "way", "place", "area", "day", "week", "gym", "club", "venue", "studio", "court",
             "campus", "office", "school", "park", "center", "centre", "session", "level", "skill", "experience",
             "availability", "discipline", "style", "type"}
STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "been", "their",
        "they", "them", "will", "can", "not", "but", "its", "our", "your", "you", "all", "any", "who", "what", "how",
        "why", "which", "about", "into", "than", "more", "most", "also", "such", "these", "those", "based", "on"}

_WORD = re.compile(r"[a-z][a-z0-9'-]{2,}")
_PLACE = re.compile(r"\bin ((?:[A-Z][a-zA-Z.]+)(?: [A-Z][a-zA-Z.]+){0,2})")
_YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def stem(word: str) -> str:
    w = word.lower().strip("'-")
    for suf in ("ings", "ing", "ers", "er", "ies", "es", "ed", "s"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            w = w[: -len(suf)]
            if suf == "ies":
                w += "y"
            break
    return w


def terms(text: str) -> Set[str]:
    return {stem(w) for w in _WORD.findall((text or "").lower()) if w not in STOP}


def guess_geography(text: str) -> str:
    """'... in Pittsburgh based on ...' -> 'Pittsburgh'. Empty when no capitalised place follows 'in'."""
    for m in _PLACE.finditer(text or ""):
        place = m.group(1).strip(" .")
        if place.split()[0].lower() not in STOP | {"a", "an", "my", "our"}:
            return place
    return ""


BUSINESS_PAYER = re.compile(r"\bfor (small |local |independent )?(businesses|companies|restaurants|clinics|gyms|"
                            r"retailers|stores|teams|enterprises|agencies|schools|hospitals|landlords|venues|"
                            r"brands|merchants|practices|firms|organizations)\b", re.I)


def guess_payer(text: str) -> str:
    return "business" if BUSINESS_PAYER.search(text or "") else "consumer"


@dataclass
class Relevance:
    score: float
    label: str  # "relevant" | "weak" | "irrelevant"
    core: List[str] = field(default_factory=list)
    context: List[str] = field(default_factory=list)
    geo: bool = False
    dated: bool = False

    def to_dict(self) -> dict:
        return {"score": round(self.score, 2), "label": self.label, "core": self.core, "context": self.context,
                "geo": self.geo, "dated": self.dated}


@dataclass
class ResearchFrame:
    category: str = ""
    idea: str = ""
    customer: str = ""
    geography: str = ""
    payer: str = "consumer"  # who pays: "consumer" or "business"
    core: Set[str] = field(default_factory=set)
    anchors: Set[str] = field(default_factory=set)  # the most distinctive core terms; at least one must match
    need: Set[str] = field(default_factory=set)  # words of the customer need (e.g. partner), used to judge "same problem"
    context: Set[str] = field(default_factory=set)
    geo_terms: Set[str] = field(default_factory=set)
    today_year: int = field(default_factory=lambda: date.today().year)

    @classmethod
    def from_plan(cls, plan: dict, idea: str) -> "ResearchFrame":
        plan = plan if isinstance(plan, dict) else {}
        category = str(plan.get("category") or "")
        summary = str(plan.get("idea_summary") or idea)
        keywords = " ".join(str(k) for k in plan.get("search_keywords") or [] if k)
        geography = str(plan.get("geography") or "").strip() or guess_geography(idea) or guess_geography(summary)
        if geography.lower() in ("global", "worldwide", "none", "n/a", "unspecified", "any"):
            geography = ""
        payer = str(plan.get("payer") or "").lower()
        payer = payer if payer in ("consumer", "business") else guess_payer(idea + " " + summary)
        geo_terms = terms(geography)
        core = {t for t in terms(category) if t not in GENERIC and t not in geo_terms}
        if not core:  # weak or placeholder category: fall back to the distinctive words of the idea
            core = {t for t in terms(idea) if t not in GENERIC and t not in geo_terms}
        plan_text = " ".join([summary, str(plan.get("problem") or ""), keywords, idea, category])
        context = {t for t in terms(plan_text) if t not in GENERIC and t not in geo_terms} - core
        counts = {t: len(re.findall(r"\b%s" % re.escape(t), plan_text.lower())) for t in core}
        top = max(counts.values()) if counts else 0
        anchors = {t for t, n in counts.items() if n >= max(1, 0.6 * top)} or set(core)
        stop = GENERIC | {stem(w) for w in NEED_STOP} | NEED_STOP
        need = {t for t in terms(str(plan.get("problem") or "")) if t not in stop and t not in geo_terms} - core
        if not need:
            need = {t for t in terms(idea) if t not in stop and t not in geo_terms} - core
        return cls(category=category, idea=idea, customer=str(plan.get("customer_type") or plan.get("customer") or ""),
                   geography=geography, payer=payer, core=core, anchors=anchors, need=need, context=context,
                   geo_terms=geo_terms)

    def describe(self) -> str:
        bits = ["category: %s" % (self.category or "?"), "core terms: %s" % ", ".join(sorted(self.core)),
                "anchor terms: %s" % ", ".join(sorted(self.anchors))]
        if self.geography:
            bits.append("geography: %s" % self.geography)
        bits.append("payer: %s" % self.payer)
        return "; ".join(bits)

    def search_context(self) -> str:
        """Words to add to a follow-up query so it stays on this category (and place, when one matters)."""
        words = sorted(self.anchors)[:2] + sorted(self.core - self.anchors)[:1]
        return " ".join(words + ([self.geography] if self.geography else []))

    def score(self, text: str, question: str = "") -> Relevance:
        t = terms(text)
        core_hit = sorted(self.core & t)
        ctx_hit = sorted(self.context & t)
        geo = bool(self.geo_terms) and self.geo_terms <= t
        years = [int(y) for y in _YEAR.findall(text or "")]
        dated = bool(years) and max(years) < self.today_year - 6
        if not core_hit or not (self.anchors & t):
            return Relevance(0.0, "irrelevant", [], ctx_hit, geo, dated)
        core_frac = len(core_hit) / max(1, len(self.core))
        ctx_frac = min(1.0, len(ctx_hit) / 3.0)
        q = terms(question) - GENERIC
        q_frac = len(q & t) / max(1, len(q)) if q else 0.0
        score = 0.55 * core_frac + 0.2 * ctx_frac + 0.1 * q_frac + (0.15 if geo else 0.0)
        if dated:
            score *= 0.7
        label = "relevant" if score >= 0.3 else "weak"
        return Relevance(min(1.0, score), label, core_hit, ctx_hit, geo, dated)


class RelevanceBook:
    """Cache of relevance per source id for one run (the frame is fixed once the plan exists)."""

    def __init__(self, frame: ResearchFrame) -> None:
        self.frame = frame
        self._by_id: Dict[str, Relevance] = {}

    def of(self, source) -> Relevance:
        rel = self._by_id.get(source.id)
        if rel is None:
            rel = self.frame.score(source.text + " " + source.url)
            self._by_id[source.id] = rel
        return rel

    def relevant_ids(self, ids: Iterable[str], ledger, minimum: str = "weak") -> List[str]:
        allowed = ("relevant",) if minimum == "relevant" else ("relevant", "weak")
        out = []
        for sid in ids:
            src = ledger.get(sid)
            if src is not None and self.of(src).label in allowed:
                out.append(sid)
        return out

    def snapshot(self) -> Dict[str, dict]:
        return {k: v.to_dict() for k, v in self._by_id.items()}


_INJECTION = re.compile(r"(ignore|disregard|forget) (all |any |the )?(previous|prior|above|earlier) "
                        r"(instructions|prompts?|rules)|you are now|system prompt|^\s*(ROLE|SYSTEM|ASSISTANT)\s*:",
                        re.I | re.M)


def neutralize(text: str) -> str:
    """Retrieved pages are untrusted. Remove instruction-like phrases so they read as data, not commands."""
    return _INJECTION.sub("[instruction-like text removed]", text or "")
