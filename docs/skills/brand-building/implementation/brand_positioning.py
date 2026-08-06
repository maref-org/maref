"""Reference implementation of the maref-brand-positioning Skill.

This module demonstrates how a MAREF Skill is implemented to pass the
three-gate admission (static scan → sandbox test → manual review).

It is placed under docs/skills/brand-building/implementation/ as a reference,
NOT under src/maref/skills/ — the latter is reserved for core framework skills
that go through the full release process.

Usage:
    from skills.brand_building.brand_positioning import generate

    result = generate(
        brand_id="maref",
        competitive_alternatives="use LangGraph/CrewAI/AutoGen without governance",
        unique_attributes=["TLA+ formal verification", "10-state Gray Code FSM"],
        market_category="agent governance and skill marketplace operating system",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PositioningResult:
    """Output of the brand-positioning skill."""

    positioning_statement: str
    one_liner: str
    elevator_pitch: str
    differentiators: list[dict[str, str]] = field(default_factory=list)
    support_points: list[str] = field(default_factory=list)
    consistency_score: float = 0.0
    warnings: list[str] = field(default_factory=list)


def generate(
    brand_id: str,
    competitive_alternatives: str,
    unique_attributes: list[str],
    market_category: str,
    value_proof: list[dict[str, str]] | None = None,
    character: str = "",
    target_audience: str = "",
) -> PositioningResult:
    """Generate a brand positioning statement using April Dunford's 5+1 framework.

    Args:
        brand_id: Brand identifier (e.g., "maref").
        competitive_alternatives: What customers would do without the product.
        unique_attributes: Attributes only the product has.
        market_category: Market frame (e.g., "agent governance OS").
        value_proof: Optional list of {attribute, value} dicts.
        character: Optional brand character (e.g., "the safety engineer").
        target_audience: Optional target audience description.

    Returns:
        PositioningResult with positioning statement, one-liner, and differentiators.

    Raises:
        ValueError: If required inputs are missing or inconsistent.
    """
    # --- Input validation (gate 1: static scan checks) ---
    if not brand_id or not isinstance(brand_id, str):
        raise ValueError("brand_id must be a non-empty string")
    if not competitive_alternatives or not isinstance(competitive_alternatives, str):
        raise ValueError("competitive_alternatives must be a non-empty string")
    if not unique_attributes or not isinstance(unique_attributes, list):
        raise ValueError("unique_attributes must be a non-empty list")
    if not market_category or not isinstance(market_category, str):
        raise ValueError("market_category must be a non-empty string")
    if len(unique_attributes) < 1:
        raise ValueError("at least one unique attribute is required")

    value_proof = value_proof or []
    warnings: list[str] = []

    # --- Consistency checks (gate 1: static scan checks) ---
    consistency_score = 100.0

    # Check: market_category should not contain hype words
    hype_words = ["revolutionary", "game-changing", "world-class", "best-in-class"]
    for word in hype_words:
        if word.lower() in market_category.lower():
            warnings.append(f"market_category contains hype word '{word}'")
            consistency_score -= 10

    # Check: unique_attributes should be specific (length > 3 words)
    for attr in unique_attributes:
        if len(attr.split()) < 3:
            warnings.append(
                f"unique_attribute '{attr}' is too vague (fewer than 3 words)"
            )
            consistency_score -= 5

    # Check: value_proof should map to unique_attributes
    proven_attrs = {vp.get("attribute", "") for vp in value_proof}
    for attr in unique_attributes:
        if attr not in proven_attrs:
            warnings.append(f"unique_attribute '{attr}' has no value_proof")

    # --- Generate positioning statement (April Dunford template) ---
    # Template: For [target_audience] who [need], [brand_id] is a [market_category]
    # that [unique_value]. Unlike [competitive_alternatives], [brand_id] [differentiation].
    audience_clause = (
        f"For {target_audience} who need safe, governed agent operations,"
        if target_audience
        else "For teams deploying AI agents in production,"
    )

    value_clause = ""
    if value_proof:
        first_proof = value_proof[0]
        value_clause = f" that delivers {first_proof.get('value', 'measurable safety')}"

    differentiation_clause = ""
    if unique_attributes:
        top_attr = unique_attributes[0]
        differentiation_clause = f" {brand_id} provides {top_attr}"

    positioning_statement = (
        f"{audience_clause} {brand_id} is a {market_category}{value_clause}. "
        f"Unlike {competitive_alternatives}, {differentiation_clause}."
    ).strip()

    # --- Generate one-liner (for README/tagline) ---
    one_liner = f"{brand_id} is the {market_category}."

    # --- Generate elevator pitch (30 seconds) ---
    pitch_parts = [
        f"{brand_id} is the {market_category}.",
    ]
    if unique_attributes:
        pitch_parts.append(f"It is the only solution with {unique_attributes[0]}.")
    if competitive_alternatives:
        pitch_parts.append(
            f"While others {competitive_alternatives}, {brand_id} ensures "
            f"production-grade safety from day one."
        )
    elevator_pitch = " ".join(pitch_parts)

    # --- Build differentiators ---
    differentiators = []
    for i, attr in enumerate(unique_attributes[:5]):  # top 5
        proof = ""
        competitor_gap = ""
        for vp in value_proof:
            if vp.get("attribute") == attr:
                proof = vp.get("value", "")
                break
        differentiators.append(
            {
                "attribute": attr,
                "proof": proof,
                "competitor_gap": competitor_gap,
            }
        )

    # --- Build support points ---
    support_points = []
    for attr in unique_attributes:
        support_points.append(f"{brand_id} provides {attr}")
    for vp in value_proof:
        support_points.append(f"{vp.get('attribute')} delivers {vp.get('value')}")

    # --- Final consistency score ---
    consistency_score = max(0.0, min(100.0, consistency_score))
    if consistency_score < 60:
        warnings.append(
            f"consistency_score {consistency_score} below 60 — positioning may be weak"
        )

    return PositioningResult(
        positioning_statement=positioning_statement,
        one_liner=one_liner,
        elevator_pitch=elevator_pitch,
        differentiators=differentiators,
        support_points=support_points,
        consistency_score=consistency_score,
        warnings=warnings,
    )


def get_dna(brand_id: str, action: str = "get") -> dict[str, Any]:
    """Stub for brand-context skill dependency (maref-brand-context@1.0.0).

    In production, this would call the brand-context skill to retrieve brand DNA.
    For the reference implementation, it returns a minimal stub.
    """
    if brand_id.lower() == "maref":
        return {
            "brand_id": "maref",
            "dna": {
                "values": ["rigorous", "open-source", "engineering-grade"],
                "voice": {"tone": "authoritative but accessible"},
                "personality": ["safety-obsessed", "formal-verification-first"],
                "mission": "make governed agent deployment the default",
                "vision": "every agent deployment is governed by default",
                "taboos": ["hype", "vaporware", "closed-source"],
            },
            "consistency_score": 85,
        }
    return {"brand_id": brand_id, "dna": {}, "consistency_score": 0}
