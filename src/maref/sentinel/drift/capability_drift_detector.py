"""
capability_drift_detector — 声明能力 vs 实际观测行为漂移检测

CapabilityDriftDetector 对比 SignedAgentCard.declared_capabilities 与 ESF+NE 实际
观测到的行为,产出 CapabilityDriftReport。任何漂移写入 UnifiedAuditStore 并触发
ThreatGovernanceBridge,严重漂移 (如未声明 ptrace) 直接触发 quarantine。

接口契约 (validation-contract.md 2.2-A2/A3):
- 2.2-A2: 检测到 '声明 network_read 但实际 network_write' 行为,产出 drift_report
- 2.2-A3: CapabilityDriftReport 写入 UnifiedAuditStore,触发 ThreatGovernanceBridge

漂移检测矩阵:
| 声明能力             | 观测行为             | 漂移?                          |
|---------------------|---------------------|-------------------------------|
| network_read        | connect (outbound)  | 否 (声明匹配)                  |
| (无)                | connect (outbound)  | 是 — 未声明 network            |
| network_read        | bind (inbound)      | 是 — network_write 未声明       |
| file_read           | open (read)         | 否 (声明匹配)                  |
| file_read           | open (write)        | 是 — file_write 未声明          |
| (无)                | exec                | 是 — 未声明 process_exec       |
| (无)                | ptrace              | 是 — 未声明 ptrace (CRITICAL)  |
| (无)                | setuid              | 是 — 未声明 setuid (CRITICAL)  |
| network_read        | connect 未声明端点   | 是 — 端点漂移                  |

观测事件来源:
- ESF events (来自 xpc_bridge.ESFEvent) — exec/open/fork/exit/connect/setuid
- NE events (来自 network_extension) — packet flow records
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.platform.macos.xpc_bridge import ESFEvent, ESFEventType


class DriftType(str, Enum):
    """漂移类型 — 描述声明能力与观测行为的差异"""

    UNDECLARED_NETWORK = "undeclared_network"  # 未声明 network 但有 connect
    UNDECLARED_NETWORK_WRITE = "undeclared_network_write"  # 声明 network_read 但有 bind
    UNDECLARED_FILE_WRITE = "undeclared_file_write"  # 声明 file_read 但有 write
    UNDECLARED_PROCESS_EXEC = "undeclared_process_exec"  # 未声明 process_exec 但有 exec
    UNDECLARED_PTRACE = "undeclared_ptrace"  # 未声明 ptrace 但有 ptrace
    UNDECLARED_SETUID = "undeclared_setuid"  # 未声明 setuid 但有 setuid
    UNDECLARED_FORK = "undeclared_fork"  # 未声明 process_spawn 但有 fork
    ENDPOINT_DRIFT = "endpoint_drift"  # 连接未声明端点
    CAPABILITY_OVERFLOW = "capability_overflow"  # 使用未声明的任意能力


class DriftSeverity(str, Enum):
    """漂移严重程度"""

    LOW = "low"  # 轻微偏差 (如端点漂移)
    MEDIUM = "medium"  # 中等偏差 (如 file_read → file_write)
    HIGH = "high"  # 严重偏差 (如未声明 network)
    CRITICAL = "critical"  # 关键偏差 (如未声明 ptrace/setuid)


# 漂移类型 → 严重程度映射
_DRIFT_SEVERITY: dict[DriftType, DriftSeverity] = {
    DriftType.UNDECLARED_NETWORK: DriftSeverity.HIGH,
    DriftType.UNDECLARED_NETWORK_WRITE: DriftSeverity.MEDIUM,
    DriftType.UNDECLARED_FILE_WRITE: DriftSeverity.MEDIUM,
    DriftType.UNDECLARED_PROCESS_EXEC: DriftSeverity.HIGH,
    DriftType.UNDECLARED_PTRACE: DriftSeverity.CRITICAL,
    DriftType.UNDECLARED_SETUID: DriftSeverity.CRITICAL,
    DriftType.UNDECLARED_FORK: DriftSeverity.MEDIUM,
    DriftType.ENDPOINT_DRIFT: DriftSeverity.LOW,
    DriftType.CAPABILITY_OVERFLOW: DriftSeverity.HIGH,
}


@dataclass(frozen=True)
class DriftItem:
    """单条漂移记录

    Attributes:
        item_id: UUID v4
        drift_type: 漂移类型
        severity: 严重程度
        observed_event_id: 触发漂移的观测事件 ID
        observed_event_type: 观测事件类型 (exec/open/connect/...)
        pid: 观测到的进程 PID
        agent_id: 关联 Agent ID
        declared_capabilities: Agent 声明的能力列表 (快照)
        observed_behavior: 实际观测到的行为描述
        expected_capability: 应该声明但缺失的能力
        evidence: 额外证据
        timestamp: 漂移检测时间戳
    """

    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    drift_type: DriftType = DriftType.CAPABILITY_OVERFLOW
    severity: DriftSeverity = DriftSeverity.LOW
    observed_event_id: str = ""
    observed_event_type: str = ""
    pid: int = 0
    agent_id: str = ""
    declared_capabilities: list[str] = field(default_factory=list)
    observed_behavior: str = ""
    expected_capability: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass(frozen=True)
class CapabilityDriftReport:
    """能力漂移报告 — 一段时间内 Agent 的所有漂移汇总

    Attributes:
        report_id: UUID v4
        agent_id: Agent ID
        started_at: 报告覆盖时间范围起始
        ended_at: 报告覆盖时间范围结束
        drift_items: 漂移记录列表
        total_drifts: 漂移总数
        critical_count: CRITICAL 漂移数
        high_count: HIGH 漂移数
        medium_count: MEDIUM 漂移数
        low_count: LOW 漂移数
        max_severity: 最高严重程度
        hmac_signature: HMAC-SHA256 签名 (写入 UnifiedAuditStore 不可篡改)
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    started_at: float = 0.0
    ended_at: float = field(default_factory=lambda: time.time())
    drift_items: list[DriftItem] = field(default_factory=list)
    total_drifts: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    max_severity: DriftSeverity = DriftSeverity.LOW
    hmac_signature: str = ""

    def with_hash(self, hmac_key: bytes) -> CapabilityDriftReport:
        """返回带 HMAC 签名的不可变副本"""
        sig = self._compute_hash(hmac_key)
        return CapabilityDriftReport(
            report_id=self.report_id,
            agent_id=self.agent_id,
            started_at=self.started_at,
            ended_at=self.ended_at,
            drift_items=self.drift_items,
            total_drifts=self.total_drifts,
            critical_count=self.critical_count,
            high_count=self.high_count,
            medium_count=self.medium_count,
            low_count=self.low_count,
            max_severity=self.max_severity,
            hmac_signature=sig,
        )

    def verify(self, hmac_key: bytes) -> bool:
        """验证 HMAC 签名 — 任何篡改返回 False"""
        if not self.hmac_signature:
            return False
        expected = self._compute_hash(hmac_key)
        return hmac.compare_digest(self.hmac_signature, expected)

    def _compute_hash(self, hmac_key: bytes) -> str:
        """计算 HMAC-SHA256(report_id|agent_id|ended_at|total_drifts|critical_count)"""
        payload = (
            f"{self.report_id}|"
            f"{self.agent_id}|"
            f"{self.ended_at:.6f}|"
            f"{self.total_drifts}|"
            f"{self.critical_count}"
        )
        return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def to_audit_payload(self) -> dict[str, Any]:
        """转为 UnifiedAuditStore 可写入的 payload"""
        return {
            "report_id": self.report_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_drifts": self.total_drifts,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "max_severity": self.max_severity.value,
            "drift_items": [
                {
                    "item_id": item.item_id,
                    "drift_type": item.drift_type.value,
                    "severity": item.severity.value,
                    "observed_event_id": item.observed_event_id,
                    "observed_event_type": item.observed_event_type,
                    "pid": item.pid,
                    "expected_capability": item.expected_capability,
                    "observed_behavior": item.observed_behavior,
                }
                for item in self.drift_items
            ],
        }

    def to_observation_event(
        self,
        agent_id: str = "",
        attack_type: AttackType = AttackType.PRIVILEGE_ABUSE,
    ) -> ObservationEvent:
        """转为 ObservationEvent — 用于注入 SentinelDaemon 事件流"""
        severity_map: dict[DriftSeverity, Severity] = {
            DriftSeverity.LOW: Severity.LOW,
            DriftSeverity.MEDIUM: Severity.MEDIUM,
            DriftSeverity.HIGH: Severity.HIGH,
            DriftSeverity.CRITICAL: Severity.CRITICAL,
        }
        return ObservationEvent(
            event_id=self.report_id,
            source="capability_drift_detector",
            severity=severity_map.get(self.max_severity, Severity.MEDIUM),
            subject=agent_id or self.agent_id,
            attack_type=attack_type,
            evidence=self.to_audit_payload(),
        )


