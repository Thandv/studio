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

# --- sandbox: every fixture test runs here, never against the real siblings ---
# Temp HOME/STUDIO_HOME (no real ~/.studio), PATH=/usr/bin:/bin, python by the
# absolute path captured now, and a fresh copy of the launcher so the default
# base (<repo-root>/..) is a temp dir too.
PY="$(command -v python3)"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
mkdir -p "$SB/home"
sb(){ env -i HOME="$SB/home" STUDIO_HOME="$SB/home/.studio" PATH=/usr/bin:/bin LANG=C.UTF-8 "$@"; }
# fake_base <dir>: a launcher copy at <dir>/studio, no siblings yet.
fake_base(){ mkdir -p "$1/studio"; cp -R "$ROOT/studio" "$1/studio/studio"; }
# fake_script <file> [shebang]: an executable stub that records its argv.
fake_script(){
  mkdir -p "$(dirname "$1")"
  printf '%s\nprintf "%%s\\n" "$@" > "$0.argv"\n' "${2:-#!/bin/sh}" > "$1"; chmod +x "$1"
}
sb "$PY" - <<'PY'
import shutil
on_path = [n for n in ("thandv", "writer", "vibe", "build-app", "audiobook") if shutil.which(n)]
assert not on_path, f"real sibling tools on the sandbox PATH: {on_path}"
PY
chk 0 $? "sandbox PATH has no real sibling tools"

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

# --- pinning: every BASE / repo_path() caller resolves under the default base ---
B="$SB/pin"; fake_base "$B"
( cd "$B/studio" && sb "$PY" - "$B" <<'PY'
import sys
from pathlib import Path
from studio import capabilities as caps
from studio.improve import improve
b = Path(sys.argv[1]).resolve()
assert caps.get("audiobook").repo_path() == b / "audiobook-converter"
assert caps.get("swe").repo_path() == b / "SWE"
assert caps.get("content").repo_path() == b / "agent-forge"
assert improve._agent_forge() == b / "agent-forge"            # improve + install + content dispatch
assert improve.resolve_target("studio") == b / "studio"
assert improve.resolve_target("swe") == b / "SWE"
assert improve.resolve_target("some/dir") == b / "some/dir"
assert improve.resolve_target("/abs/dir") == Path("/abs/dir")
print("pinned resolution OK")
PY
); chk 0 $? "pinned: repo_path()/improve resolver under the default base"

# --- STU-1: configurable base + flat sibling layout ---
# full_base <dir>: every sibling present, flat, with a stub in each venv.
full_base(){
  fake_base "$1"
  for s in thandv/.venv/bin/thandv local_ai/.venv/bin/build-app local_ai/.venv/bin/vibe \
           writer/.venv/bin/writer audiobook-converter/.venv/bin/audiobook SWE/.venv/bin/python; do
    fake_script "$1/$s"
  done
  mkdir -p "$1/SWE/binary/driver" "$1/agent-forge/scripts"
  : > "$1/SWE/binary/driver/orchestrator_driver.py"
}
B="$SB/flat"; full_base "$B"
out="$(cd "$B/studio" && sb "$PY" -m studio list 2>&1)"; rc=$?
nf="$(printf '%s\n' "$out" | grep -c 'repo not found')"
under="$(printf '%s\n' "$out" | grep -c "repo: $(cd "$B" && pwd -P)/")"
[ "$rc" -eq 0 ] && [ "$nf" -eq 0 ] && [ "$under" -eq 7 ]; chk 0 $? "default base: list resolves all 7 under <repo-root>/.. (flat), none 'repo not found'"
( cd "$B/studio" && sb "$PY" - "$(cd "$B" && pwd -P)" <<'PY'
import sys
from studio import capabilities as caps
b = sys.argv[1]
assert caps.get("build-app").resolve_command() == [f"{b}/local_ai/.venv/bin/build-app"]
assert caps.get("vibe").resolve_command() == [f"{b}/local_ai/.venv/bin/vibe"]
PY
); chk 0 $? "default base: build-app/vibe -> <base>/local_ai/.venv/bin/{build-app,vibe}"

