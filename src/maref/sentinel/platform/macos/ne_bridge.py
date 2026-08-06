"""
ne_bridge — Python ↔ Swift Network Extension 桥接

Network Extension (Packet Tunnel Provider) 以系统扩展形式运行,拦截所有
TCP/UDP 出站流量。本模块通过 Unix domain socket 接收 NE 推送的 flow records:

  ┌──────────────────┐  Unix socket  ┌─────────────────────┐
  │  NEBridge        │ ◄───────────► │  network_extension  │
  │  (Python asyncio)│   JSON lines  │  .swift (NE)        │
  └──────────────────┘               └─────────────────────┘
         │                                    │
         │ NEFlowRecord                       │ packet flow
         ▼                                    ▼
  SentinelDaemon                    Network Extension (内核)

接口契约 (validation-contract.md 2.2-A1/A5):
- 2.2-A1: Network Extension 拦截全部 TCP/UDP 出站流量,无遗漏
- 2.2-A5: NE 与 mitmproxy 协同:NE 拦截 → mitmproxy 解密 → 双重判定

注: NE 安装走 JustInTimeConsent (2.2-A4),用户拒绝则不启动 NEBridge。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.sentinel.platform.macos.xpc_bridge import XPCBridgeState


class FlowProtocol(str, Enum):
    """网络协议"""

    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    OTHER = "other"


class FlowDirection(str, Enum):
    """流量方向"""

    OUTBOUND = "outbound"
    INBOUND = "inbound"


class FlowAction(str, Enum):
    """NE 对流量的处理动作"""

    ALLOW = "allow"  # 放行
    BLOCK = "block"  # 阻断 (block mode)
    OBSERVE = "observe"  # 仅观测 (observe mode)


@dataclass(frozen=True)
class NEFlowRecord:
    """网络流量记录 — NE 推送的单个 flow

    Attributes:
        record_id: UUID v4
        seq: 序列号 (单调递增,丢包检测)
        timestamp: 时间戳 (unix seconds)
        pid: 触发流量的进程 PID
        agent_id: 关联 Agent ID
        protocol: 协议 (tcp/udp)
        local_addr: 本地地址
        local_port: 本地端口
        remote_addr: 远端地址
        remote_port: 远端端口
        direction: 方向 (outbound/inbound)
        bytes_in: 接收字节数
        bytes_out: 发送字节数
        action: NE 动作 (allow/block/observe)
        evidence: 额外证据 (process_name 等)
        hmac_signature: HMAC-SHA256 签名
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    seq: int = 0
    timestamp: float = field(default_factory=lambda: time.time())
    pid: int = 0
    agent_id: str = ""
    protocol: FlowProtocol = FlowProtocol.TCP
    local_addr: str = ""
    local_port: int = 0
    remote_addr: str = ""
    remote_port: int = 0
    direction: FlowDirection = FlowDirection.OUTBOUND
    bytes_in: int = 0
    bytes_out: int = 0
    action: FlowAction = FlowAction.OBSERVE
    evidence: dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""

    def verify(self, hmac_key: bytes) -> bool:
        """验证 HMAC 签名"""
        if not self.hmac_signature:
            return False
        expected = self._compute_hash(hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)

    def with_hash(self, hmac_key: bytes) -> NEFlowRecord:
        """返回带 HMAC 签名的不可变副本"""
        sig = self._compute_hash(hmac_key)
        return NEFlowRecord(
            record_id=self.record_id,
            seq=self.seq,
            timestamp=self.timestamp,
            pid=self.pid,
            agent_id=self.agent_id,
            protocol=self.protocol,
            local_addr=self.local_addr,
            local_port=self.local_port,
            remote_addr=self.remote_addr,
            remote_port=self.remote_port,
            direction=self.direction,
            bytes_in=self.bytes_in,
            bytes_out=self.bytes_out,
            action=self.action,
            evidence=self.evidence,
            hmac_signature=sig,
        )

    def _compute_hash(self, hmac_key: bytes) -> str:
        payload = (
            f"{self.record_id}|"
            f"{self.seq}|"
            f"{self.timestamp:.6f}|"
            f"{self.pid}|"
            f"{self.remote_addr}:{self.remote_port}"
        )
        return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def to_observation_evidence(self) -> dict[str, Any]:
        """转为 ObservationEvent.evidence 格式"""
        return {
            "ne_record_id": self.record_id,
            "ne_seq": self.seq,
            "protocol": self.protocol.value,
            "pid": self.pid,
            "local": f"{self.local_addr}:{self.local_port}",
            "remote": f"{self.remote_addr}:{self.remote_port}",
            "direction": self.direction.value,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "action": self.action.value,
            "extra": self.evidence,
        }


