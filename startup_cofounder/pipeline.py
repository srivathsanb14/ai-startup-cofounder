"""Orchestration.

    coordinator ─► researchers (4 core + 0-2 dynamic specialists, parallel)
                ─► review loop (rule checks + LLM critic, redo weak agents)
                ─► competitor verification
                ─► financial planner ─► deterministic model (+scenarios, sensitivity, unit economics)
                ─► synthesizer ─► verdict guardrail
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional

from . import quality
from .agents import Agent, AgentResult, AgentSpec, specs
from .config import Config
from .evidence import EvidenceLedger
from .finance import Projection, project, scenarios, sensitivity, sanity_flags, unit_economics
from .llm import build_llm
from .tools import Http

DEFAULT_TASKS = {
    "customer": "Who has this problem, how painful is it, how do they cope today, what would they pay?",
    "competitor": "Who are the top three existing players, what do they charge, where are they weak?",
    "market": "How big is the market, how fast is it growing, what recent trends matter?",
    "technical": "How hard is an MVP to build, what should be built vs bought, what are the risks?",
    "financial": "Propose pricing, acquisition, team and cost assumptions for a five-year model.",
}
RESERVED_ROLES = {"customer", "competitor", "market", "technical", "financial", "synthesizer",
                  "coordinator", "critic", "pipeline"}


@dataclass
class Assessment:
    idea: str
    created: str
    plan: dict
    results: Dict[str, AgentResult]
    projection: Projection
    synthesis: dict
    sources: List[dict]
    warnings: List[str] = field(default_factory=list)
    extra_roles: List[str] = field(default_factory=list)
    review_log: List[dict] = field(default_factory=list)
    scenarios: Dict[str, Projection] = field(default_factory=dict)
    sensitivity: List[dict] = field(default_factory=list)
    unit_economics: dict = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    grade: str = "D"
    grade_reasons: List[str] = field(default_factory=list)
    verdict: str = "validate_first"
    verdict_note: str = ""

    def to_dict(self) -> dict:
        return {
            "idea": self.idea, "created": self.created, "plan": self.plan, "verdict": self.verdict,
            "verdict_note": self.verdict_note, "evidence_grade": self.grade, "grade_reasons": self.grade_reasons,
            "agents": {k: v.to_dict() for k, v in self.results.items()},
            "projection": self.projection.to_dict(),
            "scenarios": {k: v.to_dict() for k, v in self.scenarios.items()},
            "sensitivity": self.sensitivity, "unit_economics": self.unit_economics, "flags": self.flags,
            "synthesis": self.synthesis, "review_log": self.review_log, "extra_roles": self.extra_roles,
            "sources": self.sources, "warnings": self.warnings,
        }


def _brief(result: AgentResult, limit: int = 2500) -> str:
    """Compact view of an agent's output, passed as context to downstream agents."""
    text = json.dumps(result.output, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z]+", "_", str(text).lower()).strip("_")[:24]


