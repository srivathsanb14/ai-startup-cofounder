import json

import pytest
import requests

from startup_cofounder.budget import RunBudget
from startup_cofounder.config import Config
from startup_cofounder.llm import LLMError, MockLLM, OpenAICompatLLM
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.report import render_markdown


def test_budget_reserves_report_time():
    now = [0]
    budget = RunBudget(60, clock=lambda: now[0])
    now[0] = 3000
    assert not budget.available()
    budget.phase = "financial"
    assert budget.remaining() == 300
    now[0] = 3300
    assert not budget.available()
    budget.phase = "synthesis"
    assert budget.remaining() == 300
    now[0] = 3600
    assert not budget.available()


def test_disabled_budget_does_not_expire():
    budget = RunBudget(0, clock=lambda: 100000)
    assert budget.available()
    assert budget.remaining() == float("inf")


def test_llm_stops_retrying_at_deadline(monkeypatch):
    now = [2998]
    budget = RunBudget(60, clock=lambda: 0)
    budget.clock = lambda: now[0]
    client = OpenAICompatLLM(Config(timeout=240))
    client.budget = budget
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["timeout"])
        now[0] = 3000
        raise requests.Timeout("test")

    monkeypatch.setattr("startup_cofounder.llm.requests.post", post)
    monkeypatch.setattr("startup_cofounder.llm.time.sleep", lambda _: None)
    with pytest.raises(LLMError, match="Time budget"):
        client.chat([{"role": "system", "content": "ROLE: customer\n"}])
    assert calls == [2]


def test_limits_apply_and_truncated_json_is_rejected(monkeypatch):
    seen = []

    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"finish_reason": "length", "message": {"content": '{"apparently_valid": true}'}}]}

    def post(url, **kwargs):
        seen.append(kwargs["json"]["max_tokens"])
        return Response()

    monkeypatch.setattr("startup_cofounder.llm.requests.post", post)
    client = OpenAICompatLLM(Config(coordinator_tokens=1000, max_tokens=2400))
    for role in ("coordinator", "customer"):
        assert client.chat([{"role": "system", "content": "ROLE: %s\n" % role}]) == ""
    # LLM_MAX_TOKENS is a ceiling; section replies are capped per role so prompt + reply fit a 4K context.
    assert seen == [1000, 900]


def test_expired_research_still_produces_report(monkeypatch, tmp_path):
    now = [0]
    budget = RunBudget(60, clock=lambda: now[0])
    monkeypatch.setattr("startup_cofounder.pipeline.RunBudget", lambda *args: budget)

    class SlowPlan(MockLLM):
        def chat(self, messages, **kwargs):
            answer = super().chat(messages, **kwargs)
            if messages[0]["content"].startswith("ROLE: coordinator\n"):
                now[0] = 3000
            return answer

    cfg = Config(agent_design="sections", backend="mock", offline=True, run_minutes=60, max_workers=1,
                 cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")
    result = Pipeline(cfg, llm=SlowPlan()).run("An indoor climbing partner matching app")
    assert any("Time budget limited" in w for w in result.warnings)
    assert result.results["customer"].error
    assert not result.results["financial"].error
    assert not result.results["synthesizer"].error
    assert result.verdict != "go"
    assert "## 1. Decision and rationale" in render_markdown(result)
    json.dumps(result.to_dict(), default=str)
