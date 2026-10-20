# Architecture

studio is a **dispatcher**, not a framework. It owns no AI logic; it locates and
runs the independent tools you already have, with one shared config.

```
studio/
  studio/
    cli.py           # arg dispatch: meta commands + capability pass-through
    capabilities.py  # the registry: Capability(name, repo, kind, script/driver, needs),
                     # base() resolution and Capability.status()
    config.py        # ~/.studio/config.json (ollama_host, default_model, base_dir, repos)
    install.py       # per-repo venv setup + agent-forge content install
    doctor.py        # system-dep + readiness checks
  install.sh         # bootstrap the launcher, then `studio install`
  Dockerfile         # experimental Linux image (capabilities baked in)
```

## Locating the repos

`capabilities.base()` is read at call time: `$STUDIO_BASE`, then `base_dir` from
the config, then the directory containing this checkout. Each capability's repo
is `base()/<name>` (flat: `thandv`, `local_ai`, `writer`, `audiobook-converter`,
`SWE`, `agent-forge`) unless `repos.<capability>` in the config overrides it; a
relative override that escapes the base raises `ConfigError`, which the CLI
reports as one line. `Capability.status()` is the only readiness logic;
`list`, `doctor` and `config` all use it. `config` never imports `capabilities`.

## Capability kinds

- **passthrough** — a console script in the tool's own venv (`thandv`, `writer`,
  `audiobook`, `build-app`, `vibe`). Resolved as `<repo>/.venv/bin/<script>`,
  falling back to `PATH`. `studio <name> ...args` → `subprocess.run([cmd, *args])`.
- **driver** — a Python entry script driven directly (`SWE` orchestrator driver).
- **content** — agent-forge's scripts (`sync`/`build`/`install`/…), run in place.

## Why independent venvs

The capabilities have genuinely conflicting dependency trees (audiobook pulls
torch + kokoro; writer pulls streamlit; local_ai pulls chromadb). Merging them
into one environment is fragile. Keeping one venv per repo and dispatching across
them is the robust choice — and it mirrors agent-forge's "registry is the source
of truth, adapters are thin" philosophy.

## Shared backend

`capabilities.shared_env()` injects `OLLAMA_HOST` (and `THANDV_MODEL` if set) into
every spawned capability, so all tools talk to the same local model runtime.
`studio install` also installs the agent-forge `thandv` content view into
`~/.thandv`, so the curated personas/skills are available to `studio code`.

## Adding a capability

Append a `Capability(...)` to `capabilities.CAPABILITIES` with its repo path,
kind, and entry script. No other change is needed — `doctor`, `list`, `install`,
and dispatch all read the registry.

## Roadmap

1. **Launcher + installer** (this repo) — done.
2. **Docker image** — bake the Python capabilities + launcher into a Linux image;
   point `OLLAMA_HOST` at a host/sidecar Ollama. macOS stays native.
3. **Unified TUI** — a single interactive front-end over the capabilities
   (Thandv's chat loop as the shell, other capabilities as slash-commands).
