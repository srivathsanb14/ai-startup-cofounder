"""Full-page passage retrieval: chunk pages and rank snippets/passages against a question (BM25, no dependencies)."""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from typing import Dict, List, Sequence, Tuple

TOKEN = re.compile(r"[a-z0-9]{3,}")
STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "been", "their",
        "they", "them", "will", "can", "not", "but", "its", "our", "your", "you", "all", "any", "who", "what",
        "how", "why", "which", "about", "into", "than", "more", "most", "also", "such", "These", "those"}
STOP = {s.lower() for s in STOP}


def tokens(text: str) -> List[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def chunk(text: str, size: int = 650, overlap: int = 100, min_len: int = 80) -> List[str]:
    """Split text into ~size-character passages, preferring to cut at sentence ends."""
    text = re.sub(r"\s+", " ", text or "").strip()
    out: List[str] = []
    i = 0
    while i < len(text):
        end = min(len(text), i + size)
        if end < len(text):
            cut = text.rfind(". ", i + size // 2, end)
            if cut != -1:
                end = cut + 1
        out.append(text[i:end].strip())
        if end >= len(text):
            break
        i = max(end - overlap, i + 1)
    return [c for c in out if len(c) >= min_len]


def bm25(query: str, docs: Sequence[str], k1: float = 1.4, b: float = 0.75) -> List[float]:
    if not docs:
        return []
    q_terms = set(tokens(query))
    counts = [Counter(tokens(d)) for d in docs]
    lengths = [sum(c.values()) for c in counts]
    avg = (sum(lengths) / len(docs)) or 1.0
    df = {t: sum(1 for c in counts if t in c) for t in q_terms}
    n = len(docs)
    scores = []
    for c, length in zip(counts, lengths):
        s = 0.0
        for t in q_terms:
            tf = c.get(t, 0)
            if tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / avg))
        scores.append(s)
    return scores


def rank(query: str, items: Sequence, text_of, k: int) -> List:
    """Top-k items by BM25 relevance to the query (stable for ties; zero-score items only fill empty slots)."""
    scores = bm25(query, [text_of(i) for i in items])
    order = sorted(range(len(items)), key=lambda i: -scores[i])
    return [items[i] for i in order[:k]]


class PassageIndex:
    """Thread-safe store of fetched pages split into passages."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.docs: Dict[str, Tuple[str, List[str]]] = {}

    def add(self, url: str, title: str, text: str) -> int:
        chunks = chunk(text)
        with self._lock:
            self.docs[url] = (title, chunks)
        return len(chunks)

    def passages(self, urls: Sequence[str]) -> List[Tuple[str, str, int, str]]:
        """(url, title, index, text) for every passage of the given pages."""
        out = []
        with self._lock:
            for url in urls:
                if url in self.docs:
                    title, chunks = self.docs[url]
                    out += [(url, title, i, c) for i, c in enumerate(chunks)]
        return out
