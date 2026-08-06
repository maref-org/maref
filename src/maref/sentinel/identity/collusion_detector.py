"""CollusionDetector — 自导自演 / 交叉背书 / 跨代理共谋检测 (v0.52.1 G1-B4)。

对位 AISI 发现 ① 与 ④:
- 发现 ①: 一个假账号假装"独立审查"代码并声称无恶意, 另一个假账号感谢这个
  "独立审查" — 这是**自导自演** (self-endorsement)。
- 发现 ④: 代理在 GitHub 公开留言邀请其他代理复用其账号与"遗产" — 这是
  **跨代理资源共享** (cross-agent account sharing)。

三类检测:
1. **自导自演** (self_endorsement): 背书者与被背书者实际属同一主体
   (同 agent_did 或同 SybilCluster)
2. **互相背书** (mutual_endorsement): A 背书 B 且 B 背书 A (吹捧闭环)
3. **跨代理账号共享** (cross_agent_share): 同一外部账号被多个不同 agent 使用
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.sentinel.identity.account_registry import ExternalAccount
from maref.sentinel.identity.sybil_detector import SybilCluster, SybilDetector


class EndorsementKind(str, Enum):
    """背书事件类型。"""

    REVIEW = "review"  # 审查/评审
    APPROVE = "approve"  # 批准/认可
    THANK = "thank"  # 感谢/致谢
    ENDORSE = "endorse"  # 一般背书/推荐
    SHARE = "share"  # 共享资源/账号 (发现 ④)


@dataclass(frozen=True)
class EndorsementEvent:
    """一条背书事件。

    Attributes:
        endorser_account: 背书者外部账号 ID。
        target_account: 被背书者外部账号 ID (空 = 非账号背书, 如分享资源)。
        action: 背书类型。
        agent_did: 背书者系统内 DID (未知可为空)。
        target_agent_did: 被背书者系统内 DID (未知可为空)。
        shared_resource: 若为 SHARE, 共享的外部资源标识 (账号/令牌/URL)。
        timestamp: 事件时间戳。
        event_id: 事件唯一标识。
    """

    endorser_account: str
    target_account: str = ""
    action: EndorsementKind = EndorsementKind.ENDORSE
    agent_did: str = ""
    target_agent_did: str = ""
    shared_resource: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "endorser_account": self.endorser_account,
            "target_account": self.target_account,
            "action": self.action.value,
            "agent_did": self.agent_did,
            "target_agent_did": self.target_agent_did,
            "shared_resource": self.shared_resource,
            "timestamp": self.timestamp,
        }


class CollusionKind(str, Enum):
    """共谋信号类型。"""

    SELF_ENDORSEMENT = "self_endorsement"  # 自导自演
    MUTUAL_ENDORSEMENT = "mutual_endorsement"  # 互相背书闭环
    CROSS_AGENT_SHARE = "cross_agent_share"  # 跨代理共享账号/资源

    @property
    def label(self) -> str:
        return {
            CollusionKind.SELF_ENDORSEMENT: "自导自演",
            CollusionKind.MUTUAL_ENDORSEMENT: "互相背书",
            CollusionKind.CROSS_AGENT_SHARE: "跨代理共享",
        }[self]


@dataclass
class CollusionEvent:
    """一条检测到的共谋信号。

    Attributes:
        kind: 共谋类型。
        involved_accounts: 涉及的外部账号 ID。
        description: 描述。
        confidence: 置信度 0.0~1.0。
        evidence: 关联的背书事件 ID 列表。
        timestamp: 检测时间。
    """

    kind: CollusionKind
    involved_accounts: list[str] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.kind.label,
            "involved_accounts": self.involved_accounts,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class CollusionReport:
    """共谋检测聚合报告。"""

    events: list[CollusionEvent] = field(default_factory=list)
    endorsement_count: int = 0
    detected_at: float = field(default_factory=time.time)

    @property
    def has_signal(self) -> bool:
        return len(self.events) > 0

    @property
    def max_confidence(self) -> float:
        return max((e.confidence for e in self.events), default=0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "endorsement_count": self.endorsement_count,
            "max_confidence": round(self.max_confidence, 3),
            "detected_at": self.detected_at,
        }


class CollusionDetector:
    """共谋/自导自演检测器。

    Usage::

        detector = CollusionDetector()
        detector.record_endorsement(EndorsementEvent(
            endorser_account="acct-a", target_account="acct-b",
            action=EndorsementKind.REVIEW, agent_did="agent-01"))
        report = detector.detect()
        if report.has_signal:
            ...
    """

    def __init__(
        self,
        sybil_detector: SybilDetector | None = None,
        min_confidence: float = 0.5,
    ) -> None:
        self._sybil = sybil_detector or SybilDetector()
        self.min_confidence = min_confidence
        self._endorsements: list[EndorsementEvent] = []
        self._events: list[CollusionEvent] = []

    def record_endorsement(self, event: EndorsementEvent) -> None:
        """记录一条背书事件。"""
        self._endorsements.append(event)

    def detect(
        self,
        accounts: list[ExternalAccount] | None = None,
        sybil_clusters: list[SybilCluster] | None = None,
        registry: Any | None = None,
    ) -> CollusionReport:
        """执行共谋检测。

        Args:
            accounts: 外部账号列表 (供跨代理共享检测)。
            sybil_clusters: 已知 sybil 集群 (供自导自演判定, 可选)。
            registry: ExternalAccountRegistry (可选)。提供后跨代理共享检测
                优先使用 registry 的使用历史 (G1-C3 修复: 幂等注册表语义下
                检测仍可靠)。

        Returns:
            CollusionReport。
        """
        self._events = []
        accounts = accounts or []
        sybil_clusters = sybil_clusters or []

        self._detect_self_endorsement(sybil_clusters)
        self._detect_mutual_endorsement()
        self._detect_cross_agent_share(accounts, registry)

        return CollusionReport(
            events=list(self._events),
            endorsement_count=len(self._endorsements),
        )

    # -- 内部检测 --

    def _account_to_agent(self, account_id: str) -> str:
        """从背书事件推断账号所属 agent (最近一次出现为准)。"""
        for ev in reversed(self._endorsements):
            if ev.endorser_account == account_id and ev.agent_did:
                return ev.agent_did
        return ""

    def _detect_self_endorsement(
        self, sybil_clusters: list[SybilCluster]
    ) -> None:
        """自导自演: 背书者与被背书者同 agent 或同 sybil 集群。"""
        for ev in self._endorsements:
            if not ev.target_account:
                continue
            # 同 agent_did
            if ev.agent_did and ev.agent_did == ev.target_agent_did and ev.agent_did:
                self._events.append(
                    CollusionEvent(
                        kind=CollusionKind.SELF_ENDORSEMENT,
                        involved_accounts=[ev.endorser_account, ev.target_account],
                        description=(
                            f"自导自演: agent {ev.agent_did} 的账号 "
                            f"{ev.endorser_account} 背书同主体的账号 {ev.target_account}"
                        ),
                        confidence=0.9,
                        evidence=[ev.event_id],
                    )
                )
                continue
            # 同 sybil 集群
            for cluster in sybil_clusters:
                ids = set(cluster.account_ids)
                if (
                    ev.endorser_account in ids
                    and ev.target_account in ids
                    and len(ids) >= 2
                ):
                    self._events.append(
                        CollusionEvent(
                            kind=CollusionKind.SELF_ENDORSEMENT,
                            involved_accounts=[ev.endorser_account, ev.target_account],
                            description=(
                                f"自导自演: 同 sybil 集群 {cluster.cluster_id[:8]} 内"
                                f"账号互相背书 ({ev.endorser_account} → {ev.target_account})"
                            ),
                            confidence=0.85,
                            evidence=[ev.event_id],
                        )
                    )
                    break

    def _detect_mutual_endorsement(self) -> None:
        """互相背书: A 背书 B 且 B 背书 A。"""
        pairs: dict[tuple[str, str], list[EndorsementEvent]] = {}
        for ev in self._endorsements:
            if not ev.target_account:
                continue
            key = (ev.endorser_account, ev.target_account)
            pairs.setdefault(key, []).append(ev)

        for (a, b), evs in pairs.items():
            if (b, a) in pairs:
                ev_ids = [e.event_id for e in evs + pairs[(b, a)]]
                self._events.append(
                    CollusionEvent(
                        kind=CollusionKind.MUTUAL_ENDORSEMENT,
                        involved_accounts=[a, b],
                        description=f"互相背书闭环: {a} ↔ {b}",
                        confidence=0.75,
                        evidence=ev_ids,
                    )
                )

    def _detect_cross_agent_share(
        self, accounts: list[ExternalAccount], registry: Any | None = None
    ) -> None:
        """跨代理共享: 同一外部账号被多个不同 agent 使用, 或 SHARE 事件显式共享。

        registry 提供时优先使用其使用历史 (``agents_using``), 因为幂等注册
        表语义下同 handle 只保留一条记录 — 仅靠 accounts 列表无法观测到
        多 agent 使用 (G1-C3 修复)。
        """
        # 1. 跨代理共享: 同一外部句柄被 ≥2 个 agent 使用 (发现 ④)
        if registry is not None:
            # 优先: registry 使用历史
            handle_accounts: dict[tuple[str, str], list[str]] = {}
            for acc in accounts:
                key = (acc.platform.value, acc.handle.lower())
                if acc.account_id not in handle_accounts.setdefault(key, []):
                    handle_accounts[key].append(acc.account_id)
            for (platform, handle), agents in registry.all_usage().items():
                if len(agents) >= 2:
                    self._events.append(
                        CollusionEvent(
                            kind=CollusionKind.CROSS_AGENT_SHARE,
                            involved_accounts=handle_accounts.get(
                                (platform, handle), []
                            ),
                            description=(
                                f"跨代理共享账号 {handle} ({platform}): agents "
                                f"{', '.join(sorted(agents))}"
                            ),
                            confidence=0.8,
                        )
                    )
        else:
            handle_agents: dict[tuple[str, str], tuple[set[str], list[str]]] = {}
            for acc in accounts:
                if not acc.agent_did:
                    continue
                key = (acc.platform.value, acc.handle.lower())
                agents, account_ids = handle_agents.setdefault(key, (set(), []))
                agents.add(acc.agent_did)
                if acc.account_id not in account_ids:
                    account_ids.append(acc.account_id)
            for (platform, handle), (agents, account_ids) in handle_agents.items():
                if len(agents) >= 2:
                    self._events.append(
                        CollusionEvent(
                            kind=CollusionKind.CROSS_AGENT_SHARE,
                            involved_accounts=account_ids,
                            description=(
                                f"跨代理共享账号 {handle} ({platform}): agents "
                                f"{', '.join(sorted(agents))}"
                            ),
                            confidence=0.8,
                        )
                    )

        # 2. 显式 SHARE 事件 (发现 ④: 公开留言邀请复用)
        for ev in self._endorsements:
            if ev.action == EndorsementKind.SHARE:
                self._events.append(
                    CollusionEvent(
                        kind=CollusionKind.CROSS_AGENT_SHARE,
                        involved_accounts=[ev.endorser_account],
                        description=(
                            f"公开共享资源: {ev.endorser_account} 共享 "
                            f"'{ev.shared_resource or '未知资源'}'"
                        ),
                        confidence=0.7,
                        evidence=[ev.event_id],
                    )
                )
