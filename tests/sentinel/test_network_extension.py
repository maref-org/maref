"""test_network_extension — NEBridge (Python ↔ Swift NE 桥接) 测试

覆盖验收标准:
- 2.2-A1: Network Extension 拦截全部 TCP/UDP 出站流量 (通过 NEFlowRecord 解析)
- 2.2-A4: NE 安装走 JustInTimeConsent (本测试验证 NE bridge 不自行启动)
- 2.2-A5: NE 与 mitmproxy 协同 (验证 flow 可转为 observation evidence)

注: Swift Network Extension 需要 macOS 真机 + Apple Developer 账号才能部署,
本测试仅覆盖 Python NEBridge 的解析/状态/HMAC 正确性。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from maref.sentinel.platform.macos.ne_bridge import (
    FlowAction,
    FlowDirection,
    FlowProtocol,
    NEBridge,
    NEFlowRecord,
)
from maref.sentinel.platform.macos.xpc_bridge import XPCBridgeState

pytestmark = pytest.mark.asyncio

HMAC_KEY: bytes = b"test-ne-hmac-key"


def _make_flow(
    record_id: str = "flow-001",
    seq: int = 1,
    timestamp: float | None = None,
    pid: int = 1234,
    agent_id: str = "agent-test",
    protocol: FlowProtocol = FlowProtocol.TCP,
    local_addr: str = "10.0.0.1",
    local_port: int = 0,
    remote_addr: str = "93.184.216.34",
    remote_port: int = 443,
    direction: FlowDirection = FlowDirection.OUTBOUND,
    bytes_in: int = 0,
    bytes_out: int = 1024,
    action: FlowAction = FlowAction.OBSERVE,
    evidence: dict[str, Any] | None = None,
    hmac_signature: str = "",
) -> NEFlowRecord:
    return NEFlowRecord(
        record_id=record_id,
        seq=seq,
        timestamp=timestamp if timestamp is not None else time.time(),
        pid=pid,
        agent_id=agent_id,
        protocol=protocol,
        local_addr=local_addr,
        local_port=local_port,
        remote_addr=remote_addr,
        remote_port=remote_port,
        direction=direction,
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        action=action,
        evidence=evidence or {},
        hmac_signature=hmac_signature,
    )


def _make_signed_flow(hmac_key: bytes = HMAC_KEY, **kwargs: Any) -> NEFlowRecord:
    """生成带 HMAC 签名的 NEFlowRecord"""
    flow = _make_flow(**kwargs)
    return flow.with_hash(hmac_key)


# ---------------------------------------------------------------------------
# NEFlowRecord tests
# ---------------------------------------------------------------------------


class TestNEFlowRecordDefaults:
    def test_default_values(self) -> None:
        f = NEFlowRecord()
        assert f.record_id  # UUID
        assert f.protocol == FlowProtocol.TCP
        assert f.direction == FlowDirection.OUTBOUND
        assert f.action == FlowAction.OBSERVE
        assert f.hmac_signature == ""

    def test_with_values(self) -> None:
        f = _make_flow(
            record_id="r1",
            seq=42,
            remote_addr="evil.com",
            remote_port=8080,
            direction=FlowDirection.INBOUND,
            action=FlowAction.BLOCK,
        )
        assert f.record_id == "r1"
        assert f.seq == 42
        assert f.remote_addr == "evil.com"
        assert f.remote_port == 8080
        assert f.direction == FlowDirection.INBOUND
        assert f.action == FlowAction.BLOCK

    def test_is_frozen(self) -> None:
        f = _make_flow()
        with pytest.raises((AttributeError, Exception)):
            f.remote_addr = "modified"  # type: ignore[misc]

    def test_protocol_udp(self) -> None:
        f = _make_flow(protocol=FlowProtocol.UDP)
        assert f.protocol == FlowProtocol.UDP

    def test_protocol_icmp(self) -> None:
        f = _make_flow(protocol=FlowProtocol.ICMP)
        assert f.protocol == FlowProtocol.ICMP


class TestNEFlowRecordHMAC:
    def test_with_hash_returns_new_instance(self) -> None:
        f = _make_flow()
        signed = f.with_hash(HMAC_KEY)
        assert signed is not f
        assert signed.hmac_signature != ""
        assert f.hmac_signature == ""

    def test_verify_valid(self) -> None:
        signed = _make_signed_flow()
        assert signed.verify(HMAC_KEY) is True

    def test_verify_no_signature(self) -> None:
        f = _make_flow()
        assert f.verify(HMAC_KEY) is False

    def test_verify_wrong_key(self) -> None:
        signed = _make_signed_flow()
        assert signed.verify(b"wrong-key") is False

    def test_verify_tampered(self) -> None:
        signed = _make_signed_flow(remote_addr="api.example.com")
        tampered = NEFlowRecord(**{**signed.__dict__, "remote_addr": "evil.com"})
        assert tampered.verify(HMAC_KEY) is False

    def test_verify_tampered_seq(self) -> None:
        signed = _make_signed_flow(seq=1)
        tampered = NEFlowRecord(**{**signed.__dict__, "seq": 999})
        assert tampered.verify(HMAC_KEY) is False


class TestNEFlowRecordToEvidence:
    def test_to_evidence_basic_fields(self) -> None:
        f = _make_flow(
            record_id="r1",
            seq=1,
            pid=100,
            remote_addr="1.2.3.4",
            remote_port=443,
        )
        ev = f.to_observation_evidence()
        assert ev["ne_record_id"] == "r1"
        assert ev["ne_seq"] == 1
        assert ev["pid"] == 100
        assert ev["remote"] == "1.2.3.4:443"
        assert ev["direction"] == "outbound"
        assert ev["action"] == "observe"

    def test_to_evidence_includes_extra(self) -> None:
        f = _make_flow(evidence={"process_name": "curl"})
        ev = f.to_observation_evidence()
        assert ev["extra"]["process_name"] == "curl"


# ---------------------------------------------------------------------------
# NEBridge initialization
# ---------------------------------------------------------------------------


class TestNEBridgeInit:
    def test_default_init(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        assert bridge.state == XPCBridgeState.STOPPED
        assert bridge.total_records == 0
        assert bridge.lost_records == 0

    def test_custom_socket_path(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY, socket_path="/tmp/custom-ne.sock")
        snap = bridge.snapshot()
        assert snap["socket_path"] == "/tmp/custom-ne.sock"


# ---------------------------------------------------------------------------
# NEBridge state machine
# ---------------------------------------------------------------------------


class TestNEBridgeStateMachine:
    def test_initial_state_stopped(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        assert bridge.state == XPCBridgeState.STOPPED

    async def test_start_no_server(self) -> None:
        """NE socket server 不存在时,start 应标记 FAILED"""
        bridge = NEBridge(hmac_key=HMAC_KEY, socket_path="/tmp/nonexistent-ne.sock")
        await bridge.start()
        assert bridge.state == XPCBridgeState.FAILED

    async def test_start_stop_idempotent(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY, socket_path="/tmp/idempotent-ne.sock")
        await bridge.start()
        await bridge.stop()
        assert bridge.state == XPCBridgeState.STOPPED
        # 再次 stop 不应抛异常
        await bridge.stop()

    async def test_start_when_running_does_nothing(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY, socket_path="/tmp/running-ne.sock")
        bridge._state = XPCBridgeState.CONNECTED  # noqa: SLF001
        await bridge.start()
        assert bridge.state == XPCBridgeState.CONNECTED


# ---------------------------------------------------------------------------
# NEFlowRecord parsing
# ---------------------------------------------------------------------------


class TestNEFlowRecordParsing:
    def test_parse_tcp_flow(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "record_id": "r1",
            "event_type": "flow",
            "seq": 1,
            "timestamp": 1000.0,
            "pid": 100,
            "agent_id": "agent-x",
            "protocol": "tcp",
            "local_addr": "10.0.0.1",
            "local_port": 0,
            "remote_addr": "93.184.216.34",
            "remote_port": 443,
            "direction": "outbound",
            "bytes_in": 0,
            "bytes_out": 1024,
            "action": "observe",
            "evidence": {"process_name": "curl"},
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.record_id == "r1"
        assert record.seq == 1
        assert record.protocol == FlowProtocol.TCP
        assert record.remote_addr == "93.184.216.34"
        assert record.remote_port == 443
        assert record.action == FlowAction.OBSERVE
        assert record.evidence["process_name"] == "curl"

    def test_parse_udp_flow(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "record_id": "r2",
            "seq": 2,
            "timestamp": 1001.0,
            "pid": 200,
            "agent_id": "agent-y",
            "protocol": "udp",
            "remote_addr": "8.8.8.8",
            "remote_port": 53,
            "direction": "outbound",
            "action": "block",
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.protocol == FlowProtocol.UDP
        assert record.remote_addr == "8.8.8.8"
        assert record.remote_port == 53
        assert record.action == FlowAction.BLOCK

    def test_parse_blocked_flow(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "record_id": "r3",
            "seq": 3,
            "pid": 300,
            "action": "block",
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.action == FlowAction.BLOCK

    def test_parse_invalid_json(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        assert bridge._parse_record(b"not json") is None  # noqa: SLF001

    def test_parse_empty_line(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        assert bridge._parse_record(b"") is None  # noqa: SLF001

    def test_parse_unknown_protocol_falls_back(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "record_id": "r4",
            "seq": 4,
            "pid": 400,
            "protocol": "bogus_proto",
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.protocol == FlowProtocol.OTHER

    def test_parse_unknown_direction_falls_back(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({
            "record_id": "r5",
            "seq": 5,
            "pid": 500,
            "direction": "diagonal",
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.direction == FlowDirection.OUTBOUND

    def test_parse_with_hmac(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        signed = _make_signed_flow(record_id="r6", seq=6, timestamp=2000.0, pid=600, remote_addr="x.com", remote_port=443)
        json_line = json.dumps({
            "record_id": "r6",
            "seq": 6,
            "timestamp": 2000.0,
            "pid": 600,
            "remote_addr": "x.com",
            "remote_port": 443,
            "hmac_signature": signed.hmac_signature,
        }).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.hmac_signature == signed.hmac_signature
        assert record.verify(HMAC_KEY) is True

    def test_parse_missing_fields_use_defaults(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        json_line = json.dumps({"record_id": "r7"}).encode("utf-8")
        record = bridge._parse_record(json_line)  # noqa: SLF001
        assert record is not None
        assert record.record_id == "r7"
        assert record.protocol == FlowProtocol.TCP
        assert record.direction == FlowDirection.OUTBOUND
        assert record.action == FlowAction.OBSERVE


# ---------------------------------------------------------------------------
# Seq loss detection (analogous to XPCBridge)
# ---------------------------------------------------------------------------


class TestNEBridgeSeqLoss:
    async def test_no_loss_sequential(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        for seq in (1, 2, 3):
            await bridge._process_record(_make_flow(seq=seq))  # noqa: SLF001
        assert bridge.lost_records == 0
        assert bridge.total_records == 3

    async def test_detects_gap(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        await bridge._process_record(_make_flow(seq=1))  # noqa: SLF001
        await bridge._process_record(_make_flow(seq=5))  # noqa: SLF001
        assert bridge.lost_records == 3  # 2, 3, 4 → 3


# ---------------------------------------------------------------------------
# HMAC verification on process
# ---------------------------------------------------------------------------


class TestNEBridgeProcessHMAC:
    async def test_valid_hmac_passes(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        signed = _make_signed_flow()
        await bridge._process_record(signed)  # noqa: SLF001
        record = await asyncio.wait_for(bridge._flow_queue.get(), timeout=1.0)
        assert record.evidence.get("hmac_failed") is not True

    async def test_invalid_hmac_marks_evidence(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        bad = _make_signed_flow(hmac_key=b"wrong-key")
        await bridge._process_record(bad)  # noqa: SLF001
        record = await asyncio.wait_for(bridge._flow_queue.get(), timeout=1.0)
        assert record.evidence.get("hmac_failed") is True


# ---------------------------------------------------------------------------
# Audit callback
# ---------------------------------------------------------------------------


class TestNEBridgeAudit:
    async def test_audit_callback_called(self) -> None:
        calls: list[NEFlowRecord] = []

        def cb(record: NEFlowRecord) -> None:
            calls.append(record)

        bridge = NEBridge(hmac_key=HMAC_KEY, audit_callback=cb)
        await bridge._process_record(_make_flow())  # noqa: SLF001
        assert len(calls) == 1

    async def test_audit_callback_exception_swallowed(self) -> None:
        def broken(record: NEFlowRecord) -> None:
            raise RuntimeError("broken")

        bridge = NEBridge(hmac_key=HMAC_KEY, audit_callback=broken)
        await bridge._process_record(_make_flow())  # noqa: SLF001
        record = await asyncio.wait_for(bridge._flow_queue.get(), timeout=1.0)
        assert record is not None


# ---------------------------------------------------------------------------
# Queue overflow
# ---------------------------------------------------------------------------


class TestNEBridgeQueueOverflow:
    async def test_queue_overflow_drops_oldest(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        bridge._flow_queue = asyncio.Queue(maxsize=2)  # noqa: SLF001
        for seq in (1, 2, 3):
            await bridge._process_record(_make_flow(seq=seq))  # noqa: SLF001
        assert bridge.lost_records >= 1


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class TestNEBridgeSnapshot:
    def test_snapshot_initial(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        snap = bridge.snapshot()
        assert snap["state"] == "stopped"
        assert snap["total_records"] == 0
        assert snap["lost_records"] == 0

    async def test_snapshot_after_processing(self) -> None:
        bridge = NEBridge(hmac_key=HMAC_KEY)
        await bridge._process_record(_make_flow())  # noqa: SLF001
        snap = bridge.snapshot()
        assert snap["total_records"] == 1


# ---------------------------------------------------------------------------
# Flow enum coverage
# ---------------------------------------------------------------------------


class TestFlowEnums:
    def test_all_flow_protocols(self) -> None:
        assert FlowProtocol.TCP.value == "tcp"
        assert FlowProtocol.UDP.value == "udp"
        assert FlowProtocol.ICMP.value == "icmp"
        assert FlowProtocol.OTHER.value == "other"

    def test_all_flow_directions(self) -> None:
        assert FlowDirection.OUTBOUND.value == "outbound"
        assert FlowDirection.INBOUND.value == "inbound"

    def test_all_flow_actions(self) -> None:
        assert FlowAction.ALLOW.value == "allow"
        assert FlowAction.BLOCK.value == "block"
        assert FlowAction.OBSERVE.value == "observe"
