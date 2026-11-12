"""Regression tests for the report-v3 redesign, built on the saved run of 2026-11-06
(tests/fixtures/run_20261106.json). Deterministic: no model, no network.

Passing tests show that known failure modes are caught and that published text stays consistent with the computed
model. They do not show that the business conclusions are true.
"""
import json
import re
from pathlib import Path

import pytest

from startup_cofounder import claims as claimlib
from startup_cofounder import final_review, identity, issues as issuelib, report_model, research, retrieval, substance
from startup_cofounder.audit import ledger_from_sources
from startup_cofounder.config import Config
from startup_cofounder.evidence import EvidenceLedger
from startup_cofounder.llm import MockLLM
from startup_cofounder.memo import render_appendix, render_memo
from startup_cofounder.passages import PassageIndex
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.relevance import RelevanceBook, ResearchFrame
from startup_cofounder.tools import ALL_TOOLS, Tool, ToolResult

FIXTURE = Path(__file__).parent / "fixtures" / "run_20261106.json"
IDEA = ("A social app that helps adult indoor climbers in Pittsburgh find compatible climbing partners based on gym, "
        "availability, experience, and climbing discipline")


@pytest.fixture(scope="module")
def run():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def model(run):
    return report_model.build(run, regenerated=True)


@pytest.fixture(scope="module")
def memo(model):
    return render_memo(model)


@pytest.fixture(scope="module")
def appendix(model, run):
    return render_appendix(model, run)


def _memo_prose(memo):
    return re.sub(r"\]\([^)]*\)", "]", memo)


# ---------------------------------------------------------------- financial statements
def test_summary_cannot_claim_breakeven_the_model_does_not_show(run, model, memo):
    assert run["projection"]["breakeven_year"] is None
    found = final_review.financial_statements(run["synthesis"], run["projection"])
    assert {i.fields[0] for i in found} >= {"verdict_rationale", "executive_summary"}
    assert "break-even period within 5 years" not in memo
    assert "Operating break-even: not reached within 5 years." in memo


def test_clause_level_negation_does_not_hide_a_false_claim():
    syn = {"executive_summary": "The model shows break-even within 5 years, but payback is not within 5 years."}
    ids = [i.id for i in final_review.financial_statements(syn, {"breakeven_year": None, "payback_year": None})]
    assert ids == ["synthesizer:break-even-contradiction:executive_summary"]
    ok = {"executive_summary": "The scenario does not break even within 5 years. We aim to break even by year 3."}
    assert final_review.financial_statements(ok, {"breakeven_year": None, "payback_year": None}) == []


def test_desired_milestone_is_a_target_not_a_forecast(model, memo):
    t = model["economics"]["targets"]
    assert t and "Break-even within 5 years" in t[0]["target"] and "not within 5 years" in t[0]["scenario_shows"]
    assert "Founder target (not a forecast)" in memo


# ---------------------------------------------------------------- customer / competition
def test_competitor_price_is_not_willingness_to_pay(run, model, memo):
    out = run["agents"]["customer"]["output"]
    products = [c["name"] for c in run["agents"]["competitor"]["output"]["competitors"]]
    frame = ResearchFrame.from_plan(run["plan"], run["idea"])
    assert "customer:wtp-is-competitor-price" in [i.id for i in substance.customer(out, frame, products)]
    assert model["customer"]["wtp"] == ""
    assert "Free to use, with a Pro plan" not in memo.split("## 3.")[0]
    assert any(u["key"] == "wtp" and u["action_type"] == "founder" and "pricing test" in u["next_action"]
               for u in model["unknowns"])


def test_customer_section_about_a_product_is_withheld(model):
    assert model["customer"]["target"] == ""
    assert any("described users of Climbing Buddy" in c["correction"] for c in model["corrections"])


