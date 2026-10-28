from startup_cofounder import quality
from startup_cofounder.agents import AgentResult
from startup_cofounder.evidence import EvidenceLedger, Finding


def _result(role, output=None, findings=None, error=None, trace=True):
    return AgentResult(role, output or {}, findings or [], [{"tool": "x"}] if trace else [], error)


def test_name_seen_handles_suffixes_and_first_word():
    corpus = "zoom video communications is a leader. airbnb inc raised funds"
    assert quality.name_seen("Zoom Video Communications, Inc.", corpus)
    assert quality.name_seen("Zoom", corpus)
    assert quality.name_seen("Airbnb", corpus)
    assert not quality.name_seen("Skype", corpus)
    assert not quality.name_seen("Competitor A (mock)", corpus)


def test_verify_competitors_ranks_confirmed_first():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "Alternatives to Notion: Coda and Obsidian", "url": "http://x", "snippet": "Coda pricing"}])
    res = _result("competitor", {"competitors": [{"name": "MadeUp Corp"}, {"name": "Coda"}, {"name": "Obsidian"}]})
    quality.verify_competitors(res, ledger)
    names = [(c["name"], c["verified"]) for c in res.output["competitors"]]
    assert names == [("Coda", True), ("Obsidian", True), ("MadeUp Corp", False)]


def test_rule_gaps_find_missing_pieces():
    ledger = EvidenceLedger()
    ledger.add("web_search", [{"title": "Some page", "url": "http://x", "snippet": "text"}])
    results = {
        "customer": _result("customer", {"segments": []}, [Finding("c", "estimate")]),
        "competitor": _result("competitor", {"competitors": [{"name": "A"}, {"name": "B"}]}),
        "market": _result("market", {"tam_sam_som": {"tam_usd": 5e9, "sam_usd": 0}}),
        "technical": _result("technical", {"summary": "ok"}),
        "regulatory": _result("regulatory", error="boom"),
    }
    gaps = {g.agent: g.issue for g in quality.rule_gaps(results, ledger)}
    assert "no finding is backed" in gaps["customer"] or "segments" in gaps["customer"]
    assert "only 2 competitors" in gaps["competitor"]
    assert "incomplete" in gaps["market"]
    assert "feasibility" in gaps["technical"]
    assert "no usable output" in gaps["regulatory"]


def test_merge_and_parse_critic():
    rule = [quality.Gap("competitor", "r", "f")]
    critic = quality.parse_critic({"gaps": [
        {"agent": "Competitor", "issue": "dup", "followup_task": "x"},
        {"agent": "market", "issue": "m", "followup_task": "y"},
        {"agent": "ghost", "issue": "nope"}, {"issue": "no agent"}]})
    merged = quality.merge_gaps(rule, critic, {"competitor", "market"})
    assert [(g.agent, g.origin) for g in merged] == [("competitor", "rule"), ("market", "critic")]


def test_grade_and_verdict_guardrail():
    good = {"competitor": _result("competitor", {"competitors": [{"verified": True}] * 3},
                                  [Finding("f", "fact", ["E1"])] * 4)}
    assert quality.evidence_grade(good, 20)[0] == "A"
    bad = {"customer": _result("customer", {}, [Finding("f", "estimate")] * 4)}
    assert quality.evidence_grade(bad, 0)[0] == "D"

    ue_good = {"ltv_cac": 5.0}
    assert quality.cap_verdict("go", "A", ue_good, 3) == ("go", "")
    verdict, note = quality.cap_verdict("go", "D", {"ltv_cac": 1.2}, None)
    assert verdict == "validate_first" and "grade is D" in note and "LTV/CAC" in note and "break-even" in note
    assert quality.cap_verdict("pivot", "D", {}, None) == ("pivot", "")
    assert quality.cap_verdict("???", "A", ue_good, 2)[0] == "validate_first"


def test_real_world_mostly_estimates_with_one_competitor_is_not_graded_b():
    # Mirrors the first live eval: 73 sources, 1 confirmed competitor, only 3 of 18 findings were facts.
    findings = [Finding("f", "fact", ["E1"])] * 3 + [Finding("g", "estimate")] * 15
    res = {"competitor": _result("competitor", {"competitors": [{"verified": True}]}, findings)}
    grade, reasons = quality.evidence_grade(res, 73)
    assert grade == "C" and any("1 of 3" in r for r in reasons)
