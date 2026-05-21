"""Backward-compatible re-exports from maref.governance.constants.

This module is kept for backward compatibility.
New code should import from maref.governance.constants directly.
"""

from maref.governance.constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    compute_valid_transitions,
    hamming_distance,
)

VALID_TRANSITIONS = compute_valid_transitions()

__all__ = [
    "ENTROPY_LEVELS",
    "GRAY_CODE",
    "MAX_ENTROPY",
    "STATE_NAMES",
    "VALID_TRANSITIONS",
    "hamming_distance",
    "compute_valid_transitions",
]