def test_same_need_competitor_is_direct_and_logbook_is_adjacent(model):
    rel = {r["name"]: r["relation"] for r in model["competition"]["rows"]}
    assert rel["Climbing Buddy"] == "direct" and rel["Gora Climbing Partner App"] == "direct"
    assert rel["Vertical-Life"] == "adjacent"  # "gym" is a place, not the partner-finding need


def test_generic_first_word_is_not_an_identity(run):
    ledger = ledger_from_sources(run["sources"])
    book = RelevanceBook(ResearchFrame.from_plan(run["plan"], run["idea"]))
    ids = identity.identity_sources("Climbing Place", [s.id for s in ledger.all()], ledger, book)
    assert all("climbingplace" in ledger.get(i).url.replace("the", "") or "climbing place" in ledger.get(i).text.lower()
               for i in ids)
    assert len(ids) < 20  # previously every page containing "climbing" matched (80+)


def test_missing_competitor_information_is_not_white_space(model, memo):
    assert model["competition"]["white_space"] == ""
    assert "Climbing Place is not detailed in sources" not in memo
    assert any("presented as white space" in c["correction"] for c in model["corrections"])
    assert not any("no specific" in w.lower() or "no information" in w.lower()
                   for r in model["competition"]["rows"] for w in r.get("weaknesses", []))


# ---------------------------------------------------------------- evidence rules
def test_question_alone_cannot_support_its_answer():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "FAQ", "url": "https://x.test/faq",
                               "snippet": "Is Climbing Buddy free to use? Does Climbing Buddy work for all skill levels?"}])
    frame = ResearchFrame.from_plan({"category": "climbing partner apps"}, IDEA)
    c = claimlib.build_claim("c", "competitor", "f", "Climbing Buddy is free to use", "fact", ["E1"], ledger,
                             RelevanceBook(frame), frame)
    assert c.status == "unsupported" and "question" in c.explanation
    saved = {"text": "Climbing Buddy is free to use with basic features", "status": "supported",
             "passage": "Is Climbing Buddy free to use?"}
    assert claimlib.rescreen(saved)["status"] == "unsupported"


def test_local_claim_needs_local_evidence(run, model, memo):
    frame = ResearchFrame.from_plan(run["plan"], run["idea"])
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "US climbing gyms", "url": "https://x.test/us",
                               "snippet": "Climbing gyms in the US grew 9% in 2025."}])
    c = claimlib.build_claim("c", "market", "f", "Climbing gyms in Pittsburgh grew 9% in 2025", "fact", ["E1"],
                             ledger, RelevanceBook(frame), frame)
    claimlib.apply_model_checks([c], {"checks": [{"id": "c", "status": "supported"}]})
    assert c.status == "partially_supported"  # a national source cannot fully support a Pittsburgh claim
    assert "growing demand for indoor climbing social apps in Pittsburgh" not in memo
    assert "Rapid growth in the climbing gym market in Pittsburgh" not in memo


def test_rejected_claims_do_not_survive_in_summaries(model, memo):
    rejected = [c for c in model["claims"] if c["id"] in model["rejected_claim_ids"]]
    assert rejected
    prose = _memo_prose(memo)
    for c in rejected:
        assert c["text"] not in prose
    assert "9.2%" not in prose  # unsupported Pittsburgh CAGR claim


# ---------------------------------------------------------------- technical, risk, finance
def test_competitor_names_fail_component_validation(run, model, memo):
    frame = ResearchFrame.from_plan(run["plan"], run["idea"])
    products = [c["name"] for c in run["agents"]["competitor"]["output"]["competitors"]]
    issues = substance.technical(run["agents"]["technical"]["output"], frame, products)
    assert "technical:components-are-products" in [i.id for i in issues]
    good = {"components": [{"name": "matching service", "responsibility": "rank compatible partners",
                            "approach": "build"}], "user_journey": ["a", "b", "c"],
            "effort": {"weeks_low": 6, "team": "1 dev", "scope": "MVP"}}
    assert not substance.technical(good, frame, products)
    assert model["mvp"]["components"] == [] and "Climbing Buddy" in model["mvp"]["rejected_components"]
    assert "MVP:** ~4 months" not in memo  # effort without a component basis is withheld


