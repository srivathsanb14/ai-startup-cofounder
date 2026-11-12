"""Regenerate the second-concept example (B2B scheduling app) used by the regression tests.

    python eval/examples/make_second_concept.py

Runs the full question-design pipeline against tests/stubweb.py: a small FIXED set of invented pages (domains end in
.test) and a scripted stand-in for the small model. No network, no model server. The output shows how the agents
behave on a non-climbing, business-to-business idea; its facts are test fixtures, not research.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import pytest  # noqa: E402

import stubweb  # noqa: E402
from startup_cofounder.config import Config  # noqa: E402
from startup_cofounder.pipeline import Pipeline  # noqa: E402
from startup_cofounder.render import render  # noqa: E402

if __name__ == "__main__":
    import tempfile
    with pytest.MonkeyPatch.context() as mp:
        stubweb.install(mp)
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(agent_design="questions", backend="mock", max_workers=1, cache_dir=tmp / "c",
                     output_dir=tmp / "o", resume=False)
        d = Pipeline(cfg, llm=stubweb.ScriptedSmallModel()).run(stubweb.IDEA, fresh=True).to_dict()
    memo, appendix = render(d["report"], d)
    note = ("> TEST FIXTURE: generated from tests/stubweb.py (invented .test pages and a scripted model) to show the "
            "agents on a second, business-to-business concept. Not real research.\n\n")
    out = Path(__file__).parent
    (out / "second-concept-coffee-scheduling-memo.md").write_text(note + memo)
    (out / "second-concept-coffee-scheduling-appendix.md").write_text(note + appendix)
    print("written to", out)
