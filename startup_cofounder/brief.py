"""Research-planning agent: understand the founder's idea before researching it.

Produces an IdeaBrief (the founder's own words, the product, target customer, problem, customer job, stage,
geography, payer, constraints, explicit exclusions) and an assumptions map: the desirability, feasibility and
viability hypotheses the idea depends on, ranked by importance (Strategyzer assumptions mapping: test the important
hypotheses with the least evidence first).

The model is asked one narrow extraction question. Code then:
* fills gaps deterministically from the founder's text (geography, stage, payer, network effects, exclusions);
* checks fidelity: a restatement that introduces concept-changing terms the founder never used (e.g. "stranger",
  "dating", "marketplace", "AI") is rejected and the founder's wording is kept, with a visible flag.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .relevance import GENERIC, guess_geography, guess_payer, terms

BRIEF_SCHEMA = {"type": "object", "properties": {
    "product": {"type": "string"}, "target_customer": {"type": "string"}, "problem": {"type": "string"},
    "customer_job": {"type": "string"}, "geography": {"type": "string"},
    "stage": {"type": "string", "enum": ["idea", "prototype", "launched"]},
    "payer": {"type": "string", "enum": ["consumer", "business", "unknown"]},
    "business_model": {"type": "string"}, "constraints": {"type": "array", "items": {"type": "string"}},
    "exclusions": {"type": "array", "items": {"type": "string"}}, "riskiest_assumption": {"type": "string"}},
    "required": ["product", "target_customer", "problem", "customer_job", "stage"]}
BRIEF_TEXT = """{
  "product": "<what the founder proposes to build, in the founder's words>",
  "target_customer": "<who it is for, as the founder said>",
  "problem": "<the problem it solves for them>",
  "customer_job": "<what the customer is trying to get done, as a verb phrase, e.g. 'find people to climb with'>",
  "geography": "<place named by the founder, or empty>",
  "stage": "idea|prototype|launched",
  "payer": "consumer|business|unknown",
  "business_model": "<how it would make money if the founder said so, else empty>",
  "constraints": ["<limits the founder stated>"],
  "exclusions": ["<things the founder said it is NOT>"],
  "riskiest_assumption": "<the one belief that, if wrong, kills the idea>"
}"""
BRIEF_MISSION = ("You restate a founder's idea precisely. Use the founder's own words. Do not add features, customers, "
                 "business models or technologies the founder did not mention. Leave a field empty if the founder did "
                 "not say it. stage is 'idea' unless the founder says something exists or has users.")

# Words that change what the product IS when they appear in a restatement but not in the founder's text.
SHIFT_WORDS = {"stranger", "dating", "date", "romantic", "marketplace", "deliver", "delivery", "hardware", "device",
               "ai", "artificial", "blockchain", "crypto", "nft", "enterprise", "b2b", "booking", "rideshare",
               "ecommerce", "subscription", "franchise", "insurance", "loan", "lending", "telehealth", "vr", "wearable"}
NETWORK_RX = re.compile(r"\b(social|community|communities|connect|connecting|match|matching|partner|partners|meet|"
                        r"meetup|network|marketplace|peer|buddy|buddies|group|groups|share|sharing)\b", re.I)
LAUNCHED_RX = re.compile(r"\b(we have|already|launched|live|our users|customers today|revenue of|paying users|"
                         r"currently serving)\b", re.I)
PROTOTYPE_RX = re.compile(r"\b(prototype|beta|mvp|pilot|built a|demo)\b", re.I)
EXCLUDE_RX = re.compile(r"\b(?:is not|isn't|not an?|excluding|exclude|never)\s+(?:a |an |the )?([a-z][a-z \-]{2,40}?)"
                        r"(?=[,.;]|$| but| and)", re.I)
BUSINESS_RX = re.compile(r"\b(shops?|stores?|restaurants?|cafes?|caf\u00e9s?|clinics?|practices|companies|businesses|"
                         r"firms|agencies|teams|owners|landlords|venues|schools|retailers|merchants|brands|startups|"
                         r"employers|hotels|bars|salons|studios|gyms|operators|organi[sz]ations|nonprofits)\b", re.I)


@dataclass
class Hypothesis:
    id: str
    category: str  # desirability | feasibility | viability
    statement: str  # "We believe that ..."
    importance: int  # 3 = idea fails if wrong
    questions: List[str] = field(default_factory=list)  # research question ids that inform it
    evidence: str = "none"  # none | weak | moderate | strong | contradicted (set after research)
    founder_test: bool = True  # whether desk research can settle it (False) or a real-world test is needed

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IdeaBrief:
    founder_statement: str
    product: str
    target_customer: str
    problem: str
    customer_job: str
    geography: str = ""
    stage: str = "idea"
    payer: str = "consumer"
    business_model: str = ""
    constraints: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    network_product: bool = False
    venue: str = ""
    category: str = ""
    riskiest_assumption: str = ""
    fidelity_flags: List[str] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hypotheses"] = [h.to_dict() for h in self.hypotheses]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "IdeaBrief":
        d = dict(d)
        hyps = [Hypothesis(**h) for h in d.pop("hypotheses", [])]
        b = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        b.hypotheses = hyps
        return b

    def context(self) -> str:
        """Compact description for prompts (founder's words first)."""
        bits = ["FOUNDER'S IDEA (verbatim): %s" % self.founder_statement,
                "customer: %s; problem: %s; stage: %s" % (self.target_customer, self.problem, self.stage)]
        if self.geography:
            bits.append("geography: %s" % self.geography)
        if self.exclusions:
            bits.append("NOT in scope: %s" % "; ".join(self.exclusions))
        return "\n".join(bits)


VENUES = ("gym", "club", "court", "studio", "venue", "campus", "office", "school", "park", "store", "shop",
          "restaurant", "clinic", "library", "field", "center", "centre", "hospital", "salon", "cafe", "bar")


def _first_venue(text: str) -> str:
    return next((w for w in VENUES if re.search(r"\b%ss?\b" % w, text, re.I)), "")


def _clean(s) -> str:
    s = " ".join(str(s or "").split()).strip(" .")
    return "" if s.lower() in ("", "n/a", "none", "unknown", "null", "empty") else s


REQUEST_RX = re.compile(r"^\s*(explore|analy[sz]e|assess|evaluate|research|include|consider|estimate|identify|"
                        r"look at|tell me|give me|please|what|how|should|is it)\b", re.I)


def description(idea: str) -> str:
    """The founder's description of the idea without trailing requests to the analyst ("Explore competitors...")."""
    sents = re.split(r"(?<=[.!?])\s+", " ".join(str(idea or "").split()))
    keep = [s for i, s in enumerate(sents) if i == 0 or not REQUEST_RX.search(s)]
    return " ".join(keep)


def fallback_fields(idea: str, plan: Optional[dict] = None) -> dict:
    """Deterministic reading of the founder's sentence (used when the model leaves gaps or drifts)."""
    plan = plan or {}
    idea = description(idea)
    m = re.search(r"\b(?:helps?|helping|lets?|letting|allows?|allowing|enables?|enabling)\s+(.+?)\s+(?:to\s+)?(find|get|book|manage|track|learn|share|"
                  r"meet|connect|buy|sell|plan|organi[sz]e|discover|reduce|save|avoid|improve)\b(.*)", idea, re.I)
    if m:
        customer = m.group(1)
        job = (m.group(2) + m.group(3)).split(" based on ")[0].strip(" .")
    else:
        m2 = re.search(r"\bfor\s+(.+?)(?:\s+(?:to|who|that|in)\b|[,.]|$)", idea, re.I)
        customer = m2.group(1) if m2 else str(plan.get("customer_type") or "target customers")
        ger = re.search(r"\b([a-z]{3,}ing)\b", idea.split(" for ")[0], re.I)
        job = str(plan.get("problem") or "") or ("manage " + ger.group(1).lower() if ger else "solve the problem")
    idea = re.sub(r"^(?:we|i)(?:'re| are| am)?\s+(?:building|making|developing|running|run|make|build|developing|"
                  r"want to build|plan to build|have built|built)\s+", "", idea, flags=re.I)
    product = re.split(r"\s+(?:that|which|to|for|helping|letting|allowing|enabling)\s+", idea, maxsplit=1)[0]
    product = re.sub(r"^(a|an|the)\s+", "", product, flags=re.I)
    return {"product": product, "target_customer": customer.strip(" ,"), "customer_job": job,
            "problem": str(plan.get("problem") or "it is hard to " + job)}


def _added_shift_terms(restated: str, founder: str) -> List[str]:
    founder_t = terms(founder.replace("-", " "))
    added = (terms(restated.replace("-", " ")) - founder_t) - GENERIC
    from .relevance import stem
    shift = {stem(w) for w in SHIFT_WORDS} | SHIFT_WORDS
    bad = {w for w in added if w in shift}
    words = re.findall(r"[A-Za-z]+", restated)
    return sorted({w.lower() for w in words if stem(w) in bad or w.lower() in bad})


def build_brief(idea: str, raw: Optional[dict], plan: Optional[dict] = None) -> IdeaBrief:
    plan = plan or {}
    raw = raw if isinstance(raw, dict) else {}
    fb = fallback_fields(idea, plan)
    flags: List[str] = []
    fields = {}
    for k in ("product", "target_customer", "problem", "customer_job"):
        val = _clean(raw.get(k)) or fb[k]
        shifted = _added_shift_terms(val, idea)
        if shifted:
            flags.append("planner restated %s with '%s', which the founder did not say; kept the founder's wording"
                         % (k.replace("_", " "), ", ".join(shifted)))
            val = fb[k]
        fields[k] = val
    geography = _clean(raw.get("geography")) or guess_geography(idea)
    if geography and geography.lower() not in idea.lower():
        flags.append("planner named geography '%s' that is not in the founder's text; ignored" % geography)
        geography = guess_geography(idea)
    stage = str(raw.get("stage") or "").lower()
    desc = description(idea)  # requests such as "explore an MVP" do not mean an MVP exists
    text_stage = "launched" if LAUNCHED_RX.search(desc) else "prototype" if PROTOTYPE_RX.search(desc) else "idea"
    if stage not in ("idea", "prototype", "launched") or (stage != "idea" and text_stage == "idea"):
        stage = text_stage  # never assume traction the founder did not state
    if geography:  # the place is recorded once, not inside the customer description
        fields["target_customer"] = re.sub(r"\s+(in|around|near)\s+%s\b" % re.escape(geography), "",
                                           fields["target_customer"], flags=re.I).strip(" ,")
    payer = str(raw.get("payer") or "").lower()
    if payer not in ("consumer", "business"):
        payer = "business" if BUSINESS_RX.search(fields["target_customer"]) else guess_payer(idea)
    exclusions = [_clean(x) for x in raw.get("exclusions") or [] if _clean(x)]
    exclusions += [m.group(1).strip() for m in EXCLUDE_RX.finditer(idea) if m.group(1).strip() not in exclusions]
    constraints = [_clean(x) for x in raw.get("constraints") or [] if _clean(x)]
    model = _clean(raw.get("business_model"))
    if model and _added_shift_terms(model, idea):
        flags.append("planner proposed business model '%s' that the founder did not state; left open" % model)
        model = ""
    category = str(plan.get("category") or "").strip()
    if category and _added_shift_terms(category, idea):
        flags.append("planner categorised the idea as '%s', which adds concepts the founder did not state; used the "
                     "founder's product description instead" % category)
        category = ""
    b = IdeaBrief(founder_statement=" ".join(idea.split()), geography=geography, stage=stage, payer=payer,
                  business_model=model, constraints=constraints, exclusions=exclusions,
                  network_product=bool(NETWORK_RX.search(idea)), venue=_first_venue(idea),
                  category=category or fields["product"],
                  riskiest_assumption=_clean(raw.get("riskiest_assumption")), fidelity_flags=flags, **fields)
    b.hypotheses = assumptions_map(b)
    return b


def assumptions_map(b: IdeaBrief) -> List[Hypothesis]:
    """Hypotheses the idea depends on (desirability, feasibility, viability), most important first."""
    where = (" in %s" % b.geography) if b.geography else ""
    H = [
        Hypothesis("H-D1", "desirability", "We believe that %s%s experience '%s' often enough to want a dedicated "
                   "solution." % (b.target_customer, where, b.problem), 3, ["Q-C1", "Q-C2"]),
        Hypothesis("H-D2", "desirability", "We believe that %s would choose this over what they use today to %s."
                   % (b.target_customer, b.customer_job), 3, ["Q-C2", "Q-K2"]),
    ]
    if b.network_product:
        H.append(Hypothesis("H-D3", "desirability", "We believe that enough %s%s will take part at the same %s and "
                            "time for the product to be useful from the first weeks (cold start)."
                            % (b.target_customer, where, b.venue or "place"), 3, ["Q-D1", "Q-D2", "Q-M1"]))
    H += [
        Hypothesis("H-V1", "viability", "We believe that %s will pay for it (or that another payer will)."
                   % ("users" if b.payer == "consumer" else "businesses"), 3, ["Q-W1"]),  # Q-R1 = competitor prices
        Hypothesis("H-V2", "viability", "We believe that the reachable market%s is large enough to support the "
                   "business." % where, 2, ["Q-M1"], founder_test=False),
        Hypothesis("H-V3", "viability", "We believe that early users can be reached at low cost through existing "
                   "channels.", 2, ["Q-D1"]),
        Hypothesis("H-F1", "feasibility", "We believe that a small team can build the first version with standard, "
                   "affordable components.", 1, ["Q-F1"], founder_test=False),
    ]
    if b.network_product:
        H.append(Hypothesis("H-F2", "feasibility", "We believe that trust, safety and privacy can be handled without "
                            "heavy moderation costs.", 2, ["Q-F2"], founder_test=False))
    if b.riskiest_assumption and not any(_overlap(b.riskiest_assumption, h.statement) for h in H):
        H.append(Hypothesis("H-X1", "desirability", "We believe that " + b.riskiest_assumption.rstrip(".") + ".", 3,
                            ["Q-C1"]))
    return H


def _overlap(a: str, b: str) -> bool:
    ta, tb = terms(a) - GENERIC, terms(b) - GENERIC
    return bool(ta) and len(ta & tb) / len(ta) >= 0.5
