# Experimental Linux image for the studio launcher (see docs/ARCHITECTURE.md).
#
# On macOS, prefer the native ./install.sh path — the model runtime
# (Ollama/Metal) runs on the host. This image targets Linux/servers and expects
# an Ollama reachable at OLLAMA_HOST (a sidecar container or the host).
#
# It bundles the launcher + the Python capabilities (each in its own venv). SWE
# (Tauri/Rust) and GPU TTS are out of scope for this base image.
#
#   docker build -t studio .
#   docker run --rm -it -e OLLAMA_HOST=http://host.docker.internal:11434 studio doctor

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/studio
COPY . /opt/studio

# Install the launcher itself (stdlib only).
RUN pip install --no-cache-dir -e .

# Capability repos are expected to be mounted/cloned under /opt and set up via
# `studio install`. Kept out of the base image to stay slim; see ARCHITECTURE.md.

ENV OLLAMA_HOST=http://host.docker.internal:11434
ENTRYPOINT ["studio"]
CMD ["doctor"]
