"""The assessment pipeline: retrieve first, then extract.

    coordinator (fast model)
      -> retrieval: templated queries run in parallel, top pages fetched in full, no LLM involved
      -> extraction: customer / market / technical / extras read ranked evidence packs (fast model, schema-constrained)
      -> competitors: names extracted -> ranked by evidence -> each top name searched and profiled
      -> review loop: rule checks + critic; weak sections get follow-up retrieval and re-extraction
      -> financial (main model) -> deterministic numbers -> synthesizer (main model) -> verdict guardrail

Every stage is checkpointed, so an interrupted run resumes instead of restarting.
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional

from . import competitors as comp
from . import quality, retrieval, schemas
from .agents import AgentResult, AgentSpec, specs
from .checkpoint import Checkpoint, run_key
from .config import Config
from .evidence import EvidenceLedger, normalize_findings
from .extract import Extractor, system_prompt
from .finance import Projection, project, sanity_flags, scenarios, sensitivity, unit_economics
from .llm import build_llm
from .passages import PassageIndex
from .tools import Http

DEFAULT_TASKS = {
    "customer": "Who has this problem, how painful is it, how do they cope today, what would they pay?",
    "competitor": "Who are the top three existing players, what do they charge, where are they weak?",
    "market": "How big is the market, how fast is it growing, what recent trends matter?",
    "technical": "How hard is an MVP to build, what should be built vs bought, what are the risks?",
    "financial": "Propose pricing, acquisition, team and cost assumptions for a five-year model.",
}
RESERVED_ROLES = {"customer", "competitor", "market", "technical", "financial", "synthesizer",
                  "coordinator", "critic", "pipeline", "candidates", "profile"}
CORE_SECTIONS = ["customer", "competitor", "market", "technical"]

PROFILE_SCHEMA = ('{"name": "", "is_competitor": true, "url": "<official site if in the evidence>", "description": "", "pricing": "", '
                  '"strengths": [""], "weaknesses": [""], "source_ids": ["E1"], '
                  '"findings": [{"claim": "", "kind": "fact|estimate", "source_ids": ["E1"]}]}')
SUMMARY_SCHEMA = '{"summary": "<3-4 sentences>", "white_space": "<where incumbents are weak>"}'
CANDIDATE_SCHEMA = '{"candidates": [{"name": "<company or product name exactly as written in the evidence>", "what_it_is": ""}]}'


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


@dataclass
class Economics:
    projection: Projection
    unit_economics: dict
    scenarios: Dict[str, Projection]
    sensitivity: List[dict]
    flags: List[str]
    grade: str
    grade_reasons: List[str]
    fact_ratio: float
    computed: dict  # authoritative numbers handed to the synthesizer


def economics(results: Dict[str, AgentResult], fin_output: dict, source_count: int) -> Economics:
    """All deterministic numbers: projection, unit economics, scenarios, sensitivity, flags, evidence grade."""
    projection = project(fin_output.get("assumptions"))
    ue = unit_economics(projection.assumptions)
    scen = scenarios(projection.assumptions)
    sens = sensitivity(projection.assumptions)
    mkt = results.get("market")
    tss = mkt.output.get("tam_sam_som") if mkt and isinstance(mkt.output.get("tam_sam_som"), dict) else {}
    flags = sanity_flags(projection, ue, tss.get("sam_usd"))
    grade, reasons = quality.evidence_grade(results, source_count)
    computed = {"projection": projection.to_dict(), "unit_economics": ue, "sanity_flags": flags,
                "scenario_year5_operating_profit": {k: round(float(v.table.iloc[-1]["operating_profit"])) for k, v in scen.items()},
                "evidence_grade": grade}
    return Economics(projection, ue, scen, sens, flags, grade, reasons, quality.fact_ratio(results), computed)


def _brief(result: AgentResult, limit: int = 2500) -> str:
    """Compact view of a section's output, passed as context to downstream steps."""
    text = json.dumps(result.output, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"


def _brief_dict(d: dict, limit: int) -> str:
    text = json.dumps({k: v for k, v in d.items() if not k.startswith("__")}, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ...(truncated)"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z]+", "_", str(text).lower()).strip("_")[:24]


class _Run:
    """State for one assessment: evidence, passage index, checkpoint, plan context."""

    def __init__(self, idea: str, ledger: EvidenceLedger, state: dict, ck: Checkpoint) -> None:
        self.idea, self.ledger, self.state, self.ck = idea, ledger, state, ck
        self.index = PassageIndex()
        self.lock = threading.Lock()
        self.ids: Dict[str, List[str]] = {}
        self.category = self.problem = self.focus = ""
        self.tasks: Dict[str, str] = dict(DEFAULT_TASKS)
        self.specs: Dict[str, AgentSpec] = {}

    def _persist(self) -> None:
        self.state["ledger"] = [s.__dict__ for s in self.ledger.all()]
        self.ck.save(self.state)

    def stage(self, name: str, fn: Callable[[], object]):
        with self.lock:
            if name in self.state["done"]:
                return self.state["raw"][name]
        out = fn()
        self.put(name, out)
        return out

    def put(self, name: str, out) -> None:
        with self.lock:
            self.state["raw"][name] = out
            if name not in self.state["done"]:
                self.state["done"].append(name)
            self._persist()


class Pipeline:
    def __init__(self, config: Config, llm=None, fast_llm=None, on_event: Optional[Callable[[dict], None]] = None) -> None:
        self.config = config
        self.llm = llm or build_llm(config)
        self.fast = fast_llm or (llm if llm is not None else build_llm(config, fast=True))
        self.ex = Extractor(self.llm)
        self.ex_fast = Extractor(self.fast)
        self.on_event = on_event or (lambda e: None)
        Http.configure(config.cache_dir, config.offline)

    def _emit(self, stage: str, status: str, detail: str = "") -> None:
        self.on_event({"stage": stage, "status": status, "detail": detail})

    def _extra_specs(self, plan: dict) -> List[AgentSpec]:
        """Idea-specific specialists requested by the coordinator (sanitized, capped)."""
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
            spec.focus = str(item.get("focus") or role)
            extras.append(spec)
        return extras

    # -- stages --------------------------------------------------------------
    def _plan(self, idea: str) -> dict:
        self._emit("coordinator", "start")
        spec = specs.COORDINATOR
        out, err = self.ex_fast.run("coordinator", system_prompt("coordinator", spec.mission, spec.schema),
                                    "IDEA: %s\nTASK: Create the research plan." % idea, schemas.COORDINATOR)
        self._emit("coordinator", "error" if err else "done", err or "")
        return out if out is not None else {"__error__": err}

    def _search(self, r: _Run, sections: List[str], extras: Dict[str, str]) -> Dict[str, List[str]]:
        self._emit("retrieval", "start", "%d sections" % len(sections))
        queries = retrieval.build_queries(sections, r.category, r.problem, extras)
        ids = retrieval.run_queries(queries, r.ledger, self.config.max_workers * 2, self.on_event)
        self._emit("retrieval", "done", "%d sources" % len(r.ledger.all()))
        return ids

    def _section(self, r: _Run, role: str, feedback: Optional[str] = None, prior: Optional[dict] = None) -> dict:
        self._emit(role, "start")
        spec = r.specs[role]
        task = r.tasks.get(role) or DEFAULT_TASKS.get(role, spec.mission)
        pack, ids = retrieval.evidence_pack("%s %s %s" % (r.category, task, r.problem), r.ids.get(role, []), r.ledger, r.index)
        user = "IDEA: %s\nTASK: %s\n" % (r.focus, task)
        if prior:
            user += "\nYOUR PREVIOUS ANSWER:\n%s\n" % _brief_dict(prior, 3000)
        if feedback:
            user += "REVIEWER FEEDBACK: %s\nReturn the COMPLETE improved output.\n" % feedback
        out, err = self.ex_fast.run(role, system_prompt(role, spec.mission, spec.schema),
                                    user + "\nEVIDENCE:\n" + pack, schemas.BY_ROLE.get(role, schemas.EXTRA))
        self._emit(role, "error" if err else "done", err or "")
        if out is None:
            return {"__error__": err}
        out["__evidence__"] = ids
        return out

    def _profile(self, r: _Run, name: str) -> Optional[dict]:
        queries = [retrieval.Query(name, tool, text) for tool, text in comp.profile_queries(name, r.category)]
        ids = retrieval.run_queries(queries, r.ledger, 4).get(name, [])
        retrieval.fetch_pages({name: ids}, r.ledger, r.index, per_section=2)
        pack, _ = retrieval.evidence_pack("%s pricing plans cost per month strengths weaknesses reviews" % name,
                                          ids, r.ledger, r.index, n_snippets=8, n_passages=6)
        user = ("IDEA: %s\nCANDIDATE: %s\nTASK: Profile this competitor: what it does, how it charges, strengths and weaknesses. "
                "If pricing is not in the evidence write 'not found in sources'. Set is_competitor to false if this is not a company "
                "or product that sells to the same customers for the same need.\n\nEVIDENCE:\n%s" % (r.focus, name, pack))
        out, _ = self.ex_fast.run("profile", system_prompt(
            "profile", "You are a competitive intelligence analyst profiling one company.", PROFILE_SCHEMA), user, schemas.PROFILE)
        if out is None:
            return None
        if out.get("is_competitor") is False:
            return None
        out.pop("is_competitor", None)
        out["name"] = name
        out["source_ids"] = r.ledger.valid_ids(out.get("source_ids"))
        out["verified"] = quality.name_seen(name, r.ledger.corpus())
        return out

    def _candidate_names(self, r: _Run, tried: List[str]):
        """Valid, evidence-backed competitor names. A second, snippets-only attempt runs when the first finds fewer than 3."""
        question = "companies products competitors alternatives %s" % r.category
        names: List[str] = []
        ids: List[str] = []
        raw_seen: List[str] = []
        for attempt, (n_snip, n_pass) in enumerate(((14, 6), (30, 0))):
            pack, pack_ids = retrieval.evidence_pack(question, r.ids.get("competitor", []), r.ledger, r.index,
                                                     n_snippets=n_snip, n_passages=n_pass)
            ids += [i for i in pack_ids if i not in ids]
            ask = ("List the companies or products that compete in this category (%s). Use names exactly as they appear "
                   "in the evidence. Names of companies or products only: never article titles, sentences or evidence ids "
                   "like E12." % r.category)
            if attempt:
                ask += " Return at least 5 distinct names."
            raw, _ = self.ex_fast.run("candidates", system_prompt(
                "candidates", "You extract competitor names from search evidence.", CANDIDATE_SCHEMA),
                "IDEA: %s\nTASK: %s\n\nEVIDENCE:\n%s" % (r.focus, ask, pack), schemas.CANDIDATES)
            found = (raw or {}).get("candidates")
            raw_seen += [str(c.get("name")) for c in found or [] if isinstance(c, dict)]
            for n in comp.rank_candidates(found, r.ledger.corpus(), skip=list(tried) + names,
                                          allow_unseen=not r.ledger.all(), docs=r.ledger.documents()):
                names.append(n)
            if len(names) >= 3:
                break
        return names, ids, raw_seen

    def _competitors(self, r: _Run, prior: Optional[dict] = None, feedback: Optional[str] = None) -> dict:
        self._emit("competitor", "start")
        if prior is not None or feedback:  # redo: widen the search first
            extra_ids = retrieval.run_queries(retrieval.build_queries(["competitor"], r.category, r.problem, followup=True),
                                              r.ledger, self.config.max_workers)
            known = r.ids.setdefault("competitor", [])
            known += [i for i in extra_ids.get("competitor", []) if i not in known]
            retrieval.fetch_pages({"competitor": extra_ids.get("competitor", [])}, r.ledger, r.index)
        have = list((prior or {}).get("competitors", []))
        tried = list((prior or {}).get("__tried__", [])) + [c.get("name", "") for c in have]

        names, ids, seen_raw = self._candidate_names(r, tried)
        top = names[: (4 if not have else max(2, 4 - len(have)))]
        with ThreadPoolExecutor(max_workers=max(1, self.config.max_workers)) as pool:
            profiles = [p for p in pool.map(lambda n: self._profile(r, n), top) if p]

        findings = list((prior or {}).get("findings", []))
        for p in profiles:
            findings += p.pop("findings", []) or []
        comps = comp.merge_competitors(have, profiles)
        brief = json.dumps([{k: c.get(k) for k in ("name", "description", "pricing", "strengths", "weaknesses")}
                            for c in comps[:4]], ensure_ascii=False)[:3500]
        if comps:
            summ, _ = self.ex.run("competitor_summary", system_prompt(
                "competitor_summary", "You summarize the competitive landscape for a founder.", SUMMARY_SCHEMA, grounded=False),
                "IDEA: %s\nPROFILES:\n%s" % (r.focus, brief), schemas.COMPETITOR_SUMMARY)
        else:  # nothing to summarize; a model asked anyway would invent players from memory
            summ = {"summary": "No competitors could be confirmed in the retrieved evidence.", "white_space": ""}
        summ = summ or {}
        self._emit("competitor", "done", "%d profiled" % len(comps))
        return {"summary": summ.get("summary", ""), "competitors": comps, "white_space": summ.get("white_space", ""),
                "findings": findings, "__evidence__": ids, "__tried__": tried + top, "__candidates__": seen_raw}

    def _result(self, r: _Run, role: str, raw: Optional[dict]) -> AgentResult:
        if not raw or "__error__" in raw:
            return AgentResult(role, {}, [], [], error=(raw or {}).get("__error__") or "no output")
        out = copy.deepcopy(raw)
        ids = out.pop("__evidence__", [])
        out.pop("__tried__", None)
        out.pop("__candidates__", None)
        findings = normalize_findings(out.get("findings"), r.ledger)
        out["findings"] = [f.to_dict() for f in findings]
        return AgentResult(role, out, findings, [{"tool": "retrieval", "source_ids": ids}])

    def _results(self, r: _Run, roles: List[str]) -> Dict[str, AgentResult]:
        return {role: self._result(r, role, r.state["raw"].get("section:" + role)) for role in roles}

    # -- review loop ---------------------------------------------------------
    def _redo(self, r: _Run, role: str, issue: str) -> bool:
        prior = r.state["raw"].get("section:" + role)
        prior = prior if prior and "__error__" not in prior else None
        if role == "competitor":
            new = self._competitors(r, prior=prior, feedback=issue)
            ok = bool(new["competitors"]) or prior is None
        else:
            if role in retrieval.FOLLOWUP_QUERIES:
                extra = retrieval.run_queries(retrieval.build_queries([role], r.category, r.problem, followup=True),
                                              r.ledger, self.config.max_workers)
                known = r.ids.setdefault(role, [])
                known += [i for i in extra.get(role, []) if i not in known]
                retrieval.fetch_pages({role: extra.get(role, [])}, r.ledger, r.index)
            new = self._section(r, role, feedback=issue, prior=prior)
            ok = "__error__" not in new
        if ok:
            r.put("section:" + role, new)
        return ok

    def _review(self, r: _Run, roles: List[str]) -> List[dict]:
        log: List[dict] = []
        for rnd in range(1, self.config.critic_rounds + 1):
            self._emit("review", "start", "round %d" % rnd)
            results = self._results(r, roles)
            rule = quality.rule_gaps(results, r.ledger)
            briefs = "\n".join("%s: %s" % (k, _brief(v, 1500)) for k, v in results.items() if v.output)
            rule_text = "\n".join("- %s: %s" % (g.agent, g.issue) for g in rule) or "(none)"
            out, _ = self.ex.run("critic", system_prompt("critic", specs.CRITIC.mission, specs.CRITIC.schema, grounded=False),
                                 "IDEA: %s\nAUTOMATIC PROBLEMS ALREADY FOUND:\n%s\n\nRESEARCH:\n%s" % (r.focus, rule_text, briefs),
                                 schemas.CRITIC)
            gaps = quality.merge_gaps(rule, quality.parse_critic(out) if out else [], set(results))
            if not gaps:
                log.append({"round": rnd, "agent": "-", "issue": "no gaps found", "origin": "-", "improved": None})
                self._emit("review", "done", "approved")
                break
            with ThreadPoolExecutor(max_workers=max(1, self.config.max_workers)) as pool:
                outcomes = list(pool.map(lambda g: self._redo(r, g.agent, g.issue), gaps))
            for g, ok in zip(gaps, outcomes):
                log.append({"round": rnd, "agent": g.agent, "issue": g.issue, "origin": g.origin, "improved": ok})
            self._emit("review", "done", "%d section(s) redone" % len(gaps))
        return log

    # -- tail ----------------------------------------------------------------
    def _financial(self, r: _Run, results: Dict[str, AgentResult]) -> dict:
        self._emit("financial", "start")
        context = "\n".join("%s: %s" % (k, _brief(v)) for k, v in results.items() if v.output)
        pack, ids = retrieval.evidence_pack("%s pricing price per month customer acquisition cost benchmark" % r.category,
                                            r.ids.get("financial", []), r.ledger, r.index, n_snippets=8, n_passages=4)
        user = ("IDEA: %s\nTASK: %s\n\nRESEARCH BY OTHER SECTIONS:\n%s\n\nEVIDENCE (pricing and cost benchmarks):\n%s"
                % (r.focus, r.tasks["financial"], context, pack))
        out, err = self.ex.run("financial", system_prompt("financial", specs.FINANCIAL.mission, specs.FINANCIAL.schema),
                               user, schemas.FINANCIAL)
        self._emit("financial", "error" if err else "done", err or "")
        if out is None:
            return {"__error__": err}
        out["__evidence__"] = ids
        return out

    def _synthesize(self, r: _Run, results: Dict[str, AgentResult], computed: dict) -> dict:
        self._emit("synthesizer", "start")
        briefs = "\n".join("%s: %s" % (k, _brief(v, 1200)) for k, v in results.items() if v.output)
        user = ("IDEA: %s\nTASK: Write the decision memo.\n\nRESEARCH SUMMARIES:\n%s\n\nCOMPUTED (authoritative): %s"
                % (r.focus, briefs, json.dumps(computed, default=str)[:3000]))
        out, err = self.ex.run("synthesizer", system_prompt(
            "synthesizer", specs.SYNTHESIZER.mission, specs.SYNTHESIZER.schema, grounded=False), user, schemas.SYNTHESIZER)
        self._emit("synthesizer", "error" if err else "done", err or "")
        return out if out is not None else {"__error__": err}

    # -- main ----------------------------------------------------------------
    def run(self, idea: str, fresh: bool = False) -> Assessment:
        idea = " ".join(idea.split())
        if len(idea) < 8:
            raise ValueError("Please describe the idea in a sentence or more.")
        cfg = self.config
        warnings: List[str] = []
        if cfg.offline:
            warnings.append("Offline mode: no web evidence was gathered, so every finding is an estimate.")
        if cfg.backend == "mock":
            warnings.append("Mock LLM backend: output is placeholder scaffolding, not real research.")

        ck = Checkpoint(cfg.cache_dir / "runs" if cfg.cache_dir else None,
                        run_key(idea, cfg.backend, cfg.model, cfg.fast_model, str(cfg.offline),
                                os.environ.get("DISABLED_TOOLS", "")))
        state = {} if (fresh or not cfg.resume) else ck.load()
        state.setdefault("done", [])
        state.setdefault("raw", {})
        ledger = EvidenceLedger()
        for src in state.get("ledger", []):
            ledger.add(src["tool"], [src])  # restoring in order reproduces the same ids
        if state["done"]:
            self._emit("pipeline", "resumed", "%d stage(s) restored" % len(state["done"]))
        r = _Run(idea, ledger, state, ck)

        # 1. plan
        plan = dict(r.stage("plan", lambda: self._plan(idea)))
        if plan.pop("__error__", None):
            warnings.append("Coordinator failed; used a default research plan.")
        plan.setdefault("idea_summary", idea)
        r.category = str(plan.get("category") or "").strip()[:80] or idea[:60]
        r.problem = str(plan.get("problem") or "").strip()[:120] or idea[:100]
        keywords = ", ".join(str(k) for k in plan.get("search_keywords", []) if k)
        r.focus = plan["idea_summary"] if not keywords else "%s (keywords: %s)" % (plan["idea_summary"], keywords)
        r.tasks.update({k: v for k, v in (plan.get("tasks") or {}).items()
                        if k in DEFAULT_TASKS and isinstance(v, str) and v.strip()})
        extras = self._extra_specs(plan)
        for e in extras:
            r.tasks[e.role] = e.extra_task
        r.specs = {s.role: s for s in specs.RESEARCHERS + extras}
        roles = CORE_SECTIONS + [e.role for e in extras]

        # 2. retrieval (searches checkpointed; pages are re-read from the HTTP cache on resume)
        r.ids = r.stage("retrieval", lambda: self._search(r, roles + ["financial"], {e.role: e.focus for e in extras}))
        fetched = retrieval.fetch_pages(r.ids, ledger, r.index, workers=cfg.max_workers * 2)
        self._emit("retrieval", "pages", "%d full pages indexed" % fetched)

        # 3. extraction, all sections in parallel
        def job(role):
            return (lambda: self._competitors(r)) if role == "competitor" else (lambda: self._section(r, role))
        with ThreadPoolExecutor(max_workers=max(1, cfg.max_workers)) as pool:
            for f in [pool.submit(r.stage, "section:" + role, job(role)) for role in roles]:
                f.result()

        # 4. review loop, then competitor verification
        review_log = r.stage("review", lambda: self._review(r, roles))
        results = self._results(r, roles)
        quality.verify_competitors(results.get("competitor"), ledger)

        # 5. financial -> deterministic economics
        results["financial"] = self._result(r, "financial", r.stage("financial", lambda: self._financial(r, results)))
        fin = results["financial"]
        eco = economics(results, fin.output, len(ledger.all()))
        if fin.error or not fin.output.get("assumptions"):
            warnings.append("Financial planner gave no usable assumptions; generic SaaS defaults were used.")

        # 6. synthesis and guardrail
        syn = self._result(r, "synthesizer", r.stage("synthesis", lambda: self._synthesize(r, results, eco.computed)))
        results["synthesizer"] = syn
        verdict, verdict_note = quality.cap_verdict(syn.output.get("verdict"), eco.grade, eco.unit_economics,
                                                    eco.projection.breakeven_year, eco.fact_ratio)
        for role, res in results.items():
            if res.error:
                warnings.append("%s failed: %s" % (role, res.error))
        self._emit("pipeline", "done")
        return Assessment(
            idea=idea, created=date.today().isoformat(), plan=plan, results=results, projection=eco.projection,
            synthesis=syn.output, sources=[s.__dict__ for s in ledger.all()], warnings=warnings,
            extra_roles=[e.role for e in extras], review_log=review_log, scenarios=eco.scenarios,
            sensitivity=eco.sensitivity, unit_economics=eco.unit_economics, flags=eco.flags, grade=eco.grade,
            grade_reasons=eco.grade_reasons, verdict=verdict, verdict_note=verdict_note,
        )
