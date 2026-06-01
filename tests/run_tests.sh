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

echo
if [ "$fails" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$fails FAILED"; fi
exit $((fails>0?1:0))