def test_marketing_text_is_not_a_risk_analysis(run, model):
    frame = ResearchFrame.from_plan(run["plan"], run["idea"])
    products = [c["name"] for c in run["agents"]["competitor"]["output"]["competitors"]]
    out = run["agents"]["safety"]["output"]
    assert "safety:no-risk-scenarios" in [i.id for i in substance.risk("safety", out, frame, products)]
    assert model["mvp"]["safety"] == [] and any(u["key"] == "safety" for u in model["unknowns"])
    assert substance.risk("safety", {"summary": "Matching guarantees safe partners", "scenarios": [
        {"scenario": "x", "control": "y", "limitation": "z"}]}, frame, products)[0].id == "safety:safety-guarantee"


def test_instruction_leakage_and_cost_overlap(run, model, memo, appendix):
    assert "Use the evidence to infer" not in memo and "Use the evidence to infer" in appendix  # only as a correction
    assert model["economics"]["overlap"] == ["Initial Team Salaries"]
    assert [i.id for i in substance.financial(run["agents"]["financial"]["output"])] == \
        ["financial:rationale-is-instruction", "financial:cost-overlap"]


# ---------------------------------------------------------------- unknowns and plan
def test_unknown_market_inputs_produce_a_plan(model, memo):
    rows = model["market"]["formula_rows"]
    assert [r["input"] for r in rows if r["value"] == "missing"] == model["market"]["missing"]
    assert all(r["how"] for r in rows)
    mk = next(u for u in model["unknowns"] if u["key"] == "market")
    assert mk["next_action"] and "web research" in mk["action_type"]
    assert model["market"]["density"] and "| Input | Meaning | Value | How to get it |" in memo


def test_every_open_question_has_why_and_next_action(model):
    for u in model["unknowns"]:
        assert u["what"] and u["why"] and u["next_action"] and u["action_type"]


def test_founder_tests_are_not_sent_to_a_web_researcher():
    tr = issuelib.Tracker()
    iss = tr.add_critic("customer", "segments are vague", "Conduct 10 customer interviews in Pittsburgh", "high")
    assert iss.action == "founder"
    assert "customer" not in tr.select() and iss.status == "founder_task"
    web = tr.add_critic("market", "no local data", "Search for and cite local gym membership counts", "high")
    assert web.action == "research" and "market" in tr.select()


def test_validation_plan_labels_thresholds_and_owners(model, memo):
    assert all(v["threshold"].startswith("proposed") or "inputs sourced" in v["threshold"]
               for v in model["validation_plan"])
    assert {"founder", "software"} <= {v["owner"] for v in model["validation_plan"]}
    assert "Thresholds are proposed decision rules, not industry benchmarks." in memo


# ---------------------------------------------------------------- tool actions
def test_impossible_or_duplicate_actions_do_not_consume_repeated_retries(monkeypatch):
    calls = []
    for name in ALL_TOOLS:
        monkeypatch.setitem(ALL_TOOLS, name, Tool(name, "s", {"query": "string"}, lambda query: calls.append(
            query) or ToolResult(sources=[{"title": "Climbing partner app", "url": "https://c.test/%d" % len(calls),
                                           "snippet": "climbing partners"}])))
    monkeypatch.setattr(retrieval, "page_text", lambda url, limit=30000: ("t", "climbing partners " * 50))
    ledger, index = EvidenceLedger(), PassageIndex()
    frame = ResearchFrame.from_plan({"category": "indoor climbing apps"}, IDEA)
    proposals = []

    def planner(status):
        proposals.append(status)
        return {"action": "fetch", "source_id": "E1"}

    sr = research.SectionResearcher(ledger, index, RelevanceBook(frame), research.RunLimits(10, 0),
                                    research.Limits(searches=2, fetches=3, planner_calls=5), lambda *a: None, lambda: 999)
    res = sr.run("customer", "q", [retrieval.Query("customer", "web_search", "climbing partners")], planner=planner)
    assert len(proposals) <= 2  # stops instead of asking again for an action that cannot run
    assert "do not request a fetch" in proposals[0]  # the agent is told the page-read budget is gone
    assert res.actions[0]["rejected_because"].startswith("page-read budget exhausted")
    assert not any(a["accepted"] for a in res.actions)
    assert len(calls) <= 2  # the fallback search ran once; nothing repeated


