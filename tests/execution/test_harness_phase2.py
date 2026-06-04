"""Phase 2 测试：Hook 系统 + 运行时权限 + 审计日志集成。"""

from __future__ import annotations

from typing import Any

import pytest

from maref.execution.harness.audit_integration import HarnessAuditLogger
from maref.execution.harness.exceptions import HarnessAbortedError
from maref.execution.harness.hooks import HARNESS_TOPICS, HarnessHookRegistry
from maref.execution.harness.lifecycle import HarnessLifecycleState
from maref.execution.harness.permission_hooks import AllowlistPermissionHook, PermissionHook
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.execution.harness.unified import UnifiedHarness
from maref.governance.audit import AuditLogger
from maref.recursive.hook_registry import HookResult, HookVerdict


# ── HarnessHookRegistry ────────────────────────────────────────────────

class TestHarnessHookRegistry:
    def test_all_seven_topics_defined(self) -> None:
        assert len(HARNESS_TOPICS) == 7
        assert "harness.start" in HARNESS_TOPICS
        assert "harness.preflight" in HARNESS_TOPICS
        assert "harness.step" in HARNESS_TOPICS
        assert "harness.stop" in HARNESS_TOPICS
        assert "harness.fail" in HARNESS_TOPICS
        assert "harness.validate" in HARNESS_TOPICS
        assert "harness.tool_call" in HARNESS_TOPICS

    def test_register_handler(self) -> None:
        reg = HarnessHookRegistry()
        def handler(data: dict[str, Any]) -> HookResult:
            return HookResult(verdict=HookVerdict.PASS, handler_id="test")
        hid = reg.register("harness.start", handler)
        assert reg.is_registered("harness.start")
        assert len(reg.get_chain("harness.start")) == 1

    def test_fire_pass_returns_success(self) -> None:
        reg = HarnessHookRegistry()
        def handler(data: dict[str, Any]) -> HookResult:
            return HookResult(verdict=HookVerdict.PASS, handler_id="pass_handler")
        reg.register("harness.start", handler)
        result = reg.fire("harness.start", {"msg": "hello"})
        assert result.passed
        assert result.verdict == HookVerdict.PASS

    def test_fire_block_stops_chain(self) -> None:
        reg = HarnessHookRegistry()
        calls: list[str] = []
        def blocker(data: dict[str, Any]) -> HookResult:
            calls.append("blocker")
            return HookResult(verdict=HookVerdict.BLOCK, handler_id="blocker", message="nope")
        def after_blocker(data: dict[str, Any]) -> HookResult:
            calls.append("after_blocker")
            return HookResult(verdict=HookVerdict.PASS, handler_id="after")
        reg.register("harness.step", blocker, priority=100)
        reg.register("harness.step", after_blocker, priority=0)
        result = reg.fire("harness.step", {})
        assert not result.passed
        assert result.verdict == HookVerdict.BLOCK
        assert calls == ["blocker"]

    def test_fire_unknown_topic_no_error(self) -> None:
        reg = HarnessHookRegistry()
        result = reg.fire("harness.start", {})
        assert result.passed

    def test_register_invalid_topic_raises(self) -> None:
        reg = HarnessHookRegistry()
        with pytest.raises(ValueError, match="Unknown harness topic"):
            reg.register("invalid.topic", lambda d: HookResult(verdict=HookVerdict.PASS))

    def test_unregister_handler(self) -> None:
        reg = HarnessHookRegistry()
        def handler(data: dict[str, Any]) -> HookResult:
            return HookResult(verdict=HookVerdict.PASS, handler_id="test")
        hid = reg.register("harness.start", handler)
        assert reg.unregister("harness.start", hid)
        assert not reg.is_registered("harness.start")

    def test_clear_removes_all(self) -> None:
        reg = HarnessHookRegistry()
        reg.register("harness.start", lambda d: HookResult(verdict=HookVerdict.PASS))
        reg.register("harness.stop", lambda d: HookResult(verdict=HookVerdict.PASS))
        reg.clear()
        assert not reg.is_registered("harness.start")
        assert not reg.is_registered("harness.stop")

    def test_multiple_handlers_fire_all_pass(self) -> None:
        reg = HarnessHookRegistry()
        results: list[int] = []
        def h1(data: dict[str, Any]) -> HookResult:
            results.append(1)
            return HookResult(verdict=HookVerdict.PASS, handler_id="h1")
        def h2(data: dict[str, Any]) -> HookResult:
            results.append(2)
            return HookResult(verdict=HookVerdict.PASS, handler_id="h2")
        reg.register("harness.validate", h1)
        reg.register("harness.validate", h2)
        result = reg.fire("harness.validate", {})
        assert result.passed
        assert results == [1, 2]

    def test_fire_returns_chain_result_metadata(self) -> None:
        reg = HarnessHookRegistry()
        reg.register("harness.stop", lambda d: HookResult(
            verdict=HookVerdict.PASS, handler_id="meta_test", message="done"
        ), handler_id="meta_handler")
        result = reg.fire("harness.stop", {"key": "val"})
        assert result.total_duration_ms >= 0
        assert len(result.execution_stack.entries) == 1
        assert result.execution_stack.entries[0]["handler_id"] == "meta_handler"


# ── PermissionHook ─────────────────────────────────────────────────────

