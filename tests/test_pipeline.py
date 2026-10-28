import json

from startup_cofounder.config import Config
from startup_cofounder.llm import MockLLM
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.report import render_markdown
from startup_cofounder.tools import ALL_TOOLS, ToolResult


def _config(tmp_path, **kw):
    return Config.from_env(backend="mock", cache_dir=tmp_path / "cache", **kw)


def test_end_to_end_offline_mock(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True)).run("An app that matches restaurants with local farms")
    assert set(result.results) >= {"customer", "competitor", "market", "technical", "financial", "synthesizer"}
    assert not any(r.error for r in result.results.values())
    assert not any("failed" in w for w in result.warnings)
    # no web evidence offline, so nothing may be presented as a sourced fact
    assert all(f.kind == "estimate" for r in result.results.values() for f in r.findings)
    md = render_markdown(result)
    for heading in ("## Verdict", "## Competitive landscape (top 3)", "## Financial projection",
                    "## Recommended validation steps", "## Evidence quality"):
        assert heading in md
    json.dumps(result.to_dict(), default=str)


def test_citations_flow_through_with_stub_tool(tmp_path, monkeypatch):
    def fake(query):
        return ToolResult(sources=[{"title": "Farm tech news", "url": "http://x/" + query[:5], "snippet": "snip"}])

    monkeypatch.setitem(ALL_TOOLS, "web_search", type(ALL_TOOLS["web_search"])(
        "web_search", "stub", {"query": "string"}, fake))
    result = Pipeline(_config(tmp_path)).run("An app that matches restaurants with local farms")
    facts = [f for r in result.results.values() for f in r.findings if f.kind == "fact"]
    assert facts and all(f.source_ids for f in facts)
    assert result.sources and "[E1]" in render_markdown(result)


class BrokenLLM:
    def chat(self, messages, temperature=None, json_mode=False):
        return "I am a chatty model that never emits JSON."


def test_pipeline_survives_garbage_model(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True), llm=BrokenLLM()).run("A marketplace for used lab equipment")
    assert result.warnings
    md = render_markdown(result)  # must still render with defaults
    assert "Financial projection" in md


def test_short_idea_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        Pipeline(_config(tmp_path)).run("hi")


class CriticLLM(MockLLM):
    """Mock whose critic always complains about the competitor agent and counts agent calls."""

    def __init__(self):
        self.competitor_runs = 0

    def chat(self, messages, temperature=None, json_mode=False):
        system = messages[0]["content"]
        if "ROLE: critic" in system:
            return json.dumps({"approved": False, "gaps": [
                {"agent": "competitor", "issue": "needs pricing detail", "followup_task": "find pricing pages"}]})
        if "ROLE: competitor" in system and len(messages) == 2:
            self.competitor_runs += 1
        return super().chat(messages, temperature, json_mode)


def test_critic_loop_reruns_flagged_agent(tmp_path):
    llm = CriticLLM()
    result = Pipeline(_config(tmp_path, offline=True, critic_rounds=1), llm=llm).run("A tool for freelancers to invoice clients")
    assert llm.competitor_runs == 2  # original + one redo
    entries = [e for e in result.review_log if e["agent"] == "competitor"]
    assert entries and entries[0]["improved"] is True


def test_critic_rounds_zero_skips_review(tmp_path):
    llm = CriticLLM()
    result = Pipeline(_config(tmp_path, offline=True, critic_rounds=0), llm=llm).run("A tool for freelancers to invoice clients")
    assert llm.competitor_runs == 1 and result.review_log == []


def test_extra_specialists_sanitized_and_capped(tmp_path):
    pipe = Pipeline(_config(tmp_path, offline=True, max_extra_specialists=2))
    plan = {"extra_specialists": [
        {"role": "Customer", "focus": "reserved name"},          # reserved -> dropped
        {"role": "x", "focus": "too short"},                      # too short -> dropped
        {"role": "Food Safety!", "focus": "regulation", "questions": "FDA rules?"},
        {"role": "supply chain", "focus": "suppliers"},
        {"role": "third_one", "focus": "over the cap"},
        "garbage"]}
    extras = pipe._extra_specs(plan)
    assert [e.role for e in extras] == ["food_safety", "supply_chain"]
    assert extras[0].extra_task == "FDA rules?"


def test_pipeline_populates_new_outputs(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True)).run("An app that matches restaurants with local farms")
    assert result.extra_roles == ["regulatory"] and "regulatory" in result.results
    assert set(result.scenarios) == {"pessimistic", "base", "optimistic"}
    assert len(result.sensitivity) == 6 and result.unit_economics["ltv_cac"]
    assert result.grade == "D" and result.verdict in ("go", "validate_first", "pivot", "no_go")
    md = render_markdown(result)
    for heading in ("## At a glance", "### Scenarios", "### Unit economics", "### What matters most",
                    "## Quality review", "## Additional research: Regulatory"):
        assert heading in md
    json.dumps(result.to_dict(), default=str)


class OptimisticLLM(MockLLM):
    def chat(self, messages, temperature=None, json_mode=False):
        out = super().chat(messages, temperature, json_mode)
        if "ROLE: synthesizer" in messages[0]["content"]:
            data = json.loads(out)
            data["final"]["verdict"] = "go"
            return json.dumps(data)
        return out


def test_guardrail_downgrades_unsupported_go(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True), llm=OptimisticLLM()).run("A tool for freelancers to invoice clients")
    assert result.synthesis["verdict"] == "go"
    assert result.verdict == "validate_first" and "guardrail" in result.verdict_note
