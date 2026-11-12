"""Bounded adaptive research: the agent asks for searches and page fetches; Python validates and runs them.

    seed queries (templates)  ->  relevance check  ->  [planner proposes an action -> validate -> execute]*  ->  pack

The planner (the section's model) only ever returns a small JSON *action*:

    {"missing": "...", "action": "search" | "fetch" | "finish", "tool": "web_search", "query": "...",
     "source_id": "E12", "reason": "..."}

Python decides whether the action is allowed (known tool, query shape, no repeats, fetch only URLs that are already in
the evidence ledger and are public http(s) pages, budgets) and executes it. Nothing the model writes is ever run as
code or shell. When the planner proposes something invalid or repetitive, a deterministic reformulation is used
instead, so a failed search is never retried verbatim.
"""
from __future__ import annotations

import ipaddress
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from . import retrieval
from .relevance import RelevanceBook, terms
from .tools import ALL_TOOLS, get_tools

ACTIONS = ("search", "fetch", "finish")
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "missing": {"type": "string"},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "tool": {"type": "string", "enum": list(ALL_TOOLS)},
        "query": {"type": "string"},
        "source_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["action"],
}
ACTION_TEXT = ('{"missing": "<what evidence is still missing>", "action": "search|fetch|finish", '
               '"tool": "web_search|news_search|wikipedia|hn_search", "query": "<new search query, max 12 words>", '
               '"source_id": "<E-id of a listed result to read in full>", "reason": "<one short sentence>"}')


@dataclass
class Limits:
    """Per-section limits. Run-wide limits live in RunLimits and are shared by every section."""

    searches: int = 6
    fetches: int = 3
    planner_calls: int = 2
    seconds: float = 300.0
    target_relevant: int = 6
    reserve_searches: int = 0  # run-level units this section must leave for later work
    reserve_fetches: int = 0


class RunLimits:
    def __init__(self, searches: int = 45, fetches: int = 18) -> None:
        self.max_searches, self.max_fetches = searches, fetches
        self.searches = self.fetches = 0
        self._lock = threading.Lock()

    def left(self, kind: str) -> int:
        return (self.max_searches - self.searches) if kind == "search" else (self.max_fetches - self.fetches)

    def take(self, kind: str, reserve: int = 0) -> bool:
        """Use one unit unless that would eat into `reserve` (units kept for later sections, review retries and
        final corrections). Early sections therefore cannot consume the whole run budget."""
        with self._lock:
            if kind == "search" and self.searches < self.max_searches - max(0, reserve):
                self.searches += 1
                return True
            if kind == "fetch" and self.fetches < self.max_fetches - max(0, reserve):
                self.fetches += 1
                return True
            return False

    def to_dict(self) -> dict:
        return {"searches": self.searches, "max_searches": self.max_searches,
                "fetches": self.fetches, "max_fetches": self.max_fetches}


@dataclass
class SectionResearch:
    role: str
    ids: List[str] = field(default_factory=list)
    queries: List[dict] = field(default_factory=list)  # {"tool", "query", "results", "relevant", "origin"}
    actions: List[dict] = field(default_factory=list)  # validated / rejected planner actions
    fetched: List[str] = field(default_factory=list)
    limitation: str = ""
    stopped: str = ""  # why research ended

    def to_dict(self) -> dict:
        return {"role": self.role, "ids": self.ids, "queries": self.queries, "actions": self.actions,
                "fetched": self.fetched, "limitation": self.limitation, "stopped": self.stopped}


def norm_query(q: str) -> str:
    return " ".join(sorted(terms(q)))


_PRIVATE_HOSTS = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "169.254.", "::1", "[::1]")


def public_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or host.endswith((".local", ".internal", ".lan")):
        return False
    if host.startswith(_PRIVATE_HOSTS) or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host):
        return False
    try:
        return not ipaddress.ip_address(host).is_private
    except ValueError:
        return True  # a hostname, not an IP literal


