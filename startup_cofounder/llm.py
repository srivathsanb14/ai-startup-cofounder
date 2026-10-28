from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional

import requests

from .config import Config

Messages = List[Dict[str, str]]


class LLMError(RuntimeError):
    pass


class OpenAICompatLLM:
    """Chat client for any OpenAI-compatible endpoint (Ollama, vLLM, llama.cpp, LM Studio)."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def chat(self, messages: Messages, temperature: Optional[float] = None, json_mode: bool = False) -> str:
        cfg = self.config
        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature if temperature is None else temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": "Bearer " + cfg.api_key}
        url = cfg.base_url + "/chat/completions"
        last_err = None
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=cfg.timeout)
                if resp.status_code == 400 and "response_format" in payload:
                    payload.pop("response_format")  # server does not support JSON mode
                    continue
                if resp.status_code >= 500:
                    raise LLMError("server error %d: %s" % (resp.status_code, resp.text[:200]))
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"] or ""
            except (requests.RequestException, LLMError, KeyError, ValueError) as exc:
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(
            "LLM call failed (%s). Is your model server running at %s?" % (last_err, cfg.base_url)
        )


class MockLLM:
    """Deterministic stand-in so the whole pipeline can be demoed and tested without a model.

    Output is generic scaffolding, clearly labelled, never real research.
    """

    RESEARCH_ROLES = {"customer", "competitor", "market", "technical", "financial"}

    def chat(self, messages: Messages, temperature: Optional[float] = None, json_mode: bool = False) -> str:
        system = messages[0]["content"]
        role = re.search(r"ROLE: (\w+)", system).group(1)
        first_user = messages[1]["content"]
        idea_match = re.search(r"IDEA: (.+)", first_user)
        idea = idea_match.group(1).strip() if idea_match else "the idea"
        observed = [m["content"] for m in messages if m["role"] == "user" and m["content"].startswith("TOOL_OBSERVATION")]

        if role == "coordinator":
            return json.dumps(self._plan(idea))
        if role == "critic":
            return json.dumps({"approved": True, "gaps": []})
        offered = re.findall(r"^- (\w+)\(", system, flags=re.M)  # tools this agent may actually use
        if role not in ("financial", "synthesizer") and offered and not observed:
            tool = "web_search" if "web_search" in offered else offered[0]
            return json.dumps({"thought": "start with a search", "tool": tool,
                               "args": {"query": "%s %s" % (idea, role)}})
        cite, title = [], ""
        if observed:
            hit = re.search(r"\[(E\d+)\] (.+)", observed[-1])
            if hit:
                cite, title = [hit.group(1)], hit.group(2).strip()
        return json.dumps({"final": self._final(role, idea, cite, title)})

    @staticmethod
    def _plan(idea: str) -> dict:
        return {
            "idea_summary": "[mock] " + idea,
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
    def _final(role: str, idea: str, cite: List[str], title: str = "") -> dict:
        if cite:  # quote the retrieved headline so the grounding check passes honestly
            finding = [{"claim": "Search result for %s: %s" % (role, title), "kind": "fact", "source_ids": cite}]
        else:
            finding = [{"claim": "[mock] placeholder finding for %s" % role, "kind": "estimate", "source_ids": []}]
        if role == "customer":
            return {"summary": "[mock] customer summary", "segments": [{
                "name": "Early adopters", "description": "Tech-savvy users of similar tools",
                "pain_points": ["time-consuming manual process"], "willingness_to_pay": "$20-50/mo",
                "size_estimate": "unknown"}], "findings": finding}
        if role == "competitor":
            comps = [{"name": "Competitor %s (mock)" % c, "url": "", "description": "placeholder",
                      "pricing": "unknown", "strengths": ["brand"], "weaknesses": ["generic"],
                      "source_ids": cite} for c in "ABC"]
            return {"summary": "[mock] competitor summary", "competitors": comps,
                    "white_space": "[mock] underserved niche", "findings": finding}
        if role == "market":
            return {"summary": "[mock] market summary",
                    "tam_sam_som": {"tam_usd": 5e9, "sam_usd": 5e8, "som_usd": 5e6,
                                    "method": "[mock] top-down estimate"},
                    "trends": ["[mock] growing demand"], "headwinds": ["[mock] incumbents"], "findings": finding}
        if role == "technical":
            return {"summary": "[mock] technical summary", "feasibility_score": 4,
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
            return {"summary": "[mock] %s summary" % role, "key_points": ["[mock] point"],
                    "implications_for_founder": ["[mock] implication"], "findings": finding}
        return {  # synthesizer
            "verdict": "validate_first", "verdict_rationale": "[mock] more customer discovery needed",
            "executive_summary": "[mock] Summary of %s." % idea,
            "scope": {"mvp_features": ["core workflow"], "target_customer": "early adopters",
                      "out_of_scope": ["enterprise features"], "success_definition": "10 paying pilots"},
            "risks": [{"risk": "weak demand", "severity": "high", "mitigation": "pre-sell before building"}],
            "validation_steps": [{"assumption": "customers will pay", "experiment": "landing page + 20 interviews",
                                  "success_metric": ">=5 pre-orders", "timeframe": "3 weeks"}],
            "future_outlook": "[mock] outlook"}


def build_llm(config: Config):
    if config.backend == "mock":
        return MockLLM()
    return OpenAICompatLLM(config)
