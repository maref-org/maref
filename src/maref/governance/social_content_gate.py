"""Social/content publishing risk gate (P3-C).

Reviews platform-bound content before publication: length limits, prohibited
claims, AI-content disclosure, PII leakage, media types, and provenance/license.
The gate returns ``allow`` / ``review`` / ``block`` with actionable reasons.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from maref.governance.content_provenance import ProvenanceLedger

_BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"包治百病|药到病除|治愈癌症|cure cancer", "prohibited medical claim"),
    (r"稳赚不赔|保证收益|零风险高回报|guaranteed returns", "prohibited financial guarantee"),
    (r"内幕消息|老鼠仓|洗钱|刷单|出售银行卡|出售身份证", "prohibited illegal/fraudulent content"),
    (r"代办证件|伪造发票|假证件", "prohibited forged-document content"),
)

_REVIEW_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"国家级|世界第一|全网最低|绝对|永久|100%", "absolute-claim review"),
    (r"投资建议|荐股|处方|诊疗方案", "regulated-advice review"),
)

_PII_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "phone"),
    (r"(?<!\d)\d{17}[\dXx](?!\d)", "national_id"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email"),
    (r"(?<!\d)\d{16,19}(?!\d)", "bank_card"),
)

_ALLOWED_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime"}
)


@dataclass(frozen=True)
class PlatformPolicy:
    name: str
    max_chars: int
    min_chars: int = 1
    requires_ai_disclosure: bool = True
    allowed_media: frozenset[str] = _ALLOWED_MEDIA_TYPES


PLATFORM_POLICIES: dict[str, PlatformPolicy] = {
    "xiaohongshu": PlatformPolicy("xiaohongshu", max_chars=1000, requires_ai_disclosure=True),
    "douyin": PlatformPolicy("douyin", max_chars=2200, requires_ai_disclosure=True),
    "bilibili": PlatformPolicy("bilibili", max_chars=2000, requires_ai_disclosure=True),
    "wechat": PlatformPolicy("wechat", max_chars=20000, requires_ai_disclosure=True),
    "linkedin": PlatformPolicy("linkedin", max_chars=3000, requires_ai_disclosure=True),
    "x": PlatformPolicy("x", max_chars=280, min_chars=1, requires_ai_disclosure=True),
}


@dataclass
class SocialContentRequest:
    platform: str
    text: str
    media_types: list[str] = field(default_factory=list)
    ai_generated: bool = False
    disclosure: str = ""
    provenance_asset_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SocialContentDecision:
    verdict: str
    allowed: bool
    risk_score: float
    reasons: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    redacted_text: str = ""
    evidence_id: str = ""
    hitl_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "allowed": self.allowed,
            "risk_score": self.risk_score,
            "reasons": list(self.reasons),
            "required_actions": list(self.required_actions),
            "redacted_text": self.redacted_text,
            "evidence_id": self.evidence_id,
            "hitl_event_id": self.hitl_event_id,
        }


class SocialContentGate:
    """Platform-aware content risk gate with evidence-backed provenance."""

    def __init__(
        self,
        *,
        platforms: dict[str, PlatformPolicy] | None = None,
        provenance: ProvenanceLedger | None = None,
        require_provenance: bool = False,
        allowed_licenses: Iterable[str] | None = None,
    ) -> None:
        self.platforms = platforms or PLATFORM_POLICIES
        self.provenance = provenance
        self.require_provenance = require_provenance
        self.allowed_licenses = (
            frozenset(allowed_licenses) if allowed_licenses is not None else None
        )

    def review(self, request: SocialContentRequest) -> SocialContentDecision:
        policy = self.platforms.get(request.platform)
        if policy is None:
            return SocialContentDecision(
                verdict="block",
                allowed=False,
                risk_score=1.0,
                reasons=[f"unknown platform '{request.platform}'"],
                required_actions=["choose_supported_platform"],
            )

        text = request.text or ""
        reasons: list[str] = []
        actions: list[str] = []
        blocking = False
        risk = 0.0

        length = len(text)
        if length < policy.min_chars:
            reasons.append(f"text too short ({length} < {policy.min_chars})")
            actions.append("add_content")
            blocking = True
            risk += 0.5
        if length > policy.max_chars:
            reasons.append(f"text too long ({length} > {policy.max_chars})")
            actions.append("shorten_content")
            blocking = True
            risk += 0.5

        for pattern, reason in _BLOCK_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                reasons.append(reason)
                actions.append("remove_prohibited_claim")
                blocking = True
                risk += 0.4

        for pattern, reason in _REVIEW_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                reasons.append(reason)
                actions.append("human_review_required")
                risk += 0.2

        redacted = text
        pii_hits: list[str] = []
        for pattern, label in _PII_PATTERNS:
            if re.search(pattern, text):
                pii_hits.append(label)
                redacted = re.sub(pattern, f"[REDACTED:{label}]", redacted)
        if pii_hits:
            reasons.append(f"PII detected: {', '.join(sorted(set(pii_hits)))}")
            actions.append("remove_or_redact_pii")
            blocking = True
            risk += 0.5

        if policy.requires_ai_disclosure and request.ai_generated:
            disclosure = request.disclosure.strip()
            if not disclosure or disclosure not in text:
                reasons.append("AI-generated content requires an in-text disclosure")
                actions.append("add_ai_disclosure")
                risk += 0.2

        if request.media_types:
            unsupported = [
                media
                for media in request.media_types
                if media not in policy.allowed_media
            ]
            if unsupported:
                reasons.append(f"unsupported media types: {', '.join(sorted(set(unsupported)))}")
                actions.append("convert_media_type")
                blocking = True
                risk += 0.3

        if self.provenance is not None and request.provenance_asset_id:
            decision = self.provenance.check_publishable(
                request.provenance_asset_id,
                allowed_licenses=self.allowed_licenses,
            )
            if not decision.allowed:
                reasons.append(f"provenance check failed: {decision.reason}")
                actions.append("fix_provenance_or_license")
                blocking = True
                risk += 0.4
        elif self.require_provenance:
            reasons.append("provenance asset is required for publishing")
            actions.append("register_provenance")
            risk += 0.2

        if blocking:
            verdict = "block"
        elif reasons:
            verdict = "review"
        else:
            verdict = "allow"
        return SocialContentDecision(
            verdict=verdict,
            allowed=verdict == "allow",
            risk_score=round(min(risk, 1.0), 3),
            reasons=reasons,
            required_actions=actions,
            redacted_text=redacted,
        )
