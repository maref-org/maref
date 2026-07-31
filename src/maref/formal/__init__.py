"""Formal verification package (Phase 3.6 — Agent Internet invariants)."""

from maref.formal.internet_invariants import (
    ENTRIES,
    MAX_CHAIN,
    NODES,
    SPEC_PATH,
    InternetInvariantsVerifier,
    InternetState,
    enumerate_reachable_states,
)

__all__ = [
    "NODES",
    "ENTRIES",
    "MAX_CHAIN",
    "SPEC_PATH",
    "InternetState",
    "InternetInvariantsVerifier",
    "enumerate_reachable_states",
]
