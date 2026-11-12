"""Deterministic retrieval: query templates -> parallel searches -> full-page fetch -> relevance-ranked evidence packs.

No LLM is involved here, so this stage is fast, repeatable and cacheable. The model's job starts afterwards,
reading the evidence that was gathered.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .evidence import EvidenceLedger
from .passages import PassageIndex, bm25, rank
from .tools import ALL_TOOLS, get_tools
from .tools.search import page_text

# (tool, template). {category} and {problem} come from the coordinator.
SECTION_QUERIES: Dict[str, List[Tuple[str, str]]] = {
    "customer": [("web_search", "{problem} problems complaints"), ("web_search", "who uses {category} and why"),
                 ("hn_search", "{category}"), ("news_search", "{category} customer survey")],
    "competitor": [("web_search", "alternatives to {category}"), ("web_search", "best {category} companies"),
                   ("web_search", "top {category} startups competitors"), ("news_search", "{category} competitors"),
                   ("wikipedia", "{category}")],
    "market": [("web_search", "{category} market size"), ("web_search", "{category} industry report CAGR forecast"),
               ("news_search", "{category} market growth"), ("wikipedia", "{category} industry")],
    "technical": [("web_search", "how to build {category} architecture technology stack"),
                  ("hn_search", "building {category}"), ("wikipedia", "{category}"),
                  ("web_search", "{category} API infrastructure cost")],
    "financial": [("web_search", "{category} pricing plans per month"),
                  ("web_search", "{category} customer acquisition cost benchmark"), ("news_search", "{category} pricing")],
}

# Second-pass queries used when the review loop finds a section too thin.
FOLLOWUP_QUERIES: Dict[str, List[Tuple[str, str]]] = {
    "customer": [("web_search", "{problem} reddit"), ("news_search", "{problem}"), ("hn_search", "{problem}")],
    "competitor": [("web_search", "{category} competitors comparison"), ("web_search", "{category} vs"),
                   ("news_search", "top {category} companies funding")],
    "market": [("web_search", "{category} TAM total addressable market"),
               ("news_search", "{category} market forecast billion"), ("web_search", "{category} statistics")],
    "technical": [("web_search", "{category} open source"), ("hn_search", "{category} technical challenges")],
}


@dataclass(frozen=True)
class Query:
    section: str
    tool: str
    text: str


def fill(template: str, category: str, problem: str) -> str:
    return " ".join(template.replace("{category}", category).replace("{problem}", problem).split())


def build_queries(sections: Sequence[str], category: str, problem: str, extras: Optional[Dict[str, str]] = None,
                  followup: bool = False) -> List[Query]:
    """Queries for each section; `extras` maps an extra-specialist role to its focus topic."""
    table = FOLLOWUP_QUERIES if followup else SECTION_QUERIES
    queries = [Query(s, tool, fill(t, category, problem)) for s in sections for tool, t in table.get(s, [])]
    for role, focus in (extras or {}).items():
        if sections and role not in sections:
            continue
        queries += [Query(role, "web_search", fill("{category} %s" % focus, category, problem)),
                    Query(role, "news_search", fill("{category} %s" % focus, category, problem)),
                    Query(role, "wikipedia", focus)]
    return queries


def run_queries(queries: Sequence[Query], ledger: EvidenceLedger, workers: int = 8,
                on_event: Optional[Callable[[dict], None]] = None) -> Dict[str, List[str]]:
    """Run searches in parallel; returns section -> evidence ids. Disabled/blocked tools fall back to news search."""
    enabled = get_tools(list(ALL_TOOLS))
    seen = set()
    jobs = []
    for q in queries:
        tool = q.tool if q.tool in enabled else ("news_search" if "news_search" in enabled else None)
        key = (q.section, tool, q.text)
        if tool and key not in seen:
            seen.add(key)
            jobs.append((q.section, tool, q.text))

    def one(job):
        section, tool, text = job
        result = enabled[tool].run(query=text)
        if result.error and not result.sources and tool == "web_search" and "news_search" in enabled:
            result = enabled["news_search"].run(query=text)  # blocked/failed web search -> headlines instead
            tool = "news_search"
        sources = ledger.add(tool, result.sources)
        if on_event:
            on_event({"stage": "retrieval", "status": "search", "detail": "%s: %s (%d)" % (tool, text[:60], len(sources))})
        return section, [s.id for s in sources]

    out: Dict[str, List[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for section, ids in pool.map(one, jobs):
            bucket = out.setdefault(section, [])
            bucket += [i for i in ids if i not in bucket]
    return out


def _fetchable(url: str) -> bool:
    return url.startswith("http") and "news.google.com" not in url and not url.lower().endswith((".pdf", ".zip"))


def fetch_pages(ids_by_section: Dict[str, List[str]], ledger: EvidenceLedger, index: PassageIndex,
                per_section: int = 3, workers: int = 6) -> int:
    """Download the top pages per section in full and index their passages. Returns pages indexed."""
    urls: List[str] = []
    for ids in ids_by_section.values():
        taken = 0
        for sid in ids:
            src = ledger.get(sid)
            if src and _fetchable(src.url) and src.url not in urls and src.url not in index.docs:
                urls.append(src.url)
                taken += 1
                if taken >= per_section:
                    break

    def one(url: str) -> int:
        try:
            title, text = page_text(url)
            return 1 if text and index.add(url, title, text) else 0
        except Exception:
            return 0  # one dead link must not matter

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return sum(pool.map(one, urls))


def fetch_url(url: str, index: PassageIndex) -> bool:
    """Download one page and index its passages. Callers validate the URL first (research.validate_action)."""
    if not _fetchable(url) or url in index.docs:
        return False
    try:
        title, text = page_text(url)
        return bool(text and index.add(url, title, text))
    except Exception:
        return False


def _dupe_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))[:160]


def select_evidence(question: str, ids: Sequence[str], ledger: EvidenceLedger, index: PassageIndex, book=None,
                    n_snippets: int = 10, n_passages: int = 8) -> Tuple[List, List[dict]]:
    """Relevance-gated, de-duplicated evidence for `question`, best first.

    With a RelevanceBook, irrelevant sources are excluded outright (never used to fill slots) and the BM25 order is
    weighted by relevance. Returns (sources, selection log entries).
    """
    snippets = [s for s in (ledger.get(i) for i in ids) if s is not None]
    log: List[dict] = []
    if book is not None:
        kept = []
        for s in snippets:
            rel = book.of(s)
            if rel.label == "irrelevant":
                log.append({"id": s.id, "decision": "excluded", "why": "irrelevant to research frame"})
            else:
                kept.append(s)
        snippets = kept
    scores = bm25(question, [s.text for s in snippets])
    weight = (lambda s: 0.5 + book.of(s).score) if book is not None else (lambda s: 1.0)
    order = sorted(range(len(snippets)), key=lambda i: -(scores[i] * weight(snippets[i])))
    top_snippets = [snippets[i] for i in order if scores[i] > 0 or book is None][:n_snippets]
    urls = []
    for s in snippets:
        base = s.url.split("#p")[0]
        if base and base not in urls:
            urls.append(base)
    passages = index.passages(urls)
    p_scores = bm25(question, [p[3] for p in passages])
    p_order = sorted(range(len(passages)), key=lambda i: -p_scores[i])
    chosen = list(top_snippets)
    for i in p_order[: n_passages * 2]:
        if len([c for c in chosen if c.tool == "passage"]) >= n_passages:
            break
        url, title, j, text = passages[i]
        if p_scores[i] <= 0 and book is not None:
            continue
        src = ledger.add("passage", [{"title": "%s (excerpt)" % title, "url": "%s#p%d" % (url, j), "snippet": text}])[0]
        if book is not None and book.of(src).label == "irrelevant":
            log.append({"id": src.id, "decision": "excluded", "why": "passage irrelevant to research frame"})
            continue
        chosen.append(src)
    out, seen = [], set()
    for s in chosen:
        key = _dupe_key(s.snippet or s.title)
        if s.id in {o.id for o in out}:
            continue
        if key in seen:
            log.append({"id": s.id, "decision": "excluded", "why": "duplicate passage"})
            continue
        seen.add(key)
        out.append(s)
        entry = {"id": s.id, "decision": "selected"}
        if book is not None:
            entry["relevance"] = book.of(s).to_dict()
        log.append(entry)
    return out, log


def format_source(s, chars: int = 650) -> str:
    from .relevance import neutralize
    return "[%s] %s\n    url: %s\n    %s" % (s.id, neutralize(s.title), s.url, neutralize(s.snippet[:chars]))


def evidence_pack(question: str, ids: Sequence[str], ledger: EvidenceLedger, index: PassageIndex,
                  n_snippets: int = 10, n_passages: int = 8, passage_chars: int = 650, book=None) -> Tuple[str, List[str]]:
    """Formatted evidence for a prompt (kept for callers that do not do token fitting themselves)."""
    chosen, _ = select_evidence(question, ids, ledger, index, book, n_snippets, n_passages)
    lines = [format_source(s, passage_chars) for s in chosen]
    return ("\n".join(lines) if lines else "(no evidence could be retrieved)"), [s.id for s in chosen]
