"""Demo: Run all 3 PMM Skills against MAREF itself (eating our own dog food).

Runs the Positioning Validation, Messaging Testing, and Competitive
Intelligence studies against MAREF's own positioning artifacts, in
self-assessment mode (no persona panel recruited).

This demo is honest about its limitations: self-assessment is a methodology
check and gap analysis, NOT market validation. The output report flags every
dimension that requires a real recruited panel to answer.

Run:
    python3 docs/skills/pmm-research/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "implementation"))

from study_runner import (  # noqa: E402
    run_competitive_intelligence,
    run_messaging_testing,
    run_positioning_validation,
)


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    print("MAREF PMM Research Skills — Self-Assessment Demo")
    print("(Eating our own dog food: validating MAREF's positioning with our own Skills)")

    # =====================================================================
    # Study 1: Positioning Validation
    # =====================================================================
    section("STUDY 1: Positioning Validation (7-question framework)")

    pv = run_positioning_validation(
        product={
            "name": "MAREF",
            "description": "Agent governance and skill marketplace OS",
            "unique_value_prop": (
                "TLA+ formal verification with 5 proven theorems + 10-state "
                "Gray Code governance FSM — the missing governance layer for "
                "LangGraph/CrewAI/AutoGen"
            ),
        },
        competitors=["LangGraph", "CrewAI", "AutoGen"],
        problem_space="agent governance for production deployments",
    )

    print(f"mode: {pv.mode}")
    for note in pv.notes:
        print(f"note: {note}")
    print()
    print("Study design (7 questions):")
    for q in pv.study_questions:
        print(f"  Q{q['number']} [{q['tests']}]: {q['question'][:80]}...")
    print()
    print("Positioning scorecard (1-5, self-assessment):")
    for dim, result in pv.positioning_scorecard.items():
        print(f"  {dim}: {result['score']}/5 — {result['evidence']}")
    print()
    print("Risk flags:")
    for flag in pv.risk_flags:
        print(f"  ⚠️  {flag}")
    print()
    print("Competitive alternative map:")
    for comp, data in pv.competitive_alternative_map.items():
        print(f"  {comp}: named_in_positioning={data['named_in_positioning']}")

    # =====================================================================
    # Study 2: Messaging Testing
    # =====================================================================
    section("STUDY 2: Messaging Testing (3 tagline variants)")

    mt = run_messaging_testing(
        product={"name": "MAREF", "description": "Agent governance OS"},
        messages=[
            {
                "id": "a",
                "variant": "problem_led",
                "text": (
                    "88% of companies had an AI agent incident last year. "
                    "MAREF is the missing governance layer."
                ),
            },
            {
                "id": "b",
                "variant": "outcome_led",
                "text": (
                    "Build with LangGraph. Govern with MAREF. "
                    "Ship to production with confidence."
                ),
            },
            {
                "id": "c",
                "variant": "capability_led",
                "text": (
                    "TLA+ verified. 10-state Gray Code. "
                    "Three-gate skill marketplace. Apache 2.0."
                ),
            },
        ],
    )

    print(f"mode: {mt.mode}")
    for note in mt.notes:
        print(f"note: {note}")
    print()
    print("Message performance ranking:")
    for rank, msg in enumerate(mt.message_performance_ranking, 1):
        print(f"  #{rank} (variant={msg['variant']}, score={msg['score']}): {msg['text'][:60]}...")
    print()
    print(f"Recommended primary message: {mt.recommended_primary_message}")

    # =====================================================================
    # Study 3: Competitive Intelligence
    # =====================================================================
    section("STUDY 3: Competitive Intelligence (MAREF vs 3 competitors)")

    ci = run_competitive_intelligence(
        product={
            "name": "MAREF",
            "description": "Agent governance and skill marketplace OS",
            "key_claim": "TLA+ formal verification + 10-state Gray Code governance FSM",
        },
        competitors=[
            {
                "name": "LangGraph",
                "known_strength": "graph-based orchestration, large ecosystem",
                "known_weakness": "no governance layer, no formal verification",
            },
            {
                "name": "CrewAI",
                "known_strength": "role-based agent design, easy to start",
                "known_weakness": "no runtime safety gates, no audit trail",
            },
            {
                "name": "AutoGen",
                "known_strength": "Microsoft-backed, multi-agent conversation",
                "known_weakness": "no circuit breakers, no skill marketplace",
            },
        ],
        category="agent orchestration and governance frameworks",
    )

    print(f"mode: {ci.mode}")
    for note in ci.notes:
        print(f"note: {note}")
    print()
    print("Competitive perception matrix:")
    for comp, data in ci.competitive_perception_matrix.items():
        print(f"  {comp}:")
        print(f"    strength: {data['known_strength']}")
        print(f"    weakness: {data['known_weakness']}")
        print(f"    maref_advantage: {data['maref_advantage']}")
    print()
    print("Landmine questions (sales must prepare for):")
    for q in ci.landmine_questions:
        print(f"  💣 {q}")
    print()
    print("Win themes:")
    for t in ci.win_themes:
        print(f"  ✅ {t}")
    print()
    print("Loss themes:")
    for t in ci.loss_themes:
        print(f"  ❌ {t}")
    print()
    print("Battlecard (JSON):")
    print(json.dumps(ci.battlecard, indent=2))

    # =====================================================================
    # Summary
    # =====================================================================
    section("SUMMARY")
    print("All 3 PMM studies ran in self-assessment mode against MAREF.")
    print()
    print("What this proves:")
    print("  ✅ The 7-question frameworks are correctly encoded and runnable.")
    print("  ✅ The Skills produce structured deliverables (scorecard, ranking, battlecard).")
    print("  ✅ Self-assessment mode surfaces positioning gaps and risk flags.")
    print()
    print("What this does NOT prove:")
    print("  ❌ Market validation — requires a recruited persona panel (Ditto API or human study).")
    print("  ❌ Real competitive perception — inferred from public docs, not panel responses.")
    print("  ❌ Adoption barriers — self-assessment cannot surface these.")
    print()
    print("Next step: acquire Ditto API key and re-run in panel_study mode.")


if __name__ == "__main__":
    main()
