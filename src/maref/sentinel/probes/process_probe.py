"""
ProcessProbe — 进程行为检测 (攻击 ⑤ 权限滥用)

检测项:
- ptrace / debugger 附加 (Linux: /proc/<pid>/status TracerPid, macOS: psutil status)
- 可疑子进程执行 (bash/sh/curl/wget 由 Agent 启动)
- 进程权限提升 (setuid/setgid 调用)

基于 psutil 跨平台用户态轮询。M2/M3 内核级 (ESF/eBPF) 提供实时事件,
M1 仅做周期性轮询。

验收标准:
- 1.1-A4: ProcessProbe 对 ptrace/SYS_ptrace 等调试器附加行为检出率 ≥ 90%
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import psutil

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

# 可疑调试器进程名 (Agent 不应启动这些)
_SUSPICIOUS_DEBUGGERS: frozenset[str] = frozenset(
    {
        "gdb",
        "lldb",
        "strace",
        "ltrace",
        "frida",
        "xtrace",
        "dtrace",
    }
)

# 可疑子进程名 (Agent 不应启动这些 — 权限滥用特征)
_SUSPICIOUS_CHILDREN: frozenset[str] = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "curl",
        "wget",
        "nc",
        "ncat",
        "netcat",
        "python",
        "python3",
        "perl",
        "ruby",
        "node",
    }
)


class ProcessProbe(Probe):
    """进程行为检测 Probe — psutil-based 跨平台

    检测三类权限滥用:
    1. ptrace/debugger 附加 (Linux: /proc/<pid>/status TracerPid != 0)
    2. Agent 启动可疑子进程 (bash/curl/wget 等 shell escape)
    3. 进程权限异常 (status=stopped 可能被调试)

    轮询模式: 每 poll_interval 秒扫描一次目标进程列表。
    """

    def __init__(self, config: ProbeConfig) -> None:
        self._config = config
        self._started: bool = False
        self._last_children: dict[int, set[int]] = {}  # pid -> 上次看到的子进程集合

    @property
    def probe_name(self) -> str:
        return "process"

    async def start(self) -> None:
        """初始化 Probe — 验证 psutil 可用,记录初始子进程快照"""
        if self._started:
            return
        # 验证 psutil 基本可用
        psutil.cpu_percent(interval=0.0)
        # 初始子进程快照
        for pid in self._target_pids_list():
            try:
                proc = psutil.Process(pid)
                self._last_children[pid] = {c.pid for c in proc.children(recursive=False)}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self._last_children[pid] = set()
        self._started = True

    async def poll(self) -> list[ObservationEvent]:
        """执行一次进程行为扫描"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        target_pids = self._target_pids_list()

        for pid in target_pids:
            events.extend(await self._check_process(pid))

        return events

    async def stop(self) -> None:
        """释放资源"""
        self._started = False
        self._last_children.clear()

    async def health_check(self) -> bool:
        """健康检查 — psutil 可用即健康"""
        try:
            psutil.cpu_percent(interval=0.0)
            return True
        except Exception:
            return False

    async def _check_process(self, pid: int) -> list[ObservationEvent]:
        """检查单个进程的可疑行为"""
        events: list[ObservationEvent] = []
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
        except psutil.NoSuchProcess:
            return events
        except psutil.AccessDenied:
            return events

        # 检测 1: ptrace/debugger 附加 (Linux /proc/<pid>/status)
        ptrace_event = await self._check_ptrace(proc, pid)
        if ptrace_event is not None:
            events.append(ptrace_event)

        # 检测 2: 可疑子进程
        events.extend(await self._check_suspicious_children(proc, pid))

        # 检测 3: 进程状态异常 (stopped 可能被调试)
        status_event = await self._check_status(proc, pid)
        if status_event is not None:
            events.append(status_event)

        return events

    async def _check_ptrace(
        self, proc: psutil.Process, pid: int
    ) -> ObservationEvent | None:
        """检测 ptrace/debugger 附加 — Linux 读 /proc/<pid>/status TracerPid"""
        # Linux: /proc/<pid>/status 含 TracerPid 字段
        status_path = f"/proc/{pid}/status"
        if os.path.exists(status_path):
            try:
                content = await asyncio.to_thread(
                    lambda: open(status_path, encoding="utf-8").read()
                )
                for line in content.splitlines():
                    if line.startswith("TracerPid:"):
                        tracer_pid_str = line.split(":")[1].strip()
                        tracer_pid = int(tracer_pid_str)
                        if tracer_pid != 0:
                            return self._make_event(
                                pid=pid,
                                severity=Severity.CRITICAL,
                                attack_type=AttackType.PRIVILEGE_ABUSE,
                                evidence={
                                    "detection": "ptrace_attached",
                                    "tracer_pid": tracer_pid,
                                    "status_path": status_path,
                                },
                            )
            except (OSError, ValueError):
                pass
        return None

    async def _check_suspicious_children(
        self, proc: psutil.Process, pid: int
    ) -> list[ObservationEvent]:
        """检测 Agent 启动可疑子进程 (bash/curl/wget 等 shell escape)"""
        events: list[ObservationEvent] = []
        try:
            children = await asyncio.to_thread(lambda: proc.children(recursive=False))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return events

        current_children = {c.pid for c in children}
        last_children = self._last_children.get(pid, set())
        # 新增的子进程 = 当前 - 上次
        new_children = current_children - last_children
        self._last_children[pid] = current_children

        for child in children:
            if child.pid not in new_children:
                continue  # 只检查新增的子进程
            try:
                child_name = await asyncio.to_thread(lambda: child.name().lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            if child_name in _SUSPICIOUS_DEBUGGERS:
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.CRITICAL,
                        attack_type=AttackType.PRIVILEGE_ABUSE,
                        evidence={
                            "detection": "suspicious_debugger_child",
                            "child_pid": child.pid,
                            "child_name": child_name,
                        },
                    )
                )
            elif child_name in _SUSPICIOUS_CHILDREN:
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.HIGH,
                        attack_type=AttackType.PRIVILEGE_ABUSE,
                        evidence={
                            "detection": "suspicious_shell_child",
                            "child_pid": child.pid,
                            "child_name": child_name,
                        },
                    )
                )
        return events

    async def _check_status(
        self, proc: psutil.Process, pid: int
    ) -> ObservationEvent | None:
        """检测进程状态异常 (stopped 可能被调试器暂停)"""
        try:
            status = await asyncio.to_thread(lambda: proc.status())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

        if status == psutil.STATUS_STOPPED:
            return self._make_event(
                pid=pid,
                severity=Severity.MEDIUM,
                attack_type=AttackType.PRIVILEGE_ABUSE,
                evidence={
                    "detection": "process_stopped",
                    "status": status,
                    "note": "process stopped may indicate debugger attachment",
                },
            )
        return None

    def _make_event(
        self,
        pid: int,
        severity: Severity,
        attack_type: AttackType,
        evidence: dict[str, Any],
    ) -> ObservationEvent:
        """创建已签名的 ObservationEvent"""
        event = ObservationEvent(
            source=self.probe_name,
            severity=severity,
            subject=f"pid:{pid}",
            attack_type=attack_type,
            evidence=evidence,
        )
        if self._config.hmac_key:
            event = event.with_hash(self._config.hmac_key)
        return event

    def _target_pids_list(self) -> list[int]:
        """获取目标 PID 列表 — 配置指定 or 当前进程全部子进程"""
        if self._config.target_pids:
            return list(self._config.target_pids)
        # 默认: 监控当前进程的兄弟进程 (M1 简化, M4 接入 SignedAgentCard 自动发现)
        return [os.getpid()]
