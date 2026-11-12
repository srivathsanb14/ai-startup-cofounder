"""Regression tests for the question-driven agents (report-v4).

Covers: preservation of the founder's idea, competitor identity, customer segmentation, geographic applicability,
unsupported pricing, financial consistency, evidence independence, cross-section contradictions, stage-appropriate
experiments, a second startup concept (B2B scheduling, stub web + scripted small model), and regeneration of the
saved Nov 5 / Nov 6 runs without network or model calls.
"""
import ast
import json
import re
from pathlib import Path

import pytest

import stubweb
from startup_cofounder import economics2, memo_v4, report_v4, retrieval, synthesis
from startup_cofounder.analyst import Analyst, packet
from startup_cofounder.brief import build_brief
from startup_cofounder.config import Config
from startup_cofounder.evidence import EvidenceLedger
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.questions import catalog
from startup_cofounder.relevance import RelevanceBook, ResearchFrame

FIX = Path(__file__).parent / "fixtures"
CLIMB = ("A social app that helps adult indoor climbers in Pittsburgh find compatible climbing partners based on gym, "
         "availability, experience, and climbing discipline")
SECTIONS = ["## 1. Recommendation", "## 2. Customer problem", "## 3. Competitive landscape",
            "## 4. Market opportunity", "## 5. Product feasibility", "## 6. Most consequential risks",
            "## 7. Validation experiments"]


def _load(name):
    return json.loads((FIX / name).read_text())


@pytest.fixture(scope="module")
def nov6():
    d = _load("run_20261106.json")
    m = report_v4.build(d, regenerated=True)
    return d, m, memo_v4.render_memo(m)


@pytest.fixture(scope="module")
def nov5():
    d = _load("failed_run_20261105.json")
    m = report_v4.build(d, regenerated=True)
    return d, m, memo_v4.render_memo(m)


@pytest.fixture(scope="module")
def coffee(tmp_path_factory):
    """Full question-design pipeline on a different concept: stub web, scripted small model, no network."""
    calls = []
    with pytest.MonkeyPatch.context() as mp:
        stubweb.install(mp, calls)
        tmp = tmp_path_factory.mktemp("coffee")
        cfg = Config(agent_design="questions", backend="mock", max_workers=1, cache_dir=tmp / "c",
                     output_dir=tmp / "o", resume=False)
        a = Pipeline(cfg, llm=stubweb.ScriptedSmallModel()).run(stubweb.IDEA, fresh=True)
        d = a.to_dict()
    m = d["report"]
    return d, m, memo_v4.render_memo(m), calls


def _prose(memo):
    return memo.split("\n---\n")[0]


# ------------------------------------------------------------------ 1. founder's idea is preserved
def test_planner_drift_to_stranger_matching_is_rejected():
    raw = {"product": "stranger-matching app for climbers", "target_customer": "adult indoor climbers",
           "problem": "meeting strangers", "customer_job": "match with strangers to climb", "stage": "launched",
           "business_model": "AI dating subscription"}
    b = build_brief("A social app that helps my climbing friends in Pittsburgh plan sessions together at local gyms",
                    raw, {})
    assert "stranger" not in (b.product + b.customer_job).lower()
    assert any("stranger" in f for f in b.fidelity_flags)
    assert b.business_model == "" and any("business model" in f for f in b.fidelity_flags)
    assert b.stage == "idea"  # the founder did not say anything exists


def test_requests_to_the_analyst_are_not_part_of_the_idea():
    d = _load("failed_run_20261105.json")
    b = build_brief(d["idea"], {}, d["plan"])
    assert b.stage == "idea"  # "Explore ... an MVP" is a request, not a built prototype
    assert b.target_customer == "adult indoor climbers" and b.geography == "Pittsburgh"
    assert "Explore" not in b.product


def test_drifting_category_is_replaced_and_flagged():
    b = build_brief(CLIMB, {}, {"category": "climbing dating marketplace"})
    assert "dating" not in b.category and any("categorised" in f for f in b.fidelity_flags)


def test_memo_quotes_the_founder_verbatim_and_shows_interpretation_flags(coffee):
    _, m, memo, _ = coffee
    assert stubweb.IDEA in memo
    assert "marketplace" in memo and "Interpretation check" in memo  # the drift is disclosed, not adopted
    assert "marketplace" not in m["brief"]["product"].lower()
    assert m["brief"]["exclusions"] == ["payroll system"]


# ------------------------------------------------------------------ 2. competitor identity and relevance
def test_competitor_identity_from_saved_run(nov6):
    _, m, memo = nov6
    rel = {r["name"]: r["relation"] for r in m["competition"]["rows"]}
    assert rel["Gora Climbing Partner App"] == "direct"
    assert rel["Climbing Place"] != "direct"  # a gym in North Carolina is not a competitor
    sec3 = memo.split("## 3.")[1].split("## 4.")[0]
    assert "Climbing Place" not in sec3.split("Adjacent")[0]