class TestPermissionHook:
    def test_blocks_destructive_operation_rm_rf(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        result = reg.fire("harness.tool_call", {"tool": "rm", "args": "-rf /"})
        assert not result.passed
        assert "Permission denied" in result.execution_stack.entries[0]["message"]

    def test_blocks_drop_table(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        result = reg.fire("harness.tool_call", {"tool": "sql", "args": "DROP TABLE users"})
        assert not result.passed

    def test_blocks_git_force_push(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        result = reg.fire("harness.tool_call", {"tool": "git push --force origin main"})
        assert not result.passed

    def test_allows_safe_operation(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        result = reg.fire("harness.tool_call", {"tool": "ls", "args": "-la"})
        assert result.passed

    def test_allows_read_operation(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        result = reg.fire("harness.tool_call", {"tool": "cat", "args": "README.md"})
        assert result.passed

    def test_multiple_checks_all_safe(self) -> None:
        reg = HarnessHookRegistry()
        PermissionHook(reg)
        for tool in ["status", "help", "list"]:
            result = reg.fire("harness.tool_call", {"tool": tool})
            assert result.passed


# ── AllowlistPermissionHook ────────────────────────────────────────────

class TestAllowlistPermissionHook:
    def test_allows_listed_tools(self) -> None:
        reg = HarnessHookRegistry()
        AllowlistPermissionHook(reg, allowed_tools={"read", "write"})
        assert reg.fire("harness.tool_call", {"tool": "read"}).passed
        assert reg.fire("harness.tool_call", {"tool": "write"}).passed

    def test_blocks_unlisted_tools(self) -> None:
        reg = HarnessHookRegistry()
        AllowlistPermissionHook(reg, allowed_tools={"read"})
        result = reg.fire("harness.tool_call", {"tool": "delete"})
        assert not result.passed
        assert "not in allowlist" in result.execution_stack.entries[0]["message"]


# ── HarnessAuditLogger ─────────────────────────────────────────────────

class TestHarnessAuditLogger:
    def test_start_round_creates_first_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "round_1")
        assert audit.count() == 1
        assert audit.get_events()[0].event_type == "harness_start"

    def test_preflight_creates_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_preflight(["warn1"])
        assert any(e.event_type == "harness_preflight" for e in audit.get_events())

    def test_step_creates_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_step("step_0", "ok")
        assert any(e.event_type == "harness_step" for e in audit.get_events())

    def test_validate_creates_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_validate(True)
        assert any(e.event_type == "harness_validate" for e in audit.get_events())

    def test_stop_creates_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_stop(HarnessResult(status=HarnessStatus.SUCCEEDED, duration_s=1.0))
        assert any(e.event_type == "harness_stop" for e in audit.get_events())

    def test_fail_creates_event(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_fail("something broke")
        assert any(e.event_type == "harness_fail" for e in audit.get_events())

    def test_event_chain_order(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "r1")
        audit.log_preflight([])
        audit.log_step("step_0", "ok")
        audit.log_validate(True)
        audit.log_stop(HarnessResult(status=HarnessStatus.SUCCEEDED))
        chain = audit.get_event_chain()
        assert chain[0] == "harness_start:start_round"
        assert chain[1] == "harness_preflight:preflight"
        assert chain[2] == "harness_step:step:step_0"
        assert chain[3] == "harness_validate:validate"
        assert chain[4] == "harness_stop:stop"

    def test_events_contain_metadata(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        audit.start_round("unified", "special_round")
        entry = audit.get_events()[0]
        assert entry.metadata["round_id"] == "special_round"
        assert entry.metadata["harness_type"] == "unified"


# ── UnifiedHarness 集成测试 ─────────────────────────────────────────────

class TestUnifiedHarnessIntegration:
    def test_hook_fires_during_lifecycle(self) -> None:
        reg = HarnessHookRegistry()
        hook_calls: list[str] = []
        def track(topic: str) -> Any:
            def handler(data: dict[str, Any]) -> HookResult:
                hook_calls.append(topic)
                return HookResult(verdict=HookVerdict.PASS, handler_id="track")
            return handler
        reg.register("harness.start", track("harness.start"))
        reg.register("harness.stop", track("harness.stop"))

        harness = UnifiedHarness(hook_registry=reg)
        harness.configure(HarnessConfig())
        harness.preflight()
        harness.run()
        assert "harness.start" in hook_calls
        assert "harness.stop" in hook_calls

    def test_hook_block_aborts_execution(self) -> None:
        reg = HarnessHookRegistry()
        def block_start(data: dict[str, Any]) -> HookResult:
            return HookResult(verdict=HookVerdict.BLOCK, handler_id="blocker", message="no way")
        reg.register("harness.start", block_start, priority=100)

        harness = UnifiedHarness(hook_registry=reg)
        harness.configure(HarnessConfig())
        harness.preflight()
        with pytest.raises(HarnessAbortedError, match="harness.start"):
            harness.run()

    def test_audit_logger_records_lifecycle(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        harness = UnifiedHarness(audit_logger=audit)
        harness.configure(HarnessConfig())
        harness.preflight()
        harness.run()
        chain = audit.get_event_chain()
        assert "harness_start:start_round" in chain
        assert "harness_stop:stop" in chain
        assert audit.count() >= 4  # start, preflight, validate, stop

    def test_hook_registry_property(self) -> None:
        reg = HarnessHookRegistry()
        harness = UnifiedHarness(hook_registry=reg)
        assert harness._hook_registry is reg

    def test_audit_logger_logs_failure(self) -> None:
        audit = HarnessAuditLogger(AuditLogger())
        harness = UnifiedHarness(audit_logger=audit)
        harness.configure(HarnessConfig())
        harness.preflight()
        def crash() -> None:
            raise RuntimeError("explosion")
        harness.add_step_handler(crash)
        result = harness.run()
        assert result.status == HarnessStatus.FAILED
        chain = audit.get_event_chain()
        assert any("harness_fail" in e for e in chain)
