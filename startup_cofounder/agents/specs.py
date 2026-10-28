from __future__ import annotations

from .base import AgentSpec

FINDINGS_SCHEMA = '"findings": [{"claim": "<one specific statement>", "kind": "fact|estimate", "source_ids": ["E1"]}]'

CUSTOMER = AgentSpec(
    role="customer",
    mission="You are the Customer Discovery researcher on a startup due-diligence team. Work out who has "
            "this problem, how painful it is, how they cope today and what they might pay.",
    tools=["web_search", "hn_search", "news_search", "fetch_page"],
    schema="""{
  "summary": "<3-4 sentences>",
  "segments": [{"name": "", "description": "", "pain_points": [""], "willingness_to_pay": "", "size_estimate": ""}],
  """ + FINDINGS_SCHEMA + """
}""",
)

COMPETITOR = AgentSpec(
    role="competitor",
    mission="You are the Competitive Intelligence researcher. Identify the top existing players (direct "
            "competitors first, then close substitutes), their pricing, strengths and weaknesses, and the "
            "white space a new entrant could own. Only name companies that appear in your tool results or "
            "that you are certain exist.",
    tools=["web_search", "news_search", "wikipedia", "fetch_page"],
    schema="""{
  "summary": "<3-4 sentences>",
  "competitors": [{"name": "", "url": "", "description": "", "pricing": "", "strengths": [""], "weaknesses": [""], "source_ids": ["E1"]}],
  "white_space": "<where incumbents are weak>",
  """ + FINDINGS_SCHEMA + """
}
List the top competitors ranked by relevance (at least 3 if they exist).""",
)

MARKET = AgentSpec(
    role="market",
    mission="You are the Market Analyst. Size the market (TAM/SAM/SOM, show your method) and find current "
            "trends, tailwinds and headwinds from recent sources. Dollar values are plain numbers in USD.",
    tools=["news_search", "web_search", "wikipedia", "fetch_page"],
    schema="""{
  "summary": "<3-4 sentences>",
  "tam_sam_som": {"tam_usd": 0, "sam_usd": 0, "som_usd": 0, "method": "<how derived, cite ids>"},
  "trends": [""], "headwinds": [""],
  """ + FINDINGS_SCHEMA + """
}""",
)

TECHNICAL = AgentSpec(
    role="technical",
    mission="You are the Technical Feasibility reviewer. Judge how hard an MVP is to build with today's "
            "technology, what to build vs buy, and the main technical risks.",
    tools=["web_search", "hn_search", "wikipedia", "fetch_page"],
    schema="""{
  "summary": "<3-4 sentences>",
  "feasibility_score": 3,
  "key_components": [""], "build_vs_buy": "", "main_risks": [""],
  "mvp_time_months": 4, "mvp_team_size": 3,
  """ + FINDINGS_SCHEMA + """
}
feasibility_score is 1 (research-grade, unlikely) to 5 (routine engineering).""",
)

FINANCIAL = AgentSpec(
    role="financial",
    mission="You are the Financial Planner. Using the other agents' findings, propose realistic model "
            "assumptions for the first five years. You do NOT do the arithmetic; code does. Anchor price "
            "and CAC to competitor pricing and benchmarks where evidence exists. Rates are decimals "
            "(0.2 = 20%).",
    tools=["web_search", "fetch_page"],
    max_tool_calls=2,
    schema="""{
  "rationale": "<why these assumptions>",
  "assumptions": {
    "arpu_monthly": 0, "year1_new_customers": 0, "growth_rate": 0.0, "annual_churn": 0.0,
    "cogs_pct": 0.0, "cac": 0, "other_opex_annual": 0,
    "team": [{"role": "", "count": 1, "annual_salary": 0, "start_year": 1}],
    "startup_costs": [{"item": "", "amount": 0}]
  },
  """ + FINDINGS_SCHEMA + """
}
growth_rate = year-over-year growth in NEW customers acquired. team gives the basic organizational
structure and when each role is hired (start_year 1-5).""",
)

SYNTHESIZER = AgentSpec(
    role="synthesizer",
    mission="You are the Co-Founder who reads all the research and writes the decision memo. Be candid: "
            "if the evidence is weak or the economics fail, say so. Tell the founder what is a sourced "
            "fact versus an estimate. Look forward: where will this market be in 3-5 years?",
    tools=[],
    schema="""{
  "verdict": "go|validate_first|pivot|no_go",
  "verdict_rationale": "<2-3 sentences referencing the evidence and the financial model>",
  "executive_summary": "<one paragraph>",
  "scope": {"target_customer": "", "mvp_features": [""], "out_of_scope": [""], "success_definition": ""},
  "risks": [{"risk": "", "severity": "low|medium|high", "mitigation": ""}],
  "validation_steps": [{"assumption": "", "experiment": "", "success_metric": "", "timeframe": ""}],
  "future_outlook": "<3-5 year view>"
}
Order validation_steps by which assumption would kill the business fastest if wrong.""",
)

COORDINATOR = AgentSpec(
    role="coordinator",
    mission="You are the Coordinator. Turn a rough business idea into a research plan for five specialist "
            "agents. Sharpen vague ideas into a concrete product hypothesis without changing the founder's intent.",
    tools=[],
    schema="""{
  "idea_summary": "<one precise sentence: who is the customer, what problem, what product>",
  "industry": "<industry / category name>",
  "search_keywords": ["<3-6 terms that real articles about this market would use>"],
  "tasks": {
    "customer": "<specific research questions>", "competitor": "<specific research questions>",
    "market": "<specific research questions>", "technical": "<specific research questions>",
    "financial": "<what to model, pricing model hint>"
  },
  "extra_specialists": [{"role": "<snake_case_name>", "focus": "<topic>", "questions": "<specific research questions>"}]
}
extra_specialists: 0-2 additional researchers, ONLY for a dimension this idea clearly needs that the five
core agents do not cover (e.g. regulation/licensing, supply chain, safety, data/privacy, distribution
partners). Use an empty list for ordinary software ideas.""",
)

CRITIC = AgentSpec(
    role="critic",
    mission="You are the skeptical Reviewer. You receive each researcher's output and a list of problems "
            "already found by automatic checks. Add only gaps that would change a decision: unsupported "
            "claims, missing evidence, vague segments, wrong or missing competitors, implausible numbers. "
            "Do not repeat the automatic problems and do not nitpick style.",
    tools=[],
    schema="""{
  "approved": false,
  "gaps": [{"agent": "<role name of the agent to redo>", "issue": "<what is wrong>", "followup_task": "<specific instructions to fix it>"}]
}
Use an empty gaps list and approved=true if the research is good enough to build a business plan on.""",
)


def make_extra_specialist(role: str, focus: str) -> AgentSpec:
    """Build a generic researcher for an idea-specific topic chosen by the coordinator."""
    return AgentSpec(
        role=role,
        mission="You are a specialist researcher on this topic: %s. Find what a founder in this space "
                "must know about it, with evidence." % focus,
        tools=["web_search", "news_search", "wikipedia", "fetch_page"],
        schema="""{
  "summary": "<3-4 sentences>",
  "key_points": [""],
  "implications_for_founder": [""],
  """ + FINDINGS_SCHEMA + """
}""",
    )

RESEARCHERS = [CUSTOMER, COMPETITOR, MARKET, TECHNICAL]
