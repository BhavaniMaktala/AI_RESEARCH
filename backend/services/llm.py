"""Optional LLM client (Gemini / OpenAI / Groq).

When no key is configured the platform uses deterministic template-based
summaries and explanations, so every feature still works offline.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
}


class LLMClient:
    def __init__(self, provider: str = "none", api_key: str = "", model: str = "", timeout: float = 25.0):
        self.provider = (provider or "none").lower()
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or DEFAULT_MODELS.get(self.provider, "")
        self.timeout = timeout
        self.enabled = self.provider in DEFAULT_MODELS and bool(self.api_key)
        self.calls = 0
        self.failures = 0

    def info(self) -> dict:
        return {"provider": self.provider if self.enabled else "template",
                "model": self.model if self.enabled else "deterministic-nlg",
                "enabled": self.enabled, "calls": self.calls, "failures": self.failures}

    def generate(self, prompt: str, system: str = "", max_tokens: int = 400) -> str | None:
        if not self.enabled:
            return None
        self.calls += 1
        try:
            if self.provider == "gemini":
                return self._gemini(prompt, system, max_tokens)
            return self._openai_compatible(prompt, system, max_tokens)
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            log.info("LLM call failed (%s); using deterministic fallback", exc)
            return None

    def _gemini(self, prompt: str, system: str, max_tokens: int) -> str:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.api_key}")
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        resp = requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _openai_compatible(self, prompt: str, system: str, max_tokens: int) -> str:
        base = "https://api.openai.com/v1" if self.provider == "openai" else "https://api.groq.com/openai/v1"
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def build_llm(config) -> LLMClient:
    client = LLMClient(config.LLM_PROVIDER, config.LLM_API_KEY, config.LLM_MODEL)
    log.info("LLM: %s", "enabled (%s)" % client.model if client.enabled else "deterministic fallback")
    return client
