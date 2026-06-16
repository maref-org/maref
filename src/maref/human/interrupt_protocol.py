"""Interrupt Protocol — human can inject PAUSE/ABORT/OVERRIDE at any moment.

Design principles:
- Global sequence numbers prevent stale interrupts from being acted upon
- Propagation within 1 heartbeat cycle to all relevant agents
- Interrupts are immutable once issued
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InterruptType(Enum):
    """Types of human interrupt signals."""

    PAUSE = "pause"  # Pause execution, can resume later
    ABORT = "abort"  # Terminate, trigger Saga rollback
    OVERRIDE = "override"  # Forcefully modify an agent's decision
    RESUME = "resume"  # Resume from PAUSE


@dataclass(frozen=True)
class InterruptSignal:
    """Immutable interrupt signal from human to multi-agent system.

    The global_sequence ensures that agents always check for newer interrupts
    before executing, preventing "I didn't receive the stop signal" failures.
    """

    signal_id: str
    interrupt_type: InterruptType
    target_agents: list[str]  # Empty = broadcast to all
    global_sequence: int  # Monotonically increasing
    issued_by: str  # Human user ID
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)  # OVERRIDE: new decision
    issued_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "interrupt_type": self.interrupt_type.value,
            "target_agents": self.target_agents,
            "global_sequence": self.global_sequence,
            "issued_by": self.issued_by,
            "reason": self.reason,
            "payload": self.payload,
            "issued_at": self.issued_at,
        }


class InterruptProtocol:
    """Protocol for propagating human interrupts to all agents.

    Usage:
        protocol = InterruptProtocol()
        signal = protocol.issue_interrupt(
            InterruptType.ABORT,
            issued_by="admin",
            reason="Emergency stop",
        )
        # In each agent's execution loop:
        latest = protocol.get_latest_interrupt()
        if latest and latest.global_sequence > agent.last_seen_sequence:
            agent.handle_interrupt(latest)
    """

    def __init__(self, heartbeat_interval: float = 1.0) -> None:
        self._heartbeat_interval = heartbeat_interval
        self._sequence: int = 0
        self._interrupts: dict[int, InterruptSignal] = {}
        self._handlers: dict[InterruptType, list] = {}

    # ------------------------------------------------------------------ #
    # Issue interrupts
    # ------------------------------------------------------------------ #
    def issue_interrupt(
        self,
        interrupt_type: InterruptType,
        issued_by: str,
        target_agents: list[str] | None = None,
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> InterruptSignal:
        """Issue a new interrupt signal. Auto-increments global sequence."""
        self._sequence += 1
        signal = InterruptSignal(
            signal_id=str(uuid.uuid4())[:8],
            interrupt_type=interrupt_type,
            target_agents=target_agents or [],
            global_sequence=self._sequence,
            issued_by=issued_by,
            reason=reason,
            payload=payload or {},
        )
        self._interrupts[self._sequence] = signal
        return signal

    # ------------------------------------------------------------------ #
    # Query interrupts
    # ------------------------------------------------------------------ #
    def get_latest_interrupt(self) -> InterruptSignal | None:
        """Get the most recent interrupt signal."""
        if not self._interrupts:
            return None
        return self._interrupts[self._sequence]

    def get_interrupt(self, sequence: int) -> InterruptSignal | None:
        """Get a specific interrupt by sequence number."""
        return self._interrupts.get(sequence)

    def get_interrupts_since(self, sequence: int) -> list[InterruptSignal]:
        """Get all interrupts with sequence > given sequence."""
        return [sig for seq, sig in self._interrupts.items() if seq > sequence]

    def should_agent_stop(self, agent_id: str, last_seen_sequence: int) -> InterruptSignal | None:
        """Check if an agent should stop based on latest interrupts.

        Returns the interrupt signal if there's a newer one targeting this agent,
        None otherwise.
        """
        latest = self.get_latest_interrupt()
        if latest is None:
            return None
        if latest.global_sequence <= last_seen_sequence:
            return None
        # Broadcast (empty target_agents) or specifically targeted
        if not latest.target_agents or agent_id in latest.target_agents:
            return latest
        return None

    # ------------------------------------------------------------------ #
    # Propagation guarantee
    # ------------------------------------------------------------------ #
    def propagate_to_agents(self, agent_ids: list[str], signal: InterruptSignal) -> dict[str, bool]:
        """Propagate interrupt to agents. Returns delivery status.

        In production, this would use a message bus (Redis Pub/Sub, RabbitMQ).
        Here we simulate delivery tracking.
        """
        delivery: dict[str, bool] = {}
        for aid in agent_ids:
            # Simulate delivery within 1 heartbeat cycle
            if not signal.target_agents or aid in signal.target_agents:
                delivery[aid] = True
            else:
                delivery[aid] = False
        return delivery

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #
    def get_history(self, limit: int = 100) -> list[InterruptSignal]:
        """Get interrupt history."""
        sorted_seqs = sorted(self._interrupts.keys(), reverse=True)
        return [self._interrupts[s] for s in sorted_seqs[:limit]]
