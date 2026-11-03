import json

import pytest

from startup_cofounder import competitors, retrieval, schemas
from startup_cofounder.checkpoint import Checkpoint, run_key
from startup_cofounder.config import Config
from startup_cofounder.evidence import EvidenceLedger
from startup_cofounder.extract import Extractor
from startup_cofounder.llm import MockLLM, OpenAICompatLLM
from startup_cofounder.passages import PassageIndex, bm25, chunk, rank
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.report import render_markdown
from startup_cofounder.tools import ALL_TOOLS, Tool, ToolResult

IDEA = "A video calling app for remote teams"


def _config(tmp_path, **kw):
    return Config.from_env(backend="mock", cache_dir=tmp_path / "cache", **kw)


# ---------------------------------------------------------------- passages / ranking
def test_chunk_and_rank_find_the_relevant_passage():
    text = "Uber raised prices in 2024 across cities. " * 25 + "Lyft charges 15 dollars per ride on average. " * 12
    chunks = chunk(text)
    assert len(chunks) >= 3 and all(80 <= len(c) <= 700 for c in chunks)
    best = rank("lyft price per ride", chunks + ["dogs and cats and birds " * 10], lambda x: x, 1)[0]
    assert "Lyft" in best
    assert bm25("anything", []) == []


def test_pack_registers_cited_passages_in_ledger():
    ledger, index = EvidenceLedger(), PassageIndex()
    ledger.add("web_search", [{"title": "Zoom pricing", "url": "http://zoom.test/p", "snippet": "plans"}])
    index.add("http://zoom.test/p", "Zoom pricing", "The Pro plan costs 15.99 dollars per month per host. " * 20)
    pack, ids = retrieval.evidence_pack("zoom pro plan price", ["E1"], ledger, index, n_passages=2)
    assert "E1" in ids and len(ids) >= 2 and "15.99" in pack
    excerpt = ledger.get(ids[1])
    assert excerpt.url.startswith("http://zoom.test/p#p") and excerpt.tool == "passage"


# ---------------------------------------------------------------- retrieval
def _tool(name, fn):
    return Tool(name, "stub", {"query": "string"}, fn)


def test_run_queries_falls_back_to_news_when_web_search_fails(monkeypatch):
    monkeypatch.setitem(ALL_TOOLS, "web_search", _tool("web_search", lambda query: ToolResult(text="blocked", error=True)))
    monkeypatch.setitem(ALL_TOOLS, "news_search", _tool("news_search", lambda query: ToolResult(
        sources=[{"title": "News " + query, "url": "http://n/" + query[:6], "snippet": "s"}])))
    ledger = EvidenceLedger()
    out = retrieval.run_queries([retrieval.Query("market", "web_search", "market size")], ledger)
    assert len(out["market"]) == 1 and ledger.get(out["market"][0]).tool == "news_search"


def test_disabled_search_is_replaced_by_news(monkeypatch):
    calls = []
    monkeypatch.setitem(ALL_TOOLS, "web_search", _tool("web_search", lambda query: calls.append("web") or ToolResult()))
    monkeypatch.setitem(ALL_TOOLS, "news_search", _tool("news_search", lambda query: ToolResult(
        sources=[{"title": "n", "url": "http://n/1", "snippet": "s"}])))
    monkeypatch.setenv("DISABLED_TOOLS", "web_search")
    out = retrieval.run_queries([retrieval.Query("customer", "web_search", "x")], EvidenceLedger())
    assert calls == [] and out["customer"]


def test_build_queries_fill_templates_and_extras():
    qs = retrieval.build_queries(["competitor", "regulatory"], "meal kits", "cooking is slow",
                                 extras={"regulatory": "food safety"})
    texts = [q.text for q in qs]
    assert "alternatives to meal kits" in texts and "meal kits food safety" in texts
    assert not any("{" in t for t in texts)
    follow = retrieval.build_queries(["market"], "meal kits", "x", followup=True)
    assert any("TAM" in q.text for q in follow)