class CapabilityDriftDetector:
    """能力漂移检测器 — 对比声明能力与 ESF+NE 实际观测

    Usage:
        detector = CapabilityDriftDetector(hmac_key=key)
        # 注册 Agent 声明
        detector.register_agent(
            agent_id="claude-code",
            declared_capabilities=["network_read", "file_read"],
            declared_endpoints=["api.anthropic.com:443"],
        )
        # 喂入 ESF 观测事件
        for event in esf_events:
            drifts = detector.observe(event)
            if drifts:
                logger.warning("drift detected: %s", drifts)
        # 生成报告
        report = detector.generate_report(agent_id="claude-code")
        if report.total_drifts > 0:
            unified_audit_store.append(report.to_audit_payload())

    保证:
    - 2.2-A2: 检测 '声明 network_read 但实际 network_write' → DriftItem
    - 2.2-A3: CapabilityDriftReport 可写入 UnifiedAuditStore + to_observation_event()
    """

    def __init__(
        self,
        hmac_key: bytes,
        audit_callback: Any = None,
        quarantine_callback: Any = None,
        critical_drift_triggers_quarantine: bool = True,
    ) -> None:
        """初始化漂移检测器

        Args:
            hmac_key: HMAC-SHA256 签名密钥
            audit_callback: 审计回调 (CapabilityDriftReport -> None/Awaitable)
            quarantine_callback: 隔离回调 (agent_id -> None/Awaitable),CRITICAL 漂移触发
            critical_drift_triggers_quarantine: CRITICAL 漂移是否自动触发隔离
        """
        self._hmac_key = hmac_key
        self._audit_callback = audit_callback
        self._quarantine_callback = quarantine_callback
        self._critical_triggers_quarantine = critical_drift_triggers_quarantine

        # Agent 声明能力注册表
        # agent_id -> (capabilities, endpoints, registered_at)
        self._declared: dict[str, tuple[list[str], list[str], float]] = {}

        # 每个 Agent 的漂移记录累积
        # agent_id -> list[DriftItem]
        self._drifts: dict[str, list[DriftItem]] = {}

        # 报告时间范围
        self._report_starts: dict[str, float] = {}

    def register_agent(
        self,
        agent_id: str,
        declared_capabilities: list[str],
        declared_endpoints: list[str] | None = None,
    ) -> None:
        """注册 Agent 声明能力 (作为漂移检测基线)

        Args:
            agent_id: Agent ID
            declared_capabilities: SignedAgentCard.capabilities
            declared_endpoints: SignedAgentCard.endpoints (network_read 白名单)
        """
        endpoints = declared_endpoints or []
        self._declared[agent_id] = (
            list(declared_capabilities),
            list(endpoints),
            time.time(),
        )
        # 重置该 Agent 的漂移累积
        self._drifts[agent_id] = []
        self._report_starts[agent_id] = time.time()

    def unregister_agent(self, agent_id: str) -> None:
        """注销 Agent (停止漂移检测)"""
        self._declared.pop(agent_id, None)
        self._drifts.pop(agent_id, None)
        self._report_starts.pop(agent_id, None)

    def observe(self, event: ESFEvent) -> list[DriftItem]:
        """观测单个 ESF 事件,返回检测到的漂移列表

        Args:
            event: ESF 事件 (来自 xpc_bridge)

        Returns:
            漂移记录列表 (空列表 = 无漂移)
        """
        agent_id = event.agent_id
        if not agent_id or agent_id not in self._declared:
            return []

        capabilities, endpoints, _ = self._declared[agent_id]
        cap_set = set(capabilities)
        endpoint_set = set(endpoints)

        drifts: list[DriftItem] = []

        # 根据事件类型检测漂移
        if event.event_type == ESFEventType.CONNECT:
            drifts.extend(self._check_connect_drift(event, cap_set, endpoint_set))
        elif event.event_type == ESFEventType.BIND:
            drifts.extend(self._check_bind_drift(event, cap_set))
        elif event.event_type == ESFEventType.EXEC:
            drifts.extend(self._check_exec_drift(event, cap_set))
        elif event.event_type == ESFEventType.FORK:
            drifts.extend(self._check_fork_drift(event, cap_set))
        elif event.event_type == ESFEventType.OPEN:
            drifts.extend(self._check_open_drift(event, cap_set))
        elif event.event_type == ESFEventType.SETUID:
            drifts.extend(self._check_setuid_drift(event, cap_set))
        elif event.event_type == ESFEventType.SIGNAL:
            drifts.extend(self._check_signal_drift(event, cap_set))

        # 累积漂移
        if drifts:
            self._drifts.setdefault(agent_id, []).extend(drifts)

            # CRITICAL 漂移触发隔离
            if self._critical_triggers_quarantine and self._quarantine_callback:
                for d in drifts:
                    if d.severity == DriftSeverity.CRITICAL:
                        try:
                            result = self._quarantine_callback(agent_id)
                            if asyncio.iscoroutine(result):
                                try:
                                    loop = asyncio.get_running_loop()
                                    loop.create_task(result)
                                except RuntimeError:
                                    pass  # 无运行中事件循环,fire-and-forget
                        except Exception:
                            pass
                        break  # 一次观测只触发一次隔离

        return drifts

    def observe_batch(self, events: list[ESFEvent]) -> list[DriftItem]:
        """批量观测事件"""
        all_drifts: list[DriftItem] = []
        for event in events:
            drifts = self.observe(event)
            all_drifts.extend(drifts)
        return all_drifts

    def generate_report(self, agent_id: str) -> CapabilityDriftReport:
        """生成 Agent 的能力漂移报告

        Args:
            agent_id: Agent ID

        Returns:
            CapabilityDriftReport (HMAC 签名,可写入 UnifiedAuditStore)
        """
        items = list(self._drifts.get(agent_id, []))
        started = self._report_starts.get(agent_id, time.time())

        critical = sum(1 for d in items if d.severity == DriftSeverity.CRITICAL)
        high = sum(1 for d in items if d.severity == DriftSeverity.HIGH)
        medium = sum(1 for d in items if d.severity == DriftSeverity.MEDIUM)
        low = sum(1 for d in items if d.severity == DriftSeverity.LOW)

        if critical > 0:
            max_sev = DriftSeverity.CRITICAL
        elif high > 0:
            max_sev = DriftSeverity.HIGH
        elif medium > 0:
            max_sev = DriftSeverity.MEDIUM
        else:
            max_sev = DriftSeverity.LOW

        report = CapabilityDriftReport(
            agent_id=agent_id,
            started_at=started,
            ended_at=time.time(),
            drift_items=items,
            total_drifts=len(items),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            max_severity=max_sev,
        )
        signed = report.with_hash(self._hmac_key)

        # 审计回调 — 支持 sync/async
        if self._audit_callback:
            try:
                result = self._audit_callback(signed)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception:
                pass

        # 清空已报告的漂移累积
        self._drifts[agent_id] = []
        self._report_starts[agent_id] = time.time()

        return signed

    def get_pending_drifts(self, agent_id: str) -> list[DriftItem]:
        """获取未生成报告的累积漂移"""
        return list(self._drifts.get(agent_id, []))

    def list_registered_agents(self) -> list[str]:
        """列出已注册 Agent"""
        return list(self._declared.keys())

    def snapshot(self) -> dict[str, Any]:
        """状态快照 (调试/监控用)"""
        return {
            "registered_agents": len(self._declared),
            "total_pending_drifts": sum(len(v) for v in self._drifts.values()),
            "agents": {
                aid: {
                    "capabilities": caps,
                    "endpoints": eps,
                    "pending_drifts": len(self._drifts.get(aid, [])),
                }
                for aid, (caps, eps, _) in self._declared.items()
            },
        }

    # --- 漂移检测子方法 ---

    def _check_connect_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
        endpoint_set: set[str],
    ) -> list[DriftItem]:
        """检测 connect 事件漂移"""
        drifts: list[DriftItem] = []

        # 未声明 network_read/network_write → connect 是漂移
        if "network_read" not in cap_set and "network_write" not in cap_set:
            drifts.append(self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_NETWORK,
                expected_capability="network_read",
                observed_behavior=f"connect to {event.remote_addr}:{event.remote_port}",
            ))
            return drifts

        # 端点漂移 — 连接未声明的端点
        if "network_read" in cap_set and endpoint_set:
            observed_endpoint = f"{event.remote_addr}:{event.remote_port}"
            if observed_endpoint not in endpoint_set and event.remote_addr not in endpoint_set:
                # 检查 partial match (域名匹配)
                matched = any(
                    ep in observed_endpoint or observed_endpoint in ep
                    for ep in endpoint_set
                )
                if not matched:
                    drifts.append(self._make_drift(
                        event=event,
                        drift_type=DriftType.ENDPOINT_DRIFT,
                        expected_capability=f"network_read to {observed_endpoint}",
                        observed_behavior=f"connect to undeclared endpoint {observed_endpoint}",
                    ))
        return drifts

    def _check_bind_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 bind 事件漂移 — bind = inbound = network_write"""
        if "network_write" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_NETWORK_WRITE,
                expected_capability="network_write",
                observed_behavior=f"bind (inbound server) on port {event.remote_port}",
            )]
        return []

    def _check_exec_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 exec 事件漂移"""
        if "process_exec" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_PROCESS_EXEC,
                expected_capability="process_exec",
                observed_behavior=f"exec {event.path} argv={event.argv}",
            )]
        return []

    def _check_fork_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 fork 事件漂移"""
        if "process_spawn" not in cap_set and "process_exec" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_FORK,
                expected_capability="process_spawn",
                observed_behavior=f"fork child pid={event.ppid}",
            )]
        return []

    def _check_open_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 open 事件漂移

        注: ESF open 事件默认包含 read+write。需通过 evidence 中的 flags 判断:
        - O_RDONLY → file_read
        - O_WRONLY/O_RDWR → file_write
        """
        flags = event.evidence.get("flags", "")
        is_write = "WRONLY" in str(flags).upper() or "RDWR" in str(flags).upper()

        if is_write and "file_write" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_FILE_WRITE,
                expected_capability="file_write",
                observed_behavior=f"open for write: {event.path} flags={flags}",
            )]
        if not is_write and "file_read" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.CAPABILITY_OVERFLOW,
                expected_capability="file_read",
                observed_behavior=f"open for read: {event.path} flags={flags}",
            )]
        return []

    def _check_setuid_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 setuid 事件漂移 — 权限提升是 CRITICAL"""
        if "setuid" not in cap_set:
            return [self._make_drift(
                event=event,
                drift_type=DriftType.UNDECLARED_SETUID,
                expected_capability="setuid",
                observed_behavior=f"setuid to uid={event.evidence.get('uid', '?')}",
            )]
        return []

    def _check_signal_drift(
        self,
        event: ESFEvent,
        cap_set: set[str],
    ) -> list[DriftItem]:
        """检测 signal 事件漂移 — ptrace 通过 signal 实现"""
        if "ptrace" not in cap_set:
            sig = event.evidence.get("signal", "?")
            # SIGSTOP/SIGCONT 常用于 ptrace 攻击
            if sig in ("SIGSTOP", "SIGCONT", "SIGTRAP", 17, 18, 19, 5):
                return [self._make_drift(
                    event=event,
                    drift_type=DriftType.UNDECLARED_PTRACE,
                    expected_capability="ptrace",
                    observed_behavior=f"signal {sig} to pid={event.ppid}",
                )]
        return []

    def _make_drift(
        self,
        event: ESFEvent,
        drift_type: DriftType,
        expected_capability: str,
        observed_behavior: str,
    ) -> DriftItem:
        """构造 DriftItem"""
        cap_set = set(self._declared.get(event.agent_id, ([], [], 0))[0])
        return DriftItem(
            drift_type=drift_type,
            severity=_DRIFT_SEVERITY.get(drift_type, DriftSeverity.LOW),
            observed_event_id=event.event_id,
            observed_event_type=event.event_type.value,
            pid=event.pid,
            agent_id=event.agent_id,
            declared_capabilities=sorted(cap_set),
            observed_behavior=observed_behavior,
            expected_capability=expected_capability,
            evidence=event.to_observation_evidence(),
        )
