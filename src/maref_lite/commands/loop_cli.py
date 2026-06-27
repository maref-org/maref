"""
MAREF Loop CLI — run convergent/exploratory/interactive loops from the command line.

Usage:
    maref loop run convergent "improve this code" --max-rounds 10
    maref loop run exploratory "agent governance patterns" --max-rounds 20
    maref loop run interactive
    maref loop list
    maref loop cancel <task-id>
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

loop_app = typer.Typer(name="loop", help="Loop Engineering commands", no_args_is_help=True)
console = Console()


@loop_app.command("run")
def loop_run(
    loop_type: str = typer.Argument(
        ..., help="Loop type: convergent, exploratory, interactive"
    ),
    input_data: str = typer.Argument(
        "", help="Input for the loop (seed topic for exploratory, initial input for convergent)"
    ),
    max_rounds: int = typer.Option(10, "--max-rounds", "-n", help="Maximum rounds"),
    convergence_threshold: float = typer.Option(
        0.01, "--threshold", "-t", help="Convergence threshold (convergent only)"
    ),
    diversity_threshold: float = typer.Option(
        0.3, "--diversity", "-d", help="Diversity threshold (exploratory only)"
    ),
    coverage_target: float = typer.Option(
        0.8, "--coverage", "-c", help="Coverage target (exploratory only)"
    ),
    max_tokens: int = typer.Option(10000, "--max-tokens", "-m", help="Max tokens (exploratory only)"),
    budget: float = typer.Option(0.0, "--budget", "-b", help="Agent budget hard limit"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Run a governed loop (convergent / exploratory / interactive)."""
    loop_type = loop_type.lower()

    if loop_type not in {"convergent", "exploratory", "interactive"}:
        console.print(f"[red]Unknown loop type: {loop_type}[/red]")
        console.print("Valid: convergent, exploratory, interactive")
        raise typer.Exit(code=1)

    if loop_type == "interactive":
        if input_data:
            console.print("[yellow]Interactive mode ignores input argument.[/yellow]")
        _run_interactive(max_rounds, verbose)
        return

    if not input_data:
        console.print("[red]Input required for convergent/exploratory loops[/red]")
        raise typer.Exit(code=1)

    if loop_type == "convergent":
        _run_convergent(input_data, max_rounds, convergence_threshold, verbose)
    elif loop_type == "exploratory":
        _run_exploratory(input_data, max_rounds, diversity_threshold, coverage_target, max_tokens, verbose)


def _run_convergent(
    input_data: str, max_rounds: int, threshold: float, verbose: bool,
) -> None:
    from maref.loop import ConvergentLoop, LoopGovernanceBridge

    async def _run() -> None:
        bridge = LoopGovernanceBridge()

        def execute_fn(x: Any) -> Any:
            return {"input": x, "result": f"processed: {x}"}

        def evaluator(result: Any) -> Any:
            from maref.loop.protocols import EvaluationResult
            return EvaluationResult(score=0.5)

        loop = ConvergentLoop(
            execute_fn=execute_fn,
            evaluator=evaluator,
            max_rounds=max_rounds,
            convergence_threshold=threshold,
        )

        console.print("[bold cyan]Convergent Loop[/bold cyan]")
        console.print(f"  Input:        [green]{input_data[:80]}[/green]")
        console.print(f"  Max rounds:   [yellow]{max_rounds}[/yellow]")
        console.print(f"  Threshold:    [yellow]{threshold}[/yellow]")

        result = await bridge.run_governed(loop, input_data)

        _print_result(result, verbose)

    asyncio.run(_run())


def _run_exploratory(
    seed: str, max_rounds: int, diversity: float, coverage: float,
    max_tokens: int, verbose: bool,
) -> None:
    from maref.loop import ExploratoryLoop, LoopGovernanceBridge

    async def _run() -> None:
        bridge = LoopGovernanceBridge()

        def generator(discoveries: list[Any], branch: int) -> list[Any]:
            from maref.loop.protocols import Discovery
            topics = [
                Discovery(content=f"{seed}: aspect-{i}", tags=[seed, f"tag-{i}"])
                for i in range(branch)
            ]
            return topics

        loop = ExploratoryLoop(
            generator=generator,
            max_rounds=max_rounds,
            diversity_threshold=diversity,
            coverage_target=coverage,
            max_tokens=max_tokens,
        )

        console.print("[bold cyan]Exploratory Loop[/bold cyan]")
        console.print(f"  Seed:          [green]{seed[:80]}[/green]")
        console.print(f"  Max rounds:    [yellow]{max_rounds}[/yellow]")
        console.print(f"  Diversity:     [yellow]{diversity}[/yellow]")
        console.print(f"  Coverage:      [yellow]{coverage}[/yellow]")

        result = await bridge.run_governed(loop, seed)

        _print_result(result, verbose)

    asyncio.run(_run())


def _run_interactive(max_turns: int, verbose: bool) -> None:
    from maref.loop import InteractiveLoop, LoopGovernanceBridge

    async def _run() -> None:
        bridge = LoopGovernanceBridge()

        def respond_fn(msg: str, ctx: list[dict[str, str]]) -> str:
            return f"You said: {msg}. (turn {len(ctx) // 2 + 1})"

        loop = InteractiveLoop(
            respond_fn=respond_fn,
            max_turns=max_turns,
        )

        console.print("[bold cyan]Interactive Loop[/bold cyan]")
        console.print("  Type messages. Enter 'bye' or 'quit' to end.")
        console.print()

        result = await bridge.run_governed(loop, "")

        _print_result(result, verbose)

    asyncio.run(_run())


def _print_result(result: Any, verbose: bool) -> None:
    console.print()
    console.print("[bold]Result[/bold]")
    console.print(f"  Stop reason:   [cyan]{result.stop_reason.value}[/cyan]")
    console.print(f"  Rounds:        [yellow]{result.rounds_completed}[/yellow]")

    if result.errors:
        console.print(f"  Errors:        [red]{len(result.errors)}[/red]")
        for e in result.errors[:3]:
            console.print(f"    - {e}")

    if verbose and hasattr(result, "convergence_history") and result.convergence_history:
        console.print()
        console.print("[bold]Convergence History[/bold]")
        for i, s in enumerate(result.convergence_history):
            console.print(f"  Round {i + 1}: score={s:.4f}")


@loop_app.command("list")
def loop_list() -> None:
    """List tasks managed by the in-process harness."""
    console.print("[bold]Loop Tasks[/bold]")
    console.print("[dim]Active only during a running 'maref loop run' session.[/dim]")
    console.print()
    table = Table(title="Loop Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="yellow")
    table.add_column("Type", style="green")
    table.add_column("Status", style="white")
    table.add_column("Rounds", style="white")
    console.print(table)
    console.print()
    console.print("Use [cyan]maref loop run[/cyan] to start a new loop.")


@loop_app.command("cancel")
def loop_cancel(
    task_id: str = typer.Argument(..., help="Task ID to cancel"),
) -> None:
    """Cancel a running loop task."""
    console.print(f"[yellow]Cancel requested for task: {task_id}[/yellow]")
    console.print("[dim]Cancellation requires a running harness session.[/dim]")


if __name__ == "__main__":
    loop_app()
