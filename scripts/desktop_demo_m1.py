#!/usr/bin/env python3
"""M1 Desktop Agent Demo — minimal closed-loop visualization.

Usage:
    python scripts/desktop_demo_m1.py               # dry-run mode (safe)
    python scripts/desktop_demo_m1.py --live         # live mode (WARNING: controls mouse!)
    python scripts/desktop_demo_m1.py --task finder  # specific demo task
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from maref.desktop.agent import DesktopAgent, DesktopOperation, DesktopStep, DesktopTask
from maref.desktop.screen_parser import OmniParserInterface


def demo_safe_finder(agent: DesktopAgent) -> None:
    """Demo: Navigate to Finder using Spotlight (dry-run safe)."""
    print("=" * 60)
    print("  MAREF Desktop Agent M1 Demo — Safe Finder Navigation")
    print("=" * 60)
    print(f"  Mode: {'DRY RUN (no real mouse control)' if agent.dry_run else 'LIVE'}")
    print(f"  Parser backend: {agent.parser.backend}")
    print()

    task = DesktopTask(
        task_id="demo-finder-001",
        description="Open Finder via Spotlight search",
        safe_apps=["Finder", "System Events"],
        steps=[
            DesktopStep(
                operation=DesktopOperation.HOTKEY,
                value="command+space",
                description="Open Spotlight",
                wait_seconds=1.0,
            ),
            DesktopStep(
                operation=DesktopOperation.TYPE,
                value="Finder",
                description="Type 'Finder'",
                wait_seconds=0.5,
            ),
            DesktopStep(
                operation=DesktopOperation.HOTKEY,
                value="enter",
                description="Press Enter to launch Finder",
                wait_seconds=2.0,
            ),
            DesktopStep(
                operation=DesktopOperation.WAIT,
                wait_seconds=0.5,
                description="Wait for Finder to appear",
            ),
        ],
    )

    print("  Task:", task.description)
    print("  Steps:", len(task.steps))
    print()

    result = agent.execute_task(task)

    print(f"  Result: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Steps executed: {result.steps_executed}/{len(task.steps)}")
    print(f"  Steps failed: {result.steps_failed}")
    print(f"  Duration: {result.total_duration_ms:.0f}ms")
    print()

    for i, op in enumerate(result.operation_log):
        status = "OK" if op.success else "FAIL"
        print(f"  [{i+1}] {op.action_type}: {status} ({op.details[:60]})")

    print()
    print("=" * 60)
    print("  Demo complete.")
    print("=" * 60)


def demo_parse_screen(agent: DesktopAgent) -> None:
    """Demo: Capture and parse current screen."""
    print("=" * 60)
    print("  MAREF Desktop Agent M1 Demo — Screen Parse")
    print("=" * 60)

    result = agent.capture_screen()
    print(f"  Screenshot: {result.width}x{result.height}, {result.capture_time_ms:.0f}ms")
    print(f"  Redactions: {result.redactions_applied}")

    parse = agent.parse_screen(result)
    print(f"  Parse: {len(parse.elements)} elements, {parse.parse_time_ms:.0f}ms")
    print(f"  Model: {parse.model_name}")

    for elem in parse.find_interactive_elements():
        print(f"    [{elem.element_type.value}] {elem.text[:40]} at {elem.bbox.center}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF M1 Desktop Agent Demo")
    parser.add_argument("--live", action="store_true", help="Enable live mouse control (USE WITH CAUTION)")
    parser.add_argument("--task", choices=["finder", "parse"], default="finder", help="Demo task to run")
    parser.add_argument(
        "--parser-backend", choices=OmniParserInterface.SUPPORTED_BACKENDS,
        default="mock", help="Screen parser backend"
    )
    args = parser.parse_args()

    parser_backend = OmniParserInterface(backend=args.parser_backend)
    parser_backend.initialize()

    agent = DesktopAgent(
        dry_run=not args.live,
        screen_parser=parser_backend,
    )

    if args.task == "parse":
        demo_parse_screen(agent)
    else:
        demo_safe_finder(agent)

    print()
    print(f"  Agent state: {agent.state.value}")


if __name__ == "__main__":
    main()
