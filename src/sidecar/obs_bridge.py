from __future__ import annotations

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
