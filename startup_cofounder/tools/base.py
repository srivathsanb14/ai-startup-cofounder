from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

USER_AGENT = "Mozilla/5.0 (compatible; StartupCofounderBot/0.1; academic project)"


class OfflineError(RuntimeError):
    pass


@dataclass
class ToolResult:
    """sources: list of {title, url, snippet}. text: extra note or error message."""

    sources: List[dict] = field(default_factory=list)
    text: str = ""
    error: bool = False


@dataclass
class Tool:
    name: str
    description: str
    args: Dict[str, str]
    fn: Callable[..., ToolResult]

    def signature(self) -> str:
        arglist = ", ".join("%s: %s" % (k, v) for k, v in self.args.items())
        return "- %s(%s): %s" % (self.name, arglist, self.description)

    def run(self, **kwargs) -> ToolResult:
        try:
            clean = {k: kwargs[k] for k in self.args if k in kwargs}
            return self.fn(**clean)
        except OfflineError:
            return ToolResult(text="offline mode: network tools are disabled", error=True)
        except Exception as exc:  # tools must never crash an agent
            return ToolResult(text="tool error: %s" % exc, error=True)


class Http:
    """requests wrapper with an on-disk cache so demos and evals are repeatable."""

    cache_dir: Optional[Path] = None
    offline: bool = False
    ttl_seconds: int = 24 * 3600

    @classmethod
    def configure(cls, cache_dir: Optional[Path], offline: bool) -> None:
        cls.cache_dir = Path(cache_dir) if cache_dir else None
        cls.offline = offline
        if cls.cache_dir:
            cls.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get(cls, url: str, params: Optional[dict] = None, timeout: int = 12,
            headers: Optional[dict] = None) -> str:
        """headers are sent but deliberately excluded from the cache key (they may hold API keys)."""
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
        cached = cls.cache_dir / (key + ".txt") if cls.cache_dir else None
        if cached is not None and cached.exists() and time.time() - cached.stat().st_mtime < cls.ttl_seconds:
            return cached.read_text()
        if cls.offline:
            raise OfflineError()
        resp = requests.get(url, params=params, timeout=timeout,
                            headers={"User-Agent": USER_AGENT, **(headers or {})})
        resp.raise_for_status()
        if cached is not None:
            cached.write_text(resp.text)
        return resp.text