def validate_action(raw, *, tried: Sequence[str], allowed_tools: Sequence[str], ledger, visible_ids: Sequence[str],
                    fetched: Sequence[str], fetchable: Callable[[str], bool] = retrieval._fetchable,
                    can_search: bool = True, can_fetch: bool = True):
    """Return (clean action dict, None) or (None, reason). Only the three known actions are possible."""
    if not isinstance(raw, dict):
        return None, "not a JSON object"
    action = str(raw.get("action", "")).strip().lower()
    if action not in ACTIONS:
        return None, "unknown action %r" % action[:20]
    out = {"action": action, "missing": str(raw.get("missing", ""))[:200], "reason": str(raw.get("reason", ""))[:200]}
    if action == "finish":
        return out, None
    if action == "search":
        if not can_search:
            return None, "search budget exhausted: finish instead"
        tool = str(raw.get("tool") or "web_search").strip()
        if tool not in allowed_tools:
            return None, "tool %r is not available" % tool[:30]
        query = " ".join(str(raw.get("query", "")).split())
        if not (3 <= len(query) <= 120):
            return None, "query must be 3-120 characters"
        if re.search(r"https?://|[;|`$<>{}\\]", query):
            return None, "query contains URLs or control characters"
        if len(terms(query)) < 1:
            return None, "query has no content words"
        if norm_query(query) in {norm_query(t) for t in tried}:
            return None, "repeats an earlier query"
        out.update(tool=tool, query=query)
        return out, None
    if not can_fetch:
        return None, "page-read budget exhausted: search or finish instead"
    sid = str(raw.get("source_id", "")).strip().strip("[]").upper()
    src = ledger.get(sid)
    if src is None or sid not in visible_ids:
        return None, "fetch must name a listed result id"
    if not public_url(src.url) or not fetchable(src.url):
        return None, "page cannot be fetched (not a public HTML page)"
    if src.url in fetched:
        return None, "page already read"
    out.update(source_id=sid, url=src.url)
    return out, None


def reformulate(query: str, frame, attempt: int, tried: Sequence[str]) -> Optional[str]:
    """Deterministic alternatives when a search returned nothing relevant (never the same query twice)."""
    base = " ".join(w for w in query.split() if w.lower() not in ("best", "top", "the"))
    ctx = frame.search_context()
    options = [
        "%s %s" % (base, ctx),
        "%s %s" % (" ".join(sorted(frame.anchors)), " ".join(base.split()[-3:])),
        "%s %s" % (frame.category or ctx, "forum discussion"),
    ]
    if frame.geography and frame.geography.lower() in base.lower():
        options.insert(0, re.sub(re.escape(frame.geography), "", base, flags=re.I) + " " + " ".join(sorted(frame.anchors)))
    seen = {norm_query(t) for t in tried}
    for cand in options[attempt % len(options):] + options[: attempt % len(options)]:
        cand = " ".join(cand.split())
        if cand and norm_query(cand) not in seen:
            return cand
    return None


