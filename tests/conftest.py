import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Keep tests independent of a developer's local .env (Config.from_env uses setdefault, so values set here win).
for _key, _value in {"DISABLED_TOOLS": "", "BRAVE_API_KEY": "", "SEARXNG_URL": "", "OFFLINE": "0"}.items():
    os.environ[_key] = _value
