from dataclasses import dataclass, field
from typing import Any

import structlog

from maref_lite.state_machine import StateMachine  # type: ignore[attr-defined]

logger = structlog.get_logger(__name__)

@dataclass
class ChaosResult:
    success: bool
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

class ChaosInjector:

    def __init__(self, state_machine: StateMachine) -> None:
        self.state_machine = state_machine
        self._active_experiments: dict[str, ChaosResult] = {}

    async def inject_failure(self, target: str, failure_type: str) -> ChaosResult:
        try:
            result = ChaosResult(success=True)
            self._active_experiments[f'{target}:{failure_type}'] = result
            return result
        except Exception as e:
            logger.error('chaos_injection_failed', target=target, failure_type=failure_type, error=str(e))
            return ChaosResult(success=False, error=str(e))
