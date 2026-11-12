import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Keep tests independent of the shell and of a developer's local .env. Settings exported for a real run
# (e.g. RESUME=0, LLM_MODEL=..., MAX_WORKERS=1 from the run commands) would otherwise change test behaviour,
# so every setting Config.from_env reads is cleared here; Config.from_env uses setdefault, so values set here win.
_SETTINGS = ("LLM_BACKEND", "LLM_BASE_URL", "LLM_MODEL", "LLM_FAST_MODEL", "LLM_API_KEY", "LLM_TEMPERATURE",
             "LLM_TIMEOUT", "RUN_MINUTES", "LLM_MAX_TOKENS", "COORDINATOR_MAX_TOKENS", "LLM_ATTEMPTS",
             "COMPETITOR_PROFILES", "MAX_WORKERS", "CRITIC_ROUNDS", "MAX_EXTRA_SPECIALISTS", "RESUME",
             "LLM_CONTEXT_TOKENS", "SECTION_SEARCHES", "SECTION_FETCHES", "PLANNER_STEPS", "RUN_SEARCHES",
             "RUN_FETCHES", "CLAIM_CHECK", "QUESTION_REPAIRS", "ILLUSTRATIVE_PROJECTION")
for _key in _SETTINGS:
    os.environ.pop(_key, None)

# The section-workflow tests pin AGENT_DESIGN=sections; tests of the question design pass agent_design explicitly.
for _key, _value in {"DISABLED_TOOLS": "", "BRAVE_API_KEY": "", "SEARXNG_URL": "", "OFFLINE": "0",
                     "AGENT_DESIGN": "sections"}.items():
    os.environ[_key] = _value
