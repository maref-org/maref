"""Federation platform summary API — real-data endpoint for the GUI dashboard.

Exposes :meth:`FederatedPlatform.platform_summary` (gateway / discovery /
catalog / trust / policy / hitl / marketplace / metering / settlement) over
HTTP so the desktop GUI can render live federation state instead of mocks.

Note: distinct from ``federation_router`` (cross-org Merkle audit root
aggregation). This router reports the *federation platform* itself.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/federation")

_platform: Any | None = None
_platform_lock = threading.Lock()


def _get_platform() -> Any:
    """Build the federation platform lazily (once per sidecar process)."""
    global _platform
    if _platform is None:
        with _platform_lock:
            if _platform is None:
                from maref.federation import create_default_federation

                _platform = create_default_federation(server_id="maref-sidecar")
    return _platform


@router.get("/platform-summary")
def platform_summary() -> dict[str, Any]:
    """Return a snapshot of the local federation platform for the GUI."""
    return _get_platform().platform_summary()
