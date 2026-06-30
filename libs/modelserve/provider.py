"""Local Qwen serving client (handoff §6 modelserve).

``OfflineProvider`` (default, DECISIONS D3): deterministic, no GPU, repeatable — composes the
agent's natural-language "why" from the structured flag. ``OpenAICompatProvider`` talks to a
local vLLM/Ollama OpenAI-compatible endpoint (the real Qwen) via stdlib urllib. The egress guard
runs before any network call, so inference can never leave the local boundary by default.

``MODEL_VERSION`` is recorded on every flag/decision for audit + future training.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol

from libs.common.config import settings
from libs.modelserve.guard import assert_local


class Provider(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class OfflineProvider:
    name = "offline"
    model_version = "qwen-offline-v1"

    def complete(self, system: str, prompt: str) -> str:
        # Deterministic stand-in: echo a controls-analyst-style line from the structured prompt.
        return f"[local-qwen:offline] {prompt.strip().splitlines()[0][:160]}"


class OpenAICompatProvider:
    name = "oss"

    def __init__(self) -> None:
        self.base = settings.oss_model_base_url
        self.model = settings.oss_model_name
        self.model_version = f"{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        assert_local(self.base)  # local-only guard
        body = json.dumps({"model": self.model, "temperature": 0, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(f"{self.base}/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


def get_provider() -> Provider:
    if settings.llm_provider == "oss":
        return OpenAICompatProvider()
    return OfflineProvider()


def model_version() -> str:
    p = get_provider()
    return getattr(p, "model_version", p.name)
