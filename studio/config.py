"""studio configuration — one shared home + model backend for every capability."""
from __future__ import annotations

import json
import os
from pathlib import Path

STUDIO_HOME = Path(os.environ.get("STUDIO_HOME", Path.home() / ".studio"))
CONFIG_PATH = STUDIO_HOME / "config.json"

DEFAULTS = {
    "ollama_host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "default_model": "",            # empty -> each tool auto-picks
    "agent_forge_install": "thandv",  # which content view to install on `studio install`
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    return cfg


def save(cfg: dict) -> None:
    STUDIO_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
