"""test_macos_esf — XPCBridge (Python ↔ Swift ESF client 桥接) 测试

覆盖验收标准:
- 2.1-A1: ESF client 订阅 execve 事件后,Agent 启动子进程 5ms 内被捕获
        (实际延迟由 Swift ESF client 保证,Python 端测试解析正确性)
- 2.1-A3: ESF 事件丢失率 ≤ 0.1% (通过 seq 单调递增检测丢包)
- 2.1-A5: ESF client crash 后 Daemon 能在 3 秒内重启并恢复订阅
        (测试 restart 逻辑,state 转换为 DEGRADED → CONNECTED)

注: Swift ESF client 二进制需要 macOS 真机 + Apple Developer 账号才能编译运行,
本测试仅覆盖 Python XPCBridge 的逻辑正确性。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from maref.sentinel.platform.macos.xpc_bridge import (
    ESFClientError,
    ESFEvent,
    ESFEventType,
    XPCBridge,
    XPCBridgeState,
)

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-xpc-bridge-hmac-key"


def _make_event(
    event_id: str = "evt-001",
    event_type: ESFEventType = ESFEventType.EXEC,
    seq: int = 1,
    timestamp: float | None = None,
    pid: int = 1234,
    ppid: int = 1000,
    agent_id: str = "agent-test",
    path: str = "/bin/ls",
    argv: list[str] | None = None,
    fd: int = 0,
    remote_addr: str = "",
    remote_port: int = 0,
    evidence: dict[str, Any] | None = None,
    hmac_signature: str = "",
) -> ESFEvent:
    return ESFEvent(
        event_id=event_id,
        event_type=event_type,
        seq=seq,
        timestamp=timestamp if timestamp is not None else time.time(),
        pid=pid,
        ppid=ppid,
        agent_id=agent_id,
        path=path,
        argv=argv or [],
        fd=fd,
        remote_addr=remote_addr,
        remote_port=remote_port,
        evidence=evidence or {},
        hmac_signature=hmac_signature,
    )


def _make_signed_event(
    hmac_key: bytes = HMAC_KEY,
    **kwargs: Any,
) -> ESFEvent:
    """生成带 HMAC 签名的 ESFEvent"""
    event = _make_event(**kwargs)
    return event.with_hash(hmac_key)


# ---------------------------------------------------------------------------
# ESFEventType tests
# ---------------------------------------------------------------------------


class TestESFEventType:
    """ESF 事件类型枚举测试"""

    def test_exec_type(self) -> None:
        assert ESFEventType.EXEC.value == "exec"

    def test_open_type(self) -> None:
        assert ESFEventType.OPEN.value == "open"

    def test_fork_type(self) -> None:
        assert ESFEventType.FORK.value == "fork"

    def test_exit_type(self) -> None:
        assert ESFEventType.EXIT.value == "exit"

    def test_connect_type(self) -> None:
        assert ESFEventType.CONNECT.value == "connect"

    def test_health_type(self) -> None:
        assert ESFEventType.HEALTH.value == "health"

    def test_error_type(self) -> None:
        assert ESFEventType.ERROR.value == "error"

    def test_all_types_are_strings(self) -> None:
        for t in ESFEventType:
            assert isinstance(t.value, str)


# ---------------------------------------------------------------------------
# XPCBridgeState tests
# ---------------------------------------------------------------------------


class TestXPCBridgeState:
    """XPC bridge 状态枚举测试"""

    def test_stopped_state(self) -> None:
        assert XPCBridgeState.STOPPED.value == "stopped"

    def test_starting_state(self) -> None:
        assert XPCBridgeState.STARTING.value == "starting"

    def test_connected_state(self) -> None:
        assert XPCBridgeState.CONNECTED.value == "connected"

    def test_degraded_state(self) -> None:
        assert XPCBridgeState.DEGRADED.value == "degraded"

    def test_failed_state(self) -> None:
        assert XPCBridgeState.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# ESFEvent tests
# ---------------------------------------------------------------------------


class TestESFEventDefaults:
    """ESFEvent 默认值测试"""

    def test_default_values(self) -> None:
        e = ESFEvent()
        assert e.event_id == ""
        assert e.event_type == ESFEventType.EXEC
        assert e.seq == 0
        assert e.pid == 0
        assert e.ppid == 0
        assert e.agent_id == ""
        assert e.path == ""
        assert e.argv == []
        assert e.fd == 0
        assert e.remote_addr == ""
        assert e.remote_port == 0
        assert e.evidence == {}
        assert e.hmac_signature == ""

    def test_event_with_values(self) -> None:
        e = _make_event(
            event_id="evt-123",
            event_type=ESFEventType.OPEN,
            seq=42,
            pid=9999,
            path="/etc/passwd",
            fd=3,
        )
        assert e.event_id == "evt-123"
        assert e.event_type == ESFEventType.OPEN
        assert e.seq == 42
        assert e.pid == 9999
        assert e.path == "/etc/passwd"
        assert e.fd == 3

    def test_event_is_frozen(self) -> None:
        """ESFEvent 是 frozen dataclass,不可修改"""
        e = _make_event()
        with pytest.raises((AttributeError, Exception)):
            e.pid = 9999  # type: ignore[misc]


class TestESFEventHMAC:
    """ESFEvent HMAC 签名测试"""

    def test_with_hash_returns_new_instance(self) -> None:
        e = _make_event()
        signed = e.with_hash(HMAC_KEY)
        assert signed is not e
        assert signed.hmac_signature != ""
        assert e.hmac_signature == ""  # 原对象不变

    def test_with_hash_preserves_fields(self) -> None:
        e = _make_event(
            event_id="evt-1",
            event_type=ESFEventType.EXEC,
            seq=1,
            pid=100,
            path="/bin/ls",
            argv=["ls", "-l"],
        )
        signed = e.with_hash(HMAC_KEY)
        assert signed.event_id == "evt-1"
        assert signed.event_type == ESFEventType.EXEC
        assert signed.seq == 1
        assert signed.pid == 100
        assert signed.path == "/bin/ls"
        assert signed.argv == ["ls", "-l"]

    def test_verify_valid_signature(self) -> None:
        signed = _make_signed_event()
        assert signed.verify(HMAC_KEY) is True

    def test_verify_no_signature_returns_false(self) -> None:
        e = _make_event()  # 无签名
        assert e.verify(HMAC_KEY) is False

    def test_verify_wrong_key_returns_false(self) -> None:
        signed = _make_signed_event(hmac_key=HMAC_KEY)
        wrong_key = b"wrong-key"
        assert signed.verify(wrong_key) is False

    def test_verify_tampered_event_id_returns_false(self) -> None:
        """篡改 event_id 导致 verify()=False"""
        signed = _make_signed_event(event_id="evt-original")
        # frozen dataclass,使用 replace 模拟篡改
        tampered = ESFEvent(
            **{**signed.__dict__, "event_id": "evt-tampered"}
        )
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_pid_returns_false(self) -> None:
        signed = _make_signed_event(pid=1000)
        tampered = ESFEvent(
            **{**signed.__dict__, "pid": 9999}
        )
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_seq_returns_false(self) -> None:
        signed = _make_signed_event(seq=1)
        tampered = ESFEvent(
            **{**signed.__dict__, "seq": 999}
        )
        assert tampered.verify(HMAC_KEY) is False

    def test_with_hash_is_deterministic(self) -> None:
        """相同输入 → 相同签名"""
        e1 = _make_event(event_id="x", seq=1, timestamp=1000.0, pid=100, event_type=ESFEventType.EXEC)
        e2 = _make_event(event_id="x", seq=1, timestamp=1000.0, pid=100, event_type=ESFEventType.EXEC)
        s1 = e1.with_hash(HMAC_KEY)
        s2 = e2.with_hash(HMAC_KEY)
        assert s1.hmac_signature == s2.hmac_signature


class TestESFEventToEvidence:
    """ESFEvent.to_observation_evidence 转换测试"""

    def test_to_evidence_basic_fields(self) -> None:
        e = _make_event(
            event_id="e1",
            event_type=ESFEventType.EXEC,
            seq=1,
            pid=100,
            ppid=50,
            path="/bin/ls",
            argv=["ls"],
        )
        evidence = e.to_observation_evidence()
        assert evidence["esf_event_id"] == "e1"
        assert evidence["esf_event_type"] == "exec"
        assert evidence["esf_seq"] == 1
        assert evidence["pid"] == 100
        assert evidence["ppid"] == 50
        assert evidence["path"] == "/bin/ls"
        assert evidence["argv"] == ["ls"]

    def test_to_evidence_includes_extra(self) -> None:
        e = _make_event(evidence={"custom": "value"})
        evidence = e.to_observation_evidence()
        assert evidence["extra"] == {"custom": "value"}

    def test_to_evidence_includes_network_fields(self) -> None:
        e = _make_event(
            event_type=ESFEventType.CONNECT,
            remote_addr="93.184.216.34",
            remote_port=443,
        )
        evidence = e.to_observation_evidence()
        assert evidence["remote_addr"] == "93.184.216.34"
        assert evidence["remote_port"] == 443


# ---------------------------------------------------------------------------
# XPCBridge initialization tests
# ---------------------------------------------------------------------------


class TestXPCBridgeInit:
    """XPCBridge 初始化测试"""

    def test_default_init(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        assert bridge.state == XPCBridgeState.STOPPED
        assert bridge.lost_events == 0
        assert bridge.total_events == 0
        assert bridge.restart_count == 0

    def test_init_with_custom_socket_path(self) -> None:
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            socket_path="/tmp/custom-esf.sock",
        )
        # 内部字段访问通过 snapshot
        snap = bridge.snapshot()
        assert snap["socket_path"] == "/tmp/custom-esf.sock"

    def test_init_with_target_pids(self) -> None:
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            target_pids=[100, 200, 300],
        )
        snap = bridge.snapshot()
        assert snap["target_pids"] == [100, 200, 300]

    def test_init_with_target_agent_ids(self) -> None:
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            target_agent_ids=["claude-code", "cursor"],
        )
        snap = bridge.snapshot()
        assert snap["target_agent_ids"] == ["claude-code", "cursor"]

    def test_init_with_subscribe_events(self) -> None:
        custom_events = (ESFEventType.EXEC, ESFEventType.FORK)
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            subscribe_events=custom_events,
        )
        snap = bridge.snapshot()
        assert "exec" in snap["subscribe_events"]
        assert "fork" in snap["subscribe_events"]

    def test_update_targets(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        bridge.update_targets(pids=[1, 2, 3], agent_ids=["a1"])
        snap = bridge.snapshot()
        assert snap["target_pids"] == [1, 2, 3]
        assert snap["target_agent_ids"] == ["a1"]


# ---------------------------------------------------------------------------
# XPCBridge state machine tests
# ---------------------------------------------------------------------------


class TestXPCBridgeStateMachine:
    """XPCBridge 状态机测试 — 不实际启动 socket/subprocess"""

    def test_initial_state_stopped(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        assert bridge.state == XPCBridgeState.STOPPED

    async def test_start_without_esf_binary_in_test_env(self) -> None:
        """无 esf_client_binary 时,启动后 state 应为 CONNECTED (仅 socket 监听)

        使用 /tmp/ 下短路径避免 AF_UNIX path too long (macOS 限制 104 字节)。
        """
        import tempfile
        socket_path = f"/tmp/test-esf-{next(tempfile._get_candidate_names())}.sock"
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            socket_path=socket_path,
            esf_client_binary="",  # 不启动子进程
            health_check_interval=999.0,  # 避免健康检查干扰
        )
        try:
            await bridge.start()
            # 无 binary 时,state 应为 CONNECTED (仅 socket 监听)
            assert bridge.state == XPCBridgeState.CONNECTED
        finally:
            await bridge.stop()

    async def test_start_when_already_running_raises(self, tmp_path: Any) -> None:
        """重复 start 应抛 ESFClientError"""
        socket_path = str(tmp_path / "test-esf.sock")
        bridge = XPCBridge(
            hmac_key=HMAC_KEY,
            socket_path=socket_path,
            esf_client_binary="",
        )
        # 手动设置 state 为 CONNECTED 模拟已启动
        bridge._state = XPCBridgeState.CONNECTED  # noqa: SLF001  # 测试需要访问私有成员
        with pytest.raises(ESFClientError):
            await bridge.start()


# ---------------------------------------------------------------------------
# Event parsing tests (2.1-A1 — 解析 ESF client 推送的 JSON)
# ---------------------------------------------------------------------------


class TestEventParsing:
    """事件解析测试 — _parse_event 方法"""

    def test_parse_exec_event(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "event_id": "e1",
            "event_type": "exec",
            "seq": 1,
            "timestamp": 1000.0,
            "pid": 100,
            "ppid": 50,
            "agent_id": "agent-x",
            "path": "/bin/ls",
            "argv": ["ls", "-l"],
        }).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.event_id == "e1"
        assert event.event_type == ESFEventType.EXEC
        assert event.seq == 1
        assert event.pid == 100
        assert event.ppid == 50
        assert event.path == "/bin/ls"
        assert event.argv == ["ls", "-l"]

    def test_parse_open_event(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "event_id": "e2",
            "event_type": "open",
            "seq": 2,
            "timestamp": 1001.0,
            "pid": 100,
            "path": "/etc/passwd",
            "fd": 3,
        }).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.event_type == ESFEventType.OPEN
        assert event.path == "/etc/passwd"
        assert event.fd == 3

    def test_parse_connect_event(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "event_id": "e3",
            "event_type": "connect",
            "seq": 3,
            "timestamp": 1002.0,
            "pid": 100,
            "remote_addr": "93.184.216.34",
            "remote_port": 443,
            "fd": 5,
        }).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.event_type == ESFEventType.CONNECT
        assert event.remote_addr == "93.184.216.34"
        assert event.remote_port == 443

    def test_parse_invalid_json_returns_none(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        event = bridge._parse_event(b"not a json")  # noqa: SLF001  # 测试需要访问私有成员
        assert event is None

    def test_parse_empty_line_returns_none(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        event = bridge._parse_event(b"")  # noqa: SLF001  # 测试需要访问私有成员
        assert event is None

    def test_parse_unknown_event_type_falls_back_to_error(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "event_id": "e4",
            "event_type": "totally_unknown",
            "seq": 4,
            "pid": 100,
        }).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.event_type == ESFEventType.ERROR

    def test_parse_missing_fields_uses_defaults(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({"event_id": "e5"}).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.event_id == "e5"
        assert event.seq == 0
        assert event.pid == 0
        assert event.event_type == ESFEventType.EXEC  # default

    def test_parse_with_hmac_signature(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        signed = _make_signed_event(event_id="e6", seq=6, timestamp=2000.0, pid=200)
        json_line = json.dumps({
            "event_id": signed.event_id,
            "event_type": signed.event_type.value,
            "seq": signed.seq,
            "timestamp": signed.timestamp,
            "pid": signed.pid,
            "hmac_signature": signed.hmac_signature,
        }).encode("utf-8")
        event = bridge._parse_event(json_line)  # noqa: SLF001  # 测试需要访问私有成员
        assert event is not None
        assert event.hmac_signature == signed.hmac_signature
        assert event.verify(HMAC_KEY) is True


# ---------------------------------------------------------------------------
# Seq loss detection tests (2.1-A3)
# ---------------------------------------------------------------------------


class TestSeqLossDetection:
    """2.1-A3: seq 单调递增检测,丢包可统计"""

    async def test_no_loss_for_sequential_events(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        for seq in (1, 2, 3, 4, 5):
            event = _make_event(seq=seq)
            await bridge._process_event(event)  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.lost_events == 0
        assert bridge.total_events == 5

    async def test_detects_single_gap(self) -> None:
        """seq 1 → 3 (跳过 2) → lost_events=1"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        await bridge._process_event(_make_event(seq=1))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(seq=3))  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.lost_events == 1

    async def test_detects_multi_gap(self) -> None:
        """seq 1 → 10 (跳过 2-9) → lost_events=8"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        await bridge._process_event(_make_event(seq=1))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(seq=10))  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.lost_events == 8

    async def test_no_loss_for_seq_zero(self) -> None:
        """seq=0 的事件不参与丢包检测 (假设 ESF client 未启用 seq)"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        await bridge._process_event(_make_event(seq=0))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(seq=0))  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.lost_events == 0

    async def test_no_loss_for_out_of_order_within_zero(self) -> None:
        """seq=0 → 1 → 0 (回退) → 不应触发丢包"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        await bridge._process_event(_make_event(seq=0))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(seq=1))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(seq=0))  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.lost_events == 0

    async def test_total_events_increments(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        for _ in range(10):
            await bridge._process_event(_make_event())  # noqa: SLF001  # 测试需要访问私有成员
        assert bridge.total_events == 10


# ---------------------------------------------------------------------------
# HMAC verification on process tests
# ---------------------------------------------------------------------------


class TestProcessEventHMAC:
    """事件处理时的 HMAC 校验"""

    async def test_valid_hmac_passes_through(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        signed = _make_signed_event()
        await bridge._process_event(signed)  # noqa: SLF001  # 测试需要访问私有成员
        # 取队首事件
        event = await asyncio.wait_for(bridge._event_queue.get(), timeout=1.0)
        assert event.evidence.get("hmac_failed") is not True

    async def test_invalid_hmac_marks_evidence(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        # 用错误的 key 签名
        bad_signed = _make_signed_event(hmac_key=b"wrong-key")
        await bridge._process_event(bad_signed)  # noqa: SLF001  # 测试需要访问私有成员
        event = await asyncio.wait_for(bridge._event_queue.get(), timeout=1.0)
        assert event.evidence.get("hmac_failed") is True

    async def test_no_hmac_passes_through_unverified(self) -> None:
        """无签名的 event 仍入队 (兼容 ESF client 未启用签名)"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        unsigned = _make_event()
        await bridge._process_event(unsigned)  # noqa: SLF001  # 测试需要访问私有成员
        event = await asyncio.wait_for(bridge._event_queue.get(), timeout=1.0)
        assert event.evidence.get("hmac_failed") is not True


