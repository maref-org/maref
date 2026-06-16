"""
MAREF Recursive Evolution — CLI Entry Point.

Usage:
    python -m maref.evolution [--dry-run] [--output-dir DIR]
                              [--rounds N] [--resume-from CYCLE] [--resume-round N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from rich.console import Console

from maref.evolution.engine import EvolutionConfig, RecursiveEvolutionEngine

logger = structlog.get_logger(__name__)
console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MAREF Recursive Evolution — 3-cycle engine",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a single round to validate pipeline integrity",
    )
    parser.add_argument(
        "--output-dir",
        default="./evolution_results/",
        help="Output directory for reports and metrics",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=200,
        help="Max total rounds across all cycles",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Resume from a specific cycle (c1/c2/c3)",
    )
    parser.add_argument(
        "--resume-round",
        type=int,
        default=0,
        help="Resume from a specific round within the cycle",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    return parser


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = EvolutionConfig()
    config.dry_run = args.dry_run
    if args.dry_run:
        config.dry_run_rounds = 1
    config.output_dir = args.output_dir
    config.max_total_rounds = args.rounds
    if args.resume_from:
        config.resume_from_cycle = args.resume_from
        config.resume_from_round = args.resume_round

    engine = RecursiveEvolutionEngine(config=config)

    if args.verbose:
        logger.info("Evolution engine starting...")
        logger.info("  dry_run=%s", config.dry_run)
        logger.info("  output_dir=%s", config.output_dir)
        logger.info("  max_rounds=%s", config.max_total_rounds)
        if config.resume_from_cycle:
            logger.info("  resume_from=%s:%s", config.resume_from_cycle, config.resume_from_round)

    try:
        result = await engine.run()
    except KeyboardInterrupt:
        console.print("\nInterrupted — stopping gracefully...")
        engine.stop()
        result = await engine.run()
    except Exception as e:
        logger.error("Fatal error: %s", e)
        return 1

    console.print(result.summary())

    if result.all_passed:
        console.print("\nRecursive evolution completed successfully.")
        return 0
    else:
        console.print("\nRecursive evolution completed with failures — see report.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
