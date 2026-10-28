import pytest

from startup_cofounder.evidence import EvidenceLedger, normalize_findings
from startup_cofounder.finance import project, sanitize
from startup_cofounder.jsonutil import extract_json


def test_extract_json_handles_noise():
    reply = '<think>hmm {not json}</think>Sure!\n```json\n{"final": {"a": "x}y"}}\n```'
    assert extract_json(reply) == {"final": {"a": "x}y"}}
    assert extract_json('prefix {"a": 1} suffix') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_ledger_dedupes_and_validates():
    ledger = EvidenceLedger()
    a = ledger.add("web_search", [{"title": "A", "url": "http://a", "snippet": "s"}])
    b = ledger.add("news_search", [{"title": "A again", "url": "http://a", "snippet": "s"}])
    assert a[0].id == b[0].id == "E1"
    assert ledger.valid_ids(["e1", "[E1]", "E9", "junk"]) == ["E1"]


def test_unsourced_facts_are_downgraded():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "Meal kit market report", "url": "http://a",
                               "snippet": "The meal kit delivery market reached 12.5 billion dollars in 2024, growing 8%."}])
    findings = normalize_findings([
        {"claim": "Meal kit delivery market reached 12.5 billion in 2024", "kind": "fact", "source_ids": ["E1"]},
        {"claim": "Meal kit delivery market reached 99 billion in 2024", "kind": "fact", "source_ids": ["E1"]},
        {"claim": "Gardening robots are popular among teenagers", "kind": "fact", "source_ids": ["E1"]},
        {"claim": "no citation at all", "kind": "fact", "source_ids": ["E7"]},
        {"claim": "a guess", "kind": "estimate"},
        "bare string",
    ], ledger)
    assert (findings[0].kind, findings[0].downgraded) == ("fact", False)
    assert findings[1].kind == "estimate" and "99" in findings[1].note       # number not in source
    assert findings[2].kind == "estimate" and "wording" in findings[2].note  # unrelated claim
    assert findings[3].kind == "estimate" and findings[3].note == "no valid citation"
    assert findings[4].kind == "estimate" and not findings[4].downgraded
    assert findings[5].kind == "estimate"


def test_sanitize_clamps_and_fixes_percentages():
    a = sanitize({"annual_churn": 20, "cogs_pct": "25%", "arpu_monthly": "$1,200", "growth_rate": 99, "team": "bad"})
    assert a["annual_churn"] == pytest.approx(0.2)
    assert a["cogs_pct"] == pytest.approx(0.25)
    assert a["arpu_monthly"] == 1200
    assert a["growth_rate"] == 5.0
    assert a["team"]  # default team restored


def test_projection_math():
    p = project({
        "arpu_monthly": 100, "year1_new_customers": 100, "growth_rate": 1.0, "annual_churn": 0.0,
        "cogs_pct": 0.0, "cac": 0, "other_opex_annual": 0, "payroll_burden": 0.0,
        "team": [{"role": "x", "count": 1, "annual_salary": 50000, "start_year": 1}],
        "startup_costs": [{"item": "a", "amount": 10000}],
    })
    t = p.table
    assert t.loc[0, "customers_end"] == 100
    assert t.loc[0, "revenue"] == pytest.approx(100 * 12 * 50)  # average of 0 and 100 customers
    assert t.loc[1, "new_customers"] == 200 and t.loc[1, "customers_end"] == 300
    assert t.loc[0, "operating_profit"] == pytest.approx(60000 - 50000)
    assert t.loc[0, "cumulative_cash"] == pytest.approx(0)
    assert p.breakeven_year == 1 and p.payback_year == 1 and p.startup_total == 10000


def test_projection_without_breakeven():
    p = project({"arpu_monthly": 1, "year1_new_customers": 1})
    assert p.breakeven_year is None and p.payback_year is None and p.peak_funding_need > 0


def test_web_search_provider_order(monkeypatch):
    import json as _json
    from startup_cofounder.tools import search
    from startup_cofounder.tools.base import Http

    calls = []

    def fake_get(url, params=None, timeout=12, headers=None):
        calls.append((url, headers))
        if "brave" in url:
            return _json.dumps({"web": {"results": [{"title": "B", "url": "http://b", "description": "<b>d</b>"}]}})
        if "searx" in url:
            return _json.dumps({"results": [{"title": "S", "url": "http://s", "content": "c"}]})
        return "<html></html>"

    monkeypatch.setattr(Http, "get", staticmethod(fake_get))
    monkeypatch.setenv("BRAVE_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_URL", "http://searx.local")
    r = search.web_search("q")
    assert r.sources[0]["title"] == "B" and r.sources[0]["snippet"] == "d"
    assert calls[0][1]["X-Subscription-Token"] == "k"

    monkeypatch.delenv("BRAVE_API_KEY")
    assert search.web_search("q").sources[0]["title"] == "S"

    monkeypatch.delenv("SEARXNG_URL")
    assert search.web_search("q").text == "no results"  # DuckDuckGo fallback


def test_unit_economics_scenarios_sensitivity():
    from startup_cofounder.finance import scenarios, sensitivity, unit_economics, sanity_flags
    a = {"arpu_monthly": 50, "year1_new_customers": 200, "cac": 100, "cogs_pct": 0.2, "annual_churn": 0.2}
    ue = unit_economics(a)
    assert ue["gross_margin_monthly"] == pytest.approx(40)
    assert ue["cac_payback_months"] == pytest.approx(2.5)
    assert ue["ltv_cac"] == pytest.approx(ue["ltv"] / 100)
    sc = scenarios(a)
    last = {k: v.table.iloc[-1]["operating_profit"] for k, v in sc.items()}
    assert last["pessimistic"] < last["base"] < last["optimistic"]
    sens = sensitivity(a)
    assert sens[0]["swing"] >= sens[-1]["swing"] and len(sens) == 6
    bad = unit_economics({"arpu_monthly": 10, "cac": 500, "annual_churn": 0.6})
    assert any("LTV/CAC" in f for f in sanity_flags(project({"arpu_monthly": 10, "cac": 500}), bad))
    assert unit_economics({"cac": 0})["cac_payback_months"] == 0.0


def test_disabled_tools_are_hidden_from_agents(monkeypatch):
    from startup_cofounder.tools import get_tools
    monkeypatch.setenv("DISABLED_TOOLS", "web_search, fetch_page")
    assert list(get_tools(["web_search", "news_search", "fetch_page", "wikipedia"])) == ["news_search", "wikipedia"]
    monkeypatch.delenv("DISABLED_TOOLS")
    assert "web_search" in get_tools(["web_search"])
