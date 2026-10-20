"""`studio doctor` — check system deps and per-capability readiness."""
from __future__ import annotations

import os
import shutil

from . import capabilities as caps
from . import config as cfg_mod

SYSTEM_DEPS = {
    "ollama": "local model runtime (https://ollama.com)",
    "ffmpeg": "audio/video encoding",
    "espeak-ng": "TTS phonemizer (audiobook)",
}


def _have(dep: str) -> bool:
    if dep == "anthropic_key":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return shutil.which(dep) is not None


def run() -> int:
    cfg = cfg_mod.load()
    print("studio doctor\n" + "=" * 40)
    print(f"home:        {cfg_mod.STUDIO_HOME}")
    print(f"ollama_host: {cfg['ollama_host']}")
    print(f"base dir:    {caps.base(cfg)}\n")

    print("system dependencies:")
    for dep, desc in SYSTEM_DEPS.items():
        mark = "ok " if _have(dep) else "MISSING"
        print(f"  [{mark}] {dep:<12} {desc}")
    print(f"  [{'ok ' if _have('anthropic_key') else '-- '}] ANTHROPIC_API_KEY "
          f"(only needed for `studio swe`)")

    print("\ncapabilities:")
    missing_caps = 0
    for c in caps.CAPABILITIES:
        status = c.status()
        needs = [d for d in c.needs if not _have(d)]
        if status != caps.READY:
            missing_caps += 1
            hint = f" (run: studio install {c.name})" if status == "not installed" else ""
            print(f"  [   ] {c.name:<11} {c.summary}")
            print(f"        -> {status}{hint}")
        else:
            warn = f"  (needs: {', '.join(needs)})" if needs else ""
            print(f"  [ok] {c.name:<11} {c.summary}{warn}")

    print("\nimprove backends (studio improve):")
    from .improve import backends as be
    avail = be.available(cfg["ollama_host"])
    for name, ok in avail.items():
        hint = "" if ok else f"  (set {be.SPECS[name]['key_env'] or 'STUDIO_IMPROVE_BASE_URL'})"
        print(f"  [{'ok ' if ok else '-- '}] {name}{hint}")
    print("  free online options: groq / cerebras / openrouter (free tiers), or")
    print("  custom = a Kaggle/Colab + Ollama + ngrok GPU tunnel (STUDIO_IMPROVE_BASE_URL).")

    print()
    if missing_caps:
        print(f"{missing_caps} capability(ies) not ready — `studio install` to set them up.")
    else:
        print("all capabilities ready.")
    return 0
