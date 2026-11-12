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
    "geography": STR, "payer": {"type": "string", "enum": ["consumer", "business"]}, "customer_type": STR,
    "tasks": obj({"customer": STR, "competitor": STR, "market": STR, "technical": STR, "financial": STR}),
    "extra_specialists": arr(obj({"role": STR, "focus": STR, "questions": STR}, ["role", "focus"])),
}, ["idea_summary", "category", "problem", "tasks"])

CANDIDATES = obj({"candidates": arr(obj({"name": STR, "what_it_is": STR}, ["name"]))}, ["candidates"])

PROFILE = obj({
    "name": STR, "is_competitor": {"type": "boolean"}, "url": STR, "description": STR,
    "intended_customer": STR, "relation": {"type": "string", "enum": ["direct", "substitute", "adjacent", "irrelevant",
                                                                       "unresolved"]}, "pricing": STR, "strengths": STRS, "weaknesses": STRS,
    "verified_differences": STRS, "unknowns": STRS,
    "source_ids": STRS, "findings": FINDINGS,
}, ["name", "description", "intended_customer", "relation", "pricing", "strengths", "weaknesses", "source_ids",
    "findings"])

COMPETITOR_SUMMARY = obj({"summary": STR, "differentiation": STR,
                          "differentiation_status": {"type": "string", "enum": ["established", "hypothesis"]},
                          "switch_reasons": STRS, "unknowns": STRS, "white_space": STR},
                         ["summary", "differentiation", "differentiation_status", "unknowns"])

NULLNUM = {"type": ["number", "null"]}
FINDINGS = arr(obj({"claim": STR, "kind": {"type": "string", "enum": ["fact", "estimate", "proposal"]},
                    "source_ids": STRS}, ["claim", "kind", "source_ids"]))

CUSTOMER = obj({
    "summary": STR, "target_segment": STR, "problem": STR, "frequency": STR, "current_workarounds": STRS,
    "unmet_need_evidence": STR, "willingness_to_pay": STR, "reach_channels": STRS, "open_questions": STRS,
    "segments": arr(obj({"name": STR, "description": STR, "pain_points": STRS,
                         "willingness_to_pay": STR, "size_estimate": STR}, ["name"])),
    "findings": FINDINGS,
}, ["summary", "target_segment", "problem", "current_workarounds", "willingness_to_pay", "findings"])

MARKET = obj({
    "summary": STR, "launch_market": STR,
    "inputs": arr(obj({"name": STR, "value": NULLNUM, "unit": STR, "source_ids": STRS, "geography": STR},
                      ["name", "value", "unit"])),
    "density_note": STR,
    "tam_sam_som": obj({"tam_usd": NUM, "sam_usd": NUM, "som_usd": NUM, "method": STR},
                       ["tam_usd", "sam_usd", "som_usd", "method"]),
    "trends": STRS, "headwinds": STRS, "open_questions": STRS, "findings": FINDINGS,
}, ["summary", "launch_market", "inputs", "tam_sam_som", "findings"])

TECHNICAL = obj({
    "summary": STR, "user_journey": STRS,
    "components": arr(obj({"name": STR, "responsibility": STR,
                           "approach": {"type": "string", "enum": ["build", "buy", "open-source"]}},
                          ["name", "responsibility", "approach"])),
    "dependencies": STRS, "delivery_risks": arr(obj({"risk": STR, "mitigation": STR}, ["risk"])),
    "effort": obj({"weeks_low": NUM, "weeks_high": NUM, "team": STR, "scope": STR}),
    "feasibility_score": INT, "key_components": STRS, "main_risks": STRS, "build_vs_buy": STR,
    "mvp_time_months": NUM, "mvp_team_size": NUM, "findings": FINDINGS,
}, ["summary", "user_journey", "components", "delivery_risks", "effort", "findings"])

EXTRA = obj({"summary": STR, "key_points": STRS, "implications_for_founder": STRS, "open_questions": STRS,
             "findings": FINDINGS}, ["summary", "key_points", "findings"])

RISK = obj({"summary": STR,
            "scenarios": arr(obj({"scenario": STR, "harm": STR, "control": STR, "limitation": STR,
                                  "basis": {"type": "string", "enum": ["proposed", "legal_requirement"]},
                                  "source_ids": STRS}, ["scenario", "harm", "control", "limitation", "basis"])),
            "open_questions": STRS, "findings": FINDINGS}, ["summary", "scenarios", "findings"])

FINANCIAL = obj({
    "rationale": STR, "payer": STR, "price_basis": STR,
    "plan_type": {"type": "string", "enum": ["lean_validation", "staffed_company"]},
    "paying_share_of_active": NUM,
    "assumptions": obj({
        "arpu_monthly": NUM, "year1_new_customers": NUM, "growth_rate": NUM, "annual_churn": NUM,
        "cogs_pct": NUM, "cac": NUM, "other_opex_annual": NUM,
        "team": arr(obj({"role": STR, "count": INT, "annual_salary": NUM, "start_year": INT})),
        "startup_costs": arr(obj({"item": STR, "amount": NUM})),
    }, ["arpu_monthly", "year1_new_customers", "growth_rate", "annual_churn", "cogs_pct", "cac", "team"]),
    "inputs": arr(obj({"name": STR, "basis": {"type": "string", "enum": ["evidence", "assumption"]}, "source_ids": STRS,
                       "reason": STR, "uncertainty": STR}, ["name", "basis"])),
    "findings": FINDINGS,
}, ["rationale", "payer", "assumptions", "findings"])

SYNTHESIZER = obj({
    "verdict": {"type": "string", "enum": ["go", "validate_first", "pivot", "no_go"]},
    "recommendation": STR, "reasons": STRS, "key_uncertainties": STRS, "would_change_if": STRS, "founder_targets": STRS,
    "scope": obj({"target_customer": STR, "mvp_features": STRS, "out_of_scope": STRS}),
    "risks": arr(obj({"risk": STR, "severity": {"type": "string", "enum": ["low", "medium", "high"]}, "mitigation": STR})),
    "validation_steps": arr(obj({"hypothesis": STR, "category": {"type": "string", "enum": [
        "desirability", "feasibility", "viability"]}, "test": STR, "metric": STR, "threshold": STR, "time_cost": STR,
        "if_pass": STR, "if_fail": STR, "owner": {"type": "string", "enum": ["founder", "software"]}},
        ["hypothesis", "test", "metric", "threshold", "owner"])),
}, ["verdict", "recommendation", "reasons", "key_uncertainties", "validation_steps"])

CRITIC = obj({"approved": {"type": "boolean"},
              "gaps": arr(obj({"agent": STR, "issue": STR, "followup_task": STR, "field": STR, "acceptance": STR,
                               "severity": {"type": "string", "enum": ["high", "medium", "low"]}},
                              ["agent", "issue", "followup_task"]))}, ["gaps"])

BY_ROLE = {
    "coordinator": COORDINATOR, "candidates": CANDIDATES, "profile": PROFILE,
    "competitor_summary": COMPETITOR_SUMMARY, "customer": CUSTOMER, "market": MARKET, "technical": TECHNICAL,
    "financial": FINANCIAL, "synthesizer": SYNTHESIZER, "critic": CRITIC,
}
