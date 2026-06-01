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
Reply with EXACTLY ONE action and nothing else, using this line format:

ACTION: list_dir | read_file | write_file | run_tests | finish
PATH: <relative path>          # for list_dir / read_file / write_file
SUMMARY: <one line>            # for finish only
CONTENT:                       # for write_file ONLY — everything BELOW this line,
<the complete new file content, verbatim, no fences, no escaping>

Rules: ONE action per reply. For write_file put the ENTIRE new file content after
a line that is exactly "CONTENT:" — do not wrap it in quotes or code fences and do
not escape newlines. Paths stay inside the project. Make the smallest change that
achieves the goal. Run tests after editing. Use finish when done or blocked.\
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


_ACTION_RE = re.compile(r"^\s*ACTION:\s*(\w+)", re.MULTILINE)
_PATH_RE = re.compile(r"^\s*PATH:\s*(.+)$", re.MULTILINE)
_SUMMARY_RE = re.compile(r"^\s*SUMMARY:\s*(.+)$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _parse_action(text: str) -> dict | None:
    """Parse the marker protocol (small-model friendly); fall back to JSON.

    The marker form avoids JSON-escaping multi-line file bodies, which small
    local models get wrong — that was why edits never registered.
    """
    m = _ACTION_RE.search(text)
    if not m:
        return _extract_json(text)
    action = m.group(1).strip().lower()
    out: dict = {"action": action}
    pm = _PATH_RE.search(text)
    if pm:
        out["path"] = pm.group(1).strip().strip('"').strip("`")
    if action == "finish":
        sm = _SUMMARY_RE.search(text)
        out["summary"] = sm.group(1).strip() if sm else text[m.end():].strip()[:500]
    if action == "write_file":
        idx = text.find("CONTENT:")
        if idx != -1:
            body = text[idx + len("CONTENT:"):]
            out["content"] = body[1:] if body[:1] == "\n" else body
        else:  # tolerate a fenced block if the model used one
            fm = _FENCE_RE.search(text)
            out["content"] = fm.group(1) if fm else ""
    return out


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
            act = _parse_action(reply)
            if not act or not act.get("action"):
                messages.append({"role": "user",
                                 "content": "Reply with ONE action in the ACTION:/PATH:/CONTENT: format."})
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
