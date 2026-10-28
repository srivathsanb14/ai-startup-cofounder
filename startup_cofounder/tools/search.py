from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .base import Http, OfflineError, Tool, ToolResult


def _clean(text: str, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _brave(query: str, key: str) -> ToolResult:
    text = Http.get("https://api.search.brave.com/res/v1/web/search", {"q": query, "count": 8},
                    headers={"X-Subscription-Token": key, "Accept": "application/json"})
    results = (json.loads(text).get("web") or {}).get("results", [])
    sources = [{"title": _clean(r.get("title", ""), 150), "url": r.get("url", ""),
                "snippet": _clean(BeautifulSoup(r.get("description", ""), "html.parser").get_text())}
               for r in results[:8]]
    return ToolResult(sources=sources, text="" if sources else "no results")


def _searxng(query: str, base: str) -> ToolResult:
    text = Http.get(base.rstrip("/") + "/search", {"q": query, "format": "json"})
    results = json.loads(text).get("results", [])
    sources = [{"title": _clean(r.get("title", ""), 150), "url": r.get("url", ""),
                "snippet": _clean(r.get("content", ""))} for r in results[:8]]
    return ToolResult(sources=sources, text="" if sources else "no results")


def web_search(query: str) -> ToolResult:
    """Provider order: Brave (BRAVE_API_KEY), SearXNG (SEARXNG_URL), then DuckDuckGo HTML."""
    brave_key = os.environ.get("BRAVE_API_KEY", "").strip()
    searx = os.environ.get("SEARXNG_URL", "").strip()
    for provider in ((lambda: _brave(query, brave_key)) if brave_key else None,
                     (lambda: _searxng(query, searx)) if searx else None):
        if provider is None:
            continue
        try:
            result = provider()
        except OfflineError:
            raise
        except Exception:
            continue  # fall through to the next provider
        if result.sources:
            return result
    return _duckduckgo(query)


def _duckduckgo(query: str) -> ToolResult:
    """DuckDuckGo HTML endpoint (no API key); may be blocked by their bot check."""
    html = Http.get("https://html.duckduckgo.com/html/", {"q": query})
    soup = BeautifulSoup(html, "html.parser")
    sources = []
    for block in soup.select("div.result")[:6]:
        link = block.select_one("a.result__a")
        if not link:
            continue
        href = link.get("href", "")
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        snippet = block.select_one(".result__snippet")
        sources.append({"title": _clean(link.get_text(), 150), "url": href,
                        "snippet": _clean(snippet.get_text() if snippet else "")})
    if sources:
        return ToolResult(sources=sources)
    if "anomaly" in html.lower() or "captcha" in html.lower() or "challenge" in html.lower():
        return ToolResult(text="web_search is blocked by the search provider's bot check; "
                               "use news_search, wikipedia or hn_search instead", error=True)
    return ToolResult(text="no results")


def news_search(query: str) -> ToolResult:
    """Google News RSS feed: recent headlines with dates and publishers."""
    xml = Http.get("https://news.google.com/rss/search",
                   {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(xml)
    sources = []
    for item in root.iter("item"):
        if len(sources) >= 8:
            break
        title = item.findtext("title") or ""
        publisher = item.findtext("source") or ""
        date = item.findtext("pubDate") or ""
        sources.append({"title": _clean(title, 200), "url": item.findtext("link") or "",
                        "snippet": "%s | %s" % (publisher, date)})
    return ToolResult(sources=sources, text="" if sources else "no results")


def wikipedia(query: str) -> ToolResult:
    text = Http.get("https://en.wikipedia.org/w/api.php", {
        "action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 3,
        "prop": "extracts", "exintro": 1, "explaintext": 1, "exchars": 700, "format": "json"})
    pages = (json.loads(text).get("query") or {}).get("pages", {})
    sources = [{"title": p.get("title", ""), "url": "https://en.wikipedia.org/?curid=%s" % pid,
                "snippet": _clean(p.get("extract", ""), 700)}
               for pid, p in sorted(pages.items(), key=lambda kv: kv[1].get("index", 99))]
    return ToolResult(sources=sources, text="" if sources else "no results")


def hn_search(query: str) -> ToolResult:
    """Hacker News via Algolia: raw voice-of-customer and builder discussion."""
    text = Http.get("https://hn.algolia.com/api/v1/search", {"query": query, "tags": "story", "hitsPerPage": 8})
    sources = []
    for hit in json.loads(text).get("hits", []):
        url = hit.get("url") or "https://news.ycombinator.com/item?id=%s" % hit.get("objectID")
        sources.append({"title": _clean(hit.get("title", ""), 200), "url": url,
                        "snippet": "%s points, %s comments on Hacker News (%s)" % (
                            hit.get("points", 0), hit.get("num_comments", 0), (hit.get("created_at") or "")[:10])})
    return ToolResult(sources=sources, text="" if sources else "no results")


def fetch_page(url: str) -> ToolResult:
    if not url.startswith(("http://", "https://")):
        return ToolResult(text="url must start with http(s)://", error=True)
    html = Http.get(url, timeout=15)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text() if soup.title else url
    body = _clean(soup.get_text(" "), 2500)
    return ToolResult(sources=[{"title": _clean(title, 150), "url": url, "snippet": body}])


ALL_TOOLS = {
    "web_search": Tool("web_search", "general web search; best for competitors, pricing, product pages",
                       {"query": "string"}, web_search),
    "news_search": Tool("news_search", "recent news headlines; best for market trends, funding, launches",
                        {"query": "string"}, news_search),
    "wikipedia": Tool("wikipedia", "encyclopedia intros; best for industry and company background",
                      {"query": "string"}, wikipedia),
    "hn_search": Tool("hn_search", "Hacker News stories; best for customer pain points and technical feasibility",
                      {"query": "string"}, hn_search),
    "fetch_page": Tool("fetch_page", "download one web page and return its text (use a URL from a prior result)",
                       {"url": "string"}, fetch_page),
}