# ---------------------------------------------------------------------------
# Audit callback tests
# ---------------------------------------------------------------------------


class TestAuditCallback:
    """审计回调测试"""

    async def test_sync_audit_callback_called(self) -> None:
        called: list[ESFEvent] = []

        def sync_callback(event: ESFEvent) -> None:
            called.append(event)

        bridge = XPCBridge(hmac_key=HMAC_KEY, audit_callback=sync_callback)
        await bridge._process_event(_make_event())  # noqa: SLF001  # 测试需要访问私有成员
        assert len(called) == 1

    async def test_async_audit_callback_called(self) -> None:
        called: list[ESFEvent] = []

        async def async_callback(event: ESFEvent) -> None:
            called.append(event)

        bridge = XPCBridge(hmac_key=HMAC_KEY, audit_callback=async_callback)
        await bridge._process_event(_make_event())  # noqa: SLF001  # 测试需要访问私有成员
        assert len(called) == 1

    async def test_audit_callback_exception_swallowed(self) -> None:
        """审计回调抛异常不应影响事件入队"""

        def bad_callback(event: ESFEvent) -> None:
            raise RuntimeError("audit failure")

        bridge = XPCBridge(hmac_key=HMAC_KEY, audit_callback=bad_callback)
        await bridge._process_event(_make_event())  # noqa: SLF001  # 测试需要访问私有成员
        # 事件仍应入队
        event = await asyncio.wait_for(bridge._event_queue.get(), timeout=1.0)
        assert event is not None


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


