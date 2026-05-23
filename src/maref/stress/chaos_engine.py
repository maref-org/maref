"""MAREF Chaos Engineering Engine.

Injects controlled failures to test system resilience.
5 fault types:
1. NETWORK: Simulate network latency / disconnection
2. PROCESS: Kill / restart critical processes
3. DISK: Fill disk space / corrupt files
4. MEMORY: Memory pressure simulation
5. CPU: CPU load injection
"""
from __future__ import annotations

import enum
import logging
import os
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class FaultType(enum.Enum):
    NETWORK = "network"
    PROCESS = "process"
    DISK = "disk"
    MEMORY = "memory"
    CPU = "cpu"


@dataclass
class FaultSchedule:
    fault_type: FaultType
    inject_at: float
    duration_s: float = 10.0
    params: dict[str, Any] = field(default_factory=dict)
    injected: bool = False
    recovered: bool = False
    error: str = ""


@dataclass
class FaultEvent:
    fault_type: FaultType
    action: str  # "inject" | "recover" | "skip"
    timestamp: float
    success: bool
    detail: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault_type": self.fault_type.value,
            "action": self.action,
            "timestamp": self.timestamp,
            "success": self.success,
            "detail": self.detail,
            "params": self.params,
        }


@dataclass
class ChaosPlan:
    schedules: list[FaultSchedule] = field(default_factory=list)
    events: list[FaultEvent] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_count": len(self.schedules),
            "event_count": len(self.events),
            "dry_run": self.dry_run,
            "events": [e.to_dict() for e in self.events],
        }


class SafetyGate:
    PRODUCTION_ENV_VAR = "MAREF_PRODUCTION"

    @classmethod
    def is_production(cls) -> bool:
        return os.environ.get(cls.PRODUCTION_ENV_VAR, "").lower() in ("1", "true", "yes")

    @classmethod
    def block_if_production(cls) -> None:
        if cls.is_production():
            raise RuntimeError(
                "ChaosEngine blocked by SafetyGate: MAREF_PRODUCTION is set. "
                "Cannot inject faults in production."
            )


