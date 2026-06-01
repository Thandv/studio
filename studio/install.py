"""`studio install` — make capabilities runnable, share one model backend.

For each capability's repo: reuse an existing `.venv`, else create one and
`pip install -e` the package. Then install agent-forge content into Thandv so
the curated personas/skills are available to `studio code`. Idempotent.

Never executes vendored/registry content; only sets up environments and runs
each project's own packaging. Honors --capability to scope the work.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import capabilities as caps
from . import config as cfg_mod


def _venv_python(repo: Path) -> Path:
    return repo / ".venv" / "bin" / "python"


def _ensure_venv(repo: Path, editable: bool = True) -> bool:
    py = _venv_python(repo)
    if not py.exists():
        print(f"    creating venv: {repo}/.venv")
        r = subprocess.run([sys.executable, "-m", "venv", str(repo / ".venv")])
        if r.returncode != 0:
            return False
    if editable:
        print(f"    pip install -e {repo.name}")
        r = subprocess.run([str(py), "-m", "pip", "install", "-q", "-e", str(repo)])
        return r.returncode == 0
    return True


def _install_capability(c: caps.Capability) -> str:
    repo = c.repo_path()
    if not repo.exists():
        return "missing-repo"
    if c.kind == "content":
        return "n/a (content)"
    if c.ready():
        return "already ready"
    ok = _ensure_venv(repo, editable=(c.kind != "driver"))
    if c.kind == "driver":
        # SWE driver needs the Anthropic SDK in its venv.
        py = _venv_python(repo)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "anthropic"])
    return "installed" if (ok and c.ready()) else "FAILED"


def _install_content(cfg: dict) -> str:
    af = (caps.get("content") or caps.CAPABILITIES[-1]).repo_path()
    if not af.exists():
        return "agent-forge not found"
    view = cfg.get("agent_forge_install", "thandv")
    subprocess.run(["python3", str(af / "scripts" / "build.py"), "--tool", view], cwd=str(af))
    subprocess.run(["python3", str(af / "scripts" / "install.py"),
                    "--tool", view, "--copy"], cwd=str(af))
    return f"agent-forge '{view}' content installed"


def run(only: str | None = None) -> int:
    cfg = cfg_mod.load()
    cfg_mod.save(cfg)  # materialize ~/.studio/config.json
    print(f"studio install (home={cfg_mod.STUDIO_HOME})\n" + "=" * 40)
    targets = [caps.get(only)] if only else caps.CAPABILITIES
    if only and targets[0] is None:
        print(f"unknown capability: {only}")
        return 1
    for c in targets:
        if c.kind == "content":
            continue
        print(f"  {c.name}:")
        print(f"    -> {_install_capability(c)}")
    if not only or only == "content" or only == "code":
        print("  content:")
        print(f"    -> {_install_content(cfg)}")
    print("\ndone. Run `studio doctor` to verify.")
    return 0
