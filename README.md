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

### Self-improvement (`studio improve`)

A safe, **human-gated** loop that researches, implements, and tests an improvement
to the product itself, then opens a PR (it **never auto-merges**):

```bash
studio improve --dry-run                       # research + plan only (no edits)
studio improve --target studio                 # improve the launcher itself
studio improve --target agent-forge --backend cerebras   # use a bigger free model
studio improve --goal "add a --json flag to studio list"
```

**How it stays safe:** all work happens in an isolated `git worktree` on a fresh
branch (never your working tree); the agent's only command is the repo's test
suite (no arbitrary shell); the diff must pass the agent-forge **security scanner**,
the repo's **tests**, and an **adversarial review** before a PR is opened.

**Compute backends** (`--backend`, all OpenAI-compatible): `ollama` (local,
default) · `groq` / `cerebras` / `openrouter` (free hosted tiers — bigger models,
need an API key) · `custom` (any base URL, e.g. a **Kaggle/Colab + Ollama + ngrok
GPU tunnel** via `STUDIO_IMPROVE_BASE_URL`). `studio doctor` shows what's available.
The driving roles are the agent-forge **`improvement`** domain agents
(researcher → planner → implementer → tester → reviewer).

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

Bare text goes to the local agent exactly as typed (apostrophes and stray quotes
included). A `/command` with an unbalanced quote passes everything after the
command as one argument. If a command fails, the shell prints
`error: <command>: <reason>` and keeps running; Ctrl-C, Ctrl-D, `/exit` and a bare
`exit` leave.

## Quickstart

```bash
./install.sh          # installs the launcher + sets up capabilities (reuses existing venvs)
studio doctor         # check system deps (ollama/ffmpeg/espeak) + capability readiness
studio list
studio code           # start chatting with the local agent
studio code chat --persona security-auditor   # uses an agent-forge persona
studio content sync   # refresh the agent/skill registry from upstreams
```

`studio doctor` reports each capability as ready or as `repo not found: <path>`,
`broken venv: interpreter <path> missing, rebuild the venv` (a venv script whose
shebang points at a deleted interpreter) or `not installed`, and **exits 1 when
any capability is not ready** (0 when all are). Missing system deps (ollama,
ffmpeg, espeak-ng, `ANTHROPIC_API_KEY`) are warnings and do not change the exit
code. `swe` needs its own `SWE/.venv/bin/python` (no fallback to system
`python3`). If a capability cannot be started, studio prints
`cannot launch <cap>: <error>. Run: studio install <cap>` and exits 1.

## How it works

- **Thin dispatcher.** `studio <cap>` resolves the capability to a concrete
  command (preferring each repo's own `.venv`) and shells out, injecting a shared
  environment (`OLLAMA_HOST`, model). No tool is imported into studio.
- **Independent repos.** Each capability keeps its own deps in its own venv —
  no dependency conflicts between e.g. audiobook's torch and writer's streamlit.
- **Shared content.** `studio install` builds agent-forge's `thandv` view and
  installs it, so `studio code` gets the curated personas/skills out of the box.
- **One config.** `~/.studio/config.json` (model backend, home). `studio config`.
- **Where the tools live.** The sibling repos sit flat under one base directory:
  `thandv`, `local_ai`, `writer`, `audiobook-converter`, `SWE`, `agent-forge`.
  The base is `$STUDIO_BASE` if set, else `base_dir` in the config (an absolute
  path), else the directory that contains this studio checkout (`~` is expanded).
  To point one capability elsewhere, set `"repos": {"write": "/path/to/writer"}`
  in the config (absolute, or relative to the base; a relative path may not
  leave the base, symlinks included).
  `studio list` shows each capability's status and repo path; `studio config`
  also prints the resolved base.
- **Stdlib only.** The launcher has zero dependencies.

## Docker

`./docker-build.sh` builds a Linux image (`Dockerfile`) that clones the
capability repos flat under `/opt/Claude` (with `STUDIO_BASE=/opt/Claude`) and
runs `studio install` in-image. The image has not been built or tested yet. Point it at a host/sidecar Ollama:

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