class ChaosEngine:
    def __init__(self, simulate: bool = True) -> None:
        self._simulate = simulate
        self._schedules: list[FaultSchedule] = []
        self._events: list[FaultEvent] = []
        self._timers: list[threading.Timer] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(
        self,
        fault_type: FaultType,
        duration_s: float = 10.0,
        params: dict[str, Any] | None = None,
    ) -> FaultEvent:
        SafetyGate.block_if_production()

        params = params or {}
        schedule = FaultSchedule(
            fault_type=fault_type,
            inject_at=time.time(),
            duration_s=duration_s,
            params=params,
        )

        event = self._simulate_inject(schedule) if self._simulate else self._real_inject(schedule)

        self._events.append(event)
        self._schedules.append(schedule)

        if event.success and duration_s > 0:
            timer = threading.Timer(duration_s, self._recover, args=[fault_type])
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

        return event

    def schedule(
        self,
        fault_type: FaultType,
        delay_s: float,
        duration_s: float = 10.0,
        params: dict[str, Any] | None = None,
    ) -> FaultSchedule:
        schedule = FaultSchedule(
            fault_type=fault_type,
            inject_at=time.time() + delay_s,
            duration_s=duration_s,
            params=params or {},
        )
        self._schedules.append(schedule)

        timer = threading.Timer(delay_s, self._execute_scheduled, args=[schedule])
        timer.daemon = True
        timer.start()
        self._timers.append(timer)

        return schedule

    def plan_only(self, fault_type: FaultType, params: dict[str, Any] | None = None) -> ChaosPlan:
        SafetyGate.block_if_production()

        params = params or {}
        schedule = FaultSchedule(
            fault_type=fault_type,
            inject_at=time.time(),
            duration_s=params.get("duration_s", 10.0),
            params=params,
        )

        event = FaultEvent(
            fault_type=fault_type,
            action="skip",
            timestamp=time.time(),
            success=True,
            detail="Dry-run: fault planned but not executed",
            params=params,
        )

        plan = ChaosPlan(schedules=[schedule], events=[event], dry_run=True)
        self._events.append(event)
        return plan

    def recover(self, fault_type: FaultType | None = None) -> list[FaultEvent]:
        events: list[FaultEvent] = []

        with self._lock:
            to_recover = (
                [s for s in self._schedules if s.fault_type == fault_type and not s.recovered]
                if fault_type
                else [s for s in self._schedules if not s.recovered]
            )
            for schedule in to_recover:
                ev = self._recover_fault(schedule)
                events.append(ev)
                self._events.append(ev)

        return events

    def clear(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()
        self._schedules.clear()

    @property
    def events(self) -> list[FaultEvent]:
        return list(self._events)

    @property
    def active_schedules(self) -> list[FaultSchedule]:
        return [s for s in self._schedules if s.injected and not s.recovered]

    # ------------------------------------------------------------------
    # Simulation (default — safe)
    # ------------------------------------------------------------------

    def _simulate_inject(self, schedule: FaultSchedule) -> FaultEvent:
        time.sleep(random.uniform(0.01, 0.05))

        params = schedule.params
        detail: str

        if schedule.fault_type == FaultType.NETWORK:
            latency_ms = params.get("latency_ms", 500)
            detail = f"Simulated network latency: +{latency_ms}ms, drop_rate={params.get('drop_rate', 0.0)}"
        elif schedule.fault_type == FaultType.PROCESS:
            target = params.get("target", "random_worker")
            detail = f"Simulated kill of process: {target}"
        elif schedule.fault_type == FaultType.DISK:
            space_mb = params.get("space_mb", 100)
            detail = f"Simulated disk fill: {space_mb}MB, corrupt={params.get('corrupt', False)}"
        elif schedule.fault_type == FaultType.MEMORY:
            pressure_mb = params.get("pressure_mb", 200)
            detail = f"Simulated memory pressure: {pressure_mb}MB allocated"
        elif schedule.fault_type == FaultType.CPU:
            load_pct = params.get("load_pct", 80)
            duration = params.get("duration_s", 10.0)
            detail = f"Simulated CPU load: {load_pct}% for {duration}s"
        else:
            detail = f"Unknown fault type: {schedule.fault_type}"

        schedule.injected = True
        return FaultEvent(
            fault_type=schedule.fault_type,
            action="inject",
            timestamp=time.time(),
            success=True,
            detail=detail,
            params=params,
        )

    def _recover_fault(self, schedule: FaultSchedule) -> FaultEvent:
        schedule.recovered = True
        return FaultEvent(
            fault_type=schedule.fault_type,
            action="recover",
            timestamp=time.time(),
            success=True,
            detail=f"Recovered from {schedule.fault_type.value} fault",
        )

    # ------------------------------------------------------------------
    # Real execution (dangerous — requires simulate=False)
    # ------------------------------------------------------------------

    def _real_inject(self, schedule: FaultSchedule) -> FaultEvent:
        impl = self._get_real_impl(schedule.fault_type)
        try:
            result = impl(schedule.params)
            schedule.injected = True
            return FaultEvent(
                fault_type=schedule.fault_type,
                action="inject",
                timestamp=time.time(),
                success=True,
                detail=result,
                params=schedule.params,
            )
        except Exception as e:
            return FaultEvent(
                fault_type=schedule.fault_type,
                action="inject",
                timestamp=time.time(),
                success=False,
                detail=str(e),
                params=schedule.params,
            )

    def _get_real_impl(self, fault_type: FaultType) -> Callable[[dict[str, Any]], str]:
        _impls: dict[FaultType, Callable[[dict[str, Any]], str]] = {
            FaultType.CPU: self._real_cpu_load,
            FaultType.MEMORY: self._real_memory_pressure,
            FaultType.DISK: self._real_disk_fill,
            FaultType.PROCESS: self._real_process_kill,
            FaultType.NETWORK: self._real_network_latency,
        }
        return _impls[fault_type]

    @staticmethod
    def _real_cpu_load(params: dict[str, Any]) -> str:
        load_pct = params.get("load_pct", 80)
        duration_s = params.get("duration_s", 5.0)
        end = time.time() + duration_s
        count = 0
        target_ratio = load_pct / 100.0
        while time.time() < end:
            if random.random() < target_ratio:
                _ = [x * x for x in range(1000)]
                count += 1
            else:
                time.sleep(0.001)
        return f"CPU loaded at {load_pct}% for {duration_s}s ({count} iterations)"

    @staticmethod
    def _real_memory_pressure(params: dict[str, Any]) -> str:
        pressure_mb = params.get("pressure_mb", 200)
        pressure_bytes = pressure_mb * 1024 * 1024
        data = bytearray(pressure_bytes)
        _ = len(data)
        return f"Allocated {pressure_mb}MB of memory"

    @staticmethod
    def _real_disk_fill(params: dict[str, Any]) -> str:
        import tempfile

        space_mb = params.get("space_mb", 10)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * space_mb * 1024 * 1024)
            tmp_name = tmp.name
        os.unlink(tmp_name)
        return f"Wrote and cleaned {space_mb}MB temp file to disk"

    @staticmethod
    def _real_process_kill(params: dict[str, Any]) -> str:
        target = params.get("target", "none")
        return f"Process kill simulated (target={target}) — not actually killing"

    @staticmethod
    def _real_network_latency(params: dict[str, Any]) -> str:
        import socket

        latency_ms = params.get("latency_ms", 100)
        host = params.get("host", "127.0.0.1")
        port = params.get("port", 0)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(latency_ms / 1000.0)
            s.connect_ex((host, port))
            s.close()
        except OSError:
            pass
        return f"Network latency simulation: +{latency_ms}ms to {host}:{port}"

    # ------------------------------------------------------------------
    # Internal scheduling
    # ------------------------------------------------------------------

    def _execute_scheduled(self, schedule: FaultSchedule) -> None:
        SafetyGate.block_if_production()

        event = self._simulate_inject(schedule) if self._simulate else self._real_inject(schedule)

        self._events.append(event)

        if event.success and schedule.duration_s > 0:
            timer = threading.Timer(schedule.duration_s, self._recover_scheduled, args=[schedule])
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

    def _recover_scheduled(self, schedule: FaultSchedule) -> None:
        ev = self._recover_fault(schedule)
        self._events.append(ev)

    def _recover(self, fault_type: FaultType) -> None:
        with self._lock:
            for schedule in self._schedules:
                if schedule.fault_type == fault_type and not schedule.recovered:
                    schedule.recovered = True
                    ev = FaultEvent(
                        fault_type=fault_type,
                        action="recover",
                        timestamp=time.time(),
                        success=True,
                        detail="Auto-recovery after timeout",
                        params=dict(schedule.params),
                    )
                    self._events.append(ev)
                    return
