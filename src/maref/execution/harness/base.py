from __future__ import annotations

from abc import ABC, abstractmethod

from maref.execution.harness.types import HarnessConfig, HarnessResult


class BaseHarness(ABC):
    _config: HarnessConfig | None

    def __init__(self) -> None:
        self._config = None

    def configure(self, config: HarnessConfig) -> None:
        self._config = config

    def preflight(self) -> list[str]:
        return []

    @abstractmethod
    def run(self, round_id: str = "") -> HarnessResult: ...

    def validate(self, result: HarnessResult) -> bool:
        return result.passed