def test_failed_fetch_is_not_accepted_twice():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "a", "url": "https://c.test/a", "snippet": ""}])
    kw = dict(tried=[], allowed_tools=["web_search"], ledger=ledger, visible_ids=["E1"])
    assert research.validate_action({"action": "fetch", "source_id": "E1"}, fetched=["https://c.test/a"], **kw)[1] == \
        "page already read"
    assert "budget exhausted" in research.validate_action({"action": "fetch", "source_id": "E1"}, fetched=[],
                                                          can_fetch=False, **kw)[1]


def test_early_sections_cannot_spend_the_reserved_budget():
    lim = research.RunLimits(searches=10, fetches=4)
    assert lim.take("fetch", reserve=3) and not lim.take("fetch", reserve=3)  # 1 usable, 3 kept for later
    assert lim.take("fetch", reserve=0)  # a review retry may use the reserve


# ---------------------------------------------------------------- presentation
def test_memo_citations_resolve_and_audit_material_stays_in_appendix(run, memo, appendix):
    urls = {s["url"].split("#p")[0] for s in run["sources"]}
    links = re.findall(r"\]\((https?://[^)]+)\)", memo)
    assert links and all(l in urls for l in links)
    for line in memo.splitlines():
        assert len(re.findall(r"\]\(https?://", line)) <= 3 or line.startswith("|")
    for audit_text in ("lexical match", "model check", "Claims and support", "[E1]", "re-screened"):
        assert audit_text not in memo
    assert "## C. Claims and support" in appendix and "## H. Sources" in appendix


def test_memo_is_readable(memo):
    words = len(re.sub(r"\]\([^)]*\)", "]", memo).split())
    assert 900 <= words <= 1900, words
    for line in memo.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            assert line.count("|") - 1 <= 5  # at most five columns
    for raw in ("None", "null", "nan", "n/a |"):
        assert raw not in memo
    assert memo.startswith("# ") and len(memo.splitlines()[0]) < 70  # short title; full idea below it


def test_incomplete_assessment_is_readable_and_honest(tmp_path, monkeypatch):
    from startup_cofounder.budget import RunBudget
    now = [0]
    budget = RunBudget(60, clock=lambda: now[0])
    monkeypatch.setattr("startup_cofounder.pipeline.RunBudget", lambda *a: budget)

    class SlowPlan(MockLLM):
        def chat(self, messages, **kw):
            out = super().chat(messages, **kw)
            if messages[0]["content"].startswith("ROLE: coordinator"):
                now[0] = 3000
            return out

    cfg = Config(agent_design="sections", backend="mock", offline=True, run_minutes=60, max_workers=1, cache_dir=tmp_path / "c",
                 output_dir=tmp_path / "o")
    result = Pipeline(cfg, llm=SlowPlan()).run(IDEA)
    rep = result.to_dict()["report"]
    md = render_memo(rep)
    assert "INCOMPLETE ASSESSMENT" in md and "No decision: research incomplete" in md
    assert rep["status"]["withheld"] and "None" not in md and "null" not in md
    for h in ("## 2. Customer and problem", "## 6. Business model and economics", "## 7. Prioritized validation plan"):
        assert h in md


def test_live_run_json_carries_versioned_report(tmp_path):
    result = Pipeline(Config.from_env(backend="mock", offline=True, cache_dir=tmp_path)).run(IDEA)
    d = result.to_dict()
    assert d["report_schema"] == "report-v3" and d["report"]["schema"] == "report-v3"
    json.dumps(d, default=str)
    assert render_memo(d["report"]).count("## ") >= 7


