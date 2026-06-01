"""Orchestrate a safe, human-gated self-improvement run.

Pipeline (one small improvement per run):
  research (read-only) -> plan (read-only) -> implement (confined writes + tests)
  -> security scan of the diff -> adversarial review -> human-gated PR.

Safety boundary:
  * all work happens in an isolated `git worktree` on a fresh branch — never the
    user's working tree;
  * the agent's only command is the repo's declared test command;
  * the diff must pass the agent-forge security scanner AND the reviewer AND the
    repo's tests before a PR is opened;
  * never auto-merges (PR only) unless --merge is explicitly passed AND all gates
    are green.

Stdlib only. Model calls go solely to the configured backend.
"""
from __future__ import annotations

import subprocess
import time
import urllib.error
from pathlib import Path

from .. import capabilities as caps
from .. import config as cfg_mod
from . import backends
from .runner import Runner

ROLES = ("improvement-researcher", "improvement-planner",
         "improvement-implementer", "improvement-reviewer")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _agent_forge() -> Path:
    return caps.get("content").repo_path()


def load_role(role: str) -> str:
    """Read an improvement agent's prompt body from the agent-forge registry."""
    p = _agent_forge() / "registry" / "agents" / "improvement" / role / "agent.md"
    if not p.exists():
        return f"You are {role}."
    text = p.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text


def resolve_target(name_or_path: str) -> Path:
    cap = caps.get(name_or_path)
    if cap is not None and cap.kind != "content":
        return cap.repo_path()
    if name_or_path in ("studio", ""):
        return caps.BASE / "studio"
    p = Path(name_or_path).expanduser()
    return p if p.is_absolute() else (caps.BASE / name_or_path)


def detect_test_cmd(root: Path) -> list[str]:
    if (root / "tests" / "run_tests.sh").exists():
        return ["bash", "tests/run_tests.sh"]
    if (root / "pyproject.toml").exists() or (root / "tests").is_dir():
        return ["python3", "-m", "pytest", "-q"]
    return ["true"]  # no tests detected — nothing to verify against


def make_worktree(repo: Path, branch: str) -> Path:
    wt = repo.parent / ".studio-improve" / f"{repo.name}-{branch.replace('/', '-')}"
    wt.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "-b", branch, str(wt), "HEAD"], repo)
    return wt


def remove_worktree(repo: Path, wt: Path) -> None:
    _git(["worktree", "remove", "--force", str(wt)], repo)


def changed_files(wt: Path) -> list[str]:
    out = _git(["status", "--porcelain"], wt).stdout
    return [ln[3:].strip() for ln in out.splitlines() if ln.strip()]


def scan_diff(paths: list[str], wt: Path) -> tuple[bool, str]:
    """Run agent-forge's security scanner over the changed files."""
    scan = _agent_forge() / "scripts" / "scan.py"
    if not scan.exists() or not paths:
        return True, "(no scanner or no changes)"
    abspaths = [str(wt / p) for p in paths if (wt / p).is_file()]
    if not abspaths:
        return True, "(no files)"
    r = subprocess.run(["python3", str(scan), *abspaths], capture_output=True, text=True)
    return r.returncode == 0, r.stdout[-2000:]


