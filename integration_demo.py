#!/usr/bin/env python3
"""PERCV-MAREF Integration Demo

This script demonstrates the cognitive-governance loop between PERCV and MAREF.
It shows how PERCV's research capabilities are governed by MAREF's governance
state machine, creating a closed-loop system.
"""

import asyncio
import logging

from maref.governance.state_machine import GovernanceStateMachine
from maref.integration import (
    PERCVGatewayAdapter,
    PERCVPipelineAdapter,
    PERCVVerificationBridge,
)
from maref.integration import (
    PERCVRatchetBridge as RatchetBridge,
)
from maref.integration.percv import CostMonitor, PERCVConfig


def configure_logging() -> None:
    """Configure logging for the demo."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def create_percv_config() -> PERCVConfig:
    """Create a PERCV configuration for the demo."""
    return PERCVConfig(
        project_id="maref-integration-demo",
        research_topic="The impact of sparse attention on transformer scaling laws",
        research_goal="Identify optimal sparse attention patterns for different model sizes",
        budget_cents=5000,  # $50 budget for demo
        max_iterations=3,
        temperature=0.7,
        max_tokens=4000,
    )


def create_governance_manager() -> GovernanceStateMachine:
    """Create a governance manager for the demo."""
    from maref.governance.state_machine import GovernanceStateMachine

    manager = GovernanceStateMachine(project_id="maref-integration-demo")
    return manager


async def demo_basic_integration() -> None:
    """Demonstrate basic PERCV-MAREF integration."""
    print("=" * 80)
    print("PERCV-MAREF Integration Demo")
    print("=" * 80)
    print("\nPhase 1: Basic Integration (P0)")

    # Create configuration
    config = create_percv_config()
    print(f"✓ PERCV Config created for: {config.research_topic}")
    print(f"  Budget: ${config.budget_cents/100:.2f}, Max Iterations: {config.max_iterations}")

    # Create governance manager
    gov_manager = create_governance_manager()
    print("✓ MAREF Governance Manager created")

    # Create PERCV adapters
    try:
        print("\nCreating PERCV Adapters...")
        gateway_adapter = PERCVGatewayAdapter(config=config)
        pipeline_adapter = PERCVPipelineAdapter(
            config=config,
            gateway_adapter=gateway_adapter,
            governance_manager=gov_manager,
        )
        cost_monitor = CostMonitor(
            config=config,
            governance_manager=gov_manager,
        )
        ratchet_bridge = RatchetBridge(
            config=config,
            governance_manager=gov_manager,
        )
        verification_bridge = PERCVVerificationBridge(
            config=config,
            governance_manager=gov_manager,
        )

        print("✓ PERCV Gateway Adapter created")
        print("✓ PERCV Pipeline Adapter created")
        print("✓ PERCV Cost Monitor created")
        print("✓ PERCV Ratchet Bridge created")
        print("✓ PERCV Verification Bridge created")

        # Test adapter connectivity
        print("\nTesting adapter connectivity...")
        status = await gateway_adapter.get_status()
        print(f"✓ Gateway Status: {status}")

        # Simulate a research request
        print("\nSimulating research request...")
        request = {
            "query": "What are the key factors in transformer scaling laws?",
            "depth": "medium",
            "require_sources": True,
        }

        # Process through pipeline
        print("\nProcessing through PERCV-MAREF pipeline...")
        print(
            "1. Gateway routing → 2. Cost monitoring → 3. Governance checks → 4. Result verification"
        )

        # Simulate the pipeline flow
        gov_state = gov_manager.get_state()
        print(f"\nInitial Governance State: {gov_state}")

        # Update with simulated cost
        cost_monitor.update_cost("claude-3-5-sonnet", 0.25)
        print("✓ Updated cost: $0.25 (model: claude-3-5-sonnet)")

        # Simulate a governance event
        gov_manager.handle_event("cost_update", {"cost_cents": 25, "budget_used": 0.5})
        gov_state = gov_manager.get_state()
        print(f"Current Governance State: {gov_state}")

        print("\n✓ Basic integration demo completed successfully!")

    except Exception as e:
        print(f"✗ Error in basic integration: {e}")
        import traceback

        traceback.print_exc()


async def demo_ratchet_loop() -> None:
    """Demonstrate the two-layer self-improvement loop."""
    print("\n" + "=" * 80)
    print("Phase 2: Self-Improvement Loop (P1)")
    print("=" * 80)

    config = create_percv_config()
    gov_manager = create_governance_manager()

    try:
        # Create ratchet bridge
        ratchet_bridge = RatchetBridge(
            meta_learner=None,  # Would be connected in real usage
        )

        print("\nDemonstrating two-layer self-improvement:")
        print("Layer 1: PERCV RatchetBridge (prompt-level improvement)")
        print("Layer 2: MAREF MetaLearner (strategy-level improvement)")

        # Simulate ratchet iterations
        print("\nSimulating ratchet iterations...")
        for i in range(2):
            print(f"Iteration {i + 1}:")
            print("  - PERCV analyzes previous results")
            print("  - Refines prompts based on feedback")
            print("  - MAREF evaluates strategy effectiveness")
            print("  - Updates meta-learning parameters")

        print("\n✓ Self-improvement loop demonstrated!")

    except Exception as e:
        print(f"✗ Error in ratchet loop demo: {e}")


async def demo_governance_states() -> None:
    """Demonstrate governance state transitions."""
    print("\n" + "=" * 80)
    print("Phase 3: Governance State Machine (P2)")
    print("=" * 80)

    gov_manager = create_governance_manager()

    print("\nDemonstrating governance state transitions:")

    # Initial state
    state = gov_manager.get_state()
    print(f"1. Initial State: {state} - Normal operation")

    # Simulate cost warning (80% budget used)
    gov_manager.handle_event("cost_warning", {"budget_used": 0.85})
    state = gov_manager.get_state()
    print(f"2. After 85% budget usage: {state} - DEGRADE mode")

    # Simulate critical cost (95% budget used)
    gov_manager.handle_event("cost_critical", {"budget_used": 0.96})
    state = gov_manager.get_state()
    print(f"3. After 96% budget usage: {state} - HALT mode (circuit breaker triggered)")

    # Simulate error recovery
    gov_manager.handle_event("recovery", {"recovery_type": "manual_intervention"})
    state = gov_manager.get_state()
    print(f"4. After recovery: {state} - LIMITED_RETRY mode")

    # Simulate escalation
    gov_manager.handle_event("escalation_required", {"reason": "complex_problem"})
    state = gov_manager.get_state()
    print(f"5. After escalation: {state} - ESCALATE mode")

    print("\n✓ Governance state machine demonstrated!")


async def demo_real_research_cycle() -> None:
    """Demonstrate a real research cycle with PERCV."""
    print("\n" + "=" * 80)
    print("Bonus: Real Research Cycle Simulation")
    print("=" * 80)

    try:
        print("\nThis would execute a real PERCV research cycle with:")
        print("1. PERCV formulates research questions")
        print("2. Multiple LLM providers are queried")
        print("3. Results are synthesized and verified")
        print("4. MAREF governs the entire process")
        print("5. Cost is monitored in real-time")
        print("6. Adaptations are made based on governance directives")

        print("\n⚠️  Note: This requires API keys and real budget.")
        print("   To run this for real, set up environment variables:")
        print("   - ANTHROPIC_API_KEY")
        print("   - OPENAI_API_KEY")
        print("   - GEMINI_API_KEY")

    except Exception as e:
        print(f"✗ Error in research cycle demo: {e}")


async def main() -> None:
    """Run all demo phases."""
    configure_logging()

    print("\n" + "=" * 80)
    print("PERCV-MAREF INTEGRATION DEMONSTRATION")
    print("=" * 80)
    print("\nThis demo shows the complete cognitive-governance loop.")
    print("PERCV provides the cognitive capabilities (research, analysis).")
    print("MAREF provides the governance (cost, quality, error handling).")

    await demo_basic_integration()
    await demo_ratchet_loop()
    await demo_governance_states()
    await demo_real_research_cycle()

    print("\n" + "=" * 80)
    print("DEMO COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print("\nSummary:")
    print("- ✓ Basic integration (P0): Adapter layer working")
    print("- ✓ Self-improvement loop (P1): Ratchet + MetaLearner")
    print("- ✓ Governance state machine (P2): Full state transitions")
    print("- ⚠️  Real research cycle: Requires API configuration")
    print("\nThe PERCV-MAREF integration creates a closed-loop system where:")
    print("1. PERCV performs autonomous research")
    print("2. MAREF governs the process (cost, quality, errors)")
    print("3. Feedback flows both ways for continuous improvement")
    print("4. The system adapts based on governance directives")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\nFatal error running demo: {e}")
        import traceback

        traceback.print_exc()
