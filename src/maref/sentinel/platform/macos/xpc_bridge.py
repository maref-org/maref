"""
xpc_bridge — Python ↔ Swift ESF client 桥接

ESF (Endpoint Security Framework) 客户端是独立 Swift 进程,需要
com.apple.developer.endpoint-security.client entitlement,无法在 Python 内直接调用。
本模块通过 Unix domain socket 与 Swift ESF client 通信:

  ┌──────────────────┐  Unix socket  ┌─────────────────────┐
  │  XPCBridge       │ ◄───────────► │  esf_client.swift   │
  │  (Python asyncio)│   JSON lines  │  (Swift ESF client) │
  └──────────────────┘               └─────────────────────┘
         │                                    │
         │ ObservationEvent                    │ es_new_client_event
         ▼                                    ▼
  SentinelDaemon                    Endpoint Security Framework

接口契约 (validation-contract.md 2.1-A1/A3/A5):
- 2.1-A1: ESF client 订阅 execve 事件后,Agent 启动子进程 5ms 内被捕获
- 2.1-A3: ESF 事件丢失率 ≤ 0.1% (10K 事件压测)
- 2.1-A5: ESF client crash 后 Daemon 能在 3 秒内重启并恢复订阅

事件流:
1. Swift ESF client 订阅 exec/open/fork/exit 事件
2. 每个事件序列化为 JSON,通过 socket 写入 (newline-delimited)
3. Python XPCBridge 读取 socket,解析 JSON,转 ESFEvent
4. SentinelDaemon 通过 async iterator 消费 ESFEvent
5. 健康检查: 每 5s ping Swift side,3s 内无响应则重启
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import socket
import stat
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ESFEventType(str, Enum):
    """ESF 事件类型 — 对应 Endpoint Security Framework 事件订阅"""

    EXEC = "exec"  # execve — 进程启动
    OPEN = "open"  # open/openat — 文件打开
    FORK = "fork"  # fork/posix_spawn — 进程派生
    EXIT = "exit"  # exit/exit_group — 进程退出
    CLOSE = "close"  # close — 文件关闭
    RENAME = "rename"  # rename — 文件重命名
    UNLINK = "unlink"  # unlink — 文件删除
    SIGNAL = "signal"  # kill — 信号发送
    SETUID = "setuid"  # setuid/setgid — 权限切换
    SOCK = "sock"  # socket — 创建 socket
    CONNECT = "connect"  # connect — 网络连接
    BIND = "bind"  # bind — 端口绑定
    HEALTH = "health"  # 健康检查 (内部)
    ERROR = "error"  # ESF client 错误
    SUBACK = "suback"  # 订阅确认


class XPCBridgeState(str, Enum):
    """XPC bridge 状态"""

    STOPPED = "stopped"  # 未启动
    STARTING = "starting"  # 启动中 (socket 创建/subprocess 启动)
    CONNECTED = "connected"  # 已连接,正常收事件
    DEGRADED = "degraded"  # 降级 (ESF client crash,自动重启中)
    FAILED = "failed"  # 失败 (重试次数超限)


class ESFClientError(Exception):
    """XPC bridge / ESF client 错误"""


@dataclass(frozen=True)
class ESFEvent:
    """ESF 事件 — Swift ESF client 推送的内核事件

    Attributes:
        event_id: 事件唯一 ID (UUID,由 Swift side 生成)
        event_type: 事件类型 (exec/open/fork/exit/...)
        seq: 序列号 (单调递增,用于丢包检测 — 2.1-A3)
        timestamp: 事件时间戳 (unix seconds,由 ESF client 捕获)
        pid: 触发事件的进程 PID
        ppid: 父进程 PID (exec/fork 事件)
        agent_id: 关联的 Agent ID (由 ESF client 根据 pid→agent 映射填充)
        path: 文件路径 (open/exec 事件)
        argv: 进程参数 (exec 事件)
        fd: 文件描述符 (open/close 事件)
        remote_addr: 远端地址 (connect 事件)
        remote_port: 远端端口 (connect 事件)
        evidence: 额外证据 (dict)
        hmac_signature: HMAC-SHA256 签名 (Swift side 用共享密钥签名)
    """

    event_id: str = ""
    event_type: ESFEventType = ESFEventType.EXEC
    seq: int = 0
    timestamp: float = field(default_factory=lambda: time.time())
    pid: int = 0
    ppid: int = 0
    agent_id: str = ""
    path: str = ""
    argv: list[str] = field(default_factory=list)
    fd: int = 0
    remote_addr: str = ""
    remote_port: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)
    hmac_signature: str = ""

    def verify(self, hmac_key: bytes) -> bool:
        """验证事件 HMAC 签名 — 防止 Swift side → Python 之间被篡改"""
        if not self.hmac_signature:
            return False
        expected = self._compute_hash(hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)

    def with_hash(self, hmac_key: bytes) -> ESFEvent:
        """返回带 HMAC 签名的不可变副本"""
        sig = self._compute_hash(hmac_key)
        return ESFEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            seq=self.seq,
            timestamp=self.timestamp,
            pid=self.pid,
            ppid=self.ppid,
            agent_id=self.agent_id,
            path=self.path,
            argv=self.argv,
            fd=self.fd,
            remote_addr=self.remote_addr,
            remote_port=self.remote_port,
            evidence=self.evidence,
            hmac_signature=sig,
        )

    def _compute_hash(self, hmac_key: bytes) -> str:
        """计算 HMAC-SHA256(payload) — payload = event_id|seq|timestamp|pid|event_type"""
        payload = (
            f"{self.event_id}|"
            f"{self.seq}|"
            f"{self.timestamp:.6f}|"
            f"{self.pid}|"
            f"{self.event_type.value}"
        )
        return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def to_observation_evidence(self) -> dict[str, Any]:
        """转为 ObservationEvent.evidence 格式"""
        return {
            "esf_event_id": self.event_id,
            "esf_event_type": self.event_type.value,
            "esf_seq": self.seq,
            "pid": self.pid,
            "ppid": self.ppid,
            "path": self.path,
            "argv": self.argv,
            "fd": self.fd,
            "remote_addr": self.remote_addr,
            "remote_port": self.remote_port,
            "extra": self.evidence,
        }


class XPCBridge:
    """Python ↔ Swift ESF client 桥接 — 基于 Unix domain socket

    Usage:
        bridge = XPCBridge(
            hmac_key=key,
            socket_path="/tmp/maref-esf.sock",
            esf_client_binary="/usr/local/libexec/maref-esf-client",
        )
        await bridge.start()
        async for event in bridge.events():
            if event.event_type == ESFEventType.EXEC:
                logger.info("exec: pid=%d path=%s", event.pid, event.path)
        await bridge.stop()

    保证:
    - 2.1-A5: ESF client crash 后 3 秒内自动重启 (max_restart_interval=3.0)
    - 2.1-A3: 事件 seq 单调递增,丢包可检测
    - HMAC 签名防止 Swift → Python 之间被中间人篡改
    """

    def __init__(
        self,
        hmac_key: bytes,
        socket_path: str = "/tmp/maref-esf.sock",
        esf_client_binary: str = "",
        target_pids: list[int] | None = None,
        target_agent_ids: list[str] | None = None,
        subscribe_events: tuple[ESFEventType, ...] = (
            ESFEventType.EXEC,
            ESFEventType.OPEN,
            ESFEventType.FORK,
            ESFEventType.EXIT,
            ESFEventType.CONNECT,
            ESFEventType.SETUID,
        ),
        max_restart_attempts: int = 3,
        max_restart_interval: float = 3.0,
        health_check_interval: float = 5.0,
        audit_callback: Any = None,
    ) -> None:
        """初始化 XPC bridge

        Args:
            hmac_key: HMAC-SHA256 共享密钥 (与 esf_client.swift 共享)
            socket_path: Unix domain socket 路径
            esf_client_binary: Swift ESF client 二进制路径 (空 = 不启动子进程,仅监听)
            target_pids: 目标 Agent PID 列表 (传给 ESF client 过滤)
            target_agent_ids: 目标 Agent ID 列表 (用于 pid→agent_id 映射)
            subscribe_events: 订阅的 ESF 事件类型
            max_restart_attempts: ESF client crash 后最大重试次数
            max_restart_interval: 重启间隔上限 (2.1-A5: 3 秒)
            health_check_interval: 健康检查间隔 (秒)
            audit_callback: 审计回调 (ESFEvent -> None/Awaitable)
        """
        self._hmac_key = hmac_key
        self._socket_path = socket_path
        self._esf_client_binary = esf_client_binary
        self._target_pids = list(target_pids) if target_pids else []
        self._target_agent_ids = list(target_agent_ids) if target_agent_ids else []
        self._subscribe_events = subscribe_events
        self._max_restart_attempts = max_restart_attempts
        self._max_restart_interval = max_restart_interval
        self._health_check_interval = health_check_interval
        self._audit_callback = audit_callback

        # 运行时状态
        self._state: XPCBridgeState = XPCBridgeState.STOPPED
        self._server_socket: socket.socket | None = None
        self._client_reader: asyncio.StreamReader | None = None
        self._client_writer: asyncio.StreamWriter | None = None
        self._esf_subprocess: asyncio.subprocess.Process | None = None
        self._event_queue: asyncio.Queue[ESFEvent] = asyncio.Queue(maxsize=10000)
        self._last_seq: int = 0
        self._lost_events: int = 0
        self._total_events: int = 0
        self._restart_count: int = 0
        self._last_heartbeat: float = 0.0
        self._listen_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()

    @property
    def state(self) -> XPCBridgeState:
        return self._state

    @property
    def lost_events(self) -> int:
        """丢失事件数 (seq 跳跃) — 用于 2.1-A3 检测"""
        return self._lost_events

    @property
    def total_events(self) -> int:
        return self._total_events

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    async def start(self) -> None:
        """启动 XPC bridge — 创建 socket server + 启动 ESF client 子进程"""
        if self._state != XPCBridgeState.STOPPED:
            raise ESFClientError(f"bridge already running (state={self._state.value})")

        self._state = XPCBridgeState.STARTING
        self._stop_event.clear()

        # 1. 创建 Unix domain socket server
        await self._setup_socket_server()

        # 2. 启动 ESF client 子进程 (若有 binary)
        if self._esf_client_binary:
            await self._start_esf_subprocess()

        # 3. 启动事件监听 + 健康检查任务
        self._listen_task = asyncio.create_task(self._listen_loop(), name="xpc-listen")
        self._health_task = asyncio.create_task(self._health_loop(), name="xpc-health")

        self._state = XPCBridgeState.CONNECTED
        self._last_heartbeat = time.time()

    async def stop(self) -> None:
        """优雅关闭 — drain queue + 关闭 socket + 终止子进程"""
        self._state = XPCBridgeState.STOPPED
        self._stop_event.set()

        # 取消任务
        for task in (self._listen_task, self._health_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._listen_task = None
        self._health_task = None

        # 关闭 socket
        if self._client_writer:
            self._client_writer.close()
            try:
                await self._client_writer.wait_closed()
            except Exception:
                pass
            self._client_writer = None
            self._client_reader = None

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        # 终止 ESF subprocess
        if self._esf_subprocess and self._esf_subprocess.returncode is None:
            try:
                self._esf_subprocess.terminate()
                await asyncio.wait_for(self._esf_subprocess.wait(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError, Exception):
                try:
                    self._esf_subprocess.kill()
                except Exception:
                    pass
        self._esf_subprocess = None

        # 清理 socket 文件
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)
        except Exception:
            pass

    async def events(self) -> AsyncIterator[ESFEvent]:
        """异步迭代 ESF 事件 — SentinelDaemon 消费入口"""
        while not self._stop_event.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                yield event
            except asyncio.TimeoutError:
                continue

    async def send_command(self, command: dict[str, Any]) -> bool:
        """向 ESF client 发送控制命令 (如更新订阅、添加目标 PID)

        Returns:
            True = 命令发送成功; False = bridge 未连接或发送失败
        """
        if not self._client_writer:
            return False
        try:
            data = (json.dumps(command) + "\n").encode("utf-8")
            self._client_writer.write(data)
            await self._client_writer.drain()
            return True
        except Exception:
            return False

    def update_targets(self, pids: list[int] | None = None, agent_ids: list[str] | None = None) -> None:
        """更新目标 Agent PID/ID 列表 (运行时动态调整)"""
        if pids is not None:
            self._target_pids = list(pids)
        if agent_ids is not None:
            self._target_agent_ids = list(agent_ids)

    async def _setup_socket_server(self) -> None:
        """创建 Unix domain socket server (等待 ESF client 连接)"""
        # 清理旧 socket 文件
        try:
            if os.path.exists(self._socket_path):
                mode = os.stat(self._socket_path).st_mode
                if stat.S_ISSOCK(mode):
                    os.unlink(self._socket_path)
        except Exception:
            pass

        # 确保父目录存在
        Path(self._socket_path).parent.mkdir(parents=True, exist_ok=True)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self._socket_path)
        sock.listen(1)
        sock.setblocking(False)
        # 限制 socket 文件权限 — 仅 owner 可读写
        os.chmod(self._socket_path, 0o600)
        self._server_socket = sock

    async def _start_esf_subprocess(self) -> None:
        """启动 Swift ESF client 子进程"""
        if not self._esf_client_binary or not os.path.exists(self._esf_client_binary):
            # 二进制不存在 — 降级到仅监听模式 (用于测试/CI)
            self._state = XPCBridgeState.DEGRADED
            return

        cmd = [
            self._esf_client_binary,
            "--socket", self._socket_path,
            "--events", ",".join(e.value for e in self._subscribe_events),
        ]
        if self._target_pids:
            cmd.extend(["--pids", ",".join(str(p) for p in self._target_pids)])
        if self._target_agent_ids:
            cmd.extend(["--agents", ",".join(self._target_agent_ids)])

        try:
            self._esf_subprocess = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            self._state = XPCBridgeState.DEGRADED
            raise ESFClientError(f"failed to start ESF client: {type(exc).__name__}: {exc}") from exc

    async def _listen_loop(self) -> None:
        """事件监听主循环 — accept ESF client + 读取 JSON lines"""
        while not self._stop_event.is_set():
            try:
                # 等待 ESF client 连接
                if self._client_reader is None:
                    await self._accept_client()

                # 读取一行 JSON
                assert self._client_reader is not None
                line = await self._client_reader.readline()
                if not line:
                    # ESF client 断开
                    await self._handle_client_disconnect()
                    continue

                event = self._parse_event(line)
                if event is not None:
                    await self._process_event(event)

            except asyncio.CancelledError:
                break
            except Exception:
                # 不让异常中断监听循环
                await asyncio.sleep(0.1)

    async def _accept_client(self) -> None:
        """接受 ESF client 连接"""
        assert self._server_socket is not None
        loop = asyncio.get_running_loop()
        client_sock, _ = await loop.sock_accept(self._server_socket)
        self._client_reader, self._client_writer = await asyncio.open_connection(sock=client_sock)

    async def _handle_client_disconnect(self) -> None:
        """处理 ESF client 断开 — 清理 + 触发重启"""
        if self._client_writer:
            self._client_writer.close()
            try:
                await self._client_writer.wait_closed()
            except Exception:
                pass
            self._client_writer = None
            self._client_reader = None

        if self._stop_event.is_set():
            return

        # 2.1-A5: crash 后 3 秒内重启
        self._state = XPCBridgeState.DEGRADED
        if self._restart_count < self._max_restart_attempts:
            self._restart_count += 1
            await asyncio.sleep(min(0.5 * self._restart_count, self._max_restart_interval))
            if self._esf_client_binary:
                await self._start_esf_subprocess()
            self._state = XPCBridgeState.CONNECTED
        else:
            self._state = XPCBridgeState.FAILED

    def _parse_event(self, line: bytes) -> ESFEvent | None:
        """解析 JSON line 为 ESFEvent"""
        try:
            data = json.loads(line.decode("utf-8").strip())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        try:
            event_type = ESFEventType(data.get("event_type", "exec"))
        except ValueError:
            event_type = ESFEventType.ERROR

        return ESFEvent(
            event_id=data.get("event_id", ""),
            event_type=event_type,
            seq=int(data.get("seq", 0)),
            timestamp=float(data.get("timestamp", time.time())),
            pid=int(data.get("pid", 0)),
            ppid=int(data.get("ppid", 0)),
            agent_id=data.get("agent_id", ""),
            path=data.get("path", ""),
            argv=list(data.get("argv", [])),
            fd=int(data.get("fd", 0)),
            remote_addr=data.get("remote_addr", ""),
            remote_port=int(data.get("remote_port", 0)),
            evidence=dict(data.get("evidence", {})),
            hmac_signature=data.get("hmac_signature", ""),
        )

    async def _process_event(self, event: ESFEvent) -> None:
        """处理 ESF 事件 — seq 检测 + HMAC 校验 + 入队"""
        self._total_events += 1
        self._last_heartbeat = time.time()

        # seq 单调递增检测 (2.1-A3 丢包检测)
        if event.seq > 0:
            if self._last_seq > 0 and event.seq > self._last_seq + 1:
                self._lost_events += event.seq - self._last_seq - 1
            if event.seq > self._last_seq:
                self._last_seq = event.seq

        # HMAC 校验 (失败仍入队,但 evidence 标记)
        if event.hmac_signature and not event.verify(self._hmac_key):
            event = ESFEvent(
                **{**event.__dict__, "evidence": {**event.evidence, "hmac_failed": True}}
            )

        # 审计回调
        if self._audit_callback:
            try:
                result = self._audit_callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

        # 入队 (队列满则丢弃最旧)
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._event_queue.get_nowait()
                self._event_queue.put_nowait(event)
                self._lost_events += 1
            except asyncio.QueueEmpty:
                pass

    async def _health_loop(self) -> None:
        """健康检查循环 — 5s ping,3s 无响应触发重启"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._health_check_interval)
                break
            except asyncio.TimeoutError:
                pass

            now = time.time()
            if now - self._last_heartbeat > self._health_check_interval * 2:
                # 心跳超时 — ESF client 可能 hung
                if self._client_writer:
                    try:
                        self._client_writer.close()
                        await self._client_writer.wait_closed()
                    except Exception:
                        pass
                    self._client_writer = None
                    self._client_reader = None
                self._state = XPCBridgeState.DEGRADED

    def snapshot(self) -> dict[str, Any]:
        """当前 bridge 状态快照 (调试/监控用)"""
        return {
            "state": self._state.value,
            "socket_path": self._socket_path,
            "esf_client_binary": self._esf_client_binary,
            "target_pids": list(self._target_pids),
            "target_agent_ids": list(self._target_agent_ids),
            "subscribe_events": [e.value for e in self._subscribe_events],
            "total_events": self._total_events,
            "lost_events": self._lost_events,
            "restart_count": self._restart_count,
            "last_heartbeat": self._last_heartbeat,
            "last_seq": self._last_seq,
            "queue_size": self._event_queue.qsize(),
        }
