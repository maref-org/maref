"""Vector Clock implementation for causal consistency in multi-agent orchestration.

Provides partial-order tracking of events across distributed agents,
enabling detection of concurrency, causality, and happens-before relations
without centralized coordination.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class VectorClock:
    """Immutable vector clock mapping agent IDs to logical timestamps."""

    clocks: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def new(cls, agent_id: str) -> VectorClock:
        """Create a new vector clock with a single agent at 0."""
        return cls({agent_id: 0})

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> VectorClock:
        """Deserialize from a plain dictionary."""
        return cls(dict(data))

    # ------------------------------------------------------------------ #
    # Core operations
    # ------------------------------------------------------------------ #
    def tick(self, agent_id: str) -> VectorClock:
        """Increment the logical clock for *agent_id* and return a new instance."""
        new_clocks = dict(self.clocks)
        new_clocks[agent_id] = new_clocks.get(agent_id, 0) + 1
        return VectorClock(new_clocks)

    def merge(self, other: VectorClock) -> VectorClock:
        """Return the element-wise maximum of two vector clocks."""
        merged = dict(self.clocks)
        for aid, ts in other.clocks.items():
            merged[aid] = max(merged.get(aid, 0), ts)
        return VectorClock(merged)

    # ------------------------------------------------------------------ #
    # Partial-order comparison
    # ------------------------------------------------------------------ #
    def compare(self, other: VectorClock) -> CausalRelation:
        """Determine the causal relationship between *self* and *other*."""
        all_keys = set(self.clocks) | set(other.clocks)
        lt = gt = eq = 0

        for key in all_keys:
            a = self.clocks.get(key, 0)
            b = other.clocks.get(key, 0)
            if a < b:
                lt += 1
            elif a > b:
                gt += 1
            else:
                eq += 1

        if gt == 0 and lt > 0:
            return CausalRelation.BEFORE
        if lt == 0 and gt > 0:
            return CausalRelation.AFTER
        if lt == 0 and gt == 0:
            return CausalRelation.EQUAL
        return CausalRelation.CONCURRENT

    def happens_before(self, other: VectorClock) -> bool:
        """Return True iff *self* strictly happens-before *other*."""
        return self.compare(other) == CausalRelation.BEFORE

    def is_concurrent_with(self, other: VectorClock) -> bool:
        """Return True iff *self* and *other* are concurrent (incomparable)."""
        return self.compare(other) == CausalRelation.CONCURRENT

    # ------------------------------------------------------------------ #
    # Deduplication / set membership helpers
    # ------------------------------------------------------------------ #
    def dominates(self, other: VectorClock) -> bool:
        """Return True iff *self* >= *other* in every dimension."""
        return all(self.clocks.get(aid, 0) >= ts for aid, ts in other.clocks.items())

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, int]:
        return dict(self.clocks)

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v}" for k, v in sorted(self.clocks.items()))
        return f"VectorClock({items})"


class CausalRelation(str, Enum):
    """Enumeration of causal comparison results."""

    BEFORE = "before"          # self -> other
    AFTER = "after"            # other -> self
    EQUAL = "equal"            # identical
    CONCURRENT = "concurrent"  # incomparable


class CausalContext:
    """Mutable causal context held by an agent during execution.

    Wraps a VectorClock and provides convenience methods for event tracking.
    """

    def __init__(self, agent_id: str, clock: VectorClock | None = None) -> None:
        self._agent_id = agent_id
        self._clock = clock or VectorClock.new(agent_id)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def clock(self) -> VectorClock:
        return self._clock

    def event(self) -> VectorClock:
        """Record a local event and return the updated clock."""
        self._clock = self._clock.tick(self._agent_id)
        return self._clock

    def receive(self, sender_clock: VectorClock) -> VectorClock:
        """Merge an incoming vector clock (e.g. from a message) and tick."""
        self._clock = self._clock.merge(sender_clock).tick(self._agent_id)
        return self._clock

    def send(self) -> VectorClock:
        """Tick before sending a message, returning the clock to attach."""
        self._clock = self._clock.tick(self._agent_id)
        return self._clock

    def snapshot(self) -> VectorClock:
        """Return an immutable copy of the current clock."""
        return copy.deepcopy(self._clock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self._agent_id,
            "clock": self._clock.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CausalContext:
        return cls(
            agent_id=data["agent_id"],
            clock=VectorClock.from_dict(data.get("clock", {})),
        )
