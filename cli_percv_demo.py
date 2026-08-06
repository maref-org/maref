#!/usr/bin/env python3
"""PERCV-MAREF Integration CLI Demo.

This script demonstrates a simple CLI for running PERCV research through MAREF governance.
"""

import argparse
import asyncio
import sys

from maref.integration.percv import PERCVConfig, PERCVGatewayAdapter, PERCVPipelineAdapter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PERCV-MAREF Integration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --topic "AI safety" --goal "Identify key risks"
  %(prog)s --topic "Quantum computing" --budget 1000 --iterations 5
        """,
    )

    parser.add_argument(
        "--topic",
        required=True,
        help="Research topic",
    )

    parser.add_argument(
        "--goal",
        default="Explore and analyze the topic",
        help="Research goal",
    )

    parser.add_argument(
        "--budget",
        type=int,
        default=5000,
        help="API budget in cents (default: 5000 = $50)",
    )

    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Maximum research iterations (default: 3)",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="LLM temperature (default: 0.7)",
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4000,
        help="Maximum tokens per response (default: 4000)",
    )

    return parser.parse_args()


async def run_research(args: argparse.Namespace) -> dict:
    """Run a PERCV research cycle through MAREF integration."""
    print("🔍 Starting PERCV-MAREF Integration")
    print(f"   Topic: {args.topic}")
    print(f"   Goal: {args.goal}")
    print(f"   Budget: ${args.budget/100:.2f}")
    print(f"   Iterations: {args.iterations}")
    print()

    # Create configuration
    config = PERCVConfig(
        project_id=f"percv-cli-{hash(args.topic) % 1000}",
        research_topic=args.topic,
        research_goal=args.goal,
        budget_cents=args.budget,
        max_iterations=args.iterations,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    print("✓ Configuration created")

    # Create adapters
    gateway = PERCVGatewayAdapter(config=config)
    # Note: PipelineAdapter would need governance_manager in production
    pipeline = PERCVPipelineAdapter(config=config, gateway_adapter=gateway)

    print("✓ Adapters created")

    # Check gateway status
    status = await gateway.get_status()
    print(f"✓ Gateway status: {status['status']}")

    # Check available providers
    providers = await gateway.get_providers()
    print(f"✓ Available providers: {providers['count']}")

    # Simulate a research query
    print()
    print("📝 Simulating research query...")

    # In a real implementation, this would call pipeline.run_research_cycle()
    # For now, just show that the integration is working
    print("""
In a full implementation, the PERCV-MAREF pipeline would:
  1. Formulate research questions
  2. Query multiple LLM providers via the gateway
  3. Synthesize and cross-verify results
  4. Apply MAREF governance checks
  5. Monitor cost against budget
  6. Produce research cards
  7. Sync to knowledge graph
""")

    return {
        "success": True,
        "config": {
            "project_id": config.project_id,
            "topic": config.research_topic,
            "goal": config.research_goal,
            "budget": config.budget_cents,
        },
        "gateway": {
            "status": status["status"],
            "providers": providers["count"],
            "router_available": status.get("router_available", False),
        },
    }


def main() -> None:
    """Main CLI entry point."""
    args = parse_args()

    try:
        print("=" * 60)
        print("PERCV-MAREF INTEGRATION CLI")
        print("=" * 60)

        result = asyncio.run(run_research(args))

        print()
        print("=" * 60)
        print("RESULTS")
        print("=" * 60)
        print("✅ Integration successful")
        print(f"   Project ID: {result['config']['project_id']}")
        print(f"   Gateway: {result['gateway']['status']}")
        print(f"   Providers available: {result['gateway']['providers']}")
        print()
        print("To run actual research, you need to:")
        print("  1. Set up API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)")
        print("  2. Configure a governance manager")
        print("  3. Call pipeline.run_research_cycle()")

    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
