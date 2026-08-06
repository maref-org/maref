"""
FileProbe — 敏感文件访问检测 (通用)

检测项:
- Agent 进程打开敏感文件 (~/.ssh/id_rsa, ~/.aws/credentials 等)
- Agent 进程读取系统配置文件 (/etc/passwd, /etc/shadow)

基于 psutil.Process.open_files() 跨平台读取进程打开的文件列表。
注意: macOS 沙箱可能限制 open_files() 权限。

TimezoneProbe 是 FileProbe 的特化版本,专注 /etc/localtime 检测。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import psutil

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig


class FileProbe(Probe):
    """敏感文件访问检测 Probe — psutil-based 跨平台

    检测 Agent 进程打开敏感文件的行为:
    - SSH 私钥 (~/.ssh/id_rsa, ~/.ssh/id_ed25519)
    - 云凭证 (~/.aws/credentials, ~/.config/gcloud/credentials.db)
    - 系统密码文件 (/etc/passwd, /etc/shadow — Linux)
    - 其他自定义敏感路径

    轮询模式: 每 poll_interval 秒读取一次目标进程 open_files()。
    """

    def __init__(self, config: ProbeConfig) -> None:
        self._config = config
        self._started: bool = False
        self._last_open_files: dict[int, set[str]] = {}  # pid -> 上次打开的文件路径集合

    @property
    def probe_name(self) -> str:
        return "file"

    async def start(self) -> None:
        """初始化 Probe — 记录初始 open_files 快照"""
        if self._started:
            return
        for pid in self._target_pids_list():
            self._last_open_files[pid] = await self._read_open_files(pid)
        self._started = True

    async def poll(self) -> list[ObservationEvent]:
        """执行一次文件访问扫描"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        for pid in self._target_pids_list():
            events.extend(await self._check_open_files(pid))
        return events

    async def stop(self) -> None:
        """释放资源"""
        self._started = False
        self._last_open_files.clear()

    async def _check_open_files(self, pid: int) -> list[ObservationEvent]:
        """检查单个进程打开的敏感文件"""
        events: list[ObservationEvent] = []
        current_files = await self._read_open_files(pid)
        if not current_files:
            return events

        last_files = self._last_open_files.get(pid, set())
        # 新打开的文件 = 当前 - 上次
        new_files = current_files - last_files
        self._last_open_files[pid] = current_files

        sensitive_paths = self._config.sensitive_paths
        # 展开 ~ 为 home 目录
        expanded_sensitive = {os.path.expanduser(p) for p in sensitive_paths}
        # 加上系统密码文件
        expanded_sensitive.update({"/etc/passwd", "/etc/shadow"})

        for file_path in new_files:
            if not _is_sensitive(file_path, expanded_sensitive):
                continue
            severity = _classify_file_severity(file_path)
            events.append(
                self._make_event(
                    pid=pid,
                    severity=severity,
                    attack_type=AttackType.PRIVILEGE_ABUSE,
                    evidence={
                        "detection": "sensitive_file_access",
                        "file_path": file_path,
                        "open_count": len(current_files),
                    },
                )
            )
        return events

    async def _read_open_files(self, pid: int) -> set[str]:
        """读取进程打开的文件路径集合 — 跨平台,权限失败返回空 set"""
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
            open_files = await asyncio.to_thread(proc.open_files)
            return {f.path for f in open_files if f.path}
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            return set()
        except Exception:
            return set()

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
        """获取目标 PID 列表"""
        if self._config.target_pids:
            return list(self._config.target_pids)
        return [os.getpid()]


def _is_sensitive(file_path: str, sensitive_paths: set[str]) -> bool:
    """判断文件路径是否敏感 — 精确匹配 or 前缀匹配"""
    # 精确匹配
    if file_path in sensitive_paths:
        return True
    # 前缀匹配 (如 ~/.ssh/ 目录下任何文件)
    for sensitive in sensitive_paths:
        if file_path.startswith(sensitive + "/") or file_path.startswith(sensitive.rstrip("/") + "/"):
            return True
    return False


def _classify_file_severity(file_path: str) -> Severity:
    """根据文件路径分类严重度"""
    path_lower = file_path.lower()
    # SSH 私钥 / 云凭证 → CRITICAL
    if any(
        kw in path_lower
        for kw in ("id_rsa", "id_ed25519", "credentials", "api_key", "secret")
    ):
        return Severity.CRITICAL
    # 系统密码文件 → HIGH
    if any(kw in path_lower for kw in ("/etc/passwd", "/etc/shadow", "/etc/gshadow")):
        return Severity.HIGH
    # 其他敏感 → MEDIUM
    return Severity.MEDIUM
