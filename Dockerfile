# Linux image for the studio launcher: clones the available capability repos,
# installs each into its own venv, and bakes in the launcher.
#
# On macOS prefer the native ./install.sh path (Ollama/Metal runs on the host).
# This image targets Linux/servers and talks to an Ollama at OLLAMA_HOST (a
# sidecar container or the host). Build/run:
#
#   docker build -t studio .
#   docker run --rm -it -e OLLAMA_HOST=http://host.docker.internal:11434 studio doctor
#   docker run --rm -it -e OLLAMA_HOST=... studio code chat
#
# All six capability repos default to their public Thandv remotes; override any
# *_URL build arg for forks / private mirrors.

FROM python:3.12-slim

ARG THANDV_URL=https://github.com/Thandv/thandv
ARG AGENTFORGE_URL=https://github.com/Thandv/agent-forge
ARG WRITER_URL=https://github.com/Thandv/writer-app
ARG SWE_URL=https://github.com/Thandv/swe-team
ARG LOCAL_AI_URL=https://github.com/Thandv/local_ai
ARG AUDIOBOOK_URL=https://github.com/Thandv/audiobook-converter

RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential ffmpeg espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Flat sibling layout under one base, named as studio's registry expects;
# STUDIO_BASE points the launcher at it.
WORKDIR /opt/Claude
ENV STUDIO_BASE=/opt/Claude
RUN set -eux; \
    git clone --depth 1 "$THANDV_URL"     thandv; \
    git clone --depth 1 "$AGENTFORGE_URL" agent-forge; \
    git clone --depth 1 "$WRITER_URL"     writer; \
    git clone --depth 1 "$SWE_URL"        SWE; \
    if [ -n "$LOCAL_AI_URL" ];  then git clone --depth 1 "$LOCAL_AI_URL"  local_ai; fi; \
    if [ -n "$AUDIOBOOK_URL" ]; then git clone --depth 1 "$AUDIOBOOK_URL" audiobook-converter; fi

# Launcher (stdlib only).
COPY . /opt/Claude/studio
RUN pip install --no-cache-dir -e /opt/Claude/studio

# Per-repo venvs + agent-forge content. Tolerant: a heavy capability that fails
# to build doesn't fail the image — `studio doctor` will report it.
RUN studio install || true

ENV OLLAMA_HOST=http://host.docker.internal:11434
ENTRYPOINT ["studio"]
CMD ["doctor"]
