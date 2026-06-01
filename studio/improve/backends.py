"""OpenAI-compatible inference backends for the improvement loop.

One client, many backends — local or free-online — since they all speak the
OpenAI /chat/completions schema:

  ollama     local Ollama (default; free, private)
  groq       Groq free tier (Llama-3.3-70B, very fast)        GROQ_API_KEY
  cerebras   Cerebras free tier (Llama-3.3-70B / Qwen3 …)     CEREBRAS_API_KEY
  openrouter OpenRouter free models                            OPENROUTER_API_KEY
  custom     any base_url — e.g. a Kaggle/Colab + Ollama + ngrok GPU tunnel
             STUDIO_IMPROVE_BASE_URL [+ STUDIO_IMPROVE_API_KEY, STUDIO_IMPROVE_MODEL]

The "free online GPU" path is `custom` (point it at a Kaggle/Colab ngrok URL) or
the hosted free tiers (groq/cerebras/openrouter) — far bigger models than local.
Stdlib only (urllib).
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

SPECS = {
    "ollama": {"base": None, "key_env": None, "model": "qwen2.5-coder:7b"},
    "groq": {"base": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY",
             "model": "llama-3.3-70b-versatile"},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "key_env": "CEREBRAS_API_KEY",
                 "model": "llama-3.3-70b"},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY",
                   "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "custom": {"base": None, "key_env": "STUDIO_IMPROVE_API_KEY", "model": None},
}


@dataclass
class Backend:
    name: str
    base_url: str
    api_key: str
    model: str

    def chat(self, messages: list[dict], temperature: float = 0.2,
             max_tokens: int = 2048, timeout: int = 120) -> str:
        body = json.dumps({
            "model": self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key or 'none'}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec - configured backend only
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]


def resolve(name: str, model: str | None, ollama_host: str) -> Backend:
    if name not in SPECS:
        raise ValueError(f"unknown backend '{name}'. Known: {', '.join(SPECS)}")
    spec = SPECS[name]
    if name == "ollama":
        base = ollama_host.rstrip("/") + "/v1"
        key = "ollama"
    elif name == "custom":
        base = os.environ.get("STUDIO_IMPROVE_BASE_URL", "")
        if not base:
            raise ValueError("custom backend needs STUDIO_IMPROVE_BASE_URL "
                             "(e.g. a Kaggle/Colab ngrok Ollama URL)")
        key = os.environ.get(spec["key_env"], "")
    else:
        base = spec["base"]
        key = os.environ.get(spec["key_env"], "")
        if not key:
            raise ValueError(f"{name} backend needs {spec['key_env']} in the environment")
    chosen = model or os.environ.get("STUDIO_IMPROVE_MODEL") or spec["model"]
    if not chosen:
        raise ValueError(f"no model set for backend '{name}' (pass --model or STUDIO_IMPROVE_MODEL)")
    return Backend(name=name, base_url=base, api_key=key, model=chosen)


def available(ollama_host: str) -> dict[str, bool]:
    """Which backends are usable right now (key present / base set)."""
    out = {}
    for n, spec in SPECS.items():
        if n == "ollama":
            out[n] = True
        elif n == "custom":
            out[n] = bool(os.environ.get("STUDIO_IMPROVE_BASE_URL"))
        else:
            out[n] = bool(os.environ.get(spec["key_env"]))
    return out
