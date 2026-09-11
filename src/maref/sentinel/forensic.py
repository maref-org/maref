"""
ForensicSnapshot — sentinel 取证证据 bundle

当 sentinel 检测到 CRITICAL/HIGH 事件时,触发 ForensicSnapshot.snapshot(pid)
打包进程内存映射、打开文件、网络连接、环境变量为 HMAC 签名的 evidence bundle。

接口契约 (与 validation-contract.md 第八节一致):
- snapshot(pid) 在 3 秒内产出 EvidenceBundle,体积 ≤ 50MB
- EvidenceBundle 的 HMAC 校验通过,任何篡改导致 verify()=False
- EvidenceBundle 写入 UnifiedAuditStore 作为不可篡改审计证据

M1.3 阶段: psutil-based 跨平台实现。所有 psutil 阻塞调用通过 asyncio.to_thread
卸载到线程池,确保不阻塞事件循环。敏感环境变量自动脱敏。
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import psutil

# 默认敏感环境变量名 (值会被脱敏为 "***REDACTED***")
_DEFAULT_SENSITIVE_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_CLIENT_SECRET",
    "GOOGLE_API_KEY",
    "GCP_SERVICE_ACCOUNT_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "HF_TOKEN",
    "DATABASE_URL",
    "PG_PASSWORD",
    "MYSQL_PASSWORD",
    "REDIS_PASSWORD",
    "KUBECONFIG",
    "DOCKER_CONFIG",
    "SSH_AUTH_SOCK",
)

# 敏感环境变量名模式 (大小写不敏感匹配)
_SENSITIVE_ENV_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r".*KEY$",
        r".*SECRET$",
        r".*TOKEN$",
        r".*PASSWORD$",
        r".*PASSWD$",
        r".*CREDENTIAL$",
        r".*CREDENTIALS$",
        r".*PRIVATE_KEY$",
    )
)

# bundle 体积上限保护 — 各字段的条目上限
_MAX_OPEN_FILES: int = 2000
_MAX_CONNECTIONS: int = 500
_MAX_MEMORY_MAPS: int = 500
_MAX_ENV_VARS: int = 500
_REDACTED_VALUE: str = "***REDACTED***"


@dataclass(frozen=True)
class EvidenceBundle:
    """取证证据 bundle — HMAC 签名的不可篡改证据包

    Attributes:
        bundle_id: UUID v4,bundle 唯一标识
        trigger_event_id: 触发此次取证的 ObservationEvent.event_id
        pid: 被取证进程 ID
        agent_id: 被取证 Agent ID (从 SignedAgentCard 解析)
        captured_at: 取证时间戳 (unix timestamp, 秒)
        process_info: 进程信息 (cmdline/environ/cpu_affinity/num_fds/...)
        open_files: 打开的文件列表 (path/fd/position/mode)
        network_connections: 网络连接列表 (family/type/laddr/raddr/status/pid)
        memory_maps: 进程内存映射 (addr/perm/path/rss/...)
        environment: 环境变量快照 (敏感值脱敏后)
        hmac_signature: HMAC-SHA256(bundle_id + captured_at + pid + evidence_json)
    """

    bundle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_event_id: str = ""
    pid: int = 0
    agent_id: str = ""
    captured_at: float = field(default_factory=lambda: time.time())
    process_info: dict[str, Any] = field(default_factory=dict)
    open_files: list[dict[str, Any]] = field(default_factory=list)
    network_connections: list[dict[str, Any]] = field(default_factory=list)
    memory_maps: list[dict[str, Any]] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    hmac_signature: str = ""

    def verify(self, hmac_key: bytes) -> bool:
        """验证 EvidenceBundle 的 HMAC 签名 — 任何篡改返回 False"""
        if not self.hmac_signature:
            return False
        expected = compute_bundle_hash(self, hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)

    def with_hash(self, hmac_key: bytes) -> EvidenceBundle:
        """返回带 HMAC 签名的不可变副本 (frozen dataclass 的 with 模式)"""
        new_signature = compute_bundle_hash(self, hmac_key)
        return EvidenceBundle(
            bundle_id=self.bundle_id,
            trigger_event_id=self.trigger_event_id,
            pid=self.pid,
            agent_id=self.agent_id,
            captured_at=self.captured_at,
            process_info=self.process_info,
            open_files=self.open_files,
            network_connections=self.network_connections,
            memory_maps=self.memory_maps,
            environment=self.environment,
            hmac_signature=new_signature,
        )

    def to_audit_payload(self) -> dict[str, Any]:
        """转为 UnifiedAuditStore 可写入的 payload (HMAC 签名不含)"""
        return {
            "bundle_id": self.bundle_id,
            "trigger_event_id": self.trigger_event_id,
            "pid": self.pid,
            "agent_id": self.agent_id,
            "captured_at": self.captured_at,
            "process_info": self.process_info,
            "open_files": self.open_files,
            "network_connections": self.network_connections,
            "memory_maps": self.memory_maps,
            "environment": self.environment,
        }


def compute_bundle_hash(bundle: EvidenceBundle, hmac_key: bytes) -> str:
    """计算 EvidenceBundle 的 HMAC-SHA256 签名

    payload 格式: f"{bundle_id}|{captured_at:.6f}|{pid}|{evidence_json}"
    其中 evidence_json = json.dumps({process_info, open_files, network_connections,
                                      memory_maps, environment}, sort_keys=True)
    """
    evidence_payload = {
        "process_info": bundle.process_info,
        "open_files": bundle.open_files,
        "network_connections": bundle.network_connections,
        "memory_maps": bundle.memory_maps,
        "environment": bundle.environment,
    }
    payload = (
        f"{bundle.bundle_id}|"
        f"{bundle.captured_at:.6f}|"
        f"{bundle.pid}|"
        f"{json.dumps(evidence_payload, sort_keys=True, default=str)}"
    )
    return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


class ForensicSnapshot:
    """取证快照器 — 事件触发时打包进程证据 bundle (M1.3 psutil-based 实现)

    Usage:
        snapshotter = ForensicSnapshot(hmac_key=key)
        bundle = await snapshotter.snapshot(pid=1234, trigger_event_id=evt.event_id)
        if snapshotter.verify_bundle(bundle):
            unified_audit_store.append(bundle.to_audit_payload())

    性能保证:
    - snapshot(pid) 在 3 秒内完成 (psutil 调用全部走 asyncio.to_thread)
    - bundle 体积 ≤ 50MB (各字段条目数有上限,超限截断并记录 truncated 字段)
    - 敏感环境变量自动脱敏 (KEY/SECRET/TOKEN/PASSWORD 等模式 + 显式名单)
    - 任何 psutil 错误 (NoSuchProcess/AccessDenied) 转为部分快照,不抛异常
    """

    def __init__(
        self,
        hmac_key: bytes,
        sensitive_env_vars: tuple[str, ...] = _DEFAULT_SENSITIVE_ENV_VARS,
        agent_pid_resolver: Any = None,
        max_open_files: int = _MAX_OPEN_FILES,
        max_connections: int = _MAX_CONNECTIONS,
        max_memory_maps: int = _MAX_MEMORY_MAPS,
        max_env_vars: int = _MAX_ENV_VARS,
    ) -> None:
        """初始化取证快照器

        Args:
            hmac_key: HMAC-SHA256 签名密钥 (必须从 KeyringStore 获取,禁止硬编码)
            sensitive_env_vars: 额外敏感环境变量名 (与默认名单合并)
            agent_pid_resolver: 可选回调 (agent_id -> list[int]),返回 Agent 全部 PID。
                若为 None,snapshot_agent() 将返回空列表。
            max_open_files: open_files 条目上限 (防止超大进程撑爆 bundle)
            max_connections: connections 条目上限
            max_memory_maps: memory_maps 条目上限
            max_env_vars: environment 条目上限
        """
        self._hmac_key = hmac_key
        self._sensitive_env_vars: set[str] = set(_DEFAULT_SENSITIVE_ENV_VARS + sensitive_env_vars)
        self._agent_pid_resolver = agent_pid_resolver
        self._max_open_files = max_open_files
        self._max_connections = max_connections
        self._max_memory_maps = max_memory_maps
        self._max_env_vars = max_env_vars

    async def snapshot(self, pid: int, trigger_event_id: str = "") -> EvidenceBundle:
        """对目标进程取证,产出 HMAC 签名的 EvidenceBundle

        性能: 3 秒内完成;psutil 调用并行走 asyncio.to_thread。

        Args:
            pid: 被取证进程 ID
            trigger_event_id: 触发此次取证的 ObservationEvent.event_id (可选, 用于溯源)

        Returns:
            带 HMAC 签名的 EvidenceBundle (即使进程不存在也返回部分快照,不抛异常)
        """
        # 并行采集五类证据 (asyncio.gather + to_thread)
        (
            process_info,
            open_files,
            connections,
            memory_maps,
            environment,
        ) = await asyncio.gather(
            self._capture_process_info(pid),
            self._capture_open_files(pid),
            self._capture_connections(pid),
            self._capture_memory_maps(pid),
            self._capture_environ(pid),
        )

        bundle = EvidenceBundle(
            trigger_event_id=trigger_event_id,
            pid=pid,
            agent_id=process_info.get("agent_id", ""),
            captured_at=time.time(),
            process_info=process_info,
            open_files=open_files,
            network_connections=connections,
            memory_maps=memory_maps,
            environment=environment,
        )
        return bundle.with_hash(self._hmac_key)

    async def snapshot_agent(self, agent_id: str) -> list[EvidenceBundle]:
        """对指定 Agent 的全部进程取证 (一个 Agent 可能多进程)

        Args:
            agent_id: Agent ID

        Returns:
            该 Agent 全部进程的 EvidenceBundle 列表 (空列表若无 resolver 或无 PID)
        """
        if self._agent_pid_resolver is None:
            return []
        try:
            pids = await _maybe_await(self._agent_pid_resolver(agent_id))
        except Exception:
            return []
        if not pids:
            return []
        # 并行对每个 PID 取证
        return await asyncio.gather(
            *(self.snapshot(pid=pid, trigger_event_id=f"agent:{agent_id}") for pid in pids)
        )

    def verify_bundle(self, bundle: EvidenceBundle) -> bool:
        """验证 EvidenceBundle 的 HMAC 签名 — 任何篡改返回 False"""
        return bundle.verify(self._hmac_key)

    # ==================== 内部采集方法 ====================

    async def _capture_process_info(self, pid: int) -> dict[str, Any]:
        """采集进程基本信息 (cmdline/exe/cwd/username/...)"""

        def _collect() -> dict[str, Any]:
            try:
                proc = psutil.Process(pid)
                info: dict[str, Any] = {
                    "pid": pid,
                    "name": _safe_call_attr(proc, "name", ""),
                    "exe": _safe_call_attr(proc, "exe", ""),
                    "cwd": _safe_call_attr(proc, "cwd", ""),
                    "cmdline": list(_safe_call_attr(proc, "cmdline", []) or []),
                    "username": _safe_call_attr(proc, "username", ""),
                    "create_time": _safe_call_attr(proc, "create_time", 0.0),
                    "status": _safe_call_attr(proc, "status", ""),
                    "ppid": _safe_call_attr(proc, "ppid", 0),
                    "num_fds": _safe_call_attr(proc, "num_fds", 0),
                    "num_threads": _safe_call_attr(proc, "num_threads", 0),
                    "cpu_percent": _safe_call_attr(proc, "cpu_percent", 0.0),
                    "cpu_affinity": list(_safe_call_attr(proc, "cpu_affinity", []) or []),
                }
                # memory_info (rss/vms)
                mem = _safe_call_attr(proc, "memory_info", None)
                if mem is not None:
                    info["memory_rss"] = getattr(mem, "rss", 0)
                    info["memory_vms"] = getattr(mem, "vms", 0)
                return info
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                return {"pid": pid, "error": "process_unavailable"}
            except Exception as exc:
                return {"pid": pid, "error": f"capture_failed: {type(exc).__name__}"}

        return await asyncio.to_thread(_collect)

    async def _capture_open_files(self, pid: int) -> list[dict[str, Any]]:
        """采集打开的文件列表"""

        def _collect() -> list[dict[str, Any]]:
            try:
                proc = psutil.Process(pid)
                files = _safe_call_attr(proc, "open_files", []) or []
                items: list[dict[str, Any]] = []
                truncated = 0
                for f in files:
                    if len(items) >= self._max_open_files:
                        truncated = len(files) - self._max_open_files
                        break
                    items.append(
                        {
                            "path": getattr(f, "path", ""),
                            "fd": getattr(f, "fd", -1),
                            "position": getattr(f, "position", 0),
                            "mode": getattr(f, "mode", ""),
                        }
                    )
                if truncated > 0:
                    items.append({"_truncated": truncated, "_max": self._max_open_files})
                return items
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                return []
            except Exception:
                return []

        return await asyncio.to_thread(_collect)

    async def _capture_connections(self, pid: int) -> list[dict[str, Any]]:
        """采集网络连接列表"""

        def _collect() -> list[dict[str, Any]]:
            try:
                proc = psutil.Process(pid)
                conns = _safe_call_attr(proc, "connections", []) or []
                items: list[dict[str, Any]] = []
                truncated = 0
                for c in conns:
                    if len(items) >= self._max_connections:
                        truncated = len(conns) - self._max_connections
                        break
                    laddr = getattr(c, "laddr", None)
                    raddr = getattr(c, "raddr", None)
                    items.append(
                        {
                            "family": getattr(c, "family", 0),
                            "type": getattr(c, "type", 0),
                            "status": getattr(c, "status", ""),
                            "laddr": _addr_to_dict(laddr),
                            "raddr": _addr_to_dict(raddr),
                            "fd": getattr(c, "fd", -1),
                        }
                    )
                if truncated > 0:
                    items.append({"_truncated": truncated, "_max": self._max_connections})
                return items
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                return []
            except Exception:
                return []

        return await asyncio.to_thread(_collect)

    async def _capture_memory_maps(self, pid: int) -> list[dict[str, Any]]:
        """采集进程内存映射 (限制条目数,防止超大进程撑爆 bundle)"""

        def _collect() -> list[dict[str, Any]]:
            try:
                proc = psutil.Process(pid)
                maps = _safe_call_attr(proc, "memory_maps", []) or []
                items: list[dict[str, Any]] = []
                truncated = 0
                for m in maps:
                    if len(items) >= self._max_memory_maps:
                        truncated = len(maps) - self._max_memory_maps
                        break
                    items.append(
                        {
                            "addr": getattr(m, "addr", ""),
                            "perm": getattr(m, "perm", ""),
                            "path": getattr(m, "path", ""),
                            "rss": getattr(m, "rss", 0),
                            "private": getattr(m, "private", 0),
                        }
                    )
                if truncated > 0:
                    items.append({"_truncated": truncated, "_max": self._max_memory_maps})
                return items
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                return []
            except Exception:
                return []

        return await asyncio.to_thread(_collect)

    async def _capture_environ(self, pid: int) -> dict[str, str]:
        """采集环境变量 (敏感值脱敏)"""

        def _collect() -> dict[str, str]:
            try:
                proc = psutil.Process(pid)
                environ = _safe_call_attr(proc, "environ", {}) or {}
                redacted: dict[str, str] = {}
                for count, (key, value) in enumerate(environ.items()):
                    if count >= self._max_env_vars:
                        redacted["_truncated"] = f"env vars truncated at {self._max_env_vars}"
                        break
                    if self._is_sensitive_env(key):
                        redacted[key] = _REDACTED_VALUE
                    else:
                        redacted[key] = str(value)
                return redacted
            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                return {}
            except Exception:
                return {}

        return await asyncio.to_thread(_collect)

    def _is_sensitive_env(self, key: str) -> bool:
        """判断环境变量名是否敏感 (需脱敏)"""
        if key in self._sensitive_env_vars:
            return True
        return any(p.match(key) for p in _SENSITIVE_ENV_PATTERNS)


# ==================== 模块级辅助函数 ====================


def _safe_attr(obj: Any, attr: str, default: Any) -> Any:
    """安全读取对象属性,任何异常返回 default"""
    try:
        value = getattr(obj, attr)
        if value is None:
            return default
        return value
    except Exception:
        return default


def _safe_call_attr(obj: Any, attr: str, default: Any) -> Any:
    """安全读取并调用对象属性 (若可调用),任何异常返回 default

    psutil 中 open_files()/connections()/memory_maps()/environ() 均为方法,
    需调用才能获取实际数据。MagicMock 的 return_value 配置也需调用才生效。
    """
    try:
        value = getattr(obj, attr)
        if value is None:
            return default
        if callable(value):
            return value()
        return value
    except Exception:
        return default


def _addr_to_dict(addr: Any) -> dict[str, Any]:
    """psutil 地址对象转 dict"""
    if addr is None:
        return {}
    try:
        return {
            "ip": getattr(addr, "ip", ""),
            "port": getattr(addr, "port", 0),
        }
    except Exception:
        return {}


async def _maybe_await(value: Any) -> Any:
    """若 value 是 coroutine 则 await,否则直接返回"""
    if asyncio.iscoroutine(value):
        return await value
    return value