def test_unsupported_statements_are_not_relabelled_as_assumptions(model):
    by_field = {c.get("field"): c for c in model["claims"]}
    assert by_field["segments[0].willingness_to_pay"]["status"] == "unsupported"
    assert by_field["segments[0].size_estimate"]["status"] == "unsupported"
    ledger = EvidenceLedger()
    c = claimlib.value_claim("x", "customer", "willingness_to_pay", "Free to use, with a Pro plan", [], ledger, None, None)
    assert c.status == "unsupported"
    c = claimlib.value_claim("y", "customer", "willingness_to_pay", "unknown; probably low", [], ledger, None, None)
    assert c.status == "explicit_assumption" and c.claim_type == "assumption"


def test_other_saved_run_renders_without_special_cases():
    """The 2026-11-05 run (different failures) goes through the same code path and stays honest."""
    d = json.loads((Path(__file__).parent / "fixtures" / "failed_run_20261105.json").read_text())
    m = report_model.build(d, regenerated=True)
    md = render_memo(m)
    names = [r["name"] for r in m["competition"]["rows"]]
    assert "SENDO" not in names and "KAYA" not in names and "Lattice" not in names
    assert "160%" not in md and "10,000 paying customers" not in md
    assert m["status"]["evidence_adequacy"] == "insufficient"


# ---------------------------------------------------------------- v3.1 validation layers
from startup_cofounder import validators  # noqa: E402


def test_vendor_only_evidence_is_flagged_and_measured(run, model, memo):
    vs = model["validation"]["sources"]
    assert vs["vendor_share"] > 0.5 and vs["by_type"]["official_vendor"] > 0
    assert any(u["key"] == "independent" for u in model["unknowns"])
    assert "Independent of vendors" in memo
    c = next(c for c in model["claims"] if c["id"] == "customer-C4")  # "hundreds of climbers" from climbingbuddy.org
    assert c["claim_type"] == "source_reported" and any("vendor" in f for f in c["validation"]["flags"])


def test_low_credibility_statistic_is_capped_and_dated_statistics_flagged():
    srcs = {"E1": {"id": "E1", "url": "https://worldmetrics.org/climbing-statistics/", "title": "Climbing Statistics 2026",
                   "snippet": "There are 10,000 gyms."},
            "E2": {"id": "E2", "url": "https://example-blog.com/post", "title": "Climbing in 2012",
                   "snippet": "In 2012 there were 300 gyms in the US."}}
    a = validators.assess_claim({"text": "There are 10,000 climbing gyms", "status": "supported", "source_ids": ["E1"],
                                 "section": "market"}, srcs, {})
    assert a["status_after"] == "partially_supported" and any("low-credibility" in f for f in a["flags"])
    b = validators.assess_claim({"text": "The US had 300 gyms", "status": "supported", "source_ids": ["E2"],
                                 "section": "market"}, srcs, {}, today_year=2026)
    assert any(f.startswith("dated") for f in b["flags"]) and b["status_after"] == "partially_supported"
    c = validators.assess_claim({"text": "x", "status": "unsupported", "source_ids": ["E1"]}, srcs, {})
    assert c["status_after"] == "unsupported"  # never upgrades


def test_plausibility_and_consistency_on_both_saved_runs(model):
    nov5 = report_model.build(json.loads((Path(__file__).parent / "fixtures" / "failed_run_20261105.json").read_text()),
                              True)
    rules5 = {p["rule"] for p in nov5["validation"]["plausibility"]}
    assert "consumer price above $30/month" in rules5 and "consumer churn below 30%/year" in rules5
    assert all(p["basis"].startswith("heuristic") for p in nov5["validation"]["plausibility"])
    checks = {c["check"]: c["result"] for c in model["validation"]["consistency"]}
    assert checks["year-1 paying customers vs local participants"] == "not checkable"
    assert checks["modelled price vs direct alternatives"] == "tension"
    rows = [{"input": "Active local participants", "value": "2000 people"}]
    proj = {"table": [{"customers_end": 900, "payroll": 0, "revenue": 1}], "assumptions": {"arpu_monthly": 5}}
    assert validators.consistency(proj, rows, [], "")[0]["result"] == "inconsistent"


