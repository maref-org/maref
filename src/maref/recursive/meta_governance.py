from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditRecord

_MAX_RECURSION_DEPTH = 3


class MetaBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RecursionDepthExceededError(RuntimeError):
    pass


@dataclass
class MetaCircuitBreaker:
    inner_trip_threshold: int = 3
    state: MetaBreakerState = MetaBreakerState.CLOSED
    inner_trip_count: int = 0
    last_open_time: float = 0.0
    cooldown_seconds: float = 30.0

    def record_trip(self) -> None:
        if self.state == MetaBreakerState.CLOSED:
            self.inner_trip_count += 1
            if self.inner_trip_count >= self.inner_trip_threshold:
                self.state = MetaBreakerState.OPEN
                self.last_open_time = time.time()

    def try_half_open(self) -> bool:
        if self.state == MetaBreakerState.OPEN:
            elapsed = time.time() - self.last_open_time
            if elapsed >= self.cooldown_seconds:
                self.state = MetaBreakerState.HALF_OPEN
                return True
        return False

    def close(self) -> None:
        self.state = MetaBreakerState.CLOSED
        self.inner_trip_count = 0

    def fail_half_open(self) -> None:
        if self.state == MetaBreakerState.HALF_OPEN:
            self.state = MetaBreakerState.OPEN
            self.last_open_time = time.time()


@dataclass
class CrossLayerAuditEntry:
    timestamp: float = field(default_factory=time.time)
    layer: str = ""
    inner_state: str = ""
    outer_state: str = ""
    event: str = ""

    def to_unified(self, round_num: int = 0) -> UnifiedAuditRecord:
        from maref.recursive.unified_audit import UnifiedAuditRecord, make_record_id

        outcome: str | None = None
        if "recovery" in self.event or "recovered" in self.inner_state.lower():
            outcome = "success"
        elif "halt" in self.event or "trip" in self.event:
            outcome = "failure"

        return UnifiedAuditRecord(
            record_id=make_record_id("cross_layer", hash((self.timestamp, self.event)) % 100000),
            timestamp=self.timestamp,
            layer=self.layer,
            round=round_num,
            event_type=f"cross_layer_{self.event}",
            source_module="MetaGovernance",
            target_module=self.layer,
            decision=self.event,
            justification=f"inner={self.inner_state}, outer={self.outer_state}",
            outcome=outcome,
            context_refs=[],
        )


class MetaGovernance:
    _depth_registry: dict[int, int] = {}
    _next_depth_id: int = 0

    def __init__(self, depth: int = 0) -> None:
        if depth > _MAX_RECURSION_DEPTH:
            raise RecursionDepthExceededError(
                f"递归深度超出限制: {depth} > {_MAX_RECURSION_DEPTH}"
            )
        self._depth = depth
        self._inner_governance: object | None = None
        self._meta_cb = MetaCircuitBreaker()
        self._audit_trail: list[CrossLayerAuditEntry] = []
        self._inner_state: str = "IDLE"
        self._halted: bool = False
        depth_id = MetaGovernance._next_depth_id
        MetaGovernance._next_depth_id += 1
        MetaGovernance._depth_registry[depth_id] = depth

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def meta_cb(self) -> MetaCircuitBreaker:
        return self._meta_cb

    @property
    def inner(self) -> object | None:
        return self._inner_governance

    @property
    def audit_trail(self) -> list[CrossLayerAuditEntry]:
        return list(self._audit_trail)

    @property
    def is_halted(self) -> bool:
        return self._halted

    def wrap(self, inner_governance: object) -> None:
        self._inner_governance = inner_governance
        self._audit_trail.append(CrossLayerAuditEntry(
            layer=f"depth_{self._depth}",
            inner_state="wrapped",
            outer_state=self._meta_cb.state.value,
            event="wrap_inner_governance",
        ))

    def signal_inner_trip(self) -> None:
        self._meta_cb.record_trip()
        self._audit_trail.append(CrossLayerAuditEntry(
            layer=f"depth_{self._depth}",
            inner_state="TRIPPED",
            outer_state=self._meta_cb.state.value,
            event="inner_cb_trip",
        ))
        if self._meta_cb.state == MetaBreakerState.OPEN:
            self._halt()

    def _halt(self) -> None:
        self._halted = True
        self._audit_trail.append(CrossLayerAuditEntry(
            layer=f"depth_{self._depth}",
            inner_state="HALTED",
            outer_state=self._meta_cb.state.value,
            event="outer_open_inner_halt",
        ))

    def try_recover(self) -> bool:
        if self._halted and self._meta_cb.try_half_open():
            self._halted = False
            self._audit_trail.append(CrossLayerAuditEntry(
                layer=f"depth_{self._depth}",
                inner_state="RECOVERING",
                outer_state=self._meta_cb.state.value,
                event="half_open_recovery_probe",
            ))
            return True
        return False

    def confirm_recovery(self) -> bool:
        if self._meta_cb.state == MetaBreakerState.HALF_OPEN and not self._halted:
            self._meta_cb.close()
            self._audit_trail.append(CrossLayerAuditEntry(
                layer=f"depth_{self._depth}",
                inner_state="RECOVERED",
                outer_state=self._meta_cb.state.value,
                event="recovery_confirmed",
            ))
            return True
        self._meta_cb.fail_half_open()
        return False

    def set_inner_state(self, state: str) -> None:
        self._inner_state = state

    def get_inner_state(self) -> str:
        return self._inner_state

    @classmethod
    def max_depth(cls) -> int:
        return _MAX_RECURSION_DEPTH

    @classmethod
    def reset_depth_registry(cls) -> None:
        cls._depth_registry.clear()
        cls._next_depth_id = 0
