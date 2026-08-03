"""v0.47 S11 — TaskPreflight wired into UnifiedHarness.preflight.

1. ``UnifiedHarness`` gains an optional ``task_preflight``.  When provided,
   ``preflight(context)`` runs the TaskPreflight battery (6 checks); any
   FAIL aborts the harness (fail-closed, HarnessAbortedError) instead of
   proceeding.

2. The risk-authorization check becomes a hard gate: an out-of-bounds /
   unauthorized action blocks execution, not merely a soft warning.

3. Without ``task_preflight`` the harness keeps its historical behaviour
   (backward compatible).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.execution.harness import UnifiedHarness
from maref.execution.harness.exceptions import HarnessAbortedError
from maref.execution.harness.lifecycle import HarnessLifecycleState
from maref.execution.harness.types import HarnessConfig
from maref.governance.task_preflight import TaskPreflight


def _full_context() -> dict[str, object]:
    return {
        "agent_id": "agent-01",
        "task_description": "Generate launch video",
        "readme_read": True,
        "readme_summary": "Project has video_producer.py",
        "selected_pipeline": "video_producer",
        "git_log_consulted": True,
        "git_log_entries": 5,
        "alternatives_considered": ["produce_launch.js", "video_producer.py"],
        "alternatives_rationale": "video_producer.py is the official pipeline",
        "decision_logged": True,
        "decision_log_location": "audit://20260716/launch-video",
        # Risk authorization: LOW-risk action passes without a scope.
        "action": "file.read",
    }


class TestPreflightWiring:
    def test_preflight_with_task_preflight_passes_complete_context(self) -> None:
        h = UnifiedHarness(task_preflight=TaskPreflight())
        h.configure(HarnessConfig())
        warnings = h.preflight(context=_full_context())
        assert h.lifecycle_state == HarnessLifecycleState.READY
        assert isinstance(warnings, list)

    def test_preflight_fails_closed_on_missing_evidence(self) -> None:
        """Missing README/git/alternatives evidence aborts the harness."""
        h = UnifiedHarness(task_preflight=TaskPreflight())
        h.configure(HarnessConfig())
        with pytest.raises(HarnessAbortedError, match="preflight"):
            h.preflight(context={"agent_id": "agent-01", "task_description": "t"})
        assert h.lifecycle_state == HarnessLifecycleState.FAILED

    def test_risk_authorization_blocks_high_risk_without_scope(self) -> None:
        """HIGH-risk action with no scope → hard block (fail-closed)."""
        h = UnifiedHarness(task_preflight=TaskPreflight())
        h.configure(HarnessConfig())
        ctx = dict(_full_context())
        ctx["action"] = "file.delete"
        with pytest.raises(HarnessAbortedError, match="preflight"):
            h.preflight(context=ctx)
        assert h.lifecycle_state == HarnessLifecycleState.FAILED

    def test_no_task_preflight_backward_compatible(self) -> None:
        """Without task_preflight, preflight keeps historical behaviour."""
        h = UnifiedHarness()
        h.configure(HarnessConfig())
        warnings = h.preflight()
        assert h.lifecycle_state == HarnessLifecycleState.READY

    def test_preflight_result_exposed(self) -> None:
        """The preflight result is available after a successful run."""
        h = UnifiedHarness(task_preflight=TaskPreflight())
        h.configure(HarnessConfig())
        h.preflight(context=_full_context())
        assert h.last_preflight is not None
        assert h.last_preflight.passed is True


class TestRiskAuthorizationHardGate:
    def test_risk_check_is_hard_gate_not_soft_warning(self) -> None:
        """RiskAuthorizationCheck FAILs a HIGH-risk unauthorized action —
        the harness aborts rather than warning-and-continue."""
        from maref.governance.task_preflight import RiskAuthorizationCheck

        check = RiskAuthorizationCheck()
        result = check.execute(
            {
                "action": "file.delete",
                "agent_id": "agent-01",
            }
        )
        assert result.status.value == "FAIL"
        assert result.details.get("action_required") == "HITL"
