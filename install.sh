#!/usr/bin/env bash
# Bootstrap the studio launcher, then set up the capabilities.
#
#   ./install.sh            # install studio + all capabilities + content
#   ./install.sh --no-caps  # install only the studio launcher
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

echo "==> installing the studio launcher (pipx if available, else user pip)"
if command -v pipx >/dev/null; then
  pipx install -e . --force >/dev/null 2>&1 || pip install -e . --user
else
  pip install -e . --user
fi

if [ "${1:-}" = "--no-caps" ]; then
  echo "studio installed. Run: studio doctor"
  exit 0
fi

echo "==> setting up capabilities (reuses existing venvs)"
if command -v studio >/dev/null; then
  studio install
else
  python3 -m studio install
fi

echo
echo "studio ready. Try:  studio doctor   |   studio code   |   studio list"