def test_off_topic_page_never_becomes_a_finding(coffee):
    _, m, _, _ = coffee
    texts = " ".join(f["text"] for q in m["questions"].values() for f in q["findings"])
    assert "roast" not in texts.lower()


# ------------------------------------------------------------------ 3. customer segmentation
def _analyst(idea, plan, sources):
    ledger = EvidenceLedger()
    ledger.add("web_search", sources)
    frame = ResearchFrame.from_plan(plan, idea)
    b = build_brief(idea, {}, plan)
    return Analyst(ledger, None, RelevanceBook(frame), b, None, lambda *a, **k: None), b, ledger


def test_product_description_is_not_customer_evidence():
    an, b, ledger = _analyst(CLIMB, {"category": "indoor climbing social apps"}, [
        {"title": "Gora", "url": "https://goraclimb.com/", "snippet": "Gora helps you find climbing partners at your "
                                                                      "gym and plan sessions."}])
    q = next(q for q in catalog(b, ["Gora"]) if q.id == "Q-C1")
    res = {"findings": [{"statement": "Gora helps you find climbing partners at your gym and plan sessions.",
                         "type": "fact", "stance": "supports", "source_ids": ["E1"]}], "status": "answered",
           "packet": ["E1"], "mode": "model"}
    out = an.validate(q, res, {"goraclimb.com": "Gora"}, ["Gora"])
    assert out["findings"][0]["role"] in ("misplaced", "vendor_claim")
    assert out["status"] == "insufficient"


def test_contradicting_customer_evidence_is_kept_and_counted(coffee):
    _, m, memo, _ = coffee
    lv = m["synthesis"]["hypotheses"]
    assert lv["H-D1"]["contradicting"] >= 1 and lv["H-D1"]["level"] == "mixed"
    assert "went back to paper" in memo


# ------------------------------------------------------------------ 4. geographic applicability
def test_national_statistic_is_not_a_local_count(coffee):
    _, m, _, _ = coffee
    mc = m["economics"]["market_check"]
    assert mc and mc["count"]["value"] == 320 and "Austin" in mc["count"]["text"]
    q = m["questions"]["Q-M1"]
    for f in q["findings"]:
        if "38,000" in f["text"]:
            assert f["role"] != "finding"


def test_out_of_area_market_findings_are_context_only(nov5):
    _, m, _ = nov5
    for f in m["questions"]["Q-M1"]["findings"]:
        if "UK" in f["text"] or "worldwide" in f["text"]:
            assert f["role"] == "broader_context"
    assert m["economics"]["market_check"] is None  # nothing local was found, so no customer base is assumed


# ------------------------------------------------------------------ 5. unsupported pricing
def test_competitor_price_is_labelled_not_validated(coffee):
    _, m, memo, _ = coffee
    price = m["economics"]["assumptions"][0]
    assert price["basis"] == "competitor_price" and "NOT evidence" in price["rationale"]
    assert any(c["id"] == "X5" for c in m["synthesis"]["checks"])
    assert not re.search(r"validated pric|customers will pay", _prose(memo), re.I)


def test_vendor_price_is_not_willingness_to_pay():
    an, b, ledger = _analyst(stubweb.IDEA, {"category": "coffee shop staff scheduling software"}, [
        {"title": "ShiftBrew pricing", "url": "https://shiftbrew.test/pricing",
         "snippet": "ShiftBrew scheduling costs $39 per month per location for coffee shops."}])
    q = next(q for q in catalog(b, ["ShiftBrew"]) if q.id == "Q-W1")
    res = {"findings": [{"statement": "ShiftBrew scheduling costs $39 per month per location for coffee shops.",
                         "type": "fact", "stance": "supports", "source_ids": ["E1"]}], "packet": ["E1"],
           "status": "answered", "mode": "model"}
    out = an.validate(q, res, {"shiftbrew.test": "ShiftBrew"}, ["ShiftBrew"])
    assert out["findings"][0]["role"] in ("competitor_price", "vendor_claim") and out["status"] == "insufficient"


def test_placeholder_price_without_evidence(nov6):
    _, m, memo = nov6
    p = m["economics"]["assumptions"][0]
    assert p["basis"] == "rule_of_thumb" and p["uncertainty"] == "high"
    assert "placeholder" in memo


# ------------------------------------------------------------------ 6. financial consistency
def test_breakeven_arithmetic_is_consistent():
    b = build_brief(CLIMB, {}, {})
    e = economics2.build(b)
    unit = e["unit"]["contribution_per_paying_month"]
    for s in e["scenarios"].values():
        assert s["breakeven_paying"] * unit >= s["fixed_monthly"] > (s["breakeven_paying"] - 1) * unit
        assert s["funding_to_milestone"] >= s["mvp_cash"]
    assert e["projection"] is None  # inputs are not evidence-based and no illustration was asked for
    assert economics2.build(b, illustrative=True)["projection"]["illustrative"] is True


