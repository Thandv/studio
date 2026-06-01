# studio

[![ci](https://github.com/Thandv/studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Thandv/studio/actions/workflows/ci.yml)

One launcher for a **local-first, open-weights AI studio**. It unifies your
existing tools behind a single command, one shared model backend, and one home —
without merging them: each stays an independent repo with its own venv, and
`studio` is a thin dispatcher.

```
                         ┌──────────────── studio ────────────────┐
   one CLI, one config → │ code  build-app  vibe  write  audiobook │ ← capabilities
                         │ swe   content                           │
                         └───────┬───────────────┬─────────────────┘
   thandv (chat/code core) ◄─────┘               └─────► agent-forge (agents/skills supply)
   local_ai (app builder) · writer (prose) · audiobook (M4B) · SWE (agent team)
```

## Capabilities

| Command | Tool | What it does |
| --- | --- | --- |
| `studio code` | [thandv](https://github.com/Thandv/thandv) | Local Claude-style chat/coding agent (personas + skills from agent-forge) |
| `studio build-app "<idea>"` | [local_ai](https://github.com/Thandv/local_ai) | Autonomously build an app from an idea |
| `studio vibe` | [local_ai](https://github.com/Thandv/local_ai) | Interactive vibe-coder |
| `studio write …` | [writer](https://github.com/Thandv/writer-app) | Multi-agent writing / novel pipeline |
| `studio audiobook …` | [audiobook-converter](https://github.com/Thandv/audiobook-converter) | Manuscript → M4B audiobook |
| `studio swe "<idea>"` | [SWE](https://github.com/Thandv/swe-team) | Markdown agent team that ships software (needs `ANTHROPIC_API_KEY`) |
| `studio content …` | [agent-forge](https://github.com/Thandv/agent-forge) | Manage the agent/skill registry (`sync`, `build`, `install`, …) |

Args after the capability pass straight through, so `studio code chat`,
`studio write start`, `studio audiobook render book.md` all work.

### Interactive shell

Run `studio` (no args) or `studio shell` for a single interactive home where the
local agent is the default and the other capabilities are slash-commands:

```
studio> /persona security-auditor
studio> /code                 # hands off to thandv chat, returns here on exit
studio> /write start
studio> /content sync
studio> review this repo for me   # bare text -> one-shot prompt to the local agent
studio> /exit
```

## Quickstart

```bash
./install.sh          # installs the launcher + sets up capabilities (reuses existing venvs)
studio doctor         # check system deps (ollama/ffmpeg/espeak) + capability readiness
studio list
studio code           # start chatting with the local agent
studio code chat --persona security-auditor   # uses an agent-forge persona
studio content sync   # refresh the agent/skill registry from upstreams
```

## How it works

- **Thin dispatcher.** `studio <cap>` resolves the capability to a concrete
  command (preferring each repo's own `.venv`) and shells out, injecting a shared
  environment (`OLLAMA_HOST`, model). No tool is imported into studio.
- **Independent repos.** Each capability keeps its own deps in its own venv —
  no dependency conflicts between e.g. audiobook's torch and writer's streamlit.
- **Shared content.** `studio install` builds agent-forge's `thandv` view and
  installs it, so `studio code` gets the curated personas/skills out of the box.
- **One config.** `~/.studio/config.json` (model backend, home). `studio config`.
- **Stdlib only.** The launcher has zero dependencies.

## Docker

`./docker-build.sh` builds a Linux image (`Dockerfile`) that clones the available
capability repos (thandv, agent-forge, writer, SWE) and runs `studio install`
in-image. Point it at a host/sidecar Ollama:

```bash
./docker-build.sh
docker run --rm -it -e OLLAMA_HOST=http://host.docker.internal:11434 studio doctor
docker run --rm -it -e OLLAMA_HOST=... studio code chat
```

Capability repo URLs are build args (`--local-ai`, `--audiobook`, or override the
`*_URL` args) so forks/private mirrors work. On macOS the model runtime
(Ollama/Metal) runs on the host, so the native `install.sh` path is the
recommended local-first setup; Docker targets Linux/servers. See
`docs/ARCHITECTURE.md`.
