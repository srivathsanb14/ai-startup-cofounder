"""Streamlit UI:  streamlit run app.py

Run a new assessment, or open a saved one. Both are shown from the same validated report model (report-v4 by
default; saved older runs are re-rendered from their saved evidence): decision memo, evidence appendix and
diagnostics, with labelled downloads for each.
"""
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from startup_cofounder.cli import describe_event
from startup_cofounder.config import Config
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.render import model_for, render

st.set_page_config(page_title="AI Startup Co-Founder", page_icon="🚀", layout="wide")
st.title("AI Startup Co-Founder")
st.caption("Type a rough business idea. Agents research customers, competitors, the market, feasibility and "
           "financials; code validates the evidence and writes a founder decision memo.")


def show(data: dict, stem: str, design: str = "v4") -> None:
    model = model_for(data, design=design)
    memo, appendix = render(model, data)
    c1, c2, c3 = st.columns(3)
    if model.get("schema") == "report-v4":
        syn = model["synthesis"]
        c1.metric("Recommendation", syn["verdict"]["verdict"].replace("_", " "))
        answered = sum(1 for q in model["questions"].values() if q["status"] in ("answered", "partial"))
        c2.metric("Research questions answered", "%d / %d" % (answered, len(model["questions"])))
        c3.metric("Experiments proposed", len(syn["experiments"]))
        if model.get("evidence_mode") == "saved_extractive":
            st.info("Regenerated from saved evidence without new searches or model calls.")
    else:
        st_ = model["status"]
        c1.metric("Run status", "finished" if st_["execution"] == "complete" else "INCOMPLETE")
        c2.metric("Evidence adequacy", st_["evidence_adequacy"])
        c3.metric("Critical open questions", len(st_["critical_unknowns"]))
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download decision memo (.md)", memo, file_name=stem + "-memo.md")
    d2.download_button("Download evidence appendix (.md)", appendix, file_name=stem + "-appendix.md")
    full = dict(data, report_schema=model["schema"], report=model)
    d3.download_button("Download data (.json)", json.dumps(full, indent=2, default=str), file_name=stem + ".json")
    tab_memo, tab_appendix, tab_diag = st.tabs(["Decision memo", "Evidence appendix", "Diagnostics"])
    with tab_memo:
        st.markdown(memo)
    with tab_appendix:
        st.markdown(appendix)
    with tab_diag:
        st.caption("For debugging the workflow. These numbers describe the research process, not the business.")
        card = data.get("scorecard") or {}
        if card:
            st.json({"execution": card.get("execution"), "research_quality": card.get("research_quality")})
        with st.expander("Issues"):
            st.json(data.get("issues", []))
        with st.expander("Corrections applied"):
            st.json(model.get("corrections", []))
        with st.expander("Raw data"):
            st.json(data)


with st.sidebar:
    st.header("Settings")
    defaults = Config.from_env()
    mock = st.checkbox("Mock LLM (demo, no model needed)", value=defaults.backend == "mock")
    offline = st.checkbox("Offline (no web tools)", value=defaults.offline)
    model = st.text_input("Model", defaults.model)
    base_url = st.text_input("LLM base URL", defaults.base_url)
    if defaults.run_minutes:
        st.caption("Time budget: up to %d minutes (a ceiling, not a target). Up to %d review rounds and %d extra "
                   "specialists." % (defaults.run_minutes, defaults.critic_rounds, defaults.max_extra_specialists))
    st.header("Saved reports")
    saved = sorted([p for p in defaults.output_dir.glob("*.json") if not p.name.endswith(("-v3.json", "-v4.json"))]
                   if defaults.output_dir.exists() else [], reverse=True)
    choice = st.selectbox("Open a saved report", ["(none)"] + [p.name for p in saved])
    design = "v3" if st.checkbox("Show the previous report format (v3)", value=False) else "v4"

if choice != "(none)":
    path = defaults.output_dir / choice
    st.subheader("Saved report: " + choice)
    try:
        show(json.loads(path.read_text()), path.stem, design)
    except (OSError, ValueError) as exc:
        st.error("Could not open %s: %s" % (choice, exc))
    st.stop()

idea = st.text_area("Your idea", height=110,
                    placeholder="e.g. A subscription service that matches small restaurants with local farms for weekly produce")

if st.button("Analyze", type="primary", disabled=len(idea.strip()) < 8):
    config = Config.from_env(backend="mock" if mock else "openai", offline=offline, model=model, base_url=base_url)
    events: "queue.Queue[dict]" = queue.Queue()
    box = {}
    started = time.monotonic()

    def work():
        try:
            box["result"] = Pipeline(config, on_event=events.put).run(idea)
            # Save the memo, appendix and data even if the browser disconnects before displaying them.
            try:
                config.output_dir.mkdir(parents=True, exist_ok=True)
                stem = "assessment-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                data = box["result"].to_dict()
                memo_text, appendix_text = render(data["report"], data)
                (config.output_dir / (stem + ".md")).write_text(memo_text)
                (config.output_dir / (stem + "-appendix.md")).write_text(appendix_text)
                (config.output_dir / (stem + ".json")).write_text(json.dumps(data, indent=2, default=str))
                box["saved"], box["stem"] = str(config.output_dir / (stem + ".md")), stem
            except OSError as exc:
                box["save_error"] = str(exc)
        except Exception as exc:  # surfaced in the UI below
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    log = st.status("Agents working...", expanded=True)
    elapsed = st.empty()
    now_doing = st.empty()
    last_tick = -1
    while thread.is_alive() or not events.empty():
        seconds = int(time.monotonic() - started)
        if seconds // 5 != last_tick:
            last_tick = seconds // 5
            elapsed.caption("Elapsed: %d min %02d sec%s" % (seconds // 60, seconds % 60,
                " · Budget: up to %d minutes" % config.run_minutes if config.run_minutes else ""))
        try:
            e = events.get(timeout=0.3)
            if e.get("status") not in ("searching", "reading"):
                log.write(describe_event(e))
            now_doing.info("Now: **%s** is %s%s" % (e.get("agent", e["stage"]), e.get("phase") or e["status"],
                                                      (" — " + str(e.get("detail"))[:120]) if e.get("detail") else ""))
        except queue.Empty:
            pass

    if "error" in box:
        log.update(label="Failed", state="error")
        st.error(str(box["error"]))
    else:
        log.update(label="Done", state="complete", expanded=False)
        if box.get("saved"):
            st.caption("Saved in the outputs folder: %s (+ -appendix.md and .json)" % box["saved"])
        if box.get("save_error"):
            st.warning("Automatic saving failed; use the download buttons. " + box["save_error"])
        show(box["result"].to_dict(), box.get("stem", "assessment"))
