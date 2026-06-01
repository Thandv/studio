"""Capability registry — the map from `studio <name>` to an underlying tool.

Each sibling project stays independent (its own repo + venv). studio is a thin
dispatcher: it resolves a capability to a concrete command and shells out,
passing a shared environment (model backend, home). Nothing here imports the
tools — it only locates and runs them.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# studio repo is <base>/studio ; siblings live under <base>.
BASE = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    repo: str                      # path relative to BASE
    kind: str = "passthrough"      # passthrough | driver | content
    script: str = ""               # console-script name (passthrough)
    driver: str = ""               # path to a python driver, relative to repo (driver)
    needs: tuple[str, ...] = ()     # required system deps / markers

    def repo_path(self) -> Path:
        return BASE / self.repo

    def venv_python(self) -> Path:
        return self.repo_path() / ".venv" / "bin" / "python"

    def resolve_command(self) -> list[str] | None:
        """Return the runnable command for this capability, or None if absent."""
        repo = self.repo_path()
        if not repo.exists():
            return None
        if self.kind == "driver":
            py = self.venv_python()
            drv = repo / self.driver
            if drv.exists():
                return [str(py if py.exists() else "python3"), str(drv)]
            return None
        if self.kind == "content":
            return ["python3"]  # studio runs agent-forge scripts directly
        # passthrough: prefer the repo's own venv script, then PATH.
        cand = repo / ".venv" / "bin" / self.script
        if cand.exists():
            return [str(cand)]
        which = shutil.which(self.script)
        return [which] if which else None

    def ready(self) -> bool:
        return self.resolve_command() is not None


CAPABILITIES: list[Capability] = [
    Capability("code", "Chat / code with the local agent (thandv)",
               "repos/thandv", script="thandv", needs=("ollama",)),
    Capability("build-app", "Autonomously build an app from an idea (local_ai)",
               "repos/local_ai", script="build-app", needs=("ollama",)),
    Capability("vibe", "Interactive vibe-coder (local_ai)",
               "repos/local_ai", script="vibe", needs=("ollama",)),
    Capability("write", "Multi-agent writing / novel pipeline (writer)",
               "repos/writer", script="writer", needs=("ollama",)),
    Capability("audiobook", "Manuscript -> audiobook M4B (audiobook-converter)",
               "audiobook-converter", script="audiobook", needs=("ffmpeg", "espeak-ng")),
    Capability("swe", "Markdown agent team ships software end-to-end (SWE)",
               "SWE", kind="driver", driver="binary/driver/orchestrator_driver.py",
               needs=("anthropic_key",)),
    Capability("content", "Manage agent/skill content (agent-forge)",
               "agent-forge", kind="content"),
]

BY_NAME = {c.name: c for c in CAPABILITIES}


def get(name: str) -> Capability | None:
    return BY_NAME.get(name)


def shared_env(cfg: dict) -> dict:
    """Environment shared with every capability: one model backend + home."""
    env = dict(os.environ)
    env["OLLAMA_HOST"] = cfg.get("ollama_host", "http://127.0.0.1:11434")
    if cfg.get("default_model"):
        env["THANDV_MODEL"] = cfg["default_model"]
    return env
