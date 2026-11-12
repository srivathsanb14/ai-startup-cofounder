"""Staged competitor discovery helpers (pure functions; the pipeline wires them to the model and tools).

    candidates  = model extracts company names from search results
    ranking     = code counts how often each name appears in ALL evidence and drops names never seen
    profiles    = one targeted search + extraction per top candidate
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence, Tuple

from .quality import _clean_name, name_seen

GENERIC = {"google", "facebook", "meta", "amazon", "microsoft", "apple", "linkedin", "twitter", "reddit",
           "youtube", "wikipedia", "forbes", "crunchbase"}  # appear everywhere; rarely the competitor itself


def _token(name: str, corpus: str) -> str:
    clean = _clean_name(name)
    if not clean:
        return ""
    token = clean if clean in corpus else clean.split()[0]
    return token if len(token) >= 4 else ""


def mention_count(name: str, corpus: str) -> int:
    token = _token(name, corpus)
    return len(re.findall(r"\b%s\b" % re.escape(token), corpus)) if token else 0


def source_breadth(name: str, corpus: str, docs: Sequence[str]) -> int:
    """In how many distinct sources the name appears. A name repeated inside one niche article scores 1."""
    token = _token(name, corpus)
    if not token:
        return 0
    pattern = re.compile(r"\b%s\b" % re.escape(token))
    return sum(1 for d in docs if pattern.search(d))


def rank_candidates(raw: Iterable, corpus: str, skip: Iterable[str] = (), allow_unseen: bool = False,
                    docs: Sequence[str] = ()) -> List[str]:
    """Distinct candidate names, widely mentioned first.

    With `docs` (one text per source) names are ordered by how many distinct sources mention them, then by total
    mentions, so well-known players beat a name that is only frequent inside one niche article.

    Names never seen in the evidence are dropped (model hallucinations) unless there is no evidence at all.
    """
    skip_clean = {_clean_name(s) for s in skip}
    best: Dict[str, Tuple[str, int, int, int]] = {}  # clean -> (display, breadth, count, first position)
    for pos, item in enumerate(raw or []):
        name = (item.get("name") if isinstance(item, dict) else str(item)).strip() if item else ""
        clean = _clean_name(name)
        if not clean or clean in skip_clean or clean in GENERIC or clean in best:
            continue
        if corpus and not name_seen(name, corpus) and not allow_unseen:
            continue
        count = mention_count(name, corpus)
        best[clean] = (name, source_breadth(name, corpus, docs) if docs else count, count, pos)
    ordered = sorted(best.values(), key=lambda v: (-v[1], -v[2], v[3]))
    return [v[0] for v in ordered]


def profile_queries(name: str, category: str) -> List[Tuple[str, str]]:
    return [("web_search", "%s pricing plans" % name), ("web_search", "%s reviews pros and cons" % name),
            ("news_search", name), ("wikipedia", name)]


def merge_competitors(existing: Sequence[dict], new: Sequence[dict]) -> List[dict]:
    """Union by cleaned name, keeping the first occurrence, confirmed competitors first."""
    seen, merged = set(), []
    for c in list(existing) + list(new):
        key = _clean_name(c.get("name", ""))
        if key and key not in seen:
            seen.add(key)
            merged.append(c)
    merged.sort(key=lambda c: not c.get("verified", False))
    return merged