class NEBridge:
    """Python ↔ Swift Network Extension 桥接 — 基于 Unix domain socket

    与 XPCBridge 类似,但接收 NEFlowRecord 而非 ESFEvent。
    NE 作为系统扩展运行,不需要 NEBridge 启动子进程 — NEBridge 仅作为
    socket client 连接 NE 推送的 socket server。

    Usage:
        bridge = NEBridge(hmac_key=key, socket_path="/tmp/maref-ne.sock")
        await bridge.start()
        async for flow in bridge.flows():
            if flow.action == FlowAction.BLOCK:
                logger.warning("blocked flow to %s:%d", flow.remote_addr, flow.remote_port)
        await bridge.stop()
    """

    def __init__(
        self,
        hmac_key: bytes,
        socket_path: str = "/tmp/maref-ne.sock",
        audit_callback: Any = None,
        max_queue_size: int = 10000,
    ) -> None:
        self._hmac_key = hmac_key
        self._socket_path = socket_path
        self._audit_callback = audit_callback
        self._state: XPCBridgeState = XPCBridgeState.STOPPED
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._flow_queue: asyncio.Queue[NEFlowRecord] = asyncio.Queue(maxsize=max_queue_size)
        self._listen_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._last_seq: int = 0
        self._lost_records: int = 0
        self._total_records: int = 0

    @property
    def state(self) -> XPCBridgeState:
        return self._state

    @property
    def total_records(self) -> int:
        return self._total_records

    @property
    def lost_records(self) -> int:
        return self._lost_records

    async def start(self) -> None:
        """启动 NE bridge — 连接 NE socket server"""
        if self._state != XPCBridgeState.STOPPED:
            return
        self._state = XPCBridgeState.STARTING
        self._stop_event.clear()

        try:
            await self._connect()
            self._state = XPCBridgeState.CONNECTED
        except Exception:
            self._state = XPCBridgeState.FAILED
            return

        self._listen_task = asyncio.create_task(self._listen_loop(), name="ne-listen")

    async def stop(self) -> None:
        """优雅关闭"""
        self._state = XPCBridgeState.STOPPED
        self._stop_event.set()

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
        self._listen_task = None

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def _connect(self) -> None:
        """连接 NE socket server"""
        self._reader, self._writer = await asyncio.open_unix_connection(self._socket_path)

    async def _listen_loop(self) -> None:
        """监听主循环 — 读取 JSON lines"""
        while not self._stop_event.is_set():
            try:
                assert self._reader is not None
                line = await self._reader.readline()
                if not line:
                    # NE 断开
                    self._state = XPCBridgeState.DEGRADED
                    break
                record = self._parse_record(line)
                if record is not None:
                    await self._process_record(record)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    def _parse_record(self, line: bytes) -> NEFlowRecord | None:
        """解析 JSON line 为 NEFlowRecord"""
        import json

        try:
            data = json.loads(line.decode("utf-8").strip())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        try:
            protocol = FlowProtocol(data.get("protocol", "tcp"))
        except ValueError:
            protocol = FlowProtocol.OTHER
        try:
            direction = FlowDirection(data.get("direction", "outbound"))
        except ValueError:
            direction = FlowDirection.OUTBOUND
        try:
            action = FlowAction(data.get("action", "observe"))
        except ValueError:
            action = FlowAction.OBSERVE

        return NEFlowRecord(
            record_id=data.get("record_id", ""),
            seq=int(data.get("seq", 0)),
            timestamp=float(data.get("timestamp", time.time())),
            pid=int(data.get("pid", 0)),
            agent_id=data.get("agent_id", ""),
            protocol=protocol,
            local_addr=data.get("local_addr", ""),
            local_port=int(data.get("local_port", 0)),
            remote_addr=data.get("remote_addr", ""),
            remote_port=int(data.get("remote_port", 0)),
            direction=direction,
            bytes_in=int(data.get("bytes_in", 0)),
            bytes_out=int(data.get("bytes_out", 0)),
            action=action,
            evidence=dict(data.get("evidence", {})),
            hmac_signature=data.get("hmac_signature", ""),
        )

    async def _process_record(self, record: NEFlowRecord) -> None:
        """处理 flow record — seq 检测 + HMAC 校验 + 入队"""
        self._total_records += 1

        # seq 丢包检测
        if record.seq > 0:
            if self._last_seq > 0 and record.seq > self._last_seq + 1:
                self._lost_records += record.seq - self._last_seq - 1
            if record.seq > self._last_seq:
                self._last_seq = record.seq

        # HMAC 校验
        if record.hmac_signature and not record.verify(self._hmac_key):
            record = NEFlowRecord(
                **{**record.__dict__, "evidence": {**record.evidence, "hmac_failed": True}}
            )

        # 审计回调
        if self._audit_callback:
            try:
                result = self._audit_callback(record)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

        # 入队
        try:
            self._flow_queue.put_nowait(record)
        except asyncio.QueueFull:
            try:
                self._flow_queue.get_nowait()
                self._flow_queue.put_nowait(record)
                self._lost_records += 1
            except asyncio.QueueEmpty:
                pass

    async def flows(self) -> AsyncIterator[NEFlowRecord]:
        """异步迭代 flow records — SentinelDaemon 消费入口"""
        while not self._stop_event.is_set():
            try:
                record = await asyncio.wait_for(self._flow_queue.get(), timeout=1.0)
                yield record
            except asyncio.TimeoutError:
                continue

    def snapshot(self) -> dict[str, Any]:
        """状态快照"""
        return {
            "state": self._state.value,
            "socket_path": self._socket_path,
            "total_records": self._total_records,
            "lost_records": self._lost_records,
            "last_seq": self._last_seq,
            "queue_size": self._flow_queue.qsize(),
        }
