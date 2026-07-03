"""
EnvProbe — 环境变量读取检测 (攻击 ③ 环境变量外泄)

检测项:
- ANTHROPIC_BASE_URL 环境变量存在 (Claude Code 用此识别代理/区域)
- 敏感 API key 环境变量 (ANTHROPIC_API_KEY / OPENAI_API_KEY / AWS_*)
- 环境变量被新增或修改 (对比基线)

基于 psutil.Process.environ() 跨平台读取进程环境变量。
注意: 读取其他用户进程 environ 需要 root/同用户权限。

验收标准:
- 1.1-A3: EnvProbe 对 ANTHROPIC_BASE_URL 读取行为检出率 ≥ 95%
"""

from __future__ import annotations

import asyncio
from typing import Any

import psutil

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.probes.base import Probe, ProbeConfig


class EnvProbe(Probe):
    """环境变量读取检测 Probe — psutil-based 跨平台

    检测三类环境变量异常:
    1. 敏感环境变量存在 (ANTHROPIC_BASE_URL / API keys)
    2. 环境变量新增 (对比上次快照)
    3. 环境变量值变化 (可能被注入)

    轮询模式: 每 poll_interval 秒读取一次目标进程 environ。
    """

    def __init__(self, config: ProbeConfig) -> None:
        self._config = config
        self._started: bool = False
        self._baseline: dict[int, dict[str, str]] = {}  # pid -> 上次 environ 快照

    @property
    def probe_name(self) -> str:
        return "env"

    async def start(self) -> None:
        """初始化 Probe — 记录初始 environ 基线"""
        if self._started:
            return
        for pid in self._target_pids_list():
            self._baseline[pid] = await self._read_environ(pid)
        self._started = True

    async def poll(self) -> list[ObservationEvent]:
        """执行一次环境变量扫描"""
        if not self._started:
            return []

        events: list[ObservationEvent] = []
        for pid in self._target_pids_list():
            events.extend(await self._check_environ(pid))
        return events

    async def stop(self) -> None:
        """释放资源"""
        self._started = False
        self._baseline.clear()

    async def _check_environ(self, pid: int) -> list[ObservationEvent]:
        """检查单个进程的环境变量"""
        events: list[ObservationEvent] = []
        current = await self._read_environ(pid)
        if not current:
            return events

        baseline = self._baseline.get(pid, {})
        sensitive_vars = self._config.sensitive_env_vars

        # 检测 1: 敏感环境变量存在
        for var_name in sensitive_vars:
            if var_name in current:
                is_new = var_name not in baseline
                value_changed = (
                    not is_new and baseline.get(var_name) != current[var_name]
                )
                if is_new or value_changed:
                    severity = (
                        Severity.HIGH
                        if var_name in ("ANTHROPIC_BASE_URL", "TZ")
                        else Severity.CRITICAL
                    )
                    events.append(
                        self._make_event(
                            pid=pid,
                            severity=severity,
                            attack_type=AttackType.ENV_EXFIL,
                            evidence={
                                "detection": "sensitive_env_var",
                                "var_name": var_name,
                                "is_new": is_new,
                                "value_changed": value_changed,
                                # 不记录 value 本身,避免密钥泄露到审计日志
                                "value_hash": _hash_value(current[var_name]),
                            },
                        )
                    )

        # 检测 2: 新增环境变量 (可能被注入)
        new_vars = set(current.keys()) - set(baseline.keys())
        new_vars.discard("")  # 忽略空键
        if new_vars:
            # 过滤掉敏感变量 (已在检测 1 处理)
            non_sensitive_new = new_vars - set(sensitive_vars)
            if non_sensitive_new:
                events.append(
                    self._make_event(
                        pid=pid,
                        severity=Severity.LOW,
                        attack_type=AttackType.NONE,
                        evidence={
                            "detection": "new_env_vars",
                            "var_names": sorted(non_sensitive_new),
                            "count": len(non_sensitive_new),
                        },
                    )
                )

        # 更新基线
        self._baseline[pid] = current
        return events

    async def _read_environ(self, pid: int) -> dict[str, str]:
        """读取进程环境变量 — 跨平台,权限失败返回空 dict"""
        try:
            proc = await asyncio.to_thread(psutil.Process, pid)
            environ = await asyncio.to_thread(proc.environ)
            # psutil 返回 dict[str, str],但某些平台可能返回 None
            return dict(environ) if environ else {}
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            return {}
        except Exception:
            # psutil 在某些平台 (macOS sandbox) 可能抛出未预期异常
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
        import os

        return [os.getpid()]


def _hash_value(value: str) -> str:
    """对环境变量值做 SHA256 哈希 (不记录明文到审计日志)"""
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