class Pipeline:
    def __init__(self, config: Config, llm=None, on_event: Optional[Callable[[dict], None]] = None) -> None:
        self.config = config
        self.llm = llm or build_llm(config)
        self.on_event = on_event or (lambda e: None)
        Http.configure(config.cache_dir, config.offline)

    # -- helpers ---------------------------------------------------------
    def _emit(self, stage: str, status: str, detail: str = "") -> None:
        self.on_event({"stage": stage, "status": status, "detail": detail})

    def _agent(self, spec: AgentSpec, ledger: EvidenceLedger) -> Agent:
        return Agent(spec, self.llm, ledger, self.config.max_tool_calls, self.on_event)

    def _guard(self, spec: AgentSpec, ledger, idea: str, task: str, context: Optional[str] = None) -> AgentResult:
        """Run an agent; a crash in one specialist must not sink the whole report."""
        self._emit(spec.role, "start")
        try:
            result = self._agent(spec, ledger).run(idea, task, context)
        except Exception as exc:
            result = AgentResult(spec.role, {}, [], [], error="%s: %s" % (type(exc).__name__, exc))
        self._emit(spec.role, "error" if result.error else "done", result.error or "")
        return result

    def _parallel(self, jobs, ledger) -> Dict[str, AgentResult]:
        """jobs: list of (spec, idea, task, context)."""
        with ThreadPoolExecutor(max_workers=max(1, self.config.max_workers)) as pool:
            futures = {spec.role: pool.submit(self._guard, spec, ledger, idea, task, ctx)
                       for spec, idea, task, ctx in jobs}
            return {role: fut.result() for role, fut in futures.items()}

    def _extra_specs(self, plan: dict) -> List[AgentSpec]:
        extras: List[AgentSpec] = []
        for item in plan.get("extra_specialists") or []:
            if len(extras) >= self.config.max_extra_specialists:
                break
            if not isinstance(item, dict):
                continue
            role = _slug(item.get("role", ""))
            if len(role) < 3 or role in RESERVED_ROLES or any(e.role == role for e in extras):
                continue
            spec = specs.make_extra_specialist(role, str(item.get("focus") or role))
            spec.extra_task = str(item.get("questions") or item.get("focus") or role)
            extras.append(spec)
        return extras

    # -- review loop -----------------------------------------------------
    def _review_loop(self, results, ledger, focus, tasks, spec_by_role) -> List[dict]:
        log: List[dict] = []
        for rnd in range(1, self.config.critic_rounds + 1):
            self._emit("review", "start", "round %d" % rnd)
            rule = quality.rule_gaps(results, ledger)
            briefs = "\n".join("%s agent: %s" % (r, _brief(res, 1500)) for r, res in results.items() if res.output)
            rule_text = "\n".join("- %s: %s" % (g.agent, g.issue) for g in rule) or "(none)"
            critic = self._guard(specs.CRITIC, ledger, focus, "Review the research below.",
                                 "AUTOMATIC PROBLEMS ALREADY FOUND:\n%s\n\nRESEARCH:\n%s" % (rule_text, briefs))
            gaps = quality.merge_gaps(rule, quality.parse_critic(critic.output) if not critic.error else [],
                                      set(results))
            if not gaps:
                log.append({"round": rnd, "agent": "-", "issue": "no gaps found", "origin": "-", "improved": None})
                self._emit("review", "done", "approved")
                break
            jobs = []
            for g in gaps:
                context = ("YOUR PREVIOUS ANSWER:\n%s\n\nREVIEWER FEEDBACK: %s\n"
                           "Fix this using new tool calls where needed and return the COMPLETE improved output."
                           % (_brief(results[g.agent], 3000), g.issue))
                jobs.append((spec_by_role[g.agent], focus, g.followup or tasks.get(g.agent, ""), context))
            redone = self._parallel(jobs, ledger)
            for g in gaps:
                new = redone[g.agent]
                improved = not new.error and bool(new.output)
                if improved:
                    results[g.agent] = new
                log.append({"round": rnd, "agent": g.agent, "issue": g.issue, "origin": g.origin, "improved": improved})
            self._emit("review", "done", "%d agent(s) redone" % len(gaps))
        return log

    # -- main ------------------------------------------------------------
    def run(self, idea: str) -> Assessment:
        idea = " ".join(idea.split())
        if len(idea) < 8:
            raise ValueError("Please describe the idea in a sentence or more.")
        ledger = EvidenceLedger()
        warnings: List[str] = []
        if self.config.offline:
            warnings.append("Offline mode: no web evidence was gathered, so every finding is an estimate.")
        if self.config.backend == "mock":
            warnings.append("Mock LLM backend: output is placeholder scaffolding, not real research.")

        # 1. coordinator: sharpen the idea, plan tasks, optionally add specialists
        coord = self._guard(specs.COORDINATOR, ledger, idea, "Create the research plan for the specialist agents.")
        plan = coord.output or {}
        if coord.error:
            warnings.append("Coordinator failed; used a default research plan.")
        tasks = dict(DEFAULT_TASKS)
        tasks.update({k: v for k, v in (plan.get("tasks") or {}).items()
                      if k in DEFAULT_TASKS and isinstance(v, str) and v.strip()})
        plan.setdefault("idea_summary", idea)
        keywords = ", ".join(str(k) for k in plan.get("search_keywords", []) if k)
        focus = idea if not keywords else "%s (keywords: %s)" % (plan["idea_summary"], keywords)
        extras = self._extra_specs(plan)
        for e in extras:
            tasks[e.role] = e.extra_task
        spec_by_role = {s.role: s for s in specs.RESEARCHERS + extras}

        # 2. researchers in parallel
        results = self._parallel([(s, focus, tasks[s.role], None) for s in spec_by_role.values()], ledger)

        # 3. critic loop, then verify competitor names against evidence
        review_log = self._review_loop(results, ledger, focus, tasks, spec_by_role)
        quality.verify_competitors(results.get("competitor"), ledger)

        # 4. financial planner sees everyone else's findings
        context = "\n".join("%s agent: %s" % (r, _brief(res)) for r, res in results.items() if res.output)
        fin = self._guard(specs.FINANCIAL, ledger, focus, tasks["financial"], context)
        results["financial"] = fin
        projection = project(fin.output.get("assumptions"))
        if fin.error or not fin.output.get("assumptions"):
            warnings.append("Financial agent gave no usable assumptions; generic SaaS defaults were used.")
        ue = unit_economics(projection.assumptions)
        scen = scenarios(projection.assumptions)
        sens = sensitivity(projection.assumptions)
        mkt = results.get("market")
        sam = ((mkt.output.get("tam_sam_som") or {}).get("sam_usd") if mkt and isinstance(mkt.output.get("tam_sam_som"), dict) else None)
        flags = sanity_flags(projection, ue, sam)
        grade, grade_reasons = quality.evidence_grade(results, len(ledger.all()))

        # 5. synthesizer gets the computed numbers, flags and grade so the verdict is grounded
        computed = {"projection": projection.to_dict(), "unit_economics": ue, "sanity_flags": flags,
                    "scenario_year5_operating_profit": {k: round(float(v.table.iloc[-1]["operating_profit"])) for k, v in scen.items()},
                    "evidence_grade": grade}
        full_context = context + "\nfinancial agent: " + _brief(fin) + "\nCOMPUTED (authoritative): " + json.dumps(computed, default=str)[:3000]
        syn = self._guard(specs.SYNTHESIZER, ledger, focus, "Write the decision memo.", full_context)
        results["synthesizer"] = syn
        synthesis = syn.output or {}
        verdict, verdict_note = quality.cap_verdict(synthesis.get("verdict"), grade, ue, projection.breakeven_year)

        for role, res in results.items():
            if res.error:
                warnings.append("%s agent failed: %s" % (role, res.error))
        self._emit("pipeline", "done")
        return Assessment(
            idea=idea, created=date.today().isoformat(), plan=plan, results=results, projection=projection,
            synthesis=synthesis, sources=[s.__dict__ for s in ledger.all()], warnings=warnings,
            extra_roles=[e.role for e in extras], review_log=review_log, scenarios=scen, sensitivity=sens,
            unit_economics=ue, flags=flags, grade=grade, grade_reasons=grade_reasons,
            verdict=verdict, verdict_note=verdict_note,
        )
