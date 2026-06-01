"""studio — one launcher for the local AI studio.

  studio                          interactive shell (default; /help inside)
  studio shell                    interactive shell explicitly
  studio <capability> [args...]   run a capability (passes args straight through)
  studio doctor                   check system deps + capability readiness
  studio install [capability]     set up capabilities (venvs) + content
  studio list                     list capabilities and readiness
  studio config                   show config (~/.studio/config.json)

Capabilities: code, build-app, vibe, write, audiobook, swe, content.
Every capability shares one model backend (OLLAMA_HOST) and home.
"""
from __future__ import annotations

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


def _dispatch_content(rest: list[str]) -> int:
    af = caps.get("content").repo_path()
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
    return subprocess.run(["python3", str(af / script), *args], cwd=str(af)).returncode


def _dispatch(cap: caps.Capability, rest: list[str], cfg: dict) -> int:
    command = cap.resolve_command()
    if not command:
        print(f"'{cap.name}' is not installed. Run: studio install {cap.name}", file=sys.stderr)
        return 1
    missing = [d for d in cap.needs if d != "anthropic_key" and __import__("shutil").which(d) is None]
    if missing:
        print(f"warning: '{cap.name}' needs missing system dep(s): {', '.join(missing)}",
              file=sys.stderr)
    return subprocess.run([*command, *rest], env=caps.shared_env(cfg)).returncode


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
        for c in caps.CAPABILITIES:
            print(f"  {'ready' if c.ready() else '     ':<6} {c.name:<11} {c.summary}")
        return 0
    if cmd == "config":
        print(f"# {cfg_mod.CONFIG_PATH}")
        print(__import__("json").dumps(cfg_mod.load(), indent=2))
        return 0

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
