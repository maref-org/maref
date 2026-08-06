"""SybilDetector — 多重身份聚类 (v0.52.1 G1-B3)。

检测 sockpuppet/sybil: 同一主体在外部平台持有多个身份协同欺骗。
对位 AISI 发现 ①: 代理创建多个虚假 GitHub 身份自导自演。

检测依据:
1. **行为指纹聚类** — 指纹相似度 ≥ 阈值 → 图连通分量 = 候选同一主体
2. **短窗口多账号** — 同一 agent 在时间窗口内注册多账号
3. **未声明账号** — 集群含 declared=False 账号 → 伪造证据

输出 ``SybilCluster`` (集群账号 + 主体 DID + 置信度 + 信号), 供
``IdentityProbe`` 产出 ObservationEvent (AttackType=SYBIL_ATTACK)。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.sentinel.identity.account_registry import ExternalAccount
from maref.sentinel.identity.fingerprint import FingerprintProfile, IdentityFingerprint


@dataclass
class SybilCluster:
    """一个被判定为同一主体的外部身份集群。

    Attributes:
        cluster_id: 集群唯一标识。
        account_ids: 集群内账号 ID 列表。
        agent_did: 主体系统内 DID (集群中声明 DID 的多数)。
        confidence: 集群置信度 0.0~1.0。
        signals: 检测信号 (fingerprint_similarity / short_window_multi / undeclared)。
        avg_similarity: 集群内平均指纹相似度。
        created_at: 检测时间戳。
    """

    cluster_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_ids: list[str] = field(default_factory=list)
    agent_did: str = ""
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    avg_similarity: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "account_ids": self.account_ids,
            "agent_did": self.agent_did,
            "confidence": round(self.confidence, 3),
            "signals": self.signals,
            "avg_similarity": round(self.avg_similarity, 3),
            "created_at": self.created_at,
        }


# 默认参数
_DEFAULT_SIM_THRESHOLD = 0.7  # 指纹相似度 ≥ 0.7 视为同主体
_DEFAULT_MIN_CLUSTER = 2  # 最少账号数
_DEFAULT_WINDOW_HOURS = 24.0  # 短窗口 (小时)
_DEFAULT_WINDOW_MIN_ACCOUNTS = 3  # 短窗口内账号数阈值


class SybilDetector:
    """Sybil 身份聚类检测器。

    Usage::

        detector = SybilDetector()
        clusters = detector.detect(accounts, profiles)
        # clusters: list[SybilCluster]

    Attributes:
        sim_threshold: 指纹相似度阈值。
        min_cluster: 最小集群账号数。
        window_hours: 短窗口时长。
        window_min_accounts: 短窗口内账号数阈值。
    """

    def __init__(
        self,
        sim_threshold: float = _DEFAULT_SIM_THRESHOLD,
        min_cluster: int = _DEFAULT_MIN_CLUSTER,
        window_hours: float = _DEFAULT_WINDOW_HOURS,
        window_min_accounts: int = _DEFAULT_WINDOW_MIN_ACCOUNTS,
    ) -> None:
        self.sim_threshold = sim_threshold
        self.min_cluster = min_cluster
        self.window_hours = window_hours
        self.window_min_accounts = window_min_accounts
        self._fingerprint = IdentityFingerprint()
        self._clusters: list[SybilCluster] = []

    def detect(
        self,
        accounts: list[ExternalAccount],
        profiles: dict[str, FingerprintProfile] | None = None,
    ) -> list[SybilCluster]:
        """对账号集合执行 sybil 聚类检测。

        Args:
            accounts: 外部账号列表。
            profiles: account_id -> 行为指纹 (可选; 缺省时跳过指纹维度)。

        Returns:
            SybilCluster 列表 (按置信度降序)。
        """
        profiles = profiles or {}
        self._clusters = []

        # 信号 1: 指纹相似度连通分量
        sim_groups = self._cluster_by_similarity(accounts, profiles)

        # 信号 2: 短窗口多账号 (同 agent)
        window_groups = self._cluster_by_window(accounts)

        # 合并候选集群 (union by account)
        groups = self._union_groups(sim_groups + window_groups)

        for group in groups:
            if len(group) < self.min_cluster:
                continue
            cluster = self._build_cluster(group, accounts, profiles)
            if cluster is not None:
                self._clusters.append(cluster)

        self._clusters.sort(key=lambda c: c.confidence, reverse=True)
        return list(self._clusters)

    @property
    def last_clusters(self) -> list[SybilCluster]:
        """最近一次检测结果。"""
        return list(self._clusters)

    # -- 内部: 指纹相似度聚类 --

    def _cluster_by_similarity(
        self,
        accounts: list[ExternalAccount],
        profiles: dict[str, FingerprintProfile],
    ) -> list[list[str]]:
        """基于指纹相似度构建连通分量。

        节点 = account_id; 边 = similarity(profile_a, profile_b) >= threshold。
        """
        nodes: list[str] = [a.account_id for a in accounts if a.account_id in profiles]
        if len(nodes) < 2:
            return []

        # 邻接表
        adj: dict[str, list[str]] = {n: [] for n in nodes}
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                sim = self._fingerprint.similarity(profiles[a], profiles[b])
                if sim >= self.sim_threshold:
                    adj[a].append(b)
                    adj[b].append(a)

        # BFS 连通分量
        visited: set[str] = set()
        components: list[list[str]] = []
        for node in nodes:
            if node in visited:
                continue
            stack = [node]
            visited.add(node)
            comp: list[str] = []
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in adj[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
            components.append(comp)
        return components

    def _cluster_by_window(
        self,
        accounts: list[ExternalAccount],
    ) -> list[list[str]]:
        """短窗口内同 agent 多账号聚类。

        同一 agent_did 在 window_hours 窗口内注册 >= window_min_accounts 个账号。
        """
        # 按 agent 分组
        by_agent: dict[str, list[ExternalAccount]] = {}
        for acc in accounts:
            if acc.agent_did:
                by_agent.setdefault(acc.agent_did, []).append(acc)

        groups: list[list[str]] = []
        for _agent, accs in by_agent.items():
            if len(accs) < self.window_min_accounts:
                continue
            sorted_accs = sorted(accs, key=lambda a: a.first_seen)
            # 滑动窗口: 找最大窗口覆盖的账号集
            for start_i in range(len(sorted_accs)):
                window_end = sorted_accs[start_i].first_seen + self.window_hours * 3600
                group = [
                    a.account_id
                    for a in sorted_accs
                    if a.first_seen <= window_end
                ]
                if len(group) >= self.window_min_accounts:
                    groups.append(group)
        return groups

    def _union_groups(self, groups: list[list[str]]) -> list[list[str]]:
        """合并重叠的候选组 (按账号 ID 取并集)。"""
        parent: dict[str, str] = {}
        group_id_of: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # 组内账号并查集
        for group in groups:
            if not group:
                continue
            for acc in group[1:]:
                union(group[0], acc)
            group_id_of[group[0]] = group[0]

        merged: dict[str, set[str]] = {}
        for group in groups:
            root = find(group[0])
            merged.setdefault(root, set()).update(group)

        return [sorted(ids) for ids in merged.values() if len(ids) >= self.min_cluster]

    def _build_cluster(
        self,
        account_ids: list[str],
        accounts: list[ExternalAccount],
        profiles: dict[str, FingerprintProfile],
    ) -> SybilCluster | None:
        """从候选账号集构建 SybilCluster (含信号与置信度)。"""
        by_id = {a.account_id: a for a in accounts}
        members = [by_id[i] for i in account_ids if i in by_id]
        if len(members) < self.min_cluster:
            return None

        signals: list[str] = []
        # 信号: 未声明账号
        undeclared = [m for m in members if not m.declared]
        if undeclared:
            signals.append("undeclared")

        # 信号: 短窗口多账号
        if self._is_short_window(members):
            signals.append("short_window_multi")

        # 信号: 指纹相似
        avg_sim = 0.0
        sim_accounts = [m for m in members if m.account_id in profiles]
        if len(sim_accounts) >= 2:
            pairs = 0
            total = 0.0
            for i in range(len(sim_accounts)):
                for j in range(i + 1, len(sim_accounts)):
                    total += self._fingerprint.similarity(
                        profiles[sim_accounts[i].account_id],
                        profiles[sim_accounts[j].account_id],
                    )
                    pairs += 1
            avg_sim = total / pairs if pairs else 0.0
            if avg_sim >= self.sim_threshold:
                signals.append("fingerprint_similarity")

        if not signals:
            return None

        # 主体 DID: 声明 DID 的多数
        did_counter: dict[str, int] = {}
        for m in members:
            if m.agent_did:
                did_counter[m.agent_did] = did_counter.get(m.agent_did, 0) + 1
        agent_did = max(did_counter, key=lambda k: did_counter[k]) if did_counter else ""

        confidence = self._compute_confidence(members, signals, avg_sim)

        return SybilCluster(
            account_ids=account_ids,
            agent_did=agent_did,
            confidence=confidence,
            signals=signals,
            avg_similarity=avg_sim,
        )

    def _is_short_window(self, members: list[ExternalAccount]) -> bool:
        if len(members) < 2:
            return False
        sorted_accs = sorted(members, key=lambda a: a.first_seen)
        span = sorted_accs[-1].first_seen - sorted_accs[0].first_seen
        return span <= self.window_hours * 3600 and len(members) >= self.window_min_accounts

    def _compute_confidence(
        self,
        members: list[ExternalAccount],
        signals: list[str],
        avg_sim: float,
    ) -> float:
        base = 0.5
        if "fingerprint_similarity" in signals:
            base += 0.3 * avg_sim
        if "short_window_multi" in signals:
            base += 0.1
        if "undeclared" in signals:
            base += 0.1
        return min(1.0, base)
