"""A small, confined agent loop for the improvement pipeline.

Backend-agnostic (any OpenAI-compatible model). Uses a strict text protocol
instead of vendor function-calling, so it works identically on Ollama and the
free hosted tiers. Every tool is confined to a single working directory (a git
worktree); the only command it can run is the repo's declared test command —
never arbitrary shell, network, or installs. That confinement is the safety
boundary that makes autonomous editing acceptable.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .backends import Backend

PROTOCOL = """\
You act by replying with EXACTLY ONE JSON object and nothing else. Shape:
  {"thought": "...", "action": "<name>", ...args}
Actions:
  {"action":"list_dir","path":"."}
  {"action":"read_file","path":"relative/path"}
  {"action":"write_file","path":"relative/path","content":"<full new file content>"}
  {"action":"run_tests"}
  {"action":"finish","summary":"what you did / concluded"}
Rules: paths are relative to the project root and must stay inside it. Make the
smallest change that achieves the goal. Run tests after editing. When done (or if
blocked), use finish. Only ONE action per reply.\
"""

MAX_OBS = 6000


@dataclass
class RunResult:
    finished: bool = False
    summary: str = ""
    changed: list[str] = field(default_factory=list)
    steps: int = 0
    last_tests_passed: bool | None = None
    transcript: list[dict] = field(default_factory=list)


def _safe(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise ValueError(f"path escapes project root: {rel!r}")
    return p


def _extract_json(text: str) -> dict | None:
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    start = -1
    return None


class Runner:
    def __init__(self, backend: Backend, root: Path, test_cmd: list[str],
                 allow_write: bool = True, max_steps: int = 14):
        self.backend = backend
        self.root = Path(root)
        self.test_cmd = test_cmd
        self.allow_write = allow_write
        self.max_steps = max_steps

    def _run_tests(self) -> tuple[bool, str]:
        try:
            r = subprocess.run(self.test_cmd, cwd=str(self.root),
                               capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"test run error: {e}"
        out = (r.stdout + "\n" + r.stderr)[-MAX_OBS:]
        return r.returncode == 0, out

    def _do(self, act: dict, res: RunResult) -> str:
        name = act.get("action")
        try:
            if name == "list_dir":
                p = _safe(self.root, act.get("path", "."))
                return "\n".join(sorted(x.name + ("/" if x.is_dir() else "")
                                        for x in p.iterdir()))[:MAX_OBS]
            if name == "read_file":
                p = _safe(self.root, act["path"])
                return p.read_text(encoding="utf-8", errors="replace")[:MAX_OBS]
            if name == "write_file":
                if not self.allow_write:
                    return "ERROR: writing is not permitted in this phase"
                p = _safe(self.root, act["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(act.get("content", ""), encoding="utf-8")
                rel = str(p.relative_to(self.root.resolve()))
                if rel not in res.changed:
                    res.changed.append(rel)
                return f"wrote {rel} ({len(act.get('content',''))} bytes)"
            if name == "run_tests":
                ok, out = self._run_tests()
                res.last_tests_passed = ok
                return f"tests {'PASSED' if ok else 'FAILED'}\n{out}"
            if name == "finish":
                res.finished = True
                res.summary = act.get("summary", "")
                return "done"
            return f"ERROR: unknown action {name!r}"
        except (KeyError, ValueError, OSError) as e:
            return f"ERROR: {e}"

    def run(self, system: str, task: str) -> RunResult:
        res = RunResult()
        messages = [
            {"role": "system", "content": system + "\n\n" + PROTOCOL},
            {"role": "user", "content": task},
        ]
        for _ in range(self.max_steps):
            res.steps += 1
            reply = self.backend.chat(messages)
            res.transcript.append({"assistant": reply[:1000]})
            act = _extract_json(reply)
            if not act:
                messages.append({"role": "user",
                                 "content": "Reply with ONE JSON action object only."})
                continue
            obs = self._do(act, res)
            res.transcript.append({"action": act.get("action"), "obs": obs[:500]})
            if res.finished:
                break
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})
            if len(messages) > 24:  # keep context bounded
                messages = messages[:1] + messages[-20:]
        return res
