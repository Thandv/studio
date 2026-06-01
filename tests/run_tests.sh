#!/usr/bin/env bash
# Offline smoke tests for the studio launcher (no model, no network).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"
fails=0
pass(){ echo "  PASS: $1"; }
fail(){ echo "  FAIL: $1"; fails=$((fails+1)); }
chk(){ if [ "$1" -eq "$2" ]; then pass "$3"; else fail "$3 (want exit $1 got $2)"; fi; }

python3 -m studio --help >/dev/null 2>&1; chk 0 $? "studio --help"
python3 -m studio list   >/dev/null 2>&1; chk 0 $? "studio list"
python3 -m studio doctor >/dev/null 2>&1; chk 0 $? "studio doctor"
python3 -m studio config >/dev/null 2>&1; chk 0 $? "studio config"
python3 -m studio totally-not-a-cap >/dev/null 2>&1; chk 2 $? "unknown capability -> exit 2"
printf '/help\n/list\n/exit\n' | python3 -m studio shell >/dev/null 2>&1; chk 0 $? "shell /help /list /exit"
printf '' | python3 -m studio shell >/dev/null 2>&1; chk 0 $? "shell EOF exits clean"

python3 - <<'PY'
import sys
from studio import capabilities as c
names = {x.name for x in c.CAPABILITIES}
assert {"code","build-app","vibe","write","audiobook","swe","content"} <= names, names
# resolver returns a list or None, never raises
for cap in c.CAPABILITIES:
    r = cap.resolve_command()
    assert r is None or isinstance(r, list)
# shared env injects the model backend
env = c.shared_env({"ollama_host":"http://x:1"})
assert env["OLLAMA_HOST"] == "http://x:1"
print("registry + resolver + shared_env OK")
PY
chk 0 $? "registry/resolver/env unit checks"

python3 - <<'PY'
import sys, tempfile, subprocess
sys.path.insert(0, ".")
from pathlib import Path
from studio.improve import backends, improve
from studio.improve.runner import _safe, _extract_json, _parse_action

# backends: ollama always resolves; hosted requires a key; availability map
b = backends.resolve("ollama", None, "http://127.0.0.1:11434")
assert b.base_url.endswith("/v1") and b.model
try:
    backends.resolve("groq", None, "x"); raise SystemExit("groq should need a key")
except ValueError:
    pass
assert backends.available("x")["ollama"] is True

# runner: path confinement + tolerant JSON action parsing
try:
    _safe(Path("/tmp"), "../etc/passwd"); raise SystemExit("traversal not blocked")
except ValueError:
    pass
assert _extract_json('ok {"action":"finish","summary":"s"} end')["action"] == "finish"

# marker protocol: multi-line file body without JSON escaping (the small-model fix)
w = _parse_action("ACTION: write_file\nPATH: a/b.py\nCONTENT:\nline1\nline2\n")
assert w["action"] == "write_file" and w["path"] == "a/b.py" and w["content"] == "line1\nline2\n", w
assert _parse_action("ACTION: run_tests")["action"] == "run_tests"
assert _parse_action("ACTION: finish\nSUMMARY: did it")["summary"] == "did it"
assert _parse_action('{"action":"read_file","path":"x"}')["action"] == "read_file"  # json fallback

# improve helpers: test-cmd detection + target resolution
assert improve.detect_test_cmd(Path(".")) == ["bash", "tests/run_tests.sh"]
assert improve.resolve_target("studio").name == "studio"

# worktree isolation on a throwaway repo (proves edits never touch the live tree)
d = Path(tempfile.mkdtemp())
for c in (["init", "-q", str(d)], ["-C", str(d), "config", "user.email", "t@t"],
          ["-C", str(d), "config", "user.name", "t"]):
    subprocess.run(["git", *c], check=True)
(d / "f.txt").write_text("hi")
subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(d), "commit", "-qm", "init"], check=True)
wt = improve.make_worktree(d, "improve/test")
assert wt.exists() and (wt / "f.txt").exists()
(wt / "g.txt").write_text("new")
assert "g.txt" in improve.changed_files(wt)
improve.remove_worktree(d, wt)
print("improve internals OK")
PY
chk 0 $? "improve internals (backends/runner/worktree isolation)"

echo
if [ "$fails" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$fails FAILED"; fi
exit $((fails>0?1:0))
