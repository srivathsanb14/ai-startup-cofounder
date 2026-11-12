from __future__ import annotations

import json
import re
from typing import Optional


def _matching_brace(text: str, start: int) -> Optional[int]:
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def extract_json(text: str) -> dict:
    """Pull the first valid JSON object out of an LLM reply.

    Handles <think> blocks, markdown fences and prose around the object, which
    small open-source models produce regularly.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    candidates = []
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    for chunk in candidates:
        start = chunk.find("{")
        while start != -1:
            end = _matching_brace(chunk, start)
            if end is not None:
                try:
                    obj = json.loads(chunk[start : end + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
            start = chunk.find("{", start + 1)
    raise ValueError("no JSON object found in model reply")
