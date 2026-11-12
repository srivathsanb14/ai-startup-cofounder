"""Transparent, mechanical comparison of report versions for the same idea.

    python eval/report_rubric.py            # prints a Markdown table and writes eval/report_rubric_results.json

Every number below is computed by the code in this file from the report text (and, where needed, the saved source
list of the run that produced it). They are PROXIES for the qualities in the brief, not a judgement of the business
idea, and some proxies are crude (noted per metric). No model is used. Reports compared (same climbing idea):

  A  Nov 5 original workflow report (outputs/assessment-20261105-155236-096579.md)
  B  Nov 6 adaptive-v2 report as generated (outputs/assessment-20261106-140151-696771.md)
  C  Nov 6 run re-rendered as the report-v3 decision memo (regenerate --v3)
  D  Nov 6 run re-rendered as report-v4 from saved evidence (question-driven agents, extractive, no model calls)
  E  Nov 5 run re-rendered as report-v4 from saved evidence (same)

D/E reuse the evidence gathered by the old agents; they show what the new planning, question decomposition,
validation, synthesis, economics and experiments do with that evidence. They do NOT show what the new research
queries would retrieve; that needs a live run, which was not performed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from startup_cofounder import validators  # noqa: E402
from startup_cofounder.relevance import ResearchFrame  # noqa: E402

LINK = re.compile(r"\]\((https?://[^)\s]+)\)|(?<![(\[])\b(https?://[^\s)\]]+)")
BODY_END = re.compile(r"^(## Sources\b|\*\*Sources cited|---\s*$|## Evidence quality|## Quality review)", re.M)
STAGE_BAD = re.compile(r"\bchurn\b|\bLTV\b|\bCAC\b|lifetime value|retention after 12 months|annual retention", re.I)
IMPLICATION = re.compile(r"implication|so what|this means|which means|means that|therefore|proceed if|stop if|"
                         r"modify if|would change|decide[sd]? whether", re.I)
CONTRADICT = re.compile(r"contradict", re.I)
OVERCLAIM = [(re.compile(r"validated (price|pricing)|proven demand|customers (will|are willing to) pay", re.I),
              "claims validated pricing/demand"),
             (re.compile(r"break[- ]?even (in|by|within) (year|month) ?\d", re.I), "states a break-even date"),
             (re.compile(r"\b(large|huge|significant|growing) (local )?market\b", re.I), "calls the market large/growing"),
             (re.compile(r"\bno (direct )?competitors?\b", re.I), "says there are no competitors")]
FTE = re.compile(r"\b(engineer|developer|growth/sales|cto|ceo|designer)\b[^\n|]{0,40}\|\s*\d", re.I)


def body(md: str) -> str:
    m = BODY_END.search(md)
    return md[:m.start()] if m else md


def sentences(text: str):
    t = re.sub(r"\[\[?\d+\]?\]\([^)]*\)|\([^)]*https?://[^)]*\)", "", text)
    return [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if len(s.split()) >= 8]


def evidence_metrics(text: str, sources: dict, vendors: dict, frame: ResearchFrame, by_id: dict) -> dict:
    urls = [a or b for a, b in LINK.findall(text)]
    urls += [by_id[i] for i in re.findall(r"\b(E\d+)\b", text) if i in by_id]  # [E12]-style citations
    urls = [u.split("#")[0].rstrip(".,") for u in urls]
    uniq = list(dict.fromkeys(urls))
    if not uniq:
        return {"cited_sources": 0}
    types, off, domains = [], 0, {}
    for u in uniq:
        s = sources.get(u, {"url": u, "title": "", "snippet": ""})
        types.append(validators.classify_source(s, vendors))
        if frame.score("%s %s %s" % (s.get("title", ""), s.get("snippet", ""), u)).label == "irrelevant":
            off += 1
        d = validators.host(u)
        domains[d] = domains.get(d, 0) + 1
    n = len(uniq)
    return {"cited_sources": n, "distinct_websites": len(domains),
            "max_share_one_website": round(max(domains.values()) / n, 2),
            "vendor_or_app_listing_share": round(sum(t in ("official_vendor", "app_store") for t in types) / n, 2),
            "user_voice_share": round(sum(t == "forum_community" for t in types) / n, 2),
            "off_topic_share": round(off / n, 2)}


def score(label: str, md_path: Path, run: dict, vendors: dict, frame: ResearchFrame, model: dict = None) -> dict:
    md = md_path.read_text()
    b = body(md)
    sents = sentences(b)
    dup = len(sents) - len(set(sents))
    sources = {}
    for s in run.get("sources", []):
        sources.setdefault(s.get("url", "").split("#")[0], s)
    val = re.split(r"(?i)\n#+ [^\n]*(validation|next steps|experiments)[^\n]*\n", b)
    validation_text = val[-1] if len(val) > 1 else ""
    thresholds = len(re.findall(r"(?i)threshold", validation_text))
    out = {
        "report": label, "file": md_path.name,
        # clarity
        "words_main_report": len(b.split()), "duplicate_sentences": dup,
        "unknown_or_not_found_mentions": len(re.findall(r"(?i)\bunknown\b|not found|no information", b)),
        # relevance / fidelity
        "founder_idea_quoted_verbatim": run.get("idea", "")[:80] in md,
        # evidence
        **evidence_metrics(b, sources, vendors, frame, {s["id"]: s.get("url", "") for s in run.get("sources", [])}),
        # depth
        "implication_statements": sum(1 for s in sents if IMPLICATION.search(s)),
        "contradicting_evidence_mentions": len(CONTRADICT.findall(b)),
        "conditional_verdict": bool(re.search(r"(?i)proceed if|stop if|would change (the|this)", b)),
        # financial credibility
        "five_year_table_shown": bool(re.search(r"(?i)\|\s*(year\s*)?5\s*\|", b) or re.search(r"(?i)\|\s*Y5\b", b)),
        "salaried_roles_in_main_report": len(FTE.findall(b)),
        "lean_or_solo_scenario": bool(re.search(r"(?i)solo|bootstrapp|part-time", b)),
        # consistency (regex proxies; v3/v4 also run their own publication gate)
        "overclaims": [why for rx, why in OVERCLAIM if rx.search(b)],
        # recommendations
        "experiments_with_thresholds": thresholds,
        "stage_inappropriate_terms_in_validation": sorted({m.group(0).lower() for m in
                                                            STAGE_BAD.finditer(validation_text)}),
    }
    if model and model.get("publication"):
        g = model["publication"]["memo_gate"]
        out["publication_gate_untraced_numbers"] = len(g["untraced"])
    elif model and model.get("validation"):
        out["publication_gate_untraced_numbers"] = len(((model.get("validation") or {}).get("publication_gate") or {})
                                                       .get("untraced", []))
    return out


def main() -> int:
    import tempfile
    from startup_cofounder import memo_v4, report_v4
    from startup_cofounder.render import model_for, render
    paths = json.loads((ROOT / "eval" / "rubric_inputs.json").read_text())
    nov5 = json.loads(Path(paths["nov5_json"]).read_text())
    nov6 = json.loads(Path(paths["nov6_json"]).read_text())
    comps = [c for run in (nov5, nov6) for c in (run.get("agents", {}).get("competitor", {}).get("output", {})
                                                   .get("competitors", []) or [])]
    vendors = validators.vendor_domains(comps)
    frame = ResearchFrame.from_plan(nov6["plan"], nov6["idea"])
    tmp = Path(tempfile.mkdtemp())
    rows = []
    rows.append(score("A original workflow (Nov 5)", Path(paths["nov5_md"]), nov5, vendors, frame))
    rows.append(score("B adaptive-v2 as generated (Nov 6)", Path(paths["nov6_md"]), nov6, vendors, frame))
    m3 = model_for(nov6, design="v3")
    (tmp / "c.md").write_text(render(m3, nov6)[0])
    rows.append(score("C report-v3 memo (Nov 6 data)", tmp / "c.md", nov6, vendors, frame, m3))
    for lab, run in (("D report-v4 (Nov 6 data, no model)", nov6), ("E report-v4 (Nov 5 data, no model)", nov5)):
        m4 = report_v4.build(run, regenerated=True)
        p = tmp / (lab[0] + ".md")
        p.write_text(memo_v4.render_memo(m4))
        rows.append(score(lab, p, run, vendors, frame, m4))
    (ROOT / "eval" / "report_rubric_results.json").write_text(json.dumps(rows, indent=2))
    keys = [k for k in rows[0] if k not in ("report", "file")] + ["publication_gate_untraced_numbers"]
    print("| Metric | " + " | ".join(r["report"] for r in rows) + " |")
    print("|---|" + "---|" * len(rows))
    for k in dict.fromkeys(keys):
        print("| %s | %s |" % (k, " | ".join(_fmt(r.get(k, "-")) for r in rows)))
    return 0


def _fmt(v) -> str:
    if isinstance(v, list):
        return "; ".join(v) if v else "none"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


if __name__ == "__main__":
    raise SystemExit(main())
