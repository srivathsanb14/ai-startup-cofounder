from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional

import requests

from .config import Config
from .tokens import estimate, reply_tokens

Messages = List[Dict[str, str]]


class LLMError(RuntimeError):
    pass


class OpenAICompatLLM:
    """Chat client for any OpenAI-compatible endpoint (Ollama, vLLM, llama.cpp, LM Studio).

    With `schema`, requests schema-constrained decoding (`response_format: json_schema`). Servers that do not
    support it are detected by an HTTP 400 and we degrade to plain JSON mode, then to unconstrained output.
    """

    def __init__(self, config: Config, model: Optional[str] = None) -> None:
        self.config = config
        self.model = model or config.model
        self.budget = None
        self.stats = {"calls": 0, "incomplete": 0, "errors": 0, "max_prompt_tokens_est": 0, "over_context": 0,
                      "seconds": 0.0}

    def chat(self, messages: Messages, temperature: Optional[float] = None, json_mode: bool = False,
             schema: Optional[dict] = None) -> str:
        cfg = self.config
        first = messages[0]["content"] if messages else ""
        role_m = re.match(r"ROLE: (\w+)", first)
        role = role_m.group(1) if role_m else ""
        reply = reply_tokens(role if role in ("coordinator", "planner", "candidates", "profile", "competitor_summary",
                                              "customer", "market", "technical", "financial", "verifier", "critic",
                                              "synthesizer", "brief", "analyst", "qcritic") else "extra",
                             cfg.max_tokens, cfg.context_tokens, cfg.coordinator_tokens)
        prompt_est = sum(estimate(m.get("content", "")) for m in messages)
        self.stats["calls"] += 1
        self.stats["max_prompt_tokens_est"] = max(self.stats["max_prompt_tokens_est"], prompt_est)
        if prompt_est + reply > cfg.context_tokens:
            self.stats["over_context"] += 1  # callers fit prompts; this records any that still overflow
        started = time.monotonic()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": cfg.temperature if temperature is None else temperature,
            "stream": False,
            # Bound generation per role so prompt + reply fit the context window (LLM_MAX_TOKENS stays the ceiling).
            "max_tokens": reply,
        }
        formats = []
        if schema:
            formats.append({"type": "json_schema", "json_schema": {"name": "output", "schema": schema}})
        if json_mode or schema:
            formats.append({"type": "json_object"})
        formats.append(None)  # last resort: no constraint
        headers = {"Authorization": "Bearer " + cfg.api_key}
        url = cfg.base_url + "/chat/completions"
        last_err = None
        attempt = 0
        while attempt < cfg.llm_attempts:
            if self.budget and not self.budget.available():
                raise LLMError("Time budget reached for %s; moving to the next phase." % self.budget.phase)
            fmt = formats[0]
            if fmt:
                payload["response_format"] = fmt
            else:
                payload.pop("response_format", None)
            try:
                timeout = min(cfg.timeout, self.budget.remaining()) if self.budget else cfg.timeout
                resp = requests.post(url, json=payload, headers=headers, timeout=max(0.1, timeout))
                if resp.status_code == 400 and len(formats) > 1:
                    formats.pop(0)  # server rejected this format; try the next one without using up a retry
                    continue
                if resp.status_code >= 500:
                    raise LLMError("server error %d: %s" % (resp.status_code, resp.text[:200]))
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                self.stats["seconds"] += time.monotonic() - started
                if choice.get("finish_reason") == "length":
                    # Incomplete generation: the extractor retries a shorter complete answer (bounded).
                    self.stats["incomplete"] += 1
                    return ""
                return choice["message"]["content"] or ""
            except (requests.RequestException, LLMError, KeyError, ValueError) as exc:
                last_err = exc
                attempt += 1
                if attempt < cfg.llm_attempts:
                    delay = min(1.5 * attempt, self.budget.remaining()) if self.budget else 1.5 * attempt
                    time.sleep(delay)
        self.stats["errors"] += 1
        raise LLMError(
            "LLM call failed (%s). Is your model server running at %s?" % (last_err, cfg.base_url)
        )


