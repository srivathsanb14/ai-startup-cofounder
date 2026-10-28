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
    api_key: str = "ollama"
    temperature: float = 0.2
    timeout: int = 600
    max_tool_calls: int = 6
    max_workers: int = 4
    critic_rounds: int = 1  # review-and-redo rounds; 0 disables the critic loop
    max_extra_specialists: int = 2  # extra agents the coordinator may add for idea-specific topics
    offline: bool = False
    cache_dir: Path = ROOT / ".cache"
    output_dir: Path = ROOT / "outputs"

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        _load_dotenv(ROOT / ".env")
        env = os.environ
        cfg = cls(
            backend=env.get("LLM_BACKEND", cls.backend),
            base_url=env.get("LLM_BASE_URL", cls.base_url).rstrip("/"),
            model=env.get("LLM_MODEL", cls.model),
            api_key=env.get("LLM_API_KEY", cls.api_key),
            temperature=float(env.get("LLM_TEMPERATURE", cls.temperature)),
            timeout=int(env.get("LLM_TIMEOUT", cls.timeout)),
            max_tool_calls=int(env.get("MAX_TOOL_CALLS", cls.max_tool_calls)),
            max_workers=int(env.get("MAX_WORKERS", cls.max_workers)),
            critic_rounds=int(env.get("CRITIC_ROUNDS", cls.critic_rounds)),
            max_extra_specialists=int(env.get("MAX_EXTRA_SPECIALISTS", cls.max_extra_specialists)),
            offline=env.get("OFFLINE", "0") == "1",
        )
        for key, value in overrides.items():
            if value is not None:
                object.__setattr__(cfg, key, value)
        return cfg
