"""Demo: MAREF Creative-Automation Skill in action.

Runs 4 scenarios against the prompt_composer to demonstrate governance
value-add over the upstream creative-automation-pipeline:

  1. Benign brief — prompt composes successfully, audit trail grows.
  2. Restricted phrase — SafetyGate blocks 'revolutionary' before reaching
     the image provider.
  3. CircuitBreaker HALT — 3 consecutive blocks freeze the brand_profile.
  4. Audit trail verification — tamper-evident hash chain stays intact.

No LLM API key required. No image generation. Pure governance behavior.

Run:
    python3 docs/case-studies/creative-automation/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the implementation importable when run from anywhere.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "implementation"))

import yaml  # noqa: E402, I001

from prompt_composer import (  # noqa: E402
    AuditTrail,
    BrandProfile,
    CampaignBrief,
    CircuitBreaker,
    LocaleProfile,
    SafetyGate,
    compose,
)


def _load_profile() -> BrandProfile:
    with open(_HERE / "brand_profile.yaml") as f:
        return BrandProfile.from_dict(yaml.safe_load(f))


def _benign_brief() -> CampaignBrief:
    return CampaignBrief(
        campaign_name="MAREF v0.36 Launch",
        target_audience="platform architects deploying agents in production",
        campaign_message="Build with LangGraph. Govern with MAREF.",
        products=[
            {
                "id": "maref-cli",
                "name": "MAREF CLI",
                "description": "Command-line interface for agent governance.",
            }
        ],
    )


def _hype_brief() -> CampaignBrief:
    """Brief full of restricted phrases — should be blocked."""
    return CampaignBrief(
        campaign_name="Hype Test",
        target_audience="easily impressed buyers",
        campaign_message="revolutionary agent governance",
        products=[
            {
                "id": "hype-product",
                "name": "Revolutionary MAREF",
                "description": "revolutionary game-changing world-class agent governance",
            }
        ],
    )


def _locale() -> LocaleProfile:
    return LocaleProfile(
        id="en-US",
        display_language="en",
        cultural_cues="San Francisco developer culture; engineering credibility over hype",
        forbidden_imagery=[],
    )


def scenario_1_benign() -> None:
    print("=" * 70)
    print("SCENARIO 1: Benign brief — should compose successfully")
    print("=" * 70)
    profile = _load_profile()
    gate = SafetyGate()
    gate.compile_from_profile(profile)
    breaker = CircuitBreaker(
        max_consecutive_blocks=profile.governance.get("circuit_breaker", {}).get(
            "max_consecutive_blocks", 3
        )
    )
    trail = AuditTrail()

    result = compose(
        brand_profile=profile,
        brief=_benign_brief(),
        locale=_locale(),
        channel="social_feed_square",
        safety_gate=gate,
        circuit_breaker=breaker,
        audit_trail=trail,
    )
    print(f"blocked:           {result.blocked}")
    print(f"profile_id:        {result.profile_id}")
    print(f"profile_version:   {result.profile_version}")
    print(f"brief_hash:        {result.brief_hash[:16]}...")
    print(f"prompt_hash:       {result.prompt_hash[:16]}...")
    print(f"template_version:  {result.template_version}")
    print(f"audit_trail_count: {trail.count()}")
    print("--- prompt (first 200 chars) ---")
    print(result.prompt[:200] + "...")
    print()


def scenario_2_restricted_phrase_blocked() -> None:
    print("=" * 70)
    print("SCENARIO 2: Restricted phrase 'revolutionary' — should be blocked")
    print("=" * 70)
    profile = _load_profile()
    gate = SafetyGate()
    gate.compile_from_profile(profile)
    breaker = CircuitBreaker()
    trail = AuditTrail()

    result = compose(
        brand_profile=profile,
        brief=_hype_brief(),
        locale=_locale(),
        channel="social_feed_square",
        safety_gate=gate,
        circuit_breaker=breaker,
        audit_trail=trail,
    )
    print(f"blocked:         {result.blocked}")
    print(f"block_reason:    {result.block_reason}")
    print(f"prompt (empty?): {result.prompt == ''}")
    print(f"audit_trail_count (should be 0 — blocked prompts aren't audited): {trail.count()}")
    print()


def scenario_3_circuit_breaker_halt() -> None:
    print("=" * 70)
    print("SCENARIO 3: 3 consecutive blocks — CircuitBreaker should HALT")
    print("=" * 70)
    profile = _load_profile()
    gate = SafetyGate()
    gate.compile_from_profile(profile)
    breaker = CircuitBreaker(max_consecutive_blocks=3)
    trail = AuditTrail()

    print(f"max_consecutive_blocks: {breaker._max}")
    for i in range(1, 5):
        result = compose(
            brand_profile=profile,
            brief=_hype_brief(),
            locale=_locale(),
            channel="social_feed_square",
            safety_gate=gate,
            circuit_breaker=breaker,
            audit_trail=trail,
        )
        is_halted = breaker.is_halted(profile.id)
        print(
            f"attempt {i}: blocked={result.blocked}, "
            f"reason={result.block_reason[:50] if result.blocked else 'n/a'}, "
            f"profile_halted={is_halted}"
        )

    print()
    print("After HALT, even a benign brief is refused until human re-authorization:")
    benign_result = compose(
        brand_profile=profile,
        brief=_benign_brief(),
        locale=_locale(),
        channel="social_feed_square",
        safety_gate=gate,
        circuit_breaker=breaker,
        audit_trail=trail,
    )
    print(f"  benign attempt after HALT: blocked={benign_result.blocked}")
    print(f"  block_reason: {benign_result.block_reason}")
    print()

    print("Human re-authorizes (circuit_breaker.reset()):")
    breaker.reset(profile.id)
    print(f"  profile_halted now: {breaker.is_halted(profile.id)}")
    benign_result2 = compose(
        brand_profile=profile,
        brief=_benign_brief(),
        locale=_locale(),
        channel="social_feed_square",
        safety_gate=gate,
        circuit_breaker=breaker,
        audit_trail=trail,
    )
    print(f"  benign attempt after reset: blocked={benign_result2.blocked}")
    print()


def scenario_4_audit_trail_integrity() -> None:
    print("=" * 70)
    print("SCENARIO 4: Audit trail tamper-evidence (SHA-256 hash chain)")
    print("=" * 70)
    profile = _load_profile()
    gate = SafetyGate()
    gate.compile_from_profile(profile)
    breaker = CircuitBreaker()
    trail = AuditTrail()

    # Compose 3 benign prompts for different channels.
    for channel in ["social_feed_square", "story_vertical", "display_banner"]:
        compose(
            brand_profile=profile,
            brief=_benign_brief(),
            locale=_locale(),
            channel=channel,
            safety_gate=gate,
            circuit_breaker=breaker,
            audit_trail=trail,
        )

    print(f"records appended: {trail.count()}")
    print(f"chain verifies:   {trail.verify_chain()}")
    print()

    print("Tamper test — manually corrupt the middle record's prompt_hash:")
    original = trail._records[1]["prompt_hash"]
    trail._records[1]["prompt_hash"] = "tampered"
    print(f"  chain verifies after tamper: {trail.verify_chain()}  (should be False)")
    trail._records[1]["prompt_hash"] = original
    print(f"  chain verifies after restore: {trail.verify_chain()}  (should be True)")
    print()


def main() -> None:
    print("MAREF Creative-Automation Skill — Governance Demo")
    print(f"brand_profile: {_HERE / 'brand_profile.yaml'}")
    print()
    scenario_1_benign()
    scenario_2_restricted_phrase_blocked()
    scenario_3_circuit_breaker_halt()
    scenario_4_audit_trail_integrity()
    print("=" * 70)
    print("All 4 scenarios complete. Governance value-add demonstrated:")
    print("  - SafetyGate blocks restricted phrases before they reach the provider")
    print("  - CircuitBreaker HALTs a drifted brand_profile after 3 blocks")
    print("  - Audit trail is tamper-evident (SHA-256 hash chain)")
    print("  - Profile version is pinned into every audit record for reproducibility")
    print("=" * 70)


if __name__ == "__main__":
    main()
