from __future__ import annotations

from enum import Enum


class HarnessLifecycleState(str, Enum):
    INIT = "init"
    PREFLIGHT = "preflight"
    READY = "ready"
    RUNNING = "running"
    VALIDATING = "validating"
    REPORTING = "reporting"
    DONE = "done"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[HarnessLifecycleState, list[HarnessLifecycleState]] = {
    HarnessLifecycleState.INIT: [HarnessLifecycleState.PREFLIGHT, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.PREFLIGHT: [HarnessLifecycleState.READY, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.READY: [HarnessLifecycleState.RUNNING, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.RUNNING: [
        HarnessLifecycleState.VALIDATING,
        HarnessLifecycleState.FAILED,
    ],
    HarnessLifecycleState.VALIDATING: [
        HarnessLifecycleState.REPORTING,
        HarnessLifecycleState.FAILED,
    ],
    HarnessLifecycleState.REPORTING: [HarnessLifecycleState.DONE, HarnessLifecycleState.FAILED],
    HarnessLifecycleState.DONE: [],
    HarnessLifecycleState.FAILED: [],
}