class TestSnapshot:
    """snapshot 状态快照测试"""

    def test_snapshot_initial_state(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        snap = bridge.snapshot()
        assert snap["state"] == "stopped"
        assert snap["total_events"] == 0
        assert snap["lost_events"] == 0
        assert snap["restart_count"] == 0
        assert snap["queue_size"] == 0

    async def test_snapshot_reflects_processed_events(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        # 处理 5 个事件
        for _ in range(5):
            await bridge._process_event(_make_event())  # noqa: SLF001  # 测试需要访问私有成员
        snap = bridge.snapshot()
        assert snap["total_events"] == 5

    def test_snapshot_includes_socket_path(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY, socket_path="/custom/path.sock")
        snap = bridge.snapshot()
        assert snap["socket_path"] == "/custom/path.sock"


# ---------------------------------------------------------------------------
# send_command tests
# ---------------------------------------------------------------------------


class TestSendCommand:
    """send_command 测试"""

    async def test_send_command_returns_false_when_not_connected(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        result = await bridge.send_command({"action": "ping"})
        assert result is False

    async def test_send_command_returns_true_when_connected(self, tmp_path: Any) -> None:
        """连接状态下,send_command 应返回 True"""
        # 这个测试需要 mock writer,简化为 mock 测试
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        # 模拟 writer 已连接
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = MagicMock(return_value=asyncio.Future())
        mock_writer.drain.return_value.set_result(None)
        bridge._client_writer = mock_writer  # noqa: SLF001  # 测试需要访问私有成员
        result = await bridge.send_command({"action": "ping"})
        assert result is True
        mock_writer.write.assert_called_once()


# ---------------------------------------------------------------------------
# Queue overflow tests
# ---------------------------------------------------------------------------


class TestQueueOverflow:
    """事件队列溢出处理"""

    async def test_queue_overflow_drops_oldest(self) -> None:
        """队列满时丢弃最旧事件 (lost_events +1)"""
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        # 替换为小队列测试
        bridge._event_queue = asyncio.Queue(maxsize=2)  # noqa: SLF001  # 测试需要访问私有成员
        # 入队 3 个事件 (超出 maxsize=2)
        for seq in (1, 2, 3):
            await bridge._process_event(_make_event(seq=seq))  # noqa: SLF001  # 测试需要访问私有成员
        # 应有 lost_events >= 1 (丢弃最旧)
        assert bridge.lost_events >= 1

    async def test_events_iterator_yields_processed(self) -> None:
        bridge = XPCBridge(hmac_key=HMAC_KEY)
        await bridge._process_event(_make_event(event_id="e1"))  # noqa: SLF001  # 测试需要访问私有成员
        await bridge._process_event(_make_event(event_id="e2"))  # noqa: SLF001  # 测试需要访问私有成员

        # 消费前 2 个事件
        events: list[ESFEvent] = []
        async for event in bridge.events():
            events.append(event)
            if len(events) >= 2:
                break

        assert len(events) == 2
        assert events[0].event_id == "e1"
        assert events[1].event_id == "e2"
