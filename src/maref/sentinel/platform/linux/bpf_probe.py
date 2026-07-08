"""
bpf_probe — Linux eBPF 内核观测探针

通过 bcc (BPF Compiler Collection) Python 绑定编译和挂载 eBPF 程序,
跟踪三类内核事件:

1. connect syscall — 网络连接发起 (network monitoring)
2. openat syscall — 文件打开操作 (file access monitoring)
3. /proc/self/environ 读取 — 环境变量访问监控

当 bcc 不可用时 (未安装或非 Linux 环境),启动时抛出 BPFNotAvailableError,
调用方 (SentinelDaemon) 应优雅降级到 psutil 探针。

与 macOS ESF 类似,每个观测事件带 HMAC-SHA256 签名以保证证据完整性,
并通过 asyncio.Queue 异步传递给 SentinelDaemon。
"""

from __future__ import annotations

import asyncio
import socket
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from maref.sentinel.event import AttackType, ObservationEvent, Severity

# ---------------------------------------------------------------------------
# eBPF C programs (Python multiline strings)
# ---------------------------------------------------------------------------

BPF_CONNECT_PROG: str = """
#include <linux/sched.h>
#include <net/sock.h>
#include <bcc/proto.h>

struct connect_event_t {
    u32 pid;
    u32 uid;
    u32 cpu;
    u64 ts_ns;
    u32 saddr;
    u32 daddr;
    u16 dport;
    u16 sport;
    char task[TASK_COMM_LEN];
};

BPF_PERF_OUTPUT(connect_events);

int trace_connect_enter(struct tracepoint__syscalls__sys_enter_connect *ctx) {
    struct connect_event_t evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.cpu = bpf_get_smp_processor_id();
    evt.ts_ns = bpf_ktime_get_ns();
    bpf_get_current_comm(&evt.task, sizeof(evt.task));

    struct sockaddr __user *us = (struct sockaddr *)ctx->uservaddr;
    // Read sockaddr_in to extract addr and port
    u16 family;
    bpf_probe_read(&family, sizeof(family), &us->sa_family);
    if (family == 2) {  // AF_INET
        struct sockaddr_in *sin = (struct sockaddr_in *)us;
        bpf_probe_read(&evt.daddr, sizeof(evt.daddr), &sin->sin_addr.s_addr);
        bpf_probe_read(&evt.dport, sizeof(evt.dport), &sin->sin_port);
    }
    connect_events.perf_submit(ctx, &evt, sizeof(evt));
    return 0;
}
"""

BPF_OPENAT_PROG: str = """
#include <linux/sched.h>
#include <uapi/linux/limits.h>
#include <bcc/proto.h>

struct openat_event_t {
    u32 pid;
    u32 uid;
    u32 cpu;
    u64 ts_ns;
    int dfd;
    int flags;
    u16 mode;
    char task[TASK_COMM_LEN];
    char filename[PATH_MAX];
};

BPF_PERF_OUTPUT(openat_events);

int trace_openat_enter(struct tracepoint__syscalls__sys_enter_openat *ctx) {
    struct openat_event_t evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.cpu = bpf_get_smp_processor_id();
    evt.ts_ns = bpf_ktime_get_ns();
    evt.dfd = ctx->dfd;
    evt.flags = ctx->flags;
    evt.mode = ctx->mode;
    bpf_get_current_comm(&evt.task, sizeof(evt.task));
    bpf_probe_read_user(&evt.filename, sizeof(evt.filename), (void *)ctx->filename);
    openat_events.perf_submit(ctx, &evt, sizeof(evt));
    return 0;
}
"""