def test_no_automatic_four_person_team():
    b = build_brief(CLIMB, {}, {})
    e = economics2.build(b)
    assert e["base_scenario"] == "solo_bootstrapped"
    assert e["scenarios"]["solo_bootstrapped"]["fixed_monthly"] < 1000
    assert "two full-time" in e["scenarios"]["venture_backed"]["team"]


def test_every_financial_assumption_has_basis_and_rationale():
    e = economics2.build(build_brief(stubweb.IDEA, {}, {}))
    for a in e["assumptions"]:
        assert a["basis"] and a["rationale"] and a["uncertainty"] in ("low", "medium", "high")
        assert a["low"] <= a["value"] <= a["high"]


def test_prices_are_normalised_to_monthly():
    assert economics2.prices_in("$59.99/year or $7.99 per month") == [5.0, 7.99]
    assert economics2.prices_in("Day pass $22 per visit") == []  # a venue's entry fee is not the app's price


def test_memo_numbers_are_traceable(nov6, nov5, coffee):
    for _, m, _ in (nov6, nov5):
        assert m["publication"]["memo_gate"]["passed"], m["publication"]["memo_gate"]
    assert coffee[1]["publication"]["memo_gate"]["passed"]


# ------------------------------------------------------------------ 7. evidence independence
def test_packet_takes_at_most_two_items_per_site():
    b = build_brief(stubweb.IDEA, {}, {"category": "coffee shop staff scheduling software"})
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "Coffee shop staff scheduling %d" % i, "url": "https://same.test/p%d" % i,
                               "snippet": "Coffee shop owners discuss staff scheduling and shift rosters, part %d." % i}
                              for i in range(5)] +
               [{"title": "Coffee shop scheduling thread", "url": "https://other.test/x",
                 "snippet": "Coffee shop owners discuss staff scheduling and weekly rosters in this thread."}])
    book = RelevanceBook(ResearchFrame.from_plan({"category": "coffee shop staff scheduling software"}, stubweb.IDEA))
    q = next(q for q in catalog(b) if q.id == "Q-C2")
    pk = packet(q, [s.id for s in ledger.all()], ledger, book, {})
    hosts = [s.url.split("/")[2] for s in pk]
    assert hosts.count("same.test") <= 2 and "other.test" in hosts


def test_same_passage_counts_once_per_hypothesis(coffee):
    _, m, _, _ = coffee
    h = m["synthesis"]["hypotheses"]["H-D1"]
    texts = [f["text"] for q in ("Q-C1", "Q-C2") for f in m["questions"][q]["findings"] if f["role"] == "finding"]
    assert h["supporting"] + h["contradicting"] + h["neutral"] <= len(set(texts))


def test_vendor_only_support_does_not_answer_a_customer_question(nov6):
    _, m, _ = nov6
    for qid in ("Q-C1", "Q-C2", "Q-W1", "Q-D1", "Q-M1"):
        for f in m["questions"][qid]["findings"]:
            if f["role"] == "finding":
                assert set(f["validation"]["source_types"]) - {"official_vendor"}


# ------------------------------------------------------------------ 8. cross-section contradictions
def test_free_competitor_and_network_cold_start_are_addressed(nov6):
    _, m, memo = nov6
    ids = {c["id"] for c in m["synthesis"]["checks"]}
    assert {"X2", "X4", "X6"} <= ids  # free alternatives, cold start, unknown local market
    assert any("Free alternative" in c for c in m["economics"]["checks"])
    assert "Cold start" in memo and "No multi-year projection" in memo


def test_consistency_check_catches_contradicting_prose(nov6):
    _, m, _ = nov6
    bad = "Pricing is validated pricing and the large market means break-even in year 2."
    found = synthesis.consistency(bad, m["synthesis"], dict(m["economics"], projection={"breakeven_month": None}))
    assert len(found) >= 2
    assert synthesis.consistency("We should test pricing first.", m["synthesis"], m["economics"]) == []


def test_verdict_is_conditional(nov6, coffee):
    for m in (nov6[1], coffee[1]):
        v = m["synthesis"]["verdict"]
        assert v["verdict"] in synthesis.VERDICTS
        assert v["proceed_if"] and v["modify_if"] and v["stop_if"]
    assert nov6[1]["synthesis"]["verdict"]["verdict"] == "validate_first"


def test_three_to_five_key_findings(nov6, nov5, coffee):
    for m in (nov6[1], nov5[1], coffee[1]):
        assert 3 <= len(m["synthesis"]["key_findings"]) <= 5


