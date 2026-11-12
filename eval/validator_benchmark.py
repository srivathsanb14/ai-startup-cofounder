"""Measure how accurate each validation layer is against hand-labelled cases (eval/gold/validator_gold.json).

    .venv/bin/python eval/validator_benchmark.py                     # deterministic layers, no model (seconds)
    .venv/bin/python eval/validator_benchmark.py --model qwen2.5:3b-instruct   # also test the model fact-checker
                                                                       # (needs Ollama running; ~16 claims, a few minutes)

Validation code that is never measured can be confidently wrong. This reports, per layer, accuracy and the two error
types that matter: accepting something a careful reader would reject (false accept) and rejecting something that is
fine (false reject). The labels are a small, reviewable set; extend them as you inspect more runs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from startup_cofounder import claims as claimlib  # noqa: E402
from startup_cofounder import final_review, identity, validators  # noqa: E402
from startup_cofounder.audit import ledger_from_sources  # noqa: E402
from startup_cofounder.relevance import RelevanceBook, ResearchFrame  # noqa: E402

RUNS = {"1105": ROOT / "tests" / "fixtures" / "failed_run_20261105.json",
        "1106": ROOT / "tests" / "fixtures" / "run_20261106.json"}
GOLD = ROOT / "eval" / "gold" / "validator_gold.json"


def _load():
    runs = {}
    for k, p in RUNS.items():
        d = json.loads(p.read_text())
        frame = ResearchFrame.from_plan(d["plan"], d["idea"])
        runs[k] = {"d": d, "ledger": ledger_from_sources(d["sources"]), "frame": frame, "book": RelevanceBook(frame),
                   "src": {s["id"]: s for s in d["sources"]}}
    return runs, json.loads(GOLD.read_text())


def _score(pairs, accept_label, accept_pred):
    """pairs: (gold, predicted). 'accept' = label/prediction that lets the item through."""
    n = len(pairs)
    correct = sum(1 for g, p in pairs if accept_label(g) == accept_pred(p))
    fa = sum(1 for g, p in pairs if not accept_label(g) and accept_pred(p))
    fr = sum(1 for g, p in pairs if accept_label(g) and not accept_pred(p))
    return {"n": n, "accuracy": round(correct / n, 2) if n else None, "false_accept": fa, "false_reject": fr}


def relevance(runs, gold):
    pairs = []
    for g in gold["relevance"]:
        r = runs[g["run"]]
        src = r["ledger"].get(g["id"])
        pairs.append((g["label"], r["book"].of(src).label, g["id"]))
    res = _score([(a, b) for a, b, _ in pairs], lambda x: x != "irrelevant", lambda x: x != "irrelevant")
    res["errors"] = [(i, a, b) for a, b, i in pairs if (a != "irrelevant") != (b != "irrelevant")]
    return res


def source_types(runs, gold):
    pairs = []
    for g in gold["source_types"]:
        r = runs[g["run"]]
        comp = r["d"]["agents"]["competitor"]["output"]
        vendors = validators.vendor_domains((comp.get("competitors") or []))
        pairs.append((g["label"], validators.classify_source(r["src"][g["id"]], vendors), g["id"]))
    correct = sum(1 for a, b, _ in pairs if a == b)
    return {"n": len(pairs), "accuracy": round(correct / len(pairs), 2),
            "errors": [(i, a, b) for a, b, i in pairs if a != b]}


def _claim(runs, g):
    r = runs[g["run"]]
    return next(c for c in r["d"]["claims"] if c["id"] == g["id"])


def claim_support_code(runs, gold):
    """Code-only layers (lexical screen + re-screen + credibility). The saved model check is removed first."""
    pairs = []
    for g in gold["claims"]:
        r = runs[g["run"]]
        c = dict(_claim(runs, g))
        ledger, book, frame = r["ledger"], r["book"], r["frame"]
        fresh = claimlib.build_claim(c["id"], c["section"], c["field"], c["text"], "fact", c["source_ids"], ledger,
                                     book, frame).to_dict()
        fresh = claimlib.rescreen(fresh, frame)
        comp = r["d"]["agents"]["competitor"]["output"].get("competitors") or []
        fresh["status"] = validators.assess_claim(fresh, r["src"], validators.vendor_domains(comp))["status_after"]
        pairs.append((g["label"], fresh["status"], g["id"]))
    res = _score([(a, b) for a, b, _ in pairs], lambda x: x != "unsupported", lambda x: x != "unsupported")
    res["errors"] = [(i, a, b) for a, b, i in pairs if (a != "unsupported") != (b != "unsupported")]
    res["note"] = "code alone never says 'supported'; it separates unsupported from (partially) supported"
    return res


def claim_support_saved(runs, gold):
    """Statuses as saved by the live run (code + the 3B model check), for comparison."""
    pairs = [(g["label"], _claim(runs, g)["status"], g["id"]) for g in gold["claims"]]
    res = _score([(a, b) for a, b, _ in pairs], lambda x: x != "unsupported", lambda x: x != "unsupported")
    res["exact_match"] = round(sum(1 for a, b, _ in pairs if a == b) / len(pairs), 2)
    res["errors"] = [(i, a, b) for a, b, i in pairs if (a != "unsupported") != (b != "unsupported")]
    return res


def claim_support_published(runs, gold):
    """Saved statuses after the v3.1 report re-screen (questions, geography) and credibility layer: what the report
    now publishes from the same saved run."""
    pairs = []
    for g in gold["claims"]:
        r = runs[g["run"]]
        c = claimlib.rescreen(_claim(runs, g), r["frame"])
        comp = r["d"]["agents"]["competitor"]["output"].get("competitors") or []
        c["status"] = validators.assess_claim(c, r["src"], validators.vendor_domains(comp))["status_after"]
        pairs.append((g["label"], c["status"], g["id"]))
    res = _score([(a, b) for a, b, _ in pairs], lambda x: x != "unsupported", lambda x: x != "unsupported")
    res["exact_match"] = round(sum(1 for a, b, _ in pairs if a == b) / len(pairs), 2)
    res["errors"] = [(i, a, b) for a, b, i in pairs if (a != "unsupported") != (b != "unsupported")]
    return res


def identity_layer(runs, gold):
    pairs = []
    for g in gold["identity"]:
        r = runs[g["run"]]
        comp = next(c for c in r["d"]["agents"]["competitor"]["output"]["competitors"] if c["name"] == g["name"])
        pred = identity.classify(dict(comp), g["name"], r["ledger"], r["book"], [s.id for s in r["ledger"].all()])
        pairs.append((g["label"], pred["relation"] if pred["verified"] else "not counted:" + pred["relation"], g["name"]))
    counted = _score([(a, b) for a, b, _ in pairs], lambda x: x in identity.COUNTED, lambda x: x in identity.COUNTED)
    counted["direct_correct"] = sum(1 for a, b, _ in pairs if (a == "direct") == (b == "direct"))
    counted["predictions"] = [(n, a, b) for a, b, n in pairs]
    return counted


def financial_statements(gold):
    pairs = []
    for g in gold["financial_statements"]:
        found = final_review.financial_statements({"executive_summary": g["text"]},
                                                  {"breakeven_year": g["breakeven_year"],
                                                   "payback_year": g["payback_year"]})
        pairs.append((g["contradiction"], bool(found), g["text"]))
    correct = sum(1 for a, b, _ in pairs if a == b)
    return {"n": len(pairs), "accuracy": round(correct / len(pairs), 2),
            "missed_contradictions": [t for a, b, t in pairs if a and not b],
            "false_alarms": [t for a, b, t in pairs if b and not a]}


def live_checker(runs, gold, model: str, base_url: str):
    """Ask the local model to check the gold claims exactly as the pipeline does, with a control item."""
    from startup_cofounder.config import Config
    from startup_cofounder.extract import Extractor
    from startup_cofounder.llm import OpenAICompatLLM
    cfg = Config.from_env(model=model, base_url=base_url, backend="openai")
    ex = Extractor(OpenAICompatLLM(cfg))
    system = "ROLE: verifier\n%s\nReply with ONE JSON object:\n%s" % (claimlib.VERIFIER_MISSION, claimlib.VERIFIER_TEXT)
    pairs, controls = [], []
    items = []
    for g in gold["claims"]:
        c = _claim(runs, g)
        items.append((g, claimlib.Claim(c["id"], c["section"], c["field"], c["text"], "fact", c["source_ids"],
                                        passage=c["passage"])))
    for k in range(0, len(items), 4):  # same batch size as the pipeline
        chunk = items[k:k + 4]
        batch, ctrl = claimlib.with_control([c for _, c in chunk], "bench")
        out, err = ex.run("verifier", system, "Check these claims.\n" + "\n".join(claimlib.verifier_prompt(batch)),
                          claimlib.VERIFIER_SCHEMA)
        controls.append(claimlib.control_result(out, ctrl))
        got = {str(i.get("id")): str(i.get("status")) for i in (out or {}).get("checks", []) if isinstance(i, dict)}
        for g, c in chunk:
            pairs.append((g["label"], got.get(c.id, "missing"), c.id))
    res = _score([(a, b) for a, b, _ in pairs], lambda x: x != "unsupported",
                 lambda x: x not in ("unsupported", "contradicted", "missing"))
    res["exact_match"] = round(sum(1 for a, b, _ in pairs if a == b) / len(pairs), 2)
    res["control_probes"] = controls
    res["errors"] = [(i, a, b) for a, b, i in pairs if a != b]
    return res


def run(model=None, base_url="http://localhost:11434/v1") -> dict:
    runs, gold = _load()
    out = {"relevance gate": relevance(runs, gold), "source type": source_types(runs, gold),
           "claim support (code only)": claim_support_code(runs, gold),
           "claim support (as saved: code + 3B check)": claim_support_saved(runs, gold),
           "claim support (published: saved + v3.1 re-screen)": claim_support_published(runs, gold),
           "competitor identity": identity_layer(runs, gold), "financial statements": financial_statements(gold)}
    if model:
        out["fact-checker live (%s)" % model] = live_checker(runs, gold, model, base_url)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", help="also measure this local model as the fact-checker (Ollama must be running)")
    p.add_argument("--base-url", default="http://localhost:11434/v1")
    args = p.parse_args(argv)
    res = run(args.model, args.base_url)
    print("| Layer | Cases | Accuracy | False accept | False reject |\n|---|---|---|---|---|")
    for name, r in res.items():
        print("| %s | %s | %s | %s | %s |" % (name, r["n"], r.get("accuracy"), r.get("false_accept", "-"),
                                            r.get("false_reject", "-")))
    print()
    for name, r in res.items():
        errs = r.get("errors") or r.get("missed_contradictions") or []
        if errs or r.get("false_alarms"):
            print("%s errors: %s %s" % (name, errs, r.get("false_alarms") or ""))
        if r.get("control_probes"):
            print("%s control probes: %s" % (name, r["control_probes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