out="$(sb STUDIO_BASE="$SB/x" "$PY" -m studio list 2>&1)"
[ "$(printf '%s\n' "$out" | grep -c "repo not found: $SB/x/")" -eq 7 ]; chk 0 $? "STUDIO_BASE=<tmp>/x: every capability 'repo not found' naming it"

B="$SB/one"; mkdir -p "$B"; fake_script "$B/writer/.venv/bin/writer"
out="$(sb STUDIO_BASE="$B" "$PY" -m studio list 2>&1)"
[ "$(printf '%s\n' "$out" | grep -c ' ready$')" -eq 1 ] && printf '%s\n' "$out" | grep -q '^  write  *ready$'
chk 0 $? "fake base with one repo: only that capability is ready"

H="$SB/home-tilde"; mkdir -p "$H/b"; fake_script "$H/b/writer/.venv/bin/writer"
sb HOME="$H" STUDIO_BASE='~/b' "$PY" -m studio list 2>&1 | grep -q '^  write  *ready$'
chk 0 $? "STUDIO_BASE expands ~"

# config: base_dir, then a per-capability override; STUDIO_BASE beats base_dir.
CH="$SB/cfg"; mkdir -p "$CH" "$SB/elsewhere"; fake_script "$SB/elsewhere/w/.venv/bin/writer"
printf '{"base_dir": "%s", "repos": {"write": "%s/elsewhere/w"}}\n' "$SB/one" "$SB" > "$CH/config.json"
out="$(sb STUDIO_HOME="$CH" "$PY" -m studio config 2>&1)"
printf '%s\n' "$out" | grep -q "^# resolved base: $SB/one$" \
  && printf '%s\n' "$out" | grep -q "^#   write  *$SB/elsewhere/w$" \
  && printf '%s\n' "$out" | grep -q "^#   code  *$SB/one/thandv$"
chk 0 $? "config: base_dir honoured, override printed by 'studio config'"
sb STUDIO_HOME="$CH" "$PY" -m studio list 2>&1 | grep -q '^  write  *ready$'; chk 0 $? "config: override honoured by 'studio list'"
sb STUDIO_HOME="$CH" STUDIO_BASE="$SB/x" "$PY" -m studio config 2>&1 | grep -q "^# resolved base: $SB/x$"
chk 0 $? "STUDIO_BASE beats config base_dir"

printf '{"repos": {"write": "../outside"}}\n' > "$CH/config.json"
out="$(sb STUDIO_HOME="$CH" STUDIO_BASE="$SB/one" "$PY" -m studio list 2>&1)"
printf '%s\n' "$out" | grep -q "^  write  *bad config: repos.write '../outside' escapes the base"
chk 0 $? "relative override escaping the base is rejected in list"
err="$(sb STUDIO_HOME="$CH" STUDIO_BASE="$SB/one" "$PY" -m studio write 2>&1 >/dev/null)"; rc=$?
[ "$rc" -eq 2 ] && printf '%s' "$err" | grep -q 'config error: repos.write' && ! printf '%s' "$err" | grep -q Traceback
chk 0 $? "dispatching an escaping override: one config error, exit 2, no traceback"
printf '{"repos": {"write": "sub/w"}}\n' > "$CH/config.json"
sb STUDIO_HOME="$CH" STUDIO_BASE="$SB/one" "$PY" -m studio config 2>&1 | grep -q "^#   write  *$SB/one/sub/w$"
chk 0 $? "relative override inside the base is joined to it"

! grep -qE '^\s*(from|import) .*capabilities' studio/config.py; chk 0 $? "config.py does not import capabilities"

echo
if [ "$fails" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$fails FAILED"; fi
exit $((fails>0?1:0))
