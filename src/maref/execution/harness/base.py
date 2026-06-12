from __future__ import annotations

from abc import ABC, abstractmethod

from maref.execution.harness.types import HarnessConfig, HarnessResult


class BaseHarness(ABC):
    def __init__(self) -> None:
        self._config: HarnessConfig | None = None

    @abstractmethod
    def configure(self, config: HarnessConfig) -> None:
        self._config = config

    @abstractmethod
    def run(self, round_id: str = "") -> HarnessResult: ...

    def preflight(self) -> list[str]:
        warnings: list[str] = []
        if self._config is None:
            warnings.append("no configuration set")
        return warnings

    def validate(self, result: HarnessResult) -> bool:
        return result.passed
