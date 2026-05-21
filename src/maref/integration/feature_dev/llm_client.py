"""Lightweight LLM client using httpx. Tests provider connectivity on init."""

from __future__ import annotations

import json
import os
import time
from typing import Any


def _first_key(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": lambda: _first_key("DEEPSEEK_API_KEY"),
        "models": {"default": "deepseek-chat", "reasoning": "deepseek-reasoner"},
    },
    {
        "name": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": lambda: _first_key("SILICONFLOW_API_KEY", "SILICONFLOW_CN_API_KEY"),
        "models": {"default": "deepseek-ai/DeepSeek-V3", "reasoning": "deepseek-ai/DeepSeek-R1"},
    },
]


class LlmClient:
    def __init__(self) -> None:
        self._provider = self._resolve_provider()
        self._available = self._provider is not None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def provider_name(self) -> str:
        return self._provider["name"] if self._provider else "none"

    def generate(
        self,
        system: str,
        prompt: str,
        model_key: str = "default",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str | None:
        if not self._available:
            return None
        import httpx

        model = self._provider["models"].get(model_key, self._provider["models"]["default"])
        t0 = time.perf_counter()
        try:
            resp = httpx.post(
                f"{self._provider['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._provider['api_key']()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120.0,
            )
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self._log_call(model, "success", elapsed, data.get("usage", {}))
            return content
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._log_call(model, f"error: {exc}", elapsed, {})
            return None

    def generate_json(
        self,
        system: str,
        prompt: str,
        model_key: str = "default",
        temperature: float = 0.3,
    ) -> dict[str, Any] | None:
        result = self.generate(
            system=system + "\nOutput ONLY valid JSON, no markdown fences.",
            prompt=prompt,
            model_key=model_key,
            temperature=temperature,
            max_tokens=4000,
        )
        if not result:
            return None
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
            result = result.rsplit("```", 1)[0]
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None

    def _resolve_provider(self) -> dict[str, Any] | None:
        import httpx
        for p in _PROVIDERS:
            key_fn = p["api_key"]
            key = key_fn()
            if not key:
                continue
            try:
                resp = httpx.post(
                    f"{p['base_url']}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": p["models"]["default"],
                        "messages": [{"role": "user", "content": "ok"}],
                        "max_tokens": 5,
                    },
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    return p
            except Exception:
                continue
        return None

    def _log_call(self, model: str, status: str, elapsed: float, usage: dict) -> None:
        pass
