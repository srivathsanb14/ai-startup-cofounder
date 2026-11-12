from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..evidence import Finding


@dataclass
class AgentSpec:
    """A research role: who it is (mission) and what it must return (schema text shown to the model)."""

    role: str
    mission: str
    schema: str
    extra_task: str = ""  # research questions for coordinator-created specialists
    focus: str = ""  # topic of a coordinator-created specialist


@dataclass
class AgentResult:
    role: str
    output: Dict[str, Any]
    findings: List[Finding]
    trace: List[dict] = field(default_factory=list)  # evidence ids each result was drawn from
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"role": self.role, "output": self.output, "error": self.error,
                "findings": [f.to_dict() for f in self.findings], "trace": self.trace}
