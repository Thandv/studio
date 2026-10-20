"""studio — one launcher for the local AI studio.

  studio                          interactive shell (default; /help inside)
  studio shell                    interactive shell explicitly
  studio <capability> [args...]   run a capability (passes args straight through)
  studio doctor                   check system deps + capability readiness
  studio install [capability]     set up capabilities (venvs) + content
  studio improve [--target ..]    safe self-improvement loop (research->test->PR)
  studio list                     list capabilities, readiness and repo paths
  studio config                   show config, the resolved base and repo paths

Capabilities: code, build-app, vibe, write, audiobook, swe, content.
Every capability shares one model backend (OLLAMA_HOST) and home.
"""
from __future__ import annotations

import json
import subprocess
import sys

from . import capabilities as caps
from . import config as cfg_mod
from . import doctor as doctor_mod
from . import install as install_mod

__version__ = "0.1.0"

CONTENT_SCRIPTS = {
    "sync": "scripts/sync.py",
    "build": "scripts/build.py",
    "install": "scripts/install.py",
    "validate": "scripts/validate.py",
    "catalog": "scripts/catalog_site.py",
    "split": "scripts/split.py",
    "marketplace": "scripts/build_marketplace.py",
}


def _usage() -> None:
    print(__doc__.strip())
    print("\ncapabilities:")
    for c in caps.CAPABILITIES:
        ready = "  " if c.ready() else " !"
        print(f" {ready} {c.name:<11} {c.summary}")
    print("\n('!' = not installed yet — run `studio install <name>`)")


def _repo_label(cap: caps.Capability, cfg: dict | None = None) -> str:
    try:
        return str(cap.repo_path(cfg))
    except caps.ConfigError as e:
        return f"(bad config: {e})"


def print_list() -> None:
    """Each capability's status() and repo path; shared by `studio list` and the shell."""
    for c in caps.CAPABILITIES:
        print(f"  {c.name:<11} {c.status()}")
        print(f"  {'':<11} repo: {_repo_label(c)}")


def _show_config() -> None:
    cfg = cfg_mod.load()
    print(f"# {cfg_mod.CONFIG_PATH}")
    print(json.dumps(cfg, indent=2))
    print(f"\n# resolved base: {caps.base(cfg)}")
    for c in caps.CAPABILITIES:
        print(f"#   {c.name:<11} {_repo_label(c, cfg)}")


def _launch(name: str, command: list[str], *, cwd: str | None = None,
            env: dict[str, str] | None = None) -> int:
    """Run a capability's command; a launch failure is one line, not a traceback."""
    try:
        return subprocess.run(command, cwd=cwd, env=env).returncode
    except OSError as e:
        print(f"cannot launch {name}: {e}. Run: studio install {name}", file=sys.stderr)
        return 1


def _dispatch_content(rest: list[str]) -> int:
    content = caps.BY_NAME["content"]
    af = content.repo_path()
    if not af.exists():
        print(f"agent-forge not found at {af}", file=sys.stderr)
        return 1
    if not rest or rest[0] in ("-h", "--help", "help"):
        print("studio content <sub> [args]\n  subcommands: " + ", ".join(CONTENT_SCRIPTS))
        return 0
    sub, args = rest[0], rest[1:]
    script = CONTENT_SCRIPTS.get(sub)
    if not script:
        print(f"unknown content subcommand: {sub}\n  known: {', '.join(CONTENT_SCRIPTS)}")
        return 2
    python = content.resolve_command()
    if not python:
        print("cannot launch content: python3 not found on PATH", file=sys.stderr)
        return 1
    return _launch("content", [*python, str(af / script), *args], cwd=str(af))


def _dispatch(cap: caps.Capability, rest: list[str], cfg: dict) -> int:
    command = cap.resolve_command()
    if not command:
        print(f"'{cap.name}' is not installed. Run: studio install {cap.name}", file=sys.stderr)
        return 1
    missing = [d for d in cap.needs if d != "anthropic_key" and __import__("shutil").which(d) is None]
    if missing:
        print(f"warning: '{cap.name}' needs missing system dep(s): {', '.join(missing)}",
              file=sys.stderr)
    return _launch(cap.name, [*command, *rest], env=caps.shared_env(cfg))


def run_capability(name: str, rest: list[str], cfg: dict | None = None) -> int:
    """Resolve and run a capability by name. Reused by the CLI and the shell."""
    cfg = cfg or cfg_mod.load()
    cap = caps.get(name)
    if cap is None:
        print(f"unknown capability: {name}", file=sys.stderr)
        return 2
    if cap.kind == "content":
        return _dispatch_content(rest)
    return _dispatch(cap, rest, cfg)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except caps.ConfigError as e:
        print(f"studio: config error: {e} (fix {cfg_mod.CONFIG_PATH})", file=sys.stderr)
        return 2


def _main(argv: list[str] | None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        _usage()
        return 0
    if not argv or argv[0] == "shell":
        from . import shell
        return shell.run()
    cmd, rest = argv[0], argv[1:]

    if cmd in ("-V", "--version", "version"):
        print(f"studio {__version__}")
        return 0
    if cmd == "doctor":
        return doctor_mod.run()
    if cmd == "install":
        return install_mod.run(only=rest[0] if rest else None)
    if cmd in ("list", "ls"):
        print_list()
        return 0
    if cmd == "config":
        _show_config()
        return 0
    if cmd == "improve":
        import argparse
        from .improve import improve as improve_mod
        ap = argparse.ArgumentParser(prog="studio improve",
                                     description="Safe, human-gated self-improvement loop.")
        cfg = cfg_mod.load()
        ap.add_argument("--target", default="studio", help="capability name, repo path, or 'studio'")
        ap.add_argument("--goal", default="", help="skip research; improve this specifically")
        ap.add_argument("--backend", default=None,
                        choices=["ollama", "groq", "cerebras", "openrouter", "custom"])
        ap.add_argument("--model", default=None)
        ap.add_argument("--timeout", type=int, default=None, help="per model-call seconds")
        ap.add_argument("--max-iters", type=int, default=14)
        ap.add_argument("--dry-run", action="store_true", help="research+plan only; no edits, no PR")
        ap.add_argument("--merge", action="store_true", help="merge the PR if all gates pass (off by default)")
        ap.add_argument("--keep", action="store_true", help="keep the worktree after the run")
        a = ap.parse_args(rest)
        return improve_mod.run(
            target=a.target, goal=a.goal,
            backend=a.backend or cfg.get("improve_backend", "ollama"),
            model=a.model or (cfg.get("improve_model") or None),
            timeout=a.timeout or int(cfg.get("improve_timeout", 300)),
            max_iters=a.max_iters, dry_run=a.dry_run, merge=a.merge, keep=a.keep)

    cap = caps.get(cmd)
    if cap is None:
        print(f"unknown command/capability: {cmd}\n", file=sys.stderr)
        _usage()
        return 2
    if cap.kind == "content":
        return _dispatch_content(rest)
    return _dispatch(cap, rest, cfg_mod.load())


if __name__ == "__main__":
    raise SystemExit(main())
