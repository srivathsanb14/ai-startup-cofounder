"""Deterministic retrieval: query templates -> parallel searches -> full-page fetch -> relevance-ranked evidence packs.

No LLM is involved here, so this stage is fast, repeatable and cacheable. The model's job starts afterwards,
reading the evidence that was gathered.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .evidence import EvidenceLedger
from .passages import PassageIndex, rank
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


def evidence_pack(question: str, ids: Sequence[str], ledger: EvidenceLedger, index: PassageIndex,
                  n_snippets: int = 10, n_passages: int = 8, passage_chars: int = 650) -> Tuple[str, List[str]]:
    """Most relevant search snippets and full-page passages for `question`, formatted for a prompt.

    Selected passages are registered in the ledger so they can be cited and grounding-checked like any source.
    """
    snippets = [s for s in (ledger.get(i) for i in ids) if s is not None]
    top_snippets = rank(question, snippets, lambda s: s.text, n_snippets)
    urls = []
    for s in snippets:
        if s.url and s.url not in urls:
            urls.append(s.url)
    passages = index.passages(urls)
    top_passages = rank(question, passages, lambda p: p[3], n_passages)

    chosen = list(top_snippets)
    for url, title, i, text in top_passages:
        chosen += ledger.add("passage", [{"title": "%s (excerpt)" % title, "url": "%s#p%d" % (url, i), "snippet": text}])
    lines, out_ids = [], []
    for s in chosen:
        if s.id in out_ids:
            continue
        out_ids.append(s.id)
        lines.append("[%s] %s\n    url: %s\n    %s" % (s.id, s.title, s.url, s.snippet[:passage_chars]))
    return ("\n".join(lines) if lines else "(no evidence could be retrieved)"), out_ids
