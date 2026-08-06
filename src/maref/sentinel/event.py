"""
ObservationEvent — sentinel 观测事件的统一 schema

所有 Probe / Backend 必须产出此类型。事件带 HMAC-SHA256 签名,
任何篡改导致 verify_event_hash() 返回 False。

HMAC 计算规则 (与 validation-contract.md 第七节一致):
    payload = f"{event_id}|{ts:.6f}|{subject}|{json.dumps(evidence, sort_keys=True)}"
    hash = hmac.new(hmac_key, payload.encode(), hashlib.sha256).hexdigest()
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """观测事件严重度分级 — 决定 ThreatBridge 的处置动作"""

    CRITICAL = "CRITICAL"  # 检出 5 类攻击 + Agent 信用分 < 30 → force_halt + quarantine
    HIGH = "HIGH"  # 检出 5 类攻击 + Agent 信用分 ≥ 30 → force_stabilize + JustInTimeConsent
    MEDIUM = "MEDIUM"  # capability drift → log_only + 信用分 -10
    LOW = "LOW"  # 异常但未确认恶意 → log_only


class AttackType(str, Enum):
    """sentinel 目标攻击类型枚举 (5 类 + none)"""

    PIXEL_TRACKING = "pixel_tracking"  # ① 邮件像素追踪
    SILENT_TIMEZONE = "silent_timezone"  # ② 静默时区读取
    ENV_EXFIL = "env_exfil"  # ③ 环境变量外泄
    STEGANOGRAPHY = "steganography"  # ④ 日期分隔符隐写
    PRIVILEGE_ABUSE = "privilege_abuse"  # ⑤ 权限滥用
    NONE = "none"  # 无攻击 (用于 capability drift / 异常但未确认)


SEVERITY_LEVELS: dict[str, Severity] = {s.value: s for s in Severity}
ATTACK_TYPES: dict[str, AttackType] = {a.value: a for a in AttackType}


@dataclass(frozen=True)
class ObservationEvent:
    """sentinel 观测事件的统一 schema — 所有 Probe 必须产出此类型

    不可变 (frozen=True) 以保证证据完整性。任何字段变化需要重新计算 hash。

    Attributes:
        event_id: UUID v4,事件唯一标识
        ts: unix timestamp (秒,毫秒精度)
        source: probe 名 (process|env|file|timezone|network_egress|prompt_baseline|esf|ebpf|psutil)
        severity: 严重度 (CRITICAL|HIGH|MEDIUM|LOW)
        subject: 被观测对象 (agent_id|pid|session_id)
        attack_type: 攻击类型 (5 类 + none)
        evidence: 结构化证据 (每个 probe 自定义 schema)
        hash: HMAC-SHA256(event_id + ts + subject + evidence_json)
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=lambda: _now_ts())
    source: str = ""
    severity: Severity = Severity.LOW
    subject: str = ""
    attack_type: AttackType = AttackType.NONE
    evidence: dict[str, Any] = field(default_factory=dict)
    hash: str = ""  # 由 compute_event_hash() 填充

    def with_hash(self, hmac_key: bytes) -> ObservationEvent:
        """返回带 HMAC 签名的不可变副本 (frozen dataclass 的 with 模式)"""
        new_hash = compute_event_hash(self, hmac_key)
        return ObservationEvent(
            event_id=self.event_id,
            ts=self.ts,
            source=self.source,
            severity=self.severity,
            subject=self.subject,
            attack_type=self.attack_type,
            evidence=self.evidence,
            hash=new_hash,
        )


def _now_ts() -> float:
    """获取当前 unix timestamp (秒,毫秒精度)"""
    import time

    return time.time()


def compute_event_hash(event: ObservationEvent, hmac_key: bytes) -> str:
    """计算 ObservationEvent 的 HMAC-SHA256 签名

    payload 格式: f"{event_id}|{ts:.6f}|{subject}|{json.dumps(evidence, sort_keys=True)}"
    """
    payload = (
        f"{event.event_id}|"
        f"{event.ts:.6f}|"
        f"{event.subject}|"
        f"{json.dumps(event.evidence, sort_keys=True, default=str)}"
    )
    return hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_event_hash(event: ObservationEvent, hmac_key: bytes) -> bool:
    """验证 ObservationEvent 的 HMAC 签名 — 任何篡改返回 False"""
    if not event.hash:
        return False
    expected = compute_event_hash(event, hmac_key)
    # 使用 hmac.compare_digest 防止时序攻击
    return hmac.compare_digest(event.hash, expected)
