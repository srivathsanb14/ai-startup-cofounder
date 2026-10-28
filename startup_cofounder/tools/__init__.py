import os
from typing import Dict, List

from .base import Http, Tool, ToolResult
from .search import ALL_TOOLS


def disabled_tools() -> set:
    """Tools switched off via DISABLED_TOOLS=web_search,fetch_page (comma separated)."""
    return {t.strip() for t in os.environ.get("DISABLED_TOOLS", "").split(",") if t.strip()}


def get_tools(names: List[str]) -> Dict[str, Tool]:
    off = disabled_tools()
    return {n: ALL_TOOLS[n] for n in names if n not in off}


__all__ = ["Http", "Tool", "ToolResult", "ALL_TOOLS", "get_tools", "disabled_tools"]
