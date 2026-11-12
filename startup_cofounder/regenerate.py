"""Re-render a saved assessment JSON WITHOUT new research.

    python -m startup_cofounder.regenerate outputs/assessment-20261106-140151-696771.json
    python -m startup_cofounder.regenerate --v3 outputs/<file>.json          # previous report format
    python -m startup_cofounder.regenerate --with-model outputs/<file>.json  # local model reads the saved evidence

Default (report-v4): the question-driven agents are re-run over the SAVED sources only: no web searches and no model
calls. Each research question gets the most relevant verbatim passages ("evidence located, not analysed"); the
economics, cross-section synthesis, verdict and experiments are computed deterministically.

--with-model additionally lets the configured local model (LLM_MODEL / LLM_BASE_URL, e.g. Ollama) interpret the same
saved evidence: about one small call per research question (10-12 calls), sequential. No web access.

Writes next to the input: <stem>-v4-memo.md, <stem>-v4-appendix.md, <stem>-v4.json (or the -memo/-appendix/-v3
names with --v3). The original files are left untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .render import model_for, render


def regenerate(path: Path, out_dir: Path = None, design: str = "v4", extract_fn=None) -> dict:
    d = json.loads(Path(path).read_text())
    model = model_for(d, design=design, extract_fn=extract_fn)
    memo_text, appendix_text = render(model, d)
    out_dir = Path(out_dir or Path(path).parent)
    stem = Path(path).stem
    if design == "v3":
        paths = {"memo": out_dir / (stem + "-memo.md"), "appendix": out_dir / (stem + "-appendix.md"),
                 "json": out_dir / (stem + "-v3.json")}
    else:
        paths = {"memo": out_dir / (stem + "-v4-memo.md"), "appendix": out_dir / (stem + "-v4-appendix.md"),
                 "json": out_dir / (stem + "-v4.json")}
    paths["memo"].write_text(memo_text)
    paths["appendix"].write_text(appendix_text)
    data = dict(d)
    data["report_schema"] = model["schema"]
    data["report"] = model
    paths["json"].write_text(json.dumps(data, indent=2, default=str))
    return {k: str(v) for k, v in paths.items()}


def _local_extractor():
    from .config import Config
    from .extract import Extractor
    from .llm import build_llm
    cfg = Config.from_env()
    ex = Extractor(build_llm(cfg, fast=True))
    print("Using local model %s at %s (saved evidence only; no web access)" % (cfg.fast_model or cfg.model,
                                                                              cfg.base_url), file=sys.stderr)
    return lambda system, user, schema: ex.run("analyst", system, user, schema)


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    design = "v3" if "--v3" in argv else "v4"
    extract_fn = _local_extractor() if "--with-model" in argv and design == "v4" else None
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        print(__doc__, file=sys.stderr)
        return 2
    for p in files:
        for kind, out in regenerate(Path(p), design=design, extract_fn=extract_fn).items():
            print("%-8s %s" % (kind, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