def test_fetch_pages_skips_unfetchable_and_survives_errors(monkeypatch):
    ledger, index = EvidenceLedger(), PassageIndex()
    ids = [s.id for s in ledger.add("web_search", [
        {"title": "g", "url": "https://news.google.com/rss/articles/abc", "snippet": ""},
        {"title": "p", "url": "http://x.test/report.pdf", "snippet": ""},
        {"title": "ok", "url": "http://x.test/ok", "snippet": ""},
        {"title": "dead", "url": "http://x.test/dead", "snippet": ""}])]

    def fake(url, limit=30000):
        if "dead" in url:
            raise RuntimeError("404")
        return "T", "A long enough paragraph about pricing and plans for teams. " * 10

    monkeypatch.setattr(retrieval, "page_text", fake)
    assert retrieval.fetch_pages({"s": ids}, ledger, index) == 1
    assert list(index.docs) == ["http://x.test/ok"]


# ---------------------------------------------------------------- competitors
def test_rank_candidates_orders_by_mentions_and_drops_hallucinations():
    corpus = "lyft lyft lyft uber uber bolt google"
    raw = [{"name": "Uber"}, {"name": "Lyft"}, {"name": "Zzyzx Corp"}, {"name": "Google"}, {"name": "lyft inc"}]
    assert competitors.rank_candidates(raw, corpus) == ["Lyft", "Uber"]
    assert competitors.rank_candidates(raw, corpus, skip=["Lyft"]) == ["Uber"]
    assert competitors.rank_candidates([{"name": "Anything"}], "", allow_unseen=True) == ["Anything"]
    assert competitors.rank_candidates(None, corpus) == []


def test_merge_competitors_dedupes_and_prefers_verified():
    merged = competitors.merge_competitors([{"name": "Acme Inc", "verified": False}],
                                           [{"name": "acme", "verified": True}, {"name": "Beta", "verified": True}])
    assert [c["name"] for c in merged] == ["Beta", "Acme Inc"]


# ---------------------------------------------------------------- checkpoint / extractor / llm
def test_checkpoint_roundtrip_and_corruption(tmp_path):
    ck = Checkpoint(tmp_path, run_key("idea", "model"))
    assert ck.load() == {}
    ck.save({"done": ["plan"], "raw": {"plan": {"a": 1}}})
    assert ck.load()["raw"]["plan"] == {"a": 1}
    ck.path.write_text("{not json")
    assert ck.load() == {}
    assert run_key("a", "b") != run_key("a", "c")


class Scripted:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        self.calls.append(schema)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_extractor_repairs_unwraps_and_reports_errors():
    ok = Extractor(Scripted(["nonsense", '{"final": {"a": 1}}']))
    assert ok.run("r", "sys", "user", schemas.CUSTOMER) == ({"a": 1}, None)
    bad = Extractor(Scripted(["x", "y", "z"]))
    assert bad.run("r", "s", "u") == (None, "model never returned valid JSON")
    down = Extractor(Scripted([RuntimeError("server down")]))
    out, err = down.run("r", "s", "u")
    assert out is None and "server down" in err


class FakeResp:
    def __init__(self, status, content="{}"):
        self.status_code, self.text = status, ""
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        pass


def test_llm_degrades_from_json_schema_to_plain(monkeypatch):
    import startup_cofounder.llm as llm_mod
    seen = []

    def fake_post(url, json=None, headers=None, timeout=None):
        fmt = json.get("response_format")
        seen.append(fmt["type"] if fmt else None)
        return FakeResp(400) if fmt else FakeResp(200, '{"ok": true}')

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    client = OpenAICompatLLM(Config.from_env(), model="m")
    assert client.chat([{"role": "user", "content": "hi"}], json_mode=True, schema={"type": "object"}) == '{"ok": true}'
    assert seen == ["json_schema", "json_object", None]


def test_fast_model_selection():
    from startup_cofounder.llm import build_llm
    cfg = Config.from_env(fast_model="small-model", model="big-model")
    assert build_llm(cfg).model == "big-model" and build_llm(cfg, fast=True).model == "small-model"
    assert build_llm(Config.from_env(model="big-model", fast_model=""), fast=True).model == "big-model"


# ---------------------------------------------------------------- pipeline
def test_end_to_end_mock_offline(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True)).run(IDEA)
    assert not any(r.error for r in result.results.values())
    assert len(result.results["competitor"].output["competitors"]) >= 3
    assert result.extra_roles == ["regulatory"]
    md = render_markdown(result)
    for heading in ("## At a glance", "## Competitive landscape (top 3)", "### Scenarios", "## Quality review"):
        assert heading in md
    assert not any("failed" in w for w in result.warnings)
    # no web evidence offline, so nothing may be presented as a sourced fact
    assert all(f.kind == "estimate" for r in result.results.values() for f in r.findings)
    json.dumps(result.to_dict(), default=str)


