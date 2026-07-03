from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelAdapter(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        ...
