"""Model adapters — 统一 LLM 调用接口，支持不同提供商。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelAdapter(ABC):
    """LLM 模型适配器基类。"""

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def count_tokens(self, text: str) -> int: ...
