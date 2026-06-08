"""Harness 审计日志集成。

封装 governance/audit.py 的 AuditLogger，在 harness 生命周期阶段自动写入。
"""

from __future__ import annotations

from typing import Any

from maref.execution.harness.types import HarnessResult
from maref.governance.audit import AuditEntry, AuditLogger


class HarnessAuditLogger:
    """Harness 生命周期审计日志封装。

    自动记录 START → PREFLIGHT → STEP → VALIDATE → STOP/FAIL 事件链。
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self._logger = audit_logger or AuditLogger()
        self._events: list[AuditEntry] = []
        self._harness_type = ""
        self._round_id = ""

    def start_round(self, harness_type: str, round_id: str) -> None:
        self._harness_type = harness_type
        self._round_id = round_id
        self._log("harness_start", "start_round", f"Run {harness_type}/{round_id}")

    def clear_events(self) -> None:
        self._events.clear()

    def log_preflight(self, warnings: list[str]) -> None:
        details = f"preflight with {len(warnings)} warning(s): {'; '.join(warnings)}" if warnings else "preflight passed"
        self._log("harness_preflight", "preflight", details)

    def log_step(self, step_id: str, step_result: str = "ok") -> None:
        self._log("harness_step", f"step:{step_id}", f"result={step_result}")

    def log_validate(self, passed: bool) -> None:
        self._log("harness_validate", "validate", f"validation={'passed' if passed else 'failed'}")

    def log_stop(self, result: HarnessResult) -> None:
        self._log(
            "harness_stop", "stop",
            f"status={result.status.value}, duration={result.duration_s:.2f}s, errors={len(result.errors)}",
            metadata={"errors": result.errors[:5]},
        )

    def log_fail(self, reason: str) -> None:
        self._log("harness_fail", "fail", f"reason={reason}")

    def get_events(self, max_entries: int = 100) -> list[AuditEntry]:
        return self._events[-max_entries:]

    def get_event_chain(self) -> list[str]:
        return [f"{e.event_type}:{e.action}" for e in self._events]

    def count(self) -> int:
        return len(self._events)

    def _log(self, event_type: str, action: str, details: str = "", metadata: dict[str, Any] | None = None) -> AuditEntry:
        entry = self._logger.log(
            event_type=event_type,
            actor=f"UnifiedHarness/{self._harness_type}",
            action=action,
            details=details,
            metadata={
                "round_id": self._round_id,
                "harness_type": self._harness_type,
                **(metadata or {}),
            },
        )
        self._events.append(entry)
        return entry
