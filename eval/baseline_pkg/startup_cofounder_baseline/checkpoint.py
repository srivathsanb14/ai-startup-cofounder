"""Stage checkpoints so a timeout or crash resumes where it stopped instead of restarting a 30-minute run."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Optional


def run_key(idea: str, *parts: str) -> str:
    return hashlib.sha1("\x1f".join((idea,) + parts).encode()).hexdigest()[:16]


class Checkpoint:
    def __init__(self, root: Optional[Path], key: str) -> None:
        self.path = Path(root) / (key + ".json") if root else None
        self._lock = threading.Lock()

    def load(self) -> dict:
        if self.path and self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (OSError, ValueError):
                pass  # corrupt checkpoint: start over
        return {}

    def save(self, state: dict) -> None:
        if not self.path:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, default=str))
            os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written checkpoint

    def clear(self) -> None:
        if self.path and self.path.exists():
            self.path.unlink()
