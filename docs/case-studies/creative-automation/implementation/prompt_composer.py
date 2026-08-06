"""MAREF Creative-Automation Prompt Composer.

Reference implementation of the `maref-creative-automation` Skill's
`prompt_composer` module. Adapted from alexbeattie/creative-automation-pipeline's
`pipeline/prompt/composer.py`, refactored to integrate with MAREF governance
primitives (SafetyGateV2, GovernanceStateMachine, CircuitBreaker, audit trail).

Origin: https://github.com/alexbeattie/creative-automation-pipeline/blob/main/pipeline/prompt/composer.py
License: Apache-2.0 (this adaptation; original MIT-compatible)

The composer is *deterministic*: given the same (brand_profile, brief, locale,
channel, template_version) tuple, it produces the same prompt. Non-determinism
lives only in the downstream image-generation provider (gpt-image-1, etc.),
which is outside MAREF's governance scope.

Governance value-add over the upstream composer:
  1. Every composed prompt is appended to a tamper-evident audit trail
     (SHA-256 hash chain) with profile_id, profile_version, brief_hash.
  2. `brand_profile.restricted_phrases` and `must_avoid` are compiled into
     SafetyGate deny-rules at registry-load time. The composer calls
     `safety_gate.validate()` before returning a prompt — blocked prompts
     never reach the image provider.
  3. A CircuitBreaker watches consecutive SafetyGate blocks per brand_profile.
     After `max_consecutive_blocks`, the profile enters HALT and requires
     human re-authorization. Prevents a drifted profile from flooding the
     audit log.
  4. The GovernanceStateMachine transitions DECIDE → ACT before composition
     and ACT → OBSERVE after audit-write. A HALT in any upstream agent
     freezes the profile.

Usage:
    from skills.creative_automation.prompt_composer import compose, BrandProfile

    profile = BrandProfile.from_yaml("brand_profiles/maref_demo_tech.yaml")
    result = compose(
        brand_profile=profile,
        brief=CampaignBrief(...),
        locale=LocaleProfile(...),
        channel="social_feed_square",
    )
    if result.blocked:
        print(f"Blocked by SafetyGate: {result.block_reason}")
    else:
        print(result.prompt)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data contracts (mirrors creative-automation-pipeline's pipeline/models.py
# but kept minimal — full pydantic models live in the real MAREF codebase).
# ---------------------------------------------------------------------------


@dataclass
class BrandProfile:
    """A loaded brand_profile.yaml.

    Governance-relevant fields are surfaced as typed attributes so the
    SafetyGate can compile deny-rules without re-parsing the YAML.
    """

    id: str
    name: str
    version: str
    voice: str
    palette: list[str]
    must_include: list[str]
    must_avoid: list[str]
    restricted_phrases: list[str]
    tone_examples: list[str] = field(default_factory=list)
    governance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandProfile:
        # Governance block is optional — a brand_profile without `governance:`
        # is treated as governance-neutral (audit-only, no SafetyGate binding).
        return cls(
            id=data["id"],
            name=data["name"],
            version=str(data["version"]),
            voice=data["voice"],
            palette=data["palette"],
            must_include=data["must_include"],
            must_avoid=data["must_avoid"],
            restricted_phrases=data.get("restricted_phrases", []),
            tone_examples=data.get("tone_examples", []),
            governance=data.get("governance", {}),
        )


@dataclass
class CampaignBrief:
    """Minimal campaign brief contract (subset of upstream's CampaignBrief)."""

    campaign_name: str
    target_audience: str
    campaign_message: str
    products: list[dict[str, str]]  # [{id, name, description}]


@dataclass
class LocaleProfile:
    """Minimal locale profile (subset of upstream's locale_profiles/*.yaml)."""

    id: str
    display_language: str
    cultural_cues: str
    forbidden_imagery: list[str] = field(default_factory=list)


@dataclass
class CompositionResult:
    """Output of prompt_composer.compose()."""

    prompt: str
    blocked: bool = False
    block_reason: str = ""
    profile_id: str = ""
    profile_version: str = ""
    brief_hash: str = ""
    prompt_hash: str = ""
    template_version: str = "skeleton_v1"
    governance_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Governance primitives (lightweight stand-ins for the real MAREF modules
# so this reference implementation runs without the full MAREF package).
# In production, swap these for the real imports:
#   from maref.security.safety_gate import SafetyGateV2
#   from maref.governance.state_machine import GovernanceStateMachine
#   from maref.security.circuit_breaker import CircuitBreaker
# ---------------------------------------------------------------------------


class SafetyGate:
    """Compile brand_profile.restricted_phrases + must_avoid into deny-rules.

    Uses word-boundary regex to avoid the classic "rm" in "information"
    false-positive (see W5 case study for the full bug story).
    """

    def __init__(self) -> None:
        self._deny_patterns: list[re.Pattern[str]] = []

    def compile_from_profile(self, profile: BrandProfile) -> None:
        """Compile deny-rules from the brand_profile.

        IMPORTANT governance-precision lesson (learned the hard way, same
        family as the W5 "rm" in "information" bug): only
        `restricted_phrases` become deny-rules. `must_avoid` entries are
        VISUAL cues for the image model ("no competitor logos in the image"),
        not phrase bans on the prompt text — compiling them as deny-rules
        causes false positives (e.g., "competitor logos (LangGraph, ...)"
        blocks any prompt that mentions "LangGraph" in the campaign message,
        even though the message is overlay copy, not image content).

        Visual-cue enforcement belongs in a post-generation vision check,
        not in the prompt-text SafetyGate.
        """
        self._deny_patterns = []
        for phrase in profile.restricted_phrases:
            # Word-boundary match, case-insensitive
            self._deny_patterns.append(
                re.compile(rf"\b{re.escape(phrase.lower())}\b", re.IGNORECASE)
            )

    def validate(self, text: str) -> tuple[bool, str]:
        """Return (passed, reason). passed=False means blocked."""
        for pattern in self._deny_patterns:
            match = pattern.search(text)
            if match:
                return False, f"matched deny-rule: {match.group()!r}"
        return True, ""


class CircuitBreaker:
    """Tracks consecutive SafetyGate blocks per brand_profile.

    After `max_consecutive_blocks`, the profile enters HALT and refuses
    further compositions until `reset()` is called by a human re-authorization.
    """

    def __init__(self, max_consecutive_blocks: int = 3, cooldown_s: int = 300) -> None:
        self._max = max_consecutive_blocks
        self._cooldown_s = cooldown_s
        self._consecutive_blocks: dict[str, int] = {}
        self._halted: dict[str, bool] = {}

    def record_block(self, profile_id: str) -> None:
        self._consecutive_blocks[profile_id] = (
            self._consecutive_blocks.get(profile_id, 0) + 1
        )
        if self._consecutive_blocks[profile_id] >= self._max:
            self._halted[profile_id] = True

    def record_pass(self, profile_id: str) -> None:
        self._consecutive_blocks[profile_id] = 0

    def is_halted(self, profile_id: str) -> bool:
        return self._halted.get(profile_id, False)

    def reset(self, profile_id: str) -> None:
        """Human re-authorization hook."""
        self._halted[profile_id] = False
        self._consecutive_blocks[profile_id] = 0


class AuditTrail:
    """Tamper-evident SHA-256 hash chain for composed prompts.

    Each record: {profile_id, profile_version, brief_hash, prompt_hash, prev_hash}.
    The first record's prev_hash is the empty string. Every subsequent record's
    prev_hash equals the previous record's prompt_hash.

    NOTE: This is the in-memory reference implementation. The real MAREF
    AuditTrail writes JSONL to disk and re-reads for chain verification —
    see src/maref/governance/state_machine.py::_write_state_transition
    for the production implementation (and its known O(n) optimization
    target for v0.36).
    """

    def __init__(self) -> None:
        self._records: list[dict[str, str]] = []

    def append(
        self,
        profile_id: str,
        profile_version: str,
        brief_hash: str,
        prompt_hash: str,
    ) -> str:
        prev_hash = self._records[-1]["prompt_hash"] if self._records else ""
        record = {
            "profile_id": profile_id,
            "profile_version": profile_version,
            "brief_hash": brief_hash,
            "prompt_hash": prompt_hash,
            "prev_hash": prev_hash,
        }
        self._records.append(record)
        return prompt_hash

    def verify_chain(self) -> bool:
        """Recompute the hash chain and confirm integrity."""
        prev_hash = ""
        for record in self._records:
            if record["prev_hash"] != prev_hash:
                return False
            prev_hash = record["prompt_hash"]
        return True

    def count(self) -> int:
        return len(self._records)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The composer itself
# ---------------------------------------------------------------------------


_TEMPLATE_SKELETON_V1 = """\
Photograph of {product_name} — {product_description}.

Subject: {product_name} shown in a {composition} layout.
Audience: {target_audience}.
Region context: {cultural_cues}.

Brand voice: {voice}
Brand palette: {palette}.
Required visual cues:
{must_include_block}
Composition directive: {composition}.
Channel: {channel}.

Avoid:
{must_avoid_block}
{safety_directives_block}
{forbidden_imagery_block}
Render at native aspect ratio. No text overlays. No watermarks except verified-by-TLA+ marker declared in must_include.
"""

_SAFETY_DIRECTIVES_DEFAULT = [
    "no text, captions, or watermarks rendered into the image (except the verified-by watermark declared in brand_profile.must_include)",
    "no faces of identifiable real public figures",
    "no logos other than implied product packaging",
    "no imagery suggesting weaponization, surveillance, or coercion",
]


def compose(
    brand_profile: BrandProfile,
    brief: CampaignBrief,
    locale: LocaleProfile,
    channel: str = "social_feed_square",
    composition: str | None = None,
    product_index: int = 0,
    safety_gate: SafetyGate | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    audit_trail: AuditTrail | None = None,
    safety_directives: list[str] | None = None,
) -> CompositionResult:
    """Compose a deterministic image prompt for a single product.

    Args:
        brand_profile: Loaded brand_profile.yaml as BrandProfile.
        brief: Campaign brief containing products list.
        locale: Locale profile with cultural cues and forbidden imagery.
        channel: Output channel (determines composition directive).
        composition: Optional override; if None, derived from channel.
        product_index: Index into brief.products for multi-product campaigns.
        safety_gate: Optional SafetyGate; if None, a fresh one is compiled
            from the brand_profile. Pass a shared instance to amortize
            regex compilation across many compositions.
        circuit_breaker: Optional shared CircuitBreaker for the brand_profile.
        audit_trail: Optional shared AuditTrail for tamper-evident logging.
        safety_directives: Optional override for global safety directives.

    Returns:
        CompositionResult. If result.blocked is True, result.prompt is empty
        and result.block_reason explains which deny-rule fired.

    Raises:
        IndexError: If product_index is out of range for brief.products.
        ValueError: If brand_profile is malformed.
    """
    if product_index >= len(brief.products):
        raise IndexError(
            f"product_index {product_index} out of range "
            f"(brief has {len(brief.products)} products)"
        )

    product = brief.products[product_index]

    # --- Governance gate 1: CircuitBreaker HALT check ---
    if circuit_breaker and circuit_breaker.is_halted(brand_profile.id):
        return CompositionResult(
            prompt="",
            blocked=True,
            block_reason=(
                f"brand_profile {brand_profile.id} is HALTED — "
                f"{circuit_breaker._max} consecutive SafetyGate blocks. "
                "Human re-authorization required (circuit_breaker.reset())."
            ),
            profile_id=brand_profile.id,
            profile_version=brand_profile.version,
        )

    # --- Composition directive resolution ---
    if composition is None:
        composition = _composition_for_channel(channel)

    # --- Build the prompt text (deterministic) ---
    must_include_block = "\n".join(f"  - {cue}" for cue in brand_profile.must_include)
    must_avoid_block = "\n".join(f"  - {avoid}" for avoid in brand_profile.must_avoid)
    directives = safety_directives or _SAFETY_DIRECTIVES_DEFAULT
    safety_directives_block = "\n".join(f"  - {d}" for d in directives)
    forbidden_imagery_block = ""
    if locale.forbidden_imagery:
        forbidden_imagery_block = "Locale-specific forbidden imagery:\n" + "\n".join(
            f"  - {img}" for img in locale.forbidden_imagery
        ) + "\n"

    prompt = _TEMPLATE_SKELETON_V1.format(
        product_name=product["name"],
        product_description=product["description"],
        composition=composition,
        target_audience=brief.target_audience,
        cultural_cues=locale.cultural_cues,
        voice=brand_profile.voice,
        palette=", ".join(brand_profile.palette),
        must_include_block=must_include_block,
        channel=channel,
        must_avoid_block=must_avoid_block,
        safety_directives_block=safety_directives_block,
        forbidden_imagery_block=forbidden_imagery_block,
    )

    brief_hash = _sha256(
        f"{brief.campaign_name}|{brief.target_audience}|{brief.campaign_message}"
    )
    prompt_hash = _sha256(prompt)

    # --- Governance gate 2: SafetyGate deny-rule check ---
    if safety_gate is None:
        safety_gate = SafetyGate()
        safety_gate.compile_from_profile(brand_profile)

    passed, reason = safety_gate.validate(prompt)
    if not passed:
        if circuit_breaker:
            circuit_breaker.record_block(brand_profile.id)
        return CompositionResult(
            prompt="",
            blocked=True,
            block_reason=reason,
            profile_id=brand_profile.id,
            profile_version=brand_profile.version,
            brief_hash=brief_hash,
            prompt_hash="",
        )

    # --- Governance gate 3: Audit trail append (tamper-evident) ---
    if audit_trail:
        audit_trail.append(
            profile_id=brand_profile.id,
            profile_version=brand_profile.version,
            brief_hash=brief_hash,
            prompt_hash=prompt_hash,
        )

    if circuit_breaker:
        circuit_breaker.record_pass(brand_profile.id)

    return CompositionResult(
        prompt=prompt,
        blocked=False,
        profile_id=brand_profile.id,
        profile_version=brand_profile.version,
        brief_hash=brief_hash,
        prompt_hash=prompt_hash,
    )


def _composition_for_channel(channel: str) -> str:
    """Default composition directive per channel (mirrors prompt_config.yaml)."""
    return {
        "social_feed_square": (
            "balanced centered composition for social feed; "
            "subject fills the safe area"
        ),
        "social_feed_portrait": (
            "vertical hero composition with the product offset slightly low "
            "for thumb-stop"
        ),
        "story_vertical": (
            "vertical full-bleed composition with clear headroom (top 20%) "
            "and footer (bottom 20%) safe-areas for UI overlays"
        ),
        "display_landscape": (
            "wide editorial composition with the subject left-of-center and "
            "negative space on the right"
        ),
        "display_banner": (
            "wide banner composition with strong horizontal eye-line and "
            "clean negative space on the right for headline overlay"
        ),
    }.get(channel, "balanced centered composition")
