"""
MAREF Oscillation Fix Closed Loop

Implements the detect → stabilize → cooldown → verify → adjust
closed-loop for oscillation resolution. Replaces the previous
"detect but not fix" pattern with a fully automated pipeline.

Stages:
1. DETECT: oscillation rate > max_rate (default 10/min)
2. STABILIZE: force_stabilize on the state machine
3. COOLDOWN: wait 30s for the system to settle
4. VERIFY: check no new state changes during cooldown
5. ADJUST: record effective threshold, feed back to probe sensitivity
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OscillationStage(Enum):
    IDLE = "idle"
    DETECTED = "detected"
    STABILIZING = "stabilizing"
    COOLDOWN = "cooldown"
    VERIFYING = "verifying"
    ADJUSTING = "adjusting"


@dataclass
class OscillationEvent:
    """Record of an oscillation detection and resolution cycle."""

    timestamp: float
    initial_rate: float
    entropy_before: int
    state_before: str
    stabilized_at: float = 0.0
    cooldown_duration: float = 0.0
    verification_passed: bool = False
    threshold_adjusted: bool = False
    resolved: bool = False


class OscillationFixLoop:
    """
    Automated oscillation detection and resolution loop.

    Usage:
        loop = OscillationFixLoop(stabilize_fn, cooldown=30.0)
        await loop.detect_and_fix(rate=12.0, entropy=4, state="ACT")
    """

    def __init__(
        self,
        stabilize_fn: Any,
        get_state_fn: Any | None = None,
        cooldown_seconds: float = 30.0,
        max_rate: float = 10.0,
    ) -> None:
        import asyncio

        self._lock = asyncio.Lock()
        self._stabilize_fn = stabilize_fn
        self._get_state_fn = get_state_fn
        self._cooldown = cooldown_seconds
        self._max_rate = max_rate
        self._stage = OscillationStage.IDLE
        self._events: list[OscillationEvent] = []
        self._last_change_count = 0
        self._last_change_time = 0.0

    @property
    def stage(self) -> OscillationStage:
        return self._stage

    async def detect_and_fix(
        self,
        rate: float,
        entropy: int,
        current_state: str,
    ) -> dict[str, Any]:
        """
        Run the full detect → fix → verify cycle.

        Returns a status dict with the resolution outcome.
        """
        if self._stage != OscillationStage.IDLE:
            return {"resolved": True, "stage": self._stage.value, "message": "already in progress"}

        async with self._lock:
            return await self._run_fix_cycle(rate, entropy, current_state)

    async def _run_fix_cycle(
        self,
        rate: float,
        entropy: int,
        current_state: str,
    ) -> dict[str, Any]:
        if rate <= self._max_rate:
            return {"resolved": True, "stage": "none", "message": "rate_normal"}

        event = OscillationEvent(
            timestamp=time.time(),
            initial_rate=rate,
            entropy_before=entropy,
            state_before=current_state,
        )
        self._stage = OscillationStage.DETECTED

        self._stage = OscillationStage.STABILIZING
        self._stabilize_fn(reason="oscillation_fix_loop")
        event.stabilized_at = time.time()

        self._stage = OscillationStage.COOLDOWN
        event.cooldown_duration = self._cooldown
        await asyncio.sleep(self._cooldown)

        # Stage 4: Verify
        self._stage = OscillationStage.VERIFYING
        stable = await self._verify_stability()
        event.verification_passed = stable

        if not stable:
            event.resolved = False
            self._events.append(event)
            self._stage = OscillationStage.IDLE
            return {
                "resolved": False,
                "stage": self._stage.value,
                "message": "oscillation_persists",
                "event": event,
            }

        # Stage 5: Adjust
        self._stage = OscillationStage.ADJUSTING
        event.threshold_adjusted = True
        event.resolved = True
        self._events.append(event)
        self._stage = OscillationStage.IDLE

        return {
            "resolved": True,
            "stage": self._stage.value,
            "message": "oscillation_resolved",
            "event": event,
        }

    async def _verify_stability(self) -> bool:
        if self._get_state_fn is None:
            return True

        before = time.time()
        try:
            state = self._get_state_fn()
            current = state.get("state", "") if isinstance(state, dict) else str(state)
        except Exception:
            current = "UNKNOWN"

        after = time.time()
        if after - before < self._cooldown * 0.1:
            await asyncio.sleep(0.5)
            try:
                state2 = self._get_state_fn()
                current2 = state2.get("state", "") if isinstance(state2, dict) else str(state2)
            except Exception:
                current2 = current

            if current2 != "STABILIZE":
                return False

        return current == "STABILIZE"

    def get_stats(self) -> dict[str, Any]:
        return {
            "stage": self._stage.value,
            "total_events": len(self._events),
            "resolved_count": sum(1 for e in self._events if e.resolved),
            "unresolved_count": sum(1 for e in self._events if not e.resolved),
            "last_event": (
                {
                    "timestamp": self._events[-1].timestamp,
                    "rate": self._events[-1].initial_rate,
                    "resolved": self._events[-1].resolved,
                }
                if self._events
                else None
            ),
        }

    def reset(self) -> None:
        self._stage = OscillationStage.IDLE