class SectionResearcher:
    """Runs the bounded loop for one section. `planner(prompt_status) -> dict|None` is the model call."""

    def __init__(self, ledger, index, book: RelevanceBook, run_limits: RunLimits, limits: Limits,
                 emit: Callable[..., None], deadline: Callable[[], float], workers: int = 4) -> None:
        self.ledger, self.index, self.book = ledger, index, book
        self.run_limits, self.limits = run_limits, limits
        self.emit, self.deadline, self.workers = emit, deadline, workers

    # -- execution ------------------------------------------------------------
    def _search(self, res: SectionResearch, tool: str, query: str, origin: str) -> int:
        if not self.run_limits.take("search", self.limits.reserve_searches):
            res.stopped = res.stopped or "run search budget exhausted"
            return -1
        self.emit(res.role, "searching", "%s: %s" % (tool, query[:70]))
        ids = retrieval.run_queries([retrieval.Query(res.role, tool, query)], self.ledger, 1).get(res.role, [])
        relevant = self.book.relevant_ids(ids, self.ledger)
        res.queries.append({"tool": tool, "query": query, "results": len(ids), "relevant": len(relevant),
                            "origin": origin})
        res.ids += [i for i in ids if i not in res.ids]
        return len(relevant)

    def _fetch(self, res: SectionResearch, url: str) -> bool:
        res.fetched.append(url)  # recorded even when it cannot run, so the same request is never accepted again
        if not self.run_limits.take("fetch", self.limits.reserve_fetches):
            res.stopped = res.stopped or "run fetch budget exhausted"
            return False
        self.emit(res.role, "reading", url[:90])
        return retrieval.fetch_url(url, self.index)

    def can(self, kind: str, res: SectionResearch, searches: int) -> bool:
        if kind == "search":
            return searches < self.limits.searches and self.run_limits.left("search") > self.limits.reserve_searches
        return len(res.fetched) < self.limits.fetches and self.run_limits.left("fetch") > self.limits.reserve_fetches

    def relevant_count(self, res: SectionResearch) -> int:
        return len(self.book.relevant_ids(res.ids, self.ledger, minimum="relevant"))

    def _auto_fetch(self, res: SectionResearch, n: int) -> None:
        """Read the most relevant result pages in full (deterministic)."""
        ranked = sorted(self.book.relevant_ids(res.ids, self.ledger), key=lambda i: -self.book.of(self.ledger.get(i)).score)
        for sid in ranked:
            if n <= 0 or len(res.fetched) >= self.limits.fetches:
                break
            src = self.ledger.get(sid)
            if public_url(src.url) and retrieval._fetchable(src.url) and src.url not in res.fetched \
                    and src.url not in self.index.docs:
                if self._fetch(res, src.url):
                    n -= 1

    # -- the loop -------------------------------------------------------------
    def run(self, role: str, question: str, seeds: Sequence[retrieval.Query], planner=None,
            prior: Optional[SectionResearch] = None, avoid: Sequence[str] = ()) -> SectionResearch:
        started = time.monotonic()
        res = SectionResearch(role)
        if prior is not None:  # a retry continues from what is already known and never repeats a query
            res.ids = list(prior.ids)
            res.queries = [dict(q) for q in prior.queries]
            res.fetched = list(prior.fetched)
        tools = list(get_tools(list(ALL_TOOLS)))
        tried = [q["query"] for q in res.queries] + list(avoid)

        def out_of_time() -> bool:
            return time.monotonic() - started > self.limits.seconds or self.deadline() < 5

        searches = 0
        for q in seeds:
            if searches >= self.limits.searches or out_of_time():
                break
            if norm_query(q.text) in {norm_query(t) for t in tried}:
                continue
            tool = q.tool if q.tool in tools else ("news_search" if "news_search" in tools else None)
            if tool is None:
                continue
            n = self._search(res, tool, q.text, "seed")
            if n < 0:
                break
            tried.append(q.text)
            searches += 1
            if n == 0:  # zero relevant results: try a reformulation instead of moving on blindly
                alt = reformulate(q.text, self.book.frame, searches, tried)
                if alt and searches < self.limits.searches:
                    if self._search(res, tool, alt, "reformulated") < 0:
                        break
                    tried.append(alt)
                    searches += 1
        self._auto_fetch(res, 2)

        calls = 0
        rejected_streak = 0
        while planner is not None and calls < self.limits.planner_calls and not out_of_time():
            if not self.can("search", res, searches) and not self.can("fetch", res, searches):
                res.stopped = "no search or page-read budget left for this section"
                break
            if self.relevant_count(res) >= self.limits.target_relevant and calls > 0:
                res.stopped = "enough relevant evidence"
                break
            calls += 1
            self.emit(role, "planning", "step %d: deciding what evidence is missing" % calls)
            visible = sorted(res.ids, key=lambda i: -self.book.of(self.ledger.get(i)).score)[:10]
            raw = planner(self.status_text(res, question, visible, tried, searches))
            action, why = validate_action(raw, tried=tried, allowed_tools=tools, ledger=self.ledger,
                                          visible_ids=visible, fetched=res.fetched + list(self.index.docs),
                                          can_search=self.can("search", res, searches),
                                          can_fetch=self.can("fetch", res, searches))
            rejected_streak = rejected_streak + 1 if action is None else 0
            entry = {"step": calls, "proposed": raw if isinstance(raw, dict) else None, "accepted": action is not None,
                     "rejected_because": why or ""}
            if action is None:  # invalid or repetitive: use a deterministic reformulation instead
                last = tried[-1] if tried else question
                alt = reformulate(last, self.book.frame, calls, tried)
                if alt and self.can("search", res, searches):
                    action = {"action": "search", "tool": "web_search" if "web_search" in tools else tools[0],
                              "query": alt, "reason": "fallback reformulation"}
                    entry["fallback"] = action
            res.actions.append(entry)
            if rejected_streak >= 2 and action is not None and entry.get("fallback"):
                pass  # the fallback search still runs once
            elif rejected_streak >= 2:
                res.stopped = "planner kept proposing actions that cannot run"
                break
            if action is None or action["action"] == "finish":
                res.stopped = "planner finished" if action else "no valid action"
                break
            if action["action"] == "search":
                if searches >= self.limits.searches:
                    res.stopped = "section search budget exhausted"
                    break
                if self._search(res, action["tool"], action["query"], "planner") < 0:
                    break
                tried.append(action["query"])
                searches += 1
                self._auto_fetch(res, 1)
            elif action["action"] == "fetch":
                if len(res.fetched) >= self.limits.fetches:
                    res.stopped = "section fetch budget exhausted"
                    break
                self._fetch(res, action["url"])
        if out_of_time() and not res.stopped:
            res.stopped = "section time budget reached"
        if not res.stopped:
            res.stopped = "planned steps completed"
        if self.relevant_count(res) == 0 and not self.book.relevant_ids(res.ids, self.ledger):
            res.limitation = ("No relevant evidence found after %d searches (%s)."
                              % (len(res.queries), "; ".join(q["query"] for q in res.queries[-4:])))
        return res

    def status_text(self, res: SectionResearch, question: str, visible: Sequence[str], tried: Sequence[str],
                    searches: int = 0) -> str:
        lines = ["QUESTION: %s" % question, "RESEARCH FRAME: %s" % self.book.frame.describe(), "QUERIES ALREADY TRIED:"]
        for q in res.queries[-6:]:
            lines.append("- %s: %s -> %d results, %d relevant" % (q["tool"], q["query"], q["results"], q["relevant"]))
        lines.append("UNREAD RESULTS YOU MAY FETCH (id, relevance, title):")
        unread = [sid for sid in visible if self.ledger.get(sid).url not in res.fetched
                  and self.ledger.get(sid).url not in self.index.docs]
        for sid in unread[:8]:
            src = self.ledger.get(sid)
            lines.append("- %s (%s) %s" % (sid, self.book.of(src).label, src.title[:90]))
        if not unread:
            lines.append("- (none: every listed page has been read)")
        lines.append("BUDGET LEFT: %d searches, %d page reads%s." % (
            max(0, self.limits.searches - searches) if self.can("search", res, searches) else 0,
            max(0, self.limits.fetches - len(res.fetched)) if self.can("fetch", res, searches) else 0,
            " (do not request a fetch)" if not self.can("fetch", res, searches) else ""))
        if res.actions and res.actions[-1].get("rejected_because"):
            lines.append("YOUR LAST ACTION WAS REJECTED: %s." % res.actions[-1]["rejected_because"])
        lines.append("Relevant results so far: %d (target %d)." % (self.relevant_count(res), self.limits.target_relevant))
        lines.append("Choose ONE next action. Use a NEW query (different words) if earlier ones found nothing relevant; "
                     "fetch a listed id to read a promising page; finish when the evidence answers the question or "
                     "further searching is unlikely to help.")
        return "\n".join(lines)
