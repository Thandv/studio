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

Bare text (no slash) is sent to the local agent as a one-shot prompt.
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
        tok = shlex.split(line)
        head, rest = tok[0], tok[1:]
        cmd = head[1:] if head.startswith("/") else head

        if cmd in ("exit", "quit"):
            return 0
        if cmd == "help":
            _help(); continue
        if cmd == "doctor":
            doctor_mod.run(); continue
        if cmd == "list":
            for c in caps.CAPABILITIES:
                print(f"  {'ready' if c.ready() else '     '}  {c.name:<11} {c.summary}")
            continue
        if cmd == "persona":
            if rest:
                persona = rest[0]
                print(f"persona set: {persona} (used by /code)")
            else:
                print(f"persona: {persona or '(default)'}")
            continue

        if cmd in CAP_CMDS:
            args = rest
            if cmd == "code":
                # default to interactive chat; apply the chosen persona
                args = rest or ["chat"]
                if persona and "--persona" not in args:
                    args = args + ["--persona", persona]
            cli.run_capability(cmd, args, cfg)
            continue

        if head.startswith("/"):
            print(f"unknown command: {head} (try /help)")
            continue

        # bare text -> one-shot prompt to the local agent
        args = ["chat", line] + (["--persona", persona] if persona else [])
        cli.run_capability("code", args, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(run())
