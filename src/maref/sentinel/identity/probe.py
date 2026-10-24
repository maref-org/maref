"""IdentityProbe — 外部身份指纹 sentinel Probe (v0.52.1 G1-B5)。

将 G1 检测器接入 sentinel 观测管线: 周期 poll 时对账号登记数据执行
sybil/共谋检测, 产出 ObservationEvent。

事件类型:
- ``IDENTITY_SPOOFING`` — 未声明外部账号 (登记 vs 实际漂移)
- ``SYBIL_ATTACK`` — 多重身份聚类检出

设计:
- 事件产出去重 (同一 signal 只产一次, 以 event 内容 hash 为键)
- poll 为无状态拉取: 检测依赖登记数据, 由外部 (identity collector) 调用
  ``submit_*`` 填充
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from maref.sentinel.event import AttackType, ObservationEvent, Severity
from maref.sentinel.identity.account_registry import (
    ExternalAccount,
    ExternalAccountRegistry,
)
from maref.sentinel.identity.collusion_detector import (
    CollusionDetector,
    EndorsementEvent,
)
from maref.sentinel.identity.fingerprint import FingerprintProfile
from maref.sentinel.identity.sybil_detector import SybilDetector
from maref.sentinel.probes.base import Probe, ProbeConfig


class IdentityProbe(Probe):
    """外部身份指纹观测 Probe。

    Usage::

        probe = IdentityProbe(
            config=ProbeConfig(hmac_key=key),
            registry=registry, sybil=sybil_detector, collusion=collusion_detector)
        await probe.start()
        probe.submit_account(account, profile)
        events = await probe.poll()
        await probe.stop()
    """

    def __init__(
        self,
        config: ProbeConfig,
        registry: ExternalAccountRegistry,
        sybil_detector: SybilDetector | None = None,
        collusion_detector: CollusionDetector | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._sybil = sybil_detector or SybilDetector()
        self._collusion = collusion_detector or CollusionDetector()
        self._profiles: dict[str, FingerprintProfile] = {}
        self._emitted: set[str] = set()
        self._started = False
        self._events_pending: list[ObservationEvent] = []

    @property
    def probe_name(self) -> str:
        return "identity"

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def health_check(self) -> bool:
        return True

    # -- 外部数据入口 --

    def submit_account(
        self,
        account: ExternalAccount,
        profile: FingerprintProfile | None = None,
    ) -> None:
        """登记外部账号 (含可选行为指纹)。

        G1-I4 修复: 使用 registry 实际返回的记录 ID 存指纹 — 幂等命中时
        register() 返回已存在的记录, 避免 profile 错位到孤儿 account_id。
        """
        registered = self._registry.register(account)
        if profile is not None:
            # 指纹归到 registry 实际生效的 account_id
            self._profiles[registered.account_id] = profile
            registered.profile_id = profile.profile_id

    def submit_endorsement(self, event: EndorsementEvent) -> None:
        """提交一条背书事件 (供共谋检测)。"""
        self._collusion.record_endorsement(event)

    def submitted_profiles(self) -> dict[str, FingerprintProfile]:
        return dict(self._profiles)

    # -- Probe 生命周期 --

    async def poll(self) -> list[ObservationEvent]:
        """执行一次身份检测, 返回 (去重后) 观测事件。

        Returns:
            本次 poll 新产出的事件列表。重复信号不重复产出。
        """
        events: list[ObservationEvent] = []

        # 1. 未声明账号 → IDENTITY_SPOOFING
        for account in self._registry.undeclared_accounts():
            signal_key = f"spoof:{account.account_id}"
            if signal_key in self._emitted:
                continue
            events.append(
                self._build_event(
                    attack_type=AttackType.IDENTITY_SPOOFING,
                    severity=Severity.HIGH,
                    subject=account.agent_did or account.account_id,
                    evidence={
                        "platform": account.platform.value,
                        "handle": account.handle,
                        "account_id": account.account_id,
                        "agent_did": account.agent_did,
                        "reason": "undeclared_external_account",
                    },
                )
            )
            self._emitted.add(signal_key)

        # 2. sybil 聚类 → SYBIL_ATTACK
        clusters = self._sybil.detect(
            self._registry.all_accounts(),
            self._profiles,
        )
        for cluster in clusters:
            # 稳定去重键: 排序账号集合哈希 (cluster_id 每次 poll 重新生成,
            # 不能作去重键 — G1-C1 修复)
            cluster_sig = hashlib.sha256("|".join(sorted(cluster.account_ids)).encode()).hexdigest()
            signal_key = f"sybil:{cluster_sig}"
            if signal_key in self._emitted:
                continue
            events.append(
                self._build_event(
                    attack_type=AttackType.SYBIL_ATTACK,
                    severity=Severity.HIGH,
                    subject=cluster.agent_did or cluster.cluster_id,
                    evidence={
                        "cluster_id": cluster.cluster_id,
                        "account_ids": cluster.account_ids,
                        "agent_did": cluster.agent_did,
                        "confidence": round(cluster.confidence, 3),
                        "signals": cluster.signals,
                    },
                )
            )
            self._emitted.add(signal_key)

        # 3. 共谋检测 → SYBIL_ATTACK (CRITICAL 用于明确自导自演)
        report = self._collusion.detect(
            self._registry.all_accounts(),
            self._sybil.last_clusters,
            registry=self._registry,
        )
        for collusion in report.events:
            # 稳定去重键: kind + 排序涉及账号 (timestamp 每次重建 — G1-C2 修复)
            involved_sig = hashlib.sha256(
                "|".join(sorted(collusion.involved_accounts)).encode()
            ).hexdigest()
            signal_key = f"collusion:{collusion.kind.value}:{involved_sig}"
            if signal_key in self._emitted:
                continue
            events.append(
                self._build_event(
                    attack_type=AttackType.SYBIL_ATTACK,
                    severity=Severity.CRITICAL,
                    subject="|".join(collusion.involved_accounts) or "collusion",
                    evidence={
                        "kind": collusion.kind.value,
                        "label": collusion.kind.label,
                        "involved_accounts": collusion.involved_accounts,
                        "description": collusion.description,
                        "confidence": round(collusion.confidence, 3),
                    },
                )
            )
            self._emitted.add(signal_key)

        return events

    # -- 事件构造 --

    def _build_event(
        self,
        attack_type: AttackType,
        severity: Severity,
        subject: str,
        evidence: dict[str, Any],
    ) -> ObservationEvent:
        event = ObservationEvent(
            event_id=str(uuid.uuid4()),
            ts=time.time(),
            source=self.probe_name,
            severity=severity,
            subject=subject,
            attack_type=attack_type,
            evidence=evidence,
        )
        if self._config.hmac_key:
            event = event.with_hash(self._config.hmac_key)
        return event