@pytest.fixture
def stub_web(monkeypatch):
    titles = ["Zoomly video calls review", "Meetio pricing plans compared", "Callrix alternatives guide",
              "Talkify features for remote teams"]

    def search(query):
        return ToolResult(sources=[{"title": t, "url": "http://web.test/%s" % t.split()[0].lower(),
                                    "snippet": t + " for remote teams, from 12 dollars per month."} for t in titles])

    for name in ("web_search", "news_search", "wikipedia", "hn_search"):
        monkeypatch.setitem(ALL_TOOLS, name, _tool(name, search))
    monkeypatch.setattr(retrieval, "page_text", lambda url, limit=30000: (
        "Page", "Pricing and plans for remote teams. The team plan costs 12 dollars per month. " * 12))


def test_with_evidence_cites_discovers_and_verifies(tmp_path, stub_web):
    result = Pipeline(_config(tmp_path)).run(IDEA)
    comps = result.results["competitor"].output["competitors"]
    assert len(comps) >= 3 and all(c["verified"] for c in comps[:3])
    assert any(s["url"].count("#p") for s in result.sources)  # full-page passages were used as evidence
    facts = [f for r in result.results.values() for f in r.findings if f.kind == "fact"]
    assert facts and all(f.source_ids for f in facts)
    assert result.grade in ("A", "B", "C")


class Counting(MockLLM):
    def __init__(self):
        self.calls = []

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        self.calls.append(messages[0]["content"].split("\n", 1)[0])
        return super().chat(messages, temperature, json_mode, schema)


def test_resume_skips_finished_stages(tmp_path, stub_web):
    cfg = _config(tmp_path)
    first = Counting()
    a = Pipeline(cfg, llm=first).run(IDEA)
    assert len(first.calls) > 8
    second = Counting()
    b = Pipeline(cfg, llm=second).run(IDEA)
    assert second.calls == []  # everything restored from the checkpoint
    assert b.verdict == a.verdict and len(b.sources) == len(a.sources)
    third = Counting()
    Pipeline(cfg, llm=third).run(IDEA, fresh=True)
    assert len(third.calls) == len(first.calls)


class CriticMarket(Counting):
    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        if messages[0]["content"].startswith("ROLE: critic"):
            return json.dumps({"approved": False, "gaps": [{"agent": "market", "issue": "needs sizing detail",
                                                            "followup_task": "find reports"}]})
        return super().chat(messages, temperature, json_mode, schema)


def test_review_loop_reruns_flagged_section(tmp_path, stub_web):
    llm = CriticMarket()
    result = Pipeline(_config(tmp_path), llm=llm).run(IDEA)
    assert llm.calls.count("ROLE: market") == 2
    entry = [e for e in result.review_log if e["agent"] == "market"][0]
    assert entry["improved"] is True and entry["origin"] == "critic"


class FlakyTechnical(Counting):
    """technical extraction returns garbage until the review loop retries it."""

    def __init__(self):
        super().__init__()
        self.technical_calls = 0

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        if messages[0]["content"].startswith("ROLE: technical"):
            self.technical_calls += 1
            if self.technical_calls <= 3:  # the Extractor's three attempts
                return "I refuse to answer in JSON."
        return super().chat(messages, temperature, json_mode, schema)


def test_recovers_from_failed_extraction_via_review(tmp_path, stub_web):
    result = Pipeline(_config(tmp_path), llm=FlakyTechnical()).run(IDEA)
    assert result.results["technical"].error is None
    entry = [e for e in result.review_log if e["agent"] == "technical"][0]
    assert entry["origin"] == "rule" and entry["improved"] is True


class SchemaSpy(MockLLM):
    def __init__(self):
        self.schemas = {}

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        self.schemas[messages[0]["content"].split("\n", 1)[0]] = schema
        return super().chat(messages, temperature, json_mode, schema)


def test_requests_schema_constrained_output(tmp_path):
    spy = SchemaSpy()
    Pipeline(_config(tmp_path, offline=True), llm=spy).run(IDEA)
    assert spy.schemas["ROLE: coordinator"] is schemas.COORDINATOR
    assert spy.schemas["ROLE: synthesizer"] is schemas.SYNTHESIZER
    assert spy.schemas["ROLE: candidates"] is schemas.CANDIDATES
    assert spy.schemas["ROLE: market"] is schemas.MARKET