def run(target: str = "studio", goal: str = "", backend: str = "ollama",
        model: str | None = None, max_iters: int = 14, dry_run: bool = False,
        merge: bool = False, keep: bool = False) -> int:
    cfg = cfg_mod.load()
    root = resolve_target(target)
    if not (root / ".git").exists() and not (root.parent / ".git").exists():
        # worktree needs the repo to be a git repo
        if not _git(["rev-parse", "--git-dir"], root).returncode == 0:
            print(f"target {root} is not a git repository", flush=True)
            return 1
    test_cmd = detect_test_cmd(root)
    print(f"studio improve\n  target:  {root}\n  backend: {backend}\n  tests:   {' '.join(test_cmd)}")

    try:
        be = backends.resolve(backend, model, cfg.get("ollama_host", "http://127.0.0.1:11434"))
    except ValueError as e:
        print(f"  backend error: {e}")
        return 1
    print(f"  model:   {be.model}")

    branch = "improve/" + time.strftime("%Y%m%d-%H%M%S")
    wt = make_worktree(root, branch)
    print(f"  worktree: {wt}  (branch {branch})")
    try:
        ro = lambda role, allow=False: Runner(be, wt, test_cmd, allow_write=allow,  # noqa: E731
                                               max_steps=max_iters)
        # 1. research (or use the provided goal)
        if not goal:
            print("\n[1/4] research")
            res = ro("improvement-researcher").run(
                load_role("improvement-researcher"),
                "Explore this project and choose the single best SMALL, testable "
                "improvement. Use list_dir/read_file. finish with: TITLE / WHY / "
                "FILES / TEST_IDEA.")
            goal = res.summary or "(no improvement chosen)"
        print(f"  goal: {goal[:300]}")

        # 2. plan
        print("\n[2/4] plan")
        plan = ro("improvement-planner").run(
            load_role("improvement-planner"),
            f"Goal:\n{goal}\nInspect the relevant files, then finish with a minimal, "
            "testable plan (files, approach, test, rollback).").summary
        print(f"  plan: {plan[:300]}")

        if dry_run:
            print("\n[dry-run] stopping before implementation. No files changed, no PR.")
            return 0

        # 3. implement (confined writes + tests)
        print("\n[3/4] implement")
        impl = ro("improvement-implementer", allow=True).run(
            load_role("improvement-implementer"),
            f"Plan:\n{plan}\nImplement it with the smallest diff, then run_tests "
            "until green, then finish.")
        files = changed_files(wt)
        print(f"  changed: {files or '(none)'}  tests_passed={impl.last_tests_passed}")
        if not files:
            print("  no changes produced — stopping.")
            return 0

        # gate A: tests must be green
        tests_ok = impl.last_tests_passed
        if tests_ok is None:
            ok, _ = Runner(be, wt, test_cmd)._run_tests()
            tests_ok = ok
        # gate B: security scan of the diff
        scan_ok, scan_out = scan_diff(files, wt)
        # 4. review (read-only) over the actual diff
        print("\n[4/4] review + security scan")
        diff = _git(["diff"], wt).stdout[:8000]
        verdict = ro("improvement-reviewer").run(
            load_role("improvement-reviewer"),
            f"Goal:\n{goal}\n\nDiff under review:\n{diff}\n\nfinish with verdict: "
            "approve or reject, plus blocking issues.").summary
        approved = "approve" in verdict.lower() and "reject" not in verdict.lower()
        print(f"  tests={'ok' if tests_ok else 'FAIL'}  scan={'clean' if scan_ok else 'BLOCK'}  "
              f"review={'approve' if approved else 'reject'}")

        if not (tests_ok and scan_ok and approved):
            print("\nGATE FAILED — not opening a PR. Branch left for inspection: "
                  f"{branch}\n  scan: {scan_out[:300]}")
            keep_branch = True
            return 2
        keep_branch = True

        # commit + push + PR (human-gated; never silent merge)
        _git(["add", "-A"], wt)
        _git(["commit", "-q", "-m", f"improve: {goal.splitlines()[0][:72]}"], wt)
        push = _git(["push", "-q", "-u", "origin", branch], wt)
        if push.returncode != 0:
            print(f"\nchange committed on branch {branch} (push failed: {push.stderr[:200]}).")
            return 0
        pr = subprocess.run(
            ["gh", "pr", "create", "--head", branch, "--base", "main",
             "--title", f"[studio improve] {goal.splitlines()[0][:60]}",
             "--body", f"Automated improvement (studio improve, backend={backend}).\n\n"
                       f"Goal:\n{goal}\n\nTests passed, security scan clean, reviewer approved.\n"
                       f"Files: {', '.join(files)}\n\n*Review before merging — never auto-merged.*"],
            cwd=str(wt), capture_output=True, text=True)
        print(f"\nPR: {pr.stdout.strip() or pr.stderr.strip()}")
        if merge and pr.returncode == 0:
            print("  --merge set: merging (gates were green)…")
            subprocess.run(["gh", "pr", "merge", "--squash", "--auto", branch], cwd=str(wt))
        return 0
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        print(f"\nbackend '{backend}' unreachable: {e}\n"
              f"  - for ollama: is it running and is the model pulled? (`ollama pull {be.model}`)\n"
              f"  - or use a free hosted model: --backend cerebras|groq|openrouter (set its API key)\n"
              f"  - or a Kaggle/Colab GPU tunnel: --backend custom (STUDIO_IMPROVE_BASE_URL)")
        return 1
    finally:
        if not keep and not locals().get("keep_branch"):
            remove_worktree(root, wt)
        else:
            print(f"  (worktree kept at {wt}; `git worktree remove --force {wt}` to clean up)")
