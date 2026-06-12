"""Article 7: Cross-boundary MCP call degradation strategy.

FAIL_MODE controls behavior when MCP service is unavailable:
- open:     Degrade on failure, bypass governance, mark governance_bypassed=true
- closed:   Block on failure (for T2/L5-L6 high-security scenarios)
"""

from __future__ import annotations

import os
from enum import Enum


class FailMode(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


def get_fail_mode() -> FailMode:
    """Read FAIL_MODE from environment, defaulting to 'open'."""
    mode = os.environ.get("FAIL_MODE", "open").lower().strip()
    if mode == "closed":
        return FailMode.CLOSED
    return FailMode.OPEN


def build_degraded_response(
    request_id: int | str,
    original_error: dict | None = None,
) -> dict:
    """Build a degraded response payload for FAIL_MODE=open."""
    return {
        "governance_bypassed": True,
        "fail_mode": "open",
        "error": original_error,
        "message": "MCP service unavailable — governance bypassed (FAIL_MODE=open)",
    }