# ------------------------------------------------------------------ 9. stage-appropriate experiments
FIELDS = ("hypothesis", "segment", "method", "metric", "threshold", "cost", "duration", "success", "failure", "next")


def test_pre_launch_social_app_tests_participation_and_return(nov6):
    exps = nov6[1]["synthesis"]["experiments"]
    assert 2 <= len(exps) <= 3
    text = json.dumps(exps).lower()
    assert "churn" not in text and "ltv" not in text and "cac" not in text
    assert "return" in text or "come back" in text
    assert exps[0]["hypothesis_id"] == "H-D1"
    for e in exps:
        assert all(e.get(k) for k in FIELDS)


def test_b2b_concept_gets_b2b_experiments(coffee):
    exps = coffee[1]["synthesis"]["experiments"]
    text = json.dumps(exps).lower()
    assert "paid pilot" in text or "letter of intent" in text
    assert "group chat" not in text  # consumer pilot template not used for a business customer
    for e in exps:
        assert all(e.get(k) for k in FIELDS)


# ------------------------------------------------------------------ 10. the agents themselves (second concept)
def test_questions_are_targeted_and_include_disconfirming_searches(coffee):
    _, m, _, calls = coffee
    queries = [q for _, q in calls]
    assert any("reddit" in q for q in queries)
    assert any("should be free" in q or "works fine without" in q or "easy" in q for q in queries)
    assert any("ShiftBrew" in q or "RosterPal" in q for q in queries)  # competitor-specific reviews and pricing
    assert len(calls) <= Config().run_searches


def test_repairs_are_targeted_and_measured(coffee):
    d, m, _, _ = coffee
    for r in m["repairs"]:
        assert r["question"] in m["questions"] and r["kept"] in ("repair", "original")
        assert r["improved"] == (r["kept"] == "repair")
    assert d["run_info"]["workflow"] == "questions-v1"


def test_report_structure_and_length(nov6, coffee):
    for memo in (nov6[2], coffee[2]):
        pos = [memo.find(s) for s in SECTIONS]
        assert all(p >= 0 for p in pos) and pos == sorted(pos)
        words = len(_prose(memo).split())
        assert 700 <= words <= 2200, words  # roughly 2-4 pages


def test_extractive_regeneration_is_labelled_and_offline(monkeypatch):
    def no_web(*a, **k):
        raise AssertionError("regeneration must not search")
    monkeypatch.setattr(retrieval, "run_queries", no_web)
    d = _load("run_20261106.json")
    m = report_v4.build(d, regenerated=True)
    assert m["evidence_mode"] == "saved_extractive"
    assert "Evidence mode: regenerated from saved sources" in memo_v4.render_memo(m)
    for q in m["questions"].values():
        assert q["status"] in ("evidence_located", "insufficient")  # never "answered" without a model


def test_appendix_has_assumptions_questions_and_economics(nov6):
    _, m, _ = nov6
    app = memo_v4.render_appendix(m)
    for h in ("## A. Idea brief", "## B. Assumptions map", "## C. Research questions", "## D. Economics",
              "## E. Cross-section checks"):
        assert h in app


def test_new_modules_parse_as_python39():
    root = Path(__file__).resolve().parent.parent / "startup_cofounder"
    for name in ("brief", "questions", "analyst", "economics2", "synthesis", "report_v4", "memo_v4", "render",
                 "pipeline", "regenerate"):
        ast.parse((root / (name + ".py")).read_text(), feature_version=(3, 9))


def test_generic_first_word_does_not_make_blogs_vendor_sites():
    from startup_cofounder import validators
    v = validators.vendor_domains([{"name": "Climbing Buddy"}, {"name": "Lattice Training"}])
    assert validators.classify_source({"url": "https://rockclimbingrealms.com/how-to"}, v) != "official_vendor"
    assert validators.classify_source({"url": "https://climbingbuddy.org/"}, v) == "official_vendor"
    assert validators.classify_source({"url": "https://latticetraining.com/"}, v) == "official_vendor"


def test_product_site_is_recognised_from_its_distinctive_name():
    an, b, ledger = _analyst(CLIMB, {"category": "indoor climbing social apps"}, [
        {"title": "Best indoor climbing apps", "url": "https://goraclimb.com/best-indoor-climbing-apps",
         "snippet": "Gora App Find Climbing Partners. Connect with climbers at your gym and plan sessions together."}])
    q = next(q for q in catalog(b) if q.id == "Q-C2")
    res = {"findings": [{"statement": "Gora App Find Climbing Partners.", "type": "fact", "stance": "neutral",
                         "source_ids": ["E1"]}], "packet": ["E1"], "status": "partial", "mode": "model"}
    out = an.validate(q, res, {}, ["Gora Climbing Partner App"])
    assert out["findings"][0]["role"] != "finding" and out["status"] == "insufficient"
