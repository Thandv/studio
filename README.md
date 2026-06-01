# studio

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
| `studio build-app "<idea>"` | local_ai | Autonomously build an app from an idea |
| `studio vibe` | local_ai | Interactive vibe-coder |
| `studio write …` | writer | Multi-agent writing / novel pipeline |
| `studio audiobook …` | audiobook-converter | Manuscript → M4B audiobook |
| `studio swe "<idea>"` | SWE | Markdown agent team that ships software (needs `ANTHROPIC_API_KEY`) |
| `studio content …` | [agent-forge](https://github.com/Thandv/agent-forge) | Manage the agent/skill registry (`sync`, `build`, `install`, …) |

Args after the capability pass straight through, so `studio code chat`,
`studio write start`, `studio audiobook render book.md` all work.

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

## Docker (later)

`Dockerfile` is an experimental Linux image that bundles the launcher and Python
capabilities. On macOS the model runtime (Ollama/Metal) runs on the host, so the
native `install.sh` path is the recommended local-first setup; Docker targets
Linux/servers. See `docs/ARCHITECTURE.md`.
