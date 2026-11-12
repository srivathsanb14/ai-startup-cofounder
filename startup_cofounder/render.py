"""One entry point for turning assessment data into the report model and its Markdown.

report-v4 (question-driven design) is the default. Saved runs from the section design are re-rendered as report-v4
from their saved evidence (no new searches; no model calls unless an extraction function is passed). report-v3
remains available for comparison.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from . import memo, memo_v4, report_model, report_v4


def model_for(data: dict, design: str = "v4", extract_fn: Optional[Callable] = None) -> dict:
    if design == "v3":
        if data.get("report_schema") == report_model.SCHEMA and data.get("report"):
            return data["report"]
        return report_model.build(data, regenerated=True)
    if data.get("report_schema") == report_v4.SCHEMA and data.get("report") and extract_fn is None:
        return data["report"]
    return report_v4.build(data, regenerated=not data.get("v4"), extract_fn=extract_fn,
                           illustrative=bool((data.get("v4") or {}).get("illustrative_projection")))


def render(model: dict, data: dict) -> Tuple[str, str]:
    """(decision memo, evidence appendix) for either schema."""
    if model.get("schema") == report_v4.SCHEMA:
        text = memo_v4.render_memo(model)
        return text, memo_v4.render_appendix(model, memo.render_appendix(model["v3"], data))
    return memo.render_memo(model), memo.render_appendix(model, data)
