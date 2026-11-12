"""JSON Schemas used for constrained decoding (Ollama/vLLM `response_format: json_schema`).

They are deliberately loose (types and required keys only) so a small model is guided into the
right shape without being boxed into loops by overly strict grammars.
"""
from __future__ import annotations

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}
STRS = {"type": "array", "items": STR}


def obj(props: dict, required=()) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


def arr(item: dict) -> dict:
    return {"type": "array", "items": item}


FINDINGS = arr(obj({"claim": STR, "kind": {"type": "string", "enum": ["fact", "estimate"]}, "source_ids": STRS},
                   ["claim", "kind", "source_ids"]))

COORDINATOR = obj({
    "idea_summary": STR, "category": STR, "problem": STR, "industry": STR, "search_keywords": STRS,
    "tasks": obj({"customer": STR, "competitor": STR, "market": STR, "technical": STR, "financial": STR}),
    "extra_specialists": arr(obj({"role": STR, "focus": STR, "questions": STR}, ["role", "focus"])),
}, ["idea_summary", "category", "problem", "tasks"])

CANDIDATES = obj({"candidates": arr(obj({"name": STR, "what_it_is": STR}, ["name"]))}, ["candidates"])

PROFILE = obj({
    "name": STR, "is_competitor": {"type": "boolean"}, "url": STR, "description": STR, "pricing": STR, "strengths": STRS, "weaknesses": STRS,
    "source_ids": STRS, "findings": FINDINGS,
}, ["name", "description", "pricing", "strengths", "weaknesses", "source_ids", "findings"])

COMPETITOR_SUMMARY = obj({"summary": STR, "white_space": STR}, ["summary", "white_space"])

CUSTOMER = obj({
    "summary": STR,
    "segments": arr(obj({"name": STR, "description": STR, "pain_points": STRS,
                         "willingness_to_pay": STR, "size_estimate": STR}, ["name", "description", "pain_points"])),
    "findings": FINDINGS,
}, ["summary", "segments", "findings"])

MARKET = obj({
    "summary": STR,
    "tam_sam_som": obj({"tam_usd": NUM, "sam_usd": NUM, "som_usd": NUM, "method": STR},
                       ["tam_usd", "sam_usd", "som_usd", "method"]),
    "trends": STRS, "headwinds": STRS, "findings": FINDINGS,
}, ["summary", "tam_sam_som", "trends", "headwinds", "findings"])

TECHNICAL = obj({
    "summary": STR, "feasibility_score": INT, "key_components": STRS, "build_vs_buy": STR, "main_risks": STRS,
    "mvp_time_months": NUM, "mvp_team_size": NUM, "findings": FINDINGS,
}, ["summary", "feasibility_score", "key_components", "main_risks", "findings"])

EXTRA = obj({"summary": STR, "key_points": STRS, "implications_for_founder": STRS, "findings": FINDINGS},
            ["summary", "key_points", "findings"])

FINANCIAL = obj({
    "rationale": STR,
    "assumptions": obj({
        "arpu_monthly": NUM, "year1_new_customers": NUM, "growth_rate": NUM, "annual_churn": NUM,
        "cogs_pct": NUM, "cac": NUM, "other_opex_annual": NUM,
        "team": arr(obj({"role": STR, "count": INT, "annual_salary": NUM, "start_year": INT})),
        "startup_costs": arr(obj({"item": STR, "amount": NUM})),
    }, ["arpu_monthly", "year1_new_customers", "growth_rate", "annual_churn", "cogs_pct", "cac", "team"]),
    "findings": FINDINGS,
}, ["rationale", "assumptions", "findings"])

SYNTHESIZER = obj({
    "verdict": {"type": "string", "enum": ["go", "validate_first", "pivot", "no_go"]},
    "verdict_rationale": STR, "executive_summary": STR,
    "scope": obj({"target_customer": STR, "mvp_features": STRS, "out_of_scope": STRS, "success_definition": STR}),
    "risks": arr(obj({"risk": STR, "severity": {"type": "string", "enum": ["low", "medium", "high"]}, "mitigation": STR})),
    "validation_steps": arr(obj({"assumption": STR, "experiment": STR, "success_metric": STR, "timeframe": STR})),
    "future_outlook": STR,
}, ["verdict", "verdict_rationale", "executive_summary", "scope", "risks", "validation_steps", "future_outlook"])

CRITIC = obj({"approved": {"type": "boolean"},
              "gaps": arr(obj({"agent": STR, "issue": STR, "followup_task": STR}, ["agent", "issue"]))}, ["gaps"])

BY_ROLE = {
    "coordinator": COORDINATOR, "candidates": CANDIDATES, "profile": PROFILE,
    "competitor_summary": COMPETITOR_SUMMARY, "customer": CUSTOMER, "market": MARKET, "technical": TECHNICAL,
    "financial": FINANCIAL, "synthesizer": SYNTHESIZER, "critic": CRITIC,
}
