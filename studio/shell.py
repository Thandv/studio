"""`studio shell` — an interactive home that makes the capabilities feel like
one app. The local agent (thandv) is the default; everything else is a
slash-command that hands off the terminal and returns you here when it exits.

  studio> /help
  studio> /persona security-auditor
  studio> /code            # hands off to thandv chat, returns here on exit
  studio> /write start
  studio> /audiobook render book.md
  studio> /content sync
  studio> /doctor
  studio> /exit

Bare text (no slash) is sent to the local agent as a one-shot prompt, unchanged.
A command that fails prints `error: <command>: <reason>` and the shell carries on.
"""
from __future__ import annotations

import shlex
import sys

from . import capabilities as caps
from . import cli
from . import config as cfg_mod
from . import doctor as doctor_mod

BANNER = "studio — local AI shell. /help for commands, /exit to leave."

CAP_CMDS = {"code", "build-app", "vibe", "write", "audiobook", "swe", "content"}


def _help() -> None:
    print("commands:")
    print("  /code [text]        local agent (thandv); hands off, returns here")
    for n in ("build-app", "vibe", "write", "audiobook", "swe"):
        c = caps.get(n)
        print(f"  /{n:<16} {c.summary}")
    print("  /content <sub..>    manage agent/skill content (agent-forge)")
    print("  /persona <name>     set the persona used by /code")
    print("  /doctor  /list  /help  /exit")
    print("  (bare text -> one-shot prompt to the local agent)")


def _parse(line: str) -> tuple[str, list[str]]:
    """Split '/cmd args' into ('cmd', args). An unbalanced quote falls back to
    whitespace: the remainder after the command is passed on as one raw argument."""
    try:
        tok = shlex.split(line)
    except ValueError:
        tok = line.split(maxsplit=1)
    return tok[0][1:], tok[1:]


def _command(cmd: str, rest: list[str], persona: str, cfg: dict) -> str:
    """Run one /command; returns the (possibly changed) persona."""
    if cmd == "help":
        _help()
    elif cmd == "doctor":
        doctor_mod.run()
    elif cmd == "list":
        cli.print_list()
    elif cmd == "persona":
        if rest:
            persona = rest[0]
            print(f"persona set: {persona} (used by /code)")
        else:
            print(f"persona: {persona or '(default)'}")
    elif cmd in CAP_CMDS:
        args = rest
        if cmd == "code":
            # default to interactive chat; apply the chosen persona
            args = rest or ["chat"]
            if persona and "--persona" not in args:
                args = args + ["--persona", persona]
        cli.run_capability(cmd, args, cfg)
    else:
        print(f"unknown command: /{cmd} (try /help)")
    return persona


def run() -> int:
    cfg = cfg_mod.load()
    persona = cfg.get("persona", "")
    print(BANNER)
    while True:
        try:
            line = input("studio> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("exit", "quit"):
            return 0
        cmd = "code"
        try:
            if line.startswith("/"):
                cmd, rest = _parse(line)
                if cmd in ("exit", "quit"):
                    return 0
                persona = _command(cmd, rest, persona, cfg)
            else:
                # bare text -> one-shot prompt to the local agent, the raw line intact
                args = ["chat", line] + (["--persona", persona] if persona else [])
                cli.run_capability("code", args, cfg)
        except Exception as e:  # noqa: BLE001 - one failing command must not end the session
            print(f"error: {cmd}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(run())
