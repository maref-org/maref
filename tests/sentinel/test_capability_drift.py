"""test_capability_drift — CapabilityDriftDetector 漂移检测测试

覆盖验收标准:
- 2.2-A2: 检测 '声明 network_read 但实际 network_write' → DriftItem
- 2.2-A3: CapabilityDriftReport 写入 UnifiedAuditStore,触发 ThreatGovernanceBridge
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from maref.sentinel.drift.capability_drift_detector import (
    CapabilityDriftDetector,
    CapabilityDriftReport,
    DriftItem,
    DriftSeverity,
    DriftType,
)
from maref.sentinel.platform.macos.xpc_bridge import ESFEvent, ESFEventType

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-drift-hmac-key"


def _esf_event(
    event_id: str = "evt-001",
    event_type: ESFEventType = ESFEventType.EXEC,
    seq: int = 1,
    pid: int = 100,
    agent_id: str = "agent-test",
    path: str = "/bin/ls",
    argv: list[str] | None = None,
    remote_addr: str = "",
    remote_port: int = 0,
    evidence: dict[str, Any] | None = None,
) -> ESFEvent:
    return ESFEvent(
        event_id=event_id,
        event_type=event_type,
        seq=seq,
        timestamp=time.time(),
        pid=pid,
        ppid=50,
        agent_id=agent_id,
        path=path,
        argv=argv or [],
        remote_addr=remote_addr,
        remote_port=remote_port,
        evidence=evidence or {},
        hmac_signature="",
    )


# ---------------------------------------------------------------------------
# DriftItem tests
# ---------------------------------------------------------------------------


class TestDriftItem:
    def test_default_values(self) -> None:
        d = DriftItem()
        assert d.item_id  # UUID
        assert d.drift_type == DriftType.CAPABILITY_OVERFLOW
        assert d.severity == DriftSeverity.LOW

    def test_with_values(self) -> None:
        d = DriftItem(
            drift_type=DriftType.UNDECLARED_PTRACE,
            severity=DriftSeverity.CRITICAL,
            agent_id="agent-x",
            expected_capability="ptrace",
            observed_behavior="ptrace attach attempt",
        )
        assert d.drift_type == DriftType.UNDECLARED_PTRACE
        assert d.severity == DriftSeverity.CRITICAL
        assert d.agent_id == "agent-x"

    def test_is_frozen(self) -> None:
        d = DriftItem()
        with pytest.raises((AttributeError, Exception)):
            d.agent_id = "modified"  # type: ignore[misc]


class TestDriftSeverityMapping:
    """漂移类型 → 严重程度映射完整性"""

    def test_all_drift_types_have_severity(self) -> None:
        """每个 DriftType 都应有对应的 DriftSeverity"""
        from maref.sentinel.drift.capability_drift_detector import _DRIFT_SEVERITY

        for dt in DriftType:
            assert dt in _DRIFT_SEVERITY, f"missing severity for {dt.value}"

    def test_undeclared_ptrace_is_critical(self) -> None:
        from maref.sentinel.drift.capability_drift_detector import _DRIFT_SEVERITY

        assert _DRIFT_SEVERITY[DriftType.UNDECLARED_PTRACE] == DriftSeverity.CRITICAL

    def test_undeclared_setuid_is_critical(self) -> None:
        from maref.sentinel.drift.capability_drift_detector import _DRIFT_SEVERITY

        assert _DRIFT_SEVERITY[DriftType.UNDECLARED_SETUID] == DriftSeverity.CRITICAL

    def test_endpoint_drift_is_low(self) -> None:
        from maref.sentinel.drift.capability_drift_detector import _DRIFT_SEVERITY

        assert _DRIFT_SEVERITY[DriftType.ENDPOINT_DRIFT] == DriftSeverity.LOW


# ---------------------------------------------------------------------------
# CapabilityDriftReport tests
# ---------------------------------------------------------------------------


class TestCapabilityDriftReport:
    def test_default_values(self) -> None:
        r = CapabilityDriftReport()
        assert r.report_id  # UUID
        assert r.total_drifts == 0
        assert r.hmac_signature == ""

    def test_with_hash_returns_new_instance(self) -> None:
        r = CapabilityDriftReport(agent_id="a1", total_drifts=3)
        signed = r.with_hash(HMAC_KEY)
        assert signed is not r
        assert signed.hmac_signature != ""
        assert r.hmac_signature == ""

    def test_verify_valid_signature(self) -> None:
        r = CapabilityDriftReport(agent_id="a1", total_drifts=3)
        signed = r.with_hash(HMAC_KEY)
        assert signed.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        r = CapabilityDriftReport(agent_id="a1")
        assert r.verify(HMAC_KEY) is False

    def test_verify_tampered_returns_false(self) -> None:
        r = CapabilityDriftReport(agent_id="a1", total_drifts=3)
        signed = r.with_hash(HMAC_KEY)
        tampered = CapabilityDriftReport(
            **{**signed.__dict__, "total_drifts": 999}
        )
        assert tampered.verify(HMAC_KEY) is False

    def test_to_audit_payload_excludes_drift_item_details(self) -> None:
        item = DriftItem(
            drift_type=DriftType.UNDECLARED_NETWORK,
            severity=DriftSeverity.HIGH,
            agent_id="a1",
        )
        r = CapabilityDriftReport(
            agent_id="a1",
            drift_items=[item],
            total_drifts=1,
            high_count=1,
            max_severity=DriftSeverity.HIGH,
        )
        payload = r.to_audit_payload()
        assert payload["total_drifts"] == 1
        assert len(payload["drift_items"]) == 1
        assert payload["drift_items"][0]["drift_type"] == "undeclared_network"
        # detail evidence 不应写入 payload (避免体积过大)
        assert "evidence" not in payload

    def test_to_observation_event_uses_privilege_abuse(self) -> None:
        r = CapabilityDriftReport(
            agent_id="a1",
            max_severity=DriftSeverity.CRITICAL,
        )
        signed = r.with_hash(HMAC_KEY)
        evt = signed.to_observation_event()
        assert evt.source == "capability_drift_detector"
        assert evt.attack_type.value == "privilege_abuse"

    def test_to_observation_event_severity_maps_correctly(self) -> None:
        """CRITICAL drift → CRITICAL ObservationEvent"""
        from maref.sentinel.event import Severity

        r = CapabilityDriftReport(max_severity=DriftSeverity.CRITICAL)
        signed = r.with_hash(HMAC_KEY)
        evt = signed.to_observation_event()
        assert evt.severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# CapabilityDriftDetector — Registration tests
# ---------------------------------------------------------------------------


class TestDetectorRegistration:
    def test_register_agent(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="agent-x",
            declared_capabilities=["network_read", "file_read"],
            declared_endpoints=["api.example.com:443"],
        )
        assert "agent-x" in detector.list_registered_agents()

    def test_register_without_endpoints(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="agent-x",
            declared_capabilities=["file_read"],
        )
        assert "agent-x" in detector.list_registered_agents()

    def test_unregister_agent(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="agent-x", declared_capabilities=[])
        assert "agent-x" in detector.list_registered_agents()
        detector.unregister_agent("agent-x")
        assert detector.list_registered_agents() == []

    def test_unregister_nonexistent(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.unregister_agent("ghost")  # 不应抛异常

    def test_snapshot_after_registration(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        snap = detector.snapshot()
        assert snap["registered_agents"] == 1
        assert "a1" in snap["agents"]


# ---------------------------------------------------------------------------
# CapabilityDriftDetector — 2.2-A2 drift detection tests
# ---------------------------------------------------------------------------


class TestConnectDrift:
    """connect 事件漂移检测 — 2.2-A2"""

    def test_undeclared_network_connect(self) -> None:
        """未声明 network → connect 是 HIGH 漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])
        event = _esf_event(
            event_type=ESFEventType.CONNECT,
            agent_id="a1",
            remote_addr="93.184.216.34",
            remote_port=443,
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_NETWORK
        assert drifts[0].severity == DriftSeverity.HIGH
        assert drifts[0].expected_capability == "network_read"

    def test_network_read_connect_not_drift(self) -> None:
        """声明 network_read → connect 无漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_read"],
            declared_endpoints=["93.184.216.34:443"],
        )
        event = _esf_event(
            event_type=ESFEventType.CONNECT,
            agent_id="a1",
            remote_addr="93.184.216.34",
            remote_port=443,
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0

    def test_connect_endpoint_drift(self) -> None:
        """声明 network_read + 端点白名单 → 连接未声明端点是 LOW 漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_read"],
            declared_endpoints=["api.example.com:443"],
        )
        event = _esf_event(
            event_type=ESFEventType.CONNECT,
            agent_id="a1",
            remote_addr="evil.com",
            remote_port=443,
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.ENDPOINT_DRIFT
        assert drifts[0].severity == DriftSeverity.LOW

    def test_connect_endpoint_match_ignores_port(self) -> None:
        """端点匹配应容忍端口差异 (partial match)"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_read"],
            declared_endpoints=["api.example.com"],
        )
        event = _esf_event(
            event_type=ESFEventType.CONNECT,
            agent_id="a1",
            remote_addr="api.example.com",
            remote_port=443,
        )
        drifts = detector.observe(event)
        # 域名匹配成功,无漂移
        assert len(drifts) == 0


class TestBindDrift:
    """bind 事件漂移检测 — network_write 未声明"""

    def test_bind_without_network_write(self) -> None:
        """声明 network_read 但 bind → MEDIUM 漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_read"],
        )
        event = _esf_event(
            event_type=ESFEventType.BIND,
            agent_id="a1",
            remote_port=8080,
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_NETWORK_WRITE
        assert drifts[0].expected_capability == "network_write"

    def test_bind_with_network_write_not_drift(self) -> None:
        """声明 network_write → bind 无漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_write"],
        )
        event = _esf_event(
            event_type=ESFEventType.BIND,
            agent_id="a1",
            remote_port=8080,
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


class TestExecDrift:
    """exec 事件漂移检测"""

    def test_exec_without_process_exec_is_drift(self) -> None:
        """未声明 process_exec → exec 是 HIGH 漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        event = _esf_event(
            event_type=ESFEventType.EXEC,
            agent_id="a1",
            path="/bin/bash",
            argv=["bash", "-c", "curl http://evil.com"],
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_PROCESS_EXEC
        assert drifts[0].expected_capability == "process_exec"
        assert drifts[0].observed_behavior == "exec /bin/bash argv=['bash', '-c', 'curl http://evil.com']"

    def test_exec_with_process_exec_not_drift(self) -> None:
        """声明 process_exec → exec 无漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["process_exec"])
        event = _esf_event(
            event_type=ESFEventType.EXEC,
            agent_id="a1",
            path="/usr/bin/env",
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


class TestForkDrift:
    """fork 事件漂移检测"""

    def test_fork_without_process_spawn_is_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        event = _esf_event(
            event_type=ESFEventType.FORK,
            agent_id="a1",
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_FORK
        assert drifts[0].expected_capability == "process_spawn"

    def test_fork_with_process_spawn_not_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["process_spawn"])
        event = _esf_event(
            event_type=ESFEventType.FORK,
            agent_id="a1",
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0

    def test_fork_with_process_exec_not_drift(self) -> None:
        """process_exec 应覆盖 fork (exec 前通常 fork)"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["process_exec"])
        event = _esf_event(
            event_type=ESFEventType.FORK,
            agent_id="a1",
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


class TestOpenDrift:
    """open 事件漂移检测"""

    def test_open_write_without_file_write_is_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])
        event = _esf_event(
            event_type=ESFEventType.OPEN,
            agent_id="a1",
            path="/etc/some.conf",
            evidence={"flags": "O_WRONLY"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_FILE_WRITE
        assert drifts[0].expected_capability == "file_write"

    def test_open_read_without_file_read_is_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        event = _esf_event(
            event_type=ESFEventType.OPEN,
            agent_id="a1",
            path="/etc/passwd",
            evidence={"flags": "O_RDONLY"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.CAPABILITY_OVERFLOW
        assert drifts[0].expected_capability == "file_read"

    def test_open_read_with_file_read_not_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])
        event = _esf_event(
            event_type=ESFEventType.OPEN,
            agent_id="a1",
            path="/usr/lib/libfoo.so",
            evidence={"flags": "O_RDONLY"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


class TestSetuidDrift:
    """setuid 事件漂移检测 — CRITICAL"""

    def test_setuid_without_declaration_is_critical(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        event = _esf_event(
            event_type=ESFEventType.SETUID,
            agent_id="a1",
            evidence={"uid": 0},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_SETUID
        assert drifts[0].severity == DriftSeverity.CRITICAL
        assert drifts[0].expected_capability == "setuid"

    def test_setuid_with_declaration_not_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["setuid"])
        event = _esf_event(
            event_type=ESFEventType.SETUID,
            agent_id="a1",
            evidence={"uid": 1000},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


class TestSignalDrift:
    """signal 事件漂移检测 — ptrace 通过 signal 实现"""

    def test_signal_sigstop_without_ptrace_is_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        event = _esf_event(
            event_type=ESFEventType.SIGNAL,
            agent_id="a1",
            evidence={"signal": "SIGSTOP"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1
        assert drifts[0].drift_type == DriftType.UNDECLARED_PTRACE
        assert drifts[0].severity == DriftSeverity.CRITICAL
        assert drifts[0].expected_capability == "ptrace"

    def test_signal_sigtrap_without_ptrace_is_drift(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        event = _esf_event(
            event_type=ESFEventType.SIGNAL,
            agent_id="a1",
            evidence={"signal": "SIGTRAP"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 1

    def test_signal_normal_without_ptrace_not_drift(self) -> None:
        """非 ptrace 相关 signal (USR1) 不应触发漂移"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        event = _esf_event(
            event_type=ESFEventType.SIGNAL,
            agent_id="a1",
            evidence={"signal": "SIGUSR1"},
        )
        drifts = detector.observe(event)
        assert len(drifts) == 0


# ---------------------------------------------------------------------------
# Bulk observation & report generation
# ---------------------------------------------------------------------------


class TestBulkObservation:
    """批量观测 + 报告生成"""

    def test_observe_batch_returns_all_drifts(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])

        events = [
            _esf_event(event_type=ESFEventType.CONNECT, agent_id="a1", remote_addr="1.2.3.4", remote_port=443, seq=1),
            _esf_event(event_type=ESFEventType.EXEC, agent_id="a1", path="/bin/sh", seq=2),
            _esf_event(event_type=ESFEventType.OPEN, agent_id="a1", path="/tmp/test", evidence={"flags": "O_RDONLY"}, seq=3),
        ]
        all_drifts = detector.observe_batch(events)
        assert len(all_drifts) == 2  # connect + exec → drift; open → no drift (file_read declared)

    def test_observe_unregistered_agent_returns_empty(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        event = _esf_event(agent_id="unknown-agent", event_type=ESFEventType.EXEC)
        drifts = detector.observe(event)
        assert len(drifts) == 0

    def test_observe_empty_agent_id_returns_empty(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        event = _esf_event(agent_id="")
        drifts = detector.observe(event)
        assert len(drifts) == 0

    def test_generate_report_without_drifts(self) -> None:
        """无漂移时报告 total_drifts=0"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        report = detector.generate_report("a1")
        assert report.total_drifts == 0
        assert report.max_severity == DriftSeverity.LOW

    def test_generate_report_with_drifts(self) -> None:
        """有漂移时报告统计准确"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])

        # 注入 3 个漂移事件
        detector.observe(_esf_event(event_type=ESFEventType.EXEC, agent_id="a1", seq=1))
        detector.observe(_esf_event(event_type=ESFEventType.CONNECT, agent_id="a1", remote_addr="x.com", remote_port=443, seq=2))
        detector.observe(_esf_event(event_type=ESFEventType.SETUID, agent_id="a1", evidence={"uid": 0}, seq=3))

        report = detector.generate_report("a1")
        assert report.total_drifts == 3
        assert report.high_count >= 1  # exec + connect
        assert report.critical_count == 1  # setuid
        assert report.max_severity == DriftSeverity.CRITICAL

    def test_generate_report_resets_pending_drifts(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])
        detector.observe(_esf_event(event_type=ESFEventType.EXEC, agent_id="a1", seq=1))
        assert len(detector.get_pending_drifts("a1")) == 1
        detector.generate_report("a1")
        assert len(detector.get_pending_drifts("a1")) == 0

    def test_generate_report_unknown_agent(self) -> None:
        """未注册 Agent → 空报告"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        report = detector.generate_report("ghost")
        assert report.total_drifts == 0
        assert report.agent_id == "ghost"


class TestQuarantineTrigger:
    """CRITICAL 漂移 → quarantine 触发"""

    def test_critical_drift_triggers_quarantine_callback(self) -> None:
        """CRITICAL 漂移应自动触发隔离回调 (2.3-A3 implied)"""
        triggered: list[str] = []

        # sync callback — 避免 async create_task 调度延迟
        def quarantine_cb(agent_id: str) -> None:
            triggered.append(agent_id)

        detector = CapabilityDriftDetector(
            hmac_key=HMAC_KEY,
            quarantine_callback=quarantine_cb,
            critical_drift_triggers_quarantine=True,
        )
        detector.register_agent(agent_id="a1", declared_capabilities=["file_read"])

        # CRITICAL: setuid
        detector.observe(_esf_event(
            event_type=ESFEventType.SETUID,
            agent_id="a1",
            evidence={"uid": 0},
            seq=1,
        ))
        assert len(triggered) == 1
        assert triggered[0] == "a1"

    def test_low_drift_does_not_trigger_quarantine(self) -> None:
        """LOW 漂移不应触发隔离"""
        triggered: list[str] = []

        def quarantine_cb(agent_id: str) -> None:
            triggered.append(agent_id)

        detector = CapabilityDriftDetector(
            hmac_key=HMAC_KEY,
            quarantine_callback=quarantine_cb,
        )
        detector.register_agent(
            agent_id="a1",
            declared_capabilities=["network_read"],
            declared_endpoints=["api.x.com:443"],
        )
        # LOW: endpoint drift
        detector.observe(_esf_event(
            event_type=ESFEventType.CONNECT,
            agent_id="a1",
            remote_addr="other.com",
            remote_port=443,
            seq=1,
        ))
        assert len(triggered) == 0

    def test_quarantine_disabled(self) -> None:
        """critical_drift_triggers_quarantine=False 不触发隔离"""
        triggered: list[str] = []

        def quarantine_cb(agent_id: str) -> None:
            triggered.append(agent_id)

        detector = CapabilityDriftDetector(
            hmac_key=HMAC_KEY,
            quarantine_callback=quarantine_cb,
            critical_drift_triggers_quarantine=False,
        )
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        detector.observe(_esf_event(
            event_type=ESFEventType.SETUID,
            agent_id="a1",
            evidence={"uid": 0},
            seq=1,
        ))
        assert len(triggered) == 0

    def test_quarantine_callback_exception_swallowed(self) -> None:
        """隔离回调抛异常不传播"""

        def broken_cb(agent_id: str) -> None:
            raise RuntimeError("broken")

        detector = CapabilityDriftDetector(
            hmac_key=HMAC_KEY,
            quarantine_callback=broken_cb,
        )
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        # 不应抛异常
        detector.observe(_esf_event(
            event_type=ESFEventType.SETUID,
            agent_id="a1",
            evidence={"uid": 0},
            seq=1,
        ))


class TestPendingDrifts:
    """pending drifts 查询"""

    def test_get_pending_drifts_empty(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        assert detector.get_pending_drifts("any") == []

    def test_get_pending_drifts_nonempty(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        detector.observe(_esf_event(event_type=ESFEventType.CONNECT, agent_id="a1", seq=1))
        assert len(detector.get_pending_drifts("a1")) == 1


class TestAuditCallback:
    """审计回调测试"""

    def test_audit_callback_on_generate_report(self) -> None:
        """generate_report 触发审计回调"""
        calls: list[CapabilityDriftReport] = []

        def audit_cb(report: CapabilityDriftReport) -> None:
            calls.append(report)

        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY, audit_callback=audit_cb)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        report = detector.generate_report("a1")
        assert len(calls) == 1
        assert calls[0].report_id == report.report_id

    def test_audit_callback_exception_swallowed(self) -> None:
        def broken_cb(report: CapabilityDriftReport) -> None:
            raise RuntimeError("audit broken")

        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY, audit_callback=broken_cb)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        # 不应抛异常
        detector.generate_report("a1")


class TestSnapshot:
    def test_snapshot_empty(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        snap = detector.snapshot()
        assert snap["registered_agents"] == 0
        assert snap["total_pending_drifts"] == 0

    def test_snapshot_with_agents_and_drifts(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=["network_read"])
        detector.register_agent(agent_id="a2", declared_capabilities=["file_read"])
        detector.observe(_esf_event(event_type=ESFEventType.EXEC, agent_id="a1", seq=1))
        snap = detector.snapshot()
        assert snap["registered_agents"] == 2
        assert snap["total_pending_drifts"] == 1
        assert snap["agents"]["a1"]["pending_drifts"] == 1
        assert snap["agents"]["a2"]["pending_drifts"] == 0


class TestHMACSignatures:
    """报告签名完整性测试 (2.2-A3)"""

    def test_report_hmac_auth(self) -> None:
        """报告 HMAC 签名不可伪造"""
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        detector.observe(_esf_event(event_type=ESFEventType.CONNECT, agent_id="a1", seq=1))
        report = detector.generate_report("a1")
        assert report.verify(HMAC_KEY) is True

    def test_report_hmac_different_key_rejected(self) -> None:
        detector = CapabilityDriftDetector(hmac_key=HMAC_KEY)
        detector.register_agent(agent_id="a1", declared_capabilities=[])
        detector.observe(_esf_event(event_type=ESFEventType.CONNECT, agent_id="a1", seq=1))
        report = detector.generate_report("a1")
        assert report.verify(b"wrong-key") is False
