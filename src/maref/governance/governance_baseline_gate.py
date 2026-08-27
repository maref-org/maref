"""Governance Baseline Gate — 治理提案底线语义预检 (P1-A2).

来源: P1-A PoC 盲点 C —— 红队用"折中方案"(compromise) 包装攻击,
若治理审查仅靠 LLM 讨论, 折中方案可能被"试点采纳"而绕过底线。

本门禁在治理提案入口对提案文本做**底线语义预检**:
- 命中底线关键词 (删除/压缩/跳过审计留痕、明文凭据、降阈兜底、熔断不可审计等)
  → 直接 RED_FLAG, 不进入试点/折中流程。
- 与 destructive_gate 同模式: 匹配即打分, BLOCK / HITL_REQUIRED / ALLOW,
  决策可选 Ed25519 签名并落审计。

设计:
- ``BASELINE_PATTERNS``: 底线语义关键词表, 命中即高严重度。
- ``evaluate(text)``: 对提案正文打分并给出 verdict。
- fail-closed: 命中底线即 BLOCK, 不允许"试点采纳"路径。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BaselineVerdict(str, Enum):
    ALLOW = "ALLOW"
    HITL_REQUIRED = "HITL_REQUIRED"
    RED_FLAG = "RED_FLAG"


# 底线语义关键词: 命中即视为触碰治理红线 (对照 PoC 盲点 C 与 IPK 审计)
BASELINE_PATTERNS: dict[str, float] = {
    # 审计留痕不可破坏 (对应 34C / governance_audit.jsonl)
    "删除审计日志": 0.95,
    "压缩审计日志": 0.9,
    "跳过审计": 0.95,
    "清理审计": 0.9,
    "清空审计": 0.95,
    "删除 governance_audit": 0.95,
    "不再记录": 0.85,
    "不写审计": 0.9,
    # 凭证安全 (对应 第四-A条 / ipk 明文 cookie 事故)
    "明文保存": 0.95,
    "明文存储": 0.95,
    "cookie 明文": 0.95,
    "明文密码": 0.95,
    "输出 token": 0.85,
    "输出密钥": 0.85,
    # 质量门禁不可架空 (对应 IPK 审计 G4/G8)
    "降低阈值": 0.9,
    "下调阈值": 0.9,
    "下调": 0.7,
    "调低": 0.75,
    "移除兜底": 0.9,
    "移除上限": 0.85,
    "绕过门禁": 0.95,
    "放行 ai 味": 0.9,
    "跳过质量": 0.9,
    "放开阈值": 0.85,
    "放宽阈值": 0.85,
    # 熔断/兜底不可静默失效 (对应 PoC 盲点)
    "熔断不记录": 0.9,
    "失败计数清零": 0.85,
    "静默熔断": 0.9,
    "熔断日志不写": 0.9,
    # 折中/试点绕行 (PoC 盲点 C 直接命中)
    "试点运行": 0.7,
    "小范围测试": 0.7,
    "折中方案": 0.7,
    "先试点": 0.7,
    "暂不删除": 0.7,
    "暂时跳过": 0.8,
}

# 软信号: 命中不直接 RED_FLAG, 但提高严重度 (compromise 检测)
SOFT_PATTERNS: list[str] = [
    "效率", "简化", "排查方便", "节省", "减少干扰", "降低误报",
    "减少噪音", "提速", "降本",
]

# 组合规则: (审计相关词元, 破坏动词) → 即使未直接命中整词也 RED_FLAG
BASELINE_COMPOSITES: list[tuple[tuple[str, ...], tuple[str, ...], float]] = [
    (
        ("审计", "audit", "日志", "留痕", "governance_audit", "audit.jsonl"),
        ("删除", "压缩", "清理", "清空", "跳过", "去掉", "移除", "截断"),
        0.9,
    ),
    (
        ("阈值", "门禁", "门槛", "兜底", "quality", "gate"),
        ("降低", "下调", "调低", "放宽", "移除", "删除", "绕过", "跳过", "降"),
        0.85,
    ),
    (
        ("熔断", "circuit", "熔断器", "失败计数", "breaker"),
        ("不记录", "不写", "清零", "静默", "跳过", "忽略"),
        0.9,
    ),
    (
        ("凭据", "cookie", "密码", "token", "密钥", "credential"),
        ("明文", "输出", "打印", "落盘", "保存", "存储"),
        0.9,
    ),
]


@dataclass
class BaselineDecision:
    """单次底线预检决策, 含可验证证据."""

    decision_id: str = field(default_factory=lambda: f"baseline-{uuid.uuid4().hex[:12]}")
    proposal_text: str = ""
    verdict: BaselineVerdict = BaselineVerdict.ALLOW
    severity: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)
    reason: str = ""
    agent_id: str = ""
    timestamp: float = field(default_factory=time.time)
    signature: str = ""
    signer_fingerprint: str = ""

    def evidence_message(self) -> bytes:
        return json.dumps({
            "decision_id": self.decision_id,
            "verdict": self.verdict.value,
            "severity": self.severity,
            "matched": self.matched_patterns,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
        }, sort_keys=True, separators=(",", ":")).encode()

    def verify_evidence(self, public_key_pem: str) -> bool:
        if not self.signature or self.signature in ("unsigned", "sign_error"):
            return False
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        try:
            return Ed25519KeyPair.verify(
                public_key_pem,
                bytes.fromhex(self.signature),
                self.evidence_message(),
            )
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "verdict": self.verdict.value,
            "severity": self.severity,
            "matched_patterns": self.matched_patterns,
            "reason": self.reason,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "signer_fingerprint": self.signer_fingerprint,
        }


class GovernanceBaselineGate:
    """治理提案底线预检门禁 (fail-closed).

    - 命中底线关键词 (severity >= red_flag_above) → RED_FLAG 直接拦截。
    - 含软信号但未命中底线 (severity >= hitl_threshold) → HITL_REQUIRED。
    - 否则 ALLOW。
    """

    def __init__(
        self,
        enabled: bool = True,
        hitl_threshold: float = 0.5,
        red_flag_above: float = 0.85,
        signer: Any = None,
        audit_logger: Any = None,
    ) -> None:
        self._enabled = enabled
        self._hitl_threshold = hitl_threshold
        self._red_flag_above = red_flag_above
        self._signer = signer
        self._audit_logger = audit_logger
        self._decisions: list[BaselineDecision] = []

    def evaluate(self, proposal_text: str, agent_id: str = "") -> BaselineDecision:
        text_lower = proposal_text.lower()
        severity = 0.0
        matched: list[str] = []

        for pattern, sev in BASELINE_PATTERNS.items():
            if pattern.lower() in text_lower:
                matched.append(pattern)
                severity = max(severity, sev)

        # 组合规则: 审计/门禁/熔断/凭据 上下文 + 破坏动词
        for domain_words, action_words, sev in BASELINE_COMPOSITES:
            if any(w in text_lower for w in domain_words) and any(
                a in text_lower for a in action_words
            ):
                matched.append(f"composite:{domain_words[0]}+{action_words[0]}")
                severity = max(severity, sev)

        # 软信号: 仅在已有命中信号基础上少量加成, 不单独触发 (防误伤良性提案)
        soft_hits = [s for s in SOFT_PATTERNS if s in text_lower]
        if soft_hits and severity > 0.0 and severity < self._red_flag_above:
            severity = max(severity, 0.6)

        verdict = BaselineVerdict.ALLOW
        reason = "Proposal passes baseline gate"

        if not self._enabled:
            verdict = BaselineVerdict.ALLOW
            reason = "Baseline gate is disabled"
        elif severity >= self._red_flag_above:
            verdict = BaselineVerdict.RED_FLAG
            reason = (
                f"Baseline red-line detected: {', '.join(matched[:3])} "
                f"(severity={severity:.2f}); 折中/试点路径禁止"
            )
        elif severity >= self._hitl_threshold:
            verdict = BaselineVerdict.HITL_REQUIRED
            reason = f"Baseline soft-signal, human review required (severity={severity:.2f})"

        decision = BaselineDecision(
            proposal_text=proposal_text[:500],
            verdict=verdict,
            severity=round(severity, 3),
            matched_patterns=matched,
            reason=reason,
            agent_id=agent_id,
        )

        if self._signer is not None:
            try:
                sig = self._signer.sign(decision.evidence_message())
                decision.signature = sig.hex()
                decision.signer_fingerprint = self._signer.fingerprint
            except Exception:
                decision.signature = "sign_error"
        else:
            decision.signature = "unsigned"

        self._decisions.append(decision)
        self._log_audit(decision)
        return decision

    def confirm_hitl(self, decision: BaselineDecision, approved: bool, approver_id: str = "") -> BaselineDecision:
        if decision.verdict != BaselineVerdict.HITL_REQUIRED:
            return decision
        decision.verdict = (
            BaselineVerdict.ALLOW if approved else BaselineVerdict.RED_FLAG
        )
        decision.reason = (
            f"Human {approver_id} approved baseline review"
            if approved
            else f"Human {approver_id} denied (RED_FLAG)"
        )
        decision.timestamp = time.time()
        if self._signer is not None:
            try:
                sig = self._signer.sign(decision.evidence_message())
                decision.signature = sig.hex()
            except Exception:
                decision.signature = "sign_error"
        self._log_audit(decision)
        return decision

    def _log_audit(self, decision: BaselineDecision) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log(
                event_type="baseline_gate.evaluate",
                actor=f"baseline-gate:{decision.agent_id}",
                detail=decision.to_dict(),
            )
        except Exception:
            pass

    def recent_decisions(self, count: int = 10, verdict: BaselineVerdict | None = None) -> list[BaselineDecision]:
        filtered = self._decisions
        if verdict is not None:
            filtered = [d for d in filtered if d.verdict == verdict]
        return filtered[-count:]

    def summary(self) -> dict[str, Any]:
        total = len(self._decisions)
        red = sum(1 for d in self._decisions if d.verdict == BaselineVerdict.RED_FLAG)
        hitl = sum(1 for d in self._decisions if d.verdict == BaselineVerdict.HITL_REQUIRED)
        allowed = sum(1 for d in self._decisions if d.verdict == BaselineVerdict.ALLOW)
        return {
            "enabled": self._enabled,
            "hitl_threshold": self._hitl_threshold,
            "red_flag_above": self._red_flag_above,
            "total_decisions": total,
            "red_flag": red,
            "hitl_required": hitl,
            "allowed": allowed,
            "signer_configured": self._signer is not None,
        }


__all__ = [
    "BASELINE_PATTERNS",
    "SOFT_PATTERNS",
    "BaselineDecision",
    "BaselineVerdict",
    "GovernanceBaselineGate",
]
