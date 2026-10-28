from __future__ import annotations

import json
from datetime import date
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..evidence import EvidenceLedger, Finding, normalize_findings
from ..jsonutil import extract_json
from ..tools import get_tools

PROTOCOL = """You work in a loop. On every turn reply with EXACTLY ONE JSON object and nothing else.
To call a tool:   {"thought": "<why>", "tool": "<tool name>", "args": {...}}
To finish:        {"final": <output object matching the schema below>}

TOOLS:
__TOOLS__

TODAY: __TODAY__ (prefer recent sources; note the year of any statistic).

RULES:
- Cite evidence using the ids shown in tool observations (e.g. "E3") in each finding's "source_ids".
- Mark a finding "fact" ONLY if a cited source supports it. Everything else (projections, judgement,
  numbers you derived) must be marked "estimate". Facts are machine-checked: every number in a fact
  must appear verbatim in a cited source, or the claim is downgraded.
- Never invent URLs, company names, statistics or quotes. If evidence is thin, say so.
- Query craft: use specific, varied queries (e.g. "alternatives to X", "X pricing", "<industry> market
  size report", "<problem> complaints"). Never repeat a query. When a result names a key competitor or
  report, use fetch_page on its URL to read the details instead of guessing.
- Look for two independent sources for important numbers.
- You may make at most __MAX__ tool calls, then you must finish.

FINAL OUTPUT SCHEMA:
__SCHEMA__
"""


@dataclass
class AgentSpec:
    role: str
    mission: str
    schema: str
    tools: List[str] = field(default_factory=list)
    max_tool_calls: Optional[int] = None  # None -> config default
    extra_task: str = ""  # research questions for coordinator-created specialists


@dataclass
class AgentResult:
    role: str
    output: Dict[str, Any]
    findings: List[Finding]
    trace: List[dict]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"role": self.role, "output": self.output, "error": self.error,
                "findings": [f.to_dict() for f in self.findings], "trace": self.trace}


def render_observation(tool: str, sources, note: str) -> str:
    lines = ["TOOL_OBSERVATION from %s:" % tool]
    for s in sources:
        lines.append("[%s] %s\n    url: %s\n    %s" % (s.id, s.title, s.url, s.snippet))
    if note:
        lines.append("note: " + note)
    if not sources and not note:
        lines.append("no results")
    return "\n".join(lines)


class Agent:
    def __init__(self, spec: AgentSpec, llm, ledger: EvidenceLedger, max_tool_calls: int = 4,
                 on_event: Optional[Callable[[dict], None]] = None) -> None:
        self.spec = spec
        self.llm = llm
        self.ledger = ledger
        self.tools = get_tools(spec.tools)
        self.max_tool_calls = spec.max_tool_calls if spec.max_tool_calls is not None else max_tool_calls
        if not self.tools:
            self.max_tool_calls = 0
        self.on_event = on_event or (lambda e: None)

    def _system_prompt(self) -> str:
        tool_text = "\n".join(t.signature() for t in self.tools.values()) or "(none: answer from the context you are given)"
        protocol = (PROTOCOL.replace("__TOOLS__", tool_text)
                    .replace("__MAX__", str(self.max_tool_calls))
                    .replace("__TODAY__", date.today().isoformat())
                    .replace("__SCHEMA__", self.spec.schema.strip()))
        return "ROLE: %s\n%s\n\n%s" % (self.spec.role, self.spec.mission.strip(), protocol)

    def run(self, idea: str, task: str, context: Optional[str] = None) -> AgentResult:
        user = "IDEA: %s\nTASK: %s" % (idea, task)
        if context:
            user += "\n\nCONTEXT FROM OTHER AGENTS:\n" + context
        messages = [{"role": "system", "content": self._system_prompt()}, {"role": "user", "content": user}]
        trace: List[dict] = []
        tool_calls = 0
        bad_replies = 0
        output: Optional[dict] = None

        for _ in range(self.max_tool_calls + 4):
            reply = self.llm.chat(messages, json_mode=True)
            try:
                obj = extract_json(reply)
            except ValueError:
                bad_replies += 1
                if bad_replies > 2:
                    break
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": "NOTE: that was not valid JSON. Reply with exactly one JSON object."}]
                continue
            messages.append({"role": "assistant", "content": reply})

            if "final" in obj and isinstance(obj["final"], dict):
                output = obj["final"]
                break
            if "tool" not in obj and set(obj) - {"thought", "final"}:
                output = obj  # model skipped the {"final": ...} wrapper
                break

            name = obj.get("tool")
            if name not in self.tools or tool_calls >= self.max_tool_calls:
                reason = ("unknown tool '%s'" % name) if name not in self.tools else "tool budget used up"
                messages.append({"role": "user", "content":
                                 "NOTE: %s. Reply now with {\"final\": ...} using what you have." % reason})
                continue

            args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
            self.on_event({"stage": self.spec.role, "status": "tool", "detail": "%s %s" % (name, json.dumps(args)[:90])})
            result = self.tools[name].run(**args)
            tool_calls += 1
            sources = self.ledger.add(name, result.sources)
            trace.append({"tool": name, "args": args, "source_ids": [s.id for s in sources], "note": result.text})
            messages.append({"role": "user", "content": render_observation(name, sources, result.text)})

        if output is None:
            return AgentResult(self.spec.role, {}, [], trace, error="agent produced no valid final output")
        findings = normalize_findings(output.get("findings"), self.ledger)
        output["findings"] = [f.to_dict() for f in findings]
        return AgentResult(self.spec.role, output, findings, trace)
