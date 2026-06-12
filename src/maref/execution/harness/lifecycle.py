from __future__ import annotations

from enum import Enum


class HarnessLifecycleState(Enum):
    """UnifiedHarness 生命周期状态 — 单向推进，异常时 -> FAILED。"""
    INIT = "init"
    PREFLIGHT = "preflight"
    READY = "ready"
    RUNNING = "running"
    VALIDATING = "validating"
    REPORTING = "reporting"
    DONE = "done"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[HarnessLifecycleState, list[HarnessLifecycleState]] = {
    HarnessLifecycleState.INIT: [HarnessLifecycleState.PREFLIGHT],
    HarnessLifecycleState.PREFLIGHT: [HarnessLifecycleState.READY, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.READY: [HarnessLifecycleState.RUNNING],
    HarnessLifecycleState.RUNNING: [HarnessLifecycleState.VALIDATING, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.VALIDATING: [HarnessLifecycleState.REPORTING, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.REPORTING: [HarnessLifecycleState.DONE, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.DONE: [],
    HarnessLifecycleState.FAILED: [],
}
