"""Issues with stable ids, severities and code-checkable acceptance criteria; retry scheduling and measurement.

Deterministic checks (here) find what code can verify: empty or duplicated fields, off-topic sections, irrelevant
citations, zero market sizes, unidentified competitors. Critic issues are added on top. Each retry targets a set of
issues and is then *measured*: the same checks run on the new answer, the targeted issues are marked resolved or not,
the two answers are scored, and the better one is kept.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .relevance import terms

SEVERITY_WEIGHT = {"high": 5, "medium": 2, "low": 1}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
MAX_ATTEMPTS = 2  # retries per issue before it is recorded as unresolved and no longer retried


@dataclass
class Issue:
    id: str
    section: str
    severity: str
    message: str
    instructions: str
    acceptance: str
    fields: List[str] = field(default_factory=list)
    origin: str = "rule"  # "rule" | "critic" | "final"
    status: str = "open"  # open | resolved | unresolved | disclosed
    attempts: int = 0
    history: List[dict] = field(default_factory=list)
    action: str = "research"  # research | regenerate | founder (real-world test: validation plan, never retried)

    def to_dict(self) -> dict:
        return asdict(self)

    def brief(self) -> str:
        return "[%s] (%s) %s\n    Fix: %s\n    Done when: %s" % (self.id, self.severity, self.message,
                                                                 self.instructions, self.acceptance)


def _iid(section: str, code: str, field_name: str = "") -> str:
    return "%s:%s%s" % (section, code, (":" + field_name) if field_name else "")


def critic_id(section: str, text: str) -> str:
    key = " ".join(sorted(terms(text)))[:200]
    return "%s:critic-%s" % (section, hashlib.sha1(key.encode()).hexdigest()[:6])


def _nonempty(items) -> List[str]:
    return [str(i).strip() for i in items if str(i).strip()] if isinstance(items, list) else []


def _dupes(items: Sequence[str]) -> int:
    seen, d = set(), 0
    for i in items:
        k = " ".join(sorted(terms(i)))
        if k in seen:
            d += 1
        seen.add(k)
    return d


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _on_topic(text: str, frame) -> bool:
    return bool(frame.anchors & terms(text))


FOUNDER_RX = re.compile(r"\b(interview|survey|talk to|ask (users|customers|climbers)|pilot|landing page|pre-?order|"
                        r"focus group|user test|beta test|questionnaire|field test)", re.I)


def is_founder_task(text: str) -> bool:
    return bool(FOUNDER_RX.search(text or ""))


def section_issues(role: str, output: dict, error: Optional[str], frame, claims: Sequence = (),
                   evidence_ids: Sequence[str] = (), book=None, ledger=None, limitation: str = "",
                   products: Sequence[str] = ()) -> List[Issue]:
    """Deterministic issues for one research section. Pure function of its inputs (re-run after every retry)."""
    out: List[Issue] = []
    add = out.append
    if error or not output:
        add(Issue(_iid(role, "no-output"), role, "high", "section produced no usable output (%s)" % (error or "empty"),
                  "Produce the complete JSON answer for this section using the evidence provided.",
                  "section returns valid output"))
        return out
    summary = str(output.get("summary") or "")
    findings = output.get("findings") if isinstance(output.get("findings"), list) else []
    claim_texts = [str(f.get("claim", "")) for f in findings if isinstance(f, dict)]
    items = [t for t in claim_texts + _nonempty(output.get("key_points")) +
             _nonempty(output.get("implications_for_founder")) if t.strip()]
    body = " ".join([summary] + items)
    on_items = [t for t in items if _on_topic(t, frame) or len(frame.context & terms(t)) >= 2]
    off_share = 1 - len(on_items) / len(items) if items else 0.0
    if role != "competitor" and body.strip() and (not _on_topic(body, frame) or (len(items) >= 2 and off_share > 0.5)):
        add(Issue(_iid(role, "off-topic"), role, "high",
                  "section is not about the product category (%s): %d of %d statements mention none of: %s"
                  % (frame.category, len(items) - len(on_items), len(items), ", ".join(sorted(frame.anchors))),
                  "Answer only about %s. Discard evidence about unrelated topics. If no relevant evidence exists, "
                  "say so explicitly instead of discussing other subjects." % frame.describe(),
                  "summary and findings mention the product category"))
    if evidence_ids and book is not None and ledger is not None:
        relevant = book.relevant_ids(evidence_ids, ledger)
        if not relevant:
            add(Issue(_iid(role, "no-relevant-evidence"), role, "high",
                      "no relevant evidence was available for this section" + (" (%s)" % limitation if limitation else ""),
                      "Search with different words that name the product category%s; or state the limitation."
                      % (" and %s" % frame.geography if frame.geography else ""),
                      "at least one relevant source is cited, or the limitation is stated"))
    if claims:
        bad = [c for c in claims if c.kind == "fact" and c.status in ("unsupported", "contradicted")]
        offtopic = [c for c in bad if "off-topic" in c.explanation]
        if offtopic:
            add(Issue(_iid(role, "irrelevant-citations"), role, "high",
                      "%d claim(s) cite only off-topic sources (%s)" % (len(offtopic), ", ".join(c.id for c in offtopic[:4])),
                      "Remove claims backed only by off-topic sources; cite relevant evidence ids or label the statement "
                      "an estimate.", "no claim cites only off-topic sources"))
        if not any(c.status in ("supported", "partially_supported") for c in claims if c.kind == "fact"):
            add(Issue(_iid(role, "no-supported-claims"), role, "medium",
                      "no finding is backed by a relevant cited source",
                      "Cite evidence ids for claims the evidence supports, quoting numbers exactly; label the rest "
                      "estimates.", "at least one fact claim is (partially) supported"))
    if _dupes(claim_texts) or any(_dupes(_nonempty(output.get(k))) for k in output if isinstance(output.get(k), list)
                                  and k != "findings"):
        add(Issue(_iid(role, "duplicates"), role, "high" if _dupes(claim_texts) >= 2 else "medium",
                  "repeated statements (%d duplicate findings)" % _dupes(claim_texts),
                  "Remove repeated statements; each finding must say something different.",
                  "no duplicated findings or list items"))
    if limitation and not re.search(r"limit|insufficient|no (relevant )?evidence|not found|could not|unclear|unknown",
                                    summary, re.I):
        add(Issue(_iid(role, "limitation-not-stated"), role, "medium",
                  "research hit a limitation that the summary does not disclose: %s" % limitation,
                  "State plainly in the summary which evidence could not be found.",
                  "summary mentions the limitation"))
    if role == "customer":
        segs = [s for s in output.get("segments", []) if isinstance(s, dict) and s.get("name")]
        if not segs:
            add(Issue(_iid(role, "segments", "segments"), role, "high", "no customer segments identified",
                      "Identify concrete customer segments with pain points and how they cope today.",
                      "at least one segment with name and pain points", ["segments"]))
    if role == "market":
        tss = output.get("tam_sam_som") if isinstance(output.get("tam_sam_som"), dict) else {}
        vals = [_num(tss.get(k)) for k in ("tam_usd", "sam_usd", "som_usd")]
        method = str(tss.get("method") or "")
        unknown_stated = re.search(r"unknown|insufficient|not (available|found)|cannot", method + summary, re.I)
        if not all(v > 0 for v in vals) and not unknown_stated:
            add(Issue(_iid(role, "sizing-missing", "tam_sam_som"), role, "high",
                      "TAM/SAM/SOM are zero or missing (%s) without saying sizing is unknown" % vals,
                      "Derive TAM, SAM and SOM in USD from cited figures (show the arithmetic: population x price, or "
                      "industry revenue x share), or set them to 0 and state in 'method' that sizing is unknown.",
                      "all three positive with a derivation, or method states sizing is unknown", ["tam_sam_som"]))
        elif all(v > 0 for v in vals) and not (vals[0] >= vals[1] >= vals[2]):
            add(Issue(_iid(role, "sizing-order", "tam_sam_som"), role, "high", "market sizes are not TAM >= SAM >= SOM",
                      "Fix the sizes so TAM >= SAM >= SOM and explain each step.", "TAM >= SAM >= SOM", ["tam_sam_som"]))
        elif all(v > 0 for v in vals) and (len(method) < 25 or not re.search(r"\d|E\d+", method)):
            add(Issue(_iid(role, "sizing-derivation", "tam_sam_som.method"), role, "medium",
                      "market sizes have no derivation", "Explain how each size was derived, with cited ids and numbers.",
                      "method shows numbers or cited ids", ["tam_sam_som.method"]))
    if role == "technical":
        comps = [str(c.get("name")) for c in output.get("components") or [] if isinstance(c, dict) and c.get("name")] \
            or _nonempty(output.get("key_components"))
        risks = [str(r.get("risk")) for r in output.get("delivery_risks") or [] if isinstance(r, dict) and r.get("risk")] \
            or _nonempty(output.get("main_risks"))
        if not comps or not risks:
            empty = [n for n, v in (("key_components", comps), ("main_risks", risks)) if not v]
            empty = ["components" if e == "key_components" else "delivery_risks" for e in empty] \
                if "components" in output or "delivery_risks" in output else empty
            add(Issue(_iid(role, "empty-fields", "+".join(empty)), role, "high",
                      "required technical fields are empty: %s" % ", ".join(empty),
                      "List the concrete components to build or buy and the main technical risks.",
                      "key_components and main_risks are non-empty", empty))
            if output.get("feasibility_score") not in (None, "") or output.get("mvp_time_months") or (
                    isinstance(output.get("effort"), dict) and output["effort"].get("weeks_low")):
                add(Issue(_iid(role, "unfounded-score", "feasibility_score"), role, "high",
                          "a feasibility score and timeline are given although components and risks are empty",
                          "Only give a feasibility score and MVP timeline that follow from the listed components and "
                          "risks.", "score accompanied by components and risks", ["feasibility_score"]))
        if output.get("feasibility_score") in (None, ""):
            add(Issue(_iid(role, "no-score", "feasibility_score"), role, "medium", "no feasibility score",
                      "Give a 1-5 feasibility score with reasons.", "feasibility_score present", ["feasibility_score"]))
    if role == "competitor":
        comps = [c for c in output.get("competitors", []) if isinstance(c, dict)]
        counted = [c for c in comps if c.get("verified")]
        if not counted:
            add(Issue(_iid(role, "no-verified"), role, "high",
                      "no competitor has positive evidence of competing in this category",
                      "Search for products in %s and keep only those whose sources describe them in this category." %
                      frame.category, "at least one competitor with identity evidence"))
        if any(c.get("relation") == "irrelevant" and c.get("verified") for c in comps):
            add(Issue(_iid(role, "irrelevant-verified"), role, "high", "an irrelevant entity is marked verified",
                      "Remove it.", "no irrelevant verified competitor"))
        unresolved = [c.get("name") for c in comps if c.get("relation") == "unresolved"]
        if unresolved:
            add(Issue(_iid(role, "unresolved-identity"), role, "low",
                      "identity unresolved for: %s" % ", ".join(unresolved[:5]),
                      "Search each name together with the product category and official domain.",
                      "each listed competitor has identity evidence or is removed"))
    from . import substance
    if role == "customer":
        out += substance.customer(output, frame, products)
    elif role == "competitor":
        out += substance.competitor(output, frame)
    elif role == "market":
        out += substance.market(output, frame, claims)
    elif role == "technical":
        out += substance.technical(output, frame, products)
    elif role == "financial":
        out += substance.financial(output)
    elif "scenarios" in output or _is_risk(role):
        out += substance.risk(role, output, frame, products)
    else:
        out += substance.other_specialist(role, output, products)
    seen = set()
    return [i for i in out if not (i.id in seen or seen.add(i.id))]


def _is_risk(role: str) -> bool:
    from .agents.specs import is_risk_role
    return is_risk_role(role)


def score(issues: Sequence[Issue]) -> int:
    """Lower is better."""
    return sum(SEVERITY_WEIGHT.get(i.severity, 1) for i in issues)


def fingerprint(output: dict) -> str:
    data = {k: v for k, v in (output or {}).items() if not str(k).startswith("__")}
    return hashlib.sha1(json.dumps(data, sort_keys=True, default=str).lower().encode()).hexdigest()[:12]


class Tracker:
    """Issue register for one run. Issues keep their id across rounds, so progress is measurable."""

    def __init__(self) -> None:
        self.issues: Dict[str, Issue] = {}

    def update(self, section: str, found: Sequence[Issue], origin: str = "rule") -> None:
        """Replace the open rule issues of a section with a fresh check; resolve the ones no longer found."""
        found_ids = {i.id for i in found}
        for iid, iss in self.issues.items():
            if iss.section == section and iss.origin == origin and iss.status == "open" and iid not in found_ids:
                iss.status = "resolved"
        for i in found:
            cur = self.issues.get(i.id)
            if cur is None:
                self.issues[i.id] = i
            else:
                cur.message, cur.instructions, cur.severity = i.message, i.instructions, i.severity
                if cur.status == "resolved":
                    cur.status = "open"  # regression
                    cur.history.append({"event": "reopened"})

    def add_critic(self, section: str, text: str, instructions: str, severity: str = "medium",
                   fields: Sequence[str] = (), acceptance: str = "") -> Issue:
        iid = critic_id(section, text)
        cur = self.issues.get(iid)
        if cur is None:  # the critic rarely repeats itself verbatim: match near-duplicates by word overlap
            words = terms(text)
            for other in self.issues.values():
                if other.section == section and other.origin == "critic":
                    ow = terms(other.message)
                    if words and ow and len(words & ow) / len(words | ow) >= 0.5:
                        cur = other
                        break
        if cur is not None:
            if cur.status == "resolved":
                cur.status = "open"
                cur.history.append({"event": "critic raised it again"})
            cur.instructions = instructions or cur.instructions
            return cur
        iss = Issue(iid, section, severity if severity in SEVERITY_WEIGHT else "medium", text,
                    instructions or text, acceptance or "the reviewer no longer raises this issue", list(fields), "critic")
        if "founder_test" in fields or is_founder_task(instructions) and not re.search(
                r"\b(search|find|cite|look up|source)\b", instructions or "", re.I):
            iss.action = "founder"
        self.issues[iid] = iss
        return iss

    def open(self, section: Optional[str] = None) -> List[Issue]:
        return [i for i in self.issues.values() if i.status == "open" and (section is None or i.section == section)]

    def select(self, max_sections: int = 3, per_section: int = 5) -> Dict[str, List[Issue]]:
        """Highest severity first; issues that already failed MAX_ATTEMPTS retries are retired as unresolved, so a
        repetitive automatic check can never crowd out a more consequential finding forever."""
        for i in self.open():
            if i.action == "founder":
                i.status = "founder_task"
                i.history.append({"event": "needs a real-world test; moved to the founder's validation plan"})
                continue
            if i.attempts >= MAX_ATTEMPTS:
                i.status = "unresolved"
                i.history.append({"event": "retired after %d attempts without resolution" % i.attempts})
        cands = sorted(self.open(), key=lambda i: (SEVERITY_RANK.get(i.severity, 2), i.attempts,
                                                   0 if i.origin == "critic" else 1))
        chosen: Dict[str, List[Issue]] = {}
        for i in cands:
            if i.section not in chosen and len(chosen) >= max_sections:
                continue
            bucket = chosen.setdefault(i.section, [])
            if len(bucket) < per_section:
                bucket.append(i)
        return chosen

    def to_list(self) -> List[dict]:
        return [i.to_dict() for i in self.issues.values()]

    def counts(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for i in self.issues.values():
            out.setdefault(i.status, {}).setdefault(i.severity, 0)
            out[i.status][i.severity] += 1
        return out


def corrections_text(targets: Sequence[Issue]) -> str:
    """Full corrective instructions handed to the retrying agent (nothing is dropped)."""
    lines = ["CORRECTIONS REQUIRED (fix every item; keep everything else that was correct):"]
    lines += [i.brief() for i in targets]
    return "\n".join(lines)


@dataclass
class RetryOutcome:
    label: str  # improved | partially_improved | no_progress | unchanged | worse | failed
    kept: str  # "new" | "previous"
    resolved: List[str]
    unresolved: List[str]
    new_issues: List[str]
    before_score: int
    after_score: int
    same_answer: bool
    repeated_queries: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_retry(before: Optional[dict], after: Optional[dict], before_issues: Sequence[Issue],
                   after_issues: Sequence[Issue], targets: Sequence[Issue], failed: bool = False,
                   repeated_queries: int = 0) -> RetryOutcome:
    """Compare two answers using the same deterministic checks. Valid JSON alone is never 'improved'."""
    tids = [t.id for t in targets]
    after_ids = {i.id for i in after_issues}
    before_ids = {i.id for i in before_issues}
    b, a = score(before_issues), score(after_issues)
    if failed or after is None:
        return RetryOutcome("failed", "previous", [], tids, [], b, b, False, repeated_queries)
    same = before is not None and fingerprint(before) == fingerprint(after)
    rule_targets = [t for t in targets if t.origin != "critic"]
    resolved = [t.id for t in rule_targets if t.id not in after_ids]
    unresolved = [t.id for t in rule_targets if t.id in after_ids]
    new = sorted(after_ids - before_ids)
    if same:
        return RetryOutcome("unchanged", "previous", [], tids, [], b, b, True, repeated_queries)
    if before is None:
        return RetryOutcome("improved" if not unresolved else "partially_improved", "new", resolved, unresolved, new,
                            b, a, False, repeated_queries)
    if a > b:
        return RetryOutcome("worse", "previous", [], tids, new, b, a, False, repeated_queries)
    if a < b and not unresolved:
        label = "improved"
    elif a < b or resolved:
        label = "partially_improved"
    else:
        label = "no_progress"
    kept = "new" if (a < b or (a == b and resolved)) else "previous"
    return RetryOutcome(label, kept, resolved, unresolved, new, b, a, False, repeated_queries)