BPF_ENVIRON_PROG: str = """
#include <linux/sched.h>
#include <uapi/linux/limits.h>
#include <bcc/proto.h>

struct environ_event_t {
    u32 pid;
    u32 uid;
    u32 cpu;
    u64 ts_ns;
    char task[TASK_COMM_LEN];
    char filename[PATH_MAX];
};

BPF_PERF_OUTPUT(environ_events);

int trace_openat_environ(struct tracepoint__syscalls__sys_enter_openat *ctx) {
    struct environ_event_t evt = {};
    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.uid = bpf_get_current_uid_gid();
    evt.cpu = bpf_get_smp_processor_id();
    evt.ts_ns = bpf_ktime_get_ns();
    bpf_get_current_comm(&evt.task, sizeof(evt.task));
    bpf_probe_read_user(&evt.filename, sizeof(evt.filename), (void *)ctx->filename);

    // Only capture /proc/*/environ accesses
    int i;
    for (i = 0; i < sizeof(evt.filename) - 8; i++) {
        if (evt.filename[i] == 'e' &&
            evt.filename[i+1] == 'n' &&
            evt.filename[i+2] == 'v' &&
            evt.filename[i+3] == 'i' &&
            evt.filename[i+4] == 'r' &&
            evt.filename[i+5] == 'o' &&
            evt.filename[i+6] == 'n') {
            environ_events.perf_submit(ctx, &evt, sizeof(evt));
            break;
        }
    }
    return 0;
}
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BPFNotAvailableError(RuntimeError):
    """bcc 不可用 — 非 Linux 环境或 bcc 未安装

    SentinelDaemon 捕获此异常后应降级到 psutil 探针。
    """


# ---------------------------------------------------------------------------
# BPFProbe
# ---------------------------------------------------------------------------


def _now_ts() -> float:
    """获取当前 unix timestamp (秒)"""
    return time.time()


class BPFProbe:
    """Linux eBPF 内核观测探针 — 通过 bcc 跟踪 syscall 事件

    Usage:
        probe = BPFProbe(hmac_key=b"...")
        await probe.start()
        async for event in probe.events():
            logger.info("event: source=%s pid=%s", event.source, event.subject)
        await probe.stop()

    当 bcc 不可用时 (非 Linux 环境或未安装),start() 抛出 BPFNotAvailableError。
    行为与 macOS ESF XPCBridge 平行,产出 HMAC 签名的 ObservationEvent。

    Attributes:
        probe_name: 探针名称,固定为 "ebpf"
        hmac_key: HMAC-SHA256 签名密钥
        event_queue: 内部事件缓冲区
    """

    def __init__(
        self,
        hmac_key: bytes,
        event_queue_maxsize: int = 10000,
    ) -> None:
        """初始化 BPFProbe

        Args:
            hmac_key: HMAC-SHA256 签名密钥 (从 KeyringStore 获取)
            event_queue_maxsize: 内部事件队列最大容量
        """
        self._hmac_key = hmac_key
        self._event_queue: asyncio.Queue[ObservationEvent] = asyncio.Queue(maxsize=event_queue_maxsize)
        self._running = False
        self._bpf_modules: list[Any] = []
        self._perf_buffers: list[Any] = []
        self._listen_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._total_events: int = 0
        self._lost_events: int = 0

    @property
    def probe_name(self) -> str:
        """探针名称 — 用于 ObservationEvent.source 字段"""
        return "ebpf"

    @property
    def total_events(self) -> int:
        return self._total_events

    @property
    def lost_events(self) -> int:
        return self._lost_events

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """启动 eBPF 探针 — 加载并挂载 BPF 程序

        Raises:
            BPFNotAvailableError: bcc 不可用时
            RuntimeError: 探针已在运行时
        """
        if self._running:
            raise RuntimeError("BPFProbe already running")

        bcc = self._import_bcc()
        if bcc is None:
            raise BPFNotAvailableError(
                "bcc (BPF Compiler Collection) is not available. "
                "Install with: sudo apt install bpfcc-tools python3-bpfcc "
                "or pip install bcc"
            )

        self._stop_event.clear()
        self._running = True

    async def stop(self) -> None:
        """停止 eBPF 探针 — 卸载 BPF 程序,清理资源"""
        self._running = False
        self._stop_event.set()

        for pb in self._perf_buffers:
            try:
                pb.close()
            except Exception:
                pass
        self._perf_buffers.clear()
        self._bpf_modules.clear()

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listen_task = None

    def observe_syscalls(self, pid: int | None = None) -> None:
        """观察目标进程的 syscall 事件 (openat)

        通过 bcc 编译和挂载 BPF_OPENAT_PROG,过滤指定 PID。
        事件通过 perf buffer 推送到内部队列。

        Args:
            pid: 目标进程 PID (None = 观察全部进程)
        """
        bcc = self._import_bcc()
        if bcc is None:
            raise BPFNotAvailableError("bcc not available")

        module = bcc.BPF(text=BPF_OPENAT_PROG)
        if pid is not None:
            module.attach_tracepoint(
                tp="syscalls:sys_enter_openat",
                fn_name="trace_openat_enter",
                pid=pid,
            )
        else:
            module.attach_tracepoint(
                tp="syscalls:sys_enter_openat",
                fn_name="trace_openat_enter",
            )

        self._bpf_modules.append(module)

        def callback(cpu: Any, data: Any, size: int) -> None:
            event = self._build_observation_from_openat(data)
            if event is not None:
                try:
                    self._event_queue.put_nowait(event)
                    self._total_events += 1
                except asyncio.QueueFull:
                    self._lost_events += 1

        pb = module["openat_events"].open_perf_buffer(callback)
        self._perf_buffers.append(pb)

    def observe_network(self, pid: int | None = None) -> None:
        """观察目标进程的网络连接事件 (connect syscall)

        通过 bcc 编译和挂载 BPF_CONNECT_PROG,过滤指定 PID。

        Args:
            pid: 目标进程 PID (None = 观察全部进程)
        """
        bcc = self._import_bcc()
        if bcc is None:
            raise BPFNotAvailableError("bcc not available")

        module = bcc.BPF(text=BPF_CONNECT_PROG)
        if pid is not None:
            module.attach_tracepoint(
                tp="syscalls:sys_enter_connect",
                fn_name="trace_connect_enter",
                pid=pid,
            )
        else:
            module.attach_tracepoint(
                tp="syscalls:sys_enter_connect",
                fn_name="trace_connect_enter",
            )

        self._bpf_modules.append(module)

        def callback(cpu: Any, data: Any, size: int) -> None:
            event = self._build_observation_from_connect(data)
            if event is not None:
                try:
                    self._event_queue.put_nowait(event)
                    self._total_events += 1
                except asyncio.QueueFull:
                    self._lost_events += 1

        pb = module["connect_events"].open_perf_buffer(callback)
        self._perf_buffers.append(pb)

    async def events(self) -> AsyncIterator[ObservationEvent]:
        """异步迭代观测事件 — SentinelDaemon 消费入口"""
        while not self._stop_event.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                yield event
            except asyncio.TimeoutError:
                continue

    def snapshot(self) -> dict[str, Any]:
        """当前探针状态快照 (调试/监控用)"""
        return {
            "probe_name": self.probe_name,
            "is_running": self._running,
            "total_events": self._total_events,
            "lost_events": self._lost_events,
            "bpf_modules_loaded": len(self._bpf_modules),
            "perf_buffers_active": len(self._perf_buffers),
            "queue_size": self._event_queue.qsize(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _import_bcc(self) -> Any:
        """尝试导入 bcc 模块,失败返回 None"""
        try:
            import bcc  # type: ignore[import-not-found]
            return bcc
        except ImportError:
            return None

    def _build_observation_from_openat(self, data: Any) -> ObservationEvent | None:
        """从 openat eBPF 事件构建 ObservationEvent

        Args:
            data: bcc perf buffer 原始数据 (ctypes struct)

        Returns:
            带 HMAC 签名的 ObservationEvent,或 None (数据无效时)
        """
        try:
            pid = int(getattr(data, "pid", 0))
            filename = getattr(data, "filename", b"")
            if isinstance(filename, bytes):
                filename = filename.rstrip(b"\x00").decode("utf-8", errors="replace")

            evidence: dict[str, Any] = {
                "syscall": "openat",
                "pid": pid,
                "uid": int(getattr(data, "uid", -1)),
                "filename": filename,
                "flags": int(getattr(data, "flags", 0)),
                "task": getattr(data, "task", b"").rstrip(b"\x00").decode("utf-8", errors="replace")
                if isinstance(getattr(data, "task", b""), bytes)
                else str(getattr(data, "task", "")),
            }

            event = ObservationEvent(
                event_id=str(uuid.uuid4()),
                ts=_now_ts(),
                source=self.probe_name,
                severity=Severity.LOW,
                subject=f"pid:{pid}",
                attack_type=AttackType.NONE,
                evidence=evidence,
            )
            return event.with_hash(self._hmac_key)
        except Exception:
            return None

    def _build_observation_from_connect(self, data: Any) -> ObservationEvent | None:
        """从 connect eBPF 事件构建 ObservationEvent

        Args:
            data: bcc perf buffer 原始数据 (ctypes struct)

        Returns:
            带 HMAC 签名的 ObservationEvent,或 None (数据无效时)
        """
        try:
            pid = int(getattr(data, "pid", 0))
            daddr_raw = getattr(data, "daddr", 0)
            dport_raw = getattr(data, "dport", 0)

            remote_addr = self._ip_to_str(int(daddr_raw)) if isinstance(daddr_raw, (int,)) else str(daddr_raw)
            remote_port = socket.htons(int(dport_raw)) if isinstance(dport_raw, (int,)) else int(dport_raw)

            evidence: dict[str, Any] = {
                "syscall": "connect",
                "pid": pid,
                "uid": int(getattr(data, "uid", -1)),
                "remote_addr": remote_addr,
                "remote_port": remote_port,
                "task": getattr(data, "task", b"").rstrip(b"\x00").decode("utf-8", errors="replace")
                if isinstance(getattr(data, "task", b""), bytes)
                else str(getattr(data, "task", "")),
            }

            event = ObservationEvent(
                event_id=str(uuid.uuid4()),
                ts=_now_ts(),
                source=self.probe_name,
                severity=Severity.LOW,
                subject=f"pid:{pid}",
                attack_type=AttackType.NONE,
                evidence=evidence,
            )
            return event.with_hash(self._hmac_key)
        except Exception:
            return None

    @staticmethod
    def _ip_to_str(addr: int) -> str:
        """将 32-bit IPv4 整数转为点分十进制字符串 (网络字节序)"""
        return f"{(addr >> 0) & 0xff}.{(addr >> 8) & 0xff}.{(addr >> 16) & 0xff}.{(addr >> 24) & 0xff}"