# ---------------------------------------------------------------- robustness and guardrails
def test_short_idea_rejected(tmp_path):
    with pytest.raises(ValueError):
        Pipeline(_config(tmp_path)).run("hi")


class BrokenLLM:
    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        return "I am a chatty model that never emits JSON."


def test_pipeline_survives_garbage_model(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True), llm=BrokenLLM()).run("A marketplace for used lab equipment")
    assert result.warnings
    assert "Financial projection" in render_markdown(result)  # must still render with defaults


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


def test_pipeline_populates_all_outputs(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True)).run("An app that matches restaurants with local farms")
    assert result.extra_roles == ["regulatory"] and "regulatory" in result.results
    assert set(result.scenarios) == {"pessimistic", "base", "optimistic"}
    assert len(result.sensitivity) == 6 and result.unit_economics["ltv_cac"]
    assert result.grade == "D" and result.verdict in ("go", "validate_first", "pivot", "no_go")
    md = render_markdown(result)
    for heading in ("## Verdict", "## Financial projection", "## Recommended validation steps",
                    "## Evidence quality", "### Unit economics", "### What matters most",
                    "## Additional research: Regulatory"):
        assert heading in md


class OptimisticLLM(MockLLM):
    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        out = super().chat(messages, temperature, json_mode, schema)
        if messages[0]["content"].startswith("ROLE: synthesizer"):
            data = json.loads(out)
            data["verdict"] = "go"
            return json.dumps(data)
        return out


def test_guardrail_downgrades_unsupported_go(tmp_path):
    result = Pipeline(_config(tmp_path, offline=True), llm=OptimisticLLM()).run("A tool for freelancers to invoice clients")
    assert result.synthesis["verdict"] == "go"
    assert result.verdict == "validate_first" and "guardrail" in result.verdict_note


class TitleThenNames(MockLLM):
    """First candidate call returns only article titles (all invalid); the retry returns real names."""

    def __init__(self):
        self.candidate_calls = 0

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        if messages[0]["content"].startswith("ROLE: candidates"):
            self.candidate_calls += 1
            names = ["Best Ride-Hailing Apps in 2026", "E16"] if self.candidate_calls == 1 else [
                "Zoomly", "Meetio", "Callrix"]
            return json.dumps({"candidates": [{"name": n} for n in names]})
        return super().chat(messages, temperature, json_mode, schema)


def test_candidate_retry_recovers_after_invalid_names(tmp_path, stub_web):
    llm = TitleThenNames()
    result = Pipeline(_config(tmp_path, critic_rounds=0), llm=llm).run(IDEA)
    assert llm.candidate_calls >= 2
    assert [c["name"] for c in result.results["competitor"].output["competitors"]][:3] == ["Zoomly", "Meetio", "Callrix"]


def test_no_competitors_means_no_invented_summary(tmp_path):
    class NoNames(MockLLM):
        def chat(self, messages, temperature=None, json_mode=False, schema=None):
            if messages[0]["content"].startswith("ROLE: candidates"):
                return json.dumps({"candidates": []})
            return super().chat(messages, temperature, json_mode, schema)

    result = Pipeline(_config(tmp_path, offline=True, critic_rounds=0), llm=NoNames()).run(IDEA)
    out = result.results["competitor"].output
    assert out["competitors"] == [] and "No competitors could be confirmed" in out["summary"]


def test_quick_flag_skips_specialists_and_review(tmp_path):
    from startup_cofounder.cli import main
    out = tmp_path / "r.md"
    assert main(["--mock", "--offline", "--fresh", "--quick", "--out", str(out), "An app for matching farms with chefs"]) == 0
    data = json.loads(out.with_suffix(".json").read_text())
    assert "regulatory" not in data["agents"]
    assert data["review_log"] == []


def test_profile_marked_not_competitor_is_dropped(tmp_path, stub_web):
    class Picky(MockLLM):
        def chat(self, messages, temperature=None, json_mode=False, schema=None):
            out = super().chat(messages, temperature, json_mode, schema)
            if messages[0]["content"].startswith("ROLE: profile") and "CANDIDATE: Meetio" in messages[1]["content"]:
                data = json.loads(out)
                data["is_competitor"] = False
                return json.dumps(data)
            return out

    result = Pipeline(_config(tmp_path, critic_rounds=0), llm=Picky()).run(IDEA)
    names = [c["name"] for c in result.results["competitor"].output["competitors"]]
    assert "Meetio" not in names and names