class MockLLM:
    """Deterministic stand-in so the whole pipeline can be demoed and tested without a model.

    Output is generic scaffolding, clearly labelled, never real research. It answers the pipeline's extraction
    prompts and quotes the first retrieved headline so grounding checks pass honestly.
    """

    def chat(self, messages: Messages, temperature: Optional[float] = None, json_mode: bool = False,
             schema: Optional[dict] = None) -> str:
        system = messages[0]["content"]
        role = re.search(r"ROLE: (\w+)", system).group(1)
        first_user = messages[1]["content"]
        idea_match = re.search(r"IDEA: (.+)", first_user)
        idea = idea_match.group(1).strip() if idea_match else "the idea"

        if role == "coordinator":
            return json.dumps(self._plan(idea))
        if role == "critic":
            return json.dumps({"approved": True, "gaps": []})
        if role == "brief":  # restates the founder's sentence without adding anything
            from .brief import fallback_fields
            said = re.search(r"FOUNDER'S IDEA: (.+)", first_user)
            fb = fallback_fields(said.group(1) if said else idea)
            return json.dumps(dict(fb, geography="", stage="idea", payer="unknown", business_model="", constraints=[],
                                   exclusions=[], riskiest_assumption=""))
        if role == "qcritic":
            return json.dumps({"verdicts": [{"id": q, "verdict": "yes", "reason": "[mock]"}
                                            for q in re.findall(r"^(Q-[A-Z]\d+) \|", first_user, re.M)]})
        if role == "analyst":  # quotes the first evidence sentence that is not a question; never interprets
            items = re.findall(r"\[(E\d+)\] (.+)\n\s+url: .+\n\s+(.+)", first_user)
            for sid, title, snippet in items:
                sent = next((s for s in re.split(r"(?<=[.!?])\s+", snippet) if len(s) > 30 and not s.strip()
                             .endswith("?")), "")
                if sent:
                    return json.dumps({"status": "partial", "answer": "[mock] " + sent[:160], "findings": [
                        {"statement": sent[:200], "type": "fact", "stance": "neutral", "source_ids": [sid]}],
                        "unknown": "[mock] not analysed"})
            return json.dumps({"status": "insufficient", "answer": "", "findings": [],
                               "unknown": "[mock] no evidence"})
        if role == "planner":  # the mock never asks for more evidence
            return json.dumps({"action": "finish", "missing": "", "reason": "[mock] evidence reviewed"})
        if role == "verifier":  # supported only when most claim words appear in the passage (conservative)
            checks = []
            for cid, claim, passage in re.findall(r"CLAIM (\S+): (.+)\n  PASSAGE \[[^\]]*\]: (.+)", first_user):
                claim = claim.split(": ", 1)[-1]  # mock findings read "Search result for <role>: <quoted text>"
                words = set(re.findall(r"[a-z]{4,}", claim.lower()))
                hit = len(words & set(re.findall(r"[a-z]{4,}", passage.lower())))
                checks.append({"id": cid, "status": "supported" if words and hit >= 0.6 * len(words) else "unsupported",
                               "reason": "[mock] word overlap check"})
            return json.dumps({"checks": checks})
        hits = re.findall(r"\[(E\d+)\] (.+)", first_user)
        cite, title = ([hits[0][0]], hits[0][1].strip()) if hits else ([], "")
        if role == "candidates":
            names = []
            for _, t in hits:
                word = re.sub(r"[^A-Za-z0-9]", "", t.split()[0]) if t.split() else ""
                if len(word) >= 4 and word not in names:
                    names.append(word)
            names = names[:4] or ["Alpha (mock)", "Beta (mock)", "Gamma (mock)"]
            return json.dumps({"candidates": [{"name": n, "what_it_is": "[mock]"} for n in names]})
        if role == "profile":
            who = re.search(r"CANDIDATE: (.+)", first_user)
            return json.dumps(self._profile(who.group(1).strip() if who else "Unknown", cite, title, hits, first_user))
        return json.dumps(self._final(role, idea, cite, title))

    @staticmethod
    def _plan(idea: str) -> dict:
        head = re.split(r"\b(?:for|that|to|which|in)\b", idea)[0]
        words = [w for w in re.findall(r"[A-Za-z-]+", head) if w.lower() not in ("a", "an", "the")]
        return {
            "idea_summary": "[mock] " + idea,
            "category": " ".join(words[-3:]).lower() or "[mock] category",
            "payer": "consumer",
            "problem": idea,
            "industry": "unspecified",
            "search_keywords": idea.split()[:4],
            "extra_specialists": [{"role": "regulatory", "focus": "licensing and compliance",
                                   "questions": "What regulation applies to this business?"}],
            "tasks": {
                "customer": "Identify who has this problem and how they cope today.",
                "competitor": "Find the top three existing players.",
                "market": "Size the market and find current trends.",
                "technical": "Assess how hard an MVP is to build.",
                "financial": "Estimate costs, revenue and profit over five years.",
            },
        }

    @staticmethod
    def _profile(name: str, cite: List[str], title: str, hits=(), first_user: str = "") -> dict:
        own = [(i, t) for i, t in hits if name.lower() in t.lower()]
        if own:
            cite, title = [own[0][0]], own[0][1].strip()
        snippet = ""
        if cite:  # describe the product from its own evidence item (title + snippet), never invent
            m = re.search(r"\[%s\] .+\n\s+url: .*\n\s+(.+)" % re.escape(cite[0]), first_user)
            snippet = m.group(1).strip()[:160] if m else ""
        finding = ([{"claim": "Search result for %s: %s" % (name, title), "kind": "fact", "source_ids": cite}]
                   if cite else [{"claim": "[mock] placeholder for %s" % name, "kind": "estimate", "source_ids": []}])
        return {"name": name, "url": "", "description": "[mock] %s" % (snippet or title or "placeholder"),
                "relation": "direct",
                "intended_customer": "[mock] same customers", "pricing": "unknown",
                "strengths": ["brand"], "weaknesses": ["generic"], "source_ids": cite, "findings": finding}

    @staticmethod
    def _final(role: str, idea: str, cite: List[str], title: str = "") -> dict:
        if cite:  # quote the retrieved headline so the grounding check passes honestly
            finding = [{"claim": "Search result for %s: %s" % (role, title), "kind": "fact", "source_ids": cite}]
        else:
            finding = [{"claim": "[mock] placeholder finding for %s" % role, "kind": "estimate", "source_ids": []}]
        if role == "customer":
            return {"summary": "[mock] customer summary for %s" % idea,
                    "target_segment": "[mock] early adopters of %s" % idea, "problem": "[mock] the core problem",
                    "frequency": "unknown", "current_workarounds": ["[mock] informal workaround"],
                    "unmet_need_evidence": "not established", "willingness_to_pay": "unknown",
                    "reach_channels": ["[mock] community channel"], "open_questions": ["[mock] what would they pay?"],
                    "segments": [{"name": "Early adopters", "description": "Tech-savvy users of similar tools",
                                  "pain_points": ["time-consuming manual process"], "willingness_to_pay": "unknown",
                                  "size_estimate": "unknown"}], "findings": finding}
        if role == "competitor":
            comps = [{"name": "Competitor %s (mock)" % c, "url": "", "description": "placeholder",
                      "pricing": "unknown", "strengths": ["brand"], "weaknesses": ["generic"],
                      "source_ids": cite} for c in "ABC"]
            return {"summary": "[mock] competitor summary for %s" % idea, "competitors": comps,
                    "white_space": "[mock] underserved niche", "findings": finding}
        if role == "competitor_summary":
            return {"summary": "[mock] competitor summary for %s" % idea, "differentiation": "[mock] hypothesis",
                    "differentiation_status": "hypothesis", "switch_reasons": ["[mock] reason"],
                    "unknowns": ["[mock] pricing of alternatives"], "white_space": ""}
        if role == "market":
            return {"summary": "[mock] market summary for %s" % idea,
                    "tam_sam_som": {"tam_usd": 5e9, "sam_usd": 5e8, "som_usd": 5e6,
                                    "method": "[mock] top-down estimate"},
                    "launch_market": "[mock] launch area", "inputs": [{"name": "local participants", "value": None,
                                                                      "unit": "people", "source_ids": []}],
                    "density_note": "unknown", "open_questions": ["[mock] how many local participants?"],
                    "trends": ["[mock] growing demand"], "headwinds": ["[mock] incumbents"], "findings": finding}
        if role == "technical":
            return {"summary": "[mock] technical summary for %s" % idea, "feasibility_score": 4,
                    "user_journey": ["sign up", "set preferences", "get a match", "message"],
                    "components": [{"name": "web app", "responsibility": "user interface", "approach": "build"},
                                   {"name": "database", "responsibility": "store profiles", "approach": "buy"}],
                    "dependencies": ["hosting"], "delivery_risks": [{"risk": "data quality", "mitigation": "validation"}],
                    "effort": {"weeks_low": 6, "weeks_high": 12, "team": "1 developer", "scope": "MVP"},
                    "key_components": ["web app", "LLM API", "database"], "build_vs_buy": "buy most components",
                    "main_risks": ["data quality"], "mvp_time_months": 4, "mvp_team_size": 3, "findings": finding}
        if role == "financial":
            return {"rationale": "[mock] generic SaaS assumptions", "assumptions": {
                "arpu_monthly": 40, "year1_new_customers": 150, "growth_rate": 0.9, "annual_churn": 0.2,
                "cogs_pct": 0.2, "cac": 200, "other_opex_annual": 30000,
                "team": [{"role": "Founder/CEO", "count": 1, "annual_salary": 90000, "start_year": 1},
                         {"role": "Engineer", "count": 2, "annual_salary": 120000, "start_year": 1},
                         {"role": "Growth/Sales", "count": 1, "annual_salary": 85000, "start_year": 2}],
                "startup_costs": [{"item": "Legal & incorporation", "amount": 5000},
                                  {"item": "MVP build & tooling", "amount": 40000}]},
                    "findings": finding}
        if role not in ("synthesizer",):  # idea-specific extra specialist
            return {"summary": "[mock] %s summary for %s" % (role, idea), "key_points": ["[mock] point about %s" % idea],
                    "implications_for_founder": ["[mock] implication for %s" % idea],
                    "scenarios": [{"scenario": "[mock] misuse of %s" % idea, "harm": "[mock] harm",
                                   "control": "[mock] control", "limitation": "[mock] limitation", "basis": "proposed"}],
                    "open_questions": ["[mock] open question"], "findings": finding}
        return {  # synthesizer
            "verdict": "validate_first", "verdict_rationale": "[mock] more customer discovery needed",
            "recommendation": "[mock] run the validation tests below before building",
            "reasons": ["[mock] demand is not yet shown"], "key_uncertainties": ["[mock] willingness to pay"],
            "would_change_if": ["[mock] five pre-orders"], "founder_targets": [],
            "executive_summary": "[mock] Summary of %s." % idea,
            "scope": {"mvp_features": ["core workflow"], "target_customer": "early adopters",
                      "out_of_scope": ["enterprise features"], "success_definition": "10 paying pilots"},
            "risks": [{"risk": "weak demand", "severity": "high", "mitigation": "pre-sell before building"}],
            "validation_steps": [{"assumption": "customers will pay", "experiment": "landing page + 20 interviews",
                                  "success_metric": ">=5 pre-orders", "timeframe": "3 weeks",
                                  "hypothesis": "customers will pay", "category": "viability",
                                  "test": "landing page + 20 interviews", "metric": "pre-orders",
                                  "threshold": ">=5 pre-orders (proposed)", "time_cost": "3 weeks, about $100",
                                  "if_pass": "build the MVP", "if_fail": "revisit the price", "owner": "founder"}],
            "future_outlook": "[mock] outlook"}


def build_llm(config: Config, fast: bool = False):
    """The main model, or (fast=True) the cheaper model for extraction. They are the same unless LLM_FAST_MODEL is set."""
    if config.backend == "mock":
        return MockLLM()
    return OpenAICompatLLM(config, model=(config.fast_model or config.model) if fast else config.model)
