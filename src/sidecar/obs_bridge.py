from __future__ import annotations

from typing import Any

try:
    from maref.obs import MarefObsClient
except ImportError:
    import logging as _logging
    _logging.getLogger(__name__).debug("maref.obs not available, using stub")

    class MarefObsClient:  # type: ignore[no-redef]
        @staticmethod
        def get_default() -> MarefObsClient:
            return MarefObsClient()


class ObsBridge:
    """Bridge between Sidecar FastAPI and the observation layer."""

    def __init__(self, client: MarefObsClient | None = None) -> None:
        self._client = client

    def get_client(self) -> MarefObsClient | None:
        return self._client

    def wire_state_machine(self, sm: Any) -> None:
        if self._client is None:
            return
        def on_transition(event: Any) -> None:
            self._client.log_state_transition(
                from_state=str(event.from_state),
                to_state=str(event.to_state),
                reason=getattr(event, 'reason', ''),
            )
        sm.add_callback(on_transition)

    def wire_circuit_breaker(self, cb: Any) -> None:
        if self._client is None:
            return
        original_trip = getattr(cb, '_trip', None)
        if original_trip:
            def tripped_wrapper(*args: Any, **kwargs: Any) -> Any:
                result = original_trip(*args, **kwargs)
                self._client.log_breaker_trip(reason="circuit breaker tripped")
                return result
            cb._trip = tripped_wrapper

    def wire_oscillation_loop(self, loop: Any) -> None:
        if self._client is None:
            return
        original_run = getattr(loop, '_run_fix_cycle', None)
        if original_run:
            def run_wrapper(*args: Any, **kwargs: Any) -> Any:
                result = original_run(*args, **kwargs)
                stage = getattr(loop, 'stage', 'none')
                if stage != 'none':
                    assert self._client is not None
                    self._client.log_oscillation(detected=True)
                return result
            loop._run_fix_cycle = run_wrapper

    def wire_multiple_components(self, components: dict[str, Any]) -> None:
        for key, component in components.items():
            if key == "state_machine":
                self.wire_state_machine(component)
            elif key == "circuit_breaker":
                self.wire_circuit_breaker(component)
            elif key == "oscillation_loop":
                self.wire_oscillation_loop(component)