def test_publication_gate_traces_every_number(model, memo):
    assert model["validation"]["publication_gate"]["passed"]
    bad = memo.replace("Operating break-even: not reached within 5 years.", "Revenue reaches $1.2M in year 5.")
    assert "$1.2M" in validators.publication_gate(bad, model)["untraced"]
    rejected_number = memo + "\nThe UK climbing gym market grows 9.2% a year."
    assert "9.2%" in validators.publication_gate(rejected_number, model)["untraced"]  # only in a rejected claim


def test_failed_gate_is_visible_in_the_memo(model):
    m = dict(model)
    m["decision"] = dict(model["decision"], reasons=["Revenue will reach $7.7M by year 2."])
    md = render_memo(m)
    assert "Publication check failed" in md and "$7.7M" in md.split("## 1.")[0]


def test_control_probe_blocks_a_rubber_stamping_checker():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "a", "url": "https://c.test/a", "snippet": "Crimpd climbing app is available on iOS."}])
    frame = ResearchFrame.from_plan({"category": "climbing apps"}, IDEA)
    c = claimlib.build_claim("x-C1", "competitor", "f", "Crimpd climbing app is available on iOS", "fact", ["E1"],
                             ledger, RelevanceBook(frame), frame)
    batch, ctrl = claimlib.with_control([c], "x")
    assert ctrl and len(batch) == 2 and batch[1].passage == claimlib.CONTROL_PASSAGE
    stamp = {"checks": [{"id": i.id, "status": "supported"} for i in batch]}
    assert claimlib.control_result(stamp, ctrl) == "failed"
    claimlib.apply_model_checks(batch, stamp, "m", ctrl)
    assert c.status == "partially_supported" and c.model_check.get("ignored")
    honest = {"checks": [{"id": "x-C1", "status": "supported"}, {"id": ctrl, "status": "unsupported"}]}
    c2 = claimlib.build_claim("x-C1", "competitor", "f", "Crimpd climbing app is available on iOS", "fact", ["E1"],
                              ledger, RelevanceBook(frame), frame)
    batch2, ctrl2 = claimlib.with_control([c2], "x")
    claimlib.apply_model_checks(batch2, honest, "m", ctrl2)
    assert claimlib.control_result(honest, ctrl2) == "passed" and c2.status == "supported"


def test_pipeline_records_control_probe(tmp_path):
    result = Pipeline(Config.from_env(backend="mock", offline=False, cache_dir=tmp_path, critic_rounds=0)).run(IDEA)
    d = result.to_dict()
    probes = [t for t in d["trace"] if t.get("type") == "claim_check"]
    assert all("control" in t for t in probes)
    assert "not measured" in d["report"]["validation"]["verifier"]["status"] or "control" in \
        d["report"]["validation"]["verifier"]["status"]


def test_validator_benchmark_floors():
    """Regression floors for measured layer accuracy on the hand-labelled set (eval/gold/validator_gold.json)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vb", Path(__file__).parent.parent / "eval" / "validator_benchmark.py")
    vb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vb)
    res = vb.run()
    assert res["relevance gate"]["accuracy"] >= 0.95 and res["relevance gate"]["false_accept"] == 0
    assert res["source type"]["accuracy"] >= 0.9
    assert res["financial statements"]["accuracy"] == 1.0
    assert res["competitor identity"]["false_accept"] == 0  # never counts the wrong company
    pub = res["claim support (published: saved + v3.1 re-screen)"]
    assert pub["false_accept"] <= res["claim support (as saved: code + 3B check)"]["false_accept"]
