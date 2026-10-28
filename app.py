"""Streamlit UI:  streamlit run app.py"""
import queue
import threading

import streamlit as st

from startup_cofounder.config import Config
from startup_cofounder.pipeline import Pipeline
from startup_cofounder.report import render_markdown

st.set_page_config(page_title="AI Startup Co-Founder", page_icon="🚀", layout="wide")
st.title("🚀 AI Startup Co-Founder")
st.caption("Type a rough business idea. A team of agents researches customers, competitors, the market, "
           "feasibility and financials, then writes an evidence-backed assessment.")

with st.sidebar:
    st.header("Settings")
    defaults = Config.from_env()
    mock = st.checkbox("Mock LLM (demo, no model needed)", value=defaults.backend == "mock")
    offline = st.checkbox("Offline (no web tools)", value=defaults.offline)
    model = st.text_input("Model", defaults.model)
    base_url = st.text_input("LLM base URL", defaults.base_url)

idea = st.text_area("Your idea", height=110,
                    placeholder="e.g. A subscription service that matches small restaurants with local farms for weekly produce")

if st.button("Analyze", type="primary", disabled=len(idea.strip()) < 8):
    config = Config.from_env(backend="mock" if mock else "openai", offline=offline, model=model, base_url=base_url)
    events: "queue.Queue[dict]" = queue.Queue()
    box = {}

    def work():
        try:
            box["result"] = Pipeline(config, on_event=events.put).run(idea)
        except Exception as exc:  # surfaced in the UI below
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    log = st.status("Agents working...", expanded=True)
    while thread.is_alive() or not events.empty():
        try:
            e = events.get(timeout=0.3)
            log.write("**%s** %s %s" % (e["stage"], e["status"], e.get("detail", "")))
        except queue.Empty:
            pass

    if "error" in box:
        log.update(label="Failed", state="error")
        st.error(str(box["error"]))
    else:
        log.update(label="Done", state="complete", expanded=False)
        assessment = box["result"]
        markdown = render_markdown(assessment)
        st.download_button("Download report (.md)", markdown, file_name="assessment.md")
        c1, c2, c3, c4 = st.columns(4)
        p = assessment.projection
        c1.metric("Verdict", assessment.verdict.replace("_", " ").title())
        c2.metric("Evidence grade", assessment.grade)
        ratio = assessment.unit_economics.get("ltv_cac")
        c3.metric("LTV / CAC", "%.1f" % ratio if ratio is not None else "n/a")
        c4.metric("Break-even", "Year %d" % p.breakeven_year if p.breakeven_year else "Beyond year 5")
        chart = {name.title(): sc.table.set_index("year")["cumulative_cash"] for name, sc in assessment.scenarios.items()}
        st.subheader("Cumulative cash by scenario")
        st.line_chart(chart)
        st.markdown(markdown)
        with st.expander("Raw agent traces"):
            st.json(assessment.to_dict())
