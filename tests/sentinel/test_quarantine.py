"""test_quarantine — QuarantineProtocol 进程隔离协议测试

覆盖验收标准:
- 1.3-A3: QuarantineProtocol.quarantine(pid) 后该进程网络连接数降至 0

使用 NoopStrategy + mock psutil 验证协议逻辑,不动真实进程。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maref.sentinel.quarantine import (
    CgroupFreezerStrategy,
    NoopStrategy,
    QuarantineProtocol,
    QuarantineReason,
    QuarantineRecord,
    QuarantineStatus,
    SandboxExecStrategy,
    SigstopStrategy,
    compute_quarantine_hash,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-quarantine-hmac-key"


def _make_fake_process_with_connections(conn_count: int = 3) -> MagicMock:
    """构造 fake psutil.Process,带指定数量的网络连接"""
    proc = MagicMock()
    conns = []
    for i in range(conn_count):
        c = MagicMock()
        c.family = 2
        c.type = 1
        c.status = "ESTABLISHED"
        c.laddr = MagicMock(ip="127.0.0.1", port=8000 + i)
        c.raddr = MagicMock(ip="10.0.0.1", port=443)
        c.fd = 5 + i
        conns.append(c)
    proc.connections.return_value = conns
    return proc


class TestQuarantineRecord:
    """QuarantineRecord 数据类 + HMAC 测试"""

    def test_default_values(self) -> None:
        record = QuarantineRecord(pid=1234)
        assert record.record_id  # UUID 自动生成
        assert record.pid == 1234
        assert record.status == QuarantineStatus.ACTIVE
        assert record.hmac_signature == ""

    def test_with_hash_returns_new_instance(self) -> None:
        record = QuarantineRecord(pid=1234)
        signed = record.with_hash(HMAC_KEY)
        assert signed is not record
        assert signed.pid == 1234
        assert signed.hmac_signature != ""

    def test_verify_valid_signature(self) -> None:
        record = QuarantineRecord(
            pid=1234, reason=QuarantineReason.CRITICAL_ATTACK
        ).with_hash(HMAC_KEY)
        assert record.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        record = QuarantineRecord(pid=1234)
        assert record.verify(HMAC_KEY) is False

    def test_verify_tampered_returns_false(self) -> None:
        """篡改导致 verify()=False"""
        record = QuarantineRecord(
            pid=1234, reason=QuarantineReason.CRITICAL_ATTACK
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(record, pid=9999)
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_status_returns_false(self) -> None:
        record = QuarantineRecord(
            pid=1234, status=QuarantineStatus.ACTIVE
        ).with_hash(HMAC_KEY)
        from dataclasses import replace

        tampered = replace(record, status=QuarantineStatus.RELEASED)
        assert tampered.verify(HMAC_KEY) is False

    def test_compute_hash_deterministic(self) -> None:
        r1 = QuarantineRecord(
            record_id="r-1", pid=1, reason=QuarantineReason.MANUAL,
            status=QuarantineStatus.ACTIVE, started_at=1000.0, connections_after=0,
        )
        r2 = QuarantineRecord(
            record_id="r-1", pid=1, reason=QuarantineReason.MANUAL,
            status=QuarantineStatus.ACTIVE, started_at=1000.0, connections_after=0,
        )
        assert compute_quarantine_hash(r1, HMAC_KEY) == compute_quarantine_hash(r2, HMAC_KEY)


class TestNoopStrategy:
    """NoopStrategy 测试"""

    async def test_strategy_name(self) -> None:
        assert NoopStrategy().strategy_name == "noop"

    async def test_apply_always_succeeds(self) -> None:
        ok, err = await NoopStrategy().apply(pid=12345)
        assert ok is True
        assert err == ""

    async def test_release_always_succeeds(self) -> None:
        ok, err = await NoopStrategy().release(pid=12345)
        assert ok is True
        assert err == ""


class TestSigstopStrategy:
    """SigstopStrategy 测试"""

    async def test_strategy_name(self) -> None:
        assert SigstopStrategy().strategy_name == "sigstop"

    async def test_apply_success(self) -> None:
        import sys
        if sys.platform == "win32":
            pytest.skip("SIGSTOP not supported on Windows")
        with patch("os.kill") as mock_kill:
            ok, err = await SigstopStrategy().apply(pid=12345)
        assert ok is True
        assert err == ""
        mock_kill.assert_called_once()

    async def test_apply_process_not_found(self) -> None:
        import sys
        if sys.platform == "win32":
            pytest.skip("SIGSTOP not supported on Windows")
        with patch("os.kill", side_effect=ProcessLookupError("no such process")):
            ok, err = await SigstopStrategy().apply(pid=99999)
        assert ok is False
        assert "not found" in err

    async def test_apply_permission_denied(self) -> None:
        import sys
        if sys.platform == "win32":
            pytest.skip("SIGSTOP not supported on Windows")
        with patch("os.kill", side_effect=PermissionError("denied")):
            ok, err = await SigstopStrategy().apply(pid=1)
        assert ok is False
        assert "permission denied" in err.lower()

    async def test_release_success(self) -> None:
        import sys
        if sys.platform == "win32":
            pytest.skip("SIGCONT not supported on Windows")
        with patch("os.kill") as mock_kill:
            ok, err = await SigstopStrategy().release(pid=12345)
        assert ok is True
        assert err == ""


class TestSandboxExecStrategy:
    """SandboxExecStrategy 测试"""

    async def test_strategy_name(self) -> None:
        assert SandboxExecStrategy().strategy_name == "sandbox_exec"

    async def test_apply_non_macos_fails(self) -> None:
        import sys
        if sys.platform == "darwin":
            pytest.skip("Test for non-macOS platforms only")
        ok, err = await SandboxExecStrategy().apply(pid=12345)
        assert ok is False
        assert "macOS" in err


class TestCgroupFreezerStrategy:
    """CgroupFreezerStrategy 测试"""

    async def test_strategy_name(self) -> None:
        assert CgroupFreezerStrategy().strategy_name == "cgroup_freezer"

    async def test_apply_non_linux_fails(self) -> None:
        import sys
        if sys.platform.startswith("linux"):
            pytest.skip("Test for non-Linux platforms only")
        ok, err = await CgroupFreezerStrategy().apply(pid=12345)
        assert ok is False
        assert "Linux" in err


class TestQuarantineProtocol:
    """QuarantineProtocol 核心逻辑测试 — 覆盖 1.3-A3"""

    async def test_quarantine_with_noop_strategy(self) -> None:
        """1.3-A3: quarantine(pid) 后网络连接数降至 0 (mock psutil)"""
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=3)

        # 隔离前: 3 个连接;隔离后: 0 个连接
        call_count = [0]

        def connections_side_effect(kind: str = "inet"):
            call_count[0] += 1
            # 第 1 次调用 (connections_before) 返回 3 条
            # 第 2 次调用 (connections_after) 返回 0 条
            if call_count[0] == 1:
                return fake_proc.connections.return_value
            return []

        fake_proc.connections.side_effect = connections_side_effect

        with patch("psutil.Process", return_value=fake_proc):
            record = await proto.quarantine(
                pid=12345,
                agent_id="agent-evil",
                reason=QuarantineReason.CRITICAL_ATTACK,
            )

        assert record.status == QuarantineStatus.ACTIVE
        assert record.strategy == "noop"
        assert record.connections_before == 3
        assert record.connections_after == 0  # 1.3-A3
        assert record.pid == 12345
        assert record.agent_id == "agent-evil"
        assert record.reason == QuarantineReason.CRITICAL_ATTACK
        assert record.verify(HMAC_KEY) is True

    async def test_is_quarantined_after_quarantine(self) -> None:
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=2)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [], [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            assert proto.is_quarantined(12345) is False
            await proto.quarantine(pid=12345)
            assert proto.is_quarantined(12345) is True

    async def test_quarantine_idempotent(self) -> None:
        """已隔离的 pid 再次调用 quarantine 返回原记录"""
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=1)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            record1 = await proto.quarantine(pid=12345)
            record2 = await proto.quarantine(pid=12345)

        assert record1.record_id == record2.record_id

    async def test_release_removes_from_active(self) -> None:
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=1)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            await proto.quarantine(pid=12345)
            assert proto.is_quarantined(12345) is True
            released = await proto.release(pid=12345)
            assert proto.is_quarantined(12345) is False

        assert released is not None
        assert released.status == QuarantineStatus.RELEASED
        assert released.released_at > 0
        assert released.verify(HMAC_KEY) is True

    async def test_release_unknown_pid_returns_none(self) -> None:
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        result = await proto.release(pid=99999)
        assert result is None

    async def test_quarantine_failed_strategy(self) -> None:
        """策略失败时 status=FAILED"""

        class FailingStrategy(NoopStrategy):
            async def apply(self, pid: int) -> tuple[bool, str]:
                return (False, "synthetic failure")

        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=FailingStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=2)

        with patch("psutil.Process", return_value=fake_proc):
            record = await proto.quarantine(pid=12345)

        assert record.status == QuarantineStatus.FAILED
        assert record.error == "synthetic failure"
        assert proto.is_quarantined(12345) is False  # 失败不进 active
        assert record.verify(HMAC_KEY) is True

    async def test_quarantine_records_audit(self) -> None:
        """audit_callback 被调用"""
        audit_records: list[Any] = []

        def audit_cb(record: Any) -> None:
            audit_records.append(record)

        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy(), audit_callback=audit_cb,
        )
        fake_proc = _make_fake_process_with_connections(conn_count=1)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            await proto.quarantine(pid=12345)

        assert len(audit_records) == 1
        assert audit_records[0].pid == 12345

    async def test_quarantine_async_audit_callback(self) -> None:
        """异步 audit_callback 也支持"""
        audit_records: list[Any] = []

        async def audit_cb(record: Any) -> None:
            audit_records.append(record)

        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy(), audit_callback=audit_cb,
        )
        fake_proc = _make_fake_process_with_connections(conn_count=1)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            await proto.quarantine(pid=12345)

        assert len(audit_records) == 1

    async def test_active_records(self) -> None:
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=1)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value, [],
            fake_proc.connections.return_value, [],
        ]

        with patch("psutil.Process", return_value=fake_proc):
            await proto.quarantine(pid=100)
            await proto.quarantine(pid=200)

        active = proto.active_records()
        assert len(active) == 2
        pids = {r.pid for r in active}
        assert pids == {100, 200}

    async def test_connections_after_nonzero_still_active(self) -> None:
        """策略成功但连接未归零时仍标记 ACTIVE (记录实际连接数)"""
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=3)
        # 隔离前后都是 3 条连接 (NoopStrategy 不真隔离)
        fake_proc.connections.side_effect = [
            fake_proc.connections.return_value,
            fake_proc.connections.return_value,  # 隔离后仍是 3 条
        ]

        with patch("psutil.Process", return_value=fake_proc):
            record = await proto.quarantine(pid=12345)

        assert record.status == QuarantineStatus.ACTIVE
        assert record.connections_before == 3
        assert record.connections_after == 3  # 实际连接数


class TestQuarantineReasonCoverage:
    """覆盖各 QuarantineReason"""

    @pytest.mark.parametrize(
        "reason",
        [
            QuarantineReason.REPUTATION_LOW,
            QuarantineReason.CRITICAL_ATTACK,
            QuarantineReason.CONSENT_DENIED,
            QuarantineReason.MANUAL,
            QuarantineReason.INTEGRITY_VIOLATION,
        ],
    )
    async def test_quarantine_with_each_reason(
        self, reason: QuarantineReason
    ) -> None:
        proto = QuarantineProtocol(
            hmac_key=HMAC_KEY, strategy=NoopStrategy()
        )
        fake_proc = _make_fake_process_with_connections(conn_count=0)

        with patch("psutil.Process", return_value=fake_proc):
            record = await proto.quarantine(pid=12345, reason=reason)

        assert record.reason == reason
        assert record.verify(HMAC_KEY) is True
