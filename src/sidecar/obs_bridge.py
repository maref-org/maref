from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from maref.obs.client import MarefObsClient

logger = logging.getLogger(__name__)


class ObsBridge:
    def __init__(self, client: MarefObsClient | None = None) -> None:
        self._client = client or MarefObsClient.get_default()
        self._state_machine_callbacks: list[Callable] = []

    def get_client(self) -> MarefObsClient:
        return self._client

    def wire_state_machine(self, sm: Any) -> None:
        def on_transition(transition: Any) -> None:
            self._client.log_state_transition(
                from_state=transition.from_state.value if hasattr(transition.from_state, 'value') else str(transition.from_state),
                to_state=transition.to_state.value if hasattr(transition.to_state, 'value') else str(transition.to_state),
                entropy=getattr(sm, 'current_entropy', 0),
                reason=getattr(transition, 'reason', ''),
            )
        sm.add_callback(on_transition)
        self._state_machine_callbacks.append(on_transition)

    def wire_circuit_breaker(self, cb: Any) -> None:
        original_check = cb.check_depth
        def wrapped_check(depth: int) -> bool:
            result = original_check(depth)
            if hasattr(cb, '_trips') and cb._trips:
                trip = cb._trips[-1]
                self._client.log_breaker_trip(
                    reason=getattr(trip, 'reason', 'depth_exceeded'),
                    depth=depth,
                    entropy=getattr(trip, 'entropy', 0),
                )
            return result
        cb.check_depth = wrapped_check

    def wire_oscillation_loop(self, loop: Any) -> None:
        original_detect = loop.detect_and_fix
        async def wrapped_detect(rate: float, entropy: int, current_state: str) -> Any:
            result = await original_detect(rate, entropy, current_state)
            self._client.log_oscillation(detected=True, rate=rate, entropy=entropy)
            return result
        loop.detect_and_fix = wrapped_detect

    def wire_multiple_components(self, items: dict[str, Any]) -> None:
        for key, component in items.items():
            if key == 'state_machine':
                self.wire_state_machine(component)
            elif key == 'circuit_breaker':
                self.wire_circuit_breaker(component)
            elif key == 'oscillation_loop':
                self.wire_oscillation_loop(component)
