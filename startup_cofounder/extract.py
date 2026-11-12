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
    if role == "coordinator":
        rules = ("Return one concise JSON research plan matching this schema:\n" + schema_text.strip()
                 + "\nDo not do the research yet. Use one short sentence per text field, "
                   "at most five search keywords, and at most two relevant extra specialists. Do not repeat fields.")
    else:
        rules += "\nKeep text concise. Include up to six distinct findings or list items when supported; avoid repetition."
    return "ROLE: %s\n%s\n\n%s" % (role, mission.strip(), rules)


REPAIR_NOTE = ("\n\nNOTE: your previous answer was incomplete or invalid JSON. Return a SHORTER complete JSON object "
               "with all required fields, at most four list items each, and one sentence per text field.")


class Extractor:
    """Calls the model with a JSON schema; repairs invalid or incomplete output at most twice.

    A repair resends the same (already budget-fitted) prompt plus a short note. The failed reply is NOT appended:
    it would grow the prompt past the context window, which is how small models lose their instructions.
    """

    def __init__(self, llm, on_call=None) -> None:
        self.llm = llm
        self.on_call = on_call  # callback(dict) for traces: role, attempt, ok, seconds

    def run(self, role: str, system: str, user: str, schema: Optional[dict] = None) -> Tuple[Optional[dict], Optional[str]]:
        import time
        for attempt in range(3):
            content = user if attempt == 0 else user + REPAIR_NOTE
            messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
            started = time.monotonic()
            try:
                reply = self.llm.chat(messages, json_mode=True, schema=schema)
            except Exception as exc:  # model server down, timeout after retries, budget reached ...
                self._log(role, attempt, "error", started, str(exc)[:160])
                return None, "%s: %s" % (type(exc).__name__, exc)
            try:
                obj = extract_json(reply)
            except ValueError:
                self._log(role, attempt, "incomplete" if not reply else "invalid_json", started)
                continue
            if set(obj) == {"final"} and isinstance(obj["final"], dict):
                obj = obj["final"]
            self._log(role, attempt, "ok", started)
            return obj, None
        return None, "model never returned valid JSON"

    def _log(self, role, attempt, outcome, started, detail=""):
        if self.on_call:
            import time
            self.on_call({"type": "llm_call", "role": role, "attempt": attempt + 1, "outcome": outcome,
                          "seconds": round(time.monotonic() - started, 2), "detail": detail})
