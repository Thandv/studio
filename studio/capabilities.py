"""Capability registry — the map from `studio <name>` to an underlying tool.

Each sibling project stays independent (its own repo + venv). studio is a thin
dispatcher: it resolves a capability to a concrete command and shells out,
passing a shared environment (model backend, home). Nothing here imports the
tools — it only locates and runs them.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# This launcher's own repo root; by default its siblings live next to it.
STUDIO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = STUDIO_ROOT.parent
READY = "ready"


# pip's long-path launcher: "#!/bin/sh" then a line '''exec' "<python>" "$0" "$@".
# The path must end inside the bytes read: a cut-off path proves nothing.
_TRAMPOLINE = re.compile(r"""^'''exec' (?:"([^"]+)"|([^\s"]\S*)(?=\s))""", re.MULTILINE)
_ENV_OPTS_WITH_ARG = {"-u", "--unset", "-C", "--chdir"}


def _broken(interpreter: str) -> str:
    return f"broken venv: interpreter {interpreter} missing, rebuild the venv"


def _env_program(args: list[str]) -> str | None:
    """The program a '#!/usr/bin/env ...' line runs: skips options (and the
    argument of -u/-C) and NAME=VALUE assignments."""
    words = iter(args)
    for word in words:
        if word in _ENV_OPTS_WITH_ARG:
            next(words, None)
        elif not word.startswith("-") and "=" not in word:
            return word
    return None


def script_problem(script: Path) -> str | None:
    """Why `script` cannot start, judged from its first 256 bytes, or None if it can.

    Handles '#!/abs/interp [args]', '#!/usr/bin/env [-S] X' (X looked up on
    PATH) and pip's '#!/bin/sh' trampoline. No shebang means a binary or a
    script the OS runs itself: fine.
    """
    try:
        with open(script, "rb") as f:
            head = f.read(256).decode("utf-8", "replace")
    except OSError as e:
        return f"cannot read {script}: {e.strerror or e}"
    if not head.startswith("#!"):
        return None
    words = head[2:].split("\n", 1)[0].split()
    if not words:
        return f"empty shebang in {script}"
    interp, args = words[0], words[1:]
    if not Path(interp).is_file():
        return _broken(interp)
    if Path(interp).name == "env":
        prog = _env_program(args)
        if prog is not None and shutil.which(prog) is None:
            return _broken(f"{prog} (via {interp})")
    tramp = _TRAMPOLINE.search(head)
    if tramp:
        target = tramp.group(1) or tramp.group(2)
        if not Path(target).is_file():
            return _broken(target)
    return None


class ConfigError(ValueError):
    """A base_dir / repos setting in the config that cannot be used."""


def base(cfg: dict | None = None) -> Path:
    """Directory holding the sibling repos: $STUDIO_BASE, then cfg base_dir, then default."""
    env = os.environ.get("STUDIO_BASE")
    if env:
        return Path(env).expanduser()
    cfg = config.load() if cfg is None else cfg
    if cfg.get("base_dir"):
        configured = Path(cfg["base_dir"]).expanduser()
        if not configured.is_absolute():
            raise ConfigError(f"base_dir '{cfg['base_dir']}' must be an absolute path")
        return configured
    return DEFAULT_BASE


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    repo: str                      # default path relative to base()
    kind: str = "passthrough"      # passthrough | driver | content
    script: str = ""               # console-script name (passthrough)
    driver: str = ""               # path to a python driver, relative to repo (driver)
    needs: tuple[str, ...] = ()     # required system deps / markers

    def repo_path(self, cfg: dict | None = None) -> Path:
        """This capability's repo: a cfg['repos'][name] override, else base()/repo.

        Raises ConfigError for a malformed override or a relative one that
        escapes the base.
        """
        cfg = config.load() if cfg is None else cfg
        root = base(cfg)
        overrides = cfg.get("repos") or {}
        if not isinstance(overrides, dict):
            raise ConfigError("'repos' must map capability names to paths")
        override = overrides.get(self.name)
        if override is None:
            return root / self.repo
        if not isinstance(override, str) or not override:
            raise ConfigError(f"repos.{self.name} must be a non-empty path string")
        path = Path(override).expanduser()
        if path.is_absolute():
            return path
        joined = Path(os.path.normpath(root / path))
        if not joined.is_relative_to(os.path.normpath(root)):
            raise ConfigError(f"repos.{self.name} '{override}' escapes the base {root}")
        return joined

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
            if drv.exists() and py.exists():
                return [str(py), str(drv)]
            return None
        if self.kind == "content":
            py3 = shutil.which("python3")  # studio runs agent-forge scripts directly
            return [py3] if py3 else None
        # passthrough: prefer the repo's own venv script, then PATH.
        cand = repo / ".venv" / "bin" / self.script
        if cand.exists():
            return [str(cand)]
        which = shutil.which(self.script)
        return [which] if which else None

    def status(self) -> str:
        """The single readiness verdict: 'ready', 'repo not found: <path>',
        'broken venv: ...', 'not executable: <path>', 'empty shebang in <path>',
        'cannot read <path>: <why>', 'not installed', or 'bad config: <why>'."""
        try:
            repo = self.repo_path()
        except ConfigError as e:
            return f"bad config: {e}"
        if not repo.exists():
            return f"repo not found: {repo}"
        py = self.venv_python()
        if self.kind == "driver" and py.is_symlink() and not py.exists():
            return _broken(os.path.realpath(py))
        command = self.resolve_command()
        if command is None:
            return "not installed"
        if self.kind == "passthrough":
            if not os.access(command[0], os.X_OK):
                return f"not executable: {command[0]}"
            return script_problem(Path(command[0])) or READY
        return READY

    def ready(self) -> bool:
        return self.status() == READY


CAPABILITIES: list[Capability] = [
    Capability("code", "Chat / code with the local agent (thandv)",
               "thandv", script="thandv", needs=("ollama",)),
    Capability("build-app", "Autonomously build an app from an idea (local_ai)",
               "local_ai", script="build-app", needs=("ollama",)),
    Capability("vibe", "Interactive vibe-coder (local_ai)",
               "local_ai", script="vibe", needs=("ollama",)),
    Capability("write", "Multi-agent writing / novel pipeline (writer)",
               "writer", script="writer", needs=("ollama",)),
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
