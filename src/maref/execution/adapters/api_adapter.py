"""API 模型适配器 — 通过 REST API 调用远端模型。"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from maref.execution.adapters.base import ModelAdapter


class APIModelAdapter(ModelAdapter):
    """远端 API 模型适配器（兼容 OpenAI API 格式）。"""

    def __init__(self, endpoint: str, api_key: str, model: str = "gpt-3.5-turbo") -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str, **kwargs: Any) -> str:
        payload = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 200),
        }).encode()

        req = urllib.request.Request(
            f"{self._endpoint}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=kwargs.get("timeout", 30)) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]

    @property
    def model_name(self) -> str:
        return self._model

    def count_tokens(self, text: str) -> int:
        return max(1, int(len(text) / 4))
