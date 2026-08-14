"""ActionChainTracker — 动作链追踪 (v0.52.1 G2-C1)。

按 agent 维护动作序列 (滑动窗口), 供链模式匹配 (C2)、意图假设 (C3)、
单步风险累积 (C4)、长时程关联 (C5) 消费。

对位 AISI 发现的治理缺口 G2: 单步动作看似合规, 组合构成欺骗性攻击。
本模块是"链级"治理的数据基础 — 从单步视角提升到序列视角。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionCategory(str, Enum):
    """动作类别 — 模式匹配的高层抽象 (忽略具体工具名)。"""

    CREATE = "create"  # 创建资源/账号
    READ = "read"  # 读取
    UPDATE = "update"  # 修改/编辑
    DELETE = "delete"  # 删除/清理痕迹
    COMMUNICATE = "communicate"  # 对外通信 (消息/邮件/留言)
    EXTERNAL = "external"  # 外部平台操作 (GitHub PR/评论)
    CREDENTIAL = "credential"  # 凭证/身份相关
    IDENTITY = "identity"  # 账号/身份管理
    NETWORK = "network"  # 网络访问 (含匿名网络)
    EXECUTE = "execute"  # 执行代码/命令
    OTHER = "other"


class ChainRiskLevel(str, Enum):
    """单步或链级风险分级。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ActionRecord:
    """一条动作链中的单步动作。

    Attributes:
        action: 动作标识 (如 ``github.create_account``)。
        agent_id: 执行 agent。
        category: 动作类别 (模式匹配用)。
        timestamp: 动作时间戳。
        risk_level: 单步风险分级 (来自 risk_classifier)。
        subject: 作用对象 (目标资源/文件/账号)。
        outcome: 动作结果 (success/denied/failed)。
        metadata: 结构化上下文 (外部账号/接收方/URL 等)。
        record_id: 记录唯一标识。
    """

    action: str
    agent_id: str = ""
    category: ActionCategory = ActionCategory.OTHER
    timestamp: float = field(default_factory=time.time)
    risk_level: ChainRiskLevel = ChainRiskLevel.LOW
    subject: str = ""
    outcome: str = "success"
    metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "action": self.action,
            "agent_id": self.agent_id,
            "category": self.category.value,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level.value,
            "subject": self.subject,
            "outcome": self.outcome,
            "metadata": self.metadata,
        }


class ActionChainTracker:
    """动作链追踪器 (按 agent 维护滑动窗口序列)。

    Usage::

        tracker = ActionChainTracker(window_seconds=3600)
        tracker.record(ActionRecord(action="github.create_account",
                                    agent_id="agent-01",
                                    category=ActionCategory.IDENTITY))
        chain = tracker.chain("agent-01")

    Attributes:
        window_seconds: 滑动窗口时长 (默认 1 小时, 用于剔除过期记录)。
    """

    def __init__(self, window_seconds: float = 3600.0) -> None:
        self.window_seconds = window_seconds
        self._chains: dict[str, list[ActionRecord]] = {}

    def record(self, record: ActionRecord) -> None:
        """记录一条动作 (自动剔除过期记录)。"""
        if not record.agent_id:
            raise ValueError("ActionRecord.agent_id 不能为空")
        self._chains.setdefault(record.agent_id, []).append(record)
        self._prune(record.agent_id)

    def chain(self, agent_id: str, window_seconds: float | None = None) -> list[ActionRecord]:
        """返回 agent 的滑动窗口动作链 (按时间升序)。

        Args:
            agent_id: agent 标识。
            window_seconds: 覆盖默认窗口 (可选)。

        Returns:
            时间升序的动作记录列表。
        """
        records = self._chains.get(agent_id, [])
        if window_seconds is not None:
            cutoff = time.time() - window_seconds
            records = [r for r in records if r.timestamp >= cutoff]
        return sorted(records, key=lambda r: r.timestamp)

    def all_chains(self) -> dict[str, list[ActionRecord]]:
        """返回全部 agent 的动作链 (已剔除过期)。"""
        result: dict[str, list[ActionRecord]] = {}
        for agent_id in list(self._chains.keys()):
            pruned = self._prune(agent_id)
            if pruned:
                result[agent_id] = pruned
        return result

    def recent_agents(self) -> list[str]:
        """返回近期有动作的 agent ID 列表。"""
        return [aid for aid, ch in self.all_chains().items() if ch]

    def chain_length(self, agent_id: str) -> int:
        return len(self._chains.get(agent_id, []))

    def clear(self, agent_id: str) -> None:
        """清空某 agent 的动作链 (隔离/恢复后使用)。"""
        self._chains.pop(agent_id, None)

    def _prune(self, agent_id: str) -> list[ActionRecord]:
        """剔除超过窗口的记录, 返回剩余链。"""
        cutoff = time.time() - self.window_seconds
        records = self._chains.get(agent_id, [])
        kept = [r for r in records if r.timestamp >= cutoff]
        self._chains[agent_id] = kept
        return kept

    def latest(self, agent_id: str) -> ActionRecord | None:
        """返回 agent 最近一条动作 (无则 None)。"""
        chain = self.chain(agent_id)
        return chain[-1] if chain else None
