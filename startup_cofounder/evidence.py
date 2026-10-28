"""Evidence ledger: every web result gets an id so claims can be traced to sources.

This is the core anti-hallucination mechanism. Agents must cite ids, and each
cited claim is *checked against the cited text*:

1. a claim labelled "fact" with no valid citation becomes an "estimate";
2. a "fact" whose numbers (e.g. "$5.2B", "40%") do not appear in the cited
   sources becomes an "estimate";
3. a "fact" that shares almost no wording with its cited sources becomes an
   "estimate".

Downgrades keep a human-readable note so the report can explain them.
"""
from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional

STOPWORDS = {
    "this", "that", "with", "from", "have", "has", "been", "were", "will", "their", "which", "about",
    "more", "than", "into", "also", "such", "they", "them", "these", "those", "other", "over", "most",
    "some", "many", "much", "very", "when", "what", "where", "while", "would", "could", "should",
    "market", "company", "companies", "customers", "users", "business",
}


@dataclass
class Source:
    id: str
    title: str
    url: str
    snippet: str
    tool: str

    @property
    def text(self) -> str:
        return "%s %s" % (self.title, self.snippet)


@dataclass
class Finding:
    claim: str
    kind: str  # "fact" | "estimate"
    source_ids: List[str] = field(default_factory=list)
    downgraded: bool = False
    note: str = ""  # why a claim was downgraded

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceLedger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: Dict[str, Source] = {}
        self._by_url: Dict[str, Source] = {}

    def add(self, tool: str, items: Iterable[dict]) -> List[Source]:
        added: List[Source] = []
        with self._lock:
            for item in items:
                url = (item.get("url") or "").strip()
                if url and url in self._by_url:
                    added.append(self._by_url[url])
                    continue
                src = Source(
                    id="E%d" % (len(self._by_id) + 1),
                    title=(item.get("title") or url or "untitled").strip(),
                    url=url,
                    snippet=(item.get("snippet") or "").strip(),
                    tool=tool,
                )
                self._by_id[src.id] = src
                if url:
                    self._by_url[url] = src
                added.append(src)
        return added

    def get(self, source_id: str) -> Optional[Source]:
        return self._by_id.get(source_id)

    def all(self) -> List[Source]:
        with self._lock:
            return list(self._by_id.values())

    def corpus(self) -> str:
        """Lower-cased text of every collected source (used to verify named entities)."""
        return " ".join((s.text + " " + s.url).lower() for s in self.all())

    def valid_ids(self, ids: Iterable) -> List[str]:
        out: List[str] = []
        for raw in ids or []:
            sid = str(raw).strip().strip("[]").upper()
            if sid in self._by_id and sid not in out:
                out.append(sid)
        return out


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}


def _numbers(text: str) -> set:
    nums = set()
    for tok in re.findall(r"\d[\d,]*\.?\d*", text):
        tok = tok.replace(",", "").rstrip(".")
        if len(tok.replace(".", "")) >= 2:  # single digits ("3 competitors") are too noisy
            nums.add(tok)
    return nums


def grounding_problem(claim: str, sources: List[Source]) -> Optional[str]:
    """Return why `claim` is not supported by `sources`, or None if it looks supported."""
    corpus = " ".join(s.text for s in sources)
    missing = sorted(_numbers(claim) - _numbers(corpus))
    if missing:
        return "number(s) %s not found in cited sources" % ", ".join(missing)
    claim_words = _words(claim)
    needed = min(2, len(claim_words))
    if len(claim_words & _words(corpus)) < needed:
        return "claim shares too little wording with its cited sources"
    return None


def normalize_findings(raw, ledger: EvidenceLedger) -> List[Finding]:
    """Validate agent-reported findings against the ledger."""
    findings: List[Finding] = []
    if not isinstance(raw, list):
        return findings
    for item in raw:
        if isinstance(item, str):
            item = {"claim": item, "kind": "estimate"}
        if not isinstance(item, dict) or not str(item.get("claim", "")).strip():
            continue
        claim = str(item["claim"]).strip()
        kind = "fact" if str(item.get("kind", "")).lower() == "fact" else "estimate"
        ids = ledger.valid_ids(item.get("source_ids") or item.get("sources") or [])
        downgraded, note = False, ""
        if kind == "fact":
            if not ids:
                kind, downgraded, note = "estimate", True, "no valid citation"
            else:
                problem = grounding_problem(claim, [ledger.get(i) for i in ids])
                if problem:
                    kind, downgraded, note = "estimate", True, problem
        findings.append(Finding(claim, kind, ids, downgraded, note))
    return findings
