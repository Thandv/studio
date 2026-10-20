#!/usr/bin/env bash
# Build the studio Docker image. Capability repos are cloned in-image from
# GitHub (override the *_URL build args for forks/mirrors/private remotes)
# into a flat layout under /opt/Claude, with STUDIO_BASE set to it.
#
#   ./docker-build.sh                          # build with defaults
#   ./docker-build.sh --local-ai <git-url>     # also include local_ai
#   ./docker-build.sh --audiobook <git-url>    # also include audiobook-converter
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }

args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --local-ai)  args+=(--build-arg "LOCAL_AI_URL=$2"); shift 2;;
    --audiobook) args+=(--build-arg "AUDIOBOOK_URL=$2"); shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

docker build -t studio "${args[@]}" .
echo
echo "built image 'studio'. Try:"
echo "  docker run --rm -it -e OLLAMA_HOST=http://host.docker.internal:11434 studio doctor"
