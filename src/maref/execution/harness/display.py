"""Harness 结果显示格式化。"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from maref.execution.harness.types import HarnessResult


def format_harness_result(
    result: HarnessResult,
    lifecycle_history: list[str],
    lifecycle_terminal: bool,
    governance_state: str,
    circuit_breaker_state: str,
    halt_triggered: bool,
    check_count: int,
    console: Console | None = None,
) -> None:
    """将 Harness 结果用 rich 表格展示。"""
    c = console or Console()

    if result.passed:
        c.print(f"\n[green]PASS[/green] ({result.duration_s:.1f}s)")
    else:
        c.print(f"\n[red]FAIL[/red] ({result.duration_s:.1f}s)")

    table = Table(title="Lifecycle")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Harness Type", result.harness_type)
    table.add_row("Round ID", result.round_id or "(auto)")
    table.add_row("Status", result.status.value)
    table.add_row("Duration", f"{result.duration_s:.2f}s")
    table.add_row("Lifecycle History", " → ".join(lifecycle_history))
    table.add_row("Lifecycle Terminal", str(lifecycle_terminal))
    c.print(table)

    gov_table = Table(title="Governance")
    gov_table.add_column("Property", style="cyan")
    gov_table.add_column("Value", style="green")
    gov_table.add_row("Governance State", governance_state)
    gov_table.add_row("Circuit Breaker", circuit_breaker_state)
    gov_table.add_row("HALT Triggered", str(halt_triggered))
    gov_table.add_row("Check Count", str(check_count))
    c.print(gov_table)

    if result.errors:
        c.print("[red]Errors:[/red]")
        for e in result.errors[:5]:
            c.print(f"  • {e}")
