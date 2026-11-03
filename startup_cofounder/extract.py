"""One-shot structured extraction: evidence in, schema-valid JSON out."""
from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from .jsonutil import extract_json

EXTRACT_RULES = """You are given EVIDENCE retrieved from the web. Do the TASK using ONLY that evidence for facts.
Reply with ONE JSON object matching this schema and nothing else:
__SCHEMA__

TODAY: __TODAY__ (note the year of any statistic you use).

RULES:
- Cite evidence ids (e.g. "E3") in "source_ids". Mark a finding "fact" ONLY if a cited item supports it, and every
  number in a fact must appear verbatim in a cited item. Everything else must be marked "estimate".
- Never invent companies, URLs, statistics or quotes. If the evidence is thin, say so in the summary and use estimates.
- Be specific and concrete; prefer named companies, prices and numbers from the evidence over generalities."""


SYNTHESIS_RULES = """Reply with ONE JSON object matching this schema and nothing else:
__SCHEMA__

TODAY: __TODAY__.

RULES:
- Base everything on the research and computed numbers you are given; the computed numbers are authoritative.
- Do not invent facts. Say plainly what is a sourced fact and what is an estimate, and be candid about weak evidence."""


def system_prompt(role: str, mission: str, schema_text: str, grounded: bool = True) -> str:
    """grounded=True for evidence extraction; False for roles that work from other agents' output (synthesis)."""
    rules = (EXTRACT_RULES if grounded else SYNTHESIS_RULES).replace("__SCHEMA__", schema_text.strip())
    rules = rules.replace("__TODAY__", date.today().isoformat())
    return "ROLE: %s\n%s\n\n%s" % (role, mission.strip(), rules)


class Extractor:
    """Calls the model with a JSON schema and repairs invalid output at most twice."""

    def __init__(self, llm) -> None:
        self.llm = llm

    def run(self, role: str, system: str, user: str, schema: Optional[dict] = None) -> Tuple[Optional[dict], Optional[str]]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(3):
            try:
                reply = self.llm.chat(messages, json_mode=True, schema=schema)
            except Exception as exc:  # model server down, timeout after retries, ...
                return None, "%s: %s" % (type(exc).__name__, exc)
            try:
                obj = extract_json(reply)
            except ValueError:
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": "NOTE: that was not valid JSON. Reply with exactly one JSON object."}]
                continue
            if set(obj) == {"final"} and isinstance(obj["final"], dict):
                obj = obj["final"]
            return obj, None
        return None, "model never returned valid JSON"
