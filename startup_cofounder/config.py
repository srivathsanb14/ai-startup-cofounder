from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we avoid a dependency. Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip()  # inline comments
        os.environ.setdefault(key.strip(), value.strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    backend: str = "openai"  # "openai" (any OpenAI-compatible server) or "mock"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:7b-instruct"
    fast_model: str = ""  # optional cheaper model for extraction (same as model when empty)
    api_key: str = "ollama"
    temperature: float = 0.2
    timeout: int = 600
    run_minutes: int = 0  # optional total budget; zero preserves unlimited stage scheduling
    max_tokens: int = 1600
    coordinator_tokens: int = 800
    llm_attempts: int = 3
    competitor_profiles: int = 4
    max_workers: int = 4
    critic_rounds: int = 1  # review-and-redo rounds; 0 disables the critic loop
    max_extra_specialists: int = 2  # extra researchers the coordinator may add for idea-specific topics
    offline: bool = False
    resume: bool = True  # reuse stage checkpoints from an interrupted run of the same idea
    # Context management: the model server's real context window (Ollama defaults to 4096 unless
    # OLLAMA_CONTEXT_LENGTH or a Modelfile says otherwise). Prompts are fitted to this; it is not raised here.
    context_tokens: int = 4096
    # Bounded adaptive research (per section, then per run)
    section_searches: int = 5
    section_fetches: int = 2
    planner_steps: int = 2  # model-proposed actions per section per attempt
    run_searches: int = 45
    run_fetches: int = 16
    claim_check: bool = True  # model-based claim verification (fallible; recorded separately)
    # Agent design: "questions" (research-planning agent + question-scoped analysts + decision synthesis, report-v4)
    # or "sections" (previous section agents, report-v3)
    agent_design: str = "questions"
    question_repairs: int = 3  # per-question repair attempts per run (field-specific, measured)
    illustrative_projection: bool = False  # show a 5-year projection even when its inputs are not evidence-based
    cache_dir: Path = ROOT / ".cache"
    output_dir: Path = ROOT / "outputs"

    def public(self) -> dict:
        """Configuration recorded in traces (never the API key)."""
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items() if k != "api_key"}

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        _load_dotenv(ROOT / ".env")
        env = os.environ
        cfg = cls(
            backend=env.get("LLM_BACKEND", cls.backend),
            base_url=env.get("LLM_BASE_URL", cls.base_url).rstrip("/"),
            model=env.get("LLM_MODEL", cls.model),
            fast_model=env.get("LLM_FAST_MODEL", cls.fast_model),
            api_key=env.get("LLM_API_KEY", cls.api_key),
            temperature=float(env.get("LLM_TEMPERATURE", cls.temperature)),
            timeout=int(env.get("LLM_TIMEOUT", cls.timeout)),
            run_minutes=max(0, int(env.get("RUN_MINUTES", cls.run_minutes))),
            max_tokens=max(128, int(env.get("LLM_MAX_TOKENS", cls.max_tokens))),
            coordinator_tokens=max(128, int(env.get("COORDINATOR_MAX_TOKENS", cls.coordinator_tokens))),
            llm_attempts=max(1, int(env.get("LLM_ATTEMPTS", cls.llm_attempts))),
            competitor_profiles=max(3, int(env.get("COMPETITOR_PROFILES", cls.competitor_profiles))),
            max_workers=int(env.get("MAX_WORKERS", cls.max_workers)),
            critic_rounds=int(env.get("CRITIC_ROUNDS", cls.critic_rounds)),
            max_extra_specialists=int(env.get("MAX_EXTRA_SPECIALISTS", cls.max_extra_specialists)),
            offline=env.get("OFFLINE", "0") == "1",
            resume=env.get("RESUME", "1") != "0",
            context_tokens=max(1024, int(env.get("LLM_CONTEXT_TOKENS", cls.context_tokens))),
            section_searches=max(1, int(env.get("SECTION_SEARCHES", cls.section_searches))),
            section_fetches=max(0, int(env.get("SECTION_FETCHES", cls.section_fetches))),
            planner_steps=max(0, int(env.get("PLANNER_STEPS", cls.planner_steps))),
            run_searches=max(1, int(env.get("RUN_SEARCHES", cls.run_searches))),
            run_fetches=max(0, int(env.get("RUN_FETCHES", cls.run_fetches))),
            claim_check=env.get("CLAIM_CHECK", "1") != "0",
            agent_design=env.get("AGENT_DESIGN", cls.agent_design) if env.get("AGENT_DESIGN", cls.agent_design) in (
                "questions", "sections") else cls.agent_design,
            question_repairs=max(0, int(env.get("QUESTION_REPAIRS", cls.question_repairs))),
            illustrative_projection=env.get("ILLUSTRATIVE_PROJECTION", "0") == "1",
        )
        for key, value in overrides.items():
            if value is not None:
                object.__setattr__(cfg, key, value)
        return cfg
