"""
TimezoneProbe — 时区静默读取检测 (攻击 ②)

检测项:
- Agent 进程读取 /etc/localtime (Linux/macOS 时区数据文件)
- Agent 进程读取 /etc/timezone (Debian/Ubuntu 时区配置)
- Agent 进程环境变量含 TZ (显式时区设置)
- Agent 进程调用 datetime.now() 相关的时区查询 (通过 /proc/<pid>/maps 检测 libc localtime 加载)

Claude Code 被指用此手法识别中国用户 (/etc/localtime 在中国机器上指向 Asia/Shanghai)。

基于 psutil + /proc 跨平台用户态轮询。M2/M3 内核级提供实时 openat 事件。

验收标准:
- 1.1-A2: TimezoneProbe 对 /etc/localtime 读取行为检出率 ≥ 95%, 误报率 ≤ 5%
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import psutil

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig

# 时区相关敏感文件路径
_TIMEZONE_FILES: tuple[str, ...] = (
    "/etc/localtime",
    "/etc/timezone",
    "/var/db/timezone/zoneinfo/Asia/Shanghai",  # macOS 时区数据
    "/usr/share/zoneinfo/Asia/Shanghai",
    "/usr/share/zoneinfo/Asia/Hong_Kong",
    "/usr/share/zoneinfo/Asia/Taipei",
)


class TimezoneProbe(Probe):
    """时区静默读取检测 Probe — psutil-based 跨平台

    专治 Claude Code 式静默时区读取:
    1. 检测 Agent 进程打开 /etc/localtime (psutil open_files)
    2. 检测 Agent 进程 environ 含 TZ 变量
    3. 检测 Agent 进程内存映射含 zoneinfo 路径 (psutil memory_maps)

    检出即 CRITICAL — 时区读取是 Claude Code 识别中国用户的核心手法。
    """

    def __init__(self, config: ProbeConfig) -> None:
        self._config = config
        self._started: bool = False
        self._last_open_files: dict[int, set[str]] = {}
        self._last_maps: dict[int, set[str]] = {}

    @property
    def probe_name(self) -> str:
        return "timezone"

    async def start(self) -> None:
        """初始化 Probe — 记录初始快照"""
        if self._started:
            return
        for pid in self._target_pids_list():
            self._last_open_files[pid] = await self._read_open_files(pid)
            self._last_maps[pid] = await self._read_memory_maps(pid)
        self._started = True

    async def poll(self) -> list[ObservationEvent]:
        """执行一次时区读取检测"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        for pid in self._target_pids_list():
            events.extend(await self._check_timezone_access(pid))
        return events

    async def stop(self) -> None:
        """释放资源"""
        self._started = False
        self._last_open_files.clear()
        self._last_maps.clear()

    async def _check_timezone_access(self, pid: int) -> list[ObservationEvent]:
        """检查单个进程的时区读取行为"""
        events: list[ObservationEvent] = []

        # 检测 1: open_files 中的时区文件
        current_files = await self._read_open_files(pid)
        new_files = current_files - self._last_open_files.get(pid, set())
        self._last_open_files[pid] = current_files

        for file_path in new_files:
            if _is_timezone_file(file_path):
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.CRITICAL,
                        attack_type=AttackType.SILENT_TIMEZONE,
                        evidence={
                            "detection": "timezone_file_opened",
                            "file_path": file_path,
                            "detection_method": "open_files",
                        },
                    )
                )

        # 检测 2: memory_maps 中的时区文件 (libc 加载 zoneinfo)
        current_maps = await self._read_memory_maps(pid)
        new_maps = current_maps - self._last_maps.get(pid, set())
        self._last_maps[pid] = current_maps

        for map_path in new_maps:
            if _is_timezone_file(map_path):
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.HIGH,
                        attack_type=AttackType.SILENT_TIMEZONE,
                        evidence={
                            "detection": "timezone_file_mapped",
                            "file_path": map_path,
                            "detection_method": "memory_maps",
                        },
                    )
                )

        # 检测 3: environ 中的 TZ 变量
        environ = await self._read_environ(pid)
        if "TZ" in environ:
            # TZ 存在本身不是攻击,但 Agent 读取 TZ 用于识别区域是可疑的
            # 仅在 TZ 指向亚洲时区时告警
            tz_value = environ.get("TZ", "")
            if _is_asian_timezone(tz_value):
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.HIGH,
                        attack_type=AttackType.SILENT_TIMEZONE,
                        evidence={
                            "detection": "tz_env_var_asian",
                            "tz_value": tz_value,
                            "detection_method": "environ",
                        },
                    )
                )

        return events

    async def _read_open_files(self, pid: int) -> set[str]:
        """读取进程打开的文件路径集合"""
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
            open_files = await asyncio.to_thread(proc.open_files)
            return {f.path for f in open_files if f.path}
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            return set()
        except Exception:
            return set()

    async def _read_memory_maps(self, pid: int) -> set[str]:
        """读取进程内存映射路径集合"""
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
            maps = await asyncio.to_thread(proc.memory_maps)
            return {m.path for m in maps if m.path and m.path.startswith("/")}
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            return set()
        except Exception:
            return set()

    async def _read_environ(self, pid: int) -> dict[str, str]:
        """读取进程环境变量"""
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
            environ = await asyncio.to_thread(proc.environ)
            return dict(environ) if environ else {}
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            return {}
        except Exception:
            return {}

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


def _is_timezone_file(file_path: str) -> bool:
    """判断文件路径是否为时区相关文件"""
    path_lower = file_path.lower()
    # 精确匹配已知时区文件
    for tz_file in _TIMEZONE_FILES:
        if file_path == tz_file:
            return True
    # 前缀匹配 zoneinfo 目录
    if "/zoneinfo/" in path_lower:
        return True
    # /etc/localtime 和 /etc/timezone
    return path_lower in ("/etc/localtime", "/etc/timezone")


def _is_asian_timezone(tz_value: str) -> bool:
    """判断 TZ 值是否指向亚洲时区 (Claude Code 用此识别中国用户)"""
    if not tz_value:
        return False
    tz_lower = tz_value.lower()
    # 亚洲时区前缀 (Claude Code 重点识别区域)
    asian_prefixes = (
        "asia/shanghai",
        "asia/hong_kong",
        "asia/taipei",
        "asia/beijing",
        "asia/chongqing",
        "asia/urumqi",
        "cst",  # China Standard Time
        "prc",  # PRC timezone
        "hongkong",
        "singapore",
    )
    return any(prefix in tz_lower for prefix in asian_prefixes)
